"""
查询工具函数

提供日期计算、数据采样、Token计数等工具函数
使用@tool装饰器自动生成schema和文档

注意：日期计算功能已迁移到date_calculator.py
"""
from datetime import datetime, timedelta
from typing import Literal, Optional, Tuple, Union, List, Dict, Any
import pandas as pd
from langchain_core.tools import tool
import tiktoken

from .date_calculator import DateCalculator, get_anchor_date


# ============= 日期计算函数（简化版，调用DateCalculator） =============

def calculate_date_range(
    time_filter: Dict[str, Any],
    anchor_date: Optional[Union[str, datetime]] = None,
    field_data_type: Literal["DATE", "DATETIME", "STRING"] = "DATE"
) -> Tuple[Optional[str], Optional[str]]:
    """
    计算日期范围，支持绝对时间和相对时间
    
    ⚠️ DEPRECATED: 此函数已废弃，推荐使用 DateParser 组件。
    
    这是向后兼容的包装函数，内部使用 DateParser 实现。
    新代码应该直接使用：
    - DateParser: 统一的日期解析入口
    - DateCalculator: 高级功能（周期对齐、同比环比等）
    
    Args:
        time_filter: 时间筛选规格，包含以下字段：
            - filter_type: "absolute" | "relative"
            - value: 绝对时间值（如"2016"、"2016-01"、"2016-01-01"、"2016-Q1"）
            - relative_type: 相对时间类型（CURRENT/LAST/TODATE/LASTN）
            - period_type: 周期类型（DAYS/WEEKS/MONTHS/QUARTERS/YEARS）
            - range_n: 相对时间数量（LASTN需要）
        anchor_date: 数据源最新日期（用于相对时间计算）
        field_data_type: 字段数据类型（DATE/DATETIME/STRING）
    
    Returns:
        (min_date, max_date): 日期范围元组
    
    Examples:
        >>> # 绝对时间 - 年份
        >>> calculate_date_range(
        ...     {"filter_type": "absolute", "value": "2016"},
        ...     field_data_type="DATE"
        ... )
        ("2016-01-01", "2016-12-31")
        
        >>> # 相对时间 - 最近3个月
        >>> calculate_date_range(
        ...     {
        ...         "filter_type": "relative",
        ...         "relative_type": "LASTN",
        ...         "period_type": "MONTHS",
        ...         "range_n": 3
        ...     },
        ...     anchor_date="2024-03-15",
        ...     field_data_type="DATE"
        ... )
        ("2023-12-15", "2024-03-15")
    """
    import warnings
    warnings.warn(
        "calculate_date_range() 已废弃，请使用 DateParser 组件",
        DeprecationWarning,
        stacklevel=2
    )
    
    from tableau_assistant.src.components.date_parser import DateParser
    from tableau_assistant.src.models.question import TimeRange, TimeRangeType, RelativeType, PeriodType
    
    filter_type = time_filter.get("filter_type")
    
    # 转换为 TimeRange 对象
    if filter_type == "absolute":
        value = time_filter.get("value")
        if not value:
            return None, None
        
        time_range = TimeRange(
            type=TimeRangeType.ABSOLUTE,
            value=value
        )
    
    elif filter_type == "relative":
        if not anchor_date:
            raise ValueError("相对时间筛选需要提供anchor_date参数")
        
        time_range = TimeRange(
            type=TimeRangeType.RELATIVE,
            relative_type=RelativeType(time_filter.get("relative_type")),
            period_type=PeriodType(time_filter.get("period_type")),
            range_n=time_filter.get("range_n")
        )
    
    else:
        raise ValueError(f"不支持的filter_type: {filter_type}")
    
    # 使用 DateParser 计算
    parser = DateParser()
    
    # 转换 anchor_date
    if anchor_date:
        if isinstance(anchor_date, str):
            anchor_date = datetime.fromisoformat(anchor_date.replace("Z", "+00:00"))
    
    start_date, end_date = parser.calculate_date_range(
        time_range=time_range,
        reference_date=anchor_date
    )
    
    # 根据字段类型格式化输出
    return _format_date_output(start_date, end_date, field_data_type)


