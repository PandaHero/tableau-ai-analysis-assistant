# 附件E：Prompt 模板与数据模型编写指南

## 概述

本文档是针对 Semantic Parser Agent 重构的 Prompt 模板和数据模型编写指南。基于 `tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md` 的核心原则，结合新的 LLM 组合架构（Step 1 + Step 2 + Observer）进行定制。

**核心理念**：思考与填写是交织在一起的，不是"先思考完再填写"，而是"每填一个字段都伴随一次微型思考"。

---

## 第一部分：核心原则

### 1.1 职责边界

> **Prompt 教 LLM 如何思考，Schema 告诉 LLM 输出什么**
> **`<rule>` 是思考与填写的桥梁**

| 内容类型 | Prompt | Schema | 说明 |
|---------|--------|--------|------|
| 领域概念（三元模型、分区） | ✅ | ❌ | 全局知识 |
| 推理步骤（抽象） | ✅ | ❌ | HOW to think |
| 字段含义 | ❌ | ✅ `<what>` | 字段代表什么 |
| 填写条件 | ❌ | ✅ `<when>` | 何时填写 |
| 决策规则 | ❌ | ✅ `<rule>` | 思考→填写的桥梁 |
| 负面约束 | ❌ | ✅ `<must_not>` | 避免的错误 |

### 1.2 黄金法则

- 如果提到具体字段名 → 放在 Schema
- 如果是通用分析方法 → 放在 Prompt
- 如果需要将思考转化为填写 → 使用 Schema 中的 `<rule>`

### 1.3 信息布局原则（Lost in the Middle）

LLM 对开头和结尾的注意力最高：
- **开头**：放 `<what>` 和 `<when>`（核心语义和条件）
- **中间**：放 `<rule>` 和 `<dependency>`（次要信息）
- **结尾**：放 `<must_not>`（最近的参考）

---

## 第二部分：XML 标签规范

### 2.1 字段级标签

| 标签 | 含义 | 必填 | 位置 | Token 限制 |
|------|------|------|------|-----------|
| `<what>` | 字段含义 | ✅ | 开头 | ≤20 tokens |
| `<when>` | 填写条件 | ✅ | 开头 | ≤20 tokens |
| `<rule>` | 决策规则 | 复杂条件 | 中间 | ≤40 tokens |
| `<dependency>` | 依赖关系 | 条件字段 | 中间 | ≤20 tokens |
| `<must_not>` | 负面约束 | 推荐 | 结尾 | ≤20 tokens |

**总计：每个字段描述 ≤100 tokens**

### 2.2 Class Docstring 标签

| 标签 | 含义 | 限制 |
|------|------|------|
| `<what>` | 模型含义 | 1 句话 |
| `<fill_order>` | 填写顺序 | 编号列表 |
| `<examples>` | 完整示例 | ≤2 个简单示例 |
| `<anti_patterns>` | 常见错误 | ≤3 个最常见错误 |

### 2.3 决策树格式（简单文本，非 ASCII 艺术）

**正确格式**：
```
1. type (ALWAYS first)
2. target (ALWAYS)
3. partition_by (ALWAYS, can be empty)
4. operation (ALWAYS)
   - 4.1 params.window_size (if type=MOVING_AVG)
   - 4.2 params.n (if type=PERIOD_AGO)
```

**错误格式**（不要使用 ASCII 艺术）：
```
❌ 不要使用：│、├、─、►、└ 等字符
```

---

## 第三部分：Prompt 模板设计

### 3.1 4 段式结构

```python
class YourPrompt(VizQLPrompt):
    def get_role(self) -> str:
        """角色定义（2-3 句话）"""
        
    def get_task(self) -> str:
        """任务定义（1 句话 + Process 流程）"""
        
    def get_specific_domain_knowledge(self) -> str:
        """领域知识 + 思考步骤（不涉及具体字段名）"""
        
    def get_constraints(self) -> str:
        """约束条件（MUST / MUST NOT）"""
```

### 3.2 Step 1 Prompt 模板

