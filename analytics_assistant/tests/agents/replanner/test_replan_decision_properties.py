# -*- coding: utf-8 -*-
"""
ReplanDecision 属性测试

Property 5: should_replan=True 时 reason 和 new_question 非空；
            should_replan=False 时 suggested_questions 非空

**Validates: Requirements 6.2, 6.3**

使用 Hypothesis 生成随机有效 ReplanDecision 实例，验证结构一致性。
"""
import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from analytics_assistant.src.agents.replanner.schemas.output import ReplanDecision


# ═══════════════════════════════════════════════════════════════════════════
# 策略定义
# ═══════════════════════════════════════════════════════════════════════════

# 非空字符串策略
non_empty_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())

# 建议问题列表策略（至少 1 条）
suggested_questions_st = st.lists(non_empty_text, min_size=1, max_size=5)

# 有效的 should_replan=True 实例
valid_replan_true_st = st.builds(
    ReplanDecision,
    should_replan=st.just(True),
    reason=non_empty_text,
    new_question=non_empty_text,
    suggested_questions=st.lists(non_empty_text, min_size=0, max_size=5),
)

# 有效的 should_replan=False 实例
valid_replan_false_st = st.builds(
    ReplanDecision,
    should_replan=st.just(False),
    reason=non_empty_text,
    new_question=st.one_of(st.none(), non_empty_text),
    suggested_questions=suggested_questions_st,
)

# 任意有效 ReplanDecision
valid_replan_decision_st = st.one_of(valid_replan_true_st, valid_replan_false_st)


# ═══════════════════════════════════════════════════════════════════════════
# Property 5: ReplanDecision 结构一致性
# ═══════════════════════════════════════════════════════════════════════════


class TestReplanDecisionProperty5:
    """Feature: insight-replanner, Property 5: ReplanDecision 结构一致性"""

    @given(decision=valid_replan_decision_st)
    @settings(max_examples=100)
    def test_valid_decision_consistency(self, decision: ReplanDecision):
        """**Validates: Requirements 6.2, 6.3**

        对于任意有效的 ReplanDecision：
        - should_replan=True 时 reason 和 new_question 均为非空字符串
        - should_replan=False 时 suggested_questions 至少包含一条建议
        """
        # reason 始终非空
        assert decision.reason
        assert len(decision.reason.strip()) > 0

        if decision.should_replan:
            # should_replan=True → new_question 非空
            assert decision.new_question is not None
            assert len(decision.new_question.strip()) > 0
        else:
            # should_replan=False → suggested_questions 非空
            assert len(decision.suggested_questions) >= 1
            for q in decision.suggested_questions:
                assert len(q.strip()) > 0

    @given(reason=non_empty_text)
    @settings(max_examples=50)
    def test_replan_true_without_question_raises(self, reason: str):
        """should_replan=True 但 new_question 为空时应抛出 ValidationError。"""
        with pytest.raises(ValidationError):
            ReplanDecision(
                should_replan=True,
                reason=reason,
                new_question=None,
                suggested_questions=[],
            )

    @given(reason=non_empty_text)
    @settings(max_examples=50)
    def test_replan_false_without_suggestions_raises(self, reason: str):
        """should_replan=False 但 suggested_questions 为空时应抛出 ValidationError。"""
        with pytest.raises(ValidationError):
            ReplanDecision(
                should_replan=False,
                reason=reason,
                new_question=None,
                suggested_questions=[],
            )

    @given(decision=valid_replan_decision_st)
    @settings(max_examples=100)
    def test_serialization_roundtrip(self, decision: ReplanDecision):
        """序列化往返一致性：model_dump → model_validate 应产生等价实例。"""
        dumped = decision.model_dump()
        restored = ReplanDecision.model_validate(dumped)

        assert restored.should_replan == decision.should_replan
        assert restored.reason == decision.reason
        assert restored.new_question == decision.new_question
        assert restored.suggested_questions == decision.suggested_questions

    @given(
        reason=non_empty_text,
        new_question=non_empty_text,
        extra_field=non_empty_text,
    )
    @settings(max_examples=30)
    def test_extra_fields_forbidden(
        self, reason: str, new_question: str, extra_field: str
    ):
        """extra="forbid" 应拒绝未定义的字段。"""
        with pytest.raises(ValidationError):
            ReplanDecision(
                should_replan=True,
                reason=reason,
                new_question=new_question,
                unexpected_field=extra_field,
            )
