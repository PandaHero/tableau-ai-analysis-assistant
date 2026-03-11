# -*- coding: utf-8 -*-
"""
SemanticParser LangGraph 子图定义

仅包含子图组装逻辑：
- create_semantic_parser_graph(): 创建子图
- compile_semantic_parser_graph(): 编译子图

节点函数定义在 nodes/ 目录下，路由函数定义在 routes.py 中。
"""
import logging
from typing import Any, Optional

from langgraph.graph import StateGraph, END

from analytics_assistant.src.agents.base.context import get_context as _get_context

from .state import SemanticParserState

# 节点函数
from .nodes import (
    intent_router_node,
    query_cache_node,
    rule_prefilter_node,
    feature_cache_node,
    feature_extractor_node,
    global_understanding_node,
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
    unified_feature_and_understanding_node,
    prepare_prompt_node,
    parallel_retrieval_node,
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
)

logger = logging.getLogger(__name__)

_compiled_graph_singleton: Optional[Any] = None

def create_semantic_parser_graph() -> StateGraph:
    """创建语义解析器子图

    精简管线架构（15 → 11 节点，复杂查询 LLM 3→2 次）：
    1. IntentRouter - 意图路由
    2. QueryCache - 查询缓存
    3. UnifiedFeatureAndUnderstanding - 规则预处理 + 特征缓存/提取 + 全局理解（纯规则）
       （合并 rule_prefilter + feature_cache + feature_extractor + global_understanding）
       （global_understanding 始终使用规则 fallback，不调 LLM）
    4. ParallelRetrieval - 字段检索 ∥ Few-shot 检索
       （合并 field_retriever + few_shot_manager，并行执行）
    5. PreparePrompt - Schema 裁剪 + Prompt 构建
       （合并 dynamic_schema_builder + modular_prompt_builder）
       （复杂查询注入全局理解增强指令）
    6. SemanticUnderstanding - 语义理解
       （简单查询：输出 SemanticOutput）
       （复杂查询：输出 ComplexSemanticOutput = SemanticOutput + 全局理解字段）
    7. OutputValidator - 输出验证
    8. FilterValueValidator - 筛选值验证
    9. QueryAdapter + 执行 + 缓存
    10. ErrorCorrector - 错误修正
    11. FeedbackLearner - 反馈学习

    Returns:
        StateGraph 实例
    """
    graph = StateGraph(SemanticParserState)

    # ========== 添加节点 ==========
    graph.add_node("intent_router", intent_router_node)
    graph.add_node("query_cache", query_cache_node)
    graph.add_node("unified_feature_understanding", unified_feature_and_understanding_node)
    graph.add_node("parallel_retrieval", parallel_retrieval_node)
    graph.add_node("prepare_prompt", prepare_prompt_node)
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
            "cache_miss": "unified_feature_understanding",
        }
    )

    graph.add_edge("unified_feature_understanding", "parallel_retrieval")
    graph.add_edge("parallel_retrieval", "prepare_prompt")
    graph.add_edge("prepare_prompt", "semantic_understanding")

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
            "retry": "output_validator",
            "abort": END,
        }
    )

    graph.add_edge("feedback_learner", END)

    return graph

def compile_semantic_parser_graph(checkpointer: Optional[Any] = None) -> Any:
    """编译语义解析器子图。

    无 checkpointer 时复用进程级单例，避免每次请求重复编译。
    """
    global _compiled_graph_singleton
    if checkpointer:
        graph = create_semantic_parser_graph()
        return graph.compile(checkpointer=checkpointer)

    if _compiled_graph_singleton is None:
        graph = create_semantic_parser_graph()
        _compiled_graph_singleton = graph.compile()
        logger.info("semantic_parser graph 已编译并缓存为进程级单例")

    return _compiled_graph_singleton

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
    "global_understanding_node",
    "dynamic_schema_builder_node",
    "modular_prompt_builder_node",
    "output_validator_node",
    "unified_feature_and_understanding_node",
    "prepare_prompt_node",
    "parallel_retrieval_node",
    # 路由函数（从 routes.py 重新导出，保持向后兼容）
    "route_by_intent",
    "route_by_cache",
    "route_after_understanding",
    "route_after_output_validation",
    "route_after_filter_validation",
    "route_after_query",
    "route_after_correction",
    # 子图组装
    "create_semantic_parser_graph",
    "compile_semantic_parser_graph",
]
