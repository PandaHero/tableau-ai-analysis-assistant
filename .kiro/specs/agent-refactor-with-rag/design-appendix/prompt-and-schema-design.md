# Prompt 模板与数据模型设计规范

## 概述

本文档定义了 Tableau Assistant 项目中 Prompt 模板和数据模型的设计规范，基于 `PROMPT_AND_MODEL_GUIDE.md` 中的前沿研究和底层原理。

**核心理念**：思考与填写是交织在一起的，不是"先思考完再填写"，而是"每填一个字段都伴随一次微型思考"。

**参考文档**：`tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md`

---

## 第一部分：底层原理

### 1.1 LLM 生成的微观过程

LLM 生成 JSON 输出时是**逐 token 生成**的：

```
生成序列: { " t y p e " : " c u m u l a t i v e " , ...
            ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑ ↑
            每个 token 都是一次"微型决策"
```

在生成每个字段值时，LLM 的 Attention 机制会：
1. **回看 System Prompt**（找到相关的思考指导）
2. **回看 Schema Description**（找到该字段的填写规则，**注意力最高！**）
3. **回看 User Input**（找到相关的关键词）
4. **回看已生成的 tokens**（保持一致性）

### 1.2 思考与填写的交织

**传统理解（错误）**：
```
Prompt（思考）→ 完成思考 → Schema（填写）→ 输出
```

**实际机制（正确）**：
```
填写字段1 → 微型思考1 → 填写字段2 → 微型思考2 → ...
     ↑           ↑           ↑           ↑
   Schema    Prompt+      Schema    Prompt+
   Description Schema     Description Schema
```

每填一个字段，都是一次"微型思考"：
- **思考**：从 Prompt 获取分析方法，从 Schema 获取决策规则
- **填写**：根据决策规则确定字段值


### 1.3 XML 标签的底层作用

XML 标签的核心价值是**为每次"微型思考"提供精确的规则定位锚点**。

**没有 XML 标签时**：
```
"type: 分析类型。派生计算的类型。ALWAYS required。
 从问题中的关键词检测。累计→cumulative，排名→ranking..."
```
- LLM 需要推断哪部分是"含义"，哪部分是"条件"，哪部分是"规则"
- Attention 分散，边界模糊

**有 XML 标签时**：
```xml
<what>派生计算的类型</what>
<when>ALWAYS required</when>
<decision_rule>
  累计→cumulative，排名→ranking...
</decision_rule>
```
- LLM 可以直接定位到 `<decision_rule>` 标签，提取决策规则
- Attention 集中，边界清晰

### 1.4 Attention 机制与信息布局

基于 "Lost in the Middle" 研究，LLM 对长上下文的注意力分布：

```
┌─────────────────────────────────────────────────────────────┐
│ 开头 ████████████████                                        │ ← 高注意力
│ 中间         ████                                            │ ← 低注意力
│ 结尾                                    ████████████████████ │ ← 高注意力
└─────────────────────────────────────────────────────────────┘
```

**信息布局原则**：
- **开头**：放 `<what>` 和 `<when>`（核心语义和条件）
- **中间**：放 `<how>` 和 `<dependency>`（次要信息）
- **结尾**：放 `<examples>` 和 `<anti_patterns>`（最近的参考）

---

## 第二部分：职责边界

### 2.1 核心原则

> **Prompt 教 LLM 如何思考，Schema 告诉 LLM 输出什么**
> **`<decision_rule>` 是思考与填写的桥梁**

### 2.2 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: System Context (系统上下文)                        │
│  ├─ Role: 你是谁（激活知识子空间）                           │
│  ├─ Capabilities: 你能做什么                                 │
│  └─ Global Constraints: 全局约束                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Task Reasoning (任务推理) - Prompt 模板            │
│  ├─ Task: 具体要做什么                                       │
│  ├─ Domain Knowledge: 领域概念（不涉及具体字段名）           │
│  ├─ Reasoning Steps: 思考步骤（HOW to think）                │
│  └─ Constraints: 约束条件                                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Output Schema (输出模式) - 数据模型                 │
│  ├─ Class Docstring:                                         │
│  │   ├─ <decision_tree>: 决策树（树状决策路径）              │
│  │   ├─ <fill_order>: 填写顺序（先简单后复杂）               │
│  │   ├─ <examples>: 完整输入输出示例                         │
│  │   └─ <anti_patterns>: 常见错误                            │
│  ├─ Field Definitions:                                       │
│  │   ├─ <what>: 字段含义                                     │
│  │   ├─ <when>: 何时填写（条件）                             │
│  │   ├─ <how>: 如何填写（格式）                              │
│  │   ├─ <dependency>: 依赖关系                               │
│  │   ├─ <decision_rule>: 决策规则（思考→填写的桥梁）         │
│  │   ├─ <values>: 取值范围                                   │
│  │   └─ <examples>: 字段级示例                               │
│  └─ Validators: 自验证逻辑（Pydantic，代码级 100% 可靠）     │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 职责划分表

| 内容类型 | Prompt | Schema | 桥梁机制 |
|---------|--------|--------|---------|
| 领域概念定义 | ✅ | ❌ | - |
| 分析方法 | ✅ | ❌ | - |
| 推理步骤（抽象） | ✅ | ❌ | - |
| 字段含义 | ❌ | ✅ `<what>` | - |
| 填写条件 | ❌ | ✅ `<when>` | - |
| 填写格式 | ❌ | ✅ `<how>` | - |
| 依赖关系 | ❌ | ✅ `<dependency>` | - |
| 取值范围 | ❌ | ✅ `<values>` | - |
| **决策规则** | ❌ | ✅ `<decision_rule>` | **思考→填写的桥梁** |
| 示例 | ❌ | ✅ `<examples>` | - |
| 常见错误 | ❌ | ✅ `<anti_patterns>` | - |

