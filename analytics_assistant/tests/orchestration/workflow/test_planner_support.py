from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
    EvidenceContext,
    PlanStepKind,
    PlanStepType,
    StepArtifact,
)
from analytics_assistant.src.orchestration.workflow.planner_support import (
    append_step_artifact,
    build_evidence_bundle_dict,
)


def test_screen_top_axes_uses_live_table_data_for_axis_scores() -> None:
    prior_context = EvidenceContext(
        primary_question="why revenue dropped",
        validated_axes=["channel", "product_line"],
        step_artifacts=[
            StepArtifact(
                step_id="step-2",
                title="解释轴排序",
                step_type=PlanStepType.QUERY,
                step_kind=PlanStepKind.RANK_EXPLANATORY_AXES,
                validated_axes=["channel", "product_line"],
            )
        ],
    )

    updated_context = append_step_artifact(
        prior_context,
        step_payload={
            "stepId": "step-3",
            "index": 3,
            "title": "筛查解释轴",
            "stepType": "query",
            "stepKind": "screen_top_axes",
            "candidateAxes": ["channel", "product_line"],
            "semanticFocus": ["channel", "product_line"],
        },
        table_data={
            "columns": [
                {
                    "name": "Product Line",
                    "dataType": "STRING",
                    "isDimension": True,
                    "isMeasure": False,
                },
                {
                    "name": "sales",
                    "dataType": "REAL",
                    "isDimension": False,
                    "isMeasure": True,
                },
            ],
            "rows": [
                {"Product Line": "Office", "sales": 120},
                {"Product Line": "Furniture", "sales": 30},
            ],
            "rowCount": 2,
        },
        semantic_summary={
            "dimensions": ["Product Line"],
            "measures": ["sales"],
            "filters": [],
        },
        evidence_context_before_step=prior_context,
    )

    assert updated_context.step_artifacts[-1].validated_axes[:2] == ["product_line", "channel"]
    assert updated_context.axis_scores[0].axis == "product_line"
    assert updated_context.axis_scores[0].explained_share > updated_context.axis_scores[1].explained_share
    assert "live query results" in updated_context.axis_scores[0].reason


def test_build_evidence_bundle_dict_keeps_why_evidence() -> None:
    evidence_context = EvidenceContext(
        primary_question="为什么华东区销售下降了？",
        validated_axes=["product_line", "channel"],
        anomalous_entities=["办公产品线"],
        key_entities=["华东区"],
        open_questions=["是否集中在企业客户"],
        step_artifacts=[
            StepArtifact(
                step_id="step-4",
                title="定位异常切片",
                step_type=PlanStepType.QUERY,
                step_kind=PlanStepKind.LOCATE_ANOMALOUS_SLICE,
                table_summary="办公产品线贡献了主要降幅。",
                validated_axes=["product_line"],
                entity_scope=["办公产品线"],
            )
        ],
    )
    evidence_context.axis_scores = []

    bundle = build_evidence_bundle_dict(
        "为什么华东区销售下降了？",
        evidence_context,
        source="planner_synthesis",
        query_id="query-why-1",
    )

    assert bundle["source"] == "planner_synthesis"
    assert bundle["question"] == "为什么华东区销售下降了？"
    assert bundle["query_id"] == "query-why-1"
    assert bundle["validated_axes"] == ["product_line", "channel"]
    assert bundle["anomalous_entities"] == ["办公产品线"]
    assert bundle["open_questions"] == ["是否集中在企业客户"]
    assert bundle["latest_summary"] == "办公产品线贡献了主要降幅。"
    assert bundle["step_artifacts"][0]["step_id"] == "step-4"
