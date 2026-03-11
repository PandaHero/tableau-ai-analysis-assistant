# -*- coding: utf-8 -*-
"""
Replanner Agent 执行逻辑

使用 stream_llm_structured + MiddlewareRunner 实现单次 LLM 调用：
- token 级流式输出（on_token / on_thinking 回调）
- ModelRetryMiddleware 处理 LLM 调用重试
- Pydantic model_validator 自动验证 ReplanDecision 一致性

公开 API：
- run_replanner_agent(): 执行 Replanner Agent，返回 ReplanDecision
"""
import json
import logging
from typing import Any, Awaitable, Callable, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain.agents.middleware import ModelRetryMiddleware

from analytics_assistant.src.agents.base import get_llm, stream_llm_structured
from analytics_assistant.src.infra.ai import TaskType
from analytics_assistant.src.infra.config import get_config

from .prompts.replanner_prompt import build_user_prompt, get_system_prompt
from .schemas.output import ReplanDecision

logger = logging.getLogger(__name__)

# 默认配置常量
_DEFAULT_MODEL_RETRY_MAX = 3
_DEFAULT_MODEL_RETRY_BASE_DELAY = 1.0
_DEFAULT_MODEL_RETRY_MAX_DELAY = 30.0
_DEFAULT_MAX_REPLAN_ROUNDS = 10

def _load_replanner_config() -> dict[str, Any]:
    """从 app.yaml 加载 Replanner Agent 配置。

    Returns:
        配置字典
    """
    try:
        config = get_config()
        return config.get("agents", {})
    except Exception as e:
        logger.warning(f"加载 Replanner Agent 配置失败，使用默认值: {e}")
        return {}

def _build_middleware_stack(agents_config: dict[str, Any]) -> list[Any]:
    """构建中间件栈（仅 ModelRetry）。

    Args:
        agents_config: agents 配置节

    Returns:
        中间件实例列表
    """
    mw_config = agents_config.get("middleware", {})
    model_retry_config = mw_config.get("model_retry", {})

    model_retry_mw = ModelRetryMiddleware(
        max_retries=model_retry_config.get("max_retries", _DEFAULT_MODEL_RETRY_MAX),
        initial_delay=model_retry_config.get("base_delay", _DEFAULT_MODEL_RETRY_BASE_DELAY),
        max_delay=model_retry_config.get("max_delay", _DEFAULT_MODEL_RETRY_MAX_DELAY),
    )

    return [model_retry_mw]

async def run_replanner_agent(
    insight_output_dict: dict[str, Any],
    semantic_output_dict: dict[str, Any],
    data_profile_dict: dict[str, Any],
    conversation_history: Optional[list[dict[str, str]]] = None,
    replan_history: Optional[list[dict[str, Any]]] = None,
    analysis_depth: str = "detailed",
    field_semantic: Optional[dict[str, Any]] = None,
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
) -> ReplanDecision:
    """执行 Replanner Agent。

    基于洞察结果、语义输出、数据画像和历史信息，
    决定是否需要后续分析并生成新问题或建议。

    Args:
        insight_output_dict: 洞察输出（序列化后的字典）
        semantic_output_dict: 语义解析输出（序列化后的字典）
        data_profile_dict: 数据画像（序列化后的字典）
        conversation_history: 对话历史（可选）
        replan_history: 重规划历史（之前各轮的 ReplanDecision，可选）
        analysis_depth: 分析深度（"detailed" 或 "comprehensive"）
        field_semantic: 字段语义信息（可选，用于让 LLM 感知数据源可用字段）
        on_token: Token 流式回调
        on_thinking: 思考过程回调

    Returns:
        ReplanDecision 重规划决策

    Raises:
        RuntimeError: LLM 调用失败
        ValueError: 参数无效
    """
    # 加载配置
    agents_config = _load_replanner_config()

    # 检查重规划轮数上限
    replanner_config = agents_config.get("replanner", {})
    max_rounds = replanner_config.get("max_replan_rounds", _DEFAULT_MAX_REPLAN_ROUNDS)
    current_round = len(replan_history) if replan_history else 0

    if current_round >= max_rounds:
        logger.info(
            f"已达到重规划轮数上限 ({current_round}/{max_rounds})，停止重规划"
        )
        return ReplanDecision(
            should_replan=False,
            reason=f"已达到最大重规划轮数上限 ({max_rounds} 轮)",
            suggested_questions=[],
        )

    # 获取 LLM
    llm = get_llm(agent_name="replanner", task_type=TaskType.REPLANNING)

    # 构建中间件栈
    middleware_stack = _build_middleware_stack(agents_config)

    # 构建摘要
    insight_summary = _build_insight_summary(insight_output_dict)
    semantic_output_summary = _build_semantic_output_summary(semantic_output_dict)
    data_profile_summary = _build_data_profile_summary(data_profile_dict)
    replan_history_summary = _build_replan_history_summary(replan_history)
    field_semantic_summary = _build_field_semantic_summary(field_semantic)

    # 构建消息
    system_prompt = get_system_prompt()
    user_prompt = build_user_prompt(
        insight_summary=insight_summary,
        semantic_output_summary=semantic_output_summary,
        data_profile_summary=data_profile_summary,
        replan_history_summary=replan_history_summary,
        analysis_depth=analysis_depth,
        field_semantic_summary=field_semantic_summary,
    )

    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    logger.info(
        f"Replanner Agent 启动: analysis_depth={analysis_depth}, "
        f"replan_history_count={len(replan_history) if replan_history else 0}"
    )

    # 执行单次 LLM 调用
    result = await stream_llm_structured(
        llm=llm,
        messages=messages,
        output_model=ReplanDecision,
        middleware=middleware_stack,
        on_token=on_token,
        on_thinking=on_thinking,
    )

    logger.info(
        f"Replanner Agent 完成: should_replan={result.should_replan}, "
        f"reason={result.reason[:80]}..."
    )

    return result

