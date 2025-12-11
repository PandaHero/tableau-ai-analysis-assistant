"""
日期解析器（DateParser）

职责：
1. 解析 LLM 输出的 TimeFilterSpec 格式
2. 计算具体的日期范围（start_date, end_date）
3. 验证日期范围的合理性
4. 不做自然语言语义理解（由 LLM 负责）

设计原则（与 VizQL API 对齐）：
- LLM 负责：理解自然语言，输出 TimeFilterSpec 格式
- 绝对日期：LLM 直接输出 RFC 3339 格式（YYYY-MM-DD），无需 DateParser 计算
- 相对日期：DateParser 根据 period_type 和 date_range_type 计算具体日期
- 离散日期：DateParser 展开为具体日期列表
- 与 VizQL API 对齐：直接映射到 QUANTITATIVE_DATE、DATE、SET 筛选类型
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, List
from calendar import monthrange
import logging
import re

from tableau_assistant.src.models.semantic.query import TimeFilterSpec
from tableau_assistant.src.models.semantic.enums import (
    TimeFilterMode,
    PeriodType,
    DateRangeType,
)

logger = logging.getLogger(__name__)


class DateParser:
    """
    日期解析器
    
    将 LLM 输出的 TimeFilterSpec 转换为 VizQL 兼容的筛选参数。
    
    使用场景：
    - 在 Query Builder 阶段使用
    - 接收 Understanding Agent 输出的 TimeFilterSpec
    - 转换为 VizQL 筛选参数或计算具体日期范围
    
    示例：
        >>> parser = DateParser()
        >>> # 绝对日期范围
        >>> time_filter = TimeFilterSpec(
        ...     mode=TimeFilterMode.ABSOLUTE_RANGE,
        ...     start_date="2024-01-01",
        ...     end_date="2024-12-31"
        ... )
        >>> result = parser.process_time_filter(time_filter)
        >>> print(result)
        {"filter_type": "QUANTITATIVE_DATE", "quantitative_filter_type": "RANGE", 
         "min_date": "2024-01-01", "max_date": "2024-12-31"}
        
        >>> # 相对日期
        >>> time_filter = TimeFilterSpec(
        ...     mode=TimeFilterMode.RELATIVE,
        ...     period_type=PeriodType.MONTHS,
        ...     date_range_type=DateRangeType.LASTN,
        ...     range_n=3
        ... )
        >>> result = parser.process_time_filter(time_filter)
        >>> print(result)
        {"filter_type": "DATE", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
    """

    def __init__(self):
        """初始化日期解析器"""
        self._cache: Dict[str, dict] = {}
    
    def process_time_filter(
        self,
        time_filter: TimeFilterSpec,
        reference_date: Optional[datetime] = None
    ) -> dict:
        """
        处理时间筛选，返回 VizQL 兼容的筛选参数
        
        Args:
            time_filter: TimeFilterSpec 对象
            reference_date: 参考日期（用于相对时间计算，默认今天）
        
        Returns:
            VizQL 筛选参数字典:
            - ABSOLUTE_RANGE: {"filter_type": "QUANTITATIVE_DATE", "quantitative_filter_type": "RANGE", "min_date": "...", "max_date": "..."}
            - RELATIVE: {"filter_type": "DATE", "period_type": "...", "date_range_type": "...", ...}
            - SET: {"filter_type": "SET", "values": [...], "exclude": false}
        """
        if reference_date is None:
            reference_date = datetime.now()
        
        if time_filter.mode == TimeFilterMode.ABSOLUTE_RANGE:
            return self._process_absolute_range(time_filter)
        elif time_filter.mode == TimeFilterMode.RELATIVE:
            return self._process_relative_filter(time_filter, reference_date)
        elif time_filter.mode == TimeFilterMode.SET:
            return self._process_set_filter(time_filter)
        else:
            raise ValueError(f"不支持的时间筛选模式: {time_filter.mode}")
    
    def _process_absolute_range(self, time_filter: TimeFilterSpec) -> dict:
        """
        处理绝对日期范围
        
        LLM 已输出 RFC 3339 格式，直接透传到 VizQL
        """
        # 验证日期格式
        self._validate_rfc3339_date(time_filter.start_date)
        self._validate_rfc3339_date(time_filter.end_date)
        
        # 验证日期范围
        self._validate_date_range(time_filter.start_date, time_filter.end_date)
        
        return {
            "filter_type": "QUANTITATIVE_DATE",
            "quantitative_filter_type": "RANGE",
            "min_date": time_filter.start_date,
            "max_date": time_filter.end_date
        }
    
    def _process_relative_filter(
        self,
        time_filter: TimeFilterSpec,
        reference_date: datetime
    ) -> dict:
        """
        处理相对日期
        
        直接返回 VizQL RelativeDateFilter 参数
        """
        result = {
            "filter_type": "DATE",
            "period_type": time_filter.period_type.value,
            "date_range_type": time_filter.date_range_type.value,
        }
        
        if time_filter.range_n is not None:
            result["range_n"] = time_filter.range_n
        
        if time_filter.anchor_date is not None:
            result["anchor_date"] = time_filter.anchor_date
        
        return result
    
    def _process_set_filter(self, time_filter: TimeFilterSpec) -> dict:
        """
        处理离散日期集合
        
        将日期值展开为 VizQL SetFilter 格式
        """
        expanded_values = []
        for value in time_filter.date_values:
            expanded_values.extend(self._expand_date_value(value))
        
        return {
            "filter_type": "SET",
            "values": expanded_values,
            "exclude": False
        }
    
    def calculate_relative_dates(
        self,
        time_filter: TimeFilterSpec,
        reference_date: Optional[datetime] = None
    ) -> Tuple[str, str]:
        """
        计算相对日期的具体日期范围
        
        当需要将相对日期转换为具体日期时使用（例如用于 QUANTITATIVE_DATE 筛选）。
        
        Args:
            time_filter: TimeFilterSpec 对象（mode 必须为 RELATIVE）
            reference_date: 参考日期（默认今天）
        
        Returns:
            (start_date, end_date) 元组，格式为 "YYYY-MM-DD"
        
        Examples:
            >>> parser = DateParser()
            >>> time_filter = TimeFilterSpec(
            ...     mode=TimeFilterMode.RELATIVE,
            ...     period_type=PeriodType.MONTHS,
            ...     date_range_type=DateRangeType.LASTN,
            ...     range_n=3
            ... )
            >>> start, end = parser.calculate_relative_dates(time_filter)
            >>> print(start, end)  # 假设今天是 2024-12-11
            2024-10-01 2024-12-11
        """
        if time_filter.mode != TimeFilterMode.RELATIVE:
            raise ValueError("此方法只处理相对日期（mode=RELATIVE）")
        
        if reference_date is None:
            reference_date = datetime.now()
        
        period_type = time_filter.period_type
        date_range_type = time_filter.date_range_type
        range_n = time_filter.range_n or 1
        
        if date_range_type == DateRangeType.CURRENT:
            return self._calc_current_period(reference_date, period_type)
        elif date_range_type == DateRangeType.LAST:
            return self._calc_last_period(reference_date, period_type)
        elif date_range_type == DateRangeType.LASTN:
            return self._calc_lastn_periods(reference_date, period_type, range_n)
        elif date_range_type == DateRangeType.NEXT:
            return self._calc_next_period(reference_date, period_type)
        elif date_range_type == DateRangeType.NEXTN:
            return self._calc_nextn_periods(reference_date, period_type, range_n)
        elif date_range_type == DateRangeType.TODATE:
            return self._calc_todate(reference_date, period_type)
        else:
            raise ValueError(f"不支持的相对日期类型: {date_range_type}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 相对日期计算方法
    # ═══════════════════════════════════════════════════════════════════════
    
    def _calc_current_period(
        self, ref: datetime, period_type: PeriodType
    ) -> Tuple[str, str]:
        """计算当前周期"""
        if period_type == PeriodType.DAYS:
            return (ref.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.WEEKS:
            start = ref - timedelta(days=ref.weekday())
            end = start + timedelta(days=6)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.MONTHS:
            start = ref.replace(day=1)
            _, last_day = monthrange(ref.year, ref.month)
            end = ref.replace(day=last_day)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.QUARTERS:
            quarter = (ref.month - 1) // 3 + 1
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            start = ref.replace(month=start_month, day=1)
            _, last_day = monthrange(ref.year, end_month)
            end = ref.replace(month=end_month, day=last_day)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.YEARS:
            start = ref.replace(month=1, day=1)
            end = ref.replace(month=12, day=31)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _calc_last_period(
        self, ref: datetime, period_type: PeriodType
    ) -> Tuple[str, str]:
        """计算上一个周期"""
        from dateutil.relativedelta import relativedelta
        
        if period_type == PeriodType.DAYS:
            last = ref - timedelta(days=1)
            return (last.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.WEEKS:
            last_week_start = ref - timedelta(days=ref.weekday() + 7)
            last_week_end = last_week_start + timedelta(days=6)
            return (last_week_start.strftime("%Y-%m-%d"), last_week_end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.MONTHS:
            last_month = ref - relativedelta(months=1)
            start = last_month.replace(day=1)
            _, last_day = monthrange(last_month.year, last_month.month)
            end = last_month.replace(day=last_day)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.QUARTERS:
            current_quarter = (ref.month - 1) // 3 + 1
            if current_quarter == 1:
                last_quarter = 4
                year = ref.year - 1
            else:
                last_quarter = current_quarter - 1
                year = ref.year
            start_month = (last_quarter - 1) * 3 + 1
            end_month = last_quarter * 3
            start = datetime(year, start_month, 1)
            _, last_day = monthrange(year, end_month)
            end = datetime(year, end_month, last_day)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.YEARS:
            last_year = ref.year - 1
            return (f"{last_year}-01-01", f"{last_year}-12-31")
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _calc_lastn_periods(
        self, ref: datetime, period_type: PeriodType, n: int
    ) -> Tuple[str, str]:
        """计算最近 N 个周期"""
        from dateutil.relativedelta import relativedelta
        
        if period_type == PeriodType.DAYS:
            start = ref - timedelta(days=n - 1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.WEEKS:
            start = ref - timedelta(weeks=n)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.MONTHS:
            start = ref - relativedelta(months=n - 1)
            start = start.replace(day=1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.QUARTERS:
            start = ref - relativedelta(months=(n - 1) * 3)
            quarter = (start.month - 1) // 3 + 1
            start_month = (quarter - 1) * 3 + 1
            start = start.replace(month=start_month, day=1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.YEARS:
            start_year = ref.year - n + 1
            return (f"{start_year}-01-01", ref.strftime("%Y-%m-%d"))
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _calc_next_period(
        self, ref: datetime, period_type: PeriodType
    ) -> Tuple[str, str]:
        """计算下一个周期"""
        from dateutil.relativedelta import relativedelta
        
        if period_type == PeriodType.DAYS:
            next_day = ref + timedelta(days=1)
            return (next_day.strftime("%Y-%m-%d"), next_day.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.WEEKS:
            next_week_start = ref + timedelta(days=7 - ref.weekday())
            next_week_end = next_week_start + timedelta(days=6)
            return (next_week_start.strftime("%Y-%m-%d"), next_week_end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.MONTHS:
            next_month = ref + relativedelta(months=1)
            start = next_month.replace(day=1)
            _, last_day = monthrange(next_month.year, next_month.month)
            end = next_month.replace(day=last_day)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.QUARTERS:
            current_quarter = (ref.month - 1) // 3 + 1
            if current_quarter == 4:
                next_quarter = 1
                year = ref.year + 1
            else:
                next_quarter = current_quarter + 1
                year = ref.year
            start_month = (next_quarter - 1) * 3 + 1
            end_month = next_quarter * 3
            start = datetime(year, start_month, 1)
            _, last_day = monthrange(year, end_month)
            end = datetime(year, end_month, last_day)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.YEARS:
            next_year = ref.year + 1
            return (f"{next_year}-01-01", f"{next_year}-12-31")
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _calc_nextn_periods(
        self, ref: datetime, period_type: PeriodType, n: int
    ) -> Tuple[str, str]:
        """计算未来 N 个周期"""
        from dateutil.relativedelta import relativedelta
        
        if period_type == PeriodType.DAYS:
            end = ref + timedelta(days=n - 1)
            return (ref.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.WEEKS:
            end = ref + timedelta(weeks=n)
            return (ref.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.MONTHS:
            end = ref + relativedelta(months=n - 1)
            _, last_day = monthrange(end.year, end.month)
            end = end.replace(day=last_day)
            return (ref.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.QUARTERS:
            end = ref + relativedelta(months=(n - 1) * 3)
            quarter = (end.month - 1) // 3 + 1
            end_month = quarter * 3
            _, last_day = monthrange(end.year, end_month)
            end = end.replace(month=end_month, day=last_day)
            return (ref.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.YEARS:
            end_year = ref.year + n - 1
            return (ref.strftime("%Y-%m-%d"), f"{end_year}-12-31")
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _calc_todate(
        self, ref: datetime, period_type: PeriodType
    ) -> Tuple[str, str]:
        """计算至今（年初至今、月初至今等）"""
        if period_type == PeriodType.WEEKS:
            start = ref - timedelta(days=ref.weekday())
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.MONTHS:
            start = ref.replace(day=1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.QUARTERS:
            quarter = (ref.month - 1) // 3 + 1
            start_month = (quarter - 1) * 3 + 1
            start = ref.replace(month=start_month, day=1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.YEARS:
            start = ref.replace(month=1, day=1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        else:
            raise ValueError(f"不支持的至今类型: {period_type}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════════════════
    
    def _expand_date_value(self, value: str) -> List[str]:
        """
        展开日期值为具体日期列表
        
        支持的格式：
        - "2024" → 年份（返回原值）
        - "2024-Q1" → 季度（展开为月份）
        - "2024-01" → 月份（返回原值）
        - "2024-01-15" → 具体日期（返回原值）
        """
        # 季度格式: 2024-Q1
        quarter_match = re.match(r'^(\d{4})-Q([1-4])$', value, re.IGNORECASE)
        if quarter_match:
            year = int(quarter_match.group(1))
            quarter = int(quarter_match.group(2))
            start_month = (quarter - 1) * 3 + 1
            return [f"{year}-{m:02d}" for m in range(start_month, start_month + 3)]
        
        # 其他格式直接返回
        return [value]
    
    def _validate_rfc3339_date(self, date_str: str) -> None:
        """验证日期格式是否为 YYYY-MM-DD"""
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            raise ValueError(f"日期格式错误，期望 YYYY-MM-DD，实际: {date_str}")
        
        # 验证日期有效性
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"无效的日期: {date_str}")
    
    def _validate_date_range(self, start_date: str, end_date: str) -> None:
        """验证日期范围的合理性"""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        if start > end:
            raise ValueError(f"开始日期晚于结束日期: {start_date} > {end_date}")
    
    def clear_cache(self) -> None:
        """清空缓存"""
        cache_size = len(self._cache)
        self._cache.clear()
        logger.info(f"缓存已清空，清除了 {cache_size} 个条目")


# ============= 导出 =============

__all__ = [
    "DateParser",
]
