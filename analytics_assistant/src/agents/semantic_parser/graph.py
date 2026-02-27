# -*- coding: utf-8 -*-
"""
SemanticParser LangGraph 子图定义

仅包含子图组装逻辑：
- create_semantic_parser_graph(): 创建子图
- compile_semantic_parser_graph(): 编译子图

节点函数定义在 nodes/ 目录下，路由函数定义在 routes.py 中。
"""
from typing import Any, Optional

from langgraph.graph import StateGraph, END

from .state import SemanticParserState

# 节点函数
from .nodes import (
    intent_router_node,
    query_cache_node,
    rule_prefilter_node,
    feature_cache_node,
    feature_extractor_node,
    field_retriever_node,
    dynamic_schema_builder_node,
    modular_prompt_builder_node,
    few_shot_manager_node,
    semantic_understanding_node,
    output_validator_node,
    filter_validator_node,
    query_adapter_node,
    error_corrector_node,
    feedback_learner_node,
)

# 路由函数
from .routes import (
    route_by_intent,
    route_by_cache,
    route_after_understanding,
    route_after_output_validation,
    route_after_filter_validation,
    route_after_query,
    route_after_correction,
    route_by_feature_cache,
)

def create_semantic_parser_graph() -> StateGraph:
    """创建语义解析器子图

    11 阶段优化架构：
    1. IntentRouter - 意图路由
    2. QueryCache - 查询缓存
    3. RulePrefilter - 规则预处理
    4. FeatureCache - 特征缓存
    5. FeatureExtractor - 特征提取
    6. FieldRetriever - 字段检索
    7. DynamicSchemaBuilder + DynamicPromptBuilder
    8. SemanticUnderstanding - 语义理解
    9. OutputValidator - 输出验证
    10. FilterValueValidator - 筛选值验证
    11. QueryAdapter + 执行 + 缓存

    Returns:
        StateGraph 实例
    """
    graph = StateGraph(SemanticParserState)

    # ========== 添加节点 ==========
    graph.add_node("intent_router", intent_router_node)
    graph.add_node("query_cache", query_cache_node)
    graph.add_node("rule_prefilter", rule_prefilter_node)
    graph.add_node("feature_cache", feature_cache_node)
    graph.add_node("feature_extractor", feature_extractor_node)
    graph.add_node("field_retriever", field_retriever_node)
    graph.add_node("dynamic_schema_builder", dynamic_schema_builder_node)
    graph.add_node("modular_prompt_builder", modular_prompt_builder_node)
    graph.add_node("few_shot_manager", few_shot_manager_node)
    graph.add_node("semantic_understanding", semantic_understanding_node)
    graph.add_node("output_validator", output_validator_node)
    graph.add_node("filter_validator", filter_validator_node)
    graph.add_node("query_adapter", query_adapter_node)
    graph.add_node("error_corrector", error_corrector_node)
    graph.add_node("feedback_learner", feedback_learner_node)

    # ========== 设置入口点 ==========
    graph.set_entry_point("intent_router")

    # ========== 添加条件边 ==========
    graph.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "data_query": "query_cache",
            "general": END,
            "irrelevant": END,
            "clarification": END,
        }
    )

    graph.add_conditional_edges(
        "query_cache",
        route_by_cache,
        {
            "cache_hit": "feedback_learner",
            "cache_miss": "rule_prefilter",
        }
    )

    graph.add_edge("rule_prefilter", "feature_cache")

    graph.add_conditional_edges(
        "feature_cache",
        route_by_feature_cache,
        {
            "cache_hit": "field_retriever",
            "cache_miss": "feature_extractor",
        }
    )

    graph.add_edge("feature_extractor", "field_retriever")
    graph.add_edge("field_retriever", "dynamic_schema_builder")
    graph.add_edge("dynamic_schema_builder", "modular_prompt_builder")
    graph.add_edge("modular_prompt_builder", "few_shot_manager")
    graph.add_edge("few_shot_manager", "semantic_understanding")

    graph.add_conditional_edges(
        "semantic_understanding",
        route_after_understanding,
        {
            "needs_clarification": END,
            "continue": "output_validator",
        }
    )

    graph.add_conditional_edges(
        "output_validator",
        route_after_output_validation,
        {
            "valid": "filter_validator",
            "needs_clarification": END,
        }
    )

    graph.add_conditional_edges(
        "filter_validator",
        route_after_filter_validation,
        {
            "valid": "query_adapter",
            "needs_clarification": END,
        }
    )

    graph.add_conditional_edges(
        "query_adapter",
        route_after_query,
        {
            "success": "feedback_learner",
            "error": "error_corrector",
        }
    )

    graph.add_conditional_edges(
        "error_corrector",
        route_after_correction,
        {
            "retry": "query_adapter",
            "max_retries": END,
        }
    )

    graph.add_edge("feedback_learner", END)

    return graph

def compile_semantic_parser_graph(checkpointer: Optional[Any] = None) -> Any:
    """编译语义解析器子图"""
    graph = create_semantic_parser_graph()
    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()

__all__ = [
    # 节点函数（从 nodes/ 重新导出，保持向后兼容）
    "intent_router_node",
    "query_cache_node",
    "field_retriever_node",
    "few_shot_manager_node",
    "semantic_understanding_node",
    "filter_validator_node",
    "query_adapter_node",
    "error_corrector_node",
    "feedback_learner_node",
    "rule_prefilter_node",
    "feature_cache_node",
    "feature_extractor_node",
    "dynamic_schema_builder_node",
    "modular_prompt_builder_node",
    "output_validator_node",
    # 路由函数（从 routes.py 重新导出，保持向后兼容）
    "route_by_intent",
    "route_by_cache",
    "route_after_understanding",
    "route_after_output_validation",
    "route_after_filter_validation",
    "route_after_query",
    "route_after_correction",
    "route_by_feature_cache",
    # 子图组装
    "create_semantic_parser_graph",
    "compile_semantic_parser_graph",
]
