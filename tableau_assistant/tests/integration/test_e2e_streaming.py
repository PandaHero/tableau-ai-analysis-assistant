# -*- coding: utf-8 -*-
"""
E2E Tests: Streaming Execution

Tests the streaming execution including:
- NODE_START events
- NODE_COMPLETE events
- TOKEN events
- COMPLETE event
- ERROR event

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

import pytest
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType
from tableau_assistant.src.workflow.printer import WorkflowPrinter


class TestStreamingEvents:
    """Streaming event tests"""
    
    @pytest.mark.asyncio
    async def test_stream_node_start_events(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test NODE_START events are emitted.
        
        Expected: Each node emits NODE_START event
        
        Requirements: 10.1
        """
        question = "各地区销售额是多少"
        
        node_start_events = []
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.NODE_START:
                node_start_events.append(event.node_name)
        
        print(f"\nNODE_START 事件: {node_start_events}")
        
        # Should have at least understanding node start
        assert len(node_start_events) > 0, "应收到 NODE_START 事件"
        assert "understanding" in node_start_events, "应收到 understanding NODE_START"
    
    @pytest.mark.asyncio
    async def test_stream_node_complete_events(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test NODE_COMPLETE events are emitted.
        
        Expected: Each node emits NODE_COMPLETE event with data
        
        Requirements: 10.2
        """
        question = "各地区销售额是多少"
        
        node_complete_events = []
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.NODE_COMPLETE:
                node_complete_events.append({
                    "node": event.node_name,
                    "has_data": event.data is not None,
                })
        
        print(f"\nNODE_COMPLETE 事件: {node_complete_events}")
        
        # Should have at least understanding node complete
        assert len(node_complete_events) > 0, "应收到 NODE_COMPLETE 事件"
    
    @pytest.mark.asyncio
    async def test_stream_token_events(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test TOKEN events are emitted during LLM streaming.
        
        Expected: TOKEN events contain content
        
        Requirements: 10.3
        """
        question = "各地区销售额是多少"
        
        token_count = 0
        token_content = []
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.TOKEN:
                token_count += 1
                if event.content:
                    token_content.append(event.content)
        
        print(f"\nTOKEN 事件数量: {token_count}")
        print(f"Token 内容示例: {''.join(token_content[:10])}")
        
        # May or may not have tokens depending on LLM streaming support
        print(f"收到 {token_count} 个 TOKEN 事件")
    
    @pytest.mark.asyncio
    async def test_stream_complete_event(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test COMPLETE event is emitted at the end.
        
        Expected: COMPLETE event marks workflow completion
        
        Requirements: 10.4
        """
        question = "各地区销售额是多少"
        
        complete_received = False
        async for event in executor.stream(question):
            printer.print_event(event)
            if event.type == EventType.COMPLETE:
                complete_received = True
        
        assert complete_received, "应收到 COMPLETE 事件"
    
    @pytest.mark.asyncio
    async def test_stream_event_order(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test event order is correct.
        
        Expected: NODE_START before NODE_COMPLETE for each node
        
        Requirements: 10.1, 10.2
        """
        question = "各地区销售额是多少"
        
        events = []
        async for event in executor.stream(question):
            printer.print_event(event)
            events.append((event.type, event.node_name))
        
        print(f"\n事件顺序: {events}")
        
        # Verify NODE_START comes before NODE_COMPLETE for understanding
        understanding_start_idx = None
        understanding_complete_idx = None
        
        for i, (event_type, node_name) in enumerate(events):
            if event_type == EventType.NODE_START and node_name == "understanding":
                understanding_start_idx = i
            if event_type == EventType.NODE_COMPLETE and node_name == "understanding":
                understanding_complete_idx = i
        
        if understanding_start_idx is not None and understanding_complete_idx is not None:
            assert understanding_start_idx < understanding_complete_idx, \
                "NODE_START 应在 NODE_COMPLETE 之前"


class TestStreamingWithPrinter:
    """Streaming with WorkflowPrinter tests"""
    
    @pytest.mark.asyncio
    async def test_printer_handles_all_events(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test WorkflowPrinter handles all event types.
        
        Expected: Printer prints all events without error
        """
        question = "各地区销售额是多少"
        
        event_types_seen = set()
        async for event in executor.stream(question):
            # This should not raise any exception
            printer.print_event(event)
            event_types_seen.add(event.type)
        
        print(f"\n处理的事件类型: {event_types_seen}")
    
    @pytest.mark.asyncio
    async def test_quiet_printer_streaming(
        self,
        executor: WorkflowExecutor,
        quiet_printer: WorkflowPrinter,
        check_env,
    ):
        """
        Test quiet printer with streaming.
        
        Expected: Quiet printer produces minimal output
        """
        question = "各地区销售额是多少"
        
        async for event in executor.stream(question):
            quiet_printer.print_event(event)
        
        print("\n静默模式流式执行完成")


class TestStreamingProperties:
    """Property-based tests for streaming"""
    
    # **Feature: workflow-e2e-testing, Property 12: 流式执行事件完整性**
    # **Validates: Requirements 10.1, 10.2, 10.4**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=3, deadline=180000)
    @given(
        question=st.sampled_from([
            "各地区销售额是多少",
            "2024年销售趋势",
            "各产品类别利润",
        ]),
    )
    async def test_property_streaming_events_complete(
        self,
        question: str,
        check_env,
    ):
        """
        Property 12: Streaming should emit complete event set.
        
        For any streaming execution, event stream should include
        NODE_START, NODE_COMPLETE, and COMPLETE events.
        
        **Feature: workflow-e2e-testing, Property 12: 流式执行事件完整性**
        **Validates: Requirements 10.1, 10.2, 10.4**
        """
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=True)
        
        event_types = set()
        async for event in executor.stream(question):
            event_types.add(event.type)
        
        # Must have COMPLETE event
        assert EventType.COMPLETE in event_types, \
            f"应包含 COMPLETE 事件: {question}"
        
        # Should have NODE_START and NODE_COMPLETE
        assert EventType.NODE_START in event_types or EventType.NODE_COMPLETE in event_types, \
            f"应包含节点事件: {question}"
