# -*- coding: utf-8 -*-
"""
TimeHintGenerator - 时间提示生成器

从用户问题中提取时间表达式，生成参考日期范围提示。
只处理明确的、规则化的时间表达式，复杂表达式交给 LLM。

设计原则：
- 只处理明确的、规则化的时间表达式
- 复杂表达式（如"去年同期"、"上个财年Q3"）交给 LLM
- 提供提示而非替换，保留原始语义

使用方式:
1. 在构建 Prompt 前调用 generate_hints()
2. 将生成的 <time_hints> 添加到 Prompt 的 <context> 中
3. LLM 既能看到原始问题，又有明确的日期参考

财年支持:
- 通过 fiscal_year_start_month 参数配置财年起始月份
- 支持 "本财年"、"上财年"、"财年Q1-Q4" 等表达式
"""

import re
from datetime import date, timedelta
from typing import List, Tuple, Callable

from dateutil.relativedelta import relativedelta

from ..schemas.intermediate import TimeHint


class TimeHintGenerator:
    """时间提示生成器
    
    从用户问题中提取时间表达式，生成参考日期范围提示。
    只处理明确的、规则化的时间表达式，复杂表达式交给 LLM。
    
    Attributes:
        current_date: 当前日期
        fiscal_year_start_month: 财年起始月份 (1-12)
    """
    
    def __init__(
        self,
        current_date: date,
        fiscal_year_start_month: int = 1,
    ):
        """
        初始化时间提示生成器
        
        Args:
            current_date: 当前日期
            fiscal_year_start_month: 财年起始月份 (1-12)，默认为 1 (自然年)
        """
        self.current_date = current_date
        self.fiscal_year_start_month = fiscal_year_start_month
        
        # 静态时间表达式 → 计算函数
        self._static_patterns: dict[str, Callable[[date], Tuple[date, date]]] = {
            # ========== 相对日期 ==========
            "今天": lambda d: (d, d),
            "昨天": lambda d: (d - timedelta(days=1), d - timedelta(days=1)),
            "前天": lambda d: (d - timedelta(days=2), d - timedelta(days=2)),
            
            # ========== 本周/上周 ==========
            "本周": lambda d: (d - timedelta(days=d.weekday()), d),
            "上周": lambda d: (
                d - timedelta(days=d.weekday() + 7),
                d - timedelta(days=d.weekday() + 1)
            ),
            
            # ========== 本月/上月 ==========
            "本月": lambda d: (date(d.year, d.month, 1), d),
            "这个月": lambda d: (date(d.year, d.month, 1), d),
            "上个月": lambda d: (
                (date(d.year, d.month, 1) - relativedelta(months=1)),
                (date(d.year, d.month, 1) - timedelta(days=1))
            ),
            "上月": lambda d: (
                (date(d.year, d.month, 1) - relativedelta(months=1)),
                (date(d.year, d.month, 1) - timedelta(days=1))
            ),
            
            # ========== 本季度/上季度 ==========
            "本季度": lambda d: (
                date(d.year, ((d.month - 1) // 3) * 3 + 1, 1),
                d
            ),
            "上季度": lambda d: (
                date(d.year, ((d.month - 1) // 3) * 3 + 1, 1) - relativedelta(months=3),
                date(d.year, ((d.month - 1) // 3) * 3 + 1, 1) - timedelta(days=1)
            ),
            
            # ========== 本年/去年 ==========
            "今年": lambda d: (date(d.year, 1, 1), d),
            "本年": lambda d: (date(d.year, 1, 1), d),
            "去年": lambda d: (date(d.year - 1, 1, 1), date(d.year - 1, 12, 31)),
            
            # ========== 年初至今 ==========
            "年初至今": lambda d: (date(d.year, 1, 1), d),
            "YTD": lambda d: (date(d.year, 1, 1), d),
            
            # ========== 财年相关表达式 ==========
            "本财年": lambda d: self._calc_fiscal_year(d, 0),
            "上财年": lambda d: self._calc_fiscal_year(d, -1),
            "财年至今": lambda d: self._calc_fiscal_ytd(d),
            "FYTD": lambda d: self._calc_fiscal_ytd(d),
        }
        
        # 动态模式：最近N天/周/月
        self._dynamic_patterns: List[Tuple[str, Callable[[date, str], Tuple[date, date]]]] = [
            (r"最近(\d+)天", lambda d, n: (d - timedelta(days=int(n)), d)),
            (r"过去(\d+)天", lambda d, n: (d - timedelta(days=int(n)), d)),
            (r"最近(\d+)周", lambda d, n: (d - timedelta(weeks=int(n)), d)),
            (r"最近(\d+)个月", lambda d, n: (d - relativedelta(months=int(n)), d)),
            (r"过去(\d+)个月", lambda d, n: (d - relativedelta(months=int(n)), d)),
        ]
        
        # 财年季度模式：财年Q1, 财年Q2, 上财年Q3 等
        self._fiscal_quarter_patterns: List[Tuple[str, Callable[[date, str], Tuple[date, date]]]] = [
            (r"(?:本)?财年Q([1-4])", lambda d, q: self._calc_fiscal_quarter(d, 0, int(q))),
            (r"上财年Q([1-4])", lambda d, q: self._calc_fiscal_quarter(d, -1, int(q))),
        ]

    
    # ═══════════════════════════════════════════════════════════════════════════
    # 财年计算辅助方法
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _get_fiscal_year_start(self, calendar_date: date) -> date:
        """
        获取给定日期所属财年的起始日期
        
        例如：fiscal_year_start_month=4 (4月开始)
        - 2025-01-15 属于 FY2024，起始日期是 2024-04-01
        - 2025-05-15 属于 FY2025，起始日期是 2025-04-01
        
        Args:
            calendar_date: 日历日期
            
        Returns:
            该日期所属财年的起始日期
        """
        fy_start = self.fiscal_year_start_month
        if calendar_date.month >= fy_start:
            return date(calendar_date.year, fy_start, 1)
        else:
            return date(calendar_date.year - 1, fy_start, 1)
    
    def _calc_fiscal_year(self, d: date, offset: int) -> Tuple[date, date]:
        """
        计算财年日期范围
        
        Args:
            d: 当前日期
            offset: 0=本财年, -1=上财年, 1=下财年
        
        Returns:
            (start_date, end_date)
        """
        fy_start = self._get_fiscal_year_start(d)
        if offset != 0:
            fy_start = fy_start + relativedelta(years=offset)
        fy_end = fy_start + relativedelta(years=1) - timedelta(days=1)
        
        # 如果是本财年，结束日期是当前日期或财年结束日期（取较小值）
        if offset == 0:
            fy_end = min(fy_end, d)
        
        return (fy_start, fy_end)
    
    def _calc_fiscal_ytd(self, d: date) -> Tuple[date, date]:
        """计算财年至今（从财年开始到当前日期）"""
        fy_start = self._get_fiscal_year_start(d)
        return (fy_start, d)
    
    def _calc_fiscal_quarter(self, d: date, fy_offset: int, quarter: int) -> Tuple[date, date]:
        """
        计算财年季度日期范围
        
        Args:
            d: 当前日期
            fy_offset: 0=本财年, -1=上财年
            quarter: 1-4
        
        Returns:
            (start_date, end_date)
        """
        fy_start = self._get_fiscal_year_start(d)
        if fy_offset != 0:
            fy_start = fy_start + relativedelta(years=fy_offset)
        
        # 计算季度起始月份（相对于财年起始）
        quarter_start = fy_start + relativedelta(months=(quarter - 1) * 3)
        quarter_end = quarter_start + relativedelta(months=3) - timedelta(days=1)
        
        return (quarter_start, quarter_end)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 核心方法
    # ═══════════════════════════════════════════════════════════════════════════
    
    def generate_hints(self, question: str) -> List[TimeHint]:
        """
        从问题中提取时间表达式，生成提示
        
        Args:
            question: 用户问题
            
        Returns:
            时间提示列表，每个提示包含表达式和日期范围
            
        Example:
            >>> generator = TimeHintGenerator(date(2025, 1, 28))
            >>> hints = generator.generate_hints("上个月各地区的销售额")
            >>> hints[0].expression
            '上个月'
            >>> hints[0].start
            '2024-12-01'
            >>> hints[0].end
            '2024-12-31'
        """
        hints: List[TimeHint] = []
        
        # 1. 匹配静态模式
        for expr, calc_fn in self._static_patterns.items():
            if expr in question:
                start, end = calc_fn(self.current_date)
                hints.append(TimeHint(
                    expression=expr,
                    start=start.isoformat(),
                    end=end.isoformat(),
                ))
        
        # 2. 匹配动态模式
        for pattern, calc_fn in self._dynamic_patterns:
            match = re.search(pattern, question)
            if match:
                n = match.group(1)
                start, end = calc_fn(self.current_date, n)
                hints.append(TimeHint(
                    expression=match.group(0),
                    start=start.isoformat(),
                    end=end.isoformat(),
                ))
        
        # 3. 匹配财年季度模式
        for pattern, calc_fn in self._fiscal_quarter_patterns:
            match = re.search(pattern, question)
            if match:
                q = match.group(1)
                start, end = calc_fn(self.current_date, q)
                hints.append(TimeHint(
                    expression=match.group(0),
                    start=start.isoformat(),
                    end=end.isoformat(),
                ))
        
        return hints
    
    def format_for_prompt(self, question: str) -> str:
        """
        生成用于 Prompt 的时间提示 XML
        
        Args:
            question: 用户问题
            
        Returns:
            "<time_hints>...</time_hints>" 或空字符串
            
        Example:
            >>> generator = TimeHintGenerator(date(2025, 1, 28))
            >>> xml = generator.format_for_prompt("上个月各地区的销售额")
            >>> print(xml)
            <time_hints>
              <hint expression="上个月">2024-12-01 到 2024-12-31</hint>
            </time_hints>
        """
        hints = self.generate_hints(question)
        if not hints:
            return ""
        
        lines = []
        
        # 如果财年起始月份不是1月，添加财年配置说明
        if self.fiscal_year_start_month != 1:
            lines.append(f'  <fiscal_year_config>财年起始月份: {self.fiscal_year_start_month}月</fiscal_year_config>')
        
        for h in hints:
            lines.append(f'  <hint expression="{h.expression}">{h.start} 到 {h.end}</hint>')
        
        return "<time_hints>\n" + "\n".join(lines) + "\n</time_hints>"
