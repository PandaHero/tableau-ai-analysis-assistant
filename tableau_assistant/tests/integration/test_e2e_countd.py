# -*- coding: utf-8 -*-
"""
E2E Tests: COUNTD (Distinct Count)

Tests the complete workflow for COUNTD distinct counting queries.

Requirements: 2.1, 2.2, 2.3
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestCountdDistinct:
    """COUNTD distinct counting tests"""
    
    @pytest.mark.asyncio
    async def test_countd_distinct_customers_by_region(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test COUNTD for distinct customers by region.
        
        Question: 各地区有多少不同的客户
        Expected: Understanding identifies COUNTD aggregation
        
        Requirements: 2.1, 2.2
        """
        question = "各地区有多少不同的客户"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
        
        # Verify COUNTD recognition
        if result.semantic_query.measures:
            for measure in result.semantic_query.measures:
                agg_type = getattr(measure, 'aggregation', None)
                print(f"度量: {measure.name}, 聚合类型: {agg_type}")
    
    @pytest.mark.asyncio
    async def test_countd_distinct_products_by_category(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test COUNTD for distinct products by category.
        
        Question: 各类别有多少种不同的产品
        
        Requirements: 2.1, 2.2
        """
        question = "各类别有多少种不同的产品"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_countd_unique_orders_by_customer(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test COUNTD for unique orders by customer.
        
        Question: 每个客户有多少个不重复的订单
        
        Requirements: 2.1, 2.3
        """
        question = "每个客户有多少个不重复的订单"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
    
    @pytest.mark.asyncio
    async def test_countd_with_dedup_keyword(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test COUNTD with '去重' keyword.
        
        Question: 各地区去重后的客户数量
        
        Requirements: 2.1, 2.2
        """
        question = "各地区去重后的客户数量"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestCountdProperties:
    """Property-based tests for COUNTD recognition"""
    
    # **Feature: workflow-e2e-testing, Property 3: COUNTD 聚合识别**
    # **Validates: Requirements 2.1, 2.2**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=5, deadline=120000)
    @given(
        distinct_keyword=st.sampled_from(["不同的", "不重复的", "去重", "唯一的", "独立的"]),
        entity=st.sampled_from(["客户", "产品", "订单", "供应商"]),
        dimension=st.sampled_from(["地区", "类别", "省份", "年份"]),
    )
    async def test_property_countd_recognition(
        self,
        distinct_keyword: str,
        entity: str,
        dimension: str,
        check_env,
    ):
        """
        Property 3: COUNTD should be recognized for distinct counting.
        
        For any question containing distinct keywords ('不同', '去重'),
        Understanding Agent should identify COUNTD aggregation type.
        
        **Feature: workflow-e2e-testing, Property 3: COUNTD 聚合识别**
        **Validates: Requirements 2.1, 2.2**
        """
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=True)
        question = f"各{dimension}有多少{distinct_keyword}{entity}"
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}, 错误: {result.error}"
        assert result.semantic_query is not None, f"SemanticQuery 为空: {question}"
