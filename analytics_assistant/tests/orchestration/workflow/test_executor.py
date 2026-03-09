# -*- coding: utf-8 -*-
"""
WorkflowExecutor 可观测性测试。

重点验证 clarification / error 等非 data 分支也会透传阶段指标，
避免前端和日志在异常或澄清场景下丢失耗时信息。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analytics_assistant.src.agents.insight.schemas.output import (
    AnalysisLevel,
    Finding,
    FindingType,
    InsightOutput,
)
from analytics_assistant.src.agents.replanner.schemas.output import (
    CandidateQuestion,
    ReplanDecision,
)
from analytics_assistant.src.orchestration.workflow.executor import WorkflowExecutor


class _DummyVizQLClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _DummyDataModel:
    datasource_id = "ds-test"
    fields = []
    _field_samples_cache = {"Sold Nm": {"sample_values": ["成都高金食品有限公司"]}}
    _field_semantic_cache = {"Sold Nm": {"category": "organization"}}


class _ClarificationGraph:
    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "semantic_understanding": {
                "needs_clarification": True,
                "clarification_question": "请选择省份字段",
                "clarification_options": ["销售方 (Sold Nm)"],
                "clarification_source": "semantic_understanding",
                "optimization_metrics": {
                    "semantic_understanding_ms": 12.5,
                    "semantic_understanding_clarification_shortcut": True,
                },
            },
        }


class _ErrorGraph:
    async def astream(self, initial_state, config, stream_mode="updates"):
        if False:
            yield {}
        raise RuntimeError("graph exploded")


def _make_semantic_output(
    query_id: str,
    *,
    restated_question: str,
    measure: str = "销售额",
    dimension: str = "地区",
) -> dict:
    return {
        "query_id": query_id,
        "restated_question": restated_question,
        "what": {"measures": [{"field_name": measure}]},
        "where": {
            "dimensions": [{"field_name": dimension}],
            "filters": [],
        },
    }


def _make_insight_output(
    *,
    summary: str = "华东区销售额下降主要集中在渠道分布变化",
) -> InsightOutput:
    return InsightOutput(
        findings=[
            Finding(
                finding_type=FindingType.ANOMALY,
                analysis_level=AnalysisLevel.DIAGNOSTIC,
                description=summary,
                supporting_data={"segment": "华东区"},
                confidence=0.87,
            )
        ],
        summary=summary,
        overall_confidence=0.87,
    )


def _make_analysis_plan_dict() -> dict:
    return {
        "plan_mode": "why_analysis",
        "needs_planning": True,
        "requires_llm_reasoning": True,
        "goal": "解释华东区销售额下降原因",
        "execution_strategy": "sequential",
        "reasoning_focus": [
            "先验证现象",
            "再定位异常切片",
            "最后做归因总结",
        ],
        "sub_questions": [
            {
                "step_id": "step-1",
                "title": "验证现象",
                "goal": "确认用户想解释的现象是否真实存在",
                "question": "为什么华东区销售额下降了？",
                "purpose": "验证现象",
                "step_type": "query",
                "uses_primary_query": True,
                "depends_on": [],
                "semantic_focus": ["销售额", "华东区", "同比"],
                "expected_output": "确认现象是否成立，并明确差异方向与幅度",
                "candidate_axes": [],
                "clarification_if_missing": ["比较基线", "时间范围"],
            },
            {
                "step_id": "step-2",
                "title": "定位异常切片",
                "goal": "定位最异常的对象或切片",
                "question": "按地区和产品找出贡献最大的异常切片",
                "purpose": "定位异常切片",
                "step_type": "query",
                "uses_primary_query": False,
                "depends_on": ["step-1"],
                "semantic_focus": ["异常定位", "产品", "地区"],
                "expected_output": "定位异常对象集合或关键切片",
                "candidate_axes": ["地区", "产品"],
                "clarification_if_missing": [],
            },
            {
                "step_id": "step-3",
                "title": "归因总结",
                "goal": "汇总证据链并输出原因总结",
                "question": "结合前两步结果总结原因",
                "purpose": "归因总结",
                "step_type": "synthesis",
                "uses_primary_query": False,
                "depends_on": ["step-1", "step-2"],
                "semantic_focus": ["证据汇总", "原因归纳"],
                "expected_output": "形成结论、证据摘要和待确认口径",
                "candidate_axes": [],
                "clarification_if_missing": [],
            },
        ],
        "retrieval_focus_terms": ["销售额", "华东区"],
        "planner_confidence": 0.93,
    }


def _make_deep_analysis_plan_dict() -> dict:
    return {
        "plan_mode": "why_analysis",
        "needs_planning": True,
        "requires_llm_reasoning": True,
        "goal": "解释华东区销售额下降原因",
        "execution_strategy": "sequential",
        "reasoning_focus": [
            "先验证现象",
            "先按省份锁定异常范围",
            "再按产品继续下钻",
            "最后汇总证据链",
        ],
        "sub_questions": [
            {
                "step_id": "step-1",
                "title": "验证现象",
                "goal": "确认用户想解释的现象是否真实存在",
                "question": "为什么华东区销售额下降了？",
                "purpose": "验证现象",
                "step_type": "query",
                "uses_primary_query": True,
                "depends_on": [],
                "semantic_focus": ["销售额", "华东区", "同比"],
                "expected_output": "确认现象是否成立，并明确差异方向与幅度",
                "candidate_axes": [],
                "clarification_if_missing": ["比较基线", "时间范围"],
            },
            {
                "step_id": "step-2",
                "title": "按省份定位异常区域",
                "goal": "先锁定最异常的省份或区域",
                "question": "按省份定位最异常的区域",
                "purpose": "缩小异常范围",
                "step_type": "query",
                "uses_primary_query": False,
                "depends_on": ["step-1"],
                "semantic_focus": ["异常定位", "省份"],
                "expected_output": "识别需要继续下钻的异常省份",
                "candidate_axes": ["省份"],
                "clarification_if_missing": [],
            },
            {
                "step_id": "step-3",
                "title": "按产品继续下钻",
                "goal": "在异常省份内定位贡献最大的产品切片",
                "question": "在已识别的异常省份内按产品定位异常切片",
                "purpose": "继续下钻定位原因",
                "step_type": "query",
                "uses_primary_query": False,
                "depends_on": ["step-1", "step-2"],
                "semantic_focus": ["异常定位", "产品", "下钻"],
                "expected_output": "识别异常产品或关键切片",
                "candidate_axes": ["产品"],
                "clarification_if_missing": [],
            },
            {
                "step_id": "step-4",
                "title": "归因总结",
                "goal": "汇总证据链并输出原因总结",
                "question": "结合前三步结果总结原因",
                "purpose": "归因总结",
                "step_type": "synthesis",
                "uses_primary_query": False,
                "depends_on": ["step-1", "step-2", "step-3"],
                "semantic_focus": ["证据汇总", "原因归纳"],
                "expected_output": "形成结论、证据摘要和待确认口径",
                "candidate_axes": [],
                "clarification_if_missing": [],
            },
        ],
        "retrieval_focus_terms": ["销售额", "华东区", "省份", "产品"],
        "planner_confidence": 0.91,
    }


def _make_global_understanding_dict() -> dict:
    return {
        "analysis_mode": "why_analysis",
        "single_query_feasible": False,
        "single_query_blockers": [
            "multi_hop_reasoning",
            "dynamic_axis_selection",
        ],
        "decomposition_reason": "why 问题需要证据链和逐步验证解释轴",
        "needs_clarification": False,
        "clarification_question": None,
        "clarification_options": [],
        "primary_restated_question": "为什么华东区销售额下降了",
        "risk_flags": [],
        "llm_confidence": 0.93,
        "analysis_plan": _make_analysis_plan_dict(),
    }


def _make_deep_global_understanding_dict() -> dict:
    return {
        "analysis_mode": "why_analysis",
        "single_query_feasible": False,
        "single_query_blockers": [
            "multi_hop_reasoning",
            "dynamic_axis_selection",
        ],
        "decomposition_reason": "why 问题需要先定位异常范围，再逐步下钻并汇总证据",
        "needs_clarification": False,
        "clarification_question": None,
        "clarification_options": [],
        "primary_restated_question": "为什么华东区销售额下降了",
        "risk_flags": [],
        "llm_confidence": 0.91,
        "analysis_plan": _make_deep_analysis_plan_dict(),
    }


def _make_complex_single_query_global_understanding_dict() -> dict:
    return {
        "analysis_mode": "complex_single_query",
        "single_query_feasible": True,
        "single_query_blockers": [],
        "decomposition_reason": "虽然有时间对比，但仍可由一条查询表达",
        "needs_clarification": False,
        "clarification_question": None,
        "clarification_options": [],
        "primary_restated_question": "比较今年和去年各地区利润率变化",
        "risk_flags": [],
        "llm_confidence": 0.88,
        "analysis_plan": {
            "plan_mode": "direct_query",
            "single_query_feasible": True,
            "needs_planning": False,
            "requires_llm_reasoning": True,
            "decomposition_reason": "虽然有时间对比，但仍可由一条查询表达",
            "goal": "直接解析复杂单查问题",
            "execution_strategy": "single_query",
            "reasoning_focus": ["保持单查表达，但保留复杂推理路径"],
            "sub_questions": [],
            "risk_flags": [],
            "needs_clarification": False,
            "clarification_question": None,
            "clarification_options": [],
            "retrieval_focus_terms": ["利润率", "地区"],
            "planner_confidence": 0.88,
        },
    }


class _PlannedGraph:
    def __init__(self):
        self.followup_questions = []
        self.followup_evidence_contexts = []
        self.followup_step_intents = []

    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "feedback_learner": {
                "parse_result": {
                    "success": True,
                    "query_id": "q-main",
                    "semantic_output": _make_semantic_output(
                        "q-main",
                        restated_question="为什么华东区销售额下降了",
                        measure="销售额",
                        dimension="地区",
                    ),
                    "query": {"query": "main"},
                    "analysis_plan": _make_analysis_plan_dict(),
                    "optimization_metrics": {
                        "semantic_understanding_ms": 12.5,
                    },
                },
            },
        }

    async def ainvoke(self, initial_state, config):
        self.followup_questions.append(initial_state["question"])
        self.followup_evidence_contexts.append(initial_state.get("evidence_context"))
        self.followup_step_intents.append(initial_state.get("current_step_intent"))
        return {
            "parse_result": {
                "success": True,
                "query_id": "q-step-2",
                "semantic_output": _make_semantic_output(
                    "q-step-2",
                    restated_question=initial_state["question"],
                    measure="销售额",
                    dimension="产品",
                ),
                "query": {"query": "followup"},
                "optimization_metrics": {
                    "semantic_understanding_ms": 9.8,
                },
            },
            "optimization_metrics": {
                "semantic_understanding_ms": 9.8,
            },
        }


class _PlannedGlobalUnderstandingGraph(_PlannedGraph):
    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "feedback_learner": {
                "parse_result": {
                    "success": True,
                    "query_id": "q-main",
                    "semantic_output": _make_semantic_output(
                        "q-main",
                        restated_question="为什么华东区销售额下降了",
                        measure="销售额",
                        dimension="地区",
                    ),
                    "query": {"query": "main"},
                    "global_understanding": _make_global_understanding_dict(),
                    "optimization_metrics": {
                        "semantic_understanding_ms": 12.5,
                        "global_understanding_llm_used": True,
                        "global_understanding_fallback_used": False,
                    },
                },
            },
        }


class _CachedPlannedGlobalUnderstandingGraph(_PlannedGraph):
    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "feedback_learner": {
                "parse_result": {
                    "success": True,
                    "query_id": "q-main-cache-hit",
                    "semantic_output": _make_semantic_output(
                        "q-main-cache-hit",
                        restated_question="为什么华东区销售额下降了",
                        measure="销售额",
                        dimension="地区",
                    ),
                    "query": {"query": "main"},
                    "global_understanding": _make_global_understanding_dict(),
                    "analysis_plan": _make_analysis_plan_dict(),
                    "query_cache_hit": True,
                    "optimization_metrics": {
                        "semantic_understanding_ms": 3.1,
                        "global_understanding_llm_used": False,
                        "global_understanding_fallback_used": False,
                    },
                },
            },
        }


class _DeepPlannedGlobalUnderstandingGraph:
    def __init__(self):
        self.followup_questions = []
        self.followup_evidence_contexts = []
        self.followup_step_intents = []
        self.followup_histories = []

    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "feedback_learner": {
                "parse_result": {
                    "success": True,
                    "query_id": "q-main-deep",
                    "semantic_output": _make_semantic_output(
                        "q-main-deep",
                        restated_question="为什么华东区销售额下降了",
                        measure="销售额",
                        dimension="地区",
                    ),
                    "query": {"query": "main"},
                    "global_understanding": _make_deep_global_understanding_dict(),
                    "optimization_metrics": {
                        "semantic_understanding_ms": 13.1,
                        "global_understanding_llm_used": True,
                        "global_understanding_fallback_used": False,
                    },
                },
            },
        }

    async def ainvoke(self, initial_state, config):
        self.followup_questions.append(initial_state["question"])
        self.followup_evidence_contexts.append(initial_state.get("evidence_context"))
        self.followup_step_intents.append(initial_state.get("current_step_intent"))
        self.followup_histories.append(initial_state.get("history"))

        if len(self.followup_questions) == 1:
            return {
                "parse_result": {
                    "success": True,
                    "query_id": "q-step-2",
                    "semantic_output": _make_semantic_output(
                        "q-step-2",
                        restated_question=initial_state["question"],
                        measure="销售额",
                        dimension="省份",
                    ),
                    "query": {"query": "followup-province"},
                    "optimization_metrics": {
                        "semantic_understanding_ms": 10.2,
                    },
                },
                "optimization_metrics": {
                    "semantic_understanding_ms": 10.2,
                },
            }

        return {
            "parse_result": {
                "success": True,
                "query_id": "q-step-3",
                "semantic_output": _make_semantic_output(
                    "q-step-3",
                    restated_question=initial_state["question"],
                    measure="销售额",
                    dimension="产品",
                ),
                "query": {"query": "followup-product"},
                "optimization_metrics": {
                    "semantic_understanding_ms": 9.6,
                },
            },
            "optimization_metrics": {
                "semantic_understanding_ms": 9.6,
            },
        }


class _ComplexSingleQueryGraph:
    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "feedback_learner": {
                "parse_result": {
                    "success": True,
                    "query_id": "q-complex-single",
                    "semantic_output": _make_semantic_output(
                        "q-complex-single",
                        restated_question="比较今年和去年各地区利润率变化",
                        measure="利润率",
                        dimension="地区",
                    ),
                    "query": {"query": "single"},
                    "global_understanding": _make_complex_single_query_global_understanding_dict(),
                    "optimization_metrics": {
                        "semantic_understanding_ms": 15.2,
                        "global_understanding_llm_used": True,
                        "global_understanding_fallback_used": False,
                    },
                },
            },
        }


class _SingleQueryGraph:
    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "feedback_learner": {
                "parse_result": {
                    "success": True,
                    "query_id": "q-single",
                    "semantic_output": _make_semantic_output(
                        "q-single",
                        restated_question="查看各地区销售额",
                        measure="销售额",
                        dimension="地区",
                    ),
                    "query": {"query": "single"},
                    "optimization_metrics": {
                        "semantic_understanding_ms": 11.4,
                    },
                },
            },
        }


class _QuestionAwareSingleQueryGraph:
    def __init__(self):
        self.questions = []

    async def astream(self, initial_state, config, stream_mode="updates"):
        question = initial_state["question"]
        self.questions.append(question)
        if "渠道" in question:
            query_id = "q-followup"
            dimension = "渠道"
        else:
            query_id = "q-single"
            dimension = "地区"

        yield {
            "feedback_learner": {
                "parse_result": {
                    "success": True,
                    "query_id": query_id,
                    "semantic_output": _make_semantic_output(
                        query_id,
                        restated_question=question,
                        measure="销售额",
                        dimension=dimension,
                    ),
                    "query": {"query": query_id},
                    "optimization_metrics": {
                        "semantic_understanding_ms": 10.5,
                    },
                },
            },
        }


class _PlannedClarificationGraph(_PlannedGraph):
    async def ainvoke(self, initial_state, config):
        self.followup_questions.append(initial_state["question"])
        return {
            "needs_clarification": True,
            "clarification_question": "请确认要下钻的产品维度字段",
            "clarification_options": ["产品名称", "产品类别"],
            "clarification_source": "semantic_understanding",
            "optimization_metrics": {
                "semantic_understanding_ms": 8.6,
            },
        }


async def _fake_load_field_semantic(self, allow_online_inference=False):
    return self.model_copy(
        update={
            "field_semantic": {"Sold Nm": {"category": "organization"}},
            "field_samples": self.field_samples or _DummyDataModel._field_samples_cache,
        },
    )


@pytest.mark.asyncio
async def test_execute_stream_clarification_event_contains_metrics():
    """澄清事件和完成事件都应带当前累计指标。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=_ClarificationGraph(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="各省份的销售额",
                datasource_name="销售",
            )
        ]

    clarification_event = next(e for e in events if e["type"] == "clarification")
    complete_event = next(e for e in events if e["type"] == "complete")

    clarification_metrics = clarification_event["optimization_metrics"]
    assert clarification_metrics["semantic_understanding_ms"] == 12.5
    assert clarification_metrics["semantic_understanding_clarification_shortcut"] is True
    assert "auth_ms" in clarification_metrics
    assert "data_model_load_ms" in clarification_metrics
    assert "field_semantic_load_ms" in clarification_metrics
    assert "data_preparation_ms" in clarification_metrics
    assert "graph_compile_ms" in clarification_metrics

    complete_metrics = complete_event["optimization_metrics"]
    assert complete_metrics["semantic_understanding_ms"] == 12.5
    assert complete_metrics["workflow_executor_ms"] >= 0
    assert complete_metrics["graph_node_count"] == 1


