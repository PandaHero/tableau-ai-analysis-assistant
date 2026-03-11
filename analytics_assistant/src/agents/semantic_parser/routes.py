# -*- coding: utf-8 -*-
"""
SemanticParser 路由函数

LangGraph 条件边的路由逻辑。
"""
from .state import SemanticParserState
from .components import IntentType

def route_by_intent(state: SemanticParserState) -> str:
    """根据意图类型路由

    Returns:
        - "data_query": 数据查询，继续处理
        - "general": 元数据问答，直接返回
        - "irrelevant": 无关问题，直接返回
        - "clarification": 需要澄清，直接返回
    """
    intent = state.get("intent_router_output", {})
    intent_type = intent.get("intent_type", IntentType.DATA_QUERY.value)

    # 转换为字符串（兼容枚举和字符串）
    if hasattr(intent_type, 'value'):
        intent_type = intent_type.value

    return intent_type

def route_by_cache(state: SemanticParserState) -> str:
    """根据缓存命中情况路由"""
    if state.get("cache_hit"):
        return "cache_hit"
    return "cache_miss"

def route_after_understanding(state: SemanticParserState) -> str:
    """语义理解后的路由"""
    if state.get("needs_clarification"):
        return "needs_clarification"
    return "continue"

def route_after_query(state: SemanticParserState) -> str:
    """查询执行后的路由"""
    if state.get("pipeline_error"):
        return "error"
    return "success"

def route_after_correction(state: SemanticParserState) -> str:
    """错误修正后的路由

    - correction_abort_reason: 修正器主动终止（重复错误、超限等）
    - pipeline_error 仍存在: 修正器未能清除错误（防御性兜底，防止无限循环）
    """
    if state.get("correction_abort_reason"):
        return "abort"
    if state.get("pipeline_error"):
        return "abort"
    return "retry"

def route_by_feature_cache(state: SemanticParserState) -> str:
    """根据特征缓存命中情况路由"""
    feature_output = state.get("feature_extraction_output")
    if feature_output:
        return "cache_hit"
    return "cache_miss"

def route_after_output_validation(state: SemanticParserState) -> str:
    """输出验证后的路由"""
    validation_result = state.get("validation_result", {})
    if validation_result.get("needs_clarification"):
        return "needs_clarification"
    return "valid"

def route_after_filter_validation(state: SemanticParserState) -> str:
    """筛选值验证后的路由

    注意：当 FilterValueValidator 发现 needs_confirmation=True 且有相似值时，
    filter_validator_node 会调用 interrupt() 暂停执行。
    用户确认后，通过 graph.update_state() 恢复执行。
    """
    if state.get("needs_clarification"):
        return "needs_clarification"
    filter_validation_result = state.get("filter_validation_result", {})
    if filter_validation_result.get("has_unresolvable_filters"):
        return "needs_clarification"
    return "valid"
