# STRING 类型日期字段的完整处理方案

## 概述

本文档详细说明了如何处理 STRING 类型的日期字段，包括所有可能的字段粒度和问题粒度组合，以及对应的 VizQL 筛选策略。

## 核心原则

当处理 STRING 类型的日期字段时，根据**字段粒度**和**问题粒度**的关系选择不同的筛选策略：

1. **字段粒度 == 问题粒度**：精确匹配，使用 `SetFilter`
2. **字段粒度 > 问题粒度**（字段更细）：展开问题范围到字段粒度，选择合适的筛选器
3. **字段粒度 < 问题粒度**（字段更粗）：❌ 无法实现（数据不足）

## 三种筛选策略

### 1. MatchFilter（模式匹配）
- **适用场景**：格式支持前缀匹配 + 问题粒度=年
- **优点**：简洁、高效
- **示例**：`startsWith="2024-"` 匹配所有2024年的数据

### 2. SetFilter（枚举值）
- **适用场景**：值的数量较少（≤31个）
- **优点**：精确、清晰
- **示例**：枚举Q1的3个月、1周的7天

### 3. DATEPARSE + QuantitativeDateFilter（日期范围）
- **适用场景**：完整日期格式 + 大范围（>100天）
- **优点**：处理大范围高效
- **示例**：筛选整年的日期数据

---

## 完整场景矩阵

### 场景 1：字段格式 YYYY（年份）

| 问题粒度 | 粒度关系 | 筛选策略 | VizQL 实现 | 说明 |
|---------|---------|---------|-----------|------|
| YEAR | 匹配 | SetFilter | `values=["2024"]` | 精确匹配年份 |
| QUARTER | 粗→细 | ❌ 无法实现 | - | 年份字段无季度信息 |
| MONTH | 粗→细 | ❌ 无法实现 | - | 年份字段无月份信息 |
| WEEK | 粗→细 | ❌ 无法实现 | - | 年份字段无周信息 |
| DAY | 粗→细 | ❌ 无法实现 | - | 年份字段无日期信息 |

**代码示例**：
```python
# 字段="2024"，问题="2024年的销售额"
SetFilter(
    field=FilterField(fieldCaption="Year"),
    filterType="SET",
    values=["2024"]
)
```

---

### 场景 2：字段格式 YYYY-QN（季度）

| 问题粒度 | 粒度关系 | 筛选策略 | VizQL 实现 | 说明 |
|---------|---------|---------|-----------|------|
| YEAR | 细→粗 | **MatchFilter** | `startsWith="2024-"` | 匹配所有2024年的季度 |
| QUARTER | 匹配 | SetFilter | `values=["2024-Q1"]` | 精确匹配季度 |
| MONTH | 粗→细 | ❌ 无法实现 | - | Q1包含1-3月，无法精确 |
| WEEK | 粗→细 | ❌ 无法实现 | - | 季度无法精确到周 |
| DAY | 粗→细 | ❌ 无法实现 | - | 季度无法精确到日 |

**代码示例**：
```python
# 场景1：字段="2024-Q1"，问题="2024年的销售额"
# 使用 MatchFilter 匹配所有 2024 年的季度
MatchFilter(
    field=FilterField(fieldCaption="Quarter"),
    filterType="MATCH",
    startsWith="2024-"
)

# 场景2：字段="2024-Q1"，问题="2024年Q1的销售额"
# 精确匹配
SetFilter(
    field=FilterField(fieldCaption="Quarter"),
    filterType="SET",
    values=["2024-Q1"]
)
```

---

### 场景 3：字段格式 YYYY-MM（年月）

