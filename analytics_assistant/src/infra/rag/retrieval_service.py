"""RetrievalService - 检索服务

统一的检索服务，复用现有的 CascadeRetriever 和 RetrievalPipeline。

接口适配策略：
- RetrievalService 作为适配层，将统一的 search() 接口转换为 CascadeRetriever.retrieve() 调用
- filters 格式转换：Dict[str, Any] → MetadataFilter
- 返回结果转换：RetrievalResult → SearchResult
- 分数归一化已在 CascadeRetriever 中完成，直接使用
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

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
    
    def __init__(self, index_manager: IndexManager, embedding_service: EmbeddingService):
        """初始化 RetrievalService
        
        Args:
            index_manager: 索引管理器
            embedding_service: Embedding 服务
        """
        self._index_manager = index_manager
        self._embedding_service = embedding_service
    
    def search(
        self,
        index_name: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: float = 0.0,
        strategy: str = "cascade",
    ) -> List[SearchResult]:
        """向量搜索
        
        Args:
            index_name: 索引名称
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤条件
            score_threshold: 分数阈值
            strategy: 检索策略
                - "cascade": 级联检索（精确匹配 → 向量检索，默认）
                - "exact": 仅精确匹配（O(1) 哈希查找）
                - "embedding": 仅向量检索
        
        Returns:
            SearchResult 列表
            
        Raises:
            IndexNotFoundError: 索引不存在
        """
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
        else:
            # 默认：级联检索
            retrieval_results = retriever.retrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        
        # 4. 转换返回结果
        return self._convert_results(retrieval_results)
    
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
        strategy: str = "cascade",
    ) -> List[SearchResult]:
        """异步向量搜索
        
        复用 CascadeRetriever.aretrieve()。
        
        Args:
            index_name: 索引名称
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤条件
            score_threshold: 分数阈值
            strategy: 检索策略
            
        Returns:
            SearchResult 列表
        """
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
        else:
            retrieval_results = await retriever.aretrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        
        return self._convert_results(retrieval_results)
    
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
        """异步批量搜索
        
        Args:
            index_name: 索引名称
            queries: 查询文本列表
            top_k: 每个查询返回的结果数量
            filters: 元数据过滤条件
            
        Returns:
            {query: [SearchResult, ...], ...}
        """
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
