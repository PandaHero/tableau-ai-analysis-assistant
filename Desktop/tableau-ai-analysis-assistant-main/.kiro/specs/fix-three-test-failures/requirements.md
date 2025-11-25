# 需求文档

## 简介

本规范解决Tableau Assistant查询流水线中的测试失败问题。测试结果显示15个测试用例中有3个执行失败，6个验证未通过。主要问题包括：

1. **日期处理问题**：TimeRange数据模型的relative_type字段描述不清晰，导致LLM无法正确区分LAST和LASTN
2. **计数查询理解错误**：Understanding Agent无法正确识别"每个X有多少个Y"模式中的分组维度和被计数维度
3. **字段映射错误**：Task Planner Agent因元数据呈现方式问题导致字段映射错误
4. **日期计算公式错误**：Query Builder生成的日期计算公式不符合Tableau VizQL API语法
5. **排序优先级冲突**：Query Builder为多个字段分配了相同的sortPriority值

## 术语表

- **System（系统）**: Tableau Assistant查询处理流水线
- **Understanding Agent（理解Agent）**: 基于LLM的自然语言问题解析Agent
- **Understanding Prompt Template（理解提示词模板）**: 指导LLM如何理解问题的结构化提示词
- **Task Planner Agent（任务规划Agent）**: 基于LLM的业务术语到技术字段映射Agent
- **Task Planner Prompt Template（任务规划提示词模板）**: 指导LLM如何映射字段的结构化提示词
- **Query Builder（查询构建器）**: 将任务规划结果转换为Tableau VizQL API查询的组件
- **Metadata（元数据）**: 数据源的字段信息，包括字段名、类型、样本值、维度层级等
- **FieldMetadata（字段元数据）**: 单个字段的元数据，包括name、dataType、sample_values、valid_max_date等
- **valid_max_date**: 维度推断时为时间类别字段获取的最大日期值（已与当前日期-1比较取最小值）
- **sample_values**: 字段的样本值列表，用于识别数据格式和内容
- **dimension_aggregations**: SubQuestion中的字段，标记哪些维度需要聚合（如COUNTD）
- **mentioned_dimensions**: SubQuestion中的字段，标记哪些维度用于分组
- **sortPriority**: VizQL API中字段的排序优先级，数值越小优先级越高，必须唯一
- **DATEPARSE**: Tableau函数，将字符串转换为日期类型
- **TRUNC_MONTH**: Tableau函数，将日期截断到月份级别

## 需求

### 需求1：TimeRange数据模型改进字段description

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

根本原因：TimeRange数据模型（question.py）中RelativeType枚举和相关字段的description未清楚说明每个值的含义，导致LLM无法根据用户问题的语义选择正确的值。

**正确的语义输出：**
- "上个月" → `{type: "relative", relative_type: "LAST", period_type: "MONTHS"}` （完整的上一个月，无range_n）
- "最近一个月" → `{type: "relative", relative_type: "LASTN", period_type: "MONTHS", range_n: 1}` （从今天往前推1个月）

**设计原则：**
- 数据模型的description应该清晰定义每个值的含义（使用英文）
- 数据模型中的示例应简洁，控制长度
- 提示模板使用英文，不包含具体示例
- 所有规则和描述必须是通用的，不针对特定场景
- LLM会根据值的含义自然地选择正确的值

#### 验收标准

1. WHEN RelativeType枚举定义LAST时，THE System SHALL在枚举值注释中使用英文说明：Complete previous period
2. WHEN RelativeType枚举定义LASTN时，THE System SHALL在枚举值注释中使用英文说明：Rolling N periods from today
3. WHEN RelativeType枚举定义CURRENT时，THE System SHALL在枚举值注释中使用英文说明：Current period to date
4. WHEN TimeRange.relative_type字段定义时，THE description SHALL使用英文说明每个RelativeType值的含义（通用描述，不针对特定场景）
5. WHEN TimeRange.range_n字段定义时，THE description SHALL使用英文说明：Required for LASTN/NEXTN, represents the number of periods
6. WHEN LLM处理任何相对时间表达时，THE System SHALL根据RelativeType的通用含义自然选择正确的值

### 需求2：QuerySubQuestion数据模型改进日期和计数查询说明

**用户故事：** 作为用户，我想询问"每个省份有多少个门店？"，以便按省份分组统计不同门店数量。

**问题分析：**

**问题1 - 计数查询**：
```json
"dimension_aggregations": {"省份": "COUNTD"}  // 错误：应该是{"门店": "COUNTD"}
"mentioned_dimensions": ["省份"]  // 错误：应该包含["省份", "门店"]
```

**问题2 - 日期字段**：
- date_field_functions的值是字符串，不是枚举
- mentioned_date_fields和filter_date_field的description未清楚说明分组和筛选的区别
- 同一个日期字段可以既用于分组又用于筛选

根本原因：
1. QuerySubQuestion数据模型中，字段的description未清楚说明使用方式
2. date_field_functions应该使用枚举类型，而不是字符串
3. Understanding提示词模板未引导LLM分析使用场景

**设计原则：**
- 数据模型的description应该清晰说明字段的使用场景（使用英文，示例简洁）
- 提示模板应该引导LLM的分析流程（使用英文，不包含具体示例）
- 所有规则和描述必须是通用的
- LLM会根据字段description自然地正确填充

#### 验收标准