| 问题粒度 | 粒度关系 | 筛选策略 | VizQL 实现 | 说明 |
|---------|---------|---------|-----------|------|
| YEAR | 细→粗 | **MatchFilter** | `startsWith="2024-"` | 匹配所有2024年的月份 |
| QUARTER | 细→粗 | **SetFilter** | `values=["2024-01", "2024-02", "2024-03"]` | 枚举Q1的3个月 |
| MONTH | 匹配 | SetFilter | `values=["2024-01"]` | 精确匹配月份 |
| WEEK | 粗→细 | ❌ 无法实现 | - | 月份无法精确到周 |
| DAY | 粗→细 | ❌ 无法实现 | - | 月份无法精确到日 |

**代码示例**：
```python
# 场景1：字段="2024-01"，问题="2024年的销售额"
# 使用 MatchFilter 匹配所有 2024 年的月份
MatchFilter(
    field=FilterField(fieldCaption="YearMonth"),
    filterType="MATCH",
    startsWith="2024-"
)

# 场景2：字段="2024-01"，问题="2024年Q1的销售额"
# 将2024-Q1展开为3个月
SetFilter(
    field=FilterField(fieldCaption="YearMonth"),
    filterType="SET",
    values=["2024-01", "2024-02", "2024-03"]
)

# 场景3：字段="2024-01"，问题="2024年1月的销售额"
# 精确匹配
SetFilter(
    field=FilterField(fieldCaption="YearMonth"),
    filterType="SET",
    values=["2024-01"]
)
```

---

### 场景 4：字段格式 YYYY-WNN（年周）

| 问题粒度 | 粒度关系 | 筛选策略 | VizQL 实现 | 说明 |
|---------|---------|---------|-----------|------|
| YEAR | 细→粗 | **MatchFilter** | `startsWith="2024-"` | 匹配所有2024年的周 |
| QUARTER | 细→粗 | **SetFilter** | 枚举Q1的所有周 | Q1约13周，可以枚举 |
| MONTH | 细→粗 | **SetFilter** | 枚举月份的所有周 | 1月约4-5周，可以枚举 |
| WEEK | 匹配 | SetFilter | `values=["2024-W01"]` | 精确匹配周 |
| DAY | 粗→细 | ❌ 无法实现 | - | 周无法精确到日 |

**代码示例**：
```python
# 场景1：字段="2024-W01"，问题="2024年的销售额"
# 使用 MatchFilter 匹配所有 2024 年的周
MatchFilter(
    field=FilterField(fieldCaption="YearWeek"),
    filterType="MATCH",
    startsWith="2024-"
)

# 场景2：字段="2024-W01"，问题="2024年Q1的销售额"
# 枚举 Q1 的所有周（约13周，需要计算）
SetFilter(
    field=FilterField(fieldCaption="YearWeek"),
    filterType="SET",
    values=["2024-W01", "2024-W02", "2024-W03", ..., "2024-W13"]
)

# 场景3：字段="2024-W01"，问题="2024年1月的销售额"
# 枚举 1月 的所有周（约4-5周，需要计算）
SetFilter(
    field=FilterField(fieldCaption="YearWeek"),
    filterType="SET",
    values=["2024-W01", "2024-W02", "2024-W03", "2024-W04"]
)

# 场景4：字段="2024-W01"，问题="第1周的销售额"
# 精确匹配
SetFilter(
    field=FilterField(fieldCaption="YearWeek"),
    filterType="SET",
    values=["2024-W01"]
)
```

---

### 场景 5：字段格式 YYYY-MM-DD（ISO日期）

| 问题粒度 | 粒度关系 | 筛选策略 | VizQL 实现 | 说明 |
|---------|---------|---------|-----------|------|
| YEAR | 细→粗 | **DATEPARSE + QuantitativeDateFilter** | 日期范围筛选 | 365天太多，用范围 |
| QUARTER | 细→粗 | **DATEPARSE + QuantitativeDateFilter** | 日期范围筛选 | 91天太多，用范围 |
| MONTH | 细→粗 | **MatchFilter** | `startsWith="2024-01-"` | 31天，用前缀匹配 |
| WEEK | 细→粗 | **SetFilter** | 枚举7天 | 7天，直接枚举 |
| DAY | 匹配 | SetFilter | `values=["2024-01-15"]` | 精确匹配 |