### 2.4 思考与填写的桥梁：`<decision_rule>`

**核心机制**：`<decision_rule>` 将 Prompt 中的抽象思考步骤转化为具体的填写动作。

```
Prompt 中的思考步骤:
"Step 5: 识别分析类型
 - 问题中是否有累计、排名、占比等关键词？"
                    ↓ 桥梁
Schema 中的 <decision_rule>:
"Prompt Step 5 (识别分析类型) → 填写 type
 - '累计' / '累积' / 'running' → cumulative
 - '排名' / '排序' / 'TOP' → ranking
 - '占比' / '百分比' / '%' → percentage"
```

**关键要求**：
1. `<decision_rule>` 必须引用 Prompt 中的思考步骤
2. 规则必须是具体的、可执行的（关键词 → 值）
3. 必须覆盖所有可能的情况，包括"不填写"的条件


---

## 第三部分：XML 标签规范

### 3.1 标准 XML 标签

| 标签 | 含义 | 必填 | 位置 | 说明 |
|------|------|------|------|------|
| `<what>` | 字段含义 | ✅ | 开头 | 一句话说明字段代表什么 |
| `<when>` | 填写条件 | ✅ | 开头 | 何时填写（ALWAYS / IF condition） |
| `<how>` | 填写方式 | ✅ | 中间 | 如何填写（格式、来源） |
| `<dependency>` | 依赖关系 | 条件字段必填 | 中间 | 依赖哪些其他字段 |
| `<decision_rule>` | 决策规则 | 复杂条件必填 | 中间 | **思考→填写的桥梁** |
| `<values>` | 取值范围 | 推荐 | 中间 | 可选值列表及含义 |
| `<examples>` | 示例 | 推荐 | 结尾 | 输入→输出示例 |
| `<anti_patterns>` | 常见错误 | 推荐 | 结尾 | 避免的错误模式 |

### 3.2 Class Docstring 标签

| 标签 | 含义 | 说明 |
|------|------|------|
| `<what>` | 模型含义 | 一句话说明模型代表什么 |
| `<decision_tree>` | 决策树 | 树状决策路径，替代依赖矩阵 |
| `<fill_order>` | 填写顺序 | 明确字段填写顺序（先简单后复杂） |
| `<conditional_groups>` | 条件分组 | 按触发条件分组字段 |
| `<examples>` | 完整示例 | 输入→输出示例 |
| `<anti_patterns>` | 常见错误 | 避免的错误模式 |

### 3.3 `<decision_rule>` 的编写规范

**格式要求**：

```xml
<decision_rule>
Prompt Step N (步骤名称) → 填写 field_name
- 条件1 → 值1
- 条件2 → 值2
- DEFAULT: 默认值
- SKIP IF: 不填写的条件
</decision_rule>
```

**示例**：

```xml
<decision_rule>
Prompt Step 5 (识别分析类型) → 填写 type
- "累计" / "累积" / "running" → cumulative
- "排名" / "排序" / "TOP" → ranking
- "占比" / "百分比" / "%" → percentage
- "同比" / "环比" / "对比" → period_compare
- "移动平均" / "滑动" → moving
- SKIP IF: 问题中没有派生计算关键词
</decision_rule>
```

### 3.4 `<dependency>` 的编写规范

**格式要求**：

```xml
<dependency>
- field: 依赖的字段名
- condition: 触发条件
- reason: 为什么有这个依赖
</dependency>
```

**示例**：

```xml
<dependency>
- field: dimensions (from parent SemanticQuery)
- condition: length > 1
- reason: 单维度不需要指定计算范围，多维度才需要区分 per_group 或 across_all
</dependency>
```

### 3.5 `<decision_tree>` 的编写规范

**格式要求**：

```
<decision_tree>
START
  │
  ├─► 字段1 = ? (填写条件)
  │   │
  │   ├─► 值A
  │   │   └─► 触发的后续字段
  │   │
  │   └─► 值B
  │       └─► 触发的后续字段
  │
  ├─► 字段2 = ? (填写条件)
  │   ...
  │
END
</decision_tree>
```

**示例**：

```
<decision_tree>
START
  │
  ├─► type = ? (ALWAYS fill first, determines conditional fields)
  │   │
  │   ├─► cumulative/moving/ranking/percentage/period_compare
  │   │   │
  │   │   └─► dimensions.length > 1 ?
  │   │       ├─ YES → fill computation_scope (default: per_group)
  │   │       └─ NO  → skip computation_scope (null)
  │   │
  │   ├─► ranking
  │   │   └─► fill order (default: desc)
  │   │
  │   ├─► moving
  │   │   └─► fill window_size (required)
  │   │
  │   └─► period_compare
  │       └─► fill compare_type (required)
  │
  ├─► target_measure = ? (ALWAYS fill)
  │
  └─► aggregation = ? (ALWAYS fill, default: sum)
  
END
</decision_tree>
```

### 3.6 `<fill_order>` 的编写规范

**格式要求**：

```
<fill_order>
┌────┬─────────────────────────┬─────────────────────────────────────┐
│ #  │ Field                   │ Condition                           │
├────┼─────────────────────────┼─────────────────────────────────────┤
│ 1  │ 字段1                   │ ALWAYS / IF condition               │
│ 2  │ 字段2                   │ ALWAYS / IF condition               │
│ ...│ ...                     │ ...                                 │
└────┴─────────────────────────┴─────────────────────────────────────┘
</fill_order>
```

**原则**：
- 无依赖的字段排在前面
- 有依赖的字段排在后面
- 依赖字段的值由先填字段决定


---

## 第四部分：Prompt 模板设计

