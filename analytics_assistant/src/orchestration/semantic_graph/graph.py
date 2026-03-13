# -*- coding: utf-8 -*-
"""语义图运行边界封装。"""

from __future__ import annotations

import inspect
from typing import Any, AsyncIterator, Callable, Optional

from langgraph.types import Command

from analytics_assistant.src.orchestration.workflow.context import (
    WorkflowContext,
    create_workflow_config,
)


class SemanticGraphRunner:
    """统一封装语义图编译、配置构造和流式执行。"""

    def __init__(
        self,
        *,
        graph_compiler: Callable[..., Any],
        checkpointer_getter: Callable[[], Any],
    ) -> None:
        self._graph_compiler = graph_compiler
        self._checkpointer_getter = checkpointer_getter

    async def acompile_graph(self) -> Any:
        """按需编译语义图，并兼容同步/异步 checkpointer getter。"""
        checkpointer = self._checkpointer_getter()
        if inspect.isawaitable(checkpointer):
            checkpointer = await checkpointer
        return self._graph_compiler(checkpointer=checkpointer)

    def compile_graph(self) -> Any:
        """同步编译语义图。

        这个入口主要保留给同步单测；在线路执行中应优先使用 `acompile_graph()`。
        """
        return self._graph_compiler(checkpointer=self._checkpointer_getter())

    def build_config(
        self,
        *,
        ctx: WorkflowContext,
        datasource_luid: str,
        session_id: Optional[str],
        request_id: Optional[str] = None,
        run_id: Optional[str] = None,
        on_token: Any = None,
        on_thinking: Any = None,
        thread_suffix: str = "",
    ) -> dict[str, Any]:
        """构造单次语义图执行的 RunnableConfig。"""
        thread_id = session_id or f"stream-{datasource_luid}"
        if thread_suffix:
            thread_id = f"{thread_id}{thread_suffix}"
        return create_workflow_config(
            thread_id=thread_id,
            context=ctx,
            request_id=request_id,
            session_id=session_id,
            run_id=run_id or request_id,
            on_token=on_token,
            on_thinking=on_thinking,
        )

    def build_input(
        self,
        *,
        question: str,
        datasource_luid: str,
        history: Optional[list[dict[str, str]]],
        current_time: str,
        language: str,
        analysis_depth: str,
        field_semantic: Optional[dict[str, Any]] = None,
        feature_flags: Optional[dict[str, bool]] = None,
        resume: Any = None,
    ) -> Any:
        """构造图初始输入或原生 resume 命令。"""
        if resume is not None:
            return Command(resume=resume)

        base_history = list(history or [])
        graph_input = {
            "question": question,
            "datasource_luid": datasource_luid,
            "history": base_history,
            "chat_history": base_history,
            "current_time": current_time,
            "language": language,
            "analysis_depth": analysis_depth,
        }
        if field_semantic is not None:
            graph_input["field_semantic"] = field_semantic
        if feature_flags is not None:
            graph_input["feature_flags"] = dict(feature_flags)
        return graph_input

    async def astream(
        self,
        *,
        graph: Any,
        graph_input: Any,
        config: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """以稳定的异步迭代协议透传语义图更新事件。"""
        async for event in graph.astream(
            graph_input,
            config,
            stream_mode="updates",
        ):
            yield event
