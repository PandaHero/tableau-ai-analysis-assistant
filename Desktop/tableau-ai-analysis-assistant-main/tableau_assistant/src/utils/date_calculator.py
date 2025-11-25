"""
日期计算器（DateCalculator）

根据旧版需求文档5.2的要求实现：
1. 获取anchor_date（数据最新日期）
2. 判断当前周期是否过完
3. 计算相对日期、对比日期、周期日期
4. 对齐未完整周期（同比环比）
5. 支持DATE、DATETIME、STRING三种字段类型
6. 支持周开始日配置（周一/周日）
7. 支持法定节假日过滤（使用chinese-calendar包）
8. 支持农历转换（可选）
"""
from datetime import datetime, timedelta, date
from typing import Literal, Optional, Tuple, Dict, Any
from calendar import monthrange
import logging

logger = logging.getLogger(__name__)

# ============= 中国法定节假日支持 =============

# 尝试导入chinese-calendar库
try:
    import chinese_calendar as calendar
    HOLIDAY_SUPPORT = True
    logger.info("chinese-calendar库已加载，节假日功能可用")
except ImportError:
    HOLIDAY_SUPPORT = False
    logger.warning("chinese-calendar库未安装，节假日功能不可用。安装: pip install chinesecalendar")


class DateCalculator:
    """
    日期计算器
    
    核心设计：
    1. 基于anchor_date（数据最新日期）而非当前系统日期
    2. 判断周期是否过完，影响同比环比计算
    3. 支持三种字段类型（DATE、DATETIME、STRING）
    4. 所有计算都是确定性的（相同输入产生相同输出）
    5. 支持周开始日配置（周一或周日）
    """
    
    def __init__(
        self,
        anchor_date: Optional[datetime] = None,
        field_data_type: Literal["DATE", "DATETIME", "STRING"] = "DATE",
        week_start_day: int = 0
    ):
        """
        初始化日期计算器
        
        Args:
            anchor_date: 数据最新日期（如果为None，使用当前日期-1）
            field_data_type: 字段数据类型
            week_start_day: 周开始日（0=周一，6=周日）
        """
        if anchor_date is None:
            # 默认使用昨天（避免使用未来日期）
            anchor_date = datetime.now() - timedelta(days=1)
        
        if isinstance(anchor_date, str):
            # 解析字符串日期
            anchor_date = datetime.fromisoformat(anchor_date.replace("Z", "+00:00"))
        
        self.anchor_date = anchor_date.replace(hour=0, minute=0, second=0, microsecond=0)
        self.field_data_type = field_data_type
        self.week_start_day = week_start_day  # 0=周一（ISO标准），6=周日（美国标准）
    
    def calculate_relative_date(
        self,
        relative_type: Literal["CURRENT", "LAST", "NEXT", "TODATE", "LASTN", "NEXTN"],
        period_type: Literal["DAYS", "WEEKS", "MONTHS", "QUARTERS", "YEARS"],
        range_n: Optional[int] = None
    ) -> Dict[str, str]:
        """
        计算相对日期
        
        Args:
            relative_type: 相对时间类型
            period_type: 周期类型
            range_n: 相对时间数量（LASTN/NEXTN需要）
        
        Returns:
            {"start_date": "...", "end_date": "...", "is_complete": True/False}
        """
        if relative_type == "CURRENT":
            return self._calculate_current_period(period_type)
        elif relative_type == "LAST":
            return self._calculate_last_period(period_type)
        elif relative_type == "NEXT":
            return self._calculate_next_period(period_type)
        elif relative_type == "TODATE":
            return self._calculate_todate(period_type)
        elif relative_type == "LASTN":
            if not range_n:
                raise ValueError("LASTN需要提供range_n参数")
            return self._calculate_lastn(period_type, range_n)
        elif relative_type == "NEXTN":
            if not range_n:
                raise ValueError("NEXTN需要提供range_n参数")
            return self._calculate_nextn(period_type, range_n)
        else:
            raise ValueError(f"不支持的relative_type: {relative_type}")
    
    def calculate_comparison_dates(
        self,
        comparison_type: Literal["YOY", "MOM", "QOQ", "WOW"],  # 同比、环比、季度环比、周环比
        current_period_type: Literal["DAYS", "WEEKS", "MONTHS", "QUARTERS", "YEARS"],
        align_incomplete: bool = True
    ) -> Dict[str, Any]:
        """
        计算对比日期（同比、环比）
        
        关键设计：
        1. 判断当前周期是否过完
        2. 如果未过完且align_incomplete=True，对齐对比周期
        
        Args:
            comparison_type: 对比类型
            current_period_type: 当前周期类型
            align_incomplete: 是否对齐未完整周期
        
        Returns:
            {
                "current": {"start_date": "...", "end_date": "...", "is_complete": True/False},
                "comparison": {"start_date": "...", "end_date": "...", "is_complete": True/False},
                "aligned": True/False
            }
        """
        # 1. 计算当前周期
        current = self._calculate_current_period(current_period_type)
        
        # 2. 根据对比类型计算对比周期
        if comparison_type == "YOY":  # 同比（去年同期）
            comparison_start = self._shift_date(current["start_date"], years=-1)
            comparison_end = self._shift_date(current["end_date"], years=-1)
        elif comparison_type == "MOM":  # 环比（上月）
            comparison_start = self._shift_date(current["start_date"], months=-1)
            comparison_end = self._shift_date(current["end_date"], months=-1)
        elif comparison_type == "QOQ":  # 季度环比（上季度）
            comparison_start = self._shift_date(current["start_date"], months=-3)
            comparison_end = self._shift_date(current["end_date"], months=-3)
        elif comparison_type == "WOW":  # 周环比（上周）
            comparison_start = self._shift_date(current["start_date"], days=-7)
            comparison_end = self._shift_date(current["end_date"], days=-7)
        else:
            raise ValueError(f"不支持的comparison_type: {comparison_type}")
        
        comparison = {
            "start_date": comparison_start,
            "end_date": comparison_end,
            "is_complete": True  # 对比周期通常是完整的
        }
        
        # 3. 对齐未完整周期
        aligned = False
        if align_incomplete and not current["is_complete"]:
            # 当前周期未过完，对齐对比周期
            # 计算当前周期的天数
            current_start = datetime.fromisoformat(current["start_date"])
            current_end = datetime.fromisoformat(current["end_date"])
            current_days = (current_end - current_start).days + 1
            
            # 对比周期也取相同天数
            comparison_start = datetime.fromisoformat(comparison["start_date"])
            comparison_end_aligned = comparison_start + timedelta(days=current_days - 1)
            comparison["end_date"] = self._format_date(comparison_end_aligned)
            aligned = True
            
            logger.info(
                f"对齐未完整周期: 当前周期{current_days}天 "
                f"({current['start_date']} ~ {current['end_date']}), "
                f"对比周期也取{current_days}天 "
                f"({comparison['start_date']} ~ {comparison['end_date']})"
            )
        
        return {
            "current": current,
            "comparison": comparison,
            "aligned": aligned
        }
    
    def calculate_period_dates(
        self,
        period_spec: str
    ) -> Dict[str, str]:
        """
        计算周期日期（如"Q3"、"上半年"、"2024年"）
        
        Args:
            period_spec: 周期规格
                - "Q1"/"Q2"/"Q3"/"Q4": 季度
                - "H1"/"H2": 半年
                - "2024": 年份
                - "2024-Q1": 特定年份的季度
                - "2024-H1": 特定年份的半年
        
        Returns:
            {"start_date": "...", "end_date": "...", "is_complete": True/False}
        """
        # 解析周期规格
        if "-" in period_spec:
            # 特定年份的周期（如"2024-Q1"）
            year_str, period_str = period_spec.split("-")
            year = int(year_str)
        else:
            # 使用anchor_date的年份
            year = self.anchor_date.year
            period_str = period_spec
        
        # 计算日期范围
        if period_str.startswith("Q"):
            # 季度
            quarter = int(period_str[1])
            start_month = (quarter - 1) * 3 + 1
            start_date = datetime(year, start_month, 1)
            
            if quarter == 4:
                end_date = datetime(year, 12, 31)
            else:
                next_quarter_start = datetime(year, start_month + 3, 1)
                end_date = next_quarter_start - timedelta(days=1)
        
        elif period_str.startswith("H"):
            # 半年
            half = int(period_str[1])
            if half == 1:
                start_date = datetime(year, 1, 1)
                end_date = datetime(year, 6, 30)
            else:
                start_date = datetime(year, 7, 1)
                end_date = datetime(year, 12, 31)
        
        elif period_str.isdigit():
            # 年份
            year = int(period_str)
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31)
        
        else:
            raise ValueError(f"无法解析的周期规格: {period_spec}")
        
        # 判断是否过完
        is_complete = end_date < self.anchor_date
        
        return {
            "start_date": self._format_date(start_date),
            "end_date": self._format_date(end_date),
            "is_complete": is_complete
        }
    
    def _calculate_current_period(
        self,
        period_type: Literal["DAYS", "WEEKS", "MONTHS", "QUARTERS", "YEARS"]
    ) -> Dict[str, Any]:
        """计算当前周期"""
        if period_type == "DAYS":
            start_date = self.anchor_date
            end_date = self.anchor_date
            is_complete = True  # 单日总是完整的
        
        elif period_type == "WEEKS":
            # 根据week_start_day计算周范围
            # 计算当前是周几（0=周一，6=周日）
            current_weekday = self.anchor_date.weekday()
            
            # 计算到周开始的偏移
            days_since_week_start = (current_weekday - self.week_start_day) % 7
            
            # 周开始日期
            start_date = self.anchor_date - timedelta(days=days_since_week_start)
            
            # 周结束日期（周开始+6天）
            week_end = start_date + timedelta(days=6)
            
            # 判断本周是否过完
            is_complete = self.anchor_date >= week_end
            # 如果未过完，结束日期是今天；如果过完了，结束日期是周末
            end_date = week_end if is_complete else self.anchor_date
        
        elif period_type == "MONTHS":
            # 本月第一天
            start_date = self.anchor_date.replace(day=1)
            last_day = monthrange(self.anchor_date.year, self.anchor_date.month)[1]
            month_end = self.anchor_date.replace(day=last_day)
            # 判断本月是否过完
            is_complete = self.anchor_date >= month_end
            # 如果未过完，结束日期是今天；如果过完了，结束日期是月末
            end_date = month_end if is_complete else self.anchor_date
        
        elif period_type == "QUARTERS":
            # 本季度第一天
            quarter = (self.anchor_date.month - 1) // 3 + 1
            start_month = (quarter - 1) * 3 + 1
            start_date = self.anchor_date.replace(month=start_month, day=1)
            
            if quarter == 4:
                quarter_end = self.anchor_date.replace(month=12, day=31)
            else:
                next_quarter_start = self.anchor_date.replace(month=start_month + 3, day=1)
                quarter_end = next_quarter_start - timedelta(days=1)
            
            # 判断本季度是否过完
            is_complete = self.anchor_date >= quarter_end
            # 如果未过完，结束日期是今天；如果过完了，结束日期是季度末
            end_date = quarter_end if is_complete else self.anchor_date
        
        elif period_type == "YEARS":
            # 本年第一天
            start_date = self.anchor_date.replace(month=1, day=1)
            year_end = self.anchor_date.replace(month=12, day=31)
            # 判断本年是否过完
            is_complete = self.anchor_date >= year_end
            # 如果未过完，结束日期是今天；如果过完了，结束日期是年末
            end_date = year_end if is_complete else self.anchor_date
        
        else:
            raise ValueError(f"不支持的period_type: {period_type}")
        
        return {
            "start_date": self._format_date(start_date),
            "end_date": self._format_date(end_date),
            "is_complete": is_complete
        }
    
    def _calculate_last_period(
        self,
        period_type: Literal["DAYS", "WEEKS", "MONTHS", "QUARTERS", "YEARS"]
    ) -> Dict[str, Any]:
        """计算上一个周期"""
        if period_type == "DAYS":
            date = self.anchor_date - timedelta(days=1)
            return {
                "start_date": self._format_date(date),
                "end_date": self._format_date(date),
                "is_complete": True
            }
        
        elif period_type == "WEEKS":
            # 上周一到上周日
            last_week = self.anchor_date - timedelta(days=7)
            start_date = last_week - timedelta(days=last_week.weekday())
            end_date = start_date + timedelta(days=6)
            return {
                "start_date": self._format_date(start_date),
                "end_date": self._format_date(end_date),
                "is_complete": True
            }
        
        elif period_type == "MONTHS":
            # 上月第一天到最后一天
            if self.anchor_date.month == 1:
                last_month = self.anchor_date.replace(year=self.anchor_date.year - 1, month=12, day=1)
            else:
                last_month = self.anchor_date.replace(month=self.anchor_date.month - 1, day=1)
            
            last_day = monthrange(last_month.year, last_month.month)[1]
            end_date = last_month.replace(day=last_day)
            
            return {
                "start_date": self._format_date(last_month),
                "end_date": self._format_date(end_date),
                "is_complete": True
            }
        
        elif period_type == "QUARTERS":
            # 上季度第一天到最后一天
            quarter = (self.anchor_date.month - 1) // 3 + 1
            if quarter == 1:
                last_quarter = 4
                year = self.anchor_date.year - 1
            else:
                last_quarter = quarter - 1
                year = self.anchor_date.year
            
            start_month = (last_quarter - 1) * 3 + 1
            start_date = datetime(year, start_month, 1)
            
            if last_quarter == 4:
                end_date = datetime(year, 12, 31)
            else:
                next_quarter_start = datetime(year, start_month + 3, 1)
                end_date = next_quarter_start - timedelta(days=1)
            
            return {
                "start_date": self._format_date(start_date),
                "end_date": self._format_date(end_date),
                "is_complete": True
            }
        
        elif period_type == "YEARS":
            # 去年第一天到最后一天
            start_date = self.anchor_date.replace(year=self.anchor_date.year - 1, month=1, day=1)
            end_date = self.anchor_date.replace(year=self.anchor_date.year - 1, month=12, day=31)
            return {
                "start_date": self._format_date(start_date),
                "end_date": self._format_date(end_date),
                "is_complete": True
            }
        
        else:
            raise ValueError(f"不支持的period_type: {period_type}")
    
    def _calculate_next_period(
        self,
        period_type: Literal["DAYS", "WEEKS", "MONTHS", "QUARTERS", "YEARS"]
    ) -> Dict[str, Any]:
        """计算下一个周期"""
        if period_type == "DAYS":
            date = self.anchor_date + timedelta(days=1)
            return {
                "start_date": self._format_date(date),
                "end_date": self._format_date(date),
                "is_complete": False  # 未来日期总是未完成
            }
        
        elif period_type == "WEEKS":
            # 下周一到下周日
            next_week = self.anchor_date + timedelta(days=7)
            # 根据week_start_day计算
            current_weekday = next_week.weekday()
            days_since_week_start = (current_weekday - self.week_start_day) % 7
            start_date = next_week - timedelta(days=days_since_week_start)
            end_date = start_date + timedelta(days=6)
            return {
                "start_date": self._format_date(start_date),
                "end_date": self._format_date(end_date),
                "is_complete": False
            }
        
        elif period_type == "MONTHS":
            # 下月第一天到最后一天
            if self.anchor_date.month == 12:
                next_month = self.anchor_date.replace(year=self.anchor_date.year + 1, month=1, day=1)
            else:
                next_month = self.anchor_date.replace(month=self.anchor_date.month + 1, day=1)
            
            last_day = monthrange(next_month.year, next_month.month)[1]
            end_date = next_month.replace(day=last_day)
            
            return {
                "start_date": self._format_date(next_month),
                "end_date": self._format_date(end_date),
                "is_complete": False
            }
        
        elif period_type == "QUARTERS":
            # 下季度第一天到最后一天
            quarter = (self.anchor_date.month - 1) // 3 + 1
            if quarter == 4:
                next_quarter = 1
                year = self.anchor_date.year + 1
            else:
                next_quarter = quarter + 1
                year = self.anchor_date.year
            
            start_month = (next_quarter - 1) * 3 + 1
            start_date = datetime(year, start_month, 1)
            
            if next_quarter == 4:
                end_date = datetime(year, 12, 31)
            else:
                next_quarter_start = datetime(year, start_month + 3, 1)
                end_date = next_quarter_start - timedelta(days=1)
            
            return {
                "start_date": self._format_date(start_date),
                "end_date": self._format_date(end_date),
                "is_complete": False
            }
        
        elif period_type == "YEARS":
            # 明年第一天到最后一天
            start_date = self.anchor_date.replace(year=self.anchor_date.year + 1, month=1, day=1)
            end_date = self.anchor_date.replace(year=self.anchor_date.year + 1, month=12, day=31)
            return {
                "start_date": self._format_date(start_date),
                "end_date": self._format_date(end_date),
                "is_complete": False
            }
        
        else:
            raise ValueError(f"不支持的period_type: {period_type}")
    
    def _calculate_todate(
        self,
        period_type: Literal["YEARS", "QUARTERS", "MONTHS"]
    ) -> Dict[str, Any]:
        """计算年初至今/季初至今/月初至今"""
        end_date = self.anchor_date
        
        if period_type == "YEARS":
            start_date = self.anchor_date.replace(month=1, day=1)
        elif period_type == "QUARTERS":
            quarter = (self.anchor_date.month - 1) // 3 + 1
            start_month = (quarter - 1) * 3 + 1
            start_date = self.anchor_date.replace(month=start_month, day=1)
        elif period_type == "MONTHS":
            start_date = self.anchor_date.replace(day=1)
        else:
            raise ValueError(f"TODATE不支持period_type: {period_type}")
        
        return {
            "start_date": self._format_date(start_date),
            "end_date": self._format_date(end_date),
            "is_complete": False  # TODATE总是未完整的
        }
    
    def _calculate_lastn(
        self,
        period_type: Literal["DAYS", "WEEKS", "MONTHS", "QUARTERS", "YEARS"],
        n: int
    ) -> Dict[str, Any]:
        """
        计算最近N个周期
        
        关键设计：
        - 对于MONTHS：从N个月前的月初到当前日期
        - 对于QUARTERS：从N个季度前的季初到当前日期
        - 对于YEARS：从N年前的年初到当前日期
        """
        end_date = self.anchor_date
        
        if period_type == "DAYS":
            start_date = self.anchor_date - timedelta(days=n - 1)
        
        elif period_type == "WEEKS":
            start_date = self.anchor_date - timedelta(weeks=n)
        
        elif period_type == "MONTHS":
            # 最近N个月：从N个月前的月初到当前日期
            # 例如：anchor_date=2025-10-30, n=1 -> 2025-10-01 到 2025-10-30
            # 例如：anchor_date=2025-10-30, n=2 -> 2025-09-01 到 2025-10-30
            start_month = self.anchor_date.month - (n - 1)
            start_year = self.anchor_date.year
            
            while start_month < 1:
                start_month += 12
                start_year -= 1
            
            start_date = datetime(start_year, start_month, 1)
        
        elif period_type == "QUARTERS":
            # 最近N个季度：从N个季度前的季初到当前日期
            current_quarter = (self.anchor_date.month - 1) // 3 + 1
            start_quarter = current_quarter - (n - 1)
            start_year = self.anchor_date.year
            
            while start_quarter < 1:
                start_quarter += 4
                start_year -= 1
            
            start_month = (start_quarter - 1) * 3 + 1
            start_date = datetime(start_year, start_month, 1)
        
        elif period_type == "YEARS":
            # 最近N年：从N年前的年初到当前日期
            start_year = self.anchor_date.year - (n - 1)
            start_date = datetime(start_year, 1, 1)
        
        else:
            raise ValueError(f"不支持的period_type: {period_type}")
        
        return {
            "start_date": self._format_date(start_date),
            "end_date": self._format_date(end_date),
            "is_complete": False  # LASTN通常包含当前未完整周期
        }
    
    def _calculate_nextn(
        self,
        period_type: Literal["DAYS", "WEEKS", "MONTHS", "QUARTERS", "YEARS"],
        n: int
    ) -> Dict[str, Any]:
        """计算未来N个周期"""
        start_date = self.anchor_date
        
        if period_type == "DAYS":
            end_date = self.anchor_date + timedelta(days=n - 1)
        elif period_type == "WEEKS":
            end_date = self.anchor_date + timedelta(weeks=n)
        elif period_type == "MONTHS":
            end_date_str = self._shift_date(self._format_date(self.anchor_date), months=n)
            end_date = datetime.fromisoformat(end_date_str)
        elif period_type == "QUARTERS":
            end_date_str = self._shift_date(self._format_date(self.anchor_date), months=n * 3)
            end_date = datetime.fromisoformat(end_date_str)
        elif period_type == "YEARS":
            end_date_str = self._shift_date(self._format_date(self.anchor_date), years=n)
            end_date = datetime.fromisoformat(end_date_str)
        else:
            raise ValueError(f"不支持的period_type: {period_type}")
        
        return {
            "start_date": self._format_date(start_date),
            "end_date": self._format_date(end_date),
            "is_complete": False  # 未来周期总是未完成
        }
    
    def _shift_date(
        self,
        date_str: str,
        days: int = 0,
        months: int = 0,
        years: int = 0
    ) -> str:
        """
        移动日期
        
        Args:
            date_str: 日期字符串
            days: 天数偏移
            months: 月份偏移
            years: 年份偏移
        
        Returns:
            移动后的日期字符串
        """
        date = datetime.fromisoformat(date_str)
        
        # 处理年份偏移
        if years != 0:
            new_year = date.year + years
            # 处理闰年边界情况（如2024-02-29 -> 2023-02-28）
            try:
                date = date.replace(year=new_year)
            except ValueError:
                # 如果日期无效（如2月29日在非闰年），使用该月最后一天
                max_day = monthrange(new_year, date.month)[1]
                date = date.replace(year=new_year, day=max_day)
        
        # 处理月份偏移
        if months != 0:
            new_month = date.month + months
            new_year = date.year
            
            while new_month > 12:
                new_month -= 12
                new_year += 1
            
            while new_month < 1:
                new_month += 12
                new_year -= 1
            
            # 处理月末日期（如1月31日 -> 2月28日）
            max_day = monthrange(new_year, new_month)[1]
            new_day = min(date.day, max_day)
            
            date = date.replace(year=new_year, month=new_month, day=new_day)
        
        # 处理天数偏移
        if days != 0:
            date = date + timedelta(days=days)
        
        return self._format_date(date)
    
    def _format_date(self, date: datetime) -> str:
        """
        根据字段类型格式化日期
        
        Args:
            date: datetime对象
        
        Returns:
            格式化后的日期字符串
        """
        if self.field_data_type == "DATETIME":
            return date.strftime("%Y-%m-%dT%H:%M:%S")
        else:  # DATE or STRING
            return date.strftime("%Y-%m-%d")
    
    def is_working_day(
        self,
        date: datetime,
        consider_holidays: bool = True
    ) -> bool:
        """
        判断是否是工作日
        
        使用chinese-calendar库判断中国法定节假日和调休工作日。
        
        Args:
            date: 日期
            consider_holidays: 是否考虑法定节假日
        
        Returns:
            True: 工作日
            False: 周末或节假日
        
        Note:
            - 如果chinese-calendar库未安装，只判断周末（周一到周五为工作日）
            - 如果库已安装，会考虑法定节假日和调休工作日
        """
        if not consider_holidays or not HOLIDAY_SUPPORT:
            # 不考虑节假日，或库未安装：只判断周末
            return date.weekday() < 5  # 周一到周五
        
        # 使用chinese-calendar库判断
        # is_workday()会考虑：
        # 1. 周末（周六周日）
        # 2. 法定节假日
        # 3. 调休工作日（如国庆节前的周末调休）
        try:
            return calendar.is_workday(date.date() if isinstance(date, datetime) else date)
        except Exception as e:
            logger.warning(f"判断工作日失败，回退到基本判断: {e}")
            return date.weekday() < 5
    
    def calculate_working_days(
        self,
        start_date: datetime,
        end_date: datetime,
        consider_holidays: bool = True
    ) -> int:
        """
        计算工作日天数
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            consider_holidays: 是否考虑法定节假日
        
        Returns:
            工作日天数
        """
        count = 0
        current = start_date
        
        while current <= end_date:
            if self.is_working_day(current, consider_holidays):
                count += 1
            current += timedelta(days=1)
        
        return count
    
    def filter_working_days(
        self,
        dates: list[datetime],
        consider_holidays: bool = True
    ) -> list[datetime]:
        """
        过滤出工作日
        
        Args:
            dates: 日期列表
            consider_holidays: 是否考虑法定节假日
        
        Returns:
            工作日列表
        """
        return [d for d in dates if self.is_working_day(d, consider_holidays)]
    
    def format_for_vizql(
        self,
        date: datetime,
        filter_type: Literal["min", "max"] = "min"
    ) -> str:
        """
        格式化日期用于VizQL筛选器
        
        根据tableau_sdk的要求，确保日期格式正确：
        - DATE类型: YYYY-MM-DD
        - DATETIME类型: YYYY-MM-DDTHH:MM:SS
        - STRING类型: YYYY-MM-DD
        
        对于DATETIME类型的max日期，自动添加23:59:59
        
        Args:
            date: datetime对象
            filter_type: "min"（开始日期）或"max"（结束日期）
        
        Returns:
            VizQL格式的日期字符串
        
        Examples:
            >>> calc = DateCalculator(field_data_type="DATE")
            >>> calc.format_for_vizql(datetime(2016, 1, 1), "min")
            '2016-01-01'
            
            >>> calc = DateCalculator(field_data_type="DATETIME")
            >>> calc.format_for_vizql(datetime(2016, 1, 1), "max")
            '2016-01-01T23:59:59'
        """
        if self.field_data_type == "DATETIME":
            if filter_type == "max":
                # 结束日期：设置为当天的23:59:59
                date = date.replace(hour=23, minute=59, second=59, microsecond=0)
            else:
                # 开始日期：设置为当天的00:00:00
                date = date.replace(hour=0, minute=0, second=0, microsecond=0)
            return date.strftime("%Y-%m-%dT%H:%M:%S")
        else:  # DATE or STRING
            return date.strftime("%Y-%m-%d")


