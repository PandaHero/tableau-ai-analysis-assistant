# -*- coding: utf-8 -*-
"""查询阶段的确定性服务。

这里放的是已经从 `WorkflowExecutor` 抽出的纯服务逻辑：
1. 查询前的高风险闸门
2. 语义查询执行
3. `tableData` 与 `ExecuteResult` 的双向归一化
4. 查询结果物化为 `result_manifest/chunks/profiles`
"""

import asyncio
import hashlib
import json
import logging
from typing import Any, Optional

from analytics_assistant.src.core.schemas.execute_result import ColumnInfo, ExecuteResult
from analytics_assistant.src.core.schemas.semantic_output import SemanticOutput
from analytics_assistant.src.infra.error_sanitizer import sanitize_error_message
from analytics_assistant.src.orchestration.workflow.context import WorkflowContext

from .artifacts import materialize_result_artifacts

logger = logging.getLogger(__name__)

_HIGH_RISK_DIMENSION_ROWS_THRESHOLD = 5000
_HIGH_RISK_PARTIAL_FILTER_ROWS_THRESHOLD = 50000
_HIGH_RISK_DEFAULT_BROAD_ROWS = 1000000
_HIGH_RISK_DEFAULT_DIMENSION_CARDINALITY = 50
_HIGH_RISK_MAX_ESTIMATED_ROWS = 10000000


async def execute_semantic_query(
    *,
    ctx: WorkflowContext,
    datasource_luid: str,
    semantic_raw: dict[str, Any],
    request_id: Optional[str] = None,
    run_id: Optional[str] = None,
    artifact_root_dir: Optional[str] = None,
) -> dict[str, Any]:
    """执行语义查询，并产出标准化结果与结果工件。"""
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
            "[query_graph] 查询执行成功: request_id=%s, rows=%s, cols=%s",
            request_id,
            execute_result.row_count,
            len(execute_result.columns),
        )

        artifact_payload = materialize_result_artifacts(
            execute_result=execute_result,
            run_id=run_id or request_id or execute_result.query_id or datasource_luid,
            artifact_root_dir=artifact_root_dir,
        )
        return {
            "success": True,
            "query_execute_ms": elapsed_ms,
            "tableData": artifact_payload["preview_table_data"],
            "truncated": bool(artifact_payload["truncated"]),
            "result_manifest_ref": artifact_payload["result_manifest_ref"],
            "profiles_ref": artifact_payload["profiles_ref"],
            "chunks_ref": artifact_payload["chunks_ref"],
            "artifact_root": artifact_payload["artifact_root"],
            "allowed_files": artifact_payload["allowed_files"],
            "data_profile_dict": artifact_payload["data_profile_dict"],
            # 这个字段只在内部继续传递，避免 answer 阶段丢失完整结果。
            "execute_result_model": execute_result,
        }
    except Exception as exec_err:
        elapsed_ms = (asyncio.get_running_loop().time() - started_at) * 1000
        logger.error("[query_graph] 查询执行失败: request_id=%s, error=%s", request_id, exec_err)
        return {
            "success": False,
            "query_execute_ms": elapsed_ms,
            "error": sanitize_error_message(f"查询执行失败: {exec_err}"),
        }


def build_high_risk_interrupt_payload(
    *,
    ctx: WorkflowContext,
    datasource_luid: str,
    semantic_raw: dict[str, Any],
    confirmed_signatures: Optional[set[str]] = None,
) -> Optional[dict[str, Any]]:
    """对明显过宽的查询应用确定性高风险闸门。"""
    if not isinstance(semantic_raw, dict):
        return None

    where = semantic_raw.get("where") or {}
    dimensions = _extract_semantic_field_names(where.get("dimensions"))
    measures = _extract_semantic_field_names((semantic_raw.get("what") or {}).get("measures"))
    raw_filters = where.get("filters") or []
    if not isinstance(raw_filters, list):
        raw_filters = []

    has_top_n_filter = any(
        _normalize_filter_type(raw_filter) == "TOP_N"
        for raw_filter in raw_filters
    )
    narrowing_filters = [
        raw_filter for raw_filter in raw_filters
        if _normalize_filter_type(raw_filter) != "TOP_N"
    ]
    if has_top_n_filter:
        return None

    risk_signature = _build_high_risk_signature(
        datasource_luid=datasource_luid,
        semantic_raw=semantic_raw,
    )
    if confirmed_signatures and risk_signature in confirmed_signatures:
        return None

    estimated_rows = 1
    dimension_cardinality: list[dict[str, Any]] = []
    for field_name in dimensions[:3]:
        unique_count = _resolve_field_cardinality(ctx=ctx, field_name=field_name)
        dimension_cardinality.append({
            "field_name": field_name,
            "unique_count": unique_count,
        })
        estimated_rows = min(
            _HIGH_RISK_MAX_ESTIMATED_ROWS,
            estimated_rows * max(unique_count, 1),
        )

    if not dimensions and not narrowing_filters:
        estimated_rows = _HIGH_RISK_DEFAULT_BROAD_ROWS
    elif dimensions and estimated_rows == 1:
        estimated_rows = _HIGH_RISK_DEFAULT_DIMENSION_CARDINALITY

    reasons: list[str] = []
    if not narrowing_filters:
        reasons.append("未检测到收敛筛选条件")
    if dimensions:
        highest_cardinality = max(
            (item["unique_count"] for item in dimension_cardinality),
            default=0,
        )
        if highest_cardinality >= _HIGH_RISK_DIMENSION_ROWS_THRESHOLD:
            reasons.append("维度基数较高，预计结果规模较大")
    else:
        reasons.append("查询没有分组维度，可能直接扫描大范围数据")
    if not measures:
        reasons.append("查询缺少明确度量，结果范围可能不可控")

    if not reasons:
        return None

    should_interrupt = False
    if not narrowing_filters and estimated_rows >= _HIGH_RISK_DIMENSION_ROWS_THRESHOLD:
        should_interrupt = True
    elif len(narrowing_filters) <= 1 and estimated_rows >= _HIGH_RISK_PARTIAL_FILTER_ROWS_THRESHOLD:
        should_interrupt = True

    if not should_interrupt:
        return None

    return {
        "title": "高风险查询确认",
        "message": "当前查询范围较大，确认后我会继续执行该查询。",
        "summary": "检测到查询缺少足够的收敛条件，可能返回大结果或产生较高执行成本。",
        "source": "query_risk_guard",
        "risk_level": "high",
        "estimated_rows": estimated_rows,
        "reasons": reasons,
        "dimensions": dimension_cardinality,
        "filter_count": len(narrowing_filters),
        "risk_signature": risk_signature,
    }


