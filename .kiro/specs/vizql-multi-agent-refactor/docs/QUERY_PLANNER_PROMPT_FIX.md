# 查询规划提示词修复

## 问题描述

查询规划Agent返回的JSON结构与Pydantic模型不匹配，导致验证失败：

```
26 validation errors for QueryPlanningResult
subtasks.0.fields
  Field required [type=missing]
subtasks.0.dims
  Extra inputs are not permitted [type=extra_forbidden]
subtasks.0.metrics
  Extra inputs are not permitted [type=extra_forbidden]
...
```

## 根本原因

提示词中的输出格式示例使用了**旧的字段结构**：
```json
{
  "dims": ["地区"],
  "metrics": [{"field": "销售额", "aggregation": "sum"}],
  "calculations": [],
  "time_dims": [],
  "filters": [{"type": "time", ...}]
}
```

但Pydantic模型期望的是**新的字段结构**：
```json
{
  "fields": [
    {"fieldCaption": "地区"},
    {"fieldCaption": "销售额", "function": "SUM"}
  ],
  "filters": [{"filterType": "DATE", ...}]
}
```

## 关键差异

### 1. 字段结构

**旧结构**（提示词中的错误示例）:
- 分散在多个字段：`dims`, `metrics`, `calculations`, `time_dims`
- 度量使用`aggregation`参数

**新结构**（Pydantic模型）:
- 统一在`fields`数组中
- 度量使用`function`参数
- 所有字段使用`fieldCaption`

### 2. 筛选器discriminator

**旧结构**:
- 使用`type`作为类型标识符
- 例如：`{"type": "time", ...}`

**新结构**:
- 使用`filterType`作为discriminator
- 例如：`{"filterType": "DATE", ...}`

## 解决方案

### 修改1: 更新输出格式示例

**之前**:
```json
{
  "subtasks": [{
    "dims": ["地区"],
    "metrics": [{"field": "销售额", "aggregation": "sum"}],
    "filters": [{"type": "time", ...}]
  }]
}
```

**之后**:
```json
{
  "subtasks": [{
    "fields": [
      {"fieldCaption": "地区"},
      {"fieldCaption": "销售额", "function": "SUM"}
    ],
    "filters": [{"filterType": "DATE", ...}]
  }]
}
```

### 修改2: 更新字段规格说明

添加了明确的字段类型说明：
- **维度字段**：只需`fieldCaption`
- **度量字段**：需要`fieldCaption`和`function`
- **时间维度**：可以添加`function`（YEAR/MONTH/DAY等）

### 修改3: 更新筛选器说明

添加了完整的筛选器类型表格：

| filterType | 说明 | 示例 |
|-----------|------|------|
| SET | 集合筛选 | `{"filterType": "SET", "field": {"fieldCaption": "地区"}, "values": ["华东"]}` |
| TOP | TopN筛选 | `{"filterType": "TOP", "field": {"fieldCaption": "产品"}, "howMany": 10, ...}` |
| MATCH | 文本匹配 | `{"filterType": "MATCH", "field": {"fieldCaption": "产品名称"}, ...}` |
| QUANTITATIVE_NUMERICAL | 数值范围 | `{"filterType": "QUANTITATIVE_NUMERICAL", ...}` |
| QUANTITATIVE_DATE | 日期范围 | `{"filterType": "QUANTITATIVE_DATE", ...}` |
| DATE | 相对日期 | `{"filterType": "DATE", "dateRangeType": "LASTN", ...}` |

## 修改的文件

- `tableau_assistant/prompts/query_planner.py`
  - 更新输出格式示例
  - 更新字段规格说明
  - 更新筛选器说明
  - 添加明确的注意事项

## 验证

运行测试验证修复：

```bash
python tableau_assistant/tests/manual/test_mvp_complete_flow.py
```

预期结果：
- ✅ 查询规划成功（不再报字段验证错误）
- ✅ LLM输出的JSON结构与Pydantic模型匹配
- ✅ 所有字段都在`fields`数组中
- ✅ 筛选器使用正确的`filterType`

## 最佳实践

在设计提示词时：

