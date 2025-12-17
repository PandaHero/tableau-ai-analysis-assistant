# 需求文档

## 简介

本规格文档定义了 Semantic Parser Agent（语义解析 Agent）和语义层重构的需求。核心目标是：
1. 建立一个**高度抽象、平台无关**的语义层，支持多 BI 平台（Tableau、Power BI、Superset 等）
2. 让 LLM 输出纯粹的**用户意图表示**，而非平台特定的技术实现
3. 增强问题理解能力，支持问题重述、意图分类、澄清问题等功能
4. 平台适配器负责将语义层转换为具体平台的查询语句

### 背景

当前系统存在以下问题：
1. **语义层与 Tableau 强耦合**：现有模型使用 Tableau 特定概念（LOD、TableCalc），无法扩展到其他 BI 平台
2. **表计算/LOD 决策硬编码**：`ImplementationResolver` 使用硬编码规则，无法处理复杂场景
3. **转换逻辑复杂**：QueryBuilder 需要理解业务意图并推断技术实现，容易出错
4. **问题理解不完整**：缺少问题重述、意图分类、澄清问题等关键功能
5. **日期计算不稳定**：当前 LLM + 代码规则混合方案不够可靠

### 解决方案

重构后的架构采用**意图驱动、平台无关**的设计：

```
用户问题 → Semantic Parser Agent → SemanticQuery（平台无关）
                                         ↓
                              ┌──────────┼──────────┐
                              ↓          ↓          ↓
                         Tableau    Power BI   Superset
                         Adapter    Adapter    Adapter
                              ↓          ↓          ↓
                          VizQL       DAX        SQL
```

- **Semantic Parser Agent**：输出 `SemanticParseResult`，包含重述问题、意图分类、语义查询、澄清问题
- **SemanticQuery**：平台无关的语义层模型，使用通用计算意图（RANKING、RUNNING_TOTAL、FIXED_GRANULARITY 等）
- **PlatformAdapter**：平台适配器，将 SemanticQuery 转换为平台特定查询（Tableau/Power BI/Superset）
- **FieldMapper**：保持现有 RAG + LLM 方案不变

## 术语表

### 核心概念（平台无关）

- **Semantic Parser Agent**: 语义解析 Agent，负责将用户自然语言问题解析为平台无关的结构化语义查询
- **SemanticParseResult**: Agent 输出的完整解析结果，包含重述问题、意图、语义查询等
- **SemanticQuery**: 平台无关的语义查询模型，描述用户想要什么数据
- **Computation**: 计算定义，描述用户想要的计算意图（排名、累计、占比、粒度聚合等）
- **ComputationType**: 计算类型枚举，包括 RANKING、RUNNING_TOTAL、MOVING_AVERAGE、FIXED_GRANULARITY 等
- **Filter**: 过滤器定义，描述用户的筛选意图
- **FilterType**: 过滤器类型枚举，包括 SET、DATE_RANGE、NUMERIC_RANGE、TEXT_MATCH、TOP_N
- **PlatformAdapter**: 平台适配器接口，定义将 SemanticQuery 转换为平台特定查询的方法
- **FieldMapper**: 字段映射器，负责将业务术语映射到技术字段名
- **意图分类**: 将用户问题分类为 DATA_QUERY、CLARIFICATION、GENERAL、IRRELEVANT 四种类型
- **会话总结中间件**: SummarizationMiddleware，负责压缩历史对话以防止上下文溢出

### 计算类型说明（平台无关）

| 计算类型 | 用户意图 | Tableau 实现 | Power BI 实现 | SQL 实现 |
|---------|---------|-------------|--------------|----------|
| RANKING | 排名 | TableCalc RANK | RANKX() | RANK() OVER |
| RUNNING_TOTAL | 累计求和 | TableCalc RUNNING_TOTAL | CALCULATE + FILTER | SUM() OVER |
| MOVING_AVERAGE | 移动平均 | TableCalc MOVING_CALCULATION | AVERAGEX | AVG() OVER |
| PERCENT_OF_TOTAL | 占比 | TableCalc PERCENT_OF_TOTAL | DIVIDE + CALCULATE | SUM()/SUM() OVER |
| FIXED_GRANULARITY | 固定粒度聚合 | LOD {FIXED:...} | CALCULATE + ALL() | Subquery |
| FINER_GRANULARITY | 更细粒度聚合 | LOD {INCLUDE:...} | CALCULATE + VALUES() | Subquery |
| COARSER_GRANULARITY | 更粗粒度聚合 | LOD {EXCLUDE:...} | CALCULATE + ALLEXCEPT() | Subquery |
| YEAR_OVER_YEAR | 同比 | TableCalc DIFFERENCE_FROM | SAMEPERIODLASTYEAR | LAG() OVER |

