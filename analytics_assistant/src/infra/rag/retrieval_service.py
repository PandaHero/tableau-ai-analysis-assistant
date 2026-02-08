"""RetrievalService - 检索服务

统一的检索服务，复用现有的 CascadeRetriever 和 RetrievalPipeline。

接口适配策略：
- RetrievalService 作为适配层，将统一的 search() 接口转换为 CascadeRetriever.retrieve() 调用
- filters 格式转换：Dict[str, Any] → MetadataFilter
- 返回结果转换：RetrievalResult → SearchResult
- 分数归一化已在 CascadeRetriever 中完成，直接使用

配置驱动：
- 从 app.yaml 读取 rag.retrieval.retriever_type 配置
- 支持 hybrid（混合检索）和 cascade（级联检索）策略
- 混合检索支持 RRF 和加权融合两种结果合并方式
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.ai import embed_documents_batch

from .exceptions import IndexNotFoundError
from .index_manager import IndexManager
from .embedding_service import EmbeddingService
from .retriever import MetadataFilter, RetrievalResult
from .schemas import SearchResult

logger = logging.getLogger(__name__)


class RetrievalService:
    """检索服务 - 适配层
    
    复用现有的检索器实现：
    - ExactRetriever：O(1) 精确匹配
    - EmbeddingRetriever：向量检索
    - CascadeRetriever：级联检索
    - RetrievalPipeline：检索管道（支持重排序）
    
    配置驱动的检索策略：
    - hybrid: 混合检索（embedding + keyword），支持 RRF/加权融合
    - cascade: 级联检索（精确匹配 → embedding）
    
    统一的相似度归一化公式（已在 CascadeRetriever 中实现）：
    - FAISS L2 距离: similarity = 1.0 / (1.0 + distance)
    - 内积: similarity = (score + 1.0) / 2.0
    - 余弦: similarity = (score + 1.0) / 2.0
    """
    
    # 统一的相似度归一化公式
    SCORE_FORMULAS = {
        "l2": lambda d: 1.0 / (1.0 + d),
        "inner_product": lambda s: (s + 1.0) / 2.0,
        "cosine": lambda s: (s + 1.0) / 2.0,
    }
    
    # 默认配置值
    _DEFAULT_STRATEGY = "cascade"
    _DEFAULT_EMBEDDING_WEIGHT = 0.7
    _DEFAULT_KEYWORD_WEIGHT = 0.3
    _DEFAULT_USE_RRF = True
    _DEFAULT_RRF_K = 60
    
    def __init__(self, index_manager: IndexManager, embedding_service: EmbeddingService):
        """初始化 RetrievalService
        
        Args:
            index_manager: 索引管理器
            embedding_service: Embedding 服务
        """
        self._index_manager = index_manager
        self._embedding_service = embedding_service
        self._load_config()
    
    def _load_config(self) -> None:
        """从配置加载检索参数"""
        try:
            config = get_config()
            rag_config = config.config.get("rag", {}).get("retrieval", {})
            
            self._default_strategy = rag_config.get("retriever_type", self._DEFAULT_STRATEGY)
            self._embedding_weight = rag_config.get("embedding_weight", self._DEFAULT_EMBEDDING_WEIGHT)
            self._keyword_weight = rag_config.get("keyword_weight", self._DEFAULT_KEYWORD_WEIGHT)
            self._use_rrf = rag_config.get("use_rrf", self._DEFAULT_USE_RRF)
            self._rrf_k = rag_config.get("rrf_k", self._DEFAULT_RRF_K)
            
            logger.info(
                f"RetrievalService 配置加载完成: strategy={self._default_strategy}, "
                f"embedding_weight={self._embedding_weight}, keyword_weight={self._keyword_weight}, "
                f"use_rrf={self._use_rrf}, rrf_k={self._rrf_k}"
            )
        except Exception as e:
            logger.warning(f"加载检索配置失败，使用默认值: {e}")
            self._default_strategy = self._DEFAULT_STRATEGY
            self._embedding_weight = self._DEFAULT_EMBEDDING_WEIGHT
            self._keyword_weight = self._DEFAULT_KEYWORD_WEIGHT
            self._use_rrf = self._DEFAULT_USE_RRF
            self._rrf_k = self._DEFAULT_RRF_K
    
    def search(
        self,
        index_name: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: float = 0.0,
        strategy: Optional[str] = None,
    ) -> List[SearchResult]:
        """向量搜索
        
        Args:
            index_name: 索引名称
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤条件
            score_threshold: 分数阈值
            strategy: 检索策略（None 使用配置默认值）
                - "hybrid": 混合检索（embedding + keyword）
                - "cascade": 级联检索（精确匹配 → 向量检索）
                - "exact": 仅精确匹配（O(1) 哈希查找）
                - "embedding": 仅向量检索
        
        Returns:
            SearchResult 列表
            
        Raises:
            IndexNotFoundError: 索引不存在
        """
        # 使用配置的默认策略
        strategy = strategy or self._default_strategy
        
        # 1. 获取检索器
        retriever = self._index_manager.get_index(index_name)
        if retriever is None:
            raise IndexNotFoundError(f"索引 '{index_name}' 不存在")
        
        # 2. 转换 filters 格式
        metadata_filter = self._convert_filters(filters) if filters else None
        
        # 3. 根据 strategy 选择检索方式
        if strategy == "exact":
            # 仅精确匹配
            retrieval_results = retriever._exact.retrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
            )
        elif strategy == "embedding":
            # 仅向量检索
            retrieval_results = retriever._embedding.retrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        elif strategy == "hybrid":
            # 混合检索
            return self._hybrid_search(
                retriever=retriever,
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        elif strategy == "cascade":
            # 级联检索
            retrieval_results = retriever.retrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        else:
            # 不支持的策略，回退到 cascade
            logger.warning(
                f"不支持的检索策略: {strategy}，回退到 cascade"
            )
            retrieval_results = retriever.retrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        
        # 4. 转换返回结果
        return self._convert_results(retrieval_results)
    
    def _hybrid_search(
        self,
        retriever,
        query: str,
        top_k: int,
        filters: Optional[MetadataFilter],
        score_threshold: float,
    ) -> List[SearchResult]:
        """混合检索：embedding + BM25
        
        Args:
            retriever: 检索器实例（CascadeRetriever，包含 _bm25）
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤条件
            score_threshold: 分数阈值
            
        Returns:
            融合后的 SearchResult 列表
        """
        # 1. Embedding 检索（获取更多候选用于融合）
        embedding_results = retriever._embedding.retrieve(
            query=query,
            top_k=top_k * 2,
            filters=filters,
            score_threshold=score_threshold,
        )
        
        # 2. BM25 关键词检索（如果可用）
        # 如果没有 BM25 检索器，回退到精确匹配
        if retriever._bm25 is not None:
            keyword_results = retriever._bm25.retrieve(
                query=query,
                top_k=top_k * 2,
                filters=filters,
            )
            logger.info(f"混合检索: BM25 返回 {len(keyword_results)} 个结果")
            if keyword_results:
                for i, r in enumerate(keyword_results[:3]):
                    logger.info(f"  BM25[{i+1}]: {r.field_chunk.field_caption} (score={r.score:.3f})")
        else:
            # 回退到精确匹配（兼容旧代码）
            keyword_results = retriever._exact.retrieve(
                query=query,
                top_k=top_k * 2,
                filters=filters,
            )
            logger.info(f"混合检索: 精确匹配返回 {len(keyword_results)} 个结果（BM25 不可用）")
        
        # 3. 结果融合
        if self._use_rrf:
            fused_results = self._rrf_fusion(
                embedding_results,
                keyword_results,
                top_k,
            )
        else:
            fused_results = self._weighted_fusion(
                embedding_results,
                keyword_results,
                top_k,
            )
        
        return fused_results
    
    def _rrf_fusion(
        self,
        results1: List[RetrievalResult],
        results2: List[RetrievalResult],
        top_k: int,
    ) -> List[SearchResult]:
        """RRF (Reciprocal Rank Fusion) 融合
        
        RRF 公式: score = sum(1 / (k + rank))
        其中 k 是平滑参数（默认 60）
        
        Args:
            results1: 第一组检索结果（embedding）
            results2: 第二组检索结果（keyword）
            top_k: 返回结果数量
            
        Returns:
            融合后的 SearchResult 列表
        """
        scores: Dict[str, float] = {}
        result_map: Dict[str, RetrievalResult] = {}
        
        # 计算第一组结果的 RRF 分数
        for rank, result in enumerate(results1, 1):
            doc_id = result.field_chunk.field_name
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (self._rrf_k + rank)
            result_map[doc_id] = result
        
        # 计算第二组结果的 RRF 分数
        for rank, result in enumerate(results2, 1):
            doc_id = result.field_chunk.field_name
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (self._rrf_k + rank)
            if doc_id not in result_map:
                result_map[doc_id] = result
        
        # 按融合分数排序
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        # 构建返回结果
        search_results = []
        for rank, doc_id in enumerate(sorted_ids[:top_k], 1):
            result = result_map[doc_id]
            search_results.append(SearchResult(
                doc_id=doc_id,
                content=result.field_chunk.index_text,
                score=scores[doc_id],  # RRF 融合分数
                rank=rank,
                metadata={
                    "role": result.field_chunk.role,
                    "data_type": result.field_chunk.data_type,
                    "category": result.field_chunk.category or "",
                    **(result.field_chunk.metadata or {}),
                },
                raw_score=result.raw_score,
            ))
        
        return search_results
    
    def _weighted_fusion(
        self,
        results1: List[RetrievalResult],
        results2: List[RetrievalResult],
        top_k: int,
    ) -> List[SearchResult]:
        """加权融合
        
        使用配置的 embedding_weight 和 keyword_weight 进行加权平均
        
        Args:
            results1: 第一组检索结果（embedding）
            results2: 第二组检索结果（keyword）
            top_k: 返回结果数量
            
        Returns:
            融合后的 SearchResult 列表
        """
        scores: Dict[str, float] = {}
        result_map: Dict[str, RetrievalResult] = {}
        
        # 计算第一组结果的加权分数
        for result in results1:
            doc_id = result.field_chunk.field_name
            scores[doc_id] = scores.get(doc_id, 0) + result.score * self._embedding_weight
            result_map[doc_id] = result
        
        # 计算第二组结果的加权分数
        for result in results2:
            doc_id = result.field_chunk.field_name
            scores[doc_id] = scores.get(doc_id, 0) + result.score * self._keyword_weight
            if doc_id not in result_map:
                result_map[doc_id] = result
        
        # 按融合分数排序
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        
        # 构建返回结果
        search_results = []
        for rank, doc_id in enumerate(sorted_ids[:top_k], 1):
            result = result_map[doc_id]
            search_results.append(SearchResult(
                doc_id=doc_id,
                content=result.field_chunk.index_text,
                score=scores[doc_id],  # 加权融合分数
                rank=rank,
                metadata={
                    "role": result.field_chunk.role,
                    "data_type": result.field_chunk.data_type,
                    "category": result.field_chunk.category or "",
                    **(result.field_chunk.metadata or {}),
                },
                raw_score=result.raw_score,
            ))
        
        return search_results
    
    def _convert_filters(self, filters: Dict[str, Any]) -> MetadataFilter:
        """将 Dict 格式转换为 MetadataFilter"""
        return MetadataFilter(
            role=filters.get("role"),
            data_type=filters.get("data_type"),
            category=filters.get("category"),
        )
    
    def _convert_results(
        self, retrieval_results: List[RetrievalResult]
    ) -> List[SearchResult]:
        """将 RetrievalResult 转换为 SearchResult"""
        search_results = []
        for rank, result in enumerate(retrieval_results, start=1):
            # 分数已经在 retriever 中归一化，直接使用
            search_results.append(SearchResult(
                doc_id=result.field_chunk.field_name,
                content=result.field_chunk.index_text,
                score=result.score,  # 已归一化
                rank=rank,
                metadata={
                    "role": result.field_chunk.role,
                    "data_type": result.field_chunk.data_type,
                    "category": result.field_chunk.category or "",
                    **(result.field_chunk.metadata or {}),
                },
                raw_score=result.raw_score,
            ))
        return search_results
    
    async def search_async(
        self,
        index_name: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: float = 0.0,
        strategy: Optional[str] = None,
    ) -> List[SearchResult]:
        """异步向量搜索
        
        复用 CascadeRetriever.aretrieve()。
        
        Args:
            index_name: 索引名称
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤条件
            score_threshold: 分数阈值
            strategy: 检索策略（None 使用配置默认值）
            
        Returns:
            SearchResult 列表
        """
        # 使用配置的默认策略
        strategy = strategy or self._default_strategy
        
        retriever = self._index_manager.get_index(index_name)
        if retriever is None:
            raise IndexNotFoundError(f"索引 '{index_name}' 不存在")
        
        metadata_filter = self._convert_filters(filters) if filters else None
        
        # 异步检索
        if strategy == "exact":
            # 精确匹配是 O(1)，无需异步
            retrieval_results = retriever._exact.retrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
            )
        elif strategy == "embedding":
            retrieval_results = await retriever._embedding.aretrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        elif strategy == "hybrid":
            # 混合检索（异步版本）
            return await self._hybrid_search_async(
                retriever=retriever,
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        elif strategy == "cascade":
            retrieval_results = await retriever.aretrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        else:
            # 不支持的策略，回退到 cascade
            logger.warning(
                f"不支持的检索策略: {strategy}，回退到 cascade"
            )
            retrieval_results = await retriever.aretrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        
        return self._convert_results(retrieval_results)
    
    async def _hybrid_search_async(
        self,
        retriever,
        query: str,
        top_k: int,
        filters: Optional[MetadataFilter],
        score_threshold: float,
    ) -> List[SearchResult]:
        """异步混合检索：embedding + BM25
        
        Args:
            retriever: 检索器实例（CascadeRetriever，包含 _bm25）
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤条件
            score_threshold: 分数阈值
            
        Returns:
            融合后的 SearchResult 列表
        """
        # 并行执行 embedding 和 BM25 检索
        embedding_task = retriever._embedding.aretrieve(
            query=query,
            top_k=top_k * 2,
            filters=filters,
            score_threshold=score_threshold,
        )
        
        # BM25 检索（如果可用）
        async def keyword_search():
            if retriever._bm25 is not None:
                # BM25 是同步的，包装为协程
                return retriever._bm25.retrieve(
                    query=query,
                    top_k=top_k * 2,
                    filters=filters,
                )
            else:
                # 回退到精确匹配
                return retriever._exact.retrieve(
                    query=query,
                    top_k=top_k * 2,
                    filters=filters,
                )
        
        embedding_results, keyword_results = await asyncio.gather(
            embedding_task,
            keyword_search(),
        )
        
        logger.info(
            f"异步混合检索: Embedding={len(embedding_results)}, "
            f"Keyword={'BM25' if retriever._bm25 else 'Exact'}={len(keyword_results)}"
        )
        
        # 打印 BM25 结果详情
        if retriever._bm25 is not None and keyword_results:
            for i, r in enumerate(keyword_results[:3]):
                logger.info(f"  BM25[{i+1}]: {r.field_chunk.field_caption} (score={r.score:.3f})")
        
        # 结果融合
        if self._use_rrf:
            return self._rrf_fusion(embedding_results, keyword_results, top_k)
        else:
            return self._weighted_fusion(embedding_results, keyword_results, top_k)
    
    def batch_search(
        self,
        index_name: str,
        queries: List[str],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[SearchResult]]:
        """批量搜索
        
        Args:
            index_name: 索引名称
            queries: 查询文本列表
            top_k: 每个查询返回的结果数量
            filters: 元数据过滤条件
            
        Returns:
            {query: [SearchResult, ...], ...}
        """
        results = {}
        for query in queries:
            results[query] = self.search(
                index_name=index_name,
                query=query,
                top_k=top_k,
                filters=filters,
            )
        return results
    
    async def batch_search_async(
        self,
        index_name: str,
        queries: List[str],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[SearchResult]]:
        """异步批量搜索（优化版：批量计算 embedding）
        
        优化策略：
        1. 先批量计算所有 query 的 embedding（一次 API 调用）
        2. 然后用 embedding 向量直接在 FAISS 中搜索
        
        Args:
            index_name: 索引名称
            queries: 查询文本列表
            top_k: 每个查询返回的结果数量
            filters: 元数据过滤条件
            
        Returns:
            {query: [SearchResult, ...], ...}
        """
        if not queries:
            return {}
        
        retriever = self._index_manager.get_index(index_name)
        if retriever is None:
            raise IndexNotFoundError(f"索引 '{index_name}' 不存在")
        
        metadata_filter = self._convert_filters(filters) if filters else None
        
        # 尝试使用批量 embedding 优化
        try:
            # 获取 FAISS 向量存储和 chunks
            embedding_retriever = retriever._embedding
            vector_store = embedding_retriever._store
            chunks = embedding_retriever._chunks
            
            # 检查是否支持 similarity_search_by_vector
            if not hasattr(vector_store, 'similarity_search_with_score_by_vector'):
                logger.info("向量存储不支持 similarity_search_with_score_by_vector，回退到并行搜索")
                return await self._batch_search_parallel(index_name, queries, top_k, filters)
            
            # 批量计算 embedding
            logger.info(f"批量 Embedding: {len(queries)} 个查询")
            query_embeddings = embed_documents_batch(queries)
            
            # 用 embedding 向量搜索
            results: Dict[str, List[SearchResult]] = {}
            filter_dict = metadata_filter.to_dict() if metadata_filter else None
            threshold = retriever.config.score_threshold if hasattr(retriever, 'config') else 0.0
            
            for query, embedding in zip(queries, query_embeddings):
                if not embedding:
                    results[query] = []
                    continue
                
                try:
                    # 使用 embedding 向量直接搜索
                    if filter_dict:
                        docs_and_scores = vector_store.similarity_search_with_score_by_vector(
                            embedding, k=top_k * 2, filter=filter_dict
                        )
                    else:
                        docs_and_scores = vector_store.similarity_search_with_score_by_vector(
                            embedding, k=top_k * 2
                        )
                    
                    # 转换结果
                    search_results = []
                    for rank, (doc, score) in enumerate(docs_and_scores, 1):
                        field_name = doc.metadata.get("field_name")
                        if field_name and field_name in chunks:
                            # L2 距离转相似度
                            similarity = 1.0 / (1.0 + score)
                            if similarity >= threshold:
                                search_results.append(SearchResult(
                                    doc_id=field_name,
                                    content=chunks[field_name].index_text,
                                    score=similarity,
                                    rank=rank,
                                    metadata={
                                        "role": chunks[field_name].role,
                                        "data_type": chunks[field_name].data_type,
                                        "category": chunks[field_name].category or "",
                                        **(chunks[field_name].metadata or {}),
                                    },
                                    raw_score=score,
                                ))
                    
                    results[query] = search_results[:top_k]
                    
                except Exception as e:
                    logger.warning(f"向量搜索失败({query}): {e}")
                    results[query] = []
            
            logger.info(f"批量搜索完成: {len(queries)} 个查询")
            return results
            
        except Exception as e:
            logger.warning(f"批量 Embedding 优化失败，回退到并行搜索: {e}")
            return await self._batch_search_parallel(index_name, queries, top_k, filters)
    
    async def _batch_search_parallel(
        self,
        index_name: str,
        queries: List[str],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[SearchResult]]:
        """并行批量搜索（回退方案）"""
        tasks = [
            self.search_async(index_name, query, top_k, filters)
            for query in queries
        ]
        results_list = await asyncio.gather(*tasks)
        return dict(zip(queries, results_list))
    
    @staticmethod
    def normalize_score(raw_score: float, score_type: str = "l2") -> float:
        """归一化分数到 [0, 1] 范围
        
        使用统一的公式，替代各组件的不同实现。
        注意：CascadeRetriever 已经做了归一化，此方法仅供外部使用。
        
        Args:
            raw_score: 原始分数
            score_type: 分数类型（l2, inner_product, cosine）
            
        Returns:
            归一化后的分数 [0, 1]
        """
        formula = RetrievalService.SCORE_FORMULAS.get(score_type)
        if formula:
            return max(0.0, min(1.0, formula(raw_score)))
        return max(0.0, min(1.0, raw_score))
