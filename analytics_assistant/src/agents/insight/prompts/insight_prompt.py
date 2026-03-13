# -*- coding: utf-8 -*-
"""Insight Agent 的提示词模板。"""

import json
from typing import Any

from ..schemas.output import InsightOutput

SYSTEM_PROMPT = """你是一个严谨的数据分析助手，负责基于结果文件生成洞察。

你的工作方式必须满足以下要求：
1. 所有结论都必须来自真实文件证据，不能臆造。
2. 先读 `result_manifest.json` 和 `profiles/*`，再按需读取 `preview.json` 或 `chunks/*`。
3. 如果现有证据不足以支持高置信度结论，应降低置信度或明确说明局限。
4. 先使用工具定位证据，再输出最终 JSON，不要直接跳到结论。
5. 输出必须严格符合给定 schema。

最终输出 schema：
```json
{output_schema}
```
""".format(
    output_schema=json.dumps(
        InsightOutput.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )
)

_DEPTH_GUIDANCE = {
    "detailed": (
        "- 优先生成 3 到 5 条高价值结论。\n"
        "- 以描述性洞察为主，必要时补一条诊断性解释。"
    ),
    "comprehensive": (
        "- 优先生成 5 到 8 条结论。\n"
        "- 需要同时覆盖描述性洞察和诊断性解释，并补充更多证据交叉验证。"
    ),
}


def get_system_prompt() -> str:
    """返回 Insight Agent 的基础 system prompt。"""
    return SYSTEM_PROMPT



def build_user_prompt(
    *,
    workspace_summary: str,
    semantic_output_summary: str,
    analysis_depth: str,
) -> str:
    """构建用户提示，强调当前问题和可用证据。"""
    depth_guidance = _DEPTH_GUIDANCE.get(analysis_depth, _DEPTH_GUIDANCE["detailed"])
    return (
        "## 用户问题上下文\n"
        f"{semantic_output_summary}\n\n"
        "## 当前结果工作区\n"
        f"{workspace_summary}\n\n"
        "## 分析深度要求\n"
        f"{depth_guidance}\n\n"
        "请先检查 manifest 和 profiles，必要时再读取 preview 或 chunks，然后基于证据输出洞察结果。"
    )



def build_workspace_summary(
    *,
    workspace_manifest: dict[str, Any],
    data_profile_summary: dict[str, Any],
) -> str:
    """把 manifest 与 profile 摘要压成适合模型阅读的工作区简介。"""
    lines = [
        f"- run_id: {workspace_manifest.get('run_id')}",
        f"- row_count: {workspace_manifest.get('row_count')}",
        f"- column_count: {workspace_manifest.get('column_count')}",
        f"- preview_ref: {workspace_manifest.get('preview_ref')}",
        f"- profiles_ref: {workspace_manifest.get('profiles_ref')}",
        f"- chunks_ref: {workspace_manifest.get('chunks_ref')}",
        "- 可用文件建议顺序: result_manifest.json -> profiles/summary.json -> profiles/data_profile.json -> preview.json -> chunks/*",
        "",
        "### 列概览",
    ]
    for column in data_profile_summary.get("columns") or []:
        column_name = column.get("column_name") or "unknown"
        data_type = column.get("data_type") or "UNKNOWN"
        if column.get("is_numeric"):
            numeric_stats = column.get("numeric_stats") or {}
            stats_parts = []
            if numeric_stats.get("min") is not None:
                stats_parts.append(f"min={numeric_stats['min']}")
            if numeric_stats.get("max") is not None:
                stats_parts.append(f"max={numeric_stats['max']}")
            if numeric_stats.get("avg") is not None:
                stats_parts.append(f"avg={numeric_stats['avg']}")
            stats_text = ", ".join(stats_parts) if stats_parts else "无数值统计"
            lines.append(f"- {column_name} ({data_type}, 数值列): {stats_text}")
            continue

        categorical_stats = column.get("categorical_stats") or {}
        unique_count = categorical_stats.get("unique_count")
        lines.append(
            f"- {column_name} ({data_type}, 分类列): unique_count={unique_count}"
        )
    return "\n".join(lines)



def build_semantic_output_summary(semantic_output_dict: dict[str, Any]) -> str:
    """把语义解析结果压成简洁的问题摘要。"""
    parts: list[str] = []

    restated = str(semantic_output_dict.get("restated_question") or "").strip()
    if restated:
        parts.append(f"- 用户问题: {restated}")

    what = semantic_output_dict.get("what") or {}
    measures = what.get("measures") if isinstance(what, dict) else []
    if isinstance(measures, list) and measures:
        measure_names = []
        for item in measures:
            if isinstance(item, dict):
                field_name = str(item.get("field_name") or "").strip()
                aggregation = str(item.get("aggregation") or "").strip()
                if field_name:
                    measure_names.append(
                        f"{field_name}({aggregation})" if aggregation else field_name
                    )
        if measure_names:
            parts.append(f"- 指标: {', '.join(measure_names)}")

    where = semantic_output_dict.get("where") or {}
    dimensions = where.get("dimensions") if isinstance(where, dict) else []
    if isinstance(dimensions, list) and dimensions:
        dimension_names = []
        for item in dimensions:
            if isinstance(item, dict):
                field_name = str(item.get("field_name") or "").strip()
                if field_name:
                    dimension_names.append(field_name)
        if dimension_names:
            parts.append(f"- 维度: {', '.join(dimension_names)}")

    filters = where.get("filters") if isinstance(where, dict) else []
    if isinstance(filters, list) and filters:
        parts.append(f"- 过滤条件数量: {len(filters)}")

    return "\n".join(parts) if parts else "- 当前没有可用的语义摘要。"
