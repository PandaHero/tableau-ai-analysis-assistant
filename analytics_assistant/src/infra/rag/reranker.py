"""
重排序器模块

提供多种重排序策略。

主要功能：
- BaseReranker 抽象基类
- DefaultReranker（按分数排序）
- RRFReranker（RRF 融合重排序）
- LLMReranker（LLM 重排序，推荐）
"""
import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable

from .models import (
    FieldChunk,
    RetrievalResult,
    RetrievalSource,
)
from .prompts import build_rerank_prompt


logger = logging.getLogger(__name__)


class BaseReranker(ABC):
    """
    重排序器抽象基类
    """
    
    def __init__(self, top_k: int = 5):
        """
        初始化重排序器
        
        Args:
            top_k: 返回结果数量
        """
        self.top_k = top_k
    
    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: List[RetrievalResult],
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """
        重排序
        
        Args:
            query: 查询文本
            candidates: 候选结果列表
            top_k: 返回结果数量（覆盖默认值）
        
        Returns:
            重排序后的结果列表
        """
        pass
    
    async def arerank(
        self,
        query: str,
        candidates: List[RetrievalResult],
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """异步重排序"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.rerank(query, candidates, top_k)
        )
    
    def _filter_duplicates(self, candidates: List[RetrievalResult]) -> List[RetrievalResult]:
        """过滤重复候选"""
        seen = set()
        unique = []
        for candidate in candidates:
            field_name = candidate.field_chunk.field_name
            if field_name not in seen:
                seen.add(field_name)
                unique.append(candidate)
        return unique
    
    def _update_ranks(self, results: List[RetrievalResult], recalculate_score: bool = False) -> List[RetrievalResult]:
        """
        更新排名
        
        Args:
            results: 重排序后的结果列表
            recalculate_score: 是否根据新排名重新计算分数
                              如果为 True，排名第一的分数为 1.0，后续递减
        """
        updated = []
        n = len(results)
        for rank, result in enumerate(results, 1):
            # 根据新排名重新计算分数：rank=1 -> 1.0, rank=2 -> 0.9, ...
            if recalculate_score and n > 0:
                new_score = max(0.5, 1.0 - (rank - 1) * 0.1)  # 最低 0.5
            else:
                new_score = result.score
            
            updated.append(RetrievalResult(
                field_chunk=result.field_chunk,
                score=new_score,
                source=result.source,
                rank=rank,
                rerank_score=result.rerank_score,
                original_rank=result.original_rank or result.rank
            ))
        return updated


class DefaultReranker(BaseReranker):
    """
    默认重排序器
    
    按分数降序排序，无需额外资源。
    """
    
    def rerank(
        self,
        query: str,
        candidates: List[RetrievalResult],
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """按分数重排序"""
        k = top_k or self.top_k
        unique = self._filter_duplicates(candidates)
        sorted_results = sorted(unique, key=lambda x: x.score, reverse=True)
        return self._update_ranks(sorted_results[:k])


class RRFReranker(BaseReranker):
    """
    RRF (Reciprocal Rank Fusion) 重排序器
    
    使用 RRF 公式融合多个检索结果，无需额外资源。
    公式: score = Σ(1/(k+rank))
    
    推荐用于混合检索场景。
    """
    
    def __init__(self, top_k: int = 5, k: int = 60):
        """
        初始化 RRF 重排序器
        
        Args:
            top_k: 返回结果数量
            k: RRF 参数 k（默认 60）
        """
        super().__init__(top_k)
        self.k = k
    
    def rerank(
        self,
        query: str,
        candidates: List[RetrievalResult],
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """RRF 重排序"""
        k = top_k or self.top_k
        unique = self._filter_duplicates(candidates)
        sorted_by_score = sorted(unique, key=lambda x: x.score, reverse=True)
        
        rrf_results = []
        for rank, result in enumerate(sorted_by_score, 1):
            rrf_score = 1.0 / (self.k + rank)
            rrf_results.append(RetrievalResult(
                field_chunk=result.field_chunk,
                score=rrf_score,
                source=result.source,
                rank=rank,
                rerank_score=rrf_score,
                original_rank=result.rank
            ))
        
        # 归一化分数
        if rrf_results:
            max_score = rrf_results[0].score
            if max_score > 0:
                for r in rrf_results:
                    r.score = r.score / max_score
        
        return self._update_ranks(rrf_results[:k])
    
    def rerank_multiple(
        self,
        query: str,
        result_lists: List[List[RetrievalResult]],
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """融合多个检索结果列表"""
        k = top_k or self.top_k
        
        rrf_scores: Dict[str, float] = {}
        field_chunks: Dict[str, FieldChunk] = {}
        original_ranks: Dict[str, int] = {}
        
        for result_list in result_lists:
            for result in result_list:
                field_name = result.field_chunk.field_name
                rrf_score = 1.0 / (self.k + result.rank)
                rrf_scores[field_name] = rrf_scores.get(field_name, 0) + rrf_score
                field_chunks[field_name] = result.field_chunk
                if field_name not in original_ranks:
                    original_ranks[field_name] = result.rank
        
        sorted_fields = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        if sorted_fields:
            max_score = sorted_fields[0][1]
            if max_score > 0:
                sorted_fields = [(name, score / max_score) for name, score in sorted_fields]
        
        results = []
        for rank, (field_name, score) in enumerate(sorted_fields[:k], 1):
            results.append(RetrievalResult(
                field_chunk=field_chunks[field_name],
                score=score,
                source=RetrievalSource.HYBRID,
                rank=rank,
                rerank_score=score,
                original_rank=original_ranks.get(field_name)
            ))
        
        return results


class LLMReranker(BaseReranker):
    """
    LLM 重排序器（推荐）
    
    使用大语言模型判断查询和候选的相关性。
    推荐方案：利用本地部署的 LLM 或云端 API。
    
    优点：
    - 精度最高，能理解复杂语义
    - 利用现有 LLM 资源，无需额外部署
    - 支持中英文混合查询
    """
    
    def __init__(
        self,
        top_k: int = 5,
        llm_call_fn: Optional[Callable[[str], str]] = None
    ):
        """
        初始化 LLM 重排序器
        
        Args:
            top_k: 返回结果数量
            llm_call_fn: 自定义 LLM 调用函数
        
        使用示例：
            # 使用 ModelManager 获取 LLM
            from analytics_assistant.src.infra.ai import get_model_manager
            manager = get_model_manager()
            llm = manager.create_llm()
            reranker = LLMReranker(llm_call_fn=lambda p: llm.invoke(p).content)
        """
        super().__init__(top_k)
        self.llm_call_fn = llm_call_fn
    
    def rerank(
        self,
        query: str,
        candidates: List[RetrievalResult],
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """使用 LLM 重排序"""
        k = top_k or self.top_k
        
        if not candidates:
            return []
        
        if self.llm_call_fn is None:
            logger.warning("LLM 调用函数未配置，使用默认排序")
            return DefaultReranker(k).rerank(query, candidates, k)
        
        unique = self._filter_duplicates(candidates)
        
        if len(unique) <= 1:
            return self._update_ranks(unique)
        
        try:
            prompt = self._build_rerank_prompt(query, unique)
            result_text = self.llm_call_fn(prompt)
            ranked_indices = self._parse_ranking(result_text, len(unique))
            
            reranked = []
            for idx in ranked_indices:
                if 0 <= idx < len(unique):
                    reranked.append(unique[idx])
            
            ranked_set = set(ranked_indices)
            for i, candidate in enumerate(unique):
                if i not in ranked_set:
                    reranked.append(candidate)
            
            # Rerank 后根据新排名重新计算分数
            return self._update_ranks(reranked[:k], recalculate_score=True)
            
        except Exception as e:
            logger.error(f"LLM 重排序失败: {e}")
            return DefaultReranker(k).rerank(query, candidates, k)
    
    def _build_rerank_prompt(self, query: str, candidates: List[RetrievalResult]) -> str:
        """构建重排序提示"""
        return build_rerank_prompt(query, candidates)
    
    def _parse_ranking(self, text: str, num_candidates: int) -> List[int]:
        """解析 LLM 返回的排序结果"""
        numbers = re.findall(r'\d+', text)
        indices = []
        
        for num in numbers:
            idx = int(num)
            if 0 <= idx < num_candidates and idx not in indices:
                indices.append(idx)
        
        return indices


__all__ = [
    "BaseReranker",
    "DefaultReranker",
    "RRFReranker",
    "LLMReranker",
]
