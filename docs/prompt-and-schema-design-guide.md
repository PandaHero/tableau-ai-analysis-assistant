# Prompt 与数据模型设计指南

> 基于 Cursor、Windsurf、Devin AI、v0、Cline 等顶级 AI 工具的设计模式分析

## 目录

1. [LLM 理解与生成原理](#1-llm-理解与生成原理)
2. [顶级 AI 工具的设计模式分析](#2-顶级-ai-工具的设计模式分析)
3. [Prompt 与 Schema 的分工](#3-prompt-与-schema-的分工)
4. [设计方法论](#4-设计方法论)
5. [完整设计方案](#5-完整设计方案)
6. [LangChain 实现模板](#6-langchain-实现模板)
7. [与你现有系统的对比](#7-与你现有系统的对比)
8. [迁移建议](#8-迁移建议)
9. [总结](#9-总结)

---

## 1. LLM 理解与生成原理

### 1.1 LLM 不是"理解"，而是"模式匹配 + 概率预测"

```
输入 Token 序列 → Transformer 编码 → 注意力权重计算 → 逐 Token 生成输出
```

**关键洞察**：
- LLM 通过**上下文窗口**中的所有 token 来预测下一个 token
- 它不"理解"你的意图，而是找到**训练数据中最相似的模式**
- Prompt 的作用是**激活正确的模式**，Schema 的作用是**约束输出格式**

### 1.2 LLM 生成 JSON 的过程

当你要求 LLM 输出 JSON 时，它实际上是这样工作的：

```
Step 1: 看到 "输出 JSON 格式" → 激活 JSON 生成模式
Step 2: 看到 Schema 定义 → 记住字段名和类型
Step 3: 看到用户问题 → 提取关键信息
Step 4: 逐 token 生成 → {"intent": "DATA_QUERY", "dimensions": [...
        ↑
        每个 token 的生成都受到：
        - Prompt 中的规则约束
        - Schema 中的结构约束
        - 用户问题中的信息
```

### 1.3 为什么 Prompt 和 Schema 要分离？

| 混在一起的问题 | 分离后的好处 |
|--------------|-------------|
| LLM 需要同时处理"怎么想"和"怎么输出" | 思考和输出分开，降低认知负担 |
| 修改规则可能破坏格式 | 独立迭代，互不影响 |
| 难以调试哪里出问题 | 问题定位更清晰 |
| Token 浪费在重复的格式说明上 | Schema 只需定义一次 |

---

## 2. 顶级 AI 工具的设计模式分析

通过深入分析 Cursor、Windsurf、Devin AI、v0、Cline 等工具的 prompt 设计，我总结出以下核心设计模式：

### 2.1 共同的架构模式

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        顶级 AI 工具的 Prompt 架构                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐           │
│  │   身份定义       │   │   能力边界       │   │   行为规范       │           │
│  │   (Identity)    │   │   (Capabilities) │   │   (Guidelines)  │           │
│  └────────┬────────┘   └────────┬────────┘   └────────┬────────┘           │
│           │                     │                     │                     │
│           └─────────────────────┼─────────────────────┘                     │
│                                 ▼                                           │
│                    ┌─────────────────────────┐                              │
│                    │      工具定义            │                              │
│                    │   (Tool Definitions)    │                              │
│                    │   - 名称 + 描述          │                              │
│                    │   - 参数 Schema          │                              │
│                    │   - 使用示例             │                              │
│                    └────────────┬────────────┘                              │
│                                 │                                           │
│                                 ▼                                           │
│                    ┌─────────────────────────┐                              │
│                    │      决策规则            │                              │
│                    │   (Decision Rules)      │                              │
│                    │   - 条件判断             │                              │
│                    │   - 优先级               │                              │
│                    │   - 边界情况             │                              │
│                    └────────────┬────────────┘                              │
│                                 │                                           │
│                                 ▼                                           │
│                    ┌─────────────────────────┐                              │
│                    │      示例库              │                              │
│                    │   (Examples)            │                              │
│                    │   - 正例                 │                              │
│                    │   - 反例                 │                              │
│                    │   - 边界情况             │                              │
│                    └─────────────────────────┘                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Cursor 的设计模式

**核心特点**：任务驱动 + 状态管理 + 自我纠错

```markdown
# Cursor 的 Prompt 结构分析

## 1. 身份定义（简洁明确）
"You are an AI coding assistant, powered by GPT-5. You operate in Cursor."

## 2. 行为规范（XML 标签分块）
<communication>
- 格式化规则
- 简洁性要求
</communication>

<status_update_spec>
- 进度汇报规范
- 时态使用规则
</status_update_spec>

<flow>
1. 发现阶段
2. 计划阶段
3. 执行阶段
4. 总结阶段
</flow>

## 3. 工具使用规范
<tool_calling>
- 只使用提供的工具
- 并行调用优化
- 不向用户提及工具名
</tool_calling>

## 4. 自我纠错机制
<non_compliance>
- 如果未更新 TODO，下一轮立即纠正
- 如果未提供状态更新，下一轮纠正
</non_compliance>
```

**关键洞察**：
- **XML 标签分块**：将不同类型的规则用 XML 标签分隔，便于 LLM 理解和遵循
- **自我纠错**：明确告诉 LLM 如何处理自己的错误
- **状态管理**：通过 TODO 列表跟踪任务进度

### 2.3 Windsurf (Cascade) 的设计模式

**核心特点**：记忆系统 + 计划管理 + 主动研究

```markdown
# Windsurf 的 Prompt 结构分析

## 1. 身份定义（强调独特性）
"You are Cascade, a powerful agentic AI coding assistant designed by the Windsurf engineering team"
"As the world's first agentic coding assistant, you operate on the revolutionary AI Flow paradigm"

## 2. 记忆系统（持久化上下文）
<memory_system>
- 主动保存重要信息
- 不需要用户许可
- 自动检索相关记忆
</memory_system>

## 3. 代码研究规范
<code_research>
- 不确定时主动搜索
- 不猜测，必须有依据
- 不需要用户许可
</code_research>

## 4. 计划管理
<planning>
- 维护行动计划
- 学到新信息时更新计划
- 执行前先更新计划
</planning>
```

**关键洞察**：
- **记忆系统**：解决 LLM 上下文窗口限制的问题
- **主动研究**：鼓励 LLM 在不确定时主动获取信息
- **计划优先**：先计划再执行，执行中持续更新计划

### 2.4 Devin AI 的设计模式

**核心特点**：双模式架构 + 详细工具定义 + 安全规范

```markdown
# Devin AI 的 Prompt 结构分析

## 1. 双模式架构
- Planning Mode：收集信息，制定计划
- Standard Mode：执行计划，完成任务

## 2. 工具定义（极其详细）
<shell>
- 参数说明
- 使用场景
- 禁止事项
</shell>

<str_replace>
- 精确匹配规则
- 空白字符处理
- 示例
</str_replace>

## 3. 思考工具（显式推理）
<think>
- 必须使用的场景（10种）
- 应该使用的场景（10种）
- 用于关键决策前的推理
</think>

## 4. 安全规范
- 数据安全
- 密钥保护
- 权限控制
```

**关键洞察**：
- **双模式**：分离"思考"和"执行"，类似你的 Step1 + Step2
- **显式推理**：通过 `<think>` 工具强制 LLM 在关键决策前推理
- **详细工具定义**：每个工具都有完整的参数说明、使用场景、禁止事项

### 2.5 v0 (Vercel) 的设计模式

**核心特点**：领域专精 + 集成指南 + 代码规范

```markdown
# v0 的 Prompt 结构分析

## 1. 领域专精（Next.js + React）
- 框架特定规则
- 版本特定功能
- 最佳实践

## 2. 集成指南（详细的第三方集成）
## Supabase Integration Guidelines
- 客户端创建方式
- 认证流程
- RLS 安全规则

## Stripe Integration Guidelines
- 环境变量
- 沙箱模式
- 上线流程

## 3. 设计规范
## Color System
- 3-5 种颜色
- 渐变规则
- 对比度要求

## Typography
- 最多 2 种字体
- 行高规范
```

**关键洞察**：
- **领域专精**：针对特定领域（Web 开发）提供详细指南
- **集成指南**：为常用第三方服务提供完整的使用规范
- **设计规范**：不仅是代码，还包括 UI/UX 规范

### 2.6 Cline 的设计模式

**核心特点**：工具优先 + 步骤化执行 + 明确的输出格式

```markdown
# Cline 的 Prompt 结构分析

## 1. 工具定义（XML Schema）
## execute_command
Description: ...
Parameters:
- command: (required) ...
- requires_approval: (required) ...
Usage:
<execute_command>
<command>Your command here</command>
<requires_approval>true or false</requires_approval>
</execute_command>

## 2. 工具使用指南
1. 评估已有信息和需要的信息
2. 选择最合适的工具
3. 使用 XML 格式调用工具
4. 等待用户确认结果
5. 根据结果决定下一步

## 3. 模式切换
- ACT MODE：执行任务
- PLAN MODE：规划任务
```

**关键洞察**：
- **XML Schema**：工具定义使用 XML 格式，清晰明确
- **步骤化**：明确的工具使用流程
- **模式切换**：类似 Devin 的双模式架构

### 2.7 设计模式总结

| 模式 | 来源 | 适用场景 | 你的系统如何应用 |
|------|------|----------|------------------|
| XML 标签分块 | Cursor, Cline | 复杂规则组织 | 将计算类型规则用 XML 标签分隔 |
| 双模式架构 | Devin, Cline | 复杂任务分解 | Step1 (理解) + Step2 (推理) |
| 显式推理 | Devin | 关键决策 | 在复杂计算判断前要求推理 |
| 记忆系统 | Windsurf | 上下文管理 | 字段映射缓存、对话历史 |
| 领域专精 | v0 | 特定领域 | Tableau/VizQL 专用规则 |
| 自我纠错 | Cursor | 错误处理 | 校验失败时的重试机制 |
| 详细工具定义 | Devin, Cline | 工具使用 | 计算类型的详细定义 |

---

## 3. Prompt 与 Schema 的分工

### 3.1 核心原则（来自 Cursor 和 Claude Code）

```
┌─────────────────────────────────────────────────────────────┐
│                        Prompt                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 教 LLM 如何思考：                                    │   │
│  │ - 什么情况下做什么决策                               │   │
│  │ - 如何分析用户问题                                   │   │
│  │ - 正确和错误的例子                                   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            ↓
                     LLM 内部推理
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                        Schema                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 约束 LLM 输出什么：                                  │   │
│  │ - 字段名称和类型                                     │   │
│  │ - 必填/可选                                          │   │
│  │ - 枚举值范围                                         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Prompt 应该包含什么（借鉴顶级 AI 工具）

```markdown
## Prompt 结构模板（基于 Cursor + Devin + Windsurf）

### 1. 身份定义（Identity）
你是谁，你的职责是什么
- 简洁明确，1-2 句话
- 强调专业领域

### 2. 能力边界（Capabilities）
你能做什么，不能做什么
- 明确列出支持的功能
- 明确列出不支持的功能

### 3. 决策规则（Decision Rules）
- 使用 XML 标签分块组织
- IF 条件 A THEN 输出 X
- 使用表格展示映射关系
- 明确优先级

### 4. 思考步骤（Thinking Steps）
- 类似 Devin 的 <think> 工具
- 在关键决策前要求推理
- 明确推理的输出格式

### 5. 示例（Examples）
- 正例：输入 → 正确输出
- 反例：输入 → 错误输出（说明为什么错）
- 边界情况：特殊输入 → 处理方式

### 6. 自我纠错（Self-Correction）
- 类似 Cursor 的 <non_compliance>
- 明确错误处理方式
- 提供重试机制
```

### 3.3 Schema 应该包含什么

```python
# Schema 只定义结构，不解释逻辑

class Output(BaseModel):
    """输出模型"""
    
    field_a: str                    # 简短描述：是什么
    field_b: int                    # 简短描述：是什么
    field_c: Literal["X", "Y", "Z"] # 枚举值
    field_d: list[str] = []         # 默认值
    field_e: str | None = None      # 可选字段
```

**Schema 中的 description 应该**：
- 说明字段**是什么**（What）
- 不说明**什么时候填**（When）← 这属于 Prompt
- 不说明**怎么判断**（How）← 这属于 Prompt

---

## 4. 设计方法论

### 4.1 从用户问题反推设计

```
用户问题类型          →  需要的输出字段  →  需要的决策规则
─────────────────────────────────────────────────────────
"各省份销售额"        →  dimensions, measures  →  提取维度和度量
"销售额排名"          →  + computations        →  检测"排名"关键词
"2024年的数据"        →  + filters             →  解析日期表达式
"销售情况怎么样"      →  clarification         →  判断信息不完整
```

### 4.2 最小化原则

**问自己**：
1. 这个字段是必须的吗？能否合并到其他字段？
2. 这个规则是必须的吗？LLM 能否自己推断？
3. 这个枚举值是必须的吗？能否简化？

### 4.3 渐进式复杂度

```
Level 1: 基础查询
- 只有 dimensions + measures
- 覆盖 80% 的简单问题

Level 2: 带筛选
- 增加 filters
- 覆盖日期、值筛选

Level 3: 复杂计算
- 增加 computations
- 覆盖排名、占比、累计
```

---

## 5. 完整设计方案

### 5.1 简化后的数据模型


```python
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# 枚举定义 - 只定义值，不解释逻辑
# ═══════════════════════════════════════════════════════════════

class Intent(str, Enum):
    """意图类型"""
    DATA_QUERY = "DATA_QUERY"       # 数据查询
    CLARIFICATION = "CLARIFICATION" # 需要澄清
    GENERAL = "GENERAL"             # 一般问题
    

class Aggregation(str, Enum):
    """聚合函数"""
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    MIN = "MIN"
    MAX = "MAX"


class CalcType(str, Enum):
    """计算类型 - 简化为 5 种核心类型"""
    RANK = "RANK"                   # 排名
    PERCENT_OF_TOTAL = "PERCENT"    # 占比
    RUNNING_TOTAL = "RUNNING"       # 累计
    DIFFERENCE = "DIFF"             # 差异/环比
    NONE = "NONE"                   # 无复杂计算


# ═══════════════════════════════════════════════════════════════
# 数据模型 - 只定义结构，description 只说"是什么"
# ═══════════════════════════════════════════════════════════════

class Dimension(BaseModel):
    """维度字段"""
    field: str = Field(description="字段名")
    granularity: str | None = Field(default=None, description="日期粒度: YEAR/MONTH/DAY")


class Measure(BaseModel):
    """度量字段"""
    field: str = Field(description="字段名")
    aggregation: Aggregation = Field(default=Aggregation.SUM, description="聚合函数")


class Filter(BaseModel):
    """筛选条件 - 统一为 SQL-like 表达式"""
    field: str = Field(description="字段名")
    operator: str = Field(description="操作符: =, in, between, >, <, contains")
    value: str | list = Field(description="筛选值")


class Computation(BaseModel):
    """复杂计算 - 通用模型"""
    calc_type: CalcType = Field(description="计算类型")
    target: str = Field(description="目标度量字段")
    partition_by: list[str] = Field(default_factory=list, description="分区字段")


class SemanticQuery(BaseModel):
    """语义查询结果 - 最终输出"""
    intent: Intent = Field(description="意图类型")
    dimensions: list[Dimension] = Field(default_factory=list, description="维度列表")
    measures: list[Measure] = Field(default_factory=list, description="度量列表")
    filters: list[Filter] = Field(default_factory=list, description="筛选条件")
    computation: Computation | None = Field(default=None, description="复杂计算")
    clarification: str | None = Field(default=None, description="澄清问题")
```

### 5.2 Prompt 模板（借鉴顶级 AI 工具设计）

```python
SYSTEM_PROMPT = """
<identity>
你是 Tableau 数据分析助手，负责将用户的自然语言问题转换为结构化查询。
你专注于数据分析领域，擅长理解业务问题并转换为可执行的查询。
</identity>

<capabilities>
你可以：
- 理解用户的数据分析问题
- 提取维度、度量、筛选条件
- 识别复杂计算需求（排名、占比、累计等）
- 处理相对日期表达式

你不能：
- 执行查询（只负责理解和转换）
- 访问外部数据源
- 回答与数据分析无关的问题
</capabilities>

<available_fields>
维度字段（用于分组）：
{available_dimensions}

度量字段（用于计算）：
{available_measures}
</available_fields>

<decision_rules>
## 意图判断规则

<intent_classification>
| 条件 | 意图 | 说明 |
|------|------|------|
| 有具体度量 + 有具体维度 | DATA_QUERY | 完整的数据查询 |
| 缺少度量或维度 | CLARIFICATION | 需要澄清 |
| 询问字段/元数据 | GENERAL | 一般性问题 |
</intent_classification>

## 复杂计算判断规则

<computation_detection>
检测以下关键词来判断是否需要复杂计算：

| 关键词 | 计算类型 | 说明 |
|-------|---------|------|
| 排名、排行、第几名、Rank | RANK | 添加排名列 |
| 占比、百分比、份额、% of | PERCENT | 计算占总量的比例 |
| 累计、YTD、累积、Running | RUNNING | 累计求和 |
| 环比、同比、增长率、MoM、YoY | DIFF | 与上期比较 |
| 无以上关键词 | NONE | 简单聚合查询 |

注意：
- "前10名"、"Top N" 是筛选，不是排名计算
- 一个问题只能有一种复杂计算类型
</computation_detection>

## 日期处理规则

<date_handling>
当前时间：{current_time}

| 用户表达 | 转换为 |
|---------|-------|
| 今年 | {current_year}-01-01 到 今天 |
| 去年 | {last_year}-01-01 到 {last_year}-12-31 |
| 上个月 | 上月第一天 到 上月最后一天 |
| 最近7天 | 7天前 到 今天 |
| 本季度 | 本季度第一天 到 今天 |
</date_handling>
</decision_rules>

<thinking_steps>
在生成输出前，你必须按以下步骤思考：

1. **识别意图**：问题是数据查询、需要澄清、还是一般问题？
   - 检查是否有具体的度量词（销售额、订单数等）
   - 检查是否有具体的维度词（省份、月份等）

2. **提取度量**：用户想看什么指标？
   - 从可用字段中选择
   - 确定聚合方式（SUM、AVG、COUNT 等）

3. **提取维度**：用户想按什么分组？
   - 从可用字段中选择
   - 如果是日期字段，确定粒度（年、月、日）

4. **提取筛选**：用户有什么限制条件？
   - 日期范围
   - 值筛选
   - Top N 筛选

5. **判断复杂度**：是否需要排名/占比/累计等计算？
   - 检测关键词
   - 确定计算类型和参数
</thinking_steps>

<examples>
## 示例 1：简单查询

问题：各省份的销售额

<analysis>
- 意图：DATA_QUERY（有具体度量"销售额"和维度"省份"）
- 度量：销售额，聚合 SUM
- 维度：省份
- 筛选：无
- 复杂计算：无（没有排名/占比/累计关键词）
</analysis>

输出：
```json
{{
  "intent": "DATA_QUERY",
  "dimensions": [{{"field": "省份"}}],
  "measures": [{{"field": "销售额", "aggregation": "SUM"}}],
  "filters": [],
  "computation": null
}}
```

## 示例 2：带筛选的查询

问题：2024年北京的月度销售额

<analysis>
- 意图：DATA_QUERY
- 度量：销售额
- 维度：订单日期（按月）
- 筛选：年份=2024，城市=北京
- 复杂计算：无
</analysis>

输出：
```json
{{
  "intent": "DATA_QUERY",
  "dimensions": [{{"field": "订单日期", "granularity": "MONTH"}}],
  "measures": [{{"field": "销售额", "aggregation": "SUM"}}],
  "filters": [
    {{"field": "订单日期", "operator": "between", "value": ["2024-01-01", "2024-12-31"]}},
    {{"field": "城市", "operator": "=", "value": "北京"}}
  ],
  "computation": null
}}
```

## 示例 3：复杂计算（排名）

问题：各省份销售额排名

<analysis>
- 意图：DATA_QUERY
- 度量：销售额
- 维度：省份
- 筛选：无
- 复杂计算：RANK（检测到"排名"关键词）
  - target: 销售额
  - partition_by: []（全局排名）
</analysis>

输出：
```json
{{
  "intent": "DATA_QUERY",
  "dimensions": [{{"field": "省份"}}],
  "measures": [{{"field": "销售额", "aggregation": "SUM"}}],
  "filters": [],
  "computation": {{"calc_type": "RANK", "target": "销售额", "partition_by": []}}
}}
```

## 示例 4：复杂计算（占比）

问题：各省份销售额占比

<analysis>
- 意图：DATA_QUERY
- 度量：销售额
- 维度：省份
- 筛选：无
- 复杂计算：PERCENT（检测到"占比"关键词）
  - target: 销售额
  - partition_by: []（占总体的比例）
</analysis>

输出：
```json
{{
  "intent": "DATA_QUERY",
  "dimensions": [{{"field": "省份"}}],
  "measures": [{{"field": "销售额", "aggregation": "SUM"}}],
  "filters": [],
  "computation": {{"calc_type": "PERCENT", "target": "销售额", "partition_by": []}}
}}
```

## 示例 5：需要澄清

问题：销售情况怎么样

<analysis>
- 意图：CLARIFICATION（缺少具体度量和维度）
- 问题太模糊，无法确定用户想看什么
</analysis>

输出：
```json
{{
  "intent": "CLARIFICATION",
  "dimensions": [],
  "measures": [],
  "filters": [],
  "computation": null,
  "clarification": "请问您想查看哪个指标？比如销售额、订单数？想按什么维度分析？比如按省份、按月份？"
}}
```

## 反例：Top N 不是排名

问题：销售额前10的省份

<analysis>
- 这是 Top N 筛选，不是排名计算
- 用户想要的是筛选后的子集，不是添加排名列
</analysis>

正确输出：
```json
{{
  "intent": "DATA_QUERY",
  "dimensions": [{{"field": "省份"}}],
  "measures": [{{"field": "销售额", "aggregation": "SUM"}}],
  "filters": [{{"field": "销售额", "operator": "top", "value": 10}}],
  "computation": null
}}
```

错误输出（不要这样做）：
```json
{{
  "computation": {{"calc_type": "RANK", ...}}
}}
```
</examples>

<self_correction>
## 自我检查规则

在输出前，检查以下内容：

1. **字段检查**：所有字段名是否来自"可用字段"列表？
   - 如果不是，返回 CLARIFICATION

2. **日期检查**：日期筛选是否转换为具体日期？
   - 不要保留"今年"这样的相对表达

3. **计算检查**：是否正确区分了 Top N 筛选和排名计算？
   - "前10名" → 筛选
   - "排名" → 计算

4. **完整性检查**：DATA_QUERY 是否至少有一个度量？
   - 如果没有，返回 CLARIFICATION
</self_correction>

<output_format>
{format_instructions}
</output_format>
"""
```

### 5.3 为什么这样设计有效？

#### 原理 1：XML 标签分块（来自 Cursor）

```
Prompt 中使用 XML 标签分块：
┌─────────────────────────────────────────────────────────┐
│ <decision_rules>                                        │
│   ## 意图判断规则                                        │
│   <intent_classification>                               │
│     | 条件 | 意图 |                                      │
│   </intent_classification>                              │
│                                                         │
│   ## 复杂计算判断规则                                    │
│   <computation_detection>                               │
│     | 关键词 | 计算类型 |                                │
│   </computation_detection>                              │
│ </decision_rules>                                       │
└─────────────────────────────────────────────────────────┘
                    ↓
LLM 更容易理解规则的层级结构和边界
                    ↓
减少规则混淆，提高准确率
```

#### 原理 2：显式推理步骤（来自 Devin）

```
<thinking_steps> 强制 LLM 按步骤思考：

1. 识别意图 → 检查度量和维度
2. 提取度量 → 从可用字段选择
3. 提取维度 → 从可用字段选择
4. 提取筛选 → 解析条件
5. 判断复杂度 → 检测关键词

这比直接要求输出 JSON 更可靠，因为：
- LLM 有明确的思考路径
- 每一步都有明确的输入和输出
- 错误更容易定位
```

#### 原理 3：正反例对比（来自 v0）

```
示例中同时提供正例和反例：

正例：
问题：各省份销售额排名
输出：computation: {calc_type: "RANK", ...}

反例：
问题：销售额前10的省份
错误输出：computation: {calc_type: "RANK", ...}  ← 不要这样做
正确输出：filters: [{operator: "top", value: 10}]

这帮助 LLM 区分容易混淆的情况
```

#### 原理 4：自我纠错机制（来自 Cursor）

```
<self_correction> 提供检查清单：

1. 字段检查 → 是否来自可用字段？
2. 日期检查 → 是否转换为具体日期？
3. 计算检查 → 是否正确区分筛选和计算？
4. 完整性检查 → 是否有必需字段？

这让 LLM 在输出前进行自我验证
```

---

## 6. LangChain 实现模板


### 6.1 完整实现代码（借鉴顶级 AI 工具设计）

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
# Step 1: 定义 Schema（只定义结构）
# ═══════════════════════════════════════════════════════════════

class Intent(str, Enum):
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"


class Aggregation(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    MIN = "MIN"
    MAX = "MAX"


class CalcType(str, Enum):
    RANK = "RANK"
    PERCENT = "PERCENT"
    RUNNING = "RUNNING"
    DIFF = "DIFF"
    NONE = "NONE"


class Dimension(BaseModel):
    field: str
    granularity: Literal["YEAR", "MONTH", "DAY"] | None = None


class Measure(BaseModel):
    field: str
    aggregation: Aggregation = Aggregation.SUM


class Filter(BaseModel):
    field: str
    operator: Literal["=", "in", "between", ">", "<", "contains"]
    value: str | list


class Computation(BaseModel):
    calc_type: CalcType
    target: str
    partition_by: list[str] = Field(default_factory=list)


class SemanticQuery(BaseModel):
    """语义查询结果"""
    intent: Intent
    dimensions: list[Dimension] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    computation: Computation | None = None
    clarification: str | None = None


# ═══════════════════════════════════════════════════════════════
# Step 2: 定义 Prompt（教 LLM 如何思考）
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
# 身份

你是数据分析助手，将自然语言转换为结构化查询。

# 可用字段

维度：{dimensions}
度量：{measures}

# 决策规则

## 意图判断
- DATA_QUERY：有具体度量和维度
- CLARIFICATION：信息不完整
- GENERAL：询问元数据

## 复杂计算
| 关键词 | calc_type |
|-------|-----------|
| 排名/排行 | RANK |
| 占比/百分比 | PERCENT |
| 累计/YTD | RUNNING |
| 环比/同比 | DIFF |
| 无 | NONE |

# 当前时间
{current_time}

# 示例

问：各省份销售额
答：{{"intent": "DATA_QUERY", "dimensions": [{{"field": "省份"}}], "measures": [{{"field": "销售额", "aggregation": "SUM"}}], "filters": [], "computation": null}}

问：各省份销售额排名
答：{{"intent": "DATA_QUERY", "dimensions": [{{"field": "省份"}}], "measures": [{{"field": "销售额", "aggregation": "SUM"}}], "filters": [], "computation": {{"calc_type": "RANK", "target": "销售额", "partition_by": []}}}}

问：销售情况怎么样
答：{{"intent": "CLARIFICATION", "dimensions": [], "measures": [], "filters": [], "computation": null, "clarification": "请问您想查看哪个指标？"}}

# 输出格式
{format_instructions}
"""


# ═══════════════════════════════════════════════════════════════
# Step 3: 组装 Chain
# ═══════════════════════════════════════════════════════════════

def create_semantic_parser(llm: ChatOpenAI, available_fields: dict) -> callable:
    """创建语义解析器"""
    
    parser = PydanticOutputParser(pydantic_object=SemanticQuery)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{question}")
    ])
    
    chain = prompt | llm | parser
    
    def parse(question: str) -> SemanticQuery:
        return chain.invoke({
            "question": question,
            "dimensions": ", ".join(available_fields.get("dimensions", [])),
            "measures": ", ".join(available_fields.get("measures", [])),
            "current_time": datetime.now().strftime("%Y-%m-%d"),
            "format_instructions": parser.get_format_instructions()
        })
    
    return parse


# ═══════════════════════════════════════════════════════════════
# Step 4: 使用示例
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from langchain_openai import ChatOpenAI
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    available_fields = {
        "dimensions": ["省份", "城市", "产品类别", "订单日期"],
        "measures": ["销售额", "利润", "订单数", "数量"]
    }
    
    parser = create_semantic_parser(llm, available_fields)
    
    # 测试
    result = parser("各省份的销售额")
    print(result.model_dump_json(indent=2))
```

### 6.2 关键设计要点总结

```
┌─────────────────────────────────────────────────────────────────┐
│                     设计要点总结                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Prompt 的职责（借鉴 Cursor + Devin）：                       │
│     ✓ 定义身份和能力边界                                        │
│     ✓ 使用 XML 标签分块组织规则                                 │
│     ✓ 提供决策规则（IF-THEN 表格）                              │
│     ✓ 要求显式推理步骤                                          │
│     ✓ 给出正反例                                                │
│     ✓ 提供自我纠错机制                                          │
│     ✗ 不要重复 Schema 中的字段定义                              │
│                                                                 │
│  2. Schema 的职责：                                             │
│     ✓ 定义字段名和类型                                          │
│     ✓ 定义枚举值范围                                            │
│     ✓ 定义必填/可选                                             │
│     ✗ 不要解释业务逻辑                                          │
│                                                                 │
│  3. 简化原则：                                                  │
│     - 枚举值越少越好（5个以内）                                  │
│     - 嵌套层级越浅越好（2层以内）                                │
│     - 示例越具体越好（5-8个，包含正反例）                        │
│     - 规则越明确越好（用表格）                                   │
│                                                                 │
│  4. 调试方法：                                                  │
│     - 输出不对 → 检查示例是否覆盖该情况                          │
│     - 格式不对 → 检查 Schema 定义                                │
│     - 逻辑不对 → 检查决策规则是否清晰                            │
│     - 混淆情况 → 添加反例说明                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 与你现有系统的对比

### 7.1 当前设计的问题

```python
# 你现在的 computations.py 中：

class RankCalc(BaseModel):
    """RANK - Rank query results with possible gaps (1,2,2,4).
    
    Use when question asks for ranking/ordering of results.  # ← 这是 Prompt 内容
    
    <fill_order>                    # ← 这是 Prompt 内容
    1. calc_type (ALWAYS = "RANK")
    2. target (ALWAYS)
    ...
    </fill_order>
    
    <anti_patterns>                 # ← 这是 Prompt 内容
    X Using RANK for simple Top N filtering
    </anti_patterns>
    """
    
    calc_type: Literal["RANK"] = Field(
        default="RANK",
        description="""<what>RANK calculation type</what>
<when>ALWAYS = "RANK"</when>"""  # ← 混合了 What 和 When
    )
```

**问题**：
1. Prompt 内容（何时使用、反模式）混在 Schema 的 docstring 里
2. Field description 混合了"是什么"和"什么时候填"
3. 11 种计算类型，每种都有独立的类，太复杂

### 7.2 简化后的设计

```python
# Schema（只定义结构）
class Computation(BaseModel):
    """复杂计算"""
    calc_type: CalcType  # 枚举：RANK, PERCENT, RUNNING, DIFF, NONE
    target: str
    partition_by: list[str] = []

# Prompt（单独文件，教 LLM 如何思考）
COMPUTATION_RULES = """
## 复杂计算判断

| 关键词 | calc_type | 说明 |
|-------|-----------|------|
| 排名、排行 | RANK | 添加排名列 |
| 占比、百分比 | PERCENT | 计算占总量的比例 |
| 累计、YTD | RUNNING | 累计求和 |
| 环比、同比 | DIFF | 与上期比较 |

### 注意
- Top N 筛选（如"前10名"）不是 RANK，用 Filter 处理
- 一个问题只能有一种复杂计算
"""
```

---

## 8. 迁移建议

### 8.1 分阶段迁移

```
Phase 1: 分离 Prompt 和 Schema
├── 将 docstring 中的规则移到单独的 prompt 文件
├── 简化 Field description 为纯"是什么"
└── 测试现有功能不受影响

Phase 2: 简化数据模型
├── 合并 11 种 Computation 为 1 个通用类
├── 合并 5 种 Filter 为 1 个通用类
└── 减少枚举值数量

Phase 3: 合并 Step1 + Step2
├── 用 is_complex 标记替代两阶段调用
├── 减少 LLM 调用次数
└── 降低延迟
```

### 8.2 文件结构建议

```
src/
├── prompts/                    # Prompt 文件（教 LLM 如何思考）
│   ├── semantic_parser.py      # 语义解析 prompt
│   ├── field_mapper.py         # 字段映射 prompt
│   └── examples/               # 示例库
│       ├── simple_queries.json
│       └── complex_queries.json
│
├── schemas/                    # Schema 文件（定义输出格式）
│   ├── query.py                # SemanticQuery
│   ├── fields.py               # Dimension, Measure
│   └── enums.py                # Intent, CalcType, etc.
│
└── chains/                     # LangChain 组装
    └── semantic_parser.py      # 组装 prompt + schema + llm
```

---

## 9. 总结

### 核心原则（来自顶级 AI 工具）

1. **Prompt 教思考，Schema 定格式** - 分离关注点（Cursor, Claude Code）
2. **XML 标签分块** - 组织复杂规则（Cursor, Cline）
3. **显式推理步骤** - 强制按步骤思考（Devin）
4. **正反例对比** - 区分容易混淆的情况（v0）
5. **自我纠错机制** - 输出前自我验证（Cursor）
6. **记忆系统** - 持久化重要上下文（Windsurf）
7. **双模式架构** - 分离理解和执行（Devin, Cline）

### LLM 工作原理

```
输入 → 模式匹配（Prompt 激活正确模式）→ 显式推理（按步骤思考）→ 逐 Token 生成（Schema 约束格式）→ 自我检查 → 输出
```

### 你的系统如何应用

| 顶级工具模式 | 你的系统应用 |
|-------------|-------------|
| XML 标签分块 | 将计算类型规则用 `<computation_detection>` 等标签分隔 |
| 显式推理 | 在 `<thinking_steps>` 中要求按步骤分析 |
| 正反例 | 添加 "Top N 不是排名" 等反例 |
| 自我纠错 | 在 `<self_correction>` 中提供检查清单 |
| 双模式 | Step1 (理解) + Step2 (推理) |
| 领域专精 | Tableau/VizQL 专用规则和示例 |
