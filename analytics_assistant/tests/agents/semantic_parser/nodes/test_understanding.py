# -*- coding: utf-8 -*-
"""
语义理解节点模型选择测试
"""

from unittest.mock import MagicMock, patch

from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
from analytics_assistant.src.agents.semantic_parser.nodes.understanding import (
    _analysis_plan_requires_reasoning,
    _enrich_clarification_output,
    _get_semantic_llm,
    _should_use_fast_semantic_model,
    _try_build_simple_clarification_output,
    _try_build_simple_semantic_output,
)
from analytics_assistant.src.agents.semantic_parser.schemas.output import (
    SemanticOutput,
    SelfCheck,
    What,
    Where,
)
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    ComplexityType,
    FeatureExtractionOutput,
    MatchedComputation,
    PrefilterResult,
)
from analytics_assistant.src.agents.semantic_parser.schemas.planner import (
    AnalysisMode,
    AnalysisPlan,
    GlobalUnderstandingOutput,
    PlanMode,
    StepIntent,
)


def _build_state(
    *,
    complexity: list[ComplexityType],
    confirmation_confidence: float,
    matched_computations: list[MatchedComputation] | None = None,
    few_shot_examples: list[dict] | None = None,
    field_candidates: list[FieldCandidate] | None = None,
    current_step_intent: StepIntent | None = None,
) -> dict:
    prefilter_result = PrefilterResult(
        detected_complexity=complexity,
        matched_computations=matched_computations or [],
        detected_language="zh",
    )
    feature_output = FeatureExtractionOutput(
        required_measures=["销售额"],
        required_dimensions=["地区"],
        confirmation_confidence=confirmation_confidence,
        is_degraded=False,
    )
    return {
        "prefilter_result": prefilter_result.model_dump(),
        "feature_extraction_output": feature_output.model_dump(),
        "few_shot_examples": few_shot_examples or [],
        "field_candidates": [
            candidate.model_dump() for candidate in (field_candidates or [])
        ],
        "current_step_intent": (
            current_step_intent.model_dump() if current_step_intent else None
        ),
    }


class TestSemanticUnderstandingModelSelection:
    """简单查询的模型选择回归测试。"""

    def test_planner_reasoning_path_disables_fast_model(self):
        """analysis_plan 要求推理时，不应再走快模型。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
        )
        state["analysis_plan"] = AnalysisPlan(
            plan_mode=PlanMode.WHY_ANALYSIS,
            needs_planning=True,
            requires_llm_reasoning=True,
        ).model_dump()

        assert _analysis_plan_requires_reasoning(state) is True
        assert _should_use_fast_semantic_model(state, "short prompt") is False

    def test_global_understanding_embedded_plan_also_disables_fast_model(self):
        """仅存在 global_understanding.analysis_plan 时，也应保留推理路径。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
        )
        plan = AnalysisPlan(
            plan_mode=PlanMode.WHY_ANALYSIS,
            single_query_feasible=False,
            needs_planning=True,
            requires_llm_reasoning=True,
        )
        state["global_understanding"] = GlobalUnderstandingOutput(
            analysis_mode=AnalysisMode.WHY_ANALYSIS,
            single_query_feasible=False,
            primary_restated_question="为什么华东区销售额下降了？",
            llm_confidence=0.84,
            analysis_plan=plan,
        ).model_dump()

        assert _analysis_plan_requires_reasoning(state) is True
        assert _should_use_fast_semantic_model(state, "short prompt") is False

    def test_simple_high_confidence_query_uses_fast_model(self):
        """简单且高置信度请求应启用快模型。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.9,
        )

        assert _should_use_fast_semantic_model(state, "short prompt")

        fake_llm = MagicMock(model_name="deepseek-chat")
        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.understanding.get_llm",
            return_value=fake_llm,
        ) as mock_get_llm:
            llm, using_fast_model = _get_semantic_llm(state, "short prompt")

        assert llm is fake_llm
        assert using_fast_model is True
        assert mock_get_llm.call_args.kwargs["model_id"] == "custom-deepseek-r1"

    def test_computation_query_keeps_default_model(self):
        """包含计算信号的请求仍保留默认推理模型路径。"""
        state = _build_state(
            complexity=[ComplexityType.RATIO],
            confirmation_confidence=0.95,
            matched_computations=[
                MatchedComputation(
                    seed_name="profit_rate",
                    display_name="利润率",
                    calc_type="RATIO",
                    formula="{profit}/{revenue}",
                )
            ],
        )

        assert _should_use_fast_semantic_model(state, "short prompt") is False

        fake_llm = MagicMock(model_name="deepseek-r1-distill-qwen")
        with patch(
            "analytics_assistant.src.agents.semantic_parser.nodes.understanding.get_llm",
            return_value=fake_llm,
        ) as mock_get_llm:
            llm, using_fast_model = _get_semantic_llm(state, "short prompt")

        assert llm is fake_llm
        assert using_fast_model is False
        assert mock_get_llm.call_args.kwargs.get("model_id") is None

    def test_followup_step_context_disables_fast_model(self):
        """follow-up step 即使表面简单，也不应走快模型。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            current_step_intent=StepIntent(
                step_id="step-2",
                title="按异常省份继续拆分",
                question="对异常省份继续按产品拆分",
                depends_on=["step-1"],
                semantic_focus=["异常归因", "结构分解"],
                candidate_axes=["产品", "渠道"],
            ),
        )

        assert _should_use_fast_semantic_model(state, "short prompt") is False