@pytest.mark.asyncio
async def test_execute_stream_error_event_contains_partial_metrics():
    """内部异常也应携带已完成阶段的指标，便于定位问题。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=_ErrorGraph(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.sanitize_error_message",
        side_effect=lambda message: message,
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="各省份的销售额",
                datasource_name="销售",
            )
        ]

    error_event = next(e for e in events if e["type"] == "error")
    assert error_event["error"] == "graph exploded"

    metrics = error_event["optimization_metrics"]
    assert metrics["workflow_failed"] is True
    assert metrics["workflow_executor_ms"] >= 0
    assert "auth_ms" in metrics
    assert "data_model_load_ms" in metrics
    assert "field_semantic_load_ms" in metrics
    assert "data_preparation_ms" in metrics
    assert "graph_compile_ms" in metrics


@pytest.mark.asyncio
async def test_execute_stream_emits_planner_and_plan_steps():
    """多步 planner 应输出 planner/plan_step/data 等结构化事件。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    planned_graph = _PlannedGraph()

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=planned_graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "地区"}],
                    "rows": [["华东"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "产品"}],
                    "rows": [["产品A"]],
                    "rowCount": 1,
                    "executionTimeMs": 9,
                },
            },
        ]),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="为什么华东区销售额下降了？",
                datasource_name="销售",
            )
        ]

    planner_event = next(e for e in events if e["type"] == "planner")
    plan_step_events = [e for e in events if e["type"] == "plan_step"]
    parse_events = [e for e in events if e["type"] == "parse_result"]
    data_events = [e for e in events if e["type"] == "data"]
    complete_event = next(e for e in events if e["type"] == "complete")

    assert planner_event["planMode"] == "why_analysis"
    assert len(planner_event["steps"]) == 3
    assert planner_event["steps"][0]["usesPrimaryQuery"] is True
    assert planner_event["steps"][-1]["stepType"] == "synthesis"

    assert len(parse_events) == 2
    assert parse_events[0]["planStep"]["index"] == 1
    assert parse_events[1]["planStep"]["index"] == 2

    running_steps = [e for e in plan_step_events if e["status"] == "running"]
    completed_steps = [e for e in plan_step_events if e["status"] == "completed"]
    assert [e["step"]["index"] for e in running_steps] == [1, 2]
    assert [e["step"]["index"] for e in completed_steps] == [1, 2, 3]
    assert "逐步累积的证据链" in completed_steps[-1]["summary"]

    assert len(data_events) == 2
    assert data_events[0]["planStep"]["index"] == 1
    assert data_events[1]["planStep"]["index"] == 2
    assert planned_graph.followup_questions == ["按地区和产品找出贡献最大的异常切片"]
    assert planned_graph.followup_evidence_contexts[0]["primary_question"] == "为什么华东区销售额下降了？"
    assert len(planned_graph.followup_evidence_contexts[0]["step_artifacts"]) == 1
    assert planned_graph.followup_step_intents[0]["step_id"] == "step-2"
    assert planned_graph.followup_step_intents[0]["goal"] == "定位最异常的对象或切片"

    complete_metrics = complete_event["optimization_metrics"]
    assert complete_metrics["planner_multistep_enabled"] is True
    assert complete_metrics["planner_steps_total"] == 3
    assert complete_metrics["planner_query_steps_executed"] == 2
    assert complete_metrics["planner_completed_steps"] == 3
    assert complete_metrics["planner_query_execute_total_ms"] == 39.0


