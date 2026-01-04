"""
字段索引"


主要功能"
- 构建增强索引文本
- 支持元数据过"
- 支持增量更新
- 支持索引持久化（FAISS"
"""
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Tuple
from dataclasses import dataclass, field

try:
    # 抑制 FAISS "AVX512/AVX2 加载日志
    import logging as _logging
    _faiss_logger = _logging.getLogger("faiss.loader")
    _faiss_logger.setLevel(_logging.WARNING)
    
    import faiss
    import numpy as np
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logging.warning("FAISS 未安装，将使用简单向量搜索。安装命 pip install faiss-cpu")

from .models import FieldChunk, RetrievalResult, RetrievalSource
from .embeddings import EmbeddingProvider, EmbeddingProviderFactory
from .cache import CachedEmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass
class IndexConfig:
    """
    索引配置
    
    Attributes:
        max_samples: 最大样本值数"
        include_formula: 是否包含公式
        include_table_caption: 是否包含表名
        include_category: 是否包含维度类别
    """
    max_samples: int = 5
    include_formula: bool = True
    include_table_caption: bool = True
    include_category: bool = True


class FieldIndexer:
    """
    字段索引"
    
    构建和管理字段的向量索引，支持语义检索"
   
    
    Attributes:
        embedding_provider: Embedding 提供"
        index_config: 索引配置
        datasource_luid: 数据"LUID（命名空间）
    """
    
    def __init__(
        self,
        embedding_provider: Optional[EmbeddingProvider] = None,
        index_config: Optional[IndexConfig] = None,
        datasource_luid: Optional[str] = None,
        index_dir: str = "data/indexes",
        use_cache: bool = True
    ):
        """
        初始化字段索引器
        
        Args:
            embedding_provider: Embedding 提供者（默认使用 Mock"
            index_config: 索引配置
            datasource_luid: 数据"LUID
            index_dir: 索引存储目录
            use_cache: 是否使用向量缓存
        """
        self.index_config = index_config or IndexConfig()
        self.datasource_luid = datasource_luid
        self.index_dir = Path(index_dir)
        
        # 确保索引目录存在
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始"Embedding 提供"
        # 优先使用传入"provider，否则尝试创建真实的 Embedding 提供"
        if embedding_provider is not None:
            base_provider = embedding_provider
        else:
            base_provider = self._create_default_embedding_provider()
        
        # 如果没有可用"Embedding 提供者，embedding_provider "None
        # 上层调用者应检查此属性并回退"LLM
        if base_provider is None:
            self.embedding_provider = None
            self._rag_available = False
        elif use_cache:
            self.embedding_provider = CachedEmbeddingProvider(base_provider)
            self._rag_available = True
        else:
            self.embedding_provider = base_provider
            self._rag_available = True
        
        # 字段分块存储
        self._chunks: Dict[str, FieldChunk] = {}  # field_name -> FieldChunk
        self._vectors: Dict[str, List[float]] = {}  # field_name -> vector
        self._field_names: List[str] = []  # 保持字段名顺序（对应 FAISS 索引"
        
        # FAISS 索引
        self._faiss_index: Optional[Any] = None
        
        # 元数据哈希（用于增量更新检测）
        self._metadata_hash: Optional[str] = None
    
    @property
    def rag_available(self) -> bool:
        """
        检"RAG 是否可用
        
        如果没有配置 Embedding 提供者，RAG 不可用，应回退"LLM"
        
        Returns:
            True 如果 RAG 可用，False 如果应回退"LLM
        """
        return self._rag_available
    
    def _create_default_embedding_provider(self) -> Optional[EmbeddingProvider]:
        """
        创建默认"Embedding 提供"
        
        使用 EmbeddingProviderFactory.get_default() 自动检测可用的提供者"
        
        Returns:
            EmbeddingProvider 实例，或 None（表示应回退"LLM"
        """
        return EmbeddingProviderFactory.get_default()
    
    def build_index_text(self, field_metadata: Any) -> str:
        """
        构建增强索引文本
        
        包含：fieldCaption, role, dataType, columnClass, category, formula, logicalTableCaption, sample_values
        
        Args:
            field_metadata: FieldMetadata 对象
        
        Returns:
            索引文本
        """
        parts = []
        
        # 基本信息（必需"
        parts.append(f"字段 {field_metadata.fieldCaption}")
        parts.append(f"角色: {field_metadata.role}")
        parts.append(f"类型: {field_metadata.dataType}")
        
        # 字段类型（可选）
        if hasattr(field_metadata, 'columnClass') and field_metadata.columnClass:
            parts.append(f"字段类型: {field_metadata.columnClass}")
        
        # 维度类别（可选）
        if self.index_config.include_category:
            if hasattr(field_metadata, 'category') and field_metadata.category:
                parts.append(f"类别: {field_metadata.category}")
        
        # 公式（可选）
        if self.index_config.include_formula:
            if hasattr(field_metadata, 'formula') and field_metadata.formula:
                parts.append(f"公式: {field_metadata.formula}")
        
        # 表名（可选）
        if self.index_config.include_table_caption:
            if hasattr(field_metadata, 'logicalTableCaption') and field_metadata.logicalTableCaption:
                parts.append(f"所属表: {field_metadata.logicalTableCaption}")
        
        # 样本值（可选）
        if hasattr(field_metadata, 'sample_values') and field_metadata.sample_values:
            samples = field_metadata.sample_values[:self.index_config.max_samples]
            if samples:
                parts.append(f"样本 {', '.join(str(s) for s in samples)}")
        
        return " | ".join(parts)

    def index_fields(
        self,
        fields: List[Any],
        force_rebuild: bool = False
    ) -> int:
        """
        索引字段列表
        
        Args:
            fields: FieldMetadata 列表
            force_rebuild: 是否强制重建索引
        
        Returns:
            索引的字段数量（如果 RAG 不可用返"0"
        """
        if not fields:
            return 0
        
        # 如果 RAG 不可用，只存储字段元数据（不做向量化"
        if not self._rag_available:
            logger.info("RAG 不可用，仅存储字段元数据（将回退LLM 匹配")
            self._chunks.clear()
            self._field_names.clear()
            for field in fields:
                chunk = FieldChunk.from_field_metadata(
                    field, 
                    max_samples=self.index_config.max_samples
                )
                self._chunks[chunk.field_name] = chunk
                self._field_names.append(chunk.field_name)
            return 0  # 返回 0 表示没有向量索引
        
        # 计算元数据哈"
        new_hash = self._compute_metadata_hash(fields)
        
        # 检查是否需要更"
        if not force_rebuild and self._metadata_hash == new_hash:
            logger.info("元数据未变化，跳过索引更")
            return len(self._chunks)
        
        # 检测变化的字段（增量更新）
        if not force_rebuild and self._chunks:
            changed_fields = self._detect_changed_fields(fields)
            if changed_fields:
                logger.info(f"检测到 {len(changed_fields)} 个字段变化，执行增量更新")
                return self._incremental_update(changed_fields)
        
        # 全量重建
        logger.info(f"开始索{len(fields)} 个字")
        
        # 构建分块
        chunks = []
        index_texts = []
        
        for field in fields:
            chunk = FieldChunk.from_field_metadata(
                field, 
                max_samples=self.index_config.max_samples
            )
            chunks.append(chunk)
            index_texts.append(self.build_index_text(field))
        
        # 向量"
        vectors = self.embedding_provider.embed_documents(index_texts)
        
        # 存储
        self._chunks.clear()
        self._vectors.clear()
        self._field_names.clear()
        
        for chunk, vector in zip(chunks, vectors):
            self._chunks[chunk.field_name] = chunk
            self._vectors[chunk.field_name] = vector
            self._field_names.append(chunk.field_name)
        
        # 构建 FAISS 索引
        self._build_faiss_index(vectors)
        
        self._metadata_hash = new_hash
        
        logger.info(f"索引完成: {len(self._chunks)} 个字")
        return len(self._chunks)
    
    def _compute_metadata_hash(self, fields: List[Any]) -> str:
        """计算元数据哈希"""
        # 使用字段名和关键属性计算哈"
        field_data = []
        for f in sorted(fields, key=lambda x: x.name):
            field_data.append({
                "name": f.name,
                "caption": f.fieldCaption,
                "role": f.role,
                "dataType": f.dataType,
            })
        
        content = json.dumps(field_data, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def _detect_changed_fields(self, fields: List[Any]) -> List[Any]:
        """检测变化的字段"""
        changed = []
        current_names = {f.name for f in fields}
        existing_names = set(self._chunks.keys())
        
        # 新增的字"
        new_names = current_names - existing_names
        
        # 删除的字"
        deleted_names = existing_names - current_names
        
        # 检查已存在字段是否有变"
        for field in fields:
            if field.name in existing_names:
                existing_chunk = self._chunks[field.name]
                # 简单比较：检"caption "role 是否变化
                if (existing_chunk.field_caption != field.fieldCaption or
                    existing_chunk.role != field.role):
                    changed.append(field)
            elif field.name in new_names:
                changed.append(field)
        
        # 删除已不存在的字"
        for name in deleted_names:
            del self._chunks[name]
            del self._vectors[name]
        
        return changed
    
    def _incremental_update(self, changed_fields: List[Any]) -> int:
        """增量更新索引"""
        if not changed_fields:
            return len(self._chunks)
        
        # 构建分块和索引文"
        index_texts = []
        for field in changed_fields:
            index_texts.append(self.build_index_text(field))
        
        # 向量"
        vectors = self.embedding_provider.embed_documents(index_texts)
        
        # 更新存储
        for field, vector in zip(changed_fields, vectors):
            chunk = FieldChunk.from_field_metadata(
                field,
                max_samples=self.index_config.max_samples
            )
            
            # 如果是新字段，添加到列表末尾
            if chunk.field_name not in self._chunks:
                self._field_names.append(chunk.field_name)
            
            self._chunks[chunk.field_name] = chunk
            self._vectors[chunk.field_name] = vector
        
        # 重建 FAISS 索引
        all_vectors = [self._vectors[name] for name in self._field_names]
        self._build_faiss_index(all_vectors)
        
        logger.info(f"增量更新完成: 更新 {len(changed_fields)} 个字")
        return len(self._chunks)

    def _build_faiss_index(self, vectors: List[List[float]]) -> None:
        """
        构建 FAISS 索引
        
        使用内积（Inner Product）索引配合归一化向量实现余弦相似度"
        
        Args:
            vectors: 向量列表
        """
        if not vectors or not FAISS_AVAILABLE:
            self._faiss_index = None
            return
        
        try:
            # 转换"numpy 数组
            vector_array = np.array(vectors, dtype=np.float32)
            dimension = vector_array.shape[1]
            
            # 归一化向量（用于余弦相似度）
            norms = np.linalg.norm(vector_array, axis=1, keepdims=True)
            norms[norms == 0] = 1  # 避免除零
            vector_array = vector_array / norms
            
            # 创建 FAISS 索引（使用内积，配合归一化向量等价于余弦相似度）
            self._faiss_index = faiss.IndexFlatIP(dimension)
            self._faiss_index.add(vector_array)
            
            logger.debug(f"FAISS 索引已构建（余弦相似度）: {len(vectors)} 个向 维度 {dimension}")
            
        except Exception as e:
            logger.error(f"构建 FAISS 索引失败: {e}")
            self._faiss_index = None
    
    def _faiss_search(self, query_vector: List[float], top_k: int) -> List[Tuple[str, float, float]]:
        """
        使用 FAISS 进行向量搜索
        
        使用内积索引，查询向量需要归一化以获得余弦相似度"
        归一化后的向量内积就是余弦相似度，范"[-1, 1]"
        对于正常的语义相似度，值通常"[0, 1] 范围"
        
        Args:
            query_vector: 查询向量
            top_k: 返回结果数量
        
        Returns:
            (field_name, confidence, raw_score) 列表
            - confidence: 归一化置信度 [0, 1]，使"max(0, score) 而非 (score+1)/2
            - raw_score: 原始 FAISS 内积分数，用于调"
        """
        try:
            # 转换并归一化查询向"
            query_array = np.array([query_vector], dtype=np.float32)
            norm = np.linalg.norm(query_array)
            if norm > 0:
                query_array = query_array / norm
            
            # FAISS 搜索（内积分数，归一化后等于余弦相似度）
            scores_array, indices = self._faiss_index.search(query_array, min(top_k, len(self._field_names)))
            
            scores = []
            for score, idx in zip(scores_array[0], indices[0]):
                if idx >= 0 and idx < len(self._field_names):  # 有效索引
                    field_name = self._field_names[idx]
                    # 修改: 直接使用余弦相似度，不做 (score+1)/2 转换
                    # 归一化后的向量内积就是余弦相似度，范"[-1, 1]
                    # 对于正常的语义相似度，值通常"[0, 1] 范围
                    confidence = max(0.0, min(1.0, float(score)))
                    raw_score = float(score)
                    scores.append((field_name, confidence, raw_score))
            
            return scores
            
        except Exception as e:
            logger.error(f"FAISS 搜索失败: {e}")
            return self._simple_search(query_vector)
    
    def _simple_search(self, query_vector: List[float]) -> List[Tuple[str, float, float]]:
        """
        简单向量搜索（余弦相似度）
        
        Args:
            query_vector: 查询向量
        
        Returns:
            (field_name, confidence, raw_score) 列表，按相似度降序排"
            - confidence: 归一化置信度 [0, 1]
            - raw_score: 原始余弦相似度分"
        """
        scores = []
        for field_name, field_vector in self._vectors.items():
            similarity = self._cosine_similarity(query_vector, field_vector)
            # confidence "raw_score 相同（余弦相似度本身就在 [-1, 1] 范围"
            confidence = max(0.0, min(1.0, similarity))
            scores.append((field_name, confidence, similarity))
        
        # 按相似度排序
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

    def search(
        self,
        query: str,
        top_k: int = 5,
        category_filter: Optional[str] = None,
        role_filter: Optional[str] = None
    ) -> List[RetrievalResult]:
        """
        搜索相似字段
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            category_filter: 按类别过"
            role_filter: 按角色过滤（dimension/measure"
        
        Returns:
            检索结果列表（如果 RAG 不可用返回空列表"
        """
        if not self._chunks:
            logger.warning("索引为空，请先调index_fields()")
            return []
        
        # 如果 RAG 不可用，返回空列表（由上层回退"LLM"
        if not self._rag_available:
            logger.debug("RAG 不可用，返回空结果（将回退LLM 匹配")
            return []
        
        # 向量化查"
        query_vector = self.embedding_provider.embed_query(query)
        
        # 使用 FAISS 搜索（如果可用）
        if self._faiss_index is not None and FAISS_AVAILABLE:
            scores = self._faiss_search(query_vector, top_k * 2)  # 获取更多结果用于过滤
        else:
            # 回退到简单搜"
            scores = self._simple_search(query_vector)
        
        # 应用过滤"
        # scores 格式: (field_name, confidence, raw_score)
        filtered_scores = []
        for field_name, confidence, raw_score in scores:
            chunk = self._chunks[field_name]
            
            if category_filter and chunk.category != category_filter:
                continue
            if role_filter and chunk.role != role_filter:
                continue
            
            filtered_scores.append((field_name, confidence, raw_score))
        
        # 返回 top-k
        top_scores = filtered_scores[:top_k]
        
        results = []
        for rank, (field_name, confidence, raw_score) in enumerate(top_scores, 1):
            results.append(RetrievalResult(
                field_chunk=self._chunks[field_name],
                score=confidence,  # 已经"[0, 1] 范围"
                source=RetrievalSource.EMBEDDING,
                rank=rank,
                raw_score=raw_score  # 传递原始分数用于调"
            ))
        
        return results
    
    async def asearch(
        self,
        query: str,
        top_k: int = 5,
        category_filter: Optional[str] = None,
        role_filter: Optional[str] = None
    ) -> List[RetrievalResult]:
        """
        异步搜索相似字段
        
        使用异步 embedding 进行向量化，提供更好的并发性能"
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            category_filter: 按类别过"
            role_filter: 按角色过滤（dimension/measure"
        
        Returns:
            检索结果列"
        
        **Validates: Requirements 7.4**
        """
        import asyncio
        
        if not self._chunks:
            logger.warning("索引为空，请先调index_fields()")
            return []
        
        # 异步向量化查"
        if hasattr(self.embedding_provider, 'aembed_query'):
            query_vector = await self.embedding_provider.aembed_query(query)
        else:
            # 回退到同步方"
            loop = asyncio.get_event_loop()
            query_vector = await loop.run_in_executor(
                None,
                self.embedding_provider.embed_query,
                query
            )
        
        # 使用 FAISS 搜索（如果可用）- 这部分是 CPU 密集型，在线程池中执"
        loop = asyncio.get_event_loop()
        if self._faiss_index is not None and FAISS_AVAILABLE:
            scores = await loop.run_in_executor(
                None,
                self._faiss_search,
                query_vector,
                top_k * 2  # 获取更多结果用于过滤
            )
        else:
            # 回退到简单搜"
            scores = await loop.run_in_executor(
                None,
                self._simple_search,
                query_vector
            )
        
        # 应用过滤"
        # scores 格式: (field_name, confidence, raw_score)
        filtered_scores = []
        for field_name, confidence, raw_score in scores:
            chunk = self._chunks[field_name]
            
            if category_filter and chunk.category != category_filter:
                continue
            if role_filter and chunk.role != role_filter:
                continue
            
            filtered_scores.append((field_name, confidence, raw_score))
        
        # 返回 top-k
        top_scores = filtered_scores[:top_k]
        
        results = []
        for rank, (field_name, confidence, raw_score) in enumerate(top_scores, 1):
            results.append(RetrievalResult(
                field_chunk=self._chunks[field_name],
                score=confidence,  # 已经"[0, 1] 范围"
                source=RetrievalSource.EMBEDDING,
                rank=rank,
                raw_score=raw_score  # 传递原始分数用于调"
            ))
        
        return results
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似"""
        if len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    def get_chunk(self, field_name: str) -> Optional[FieldChunk]:
        """获取字段分块"""
        return self._chunks.get(field_name)
    
    def get_all_chunks(self) -> List[FieldChunk]:
        """获取所有字段分"""
        return list(self._chunks.values())
    
    @property
    def field_count(self) -> int:
        """索引的字段数"""
        return len(self._chunks)
    
    # ========== SqliteStore 缓存方法 ==========
    
    def export_for_cache(self) -> Dict[str, Any]:
        """
        导出索引数据用于 SqliteStore 缓存
        
        Returns:
            包含 metadata_hash, field_names, chunks, vectors 的字"
        """
        chunks_data = {}
        for name, chunk in self._chunks.items():
            chunks_data[name] = {
                "field_name": chunk.field_name,
                "field_caption": chunk.field_caption,
                "role": chunk.role,
                "data_type": chunk.data_type,
                "index_text": chunk.index_text,
                "column_class": chunk.column_class,
                "category": chunk.category,
                "formula": chunk.formula,
                "logical_table_id": chunk.logical_table_id,
                "logical_table_caption": chunk.logical_table_caption,
                "sample_values": chunk.sample_values,
                "metadata": chunk.metadata,
            }
        
        return {
            "metadata_hash": self._metadata_hash,
            "field_names": self._field_names.copy(),
            "chunks": chunks_data,
            "vectors": {name: vec for name, vec in self._vectors.items()},
        }
    
    def restore_from_cache(self, cache_data: Dict[str, Any]) -> bool:
        """
        "SqliteStore 缓存恢复索引
        
        Args:
            cache_data: export_for_cache() 导出的数"
        
        Returns:
            是否恢复成功
        """
        try:
            self._metadata_hash = cache_data.get("metadata_hash")
            self._field_names = cache_data.get("field_names", [])
            self._chunks.clear()
            self._vectors.clear()
            
            for name, chunk_data in cache_data.get("chunks", {}).items():
                self._chunks[name] = FieldChunk(
                    field_name=chunk_data["field_name"],
                    field_caption=chunk_data["field_caption"],
                    role=chunk_data["role"],
                    data_type=chunk_data["data_type"],
                    index_text=chunk_data["index_text"],
                    column_class=chunk_data.get("column_class"),
                    category=chunk_data.get("category"),
                    formula=chunk_data.get("formula"),
                    logical_table_id=chunk_data.get("logical_table_id"),
                    logical_table_caption=chunk_data.get("logical_table_caption"),
                    sample_values=chunk_data.get("sample_values"),
                    metadata=chunk_data.get("metadata", {}),
                )
            
            for name, vector in cache_data.get("vectors", {}).items():
                self._vectors[name] = vector
            
            # 重建 FAISS 索引
            if self._vectors and FAISS_AVAILABLE:
                all_vectors = [self._vectors[name] for name in self._field_names if name in self._vectors]
                self._build_faiss_index(all_vectors)
            else:
                self._faiss_index = None
            
            logger.info(f"从缓存恢复索 {len(self._chunks)} 个字")
            return True
            
        except Exception as e:
            logger.error(f"从缓存恢复索引失 {e}")
            return False
    
    @property
    def metadata_hash(self) -> Optional[str]:
        """获取当前元数据哈"""
        return self._metadata_hash

    def save_index(self, filename: Optional[str] = None) -> bool:
        """
        保存索引到磁盘（FAISS + 元数据）
        
        使用 FAISS 持久化向量索引，"datasource LUID 为命名空间"
        
        Args:
            filename: 文件名前缀（默认使"datasource_luid"
        
        Returns:
            是否保存成功
        """
        if not self._chunks:
            logger.warning("索引为空，无需保存")
            return False
        
        if filename is None:
            if self.datasource_luid:
                filename = self.datasource_luid
            else:
                filename = "default_index"
        
        try:
            # 保存元数据（JSON"
            metadata_path = self.index_dir / f"{filename}_metadata.json"
            data = {
                "metadata_hash": self._metadata_hash,
                "field_names": self._field_names,
                "chunks": {},
                "vectors": {}  # 保留向量用于回退
            }
            
            for name, chunk in self._chunks.items():
                data["chunks"][name] = {
                    "field_name": chunk.field_name,
                    "field_caption": chunk.field_caption,
                    "role": chunk.role,
                    "data_type": chunk.data_type,
                    "index_text": chunk.index_text,
                    "column_class": chunk.column_class,
                    "category": chunk.category,
                    "formula": chunk.formula,
                    "logical_table_id": chunk.logical_table_id,
                    "logical_table_caption": chunk.logical_table_caption,
                    "sample_values": chunk.sample_values,
                    "metadata": chunk.metadata,
                }
            
            # 保存向量（用于回退"
            for name, vector in self._vectors.items():
                data["vectors"][name] = vector
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 保存 FAISS 索引
            if self._faiss_index is not None and FAISS_AVAILABLE:
                faiss_path = self.index_dir / f"{filename}_faiss.index"
                faiss.write_index(self._faiss_index, str(faiss_path))
                logger.info(f"FAISS 索引已保 {faiss_path}")
            
            logger.info(f"索引已保 {metadata_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存索引失败: {e}")
            return False
    
    def load_index(self, filename: Optional[str] = None) -> bool:
        """
        从磁盘加载索引（FAISS + 元数据）
        
        Args:
            filename: 文件名前缀（默认使"datasource_luid"
        
        Returns:
            是否加载成功
        """
        if filename is None:
            if self.datasource_luid:
                filename = self.datasource_luid
            else:
                filename = "default_index"
        
        metadata_path = self.index_dir / f"{filename}_metadata.json"
        
        if not metadata_path.exists():
            logger.info(f"索引文件不存 {metadata_path}")
            return False
        
        try:
            # 加载元数"
            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._metadata_hash = data.get("metadata_hash")
            self._field_names = data.get("field_names", [])
            self._chunks.clear()
            self._vectors.clear()
            
            for name, chunk_data in data.get("chunks", {}).items():
                self._chunks[name] = FieldChunk(
                    field_name=chunk_data["field_name"],
                    field_caption=chunk_data["field_caption"],
                    role=chunk_data["role"],
                    data_type=chunk_data["data_type"],
                    index_text=chunk_data["index_text"],
                    column_class=chunk_data.get("column_class"),
                    category=chunk_data.get("category"),
                    formula=chunk_data.get("formula"),
                    logical_table_id=chunk_data.get("logical_table_id"),
                    logical_table_caption=chunk_data.get("logical_table_caption"),
                    sample_values=chunk_data.get("sample_values"),
                    metadata=chunk_data.get("metadata", {}),
                )
            
            for name, vector in data.get("vectors", {}).items():
                self._vectors[name] = vector
            
            # 加载 FAISS 索引
            faiss_path = self.index_dir / f"{filename}_faiss.index"
            if faiss_path.exists() and FAISS_AVAILABLE:
                try:
                    self._faiss_index = faiss.read_index(str(faiss_path))
                    logger.info(f"FAISS 索引已加 {faiss_path}")
                except Exception as e:
                    logger.warning(f"加载 FAISS 索引失败，将使用简单搜 {e}")
                    self._faiss_index = None
            else:
                # 如果没有 FAISS 索引文件，从向量重建
                if self._vectors and FAISS_AVAILABLE:
                    all_vectors = [self._vectors[name] for name in self._field_names if name in self._vectors]
                    self._build_faiss_index(all_vectors)
                else:
                    self._faiss_index = None
            
            logger.info(f"索引已加 {metadata_path}, {len(self._chunks)} 个字")
            return True
            
        except Exception as e:
            logger.error(f"加载索引失败: {e}")
            return False


__all__ = [
    "IndexConfig",
    "FieldIndexer",
]
