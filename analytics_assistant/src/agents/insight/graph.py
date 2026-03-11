# -*- coding: utf-8 -*-
"""
Insight Agent 执行逻辑

使用 stream_llm_structured + MiddlewareRunner 实现 ReAct 循环：
- token 级流式输出（on_token / on_thinking 回调）
- 工具调用循环（LLM 自主决定何时调用 finish_insight 结束）
- 中间件栈（ModelRetry / ToolRetry / Summarization / Filesystem）

公开 API：
- run_insight_agent(): 执行 Insight Agent，返回 InsightOutput
"""
import logging
from typing import Any, Awaitable, Callable, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain.agents.middleware import (
    ModelRetryMiddleware,
    SummarizationMiddleware,
    ToolRetryMiddleware,
)
from analytics_assistant.src.agents.base.middleware import FilesystemMiddleware

from analytics_assistant.src.agents.base import get_llm, stream_llm_structured
from analytics_assistant.src.infra.ai import TaskType
from analytics_assistant.src.infra.config import get_config

from .components.data_store import DataStore
from .components.data_tools import create_insight_tools
from .prompts.insight_prompt import build_user_prompt, get_system_prompt
from .schemas.output import DataProfile, InsightOutput

logger = logging.getLogger(__name__)

# 默认配置常量
_DEFAULT_MAX_ITERATIONS = 10
_DEFAULT_DETAILED_ROUNDS = 5
_DEFAULT_COMPREHENSIVE_ROUNDS = 10
_DEFAULT_MODEL_RETRY_MAX = 3
_DEFAULT_MODEL_RETRY_BASE_DELAY = 1.0
_DEFAULT_MODEL_RETRY_MAX_DELAY = 30.0
_DEFAULT_TOOL_RETRY_MAX = 2
_DEFAULT_TOOL_RETRY_BASE_DELAY = 0.5
_DEFAULT_FS_MAX_TOKENS = 2000
_DEFAULT_SUMMARIZATION_MAX_TOKENS = 8000
_DEFAULT_SUMMARIZATION_KEEP_MESSAGES = 6

def _load_insight_config() -> dict[str, Any]:
    """从 app.yaml 加载 Insight Agent 配置。

    Returns:
        配置字典，包含 insight、middleware 等子节点
    """
    try:
        config = get_config()
        return config.get("agents", {})
    except Exception as e:
        logger.warning(f"加载 Insight Agent 配置失败，使用默认值: {e}")
        return {}

def _get_max_iterations(agents_config: dict[str, Any], analysis_depth: str) -> int:
    """根据分析深度获取最大迭代次数。

    Args:
        agents_config: agents 配置节
        analysis_depth: 分析深度（"detailed" 或 "comprehensive"）

    Returns:
        最大迭代次数
    """
    insight_config = agents_config.get("insight", {})
    depth_rounds = insight_config.get("analysis_depth_rounds", {})

    if analysis_depth == "comprehensive":
        return depth_rounds.get("comprehensive", _DEFAULT_COMPREHENSIVE_ROUNDS)
    return depth_rounds.get("detailed", _DEFAULT_DETAILED_ROUNDS)

def _build_middleware_stack(
    agents_config: dict[str, Any],
    llm: Any,
) -> list[Any]:
    """构建中间件栈。

    Args:
        agents_config: agents 配置节
        llm: LLM 实例（SummarizationMiddleware 需要）

    Returns:
        中间件实例列表
    """
    mw_config = agents_config.get("middleware", {})

    # SummarizationMiddleware - 消息历史摘要压缩
    summarization_config = mw_config.get("summarization", {})
    summarization_mw = SummarizationMiddleware(
        model=llm,
        trigger=(
            "tokens",
            summarization_config.get("max_history_tokens", _DEFAULT_SUMMARIZATION_MAX_TOKENS),
        ),
        keep=(
            "messages",
            summarization_config.get("keep_recent_messages", _DEFAULT_SUMMARIZATION_KEEP_MESSAGES),
        ),
    )

    # ModelRetryMiddleware - LLM 调用重试
    model_retry_config = mw_config.get("model_retry", {})
    model_retry_mw = ModelRetryMiddleware(
        max_retries=model_retry_config.get("max_retries", _DEFAULT_MODEL_RETRY_MAX),
        initial_delay=model_retry_config.get("base_delay", _DEFAULT_MODEL_RETRY_BASE_DELAY),
        max_delay=model_retry_config.get("max_delay", _DEFAULT_MODEL_RETRY_MAX_DELAY),
    )

    # ToolRetryMiddleware - 工具调用重试
    tool_retry_config = mw_config.get("tool_retry", {})
    tool_retry_mw = ToolRetryMiddleware(
        max_retries=tool_retry_config.get("max_retries", _DEFAULT_TOOL_RETRY_MAX),
        initial_delay=tool_retry_config.get("base_delay", _DEFAULT_TOOL_RETRY_BASE_DELAY),
    )

    # FilesystemMiddleware - 大结果截断 + 虚拟文件系统
    fs_config = mw_config.get("filesystem", {})
    fs_mw = FilesystemMiddleware(
        tool_token_limit_before_evict=fs_config.get(
            "max_tool_result_tokens", _DEFAULT_FS_MAX_TOKENS
        ),
    )

    return [summarization_mw, model_retry_mw, tool_retry_mw, fs_mw]

