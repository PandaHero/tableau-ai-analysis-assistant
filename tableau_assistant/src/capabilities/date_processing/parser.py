"""
日期解析器（DateParser）

职责：
1. 解析 LLM 输出的标准格式 TimeRange
2. 计算具体的日期范围（start_date, end_date）
3. 验证日期范围的合理性
4. 不做自然语言语义理解（由 LLM 负责）

设计原则：
- LLM 负责：理解自然语言，输出标准格式
- DateParser 负责：解析标准格式，计算具体日期
- 代码优先：使用 DateCalculator 进行精确计算
- 无状态：每次调用独立计算，不存储结果
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import logging

from tableau_assistant.src.models.question import TimeRange, TimeRangeType, RelativeType, PeriodType
from tableau_assistant.src.capabilities.date_processing.calculator import DateCalculator

logger = logging.getLogger(__name__)


class DateParser:
    """
    日期解析器
    
    将 LLM 输出的标准格式 TimeRange 转换为具体的日期范围。
    
    使用场景：
    - 在 Query Builder 阶段使用
    - 接收 Understanding Agent 输出的 TimeRange
    - 计算具体的 start_date 和 end_date
    - 传递给 DateFilterConverter 生成 VizQL 筛选器
    
    示例：
        >>> parser = DateParser()
        >>> time_range = TimeRange(
        ...     type=TimeRangeType.RELATIVE,
        ...     relative_type=RelativeType.LASTN,
        ...     period_type=PeriodType.MONTHS,
        ...     range_n=3
        ... )
        >>> start, end = parser.calculate_date_range(
        ...     time_range,
        ...     reference_date=datetime(2024, 12, 31)
        ... )
        >>> print(start, end)
        2024-10-01 2024-12-31
    """
    
    def __init__(self, date_calculator: Optional[DateCalculator] = None):
        """
        初始化日期解析器
        
        Args:
            date_calculator: DateCalculator 实例（可选）
                           如果不提供，会在 calculate_date_range 时创建
        """
        self.date_calculator = date_calculator
        self._cache: Dict[str, Tuple[str, str]] = {}  # 简单的内存缓存
    
    def calculate_date_range(
        self,
        time_range: TimeRange,
        reference_date: Optional[datetime] = None,
        max_date: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        计算日期范围
        
        这是主要的公共方法，接收 TimeRange 和参考日期，返回具体的日期范围。
        
        Args:
            time_range: LLM 输出的 TimeRange 对象
            reference_date: 参考日期（用于相对时间计算）
                          如果为 None，使用当前日期 - 1 天
            max_date: 数据源的最大日期（可选）
                     如果提供，会调整 end_date 不超过此日期
        
        Returns:
            (start_date, end_date) 元组，格式为 "YYYY-MM-DD"
        
        Raises:
            ValueError: 如果 TimeRange 格式不正确或无法解析
        
        Examples:
            # 绝对时间 - 年份
            >>> time_range = TimeRange(type="absolute", value="2024")
            >>> parser.calculate_date_range(time_range)
            ("2024-01-01", "2024-12-31")
            
            # 绝对时间 - 日期范围
            >>> time_range = TimeRange(
            ...     type="absolute",
            ...     start_date="2024-01-01",
            ...     end_date="2024-03-31"
            ... )
            >>> parser.calculate_date_range(time_range)
            ("2024-01-01", "2024-03-31")
            
            # 相对时间
            >>> time_range = TimeRange(
            ...     type="relative",
            ...     relative_type="LASTN",
            ...     period_type="MONTHS",
            ...     range_n=3
            ... )
            >>> parser.calculate_date_range(time_range, datetime(2024, 12, 31))
            ("2024-10-01", "2024-12-31")
        """
        import time
        start_time = time.time()
        
        # 记录输入信息
        logger.debug(
            f"开始日期计算 - "
            f"类型: {time_range.type}, "
            f"参考日期: {reference_date.date() if reference_date else 'None'}, "
            f"max_date: {max_date or 'None'}"
        )
        
        # 生成缓存键
        cache_key = self._generate_cache_key(time_range, reference_date, max_date)
        
        # 检查缓存
        if cache_key in self._cache:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.debug(
                f"缓存命中 - "
                f"耗时: {elapsed_ms:.2f}ms, "
                f"缓存大小: {len(self._cache)}"
            )
            return self._cache[cache_key]
        
        # 计算日期范围
        try:
            # 记录计算方法
            if time_range.type == TimeRangeType.ABSOLUTE:
                if time_range.start_date and time_range.end_date:
                    method = "range"
                elif time_range.value:
                    method = f"value({time_range.value})"
                else:
                    method = "unknown"
            elif time_range.type == TimeRangeType.RELATIVE:
                method = f"relative({time_range.relative_type}/{time_range.period_type})"
            else:
                method = "unknown"
            
            logger.debug(f"计算方法: {method}")
            
            start_date, end_date = self._calculate_dates(time_range, reference_date)
            
            # 验证日期范围
            self._validate_date_range(start_date, end_date)
            
            # 边界调整（如果提供了 max_date）
            adjusted = False
            if max_date:
                original_end = end_date
                start_date, end_date = self._adjust_boundaries(
                    start_date, end_date, max_date
                )
                adjusted = (original_end != end_date)
            
            # 缓存结果
            self._cache[cache_key] = (start_date, end_date)
            
            # 计算耗时
            elapsed_ms = (time.time() - start_time) * 1000
            
            # 记录完成信息
            logger.info(
                f"日期计算完成 - "
                f"类型: {time_range.type}, "
                f"方法: {method}, "
                f"结果: {start_date} to {end_date}, "
                f"边界调整: {'是' if adjusted else '否'}, "
                f"耗时: {elapsed_ms:.2f}ms"
            )
            
            return (start_date, end_date)
        
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(
                f"日期计算失败 - "
                f"类型: {time_range.type}, "
                f"错误: {e}, "
                f"耗时: {elapsed_ms:.2f}ms, "
                f"TimeRange: {time_range}"
            )
            raise ValueError(f"无法计算日期范围: {e}") from e
    
    def _calculate_dates(
        self,
        time_range: TimeRange,
        reference_date: Optional[datetime]
    ) -> Tuple[str, str]:
        """
        计算具体日期（内部方法）
        
        根据 TimeRange 的类型调用不同的计算逻辑：
        - absolute: 解析 value 或 start_date/end_date
        - relative: 使用 DateCalculator 计算相对时间
        
        Args:
            time_range: TimeRange 对象
            reference_date: 参考日期
        
        Returns:
            (start_date, end_date) 元组
        """
        if time_range.type == TimeRangeType.ABSOLUTE:
            return self._calculate_absolute_dates(time_range, reference_date)
        elif time_range.type == TimeRangeType.RELATIVE:
            return self._calculate_relative_dates(time_range, reference_date)
        else:
            raise ValueError(f"不支持的 TimeRange 类型: {time_range.type}")
    
    def _calculate_absolute_dates(
        self,
        time_range: TimeRange,
        reference_date: Optional[datetime]
    ) -> Tuple[str, str]:
        """
        计算绝对时间日期
        
        支持两种格式：
        1. start_date + end_date（LLM 直接输出日期范围）
        2. value（年份、季度、月份、日期）
        
        Args:
            time_range: TimeRange 对象
            reference_date: 参考日期（用于补全年份）
        
        Returns:
            (start_date, end_date) 元组
        """
        # 格式1: 已经有 start_date 和 end_date
        if time_range.start_date and time_range.end_date:
            return (time_range.start_date, time_range.end_date)
        
        # 格式2: 使用 value 字段
        if time_range.value:
            return self._parse_value_format(time_range.value, reference_date)
        
        raise ValueError("绝对时间必须提供 start_date+end_date 或 value")
    
    def _parse_value_format(
        self,
        value: str,
        reference_date: Optional[datetime]
    ) -> Tuple[str, str]:
        """
        解析 value 字段的标准格式
        
        支持的格式：
        - 年份: "2024" → ("2024-01-01", "2024-12-31")
        - 季度: "2024-Q1" → ("2024-01-01", "2024-03-31")
        - 月份: "2024-03" → ("2024-03-01", "2024-03-31")
        - 日期: "2024-03-15" → ("2024-03-15", "2024-03-15")
        
        Args:
            value: 日期值字符串
            reference_date: 参考日期（用于补全年份）
        
        Returns:
            (start_date, end_date) 元组
        """
        value = value.strip()
        
        # 年份: "2024"
        if len(value) == 4 and value.isdigit():
            year = int(value)
            return (f"{year}-01-01", f"{year}-12-31")
        
        # 季度: "2024-Q1"
        if "-Q" in value.upper():
            parts = value.upper().split("-Q")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                year = int(parts[0])
                quarter = int(parts[1])
                if 1 <= quarter <= 4:
                    start_month = (quarter - 1) * 3 + 1
                    end_month = quarter * 3
                    # 计算季度最后一天
                    from calendar import monthrange
                    _, last_day = monthrange(year, end_month)
                    return (
                        f"{year}-{start_month:02d}-01",
                        f"{year}-{end_month:02d}-{last_day:02d}"
                    )
        
        # 月份: "2024-03"
        if len(value) == 7 and value[4] == "-":
            try:
                year, month = value.split("-")
                year = int(year)
                month = int(month)
                if 1 <= month <= 12:
                    from calendar import monthrange
                    _, last_day = monthrange(year, month)
                    return (
                        f"{year}-{month:02d}-01",
                        f"{year}-{month:02d}-{last_day:02d}"
                    )
            except ValueError:
                pass
        
        # 日期: "2024-03-15"
        if len(value) == 10 and value[4] == "-" and value[7] == "-":
            try:
                # 验证日期格式
                datetime.strptime(value, "%Y-%m-%d")
                return (value, value)
            except ValueError:
                pass
        
        raise ValueError(f"无法解析日期格式: {value}")
    
    def _calculate_relative_dates(
        self,
        time_range: TimeRange,
        reference_date: Optional[datetime]
    ) -> Tuple[str, str]:
        """
        计算相对时间日期
        
        使用 DateCalculator 进行计算。
        
        Args:
            time_range: TimeRange 对象
            reference_date: 参考日期
        
        Returns:
            (start_date, end_date) 元组
        """
        if not time_range.relative_type or not time_range.period_type:
            raise ValueError("相对时间必须提供 relative_type 和 period_type")
        
        # 创建或使用 DateCalculator
        if reference_date is None:
            reference_date = datetime.now() - timedelta(days=1)
        
        calculator = self.date_calculator or DateCalculator(anchor_date=reference_date)
        
        # 调用 DateCalculator 计算
        result = calculator.calculate_relative_date(
            relative_type=time_range.relative_type.value,
            period_type=time_range.period_type.value,
            range_n=time_range.range_n
        )
        
        return (result["start_date"], result["end_date"])
    
    def _validate_date_range(self, start_date: str, end_date: str) -> None:
        """
        验证日期范围的合理性
        
        检查：
        1. start_date <= end_date
        2. 日期格式是否符合 ISO 标准（YYYY-MM-DD）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
        
        Raises:
            ValueError: 如果验证失败
        """
        # 验证日期格式
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"日期格式不正确: {e}")
        
        # 验证日期顺序
        if start > end:
            raise ValueError(
                f"开始日期晚于结束日期: {start_date} > {end_date}"
            )
    
    def _adjust_boundaries(
        self,
        start_date: str,
        end_date: str,
        max_date: str
    ) -> Tuple[str, str]:
        """
        调整日期范围边界
        
        如果 end_date 超过数据源的 max_date，调整为 max_date。
        这确保查询不会请求超出数据范围的日期。
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            max_date: 数据源的最大日期
        
        Returns:
            调整后的 (start_date, end_date) 元组
        
        Examples:
            >>> parser._adjust_boundaries(
            ...     "2024-01-01", "2024-12-31", "2024-06-30"
            ... )
            ("2024-01-01", "2024-06-30")  # end_date 被调整
            
            >>> parser._adjust_boundaries(
            ...     "2024-01-01", "2024-03-31", "2024-12-31"
            ... )
            ("2024-01-01", "2024-03-31")  # 无需调整
        """
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            max_dt = datetime.strptime(max_date, "%Y-%m-%d")
            
            if end_dt > max_dt:
                # 调整 end_date
                adjusted_end = max_date
                logger.warning(
                    f"日期范围超出数据范围，调整 end_date: "
                    f"{end_date} → {adjusted_end} (max_date: {max_date})"
                )
                return (start_date, adjusted_end)
            
            # 无需调整
            return (start_date, end_date)
        
        except ValueError as e:
            logger.error(f"边界调整失败: {e}")
            # 如果解析失败，返回原始值
            return (start_date, end_date)
    
    def _generate_cache_key(
        self,
        time_range: TimeRange,
        reference_date: Optional[datetime],
        max_date: Optional[str] = None
    ) -> str:
        """
        生成缓存键
        
        Args:
            time_range: TimeRange 对象
            reference_date: 参考日期
            max_date: 最大日期（可选）
        
        Returns:
            缓存键字符串
        """
        ref_str = reference_date.date().isoformat() if reference_date else "None"
        max_str = max_date if max_date else "None"
        return f"{time_range.model_dump_json()}|{ref_str}|{max_str}"
    
    def get_performance_stats(self) -> dict:
        """
        获取性能统计信息
        
        Returns:
            包含性能指标的字典：
            - cache_size: 缓存大小
            - cache_hit_rate: 缓存命中率（需要跟踪）
        """
        return {
            "cache_size": len(self._cache),
            "cache_keys": list(self._cache.keys())[:5]  # 前5个缓存键
        }
    
    def clear_cache(self) -> None:
        """清空缓存"""
        cache_size = len(self._cache)
        self._cache.clear()
        logger.info(f"缓存已清空，清除了 {cache_size} 个条目")


# ============= 导出 =============

__all__ = [
    "DateParser",
]
