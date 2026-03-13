# -*- coding: utf-8 -*-
import os
import sys

project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
repo_root = os.path.dirname(project_root)
for candidate in (repo_root, project_root):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from analytics_assistant.src.platform.tableau.auth import (
    _build_auth_cache_key,
    _build_cache_candidates,
    _resolve_cache_key_for_auth,
)


def test_cache_key_includes_site_principal_auth_method_and_scope_hash() -> None:
    key = _build_auth_cache_key(
        domain="https://tableau.example.com/",
        site="Sales",
        principal="alice@example.com",
        auth_method="jwt",
        scopes=["tableau:content:read", "tableau:views:download"],
    )

    assert key.startswith("tableau:token:https://tableau.example.com:sales:")
    assert ":alice@example.com:jwt:" in key


def test_cache_candidates_are_isolated_by_auth_method() -> None:
    params = {
        "domain": "https://tableau.example.com",
        "site": "Sales",
        "jwt_config": {
            "client_id": "cid",
            "secret_id": "sid",
            "secret": "sec",
            "user": "alice@example.com",
            "scopes": ["tableau:content:read"],
        },
        "pat_config": {
            "name": "pat-user",
            "secret": "pat-secret",
        },
    }

    candidates = _build_cache_candidates(params)

    assert len(candidates) == 2
    assert any(":alice@example.com:jwt:" in candidate for candidate in candidates)
    assert any(":pat-user:pat:" in candidate for candidate in candidates)


def test_resolve_cache_key_uses_actual_auth_method() -> None:
    params = {
        "domain": "https://tableau.example.com",
        "site": "Sales",
        "jwt_config": {
            "client_id": "cid",
            "secret_id": "sid",
            "secret": "sec",
            "user": "alice@example.com",
            "scopes": ["tableau:content:read"],
        },
        "pat_config": {
            "name": "pat-user",
            "secret": "pat-secret",
        },
    }

    key = _resolve_cache_key_for_auth(params, "pat")

    assert ":pat-user:pat:" in key