### 4.1 4 段式结构

```python
class YourPrompt(VizQLPrompt):
    def get_role(self) -> str:
        """定义 LLM 的角色（激活知识子空间）"""
        
    def get_task(self) -> str:
        """定义 LLM 的任务（聚焦注意力）"""
        
    def get_specific_domain_knowledge(self) -> str:
        """提供领域知识和思考步骤（HOW to think）"""
        
    def get_constraints(self) -> str:
        """定义约束条件"""
        
    def get_user_template(self) -> str:
        """定义用户输入模板"""
        
    def get_output_model(self) -> Type[BaseModel]:
        """指定输出模型"""
```

### 4.2 Role 部分

**作用**：激活 LLM 的相关知识子空间

**编写要点**：
- 简洁明确（2-3 句话）
- 突出专业领域
- 列出核心能力

**示例**：

```python
def get_role(self) -> str:
    return """Data analysis expert who understands user questions and extracts structured query intent.

Expertise:
- Semantic understanding of business terminology
- Dimension vs Measure classification
- Time expression parsing
- Analysis type detection (cumulative, ranking, percentage, etc.)"""
```

### 4.3 Task 部分

**作用**：聚焦 LLM 的注意力

**编写要点**：
- 一句话概括任务
- 列出处理流程（Process）
- 使用箭头（→）表示步骤

**示例**：

```python
def get_task(self) -> str:
    return """Understand user question and output SemanticQuery (pure semantic, no VizQL concepts).

Process: Analyze question → Extract entities → Classify roles → Detect analysis type → Output structured JSON"""
```

### 4.4 Domain Knowledge 部分

**作用**：提供领域知识和思考步骤

**编写要点**：
- 使用 "Think step by step" 引导
- 每个步骤清晰编号
- **不涉及具体字段名**（字段名在 Schema 中）
- 提供概念定义和分类规则

**示例**：

```python
def get_specific_domain_knowledge(self) -> str:
    return """**Think step by step:**

Step 1: Understand user intent
- What does the user want to know?
- Is it a simple query or complex analysis?

Step 2: Extract business entities
- Identify all business terms (e.g., "销售额", "省份", "日期")
- Note: Use exact terms from question, not technical field names

Step 3: Classify entity roles
- Dimension: Categorical field for grouping ("各XX", "按XX", "每个XX")
- Measure: Numeric field for aggregation ("销售额", "利润", "数量")
- Time dimension: Date/time field ("日期", "时间", "年", "月")

Step 4: Detect time expressions
- Absolute: "2024年", "1月", "Q1"
- Relative: "最近3个月", "上周", "去年同期"

Step 5: Detect analysis type
- Cumulative: "累计", "累积", "running"
- Ranking: "排名", "排序", "TOP", "前N名"
- Percentage: "占比", "百分比", "%"
- Period compare: "同比", "环比", "对比"
- Moving: "移动平均", "滑动"

Step 6: Determine computation scope (for multi-dimension analysis)
- Per group: "各XX", "每个XX" → Calculate independently per group
- Across all: "总", "全部", "整体" → Calculate across all data"""
```

### 4.5 Constraints 部分

**作用**：定义必须遵守的约束

**编写要点**：
- 分为 MUST 和 MUST NOT
- 简洁列举
- 避免冗长解释

**示例**：

```python
def get_constraints(self) -> str:
    return """MUST:
- Use business terms from question (not technical field names)
- Fill fields in order specified by <fill_order>
- Follow <decision_rule> for each field

MUST NOT:
- Use VizQL concepts (addressing, partitioning, RUNNING_SUM, etc.)
- Invent fields not mentioned in question
- Set computation_scope for single dimension queries"""
```

### 4.6 Prompt 与 Schema 的协同

**关键**：Prompt 中的思考步骤必须与 Schema 中的 `<decision_rule>` 对应。

```
Prompt Step 5 (Detect analysis type)
        ↓ 对应
Schema type 字段的 <decision_rule>:
"Prompt Step 5 (识别分析类型) → 填写 type"

Prompt Step 6 (Determine computation scope)
        ↓ 对应
Schema computation_scope 字段的 <decision_rule>:
"Prompt Step 6 (确定计算范围) → 填写 computation_scope"
```


---

## 第五部分：数据模型设计

### 5.1 模型结构

```python
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List, Literal

class YourModel(BaseModel):
    """
    模型描述
    
    <what>模型代表什么</what>
    
    <decision_tree>
    决策树结构
    </decision_tree>
    
    <fill_order>
    填写顺序表格
    </fill_order>
    
    <examples>
    完整输入输出示例
    </examples>
    
    <anti_patterns>
    常见错误
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: FieldType = Field(
        description="""字段描述
        
        <what>字段含义</what>
        <when>填写条件</when>
        <how>填写方式</how>
        
        <dependency>
        依赖关系（如果有）
        </dependency>
        
        <decision_rule>
        决策规则（思考→填写的桥梁）
        </decision_rule>
        
        <values>
        取值范围
        </values>
        
        <examples>
        字段级示例
        </examples>
        
        <anti_patterns>
        常见错误
        </anti_patterns>"""
    )
    
    @model_validator(mode='after')
    def validate_dependencies(self) -> 'YourModel':
        """代码级验证，100% 可靠"""
        # 验证逻辑
        return self
```

### 5.2 字段描述的信息布局

基于 "Lost in the Middle" 研究，字段描述应遵循以下布局：

