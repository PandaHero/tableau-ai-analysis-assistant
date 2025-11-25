"""
数据处理器模块

提供数据处理功能，支持同比、环比、增长率、占比等计算

数据流：
    QueryResult (多个) → DataProcessor → ProcessingResult (单个)
"""
from tableau_assistant.src.components.data_processor.base import ProcessorBase
from tableau_assistant.src.components.data_processor.factory import ProcessorFactory
from tableau_assistant.src.components.data_processor.processor import DataProcessor
from tableau_assistant.src.components.data_processor.exceptions import (
    ProcessingError,
    ValidationError,
    CalculationError,
    DependencyError
)

# 导入所有处理器
from tableau_assistant.src.components.data_processor.processors import (
    YoYProcessor,
    MoMProcessor,
    GrowthRateProcessor,
    PercentageProcessor,
    CustomProcessor
)

# 注册所有处理器
ProcessorFactory.register_processor("yoy", YoYProcessor)
ProcessorFactory.register_processor("mom", MoMProcessor)
ProcessorFactory.register_processor("growth_rate", GrowthRateProcessor)
ProcessorFactory.register_processor("percentage", PercentageProcessor)
ProcessorFactory.register_processor("custom", CustomProcessor)


__all__ = [
    # 基础类
    "ProcessorBase",
    "ProcessorFactory",
    "DataProcessor",
    
    # 异常类
    "ProcessingError",
    "ValidationError",
    "CalculationError",
    "DependencyError",
    
    # 处理器
    "YoYProcessor",
    "MoMProcessor",
    "GrowthRateProcessor",
    "PercentageProcessor",
    "CustomProcessor",
]
