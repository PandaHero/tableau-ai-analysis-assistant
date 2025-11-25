# 需求文档

## 简介

本功能旨在修复 Tableau Assistant 系统中的一个核心逻辑错误：维度字段（用于分组）被错误地分配了聚合函数。系统当前会为维度字段（如"pro_name"（省份）、"门店编码"）分配聚合函数（如 COUNTD），这导致 Tableau 查询失败。维度字段应该直接用于 GROUP BY 操作，不需要聚合函数，只有度量字段才需要应用聚合函数。

### 设计原则

本修复方案遵循主流LLM上下文最佳实践：

1. **Schema优先设计**（Pydantic AI模式）
   - 数据模型通过Field description说明字段用途、可用值和使用方法
   - 类型注解和验证器约束输出格式

2. **Prompt提供判断逻辑**（Anthropic/OpenAI最佳实践）
   - 使用SQL语义进行角色判断
   - 提供清晰的判断标准
   - 不包含字段填充规则

3. **职责分离**
   - 数据模型：说明"是什么"、"有哪些值"、"怎么用这些值"
   - Prompt：说明"如何判断"（仅判断逻辑）
   - get_role()：定义Agent的SQL角色

## 术语表

- **问题理解Agent (Understanding Agent)**: 负责解析用户问题并识别维度、度量及其聚合意图的组件（输出包含 dimension_aggregations 和 measure_aggregations 的 QuerySubQuestion）
- **任务规划Agent (Task Planner Agent)**: 将理解结果转换为可执行查询计划的组件（输出包含 DimensionIntent 和 MeasureIntent 的 QuerySubTask）
- **查询构建器 (Query Builder)**: 将 Intent 模型（DimensionIntent、MeasureIntent）转换为 VizQL 查询结构的组件
- **维度字段 (Dimension Field)**: 用于数据分组的分类字段（如省份、门店、渠道）- 在 VizQL 查询中不应有聚合函数
- **度量字段 (Measure Field)**: 用于计算的数值字段（如销售额、利润）- 在 VizQL 查询中必须有聚合函数（SUM、AVG 等）
- **VizQL 查询**: 发送到 Tableau VizQL Data Service API 的 JSON 查询结构
- **聚合函数 (Aggregation Function)**: 应用于字段的数学运算，如 SUM、AVG、COUNT、COUNTD
- **dimension_aggregations**: QuerySubQuestion 中的字典，将维度字段名映射到聚合函数（如 {"pro_name": "COUNTD"}）
- **measure_aggregations**: QuerySubQuestion 中的字典，将度量字段名映射到聚合函数（如 {"收入": "SUM"}）
- **DimensionIntent**: QuerySubTask 中的意图模型，表示维度字段，包含 business_term、technical_field 和可选的 aggregation
- **MeasureIntent**: QuerySubTask 中的意图模型，表示度量字段，包含 business_term、technical_field 和必需的 aggregation

## 需求

### 需求 1: 问题理解Agent中的维度字段正确处理

**用户故事：** 作为数据分析师，我希望维度字段在理解阶段被正确识别且不带聚合函数，以便下游组件能够正确处理它们。

#### 验收标准

1. 当问题理解Agent识别到用户问题中提到的维度字段（如"省份"、"门店"）时，问题理解Agent应将其添加到 mentioned_dimensions 列表中
2. 当问题理解Agent处理 mentioned_dimensions 中的维度字段时，对于用于分组的维度，问题理解Agent不应在 dimension_aggregations 字典中为其设置聚合函数
3. 当用户询问"计数类"问题（如"每个地区有多少个产品"）时，问题理解Agent应将分组维度（"地区"）和被计数实体（"产品"）都添加到 mentioned_dimensions 中
4. 在检测到"计数类"模式的情况下，问题理解Agent应仅为被计数实体设置 dimension_aggregations（如 {"产品": "COUNTD"}），而不为分组维度设置
5. 问题理解Agent应在 dimension_aggregations 字典中清晰区分分组维度（无聚合）和被计数维度（COUNTD聚合）

**示例说明：**
```python
# ✅ 正确示例 1：简单分组查询
问题: "各省份的销售额是多少？"
输出: {
    "mentioned_dimensions": ["省份"],
    "dimension_aggregations": {},  # 分组维度不需要聚合
    "mentioned_measures": ["销售额"],
    "measure_aggregations": {"销售额": "SUM"}
}

# ✅ 正确示例 2：计数类查询
问题: "每个省份有多少个门店？"
输出: {
    "mentioned_dimensions": ["省份", "门店"],
    "dimension_aggregations": {"门店": "COUNTD"},  # 只为被计数实体设置聚合
    "mentioned_measures": [],
    "measure_aggregations": {}
}

# ❌ 错误示例：当前系统的错误输出
问题: "各省份的销售额是多少？"
当前错误输出: {
    "mentioned_dimensions": ["省份"],
    "dimension_aggregations": {"省份": "COUNTD"},  # 错误！分组维度不应有聚合
    "mentioned_measures": ["销售额"],
    "measure_aggregations": {"销售额": "SUM"}
}
```