```python
class Step1Prompt(VizQLPrompt):
    """Step 1: 语义理解与问题重述"""
    
    def get_role(self) -> str:
        return """Semantic understanding expert for data analysis queries.

Expertise: Question restatement, Three-element model extraction, Intent classification"""

    def get_task(self) -> str:
        return """Restate user's follow-up question as complete, standalone question.

Process: Merge history → Extract What/Where/How → Classify intent → Generate restatement"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Three-Element Model**
Query = What × Where × How
- What: Target measures + aggregation
- Where: Dimensions + filters
- How: SIMPLE | RANKING | CUMULATIVE | COMPARISON | GRANULARITY

**Think step by step:**
Step 1: Understand user intent
Step 2: Extract business entities (use exact terms from question)
Step 3: Classify entity roles (dimension vs measure)
Step 4: Detect analysis type from keywords
Step 5: Preserve partition intent (每月/当月/全国 etc.)

**Intent Classification**
- DATA_QUERY: Has queryable fields, info complete
- CLARIFICATION: References unspecified values
- GENERAL: Asks about metadata/fields
- IRRELEVANT: Not about data analysis"""

    def get_constraints(self) -> str:
        return """MUST: Preserve partition intent, Use business terms, Provide reasoning
MUST NOT: Lose partition keywords, Invent fields, Classify as DATA_QUERY if incomplete"""
```

### 3.3 Step 2 Prompt 模板

```python
class Step2Prompt(VizQLPrompt):
    """Step 2: 计算推理与自我验证"""
    
    def get_role(self) -> str:
        return """Computation reasoning expert for data analysis.

Expertise: Computation inference, Self-validation, Partition inference"""

    def get_task(self) -> str:
        return """Infer computation from restated_question, then validate against Step 1 output.

Process: Infer target → Infer partition_by → Infer operation → Validate"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Computation Model**
Computation = Target × Partition × Operation

**Think step by step:**
Step 1: Infer target from restated_question (must be in what.measures)
Step 2: Infer partition_by from keywords (must be subset of where.dimensions)
Step 3: Infer operation.type (must match how_type via OPERATION_TYPE_MAPPING)
Step 4: Validate all three checks

**Partition Keywords**
- 全局/总/无分区词 → []
- 每月/月内/当月 → [时间维度]
- 每省/省内 → [省份]

**OPERATION_TYPE_MAPPING**
- RANKING → RANK, DENSE_RANK
- CUMULATIVE → RUNNING_SUM, RUNNING_AVG, MOVING_AVG, MOVING_SUM
- COMPARISON → PERCENT, DIFFERENCE, GROWTH_RATE, YEAR_AGO, PERIOD_AGO
- GRANULARITY → FIXED"""

    def get_constraints(self) -> str:
        return """MUST: Infer from restated_question, Validate against Step 1, Report inconsistencies
MUST NOT: Infer partition_by not in dimensions, Use operation.type not matching how_type"""
```

### 3.4 Observer Prompt 模板

```python
class ObserverPrompt(VizQLPrompt):
    """Observer: 一致性检查"""
    
    def get_role(self) -> str:
        return """Quality assurance expert for semantic parsing.

Expertise: Consistency checking, Conflict detection, Decision making"""

    def get_task(self) -> str:
        return """Check consistency between Step 1 and Step 2 outputs.

Process: Check restatement completeness → Review validation → Check semantics → Decide"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Consistency Checks**
1. Restatement completeness: Did restated_question preserve key info?
2. Structure consistency: Review Step 2's validation results
3. Semantic consistency: Does computation match intent?

**Decision Rules**
- All checks pass → ACCEPT
- Small conflict, can fix → CORRECT
- Large conflict → RETRY
- Cannot determine → CLARIFY"""

    def get_constraints(self) -> str:
        return """MUST: Check original_question, Review validation, Provide correction if CORRECT
MUST NOT: Accept when validation failed, Retry for minor issues, Clarify when clear"""
```

---

## 第四部分：数据模型设计

### 4.1 字段描述格式（≤100 tokens）

**简单字段示例**：
```python
restated_question: str = Field(
    description="""<what>Complete standalone question in natural language</what>
<when>ALWAYS required</when>
<rule>Must preserve partition intent (每月→"在每个月内", 当月→"当月")</rule>
<must_not>Lose partition keywords (will cause wrong computation scope)</must_not>"""
)
```

**条件字段示例**：
```python
partition_by: list[str] = Field(
    default_factory=list,
    description="""<what>Dimensions to partition by</what>
<when>ALWAYS fill (can be empty list)</when>
<rule>全局/总→[], 每月/当月→[时间维度], 每省→[省份]</rule>
<dependency>partition_by ⊆ where.dimensions</dependency>
<must_not>Include dimension not in where.dimensions (will cause error)</must_not>"""
)
```

### 4.2 Step1Output 模型

