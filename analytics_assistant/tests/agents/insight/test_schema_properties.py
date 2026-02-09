# -*- coding: utf-8 -*-
"""
Insight / Replanner Schema 属性测试

**Validates: Requirements 11.6, 11.7, 11.8**
**PBT**: Property 6 - 数据模型序列化往返一致性

测试内容：
- InsightOutput 序列化往返一致性
- ReplanDecision 序列化往返一致性
- DataProfile 序列化往返一致性
"""
import pytest
from hypothesis import given, settings, strategies as st

from analytics_assistant.src.agents.insight.schemas.output import (
    AnalysisLevel,
    CategoricalStats,
    ColumnProfile,
    DataProfile,
    Finding,
    FindingType,
    InsightOutput,
    NumericStats,
)
from analytics_assistant.src.agents.replanner.schemas.output import ReplanDecision


# ═══════════════════════════════════════════════════════════════════════════
# Hypothesis 策略（生成器）
# ═══════════════════════════════════════════════════════════════════════════

# 基础策略
_confidence = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
_non_empty_text = st.text(min_size=1, max_size=100)


# Finding 策略
_finding_type = st.sampled_from(list(FindingType))
_analysis_level = st.sampled_from(list(AnalysisLevel))
_supporting_data = st.dictionaries(
    keys=st.text(min_size=1, max_size=20),
    values=st.one_of(
        st.integers(min_value=-10000, max_value=10000),
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        st.text(max_size=50),
        st.booleans(),
        st.none(),
    ),
    max_size=5,
)

_finding = st.builds(
    Finding,
    finding_type=_finding_type,
    analysis_level=_analysis_level,
    description=_non_empty_text,
    supporting_data=_supporting_data,
    confidence=_confidence,
)

# InsightOutput 策略
_insight_output = st.builds(
    InsightOutput,
    findings=st.lists(_finding, min_size=1, max_size=5),
    summary=_non_empty_text,
    overall_confidence=_confidence,
)

# NumericStats 策略
_optional_float = st.one_of(
    st.none(),
    st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False),
)
_numeric_stats = st.builds(
    NumericStats,
    min=_optional_float,
    max=_optional_float,
    avg=_optional_float,
    median=_optional_float,
    std=_optional_float,
)

# CategoricalStats 策略
_top_value_entry = st.fixed_dictionaries({
    "value": st.text(max_size=20),
    "count": st.integers(min_value=0, max_value=10000),
})
_categorical_stats = st.builds(
    CategoricalStats,
    unique_count=st.integers(min_value=0, max_value=10000),
    top_values=st.lists(_top_value_entry, max_size=10),
)

# ColumnProfile 策略
_column_profile = st.one_of(
    # 数值列
    st.builds(
        ColumnProfile,
        column_name=_non_empty_text,
        data_type=st.sampled_from(["INTEGER", "FLOAT", "DOUBLE", "DECIMAL"]),
        is_numeric=st.just(True),
        null_count=st.integers(min_value=0, max_value=1000),
        numeric_stats=st.one_of(st.none(), _numeric_stats),
        categorical_stats=st.none(),
        error=st.one_of(st.none(), _non_empty_text),
    ),
    # 分类列
    st.builds(
        ColumnProfile,
        column_name=_non_empty_text,
        data_type=st.sampled_from(["STRING", "BOOLEAN", "DATE"]),
        is_numeric=st.just(False),
        null_count=st.integers(min_value=0, max_value=1000),
        numeric_stats=st.none(),
        categorical_stats=st.one_of(st.none(), _categorical_stats),
        error=st.one_of(st.none(), _non_empty_text),
    ),
)

# DataProfile 策略
@st.composite
def _data_profile_strategy(draw):
    """生成有效的 DataProfile（column_count 与 columns_profile 长度一致）。"""
    columns = draw(st.lists(_column_profile, min_size=0, max_size=8))
    row_count = draw(st.integers(min_value=0, max_value=100000))
    return DataProfile(
        row_count=row_count,
        column_count=len(columns),
        columns_profile=columns,
    )

# ReplanDecision 策略
@st.composite
def _replan_decision_strategy(draw):
    """生成有效的 ReplanDecision。"""
    should_replan = draw(st.booleans())
    reason = draw(_non_empty_text)
    if should_replan:
        new_question = draw(_non_empty_text)
        suggested = draw(st.lists(_non_empty_text, max_size=3))
    else:
        new_question = None
        suggested = draw(st.lists(_non_empty_text, min_size=1, max_size=5))
    return ReplanDecision(
        should_replan=should_replan,
        reason=reason,
        new_question=new_question,
        suggested_questions=suggested,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 6: 数据模型序列化往返一致性
# ═══════════════════════════════════════════════════════════════════════════


class TestInsightOutputRoundTrip:
    """InsightOutput 序列化往返一致性。

    **Validates: Requirements 11.6**
    """

    @given(instance=_insight_output)
    @settings(max_examples=100)
    def test_roundtrip(self, instance: InsightOutput) -> None:
        """序列化后反序列化应产生等价对象。"""
        dumped = instance.model_dump()
        restored = InsightOutput.model_validate(dumped)
        assert restored == instance

    @given(instance=_insight_output)
    @settings(max_examples=50)
    def test_json_roundtrip(self, instance: InsightOutput) -> None:
        """JSON 字符串序列化往返一致性。"""
        json_str = instance.model_dump_json()
        restored = InsightOutput.model_validate_json(json_str)
        assert restored == instance


class TestReplanDecisionRoundTrip:
    """ReplanDecision 序列化往返一致性。

    **Validates: Requirements 11.7**
    """

    @given(instance=_replan_decision_strategy())
    @settings(max_examples=100)
    def test_roundtrip(self, instance: ReplanDecision) -> None:
        """序列化后反序列化应产生等价对象。"""
        dumped = instance.model_dump()
        restored = ReplanDecision.model_validate(dumped)
        assert restored == instance

    @given(instance=_replan_decision_strategy())
    @settings(max_examples=50)
    def test_json_roundtrip(self, instance: ReplanDecision) -> None:
        """JSON 字符串序列化往返一致性。"""
        json_str = instance.model_dump_json()
        restored = ReplanDecision.model_validate_json(json_str)
        assert restored == instance


class TestDataProfileRoundTrip:
    """DataProfile 序列化往返一致性。

    **Validates: Requirements 11.8**
    """

    @given(instance=_data_profile_strategy())
    @settings(max_examples=100)
    def test_roundtrip(self, instance: DataProfile) -> None:
        """序列化后反序列化应产生等价对象。"""
        dumped = instance.model_dump()
        restored = DataProfile.model_validate(dumped)
        assert restored == instance

    @given(instance=_data_profile_strategy())
    @settings(max_examples=50)
    def test_json_roundtrip(self, instance: DataProfile) -> None:
        """JSON 字符串序列化往返一致性。"""
        json_str = instance.model_dump_json()
        restored = DataProfile.model_validate_json(json_str)
        assert restored == instance
