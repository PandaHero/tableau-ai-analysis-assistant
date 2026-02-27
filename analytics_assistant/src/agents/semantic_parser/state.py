# -*- coding: utf-8 -*-
"""
SemanticParser 状态定义

定义 SemanticParserState TypedDict，用于 LangGraph 子图内部状态管理。

⚠️ State 序列化原则（支持 checkpoint/持久化/回放）：
- State 中只存可 JSON 化的基本类型或结构
- 复杂对象（如 Pydantic BaseModel）在存入 State 前必须调用 .model_dump()
- 从 State 读取后需要重新构造对象

字段类型约定：
- 基本类型：str, int, float, bool, None
- 容器类型：list[基本类型], dict[str, 基本类型]
- 嵌套结构：dict（已序列化的 Pydantic 对象）

字段分组：
1. 输入字段：question, chat_history, datasource_luid, current_time
2. 组件输出：intent_router_output, cache_hit, field_candidates, few_shot_examples, semantic_output
3. 筛选值确认：confirmed_filters（多轮累积）
4. 流程控制：needs_clarification, clarification_question, clarification_options, clarification_source
5. 错误处理：retry_count, error_feedback, pipeline_error, error_history, correction_abort_reason
6. 最终输出：semantic_query, parse_result
7. 调试：thinking
"""
from typing import Any, Optional
from typing_extensions import TypedDict

