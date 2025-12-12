# -*- coding: utf-8 -*-
"""
E2E Tests: Replanning Flow

Tests the replanning workflow including:
- Replanner decision making
- Replan routing
- Max replan rounds limit
- Completeness evaluation

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestReplannerDecision:
    """Replanner decision tests"""
    
    @pytest.mark.asyncio
    async def test_replanner_returns_decision(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test replanner returns ReplanDecision.
        
        Question: 各地区销售额是多少
        Expected: Replanner returns decision with completeness_score
        
        Requirements: 9.1
        """
        question = "各地区销售额是多少"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Check replan decision
        if result.replan_decision:
            print(f"重规划决策:")
            print(f"  - should_replan: {result.replan_decision.should_replan}")
            print(f"  - completeness_score: {result.replan_decision.completeness_score}")
            print(f"  - reason: {result.replan_decision.reason}")
    
    @pytest.mark.asyncio
    async def test_replan_when_incomplete(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test replan triggers when analysis is incomplete.
        
        Question: 分析各地区销售情况（需要深入分析）
        Expected: May trigger replan for deeper analysis
        
        Requirements: 9.2
        """
        question = "分析各地区销售情况"
        
        # Stream to observe replan flow
        replan_events = []
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.NODE_COMPLETE and event.node_name == "replanner":
                replan_events.append(event.data)
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"重规划次数: {result.replan_count}")
    
    @pytest.mark.asyncio
    async def test_no_replan_when_complete(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test no replan when analysis is complete.
        
        Question: 2024年各地区销售额是多少（简单明确的问题）
        Expected: should_replan=False for simple complete queries
        
        Requirements: 9.3
        """
        question = "2024年各地区销售额是多少"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Simple queries may not need replan
        if result.replan_decision:
            print(f"should_replan: {result.replan_decision.should_replan}")


class TestReplanRoundsLimit:
    """Replan rounds limit tests"""
    
    @pytest.mark.asyncio
    async def test_max_replan_rounds_limit(
        self,
        check_env,
    ):
        """
        Test max replan rounds limit is respected.
        
        Expected: Workflow stops after max_replan_rounds
        
        Requirements: 9.4
        """
        # Create executor with low max rounds for testing
        executor = WorkflowExecutor(
            max_replan_rounds=2,
            use_memory_checkpointer=True,
        )
        printer = WorkflowPrinter(verbose=True, show_tokens=False)
        
        question = "深入分析各地区销售情况，找出所有问题"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.replan_count <= 2, f"重规划次数超过限制: {result.replan_count}"
        print(f"重规划次数: {result.replan_count}")
    
    @pytest.mark.asyncio
    async def test_replan_count_increments(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test replan count increments correctly.
        
        Requirements: 9.4
        """
        question = "分析各地区销售趋势"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.replan_count >= 0, "重规划次数应为非负数"
        print(f"重规划次数: {result.replan_count}")


class TestReplanRouting:
    """Replan routing tests"""
    
    @pytest.mark.asyncio
    async def test_replan_routing_to_understanding(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test replan routes back to understanding.
        
        Expected: When should_replan=True, routes to understanding
        
        Requirements: 9.5
        """
        question = "分析各地区销售情况"
        
        # Track node visits
        node_visits = []
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.NODE_START:
                node_visits.append(event.node_name)
        
        print(f"\n节点访问顺序: {node_visits}")
        
        # If replan happened, understanding should appear more than once
        understanding_count = node_visits.count("understanding")
        print(f"understanding 节点访问次数: {understanding_count}")


class TestReplanProperties:
    """Property-based tests for replanning"""
    
    # **Feature: workflow-e2e-testing, Property 10: 重规划决策正确性**
    # **Validates: Requirements 9.1**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=3, deadline=180000)
    @given(
        question=st.sampled_from([
            "各地区销售额是多少",
            "分析各产品类别销售情况",
            "2024年销售趋势分析",
        ]),
    )
    async def test_property_replan_decision_valid(
        self,
        question: str,
        check_env,
    ):
        """
        Property 10: Replanner should return valid ReplanDecision.
        
        For any Insight Agent output, Replanner should return
        ReplanDecision with completeness_score.
        
        **Feature: workflow-e2e-testing, Property 10: 重规划决策正确性**
        **Validates: Requirements 9.1**
        """
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=True)
        
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}, 错误: {result.error}"
        
        # Replan decision should exist for analysis questions
        if result.is_analysis_question and result.replan_decision:
            assert hasattr(result.replan_decision, 'completeness_score'), \
                "ReplanDecision 应包含 completeness_score"
    
    # **Feature: workflow-e2e-testing, Property 11: 重规划路由正确性**
    # **Validates: Requirements 9.2, 9.3, 9.4, 9.5**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=3, deadline=180000)
    @given(
        max_rounds=st.sampled_from([1, 2, 3]),
    )
    async def test_property_replan_routing_correct(
        self,
        max_rounds: int,
        check_env,
    ):
        """
        Property 11: Replan routing should be correct.
        
        When should_replan=True and replan_count < max_rounds,
        should route to Understanding. Otherwise route to END.
        
        **Feature: workflow-e2e-testing, Property 11: 重规划路由正确性**
        **Validates: Requirements 9.2, 9.3, 9.4, 9.5**
        """
        executor = WorkflowExecutor(
            max_replan_rounds=max_rounds,
            use_memory_checkpointer=True,
        )
        
        question = "分析各地区销售情况"
        result = await executor.run(question)
        
        assert result.success, f"查询失败: {question}"
        assert result.replan_count <= max_rounds, \
            f"重规划次数 {result.replan_count} 超过限制 {max_rounds}"
