# -*- coding: utf-8 -*-
"""Insight Agent 执行入口。"""

import json
import logging
from typing import Any, Awaitable, Callable, Optional

from langchain.agents.middleware import (
    ModelRetryMiddleware,
    SummarizationMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, StructuredTool

from analytics_assistant.src.agents.base import get_llm, stream_llm_structured
from analytics_assistant.src.infra.ai import TaskType
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.orchestration.answer_graph import (
    InsightFilesystemMiddleware,
    InsightWorkspace,
    prepare_insight_workspace,
)
from analytics_assistant.src.orchestration.query_graph import load_json_artifact

from .prompts.insight_prompt import (
    build_semantic_output_summary,
    build_user_prompt,
    build_workspace_summary,
    get_system_prompt,
)
from .schemas.output import InsightOutput

logger = logging.getLogger(__name__)

_DEFAULT_DETAILED_ROUNDS = 5
_DEFAULT_COMPREHENSIVE_ROUNDS = 10
_DEFAULT_MODEL_RETRY_MAX = 3
_DEFAULT_MODEL_RETRY_BASE_DELAY = 1.0
_DEFAULT_MODEL_RETRY_MAX_DELAY = 30.0
_DEFAULT_TOOL_RETRY_MAX = 2
_DEFAULT_TOOL_RETRY_BASE_DELAY = 0.5
_DEFAULT_SUMMARIZATION_MAX_TOKENS = 8000
_DEFAULT_SUMMARIZATION_KEEP_MESSAGES = 6
_FINISH_SIGNAL = "INSIGHT_ANALYSIS_COMPLETE"



def _load_insight_config() -> dict[str, Any]:
    try:
        config = get_config()
        return config.get("agents", {})
    except Exception as exc:
        logger.warning("加载 Insight Agent 配置失败，使用默认值: %s", exc)
        return {}



def _get_max_iterations(agents_config: dict[str, Any], analysis_depth: str) -> int:
    insight_config = agents_config.get("insight", {})
    depth_rounds = insight_config.get("analysis_depth_rounds", {})
    if analysis_depth == "comprehensive":
        return int(depth_rounds.get("comprehensive", _DEFAULT_COMPREHENSIVE_ROUNDS))
    return int(depth_rounds.get("detailed", _DEFAULT_DETAILED_ROUNDS))



def _build_middleware_stack(agents_config: dict[str, Any], llm: Any) -> list[Any]:
    middleware_config = agents_config.get("middleware", {})
    summarization_config = middleware_config.get("summarization", {})
    model_retry_config = middleware_config.get("model_retry", {})
    tool_retry_config = middleware_config.get("tool_retry", {})

    return [
        SummarizationMiddleware(
            model=llm,
            trigger=(
                "tokens",
                summarization_config.get(
                    "max_history_tokens",
                    _DEFAULT_SUMMARIZATION_MAX_TOKENS,
                ),
            ),
            keep=(
                "messages",
                summarization_config.get(
                    "keep_recent_messages",
                    _DEFAULT_SUMMARIZATION_KEEP_MESSAGES,
                ),
            ),
        ),
        ModelRetryMiddleware(
            max_retries=model_retry_config.get("max_retries", _DEFAULT_MODEL_RETRY_MAX),
            initial_delay=model_retry_config.get("base_delay", _DEFAULT_MODEL_RETRY_BASE_DELAY),
            max_delay=model_retry_config.get("max_delay", _DEFAULT_MODEL_RETRY_MAX_DELAY),
        ),
        ToolRetryMiddleware(
            max_retries=tool_retry_config.get("max_retries", _DEFAULT_TOOL_RETRY_MAX),
            initial_delay=tool_retry_config.get("base_delay", _DEFAULT_TOOL_RETRY_BASE_DELAY),
        ),
    ]



def _resolve_profile_refs(manifest: dict[str, Any]) -> tuple[str, str]:
    data_profile_ref = ""
    summary_ref = ""
    for profile in manifest.get("profiles") or []:
        if not isinstance(profile, dict):
            continue
        if profile.get("name") == "data_profile":
            data_profile_ref = str(profile.get("path") or "")
        elif profile.get("name") == "summary":
            summary_ref = str(profile.get("path") or "")
    if not data_profile_ref or not summary_ref:
        raise ValueError("result_manifest 缺少 data_profile 或 summary 引用")
    return data_profile_ref, summary_ref



def _create_finish_insight_tool() -> BaseTool:
    def finish_insight() -> str:
        """当你已经收集到足够证据时调用该工具，表示可以输出最终洞察。"""
        return _FINISH_SIGNAL

    return StructuredTool.from_function(
        name="finish_insight",
        description="在证据充分时结束分析，并开始输出最终洞察 JSON。",
        func=finish_insight,
    )


async def run_insight_agent(
    *,
    result_manifest_ref: Optional[str] = None,
    workspace: Optional[InsightWorkspace] = None,
    semantic_output_dict: dict[str, Any],
    analysis_depth: str = "detailed",
    session_id: Optional[str] = None,
    artifact_root_dir: Optional[str] = None,
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,
    on_progress: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None,
) -> InsightOutput:
    """基于结果文件工作区执行洞察分析。"""
    del on_progress

    if workspace is None:
        if not result_manifest_ref:
            raise ValueError("run_insight_agent 需要 result_manifest_ref 或 workspace")
        workspace = prepare_insight_workspace(
            result_manifest_ref=result_manifest_ref,
            session_id=session_id,
            artifact_root_dir=artifact_root_dir,
        )

    manifest = workspace.manifest
    data_profile_ref, summary_ref = _resolve_profile_refs(manifest)
    data_profile_summary = load_json_artifact(
        summary_ref,
        artifact_root_dir=workspace.artifact_root_dir,
    )

    agents_config = _load_insight_config()
    max_iterations = _get_max_iterations(agents_config, analysis_depth)
    llm = get_llm(agent_name="insight", task_type=TaskType.INSIGHT_GENERATION)
    middleware_stack = _build_middleware_stack(agents_config, llm)

    filesystem_middleware = InsightFilesystemMiddleware(workspace)
    tools = filesystem_middleware.get_tools() + [_create_finish_insight_tool()]
    system_prompt = (
        get_system_prompt().strip()
        + "\n\n"
        + filesystem_middleware.get_system_prompt_suffix().strip()
    )
    workspace_summary = build_workspace_summary(
        workspace_manifest=manifest,
        data_profile_summary=data_profile_summary,
    )
    semantic_output_summary = build_semantic_output_summary(semantic_output_dict)
    user_prompt = build_user_prompt(
        workspace_summary=workspace_summary,
        semantic_output_summary=semantic_output_summary,
        analysis_depth=analysis_depth,
    )
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    logger.info(
        "Insight Agent 启动: workspace=%s, run_id=%s, row_count=%s, columns=%s",
        workspace.workspace_id,
        workspace.run_id,
        manifest.get("row_count"),
        manifest.get("column_count"),
    )

    result = await stream_llm_structured(
        llm=llm,
        messages=messages,
        output_model=InsightOutput,
        tools=tools,
        middleware=middleware_stack,
        max_iterations=max_iterations,
        on_token=on_token,
        on_thinking=on_thinking,
    )

    logger.info(
        "Insight Agent 完成: findings=%s, confidence=%.2f",
        len(result.findings),
        result.overall_confidence,
    )
    return result
