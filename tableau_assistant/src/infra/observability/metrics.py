"""Semantic Parser Metrics - Basic observability for the parser.

This module defines the SemanticParserMetrics dataclass and helper functions
for passing metrics through RunnableConfig.

Design principles (Requirements 0.5):
- Metrics are passed through RunnableConfig.configurable["metrics"]
- Metrics do NOT enter State (to avoid serialization issues)
- Metrics are serialized to dict at subgraph exit for logging/monitoring
- Supports both simple increment and counter-style patterns

Usage:
    # In component
    from tableau_assistant.src.infra.observability import get_metrics_from_config
    
    metrics = get_metrics_from_config(config)
    metrics.step1_ms = 100
    metrics.step1_call_count += 1
    
    # At subgraph exit
    logger.info("SemanticParser completed", extra={"metrics": metrics.to_dict()})
"""

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

# Type alias for RunnableConfig (avoid circular import)
RunnableConfig = Dict[str, Any]


@dataclass
class SemanticParserMetrics:
    """Semantic Parser metrics for observability.
    
    ⚠️ Important: This object does NOT enter State.
    It's passed through RunnableConfig as a runtime object.
    At subgraph exit, call to_dict() to serialize for logging.
    
    Attributes:
        # Timing (milliseconds)
        preprocess_ms: Preprocess layer execution time
        schema_linking_ms: Schema linking execution time
        step1_ms: Step1 execution time
        step2_ms: Step2 execution time
        pipeline_ms: Pipeline (MapFields + BuildQuery + ExecuteQuery) time
        total_ms: Total semantic parser execution time
        
        # Token counts
        step1_prompt_tokens: Step1 prompt token count
        step1_completion_tokens: Step1 completion token count
        step2_prompt_tokens: Step2 prompt token count
        step2_completion_tokens: Step2 completion token count
        
        # LLM call counts
        step1_call_count: Number of Step1 LLM calls (including retries)
        step2_call_count: Number of Step2 LLM calls (including retries)
        react_call_count: Number of ReAct LLM calls
        
        # Truncation flags
        history_truncated: Whether history was truncated
        schema_truncated: Whether schema was truncated
        history_truncation_count: Number of history truncations
        schema_truncation_count: Number of schema truncations
        
        # Retry counts
        step1_parse_retry_count: Step1 format parse retry count
        step2_parse_retry_count: Step2 format parse retry count
        
        # Cache hits
        schema_cache_hit: Whether schema linking cache was hit
        field_mapping_cache_hit: Whether field mapping cache was hit
    
    Requirements: 0.5 - 基础可观测性
    """
    
    # Timing (milliseconds)
    preprocess_ms: int = 0
    schema_linking_ms: int = 0
    step1_ms: int = 0
    step2_ms: int = 0
    pipeline_ms: int = 0
    total_ms: int = 0
    
    # Token counts
    step1_prompt_tokens: int = 0
    step1_completion_tokens: int = 0
    step2_prompt_tokens: int = 0
    step2_completion_tokens: int = 0
    
    # LLM call counts
    step1_call_count: int = 0
    step2_call_count: int = 0
    react_call_count: int = 0
    
    # Truncation flags
    history_truncated: bool = False
    schema_truncated: bool = False
    history_truncation_count: int = 0
    schema_truncation_count: int = 0
    
    # Retry counts
    step1_parse_retry_count: int = 0
    step2_parse_retry_count: int = 0

    # 结构化重试原因（Requirements 0.6）
    # 约定 key 示例："json_parse" / "pydantic_validation" / "value_error" / "execution_error" 等
    step1_parse_retry_reason_counts: Dict[str, int] = field(default_factory=dict)
    step2_parse_retry_reason_counts: Dict[str, int] = field(default_factory=dict)
    semantic_retry_reason_counts: Dict[str, int] = field(default_factory=dict)

    # Cache hits
    schema_cache_hit: bool = False
    field_mapping_cache_hit: bool = False
    
    # JSON 解析指标（Requirements 0.7）
    json_direct_parse_success_count: int = 0  # 直接解析成功次数
    json_repair_success_count: int = 0  # json_repair/修复尝试成功次数
    json_parse_failure_count: int = 0  # JSON 解析失败次数
    pydantic_validation_failure_count: int = 0  # Pydantic 校验失败次数
    json_mode_fallback_count: int = 0  # JSON Mode 降级次数

    # JSON 指标按 Provider 分类（Requirements 0.7）
    json_direct_parse_success_by_provider: Dict[str, int] = field(default_factory=dict)
    json_repair_success_by_provider: Dict[str, int] = field(default_factory=dict)
    json_parse_failure_by_provider: Dict[str, int] = field(default_factory=dict)
    pydantic_validation_failure_by_provider: Dict[str, int] = field(default_factory=dict)
    json_mode_fallback_by_provider: Dict[str, int] = field(default_factory=dict)

    # JSON 修复尝试类型统计（Requirements 0.7）
    # key 示例："remove_trailing_commas" / "normalize_quotes" / "close_unbalanced_braces" / "json_repair_lib"
    json_repair_attempt_type_attempt_counts: Dict[str, int] = field(default_factory=dict)
    json_repair_attempt_type_success_counts: Dict[str, int] = field(default_factory=dict)
    
    # Tool calls 解析指标（Requirements 0.8）

    tool_args_parse_failure_count: int = 0  # tool_calls 参数解析失败次数
    tool_args_repair_success_count: int = 0  # tool_calls 参数修复成功次数
    
    # LLM 空响应指标（Requirements 0.9）
    llm_empty_response_count: int = 0  # LLM 返回空响应次数
    
    # Middleware 钩子失败指标（Requirements 0.11）
    middleware_hook_failure_count: int = 0  # middleware 钩子执行失败次数
    middleware_hook_failure_by_hook: Dict[str, int] = field(default_factory=dict)  # 按钩子类型分类
    middleware_hook_failure_by_middleware: Dict[str, int] = field(default_factory=dict)  # 按 middleware 分类
    
    # IntentRouter 指标（Requirements 0.12）
    intent_router_l0_hit_count: int = 0  # L0 规则层命中次数
    intent_router_l1_call_count: int = 0  # L1 小模型分类调用次数（用于计算调用率）
    intent_router_l1_hit_count: int = 0  # L1 小模型分类命中次数（置信度达标）
    intent_router_l2_fallback_count: int = 0  # L2 Step1 兜底次数
    
    # Schema Linking 回退指标（Requirements 0.13）
    schema_linking_fallback_count: int = 0  # Schema Linking 回退总次数
    schema_linking_fallback_by_reason: Dict[str, int] = field(default_factory=dict)  # 按原因分类
    # 原因 key: "empty_candidates" / "low_confidence" / "timeout" / "error" /
    #          "low_coverage_score_spread" / "low_coverage_term_hit" / "low_coverage_avg_score"
    
    # Start time for total_ms calculation
    _start_time: float = field(default_factory=time.monotonic, repr=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to JSON-compatible dict for logging/monitoring.
        
        Excludes internal fields (prefixed with _).
        
        Returns:
            Dict with all metric values
        """
        result = asdict(self)
        # Remove internal fields
        result.pop("_start_time", None)
        return result
    
    def finalize(self) -> None:
        """Finalize metrics by calculating total_ms.
        
        Call this at subgraph exit to set total_ms.
        """
        self.total_ms = int((time.monotonic() - self._start_time) * 1000)
    
    def record_step1_timing(self, start_time: float) -> None:
        """Record Step1 execution time.
        
        Args:
            start_time: time.monotonic() value at start
        """
        self.step1_ms = int((time.monotonic() - start_time) * 1000)
    
    def record_step2_timing(self, start_time: float) -> None:
        """Record Step2 execution time.
        
        Args:
            start_time: time.monotonic() value at start
        """
        self.step2_ms = int((time.monotonic() - start_time) * 1000)
    
    def record_pipeline_timing(self, start_time: float) -> None:
        """Record Pipeline execution time.
        
        Args:
            start_time: time.monotonic() value at start
        """
        self.pipeline_ms = int((time.monotonic() - start_time) * 1000)
    
    def record_step1_tokens(
        self,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record Step1 token usage.
        
        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
        """
        self.step1_prompt_tokens += prompt_tokens
        self.step1_completion_tokens += completion_tokens
        self.step1_call_count += 1
    
    def record_step2_tokens(
        self,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record Step2 token usage.
        
        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
        """
        self.step2_prompt_tokens += prompt_tokens
        self.step2_completion_tokens += completion_tokens
        self.step2_call_count += 1


def get_metrics_from_config(config: Optional[RunnableConfig]) -> SemanticParserMetrics:
    """Get metrics object from RunnableConfig.
    
    If metrics doesn't exist in config, returns a new instance.
    
    Args:
        config: LangGraph RunnableConfig
        
    Returns:
        SemanticParserMetrics instance
        
    Requirements: 0.5 - Metrics 通过 RunnableConfig 传递
    """
    if config is None:
        return SemanticParserMetrics()
    
    configurable = config.get("configurable", {})
    metrics = configurable.get("metrics")
    
    if metrics is None:
        return SemanticParserMetrics()
    
    return metrics


def set_metrics_to_config(
    config: Optional[RunnableConfig],
    metrics: SemanticParserMetrics,
) -> RunnableConfig:
    """Set metrics object to RunnableConfig.
    
    Creates a new config dict with metrics in configurable.
    
    Args:
        config: LangGraph RunnableConfig (can be None)
        metrics: SemanticParserMetrics instance
        
    Returns:
        New RunnableConfig with metrics set
        
    Requirements: 0.5 - Metrics 通过 RunnableConfig 传递
    """
    if config is None:
        config = {}
    
    configurable = dict(config.get("configurable", {}))
    configurable["metrics"] = metrics
    
    return {**config, "configurable": configurable}


def ensure_metrics_in_config(config: Optional[RunnableConfig]) -> RunnableConfig:
    """Ensure metrics exists in config, creating if necessary.
    
    This is useful at subgraph entry to ensure metrics is available.
    
    Args:
        config: LangGraph RunnableConfig (can be None)
        
    Returns:
        RunnableConfig with metrics guaranteed to exist
        
    Requirements: 0.5 - Metrics 通过 RunnableConfig 传递
    """
    if config is None:
        config = {}
    
    configurable = config.get("configurable", {})
    
    if "metrics" not in configurable or configurable["metrics"] is None:
        metrics = SemanticParserMetrics()
        return set_metrics_to_config(config, metrics)
    
    return config


__all__ = [
    "SemanticParserMetrics",
    "get_metrics_from_config",
    "set_metrics_to_config",
    "ensure_metrics_in_config",
]
