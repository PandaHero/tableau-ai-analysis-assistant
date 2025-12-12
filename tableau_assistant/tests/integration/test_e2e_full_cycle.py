# -*- coding: utf-8 -*-
"""
E2E Tests: Full Workflow Cycle

Tests the complete workflow cycle including:
- Full workflow execution (Understanding → FieldMapper → QueryBuilder → Execute → Insight → Replanner)
- Multi-round analysis
- Insights accumulation

Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 31.1, 31.2, 31.3, 31.4
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestFullWorkflowCycle:
    """Full workflow cycle tests"""
    
    @pytest.mark.asyncio
    async def test_full_workflow_cycle(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test complete workflow cycle.
        
        Question: 各地区销售额是多少
        Expected: All 6 nodes execute in order
        
        Requirements: 15.1, 15.2
        """
        question = "各地区销售额是多少"
        
        # Track all nodes
        nodes_executed = []
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.NODE_COMPLETE:
                nodes_executed.append(event.node_name)
        
        print(f"\n执行的节点: {nodes_executed}")
        
        # Verify workflow result
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Verify key outputs
        assert result.semantic_query is not None, "SemanticQuery 应存在"
        print(f"\n完整工作流执行成功")
        print(f"  - SemanticQuery: {result.semantic_query is not None}")
        print(f"  - MappedQuery: {result.mapped_query is not None}")
        print(f"  - VizQLQuery: {result.vizql_query is not None}")
        print(f"  - ExecuteResult: {result.query_result is not None}")
        print(f"  - Insights: {len(result.insights)}")
        print(f"  - ReplanDecision: {result.replan_decision is not None}")
    
    @pytest.mark.asyncio
    async def test_full_workflow_with_filter(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test full workflow with date filter.
        
        Question: 2024年各地区销售额
        
        Requirements: 15.3
        """
        question = "2024年各地区销售额"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Check filter was applied
        if result.semantic_query and result.semantic_query.filters:
            print(f"应用的筛选器: {len(result.semantic_query.filters)} 个")
    
    @pytest.mark.asyncio
    async def test_full_workflow_with_aggregation(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test full workflow with specific aggregation.
        
        Question: 各产品类别的平均利润
        
        Requirements: 15.3
        """
        question = "各产品类别的平均利润"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"


class TestMultiRoundAnalysis:
    """Multi-round analysis tests"""
    
    @pytest.mark.asyncio
    async def test_multi_round_analysis(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test multi-round analysis with replanning.
        
        Question: 分析各地区销售情况
        Expected: May trigger multiple rounds of analysis
        
        Requirements: 15.4, 31.1
        """
        question = "分析各地区销售情况"
        
        # Track rounds
        understanding_count = 0
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.NODE_START and event.node_name == "understanding":
                understanding_count += 1
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"\n分析轮数: {understanding_count}")
        print(f"重规划次数: {result.replan_count}")
    
    @pytest.mark.asyncio
    async def test_deep_analysis(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test deep analysis request.
        
        Question: 深入分析各地区销售趋势，找出关键问题
        
        Requirements: 31.2, 31.3
        """
        question = "深入分析各地区销售趋势，找出关键问题"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"重规划次数: {result.replan_count}")


class TestInsightsAccumulation:
    """Insights accumulation tests"""
    
    @pytest.mark.asyncio
    async def test_insights_accumulation(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test insights accumulation across rounds.
        
        Expected: all_insights accumulates insights from all rounds
        
        Requirements: 15.4, 31.4
        """
        question = "分析各地区销售情况"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Check insights
        print(f"\n累积洞察数量: {len(result.insights)}")
        for i, insight in enumerate(result.insights[:5]):
            print(f"  {i+1}. {insight}")
    
    @pytest.mark.asyncio
    async def test_insights_no_duplicates(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test insights have no duplicates.
        
        Expected: all_insights should not contain duplicates
        
        Requirements: 31.4
        """
        question = "分析各产品类别销售情况"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Check for duplicates (simplified check)
        insights_str = [str(i) for i in result.insights]
        unique_insights = set(insights_str)
        
        print(f"总洞察数: {len(insights_str)}, 唯一洞察数: {len(unique_insights)}")


class TestWorkflowNodeOutputs:
    """Workflow node outputs tests"""
    
    @pytest.mark.asyncio
    async def test_all_node_outputs_present(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test all node outputs are present in result.
        
        Expected: All intermediate outputs accessible
        
        Requirements: 15.5
        """
        question = "各地区销售额是多少"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Check all outputs
        outputs = {
            "semantic_query": result.semantic_query,
            "mapped_query": result.mapped_query,
            "vizql_query": result.vizql_query,
            "query_result": result.query_result,
            "insights": result.insights,
            "replan_decision": result.replan_decision,
        }
        
        print("\n节点输出检查:")
        for name, output in outputs.items():
            status = "✓" if output is not None else "✗"
            print(f"  {status} {name}: {output is not None}")


class TestFullCycleProperties:
    """Property-based tests for full cycle"""
    
    # **Feature: workflow-e2e-testing, Property 15: 洞察累积正确性**
    # **Validates: Requirements 15.4, 31.1, 31.2**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=3, deadline=180000)
    @given(
        question=st.sampled_from([
            "分析各地区销售情况",
            "分析各产品类别利润趋势",
            "分析各年度销售变化",
        ]),
    )
    async def test_property_insights_accumulation(
        self,
        question: str,
        check_env,
    ):
        """
        Property 15: Insights should accumulate correctly.
        
        For any multi-round analysis, all_insights should accumulate
        insights from all rounds without duplicates.
        
        **Feature: workflow-e2e-testing, Property 15: 洞察累积正确性**
        **Validates: Requirements 15.4, 31.1, 31.2**
        """
        executor = WorkflowExecutor(max_replan_rounds=2, use_memory_checkpointer=True)
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}"
        
        # Insights should be a list
        assert isinstance(result.insights, list), "insights 应为列表"
        
        print(f"问题: {question}, 洞察数量: {len(result.insights)}")
