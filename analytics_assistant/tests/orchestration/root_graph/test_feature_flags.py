# -*- coding: utf-8 -*-
"""root_graph 功能开关解析测试。"""

from __future__ import annotations

import pytest

from analytics_assistant.src.orchestration.root_graph.feature_flags import (
    resolve_root_graph_feature_flags,
)


class _ConfigStub:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def get(self, key: str, default=None):
        return self._payload.get(key, default)


def test_resolve_root_graph_feature_flags_uses_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "analytics_assistant.src.orchestration.root_graph.feature_flags.get_config",
        lambda: _ConfigStub({
            "root_graph": {
                "feature_flags": {
                    "defaults": {
                        "why_screening_wave": True,
                    },
                }
            }
        }),
    )

    flags = resolve_root_graph_feature_flags(
        tableau_username="alice",
        session_id="sess-default",
    )

    assert flags == {"why_screening_wave": True}


def test_resolve_root_graph_feature_flags_applies_override_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "analytics_assistant.src.orchestration.root_graph.feature_flags.get_config",
        lambda: _ConfigStub({
            "root_graph": {
                "feature_flags": {
                    "defaults": {
                        "why_screening_wave": True,
                    },
                    "tenant_overrides": {
                        "alice": {"why_screening_wave": False},
                    },
                    "session_overrides": {
                        "sess-flag": {"why_screening_wave": True},
                    },
                }
            }
        }),
    )

    flags = resolve_root_graph_feature_flags(
        tableau_username="alice",
        session_id="sess-flag",
        request_overrides={"why_screening_wave": False},
    )

    assert flags == {"why_screening_wave": False}
