"""SemanticParser 子图 - LangGraph 子图实现。

本模块创建一个 LangGraph StateGraph，将 SemanticParser 实现为子图。
该子图可以作为主工作流中的一个节点使用。

架构（LangGraph 节点路由循环）：
    START → step1 → (条件) → step2 | pipeline | END
    step2 → pipeline
    pipeline → (条件) → react_error_handler | END
    react_error_handler → (条件) → step1 | step2 | pipeline | END

流程：
1. Step1: 语义理解（始终运行）
2. Step2: 计算推理（仅用于非 SIMPLE 查询）
3. Pipeline: MapFields → BuildQuery → ExecuteQuery（单次执行）
4. ReAct 错误处理器: 分析错误并决定 RETRY/CLARIFY/ABORT
5. 如果 RETRY: 通过 LangGraph 路由循环回到相应步骤

关键设计：
- ReAct 错误处理是一个独立的 LangGraph 节点
- 重试循环通过 LangGraph 条件边实现
- 状态携带 error_feedback 和 retry_from 用于重试逻辑
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
    QueryPipeline,
    ReActErrorHandler,
    Step1Component,
    Step2Component,
)
from .components.react_error_handler import RetryRecord
from ...core.models import IntentType, HowType
from ...infra.config.settings import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 节点函数
# ═══════════════════════════════════════════════════════════════════════════

async def step1_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Step 1 节点：语义理解。
    
    从用户问题中提取 What/Where/How 并分类意图。
    """
    logger.info("子图 Step1 节点启动")
    
    question = state.get("question", "")
    messages = state.get("messages", [])
    data_model = state.get("data_model")
    error_feedback = state.get("error_feedback")
    retry_from = state.get("retry_from")
    
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
        )
        
        logger.info(
            f"Step 1 完成: intent={step1_output.intent.type}, "
            f"how_type={step1_output.how_type}"
        )
        
        return {
            "step1_output": step1_output,
            "restated_question": step1_output.restated_question,
            "current_stage": "semantic_parser.step1",
            "thinking": thinking,
            # 成功执行后清除重试状态和 pipeline_error
            "retry_from": None,
            "error_feedback": None,
            "pipeline_error": None,  # 清除之前的错误以允许管道继续
        }
        
    except Exception as e:
        logger.error(f"Step 1 失败: {e}", exc_info=True)
        return {
            "step1_output": None,
            "current_stage": "semantic_parser.step1",
            "pipeline_error": QueryError(
                type=QueryErrorType.STEP1_FAILED,
                message=str(e),
                step="step1",
                can_retry=True,
            ),
        }