class SemanticParserState(TypedDict, total=False):
    """SemanticParser LangGraph 子图状态
    
    使用 TypedDict 定义，支持 LangGraph 的状态管理和 checkpoint 机制。
    所有字段都是可选的（total=False），允许渐进式状态更新。
    
    使用示例：
    ```python
    # 初始化状态
    state: SemanticParserState = {
        "question": "上个月各地区的销售额",
        "datasource_luid": "abc-123",
    }
    
    # 更新状态（节点返回部分更新）
    def intent_router_node(state: SemanticParserState) -> dict:
        return {
            "intent_router_output": {
                "intent_type": "data_query",
                "confidence": 0.95,
            }
        }
    
    # 读取复杂对象
    if state.get("semantic_output"):
        output = SemanticOutput.model_validate(state["semantic_output"])
    ```
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # 输入字段
    # ═══════════════════════════════════════════════════════════════════════
    
    question: str
    """用户问题"""
    
    chat_history: Optional[list[dict[str, Any]]]
    """对话历史，格式：[{"role": "user/assistant", "content": "..."}]"""
    
    datasource_luid: Optional[str]
    """数据源 LUID"""
    
    current_time: Optional[str]
    """当前时间（ISO 格式），用于时间表达式解析"""
    
    # ═══════════════════════════════════════════════════════════════════════
    # 组件输出（存储为 dict，非 Pydantic 对象）
    # ═══════════════════════════════════════════════════════════════════════
    
    intent_router_output: Optional[dict[str, Any]]
    """IntentRouter 输出（IntentRouterOutput 序列化后）
    
    结构：
    {
        "intent_type": "data_query" | "clarification" | "general" | "irrelevant",
        "confidence": float,  # 0-1
        "reason": str,
        "source": "L0_RULE" | "L1_MODEL" | "L2_FALLBACK"
    }
    """
    
    cache_hit: Optional[bool]
    """QueryCache 是否命中"""
    
    field_candidates: Optional[list[dict[str, Any]]]
    """FieldRetriever 输出（list[FieldCandidate] 序列化后）
    
    结构：
    [
        {
            "field_name": str,
            "field_caption": str,
            "field_type": "dimension" | "measure",  # 已合并为 role
            "data_type": str,
            "description": Optional[str],
            "sample_values": Optional[list[str]],
            "confidence": float
        }
    ]
    """
    
    few_shot_examples: Optional[list[dict[str, Any]]]
    """FewShotManager 输出（list[FewShotExample] 序列化后）
    
    结构：
    [
        {
            "id": str,
            "question": str,
            "restated_question": str,
            "what": dict,
            "where": dict,
            "how_type": str,
            "computations": Optional[list[dict]],
            "query": str,
            "datasource_luid": str,
            "accepted_count": int
        }
    ]
    """
    
    semantic_output: Optional[dict[str, Any]]
    """SemanticUnderstanding 输出（SemanticOutput 序列化后）
    
    结构：
    {
        "query_id": str,
        "parent_query_id": Optional[str],
        "restated_question": str,
        "what": {"measures": [...]},
        "where": {"dimensions": [...], "filters": [...]},
        "how_type": "SIMPLE" | "COMPLEX",
        "computations": [...],
        "needs_clarification": bool,
        "clarification_question": Optional[str],
        "clarification_options": Optional[list[str]],
        "self_check": {...}
    }
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # 筛选值确认（多轮累积）
    # ═══════════════════════════════════════════════════════════════════════
    
    confirmed_filters: Optional[list[dict[str, Any]]]
    """多轮筛选值确认累积（list[FilterConfirmation] 序列化后）
    
    用于累积多轮 interrupt() 确认的结果，防止上下文丢失。
    
    示例：
    - 第一次确认 "北京" → "北京市"
    - 第二次确认 "上海" → "上海市"
    两次确认都会保留在此列表中。
    
    结构：
    [
        {
            "field_name": str,
            "original_value": str,
            "confirmed_value": str,
            "confirmed_at": str  # ISO datetime
        }
    ]
    """
    
    filter_validation_result: Optional[dict[str, Any]]
    """FilterValueValidator 验证结果
    
    结构：
    {
        "results": [
            {
                "field_name": str,
                "requested_value": str,
                "is_valid": bool,
                "similar_values": list[str],
                "needs_confirmation": bool,
                "is_unresolvable": bool,
                "message": Optional[str]
            }
        ],
        "all_valid": bool,
        "has_unresolvable_filters": bool,
        "needs_confirmation": bool
    }
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # 流程控制
    # ═══════════════════════════════════════════════════════════════════════
    
    needs_clarification: Optional[bool]
    """是否需要用户澄清"""
    
    clarification_question: Optional[str]
    """澄清问题（当 needs_clarification=True 时）"""
    
    clarification_options: Optional[list[str]]
    """澄清选项列表（供用户选择）"""
    
    clarification_source: Optional[str]
    """澄清请求来源：semantic_understanding | filter_validator"""
    
    # ═══════════════════════════════════════════════════════════════════════
    # 错误处理
    # ═══════════════════════════════════════════════════════════════════════
    
    retry_count: Optional[int]
    """当前重试次数（最大 3 次）"""
    
    error_feedback: Optional[str]
    """传递给重试步骤的错误反馈信息"""
    
    pipeline_error: Optional[dict[str, Any]]
    """管道执行错误（QueryError 序列化后）
    
    结构：
    {
        "error_type": str,
        "message": str,
        "details": Optional[dict],
        "is_retryable": bool
    }
    """
    
    error_history: Optional[list[dict[str, Any]]]
    """错误历史记录（用于检测重复错误和交替错误模式）
    
    结构：
    [
        {
            "error_hash": str,  # 错误的规范化哈希
            "error_type": str,
            "message": str,
            "occurred_at": str  # ISO datetime
        }
    ]
    """
    
    correction_abort_reason: Optional[str]
    """错误修正终止原因
    
    可能的值：
    - "max_retries_exceeded": 超过最大重试次数
    - "duplicate_error": 相同错误出现 2 次
    - "alternating_errors": 检测到交替错误模式 (A→B→A→B)
    - "non_retryable_error": 不可重试的错误类型
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # 最终输出
    # ═══════════════════════════════════════════════════════════════════════
    
    semantic_query: Optional[dict[str, Any]]
    """QueryAdapter 输出的最终查询（VizQL 或 SQL）
    
    结构取决于目标平台，VizQL 示例：
    {
        "columns": [...],
        "rows": [...],
        "filters": [...],
        "calculated_fields": [...]
    }
    """
    
    parse_result: Optional[dict[str, Any]]
    """解析结果汇总
    
    结构：
    {
        "success": bool,
        "query_id": str,
        "semantic_output": dict,
        "query": Optional[dict],
        "error": Optional[dict]
    }
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # 调试
    # ═══════════════════════════════════════════════════════════════════════
    
    thinking: Optional[str]
    """LLM 思考过程（来自 R1 等推理模型）"""
    
    # ═══════════════════════════════════════════════════════════════════════
    # 语义解析优化字段
    # ═══════════════════════════════════════════════════════════════════════
    
    prefilter_result: Optional[dict[str, Any]]
    """RulePrefilter 输出（PrefilterResult 序列化后）
    
    结构：
    {
        "time_hints": [{"original_expression": str, "hint_type": str, "parsed_hint": str, "confidence": float}],
        "matched_computations": [{"seed_name": str, "display_name": str, "calc_type": str, "formula": str}],
        "detected_complexity": ["simple" | "ratio" | "time_compare" | ...],
        "detected_language": "zh" | "en" | "ja",
        "match_confidence": float,
        "low_confidence": bool
    }
    """
    
    feature_extraction_output: Optional[dict[str, Any]]
    """FeatureExtractor 输出（FeatureExtractionOutput 序列化后）
    
    结构：
    {
        "required_measures": [str],
        "required_dimensions": [str],
        "confirmed_time_hints": [str],
        "confirmed_computations": [str | dict],
        "confirmation_confidence": float,
        "is_degraded": bool
    }
    """
    
    field_rag_result: Optional[dict[str, Any]]
    """FieldRetriever 输出（FieldRAGResult 序列化后）
    
    结构：
    {
        "measures": [FieldCandidate],
        "dimensions": [FieldCandidate],
        "time_fields": [FieldCandidate]
    }
    """
    
    dynamic_schema_result: Optional[dict[str, Any]]
    """DynamicSchemaBuilder 输出
    
    结构：
    {
        "field_candidates": [FieldCandidate],
        "modules": ["base", "time", "computation", ...],
        "computation_types": [str],
        "time_expressions": [str]
    }
    """
    
    modular_prompt: Optional[str]
    """ModularPromptBuilder 输出的增强 Prompt"""
    
    validation_result: Optional[dict[str, Any]]
    """OutputValidator 输出（ValidationResult 序列化后）
    
    结构：
    {
        "is_valid": bool,
        "errors": [{"error_type": str, "field_name": str, "message": str, "auto_correctable": bool}],
        "corrected_output": Optional[dict],
        "needs_clarification": bool,
        "clarification_message": Optional[str]
    }
    """
    
    is_degraded: Optional[bool]
    """是否处于降级模式（FeatureExtractor 超时等）"""
    
    optimization_metrics: Optional[dict[str, Any]]
    """语义解析优化性能指标
    
    结构：
    {
        "rule_prefilter_ms": float,
        "feature_extractor_ms": float,
        "field_retriever_ms": float,
        "dynamic_schema_builder_ms": float,
        "modular_prompt_builder_ms": float,
        "output_validator_ms": float,
        "total_optimization_ms": float,
        "feature_cache_hit": bool,
        "token_reduction_percent": float
    }
    """

__all__ = ["SemanticParserState"]
