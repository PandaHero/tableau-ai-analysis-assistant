"""Observability module for metrics and monitoring.

This module provides metrics collection and structured logging for
the Semantic Parser and other components.

Key components:
- SemanticParserMetrics: Dataclass for collecting parser metrics
- get_metrics_from_config: Get metrics from RunnableConfig
- set_metrics_to_config: Set metrics to RunnableConfig

Design principles:
- Metrics are passed through RunnableConfig, NOT through State
- Metrics are serialized to dict at subgraph exit for logging
- Metrics support both simple increment and counter-style (.inc()) patterns
"""

from tableau_assistant.src.infra.observability.metrics import (
    SemanticParserMetrics,
    get_metrics_from_config,
    set_metrics_to_config,
    ensure_metrics_in_config,
)


__all__ = [
    "SemanticParserMetrics",
    "get_metrics_from_config",
    "set_metrics_to_config",
    "ensure_metrics_in_config",
]