async def step2_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Step 2 节点：计算推理。
    
    设计复杂计算（LOD、排名、同比等）。
    仅当 step1_output.how_type != SIMPLE 时调用。
    """
    logger.info("子图 Step2 节点启动")
    
    step1_output: Step1Output | None = state.get("step1_output")
    error_feedback = state.get("error_feedback")
    retry_from = state.get("retry_from")
    
    if not step1_output:
        logger.error("Step 2 被调用但没有 step1_output")
        return {
            "step2_output": None,
            "current_stage": "semantic_parser.step2",
            "pipeline_error": QueryError(
                type=QueryErrorType.STEP2_FAILED,
                message="Step 2 需要 step1_output",
                step="step2",
                can_retry=False,
            ),
        }
    
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
        
        return {
            "step2_output": step2_output,
            "current_stage": "semantic_parser.step2",
            # 成功执行后清除重试状态和 pipeline_error
            "retry_from": None,
            "error_feedback": None,
            "pipeline_error": None,  # 清除之前的错误以允许管道继续
        }
        
    except Exception as e:
        logger.error(f"Step 2 失败: {e}", exc_info=True)
        return {
            "step2_output": None,
            "current_stage": "semantic_parser.step2",
            "pipeline_error": QueryError(
                type=QueryErrorType.STEP2_FAILED,
                message=str(e),
                step="step2",
                can_retry=True,
            ),
        }


async def pipeline_node(
    state: SemanticParserState,
    config: RunnableConfig | None = None,
) -> Dict[str, Any]:
    """Pipeline 节点：执行 MapFields → BuildQuery → ExecuteQuery。
    
    此节点在 Step1/Step2 之后执行剩余的管道步骤。
    单次执行 - 这里没有重试循环。错误由 react_error_handler_node 处理。
    """
    logger.info("子图 Pipeline 节点启动")
    
    step1_output: Step1Output | None = state.get("step1_output")
    step2_output: Step2Output | None = state.get("step2_output")
    question = state.get("question", "")
    data_model = state.get("data_model")
    datasource_luid = state.get("datasource_luid", "default")
    error_feedback = state.get("error_feedback")
    retry_from = state.get("retry_from")
    
    if not step1_output:
        logger.error("Pipeline 被调用但没有 step1_output")
        return {
            "pipeline_success": False,
            "current_stage": "semantic_parser.pipeline",
            "pipeline_error": QueryError(
                type=QueryErrorType.BUILD_FAILED,
                message="Pipeline 需要 step1_output",
                step="pipeline",
                can_retry=False,
            ),
        }
    
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
                
                return {
                    "pipeline_success": True,  # 查询执行成功，只是没有结果
                    "current_stage": "semantic_parser.pipeline",
                    "semantic_query": result.semantic_query,
                    "mapped_query": result.mapped_query,
                    "vizql_query": result.vizql_query,
                    "query_result": result.data,
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
            
            return {
                "pipeline_success": True,
                "current_stage": "semantic_parser.pipeline",
                "semantic_query": result.semantic_query,
                "mapped_query": result.mapped_query,
                "vizql_query": result.vizql_query,
                "query_result": result.data,
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
            
            return {
                "pipeline_success": False,
                "current_stage": "semantic_parser.pipeline",
                "pipeline_error": result.pipeline_error,
                "semantic_query": result.semantic_query,
                "mapped_query": result.mapped_query,
                "vizql_query": result.vizql_query,
            }
            
    except Exception as e:
        logger.error(f"Pipeline 执行失败: {e}", exc_info=True)
        return {
            "pipeline_success": False,
            "current_stage": "semantic_parser.pipeline",
            "pipeline_error": QueryError(
                type=QueryErrorType.BUILD_FAILED,
                message=str(e),
                step="pipeline",
                can_retry=False,
            ),
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
    """
    logger.info("子图 ReAct 错误处理器节点启动")
    
    pipeline_error: QueryError | None = state.get("pipeline_error")
    question = state.get("question", "")
    step1_output = state.get("step1_output")
    step2_output = state.get("step2_output")
    retry_history = state.get("retry_history") or []
    retry_count = state.get("retry_count") or 0
    
    if not pipeline_error:
        logger.warning("ReAct 处理器被调用但没有 pipeline_error")
        return {
            "react_action": ReActActionType.ABORT,
            "user_message": "发生未知错误，请稍后重试。",
            "current_stage": "semantic_parser.react_error_handler",
        }
    
    # 为错误分析构建管道上下文
    pipeline_context: Dict[str, Any] = {
        "semantic_query": state.get("semantic_query"),
        "mapped_query": state.get("mapped_query"),
        "vizql_query": state.get("vizql_query"),
    }
    
    # 将重试历史转换为 RetryRecord 对象（统一类型处理）
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
            "react_action": output.action.action_type,
            "retry_history": new_retry_history,
            "retry_count": retry_count + 1,
            "current_stage": "semantic_parser.react_error_handler",
        }
        
        if output.action.action_type == ReActActionType.CORRECT:
            # 应用修正并继续到管道
            result["step1_output"] = corrected_step1
            result["step2_output"] = corrected_step2
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
            "react_action": ReActActionType.ABORT,
            "pipeline_aborted": True,
            "user_message": f"处理过程中发生错误: {pipeline_error.message}",
            "current_stage": "semantic_parser.react_error_handler",
        }


# ═══════════════════════════════════════════════════════════════════════════
# 路由函数
# ═══════════════════════════════════════════════════════════════════════════