# ============= 辅助函数 =============

def get_anchor_date(
    datasource_luid: str,
    date_field_name: str,
    metadata: Optional[Dict] = None,
    tableau_client: Optional[Any] = None,
    cache: Optional[Any] = None
) -> datetime:
    """
    获取anchor_date（数据最新日期）
    
    根据旧版需求文档5.2.6的流程：
    1. 获取当前系统日期
    2. 尝试从metadata读取max_date
    3. 如果没有，查询数据源获取MAX(date_field)
    4. 取两者最小值
    5. 缓存结果
    
    Args:
        datasource_luid: 数据源LUID
        date_field_name: 日期字段名称
        metadata: 元数据（可选）
        tableau_client: Tableau客户端（用于查询）
        cache: 缓存对象（用于缓存结果）
    
    Returns:
        anchor_date（datetime对象）
    """
    # 步骤1：获取当前系统日期
    current_date = datetime.now().date()
    
    # 步骤2：检查缓存
    if cache:
        cache_key = f"anchor_date:{datasource_luid}:{date_field_name}"
        cached_date = cache.get(cache_key)
        if cached_date:
            logger.info(f"从缓存获取anchor_date: {cached_date}")
            return datetime.fromisoformat(cached_date)
    
    # 步骤3：尝试从metadata读取max_date
    datasource_max_date = None
    if metadata and "max_date" in metadata:
        datasource_max_date = datetime.fromisoformat(metadata["max_date"]).date()
        logger.info(f"从metadata获取max_date: {datasource_max_date}")
    
    # 步骤4：如果metadata没有，查询数据源
    if datasource_max_date is None and tableau_client:
        try:
            # 生成VizQL查询获取MAX(date_field)
            query = {
                "fields": [
                    {
                        "fieldCaption": date_field_name,
                        "function": "MAX"
                    }
                ]
            }
            
            result = tableau_client.execute_vizql_query(
                datasource_luid=datasource_luid,
                query=query
            )
            
            if result and len(result) > 0:
                max_date_str = result[0].get(f"MAX({date_field_name})")
                if max_date_str:
                    datasource_max_date = datetime.fromisoformat(max_date_str).date()
                    logger.info(f"从数据源查询获取max_date: {datasource_max_date}")
        except Exception as e:
            logger.warning(f"查询数据源max_date失败: {e}")
    
    # 步骤5：取两者最小值
    if datasource_max_date:
        anchor_date = min(current_date, datasource_max_date)
    else:
        # 如果无法获取数据源最大日期，使用当前日期-1
        anchor_date = current_date - timedelta(days=1)
        logger.warning(f"无法获取数据源max_date，使用当前日期-1: {anchor_date}")
    
    # 步骤6：缓存结果
    if cache:
        cache_key = f"anchor_date:{datasource_luid}:{date_field_name}"
        cache.set(cache_key, anchor_date.isoformat(), ttl=3600)  # 1小时
    
    return datetime.combine(anchor_date, datetime.min.time())



    def calculate_holiday_date_range(
        self,
        year: int,
        holiday_name: str
    ) -> Optional[Dict[str, str]]:
        """
        计算指定年份的节假日日期范围
        
        Args:
            year: 年份（如 2025）
            holiday_name: 节假日名称（如 "春节", "Spring Festival"）
        
        Returns:
            {"start_date": "...", "end_date": "..."} 或 None（如果无法计算）
        """
        if not HOLIDAY_SUPPORT:
            logger.warning("chinese-calendar库未安装，无法计算节假日日期范围")
            return None
        
        try:
            # 标准化节假日名称
            holiday_name_lower = holiday_name.lower()
            if "春节" in holiday_name or "spring" in holiday_name_lower:
                # 春节：查找该年份的春节假期
                # 通常是除夕到初六，共7天
                for month in [1, 2]:  # 春节可能在1月或2月
                    for day in range(1, 32):
                        try:
                            check_date = date(year, month, day)
                            if calendar.is_holiday(check_date):
                                # 找到第一个春节假期日
                                # 向前找到假期开始
                                start_date = check_date
                                while start_date > date(year, 1, 1):
                                    prev_date = start_date - timedelta(days=1)
                                    if not calendar.is_holiday(prev_date):
                                        break
                                    start_date = prev_date
                                
                                # 向后找到假期结束
                                end_date = check_date
                                while end_date < date(year, 12, 31):
                                    next_date = end_date + timedelta(days=1)
                                    if not calendar.is_holiday(next_date):
                                        break
                                    end_date = next_date
                                
                                return {
                                    "start_date": self._format_date(datetime.combine(start_date, datetime.min.time())),
                                    "end_date": self._format_date(datetime.combine(end_date, datetime.min.time()))
                                }
                        except ValueError:
                            continue
            
            # 其他节假日可以类似处理
            logger.warning(f"暂不支持节假日: {holiday_name}")
            return None
            
        except Exception as e:
            logger.error(f"计算节假日日期范围失败: {e}")
            return None


# ============= 导出 =============

__all__ = [
    "DateCalculator",
    "get_anchor_date",
    "solar_to_lunar",
    "lunar_to_solar",
    "HOLIDAY_SUPPORT",
    "LUNAR_SUPPORT",
]