```python
class Step1Output(BaseModel):
    """Step 1 output: Semantic understanding and question restatement.
    
    <what>Restated question + structured What/Where/How + intent classification</what>
    
    <fill_order>
    1. restated_question (ALWAYS first)
    2. what (ALWAYS)
    3. where (ALWAYS)
    4. how_type (ALWAYS)
    5. intent (ALWAYS)
    </fill_order>
    
    <examples>
    Input: "各省份销售额"
    Output: {"restated_question": "按省份分组，计算销售额总和", "how_type": "SIMPLE", "intent": {"type": "DATA_QUERY"}}
    
    Input: History="各省份各月销售额", Current="每月排名呢？"
    Output: {"restated_question": "按省份和月份分组，在每个月内按销售额降序排名", "how_type": "RANKING"}
    </examples>
    
    <anti_patterns>
    ❌ Losing partition intent: "每月排名" → "按销售额排名" (lost "每月")
    ❌ Using technical field names: {"field": "[Sales].[Amount]"}
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    restated_question: str = Field(
        description="""<what>Complete standalone question</what>
<when>ALWAYS required</when>
<rule>Preserve partition intent (每月→"在每个月内")</rule>
<must_not>Lose partition keywords (will cause wrong scope)</must_not>"""
    )
    
    what: What = Field(
        description="""<what>Target measures</what>
<when>ALWAYS required</when>
<rule>Extract from question, use business terms</rule>"""
    )
    
    where: Where = Field(
        description="""<what>Dimensions + filters</what>
<when>ALWAYS required</when>
<rule>Extract from question, use business terms</rule>"""
    )
    
    how_type: HowType = Field(
        description="""<what>Computation type</what>
<when>ALWAYS required</when>
<rule>排名→RANKING, 累计→CUMULATIVE, 占比/同比→COMPARISON, 固定粒度→GRANULARITY, 其他→SIMPLE</rule>"""
    )
    
    intent: Intent = Field(
        description="""<what>Intent classification + reasoning</what>
<when>ALWAYS required</when>
<rule>Complete info→DATA_QUERY, Unspecified values→CLARIFICATION, Metadata→GENERAL, Unrelated→IRRELEVANT</rule>"""
    )
```

### 4.3 Step2Output 模型

```python
class Step2Output(BaseModel):
    """Step 2 output: Computation reasoning and self-validation.
    
    <what>Computation definitions + validation results</what>
    
    <fill_order>
    1. reasoning (ALWAYS first)
    2. computations (ALWAYS)
    3. validation (ALWAYS)
    </fill_order>
    
    <examples>
    Input: restated_question="按省份分组，在每个月内按销售额降序排名"
    Output: {"computations": [{"target": "销售额", "partition_by": ["订单日期"], "operation": {"type": "RANK"}}], "validation": {"all_valid": true}}
    </examples>
    
    <anti_patterns>
    ❌ partition_by not in dimensions: where.dimensions=["省份"], partition_by=["月份"]
    ❌ operation.type not matching how_type: how_type=RANKING, operation.type=PERCENT
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    reasoning: str = Field(
        description="""<what>Inference process description</what>
<when>ALWAYS required</when>
<rule>Explain how target, partition_by, operation were inferred</rule>"""
    )
    
    computations: list[Computation] = Field(
        description="""<what>Computation definitions</what>
<when>ALWAYS required</when>
<rule>Each has target, partition_by, operation</rule>"""
    )
    
    validation: Step2Validation = Field(
        description="""<what>Self-validation result</what>
<when>ALWAYS required</when>
<rule>Check target, partition_by, operation against Step 1 output</rule>"""
    )
```

### 4.4 Computation 模型

```python
class Computation(BaseModel):
    """Computation = Target × Partition × Operation
    
    <what>Core computation definition (platform-agnostic)</what>
    
    <examples>
    Global ranking: {"target": "销售额", "partition_by": [], "operation": {"type": "RANK"}}
    Monthly ranking: {"target": "销售额", "partition_by": ["订单日期"], "operation": {"type": "RANK"}}
    </examples>
    
    <anti_patterns>
    ❌ partition_by not subset of dimensions
    ❌ operation.type not in OPERATION_TYPE_MAPPING[how_type]
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    target: str = Field(
        description="""<what>Measure field to compute</what>
<when>ALWAYS required</when>
<rule>Must be one of what.measures</rule>
<must_not>Use technical field name (will cause mapping error)</must_not>"""
    )
    
    partition_by: list[str] = Field(
        default_factory=list,
        description="""<what>Partition dimensions</what>
<when>ALWAYS fill (can be empty)</when>
<rule>全局→[], 每月→[时间维度], 每省→[省份]</rule>
<dependency>partition_by ⊆ where.dimensions</dependency>
<must_not>Include dimension not in where.dimensions (will cause error)</must_not>"""
    )
    
    operation: Operation = Field(
        description="""<what>Computation operation</what>
<when>ALWAYS required</when>
<rule>Must match how_type via OPERATION_TYPE_MAPPING</rule>
<dependency>operation.type ∈ OPERATION_TYPE_MAPPING[how_type]</dependency>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>Display name for result</what>
<when>Optional</when>"""
    )
```