def table_data_to_execute_result(
    table_data: Optional[dict[str, Any]],
    *,
    query_id: Optional[str] = None,
) -> Optional[ExecuteResult]:
    """把 `tableData` 还原成平台无关的 `ExecuteResult`。"""
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
                normalized_rows.append({name: raw_row.get(name) for name in column_names})
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


def _extract_semantic_field_names(
    items: Any,
    *,
    key: str = "field_name",
) -> list[str]:
    """从半结构化语义输出中提取字段名。"""
    if not isinstance(items, list):
        return []
    result: list[str] = []
    for item in items:
        if isinstance(item, dict):
            field_name = str(item.get(key) or "").strip()
        else:
            field_name = str(item or "").strip()
        if field_name:
            result.append(field_name)
    return result


def _normalize_filter_type(raw_filter: Any) -> str:
    """从 dict 或枚举对象中提取统一的 filter type。"""
    if isinstance(raw_filter, dict):
        value = raw_filter.get("filter_type")
    else:
        value = getattr(raw_filter, "filter_type", None)
    text = str(value or "").strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.upper()


def _build_high_risk_signature(
    *,
    datasource_luid: str,
    semantic_raw: dict[str, Any],
) -> str:
    """构造稳定签名，避免同一高风险查询被重复打断。"""
    where = semantic_raw.get("where") or {}
    what = semantic_raw.get("what") or {}
    payload = {
        "datasource_luid": datasource_luid,
        "restated_question": str(semantic_raw.get("restated_question") or "").strip(),
        "dimensions": _extract_semantic_field_names(where.get("dimensions")),
        "measures": _extract_semantic_field_names(what.get("measures")),
        "filters": where.get("filters") or [],
        "computations": semantic_raw.get("computations") or [],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:16]


def _resolve_field_cardinality(
    *,
    ctx: WorkflowContext,
    field_name: str,
) -> int:
    """优先使用样例缓存估算字段基数，缺失时回退到保守默认值。"""
    normalized_name = str(field_name or "").strip()
    if not normalized_name:
        return _HIGH_RISK_DEFAULT_DIMENSION_CARDINALITY

    field_samples = ctx.field_samples or {}
    candidate_names = [normalized_name]
    data_model = getattr(ctx, "data_model", None)
    if data_model is not None and hasattr(data_model, "get_field"):
        field = data_model.get_field(normalized_name)
        if field is not None:
            caption = str(getattr(field, "caption", "") or "").strip()
            name = str(getattr(field, "name", "") or "").strip()
            for candidate in (caption, name):
                if candidate and candidate not in candidate_names:
                    candidate_names.append(candidate)

    for candidate in candidate_names:
        sample_info = field_samples.get(candidate)
        if not isinstance(sample_info, dict):
            continue
        unique_count = sample_info.get("unique_count")
        try:
            resolved_unique_count = int(unique_count)
        except (TypeError, ValueError):
            resolved_unique_count = 0
        if resolved_unique_count > 0:
            return resolved_unique_count

        sample_values = sample_info.get("sample_values") or []
        if isinstance(sample_values, list) and sample_values:
            return len(sample_values)

    return _HIGH_RISK_DEFAULT_DIMENSION_CARDINALITY
