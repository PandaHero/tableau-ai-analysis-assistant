# 附录 A: Preprocess 时间解析规则

## 概述

`extract_time()` 函数使用纯规则（0 LLM）解析用户问题中的相对时间表达，输出标准化的 `TimeContext`。

## 支持的时间表达

### 1. 相对日期

| 表达 | 解析规则 | 示例输出 |
|------|----------|----------|
| 今天 | `current_date` | `[2024-01-15, 2024-01-15]` |
| 昨天 | `current_date - 1 day` | `[2024-01-14, 2024-01-14]` |
| 前天 | `current_date - 2 days` | `[2024-01-13, 2024-01-13]` |
| 明天 | `current_date + 1 day` | `[2024-01-16, 2024-01-16]` |

### 2. 相对周

| 表达 | 解析规则 | 示例输出 |
|------|----------|----------|
| 本周 | `week_start(current_date)` ~ `week_end(current_date)` | `[2024-01-15, 2024-01-21]` |
| 上周 | `week_start(current_date - 7 days)` ~ `week_end(...)` | `[2024-01-08, 2024-01-14]` |
| 上上周 | `week_start(current_date - 14 days)` ~ `week_end(...)` | `[2024-01-01, 2024-01-07]` |

### 3. 相对月

| 表达 | 解析规则 | 示例输出 |
|------|----------|----------|
| 本月 | `month_start(current_date)` ~ `month_end(current_date)` | `[2024-01-01, 2024-01-31]` |
| 上月/上个月 | `month_start(current_date - 1 month)` ~ `month_end(...)` | `[2023-12-01, 2023-12-31]` |
| 上上月 | `month_start(current_date - 2 months)` ~ `month_end(...)` | `[2023-11-01, 2023-11-30]` |

### 4. 相对季度

| 表达 | 解析规则 | 示例输出 |
|------|----------|----------|
| 本季度 | `quarter_start(current_date)` ~ `quarter_end(current_date)` | `[2024-01-01, 2024-03-31]` |
| 上季度 | `quarter_start(current_date - 1 quarter)` ~ `quarter_end(...)` | `[2023-10-01, 2023-12-31]` |

### 5. 相对年

| 表达 | 解析规则 | 示例输出 |
|------|----------|----------|
| 今年 | `year_start(current_date)` ~ `year_end(current_date)` | `[2024-01-01, 2024-12-31]` |
| 去年 | `year_start(current_date - 1 year)` ~ `year_end(...)` | `[2023-01-01, 2023-12-31]` |
| 前年 | `year_start(current_date - 2 years)` ~ `year_end(...)` | `[2022-01-01, 2022-12-31]` |

### 6. 近 N 天/周/月

| 表达 | 解析规则 | 示例输出 |
|------|----------|----------|
| 近7天/最近7天 | `current_date - 6 days` ~ `current_date` | `[2024-01-09, 2024-01-15]` |
| 近30天 | `current_date - 29 days` ~ `current_date` | `[2023-12-17, 2024-01-15]` |
| 近3个月 | `current_date - 3 months` ~ `current_date` | `[2023-10-15, 2024-01-15]` |
| 过去一年 | `current_date - 1 year` ~ `current_date` | `[2023-01-15, 2024-01-15]` |

### 7. 特定月份

| 表达 | 解析规则 | 示例输出 |
|------|----------|----------|
| 1月/一月 | 当年1月 | `[2024-01-01, 2024-01-31]` |
| 去年12月 | 去年12月 | `[2023-12-01, 2023-12-31]` |

## 正则表达式模式

```python
TIME_PATTERNS = [
    # 今天/昨天/前天
    (r"今天", lambda d: (d, d, "DAY")),
    (r"昨天", lambda d: (d - timedelta(days=1), d - timedelta(days=1), "DAY")),
    (r"前天", lambda d: (d - timedelta(days=2), d - timedelta(days=2), "DAY")),
    
    # 本周/上周
    (r"本周", lambda d: (week_start(d), week_end(d), "WEEK")),
    (r"上周", lambda d: (week_start(d - timedelta(weeks=1)), week_end(d - timedelta(weeks=1)), "WEEK")),
    
    # 本月/上月
    (r"本月", lambda d: (month_start(d), month_end(d), "MONTH")),
    (r"上个?月", lambda d: (month_start(prev_month(d)), month_end(prev_month(d)), "MONTH")),
    
    # 本季度/上季度
    (r"本季度?", lambda d: (quarter_start(d), quarter_end(d), "QUARTER")),
    (r"上季度?", lambda d: (quarter_start(prev_quarter(d)), quarter_end(prev_quarter(d)), "QUARTER")),
    
    # 今年/去年
    (r"今年", lambda d: (year_start(d), year_end(d), "YEAR")),
    (r"去年", lambda d: (year_start(prev_year(d)), year_end(prev_year(d)), "YEAR")),
    
    # 近N天/周/月
    (r"近(\d+)天", lambda d, n: (d - timedelta(days=int(n)-1), d, "DAY")),
    (r"最近(\d+)天", lambda d, n: (d - timedelta(days=int(n)-1), d, "DAY")),
    (r"近(\d+)个?月", lambda d, n: (d - relativedelta(months=int(n)), d, "MONTH")),
    (r"过去(\d+)年", lambda d, n: (d - relativedelta(years=int(n)), d, "YEAR")),
]
```

