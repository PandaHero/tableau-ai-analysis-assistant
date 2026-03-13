# -*- coding: utf-8 -*-
"""真实 Tableau + LLM 语义解析端到端集成测试。

默认跳过，只有显式开启外部依赖后才运行：
- `AA_RUN_REAL_LLM_TESTS=1`
- `AA_RUN_TABLEAU_INTEGRATION_TESTS=1`

也可以用 `AA_RUN_EXTERNAL_INTEGRATION_TESTS=1` 一次性打开两类测试。
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

import pytest

from analytics_assistant.tests.integration.base import BaseIntegrationTest
from analytics_assistant.tests.integration.config_loader import TestConfigLoader
from analytics_assistant.tests.integration.test_data_manager import TestDataManager
from analytics_assistant.src.agents.semantic_parser.graph import (
    compile_semantic_parser_graph,
)
from analytics_assistant.src.core.schemas.enums import FilterType, IntentType
from analytics_assistant.src.core.schemas.semantic_output import SemanticOutput
from analytics_assistant.src.orchestration.workflow.context import (
    WorkflowContext,
    create_workflow_config,
)
from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader

logger = logging.getLogger(__name__)


def _configured_value(config: dict[str, Any], key: str) -> str:
    """读取测试配置中的可用值，自动过滤未展开的环境变量。"""
    value = str(config.get(key) or "").strip()
    if not value or "${" in value:
        return ""
    return value


class TestE2ESemanticParsing(BaseIntegrationTest):
    """验证真实外部依赖下的语义解析主链路。"""

    _resolved_datasource_luid: str = ""
    _data_model_cache: dict[str, Any] = {}

    @classmethod
    def setup_class(cls) -> None:
        """只在显式开启外部依赖时初始化真实集成环境。"""
        cls._ensure_external_tests_enabled()
        super().setup_class()

        cls._timeout = TestConfigLoader.get_timeout("semantic_parsing")
        cls._semantic_parser_graph = compile_semantic_parser_graph()
        cls._test_data_manager = TestDataManager(TestConfigLoader.get_test_data_dir())
        cls._preload_data_model()

    @classmethod
    def _ensure_external_tests_enabled(cls) -> None:
        if not TestConfigLoader.allow_real_llm_tests():
            pytest.skip(
                "未显式开启真实 LLM 集成测试，设置 AA_RUN_REAL_LLM_TESTS=1 后再运行",
                allow_module_level=True,
            )
        if not TestConfigLoader.allow_tableau_integration_tests():
            pytest.skip(
                "未显式开启 Tableau 集成测试，设置 AA_RUN_TABLEAU_INTEGRATION_TESTS=1 后再运行",
                allow_module_level=True,
            )

    @classmethod
    def _preload_data_model(cls) -> None:
        tableau_config = TestConfigLoader.get_tableau_config()
        datasource_luid = _configured_value(tableau_config, "test_datasource_luid")
        datasource_name = _configured_value(tableau_config, "test_datasource_name")

        if not datasource_luid and not datasource_name:
            pytest.skip(
                "未配置测试数据源，请设置 tableau.test_datasource_luid 或 tableau.test_datasource_name",
                allow_module_level=True,
            )

        async def load() -> None:
            async with TableauDataLoader() as loader:
                if datasource_luid:
                    data_model = await loader.load_data_model(
                        datasource_id=datasource_luid,
                        skip_index_creation=True,
                    )
                else:
                    data_model = await loader.load_data_model(
                        datasource_name=datasource_name,
                        skip_index_creation=True,
                    )

                cls._resolved_datasource_luid = data_model.datasource_id
                cls._data_model_cache[data_model.datasource_id] = data_model
                logger.info(
                    "预加载真实数据模型完成: datasource=%s fields=%s",
                    data_model.datasource_id,
                    len(getattr(data_model, "fields", []) or []),
                )

        asyncio.run(load())

    def _get_question_text(self, question_id: str) -> str:
        question = self._test_data_manager.get_question_by_id(question_id)
        assert question is not None, f"测试问题不存在: {question_id}"
        return question.question

    async def _ainvoke_question(self, question: str) -> tuple[dict[str, Any], float]:
        datasource_luid = self._resolved_datasource_luid or self._get_test_datasource_luid()
        assert datasource_luid, "未解析出测试数据源 LUID"

        if datasource_luid not in self._data_model_cache:
            async with TableauDataLoader() as loader:
                self._data_model_cache[datasource_luid] = await loader.load_data_model(
                    datasource_id=datasource_luid,
                    skip_index_creation=True,
                )

        data_model = self._data_model_cache[datasource_luid]
        current_time = datetime.now().isoformat()
        context = WorkflowContext(
            datasource_luid=datasource_luid,
            data_model=data_model,
            current_time=current_time,
        )
        config = create_workflow_config(
            thread_id=f"semantic-e2e-{int(time.time() * 1000)}",
            context=context,
        )
        state = {
            "question": question,
            "datasource_luid": datasource_luid,
            "current_time": current_time,
        }

        start = time.perf_counter()
        result = await self._semantic_parser_graph.ainvoke(state, config)
        elapsed = time.perf_counter() - start
        return result, elapsed

    def _parse_question(self, question: str) -> tuple[dict[str, Any], float]:
        return asyncio.run(self._ainvoke_question(question))

    def _assert_successful_parse(
        self,
        result: dict[str, Any],
        elapsed: float,
    ) -> SemanticOutput:
        self._record_metric("semantic_parsing_time", elapsed)

        assert elapsed <= self._timeout, f"语义解析超时: {elapsed:.2f}s > {self._timeout}s"
        assert result.get("semantic_output") is not None, "未生成 semantic_output"

        intent = result.get("intent_router_output", {}).get("intent_type")
        assert intent == IntentType.DATA_QUERY or intent == IntentType.DATA_QUERY.value

        semantic_output = SemanticOutput.model_validate(result["semantic_output"])
        assert 0.0 <= semantic_output.self_check.overall_confidence <= 1.0
        return semantic_output

    @pytest.mark.smoke
    @pytest.mark.e2e
    def test_simple_measure_query(self) -> None:
        result, elapsed = self._parse_question(self._get_question_text("simple_001"))
        semantic_output = self._assert_successful_parse(result, elapsed)

        assert semantic_output.what.measures, "简单查询至少应识别出一个度量"
        assert result.get("semantic_query") is not None, "简单查询应完成到 query_adapter"
        assert not semantic_output.needs_clarification

    @pytest.mark.core
    @pytest.mark.e2e
    def test_time_range_query(self) -> None:
        result, elapsed = self._parse_question(self._get_question_text("time_series_001"))
        semantic_output = self._assert_successful_parse(result, elapsed)

        has_time_filter = any(
            filter_obj.filter_type == FilterType.DATE_RANGE
            for filter_obj in semantic_output.where.filters
        )
        has_time_dimension = any(
            dimension.date_granularity is not None
            for dimension in semantic_output.where.dimensions
        )
        assert has_time_filter or has_time_dimension, "时间序列查询应识别出时间过滤或时间粒度"

    @pytest.mark.core
    @pytest.mark.e2e
    def test_calculation_query(self) -> None:
        result, elapsed = self._parse_question(self._get_question_text("calculation_001"))
        semantic_output = self._assert_successful_parse(result, elapsed)

        assert semantic_output.computations, "计算型问题应生成派生计算"

    @pytest.mark.core
    @pytest.mark.e2e
    def test_ranking_query(self) -> None:
        result, elapsed = self._parse_question(self._get_question_text("ranking_001"))
        semantic_output = self._assert_successful_parse(result, elapsed)

        top_n_filters = [
            filter_obj
            for filter_obj in semantic_output.where.filters
            if filter_obj.filter_type == FilterType.TOP_N
        ]
        assert top_n_filters, "排名类问题应生成 Top N 过滤器"
        assert any(getattr(filter_obj, "n", 0) > 0 for filter_obj in top_n_filters)

    @pytest.mark.e2e
    def test_confidence_range_for_sample_queries(self) -> None:
        sample_ids = ["simple_001", "simple_002", "filter_001"]

        for question_id in sample_ids:
            result, elapsed = self._parse_question(self._get_question_text(question_id))
            semantic_output = self._assert_successful_parse(result, elapsed)
            assert 0.0 <= semantic_output.self_check.overall_confidence <= 1.0

    @pytest.mark.e2e
    def test_performance_requirement(self) -> None:
        result, elapsed = self._parse_question(self._get_question_text("simple_001"))
        self._assert_successful_parse(result, elapsed)
        assert elapsed <= 30.0, f"端到端语义解析超过 30 秒预算: {elapsed:.2f}s"