async def run_insight_agent(
    data_store: DataStore,
    data_profile: DataProfile,
    semantic_output_dict: dict[str, Any],
    analysis_depth: str = "detailed",
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
    on_progress: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
) -> InsightOutput:
    """执行 Insight Agent。

    使用 stream_llm_structured + tools 实现 ReAct 循环。
    LLM 通过工具调用分批读取数据，调用 finish_insight 时结束。

    Args:
        data_store: 数据存储实例
        data_profile: 数据画像
        semantic_output_dict: 语义解析输出（序列化后的字典）
        analysis_depth: 分析深度（"detailed" 或 "comprehensive"）
        on_token: Token 流式回调
        on_thinking: 思考过程回调
        on_progress: 进度回调（轮数、工具调用信息）

    Returns:
        InsightOutput 洞察结果

    Raises:
        RuntimeError: 达到最大迭代次数仍未获得结果
        ValueError: 参数无效
    """
    # 加载配置
    agents_config = _load_insight_config()
    max_iterations = _get_max_iterations(agents_config, analysis_depth)

    # 获取 LLM
    llm = get_llm(agent_name="insight", task_type=TaskType.INSIGHT_GENERATION)

    # 构建工具集
    insight_tools = create_insight_tools(data_store, data_profile)

    # 构建中间件栈
    middleware_stack = _build_middleware_stack(agents_config, llm)

    # 将 FilesystemMiddleware 的 read_file 工具注入到工具列表
    fs_mw_ref = None
    for mw in middleware_stack:
        if isinstance(mw, FilesystemMiddleware):
            insight_tools.extend(mw.get_tools())
            fs_mw_ref = mw

    # 构建 DataProfile 摘要
    data_profile_summary = _build_data_profile_summary(data_profile)

    # 构建语义输出摘要
    semantic_output_summary = _build_semantic_output_summary(semantic_output_dict)

    # 构建消息
    system_prompt = get_system_prompt()
    user_prompt = build_user_prompt(
        data_profile_summary=data_profile_summary,
        semantic_output_summary=semantic_output_summary,
        analysis_depth=analysis_depth,
    )

    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    logger.info(
        f"Insight Agent 启动: analysis_depth={analysis_depth}, "
        f"max_iterations={max_iterations}, "
        f"data_rows={data_store.row_count}, "
        f"data_columns={len(data_store.columns)}"
    )

    # 执行 ReAct 循环
    try:
        result = await stream_llm_structured(
            llm=llm,
            messages=messages,
            output_model=InsightOutput,
            tools=insight_tools,
            middleware=middleware_stack,
            max_iterations=max_iterations,
            on_token=on_token,
            on_thinking=on_thinking,
        )

        logger.info(
            f"Insight Agent 完成: findings={len(result.findings)}, "
            f"overall_confidence={result.overall_confidence:.2f}"
        )

        return result
    finally:
        data_store.cleanup()
        if fs_mw_ref is not None:
            fs_mw_ref.cleanup()