## Canonical Question 标准化

时间表达在 `build_canonical()` 中被替换为标准形式：

| 原始表达 | 标准形式 |
|----------|----------|
| 上月 | `time:last_month` |
| 近7天 | `time:last_7_days` |
| 今年 | `time:this_year` |
| 去年同期 | `time:yoy` |

这确保了相同语义的问题生成相同的 `canonical_question`，从而提高缓存命中率。

## 缓存失效策略

- `is_relative=True` 的时间上下文，缓存键包含 `current_date`
- 跨天自动失效：`hash(canonical_question + current_date)`
- 绝对时间（如"2024年1月"）不受跨天影响

## 边界情况处理

1. **无时间表达**：`time_context = None`
2. **多个时间表达**：取第一个匹配
3. **冲突时间表达**：如"上月今年"，取更具体的（上月）
4. **无法解析**：保留原文，`is_relative=False`

## 时区与周起始日配置

### 时区处理

```python
@dataclass
class TimeParserConfig:
    """时间解析配置"""
    timezone: str = "Asia/Shanghai"  # 默认时区
    week_start: int = 1  # 周起始日：1=周一，0=周日
    
def extract_time(
    question: str,
    current_date: date | None = None,
    config: TimeParserConfig | None = None,
) -> TimeContext | None:
    """
    解析时间表达
    
    注意：
    - current_date 应由调用方传入，确保一致性
    - 不使用 datetime.now()，避免时区问题
    """
    config = config or TimeParserConfig()
    if current_date is None:
        # 使用配置的时区获取当前日期
        tz = pytz.timezone(config.timezone)
        current_date = datetime.now(tz).date()
    ...
```

### 周起始日

| 配置 | 说明 | 示例（2024-01-15 周一） |
|------|------|------------------------|
| `week_start=1` | 周一为周起始 | 本周 = [01-15, 01-21] |
| `week_start=0` | 周日为周起始 | 本周 = [01-14, 01-20] |

## 边界示例

### 跨月边界

| 场景 | current_date | 表达 | 结果 |
|------|--------------|------|------|
| 月初问上月 | 2024-01-01 | "上月" | [2023-12-01, 2023-12-31] |
| 月末问本月 | 2024-01-31 | "本月" | [2024-01-01, 2024-01-31] |
| 2月问上月 | 2024-02-15 | "上月" | [2024-01-01, 2024-01-31] |

### 跨年边界

| 场景 | current_date | 表达 | 结果 |
|------|--------------|------|------|
| 年初问去年 | 2024-01-01 | "去年" | [2023-01-01, 2023-12-31] |
| 年初问今年 | 2024-01-01 | "今年" | [2024-01-01, 2024-12-31] |
| 年末问本季度 | 2024-12-31 | "本季度" | [2024-10-01, 2024-12-31] |

### "本月/今年" 的 end_date 语义

**重要**：`end_date` 始终是该时间段的最后一天，而非当前日期。

| 表达 | current_date | end_date | 说明 |
|------|--------------|----------|------|
| 本月 | 2024-01-15 | 2024-01-31 | 月末，非今天 |
| 今年 | 2024-01-15 | 2024-12-31 | 年末，非今天 |
| 本季度 | 2024-01-15 | 2024-03-31 | 季末，非今天 |

**原因**：
- 与 Tableau DateRangeFilter 语义一致
- 避免"本月销售额"只查到今天为止的数据
- 如需"截至今天"，用户应明确说"本月截至今天"

### 闰年处理

| 场景 | current_date | 表达 | 结果 |
|------|--------------|------|------|
| 闰年2月 | 2024-02-15 | "本月" | [2024-02-01, 2024-02-29] |
| 非闰年2月 | 2023-02-15 | "本月" | [2023-02-01, 2023-02-28] |
| 3月问上月（闰年） | 2024-03-15 | "上月" | [2024-02-01, 2024-02-29] |

## 与现有 DateRangeFilter 对齐

```python
# 现有 DateRangeFilter 定义
class DateRangeFilter(BaseModel):
    field_name: str
    start_date: date | None = None
    end_date: date | None = None
    
# TimeContext 到 DateRangeFilter 的转换
def time_context_to_filter(
    time_context: TimeContext,
    date_field: str,
) -> DateRangeFilter:
    """转换为 DateRangeFilter"""
    return DateRangeFilter(
        field_name=date_field,
        start_date=time_context.start_date,
        end_date=time_context.end_date,
    )
```

**语义对齐**：
- `start_date` 和 `end_date` 都是 **包含** 的（inclusive）
- 与 Tableau 的 `DATETRUNC` 和 `DATEADD` 行为一致
