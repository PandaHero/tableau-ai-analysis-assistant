"""
数据处理能力

提供查询结果的后处理功能，包括同比、环比、增长率等计算。

主要组件：
- DataProcessor: 数据处理器，执行各种数据处理操作
- StatisticsDetector: 统计检测器，检测数据的统计特征
- ProcessorFactory: 处理器工厂，创建各种处理器实例

处理类型：
- yoy: 同比计算
- mom: 环比计算
- growth_rate: 增长率计算
- percentage: 百分比计算
- custom: 自定义计算

使用示例：
    from tableau_assistant.src.capabilities.data_processing import DataProcessor
    
    processor = DataProcessor()
    result = processor.process(data, processing_type="yoy")
"""
from tableau_assistant.src.capabilities.data_processing.processor import DataProcessor
from tableau_assistant.src.capabilities.data_processing.statistics import StatisticsDetector
from tableau_assistant.src.capabilities.data_processing.factory import ProcessorFactory
from tableau_assistant.src.capabilities.data_processing.base import ProcessorBase

__all__ = [
    "DataProcessor",
    "StatisticsDetector",
    "ProcessorFactory",
    "ProcessorBase",
]