**代码示例**：
```python
# 场景1：字段="2024-01-15"，问题="2024年的销售额"
# 365天太多，使用 DATEPARSE + QuantitativeDateFilter
QuantitativeDateFilter(
    field=FilterField(calculation='DATEPARSE("yyyy-MM-dd", [Date])'),
    filterType="QUANTITATIVE_DATE",
    quantitativeFilterType="RANGE",
    minDate="2024-01-01",
    maxDate="2024-12-31"
)

# 场景2：字段="2024-01-15"，问题="2024年Q1的销售额"
# 91天太多，使用 DATEPARSE + QuantitativeDateFilter
QuantitativeDateFilter(
    field=FilterField(calculation='DATEPARSE("yyyy-MM-dd", [Date])'),
    filterType="QUANTITATIVE_DATE",
    quantitativeFilterType="RANGE",
    minDate="2024-01-01",
    maxDate="2024-03-31"
)

# 场景3：字段="2024-01-15"，问题="2024年1月的销售额"
# 31天，使用 MatchFilter（推荐）
MatchFilter(
    field=FilterField(fieldCaption="Date"),
    filterType="MATCH",
    startsWith="2024-01-"
)

# 场景4：字段="2024-01-15"，问题="2024年第1周的销售额"
# 7天，直接枚举
SetFilter(
    field=FilterField(fieldCaption="Date"),
    filterType="SET",
    values=["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04",
            "2024-01-05", "2024-01-06", "2024-01-07"]
)

# 场景5：字段="2024-01-15"，问题="1月15日的销售额"
# 精确匹配
SetFilter(
    field=FilterField(fieldCaption="Date"),
    filterType="SET",
    values=["2024-01-15"]
)
```

---

### 场景 6：字段格式 MM/DD/YYYY（美国日期）

| 问题粒度 | 粒度关系 | 筛选策略 | VizQL 实现 | 说明 |
|---------|---------|---------|-----------|------|
| YEAR | 细→粗 | **DATEPARSE + QuantitativeDateFilter** | 日期范围筛选 | 365天太多，用范围 |
| QUARTER | 细→粗 | **DATEPARSE + QuantitativeDateFilter** | 日期范围筛选 | 91天太多，用范围 |
| MONTH | 细→粗 | **SetFilter** | 枚举月份的所有日期 | 31天，枚举（无法用前缀） |
| WEEK | 细→粗 | **SetFilter** | 枚举7天 | 7天，直接枚举 |
| DAY | 匹配 | SetFilter | `values=["01/15/2024"]` | 精确匹配 |

**注意**：MM/DD/YYYY 格式无法使用 `startsWith` 匹配年份或月份（年份在最后）。

**代码示例**：
```python
# 场景1：字段="01/15/2024"，问题="2024年的销售额"
# 365天太多，使用 DATEPARSE + QuantitativeDateFilter
QuantitativeDateFilter(
    field=FilterField(calculation='DATEPARSE("MM/dd/yyyy", [Date])'),
    filterType="QUANTITATIVE_DATE",
    quantitativeFilterType="RANGE",
    minDate="2024-01-01",
    maxDate="2024-12-31"
)

# 场景2：字段="01/15/2024"，问题="2024年1月的销售额"
# 31天，枚举（无法使用前缀匹配）
SetFilter(
    field=FilterField(fieldCaption="Date"),
    filterType="SET",
    values=["01/01/2024", "01/02/2024", "01/03/2024", ..., "01/31/2024"]
)

# 场景3：字段="01/15/2024"，问题="1月15日的销售额"
# 精确匹配
SetFilter(
    field=FilterField(fieldCaption="Date"),
    filterType="SET",
    values=["01/15/2024"]
)
```

---

### 场景 7：字段格式 MM/YYYY（月年）

