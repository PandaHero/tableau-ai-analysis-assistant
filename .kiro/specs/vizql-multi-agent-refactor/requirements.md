# VizQL多智能体查询与分析重构 - 需求文档

## 📖 文档导航

### 🚀 快速开始
- **[任务列表](./tasks.md)** - 可执行的任务分解

### 📋 主文档（本文件）
- 项目简介和核心目标
- 架构概述（7 Agent + 6 组件）
- 需求列表（精简版，每个需求1页）
- 性能总结
- **实施状态**（新增）

### 📚 详细附录（./appendix/）
- [Agent详细规格](./appendix/agent-requirements.md) - 7个Agent的详细验收标准、提示词设计、输入输出示例
- [代码组件详细规格](./appendix/code-component-requirements.md) - 6个代码组件的详细实现规格
- [系统需求详细规格](./appendix/system-requirements.md) - LangGraph编排、提示词管理、前端UI
- [技术规格](./appendix/technical-specs.md) - 数据模型、缓存架构、性能优化、数据采样策略
- [VizQL查询能力详解](./appendix/vizql-capabilities.md) - VizQL的能力边界、问题拆分决策指南
- [用户场景和示例](./appendix/user-scenarios.md) - 典型用户场景、端到端示例

### 📖 参考文档
- [旧版详细需求文档](./old/requirements-old-detailed.md) - 供参考

---

## 简介

本项目旨在重构现有的VizQL查询生成与结果分析逻辑，采用**7 Agent多智能体架构**和LangGraph编排，实现更智能、更灵活的业务数据分析能力。

### 参考项目说明

本项目参考了**tableau_langchain**项目（位于`tableau_langchain-main-原始/`目录），该项目提供了：
- ✅ LangChain + LangGraph的基础架构
- ✅ Tableau认证和API调用的工具函数
- ✅ VizQL Data Service的查询执行逻辑

**关键变化**：
- ❌ **舍弃**：tableau_langchain中使用AI生成VizQL查询语句的部分
- ✅ **改用**：纯代码规则生成VizQL查询JSON，参考`sdks/tableau/apis/vizqlDataServiceApi.ts`的类型定义
- ✅ **保留**：LangGraph编排、Tableau认证、API调用等基础设施

### 核心目标

1. **职责清晰** - 每个Agent只做一件事，易于理解和维护
2. **性能可控** - 单次LLM调用最大token ~8K（20%上下文），避免超限
3. **易于优化** - 可以独立优化每个Agent的提示词和策略
4. **用户体验** - 实时进度反馈、智能推荐、探索式分析

### 技术栈

- **后端**: LangChain + LangGraph + Python
- **前端**: Vue 3 + TypeScript + Vite
- **模型**: Qwen3-32B-AWQ-Int4（上下文40,960 tokens）
- **数据源**: Tableau VizQL Data Service (VDS)
- **类型定义参考**: tableau_sdk（TypeScript + Zod schema，位于`sdks/tableau/apis/vizqlDataServiceApi.ts`）
  - 提供VizQL的完整类型定义（Field、Filter、Query等）
  - 提供所有支持的枚举值（Function、FilterType等）
  - Python查询构建器参考这些类型定义创建对应的Pydantic模型

---

## 架构概述


### 系统组件

本系统采用**7个专业化Agent + 6个纯代码组件**的架构设计。

#### 7个Agent（需要LLM）

**预处理Agent（2个）**：
1. **维度层级推断Agent** - 推断维度的层级关系和粒度（首次访问时，缓存24小时）
2. **问题Boost Agent** - 优化和增强用户问题表达（可选，用户主动触发）

**查询流程Agent（5个）**：
3. **问题理解Agent** - 理解用户意图、拆分子问题、提取关键信息、评估问题复杂度
4. **任务规划Agent** - 根据问题复杂度智能规划查询策略、从元数据中选择字段、生成完整的查询规格
5. **洞察Agent** - 分析查询结果和统计检测结果、计算贡献度、生成业务洞察
6. **重规划Agent** - 基于洞察结果决策下一步分析方向、查找下钻维度、生成问题清单
7. **总结Agent** - 整合所有结果、生成最终报告

#### 6个纯代码组件（不需要LLM）

1. **元数据管理器** - 获取和缓存数据源元数据
2. **查询构建器** - 根据Spec生成VizQL查询JSON（**纯代码规则，参考tableau_sdk类型定义**）
3. **查询执行器** - 调用VDS API执行查询
4. **统计检测器** - 客观的统计分析和异常检测
5. **数据合并器** - 智能合并多个查询结果（**纯代码规则**）
6. **任务调度器** - 并行执行、超时控制、失败处理

### 工作流程

```
数据源首次访问 → [维度层级推断Agent] → 缓存24小时

用户提问 → (可选)[问题Boost Agent] → [问题理解Agent（拆分子问题）] → [任务规划Agent]
  ↓
  生成StructuredQuestionSpec（语义级别：dims、metrics、filters等）
  ↓
  → [查询构建器（纯代码规则）] → [查询执行器]
  ↓
  生成VizQL查询JSON（技术级别：参考tableau_sdk类型定义）
  ↓
  → [统计检测器] → [数据合并器（按需）] → [洞察Agent] → [重规划Agent]
  → 是否重规划？
    → 是：[任务调度器] → 回到任务规划Agent（处理重规划问题清单）
    → 否：[总结Agent] → 最终报告
```

**关键说明**：
- **AI负责**：语义理解、字段选择、任务拆分、结果分析
- **代码负责**：VizQL查询生成、查询执行、数据合并、统计检测

