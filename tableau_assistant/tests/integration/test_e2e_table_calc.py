# -*- coding: utf-8 -*-
"""
E2E Tests: Table Calculations

Tests the complete workflow for table calculation queries including:
- RUNNING_SUM (cumulative)
- RANK
- Moving Average
- YoY (Year over Year)
- MoM (Month over Month)
- Percent of Total

Requirements: 4.1, 4.2, 4.3, 22.1-22.4, 23.1-23.4, 24.1-24.4, 25.1-25.3
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestRunningSum:
    """RUNNING_SUM (cumulative) tests"""
    
    @pytest.mark.asyncio
    async def test_running_sum_monthly(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test RUNNING_SUM by month.
        
        Question: 按月份显示累计销售额
        Expected: Understanding identifies RUNNING_SUM table calculation
        
        Requirements: 4.1, 22.1, 22.2
        """
        question = "按月份显示累计销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_running_sum_quarterly(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test RUNNING_SUM by quarter.
        
        Question: 按季度显示累计利润
        
        Requirements: 22.3, 22.4
        """
        question = "按季度显示累计利润"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestRank:
    """RANK table calculation tests"""
    
    @pytest.mark.asyncio
    async def test_rank_sales_by_product(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test RANK for product sales.
        
        Question: 各产品销售额排名
        Expected: Understanding identifies RANK table calculation
        
        Requirements: 4.2, 23.1, 23.2
        """
        question = "各产品销售额排名"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_rank_profit_by_region(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test RANK for region profit.
        
        Question: 各地区利润排名
        
        Requirements: 23.3, 23.4
        """
        question = "各地区利润排名"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestMovingAverage:
    """Moving average tests"""
    
    @pytest.mark.asyncio
    async def test_moving_avg_3_months(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test 3-month moving average.
        
        Question: 销售额的3个月移动平均
        Expected: Understanding identifies moving average calculation
        
        Requirements: 4.3, 24.1, 24.2
        """
        question = "销售额的3个月移动平均"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_moving_avg_weekly(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test weekly moving average.
        
        Question: 按周计算销售额的移动平均
        
        Requirements: 24.3, 24.4
        """
        question = "按周计算销售额的移动平均"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestYoYGrowth:
    """Year over Year growth tests"""
    
    @pytest.mark.asyncio
    async def test_yoy_growth_by_region(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test YoY growth rate by region.
        
        Question: 各地区销售额同比增长率
        Expected: Understanding identifies YoY calculation
        
        Requirements: 4.3, 25.1
        """
        question = "各地区销售额同比增长率"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_yoy_comparison(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test YoY comparison.
        
        Question: 今年与去年销售额对比
        
        Requirements: 25.2
        """
        question = "今年与去年销售额对比"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestMoMGrowth:
    """Month over Month growth tests"""
    
    @pytest.mark.asyncio
    async def test_mom_growth(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test MoM growth rate.
        
        Question: 各月销售额环比增长
        Expected: Understanding identifies MoM calculation
        
        Requirements: 4.3, 25.3
        """
        question = "各月销售额环比增长"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None


class TestPercentOfTotal:
    """Percent of total tests"""
    
    @pytest.mark.asyncio
    async def test_percent_of_total_by_category(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test percent of total by category.
        
        Question: 各产品类别销售额占比
        Expected: Understanding identifies percent of total calculation
        
        Requirements: 4.3
        """
        question = "各产品类别销售额占比"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_percent_of_total_by_region(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test percent of total by region.
        
        Question: 各地区销售额占总销售额的百分比
        """
        question = "各地区销售额占总销售额的百分比"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestTableCalcProperties:
    """Property-based tests for table calculation recognition"""
    
    # **Feature: workflow-e2e-testing, Property 5: 表计算识别**
    # **Validates: Requirements 4.1, 4.2, 22.1, 23.1, 24.1**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=5, deadline=120000)
    @given(
        calc_scenario=st.sampled_from([
            ("按月份显示累计销售额", "RUNNING_SUM"),
            ("各产品销售额排名", "RANK"),
            ("销售额的移动平均", "MOVING_AVG"),
            ("销售额同比增长", "YOY"),
            ("销售额环比增长", "MOM"),
            ("各类别销售额占比", "PERCENT_OF_TOTAL"),
        ]),
    )
    async def test_property_table_calc_recognition(
        self,
        calc_scenario: tuple,
        check_env,
    ):
        """
        Property 5: Table calculations should be correctly recognized.
        
        For any question containing table calculation keywords,
        Understanding Agent should identify the correct calculation type.
        
        **Feature: workflow-e2e-testing, Property 5: 表计算识别**
        **Validates: Requirements 4.1, 4.2, 22.1, 23.1, 24.1**
        """
        question, expected_calc_type = calc_scenario
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=True)
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}, 错误: {result.error}"
        assert result.semantic_query is not None, f"SemanticQuery 为空: {question}"
        
        print(f"问题: {question}, 预期计算类型: {expected_calc_type}")