### 4.5 ObserverOutput 模型

```python
class ObserverOutput(BaseModel):
    """Observer output: Consistency check result.
    
    <what>Consistency check + decision + correction</what>
    
    <fill_order>
    1. is_consistent (ALWAYS first)
    2. conflicts (ALWAYS, can be empty)
    3. decision (ALWAYS)
    4. correction (if decision=CORRECT)
    5. final_result (if decision=ACCEPT or CORRECT)
    </fill_order>
    
    <examples>
    Consistent: {"is_consistent": true, "conflicts": [], "decision": "ACCEPT", "final_result": {...}}
    Correctable: {"is_consistent": false, "conflicts": [...], "decision": "CORRECT", "correction": {...}}
    </examples>
    
    <anti_patterns>
    ❌ ACCEPT when validation failed
    ❌ RETRY for minor fixable issues
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    is_consistent: bool = Field(
        description="""<what>Whether Step 1 and Step 2 are consistent</what>
<when>ALWAYS required</when>
<rule>Check restatement, structure, semantics</rule>"""
    )
    
    conflicts: list[Conflict] = Field(
        default_factory=list,
        description="""<what>Inconsistencies found</what>
<when>ALWAYS fill (empty if consistent)</when>"""
    )
    
    decision: ObserverDecision = Field(
        description="""<what>Action to take</what>
<when>ALWAYS required</when>
<rule>All pass→ACCEPT, Small conflict→CORRECT, Large conflict→RETRY, Unclear→CLARIFY</rule>"""
    )
    
    correction: Correction | None = Field(
        default=None,
        description="""<what>Correction details</what>
<when>ONLY when decision=CORRECT</when>
<dependency>decision == "CORRECT"</dependency>"""
    )
    
    final_result: Computation | None = Field(
        default=None,
        description="""<what>Final computation</what>
<when>ONLY when decision=ACCEPT or CORRECT</when>
<dependency>decision in ["ACCEPT", "CORRECT"]</dependency>"""
    )
```

---

## 第五部分：枚举类型定义

### 5.1 HowType

```python
class HowType(str, Enum):
    """Computation type (Step 1 output).
    
    <rule>
    排名/Top N → RANKING
    累计/累积 → CUMULATIVE
    占比/同比/环比 → COMPARISON
    固定粒度 → GRANULARITY
    其他 → SIMPLE
    </rule>
    """
    SIMPLE = "SIMPLE"
    RANKING = "RANKING"
    CUMULATIVE = "CUMULATIVE"
    COMPARISON = "COMPARISON"
    GRANULARITY = "GRANULARITY"
```

### 5.2 OperationType

```python
class OperationType(str, Enum):
    """Operation type (Step 2 output).
    
    <dependency>Must match HowType via OPERATION_TYPE_MAPPING</dependency>
    """
    # RANKING
    RANK = "RANK"
    DENSE_RANK = "DENSE_RANK"
    # CUMULATIVE
    RUNNING_SUM = "RUNNING_SUM"
    RUNNING_AVG = "RUNNING_AVG"
    MOVING_AVG = "MOVING_AVG"
    MOVING_SUM = "MOVING_SUM"
    # COMPARISON
    PERCENT = "PERCENT"
    DIFFERENCE = "DIFFERENCE"
    GROWTH_RATE = "GROWTH_RATE"
    YEAR_AGO = "YEAR_AGO"
    PERIOD_AGO = "PERIOD_AGO"
    # GRANULARITY
    FIXED = "FIXED"
```

### 5.3 IntentType

```python
class IntentType(str, Enum):
    """Intent type (Step 1 output).
    
    <rule>
    Complete info → DATA_QUERY
    Unspecified values → CLARIFICATION
    Metadata question → GENERAL
    Unrelated → IRRELEVANT
    </rule>
    """
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"
    IRRELEVANT = "IRRELEVANT"
```

### 5.4 ObserverDecision

```python
class ObserverDecision(str, Enum):
    """Observer decision.
    
    <rule>
    All checks pass → ACCEPT
    Small conflict, can fix → CORRECT
    Large conflict → RETRY
    Cannot determine → CLARIFY
    </rule>
    """
    ACCEPT = "ACCEPT"
    CORRECT = "CORRECT"
    RETRY = "RETRY"
    CLARIFY = "CLARIFY"
```

---

## 第六部分：LLM 自我验证参考信息

### 6.1 设计说明

**重要**：Step 2 的验证是 **LLM 自我验证**，不是代码验证。