| 问题粒度 | 粒度关系 | 筛选策略 | VizQL 实现 | 说明 |
|---------|---------|---------|-----------|------|
| YEAR | 细→粗 | **SetFilter** | 枚举年份的所有月份 | 12个月，枚举（无法用前缀） |
| QUARTER | 细→粗 | **SetFilter** | 枚举季度的所有月份 | 3个月，枚举 |
| MONTH | 匹配 | SetFilter | `values=["01/2024"]` | 精确匹配 |
| WEEK | 粗→细 | ❌ 无法实现 | - | 月份无法精确到周 |
| DAY | 粗→细 | ❌ 无法实现 | - | 月份无法精确到日 |

**代码示例**：
```python
# 场景1：字段="01/2024"，问题="2024年的销售额"
# 12个月，枚举（无法使用前缀匹配）
SetFilter(
    field=FilterField(fieldCaption="MonthYear"),
    filterType="SET",
    values=["01/2024", "02/2024", "03/2024", ..., "12/2024"]
)

# 场景2：字段="01/2024"，问题="2024年Q1的销售额"
# 3个月，枚举
SetFilter(
    field=FilterField(fieldCaption="MonthYear"),
    filterType="SET",
    values=["01/2024", "02/2024", "03/2024"]
)
```

---

## 决策树

```
输入：字段格式、字段粒度、问题粒度、时间范围

1. 比较粒度关系
   ├─ 字段粒度 == 问题粒度
   │  └─ 使用 SetFilter 精确匹配
   │
   ├─ 字段粒度 < 问题粒度（字段更粗）
   │  └─ ❌ 返回 None（无法实现）
   │
   └─ 字段粒度 > 问题粒度（字段更细）
      └─ 2. 检查字段格式是否支持前缀匹配
         ├─ 支持前缀匹配（YYYY-MM, YYYY-QN, YYYY-WNN, YYYY-MM-DD）
         │  ├─ 问题粒度 == YEAR
         │  │  └─ 使用 MatchFilter (startsWith="YYYY-")
         │  │
         │  ├─ 问题粒度 == QUARTER
         │  │  └─ 使用 SetFilter 枚举（3-13个值）
         │  │
         │  ├─ 问题粒度 == MONTH
         │  │  ├─ 字段格式 == YYYY-MM-DD
         │  │  │  └─ 使用 MatchFilter (startsWith="YYYY-MM-")
         │  │  └─ 其他
         │  │     └─ 使用 SetFilter 枚举（4-31个值）
         │  │
         │  └─ 问题粒度 == WEEK
         │     └─ 使用 SetFilter 枚举（7个值）
         │
         └─ 不支持前缀匹配（MM/DD/YYYY, DD/MM/YYYY, MM/YYYY）
            ├─ 范围 > 100天
            │  └─ 使用 DATEPARSE + QuantitativeDateFilter
            │
            └─ 范围 ≤ 100天
               └─ 使用 SetFilter 枚举
```

---

## 实现要点

### 1. 格式是否支持前缀匹配

```python
def supports_prefix_match(format_type: DateFormatType) -> bool:
    """
    判断日期格式是否支持前缀匹配
    
    支持前缀匹配的格式：年份在前面
    - YYYY-MM
    - YYYY-QN
    - YYYY-WNN
    - YYYY-MM-DD
    
    不支持前缀匹配的格式：年份在后面或中间
    - MM/DD/YYYY
    - DD/MM/YYYY
    - MM/YYYY
    """
    prefix_match_formats = [
        DateFormatType.YEAR_MONTH,
        DateFormatType.QUARTER,
        DateFormatType.YEAR_WEEK,
        DateFormatType.ISO_DATE,
    ]
    return format_type in prefix_match_formats
```

### 2. 时间范围展开函数

