"""SemanticParser 子图 - LangGraph 子图实现。

本模块创建一个 LangGraph StateGraph，将 SemanticParser 实现为子图。
该子图可以作为主工作流中的一个节点使用。

架构（LangGraph 节点路由循环）：
    START → entry → intent_router → (条件) → preprocess | exit
    preprocess → schema_linking → step1
    step1 → (条件) → step2 | pipeline | END
    step2 → pipeline
    pipeline → (条件) → react_error_handler | END
    react_error_handler → (条件) → step1 | step2 | pipeline | END

流程：
1. Entry: 调用 before_agent 钩子（Requirements 0.11）
2. IntentRouter: 意图识别（Requirements 0.12）
   - L0 规则层：0 LLM 调用
   - L1 小模型分类：1 次低成本调用（可选）
   - L2 Step1 兜底
3. Preprocess: 预处理层（0 LLM 调用）（Requirements 1 - Phase 1）
   - normalize(): 全角半角归一、空白归一
   - extract_time(): 规则解析相对时间
   - extract_slots(): 从历史抽取已确认项
   - build_canonical(): 生成稳定的 canonical_question
   - extract_terms(): 提取候选业务术语
4. Schema Linking: 候选字段前置检索（0 LLM 调用）（Requirements 2 - Phase 1）
    - 精确匹配
    - 判断检索池（维度/度量/全部）
    - 向量检索（可选）

   - 两阶段打分融合
5. Step1: 语义理解（仅 DATA_QUERY 时运行）
6. Step2: 计算推理（仅用于非 SIMPLE 查询）
7. Pipeline: MapFields → BuildQuery → ExecuteQuery（单次执行）
8. ReAct 错误处理器: 分析错误并决定 RETRY/CLARIFY/ABORT
9. Exit: 调用 after_agent 钩子 + 扁平化输出（Requirements 0.11）
10. 如果 RETRY: 通过 LangGraph 路由循环回到相应步骤

关键设计：
- IntentRouter 在 Step1 之前执行，减少不必要的 LLM 调用
- Preprocess 在 Schema Linking 之前执行，提供规范化问题和时间上下文
- Schema Linking 在 Step1 之前执行，将候选字段集缩小到 O(k) 规模
- ReAct 错误处理是一个独立的 LangGraph 节点
- 重试循环通过 LangGraph 条件边实现
- 状态携带 error_feedback 和 retry_from 用于重试逻辑
- 入口/出口节点确保 middleware 钩子完整调用
"""

import logging
from typing import Any, Dict, List, Literal, Optional

from langgraph.graph import StateGraph, START, END
from langgraph.types import RunnableConfig

from .state import SemanticParserState
from .models import Step1Output, Step2Output
from .models.pipeline import PipelineResult, QueryError, QueryErrorType
from .models.react import ReActActionType, ReActOutput
from .components import (
    IntentRouter,
    IntentType,
    IntentRouterOutput,
    PreprocessComponent,
    PreprocessResult,
    QueryPipeline,
    ReActErrorHandler,
    SchemaCandidates,
    SchemaLinking,
    SchemaLinkingComponentConfig,
    Step1Component,
    Step2Component,
)

from .components.react_error_handler import RetryRecord
from ...core.models import IntentType as CoreIntentType, HowType
from ...infra.config.settings import settings
from ...infra.observability import get_metrics_from_config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 节点函数
# ═══════════════════════════════════════════════════════════════════════════

async def semantic_parser_entry(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """子图入口节点 - 调用 before_agent 钩子（带错误处理）。
    
    确保 PatchToolCallsMiddleware.before_agent() 等钩子能够生效。
    单个钩子失败不阻塞整个流程（skip_on_error=True）。
    
    ⚠️ Middleware 钩子调用（Requirements 0.11）：
    - 从 config 获取 middleware 栈
    - 调用 run_before_agent() 执行所有 before_agent 钩子
    - 失败时记录 middleware_hook_failure_count 指标
    
    Returns:
        更新后的状态字典
    """
    import copy
    
    logger.info("子图入口节点：调用 before_agent 钩子")
    
    # 获取 middleware 配置
    from ...agents.base.middleware_runner import (
        MiddlewareRunner,
        get_middleware_from_config,
    )
    
    middleware_list = get_middleware_from_config(config)
    
    if not middleware_list:
        logger.debug("No middleware configured, skipping before_agent hooks")
        return {}
    
    # 获取 skip_failed_hooks 配置（默认 True）
    configurable = (config or {}).get("configurable", {})
    skip_failed_hooks = configurable.get("skip_failed_hooks", True)
    
    # 创建 MiddlewareRunner
    runner = MiddlewareRunner(middleware=middleware_list, fail_fast=False)
    runtime = runner.build_runtime(config=config)
    
    try:
        # ⚠️ 修复（GPT-5.2 审计）：使用深拷贝来正确检测变更
        # 浅拷贝场景下，如果 middleware 原地修改 list/dict（如 messages append），
        # 比较不出差异，从而"返回为空"
        original_state = copy.deepcopy(dict(state))
        
        # 执行 before_agent 钩子
        updated_state = await runner.run_before_agent(
            state=dict(state),
            runtime=runtime,
            skip_on_error=skip_failed_hooks,
        )
        
        logger.debug("Semantic parser entry: before_agent hooks executed successfully")
        
        # 只返回 middleware 更新的字段（避免覆盖整个 state）
        # 计算差异：只返回被 middleware 修改的字段
        diff = {}
        for key, value in updated_state.items():
            if key not in original_state or original_state[key] != value:
                diff[key] = value
        
        return diff
        
    except Exception as e:
        logger.error(f"before_agent hooks failed: {e}", exc_info=True)
        
        # 记录失败指标（Requirements 0.11）
        metrics = get_metrics_from_config(config)
        if metrics is not None:
            metrics.middleware_hook_failure_count += 1
            metrics.middleware_hook_failure_by_hook["before_agent"] = (
                metrics.middleware_hook_failure_by_hook.get("before_agent", 0) + 1
            )
        
        if skip_failed_hooks:
            logger.warning("Continuing with original state due to skip_failed_hooks=True")
            return {}
        raise


async def intent_router_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """IntentRouter 节点 - 意图识别（两阶段路由）。
    
    在进入重路径（Step1/Schema Linking）之前，先用轻量级方式识别意图，
    减少不必要的 LLM 调用。
    
    三层策略：
    - L0 规则层（0 LLM 调用）：规则匹配闲聊/元数据/澄清
    - L1 小模型分类（1 次低成本调用）：严格 JSON 输出（可选）
    - L2 Step1 兜底：当 L1 置信度低时返回 DATA_QUERY
    
    路由逻辑：
    - DATA_QUERY → step1（进入重路径）
    - CLARIFICATION → exit（返回澄清请求）
    - GENERAL → exit（直接回答元数据问题）
    - IRRELEVANT → exit（礼貌拒绝）
    
    ⚠️ State 序列化：intent_router_output 存储为 dict（.model_dump()）
    
    Requirements: 0.12 - IntentRouter 意图识别（两阶段路由）
    
    Returns:
        更新后的状态字典
    """
    logger.info("子图 IntentRouter 节点启动")
    
    question = state.get("question", "")
    
    if not question:
        logger.warning("IntentRouter 未收到问题")
        return {
            "intent_router_output": None,
            "current_stage": "semantic_parser.intent_router",
            "error": "未提供问题",
        }
    
    # 获取 L1 置信度阈值配置
    l1_confidence_threshold = getattr(settings, "intent_router_l1_confidence_threshold", 0.8)
    enable_l1 = getattr(settings, "intent_router_enable_l1", False)
    
    # 创建 IntentRouter 实例
    router = IntentRouter(
        l1_confidence_threshold=l1_confidence_threshold,
        enable_l1=enable_l1,
    )
    
    try:
        # 执行意图识别
        output = await router.route(
            question=question,
            context={"messages": state.get("messages", [])},
            config=config,
        )
        
        logger.info(
            f"IntentRouter 完成: intent={output.intent_type.value}, "
            f"confidence={output.confidence:.2f}, source={output.source}"
        )
        
        # 构建返回结果
        result: Dict[str, Any] = {
            "intent_router_output": output.model_dump(),  # 序列化为 dict
            "current_stage": "semantic_parser.intent_router",
        }
        
        # 根据意图类型设置额外字段
        if output.intent_type == IntentType.CLARIFICATION:
            # 需要澄清
            clarify_message = "您的问题不够具体，请提供更多信息。"
            if output.need_clarify_slots:
                slots_str = "、".join(output.need_clarify_slots)
                clarify_message = f"您的问题不够具体，请说明您想查询的{slots_str}。"
            
            result["needs_clarification"] = True
            result["clarification_question"] = clarify_message
            
        elif output.intent_type == IntentType.GENERAL:
            # 元数据问答 - 设置标记，由主工作流处理
            result["is_metadata_question"] = True
            result["user_message"] = "这是一个关于数据结构的问题，我来为您查询相关信息。"
            
        elif output.intent_type == IntentType.IRRELEVANT:
            # 无关问题 - 礼貌拒绝
            result["pipeline_aborted"] = True
            result["user_message"] = (
                "抱歉，我是一个数据分析助手，专注于帮助您查询和分析数据。"
                "如果您有数据相关的问题，请随时告诉我！"
            )
        
        # DATA_QUERY 不需要额外处理，继续进入 step1
        
        return result
        
    except Exception as e:
        logger.error(f"IntentRouter 执行失败: {e}", exc_info=True)
        
        # 失败时降级为 DATA_QUERY，让 Step1 处理
        fallback_output = IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=0.5,
            reason=f"IntentRouter 执行失败，降级为 DATA_QUERY: {str(e)}",
            source="L2_FALLBACK",
        )
        
        return {
            "intent_router_output": fallback_output.model_dump(),
            "current_stage": "semantic_parser.intent_router",
        }


