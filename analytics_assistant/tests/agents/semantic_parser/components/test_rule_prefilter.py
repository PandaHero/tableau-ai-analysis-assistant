# -*- coding: utf-8 -*-
"""
RulePrefilter 单元测试
"""

from analytics_assistant.src.agents.semantic_parser.components.rule_prefilter import (
    RulePrefilter,
)
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    ComplexityType,
)


class TestRulePrefilter:
    """RulePrefilter 简单查询误判回归测试。"""

    def test_gross_profit_summary_stays_simple(self):
        """“总销售额和总毛利”不应被识别为派生度量。"""
        prefilter = RulePrefilter()

        result = prefilter.prefilter("总销售额和总毛利分别是多少")

        assert result.detected_complexity == [ComplexityType.SIMPLE]
        assert result.matched_computations == []

    def test_quantity_summary_stays_simple(self):
        """“销售数量汇总”不应被识别为累计表计算。"""
        prefilter = RulePrefilter()

        result = prefilter.prefilter("各部门的销售数量汇总")

        assert result.detected_complexity == [ComplexityType.SIMPLE]
        assert result.matched_computations == []