```
┌─────────────────────────────────────────────────────────────┐
│ 开头（高注意力）                                             │
│ <what>字段含义</what>                                        │
│ <when>填写条件</when>                                        │
├─────────────────────────────────────────────────────────────┤
│ 中间（低注意力）                                             │
│ <how>填写方式</how>                                          │
│ <dependency>依赖关系</dependency>                            │
│ <decision_rule>决策规则</decision_rule>                      │
│ <values>取值范围</values>                                    │
├─────────────────────────────────────────────────────────────┤
│ 结尾（高注意力）                                             │
│ <examples>示例</examples>                                    │
│ <anti_patterns>常见错误</anti_patterns>                      │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 必填字段示例

```python
type: AnalysisType = Field(
    description="""分析类型

<what>派生计算的类型</what>
<when>ALWAYS required (determines other conditional fields)</when>
<how>Detect from keywords in question</how>

<decision_rule>
Prompt Step 5 (识别分析类型) → 填写 type
- "累计" / "累积" / "running" → cumulative
- "排名" / "排序" / "TOP" / "前N名" → ranking
- "占比" / "百分比" / "%" → percentage
- "同比" / "环比" / "对比" → period_compare
- "移动平均" / "滑动" → moving
- SKIP IF: 问题中没有派生计算关键词 → 不填写 analyses 数组
</decision_rule>

<values>
- cumulative: 累计计算（RUNNING_SUM）
- ranking: 排名计算（RANK）
- percentage: 占比计算（PERCENT_OF_TOTAL）
- period_compare: 同比/环比（DIFFERENCE_FROM）
- moving: 移动计算（WINDOW_AVG）
</values>

<examples>
- "按月累计销售额" → cumulative
- "销售额排名前10" → ranking
- "各省份销售额占比" → percentage
</examples>

<anti_patterns>
❌ 简单查询（无派生计算关键词）时填写 type
❌ 混淆 cumulative 和 percentage
</anti_patterns>"""
)
```

### 5.4 条件字段示例

```python
computation_scope: Optional[ComputationScope] = Field(
    default=None,
    description="""计算范围（语义意图）

<what>是按组计算还是跨所有数据计算</what>

<when>ONLY when query has MULTIPLE dimensions (len(dimensions) > 1)</when>

<how>Detect from keywords in question</how>

<dependency>
- field: dimensions (from parent SemanticQuery)
- condition: length > 1
- reason: 单维度不需要指定计算范围，多维度才需要区分 per_group 或 across_all
</dependency>

<decision_rule>
Prompt Step 6 (确定计算范围) → 填写 computation_scope
IF dimensions.length == 1 THEN null (不填写！)
IF dimensions.length > 1:
  - "各XX" / "每个XX" in question → per_group
  - "总" / "全部" / "整体" in question → across_all
  - DEFAULT: per_group
</decision_rule>

<values>
- per_group: 按组计算（每个省份独立累计）
- across_all: 跨所有数据计算（所有数据一起累计）
</values>

<examples>
- "各省份按月累计销售额" (2 dims: 省份, 月) → per_group
- "按月累计总销售额" (2 dims: 月, 总) → across_all
- "按月累计销售额" (1 dim: 月) → null (不填写)
</examples>

<anti_patterns>
❌ 单维度查询时设置 computation_scope
❌ 没有明确"总"关键词时默认 across_all
❌ 混淆 per_group 和 across_all 的语义
</anti_patterns>"""
)
```

### 5.5 Pydantic Validator

**作用**：代码级验证，100% 可靠（LLM 的置信度 ≠ 准确度）

```python
@model_validator(mode='after')
def validate_dependencies(self) -> 'AnalysisSpec':
    """验证字段依赖关系"""
    
    # Rule 1: computation_scope 只在多维度时有效
    # 注意：这个验证需要访问父级 SemanticQuery 的 dimensions
    # 在实际实现中，可能需要在 SemanticQuery 级别验证
    
    # Rule 2: order 只在 ranking 类型时有效
    if self.order is not None and self.type != AnalysisType.RANKING:
        raise ValueError("order should only be set when type=ranking")
    
    # Rule 3: window_size 只在 moving 类型时有效
    if self.window_size is not None and self.type != AnalysisType.MOVING:
        raise ValueError("window_size should only be set when type=moving")
    
    # Rule 4: compare_type 只在 period_compare 类型时有效
    if self.compare_type is not None and self.type != AnalysisType.PERIOD_COMPARE:
        raise ValueError("compare_type should only be set when type=period_compare")
    
    return self
```


---

## 第六部分：完整示例

### 6.1 Understanding Agent 的 Prompt 模板

```python
# tableau_assistant/src/agents/understanding/prompt.py