**详细说明**: [系统架构详解](./appendix/technical-specs.md#系统架构)

---

## AI与代码的职责划分

本项目采用"**AI做理解，代码做执行**"的设计理念，明确区分AI和代码的职责边界。

### AI的职责（语义理解层）

AI负责所有需要语义理解、灵活决策和业务解读的任务：

1. **自然语言理解** - 理解用户问题的业务意图、识别隐含需求
2. **字段理解与映射** - 从完整数据模型中选择正确字段、理解字段关系和层级
3. **问题拆分与结构化** - 将复杂问题拆分为子问题、识别依赖关系、评估复杂度
4. **智能决策与推荐** - 决定是否重规划、生成后续问题推荐、选择重规划类型
5. **异常解读与洞察** - 为统计异常提供业务解释、提取关键发现、生成业务洞察
6. **语义补全** - 补全模糊的时间表达、筛选条件、聚合方式等

**AI的输出**：结构化的规格（Spec）、决策结果、分析报告，而非可执行代码或精确数据

### 代码的职责（确定性执行层）

代码负责所有需要精确性、稳定性和可预测性的任务：

1. **精确的查询生成** - 基于AI的规格生成标准VizQL JSON，使用代码模板而非AI
   - 参考tableau_sdk的类型定义（`sdks/tableau/apis/vizqlDataServiceApi.ts`）
   - 使用Pydantic模型验证查询结构
   - 确保查询100%符合VDS规范
2. **数据处理与计算** - 数据合并、去重、聚合、排序等，使用Pandas/SQL等工具
3. **系统流程控制** - 任务调度、并发控制、超时处理、重试机制，使用LangGraph编排
4. **统计检测** - 异常检测（Z-score、IQR）、数据质量检查，使用统计方法
5. **验证与校验** - 验证字段存在性、检查依赖关系、验证JSON结构
6. **性能优化** - 缓存管理、查询合并、数据量估算、资源控制

**代码的输出**：可执行的查询语句、处理后的数据、客观的统计报告

### 协作模式

```
用户问题 
  → [AI理解] → 结构化规格（语义级别）
  → [代码生成] → VizQL查询JSON（技术级别，参考tableau_sdk）
  → [代码执行] → 查询结果
  → [代码统计] → 统计报告
  → [AI解读] → 业务洞察
  → [AI决策] → 重规划建议
  → [代码验证] → [AI生成] → 新一轮规格
  → ...
```

### 关键原则

1. **AI做"理解"，代码做"执行"** - AI负责语义理解和决策，代码负责精确执行
2. **AI做"生成规格"，代码做"生成代码"** - AI生成意图描述，代码生成查询语句
3. **AI做"分析"，代码做"检测"** - AI分析业务含义，代码执行客观检测
4. **AI做"推荐"，代码做"验证"** - AI推荐方向，代码验证可行性
5. **AI做"灵活决策"，代码做"确定性控制"** - AI处理不确定性，代码保证稳定性

**参考项目的经验**：
- tableau_langchain项目最初使用AI生成VizQL查询，但发现准确率和稳定性不足
- 本项目改用纯代码规则，参考tableau_sdk的类型定义，确保查询100%正确

---

## 术语表

### 系统组件
- **Agent** - 需要LLM调用的智能组件，负责语义理解、决策和分析
- **Code Component** - 纯代码组件，负责确定性的执行和计算
- **LangGraph** - LangChain的图编排框架，提供状态管理和对话历史功能

### 7个Agent
- **Dimension Hierarchy Agent** - 维度层级推断Agent
- **Question Boost Agent** - 问题Boost Agent（可选，用户主动触发）
- **Understanding Agent** - 问题理解Agent（拆分子问题、提取关键信息）
- **Task Planner Agent** - 任务规划Agent（智能规划查询策略、字段映射）
- **Insight Agent** - 洞察Agent（贡献度分析、业务洞察）
- **Replanner Agent** - 重规划Agent（下钻维度查找、问题清单生成）
- **Summarizer Agent** - 总结Agent

### 核心概念
- **VizQL** - Tableau的VizQL Data Service查询语言
- **VDS** - VizQL Data Service，Tableau的数据查询服务
- **tableau_sdk** - TypeScript SDK（位于`sdks/tableau/`），提供VizQL的完整类型定义和Zod schema
  - **作用**：作为Python查询构建器的类型定义参考标准
  - **位置**：`sdks/tableau/apis/vizqlDataServiceApi.ts`
  - **内容**：Field、Filter、Query、Function枚举、FilterType枚举等完整类型定义
  - **使用方式**：Python查询构建器参考这些TypeScript类型创建对应的Pydantic模型
- **StructuredQuestionSpec** - 结构化问题规格（语义级别，包含dims、metrics、filters、sort_by等）
- **Dimension Hierarchy** - 维度层级（category、level、granularity、父子关系）
- **Stage** - 执行阶段（同stage内并行执行，不同stage顺序执行）
- **Replan** - 重新规划（根据分析结果动态生成新一轮任务）

**完整术语表**: [术语表详解](./appendix/technical-specs.md#术语表)

---

## 需求概览

本系统包含**16个需求**，分为4类：

### 预处理Agent（2个）
- **需求0**: 维度层级推断Agent
- **需求15**: 问题Boost Agent

### 查询流程Agent（5个）
- **需求1**: 问题理解Agent（拆分子问题、提取关键信息、评估复杂度）
- **需求2**: 任务规划Agent（智能规划查询策略、字段映射、生成查询规格）
- **需求5**: 洞察Agent（贡献度分析、业务洞察生成）
- **需求6**: 重规划Agent（下钻维度查找、问题清单生成）
- **需求7**: 总结Agent（整合结果、生成报告）

### 纯代码组件（6个）
- **需求3**: 任务调度器
- **需求4**: 数据合并器
- **需求8**: 查询构建器
- **需求9**: 查询执行器
- **需求10**: 统计检测器
- **需求11**: 元数据管理器

### 系统需求（5个）
- **需求12**: LangGraph工作流编排
- **需求13**: 提示词模板管理
- **需求14**: 前端UI重构（Vue 3 + TypeScript + Tableau Embedding API v3）
- **需求16**: Tableau临时viz可视化
- **需求17**: 看板初始化和自动执行机制（新增）

---

## 需求详情

### 需求 0: 维度层级推断Agent

**用户故事**: 作为系统，我需要在数据源首次访问时推断维度的层级关系和粒度，为后续的字段选择提供支持

**执行时机**:
- 数据源首次访问时（结果缓存24小时）
- **自动触发**: 当用户打开Tableau看板时，后台自动执行维度层级推断（如果缓存不存在或已过期）

#### 核心功能

1. **维度层级推断** - 根据字段元数据、统计信息和数据样例，推断每个维度的category、level、granularity、父子关系
2. **缓存策略** - 结果写入元数据的`dimension_hierarchy`字段，Redis缓存24小时
3. **Fallback机制** - LLM调用失败时，使用基于unique_count的默认规则
4. **性能优化** - 如果维度数量>100，分批并行推断（每批20个维度）
5. **自动执行机制** - 前端打开看板时，通过API触发后台异步执行维度层级推断（不阻塞用户交互）

#### 输入输出

**输入**（~5,500 tokens）：
- 维度字段列表 + 统计信息 + 数据样例（10行）

**输出**：
```json
{
  "dimension_hierarchy": {
    "地区": {
      "category": "地理",
      "level": 1,
      "granularity": "粗粒度",
      "parent_dimension": null,
      "child_dimension": "城市"
    }
  }
}
```

#### 验收标准

1. level_confidence >= 0.7 的维度占比 >= 80%
2. category推断准确率 >= 90%
3. 缓存命中率 >= 95%（24小时内）
4. 单次推断耗时 <= 3秒（50个维度以内）
5. **自动执行**: 用户打开看板后，后台自动触发维度层级推断（异步执行，不阻塞UI）
6. **前端集成**: 提供API端点供前端在看板加载时调用（如 `POST /api/metadata/init-hierarchy`）

**详细规格**: [需求0详细规格](./appendix/agent-requirements.md#需求0维度层级推断agent)

---

### 需求 1: 问题理解Agent

**用户故事**: 作为业务数据分析师，我希望系统能够理解我的问题意图，拆分子问题，提取关键信息，评估问题复杂度

#### 核心功能

1. **问题有效性验证** - 识别问题类型（数据分析 vs 操作指令 vs 定义查询）
2. **问题拆分** - 如果问题包含多个子问题，拆分为独立的子问题列表
3. **问题类型识别** - 对比、趋势、排名、诊断、多维分解、占比、同环比
4. **关键信息提取** - 时间范围、筛选条件、排序要求、TopN限制、时间粒度、聚合方式
5. **隐含需求识别** - 同比需要两个时间段、占比需要先计算总计等
6. **问题复杂度评估** - Simple/Medium/Complex

#### 输入输出

**输入**（~1,550 tokens）：用户问题 + 问题类型定义 + 提示词模板

**输出**（纯语义级别）：
```json
{
  "original_question": "2016年各地区的销售额和利润，按销售额降序",
  "sub_questions": ["2016年各地区的销售额和利润，按销售额降序"],
  "question_type": ["对比"],
  "time_range": {"type": "absolute", "year": 2016},
  "mentioned_dimensions": ["地区"],
  "mentioned_metrics": ["销售额", "利润"],
  "sort_requirement": "按销售额降序",
  "topn_requirement": null,
  "grain_requirement": null,
  "aggregation_intent": "求和",
  "complexity": "Simple",
  "implicit_requirements": ["需要排序", "降序排列"]
}
```

#### 验收标准

1. 问题类型识别准确率 >= 90%
2. 时间范围提取准确率 >= 95%
3. 隐含需求识别准确率 >= 85%
4. 响应时间 <= 2秒

**详细规格**: [需求1详细规格](./appendix/agent-requirements.md#需求1问题理解agent)

---

### 需求 2: 任务规划Agent

**用户故事**: 作为业务数据分析师，我希望系统能够根据问题复杂度智能规划查询策略，生成完整的查询规格

#### 核心功能

1. **智能规划策略** - 复杂问题生成1-2个现象确认查询（needs_replan=True），简单问题直接生成完整查询（needs_replan=False）
2. **完整字段映射** - 从元数据中匹配真实字段（fieldCaption、dataType、role、level），将自然语言维度名称映射到技术字段
3. **查询规格生成** - 生成完整的QuerySpec（fields、filters、reasoning），处理筛选条件的技术实现
4. **重规划问题处理** - 处理重规划Agent生成的自然语言问题清单，生成对应的查询规格
5. **查询可执行性保证** - 确保生成的查询规格可以被查询构建器正确转换为VizQL查询JSON

#### 重要说明：输出的是语义级别的Spec

**任务规划Agent的输出**：
- ✅ 字段名称（如"销售额"、"地区"）
- ✅ 聚合方式（如"sum"、"avg"）
- ✅ 筛选条件（如"订单日期=2016年"）
- ✅ 排序规则（如"按销售额降序"）
- ❌ **不包含**VizQL技术细节（如Field的JSON结构、Function枚举值、Filter的具体类型）

**VizQL查询JSON的生成**：
- 由查询构建器（纯代码）完成
- 参考tableau_sdk的类型定义（`sdks/tableau/apis/vizqlDataServiceApi.ts`）
- 将语义级别的Spec转换为技术级别的VizQL查询JSON

#### 输入输出

**输入**（~8,250 tokens）：
- 用户问题
- 问题理解结果
- 完整元数据（包含维度层级）
- VizQL查询能力说明

**输出**：
```json
{
  "queries": [
    {
      "question_id": "q1",
      "question_text": "2016年各地区的销售额，按销售额降序",
      "reasoning": "单个查询即可完成，选择粗粒度的地区维度",
      "fields": [
        {
          "fieldCaption": "地区",
          "dataType": "string",
          "role": "dimension",
          "level": 1
        },
        {
          "fieldCaption": "销售额",
          "dataType": "real",
          "role": "measure",
          "function": "SUM",
          "sortDirection": "DESC",
          "sortPriority": 1
        }
      ],
      "filters": [
        {
          "fieldCaption": "订单日期",
          "filterType": "QUANTITATIVE_DATE",
          "year": 2016
        }
      ]
    }
  ],
  "needs_replan": false,
  "replan_mode": null,
  "planning_reasoning": "简单问题，直接生成完整查询",
  "complexity": "Simple"
}
```

#### 验收标准

1. 字段选择准确率 >= 90%
2. 智能补全准确率 >= 85%（聚合、排序、筛选）
3. 拆分决策准确率 >= 90%（不该拆的不拆，该拆的拆对）
4. 依赖关系识别准确率 >= 95%
5. 响应时间 <= 2秒

**详细规格**: [需求2详细规格](./appendix/agent-requirements.md#需求2任务规划agent)

---

### 需求 3: 任务调度器（纯代码组件）

**用户故事**: 作为系统架构师，我希望有一个任务调度器来管理重规划后的问题清单执行

#### 核心功能

1. **任务接收** - 接收重规划Agent生成的问题清单，解析自然语言问题和建议，管理任务执行顺序
2. **流程调度** - 直接调用任务规划Agent处理自然语言问题（重规划已生成完整问题），管理查询构建器→执行器→统计检测器的流程
3. **并行处理** - 支持多个查询的并行执行，管理查询依赖关系，收集所有查询结果
4. **超时控制** - 动态超时时间（基于数据量和复杂度）
5. **失败处理** - 智能重试（指数退避）、降级策略、部分失败处理
6. **进度反馈** - 通过SSE实时推送执行进度

#### 验收标准

1. 并发执行正确性 100%（无竞态条件）
2. 超时控制准确率 >= 95%
3. 部分失败不影响整体流程
4. 进度反馈实时性 <= 1秒延迟

**详细规格**: [需求3详细规格](./appendix/code-component-requirements.md#需求3任务调度器)

---

### 需求 4: 数据合并器（纯代码组件）

**用户故事**: 作为业务数据分析师，我希望系统能够智能合并多个子任务的查询结果，自动处理数据对齐、补全和计算

#### 核心功能

1. **合并策略** - 第0轮：简单问题和复杂问题都不需要合并；第1轮及以后：多个查询结果需要合并（按维度合并或并列展示）
2. **合并策略选择** - Union/Join/Append/Pivot/Hierarchical（**基于代码规则，不使用AI**）
3. **数据对齐与补全** - 时间序列补点、维度组合补全
4. **数据去重与清洗** - 检测重复记录、异常值、空值处理
5. **聚合计算** - 总计、小计、平均值、占比、排名、累计
6. **数据质量评分** - 完整性、一致性、准确性、时效性

#### 重要说明：使用代码规则而非AI

**合并策略选择规则**（纯代码逻辑）：
- IF 所有子任务的维度列表相同 → Union（上下拼接）
- IF 子任务有公共维度且问题类型为"对比" → Join（横向连接）
- IF 子任务的时间范围不同且连续 → Append（追加）
- IF 问题类型为"同比"或"环比" → Join（按维度连接不同时间段）
- IF 子任务的维度存在层级关系 → Hierarchical（层级合并）
- ELSE → Union（默认策略）

**字段命名规则**（纯代码逻辑）：
- 同比/环比：使用"当期_销售额"、"上期_销售额"等命名
- 多时间段对比：使用"2016年_销售额"、"2015年_销售额"等命名
- 公共维度识别：直接匹配字段名称，不需要AI

#### 验收标准

1. 合并策略选择准确率 >= 95%
2. 数据对齐准确率 100%
3. 数据质量评分准确率 >= 90%
4. 合并耗时 <= 1秒（1000行以内）

**详细规格**: [需求4详细规格](./appendix/code-component-requirements.md#需求4数据合并器)

---

### 需求 5: 洞察Agent

**用户故事**: 作为业务数据分析师，我希望系统能够分析查询结果和统计检测结果，生成业务洞察

#### 核心功能

1. **数据分析** - 分析查询结果，计算贡献度，结合统计检测结果识别异常
2. **贡献度分析** - 计算各维度值的贡献百分比、排名贡献度（rank）、识别主要贡献因素
3. **洞察生成** - 生成自然语言描述、提供业务解读、识别关键发现、生成新问题列表
4. **职责边界** - 不判断是否可下钻（由重规划Agent负责）

#### 输入输出

**输入**（~4,050 tokens）：子任务问题 + VizQL查询结果（智能采样） + 统计报告 + 上下文信息

**输出**：
```json
{
  "key_findings": ["华东地区销售额最高，占总销售额的35%"],
  "metrics": {"total_sales": 1000000, "avg_sales": 250000},
  "contribution_analysis": [
    {
      "dimension": "地区",
      "dimension_value": "华东",
      "contribution_percentage": 35.0,
      "contribution_absolute": 350000,
      "rank": 1,
      "significance": "high"
    }
  ],
  "anomalies": ["华东地区利润率异常低（5%），远低于平均水平（15%）"],
  "trends": ["销售额呈上升趋势"],
  "answered_questions": ["2016年各地区的销售额分布"],
  "new_questions": ["华东地区利润率为什么这么低？"],
  "insight_reasoning": "基于贡献度分析和统计检测结果"
}
```

#### 验收标准

1. 关键发现识别准确率 >= 85%
2. 异常解释合理性 >= 80%
3. 行动建议可执行性 >= 75%
4. 响应时间 <= 2秒

**详细规格**: [需求5详细规格](./appendix/agent-requirements.md#需求5洞察agent)

---

### 需求 6: 重规划Agent

**用户故事**: 作为业务数据分析师，我希望系统能够基于洞察结果智能决策下一步分析方向，自动查找下钻维度

#### 核心功能

1. **重规划决策（多轮迭代控制）** 
   - 评估分析完整性，决定是否继续（should_replan）
   - 判断重规划类型（drill_down、dimension_expansion等）
   - 支持多轮重规划，直到分析完整或达到最大轮数限制
   - 轮次控制由环境变量`MAX_REPLAN_ROUNDS`配置（默认3轮）
   
2. **下钻维度查找** 
   - 基于贡献度分析选择下钻目标
   - 从metadata/dimension_hierarchy查找子维度
   - 确定下钻的可行性（child_dimension是否存在）
   
3. **问题清单生成** 
   - 生成自然语言问题
   - 提供建议的维度、筛选条件、度量
   - 为任务调度器提供完整的问题清单

#### 重规划轮次控制说明

**关键概念区分**：

1. **needs_replan**（任务规划Agent设置）：
   - 这是**初始标志**，由问题复杂度决定
   - Complex问题：第0轮设置needs_replan=true（需要探索式分析）
   - 第1轮及以后：都是needs_replan=false（处理具体问题，不需要探索）

2. **should_replan**（重规划Agent决策）：
   - 这是**每轮的决策**，由重规划Agent根据分析结果决定
   - 每轮执行后，重规划Agent评估是否需要继续
   - 可以多轮重规划，直到分析完整或达到最大轮数

**多轮重规划流程**：

```
第0轮（初始查询）:
  - 任务规划Agent: needs_replan=true, replan_mode="exploratory"
  - 执行查询 → 洞察 → 重规划Agent决策
  ↓
第1轮（第一次重规划）:
  - 重规划Agent: should_replan=true → 生成问题清单
  - 任务规划Agent处理问题: needs_replan=false
  - 执行查询 → 洞察 → 重规划Agent再次决策
    ├─ 如果发现新异常或分析不完整 → should_replan=true → 继续第2轮
    └─ 如果分析完整 → should_replan=false → 结束
  ↓
第2轮（第二次重规划）:
  - 重规划Agent: should_replan=true → 生成新问题清单
  - 任务规划Agent处理问题: needs_replan=false
  - 执行查询 → 洞察 → 重规划Agent再次决策
    ├─ 如果还需要继续 → should_replan=true → 继续第3轮
    └─ 如果达到最大轮数限制 → 强制结束
  ↓
...继续迭代，直到：
  1. 重规划Agent决定should_replan=false（分析完整）
  2. 达到最大轮数限制（环境变量MAX_REPLAN_ROUNDS，默认3）
```

**重规划决策逻辑**：

```python
# 重规划Agent的决策逻辑
def replanner_agent(insights, round_num, max_rounds):
    # 1. 检查是否达到最大轮数
    if round_num >= max_rounds:
        return {
            "should_replan": False,
            "reasoning": "已达到最大重规划轮数限制",
            "max_rounds_reached": True
        }
    
    # 2. 评估分析完整性
    completeness = evaluate_completeness(insights)
    
    # 3. 检查是否有新的异常或未解答的问题
    has_new_anomalies = check_new_anomalies(insights)
    has_unanswered_questions = check_unanswered_questions(insights)
    
    # 4. 决策
    if completeness >= 0.8 and not has_new_anomalies:
        return {
            "should_replan": False,
            "reasoning": "分析已完整，无需继续"
        }
    
    if has_new_anomalies or has_unanswered_questions:
        return {
            "should_replan": True,
            "reasoning": "发现新异常或未解答问题，需要继续分析",
            "new_questions": generate_questions(insights)
        }
    
    return {
        "should_replan": False,
        "reasoning": "无明显需要继续分析的方向"
    }
```

#### 输入输出

**输入**（~5,250 tokens）：原始问题 + 问题理解结果 + 数据摘要 + 关键发现摘要

**输出**：
```json
{
  "should_replan": true,
  "replan_type": "drill_down",
  "drill_down_target": {
    "parent_dimension": "地区",
    "parent_value": "华东",
    "child_dimension": "城市",
    "can_drill_down": true
  },
  "new_questions": [
    "华东地区各城市的销售额和利润率分别是多少？",
    "华东地区各产品类别的利润率分别是多少？"
  ],
  "suggested_dimensions": ["城市", "产品类别"],
  "suggested_filters": ["地区=华东"],
  "suggested_metrics": ["销售额", "利润率"],
  "reasoning": "华东地区贡献度最高但利润率异常低，需要下钻到城市和产品类别进行分析",
  "confidence": 0.9,
  "max_rounds_reached": false,
  "current_round": 1,
  "completeness_score": 0.4
}
```

**多轮重规划示例**：

```
问题："为什么华东地区利润率低？"

第0轮（初始查询）:
  - 查询：各地区利润率
  - 洞察：华东利润率5%，平均15%，异常低
  - 重规划决策：
    - should_replan: true
    - current_round: 0
    - completeness_score: 0.3
    - new_questions: ["华东各城市的利润率分别是多少？"]
  ↓
第1轮（第一次重规划）:
  - 查询：华东各城市利润率
  - 洞察：上海利润率3%，异常低；杭州利润率8%，正常
  - 重规划决策：
    - should_replan: true（发现上海异常）
    - current_round: 1
    - completeness_score: 0.5
    - new_questions: ["上海各产品类别的利润率分别是多少？"]
  ↓
第2轮（第二次重规划）:
  - 查询：上海各产品类别利润率
  - 洞察：家具类利润率-2%，亏损；其他类别正常
  - 重规划决策：
    - should_replan: true（发现家具类亏损）
    - current_round: 2
    - completeness_score: 0.7
    - new_questions: ["上海家具类的成本和折扣情况如何？"]
  ↓
第3轮（第三次重规划）:
  - 查询：上海家具类成本和折扣
  - 洞察：折扣率高达40%，远超平均20%
  - 重规划决策：
    - should_replan: false（找到根因，分析完整）
    - current_round: 3
    - completeness_score: 0.9
    - reasoning: "找到根本原因：上海家具类折扣过高导致亏损"
  ↓
总结：华东利润率低的根本原因是上海家具类折扣过高导致亏损
```

**重规划类型说明**（replan_type）：
- `drill_down`：维度下钻（更细粒度，如从"地区"到"城市"）
- `drill_up`：维度上卷（更粗粒度，如从"门店"到"地区"）
- `pivot`：横向对比（切换维度，如从"地区"到"产品类别"）
- `metric_expansion`：指标扩展（增加度量，如增加"利润率"）
- `time_adjustment`：时间窗口调整（如从"年"到"月"）
- `anomaly_focus`：异常聚焦（深入异常，如聚焦"华东地区"）
- `related_question`：相关问题探索（探索相关维度）
- `mixed`：混合类型（多种类型组合）

#### 验收标准

1. 重规划决策准确率 >= 85%
2. 新问题质量评分 >= 80%
3. 轮次控制准确率 100%（正确执行MAX_REPLAN_ROUNDS限制）
4. 完整性评估准确率 >= 80%
5. 响应时间 <= 2秒

#### 环境变量配置

- `MAX_REPLAN_ROUNDS`: 最大重规划轮数（默认3）
- `MIN_COMPLETENESS_SCORE`: 最小完整性分数阈值（默认0.8）
- `ENABLE_FORCED_STOP`: 是否启用强制停止（默认true）

**详细规格**: [需求6详细规格](./appendix/agent-requirements.md#需求6重规划agent)

---

### 需求 7: 总结Agent

**用户故事**: 作为业务数据分析师，我希望系统能够整合所有结果，生成结构化、易理解的分析报告

#### 核心功能

1. **结果整合** - 去重和排序关键发现
2. **执行摘要生成** - 一句话回答原始问题
3. **分析路径回顾** - 展示分析思路和过程
4. **后续探索建议** - 推荐深入分析方向

#### 输入输出

**输入**（~4,050 tokens）：原始问题 + 关键发现摘要（去重后） + 重规划历史

**输出**：
```json
{
  "executive_summary": "2016年华东地区销售额最高但利润率偏低...",
  "analysis_path": ["总体对比", "异常发现", "深入分析"],
  "next_suggestions": [...]
}
```

#### 验收标准

1. 执行摘要准确性 >= 90%
2. 分析路径完整性 100%
3. 后续建议质量评分 >= 80%
4. 响应时间 <= 2秒

**详细规格**: [需求7详细规格](./appendix/agent-requirements.md#需求7总结agent)

---

### 需求 8: 查询构建器（纯代码组件）

**用户故事**: 作为系统，我需要根据StructuredQuestionSpec生成符合VDS规范的VizQL查询JSON，确保查询100%正确

#### 核心功能

1. **查询生成** - 根据语义级别的Spec生成技术级别的VizQL查询JSON（使用代码模板和规则，**不使用AI**）
2. **类型定义参考** - 严格参考tableau_sdk的TypeScript类型定义，确保生成的查询100%符合VizQL规范
3. **日期值计算** - 相对时间计算、同比时间计算、环比时间计算（纯代码逻辑）
4. **查询验证** - 基于tableau_sdk的Zod schema验证查询合法性
5. **Builder模式** - 不同类型的查询使用不同的Builder（如BasicQueryBuilder、TimeComparisonBuilder等）
6. **规则说明** - 记录使用的规则和口径（rule_notes字段）

#### tableau_sdk的关键作用

**tableau_sdk** (`sdks/tableau/apis/vizqlDataServiceApi.ts`) 是查询构建器的**类型定义参考标准**，提供：

**✅ 完整的VizQL类型定义**：
- `Field`: 基础字段、函数字段、计算字段的类型定义
- `Filter`: 6种Filter类型（SetFilter、TopNFilter、MatchFilter、QuantitativeNumericalFilter、QuantitativeDateFilter、RelativeDateFilter）
- `Query`: 完整的查询结构（fields + filters）
- `Datasource`: 数据源连接信息

**✅ 所有支持的枚举值**：
- `Function`: SUM、AVG、MEDIAN、COUNT、COUNTD、MIN、MAX、STDEV、VAR、COLLECT、YEAR、QUARTER、MONTH、WEEK、DAY、TRUNC_YEAR、TRUNC_QUARTER、TRUNC_MONTH、TRUNC_WEEK、TRUNC_DAY、AGG、NONE、UNSPECIFIED
- `SortDirection`: ASC、DESC
- `ReturnFormat`: OBJECTS、ARRAYS
- `FilterType`: SET、TOP、MATCH、QUANTITATIVE_NUMERICAL、QUANTITATIVE_DATE、DATE

**✅ Zod schema用于验证**：
- 每个类型都有对应的Zod schema
- 可以验证生成的查询JSON是否符合规范
- 提供详细的错误信息

#### 实现方式

**Python实现参考TypeScript类型**：
1. 创建对应的Python Pydantic模型（严格对应tableau_sdk的TypeScript类型）
2. 使用代码规则和模板生成VizQL查询JSON
3. 使用Pydantic验证生成的查询结构
4. 确保生成的查询100%符合VDS规范

**示例**：
```python
# Python Pydantic模型（参考tableau_sdk的TypeScript类型）
from pydantic import BaseModel, Field as PydanticField
from typing import Literal, Union, Optional, List
from enum import Enum

class FunctionEnum(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    YEAR = "YEAR"
    MONTH = "MONTH"
    # ... 其他Function

class SortDirection(str, Enum):
    ASC = "ASC"
    DESC = "DESC"

class FieldBase(BaseModel):
    fieldCaption: str
    fieldAlias: Optional[str] = None
    maxDecimalPlaces: Optional[int] = None
    sortDirection: Optional[SortDirection] = None
    sortPriority: Optional[int] = None

class BasicField(FieldBase):
    pass

class FunctionField(FieldBase):
    function: FunctionEnum

class CalculationField(FieldBase):
    calculation: str

# Union类型（对应TypeScript的union）
VizQLField = Union[BasicField, FunctionField, CalculationField]

# ... 其他类型定义
```

#### 验收标准

1. 查询生成准确率 100%（纯代码规则，不使用AI）
2. 日期计算准确率 100%（纯代码逻辑）
3. 类型定义100%对应tableau_sdk的TypeScript类型
4. 查询验证覆盖率 >= 95%（基于Pydantic模型验证）
5. 生成耗时 <= 0.1秒

**详细规格**: [需求8详细规格](./appendix/code-component-requirements.md#需求8查询构建器)

---

### 需求 9: 查询执行器（纯代码组件）

**用户故事**: 作为系统，我需要调用VDS API执行查询，处理分页和错误，确保查询稳定可靠

#### 核心功能

1. **查询执行** - 调用Tableau VDS API执行查询
2. **分页处理** - 自动获取所有页（每页最多10000行）
3. **错误处理** - 重试机制（指数退避）、超时控制
4. **结果解析** - 解析VDS响应，转换为DataFrame

#### 验收标准

1. 查询成功率 >= 99%
2. 分页处理准确率 100%
3. 错误恢复成功率 >= 90%
4. 查询耗时 <= 10秒（取决于数据量）

**详细规格**: [需求9详细规格](./appendix/code-component-requirements.md#需求9查询执行器)

---

### 需求 10: 统计检测器（纯代码组件）

**用户故事**: 作为系统，我需要对查询结果进行客观的统计分析，检测异常值和趋势，为AI提供分析依据

#### 核心功能

1. **描述性统计** - 均值、中位数、标准差、分位数
2. **异常检测** - Z-score、IQR、MAD、孤立森林
3. **趋势分析** - 线性回归、Mann-Kendall检验
4. **数据质量检查** - 完整性、一致性、准确性

#### 验收标准

1. 统计计算准确率 100%
2. 异常检测准确率 >= 85%
3. 趋势分析准确率 >= 90%
4. 计算耗时 <= 0.5秒（1000行以内）

**详细规格**: [需求10详细规格](./appendix/code-component-requirements.md#需求10统计检测器)

---

### 需求 11: 元数据管理器（纯代码组件）

**用户故事**: 作为系统，我需要获取和缓存数据源元数据，为Agent提供字段信息

#### 核心功能

1. **元数据获取** - 通过Tableau Metadata API获取字段列表、类型、统计信息
2. **缓存管理** - Redis缓存（基础元数据1小时，维度层级24小时）
3. **数据源查找** - 支持精确匹配、模糊匹配、去括号匹配
4. **元数据增强** - 调用维度层级推断Agent，将结果写入元数据

#### 验收标准

1. 元数据获取成功率 >= 99%
2. 缓存命中率 >= 90%
3. 数据源查找准确率 >= 95%
4. 元数据增强成功率 >= 95%

**详细规格**: [需求11详细规格](./appendix/code-component-requirements.md#需求11元数据管理器)

---

### 需求 12: LangGraph工作流编排

**用户故事**: 作为系统架构师，我需要使用LangGraph编排7个Agent的工作流，实现状态管理、错误恢复、流式输出

#### 核心功能

1. **工作流定义** - 定义节点（7个Agent + 6个代码组件）和边（流转逻辑）
2. **状态管理** - 使用LangGraph的StateGraph管理状态
3. **对话历史** - 利用LangGraph的MemorySaver管理对话历史
4. **条件路由** - 根据重规划决策选择路径（replan vs compose）
5. **检查点机制** - 支持中断和恢复

#### 验收标准

1. 工作流执行正确性 100%
2. 状态管理一致性 100%
3. 错误恢复成功率 >= 90%
4. 流式输出延迟 <= 1秒

**详细规格**: [需求12详细规格](./appendix/system-requirements.md#需求12langgraph工作流编排)

---

### 需求 13: 提示词模板管理

**用户故事**: 作为系统维护者，我希望所有给LLM使用的提示词都以文本形式存储在prompts.py中，便于维护和版本控制

#### 核心功能

1. **模板存储** - 所有LLM提示词集中存储在prompts.py中（包括7个Agent提示词、2个规则模板）
2. **模板分类** - 明确区分：
   - **Agent提示词（7个）**：直接作为prompt发送给LLM
     - `DIMENSION_HIERARCHY_AGENT_TEMPLATE` - 维度层级推断Agent
     - `QUESTION_BOOST_AGENT_TEMPLATE` - 问题Boost Agent
     - `UNDERSTANDING_AGENT_TEMPLATE` - 问题理解Agent
     - `TASK_PLANNER_AGENT_TEMPLATE` - 任务规划Agent
     - `INSIGHT_AGENT_TEMPLATE` - 洞察Agent
     - `REPLANNER_AGENT_TEMPLATE` - 重规划Agent
     - `SUMMARIZER_AGENT_TEMPLATE` - 总结Agent
   - **规则模板（2个）**：嵌入到**任务规划Agent**提示词中
     - `COMMON_FIELD_NAME_RULES` - 字段名必须精确匹配元数据中的字段名
     - `VIZQL_CAPABILITIES_SUMMARY` - VizQL查询能力摘要（**仅语义级别**，不包含技术细节）
3. **模板命名** - 清晰的命名规范（`<AGENT_NAME>_AGENT_TEMPLATE`、`COMMON_<RULE_NAME>_RULES`）
4. **模板版本控制** - 使用Git管理提示词变更
5. **模板测试** - 提供测试用例验证提示词效果

#### 重要说明：AI与代码的职责边界

**✅ AI的职责（在提示词中说明）**：
- 理解用户问题的业务意图
- 从元数据中选择正确的字段（dims、metrics）
- 生成语义级别的StructuredQuestionSpec（包含字段名、聚合方式、筛选条件等）
- 决定是否需要拆分子任务
- 对查询结果进行业务解读和洞察生成

**❌ 不在提示词中说明的内容（由代码完成）**：
- **VizQL查询JSON的生成**：由查询构建器（纯代码）完成，参考tableau_sdk的类型定义
- **VizQL技术细节**：如Field的具体结构、Filter的具体类型、Function的枚举值等
- **数据合并策略**：由数据合并器（纯代码）完成
- **查询验证规则**：由查询构建器（纯代码）完成

**VIZQL_CAPABILITIES_SUMMARY的内容**：
- ✅ 说明VizQL支持多维度、多度量、多筛选（语义级别）
- ✅ 说明什么情况下需要拆分、什么情况下不需要拆分（决策指南）
- ❌ 不包含Field、Filter的具体JSON结构
- ❌ 不包含Function枚举值的完整列表
- ❌ 不包含查询验证规则

#### 验收标准

1. 所有提示词集中管理 100%
2. 命名规范遵守率 100%
3. 版本控制覆盖率 100%
4. 模板测试覆盖率 >= 80%
5. 提示词中不包含VizQL技术细节 100%

**详细规格**: [需求13详细规格](./appendix/system-requirements.md#需求13提示词模板管理)

---

### 需求 14: 前端UI重构（Vue 3 + TypeScript）

**用户故事**: 作为业务数据分析师，我希望看到像ChatGPT一样流畅的对话界面，像Perplexity一样清晰的分析过程，像ThoughtSpot一样直观的数据展示

#### 核心功能

1. **对话界面** - Token级流式输出、Markdown渲染、代码高亮
2. **分析过程展示** - 展示7个Agent的执行过程和结果
3. **数据可视化** - 表格、原生图表、下钻交互
4. **进度反馈** - 实时显示执行进度（SSE）
5. **重规划交互** - 展示推荐问题、支持一键执行

#### 验收标准

1. 流式输出流畅度 >= 90%（无卡顿）
2. 分析过程可视化完整性 100%
3. 数据可视化准确性 100%
4. 进度反馈实时性 <= 1秒延迟

**详细规格**: [需求14详细规格](./appendix/system-requirements.md#需求14前端ui重构)

---

### 需求 15: 问题Boost Agent

**用户故事**: 作为业务数据分析师，我希望系统能够帮我优化模糊的问题，使其更加精确和可执行

#### 核心功能

1. **问题优化** - 将模糊的问题转换为更精确的表达
2. **问题补全** - 自动补充缺失的关键信息（时间范围、维度、度量）
3. **多个建议** - 提供3-5个相关的问题建议
4. **上下文感知** - 基于数据源元数据和对话历史优化问题

#### 输入输出

**输入**（~2,000 tokens）：
- 用户原始问题
- 数据源元数据（维度、度量、维度层级）
- 对话历史（可选）

**输出**：
```json
{
  "boosted_question": "最近一个月各地区的销售额、订单量和客户数分别是多少？",
  "suggestions": [
    "最近一个月销售额TOP10的门店是哪些？",
    "最近一个月各产品类别的销售额占比",
    "最近一个月的销售额趋势（按日统计）"
  ],
  "reasoning": "原问题过于宽泛，补充了时间范围、维度和度量"
}
```

#### 验收标准

1. 优化准确率 >= 85%
2. 建议相关性 >= 80%
3. 响应时间 <= 2秒
4. 用户采纳率 >= 60%

**详细规格**: [需求15详细规格](./appendix/system-requirements.md#需求15问题boost功能)

---

### 需求 16: Tableau临时viz可视化

**用户故事**: 作为业务数据分析师，我希望看到专业的Tableau可视化图表，而不仅仅是表格

#### 核心功能

1. **临时viz创建** - 使用Tableau REST API + Hyper API创建临时工作簿
2. **Tableau嵌入** - 使用Tableau Embedding API v3嵌入viz
3. **自动清理** - 临时viz在1小时后自动过期删除
4. **图表导出** - 支持导出viz为图片

#### 技术方案

**后端**：
- 使用VizQL查询获取数据
- 使用Tableau Hyper API创建临时数据源
- 使用Tableau REST API发布临时工作簿
- 生成带JWT token的嵌入URL

**前端**：
- 使用Tableau Embedding API v3嵌入viz
- 支持表格和viz两种视图切换

#### 验收标准

1. viz创建成功率 >= 95%
2. viz加载时间 <= 5秒
3. 自动清理准确率 100%
4. 图表导出成功率 >= 95%

**详细规格**: [需求14详细规格 - 数据可视化部分](./appendix/system-requirements.md#需求14前端ui重构)

---

## 性能总结

### Token消耗（单次查询，3个子任务，1轮重规划）

| Agent | Token消耗 | 调用次数 | 总Token |
|-------|----------|---------|---------|
| 维度层级推断 | 5,500 | 0（缓存） | 0 |
| 问题Boost | 2,000 | 0（可选） | 0 |
| 问题理解 | 1,550 | 2 | 3,100 |
| 任务规划 | 8,250 | 2 | 16,500 |
| 洞察Agent | 4,050 | 5 | 20,250 |
| 重规划 | 5,250 | 2 | 10,500 |
| 总结 | 4,050 | 1 | 4,050 |
| **总计** | - | **12** | **54,400** |

**注**：问题Boost Agent是可选的，用户主动触发时才调用，不计入常规流程的token消耗

**单次最大token**: 8,250（任务规划Agent，20%上下文）✅

**优化说明**：合并字段选择和任务拆分后，减少了2次LLM调用，节省~5,700 tokens

### 时间消耗（单次查询，3个子任务，1轮重规划）

| 阶段 | 耗时 | 说明 |
|------|------|------|
| 问题理解 | 2秒 | LLM调用 |
| 任务规划 | 2秒 | LLM调用 |
| 查询执行（3个并行） | 5秒 | VDS API调用 |
| 洞察生成（3个并行） | 2秒 | LLM调用（并行） |
| 数据合并 | 1秒 | 纯代码 |
| 重规划决策 | 2秒 | LLM调用 |
| **第1轮小计** | **14秒** | - |
| 第2轮（重规划） | 12秒 | 同上 |
| 总结 | 2秒 | LLM调用 |
| **总计** | **28秒** | - |

**优化说明**：合并字段选择和任务拆分后，每轮节省2秒，总计节省4秒

**注**：问题Boost Agent是可选的，用户主动触发时增加约2秒

**用户体验**: 通过SSE实时推送进度，用户可以看到每个阶段的执行状态

### 优化策略

1. **缓存优化** - 维度层级缓存24小时，元数据缓存1小时，查询结果缓存
2. **并行优化** - 同stage内的子任务并行执行，洞察Agent并行调用
3. **Token优化** - 元数据精简、数据采样、摘要传递
4. **失败处理** - 智能重试、降级策略、部分失败不影响整体流程

**详细说明**: [性能优化详解](./appendix/technical-specs.md#性能优化)

---

## 附录索引

- [Agent详细规格](./appendix/agent-requirements.md) - 7个Agent的详细验收标准、提示词设计、输入输出示例
- [代码组件详细规格](./appendix/code-component-requirements.md) - 6个代码组件的详细实现规格
- [系统需求详细规格](./appendix/system-requirements.md) - LangGraph编排、提示词管理、前端UI
- [技术规格](./appendix/technical-specs.md) - 数据模型、缓存架构、性能优化、数据采样策略
- [VizQL查询能力详解](./appendix/vizql-capabilities.md) - VizQL的能力边界、问题拆分决策指南
- [用户场景和示例](./appendix/user-scenarios.md) - 典型用户场景、端到端示例

---

**需求文档版本**: v2.0 (精简版)
**最后更新**: 2025-10-30
**文档状态**: 待审核


---

### 需求 17: 看板初始化和自动执行机制（新增）

**用户故事**: 作为Tableau看板用户，当我打开看板时，系统应该自动在后台准备好数据源的元数据和维度层级信息，确保后续的问题分析能够快速响应

**执行时机**: 用户打开Tableau看板时自动触发

#### 核心功能

1. **看板加载检测** - 前端检测看板加载完成事件
2. **数据源识别** - 自动识别当前看板使用的数据源LUID
3. **后台初始化** - 异步调用后端API初始化元数据和维度层级
4. **进度反馈** - 向用户显示初始化进度（可选，不阻塞交互）
5. **错误处理** - 初始化失败时使用fallback机制，不影响用户使用

#### 技术实现

**前端（Vue 3 + Tableau Extension API）**：
```typescript
// 1. 监听看板加载完成事件
tableau.extensions.initializeAsync().then(() => {
  // 2. 获取当前数据源
  const datasources = tableau.extensions.dashboardContent.dashboard.worksheets
    .flatMap(ws => ws.getDataSourcesAsync());

  // 3. 对每个数据源调用初始化API
  datasources.forEach(ds => {
    fetch('/api/metadata/init-hierarchy', {
      method: 'POST',
      body: JSON.stringify({ datasource_luid: ds.id })
    });
  });
});
```

**后端（FastAPI）**：
```python
@app.post("/api/metadata/init-hierarchy")
async def init_hierarchy(payload: Dict[str, Any]):
    """
    异步初始化数据源的维度层级
    - 检查缓存是否存在
    - 如果不存在，后台异步执行维度层级推断
    - 立即返回，不阻塞前端
    """
    datasource_luid = payload.get("datasource_luid")

    # 创建后台任务
    background_tasks.add_task(
        ensure_dimension_hierarchy,
        datasource_luid
    )

    return {"status": "initializing", "datasource_luid": datasource_luid}

async def ensure_dimension_hierarchy(datasource_luid: str):
    """确保维度层级存在（后台任务）"""
    metadata_manager = create_metadata_manager(
        dimension_hierarchy_agent=create_dimension_hierarchy_agent()
    )

    # get_metadata(enhance=True) 会自动处理：
    # - 如果有缓存 → 直接返回
    # - 如果没有缓存 → 调用维度层级Agent生成并缓存
    metadata_manager.get_metadata(
        datasource_luid,
        use_cache=True,
        enhance=True
    )
```

#### 工作流程

```
用户打开看板
  ↓
前端: Tableau Extension初始化
  ↓
前端: 获取数据源列表
  ↓
前端: 调用 POST /api/metadata/init-hierarchy (异步)
  ↓
后端: 检查缓存
  ├─ 有缓存 → 立即返回（无需执行）
  └─ 无缓存 → 后台执行维度层级推断 → 缓存24小时
  ↓
用户开始提问
  ↓
后端: 使用已缓存的维度层级信息（快速响应）
```

#### 验收标准

1. **自动触发**: 看板加载后自动调用初始化API（100%）
2. **异步执行**: 初始化不阻塞前端交互（响应时间 < 100ms）
3. **缓存优先**: 如果缓存存在，不重复执行（缓存命中率 >= 95%）
4. **错误容忍**: 初始化失败不影响用户使用（使用fallback机制）
5. **性能优化**: 后台执行完成时间 <= 5秒（50个维度以内）

#### 配置选项

**环境变量**：
- `AUTO_INIT_HIERARCHY`: 是否启用自动初始化（默认true）
- `INIT_HIERARCHY_TIMEOUT`: 初始化超时时间（默认30秒）
- `SHOW_INIT_PROGRESS`: 是否显示初始化进度（默认false）

#### 注意事项

1. **不阻塞用户**: 初始化必须是异步的，不能阻塞用户交互
2. **优雅降级**: 如果初始化失败，系统应该使用fallback机制（基于unique_count的规则）
3. **避免重复执行**: 使用缓存避免重复推断同一数据源
4. **多数据源支持**: 一个看板可能使用多个数据源，需要分别初始化
5. **前端兼容性**: 需要等前端开发完成后再实现此功能

**详细规格**: 待前端开发完成后补充

---

## 性能总结

### Token消耗预估

| Agent/组件 | 单次Token消耗 | 调用频率 | 总Token |
|-----------|--------------|---------|---------|
| 维度层级推断 | ~5,500 | 首次访问 | ~5,500 |
| 问题Boost | ~2,000 | 可选 | ~2,000 |
| 问题理解 | ~1,550 | 每次提问 | ~1,550 |
| 任务规划 | ~8,250 | 每次提问 | ~8,250 |
| 洞察Agent | ~4,050 | 每个子任务 | ~12,150 (3个子任务) |
| 重规划 | ~5,250 | 可选 | ~5,250 |
| 总结 | ~4,050 | 每次提问 | ~4,050 |
| **总计** | - | - | **~38,750** |

### 响应时间预估

| 阶段 | 预估时间 | 说明 |
|------|---------|------|
| 维度层级推断 | 3-5秒 | 首次访问，后续使用缓存 |
| 问题理解 | 1-2秒 | 每次提问 |
| 查询规划 | 1-2秒 | 每次提问 |
| 查询执行 | 2-5秒 | 取决于数据量 |
| 洞察生成 | 1-2秒 | 每个子任务 |
| 总结 | 1-2秒 | 每次提问 |
| **总计** | **8-15秒** | 不含重规划 |

---

## 实施状态

**当前阶段**: 阶段3 - Agent开发
**总体进度**: 约 20%

### 已完成 ✅
- ✅ **需求0**: 维度层级推断Agent（已完成并测试）
- ✅ **需求15**: 问题Boost Agent（已完成并优化）
- ✅ **需求11**: 元数据管理器（已完成并集成）
- ✅ **需求13**: 提示词模板管理（已完成）

### 进行中 🔄
- 🔄 **需求8**: 查询构建器（基础框架已创建，待完善）

### 待开始 ⏳
- ⏳ **需求1**: 问题理解Agent
- ⏳ **需求2**: 任务规划Agent
- ⏳ **需求3**: 任务调度器
- ⏳ **需求4**: 数据合并器
- ⏳ **需求5**: 洞察Agent
- ⏳ **需求6**: 重规划Agent
- ⏳ **需求7**: 总结Agent
- ⏳ **需求9**: 查询执行器
- ⏳ **需求10**: 统计检测器
- ⏳ **需求12**: LangGraph工作流编排
- ⏳ **需求14**: 前端UI重构
- ⏳ **需求16**: Tableau临时viz可视化
- ⏳ **需求17**: 看板初始化和自动执行机制

**详细进度**: 参见 [PROGRESS.md](./PROGRESS.md)

---

**文档版本**: v1.1
**最后更新**: 2025-10-30
**状态**: 进行中 - 阶段3 Agent开发
