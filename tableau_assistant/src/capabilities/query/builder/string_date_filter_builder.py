"""
STRING类型日期字段筛选器构建模块

负责为STRING类型的日期字段构建合适的VizQL筛选器。
根据字段粒度、问题粒度和日期格式选择最优的筛选策略。
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from dateutil.relativedelta import relativedelta

from tableau_assistant.src.models.time_granularity import TimeGranularity
from tableau_assistant.src.capabilities.date_processing.format_detector import DateFormatType
from tableau_assistant.src.models.vizql_types import (
    VizQLFilter,
    SetFilter,
    MatchFilter,
    QuantitativeDateFilter,
    FilterField,
)

logger = logging.getLogger(__name__)


class StringDateFilterBuilder:
    """
    STRING类型日期字段筛选器构建器
    
    根据字段粒度和问题粒度的关系，选择合适的筛选策略：
    1. MatchFilter - 模式匹配（格式支持前缀 + 问题粒度=年）
    2. SetFilter - 枚举值（值数量较少）
    3. DATEPARSE + QuantitativeDateFilter - 日期范围（大范围）
    """
    
    def __init__(self):
        """初始化构建器"""
        logger.debug("StringDateFilterBuilder初始化")
    
    def build_filter(
        self,
        field_name: str,
        field_format: DateFormatType,
        field_granularity: TimeGranularity,
        question_granularity: TimeGranularity,
        start_date: str,
        end_date: str
    ) -> Optional[VizQLFilter]:
        """
        构建STRING类型日期字段的筛选器
        
        Args:
            field_name: 字段名称
            field_format: 字段的日期格式
            field_granularity: 字段的时间粒度
            question_granularity: 问题的时间粒度
            start_date: 开始日期（ISO格式 YYYY-MM-DD）
            end_date: 结束日期（ISO格式 YYYY-MM-DD）
        
        Returns:
            VizQLFilter对象，如果无法处理则返回None
        """
        logger.info(
            f"构建STRING日期筛选器: field={field_name}, "
            f"field_format={field_format.value}, "
            f"field_granularity={field_granularity.value}, "
            f"question_granularity={question_granularity.value}, "
            f"range={start_date} to {end_date}"
        )
        
        # 1. 比较粒度关系
        if field_granularity == question_granularity:
            # 精确匹配
            return self._build_exact_match_filter(
                field_name, field_format, field_granularity, start_date, end_date
            )
        
        elif field_granularity < question_granularity:
            # 字段更粗，无法实现
            logger.warning(
                f"字段粒度 {field_granularity.value} < 问题粒度 {question_granularity.value}，无法实现"
            )
            return None
        
        else:  # field_granularity > question_granularity
            # 字段更细，需要展开
            return self._build_expanded_filter(
                field_name, field_format, field_granularity, 
                question_granularity, start_date, end_date
            )
    
    def _build_exact_match_filter(
        self,
        field_name: str,
        field_format: DateFormatType,
        granularity: TimeGranularity,
        start_date: str,
        end_date: str
    ) -> SetFilter:
        """构建精确匹配筛选器（字段粒度 == 问题粒度）"""
        values = self._expand_time_range_to_values(
            start_date, end_date, granularity, field_format
        )
        
        logger.info(
            f"✓ 使用SetFilter精确匹配: {len(values)} 个值"
        )
        
        return SetFilter(
            field=FilterField(fieldCaption=field_name),
            filterType="SET",
            values=values
        )
    
    def _build_expanded_filter(
        self,
        field_name: str,
        field_format: DateFormatType,
        field_granularity: TimeGranularity,
        question_granularity: TimeGranularity,
        start_date: str,
        end_date: str
    ) -> Optional[VizQLFilter]:
        """构建展开筛选器（字段粒度 > 问题粒度）"""
        
        # 计算需要枚举的值数量
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days_count = (end_dt - start_dt).days + 1
        
        # 对于完整日期格式（DAY粒度），如果范围超过100天，优先使用 DATEPARSE
        if field_granularity == TimeGranularity.DAY and days_count > 100:
            # 使用 DATEPARSE + QuantitativeDateFilter
            dateparse_format = self._get_dateparse_format(field_format)
            logger.info(
                f"✓ 使用DATEPARSE+QuantitativeDateFilter: {days_count}天，格式={dateparse_format}"
            )
            return QuantitativeDateFilter(
                field=FilterField(
                    calculation=f'DATEPARSE("{dateparse_format}", [{field_name}])'
                ),
                filterType="QUANTITATIVE_DATE",
                quantitativeFilterType="RANGE",
                minDate=start_date,
                maxDate=end_date
            )
        
        # 检查是否支持前缀匹配
        if self._supports_prefix_match(field_format):
            # 支持前缀匹配的格式
            if question_granularity == TimeGranularity.YEAR and \
               field_granularity != TimeGranularity.DAY:
                # 非日期粒度（月、季度、周）+ 问题粒度=年 → 使用 MatchFilter
                year = start_date[:4]
                logger.info(
                    f"✓ 使用MatchFilter前缀匹配: startsWith='{year}-'"
                )
                return MatchFilter(
                    field=FilterField(fieldCaption=field_name),
                    filterType="MATCH",
                    startsWith=f"{year}-"
                )
            
            elif question_granularity == TimeGranularity.MONTH and \
                 field_granularity == TimeGranularity.DAY and \
                 field_format == DateFormatType.ISO_DATE:
                # YYYY-MM-DD 格式可以用前缀匹配月份
                year_month = start_date[:7]  # "2024-01"
                logger.info(
                    f"✓ 使用MatchFilter前缀匹配月份: startsWith='{year_month}-'"
                )
                return MatchFilter(
                    field=FilterField(fieldCaption=field_name),
                    filterType="MATCH",
                    startsWith=f"{year_month}-"
                )
            
            else:
                # 使用 SetFilter 枚举
                values = self._expand_time_range_to_values(
                    start_date, end_date, field_granularity, field_format
                )
                logger.info(
                    f"✓ 使用SetFilter枚举: {len(values)} 个值"
                )
                return SetFilter(
                    field=FilterField(fieldCaption=field_name),
                    filterType="SET",
                    values=values
                )
        
        else:
            # 不支持前缀匹配的格式
            if days_count > 100:
                # 使用 DATEPARSE + QuantitativeDateFilter
                dateparse_format = self._get_dateparse_format(field_format)
                logger.info(
                    f"✓ 使用DATEPARSE+QuantitativeDateFilter: {days_count}天，格式={dateparse_format}"
                )
                return QuantitativeDateFilter(
                    field=FilterField(
                        calculation=f'DATEPARSE("{dateparse_format}", [{field_name}])'
                    ),
                    filterType="QUANTITATIVE_DATE",
                    quantitativeFilterType="RANGE",
                    minDate=start_date,
                    maxDate=end_date
                )
            else:
                # 使用 SetFilter 枚举
                values = self._expand_time_range_to_values(
                    start_date, end_date, field_granularity, field_format
                )
                logger.info(
                    f"✓ 使用SetFilter枚举: {len(values)} 个值"
                )
                return SetFilter(
                    field=FilterField(fieldCaption=field_name),
                    filterType="SET",
                    values=values
                )
    
    def _supports_prefix_match(self, format_type: DateFormatType) -> bool:
        """
        判断日期格式是否支持前缀匹配
        
        支持前缀匹配的格式：年份在前面
        - YYYY-MM
        - YYYY-QN
        - YYYY-WNN
        - YYYY-MM-DD
        """
        prefix_match_formats = [
            DateFormatType.YEAR_MONTH,
            DateFormatType.QUARTER,
            DateFormatType.YEAR_WEEK,
            DateFormatType.ISO_DATE,
        ]
        return format_type in prefix_match_formats
    
    def _get_dateparse_format(self, format_type: DateFormatType) -> str:
        """获取 DATEPARSE 函数的格式字符串"""
        format_map = {
            DateFormatType.ISO_DATE: "yyyy-MM-dd",
            DateFormatType.US_DATE: "MM/dd/yyyy",
            DateFormatType.EU_DATE: "dd/MM/yyyy",
            DateFormatType.YEAR_MONTH: "yyyy-MM",
            DateFormatType.MONTH_YEAR: "MM/yyyy",
        }
        return format_map.get(format_type, "yyyy-MM-dd")
    
    def _expand_time_range_to_values(
        self,
        start_date: str,
        end_date: str,
        granularity: TimeGranularity,
        format_type: DateFormatType
    ) -> List[str]:
        """
        将时间范围展开为字段格式的值列表
        
        Args:
            start_date: 开始日期（ISO格式 YYYY-MM-DD）
            end_date: 结束日期（ISO格式 YYYY-MM-DD）
            granularity: 时间粒度
            format_type: 日期格式
        
        Returns:
            字段格式的值列表
        """
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        values = []
        
        if granularity == TimeGranularity.YEAR:
            # 按年展开
            current = start_dt
            while current <= end_dt:
                if format_type == DateFormatType.YEAR_ONLY:
                    values.append(current.strftime("%Y"))
                current = current.replace(year=current.year + 1, month=1, day=1)
        
        elif granularity == TimeGranularity.QUARTER:
            # 按季度展开
            current = start_dt.replace(day=1)
            while current <= end_dt:
                quarter = (current.month - 1) // 3 + 1
                if format_type == DateFormatType.QUARTER:
                    quarter_str = f"{current.year}-Q{quarter}"
                    if not values or values[-1] != quarter_str:
                        values.append(quarter_str)
                current += relativedelta(months=1)
        
        elif granularity == TimeGranularity.MONTH:
            # 按月展开
            current = start_dt.replace(day=1)
            while current <= end_dt:
                if format_type == DateFormatType.YEAR_MONTH:
                    values.append(current.strftime("%Y-%m"))
                elif format_type == DateFormatType.MONTH_YEAR:
                    values.append(current.strftime("%m/%Y"))
                current += relativedelta(months=1)
        
        elif granularity == TimeGranularity.WEEK:
            # 按周展开
            current = start_dt
            seen_weeks = set()
            while current <= end_dt:
                iso_year, iso_week, _ = current.isocalendar()
                week_str = f"{iso_year}-W{iso_week:02d}"
                if format_type == DateFormatType.YEAR_WEEK and week_str not in seen_weeks:
                    values.append(week_str)
                    seen_weeks.add(week_str)
                current += timedelta(days=1)
        
        elif granularity == TimeGranularity.DAY:
            # 按天展开
            current = start_dt
            while current <= end_dt:
                if format_type == DateFormatType.ISO_DATE:
                    values.append(current.strftime("%Y-%m-%d"))
                elif format_type == DateFormatType.US_DATE:
                    values.append(current.strftime("%m/%d/%Y"))
                elif format_type == DateFormatType.EU_DATE:
                    values.append(current.strftime("%d/%m/%Y"))
                current += timedelta(days=1)
        
        return values


# ============= 导出 =============

__all__ = [
    "StringDateFilterBuilder",
]