class UnderstandingPrompt(VizQLPrompt):
    """Understanding Agent 的 Prompt 模板"""
    
    def get_role(self) -> str:
        return """Data analysis expert who understands user questions and extracts structured query intent.

Expertise:
- Semantic understanding of business terminology
- Dimension vs Measure classification
- Time expression parsing
- Analysis type detection (cumulative, ranking, percentage, etc.)"""
    
    def get_task(self) -> str:
        return """Understand user question and output SemanticQuery (pure semantic, no VizQL concepts).

Process: Analyze question → Extract entities → Classify roles → Detect analysis type → Output structured JSON"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Understand user intent
- What does the user want to know?
- Is it a simple query or complex analysis?

Step 2: Extract business entities
- Identify all business terms (e.g., "销售额", "省份", "日期")
- Note: Use exact terms from question, not technical field names

Step 3: Classify entity roles
- Dimension: Categorical field for grouping ("各XX", "按XX", "每个XX")
- Measure: Numeric field for aggregation ("销售额", "利润", "数量")
- Time dimension: Date/time field with granularity ("按年", "按月", "按日")

Step 4: Detect time filters
- Absolute: "2024年", "1月", "Q1"
- Relative: "最近3个月", "上周", "去年同期"

Step 5: Detect analysis type (if any)
- Cumulative: "累计", "累积", "running"
- Ranking: "排名", "排序", "TOP", "前N名"
- Percentage: "占比", "百分比", "%"
- Period compare: "同比", "环比", "对比"
- Moving: "移动平均", "滑动"

Step 6: Determine computation scope (for multi-dimension analysis)
- Per group: "各XX", "每个XX" → Calculate independently per group
- Across all: "总", "全部", "整体" → Calculate across all data
- Note: Only applicable when dimensions.length > 1"""
    
    def get_constraints(self) -> str:
        return """MUST:
- Use business terms from question (not technical field names)
- Fill fields in order specified by <fill_order>
- Follow <decision_rule> for each field

MUST NOT:
- Use VizQL concepts (addressing, partitioning, RUNNING_SUM, etc.)
- Invent fields not mentioned in question
- Set computation_scope for single dimension queries"""
    
    def get_user_template(self) -> str:
        return """Analyze this question and output SemanticQuery:

Question: {question}
Available fields: {metadata_summary}
Current date: {current_date}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return SemanticQuery
```

### 6.2 SemanticQuery 数据模型

```python
# tableau_assistant/src/models/semantic/query.py

from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, List, Literal
from enum import Enum

class AnalysisType(str, Enum):
    CUMULATIVE = "cumulative"
    RANKING = "ranking"
    PERCENTAGE = "percentage"
    PERIOD_COMPARE = "period_compare"
    MOVING = "moving"

class ComputationScope(str, Enum):
    PER_GROUP = "per_group"
    ACROSS_ALL = "across_all"

class SemanticQuery(BaseModel):
    """
    语义查询 - LLM 输出的纯语义模型
    
    <what>Understanding Agent 输出的结构化查询意图，完全不包含 VizQL 技术概念</what>
    
    <decision_tree>
    START
      │
      ├─► measures = ? (ALWAYS fill, at least one)
      │   └─► Extract numeric concepts from question
      │
      ├─► dimensions = ? (IF grouping needed)
      │   └─► Extract categorical concepts from question
      │   └─► Mark is_time and time_granularity for time dimensions
      │
      ├─► filters = ? (IF filtering needed)
      │   └─► Extract filter conditions from question
      │
      ├─► analyses = ? (IF derived calculation needed)
      │   │
      │   └─► For each analysis:
      │       ├─► type = ? (from Step 5)
      │       ├─► target_measure = ? (which measure to analyze)
      │       ├─► aggregation = ? (default: sum)
      │       └─► computation_scope = ? (ONLY if dimensions.length > 1)
      │
      └─► output_control = ? (IF TopN/sorting needed)
    
    END
    </decision_tree>
    
    <fill_order>
    ┌────┬─────────────────────────┬─────────────────────────────────────┐
    │ #  │ Field                   │ Condition                           │
    ├────┼─────────────────────────┼─────────────────────────────────────┤
    │ 1  │ measures                │ ALWAYS (at least one required)      │
    │ 2  │ dimensions              │ IF grouping needed                  │
    │ 3  │ filters                 │ IF filtering needed                 │
    │ 4  │ analyses                │ IF derived calculation needed       │
    │ 5  │ output_control          │ IF TopN/sorting needed              │
    └────┴─────────────────────────┴─────────────────────────────────────┘
    </fill_order>
    
    <examples>
    Example 1 - Simple aggregation (no analysis):
    Input: "各省份的销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "省份", "is_time": false}]
    }
    
    Example 2 - Single dimension cumulative (no computation_scope):
    Input: "按月累计销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "日期", "is_time": true, "time_granularity": "month"}],
        "analyses": [{
            "type": "cumulative",
            "target_measure": "销售额",
            "aggregation": "sum"
        }]
    }
    
    Example 3 - Multi-dimension cumulative (with computation_scope):
    Input: "各省份按月累计销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [
            {"name": "省份", "is_time": false},
            {"name": "日期", "is_time": true, "time_granularity": "month"}
        ],
        "analyses": [{
            "type": "cumulative",
            "target_measure": "销售额",
            "aggregation": "sum",
            "computation_scope": "per_group"
        }]
    }
    </examples>
    
    <anti_patterns>
    ❌ ERROR 1: Using technical field names
    Wrong: {"measures": [{"name": "Sales"}]}
    Right: {"measures": [{"name": "销售额"}]}
    
    ❌ ERROR 2: Including VizQL concepts
    Wrong: {"analyses": [{"addressing": ["Order_Date"]}]}
    Right: {"analyses": [{"computation_scope": "per_group"}]}
    
    ❌ ERROR 3: Setting computation_scope for single dimension
    Input: "按月累计销售额" (only one dimension: 月)
    Wrong: {"analyses": [{"computation_scope": "per_group"}]}
    Right: {"analyses": [{}]} (omit computation_scope)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    measures: List["MeasureSpec"] = Field(
        min_length=1,
        description="""度量列表

<what>需要聚合计算的数值字段</what>
<when>ALWAYS required (at least one)</when>
<how>Extract numeric concepts from question</how>

<decision_rule>
Prompt Step 2 (提取业务实体) + Step 3 (分类实体角色) → 填写 measures
- 识别问题中的数值概念（销售额、利润、数量等）
- 每个数值概念对应一个 MeasureSpec
- 使用问题中的原始术语，不使用技术字段名
</decision_rule>

<examples>
- "各省份的销售额" → [{"name": "销售额", "aggregation": "sum"}]
- "平均利润" → [{"name": "利润", "aggregation": "avg"}]
</examples>"""
    )
    
    dimensions: List["DimensionSpec"] = Field(
        default_factory=list,
        description="""维度列表

<what>用于分组的分类字段</what>
<when>IF question implies grouping ("各XX", "按XX", "每个XX")</when>
<how>Extract categorical concepts from question</how>

<decision_rule>
Prompt Step 2 (提取业务实体) + Step 3 (分类实体角色) → 填写 dimensions
- "各省份" → {"name": "省份", "is_time": false}
- "按月" → {"name": "日期", "is_time": true, "time_granularity": "month"}
- "每个产品" → {"name": "产品", "is_time": false}
</decision_rule>

<examples>
- "各省份按月销售额" → [
    {"name": "省份", "is_time": false},
    {"name": "日期", "is_time": true, "time_granularity": "month"}
  ]
</examples>"""
    )
    
    filters: List["FilterSpec"] = Field(
        default_factory=list,
        description="""筛选列表

<what>数据筛选条件</what>
<when>IF question has filtering conditions</when>
<how>Extract filter conditions from question</how>

<decision_rule>
Prompt Step 4 (检测时间筛选) → 填写 filters
- "2024年" → time_range filter
- "华东地区" → set filter
- "销售额>1000" → quantitative filter
</decision_rule>"""
    )
    
    analyses: List["AnalysisSpec"] = Field(
        default_factory=list,
        description="""分析列表（派生计算）

<what>需要进行的派生计算</what>
<when>IF question implies derived calculation (累计、排名、占比等)</when>
<how>Detect analysis keywords and fill AnalysisSpec</how>

<dependency>
- field: dimensions
- reason: computation_scope depends on dimensions.length
</dependency>

<decision_rule>
Prompt Step 5 (检测分析类型) → 填写 analyses
- "累计" → type=cumulative
- "排名" → type=ranking
- "占比" → type=percentage
- "同比" → type=period_compare
- SKIP IF: 问题中没有派生计算关键词
</decision_rule>"""
    )
    
    output_control: Optional["OutputControl"] = Field(
        None,
        description="""输出控制

<what>结果排序和限制</what>
<when>IF question has TopN or sorting requirements</when>
<how>Detect TopN keywords</how>

<decision_rule>
- "前10名" → TopN with limit=10
- "TOP5" → TopN with limit=5
- "排名前3" → TopN with limit=3
</decision_rule>"""
    )
    
    @model_validator(mode='after')
    def validate_analyses_scope(self) -> 'SemanticQuery':
        """验证 analyses 中的 computation_scope 与 dimensions 的一致性"""
        dim_count = len(self.dimensions)
        
        for analysis in self.analyses:
            if analysis.computation_scope is not None and dim_count <= 1:
                raise ValueError(
                    f"computation_scope should only be set when dimensions.length > 1, "
                    f"but got {dim_count} dimensions"
                )
        
        return self
