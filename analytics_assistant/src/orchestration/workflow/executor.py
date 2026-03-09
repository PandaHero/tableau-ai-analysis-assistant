# -*- coding: utf-8 -*-
"""
WorkflowExecutor - 工作流执行器

编排完整的查询执行流程：
1. 认证（获取 Tableau auth token）
2. 数据源解析 + 数据模型加载（TableauDataLoader）
3. 字段语义推断（FieldSemanticInference）
4. 创建 WorkflowContext 并注入 SSE 回调
5. 执行 semantic_parser 子图

使用示例:
    executor = WorkflowExecutor(tableau_username="admin")
    async for event in executor.execute_stream(
        question="各区域销售额",
        datasource_name="销售数据",
    ):
        # event: {"type": "token", "content": "..."} 等
        yield format_sse_event(event)
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from analytics_assistant.src.agents.semantic_parser.graph import (
    compile_semantic_parser_graph,
)
from analytics_assistant.src.agents.insight.components.data_profiler import DataProfiler
from analytics_assistant.src.agents.insight.components.data_store import DataStore
from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
    AnalysisPlan,
    AnalysisPlanStep,
    EvidenceContext,
    PlanStepType,
    StepArtifact,
    parse_analysis_plan as resolve_analysis_plan,
)
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.error_sanitizer import sanitize_error_message
from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
from analytics_assistant.src.platform.tableau.client import VizQLClient
from analytics_assistant.src.platform.tableau.data_loader import (
    TableauDataLoader,
    schedule_datasource_artifact_preparation,
)
from analytics_assistant.src.core.schemas.execute_result import ColumnInfo, ExecuteResult
from analytics_assistant.src.core.schemas.semantic_output import SemanticOutput

from .callbacks import SSECallbacks
from .context import WorkflowContext, create_workflow_config

logger = logging.getLogger(__name__)

# 默认超时（秒）
_DEFAULT_WORKFLOW_TIMEOUT = 180  # 增加到 180 秒，给字段语义推断和 LLM 调用足够时间

def _merge_metrics(*metric_groups: Optional[dict[str, Any]]) -> dict[str, Any]:
    """按顺序合并多组指标，后者覆盖前者。"""
    merged: dict[str, Any] = {}
    for metrics in metric_groups:
        if metrics:
            merged.update(metrics)
    return merged


async def _invoke_insight_agent(**kwargs: Any) -> Any:
    """懒加载 Insight Agent，避免可选依赖在模块导入阶段触发。"""
    from analytics_assistant.src.agents.insight.graph import run_insight_agent

    return await run_insight_agent(**kwargs)


async def _invoke_replanner_agent(**kwargs: Any) -> Any:
    """懒加载 Replanner Agent，避免可选依赖在模块导入阶段触发。"""
    from analytics_assistant.src.agents.replanner.graph import run_replanner_agent

    return await run_replanner_agent(**kwargs)

async def _execute_semantic_query(
    *,
    ctx: WorkflowContext,
    datasource_luid: str,
    semantic_raw: dict[str, Any],
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    """执行语义查询并返回统一结构，便于后续独立拆分查询执行服务。"""
    started_at = asyncio.get_running_loop().time()
    try:
        semantic_output_obj = SemanticOutput.model_validate(semantic_raw)
        platform_kwargs: dict[str, Any] = {
            "data_model": ctx.data_model,
            "field_samples": ctx.field_samples,
        }
        if ctx.auth is not None:
            if hasattr(ctx.auth, "api_key"):
                platform_kwargs["api_key"] = ctx.auth.api_key
            if hasattr(ctx.auth, "site"):
                platform_kwargs["site"] = ctx.auth.site

        execute_result = await ctx.platform_adapter.execute_query(
            semantic_output=semantic_output_obj,
            datasource_id=datasource_luid,
            **platform_kwargs,
        )
        elapsed_ms = (asyncio.get_running_loop().time() - started_at) * 1000
        logger.info(
            f"[工作流] 查询执行成功: request_id={request_id}, rows={execute_result.row_count}, "
            f"cols={len(execute_result.columns)}"
        )
        return {
            "success": True,
            "query_execute_ms": elapsed_ms,
            "tableData": {
                "columns": [
                    {
                        "name": col.name,
                        "dataType": col.data_type,
                        "isDimension": col.is_dimension,
                        "isMeasure": col.is_measure,
                    }
                    for col in execute_result.columns
                ],
                "rows": execute_result.data,
                "rowCount": execute_result.row_count,
                "executionTimeMs": execute_result.execution_time_ms,
            },
        }
    except Exception as exec_err:
        elapsed_ms = (asyncio.get_running_loop().time() - started_at) * 1000
        logger.error(f"[工作流] 查询执行失败: request_id={request_id}, error={exec_err}")
        return {
            "success": False,
            "query_execute_ms": elapsed_ms,
            "error": sanitize_error_message(f"查询执行失败: {exec_err}"),
        }


def _parse_analysis_plan(
    raw: Any,
    raw_global_understanding: Any = None,
) -> Optional[AnalysisPlan]:
    """安全解析 analysis_plan。"""
    return resolve_analysis_plan(
        raw_analysis_plan=raw,
        raw_global_understanding=raw_global_understanding,
    )


def _normalize_followup_questions(
    primary_question: Optional[str],
    suggested_questions: Optional[list[str]],
) -> list[str]:
    """合并并去重 replanner 产出的后续问题。"""
    merged: list[str] = []
    seen: set[str] = set()
    for question in [primary_question, *(suggested_questions or [])]:
        normalized = str(question or "").strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(normalized)
    return merged


def _normalize_candidate_questions(
    *,
    primary_question: Optional[str],
    suggested_questions: Optional[list[str]],
    candidate_questions: Optional[list[Any]],
) -> list[dict[str, Any]]:
    """将 replanner 输出统一收敛为结构化候选问题列表。"""
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _coerce_priority(value: Any, fallback: int) -> int:
        try:
            return max(1, min(int(value), 10))
        except (TypeError, ValueError):
            return fallback

    def _coerce_gain(value: Any, fallback: float = 0.5) -> float:
        try:
            return max(0.0, min(float(value), 1.0))
        except (TypeError, ValueError):
            return fallback

    def _append_candidate(
        question: Any,
        *,
        question_type: str = "followup",
        priority: int,
        expected_info_gain: float = 0.5,
        rationale: str = "",
        estimated_mode: str = "single_query",
    ) -> None:
        normalized_question = str(question or "").strip()
        if not normalized_question:
            return
        key = normalized_question.lower()
        if key in seen:
            return
        seen.add(key)
        normalized.append({
            "question": normalized_question,
            "questionType": str(question_type or "followup").strip() or "followup",
            "priority": priority,
            "expectedInfoGain": expected_info_gain,
            "rationale": str(rationale or "").strip(),
            "estimatedMode": str(estimated_mode or "single_query").strip() or "single_query",
        })

    for index, raw in enumerate(candidate_questions or [], start=1):
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        if isinstance(raw, dict):
            _append_candidate(
                raw.get("question"),
                question_type=str(raw.get("question_type") or "followup"),
                priority=_coerce_priority(raw.get("priority"), index),
                expected_info_gain=_coerce_gain(raw.get("expected_info_gain")),
                rationale=str(raw.get("rationale") or ""),
                estimated_mode=str(raw.get("estimated_mode") or "single_query"),
            )
        elif isinstance(raw, str):
            _append_candidate(raw, priority=index)

    if primary_question:
        _append_candidate(
            primary_question,
            question_type="primary_followup",
            priority=1,
        )

    for index, question in enumerate(
        suggested_questions or [],
        start=2 if primary_question else max(1, len(normalized) + 1),
    ):
        _append_candidate(question, priority=index)

    normalized.sort(key=lambda item: (item["priority"], item["question"].lower()))
    return normalized


def _select_auto_continue_question(
    *,
    current_question: str,
    candidate_questions: list[dict[str, Any]],
    replan_history: Optional[list[dict[str, Any]]] = None,
) -> Optional[str]:
    """为 auto_continue 选择下一轮问题，避免循环重复。"""
    seen_questions = {str(current_question or "").strip().lower()}
    for decision in replan_history or []:
        for candidate in _normalize_candidate_questions(
            primary_question=decision.get("new_question"),
            suggested_questions=decision.get("suggested_questions"),
            candidate_questions=decision.get("candidate_questions"),
        ):
            seen_questions.add(candidate["question"].lower())

    for candidate in candidate_questions:
        normalized = str(candidate.get("question") or "").strip()
        if normalized and normalized.lower() not in seen_questions:
            return normalized
    return None


def _build_replan_followup_history(
    history: Optional[list[dict[str, str]]],
    *,
    previous_question: str,
    round_summary: str,
    replan_reason: str,
    next_question: str,
) -> list[dict[str, str]]:
    """为自动继续的新问题构建简短上下文。"""
    base_history = list(history or [])
    lines = [f"上一轮问题：{previous_question}"]
    if round_summary.strip():
        lines.append(f"上一轮结论：{round_summary.strip()}")
    if replan_reason.strip():
        lines.append(f"继续原因：{replan_reason.strip()}")
    lines.append(f"当前继续分析的问题：{next_question}")
    base_history.append({
        "role": "assistant",
        "content": "以下是上一轮分析上下文：\n" + "\n".join(lines),
    })
    return base_history


def _table_data_to_execute_result(
    table_data: Optional[dict[str, Any]],
    *,
    query_id: Optional[str] = None,
) -> Optional[ExecuteResult]:
    """将前端友好的 tableData 结构恢复为 ExecuteResult。"""
    if not isinstance(table_data, dict):
        return None

    columns_raw = table_data.get("columns") or []
    rows_raw = table_data.get("rows") or []
    if not isinstance(columns_raw, list) or not isinstance(rows_raw, list):
        return None

    columns: list[ColumnInfo] = []
    column_names: list[str] = []
    for index, raw_column in enumerate(columns_raw):
        if not isinstance(raw_column, dict):
            continue
        name = str(raw_column.get("name") or f"column_{index + 1}")
        column_names.append(name)
        columns.append(
            ColumnInfo(
                name=name,
                data_type=str(raw_column.get("dataType") or "STRING"),
                is_dimension=bool(raw_column.get("isDimension", False)),
                is_measure=bool(raw_column.get("isMeasure", False)),
            )
        )

    if not column_names and rows_raw and isinstance(rows_raw[0], dict):
        column_names = [str(key) for key in rows_raw[0].keys()]
        columns = [ColumnInfo(name=name) for name in column_names]

    normalized_rows: list[dict[str, Any]] = []
    for raw_row in rows_raw:
        if isinstance(raw_row, dict):
            if column_names:
                normalized_rows.append(
                    {name: raw_row.get(name) for name in column_names}
                )
            else:
                normalized_rows.append({str(key): value for key, value in raw_row.items()})
            continue

        if isinstance(raw_row, (list, tuple)) and column_names:
            normalized_rows.append(
                {
                    name: raw_row[idx] if idx < len(raw_row) else None
                    for idx, name in enumerate(column_names)
                }
            )

    return ExecuteResult(
        data=normalized_rows,
        columns=columns,
        row_count=int(table_data.get("rowCount") or len(normalized_rows)),
        execution_time_ms=int(table_data.get("executionTimeMs") or 0),
        query_id=query_id,
    )


def _serialize_plan_step(
    step: AnalysisPlanStep,
    *,
    index: int,
    total: int,
) -> dict[str, Any]:
    """将计划步骤转换为前端可消费的结构。"""
    return {
        "stepId": step.step_id or f"step-{index}",
        "index": index,
        "total": total,
        "title": step.title,
        "question": step.question,
        "purpose": step.purpose or "",
        "stepType": step.step_type.value,
        "usesPrimaryQuery": step.uses_primary_query,
        "dependsOn": step.depends_on,
        "semanticFocus": step.semantic_focus,
        "expectedOutput": step.expected_output or "",
    }


def _build_initial_evidence_context(original_question: str) -> EvidenceContext:
    """初始化多步分析的证据上下文。"""
    return EvidenceContext(primary_question=original_question)


def _dedupe_keep_order(values: list[str]) -> list[str]:
    """字符串列表去重并保留原有顺序。"""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _extract_entity_scope(
    table_data: Optional[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[str]:
    """从结果表中提取可复用的对象范围。"""
    if not isinstance(table_data, dict):
        return []

    columns = table_data.get("columns") or []
    rows = table_data.get("rows") or []
    if not isinstance(columns, list) or not isinstance(rows, list):
        return []

    column_names = [
        str(column.get("name"))
        for column in columns
        if isinstance(column, dict) and column.get("name")
    ]
    dimension_names = [
        str(column.get("name"))
        for column in columns
        if isinstance(column, dict)
        and column.get("name")
        and (
            bool(column.get("isDimension"))
            or not bool(column.get("isMeasure"))
        )
    ]

    values: list[str] = []
    for raw_row in rows[:20]:
        if isinstance(raw_row, dict):
            row = {str(key): value for key, value in raw_row.items()}
        elif isinstance(raw_row, (list, tuple)) and column_names:
            row = {
                name: raw_row[index] if index < len(raw_row) else None
                for index, name in enumerate(column_names)
            }
        else:
            continue

        for name in dimension_names[:2]:
            value = row.get(name)
            if value is None:
                continue
            values.append(str(value))

    return _dedupe_keep_order(values)[:limit]


def _extract_validated_axes(
    step_payload: dict[str, Any],
    semantic_summary: Optional[dict[str, Any]] = None,
) -> list[str]:
    """从步骤与语义摘要中提取已验证的解释轴。"""
    semantic_summary = semantic_summary or {}
    dimensions = semantic_summary.get("dimensions") or []
    semantic_focus = step_payload.get("semanticFocus") or []
    return _dedupe_keep_order([
        *[str(item) for item in dimensions if item],
        *[str(item) for item in semantic_focus if item],
    ])


def _step_targets_anomaly(step_payload: dict[str, Any]) -> bool:
    """粗略判断当前步骤是否在定位异常对象。"""
    haystack = " ".join([
        str(step_payload.get("title") or ""),
        str(step_payload.get("purpose") or ""),
        str(step_payload.get("question") or ""),
    ]).lower()
    return any(keyword in haystack for keyword in ["异常", "定位", "归因"])


def _append_step_artifact(
    evidence_context: EvidenceContext,
    *,
    step_payload: dict[str, Any],
    query_id: Optional[str] = None,
    restated_question: Optional[str] = None,
    table_data: Optional[dict[str, Any]] = None,
    summary_text: Optional[str] = None,
    blocked_reason: Optional[str] = None,
    semantic_summary: Optional[dict[str, Any]] = None,
    key_findings: Optional[list[str]] = None,
    entity_scope: Optional[list[str]] = None,
    validated_axes: Optional[list[str]] = None,
    open_questions: Optional[list[str]] = None,
) -> EvidenceContext:
    """将已完成步骤沉淀到结构化证据上下文中。"""
    updated_context = evidence_context.model_copy(deep=True)
    step_type = PlanStepType(step_payload.get("stepType", PlanStepType.QUERY.value))
    resolved_summary = summary_text or _summarize_table_data(table_data or {})
    resolved_entity_scope = _dedupe_keep_order(
        list(entity_scope or _extract_entity_scope(table_data))
    )
    resolved_validated_axes = _dedupe_keep_order(
        list(validated_axes or _extract_validated_axes(step_payload, semantic_summary))
    )
    resolved_key_findings = _dedupe_keep_order(
        list(key_findings or ([resolved_summary] if resolved_summary else []))
    )
    resolved_open_questions = _dedupe_keep_order(list(open_questions or []))
    updated_context.step_artifacts.append(
        StepArtifact(
            step_id=str(step_payload.get("stepId") or f"step-{step_payload.get('index', '?')}"),
            title=step_payload.get("title", "步骤"),
            step_type=step_type,
            query_id=query_id,
            restated_question=restated_question,
            table_summary=resolved_summary,
            key_findings=resolved_key_findings,
            entity_scope=resolved_entity_scope,
            validated_axes=resolved_validated_axes,
            blocked_reason=blocked_reason,
        )
    )
    updated_context.key_entities = _dedupe_keep_order(
        [*updated_context.key_entities, *resolved_entity_scope]
    )
    updated_context.validated_axes = _dedupe_keep_order(
        [*updated_context.validated_axes, *resolved_validated_axes]
    )
    updated_context.open_questions = _dedupe_keep_order(
        [*updated_context.open_questions, *resolved_open_questions]
    )
    if _step_targets_anomaly(step_payload):
        updated_context.anomalous_entities = _dedupe_keep_order(
            [*updated_context.anomalous_entities, *resolved_entity_scope]
        )
    return updated_context


def _serialize_insight_payload(insight_output_dict: dict[str, Any]) -> dict[str, Any]:
    """规范化 insight 事件结构。"""
    findings_payload: list[dict[str, Any]] = []
    for raw_finding in insight_output_dict.get("findings") or []:
        if not isinstance(raw_finding, dict):
            continue
        findings_payload.append({
            "findingType": raw_finding.get("finding_type", "comparison"),
            "analysisLevel": raw_finding.get("analysis_level", "descriptive"),
            "description": raw_finding.get("description", ""),
            "confidence": raw_finding.get("confidence", 0.0),
            "supportingData": raw_finding.get("supporting_data") or {},
        })

    return {
        "summary": str(insight_output_dict.get("summary") or ""),
        "overallConfidence": float(insight_output_dict.get("overall_confidence") or 0.0),
        "findings": findings_payload,
    }


def _build_evidence_insight_output(
    original_question: str,
    evidence_context: EvidenceContext,
    completed_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """基于累积证据构造统一洞察摘要，供 replanner 复用。"""
    summary = ""
    for artifact in reversed(evidence_context.step_artifacts):
        if artifact.step_type == PlanStepType.SYNTHESIS and artifact.table_summary:
            summary = artifact.table_summary
            break
    if not summary:
        summary = _build_synthesis_step_summary(original_question, completed_steps)

    findings: list[dict[str, Any]] = []
    for artifact in evidence_context.step_artifacts:
        descriptions = artifact.key_findings or ([artifact.table_summary] if artifact.table_summary else [])
        for description in descriptions[:2]:
            normalized = str(description or "").strip()
            if not normalized:
                continue
            findings.append({
                "finding_type": "comparison",
                "analysis_level": "diagnostic",
                "description": normalized,
                "supporting_data": {
                    "step_id": artifact.step_id,
                    "title": artifact.title,
                    "query_id": artifact.query_id,
                    "entity_scope": artifact.entity_scope,
                    "validated_axes": artifact.validated_axes,
                },
                "confidence": 0.72,
            })
        if len(findings) >= 6:
            break

    if not findings:
        findings.append({
            "finding_type": "comparison",
            "analysis_level": "diagnostic",
            "description": summary,
            "supporting_data": {
                "step_count": len(evidence_context.step_artifacts),
            },
            "confidence": 0.65,
        })

    overall_confidence = min(0.9, 0.55 + 0.05 * len(findings))
    return {
        "summary": summary,
        "overall_confidence": overall_confidence,
        "findings": findings,
    }


def _build_evidence_data_profile_dict(
    evidence_context: EvidenceContext,
) -> dict[str, Any]:
    """将累积证据转换为 replanner 可消费的数据概览。"""
    return {
        "row_count": len(evidence_context.step_artifacts),
        "column_count": 5,
        "columns_profile": [
            {"column_name": "step_id", "data_type": "STRING", "is_numeric": False},
            {"column_name": "title", "data_type": "STRING", "is_numeric": False},
            {"column_name": "table_summary", "data_type": "STRING", "is_numeric": False},
            {"column_name": "entity_scope", "data_type": "STRING", "is_numeric": False},
            {"column_name": "validated_axes", "data_type": "STRING", "is_numeric": False},
        ],
    }


def _build_step_insight_output(
    step_payload: dict[str, Any],
    summary_text: str,
    semantic_summary: Optional[dict[str, Any]],
    table_data: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """为单个 query step 构造轻量结构化洞察。"""
    semantic_summary = semantic_summary or {}
    entity_scope = _extract_entity_scope(table_data)
    validated_axes = _extract_validated_axes(step_payload, semantic_summary)
    findings = [{
        "finding_type": "comparison",
        "analysis_level": "diagnostic",
        "description": summary_text,
        "supporting_data": {
            "step_id": step_payload.get("stepId"),
            "title": step_payload.get("title"),
            "entity_scope": entity_scope,
            "validated_axes": validated_axes,
        },
        "confidence": 0.66,
    }]
    return {
        "summary": summary_text,
        "overall_confidence": 0.66,
        "findings": findings,
    }


def _extract_insight_key_findings(insight_output_dict: Optional[dict[str, Any]]) -> list[str]:
    """提取 insight 输出中的关键信息描述，回写到 EvidenceContext。"""
    if not isinstance(insight_output_dict, dict):
        return []

    findings: list[str] = []
    for raw_finding in insight_output_dict.get("findings") or []:
        if not isinstance(raw_finding, dict):
            continue
        description = str(raw_finding.get("description") or "").strip()
        if description:
            findings.append(description)

    if findings:
        return _dedupe_keep_order(findings)

    summary = str(insight_output_dict.get("summary") or "").strip()
    return [summary] if summary else []


def _get_primary_plan_step(
    analysis_plan: AnalysisPlan,
) -> tuple[Optional[int], Optional[AnalysisPlanStep]]:
    """找到复用主问题首跳查询的步骤。"""
    total = len(analysis_plan.sub_questions)
    for index, step in enumerate(analysis_plan.sub_questions, start=1):
        if step.step_type == PlanStepType.QUERY and step.uses_primary_query:
            return index, step
    for index, step in enumerate(analysis_plan.sub_questions, start=1):
        if step.step_type == PlanStepType.QUERY:
            return index, step
    return None, None


def _summarize_table_data(table_data: dict[str, Any]) -> str:
    """生成轻量表格结果摘要。"""
    if not isinstance(table_data, dict):
        return "未返回可展示的数据结果。"

    row_count = int(table_data.get("rowCount") or 0)
    columns = table_data.get("columns") or []
    column_names = [
        column.get("name", "")
        for column in columns
        if isinstance(column, dict) and column.get("name")
    ]
    preview_columns = "、".join(column_names[:3]) if column_names else "无字段信息"
    return f"返回 {row_count} 行数据，主要字段包括 {preview_columns}。"


def _build_query_step_summary(
    step_payload: dict[str, Any],
    semantic_summary: dict[str, Any],
    table_data: dict[str, Any],
) -> str:
    """构建查询步骤的用户可读摘要。"""
    measures = semantic_summary.get("measures") or []
    dimensions = semantic_summary.get("dimensions") or []
    filters = semantic_summary.get("filters") or []

    measure_text = "、".join(measures[:3]) if measures else "核心指标"
    dimension_text = "、".join(dimensions[:3]) if dimensions else "整体"
    filter_text = f"，筛选字段 { '、'.join(filters[:2]) }" if filters else ""

    return (
        f"{step_payload['title']}已完成：围绕 {measure_text} 按 {dimension_text} 进行查询"
        f"{filter_text}。{_summarize_table_data(table_data)}"
    )


def _build_synthesis_step_summary(
    original_question: str,
    completed_steps: list[dict[str, Any]],
) -> str:
    """基于已完成的查询步骤生成累积证据摘要。"""
    query_steps = [step for step in completed_steps if step.get("summary_text")]
    if not query_steps:
        return f"围绕“{original_question}”已生成分析计划，但还没有足够的查询结果用于汇总。"

    lines = [f"围绕“{original_question}”已完成 {len(query_steps)} 个查询步骤："]
    for item in query_steps:
        payload = item.get("step") or {}
        summary_text = item.get("summary_text", "")
        lines.append(f"{payload.get('index', '?')}. {payload.get('title', '步骤')}: {summary_text}")
    lines.append("当前已形成逐步累积的证据链，可继续基于这些结果做洞察或自动重规划。")
    return "\n".join(lines)


def _build_followup_history(
    history: Optional[list[dict[str, str]]],
    original_question: str,
    completed_steps: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """为 follow-up 子问题注入简短的前序步骤上下文。"""
    base_history = list(history or [])
    if not completed_steps:
        return base_history

    lines = [f"原始问题：{original_question}"]
    for item in completed_steps[-2:]:
        payload = item.get("step") or {}
        summary_text = item.get("summary_text")
        if summary_text:
            lines.append(f"步骤{payload.get('index', '?')} {payload.get('title', '步骤')}：{summary_text}")

    base_history.append({
        "role": "assistant",
        "content": "以下是已完成的分析上下文：\n" + "\n".join(lines),
    })
    return base_history

class WorkflowExecutor:
    """工作流执行器。

    负责编排完整的查询工作流：认证 → 数据模型加载 → 字段语义 → 语义解析。

    重要说明：
    - semantic_parser 子图已经是完整的端到端流程（15+ 节点）
    - field_mapper 在 semantic_parser 子图内部调用
    - field_semantic 在数据准备阶段通过 WorkflowContext.load_field_semantic() 调用

    Attributes:
        _tableau_username: Tableau 用户名
        _timeout: 工作流执行超时（秒）
    """

    def __init__(self, tableau_username: str, request_id: Optional[str] = None):
        """初始化 WorkflowExecutor。

        Args:
            tableau_username: Tableau 用户名（用于认证和数据隔离）
            request_id: 请求标识，用于串联 API/SSE/执行日志
        """
        self._tableau_username = tableau_username
        self._request_id = request_id
        self._timeout = self._load_timeout()

    def _load_timeout(self) -> int:
        """从 app.yaml 读取工作流超时配置。

        Returns:
            超时秒数
        """
        try:
            config = get_config()
            return config.get("api", {}).get(
                "timeout", {},
            ).get("workflow_execution", _DEFAULT_WORKFLOW_TIMEOUT)
        except Exception as e:
            logger.warning(f"读取超时配置失败，使用默认值: {e}")
            return _DEFAULT_WORKFLOW_TIMEOUT

    async def execute_stream(
        self,
        question: str,
        datasource_name: str,
        history: Optional[list[dict[str, str]]] = None,
        language: str = "zh",
        analysis_depth: str = "detailed",
        replan_mode: str = "user_select",
        selected_candidate_question: Optional[str] = None,
        session_id: Optional[str] = None,
        _replan_history: Optional[list[dict[str, Any]]] = None,
        _emit_complete: bool = True,
    ) -> AsyncIterator[dict[str, Any]]:
        """执行工作流并返回 SSE 事件流。

        内部流程：
        1. 认证（获取 Tableau auth token）
        2. 数据模型加载（TableauDataLoader，内部解析 name → LUID）
        3. 字段语义推断
        4. 创建 WorkflowContext + 注入 SSE 回调
        5. 执行 semantic_parser 子图

        Args:
            question: 用户问题
            datasource_name: 数据源名称（前端传入）
            history: 对话历史（已裁剪）
            language: 语言（"zh" 或 "en"）
            analysis_depth: 分析深度
            replan_mode: 重规划继续策略（user_select / auto_continue / stop）
            selected_candidate_question: 用户已选择的候选问题
            session_id: 会话 ID
            _replan_history: 内部递归自动继续时复用的重规划历史
            _emit_complete: 内部递归自动继续时是否发送 complete 事件

        Yields:
            SSE 事件字典，如 {"type": "token", "content": "..."}
        """
        event_queue: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue()
        callbacks = SSECallbacks(event_queue, language=language)
        loop = asyncio.get_running_loop()
        workflow_started_at = loop.time()
        stage_metrics: dict[str, Any] = {}
        collected_metrics: dict[str, Any] = {}
        question = selected_candidate_question or question
        history = list(history or [])
        replan_history_records: list[dict[str, Any]] = list(_replan_history or [])
        stage_metrics["replan_mode"] = replan_mode
        if selected_candidate_question:
            stage_metrics["selected_candidate_question_used"] = True

        def _record_stage(metric_name: str, started_at: float) -> float:
            elapsed_ms = (loop.time() - started_at) * 1000
            stage_metrics[metric_name] = elapsed_ms
            return elapsed_ms

        def _collect_metrics(metrics: Optional[dict[str, Any]]) -> None:
            if metrics:
                collected_metrics.update(metrics)

        def _current_metrics(*metric_groups: Optional[dict[str, Any]]) -> dict[str, Any]:
            return _merge_metrics(
                collected_metrics,
                stage_metrics,
                *metric_groups,
            )

        def _mark_workflow_end(
            *,
            cancelled: bool = False,
            failed: bool = False,
            timed_out: bool = False,
        ) -> float:
            elapsed_ms = (loop.time() - workflow_started_at) * 1000
            stage_metrics["workflow_executor_ms"] = elapsed_ms
            if cancelled:
                stage_metrics["workflow_cancelled"] = True
            if failed:
                stage_metrics["workflow_failed"] = True
            if timed_out:
                stage_metrics["workflow_timed_out"] = True
            return elapsed_ms

        async def _emit_parse_result_event(
            parse_result: dict[str, Any],
            *,
            plan_step: Optional[dict[str, Any]] = None,
            step_metrics: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            """推送语义解析摘要事件。"""
            semantic_raw = parse_result.get("semantic_output", {})
            summary = _build_semantic_summary(semantic_raw)
            if summary:
                event: dict[str, Any] = {
                    "type": "parse_result",
                    "success": True,
                    "query_id": parse_result.get("query_id", ""),
                    "summary": summary,
                    "is_degraded": bool(parse_result.get("is_degraded", False)),
                    "query_cache_hit": bool(parse_result.get("query_cache_hit", False)),
                    "optimization_metrics": _current_metrics(step_metrics),
                }
                if plan_step:
                    event["planStep"] = plan_step
                if (
                    parse_result.get("analysis_plan")
                    and not parse_result.get("global_understanding")
                ):
                    event["analysis_plan"] = parse_result.get("analysis_plan")
                if parse_result.get("global_understanding"):
                    event["global_understanding"] = parse_result.get("global_understanding")
                await event_queue.put(event)
            return summary

        async def _emit_insight_event(
            insight_output_dict: dict[str, Any],
            *,
            source: str,
            plan_step: Optional[dict[str, Any]] = None,
            step_metrics: Optional[dict[str, Any]] = None,
        ) -> None:
            """发送结构化洞察事件。"""
            event: dict[str, Any] = {
                "type": "insight",
                "source": source,
                **_serialize_insight_payload(insight_output_dict),
                "optimization_metrics": _current_metrics(step_metrics),
            }
            if plan_step:
                event["planStep"] = plan_step
            await event_queue.put(event)

        async def _emit_replan_events(
            *,
            replan_decision: Any,
            source: str,
            step_metrics: Optional[dict[str, Any]] = None,
            mode: str = "user_select",
            action: str = "await_user_select",
            selected_question: Optional[str] = None,
        ) -> list[dict[str, Any]]:
            """发送结构化 replan / candidate_questions / suggestions 事件。"""
            candidate_questions = _normalize_candidate_questions(
                primary_question=getattr(replan_decision, "new_question", None),
                suggested_questions=getattr(replan_decision, "suggested_questions", None),
                candidate_questions=getattr(replan_decision, "candidate_questions", None),
            )
            questions = [item["question"] for item in candidate_questions]
            metrics = _current_metrics(step_metrics)
            if candidate_questions:
                await event_queue.put({
                    "type": "candidate_questions",
                    "source": source,
                    "questions": candidate_questions,
                    "optimization_metrics": metrics,
                })
            await event_queue.put({
                "type": "replan",
                "source": source,
                "mode": mode,
                "action": action,
                "shouldReplan": bool(getattr(replan_decision, "should_replan", False)),
                "reason": str(getattr(replan_decision, "reason", "") or ""),
                "newQuestion": getattr(replan_decision, "new_question", None),
                "selectedQuestion": selected_question,
                "questions": questions,
                "candidateQuestions": candidate_questions,
                "optimization_metrics": metrics,
            })
            if questions:
                await event_queue.put({
                    "type": "suggestions",
                    "source": source,
                    "questions": questions,
                    "candidateQuestions": candidate_questions,
                    "optimization_metrics": metrics,
                })
            return candidate_questions

        async def _handle_replan_outcome(
            *,
            replan_decision: Any,
            source: str,
            round_history: list[dict[str, str]],
            round_summary: str,
            step_metrics: Optional[dict[str, Any]] = None,
        ) -> None:
            """统一处理 replan 事件投影与 auto_continue。"""
            candidate_questions = _normalize_candidate_questions(
                primary_question=getattr(replan_decision, "new_question", None),
                suggested_questions=getattr(replan_decision, "suggested_questions", None),
                candidate_questions=getattr(replan_decision, "candidate_questions", None),
            )
            action = "stop"
            selected_question: Optional[str] = None

            if replan_mode == "user_select":
                action = "await_user_select" if candidate_questions else "stop"
            elif replan_mode == "auto_continue":
                if bool(getattr(replan_decision, "should_replan", False)):
                    selected_question = _select_auto_continue_question(
                        current_question=question,
                        candidate_questions=candidate_questions,
                        replan_history=replan_history_records,
                    )
                action = "auto_continue" if selected_question else "stop"

            await _emit_replan_events(
                replan_decision=replan_decision,
                source=source,
                step_metrics=step_metrics,
                mode=replan_mode,
                action=action,
                selected_question=selected_question,
            )

            if hasattr(replan_decision, "model_dump"):
                replan_history_records.append(replan_decision.model_dump())

            if action != "auto_continue" or not selected_question:
                return

            stage_metrics["auto_continue_triggered"] = True
            stage_metrics["auto_continue_rounds"] = int(
                stage_metrics.get("auto_continue_rounds", 0)
            ) + 1
            followup_history = _build_replan_followup_history(
                round_history,
                previous_question=question,
                round_summary=round_summary,
                replan_reason=str(getattr(replan_decision, "reason", "") or ""),
                next_question=selected_question,
            )

            async for followup_event in self.execute_stream(
                question=selected_question,
                datasource_name=datasource_name,
                history=followup_history,
                language=language,
                analysis_depth=analysis_depth,
                replan_mode=replan_mode,
                session_id=session_id,
                _replan_history=replan_history_records,
                _emit_complete=False,
            ):
                await event_queue.put(followup_event)

        async def _run_post_query_agents(
            *,
            semantic_raw: dict[str, Any],
            query_id: Optional[str],
            table_data: Optional[dict[str, Any]],
        ) -> Optional[Any]:
            """在单次查询完成后补充洞察与重规划建议。"""
            execute_result = _table_data_to_execute_result(table_data, query_id=query_id)
            if execute_result is None or execute_result.is_empty():
                stage_metrics["insight_skipped"] = True
                return None

            store_id = str(query_id or self._request_id or f"{datasource_luid}-{int(loop.time() * 1000)}")
            data_store = DataStore(store_id=store_id)
            data_store.save(execute_result)

            try:
                profiler = DataProfiler()
                data_profile = profiler.generate(execute_result)
                data_store.set_profile(data_profile)

                insight_output = None
                insight_started_at = loop.time()
                await callbacks.on_node_start("insight_agent")
                try:
                    insight_output = await _invoke_insight_agent(
                        data_store=data_store,
                        data_profile=data_profile,
                        semantic_output_dict=semantic_raw,
                        analysis_depth=analysis_depth,
                        on_token=callbacks.on_token,
                        on_thinking=callbacks.on_thinking,
                    )
                    stage_metrics["insight_ms"] = (loop.time() - insight_started_at) * 1000
                    stage_metrics["insight_findings_count"] = len(insight_output.findings)
                except Exception as exc:
                    logger.warning("查询后 insight agent 执行失败，跳过洞察闭环: %s", exc)
                    stage_metrics["insight_failed"] = True
                finally:
                    await callbacks.on_node_end("insight_agent")

                if insight_output is None:
                    return None

                await _emit_insight_event(
                    insight_output.model_dump(),
                    source="single_query",
                )

                replanner_started_at = loop.time()
                await callbacks.on_node_start("replanner_agent")
                try:
                    replan_decision = await _invoke_replanner_agent(
                        insight_output_dict=insight_output.model_dump(),
                        semantic_output_dict=semantic_raw,
                        data_profile_dict=data_profile.model_dump(),
                        conversation_history=history,
                        replan_history=replan_history_records,
                        analysis_depth=analysis_depth,
                        on_token=callbacks.on_token,
                        on_thinking=callbacks.on_thinking,
                    )
                    stage_metrics["replanner_ms"] = (
                        loop.time() - replanner_started_at
                    ) * 1000
                    stage_metrics["replanner_should_replan"] = replan_decision.should_replan
                    stage_metrics["replanner_suggested_questions_count"] = len(
                        replan_decision.suggested_questions
                    )
                    stage_metrics["replanner_candidate_questions_count"] = len(
                        _normalize_candidate_questions(
                            primary_question=replan_decision.new_question,
                            suggested_questions=replan_decision.suggested_questions,
                            candidate_questions=getattr(
                                replan_decision, "candidate_questions", None
                            ),
                        )
                    )
                    await _handle_replan_outcome(
                        replan_decision=replan_decision,
                        source="single_query",
                        round_history=history,
                        round_summary=insight_output.summary,
                    )
                    return replan_decision
                except Exception as exc:
                    logger.warning("查询后 replanner agent 执行失败，跳过建议生成: %s", exc)
                    stage_metrics["replanner_failed"] = True
                    return None
                finally:
                    await callbacks.on_node_end("replanner_agent")
            finally:
                data_store.cleanup()

        async def _run_post_planner_agents(
            *,
            semantic_raw: dict[str, Any],
            evidence_context: EvidenceContext,
            completed_steps: list[dict[str, Any]],
        ) -> Optional[Any]:
            """多步 planner 完成后，基于累积证据生成洞察与重规划建议。"""
            if not completed_steps:
                stage_metrics["planner_replanner_skipped"] = True
                return None

            insight_output_dict = _build_evidence_insight_output(
                question,
                evidence_context,
                completed_steps,
            )
            await _emit_insight_event(
                insight_output_dict,
                source="planner_synthesis",
            )
            stage_metrics["planner_insight_findings_count"] = len(
                insight_output_dict.get("findings") or []
            )

            replanner_started_at = loop.time()
            await callbacks.on_node_start("replanner_agent")
            try:
                replan_decision = await _invoke_replanner_agent(
                    insight_output_dict=insight_output_dict,
                    semantic_output_dict=semantic_raw,
                    data_profile_dict=_build_evidence_data_profile_dict(evidence_context),
                    conversation_history=_build_followup_history(
                        history,
                        question,
                        completed_steps,
                    ),
                    replan_history=replan_history_records,
                    analysis_depth=analysis_depth,
                    on_token=callbacks.on_token,
                    on_thinking=callbacks.on_thinking,
                )
                stage_metrics["planner_replanner_ms"] = (
                    loop.time() - replanner_started_at
                ) * 1000
                stage_metrics["planner_replanner_should_replan"] = (
                    replan_decision.should_replan
                )
                stage_metrics["planner_replanner_suggested_questions_count"] = len(
                    replan_decision.suggested_questions
                )
                stage_metrics["planner_replanner_candidate_questions_count"] = len(
                    _normalize_candidate_questions(
                        primary_question=replan_decision.new_question,
                        suggested_questions=replan_decision.suggested_questions,
                        candidate_questions=getattr(
                            replan_decision, "candidate_questions", None
                        ),
                    )
                )
                await _handle_replan_outcome(
                    replan_decision=replan_decision,
                    source="planner_synthesis",
                    round_history=_build_followup_history(
                        history,
                        question,
                        completed_steps,
                    ),
                    round_summary=insight_output_dict.get("summary", ""),
                )
                return replan_decision
            except Exception as exc:
                logger.warning("多步分析后 replanner 执行失败，跳过后续建议: %s", exc)
                stage_metrics["planner_replanner_failed"] = True
                return None
            finally:
                await callbacks.on_node_end("replanner_agent")

        async def _run_plan_step_insight_round(
            *,
            semantic_raw: dict[str, Any],
            plan_step: dict[str, Any],
            query_id: Optional[str],
            table_data: Optional[dict[str, Any]],
            semantic_summary: Optional[dict[str, Any]],
            step_metrics: Optional[dict[str, Any]] = None,
        ) -> dict[str, Any]:
            """优先为 query step 运行真实 InsightAgent，失败时回退到轻量 summary。"""
            fallback_output = _build_step_insight_output(
                plan_step,
                _build_query_step_summary(
                    plan_step,
                    semantic_summary or {},
                    table_data or {},
                ) if table_data else "",
                semantic_summary,
                table_data,
            )
            execute_result = _table_data_to_execute_result(table_data, query_id=query_id)
            if execute_result is None or execute_result.is_empty():
                stage_metrics["planner_step_insight_skipped"] = int(
                    stage_metrics.get("planner_step_insight_skipped", 0)
                ) + 1
                return fallback_output

            store_id = str(
                query_id
                or self._request_id
                or f"{datasource_luid}-plan-step-{plan_step.get('stepId')}"
            )
            data_store = DataStore(store_id=store_id)
            data_store.save(execute_result)

            try:
                profiler = DataProfiler()
                data_profile = profiler.generate(execute_result)
                data_store.set_profile(data_profile)

                insight_started_at = loop.time()
                await callbacks.on_node_start("insight_agent")
                try:
                    insight_output = await _invoke_insight_agent(
                        data_store=data_store,
                        data_profile=data_profile,
                        semantic_output_dict=semantic_raw,
                        analysis_depth=analysis_depth,
                        on_token=callbacks.on_token,
                        on_thinking=callbacks.on_thinking,
                    )
                    elapsed_ms = (loop.time() - insight_started_at) * 1000
                    stage_metrics["planner_step_insight_total_ms"] = (
                        float(stage_metrics.get("planner_step_insight_total_ms", 0.0))
                        + elapsed_ms
                    )
                    stage_metrics["planner_step_insight_rounds"] = int(
                        stage_metrics.get("planner_step_insight_rounds", 0)
                    ) + 1
                    if step_metrics is not None:
                        step_metrics["planner_step_insight_ms"] = elapsed_ms
                    return insight_output.model_dump()
                except Exception as exc:
                    logger.warning("query step insight agent 执行失败，回退轻量洞察: %s", exc)
                    stage_metrics["planner_step_insight_failed"] = int(
                        stage_metrics.get("planner_step_insight_failed", 0)
                    ) + 1
                    return fallback_output
                finally:
                    await callbacks.on_node_end("insight_agent")
            finally:
                data_store.cleanup()

        async def _execute_query_from_semantic(
            *,
            ctx: WorkflowContext,
            datasource_luid: str,
            semantic_raw: dict[str, Any],
            semantic_query: Any,
            plan_step: Optional[dict[str, Any]] = None,
            semantic_summary: Optional[dict[str, Any]] = None,
            step_metrics: Optional[dict[str, Any]] = None,
            fail_hard: bool = True,
        ) -> dict[str, Any]:
            """执行单次语义查询，并在需要时附带计划步骤信息。"""
            if not semantic_query:
                error_message = "缺少可执行查询骨架"
                if plan_step:
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "error",
                        "step": plan_step,
                        "error": error_message,
                        "optimization_metrics": _current_metrics(step_metrics),
                    })
                elif fail_hard:
                    await event_queue.put({
                        "type": "error",
                        "error": error_message,
                        "optimization_metrics": _current_metrics(step_metrics),
                    })
                return {
                    "success": False,
                    "error": error_message,
                }

            if plan_step is None:
                await event_queue.put({
                    "type": "status",
                    "message": "正在执行数据查询...",
                })

            query_execution = await _execute_semantic_query(
                ctx=ctx,
                datasource_luid=datasource_luid,
                semantic_raw=semantic_raw,
                request_id=self._request_id,
            )

            if plan_step:
                stage_metrics["planner_query_execute_total_ms"] = (
                    float(stage_metrics.get("planner_query_execute_total_ms", 0.0))
                    + float(query_execution["query_execute_ms"])
                )
                stage_metrics["planner_query_steps_executed"] = (
                    int(stage_metrics.get("planner_query_steps_executed", 0)) + 1
                )
                if plan_step.get("usesPrimaryQuery") and "query_execute_ms" not in stage_metrics:
                    stage_metrics["query_execute_ms"] = query_execution["query_execute_ms"]
            else:
                stage_metrics["query_execute_ms"] = query_execution["query_execute_ms"]
                stage_metrics["query_execute_failed"] = not bool(query_execution["success"])

            if query_execution["success"]:
                data_event: dict[str, Any] = {
                    "type": "data",
                    "tableData": query_execution["tableData"],
                    "optimization_metrics": _current_metrics(step_metrics),
                }
                summary_text = ""
                if plan_step:
                    summary_text = _build_query_step_summary(
                        plan_step,
                        semantic_summary or {},
                        query_execution["tableData"],
                    )
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "completed",
                        "step": plan_step,
                        "queryId": semantic_raw.get("query_id", ""),
                        "semanticSummary": semantic_summary or {},
                        "summary": summary_text,
                        "optimization_metrics": _current_metrics(step_metrics),
                    })
                    data_event["planStep"] = plan_step
                    data_event["summary"] = summary_text

                await event_queue.put(data_event)
                return {
                    "success": True,
                    "tableData": query_execution["tableData"],
                    "summary_text": summary_text,
                }

            if plan_step:
                stage_metrics["planner_failed_step"] = plan_step.get("index")
                await event_queue.put({
                    "type": "plan_step",
                    "status": "error",
                    "step": plan_step,
                    "error": query_execution["error"],
                    "optimization_metrics": _current_metrics(step_metrics),
                })
                return {
                    "success": False,
                    "error": query_execution["error"],
                }

            await event_queue.put({
                "type": "error",
                "error": query_execution["error"],
                "optimization_metrics": _current_metrics(step_metrics),
            })
            return {
                "success": False,
                "error": query_execution["error"],
            }

        async def _execute_analysis_plan(
            *,
            graph: Any,
            ctx: WorkflowContext,
            datasource_luid: str,
            parse_result: dict[str, Any],
            analysis_plan: AnalysisPlan,
        ) -> None:
            """按 analysis_plan 顺序执行多步查询和汇总步骤。"""
            total_steps = len(analysis_plan.sub_questions)
            if not analysis_plan.needs_planning or total_steps == 0:
                return

            evidence_context = _build_initial_evidence_context(question)
            planner_event = {
                "type": "planner",
                "planMode": analysis_plan.plan_mode.value,
                "goal": analysis_plan.goal or "",
                "executionStrategy": analysis_plan.execution_strategy,
                "reasoningFocus": analysis_plan.reasoning_focus,
                "steps": [
                    _serialize_plan_step(step, index=index, total=total_steps)
                    for index, step in enumerate(analysis_plan.sub_questions, start=1)
                ],
                "optimization_metrics": _current_metrics(),
            }
            await event_queue.put(planner_event)

            stage_metrics["planner_multistep_enabled"] = True
            stage_metrics["planner_steps_total"] = total_steps
            stage_metrics["planner_query_steps_total"] = sum(
                1
                for step in analysis_plan.sub_questions
                if step.step_type == PlanStepType.QUERY
            )
            stage_metrics["planner_synthesis_steps_total"] = sum(
                1
                for step in analysis_plan.sub_questions
                if step.step_type == PlanStepType.SYNTHESIS
            )

            completed_steps: list[dict[str, Any]] = []
            primary_index, primary_step = _get_primary_plan_step(analysis_plan)

            if primary_index is not None and primary_step is not None:
                primary_payload = _serialize_plan_step(
                    primary_step,
                    index=primary_index,
                    total=total_steps,
                )
                await _emit_parse_result_event(parse_result, plan_step=primary_payload)
                await event_queue.put({
                    "type": "plan_step",
                    "status": "running",
                    "step": primary_payload,
                    "message": f"正在执行规划步骤 {primary_index}/{total_steps}",
                    "optimization_metrics": _current_metrics(),
                })
                semantic_raw = parse_result.get("semantic_output", {})
                semantic_summary = _build_semantic_summary(semantic_raw)
                query_result = await _execute_query_from_semantic(
                    ctx=ctx,
                    datasource_luid=datasource_luid,
                    semantic_raw=semantic_raw,
                    semantic_query=parse_result.get("query"),
                    plan_step=primary_payload,
                    semantic_summary=semantic_summary,
                )
                if not query_result["success"]:
                    return
                completed_steps.append({
                    "step": primary_payload,
                    "summary_text": query_result.get("summary_text", ""),
                    "tableData": query_result.get("tableData"),
                    "semantic_summary": semantic_summary,
                })
                primary_step_insight = await _run_plan_step_insight_round(
                    semantic_raw=semantic_raw,
                    plan_step=primary_payload,
                    query_id=parse_result.get("query_id"),
                    table_data=query_result.get("tableData"),
                    semantic_summary=semantic_summary,
                )
                await _emit_insight_event(
                    primary_step_insight,
                    source="plan_step",
                    plan_step=primary_payload,
                )
                stage_metrics["planner_step_insights_emitted"] = int(
                    stage_metrics.get("planner_step_insights_emitted", 0)
                ) + 1
                evidence_context = _append_step_artifact(
                    evidence_context,
                    step_payload=primary_payload,
                    query_id=parse_result.get("query_id"),
                    restated_question=semantic_raw.get("restated_question"),
                    table_data=query_result.get("tableData"),
                    summary_text=query_result.get("summary_text", ""),
                    semantic_summary=semantic_summary,
                    key_findings=_extract_insight_key_findings(primary_step_insight),
                )
                stage_metrics["planner_completed_steps"] = len(completed_steps)
            else:
                await _emit_parse_result_event(parse_result)

            for index, step in enumerate(analysis_plan.sub_questions, start=1):
                if primary_index is not None and index == primary_index:
                    continue

                step_payload = _serialize_plan_step(step, index=index, total=total_steps)

                if step.step_type == PlanStepType.SYNTHESIS:
                    synthesis_summary = _build_synthesis_step_summary(
                        question,
                        completed_steps,
                    )
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "completed",
                        "step": step_payload,
                        "summary": synthesis_summary,
                        "evidenceCount": len(completed_steps),
                        "optimization_metrics": _current_metrics(),
                    })
                    completed_steps.append({
                        "step": step_payload,
                        "summary_text": synthesis_summary,
                    })
                    evidence_context = _append_step_artifact(
                        evidence_context,
                        step_payload=step_payload,
                        summary_text=synthesis_summary,
                        key_findings=[synthesis_summary],
                        open_questions=analysis_plan.risk_flags,
                    )
                    stage_metrics["planner_completed_steps"] = len(completed_steps)
                    continue

                await event_queue.put({
                    "type": "plan_step",
                    "status": "running",
                    "step": step_payload,
                    "message": f"正在执行规划步骤 {index}/{total_steps}",
                    "optimization_metrics": _current_metrics(),
                })

                followup_history = _build_followup_history(history, question, completed_steps)
                followup_started_at = loop.time()
                followup_config = create_workflow_config(
                    thread_id=f"{session_id or f'stream-{datasource_luid}'}:plan-step-{index}",
                    context=ctx,
                    on_token=callbacks.on_token,
                    on_thinking=callbacks.on_thinking,
                )
                followup_state = await graph.ainvoke(
                    {
                        "question": step.question,
                        "datasource_luid": datasource_luid,
                        "history": followup_history,
                        "chat_history": followup_history,
                        "current_step_intent": {
                            **step.model_dump(mode="json"),
                            "step_id": step.step_id or f"step-{index}",
                            "goal": step.goal or step.purpose,
                        },
                        "evidence_context": evidence_context.model_dump(),
                        "current_time": ctx.current_time,
                        "language": language,
                        "analysis_depth": analysis_depth,
                    },
                    followup_config,
                )
                followup_parse_ms = (loop.time() - followup_started_at) * 1000
                stage_metrics["planner_followup_parse_total_ms"] = (
                    float(stage_metrics.get("planner_followup_parse_total_ms", 0.0))
                    + followup_parse_ms
                )
                stage_metrics["planner_followup_steps_executed"] = (
                    int(stage_metrics.get("planner_followup_steps_executed", 0)) + 1
                )
                followup_parse_result = followup_state.get("parse_result") or {}
                step_metrics = _merge_metrics(
                    followup_state.get("optimization_metrics"),
                    followup_parse_result.get("optimization_metrics"),
                    {"planner_followup_parse_ms": followup_parse_ms},
                )

                if followup_state.get("needs_clarification"):
                    stage_metrics["planner_blocked_step"] = index
                    clarification_event = {
                        "type": "clarification",
                        "question": followup_state.get("clarification_question", ""),
                        "options": followup_state.get("clarification_options") or [],
                        "source": followup_state.get("clarification_source", ""),
                        "optimization_metrics": _current_metrics(step_metrics),
                    }
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "clarification",
                        "step": step_payload,
                        "question": clarification_event["question"],
                        "options": clarification_event["options"],
                        "source": clarification_event["source"],
                        "optimization_metrics": clarification_event["optimization_metrics"],
                    })
                    await event_queue.put(clarification_event)
                    return

                if not followup_parse_result.get("success"):
                    stage_metrics["planner_failed_step"] = index
                    await event_queue.put({
                        "type": "plan_step",
                        "status": "error",
                        "step": step_payload,
                        "error": "多步分析未生成可执行解析结果",
                        "optimization_metrics": _current_metrics(step_metrics),
                    })
                    return

                semantic_raw = followup_parse_result.get("semantic_output", {})
                semantic_summary = await _emit_parse_result_event(
                    followup_parse_result,
                    plan_step=step_payload,
                    step_metrics=step_metrics,
                )
                query_result = await _execute_query_from_semantic(
                    ctx=ctx,
                    datasource_luid=datasource_luid,
                    semantic_raw=semantic_raw,
                    semantic_query=followup_parse_result.get("query"),
                    plan_step=step_payload,
                    semantic_summary=semantic_summary,
                    step_metrics=step_metrics,
                    fail_hard=False,
                )
                if not query_result["success"]:
                    return
                completed_steps.append({
                    "step": step_payload,
                    "summary_text": query_result.get("summary_text", ""),
                    "tableData": query_result.get("tableData"),
                    "semantic_summary": semantic_summary,
                })
                step_insight_output = await _run_plan_step_insight_round(
                    semantic_raw=semantic_raw,
                    plan_step=step_payload,
                    query_id=followup_parse_result.get("query_id"),
                    table_data=query_result.get("tableData"),
                    semantic_summary=semantic_summary,
                    step_metrics=step_metrics,
                )
                await _emit_insight_event(
                    step_insight_output,
                    source="plan_step",
                    plan_step=step_payload,
                    step_metrics=step_metrics,
                )
                stage_metrics["planner_step_insights_emitted"] = int(
                    stage_metrics.get("planner_step_insights_emitted", 0)
                ) + 1
                evidence_context = _append_step_artifact(
                    evidence_context,
                    step_payload=step_payload,
                    query_id=followup_parse_result.get("query_id"),
                    restated_question=semantic_raw.get("restated_question"),
                    table_data=query_result.get("tableData"),
                    summary_text=query_result.get("summary_text", ""),
                    semantic_summary=semantic_summary,
                    key_findings=_extract_insight_key_findings(step_insight_output),
                )
                stage_metrics["planner_completed_steps"] = len(completed_steps)

            await _run_post_planner_agents(
                semantic_raw=parse_result.get("semantic_output", {}) or {},
                evidence_context=evidence_context,
                completed_steps=completed_steps,
            )

        async def _run_workflow() -> None:
            """在后台任务中执行工作流。"""
            try:
                # 1. 认证
                auth_started_at = loop.time()
                logger.info("=" * 60)
                logger.info("[工作流] 步骤 1: 开始认证")
                await callbacks.on_node_start("authentication")
                auth = await get_tableau_auth_async()
                _record_stage("auth_ms", auth_started_at)
                logger.info(f"[工作流] 认证成功: user={self._tableau_username}")
                await callbacks.on_node_end("authentication")

                async with VizQLClient() as vizql_client:
                    # 2. 数据模型加载（内部自动解析 datasource_name → LUID）
                    data_preparation_started_at = loop.time()
                    data_model_started_at = loop.time()
                    logger.info("[工作流] 步骤 2: 开始加载数据模型")
                    logger.info(f"[工作流] 数据源名称: {datasource_name}")
                    await callbacks.on_node_start("data_preparation")
                    loader = TableauDataLoader(client=vizql_client)
                    data_model = await loader.load_data_model(
                        datasource_name=datasource_name,
                        auth=auth,
                        skip_index_creation=True,
                    )
                    _record_stage("data_model_load_ms", data_model_started_at)
                    datasource_luid = data_model.datasource_id
                    logger.info(
                        f"[工作流] 数据模型加载成功: luid={datasource_luid}, "
                        f"fields={len(data_model.fields)}"
                    )

                    # 3. 创建 VizQLClient + TableauAdapter，注入 WorkflowContext
                    logger.info("[工作流] 步骤 3: 创建工作流上下文（含 platform_adapter）")
                    platform_adapter = TableauAdapter(vizql_client=vizql_client)
                    ctx = WorkflowContext(
                        auth=auth,
                        datasource_luid=datasource_luid,
                        data_model=data_model,
                        field_samples=getattr(data_model, "_field_samples_cache", None),
                        current_time=datetime.now().isoformat(),
                        user_id=self._tableau_username,
                        platform_adapter=platform_adapter,
                    )
                    logger.info("[工作流] 开始加载字段语义信息...")
                    field_semantic_started_at = loop.time()
                    ctx = await ctx.load_field_semantic(allow_online_inference=False)
                    _record_stage("field_semantic_load_ms", field_semantic_started_at)
                    stage_metrics["field_semantic_available"] = bool(ctx.field_semantic)
                    stage_metrics["field_samples_available"] = bool(ctx.field_samples)
                    logger.info("[工作流] 字段语义加载完成")
                    if not ctx.field_semantic or not ctx.field_samples:
                        scheduled = schedule_datasource_artifact_preparation(
                            datasource_id=datasource_luid,
                            auth=auth,
                        )
                        stage_metrics["datasource_prewarm_scheduled"] = scheduled
                        if scheduled:
                            logger.info(
                                f"[工作流] 已调度 datasource 后台预热: {datasource_luid}"
                            )
                    else:
                        stage_metrics["datasource_prewarm_scheduled"] = False
                    _record_stage("data_preparation_ms", data_preparation_started_at)
                    await callbacks.on_node_end("data_preparation")

                    # 4. 编译 semantic_parser 子图
                    graph_compile_started_at = loop.time()
                    logger.info("[工作流] 步骤 4: 编译 semantic_parser 子图")
                    graph = compile_semantic_parser_graph()
                    _record_stage("graph_compile_ms", graph_compile_started_at)
                    logger.info("[工作流] 子图编译完成")

                    # 5. 创建 RunnableConfig，注入回调
                    logger.info("[工作流] 步骤 5: 创建运行配置")
                    config = create_workflow_config(
                        thread_id=session_id or f"stream-{datasource_luid}",
                        context=ctx,
                        on_token=callbacks.on_token,
                        on_thinking=callbacks.on_thinking,
                    )

                    # 6. 构建初始状态
                    logger.info("[工作流] 步骤 6: 构建初始状态")
                    logger.debug(f"[工作流] 问题: {question}")
                    logger.info(f"[工作流] 历史消息数: {len(history or [])}")
                    initial_state = {
                        "question": question,
                        "datasource_luid": datasource_luid,
                        "history": history or [],
                        "chat_history": history or [],
                        "current_time": ctx.current_time,
                        "language": language,
                        "analysis_depth": analysis_depth,
                    }
                    logger.info("[工作流] 初始状态构建完成")
                    logger.info("=" * 60)

                    # 7. 执行子图，监听节点事件
                    logger.info("[工作流] 步骤 7: 开始执行子图")
                    logger.debug(
                        f"[工作流] 初始状态: question={question[:50]}..., "
                        f"datasource_luid={datasource_luid}"
                    )
                    node_count = 0

                    logger.debug("[工作流] 调用 graph.astream()...")
                    logger.debug("[工作流] stream_mode='updates'")
                    logger.debug(f"[工作流] config keys: {list(config.keys())}")

                    async for event in graph.astream(
                        initial_state,
                        config,
                        stream_mode="updates",
                    ):
                        logger.debug(f"[工作流] 收到事件: {list(event.keys())}")
                        for node_name, node_output in event.items():
                            node_count += 1
                            stage_metrics["graph_node_count"] = node_count
                            logger.debug(f"[工作流] 节点 #{node_count}: {node_name} 开始执行")
                            await callbacks.on_node_start(node_name)

                            # 转发结构化数据事件
                            if isinstance(node_output, dict):
                                _collect_metrics(node_output.get("optimization_metrics"))
                                if "query_result" in node_output:
                                    logger.debug(f"[工作流] 节点 {node_name} 返回查询结果")
                                    await event_queue.put({
                                        "type": "data",
                                        "tableData": node_output["query_result"],
                                    })
                                if "chart_config" in node_output:
                                    logger.debug(f"[工作流] 节点 {node_name} 返回图表配置")
                                    await event_queue.put({
                                        "type": "chart",
                                        "chartConfig": node_output["chart_config"],
                                    })
                                if "suggestions" in node_output:
                                    logger.debug(f"[工作流] 节点 {node_name} 返回建议问题")
                                    await event_queue.put({
                                        "type": "suggestions",
                                        "questions": node_output["suggestions"],
                                    })
                                # feedback_learner 返回的 parse_result：提取语义解析摘要推送前端，并执行真实查询
                                if "parse_result" in node_output:
                                    parse_result = node_output["parse_result"]
                                    if isinstance(parse_result, dict) and parse_result.get("success"):
                                        _collect_metrics(
                                            parse_result.get("optimization_metrics") or {},
                                        )
                                        semantic_raw = parse_result.get("semantic_output", {})
                                        analysis_plan = _parse_analysis_plan(
                                            parse_result.get("analysis_plan"),
                                            parse_result.get("global_understanding"),
                                        )
                                        logger.debug(
                                            f"[工作流] 节点 {node_name} 返回 parse_result，"
                                            "推送语义解析摘要"
                                        )
                                        if (
                                            analysis_plan is not None
                                            and analysis_plan.needs_planning
                                            and analysis_plan.sub_questions
                                        ):
                                            await _execute_analysis_plan(
                                                graph=graph,
                                                ctx=ctx,
                                                datasource_luid=datasource_luid,
                                                parse_result=parse_result,
                                                analysis_plan=analysis_plan,
                                            )
                                        else:
                                            await _emit_parse_result_event(parse_result)
                                            if parse_result.get("query") and ctx.platform_adapter:
                                                single_query_result = await _execute_query_from_semantic(
                                                    ctx=ctx,
                                                    datasource_luid=datasource_luid,
                                                    semantic_raw=semantic_raw,
                                                    semantic_query=parse_result.get("query"),
                                                )
                                                if single_query_result.get("success"):
                                                    await _run_post_query_agents(
                                                        semantic_raw=semantic_raw,
                                                        query_id=parse_result.get("query_id"),
                                                        table_data=single_query_result.get("tableData"),
                                                    )
                                # needs_clarification：语义理解需要澄清时推送给前端
                                if node_output.get("needs_clarification"):
                                    logger.debug(f"[工作流] 节点 {node_name} 需要用户澄清")
                                    await event_queue.put({
                                        "type": "clarification",
                                        "question": node_output.get("clarification_question", ""),
                                        "options": node_output.get("clarification_options") or [],
                                        "source": node_output.get("clarification_source", ""),
                                        "optimization_metrics": _current_metrics(),
                                    })

                            logger.debug(f"[工作流] 节点 {node_name} 执行完成")
                            await callbacks.on_node_end(node_name)

                # 完成
                stage_metrics["graph_node_count"] = node_count
                logger.info(f"[工作流] 子图执行完成，共执行 {node_count} 个节点")
                if _emit_complete:
                    logger.info("[工作流] 发送完成事件")
                    workflow_elapsed_ms = _mark_workflow_end()
                    await event_queue.put({
                        "type": "complete",
                        "workflowTimeMs": workflow_elapsed_ms,
                        "optimization_metrics": _current_metrics(),
                    })

            except asyncio.CancelledError:
                logger.info(f"工作流被取消: request_id={self._request_id}")
                _mark_workflow_end(cancelled=True)
                await event_queue.put({
                    "type": "error",
                    "error": "请求已取消",
                    "optimization_metrics": _current_metrics(),
                })
            except Exception as e:
                logger.exception(
                    f"工作流执行失败: request_id={self._request_id}, "
                    f"user={self._tableau_username}, "
                    f"datasource={datasource_name}, error={e}"
                )
                _mark_workflow_end(failed=True)
                await event_queue.put({
                    "type": "error",
                    "error": sanitize_error_message(str(e)),
                    "optimization_metrics": _current_metrics(),
                })
            finally:
                # 标记队列结束
                await event_queue.put(None)

        # 启动后台任务（带总超时控制）
        workflow_task = asyncio.create_task(_run_workflow())
        start_time = loop.time()

        try:
            while True:
                elapsed = loop.time() - start_time
                remaining = float(self._timeout) - elapsed
                if remaining <= 0:
                    logger.error(
                        f"工作流总超时: timeout={self._timeout}s, "
                        f"user={self._tableau_username}"
                    )
                    _mark_workflow_end(timed_out=True)
                    yield {
                        "type": "error",
                        "error": "工作流执行超时",
                        "optimization_metrics": _current_metrics(),
                    }
                    break

                try:
                    # 每次最多等待 30 秒，超时发心跳保持连接
                    event = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=min(remaining, 30.0),
                    )
                except asyncio.TimeoutError:
                    # 30 秒内无事件，发送心跳保持 SSE 连接
                    yield {"type": "heartbeat"}
                    continue

                if event is None:
                    break
                yield event
        finally:
            # 客户端断开时取消工作流
            if not workflow_task.done():
                workflow_task.cancel()
                try:
                    await workflow_task
                except asyncio.CancelledError:
                    pass

def _build_semantic_summary(semantic_raw: dict) -> dict:
    """从 SemanticOutput 中提取前端可展示的摘要信息。

    Args:
        semantic_raw: SemanticOutput.model_dump() 的结果

    Returns:
        包含 measures / dimensions / filters / restated_question 的摘要 dict，
        如果输入无效则返回空 dict。
    """
    if not isinstance(semantic_raw, dict):
        return {}

    restated = semantic_raw.get("restated_question", "")

    # 度量列表
    what = semantic_raw.get("what", {}) or {}
    measures = [
        m.get("field_name", "")
        for m in (what.get("measures") or [])
        if isinstance(m, dict) and m.get("field_name")
    ]

    # 维度列表
    where = semantic_raw.get("where", {}) or {}
    dimensions = [
        d.get("field_name", "")
        for d in (where.get("dimensions") or [])
        if isinstance(d, dict) and d.get("field_name")
    ]

    # 筛选器摘要
    filters = []
    for f in (where.get("filters") or []):
        if not isinstance(f, dict):
            continue
        field = f.get("field_name", "")
        if field:
            filters.append(field)

    return {
        "restated_question": restated,
        "measures": measures,
        "dimensions": dimensions,
        "filters": filters,
    }


__all__ = [
    "WorkflowExecutor",
]
