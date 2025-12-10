"""
测试辅助模块

提供端到端工作流测试所需的辅助类和工具：
- TestEnvironment: 测试环境管理
- TestReporter: 测试报告生成
- MetadataTester: 元数据测试器
- StoreTester: 存储测试器
- 测试数据模型（TestCase, TestStageResult, TestResult, TestReport）
"""

# 版本信息
__version__ = "1.0.0"

# 导入所有组件
from tableau_assistant.tests.test_helpers.test_cases import TestCase
from tableau_assistant.tests.test_helpers.test_models import (
    TestStageResult,
    TestResult,
    TestReport
)
from tableau_assistant.tests.test_helpers.test_environment import TestEnvironment
from tableau_assistant.tests.test_helpers.test_reporter import TestReporter
from tableau_assistant.tests.test_helpers.metadata_tester import MetadataTester
from tableau_assistant.tests.test_helpers.store_tester import StoreTester

# 导出的类和函数
__all__ = [
    # 数据模型
    "TestCase",
    "TestStageResult",
    "TestResult",
    "TestReport",
    
    # 测试组件
    "TestEnvironment",
    "TestReporter",
    "MetadataTester",
    "StoreTester",
]
