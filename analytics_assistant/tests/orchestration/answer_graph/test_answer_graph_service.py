# -*- coding: utf-8 -*-

from analytics_assistant.src.agents.replanner.schemas.output import (
    CandidateQuestion,
    ReplanDecision,
)
from analytics_assistant.src.orchestration.answer_graph import service as answer_service
from analytics_assistant.src.orchestration.answer_graph.service import (
    build_replan_followup_history,
    build_replan_projection,
    serialize_insight_payload,
)


def test_serialize_insight_payload_normalizes_findings():
    payload = serialize_insight_payload(
        {
            "summary": "直营渠道下降最明显",
            "overall_confidence": 0.81,
            "findings": [
                {
                    "finding_type": "anomaly",
                    "analysis_level": "diagnostic",
                    "description": "直营渠道降幅最大",
                    "confidence": 0.9,
                    "supporting_data": {"channel": "直营"},
                }
            ],
        }
    )

    assert payload["summary"] == "直营渠道下降最明显"
    assert payload["overallConfidence"] == 0.81
    assert payload["findings"][0]["findingType"] == "anomaly"


def test_build_replan_projection_user_select_emits_interrupt_payload():
    decision = ReplanDecision(
        should_replan=True,
        reason="可以继续按产品线补查",
        new_question="按产品线继续分析",
        suggested_questions=["按渠道继续分析"],
        candidate_questions=[
            CandidateQuestion(
                question="按产品线继续分析",
                question_type="drilldown",
                priority=1,
                expected_info_gain=0.9,
                rationale="定位主因",
                estimated_mode="single_query",
            )
        ],
    )

    projection = build_replan_projection(
        replan_decision=decision,
        source="single_query",
        replan_mode="user_select",
        current_question="为什么最近销售下降",
    )

    assert projection["action"] == "await_user_select"
    assert projection["interrupt_payload"] is not None
    assert projection["replan_event"]["candidateQuestions"][0]["question"] == "按产品线继续分析"
    assert projection["replan_event"]["questions"][0] == "按产品线继续分析"


def test_build_replan_projection_auto_continue_skips_seen_questions():
    decision = ReplanDecision(
        should_replan=True,
        reason="继续往渠道下钻",
        new_question="按产品线继续分析",
        suggested_questions=["按渠道继续分析"],
        candidate_questions=[
            CandidateQuestion(
                question="按产品线继续分析",
                question_type="drilldown",
                priority=1,
                expected_info_gain=0.8,
                rationale="已经看过产品线则跳过",
                estimated_mode="single_query",
            ),
            CandidateQuestion(
                question="按渠道继续分析",
                question_type="comparison",
                priority=2,
                expected_info_gain=0.7,
                rationale="补充对比",
                estimated_mode="single_query",
            ),
        ],
    )

    projection = build_replan_projection(
        replan_decision=decision,
        source="single_query",
        replan_mode="auto_continue",
        current_question="为什么最近销售下降",
        replan_history=[{"new_question": "按产品线继续分析"}],
    )

    assert projection["action"] == "auto_continue"
    assert projection["selected_question"] == "按渠道继续分析"
    assert projection["interrupt_payload"] is None


def test_build_replan_projection_stops_when_replan_round_limit_reached(
    monkeypatch,
):
    monkeypatch.setattr(answer_service, "_get_max_replan_rounds", lambda: 2)
    decision = ReplanDecision(
        should_replan=True,
        reason="继续按渠道分析",
        new_question="按渠道继续分析",
        suggested_questions=["按产品继续分析"],
        candidate_questions=[
            CandidateQuestion(
                question="按渠道继续分析",
                question_type="drilldown",
                priority=1,
                expected_info_gain=0.85,
                rationale="继续验证渠道贡献",
                estimated_mode="single_query",
            )
        ],
    )

    projection = build_replan_projection(
        replan_decision=decision,
        source="single_query",
        replan_mode="auto_continue",
        current_question="为什么最近销售下降",
        replan_history=[
            {"new_question": "按产品线继续分析"},
            {"new_question": "按客户类型继续分析"},
        ],
    )

    assert projection["action"] == "stop"
    assert projection["selected_question"] is None
    assert projection["candidate_questions"] == []
    assert projection["interrupt_payload"] is None
    assert projection["replan_event"]["shouldReplan"] is False
    assert projection["replan_event"]["replanRoundLimitReached"] is True
    assert projection["replan_event"]["reason"] == "已达到最大重规划轮数上限（2 轮）"


def test_build_replan_followup_history_includes_round_context():
    history = build_replan_followup_history(
        [],
        previous_question="为什么最近销售下降",
        round_summary="直营渠道贡献了主要降幅",
        replan_reason="需要继续核对渠道差异",
        next_question="按渠道继续分析",
    )

    assert len(history) == 1
    assert "上一轮问题：为什么最近销售下降" in history[0]["content"]
    assert "当前继续分析的问题：按渠道继续分析" in history[0]["content"]
