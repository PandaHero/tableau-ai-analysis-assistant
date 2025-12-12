# -*- coding: utf-8 -*-
"""
E2E Tests: Insight-Query Linkage

Tests how insights drive subsequent query optimization including:
- Insight-driven drilldown
- Anomaly-driven analysis
- Pareto-driven top N
- Trend-driven analysis

Requirements: 30.1, 30.2, 30.3, 30.4, 32.1, 32.2, 32.3, 32.4
"""

import pytest

from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestInsightDrivenDrilldown:
    """Insight-driven drilldown tests"""
    
    @pytest.mark.asyncio
    async def test_insight_driven_drilldown(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test insight-driven drilldown.
        
        Question: 分析各地区销售情况，找出需要关注的区域
        Expected: Insights drive subsequent drilldown queries
        
        Requirements: 30.1, 32.1
        """
        question = "分析各地区销售情况，找出需要关注的区域"
        
        print("\n=== 洞察驱动下钻测试 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Check insights
        print(f"\n生成的洞察数量: {len(result.insights)}")
        for i, insight in enumerate(result.insights[:3]):
            print(f"  {i+1}. {insight}")
    
    @pytest.mark.asyncio
    async def test_insight_driven_focus(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test insight-driven focus on specific areas.
        
        Question: 分析销售数据，找出表现最好和最差的产品
        
        Requirements: 30.2, 32.2
        """
        question = "分析销售数据，找出表现最好和最差的产品"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestAnomalyDrivenAnalysis:
    """Anomaly-driven analysis tests"""
    
    @pytest.mark.asyncio
    async def test_anomaly_driven_analysis(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test anomaly-driven analysis.
        
        Question: 分析销售数据，找出异常情况
        Expected: Anomalies drive deeper analysis
        
        Requirements: 30.2, 32.2
        """
        question = "分析销售数据，找出异常情况"
        
        print("\n=== 异常驱动分析测试 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_outlier_detection(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test outlier detection in analysis.
        
        Question: 找出销售额异常高或异常低的地区
        
        Requirements: 30.2
        """
        question = "找出销售额异常高或异常低的地区"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestParetoDrivenTopN:
    """Pareto-driven top N analysis tests"""
    
    @pytest.mark.asyncio
    async def test_pareto_driven_top_n(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test Pareto-driven top N analysis.
        
        Question: 找出贡献80%销售额的产品
        Expected: Pareto analysis drives focus on top contributors
        
        Requirements: 30.3, 32.3
        """
        question = "找出贡献80%销售额的产品"
        
        print("\n=== 帕累托驱动Top N测试 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_top_n_analysis(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test top N analysis.
        
        Question: 销售额前10的产品是哪些
        
        Requirements: 30.3
        """
        question = "销售额前10的产品是哪些"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_bottom_n_analysis(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test bottom N analysis.
        
        Question: 销售额最低的5个地区
        
        Requirements: 30.3
        """
        question = "销售额最低的5个地区"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestTrendDrivenAnalysis:
    """Trend-driven analysis tests"""
    
    @pytest.mark.asyncio
    async def test_trend_driven_analysis(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test trend-driven analysis.
        
        Question: 分析销售趋势，找出增长和下降的时期
        Expected: Trend insights drive temporal analysis
        
        Requirements: 30.4, 32.4
        """
        question = "分析销售趋势，找出增长和下降的时期"
        
        print("\n=== 趋势驱动分析测试 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_growth_analysis(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test growth analysis.
        
        Question: 哪些产品类别增长最快
        
        Requirements: 30.4
        """
        question = "哪些产品类别增长最快"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_decline_analysis(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test decline analysis.
        
        Question: 哪些地区销售在下降
        
        Requirements: 30.4
        """
        question = "哪些地区销售在下降"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestInsightQueryOptimization:
    """Insight-query optimization tests"""
    
    @pytest.mark.asyncio
    async def test_insight_optimizes_next_query(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test insights optimize subsequent queries.
        
        Expected: Replanner uses insights to generate better follow-up questions
        
        Requirements: 32.1, 32.2, 32.3, 32.4
        """
        question = "全面分析销售数据，给出改进建议"
        
        print("\n=== 洞察优化查询测试 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Check if replan decision has exploration questions
        if result.replan_decision and hasattr(result.replan_decision, 'exploration_questions'):
            print(f"\n探索问题: {result.replan_decision.exploration_questions}")
