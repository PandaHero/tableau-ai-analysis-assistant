# -*- coding: utf-8 -*-
"""
Dimension Pattern FAISS 向量索引（LangChain 版本）

提供维度模式的向量存储和高效检索功能，基于 LangChain FAISS wrapper。

职责：
- 向量存储和高效检索（ANN）
- 持久化到磁盘
- 启动时加载

与 LangGraph Store 配合：
- FAISS 存向量 + pattern_id
- LangGraph Store 存模式详情（category, level 等）

关键实现约束：
- 入库和查询时都必须 L2 归一化，否则相似度分数无意义
- 使用 IndexFlatIP（内积），归一化后等价于余弦相似度

Requirements: 1.1, 2.1, 2.2, 2.3
"""
from typing import List, Dict, Any, Optional, Tuple
import logging
from pathlib import Path

import numpy as np
import faiss
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# 默认配置
# ═══════════════════════════════════════════════════════════

DEFAULT_INDEX_PATH = "data/indexes/dimension_patterns"
DEFAULT_DIMENSION = 1024  # 智谱 Embedding 维度


class DimensionPatternFAISS:
    """
    维度模式 FAISS 向量索引（LangChain 版本）
    
    职责：
    - 向量存储和高效检索（ANN）
    - 持久化到磁盘
    - 启动时加载
    
    与 LangGraph Store 配合：
    - FAISS 存向量 + pattern_id
    - LangGraph Store 存模式详情（category, level 等）
    
    关键实现：
    - 使用 LangChain FAISS wrapper 简化操作
    - 使用 IndexFlatIP（内积）作为索引类型
    - 入库和查询时都做 L2 归一化，使内积等价于余弦相似度
    - 支持批量操作以减少 API 调用
    """
    
    def __init__(
        self,
        embedding_provider,
        index_path: str = DEFAULT_INDEX_PATH,
        dimension: int = DEFAULT_DIMENSION,
    ):
        """
        Args:
            embedding_provider: Embedding 提供者（需实现 embed_documents, embed_query）
            index_path: 索引文件路径
            dimension: 向量维度（默认 1024，智谱 Embedding）
        """
        self._embedding_provider = embedding_provider
        self._index_path = index_path
        self._dimension = dimension
        
        # LangChain FAISS vectorstore
        self._vectorstore: Optional[FAISS] = None
        self._loaded = False

    # ═══════════════════════════════════════════════════════════
    # 索引加载和创建
    # ═══════════════════════════════════════════════════════════
    
    def load_or_create(self) -> bool:
        """
        加载或创建索引
        
        Returns:
            是否成功
        """
        if self._loaded:
            return True
        
        index_file = Path(self._index_path)
        faiss_file = index_file / "index.faiss"
        
        if index_file.exists() and faiss_file.exists():
            try:
                # 使用 LangChain FAISS 加载
                self._vectorstore = FAISS.load_local(
                    str(index_file),
                    self._embedding_provider,
                    allow_dangerous_deserialization=True,
                )
                self._loaded = True
                logger.info(f"FAISS 索引已加载: {self._index_path}, 向量数: {self.count}")
                return True
            except Exception as e:
                logger.warning(f"加载 FAISS 索引失败: {e}，将创建新索引")
        
        # 创建空索引
        self._create_empty_index()
        self._loaded = True
        logger.info("FAISS 空索引已创建")
        return True
    
    def _create_empty_index(self) -> None:
        """创建空的 FAISS 索引"""
        # 使用 IndexFlatIP（内积）适合余弦相似度（需要归一化向量）
        index = faiss.IndexFlatIP(self._dimension)
        
        self._vectorstore = FAISS(
            embedding_function=self._embedding_provider,
            index=index,
            docstore=InMemoryDocstore({}),
            index_to_docstore_id={},
        )
    
    # ═══════════════════════════════════════════════════════════
    # 向量归一化
    # ═══════════════════════════════════════════════════════════
    
    @staticmethod
    def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
        """
        L2 归一化向量
        
        归一化后，内积等价于余弦相似度。
        
        Args:
            vectors: 形状为 (n, d) 的向量数组
        
        Returns:
            归一化后的向量数组
        """
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        faiss.normalize_L2(vectors)
        return vectors
    
    # ═══════════════════════════════════════════════════════════
    # 添加模式
    # ═══════════════════════════════════════════════════════════
    
    def add_pattern(
        self,
        pattern_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        添加单个模式到索引（带归一化）
        
        Args:
            pattern_id: 模式 ID
            text: 用于 embedding 的文本
            metadata: 元数据（可选）
        
        Returns:
            是否成功
        
        注意：必须对向量做 L2 归一化，否则 IndexFlatIP 的内积不等于余弦相似度
        """
        if not self._loaded:
            self.load_or_create()
        
        try:
            # 1. 计算 embedding
            vector = self._embedding_provider.embed_query(text)
            
            # 2. 维度校验（关键！避免换模型后 silent degradation）
            if len(vector) != self._dimension:
                logger.error(
                    f"Embedding 维度不匹配: 期望 {self._dimension}, 实际 {len(vector)}。"
                    f"请检查 embedding_provider 配置是否与 FAISS 索引一致。"
                )
                return False
            
            # 3. L2 归一化（关键！）
            vector_array = np.array([vector], dtype=np.float32)
            vector_array = self._normalize_vectors(vector_array)
            
            # 4. 直接添加到 FAISS 索引
            start_idx = self._vectorstore.index.ntotal
            self._vectorstore.index.add(vector_array)
            
            # 5. 更新 docstore
            doc_id = str(start_idx)
            doc = Document(
                page_content=text,
                metadata={"pattern_id": pattern_id, **(metadata or {})},
            )
            self._vectorstore.docstore.add({doc_id: doc})
            self._vectorstore.index_to_docstore_id[start_idx] = doc_id
            
            logger.debug(f"模式已添加到 FAISS: {pattern_id}")
            return True
        except Exception as e:
            logger.warning(f"添加模式到 FAISS 失败: {e}")
            return False

    def batch_add_patterns(
        self,
        patterns: List[Dict[str, Any]],
    ) -> int:
        """
        批量添加模式到索引（带归一化）
        
        Args:
            patterns: [{"pattern_id": str, "text": str, "metadata": dict}, ...]
        
        Returns:
            成功添加的数量
            
        注意：必须对向量做 L2 归一化，否则 IndexFlatIP 的内积不等于余弦相似度
        """
        if not self._loaded:
            self.load_or_create()
        
        if not patterns:
            return 0
        
        try:
            # 1. 批量计算 embedding（单次 API 调用）
            texts = [p["text"] for p in patterns]
            vectors = self._embedding_provider.embed_documents(texts)
            
            # 2. 维度校验（关键！避免换模型后 silent degradation）
            if vectors and len(vectors[0]) != self._dimension:
                logger.error(
                    f"Embedding 维度不匹配: 期望 {self._dimension}, 实际 {len(vectors[0])}。"
                    f"请检查 embedding_provider 配置是否与 FAISS 索引一致。"
                )
                return 0
            
            # 3. L2 归一化（关键！）
            vectors_array = np.array(vectors, dtype=np.float32)
            vectors_array = self._normalize_vectors(vectors_array)
            
            # 4. 批量添加到 FAISS 索引
            start_idx = self._vectorstore.index.ntotal
            self._vectorstore.index.add(vectors_array)
            
            # 5. 更新 docstore
            for i, p in enumerate(patterns):
                doc_id = str(start_idx + i)
                doc = Document(
                    page_content=p["text"],
                    metadata={"pattern_id": p["pattern_id"], **(p.get("metadata") or {})},
                )
                self._vectorstore.docstore.add({doc_id: doc})
                self._vectorstore.index_to_docstore_id[start_idx + i] = doc_id
            
            logger.info(f"批量添加 {len(patterns)} 个模式到 FAISS（已归一化）")
            return len(patterns)
        except Exception as e:
            logger.warning(f"批量添加模式失败: {e}")
            return 0
    
    # ═══════════════════════════════════════════════════════════
    # 检索
    # ═══════════════════════════════════════════════════════════
    
    def search(
        self,
        query_text: str,
        k: int = 5,
    ) -> List[Tuple[str, float]]:
        """
        检索相似模式
        
        Args:
            query_text: 查询文本
            k: 返回的最大结果数
        
        Returns:
            [(pattern_id, similarity_score), ...]
            similarity_score 范围 [-1, 1]，越大越相似
        """
        if not self._loaded:
            self.load_or_create()
        
        if not self._vectorstore or self.count == 0:
            return []
        
        try:
            # 1. 计算查询向量
            query_vector = self._embedding_provider.embed_query(query_text)
            
            # 2. 维度校验
            if len(query_vector) != self._dimension:
                logger.error(
                    f"查询 Embedding 维度不匹配: 期望 {self._dimension}, 实际 {len(query_vector)}。"
                    f"请检查 embedding_provider 配置是否与 FAISS 索引一致。"
                )
                return []
            
            # 3. L2 归一化
            query_array = np.array([query_vector], dtype=np.float32)
            query_array = self._normalize_vectors(query_array)
            
            # 4. 搜索
            actual_k = min(k, self.count)
            scores, indices = self._vectorstore.index.search(query_array, actual_k)
            
            # 5. 转换结果
            results = []
            for i in range(len(indices[0])):
                idx = indices[0][i]
                score = scores[0][i]
                
                if idx == -1:  # FAISS 返回 -1 表示无结果
                    continue
                
                # 从 docstore 获取 pattern_id
                doc_id = self._vectorstore.index_to_docstore_id.get(idx)
                if doc_id:
                    doc = self._vectorstore.docstore.search(doc_id)
                    if doc and hasattr(doc, 'metadata'):
                        pattern_id = doc.metadata.get("pattern_id", "")
                        results.append((pattern_id, float(score)))
            
            return results
        except Exception as e:
            logger.warning(f"FAISS 检索失败: {e}")
            return []

    def batch_search(
        self,
        query_texts: List[str],
        k: int = 1,
    ) -> List[List[Tuple[str, float]]]:
        """
        批量检索（真正的批量 Embedding，单次 API 调用）
        
        优化点：
        - 原方案：N 个查询 = N 次 Embedding API 调用
        - 优化后：N 个查询 = 1 次批量 Embedding API 调用
        
        Args:
            query_texts: 查询文本列表
            k: 每个查询返回的最大结果数
        
        Returns:
            [[(pattern_id, score), ...], ...]
        """
        if not self._loaded:
            self.load_or_create()
        
        if not self._vectorstore or self.count == 0 or not query_texts:
            return [[] for _ in query_texts]
        
        try:
            # 1. 批量计算 embedding（单次 API 调用）
            query_vectors = self._embedding_provider.embed_documents(query_texts)
            
            # 2. 维度校验
            if query_vectors and len(query_vectors[0]) != self._dimension:
                logger.error(
                    f"批量查询 Embedding 维度不匹配: 期望 {self._dimension}, 实际 {len(query_vectors[0])}。"
                    f"请检查 embedding_provider 配置是否与 FAISS 索引一致。"
                )
                return [[] for _ in query_texts]
            
            # 3. L2 归一化
            query_array = np.array(query_vectors, dtype=np.float32)
            query_array = self._normalize_vectors(query_array)
            
            # 4. 批量搜索
            actual_k = min(k, self.count)
            scores, indices = self._vectorstore.index.search(query_array, actual_k)
            
            # 5. 转换结果
            results = []
            for i in range(len(query_texts)):
                query_results = []
                for j in range(actual_k):
                    idx = indices[i][j]
                    score = scores[i][j]
                    
                    if idx == -1:  # FAISS 返回 -1 表示无结果
                        continue
                    
                    # 从 docstore 获取 pattern_id
                    doc_id = self._vectorstore.index_to_docstore_id.get(idx)
                    if doc_id:
                        doc = self._vectorstore.docstore.search(doc_id)
                        if doc and hasattr(doc, 'metadata'):
                            pattern_id = doc.metadata.get("pattern_id", "")
                            query_results.append((pattern_id, float(score)))
                
                results.append(query_results)
            
            logger.debug(f"批量检索完成: {len(query_texts)} 个查询, 1 次 Embedding API 调用")
            return results
            
        except Exception as e:
            logger.warning(f"批量检索失败: {e}，回退到逐个检索")
            # 回退到逐个检索
            return [self.search(text, k) for text in query_texts]
    
    # ═══════════════════════════════════════════════════════════
    # 持久化
    # ═══════════════════════════════════════════════════════════
    
    def save(self) -> bool:
        """
        持久化到磁盘
        
        Returns:
            是否成功
        """
        if not self._vectorstore:
            return False
        
        try:
            index_path = Path(self._index_path)
            index_path.mkdir(parents=True, exist_ok=True)
            
            # 使用 LangChain FAISS 保存
            self._vectorstore.save_local(str(index_path))
            
            logger.info(f"FAISS 索引已保存: {self._index_path}, 向量数: {self.count}")
            return True
        except Exception as e:
            logger.warning(f"保存 FAISS 索引失败: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════
    # 重建索引
    # ═══════════════════════════════════════════════════════════
    
    def rebuild_index(self, patterns: List[Dict[str, Any]]) -> bool:
        """
        重建索引（用于删除模式后）
        
        FAISS 不支持高效删除，需要重建索引。
        
        Args:
            patterns: [{"pattern_id": str, "text": str}, ...]
        
        Returns:
            是否成功
        """
        try:
            # 创建新的空索引
            self._create_empty_index()
            self._loaded = True
            
            # 批量添加
            if patterns:
                self.batch_add_patterns(patterns)
            
            # 保存
            self.save()
            
            logger.info(f"FAISS 索引已重建: {len(patterns)} 个模式")
            return True
        except Exception as e:
            logger.warning(f"重建 FAISS 索引失败: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════
    # 属性
    # ═══════════════════════════════════════════════════════════
    
    @property
    def count(self) -> int:
        """索引中的向量数量"""
        if not self._vectorstore:
            return 0
        return self._vectorstore.index.ntotal
    
    @property
    def dimension(self) -> int:
        """向量维度"""
        return self._dimension
    
    @property
    def is_loaded(self) -> bool:
        """索引是否已加载"""
        return self._loaded


__all__ = [
    "DimensionPatternFAISS",
    "DEFAULT_INDEX_PATH",
    "DEFAULT_DIMENSION",
]
