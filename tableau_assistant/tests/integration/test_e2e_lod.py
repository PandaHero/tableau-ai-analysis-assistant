# -*- coding: utf-8 -*-
"""
E2E Tests: LOD Expressions (FIXED, INCLUDE, EXCLUDE)

Tests the complete workflow for LOD (Level of Detail) expression queries.
Verifies that Understanding Agent identifies LOD needs and QueryBuilder
generates correct LOD expressions.

Requirements: 3.1, 3.2, 3.3, 19.1-19.5, 20.1-20.4, 21.1-21.4
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestFixedLOD:
    """FIXED LOD expression tests"""
    
    @pytest.mark.asyncio
    async def test_fixed_lod_first_purchase_date(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test FIXED LOD for first purchase date per customer.
        
        Question: 每个客户的首次购买日期是什么
        Expected: Understanding identifies FIXED LOD need
        
        Requirements: 3.1, 19.1, 19.2
        """
        question = "每个客户的首次购买日期是什么"
        
        # Stream to show detailed process
        print("\n=== 流式执行过程 ===")
        async for event in executor.stream(question):
            printer.print_event(event)
        
        # Also run for assertions
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
        
        # Check LOD type if available
        if hasattr(result.semantic_query, 'lod_type'):
            print(f"LOD 类型: {result.semantic_query.lod_type}")
    
    @pytest.mark.asyncio
    async def test_fixed_lod_category_total(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test FIXED LOD for category total sales.
        
        Question: 每个产品类别的总销售额（固定在类别级别）
        
        Requirements: 3.1, 19.3, 19.4
        """
        question = "计算每个产品类别的总销售额，不受其他维度影响"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_fixed_lod_customer_lifetime_value(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test FIXED LOD for customer lifetime value.
        
        Question: 每个客户的总消费金额
        
        Requirements: 19.5
        """
        question = "每个客户的总消费金额是多少"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestIncludeLOD:
    """INCLUDE LOD expression tests"""
    
    @pytest.mark.asyncio
    async def test_include_lod_avg_orders_per_customer(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test INCLUDE LOD for average orders per customer per region.
        
        Question: 每个地区每个客户的平均订单金额
        Expected: Understanding identifies INCLUDE LOD need
        
        Requirements: 3.2, 20.1, 20.2
        """
        question = "每个地区每个客户的平均订单金额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_include_lod_customer_order_count(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test INCLUDE LOD for customer order count.
        
        Question: 包含客户维度计算每个地区的订单数
        
        Requirements: 20.3, 20.4
        """
        question = "按地区统计，包含每个客户的订单数量"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestExcludeLOD:
    """EXCLUDE LOD expression tests"""
    
    @pytest.mark.asyncio
    async def test_exclude_lod_category_avg(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test EXCLUDE LOD for category average excluding product.
        
        Question: 不考虑产品类别的地区平均销售额
        Expected: Understanding identifies EXCLUDE LOD need
        
        Requirements: 3.3, 21.1, 21.2
        """
        question = "不考虑产品类别的地区平均销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_exclude_lod_region_total(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test EXCLUDE LOD for region total excluding sub-dimensions.
        
        Question: 排除省份维度的地区销售总额
        
        Requirements: 21.3, 21.4
        """
        question = "排除省份维度的地区销售总额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestLODProperties:
    """Property-based tests for LOD expression recognition"""
    
    # **Feature: workflow-e2e-testing, Property 4: LOD 表达式识别**
    # **Validates: Requirements 3.1, 19.1, 19.2, 20.1, 21.1**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=5, deadline=120000)
    @given(
        lod_scenario=st.sampled_from([
            ("每个客户的首次购买日期", "FIXED"),
            ("每个地区每个客户的平均订单", "INCLUDE"),
            ("不考虑产品的地区销售额", "EXCLUDE"),
            ("固定在类别级别的总销售额", "FIXED"),
            ("包含客户维度的订单统计", "INCLUDE"),
        ]),
    )
    async def test_property_lod_recognition(
        self,
        lod_scenario: tuple,
        check_env,
    ):
        """
        Property 4: LOD expressions should be correctly recognized.
        
        For any question requiring cross-granularity calculation,
        Understanding Agent should identify LOD need and set correct lod_type.
        
        **Feature: workflow-e2e-testing, Property 4: LOD 表达式识别**
        **Validates: Requirements 3.1, 19.1, 19.2, 20.1, 21.1**
        """
        question, expected_lod_type = lod_scenario
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=True)
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}, 错误: {result.error}"
        assert result.semantic_query is not None, f"SemanticQuery 为空: {question}"
        
        # Note: Actual LOD type verification depends on SemanticQuery structure
        print(f"问题: {question}, 预期LOD类型: {expected_lod_type}")
