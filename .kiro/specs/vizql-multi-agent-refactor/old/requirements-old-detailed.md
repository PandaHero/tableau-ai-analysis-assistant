# VizQL多智能体查询与分析重构 - 需求文档

## 简介

本项目旨在重构现有的VizQL查询生成与结果分析逻辑，采用**7 Agent多智能体架构**和LangGraph编排，实现更智能、更灵活的业务数据分析能力。重点解决问题理解、字段选择、任务拆分、查询生成、结果分析、动态重规划等核心功能。

## 多智能体架构概述

本系统采用**7个专业化Agent + 6个纯代码组件**的架构设计，每个Agent职责单一、易于优化。

### 7个Agent（需要LLM）

**预处理Agent（1个）**：
1. **维度层级推断Agent（Dimension Hierarchy Agent）**
   - 职责：推断维度的层级关系和粒度
   - 执行时机：数据源首次访问时（结果缓存24小时）
   - 输出：维度层级信息（写入元数据）

**查询流程Agent（6个）**：
2. **问题理解Agent（Understanding Agent）**
   - 职责：理解用户意图、提取关键信息、评估问题复杂度
   - 输入：用户问题 + 对话历史
   - 输出：问题类型、时间范围、筛选条件、复杂度评估

3. **字段选择Agent（Field Selector Agent）**
   - 职责：从数据模型中选择正确的维度和度量
   - 输入：问题理解结果 + 增强元数据（包含维度层级）
   - 输出：维度列表、度量列表、字段选择理由

4. **任务拆分Agent（Task Decomposer Agent）**
   - 职责：将问题拆分为子任务、识别依赖关系
   - 输入：问题理解结果 + 字段选择结果 + VizQL查询能力
   - 输出：StructuredQuestionSpec列表（子任务）

5. **洞察Agent（Insight Agent）**
   - 职责：对单个子任务结果进行业务解读
   - 输入：查询结果（采样） + 统计报告
   - 输出：业务洞察、关键发现、异常解读

6. **重规划Agent（Replanner Agent）**
   - 职责：决定是否需要重规划、生成新问题
   - 输入：原始问题 + 所有轮次的分析结果
   - 输出：是否重规划、新问题、重规划理由

7. **总结Agent（Summarizer Agent）**
   - 职责：整合所有结果、生成最终报告
   - 输入：所有轮次的分析结果 + 合并数据
   - 输出：执行摘要、分析路径、后续建议

### 6个纯代码组件（不需要LLM）

1. **元数据管理器（Metadata Manager）**：获取和缓存数据源元数据
2. **查询构建器（Query Builder）**：根据Spec生成VizQL查询JSON（纯代码规则）
3. **查询执行器（Query Executor）**：调用VDS API执行查询
4. **统计检测器（Statistics Detector）**：客观的统计分析和异常检测
5. **数据合并器（Data Merger）**：智能合并多个查询结果
6. **任务调度器（Task Scheduler）**：并行执行、超时控制、失败处理

### 架构优势

1. **职责单一**：每个Agent只做一件事，易于理解和维护
2. **上下文可控**：单次LLM调用最大token ~8K（20%上下文），避免超限
3. **性能优化**：维度层级推断结果缓存24小时，不影响查询性能
4. **易于扩展**：可以独立优化每个Agent的提示词和策略
5. **符合最佳实践**：与ThoughtSpot、Power BI Copilot等主流产品对标

## 技术选型说明

### 前端：Vue 3 vs React

**选择Vue 3的理由：**
1. **渐进式框架**：Vue更容易上手，模板语法更直观，适合快速重构UI
2. **更好的TypeScript支持**：Vue 3原生支持TypeScript，类型推断更强
3. **组合式API（Composition API）**：与React Hooks类似，但更灵活，逻辑复用更清晰
4. **更小的包体积**：Vue 3运行时更轻量，适合嵌入式场景（Tableau Extension）
5. **更好的性能**：Vue 3的响应式系统基于Proxy，性能优于React的虚拟DOM diff
6. **官方生态完整**：Vue Router、Pinia（状态管理）、Vite（构建工具）官方维护，集成度高

**React的优势（但不适合本项目）：**
- 更大的社区和生态
- 更多的第三方组件库
- 但本项目需要完全自定义UI，不依赖现成组件库，Vue的灵活性更适合

**最终决策：使用Vue 3 + TypeScript + Vite**

### 后端：LangChain + LangGraph

**选择理由：**
1. **成熟的LLM编排框架**：LangChain提供丰富的工具和抽象
2. **图编排能力**：LangGraph支持复杂的多智能体工作流
3. **现有基础**：项目已使用LangChain和tableau_langchain，可直接扩展
4. **社区活跃**：持续更新，文档完善

## AI与代码的职责划分原则

本项目采用"AI做理解，代码做执行"的设计理念，明确区分AI和代码的职责边界：

### AI的职责（语义理解层）

AI负责所有需要语义理解、灵活决策和业务解读的任务：

1. **自然语言理解**：理解用户问题的业务意图、识别隐含需求、生成澄清问题
2. **字段理解与映射**：从完整数据模型中选择正确字段、理解字段关系和层级
3. **问题拆分与结构化**：将复杂问题拆分为子问题、识别依赖关系、评估复杂度
4. **智能决策与推荐**：决定是否重规划、生成后续问题推荐、选择重规划类型
5. **异常解读与洞察**：为统计异常提供业务解释、提取关键发现、生成业务洞察
6. **语义补全**：补全模糊的时间表达、筛选条件、聚合方式等

**AI的输出**：结构化的规格（Spec）、决策结果、分析报告，而非可执行代码或精确数据

### 代码的职责（确定性执行层）

代码负责所有需要精确性、稳定性和可预测性的任务：

1. **精确的查询生成**：基于AI的规格生成标准VizQL JSON，使用代码模板而非AI
2. **数据处理与计算**：数据合并、去重、聚合、排序等，使用Pandas/SQL等工具
3. **系统流程控制**：任务调度、并发控制、超时处理、重试机制，使用LangGraph编排
4. **统计检测**：异常检测（Z-score、IQR）、数据质量检查，使用统计方法
5. **验证与校验**：验证字段存在性、检查依赖关系、验证JSON结构
6. **性能优化**：缓存管理、查询合并、数据量估算、资源控制

**代码的输出**：可执行的查询语句、处理后的数据、客观的统计报告

### 协作模式

```
用户问题 → [AI理解] → 结构化规格 → [代码生成] → VizQL查询 → [代码执行] → 查询结果
         → [代码统计] → 统计报告 → [AI解读] → 业务洞察 → [AI决策] → 重规划建议
         → [代码验证] → [AI生成] → 新一轮规格 → ...
```

### 关键原则

1. **AI做"理解"，代码做"执行"**：AI负责语义理解和决策，代码负责精确执行
2. **AI做"生成规格"，代码做"生成代码"**：AI生成意图描述，代码生成查询语句
3. **AI做"分析"，代码做"检测"**：AI分析业务含义，代码执行客观检测
4. **AI做"推荐"，代码做"验证"**：AI推荐方向，代码验证可行性
5. **AI做"灵活决策"，代码做"确定性控制"**：AI处理不确定性，代码保证稳定性

## VizQL查询能力说明

本节说明VizQL Data Service的查询能力，帮助AI在问题拆分时做出正确决策。

### VizQL查询结构

一个完整的VizQL查询包含以下核心组件：

```json
{
  "datasource": {
    "datasourceLuid": "string"
  },
  "query": {
    "fields": [
      {
        "fieldCaption": "门店名称",
        "sortDirection": "ASC",
        "sortPriority": 1
      },
      {
        "fieldCaption": "销售额",
        "function": "SUM"
      },
      {
        "fieldCaption": "利润",
        "function": "SUM"
      }
    ],
    "filters": [
      {
        "filterType": "QUANTITATIVE_DATE",
        "fieldCaption": "订单日期",
        "quantitativeFilterType": "RANGE",
        "minDate": "2016-01-01",
        "maxDate": "2016-12-31"
      }
    ]
  }
}
```

### VizQL支持的查询能力

| 能力 | 说明 | 示例 |
|------|------|------|
| **多维度** | 一个查询可以包含多个维度字段 | [地区, 产品类别, 门店] |
| **多度量** | 一个查询可以包含多个度量字段 | [销售额, 利润, 订单量] |
| **多筛选** | 一个查询可以包含多个筛选条件 | [日期范围, 地区=北京, 销售额>1000] |
| **聚合函数** | 支持SUM、AVG、COUNT、MIN、MAX等 | SUM(销售额)、AVG(利润率) |
| **日期函数** | 支持YEAR、MONTH、DAY、TRUNC_YEAR等 | YEAR(订单日期)、MONTH(订单日期) |
| **计算字段** | 支持自定义计算表达式 | 利润率 = 利润 / 销售额 |
| **排序** | 支持多字段排序，指定优先级 | sortPriority: 1, 2, 3... |
| **TopN** | 支持TopNFilter限制结果数量 | Top 10门店 |

### Field类型详解

VizQL支持三种Field类型：

1. **Basic Field**（基础字段）
```json
{
  "fieldCaption": "门店名称",
  "sortDirection": "ASC",
  "sortPriority": 1
}
```

2. **Function Field**（函数字段）
```json
{
  "fieldCaption": "销售额",
  "function": "SUM",
  "sortDirection": "DESC",
  "sortPriority": 2
}
```

3. **Calculation Field**（计算字段）
```json
{
  "calculation": "SUM([销售额]) / SUM([订单量])",
  "fieldAlias": "平均客单价"
}
```

**重要约束**：
- 一个field不能同时有`function`和`calculation`
- 一个field不能同时有`fieldCaption`和`calculation`
- `sortPriority`在所有fields中必须唯一

### Filter类型详解

VizQL支持六种Filter类型：

1. **SetFilter**（集合筛选）
```json
{
  "filterType": "SET",
  "fieldCaption": "地区",
  "values": ["北京", "上海", "广州"],
  "exclude": false
}
```

2. **MatchFilter**（文本匹配）
```json
{
  "filterType": "MATCH",
  "fieldCaption": "产品名称",
  "contains": "手机"
}
```

3. **TopNFilter**（TopN筛选）
```json
{
  "filterType": "TOP",
  "fieldCaption": "门店名称",
  "howMany": 10,
  "direction": "TOP",
  "fieldToMeasure": {
    "fieldCaption": "销售额",
    "function": "SUM"
  }
}
```

4. **QuantitativeNumericalFilter**（数值范围）
```json
{
  "filterType": "QUANTITATIVE_NUMERICAL",
  "fieldCaption": "销售额",
  "quantitativeFilterType": "RANGE",
  "min": 1000,
  "max": 10000
}
```

5. **QuantitativeDateFilter**（日期范围）
```json
{
  "filterType": "QUANTITATIVE_DATE",
  "fieldCaption": "订单日期",
  "quantitativeFilterType": "RANGE",
  "minDate": "2016-01-01",
  "maxDate": "2016-12-31"
}
```

6. **RelativeDateFilter**（相对日期）
```json
{
  "filterType": "DATE",
  "fieldCaption": "订单日期",
  "relativeDateFilterType": "LAST",
  "periodType": "MONTH",
  "rangeN": 3
}
```

### 查询验证规则

代码在生成VizQL查询后，必须验证以下规则：

| 规则 | 说明 | 错误信息 |
|------|------|----------|
| 最少字段数 | 至少包含一个field | "The query must include at least one field" |
| 非空fieldCaption | fieldCaption不能为空 | "The query must not include any fields with an empty fieldCaption" |
| 无重复字段 | fieldCaption不能重复 | "The query must not include duplicate fields" |
| 唯一sortPriority | sortPriority不能重复 | "The query must not include duplicate sort priorities" |
| Function与Calculation互斥 | 不能同时有function和calculation | "The query must not include fields that contain both a function and a calculation" |
| 非负maxDecimalPlaces | maxDecimalPlaces必须≥0 | "maxDecimalPlaces value that is less than 0" |
| 无重复筛选 | 同一字段不能有多个filter | "The query must not include multiple filters for the following fields" |

### 问题拆分决策指南

基于VizQL的查询能力，AI在拆分问题时应遵循以下原则：

**不需要拆分的情况**（一个VizQL查询即可）：
- ✅ 多个度量 + 相同维度组合 + 相同时间段
  - 例："2016年各门店的销售额、利润和订单量"
- ✅ 多个维度 + 多个度量
  - 例："各地区各产品类别的销售额和利润"
- ✅ 多个筛选条件 + 单个时间段
  - 例："2016年北京和上海地区销售额超过1000的门店"

**需要拆分的情况**（需要多个VizQL查询）：
- ❌ 多个时间段对比（同比、环比）
  - 例："2016年和2015年各门店的销售额对比" → 拆分为2个查询
- ❌ 不同维度组合（先总体后明细）
  - 例："先看总体销售额，再看各地区明细" → 拆分为2个查询
- ❌ 计算依赖（需要先计算A再计算B）
  - 例："计算各门店销售额占比" → 先查总销售额，再查各门店销售额
- ❌ 不同筛选条件组合对比
  - 例："对比高价产品和低价产品的销售情况" → 拆分为2个查询

## 术语表

### 系统组件

- **System**: 指整个VizQL多智能体分析系统
- **Agent**: 需要LLM调用的智能组件，负责语义理解、决策和分析
- **Code Component**: 纯代码组件，负责确定性的执行和计算，不涉及LLM调用
- **LangGraph**: LangChain的图编排框架，用于构建多智能体工作流，提供状态管理和对话历史功能

### 7个Agent

- **Dimension Hierarchy Agent**: 维度层级推断Agent，推断维度的层级关系和粒度（预处理阶段，结果缓存24小时）
- **Understanding Agent**: 问题理解Agent，理解用户意图、提取关键信息、评估问题复杂度
- **Field Selector Agent**: 字段选择Agent，从数据模型中选择正确的维度和度量
- **Task Decomposer Agent**: 任务拆分Agent，将问题拆分为子任务、识别依赖关系
- **Insight Agent**: 洞察Agent，对单个子任务结果进行业务解读
- **Replanner Agent**: 重规划Agent，决定是否需要重规划、生成新问题
- **Summarizer Agent**: 总结Agent，整合所有结果、生成最终报告

### 6个纯代码组件

- **Metadata Manager**: 元数据管理器，获取和缓存数据源元数据
- **Query Builder**: 查询构建器，根据Spec生成VizQL查询JSON（纯代码规则，不用AI）
- **Query Executor**: 查询执行器，调用VDS API执行查询
- **Statistics Detector**: 统计检测器，客观的统计分析和异常检测
- **Data Merger**: 数据合并器，智能合并多个查询结果
- **Task Scheduler**: 任务调度器，并行执行、超时控制、失败处理

### 核心概念

- **VizQL**: Tableau的VizQL Data Service查询语言，支持多维度、多度量、多筛选的复杂查询
- **VDS**: VizQL Data Service，Tableau的数据查询服务
- **VizQL Query Capabilities**: VizQL查询能力，指VizQL支持的查询特性（多度量、多维度、计算字段、聚合函数等）
- **StructuredQuestionSpec**: 结构化问题规格，包含维度、度量、筛选、聚合、排序等要素
- **Dimension Hierarchy**: 维度层级，包含维度的类别、层级级别、粒度、父子关系等信息
- **Metadata API**: Tableau的元数据API，用于获取数据源信息
- **SSE**: Server-Sent Events，服务器推送事件，用于流式响应
- **Stage**: 执行阶段，同一stage内的任务可并行执行，不同stage顺序执行
- **Replan**: 重新规划，根据分析结果动态生成新一轮任务
- **Merge Policies**: 合并策略，定义如何对齐和合并多个子任务的查询结果
- **StatisticalReport**: 统计报告，代码生成的客观统计分析结果
- **AnalysisResult**: 分析结果，AI生成的业务洞察和建议
- **Prompt Template**: 提示词模板，存储在prompts.py中的文本规则
- **Token**: LLM的输入输出单位，Qwen3-32B上下文长度为40,960 tokens

## 文档导航

本需求文档采用**精简主文档 + 详细附录**的结构，便于快速查阅和深入研究。

### 主文档结构

- **简介**：项目概述和多智能体架构说明
- **技术选型**：前端（Vue 3）和后端（LangChain + LangGraph）选型理由
- **AI与代码职责划分**：明确AI和代码的边界
- **VizQL查询能力**：VizQL支持的查询特性和拆分决策指南
- **术语表**：核心概念和组件定义
- **需求**：7个Agent + 6个代码组件的核心需求（精简版）

### 详细附录（./appendix/）

每个需求的详细规格、验收标准、输入输出示例都在附录中：

- [Agent需求详细规格](./appendix/agent-requirements.md)
  - 需求0：维度层级推断Agent
  - 需求1：问题理解Agent
  - 需求2：字段选择Agent
  - 需求3：任务拆分Agent
  - 需求6：洞察Agent
  - 需求7：重规划Agent
  - 需求8：总结Agent

- [代码组件需求详细规格](./appendix/code-component-requirements.md)
  - 需求4：任务调度器
  - 需求5：数据合并器
  - 需求9：查询构建器
  - 需求10：查询执行器
  - 需求11：统计检测器
  - 需求12：元数据管理器

- [系统需求详细规格](./appendix/system-requirements.md)
  - 需求13：LangGraph工作流编排
  - 需求14：提示词模板管理
  - 需求15：前端UI重构

- [技术规格](./appendix/technical-specs.md)
  - VizQL查询能力详解
  - 数据模型定义
  - 缓存架构设计
  - 性能优化策略

---

## 需求

### 需求概览

本系统包含**7个Agent（需要LLM）+ 6个代码组件（纯代码）**：

**预处理Agent（1个）**：
- 需求0：维度层级推断Agent

**查询流程Agent（6个）**：
- 需求1：问题理解Agent
- 需求2：字段选择Agent
- 需求3：任务拆分Agent
- 需求6：洞察Agent
- 需求7：重规划Agent
- 需求8：总结Agent

**纯代码组件（6个）**：
- 需求4：任务调度器
- 需求5：数据合并器
- 需求9：查询构建器
- 需求10：查询执行器
- 需求11：统计检测器
- 需求12：元数据管理器

**系统需求（3个）**：
- 需求13：LangGraph工作流编排
- 需求14：提示词模板管理
- 需求15：前端UI重构

---

### 需求 0: 维度层级推断Agent

**用户故事:** 作为系统，我需要在数据源首次访问时推断维度的层级关系和粒度，为后续的字段选择提供支持

**执行时机**: 数据源首次访问时（结果缓存24小时）

**职责说明**: AI任务，需要LLM调用

#### 核心功能

1. **维度层级推断**：根据字段元数据、统计信息和数据样例，推断每个维度的：
   - 类别（category）：地理、时间、产品、客户等
   - 层级级别（level）：1=粗粒度、2=中粒度、3=细粒度
   - 父子关系（parent_dimension、child_dimension）
   - 置信度（level_confidence）

2. **缓存策略**：
   - 结果写入元数据的`dimension_hierarchy`字段
   - Redis缓存24小时
   - 支持手动刷新和调整

3. **Fallback机制**：
   - 如果LLM调用失败，使用基于unique_count的默认规则
   - 如果置信度<0.7，记录警告并使用fallback规则

#### 输入输出

**输入**（~5,500 tokens）：
- 维度字段列表 + 统计信息 + 数据样例（10行）

**输出**：
```json
{
  "dimension_hierarchy": {
    "地区": {
      "category": "地理",
      "category_detail": "地理-省级",
      "level": 1,
      "granularity": "粗粒度",
      "unique_count": 34,
      "parent_dimension": null,
      "child_dimension": "城市",
      "sample_values": ["北京", "上海", "广东"],
      "level_confidence": 0.95,
      "reasoning": "unique_count=34，对应中国省级行政区，属于粗粒度地理维度"
    }
  }
}
```

**性能**：
- LLM调用：每个数据源首次访问时1次
- 后续24小时内使用缓存
- 预估耗时：~2秒