## 需求

### 需求 1：问题重述

**用户故事：** 作为系统用户，我希望系统能够将跟进问题补全为完整问题，以便系统能够正确理解上下文相关的查询。

#### 验收标准

1. 当用户提出跟进问题且存在历史对话时，系统应将跟进问题与历史上下文合并为完整问题
2. 当用户问题引用了历史对话中的实体（如"这些产品"、"上面的数据"）时，系统应将引用替换为具体实体
3. 当用户问题是独立问题（无需历史上下文）时，系统应原样保留问题
4. 当系统重述问题时，应保留用户的原始意图和所有筛选条件
5. 当历史对话超过 5 轮时，系统应优先使用会话总结中间件生成的摘要作为上下文，而非原始对话历史
6. 当会话总结可用时，系统应从摘要中提取关键实体（维度、度量、筛选条件）用于问题重述

**历史对话处理规则：**
- 最大回溯层数：5 轮对话
- 超过 5 轮时：使用 SummarizationMiddleware 生成的摘要
- 摘要格式应包含：当前分析主题、已使用的维度/度量、活跃的筛选条件

**示例：**
- 历史="2024年销售额"，当前="各省份呢？" → 重述为"2024年各省份销售额"
- 历史="华东地区销售额"，当前="利润呢？" → 重述为"华东地区利润"
- 当前="各产品类别的销售额" → 重述为"各产品类别的销售额"（无需补全）

### 需求 2：意图分类

**用户故事：** 作为系统开发者，我希望系统能够准确分类用户问题的意图，以便系统能够采取正确的处理路径。

#### 验收标准

1. 当用户问题包含可查询的字段（维度、度量或两者）且信息完整时，系统应将意图分类为 `VIZQL_QUERY`
2. 当用户问题引用了未指定的值或需要澄清时，系统应将意图分类为 `CLARIFICATION`
3. 当用户问题询问数据集描述、字段信息等元数据时，系统应将意图分类为 `GENERAL`
4. 当用户问题与数据分析无关时，系统应将意图分类为 `IRRELEVANT`
5. 当系统分类意图时，应同时输出分类理由

**意图分类表：**

| 意图 | 判断条件 | 示例 |
|------|---------|------|
| VIZQL_QUERY | 有可查询的字段，信息完整 | "各省份销售额"、"总销售额"、"有哪些产品类别" |
| CLARIFICATION | 引用了未指定的值或需要澄清 | "这些产品的销售额" |
| GENERAL | 问数据集描述、字段信息 | "有哪些字段？"、"销售额是什么意思？" |
| IRRELEVANT | 与数据分析无关 | "今天天气怎么样？" |

**注意**：VIZQL_QUERY 不要求同时有维度和度量，以下都是有效的查询：
- 只有维度："有哪些产品类别"、"列出所有省份"
- 只有度量："总销售额是多少"、"平均利润"
- 维度+度量："各省份销售额"、"按月统计订单数量"

### 需求 3：澄清问题生成

**用户故事：** 作为系统用户，我希望当我的问题不够清晰时，系统能够生成澄清问题帮助我完善查询。

#### 验收标准

1. 当意图为 `CLARIFICATION` 时，系统应生成具体的澄清问题
2. 当用户问题引用了未指定的值时，系统应基于数据源元数据提供可选值列表
3. 当用户问题存在歧义时，系统应基于数据源元数据提供选项供用户选择
4. 当系统生成澄清问题时，应保持友好和简洁的语气
5. 当生成澄清问题时，系统应从预加载的数据源元数据中获取字段信息和可选值

