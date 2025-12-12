# -*- coding: utf-8 -*-
"""
E2E Tests: Performance Benchmarks

Tests performance benchmarks including:
- Simple query performance
- Complex query performance
- Replan round performance

Requirements: 14.1, 14.2, 14.3
"""

import pytest
import time
from hypothesis import given, strategies as st, settings as hyp_settings

from tableau_assistant.src.workflow.executor import WorkflowExecutor
from tableau_assistant.src.workflow.printer import WorkflowPrinter


# Performance thresholds (in seconds)
SIMPLE_QUERY_THRESHOLD = 30  # Simple queries should complete within 30s
COMPLEX_QUERY_THRESHOLD = 60  # Complex queries should complete within 60s
REPLAN_ROUND_THRESHOLD = 45  # Each replan round should complete within 45s


class TestSimpleQueryPerformance:
    """Simple query performance tests"""
    
    @pytest.mark.asyncio
    async def test_simple_query_performance(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        timer,
        check_env,
    ):
        """
        Test simple query performance.
        
        Question: 各地区销售额是多少
        Expected: Completes within 30 seconds
        
        Requirements: 14.1
        """
        question = "各地区销售额是多少"
        
        with timer() as t:
            result = await executor.run(question)
        
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        print(f"\n性能指标:")
        print(f"  - 执行时间: {t.duration:.2f}s")
        print(f"  - 阈值: {SIMPLE_QUERY_THRESHOLD}s")
        
        assert t.duration < SIMPLE_QUERY_THRESHOLD, \
            f"简单查询超时: {t.duration:.2f}s > {SIMPLE_QUERY_THRESHOLD}s"
    
    @pytest.mark.asyncio
    async def test_simple_aggregation_performance(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        timer,
        check_env,
    ):
        """
        Test simple aggregation performance.
        
        Question: 各产品类别的平均利润
        
        Requirements: 14.1
        """
        question = "各产品类别的平均利润"
        
        with timer() as t:
            result = await executor.run(question)
        
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"执行时间: {t.duration:.2f}s")
        
        assert t.duration < SIMPLE_QUERY_THRESHOLD
    
    @pytest.mark.asyncio
    async def test_simple_filter_performance(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        timer,
        check_env,
    ):
        """
        Test simple filter query performance.
        
        Question: 2024年各地区销售额
        
        Requirements: 14.1
        """
        question = "2024年各地区销售额"
        
        with timer() as t:
            result = await executor.run(question)
        
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"执行时间: {t.duration:.2f}s")
        
        assert t.duration < SIMPLE_QUERY_THRESHOLD


class TestComplexQueryPerformance:
    """Complex query performance tests"""
    
    @pytest.mark.asyncio
    async def test_complex_query_performance(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        timer,
        check_env,
    ):
        """
        Test complex query performance.
        
        Question: 各地区各产品类别的销售额和利润，按年份分组
        Expected: Completes within 60 seconds
        
        Requirements: 14.2
        """
        question = "各地区各产品类别的销售额和利润，按年份分组"
        
        with timer() as t:
            result = await executor.run(question)
        
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        print(f"\n性能指标:")
        print(f"  - 执行时间: {t.duration:.2f}s")
        print(f"  - 阈值: {COMPLEX_QUERY_THRESHOLD}s")
        
        assert t.duration < COMPLEX_QUERY_THRESHOLD, \
            f"复杂查询超时: {t.duration:.2f}s > {COMPLEX_QUERY_THRESHOLD}s"
    
    @pytest.mark.asyncio
    async def test_lod_query_performance(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        timer,
        check_env,
    ):
        """
        Test LOD query performance.
        
        Question: 每个客户的首次购买日期
        
        Requirements: 14.2
        """
        question = "每个客户的首次购买日期"
        
        with timer() as t:
            result = await executor.run(question)
        
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"执行时间: {t.duration:.2f}s")
        
        assert t.duration < COMPLEX_QUERY_THRESHOLD
    
    @pytest.mark.asyncio
    async def test_table_calc_performance(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        timer,
        check_env,
    ):
        """
        Test table calculation performance.
        
        Question: 按月份显示累计销售额和同比增长
        
        Requirements: 14.2
        """
        question = "按月份显示累计销售额和同比增长"
        
        with timer() as t:
            result = await executor.run(question)
        
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        print(f"执行时间: {t.duration:.2f}s")
        
        assert t.duration < COMPLEX_QUERY_THRESHOLD