**日期字段相关**：
1. WHEN 定义DateFunction枚举时，THE System SHALL包含：YEAR, QUARTER, MONTH, WEEK, DAY（使用英文注释说明含义）
2. WHEN QuerySubQuestion.date_field_functions字段定义时，THE type SHALL为dict[str, DateFunction]（枚举类型）
3. WHEN date_field_functions的description定义时，THE System SHALL使用英文说明：Maps date fields to time granularity functions for GROUP BY
4. WHEN QuerySubQuestion.mentioned_date_fields字段定义时，THE description SHALL使用英文说明：Date fields used for time-based grouping (GROUP BY time periods)
5. WHEN QuerySubQuestion.filter_date_field字段定义时，THE description SHALL使用英文说明：Date field used for time range filtering (WHERE clause with time range)

**计数查询相关**：
6. WHEN QuerySubQuestion.mentioned_dimensions字段定义时，THE description SHALL使用英文说明：Include ALL dimensions (both grouping and counted)
7. WHEN QuerySubQuestion.dimension_aggregations字段定义时，THE description SHALL使用英文包含通用示例（控制长度），VALUES SHALL包含：'COUNTD', 'MAX', 'MIN'
8. WHEN dimension_aggregations的description说明使用规则时，THE System SHALL使用英文说明通用规则：Include dimension → Has SQL aggregation; Exclude dimension → For GROUP BY

**提示模板相关**：
9. WHEN Understanding Prompt的Step 2定义时，THE System SHALL使用英文添加计数模式分析引导（不包含具体示例）
10. WHEN Understanding Prompt的Step 4定义时，THE System SHALL使用英文添加日期字段使用场景分析引导（区分grouping和filtering）

### 需求3：Task Planner Agent改进元数据呈现方式

**用户故事：** 作为用户，我想询问"各省份各渠道有多少个产品？"，以便按省份和渠道分组统计不同产品数量。

**问题分析：**
从终端输出看：
```json
"省份" → "门店名称"  // 错误：应该是"pro_name"
"产品" → "pro_name"  // 错误：应该是"分类五级名称"
```

根本原因：Task Planner Agent在调用LLM时，传递给LLM的metadata格式不够结构化，未按category分组呈现，导致LLM难以找到正确的字段。

**设计原则：**
- Agent负责格式化元数据，按category分组呈现给LLM
- 提示模板引导LLM的映射流程（使用英文，通用规则,先匹配category，再匹配name）
- LLM根据结构化的元数据自然地找到正确字段

#### 验收标准

1. WHEN Task Planner Agent准备LLM输入时，THE System SHALL按category分组整理metadata（geographic、product、organizational、temporal等）
2. WHEN Agent格式化元数据字符串时，THE System SHALL按category分组展示字段
3. WHEN 展示每个字段时，THE System SHALL包含：name、category、level（如果有）、sample_values（前3个，如果有）
4. WHEN Task Planner Prompt的get_specific_domain_knowledge方法说明映射规则时，THE System SHALL使用英文说明通用规则：Match category first, then match name
5. WHEN 映射规则说明计数查询时，THE System SHALL使用英文说明通用规则：For COUNTD aggregation, prefer fine-grained fields (higher level value)
6. WHEN LLM映射任何业务术语时，THE System SHALL根据category和name的通用匹配规则找到正确字段
7. WHEN LLM映射任何用于计数的维度时，THE System SHALL根据细粒度优先的通用规则选择正确字段

### 需求4：Query Builder修复日期计算公式生成

**用户故事：** 作为用户，我想询问"最近一个月各省份的销售额"或"显示每月的销售额"，以便查看带日期筛选或日期维度的数据。

**问题分析：**
从终端输出看：
```
Status code: 400
errorCode: "400800"
message: "The formula for calculation is invalid."
```

查询内容：
```json
{
  "fieldCaption": "TRUNC_MONTH_日期",
  "calculation": "TRUNC_MONTH(DATEPARSE('yyyy-MM-dd', [日期]))"
}
```

根本原因：Query Builder生成的日期计算公式不符合Tableau VizQL API的语法要求。

#### 验收标准

1. WHEN Query Builder生成日期维度字段时，THE System SHALL使用正确的Tableau计算公式语法
2. WHEN 日期字段类型为STRING时，THE System SHALL先使用DATEPARSE转换为日期类型
3. WHEN 应用日期函数（如TRUNC_MONTH）时，THE System SHALL确保公式语法正确
4. WHEN 生成日期筛选时，THE System SHALL使用正确的日期范围计算公式
5. WHEN Query Builder构建查询时，THE System SHALL验证生成的计算公式不会导致400错误

### 需求5：Query Builder修复排序优先级冲突

**用户故事：** 作为用户，我想询问"哪个门店的利润最高？"，以便找到利润排名第一的门店。

**问题分析：**
从终端输出看：
```
Status code: 400
errorCode: "400803"
message: "Cannot have multiple Fields with the same sort priority value."
```

查询内容：
```json
{
  "fields": [
    {
      "fieldCaption": "门店名称",
      "sortDirection": "DESC",
      "sortPriority": 0
    },
    {
      "fieldCaption": "netplamt",
      "sortDirection": "DESC",
      "sortPriority": 0,
      "function": "SUM"
    }
  ]
}
```

根本原因：Query Builder为多个字段分配了相同的sortPriority值（都是0），违反了Tableau VizQL API的约束。

#### 验收标准

1. WHEN Query Builder生成排序字段时，THE System SHALL为每个字段分配唯一的sortPriority值
2. WHEN 有多个字段需要排序时，THE System SHALL按优先级顺序分配递增的sortPriority值（0, 1, 2...）
3. WHEN TopN查询需要排序时，THE System SHALL确保度量字段的sortPriority优先级最高（值为0）
4. WHEN 维度字段也需要排序时，THE System SHALL为维度字段分配更高的sortPriority值（如1, 2...）
5. WHEN Query Builder构建查询时，THE System SHALL验证不存在重复的sortPriority值
