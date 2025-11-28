"""
处理器工厂

根据处理类型创建相应的处理器实例
"""
from typing import Dict, Type
import logging

from tableau_assistant.src.capabilities.data_processing.processor.base import ProcessorBase

logger = logging.getLogger(__name__)


class ProcessorFactory:
    """
    处理器工厂
    
    根据processing_type创建相应的处理器实例
    """
    
    # 处理器注册表 {ProcessingType: ProcessorClass}
    _processors: Dict[str, Type[ProcessorBase]] = {}
    
    @classmethod
    def register_processor(
        cls,
        processing_type: str,
        processor_class: Type[ProcessorBase]
    ) -> None:
        """
        注册处理器
        
        Args:
            processing_type: 处理类型（如 "yoy", "mom"）
            processor_class: 处理器类
        """
        cls._processors[processing_type] = processor_class
        logger.debug(f"Registered processor: {processing_type} -> {processor_class.__name__}")
    
    @classmethod
    def create_processor(cls, processing_type: str) -> ProcessorBase:
        """
        创建处理器实例
        
        Args:
            processing_type: 处理类型
            
        Returns:
            处理器实例
            
        Raises:
            ValueError: 不支持的处理类型
        """
        processor_class = cls._processors.get(processing_type)
        
        if not processor_class:
            raise ValueError(
                f"Unsupported processing type: {processing_type}. "
                f"Available types: {list(cls._processors.keys())}"
            )
        
        logger.debug(f"Creating processor for type: {processing_type}")
        return processor_class()
    
    @classmethod
    def get_supported_types(cls) -> list[str]:
        """
        获取支持的处理类型列表
        
        Returns:
            处理类型列表
        """
        return list(cls._processors.keys())


# ============= 导出 =============

__all__ = [
    "ProcessorFactory",
]
