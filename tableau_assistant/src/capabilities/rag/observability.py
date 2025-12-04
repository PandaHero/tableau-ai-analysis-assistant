"""
RAG 可观测性模块

提供 RAG 系统的日志、指标和调试功能。

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**

主要功能：
- 检索日志：记录 query text, candidate count, top-3 scores, latency
- Rerank 日志：记录 before/after rankings 和 score changes
- 错误日志：详细错误信息（query, stage, stack trace）
- verbose 模式：step-by-step trace output
- 指标暴露：avg_retrieval_latency, cache_hit_rate, llm_skip_rate
"""
import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
from enum import Enum
from contextlib import contextmanager
from functools import wraps

logger = logging.getLogger(__name__)


class RAGStage(Enum):
    """RAG 处理阶段"""
    EMBEDDING = "embedding"
    RETRIEVAL = "retrieval"
    RERANK = "rerank"
    DISAMBIGUATION = "disambiguation"
    LLM = "llm"
    CACHE = "cache"


@dataclass
class RetrievalLogEntry:
    """
    检索日志条目
    
    **Validates: Requirements 8.1**
    
    Attributes:
        query_text: 查询文本
        candidate_count: 候选数量
        top_scores: top-3 分数
        latency_ms: 延迟（毫秒）
        source: 检索来源
        timestamp: 时间戳
    """
    query_text: str
    candidate_count: int
    top_scores: List[float]
    latency_ms: int
    source: str = "vector"
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_text": self.query_text,
            "candidate_count": self.candidate_count,
            "top_scores": self.top_scores,
            "latency_ms": self.latency_ms,
            "source": self.source,
            "timestamp": self.timestamp,
        }
    
    def __str__(self) -> str:
        scores_str = ", ".join(f"{s:.4f}" for s in self.top_scores[:3])
        return (
            f"Retrieval: query='{self.query_text[:50]}...', "
            f"candidates={self.candidate_count}, "
            f"top_scores=[{scores_str}], "
            f"latency={self.latency_ms}ms"
        )


@dataclass
class RerankLogEntry:
    """
    Rerank 日志条目
    
    **Validates: Requirements 8.2**
    
    Attributes:
        query_text: 查询文本
        before_ranking: 重排序前的排名
        after_ranking: 重排序后的排名
        score_changes: 分数变化
        latency_ms: 延迟（毫秒）
        reranker_type: 重排序器类型
        timestamp: 时间戳
    """
    query_text: str
    before_ranking: List[str]  # field names
    after_ranking: List[str]   # field names
    score_changes: Dict[str, float]  # field_name -> score_change
    latency_ms: int
    reranker_type: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_text": self.query_text,
            "before_ranking": self.before_ranking,
            "after_ranking": self.after_ranking,
            "score_changes": self.score_changes,
            "latency_ms": self.latency_ms,
            "reranker_type": self.reranker_type,
            "timestamp": self.timestamp,
        }
    
    def __str__(self) -> str:
        changes = [f"{k}: {v:+.4f}" for k, v in list(self.score_changes.items())[:3]]
        return (
            f"Rerank ({self.reranker_type}): "
            f"before={self.before_ranking[:3]}, "
            f"after={self.after_ranking[:3]}, "
            f"changes=[{', '.join(changes)}], "
            f"latency={self.latency_ms}ms"
        )


@dataclass
class ErrorLogEntry:
    """
    错误日志条目
    
    **Validates: Requirements 8.3**
    
    Attributes:
        query_text: 查询文本
        stage: 发生错误的阶段
        error_message: 错误信息
        stack_trace: 堆栈跟踪
        timestamp: 时间戳
    """
    query_text: str
    stage: RAGStage
    error_message: str
    stack_trace: str
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_text": self.query_text,
            "stage": self.stage.value,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "timestamp": self.timestamp,
        }
    
    def __str__(self) -> str:
        return (
            f"Error at {self.stage.value}: "
            f"query='{self.query_text[:50]}...', "
            f"error='{self.error_message}'"
        )


