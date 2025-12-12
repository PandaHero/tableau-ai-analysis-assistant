"""
Date Tools - 日期处理工具

提供日期计算和格式检测功能。

设计原则（与 VizQL API 对齐）：
- LLM 负责：理解自然语言，输出 TimeFilterSpec 格式
- 绝对日期：LLM 直接输出 RFC 3339 格式（YYYY-MM-DD），无需 DateParser 计算
- 相对日期：DateParser 根据 period_type 和 date_range_type 计算具体日期
- 离散日期：DateParser 展开为具体日期列表

工具列表：
- process_time_filter: 处理 TimeFilterSpec，返回 VizQL 兼容的筛选参数
- calculate_relative_dates: 计算相对日期的具体日期范围
- detect_date_format: 检测日期格式

注意：这些工具是纯计算工具，不依赖 WorkflowContext。
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from langchain_core.tools import tool
import logging
import json
import re

logger = logging.getLogger(__name__)


def _get_date_manager():
    """获取 DateManager 实例（按需创建）"""
    from tableau_assistant.src.capabilities.date_processing import DateManager
    return DateManager()


class ProcessTimeFilterInput(BaseModel):
    """process_time_filter 工具输入参数"""
    time_filter_json: str = Field(
        description="""TimeFilterSpec JSON 格式，包含：
