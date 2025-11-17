# 需求文档

## 简介

本规范解决Tableau Assistant查询流水线中三个失败的测试用例。

## 术语表

- **System（系统）**: Tableau Assistant查询处理流水线
- **Understanding Agent（理解Agent）**: 基于LLM的自然语言问题解析Agent
- **Understanding Prompt Template（理解提示词模板）**: 指导LLM如何理解问题的结构化提示词
- **Task Planner Agent（任务规划Agent）**: 基于LLM的业务术语到技术字段映射Agent
- **Task Planner Prompt Template（任务规划提示词模板）**: 指导LLM如何映射字段的结构化提示词
- **Metadata（元数据）**: 数据源的字段信息，包括字段名、类型、样本值、维度层级等
- **FieldMetadata（字段元数据）**: 单个字段的元数据，包括name、dataType、sample_values、valid_max_date等
- **valid_max_date**: 维度推断时为时间类别字段获取的最大日期值（已与当前日期-1比较取最小值）
- **sample_values**: 字段的样本值列表，用于识别数据格式和内容
- **dimension_aggregations**: SubQuestion中的字段，标记哪些维度需要聚合（如COUNTD）
- **mentioned_dimensions**: SubQuestion中的字段，标记哪些维度用于分组

## 需求

### 需求1：TimeRange数据模型改进relative_type字段的description

**用户故事：** 作为用户，我想查询"2024年销售额"、"今年销售额"、"今年9月销售额"或"最近一个月销售额"，以便查看按不同日期语义筛选的数据。

**问题分析：**
从终端输出看：
```json
"time_range": {
  "type": "relative",
  "value": null,
  "relative_type": "LAST",  // 错误：应该是"LASTN"
  "period_type": "MONTHS",
  "range_n": 1  // 矛盾：LAST类型不应该有range_n
}
```

根本原因：TimeRange数据模型中relative_type字段的description未清楚说明LAST和LASTN的区别，导致LLM无法根据"从今天往前推一个月"这个场景选择正确的值。

**模板的职责**：判断场景
- "最近一个月" → 模板判断：这是相对时间，从今天往前推

**数据模型的职责**：提供选择
- 相对时间 + 从今天往前推 → 数据模型应该让LLM知道：用`relative_type="LASTN"`和`range_n=1`

**正确的语义输出：**
- "上个月" → `{type: "relative", relative_type: "LAST", period_type: "MONTHS"}` （完整的上一个月，无range_n）
- "最近一个月" → `{type: "relative", relative_type: "LASTN", period_type: "MONTHS", range_n: 1}` （从今天往前推1个月）

#### 验收标准

1. WHEN RelativeType枚举定义LAST时，THE description SHALL明确：完整的上一个周期（如"上个月"="上月1日到上月最后一日"）
2. WHEN RelativeType枚举定义LASTN时，THE description SHALL明确：从今天往前推N个周期（如"最近一个月"="今天往前推30天"）
3. WHEN TimeRange.range_n字段定义时，THE description SHALL明确：仅用于LASTN/NEXTN，表示N的值
4. WHEN LLM处理"最近一个月"时，THE System SHALL根据数据模型的description选择`{relative_type: "LASTN", range_n: 1}`
5. WHEN Understanding Agent准备输入数据时，THE System SHALL提供max_date作为上下文（格式：`Current date: YYYY-MM-DD`）
6. WHEN Query Builder使用DateCalculator时，THE System SHALL传递valid_max_date作为anchor_date参数

### 需求2：Understanding Prompt Template明确计数模式识别规则

**用户故事：** 作为用户，我想询问"每个省份有多少个门店？"，以便按省份分组统计不同门店数量。

**问题分析：**
从终端输出看：
```json
"dimension_aggregations": {"省份": "COUNTD"}  // 错误：应该是{"门店": "COUNTD"}
"mentioned_dimensions": ["省份"]  // 正确
```

根本原因：提示词模板未明确说明"每个X有多少个Y？"模式中，X是分组维度，Y是被计数维度。

#### 验收标准

1. WHEN Understanding Prompt Template呈现给LLM时，THE Template SHALL包含计数模式示例："每个X有多少个Y？" → X放入mentioned_dimensions，Y放入dimension_aggregations
2. WHEN Template说明dimension_aggregations字段时，THE Template SHALL明确：只有被计数的维度才放入dimension_aggregations，分组维度放入mentioned_dimensions
3. WHEN LLM处理"每个省份有多少个门店？"时，THE System SHALL输出dimension_aggregations={"门店": "COUNTD"}
4. WHEN LLM处理"每个省份有多少个门店？"时，THE System SHALL输出mentioned_dimensions=["省份"]
5. WHEN Understanding Agent返回结果时，THE System SHALL正确区分分组维度和被计数维度

### 需求3：Task Planner Prompt Template改进元数据呈现方式

**用户故事：** 作为用户，我想询问"各省份各渠道有多少个产品？"，以便按省份和渠道分组统计不同产品数量。

**问题分析：**
从终端输出看：
```json
"省份" → "门店名称"  // 错误：应该是"pro_name"
"产品" → "pro_name"  // 错误：应该是"分类五级名称"
```

根本原因：提示词模板未按category分组呈现元数据，LLM无法找到正确的字段。

#### 验收标准

1. WHEN Task Planner Agent准备输入数据时，THE System SHALL按category分组整理metadata
2. WHEN Task Planner Prompt Template呈现元数据时，THE Template SHALL按category分组展示字段（geographic、product、organizational、temporal等）
3. WHEN Template呈现每个字段时，THE Template SHALL包含：name、category、level、granularity、sample_values（前3个）
4. WHEN Template指导LLM映射时，THE Template SHALL说明：先匹配category，再匹配name，对于计数查询优先选择细粒度字段
5. WHEN LLM映射"省份"时，THE System SHALL在geographic类别中找到"pro_name"
6. WHEN LLM映射"产品"用于计数时，THE System SHALL在product类别中选择最细粒度的"分类五级名称"
