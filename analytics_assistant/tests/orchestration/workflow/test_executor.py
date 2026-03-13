# -*- coding: utf-8 -*-
"""
WorkflowExecutor observability tests.
Focus on interrupt/error branches and accumulated metrics.
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
from analytics_assistant.src.orchestration.workflow import executor as executor_module
from analytics_assistant.src.orchestration.workflow.executor import WorkflowExecutor
from analytics_assistant.src.orchestration.workflow.checkpoint import (
    reset_workflow_checkpointers,
)
from analytics_assistant.src.platform.tableau.client import TableauDatasourceAmbiguityError


class _DummyVizQLClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _DummyDataModel:
    datasource_id = "ds-test"
    fields = []
    _field_samples_cache = {"Sold Nm": {"sample_values": ["Acme Foods Ltd."]}}
    _field_semantic_cache = {"Sold Nm": {"category": "organization"}}


class _HighRiskDataModel:
    datasource_id = "ds-high-risk"
    fields = []
    _field_samples_cache = {
        "Region": {
            "sample_values": ["East", "West", "North", "South"],
            "unique_count": 8000,
        }
    }
    _field_semantic_cache = {"Region": {"category": "geography"}}


@pytest.fixture(autouse=True)
def reset_checkpointers() -> None:
    """每个测试前后重置 checkpoint，避免 aiosqlite 线程残留。"""
    reset_workflow_checkpointers(clear_persisted_state=True)
    yield
    reset_workflow_checkpointers(clear_persisted_state=True)


class _ClarificationGraph:
    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "__interrupt__": (
                SimpleNamespace(
                    value={
                        "interrupt_type": "missing_slot",
                        "message": "Choose dimension field",
                        "source": "semantic_understanding",
                        "slot_name": "dimension",
                        "options": ["Seller Name (Sold Nm)"],
                        "resume_strategy": "langgraph_native",
                        "optimization_metrics": {
                            "semantic_understanding_ms": 12.5,
                            "semantic_understanding_clarification_shortcut": True,
                        },
                    },
                    ns=["semantic_understanding:test"],
                ),
            ),
        }


class _ValueConfirmGraph:
    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "__interrupt__": (
                SimpleNamespace(
                    value={
                        "interrupt_type": "value_confirm",
                        "message": "Select correct region value",
                        "source": "filter_validator",
                        "field": "Region",
                        "requested_value": "Eest",
                        "candidates": ["East", "West"],
                        "resume_strategy": "langgraph_native",
                        "optimization_metrics": {
                            "filter_validation_ms": 7.2,
                        },
                    },
                    ns=["filter_validator:test"],
                ),
            ),
        }


class _NativeMissingSlotGraph:
    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "__interrupt__": (
                SimpleNamespace(
                    value={
                        "interrupt_type": "missing_slot",
                        "message": "Select timeframe",
                        "source": "semantic_understanding",
                        "slot_name": "timeframe",
                        "options": ["last_7_days", "last_30_days"],
                        "resume_strategy": "langgraph_native",
                        "optimization_metrics": {
                            "semantic_understanding_ms": 11.3,
                        },
                    },
                    ns=["semantic_understanding:test"],
                ),
            ),
        }


class _MalformedClarificationGraph:
    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "semantic_understanding": {
                "needs_clarification": True,
                "clarification_question": "Choose dimension field",
                "clarification_options": ["Seller Name (Sold Nm)"],
                "clarification_source": "semantic_understanding",
            },
        }


def test_load_event_queue_maxsize_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        executor_module,
        "get_config",
        lambda: {"api": {"streaming": {"event_queue_maxsize": 64}}},
    )

    executor = WorkflowExecutor("admin", request_id="req-queue-size")

    assert executor._event_queue_maxsize == 64


def test_load_event_queue_maxsize_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        executor_module,
        "get_config",
        lambda: {"api": {"streaming": {"event_queue_maxsize": "invalid"}}},
    )

    executor = WorkflowExecutor("admin", request_id="req-queue-default")

    assert executor._event_queue_maxsize == executor_module._DEFAULT_EVENT_QUEUE_SIZE


class _ErrorGraph:
    async def astream(self, initial_state, config, stream_mode="updates"):
        if False:
            yield {}
        raise RuntimeError("graph exploded")


def _make_semantic_output(
    query_id: str,
    *,
    restated_question: str,
    measure: str = "Sales",
    dimension: str = "Region",
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
    summary: str = "The sales decline is mainly concentrated in channel mix changes.",
) -> InsightOutput:
    return InsightOutput(
        findings=[
            Finding(
                finding_type=FindingType.ANOMALY,
                analysis_level=AnalysisLevel.DIAGNOSTIC,
                description=summary,
                supporting_data={"segment": "East Region"},
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
        "goal": "Explain why sales declined in the East region",
        "execution_strategy": "sequential",
        "reasoning_focus": [
            "Verify the observed decline",
            "Locate the abnormal slice",
            "Summarize the root cause",
        ],
        "sub_questions": [
            {
                "step_id": "step-1",
                "title": "Verify the decline",
                "goal": "Confirm that the decline described by the user is real",
                "question": "Why did sales decline in the East region?",
                "purpose": "Verify the decline",
                "step_type": "query",
                "uses_primary_query": True,
                "depends_on": [],
                "semantic_focus": ["sales", "east region", "year-over-year"],
                "expected_output": "Confirm whether the decline exists and quantify its direction and magnitude",
                "candidate_axes": [],
                "targets_anomaly": False,
                "clarification_if_missing": ["comparison baseline", "time range"],
            },
            {
                "step_id": "step-2",
                "title": "Locate the abnormal slice",
                "goal": "Find the object or slice with the strongest anomaly",
                "question": "Break down by region and product to find the slice contributing most to the anomaly",
                "purpose": "Locate the abnormal slice",
                "step_type": "query",
                "uses_primary_query": False,
                "depends_on": ["step-1"],
                "semantic_focus": ["anomaly localization", "product", "region"],
                "expected_output": "Identify the anomalous object set or key slice",
                "candidate_axes": ["region", "product"],
                "targets_anomaly": True,
                "clarification_if_missing": [],
            },
            {
                "step_id": "step-3",
                "title": "Summarize the root cause",
                "goal": "Aggregate the evidence chain and summarize the root cause",
                "question": "Summarize the cause based on the first two steps",
                "purpose": "Summarize the root cause",
                "step_type": "synthesis",
                "uses_primary_query": False,
                "depends_on": ["step-1", "step-2"],
                "semantic_focus": ["evidence aggregation", "cause synthesis"],
                "expected_output": "Produce a conclusion, evidence summary, and open questions",
                "candidate_axes": [],
                "targets_anomaly": False,
                "clarification_if_missing": [],
            },
        ],
        "retrieval_focus_terms": ["sales", "east region"],
        "planner_confidence": 0.93,
    }


def _make_deep_analysis_plan_dict() -> dict:
    return {
        "plan_mode": "why_analysis",
        "needs_planning": True,
        "requires_llm_reasoning": True,
        "goal": "Explain why sales declined in the East region",
        "execution_strategy": "sequential",
        "reasoning_focus": [
            "Verify the observed decline",
            "Narrow the abnormal region first",
            "Continue drilling down by product",
            "Summarize the evidence chain",
        ],
        "sub_questions": [
            {
                "step_id": "step-1",
                "title": "Verify the decline",
                "goal": "Confirm that the decline described by the user is real",
                "question": "Why did sales decline in the East region?",
                "purpose": "Verify the decline",
                "step_type": "query",
                "uses_primary_query": True,
                "depends_on": [],
                "semantic_focus": ["sales", "east region", "year-over-year"],
                "expected_output": "Confirm whether the decline exists and quantify its direction and magnitude",
                "candidate_axes": [],
                "targets_anomaly": False,
                "clarification_if_missing": ["comparison baseline", "time range"],
            },
            {
                "step_id": "step-2",
                "title": "Locate the abnormal area by province",
                "goal": "Narrow down the province or area with the strongest anomaly",
                "question": "Break down by province to locate the most abnormal area",
                "purpose": "Narrow the anomaly scope",
                "step_type": "query",
                "uses_primary_query": False,
                "depends_on": ["step-1"],
                "semantic_focus": ["anomaly localization", "province"],
                "expected_output": "Identify the anomalous province that needs further drill-down",
                "candidate_axes": ["province"],
                "targets_anomaly": True,
                "clarification_if_missing": [],
            },
            {
                "step_id": "step-3",
                "title": "Continue drilling down by product",
                "goal": "Within the abnormal province, find the product slice with the largest contribution",
                "question": "Within the identified abnormal province, locate the abnormal slice by product",
                "purpose": "Continue drilling down to find the cause",
                "step_type": "query",
                "uses_primary_query": False,
                "depends_on": ["step-1", "step-2"],
                "semantic_focus": ["anomaly localization", "product", "drill-down"],
                "expected_output": "Identify the anomalous product or key slice",
                "candidate_axes": ["product"],
                "targets_anomaly": True,
                "clarification_if_missing": [],
            },
            {
                "step_id": "step-4",
                "title": "Summarize the root cause",
                "goal": "Aggregate the evidence chain and summarize the root cause",
                "question": "Summarize the cause based on the first three steps",
                "purpose": "Summarize the root cause",
                "step_type": "synthesis",
                "uses_primary_query": False,
                "depends_on": ["step-1", "step-2", "step-3"],
                "semantic_focus": ["evidence aggregation", "cause synthesis"],
                "expected_output": "Produce a conclusion, evidence summary, and open questions",
                "candidate_axes": [],
                "targets_anomaly": False,
                "clarification_if_missing": [],
            },
        ],
        "retrieval_focus_terms": ["sales", "east region", "province", "product"],
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
        "decomposition_reason": "This why-question requires an evidence chain and stepwise validation.",
        "needs_clarification": False,
        "clarification_question": None,
        "clarification_options": [],
        "primary_restated_question": "Why did sales decline in the East region?",
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
        "decomposition_reason": "This why-question needs anomaly localization before deeper drill-down.",
        "needs_clarification": False,
        "clarification_question": None,
        "clarification_options": [],
        "primary_restated_question": "Why did sales decline in the East region?",
        "risk_flags": [],
        "llm_confidence": 0.91,
        "analysis_plan": _make_deep_analysis_plan_dict(),
    }


def _make_complex_single_query_global_understanding_dict() -> dict:
    return {
        "analysis_mode": "complex_single_query",
        "single_query_feasible": True,
        "single_query_blockers": [],
        "decomposition_reason": "Even with time comparison, a single query is still sufficient.",
        "needs_clarification": False,
        "clarification_question": None,
        "clarification_options": [],
        "primary_restated_question": "Compare profit margin changes by region this year versus last year",
        "risk_flags": [],
        "llm_confidence": 0.88,
        "analysis_plan": {
            "plan_mode": "direct_query",
            "single_query_feasible": True,
            "needs_planning": False,
            "requires_llm_reasoning": True,
            "decomposition_reason": "Even with time comparison, a single query is still sufficient.",
            "goal": "Directly parse the complex single-query question",
            "execution_strategy": "single_query",
            "reasoning_focus": ["Keep the query single-pass while preserving complex reasoning"],
            "sub_questions": [],
            "risk_flags": [],
            "needs_clarification": False,
            "clarification_question": None,
            "clarification_options": [],
            "retrieval_focus_terms": ["Profit Margin", "Region"],
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
                        restated_question="Why sales declined in the East region",
                        measure="Sales",
                        dimension="Region",
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
                    measure="Sales",
                    dimension="??",
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
                        restated_question="Why sales declined in the East region",
                        measure="Sales",
                        dimension="Region",
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
                        restated_question="Why sales declined in the East region",
                        measure="Sales",
                        dimension="Region",
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
                        restated_question="Why sales declined in the East region",
                        measure="Sales",
                        dimension="Region",
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
                        measure="Sales",
                        dimension="Province",
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
                    measure="Sales",
                    dimension="??",
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
                        restated_question="Compare profit margin changes by region this year versus last year",
                        measure="Profit Margin",
                        dimension="Region",
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
                        restated_question="Show sales by region",
                        measure="Sales",
                        dimension="Region",
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
        if "channel" in question.lower():
            query_id = "q-followup"
            dimension = "Channel"
        else:
            query_id = "q-single"
            dimension = "Region"

        yield {
            "feedback_learner": {
                "parse_result": {
                    "success": True,
                    "query_id": query_id,
                    "semantic_output": _make_semantic_output(
                        query_id,
                        restated_question=question,
                        measure="Sales",
                        dimension=dimension,
                    ),
                    "query": {"query": query_id},
                    "optimization_metrics": {
                        "semantic_understanding_ms": 10.5,
                    },
                },
            },
        }


class _HighRiskSingleQueryGraph:
    async def astream(self, initial_state, config, stream_mode="updates"):
        yield {
            "feedback_learner": {
                "parse_result": {
                    "success": True,
                    "query_id": "q-high-risk",
                    "semantic_output": _make_semantic_output(
                        "q-high-risk",
                        restated_question="show all sales by region",
                        measure="Sales",
                        dimension="Region",
                    ),
                    "query": {"query": "high-risk"},
                    "optimization_metrics": {
                        "semantic_understanding_ms": 9.8,
                    },
                },
            },
        }


class _PlannedClarificationGraph(_PlannedGraph):
    async def ainvoke(self, initial_state, config):
        self.followup_questions.append(initial_state["question"])
        return {
            "__interrupt__": (
                SimpleNamespace(
                    value={
                        "interrupt_type": "missing_slot",
                        "message": "Confirm drilldown dimension",
                        "source": "semantic_understanding",
                        "slot_name": "dimension",
                        "options": ["product_name", "product_category"],
                        "resume_strategy": "langgraph_native",
                        "optimization_metrics": {
                            "semantic_understanding_ms": 8.6,
                        },
                    },
                    ns=["semantic_understanding:plan-step"],
                ),
            ),
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
    """native interrupt 事件应携带累计指标。"""
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
                question="Sales by province",
                datasource_name="sales",
            )
        ]

    clarification_event = next(e for e in events if e["type"] == "interrupt")
    assert clarification_event["interrupt_type"] == "missing_slot"
    assert clarification_event["payload"]["slot_name"] == "dimension"
    assert clarification_event["payload"]["options"] == ["Seller Name (Sold Nm)"]
    assert clarification_event["payload"]["resume_strategy"] == "langgraph_native"

    clarification_metrics = clarification_event["payload"]["optimization_metrics"]
    assert clarification_metrics["semantic_understanding_ms"] == 12.5
    assert clarification_metrics["semantic_understanding_clarification_shortcut"] is True
    assert "auth_ms" in clarification_metrics
    assert "data_model_load_ms" in clarification_metrics
    assert "field_semantic_load_ms" in clarification_metrics
    assert "data_preparation_ms" in clarification_metrics
    assert "graph_compile_ms" in clarification_metrics
    assert clarification_metrics["workflow_executor_ms"] >= 0
    assert clarification_metrics["workflow_interrupted"] is True
    assert all(e["type"] != "complete" for e in events)


@pytest.mark.asyncio
async def test_execute_stream_emits_value_confirm_interrupt():
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
        return_value=_ValueConfirmGraph(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ):
        executor = WorkflowExecutor("admin", request_id="req-value-confirm")
        events = [
            event
            async for event in executor.execute_stream(
                question="Query region sales",
                datasource_name="sales",
            )
        ]

    interrupt_event = next(e for e in events if e["type"] == "interrupt")
    assert interrupt_event["interrupt_type"] == "value_confirm"
    assert interrupt_event["payload"]["field"] == "Region"
    assert interrupt_event["payload"]["requested_value"] == "Eest"
    assert interrupt_event["payload"]["candidates"] == ["East", "West"]
    assert interrupt_event["payload"]["resume_strategy"] == "langgraph_native"
    assert interrupt_event["payload"]["optimization_metrics"]["filter_validation_ms"] == 7.2
    assert all(e["type"] != "complete" for e in events)


@pytest.mark.asyncio
async def test_execute_stream_emits_native_missing_slot_interrupt():
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
        return_value=_NativeMissingSlotGraph(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ):
        executor = WorkflowExecutor("admin", request_id="req-native-missing-slot")
        events = [
            event
            async for event in executor.execute_stream(
                question="show sales by region",
                datasource_name="sales",
            )
        ]

    interrupt_event = next(e for e in events if e["type"] == "interrupt")
    assert interrupt_event["interrupt_type"] == "missing_slot"
    assert interrupt_event["payload"]["slot_name"] == "timeframe"
    assert interrupt_event["payload"]["options"] == ["last_7_days", "last_30_days"]
    assert interrupt_event["payload"]["resume_strategy"] == "langgraph_native"
    assert interrupt_event["payload"]["optimization_metrics"]["semantic_understanding_ms"] == 11.3
    assert interrupt_event["payload"]["optimization_metrics"]["workflow_interrupted"] is True
    assert all(e["type"] != "complete" for e in events)


@pytest.mark.asyncio
async def test_execute_stream_interrupts_before_high_risk_query_execution():
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_HighRiskDataModel())

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
        return_value=_HighRiskSingleQueryGraph(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(return_value={"success": True, "query_execute_ms": 12.0}),
    ) as mock_execute_query:
        executor = WorkflowExecutor("admin", request_id="req-high-risk")
        events = [
            event
            async for event in executor.execute_stream(
                question="show all sales by region",
                datasource_name="sales",
            )
        ]

    interrupt_event = next(e for e in events if e["type"] == "interrupt")
    assert interrupt_event["interrupt_type"] == "high_risk_query_confirm"
    assert interrupt_event["payload"]["risk_level"] == "high"
    assert interrupt_event["payload"]["estimated_rows"] == 8000
    assert interrupt_event["payload"]["risk_signature"]
    assert "未检测到收敛筛选条件" in interrupt_event["payload"]["reasons"]
    assert "维度基数较高，预计结果规模较大" in interrupt_event["payload"]["reasons"]
    assert interrupt_event["payload"]["optimization_metrics"]["workflow_interrupted"] is True
    assert all(e["type"] != "complete" for e in events)
    assert mock_execute_query.await_count == 0


@pytest.mark.asyncio
async def test_execute_stream_rejects_legacy_clarification_output():
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
        return_value=_MalformedClarificationGraph(),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.schedule_datasource_artifact_preparation",
        return_value=False,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.WorkflowContext.load_field_semantic",
        new=_fake_load_field_semantic,
    ):
        executor = WorkflowExecutor("admin", request_id="req-malformed-interrupt")
        events = [
            event
            async for event in executor.execute_stream(
                question="各省份的销售额",
                datasource_name="销售",
            )
        ]

    error_event = next(e for e in events if e["type"] == "error")
    assert "legacy clarification output" in error_event["error"]


@pytest.mark.asyncio
async def test_execute_stream_error_event_contains_partial_metrics():
    """Internal errors should still carry completed-stage metrics for diagnosis."""
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
                question="Sales by province",
                datasource_name="sales",
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
async def test_execute_stream_emits_datasource_disambiguation_interrupt():
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(
        side_effect=TableauDatasourceAmbiguityError(
            "Datasource name is not unique; provide project_name or datasource_luid",
            datasource_name="Revenue",
            choices=[
                {"datasource_luid": "ds_001", "name": "Revenue", "project": "Sales"},
                {"datasource_luid": "ds_002", "name": "Revenue", "project": "Ops"},
            ],
        )
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
    ):
        executor = WorkflowExecutor("admin", request_id="req-ds-ambiguity")
        events = [
            event
            async for event in executor.execute_stream(
                question="Regional sales",
                datasource_name="Revenue",
            )
        ]

    interrupt_event = next(e for e in events if e["type"] == "interrupt")
    assert interrupt_event["interrupt_type"] == "datasource_disambiguation"
    assert interrupt_event["payload"]["choices"] == [
        {"datasource_luid": "ds_001", "name": "Revenue", "project": "Sales"},
        {"datasource_luid": "ds_002", "name": "Revenue", "project": "Ops"},
    ]
    assert interrupt_event["payload"]["datasource_name"] == "Revenue"
    assert interrupt_event["payload"]["optimization_metrics"][
        "datasource_disambiguation_required"
    ] is True
    assert all(event["type"] != "complete" for event in events)


@pytest.mark.asyncio
async def test_execute_stream_emits_planner_and_plan_steps():
    """The multi-step planner should emit structured planner/plan_step/data events."""
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "Region"}],
                    "rows": [["East"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "??"}],
                    "rows": [["??A"]],
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
                question="Why did sales decline in the East region?",
                datasource_name="sales",
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
    assert completed_steps[-1]["step"]["stepType"] == "synthesis"
    assert completed_steps[-1]["summary"]
    assert planner_event["steps"][1]["targetsAnomaly"] is True

    assert len(data_events) == 2
    assert data_events[0]["planStep"]["index"] == 1
    assert data_events[1]["planStep"]["index"] == 2
    assert len(planned_graph.followup_questions) == 1
    assert len(planned_graph.followup_evidence_contexts[0]["step_artifacts"]) == 1
    assert planned_graph.followup_step_intents[0]["step_id"] == "step-2"
    assert planned_graph.followup_step_intents[0]["targets_anomaly"] is True

    complete_metrics = complete_event["optimization_metrics"]
    assert complete_metrics["planner_multistep_enabled"] is True
    assert complete_metrics["planner_steps_total"] == 3
    assert complete_metrics["planner_query_steps_executed"] == 2
    assert complete_metrics["planner_completed_steps"] == 3
    assert complete_metrics["planner_query_execute_total_ms"] == 39.0


@pytest.mark.asyncio
async def test_execute_stream_can_use_analysis_plan_from_global_understanding():
    """Executor should still detect a multi-step plan when it only receives global_understanding."""
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "Region"}],
                    "rows": [["East"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "Product"}],
                    "rows": [["Product A"]],
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
                question="Why did sales decline in the East region?",
                datasource_name="sales",
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
    """A cached complex why-question should still preserve planner context and continue multi-step execution."""
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "Region"}],
                    "rows": [["East"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "??"}],
                    "rows": [["??A"]],
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
                question="Why did sales decline in the East region?",
                datasource_name="sales",
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
    """After synthesis, the multi-step planner should continue emitting insight/replan/suggestions."""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    planned_graph = _PlannedGlobalUnderstandingGraph()

    async def _mock_run_replanner_agent(**kwargs):
        on_thinking = kwargs.get("on_thinking")
        if on_thinking:
            await on_thinking("Generating follow-up questions from accumulated evidence")
        return ReplanDecision(
            should_replan=True,
            reason="Product structure still needs further validation",
            new_question="Continue analyzing the East-region sales decline by product structure",
            suggested_questions=[
                "Compare anomalous-product share changes across channels",
                "Inspect anomalous-product contribution changes in key provinces",
            ],
            candidate_questions=[
                CandidateQuestion(
                    question="Continue analyzing the East-region sales decline by product structure",
                    question_type="drilldown",
                    priority=1,
                    expected_info_gain=0.88,
                    rationale="?????????",
                    estimated_mode="single_query",
                ),
                CandidateQuestion(
                    question="Compare anomalous-product share changes across channels",
                    question_type="comparison",
                    priority=2,
                    expected_info_gain=0.73,
                    rationale="Validate whether channel structure amplifies the anomaly",
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "Region"}],
                    "rows": [["East"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "??"}],
                    "rows": [["??A"]],
                    "rowCount": 1,
                    "executionTimeMs": 9,
                },
            },
        ]),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_replanner_agent",
        side_effect=_mock_run_replanner_agent,
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="Why did sales decline in the East region?",
                datasource_name="sales",
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
    complete_event = next(e for e in events if e["type"] == "complete")
    assert insight_event["summary"]
    assert replan_event["shouldReplan"] is True
    assert replan_event["newQuestion"]
    assert replan_event["candidateQuestions"][0]["question"] == replan_event["newQuestion"]
    assert replan_event["candidateQuestions"][0]["priority"] == 1
    assert replan_event["questions"][0] == replan_event["newQuestion"]
    assert len(replan_event["questions"]) >= len(replan_event["candidateQuestions"])
    complete_metrics = complete_event["optimization_metrics"]
    assert complete_metrics["planner_replanner_should_replan"] is True
    assert complete_metrics["planner_replanner_suggested_questions_count"] == 2


@pytest.mark.asyncio
async def test_execute_stream_multistep_query_steps_run_actual_insight_rounds():
    """A multi-step query step should prefer the real InsightAgent instead of only a synthetic step summary."""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    planned_graph = _PlannedGlobalUnderstandingGraph()

    insight_results = [
        _make_insight_output(summary="Verification insight: the East region does show a decline"),
        _make_insight_output(summary="Anomalous-slice insight: Product A drove most of the decline"),
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "Region"}],
                    "rows": [["East"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "??"}],
                    "rows": [["??A"]],
                    "rowCount": 1,
                    "executionTimeMs": 9,
                },
            },
        ]),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_insight_agent",
        new=AsyncMock(side_effect=insight_results),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_replanner_agent",
        new=AsyncMock(return_value=ReplanDecision(
            should_replan=False,
            reason="The evidence chain is already sufficient",
            suggested_questions=[],
            candidate_questions=[],
        )),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="Why did sales decline in the East region?",
                datasource_name="sales",
            )
        ]

    step_insight_events = [
        e for e in events
        if e["type"] == "insight" and e.get("source") == "plan_step"
    ]
    complete_event = next(e for e in events if e["type"] == "complete")

    assert [e["summary"] for e in step_insight_events] == [
        "Verification insight: the East region does show a decline",
        "Anomalous-slice insight: Product A drove most of the decline",
    ]
    assert complete_event["optimization_metrics"]["planner_step_insight_rounds"] == 2


@pytest.mark.asyncio
async def test_execute_stream_multihop_followups_preserve_cumulative_context():
    """The second follow-up step should inherit accumulated evidence and summary context from prior steps."""
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 21.0,
                "tableData": {
                    "columns": [{"name": "Region"}],
                    "rows": [["East"]],
                    "rowCount": 1,
                    "executionTimeMs": 10,
                },
            },
            {
                "success": True,
                "query_execute_ms": 18.0,
                "tableData": {
                    "columns": [{"name": "Province"}],
                    "rows": [["Jiangsu"], ["Zhejiang"]],
                    "rowCount": 2,
                    "executionTimeMs": 9,
                },
            },
            {
                "success": True,
                "query_execute_ms": 16.0,
                "tableData": {
                    "columns": [{"name": "??"}],
                    "rows": [["??A"], ["??B"]],
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
                question="Why did sales decline in the East region?",
                datasource_name="sales",
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
        "Break down by province to locate the most abnormal area",
        "Within the identified abnormal province, locate the abnormal slice by product",
    ]

    first_context = planned_graph.followup_evidence_contexts[0]
    second_context = planned_graph.followup_evidence_contexts[1]
    assert first_context["primary_question"]
    assert [artifact["step_id"] for artifact in first_context["step_artifacts"]] == ["step-1"]
    assert first_context["step_artifacts"][0]["table_summary"]
    assert first_context["step_artifacts"][0]["targets_anomaly"] is False
    assert len(first_context["key_entities"]) == 1
    assert first_context["validated_axes"]

    assert [artifact["step_id"] for artifact in second_context["step_artifacts"]] == [
        "step-1",
        "step-2",
    ]
    assert second_context["step_artifacts"][1]["table_summary"]
    assert second_context["step_artifacts"][1]["targets_anomaly"] is True
    assert len(second_context["key_entities"]) >= 3
    assert len(second_context["anomalous_entities"]) == 2
    assert set(second_context["anomalous_entities"]).issubset(set(second_context["key_entities"]))
    assert second_context["validated_axes"]
    assert planned_graph.followup_step_intents[0]["step_id"] == "step-2"
    assert planned_graph.followup_step_intents[1]["step_id"] == "step-3"
    assert planned_graph.followup_step_intents[1]["depends_on"] == ["step-1", "step-2"]

    second_history = planned_graph.followup_histories[1]
    assert second_history[-1]["role"] == "assistant"
    assert second_history[-1]["content"]
    complete_metrics = complete_event["optimization_metrics"]
    assert complete_metrics["planner_query_steps_executed"] == 3
    assert complete_metrics["planner_completed_steps"] == 4
    assert complete_metrics["planner_query_execute_total_ms"] == 55.0
    assert complete_metrics["planner_step_insights_emitted"] == 3


@pytest.mark.asyncio
async def test_execute_stream_complex_single_query_does_not_enable_planner():
    """complex_single_query should stay on the single-query path and must not trigger the multi-step planner."""
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(return_value={
            "success": True,
            "query_execute_ms": 24.0,
            "tableData": {
                "columns": [{"name": "Region"}],
                "rows": [["East"]],
                "rowCount": 1,
                "executionTimeMs": 11,
            },
        }),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_insight_agent",
        new=AsyncMock(return_value=_make_insight_output()),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_replanner_agent",
        new=AsyncMock(return_value=ReplanDecision(
            should_replan=False,
            reason="The current analysis is already sufficient",
            suggested_questions=["Compare profit margin changes across regions"],
        )),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="Compare profit margin changes by region this year versus last year",
                datasource_name="sales",
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
    """After a successful single query, insight/replanner should continue and emit suggestions."""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    graph = _SingleQueryGraph()

    async def _mock_run_insight_agent(**kwargs):
        on_token = kwargs.get("on_token")
        on_thinking = kwargs.get("on_thinking")
        if on_thinking:
            await on_thinking("????????")
        if on_token:
            await on_token("The East-region sales decline is mainly concentrated in channel mix changes.")
        return _make_insight_output()

    async def _mock_run_replanner_agent(**kwargs):
        on_thinking = kwargs.get("on_thinking")
        if on_thinking:
            await on_thinking("Evaluating whether deeper drill-down is needed")
        return ReplanDecision(
            should_replan=True,
            reason="Further localization is still needed by channel",
            new_question="Continue analyzing the East-region sales decline by channel",
            suggested_questions=[
                "Compare the decline gap across channels",
                "Inspect product-structure changes inside the anomalous channel",
            ],
            candidate_questions=[
                CandidateQuestion(
                    question="Continue analyzing the East-region sales decline by channel",
                    question_type="drilldown",
                    priority=1,
                    expected_info_gain=0.82,
                    rationale="Continue locking onto the anomalous channel",
                    estimated_mode="single_query",
                ),
                CandidateQuestion(
                    question="Compare the decline gap across channels",
                    question_type="comparison",
                    priority=2,
                    expected_info_gain=0.75,
                    rationale="Compare the gap between channels",
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(return_value={
            "success": True,
            "query_execute_ms": 19.0,
            "tableData": {
                "columns": [
                    {"name": "Region"},
                    {"name": "Sales", "dataType": "REAL", "isMeasure": True},
                ],
                "rows": [{"Region": "East", "Sales": 120.5}],
                "rowCount": 1,
                "executionTimeMs": 9,
            },
        }),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_insight_agent",
        side_effect=_mock_run_insight_agent,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_replanner_agent",
        side_effect=_mock_run_replanner_agent,
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="Show sales by region",
                datasource_name="sales",
            )
        ]

    insight_event = next(e for e in events if e["type"] == "insight")
    replan_event = next(e for e in events if e["type"] == "replan")
    complete_event = next(e for e in events if e["type"] == "complete")
    token_events = [e for e in events if e["type"] == "token"]
    thinking_events = [e for e in events if e["type"] == "thinking"]

    assert token_events and all(e["content"] for e in token_events)
    assert insight_event["source"] == "single_query"
    assert insight_event["summary"]
    assert replan_event["shouldReplan"] is True
    assert replan_event["reason"]
    assert replan_event["candidateQuestions"][0]["priority"] == 1
    assert replan_event["candidateQuestions"][0]["question"] == replan_event["newQuestion"]
    assert replan_event["questions"][0] == replan_event["newQuestion"]
    assert len(replan_event["questions"]) == 3
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
    """In auto_continue mode, executor should automatically execute the next question selected by replanner."""
    loader_instance = MagicMock()
    loader_instance.load_data_model = AsyncMock(return_value=_DummyDataModel())
    graph = _QuestionAwareSingleQueryGraph()

    async def _mock_run_insight_agent(**kwargs):
        semantic_output_dict = kwargs["semantic_output_dict"]
        question = semantic_output_dict.get("restated_question", "")
        if "Channel" in question:
            return _make_insight_output(summary="Channel view shows the direct-sales network dropped the most")
        return _make_insight_output(summary="Region view shows the East region dropped the most")

    replanner_results = [
        ReplanDecision(
            should_replan=True,
            reason="We still need to localize the East-region decline by channel",
            new_question="Continue analyzing the East-region sales decline by channel",
            suggested_questions=["Compare the decline gap across channels"],
            candidate_questions=[
                CandidateQuestion(
                    question="Continue analyzing the East-region sales decline by channel",
                    question_type="drilldown",
                    priority=1,
                    expected_info_gain=0.84,
                    rationale="Continue locating the anomalous channel",
                    estimated_mode="single_query",
                )
            ],
        ),
        ReplanDecision(
            should_replan=False,
            reason="The channel-level anomaly is already enough to explain the current question",
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(side_effect=[
            {
                "success": True,
                "query_execute_ms": 19.0,
                "tableData": {
                    "columns": [{"name": "Region"}],
                    "rows": [["East"]],
                    "rowCount": 1,
                    "executionTimeMs": 9,
                },
            },
            {
                "success": True,
                "query_execute_ms": 17.0,
                "tableData": {
                    "columns": [{"name": "Channel"}],
                    "rows": [["????"]],
                    "rowCount": 1,
                    "executionTimeMs": 8,
                },
            },
        ]),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_insight_agent",
        side_effect=_mock_run_insight_agent,
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_replanner_agent",
        new=AsyncMock(side_effect=replanner_results),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="Show sales by region",
                datasource_name="sales",
                replan_mode="auto_continue",
            )
        ]

    parse_events = [e for e in events if e["type"] == "parse_result"]
    replan_events = [e for e in events if e["type"] == "replan"]
    complete_event = next(e for e in events if e["type"] == "complete")

    assert graph.questions == [
        "Show sales by region",
        "Continue analyzing the East-region sales decline by channel",
    ]
    assert len(parse_events) == 2
    assert replan_events[0]["action"] == "auto_continue"
    assert replan_events[0]["selectedQuestion"] == "Continue analyzing the East-region sales decline by channel"
    assert complete_event["optimization_metrics"]["auto_continue_triggered"] is True


@pytest.mark.asyncio
async def test_execute_stream_selected_candidate_question_overrides_current_question():
    """In user_select mode, `selected_candidate_question` should be executed directly."""
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(return_value={
            "success": True,
            "query_execute_ms": 16.0,
            "tableData": {
                "columns": [{"name": "Channel"}],
                "rows": [["????"]],
                "rowCount": 1,
                "executionTimeMs": 8,
            },
        }),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_insight_agent",
        new=AsyncMock(return_value=_make_insight_output(summary="Channel view shows the direct-sales network dropped the most")),
    ), patch(
        "analytics_assistant.src.orchestration.workflow.executor.invoke_replanner_agent",
        new=AsyncMock(return_value=ReplanDecision(
            should_replan=False,
            reason="The current channel analysis is already sufficient",
            suggested_questions=[],
            candidate_questions=[],
        )),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="The original question should not be executed",
                datasource_name="sales",
                replan_mode="user_select",
                selected_candidate_question="Continue analyzing the East-region sales decline by channel",
            )
        ]

    parse_event = next(e for e in events if e["type"] == "parse_result")

    assert graph.questions == ["Continue analyzing the East-region sales decline by channel"]
    assert parse_event["summary"]["restated_question"] == "Continue analyzing the East-region sales decline by channel"


@pytest.mark.asyncio
async def test_execute_stream_followup_plan_step_can_clarify():
    """follow-up step 澄清时，应通过 native interrupt 输出 plan_step 和 interrupt 事件。"""
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
        "analytics_assistant.src.orchestration.workflow.executor.execute_semantic_query",
        new=AsyncMock(return_value={
            "success": True,
            "query_execute_ms": 21.0,
            "tableData": {
                "columns": [{"name": "Region"}],
                "rows": [["East"]],
                "rowCount": 1,
                "executionTimeMs": 10,
            },
        }),
    ):
        executor = WorkflowExecutor("admin", request_id="req-test")
        events = [
            event
            async for event in executor.execute_stream(
                question="Why did sales decline in the East region?",
                datasource_name="sales",
            )
        ]

    clarification_event = next(e for e in events if e["type"] == "interrupt")
    plan_step_clarification = next(
        e for e in events
        if e["type"] == "plan_step" and e["status"] == "clarification"
    )
    assert clarification_event["interrupt_type"] == "missing_slot"
    assert clarification_event["payload"]["message"] == "Confirm drilldown dimension"
    assert clarification_event["payload"]["options"] == ["product_name", "product_category"]
    assert clarification_event["payload"]["resume_strategy"] == "langgraph_native"
    assert clarification_event["payload"]["interrupt_ns"] == ["semantic_understanding:plan-step"]
    assert plan_step_clarification["step"]["index"] == 2
    assert plan_step_clarification["question"] == clarification_event["payload"]["message"]
    assert plan_step_clarification["slot_name"] == "dimension"
    assert plan_step_clarification["options"] == ["product_name", "product_category"]
    clarification_metrics = clarification_event["payload"]["optimization_metrics"]
    assert clarification_metrics["planner_multistep_enabled"] is True
    assert clarification_metrics["planner_blocked_step"] == 2
    assert all(e["type"] != "complete" for e in events)


