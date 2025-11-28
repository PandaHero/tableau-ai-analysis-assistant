"""
日期计算器模块

职责：
1. 提供底层日期计算功能
2. 处理相对日期计算（LASTN, LAST, CURRENT, NEXT, NEXTN）
3. 处理周期类型（YEARS, QUARTERS, MONTHS, WEEKS, DAYS）
4. 计算日期范围的开始和结束日期

设计原则：
- 纯计算逻辑，无业务逻辑
- 所有方法都是确定性的（相同输入→相同输出）
- 完整覆盖所有相对日期类型和周期类型的组合
- 清晰的错误处理
"""
from datetime import datetime, timedelta
from typing import Optional, Dict
from calendar import monthrange
import logging

logger = logging.getLogger(__name__)


class DateCalculator:
    """
    日期计算器
    
    提供底层日期计算功能，支持相对日期和绝对日期的转换。
    
    支持的相对类型（RelativeType）：
    - LASTN: 最近N个周期
    - LAST: 上一个周期
    - CURRENT: 当前周期
    - NEXT: 下一个周期
    - NEXTN: 未来N个周期
    
    支持的周期类型（PeriodType）：
    - YEARS: 年
    - QUARTERS: 季度
    - MONTHS: 月
    - WEEKS: 周
    - DAYS: 天
    
    Examples:
        >>> calc = DateCalculator(anchor_date=datetime(2024, 12, 31))
        >>> result = calc.calculate_relative_date("LASTN", "MONTHS", 3)
        >>> print(result)
        {'start_date': '2024-10-01', 'end_date': '2024-12-31'}
    """
    
    def __init__(
        self,
        anchor_date: Optional[datetime] = None,
        week_start_day: int = 0
    ):
        """
        初始化日期计算器
        
        Args:
            anchor_date: 锚点日期（参考日期），默认为当前日期
            week_start_day: 周开始日（0=周一，1=周二，...，6=周日）
        """
        self.anchor_date = anchor_date or datetime.now()
        self.week_start_day = week_start_day
        
        logger.debug(
            f"DateCalculator初始化: "
            f"anchor_date={self.anchor_date.date()}, "
            f"week_start_day={self.week_start_day}"
        )
    
    def calculate_relative_date(
        self,
        relative_type: str,
        period_type: str,
        range_n: Optional[int] = None
    ) -> Dict[str, str]:
        """
        计算相对日期范围
        
        这是主要的公共方法，根据相对类型和周期类型计算日期范围。
        
        Args:
            relative_type: 相对类型（LASTN, LAST, CURRENT, NEXT, NEXTN）
            period_type: 周期类型（YEARS, QUARTERS, MONTHS, WEEKS, DAYS）
            range_n: 范围数量（LASTN和NEXTN需要）
        
        Returns:
            包含start_date和end_date的字典，格式为"YYYY-MM-DD"
        
        Raises:
            ValueError: 如果参数无效
        
        Examples:
            # 最近3个月
            >>> calc.calculate_relative_date("LASTN", "MONTHS", 3)
            {'start_date': '2024-10-01', 'end_date': '2024-12-31'}
            
            # 上个月
            >>> calc.calculate_relative_date("LAST", "MONTHS")
            {'start_date': '2024-11-01', 'end_date': '2024-11-30'}
            
            # 当前年
            >>> calc.calculate_relative_date("CURRENT", "YEARS")
            {'start_date': '2024-01-01', 'end_date': '2024-12-31'}
        """
        # 验证参数
        self._validate_parameters(relative_type, period_type, range_n)
        
        # 根据相对类型调用对应的计算方法
        if relative_type == "LASTN":
            return self._calculate_lastn(period_type, range_n)
        elif relative_type == "LAST":
            return self._calculate_last(period_type)
        elif relative_type == "CURRENT":
            return self._calculate_current(period_type)
        elif relative_type == "NEXT":
            return self._calculate_next(period_type)
        elif relative_type == "NEXTN":
            return self._calculate_nextn(period_type, range_n)
        else:
            raise ValueError(f"不支持的相对类型: {relative_type}")
    
    def _validate_parameters(
        self,
        relative_type: str,
        period_type: str,
        range_n: Optional[int]
    ) -> None:
        """验证参数有效性"""
        valid_relative_types = ["LASTN", "LAST", "CURRENT", "NEXT", "NEXTN"]
        valid_period_types = ["YEARS", "QUARTERS", "MONTHS", "WEEKS", "DAYS"]
        
        if relative_type not in valid_relative_types:
            raise ValueError(
                f"无效的相对类型: {relative_type}，"
                f"有效值: {valid_relative_types}"
            )
        
        if period_type not in valid_period_types:
            raise ValueError(
                f"无效的周期类型: {period_type}，"
                f"有效值: {valid_period_types}"
            )
        
        if relative_type in ["LASTN", "NEXTN"]:
            if range_n is None or range_n < 1:
                raise ValueError(
                    f"{relative_type}需要提供有效的range_n（>= 1）"
                )
    
    # ============= LASTN 计算 =============
    
    def _calculate_lastn(self, period_type: str, n: int) -> Dict[str, str]:
        """计算最近N个周期"""
        if period_type == "YEARS":
            return self._lastn_years(n)
        elif period_type == "QUARTERS":
            return self._lastn_quarters(n)
        elif period_type == "MONTHS":
            return self._lastn_months(n)
        elif period_type == "WEEKS":
            return self._lastn_weeks(n)
        elif period_type == "DAYS":
            return self._lastn_days(n)
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _lastn_years(self, n: int) -> Dict[str, str]:
        """最近N年"""
        end_year = self.anchor_date.year
        start_year = end_year - n + 1
        return {
            "start_date": f"{start_year}-01-01",
            "end_date": f"{end_year}-12-31"
        }
    
    def _lastn_quarters(self, n: int) -> Dict[str, str]:
        """最近N个季度"""
        # 计算当前季度
        current_quarter = (self.anchor_date.month - 1) // 3 + 1
        current_year = self.anchor_date.year
        
        # 计算开始季度
        total_quarters = current_year * 4 + current_quarter
        start_total_quarters = total_quarters - n + 1
        start_year = (start_total_quarters - 1) // 4
        start_quarter = (start_total_quarters - 1) % 4 + 1
        
        # 计算开始日期
        start_month = (start_quarter - 1) * 3 + 1
        start_date = f"{start_year}-{start_month:02d}-01"
        
        # 计算结束日期（当前季度最后一天）
        end_month = current_quarter * 3
        _, last_day = monthrange(current_year, end_month)
        end_date = f"{current_year}-{end_month:02d}-{last_day:02d}"
        
        return {"start_date": start_date, "end_date": end_date}
    
    def _lastn_months(self, n: int) -> Dict[str, str]:
        """最近N个月"""
        end_year = self.anchor_date.year
        end_month = self.anchor_date.month
        
        # 计算开始月份
        total_months = end_year * 12 + end_month
        start_total_months = total_months - n + 1
        start_year = (start_total_months - 1) // 12
        start_month = (start_total_months - 1) % 12 + 1
        
        # 计算结束日期（当前月最后一天）
        _, last_day = monthrange(end_year, end_month)
        
        return {
            "start_date": f"{start_year}-{start_month:02d}-01",
            "end_date": f"{end_year}-{end_month:02d}-{last_day:02d}"
        }
    
    def _lastn_weeks(self, n: int) -> Dict[str, str]:
        """最近N周"""
        # 计算当前周的开始日期
        days_since_week_start = (self.anchor_date.weekday() - self.week_start_day) % 7
        current_week_start = self.anchor_date - timedelta(days=days_since_week_start)
        
        # 计算N周前的开始日期
        start_date = current_week_start - timedelta(weeks=n-1)
        
        # 当前周的结束日期
        end_date = current_week_start + timedelta(days=6)
        
        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d")
        }
    
    def _lastn_days(self, n: int) -> Dict[str, str]:
        """最近N天"""
        end_date = self.anchor_date
        start_date = end_date - timedelta(days=n-1)
        
        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d")
        }
    
    # ============= LAST 计算 =============
    
    def _calculate_last(self, period_type: str) -> Dict[str, str]:
        """计算上一个周期"""
        if period_type == "YEARS":
            return self._last_year()
        elif period_type == "QUARTERS":
            return self._last_quarter()
        elif period_type == "MONTHS":
            return self._last_month()
        elif period_type == "WEEKS":
            return self._last_week()
        elif period_type == "DAYS":
            return self._last_day()
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _last_year(self) -> Dict[str, str]:
        """去年"""
        last_year = self.anchor_date.year - 1
        return {
            "start_date": f"{last_year}-01-01",
            "end_date": f"{last_year}-12-31"
        }
    
    def _last_quarter(self) -> Dict[str, str]:
        """上季度"""
        current_quarter = (self.anchor_date.month - 1) // 3 + 1
        current_year = self.anchor_date.year
        
        if current_quarter == 1:
            last_quarter = 4
            last_year = current_year - 1
        else:
            last_quarter = current_quarter - 1
            last_year = current_year
        
        start_month = (last_quarter - 1) * 3 + 1
        end_month = last_quarter * 3
        _, last_day = monthrange(last_year, end_month)
        
        return {
            "start_date": f"{last_year}-{start_month:02d}-01",
            "end_date": f"{last_year}-{end_month:02d}-{last_day:02d}"
        }
    
    def _last_month(self) -> Dict[str, str]:
        """上个月"""
        if self.anchor_date.month == 1:
            last_month = 12
            last_year = self.anchor_date.year - 1
        else:
            last_month = self.anchor_date.month - 1
            last_year = self.anchor_date.year
        
        _, last_day = monthrange(last_year, last_month)
        
        return {
            "start_date": f"{last_year}-{last_month:02d}-01",
            "end_date": f"{last_year}-{last_month:02d}-{last_day:02d}"
        }
    
    def _last_week(self) -> Dict[str, str]:
        """上周"""
        # 当前周的开始日期
        days_since_week_start = (self.anchor_date.weekday() - self.week_start_day) % 7
        current_week_start = self.anchor_date - timedelta(days=days_since_week_start)
        
        # 上周的开始和结束日期
        last_week_start = current_week_start - timedelta(weeks=1)
        last_week_end = last_week_start + timedelta(days=6)
        
        return {
            "start_date": last_week_start.strftime("%Y-%m-%d"),
            "end_date": last_week_end.strftime("%Y-%m-%d")
        }
    
    def _last_day(self) -> Dict[str, str]:
        """昨天"""
        last_day = self.anchor_date - timedelta(days=1)
        date_str = last_day.strftime("%Y-%m-%d")
        return {"start_date": date_str, "end_date": date_str}
    
    # ============= CURRENT 计算 =============
    
    def _calculate_current(self, period_type: str) -> Dict[str, str]:
        """计算当前周期"""
        if period_type == "YEARS":
            return self._current_year()
        elif period_type == "QUARTERS":
            return self._current_quarter()
        elif period_type == "MONTHS":
            return self._current_month()
        elif period_type == "WEEKS":
            return self._current_week()
        elif period_type == "DAYS":
            return self._current_day()
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _current_year(self) -> Dict[str, str]:
        """今年"""
        year = self.anchor_date.year
        return {
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31"
        }
    
    def _current_quarter(self) -> Dict[str, str]:
        """本季度"""
        quarter = (self.anchor_date.month - 1) // 3 + 1
        year = self.anchor_date.year
        
        start_month = (quarter - 1) * 3 + 1
        end_month = quarter * 3
        _, last_day = monthrange(year, end_month)
        
        return {
            "start_date": f"{year}-{start_month:02d}-01",
            "end_date": f"{year}-{end_month:02d}-{last_day:02d}"
        }
    
    def _current_month(self) -> Dict[str, str]:
        """本月"""
        year = self.anchor_date.year
        month = self.anchor_date.month
        _, last_day = monthrange(year, month)
        
        return {
            "start_date": f"{year}-{month:02d}-01",
            "end_date": f"{year}-{month:02d}-{last_day:02d}"
        }
    
    def _current_week(self) -> Dict[str, str]:
        """本周"""
        days_since_week_start = (self.anchor_date.weekday() - self.week_start_day) % 7
        week_start = self.anchor_date - timedelta(days=days_since_week_start)
        week_end = week_start + timedelta(days=6)
        
        return {
            "start_date": week_start.strftime("%Y-%m-%d"),
            "end_date": week_end.strftime("%Y-%m-%d")
        }
    
    def _current_day(self) -> Dict[str, str]:
        """今天"""
        date_str = self.anchor_date.strftime("%Y-%m-%d")
        return {"start_date": date_str, "end_date": date_str}
    
    # ============= NEXT 计算 =============
    
    def _calculate_next(self, period_type: str) -> Dict[str, str]:
        """计算下一个周期"""
        if period_type == "YEARS":
            return self._next_year()
        elif period_type == "QUARTERS":
            return self._next_quarter()
        elif period_type == "MONTHS":
            return self._next_month()
        elif period_type == "WEEKS":
            return self._next_week()
        elif period_type == "DAYS":
            return self._next_day()
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _next_year(self) -> Dict[str, str]:
        """明年"""
        next_year = self.anchor_date.year + 1
        return {
            "start_date": f"{next_year}-01-01",
            "end_date": f"{next_year}-12-31"
        }
    
    def _next_quarter(self) -> Dict[str, str]:
        """下季度"""
        current_quarter = (self.anchor_date.month - 1) // 3 + 1
        current_year = self.anchor_date.year
        
        if current_quarter == 4:
            next_quarter = 1
            next_year = current_year + 1
        else:
            next_quarter = current_quarter + 1
            next_year = current_year
        
        start_month = (next_quarter - 1) * 3 + 1
        end_month = next_quarter * 3
        _, last_day = monthrange(next_year, end_month)
        
        return {
            "start_date": f"{next_year}-{start_month:02d}-01",
            "end_date": f"{next_year}-{end_month:02d}-{last_day:02d}"
        }
    
    def _next_month(self) -> Dict[str, str]:
        """下个月"""
        if self.anchor_date.month == 12:
            next_month = 1
            next_year = self.anchor_date.year + 1
        else:
            next_month = self.anchor_date.month + 1
            next_year = self.anchor_date.year
        
        _, last_day = monthrange(next_year, next_month)
        
        return {
            "start_date": f"{next_year}-{next_month:02d}-01",
            "end_date": f"{next_year}-{next_month:02d}-{last_day:02d}"
        }
    
    def _next_week(self) -> Dict[str, str]:
        """下周"""
        days_since_week_start = (self.anchor_date.weekday() - self.week_start_day) % 7
        current_week_start = self.anchor_date - timedelta(days=days_since_week_start)
        
        next_week_start = current_week_start + timedelta(weeks=1)
        next_week_end = next_week_start + timedelta(days=6)
        
        return {
            "start_date": next_week_start.strftime("%Y-%m-%d"),
            "end_date": next_week_end.strftime("%Y-%m-%d")
        }
    
    def _next_day(self) -> Dict[str, str]:
        """明天"""
        next_day = self.anchor_date + timedelta(days=1)
        date_str = next_day.strftime("%Y-%m-%d")
        return {"start_date": date_str, "end_date": date_str}
    
    # ============= NEXTN 计算 =============
    
    def _calculate_nextn(self, period_type: str, n: int) -> Dict[str, str]:
        """计算未来N个周期"""
        if period_type == "YEARS":
            return self._nextn_years(n)
        elif period_type == "QUARTERS":
            return self._nextn_quarters(n)
        elif period_type == "MONTHS":
            return self._nextn_months(n)
        elif period_type == "WEEKS":
            return self._nextn_weeks(n)
        elif period_type == "DAYS":
            return self._nextn_days(n)
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _nextn_years(self, n: int) -> Dict[str, str]:
        """未来N年"""
        start_year = self.anchor_date.year + 1
        end_year = start_year + n - 1
        return {
            "start_date": f"{start_year}-01-01",
            "end_date": f"{end_year}-12-31"
        }
    
    def _nextn_quarters(self, n: int) -> Dict[str, str]:
        """未来N个季度"""
        current_quarter = (self.anchor_date.month - 1) // 3 + 1
        current_year = self.anchor_date.year
        
        # 下一个季度的开始
        if current_quarter == 4:
            start_quarter = 1
            start_year = current_year + 1
        else:
            start_quarter = current_quarter + 1
            start_year = current_year
        
        # 计算结束季度
        total_quarters = start_year * 4 + start_quarter
        end_total_quarters = total_quarters + n - 1
        end_year = (end_total_quarters - 1) // 4
        end_quarter = (end_total_quarters - 1) % 4 + 1
        
        # 计算日期
        start_month = (start_quarter - 1) * 3 + 1
        end_month = end_quarter * 3
        _, last_day = monthrange(end_year, end_month)
        
        return {
            "start_date": f"{start_year}-{start_month:02d}-01",
            "end_date": f"{end_year}-{end_month:02d}-{last_day:02d}"
        }
    
    def _nextn_months(self, n: int) -> Dict[str, str]:
        """未来N个月"""
        # 下个月的开始
        if self.anchor_date.month == 12:
            start_month = 1
            start_year = self.anchor_date.year + 1
        else:
            start_month = self.anchor_date.month + 1
            start_year = self.anchor_date.year
        
        # 计算结束月份
        total_months = start_year * 12 + start_month
        end_total_months = total_months + n - 1
        end_year = (end_total_months - 1) // 12
        end_month = (end_total_months - 1) % 12 + 1
        
        _, last_day = monthrange(end_year, end_month)
        
        return {
            "start_date": f"{start_year}-{start_month:02d}-01",
            "end_date": f"{end_year}-{end_month:02d}-{last_day:02d}"
        }
    
    def _nextn_weeks(self, n: int) -> Dict[str, str]:
        """未来N周"""
        days_since_week_start = (self.anchor_date.weekday() - self.week_start_day) % 7
        current_week_start = self.anchor_date - timedelta(days=days_since_week_start)
        
        # 下周的开始
        start_date = current_week_start + timedelta(weeks=1)
        # N周后的结束
        end_date = start_date + timedelta(weeks=n) - timedelta(days=1)
        
        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d")
        }
    
    def _nextn_days(self, n: int) -> Dict[str, str]:
        """未来N天"""
        start_date = self.anchor_date + timedelta(days=1)
        end_date = start_date + timedelta(days=n-1)
        
        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d")
        }
    
    # ============= 辅助方法 =============
    
    def get_anchor_date(self) -> datetime:
        """获取锚点日期"""
        return self.anchor_date
    
    def get_week_start_day(self) -> int:
        """获取周开始日"""
        return self.week_start_day


# ============= 导出 =============

__all__ = [
    "DateCalculator",
]
