"""Preprocess 组件 - 预处理层（0 LLM 调用）。

本模块实现预处理层，在 LLM 调用前完成确定性预处理，把"高频可规则化"的不确定性从 LLM 中剥离。

设计原则（Requirements 1）：
- 0 LLM 调用，纯规则处理
- 时间解析使用规则，非 LLM
- 生成稳定的 canonical_question 用于缓存 key
- 从历史对话中提取已确认项

主要功能：
- normalize(): 全角半角归一、空白归一、单位归一
- extract_time(): 规则解析相对时间
- extract_slots(): 从历史抽取已确认项
- build_canonical(): 生成稳定的 canonical_question
- extract_terms(): 提取候选业务术语

Usage:
    from tableau_assistant.src.agents.semantic_parser.components.preprocess import (
        PreprocessComponent,
        PreprocessResult,
        TimeContext,
        MemorySlots,
    )
    
    preprocess = PreprocessComponent()
    result = preprocess.execute(
        question="各地区上月销售额是多少？",
        history=history,
        current_date=date.today(),
    )
    
    print(result.canonical_question)  # "time:last_month 各地区销售额是多少"
    print(result.time_context)  # TimeContext(start_date=..., end_date=..., is_relative=True)
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tableau_assistant.src.infra.config.settings import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 数据结构定义
# ═══════════════════════════════════════════════════════════════════════════

class TimeGrain(str, Enum):
    """时间粒度枚举"""
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    QUARTER = "QUARTER"
    YEAR = "YEAR"


@dataclass
class TimeContext:
    """时间上下文。
    
    表示从用户问题中解析出的时间范围信息。
    
    Attributes:
        start_date: 开始日期（包含）
        end_date: 结束日期（包含）
        is_relative: 是否为相对时间（如"上月"、"近7天"）
        grain_hint: 时间粒度提示（DAY/WEEK/MONTH/QUARTER/YEAR）
        original_expression: 原始时间表达式（如"上月"、"近7天"）
    """
    start_date: date | None = None
    end_date: date | None = None
    is_relative: bool = False
    grain_hint: TimeGrain | None = None
    original_expression: str | None = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为可 JSON 序列化的字典"""
        return {
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_relative": self.is_relative,
            "grain_hint": self.grain_hint.value if self.grain_hint else None,
            "original_expression": self.original_expression,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TimeContext":
        """从字典创建实例"""
        return cls(
            start_date=date.fromisoformat(data["start_date"]) if data.get("start_date") else None,
            end_date=date.fromisoformat(data["end_date"]) if data.get("end_date") else None,
            is_relative=data.get("is_relative", False),
            grain_hint=TimeGrain(data["grain_hint"]) if data.get("grain_hint") else None,
            original_expression=data.get("original_expression"),
        )


@dataclass
class MemorySlots:
    """从历史对话中提取的已确认项。
    
    用于多轮对话中保持上下文一致性。
    
    Attributes:
        confirmed_dimensions: 已确认的维度字段列表
        confirmed_measures: 已确认的度量字段列表
        confirmed_filters: 已确认的过滤条件列表
        time_preference: 用户的时间偏好
        granularity_preference: 用户的粒度偏好（如"按月"、"按地区"）
    """
    confirmed_dimensions: List[str] = field(default_factory=list)
    confirmed_measures: List[str] = field(default_factory=list)
    confirmed_filters: List[Dict[str, Any]] = field(default_factory=list)
    time_preference: TimeContext | None = None
    granularity_preference: str | None = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为可 JSON 序列化的字典"""
        return {
            "confirmed_dimensions": self.confirmed_dimensions,
            "confirmed_measures": self.confirmed_measures,
            "confirmed_filters": self.confirmed_filters,
            "time_preference": self.time_preference.to_dict() if self.time_preference else None,
            "granularity_preference": self.granularity_preference,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemorySlots":
        """从字典创建实例"""
        return cls(
            confirmed_dimensions=data.get("confirmed_dimensions", []),
            confirmed_measures=data.get("confirmed_measures", []),
            confirmed_filters=data.get("confirmed_filters", []),
            time_preference=TimeContext.from_dict(data["time_preference"]) if data.get("time_preference") else None,
            granularity_preference=data.get("granularity_preference"),
        )


class PreprocessResult(BaseModel):
    """预处理结果。
    
    包含预处理后的所有信息，供后续组件使用。
    
    Attributes:
        canonical_question: 规范化后的问题（用于缓存 key）
        normalized_question: 规范化后的问题（保留原始语义）
        time_context: 时间上下文
        memory_slots: 从历史对话中提取的已确认项
        extracted_terms: 提取的候选业务术语
    """
    canonical_question: str = Field(description="规范化后的问题（用于缓存 key）")
    normalized_question: str = Field(description="规范化后的问题（保留原始语义）")
    time_context: Optional[Dict[str, Any]] = Field(default=None, description="时间上下文")
    memory_slots: Dict[str, Any] = Field(default_factory=dict, description="从历史对话中提取的已确认项")
    extracted_terms: List[str] = Field(default_factory=list, description="提取的候选业务术语")
    
    class Config:
        """Pydantic 配置"""
        extra = "forbid"


# ═══════════════════════════════════════════════════════════════════════════
# 常量定义
# ═══════════════════════════════════════════════════════════════════════════

# 停用词列表（不作为业务术语）
STOPWORDS = {
    # 中文停用词
    "的", "是", "在", "有", "和", "与", "或", "了", "吗", "呢", "吧",
    "什么", "怎么", "如何", "多少", "哪些", "哪个", "为什么",
    "请", "帮", "我", "你", "他", "她", "它", "们",
    "这", "那", "这个", "那个", "这些", "那些",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "个", "只", "条", "件", "份", "次", "回",
    "能", "可以", "可能", "应该", "需要", "想要", "希望",
    "看", "看看", "查", "查看", "查询", "分析", "统计", "计算",
    "给", "告诉", "显示", "展示", "列出",
    # 英文停用词
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "can", "could", "may", "might", "must", "shall", "should",
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "my", "your", "his", "her", "its", "our", "their",
    "this", "that", "these", "those",
    "and", "or", "but", "if", "then", "else", "for", "to", "of", "in", "on", "at",
}

# 时间相关词汇（不作为业务术语，但用于时间解析）
TIME_WORDS = {
    "今天", "昨天", "前天", "明天", "后天",
    "本周", "上周", "下周", "这周",
    "本月", "上月", "下月", "这个月", "上个月", "下个月",
    "本季", "上季", "下季", "本季度", "上季度", "下季度",
    "今年", "去年", "明年", "本年", "上年", "下年",
    "近", "最近", "过去", "之前", "以前", "以来",
    "天", "周", "月", "季", "季度", "年",
    "日", "号", "星期", "礼拜",
    "年初", "年末", "年底", "月初", "月末", "月底",
    "上半年", "下半年", "第一季度", "第二季度", "第三季度", "第四季度",
    "Q1", "Q2", "Q3", "Q4",
}

# 计算相关词汇（不作为业务术语，但用于计算类型识别）
COMPUTATION_WORDS = {
    "同比", "环比", "增长", "增长率", "下降", "下降率",
    "占比", "比例", "百分比", "比重",
    "排名", "排行", "前", "后", "TOP", "top",
    "累计", "累积", "汇总", "合计", "总计", "总",
    "平均", "均值", "平均值", "均",
    "最大", "最小", "最高", "最低", "极值",
    "移动平均", "滚动", "滑动",
    "每", "按", "分", "分组", "分类",
}

# 单位归一化映射
UNIT_NORMALIZATION = {
    "万": "10000",
    "千": "1000",
    "百": "100",
    "亿": "100000000",
    "k": "1000",
    "K": "1000",
    "m": "1000000",
    "M": "1000000",
    "b": "1000000000",
    "B": "1000000000",
}

# 相对时间模式（正则表达式）
RELATIVE_TIME_PATTERNS = [
    # 近N天/周/月/年
    (r"近(\d+)天", "days"),
    (r"近(\d+)周", "weeks"),
    (r"近(\d+)个?月", "months"),
    (r"近(\d+)年", "years"),
    (r"最近(\d+)天", "days"),
    (r"最近(\d+)周", "weeks"),
    (r"最近(\d+)个?月", "months"),
    (r"最近(\d+)年", "years"),
    (r"过去(\d+)天", "days"),
    (r"过去(\d+)周", "weeks"),
    (r"过去(\d+)个?月", "months"),
    (r"过去(\d+)年", "years"),
    # 本周/上周/本月/上月/今年/去年
    (r"今天", "today"),
    (r"昨天", "yesterday"),
    (r"前天", "day_before_yesterday"),
    (r"本周", "this_week"),
    (r"上周", "last_week"),
    (r"这周", "this_week"),
    (r"本月", "this_month"),
    (r"上月", "last_month"),
    (r"上个月", "last_month"),
    (r"这个月", "this_month"),
    (r"本季度?", "this_quarter"),
    (r"上季度?", "last_quarter"),
    (r"今年", "this_year"),
    (r"去年", "last_year"),
    (r"本年", "this_year"),
    (r"上年", "last_year"),
    # 年初/年末/月初/月末
    (r"年初", "year_start"),
    (r"年末", "year_end"),
    (r"年底", "year_end"),
    (r"月初", "month_start"),
    (r"月末", "month_end"),
    (r"月底", "month_end"),
    # 上半年/下半年
    (r"上半年", "first_half"),
    (r"下半年", "second_half"),
    # 季度
    (r"第?一季度?|Q1", "q1"),
    (r"第?二季度?|Q2", "q2"),
    (r"第?三季度?|Q3", "q3"),
    (r"第?四季度?|Q4", "q4"),
]


# ═══════════════════════════════════════════════════════════════════════════
# PreprocessComponent 实现
# ═══════════════════════════════════════════════════════════════════════════

class PreprocessComponent:
    """预处理组件 - 0 LLM 调用。
    
    在 LLM 调用前完成确定性预处理，把"高频可规则化"的不确定性从 LLM 中剥离。
    
    主要功能：
    - normalize(): 全角半角归一、空白归一、单位归一
    - extract_time(): 规则解析相对时间
    - extract_slots(): 从历史抽取已确认项
    - build_canonical(): 生成稳定的 canonical_question
    - extract_terms(): 提取候选业务术语
    """
    
    def __init__(self):
        """初始化预处理组件"""
        # 编译正则表达式（性能优化）
        self._time_patterns = [
            (re.compile(pattern, re.IGNORECASE), time_type)
            for pattern, time_type in RELATIVE_TIME_PATTERNS
        ]
    
    def _days_in_month(self, year: int, month: int) -> int:
        """获取指定月份的天数。
        
        Args:
            year: 年份
            month: 月份（1-12）
        
        Returns:
            该月的天数
        """
        if month in (1, 3, 5, 7, 8, 10, 12):
            return 31
        elif month in (4, 6, 9, 11):
            return 30
        elif month == 2:
            # 闰年判断
            if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
                return 29
            return 28
        return 30  # 默认值
    
    def execute(
        self,
        question: str,
        history: List[Dict[str, str]] | None = None,
        current_date: date | None = None,
    ) -> PreprocessResult:
        """执行预处理。
        
        Args:
            question: 用户问题
            history: 对话历史（list of {"role": "user/assistant", "content": "..."}）
            current_date: 当前日期（用于相对时间计算，默认为今天）
        
        Returns:
            PreprocessResult 包含规范化问题、时间上下文、记忆槽位、候选术语
        """
        if current_date is None:
            current_date = date.today()
        
        # 1. 规范化
        normalized = self.normalize(question)
        
        # 2. 时间解析
        time_context = self.extract_time(normalized, current_date)
        
        # 3. 历史槽位提取
        memory_slots = self.extract_slots(history)
        
        # 4. 构建 canonical question
        canonical = self.build_canonical(normalized, time_context)
        
        # 5. 提取候选术语
        terms = self.extract_terms(normalized)
        
        logger.debug(
            f"Preprocess completed: "
            f"normalized='{normalized[:50]}...', "
            f"canonical='{canonical[:50]}...', "
            f"time_context={time_context}, "
            f"terms={terms[:5]}..."
        )
        
        return PreprocessResult(
            canonical_question=canonical,
            normalized_question=normalized,
            time_context=time_context.to_dict() if time_context else None,
            memory_slots=memory_slots.to_dict(),
            extracted_terms=terms,
        )
    
    def normalize(self, question: str) -> str:
        """规范化问题文本。
        
        包括：
        - 全角半角归一
        - 空白字符归一
        - 去除 emoji 和特殊符号
        - 数字格式统一
        
        Args:
            question: 原始问题
        
        Returns:
            规范化后的问题
        """
        if not question:
            return ""
        
        # 1. 全角转半角
        result = self._fullwidth_to_halfwidth(question)
        
        # 2. 去除 emoji 和特殊符号
        result = self._remove_emoji_and_special(result)
        
        # 3. 空白字符归一（多个空白变成单个空格）
        result = re.sub(r'\s+', ' ', result)
        
        # 4. 去除首尾空白
        result = result.strip()
        
        # 5. 标点符号归一（中文标点转英文）
        result = self._normalize_punctuation(result)
        
        # 6. 单位归一（数值+单位）
        result = self._normalize_units(result)
        
        return result

    
    def _fullwidth_to_halfwidth(self, text: str) -> str:
        """全角字符转半角字符"""
        result = []
        for char in text:
            code = ord(char)
            # 全角空格
            if code == 0x3000:
                result.append(' ')
            # 其他全角字符（！到～）
            elif 0xFF01 <= code <= 0xFF5E:
                result.append(chr(code - 0xFEE0))
            else:
                result.append(char)
        return ''.join(result)
    
    def _remove_emoji_and_special(self, text: str) -> str:
        """去除 emoji 和特殊符号"""
        # 保留中文、英文、数字、常用标点
        result = []
        for char in text:
            # 中文字符
            if '\u4e00' <= char <= '\u9fff':
                result.append(char)
            # 英文字母和数字
            elif char.isalnum():
                result.append(char)
            # 常用标点和空白
            elif char in ' ,.?!;:，。？！；：、""''（）()[]【】-_+=/\\@#$%&*':
                result.append(char)
            # 其他字符跳过
        return ''.join(result)
    
    def _normalize_punctuation(self, text: str) -> str:
        """标点符号归一化"""
        replacements = {
            '，': ',',
            '。': '.',
            '？': '?',
            '！': '!',
            '；': ';',
            '：': ':',
            '"': '"',
            '"': '"',
            ''': "'",
            ''': "'",
            '（': '(',
            '）': ')',
            '【': '[',
            '】': ']',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text

    def _normalize_units(self, text: str) -> str:
        """单位归一化：将数值+单位转换为标准数值。"""
        if not text:
            return text

        pattern = re.compile(r"(\d+(?:\.\d+)?)(\s*)(万|千|百|亿|k|K|m|M|b|B)")

        def _format_number(value: float) -> str:
            if value.is_integer():
                return str(int(value))
            return str(value)

        def _replace(match: re.Match) -> str:
            number_str = match.group(1)
            unit = match.group(3)
            multiplier = UNIT_NORMALIZATION.get(unit)
            if multiplier is None:
                return match.group(0)
            try:
                value = float(number_str) * float(multiplier)
                return _format_number(value)
            except Exception:
                return match.group(0)

        return pattern.sub(_replace, text)
    
    def extract_time(

        self,
        question: str,
        current_date: date,
    ) -> TimeContext | None:
        """从问题中提取时间上下文。
        
        使用规则解析相对时间，不调用 LLM。
        
        Args:
            question: 规范化后的问题
            current_date: 当前日期
        
        Returns:
            TimeContext 或 None（如果没有时间表达式）
        """
        for pattern, time_type in self._time_patterns:
            match = pattern.search(question)
            if match:
                return self._parse_time_expression(
                    match=match,
                    time_type=time_type,
                    current_date=current_date,
                    original_expression=match.group(0),
                )
        
        return None
    
    def _parse_time_expression(
        self,
        match: re.Match,
        time_type: str,
        current_date: date,
        original_expression: str,
    ) -> TimeContext:
        """解析时间表达式。
        
        Args:
            match: 正则匹配结果
            time_type: 时间类型
            current_date: 当前日期
            original_expression: 原始时间表达式
        
        Returns:
            TimeContext
        """
        start_date: date | None = None
        end_date: date | None = None
        grain_hint: TimeGrain | None = None
        is_relative = True
        
        # 近N天/周/月/年
        if time_type == "days":
            n = int(match.group(1))
            end_date = current_date
            start_date = current_date - timedelta(days=n - 1)
            grain_hint = TimeGrain.DAY
        
        elif time_type == "weeks":
            n = int(match.group(1))
            end_date = current_date
            start_date = current_date - timedelta(weeks=n)
            grain_hint = TimeGrain.WEEK
        
        elif time_type == "months":
            n = int(match.group(1))
            end_date = current_date
            # 按实际月份计算：往前推 n 个月
            year = current_date.year
            month = current_date.month - n
            while month <= 0:
                month += 12
                year -= 1
            # 处理日期溢出（如 3月31日 往前推1个月 -> 2月28日）
            day = min(current_date.day, self._days_in_month(year, month))
            start_date = date(year, month, day)
            grain_hint = TimeGrain.MONTH
        
        elif time_type == "years":
            n = int(match.group(1))
            end_date = current_date
            start_date = current_date.replace(year=current_date.year - n)
            grain_hint = TimeGrain.YEAR
        
        # 今天/昨天/前天
        elif time_type == "today":
            start_date = end_date = current_date
            grain_hint = TimeGrain.DAY
        
        elif time_type == "yesterday":
            start_date = end_date = current_date - timedelta(days=1)
            grain_hint = TimeGrain.DAY
        
        elif time_type == "day_before_yesterday":
            start_date = end_date = current_date - timedelta(days=2)
            grain_hint = TimeGrain.DAY
        
        # 本周/上周
        elif time_type == "this_week":
            # 本周一到今天
            weekday = current_date.weekday()
            start_date = current_date - timedelta(days=weekday)
            end_date = current_date
            grain_hint = TimeGrain.WEEK
        
        elif time_type == "last_week":
            # 上周一到上周日
            weekday = current_date.weekday()
            end_date = current_date - timedelta(days=weekday + 1)
            start_date = end_date - timedelta(days=6)
            grain_hint = TimeGrain.WEEK
        
        # 本月/上月
        elif time_type == "this_month":
            start_date = current_date.replace(day=1)
            end_date = current_date
            grain_hint = TimeGrain.MONTH
        
        elif time_type == "last_month":
            # 上月第一天
            first_of_this_month = current_date.replace(day=1)
            last_of_last_month = first_of_this_month - timedelta(days=1)
            start_date = last_of_last_month.replace(day=1)
            end_date = last_of_last_month
            grain_hint = TimeGrain.MONTH
        
        # 本季度/上季度
        elif time_type == "this_quarter":
            quarter = (current_date.month - 1) // 3
            start_date = date(current_date.year, quarter * 3 + 1, 1)
            end_date = current_date
            grain_hint = TimeGrain.QUARTER
        
        elif time_type == "last_quarter":
            quarter = (current_date.month - 1) // 3
            if quarter == 0:
                # 上一年第四季度
                start_date = date(current_date.year - 1, 10, 1)
                end_date = date(current_date.year - 1, 12, 31)
            else:
                start_date = date(current_date.year, (quarter - 1) * 3 + 1, 1)
                end_month = quarter * 3
                if end_month == 3:
                    end_date = date(current_date.year, 3, 31)
                elif end_month == 6:
                    end_date = date(current_date.year, 6, 30)
                elif end_month == 9:
                    end_date = date(current_date.year, 9, 30)
            grain_hint = TimeGrain.QUARTER
        
        # 今年/去年
        elif time_type == "this_year":
            start_date = date(current_date.year, 1, 1)
            end_date = current_date
            grain_hint = TimeGrain.YEAR
        
        elif time_type == "last_year":
            start_date = date(current_date.year - 1, 1, 1)
            end_date = date(current_date.year - 1, 12, 31)
            grain_hint = TimeGrain.YEAR
        
        # 年初/年末
        elif time_type == "year_start":
            start_date = end_date = date(current_date.year, 1, 1)
            grain_hint = TimeGrain.DAY
        
        elif time_type == "year_end":
            start_date = end_date = date(current_date.year, 12, 31)
            grain_hint = TimeGrain.DAY
        
        # 月初/月末
        elif time_type == "month_start":
            start_date = end_date = current_date.replace(day=1)
            grain_hint = TimeGrain.DAY
        
        elif time_type == "month_end":
            # 下月第一天减一天
            if current_date.month == 12:
                next_month = date(current_date.year + 1, 1, 1)
            else:
                next_month = date(current_date.year, current_date.month + 1, 1)
            start_date = end_date = next_month - timedelta(days=1)
            grain_hint = TimeGrain.DAY
        
        # 上半年/下半年
        elif time_type == "first_half":
            start_date = date(current_date.year, 1, 1)
            end_date = date(current_date.year, 6, 30)
            grain_hint = TimeGrain.MONTH
        
        elif time_type == "second_half":
            start_date = date(current_date.year, 7, 1)
            end_date = date(current_date.year, 12, 31)
            grain_hint = TimeGrain.MONTH
        
        # 季度
        elif time_type == "q1":
            start_date = date(current_date.year, 1, 1)
            end_date = date(current_date.year, 3, 31)
            grain_hint = TimeGrain.QUARTER
        
        elif time_type == "q2":
            start_date = date(current_date.year, 4, 1)
            end_date = date(current_date.year, 6, 30)
            grain_hint = TimeGrain.QUARTER
        
        elif time_type == "q3":
            start_date = date(current_date.year, 7, 1)
            end_date = date(current_date.year, 9, 30)
            grain_hint = TimeGrain.QUARTER
        
        elif time_type == "q4":
            start_date = date(current_date.year, 10, 1)
            end_date = date(current_date.year, 12, 31)
            grain_hint = TimeGrain.QUARTER
        
        return TimeContext(
            start_date=start_date,
            end_date=end_date,
            is_relative=is_relative,
            grain_hint=grain_hint,
            original_expression=original_expression,
        )

    def extract_slots(
        self,
        history: List[Dict[str, str]] | None,
    ) -> MemorySlots:
        """从历史对话中提取已确认项。
        
        分析对话历史，提取用户已确认的维度、度量、过滤条件等。
        
        Args:
            history: 对话历史（list of {"role": "user/assistant", "content": "..."}）
        
        Returns:
            MemorySlots 包含已确认的维度、度量、过滤条件等
        """
        if not history:
            return MemorySlots()
        
        confirmed_dimensions: List[str] = []
        confirmed_measures: List[str] = []
        confirmed_filters: List[Dict[str, Any]] = []
        time_preference: TimeContext | None = None
        granularity_preference: str | None = None
        
        # 遍历历史对话，提取已确认项
        for msg in history:
            content = msg.get("content", "")
            role = msg.get("role", "")
            
            # 从 assistant 回复中提取确认的字段
            if role == "assistant":
                # 提取确认的维度（如"按地区"、"按产品类别"）
                dim_patterns = [
                    r"按(.+?)(?:分组|分类|统计|查看|展示)",
                    r"(.+?)维度",
                ]
                for pattern in dim_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if match and match not in confirmed_dimensions:
                            confirmed_dimensions.append(match)
                
                # 提取确认的度量（如"销售额"、"订单数"）
                measure_patterns = [
                    r"(?:查看|统计|计算|分析)(.+?)(?:数据|情况|趋势)?",
                ]
                for pattern in measure_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if match and match not in confirmed_measures:
                            confirmed_measures.append(match)
                
                # 提取粒度偏好
                granularity_patterns = [
                    r"按(日|周|月|季度?|年)(?:统计|查看|展示)",
                ]
                for pattern in granularity_patterns:
                    match = re.search(pattern, content)
                    if match:
                        granularity_preference = match.group(1)
            
            # 从 user 问题中提取时间偏好
            if role == "user":
                time_ctx = self.extract_time(content, date.today())
                if time_ctx:
                    time_preference = time_ctx
        
        return MemorySlots(
            confirmed_dimensions=confirmed_dimensions,
            confirmed_measures=confirmed_measures,
            confirmed_filters=confirmed_filters,
            time_preference=time_preference,
            granularity_preference=granularity_preference,
        )
    
    def build_canonical(
        self,
        normalized_question: str,
        time_context: TimeContext | None,
    ) -> str:
        """构建规范化问题（用于缓存 key）。
        
        将相对时间表达式替换为规范化标记，确保相同语义的问题生成相同的 key。
        
        例如：
        - "各地区上月销售额是多少" -> "time:last_month 各地区销售额是多少"
        - "近7天订单数" -> "time:7_days 订单数"
        
        Args:
            normalized_question: 规范化后的问题
            time_context: 时间上下文
        
        Returns:
            规范化后的问题（用于缓存 key）
        """
        canonical = normalized_question
        
        if time_context and time_context.original_expression:
            # 将原始时间表达式替换为规范化标记
            time_marker = self._get_time_marker(time_context)
            canonical = canonical.replace(time_context.original_expression, "")
            canonical = f"time:{time_marker} {canonical}".strip()
        
        # 去除多余空格
        canonical = re.sub(r'\s+', ' ', canonical).strip()
        
        return canonical
    
    def _get_time_marker(self, time_context: TimeContext) -> str:
        """获取时间标记。
        
        Args:
            time_context: 时间上下文
        
        Returns:
            时间标记字符串
        """
        expr = time_context.original_expression or ""
        
        # 近N天/周/月/年
        for pattern, unit in [
            (r"近(\d+)天", "days"),
            (r"最近(\d+)天", "days"),
            (r"过去(\d+)天", "days"),
            (r"近(\d+)周", "weeks"),
            (r"最近(\d+)周", "weeks"),
            (r"过去(\d+)周", "weeks"),
            (r"近(\d+)个?月", "months"),
            (r"最近(\d+)个?月", "months"),
            (r"过去(\d+)个?月", "months"),
            (r"近(\d+)年", "years"),
            (r"最近(\d+)年", "years"),
            (r"过去(\d+)年", "years"),
        ]:
            match = re.search(pattern, expr)
            if match:
                return f"{match.group(1)}_{unit}"
        
        # 固定时间表达式映射
        time_markers = {
            "今天": "today",
            "昨天": "yesterday",
            "前天": "day_before_yesterday",
            "本周": "this_week",
            "上周": "last_week",
            "这周": "this_week",
            "本月": "this_month",
            "上月": "last_month",
            "上个月": "last_month",
            "这个月": "this_month",
            "本季度": "this_quarter",
            "上季度": "last_quarter",
            "本季": "this_quarter",
            "上季": "last_quarter",
            "今年": "this_year",
            "去年": "last_year",
            "本年": "this_year",
            "上年": "last_year",
            "年初": "year_start",
            "年末": "year_end",
            "年底": "year_end",
            "月初": "month_start",
            "月末": "month_end",
            "月底": "month_end",
            "上半年": "first_half",
            "下半年": "second_half",
            "第一季度": "q1",
            "第二季度": "q2",
            "第三季度": "q3",
            "第四季度": "q4",
            "一季度": "q1",
            "二季度": "q2",
            "三季度": "q3",
            "四季度": "q4",
            "Q1": "q1",
            "Q2": "q2",
            "Q3": "q3",
            "Q4": "q4",
        }
        
        return time_markers.get(expr, expr)
    
    def extract_terms(self, normalized_question: str) -> List[str]:
        """提取候选业务术语。
        
        从规范化问题中提取可能的业务术语，用于后续的 Schema Linking。
        
        Args:
            normalized_question: 规范化后的问题
        
        Returns:
            候选业务术语列表
        """
        terms: List[str] = []
        
        # 简单分词（按空格和标点分割）
        words = re.split(r'[\s,.:;?!，。：；？！]+', normalized_question)
        
        for word in words:
            if self._is_valid_term(word):
                terms.append(word)
        
        # 去重并保持顺序
        seen = set()
        unique_terms = []
        for term in terms:
            if term not in seen:
                seen.add(term)
                unique_terms.append(term)
        
        return unique_terms
    
    def _is_valid_term(self, word: str) -> bool:
        """判断是否为有效术语。
        
        Args:
            word: 待判断的词
        
        Returns:
            是否为有效术语
        """
        # 长度检查（使用配置值）
        if len(word) < settings.preprocess_min_term_length:
            return False
        
        # 停用词检查
        if word in STOPWORDS:
            return False
        
        # 时间词检查
        if word in TIME_WORDS:
            return False
        
        # 计算词检查
        if word in COMPUTATION_WORDS:
            return False
        
        return True
