"""
筛选器转换器模块

负责将FilterIntent和TopNIntent转换为VizQLFilter。

转换规则：
- FilterIntent (filter_type="SET") → SetFilter
- FilterIntent (filter_type="QUANTITATIVE") → QuantitativeNumericalFilter
- FilterIntent (filter_type="MATCH") → MatchFilter
- TopNIntent → TopNFilter
"""
import logging
from typing import Union
from tableau_assistant.src.models.intent import (
    FilterIntent,
    TopNIntent,
)
from tableau_assistant.src.models.vizql_types import (
    SetFilter,
    QuantitativeNumericalFilter,
    MatchFilter,
    TopNFilter,
    FilterField,
    VizQLFilter,
)
from tableau_assistant.src.models.metadata import Metadata

logger = logging.getLogger(__name__)


class FilterConverter:
    """
    筛选器转换器
    
    将FilterIntent和TopNIntent转换为VizQLFilter。
    """
    
    def __init__(self, metadata: Metadata):
        """
        初始化筛选器转换器
        
        Args:
            metadata: Metadata模型对象
        """
        self.metadata = metadata
    
    def convert_filter_intent(self, intent: FilterIntent) -> VizQLFilter:
        """
        转换筛选意图为VizQL筛选器
        
        规则：
        - filter_type="SET" → SetFilter
        - filter_type="QUANTITATIVE" → QuantitativeNumericalFilter
        - filter_type="MATCH" → MatchFilter
        
        Args:
            intent: FilterIntent对象
        
        Returns:
            VizQLFilter对象
        
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
            
            # 根据filter_type选择转换方法
            if intent.filter_type == "SET":
                return self._convert_set_filter(intent)
            elif intent.filter_type == "QUANTITATIVE":
                return self._convert_quantitative_filter(intent)
            elif intent.filter_type == "MATCH":
                return self._convert_match_filter(intent)
            else:
                raise ValueError(f"不支持的filter_type: {intent.filter_type}")
        
        except Exception as e:
            raise ValueError(
                f"转换筛选意图失败: {intent.technical_field}, 错误: {e}"
            ) from e
    
    def _convert_set_filter(self, intent: FilterIntent) -> SetFilter:
        """
        转换为SetFilter（集合筛选）
        
        Args:
            intent: FilterIntent对象
        
        Returns:
            SetFilter对象
        """
        if not intent.values:
            raise ValueError(
                f"SET类型筛选器缺少values字段: {intent.technical_field}"
            )
        
        logger.debug(
            f"转换为SetFilter: {intent.technical_field} "
            f"(values={intent.values}, exclude={intent.exclude})"
        )
        
        return SetFilter(
            field=FilterField(fieldCaption=intent.technical_field),
            filterType="SET",
            values=intent.values,
            exclude=intent.exclude or False
        )
    
    def _convert_quantitative_filter(
        self,
        intent: FilterIntent
    ) -> QuantitativeNumericalFilter:
        """
        转换为QuantitativeNumericalFilter（数值范围筛选）
        
        Args:
            intent: FilterIntent对象
        
        Returns:
            QuantitativeNumericalFilter对象
        """
        if not intent.quantitative_filter_type:
            raise ValueError(
                f"QUANTITATIVE类型筛选器缺少quantitative_filter_type字段: "
                f"{intent.technical_field}"
            )
        
        logger.debug(
            f"转换为QuantitativeNumericalFilter: {intent.technical_field} "
            f"(type={intent.quantitative_filter_type}, "
            f"min={intent.min_value}, max={intent.max_value})"
        )
        
        return QuantitativeNumericalFilter(
            field=FilterField(fieldCaption=intent.technical_field),
            filterType="QUANTITATIVE_NUMERICAL",
            quantitativeFilterType=intent.quantitative_filter_type,
            min=intent.min_value,
            max=intent.max_value,
            includeNulls=intent.include_nulls
        )
    
    def _convert_match_filter(self, intent: FilterIntent) -> MatchFilter:
        """
        转换为MatchFilter（文本匹配筛选）
        
        Args:
            intent: FilterIntent对象
        
        Returns:
            MatchFilter对象
        """
        if not intent.match_type or not intent.match_value:
            raise ValueError(
                f"MATCH类型筛选器缺少match_type或match_value字段: "
                f"{intent.technical_field}"
            )
        
        # 构建匹配参数
        match_kwargs = {}
        if intent.match_type == "startsWith":
            match_kwargs["startsWith"] = intent.match_value
        elif intent.match_type == "endsWith":
            match_kwargs["endsWith"] = intent.match_value
        elif intent.match_type == "contains":
            match_kwargs["contains"] = intent.match_value
        
        logger.debug(
            f"转换为MatchFilter: {intent.technical_field} "
            f"({intent.match_type}={intent.match_value}, "
            f"exclude={intent.match_exclude})"
        )
        
        return MatchFilter(
            field=FilterField(fieldCaption=intent.technical_field),
            filterType="MATCH",
            exclude=intent.match_exclude or False,
            **match_kwargs
        )
    
    def convert_topn_intent(self, intent: TopNIntent) -> TopNFilter:
        """
        转换TopN意图为TopNFilter
        
        Args:
            intent: TopNIntent对象
        
        Returns:
            TopNFilter对象
        
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
            
            logger.debug(
                f"转换为TopNFilter: {intent.technical_field} "
                f"(n={intent.n}, direction={intent.direction})"
            )
            
            return TopNFilter(
                field=FilterField(fieldCaption=intent.technical_field),
                filterType="TOP",
                howMany=intent.n,
                fieldToMeasure=FilterField(fieldCaption=intent.technical_field),
                direction=intent.direction
            )
        
        except Exception as e:
            raise ValueError(
                f"转换TopN意图失败: {intent.technical_field}, 错误: {e}"
            ) from e


# ============= 导出 =============

__all__ = [
    "FilterConverter",
]