@pytest.mark.asyncio
async def test_execute_stream_can_use_analysis_plan_from_global_understanding():
    """当 parse_result 只带 global_understanding 时，executor 仍应识别多步计划。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    planned_graph = _PlannedGlobalUnderstandingGraph()

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=planned_graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "地区"}],
                    "rows": [["华东"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "产品"}],
                    "rows": [["产品A"]],
                    "rowCount": 1,
                    "executionTimeMs": 9,
                },
            },
        ]),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="为什么华东区销售额下降了？",
                datasource_name="销售",
            )
        ]

    planner_event = next(e for e in events if e["type"] == "planner")
    parse_event = next(e for e in events if e["type"] == "parse_result")
    complete_event = next(e for e in events if e["type"] == "complete")

    assert planner_event["planMode"] == "why_analysis"
    assert "analysis_plan" not in parse_event
    assert parse_event["global_understanding"]["analysis_mode"] == "why_analysis"
    assert parse_event["optimization_metrics"]["global_understanding_llm_used"] is True
    assert parse_event["optimization_metrics"]["global_understanding_fallback_used"] is False
    assert complete_event["optimization_metrics"]["planner_multistep_enabled"] is True


@pytest.mark.asyncio
async def test_execute_stream_cached_why_query_still_uses_planner():
    """复杂 why 问题命中 QueryCache 后，仍应保留 planner 上下文并继续多步执行。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    planned_graph = _CachedPlannedGlobalUnderstandingGraph()

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=planned_graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "地区"}],
                    "rows": [["华东"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "产品"}],
                    "rows": [["产品A"]],
                    "rowCount": 1,
                    "executionTimeMs": 9,
                },
            },
        ]),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="为什么华东区销售额下降了？",
                datasource_name="销售",
            )
        ]

    planner_event = next(e for e in events if e["type"] == "planner")
    parse_event = next(e for e in events if e["type"] == "parse_result")
    complete_event = next(e for e in events if e["type"] == "complete")

    assert planner_event["planMode"] == "why_analysis"
    assert parse_event["query_cache_hit"] is True
    assert parse_event["global_understanding"]["analysis_mode"] == "why_analysis"
    assert complete_event["optimization_metrics"]["planner_multistep_enabled"] is True


