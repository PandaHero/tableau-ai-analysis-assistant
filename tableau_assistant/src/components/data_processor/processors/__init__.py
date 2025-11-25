"""
数据处理器实现

包含各种类型的数据处理器
"""
from tableau_assistant.src.components.data_processor.processors.yoy import YoYProcessor
from tableau_assistant.src.components.data_processor.processors.mom import MoMProcessor
from tableau_assistant.src.components.data_processor.processors.growth_rate import GrowthRateProcessor
from tableau_assistant.src.components.data_processor.processors.percentage import PercentageProcessor
from tableau_assistant.src.components.data_processor.processors.custom import CustomProcessor

__all__ = [
    "YoYProcessor",
    "MoMProcessor",
    "GrowthRateProcessor",
    "PercentageProcessor",
    "CustomProcessor",
]