class TestSimpleSemanticShortcut:
    """简单查询直出快捷路径测试。"""

    def test_measure_technical_hints_resolve_without_semantic_aliases(self):
        """技术字段名也应能帮助简单度量在无 alias 时命中快捷路径。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    match_type="exact",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = [
            "销售额",
            "Sales",
        ]
        state["feature_extraction_output"]["required_dimensions"] = []

        result = _try_build_simple_semantic_output(
            state,
            "总销售额是多少",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == ["Sale Amtws"]

    def test_measure_synonyms_can_share_single_candidate(self):
        """同义词重复不应导致快捷路径误判为多个独立字段。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Weg",
                    field_caption="Sale Weg",
                    role="measure",
                    confidence=0.95,
                    measure_category="quantity",
                    aliases=["Quantity", "units_sold"],
                    match_type="exact",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = [
            "数量",
            "units_sold",
            "Quantity",
        ]
        state["feature_extraction_output"]["required_dimensions"] = []

        result = _try_build_simple_semantic_output(
            state,
            "销售数量汇总",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == ["Sale Weg"]

    def test_measure_category_from_field_semantic_resolves_opaque_metric_name(self):
        """字段名不友好时，也应能借助 measure_category + seeds 命中真实度量。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="M001",
                    field_caption="M001",
                    role="measure",
                    confidence=0.95,
                    measure_category="revenue",
                    match_type="semantic",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["营收"]
        state["feature_extraction_output"]["required_dimensions"] = []

        result = _try_build_simple_semantic_output(
            state,
            "营收是多少",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == ["M001"]

    def test_measure_alias_variants_reuse_candidate_without_explicit_aliases(self):
        """下划线/大小写变体也应复用同一 quantity 候选，而不是触发残留澄清。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Weg",
                    field_caption="Sale Weg",
                    role="measure",
                    confidence=0.95,
                    measure_category="quantity",
                    match_type="exact",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = [
            "数量",
            "units_sold",
            "Quantity",
        ]
        state["feature_extraction_output"]["required_dimensions"] = []

        result = _try_build_simple_semantic_output(
            state,
            "销售数量是多少",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == ["Sale Weg"]

    def test_quantity_phrase_does_not_pull_revenue_candidate(self):
        """“销售数量”应优先命中 quantity，而不是被 revenue 的“销售”误吸附。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Sale Weg",
                    field_caption="Sale Weg",
                    role="measure",
                    confidence=0.94,
                    measure_category="quantity",
                    match_type="exact",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售数量"]
        state["feature_extraction_output"]["required_dimensions"] = []

        result = _try_build_simple_semantic_output(
            state,
            "销售数量是多少",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == ["Sale Weg"]

    def test_revenue_term_does_not_match_profit_only_via_description(self):
        """销售额不应仅因 profit 描述里含 revenue 而误命中利润字段。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Gross Profit",
                    field_caption="Gross Profit",
                    role="measure",
                    confidence=0.95,
                    business_description="Revenue minus cost of goods sold",
                    aliases=["毛利", "毛利润"],
                    measure_category="profit",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.9,
                    measure_category="revenue",
                    match_type="exact",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售额", "毛利"]
        state["feature_extraction_output"]["required_dimensions"] = []

        result = _try_build_simple_semantic_output(
            state,
            "销售额和毛利",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == [
            "Sale Amtws",
            "Gross Profit",
        ]

    def test_measure_only_query_builds_shortcut_output(self):
        """高置信度简单双度量查询应直接构造语义输出。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    aliases=["销售额"],
                    measure_category="revenue",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Gross Profit",
                    field_caption="Gross Profit",
                    role="measure",
                    confidence=0.94,
                    aliases=["毛利"],
                    measure_category="profit",
                    match_type="exact",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售额", "毛利"]
        state["feature_extraction_output"]["required_dimensions"] = []

        result = _try_build_simple_semantic_output(
            state,
            "总销售额和总毛利分别是多少",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == [
            "Sale Amtws",
            "Gross Profit",
        ]
        assert result.needs_clarification is False

    def test_followup_step_skips_simple_shortcut(self):
        """存在 step intent 上下文时，不应直接走 simple shortcut。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            current_step_intent=StepIntent(
                step_id="step-2",
                title="按产品拆",
                question="在异常省份内继续看产品",
                depends_on=["step-1"],
                semantic_focus=["异常定位"],
                candidate_axes=["产品"],
            ),
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    aliases=["销售额"],
                    measure_category="revenue",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Product Name",
                    field_caption="Product Name",
                    role="dimension",
                    confidence=0.94,
                    aliases=["产品"],
                    category="product",
                    level=3,
                    match_type="exact",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售额"]
        state["feature_extraction_output"]["required_dimensions"] = ["产品"]

        result = _try_build_simple_semantic_output(
            state,
            "看下这个省份里各产品的销售额",
        )

        assert result is None

    def test_ambiguous_dimension_query_skips_shortcut(self):
        """维度无法明确匹配时，不应走直出快捷路径。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    aliases=["销售额"],
                    measure_category="revenue",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Channel Manager Nm",
                    field_caption="Channel Manager Nm",
                    role="dimension",
                    confidence=0.94,
                    aliases=["渠道经理"],
                    match_type="semantic",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售额"]
        state["feature_extraction_output"]["required_dimensions"] = ["部门"]

        result = _try_build_simple_semantic_output(
            state,
            "各部门的销售额",
        )

        assert result is None

    def test_dimension_business_description_can_resolve_shortcut(self):
        """字段业务描述中的层级语义应能帮助简单维度直接命中。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    aliases=["销售额"],
                    measure_category="revenue",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Comp Name",
                    field_caption="Comp Name",
                    role="dimension",
                    confidence=0.93,
                    business_description="表示省份，地理维度粗粒度",
                    hierarchy_category="geography",
                    hierarchy_level=2,
                    match_type="semantic",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售额"]
        state["feature_extraction_output"]["required_dimensions"] = ["省份"]

        result = _try_build_simple_semantic_output(
            state,
            "各省份的销售额",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == ["Sale Amtws"]
        assert [d.field_name for d in result.where.dimensions] == ["Comp Name"]

    def test_dimension_category_and_level_can_resolve_opaque_field_name(self):
        """字段名不友好时，也应能借助 category/level 元数据命中维度。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    aliases=["销售额"],
                    measure_category="revenue",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="D001",
                    field_caption="D001",
                    role="dimension",
                    confidence=0.93,
                    hierarchy_category="geography",
                    hierarchy_level=2,
                    match_type="semantic",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售额"]
        state["feature_extraction_output"]["required_dimensions"] = ["省份"]

        result = _try_build_simple_semantic_output(
            state,
            "各省份的销售额",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == ["Sale Amtws"]
        assert [d.field_name for d in result.where.dimensions] == ["D001"]

    def test_ambiguous_simple_query_builds_clarification_shortcut(self):
        """简单查询字段不明确时，应直接返回规则澄清。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Weg",
                    field_caption="Sale Weg",
                    role="measure",
                    confidence=0.95,
                    aliases=["Quantity", "units_sold"],
                    measure_category="quantity",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Channel Manager Nm",
                    field_caption="Channel Manager Nm",
                    role="dimension",
                    confidence=0.92,
                    match_type="semantic",
                ),
                FieldCandidate(
                    field_name="Comp Name",
                    field_caption="Comp Name",
                    role="dimension",
                    confidence=0.88,
                    match_type="semantic",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = [
            "数量",
            "units_sold",
            "Quantity",
        ]
        state["feature_extraction_output"]["required_dimensions"] = [
            "部门",
            "department",
            "Department",
        ]

        result = _try_build_simple_clarification_output(
            state,
            "各部门的销售数量汇总",
        )

        assert result is not None
        assert result.needs_clarification is True
        assert [m.field_name for m in result.what.measures] == ["Sale Weg"]
        assert "部门" in (result.clarification_question or "")
        assert result.clarification_options

    def test_dimension_clarification_prefers_non_time_candidates(self):
        """省份/部门澄清时应优先展示组织类候选，而不是时间字段。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    aliases=["销售额"],
                    measure_category="revenue",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Sold Nm",
                    field_caption="Sold Nm",
                    role="dimension",
                    confidence=0.95,
                    business_description="销售方的名称，用于标识销售主体",
                    aliases=["销售方", "卖方名称"],
                    category="organization",
                    level=4,
                    sample_values=["成都高金食品有限公司"],
                    match_type="semantic",
                ),
                FieldCandidate(
                    field_name="Zsaleper Nm",
                    field_caption="Zsaleper Nm",
                    role="dimension",
                    confidence=0.83,
                    business_description="销售员的姓名，用于标识具体销售人员",
                    aliases=["销售员", "销售人员姓名"],
                    category="organization",
                    level=5,
                    sample_values=["张三"],
                    match_type="semantic",
                ),
                FieldCandidate(
                    field_name="Channel Manager Nm",
                    field_caption="Channel Manager Nm",
                    role="dimension",
                    confidence=0.78,
                    business_description="渠道经理的姓名，用于标识具体负责人",
                    aliases=["渠道经理", "经理姓名"],
                    category="organization",
                    level=5,
                    sample_values=["李四"],
                    match_type="semantic",
                ),
                FieldCandidate(
                    field_name="Last Time",
                    field_caption="Last Time",
                    role="dimension",
                    confidence=0.96,
                    business_description="最后发生的时间，用于记录事件的时间戳",
                    aliases=["最后时间"],
                    category="time",
                    level=5,
                    match_type="semantic",
                ),
                FieldCandidate(
                    field_name="Zdate",
                    field_caption="Zdate",
                    role="dimension",
                    confidence=0.94,
                    business_description="Date when order was shipped",
                    category="time",
                    level=5,
                    match_type="semantic",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售额"]
        state["feature_extraction_output"]["required_dimensions"] = ["省份", "部门"]

        result = _try_build_simple_clarification_output(
            state,
            "各省份各部门的销售额",
        )

        assert result is not None
        assert result.needs_clarification is True
        assert "最后时间 (Last Time)" not in result.clarification_options
        assert "Zdate" not in result.clarification_options
        assert result.clarification_options == [
            "销售方 (Sold Nm)",
            "销售员 (Zsaleper Nm)",
            "渠道经理 (Channel Manager Nm)",
        ]

    def test_dimension_clarification_uses_missing_dimension_question_when_no_category_match(self):
        """候选里没有明显省份维度时，应使用更明确的缺失提示文案。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    aliases=["销售额"],
                    measure_category="revenue",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Sold Nm",
                    field_caption="Sold Nm",
                    role="dimension",
                    confidence=0.95,
                    business_description="销售方的名称，用于标识销售主体",
                    aliases=["销售方", "卖方名称"],
                    category="organization",
                    level=4,
                    match_type="semantic",
                ),
                FieldCandidate(
                    field_name="Last Time",
                    field_caption="Last Time",
                    role="dimension",
                    confidence=0.9,
                    business_description="最后发生的时间，用于记录事件的时间戳",
                    aliases=["最后时间"],
                    category="time",
                    level=5,
                    match_type="semantic",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售额"]
        state["feature_extraction_output"]["required_dimensions"] = ["省份"]

        result = _try_build_simple_clarification_output(
            state,
            "各省份的销售额",
        )

        assert result is not None
        assert (
            result.clarification_question
            == "当前候选中没有明显对应“省份”的维度字段。以下哪个字段最接近你的分析意图？"
        )

    def test_partial_dimension_resolution_keeps_confirmed_fields(self):
        """部分字段可确认时，应保留真实字段并只澄清未确认部分。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    aliases=["销售额"],
                    measure_category="revenue",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Region Name",
                    field_caption="Region Name",
                    role="dimension",
                    confidence=0.94,
                    aliases=["地区"],
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Dept Name",
                    field_caption="Dept Name",
                    role="dimension",
                    confidence=0.92,
                    aliases=["组织单元"],
                    match_type="semantic",
                ),
                FieldCandidate(
                    field_name="Company Name",
                    field_caption="Company Name",
                    role="dimension",
                    confidence=0.90,
                    aliases=["法人主体"],
                    match_type="semantic",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售额"]
        state["feature_extraction_output"]["required_dimensions"] = ["地区", "部门"]

        result = _try_build_simple_clarification_output(
            state,
            "按地区和部门查看销售额",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == ["Sale Amtws"]
        assert [d.field_name for d in result.where.dimensions] == ["Region Name"]
        assert "部门" in (result.clarification_question or "")
        assert result.clarification_options
        assert result.clarification_options[0].startswith("组织单元")
        assert all("Region Name" not in option for option in result.clarification_options)

    def test_clarification_shortcut_accepts_low_confidence_measure_candidates(self):
        """澄清场景应允许保留检索到的低置信度 top measure 候选。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.90,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.50,
                    match_type="fallback",
                ),
                FieldCandidate(
                    field_name="Gross Profit",
                    field_caption="Gross Profit",
                    role="measure",
                    confidence=0.50,
                    match_type="fallback",
                ),
                FieldCandidate(
                    field_name="Channel Manager Nm",
                    field_caption="Channel Manager Nm",
                    role="dimension",
                    confidence=0.50,
                    match_type="fallback",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = [
            "销售额",
            "毛利",
            "Sales",
        ]
        state["feature_extraction_output"]["required_dimensions"] = ["部门"]

        result = _try_build_simple_clarification_output(
            state,
            "各部门的销售额和毛利",
        )

        assert result is not None
        assert [m.field_name for m in result.what.measures] == [
            "Sale Amtws",
            "Gross Profit",
        ]
        assert result.needs_clarification is True

    def test_followup_step_skips_clarification_shortcut(self):
        """follow-up step 也不应直接走规则澄清输出。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            current_step_intent=StepIntent(
                step_id="step-2",
                title="按产品拆",
                question="在异常省份内继续看产品",
                depends_on=["step-1"],
                semantic_focus=["异常定位"],
                candidate_axes=["产品"],
            ),
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Weg",
                    field_caption="Sale Weg",
                    role="measure",
                    confidence=0.95,
                    aliases=["Quantity", "units_sold"],
                    measure_category="quantity",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Product Name",
                    field_caption="Product Name",
                    role="dimension",
                    confidence=0.92,
                    match_type="semantic",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["数量"]
        state["feature_extraction_output"]["required_dimensions"] = ["产品层级"]

        result = _try_build_simple_clarification_output(
            state,
            "这个省里看各产品的销量",
        )

        assert result is None


class TestClarificationEnrichment:
    """澄清输出回填测试。"""

    def test_enrich_clarification_prefers_resolved_candidates(self):
        """澄清后处理应优先回填真实字段名，而不是继续保留占位词。"""
        state = _build_state(
            complexity=[ComplexityType.SIMPLE],
            confirmation_confidence=0.95,
            field_candidates=[
                FieldCandidate(
                    field_name="Sale Amtws",
                    field_caption="Sale Amtws",
                    role="measure",
                    confidence=0.95,
                    aliases=["销售额"],
                    measure_category="revenue",
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Region Name",
                    field_caption="Region Name",
                    role="dimension",
                    confidence=0.94,
                    aliases=["地区"],
                    match_type="exact",
                ),
                FieldCandidate(
                    field_name="Dept Name",
                    field_caption="Dept Name",
                    role="dimension",
                    confidence=0.92,
                    aliases=["组织单元"],
                    match_type="semantic",
                ),
                FieldCandidate(
                    field_name="Company Name",
                    field_caption="Company Name",
                    role="dimension",
                    confidence=0.90,
                    aliases=["法人主体"],
                    match_type="semantic",
                ),
            ],
        )
        state["feature_extraction_output"]["required_measures"] = ["销售额"]
        state["feature_extraction_output"]["required_dimensions"] = ["地区", "部门"]
        result = SemanticOutput(
            restated_question="按地区和部门查看销售额",
            what=What(measures=["销售额"]),
            where=Where(dimensions=["地区", "部门"]),
            needs_clarification=True,
            clarification_question="“部门”具体对应哪个维度字段？",
            clarification_options=[],
            self_check=SelfCheck(
                field_mapping_confidence=0.55,
                time_range_confidence=1.0,
                computation_confidence=1.0,
                overall_confidence=0.55,
            ),
        )

        enriched = _enrich_clarification_output(result, state)

        assert [m.field_name for m in enriched.what.measures] == ["Sale Amtws"]
        assert [d.field_name for d in enriched.where.dimensions] == ["Region Name"]
        assert enriched.clarification_options
        assert enriched.clarification_options[0].startswith("组织单元")
        assert any(
            "真实候选字段" in warning
            for warning in enriched.parsing_warnings
        )
