"""
测试报告器

负责格式化和输出测试结果，提供清晰的测试报告
"""
from typing import List, Dict, Any, Optional
import json
from datetime import datetime

from tableau_assistant.tests.test_helpers.test_models import (
    TestStageResult,
    TestResult,
    TestReport
)


class TestReporter:
    """
    测试报告器
    
    提供格式化的测试输出，包括：
    - 分隔线和标题
    - 阶段结果输出
    - 测试总结
    - 数据样本格式化
    """
    
    def __init__(self, verbose: bool = True):
        """
        初始化测试报告器
        
        Args:
            verbose: 是否输出详细信息
        """
        self.verbose = verbose
        self.section_width = 100
        self.subsection_width = 80
    
    def print_section(self, title: str, level: int = 1):
        """
        打印分隔线和标题
        
        Args:
            title: 标题文本
            level: 级别（1=主标题，2=子标题）
        """
        if level == 1:
            # 主标题
            print("\n" + "=" * self.section_width)
            print(f"  {title}")
            print("=" * self.section_width + "\n")
        else:
            # 子标题
            print("\n" + "-" * self.subsection_width)
            print(f"  {title}")
            print("-" * self.subsection_width + "\n")
    
    def format_duration(self, seconds: float) -> str:
        """
        格式化时间
        
        Args:
            seconds: 秒数
        
        Returns:
            格式化的时间字符串
        """
        if seconds < 1:
            return f"{seconds * 1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.2f}秒"
        else:
            minutes = int(seconds // 60)
            remaining_seconds = seconds % 60
            return f"{minutes}分{remaining_seconds:.2f}秒"
    
    def format_data_sample(
        self,
        data: List[Dict],
        max_rows: int = 5,
        max_col_width: int = 30
    ) -> str:
        """
        格式化数据样本
        
        Args:
            data: 数据列表
            max_rows: 最大显示行数
            max_col_width: 最大列宽
        
        Returns:
            格式化的数据样本字符串
        """
        if not data:
            return "  (无数据)"
        
        # 获取列名
        columns = list(data[0].keys())
        
        # 限制显示的行数
        display_data = data[:max_rows]
        
        # 构建表格
        lines = []
        
        # 表头
        header = "  | ".join([str(col)[:max_col_width].ljust(max_col_width) for col in columns])
        lines.append("  " + header)
        lines.append("  " + "-" * len(header))
        
        # 数据行
        for row in display_data:
            row_str = "  | ".join([
                str(row.get(col, ""))[:max_col_width].ljust(max_col_width)
                for col in columns
            ])
            lines.append("  " + row_str)
        
        # 如果有更多数据
        if len(data) > max_rows:
            lines.append(f"  ... (还有 {len(data) - max_rows} 行)")
        
        return "\n".join(lines)
    
    def print_stage_result(self, stage_result: TestStageResult, indent: int = 0):
        """
        打印阶段测试结果
        
        Args:
            stage_result: 阶段测试结果
            indent: 缩进级别
        """
        indent_str = "  " * indent
        
        # 状态符号
        status_symbol = "✓" if stage_result.success else "✗"
        status_text = "成功" if stage_result.success else "失败"
        
        print(f"{indent_str}{status_symbol} {status_text}")
        print(f"{indent_str}  - 执行时间: {self.format_duration(stage_result.duration)}")
        
        # 显示元数据
        if stage_result.metadata:
            for key, value in stage_result.metadata.items():
                if key == "token_count":
                    print(f"{indent_str}  - Token使用: {value} tokens")
                elif key == "row_count":
                    print(f"{indent_str}  - 返回行数: {value}")
                elif key == "field_count":
                    print(f"{indent_str}  - 字段数: {value}")
                elif self.verbose:
                    print(f"{indent_str}  - {key}: {value}")
        
        # 显示警告
        if stage_result.warnings:
            for warning in stage_result.warnings:
                print(f"{indent_str}  ⚠️  {warning}")
        
        # 显示错误信息
        if stage_result.error_message:
            print(f"{indent_str}  ✗ 错误: {stage_result.error_message}")
        
        # 显示输出数据摘要（如果verbose模式）
        if self.verbose and stage_result.output_data:
            self._print_output_summary(stage_result.output_data, indent + 1)
    
    def _print_output_summary(self, output_data: Any, indent: int = 0):
        """
        打印输出数据摘要
        
        Args:
            output_data: 输出数据
            indent: 缩进级别
        """
        indent_str = "  " * indent
        
        if output_data is None:
            return
        
        # 如果是字典
        if isinstance(output_data, dict):
            if "data" in output_data and isinstance(output_data["data"], list):
                # 查询结果格式
                print(f"{indent_str}数据样本:")
                print(self.format_data_sample(output_data["data"], max_rows=3))
            elif "boosted_question" in output_data:
                # 问题Boost结果
                print(f"{indent_str}优化后问题: {output_data['boosted_question']}")
            elif "question_type" in output_data:
                # 问题理解结果
                print(f"{indent_str}问题类型: {output_data['question_type']}")
            elif "subtasks" in output_data:
                # 查询规划结果
                print(f"{indent_str}子任务数: {len(output_data['subtasks'])}")
        
        # 如果是列表
        elif isinstance(output_data, list):
            print(f"{indent_str}列表项数: {len(output_data)}")
    
    def print_test_result(self, test_result: TestResult):
        """
        打印单个测试用例结果
        
        Args:
            test_result: 测试用例结果
        """
        self.print_section(f"测试用例: {test_result.test_case_name}", level=1)
        
        # 总体状态
        status_symbol = "✓" if test_result.success else "✗"
        status_text = "通过" if test_result.success else "失败"
        print(f"{status_symbol} 状态: {status_text}")
        print(f"⏱  总执行时间: {self.format_duration(test_result.total_duration)}")
        
        # 各阶段结果
        if test_result.stage_results:
            print(f"\n阶段执行结果:")
            for stage in test_result.stage_results:
                self.print_section(f"阶段: {stage.stage_name}", level=2)
                self.print_stage_result(stage, indent=0)
        
        # 错误信息
        if test_result.error_message:
            print(f"\n✗ 错误信息: {test_result.error_message}")
        
        # 摘要信息
        if test_result.summary:
            print(f"\n摘要:")
            for key, value in test_result.summary.items():
                print(f"  - {key}: {value}")
    
    def print_test_summary(self, report: TestReport):
        """
        打印测试总结
        
        Args:
            report: 测试报告
        """
        self.print_section("测试总结", level=1)
        
        # 基本统计
        print(f"总测试数: {report.total_tests}")
        print(f"✓ 通过: {report.passed_tests}")
        print(f"✗ 失败: {report.failed_tests}")
        print(f"通过率: {report.get_pass_rate():.1f}%")
        print(f"⏱  总执行时间: {self.format_duration(report.total_duration)}")
        print(f"⏱  平均执行时间: {self.format_duration(report.get_average_duration())}")
        
        # 环境信息
        if report.environment_info:
            print(f"\n环境信息:")
            for key, value in report.environment_info.items():
                print(f"  - {key}: {value}")
        
        # 统计信息
        if report.statistics:
            print(f"\n详细统计:")
            
            # 各阶段平均执行时间
            if "average_stage_durations" in report.statistics:
                print(f"  各阶段平均执行时间:")
                for stage, duration in report.statistics["average_stage_durations"].items():
                    print(f"    - {stage}: {self.format_duration(duration)}")
            
            # Token使用
            if "total_tokens" in report.statistics:
                print(f"  总Token使用: {report.statistics['total_tokens']}")
            
            # 总阶段数
            if "total_stages" in report.statistics:
                print(f"  总执行阶段数: {report.statistics['total_stages']}")
        
        # 失败的测试
        if report.failed_tests > 0:
            failed_names = report.get_failed_test_names()
            print(f"\n失败的测试用例:")
            for name in failed_names:
                print(f"  ✗ {name}")
        
        # 最终状态
        print()
        if report.failed_tests == 0:
            print("🎉 所有测试通过！")
        else:
            print(f"⚠️  有 {report.failed_tests} 个测试失败")
    
    def export_json(self, report: TestReport, filepath: str):
        """
        导出JSON格式的测试报告
        
        Args:
            report: 测试报告
            filepath: 输出文件路径
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        
        print(f"✓ 测试报告已导出到: {filepath}")
    
    def print_progress(self, current: int, total: int, message: str = ""):
        """
        打印进度信息
        
        Args:
            current: 当前进度
            total: 总数
            message: 附加消息
        """
        percentage = (current / total) * 100 if total > 0 else 0
        progress_bar = "█" * int(percentage / 5) + "░" * (20 - int(percentage / 5))
        print(f"\r进度: [{progress_bar}] {percentage:.1f}% ({current}/{total}) {message}", end="", flush=True)
        
        if current == total:
            print()  # 完成后换行


# ============= 导出 =============

__all__ = [
    "TestReporter",
]