@dataclass
class RAGMetrics:
    """
    RAG 指标（增强版）
    
    **Validates: Requirements 8.5**
    
    Attributes:
        total_queries: 总查询数
        total_retrieval_latency_ms: 总检索延迟
        cache_hits: 缓存命中数
        llm_skips: LLM 跳过数（高置信度快速路径）
        errors: 错误数
        
        # 增强指标
        total_embedding_latency_ms: 总向量化延迟
        total_rerank_latency_ms: 总重排序延迟
        total_disambiguation_latency_ms: 总消歧延迟
        rerank_count: 重排序次数
        history_reuse_hits: 历史结果复用次数
        fallback_count: 降级次数
        high_confidence_count: 高置信度匹配次数
        low_confidence_count: 低置信度匹配次数
        
        # 分位数统计
        latency_samples: 延迟样本（用于计算分位数）
        max_latency_ms: 最大延迟
        min_latency_ms: 最小延迟
    """
    total_queries: int = 0
    total_retrieval_latency_ms: int = 0
    cache_hits: int = 0
    llm_skips: int = 0
    errors: int = 0
    
    # 增强指标
    total_embedding_latency_ms: int = 0
    total_rerank_latency_ms: int = 0
    total_disambiguation_latency_ms: int = 0
    rerank_count: int = 0
    history_reuse_hits: int = 0
    fallback_count: int = 0
    high_confidence_count: int = 0
    low_confidence_count: int = 0
    
    # 分位数统计
    latency_samples: List[int] = field(default_factory=list)
    max_latency_ms: int = 0
    min_latency_ms: int = 0
    
    # 内部配置
    _max_samples: int = field(default=1000, repr=False)
    
    @property
    def avg_retrieval_latency(self) -> float:
        """平均检索延迟（毫秒）"""
        if self.total_queries == 0:
            return 0.0
        return self.total_retrieval_latency_ms / self.total_queries
    
    @property
    def avg_embedding_latency(self) -> float:
        """平均向量化延迟（毫秒）"""
        if self.total_queries == 0:
            return 0.0
        return self.total_embedding_latency_ms / self.total_queries
    
    @property
    def avg_rerank_latency(self) -> float:
        """平均重排序延迟（毫秒）"""
        if self.rerank_count == 0:
            return 0.0
        return self.total_rerank_latency_ms / self.rerank_count
    
    @property
    def cache_hit_rate(self) -> float:
        """缓存命中率"""
        if self.total_queries == 0:
            return 0.0
        return self.cache_hits / self.total_queries
    
    @property
    def llm_skip_rate(self) -> float:
        """LLM 跳过率"""
        if self.total_queries == 0:
            return 0.0
        return self.llm_skips / self.total_queries
    
    @property
    def rerank_rate(self) -> float:
        """重排序率"""
        if self.total_queries == 0:
            return 0.0
        return self.rerank_count / self.total_queries
    
    @property
    def history_reuse_rate(self) -> float:
        """历史结果复用率"""
        if self.total_queries == 0:
            return 0.0
        return self.history_reuse_hits / self.total_queries
    
    @property
    def fallback_rate(self) -> float:
        """降级率"""
        if self.total_queries == 0:
            return 0.0
        return self.fallback_count / self.total_queries
    
    @property
    def high_confidence_rate(self) -> float:
        """高置信度匹配率"""
        if self.total_queries == 0:
            return 0.0
        return self.high_confidence_count / self.total_queries
    
    @property
    def error_rate(self) -> float:
        """错误率"""
        if self.total_queries == 0:
            return 0.0
        return self.errors / self.total_queries
    
    @property
    def p50_latency(self) -> float:
        """P50 延迟（毫秒）"""
        return self._percentile(50)
    
    @property
    def p90_latency(self) -> float:
        """P90 延迟（毫秒）"""
        return self._percentile(90)
    
    @property
    def p99_latency(self) -> float:
        """P99 延迟（毫秒）"""
        return self._percentile(99)
    
    def _percentile(self, p: int) -> float:
        """计算分位数"""
        if not self.latency_samples:
            return 0.0
        sorted_samples = sorted(self.latency_samples)
        idx = int(len(sorted_samples) * p / 100)
        idx = min(idx, len(sorted_samples) - 1)
        return float(sorted_samples[idx])
    
    def record_latency(self, latency_ms: int) -> None:
        """记录延迟样本"""
        self.latency_samples.append(latency_ms)
        if len(self.latency_samples) > self._max_samples:
            self.latency_samples = self.latency_samples[-self._max_samples:]
        
        if self.max_latency_ms == 0 or latency_ms > self.max_latency_ms:
            self.max_latency_ms = latency_ms
        if self.min_latency_ms == 0 or latency_ms < self.min_latency_ms:
            self.min_latency_ms = latency_ms
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            # 基础指标
            "total_queries": self.total_queries,
            "errors": self.errors,
            "error_rate": self.error_rate,
            
            # 延迟指标
            "avg_retrieval_latency": self.avg_retrieval_latency,
            "avg_embedding_latency": self.avg_embedding_latency,
            "avg_rerank_latency": self.avg_rerank_latency,
            "p50_latency": self.p50_latency,
            "p90_latency": self.p90_latency,
            "p99_latency": self.p99_latency,
            "max_latency_ms": self.max_latency_ms,
            "min_latency_ms": self.min_latency_ms,
            
            # 缓存和优化指标
            "cache_hit_rate": self.cache_hit_rate,
            "llm_skip_rate": self.llm_skip_rate,
            "history_reuse_rate": self.history_reuse_rate,
            "rerank_rate": self.rerank_rate,
            "fallback_rate": self.fallback_rate,
            "high_confidence_rate": self.high_confidence_rate,
            
            # 原始计数
            "cache_hits": self.cache_hits,
            "llm_skips": self.llm_skips,
            "rerank_count": self.rerank_count,
            "history_reuse_hits": self.history_reuse_hits,
            "fallback_count": self.fallback_count,
            "high_confidence_count": self.high_confidence_count,
            "low_confidence_count": self.low_confidence_count,
        }
    
    def to_summary(self) -> str:
        """生成简洁的性能摘要"""
        return (
            f"RAG Metrics Summary:\n"
            f"  Queries: {self.total_queries}, Errors: {self.errors} ({self.error_rate:.1%})\n"
            f"  Latency: avg={self.avg_retrieval_latency:.0f}ms, "
            f"p50={self.p50_latency:.0f}ms, p90={self.p90_latency:.0f}ms, p99={self.p99_latency:.0f}ms\n"
            f"  Cache Hit: {self.cache_hit_rate:.1%}, LLM Skip: {self.llm_skip_rate:.1%}, "
            f"History Reuse: {self.history_reuse_rate:.1%}\n"
            f"  High Confidence: {self.high_confidence_rate:.1%}, Fallback: {self.fallback_rate:.1%}"
        )
    
    def reset(self) -> None:
        """重置指标"""
        self.total_queries = 0
        self.total_retrieval_latency_ms = 0
        self.cache_hits = 0
        self.llm_skips = 0
        self.errors = 0
        self.total_embedding_latency_ms = 0
        self.total_rerank_latency_ms = 0
        self.total_disambiguation_latency_ms = 0
        self.rerank_count = 0
        self.history_reuse_hits = 0
        self.fallback_count = 0
        self.high_confidence_count = 0
        self.low_confidence_count = 0
        self.latency_samples.clear()
        self.max_latency_ms = 0
        self.min_latency_ms = 0


