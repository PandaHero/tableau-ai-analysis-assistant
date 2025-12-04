"""
重排序器模块

提供多种重排序策略，专为 Tableau 扩展插件设计（无需下载大模型）。

主要功能：
- BaseReranker 抽象基类
- DefaultReranker（按分数排序）
- RRFReranker（RRF 融合重排序）
- LLMReranker（LLM 重排序，推荐）

注意：本模块不包含需要下载大模型的 CrossEncoder，
如需高质量重排序，请使用 LLMReranker 配合现有的 LLM API。
"""
import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Callable

from tableau_assistant.src.capabilities.rag.models import (
    FieldChunk,
    RetrievalResult,
    RetrievalSource,
)

logger = logging.getLogger(__name__)


class BaseReranker(ABC):
    """
    重排序器抽象基类
    
    Requirements: 4.1
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
    
    def _update_ranks(self, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """更新排名"""
        updated = []
        for rank, result in enumerate(results, 1):
            updated.append(RetrievalResult(
                field_chunk=result.field_chunk,
                score=result.score,
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


class CrossEncoderReranker(BaseReranker):
    """
    交叉编码器重排序器
    
    使用 embedding 计算查询和候选的相似度进行重排序。
    这是一个轻量级实现，不需要下载额外的大模型。
    
    注意：如需更高精度，推荐使用 LLMReranker。
    
    Requirements: 4.2
    """
    
    def __init__(
        self,
        top_k: int = 5,
        embedding_provider: Optional[Any] = None
    ):
        """
        初始化交叉编码器重排序器
        
        Args:
            top_k: 返回结果数量
            embedding_provider: 向量化提供者（可选，用于计算相似度）
        """
        super().__init__(top_k)
        self.embedding_provider = embedding_provider
    
    def rerank(
        self,
        query: str,
        candidates: List[RetrievalResult],
        top_k: Optional[int] = None
    ) -> List[RetrievalResult]:
        """使用交叉编码器重排序"""
        k = top_k or self.top_k
        
        if not candidates:
            return []
        
        unique = self._filter_duplicates(candidates)
        
        if len(unique) <= 1:
            return self._update_ranks(unique)
        
        if self.embedding_provider is None:
            # 没有 embedding provider，使用默认排序
            logger.warning("CrossEncoderReranker: 未配置 embedding_provider，使用默认排序")
            return DefaultReranker(k).rerank(query, candidates, k)
        
        try:
            import numpy as np
            
            # 获取查询向量
            query_vector = self.embedding_provider.embed_query(query)
            query_vec = np.array(query_vector)
            query_norm = np.linalg.norm(query_vec)
            
            if query_norm == 0:
                return DefaultReranker(k).rerank(query, candidates, k)
            
            query_vec_normalized = query_vec / query_norm
            
            # 计算每个候选的相似度
            scored_candidates = []
            for candidate in unique:
                # 使用索引文本计算相似度
                candidate_text = candidate.field_chunk.index_text
                candidate_vector = self.embedding_provider.embed_query(candidate_text)
                candidate_vec = np.array(candidate_vector)
                candidate_norm = np.linalg.norm(candidate_vec)
                
                if candidate_norm > 0:
                    candidate_vec_normalized = candidate_vec / candidate_norm
                    similarity = float(np.dot(query_vec_normalized, candidate_vec_normalized))
                else:
                    similarity = 0.0
                
                # 归一化到 [0, 1]
                similarity = max(0.0, min(1.0, (similarity + 1) / 2))
                
                scored_candidates.append((candidate, similarity))
            
            # 按相似度排序
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            
            # 构建结果
            reranked = []
            for candidate, score in scored_candidates:
                reranked.append(RetrievalResult(
                    field_chunk=candidate.field_chunk,
                    score=score,
                    source=candidate.source,
                    rank=candidate.rank,
                    rerank_score=score,
                    original_rank=candidate.rank
                ))
            
            return self._update_ranks(reranked[:k])
            
        except Exception as e:
            logger.error(f"CrossEncoder 重排序失败: {e}")
            return DefaultReranker(k).rerank(query, candidates, k)


class LLMReranker(BaseReranker):
    """
    LLM 重排序器（推荐）
    
    使用大语言模型判断查询和候选的相关性。
    推荐方案：利用本地部署的 LLM 或云端 API。
    
    优点：
    - 精度最高，能理解复杂语义
    - 利用现有 LLM 资源，无需额外部署
    - 支持中英文混合查询
    
    Requirements: 4.3
    """
    
    def __init__(
        self,
        top_k: int = 5,
        llm_client: Optional[Any] = None,
        model: Optional[str] = None,
        llm_call_fn: Optional[Callable[[str], str]] = None
    ):
        """
        初始化 LLM 重排序器
        
        Args:
            top_k: 返回结果数量
            llm_client: LLM 客户端（兼容 OpenAI API）
            model: 模型名称（由调用方指定）
            llm_call_fn: 自定义 LLM 调用函数
        
        使用示例：
            # 方式1：使用模型管理器
            reranker = RerankerFactory.create_llm_from_provider(
                provider="zhipu",
                model_name="glm-4-flash"
            )
            
            # 方式2：自定义调用函数
            reranker = LLMReranker(llm_call_fn=my_llm_call)
        """
        super().__init__(top_k)
        self.llm_client = llm_client
        self.model = model
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
        
        if self.llm_client is None and self.llm_call_fn is None:
            logger.warning("LLM 客户端未配置，使用默认排序")
            return DefaultReranker(k).rerank(query, candidates, k)
        
        unique = self._filter_duplicates(candidates)
        
        if len(unique) <= 1:
            return self._update_ranks(unique)
        
        try:
            prompt = self._build_rerank_prompt(query, unique)
            
            if self.llm_call_fn is not None:
                result_text = self.llm_call_fn(prompt)
            else:
                if self.model is None:
                    raise ValueError("使用 llm_client 时必须指定 model 参数")
                response = self.llm_client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1
                )
                result_text = response.choices[0].message.content
            
            ranked_indices = self._parse_ranking(result_text, len(unique))
            
            reranked = []
            for idx in ranked_indices:
                if 0 <= idx < len(unique):
                    reranked.append(unique[idx])
            
            ranked_set = set(ranked_indices)
            for i, candidate in enumerate(unique):
                if i not in ranked_set:
                    reranked.append(candidate)
            
            return self._update_ranks(reranked[:k])
            
        except Exception as e:
            logger.error(f"LLM 重排序失败: {e}")
            return DefaultReranker(k).rerank(query, candidates, k)
    
    def _build_rerank_prompt(self, query: str, candidates: List[RetrievalResult]) -> str:
        """构建重排序提示"""
        candidate_list = []
        for i, c in enumerate(candidates):
            chunk = c.field_chunk
            info = f"{i}. {chunk.field_caption}"
            info += f" (角色: {chunk.role}, 类型: {chunk.data_type}"
            if chunk.category:
                info += f", 类别: {chunk.category}"
            info += ")"
            candidate_list.append(info)
        
        return f"""你是一个 Tableau 数据分析专家。请根据用户的查询意图，对以下数据字段按相关性从高到低排序。

