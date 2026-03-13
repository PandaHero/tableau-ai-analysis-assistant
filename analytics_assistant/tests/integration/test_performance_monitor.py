from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from analytics_assistant.tests.integration.config_loader import TestConfigLoader
from analytics_assistant.tests.integration.performance_monitor import (
    PerformanceMetric,
    PerformanceMonitor,
)


def _write_baseline(path, *, test_name: str, elapsed_time: float, memory_usage_mb: float) -> None:
    path.write_text(
        json.dumps({
            test_name: {
                "test_name": test_name,
                "timestamp": datetime(2026, 3, 13, 12, 0, 0).isoformat(),
                "elapsed_time": elapsed_time,
                "memory_usage_mb": memory_usage_mb,
            }
        }),
        encoding="utf-8",
    )


def _make_workspace_temp_dir() -> Path:
    base_dir = Path(__file__).resolve().parents[1] / "test_outputs" / "performance_monitor_tests"
    temp_dir = base_dir / uuid4().hex
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def test_performance_monitor_reads_default_performance_baseline_file() -> None:
    tmp_path = _make_workspace_temp_dir()
    try:
        baseline_file = tmp_path / "performance_baseline.json"
        _write_baseline(
            baseline_file,
            test_name="root_graph_smoke",
            elapsed_time=1.25,
            memory_usage_mb=64.0,
        )

        monitor = PerformanceMonitor(output_dir=tmp_path)
        baseline = monitor.get_baseline("root_graph_smoke")

        assert monitor.baseline_file == baseline_file
        assert baseline is not None
        assert baseline.elapsed_time == 1.25
        assert baseline.memory_usage_mb == 64.0
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_performance_monitor_supports_explicit_baseline_file() -> None:
    tmp_path = _make_workspace_temp_dir()
    try:
        baseline_file = tmp_path / "custom_baseline.json"
        _write_baseline(
            baseline_file,
            test_name="planner_runtime_smoke",
            elapsed_time=2.0,
            memory_usage_mb=80.0,
        )

        monitor = PerformanceMonitor(output_dir=tmp_path, baseline_file=baseline_file)
        metric = PerformanceMetric(
            test_name="planner_runtime_smoke",
            timestamp=datetime(2026, 3, 13, 12, 30, 0),
            elapsed_time=2.7,
            memory_usage_mb=81.0,
        )

        assert monitor.get_baseline("planner_runtime_smoke") is not None
        assert monitor.check_regression(metric, threshold=1.2) is True
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_config_loader_returns_performance_baseline_path() -> None:
    TestConfigLoader.reload_config()
    baseline_path = TestConfigLoader.get_performance_baseline_path()

    assert baseline_path.name == "performance_baseline.json"