def _build_insight_summary(insight_output_dict: dict[str, Any]) -> str:
    """构建洞察输出摘要。

    Args:
        insight_output_dict: 洞察输出字典

    Returns:
        摘要文本
    """
    findings = insight_output_dict.get("findings", [])
    summary = insight_output_dict.get("summary", "")
    confidence = insight_output_dict.get("overall_confidence", 0.0)

    parts = []
    if summary:
        parts.append(f"**摘要**: {summary}")
    parts.append(f"**整体置信度**: {confidence:.2f}")
    parts.append(f"**发现数量**: {len(findings)}")

    for i, finding in enumerate(findings, 1):
        f_type = finding.get("finding_type", "unknown")
        f_level = finding.get("analysis_level", "descriptive")
        f_desc = finding.get("description", "")
        f_conf = finding.get("confidence", 0.0)
        parts.append(f"\n### 发现 {i} [{f_type}/{f_level}] (置信度: {f_conf:.2f})")
        parts.append(f_desc)

    return "\n".join(parts)

def _build_semantic_output_summary(semantic_output_dict: dict[str, Any]) -> str:
    """构建语义解析输出摘要。

    Args:
        semantic_output_dict: 语义解析输出字典

    Returns:
        摘要文本
    """
    parts = []

    restated = semantic_output_dict.get("restated_question", "")
    if restated:
        parts.append(f"**用户问题**: {restated}")

    intent = semantic_output_dict.get("intent", "")
    if intent:
        parts.append(f"**分析意图**: {intent}")

    return "\n".join(parts) if parts else "（无语义解析信息）"

def _build_data_profile_summary(data_profile_dict: dict[str, Any]) -> str:
    """构建数据画像摘要。

    Args:
        data_profile_dict: 数据画像字典

    Returns:
        摘要文本
    """
    row_count = data_profile_dict.get("row_count", 0)
    column_count = data_profile_dict.get("column_count", 0)
    columns = data_profile_dict.get("columns_profile", [])

    parts = [
        f"- 总行数: {row_count}",
        f"- 总列数: {column_count}",
    ]

    numeric_cols = [c for c in columns if c.get("is_numeric")]
    categorical_cols = [c for c in columns if not c.get("is_numeric")]

    if numeric_cols:
        names = [c.get("column_name", "") for c in numeric_cols]
        parts.append(f"- 数值列: {', '.join(names)}")

    if categorical_cols:
        names = [c.get("column_name", "") for c in categorical_cols]
        parts.append(f"- 分类列: {', '.join(names)}")

    return "\n".join(parts)

def _build_replan_history_summary(
    replan_history: Optional[list[dict[str, Any]]],
) -> str:
    """构建重规划历史摘要。

    Args:
        replan_history: 重规划历史列表

    Returns:
        摘要文本（空字符串表示无历史）
    """
    if not replan_history:
        return ""

    parts = []
    for i, decision in enumerate(replan_history, 1):
        should_replan = decision.get("should_replan", False)
        reason = decision.get("reason", "")
        new_question = decision.get("new_question", "")
        if not new_question:
            candidate_questions = decision.get("candidate_questions") or []
            if candidate_questions and isinstance(candidate_questions[0], dict):
                new_question = str(candidate_questions[0].get("question") or "")

        if should_replan and new_question:
            parts.append(f"- 第 {i} 轮: 重规划 → \"{new_question}\" (原因: {reason[:60]}...)")
        else:
            parts.append(f"- 第 {i} 轮: 不重规划 (原因: {reason[:60]}...)")

    return "\n".join(parts)

def _build_field_semantic_summary(
    field_semantic: Optional[dict[str, Any]],
) -> str:
    """构建数据源字段语义摘要，供 Replanner LLM 感知可用字段。

    Args:
        field_semantic: 字段语义字典（字段名 → 属性）

    Returns:
        摘要文本（空字符串表示无语义信息）
    """
    if not field_semantic:
        return ""

    dimensions: list[str] = []
    measures: list[str] = []

    for field_name, info in field_semantic.items():
        if not isinstance(info, dict):
            continue
        role = info.get("role", "")
        aliases = info.get("aliases") or []
        desc = info.get("business_description") or ""
        category = (
            info.get("hierarchy_category")
            or info.get("category")
            or info.get("measure_category")
            or ""
        )

        alias_text = f"（别名: {', '.join(aliases[:3])}）" if aliases else ""
        category_text = f"[{category}]" if category else ""
        desc_text = f" - {desc}" if desc else ""
        entry = f"  - {field_name} {category_text}{alias_text}{desc_text}"

        if role == "dimension":
            dimensions.append(entry)
        elif role == "measure":
            measures.append(entry)

    if not dimensions and not measures:
        return ""

    parts = []
    if measures:
        parts.append(f"**度量字段** ({len(measures)} 个):")
        parts.extend(measures[:10])
    if dimensions:
        parts.append(f"**维度字段** ({len(dimensions)} 个):")
        parts.extend(dimensions[:10])

    return "\n".join(parts)