- mode: "absolute_range", "relative", 或 "set"
- 绝对日期范围: start_date, end_date (YYYY-MM-DD 格式)
- 相对日期: period_type, date_range_type, range_n
- 离散日期: date_values (日期值列表)"""
    )
    reference_date: Optional[str] = Field(
        default=None,
        description="参考日期（YYYY-MM-DD 格式），用于相对时间计算"
    )


class DetectDateFormatInput(BaseModel):
    """detect_date_format 工具输入参数"""
    sample_values: List[str] = Field(
        description="日期样本值列表，至少提供 2 个样本"
    )


def _expand_date_values(date_values: List[str]) -> List[str]:
    """展开日期值（将季度展开为月份）"""
    expanded = []
    for value in date_values:
        # 季度格式: 2024-Q1 → 展开为月份
        quarter_match = re.match(r'^(\d{4})-Q([1-4])$', value, re.IGNORECASE)
        if quarter_match:
            year = int(quarter_match.group(1))
            quarter = int(quarter_match.group(2))
            start_month = (quarter - 1) * 3 + 1
            for m in range(start_month, start_month + 3):
                expanded.append(f"{year}-{m:02d}")
        else:
            expanded.append(value)
    return expanded


@tool
def process_time_filter(
    time_filter_json: str,
    reference_date: Optional[str] = None
) -> str:
    """
    处理时间筛选，返回 VizQL 兼容的筛选参数
    
    LLM 输出 TimeFilterSpec 格式，此工具转换为 VizQL 筛选参数。
    
    Args:
        time_filter_json: TimeFilterSpec JSON 格式
            绝对日期范围: {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-12-31"}
            相对日期: {"mode": "relative", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
            离散日期: {"mode": "set", "date_values": ["2024-01", "2024-02"]}
        reference_date: 参考日期（YYYY-MM-DD），用于相对时间计算
    
    Returns:
        JSON 格式的 VizQL 筛选参数:
        - 绝对日期范围: {"filter_type": "QUANTITATIVE_DATE", "quantitative_filter_type": "RANGE", "min_date": "...", "max_date": "..."}
        - 相对日期: {"filter_type": "DATE", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
        - 离散日期: {"filter_type": "SET", "values": [...], "exclude": false}
    
    Examples:
        >>> process_time_filter('{"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-12-31"}')
        {"filter_type": "QUANTITATIVE_DATE", "quantitative_filter_type": "RANGE", "min_date": "2024-01-01", "max_date": "2024-12-31"}
        
        >>> process_time_filter('{"mode": "relative", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}')
        {"filter_type": "DATE", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
    """
    try:
        from tableau_assistant.src.models.semantic.query import TimeFilterSpec
        from tableau_assistant.src.models.semantic.enums import TimeFilterMode
        
        # 解析 TimeFilterSpec
        time_filter_dict = json.loads(time_filter_json)
        time_filter = TimeFilterSpec(**time_filter_dict)
        
        # 根据模式生成 VizQL 筛选参数
        if time_filter.mode == TimeFilterMode.ABSOLUTE_RANGE:
            result = {
                "filter_type": "QUANTITATIVE_DATE",
                "quantitative_filter_type": "RANGE",
                "min_date": time_filter.start_date,
                "max_date": time_filter.end_date
            }
        
        elif time_filter.mode == TimeFilterMode.RELATIVE:
            result = {
                "filter_type": "DATE",
                "period_type": time_filter.period_type.value,
                "date_range_type": time_filter.date_range_type.value,
            }
            if time_filter.range_n is not None:
                result["range_n"] = time_filter.range_n
            if time_filter.anchor_date is not None:
                result["anchor_date"] = time_filter.anchor_date
        
        elif time_filter.mode == TimeFilterMode.SET:
            # 展开日期值
            expanded_values = _expand_date_values(time_filter.date_values)
            result = {
                "filter_type": "SET",
                "values": expanded_values,
                "exclude": False
            }
        
        else:
            return json.dumps({"error": f"不支持的时间筛选模式: {time_filter.mode}"})
        
        logger.info(f"process_time_filter: {result}")
        return json.dumps(result, ensure_ascii=False)
        
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"JSON 解析失败: {e}"})
    except Exception as e:
        logger.error(f"process_time_filter error: {e}")
        return json.dumps({"error": str(e)})


@tool
def calculate_relative_dates(
    time_filter_json: str,
    reference_date: Optional[str] = None
) -> str:
    """
    计算相对日期的具体日期范围
    
    当需要将相对日期转换为具体日期时使用（例如用于 QUANTITATIVE_DATE 筛选）。
    
    Args:
        time_filter_json: TimeFilterSpec JSON 格式（mode 必须为 "relative"）
        reference_date: 参考日期（YYYY-MM-DD），默认今天
    
    Returns:
        JSON 格式: {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
    
    Examples:
        >>> calculate_relative_dates('{"mode": "relative", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}')
        {"start_date": "2024-10-01", "end_date": "2024-12-11"}
    """
    try:
        from tableau_assistant.src.models.semantic.query import TimeFilterSpec
        from tableau_assistant.src.models.semantic.enums import TimeFilterMode
        from datetime import datetime
        
        # 解析 TimeFilterSpec
        time_filter_dict = json.loads(time_filter_json)
        time_filter = TimeFilterSpec(**time_filter_dict)
        
        if time_filter.mode != TimeFilterMode.RELATIVE:
            return json.dumps({"error": "此工具只处理相对日期（mode=relative）"})
        
        # 解析参考日期
        ref_date = None
        if reference_date:
            ref_date = datetime.strptime(reference_date, "%Y-%m-%d")
        
        # 使用 DateManager 计算日期范围
        date_manager = _get_date_manager()
        start_date, end_date = date_manager.calculate_relative_dates(
            time_filter=time_filter,
            reference_date=ref_date
        )
        
        logger.info(f"calculate_relative_dates: {start_date} to {end_date}")
        return json.dumps({"start_date": start_date, "end_date": end_date})
        
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"JSON 解析失败: {e}"})
    except Exception as e:
        logger.error(f"calculate_relative_dates error: {e}")
        return json.dumps({"error": str(e)})


@tool
def detect_date_format(sample_values: List[str]) -> str:
    """
    检测日期格式
    
    分析样本值，检测其日期格式类型。用于处理 STRING 类型的日期字段。
    
    Args:
        sample_values: 日期样本值列表，至少 2 个样本
    
    Returns:
        JSON 格式: {"format_type": "ISO_DATE", "pattern": "YYYY-MM-DD"}
    """
    if not sample_values or len(sample_values) < 2:
        return '{"format_type": null, "error": "至少需要 2 个样本值"}'
    
    try:
        date_manager = _get_date_manager()
        format_type = date_manager.detect_field_date_format(
            sample_values=sample_values,
            confidence_threshold=0.7
        )
        
        if format_type:
            info = date_manager.get_format_info(format_type)
            return json.dumps({
                "format_type": format_type.value,
                "pattern": info.get("pattern", ""),
            }, ensure_ascii=False)
        else:
            return '{"format_type": null, "error": "无法检测日期格式"}'
        
    except Exception as e:
        logger.error(f"detect_date_format error: {e}")
        return json.dumps({"format_type": None, "error": str(e)})


__all__ = [
    # 工具（与 VizQL API 对齐）
    "process_time_filter",
    "calculate_relative_dates",
    "detect_date_format",
    # 输入模型
    "ProcessTimeFilterInput",
    "DetectDateFormatInput",
]