```


### 6.3 AnalysisSpec 数据模型

```python
# tableau_assistant/src/models/semantic/query.py (continued)

class AnalysisSpec(BaseModel):
    """
    分析规格 - 纯语义，无 VizQL 概念
    
    <what>用户想要进行的派生计算</what>
    
    <decision_tree>
    START
      │
      ├─► type = ? (ALWAYS fill first, determines conditional fields)
      │   │
      │   ├─► cumulative/percentage
      │   │   │
      │   │   └─► dimensions.length > 1 ?
      │   │       ├─ YES → fill computation_scope (default: per_group)
      │   │       └─ NO  → skip computation_scope (null)
      │   │
      │   ├─► ranking
      │   │   ├─► fill order (default: desc)
      │   │   └─► dimensions.length > 1 ?
      │   │       ├─ YES → fill computation_scope (default: per_group)
      │   │       └─ NO  → skip computation_scope (null)
      │   │
      │   ├─► moving
      │   │   ├─► fill window_size (required)
      │   │   └─► dimensions.length > 1 ?
      │   │       ├─ YES → fill computation_scope (default: per_group)
      │   │       └─ NO  → skip computation_scope (null)
      │   │
      │   └─► period_compare
      │       └─► fill compare_type (required)
      │
      ├─► target_measure = ? (ALWAYS fill)
      │
      └─► aggregation = ? (ALWAYS fill, default: sum)
      
    END
    </decision_tree>
    
    <fill_order>
    ┌────┬─────────────────────────┬─────────────────────────────────────┐
    │ #  │ Field                   │ Condition                           │
    ├────┼─────────────────────────┼─────────────────────────────────────┤
    │ 1  │ type                    │ ALWAYS (determines other fields)    │
    │ 2  │ target_measure          │ ALWAYS                              │
    │ 3  │ aggregation             │ ALWAYS (default: sum)               │
    │ 4  │ computation_scope       │ IF dimensions.length > 1            │
    │ 5  │ order                   │ IF type = ranking                   │
    │ 6  │ window_size             │ IF type = moving                    │
    │ 7  │ compare_type            │ IF type = period_compare            │
    └────┴─────────────────────────┴─────────────────────────────────────┘
    </fill_order>
    
    <conditional_groups>
    Group 1: ALWAYS fill (required fields)
    ├─ type
    ├─ target_measure
    └─ aggregation (default: sum)
    
    Group 2: type-dependent fields (fill based on type value)
    ├─ [type=ranking]           → order
    ├─ [type=moving]            → window_size
    └─ [type=period_compare]    → compare_type
    
    Group 3: context-dependent fields (fill based on query context)
    └─ [dimensions.length > 1]  → computation_scope
    </conditional_groups>
    
    <examples>
    Example 1 - Simple cumulative (single dimension):
    Input: "按月累计销售额"
    Output: {
        "type": "cumulative",
        "target_measure": "销售额",
        "aggregation": "sum"
    }
    Note: 没有 computation_scope，因为只有一个维度
    
    Example 2 - Multi-dimension cumulative (per_group):
    Input: "各省份按月累计销售额"
    Output: {
        "type": "cumulative",
        "target_measure": "销售额",
        "aggregation": "sum",
        "computation_scope": "per_group"
    }
    Note: 有 computation_scope，因为有两个维度（省份、月）
    
    Example 3 - Ranking:
    Input: "销售额排名"
    Output: {
        "type": "ranking",
        "target_measure": "销售额",
        "aggregation": "sum",
        "order": "desc"
    }
    </examples>
    
    <anti_patterns>
    ❌ ERROR 1: Setting computation_scope for single dimension
    Input: "按月累计销售额" (only one dimension: 月)
    Wrong: {"computation_scope": "per_group"}
    Right: {} (omit computation_scope)
    
    ❌ ERROR 2: Using technical field names
    Wrong: {"target_measure": "Sales"}
    Right: {"target_measure": "销售额"}
    
    ❌ ERROR 3: Setting order for non-ranking type
    Wrong: {"type": "cumulative", "order": "desc"}
    Right: {"type": "cumulative"} (omit order)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    type: AnalysisType = Field(
        description="""分析类型

