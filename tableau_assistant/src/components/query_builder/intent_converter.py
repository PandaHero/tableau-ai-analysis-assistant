"""
Intent转换器模块

负责将Intent模型转换为VizQLField对象。

转换规则：
- DimensionIntent → BasicField（无聚合）或 FunctionField（有聚合）
- MeasureIntent → FunctionField（必须有聚合）
- DateFieldIntent → BasicField（无日期函数）或 FunctionField（有日期函数）
"""
import logging
from typing import Union
from tableau_assistant.src.models.intent import (
    DimensionIntent,
    MeasureIntent,
    DateFieldIntent,
)
from tableau_assistant.src.models.vizql_types import (
    BasicField,
    FunctionField,
    FunctionEnum,
    SortDirection,
    VizQLField,
)
from tableau_assistant.src.models.metadata import Metadata

logger = logging.getLogger(__name__)


class IntentConverter:
    """
    Intent转换器
    
    将Intent模型转换为VizQLField对象。
    """
    
    def __init__(self, metadata: Metadata):
        """
        初始化Intent转换器
        
        Args:
            metadata: Metadata模型对象
        """
        self.metadata = metadata
    
    def convert_dimension_intent(self, intent: DimensionIntent) -> VizQLField:
        """
        转换维度意图为VizQLField
        
        规则：
        - 如果有aggregation（COUNT、COUNTD、MIN、MAX），生成FunctionField
        - 否则生成BasicField
        
        Args:
            intent: DimensionIntent对象
        
        Returns:
            BasicField或FunctionField对象
        
        Raises:
            ValueError: 如果字段不存在或转换失败
        """
        try:
            # 验证字段存在
            field_meta = self.metadata.get_field(intent.technical_field)
            if not field_meta:
                raise ValueError(
                    f"字段 '{intent.technical_field}' 不存在于元数据中。"
                    f"可用字段: {[f.name for f in self.metadata.fields]}"
                )
            
            # 转换排序方向
            sort_direction = None
            if intent.sort_direction:
                sort_direction = SortDirection[intent.sort_direction]
            
            # 根据是否有聚合函数决定生成类型
            if intent.aggregation:
                logger.debug(
                    f"转换维度意图为FunctionField: {intent.technical_field} "
                    f"(aggregation={intent.aggregation})"
                )
                return FunctionField(
                    fieldCaption=intent.technical_field,
                    function=FunctionEnum[intent.aggregation],
                    sortDirection=sort_direction,
                    sortPriority=intent.sort_priority
                )
            else:
                logger.debug(
                    f"转换维度意图为BasicField: {intent.technical_field}"
                )
                return BasicField(
                    fieldCaption=intent.technical_field,
                    sortDirection=sort_direction,
                    sortPriority=intent.sort_priority
                )
        
        except KeyError as e:
            raise ValueError(
                f"无效的聚合函数或排序方向: {e}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"转换维度意图失败: {intent.technical_field}, 错误: {e}"
            ) from e
    
    def convert_measure_intent(self, intent: MeasureIntent) -> FunctionField:
        """
        转换度量意图为FunctionField
        
        规则：
        - 度量必须有聚合函数，生成FunctionField
        
        Args:
            intent: MeasureIntent对象
        
        Returns:
            FunctionField对象
        
        Raises:
            ValueError: 如果字段不存在或转换失败
        """
        try:
            # 验证字段存在
            field_meta = self.metadata.get_field(intent.technical_field)
            if not field_meta:
                raise ValueError(
                    f"字段 '{intent.technical_field}' 不存在于元数据中。"
                    f"可用字段: {[f.name for f in self.metadata.fields]}"
                )
            
            # 转换排序方向
            sort_direction = None
            if intent.sort_direction:
                sort_direction = SortDirection[intent.sort_direction]
            
            logger.debug(
                f"转换度量意图为FunctionField: {intent.technical_field} "
                f"(aggregation={intent.aggregation})"
            )
            
            return FunctionField(
                fieldCaption=intent.technical_field,
                function=FunctionEnum[intent.aggregation],
                sortDirection=sort_direction,
                sortPriority=intent.sort_priority
            )
        
        except KeyError as e:
            raise ValueError(
                f"无效的聚合函数或排序方向: {e}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"转换度量意图失败: {intent.technical_field}, 错误: {e}"
            ) from e
    
    def convert_date_field_intent(self, intent: DateFieldIntent) -> VizQLField:
        """
        转换日期字段意图为VizQLField
        
        规则：
        - 如果有date_function（YEAR、MONTH、QUARTER等），生成FunctionField
        - 否则生成BasicField
        
        注意：STRING类型日期字段的DATEPARSE处理由QueryBuilder负责
        
        Args:
            intent: DateFieldIntent对象
        
        Returns:
            BasicField或FunctionField对象
        
        Raises:
            ValueError: 如果字段不存在或转换失败
        """
        try:
            # 验证字段存在
            field_meta = self.metadata.get_field(intent.technical_field)
            if not field_meta:
                raise ValueError(
                    f"字段 '{intent.technical_field}' 不存在于元数据中。"
                    f"可用字段: {[f.name for f in self.metadata.fields]}"
                )
            
            # 转换排序方向
            sort_direction = None
            if intent.sort_direction:
                sort_direction = SortDirection[intent.sort_direction]
            
            # 根据是否有日期函数决定生成类型
            if intent.date_function:
                logger.debug(
                    f"转换日期字段意图为FunctionField: {intent.technical_field} "
                    f"(date_function={intent.date_function})"
                )
                return FunctionField(
                    fieldCaption=intent.technical_field,
                    function=FunctionEnum[intent.date_function],
                    sortDirection=sort_direction,
                    sortPriority=intent.sort_priority
                )
            else:
                logger.debug(
                    f"转换日期字段意图为BasicField: {intent.technical_field}"
                )
                return BasicField(
                    fieldCaption=intent.technical_field,
                    sortDirection=sort_direction,
                    sortPriority=intent.sort_priority
                )
        
        except KeyError as e:
            raise ValueError(
                f"无效的日期函数或排序方向: {e}"
            ) from e
        except Exception as e:
            raise ValueError(
                f"转换日期字段意图失败: {intent.technical_field}, 错误: {e}"
            ) from e


# ============= 导出 =============

__all__ = [
    "IntentConverter",
]
