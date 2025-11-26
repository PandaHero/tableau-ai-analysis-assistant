"""
数据处理器基类

定义所有数据处理器的通用接口
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class ProcessorBase(ABC):
    """
    数据处理器基类
    
    所有具体处理器必须继承此类并实现抽象方法
    """
    
    @abstractmethod
    def process(
        self, 
        source_data: Dict[str, pd.DataFrame], 
        instruction: Any
    ) -> pd.DataFrame:
        """
        执行数据处理
        
        Args:
            source_data: 源数据字典 {task_id: dataframe}
            instruction: 处理指令（ProcessingInstruction实例）
            
        Returns:
            处理后的数据（Pandas DataFrame）
            
        Raises:
            ValidationError: 输入数据验证失败
            CalculationError: 计算过程出错
        """
        pass
    
    @abstractmethod
    def validate_instruction(self, instruction: Any) -> bool:
        """
        验证处理指令是否有效
        
        Args:
            instruction: 处理指令
            
        Returns:
            是否有效
        """
        pass
    
    def _validate_source_data(
        self,
        source_data: Dict[str, pd.DataFrame],
        required_tasks: list
    ) -> None:
        """
        验证源数据是否完整
        
        Args:
            source_data: 源数据字典
            required_tasks: 必需的任务ID列表
            
        Raises:
            ValidationError: 数据验证失败
        """
        from tableau_assistant.src.components.data_processor.exceptions import ValidationError
        
        for task_id in required_tasks:
            if task_id not in source_data:
                raise ValidationError(f"Missing source data for task {task_id}")
            
            df = source_data[task_id]
            if df.empty:
                raise ValidationError(f"Empty data from task {task_id}")
    
    def _get_field_info_from_subtask(
        self,
        subtask: Any,  # QuerySubTask
        df: pd.DataFrame
    ) -> tuple[list[str], list[str]]:
        """
        从 QuerySubTask 的 fields 中获取维度和度量信息
        
        Args:
            subtask: QuerySubTask 实例
            df: 数据框（用于验证列名）
            
        Returns:
            (dimension_cols, measure_cols) 元组
        """
        from tableau_assistant.src.models.vizql_types import BasicField, FunctionField
        
        dimension_cols = []
        measure_cols = []
        
        # 从 subtask.fields 中识别维度和度量
        for field in subtask.fields:
            field_name = field.fieldCaption
            
            # 检查字段是否在数据框中
            if field_name not in df.columns:
                logger.warning(f"Field {field_name} not found in dataframe columns")
                continue
            
            if isinstance(field, BasicField):
                # BasicField 是维度
                dimension_cols.append(field_name)
            elif isinstance(field, FunctionField):
                # FunctionField 是度量
                measure_cols.append(field_name)
        
        logger.debug(
            f"Identified from subtask: {len(dimension_cols)} dimensions, "
            f"{len(measure_cols)} measures"
        )
        
        return dimension_cols, measure_cols


# ============= 导出 =============

__all__ = [
    "ProcessorBase",
]
