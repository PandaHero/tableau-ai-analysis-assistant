"""
Date Tools - 日期处理工具

薄封装 DateManager，提供日期解析和格式检测功能。

工具列表：
- parse_date: 解析日期表达式（相对/绝对）
- detect_date_format: 检测日期格式
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.tools import tool
import logging

from tableau_assistant.src.tools.base import (
    ToolResponse,
    ToolErrorCode,
    format_tool_response,
)

logger = logging.getLogger(__name__)


# 全局 DateManager 引用（由依赖注入设置）
_date_manager = None


def set_date_manager(manager: Any) -> None:
    """设置 DateManager 实例（依赖注入）"""
    global _date_manager
    _date_manager = manager
    logger.info("DateManager injected into date_tool")


def get_date_manager() -> Any:
    """获取 DateManager 实例"""
    return _date_manager


class ParseDateInput(BaseModel):
    """parse_date 工具输入参数"""
    expression: str = Field(
        description="日期表达式，如 '最近3个月', '2024年1月', 'last 7 days'"
    )
    reference_date: Optional[str] = Field(
        default=None,
        description="参考日期（YYYY-MM-DD 格式），默认为当前日期"
    )


class DetectDateFormatInput(BaseModel):
    """detect_date_format 工具输入参数"""
    sample_values: List[str] = Field(
        description="日期样本值列表，至少提供 3 个样本"
    )


def _parse_expression_to_time_range(expression: str) -> Any:
    """
    将自然语言日期表达式转换为 TimeRange 对象
    
    支持的表达式格式：
    - 相对日期：最近N天/周/月/年、上个月、本季度
    - 绝对日期：2024年1月、2024-01-01 到 2024-12-31
    
    Args:
        expression: 日期表达式
    
    Returns:
        TimeRange 对象
    """
    from tableau_assistant.src.models.question import TimeRange
    
    expression = expression.strip().lower()
    
    # 相对日期模式
    relative_patterns = {
        # 中文模式
        r'最近(\d+)天': ('LASTN', 'DAYS'),
        r'最近(\d+)周': ('LASTN', 'WEEKS'),
        r'最近(\d+)个?月': ('LASTN', 'MONTHS'),
        r'最近(\d+)年': ('LASTN', 'YEARS'),
        r'最近(\d+)个?季度': ('LASTN', 'QUARTERS'),
        r'上个?月': ('LAST', 'MONTHS'),
        r'上个?季度': ('LAST', 'QUARTERS'),
        r'上一?年': ('LAST', 'YEARS'),
        r'本月': ('CURRENT', 'MONTHS'),
        r'本季度': ('CURRENT', 'QUARTERS'),
        r'本年|今年': ('CURRENT', 'YEARS'),
        r'下个?月': ('NEXT', 'MONTHS'),
        r'下个?季度': ('NEXT', 'QUARTERS'),
        r'下一?年|明年': ('NEXT', 'YEARS'),
        # 英文模式
        r'last\s*(\d+)\s*days?': ('LASTN', 'DAYS'),
        r'last\s*(\d+)\s*weeks?': ('LASTN', 'WEEKS'),
        r'last\s*(\d+)\s*months?': ('LASTN', 'MONTHS'),
        r'last\s*(\d+)\s*years?': ('LASTN', 'YEARS'),
        r'last\s*(\d+)\s*quarters?': ('LASTN', 'QUARTERS'),
        r'last\s*month': ('LAST', 'MONTHS'),
        r'last\s*quarter': ('LAST', 'QUARTERS'),
        r'last\s*year': ('LAST', 'YEARS'),
        r'this\s*month': ('CURRENT', 'MONTHS'),
        r'this\s*quarter': ('CURRENT', 'QUARTERS'),
        r'this\s*year': ('CURRENT', 'YEARS'),
        r'next\s*month': ('NEXT', 'MONTHS'),
        r'next\s*quarter': ('NEXT', 'QUARTERS'),
        r'next\s*year': ('NEXT', 'YEARS'),
    }
    
    import re
    
    for pattern, (relative_type, period_type) in relative_patterns.items():
        match = re.search(pattern, expression)
        if match:
            range_n = None
            if match.groups():
                try:
                    range_n = int(match.group(1))
                except (IndexError, ValueError):
                    pass
            
            return TimeRange(
                type="relative",
                relative_type=relative_type,
                period_type=period_type,
                range_n=range_n
            )
    
    # 绝对日期模式
    # 年月格式：2024年1月、2024-01
    year_month_patterns = [
        r'(\d{4})年(\d{1,2})月',
        r'(\d{4})-(\d{1,2})',
        r'(\d{4})/(\d{1,2})',
    ]
    
    for pattern in year_month_patterns:
        match = re.search(pattern, expression)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            
            # 计算月份的开始和结束日期
            import calendar
            _, last_day = calendar.monthrange(year, month)
            
            return TimeRange(
                type="absolute",
                start_date=f"{year}-{month:02d}-01",
                end_date=f"{year}-{month:02d}-{last_day:02d}"
            )
    
    # 年份格式：2024年、2024
    year_patterns = [
        r'(\d{4})年',
        r'^(\d{4})$',
    ]
    
    for pattern in year_patterns:
        match = re.search(pattern, expression)
        if match:
            year = int(match.group(1))
            return TimeRange(
                type="absolute",
                start_date=f"{year}-01-01",
                end_date=f"{year}-12-31"
            )
    
    # 日期范围格式：2024-01-01 到 2024-12-31
    range_patterns = [
        r'(\d{4}-\d{2}-\d{2})\s*(?:到|至|-|~)\s*(\d{4}-\d{2}-\d{2})',
        r'from\s*(\d{4}-\d{2}-\d{2})\s*to\s*(\d{4}-\d{2}-\d{2})',
    ]
    
    for pattern in range_patterns:
        match = re.search(pattern, expression)
        if match:
            return TimeRange(
                type="absolute",
                start_date=match.group(1),
                end_date=match.group(2)
            )
    
    # 无法解析
    raise ValueError(f"无法解析日期表达式: {expression}")


@tool
def parse_date(
    expression: str,
    reference_date: Optional[str] = None
) -> str:
    """
    解析日期表达式
    
    将自然语言日期表达式转换为具体的日期范围。
    支持相对日期（如"最近3个月"）和绝对日期（如"2024年1月"）。
    
    Args:
        expression: 日期表达式，支持以下格式：
            - 相对日期：最近N天/周/月/年、上个月、本季度、last 7 days
            - 绝对日期：2024年1月、2024-01、2024年
            - 日期范围：2024-01-01 到 2024-12-31
        reference_date: 参考日期（YYYY-MM-DD 格式），用于计算相对日期，默认为当前日期
    
    Returns:
        JSON 格式的日期范围：
        - 成功：{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
        - 失败：{"start_date": null, "end_date": null, "error": "错误信息"}
    
    Examples:
        >>> parse_date("最近3个月")
        {"start_date": "2024-10-01", "end_date": "2024-12-31"}
        
        >>> parse_date("2024年1月")
        {"start_date": "2024-01-01", "end_date": "2024-01-31"}
        
        >>> parse_date("last 7 days")
        {"start_date": "2024-12-02", "end_date": "2024-12-08"}
    """
    global _date_manager
    
    # 检查依赖
    if _date_manager is None:
        return '{"start_date": null, "end_date": null, "error": "DateManager 未初始化"}'
    
    try:
        # 解析表达式为 TimeRange
        time_range = _parse_expression_to_time_range(expression)
        
        # 解析参考日期
        ref_date = None
        if reference_date:
            from datetime import datetime
            try:
                ref_date = datetime.strptime(reference_date, "%Y-%m-%d")
            except ValueError:
                return f'{{"start_date": null, "end_date": null, "error": "无效的参考日期格式: {reference_date}，请使用 YYYY-MM-DD 格式"}}'
        
        # 使用 DateManager 解析
        start_date, end_date = _date_manager.parse_time_range(
            time_range=time_range,
            reference_date=ref_date
        )
        
        logger.info(f"parse_date: '{expression}' -> {start_date} to {end_date}")
        return f'{{"start_date": "{start_date}", "end_date": "{end_date}"}}'
        
    except ValueError as e:
        logger.warning(f"parse_date failed: {e}")
        return f'{{"start_date": null, "end_date": null, "error": "{str(e)}"}}'
    except Exception as e:
        logger.error(f"parse_date error: {e}")
        return f'{{"start_date": null, "end_date": null, "error": "解析失败: {str(e)}"}}'


@tool
def detect_date_format(sample_values: List[str]) -> str:
    """
    检测日期格式
    
    分析样本值，检测其日期格式类型。用于处理 STRING 类型的日期字段。
    
    Args:
        sample_values: 日期样本值列表，建议至少提供 3 个样本以提高准确性
    
    Returns:
        JSON 格式的检测结果：
        - 成功：{"format_type": "ISO_DATE", "pattern": "YYYY-MM-DD", "conversion_hint": "..."}
        - 失败：{"format_type": null, "error": "错误信息"}
    
    Examples:
        >>> detect_date_format(["2024-01-15", "2024-02-20", "2024-03-25"])
        {"format_type": "ISO_DATE", "pattern": "YYYY-MM-DD", "conversion_hint": "使用 YYYY-MM-DD 格式解析"}
        
        >>> detect_date_format(["01/15/2024", "02/20/2024", "03/25/2024"])
        {"format_type": "US_DATE", "pattern": "MM/DD/YYYY", "conversion_hint": "使用 MM/DD/YYYY 格式解析"}
        
        >>> detect_date_format(["15/01/2024", "20/02/2024", "25/03/2024"])
        {"format_type": "EU_DATE", "pattern": "DD/MM/YYYY", "conversion_hint": "使用 DD/MM/YYYY 格式解析"}
    """
    global _date_manager
    
    # 检查依赖
    if _date_manager is None:
        return '{"format_type": null, "error": "DateManager 未初始化"}'
    
    # 验证输入
    if not sample_values:
        return '{"format_type": null, "error": "样本值列表不能为空"}'
    
    if len(sample_values) < 2:
        return '{"format_type": null, "error": "建议至少提供 2 个样本值以提高检测准确性"}'
    
    try:
        # 使用 DateManager 检测格式
        format_type = _date_manager.detect_field_date_format(
            sample_values=sample_values,
            confidence_threshold=0.7
        )
        
        if format_type:
            # 获取格式信息
            info = _date_manager.get_format_info(format_type)
            
            result = {
                "format_type": format_type.value,
                "pattern": info.get("pattern", ""),
                "conversion_hint": f"使用 {info.get('pattern', '')} 格式解析"
            }
            
            logger.info(f"detect_date_format: detected {format_type.value}")
            
            import json
            return json.dumps(result, ensure_ascii=False)
        else:
            return '{"format_type": null, "error": "无法检测日期格式，样本值可能不是有效的日期"}'
        
    except Exception as e:
        logger.error(f"detect_date_format error: {e}")
        return f'{{"format_type": null, "error": "检测失败: {str(e)}"}}'


__all__ = [
    "parse_date",
    "detect_date_format",
    "set_date_manager",
    "get_date_manager",
    "ParseDateInput",
    "DetectDateFormatInput",
]
