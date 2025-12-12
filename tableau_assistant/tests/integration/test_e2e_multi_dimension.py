# -*- coding: utf-8 -*-
"""
E2E Tests: Multi-Dimension Analysis

Tests the complete workflow for multi-dimension and multi-measure queries.

Requirements: 7.1, 7.2, 7.3
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestMultiDimension:
    """Multi-dimension tests"""
    
    @pytest.mark.asyncio
    async def test_two_dimensions(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test two dimensions query.
        
        Question: 各地区各产品类别的销售额
        Expected: Understanding identifies both dimensions
        
        Requirements: 7.1
        """
        question = "各地区各产品类别的销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
        
        # Verify multiple dimensions
        if result.semantic_query.dimensions:
            dim_names = [d.name for d in result.semantic_query.dimensions]
            print(f"识别到的维度: {dim_names}")
            assert len(dim_names) >= 2, f"应识别至少2个维度，实际: {len(dim_names)}"
    
    @pytest.mark.asyncio
    async def test_three_dimensions(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test three dimensions query.
        
        Question: 各地区各产品类别各年份的销售额
        
        Requirements: 7.1
        """
        question = "各地区各产品类别各年份的销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestMultiMeasure:
    """Multi-measure tests"""
    
    @pytest.mark.asyncio
    async def test_two_measures(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test two measures query.
        
        Question: 各地区的销售额和利润
        Expected: Understanding identifies both measures
        
        Requirements: 7.2
        """
        question = "各地区的销售额和利润"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
        
        # Verify multiple measures
        if result.semantic_query.measures:
            measure_names = [m.name for m in result.semantic_query.measures]
            print(f"识别到的度量: {measure_names}")
            assert len(measure_names) >= 2, f"应识别至少2个度量，实际: {len(measure_names)}"
    
    @pytest.mark.asyncio
    async def test_three_measures(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test three measures query.
        
        Question: 各地区的销售额、利润和数量
        
        Requirements: 7.2
        """
        question = "各地区的销售额、利润和数量"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestMultiDimensionMultiMeasure:
    """Multi-dimension and multi-measure combined tests"""
    
    @pytest.mark.asyncio
    async def test_multi_dim_multi_measure(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test multi-dimension and multi-measure query.
        
        Question: 各地区各产品类别的销售额和利润
        Expected: Understanding identifies all dimensions and measures
        
        Requirements: 7.3
        """
        question = "各地区各产品类别的销售额和利润"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
        
        # Verify dimensions and measures
        if result.semantic_query.dimensions:
            dim_names = [d.name for d in result.semantic_query.dimensions]
            print(f"识别到的维度: {dim_names}")
        
        if result.semantic_query.measures:
            measure_names = [m.name for m in result.semantic_query.measures]
            print(f"识别到的度量: {measure_names}")


class TestMultiDimensionProperties:
    """Property-based tests for multi-dimension recognition"""
    
    # **Feature: workflow-e2e-testing, Property 8: 多维度多度量识别**
    # **Validates: Requirements 7.1, 7.2**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=5, deadline=120000)
    @given(
        dim1=st.sampled_from(["地区", "产品类别", "客户"]),
        dim2=st.sampled_from(["年份", "月份", "季度"]),
        measure1=st.sampled_from(["销售额", "利润"]),
        measure2=st.sampled_from(["数量", "折扣"]),
    )
    async def test_property_multi_dim_measure_recognition(
        self,
        dim1: str,
        dim2: str,
        measure1: str,
        measure2: str,
        check_env,
    ):
        """
        Property 8: Multi-dimension and multi-measure should be recognized.
        
        For any question containing multiple dimensions or measures,
        Understanding Agent should identify all of them.
        
        **Feature: workflow-e2e-testing, Property 8: 多维度多度量识别**
        **Validates: Requirements 7.1, 7.2**
        """
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=True)
        question = f"各{dim1}各{dim2}的{measure1}和{measure2}"
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}, 错误: {result.error}"
        assert result.semantic_query is not None
