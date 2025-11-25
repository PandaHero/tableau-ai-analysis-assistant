"""
测试用例数据模型

定义测试用例的数据结构和预定义的测试用例集合
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class TestCase:
    """
    测试用例数据类
    
    定义单个测试用例的所有必要信息，包括测试问题、期望结果等
    
    Attributes:
        name: 测试用例名称
        description: 测试用例描述
        question: 测试问题
        expected_question_type: 期望的问题类型（可选）
        expected_dimensions: 期望的维度列表（可选）
        expected_measures: 期望的度量列表（可选）
        expected_time_range: 期望的时间范围（可选）
        complexity: 复杂度（simple, medium, complex）
        tags: 标签列表，用于分类和筛选
        enabled: 是否启用此测试用例
    """
    name: str
    description: str
    question: str
    expected_question_type: Optional[str] = None
    expected_dimensions: Optional[List[str]] = None
    expected_measures: Optional[List[str]] = None
    expected_time_range: Optional[Dict[str, Any]] = None
    complexity: str = "simple"
    tags: List[str] = field(default_factory=list)
    enabled: bool = True
    
    def __post_init__(self):
        """验证数据"""
        if self.complexity not in ["simple", "medium", "complex"]:
            raise ValueError(f"Invalid complexity: {self.complexity}")
        
        if not self.question or not self.question.strip():
            raise ValueError("Question cannot be empty")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "question": self.question,
            "expected_question_type": self.expected_question_type,
            "expected_dimensions": self.expected_dimensions,
            "expected_measures": self.expected_measures,
            "expected_time_range": self.expected_time_range,
            "complexity": self.complexity,
            "tags": self.tags,
            "enabled": self.enabled
        }


# ============= 预定义测试用例 =============

# 简单查询测试用例
SIMPLE_QUERY_CASES = [
    TestCase(
        name="简单聚合查询",
        description="测试单维度、单度量的简单聚合查询",
        question="显示各地区的销售额",
        expected_question_type="aggregation",
        expected_dimensions=["地区"],
        expected_measures=["销售额"],
        complexity="simple",
        tags=["aggregation", "simple"]
    ),
    TestCase(
        name="简单计数查询",
        description="测试记录计数查询",
        question="每个产品类别有多少个产品",
        expected_question_type="aggregation",
        expected_dimensions=["产品类别"],
        expected_measures=["产品数量"],
        complexity="simple",
        tags=["count", "simple"]
    ),
]

# 时间序列测试用例
TIME_SERIES_CASES = [
    TestCase(
        name="月度趋势分析",
        description="测试包含时间维度的趋势分析",
        question="显示最近6个月的销售趋势",
        expected_question_type="trend",
        expected_dimensions=["月份"],
        expected_measures=["销售额"],
        expected_time_range={"type": "relative", "value": "last_6_months"},
        complexity="medium",
        tags=["time_series", "trend"]
    ),
    TestCase(
        name="年度对比分析",
        description="测试跨年度的对比分析",
        question="对比2023年和2024年的销售额",
        expected_question_type="comparison",
        expected_dimensions=["年份"],
        expected_measures=["销售额"],
        expected_time_range={"type": "absolute", "years": [2023, 2024]},
        complexity="medium",
        tags=["time_series", "comparison"]
    ),
]

# 复杂聚合测试用例
COMPLEX_AGGREGATION_CASES = [
    TestCase(
        name="多维度聚合",
        description="测试多维度、多度量的复杂聚合",
        question="显示各地区各产品类别的销售额和利润",
        expected_question_type="aggregation",
        expected_dimensions=["地区", "产品类别"],
        expected_measures=["销售额", "利润"],
        complexity="complex",
        tags=["aggregation", "multi_dimension"]
    ),
    TestCase(
        name="带筛选的聚合",
        description="测试包含复杂筛选条件的聚合查询",
        question="显示销售额大于10000的地区的平均利润率",
        expected_question_type="aggregation",
        expected_dimensions=["地区"],
        expected_measures=["利润率"],
        complexity="complex",
        tags=["aggregation", "filter"]
    ),
]

# 排名分析测试用例
RANKING_CASES = [
    TestCase(
        name="Top N查询",
        description="测试排名和Top N查询",
        question="显示销售额前10的产品",
        expected_question_type="ranking",
        expected_dimensions=["产品名称"],
        expected_measures=["销售额"],
        complexity="medium",
        tags=["ranking", "top_n"]
    ),
    TestCase(
        name="排序查询",
        description="测试带排序的查询",
        question="按利润从高到低显示所有产品类别",
        expected_question_type="ranking",
        expected_dimensions=["产品类别"],
        expected_measures=["利润"],
        complexity="simple",
        tags=["ranking", "sort"]
    ),
]

# 对比分析测试用例
COMPARISON_CASES = [
    TestCase(
        name="同比分析",
        description="测试同比增长分析",
        question="对比今年和去年同期的销售额增长率",
        expected_question_type="comparison",
        expected_dimensions=["时间"],
        expected_measures=["销售额", "增长率"],
        complexity="complex",
        tags=["comparison", "yoy"]
    ),
    TestCase(
        name="环比分析",
        description="测试环比增长分析",
        question="显示每月销售额的环比变化",
        expected_question_type="comparison",
        expected_dimensions=["月份"],
        expected_measures=["销售额", "环比变化"],
        complexity="medium",
        tags=["comparison", "mom"]
    ),
]

# 所有测试用例集合
ALL_TEST_CASES = (
    SIMPLE_QUERY_CASES +
    TIME_SERIES_CASES +
    COMPLEX_AGGREGATION_CASES +
    RANKING_CASES +
    COMPARISON_CASES
)


def get_test_cases_by_tag(tag: str) -> List[TestCase]:
    """
    根据标签获取测试用例
    
    Args:
        tag: 标签名称
    
    Returns:
        匹配的测试用例列表
    """
    return [case for case in ALL_TEST_CASES if tag in case.tags]


def get_test_cases_by_complexity(complexity: str) -> List[TestCase]:
    """
    根据复杂度获取测试用例
    
    Args:
        complexity: 复杂度（simple, medium, complex）
    
    Returns:
        匹配的测试用例列表
    """
    return [case for case in ALL_TEST_CASES if case.complexity == complexity]


def get_enabled_test_cases() -> List[TestCase]:
    """
    获取所有启用的测试用例
    
    Returns:
        启用的测试用例列表
    """
    return [case for case in ALL_TEST_CASES if case.enabled]


# ============= 导出 =============

__all__ = [
    "TestCase",
    "SIMPLE_QUERY_CASES",
    "TIME_SERIES_CASES",
    "COMPLEX_AGGREGATION_CASES",
    "RANKING_CASES",
    "COMPARISON_CASES",
    "ALL_TEST_CASES",
    "get_test_cases_by_tag",
    "get_test_cases_by_complexity",
    "get_enabled_test_cases",
]