```python
def expand_time_range_to_values(
    start_date: str,
    end_date: str,
    field_granularity: TimeGranularity,
    field_format: DateFormatType
) -> List[str]:
    """
    将时间范围展开为字段格式的值列表
    
    Args:
        start_date: 开始日期（ISO格式 YYYY-MM-DD）
        end_date: 结束日期（ISO格式 YYYY-MM-DD）
        field_granularity: 字段的时间粒度
        field_format: 字段的日期格式
    
    Returns:
        字段格式的值列表
    
    Examples:
        # 2024年 → 12个月（YYYY-MM格式）
        expand_time_range_to_values("2024-01-01", "2024-12-31", 
                                   TimeGranularity.MONTH, DateFormatType.YEAR_MONTH)
        # 返回: ["2024-01", "2024-02", ..., "2024-12"]
        
        # 2024-Q1 → 3个月（YYYY-MM格式）
        expand_time_range_to_values("2024-01-01", "2024-03-31",
                                   TimeGranularity.MONTH, DateFormatType.YEAR_MONTH)
        # 返回: ["2024-01", "2024-02", "2024-03"]
        
        # 2024年1月 → 31天（YYYY-MM-DD格式）
        expand_time_range_to_values("2024-01-01", "2024-01-31",
                                   TimeGranularity.DAY, DateFormatType.ISO_DATE)
        # 返回: ["2024-01-01", "2024-01-02", ..., "2024-01-31"]
    """
    from datetime import datetime, timedelta
    from dateutil.relativedelta import relativedelta
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    values = []
    
    if field_granularity == TimeGranularity.YEAR:
        # 按年展开
        current = start_dt
        while current <= end_dt:
            if field_format == DateFormatType.YEAR_ONLY:
                values.append(current.strftime("%Y"))
            current = current.replace(year=current.year + 1, month=1, day=1)
    
    elif field_granularity == TimeGranularity.QUARTER:
        # 按季度展开
        current = start_dt.replace(day=1)
        while current <= end_dt:
            quarter = (current.month - 1) // 3 + 1
            if field_format == DateFormatType.QUARTER:
                values.append(f"{current.year}-Q{quarter}")
            current += relativedelta(months=3)
    
    elif field_granularity == TimeGranularity.MONTH:
        # 按月展开
        current = start_dt.replace(day=1)
        while current <= end_dt:
            if field_format == DateFormatType.YEAR_MONTH:
                values.append(current.strftime("%Y-%m"))
            elif field_format == DateFormatType.MONTH_YEAR:
                values.append(current.strftime("%m/%Y"))
            current += relativedelta(months=1)
    
    elif field_granularity == TimeGranularity.WEEK:
        # 按周展开
        current = start_dt
        while current <= end_dt:
            iso_year, iso_week, _ = current.isocalendar()
            if field_format == DateFormatType.YEAR_WEEK:
                values.append(f"{iso_year}-W{iso_week:02d}")
            current += timedelta(weeks=1)
    
    elif field_granularity == TimeGranularity.DAY:
        # 按天展开
        current = start_dt
        while current <= end_dt:
            if field_format == DateFormatType.ISO_DATE:
                values.append(current.strftime("%Y-%m-%d"))
            elif field_format == DateFormatType.US_DATE:
                values.append(current.strftime("%m/%d/%Y"))
            elif field_format == DateFormatType.EU_DATE:
                values.append(current.strftime("%d/%m/%Y"))
            current += timedelta(days=1)
    
    return values
```

### 3. 主要逻辑流程

