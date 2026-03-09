# -*- coding: utf-8 -*-
"""
ComputationMatcher 单元测试

覆盖简单聚合查询中的常见误判场景。
"""

from analytics_assistant.src.agents.semantic_parser.seeds.matchers import (
    ComputationMatcher,
)


class TestComputationMatcher:
    """ComputationMatcher 规则回归测试。"""

    def test_summary_query_does_not_trigger_running_total(self):
        """“汇总”应保留为普通聚合语义，而不是累计表计算。"""
        matcher = ComputationMatcher()

        matched = matcher.find_in_text("各部门的销售数量汇总")

        assert "running_total" not in {seed.name for seed in matched}

    def test_gross_profit_query_does_not_trigger_profit_computation(self):
        """“毛利”优先视为显式度量字段，而不是 revenue-cost 派生计算。"""
        matcher = ComputationMatcher()

        matched = matcher.find_in_text("总销售额和总毛利分别是多少")

        assert "profit" not in {seed.name for seed in matched}

    def test_explicit_running_total_still_matches(self):
        """明确的累计表达仍应命中 running_total。"""
        matcher = ComputationMatcher()

        matched = matcher.find_in_text("各部门累计销售数量")

        assert "running_total" in {seed.name for seed in matched}

    def test_explicit_profit_still_matches(self):
        """明确的利润表达仍应命中 profit 派生计算。"""
        matcher = ComputationMatcher()

        matched = matcher.find_in_text("各地区利润是多少")

        assert "profit" in {seed.name for seed in matched}
