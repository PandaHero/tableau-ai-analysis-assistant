"""
测试结果数据模型

定义测试执行过程中的各种结果数据结构
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class TestStageResult:
    """
    测试阶段结果数据类
    
    记录单个测试阶段的执行结果，包括成功状态、执行时间、输出数据等
    
    Attributes:
        stage_name: 阶段名称（如 "question_boost", "understanding"）
        success: 是否成功
        duration: 执行时间（秒）
        output_data: 输出数据（可以是任何类型）
        error_message: 错误信息（如果失败）
        warnings: 警告信息列表
        metadata: 额外的元数据（如token使用量、API调用次数等）
        timestamp: 执行时间戳
    """
    stage_name: str
    success: bool
    duration: float
    output_data: Optional[Any] = None
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "stage_name": self.stage_name,
            "success": self.success,
            "duration": self.duration,
            "output_data": self.output_data,
            "error_message": self.error_message,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }
    
    def add_warning(self, warning: str):
        """添加警告信息"""
        self.warnings.append(warning)
    
    def add_metadata(self, key: str, value: Any):
        """添加元数据"""
        self.metadata[key] = value


@dataclass
class TestResult:
    """
    测试用例结果数据类
    
    记录单个测试用例的完整执行结果，包括所有阶段的结果
    
    Attributes:
        test_case_name: 测试用例名称
        success: 是否成功（所有阶段都成功才算成功）
        total_duration: 总执行时间（秒）
        stage_results: 各阶段结果列表
        error_message: 错误信息（如果失败）
        summary: 测试摘要信息
        timestamp: 执行时间戳
    """
    test_case_name: str
    success: bool
    total_duration: float
    stage_results: List[TestStageResult] = field(default_factory=list)
    error_message: Optional[str] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "test_case_name": self.test_case_name,
            "success": self.success,
            "total_duration": self.total_duration,
            "stage_results": [stage.to_dict() for stage in self.stage_results],
            "error_message": self.error_message,
            "summary": self.summary,
            "timestamp": self.timestamp.isoformat()
        }
    
    def add_stage_result(self, stage_result: TestStageResult):
        """添加阶段结果"""
        self.stage_results.append(stage_result)
        
        # 如果有阶段失败，整个测试用例标记为失败
        if not stage_result.success:
            self.success = False
    
    def get_stage_result(self, stage_name: str) -> Optional[TestStageResult]:
        """获取指定阶段的结果"""
        for stage in self.stage_results:
            if stage.stage_name == stage_name:
                return stage
        return None
    
    def get_successful_stages(self) -> List[TestStageResult]:
        """获取所有成功的阶段"""
        return [stage for stage in self.stage_results if stage.success]
    
    def get_failed_stages(self) -> List[TestStageResult]:
        """获取所有失败的阶段"""
        return [stage for stage in self.stage_results if not stage.success]


@dataclass
class TestReport:
    """
    测试报告数据类
    
    汇总所有测试用例的执行结果，生成完整的测试报告
    
    Attributes:
        total_tests: 总测试数
        passed_tests: 通过的测试数
        failed_tests: 失败的测试数
        total_duration: 总执行时间（秒）
        test_results: 所有测试结果列表
        environment_info: 环境信息
        statistics: 统计信息
        timestamp: 报告生成时间戳
    """
    total_tests: int
    passed_tests: int
    failed_tests: int
    total_duration: float
    test_results: List[TestResult] = field(default_factory=list)
    environment_info: Dict[str, Any] = field(default_factory=dict)
    statistics: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "total_duration": self.total_duration,
            "test_results": [result.to_dict() for result in self.test_results],
            "environment_info": self.environment_info,
            "statistics": self.statistics,
            "timestamp": self.timestamp.isoformat()
        }
    
    def add_test_result(self, test_result: TestResult):
        """添加测试结果"""
        self.test_results.append(test_result)
    
    def get_pass_rate(self) -> float:
        """获取通过率"""
        if self.total_tests == 0:
            return 0.0
        return (self.passed_tests / self.total_tests) * 100
    
    def get_average_duration(self) -> float:
        """获取平均执行时间"""
        if self.total_tests == 0:
            return 0.0
        return self.total_duration / self.total_tests
    
    def get_failed_test_names(self) -> List[str]:
        """获取失败的测试用例名称列表"""
        return [result.test_case_name for result in self.test_results if not result.success]
    
    def calculate_statistics(self):
        """计算统计信息"""
        if not self.test_results:
            return
        
        # 计算各阶段的平均执行时间
        stage_durations: Dict[str, List[float]] = {}
        for test_result in self.test_results:
            for stage in test_result.stage_results:
                if stage.stage_name not in stage_durations:
                    stage_durations[stage.stage_name] = []
                stage_durations[stage.stage_name].append(stage.duration)
        
        avg_stage_durations = {
            stage: sum(durations) / len(durations)
            for stage, durations in stage_durations.items()
        }
        
        # 计算token使用量（如果有）
        total_tokens = 0
        for test_result in self.test_results:
            for stage in test_result.stage_results:
                if "token_count" in stage.metadata:
                    total_tokens += stage.metadata["token_count"]
        
        self.statistics = {
            "pass_rate": self.get_pass_rate(),
            "average_duration": self.get_average_duration(),
            "average_stage_durations": avg_stage_durations,
            "total_tokens": total_tokens,
            "total_stages": sum(len(r.stage_results) for r in self.test_results),
            "failed_tests": self.get_failed_test_names()
        }


# ============= 导出 =============

__all__ = [
    "TestStageResult",
    "TestResult",
    "TestReport",
]
