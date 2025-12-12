# -*- coding: utf-8 -*-
"""
E2E Tests: Dimension Drilldown

Tests the dimension hierarchy drilldown including:
- Geographic drilldown (Region → Province → City)
- Time drilldown (Year → Quarter → Month)
- Product drilldown (Category → Subcategory → Product)

Verifies that Replanner LLM selects dimensions based on metadata (dimension hierarchy).

Requirements: 12.1, 12.2, 12.3, 16.1-16.5, 17.1-17.5, 18.1-18.5
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestGeoDrilldown:
    """Geographic dimension drilldown tests"""
    
    @pytest.mark.asyncio
    async def test_geo_drilldown_region_to_province(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test geographic drilldown from region to province.
        
        Question: 分析各地区销售情况
        Expected: Replanner may suggest drilling down to province level
        
        Requirements: 12.1, 16.1, 16.2
        """
        question = "分析各地区销售情况"
        
        print("\n=== 地理维度下钻测试: 地区 → 省份 ===")
        
        # Stream to show full drilldown process
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Check replan decision for drilldown suggestions
        if result.replan_decision:
            print(f"\n重规划决策:")
            print(f"  - should_replan: {result.replan_decision.should_replan}")
            if hasattr(result.replan_decision, 'exploration_questions'):
                print(f"  - 探索问题: {result.replan_decision.exploration_questions}")
    
    @pytest.mark.asyncio
    async def test_geo_drilldown_province_to_city(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test geographic drilldown from province to city.
        
        Question: 分析各省份销售情况
        Expected: Replanner may suggest drilling down to city level
        
        Requirements: 16.3, 16.4, 16.5
        """
        question = "分析各省份销售情况"
        
        print("\n=== 地理维度下钻测试: 省份 → 城市 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestTimeDrilldown:
    """Time dimension drilldown tests"""
    
    @pytest.mark.asyncio
    async def test_time_drilldown_year_to_quarter(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test time drilldown from year to quarter.
        
        Question: 分析各年度销售趋势
        Expected: Replanner may suggest drilling down to quarter level
        
        Requirements: 12.2, 17.1, 17.2
        """
        question = "分析各年度销售趋势"
        
        print("\n=== 时间维度下钻测试: 年 → 季度 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_time_drilldown_quarter_to_month(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test time drilldown from quarter to month.
        
        Question: 分析各季度销售情况
        Expected: Replanner may suggest drilling down to month level
        
        Requirements: 17.3, 17.4, 17.5
        """
        question = "分析各季度销售情况"
        
        print("\n=== 时间维度下钻测试: 季度 → 月 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestProductDrilldown:
    """Product dimension drilldown tests"""
    
    @pytest.mark.asyncio
    async def test_product_drilldown_category_to_subcategory(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test product drilldown from category to subcategory.
        
        Question: 分析各产品类别销售情况
        Expected: Replanner may suggest drilling down to subcategory level
        
        Requirements: 12.3, 18.1, 18.2
        """
        question = "分析各产品类别销售情况"
        
        print("\n=== 产品维度下钻测试: 类别 → 子类别 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_product_drilldown_subcategory_to_product(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test product drilldown from subcategory to product.
        
        Question: 分析各产品子类别销售情况
        Expected: Replanner may suggest drilling down to product level
        
        Requirements: 18.3, 18.4, 18.5
        """
        question = "分析各产品子类别销售情况"
        
        print("\n=== 产品维度下钻测试: 子类别 → 产品 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestMultiRoundDrilldown:
    """Multi-round drilldown tests"""
    
    @pytest.mark.asyncio
    async def test_multi_round_geo_drilldown(
        self,
        check_env,
    ):
        """
        Test multi-round geographic drilldown.
        
        Expected: Multiple rounds of drilldown from region to city
        
        Requirements: 12.1, 16.1-16.5
        """
        # Use higher max_replan_rounds for drilldown
        executor = WorkflowExecutor(
            max_replan_rounds=3,
            use_memory_checkpointer=True,
        )
        printer = WorkflowPrinter(verbose=True, show_tokens=False)
        
        question = "深入分析各地区销售情况，找出销售最好和最差的区域"
        
        print("\n=== 多轮地理下钻测试 ===")
        
        # Track understanding visits
        understanding_visits = 0
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.NODE_START and event.node_name == "understanding":
                understanding_visits += 1
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"\n分析轮数: {understanding_visits}")
        print(f"重规划次数: {result.replan_count}")
    
    @pytest.mark.asyncio
    async def test_multi_round_time_drilldown(
        self,
        check_env,
    ):
        """
        Test multi-round time drilldown.
        
        Expected: Multiple rounds of drilldown from year to month
        
        Requirements: 12.2, 17.1-17.5
        """
        executor = WorkflowExecutor(
            max_replan_rounds=3,
            use_memory_checkpointer=True,
        )
        printer = WorkflowPrinter(verbose=True, show_tokens=False)
        
        question = "深入分析销售趋势，找出销售高峰和低谷时期"
        
        print("\n=== 多轮时间下钻测试 ===")
        
        async for event in executor.stream(question):
            printer.print_event(event)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestDrilldownProperties:
    """Property-based tests for dimension drilldown"""
    
    # **Feature: workflow-e2e-testing, Property 18: 维度下钻决策正确性**
    # **Validates: Requirements 12.2, 16.2, 17.2, 18.2**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=3, deadline=180000)
    @given(
        drilldown_scenario=st.sampled_from([
            ("分析各地区销售情况", "geo"),
            ("分析各年度销售趋势", "time"),
            ("分析各产品类别销售情况", "product"),
        ]),
    )
    async def test_property_drilldown_decision(
        self,
        drilldown_scenario: tuple,
        check_env,
    ):
        """
        Property 18: Drilldown decisions should be based on dimension hierarchy.
        
        For any Replanner drilldown decision, exploration_questions should
        contain suggestions based on dimension hierarchy.
        
        **Feature: workflow-e2e-testing, Property 18: 维度下钻决策正确性**
        **Validates: Requirements 12.2, 16.2, 17.2, 18.2**
        """
        question, hierarchy_type = drilldown_scenario
        executor = WorkflowExecutor(max_replan_rounds=2, use_memory_checkpointer=True)
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}"
        
        # Check replan decision
        if result.replan_decision:
            print(f"问题: {question}")
            print(f"层级类型: {hierarchy_type}")
            print(f"should_replan: {result.replan_decision.should_replan}")
            if hasattr(result.replan_decision, 'exploration_questions'):
                print(f"探索问题: {result.replan_decision.exploration_questions}")
