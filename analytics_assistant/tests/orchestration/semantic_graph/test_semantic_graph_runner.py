# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langgraph.types import Command

from analytics_assistant.src.orchestration.semantic_graph import SemanticGraphRunner


class _FakeCompiledGraph:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, dict[str, Any], str]] = []

    async def astream(
        self,
        graph_input: Any,
        config: dict[str, Any],
        *,
        stream_mode: str,
    ):
        self.calls.append((graph_input, config, stream_mode))
        yield {"parse_result": {"success": True}}


def test_compile_graph_passes_checkpointer() -> None:
    calls: list[Any] = []

    def _compiler(*, checkpointer: Any) -> _FakeCompiledGraph:
        calls.append(checkpointer)
        return _FakeCompiledGraph()

    runner = SemanticGraphRunner(
        graph_compiler=_compiler,
        checkpointer_getter=lambda: "ckpt",
    )

    graph = runner.compile_graph()

    assert isinstance(graph, _FakeCompiledGraph)
    assert calls == ["ckpt"]


def test_build_input_returns_resume_command() -> None:
    runner = SemanticGraphRunner(
        graph_compiler=lambda **_kwargs: _FakeCompiledGraph(),
        checkpointer_getter=lambda: "ckpt",
    )

    graph_input = runner.build_input(
        question="ignored",
        datasource_luid="ds_001",
        history=[{"role": "user", "content": "hi"}],
        current_time="2026-03-11T00:00:00Z",
        language="zh",
        analysis_depth="detailed",
        resume={"slot": "timeframe"},
    )

    assert isinstance(graph_input, Command)


def test_build_config_uses_session_and_suffix() -> None:
    runner = SemanticGraphRunner(
        graph_compiler=lambda **_kwargs: _FakeCompiledGraph(),
        checkpointer_getter=lambda: "ckpt",
    )

    config = runner.build_config(
        ctx=SimpleNamespace(),
        datasource_luid="ds_001",
        session_id="sess_001",
        on_token="token_cb",
        on_thinking="thinking_cb",
        thread_suffix=":plan-step-2",
    )

    assert config["configurable"]["thread_id"] == "sess_001:plan-step-2"
    assert config["configurable"]["on_token"] == "token_cb"
    assert config["configurable"]["on_thinking"] == "thinking_cb"


@pytest.mark.asyncio
async def test_astream_proxies_graph_updates() -> None:
    graph = _FakeCompiledGraph()
    runner = SemanticGraphRunner(
        graph_compiler=lambda **_kwargs: graph,
        checkpointer_getter=lambda: "ckpt",
    )

    config = {"configurable": {"thread_id": "sess_001"}}
    events = [
        event
        async for event in runner.astream(
            graph=graph,
            graph_input={"question": "show revenue"},
            config=config,
        )
    ]

    assert events == [{"parse_result": {"success": True}}]
    assert graph.calls == [
        (
            {"question": "show revenue"},
            config,
            "updates",
        )
    ]
