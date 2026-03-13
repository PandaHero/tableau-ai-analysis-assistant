# -*- coding: utf-8 -*-
"""Global understanding 阶段使用的提示词。"""

from __future__ import annotations

from typing import Any, Optional

from ..schemas.prefilter import FeatureExtractionOutput, PrefilterResult

GLOBAL_UNDERSTANDING_SYSTEM_PROMPT = """你负责在字段 grounding 之前完成全局问题理解。

你的任务不是直接选择字段，也不是直接生成可执行查询，而是先判断：
1. 这个问题是否可以用一条 Tableau 查询表达
2. 如果不能，为什么不能
3. 如果需要拆解，应该形成怎样的分析计划

请严格遵守以下原则：
- rule prefilter 和 feature extractor 的结果只是 hints，不是最终结论，不能机械照抄
- 如果问题本质上是 why / 原因分析，必须给出 evidence-building plan，而不是单查
- 如果问题虽然复杂，但仍可由一条查询表达，使用 `analysis_mode=complex_single_query`
- `complex_single_query` 仍属于单查，`single_query_feasible=true`
- 如果需要多步，`analysis_plan` 里的 query step 仍然只是自然语言步骤意图，后续还会重新走 semantic grounding
- 如果输出了多步计划，请尽量为每个 step 设置稳定的 `step_kind`
- 不要生成 SQL、VizQL 或任何可执行 query draft
- 如果缺少比较基线、业务口径、对象范围等关键信息，应优先输出澄清问题
- 只有在 `single_query_feasible=false` 时才填写 `single_query_blockers`
- 只有在确实需要用户补充信息时才设置 `needs_clarification=true`
- `llm_confidence` 使用 0-1 之间的小数

分析模式建议：
- `single_query`: 简单直接单查
- `complex_single_query`: 语义较复杂，但本质仍可由一条查询完成
- `multi_step_analysis`: 下一步依赖前一步结果，或需要多跳拆解
- `why_analysis`: 明确在问原因、驱动因素、根因、背后原因

多步计划要求：
- why / multi-step 模式下，尽量给出 2-5 个步骤
- 第一步通常先验证现象，或拿到主问题首跳结果
- 中间 query step 用于解释轴排序、top-k screening、异常切片定位或补充验证
- 如果某一步显式用于定位异常对象或异常切片，请设置 `targets_anomaly=true`
- 最后一步通常是 synthesis / 总结归因
- step_id 使用 `step-1`, `step-2` 这种格式
"""


def _format_prefilter_result(prefilter_result: Optional[PrefilterResult]) -> list[str]:
    if prefilter_result is None:
        return ["- 无"]

    complexity = [
        item.value if hasattr(item, "value") else str(item)
        for item in (prefilter_result.detected_complexity or [])
    ]
    time_hints = [
        hint.original_expression
        for hint in (prefilter_result.time_hints or [])
        if hint.original_expression
    ]
    computations = [
        item.display_name or item.seed_name
        for item in (prefilter_result.matched_computations or [])
        if item.display_name or item.seed_name
    ]

    return [
        f"- complexity_hints: {', '.join(complexity) if complexity else '无'}",
        f"- time_hints: {', '.join(time_hints) if time_hints else '无'}",
        f"- computation_hints: {', '.join(computations) if computations else '无'}",
        f"- low_confidence: {prefilter_result.low_confidence}",
        f"- match_confidence: {prefilter_result.match_confidence:.2f}",
    ]


def _format_feature_output(feature_output: Optional[FeatureExtractionOutput]) -> list[str]:
    if feature_output is None:
        return ["- 无"]

    return [
        (
            "- required_measures: "
            f"{', '.join(feature_output.required_measures) if feature_output.required_measures else '无'}"
        ),
        (
            "- required_dimensions: "
            f"{', '.join(feature_output.required_dimensions) if feature_output.required_dimensions else '无'}"
        ),
        (
            "- confirmed_time_hints: "
            f"{', '.join(feature_output.confirmed_time_hints) if feature_output.confirmed_time_hints else '无'}"
        ),
        (
            "- confirmed_computations: "
            f"{', '.join(feature_output.confirmed_computations) if feature_output.confirmed_computations else '无'}"
        ),
        f"- confirmation_confidence: {feature_output.confirmation_confidence:.2f}",
        f"- is_degraded: {feature_output.is_degraded}",
    ]


def _format_field_semantic(field_semantic: Optional[dict[str, Any]]) -> list[str]:
    """把字段语义压缩成 why 规划可用的维度/层级事实。"""

    if not field_semantic:
        return ["- 无"]

    lines: list[str] = []
    for field_name, raw_info in field_semantic.items():
        if not isinstance(raw_info, dict):
            continue
        if str(raw_info.get("role") or "").strip().lower() != "dimension":
            continue

        category = str(
            raw_info.get("hierarchy_category")
            or raw_info.get("category")
            or ""
        ).strip()
        level = str(
            raw_info.get("hierarchy_level")
            or raw_info.get("level")
            or ""
        ).strip()
        parent_dimension = str(raw_info.get("parent_dimension") or "").strip()
        child_dimension = str(raw_info.get("child_dimension") or "").strip()
        description = str(raw_info.get("business_description") or "").strip()

        parts = [field_name]
        if category:
            parts.append(f"category={category}")
        if level:
            parts.append(f"level={level}")
        if parent_dimension:
            parts.append(f"parent={parent_dimension}")
        if child_dimension:
            parts.append(f"child={child_dimension}")
        if description:
            parts.append(f"description={description}")

        lines.append(f"- {'; '.join(parts)}")
        if len(lines) >= 10:
            break

    return lines or ["- 无"]


def build_global_understanding_prompt(
    question: str,
    prefilter_result: Optional[PrefilterResult] = None,
    feature_output: Optional[FeatureExtractionOutput] = None,
    field_semantic: Optional[dict[str, Any]] = None,
) -> str:
    """构建 global understanding 阶段的人类消息。"""

    lines = [
        f"主问题: {question.strip() or '无'}",
        "",
        "规则与特征信号（仅供参考，可能不完整或不准确）",
        "[Prefilter]",
        *_format_prefilter_result(prefilter_result),
        "",
        "[Feature Extraction]",
        *_format_feature_output(feature_output),
        "",
        "[Available Dimension Semantics]",
        *_format_field_semantic(field_semantic),
        "",
        "请输出 `GlobalUnderstandingOutput`，并特别注意：",
        "- 如果可单查，请解释为什么当前系统能力足以支持一条查询完成。",
        "- 如果不可单查，请明确 blockers，并给出可执行的分析计划结构。",
        "- 如果问题是 why，plan 不要直接回答原因，而是先设计证据链。",
        "- Available Dimension Semantics 是当前真实可用的维度/层级事实；若需要 candidate_axes，应优先从这些事实中选择，不要凭空杜撰。",
        "- 如果问题复杂但 Tableau 仍能单查，请使用 `complex_single_query`，不要为了保守而强行拆步。",
    ]
    return "\n".join(lines)


__all__ = [
    "GLOBAL_UNDERSTANDING_SYSTEM_PROMPT",
    "build_global_understanding_prompt",
]