```python
def build_string_date_filter(
    field_name: str,
    field_format: DateFormatType,
    field_granularity: TimeGranularity,
    question_granularity: TimeGranularity,
    start_date: str,
    end_date: str
) -> Optional[VizQLFilter]:
    """
    为STRING类型日期字段构建筛选器
    
    Args:
        field_name: 字段名称
        field_format: 字段的日期格式
        field_granularity: 字段的时间粒度
        question_granularity: 问题的时间粒度
        start_date: 开始日期（ISO格式 YYYY-MM-DD）
        end_date: 结束日期（ISO格式 YYYY-MM-DD）
    
    Returns:
        VizQLFilter对象，如果无法处理则返回None
    """
    from datetime import datetime
    
    # 1. 比较粒度
    if field_granularity == question_granularity:
        # 精确匹配
        values = expand_time_range_to_values(
            start_date, end_date, field_granularity, field_format
        )
        return SetFilter(
            field=FilterField(fieldCaption=field_name),
            filterType="SET",
            values=values
        )
    
    elif field_granularity < question_granularity:
        # 字段更粗，无法实现
        logger.warning(
            f"字段粒度 {field_granularity} < 问题粒度 {question_granularity}，无法实现"
        )
        return None
    
    else:  # field_granularity > question_granularity
        # 字段更细，需要展开
        
        # 2. 检查是否支持前缀匹配
        if supports_prefix_match(field_format):
            if question_granularity == TimeGranularity.YEAR:
                # 使用 MatchFilter
                year = start_date[:4]
                return MatchFilter(
                    field=FilterField(fieldCaption=field_name),
                    filterType="MATCH",
                    startsWith=f"{year}-"
                )
            elif question_granularity == TimeGranularity.MONTH and \
                 field_granularity == TimeGranularity.DAY and \
                 field_format == DateFormatType.ISO_DATE:
                # YYYY-MM-DD 格式可以用前缀匹配月份
                year_month = start_date[:7]  # "2024-01"
                return MatchFilter(
                    field=FilterField(fieldCaption=field_name),
                    filterType="MATCH",
                    startsWith=f"{year_month}-"
                )
            else:
                # 使用 SetFilter 枚举
                values = expand_time_range_to_values(
                    start_date, end_date, field_granularity, field_format
                )
                return SetFilter(
                    field=FilterField(fieldCaption=field_name),
                    filterType="SET",
                    values=values
                )
        else:
            # 不支持前缀匹配
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            days_count = (end_dt - start_dt).days + 1
            
            if days_count > 100:
                # 使用 DATEPARSE + QuantitativeDateFilter
                # 需要根据 field_format 确定 DATEPARSE 的格式字符串
                dateparse_format = get_dateparse_format(field_format)
                return QuantitativeDateFilter(
                    field=FilterField(
                        calculation=f'DATEPARSE("{dateparse_format}", [{field_name}])'
                    ),
                    filterType="QUANTITATIVE_DATE",
                    quantitativeFilterType="RANGE",
                    minDate=start_date,
                    maxDate=end_date
                )
            else:
                # 使用 SetFilter 枚举
                values = expand_time_range_to_values(
                    start_date, end_date, field_granularity, field_format
                )
                return SetFilter(
                    field=FilterField(fieldCaption=field_name),
                    filterType="SET",
                    values=values
                )


def get_dateparse_format(format_type: DateFormatType) -> str:
    """获取 DATEPARSE 函数的格式字符串"""
    format_map = {
        DateFormatType.ISO_DATE: "yyyy-MM-dd",
        DateFormatType.US_DATE: "MM/dd/yyyy",
        DateFormatType.EU_DATE: "dd/MM/yyyy",
        DateFormatType.YEAR_MONTH: "yyyy-MM",
        DateFormatType.MONTH_YEAR: "MM/yyyy",
    }
    return format_map.get(format_type, "yyyy-MM-dd")
```

---

## 总结

本文档提供了处理 STRING 类型日期字段的完整方案，涵盖了所有常见的日期格式和粒度组合。实现时需要注意：

1. **优先使用 MatchFilter**：当格式支持前缀匹配且问题粒度为年时
2. **适度使用 SetFilter**：当需要枚举的值数量较少时（≤31个）
3. **大范围使用 DATEPARSE**：当需要筛选的日期范围超过100天时

通过这三种策略的组合，可以高效地处理各种 STRING 类型日期字段的筛选需求。