def route_after_step1(state: SemanticParserState) -> Literal["step2", "pipeline", "__end__"]:
    """Step 1 节点后的路由。
    
    路由逻辑：
    - 如果 step1 失败（设置了 pipeline_error）：END（错误将在状态中）
    - 如果意图不是 DATA_QUERY：END（不需要进一步处理）
    - 如果 how_type 是 SIMPLE：pipeline（跳过 step2）
    - 否则：step2（需要计算推理）
    """
    pipeline_error = state.get("pipeline_error")
    if pipeline_error:
        logger.info("step1 后路由: END（错误）")
        return "__end__"
    
    step1_output: Step1Output | None = state.get("step1_output")
    if not step1_output:
        logger.warning("step1 后路由: END（无输出）")
        return "__end__"
    
    # 检查意图类型
    if step1_output.intent.type != IntentType.DATA_QUERY:
        logger.info(f"step1 后路由: END（intent={step1_output.intent.type}）")
        return "__end__"
    
    # 检查 how_type
    if step1_output.how_type == HowType.SIMPLE:
        logger.info("step1 后路由: pipeline（SIMPLE 查询）")
        return "pipeline"
    else:
        logger.info(f"step1 后路由: step2（how_type={step1_output.how_type}）")
        return "step2"


def route_after_step2(state: SemanticParserState) -> Literal["pipeline", "__end__"]:
    """Step 2 节点后的路由。
    
    路由逻辑：
    - 如果 step2 失败（设置了 pipeline_error）：END
    - 否则：pipeline
    """
    pipeline_error = state.get("pipeline_error")
    if pipeline_error:
        logger.info("step2 后路由: END（错误）")
        return "__end__"
    
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
    """
    max_retries = settings.semantic_parser_max_retries
    
    react_action = state.get("react_action")
    retry_from = state.get("retry_from")
    retry_count = state.get("retry_count") or 0
    
    # 检查最大重试次数
    if retry_count >= max_retries:
        logger.warning(f"react 后路由: END（已达最大重试次数 {max_retries}）")
        return "__end__"
    
    if react_action == ReActActionType.CORRECT:
        # CORRECT 动作：使用修正后的输出重新运行管道
        logger.info("react 后路由: pipeline（CORRECT）")
        return "pipeline"
    
    if react_action == ReActActionType.RETRY:
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
            
    elif react_action == ReActActionType.CLARIFY:
        logger.info("react 后路由: END（CLARIFY）")
        return "__end__"
        
    elif react_action == ReActActionType.ABORT:
        logger.info("react 后路由: END（ABORT）")
        return "__end__"
        
    else:
        logger.warning(f"react 后路由: END（未知动作: {react_action}）")
        return "__end__"


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

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
        START → step1 → (条件) → step2 | pipeline | END
        step2 → (条件) → pipeline | END
        pipeline → (条件) → react_error_handler | END
        react_error_handler → (条件) → step1 | step2 | pipeline | END
    
    节点：
    - step1: 语义理解（意图 + what/where/how）
    - step2: 计算推理（LOD、排名等）
    - pipeline: MapFields → BuildQuery → ExecuteQuery
    - react_error_handler: 分析错误并决定 RETRY/CLARIFY/ABORT
    
    Returns:
        SemanticParser 的编译后 StateGraph
    """
    # 使用 SemanticParserState 创建图
    graph = StateGraph(SemanticParserState)
    
    # 添加节点
    graph.add_node("step1", step1_node)
    graph.add_node("step2", step2_node)
    graph.add_node("pipeline", pipeline_node)
    graph.add_node("react_error_handler", react_error_handler_node)
    
    # 添加边
    # START → step1
    graph.add_edge(START, "step1")
    
    # step1 → (条件) → step2 | pipeline | END
    graph.add_conditional_edges(
        "step1",
        route_after_step1,
        {
            "step2": "step2",
            "pipeline": "pipeline",
            "__end__": END,
        },
    )
    
    # step2 → (条件) → pipeline | END
    graph.add_conditional_edges(
        "step2",
        route_after_step2,
        {
            "pipeline": "pipeline",
            "__end__": END,
        },
    )
    
    # pipeline → (条件) → react_error_handler | END
    graph.add_conditional_edges(
        "pipeline",
        route_after_pipeline,
        {
            "react_error_handler": "react_error_handler",
            "__end__": END,
        },
    )
    
    # react_error_handler → (条件) → step1 | step2 | pipeline | END
    graph.add_conditional_edges(
        "react_error_handler",
        route_after_react,
        {
            "step1": "step1",
            "step2": "step2",
            "pipeline": "pipeline",
            "__end__": END,
        },
    )
    
    logger.info("SemanticParser 子图已创建，使用 LangGraph 节点路由循环")
    
    return graph


__all__ = [
    "create_semantic_parser_subgraph",
    "step1_node",
    "step2_node",
    "pipeline_node",
    "react_error_handler_node",
]
