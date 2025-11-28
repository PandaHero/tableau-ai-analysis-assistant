"""
日期筛选转换器模块

负责将DateFilterIntent转换为VizQL日期筛选器。

转换规则：
- DATE/DATETIME + relative → RelativeDateFilter
- DATE/DATETIME + absolute → QuantitativeDateFilter
- STRING + any → 根据粒度关系选择最优策略（MatchFilter/SetFilter/QuantitativeDateFilter）
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, TYPE_CHECKING

if TYPE_CHECKING:
    from tableau_assistant.src.capabilities.date_processing.manager import DateManager

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
from tableau_assistant.src.capabilities.date_processing.calculator import DateCalculator
from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import StringDateFilterBuilder

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
        week_start_day: int = 0,
        date_manager: Optional['DateManager'] = None
    ):
        """
        初始化日期筛选转换器
        
        Args:
            metadata: Metadata模型对象
            anchor_date: 锚点日期（数据最新日期）
            week_start_day: 周开始日（0=周一，6=周日）
            date_manager: 日期管理器（可选，用于处理STRING类型日期字段）
        """
        self.metadata = metadata
        self.anchor_date = anchor_date
        self.week_start_day = week_start_day
        self.date_manager = date_manager
        self.date_calculator = DateCalculator(
            anchor_date=anchor_date,
            week_start_day=week_start_day
        )
        
        # 创建 DateParser 实例
        from tableau_assistant.src.capabilities.date_processing.parser import DateParser
        self.date_parser = DateParser(date_calculator=self.date_calculator)
        
        # 创建 StringDateFilterBuilder 实例
        self.string_date_filter_builder = StringDateFilterBuilder()
    
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
        
        新策略：根据字段粒度和问题粒度的关系选择最优筛选器：
        1. 使用 DateManager 获取字段格式和粒度
        2. 计算日期范围
        3. 使用 StringDateFilterBuilder 构建最优筛选器
           - MatchFilter（格式支持前缀 + 问题粒度=年）
           - SetFilter（值数量较少）
           - DATEPARSE + QuantitativeDateFilter（大范围）
        
        Args:
            intent: DateFilterIntent对象
            field_meta: FieldMetadata对象
        
        Returns:
            (VizQLFilter, None) 元组
        """
        # 1. 计算日期范围
        start_date, end_date = self._calculate_date_range(intent)
        
        # 2. 尝试使用 DateManager 获取字段格式和粒度
        if self.date_manager:
            # 从 DateManager 获取字段格式
            field_format = self.date_manager.get_cached_field_format(intent.technical_field)
            
            if field_format:
                # 获取字段粒度
                from tableau_assistant.src.models.time_granularity import get_field_granularity_from_format
                field_granularity = get_field_granularity_from_format(field_format)
                
                # 获取问题粒度（从 time_range 推断）
                question_granularity = self._infer_question_granularity(intent.time_range)
                
                logger.debug(
                    f"使用智能筛选策略: field_format={field_format.value}, "
                    f"field_granularity={field_granularity.value}, "
                    f"question_granularity={question_granularity.value}"
                )
                
                # 3. 使用 StringDateFilterBuilder 构建最优筛选器
                filter_obj = self.string_date_filter_builder.build_filter(
                    field_name=intent.technical_field,
                    field_format=field_format,
                    field_granularity=field_granularity,
                    question_granularity=question_granularity,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if filter_obj:
                    return filter_obj, None
                else:
                    logger.warning(
                        f"StringDateFilterBuilder 无法处理（字段粒度 < 问题粒度），"
                        f"回退到 DATEPARSE 策略"
                    )
        
        # 4. 回退策略：使用传统的 DATEPARSE + QuantitativeDateFilter
        logger.debug("使用传统 DATEPARSE 策略")
        
        # 检测日期格式
        date_format = self.detect_date_format(field_meta.sample_values or [])
        if not date_format:
            raise ValueError(
                f"无法识别字段 '{intent.technical_field}' 的日期格式。"
                f"样本值: {field_meta.sample_values[:3] if field_meta.sample_values else []}"
            )
        
        logger.debug(f"检测到日期格式: {date_format}")
        
        # 生成DATEPARSE calculation
        dateparse_calculation = f"DATEPARSE('{date_format}', [{intent.technical_field}])"
        
        # 生成QuantitativeDateFilter
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
    
    def _infer_question_granularity(self, time_range):
        """
        从 TimeRange 推断问题的时间粒度
        
        Args:
            time_range: TimeRange对象
        
        Returns:
            TimeGranularity枚举值
        """
        from tableau_assistant.src.models.time_granularity import TimeGranularity
        
        # 如果是相对时间，从 period_type 推断
        if time_range.type == "relative" and time_range.period_type:
            period_type_str = time_range.period_type.value
            if period_type_str == "YEARS":
                return TimeGranularity.YEAR
            elif period_type_str == "QUARTERS":
                return TimeGranularity.QUARTER
            elif period_type_str == "MONTHS":
                return TimeGranularity.MONTH
            elif period_type_str == "WEEKS":
                return TimeGranularity.WEEK
            elif period_type_str == "DAYS":
                return TimeGranularity.DAY
        
        # 如果是绝对时间，从日期范围推断
        # 默认返回 DAY（最细粒度）
        return TimeGranularity.DAY
    
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