### 需求 2: 任务规划Agent中的正确字段处理

**用户故事：** 作为数据分析师，我希望任务规划Agent能够正确生成维度和度量的Intent模型，以便查询构建器能够生成正确的VizQL查询。

#### 验收标准

1. 当任务规划Agent从问题理解结果中接收到维度字段时，如果该维度在 dimension_aggregations 中没有聚合函数，则任务规划Agent应生成不带 aggregation 属性的 DimensionIntent
2. 当任务规划Agent从问题理解结果中接收到维度字段时，如果该维度在 dimension_aggregations 中有聚合函数（如COUNTD），则任务规划Agent应生成带有相应 aggregation 属性的 DimensionIntent
3. 当任务规划Agent从问题理解结果中接收到度量字段时，任务规划Agent应确保所有度量字段在 MeasureIntent 中都指定了聚合函数
4. 在任务规划Agent生成的 QuerySubTask 中，dimension_intents 列表应包含所有维度字段的映射，measure_intents 列表应包含所有度量字段的映射

**示例说明：**
```python
# ✅ 正确示例：分组维度的Intent
问题理解输出: {
    "mentioned_dimensions": ["省份"],
    "dimension_aggregations": {}  # 无聚合
}
任务规划输出: {
    "dimension_intents": [{
        "business_term": "省份",
        "technical_field": "pro_name",
        "field_data_type": "STRING",
        "aggregation": None  # 正确：分组维度无聚合
    }]
}

# ✅ 正确示例：被计数维度的Intent
问题理解输出: {
    "mentioned_dimensions": ["省份", "门店"],
    "dimension_aggregations": {"门店": "COUNTD"}
}
任务规划输出: {
    "dimension_intents": [
        {
            "business_term": "省份",
            "technical_field": "pro_name",
            "field_data_type": "STRING",
            "aggregation": None  # 分组维度无聚合
        },
        {
            "business_term": "门店",
            "technical_field": "门店编码",
            "field_data_type": "STRING",
            "aggregation": "COUNTD"  # 被计数维度有聚合
        }
    ]
}
```

### 需求 3: 查询构建器中的正确VizQL生成

**用户故事：** 作为系统开发者，我希望查询构建器能够根据Intent模型生成符合Tableau VizQL API规范的查询，以便查询能够成功执行。

#### 验收标准

1. 当查询构建器处理不带 aggregation 属性的 DimensionIntent 时，查询构建器应生成不包含 "function" 属性的 VizQL 字段
2. 当查询构建器处理带有 aggregation 属性的 DimensionIntent 时，查询构建器应生成包含相应 "function" 属性的 VizQL 字段
3. 当查询构建器处理 MeasureIntent 时，查询构建器应始终生成包含 "function" 属性的 VizQL 字段
4. 查询构建器生成的 VizQL 查询应符合 Tableau VizQL Data Service API 的规范，其中分组维度字段不包含 function 属性

**示例说明：**
```python
# ✅ 正确示例：生成的VizQL查询
Intent输入: {
    "dimension_intents": [{
        "technical_field": "pro_name",
        "aggregation": None  # 无聚合
    }],
    "measure_intents": [{
        "technical_field": "收入",
        "aggregation": "SUM"
    }]
}
VizQL输出: {
    "fields": [
        {
            "fieldCaption": "pro_name"
            # 正确：分组维度没有 function 属性
        },
        {
            "fieldCaption": "收入",
            "function": "SUM"  # 度量必须有 function
        }
    ]
}

# ❌ 错误示例：当前系统的错误输出
VizQL错误输出: {
    "fields": [
        {
            "fieldCaption": "pro_name",
            "function": "COUNTD"  # 错误！分组维度不应有 function
        },
        {
            "fieldCaption": "收入",
            "function": "SUM"
        }
    ]
}
```

### 需求 4: 数据模型和Prompt优化

**用户故事：** 作为系统维护者，我希望通过优化数据模型描述和Prompt逻辑来指导LLM正确处理维度字段，以便从源头避免错误。

#### 验收标准