```
Step 2 LLM 调用
├── 推理：从 restated_question 推断 target, partition_by, operation
└── 自我验证：LLM 自己检查推理结果是否与 Step 1 输出一致
    ├── target_check: target ∈ what.measures?
    ├── partition_by_check: partition_by ⊆ where.dimensions?
    └── operation_check: operation.type 与 how_type 匹配?
```

下面的映射关系是**放在 Prompt 或 Schema 中给 LLM 参考的**，让 LLM 知道如何判断 operation.type 与 how_type 是否匹配。

### 6.2 HowType → OperationType 映射（给 LLM 的参考）

这个映射应该放在 **Step 2 Prompt 的领域知识**部分：

```
**OPERATION_TYPE_MAPPING（用于 operation_check 验证）**
- RANKING → RANK, DENSE_RANK
- CUMULATIVE → RUNNING_SUM, RUNNING_AVG, MOVING_AVG, MOVING_SUM
- COMPARISON → PERCENT, DIFFERENCE, GROWTH_RATE, YEAR_AGO, PERIOD_AGO
- GRANULARITY → FIXED
```

### 6.3 在 Schema 中的使用

在 `Step2Validation.operation_check` 字段描述中引用：

```python
operation_check: ValidationCheck = Field(
    description="""<what>Check if operation.type matches how_type</what>
<when>ALWAYS required</when>
<rule>Use OPERATION_TYPE_MAPPING from prompt to verify match</rule>
<must_not>Mark as match if operation.type not in mapping[how_type]</must_not>"""
)
```

### 6.4 为什么是 LLM 验证而非代码验证？

| 方式 | 优点 | 缺点 |
|------|------|------|
| **LLM 自我验证** | 可以理解语义、处理边界情况 | 可能出错 |
| **代码验证** | 100% 准确 | 无法处理语义模糊情况 |

我们选择 LLM 自我验证，因为：
1. LLM 可以理解"为什么不匹配"并给出 reasoning
2. Observer 可以复核 LLM 的验证结果
3. 形成 Step 1 → Step 2 → Observer 的闭环检查

---

## 第七部分：设计原则速查

| # | 原则 | 应用 |
|---|------|------|
| 1 | 最小激活 | Prompt 使用高密度关键词 |
| 2 | 正交分解 | 字段独立决策 |
| 3 | 语义一致 | Prompt 和 Schema 使用相同术语 |
| 4 | 渐进约束 | Step 1 → Step 2 → Observer |
| 5 | XML 结构化 | 使用 XML 标签标记边界 |
| 6 | 位置敏感 | 关键信息放开头/结尾 |
| 7 | 填写顺序 | 先简单后复杂 |
| 8 | 选项限制 | 枚举值 ≤ 7 |
| 9 | 双向显式 | 正反关系都说明 |
| 10 | 外部验证 | Pydantic Validator |
| 11 | 字段描述精简 | ≤100 tokens |
| 12 | 决策树简化 | 编号列表，非 ASCII 艺术 |
| 13 | 负面约束强调 | `<must_not>` 标签 |
| 14 | Docstring 精简 | ≤2 示例，≤3 反模式 |

---

## 第八部分：检查清单

### Prompt 检查
- [ ] 是否提到具体字段名？→ 移到 Schema
- [ ] 是否在教 LLM 如何分析？→ 保留
- [ ] 是否有重复的字段说明？→ 删除

### Schema 检查
- [ ] 每个字段描述是否 ≤100 tokens？
- [ ] 是否包含 `<what>`, `<when>`？
- [ ] 条件字段是否有 `<dependency>`？
- [ ] 是否有 `<must_not>` 强调负面约束？
- [ ] Class Docstring 是否有 `<fill_order>`？
- [ ] 示例是否 ≤2 个？
- [ ] 反模式是否 ≤3 个？
- [ ] 决策树是否使用编号列表格式？

---

## 与原文档的差异

| 方面 | 原文档 | 本文档 |
|------|--------|--------|
| 架构 | 单步 LLM | LLM 组合（Step 1 + Step 2 + Observer） |
| 核心模型 | AnalysisSpec | Step1Output, Step2Output, Computation |
| 计算类型 | type 枚举 | HowType + OperationType 分离 |
| 核心抽象 | 无 | partition_by 统一分区 |
| 验证机制 | Pydantic Validator | Step 2 自我验证 + Observer |
| 意图分类 | 无 | IntentType 四分类 |
| 字段描述 | 无限制 | ≤100 tokens |
| 决策树格式 | ASCII 艺术 | 编号列表 |
| 负面约束 | `<anti_patterns>` | `<must_not>` 标签 |