def _format_date_output(
    min_date: str,
    max_date: str,
    field_data_type: Literal["DATE", "DATETIME", "STRING"]
) -> Tuple[str, str]:
    """
    根据字段类型格式化日期输出
    
    Args:
        min_date: 最小日期（YYYY-MM-DD格式）
        max_date: 最大日期（YYYY-MM-DD格式）
        field_data_type: 字段数据类型
    
    Returns:
        格式化后的日期范围
    """
    if field_data_type == "DATETIME":
        # DATETIME类型：添加时间部分
        min_date = f"{min_date}T00:00:00"
        max_date = f"{max_date}T23:59:59"
    elif field_data_type in ("DATE", "STRING"):
        # DATE和STRING类型：保持YYYY-MM-DD格式
        pass
    else:
        raise ValueError(f"不支持的field_data_type: {field_data_type}")
    
    return min_date, max_date


# ============= 数据采样函数 =============

def sample_dataframe(
    df: pd.DataFrame,
    max_rows: int = 30,
    strategy: Literal["head", "random", "stratified"] = "head"
) -> pd.DataFrame:
    """
    对DataFrame进行智能采样
    
    Args:
        df: 原始DataFrame
        max_rows: 最大行数
        strategy: 采样策略
            - "head": 取前N行（默认）
            - "random": 随机采样
            - "stratified": 分层采样（保留数据分布）
    
    Returns:
        采样后的DataFrame
    
    Examples:
        >>> df = pd.DataFrame({"A": range(100), "B": range(100)})
        >>> sampled = sample_dataframe(df, max_rows=10, strategy="head")
        >>> len(sampled)
        10
    """
    if len(df) <= max_rows:
        return df
    
    if strategy == "head":
        return df.head(max_rows)
    
    elif strategy == "random":
        return df.sample(n=max_rows, random_state=42)
    
    elif strategy == "stratified":
        # 分层采样：保留数据分布
        # 如果有分类列，按分类比例采样
        categorical_cols = df.select_dtypes(include=["object", "category"]).columns
        
        if len(categorical_cols) > 0:
            # 使用第一个分类列进行分层
            strat_col = categorical_cols[0]
            return df.groupby(strat_col, group_keys=False).apply(
                lambda x: x.sample(
                    n=min(len(x), max(1, int(max_rows * len(x) / len(df)))),
                    random_state=42
                )
            ).head(max_rows)
        else:
            # 没有分类列，使用随机采样
            return df.sample(n=max_rows, random_state=42)
    
    else:
        raise ValueError(f"不支持的采样策略: {strategy}")


# ============= Token计数函数 =============

def count_tokens(
    text: str,
    model: str = "gpt-4"
) -> int:
    """
    计算文本的Token数量
    
    Args:
        text: 要计算的文本
        model: 模型名称（用于选择tokenizer）
    
    Returns:
        Token数量
    
    Examples:
        >>> count_tokens("Hello, world!")
        4
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # 如果模型不存在，使用cl100k_base（GPT-4的编码）
        encoding = tiktoken.get_encoding("cl100k_base")
    
    return len(encoding.encode(text))


def estimate_tokens_from_dict(
    data: Dict[str, Any],
    model: str = "gpt-4"
) -> int:
    """
    估算字典数据的Token数量
    
    Args:
        data: 字典数据
        model: 模型名称
    
    Returns:
        估算的Token数量
    
    Examples:
        >>> estimate_tokens_from_dict({"key": "value"})
        6
    """
    import json
    text = json.dumps(data, ensure_ascii=False)
    return count_tokens(text, model)


# ============= 导出 =============

__all__ = [
    "calculate_date_range",
    "sample_dataframe",
    "count_tokens",
    "estimate_tokens_from_dict",
    "DateCalculator",  # 从date_calculator导出
    "get_anchor_date",  # 从date_calculator导出
]