<what>派生计算的类型</what>
<when>ALWAYS required (determines other conditional fields)</when>
<how>Detect from keywords in question</how>

<decision_rule>
Prompt Step 5 (检测分析类型) → 填写 type
- "累计" / "累积" / "running" → cumulative
- "排名" / "排序" / "TOP" / "前N名" → ranking
- "占比" / "百分比" / "%" → percentage
- "同比" / "环比" / "对比" → period_compare
- "移动平均" / "滑动" → moving
</decision_rule>

<values>
- cumulative: 累计计算
- ranking: 排名计算
- percentage: 占比计算
- period_compare: 同比/环比
- moving: 移动计算
</values>

<examples>
- "按月累计销售额" → cumulative
- "销售额排名前10" → ranking
- "各省份销售额占比" → percentage
</examples>"""
    )
    
    target_measure: str = Field(
        description="""目标度量（业务术语）

<what>要进行派生计算的度量名称</what>
<when>ALWAYS required</when>
<how>Use exact term from question (business term, not technical field name)</how>

<decision_rule>
- 使用问题中的原始术语
- 必须是 measures 列表中的某个度量名称
</decision_rule>

<examples>
- "按月累计销售额" → "销售额"
- "利润排名" → "利润"
</examples>

<anti_patterns>
❌ Using technical field names: "Sales" instead of "销售额"
</anti_patterns>"""
    )
    
    aggregation: Literal["sum", "avg", "count", "countd", "min", "max"] = Field(
        default="sum",
        description="""聚合方式

<what>派生计算前的基础聚合函数</what>
<when>ALWAYS (default: sum)</when>
<how>Detect from keywords, default to sum</how>

<decision_rule>
- "总" / "合计" / default → sum
- "平均" → avg
- "多少个" / "几种" → countd
- "最大" → max
- "最小" → min
</decision_rule>

<values>
- sum: 求和（默认）
- avg: 平均
- count: 计数
- countd: 去重计数
- min: 最小值
- max: 最大值
</values>"""
    )
    
    computation_scope: Optional[ComputationScope] = Field(
        default=None,
        description="""计算范围（语义意图）

<what>是按组计算还是跨所有数据计算</what>

<when>ONLY when query has MULTIPLE dimensions (len(dimensions) > 1)</when>

<how>Detect from keywords in question</how>

<dependency>
- field: dimensions (from parent SemanticQuery)
- condition: length > 1
- reason: 单维度不需要指定计算范围，多维度才需要区分 per_group 或 across_all
</dependency>

<decision_rule>
Prompt Step 6 (确定计算范围) → 填写 computation_scope
IF dimensions.length == 1 THEN null (不填写！)
IF dimensions.length > 1:
  - "各XX" / "每个XX" in question → per_group
  - "总" / "全部" / "整体" in question → across_all
  - DEFAULT: per_group
</decision_rule>

<values>
- per_group: 按组计算（每个省份独立累计）
- across_all: 跨所有数据计算（所有数据一起累计）
</values>

<examples>
- "各省份按月累计销售额" (2 dims) → per_group
- "按月累计总销售额" (2 dims) → across_all
- "按月累计销售额" (1 dim) → null (不填写)
</examples>

<anti_patterns>
❌ 单维度查询时设置 computation_scope
❌ 没有明确"总"关键词时默认 across_all
</anti_patterns>"""
    )
    
    order: Optional[Literal["asc", "desc"]] = Field(
        default=None,
        description="""排序方向

<what>排名的排序方向</what>

<when>ONLY when type = ranking</when>

<dependency>
- field: type
- condition: type == "ranking"
- reason: 只有排名计算需要指定排序方向
</dependency>

<decision_rule>
IF type != ranking THEN null (不填写！)
IF type == ranking:
  - "前N名" / "TOP" / default → desc (降序，值大的排前面)
  - "后N名" / "BOTTOM" → asc (升序，值小的排前面)
</decision_rule>

<values>
- desc: 降序（默认，值大的排前面）
- asc: 升序（值小的排前面）
</values>

<anti_patterns>
❌ 非 ranking 类型时设置 order
</anti_patterns>"""
    )
    
    window_size: Optional[int] = Field(
        default=None,
        description="""窗口大小

<what>移动计算的窗口大小</what>

<when>ONLY when type = moving</when>

<dependency>
- field: type
- condition: type == "moving"
- reason: 只有移动计算需要指定窗口大小
</dependency>

<decision_rule>
IF type != moving THEN null (不填写！)
IF type == moving:
  - "移动平均3期" → 3
  - "滑动5日" → 5
</decision_rule>

<anti_patterns>
❌ 非 moving 类型时设置 window_size
</anti_patterns>"""
    )
    
    compare_type: Optional[Literal["yoy", "mom", "wow", "dod"]] = Field(
        default=None,
        description="""对比类型

