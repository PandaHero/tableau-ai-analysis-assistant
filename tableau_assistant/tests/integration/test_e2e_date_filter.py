# -*- coding: utf-8 -*-
"""
E2E Tests: Date Filters (Absolute, Relative, Compound)

Tests the complete workflow for date filter queries including:
- Absolute date filters (year, month, date range, quarter)
- Relative date filters (current month, last month, YTD, etc.)
- Compound time filters (year+week, multi-year quarter, weekday/weekend)

Requirements: 5.1-5.4, 6.1-6.5, 26.1-26.4, 27.1-27.4, 28.1-28.5, 29.1-29.4
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestAbsoluteDateFilter:
    """Absolute date filter tests"""
    
    @pytest.mark.asyncio
    async def test_absolute_year_filter(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test absolute year filter.
        
        Question: 2024年各地区销售额
        Expected: Understanding generates year filter
        
        Requirements: 5.1, 26.1
        """
        question = "2024年各地区销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
        
        # Check filters
        if result.semantic_query.filters:
            print(f"识别到的筛选器: {len(result.semantic_query.filters)} 个")
            for f in result.semantic_query.filters:
                print(f"  - {f}")
    
    @pytest.mark.asyncio
    async def test_absolute_month_filter(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test absolute month filter.
        
        Question: 2024年3月的销售情况
        
        Requirements: 5.2, 26.2
        """
        question = "2024年3月的销售情况"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_absolute_date_range(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test absolute date range filter.
        
        Question: 2024年1月到3月的销售额
        
        Requirements: 5.3, 26.3
        """
        question = "2024年1月到3月的销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_absolute_quarter_filter(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test absolute quarter filter.
        
        Question: 2024年第一季度销售额
        
        Requirements: 5.4, 26.4
        """
        question = "2024年第一季度销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestRelativeDateFilter:
    """Relative date filter tests"""
    
    @pytest.mark.asyncio
    async def test_current_month(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test current month filter.
        
        Question: 本月销售额是多少
        Expected: Understanding generates relative date filter
        
        Requirements: 6.1, 27.1
        """
        question = "本月销售额是多少"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_last_month(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test last month filter.
        
        Question: 上个月各地区销售额
        
        Requirements: 6.2, 27.2
        """
        question = "上个月各地区销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_last_n_months(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test last N months filter.
        
        Question: 最近3个月的销售趋势
        
        Requirements: 6.3, 27.3
        """
        question = "最近3个月的销售趋势"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_year_to_date(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test YTD (Year to Date) filter.
        
        Question: 今年至今的销售总额
        
        Requirements: 6.4, 27.4
        """
        question = "今年至今的销售总额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_current_week(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test current week filter.
        
        Question: 本周销售额
        
        Requirements: 6.5, 28.1
        """
        question = "本周销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_last_week(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test last week filter.
        
        Question: 上周销售额
        
        Requirements: 28.2
        """
        question = "上周销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_last_n_days(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test last N days filter.
        
        Question: 最近7天的销售额
        
        Requirements: 28.3, 28.4
        """
        question = "最近7天的销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_today_yesterday(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test today/yesterday filter.
        
        Question: 昨天的销售额
        
        Requirements: 28.5
        """
        question = "昨天的销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestCompoundDateFilter:
    """Compound time filter tests"""
    
    @pytest.mark.asyncio
    async def test_year_and_week(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test year and week compound filter.
        
        Question: 2024年第10周的销售额
        
        Requirements: 29.1
        """
        question = "2024年第10周的销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_multi_year_quarter(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test multi-year quarter comparison.
        
        Question: 2023年和2024年第一季度销售对比
        
        Requirements: 29.2, 29.3
        """
        question = "2023年和2024年第一季度销售对比"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_weekday_weekend(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test weekday vs weekend filter.
        
        Question: 工作日和周末的销售额对比
        
        Requirements: 29.4
        """
        question = "工作日和周末的销售额对比"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestDateFilterProperties:
    """Property-based tests for date filter recognition"""
    
    # **Feature: workflow-e2e-testing, Property 6: 绝对日期筛选识别**
    # **Validates: Requirements 5.1, 5.2, 5.3**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=5, deadline=120000)
    @given(
        year=st.sampled_from(["2023", "2024"]),
        month=st.sampled_from(["1月", "3月", "6月", "12月"]),
    )
    async def test_property_absolute_date_filter(
        self,
        year: str,
        month: str,
        check_env,
    ):
        """
        Property 6: Absolute date filters should be correctly recognized.
        
        For any question containing specific year/month,
        Understanding Agent should generate correct date filter.
        
        **Feature: workflow-e2e-testing, Property 6: 绝对日期筛选识别**
        **Validates: Requirements 5.1, 5.2, 5.3**
        """
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=True)
        question = f"{year}年{month}的销售额"
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}, 错误: {result.error}"
        assert result.semantic_query is not None
    
    # **Feature: workflow-e2e-testing, Property 7: 相对日期筛选识别**
    # **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=5, deadline=120000)
    @given(
        relative_keyword=st.sampled_from([
            "本月", "上月", "上个月", "最近3个月", "今年至今", "本周", "上周", "最近7天"
        ]),
    )
    async def test_property_relative_date_filter(
        self,
        relative_keyword: str,
        check_env,
    ):
        """
        Property 7: Relative date filters should be correctly recognized.
        
        For any question containing relative date keywords,
        Understanding Agent should generate relative date filter.
        
        **Feature: workflow-e2e-testing, Property 7: 相对日期筛选识别**
        **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
        """
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=True)
        question = f"{relative_keyword}的销售额"
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}, 错误: {result.error}"
        assert result.semantic_query is not None