**澄清问题字段来源：**
- 字段列表：来自 `/read-metadata` API 返回的 `FieldMetadata`
- 维度可选值：来自数据源元数据中的维度成员（如有缓存）
- 度量列表：来自元数据中 `fieldRole: MEASURE` 的字段

**示例：**
- "这些产品的销售额" → 澄清问题："您指的是哪些产品？数据源中包含以下产品类别：[家具、办公用品、技术产品]"
- "上个月的数据" → 澄清问题："您需要查看哪个指标的数据？可选指标包括：[销售额、利润、订单数量、折扣]"

### 需求 4：语义查询输出（平台无关）

**用户故事：** 作为系统架构师，我希望 Semantic Parser Agent 输出平台无关的语义查询，以便支持多 BI 平台扩展。

#### 验收标准

1. 当 Semantic Parser Agent 处理用户问题时，系统应输出平台无关的 `SemanticQuery`，包含：
   - `dimensions`: 维度字段列表
   - `measures`: 度量字段列表
   - `computations`: 计算列表（使用通用 ComputationType）
   - `filters`: 过滤器列表（使用通用 FilterType）
2. 当用户问题涉及窗口计算（累计、排名、占比、移动平均）时，Agent 应生成 `Computation`，指定：
   - `type`: 计算类型（RANKING/RUNNING_TOTAL/MOVING_AVERAGE/PERCENT_OF_TOTAL 等）
   - `target_measure`: 目标度量字段
   - `order_dimensions`: 排序维度（计算沿哪些维度进行）
   - `partition_dimensions`: 分区维度（在哪些维度内独立计算）
   - 类型特定参数（如 `direction`、`window_size` 等）
3. 当用户问题涉及粒度聚合时，Agent 应生成 `Computation`，指定：
   - `type`: FIXED_GRANULARITY / FINER_GRANULARITY / COARSER_GRANULARITY
   - `granularity_dimensions`: 粒度维度
   - `target_field`: 目标字段
   - `aggregation`: 聚合方式
4. 当 Agent 输出语义查询时，系统应使用业务术语作为字段名（而非技术字段名）

**平台无关设计原则：**
- 语义层只描述"用户想要什么"，不描述"BI 工具怎么实现"
- 不使用任何平台特定术语（如 LOD、TableCalc、DAX）
- 平台适配器负责将通用计算意图转换为平台特定实现


### 需求 5：支持窗口计算（平台无关）

**用户故事：** 作为开发者，我希望新语义层支持窗口计算功能，以便系统能够处理复杂的分析场景，并支持多 BI 平台。

#### 背景：窗口计算的通用概念

窗口计算是依赖结果集顺序的计算，所有 BI 平台都支持，但实现方式不同：

| 计算意图 | Tableau | Power BI | SQL |
|---------|---------|----------|-----|
| 排名 | TableCalc RANK | RANKX() | RANK() OVER |
| 累计求和 | TableCalc RUNNING_TOTAL | CALCULATE + FILTER | SUM() OVER |
| 移动平均 | TableCalc MOVING_CALCULATION | AVERAGEX + DATESINPERIOD | AVG() OVER |
| 占比 | TableCalc PERCENT_OF_TOTAL | DIVIDE + CALCULATE | SUM()/SUM() OVER |
| 同比/环比 | TableCalc DIFFERENCE_FROM | SAMEPERIODLASTYEAR | LAG() OVER |

**关键概念（平台无关）：**
- **order_dimensions（排序维度）**：计算沿着哪些维度进行
- **partition_dimensions（分区维度）**：在哪些维度内独立计算

#### 验收标准

1. 当用户询问累计计算（"累计销售额"）时，系统应生成 `type: RUNNING_TOTAL` 的 `Computation`，并指定：
   - `target_measure`: 目标度量
   - `order_dimensions`: 排序维度
   - `partition_dimensions`: 分区维度（可选，用于按某维度重新开始累计）
2. 当用户询问移动计算（"3期移动平均"）时，系统应生成 `type: MOVING_AVERAGE` 的 `Computation`，并指定：
   - `target_measure`: 目标度量
   - `window_size`: 窗口大小（如 3）
   - `include_current`: 是否包含当前值（默认 true）