1. 当数据模型的Field description被更新时，应包含完整的使用说明（如何使用、何时添加、何时不添加、可用值）
2. 当问题理解Agent的Prompt被更新时，应只包含判断逻辑（如何判断SQL角色）
3. 当问题理解Agent的get_role()被更新时，应定义Agent的SQL角色
4. 更新后的设计应遵循主流LLM最佳实践，职责分离清晰

**设计原则**（基于Anthropic/OpenAI/Pydantic最佳实践）:

**数据模型职责**:
- 说明字段是什么
- 说明有哪些值可用
- 说明怎么用这些值（何时添加、何时不添加）
- 提供使用示例

**Prompt职责**:
- 提供判断逻辑（如何判断SQL角色）
- 使用SQL语义
- 不包含字段填充规则

**get_role()职责**:
- 定义Agent的SQL角色
- 说明处理的实体类型

### 需求 5: 测试验证和向后兼容性

**用户故事：** 作为系统维护者，我希望修复后的系统能够通过所有测试用例，并且不破坏现有功能。

#### 验收标准

1. 当系统更新修复后，系统应能够正确处理所有测试用例中的简单分组查询（如"各省份的销售额"）
2. 当系统更新修复后，系统应能够正确处理所有测试用例中的计数类查询（如"每个省份有多少门店"）
3. 系统应修复之前因维度聚合错误而失败的测试用例，使其能够成功执行
4. 系统应保持 Understanding Agent、Task Planner Agent 和 Query Executor 的相同API接口

### 需求 6: 符合Tableau VizQL API规范

**用户故事：** 作为系统架构师，我希望系统生成的VizQL查询完全符合Tableau官方API规范，以确保与Tableau MCP等标准实现保持一致。

#### 验收标准

1. 当系统生成VizQL查询时，对于用于分组的维度字段，系统应生成不包含 "function" 属性的字段对象
2. 当系统生成VizQL查询时，对于需要聚合的字段（度量或被计数维度），系统应生成包含 "function" 属性的字段对象
3. 系统生成的VizQL查询结构应与 Tableau MCP 项目的 query-datasource 工具示例保持一致
4. 系统应遵循 Tableau VizQL Data Service API 文档中关于字段聚合的规范

**官方文档参考：**
- **Tableau VizQL Data Service API**: https://help.tableau.com/current/api/vizql-data-service/en-us/index.html
- **创建查询文档**: https://help.tableau.com/current/api/vizql-data-service/en-us/docs/vds_create_queries.html
- **Tableau MCP 项目**: https://github.com/tableau/tableau-mcp

**参考标准（来自Tableau MCP）：**
```typescript
// ✅ Tableau MCP的正确示例
{
  "query": {
    "fields": [
      {
        "fieldCaption": "Customer Name"  // 维度字段，无function
      },
      {
        "fieldCaption": "Sales",
        "function": "SUM",  // 度量字段，必须有function
        "fieldAlias": "Total Revenue"
      }
    ]
  }
}

// ✅ 带计数的正确示例
{
  "query": {
    "fields": [
      {
        "fieldCaption": "Category"  // 分组维度，无function
      },
      {
        "fieldCaption": "Order ID",
        "function": "COUNT",  // 计数，有function
        "fieldAlias": "Order Count"
      }
    ]
  }
}
```

**测试场景覆盖：**
```python
# 场景1：简单分组查询
测试问题: "各省份的销售额是多少？"
预期VizQL: {
    "fields": [
        {"fieldCaption": "pro_name"},  # 无function
        {"fieldCaption": "收入", "function": "SUM"}
    ]
}

# 场景2：多维度分组
测试问题: "各省份各门店的销售额和利润"
预期VizQL: {
    "fields": [
        {"fieldCaption": "pro_name"},  # 无function
        {"fieldCaption": "门店编码"},  # 无function
        {"fieldCaption": "收入", "function": "SUM"},
        {"fieldCaption": "过机毛利", "function": "SUM"}
    ]
}

# 场景3：计数类查询
测试问题: "每个省份有多少个门店？"
预期VizQL: {
    "fields": [
        {"fieldCaption": "pro_name"},  # 分组维度，无function
        {"fieldCaption": "门店编码", "function": "COUNTD"}  # 被计数维度，有function
    ]
}

# 场景4：TopN查询
测试问题: "销售额前5的省份"
预期VizQL: {
    "fields": [
        {"fieldCaption": "pro_name"},  # 无function
        {"fieldCaption": "收入", "function": "SUM"}
    ],
    "filters": [{
        "field": {"fieldCaption": "收入"},
        "filterType": "TOP",
        "howMany": 5,
        "fieldToMeasure": {"fieldCaption": "收入"}
    }]
}
```