**详细规格**: [需求0详细规格](./appendix/agent-requirements.md#需求0维度层级推断agent)

---

### 需求 1: 问题理解Agent

**用户故事:** 作为业务数据分析师，我希望系统能够理解我的问题意图，提取关键信息，评估问题复杂度

**职责说明**: AI任务，需要LLM调用

#### 核心功能

1. **问题有效性验证**：识别问题类型（数据分析 vs 操作指令 vs 定义查询）
2. **问题类型识别**：对比、趋势、排名、诊断、多维分解、占比、同环比
3. **关键信息提取**：时间范围、筛选条件、排序、TopN、时间粒度、聚合方式
4. **隐含需求识别**：同比需要两个时间段、占比需要先计算总计等
5. **问题复杂度评估**：Simple/Medium/Complex

#### 输入输出

**输入**（~1,550 tokens）：
- 用户问题 + 问题类型定义 + 提示词模板

**输出**：
```json
{
  "question_type": ["对比", "趋势"],
  "time_range": {"start": "2016-01-01", "end": "2016-12-31"},
  "filters": ["地区=北京"],
  "complexity": "Medium",
  "implicit_requirements": ["需要对比多个时间段"]
}
```

**性能**：
- LLM调用：每次查询1次
- 预估耗时：~2秒

**详细规格**: [需求1详细规格](./appendix/agent-requirements.md#需求1问题理解agent)

---

### 需求 2: 字段选择Agent

**用户故事:** 作为业务数据分析师，我希望系统能够从数据模型中选择正确的维度和度量，利用维度层级信息选择合适粒度的字段

**职责说明**: AI任务，需要LLM调用

#### 核心功能

1. **字段选择**：根据问题理解结果，从数据模型中选择正确的维度和度量
2. **利用维度层级**：根据问题要求（总体/明细），选择合适粒度的维度（level 1/2/3）
3. **字段验证**：验证字段存在性和类型匹配
4. **置信度评估**：评估字段选择的置信度（0-1）

#### 输入输出

**输入**（~8,250 tokens）：
- 用户问题 + 问题理解结果 + 精简元数据（字段名+描述） + 维度层级信息

**输出**：
```json
{
  "dimensions": ["地区", "产品类别"],
  "measures": ["销售额", "利润"],
  "field_selection_reason": "用户问题要求'各地区'，选择粗粒度的地区维度（level=1）",
  "field_confidence": 0.95,
  "suggested_drill_down": "城市"
}
```

**性能**：
- LLM调用：每次查询1次
- 预估耗时：~2秒
- **优化**：如果字段数>200，先用代码过滤（关键词匹配），再传给AI

**详细规格**: [需求2详细规格](./appendix/agent-requirements.md#需求2字段选择agent)

---

### 需求 3: 任务拆分Agent

**用户故事:** 作为业务数据分析师，我希望系统能够将复杂问题拆分为多个子任务，识别依赖关系，合理分配执行阶段

**职责说明**: AI任务，需要LLM调用

#### 核心功能

1. **拆分决策**：基于VizQL查询能力决定是否拆分（避免不必要的拆分）
2. **子任务生成**：生成StructuredQuestionSpec列表
3. **依赖关系识别**：识别子任务之间的依赖关系
4. **Stage分配**：同stage内的任务可并行执行，不同stage顺序执行
5. **优先级分配**：HIGH/MEDIUM/LOW

#### 输入输出

**输入**（~2,850 tokens）：
- 用户问题 + 问题理解结果 + 字段选择结果 + VizQL查询能力说明

**输出**：
```json
{
  "subtasks": [
    {
      "question_id": "q1",
      "question_text": "2016年各地区的销售额",
      "dims": ["地区"],
      "metrics": [{"field": "销售额", "function": "SUM"}],
      "stage": 1,
      "depends_on": [],
      "priority": "HIGH",
      "rationale": "VizQL支持在一个查询中包含多个度量，无需拆分"
    }
  ]
}
```

**性能**：
- LLM调用：每次查询1次
- 预估耗时：~2秒

**详细规格**: [需求3详细规格](./appendix/agent-requirements.md#需求3任务拆分agent)

---

### 需求 4: 任务调度器（纯代码组件）

**用户故事:** 作为业务数据分析师，我希望系统能够高效执行多个子任务，实时看到执行进度，即使部分任务失败也能获得可用的分析结果

**职责说明**: 纯代码组件，不涉及LLM调用

#### 核心功能

1. **任务调度**：按stage升序执行，同stage内并行执行（最多3个并发）
2. **超时控制**：动态超时时间（基于数据量和复杂度）
3. **失败处理**：智能重试（指数退避）、降级策略、部分失败处理
4. **进度反馈**：通过SSE实时推送执行进度
5. **资源监控**：监控内存、CPU、数据库连接数

**性能**：
- 并发数：最多3个
- 超时时间：30-120秒（动态调整）
- 重试次数：最多2次

**详细规格**: [需求4详细规格](./appendix/code-component-requirements.md#需求4任务调度器)

---

### 需求 5: 数据合并器（纯代码组件）

**用户故事:** 作为业务数据分析师，我希望系统能够智能合并多个子任务的查询结果，自动处理数据对齐、补全和计算，输出高质量、易理解的分析数据

**职责说明**: 纯代码组件，不涉及LLM调用

#### 核心功能

1. **合并策略选择**：Union/Join/Append/Pivot/Hierarchical（基于代码规则）
2. **数据对齐与补全**：时间序列补点、维度组合补全
3. **数据去重与清洗**：检测重复记录、异常值、空值处理
4. **聚合计算**：总计、小计、平均值、占比、排名、累计
5. **数据质量评分**：完整性、一致性、准确性、时效性

**性能**：
- 合并耗时：~1秒（取决于数据量）
- 数据质量评分：0-1

**详细规格**: [需求5详细规格](./appendix/code-component-requirements.md#需求5数据合并器)

---

### 需求 6: 洞察Agent

**用户故事:** 作为业务数据分析师，我希望系统能够对查询结果进行业务解读，识别关键发现和异常，提供行动建议

**职责说明**: AI任务，需要LLM调用

#### 核心功能

1. **数据解读**：理解查询结果的业务含义
2. **异常分析**：为统计异常（由代码检测）提供业务解释
3. **洞察生成**：提取业务洞察、生成行动建议
4. **后续建议**：建议后续分析方向

#### 输入输出

**输入**（~4,050 tokens）：
- 子任务问题 + 数据样本（智能采样，最多30行） + 统计报告

**输出**：
```json
{
  "key_findings": ["华东地区销售额最高，但利润率偏低"],
  "anomalies": ["西北地区利润率异常高（可能是促销）"],
  "insights": ["建议优化华东地区的成本结构"],
  "next_steps": ["深入分析华东地区各产品类别的利润率"]
}
```

**性能**：
- LLM调用：每个子任务1次（可并行）
- 预估耗时：~2秒/任务

**详细规格**: [需求6详细规格](./appendix/agent-requirements.md#需求6洞察agent)

---

### 需求 7: 重规划Agent

**用户故事:** 作为业务数据分析师，我希望系统能够根据当前分析结果智能推荐后续问题，自动发现异常并深入分析，实现连续的探索式分析

**职责说明**: AI任务，需要LLM调用

#### 核心功能

1. **完成度评估**：评估当前分析是否充分回答了原始问题
2. **异常识别**：识别值得深入的异常和趋势
3. **重规划决策**：决定是否需要重规划
4. **新问题生成**：如果需要重规划，生成新问题

#### 输入输出

**输入**（~5,250 tokens）：
- 原始问题 + 问题理解结果 + 数据摘要（不是完整数据） + 关键发现摘要

**输出**：
```json
{
  "should_replan": true,
  "replan_reason": "发现华东地区利润率异常低，需要深入分析",
  "new_question": "华东地区各产品类别的利润率分别是多少？",
  "replan_type": "drill_down"
}
```

**性能**：
- LLM调用：每轮1次
- 预估耗时：~2秒
- 最多重规划3轮

**详细规格**: [需求7详细规格](./appendix/agent-requirements.md#需求7重规划agent)

---

### 需求 8: 总结Agent

**用户故事:** 作为业务数据分析师，我希望系统能够整合所有结果，生成结构化、易理解的分析报告

**职责说明**: AI任务，需要LLM调用

#### 核心功能

1. **结果整合**：去重和排序关键发现
2. **执行摘要生成**：一句话回答原始问题
3. **分析路径回顾**：展示分析思路和过程
4. **后续探索建议**：推荐深入分析方向

#### 输入输出

**输入**（~4,050 tokens）：
- 原始问题 + 关键发现摘要（去重后） + 重规划历史

**输出**：
```json
{
  "executive_summary": "2016年华东地区销售额最高但利润率偏低，主要原因是电子产品类别的价格竞争激烈",
  "analysis_path": ["总体对比", "异常发现", "深入分析", "根因诊断"],
  "next_suggestions": ["分析华东地区的竞争对手策略", "评估价格调整的可行性"]
}
```

**性能**：
- LLM调用：整个分析流程结束时1次
- 预估耗时：~2秒

**详细规格**: [需求8详细规格](./appendix/agent-requirements.md#需求8总结agent)
   - 字段列表（fieldName、fieldCaption、description）
   - 字段类型（dataType：STRING/INTEGER/REAL/DATE/DATETIME/BOOLEAN）
   - 字段角色（role：dimension/measure）
   - 字段统计信息（unique_count、sample_values、min/max值）
   - 字段关系（parent_dimension、child_dimension、related_fields）
   - 字段层级信息（category、level、granularity）
   - 数据时间范围（最早日期、最新日期）
5. THE System SHALL 获取数据源的基本统计信息：
   - 总字段数量
   - 维度数量和度量数量
   - 数据源大小和复杂度指标
6. THE System SHALL 支持通过数据源名称查找LUID，支持以下匹配策略：
   - 精确匹配：完全匹配数据源名称
   - 模糊匹配：部分匹配数据源名称
   - 去括号匹配：去除括号后匹配（如"Sales (Live)" → "Sales"）
7. THE System SHALL 根据字段的dataType将字段分类为维度（dimensions）和度量（measures）
8. THE System SHALL 将元数据注入到提示词中，约束LLM的字段选择
9. THE System SHALL 缓存元数据以减少API调用次数：
   - 缓存key: datasource_luid
   - 缓存有效期: 1小时
   - 缓存失效策略：手动刷新或超时自动失效

##### 1.2a 维度层级动态判断（AI辅助，合并原需求18）

10. WHEN System获取数据源元数据后，THE System SHALL 使用LLM根据字段元数据、数据统计信息和少量数据样例（最多10行）动态判断维度层级
11. THE System SHALL 调用DIMENSION_HIERARCHY_INFERENCE_TEMPLATE模板，输入以下信息：
    - 字段元数据（fieldName、fieldCaption、description、dataType、role）
    - 字段统计信息（unique_count、min/max值）
    - 数据样例（sample_values，最多10个唯一值）
    - 字段关系提示（如果元数据中有parent_dimension、child_dimension信息）
12. THE System SHALL 为每个维度生成层级信息，包含以下字段：
    - **category**: 维度类别（由LLM智能推断，输出标准化类别名称）
      - 标准类别参考列表：["地理", "时间", "产品", "客户", "组织", "财务", "其他"]
      - LLM应该将推断的类别映射到最接近的标准类别
      - 如果无法映射，使用"其他"类别，并在category_detail中记录具体类别
    - **category_detail**: 详细类别描述（如"地理-国家"、"地理-城市"、"时间-年"、"时间-月"）
    - **level**: 层级级别（数字，越小越粗粒度）
      - 计算规则：主要基于unique_count，辅以LLM的语义理解
      - unique_count < 10 → level=1（粗粒度）
      - 10 <= unique_count < 100 → level=2（中粒度）
      - unique_count >= 100 → level=3（细粒度）
      - LLM可以根据语义调整±1个level（如"国家"即使unique_count=200也应该是level=1）
    - **granularity**: 粒度描述（"粗粒度" | "中粒度" | "细粒度"）
    - **unique_count**: 唯一值数量（来自统计信息）
    - **parent_dimension**: 父维度（更粗粒度，LLM根据语义推断）
    - **child_dimension**: 子维度（更细粒度，LLM根据语义推断）
    - **sample_values**: 示例值列表（最多10个代表性值）
    - **level_confidence**: 层级判断的置信度（0-1）
      - 基于数据样例的完整性、字段名称的明确性、统计信息的可靠性
    - **reasoning**: LLM的推理过程（为什么这样判断，用于调试和优化）
13. THE System SHALL 允许多个维度具有相同的level值：
    - 例如："地区"和"产品类别"都可以是level=1（同级维度）
    - 例如："城市"和"产品子类"都可以是level=2
    - 这是正常的，因为不同category的维度可以有相同的粒度
14. WHEN 两个维度的unique_count相同，THE System SHALL 允许它们具有相同的level值
15. IF LLM判断的level_confidence小于0.7，THEN System SHALL 记录警告日志并使用fallback规则：
    - 纯粹基于unique_count计算level（见第12条的计算规则）
    - parent_dimension和child_dimension设为null
    - category设为"其他"
16. IF 维度层级判断失败（LLM调用失败或返回无效结果），THEN System SHALL 使用默认规则：
    - 根据unique_count计算level（见第12条）
    - 根据字段名称关键词推断category：
      - 包含"地区"、"省"、"市"、"国家" → "地理"
      - 包含"年"、"月"、"日"、"季度" → "时间"
      - 包含"产品"、"类别"、"品牌" → "产品"
      - 包含"客户"、"用户"、"会员" → "客户"
      - 其他 → "其他"
    - parent_dimension和child_dimension设为null
    - level_confidence设为0.5
17. THE System SHALL 缓存维度层级信息：
    - 缓存key: datasource_luid + "_hierarchy"
    - 缓存有效期: 1小时
    - 与元数据缓存同步失效
18. THE System SHALL 提供维度层级的可视化展示（在前端）：
    - 树形结构展示维度层级关系
    - 标注每个维度的level和unique_count
    - 支持用户手动调整层级关系（覆盖AI判断）

##### 1.3 一次性问题理解与拆分（AI负责）

6. THE System SHALL 将以下信息输入MOTHER_PLANNER_AND_DECOMPOSER模板（一次性完成）：
   - 用户问题（original_question）
   - 数据源完整元数据（metadata）
   - 数据源统计信息（metadata_stats）
   - VizQL查询能力说明（vizql_capabilities）
7. THE System SHALL 通过AI一次性完成以下任务：
    - **评估问题复杂度**（Simple/Medium/Complex）
    - 识别问题类型（对比、趋势、排名、诊断、多维分解、占比、同环比）
    - 提取关键约束条件（时间范围、筛选条件、排序、TopN等）
    - 识别隐含需求（如同比需要两个时间段）
    - 从数据模型中选择字段（dims、metrics、filter_fields）
    - **基于VizQL查询能力决定是否拆分**（避免不必要的拆分）
    - 拆分为结构化的子问题列表（StructuredQuestionSpec）
    - 识别子任务之间的依赖关系和stage分配
7a. THE System SHALL 在MOTHER_PLANNER_AND_DECOMPOSER模板中明确说明VizQL的查询能力，指导AI避免不必要的拆分：
    - **多度量支持**：一个VizQL查询可以同时包含多个度量字段（metrics），无需为每个度量创建单独的子任务
    - **多维度支持**：一个VizQL查询可以同时包含多个维度字段（dims），支持多维分组
    - **多筛选支持**：一个VizQL查询可以同时应用多个筛选条件（filters），包括维度筛选和度量筛选
    - **排序和TopN**：一个VizQL查询可以同时指定排序（sortDirection、sortPriority）和TopN限制
    - **计算字段**：VizQL支持在查询中定义计算字段（calculation），可以进行复杂的计算
    - **聚合函数**：VizQL支持多种聚合函数（SUM、AVG、COUNT、MIN、MAX等）
    - **日期函数**：VizQL支持日期函数（YEAR、MONTH、DAY、TRUNC_YEAR等）
7b. THE System SHALL 要求AI在拆分前评估是否真的需要拆分：
    - **不需要拆分的情况**：
      - 问题只涉及单个时间段、单个维度组合、多个度量 → 一个查询即可
      - 例如："2016年各门店的利润和销售额分别是多少？" → 不拆分，一个查询包含[门店]维度和[利润、销售额]两个度量
      - 例如："各地区各产品类别的销售额和订单量" → 不拆分，一个查询包含[地区、产品类别]维度和[销售额、订单量]度量
    - **需要拆分的情况**：
      - 问题涉及多个时间段对比（如同比、环比） → 拆分为多个查询，每个查询对应一个时间段
      - 问题涉及不同的维度组合（如先看总体，再看明细） → 拆分为多个查询，每个查询对应一个维度组合
      - 问题涉及复杂的计算依赖（如需要先计算A，再基于A计算B） → 拆分为多个查询，按依赖关系排序
      - 问题涉及不同的筛选条件组合（如对比不同条件下的结果） → 拆分为多个查询，每个查询对应一个筛选条件组合
7c. THE System SHALL 在拆分理由（rationale）中明确说明为什么拆分或为什么不拆分：
    - 如果不拆分，说明"VizQL支持在一个查询中包含多个度量/维度，无需拆分"
    - 如果拆分，说明"需要拆分的原因：时间段对比/维度组合不同/计算依赖/筛选条件不同"
8. THE System SHALL 要求AI根据以下因素评估问题复杂度：
    - 子问题数量（1个=Simple，2-5个=Medium，5个以上=Complex）
    - 依赖关系复杂度（无依赖=Simple，简单依赖=Medium，复杂依赖=Complex）
    - 字段明确程度（明确=Simple，部分明确=Medium，不明确=Complex）
    - 预期重规划轮次（0轮=Simple，1-2轮=Medium，3轮以上=Complex）
9. THE System SHALL 输出以下结构化结果：
    - **问题复杂度**（complexity: Simple/Medium/Complex）
    - **复杂度评估理由**（complexity_reason）
    - **问题类型**（question_type）
    - **原始意图**（original_intent）
    - **子任务列表**（subtasks），每个子任务包含：
      - question_id：子问题唯一标识
      - question_text：子问题的自然语言描述
      - dims：维度列表（fieldName）
      - metrics：度量列表（fieldName + 聚合方式）
      - calculated_metrics：计算字段列表（如"增长率"、"占比"）
      - filters：维度/度量筛选条件
      - date_filters：日期筛选条件
      - order_by：排序字段与方向
      - limit：TopN限制（可选）
      - grain：时间粒度（可选）
      - stage：执行阶段编号
      - depends_on：依赖的子任务ID列表
      - rationale：拆分理由和预期目标
      - estimated_rows：预估结果行数
      - priority：优先级（HIGH/MEDIUM/LOW）
      - field_selection_reason：字段选择理由
    - **分析计划摘要**（plan_summary）
    - **session_id和plan_id**

##### 1.4 结果验证与修正（代码负责）

10. THE System SHALL 使用代码（而非AI）验证AI输出的结果：
    - 所有字段是否在数据模型中存在
    - 字段组合是否合理（维度+度量、筛选条件+字段类型）
    - 子任务之间的依赖关系是否形成循环
    - 子任务数量是否超过Max_Subtasks_Per_Round（默认10）
11. THE System SHALL 计算字段选择的置信度（field_confidence，0-1）
12. IF 验证失败或置信度低于0.7，THEN THE System SHALL 采取以下策略之一：
    - 要求AI重新生成（最多重试2次）
    - 提示用户澄清问题
    - 切换到两步方案（fallback机制，见1.6）
13. THE System SHALL 计算拆分后的总预估token数量（基于estimated_rows和字段数量）
14. THE System SHALL 获取模型的最大上下文长度：
    - 优先从模型配置中读取max_tokens
    - 如果模型配置中没有，使用环境变量API_MAX_TOKENS
    - 如果都没有，使用默认值128000
15. IF 总预估token数量超过模型最大上下文的80%，THEN THE System SHALL 建议添加筛选条件或调整拆分策略

##### 1.5 复杂度处理策略

15. THE System SHALL 根据AI评估的问题复杂度采取不同的处理策略：
    - **Simple问题**：使用一次性方案，通常不需要重规划
    - **Medium问题**：使用一次性方案，通过重规划机制（需求4）完善细节，预期1-2轮重规划
    - **Complex问题**：切换到两步方案（Fallback机制）
16. THE System SHALL 在一次性方案的输出中包含replan_suggestion字段，指导后续重规划：
    - Simple问题：replan_suggestion = "no_replan_needed"
    - Medium问题：replan_suggestion = "may_need_replan"，并提供初步的重规划方向
    - Complex问题：replan_suggestion = "switch_to_two_step"

##### 1.6 Fallback机制：两步方案（复杂问题）

17. IF 满足以下任一条件，THEN THE System SHALL 切换到两步方案：
    - AI评估的问题复杂度为Complex
    - 数据模型字段数超过500
    - 一次性方案的置信度低于0.7
    - 一次性方案重试2次仍失败
18. WHEN 使用两步方案，THE System SHALL 执行以下步骤：
    - **步骤1：问题理解与复杂度评估**
      - 调用MOTHER_PLANNER模板
      - 输出：问题类型、复杂度、约束条件、隐含需求、分析策略
    - **步骤2：结构化拆分与字段选择**
      - 调用MOTHER_DECOMPOSER模板
      - 基于步骤1的结果和数据模型元数据
      - 输出：结构化子任务列表（包含字段选择）
19. THE System SHALL 记录使用的方案类型（one_step或two_step）供后续分析

##### 1.7 输出与记录

20. THE System SHALL 为分析计划分配唯一的session_id和plan_id
21. THE System SHALL 将以下信息记录到会话上下文中：
    - 原始问题（original_question）
    - 原始意图（original_intent）
    - 问题类型（question_type）
    - 问题复杂度（complexity）
    - 重规划建议（replan_suggestion）
    - 子任务列表（subtasks）
    - 使用的方案类型（one_step或two_step）
    - 字段选择置信度（field_confidence）
22. THE System SHALL 输出严格的JSON格式，不包含多余文本

### 需求 2: 任务调度与并行执行（纯代码，无AI）

**用户故事:** 作为业务数据分析师，我希望系统能够高效执行多个子任务，实时看到执行进度，即使部分任务失败也能获得可用的分析结果

**职责说明**：本需求是纯代码逻辑，不涉及AI调用，不属于Agent职责

#### 验收标准

##### 2.1 任务调度策略

1. THE System SHALL 按stage升序依次执行任务组，确保依赖关系正确
2. WITHIN 同一stage，THE System SHALL 按优先级（priority）排序任务：HIGH > MEDIUM > LOW
3. THE System SHALL 并行执行同stage内的任务，并发数不超过Parallel_Upper_Limit环境变量（默认3）
4. THE System SHALL 使用ThreadPoolExecutor实现并行执行
5. THE System SHALL 为每个子任务分配唯一的execution_id
6. THE System SHALL 在开始执行前，生成执行计划（execution_plan），包括：
   - 总任务数量
   - 各stage的任务分布
   - 预估总执行时间
   - 关键路径（critical path）分析

##### 2.2 智能超时控制

7. THE System SHALL 为每个子任务设置动态超时时间，基于以下因素：
   - 预估数据量（estimated_rows）
   - 查询复杂度（维度数量、计算字段数量）
   - 历史执行时间（相似查询的平均耗时）
8. THE System SHALL 使用以下默认超时策略：
   - 简单查询（estimated_rows < 1000）：30秒
   - 中等查询（1000 <= estimated_rows < 10000）：60秒
   - 复杂查询（estimated_rows >= 10000）：120秒
   - 如果有历史数据，使用历史平均耗时 × 1.5作为超时时间
9. IF 子任务执行超时，THEN THE System SHALL 采取以下策略：
   - 尝试简化查询（如添加筛选条件、减少维度）
   - 如果简化失败，取消该任务并标记为timeout状态
   - 记录超时原因和查询特征，供后续优化
10. THE System SHALL 监控系统资源使用率（内存、CPU、数据库连接数）
11. IF 资源使用率超过80%，THEN THE System SHALL 采取以下措施：
    - 降低并发数（从3降到2或1）
    - 暂停新任务提交，等待当前任务完成
    - 如果资源持续紧张，建议用户添加筛选条件

##### 2.3 智能失败处理与重试

12. WHEN 子任务执行失败，THE System SHALL 智能判断失败类型和原因：
    - **临时错误**（网络抖动、数据库繁忙、超时）：可重试
    - **数据问题**（数据量过大、查询超时）：可优化后重试
    - **永久错误**（语法错误、权限不足、字段不存在）：不可重试
    - **业务逻辑错误**（筛选条件冲突、计算字段错误）：需要修正
13. IF 失败类型为临时错误，THEN THE System SHALL 自动重试，最多重试Max_Retry_Times次（默认2次）
14. THE System SHALL 使用指数退避策略（exponential backoff）：第1次重试等待2秒，第2次等待4秒
15. IF 失败类型为数据问题，THEN THE System SHALL 尝试优化查询：
    - 添加筛选条件（基于TopN或时间范围）
    - 减少维度数量（移除非核心维度）
    - 简化计算字段
    - 如果优化成功，重新执行优化后的查询
16. IF 重试和优化均失败，THEN THE System SHALL 标记该子任务为failed状态
17. THE System SHALL 继续执行其他子任务，不因单个任务失败而中断整体流程
18. THE System SHALL 记录失败任务的详细信息：
    - 失败类型（error_type）
    - 错误消息（error_message）
    - 堆栈跟踪（stack_trace）
    - 失败的查询语句（failed_query）
    - 重试次数和优化尝试
    - 失败时间和执行耗时

##### 2.4 部分失败处理与降级策略

19. WHEN 某个stage内有子任务失败，THE System SHALL 智能评估影响范围和是否继续执行：
    - IF 失败任务为HIGH优先级且是核心问题，THEN 评估是否有替代方案
    - IF 失败任务为HIGH优先级且无替代方案，THEN 停止后续stage执行，返回已完成的结果
    - IF 失败任务为MEDIUM/LOW优先级，THEN 继续执行后续stage
    - IF 失败任务被其他stage的任务依赖（depends_on），THEN 跳过依赖任务或尝试替代方案
20. THE System SHALL 提供智能降级策略：
    - **缓存降级**：如果有历史缓存数据，返回缓存结果并标注时效性
    - **简化降级**：简化查询条件（如减少维度、缩小时间范围）后重试
    - **近似降级**：使用近似算法或采样数据提供估算结果
    - **部分降级**：返回部分维度或部分时间段的结果
21. THE System SHALL 在最终结果中清晰标注：
    - 哪些子任务成功、哪些失败
    - 失败原因和影响范围
    - 是否使用了降级策略
    - 结果的完整性评分（0-1，表示结果覆盖原始问题的程度）
22. THE System SHALL 为用户提供失败任务的修复建议：
    - 如果是数据量问题，建议添加筛选条件
    - 如果是权限问题，建议联系管理员
    - 如果是字段问题，建议检查数据源配置

##### 2.5 任务取消与中断处理

23. THE System SHALL 支持用户主动取消正在执行的任务
24. WHEN 收到取消请求，THE System SHALL 采取以下措施：
    - 立即停止所有未开始的子任务
    - 尝试优雅停止正在执行的子任务（发送中断信号）
    - 如果5秒内无法停止，强制终止任务
    - 清理已分配的资源（线程、内存、数据库连接）
25. THE System SHALL 返回取消时的状态信息：
    - 已完成的子任务结果
    - 正在执行但被中断的任务列表
    - 未开始的任务列表
    - 取消时间和原因
26. THE System SHALL 支持部分取消：
    - 用户可以取消特定的子任务
    - 用户可以取消特定的stage
    - 其他任务继续执行

##### 2.6 执行结果收集与质量评估

27. THE System SHALL 收集每个子任务的详细执行结果，包括：
    - **execution_id**: 执行ID
    - **question_id**: 子问题ID
    - **status**: 执行状态（success/failed/timeout/cancelled/degraded）
    - **vizql_query**: 生成的VDS查询JSON
    - **data_rows**: 查询结果数据行
    - **row_count**: 结果行数
    - **execution_time**: 执行耗时（毫秒）
    - **start_time**: 开始时间
    - **end_time**: 结束时间
    - **retry_count**: 重试次数
    - **optimization_applied**: 是否应用了查询优化
    - **degradation_strategy**: 使用的降级策略（如果有）
    - **error_info**: 错误信息（如果失败）
    - **rule_notes**: 使用的规则说明
    - **data_quality_score**: 数据质量评分（0-1）
28. THE System SHALL 评估每个子任务结果的质量：
    - **完整性**：结果是否完整（是否被截断、是否使用了降级）
    - **准确性**：结果是否准确（是否有异常值、是否符合预期）
    - **时效性**：结果是否最新（是否使用了缓存）
    - **可信度**：结果的可信程度（基于数据源质量、查询复杂度）
29. THE System SHALL 在所有子任务完成（或失败）后，生成stage执行摘要：
    - 成功任务数量和失败任务数量
    - 平均执行时间和最长执行时间
    - 总数据行数和总数据量
    - 整体质量评分
30. THE System SHALL 在所有子任务完成后，再进入下一个stage

##### 2.7 实时进度反馈与用户体验

31. THE System SHALL 实时计算和推送执行进度，提供以下信息：
    - **整体进度**：completed_tasks / total_tasks（百分比）
    - **当前stage进度**：当前stage的完成情况
    - **预计剩余时间**：基于已完成任务的平均耗时和剩余任务数量
    - **当前执行状态**：正在执行哪些任务
32. THE System SHALL 通过SSE推送以下事件类型：
    - **execution_started**: 开始执行，包含执行计划
    - **stage_started**: 开始执行某个stage
    - **task_started**: 开始执行某个子任务
    - **task_progress**: 子任务执行进度（如果查询支持进度报告）
    - **task_completed**: 子任务完成，包含结果摘要
    - **task_failed**: 子任务失败，包含错误信息
    - **stage_completed**: stage完成，包含stage摘要
    - **execution_completed**: 全部执行完成
    - **execution_cancelled**: 执行被取消
33. THE System SHALL 在进度事件中包含用户友好的信息：
    - 当前正在做什么（如"正在查询北京地区的销售数据..."）
    - 已经完成了什么（如"已完成3个地区的数据查询"）
    - 接下来要做什么（如"接下来将分析销售趋势"）
    - 如果有延迟，说明原因（如"数据量较大，查询需要更多时间"）
34. THE System SHALL 提供可视化的进度指示：
    - 进度条（百分比）
    - 时间线（已完成的stage和正在执行的stage）
    - 任务状态图（成功/失败/进行中）
35. THE System SHALL 在执行过程中提供交互能力：
    - 用户可以查看详细的执行日志
    - 用户可以暂停/恢复执行
    - 用户可以调整并发数
    - 用户可以跳过失败的任务继续执行

##### 2.8 性能优化与缓存

36. THE System SHALL 实现智能查询缓存机制：
    - 缓存最近执行的查询结果（基于查询指纹）
    - 缓存有效期根据数据更新频率动态调整
    - 如果缓存命中，直接返回缓存结果并标注缓存时间
37. THE System SHALL 实现查询结果预取（Prefetching）：
    - 根据问题类型预测可能需要的后续查询
    - 在空闲时预先执行预测的查询
    - 如果预测准确，后续查询可以直接使用预取结果
38. THE System SHALL 实现查询合并优化：
    - 识别相似的查询（如只有筛选条件不同）
    - 合并为一个更大的查询，然后在内存中拆分结果
    - 减少数据库查询次数
39. THE System SHALL 记录执行统计信息，用于持续优化：
    - 各类查询的平均执行时间
    - 失败率和失败原因分布
    - 缓存命中率
    - 资源使用情况
    - 用户取消率和取消原因

### 需求 3: 结果合并与数据整形（纯代码，无AI）

**用户故事:** 作为业务数据分析师，我希望系统能够智能合并多个子任务的查询结果，自动处理数据对齐、补全和计算，输出高质量、易理解的分析数据

**职责说明**：本需求是纯代码逻辑，不涉及AI调用
- **代码职责**：合并策略选择、数据对齐、去重、清洗、聚合计算、排序、质量检查
- **理由**：
  - 字段命名：使用代码规则（如"当期_销售额"、"上期_销售额"），不需要AI
  - 公共维度识别：查询语句中的维度字段名称是确定的，直接匹配即可，不需要AI

#### 验收标准

##### 3.1 智能合并策略选择（代码规则决定）

1. WHEN 所有子任务执行完成，THE System SHALL 使用代码规则（而非AI）分析子任务的维度结构和问题类型，确定性地选择合并策略：
   - **Union（上下拼接）**：维度结构相同或兼容，直接拼接（如多个地区的数据）
   - **Join（横向连接）**：维度结构不同但有公共维度，按公共维度连接（如销售数据+成本数据）
   - **Append（追加）**：时间序列数据，按时间顺序追加
   - **Pivot（透视）**：需要行列转换的场景（如对比分析）
   - **Hierarchical（层级）**：有父子关系的数据（如地区→城市→门店）
2. THE System SHALL 使用以下代码规则决定合并策略：
   - IF 所有子任务的维度列表相同 → Union
   - IF 子任务有公共维度且问题类型为"对比" → Join
   - IF 子任务的时间范围不同且连续 → Append
   - IF 问题类型为"同比"或"环比" → Join（按维度连接不同时间段）
   - IF 子任务的维度存在层级关系 → Hierarchical
   - ELSE → Union（默认策略）
3. THE System SHALL 在合并前验证数据兼容性：
   - 字段类型是否匹配
   - 数值范围是否合理
   - 时间粒度是否一致
   - 维度值域是否重叠
4. IF 数据不兼容，THEN THE System SHALL 尝试自动转换或提示用户

##### 3.2 Union合并（基础策略）

5. WHEN 使用Union策略，THE System SHALL 使用上下拼接方式合并结果
6. THE System SHALL 为每条记录添加可选的元数据字段（用户可配置是否显示）：
   - **_source**: 数据来源（question_id或question_text）
   - **_round**: 执行轮次（1表示初始轮次，2+表示重规划轮次）
   - **_stage**: 执行阶段编号
   - **_priority**: 子任务优先级
   - **_confidence**: 数据置信度（0-1）
7. THE System SHALL 智能处理列名冲突：
   - 如果维度组合不同，使用"维度组合_度量名称"格式
   - 如果维度组合相同，直接使用度量名称
   - 提供列名映射表，说明每列的来源
8. THE System SHALL 保留所有子任务的原始维度结构，缺失维度填充为NULL或"N/A"

##### 3.3 Join合并（高级策略）

9. WHEN 使用Join策略，THE System SHALL 使用代码逻辑识别公共维度作为连接键（join key）：
   - 对比两个子任务的dims列表，找到相同的字段名称
   - 优先选择业务主键（如门店ID、产品ID）
   - 其次选择自然键（如门店名称、产品名称）
   - 考虑时间维度的对齐（如同比需要对齐相同的时间点）
   - **不需要AI**：字段名称是确定的，直接字符串匹配即可
10. THE System SHALL 根据业务场景智能选择连接类型：
   - **Inner Join**：只保留匹配的记录（如计算占比、增长率）
   - **Left Join**：保留主表所有记录（如补充属性、添加辅助指标）
   - **Full Outer Join**：保留所有记录（如完整对比、发现差异）
   - **Cross Join**：笛卡尔积（如生成所有维度组合）
11. THE System SHALL 智能处理连接后的字段命名冲突：
   - 根据业务语义添加有意义的前缀（如"当期_销售额"、"上期_销售额"、"目标_销售额"）
   - 如果是同比/环比，使用"本期"、"上期"、"同期"等前缀
   - 如果是不同维度，使用维度值作为前缀（如"北京_销售额"、"上海_销售额"）
12. THE System SHALL 在Join后自动计算派生指标：
   - 增长率：(当期-上期)/上期 × 100%
   - 增长额：当期-上期
   - 完成率：实际/目标 × 100%
   - 差异：实际-目标
13. THE System SHALL 处理Join后的数据缺失：
   - 标注哪些记录在某个表中缺失
   - 提供缺失原因（如时间范围不匹配、维度值不存在）
   - 建议用户如何处理缺失数据

##### 3.4 智能数据对齐与补全

14. WHEN 合并时间序列数据，THE System SHALL 智能识别时间粒度（grain）和对齐需求：
    - 自动检测时间粒度（日/周/月/季/年）
    - 识别时间范围的起止点
    - 检测时间序列的连续性
15. THE System SHALL 对时间维度进行智能补点：
    - 日粒度：补全日期序列，考虑工作日/节假日
    - 周粒度：补全周序列，统一周起始日（周一或周日）
    - 月粒度：补全月份序列
    - 季度粒度：补全季度序列
    - 年粒度：补全年份序列
16. THE System SHALL 根据指标类型智能填充补全的时间点：
    - **累计类指标**（如累计销售额、累计订单量）：使用前值或线性插值
    - **瞬时类指标**（如当日销售额、当日订单量）：填充0或NULL
    - **平均类指标**（如平均客单价）：不填充，保持NULL
    - **比率类指标**（如转化率）：根据分子分母重新计算
    - **状态类指标**（如库存量）：使用前值
17. THE System SHALL 提供补全策略配置：
    - 用户可以选择是否补全
    - 用户可以选择补全方式（0/NULL/前值/插值）
    - 用户可以查看哪些数据点是补全的
18. WHEN 合并多维度数据，THE System SHALL 智能识别维度的完整值域：
    - 从数据源元数据获取维度的所有可能值
    - 识别维度之间的层级关系（如地区→城市）
    - 考虑筛选条件对值域的影响
19. THE System SHALL 智能补全缺失的维度组合：
    - 只补全有意义的组合（如不补全"北京_上海"这种无意义组合）
    - 度量值填充为0或NULL，并标注为"补全"
    - 提供补全原因说明

##### 3.5 智能数据去重与清洗

20. THE System SHALL 智能检测重复记录：
    - 完全重复：相同维度组合+相同度量值
    - 部分重复：相同维度组合+不同度量值（可能是数据更新）
    - 逻辑重复：不同维度值但表示同一实体（如"北京"和"北京市"）
21. IF 检测到重复记录，THEN THE System SHALL 根据场景智能处理：
    - **保留第一条**：默认策略，适用于静态数据
    - **保留最后一条**：时间序列更新场景，保留最新数据
    - **聚合合并**：对度量值求和或平均，适用于分组数据
    - **标记冲突**：如果无法判断，标记为冲突并提示用户
22. THE System SHALL 使用代码检测数据质量异常（与需求4的业务异常不同）：
    - **数据质量异常**（代码检测）：脏数据、错误数据、数据完整性问题
      - 统计离群值：使用3σ原则或IQR方法识别
      - 明显错误：负数销售额、超大值、未来日期、空值过多
      - 逻辑错误：销售额>0但订单量=0等不合理组合
    - **业务异常**（AI分析，见需求4.3）：趋势突变、显著偏离、周期性异常
23. THE System SHALL 对数据质量异常采取分级处理：
    - **严重异常**：明显错误，标记并建议删除
    - **可疑异常**：可能错误，标记但保留
    - **正常异常**：合理的极端值（如促销期销售额暴涨），保留并说明
24. THE System SHALL 智能处理空值（NULL）：
    - **维度字段的NULL**：
      - 标记为"未知"、"其他"或"未分类"
      - 如果NULL占比>20%，提示数据质量问题
    - **度量字段的NULL**：
      - 在聚合时忽略（不参与计算）
      - 在对比时标注为"无数据"
      - 提供NULL的原因（如筛选条件导致、数据源缺失）
25. THE System SHALL 提供数据清洗报告：
    - 去重数量和去重策略
    - 异常值数量和处理方式
    - 空值数量和分布
    - 数据清洗前后的对比

##### 3.6 智能聚合计算与派生指标

26. WHEN 问题涉及聚合或对比，THE System SHALL 智能识别需要计算的指标：
    - **总计（Grand Total）**：所有记录的度量值汇总
    - **小计（Subtotal）**：按某个维度分组的汇总
    - **平均值（Average）**：度量值的平均（加权平均或简单平均）
    - **占比（Percentage）**：每个值占总计的百分比
    - **排名（Rank）**：按度量值排序的名次
    - **累计（Cumulative）**：累计求和或累计占比
27. THE System SHALL 根据问题类型自动计算派生指标：
    - **对比分析**：增长率、增长额、差异、差异率
    - **趋势分析**：移动平均、同比、环比、趋势线
    - **占比分析**：占比、累计占比、贡献度
    - **排名分析**：排名、排名变化、Top/Bottom标识
28. THE System SHALL 智能处理聚合的层级关系：
    - 识别维度的层级（如地区→城市→门店）
    - 自动计算各层级的小计
    - 确保小计之和等于总计（数据一致性检查）
29. THE System SHALL 为聚合行添加清晰的标识：
    - 使用特殊标识（如_is_total=true、_is_subtotal=true）
    - 在维度列显示"总计"、"小计"等文本
    - 使用不同的样式（如加粗、背景色）
30. THE System SHALL 智能放置聚合行：
    - 总计放在表格末尾
    - 小计放在相应分组的末尾
    - 支持用户配置聚合行的位置（顶部/底部/分组内）

##### 3.7 智能数据转换与标准化

31. THE System SHALL 智能识别并统一数值单位：
    - 自动检测单位（元/万元/亿元、个/千个/万个）
    - 统一到合适的单位（根据数值大小自动选择）
    - 在列名或元数据中标注单位
    - 提供单位转换说明
32. THE System SHALL 智能格式化数值显示：
    - 大数值使用千分位分隔符（如1,234,567）
    - 小数位数根据精度需求自动调整
    - 百分比自动添加%符号
    - 货币自动添加货币符号
33. THE System SHALL 统一日期时间格式：
    - 统一为ISO格式（YYYY-MM-DD）或用户偏好格式
    - 处理不同时区的时间
    - 统一日期粒度（如都转为日期，去除时间部分）
34. THE System SHALL 统一文本格式：
    - 去除前后空格和特殊字符
    - 统一大小写（根据业务需求）
    - 统一同义词（如"北京"和"北京市"）
    - 处理编码问题（如乱码）
35. THE System SHALL 自动计算派生字段：
    - 增长率 = (当期-上期)/上期 × 100%
    - 占比 = 当前值/总计 × 100%
    - 完成率 = 实际/目标 × 100%
    - 人均指标 = 总量/人数
    - 单位指标 = 总量/单位数
36. THE System SHALL 提供数据转换日志：
    - 记录所有转换操作
    - 说明转换原因和规则
    - 提供转换前后的对比

##### 3.8 智能排序与分页

37. THE System SHALL 根据问题类型智能选择排序策略：
    - **排名分析**：按度量值降序
    - **趋势分析**：按时间升序
    - **对比分析**：按维度值或度量值排序
    - **诊断分析**：按异常程度或重要性排序
38. IF 原始问题未指定排序，THEN THE System SHALL 使用智能默认排序：
    - 时间维度：升序（从早到晚）
    - 度量字段：降序（显示最大值在前）
    - 维度字段：按业务重要性或字母顺序
39. THE System SHALL 支持多级排序：
    - 自动识别排序优先级（如先按地区，再按销售额）
    - 支持混合排序（部分升序、部分降序）
    - 保持聚合行的位置（总计、小计不参与排序）
40. THE System SHALL 智能处理大数据集：
    - 限制合并结果的最大行数为Max_Result_Rows（默认10000）
    - 如果超过限制，智能选择截断策略：
      - TopN截断：保留最重要的N行
      - 采样截断：随机采样或分层采样
      - 聚合截断：聚合到更粗的粒度
    - 提供截断说明和完整数据的获取方式
41. THE System SHALL 提供分页支持：
    - 支持前端分页（一次返回所有数据）
    - 支持后端分页（按需加载）
    - 提供分页元数据（总页数、当前页、每页行数）

##### 3.9 全面数据质量检查与评分

42. THE System SHALL 计算合并结果的多维度数据质量指标：
    - **完整性（Completeness）**：非空值比例、缺失数据分布
    - **一致性（Consistency）**：字段类型、数值范围、逻辑关系是否合理
    - **准确性（Accuracy）**：是否有明显异常值、是否符合业务规则
    - **时效性（Timeliness）**：数据是否最新、是否使用了缓存
    - **唯一性（Uniqueness）**：是否有重复记录
    - **有效性（Validity）**：数据格式、数值范围是否符合要求
43. THE System SHALL 为每个质量维度计算评分（0-1）：
    - 完整性 = 非空值数量 / 总值数量
    - 一致性 = 符合规则的记录数 / 总记录数
    - 准确性 = 无异常值的记录数 / 总记录数
    - 综合质量评分 = 各维度加权平均
44. THE System SHALL 在数据质量低于阈值时发出分级警告：
    - **严重警告**（质量<60%）：红色标识，建议检查数据源
    - **一般警告**（60%≤质量<80%）：黄色标识，建议谨慎使用
    - **提示信息**（80%≤质量<95%）：蓝色标识，说明质量问题
    - **优秀**（质量≥95%）：绿色标识
45. THE System SHALL 生成详细的数据质量报告：
    - 各维度的质量评分和说明
    - 具体的质量问题列表（如哪些字段有缺失、哪些记录有异常）
    - 质量问题的影响范围
    - 改进建议（如添加筛选条件、检查数据源）
46. THE System SHALL 提供数据质量趋势：
    - 对比历史查询的质量评分
    - 识别质量下降的趋势
    - 预警可能的数据质量问题

##### 3.10 丰富的输出格式与可视化建议

47. THE System SHALL 输出结构化的合并结果，包含：
    - **data**: 数据行数组
    - **columns**: 列定义（名称、类型、描述、单位、格式）
    - **metadata**: 元数据
      - 总行数、总列数
      - 数据来源（各子任务的贡献）
      - 合并策略和参数
      - 数据质量评分
      - 执行时间和性能指标
    - **warnings**: 警告信息（数据截断、异常值、质量问题）
    - **transformations**: 数据转换日志
    - **quality_report**: 数据质量报告
48. THE System SHALL 支持多种输出格式：
    - **JSON**：适合API调用和前端渲染
    - **CSV**：适合导出和Excel打开
    - **Pandas DataFrame**：适合Python分析
    - **Tableau Hyper**：适合Tableau可视化
    - **Excel**：支持多sheet、格式化、图表
49. THE System SHALL 提供智能可视化建议：
    - 根据数据类型和问题类型推荐图表类型
    - 趋势分析 → 折线图、面积图
    - 对比分析 → 柱状图、条形图
    - 占比分析 → 饼图、树图
    - 排名分析 → 条形图、热力图
    - 多维分析 → 散点图、气泡图
50. THE System SHALL 保留原始子任务的结果：
    - 提供明细数据的访问接口
    - 支持用户查看合并前的原始数据
    - 提供数据血缘（data lineage）追溯
51. THE System SHALL 提供数据导出选项：
    - 支持导出到Tableau工作簿
    - 支持导出到Excel（带格式和图表）
    - 支持导出到数据库
    - 支持导出到云存储（S3、Azure Blob等）

##### 3.11 性能优化与缓存

52. THE System SHALL 实现智能合并优化：
    - 对于大数据集，使用流式合并而不是一次性加载
    - 使用并行处理加速数据转换
    - 使用增量合并（只合并新增数据）
53. THE System SHALL 缓存合并结果：
    - 缓存常用的合并结果
    - 缓存有效期根据数据更新频率调整
    - 提供缓存失效机制
54. THE System SHALL 记录合并性能指标：
    - 合并耗时
    - 内存使用
    - 数据处理速度（行/秒）
    - 瓶颈分析

### 需求 4: 母Agent - 动态重规划（Replan）

**用户故事:** 作为业务数据分析师，我希望系统能够像ThoughtSpot、Power BI Copilot和Tableau Pulse一样，根据当前分析结果智能推荐后续问题，自动发现异常并深入分析，实现连续的探索式分析，同时提供自然的对话式交互体验

#### 验收标准

##### 4.1 分析结果收集与智能评估

1. WHEN 一轮任务执行完成（需求2完成、需求3合并完成），THE System SHALL 从所有子Agent的分析结果中提取结构化信息：
   - **key_findings**: 关键发现列表（每个包含：发现内容、重要性评分、相关维度/指标）
   - **anomalies**: 异常列表（每个包含：异常类型、异常值、偏离程度、可能原因）
   - **next_steps**: 建议的后续分析方向（每个包含：分析类型、目标维度/指标、预期收益）
   - **insights**: 业务洞察（趋势、模式、相关性）
   - **confidence**: 分析结果的置信度（0-1）
2. THE System SHALL 统计当前轮次的全面指标：
   - **数据量指标**：总行数、总列数、总token数
   - **执行指标**：查询耗时、合并耗时、总耗时
   - **质量指标**：数据质量评分（来自需求3.9）、结果完整性
   - **用户体验指标**：是否有失败任务、是否使用了降级策略
3. THE System SHALL 收集完整的上下文信息：
   - **问题上下文**：
     - 原始问题（original_question）
     - 原始意图（original_intent）
     - 问题类型（question_type）
     - 问题复杂度（complexity）
   - **执行上下文**：
     - 使用的维度列表（current_dimensions）及其层级信息
     - 使用的度量列表（current_metrics）及其聚合方式
     - 应用的筛选条件（current_filters）
     - 排序逻辑（current_order_by）
     - 时间范围（current_time_range）
     - 时间粒度（current_grain）
   - **结果上下文**：
     - 合并后的数据摘要（行数、列数、数据范围）
     - 数据质量评分
     - 发现的异常数量和类型
4. THE System SHALL 智能评估当前分析的完成度：
   - **目标达成度**：原始问题是否已充分回答（0-1评分）
   - **信息充分度**：是否有足够的信息支持结论（0-1评分）
   - **异常覆盖度**：发现的异常是否已充分解释（0-1评分）
   - **综合完成度** = 加权平均
5. THE System SHALL 检查原始问题意图，确保重规划方向不偏离用户的核心分析目标

##### 4.2 智能重规划决策（AI模板驱动）

6. THE System SHALL 将完整的上下文信息输入MOTHER_REPLAN模板：
   - **问题上下文**：original_question、original_intent、question_type、complexity
   - **执行上下文**：current_dimensions、current_metrics、current_filters、current_time_range等
   - **结果上下文**：key_findings、anomalies、next_steps、insights、confidence
   - **数据指标**：total_rows、total_tokens、execution_time、data_quality_score
   - **轮次信息**：current_round、max_rounds、estimated_context_tokens
   - **元数据**：dimension_hierarchy（来自需求1.2）、available_dimensions、available_metrics
   - **完成度评估**：goal_achievement、information_sufficiency、anomaly_coverage
7. THE System SHALL 通过MOTHER_REPLAN模板让AI进行多维度决策：
   - **是否继续分析**（continue_analysis: true/false）
   - **继续的理由**（replan_reason）：
     - 发现重要异常需要深入分析
     - 目标未充分达成
     - 有明确的后续分析方向
     - 用户可能感兴趣的相关问题
   - **重规划类型**（replan_type）：
     - drill_down：维度下钻
     - pivot：横向对比
     - metric_expansion：指标扩展
     - time_adjustment：时间窗口调整
     - anomaly_focus：异常聚焦
     - related_question：相关问题探索
     - mixed：混合类型
   - **预期目标**（expected_goal）：本轮重规划希望达成什么
   - **预期收益**（expected_benefit）：对用户的价值（0-1评分）
   - **置信度**（replan_confidence）：重规划决策的置信度（0-1）
8. THE System SHALL 基于AI决策结果判断是否继续重规划：
   - IF continue_analysis=false，THEN 停止并进入最终总结
   - IF continue_analysis=true AND 满足以下任一条件，THEN 继续重规划：
     - 发现重要异常（severity>0.7）且异常覆盖度<0.5
     - 综合完成度<0.9 AND 有明确的next_steps
     - replan_confidence>0.7 AND expected_benefit>0.6
   - IF continue_analysis=true BUT 不满足继续条件，THEN 建议停止但允许用户选择继续
   - 详细的停止条件评估见需求4.10第36条
9. THE System SHALL 在重规划决策中考虑用户交互模式偏好：
   - 自动模式：AI自主决策是否继续，无需用户确认
   - 推荐模式：生成推荐问题列表，等待用户选择
   - 对话模式：生成自然语言提问，等待用户回答
   - 手动模式：不自动推荐，完全由用户控制
##### 4.3 统计异常检测与评估（借鉴ThoughtSpot + Tableau）

10. THE System SHALL 使用统计方法智能检测异常：
    - **Z-score方法**：识别偏离均值3个标准差以上的值
    - **IQR方法**：识别超出1.5倍四分位距的离群值
    - **时间序列异常**：识别趋势突变、周期性异常
    - **同比/环比异常**：识别显著的增长或下降
11. THE System SHALL 为每个检测到的异常计算评估指标：
    - **异常严重程度**（severity）：0-1评分，基于偏离程度
    - **统计显著性**（p_value）：统计检验的p值
    - **影响范围**（impact_scope）：影响的数据量占比
    - **业务重要性**（business_importance）：基于指标的业务权重
12. THE System SHALL 对异常进行分类和优先级排序：
    - **严重异常**（severity>0.7 AND p_value<0.01）：必须分析
    - **重要异常**（severity>0.5 AND p_value<0.05）：建议分析
    - **一般异常**（severity>0.3）：可选分析
    - 按严重程度×业务重要性排序
13. THE System SHALL 为每个严重异常自动生成"为什么"问题：
    - "为什么[维度值]的[指标]突然[增长/下降]？"
    - "是什么导致了[维度值]的异常？"
    - "[维度值]的异常是否在其他维度也存在？"

##### 4.4 推荐问题生成（借鉴ThoughtSpot Follow-up Questions）

14. THE System SHALL 生成推荐问题列表（3-5个）：
    - **基于异常的问题**：为每个严重异常生成"为什么"问题
    - **基于next_steps的问题**：将next_steps转换为具体问题
    - **基于维度层级的问题**：推荐下钻或上卷
    - **基于相关性的问题**：推荐相关维度或指标的分析
15. THE System SHALL 为每个推荐问题生成完整信息：
    - **question_text**：问题的自然语言描述（如"为什么北京销售额下降30%？"）
    - **analysis_type**：分析类型（drill_down/pivot/metric_expansion/anomaly_focus等）
    - **expected_benefit**：预期收益评分（0-1），基于：
      - 异常严重程度
      - 业务重要性
      - 信息增益
    - **expected_insights**：预期发现的洞察类型（趋势/原因/相关性/对比）
    - **estimated_time**：预估执行时间（秒）
    - **estimated_rows**：预估结果行数
    - **confidence**：推荐置信度（0-1）
    - **one_click_params**：一键执行所需的参数（dims、metrics、filters等）
16. THE System SHALL 按预期收益排序推荐问题：
    - 第1个问题：最高收益（通常是最严重的异常）
    - 第2-3个问题：次高收益（其他异常或重要的next_steps）
    - 第4-5个问题：相关探索（横向对比、指标扩展）
17. THE System SHALL 为每个推荐问题生成可视化预览（借鉴Tableau）：
    - 推荐的图表类型（折线图/柱状图/散点图等）
    - 预期的数据形状（X轴、Y轴、分组）
    - 缩略图或示意图（可选）

##### 4.5 用户交互模式（借鉴Power BI Copilot + Tableau Pulse）

18. THE System SHALL 支持多种重规划交互模式，用户可在设置中配置默认模式：
    - **自动模式**（Auto Mode）：
      - AI自动执行最佳推荐问题（expected_benefit最高）
      - 适合快速探索和演示场景
      - 用户可以随时中断或切换到其他模式
      - 每轮自动执行前显示3秒倒计时，用户可取消
    - **推荐模式**（Recommended Mode）：
      - 展示推荐问题列表（3-5个）
      - 用户点击选择执行
      - 用户可以修改问题参数
      - 默认模式，适合大多数用户
    - **对话模式**（Conversational Mode）：
      - Copilot主动提问："我注意到北京地区销售额下降了30%，要不要深入看看是哪些产品导致的？"
      - 用户用自然语言回答："是"、"不用"、"换个角度"、"看看其他地区"
      - 更自然的对话式体验，适合非技术用户
      - AI理解用户意图并执行相应操作
    - **手动模式**（Manual Mode）：
      - 不自动推荐
      - 用户完全控制分析方向
      - 适合专家用户和精确分析场景
19. THE System SHALL 在推荐模式下提供丰富的交互：
    - 显示推荐问题卡片，每个卡片包含：
      - 问题文本（如"为什么北京销售额下降30%？"）
      - 分析类型标签（下钻/对比/异常分析等）
      - 预期收益评分（高/中/低，用颜色区分）
      - 预估执行时间（如"约15秒"）
      - 预期发现（如"可能发现具体产品或时间段的问题"）
    - 用户可以：
      - 点击"执行"按钮 → 一键执行推荐问题
      - 点击"修改"按钮 → 调整维度、指标、筛选条件后执行
      - 点击"跳过"按钮 → 查看下一个推荐
      - 点击"查看更多"按钮 → 展开完整的推荐列表（如果超过3个）
      - 点击"自定义"按钮 → 输入自己的问题
      - 点击"停止分析"按钮 → 结束重规划，生成最终总结
20. THE System SHALL 在对话模式下提供自然交互：
    - Copilot主动提问（基于最佳推荐），使用自然语言：
      - "我发现了一个有趣的现象：北京地区销售额下降了30%，但上海却增长了15%。要不要深入看看北京是哪些产品出了问题？"
      - "数据显示Q3的销售额比Q2下降了20%，要看看是哪个月份导致的吗？"
      - "我注意到电子产品类的销售额占比从40%降到了30%，要分析一下具体是哪些产品吗？"
    - 用户回答选项（AI理解自然语言）：
      - "是" / "好的" / "执行" / "看看" → 执行推荐问题
      - "不用" / "跳过" / "不感兴趣" → 查看下一个推荐
      - "换个角度" / "看看其他的" / "还有别的吗" → 展示其他推荐
      - "停止" / "够了" / "不用继续了" → 结束重规划
      - "看看上海" / "分析产品" / 自定义问题 → AI理解意图并执行
    - AI根据用户回答智能调整：
      - 如果用户连续跳过2个推荐，AI询问："要不要换个分析方向？"
      - 如果用户提出自定义问题，AI尝试理解并生成新的子问题
      - 如果用户表达不满（如"没什么用"），AI调整推荐策略
21. THE System SHALL 支持用户在任意时刻切换交互模式：
    - 在推荐模式下，用户可以点击"切换到对话模式"
    - 在对话模式下，用户可以点击"显示推荐列表"切换到推荐模式
    - 在自动模式下，用户可以点击"暂停"切换到推荐模式
22. THE System SHALL 记录用户的交互偏好，用于优化推荐：
    - 记录用户最常使用的交互模式
    - 记录用户最常选择的推荐类型（下钻/对比/异常分析等）
    - 记录用户跳过的推荐类型
    - 根据历史偏好调整推荐排序

##### 4.6 新一轮子问题生成（AI模板驱动）

21. WHEN 用户选择执行某个推荐问题（或自动模式下），THE System SHALL 根据重规划类型使用对应的AI模板生成新一轮子问题：
   - **维度下钻**：使用INTELLIGENT_DRILL_ANALYSIS_TEMPLATE模板
   - **横向对比**：使用PIVOT_ANALYSIS_TEMPLATE模板
   - **指标扩展**：使用METRIC_EXPANSION_TEMPLATE模板
   - **时间窗口调整**：使用TIME_WINDOW_ADJUSTMENT_TEMPLATE模板
   - **异常聚焦**：使用ANOMALY_FOCUS_TEMPLATE模板
   - **相关问题探索**：使用RELATED_QUESTION_TEMPLATE模板
22. THE System SHALL 将完整的上下文信息输入对应的重规划模板：
   - 原始问题和意图
   - 上一轮问题上下文（dimensions、metrics、filters等）
   - 子Agent分析结果（key_findings、anomalies、next_steps）
   - 维度层级信息（dimension_hierarchy，来自需求1.2，由AI判断）
   - 可用维度和度量列表
   - 数据量约束
   - 用户选择的推荐问题（如果有）
23. THE System SHALL 通过AI模板让LLM生成完整的新一轮子问题，包括：
   - 子问题的自然语言描述（question_text）
   - 维度列表（dims）
   - 度量列表（metrics）
   - 计算字段（calculated_metrics，如需要）
   - 筛选条件（filters，继承+新增）
   - 日期筛选（date_filters）
   - 排序逻辑（order_by）
   - TopN限制（limit，如需要）
   - 时间粒度（grain，如需要）
   - Stage和依赖关系
   - 拆分理由（rationale）
   - 重规划理由（replan_reason）
   - 置信度（confidence_score，0-1）
23a. THE System SHALL 要求AI在生成新问题时遵循需求1的VizQL查询能力和拆分规则：
   - 如果新问题只涉及多个度量+相同维度+相同时间段 → 不拆分，生成1个子问题
   - 如果新问题涉及多个时间段对比 → 拆分为多个子问题
   - 如果新问题涉及计算依赖 → 拆分为多个子问题并设置依赖关系
   - 遵循需求1.3第7a-7c条的所有拆分规则

23b. THE System SHALL 根据重规划类型智能选择维度（合并原需求18）：
   - **下钻（drill_down）**：
     - 选择更小level的维度（更细粒度）
     - 例如：从"地区"（level=1）下钻到"城市"（level=2）或"门店"（level=3）
     - 优先选择parent_dimension指向当前维度的子维度
   - **上卷（roll_up）**：
     - 选择更大level的维度（更粗粒度）
     - 例如：从"门店"（level=3）上卷到"城市"（level=2）或"地区"（level=1）
     - 优先选择当前维度的parent_dimension
   - **横向对比（pivot）**：
     - 选择同level的维度
     - 例如：从"地区"（level=1）切换到"产品类别"（level=1）
     - 保持分析粒度不变，只改变分析角度
   - **维度扩展**：
     - 在VizQL支持的前提下，可以同时包含多个不同level的维度
     - 例如：[地区, 城市, 门店]（level=1,2,3）
     - 用于多层级联合分析

23c. THE System SHALL 按以下优先级选择新维度：
   1. **优先级1**：上一轮分析结论的next_steps中明确提到的维度
   2. **优先级2**：从维度层级（dimension_hierarchy）中选择符合重规划类型的维度
   3. **优先级3**：从可用维度列表中选择与问题相关的维度

23d. THE System SHALL 在选择维度时考虑VizQL的多维度查询能力：
   - 如果是单个查询，可以包含多个不同level的维度（VizQL支持）
   - 如果是重规划生成新查询，根据分析目标选择合适的维度level
   - 避免选择过多维度导致结果过于分散（建议最多3-4个维度）

##### 4.7 问题补全与验证

24. THE System SHALL 验证AI生成的新一轮子问题的完整性和合理性：
    - 维度和度量是否在数据源中存在
    - 维度组合是否合理（避免冲突）
    - 筛选条件是否有效
    - 是否有重复的维度（与current_dimensions对比）
    - 维度选择是否符合重规划类型（参考需求18第6条）：
      - drill_down：应选择更小level的维度
      - roll_up：应选择更大level的维度
      - pivot：应选择同level的维度
      - 其他类型：根据VizQL能力灵活选择
25. THE System SHALL 为新生成的子问题补全缺失的上下文信息：
    - 自动继承上一轮的公共筛选条件（如果AI未明确指定）
    - 自动继承排序逻辑（如果AI未明确指定）
    - 自动添加必要的计算字段（如同比需要两个时间段）
26. THE System SHALL 为每个新生成的子问题添加元数据：
    - replan_type：重规划类型
    - parent_question_ids：依赖的上一轮子问题ID列表
    - triggered_by：触发原因（anomaly/next_steps/user_selection）
    - recommendation_rank：在推荐列表中的排名

##### 4.8 数据量估算与智能优化（合并原需求18）

27. THE System SHALL 在生成新一轮子问题后，估算查询的数据量：
    - estimated_rows：预估结果行数（基于维度的unique_count和筛选条件）
    - estimated_tokens：预估token数量（基于行数、列数、字段类型）
    - estimated_time：预估执行时间

27a. THE System SHALL 按以下优先级添加筛选条件：
    1. **问题中的筛选**：用户明确指定的筛选条件（最高优先级）
    2. **基于token估算的筛选**：如果estimated_tokens>20000，添加TopN或时间范围筛选
    3. **基于分析结论的筛选**：上一轮next_steps建议的筛选（如"聚焦北京地区"）
    4. **下钻时的筛选**：下钻分析时，添加父维度的筛选（如下钻到"北京的门店"，添加"地区=北京"）

27b. WHEN 生成VizQL查询前，THE System SHALL 估算查询结果的token数量：
    - 计算公式：estimated_tokens = estimated_rows × 字段数 × 平均token/字段
    - 平均token/字段：STRING=10、INTEGER=5、REAL=5、DATE=5
    - IF estimated_tokens > 20000，THEN 添加筛选条件以减少数据量

27c. WHEN 母Agent调用replan方法，THE System SHALL 估算下钻后的上下文长度：
    - 计算公式：estimated_context = 当前上下文 + 新一轮estimated_tokens
    - IF estimated_context > 25000，THEN 采取以下策略：
      - 添加筛选条件（优先TopN或时间范围）
      - 如果添加筛选后仍超限，停止重规划
      - 生成当前结果的总结

27d. IF token估算超限且添加筛选后仍超限，THEN System SHALL 停止查询并提示用户：
    - 提示信息："查询结果可能过大，建议添加筛选条件或缩小时间范围"
    - 提供建议的筛选条件（如"Top 100"、"最近3个月"）
    - 允许用户调整筛选条件后重试

27e. IF 上下文长度超限，THEN System SHALL 停止重规划并生成当前结果的总结：
    - 提示信息："分析已达到上下文限制，正在生成总结"
    - 使用需求7的总结生成逻辑
    - 在总结中说明"由于上下文限制，分析在第X轮停止"
28. THE System SHALL 获取模型的最大上下文长度（与需求1.4第14条一致）：
    - 优先从模型配置中读取max_tokens
    - 如果模型配置中没有，使用环境变量API_MAX_TOKENS
    - 如果都没有，使用默认值128000
29. IF estimated_tokens超过模型最大上下文的30%，THEN THE System SHALL 调用DATA_VOLUME_OPTIMIZATION_TEMPLATE模板让AI优化查询：
    - 添加筛选条件（基于TopN、时间范围缩小或异常值聚焦）
    - 调整维度粒度（选择更粗的粒度）
    - 减少度量字段（只保留核心指标）
    - 使用采样（如果数据量特别大）
30. THE System SHALL 将优化后的子问题重新验证，确保数据量在可控范围内
31. THE System SHALL 在推荐问题中标注是否需要优化：
    - 如果需要优化，提示用户"数据量较大，已自动添加筛选条件"
    - 用户可以选择"查看完整数据"（移除优化）或"使用优化查询"

##### 4.9 重规划执行与进度反馈

32. WHEN 开始执行新一轮子问题，THE System SHALL 通过SSE推送replan事件：
    - **replan_started**：重规划开始
      - 重规划类型
      - 推荐问题列表
      - 用户选择的问题（如果有）
    - **replan_decision**：重规划决策
      - 是否继续
      - 继续的理由
      - 预期目标
    - **replan_questions_generated**：新问题生成完成
      - 新子问题列表
      - 预估执行时间
33. THE System SHALL 复用需求2的任务调度机制执行新一轮子问题
34. THE System SHALL 复用需求3的结果合并机制合并新一轮结果
35. THE System SHALL 在新一轮执行完成后，递归调用重规划流程（直到停止条件满足）

##### 4.10 智能停止条件与终止策略

36. THE System SHALL 在每轮重规划前评估是否应该停止：
    - **目标达成**：综合完成度>0.9
    - **无新发现**：连续两轮未发现新的key_findings
    - **异常已解释**：所有严重异常的覆盖度>0.8
    - **资源限制**：
      - 达到最大重规划轮次（Maximum_Replan_Rounds，默认3）
      - 累计上下文长度超过25000 tokens
      - 累计执行时间超过5分钟
    - **数据限制**：
      - 结果行数<10，无法继续下钻
      - 维度层级已达最细粒度
      - 无可用的新维度或指标
    - **用户意图**：
      - 用户选择"停止"
      - 用户长时间无交互（推荐模式下）
37. THE System SHALL 在停止前生成停止原因说明：
    - 清晰说明为什么停止
    - 如果是资源限制，建议如何继续（如添加筛选条件）
    - 如果是目标达成，总结已完成的分析
38. THE System SHALL 提供"继续探索"选项：
    - 即使达到停止条件，用户仍可以选择继续
    - 提示可能的风险（如上下文过长、执行时间长）
    - 用户确认后可以继续

##### 4.11 重规划历史与回溯

39. THE System SHALL 记录完整的重规划历史：
    - 每一轮的推荐问题列表
    - 用户的选择（执行了哪个问题、跳过了哪些）
    - 每一轮的分析结果和发现
    - 重规划决策的理由和置信度
40. THE System SHALL 支持用户回溯到任意轮次：
    - 查看历史轮次的结果
    - 从某个轮次重新开始
    - 对比不同轮次的结果
41. THE System SHALL 生成重规划路径图（类似思维导图）：
    - 显示分析的完整路径
    - 标注关键发现和决策点
    - 用户可以点击任意节点查看详情
42. THE System SHALL 支持保存分析路径（可选功能，非MVP必需）：
    - 用户可以保存当前的完整分析路径（包括所有轮次）
    - 保存内容包括：原始问题、所有子问题、查询结果、分析结论、重规划历史
    - 用户可以为保存的分析路径命名和添加描述
    - 用户可以重新加载已保存的分析路径，继续探索
    - 用户可以查看历史保存的分析路径列表

##### 4.12 性能优化与用户体验增强

43. THE System SHALL 实现重规划的性能优化：
    - **预测性加载**：预测下一轮可能的问题，提前准备元数据和统计信息
    - **智能缓存**：缓存推荐问题的预计算结果（如异常检测结果、维度层级）
    - **增量分析**：只分析新增的维度/指标，复用已有的分析结果
    - **并行推荐生成**：并行生成多个推荐问题，减少等待时间
44. THE System SHALL 提供重规划的统计信息和分析：
    - **使用统计**：
      - 平均重规划轮次（按问题类型分组）
      - 最常用的重规划类型（下钻/对比/异常分析等）
      - 推荐问题的接受率（被执行的推荐占比）
      - 用户停止的原因分布（目标达成/资源限制/用户主动停止等）
    - **性能统计**：
      - 推荐生成耗时
      - 异常检测耗时
      - 用户响应时间（从推荐到执行的时间）
    - **质量统计**：
      - 推荐问题的平均收益评分
      - 用户满意度（基于用户反馈）
      - 分析深度（平均轮次、平均维度数）
45. THE System SHALL 持续学习和优化推荐算法：
    - **推荐优化**：
      - 记录哪些推荐问题被用户执行（正样本）
      - 记录哪些推荐问题被用户跳过（负样本）
      - 分析用户偏好模式（如更喜欢下钻还是对比）
      - 根据历史数据调整推荐排序和收益评分
    - **停止条件优化**：
      - 分析过早停止的案例（用户继续提问）
      - 分析过晚停止的案例（用户主动停止）
      - 动态调整停止阈值（如完成度阈值、轮次限制）
    - **异常检测优化**：
      - 记录哪些异常被用户关注（执行了相关推荐）
      - 记录哪些异常被用户忽略（跳过了相关推荐）
      - 调整异常严重程度的评分权重
44. THE System SHALL 提供用户反馈机制：
    - 在每个推荐问题卡片上提供"有用"/"无用"按钮
    - 在分析结束后询问用户："这次分析对您有帮助吗？"
    - 收集用户对推荐质量的评分（1-5星）
    - 允许用户提供文字反馈（如"推荐太浅"、"推荐很准确"）
45. THE System SHALL 根据用户反馈实时调整：
    - 如果用户标记推荐为"无用"，降低该类型推荐的优先级
    - 如果用户标记推荐为"有用"，提高该类型推荐的优先级
    - 如果用户反馈"推荐太浅"，增加下钻深度
    - 如果用户反馈"推荐太多"，减少推荐数量
46. THE System SHALL 提供个性化推荐：
    - 根据用户历史行为建立用户画像
    - 识别用户的分析风格（探索型/验证型/诊断型）
    - 根据用户角色调整推荐（管理者/分析师/业务人员）
    - 学习用户的领域知识（如熟悉哪些维度和指标）
47. THE System SHALL 提供推荐解释和透明度：
    - 在每个推荐问题中说明推荐理由（如"因为发现了异常"、"因为这是常见的后续分析"）
    - 显示推荐的置信度（高/中/低）
    - 允许用户查看推荐算法的详细逻辑（可选，面向高级用户）
    - 提供"为什么推荐这个"的解释按钮

##### 4.13 与主流产品对标和差异化

48. THE System SHALL 对标ThoughtSpot的Follow-up Questions功能：
    - **相似点**：自动生成后续问题推荐、基于异常检测、支持一键执行
    - **差异化**：
      - 提供多种交互模式（ThoughtSpot主要是推荐模式）
      - 更深入的异常分析（不仅检测异常，还自动生成"为什么"问题）
      - 更智能的停止条件（ThoughtSpot通常需要用户主动停止）
      - 支持对话式交互（ThoughtSpot主要是点击式交互）
49. THE System SHALL 对标Power BI Copilot的对话式分析：
    - **相似点**：自然语言交互、AI主动提问、理解用户意图
    - **差异化**：
      - 更结构化的推荐（Power BI Copilot主要是对话式）
      - 支持推荐模式和自动模式（Power BI Copilot主要是对话模式）
      - 更详细的推荐信息（预期收益、预估时间、预期发现）
      - 更强的异常检测能力（Power BI Copilot主要依赖用户提问）
50. THE System SHALL 对标Tableau Pulse的智能洞察：
    - **相似点**：自动发现异常、生成洞察、推送通知
    - **差异化**：
      - 支持交互式探索（Tableau Pulse主要是被动推送）
      - 用户可以选择分析方向（Tableau Pulse主要是AI决定）
      - 更灵活的重规划策略（Tableau Pulse主要是固定的分析模板）
      - 支持多轮深入分析（Tableau Pulse通常是单轮洞察）
51. THE System SHALL 提供独特的价值主张：
    - **探索式分析**：支持用户主导的探索式分析，而不仅是AI推荐
    - **多模式融合**：融合自动、推荐、对话、手动四种模式，适应不同用户和场景
    - **深度分析**：支持多轮重规划，深入挖掘问题根因
    - **透明可控**：用户可以查看推荐理由、调整参数、切换模式
    - **持续学习**：根据用户反馈持续优化推荐算法
52. THE System SHALL 在产品文档中清晰说明与竞品的差异：
    - 提供对比表格（功能对比、交互方式对比、适用场景对比）
    - 提供使用场景示例（如何使用不同模式解决不同问题）
    - 提供最佳实践指南（如何选择合适的交互模式）



### 需求 5: VizQL查询生成与执行（代码模板生成，无需AI）

**用户故事:** 作为系统，我需要根据母Agent生成的StructuredQuestionSpec，使用代码模板生成符合VDS规范的JSON查询语句并执行，确保查询100%正确、高性能、易维护

#### 设计理念

本需求采用**纯代码模板方案**（对标Tableau Pulse），**不涉及AI调用**：
- **母Agent已完成**：问题理解、字段选择、时间范围识别、聚合方式推断（需求1.3）
- **本需求职责**：将母Agent的结构化规格转换为VizQL查询JSON，执行查询，返回结果

**核心优势**：
- ✅ 查询正确率：99%+（代码模板保证）
- ✅ 生成性能：<100ms（纯代码，无LLM调用）
- ✅ LLM成本：0（不调用AI）
- ✅ 可维护性：代码逻辑清晰，易于测试和调试

#### 职责划分原则

- **母Agent职责**（需求1.3）：问题理解、字段选择、时间范围识别、聚合方式推断
- **本需求职责**：
  - 代码计算具体日期（基于母Agent识别的时间语义）
  - 代码选择查询模板（基于问题类型）
  - 代码生成VizQL查询JSON（使用模板）
  - 代码验证查询正确性
  - 代码执行查询并返回结果
- **子Agent职责**（需求6）：分析查询结果，提取关键发现

**注意**：本需求与Agent无关，是纯代码逻辑

#### 验收标准

##### 5.1 查询生成流程（整体架构）

1. THE System SHALL 实现以下查询生成流程：
   ```
   StructuredQuestionSpec
       ↓
   [可选] Step 1: 语义增强（AI）
       ↓
   EnhancedQuestionSpec
       ↓
   Step 2: 模板选择（代码）
       ↓
   Step 3: 查询构建（代码模板）
       ↓
   Step 4: 严格验证（代码）
       ↓
   VizQL Query (100%正确)
   ```

2. THE System SHALL 提供以下核心组件：
   - **SemanticEnhancer**：语义增强器（AI驱动，可选）
   - **TemplateSelector**：模板选择器（代码逻辑）
   - **QueryBuilder**：查询构建器（代码模板）
   - **QueryValidator**：查询验证器（代码逻辑）

##### 5.2 日期计算（纯代码，无AI）

3. WHEN 接收到StructuredQuestionSpec，THE System SHALL 使用**纯代码**处理时间日期：
   - **输入**：母Agent识别的时间语义（来自StructuredQuestionSpec的date_filters）
     - relative_type: "LAST_N_MONTHS" / "LAST_QUARTER" / "YEAR_OVER_YEAR"
     - time_unit: "MONTH" / "QUARTER" / "YEAR"
     - time_value: 3 (如"最近3个月")
     - comparison_type: "SAME_PERIOD_LAST_YEAR" / "PREVIOUS_PERIOD"（如果有）
   - **处理流程**：
     - 创建DateCalculator实例
     - 获取anchor_date（见第6条）
     - 调用DateCalculator.calculate()方法
     - 返回具体的start_date和end_date
     - 如果是同比/环比，返回多个时间段
   - **不调用AI**：日期计算是确定性逻辑，使用代码保证100%正确

4. **明确规则**：本需求不涉及AI调用
   - 母Agent（需求1.3）已完成：字段选择、维度/度量识别、聚合方式推断、时间语义识别
   - 本需求只负责：将时间语义转换为具体日期、选择查询模板、生成VizQL JSON
   - 如果母Agent的spec包含模糊信息（如"主要产品"），应该在需求1.3阶段就补全，而不是在本需求补全

5. THE System SHALL 要求AI输出补全后的结构化规格（EnhancedQuestionSpec），包含：
   - **时间语义**（不是具体日期，而是语义描述）：
     - relative_type: 相对时间类型
     - time_unit: 时间单位
     - time_value: 时间数值
     - comparison_type: 对比类型（如果有）
   - **筛选条件补全**：
     - 具体的筛选值列表（如Top 10产品）
   - **聚合方式**：
     - 明确的聚合函数（SUM/AVG/COUNT等）
   - **排序逻辑**：
     - 排序字段和方向
   - **TopN限制**：
     - 是否需要TopN及其值
   - **置信度**：
     - 语义理解的置信度（confidence）

6. THE System SHALL 使用以下流程获取anchor_date（数据的最新日期）：
   - **步骤1**：使用代码获取当前系统日期（current_date = datetime.now().date()）
   - **步骤2**：尝试从需求1.2获取的metadata中读取数据源最大日期（max_date）
     - IF metadata中有max_date字段，THEN 使用该值
     - IF metadata中没有max_date，THEN 生成VizQL查询获取最大日期：
       ```json
       {
         "query": {
           "fields": [
             {
               "fieldCaption": "订单日期",
               "function": "MAX"
             }
           ]
         }
       }
       ```
     - 执行查询并解析结果得到datasource_max_date
   - **步骤3**：取两个日期的最小值作为anchor_date
     - anchor_date = min(current_date, datasource_max_date)
     - 理由：避免使用未来日期（如数据源最大日期是2025年，但今天是2024年）
   - **步骤4**：缓存anchor_date，避免重复查询
     - 缓存key: datasource_luid + date_field_name
     - 缓存有效期: 1小时

7. WHEN 获得anchor_date后，THE System SHALL 使用代码计算具体日期：
   - 创建DateCalculator实例
   - 传入anchor_date和时间语义
   - 计算start_date和end_date
   - 如果是同比/环比，计算多个时间段
   - 示例：
     ```python
     calculator = DateCalculator(anchor_date="2024-10-27")
     dates = calculator.calculate(
         relative_type="LAST_N_MONTHS",
         time_value=3
     )
     # 返回: {"start_date": "2024-07-27", "end_date": "2024-10-27"}
     ```

8. **删除**：不再需要AI筛选值补全（应在需求1.3完成）

9. THE System SHALL 提供DateCalculator工具类，包含以下方法：
   - `calculate_relative_date()`: 计算相对日期（如"最近3个月"）
   - `calculate_comparison_dates()`: 计算对比日期（如"同比"、"环比"）
   - `calculate_period_dates()`: 计算周期日期（如"Q3"、"上半年"）
   - `align_incomplete_periods()`: 对齐未完整周期（如本月已过15天，上月也只取前15天）
   - 所有计算都是确定性的，相同输入产生相同输出

##### 5.3 模板选择器（TemplateSelector）- 代码职责

9. WHEN 获得EnhancedQuestionSpec后，THE System SHALL 使用代码逻辑选择合适的查询构建器：
   - **TrendQueryBuilder**（趋势分析）：
     - 条件：有时间维度 AND 时间范围连续
     - 示例："2024年每月的销售额趋势"
   - **RankingQueryBuilder**（排名分析）：
     - 条件：有limit OR 明确的排序要求
     - 示例："销售额Top 10的门店"
   - **DrillDownQueryBuilder**（下钻分析）：
     - 条件：有层级维度 AND 有上层筛选
     - 示例："北京地区各门店的销售额"
   - **AggregationQueryBuilder**（聚合分析）：
     - 条件：只有度量，无维度或少量维度（≤1个）
     - 示例："总销售额是多少"
   - **ComparisonQueryBuilder**（对比分析，默认）：
     - 条件：其他情况
     - 示例："各地区的销售额和利润"

10. THE System SHALL 使用以下代码逻辑进行模板选择：
   ```python
   if has_time_dimension(spec) and is_continuous_time_range(spec):
       return TrendQueryBuilder()
   elif spec.get("limit") or has_ranking_intent(spec):
       return RankingQueryBuilder()
   elif has_hierarchical_dimensions(spec) and has_parent_filters(spec):
       return DrillDownQueryBuilder()
   elif len(spec.get("dims", [])) <= 1:
       return AggregationQueryBuilder()
   else:
       return ComparisonQueryBuilder()
   ```

##### 5.4 查询构建器（QueryBuilder）- 代码模板

11. THE System SHALL 提供BaseQueryBuilder基类，包含通用功能：
   - `_init_query()`: 初始化查询结构
   - `_get_field_info()`: 获取字段信息（从metadata）
   - `_infer_aggregation()`: 根据dataType推断聚合函数
   - `_build_filters()`: 构建筛选条件
   - `_add_dimension_field()`: 添加维度字段
   - `_add_metric_field()`: 添加度量字段

12. THE System SHALL 为每个查询构建器实现`build()`方法，使用代码模板生成VizQL查询：
    - **不调用AI生成JSON**：所有JSON由代码生成
    - **确定性逻辑**：相同输入产生相同输出
    - **100%正确**：代码保证语法正确和约束满足

13. THE System SHALL 在ComparisonQueryBuilder中实现以下逻辑：
    ```python
    def build(self, spec, metadata):
        query = self._init_query(metadata)
        sort_priority = 1

        # 1. 添加维度字段（升序）
        for dim in spec["dims"]:
            sort_priority = self._add_dimension_field(
                query, dim, sort_priority, "ASC"
            )

        # 2. 添加度量字段（第一个降序，其他不排序）
        for i, metric in enumerate(spec["metrics"]):
            if i == 0:
                sort_priority = self._add_metric_field(
                    query, metric, metadata, sort_priority, "DESC"
                )
            else:
                self._add_metric_field_no_sort(query, metric, metadata)

        # 3. 添加筛选条件
        query["query"]["filters"] = self._build_filters(spec, metadata)

        return query
    ```

14. THE System SHALL 根据字段的dataType使用代码逻辑选择正确的聚合函数：
    - INTEGER/REAL → SUM（默认）
    - STRING → 不聚合
    - DATE/DATETIME → YEAR（默认）
    - BOOLEAN → COUNT

15. WHEN 日期字段的dataType为STRING，THE System SHALL 使用代码逻辑生成DATEPARSE计算字段：
    - 生成标准的DATEPARSE表达式：`DATEPARSE('yyyy-MM-dd', [字段名])`
    - 使用QuantitativeDateFilter（RANGE）配合minDate和maxDate
    - 确保日期格式正确

16. WHEN 日期字段的dataType为DATE或DATETIME，THE System SHALL 使用代码逻辑直接使用fieldCaption：
    - 配合QuantitativeDateFilter
    - 根据时间粒度选择合适的过滤器类型

17. THE System SHALL 使用代码逻辑为字段添加sortDirection和sortPriority：
    - sortPriority从1开始递增，保证唯一性
    - 维度字段默认ASC
    - 度量字段默认DESC（第一个度量）
    - 其他度量不排序（不添加sortPriority）

18. THE System SHALL 使用代码逻辑决定是否使用TopNFilter：
    - 仅在EnhancedQuestionSpec明确指定TopN时使用
    - 或在数据量估算超过阈值（>10000行）时使用
    - 记录使用原因到rule_notes

##### 5.4.1 计算字段生成（Calculation Field）

18a. WHEN StructuredQuestionSpec包含calculated_metrics时，THE System SHALL 使用代码逻辑生成计算字段：
    - **输入**：calculated_metrics列表，每个包含：
      - metric_name: 计算字段名称（如"增长率"、"占比"、"利润率"）
      - calculation_type: 计算类型（如"growth_rate"、"percentage"、"ratio"）
      - source_fields: 依赖的源字段列表（如["当期销售额", "上期销售额"]）
      - parameters: 额外参数（如小数位数、是否显示百分号）
    - **处理流程**：
      - 使用代码模板生成计算表达式（不调用AI）
      - 验证源字段存在且类型正确
      - 生成VizQL的calculation字段
    - **预定义计算模板**：
      - **增长率**（growth_rate）：
        ```python
        calculation = f"({current_field} - {previous_field}) / {previous_field}"
        ```
      - **占比**（percentage）：
        ```python
        calculation = f"{part_field} / {total_field}"
        ```
      - **比率**（ratio）：
        ```python
        calculation = f"{numerator_field} / {denominator_field}"
        ```
      - **差异**（difference）：
        ```python
        calculation = f"{field1} - {field2}"
        ```
      - **加权平均**（weighted_average）：
        ```python
        calculation = f"SUM({value_field} * {weight_field}) / SUM({weight_field})"
        ```
    - **计算字段约束**（代码验证）：
      - 不能同时有fieldCaption和calculation
      - 必须有fieldAlias（计算字段的显示名称）
      - 不能有function（function和calculation互斥）
      - 引用的字段必须存在于metadata或已定义的fields中
    - **复杂计算处理**：
      - IF 计算类型不在预定义模板中，THEN 调用AI生成计算表达式
      - 使用CALCULATION_FIELD_GENERATION模板（需新增）
      - 代码验证AI生成的表达式语法正确性
      - 代码验证引用的字段存在
      - IF 验证失败，THEN 返回错误，不使用该计算字段

18b. THE System SHALL 在生成计算字段时处理特殊情况：
    - **除零保护**：
      - 对于ratio和percentage类型，添加除零保护
      - 使用VizQL的IIF函数：`IIF([分母] = 0, NULL, [分子] / [分母])`
    - **NULL值处理**：
      - 对于涉及NULL的计算，使用ZN函数（Zero if Null）
      - 例如：`ZN([销售额]) + ZN([退货金额])`
    - **数据类型转换**：
      - 确保计算中的字段类型兼容
      - 必要时添加类型转换函数（如STR、INT、FLOAT）
    - **精度控制**：
      - 对于百分比和比率，使用ROUND函数控制小数位数
      - 例如：`ROUND([利润] / [销售额], 4)` （保留4位小数）

18c. THE System SHALL 记录计算字段的元数据：
    - calculation_template_used: 使用的计算模板类型
    - source_fields: 依赖的源字段
    - calculation_expression: 完整的计算表达式
    - ai_generated: 是否由AI生成（true/false）
    - validation_passed: 是否通过验证（true/false）

##### 5.5 查询验证器（QueryValidator）- 代码职责

19. THE System SHALL 在生成VDS查询后进行严格验证：
    - **sortPriority唯一性**：检查所有sortPriority值不重复
    - **字段不重复**：检查fieldCaption不重复
    - **function和calculation互斥**：检查不能同时存在
    - **字段存在性**：检查所有字段在metadata中存在
    - **筛选类型匹配**：检查筛选器类型与字段类型匹配
    - **非负maxDecimalPlaces**：检查maxDecimalPlaces≥0
    - **无重复筛选**：检查同一字段不能有多个filter

20. THE System SHALL 提供以下验证方法：
    ```python
    def validate(self, query, metadata):
        self._validate_sort_priority_unique(query)
        self._validate_fields_not_duplicate(query)
        self._validate_function_calculation_exclusive(query)
        self._validate_fields_exist(query, metadata)
        self._validate_filter_types_match(query, metadata)
        self._validate_max_decimal_places(query)
        self._validate_filters_not_duplicate(query)
    ```

21. IF 验证失败，THEN THE System SHALL 根据错误类型采取分级处理策略：
    - **严重错误**（阻止执行）：
      - 字段不存在（FieldNotFound）
      - 筛选类型不匹配（FilterTypeMismatch）
      - function和calculation同时存在（FunctionCalculationConflict）
      - 处理方式：
        - 阻止查询执行，不发送到VDS
        - 抛出ValidationError异常
        - 记录完整的错误上下文（spec、metadata、生成的query）
        - 触发告警（见第22条）
        - 返回错误给调用方，包含：
          - error_type: 错误类型
          - error_message: 用户友好的错误描述
          - error_details: 技术细节（字段名、位置、期望值vs实际值）
          - suggested_fix: 建议的修复方式
    - **可修复错误**（自动修复）：
      - sortPriority重复：重新分配sortPriority（1, 2, 3...）
      - 字段重复：移除重复字段，保留第一个
      - maxDecimalPlaces为负：设置为0
      - 处理方式：
        - 自动修复query
        - 记录警告日志（包含修复前后的对比）
        - 继续执行查询
        - 在query的meta字段中记录auto_fixed: true和fix_details
    - **警告级错误**（不影响执行）：
      - 筛选条件可能过于宽松（预估结果>10000行）
      - 未指定排序（可能导致结果顺序不确定）
      - 处理方式：
        - 继续执行查询
        - 在query的warnings字段中记录警告信息
        - 在结果中提示用户

22. THE System SHALL 实现以下告警机制：
    - **开发环境**：
      - 打印详细的错误堆栈到控制台
      - 记录到本地日志文件（logs/query_validation_errors.log）
      - 不发送外部告警
    - **生产环境**：
      - 记录到集中式日志系统（如ELK、Splunk）
      - 发送告警到监控系统（如Sentry、DataDog）
      - 如果错误率>5%，发送邮件/Slack通知给开发团队
      - 记录错误指纹（error_fingerprint），用于去重和聚合
    - **告警内容**：
      - 错误类型和错误消息
      - 完整的spec和metadata（脱敏后）
      - 生成的query（如果有）
      - 堆栈跟踪
      - 环境信息（Python版本、依赖版本、操作系统）
      - 时间戳和session_id

23. THE System SHALL 提供错误恢复和降级策略：
    - **重试机制**（仅限可修复错误）：
      - 自动修复后重新验证
      - 最多重试1次（避免无限循环）
    - **降级策略**（严重错误时）：
      - 不回退到AI生成（代码失败说明逻辑有bug，AI生成不可靠）
      - 返回结构化错误信息给用户
      - 建议用户简化问题或调整筛选条件
      - 记录失败的spec，供后续分析和修复
    - **用户友好的错误提示**：
      - 字段不存在 → "抱歉，数据源中没有找到字段'XXX'，请检查字段名称或联系管理员"
      - 筛选类型不匹配 → "字段'XXX'的类型不支持该筛选条件，请调整筛选方式"
      - 数据量过大 → "查询结果可能过大，建议添加筛选条件或限制结果数量"

##### 5.6 性能优化与数据量估算

20. THE System SHALL 在查询生成前估算结果数据量：
    - 基于维度的unique_count和筛选条件
    - 估算结果行数（estimated_rows）
    - 估算token数量（estimated_tokens = estimated_rows × 字段数 × 平均token/字段）

21. THE System SHALL 获取模型的最大上下文长度（与需求1.4第14条一致）：
    - 优先从模型配置中读取max_tokens
    - 如果模型配置中没有，使用环境变量API_MAX_TOKENS
    - 如果都没有，使用默认值128000

22. IF estimated_tokens超过模型最大上下文的30%，THEN THE System SHALL 自动优化查询：
    - 添加TopNFilter（限制为1000行）
    - 或建议用户添加筛选条件
    - 记录优化原因到warnings字段

##### 5.7 输出与元数据

23. THE System SHALL 输出纯JSON格式的VizQL查询，不包含markdown代码块标记

24. THE System SHALL 在查询的meta字段中记录：
    - **template_used**: 使用的查询构建器类型
    - **semantic_enhanced**: 是否进行了语义增强
    - **rule_notes**: 应用的生成规则和口径说明
    - **estimated_rows**: 预估结果行数
    - **estimated_tokens**: 预估token数量
    - **generation_time**: 查询生成耗时（毫秒）

##### 5.8 错误处理与降级策略

25. IF 代码模板生成失败（如字段不存在、metadata缺失），THEN THE System SHALL 采取以下策略：
    - **记录详细错误**：包含堆栈跟踪、输入参数、失败原因
    - **不回退到AI生成**：代码失败说明逻辑有bug，AI生成不可靠
    - **返回错误给用户**：清晰说明问题和建议
    - **触发告警**：通知开发者修复代码bug

26. THE System SHALL 提供详细的错误信息：
    - 错误类型（FieldNotFound/MetadataMissing/ValidationFailed等）
    - 错误位置（哪个字段、哪个步骤）
    - 建议修复方式（如"检查字段名拼写"、"更新metadata"）

##### 5.9 测试与质量保证

27. THE System SHALL 为每个查询构建器提供单元测试：
    - 测试正常场景（各种spec组合）
    - 测试边缘场景（空维度、空度量、复杂筛选）
    - 测试错误场景（字段不存在、metadata缺失）
    - 测试覆盖率>90%

28. THE System SHALL 提供集成测试：
    - 端到端测试（从spec到VizQL查询）
    - 验证生成的查询可以成功执行
    - 验证查询结果符合预期

29. THE System SHALL 提供性能测试：
    - 测试查询生成耗时<100ms
    - 测试内存使用<50MB
    - 测试并发生成（10个查询同时生成）

##### 5.10 与Tableau Pulse对标

30. THE System SHALL 对标Tableau Pulse的以下特性：
    - ✅ **代码模板化**：使用代码生成查询，不依赖AI
    - ✅ **模板库**：提供多种预定义查询构建器
    - ✅ **严格验证**：检查所有VizQL约束
    - ✅ **高性能**：查询生成<100ms
    - ✅ **100%正确**：代码保证语法正确
    - ✅ **易维护**：代码逻辑清晰，易于测试和调试

31. THE System SHALL 提供以下差异化优势：
    - ✅ **灵活的语义增强**：AI处理模糊信息（Tableau Pulse较弱）
    - ✅ **智能模板选择**：根据spec特征自动选择最佳模板
    - ✅ **开源可扩展**：用户可以添加自定义查询构建器

### 需求 6: 子Agent - 查询结果分析（代码统计检测 + AI业务洞察）

**用户故事:** 作为子Agent，我需要对VDS返回的数据进行结构化分析，提取关键发现和异常点，其中代码负责客观检测，AI负责业务解读

#### 职责划分原则

- **代码职责**：客观的统计检测、数据质量检查、异常识别
- **AI职责**：业务含义解读、洞察提取、后续建议生成

#### 验收标准

##### 6.1 代码的统计检测职责

1. WHEN 子Agent接收到VDS查询结果，THE System SHALL 首先使用代码进行客观的统计分析：
   - **基础统计**：
     - 结果行数、列数
     - 数值字段的min、max、mean、median、std、sum
     - 分类字段的unique_count、value_counts、mode
     - 空值数量和占比
     - 数据分布特征（偏度skewness、峰度kurtosis）
   - **异常检测**（使用统计方法，明确阈值和参数）：
     - **Z-score方法**：
       - 阈值：|z| > 3（可配置，环境变量ANOMALY_ZSCORE_THRESHOLD，默认3）
       - 适用场景：数据近似正态分布
       - 计算公式：z = (x - μ) / σ
       - 识别偏离均值3个标准差以上的值
     - **IQR方法**（四分位距）：
       - 阈值：Q1 - 1.5×IQR 或 Q3 + 1.5×IQR（可配置，环境变量ANOMALY_IQR_MULTIPLIER，默认1.5）
       - 适用场景：数据分布不对称或有明显离群值
       - 计算公式：IQR = Q3 - Q1
       - 识别超出1.5倍四分位距的离群值
     - **时间序列异常**：
       - **趋势突变检测**：
         - 使用移动平均（窗口大小：7天或7个数据点，可配置）
         - 阈值：偏离移动平均>2个标准差（可配置，环境变量ANOMALY_TREND_THRESHOLD，默认2）
         - 适用场景：检测突然的趋势变化
       - **周期性异常检测**：
         - 使用季节性分解（STL: Seasonal and Trend decomposition using Loess）
         - 阈值：残差>3个标准差（可配置）
         - 适用场景：有明显周期性的数据（如每周、每月）
     - **同比/环比异常**：
       - **同比增长率**：
         - 阈值：|增长率| > 50%（可配置，环境变量ANOMALY_YOY_THRESHOLD，默认0.5）
         - 计算公式：(当期 - 去年同期) / 去年同期
       - **环比增长率**：
         - 阈值：|增长率| > 30%（可配置，环境变量ANOMALY_MOM_THRESHOLD，默认0.3）
         - 计算公式：(当期 - 上期) / 上期
       - **特殊处理**：
         - 如果基期值为0或接近0（<1），不计算增长率，标记为"基期过小"
         - 如果增长率>1000%，标记为"极端增长"，需要人工审核
   - **数据质量检查**（复用需求3的部分结果，避免重复）：
     - **IF 数据已经过需求3的合并和清洗**，THEN 直接使用已有的质量评分
     - **子任务级别的额外检测**：
       - 业务规则检查（如销售额>0但订单量=0）
       - 数值范围合理性检查（如负数销售额、未来日期）
       - 逻辑一致性检查（如利润>销售额）
   - **参数配置**：
     - 所有阈值应可配置（通过环境变量或配置文件）
     - 提供默认值（如上所示）
     - 记录使用的阈值和参数到StatisticalReport的metadata字段

2. THE System SHALL 为每个检测到的异常计算客观指标：
   - **异常严重程度**（severity）：0-1评分，基于偏离程度
     - 计算公式（Z-score方法）：severity = min(|z| / 5, 1.0)
     - 计算公式（IQR方法）：severity = min(偏离距离 / (3×IQR), 1.0)
     - 计算公式（增长率方法）：severity = min(|增长率| / 2, 1.0)
   - **统计显著性**（p_value）：统计检验的p值
     - 使用t检验或卡方检验
     - p_value < 0.01：高度显著
     - p_value < 0.05：显著
     - p_value >= 0.05：不显著
   - **影响范围**（impact_scope）：影响的数据量占比
     - 计算公式：异常数据点数量 / 总数据点数量
   - **置信度**（confidence）：检测方法的可靠性，0-1评分
     - 基于数据量：数据点<10 → confidence=0.5，数据点>100 → confidence=0.9
     - 基于数据分布：正态分布 → confidence更高
   - **异常类型**（anomaly_type）：
     - "outlier_high"：高值离群
     - "outlier_low"：低值离群
     - "trend_break"：趋势突变
     - "seasonal_anomaly"：周期性异常
     - "yoy_spike"：同比激增
     - "yoy_drop"：同比骤降
     - "mom_spike"：环比激增
     - "mom_drop"：环比骤降

3. THE System SHALL 对异常进行分类和排序：
   - **严重异常**：severity>0.7 AND p_value<0.01
   - **重要异常**：severity>0.5 AND p_value<0.05
   - **一般异常**：severity>0.3
   - 按综合评分排序：score = severity × (1 - p_value) × impact_scope

4. THE System SHALL 生成结构化的统计报告（StatisticalReport），包含：
   - **basic_stats**：基础统计信息
     - row_count, column_count
     - numeric_stats: {field_name: {min, max, mean, median, std, sum}}
     - categorical_stats: {field_name: {unique_count, mode, value_counts}}
     - null_stats: {field_name: {null_count, null_percentage}}
   - **anomalies**：异常列表（含客观指标）
     - 每个异常包含：anomaly_type, field_name, value, severity, p_value, impact_scope, confidence
   - **data_quality**：数据质量评分（0-1）
   - **warnings**：数据质量警告列表
   - **metadata**：检测方法和参数
     - detection_methods: ["zscore", "iqr", "trend", "yoy"]
     - thresholds: {zscore: 3, iqr_multiplier: 1.5, yoy: 0.5, mom: 0.3}
     - detection_time: 检测耗时（毫秒）

##### 6.2 AI的业务洞察职责

5. WHEN 代码完成统计检测后，THE System SHALL 将StatisticalReport和原始数据输入ANALYSIS_DEPTH_TEMPLATES模板让AI进行业务解读：
   - **关键发现提取**（key_findings）：
     - 从统计结果中提取业务含义
     - 识别重要的趋势、模式、相关性
     - 评估发现的业务重要性（0-1评分）
   - **异常解读**（anomaly_interpretation）：
     - 为代码检测到的异常提供业务解释
     - 推测可能的原因（如季节性、促销活动、数据错误）
     - 评估异常的业务影响
   - **目标达成评估**（goal_achievement）：
     - 评估是否回答了子任务的问题
     - 识别信息缺口
     - 评估结果的可信度
   - **后续建议**（next_steps）：
     - 基于发现和异常，建议后续分析方向
     - 推荐需要深入的维度或指标
     - 评估建议的预期收益
6. THE System SHALL 使用CHILD_RESULT_ANALYST模板（或类似的子任务分析模板）让AI进行业务解读：
   - **输入**：
     - StatisticalReport（代码生成的统计报告）
     - 原始数据（智能采样，最多100行）
     - 子任务描述（task_text）
     - 子任务目标（spec）
   - **输出**：结构化的分析结果（AnalysisResult）
   - **注意**：CHILD_RESULT_ANALYST只是参考模板，可以根据实际需求调整
   - **分析深度**：子任务分析通常使用basic或detailed深度，不需要comprehensive（节省成本）

7. THE System SHALL 输出结构化的分析结果（AnalysisResult），包含：
   - **goal_achievement**：目标达成度评估
     - 值："是" / "否" / "部分"
     - 说明：是否回答了子任务的问题
   - **key_findings**：关键发现列表（1-5个）
     - 每个包含：内容（不超过50字）、重要性评分（0-1）、相关数据（具体数字）
     - 从StatisticalReport中提取业务含义
     - 识别重要的趋势、模式、相关性
   - **anomaly_interpretation**：异常解读列表（0-5个）
     - 每个包含：异常描述、可能原因、业务影响、建议行动
     - 为代码检测到的异常提供业务解释
     - 推测可能的原因（如季节性、促销活动、数据错误）
   - **data_quality**：数据质量评估
     - 值："良好" / "一般" / "较差"
     - 说明：是否存在数据质量问题
   - **next_steps**：后续建议列表（1-3个）
     - 每个包含：分析类型、目标维度/指标、预期收益（0-1）
     - 基于发现和异常，建议后续分析方向
     - 推荐需要深入的维度或指标
   - **insights**：业务洞察（可选）
     - 从数据中提炼的业务洞察
     - 支持证据和业务影响
   - **confidence**：分析结果的置信度（0-1）
     - 基于数据质量、样本量、统计显著性

8. THE System SHALL 根据子任务的重要性和复杂度调整分析深度：
   - **核心子任务**（priority=HIGH）：使用detailed分析
   - **辅助子任务**（priority=MEDIUM/LOW）：使用basic分析
   - **异常聚焦子任务**：使用detailed分析，重点解读异常
   - **快速验证子任务**：使用basic分析，只提取关键发现

##### 6.3 结果整合与输出

9. THE System SHALL 整合代码的统计报告和AI的分析结果：
   - 将StatisticalReport和AnalysisResult合并
   - 确保异常的客观指标和业务解读对应
   - 标注哪些是代码检测的，哪些是AI解读的
10. THE System SHALL 在输出中明确区分：
    - **客观事实**（来自代码统计）：用"数据显示"、"统计检测到"等表述
    - **业务解读**（来自AI分析）：用"可能是因为"、"建议"等表述
    - **置信度标注**：为AI的解读标注置信度
11. IF 数据不足或口径冲突，THEN THE System SHALL 明确指出问题：
    - 代码检测数据质量问题（如缺失值过多）
    - AI识别口径冲突（如维度组合不合理）
    - 提供具体的问题描述和建议
12. THE System SHALL 记录分析过程的元数据：
    - 使用的统计方法和参数
    - AI模板和分析深度
    - 分析耗时
    - 异常检测的阈值

##### 6.4 质量保证

13. THE System SHALL 验证AI分析结果的质量：
    - 检查key_findings是否有数据支持
    - 检查异常解读是否与统计结果一致
    - 检查next_steps是否具体可执行
14. IF AI分析结果质量不佳（如置信度<0.5），THEN THE System SHALL 采取降级策略：
    - 只返回代码的统计报告
    - 使用简化的分析模板
    - 标注"分析结果仅供参考"
15. THE System SHALL 提供分析结果的可解释性：
    - 说明关键发现的数据来源
    - 说明异常检测的方法和阈值
    - 说明AI推理的依据
### 需求 7: 母Agent - 最终合成与总结（对标ThoughtSpot + Power BI Copilot）

**用户故事:** 作为业务数据分析师，我希望系统能够整合所有轮次的分析结果，生成结构化、易理解的分析报告，包含关键发现、业务洞察、行动建议和数据说明，帮助我快速做出业务决策

#### 设计理念

本需求对标ThoughtSpot的Answer Summary和Power BI Copilot的Narrative Summary：
- **ThoughtSpot**：自动生成分析摘要，突出关键发现和异常
- **Power BI Copilot**：生成自然语言叙述，解释数据故事
- **Tableau Pulse**：生成洞察卡片，提供可视化建议

**核心目标**：
- ✅ 将复杂的多轮分析结果转化为清晰的业务结论
- ✅ 提供可操作的业务建议，而不仅是数据描述
- ✅ 说明数据局限性和注意事项，建立用户信任
- ✅ 支持多种输出格式，适应不同使用场景

#### 职责划分原则

- **代码职责**：收集和整合所有轮次的数据、统计信息、执行元数据
- **AI职责**：提炼关键发现、生成业务洞察、撰写自然语言总结

#### 验收标准

##### 7.1 分析结果收集与整合（代码职责）

1. WHEN 所有轮次的任务执行完成（或用户主动停止），THE System SHALL 收集完整的分析上下文：
   - **原始问题信息**：
     - 用户的原始问题（original_question）
     - 问题类型（question_type）
     - 问题复杂度（complexity）
   - **执行历史**（复用需求4.11的重规划历史，避免重复收集）：
     - 从需求4.11获取完整的重规划历史记录
     - 包含：总轮次数、每轮的推荐问题、用户选择、分析结果摘要、重规划决策
     - 生成分析路径图（思维导图格式，见需求4.11第41条）
     - 识别关键转折点（如"发现异常后深入分析"、"用户选择横向对比"）
     - **不在需求7重新收集**：直接引用需求4已记录的数据
     - **简化处理**：只保留关键决策点（最多5个），不保留详细的子任务执行过程
   - **数据摘要**（智能采样，避免超上下文）：
     - 最终合并数据的**智能采样**（最多100行，包含Top/Bottom/异常值）
     - 数据统计摘要（总行数、列数、min/max/avg/count）
     - 数据质量评分（来自需求3.9）
     - 数据来源和时间范围
   - **关键发现**：
     - 所有子Agent的key_findings（去重和排序）
     - 所有检测到的异常（anomalies）
     - 所有后续建议（next_steps）
   - **执行质量**：
     - 成功任务数和失败任务数
     - 是否使用了降级策略
     - 是否有数据截断或采样
     - 总执行时间和总token消耗

2. THE System SHALL 对"执行历史"中的每轮执行结果进行精简：
   - **保留**：
     - 分析结果摘要（key_findings、anomalies、next_steps）
     - 数据统计信息（行数、列数、数值范围）
     - 执行元数据（耗时、状态、质量评分）
   - **不保留**：
     - 完整的查询结果数据（太大，会超上下文）
     - 原始的VizQL查询JSON（不需要在总结中展示）
   - **可选保留**（仅在需要时）：
     - 代表性数据样本（Top 5行，用于说明发现）

3. THE System SHALL 对"数据摘要"进行智能采样，避免超上下文：
   - **采样策略**：
     - Top 20行（按主要度量降序）
     - Bottom 5行（按主要度量升序）
     - 异常值行（统计检测到的异常）
     - 代表性中间值（如果数据分布广泛）
   - **采样上限**：最多100行（预估<5000 tokens）
   - **如果数据仍然过大**：
     - 只保留统计摘要（min/max/avg/count/unique_count）
     - 不传递原始数据到AI
     - 在总结中说明"基于统计摘要生成"

4. THE System SHALL 采用**主流AI数据分析产品的上下文管理策略**，避免超限：

   **参考主流产品实践**：
   - **ThoughtSpot**：只传递数据摘要（统计信息），不传递原始数据
   - **Power BI Copilot**：使用分层摘要（Layer-wise Summarization），每轮生成中间摘要
   - **Tableau Pulse**：使用固定的数据采样策略（Top 20 + Bottom 5 + 异常值）
   - **Google Bard/Gemini**：使用动态上下文窗口，优先保留最相关的信息

   **本系统采用的策略**（结合主流实践）：

   **策略1：固定采样 + 统计摘要（默认，对标Tableau Pulse）**
   - **数据采样**：固定采样100行（Top 20 + Bottom 5 + 异常值 + 代表性样本）
   - **统计摘要**：始终包含完整的统计信息（min/max/avg/count/unique_count）
   - **key_findings**：固定保留Top 15（按重要性）
   - **anomalies**：固定保留Top 10（按严重程度）
   - **分析路径**：固定保留关键决策点（最多5个）
   - **预估token数**：<8000 tokens（远低于128K上下文的10%）
   - **优点**：简单可靠，性能稳定，适合90%的场景

   **策略2：仅统计摘要（极端情况，对标ThoughtSpot）**
   - **触发条件**：IF 策略1的预估token数仍超过模型最大上下文的60%
   - **数据采样**：不传递原始数据，只传递统计摘要
   - **key_findings**：保留Top 10
   - **anomalies**：保留Top 5
   - **分析路径**：只保留最终决策
   - **预估token数**：<3000 tokens
   - **标注**：在总结中明确标注"基于统计摘要生成，未使用原始数据"
   - **优点**：极限压缩，保证不超限

   **策略3：分段生成（备用，对标Power BI Copilot）**
   - **触发条件**：IF 策略2仍超过70%上下文（极少发生）
   - **分段方式**：
     - 第1次调用：生成"执行摘要"和"关键发现"（输入：统计摘要 + Top 5 findings）
     - 第2次调用：生成"异常分析"和"业务洞察"（输入：统计摘要 + Top 5 anomalies + 第1次的输出）
     - 第3次调用：生成"行动建议"和"数据说明"（输入：第1次和第2次的输出摘要）
     - 最后合并：将3次输出合并为完整总结
   - **优点**：理论上可以处理任意复杂度，但增加LLM调用次数和成本

   **策略选择逻辑**：
   ```python
   estimated_tokens = calculate_tokens(context)
   max_tokens = get_model_max_tokens()  # 默认128000

   if estimated_tokens < max_tokens * 0.6:
       use_strategy_1()  # 固定采样 + 统计摘要（90%的情况）
   elif estimated_tokens < max_tokens * 0.7:
       use_strategy_2()  # 仅统计摘要（9%的情况）
   else:
       use_strategy_3()  # 分段生成（1%的情况）
   ```

5. THE System SHALL 对收集的信息进行预处理：
   - **去重**：合并相同或相似的key_findings（基于语义相似度）
   - **排序**：按重要性评分排序key_findings和anomalies
   - **分类**：将findings按类型分组（趋势/对比/异常/占比等）
   - **关联**：建立findings之间的因果关系或关联关系
   - **压缩**：如果findings过多（>20个），只保留最重要的Top 15

6. THE System SHALL 计算分析的综合指标：
   - **目标达成度**：原始问题是否已充分回答（0-1评分）
   - **信息充分度**：是否有足够的信息支持结论（0-1评分）
   - **分析深度**：平均重规划轮次、平均维度数、分析路径复杂度
   - **数据覆盖度**：分析覆盖的数据范围占总数据的比例
   - **异常覆盖度**：发现的异常是否已充分解释（0-1评分）
   - **上下文使用率**：实际使用的token数 / 模型最大上下文（监控是否接近上限）

##### 7.2 最终总结生成（AI职责）

7. WHEN 完成信息收集后，THE System SHALL 调用MOTHER_FINAL_COMPOSE模板让AI生成最终总结

8. THE System SHALL 将以下信息输入MOTHER_FINAL_COMPOSE模板（已优化，避免超上下文）：
   - **问题上下文**（<500 tokens）：
     - 原始问题和问题类型
     - 问题复杂度和分析目标
   - **关键发现**（<2000 tokens）：
     - 所有轮次的key_findings（已去重、排序、压缩，最多15个）
     - 每个finding包含：内容、重要性、数据支持（简化）
   - **异常分析**（<1000 tokens）：
     - 所有检测到的异常（已分类和排序，最多10个）
     - 每个异常包含：描述、严重程度、可能原因
   - **数据摘要**（<3000 tokens）：
     - 智能采样的数据（最多100行）
     - 数据统计信息（min/max/avg/count）
     - 数据质量评分和警告
   - **分析路径**（<1000 tokens）：
     - 重规划历史（简化，只保留关键决策点）
     - 每轮的核心发现和决策理由
   - **综合指标**（<500 tokens）：
     - 目标达成度、信息充分度、异常覆盖度
     - 执行质量（成功率、耗时、token消耗）
   - **用户参数**：
     - depth参数（basic/detailed/comprehensive）
     - 用户角色（如果有）
   - **预估总token数**：<8000 tokens（远低于模型上下文限制）

9. THE System SHALL 在传递数据前进行最终检查：
   - 计算实际token数（使用tokenizer）
   - IF 超过模型最大上下文的60%，THEN 触发紧急压缩：
     - 数据采样从100行降到50行
     - key_findings从15个降到10个
     - 异常从10个降到5个
     - 分析路径只保留最关键的2-3个决策点
   - IF 仍然超过70%，THEN 使用分段生成策略（见需求6.1第4条）

10. THE System SHALL 根据用户指定的depth参数应用不同的分析深度规则：
   - **basic**（快速阅读，30秒内）：
     - 3-5个关键发现
     - 1-2个核心洞察
     - 1-2个行动建议
     - 简洁的数据说明
   - **detailed**（深入理解，2-3分钟）：
     - 5-8个关键发现
     - 3-5个业务洞察
     - 3-5个行动建议
     - 详细的数据说明和局限性
     - 分析路径回顾
   - **comprehensive**（全面报告，5-10分钟）：
     - 10-15个关键发现
     - 5-10个业务洞察
     - 5-10个行动建议
     - 完整的数据说明和方法论
     - 详细的分析路径和决策过程
     - 可视化建议和后续分析方向

##### 7.3 总结结构与内容（对标主流产品）

11. THE System SHALL 生成结构化的最终总结，包含以下部分：

   **Part 1: 执行摘要（Executive Summary）**
   - 一句话回答原始问题（如"2024年Q3销售额为$5.2M，同比增长15%"）
   - 2-3个最重要的发现（用粗体突出关键数字）
   - 整体结论（如"销售增长主要由北京和上海地区驱动"）

   **Part 2: 关键发现（Key Findings）**
   - 按重要性排序的发现列表
   - 每个发现包含：
     - 发现内容（如"北京地区销售额增长30%"）
     - 数据支持（具体数字和对比）
     - 业务含义（为什么重要）
   - 使用可视化元素（如📈趋势、⚠️异常、✅正常）

   **Part 3: 异常分析（Anomaly Analysis）**
   - 检测到的异常列表（按严重程度排序）
   - 每个异常包含：
     - 异常描述（如"上海地区销售额突然下降20%"）
     - 统计指标（偏离程度、显著性）
     - 可能原因（AI推测）
     - 建议行动（如"深入分析上海地区的产品结构"）

   **Part 4: 业务洞察（Business Insights）**
   - 从数据中提炼的业务洞察
   - 每个洞察包含：
     - 洞察内容（如"电子产品类别的增长速度超过其他类别"）
     - 支持证据（数据和趋势）
     - 业务影响（对业务的意义）
     - 置信度（高/中/低）

   **Part 5: 行动建议（Action Recommendations）**
   - 基于分析结果的可操作建议
   - 每个建议包含：
     - 建议内容（如"增加北京地区的库存"）
     - 理由（基于哪些发现）
     - 优先级（高/中/低）
     - 预期影响（如"预计可提升10%销售额"）
     - 实施难度（易/中/难）

   **Part 6: 数据说明（Data Notes）**
   - 数据来源和时间范围
   - 数据质量评分和警告
   - 数据局限性（如"数据截断到前1000行"）
   - 不可比情况（如"TopN定义不一致"）
   - 口径说明（如"销售额包含退货"）

   **Part 7: 分析路径（Analysis Path）**（仅detailed和comprehensive）
   - 分析的完整路径（从原始问题到最终结论）
   - 每轮重规划的决策和理由
   - 关键转折点（如"发现异常后深入分析"）
   - 分析深度和广度的可视化

   **Part 8: 后续探索（Next Steps）**
   - 建议的后续分析方向
   - 未回答的问题
   - 可以深入的维度或指标
   - 相关的分析主题

12. THE System SHALL 使用清晰的Markdown格式：
    - 使用##、###标题层级组织结构
    - 使用**粗体**强调关键数字和结论
    - 使用列表（-或1.）展示要点
    - 使用表格对比数据
    - 使用emoji图标（��📉⚠️✅❌）增强可读性

##### 7.4 合并视图定义（数据血缘）

13. THE System SHALL 生成合并视图定义（Merged View Definition），说明最终数据的来源和构成：
   - **字段来源映射**：
     - 每个字段来自哪个子任务
     - 字段的原始名称和转换规则
     - 字段的聚合方式和计算逻辑
   - **数据合并策略**：
     - 使用的合并策略（Union/Join/Append等）
     - 合并的维度键
     - 数据对齐和补全规则
   - **数据转换日志**：
     - 应用的数据转换（去重、清洗、格式化等）
     - 转换前后的数据对比
     - 转换的原因和影响

14. THE System SHALL 提供数据血缘追溯（Data Lineage）：
    - 从原始问题到最终数据的完整路径
    - 每个数据点的来源（哪个查询、哪个轮次）
    - 数据的转换和计算过程
    - 支持用户点击查看详细信息

##### 7.5 可视化建议（对标Tableau Pulse）

15. THE System SHALL 根据数据类型和问题类型提供智能可视化建议：
    - **趋势分析** → 折线图、面积图
    - **对比分析** → 柱状图、条形图
    - **占比分析** → 饼图、树图、堆叠柱状图
    - **排名分析** → 条形图、热力图
    - **多维分析** → 散点图、气泡图、矩阵图
    - **地理分析** → 地图、热力地图

16. THE System SHALL 为每个可视化建议提供详细信息：
    - 推荐的图表类型
    - X轴和Y轴的字段
    - 分组和颜色编码
    - 筛选和排序建议
    - 图表标题和说明
    - 预期的洞察（用户可以从图表中看到什么）

17. THE System SHALL 提供可视化配置的JSON或代码：
    - Tableau配置（如果在Tableau环境）
    - Plotly/Matplotlib代码（如果在Python环境）
    - ECharts配置（如果在Web环境）
    - 用户可以一键生成可视化

##### 7.6 质量保证与透明度

18. THE System SHALL 在总结中明确标注：
    - **数据质量**：整体数据质量评分（0-1）和分级（优秀/良好/一般/较差）
    - **分析置信度**：AI分析结果的置信度（0-1）
    - **数据局限性**：
      - 数据截断（如"只分析了前1000行"）
      - 数据采样（如"使用了10%采样"）
      - 时间范围限制（如"只包含2024年数据"）
      - 维度缺失（如"缺少产品类别维度"）
    - **不可比情况**：
      - TopN定义不一致（如"第一轮Top 10，第二轮Top 20"）
      - 时间粒度不一致（如"第一轮按月，第二轮按周"）
      - 筛选条件不一致（如"第一轮包含退货，第二轮不包含"）
    - **口径说明**：
      - 关键指标的定义（如"销售额 = 订单金额 - 退货金额"）
      - 计算规则（如"增长率 = (当期-上期)/上期 × 100%"）
      - 特殊处理（如"空值填充为0"）

19. THE System SHALL 提供分析方法论说明（仅comprehensive模式）：
    - 使用的统计方法（如Z-score、IQR）
    - 异常检测的阈值和参数
    - 数据合并的策略和规则
    - AI模型的版本和参数
    - 分析的假设和前提

##### 7.7 多格式输出（适应不同场景）

20. THE System SHALL 支持多种输出格式：
    - **Markdown**（默认）：适合在线查看和分享
    - **HTML**：适合嵌入网页和邮件
    - **PDF**：适合打印和存档
    - **PowerPoint**：适合演示和汇报
    - **JSON**：适合程序化处理和集成
    - **Jupyter Notebook**：适合数据科学家深入分析

21. THE System SHALL 为每种格式优化内容：
    - **Markdown/HTML**：使用交互式元素（折叠、展开、链接）
    - **PDF**：使用专业排版和分页
    - **PowerPoint**：每个部分一张幻灯片，突出关键信息
    - **JSON**：结构化数据，便于程序处理
    - **Jupyter Notebook**：包含代码和数据，支持重现分析

##### 7.8 个性化与定制

22. THE System SHALL 支持用户定制总结内容：
    - **选择包含的部分**：用户可以选择只包含某些部分（如只要关键发现和行动建议）
    - **调整详细程度**：用户可以为每个部分单独设置详细程度
    - **自定义模板**：用户可以提供自定义的总结模板
    - **品牌定制**：用户可以添加公司logo、颜色主题、页眉页脚

23. THE System SHALL 根据用户角色调整总结风格：
    - **管理者**：强调业务影响和行动建议，减少技术细节
    - **分析师**：提供详细的数据说明和方法论
    - **业务人员**：使用业务语言，避免技术术语
    - **数据科学家**：包含统计指标和技术细节

##### 7.9 交互式总结（对标Power BI Copilot）

24. THE System SHALL 提供交互式总结功能（如果在Web环境）：
    - **可折叠部分**：用户可以展开/折叠各个部分
    - **数据钻取**：用户可以点击数字查看详细数据
    - **可视化预览**：用户可以点击可视化建议查看预览
    - **问题链接**：用户可以点击"后续探索"中的问题直接执行
    - **反馈按钮**：用户可以对总结的每个部分提供反馈

25. THE System SHALL 支持总结的版本管理：
    - 保存每次分析的总结
    - 用户可以查看历史总结
    - 用户可以对比不同时间的总结
    - 用户可以分享总结链接

##### 7.10 性能与缓存

26. THE System SHALL 优化总结生成性能：
    - 并行生成不同部分（如关键发现和可视化建议）
    - 缓存常用的模板和格式
    - 增量生成（如果用户只修改了部分参数）
    - 总结生成耗时<5秒（basic模式）、<10秒（detailed模式）、<20秒（comprehensive模式）

27. THE System SHALL 提供总结生成进度反馈：
    - 显示当前正在生成哪个部分
    - 显示预计剩余时间
    - 允许用户取消生成

##### 7.11 与主流产品对标

28. THE System SHALL 对标ThoughtSpot的Answer Summary：
    - **相似点**：自动生成分析摘要、突出关键发现、提供可视化建议
    - **差异化**：
      - 更详细的分析路径回顾（ThoughtSpot较简单）
      - 更丰富的行动建议（ThoughtSpot主要是数据描述）
      - 支持多种输出格式（ThoughtSpot主要是Web）
      - 更透明的数据说明（ThoughtSpot较少提及局限性）

29. THE System SHALL 对标Power BI Copilot的Narrative Summary：
    - **相似点**：自然语言叙述、解释数据故事、提供洞察
    - **差异化**：
      - 更结构化的总结（Power BI Copilot主要是段落文本）
      - 更详细的数据血缘（Power BI Copilot较少提及）
      - 支持更多输出格式（Power BI Copilot主要是文本）
      - 更强的可定制性（Power BI Copilot较固定）

30. THE System SHALL 对标Tableau Pulse的Insight Cards：
    - **相似点**：生成洞察卡片、提供可视化建议、突出异常
    - **差异化**：
      - 更全面的总结（Tableau Pulse主要是单个洞察）
      - 支持多轮分析的整合（Tableau Pulse通常是单轮）
      - 更详细的行动建议（Tableau Pulse较简单）
      - 支持交互式探索（Tableau Pulse主要是静态卡片）

31. THE System SHALL 提供独特的价值主张：
    - **全面性**：整合多轮分析的所有结果，提供完整的分析报告
    - **可操作性**：提供具体的、可执行的行动建议，而不仅是数据描述
    - **透明度**：清晰说明数据局限性和分析方法，建立用户信任
    - **灵活性**：支持多种输出格式和定制选项，适应不同场景
    - **交互性**：支持交互式探索和反馈，持续改进分析质量

### 需求 8: LangChain + LangGraph工作流编排（对标AutoGen + CrewAI）

**用户故事:** 作为系统架构师，我需要使用LangChain和LangGraph编排母Agent和子Agent的工作流，实现状态管理、错误恢复、流式输出和可视化监控，确保系统稳定可靠、易于调试和扩展

#### 设计理念

本需求基于LangChain和LangGraph，对标主流AI Agent框架的工作流编排能力：
- **LangChain + LangGraph**（本项目使用）：图编排、状态管理、检查点机制、流式输出
- **AutoGen**（对标）：多Agent对话、角色定义、消息传递
- **CrewAI**（对标）：任务编排、Agent协作
- **Semantic Kernel**（对标）：插件系统、函数调用

**核心目标**：
- ✅ 清晰的工作流定义，易于理解和维护
- ✅ 健壮的错误处理和恢复机制
- ✅ 实时的流式输出和进度反馈
- ✅ 完整的状态管理和检查点机制
- ✅ 可视化的工作流监控和调试

#### 职责划分原则

- **LangGraph职责**：工作流编排、状态管理、节点路由、错误恢复
- **Agent职责**：具体的业务逻辑（问题理解、查询生成、结果分析等）
- **代码职责**：确定性的流程控制、数据传递、资源管理

#### 验收标准

##### 8.1 工作流状态定义（State Schema）

1. THE System SHALL 定义完整的工作流状态（WorkflowState），包含：
   - **输入状态**：
     - user_question: 用户原始问题
     - datasource_luid: 数据源ID
     - depth: 分析深度（basic/detailed/comprehensive）
     - interaction_mode: 交互模式（auto/recommended/conversational/manual）
     - session_id: 会话ID
     - user_context: 用户上下文（角色、偏好等）
   - **元数据状态**：
     - metadata: 数据源元数据（来自需求1.2）
     - metadata_stats: 数据源统计信息
     - anchor_date: 数据最新日期（来自需求5.2）
   - **规划状态**：
     - plan: 分析计划（来自需求1.3）
     - subtasks: 子任务列表
     - current_round: 当前轮次
     - max_rounds: 最大轮次
   - **执行状态**：
     - execution_results: 子任务执行结果列表
     - failed_tasks: 失败任务列表
     - current_stage: 当前执行阶段
     - total_stages: 总阶段数
   - **合并状态**：
     - merged_data: 合并后的数据
     - merge_strategy: 使用的合并策略
     - data_quality_score: 数据质量评分
   - **重规划状态**：
     - replan_history: 重规划历史（来自需求4.11）
     - replan_decision: 当前重规划决策
     - recommended_questions: 推荐问题列表
     - user_selection: 用户选择
   - **输出状态**：
     - final_summary: 最终总结
     - visualization_suggestions: 可视化建议
     - analysis_path: 分析路径图
   - **控制状态**：
     - should_continue: 是否继续重规划
     - should_cancel: 是否取消执行
     - error: 错误信息（如果有）
     - warnings: 警告信息列表

2. THE System SHALL 使用TypedDict或Pydantic定义状态结构：
   ```python
   from typing import TypedDict, List, Dict, Optional
   from pydantic import BaseModel

   class WorkflowState(TypedDict):
       # 输入状态
       user_question: str
       datasource_luid: str
       depth: str  # "basic" | "detailed" | "comprehensive"
       interaction_mode: str  # "auto" | "recommended" | "conversational" | "manual"
       session_id: str

       # 元数据状态
       metadata: Dict
       metadata_stats: Dict
       anchor_date: str

       # 规划状态
       plan: Dict
       subtasks: List[Dict]
       current_round: int
       max_rounds: int

       # 执行状态
       execution_results: List[Dict]
       failed_tasks: List[Dict]
       current_stage: int
       total_stages: int

       # 合并状态
       merged_data: Optional[Dict]
       merge_strategy: Optional[str]
       data_quality_score: Optional[float]

       # 重规划状态
       replan_history: List[Dict]
       replan_decision: Optional[Dict]
       recommended_questions: List[Dict]
       user_selection: Optional[Dict]

       # 输出状态
       final_summary: Optional[str]
       visualization_suggestions: List[Dict]
       analysis_path: Optional[Dict]

       # 控制状态
       should_continue: bool
       should_cancel: bool
       error: Optional[str]
       warnings: List[str]
   ```

3. THE System SHALL 提供状态访问和更新的辅助方法：
   - `get_state(key)`: 获取状态值
   - `update_state(key, value)`: 更新状态值
   - `append_to_list(key, value)`: 向列表状态追加值
   - `merge_state(updates)`: 批量更新状态

##### 8.2 工作流节点定义（Nodes）

4. THE System SHALL 定义以下核心节点：
   - **metadata_node**（元数据获取）：
     - 输入：datasource_luid
     - 处理：调用需求1.2获取元数据和统计信息
     - 输出：更新metadata、metadata_stats、anchor_date
     - 错误处理：如果获取失败，返回错误并终止流程

   - **planning_node**（问题理解与拆分）：
     - 输入：user_question、metadata、metadata_stats
     - 处理：调用需求1.3进行问题理解和拆分
     - 输出：更新plan、subtasks、current_round
     - 错误处理：如果拆分失败，尝试fallback到两步方案

   - **execution_node**（任务执行）：
     - 输入：subtasks、current_stage
     - 处理：调用需求2并行执行当前stage的子任务
     - 输出：更新execution_results、failed_tasks、current_stage
     - 错误处理：记录失败任务，继续执行其他任务

   - **merge_node**（结果合并）：
     - 输入：execution_results
     - 处理：调用需求3合并子任务结果
     - 输出：更新merged_data、merge_strategy、data_quality_score
     - 错误处理：如果合并失败，返回部分结果

   - **replan_decision_node**（重规划决策）：
     - 输入：merged_data、execution_results、replan_history、current_round、max_rounds
     - 处理：调用需求4.2评估是否需要重规划
     - 输出：更新replan_decision、recommended_questions、should_continue
     - 错误处理：如果决策失败，默认停止重规划

   - **replan_interaction_node**（重规划交互）：
     - 输入：recommended_questions、interaction_mode
     - 处理：根据交互模式与用户交互（需求4.5）
     - 输出：更新user_selection
     - 错误处理：如果用户超时未响应，默认停止

   - **replan_generation_node**（重规划生成）：
     - 输入：user_selection、replan_decision、metadata
     - 处理：调用需求4.6生成新一轮子任务
     - 输出：更新subtasks、current_round
     - 错误处理：如果生成失败，停止重规划

   - **final_compose_node**（最终总结）：
     - 输入：所有轮次的execution_results、merged_data、replan_history
     - 处理：调用需求7生成最终总结
     - 输出：更新final_summary、visualization_suggestions、analysis_path
     - 错误处理：如果生成失败，返回简化版总结

5. THE System SHALL 为每个节点实现标准接口：
   ```python
   from langgraph.graph import StateGraph

   def metadata_node(state: WorkflowState) -> WorkflowState:
       """获取数据源元数据"""
       try:
           # 调用需求1.2的逻辑
           metadata = get_metadata(state["datasource_luid"])
           metadata_stats = calculate_metadata_stats(metadata)
           anchor_date = get_anchor_date(metadata)

           return {
               **state,
               "metadata": metadata,
               "metadata_stats": metadata_stats,
               "anchor_date": anchor_date
           }
       except Exception as e:
           return {
               **state,
               "error": f"Failed to get metadata: {str(e)}"
           }

   def planning_node(state: WorkflowState) -> WorkflowState:
       """问题理解与拆分"""
       try:
           # 调用需求1.3的逻辑
           plan = plan_and_decompose(
               state["user_question"],
               state["metadata"],
               state["metadata_stats"]
           )

           return {
               **state,
               "plan": plan,
               "subtasks": plan["subtasks"],
               "current_round": 1
           }
       except Exception as e:
           # 尝试fallback到两步方案
           try:
               plan = two_step_planning(state["user_question"], state["metadata"])
               return {**state, "plan": plan, "subtasks": plan["subtasks"], "current_round": 1}
           except:
               return {**state, "error": f"Failed to plan: {str(e)}"}

   # 其他节点类似实现...
   ```

##### 8.3 工作流边定义（Edges）

6. THE System SHALL 定义以下边和路由逻辑：
   - **START → metadata_node**：无条件开始
   - **metadata_node → planning_node**：如果metadata获取成功
   - **metadata_node → END**：如果metadata获取失败
   - **planning_node → execution_node**：如果拆分成功
   - **planning_node → END**：如果拆分失败
   - **execution_node → execution_node**：如果还有未执行的stage（循环）
   - **execution_node → merge_node**：如果所有stage执行完成
   - **merge_node → replan_decision_node**：如果合并成功
   - **merge_node → final_compose_node**：如果合并失败但有部分结果
   - **replan_decision_node → replan_interaction_node**：如果should_continue=true
   - **replan_decision_node → final_compose_node**：如果should_continue=false
   - **replan_interaction_node → replan_generation_node**：如果用户选择了问题
   - **replan_interaction_node → final_compose_node**：如果用户选择停止
   - **replan_generation_node → execution_node**：如果生成成功（开始新一轮）
   - **replan_generation_node → final_compose_node**：如果生成失败
   - **final_compose_node → END**：无条件结束

7. THE System SHALL 实现条件路由函数：
   ```python
   def should_continue_execution(state: WorkflowState) -> str:
       """判断是否继续执行下一个stage"""
       if state.get("error"):
           return "error"
       if state["current_stage"] < state["total_stages"]:
           return "continue"
       return "done"

   def should_replan(state: WorkflowState) -> str:
       """判断是否需要重规划"""
       if state.get("error"):
           return "error"
       if state.get("should_cancel"):
           return "cancel"
       if state.get("should_continue"):
           return "replan"
       return "finish"

   def handle_user_selection(state: WorkflowState) -> str:
       """处理用户选择"""
       if state.get("user_selection") == "stop":
           return "stop"
       if state.get("user_selection"):
           return "continue"
       return "timeout"
   ```

##### 8.4 检查点机制（Checkpoint）

8. THE System SHALL 实现检查点机制，支持工作流的暂停和恢复：
   - **检查点存储**：
     - 使用LangGraph的MemorySaver或SqliteSaver
     - 在每个节点执行后自动保存状态
     - 检查点包含完整的WorkflowState
   - **检查点恢复**：
     - 支持从任意检查点恢复执行
     - 恢复后继续执行后续节点
     - 适用场景：系统崩溃、用户中断、长时间等待
   - **检查点清理**：
     - 成功完成的工作流：保留检查点7天
     - 失败的工作流：保留检查点30天
     - 用户取消的工作流：保留检查点3天

9. THE System SHALL 提供检查点管理接口：
   ```python
   from langgraph.checkpoint.sqlite import SqliteSaver

   # 创建检查点存储
   checkpointer = SqliteSaver.from_conn_string("checkpoints.db")

   # 创建工作流图
   workflow = StateGraph(WorkflowState)
   workflow.add_node("metadata", metadata_node)
   workflow.add_node("planning", planning_node)
   # ... 添加其他节点

   # 编译工作流（启用检查点）
   app = workflow.compile(checkpointer=checkpointer)

   # 执行工作流（自动保存检查点）
   config = {"configurable": {"thread_id": session_id}}
   result = app.invoke(initial_state, config=config)

   # 恢复工作流
   result = app.invoke(None, config=config)  # 从最后一个检查点恢复
   ```

##### 8.5 流式输出（Streaming）

10. THE System SHALL 实现流式输出，实时推送执行进度：
    - **流式事件类型**（对标需求2.7）：
      - workflow_started: 工作流开始
      - node_started: 节点开始执行
      - node_progress: 节点执行进度
      - node_completed: 节点执行完成
      - node_failed: 节点执行失败
      - edge_transition: 边转换（从一个节点到另一个节点）
      - workflow_completed: 工作流完成
      - workflow_failed: 工作流失败
    - **流式输出格式**：
      - 使用SSE（Server-Sent Events）推送事件
      - 每个事件包含：event_type、timestamp、node_name、data、progress
    - **流式输出示例**：
      ```python
      async for event in app.astream(initial_state, config=config):
          event_type = event["type"]  # "node_start" | "node_end" | "edge"
          node_name = event.get("node")
          data = event.get("data")

          # 推送到前端
          yield {
              "event": event_type,
              "node": node_name,
              "data": data,
              "timestamp": datetime.now().isoformat()
          }
      ```

11. THE System SHALL 提供流式进度计算：
    - 计算整体进度：completed_nodes / total_nodes
    - 计算当前节点进度（如果节点支持）
    - 预估剩余时间：基于已完成节点的平均耗时

##### 8.6 错误处理与恢复

12. THE System SHALL 实现分级错误处理策略：
    - **节点级错误**：
      - 在节点内部捕获异常
      - 更新state["error"]和state["warnings"]
      - 根据错误类型决定是否继续（见需求5.5第21条）
    - **工作流级错误**：
      - 捕获未处理的异常
      - 保存错误状态到检查点
      - 发送告警（见需求5.5第22条）
      - 返回错误信息给用户
    - **恢复策略**：
      - 自动重试：对于临时错误（网络抖动、超时），自动重试最多2次
      - 降级执行：对于部分失败，继续执行其他节点
      - 人工介入：对于严重错误，通知用户或管理员

13. THE System SHALL 提供错误恢复接口：
    ```python
    try:
        result = app.invoke(initial_state, config=config)
    except Exception as e:
        # 记录错误
        logger.error(f"Workflow failed: {str(e)}", exc_info=True)

        # 尝试恢复
        if is_recoverable_error(e):
            # 从最后一个检查点恢复
            result = app.invoke(None, config=config)
        else:
            # 返回错误信息
            return {"error": str(e), "recoverable": False}
    ```

##### 8.7 工作流可视化与监控

14. THE System SHALL 提供工作流可视化：
    - **静态可视化**：
      - 生成工作流图（Mermaid或Graphviz格式）
      - 显示所有节点和边
      - 标注节点类型和路由条件
    - **动态可视化**：
      - 实时显示当前执行的节点
      - 高亮已完成的节点（绿色）
      - 高亮失败的节点（红色）
      - 显示节点执行耗时
    - **可视化示例**：
      ```python
      from langgraph.graph import StateGraph

      # 生成Mermaid图
      mermaid_graph = app.get_graph().draw_mermaid()
      print(mermaid_graph)

      # 生成PNG图（需要安装graphviz）
      png_graph = app.get_graph().draw_mermaid_png()
      with open("workflow.png", "wb") as f:
          f.write(png_graph)
      ```

15. THE System SHALL 提供工作流监控指标：
    - **执行指标**：
      - 总执行时间
      - 各节点执行时间
      - 节点执行次数（检测循环）
      - 失败节点数量
    - **资源指标**：
      - 内存使用量
      - LLM调用次数和token消耗
      - 数据库查询次数
    - **质量指标**：
      - 数据质量评分
      - 分析置信度
      - 用户满意度（如果有反馈）

##### 8.8 工作流测试与调试

16. THE System SHALL 提供工作流测试工具：
    - **单元测试**：
      - 测试每个节点的输入输出
      - 使用mock数据模拟状态
      - 验证节点逻辑正确性
    - **集成测试**：
      - 测试完整的工作流执行
      - 使用真实数据源
      - 验证端到端流程
    - **边界测试**：
      - 测试错误处理逻辑
      - 测试边界条件（空数据、超大数据）
      - 测试并发执行

17. THE System SHALL 提供调试工具：
    - **日志记录**：
      - 记录每个节点的输入输出
      - 记录状态变化
      - 记录错误和警告
    - **断点调试**：
      - 支持在特定节点暂停执行
      - 检查当前状态
      - 手动修改状态后继续
    - **回放功能**：
      - 从检查点回放执行过程
      - 逐步执行每个节点
      - 对比不同执行的状态差异

##### 8.9 与主流框架对标

18. THE System SHALL 对标LangChain/LangGraph：
    - **相似点**：使用StateGraph、检查点机制、流式输出
    - **差异化**：
      - 更清晰的状态定义（TypedDict）
      - 更完善的错误处理和恢复
      - 更丰富的监控和可视化

19. THE System SHALL 对标AutoGen：
    - **相似点**：多Agent协作、消息传递
    - **差异化**：
      - 使用图编排而非对话式编排（更适合复杂流程）
      - 更强的状态管理（集中式状态）
      - 更好的可视化和调试

20. THE System SHALL 对标CrewAI：
    - **相似点**：任务编排、Agent协作
    - **差异化**：
      - 使用图编排而非顺序编排（更适合复杂流程）
      - 更灵活的路由逻辑（条件路由）
      - 更强的错误恢复能力
      - 更详细的执行监控
    - **注意**：结果聚合在需求3完成，不属于工作流编排职责

21. THE System SHALL 提供独特的价值主张：
    - **健壮性**：完善的错误处理和恢复机制，确保系统稳定
    - **可观测性**：实时监控、可视化、日志记录，易于调试
    - **可扩展性**：清晰的节点接口，易于添加新节点和功能
    - **用户体验**：流式输出、进度反馈、交互式重规划

### 需求 9: 提示词模板管理

**用户故事:** 作为系统维护者，我希望所有的分析规则和提示词都以文本形式存储在prompts.py中，便于维护和版本控制

#### 验收标准

1. THE System SHALL 将所有母Agent模板存储在experimental/tools/prompts.py文件中
2. THE System SHALL 将所有子Agent模板存储在experimental/tools/prompts.py文件中
3. THE System SHALL 将所有策略规则（MERGE_POLICIES、SORT_POLICIES、FILTER_POLICIES等）存储为文本模板
4. THE System SHALL 禁止在代码中硬编码提示词或规则
5. THE System SHALL 支持通过修改prompts.py文件来调整分析策略，无需修改业务代码




### 需求 10: 前端UI重构（Vue 3 + TypeScript）- 对标ChatGPT + Perplexity + ThoughtSpot

**用户故事:** 作为业务数据分析师，我希望看到像ChatGPT一样流畅的对话界面，像Perplexity一样清晰的分析过程，像ThoughtSpot一样直观的数据展示，让我能够轻松理解AI的分析思路和结果

#### 设计理念

本需求对标主流AI对话产品的用户体验：
- **ChatGPT**：流畅的对话体验、实时打字效果、清晰的消息气泡
- **Claude**：结构化的思考过程展示、可折叠的详细信息
- **Perplexity**：清晰的分析步骤、来源引用、相关问题推荐
- **ThoughtSpot**：直观的数据表格、交互式图表、Follow-up Questions
- **Tableau Pulse**：洞察卡片、异常高亮、可视化建议

**核心目标**：
- ✅ 让用户像聊天一样自然地提问和获取答案
- ✅ 让用户清晰地看到AI的分析思路（透明度）
- ✅ 让用户快速找到关键信息（可读性）
- ✅ 让用户能够深入探索数据（交互性）

#### 验收标准

##### 14.1 整体布局（Tableau Extension插件）

1. THE System SHALL 使用Vue 3 + TypeScript + Vite重构前端对话界面
2. THE System SHALL **保持现有的Tableau Extension布局**（参考现有React实现）：
   - **单页面布局**（无侧边栏，适配Tableau Dashboard）
   - **顶部区域**（简洁设计）：
     - 设置按钮（右上角，点击后弹出右侧抽屉式设置面板）
     - 清空对话按钮（可选）
     - **不包含**：数据源选择器、分析设置（这些都在设置面板中）
   - **中间主区域**：
     - 对话消息流（用户消息 + AI回复）
     - 占据大部分空间，支持滚动
   - **底部区域**：
     - 输入框（固定在底部，支持多行输入）
     - 发送按钮
   - **右侧抽屉式设置面板**（点击设置按钮后弹出，参考现有SettingsPanel.tsx，合并原需求17）：
     - **数据源选择器**：
       - 下拉菜单，显示所有可用数据源
       - 格式：数据源名称 (项目名称)
       - 初始化时主动调用后端API获取数据源列表（不依赖缓存）
       - 项目重启后，从本地存储（localStorage或Tableau Settings API）恢复选择
     - **语言选择**（中文/英文）：
       - 从环境变量VITE_LANGUAGE_OPTIONS读取可选项
       - 如果环境变量缺失，使用默认选项
     - **深度选择**（基础/详细/全面）：
       - 从环境变量VITE_DEPTH_OPTIONS读取可选项
       - 如果环境变量缺失，使用默认选项
     - **模型提供商选择**：
       - 仅保留"公司自建模型"（self_hosted）作为唯一选项
       - 移除"阿里云百炼"选项
     - **模型名称选择**（动态加载）：
       - 从/api/models端点动态获取可用模型列表（不硬编码）
       - 下拉菜单显示所有可用模型
       - 如果当前模型名不在列表中，自动选择最新模型（列表最后一个）
       - 显示加载状态（"加载中..."）
       - 如果是思考模型（名称包含reason/thinking/reasoner/思考），显示"启用思考过程"复选框
     - **测试连接按钮**：
       - 验证模型服务是否可用
       - 显示测试结果（成功/失败）
       - 失败时显示错误信息
     - **主题选择**（浅色/深色/系统）：
       - 默认跟随系统主题
       - 用户手动切换后不再跟随系统
     - **重置按钮**：
       - 恢复所有设置为默认值
     - **保存按钮**：
       - 验证必填字段（数据源名称、模型名称）是否已填写
       - 保存成功后显示明确的成功提示
       - 保存失败时显示错误信息
     - **交互**：
       - 按Esc键关闭抽屉
       - 点击抽屉外部区域关闭抽屉
       - 抽屉宽度：约35%容器宽度，最小200px
       - 抽屉打开时，主区域添加半透明遮罩
3. THE System SHALL 使用现代化的视觉设计：
   - 适配Tableau的视觉风格（与Dashboard协调）
   - 清晰的视觉层次（卡片、阴影、间距）
   - 一致的配色方案（主色调、成功色、警告色、错误色）
   - 支持浅色/深色主题切换（跟随系统或手动切换）
   - 响应式布局（适配不同Dashboard尺寸）
   - **注意**：作为Tableau Extension，不需要左侧边栏和历史对话列表

##### 14.2 用户消息展示（对标ChatGPT）

4. THE System SHALL 展示用户消息：
   - 右对齐，浅色背景（如浅蓝色）
   - 用户头像（右侧）
   - 消息文本（支持多行）
   - 时间戳（小字，灰色）
   - 编辑按钮（hover时显示，允许用户修改问题并重新提交）
   - 复制按钮（hover时显示）

##### 14.3 AI回复展示 - 流式打字效果（对标ChatGPT）

5. THE System SHALL 实现流畅的流式打字效果：
   - 逐字显示AI回复（模拟打字效果）
   - 显示"正在思考..."动画（在AI开始回复前）
   - 显示光标闪烁（在打字过程中）
   - 支持暂停/继续（用户可以暂停AI回复）
   - 支持停止生成（用户可以中断AI回复）

##### 14.4 AI回复展示 - 分析过程可视化（对标Perplexity + Claude）

6. THE System SHALL 展示清晰的分析过程（可折叠）：
   - **步骤1：理解问题**（对标Claude的思考过程）
     - 显示"🤔 正在理解您的问题..."
     - 展示问题类型（如"对比分析"、"趋势分析"）
     - 展示识别的关键要素（维度、指标、时间范围）
     - 展示问题复杂度（Simple/Medium/Complex）
     - 可折叠/展开详细信息

   - **步骤2：规划分析**
     - 显示"📋 正在规划分析步骤..."
     - 展示子任务列表（卡片形式，显示任务数量）
     - 展示任务依赖关系（简化的流程图或列表）
     - 展示预估执行时间
     - 可折叠/展开详细信息

   - **步骤3：执行查询**（对标Perplexity的来源展示）
     - 显示"🔍 正在查询数据..."
     - 实时显示执行进度（进度条 + 百分比）
     - 展示当前执行的子任务（如"正在查询北京地区的销售数据..."）
     - 展示已完成的子任务（绿色勾号 ✅）
     - 展示失败的子任务（红色叉号 ❌，可点击查看错误详情）
     - 可折叠/展开每个子任务的详细信息

   - **步骤4：分析结果**
     - 显示"📊 正在分析数据..."
     - 展示数据质量评分（如"数据质量：优秀 95%"）
     - 展示检测到的异常数量（如"发现3个异常"）
     - 可折叠/展开详细信息

   - **步骤5：生成总结**
     - 显示"✍️ 正在生成分析报告..."
     - 展示总结的各个部分（执行摘要、关键发现、异常分析等）
     - 逐段显示（流式打字效果）

7. THE System SHALL 提供"查看详细过程"按钮：
   - 默认折叠分析过程，只显示最终结果
   - 用户点击后展开完整的分析过程
   - 用户可以随时折叠/展开

##### 14.5 AI回复展示 - 最终结果（对标ThoughtSpot + Tableau Pulse）

8. THE System SHALL 展示结构化的最终结果（对标需求7的总结结构）：

   **Part 1: 执行摘要**（最醒目，置顶）
   - 大字号显示核心结论（如"2024年Q3销售额为$5.2M，同比增长15%"）
   - 使用图标和颜色突出关键数字（如📈增长、📉下降）
   - 2-3个最重要的发现（用卡片或标签展示）

   **Part 2: 关键发现**（卡片列表）
   - 每个发现一个卡片
   - 卡片包含：
     - 发现标题（粗体）
     - 数据支持（具体数字，带图标）
     - 业务含义（简短说明）
     - 重要性标签（高/中/低，用颜色区分）
   - 支持展开查看详细数据

   **Part 3: 数据表格**（对标ThoughtSpot）
   - 清晰的表格展示（带斑马纹）
   - 支持排序（点击列头）
   - 支持筛选（列头下拉菜单）
   - 支持分页（每页10/20/50行可选）
   - 支持导出（CSV/Excel）
   - 数值列右对齐，文本列左对齐
   - 异常值高亮显示（如红色背景）
   - 支持列宽调整

   **Part 4: 可视化图表**（对标Tableau Pulse，可选）
   - 根据数据类型自动推荐图表
   - 支持切换图表类型（折线图/柱状图/饼图等）
   - 交互式图表（hover显示详细数据）
   - 支持导出图表（PNG/SVG）

   **Part 5: 异常分析**（对标Tableau Pulse的Insight Cards）
   - 异常卡片列表
   - 每个卡片包含：
     - 异常标题（如"北京地区销售额下降30%"）
     - 严重程度标签（严重/重要/一般，用颜色区分）
     - 可能原因（AI推测）
     - 建议行动（可点击执行）
   - 异常值在数据表格中高亮显示

   **Part 6: 后续问题推荐**（对标Perplexity + ThoughtSpot）
   - 3-5个推荐问题（卡片或按钮形式）
   - 每个问题包含：
     - 问题文本（如"为什么北京销售额下降？"）
     - 分析类型标签（下钻/对比/异常分析等）
     - 预期收益评分（高/中/低）
     - 预估执行时间（如"约15秒"）
   - 用户点击后直接执行该问题
   - 支持"查看更多问题"（展开完整列表）

   **Part 7: 数据说明**（可折叠，默认折叠）
   - 数据来源和时间范围
   - 数据质量评分和警告
   - 数据局限性（如"数据截断到前1000行"）
   - 口径说明（如"销售额包含退货"）
   - 分析方法论（如"使用Z-score检测异常"）

9. THE System SHALL 提供快速操作按钮（每个部分的右上角）：
   - 复制（复制该部分内容）
   - 导出（导出为PDF/Excel/CSV）
   - 分享（生成分享链接）
   - 反馈（点赞/点踩，帮助改进）

##### 14.6 交互式探索（对标ThoughtSpot）

10. THE System SHALL 支持用户在结果中直接交互：
    - **点击数据表格的单元格**：
      - 显示该值的详细信息（如占比、同比、环比）
      - 提供快速操作（如"查看该门店的详细数据"）
    - **点击图表的数据点**：
      - 高亮该数据点
      - 显示详细数值
      - 提供下钻选项（如"查看该月的每日数据"）
    - **点击异常卡片**：
      - 展开异常详情
      - 显示相关数据
      - 提供"深入分析"按钮（自动生成后续问题）
    - **点击推荐问题**：
      - 直接执行该问题
      - 显示执行进度
      - 将结果追加到对话中

11. THE System SHALL 支持用户自定义视图：
    - 切换表格/图表视图
    - 调整图表类型
    - 筛选和排序数据
    - 隐藏/显示某些列
    - 保存自定义视图（下次自动应用）

##### 14.7 错误处理与用户反馈（对标ChatGPT）

12. THE System SHALL 友好地展示错误信息：
    - 使用温和的语言（如"抱歉，我遇到了一些问题..."）
    - 清晰说明错误原因（如"数据源连接失败"）
    - 提供具体的解决建议（如"请检查数据源配置"）
    - 提供重试按钮（用户可以一键重试）
    - 提供"联系支持"按钮（如果是严重错误）

13. THE System SHALL 提供实时反馈：
    - 显示"正在思考..."动画（AI处理时）
    - 显示进度条（长时间操作时）
    - 显示预计剩余时间（如"预计还需30秒"）
    - 显示当前状态（如"正在查询第2个子任务，共5个"）

##### 14.8 性能优化与用户体验

14. THE System SHALL 实现渐进式加载：
    - 优先显示执行摘要和关键发现
    - 延迟加载数据表格（用户滚动到时再加载）
    - 延迟加载图表（用户点击时再渲染）
    - 使用虚拟滚动（大数据表格）

15. THE System SHALL 实现智能缓存：
    - 缓存历史对话（本地存储）
    - 缓存数据表格（避免重复渲染）
    - 缓存图表（避免重复计算）
    - 提供"刷新"按钮（用户可以手动刷新）

16. THE System SHALL 提供流畅的动画：
    - 消息气泡淡入动画
    - 卡片展开/折叠动画
    - 数据表格加载动画（骨架屏）
    - 图表渲染动画
    - 页面滚动平滑过渡

##### 14.9 Tableau Dashboard适配（响应式设计）

17. THE System SHALL 适配不同的Tableau Dashboard尺寸：
    - 自动调整布局（适应Dashboard容器大小）
    - 优化小尺寸显示（如Dashboard的1/4区域）
    - 优化大尺寸显示（如全屏Dashboard）
    - 优化表格展示（横向滚动或卡片式）
    - 优化图表展示（自适应大小）
    - **注意**：作为Tableau Extension，主要适配桌面端，移动端由Tableau Mobile处理

##### 14.10 可访问性（Accessibility）

18. THE System SHALL 支持可访问性：
    - 支持键盘导航（Tab键切换焦点）
    - 支持屏幕阅读器（ARIA标签）
    - 支持高对比度模式
    - 支持字体大小调整
    - 支持色盲模式（使用图案而非仅颜色区分）

##### 14.11 与主流产品对标

19. THE System SHALL 对标ChatGPT：
    - **相似点**：流畅的对话体验、实时打字效果、清晰的消息气泡
    - **差异化**：
      - 更详细的分析过程展示（ChatGPT较简单）
      - 更丰富的数据展示（表格、图表、异常卡片）
      - 更强的交互性（点击数据、下钻分析）

20. THE System SHALL 对标Perplexity：
    - **相似点**：清晰的分析步骤、来源引用、相关问题推荐
    - **差异化**：
      - 更专注于数据分析（Perplexity是通用搜索）
      - 更丰富的数据可视化（Perplexity主要是文本）
      - 更强的交互式探索（Perplexity较静态）

21. THE System SHALL 对标ThoughtSpot：
    - **相似点**：直观的数据表格、交互式图表、Follow-up Questions
    - **差异化**：
      - 更自然的对话体验（ThoughtSpot较生硬）
      - 更详细的分析过程（ThoughtSpot直接显示结果）
      - 更友好的错误提示（ThoughtSpot较技术化）

22. THE System SHALL 提供独特的价值主张：
    - **对话式体验**：像聊天一样自然地提问和获取答案
    - **透明度**：清晰展示AI的分析思路和决策过程
    - **交互性**：支持点击数据、下钻分析、自定义视图
    - **可读性**：结构化的结果展示，快速找到关键信息




---

### 需求 9: 查询构建器（纯代码组件）

**用户故事:** 作为系统，我需要根据StructuredQuestionSpec生成符合VDS规范的VizQL查询JSON，确保查询100%正确

**职责说明**: 纯代码组件，使用代码模板生成查询，不涉及LLM调用

#### 核心功能

1. **查询生成**：根据Spec生成VizQL查询JSON（使用代码模板，不用AI）
2. **查询验证**：验证查询合法性（字段存在性、sortPriority唯一性等）
3. **Builder模式**：BasicQueryBuilder、TimeSeriesQueryBuilder、RankingQueryBuilder等
4. **规则说明**：记录使用的规则和口径（rule_notes）

**性能**：
- 生成耗时：<0.1秒
- 准确率：100%（纯代码规则）

**详细规格**: [需求9详细规格](./appendix/code-component-requirements.md#需求9查询构建器)

---

### 需求 10: 查询执行器（纯代码组件）

**用户故事:** 作为系统，我需要调用VDS API执行查询，处理分页和错误，确保查询稳定可靠

**职责说明**: 纯代码组件，不涉及LLM调用

#### 核心功能

1. **查询执行**：调用Tableau VDS API执行查询
2. **分页处理**：自动获取所有页（每页最多10000行）
3. **错误处理**：重试机制（指数退避）、超时控制
4. **结果解析**：解析VDS响应，转换为DataFrame

**性能**：
- 查询耗时：3-10秒（取决于数据量）
- 重试次数：最多2次

**详细规格**: [需求10详细规格](./appendix/code-component-requirements.md#需求10查询执行器)

---

### 需求 11: 统计检测器（纯代码组件）

**用户故事:** 作为系统，我需要对查询结果进行客观的统计分析，检测异常值和趋势，为AI提供分析依据

**职责说明**: 纯代码组件，使用统计方法，不涉及LLM调用

#### 核心功能

1. **描述性统计**：均值、中位数、标准差、分位数
2. **异常检测**：Z-score、IQR、MAD、孤立森林
3. **趋势分析**：线性回归、Mann-Kendall检验
4. **数据质量检查**：完整性、一致性、准确性

**输出**：
```json
{
  "statistics": {
    "mean": 1234.56,
    "std": 567.89,
    "anomalies": [{"value": 9999, "z_score": 3.5}]
  },
  "trend": {"slope": 0.05, "p_value": 0.01},
  "quality_score": 0.95
}
```

**详细规格**: [需求11详细规格](./appendix/code-component-requirements.md#需求11统计检测器)

---

### 需求 12: 元数据管理器（纯代码组件）

**用户故事:** 作为系统，我需要获取和缓存数据源元数据，为Agent提供字段信息

**职责说明**: 纯代码组件，调用Tableau Metadata API，不涉及LLM调用

#### 核心功能

1. **元数据获取**：通过Tableau Metadata API获取字段列表、类型、统计信息
2. **缓存管理**：Redis缓存（基础元数据1小时，维度层级24小时）
3. **数据源查找**：支持精确匹配、模糊匹配、去括号匹配
4. **元数据增强**：调用维度层级推断Agent，将结果写入元数据

**性能**：
- API调用：首次访问时1次
- 缓存命中率：>90%

**详细规格**: [需求12详细规格](./appendix/code-component-requirements.md#需求12元数据管理器)

---

### 需求 13: LangGraph工作流编排

**用户故事:** 作为系统架构师，我需要使用LangGraph编排7个Agent的工作流，实现状态管理、错误恢复、流式输出

**职责说明**: 系统需求，使用LangGraph框架

#### 核心功能

1. **工作流定义**：定义节点（7个Agent + 6个代码组件）和边（流转逻辑）
2. **状态管理**：使用LangGraph的StateGraph管理状态
3. **对话历史**：利用LangGraph的MemorySaver管理对话历史
4. **条件路由**：根据重规划决策选择路径（replan vs compose）
5. **检查点机制**：支持中断和恢复

**工作流**：
```
metadata_node → understanding_node → field_selector_node → task_decomposer_node
  → execution_node → merge_node → replanner_node → [replan or summarizer_node]
```

**详细规格**: [需求13详细规格](./appendix/system-requirements.md#需求13langgraph工作流编排)

---

### 需求 14: 提示词模板管理

**用户故事:** 作为系统维护者，我希望所有的提示词都以文本形式存储在prompts.py中，便于维护和版本控制

**职责说明**: 系统需求

#### 核心功能

1. **模板存储**：所有提示词存储在prompts.py中
2. **模板命名**：清晰的命名规范（如UNDERSTANDING_AGENT_TEMPLATE）
3. **模板版本控制**：使用Git管理提示词变更
4. **模板测试**：提供测试用例验证提示词效果

**详细规格**: [需求14详细规格](./appendix/system-requirements.md#需求14提示词模板管理)

---

### 需求 15: 前端UI重构（Vue 3 + TypeScript）

**用户故事:** 作为业务数据分析师，我希望看到像ChatGPT一样流畅的对话界面，像Perplexity一样清晰的分析过程，像ThoughtSpot一样直观的数据展示

**职责说明**: 前端需求，使用Vue 3 + TypeScript + Vite

#### 核心功能

1. **对话界面**：流式显示、Markdown渲染、代码高亮
2. **分析过程展示**：展示7个Agent的执行过程和结果
3. **数据可视化**：表格、图表、下钻交互
4. **进度反馈**：实时显示执行进度（SSE）
5. **重规划交互**：展示推荐问题、支持一键执行

**详细规格**: [需求15详细规格](./appendix/system-requirements.md#需求15前端ui重构)

---

## 性能总结

### Token消耗（单次查询，3个子任务，1轮重规划）

| Agent | Token消耗 | 调用次数 | 总Token |
|-------|----------|---------|---------|
| 维度层级推断 | 5,500 | 0（缓存） | 0 |
| 问题理解 | 1,550 | 2 | 3,100 |
| 字段选择 | 8,250 | 2 | 16,500 |
| 任务拆分 | 2,850 | 2 | 5,700 |
| 洞察Agent | 4,050 | 5 | 20,250 |
| 重规划 | 5,250 | 2 | 10,500 |
| 总结 | 4,050 | 1 | 4,050 |
| **总计** | - | **14** | **60,100** |

**单次最大token**: 8,250（字段选择Agent，20%上下文）✅

### 时间消耗（单次查询，3个子任务，1轮重规划）

| 阶段 | 耗时 | 说明 |
|------|------|------|
| 问题理解 | 2秒 | LLM调用 |
| 字段选择 | 2秒 | LLM调用 |
| 任务拆分 | 2秒 | LLM调用 |
| 查询执行（3个并行） | 5秒 | VDS API调用 |
| 洞察生成（3个并行） | 2秒 | LLM调用（并行） |
| 数据合并 | 1秒 | 纯代码 |
| 重规划决策 | 2秒 | LLM调用 |
| **第1轮小计** | **16秒** | - |
| 第2轮（重规划） | 14秒 | 同上 |
| 总结 | 2秒 | LLM调用 |
| **总计** | **32秒** | - |

---

## 下一步

需求文档已完成精简重构。接下来：

1. ✅ **创建详细附录**：在`./appendix/`目录下创建详细规格文档
2. ✅ **更新设计文档**：基于新的7 Agent架构更新design.md
3. ✅ **生成任务列表**：基于新需求生成tasks.md

**需求文档更新完成！**