async def preprocess_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Preprocess 节点 - 预处理层（0 LLM 调用）。
    
    在 Step1 之前执行确定性预处理，把"高频可规则化"的不确定性从 LLM 中剥离。
    
    主要功能：
    - normalize(): 全角半角归一、空白归一、单位归一
    - extract_time(): 规则解析相对时间
    - extract_slots(): 从历史抽取已确认项
    - build_canonical(): 生成稳定的 canonical_question
    - extract_terms(): 提取候选业务术语
    
    ⚠️ State 序列化：preprocess_result 存储为 dict（.model_dump()）
    
    Requirements: 1 - Phase 1 预处理层
    
    Returns:
        更新后的状态字典
    """
    import time
    from datetime import date
    
    logger.info("子图 Preprocess 节点启动")
    
    question = state.get("question", "")
    messages = state.get("messages", [])
    
    if not question:
        logger.warning("Preprocess 未收到问题")
        return {
            "preprocess_result": None,
            "current_stage": "semantic_parser.preprocess",
        }
    
    # 获取 metrics
    metrics = get_metrics_from_config(config)
    start_time = time.monotonic()
    
    # 将消息转换为历史格式
    history = _convert_messages_to_history(messages)
    
    # 创建 PreprocessComponent 实例
    component = PreprocessComponent()
    
    try:
        # 执行预处理
        result = component.execute(
            question=question,
            history=history,
            current_date=date.today(),
        )
        
        # 记录耗时
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        if metrics is not None:
            metrics.preprocess_ms = elapsed_ms
        
        logger.info(
            f"Preprocess 完成: "
            f"canonical='{result.canonical_question[:50]}...', "
            f"time_context={result.time_context is not None}, "
            f"terms_count={len(result.extracted_terms)}, "
            f"elapsed_ms={elapsed_ms}"
        )
        
        return {
            "preprocess_result": result.model_dump(),  # 序列化为 dict
            "canonical_question": result.canonical_question,  # 扁平化字段
            "time_context": result.time_context,  # 扁平化字段
            "current_stage": "semantic_parser.preprocess",
        }
        
    except Exception as e:
        logger.error(f"Preprocess 执行失败: {e}", exc_info=True)
        
        # 预处理失败不阻塞流程，使用原始问题继续
        return {
            "preprocess_result": None,
            "canonical_question": question,  # 使用原始问题
            "time_context": None,
            "current_stage": "semantic_parser.preprocess",
        }


async def schema_linking_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Schema Linking 节点 - 候选字段前置检索（Phase 1）。
    
    在 Step1 之前执行 Schema Linking，将候选字段集缩小到 O(k) 规模，
    减少 Step1 prompt 的 token 消耗。
    
    主要功能：
    - 精确匹配 + N-gram 模糊匹配（O(1) + O(k)）
    - 判断检索池（维度/度量/全部）
    - 向量检索（可选，使用 Batch Embedding）
    - 两阶段打分融合
    - 合并去重
    
    ⚠️ State 序列化：schema_candidates 存储为 dict（.model_dump()）
    
    Requirements: 2 - Phase 1 Schema Linking 层
    
    Returns:
        更新后的状态字典
    """
    import time
    
    logger.info("子图 Schema Linking 节点启动")
    
    # 获取输入
    canonical_question = state.get("canonical_question") or state.get("question", "")
    data_model = state.get("data_model")
    datasource_luid = state.get("datasource_luid", "default")
    preprocess_result_dict = state.get("preprocess_result")
    
    if not canonical_question:
        logger.warning("Schema Linking 未收到问题")
        return {
            "schema_candidates": None,
            "current_stage": "semantic_parser.schema_linking",
        }
    
    if not data_model:
        logger.warning("Schema Linking 未收到数据模型，跳过")
        return {
            "schema_candidates": None,
            "current_stage": "semantic_parser.schema_linking",
        }
    
    # 获取 metrics
    metrics = get_metrics_from_config(config)
    start_time = time.monotonic()
    
    # 从 preprocess_result 获取提取的术语
    extracted_terms = None
    if preprocess_result_dict:
        extracted_terms = preprocess_result_dict.get("extracted_terms")
    
    try:
        # 获取字段列表
        fields = getattr(data_model, 'fields', [])
        if not fields:
            logger.warning("数据模型没有字段，跳过 Schema Linking")
            return {
                "schema_candidates": None,
                "current_stage": "semantic_parser.schema_linking",
            }
        
        schema_linking = SchemaLinking()
        result = await schema_linking.link(
            question=canonical_question,
            data_model=data_model,
            config=config,
        )
        
        # 记录耗时
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        if metrics is not None:
            metrics.schema_linking_ms = elapsed_ms
        
        if result.fallback_triggered:
            logger.warning(
                f"Schema Linking fallback: reason={result.fallback_reason}, "
                f"details={result.fallback_details}"
            )
            return {
                "schema_candidates": None,
                "schema_linking_fallback": {
                    "reason": result.fallback_reason,
                    "details": result.fallback_details,
                },
                "current_stage": "semantic_parser.schema_linking",
            }
        
        component_config = SchemaLinkingComponentConfig()
        dimensions = [c for c in result.candidates if c.field_type == "dimension"]
        measures = [c for c in result.candidates if c.field_type != "dimension"]
        schema_candidates = SchemaCandidates(
            dimensions=dimensions,
            measures=measures,
            total_fields=len(fields),
            is_degraded=len(fields) > component_config.degradation_threshold,
            search_pool="both",
        )
        
        logger.info(
            f"Schema Linking 完成: "
            f"dims={len(schema_candidates.dimensions)}, "
            f"meas={len(schema_candidates.measures)}, "
            f"search_pool={schema_candidates.search_pool}, "
            f"is_degraded={schema_candidates.is_degraded}, "
            f"elapsed_ms={elapsed_ms}"
        )
        
        return {
            "schema_candidates": schema_candidates.model_dump(),  # 序列化为 dict
            "current_stage": "semantic_parser.schema_linking",
        }
        
    except Exception as e:

        logger.error(f"Schema Linking 执行失败: {e}", exc_info=True)
        
        # Schema Linking 失败不阻塞流程，继续进入 Step1（使用全量字段）
        return {
            "schema_candidates": None,
            "current_stage": "semantic_parser.schema_linking",
        }


