# -*- coding: utf-8 -*-
"""
IntentRouter regression tests.
"""

import pytest

from analytics_assistant.src.agents.semantic_parser.components.intent_router import (
    IntentRouter,
)
from analytics_assistant.src.agents.semantic_parser.schemas.intent import IntentType


@pytest.mark.asyncio
async def test_mixed_metadata_and_data_signal_prefers_data_query():
    router = IntentRouter()

    result = await router.route("可以查询什么地区的销售额最高")

    assert result.intent_type == IntentType.DATA_QUERY
    assert result.source == "L0_RULES"


@pytest.mark.asyncio
async def test_metadata_query_is_not_overridden_by_ambiguous_analysis_verbs():
    router = IntentRouter()

    result = await router.route("可以查询什么字段")

    assert result.intent_type == IntentType.GENERAL
    assert result.source == "L0_RULES"
