"""
字段索引器

参考 DB-GPT 的 DBSchemaAssembler 实现模式，提供字段索引能力。

主要功能：
- 构建增强索引文本
- 支持元数据过滤
- 支持增量更新
- 支持索引持久化（FAISS）
"""
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, Tuple
from dataclasses import dataclass, field

try:
    import faiss
    import numpy as np
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logging.warning("FAISS 未安装，将使用简单向量搜索。安装命令: pip install faiss-cpu")

from tableau_assistant.src.capabilities.rag.models import FieldChunk, RetrievalResult, RetrievalSource
from tableau_assistant.src.capabilities.rag.embeddings import EmbeddingProvider, EmbeddingProviderFactory
from tableau_assistant.src.capabilities.rag.cache import VectorCache, CachedEmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass
class IndexConfig:
    """
    索引配置
    
    Attributes:
        max_samples: 最大样本值数量
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
    字段索引器
    
    构建和管理字段的向量索引，支持语义检索。
    参考 DB-GPT 的 DBSchemaAssembler 实现模式。
    
    Attributes:
        embedding_provider: Embedding 提供者
        index_config: 索引配置
        datasource_luid: 数据源 LUID（命名空间）
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
            embedding_provider: Embedding 提供者（默认使用 Mock）
            index_config: 索引配置
            datasource_luid: 数据源 LUID
            index_dir: 索引存储目录
            use_cache: 是否使用向量缓存
        """
        self.index_config = index_config or IndexConfig()
        self.datasource_luid = datasource_luid
        self.index_dir = Path(index_dir)
        
        # 确保索引目录存在
        self.index_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化 Embedding 提供者
        # 优先使用传入的 provider，否则尝试创建真实的 Embedding 提供者
        if embedding_provider is not None:
            base_provider = embedding_provider
        else:
            base_provider = self._create_default_embedding_provider()
        
        # 如果没有可用的 Embedding 提供者，embedding_provider 为 None
        # 上层调用者应检查此属性并回退到 LLM
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
        self._field_names: List[str] = []  # 保持字段名顺序（对应 FAISS 索引）
        
        # FAISS 索引
        self._faiss_index: Optional[Any] = None
        
        # 元数据哈希（用于增量更新检测）
        self._metadata_hash: Optional[str] = None
    
    @property
    def rag_available(self) -> bool:
        """
        检查 RAG 是否可用
        
        如果没有配置 Embedding 提供者，RAG 不可用，应回退到 LLM。
        
        Returns:
            True 如果 RAG 可用，False 如果应回退到 LLM
        """
        return self._rag_available
    
    def _create_default_embedding_provider(self) -> Optional[EmbeddingProvider]:
        """
        创建默认的 Embedding 提供者
        
        根据环境变量自动检测可用的 Embedding 提供者：
        1. 检测 ZHIPUAI_API_KEY / ZHIPU_API_KEY - 使用智谱 AI
        2. 检测 OPENAI_API_KEY - 使用 OpenAI
        3. 如果没有配置任何 Embedding API Key，返回 None（由上层回退到 LLM）
        
        Returns:
            EmbeddingProvider 实例，或 None（表示应回退到 LLM）
        """
        import os
        
        # 1. 尝试智谱 AI（如果配置了专用 API Key）
        zhipu_key = os.environ.get("ZHIPUAI_API_KEY") or os.environ.get("ZHIPU_API_KEY")
        if zhipu_key:
            try:
                provider = EmbeddingProviderFactory.create("zhipu")
                logger.info("使用智谱 AI Embedding 提供者")
                return provider
            except Exception as e:
                logger.warning(f"初始化智谱 AI Embedding 失败: {e}")
        
        # 2. 尝试 OpenAI（如果配置了专用 API Key）
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                provider = EmbeddingProviderFactory.create("openai")
                logger.info("使用 OpenAI Embedding 提供者")
                return provider
            except Exception as e:
                logger.warning(f"初始化 OpenAI Embedding 失败: {e}")
        
        # 3. 没有配置 Embedding API Key，返回 None（由上层回退到 LLM）
        logger.warning(
            "未配置 Embedding API Key (ZHIPUAI_API_KEY 或 OPENAI_API_KEY)，"
            "字段映射将回退到 LLM 直接匹配"
        )
        return None
    
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
        
        # 基本信息（必需）
        parts.append(f"字段名: {field_metadata.fieldCaption}")
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
                parts.append(f"样本值: {', '.join(str(s) for s in samples)}")
        
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
            索引的字段数量（如果 RAG 不可用返回 0）
        """
        if not fields:
            return 0
        
        # 如果 RAG 不可用，只存储字段元数据（不做向量化）
        if not self._rag_available:
            logger.info("RAG 不可用，仅存储字段元数据（将回退到 LLM 匹配）")
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
        
        # 计算元数据哈希
        new_hash = self._compute_metadata_hash(fields)
        
        # 检查是否需要更新
        if not force_rebuild and self._metadata_hash == new_hash:
            logger.info("元数据未变化，跳过索引更新")
            return len(self._chunks)
        
        # 检测变化的字段（增量更新）
        if not force_rebuild and self._chunks:
            changed_fields = self._detect_changed_fields(fields)
            if changed_fields:
                logger.info(f"检测到 {len(changed_fields)} 个字段变化，执行增量更新")
                return self._incremental_update(changed_fields)
        
        # 全量重建
        logger.info(f"开始索引 {len(fields)} 个字段")
        
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
        
        # 向量化
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
        
        logger.info(f"索引完成: {len(self._chunks)} 个字段")
        return len(self._chunks)
    
    def _compute_metadata_hash(self, fields: List[Any]) -> str:
        """计算元数据哈希值"""
        # 使用字段名和关键属性计算哈希
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
        
        # 新增的字段
        new_names = current_names - existing_names
        
        # 删除的字段
        deleted_names = existing_names - current_names
        
        # 检查已存在字段是否有变化
        for field in fields:
            if field.name in existing_names:
                existing_chunk = self._chunks[field.name]
                # 简单比较：检查 caption 和 role 是否变化
                if (existing_chunk.field_caption != field.fieldCaption or
                    existing_chunk.role != field.role):
                    changed.append(field)
            elif field.name in new_names:
                changed.append(field)
        
        # 删除已不存在的字段
        for name in deleted_names:
            del self._chunks[name]
            del self._vectors[name]
        
        return changed
    
    def _incremental_update(self, changed_fields: List[Any]) -> int:
        """增量更新索引"""
        if not changed_fields:
            return len(self._chunks)
        
        # 构建分块和索引文本
        index_texts = []
        for field in changed_fields:
            index_texts.append(self.build_index_text(field))
        
        # 向量化
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
        
        logger.info(f"增量更新完成: 更新 {len(changed_fields)} 个字段")
        return len(self._chunks)
    
    def _build_faiss_index(self, vectors: List[List[float]]) -> None:
        """
        构建 FAISS 索引
        
        使用内积（Inner Product）索引配合归一化向量实现余弦相似度。
        
        Args:
            vectors: 向量列表
        """
        if not vectors or not FAISS_AVAILABLE:
            self._faiss_index = None
            return
        
        try:
            # 转换为 numpy 数组
            vector_array = np.array(vectors, dtype=np.float32)
            dimension = vector_array.shape[1]
            
            # 归一化向量（用于余弦相似度）
            norms = np.linalg.norm(vector_array, axis=1, keepdims=True)
            norms[norms == 0] = 1  # 避免除零
            vector_array = vector_array / norms
            
            # 创建 FAISS 索引（使用内积，配合归一化向量等价于余弦相似度）
            self._faiss_index = faiss.IndexFlatIP(dimension)
            self._faiss_index.add(vector_array)
            
            logger.debug(f"FAISS 索引已构建（余弦相似度）: {len(vectors)} 个向量, 维度 {dimension}")
            
        except Exception as e:
            logger.error(f"构建 FAISS 索引失败: {e}")
            self._faiss_index = None
    
    def _faiss_search(self, query_vector: List[float], top_k: int) -> List[Tuple[str, float]]:
        """
        使用 FAISS 进行向量搜索
        
        使用内积索引，查询向量需要归一化以获得余弦相似度。
        
        Args:
            query_vector: 查询向量
            top_k: 返回结果数量
        
        Returns:
            (field_name, similarity) 列表，相似度范围 [0, 1]
        """
        try:
            # 转换并归一化查询向量
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
                    # 内积分数范围 [-1, 1]，转换为 [0, 1]
                    similarity = (score + 1.0) / 2.0
                    scores.append((field_name, similarity))
            
            return scores
            
        except Exception as e:
            logger.error(f"FAISS 搜索失败: {e}")
            return self._simple_search(query_vector)
    
    def _simple_search(self, query_vector: List[float]) -> List[Tuple[str, float]]:
        """
        简单向量搜索（余弦相似度）
        
        Args:
            query_vector: 查询向量
        
        Returns:
            (field_name, similarity) 列表，按相似度降序排列
        """
        scores = []
        for field_name, field_vector in self._vectors.items():
            similarity = self._cosine_similarity(query_vector, field_vector)
            scores.append((field_name, similarity))
        
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
            category_filter: 按类别过滤
            role_filter: 按角色过滤（dimension/measure）
        
        Returns:
            检索结果列表（如果 RAG 不可用返回空列表）
        """
        if not self._chunks:
            logger.warning("索引为空，请先调用 index_fields()")
            return []
        
        # 如果 RAG 不可用，返回空列表（由上层回退到 LLM）
        if not self._rag_available:
            logger.debug("RAG 不可用，返回空结果（将回退到 LLM 匹配）")
            return []
        
        # 向量化查询
        query_vector = self.embedding_provider.embed_query(query)
        
        # 使用 FAISS 搜索（如果可用）
        if self._faiss_index is not None and FAISS_AVAILABLE:
            scores = self._faiss_search(query_vector, top_k * 2)  # 获取更多结果用于过滤
        else:
            # 回退到简单搜索
            scores = self._simple_search(query_vector)
        
        # 应用过滤器
        filtered_scores = []
        for field_name, similarity in scores:
            chunk = self._chunks[field_name]
            
            if category_filter and chunk.category != category_filter:
                continue
            if role_filter and chunk.role != role_filter:
                continue
            
            filtered_scores.append((field_name, similarity))
        
        # 返回 top-k
        top_scores = filtered_scores[:top_k]
        
        results = []
        for rank, (field_name, score) in enumerate(top_scores, 1):
            results.append(RetrievalResult(
                field_chunk=self._chunks[field_name],
                score=max(0.0, min(1.0, score)),  # 确保分数在 0-1 之间
                source=RetrievalSource.EMBEDDING,
                rank=rank
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
        
        使用异步 embedding 进行向量化，提供更好的并发性能。
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            category_filter: 按类别过滤
            role_filter: 按角色过滤（dimension/measure）
        
        Returns:
            检索结果列表
        
        **Validates: Requirements 7.4**
        """
        import asyncio
        
        if not self._chunks:
            logger.warning("索引为空，请先调用 index_fields()")
            return []
        
        # 异步向量化查询
        if hasattr(self.embedding_provider, 'aembed_query'):
            query_vector = await self.embedding_provider.aembed_query(query)
        else:
            # 回退到同步方法
            loop = asyncio.get_event_loop()
            query_vector = await loop.run_in_executor(
                None,
                self.embedding_provider.embed_query,
                query
            )
        
        # 使用 FAISS 搜索（如果可用）- 这部分是 CPU 密集型，在线程池中执行
        loop = asyncio.get_event_loop()
        if self._faiss_index is not None and FAISS_AVAILABLE:
            scores = await loop.run_in_executor(
                None,
                self._faiss_search,
                query_vector,
                top_k * 2  # 获取更多结果用于过滤
            )
        else:
            # 回退到简单搜索
            scores = await loop.run_in_executor(
                None,
                self._simple_search,
                query_vector
            )
        
        # 应用过滤器
        filtered_scores = []
        for field_name, similarity in scores:
            chunk = self._chunks[field_name]
            
            if category_filter and chunk.category != category_filter:
                continue
            if role_filter and chunk.role != role_filter:
                continue
            
            filtered_scores.append((field_name, similarity))
        
        # 返回 top-k
        top_scores = filtered_scores[:top_k]
        
        results = []
        for rank, (field_name, score) in enumerate(top_scores, 1):
            results.append(RetrievalResult(
                field_chunk=self._chunks[field_name],
                score=max(0.0, min(1.0, score)),  # 确保分数在 0-1 之间
                source=RetrievalSource.EMBEDDING,
                rank=rank
            ))
        
        return results
    
    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
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
        """获取所有字段分块"""
        return list(self._chunks.values())
    
    @property
    def field_count(self) -> int:
        """索引的字段数量"""
        return len(self._chunks)
    
    def save_index(self, filename: Optional[str] = None) -> bool:
        """
        保存索引到磁盘（FAISS + 元数据）
        
        使用 FAISS 持久化向量索引，以 datasource LUID 为命名空间。
        
        Args:
            filename: 文件名前缀（默认使用 datasource_luid）
        
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
            # 保存元数据（JSON）
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
            
            # 保存向量（用于回退）
            for name, vector in self._vectors.items():
                data["vectors"][name] = vector
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 保存 FAISS 索引
            if self._faiss_index is not None and FAISS_AVAILABLE:
                faiss_path = self.index_dir / f"{filename}_faiss.index"
                faiss.write_index(self._faiss_index, str(faiss_path))
                logger.info(f"FAISS 索引已保存: {faiss_path}")
            
            logger.info(f"索引已保存: {metadata_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存索引失败: {e}")
            return False
    
    def load_index(self, filename: Optional[str] = None) -> bool:
        """
        从磁盘加载索引（FAISS + 元数据）
        
        Args:
            filename: 文件名前缀（默认使用 datasource_luid）
        
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
            logger.info(f"索引文件不存在: {metadata_path}")
            return False
        
        try:
            # 加载元数据
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
                    logger.info(f"FAISS 索引已加载: {faiss_path}")
                except Exception as e:
                    logger.warning(f"加载 FAISS 索引失败，将使用简单搜索: {e}")
                    self._faiss_index = None
            else:
                # 如果没有 FAISS 索引文件，从向量重建
                if self._vectors and FAISS_AVAILABLE:
                    all_vectors = [self._vectors[name] for name in self._field_names if name in self._vectors]
                    self._build_faiss_index(all_vectors)
                else:
                    self._faiss_index = None
            
            logger.info(f"索引已加载: {metadata_path}, {len(self._chunks)} 个字段")
            return True
            
        except Exception as e:
            logger.error(f"加载索引失败: {e}")
            return False


__all__ = [
    "IndexConfig",
    "FieldIndexer",
]