@pytest.mark.asyncio
async def test_execute_stream_multistep_runs_replanner_after_synthesis():
    """多步 planner 在 synthesis 完成后，应继续输出 insight/replan/suggestions。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    planned_graph = _PlannedGlobalUnderstandingGraph()

    async def _mock_run_replanner_agent(**kwargs):
        on_thinking = kwargs.get("on_thinking")
        if on_thinking:
            await on_thinking("正在基于累积证据生成后续问题")
        return ReplanDecision(
            should_replan=True,
            reason="仍需继续验证异常产品结构",
            new_question="按产品结构继续分析华东区销售额下降原因",
            suggested_questions=[
                "比较异常产品在不同渠道的占比变化",
                "查看异常产品在重点省份的销售贡献变化",
            ],
            candidate_questions=[
                CandidateQuestion(
                    question="按产品结构继续分析华东区销售额下降原因",
                    question_type="drilldown",
                    priority=1,
                    expected_info_gain=0.88,
                    rationale="先定位异常产品结构",
                    estimated_mode="single_query",
                ),
                CandidateQuestion(
                    question="比较异常产品在不同渠道的占比变化",
                    question_type="comparison",
                    priority=2,
                    expected_info_gain=0.73,
                    rationale="验证渠道结构是否放大异常",
                    estimated_mode="single_query",
                ),
            ],
        )

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=planned_graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "地区"}],
                    "rows": [["华东"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "产品"}],
                    "rows": [["产品A"]],
                    "rowCount": 1,
                    "executionTimeMs": 9,
                },
            },
        ]),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_replanner_agent",
        side_effect=_mock_run_replanner_agent,
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="为什么华东区销售额下降了？",
                datasource_name="销售",
            )
        ]

    insight_event = next(
        e for e in events
        if e["type"] == "insight" and e.get("source") == "planner_synthesis"
    )
    replan_event = next(
        e for e in events
        if e["type"] == "replan" and e.get("source") == "planner_synthesis"
    )
    candidate_questions_event = next(
        e for e in events
        if e["type"] == "candidate_questions" and e.get("source") == "planner_synthesis"
    )
    suggestions_event = next(e for e in events if e["type"] == "suggestions")
    complete_event = next(e for e in events if e["type"] == "complete")

    assert "已完成 2 个查询步骤" in insight_event["summary"]
    assert replan_event["shouldReplan"] is True
    assert replan_event["newQuestion"] == "按产品结构继续分析华东区销售额下降原因"
    assert candidate_questions_event["questions"][0]["question"] == "按产品结构继续分析华东区销售额下降原因"
    assert candidate_questions_event["questions"][0]["priority"] == 1
    assert suggestions_event["questions"] == [
        "按产品结构继续分析华东区销售额下降原因",
        "比较异常产品在不同渠道的占比变化",
        "查看异常产品在重点省份的销售贡献变化",
    ]
    complete_metrics = complete_event["optimization_metrics"]
    assert complete_metrics["planner_replanner_should_replan"] is True
    assert complete_metrics["planner_replanner_suggested_questions_count"] == 2


@pytest.mark.asyncio
async def test_execute_stream_multistep_query_steps_run_actual_insight_rounds():
    """多步 query step 应优先运行真实 InsightAgent，而不是只发 synthetic step summary。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    planned_graph = _PlannedGlobalUnderstandingGraph()

    insight_results = [
        _make_insight_output(summary="现象验证 insight：华东区确实出现下滑"),
        _make_insight_output(summary="异常切片 insight：产品A贡献了主要降幅"),
    ]

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=planned_graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "地区"}],
                    "rows": [["华东"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "产品"}],
                    "rows": [["产品A"]],
                    "rowCount": 1,
                    "executionTimeMs": 9,
                },
            },
        ]),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_insight_agent",
        new=AsyncMock(side_effect=insight_results),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_replanner_agent",
        new=AsyncMock(return_value=ReplanDecision(
            should_replan=False,
            reason="证据链已经足够",
            suggested_questions=[],
            candidate_questions=[],
        )),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="为什么华东区销售额下降了？",
                datasource_name="销售",
            )
        ]

    step_insight_events = [
        e for e in events
        if e["type"] == "insight" and e.get("source") == "plan_step"
    ]
    complete_event = next(e for e in events if e["type"] == "complete")

    assert [e["summary"] for e in step_insight_events] == [
        "现象验证 insight：华东区确实出现下滑",
        "异常切片 insight：产品A贡献了主要降幅",
    ]
    assert complete_event["optimization_metrics"]["planner_step_insight_rounds"] == 2