3. 当用户询问排名（"销售额排名"）时，系统应生成 `type: RANKING` 的 `Computation`，并指定：
   - `target_measure`: 目标度量
   - `direction`: 排序方向（ASC/DESC，默认 DESC）
   - `order_dimensions`: 排序维度
4. 当用户询问占比（"占比"）时，系统应生成 `type: PERCENT_OF_TOTAL` 的 `Computation`
5. 当用户询问同比/环比时，系统应生成相应的 `Computation`：
   - 同比 → `type: YEAR_OVER_YEAR`
   - 环比 → `type: MONTH_OVER_MONTH` 或 `type: PERIOD_OVER_PERIOD`
   - 并指定 `date_dimension` 和 `comparison_period`
6. 当用户需要复杂的自定义计算时，系统应生成 `type: CUSTOM` 的 `Computation`，并在 `custom_expression` 字段中描述计算逻辑

**平台适配器职责：**
- Tableau 适配器：将 RANKING → TableCalc RANK，FIXED_GRANULARITY → LOD {FIXED:...}
- Power BI 适配器：将 RANKING → RANKX()，FIXED_GRANULARITY → CALCULATE + ALL()
- SQL 适配器：将 RANKING → RANK() OVER，FIXED_GRANULARITY → Subquery

### 需求 6：支持粒度聚合（平台无关）

**用户故事：** 作为开发者，我希望新语义层支持不同粒度级别的聚合计算，以便系统能够处理复杂的分析场景，并支持多 BI 平台。

#### 背景：粒度聚合的通用概念

粒度聚合是在不同于当前视图粒度的级别进行聚合计算，所有 BI 平台都支持，但实现方式不同：

| 计算意图 | Tableau | Power BI | SQL |
|---------|---------|----------|-----|
| 固定粒度聚合 | LOD {FIXED:...} | CALCULATE + ALL() | Subquery |
| 更细粒度聚合 | LOD {INCLUDE:...} | CALCULATE + VALUES() | Subquery |
| 更粗粒度聚合 | LOD {EXCLUDE:...} | CALCULATE + ALLEXCEPT() | Subquery |

**关键概念（平台无关）：**
- **FIXED_GRANULARITY**：在指定维度级别聚合，不受当前视图影响
- **FINER_GRANULARITY**：在视图维度基础上，额外包含指定维度进行更细粒度聚合
- **COARSER_GRANULARITY**：从视图维度中排除指定维度，在更粗粒度聚合

#### 验收标准

1. 当用户询问固定粒度聚合时，系统应生成 `type: FIXED_GRANULARITY` 的 `Computation`
   - **语义**：在指定维度级别聚合，不受当前视图影响
   - **示例**："每个客户的总销售额（不受当前视图维度影响）"
     ```json
     {
       "type": "FIXED_GRANULARITY",
       "alias": "客户总销售额",
       "granularity_dimensions": ["客户"],
       "aggregation": "SUM",
       "target_field": "销售额"
     }
     ```
   - **示例**："每个客户的首次购买日期"
     ```json
     {
       "type": "FIXED_GRANULARITY",
       "alias": "客户首次购买日期",
       "granularity_dimensions": ["客户"],
       "aggregation": "MIN",
       "target_field": "订单日期"
     }
     ```
   - **示例**："全局总销售额"（无维度 = 全局聚合）
     ```json
     {
       "type": "FIXED_GRANULARITY",
       "granularity_dimensions": [],
       "aggregation": "SUM",
       "target_field": "销售额"
     }
     ```

2. 当用户询问更细粒度聚合时，系统应生成 `type: FINER_GRANULARITY` 的 `Computation`
   - **语义**：在视图维度基础上，额外包含指定维度进行更细粒度聚合
   - **示例**："在当前视图基础上，按产品细分的平均销售额"
     ```json
     {
       "type": "FINER_GRANULARITY",
       "granularity_dimensions": ["产品"],
       "aggregation": "AVG",
       "target_field": "销售额"
     }
     ```

3. 当用户询问更粗粒度聚合时，系统应生成 `type: COARSER_GRANULARITY` 的 `Computation`
   - **语义**：从视图维度中排除指定维度，在更粗粒度聚合
   - **示例**："排除当前区域维度的总销售额"
     ```json
     {
       "type": "COARSER_GRANULARITY",
       "granularity_dimensions": ["区域"],
       "aggregation": "SUM",
       "target_field": "销售额"
     }
     ```

