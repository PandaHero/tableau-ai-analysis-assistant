"""
语义映射器

参考 DB-GPT 的 SchemaLinking 实现模式，提供用户字段到数据库字段的语义映射。

主要功能：
- 向量检索 top-K
- 上下文消歧
- 低置信度备选
- 高置信度快速路径
- 历史结果复用（相似度 > 0.95）

注意：LLM 判断功能由任务规划 agent 处理，本模块不包含 LLM 调用。
"""
import logging
import time
import numpy as np
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from tableau_assistant.src.capabilities.rag.models import (
    FieldChunk,
    RetrievalResult,
    RetrievalSource,
)
from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer

logger = logging.getLogger(__name__)


class MappingSource(Enum):
    """映射结果来源"""
    CACHE = "cache"           # 缓存命中
    VECTOR = "vector"         # 向量检索
    VECTOR_FAST = "vector_fast"  # 高置信度快速路径
    FALLBACK = "fallback"     # 降级结果


@dataclass
class LatencyBreakdown:
    """
    延迟分解
    
    记录各阶段的延迟（毫秒）
    
    Attributes:
        embedding_ms: 向量化延迟
        retrieval_ms: 检索延迟
        rerank_ms: 重排序延迟（如果有）
        disambiguation_ms: 消歧延迟
        total_ms: 总延迟
    """
    embedding_ms: int = 0
    retrieval_ms: int = 0
    rerank_ms: int = 0
    disambiguation_ms: int = 0
    total_ms: int = 0
    
    def to_dict(self) -> Dict[str, int]:
        """转换为字典"""
        return {
            "embedding_ms": self.embedding_ms,
            "retrieval_ms": self.retrieval_ms,
            "rerank_ms": self.rerank_ms,
            "disambiguation_ms": self.disambiguation_ms,
            "total_ms": self.total_ms,
        }


@dataclass
class FieldMappingResult:
    """
    字段映射结果
    
    Attributes:
        term: 原始业务术语
        matched_field: 匹配的字段名
        confidence: 置信度 (0-1)
        reasoning: LLM 推理过程（如果使用 LLM）
        alternatives: 备选字段列表
        source: 结果来源
        latency_ms: 总延迟（毫秒）
        latency_breakdown: 延迟分解
        retrieval_results: 原始检索结果
    """
    term: str
    matched_field: Optional[str]
    confidence: float
    reasoning: Optional[str] = None
    alternatives: List[str] = field(default_factory=list)
    source: MappingSource = MappingSource.VECTOR
    latency_ms: int = 0
    latency_breakdown: Optional[LatencyBreakdown] = None
    retrieval_results: List[RetrievalResult] = field(default_factory=list)
    
    @property
    def is_confident(self) -> bool:
        """是否高置信度匹配"""
        return self.confidence >= 0.7
    
    @property
    def needs_disambiguation(self) -> bool:
        """是否需要消歧"""
        return not self.is_confident and len(self.alternatives) > 0


@dataclass
class MappingConfig:
    """
    映射配置
    
    Attributes:
        top_k: 向量检索返回数量
        confidence_threshold: 置信度阈值
        high_confidence_threshold: 高置信度阈值（快速路径）
        history_similarity_threshold: 历史结果复用相似度阈值
        max_alternatives: 最大备选数量
        enable_cache: 是否启用缓存
        enable_history_reuse: 是否启用历史结果复用
        max_history_size: 最大历史记录数量
    """
    top_k: int = 10
    confidence_threshold: float = 0.7
    high_confidence_threshold: float = 0.9
    history_similarity_threshold: float = 0.95
    max_alternatives: int = 3
    enable_cache: bool = True
    enable_history_reuse: bool = True
    max_history_size: int = 1000


@dataclass
class HistoryEntry:
    """
    历史查询记录
    
    Attributes:
        term: 查询术语
        query_vector: 查询向量
        result: 映射结果
        timestamp: 时间戳
    """
    term: str
    query_vector: List[float]
    result: 'FieldMappingResult'
    timestamp: float


