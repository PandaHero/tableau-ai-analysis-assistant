# -*- coding: utf-8 -*-
"""Replanner Agent 执行入口。"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from langchain.agents.middleware import ModelRetryMiddleware
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from analytics_assistant.src.agents.base import get_llm, stream_llm_structured
from analytics_assistant.src.infra.ai import TaskType
from analytics_assistant.src.infra.config import get_config

from .prompts.replanner_prompt import build_user_prompt, get_system_prompt
from .schemas.output import ReplanDecision

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_RETRY_MAX = 3
_DEFAULT_MODEL_RETRY_BASE_DELAY = 1.0
_DEFAULT_MODEL_RETRY_MAX_DELAY = 30.0
_DEFAULT_MAX_REPLAN_ROUNDS = 10


def _load_replanner_config() -> dict[str, Any]:
    """读取 replanner 配置，失败时回退默认值。"""
    try:
        config = get_config()
        return config.get("agents", {})
    except Exception as exc:
        logger.warning("加载 Replanner Agent 配置失败，使用默认值: %s", exc)
        return {}


def _build_middleware_stack(agents_config: dict[str, Any]) -> list[Any]:
    """构建单次结构化调用的中间件栈。"""
    middleware_config = agents_config.get("middleware", {})
    retry_config = middleware_config.get("model_retry", {})
    return [
        ModelRetryMiddleware(
            max_retries=retry_config.get("max_retries", _DEFAULT_MODEL_RETRY_MAX),
            initial_delay=retry_config.get(
                "base_delay",
                _DEFAULT_MODEL_RETRY_BASE_DELAY,
            ),
            max_delay=retry_config.get("max_delay", _DEFAULT_MODEL_RETRY_MAX_DELAY),
        ),
    ]


async def run_replanner_agent(
    insight_output_dict: dict[str, Any],
    semantic_output_dict: dict[str, Any],
    evidence_bundle_dict: dict[str, Any],
    conversation_history: Optional[list[dict[str, str]]] = None,
    replan_history: Optional[list[dict[str, Any]]] = None,
    analysis_depth: str = "detailed",
    field_semantic: Optional[dict[str, Any]] = None,
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
) -> ReplanDecision:
    """执行 replanner，并输出结构化重规划决策。"""
    del conversation_history

    agents_config = _load_replanner_config()
    replanner_config = agents_config.get("replanner", {})
    max_rounds = replanner_config.get("max_replan_rounds", _DEFAULT_MAX_REPLAN_ROUNDS)
    current_round = len(replan_history or [])
    if current_round >= max_rounds:
        logger.info(
            "已达到重规划轮数上限，直接停止重规划: current_round=%s, max_rounds=%s",
            current_round,
            max_rounds,
        )
        return ReplanDecision(
            should_replan=False,
            reason=f"已达到最大重规划轮数上限（{max_rounds} 轮）",
            suggested_questions=[],
        )

    llm = get_llm(agent_name="replanner", task_type=TaskType.REPLANNING)
    middleware_stack = _build_middleware_stack(agents_config)

    system_prompt = get_system_prompt()
    user_prompt = build_user_prompt(
        insight_summary=_build_insight_summary(insight_output_dict),
        semantic_output_summary=_build_semantic_output_summary(semantic_output_dict),
        evidence_bundle_summary=_build_evidence_bundle_summary(evidence_bundle_dict),
        replan_history_summary=_build_replan_history_summary(replan_history),
        analysis_depth=analysis_depth,
        field_semantic_summary=_build_field_semantic_summary(field_semantic),
    )
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    logger.info(
        "Replanner Agent 启动: analysis_depth=%s, source=%s, replan_history_count=%s",
        analysis_depth,
        str(evidence_bundle_dict.get("source") or "").strip() or "unknown",
        len(replan_history or []),
    )
    result = await stream_llm_structured(
        llm=llm,
        messages=messages,
        output_model=ReplanDecision,
        middleware=middleware_stack,
        on_token=on_token,
        on_thinking=on_thinking,
    )
    logger.info(
        "Replanner Agent 完成: should_replan=%s, reason=%s",
        result.should_replan,
        result.reason[:120],
    )
    return result


def _build_insight_summary(insight_output_dict: dict[str, Any]) -> str:
    """把洞察输出压缩成 replanner 易消费的摘要。"""
    findings = insight_output_dict.get("findings") or []
    summary = str(insight_output_dict.get("summary") or "").strip()
    confidence = float(insight_output_dict.get("overall_confidence") or 0.0)

    parts = []
    if summary:
        parts.append(f"摘要: {summary}")
    parts.append(f"整体置信度: {confidence:.2f}")
    parts.append(f"发现数量: {len(findings)}")
    for index, finding in enumerate(findings[:5], start=1):
        if not isinstance(finding, dict):
            continue
        description = str(finding.get("description") or "").strip()
        if not description:
            continue
        finding_type = str(finding.get("finding_type") or "comparison").strip()
        analysis_level = str(finding.get("analysis_level") or "diagnostic").strip()
        finding_confidence = float(finding.get("confidence") or 0.0)
        parts.append(
            f"{index}. [{finding_type}/{analysis_level}] {description} "
            f"(置信度 {finding_confidence:.2f})"
        )
    return "\n".join(parts)


def _build_semantic_output_summary(semantic_output_dict: dict[str, Any]) -> str:
    """构建当前问题语义摘要。"""
    restated_question = str(
        semantic_output_dict.get("restated_question") or ""
    ).strip()
    intent = str(semantic_output_dict.get("intent") or "").strip()
    parts = []
    if restated_question:
        parts.append(f"问题: {restated_question}")
    if intent:
        parts.append(f"意图: {intent}")
    return "\n".join(parts) if parts else "（无语义摘要）"


def _build_evidence_bundle_summary(evidence_bundle_dict: dict[str, Any]) -> str:
    """构建 evidence bundle 摘要，替代旧 data profile 摘要。"""
    source = str(evidence_bundle_dict.get("source") or "").strip() or "unknown"
    result_profile = evidence_bundle_dict.get("result_profile") or {}
    step_artifacts = evidence_bundle_dict.get("step_artifacts") or []
    validated_axes = evidence_bundle_dict.get("validated_axes") or []
    axis_scores = evidence_bundle_dict.get("axis_scores") or []
    anomalous_entities = evidence_bundle_dict.get("anomalous_entities") or []
    key_entities = evidence_bundle_dict.get("key_entities") or []
    open_questions = evidence_bundle_dict.get("open_questions") or []
    latest_summary = str(evidence_bundle_dict.get("latest_summary") or "").strip()
    insight_summary = str(evidence_bundle_dict.get("insight_summary") or "").strip()

    parts = [f"证据来源: {source}"]
    if latest_summary:
        parts.append(f"最新证据摘要: {latest_summary}")
    if insight_summary:
        parts.append(f"最终洞察摘要: {insight_summary}")

    if isinstance(result_profile, dict) and result_profile:
        row_count = int(result_profile.get("row_count") or 0)
        column_count = int(result_profile.get("column_count") or 0)
        parts.append(f"结果画像: {row_count} 行，{column_count} 列")
        columns_profile = result_profile.get("columns_profile") or []
        if isinstance(columns_profile, list) and columns_profile:
            numeric_columns = [
                str(item.get("column_name") or "")
                for item in columns_profile
                if isinstance(item, dict) and bool(item.get("is_numeric"))
            ]
            categorical_columns = [
                str(item.get("column_name") or "")
                for item in columns_profile
                if isinstance(item, dict) and not bool(item.get("is_numeric"))
            ]
            if numeric_columns:
                parts.append(f"数值列: {', '.join(filter(None, numeric_columns[:5]))}")
            if categorical_columns:
                parts.append(f"分类列: {', '.join(filter(None, categorical_columns[:5]))}")

    if step_artifacts:
        parts.append(f"多步证据数: {len(step_artifacts)}")
        for index, artifact in enumerate(step_artifacts[:4], start=1):
            if not isinstance(artifact, dict):
                continue
            title = str(artifact.get("title") or artifact.get("step_id") or f"step-{index}")
            summary = str(artifact.get("table_summary") or "").strip()
            axes = artifact.get("validated_axes") or []
            entity_scope = artifact.get("entity_scope") or []
            line_parts = [f"{index}. {title}"]
            if summary:
                line_parts.append(summary)
            if axes:
                line_parts.append(f"已验证轴: {', '.join(str(item) for item in axes[:3])}")
            if entity_scope:
                line_parts.append(f"实体范围: {', '.join(str(item) for item in entity_scope[:3])}")
            parts.append(" | ".join(line_parts))

    if validated_axes:
        parts.append(f"已验证解释轴: {', '.join(str(item) for item in validated_axes[:5])}")
    if axis_scores:
        top_scores = []
        for raw_score in axis_scores[:5]:
            if not isinstance(raw_score, dict):
                continue
            axis = str(raw_score.get("axis") or "").strip()
            explained_share = float(raw_score.get("explained_share") or 0.0)
            if axis:
                top_scores.append(f"{axis}({explained_share:.0%})")
        if top_scores:
            parts.append(f"解释轴排序: {', '.join(top_scores)}")
    if anomalous_entities:
        parts.append(
            "异常对象: " + ", ".join(str(item) for item in anomalous_entities[:5])
        )
    if key_entities:
        parts.append(
            "关键实体: " + ", ".join(str(item) for item in key_entities[:5])
        )
    if open_questions:
        parts.append(
            "未解决问题: " + ", ".join(str(item) for item in open_questions[:5])
        )

    return "\n".join(parts)


def _build_replan_history_summary(
    replan_history: Optional[list[dict[str, Any]]],
) -> str:
    """构建历史重规划摘要，避免循环分析。"""
    if not replan_history:
        return ""

    parts = []
    for index, decision in enumerate(replan_history, start=1):
        should_replan = bool(decision.get("should_replan", False))
        reason = str(decision.get("reason") or "").strip()
        new_question = str(decision.get("new_question") or "").strip()
        if not new_question:
            candidate_questions = decision.get("candidate_questions") or []
            if candidate_questions and isinstance(candidate_questions[0], dict):
                new_question = str(candidate_questions[0].get("question") or "").strip()
        if should_replan and new_question:
            parts.append(f"{index}. 继续到“{new_question}” | 原因: {reason[:80]}")
        else:
            parts.append(f"{index}. 停止重规划 | 原因: {reason[:80]}")
    return "\n".join(parts)


def _build_field_semantic_summary(
    field_semantic: Optional[dict[str, Any]],
) -> str:
    """给 replanner 提供可用字段范围，减少无效 follow-up。"""
    if not field_semantic:
        return ""

    dimensions: list[str] = []
    measures: list[str] = []
    for field_name, info in field_semantic.items():
        if not isinstance(info, dict):
            continue
        role = str(info.get("role") or "").strip()
        category = str(
            info.get("hierarchy_category")
            or info.get("category")
            or info.get("measure_category")
            or ""
        ).strip()
        aliases = info.get("aliases") or []
        business_description = str(info.get("business_description") or "").strip()
        alias_text = f"（别名: {', '.join(aliases[:3])}）" if aliases else ""
        category_text = f"[{category}]" if category else ""
        description_text = f" - {business_description}" if business_description else ""
        line = f"- {field_name} {category_text}{alias_text}{description_text}".strip()
        if role == "dimension":
            dimensions.append(line)
        elif role == "measure":
            measures.append(line)

    parts = []
    if measures:
        parts.append(f"度量字段 ({len(measures)}):")
        parts.extend(measures[:10])
    if dimensions:
        parts.append(f"维度字段 ({len(dimensions)}):")
        parts.extend(dimensions[:10])
    return "\n".join(parts)


__all__ = [
    "run_replanner_agent",
]