4. 当 LLM 填写 `Computation` 时，系统应使用业务术语（如"客户"、"销售额"），由 FieldMapper 映射到技术字段名

5. 当平台适配器处理 `Computation` 时，系统应将其转换为平台特定实现：
   - Tableau: `{FIXED [Customer]: SUM([Sales])}`
   - Power BI: `CALCULATE(SUM([Sales]), ALL(Customer))`
   - SQL: `SELECT customer, SUM(sales) FROM ... GROUP BY customer`

**粒度聚合类型对比：**

| 类型 | 粒度关系 | 典型场景 | 关键词 |
|------|---------|---------|--------|
| FIXED_GRANULARITY | 独立于视图 | 客户级别汇总、全局汇总 | "不受视图影响"、"固定级别" |
| FINER_GRANULARITY | 比视图更细 | 在类别视图中按产品细分 | "在当前基础上细分"、"额外按XX" |
| COARSER_GRANULARITY | 比视图更粗 | 在产品视图中计算类别汇总 | "排除XX维度"、"忽略XX" |

### 需求 7：平台适配器转换

**用户故事：** 作为开发者，我希望平台适配器负责将语义层转换为平台特定查询语句，包含验证和错误处理机制。

#### 验收标准

1. 当平台适配器接收 `SemanticQuery` 时，系统应按照目标平台规范将语义字段转换为对应的平台特定类型
2. 当平台适配器转换 `Computation` 时，系统应：
   - 验证 `type` 是否为有效的计算类型
   - 验证必要参数是否完整（如窗口计算需要 `order_dimensions`，粒度聚合需要 `granularity_dimensions`）
   - 将通用计算意图转换为平台特定实现
3. 当平台适配器转换粒度聚合时，系统应：
   - 验证结构化字段是否完整（`type`、`granularity_dimensions`、`aggregation`、`target_field`）
   - 转换为平台特定语法：
     - Tableau: `{FIXED [Customer]: SUM([Sales])}`
     - Power BI: `CALCULATE(SUM([Sales]), ALL(Customer))`
     - SQL: Subquery
4. 当语义层输出不符合平台要求时，适配器应尝试自动修正（如参数默认值填充）
5. 当自动修正无法解决问题时，适配器应返回详细的错误信息，由 LLM 根据错误提示进行二次生成
6. 当适配器遇到无法处理的语义结构时，系统应抛出明确的错误，包含错误类型、错误位置和修复建议

**错误处理流程：**
```
SemanticQuery → PlatformAdapter.validate() → 
  ├─ 验证通过 → PlatformAdapter.build() → 平台特定查询
  ├─ 可自动修正 → 修正后生成查询
  └─ 无法修正 → 返回错误信息 → LLM 二次生成
```

### 需求 8：FieldMapper 保持不变

**用户故事：** 作为开发者，我希望 FieldMapper 保持不变，以便现有的 RAG + LLM 字段映射方案继续工作。

#### 验收标准

1. 当 FieldMapper 接收语义查询时，系统应使用现有的两阶段检索（向量检索 + LLM rerank）将业务术语映射到技术字段名
2. 当 FieldMapper 处理 `TableCalcField.dimensions` 中的字段名时，系统应将每个 `fieldCaption` 从业务术语映射到技术字段名
3. 当 FieldMapper 处理 `CalculatedField` 的结构化字段时，系统应映射 `lod_dimensions` 列表中的每个维度名和 `target_field`（可以是度量或维度）
4. 当 FieldMapper 完成映射时，系统应保留所有 VizQL 对齐的结构，仅更改字段名

**CalculatedField 映射说明：**

由于 `CalculatedField` 使用结构化字段（而非 LOD 表达式字符串），FieldMapper 的映射逻辑非常简单：