def _build_data_profile_summary(data_profile: DataProfile) -> str:
    """构建 DataProfile 摘要文本。

    Args:
        data_profile: 数据画像

    Returns:
        摘要文本
    """
    lines = [
        f"- 总行数: {data_profile.row_count}",
        f"- 总列数: {data_profile.column_count}",
        "",
        "### 列信息",
    ]

    for col in data_profile.columns_profile:
        col_desc = f"- **{col.column_name}** ({col.data_type})"
        if col.is_numeric and col.numeric_stats:
            stats = col.numeric_stats
            parts = []
            if stats.min is not None:
                parts.append(f"min={stats.min:g}")
            if stats.max is not None:
                parts.append(f"max={stats.max:g}")
            if stats.avg is not None:
                parts.append(f"avg={stats.avg:g}")
            if parts:
                col_desc += f" [{', '.join(parts)}]"
        elif col.categorical_stats:
            stats = col.categorical_stats
            col_desc += f" [unique={stats.unique_count}]"
        if col.null_count > 0:
            col_desc += f" (null: {col.null_count})"
        if col.error:
            col_desc += f" (error: {col.error})"
        lines.append(col_desc)

    return "\n".join(lines)

def _build_semantic_output_summary(semantic_output_dict: dict[str, Any]) -> str:
    """构建语义解析输出摘要。

    Args:
        semantic_output_dict: 语义解析输出字典（SemanticOutput.model_dump() 格式）

    Returns:
        摘要文本
    """
    parts = []

    # 用户原始问题
    restated = semantic_output_dict.get("restated_question", "")
    if restated:
        parts.append(f"**用户问题**: {restated}")

    # 计算复杂度
    how_type = semantic_output_dict.get("how_type", "")
    if how_type:
        parts.append(f"**计算复杂度**: {how_type}")

    # 度量字段 (what.measures)
    what = semantic_output_dict.get("what", {})
    measures = what.get("measures", []) if isinstance(what, dict) else []
    if measures:
        measure_names = []
        for m in measures:
            name = m.get("field_name", "") if isinstance(m, dict) else str(m)
            agg = m.get("aggregation", "") if isinstance(m, dict) else ""
            if name:
                measure_names.append(f"{name}({agg})" if agg else name)
        if measure_names:
            parts.append(f"**度量字段**: {', '.join(measure_names)}")

    # 维度字段 (where.dimensions)
    where = semantic_output_dict.get("where", {})
    dimensions = where.get("dimensions", []) if isinstance(where, dict) else []
    if dimensions:
        dim_names = []
        for d in dimensions:
            name = d.get("field_name", "") if isinstance(d, dict) else str(d)
            granularity = d.get("date_granularity", "") if isinstance(d, dict) else ""
            if name:
                dim_names.append(f"{name}({granularity})" if granularity else name)
        if dim_names:
            parts.append(f"**维度字段**: {', '.join(dim_names)}")

    # 筛选条件 (where.filters)
    filters = where.get("filters", []) if isinstance(where, dict) else []
    if filters:
        filter_descs = []
        for f in filters:
            if not isinstance(f, dict):
                continue
            field_name = f.get("field_name", "")
            filter_type = f.get("filter_type", "")
            if field_name:
                if filter_type == "SET":
                    vals = f.get("values", [])
                    exclude = f.get("exclude", False)
                    op = "NOT IN" if exclude else "IN"
                    filter_descs.append(f"{field_name} {op} {vals}")
                elif filter_type == "DATE_RANGE":
                    start = f.get("start_date", "")
                    end = f.get("end_date", "")
                    filter_descs.append(f"{field_name}: {start} ~ {end}")
                elif filter_type == "NUMERIC_RANGE":
                    min_v = f.get("min_value", "")
                    max_v = f.get("max_value", "")
                    filter_descs.append(f"{field_name}: {min_v} ~ {max_v}")
                elif filter_type == "TOP_N":
                    n = f.get("n", "")
                    by = f.get("by_field", "")
                    filter_descs.append(f"{field_name}: Top {n} by {by}")
                else:
                    filter_descs.append(f"{field_name} ({filter_type})")
        if filter_descs:
            parts.append(f"**筛选条件**: {'; '.join(filter_descs)}")

    # 派生计算 (computations)
    computations = semantic_output_dict.get("computations", [])
    if computations:
        comp_descs = []
        for c in computations:
            if isinstance(c, dict):
                display = c.get("display_name", c.get("name", ""))
                calc_type = c.get("calc_type", "")
                if display:
                    comp_descs.append(f"{display}({calc_type})" if calc_type else display)
        if comp_descs:
            parts.append(f"**派生计算**: {', '.join(comp_descs)}")

    return "\n".join(parts) if parts else "（无语义解析信息）"