async def semantic_parser_exit(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """子图出口节点 - 调用 after_agent 钩子 + 统一扁平化输出 + 指标输出。
    
    在子图的所有终止路径上调用此节点，确保状态契约的单一事实来源。
    将子图内部的复杂对象转换为扁平化的基本类型字段，供主工作流路由消费。
    
    同时输出结构化日志，包含 SemanticParserMetrics 指标（Requirements 0.5）。
    
    ⚠️ Middleware 钩子调用（Requirements 0.11）：
    - 从 config 获取 middleware 栈
    - 调用 run_after_agent() 执行所有 after_agent 钩子
    - 失败时记录 middleware_hook_failure_count 指标
    
    ⚠️ Metrics 注入链路（Requirements 0.5）：
    - Metrics 通过 RunnableConfig.configurable["metrics"] 传递
    - semantic_parser_node 在调用 subgraph 前注入 metrics 到 config
    - 所有节点通过 get_metrics_from_config(config) 获取同一个 metrics 实例
    - 出口节点从 config 获取 metrics 并输出结构化日志
    
    Returns:
        包含扁平化字段的字典
    """
    logger.info("子图出口节点：调用 after_agent 钩子 + 扁平化输出")
    
    # 获取 middleware 配置
    from ...agents.base.middleware_runner import (
        MiddlewareRunner,
        get_middleware_from_config,
    )
    
    middleware_list = get_middleware_from_config(config)
    current_state = dict(state)
    
    if middleware_list:
        # 获取 skip_failed_hooks 配置（默认 True）
        configurable = (config or {}).get("configurable", {})
        skip_failed_hooks = configurable.get("skip_failed_hooks", True)
        
        # 创建 MiddlewareRunner
        runner = MiddlewareRunner(middleware=middleware_list, fail_fast=False)
        runtime = runner.build_runtime(config=config)
        
        try:
            # 执行 after_agent 钩子
            current_state = await runner.run_after_agent(
                state=current_state,
                runtime=runtime,
                skip_on_error=skip_failed_hooks,
            )
            
            logger.debug("Semantic parser exit: after_agent hooks executed successfully")
            
        except Exception as e:
            logger.error(f"after_agent hooks failed: {e}", exc_info=True)
            
            # 记录失败指标（Requirements 0.11）
            metrics = get_metrics_from_config(config)
            if metrics is not None:
                metrics.middleware_hook_failure_count += 1
                metrics.middleware_hook_failure_by_hook["after_agent"] = (
                    metrics.middleware_hook_failure_by_hook.get("after_agent", 0) + 1
                )
            
            if not skip_failed_hooks:
                raise
            
            logger.warning("Continuing with original state due to skip_failed_hooks=True")
    else:
        logger.debug("No middleware configured, skipping after_agent hooks")
    
    # 调用 _flatten_output 获取扁平化字段
    # 使用更新后的 state（可能被 after_agent 钩子修改）
    flattened = _flatten_output(current_state)
    
    # 获取 metrics 并输出结构化日志（Requirements 0.5）
    # 从 config 获取（由 semantic_parser_node 在入口注入）
    metrics = get_metrics_from_config(config)
    
    metrics.finalize()  # 计算 total_ms
    
    # 输出结构化日志
    logger.info(
        f"子图完成: intent_type={flattened.get('intent_type')}, "
        f"is_analysis_question={flattened.get('is_analysis_question')}",
        extra={"metrics": metrics.to_dict()},
    )
    
    return flattened


async def step1_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Step 1 节点：语义理解。
    
    从用户问题中提取 What/Where/How 并分类意图。
    
    ⚠️ State 序列化：step1_output 存储为 dict（.model_dump()），非 Pydantic 对象
    
    ⚠️ Metrics 注入（Requirements 0.5）：
    - Metrics 通过 RunnableConfig.configurable["metrics"] 传递
    - semantic_parser_node 在调用 subgraph 前注入 metrics 到 config
    - 所有节点通过 get_metrics_from_config(config) 获取同一个 metrics 实例
    
    ⚠️ Time Context（Requirements 1 - Phase 1）：
    - 从 state["time_context"] 读取 Preprocess 提供的时间上下文
    - 传递给 Step1Component 使用日期级别时间（非秒级）
    """
    logger.info("子图 Step1 节点启动")
    
    question = state.get("question", "")
    messages = state.get("messages", [])
    data_model = state.get("data_model")
    error_feedback = state.get("error_feedback")
    retry_from = state.get("retry_from")
    time_context = state.get("time_context")  # 从 Preprocess 获取时间上下文
    
    if not question:
        logger.warning("Step 1 未收到问题")
        return {
            "step1_output": None,
            "current_stage": "semantic_parser.step1",
            "error": "未提供问题",
        }
    
    # 将消息转换为历史格式
    history = _convert_messages_to_history(messages)
    
    # 执行 Step1
    component = Step1Component()
    
    try:
        step1_output, thinking = await component.execute(
            question=question,
            history=history if history else None,
            data_model=data_model,
            state=dict(state),
            config=config,
            error_feedback=error_feedback if retry_from == "step1" else None,
            time_context=time_context,  # 传递时间上下文（Requirements 1 - Phase 1）
        )
        
        logger.info(
            f"Step 1 完成: intent={step1_output.intent.type}, "
            f"how_type={step1_output.how_type}"
        )
        
        # 获取 metrics 中的格式重试次数，更新到 State（Requirements 0.6 - 分类重试预算管理）
        # ⚠️ 修复 double count 风险：直接使用 metrics 中的累积值，而非叠加
        # 因为 metrics 是贯通对象，step1_parse_retry_count 已经是本次子图执行的累积值
        metrics = get_metrics_from_config(config)
        
        # ⚠️ 序列化：将 Pydantic 对象转换为 dict 后存入 state
        return {
            "step1_output": step1_output.model_dump(),  # 序列化为 dict
            "restated_question": step1_output.restated_question,
            "current_stage": "semantic_parser.step1",
            "thinking": thinking,
            # 更新格式重试计数（Requirements 0.6）
            # 直接使用 metrics 累积值，避免 double count
            "parse_retry_count": metrics.step1_parse_retry_count + metrics.step2_parse_retry_count,
            # 成功执行后清除重试状态和错误
            "retry_from": None,
            "error_feedback": None,
            "pipeline_error": None,  # 清除之前的错误以允许管道继续
            "step1_parse_error": None,  # 清除解析错误
        }
        
    except (ValueError, Exception) as e:
        # 判断是否为解析错误
        error_message = str(e)
        is_parse_error = (
            "parse" in error_message.lower() or
            "json" in error_message.lower() or
            "validation" in error_message.lower() or
            isinstance(e, ValueError)
        )
        
        if is_parse_error:
            # 解析错误：设置 step1_parse_error，进入 ReAct 纠错链路
            logger.error(f"Step 1 解析失败: {e}", exc_info=True)
            
            # 构建结构化错误信息，携带原始输出（Requirements 0.2）
            from .models.pipeline import QueryError, QueryErrorType
            
            # 尝试获取原始输出（如果异常携带）
            original_output = None
            if hasattr(e, 'original_output'):
                original_output = e.original_output
            
            error_obj = QueryError(
                type=QueryErrorType.STEP1_PARSE_ERROR,
                message=f"Step1 输出解析失败: {error_message}",
                step="step1",
                can_retry=True,
                details={
                    "error_type": "parse_error",
                    "original_error": error_message,
                    "original_output_preview": original_output[:500] if original_output else None,
                },
            )
            
            return {
                "step1_output": None,
                "current_stage": "semantic_parser.step1",
                "step1_parse_error": error_message,  # 设置解析错误
                "pipeline_error": error_obj.model_dump(),  # 同时设置 pipeline_error 供 ReAct 使用
            }
        else:
            # 其他执行错误
            logger.error(f"Step 1 执行失败: {e}", exc_info=True)
            
            from .models.pipeline import QueryError, QueryErrorType
            error_obj = QueryError(
                type=QueryErrorType.STEP1_FAILED,
                message=str(e),
                step="step1",
                can_retry=True,
            )
            
            return {
                "step1_output": None,
                "current_stage": "semantic_parser.step1",
                "pipeline_error": error_obj.model_dump(),  # 序列化为 dict
            }


async def step2_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Step 2 节点：计算推理。
    
    设计复杂计算（LOD、排名、同比等）。
    仅当 step1_output.how_type != SIMPLE 时调用。
    
    ⚠️ State 序列化：
    - 读取：从 dict 重构 Step1Output
    - 写入：step2_output 存储为 dict（.model_dump()）
    """
    logger.info("子图 Step2 节点启动")
    
    step1_output_dict = state.get("step1_output")
    error_feedback = state.get("error_feedback")
    retry_from = state.get("retry_from")
    
    if not step1_output_dict:
        logger.error("Step 2 被调用但没有 step1_output")
        
        # ⚠️ 序列化：将 QueryError 转换为 dict
        from .models.pipeline import QueryError, QueryErrorType
        error_obj = QueryError(
            type=QueryErrorType.STEP2_FAILED,
            message="Step 2 需要 step1_output",
            step="step2",
            can_retry=False,
        )
        
        return {
            "step2_output": None,
            "current_stage": "semantic_parser.step2",
            "pipeline_error": error_obj.model_dump(),  # 序列化为 dict
        }
    
    # ⚠️ 反序列化：从 dict 重构 Step1Output 对象
    step1_output = Step1Output.model_validate(step1_output_dict)
    
    # 执行 Step2
    component = Step2Component()
    
    try:
        step2_output = await component.execute(
            step1_output=step1_output,
            state=dict(state),
            config=config,
            error_feedback=error_feedback if retry_from == "step2" else None,
        )
        
        logger.info(
            f"Step 2 完成: computations={len(step2_output.computations)}, "
            f"all_valid={step2_output.validation.all_valid}"
        )
        
        # 获取 metrics 中的格式重试次数，更新到 State（Requirements 0.6 - 分类重试预算管理）
        # ⚠️ 修复 double count 风险：直接使用 metrics 中的累积值，而非叠加
        # 因为 metrics 是贯通对象，step2_parse_retry_count 已经是本次子图执行的累积值
        metrics = get_metrics_from_config(config)
        
        # ⚠️ 序列化：将 Pydantic 对象转换为 dict 后存入 state
        return {
            "step2_output": step2_output.model_dump(),  # 序列化为 dict
            "current_stage": "semantic_parser.step2",
            # 更新格式重试计数（Requirements 0.6）
            # 直接使用 metrics 累积值，避免 double count
            "parse_retry_count": metrics.step1_parse_retry_count + metrics.step2_parse_retry_count,
            # 成功执行后清除重试状态和错误
            "retry_from": None,
            "error_feedback": None,
            "pipeline_error": None,  # 清除之前的错误以允许管道继续
            "step2_parse_error": None,  # 清除解析错误
        }
        
    except (ValueError, Exception) as e:
        # 判断是否为解析错误
        error_message = str(e)
        is_parse_error = (
            "parse" in error_message.lower() or
            "json" in error_message.lower() or
            "validation" in error_message.lower() or
            isinstance(e, ValueError)
        )
        
        if is_parse_error:
            # 解析错误：设置 step2_parse_error，进入 ReAct 纠错链路
            logger.error(f"Step 2 解析失败: {e}", exc_info=True)
            
            # 构建结构化错误信息，携带原始输出（Requirements 0.2）
            from .models.pipeline import QueryError, QueryErrorType
            
            # 尝试获取原始输出（如果异常携带）
            original_output = None
            if hasattr(e, 'original_output'):
                original_output = e.original_output
            
            error_obj = QueryError(
                type=QueryErrorType.STEP2_PARSE_ERROR,
                message=f"Step2 输出解析失败: {error_message}",
                step="step2",
                can_retry=True,
                details={
                    "error_type": "parse_error",
                    "original_error": error_message,
                    "original_output_preview": original_output[:500] if original_output else None,
                },
            )
            
            return {
                "step2_output": None,
                "current_stage": "semantic_parser.step2",
                "step2_parse_error": error_message,  # 设置解析错误
                "pipeline_error": error_obj.model_dump(),  # 同时设置 pipeline_error 供 ReAct 使用
            }
        else:
            # 其他执行错误
            logger.error(f"Step 2 执行失败: {e}", exc_info=True)
            
            from .models.pipeline import QueryError, QueryErrorType
            error_obj = QueryError(
                type=QueryErrorType.STEP2_FAILED,
                message=str(e),
                step="step2",
                can_retry=True,
            )
            
            return {
                "step2_output": None,
                "current_stage": "semantic_parser.step2",
                "pipeline_error": error_obj.model_dump(),  # 序列化为 dict
            }


async def pipeline_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Pipeline 节点：执行 MapFields → BuildQuery → ExecuteQuery。
    
    此节点在 Step1/Step2 之后执行剩余的管道步骤。
    单次执行 - 这里没有重试循环。错误由 react_error_handler_node 处理。
    
    ⚠️ State 序列化：
    - 读取：从 dict 重构 Step1Output/Step2Output
    - 写入：pipeline_error 存储为 dict
    """
    logger.info("子图 Pipeline 节点启动")
    
    step1_output_dict = state.get("step1_output")
    step2_output_dict = state.get("step2_output")
    question = state.get("question", "")
    data_model = state.get("data_model")
    datasource_luid = state.get("datasource_luid", "default")
    error_feedback = state.get("error_feedback")
    retry_from = state.get("retry_from")
    
    if not step1_output_dict:
        logger.error("Pipeline 被调用但没有 step1_output")
        
        # ⚠️ 序列化：将 QueryError 转换为 dict
        from .models.pipeline import QueryError, QueryErrorType
        error_obj = QueryError(
            type=QueryErrorType.BUILD_FAILED,
            message="Pipeline 需要 step1_output",
            step="pipeline",
            can_retry=False,
        )
        
        return {
            "pipeline_success": False,
            "current_stage": "semantic_parser.pipeline",
            "pipeline_error": error_obj.model_dump(),  # 序列化为 dict
        }
    
    # ⚠️ 反序列化：从 dict 重构对象
    step1_output = Step1Output.model_validate(step1_output_dict)
    step2_output = Step2Output.model_validate(step2_output_dict) if step2_output_dict else None
    
    # 为 QueryPipeline 构建状态（包含现有输出用于重试跳过逻辑）
    pipeline_state: Dict[str, Any] = {
        "mapped_query": state.get("mapped_query"),
        "vizql_query": state.get("vizql_query"),
    }
    
    # 如果从 map_fields 或 build_query 重试，添加错误反馈
    if retry_from in ("map_fields", "build_query") and error_feedback:
        pipeline_state["error_feedback"] = {
            "step": retry_from,
            "feedback": error_feedback,
        }
    
    # 使用新签名执行 QueryPipeline
    pipeline = QueryPipeline()
    
    try:
        result = await pipeline.execute(
            question=question,
            step1_output=step1_output,
            step2_output=step2_output,
            data_model=data_model,
            datasource_luid=datasource_luid,
            state=pipeline_state,
            config=config,
        )
        
        if result.success:
            logger.info(
                f"Pipeline 成功完成: "
                f"row_count={result.row_count}, "
                f"execution_time_ms={result.execution_time_ms}"
            )
            
            # 检查是否需要澄清（过滤值未找到）
            if result.needs_clarification and result.clarification:
                logger.info(
                    f"Pipeline 需要澄清: {result.clarification.get('type')}"
                )
                
                # 从澄清信息构建澄清问题
                clarification = result.clarification
                available_values = clarification.get("available_values", [])
                user_values = clarification.get("user_values", [])
                
                clarification_question = (
                    f"{clarification.get('message', '未找到过滤值')}\n"
                    f"您的输入: {', '.join(user_values)}\n"
                )
                if available_values:
                    clarification_question += f"可用值包括: {', '.join(available_values[:10])}"
                    if len(available_values) > 10:
                        clarification_question += f" 等 {len(available_values) - 10} 个"
                
                # ⚠️ State 序列化：query_result 存储为 ExecuteResult.model_dump() 的 dict
                # 而非 result.data（list），以符合 VizQLState 契约
                return {
                    "pipeline_success": True,  # 查询执行成功，只是没有结果
                    "current_stage": "semantic_parser.pipeline",
                    "semantic_query": result.semantic_query,
                    "mapped_query": result.mapped_query,
                    "vizql_query": result.vizql_query,
                    "query_result": result.model_dump(),  # ⚠️ 修复：存储完整 ExecuteResult dict
                    "columns": result.columns,
                    "row_count": result.row_count,
                    "execution_time_ms": result.execution_time_ms,
                    # 澄清信息
                    "needs_clarification": True,
                    "clarification_question": clarification_question,
                    # 清除重试状态
                    "retry_from": None,
                    "error_feedback": None,
                    "pipeline_error": None,
                }
            
            # ⚠️ State 序列化：query_result 存储为 ExecuteResult.model_dump() 的 dict
            return {
                "pipeline_success": True,
                "current_stage": "semantic_parser.pipeline",
                "semantic_query": result.semantic_query,
                "mapped_query": result.mapped_query,
                "vizql_query": result.vizql_query,
                "query_result": result.model_dump(),  # ⚠️ 修复：存储完整 ExecuteResult dict
                "columns": result.columns,
                "row_count": result.row_count,
                "file_path": result.file_path,
                "is_large_result": result.is_large_result,
                "execution_time_ms": result.execution_time_ms,
                # 清除重试状态
                "retry_from": None,
                "error_feedback": None,
                "pipeline_error": None,
            }
        else:
            logger.warning(f"Pipeline 失败: {result.error}")
            
            # ⚠️ 序列化：将 pipeline_error 转换为 dict
            return {
                "pipeline_success": False,
                "current_stage": "semantic_parser.pipeline",
                "pipeline_error": result.pipeline_error.model_dump() if result.pipeline_error else None,
                "semantic_query": result.semantic_query,
                "mapped_query": result.mapped_query,
                "vizql_query": result.vizql_query,
            }
            
    except Exception as e:
        logger.error(f"Pipeline 执行失败: {e}", exc_info=True)
        
        # ⚠️ 序列化：将 QueryError 转换为 dict
        from .models.pipeline import QueryError, QueryErrorType
        error_obj = QueryError(
            type=QueryErrorType.BUILD_FAILED,
            message=str(e),
            step="pipeline",
            can_retry=False,
        )
        
        return {
            "pipeline_success": False,
            "current_stage": "semantic_parser.pipeline",
            "pipeline_error": error_obj.model_dump(),  # 序列化为 dict
        }


async def react_error_handler_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """ReAct 错误处理器节点：分析错误并决定下一步动作。
    
    当 pipeline_node 失败时调用此节点。它使用 LLM 来：
    1. 分析错误并识别根本原因
    2. 决定动作：CORRECT、RETRY、CLARIFY 或 ABORT
    3. 对于 CORRECT：直接对 Step1/Step2 输出应用修正
    4. 对于 RETRY：为重试步骤生成 error_feedback
    
    路由函数将使用 react_action 和 retry_from 来路由回相应的步骤。
    
    ⚠️ State 序列化：
    - 读取：从 dict 重构 QueryError/Step1Output/Step2Output
    - 写入：react_action 存储为字符串值，step1_output/step2_output 存储为 dict
    """
    logger.info("子图 ReAct 错误处理器节点启动")
    
    pipeline_error_dict = state.get("pipeline_error")
    question = state.get("question", "")
    step1_output_dict = state.get("step1_output")
    step2_output_dict = state.get("step2_output")
    retry_history = state.get("retry_history") or []
    retry_count = state.get("retry_count") or 0
    
    if not pipeline_error_dict:
        logger.warning("ReAct 处理器被调用但没有 pipeline_error")
        return {
            "react_action": "ABORT",  # 存储为字符串值
            "user_message": "发生未知错误，请稍后重试。",
            "current_stage": "semantic_parser.react_error_handler",
        }
    
    # ⚠️ 反序列化：从 dict 重构对象
    from .models.pipeline import QueryError
    pipeline_error = QueryError.model_validate(pipeline_error_dict)
    
    step1_output = Step1Output.model_validate(step1_output_dict) if step1_output_dict else None
    step2_output = Step2Output.model_validate(step2_output_dict) if step2_output_dict else None
    
    # 为错误分析构建管道上下文
    pipeline_context: Dict[str, Any] = {
        "semantic_query": state.get("semantic_query"),
        "mapped_query": state.get("mapped_query"),
        "vizql_query": state.get("vizql_query"),
    }
    
    # 将重试历史转换为 RetryRecord 对象（统一类型处理）
    from .components.react_error_handler import RetryRecord
    retry_records: List[RetryRecord] = []
    for record in retry_history:
        if isinstance(record, RetryRecord):
            retry_records.append(record)
        elif isinstance(record, dict):
            retry_records.append(RetryRecord(
                step=record.get("step", ""),
                error_message=record.get("error_message", ""),
                action_taken=record.get("action_taken", ""),
                success=record.get("success", False),
            ))
    
    # 使用新签名调用 ReAct 错误处理器
    handler = ReActErrorHandler()
    
    try:
        output, corrected_step1, corrected_step2 = await handler.handle_error(
            error=pipeline_error,
            question=question,
            step1_output=step1_output,
            step2_output=step2_output,
            pipeline_context=pipeline_context,
            retry_history=retry_records,
            config=config,
        )
        
        logger.info(
            f"ReAct 决策: action={output.action.action_type}, "
            f"error_category={output.thought.error_category}, "
            f"can_correct={output.thought.can_correct}"
        )
        
        # 为历史记录创建重试记录
        new_record = handler.create_retry_record(
            step=pipeline_error.step,
            error_message=pipeline_error.message,
            action_taken=output.action.action_type.value,
            success=False,
        )
        new_retry_history = retry_history + [{
            "step": new_record.step,
            "error_message": new_record.error_message,
            "action_taken": new_record.action_taken,
            "success": new_record.success,
        }]
        
        # 根据动作类型构建结果
        result: Dict[str, Any] = {
            "react_action": output.action.action_type.value,  # ⚠️ 存储为字符串值
            "retry_history": new_retry_history,
            "retry_count": retry_count + 1,
            "current_stage": "semantic_parser.react_error_handler",
        }
        
        from .models.react import ReActActionType
        
        # 更新语义重试计数（Requirements 0.6 - 分类重试预算管理）
        # 只有 RETRY 和 CORRECT 动作才算语义重试
        if output.action.action_type in (ReActActionType.RETRY, ReActActionType.CORRECT):
            current_semantic_retry_count = state.get("semantic_retry_count") or 0
            result["semantic_retry_count"] = current_semantic_retry_count + 1

            # 记录语义重试触发原因（Requirements 0.6）
            try:
                metrics = get_metrics_from_config(config)
                if metrics is not None and hasattr(metrics, "semantic_retry_reason_counts"):
                    category = getattr(output.thought.error_category, "value", str(output.thought.error_category))
                    key = f"{pipeline_error.step}:{category}"
                    metrics.semantic_retry_reason_counts[key] = metrics.semantic_retry_reason_counts.get(key, 0) + 1
            except Exception:
                # metrics 仅用于可观测性，失败不影响主流程
                pass

        
        if output.action.action_type == ReActActionType.CORRECT:
            # 应用修正并继续到管道
            # ⚠️ 序列化：将修正后的对象转换为 dict
            result["step1_output"] = corrected_step1.model_dump() if corrected_step1 else step1_output_dict
            result["step2_output"] = corrected_step2.model_dump() if corrected_step2 else step2_output_dict
            # 清除错误状态并从管道重试
            result["pipeline_error"] = None
            result["retry_from"] = "pipeline"  # 使用修正后的输出重新运行管道
            
            # 关键：清除下游输出以强制重建
            # 否则管道将跳过 MapFields/BuildQuery 并使用过时的 vizql_query
            result["semantic_query"] = None
            result["mapped_query"] = None
            result["vizql_query"] = None
            
            logger.info("CORRECT 动作: 已应用修正，清除下游输出，将重新运行管道")
            
        elif output.action.action_type == ReActActionType.RETRY:
            result["retry_from"] = output.action.retry_from
            result["error_feedback"] = output.action.retry_guidance
            
            # 从 retry_from 步骤开始清除输出
            if output.action.retry_from == "step1":
                result["step1_output"] = None
                result["step2_output"] = None
                result["semantic_query"] = None
                result["mapped_query"] = None
                result["vizql_query"] = None
            elif output.action.retry_from == "step2":
                result["step2_output"] = None
                result["semantic_query"] = None
                result["mapped_query"] = None
                result["vizql_query"] = None
            elif output.action.retry_from == "map_fields":
                result["mapped_query"] = None
                result["vizql_query"] = None
            elif output.action.retry_from == "build_query":
                result["vizql_query"] = None
                
        elif output.action.action_type == ReActActionType.CLARIFY:
            result["needs_clarification"] = True
            result["clarification_question"] = output.action.clarification_question
            
        elif output.action.action_type == ReActActionType.ABORT:
            result["pipeline_aborted"] = True
            result["user_message"] = output.action.user_message
        
        return result
        
    except Exception as e:
        logger.error(f"ReAct 错误处理器失败: {e}", exc_info=True)
        return {
            "react_action": "ABORT",  # 存储为字符串值
            "pipeline_aborted": True,
            "user_message": f"处理过程中发生错误: {pipeline_error.message}",
            "current_stage": "semantic_parser.react_error_handler",
        }


# ═══════════════════════════════════════════════════════════════════════════
# 路由函数
# ═══════════════════════════════════════════════════════════════════════════

def route_after_intent_router(state: SemanticParserState) -> Literal["preprocess", "__end__"]:
    """IntentRouter 节点后的路由。
    
    路由逻辑（Requirements 0.12）：
    - DATA_QUERY → preprocess（进入预处理层，然后 step1）
    - CLARIFICATION → exit（返回澄清请求）
    - GENERAL → exit（直接回答元数据问题）
    - IRRELEVANT → exit（礼貌拒绝）
    
    ⚠️ State 序列化：intent_router_output 是 dict，需要重构后读取
    """
    intent_router_output_dict = state.get("intent_router_output")
    
    if not intent_router_output_dict:
        # 没有输出，降级进入 preprocess
        logger.warning("intent_router 后路由: preprocess（无输出，降级）")
        return "preprocess"
    
    # 从 dict 获取 intent_type
    intent_type_str = intent_router_output_dict.get("intent_type")
    
    if intent_type_str == IntentType.DATA_QUERY.value:
        logger.info("intent_router 后路由: preprocess（DATA_QUERY）")
        return "preprocess"
    else:
        # CLARIFICATION / GENERAL / IRRELEVANT 都直接结束
        logger.info(f"intent_router 后路由: exit（{intent_type_str}）")
        return "__end__"


def route_after_step1(state: SemanticParserState) -> Literal["step2", "pipeline", "react_error_handler", "__end__"]:
    """Step 1 节点后的路由。
    
    路由逻辑（方案 A：解析失败统一走 ReAct）：
    - 如果 step1 失败（设置了 pipeline_error，包括解析错误）：react_error_handler（进入纠错链路）
    - 如果意图不是 DATA_QUERY：END（不需要进一步处理）
    - 如果 how_type 是 SIMPLE：pipeline（跳过 step2）
    - 否则：step2（需要计算推理）
    
    注意：ReAct 对解析错误使用 deterministic 策略（不调用 LLM），符合"LLM 只处理长尾"原则
    
    ⚠️ State 序列化：step1_output 是 dict，需要重构后读取
    """
    # 检查错误（包括解析错误和执行错误，统一进入 ReAct）
    pipeline_error = state.get("pipeline_error")
    if pipeline_error:
        logger.info("step1 后路由: react_error_handler（错误）")
        return "react_error_handler"
    
    step1_output_dict = state.get("step1_output")
    if not step1_output_dict:
        logger.warning("step1 后路由: END（无输出）")
        return "__end__"
    
    # ⚠️ 反序列化：从 dict 重构 Step1Output
    try:
        step1_output = Step1Output.model_validate(step1_output_dict)
    except Exception as e:
        logger.error(f"step1 后路由: 无法解析 step1_output: {e}")
        return "__end__"
    
    # 检查意图类型
    if step1_output.intent.type != CoreIntentType.DATA_QUERY:
        logger.info(f"step1 后路由: END（intent={step1_output.intent.type}）")
        return "__end__"
    
    # 检查 how_type
    if step1_output.how_type == HowType.SIMPLE:
        logger.info("step1 后路由: pipeline（SIMPLE 查询）")
        return "pipeline"
    else:
        logger.info(f"step1 后路由: step2（how_type={step1_output.how_type}）")
        return "step2"


def route_after_step2(state: SemanticParserState) -> Literal["pipeline", "react_error_handler", "__end__"]:
    """Step 2 节点后的路由。
    
    路由逻辑（方案 A：解析失败统一走 ReAct）：
    - 如果 step2 失败（设置了 pipeline_error，包括解析错误）：react_error_handler（进入纠错链路）
    - 否则：pipeline
    
    注意：ReAct 对解析错误使用 deterministic 策略（不调用 LLM），符合"LLM 只处理长尾"原则
    """
    # 检查错误（包括解析错误和执行错误，统一进入 ReAct）
    pipeline_error = state.get("pipeline_error")
    if pipeline_error:
        logger.info("step2 后路由: react_error_handler（错误）")
        return "react_error_handler"
    
    logger.info("step2 后路由: pipeline")
    return "pipeline"


def route_after_pipeline(state: SemanticParserState) -> Literal["react_error_handler", "__end__"]:
    """Pipeline 节点后的路由。
    
    路由逻辑：
    - 如果管道成功：END
    - 如果管道需要澄清：END（返回澄清给用户）
    - 如果管道失败：react_error_handler
    """
    pipeline_success = state.get("pipeline_success")
    needs_clarification = state.get("needs_clarification")
    
    if pipeline_success:
        if needs_clarification:
            logger.info("pipeline 后路由: END（需要澄清）")
        else:
            logger.info("pipeline 后路由: END（成功）")
        return "__end__"
    else:
        logger.info("pipeline 后路由: react_error_handler")
        return "react_error_handler"


def route_after_react(
    state: SemanticParserState,
) -> Literal["step1", "step2", "pipeline", "__end__"]:
    """ReAct 错误处理器节点后的路由。
    
    基于 react_action 的路由逻辑：
    - CORRECT: 路由到 pipeline（使用修正后的输出重新运行）
    - RETRY: 路由到 retry_from 步骤（step1、step2 或 pipeline 用于 map_fields/build_query）
    - CLARIFY: END（返回澄清问题给用户）
    - ABORT: END（返回错误消息给用户）
    
    最大重试检查：
    - 如果 retry_count >= max_retries（来自设置）：END（中止）
    
    ⚠️ State 序列化：react_action 是字符串值，需要转换为枚举比较
    """
    from ...infra.config.settings import settings
    max_retries = settings.semantic_parser_max_retries
    max_semantic_retries = getattr(settings, "semantic_parser_max_semantic_retries", 2)
    
    react_action_str = state.get("react_action")  # 字符串值
    retry_from = state.get("retry_from")
    retry_count = state.get("retry_count") or 0
    semantic_retry_count = state.get("semantic_retry_count") or 0

    # 分类预算：语义重试预算（Requirements 0.6）
    # 仅对 RETRY/CORRECT 这种“继续尝试”的动作生效；CLARIFY/ABORT 直接终止。
    if react_action_str in ("RETRY", "CORRECT") and semantic_retry_count >= max_semantic_retries:
        logger.warning(
            f"react 后路由: END（已达语义重试预算 {semantic_retry_count}/{max_semantic_retries}）"
        )
        return "__end__"
    
    # 总重试保护（历史兼容）：避免无限循环
    if retry_count >= max_retries:
        logger.warning(f"react 后路由: END（已达最大重试次数 {max_retries}）")
        return "__end__"

    
    # ⚠️ 字符串值比较（不使用枚举）
    if react_action_str == "CORRECT":
        # CORRECT 动作：使用修正后的输出重新运行管道
        logger.info("react 后路由: pipeline（CORRECT）")
        return "pipeline"
    
    if react_action_str == "RETRY":
        if retry_from == "step1":
            logger.info("react 后路由: step1（RETRY）")
            return "step1"
        elif retry_from == "step2":
            logger.info("react 后路由: step2（RETRY）")
            return "step2"
        elif retry_from in ("map_fields", "build_query", "pipeline"):
            # map_fields 和 build_query 在 pipeline_node 内部
            logger.info(f"react 后路由: pipeline（RETRY from {retry_from}）")
            return "pipeline"
        else:
            logger.warning(f"react 后路由: END（未知 retry_from: {retry_from}）")
            return "__end__"
            
    elif react_action_str == "CLARIFY":
        logger.info("react 后路由: END（CLARIFY）")
        return "__end__"
        
    elif react_action_str == "ABORT":
        logger.info("react 后路由: END（ABORT）")
        return "__end__"
        
    else:
        logger.warning(f"react 后路由: END（未知动作: {react_action_str}）")
        return "__end__"


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def _flatten_output(state: Dict[str, Any] | SemanticParserState) -> Dict[str, Any]:
    """在 subgraph 出口处统一扁平化输出。
    
    将子图内部的复杂对象（Pydantic BaseModel）转换为扁平化的基本类型字段，
    供主工作流路由消费。这是状态契约的单一事实来源。
    
    扁平化规则（优先级从高到低）：
    1. intent_router_output (dict) → intent_type (str)（非 DATA_QUERY 时直接使用）
    2. step1_output (dict) → intent_type (str), is_analysis_question (bool)
    - 枚举类型转换为字符串值（.value）
    - 保持其他字段不变
    
    ⚠️ 修复（Requirements 0.12）：
    当 IntentRouter 返回 CLARIFICATION/GENERAL/IRRELEVANT 时，不会运行 Step1，
    此时必须从 intent_router_output 读取 intent_type，否则会返回 None。
    
    Args:
        state: SemanticParserState 或 dict（包含 dict 格式的 step1_output）
    
    Returns:
        包含扁平化字段的字典，用于更新状态
    """
    result: Dict[str, Any] = {}
    
    # 支持 dict 和 TypedDict 两种输入
    state_dict = dict(state) if not isinstance(state, dict) else state
    
    # ⚠️ 修复（Requirements 0.12）：优先从 intent_router_output 读取 intent_type
    # 当 IntentRouter 返回非 DATA_QUERY 时，不会运行 Step1，必须从这里获取
    intent_router_output_dict = state_dict.get("intent_router_output")
    if intent_router_output_dict:
        router_intent_type = intent_router_output_dict.get("intent_type")
        
        # 如果 IntentRouter 返回非 DATA_QUERY，直接使用其 intent_type
        if router_intent_type and router_intent_type != IntentType.DATA_QUERY.value:
            result["intent_type"] = router_intent_type
            result["is_analysis_question"] = False  # 非 DATA_QUERY 都不是分析问题
            
            logger.debug(
                f"Flattened output from intent_router: intent_type={result['intent_type']}, "
                f"is_analysis_question={result['is_analysis_question']}"
            )
            return result
    
    # 从 step1_output (dict) 提取扁平化字段（DATA_QUERY 路径）
    step1_output_dict = state_dict.get("step1_output")
    if step1_output_dict:
        try:
            # 从 dict 重构 Step1Output 对象以获取字段
            from .models import Step1Output
            step1 = Step1Output.model_validate(step1_output_dict)
            
            # 扁平化：intent_type 存储为字符串值，非枚举对象
            result["intent_type"] = step1.intent.type.value if step1.intent and step1.intent.type else None
            
            # 扁平化：is_analysis_question
            result["is_analysis_question"] = (
                step1.intent.type == CoreIntentType.DATA_QUERY if step1.intent and step1.intent.type else False
            )
            
            logger.debug(
                f"Flattened output from step1: intent_type={result['intent_type']}, "
                f"is_analysis_question={result['is_analysis_question']}"
            )
        except Exception as e:
            logger.error(f"Failed to flatten step1_output: {e}", exc_info=True)
            result["intent_type"] = None
            result["is_analysis_question"] = False
    else:
        # 没有 step1_output，检查是否有 intent_router_output（DATA_QUERY 但 Step1 失败）
        if intent_router_output_dict:
            router_intent_type = intent_router_output_dict.get("intent_type")
            result["intent_type"] = router_intent_type
            result["is_analysis_question"] = (router_intent_type == IntentType.DATA_QUERY.value)
        else:
            result["intent_type"] = None
            result["is_analysis_question"] = False
    
    return result


def _convert_messages_to_history(
    messages: List[Any],
) -> Optional[List[Dict[str, str]]]:
    """将 LangChain 消息转换为历史格式。
    
    Args:
        messages: LangChain 消息列表
    
    Returns:
        包含 'role' 和 'content' 键的字典列表，如果为空则返回 None
    """
    if not messages:
        return None
    
    history = []
    for msg in messages:
        if hasattr(msg, "type") and hasattr(msg, "content"):
            role = "user" if msg.type == "human" else "assistant"
            history.append({"role": role, "content": msg.content})
    
    return history if history else None


# ═══════════════════════════════════════════════════════════════════════════
# 子图工厂
# ═══════════════════════════════════════════════════════════════════════════

def create_semantic_parser_subgraph() -> StateGraph:
    """创建 SemanticParser 子图。
    
    架构（LangGraph 节点路由循环）：
        START → entry → intent_router → (条件) → preprocess | exit
        preprocess → schema_linking → step1
        step1 → (条件) → step2 | pipeline | react_error_handler | exit
        step2 → (条件) → pipeline | react_error_handler | exit
        pipeline → (条件) → react_error_handler | exit
        react_error_handler → (条件) → step1 | step2 | pipeline | exit
        exit → END
    
    节点：
    - entry: 入口节点，调用 before_agent 钩子（Requirements 0.11）
    - intent_router: 意图识别（Requirements 0.12）
    - preprocess: 预处理层（0 LLM 调用）（Requirements 1 - Phase 1）
    - schema_linking: Schema Linking 层（候选字段前置检索）（Requirements 2 - Phase 1）
    - step1: 语义理解（意图 + what/where/how）
    - step2: 计算推理（LOD、排名等）
    - pipeline: MapFields → BuildQuery → ExecuteQuery
    - react_error_handler: 分析错误并决定 RETRY/CLARIFY/ABORT
    - exit: 统一出口，调用 after_agent 钩子 + 扁平化输出（Requirements 0.11）
    
    Returns:
        SemanticParser 的编译后 StateGraph
    """
    # 使用 SemanticParserState 创建图
    graph = StateGraph(SemanticParserState)
    
    # 添加节点
    graph.add_node("entry", semantic_parser_entry)  # 入口节点（Requirements 0.11）
    graph.add_node("intent_router", intent_router_node)  # 意图识别（Requirements 0.12）
    graph.add_node("preprocess", preprocess_node)  # 预处理层（Requirements 1 - Phase 1）
    graph.add_node("schema_linking", schema_linking_node)  # Schema Linking 层（Requirements 2 - Phase 1）
    graph.add_node("step1", step1_node)
    graph.add_node("step2", step2_node)
    graph.add_node("pipeline", pipeline_node)
    graph.add_node("react_error_handler", react_error_handler_node)
    graph.add_node("exit", semantic_parser_exit)  # 统一出口节点
    
    # 添加边
    # START → entry → intent_router（Requirements 0.11, 0.12）
    graph.add_edge(START, "entry")
    graph.add_edge("entry", "intent_router")
    
    # intent_router → (条件) → preprocess | exit（Requirements 0.12）
    graph.add_conditional_edges(
        "intent_router",
        route_after_intent_router,
        {
            "preprocess": "preprocess",  # DATA_QUERY 进入预处理
            "__end__": "exit",  # CLARIFICATION/GENERAL/IRRELEVANT 直接结束
        },
    )
    
    # preprocess → schema_linking（Requirements 1, 2 - Phase 1）
    graph.add_edge("preprocess", "schema_linking")
    
    # schema_linking → step1（Requirements 2 - Phase 1）
    graph.add_edge("schema_linking", "step1")
    
    # step1 → (条件) → step2 | pipeline | react_error_handler | exit
    graph.add_conditional_edges(
        "step1",
        route_after_step1,
        {
            "step2": "step2",
            "pipeline": "pipeline",
            "react_error_handler": "react_error_handler",  # 新增：解析失败进入 ReAct
            "__end__": "exit",  # 所有终止路径都经过 exit
        },
    )
    
    # step2 → (条件) → pipeline | react_error_handler | exit
    graph.add_conditional_edges(
        "step2",
        route_after_step2,
        {
            "pipeline": "pipeline",
            "react_error_handler": "react_error_handler",  # 新增：解析失败进入 ReAct
            "__end__": "exit",  # 所有终止路径都经过 exit
        },
    )
    
    # pipeline → (条件) → react_error_handler | exit
    graph.add_conditional_edges(
        "pipeline",
        route_after_pipeline,
        {
            "react_error_handler": "react_error_handler",
            "__end__": "exit",  # 所有终止路径都经过 exit
        },
    )
    
    # react_error_handler → (条件) → step1 | step2 | pipeline | exit
    graph.add_conditional_edges(
        "react_error_handler",
        route_after_react,
        {
            "step1": "step1",
            "step2": "step2",
            "pipeline": "pipeline",
            "__end__": "exit",  # 所有终止路径都经过 exit
        },
    )
    
    # exit → END（统一出口）
    graph.add_edge("exit", END)
    
    logger.info(
        "SemanticParser 子图已创建，"
        "使用 IntentRouter 进行意图识别（Requirements 0.12），"
        "使用 Preprocess 进行预处理（Requirements 1 - Phase 1），"
        "使用 Schema Linking 进行候选字段前置检索（Requirements 2 - Phase 1），"
        "入口/出口节点确保 middleware 钩子完整调用（Requirements 0.11）"
    )
    
    return graph


def route_by_feature_flag(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> Literal["vnext_entry", "legacy_entry"]:
    """根据灰度开关路由（Requirements 0.14）。
    
    优先级：
    1. 请求级别覆盖（通过 config.configurable）
    2. 全局开关（feature_flags.semantic_parser_vnext_enabled）
    
    Args:
        state: 语义解析器状态
        config: LangGraph 配置
    
    Returns:
        路由目标节点名称
    """
    from ...infra.config.feature_flags import feature_flags
    
    # 1. 请求级别覆盖
    if config:
        configurable = config.get("configurable", {})
        if configurable.get("force_vnext"):
            logger.info("Feature flag routing: vnext_entry (force_vnext)")
            return "vnext_entry"
        if configurable.get("force_legacy"):
            logger.info("Feature flag routing: legacy_entry (force_legacy)")
            return "legacy_entry"
    
    # 2. 全局开关
    if feature_flags.semantic_parser_vnext_enabled:
        logger.info("Feature flag routing: vnext_entry (global flag)")
        return "vnext_entry"
    
    logger.info("Feature flag routing: legacy_entry (default)")
    return "legacy_entry"


__all__ = [
    "create_semantic_parser_subgraph",
    "intent_router_node",
    "preprocess_node",
    "route_by_feature_flag",
    "schema_linking_node",
    "semantic_parser_entry",
    "semantic_parser_exit",
    "step1_node",
    "step2_node",
    "pipeline_node",
    "react_error_handler_node",
]