```python
# 示例 1：聚合度量字段
# 输入（业务术语）
CalculatedField(
    lod_type="FIXED",
    lod_dimensions=["客户"],
    aggregation="SUM",
    target_field="销售额"
)
# 输出（技术字段名）
CalculatedField(
    lod_type="FIXED",
    lod_dimensions=["Customer"],
    aggregation="SUM",
    target_field="Sales"
)

# 示例 2：聚合维度字段（首次购买日期）
# 输入（业务术语）
CalculatedField(
    lod_type="FIXED",
    lod_dimensions=["客户"],
    aggregation="MIN",
    target_field="订单日期"
)
# 输出（技术字段名）
CalculatedField(
    lod_type="FIXED",
    lod_dimensions=["Customer"],
    aggregation="MIN",
    target_field="Order Date"
)
```

**注意**：LOD 表达式字符串的组装由 QueryBuilder 负责，不是 FieldMapper 的职责。


### 需求 9：支持全部 7 种过滤器类型

**用户故事：** 作为开发者，我希望新语义层支持 VizQL API 的全部 7 种过滤器类型，以便系统能够处理各种筛选场景。

#### 验收标准

1. 当用户指定集合筛选（"华东地区"）时，系统应生成 `filterType: SET` 的过滤器，并指定适当的 `values`
2. 当用户指定日期范围筛选时，系统应根据以下规则选择过滤器类型：
   - **相对日期过滤器**（`filterType: DATE`）：仅用于原生日期字段，支持 6 种 `dateRangeType`：
     - `CURRENT`：当前期间（当前年/季度/月/周/日）
     - `LAST`：上一个期间
     - `LASTN`：最近 N 个期间（需指定 `rangeN`）
     - `NEXT`：下一个期间
     - `NEXTN`：未来 N 个期间（需指定 `rangeN`）
     - `TODATE`：期间至今（年初至今、月初至今等）
   - **绝对日期过滤器**（`filterType: QUANTITATIVE_DATE`）：用于指定具体日期范围，需指定 `minDate` 和 `maxDate`（RFC 3339 格式）
3. 当用户指定数值范围筛选（">1000"、"100-500"）时，系统应生成 `filterType: QUANTITATIVE_NUMERICAL` 的过滤器
4. 当用户指定匹配筛选（"包含XX"）时，系统应生成 `filterType: MATCH` 的过滤器
5. 当用户指定 Top N 筛选（"前10名"）时，系统应生成 `filterType: TOP` 的过滤器，并指定适当的 `howMany` 和 `direction`

**⚠️ 重要限制：相对日期过滤器只能用于原生日期字段**

根据 VizQL API 测试验证（2025-12-17）：
- ✅ 原生日期字段（如 `Order Date`）可以使用相对日期过滤器（`filterType: DATE`）
- ❌ 计算字段（如 `DATEPARSE('yyyy-MM-dd', [StringField])`）**不能**使用相对日期过滤器
- ❌ 在 `fields` 中定义的计算字段**不能**在 `filters` 中通过 `fieldCaption` 引用（会报 `Unknown Field` 错误）
- ✅ 计算字段可以使用绝对日期过滤器（`filterType: QUANTITATIVE_DATE`）

**API 限制原因：**
- VizQL API 的 `fields` 和 `filters` 是独立的命名空间
- `filters` 中的 `fieldCaption` 只能引用数据源元数据中已存在的字段
- 相对日期过滤器明确禁止使用 `calculation` 表达式（错误信息："Set Filters, Match Filters, and Relative Date Filters can't have Functions or Calculations"）

**对于字符串转日期的场景，替代方案：**
使用 `QUANTITATIVE_DATE` + 应用层动态计算日期范围：
```json
{
  "filterType": "QUANTITATIVE_DATE",
  "field": {"calculation": "DATEPARSE('yyyy-MM-dd', [StringField])"},
  "quantitativeFilterType": "RANGE",
  "minDate": "2025-01-01",  // 应用层根据"今年"计算
  "maxDate": "2025-12-31"
}
```

**日期过滤器选择决策树：**
```
用户日期筛选需求
├─ 字段是原生日期字段？
│   ├─ 是 → 相对日期表达式？（"最近3个月"、"年初至今"）
│   │   ├─ 是 → filterType: DATE + 对应的 dateRangeType
│   │   └─ 否 → filterType: QUANTITATIVE_DATE + minDate/maxDate
│   └─ 否（计算字段）→ filterType: QUANTITATIVE_DATE + minDate/maxDate
```

### 需求 10：日期计算策略

