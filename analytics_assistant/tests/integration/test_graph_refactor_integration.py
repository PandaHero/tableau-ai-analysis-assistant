# -*- coding: utf-8 -*-
"""重构后语义图的集成测试。"""

from __future__ import annotations

import ast
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from analytics_assistant.tests.integration.config_loader import TestConfigLoader

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestGraphCompilation:
    """验证语义图的装配结果符合重构设计。"""

    def test_create_semantic_parser_graph(self) -> None:
        from analytics_assistant.src.agents.semantic_parser.graph import (
            create_semantic_parser_graph,
        )
        from langgraph.graph import StateGraph

        graph = create_semantic_parser_graph()
        assert isinstance(graph, StateGraph)

    def test_compile_semantic_parser_graph(self) -> None:
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )

        compiled = compile_semantic_parser_graph()
        assert compiled is not None
        assert hasattr(compiled, "ainvoke") or hasattr(compiled, "invoke")

    def test_graph_has_expected_nodes(self) -> None:
        from analytics_assistant.src.agents.semantic_parser.graph import (
            create_semantic_parser_graph,
        )

        graph = create_semantic_parser_graph()
        node_names = set(graph.nodes.keys())

        expected_nodes = {
            "intent_router",
            "query_cache",
            "unified_feature_understanding",
            "parallel_retrieval",
            "prepare_prompt",
            "semantic_understanding",
            "output_validator",
            "filter_validator",
            "query_adapter",
            "error_corrector",
            "feedback_learner",
        }
        legacy_nodes = {
            "rule_prefilter",
            "feature_cache",
            "feature_extractor",
            "global_understanding_stage",
            "field_retriever",
            "dynamic_schema_builder",
            "modular_prompt_builder",
            "few_shot_manager",
        }

        assert expected_nodes.issubset(node_names)
        assert legacy_nodes.isdisjoint(node_names)

    def test_graph_import_stays_orchestration_free(self) -> None:
        graph_path = PROJECT_ROOT / "src" / "agents" / "semantic_parser" / "graph.py"
        tree = ast.parse(graph_path.read_text(encoding="utf-8"), filename=str(graph_path))

        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        assert not any("orchestration" in module_name for module_name in imports)


class TestIntentRouterIntegration:
    """验证不依赖真实外部服务的图内节点行为。"""

    @pytest.mark.asyncio
    async def test_data_query_intent(self) -> None:
        from analytics_assistant.src.agents.semantic_parser.graph import (
            intent_router_node,
        )

        result = await intent_router_node({"question": "上个月各地区销售额是多少"})
        assert result["intent_router_output"]["intent_type"] == "data_query"
        assert result["intent_router_output"]["confidence"] > 0

    @pytest.mark.asyncio
    async def test_irrelevant_intent(self) -> None:
        from analytics_assistant.src.agents.semantic_parser.graph import (
            intent_router_node,
        )

        result = await intent_router_node({"question": "今天天气怎么样"})
        assert result["intent_router_output"]["intent_type"] in {
            "irrelevant",
            "general",
            "clarification",
        }

    @pytest.mark.asyncio
    async def test_empty_question(self) -> None:
        from analytics_assistant.src.agents.semantic_parser.graph import (
            intent_router_node,
        )

        result = await intent_router_node({"question": ""})
        assert result["intent_router_output"]["intent_type"] == "irrelevant"

    @pytest.mark.asyncio
    async def test_intent_router_to_unified_feature_understanding(self, monkeypatch) -> None:
        from analytics_assistant.src.agents.semantic_parser.graph import (
            intent_router_node,
            query_cache_node,
            unified_feature_and_understanding_node,
        )
        from analytics_assistant.src.agents.semantic_parser.nodes import parallel
        from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
            AnalysisMode,
            AnalysisPlan,
            GlobalUnderstandingOutput,
            PlanMode,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
            FeatureExtractionOutput,
        )
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )

        async def fake_feature_extractor_node(state: dict[str, Any]) -> dict[str, Any]:
            del state
            feature_output = FeatureExtractionOutput(
                required_measures=["销售额"],
                required_dimensions=["地区", "日期"],
                confirmed_time_hints=["上个月"],
                confirmation_confidence=0.85,
                is_degraded=False,
            )
            return {
                "feature_extraction_output": feature_output.model_dump(),
                "is_degraded": False,
            }

        async def fake_run_global_understanding(
            question: str,
            *,
            prefilter_result,
            feature_output,
            field_semantic=None,
            feature_flags=None,
        ) -> GlobalUnderstandingOutput:
            del prefilter_result, feature_output, field_semantic, feature_flags
            plan = AnalysisPlan(
                plan_mode=PlanMode.DIRECT_QUERY,
                single_query_feasible=True,
                needs_planning=False,
                requires_llm_reasoning=False,
                goal=question,
                execution_strategy="single_query",
                reasoning_focus=["销售额", "地区"],
                sub_questions=[],
                retrieval_focus_terms=["销售额", "地区"],
                planner_confidence=0.9,
            )
            return GlobalUnderstandingOutput(
                analysis_mode=AnalysisMode.COMPLEX_SINGLE_QUERY,
                single_query_feasible=True,
                primary_restated_question=question,
                llm_confidence=0.9,
                analysis_plan=plan,
            )

        monkeypatch.setattr(parallel, "_should_allow_semantic_lookup", lambda *_: False)
        monkeypatch.setattr(parallel, "feature_extractor_node", fake_feature_extractor_node)
        monkeypatch.setattr(parallel, "run_global_understanding", fake_run_global_understanding)

        state: dict[str, Any] = {
            "question": "上个月各地区销售额",
            "datasource_luid": "test-e2e-ds",
            "current_time": datetime.now().isoformat(),
        }
        config = create_workflow_config(
            thread_id="test-unified",
            context=WorkflowContext(
                datasource_luid="test-e2e-ds",
                current_time=datetime.now().isoformat(),
            ),
        )

        state.update(await intent_router_node(state))
        assert state["intent_router_output"]["intent_type"] == "data_query"

        state.update(await query_cache_node(state, config))
        assert state["cache_hit"] is False

        state.update(await unified_feature_and_understanding_node(state, config))
        assert "prefilter_result" in state
        assert "feature_extraction_output" in state
        assert "global_understanding" in state
        assert "analysis_plan" in state
        assert len(state["prefilter_result"].get("time_hints", [])) > 0

    @pytest.mark.asyncio
    async def test_compiled_graph_irrelevant_query(self) -> None:
        from analytics_assistant.src.agents.semantic_parser.graph import (
            compile_semantic_parser_graph,
        )
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )
        from langgraph.checkpoint.memory import MemorySaver

        compiled = compile_semantic_parser_graph(checkpointer=MemorySaver())
        config = create_workflow_config(
            thread_id="test-compiled",
            context=WorkflowContext(
                datasource_luid="test-compiled-ds",
                current_time=datetime.now().isoformat(),
            ),
        )

        final_state = await compiled.ainvoke(
            {
                "question": "今天天气怎么样",
                "datasource_luid": "test-compiled-ds",
                "current_time": datetime.now().isoformat(),
            },
            config,
        )
        assert final_state["intent_router_output"]["intent_type"] in {
            "irrelevant",
            "general",
            "clarification",
        }


