# -*- coding: utf-8 -*-
"""
SemanticParser LangGraph 子图定义

包含：
- 节点函数：各组件的 LangGraph 节点封装
- 路由函数：条件边的路由逻辑
- 子图组装：create_semantic_parser_graph()

设计原则：
- 节点函数接收 SemanticParserState，返回部分状态更新
- 所有复杂对象在存入 State 前调用 .model_dump()
- 使用 LangGraph interrupt() 实现筛选值确认

Requirements: Task 16-18 - LangGraph 子图集成
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, RunnableConfig

from analytics_assistant.src.agents.base.node import get_llm, stream_llm_structured

from .state import SemanticParserState
from .components import (
    IntentRouter,
    IntentType,
    QueryCache,
    compute_schema_hash,
    FieldRetriever,
    FewShotManager,
    FilterValueValidator,
    ErrorCorrector,
    FeedbackLearner,
    FeedbackType,
    FieldValueCache,
    # 优化组件
    RulePrefilter,
    FeatureExtractor,
    FeatureCache,
    DynamicSchemaBuilder,
    OutputValidator,
)
# SemanticUnderstanding 单独导入以避免循环依赖
from .components.semantic_understanding import SemanticUnderstanding, get_low_confidence_threshold
from .schemas.output import SemanticOutput, ClarificationSource
from .schemas.intermediate import FieldCandidate, FewShotExample
from .schemas.feedback import FeedbackRecord
from .schemas.prefilter import FeatureExtractionOutput, PrefilterResult, FieldRAGResult, ComplexityType
from .schemas.config import SemanticConfig
from .schemas.error_correction import ErrorCorrectionHistory
from .prompts import DynamicPromptBuilder
from analytics_assistant.src.agents.base.context import (
    get_context,
    get_context_or_raise,
)


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 节点函数
# ═══════════════════════════════════════════════════════════════════════════

async def intent_router_node(state: SemanticParserState) -> Dict[str, Any]:
    """意图路由节点
    
    执行意图识别，判断问题类型。
    
    输入：
    - state["question"]: 用户问题
    
    输出：
    - intent_router_output: IntentRouterOutput 序列化后的 dict
    """
    question = state.get("question", "")
    
    if not question:
        logger.warning("intent_router_node: 问题为空")
        return {
            "intent_router_output": {
                "intent_type": IntentType.IRRELEVANT.value,
                "confidence": 1.0,
                "reason": "问题为空",
                "source": "L0_RULES",
            }
        }
    
    router = IntentRouter()
    result = await router.route(question)
    
    logger.info(
        f"intent_router_node: intent={result.intent_type.value}, "
        f"confidence={result.confidence:.2f}"
    )
    
    return {
        "intent_router_output": result.model_dump(),
    }


async def query_cache_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    """查询缓存节点
    
    检查缓存是否命中。
    
    输入：
    - state["question"]: 用户问题
    - state["datasource_luid"]: 数据源 ID
    - config: RunnableConfig，包含 WorkflowContext
    
    输出：
    - cache_hit: 是否命中缓存
    - semantic_output: 缓存的语义输出（如果命中）
    - semantic_query: 缓存的查询（如果命中）
    """
    question = state.get("question", "")
    datasource_luid = state.get("datasource_luid", "")
    
    if not question or not datasource_luid:
        logger.debug("query_cache_node: 缺少必要参数，跳过缓存检查")
        return {"cache_hit": False}
    
    # 从 WorkflowContext 获取 schema_hash
    ctx = get_context(config) if config else None
    if ctx is not None:
        current_schema_hash = ctx.schema_hash
    else:
        # 没有 WorkflowContext，使用空 hash（会导致缓存不命中）
        logger.warning("query_cache_node: 未提供 WorkflowContext，缓存可能无法正确验证")
        current_schema_hash = ""
    
    cache = QueryCache()
    
    # 精确匹配
    cached = cache.get(question, datasource_luid, current_schema_hash)
    
    if cached is None:
        # 尝试语义相似匹配
        cached = cache.get_similar(question, datasource_luid, current_schema_hash)
    
    if cached is not None:
        logger.info(f"query_cache_node: 缓存命中, hit_count={cached.hit_count}")
        return {
            "cache_hit": True,
            "semantic_output": cached.semantic_output,
            "semantic_query": {"query": cached.query},
        }
    
    logger.debug("query_cache_node: 缓存未命中")
    return {"cache_hit": False}


async def field_retriever_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    """字段检索节点
    
    检索与问题相关的字段，并使用维度层级信息丰富结果。
    使用 RAGService 进行索引管理和检索。
    
    Task 24.1.2: 在 Prompt 中包含层级信息
    Property 28: Hierarchy Enrichment
    
    输入：
    - state["question"]: 用户问题
    - state["feature_extraction_output"]: 特征提取输出（可选，如果没有则从问题提取关键词）
    - config["configurable"]["workflow_context"]: WorkflowContext
    
    输出：
    - field_candidates: FieldCandidate 列表序列化后的 list[dict]
    """
    question = state.get("question", "")
    
    if not question:
        logger.warning("field_retriever_node: 问题为空")
        return {"field_candidates": []}
    
    # 从 config 获取 WorkflowContext
    ctx = get_context(config) if config else None
    data_model = ctx.data_model if ctx else None
    datasource_luid = ctx.datasource_luid if ctx else None
    
    # 获取或创建 FeatureExtractionOutput
    # 优先使用 state 中的 feature_extraction_output（来自 FeatureExtractor）
    # 如果没有，则从问题中提取简单的关键词作为降级方案
    feature_output_raw = state.get("feature_extraction_output")
    if feature_output_raw:
        feature_output = FeatureExtractionOutput.model_validate(feature_output_raw)
    else:
        # 降级方案：从问题中提取关键词
        # 这是一个简化的实现，完整的 FeatureExtractor 会在任务 12 中集成
        logger.debug("field_retriever_node: 未找到 feature_extraction_output，使用降级方案")
        feature_output = FeatureExtractionOutput(
            required_measures=[],  # 空列表会触发 FieldRetriever 的降级模式
            required_dimensions=[],
            is_degraded=True,
        )
    
    # 创建 FieldRetriever
    # 注意：索引在构建时已包含语义增强信息（aliases、business_description）
    # 检索时通过向量相似度自动匹配，无需额外传递 field_semantic
    retriever = FieldRetriever()
    
    # 检索字段
    rag_result = await retriever.retrieve(
        feature_output=feature_output,
        data_model=data_model,
        datasource_luid=datasource_luid,
    )
    
    # 合并所有候选字段
    candidates = rag_result.measures + rag_result.dimensions + rag_result.time_fields
    
    # 使用字段语义信息丰富字段候选（Property 28: Hierarchy Enrichment）
    if ctx and ctx.field_semantic:
        candidates = ctx.enrich_field_candidates_with_hierarchy(candidates)
    
    logger.info(f"field_retriever_node: 检索到 {len(candidates)} 个字段")
    
    return {
        "field_candidates": [c.model_dump() for c in candidates],
    }


async def few_shot_manager_node(state: SemanticParserState) -> Dict[str, Any]:
    """Few-shot 示例检索节点
    
    检索相关的 Few-shot 示例。
    
    输入：
    - state["question"]: 用户问题
    - state["datasource_luid"]: 数据源 ID
    
    输出：
    - few_shot_examples: FewShotExample 列表序列化后的 list[dict]
    """
    question = state.get("question", "")
    datasource_luid = state.get("datasource_luid", "")
    
    if not question or not datasource_luid:
        logger.debug("few_shot_manager_node: 缺少必要参数")
        return {"few_shot_examples": []}
    
    manager = FewShotManager()
    examples = await manager.retrieve(
        question=question,
        datasource_luid=datasource_luid,
        top_k=3,
    )
    
    logger.info(f"few_shot_manager_node: 检索到 {len(examples)} 个示例")
    
    return {
        "few_shot_examples": [e.model_dump() for e in examples],
    }


async def semantic_understanding_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    """语义理解节点
    
    使用 modular_prompt_builder_node 构建的 Prompt 调用 LLM 进行语义理解。
    
    输入：
    - state["question"]: 用户问题
    - state["modular_prompt"]: 由 modular_prompt_builder_node 构建的 Prompt
    - state["chat_history"]: 对话历史（可选）
    
    输出：
    - semantic_output: SemanticOutput 序列化后的 dict
    - needs_clarification: 是否需要澄清
    - clarification_question: 澄清问题
    - clarification_options: 澄清选项
    - clarification_source: 澄清来源
    - thinking: LLM 思考过程
    """
    question = state.get("question", "")
    
    if not question:
        logger.warning("semantic_understanding_node: 问题为空")
        return {
            "needs_clarification": True,
            "clarification_question": "请输入您的问题",
            "clarification_source": ClarificationSource.SEMANTIC_UNDERSTANDING.value,
        }
    
    # 获取 modular_prompt_builder_node 构建的 Prompt
    modular_prompt = state.get("modular_prompt")
    
    if not modular_prompt:
        # 降级：如果没有 modular_prompt，使用旧的方式构建
        logger.warning(
            "semantic_understanding_node: 未找到 modular_prompt，使用降级模式"
        )
        # 解析字段候选
        field_candidates_raw = state.get("field_candidates", [])
        field_candidates = [
            FieldCandidate.model_validate(c) for c in field_candidates_raw
        ]
        
        # 解析 Few-shot 示例
        few_shot_examples_raw = state.get("few_shot_examples", [])
        few_shot_examples = [
            FewShotExample.model_validate(e) for e in few_shot_examples_raw
        ] if few_shot_examples_raw else None
        
        # 解析对话历史
        history = state.get("chat_history")
        
        # 解析当前时间
        current_time_str = state.get("current_time")
        current_date = None
        if current_time_str:
            try:
                current_date = datetime.fromisoformat(current_time_str).date()
            except (ValueError, TypeError):
                pass
        
        # 使用旧的 SemanticUnderstanding 方式
        understanding = SemanticUnderstanding()
        result = await understanding.understand(
            question=question,
            field_candidates=field_candidates,
            current_date=current_date,
            history=history,
            few_shot_examples=few_shot_examples,
            return_thinking=True,
        )
    else:
        # 正常流程：直接使用 modular_prompt 调用 LLM
        logger.info(
            f"semantic_understanding_node: 使用 modular_prompt, "
            f"prompt_length={len(modular_prompt)}"
        )
        
        # 获取 LLM
        llm = get_llm(
            agent_name="semantic_parser",
            enable_json_mode=True,
        )
        
        # 构建消息
        messages = [HumanMessage(content=modular_prompt)]
        
        # 从 config 中获取流式回调
        on_token = None
        on_thinking = None
        if config:
            configurable = config.get("configurable", {})
            on_token = configurable.get("on_token")
            on_thinking = configurable.get("on_thinking")
        
        # 调用 LLM
        result, thinking = await stream_llm_structured(
            llm=llm,
            messages=messages,
            output_model=SemanticOutput,
            on_token=on_token,
            on_thinking=on_thinking,
            return_thinking=True,
        )
        
        # 后处理：检查自检结果
        result = _post_process_semantic_output(result)
        
        # 设置澄清来源
        if result.needs_clarification:
            result.clarification_source = ClarificationSource.SEMANTIC_UNDERSTANDING
    
    logger.info(
        f"semantic_understanding_node: query_id={result.query_id}, "
        f"needs_clarification={result.needs_clarification}"
    )
    
    output = {
        "semantic_output": result.model_dump(),
        "needs_clarification": result.needs_clarification,
    }
    
    if result.needs_clarification:
        output["clarification_question"] = result.clarification_question
        output["clarification_options"] = result.clarification_options
        output["clarification_source"] = (
            result.clarification_source.value 
            if result.clarification_source 
            else ClarificationSource.SEMANTIC_UNDERSTANDING.value
        )
    
    return output


def _post_process_semantic_output(result: SemanticOutput) -> SemanticOutput:
    """后处理：检查自检结果
    
    如果任一置信度低于阈值，确保 potential_issues 非空。
    """
    self_check = result.self_check
    low_confidence_threshold = get_low_confidence_threshold()
    
    # 检查各项置信度
    low_confidence_fields = []
    
    if self_check.field_mapping_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"字段映射置信度较低 ({self_check.field_mapping_confidence:.2f})"
        )
    
    if self_check.time_range_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"时间范围置信度较低 ({self_check.time_range_confidence:.2f})"
        )
    
    if self_check.computation_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"计算逻辑置信度较低 ({self_check.computation_confidence:.2f})"
        )
    
    if self_check.overall_confidence < low_confidence_threshold:
        low_confidence_fields.append(
            f"整体置信度较低 ({self_check.overall_confidence:.2f})"
        )
    
    # 如果有低置信度字段但 potential_issues 为空，添加警告
    if low_confidence_fields and not self_check.potential_issues:
        self_check.potential_issues = low_confidence_fields
        result.parsing_warnings.append(
            "检测到低置信度但 LLM 未报告问题，已自动添加警告"
        )
    
    return result


async def filter_validator_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    """筛选值验证节点
    
    验证筛选条件的值是否存在于数据源中。
    当需要用户确认时，使用 LangGraph interrupt() 暂停执行。
    
    输入：
    - state["semantic_output"]: 语义输出
    - state["confirmed_filters"]: 已确认的筛选值（多轮累积）
    - config: RunnableConfig，包含 WorkflowContext
    
    输出：
    - semantic_output: 更新后的语义输出
    - filter_validation_result: 验证结果
    - confirmed_filters: 累积的确认结果
    - needs_clarification: 是否需要澄清（无相似值时）
    - clarification_question: 澄清问题
    - clarification_source: 澄清来源
    """
    semantic_output_raw = state.get("semantic_output")
    
    if not semantic_output_raw:
        logger.warning("filter_validator_node: 缺少 semantic_output")
        return {}
    
    # 解析语义输出
    semantic_output = SemanticOutput.model_validate(semantic_output_raw)
    
    # 获取已确认的筛选值（用于多轮确认场景）
    existing_confirmations = state.get("confirmed_filters", [])
    
    # 尝试从 config 获取 WorkflowContext
    ctx = get_context(config) if config else None
    
    if ctx is None:
        # 没有 WorkflowContext，跳过验证
        logger.warning(
            "filter_validator_node: 未提供 WorkflowContext，跳过筛选值验证。"
        )
        return {
            "semantic_output": semantic_output.model_dump(),
            "filter_validation_result": {
                "results": [],
                "all_valid": True,
                "has_unresolvable_filters": False,
                "needs_confirmation": False,
            },
            "confirmed_filters": existing_confirmations,
        }
    
    # 检查必要的依赖
    platform_adapter = ctx.platform_adapter
    data_model = ctx.data_model
    datasource_id = ctx.datasource_luid
    
    if platform_adapter is None or data_model is None:
        logger.warning(
            "filter_validator_node: 缺少 platform_adapter 或 data_model，跳过验证。"
        )
        return {
            "semantic_output": semantic_output.model_dump(),
            "filter_validation_result": {
                "results": [],
                "all_valid": True,
                "has_unresolvable_filters": False,
                "needs_confirmation": False,
            },
            "confirmed_filters": existing_confirmations,
        }
    
    # 创建或获取字段值缓存
    field_value_cache = FieldValueCache()
    
    # 创建验证器
    validator = FilterValueValidator(
        platform_adapter=platform_adapter,
        field_value_cache=field_value_cache,
    )
    
    # 应用已有的确认到 semantic_output
    if existing_confirmations:
        for conf in existing_confirmations:
            semantic_output = validator.apply_single_confirmation(
                semantic_output,
                conf["field_name"],
                conf["original_value"],
                conf["confirmed_value"],
            )
    
    # 准备平台特定参数（如认证信息）
    platform_kwargs = {}
    if ctx.auth is not None:
        # 如果有认证上下文，提取 api_key 和 site
        if hasattr(ctx.auth, 'api_key'):
            platform_kwargs['api_key'] = ctx.auth.api_key
        if hasattr(ctx.auth, 'site'):
            platform_kwargs['site'] = ctx.auth.site
    
    # 执行验证
    try:
        summary = await validator.validate(
            semantic_output=semantic_output,
            data_model=data_model,
            datasource_id=datasource_id,
            **platform_kwargs,
        )
    except Exception as e:
        logger.error(f"filter_validator_node: 验证失败: {e}")
        # 验证失败时跳过，继续流程
        return {
            "semantic_output": semantic_output.model_dump(),
            "filter_validation_result": {
                "results": [],
                "all_valid": True,
                "has_unresolvable_filters": False,
                "needs_confirmation": False,
            },
            "confirmed_filters": existing_confirmations,
        }
    
    # 检查是否有需要用户确认的筛选值
    pending_confirmations = [
        r for r in summary.results
        if r.needs_confirmation and len(r.similar_values) > 0
    ]
    
    if pending_confirmations:
        # 使用 LangGraph interrupt() 暂停执行
        confirmation_request = {
            "type": "filter_value_confirmation",
            "pending": [
                {
                    "field_name": r.field_name,
                    "requested_value": r.requested_value,
                    "similar_values": r.similar_values,
                    "message": r.message,
                }
                for r in pending_confirmations
            ],
        }
        
        # interrupt() 会暂停执行并返回给调用方
        user_response = interrupt(confirmation_request)
        
        # 用户确认后，应用确认的值并累积到 confirmed_filters
        if user_response and "confirmations" in user_response:
            new_confirmations = []
            for field_name, confirmed_value in user_response["confirmations"].items():
                # 找到原始值
                original_value = next(
                    (r.requested_value for r in pending_confirmations 
                     if r.field_name == field_name),
                    None
                )
                if original_value:
                    new_confirmations.append({
                        "field_name": field_name,
                        "original_value": original_value,
                        "confirmed_value": confirmed_value,
                        "confirmed_at": datetime.now().isoformat(),
                    })
            
            # 累积所有确认（包括之前的和新的）
            all_confirmations = existing_confirmations + new_confirmations
            
            # 构建 {original_value: confirmed_value} 映射用于 apply_confirmations
            # 注意：user_response["confirmations"] 是 {field_name: confirmed_value}
            # 但 apply_confirmations 期望 {original_value: confirmed_value}
            value_confirmations = {}
            for conf in new_confirmations:
                value_confirmations[conf["original_value"]] = conf["confirmed_value"]
            
            updated_output = validator.apply_confirmations(
                semantic_output,
                value_confirmations,
            )
            return {
                "semantic_output": updated_output.model_dump(),
                "filter_validation_result": summary.model_dump(),
                "confirmed_filters": all_confirmations,
            }
    
    # 检查是否有无法解决的筛选值
    if summary.has_unresolvable_filters:
        unresolvable = [
            r for r in summary.results
            if r.is_unresolvable
        ]
        messages = [r.message for r in unresolvable if r.message]
        
        return {
            "semantic_output": semantic_output.model_dump(),
            "filter_validation_result": summary.model_dump(),
            "confirmed_filters": existing_confirmations,
            "needs_clarification": True,
            "clarification_question": "\n".join(messages) if messages else "筛选值无法匹配，请检查输入",
            "clarification_source": ClarificationSource.FILTER_VALIDATOR.value,
        }
    
    logger.info(
        f"filter_validator_node: 验证完成, all_valid={summary.all_valid}"
    )
    
    return {
        "semantic_output": semantic_output.model_dump(),
        "filter_validation_result": summary.model_dump(),
        "confirmed_filters": existing_confirmations,
    }


async def query_adapter_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    """查询适配节点
    
    将 SemanticOutput 转换为目标查询语言（VizQL）。
    
    输入：
    - state["semantic_output"]: 语义输出
    - config: RunnableConfig，包含 WorkflowContext
    
    输出：
    - semantic_query: 生成的 VizQL 查询
    - pipeline_error: 执行错误（如果有）
    """
    semantic_output_raw = state.get("semantic_output")
    
    if not semantic_output_raw:
        logger.warning("query_adapter_node: 缺少 semantic_output")
        return {
            "pipeline_error": {
                "error_type": "missing_input",
                "message": "缺少 semantic_output",
                "is_retryable": False,
            }
        }
    
    # 解析语义输出
    semantic_output = SemanticOutput.model_validate(semantic_output_raw)
    
    # 尝试从 config 获取 WorkflowContext
    ctx = get_context(config) if config else None
    
    if ctx is None or ctx.platform_adapter is None:
        # 没有平台适配器，直接返回 semantic_output 作为查询
        # 这允许在没有完整配置时也能运行流程
        logger.warning(
            "query_adapter_node: 未提供 platform_adapter，直接返回 semantic_output。"
        )
        return {
            "semantic_query": semantic_output_raw,
        }
    
    # 使用平台适配器构建查询
    try:
        platform_adapter = ctx.platform_adapter
        datasource_id = ctx.datasource_luid
        
        # 先验证查询
        validation = platform_adapter.validate_query(semantic_output)
        if not validation.is_valid:
            error_msgs = [e.message for e in (validation.errors or [])]
            return {
                "pipeline_error": {
                    "error_type": "validation_error",
                    "message": f"查询验证失败: {'; '.join(error_msgs)}",
                    "is_retryable": True,
                }
            }
        
        # 构建 VizQL 查询
        vizql_query = platform_adapter.build_query(
            semantic_output,
            datasource_id=datasource_id,
        )
        
        logger.info(
            f"query_adapter_node: 成功构建 VizQL 查询"
        )
        
        return {
            "semantic_query": vizql_query,
        }
        
    except Exception as e:
        logger.error(f"query_adapter_node: 构建查询失败: {e}")
        return {
            "pipeline_error": {
                "error_type": "build_error",
                "message": str(e),
                "is_retryable": True,
            }
        }


async def error_corrector_node(state: SemanticParserState) -> Dict[str, Any]:
    """错误修正节点
    
    基于执行错误反馈，让 LLM 修正语义理解输出。
    
    输入：
    - state["question"]: 用户问题
    - state["semantic_output"]: 之前的语义输出
    - state["pipeline_error"]: 执行错误
    - state["error_history"]: 错误历史
    - state["retry_count"]: 当前重试次数
    
    输出：
    - semantic_output: 修正后的语义输出
    - error_history: 更新后的错误历史
    - retry_count: 更新后的重试次数
    - correction_abort_reason: 修正终止原因（如果终止）
    - thinking: LLM 思考过程
    """
    question = state.get("question", "")
    semantic_output_raw = state.get("semantic_output")
    pipeline_error = state.get("pipeline_error")
    error_history = state.get("error_history", [])
    retry_count = state.get("retry_count", 0)
    
    if not pipeline_error:
        logger.warning("error_corrector_node: 没有错误需要修正")
        return {}
    
    if not semantic_output_raw:
        logger.warning("error_corrector_node: 缺少 semantic_output")
        return {
            "correction_abort_reason": "missing_semantic_output",
        }
    
    # 解析语义输出
    semantic_output = SemanticOutput.model_validate(semantic_output_raw)
    
    # 提取错误信息
    error_type = pipeline_error.get("error_type", "unknown")
    error_message = pipeline_error.get("message", "")
    
    # 创建错误修正器
    corrector = ErrorCorrector()
    
    # 恢复错误历史
    for h in error_history:
        corrector._error_history.append(
            ErrorCorrectionHistory.model_validate(h)
        )
    
    # 执行修正
    result = await corrector.correct(
        question=question,
        previous_output=semantic_output,
        error_info=error_message,
        error_type=error_type,
    )
    
    # 更新状态
    new_error_history = [h.model_dump() for h in corrector.error_history]
    new_retry_count = corrector.retry_count
    
    if not result.should_continue:
        logger.info(
            f"error_corrector_node: 修正终止, reason={result.abort_reason}"
        )
        return {
            "error_history": new_error_history,
            "retry_count": new_retry_count,
            "correction_abort_reason": result.abort_reason,
            "thinking": result.thinking,
        }
    
    logger.info(
        f"error_corrector_node: 修正完成, retry_count={new_retry_count}"
    )
    
    return {
        "semantic_output": result.corrected_output.model_dump() if result.corrected_output else semantic_output_raw,
        "error_history": new_error_history,
        "retry_count": new_retry_count,
        "pipeline_error": None,  # 清除错误，准备重试
        "thinking": result.thinking,
    }


async def feedback_learner_node(state: SemanticParserState) -> Dict[str, Any]:
    """反馈学习节点
    
    记录成功的查询，更新缓存，学习用户反馈。
    
    输入：
    - state["question"]: 用户问题
    - state["semantic_output"]: 语义输出
    - state["semantic_query"]: 生成的查询
    - state["datasource_luid"]: 数据源 ID
    - state["confirmed_filters"]: 确认的筛选值（用于学习同义词）
    
    输出：
    - parse_result: 解析结果汇总
    """
    question = state.get("question", "")
    semantic_output_raw = state.get("semantic_output")
    semantic_query = state.get("semantic_query")
    datasource_luid = state.get("datasource_luid", "")
    confirmed_filters = state.get("confirmed_filters", [])
    
    if not semantic_output_raw:
        logger.warning("feedback_learner_node: 缺少 semantic_output")
        return {
            "parse_result": {
                "success": False,
                "error": {"message": "缺少 semantic_output"},
            }
        }
    
    # 解析语义输出
    semantic_output = SemanticOutput.model_validate(semantic_output_raw)
    
    # 缓存成功的查询
    if datasource_luid and semantic_query:
        cache = QueryCache()
        query_str = str(semantic_query) if not isinstance(semantic_query, str) else semantic_query
        cache.set(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash="",  # 实际使用时需要计算
            semantic_output=semantic_output_raw,
            query=query_str,
        )
    
    # 学习同义词（从确认的筛选值）
    if confirmed_filters and datasource_luid:
        learner = FeedbackLearner()
        for conf in confirmed_filters:
            await learner.learn_synonym(
                original_term=conf.get("original_value", ""),
                correct_field=conf.get("confirmed_value", ""),
                datasource_luid=datasource_luid,
            )
    
    logger.info(
        f"feedback_learner_node: 完成, query_id={semantic_output.query_id}"
    )
    
    return {
        "parse_result": {
            "success": True,
            "query_id": semantic_output.query_id,
            "semantic_output": semantic_output_raw,
            "query": semantic_query,
        }
    }


# ═══════════════════════════════════════════════════════════════════════════
# 优化节点函数（Phase 14）
# ═══════════════════════════════════════════════════════════════════════════

async def rule_prefilter_node(state: SemanticParserState) -> Dict[str, Any]:
    """规则预处理节点
    
    执行规则预处理，提取时间提示、计算种子、复杂度类型。
    不调用 LLM，目标 50ms 内完成。
    
    输入：
    - state["question"]: 用户问题
    - state["current_time"]: 当前时间（可选）
    
    输出：
    - prefilter_result: PrefilterResult 序列化后的 dict
    """
    start_time = time.time()
    
    question = state.get("question", "")
    
    if not question:
        logger.warning("rule_prefilter_node: 问题为空")
        return {
            "prefilter_result": PrefilterResult().model_dump(),
        }
    
    # 解析当前时间
    current_time_str = state.get("current_time")
    current_date = None
    if current_time_str:
        try:
            current_date = datetime.fromisoformat(current_time_str).date()
        except (ValueError, TypeError):
            pass
    
    # 执行规则预处理
    prefilter = RulePrefilter(current_date=current_date)
    result = prefilter.prefilter(question)
    
    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"rule_prefilter_node: 完成, "
        f"time_hints={len(result.time_hints)}, "
        f"computations={len(result.matched_computations)}, "
        f"confidence={result.match_confidence:.2f}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )
    
    return {
        "prefilter_result": result.model_dump(),
        "optimization_metrics": {
            "rule_prefilter_ms": elapsed_ms,
        },
    }


async def feature_cache_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    """特征缓存节点
    
    检查特征缓存是否命中。
    
    输入：
    - state["question"]: 用户问题
    - state["datasource_luid"]: 数据源 ID
    
    输出：
    - feature_extraction_output: 缓存的特征输出（如果命中）
    - is_degraded: 是否为降级模式
    """
    question = state.get("question", "")
    datasource_luid = state.get("datasource_luid", "")
    
    if not question or not datasource_luid:
        logger.debug("feature_cache_node: 缺少必要参数，跳过缓存检查")
        return {}
    
    cache = FeatureCache()
    
    # 精确匹配
    cached = cache.get(question, datasource_luid)
    
    if cached is None:
        # 尝试语义相似匹配
        cached = cache.get_similar(question, datasource_luid)
    
    if cached is not None:
        logger.info(f"feature_cache_node: 缓存命中, hit_count={cached.hit_count}")
        return {
            "feature_extraction_output": cached.feature_output,
            "optimization_metrics": {
                "feature_cache_hit": True,
            },
        }
    
    logger.debug("feature_cache_node: 缓存未命中")
    return {
        "optimization_metrics": {
            "feature_cache_hit": False,
        },
    }


async def feature_extractor_node(state: SemanticParserState) -> Dict[str, Any]:
    """特征提取节点
    
    使用快速 LLM 验证规则预处理结果，提取字段需求。
    500ms 超时后降级到规则结果。
    
    输入：
    - state["question"]: 用户问题
    - state["prefilter_result"]: 规则预处理结果
    
    输出：
    - feature_extraction_output: FeatureExtractionOutput 序列化后的 dict
    - is_degraded: 是否为降级模式
    """
    start_time = time.time()
    
    question = state.get("question", "")
    prefilter_result_raw = state.get("prefilter_result")
    
    if not question:
        logger.warning("feature_extractor_node: 问题为空")
        return {
            "feature_extraction_output": FeatureExtractionOutput(is_degraded=True).model_dump(),
            "is_degraded": True,
        }
    
    # 解析 PrefilterResult
    if prefilter_result_raw:
        prefilter_result = PrefilterResult.model_validate(prefilter_result_raw)
    else:
        prefilter_result = PrefilterResult()
    
    # 执行特征提取
    extractor = FeatureExtractor()
    result = await extractor.extract(question, prefilter_result)
    
    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"feature_extractor_node: 完成, "
        f"measures={len(result.required_measures)}, "
        f"dimensions={len(result.required_dimensions)}, "
        f"is_degraded={result.is_degraded}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )
    
    # 更新 optimization_metrics
    existing_metrics = state.get("optimization_metrics", {})
    updated_metrics = {**existing_metrics, "feature_extractor_ms": elapsed_ms}
    
    return {
        "feature_extraction_output": result.model_dump(),
        "is_degraded": result.is_degraded,
        "optimization_metrics": updated_metrics,
    }


async def dynamic_schema_builder_node(state: SemanticParserState) -> Dict[str, Any]:
    """动态 Schema 构建节点
    
    根据 ComplexityType 精确裁剪 Schema，生成 schema_text。
    
    输入：
    - state["feature_extraction_output"]: 特征提取输出
    - state["field_candidates"]: 字段候选列表（来自 field_retriever_node）
    - state["prefilter_result"]: 规则预处理结果
    
    输出：
    - dynamic_schema_result: DynamicSchemaResult 序列化后的 dict
    - field_candidates: 更新后的字段候选列表（已裁剪）
    """
    start_time = time.time()
    
    feature_output_raw = state.get("feature_extraction_output")
    field_candidates_raw = state.get("field_candidates", [])
    prefilter_result_raw = state.get("prefilter_result")
    
    # 解析输入
    feature_output = None
    if feature_output_raw:
        feature_output = FeatureExtractionOutput.model_validate(feature_output_raw)
    
    prefilter_result = None
    if prefilter_result_raw:
        prefilter_result = PrefilterResult.model_validate(prefilter_result_raw)
    
    # 构建 FieldRAGResult（从 field_candidates 转换）
    field_candidates = [
        FieldCandidate.model_validate(c) for c in field_candidates_raw
    ]
    
    # 分类字段（忽略大小写）
    measures = [c for c in field_candidates if c.field_type.lower() == "measure"]
    dimensions = [c for c in field_candidates if c.field_type.lower() == "dimension"]
    time_fields = [c for c in field_candidates if c.data_type in ("date", "datetime")]
    
    field_rag_result = FieldRAGResult(
        measures=measures,
        dimensions=dimensions,
        time_fields=time_fields,
    )
    
    # 构建动态 Schema
    builder = DynamicSchemaBuilder()
    result = builder.build(
        feature_output=feature_output,
        field_rag_result=field_rag_result,
        prefilter_result=prefilter_result,
    )
    
    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"dynamic_schema_builder_node: 完成, "
        f"complexity={[c.value for c in result.detected_complexity]}, "
        f"schema_json_len={len(result.schema_text)}, "
        f"field_count={len(result.field_candidates)}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )
    
    # 更新 optimization_metrics
    existing_metrics = state.get("optimization_metrics", {})
    updated_metrics = {**existing_metrics, "dynamic_schema_builder_ms": elapsed_ms}
    
    return {
        "dynamic_schema_result": {
            "field_candidates": [c.model_dump() for c in result.field_candidates],
            "schema_text": result.schema_text,
            "modules": list(result.modules),
            "detected_complexity": [c.value for c in result.detected_complexity],
            "allowed_calc_types": result.allowed_calc_types,
            "time_expressions": result.time_expressions,
        },
        # 更新 field_candidates 为裁剪后的列表
        "field_candidates": [c.model_dump() for c in result.field_candidates],
        "optimization_metrics": updated_metrics,
    }


async def modular_prompt_builder_node(state: SemanticParserState) -> Dict[str, Any]:
    """模块化 Prompt 构建节点
    
    使用 DynamicSchemaBuilder 输出的 schema_text 构建 Prompt。
    
    输入：
    - state["question"]: 用户问题
    - state["dynamic_schema_result"]: DynamicSchemaBuilder 的输出
    - state["field_candidates"]: 字段候选列表（已裁剪）
    - state["prefilter_result"]: 规则预处理结果
    - state["feature_extraction_output"]: 特征提取输出
    - state["few_shot_examples"]: Few-shot 示例
    - state["current_time"]: 当前时间
    - state["chat_history"]: 对话历史（多轮对话上下文）
    
    输出：
    - modular_prompt: 构建好的 Prompt 字符串
    """
    start_time = time.time()
    
    question = state.get("question", "")
    dynamic_schema_result_raw = state.get("dynamic_schema_result")
    field_candidates_raw = state.get("field_candidates", [])
    prefilter_result_raw = state.get("prefilter_result")
    feature_output_raw = state.get("feature_extraction_output")
    few_shot_examples_raw = state.get("few_shot_examples", [])
    current_time_str = state.get("current_time")
    chat_history = state.get("chat_history")
    
    # 解析字段候选
    field_candidates = [
        FieldCandidate.model_validate(c) for c in field_candidates_raw
    ]
    
    # 解析 Few-shot 示例
    few_shot_examples = [
        FewShotExample.model_validate(e) for e in few_shot_examples_raw
    ] if few_shot_examples_raw else None
    
    # 解析当前时间
    current_date = None
    if current_time_str:
        try:
            current_date = datetime.fromisoformat(current_time_str).date()
        except (ValueError, TypeError):
            pass
    
    # 创建 SemanticConfig
    config = SemanticConfig(
        current_date=current_date or datetime.now().date(),
    )
    
    # 解析 prefilter_result 和 feature_output
    prefilter_result = None
    if prefilter_result_raw:
        prefilter_result = PrefilterResult.model_validate(prefilter_result_raw)
    
    feature_output = None
    if feature_output_raw:
        feature_output = FeatureExtractionOutput.model_validate(feature_output_raw)
    
    # 从 dynamic_schema_result 提取信息
    schema_text = ""
    detected_complexity = [ComplexityType.SIMPLE]
    allowed_calc_types = []
    
    if dynamic_schema_result_raw:
        schema_text = dynamic_schema_result_raw.get("schema_text", "")
        detected_complexity = [
            ComplexityType(c) for c in dynamic_schema_result_raw.get("detected_complexity", ["simple"])
        ]
        allowed_calc_types = dynamic_schema_result_raw.get("allowed_calc_types", [])
    
    # 构建 Prompt
    builder = DynamicPromptBuilder()
    prompt = builder.build(
        question=question,
        config=config,
        field_candidates=field_candidates,
        schema_json=schema_text,
        detected_complexity=detected_complexity,
        allowed_calc_types=allowed_calc_types,
        history=chat_history,
        few_shot_examples=few_shot_examples,
        prefilter_result=prefilter_result,
        feature_output=feature_output,
    )
    
    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"modular_prompt_builder_node: 完成, "
        f"complexity={[c.value for c in detected_complexity]}, "
        f"prompt_length={len(prompt)}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )
    
    # 更新 optimization_metrics
    existing_metrics = state.get("optimization_metrics", {})
    updated_metrics = {**existing_metrics, "modular_prompt_builder_ms": elapsed_ms}
    
    return {
        "modular_prompt": prompt,
        "optimization_metrics": updated_metrics,
    }


async def output_validator_node(state: SemanticParserState) -> Dict[str, Any]:
    """输出验证节点
    
    验证 SemanticUnderstanding 输出，自动修正简单错误。
    
    输入：
    - state["semantic_output"]: 语义输出
    - state["field_candidates"]: 字段候选列表
    
    输出：
    - semantic_output: 验证/修正后的语义输出
    - validation_result: 验证结果
    - needs_clarification: 是否需要澄清
    - clarification_question: 澄清问题
    """
    start_time = time.time()
    
    semantic_output_raw = state.get("semantic_output")
    field_candidates_raw = state.get("field_candidates", [])
    
    if not semantic_output_raw:
        logger.warning("output_validator_node: 缺少 semantic_output")
        return {}
    
    # 解析字段候选
    field_candidates = [
        FieldCandidate.model_validate(c) for c in field_candidates_raw
    ]
    
    # 分类字段（忽略大小写）
    measures = [c for c in field_candidates if c.field_type.lower() == "measure"]
    dimensions = [c for c in field_candidates if c.field_type.lower() == "dimension"]
    time_fields = [c for c in field_candidates if c.data_type in ("date", "datetime")]
    
    field_rag_result = FieldRAGResult(
        measures=measures,
        dimensions=dimensions,
        time_fields=time_fields,
    )
    
    # 执行验证
    validator = OutputValidator()
    result = validator.validate(
        semantic_output=semantic_output_raw,
        field_rag_result=field_rag_result,
    )
    
    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"output_validator_node: 完成, "
        f"is_valid={result.is_valid}, "
        f"errors={len(result.errors)}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )
    
    # 更新 optimization_metrics
    existing_metrics = state.get("optimization_metrics", {})
    updated_metrics = {**existing_metrics, "output_validator_ms": elapsed_ms}
    
    output = {
        "validation_result": result.model_dump(),
        "optimization_metrics": updated_metrics,
    }
    
    # 如果有修正，更新 semantic_output
    if result.corrected_output:
        output["semantic_output"] = result.corrected_output
    
    # 如果需要澄清
    if result.needs_clarification:
        output["needs_clarification"] = True
        output["clarification_question"] = result.clarification_message
        output["clarification_source"] = ClarificationSource.SEMANTIC_UNDERSTANDING.value
    
    return output


# ═══════════════════════════════════════════════════════════════════════════
# 路由函数
# ═══════════════════════════════════════════════════════════════════════════

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
    """根据缓存命中情况路由
    
    Returns:
        - "cache_hit": 缓存命中，跳到反馈学习
        - "cache_miss": 缓存未命中，继续检索
    """
    if state.get("cache_hit"):
        return "cache_hit"
    return "cache_miss"


def route_after_understanding(state: SemanticParserState) -> str:
    """语义理解后的路由
    
    Returns:
        - "needs_clarification": 需要澄清，返回给用户
        - "continue": 继续验证筛选值
    """
    if state.get("needs_clarification"):
        return "needs_clarification"
    return "continue"


def route_after_validation(state: SemanticParserState) -> str:
    """筛选值验证后的路由
    
    注意：当 FilterValueValidator 发现 needs_confirmation=True 且有相似值时，
    filter_validator_node 会调用 interrupt() 暂停执行。
    用户确认后，通过 graph.update_state() 恢复执行，FilterValueValidator 更新 filters，
    然后继续执行到这里，此时 validation_result 已经是 valid。
    
    只有当完全无法匹配（没有相似值可选）时，才返回 needs_clarification。
    
    Returns:
        - "valid": 验证通过，生成查询
        - "needs_clarification": 需要用户提供更多信息
    """
    # 检查是否需要澄清（来自 filter_validator_node）
    if state.get("needs_clarification"):
        return "needs_clarification"
    
    # 检查验证结果
    validation_result = state.get("filter_validation_result", {})
    if validation_result.get("has_unresolvable_filters"):
        return "needs_clarification"
    
    return "valid"


def route_after_query(state: SemanticParserState) -> str:
    """查询执行后的路由
    
    Returns:
        - "success": 执行成功，进入反馈学习
        - "error": 执行失败，进入错误修正
    """
    if state.get("pipeline_error"):
        return "error"
    return "success"


def route_after_correction(state: SemanticParserState) -> str:
    """错误修正后的路由
    
    Returns:
        - "retry": 重试查询
        - "max_retries": 达到最大重试次数，终止
    """
    # 检查是否有终止原因
    if state.get("correction_abort_reason"):
        return "max_retries"
    
    # 检查是否还有错误
    if state.get("pipeline_error"):
        return "max_retries"
    
    return "retry"


def route_by_feature_cache(state: SemanticParserState) -> str:
    """根据特征缓存命中情况路由
    
    Returns:
        - "cache_hit": 缓存命中，跳过 FeatureExtractor
        - "cache_miss": 缓存未命中，继续特征提取
    """
    feature_output = state.get("feature_extraction_output")
    if feature_output:
        return "cache_hit"
    return "cache_miss"


def route_after_output_validation(state: SemanticParserState) -> str:
    """输出验证后的路由
    
    Returns:
        - "valid": 验证通过，继续筛选值验证
        - "needs_clarification": 需要澄清
    """
    validation_result = state.get("validation_result", {})
    
    if validation_result.get("needs_clarification"):
        return "needs_clarification"
    
    return "valid"


def route_after_filter_validation(state: SemanticParserState) -> str:
    """筛选值验证后的路由
    
    注意：当 FilterValueValidator 发现 needs_confirmation=True 且有相似值时，
    filter_validator_node 会调用 interrupt() 暂停执行。
    用户确认后，通过 graph.update_state() 恢复执行，FilterValueValidator 更新 filters，
    然后继续执行到这里，此时 validation_result 已经是 valid。
    
    只有当完全无法匹配（没有相似值可选）时，才返回 needs_clarification。
    
    Returns:
        - "valid": 验证通过，生成查询
        - "needs_clarification": 需要用户提供更多信息
    """
    # 检查是否需要澄清（来自 filter_validator_node）
    if state.get("needs_clarification"):
        return "needs_clarification"
    
    # 检查验证结果
    filter_validation_result = state.get("filter_validation_result", {})
    if filter_validation_result.get("has_unresolvable_filters"):
        return "needs_clarification"
    
    return "valid"


# ═══════════════════════════════════════════════════════════════════════════
# 子图组装
# ═══════════════════════════════════════════════════════════════════════════

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
    
    筛选值确认机制说明：
    - 不使用独立的 filter_confirmation 节点
    - 通过 ValidateFilterValueTool + LangGraph interrupt() 实现
    - 当 FilterValueValidator 发现值不匹配时，调用工具返回 needs_confirmation=True
    - filter_validator_node 调用 interrupt() 暂停执行等待用户确认
    - 用户确认后，通过 graph.update_state() 恢复执行
    
    Returns:
        StateGraph 实例
    """
    graph = StateGraph(SemanticParserState)
    
    # ========== 添加节点 ==========
    # 阶段 1: 意图路由
    graph.add_node("intent_router", intent_router_node)
    
    # 阶段 2: 查询缓存
    graph.add_node("query_cache", query_cache_node)
    
    # 阶段 3: 规则预处理
    graph.add_node("rule_prefilter", rule_prefilter_node)
    
    # 阶段 4: 特征缓存
    graph.add_node("feature_cache", feature_cache_node)
    
    # 阶段 5: 特征提取
    graph.add_node("feature_extractor", feature_extractor_node)
    
    # 阶段 6: 字段检索
    graph.add_node("field_retriever", field_retriever_node)
    
    # 阶段 7: 动态 Schema 构建 + Prompt 构建
    graph.add_node("dynamic_schema_builder", dynamic_schema_builder_node)
    graph.add_node("modular_prompt_builder", modular_prompt_builder_node)
    
    # Few-shot 检索（与优化流程并行）
    graph.add_node("few_shot_manager", few_shot_manager_node)
    
    # 阶段 8: 语义理解
    graph.add_node("semantic_understanding", semantic_understanding_node)
    
    # 阶段 9: 输出验证
    graph.add_node("output_validator", output_validator_node)
    
    # 阶段 10: 筛选值验证
    graph.add_node("filter_validator", filter_validator_node)
    
    # 阶段 11: 查询适配 + 执行 + 缓存
    graph.add_node("query_adapter", query_adapter_node)
    graph.add_node("error_corrector", error_corrector_node)
    graph.add_node("feedback_learner", feedback_learner_node)
    
    # ========== 设置入口点 ==========
    graph.set_entry_point("intent_router")
    
    # ========== 添加条件边 ==========
    
    # 意图路由后的分支
    graph.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "data_query": "query_cache",
            "general": END,       # 直接返回元数据信息
            "irrelevant": END,    # 直接返回礼貌拒绝
            "clarification": END, # 直接返回澄清请求
        }
    )
    
    # 缓存检查后的分支
    graph.add_conditional_edges(
        "query_cache",
        route_by_cache,
        {
            "cache_hit": "feedback_learner",  # 缓存命中，直接到反馈学习
            "cache_miss": "rule_prefilter"    # 缓存未命中，进入规则预处理
        }
    )
    
    # 规则预处理 → 特征缓存
    graph.add_edge("rule_prefilter", "feature_cache")
    
    # 特征缓存后的分支
    graph.add_conditional_edges(
        "feature_cache",
        route_by_feature_cache,
        {
            "cache_hit": "field_retriever",     # 缓存命中，跳过特征提取
            "cache_miss": "feature_extractor"   # 缓存未命中，继续特征提取
        }
    )
    
    # 特征提取 → 字段检索
    graph.add_edge("feature_extractor", "field_retriever")
    
    # 字段检索 → 动态 Schema 构建
    graph.add_edge("field_retriever", "dynamic_schema_builder")
    
    # 动态 Schema 构建 → Prompt 构建
    graph.add_edge("dynamic_schema_builder", "modular_prompt_builder")
    
    # Prompt 构建 → Few-shot 检索
    graph.add_edge("modular_prompt_builder", "few_shot_manager")
    
    # Few-shot 检索 → 语义理解
    graph.add_edge("few_shot_manager", "semantic_understanding")
    
    # 语义理解后的分支
    graph.add_conditional_edges(
        "semantic_understanding",
        route_after_understanding,
        {
            "needs_clarification": END,           # 需要澄清，返回给用户
            "continue": "output_validator"        # 继续输出验证
        }
    )
    
    # 输出验证后的分支
    graph.add_conditional_edges(
        "output_validator",
        route_after_output_validation,
        {
            "valid": "filter_validator",          # 验证通过，继续筛选值验证
            "needs_clarification": END            # 需要澄清
        }
    )
    
    # 筛选值验证后的分支
    # 注意：当 needs_confirmation=True 且有相似值时，filter_validator_node 会调用 interrupt()
    # 用户确认后通过 graph.update_state() 恢复执行，此时 validation 结果已更新为 valid
    graph.add_conditional_edges(
        "filter_validator",
        route_after_filter_validation,
        {
            "valid": "query_adapter",             # 验证通过（或用户已确认），生成查询
            "needs_clarification": END            # 需要用户提供更多信息（无相似值可选）
        }
    )
    
    # 查询适配后的分支
    graph.add_conditional_edges(
        "query_adapter",
        route_after_query,
        {
            "success": "feedback_learner",        # 执行成功
            "error": "error_corrector"            # 执行失败，进入修正
        }
    )
    
    # 错误修正后的分支
    graph.add_conditional_edges(
        "error_corrector",
        route_after_correction,
        {
            "retry": "query_adapter",             # 重试查询
            "max_retries": END                    # 达到最大重试次数
        }
    )
    
    # 反馈学习 → 结束
    graph.add_edge("feedback_learner", END)
    
    return graph


def compile_semantic_parser_graph(checkpointer: Optional[Any] = None) -> Any:
    """编译语义解析器子图
    
    Args:
        checkpointer: LangGraph checkpointer，用于状态持久化
    
    Returns:
        编译后的图
    """
    graph = create_semantic_parser_graph()
    
    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    
    return graph.compile()


__all__ = [
    # 节点函数
    "intent_router_node",
    "query_cache_node",
    "field_retriever_node",
    "few_shot_manager_node",
    "semantic_understanding_node",
    "filter_validator_node",
    "query_adapter_node",
    "error_corrector_node",
    "feedback_learner_node",
    # 优化节点函数
    "rule_prefilter_node",
    "feature_cache_node",
    "feature_extractor_node",
    "dynamic_schema_builder_node",
    "modular_prompt_builder_node",
    "output_validator_node",
    # 路由函数
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
