"""
测试协调器

负责协调整个测试流程，包括：
- 执行单个测试用例
- 执行所有测试用例
- 错误处理
- 结果汇总
"""
import time
from typing import List
import traceback

from tableau_assistant.tests.test_helpers.test_environment import TestEnvironment
from tableau_assistant.tests.test_helpers.test_reporter import TestReporter
from tableau_assistant.tests.test_helpers.test_cases import TestCase
from tableau_assistant.tests.test_helpers.test_models import TestResult, TestReport, TestStageResult
from tableau_assistant.tests.test_helpers.workflow_tester import WorkflowTester
from tableau_assistant.tests.test_helpers.metadata_tester import MetadataTester
from tableau_assistant.tests.test_helpers.store_tester import StoreTester


class TestOrchestrator:
    """
    测试协调器
    
    协调整个测试流程的执行
    """
    
    def __init__(self, environment: TestEnvironment, reporter: TestReporter):
        """
        初始化测试协调器
        
        Args:
            environment: 测试环境实例
            reporter: 测试报告器实例
        """
        self.environment = environment
        self.reporter = reporter
        self.workflow_tester = WorkflowTester(environment)
        self.metadata_tester = MetadataTester(environment)
        self.store_tester = StoreTester(environment)
    
    async def run_single_test(self, test_case: TestCase) -> TestResult:
        """
        运行单个测试用例
        
        执行完整的工作流程：
        1. 问题Boost（可选）
        2. 问题理解
        3. 任务规划
        4. 查询构建
        5. 查询执行
        
        Args:
            test_case: 测试用例
        
        Returns:
            TestResult: 测试结果
        """
        start_time = time.time()
        stage_results = []
        
        try:
            self.reporter.print_section(f"测试用例: {test_case.name}", level=1)
            print(f"描述: {test_case.description}")
            print(f"问题: {test_case.question}")
            print(f"复杂度: {test_case.complexity}\n")
            
            # 获取元数据（所有测试用例共享）
            metadata = await self.metadata_tester.metadata_manager.get_metadata_async(
                use_cache=True,
                enhance=True
            )
            
            dimension_hierarchy = metadata.dimension_hierarchy if metadata else None
            
            # 阶段1: 问题Boost（可选）
            self.reporter.print_section("阶段 1: 问题Boost", level=2)
            boost, boost_result = await self.workflow_tester.test_question_boost(
                question=test_case.question,
                metadata=metadata
            )
            stage_results.append(boost_result)
            self.reporter.print_stage_result(boost_result)
            
            # 使用优化后的问题（如果有）
            question_to_use = test_case.question
            if boost and hasattr(boost, 'boosted_question') and boost.boosted_question:
                question_to_use = boost.boosted_question
                print(f"\n使用优化后的问题: {question_to_use}")
            
            # 阶段2: 问题理解
            self.reporter.print_section("阶段 2: 问题理解", level=2)
            understanding, understanding_result = await self.workflow_tester.test_understanding(
                question=question_to_use
            )
            stage_results.append(understanding_result)
            self.reporter.print_stage_result(understanding_result)
            
            if not understanding:
                # 如果问题理解失败，停止后续测试
                return TestResult(
                    test_case_name=test_case.name,
                    success=False,
                    total_duration=time.time() - start_time,
                    stage_results=stage_results,
                    error_message="问题理解失败，无法继续后续测试"
                )
            
            # 阶段3: 任务规划
            self.reporter.print_section("阶段 3: 任务规划", level=2)
            query_plan, planning_result = await self.workflow_tester.test_task_planning(
                question=question_to_use,
                understanding=understanding,
                metadata=metadata,
                dimension_hierarchy=dimension_hierarchy
            )
            stage_results.append(planning_result)
            self.reporter.print_stage_result(planning_result)
            
            if not query_plan:
                # 如果任务规划失败，停止后续测试
                return TestResult(
                    test_case_name=test_case.name,
                    success=False,
                    total_duration=time.time() - start_time,
                    stage_results=stage_results,
                    error_message="任务规划失败，无法继续后续测试"
                )
            
            # 阶段4: 查询构建
            self.reporter.print_section("阶段 4: 查询构建", level=2)
            queries, building_result = await self.workflow_tester.test_query_building(
                query_plan=query_plan,
                metadata=metadata
            )
            stage_results.append(building_result)
            self.reporter.print_stage_result(building_result)
            
            if not queries:
                # 如果查询构建失败，停止后续测试
                return TestResult(
                    test_case_name=test_case.name,
                    success=False,
                    total_duration=time.time() - start_time,
                    stage_results=stage_results,
                    error_message="查询构建失败，无法继续后续测试"
                )
            
            # 阶段5: 查询执行
            self.reporter.print_section("阶段 5: 查询执行", level=2)
            results, execution_result = await self.workflow_tester.test_query_execution(
                queries=queries
            )
            stage_results.append(execution_result)
            self.reporter.print_stage_result(execution_result)
            
            # 计算总体成功状态
            success = all(stage.success for stage in stage_results)
            
            # 创建测试结果
            test_result = TestResult(
                test_case_name=test_case.name,
                success=success,
                total_duration=time.time() - start_time,
                stage_results=stage_results,
                error_message=None if success else "部分阶段执行失败",
                summary={
                    "question": test_case.question,
                    "complexity": test_case.complexity,
                    "total_stages": len(stage_results),
                    "successful_stages": sum(1 for s in stage_results if s.success),
                    "failed_stages": sum(1 for s in stage_results if not s.success)
                }
            )
            
            return test_result
            
        except Exception as e:
            # 捕获未预期的错误
            error_stage = TestStageResult(
                stage_name="unexpected_error",
                success=False,
                duration=time.time() - start_time,
                error_message=f"未预期的错误: {str(e)}\n{traceback.format_exc()}"
            )
            stage_results.append(error_stage)
            
            return TestResult(
                test_case_name=test_case.name,
                success=False,
                total_duration=time.time() - start_time,
                stage_results=stage_results,
                error_message=f"测试执行过程中发生未预期的错误: {str(e)}"
            )
    
    async def run_all_tests(self, test_cases: List[TestCase]) -> TestReport:
        """
        运行所有测试用例
        
        Args:
            test_cases: 测试用例列表
        
        Returns:
            TestReport: 测试报告
        """
        start_time = time.time()
        test_results = []
        
        self.reporter.print_section("开始执行测试", level=1)
        print(f"总测试用例数: {len(test_cases)}\n")
        
        # 执行每个测试用例
        for i, test_case in enumerate(test_cases):
            if not test_case.enabled:
                print(f"跳过测试用例 {i+1}/{len(test_cases)}: {test_case.name} (已禁用)\n")
                continue
            
            print(f"\n{'='*100}")
            print(f"执行测试用例 {i+1}/{len(test_cases)}")
            print(f"{'='*100}\n")
            
            try:
                test_result = await self.run_single_test(test_case)
                test_results.append(test_result)
                
                # 显示测试结果摘要
                status = "✓ 通过" if test_result.success else "✗ 失败"
                print(f"\n{status} - {test_case.name}")
                print(f"执行时间: {self.reporter.format_duration(test_result.total_duration)}\n")
                
            except Exception as e:
                # 捕获测试用例级别的错误
                print(f"\n✗ 测试用例执行失败: {str(e)}\n")
                error_result = TestResult(
                    test_case_name=test_case.name,
                    success=False,
                    total_duration=time.time() - start_time,
                    stage_results=[],
                    error_message=f"测试用例执行失败: {str(e)}"
                )
                test_results.append(error_result)
        
        # 统计结果
        total_tests = len(test_results)
        passed_tests = sum(1 for r in test_results if r.success)
        failed_tests = total_tests - passed_tests
        
        # 创建测试报告
        report = TestReport(
            total_tests=total_tests,
            passed_tests=passed_tests,
            failed_tests=failed_tests,
            total_duration=time.time() - start_time,
            test_results=test_results,
            environment_info=self.environment.get_environment_info(),
            statistics={}
        )
        
        # 计算统计信息
        report.calculate_statistics()
        
        return report
    
    async def run_metadata_tests(self) -> List[TestStageResult]:
        """
        运行元数据测试
        
        Returns:
            测试结果列表
        """
        self.reporter.print_section("元数据管理测试", level=1)
        
        results = []
        
        # 测试1: 元数据获取
        self.reporter.print_section("测试 1: 元数据获取", level=2)
        result = await self.metadata_tester.test_metadata_fetch()
        results.append(result)
        self.reporter.print_stage_result(result)
        
        # 测试2: 元数据缓存
        self.reporter.print_section("测试 2: 元数据缓存", level=2)
        result = await self.metadata_tester.test_metadata_cache()
        results.append(result)
        self.reporter.print_stage_result(result)
        
        # 测试3: 增强元数据
        self.reporter.print_section("测试 3: 增强元数据", level=2)
        result = await self.metadata_tester.test_enhanced_metadata()
        results.append(result)
        self.reporter.print_stage_result(result)
        
        # 测试4: 维度层级
        self.reporter.print_section("测试 4: 维度层级", level=2)
        result = await self.metadata_tester.test_dimension_hierarchy()
        results.append(result)
        self.reporter.print_stage_result(result)
        
        return results
    
    async def run_store_tests(self) -> List[TestStageResult]:
        """
        运行存储管理测试
        
        Returns:
            测试结果列表
        """
        self.reporter.print_section("存储管理测试", level=1)
        
        results = []
        
        # 测试1: 缓存写入
        self.reporter.print_section("测试 1: 缓存写入", level=2)
        result = await self.store_tester.test_cache_write()
        results.append(result)
        self.reporter.print_stage_result(result)
        
        # 测试2: 缓存读取
        self.reporter.print_section("测试 2: 缓存读取", level=2)
        result = await self.store_tester.test_cache_read()
        results.append(result)
        self.reporter.print_stage_result(result)
        
        # 测试3: 缓存清除
        self.reporter.print_section("测试 3: 缓存清除", level=2)
        result = await self.store_tester.test_cache_clear()
        results.append(result)
        self.reporter.print_stage_result(result)
        
        # 测试4: 缓存过期
        self.reporter.print_section("测试 4: 缓存过期", level=2)
        result = await self.store_tester.test_cache_expiration()
        results.append(result)
        self.reporter.print_stage_result(result)
        
        return results


# ============= 导出 =============

__all__ = [
    "TestOrchestrator",
]
