# STRING 日期字段筛选设计文档

## 问题分析

当日期字段是 STRING 类型时，需要根据**字段格式粒度**和**问题时间粒度**的关系来选择合适的筛选策略。

## 粒度关系矩阵

### 关系1：字段粒度 == 问题粒度（直接匹配）

| 字段格式 | 字段粒度 | 问题粒度 | 处理方式 | 示例 |
|---------|---------|---------|---------|------|
| YYYY | YEAR | YEAR | SetFilter | 字段="2024", 问题="2024年" |
| YYYY-MM | MONTH | MONTH | SetFilter | 字段="2024-01", 问题="2024年1月" |
| YYYY-QN | QUARTER | QUARTER | SetFilter | 字段="2024-Q1", 问题="2024年Q1" |
| YYYY-WNN | WEEK | WEEK | SetFilter | 字段="2024-W01", 问题="2024年第1周" |
| YYYY-MM-DD | DAY | DAY | SetFilter (小范围) | 字段="2024-01-15", 问题="2024年1月15日" |

**实现**：直接生成值列表，使用 SetFilter

### 关系2：字段粒度 > 问题粒度（字段更细，需要聚合）

| 字段格式 | 字段粒度 | 问题粒度 | 处理方式 | 示例 |
|---------|---------|---------|---------|------|
| YYYY-MM | MONTH | YEAR | 提取年份 | 字段="2024-01" → 提取"2024" |
| YYYY-MM-DD | DAY | YEAR | CalculationField: LEFT([field], 4) | 字段="2024-01-15" → "2024" |
| YYYY-MM-DD | DAY | QUARTER | CalculationField: 计算季度 | 字段="2024-01-15" → "2024-Q1" |
| YYYY-MM-DD | DAY | MONTH | CalculationField: LEFT([field], 7) | 字段="2024-01-15" → "2024-01" |
| YYYY-MM-DD | DAY | WEEK | CalculationField: DATEPART('week', DATEPARSE(...)) | 复杂 |

**实现**：
1. 创建 CalculationField 提取相应的时间部分
2. 对提取的值使用 SetFilter

### 关系3：字段粒度 < 问题粒度（字段更粗，无法实现）

| 字段格式 | 字段粒度 | 问题粒度 | 处理方式 | 示例 |
|---------|---------|---------|---------|------|
| YYYY | YEAR | MONTH | ❌ 无法实现 | 字段="2024" 无法知道具体月份 |
| YYYY | YEAR | DAY | ❌ 无法实现 | 字段="2024" 无法知道具体日期 |
| YYYY-MM | MONTH | DAY | ❌ 无法实现 | 字段="2024-01" 无法知道具体日期 |
| YYYY-QN | QUARTER | MONTH | ❌ 无法实现 | 字段="2024-Q1" 无法精确到月 |

**实现**：返回 None，记录警告日志

## 实现策略

### 策略1：直接匹配（字段粒度 == 问题粒度）

```python
# 生成值列表
values = generate_values_for_granularity(
    start_date, end_date, granularity
)

# 使用 SetFilter
return SetFilter(
    field=FilterField(fieldCaption=field_name),
    filterType="SET",
    values=values
)
```

### 策略2：提取聚合（字段粒度 > 问题粒度）

```python
# 创建 CalculationField 提取时间部分
calc_field = CalculationField(
    fieldCaption=f"_extracted_{field_name}",
    calculation=extract_formula  # 根据粒度生成公式
)

# 生成值列表
values = generate_values_for_granularity(
    start_date, end_date, question_granularity
)

# 使用 SetFilter（注意：需要在查询中添加 calc_field）
return SetFilter(
    field=FilterField(fieldCaption=f"_extracted_{field_name}"),
    filterType="SET",
    values=values
)
```

**问题**：当前方法只返回 Filter，不返回 Field。需要返回 `(CalculationField, Filter)` 元组。

### 策略3：无法实现（字段粒度 < 问题粒度）

```python
logger.warning(
    f"字段 {field_name} 的粒度({field_granularity})粗于问题粒度({question_granularity})，"
    f"无法生成筛选器"
)
return None
```

## 提取公式

### 从完整日期提取年份
```python
# 对于 YYYY-MM-DD 格式
"LEFT([field_name], 4)"

# 对于 MM/DD/YYYY 格式
"RIGHT([field_name], 4)"
```

### 从完整日期提取年月
```python
# 对于 YYYY-MM-DD 格式
"LEFT([field_name], 7)"

# 对于 MM/DD/YYYY 格式 → 需要转换
"DATEPART('year', DATEPARSE('MM/dd/yyyy', [field_name])) + '-' + "
"RIGHT('0' + STR(DATEPART('month', DATEPARSE('MM/dd/yyyy', [field_name]))), 2)"
```

### 从完整日期提取季度
```python
# 需要先解析日期
"STR(DATEPART('year', DATEPARSE('yyyy-MM-dd', [field_name]))) + '-Q' + "
"STR(DATEPART('quarter', DATEPARSE('yyyy-MM-dd', [field_name])))"
```

## 方法签名变更

### 当前签名
```python
def _build_date_filter_for_string_field(
    self,
    field_name: str,
    start_date: str,
    end_date: str
) -> Optional[VizQLFilter]:
```

### 新签名（选项1：只返回 Filter）
```python
def _build_date_filter_for_string_field(
    self,
    field_name: str,
    start_date: str,
    end_date: str,
    question_granularity: TimeGranularity
) -> Optional[VizQLFilter]:
```

### 新签名（选项2：返回 Field + Filter）
```python
def _build_date_filter_for_string_field(
    self,
    field_name: str,
    start_date: str,
    end_date: str,
    question_granularity: TimeGranularity
) -> Optional[Tuple[Optional[CalculationField], VizQLFilter]]:
```

**推荐**：选项2，因为需要返回 CalculationField

## 下一步

1. 确认设计方向是否正确
2. 实现新的方法逻辑
3. 更新所有调用方
4. 更新测试用例
