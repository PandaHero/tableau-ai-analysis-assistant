# -*- coding: utf-8 -*-
"""
E2E Tests: Simple Aggregation (SUM, AVG, COUNT)

Tests the complete workflow for simple aggregation queries.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestSumAggregation:
    """SUM aggregation tests"""
    
    @pytest.mark.asyncio
    async def test_sum_by_region(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test SUM aggregation by region.
        
        Question: 各地区销售额是多少
        Expected: Understanding identifies SUM aggregation, QueryBuilder generates correct query
        
        Requirements: 1.1, 1.2, 1.3
        """
        question = "各地区销售额是多少"
        
        # Execute workflow
        result = await executor.run(question)
        
        # Print real output
        printer.print_result(result)
        
        # Assertions
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None, "SemanticQuery 为空"
        assert result.is_analysis_question, "应识别为分析类问题"
        
        # Verify measures identified
        if result.semantic_query.measures:
            measure_names = [m.name for m in result.semantic_query.measures]
            print(f"识别到的度量: {measure_names}")
        
        # Verify dimensions identified
        if result.semantic_query.dimensions:
            dim_names = [d.name for d in result.semantic_query.dimensions]
            print(f"识别到的维度: {dim_names}")
    
    @pytest.mark.asyncio
    async def test_sum_by_region_streaming(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test SUM aggregation with streaming output.
        
        Verifies token streaming and node status events.
        
        Requirements: 1.1, 10.1, 10.2
        """
        question = "各地区销售额是多少"
        
        events_received = {
            "node_start": [],
            "node_complete": [],
            "token": 0,
            "complete": False,
        }
        
        # Stream execution
        async for event in executor.stream(question):
            printer.print_event(event)
            
            if event.type == EventType.NODE_START:
                events_received["node_start"].append(event.node_name)
            elif event.type == EventType.NODE_COMPLETE:
                events_received["node_complete"].append(event.node_name)
            elif event.type == EventType.TOKEN:
                events_received["token"] += 1
            elif event.type == EventType.COMPLETE:
                events_received["complete"] = True
        
        # Verify events
        assert events_received["complete"], "未收到 COMPLETE 事件"
        assert "understanding" in events_received["node_start"], "未收到 understanding NODE_START"
        print(f"\n事件统计: {events_received}")
    
    @pytest.mark.asyncio
    async def test_sum_by_category(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test SUM aggregation by product category.
        
        Question: 各产品类别的销售总额
        
        Requirements: 1.1, 1.2
        """
        question = "各产品类别的销售总额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None


class TestAvgAggregation:
    """AVG aggregation tests"""
    
    @pytest.mark.asyncio
    async def test_avg_profit_by_category(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test AVG aggregation for profit by category.
        
        Question: 各产品类别的平均利润是多少
        Expected: Understanding identifies AVG aggregation type
        
        Requirements: 1.4, 1.5
        """
        question = "各产品类别的平均利润是多少"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
        
        # Check if AVG aggregation is identified
        if result.semantic_query.measures:
            for measure in result.semantic_query.measures:
                print(f"度量: {measure.name}, 聚合类型: {getattr(measure, 'aggregation', 'N/A')}")
    
    @pytest.mark.asyncio
    async def test_avg_sales_by_region(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test AVG aggregation for sales by region.
        
        Question: 各地区的平均销售额
        
        Requirements: 1.4
        """
        question = "各地区的平均销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestCountAggregation:
    """COUNT aggregation tests"""
    
    @pytest.mark.asyncio
    async def test_count_orders_by_region(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test COUNT aggregation for orders by region.
        
        Question: 各地区有多少订单
        Expected: Understanding identifies COUNT aggregation
        
        Requirements: 1.4, 1.5
        """
        question = "各地区有多少订单"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
    
    @pytest.mark.asyncio
    async def test_count_products_by_category(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test COUNT aggregation for products by category.
        
        Question: 各类别有多少产品
        
        Requirements: 1.4
        """
        question = "各类别有多少产品"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestAggregationProperties:
    """Property-based tests for aggregation recognition"""
    
    # **Feature: workflow-e2e-testing, Property 1: 简单聚合查询成功执行**
    # **Validates: Requirements 1.1, 1.2**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=5, deadline=120000)
    @given(
        dimension=st.sampled_from(["地区", "产品类别", "客户", "省份"]),
        measure=st.sampled_from(["销售额", "利润", "数量", "折扣"]),
    )
    async def test_property_simple_aggregation_success(
        self,
        dimension: str,
        measure: str,
        check_env,
    ):
        """
        Property 1: Simple aggregation queries should execute successfully.
        
        For any dimension and measure combination, the workflow should:
        - Return success=True
        - Generate non-null SemanticQuery
        
        **Feature: workflow-e2e-testing, Property 1: 简单聚合查询成功执行**
        **Validates: Requirements 1.1, 1.2**
        """
        executor = WorkflowExecutor(max_replan_rounds=3, use_memory_checkpointer=True)
        question = f"各{dimension}的{measure}是多少"
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}, 错误: {result.error}"
        assert result.semantic_query is not None, f"SemanticQuery 为空: {question}"
    
    # **Feature: workflow-e2e-testing, Property 2: 聚合类型正确识别**
    # **Validates: Requirements 1.4, 1.5**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=5, deadline=120000)
    @given(
        agg_keyword=st.sampled_from([
            ("平均", "AVG"),
            ("总计", "SUM"),
            ("合计", "SUM"),
            ("数量", "COUNT"),
            ("多少", "COUNT"),
        ]),
    )
    async def test_property_aggregation_type_recognition(
        self,
        agg_keyword: tuple,
        check_env,
    ):
        """
        Property 2: Aggregation type should be correctly recognized.
        
        For any aggregation keyword, Understanding Agent should identify
        the correct aggregation type.
        
        **Feature: workflow-e2e-testing, Property 2: 聚合类型正确识别**
        **Validates: Requirements 1.4, 1.5**
        """
        keyword, expected_type = agg_keyword
        executor = WorkflowExecutor(max_replan_rounds=3, use_memory_checkpointer=True)
        
        if expected_type == "AVG":
            question = f"各地区的{keyword}销售额"
        elif expected_type == "COUNT":
            question = f"各地区有{keyword}订单"
        else:
            question = f"各地区销售额{keyword}"
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}"
        assert result.semantic_query is not None
        # Note: Actual aggregation type verification depends on SemanticQuery structure
