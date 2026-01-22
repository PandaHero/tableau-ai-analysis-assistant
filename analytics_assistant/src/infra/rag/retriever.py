"""
检索器

使用 langgraph_store 进行向量检索。
支持：
- ExactRetriever（精确匹配，O(1)）
- EmbeddingRetriever（向量检索）
- CascadeRetriever（级联检索：精确匹配 → 向量检索）
- RetrievalPipeline（检索管道）
- RetrieverFactory（检索器工厂）

检索策略：精确匹配 → Embedding 检索 → LLM 重排序
不使用 BM25，避免分词依赖。
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from ..storage import get_vector_store
from ..ai import get_embeddings
from ..config import get_config
from .models import FieldChunk, RetrievalResult, RetrievalSource


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
    
    def to_dict(self) -> Dict[str, str]:
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
    ) -> List[RetrievalResult]:
        pass
    
    async def aretrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
        score_threshold: float = 0.0
    ) -> List[RetrievalResult]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.retrieve(query, top_k, filters, score_threshold)
        )
    
    def _apply_filters(
        self,
        results: List[RetrievalResult],
        filters: Optional[MetadataFilter],
        score_threshold: float
    ) -> List[RetrievalResult]:
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
        chunks: Dict[str, FieldChunk],
        config: Optional[RetrievalConfig] = None,
        case_sensitive: bool = False,
        match_caption_first: bool = True
    ):
        super().__init__(config)
        self._chunks = chunks
        self.case_sensitive = case_sensitive
        self.match_caption_first = match_caption_first
        self._name_index: Dict[str, FieldChunk] = {}
        self._caption_index: Dict[str, FieldChunk] = {}
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
    ) -> List[RetrievalResult]:
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
        chunks: Dict[str, FieldChunk],
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
    ) -> List[RetrievalResult]:
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
    
    def get_all_chunks(self) -> List[FieldChunk]:
        return list(self._chunks.values())


class CascadeRetriever(BaseRetriever):
    """
    级联检索器
    
    检索策略：精确匹配 → 向量检索
    如果精确匹配成功，直接返回；否则使用向量检索。
    """
    
    def __init__(
        self,
        exact_retriever: ExactRetriever,
        embedding_retriever: EmbeddingRetriever,
        config: Optional[RetrievalConfig] = None
    ):
        super().__init__(config)
        self._exact = exact_retriever
        self._embedding = embedding_retriever
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[MetadataFilter] = None,
        score_threshold: Optional[float] = None
    ) -> List[RetrievalResult]:
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
    ) -> List[RetrievalResult]:
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
    ) -> List[RetrievalResult]:
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
    ) -> List[RetrievalResult]:
        if self.reranker is not None:
            candidate_k = rerank_top_k or top_k * 3
            candidates = await self.retriever.aretrieve(query, top_k=candidate_k, filters=filters, score_threshold=score_threshold)
            return await self.reranker.arerank(query, candidates, top_k)
        else:
            return await self.retriever.aretrieve(query, top_k=top_k, filters=filters, score_threshold=score_threshold)
    
    def batch_search(
        self,
        queries: List[str],
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None
    ) -> Dict[str, List[RetrievalResult]]:
        return {query: self.search(query, top_k, filters) for query in queries}


def _build_chunks_and_metadata(fields: List[Any]) -> tuple:
    """从字段列表构建 chunks 和 metadata"""
    chunks: Dict[str, FieldChunk] = {}
    texts = []
    metadatas = []
    
    for field_data in fields:
        chunk = FieldChunk.from_field_metadata(field_data)
        chunks[chunk.field_name] = chunk
        texts.append(chunk.index_text)
        metadatas.append({
            "field_name": chunk.field_name,
            "field_caption": chunk.field_caption,
            "role": chunk.role,
            "data_type": chunk.data_type,
            "category": chunk.category or "",
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
    def create_exact_retriever(
        fields: List[Any],
        config: Optional[RetrievalConfig] = None
    ) -> ExactRetriever:
        """创建精确匹配检索器"""
        chunks, _, _ = _build_chunks_and_metadata(fields)
        return ExactRetriever(chunks, config)
    
    @staticmethod
    def create_embedding_retriever(
        fields: List[Any],
        config: Optional[RetrievalConfig] = None,
        collection_name: str = "fields",
        persist_directory: Optional[str] = None,
        embedding_model_id: Optional[str] = None
    ) -> EmbeddingRetriever:
        """创建向量检索器"""
        chunks, texts, metadatas = _build_chunks_and_metadata(fields)
        
        app_config = get_config()
        vector_config = app_config.config.get("vector_storage", {})
        backend = vector_config.get("backend", "faiss")
        index_dir = persist_directory or vector_config.get("index_dir", "data/indexes")
        
        embeddings = get_embeddings(model_id=embedding_model_id)
        vector_store = get_vector_store(
            backend=backend,
            embeddings=embeddings,
            collection_name=collection_name,
            persist_directory=index_dir,
            texts=texts,
            metadatas=metadatas
        )
        
        return EmbeddingRetriever(vector_store, chunks, config)
    
    @staticmethod
    def create_cascade_retriever(
        fields: List[Any],
        config: Optional[RetrievalConfig] = None,
        collection_name: str = "fields",
        persist_directory: Optional[str] = None,
        embedding_model_id: Optional[str] = None
    ) -> CascadeRetriever:
        """创建级联检索器（精确匹配 → 向量检索）"""
        chunks, texts, metadatas = _build_chunks_and_metadata(fields)
        
        app_config = get_config()
        vector_config = app_config.config.get("vector_storage", {})
        backend = vector_config.get("backend", "faiss")
        index_dir = persist_directory or vector_config.get("index_dir", "data/indexes")
        
        embeddings = get_embeddings(model_id=embedding_model_id)
        vector_store = get_vector_store(
            backend=backend,
            embeddings=embeddings,
            collection_name=collection_name,
            persist_directory=index_dir,
            texts=texts,
            metadatas=metadatas
        )
        
        exact_retriever = ExactRetriever(chunks, config)
        embedding_retriever = EmbeddingRetriever(vector_store, chunks, config)
        
        return CascadeRetriever(exact_retriever, embedding_retriever, config)
    
    @staticmethod
    def create_pipeline(
        fields: List[Any],
        retriever_type: str = "cascade",
        reranker_type: Optional[str] = "llm",
        config: Optional[RetrievalConfig] = None,
        collection_name: str = "fields",
        persist_directory: Optional[str] = None,
        embedding_model_id: Optional[str] = None,
        **kwargs
    ) -> RetrievalPipeline:
        """
        创建检索管道
        
        Args:
            fields: 字段元数据列表
            retriever_type: 检索器类型（exact/embedding/cascade）
            reranker_type: 重排序器类型（llm/rrf/default，None 表示不重排序）
            config: 检索配置
        """
        if retriever_type == "exact":
            retriever = RetrieverFactory.create_exact_retriever(fields, config)
        elif retriever_type == "embedding":
            retriever = RetrieverFactory.create_embedding_retriever(
                fields, config, collection_name, persist_directory, embedding_model_id
            )
        else:  # cascade
            retriever = RetrieverFactory.create_cascade_retriever(
                fields, config, collection_name, persist_directory, embedding_model_id
            )
        
        reranker = None
        if reranker_type:
            reranker = _create_reranker(reranker_type, top_k=config.top_k if config else 10)
        
        return RetrievalPipeline(retriever, reranker)


def _create_reranker(reranker_type: str, top_k: int = 10) -> Optional[Any]:
    """创建重排序器"""
    from .reranker import DefaultReranker, RRFReranker, LLMReranker
    
    if reranker_type == "default":
        return DefaultReranker(top_k)
    elif reranker_type == "rrf":
        return RRFReranker(top_k)
    elif reranker_type == "llm":
        try:
            from ..ai import get_model_manager
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
    fields: List[Any],
    retriever_type: str = "cascade",
    config: Optional[RetrievalConfig] = None,
    collection_name: str = "fields",
    persist_directory: Optional[str] = None,
    embedding_model_id: Optional[str] = None
) -> BaseRetriever:
    """创建检索器（便捷函数）"""
    if retriever_type == "exact":
        return RetrieverFactory.create_exact_retriever(fields, config)
    elif retriever_type == "embedding":
        return RetrieverFactory.create_embedding_retriever(
            fields, config, collection_name, persist_directory, embedding_model_id
        )
    else:  # cascade
        return RetrieverFactory.create_cascade_retriever(
            fields, config, collection_name, persist_directory, embedding_model_id
        )


__all__ = [
    "RetrievalConfig",
    "MetadataFilter",
    "BaseRetriever",
    "ExactRetriever",
    "EmbeddingRetriever",
    "CascadeRetriever",
    "RetrievalPipeline",
    "RetrieverFactory",
    "create_retriever",
]