class RAGObserver:
    """
    RAG 可观测性管理器
    
    提供统一的日志、指标和调试接口。
    
    **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**
    """
    
    def __init__(self, verbose: bool = False, max_log_entries: int = 1000):
        """
        初始化观察器
        
        Args:
            verbose: 是否启用详细输出模式
            max_log_entries: 最大日志条目数
        """
        self.verbose = verbose
        self.max_log_entries = max_log_entries
        
        # 日志存储
        self._retrieval_logs: List[RetrievalLogEntry] = []
        self._rerank_logs: List[RerankLogEntry] = []
        self._error_logs: List[ErrorLogEntry] = []
        
        # 指标
        self._metrics = RAGMetrics()
        
        # 回调函数
        self._on_retrieval: Optional[Callable[[RetrievalLogEntry], None]] = None
        self._on_rerank: Optional[Callable[[RerankLogEntry], None]] = None
        self._on_error: Optional[Callable[[ErrorLogEntry], None]] = None

    def set_verbose(self, verbose: bool) -> None:
        """
        设置 verbose 模式
        
        **Validates: Requirements 8.4**
        
        Args:
            verbose: 是否启用详细输出
        """
        self.verbose = verbose
    
    def log_retrieval(
        self,
        query_text: str,
        candidate_count: int,
        top_scores: List[float],
        latency_ms: int,
        source: str = "vector"
    ) -> RetrievalLogEntry:
        """
        记录检索日志
        
        **Validates: Requirements 8.1**
        
        Args:
            query_text: 查询文本
            candidate_count: 候选数量
            top_scores: top-3 分数
            latency_ms: 延迟（毫秒）
            source: 检索来源
        
        Returns:
            日志条目
        """
        entry = RetrievalLogEntry(
            query_text=query_text,
            candidate_count=candidate_count,
            top_scores=top_scores[:3],
            latency_ms=latency_ms,
            source=source,
        )
        
        # 存储日志
        self._retrieval_logs.append(entry)
        if len(self._retrieval_logs) > self.max_log_entries:
            self._retrieval_logs = self._retrieval_logs[-self.max_log_entries:]
        
        # 更新指标
        self._metrics.total_queries += 1
        self._metrics.total_retrieval_latency_ms += latency_ms
        
        # 输出日志
        if self.verbose:
            logger.info(str(entry))
        else:
            logger.debug(str(entry))
        
        # 回调
        if self._on_retrieval:
            self._on_retrieval(entry)
        
        return entry
    
    def log_rerank(
        self,
        query_text: str,
        before_ranking: List[str],
        after_ranking: List[str],
        before_scores: Dict[str, float],
        after_scores: Dict[str, float],
        latency_ms: int,
        reranker_type: str = "unknown"
    ) -> RerankLogEntry:
        """
        记录 Rerank 日志
        
        **Validates: Requirements 8.2**
        
        Args:
            query_text: 查询文本
            before_ranking: 重排序前的排名
            after_ranking: 重排序后的排名
            before_scores: 重排序前的分数
            after_scores: 重排序后的分数
            latency_ms: 延迟（毫秒）
            reranker_type: 重排序器类型
        
        Returns:
            日志条目
        """
        # 计算分数变化
        score_changes = {}
        for field_name in after_ranking:
            before = before_scores.get(field_name, 0.0)
            after = after_scores.get(field_name, 0.0)
            score_changes[field_name] = after - before
        
        entry = RerankLogEntry(
            query_text=query_text,
            before_ranking=before_ranking,
            after_ranking=after_ranking,
            score_changes=score_changes,
            latency_ms=latency_ms,
            reranker_type=reranker_type,
        )
        
        # 存储日志
        self._rerank_logs.append(entry)
        if len(self._rerank_logs) > self.max_log_entries:
            self._rerank_logs = self._rerank_logs[-self.max_log_entries:]
        
        # 输出日志
        if self.verbose:
            logger.info(str(entry))
        else:
            logger.debug(str(entry))
        
        # 回调
        if self._on_rerank:
            self._on_rerank(entry)
        
        return entry
    
    def log_error(
        self,
        query_text: str,
        stage: RAGStage,
        error: Exception
    ) -> ErrorLogEntry:
        """
        记录错误日志
        
        **Validates: Requirements 8.3**
        
        Args:
            query_text: 查询文本
            stage: 发生错误的阶段
            error: 异常对象
        
        Returns:
            日志条目
        """
        entry = ErrorLogEntry(
            query_text=query_text,
            stage=stage,
            error_message=str(error),
            stack_trace=traceback.format_exc(),
        )
        
        # 存储日志
        self._error_logs.append(entry)
        if len(self._error_logs) > self.max_log_entries:
            self._error_logs = self._error_logs[-self.max_log_entries:]
        
        # 更新指标
        self._metrics.errors += 1
        
        # 输出日志
        logger.error(f"{entry}\n{entry.stack_trace}")
        
        # 回调
        if self._on_error:
            self._on_error(entry)
        
        return entry
    
    def log_cache_hit(self) -> None:
        """记录缓存命中"""
        self._metrics.cache_hits += 1
        if self.verbose:
            logger.info("Cache hit")
    
    def log_llm_skip(self) -> None:
        """记录 LLM 跳过（高置信度快速路径）"""
        self._metrics.llm_skips += 1
        if self.verbose:
            logger.info("LLM skipped (high confidence fast path)")
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        获取指标
        
        **Validates: Requirements 8.5**
        
        Returns:
            指标字典
        """
        return self._metrics.to_dict()
    
    def get_retrieval_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取检索日志"""
        return [e.to_dict() for e in self._retrieval_logs[-limit:]]
    
    def get_rerank_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取 Rerank 日志"""
        return [e.to_dict() for e in self._rerank_logs[-limit:]]
    
    def get_error_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取错误日志"""
        return [e.to_dict() for e in self._error_logs[-limit:]]
    
    def reset(self) -> None:
        """重置所有日志和指标"""
        self._retrieval_logs.clear()
        self._rerank_logs.clear()
        self._error_logs.clear()
        self._metrics.reset()
    
    def on_retrieval(self, callback: Callable[[RetrievalLogEntry], None]) -> None:
        """设置检索回调"""
        self._on_retrieval = callback
    
    def on_rerank(self, callback: Callable[[RerankLogEntry], None]) -> None:
        """设置 Rerank 回调"""
        self._on_rerank = callback
    
    def on_error(self, callback: Callable[[ErrorLogEntry], None]) -> None:
        """设置错误回调"""
        self._on_error = callback
    
    @contextmanager
    def trace(self, stage: RAGStage, query_text: str = ""):
        """
        跟踪上下文管理器
        
        **Validates: Requirements 8.4**
        
        用于 verbose 模式下的 step-by-step 跟踪。
        
        Args:
            stage: 处理阶段
            query_text: 查询文本
        
        Yields:
            开始时间
        """
        start_time = time.time()
        
        if self.verbose:
            logger.info(f"[TRACE] Starting {stage.value}: {query_text[:50]}...")
        
        try:
            yield start_time
        except Exception as e:
            self.log_error(query_text, stage, e)
            raise
        finally:
            elapsed_ms = int((time.time() - start_time) * 1000)
            if self.verbose:
                logger.info(f"[TRACE] Completed {stage.value}: {elapsed_ms}ms")