<what>同比/环比的对比类型</what>

<when>ONLY when type = period_compare</when>

<dependency>
- field: type
- condition: type == "period_compare"
- reason: 只有同比/环比计算需要指定对比类型
</dependency>

<decision_rule>
IF type != period_compare THEN null (不填写！)
IF type == period_compare:
  - "同比" / "去年同期" → yoy (Year over Year)
  - "环比" / "上月" → mom (Month over Month)
  - "周环比" → wow (Week over Week)
  - "日环比" → dod (Day over Day)
</decision_rule>

<values>
- yoy: 同比（Year over Year）
- mom: 月环比（Month over Month）
- wow: 周环比（Week over Week）
- dod: 日环比（Day over Day）
</values>

<anti_patterns>
❌ 非 period_compare 类型时设置 compare_type
</anti_patterns>"""
    )
    
    @model_validator(mode='after')
    def validate_type_dependencies(self) -> 'AnalysisSpec':
        """验证类型相关的字段依赖"""
        
        # Rule 1: order 只在 ranking 类型时有效
        if self.order is not None and self.type != AnalysisType.RANKING:
            raise ValueError("order should only be set when type=ranking")
        
        # Rule 2: window_size 只在 moving 类型时有效
        if self.window_size is not None and self.type != AnalysisType.MOVING:
            raise ValueError("window_size should only be set when type=moving")
        
        # Rule 3: compare_type 只在 period_compare 类型时有效
        if self.compare_type is not None and self.type != AnalysisType.PERIOD_COMPARE:
            raise ValueError("compare_type should only be set when type=period_compare")
        
        return self
```


---

## 第七部分：设计原则总结

### 7.1 15 条设计原则

| # | 原则 | 核心思想 | 应用场景 |
|---|------|---------|---------|
| 1 | 最小激活 | 高密度关键词，减少冗余 | Prompt 精简化 |
| 2 | 正交分解 | 字段独立决策，减少依赖 | Schema 结构设计 |
| 3 | 语义一致 | Prompt 和 Schema 术语统一 | 术语对齐 |
| 4 | 渐进约束 | 先理解后结构化 | 复杂任务分解 |
| 5 | ICL 本质 | 示例是模式激活，不是教学 | 示例设计 |
| 6 | 信息瓶颈 | 只保留任务相关信息 | 字段选择 |
| 7 | MDL | 最短描述，最小误差 | 整体简化 |
| 8 | **XML 结构化** | 显式边界标记，Attention 集中 | Schema 字段描述 |
| 9 | **位置敏感** | 开头/结尾高注意力 | 信息布局 |
| 10 | **决策树** | 树状决策路径，替代矩阵 | 条件字段 |
| 11 | **填写顺序** | 先简单后复杂 | 字段顺序 |
| 12 | 选项限制 | 枚举值 ≤ 7 | 枚举设计 |
| 13 | 双向显式 | 正反关系都说明 | 依赖关系 |
| 14 | 外部验证 | Pydantic Validator，代码级 100% 可靠 | 关键决策 |
| 15 | 格式标准化 | 统一格式，避免 Prompt Sensitivity | Prompt 模板 |

### 7.2 核心洞察

```
LLM 的知识空间是一个高维流形
Prompt = 导航坐标（激活正确的知识）
Schema = 着陆区域（约束输出分布）
XML 标签 = 边界标记（提高信息检索效率）
<decision_rule> = 桥梁（思考→填写的映射）
决策树 = 路径指引（引导填写顺序）
Validator = 安全网（代码级 100% 可靠验证）

思考与填写的交织：
- LLM 是逐 token 生成的
- 每填一个字段都是一次"微型思考"
- XML 标签为每次微型思考提供精确的规则定位
- <decision_rule> 将 Prompt 中的抽象思考转化为具体填写动作
```

### 7.3 检查清单

**Prompt 检查**：
- [ ] 是否使用 4 段式结构（Role、Task、Domain Knowledge、Constraints）？
- [ ] 是否提供了清晰的思考步骤（Step 1, 2, 3...）？
- [ ] 是否避免了具体字段名（字段名应在 Schema 中）？
- [ ] 思考步骤是否与 Schema 中的 `<decision_rule>` 对应？

**Schema 检查**：
- [ ] Class Docstring 是否包含 `<decision_tree>` 和 `<fill_order>`？
- [ ] Class Docstring 是否包含 `<examples>` 和 `<anti_patterns>`？
- [ ] 每个字段是否包含 `<what>`, `<when>`, `<how>`？
- [ ] 条件字段是否包含 `<dependency>` 和 `<decision_rule>`？
- [ ] `<decision_rule>` 是否引用了 Prompt 中的思考步骤？
- [ ] 是否遵循了信息布局原则（开头/结尾高注意力）？
- [ ] 是否添加了 Pydantic Validator 进行代码级验证？

---

## 附录：与原设计的对比

| 方面 | 原设计 | 新设计 |
|------|--------|--------|
| XML 标签 | 部分使用 | 完整使用，包含 `<decision_rule>` |
| 决策树 | 无 | 使用 `<decision_tree>` 表达树状决策 |
| 填写顺序 | 简单表格 | 使用 `<fill_order>` 明确顺序和条件 |
| 思考与填写的桥梁 | 隐式 | 显式，通过 `<decision_rule>` 引用 Prompt 步骤 |
| 信息布局 | 未考虑 | 遵循 "Lost in the Middle" 原则 |
| 双向关系 | 部分 | 完整，包含"不填写"的条件 |
| Validator | 简单 | 完整的依赖关系验证 |

---

**文档版本**: v1.0
**最后更新**: 2025-12-05
**参考文档**: `tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md`