class TestWorkflowContextIntegration:
    """验证 WorkflowContext 在图中的传递契约。"""

    def test_workflow_context_satisfies_protocol(self) -> None:
        from analytics_assistant.src.core.interfaces import WorkflowContextProtocol
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
        )

        ctx = WorkflowContext(datasource_luid="test-ds-001")
        assert isinstance(ctx, WorkflowContextProtocol)

    def test_get_context_from_config(self) -> None:
        from analytics_assistant.src.agents.base.context import get_context
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )

        ctx = WorkflowContext(datasource_luid="test-ds-002")
        config = create_workflow_config(thread_id="test-thread", context=ctx)

        extracted = get_context(config)
        assert extracted is ctx
        assert extracted.datasource_luid == "test-ds-002"

    @pytest.mark.asyncio
    async def test_query_cache_node_with_context(self) -> None:
        from analytics_assistant.src.agents.semantic_parser.graph import (
            query_cache_node,
        )
        from analytics_assistant.src.orchestration.workflow.context import (
            WorkflowContext,
            create_workflow_config,
        )

        config = create_workflow_config(
            thread_id="test-thread",
            context=WorkflowContext(datasource_luid="test-ds-003"),
        )
        result = await query_cache_node(
            {
                "question": "测试查询",
                "datasource_luid": "test-ds-003",
            },
            config,
        )
        assert result["cache_hit"] is False


class TestEndToEndWithRealLLM:
    """真实 LLM 测试默认关闭，避免离线环境误报。"""

    @pytest.fixture
    def require_real_llm(self) -> None:
        if not TestConfigLoader.allow_real_llm_tests():
            pytest.skip(
                "未显式开启真实 LLM 集成测试，设置 AA_RUN_REAL_LLM_TESTS=1 后再运行"
            )

        from analytics_assistant.src.infra.config import get_config

        config = get_config()
        ai_config = config.get("ai", {})
        llm_models = ai_config.get("llm_models", [])
        has_api_key = any(
            model.get("api_key")
            for model in llm_models
            if isinstance(model, dict)
        )
        assert has_api_key, "真实 LLM 测试缺少 ai.llm_models.api_key 配置"

    @pytest.mark.asyncio
    async def test_semantic_understanding_with_real_llm(
        self,
        require_real_llm,
    ) -> None:
        from analytics_assistant.src.agents.semantic_parser.graph import (
            semantic_understanding_node,
        )
        from analytics_assistant.src.core.schemas.semantic_output import (
            SemanticOutput,
        )

        state: dict[str, Any] = {
            "question": "各地区的销售额",
            "field_candidates": [
                {
                    "field_name": "Region",
                    "field_caption": "地区",
                    "field_type": "dimension",
                    "data_type": "string",
                    "description": "销售地区",
                    "confidence": 0.9,
                },
                {
                    "field_name": "Sales",
                    "field_caption": "销售额",
                    "field_type": "measure",
                    "data_type": "real",
                    "description": "销售金额",
                    "confidence": 0.95,
                },
            ],
            "few_shot_examples": [],
            "current_time": datetime.now().isoformat(),
        }

        result = await semantic_understanding_node(state)
        semantic_output = SemanticOutput.model_validate(result["semantic_output"])
        assert semantic_output.query_id is not None
        assert semantic_output.restated_question

        logger.info(
            "real llm semantic output: query_id=%s restated=%s",
            semantic_output.query_id,
            semantic_output.restated_question,
        )
