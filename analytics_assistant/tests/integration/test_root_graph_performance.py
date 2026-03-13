from __future__ import annotations

import time
import tracemalloc
from datetime import datetime

import pytest

from analytics_assistant.src.orchestration.root_graph import RootGraphRunner
from analytics_assistant.src.orchestration.workflow.checkpoint import (
    reset_workflow_checkpointers,
)
from analytics_assistant.tests.integration.config_loader import TestConfigLoader
from analytics_assistant.tests.integration.performance_monitor import (
    PerformanceMetric,
    PerformanceMonitor,
)
from analytics_assistant.tests.orchestration.workflow.test_root_graph_runner import (
    _SemanticGraphRunnerStub,
    _fake_auth_getter,
    _make_parse_result_update,
    _patch_direct_round,
    _resolved_context,
)


@pytest.mark.asyncio
async def test_root_graph_native_stream_meets_performance_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_workflow_checkpointers(clear_persisted_state=True)
    try:
        _patch_direct_round(monkeypatch)
        runner = RootGraphRunner(
            "alice",
            request_id="perf_root_graph_native_stream",
            auth_getter=_fake_auth_getter,
            semantic_graph_runner=_SemanticGraphRunnerStub(
                events_per_call=[[_make_parse_result_update()]]
            ),
            context_resolver=_resolved_context,
        )

        tracemalloc.start()
        start = time.perf_counter()
        events = [
            event
            async for event in runner.execute_stream(
                question="show revenue",
                datasource_name="Revenue",
                session_id="sess_perf_root_graph_native_stream",
            )
        ]
        elapsed = time.perf_counter() - start
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        metric = PerformanceMetric(
            test_name="root_graph_native_stream_smoke",
            timestamp=datetime.now(),
            elapsed_time=elapsed,
            memory_usage_mb=peak_bytes / (1024 * 1024),
            metadata={
                "event_count": len(events),
                "final_event_type": events[-1]["type"] if events else None,
            },
        )
        monitor = PerformanceMonitor(
            output_dir=TestConfigLoader.get_log_file_path().parent,
            baseline_file=TestConfigLoader.get_performance_baseline_path(),
        )
        threshold = TestConfigLoader.get_performance_config().get("regression_threshold", 1.2)

        assert events
        assert events[-1]["type"] == "complete"
        assert elapsed <= 0.5, f"root_graph native smoke exceeded 0.5s: {elapsed:.4f}s"
        assert monitor.check_regression(metric, threshold=threshold) is False
    finally:
        reset_workflow_checkpointers(clear_persisted_state=True)