@pytest.mark.asyncio
async def test_execute_stream_multihop_followups_preserve_cumulative_context():
    """第二个 follow-up step 应继承前两步累积证据与摘要上下文。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    planned_graph = _DeepPlannedGlobalUnderstandingGraph()

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=planned_graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "地区"}],
                    "rows": [["华东"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "省份"}],
                    "rows": [["江苏"], ["浙江"]],
                    "rowCount": 2,
                    "executionTimeMs": 9,
                },
            },
            {
                "success": True,
                "query_execute_ms": 16.0,
                "tableData": {
                    "columns": [{"name": "产品"}],
                    "rows": [["产品A"], ["产品B"]],
                    "rowCount": 2,
                    "executionTimeMs": 8,
                },
            },
        ]),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="为什么华东区销售额下降了？",
                datasource_name="销售",
            )
        ]

    planner_event = next(e for e in events if e["type"] == "planner")
    parse_events = [e for e in events if e["type"] == "parse_result"]
    data_events = [e for e in events if e["type"] == "data"]
    step_insight_events = [
        e for e in events
        if e["type"] == "insight" and e.get("source") == "plan_step"
    ]
    complete_event = next(e for e in events if e["type"] == "complete")

    assert planner_event["planMode"] == "why_analysis"
    assert len(planner_event["steps"]) == 4
    assert [e["planStep"]["index"] for e in parse_events] == [1, 2, 3]
    assert [e["planStep"]["index"] for e in data_events] == [1, 2, 3]
    assert [e["planStep"]["index"] for e in step_insight_events] == [1, 2, 3]
    assert planned_graph.followup_questions == [
        "按省份定位最异常的区域",
        "在已识别的异常省份内按产品定位异常切片",
    ]

    first_context = planned_graph.followup_evidence_contexts[0]
    second_context = planned_graph.followup_evidence_contexts[1]
    assert first_context["primary_question"] == "为什么华东区销售额下降了？"
    assert [artifact["step_id"] for artifact in first_context["step_artifacts"]] == ["step-1"]
    assert "按 地区 进行查询" in first_context["step_artifacts"][0]["table_summary"]
    assert first_context["key_entities"] == ["华东"]
    assert "地区" in first_context["validated_axes"]

    assert [artifact["step_id"] for artifact in second_context["step_artifacts"]] == [
        "step-1",
        "step-2",
    ]
    assert "按 省份 进行查询" in second_context["step_artifacts"][1]["table_summary"]
    assert second_context["key_entities"] == ["华东", "江苏", "浙江"]
    assert second_context["anomalous_entities"] == ["江苏", "浙江"]
    assert "省份" in second_context["validated_axes"]
    assert planned_graph.followup_step_intents[0]["step_id"] == "step-2"
    assert planned_graph.followup_step_intents[1]["step_id"] == "step-3"
    assert planned_graph.followup_step_intents[1]["depends_on"] == ["step-1", "step-2"]

    second_history = planned_graph.followup_histories[1]
    assert second_history[-1]["role"] == "assistant"
    assert "步骤1 验证现象" in second_history[-1]["content"]
    assert "步骤2 按省份定位异常区域" in second_history[-1]["content"]

    complete_metrics = complete_event["optimization_metrics"]
    assert complete_metrics["planner_multistep_enabled"] is True
    assert complete_metrics["planner_steps_total"] == 4
    assert complete_metrics["planner_followup_steps_executed"] == 2
    assert complete_metrics["planner_query_steps_executed"] == 3
    assert complete_metrics["planner_completed_steps"] == 4
    assert complete_metrics["planner_query_execute_total_ms"] == 55.0
    assert complete_metrics["planner_step_insights_emitted"] == 3


@pytest.mark.asyncio
async def test_execute_stream_complex_single_query_does_not_enable_planner():
    """complex_single_query 应保留单查执行，不应误触发多步 planner。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    graph = _ComplexSingleQueryGraph()

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(return_value={
            "success": True,
            "query_execute_ms": 24.0,
            "tableData": {
                "columns": [{"name": "地区"}],
                "rows": [["华东"]],
                "rowCount": 1,
                "executionTimeMs": 11,
            },
        }),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_insight_agent",
        new=AsyncMock(return_value=_make_insight_output()),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_replanner_agent",
        new=AsyncMock(return_value=ReplanDecision(
            should_replan=False,
            reason="当前分析已足够",
            suggested_questions=["看看不同区域利润率变化"],
        )),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="比较今年和去年各地区利润率变化",
                datasource_name="销售",
            )
        ]

    parse_event = next(e for e in events if e["type"] == "parse_result")
    complete_event = next(e for e in events if e["type"] == "complete")

    assert not any(e["type"] == "planner" for e in events)
    assert parse_event["global_understanding"]["analysis_mode"] == "complex_single_query"
    assert parse_event["optimization_metrics"]["global_understanding_llm_used"] is True
    assert parse_event["optimization_metrics"]["global_understanding_fallback_used"] is False
    assert complete_event["optimization_metrics"].get("planner_multistep_enabled") is not True