**用户故事：** 作为开发者，我希望日期计算有清晰的策略，优先使用 VizQL 原生相对日期过滤器，以便日期处理更加可靠和一致。

#### 验收标准

1. 当用户使用相对日期表达式且目标字段是原生日期字段时，系统应优先使用 VizQL 相对日期过滤器（`filterType: DATE`）
2. 当用户使用绝对日期表达式或目标字段是计算字段时，LLM 应输出计算后的日期值（RFC 3339 格式：YYYY-MM-DD），使用 `filterType: QUANTITATIVE_DATE`
3. 当 LLM 输出日期值时，代码应验证日期格式是否正确（符合 RFC 3339）
4. 当 LLM 输出日期范围时，代码应验证 start_date ≤ end_date
5. 当日期验证失败时，系统应返回错误信息，由 LLM 根据错误提示重新生成

**日期处理策略（优先级从高到低）：**

| 优先级 | 场景 | 处理方式 | 示例 |
|--------|------|---------|------|
| 1 | 相对日期 + 原生日期字段 | VizQL 相对日期过滤器 | "最近3个月" → `filterType: DATE, dateRangeType: LASTN, rangeN: 3` |
| 2 | 绝对日期 + 任意字段 | LLM 计算 + QUANTITATIVE_DATE | "2024年Q1" → `minDate: 2024-01-01, maxDate: 2024-03-31` |
| 3 | 相对日期 + 计算字段 | LLM 计算 + QUANTITATIVE_DATE | "最近3个月"（计算字段）→ LLM 计算具体日期范围 |

**相对日期到绝对日期的转换示例：**

| 相对日期表达式 | 转换为 QUANTITATIVE_DATE（假设当前日期 2025-12-17） |
|---------------|--------------------------------------------------|
| 今年 | `minDate: 2025-01-01, maxDate: 2025-12-31` |
| 最近3个月 | `minDate: 2025-09-17, maxDate: 2025-12-17` |
| 年初至今 | `minDate: 2025-01-01, maxDate: 2025-12-17` |
| 上个季度 | `minDate: 2025-07-01, maxDate: 2025-09-30` |

**VizQL 相对日期过滤器参数：**
```json
{
  "filterType": "DATE",
  "field": {"fieldCaption": "Order Date"},
  "periodType": "MONTHS",
  "dateRangeType": "LASTN",
  "rangeN": 3
}
```
- `periodType`: YEARS, QUARTERS, MONTHS, WEEKS, DAYS
- `dateRangeType`: CURRENT, LAST, LASTN, NEXT, NEXTN, TODATE
- `rangeN`: 仅 LASTN/NEXTN 需要

**代码验证规则（用于 QUANTITATIVE_DATE）：**
- 格式验证：必须符合 `^\d{4}-\d{2}-\d{2}$` 正则
- 范围验证：start_date ≤ end_date
- 合理性验证：日期在合理范围内（如不超过当前日期太远）

### 需求 11：表计算 vs LOD 决策引导

**用户故事：** 作为开发者，我希望 Agent Prompt 能够引导 LLM 做出表计算 vs LOD 的决策，以便 LLM 能够正确选择适当的实现方式。

#### 验收标准

1. 当用户问题涉及依赖查询结果顺序的计算（累计、排名、移动平均）时，Agent 应选择表计算实现
2. 当用户问题涉及固定粒度级别的计算（不受查询维度影响）时，Agent 应选择 LOD 实现
3. 当 Agent 做出实现决策时，系统应在 Prompt 中包含决策推理以引导 LLM
4. 当实现选择存在歧义时，Agent 应默认选择表计算（更常见的情况）

**决策规则：**

| 场景 | 选择 | 原因 |
|------|------|------|
| 累计求和、排名、移动平均 | 表计算 | 依赖结果集顺序 |
| 客户级别汇总（不受视图影响） | FIXED LOD | 独立于视图维度 |
| 在视图基础上细分 | INCLUDE LOD | 比视图更细粒度 |
| 排除某维度的汇总 | EXCLUDE LOD | 比视图更粗粒度 |

### 需求 12：完整的验证逻辑

**用户故事：** 作为开发者，我希望新语义层模型有完整的验证，以便无效查询能够被早期拒绝并提供清晰的错误消息。