1. **保持一致性**：提示词中的示例必须与Pydantic模型完全匹配
2. **明确discriminator**：如果使用Union类型，明确指出discriminator字段
3. **提供完整示例**：包含所有必需字段的完整示例
4. **添加注意事项**：在关键位置添加"重要"提示
5. **定期验证**：修改模型后，同步更新提示词

## 相关文档

- [VizQL类型定义](../../src/models/vizql_types.py)
- [查询规划模型](../../src/models/query_plan.py)
- [with_structured_output修复](./WITH_STRUCTURED_OUTPUT_FIX.md)


## 补充修复（第二轮）

### 问题3: 日期范围筛选器字段错误

**错误**:
```json
{
  "filterType": "QUANTITATIVE_DATE",
  "field": {"fieldCaption": "日期"},
  "min": "2016-01-01",
  "max": "2016-12-31"
}
```

**正确**:
```json
{
  "filterType": "QUANTITATIVE_DATE",
  "field": {"fieldCaption": "日期"},
  "quantitativeFilterType": "RANGE",
  "minDate": "2016-01-01",
  "maxDate": "2016-12-31"
}
```

**关键点**:
- 必须包含`quantitativeFilterType`字段（RANGE/MIN/MAX等）
- 使用`minDate`和`maxDate`，而不是`min`和`max`

### 问题4: 计算字段结构错误

**错误**:
```json
{
  "fieldCaption": "同比增长率",
  "function": "([2016年销售额] - [2015年销售额]) / [2015年销售额]"
}
```

**正确**:
```json
{
  "fieldCaption": "同比增长率",
  "calculation": "([2016年销售额] - [2015年销售额]) / [2015年销售额]"
}
```

**关键点**:
- 计算字段使用`calculation`字段，而不是`function`
- `function`字段只用于度量字段的聚合函数（SUM/AVG等）

## 完整的字段类型总结

| 字段类型 | 必需字段 | 示例 |
|---------|---------|------|
| 维度字段 | `fieldCaption` | `{"fieldCaption": "地区"}` |
| 度量字段 | `fieldCaption`, `function` | `{"fieldCaption": "销售额", "function": "SUM"}` |
| 时间维度 | `fieldCaption`, `function` | `{"fieldCaption": "日期", "function": "YEAR"}` |
| 计算字段 | `fieldCaption`, `calculation` | `{"fieldCaption": "利润率", "calculation": "[利润] / [销售额]"}` |

## 完整的筛选器类型总结

| filterType | 必需字段 | 示例 |
|-----------|---------|------|
| SET | `field`, `values` | `{"filterType": "SET", "field": {"fieldCaption": "地区"}, "values": ["华东"]}` |
| TOP | `field`, `howMany`, `direction`, `fieldToMeasure` | `{"filterType": "TOP", "field": {"fieldCaption": "产品"}, "howMany": 10, "direction": "TOP", "fieldToMeasure": {"fieldCaption": "销售额", "function": "SUM"}}` |
| MATCH | `field`, `matchType`, `value` | `{"filterType": "MATCH", "field": {"fieldCaption": "产品名称"}, "matchType": "CONTAINS", "value": "椅子"}` |
| QUANTITATIVE_NUMERICAL | `field`, `quantitativeFilterType`, `min`/`max` | `{"filterType": "QUANTITATIVE_NUMERICAL", "field": {"fieldCaption": "销售额"}, "quantitativeFilterType": "RANGE", "min": 1000, "max": 5000}` |
| QUANTITATIVE_DATE | `field`, `quantitativeFilterType`, `minDate`/`maxDate` | `{"filterType": "QUANTITATIVE_DATE", "field": {"fieldCaption": "日期"}, "quantitativeFilterType": "RANGE", "minDate": "2016-01-01", "maxDate": "2016-12-31"}` |
| DATE | `field`, `dateRangeType`, `periodType`, `rangeN`(可选) | `{"filterType": "DATE", "field": {"fieldCaption": "日期"}, "dateRangeType": "LASTN", "periodType": "MONTHS", "rangeN": 3}` |

## 修改历史

1. **第一轮修复**: 统一字段结构（`fields`数组）和筛选器discriminator（`filterType`）
2. **第二轮修复**: 修正日期范围筛选器字段名和计算字段结构
