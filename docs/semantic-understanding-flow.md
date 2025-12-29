# 语义理解完整流程文档

## 目录

1. [概述](#1-概述)
2. [整体架构](#2-整体架构)
3. [Step1: 意图识别与实体提取](#3-step1-意图识别与实体提取)
4. [Step2: 复杂计算推理](#4-step2-复杂计算推理)
5. [字段映射](#5-字段映射)
6. [筛选器处理](#6-筛选器处理)
7. [查询构建](#7-查询构建)
8. [数据模型](#8-数据模型)
9. [路由决策逻辑](#9-路由决策逻辑)
10. [状态管理](#10-状态管理)
11. [上下文管理](#11-上下文管理)
12. [持久化存储](#12-持久化存储)
13. [中间件](#13-中间件)
14. [异常处理](#14-异常处理)

---

## 1. 概述

语义理解系统将用户的自然语言问题转换为可执行的 VizQL 查询。

**核心目标**：将 "各省份2024年的销售额排名" 这样的自然语言，转换为 Tableau 可执行的结构化查询。

**两阶段架构**：

- **Step1 (意图识别)**：理解用户问什么、从哪里取、怎么算。每次查询必经。
- **Step2 (复杂计算)**：推理排名、累计、占比等高级计算。仅当 Step1 判定为复杂查询时触发。

**处理流水线**：

```
用户问题 → Step1(意图识别) → [Step2(复杂计算)] → 字段映射 → 筛选值解析 → 查询构建 → 执行
```


---

## 2. 整体架构

### 2.1 系统流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SemanticParser Subgraph                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────┐    ┌──────────────────┐    ┌─────────┐    ┌─────────────┐    │
│   │  Step1  │───▶│ route_after_step1│───▶│  Step2  │───▶│route_after_ │    │
│   │  (LLM)  │    │                  │    │  (LLM)  │    │   step2     │    │
│   └─────────┘    └──────────────────┘    └─────────┘    └─────────────┘    │
│        │                  │                   │                │            │
│        │         ┌────────┴────────┐          │                │            │
│        │         │                 │          │                ▼            │
│        │         ▼                 ▼          │          ┌─────────┐       │
│        │    ┌─────────┐      ┌─────────┐      │          │ Pipeline│       │
│        │    │ Pipeline│      │   END   │      │          └─────────┘       │
│        │    │         │      │(GENERAL)│      │                │            │
│        │    └─────────┘      └─────────┘      │                ▼            │
│        │         │                            │          ┌─────────┐       │
│        │         ▼                            │          │   END   │       │
│        │    ┌─────────┐                       │          └─────────┘       │
│        │    │   END   │                       │                             │
│        │    └─────────┘                       │                             │
└────────┴──────────────────────────────────────┴─────────────────────────────┘
```

### 2.2 路由决策规则

**规则1**：意图 = GENERAL → 结束（用户问的是元数据问题，如"有哪些字段"）

**规则2**：意图 = CLARIFICATION → 结束（信息不完整，返回澄清问题）

**规则3**：意图 = IRRELEVANT → 结束（与数据分析无关的问题）

**规则4**：意图 = DATA_QUERY 且 复杂度 = SIMPLE → 进入 Pipeline（简单聚合查询，跳过 Step2）

**规则5**：意图 = DATA_QUERY 且 复杂度 = COMPLEX → 进入 Step2（需要复杂计算）

**规则6**：Pipeline 执行成功 → 结束（返回查询结果）

**规则7**：Pipeline 需要澄清 → 结束（返回澄清信息给用户）

---

## 3. Step1: 意图识别与实体提取

Step1 是语义理解的"直觉"阶段，负责理解用户问题并提取结构化信息。

### 3.1 输入信息

- **用户问题**：当前对话中的问题，是主要分析对象
- **对话历史**：用于解决指代消解（如"它"指什么）
- **可用字段列表**：数据源元数据，约束 LLM 只能选择存在的字段
- **当前时间**：用于解析"上个月"、"今年"等相对日期

### 3.2 输出结构（三元素模型）

Step1 的输出遵循 **What-Where-How** 三元素模型：

```
Step1Output
├── restated_question    # 重述的完整问题
├── what                 # 用户想要什么（度量）
│   └── measures[]       # 度量列表
├── where                # 从哪里取（维度+筛选）
│   ├── dimensions[]     # 维度列表
│   └── filters[]        # 筛选器列表
├── how_type             # 怎么算（SIMPLE 或 COMPLEX）
├── intent               # 意图分类
└── validation           # 自校验结果
```


### 3.3 What（目标度量）

What 回答"用户想看什么数据"，包含一个度量列表。

**度量字段 (MeasureField) 包含**：

- **field_name**：字段名（用户语言），如"销售额"、"订单数"
- **aggregation**：聚合方式，如 SUM、AVG、COUNT
- **alias**：别名（可选），如"总销售额"
- **sort**：排序规格（可选），ASC 或 DESC

**聚合类型说明**：

- **SUM**：求和，如"总销售额"
- **AVG**：平均值，如"平均单价"
- **COUNT**：计数，如"订单数量"
- **COUNTD**：去重计数，如"客户数"
- **MIN**：最小值，如"最低价格"
- **MAX**：最大值，如"最高销售额"
- **MEDIAN**：中位数
- **STDEV**：标准差
- **VAR**：方差

### 3.4 Where（维度和筛选器）

Where 回答"按什么分组"和"筛选什么数据"。

**维度字段 (DimensionField) 包含**：

- **field_name**：字段名，如"省份"、"订单日期"
- **alias**：别名（可选）
- **date_granularity**：日期粒度（可选），如 YEAR、MONTH、DAY
- **sort**：排序规格（可选）

**日期粒度说明**：

- **YEAR**：按年，如"按年查看"
- **QUARTER**：按季度
- **MONTH**：按月
- **WEEK**：按周
- **DAY**：按天
- **HOUR**：按小时
- **MINUTE**：按分钟

### 3.5 HowType（计算复杂度判定）

HowType 决定是否需要进入 Step2 进行复杂计算推理。

**SIMPLE（简单查询）**：

- 基本聚合："总销售额"、"平均价格"、"订单数量"
- 简单分组："各省份销售额"、"按月订单数"
- Top N 筛选："销售额前5的城市"（返回筛选后的子集，不是排名列）

**COMPLEX（复杂查询）触发关键词**：

- 排名类："排名"、"排行"、"Rank"（添加排名列到所有行）
- 累计类："累计"、"YTD"、"Running Total"
- 同比环比："同比"、"环比"、"YoY"、"MoM"
- 占比类："占比"、"百分比"、"% of Total"
- LOD 类："每个客户的X"、"首次购买日期"、"客户生命周期价值"

### 3.6 Intent（意图分类）

意图分类决定后续的处理路径。

**DATA_QUERY（数据查询）**：
- 完整的数据查询请求
- 示例："各省份的销售额"、"2024年每月订单数"

**CLARIFICATION（需要澄清）**：
- 信息不完整，无法构建查询
- 示例："销售情况怎么样？"（缺少具体度量和维度）

**GENERAL（一般性问题）**：
- 询问元数据或字段信息
- 示例："这个数据源有哪些字段？"、"销售额字段是什么类型？"

**IRRELEVANT（无关问题）**：
- 与数据分析完全无关
- 示例："今天天气怎么样？"


### 3.7 Step1 处理流程

```
接收用户问题
    │
    ▼
┌─────────────────────────────────────┐
│  1. 问题重述                         │
│     - 结合对话历史                    │
│     - 解决指代消解                    │
│     - 补全省略信息                    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. 意图分类                         │
│     - 判断是否为数据查询              │
│     - 判断信息是否完整                │
│     - 判断是否与数据分析相关          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. 实体提取                         │
│     - 提取度量（What）               │
│     - 提取维度（Where.dimensions）   │
│     - 提取筛选条件（Where.filters）  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  4. 复杂度判定                       │
│     - 检测排名/累计/占比等关键词      │
│     - 判定 SIMPLE 或 COMPLEX         │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  5. 自校验                           │
│     - 检查筛选器是否完整              │
│     - 检查必填字段是否存在            │
└─────────────────────────────────────┘
    │
    ▼
输出 Step1Output
```

---

## 4. Step2: 复杂计算推理

Step2 是语义理解的"推理"阶段，仅当 Step1 判定 how_type = COMPLEX 时触发。

### 4.1 触发条件

- 意图必须是 DATA_QUERY
- 复杂度必须是 COMPLEX

### 4.2 输出结构

```
Step2Output
├── reasoning        # 推理过程说明
├── computations[]   # 计算定义列表
└── validation       # 自校验结果
```

### 4.3 计算类型概览

**LOD 表达式（改变计算粒度）**：

- **LOD_FIXED**：固定粒度计算，与查询维度无关
  - 场景：计算每个客户的首次购买日期
  - 示例：`{FIXED [CustomerID] : MIN([OrderDate])}`

- **LOD_INCLUDE**：包含额外维度，比查询更细
  - 场景：在区域汇总中计算每个订单的平均值
  - 示例：`{INCLUDE [OrderID] : AVG([Sales])}`

- **LOD_EXCLUDE**：排除某些维度，比查询更粗
  - 场景：在子类别视图中计算类别级别的总和
  - 示例：`{EXCLUDE [Subcategory] : SUM([Sales])}`

**表计算（基于查询结果的二次计算）**：

- **RANK**：排名（有间隔），如 1, 2, 2, 4
- **DENSE_RANK**：密集排名（无间隔），如 1, 2, 2, 3
- **PERCENTILE**：百分位排名
- **RUNNING_TOTAL**：累计总和
- **MOVING_CALC**：移动计算（移动平均等）
- **PERCENT_OF_TOTAL**：占比计算
- **DIFFERENCE**：差异计算
- **PERCENT_DIFFERENCE**：百分比差异（环比等）


### 4.4 计算类型详解

#### 4.4.1 排名计算 (RANK / DENSE_RANK)

**参数说明**：

- **target**：排名依据的度量字段
- **partition_by**：分区维度列表（在每个分区内独立排名）
- **direction**：排序方向，DESC（降序，值大排前）或 ASC（升序）
- **rank_style**：排名风格
  - COMPETITION：竞争排名，有间隔（1, 2, 2, 4）
  - DENSE：密集排名，无间隔（1, 2, 2, 3）
  - UNIQUE：唯一排名（1, 2, 3, 4）
- **top_n**：可选，只保留前 N 名

**示例场景**：

- "各省份销售额排名" → RANK, target=销售额, partition_by=[], direction=DESC
- "每个类别内的产品销售排名" → RANK, target=销售额, partition_by=[类别], direction=DESC

#### 4.4.2 累计计算 (RUNNING_TOTAL)

**参数说明**：

- **target**：累计的度量字段
- **partition_by**：分区维度（在每个分区内独立累计）
- **aggregation**：累计方式，SUM（累计和）、AVG（累计平均）等
- **restart_every**：重新开始累计的维度（如按年重置）

**示例场景**：

- "按月累计销售额" → RUNNING_TOTAL, target=销售额, aggregation=SUM
- "年度内按月累计（YTD）" → RUNNING_TOTAL, target=销售额, restart_every=Year

#### 4.4.3 占比计算 (PERCENT_OF_TOTAL)

**参数说明**：

- **target**：计算占比的度量字段
- **partition_by**：分区维度（空=全局占比）
- **level_of**：占比计算的层级

**示例场景**：

- "各省份销售额占总销售额的比例" → PERCENT_OF_TOTAL, target=销售额, partition_by=[]
- "各省份在所属区域内的销售占比" → PERCENT_OF_TOTAL, target=销售额, partition_by=[区域]

#### 4.4.4 差异计算 (DIFFERENCE / PERCENT_DIFFERENCE)

**参数说明**：

- **target**：计算差异的度量字段
- **partition_by**：分区维度
- **relative_to**：相对于哪个值
  - PREVIOUS：上一个值（环比）
  - NEXT：下一个值
  - FIRST：第一个值
  - LAST：最后一个值

**示例场景**：

- "销售额环比增长率" → PERCENT_DIFFERENCE, target=销售额, relative_to=PREVIOUS
- "与首月相比的销售额变化" → DIFFERENCE, target=销售额, relative_to=FIRST

### 4.5 组合计算规则

当问题同时需要 LOD 和表计算时，必须遵循以下顺序：

```
LOD 计算（先执行）→ 表计算（后执行，可引用 LOD 结果）
```

**示例**："按首次购买日期对客户进行排名"

1. 先用 LOD_FIXED 计算每个客户的首次购买日期
2. 再用 RANK 对首次购买日期进行排名

```
computations = [
    LOD_FIXED(target=订单日期, dimensions=[客户ID], aggregation=MIN, alias=首次购买日期),
    RANK(target=首次购买日期, partition_by=[], direction=ASC)
]
```


### 4.6 Step2 处理流程

```
接收 Step1Output
    │
    ▼
┌─────────────────────────────────────┐
│  1. 分析重述问题                     │
│     - 识别计算类型关键词              │
│     - 确定需要哪些计算                │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. 判断是否需要 LOD                 │
│     - 是否需要改变计算粒度            │
│     - 确定 LOD 类型和参数             │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. 判断是否需要表计算               │
│     - 是否需要排名/累计/占比等        │
│     - 确定表计算类型和参数            │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  4. 组装计算列表                     │
│     - LOD 在前，表计算在后            │
│     - 表计算可引用 LOD 的 alias       │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  5. 自校验                           │
│     - 检查 target 是否在度量中        │
│     - 检查 partition_by 是否在维度中  │
│     - 检查计算类型是否匹配问题意图    │
└─────────────────────────────────────┘
    │
    ▼
输出 Step2Output
```

---

## 5. 字段映射

字段映射将用户输入的业务术语（如"销售额"）映射到数据源中的技术字段名（如"Sales"）。

### 5.1 映射挑战

- 用户可能使用中文，字段名是英文
- 用户可能使用别名或简称
- 用户可能拼写错误或使用模糊表达

### 5.2 映射策略（优先级从高到低）

**策略1：缓存命中**
- 检查是否有之前成功映射的缓存
- 命中则直接返回，最快

**策略2：精确匹配**
- 字段名完全匹配
- 或字段的 Caption 完全匹配

**策略3：RAG 高置信度匹配**
- 使用向量相似度搜索
- 置信度 ≥ 0.9 时直接采用，不调用 LLM

**策略4：RAG + LLM 回退**
- 置信度 < 0.9 时
- 将 Top-K 候选字段交给 LLM 选择最佳匹配

**策略5：纯 LLM 匹配**
- RAG 不可用时的兜底方案
- 将所有字段列表交给 LLM 选择


### 5.3 字段映射流程

```
接收业务术语（如"销售额"）
    │
    ▼
┌─────────────────────────────────────┐
│  1. 检查缓存                         │
│     - 命中 → 直接返回                │
│     - 未命中 → 继续                  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. RAG 向量检索                     │
│     - 计算术语的 Embedding           │
│     - 在字段索引中搜索相似字段        │
│     - 返回 Top-K 候选及置信度         │
└─────────────────────────────────────┘
    │
    ├── 置信度 ≥ 0.9 ──────────────────┐
    │                                  │
    ▼                                  ▼
┌─────────────────────┐    ┌─────────────────────┐
│  3a. LLM 选择       │    │  3b. 直接采用       │
│  - 将候选交给 LLM   │    │  - 高置信度快速路径 │
│  - LLM 选择最佳匹配 │    │  - 不调用 LLM      │
└─────────────────────┘    └─────────────────────┘
    │                                  │
    └──────────────┬───────────────────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│  4. 写入缓存                         │
│     - 保存映射结果                   │
│     - 设置 TTL（24小时）             │
└─────────────────────────────────────┘
    │
    ▼
返回映射结果（技术字段名 + 置信度 + 来源）
```

### 5.4 映射结果结构

- **business_term**：原始业务术语
- **technical_field**：映射到的技术字段名
- **confidence**：置信度（0-1）
- **mapping_source**：映射来源
  - cache_hit：缓存命中
  - rag_direct：RAG 高置信度直接匹配
  - rag_llm_fallback：RAG + LLM 回退
  - llm_only：纯 LLM 匹配
- **alternatives**：备选字段列表（低置信度时提供）
- **category**：字段所属类别（如果有层级信息）
- **level**：字段层级
- **granularity**：字段粒度

---

## 6. 筛选器处理

筛选器定义了数据的过滤条件，Step1 提取筛选器后，需要进一步处理才能转换为 VizQL 格式。

### 6.1 筛选器类型

**SetFilter（集合筛选）**：
- 用途：筛选特定值的集合
- 参数：field_name, values[], exclude
- 示例："只看北京和上海" → values=["北京", "上海"], exclude=false
- 示例："排除华北区域" → values=["华北"], exclude=true

**DateRangeFilter（日期范围筛选）**：
- 用途：筛选日期范围
- 参数：field_name, start_date, end_date
- 示例："2024年" → start_date=2024-01-01, end_date=2024-12-31
- 示例："上个月" → 根据当前时间计算具体日期

**NumericRangeFilter（数值范围筛选）**：
- 用途：筛选数值范围
- 参数：field_name, min_value, max_value, include_min, include_max
- 示例："销售额大于1000" → min_value=1000, include_min=false
- 示例："价格在10到100之间" → min_value=10, max_value=100

**TextMatchFilter（文本匹配筛选）**：
- 用途：筛选文本模式
- 参数：field_name, pattern, match_type
- match_type 选项：
  - CONTAINS：包含
  - STARTS_WITH：开头匹配
  - ENDS_WITH：结尾匹配
  - EXACT：精确匹配
  - REGEX：正则表达式

**TopNFilter（Top N 筛选）**：
- 用途：筛选排名前/后 N 的记录
- 参数：field_name, n, by_field, direction
- 示例："销售额前10的产品" → n=10, by_field=销售额, direction=DESC
- 示例："销量最低的5个区域" → n=5, by_field=销量, direction=ASC


### 6.2 日期筛选处理流程

日期筛选需要特殊处理，因为用户通常使用相对日期表达。

```
用户输入相对日期（如"上个月"、"今年"）
    │
    ▼
┌─────────────────────────────────────┐
│  1. LLM 解析相对日期                 │
│     - 结合当前时间                   │
│     - 计算具体的 start_date          │
│     - 计算具体的 end_date            │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. 检查字段数据类型                 │
│     - DATE/DATETIME 类型 → 直接使用  │
│     - STRING 类型 → 需要 DATEPARSE   │
└─────────────────────────────────────┘
    │
    ▼
生成 DateRangeFilter
```

**相对日期解析示例**（假设当前时间是 2024-12-27）：

- "今年" → start_date=2024-01-01, end_date=2024-12-31
- "上个月" → start_date=2024-11-01, end_date=2024-11-30
- "最近7天" → start_date=2024-12-20, end_date=2024-12-27
- "去年同期" → start_date=2023-12-01, end_date=2023-12-27

---

## 7. 查询构建

查询构建器将平台无关的 SemanticQuery 转换为 Tableau 特定的 VizQL API 请求。

### 7.1 SemanticQuery 结构

```
SemanticQuery
├── dimensions[]      # 维度列表（来自 Step1）
├── measures[]        # 度量列表（来自 Step1）
├── computations[]    # 计算列表（来自 Step2，可选）
├── filters[]         # 筛选器列表（来自 Step1）
└── row_limit         # 行数限制（可选）
```

### 7.2 VizQL 字段构建规则

**维度字段构建**：

- 普通维度 → `{"fieldCaption": "Category"}`
- 带日期粒度（DATE 类型）→ `{"fieldCaption": "Order Date", "function": "TRUNC_MONTH"}`
- 带日期粒度（STRING 类型）→ `{"fieldCaption": "Order Date", "calculation": "DATETRUNC('month', DATEPARSE('yyyy-MM-dd', [Order Date]))"}`

**度量字段构建**：

- 普通度量 → `{"fieldCaption": "Sales", "function": "SUM"}`

**表计算字段构建**：

- 需要同时包含聚合函数和表计算定义
- 结构：`{"fieldCaption": "Sales", "function": "SUM", "tableCalculation": {...}}`

**LOD 字段构建**：

- 使用 calculation 属性
- 结构：`{"fieldCaption": "FirstPurchase", "calculation": "{FIXED [CustomerID] : MIN([OrderDate])}"}`

### 7.3 VizQL 筛选器构建规则

**SetFilter → SET 类型**：
```
{
  "field": {"fieldCaption": "City"},
  "filterType": "SET",
  "values": ["北京", "上海"],
  "exclude": false
}
```

**DateRangeFilter → QUANTITATIVE_DATE 类型**：
```
{
  "field": {"fieldCaption": "Order Date"},
  "filterType": "QUANTITATIVE_DATE",
  "quantitativeFilterType": "RANGE",
  "minDate": "2024-01-01",
  "maxDate": "2024-12-31"
}
```

**NumericRangeFilter → QUANTITATIVE_NUMERICAL 类型**：
```
{
  "field": {"fieldCaption": "Sales"},
  "filterType": "QUANTITATIVE_NUMERICAL",
  "quantitativeFilterType": "RANGE",
  "min": 1000,
  "max": 5000
}
```

**TextMatchFilter → MATCH 类型**：
```
{
  "field": {"fieldCaption": "City"},
  "filterType": "MATCH",
  "contains": "北京"
}
```

**TopNFilter → TOP 类型**：
```
{
  "field": {"fieldCaption": "Product"},
  "filterType": "TOP",
  "howMany": 10,
  "fieldToMeasure": {"fieldCaption": "Sales"},
  "direction": "DESC"
}
```


### 7.4 查询构建流程

```
接收 SemanticQuery（字段已映射）
    │
    ▼
┌─────────────────────────────────────┐
│  1. 构建维度字段                     │
│     - 遍历 dimensions                │
│     - 处理日期粒度                   │
│     - 检查字段数据类型               │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. 构建度量字段                     │
│     - 遍历 measures                  │
│     - 添加聚合函数                   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. 构建计算字段（如果有）           │
│     - 先处理 LOD 字段                │
│     - 再处理表计算字段               │
│     - 表计算可引用 LOD 结果          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  4. 构建筛选器                       │
│     - 遍历 filters                   │
│     - 根据类型转换为 VizQL 格式      │
│     - 处理 STRING 类型日期字段       │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  5. 构建排序                         │
│     - 从字段的 sort 属性提取         │
│     - 按优先级排序                   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  6. 组装最终请求                     │
│     - 添加 datasource 信息           │
│     - 添加 rowLimit（如果有）        │
└─────────────────────────────────────┘
    │
    ▼
输出 VizQL API 请求
```

---

## 8. 数据模型

### 8.1 核心模型关系图

```
Step1Output
├── What
│   └── MeasureField[]
│       ├── field_name
│       ├── aggregation
│       ├── alias
│       └── sort
├── Where
│   ├── DimensionField[]
│   │   ├── field_name
│   │   ├── alias
│   │   ├── date_granularity
│   │   └── sort
│   └── Filter[]
│       ├── SetFilter
│       ├── DateRangeFilter
│       ├── NumericRangeFilter
│       ├── TextMatchFilter
│       └── TopNFilter
├── HowType (SIMPLE | COMPLEX)
├── Intent
│   ├── type
│   └── reasoning
└── Step1Validation

Step2Output（仅当 HowType=COMPLEX）
├── reasoning
├── Computation[]
│   ├── LOD 类型
│   │   ├── LOD_FIXED
│   │   ├── LOD_INCLUDE
│   │   └── LOD_EXCLUDE
│   └── 表计算类型
│       ├── RANK / DENSE_RANK
│       ├── RUNNING_TOTAL
│       ├── PERCENT_OF_TOTAL
│       ├── DIFFERENCE
│       └── PERCENT_DIFFERENCE
└── Step2Validation

SemanticQuery（最终输出）
├── dimensions[]
├── measures[]
├── computations[]
├── filters[]
└── row_limit
```

### 8.2 枚举类型汇总

**聚合类型 (AggregationType)**：SUM, AVG, COUNT, COUNTD, MIN, MAX, MEDIAN, STDEV, VAR

**日期粒度 (DateGranularity)**：YEAR, QUARTER, MONTH, WEEK, DAY, HOUR, MINUTE

**排序方向 (SortDirection)**：ASC, DESC

**筛选器类型 (FilterType)**：SET, DATE_RANGE, NUMERIC_RANGE, TEXT_MATCH, TOP_N

**文本匹配类型 (TextMatchType)**：CONTAINS, STARTS_WITH, ENDS_WITH, EXACT, REGEX

**计算复杂度 (HowType)**：SIMPLE, COMPLEX

**意图类型 (IntentType)**：DATA_QUERY, CLARIFICATION, GENERAL, IRRELEVANT

**排名风格 (RankStyle)**：COMPETITION, DENSE, UNIQUE

**相对位置 (RelativeTo)**：PREVIOUS, NEXT, FIRST, LAST

**窗口聚合 (WindowAggregation)**：SUM, AVG, MIN, MAX, COUNT


---

## 9. 路由决策逻辑

### 9.1 Step1 后路由

```
Step1 完成
    │
    ▼
检查意图类型
    │
    ├── GENERAL ────────────────→ END（返回元数据信息）
    │
    ├── CLARIFICATION ──────────→ END（返回澄清问题）
    │
    ├── IRRELEVANT ─────────────→ END（返回无法处理提示）
    │
    └── DATA_QUERY
            │
            ▼
        检查复杂度
            │
            ├── SIMPLE ─────────→ Pipeline（跳过 Step2）
            │
            └── COMPLEX ────────→ Step2
```

### 9.2 Step2 后路由

```
Step2 完成
    │
    ▼
检查自校验结果
    │
    ├── 校验通过 ───────────────→ Pipeline
    │
    └── 校验失败 ───────────────→ 重试或澄清
```

### 9.3 Pipeline 后路由

```
Pipeline 完成
    │
    ▼
检查执行结果
    │
    ├── 成功 ───────────────────→ END（返回查询结果）
    │
    ├── 需要澄清 ───────────────→ END（返回澄清信息）
    │
    └── 失败 ───────────────────→ 重试或自纠错
```

---

## 10. 状态管理

### 10.1 VizQLState 概述

VizQLState 是工作流的全局状态容器，在各节点间传递数据。

### 10.2 状态字段分类

**用户输入相关**：
- question：用户问题
- messages：对话历史（自动累积）

**意图分类相关**：
- intent_type：意图类型
- is_analysis_question：是否为数据分析问题
- clarification_question：需要澄清时的问题

**语义解析输出**：
- semantic_query：SemanticQuery 对象
- restated_question：重述的问题

**字段映射输出**：
- mapped_query：映射后的查询

**查询构建输出**：
- vizql_query：VizQL 查询请求

**执行输出**：
- query_result：查询结果

**洞察输出**：
- insights：洞察列表（自动累积）

**重规划相关**：
- replan_decision：重规划决策
- replan_count：当前重规划轮数
- max_replan_rounds：最大重规划轮数

**控制流相关**：
- current_stage：当前阶段
- execution_path：执行路径记录（自动累积）

**错误处理相关**：
- errors：错误记录列表（自动累积）
- warnings：警告记录列表（自动累积）

### 10.3 状态累积机制

以下字段使用自动累积，新值会追加到列表末尾：
- messages（对话消息）
- errors（错误记录）
- insights（洞察结果）
- execution_path（执行路径）

### 10.4 节点完成标志

每个节点完成后设置对应标志：
- semantic_parser_complete
- field_mapper_complete
- query_builder_complete
- execute_complete
- insight_complete
- replanner_complete


---

## 11. 上下文管理

### 11.1 WorkflowContext 概述

WorkflowContext 是统一的依赖容器，通过 RunnableConfig 传递给所有节点。

### 11.2 上下文字段

- **auth**：Tableau 认证上下文（token、domain、过期时间）
- **datasource_luid**：数据源 LUID
- **tableau_domain**：Tableau 域名（支持多环境）
- **data_model**：完整的数据模型
- **max_replan_rounds**：最大重规划轮数
- **user_id**：用户 ID
- **metadata_load_status**：元数据加载状态（cache/api）

### 11.3 上下文传递流程

```
WorkflowExecutor 启动
    │
    ▼
┌─────────────────────────────────────┐
│  1. 获取 Tableau 认证               │
│     - 调用 get_tableau_auth_async   │
│     - 获取 token 和过期时间          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. 加载数据模型                     │
│     - 先检查缓存                     │
│     - 未命中则调用 API               │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. 创建 WorkflowContext            │
│     - 组装所有依赖                   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  4. 创建 RunnableConfig             │
│     - 将 context 放入 configurable  │
└─────────────────────────────────────┘
    │
    ▼
传递给所有节点（节点通过 get_context_or_raise 获取）
```

### 11.4 认证刷新机制

- **过期检查**：is_auth_valid(buffer_seconds=60)，提前 60 秒判定为即将过期
- **自动刷新**：refresh_auth_if_needed() 在 Token 即将过期时自动刷新

---

## 12. 持久化存储

### 12.1 存储方案

使用 LangGraph 的 SqliteStore 实现持久化缓存。

**存储位置**：data/langgraph_store.db

**TTL 配置**：
- 默认 TTL：24 小时
- 读取时刷新 TTL
- 每小时清理过期数据

### 12.2 缓存命名空间

**数据模型缓存**：
- 命名空间：("data_model", datasource_luid)
- 内容：DataModel 对象

**维度层级缓存**：
- 命名空间：("dimension_hierarchy", datasource_luid)
- 内容：维度层级字典

**字段索引缓存**：
- 命名空间：("field_index", datasource_luid)
- 内容：RAG 向量索引数据

**字段映射缓存**：
- 命名空间：("field_mapping", datasource_luid)
- 内容：业务术语到技术字段的映射

### 12.3 DataModelCache 加载流程

```
请求数据模型
    │
    ▼
┌─────────────────────────────────────┐
│  1. 尝试从缓存获取                   │
│     - 检查命名空间是否存在            │
│     - 检查数据是否有效               │
└─────────────────────────────────────┘
    │
    ├── 命中且有效 ─────────────────→ 返回缓存数据
    │
    └── 未命中或无效
            │
            ▼
┌─────────────────────────────────────┐
│  2. 调用 API 加载数据模型            │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. 推断维度层级（如果需要）         │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  4. 存入缓存                         │
│     - 设置 TTL                       │
└─────────────────────────────────────┘
    │
    ▼
返回数据模型
```

### 12.4 FieldIndexCache 内容

- **metadata_hash**：元数据哈希（用于增量更新检测）
- **field_names**：字段名列表
- **chunks**：字段分块数据
- **vectors**：向量数据


---

## 13. 中间件

### 13.1 中间件概述

中间件在节点执行前后进行拦截处理，用于修复问题、校验输出、记录日志等。

### 13.2 PatchToolCallsMiddleware

**解决的问题**：
- LLM 生成了 tool_call，但执行被中断
- 工具执行失败但未正确处理
- 用户在工具执行完成前发送新消息

**处理流程**：

```
Agent 运行前
    │
    ▼
┌─────────────────────────────────────┐
│  1. 扫描消息历史                     │
│     - 找到所有 AIMessage 中的 tool_call │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. 检查是否有对应的 ToolMessage    │
│     - 根据 tool_call_id 匹配        │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. 修复悬空的 tool_call            │
│     - 插入占位符 ToolMessage        │
│     - 保持消息顺序一致性             │
└─────────────────────────────────────┘
    │
    ▼
继续执行 Agent
```

### 13.3 OutputValidationMiddleware

**校验时机**：
- after_model 钩子：校验 LLM 输出是否符合 Schema
- after_agent 钩子：校验最终状态是否包含必需字段

**校验流程**：

```
LLM 输出
    │
    ▼
┌─────────────────────────────────────┐
│  1. 提取 JSON                        │
│     - 支持 Markdown 代码块           │
│     - 支持纯 JSON                    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. JSON 格式校验                    │
│     - 检查是否为有效 JSON            │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. Pydantic Schema 校验            │
│     - 检查字段类型                   │
│     - 检查必填字段                   │
│     - 检查枚举值                     │
└─────────────────────────────────────┘
    │
    ├── 校验通过 ───────────────────→ 继续执行
    │
    └── 校验失败
            │
            ├── strict=True ────────→ 抛出异常
            │
            ├── retry_on_failure ───→ 触发重试
            │
            └── 宽松模式 ───────────→ 记录错误到 state
```

### 13.4 FilesystemMiddleware

**功能**：当查询结果过大时，自动保存到文件

**触发条件**：结果大小超过阈值

**处理流程**：
1. 检查结果大小
2. 超过阈值则保存到临时文件
3. 返回文件路径而非完整数据


---

## 14. 异常处理

### 14.1 异常类型层级

```
Exception
│
├── ValidationError（语义解析校验错误）
│   ├── message：错误消息
│   ├── original_output：原始 LLM 输出
│   └── step：失败步骤（step1/step2）
│
└── VizQLError（VizQL API 错误基类）
    ├── VizQLAuthError（401 认证错误）
    ├── VizQLValidationError（400 请求校验错误）
    ├── VizQLServerError（5xx 服务器错误）
    ├── VizQLRateLimitError（429 限流错误）
    ├── VizQLTimeoutError（408 超时错误）
    └── VizQLNetworkError（网络错误）
```

### 14.2 可重试判断

**可重试的错误**：
- VizQLServerError：服务器临时故障
- VizQLRateLimitError：限流，等待后重试
- VizQLTimeoutError：超时，可重试
- VizQLNetworkError：网络问题，可重试

**不可重试的错误**：
- VizQLAuthError：认证失败，需要重新登录
- VizQLValidationError：请求参数错误，需要修正

### 14.3 错误记录结构

每个错误记录包含：
- **node**：发生错误的节点名
- **error**：错误消息
- **type**：错误类型

### 14.4 错误处理流程

```
节点执行
    │
    ├── 成功 ───────────────────→ 更新 state，继续下一节点
    │
    └── 失败
            │
            ▼
        判断错误类型
            │
            ├── ValidationError
            │       │
            │       └─→ 携带原始输出，供 Observer 分析纠正
            │
            ├── VizQLError（可重试）
            │       │
            │       └─→ 记录错误，触发重试机制
            │
            └── VizQLError（不可重试）
                    │
                    └─→ 记录错误，路由到 END
```

### 14.5 自纠错流程

```
Execute 节点失败
    │
    ▼
检查 correction_count < max_attempts?
    │
    ├── 是
    │   │
    │   ▼
    │   ┌─────────────────────────────────────┐
    │   │  路由到 self_correction 节点        │
    │   │  - 分析错误原因                     │
    │   │  - 修正查询                         │
    │   │  - 重新执行                         │
    │   └─────────────────────────────────────┘
    │
    └── 否
        │
        ▼
    路由到 END，返回错误信息
```


---

## 附录：完整示例

### 示例1：简单查询

**用户问题**："各省份的销售额"

**Step1 处理**：

1. 问题重述："各省份的销售额是多少？"
2. 意图分类：DATA_QUERY（完整的数据查询）
3. 实体提取：
   - What：度量 = 销售额，聚合 = SUM
   - Where：维度 = 省份，筛选 = 无
4. 复杂度判定：SIMPLE（简单聚合）

**路由决策**：跳过 Step2，直接进入 Pipeline

**字段映射**：
- "销售额" → "Sales"
- "省份" → "Province"

**最终 VizQL 请求**：
```
fields: [
  {fieldCaption: "Province"},
  {fieldCaption: "Sales", function: "SUM"}
]
```

---

### 示例2：复杂查询（排名）

**用户问题**："各省份销售额排名"

**Step1 处理**：

1. 问题重述："各省份的销售额排名是多少？"
2. 意图分类：DATA_QUERY
3. 实体提取：
   - What：度量 = 销售额，聚合 = SUM
   - Where：维度 = 省份
4. 复杂度判定：COMPLEX（检测到"排名"关键词）

**路由决策**：进入 Step2

**Step2 处理**：

1. 分析：用户需要对销售额进行排名
2. 计算类型：RANK
3. 参数：target=销售额, partition_by=[], direction=DESC

**字段映射**：
- "销售额" → "Sales"
- "省份" → "Province"

**最终 VizQL 请求**：
```
fields: [
  {fieldCaption: "Province"},
  {fieldCaption: "Sales", function: "SUM"},
  {fieldCaption: "Sales", function: "SUM", tableCalculation: {
    tableCalcType: "RANK",
    dimensions: [],
    rankType: "COMPETITION",
    direction: "DESC"
  }}
]
```

---

### 示例3：复杂查询（LOD + 排名）

**用户问题**："按首次购买日期对客户进行排名"

**Step1 处理**：

1. 问题重述："按首次购买日期对客户进行排名"
2. 意图分类：DATA_QUERY
3. 实体提取：
   - What：度量 = 订单日期，聚合 = MIN
   - Where：维度 = 客户ID
4. 复杂度判定：COMPLEX（需要 LOD + 排名）

**Step2 处理**：

1. 分析：
   - 需要计算每个客户的首次购买日期（LOD_FIXED）
   - 然后对首次购买日期进行排名（RANK）
2. 计算列表（顺序重要）：
   - 第一步：LOD_FIXED(target=订单日期, dimensions=[客户ID], aggregation=MIN, alias=首次购买日期)
   - 第二步：RANK(target=首次购买日期, partition_by=[], direction=ASC)

**字段映射**：
- "订单日期" → "OrderDate"
- "客户ID" → "CustomerID"

**最终 VizQL 请求**：
```
fields: [
  {fieldCaption: "CustomerID"},
  {fieldCaption: "FirstPurchase", calculation: "{FIXED [CustomerID] : MIN([OrderDate])}"},
  {fieldCaption: "FirstPurchase", function: "SUM", tableCalculation: {
    tableCalcType: "RANK",
    dimensions: [],
    rankType: "COMPETITION",
    direction: "ASC"
  }}
]
```

---

### 示例4：带筛选的查询

**用户问题**："2024年北京和上海的月度销售额"

**Step1 处理**：

1. 问题重述："2024年北京和上海的月度销售额是多少？"
2. 意图分类：DATA_QUERY
3. 实体提取：
   - What：度量 = 销售额，聚合 = SUM
   - Where：
     - 维度 = 订单日期（粒度=MONTH）
     - 筛选1 = DateRangeFilter(field=订单日期, start=2024-01-01, end=2024-12-31)
     - 筛选2 = SetFilter(field=城市, values=[北京, 上海])
4. 复杂度判定：SIMPLE

**字段映射**：
- "销售额" → "Sales"
- "订单日期" → "Order Date"
- "城市" → "City"

**最终 VizQL 请求**：
```
fields: [
  {fieldCaption: "Order Date", function: "TRUNC_MONTH"},
  {fieldCaption: "Sales", function: "SUM"}
],
filters: [
  {field: {fieldCaption: "Order Date"}, filterType: "QUANTITATIVE_DATE", 
   quantitativeFilterType: "RANGE", minDate: "2024-01-01", maxDate: "2024-12-31"},
  {field: {fieldCaption: "City"}, filterType: "SET", 
   values: ["北京", "上海"], exclude: false}
]
```
