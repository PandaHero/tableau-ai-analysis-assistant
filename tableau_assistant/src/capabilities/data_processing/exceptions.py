"""
数据处理器异常类

定义数据处理过程中可能出现的各种异常
"""


class ProcessingError(Exception):
    """数据处理错误基类"""
    pass


class ValidationError(ProcessingError):
    """
    验证错误
    
    当输入数据或指令验证失败时抛出
    """
    pass


class CalculationError(ProcessingError):
    """
    计算错误
    
    当数据计算过程中出现错误时抛出
    """
    pass


class DependencyError(ProcessingError):
    """
    依赖错误
    
    当任务依赖关系不满足时抛出
    """
    pass


# ============= 导出 =============

__all__ = [
    "ProcessingError",
    "ValidationError",
    "CalculationError",
    "DependencyError",
]
