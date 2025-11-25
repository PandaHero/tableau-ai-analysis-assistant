"""
日期筛选转换器模块

负责将DateFilterIntent转换为VizQL日期筛选器。

转换规则：
- DATE/DATETIME + relative → RelativeDateFilter
- DATE/DATETIME + absolute → QuantitativeDateFilter
- STRING + any → QuantitativeDateFilter + DATEPARSE字段
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from tableau_assistant.src.models.intent import DateFilterIntent
from tableau_assistant.src.models.vizql_types import (
    RelativeDateFilter,
    QuantitativeDateFilter,
    FilterField,
    CalculationField,
    VizQLFilter,
    create_dateparse_field,
)
from tableau_assistant.src.models.metadata import Metadata
from tableau_assistant.src.utils.date_calculator import DateCalculator

logger = logging.getLogger(__name__)


# 日期格式模式常量
DATE_FORMAT_PATTERNS = {
    r'^\d{4}-\d{2}-\d{2}$': 'yyyy-MM-dd',           # 2024-03-15
    r'^\d{4}/\d{2}/\d{2}$': 'yyyy/MM/dd',           # 2024/03/15
    r'^\d{2}/\d{2}/\d{4}$': 'dd/MM/yyyy',           # 15/03/2024
    r'^\d{2}-\d{2}-\d{4}$': 'dd-MM-yyyy',           # 15-03-2024
    r'^\d{4}\d{2}\d{2}$': 'yyyyMMdd',               # 20240315
    r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$': 'yyyy-MM-dd HH:mm:ss',  # 2024-03-15 10:30:00
}


class DateFilterConverter:
    """
    日期筛选转换器
    
    将DateFilterIntent转换为VizQL日期筛选器。
    """
    
    def __init__(
        self,
        metadata: Metadata,
        anchor_date: Optional[datetime] = None,
        week_start_day: int = 0
    ):
        """
        初始化日期筛选转换器
        
        Args:
            metadata: Metadata模型对象
            anchor_date: 锚点日期（数据最新日期）
            week_start_day: 周开始日（0=周一，6=周日）
        """
        self.metadata = metadata
        self.anchor_date = anchor_date
        self.week_start_day = week_start_day
        self.date_calculator = DateCalculator(
            anchor_date=anchor_date,
            week_start_day=week_start_day
        )
        
        # 创建 DateParser 实例
        from tableau_assistant.src.components.date_parser import DateParser
        self.date_parser = DateParser(date_calculator=self.date_calculator)
    
    def convert(
        self,
        intent: DateFilterIntent
    ) -> Tuple[Optional[VizQLFilter], Optional[CalculationField]]:
        """
        转换日期筛选意图为VizQL筛选器
        
        返回：
        - VizQL筛选器（RelativeDateFilter或QuantitativeDateFilter）
        - DATEPARSE计算字段（如果需要，用于STRING类型日期字段）
        
        规则：
        - DATE/DATETIME + relative → RelativeDateFilter
        - DATE/DATETIME + absolute → QuantitativeDateFilter
        - STRING + any → QuantitativeDateFilter + DATEPARSE字段
        
        Args:
            intent: DateFilterIntent对象
        
        Returns:
            (VizQLFilter, CalculationField) 元组
        
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
            
            # 根据字段类型选择策略
            if field_meta.dataType in ("DATE", "DATETIME"):
                logger.debug(
                    f"转换原生日期字段: {intent.technical_field} "
                    f"(type={field_meta.dataType})"
                )
                return self._convert_native_date_field(intent, field_meta.dataType)
            else:
                logger.debug(
                    f"转换STRING类型日期字段: {intent.technical_field}"
                )
                return self._convert_string_date_field(intent, field_meta)
        
        except Exception as e:
            raise ValueError(
                f"转换日期筛选意图失败: {intent.technical_field}, 错误: {e}"
            ) from e
    
    def _convert_native_date_field(
        self,
        intent: DateFilterIntent,
        field_data_type: str
    ) -> Tuple[VizQLFilter, None]:
        """
        处理原生DATE/DATETIME字段
        
        Args:
            intent: DateFilterIntent对象
            field_data_type: 字段数据类型
        
        Returns:
            (VizQLFilter, None) 元组
        """
        time_range = intent.time_range
        
        # 根据时间范围类型选择筛选器类型
        if time_range.type == "relative":
            # 相对时间 → RelativeDateFilter
            logger.debug(
                f"生成RelativeDateFilter: {time_range.relative_type} "
                f"{time_range.period_type}"
            )
            
            filter_obj = RelativeDateFilter(
                field=FilterField(fieldCaption=intent.technical_field),
                filterType="DATE",
                dateRangeType=time_range.relative_type.value,
                periodType=time_range.period_type.value,
                rangeN=time_range.range_n,
                anchorDate=self.anchor_date.isoformat() if self.anchor_date else None
            )
            return filter_obj, None
        
        else:
            # 绝对时间 → QuantitativeDateFilter
            # 需要计算具体的日期范围
            start_date, end_date = self._calculate_date_range(intent)
            
            logger.debug(
                f"生成QuantitativeDateFilter: {start_date} ~ {end_date}"
            )
            
            filter_obj = QuantitativeDateFilter(
                field=FilterField(fieldCaption=intent.technical_field),
                filterType="QUANTITATIVE_DATE",
                quantitativeFilterType="RANGE",
                minDate=start_date,
                maxDate=end_date
            )
            return filter_obj, None
    
    def _convert_string_date_field(
        self,
        intent: DateFilterIntent,
        field_meta
    ) -> Tuple[VizQLFilter, None]:
        """
        处理STRING类型日期字段
        
        步骤：
        1. 检测日期格式
        2. 生成DATEPARSE calculation
        3. 计算日期范围
        4. 生成QuantitativeDateFilter（直接在FilterField中使用calculation）
        
        注意：根据SDK文档，筛选器中的STRING日期字段应该直接在FilterField中使用calculation，
        而不是创建单独的CalculationField。
        
        Args:
            intent: DateFilterIntent对象
            field_meta: FieldMetadata对象
        
        Returns:
            (VizQLFilter, None) 元组
        """
        # 1. 检测日期格式
        date_format = self.detect_date_format(field_meta.sample_values or [])
        if not date_format:
            raise ValueError(
                f"无法识别字段 '{intent.technical_field}' 的日期格式。"
                f"样本值: {field_meta.sample_values[:3] if field_meta.sample_values else []}"
            )
        
        logger.debug(f"检测到日期格式: {date_format}")
        
        # 2. 生成DATEPARSE calculation
        dateparse_calculation = f"DATEPARSE('{date_format}', [{intent.technical_field}])"
        
        logger.debug(
            f"生成DATEPARSE calculation: {dateparse_calculation}"
        )
        
        # 3. 计算日期范围
        start_date, end_date = self._calculate_date_range(intent)
        
        # 4. 生成QuantitativeDateFilter（直接在FilterField中使用calculation）
        filter_obj = QuantitativeDateFilter(
            field=FilterField(calculation=dateparse_calculation),
            filterType="QUANTITATIVE_DATE",
            quantitativeFilterType="RANGE",
            minDate=start_date,
            maxDate=end_date
        )
        
        logger.debug(
            f"生成QuantitativeDateFilter: {start_date} ~ {end_date}"
        )
        
        return filter_obj, None
    
    def _calculate_date_range(
        self,
        intent: DateFilterIntent
    ) -> Tuple[str, str]:
        """
        计算日期范围
        
        使用 DateParser 组件计算具体的开始和结束日期。
        
        Args:
            intent: DateFilterIntent对象
        
        Returns:
            (start_date, end_date) 元组
        """
        time_range = intent.time_range
        
        # 获取参考日期（优先级：anchor_date > field.valid_max_date > metadata.get_reference_date）
        reference_date = self._get_reference_date(intent.technical_field)
        
        # 获取数据源最大日期（用于边界调整）
        max_date = self._get_max_date(intent.technical_field)
        
        # 使用 DateParser 计算日期范围
        start_date, end_date = self.date_parser.calculate_date_range(
            time_range=time_range,
            reference_date=reference_date,
            max_date=max_date
        )
        
        logger.debug(
            f"日期范围计算完成: {intent.technical_field} → "
            f"{start_date} to {end_date} (reference: {reference_date.date() if reference_date else 'None'})"
        )
        
        return start_date, end_date
    
    def _get_reference_date(self, field_name: str) -> Optional[datetime]:
        """
        获取参考日期（用于相对时间计算）
        
        优先级：
        1. self.anchor_date（构造函数传入）
        2. field.valid_max_date（字段的最大日期）
        3. metadata.get_reference_date(field_name)（智能选择）
        4. None（DateParser 会使用默认值）
        
        Args:
            field_name: 字段名称
        
        Returns:
            参考日期（datetime 对象）或 None
        """
        # 优先级1: 构造函数传入的 anchor_date
        if self.anchor_date:
            return self.anchor_date
        
        # 优先级2: 字段的 valid_max_date
        field_meta = self.metadata.get_field(field_name)
        if field_meta and field_meta.valid_max_date:
            try:
                return datetime.fromisoformat(field_meta.valid_max_date)
            except ValueError:
                logger.warning(f"无法解析 valid_max_date: {field_meta.valid_max_date}")
        
        # 优先级3: metadata.get_reference_date（智能选择）
        reference_date_str = self.metadata.get_reference_date(mentioned_field=field_name)
        if reference_date_str:
            try:
                return datetime.fromisoformat(reference_date_str)
            except ValueError:
                logger.warning(f"无法解析 reference_date: {reference_date_str}")
        
        # 优先级4: None（DateParser 会使用默认值：当前日期-1）
        return None
    
    def _get_max_date(self, field_name: str) -> Optional[str]:
        """
        获取数据源最大日期（用于边界调整）
        
        Args:
            field_name: 字段名称
        
        Returns:
            最大日期字符串（YYYY-MM-DD）或 None
        """
        field_meta = self.metadata.get_field(field_name)
        if field_meta and field_meta.valid_max_date:
            return field_meta.valid_max_date
        
        # 尝试从 metadata 获取
        reference_date_str = self.metadata.get_reference_date(mentioned_field=field_name)
        if reference_date_str:
            return reference_date_str
        
        return None
    

    def detect_date_format(self, sample_values: List[str]) -> Optional[str]:
        """
        检测日期格式
        
        使用样本值匹配预定义的日期格式模式。
        
        Args:
            sample_values: 样本值列表
        
        Returns:
            日期格式字符串，如果无法识别则返回None
        """
        if not sample_values:
            return None
        
        # 取前5个样本值进行匹配
        samples = sample_values[:5]
        
        for pattern, format_str in DATE_FORMAT_PATTERNS.items():
            # 检查所有样本值是否都匹配该模式
            if all(re.match(pattern, str(val)) for val in samples if val):
                logger.debug(
                    f"匹配到日期格式: {format_str} (pattern={pattern})"
                )
                return format_str
        
        logger.warning(
            f"无法识别日期格式，样本值: {samples}"
        )
        return None


# ============= 导出 =============

__all__ = [
    "DateFilterConverter",
    "DATE_FORMAT_PATTERNS",
]