#### 验收标准

1. 当创建 `tableCalcType: RUNNING_TOTAL` 的 `TableCalcField` 时，系统应验证 `dimensions` 不为空
2. 当创建 `tableCalcType: MOVING_CALCULATION` 的 `TableCalcField` 时，系统应验证 `previous` 和 `next` 是非负整数
3. 当创建 `CalculatedField` 时，系统应验证结构化字段的完整性：
   - `lod_type` 必须是 `FIXED`、`INCLUDE` 或 `EXCLUDE` 之一
   - `lod_dimensions` 必须是字符串列表（可以为空表示全局聚合）
   - `aggregation` 必须是有效的聚合函数（SUM/AVG/MIN/MAX/COUNT/COUNTD）
   - `target_field` 必须是非空字符串（可以是度量或维度）
4. 当验证失败时，系统应抛出 `ValidationError`，并提供清晰的消息指明哪个字段和什么约束被违反

### 需求 13：Schema 字段描述精简化

**用户故事：** 作为开发者，我希望 Schema 字段描述简洁且自包含，以便 LLM 注意力在字段生成时集中在最相关的信息上。

#### 验收标准

1. 当定义 Schema 字段描述时，系统应将每个字段的描述限制在 100 tokens 以内
2. 当定义 Schema 字段描述时，系统应使用 XML 标签（`<when>`、`<rule>`、`<must_not>`）来结构化内容
3. 当定义 Schema 字段描述时，系统不应引用 Prompt 步骤编号（如"Prompt Step 6"）
4. 当定义 Schema 字段描述时，系统应在字段描述本身中包含所有必要的决策规则（自包含）
5. 当定义条件字段时，系统应使用 `<must_not>` 标签强调负面约束

### 需求 14：Prompt 和 Schema 职责分离

**用户故事：** 作为开发者，我希望 Prompt 和 Schema 有清晰的职责分离，以便没有冗余且每个组件服务于其独特目的。

#### 验收标准

1. 当编写 Prompt 内容时，系统应仅包含高层概念（什么是维度、什么是度量），不引用具体字段名
2. 当编写 Schema 内容时，系统应包含所有具体的填写规则，不引用 Prompt 步骤编号
3. 当相同信息同时出现在 Prompt 和 Schema 中时，系统应从 Prompt 中删除重复内容，仅保留在 Schema 中
4. 当定义决策规则时，系统应使用 `<rule>` 标签将其放在 Schema 字段描述中，而非 Prompt 中

### 需求 15：决策树格式优化

**用户故事：** 作为开发者，我希望决策树格式针对 LLM tokenization 进行优化，以便决策逻辑被模型高效处理。

#### 验收标准

1. 当表示决策树时，系统应使用简单文本格式而非 ASCII 艺术（│、├、─、►）
2. 当表示填写顺序时，系统应使用带括号条件的编号列表
3. 当表示条件逻辑时，系统应使用内联格式（如"4. order (if type=ranking)"）
4. 当决策树复杂时，系统应将其拆分为多个较小的决策块

### 需求 16：负面约束强调

**用户故事：** 作为开发者，我希望负面约束被突出强调，以便 LLM 更可能避免常见错误。

#### 验收标准

1. 当字段有不可违反的关键约束时，系统应使用 `<MUST_NOT>` 标签并提供清晰的错误描述
2. 当定义反模式时，系统应将其放在 `<rule>` 部分之后以获得最大可见性
3. 当约束违反会导致系统错误时，系统应在约束描述中包含"(will cause error)"
4. 当存在多个负面约束时，系统应按严重程度排序（最关键的在前）

### 需求 17：Class Docstring 精简

**用户故事：** 作为开发者，我希望 Class Docstring 示例简洁，以便复杂示例不会稀释对字段级描述的注意力。

#### 验收标准

1. 当编写 Class Docstring 示例时，系统应在 docstring 中最多包含 2 个简单示例
2. 当需要复杂示例时，系统应将其放在 Prompt 的 few-shot 部分而非 Schema 中
3. 当编写 Class Docstring 时，系统应专注于模型的目的和关键约束，而非详尽的示例
4. 当在 Class Docstring 中包含反模式时，系统应限制为 2-3 个最常见的错误
