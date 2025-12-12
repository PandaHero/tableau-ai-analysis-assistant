# -*- coding: utf-8 -*-
"""
E2E Tests: Non-Analysis Question Routing

Tests the workflow routing for non-analysis questions.
Verifies that is_analysis_question=False routes directly to END.

Requirements: 8.1, 8.2, 8.3
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestNonAnalysisRouting:
    """Non-analysis question routing tests"""
    
    @pytest.mark.asyncio
    async def test_greeting_routing(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test greeting question routing.
        
        Question: 你好
        Expected: is_analysis_question=False, routes to END
        
        Requirements: 8.1
        """
        question = "你好"
        
        # Stream to observe routing
        nodes_visited = []
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.NODE_START:
                nodes_visited.append(event.node_name)
        
        # Also run for assertions
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert not result.is_analysis_question, "应识别为非分析类问题"
        
        # Should not visit field_mapper, query_builder, execute
        print(f"访问的节点: {nodes_visited}")
    
    @pytest.mark.asyncio
    async def test_help_routing(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test help question routing.
        
        Question: 你能做什么
        Expected: is_analysis_question=False
        
        Requirements: 8.2
        """
        question = "你能做什么"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert not result.is_analysis_question, "应识别为非分析类问题"
    
    @pytest.mark.asyncio
    async def test_bye_routing(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test goodbye question routing.
        
        Question: 再见
        Expected: is_analysis_question=False
        
        Requirements: 8.3
        """
        question = "再见"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert not result.is_analysis_question, "应识别为非分析类问题"
    
    @pytest.mark.asyncio
    async def test_chitchat_routing(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test chitchat question routing.
        
        Question: 今天天气怎么样
        Expected: is_analysis_question=False
        """
        question = "今天天气怎么样"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert not result.is_analysis_question, "应识别为非分析类问题"
    
    @pytest.mark.asyncio
    async def test_thanks_routing(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test thanks question routing.
        
        Question: 谢谢
        Expected: is_analysis_question=False
        """
        question = "谢谢"
        
        result = await executor.run(question)
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        assert not result.is_analysis_question, "应识别为非分析类问题"


class TestAnalysisRouting:
    """Analysis question routing tests (should NOT route to END early)"""
    
    @pytest.mark.asyncio
    async def test_analysis_question_full_flow(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test analysis question goes through full workflow.
        
        Question: 各地区销售额是多少
        Expected: is_analysis_question=True, visits all nodes
        """
        question = "各地区销售额是多少"
        
        # Stream to observe routing
        nodes_visited = []
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.NODE_START:
                nodes_visited.append(event.node_name)
        
        result = await executor.run(question)
        
        assert result.success, f"执行失败: {result.error}"
        assert result.is_analysis_question, "应识别为分析类问题"
        
        # Should visit understanding, field_mapper, query_builder, execute
        print(f"访问的节点: {nodes_visited}")
        assert "understanding" in nodes_visited, "应访问 understanding 节点"


class TestRoutingProperties:
    """Property-based tests for routing"""
    
    # **Feature: workflow-e2e-testing, Property 9: 非分析类问题路由**
    # **Validates: Requirements 8.1, 8.2, 8.3**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=5, deadline=120000)
    @given(
        non_analysis_question=st.sampled_from([
            "你好",
            "你能做什么",
            "再见",
            "谢谢",
            "帮助",
            "你是谁",
            "今天天气怎么样",
        ]),
    )
    async def test_property_non_analysis_routing(
        self,
        non_analysis_question: str,
        check_env,
    ):
        """
        Property 9: Non-analysis questions should route to END.
        
        For any non-analysis question (greeting, help, bye),
        Understanding Agent should set is_analysis_question=False
        and workflow should route directly to END.
        
        **Feature: workflow-e2e-testing, Property 9: 非分析类问题路由**
        **Validates: Requirements 8.1, 8.2, 8.3**
        """
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=True)
        
        result = await executor.run(non_analysis_question)
        
        assert result.success, f"查询失败: {non_analysis_question}, 错误: {result.error}"
        assert not result.is_analysis_question, f"应识别为非分析类问题: {non_analysis_question}"
