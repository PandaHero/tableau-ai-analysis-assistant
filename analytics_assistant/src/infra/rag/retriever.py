"""
检索器

使用 langgraph_store 进行向量检索。
支持：
- ExactRetriever（精确匹配，O(1)）
- BM25Retriever（BM25 关键词检索，使用 jieba 分词）
- EmbeddingRetriever（向量检索）
- CascadeRetriever（级联检索：精确匹配 → 向量检索）
- HybridRetriever（混合检索：BM25 + Embedding + RRF 融合）
- RetrievalPipeline（检索管道）
- RetrieverFactory（检索器工厂）

检索策略：
- cascade: 精确匹配 → Embedding 检索
- hybrid: BM25 + Embedding → RRF 融合
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import jieba
from langchain_community.retrievers import BM25Retriever as LangChainBM25Retriever
from langchain_core.documents import Document

from ..storage.vector_store import get_vector_store
from ..ai import get_embeddings, get_model_manager
from ..config import get_config
from .models import FieldChunk, RetrievalResult, RetrievalSource
from .reranker import DefaultReranker, RRFReranker, LLMReranker

logger = logging.getLogger(__name__)

@dataclass
class RetrievalConfig:
    """检索配置"""
    top_k: int = 10
    score_threshold: float = 0.0
    use_reranker: bool = False

@dataclass
class MetadataFilter:
    """元数据过滤器"""
    role: Optional[str] = None
    data_type: Optional[str] = None
    category: Optional[str] = None
    
    def matches(self, chunk: FieldChunk) -> bool:
        if self.role and chunk.role != self.role:
            return False
        if self.data_type and chunk.data_type != self.data_type:
            return False
        if self.category and chunk.category != self.category:
            return False
        return True
    
    def to_dict(self) -> dict[str, str]:
        d = {}
        if self.role:
            d["role"] = self.role
        if self.data_type:
            d["data_type"] = self.data_type
        if self.category:
            d["category"] = self.category
        return d

class BaseRetriever(ABC):
    """检索器抽象基类"""
    
    def __init__(self, config: Optional[RetrievalConfig] = None):
        self.config = config or RetrievalConfig()
    
    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
        score_threshold: float = 0.0
    ) -> list[RetrievalResult]:
        pass
    
    async def aretrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
        score_threshold: float = 0.0
    ) -> list[RetrievalResult]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.retrieve(query, top_k, filters, score_threshold)
        )
    
    def _apply_filters(
        self,
        results: list[RetrievalResult],
        filters: Optional[MetadataFilter],
        score_threshold: float
    ) -> list[RetrievalResult]:
        filtered = []
        for result in results:
            if result.score < score_threshold:
                continue
            if filters and not filters.matches(result.field_chunk):
                continue
            filtered.append(result)
        return filtered

class ExactRetriever(BaseRetriever):
    """精确匹配检索器 - O(1) 哈希查找"""
    
    def __init__(
        self,
        chunks: dict[str, FieldChunk],
        config: Optional[RetrievalConfig] = None,
        case_sensitive: bool = False,
        match_caption_first: bool = True
    ):
        super().__init__(config)
        self._chunks = chunks
        self.case_sensitive = case_sensitive
        self.match_caption_first = match_caption_first
        self._name_index: dict[str, FieldChunk] = {}
        self._caption_index: dict[str, FieldChunk] = {}
        self._build_index()
    
    def _build_index(self) -> None:
        for chunk in self._chunks.values():
            name_key = chunk.field_name if self.case_sensitive else chunk.field_name.lower()
            caption_key = chunk.field_caption if self.case_sensitive else chunk.field_caption.lower()
            self._name_index[name_key] = chunk
            if caption_key:
                self._caption_index[caption_key] = chunk
    
    def retrieve(
        self,
        query: str,
        top_k: int = 1,
        filters: Optional[MetadataFilter] = None,
        score_threshold: float = 0.0
    ) -> list[RetrievalResult]:
        if not query:
            return []
        
        query_key = query if self.case_sensitive else query.lower()
        chunk = None
        
        if self.match_caption_first:
            chunk = self._caption_index.get(query_key) or self._name_index.get(query_key)
        else:
            chunk = self._name_index.get(query_key) or self._caption_index.get(query_key)
        
        if chunk is None:
            return []
        
        if filters and not filters.matches(chunk):
            return []
        
        return [RetrievalResult(
            field_chunk=chunk,
            score=1.0,
            source=RetrievalSource.EXACT,
            rank=1,
            raw_score=1.0,
            original_term=query,
        )]
    
    def get_chunk(self, field_name: str) -> Optional[FieldChunk]:
        return self._chunks.get(field_name)

class EmbeddingRetriever(BaseRetriever):
    """向量检索器"""
    
    def __init__(
        self,
        vector_store,
        chunks: dict[str, FieldChunk],
        config: Optional[RetrievalConfig] = None
    ):
        super().__init__(config)
        self._store = vector_store
        self._chunks = chunks
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> list[RetrievalResult]:
        if not query or not query.strip() or not self._store:
            return []
        
        k = top_k if top_k is not None else self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold
        search_k = k * 2 if filters else k
        filter_dict = filters.to_dict() if filters else None
        
        try:
            if filter_dict:
                docs_and_scores = self._store.similarity_search_with_score(query, k=search_k, filter=filter_dict)
            else:
                docs_and_scores = self._store.similarity_search_with_score(query, k=search_k)
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []
        
        results = []
        for rank, (doc, score) in enumerate(docs_and_scores, 1):
            field_name = doc.metadata.get("field_name")
            if field_name and field_name in self._chunks:
                similarity = 1.0 / (1.0 + score)
                results.append(RetrievalResult(
                    field_chunk=self._chunks[field_name],
                    score=similarity,
                    source=RetrievalSource.EMBEDDING,
                    rank=rank,
                    raw_score=score
                ))
        
        filtered = self._apply_filters(results, filters, threshold)
        return filtered[:k]
    
    def get_chunk(self, field_name: str) -> Optional[FieldChunk]:
        return self._chunks.get(field_name)
    
    def get_all_chunks(self) -> list[FieldChunk]:
        return list(self._chunks.values())

class BM25Retriever(BaseRetriever):
    """BM25 关键词检索器
    
    基于 LangChain 的 BM25Retriever，使用 jieba 分词。
    适用于中文文本的关键词匹配场景。
    """
    
    def __init__(
        self,
        chunks: dict[str, FieldChunk],
        config: Optional[RetrievalConfig] = None,
        preprocess_func: Optional[Callable[[str], list[str]]] = None,
    ):
        """初始化 BM25 检索器
        
        Args:
            chunks: 字段分块字典 {field_name: FieldChunk}
            config: 检索配置
            preprocess_func: 分词函数，默认使用 jieba.lcut
        """
        super().__init__(config)
        self._chunks = chunks
        self._preprocess_func = preprocess_func or jieba.lcut
        
        # LangChain BM25 检索器
        self._lc_bm25: Optional[LangChainBM25Retriever] = None
        self._build_index()
    
    def _build_index(self) -> None:
        """构建 BM25 索引"""
        if not self._chunks:
            logger.warning("BM25Retriever: 没有文档可索引")
            return
        
        # 将 FieldChunk 转换为 LangChain Document
        documents = []
        for field_name, chunk in self._chunks.items():
            doc = Document(
                page_content=chunk.index_text,
                metadata={
                    "field_name": field_name,
                    "field_caption": chunk.field_caption,
                    "role": chunk.role,
                    "data_type": chunk.data_type,
                    "category": chunk.category or "",
                }
            )
            documents.append(doc)
        
        # 创建 LangChain BM25 检索器
        self._lc_bm25 = LangChainBM25Retriever.from_documents(
            documents,
            preprocess_func=self._preprocess_func,
        )
        # 设置默认 k 值
        self._lc_bm25.k = self.config.top_k
        
        logger.info(f"BM25Retriever: 索引构建完成，共 {len(documents)} 个文档")
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> list[RetrievalResult]:
        """BM25 检索
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤条件
            score_threshold: 分数阈值（BM25 不支持，忽略）
            
        Returns:
            检索结果列表
        """
        if not query or not query.strip() or self._lc_bm25 is None:
            return []
        
        k = top_k if top_k is not None else self.config.top_k
        
        # 设置检索数量（多取一些用于过滤）
        search_k = k * 2 if filters else k
        self._lc_bm25.k = search_k
        
        # 使用 LangChain BM25 检索
        docs = self._lc_bm25.invoke(query)
        
        # 转换为 RetrievalResult
        results = []
        for rank, doc in enumerate(docs, 1):
            field_name = doc.metadata.get("field_name")
            if field_name and field_name in self._chunks:
                chunk = self._chunks[field_name]
                
                # BM25 不返回分数，使用排名计算伪分数
                # 排名越靠前，分数越高
                pseudo_score = 1.0 / rank
                
                results.append(RetrievalResult(
                    field_chunk=chunk,
                    score=pseudo_score,
                    source=RetrievalSource.BM25,
                    rank=rank,
                    raw_score=pseudo_score,  # BM25 没有原始分数
                    original_term=query,
                ))
        
        # 应用过滤器
        filtered = self._apply_filters(results, filters, 0.0)
        return filtered[:k]
    
    def get_chunk(self, field_name: str) -> Optional[FieldChunk]:
        return self._chunks.get(field_name)
    
    def get_all_chunks(self) -> list[FieldChunk]:
        return list(self._chunks.values())

class CascadeRetriever(BaseRetriever):
    """
    级联检索器
    
    检索策略：精确匹配 → 向量检索
    如果精确匹配成功，直接返回；否则使用向量检索。
    
    可选：包含 BM25 检索器用于混合检索场景。
    """
    
    def __init__(
        self,
        exact_retriever: ExactRetriever,
        embedding_retriever: EmbeddingRetriever,
        config: Optional[RetrievalConfig] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
    ):
        super().__init__(config)
        self._exact = exact_retriever
        self._embedding = embedding_retriever
        self._bm25 = bm25_retriever  # 可选，用于混合检索
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> list[RetrievalResult]:
        if not query:
            return []
        
        k = top_k if top_k is not None else self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold
        
        # 1. 先尝试精确匹配
        exact_results = self._exact.retrieve(query, top_k=1, filters=filters)
        if exact_results:
            logger.debug(f"精确匹配成功: {query} -> {exact_results[0].field_chunk.field_name}")
            return exact_results
        
        # 2. 回退到向量检索
        embedding_results = self._embedding.retrieve(query, top_k=k, filters=filters, score_threshold=threshold)
        
        # 更新来源为 CASCADE
        for result in embedding_results:
            result.source = RetrievalSource.CASCADE
        
        return embedding_results
    
    async def aretrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> list[RetrievalResult]:
        if not query:
            return []
        
        k = top_k if top_k is not None else self.config.top_k
        threshold = score_threshold if score_threshold is not None else self.config.score_threshold
        
        # 精确匹配是 O(1)，无需异步
        exact_results = self._exact.retrieve(query, top_k=1, filters=filters)
        if exact_results:
            return exact_results
        
        # 向量检索
        embedding_results = await self._embedding.aretrieve(query, top_k=k, filters=filters, score_threshold=threshold)
        for result in embedding_results:
            result.source = RetrievalSource.CASCADE
        
        return embedding_results

class RetrievalPipeline:
    """检索管道：检索器 + 重排序器"""
    
    def __init__(self, retriever: BaseRetriever, reranker: Optional[Any] = None):
        self.retriever = retriever
        self.reranker = reranker
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
        score_threshold: float = 0.0,
        rerank_top_k: Optional[int] = None
    ) -> list[RetrievalResult]:
        if self.reranker is not None:
            candidate_k = rerank_top_k or top_k * 3
            candidates = self.retriever.retrieve(query, top_k=candidate_k, filters=filters, score_threshold=score_threshold)
            return self.reranker.rerank(query, candidates, top_k)
        else:
            return self.retriever.retrieve(query, top_k=top_k, filters=filters, score_threshold=score_threshold)
    
    async def asearch(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
        score_threshold: float = 0.0,
        rerank_top_k: Optional[int] = None
    ) -> list[RetrievalResult]:
        if self.reranker is not None:
            candidate_k = rerank_top_k or top_k * 3
            candidates = await self.retriever.aretrieve(query, top_k=candidate_k, filters=filters, score_threshold=score_threshold)
            return await self.reranker.arerank(query, candidates, top_k)
        else:
            return await self.retriever.aretrieve(query, top_k=top_k, filters=filters, score_threshold=score_threshold)
    
    def batch_search(
        self,
        queries: list[str],
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None
    ) -> dict[str, list[RetrievalResult]]:
        return {query: self.search(query, top_k, filters) for query in queries}

def _build_chunks_and_metadata(fields: list[Any]) -> tuple:
    """从字段列表构建 chunks 和 metadata
    
    注意：
    1. role 和 data_type 统一转为小写，确保检索时 filters 匹配
    2. 如果传入的 field_data 已包含 index_text，优先使用它（支持增强索引文本）
    """
    chunks: dict[str, FieldChunk] = {}
    texts = []
    metadatas = []
    
    for field_data in fields:
        # 检查是否已有预构建的 index_text（来自 IndexDocument）
        # 这支持使用增强的索引文本格式（包含别名、业务描述等）
        if isinstance(field_data, dict) and field_data.get("index_text"):
            # 直接使用传入的 index_text，不重新生成
            field_name = field_data.get("field_name", "")
            field_caption = field_data.get("field_caption", field_name)
            role_lower = (field_data.get("role") or "dimension").lower()
            data_type_lower = (field_data.get("data_type") or "string").lower()
            
            chunk = FieldChunk(
                field_name=field_name,
                field_caption=field_caption,
                role=role_lower,
                data_type=data_type_lower,
                index_text=field_data["index_text"],  # 使用预构建的增强索引文本
                category=field_data.get("category"),
                formula=field_data.get("formula"),
                logical_table_id=field_data.get("logical_table_id"),
                logical_table_caption=field_data.get("logical_table_caption"),
                metadata={
                    k: v for k, v in field_data.items()
                    if k not in {"field_name", "field_caption", "role", "data_type", 
                                "index_text", "category", "formula", 
                                "logical_table_id", "logical_table_caption"}
                },
            )
        else:
            # 旧逻辑：从 field_metadata 生成（兼容旧代码）
            chunk = FieldChunk.from_field_metadata(field_data)
            
            # 统一转为小写，确保检索时 filters 匹配
            role_lower = chunk.role.lower() if chunk.role else 'dimension'
            data_type_lower = chunk.data_type.lower() if chunk.data_type else 'string'
            
            # 更新 chunk 的 role 和 data_type 为小写
            chunk.role = role_lower
            chunk.data_type = data_type_lower
        
        chunks[chunk.field_name] = chunk
        texts.append(chunk.index_text)
        metadatas.append({
            "field_name": chunk.field_name,
            "field_caption": chunk.field_caption,
            "role": chunk.role,
            "data_type": chunk.data_type,
            "category": (chunk.category or "").lower() if chunk.category else "",
            "column_class": chunk.column_class or "",
            "formula": chunk.formula or "",
            "logical_table_id": chunk.logical_table_id or "",
            "logical_table_caption": chunk.logical_table_caption or "",
            **chunk.metadata
        })
    
    return chunks, texts, metadatas

class RetrieverFactory:
    """检索器工厂"""
    
    @staticmethod
    def _index_exists(collection_name: str, persist_directory: Optional[str] = None) -> bool:
        """检查索引是否已存在"""
        if not persist_directory:
            app_config = get_config()
            vector_config = app_config.config.get("vector_storage", {})
            persist_directory = vector_config.get("index_dir", "data/indexes")
        
        index_path = Path(persist_directory) / collection_name
        return index_path.exists()
    
    @staticmethod
    def create_exact_retriever(
        fields: list[Any],
        config: Optional[RetrievalConfig] = None
    ) -> ExactRetriever:
        """创建精确匹配检索器"""
        chunks, _, _ = _build_chunks_and_metadata(fields)
        return ExactRetriever(chunks, config)
    
    @staticmethod
    def create_embedding_retriever(
        fields: list[Any],
        config: Optional[RetrievalConfig] = None,
        collection_name: str = "fields",
        persist_directory: Optional[str] = None,
        embedding_model_id: Optional[str] = None,
        force_rebuild: bool = False,
        use_batch_embedding: bool = True,
    ) -> EmbeddingRetriever:
        """创建向量检索器
        
        Args:
            fields: 字段元数据列表
            config: 检索配置
            collection_name: 集合名称（用于索引文件名）
            persist_directory: 持久化目录
            embedding_model_id: Embedding 模型 ID
            force_rebuild: 强制重建索引（忽略已有索引）
            use_batch_embedding: 是否使用批量 embedding（默认 True，首次创建时更快）
        """
        chunks, texts, metadatas = _build_chunks_and_metadata(fields)
        
        app_config = get_config()
        vector_config = app_config.config.get("vector_storage", {})
        backend = vector_config.get("backend", "faiss")
        index_dir = persist_directory or vector_config.get("index_dir", "data/indexes")
        
        embeddings = get_embeddings(model_id=embedding_model_id)
        
        # 检查索引是否已存在，如果存在且不强制重建，则复用
        if not force_rebuild and RetrieverFactory._index_exists(collection_name, index_dir):
            logger.info(f"复用已有索引: {collection_name}")
            vector_store = get_vector_store(
                backend=backend,
                embeddings=embeddings,
                collection_name=collection_name,
                persist_directory=index_dir,
                texts=None,  # 不传 texts，触发加载已有索引
                metadatas=None,
            )
        else:
            vector_store = get_vector_store(
                backend=backend,
                embeddings=embeddings,
                collection_name=collection_name,
                persist_directory=index_dir,
                texts=texts,
                metadatas=metadatas,
                use_batch_embedding=use_batch_embedding,
            )
        
        return EmbeddingRetriever(vector_store, chunks, config)
    
    @staticmethod
    def create_cascade_retriever(
        fields: list[Any],
        config: Optional[RetrievalConfig] = None,
        collection_name: str = "fields",
        persist_directory: Optional[str] = None,
        embedding_model_id: Optional[str] = None,
        force_rebuild: bool = False,
        include_bm25: bool = True,
        use_batch_embedding: bool = True,
    ) -> CascadeRetriever:
        """创建级联检索器（精确匹配 → 向量检索）
        
        Args:
            fields: 字段元数据列表
            config: 检索配置
            collection_name: 集合名称（用于索引文件名）
            persist_directory: 持久化目录
            embedding_model_id: Embedding 模型 ID
            force_rebuild: 强制重建索引（忽略已有索引）
            include_bm25: 是否包含 BM25 检索器（用于混合检索）
            use_batch_embedding: 是否使用批量 embedding（默认 True，首次创建时更快）
        """
        chunks, texts, metadatas = _build_chunks_and_metadata(fields)
        
        app_config = get_config()
        vector_config = app_config.config.get("vector_storage", {})
        backend = vector_config.get("backend", "faiss")
        index_dir = persist_directory or vector_config.get("index_dir", "data/indexes")
        
        embeddings = get_embeddings(model_id=embedding_model_id)
        
        # 检查索引是否已存在，如果存在且不强制重建，则复用
        if not force_rebuild and RetrieverFactory._index_exists(collection_name, index_dir):
            logger.info(f"复用已有索引: {collection_name}")
            vector_store = get_vector_store(
                backend=backend,
                embeddings=embeddings,
                collection_name=collection_name,
                persist_directory=index_dir,
                texts=None,  # 不传 texts，触发加载已有索引
                metadatas=None,
            )
        else:
            vector_store = get_vector_store(
                backend=backend,
                embeddings=embeddings,
                collection_name=collection_name,
                persist_directory=index_dir,
                texts=texts,
                metadatas=metadatas,
                use_batch_embedding=use_batch_embedding,
            )
        
        exact_retriever = ExactRetriever(chunks, config)
        embedding_retriever = EmbeddingRetriever(vector_store, chunks, config)
        
        # 创建 BM25 检索器（用于混合检索）
        bm25_retriever = None
        if include_bm25:
            bm25_retriever = BM25Retriever(chunks, config)
            logger.info("BM25 检索器已创建，支持混合检索")
        
        return CascadeRetriever(
            exact_retriever, 
            embedding_retriever, 
            config,
            bm25_retriever=bm25_retriever,
        )
    
    @staticmethod
    def create_pipeline(
        fields: list[Any],
        retriever_type: str = "cascade",
        reranker_type: Optional[str] = "llm",
        config: Optional[RetrievalConfig] = None,
        collection_name: str = "fields",
        persist_directory: Optional[str] = None,
        embedding_model_id: Optional[str] = None,
        force_rebuild: bool = False,
        use_batch_embedding: bool = True,
        **kwargs
    ) -> RetrievalPipeline:
        """
        创建检索管道
        
        Args:
            fields: 字段元数据列表
            retriever_type: 检索器类型（exact/embedding/cascade）
            reranker_type: 重排序器类型（llm/rrf/default，None 表示不重排序）
            config: 检索配置
            collection_name: 集合名称
            persist_directory: 持久化目录
            embedding_model_id: Embedding 模型 ID
            force_rebuild: 强制重建索引
            use_batch_embedding: 是否使用批量 embedding（默认 True）
        """
        if retriever_type == "exact":
            retriever = RetrieverFactory.create_exact_retriever(fields, config)
        elif retriever_type == "embedding":
            retriever = RetrieverFactory.create_embedding_retriever(
                fields, config, collection_name, persist_directory, embedding_model_id, force_rebuild,
                use_batch_embedding=use_batch_embedding,
            )
        else:  # cascade
            retriever = RetrieverFactory.create_cascade_retriever(
                fields, config, collection_name, persist_directory, embedding_model_id, force_rebuild,
                use_batch_embedding=use_batch_embedding,
            )
        
        reranker = None
        if reranker_type:
            reranker = _create_reranker(reranker_type, top_k=config.top_k if config else 10)
        
        return RetrievalPipeline(retriever, reranker)

def _create_reranker(reranker_type: str, top_k: int = 10) -> Optional[Any]:
    """创建重排序器"""
    if reranker_type == "default":
        return DefaultReranker(top_k)
    elif reranker_type == "rrf":
        return RRFReranker(top_k)
    elif reranker_type == "llm":
        try:
            manager = get_model_manager()
            llm = manager.create_llm()
            
            def llm_call_fn(prompt: str) -> str:
                response = llm.invoke(prompt)
                return response.content if hasattr(response, 'content') else str(response)
            
            return LLMReranker(top_k=top_k, llm_call_fn=llm_call_fn)
        except Exception as e:
            logger.warning(f"创建 LLMReranker 失败: {e}")
            return DefaultReranker(top_k)
    else:
        return DefaultReranker(top_k)

def create_retriever(
    fields: list[Any],
    retriever_type: str = "cascade",
    config: Optional[RetrievalConfig] = None,
    collection_name: str = "fields",
    persist_directory: Optional[str] = None,
    embedding_model_id: Optional[str] = None,
    force_rebuild: bool = False,
    use_batch_embedding: bool = True,
) -> BaseRetriever:
    """创建检索器（便捷函数）
    
    Args:
        fields: 字段元数据列表
        retriever_type: 检索器类型（exact/embedding/cascade）
        config: 检索配置
        collection_name: 集合名称
        persist_directory: 持久化目录
        embedding_model_id: Embedding 模型 ID
        force_rebuild: 强制重建索引
        use_batch_embedding: 是否使用批量 embedding（默认 True）
    """
    if retriever_type == "exact":
        return RetrieverFactory.create_exact_retriever(fields, config)
    elif retriever_type == "embedding":
        return RetrieverFactory.create_embedding_retriever(
            fields, config, collection_name, persist_directory, embedding_model_id, force_rebuild,
            use_batch_embedding=use_batch_embedding,
        )
    else:  # cascade
        return RetrieverFactory.create_cascade_retriever(
            fields, config, collection_name, persist_directory, embedding_model_id, force_rebuild,
            use_batch_embedding=use_batch_embedding,
        )

__all__ = [
    "RetrievalConfig",
    "MetadataFilter",
    "BaseRetriever",
    "ExactRetriever",
    "BM25Retriever",
    "EmbeddingRetriever",
    "CascadeRetriever",
    "RetrievalPipeline",
    "RetrieverFactory",
    "create_retriever",
]