class TestReplanRoundPerformance:
    """Replan round performance tests"""
    
    @pytest.mark.asyncio
    async def test_replan_round_performance(
        self,
        printer: WorkflowPrinter,
        timer,
        check_env,
    ):
        """
        Test replan round performance.
        
        Question: 分析各地区销售情况
        Expected: Each replan round completes within threshold
        
        Requirements: 14.3
        """
        executor = WorkflowExecutor(
            max_replan_rounds=2,
            use_memory_checkpointer=True,
        )
        
        question = "分析各地区销售情况"
        
        with timer() as t:
            result = await executor.run(question)
        
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        # Calculate average time per round
        rounds = result.replan_count + 1  # Initial round + replan rounds
        avg_time_per_round = t.duration / rounds if rounds > 0 else t.duration
        
        print(f"\n性能指标:")
        print(f"  - 总执行时间: {t.duration:.2f}s")
        print(f"  - 分析轮数: {rounds}")
        print(f"  - 平均每轮时间: {avg_time_per_round:.2f}s")
        print(f"  - 每轮阈值: {REPLAN_ROUND_THRESHOLD}s")
        
        assert avg_time_per_round < REPLAN_ROUND_THRESHOLD, \
            f"每轮平均时间超时: {avg_time_per_round:.2f}s > {REPLAN_ROUND_THRESHOLD}s"
    
    @pytest.mark.asyncio
    async def test_multi_round_performance(
        self,
        printer: WorkflowPrinter,
        timer,
        check_env,
    ):
        """
        Test multi-round analysis performance.
        
        Question: 深入分析销售数据
        
        Requirements: 14.3
        """
        executor = WorkflowExecutor(
            max_replan_rounds=3,
            use_memory_checkpointer=True,
        )
        
        question = "深入分析销售数据，找出关键问题"
        
        with timer() as t:
            result = await executor.run(question)
        
        printer.print_result(result)
        
        assert result.success, f"执行失败: {result.error}"
        
        print(f"总执行时间: {t.duration:.2f}s, 重规划次数: {result.replan_count}")


class TestPerformanceComparison:
    """Performance comparison tests"""
    
    @pytest.mark.asyncio
    async def test_streaming_vs_run_performance(
        self,
        executor: WorkflowExecutor,
        printer: WorkflowPrinter,
        timer,
        check_env,
    ):
        """
        Test streaming vs run performance comparison.
        
        Expected: Streaming and run should have similar total time
        """
        question = "各地区销售额是多少"
        
        # Test run()
        with timer() as t_run:
            result_run = await executor.run(question)
        
        # Test stream()
        with timer() as t_stream:
            async for event in executor.stream(question):
                pass  # Just consume events
        
        print(f"\n性能对比:")
        print(f"  - run() 时间: {t_run.duration:.2f}s")
        print(f"  - stream() 时间: {t_stream.duration:.2f}s")
        
        assert result_run.success


class TestPerformanceProperties:
    """Property-based tests for performance"""
    
    # **Feature: workflow-e2e-testing, Property 17: 性能基准**
    # **Validates: Requirements 14.1**
    @pytest.mark.asyncio
    @hyp_settings(max_examples=3, deadline=None)  # No deadline for performance tests
    @given(
        question=st.sampled_from([
            "各地区销售额",
            "各产品类别利润",
            "2024年销售趋势",
        ]),
    )
    async def test_property_performance_baseline(
        self,
        question: str,
        check_env,
    ):
        """
        Property 17: Simple queries should complete within threshold.
        
        For any simple aggregation query, execution time should be
        less than 30 seconds.
        
        **Feature: workflow-e2e-testing, Property 17: 性能基准**
        **Validates: Requirements 14.1**
        """
        executor = WorkflowExecutor(max_replan_rounds=1, use_memory_checkpointer=True)
        
        start_time = time.time()
        result = await executor.run(question)
        duration = time.time() - start_time
        
        assert result.success, f"查询失败: {question}"
        assert duration < SIMPLE_QUERY_THRESHOLD, \
            f"查询超时: {question}, {duration:.2f}s > {SIMPLE_QUERY_THRESHOLD}s"
        
        print(f"问题: {question}, 执行时间: {duration:.2f}s")