用户查询: {query}

候选字段:
{chr(10).join(candidate_list)}

排序规则:
1. 字段名称或含义与查询最匹配的排在前面
2. 考虑字段角色（dimension/measure）是否符合查询意图
3. 考虑数据类型是否适合查询需求

请只返回排序后的字段编号，用逗号分隔。例如: 2,0,1,3
"""
    
    def _parse_ranking(self, text: str, num_candidates: int) -> List[int]:
        """解析 LLM 返回的排序结果"""
        numbers = re.findall(r'\d+', text)
        indices = []
        
        for num in numbers:
            idx = int(num)
            if 0 <= idx < num_candidates and idx not in indices:
                indices.append(idx)
        
        return indices


class RerankerFactory:
    """
    重排序器工厂
    
    创建不同类型的重排序器。
    
    推荐：
    - LLMReranker：精度最高，利用本地/云端 LLM
    - RRFReranker：备选方案，零延迟零成本
    - CrossEncoderReranker：轻量级方案，使用 embedding 计算相似度
    """
    
    @staticmethod
    def create_default(top_k: int = 5) -> DefaultReranker:
        """创建默认重排序器（按分数排序）"""
        return DefaultReranker(top_k)
    
    @staticmethod
    def create_rrf(top_k: int = 5, k: int = 60) -> RRFReranker:
        """创建 RRF 重排序器（备选方案，零延迟）"""
        return RRFReranker(top_k, k)
    
    @staticmethod
    def create_cross_encoder(
        top_k: int = 5,
        embedding_provider: Optional[Any] = None
    ) -> CrossEncoderReranker:
        """创建交叉编码器重排序器（轻量级方案）"""
        return CrossEncoderReranker(top_k, embedding_provider)
    
    @staticmethod
    def create_llm(
        top_k: int = 5,
        llm_client: Optional[Any] = None,
        model: Optional[str] = None,
        llm_call_fn: Optional[Callable[[str], str]] = None
    ) -> LLMReranker:
        """创建 LLM 重排序器"""
        return LLMReranker(top_k, llm_client, model, llm_call_fn)
    
    @staticmethod
    def create_llm_from_provider(
        provider: str,
        model_name: str,
        top_k: int = 5,
        temperature: float = 0.1
    ) -> LLMReranker:
        """
        使用模型管理器创建 LLM 重排序器（推荐）
        
        Args:
            provider: 模型提供商（zhipu/deepseek/openai/local 等）
            model_name: 模型名称
            top_k: 返回结果数量
            temperature: 温度参数
        
        Examples:
            # 使用智谱
            reranker = RerankerFactory.create_llm_from_provider(
                provider="zhipu",
                model_name="glm-4-flash"
            )
            
            # 使用 DeepSeek
            reranker = RerankerFactory.create_llm_from_provider(
                provider="deepseek",
                model_name="deepseek-chat"
            )
        """
        try:
            from tableau_assistant.src.model_manager import select_model
            
            llm = select_model(provider, model_name, temperature)
            
            def llm_call_fn(prompt: str) -> str:
                response = llm.invoke(prompt)
                return response.content
            
            return LLMReranker(top_k=top_k, llm_call_fn=llm_call_fn)
            
        except ImportError as e:
            logger.error(f"无法导入模型管理器: {e}")
            raise
        except Exception as e:
            logger.error(f"创建 LLM 重排序器失败: {e}")
            raise


__all__ = [
    "BaseReranker",
    "DefaultReranker",
    "CrossEncoderReranker",
    "RRFReranker",
    "LLMReranker",
    "RerankerFactory",
]