@pytest.mark.asyncio
async def test_execute_stream_single_query_runs_insight_and_replanner():
    """单次查询成功后，应继续执行 insight/replanner 并输出 suggestions。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    graph = _SingleQueryGraph()

    async def _mock_run_insight_agent(**kwargs):
        on_token = kwargs.get("on_token")
        on_thinking = kwargs.get("on_thinking")
        if on_thinking:
            await on_thinking("正在分析数据特征")
        if on_token:
            await on_token("华东区销售额下降主要集中在渠道分布变化。")
        return _make_insight_output()

    async def _mock_run_replanner_agent(**kwargs):
        on_thinking = kwargs.get("on_thinking")
        if on_thinking:
            await on_thinking("正在评估是否需要继续深挖")
        return ReplanDecision(
            should_replan=True,
            reason="仍需按渠道继续定位下降原因",
            new_question="按渠道继续分析华东区销售额下降原因",
            suggested_questions=[
                "比较各渠道的降幅差异",
                "查看异常渠道中的产品结构变化",
            ],
            candidate_questions=[
                CandidateQuestion(
                    question="按渠道继续分析华东区销售额下降原因",
                    question_type="drilldown",
                    priority=1,
                    expected_info_gain=0.82,
                    rationale="继续锁定异常渠道",
                    estimated_mode="single_query",
                ),
                CandidateQuestion(
                    question="比较各渠道的降幅差异",
                    question_type="comparison",
                    priority=2,
                    expected_info_gain=0.75,
                    rationale="比较渠道间差异",
                    estimated_mode="single_query",
                ),
            ],
        )

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(return_value={
            "success": True,
            "query_execute_ms": 19.0,
            "tableData": {
                "columns": [
                    {"name": "地区"},
                    {"name": "销售额", "dataType": "REAL", "isMeasure": True},
                ],
                "rows": [{"地区": "华东", "销售额": 120.5}],
                "rowCount": 1,
                "executionTimeMs": 9,
            },
        }),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_insight_agent",
        side_effect=_mock_run_insight_agent,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_replanner_agent",
        side_effect=_mock_run_replanner_agent,
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="查看各地区销售额",
                datasource_name="销售",
            )
        ]

    suggestions_event = next(e for e in events if e["type"] == "suggestions")
    candidate_questions_event = next(e for e in events if e["type"] == "candidate_questions")
    insight_event = next(e for e in events if e["type"] == "insight")
    replan_event = next(e for e in events if e["type"] == "replan")
    complete_event = next(e for e in events if e["type"] == "complete")
    token_events = [e for e in events if e["type"] == "token"]
    thinking_events = [e for e in events if e["type"] == "thinking"]

    assert any("渠道分布变化" in e["content"] for e in token_events)
    assert insight_event["source"] == "single_query"
    assert "渠道分布变化" in insight_event["summary"]
    assert replan_event["shouldReplan"] is True
    assert replan_event["reason"] == "仍需按渠道继续定位下降原因"
    assert candidate_questions_event["questions"][0]["question"] == "按渠道继续分析华东区销售额下降原因"
    assert suggestions_event["questions"] == [
        "按渠道继续分析华东区销售额下降原因",
        "比较各渠道的降幅差异",
        "查看异常渠道中的产品结构变化",
    ]
    assert ("generating", "running") in {
        (e["stage"], e["status"]) for e in thinking_events
    }
    assert ("replanning", "running") in {
        (e["stage"], e["status"]) for e in thinking_events
    }
    complete_metrics = complete_event["optimization_metrics"]
    assert complete_metrics["insight_findings_count"] == 1
    assert complete_metrics["replanner_should_replan"] is True


@pytest.mark.asyncio
async def test_execute_stream_auto_continue_runs_followup_round():
    """auto_continue 模式下，executor 应自动执行 replanner 选中的下一轮问题。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    graph = _QuestionAwareSingleQueryGraph()

    async def _mock_run_insight_agent(**kwargs):
        semantic_output_dict = kwargs["semantic_output_dict"]
        question = semantic_output_dict.get("restated_question", "")
        if "渠道" in question:
            return _make_insight_output(summary="渠道维度显示直营网点下滑最明显")
        return _make_insight_output(summary="地区维度显示华东区下滑最明显")

    replanner_results = [
        ReplanDecision(
            should_replan=True,
            reason="需要继续按渠道定位华东区下降原因",
            new_question="按渠道继续分析华东区销售额下降原因",
            suggested_questions=["比较各渠道的降幅差异"],
            candidate_questions=[
                CandidateQuestion(
                    question="按渠道继续分析华东区销售额下降原因",
                    question_type="drilldown",
                    priority=1,
                    expected_info_gain=0.84,
                    rationale="继续定位异常渠道",
                    estimated_mode="single_query",
                )
            ],
        ),
        ReplanDecision(
            should_replan=False,
            reason="渠道层面的异常已经足够解释当前问题",
            suggested_questions=[],
            candidate_questions=[],
        ),
    ]

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 19.0,
                "tableData": {
                    "columns": [{"name": "地区"}],
                    "rows": [["华东"]],
                    "rowCount": 1,
                    "executionTimeMs": 9,
                },
            },
            {
                "success": True,
                "query_execute_ms": 17.0,
                "tableData": {
                    "columns": [{"name": "渠道"}],
                    "rows": [["直营网点"]],
                    "rowCount": 1,
                    "executionTimeMs": 8,
                },
            },
        ]),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_insight_agent",
        side_effect=_mock_run_insight_agent,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_replanner_agent",
        new=AsyncMock(side_effect=replanner_results),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="查看各地区销售额",
                datasource_name="销售",
                replan_mode="auto_continue",
            )
        ]

    parse_events = [e for e in events if e["type"] == "parse_result"]
    replan_events = [e for e in events if e["type"] == "replan"]
    complete_event = next(e for e in events if e["type"] == "complete")

    assert graph.questions == [
        "查看各地区销售额",
        "按渠道继续分析华东区销售额下降原因",
    ]
    assert len(parse_events) == 2
    assert replan_events[0]["action"] == "auto_continue"
    assert replan_events[0]["selectedQuestion"] == "按渠道继续分析华东区销售额下降原因"
    assert complete_event["optimization_metrics"]["auto_continue_triggered"] is True


