# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
repo_root = os.path.dirname(project_root)
for candidate in (repo_root, project_root):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from analytics_assistant.src.platform.tableau.client import (
    TableauDatasourceAmbiguityError,
    VizQLClient,
)


@pytest.mark.asyncio
async def test_unique_exact_datasource_name_returns_luid() -> None:
    client = VizQLClient()
    payload = {
        "data": {
            "publishedDatasources": [
                {"luid": "ds_001", "name": "Revenue", "projectName": "Sales"},
            ]
        }
    }

    with patch.object(client, "graphql_query", AsyncMock(return_value=payload)):
        luid = await client.get_datasource_luid_by_name(
            datasource_name="Revenue",
            api_key="token",
        )

    assert luid == "ds_001"


@pytest.mark.asyncio
async def test_duplicate_datasource_name_requires_project_name() -> None:
    client = VizQLClient()
    payload = {
        "data": {
            "publishedDatasources": [
                {"luid": "ds_001", "name": "Revenue", "projectName": "Sales"},
                {"luid": "ds_002", "name": "Revenue", "projectName": "Ops"},
            ]
        }
    }

    with patch.object(client, "graphql_query", AsyncMock(return_value=payload)):
        with pytest.raises(ValueError, match="project_name"):
            await client.get_datasource_luid_by_name(
                datasource_name="Revenue",
                api_key="token",
            )


@pytest.mark.asyncio
async def test_project_suffix_in_name_resolves_exact_match() -> None:
    client = VizQLClient()
    payload = {
        "data": {
            "publishedDatasources": [
                {"luid": "ds_001", "name": "Revenue", "projectName": "Sales"},
                {"luid": "ds_002", "name": "Revenue", "projectName": "Ops"},
            ]
        }
    }

    with patch.object(client, "graphql_query", AsyncMock(return_value=payload)):
        luid = await client.get_datasource_luid_by_name(
            datasource_name="Revenue | 项目 : Sales",
            api_key="token",
        )

    assert luid == "ds_001"


@pytest.mark.asyncio
async def test_duplicate_datasource_name_exposes_disambiguation_choices() -> None:
    client = VizQLClient()
    payload = {
        "data": {
            "publishedDatasources": [
                {"luid": "ds_001", "name": "Revenue", "projectName": "Sales"},
                {"luid": "ds_002", "name": "Revenue", "projectName": "Ops"},
            ]
        }
    }

    with patch.object(client, "graphql_query", AsyncMock(return_value=payload)):
        with pytest.raises(TableauDatasourceAmbiguityError) as exc_info:
            await client.get_datasource_luid_by_name(
                datasource_name="Revenue",
                api_key="token",
            )

    assert exc_info.value.datasource_name == "Revenue"
    assert exc_info.value.choices == [
        {"datasource_luid": "ds_001", "name": "Revenue", "project": "Sales"},
        {"datasource_luid": "ds_002", "name": "Revenue", "project": "Ops"},
    ]