# 全局观察器实例
_global_observer: Optional[RAGObserver] = None


def get_observer() -> RAGObserver:
    """获取全局观察器实例"""
    global _global_observer
    if _global_observer is None:
        _global_observer = RAGObserver()
    return _global_observer


def set_verbose(verbose: bool) -> None:
    """设置全局 verbose 模式"""
    get_observer().set_verbose(verbose)


def observe_retrieval(func: Callable) -> Callable:
    """
    检索观察装饰器
    
    自动记录检索日志。
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        observer = get_observer()
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            
            # 尝试从结果中提取信息
            if hasattr(result, '__len__'):
                candidate_count = len(result)
                top_scores = []
                if candidate_count > 0 and hasattr(result[0], 'score'):
                    top_scores = [r.score for r in result[:3]]
            else:
                candidate_count = 0
                top_scores = []
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # 尝试获取查询文本
            query_text = kwargs.get('query', str(args[0]) if args else "unknown")
            
            observer.log_retrieval(
                query_text=query_text,
                candidate_count=candidate_count,
                top_scores=top_scores,
                latency_ms=latency_ms,
            )
            
            return result
            
        except Exception as e:
            query_text = kwargs.get('query', str(args[0]) if args else "unknown")
            observer.log_error(query_text, RAGStage.RETRIEVAL, e)
            raise
    
    return wrapper


__all__ = [
    "RAGStage",
    "RetrievalLogEntry",
    "RerankLogEntry",
    "ErrorLogEntry",
    "RAGMetrics",
    "RAGObserver",
    "get_observer",
    "set_verbose",
    "observe_retrieval",
]