@pytest.mark.asyncio
async def test_execute_stream_selected_candidate_question_overrides_current_question():
    """user_select 模式传入 selected_candidate_question 时，应直接执行被选中的问题。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    graph = _QuestionAwareSingleQueryGraph()

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(return_value={
            "success": True,
            "query_execute_ms": 16.0,
            "tableData": {
                "columns": [{"name": "渠道"}],
                "rows": [["直营网点"]],
                "rowCount": 1,
                "executionTimeMs": 8,
            },
        }),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_insight_agent",
        new=AsyncMock(return_value=_make_insight_output(summary="渠道维度显示直营网点下滑最明显")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._invoke_replanner_agent",
        new=AsyncMock(return_value=ReplanDecision(
            should_replan=False,
            reason="当前渠道分析已足够",
            suggested_questions=[],
            candidate_questions=[],
        )),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="原始问题不会被执行",
                datasource_name="销售",
                replan_mode="user_select",
                selected_candidate_question="按渠道继续分析华东区销售额下降原因",
            )
        ]

    parse_event = next(e for e in events if e["type"] == "parse_result")

    assert graph.questions == ["按渠道继续分析华东区销售额下降原因"]
    assert parse_event["summary"]["restated_question"] == "按渠道继续分析华东区销售额下降原因"


@pytest.mark.asyncio
async def test_execute_stream_followup_plan_step_can_clarify():
    """follow-up step 澄清时，应同步输出 plan_step 和 clarification 事件。"""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    planned_graph = _PlannedClarificationGraph()

    with patch(
        "analytics_assistant.src.orchestration.workflow.executor.get_tableau_auth_async",
        new=AsyncMock(return_value=SimpleNamespace(api_key="k", site="s")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.VizQLClient",
        _DummyVizQLClient,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauDataLoader",
        return_value=loader_instance,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.TableauAdapter",
        return_value=MagicMock(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.compile_semantic_parser_graph",
        return_value=planned_graph,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor._execute_semantic_query",
        new=AsyncMock(return_value={
            "success": True,
            "query_execute_ms": 21.0,
            "tableData": {
                "columns": [{"name": "地区"}],
                "rows": [["华东"]],
                "rowCount": 1,
                "executionTimeMs": 10,
            },
        }),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="为什么华东区销售额下降了？",
                datasource_name="销售",
            )
        ]

    clarification_event = next(e for e in events if e["type"] == "clarification")
    plan_step_clarification = next(
        e for e in events
        if e["type"] == "plan_step" and e["status"] == "clarification"
    )
    complete_event = next(e for e in events if e["type"] == "complete")

    assert clarification_event["question"] == "请确认要下钻的产品维度字段"
    assert clarification_event["options"] == ["产品名称", "产品类别"]
    assert plan_step_clarification["step"]["index"] == 2
    assert plan_step_clarification["question"] == clarification_event["question"]

    complete_metrics = complete_event["optimization_metrics"]
    assert complete_metrics["planner_multistep_enabled"] is True
    assert complete_metrics["planner_blocked_step"] == 2