class SemanticMapper:
    """
    语义映射器
    
    提供用户字段到数据库字段的语义映射功能。
    参考 DB-GPT 的 SchemaLinking 实现模式。
    
    主要功能：
    - 向量检索 top-K
    - 元数据消歧
    - 高置信度快速路径（>0.9 直接返回）
    - 低置信度备选（<0.7 返回 top-3）
    - 历史结果复用（相似度 > 0.95 时复用缓存结果）
    
    注意：LLM 判断由任务规划 agent 处理，本模块只返回检索结果和候选字段。
    """
    
    def __init__(
        self,
        field_indexer: FieldIndexer,
        config: Optional[MappingConfig] = None,
        cache_manager: Optional[Any] = None
    ):
        """
        初始化语义映射器
        
        Args:
            field_indexer: 字段索引器
            config: 映射配置
            cache_manager: 缓存管理器（可选）
        """
        self.field_indexer = field_indexer
        self.config = config or MappingConfig()
        self.cache_manager = cache_manager
        
        # 历史查询记录（用于相似度复用）
        self._history: List[HistoryEntry] = []
        self._history_vectors: Optional[np.ndarray] = None
        
        # 统计信息
        self._total_mappings = 0
        self._cache_hits = 0
        self._fast_path_hits = 0
        self._history_reuse_hits = 0
    
    def map_field(
        self,
        term: str,
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
        category_filter: Optional[str] = None
    ) -> FieldMappingResult:
        """
        将业务术语映射到字段
        
        Args:
            term: 业务术语
            context: 上下文信息（用于消歧）
            role_filter: 角色过滤（dimension/measure）
            category_filter: 类别过滤
        
        Returns:
            字段映射结果（包含延迟分解）
        """
        start_time = time.time()
        latency = LatencyBreakdown()
        self._total_mappings += 1
        
        if not term or not term.strip():
            return FieldMappingResult(
                term=term,
                matched_field=None,
                confidence=0.0,
                source=MappingSource.VECTOR,
                latency_ms=0,
                latency_breakdown=latency
            )
        
        term = term.strip()
        
        # 1. 检查缓存（如果启用）
        if self.config.enable_cache and self.cache_manager:
            cached = self._check_cache(term)
            if cached:
                self._cache_hits += 1
                cached.latency_ms = int((time.time() - start_time) * 1000)
                return cached
        
        # 2. 获取查询向量（记录 embedding 延迟）
        embedding_start = time.time()
        query = self._build_query(term, context)
        query_vector = self.field_indexer.embedding_provider.embed_query(query)
        latency.embedding_ms = int((time.time() - embedding_start) * 1000)
        
        # 3. 检查历史结果复用（相似度 > 0.95）
        if self.config.enable_history_reuse:
            history_result = self._check_history_reuse(query_vector)
            if history_result:
                self._history_reuse_hits += 1
                total_ms = int((time.time() - start_time) * 1000)
                latency.total_ms = total_ms
                # 复制结果并更新元信息
                result = FieldMappingResult(
                    term=term,
                    matched_field=history_result.matched_field,
                    confidence=history_result.confidence,
                    reasoning=history_result.reasoning,
                    alternatives=history_result.alternatives.copy(),
                    source=MappingSource.CACHE,  # 标记为缓存来源
                    latency_ms=total_ms,
                    latency_breakdown=latency,
                    retrieval_results=history_result.retrieval_results
                )
                return result
        
        # 4. 向量检索 top-K（记录 retrieval 延迟）
        retrieval_start = time.time()
        retrieval_results = self.field_indexer.search(
            query=query,
            top_k=self.config.top_k,
            role_filter=role_filter,
            category_filter=category_filter
        )
        latency.retrieval_ms = int((time.time() - retrieval_start) * 1000)
        
        if not retrieval_results:
            total_ms = int((time.time() - start_time) * 1000)
            latency.total_ms = total_ms
            return FieldMappingResult(
                term=term,
                matched_field=None,
                confidence=0.0,
                source=MappingSource.VECTOR,
                latency_ms=total_ms,
                latency_breakdown=latency,
                retrieval_results=[]
            )
        
        # 5. 检查高置信度快速路径
        top_result = retrieval_results[0]
        if top_result.score >= self.config.high_confidence_threshold:
            self._fast_path_hits += 1
            total_ms = int((time.time() - start_time) * 1000)
            latency.total_ms = total_ms
            result = FieldMappingResult(
                term=term,
                matched_field=top_result.field_chunk.field_name,
                confidence=top_result.score,
                source=MappingSource.VECTOR_FAST,
                latency_ms=total_ms,
                latency_breakdown=latency,
                retrieval_results=retrieval_results
            )
            self._save_to_cache(term, result)
            self._add_to_history(term, query_vector, result)
            
            # 记录延迟日志
            logger.debug(
                f"字段映射完成(快速路径): term='{term}', "
                f"embedding={latency.embedding_ms}ms, retrieval={latency.retrieval_ms}ms, "
                f"total={total_ms}ms"
            )
            return result
        
        # 6. 使用元数据消歧（记录 disambiguation 延迟）
        disamb_start = time.time()
        disambiguated_results = self._disambiguate(term, context, retrieval_results)
        latency.disambiguation_ms = int((time.time() - disamb_start) * 1000)
        
        # 7. 构建结果
        best_result = disambiguated_results[0] if disambiguated_results else top_result
        confidence = best_result.score
        
        # 8. 低置信度处理：返回备选
        alternatives = []
        if confidence < self.config.confidence_threshold:
            alternatives = [
                r.field_chunk.field_name 
                for r in disambiguated_results[1:self.config.max_alternatives + 1]
            ]
        
        total_ms = int((time.time() - start_time) * 1000)
        latency.total_ms = total_ms
        
        result = FieldMappingResult(
            term=term,
            matched_field=best_result.field_chunk.field_name if confidence >= self.config.confidence_threshold else None,
            confidence=confidence,
            alternatives=alternatives,
            source=MappingSource.VECTOR,
            latency_ms=total_ms,
            latency_breakdown=latency,
            retrieval_results=retrieval_results
        )
        
        self._save_to_cache(term, result)
        self._add_to_history(term, query_vector, result)
        
        # 记录延迟日志
        logger.debug(
            f"字段映射完成: term='{term}', "
            f"embedding={latency.embedding_ms}ms, retrieval={latency.retrieval_ms}ms, "
            f"disambiguation={latency.disambiguation_ms}ms, total={total_ms}ms"
        )
        
        return result
    
    def map_fields_batch(
        self,
        terms: List[str],
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
        category_filter: Optional[str] = None
    ) -> List[FieldMappingResult]:
        """
        批量映射字段（串行处理）
        
        Args:
            terms: 业务术语列表
            context: 上下文信息
            role_filter: 角色过滤
            category_filter: 类别过滤
        
        Returns:
            映射结果列表
        """
        results = []
        for term in terms:
            result = self.map_field(
                term=term,
                context=context,
                role_filter=role_filter,
                category_filter=category_filter
            )
            results.append(result)
        return results
    
    async def map_fields_batch_async(
        self,
        terms: List[str],
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        max_concurrency: int = 5
    ) -> List[FieldMappingResult]:
        """
        批量映射字段（并发处理）
        
        使用 asyncio 并发处理最多 max_concurrency 个查询。
        
        Args:
            terms: 业务术语列表
            context: 上下文信息
            role_filter: 角色过滤
            category_filter: 类别过滤
            max_concurrency: 最大并发数（默认 5）
        
        Returns:
            映射结果列表（保持原始顺序）
        
        **Validates: Requirements 13.4**
        """
        import asyncio
        
        if not terms:
            return []
        
        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def map_with_semaphore(term: str, index: int) -> Tuple[int, FieldMappingResult]:
            """带信号量的映射任务"""
            async with semaphore:
                # 在线程池中执行同步方法
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self.map_field(
                        term=term,
                        context=context,
                        role_filter=role_filter,
                        category_filter=category_filter
                    )
                )
                return (index, result)
        
        # 创建所有任务
        tasks = [
            map_with_semaphore(term, i)
            for i, term in enumerate(terms)
        ]
        
        # 并发执行
        indexed_results = await asyncio.gather(*tasks)
        
        # 按原始顺序排序
        indexed_results.sort(key=lambda x: x[0])
        
        return [result for _, result in indexed_results]
    
    def _build_query(self, term: str, context: Optional[str] = None) -> str:
        """构建查询文本"""
        if context:
            return f"{term} {context}"
        return term
    
    def _check_cache(self, term: str) -> Optional[FieldMappingResult]:
        """检查缓存"""
        if not self.cache_manager:
            return None
        try:
            # 简单实现：假设 cache_manager 有 get 方法
            cached = self.cache_manager.get(f"mapping:{term}")
            if cached:
                cached.source = MappingSource.CACHE
                return cached
        except Exception as e:
            logger.debug(f"缓存检查失败: {e}")
        return None
    
    def _save_to_cache(self, term: str, result: FieldMappingResult) -> None:
        """保存到缓存"""
        if not self.cache_manager or not self.config.enable_cache:
            return
        try:
            self.cache_manager.put(f"mapping:{term}", result)
        except Exception as e:
            logger.debug(f"缓存保存失败: {e}")
    
    def _check_history_reuse(self, query_vector: List[float]) -> Optional[FieldMappingResult]:
        """
        检查历史结果复用
        
        当查询向量与历史查询的相似度 > 0.95 时，复用历史结果。
        
        Args:
            query_vector: 查询向量
        
        Returns:
            历史映射结果，如果没有相似的历史则返回 None
        """
        if not self._history or self._history_vectors is None:
            return None
        
        try:
            # 计算与所有历史向量的余弦相似度
            query_vec = np.array(query_vector)
            query_norm = np.linalg.norm(query_vec)
            
            if query_norm == 0:
                return None
            
            # 归一化查询向量
            query_vec_normalized = query_vec / query_norm
            
            # 计算余弦相似度
            history_norms = np.linalg.norm(self._history_vectors, axis=1, keepdims=True)
            # 避免除零
            history_norms = np.where(history_norms == 0, 1, history_norms)
            history_normalized = self._history_vectors / history_norms
            
            similarities = np.dot(history_normalized, query_vec_normalized)
            
            # 找到最相似的历史记录
            max_idx = np.argmax(similarities)
            max_similarity = similarities[max_idx]
            
            if max_similarity >= self.config.history_similarity_threshold:
                logger.debug(
                    f"历史结果复用: 相似度={max_similarity:.4f}, "
                    f"原查询='{self._history[max_idx].term}'"
                )
                return self._history[max_idx].result
            
            return None
            
        except Exception as e:
            logger.debug(f"历史结果复用检查失败: {e}")
            return None
    
    def _add_to_history(self, term: str, query_vector: List[float], result: FieldMappingResult) -> None:
        """
        添加到历史记录
        
        Args:
            term: 查询术语
            query_vector: 查询向量
            result: 映射结果
        """
        if not self.config.enable_history_reuse:
            return
        
        try:
            # 创建历史记录
            entry = HistoryEntry(
                term=term,
                query_vector=query_vector,
                result=result,
                timestamp=time.time()
            )
            
            # 添加到历史
            self._history.append(entry)
            
            # 更新历史向量矩阵
            new_vector = np.array(query_vector).reshape(1, -1)
            if self._history_vectors is None:
                self._history_vectors = new_vector
            else:
                self._history_vectors = np.vstack([self._history_vectors, new_vector])
            
            # 限制历史大小
            if len(self._history) > self.config.max_history_size:
                # 移除最旧的记录
                self._history = self._history[-self.config.max_history_size:]
                self._history_vectors = self._history_vectors[-self.config.max_history_size:]
                
        except Exception as e:
            logger.debug(f"添加历史记录失败: {e}")
    
    def _disambiguate(
        self,
        term: str,
        context: Optional[str],
        results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """
        使用元数据消歧
        
        使用 sample_values, category, description 区分相似字段
        
        Args:
            term: 业务术语
            context: 上下文
            results: 检索结果
        
        Returns:
            消歧后的结果（按相关性排序）
        """
        if not results or len(results) <= 1:
            return results
        
        term_lower = term.lower()
        
        # 计算消歧分数
        scored_results = []
        for result in results:
            chunk = result.field_chunk
            bonus = 0.0
            
            # 1. 字段名精确匹配加分
            if chunk.field_name.lower() == term_lower:
                bonus += 0.2
            elif term_lower in chunk.field_name.lower():
                bonus += 0.1
            
            # 2. 字段标题匹配加分
            if chunk.field_caption.lower() == term_lower:
                bonus += 0.15
            elif term_lower in chunk.field_caption.lower():
                bonus += 0.08
            
            # 3. 样本值匹配加分
            if chunk.sample_values:
                for sample in chunk.sample_values:
                    if term_lower in str(sample).lower():
                        bonus += 0.05
                        break
            
            # 4. 上下文匹配加分
            if context:
                context_lower = context.lower()
                if chunk.category and chunk.category.lower() in context_lower:
                    bonus += 0.1
                if chunk.logical_table_caption and chunk.logical_table_caption.lower() in context_lower:
                    bonus += 0.08
            
            # 计算最终分数
            final_score = min(1.0, result.score + bonus)
            scored_results.append((result, final_score))
        
        # 按分数排序
        scored_results.sort(key=lambda x: x[1], reverse=True)
        
        # 更新分数并返回
        disambiguated = []
        for i, (result, score) in enumerate(scored_results):
            # 创建新的 RetrievalResult 以避免修改原始对象
            new_result = RetrievalResult(
                field_chunk=result.field_chunk,
                score=score,
                source=result.source,
                rank=i + 1
            )
            disambiguated.append(new_result)
        
        return disambiguated
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_mappings": self._total_mappings,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": self._cache_hits / max(1, self._total_mappings),
            "fast_path_hits": self._fast_path_hits,
            "fast_path_rate": self._fast_path_hits / max(1, self._total_mappings),
            "history_reuse_hits": self._history_reuse_hits,
            "history_reuse_rate": self._history_reuse_hits / max(1, self._total_mappings),
            "history_size": len(self._history),
        }
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._total_mappings = 0
        self._cache_hits = 0
        self._fast_path_hits = 0
        self._history_reuse_hits = 0
    
    def clear_history(self) -> None:
        """清除历史记录"""
        self._history = []
        self._history_vectors = None
    
    def map_field_fallback(
        self,
        term: str,
        context: Optional[str] = None,
        role_filter: Optional[str] = None,
        category_filter: Optional[str] = None
    ) -> FieldMappingResult:
        """
        降级模式：直接返回向量检索 top-1 结果
        
        当 LLM 不可用或超时时，上层可以调用此方法获取降级结果。
        
        Args:
            term: 业务术语
            context: 上下文信息
            role_filter: 角色过滤
            category_filter: 类别过滤
        
        Returns:
            降级的字段映射结果（向量检索 top-1）
        
        **Validates: Requirements 13.3**
        """
        start_time = time.time()
        
        if not term or not term.strip():
            return FieldMappingResult(
                term=term,
                matched_field=None,
                confidence=0.0,
                source=MappingSource.FALLBACK,
                latency_ms=0
            )
        
        term = term.strip()
        query = self._build_query(term, context)
        
        # 直接向量检索 top-1
        retrieval_results = self.field_indexer.search(
            query=query,
            top_k=1,  # 只取 top-1
            role_filter=role_filter,
            category_filter=category_filter
        )
        
        if not retrieval_results:
            return FieldMappingResult(
                term=term,
                matched_field=None,
                confidence=0.0,
                source=MappingSource.FALLBACK,
                latency_ms=int((time.time() - start_time) * 1000),
                retrieval_results=[]
            )
        
        top_result = retrieval_results[0]
        
        result = FieldMappingResult(
            term=term,
            matched_field=top_result.field_chunk.field_name,
            confidence=top_result.score,
            reasoning="LLM 降级：直接使用向量检索 top-1 结果",
            source=MappingSource.FALLBACK,
            latency_ms=int((time.time() - start_time) * 1000),
            retrieval_results=retrieval_results
        )
        
        logger.info(f"LLM 降级: term='{term}', matched='{result.matched_field}', confidence={result.confidence:.4f}")
        
        return result


__all__ = [
    "MappingSource",
    "LatencyBreakdown",
    "FieldMappingResult",
    "MappingConfig",
    "HistoryEntry",
    "SemanticMapper",
]
