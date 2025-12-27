# 附件E：Prompt 模板与数据模型编写指南

## 概述

本文档是针对 Semantic Parser Agent 重构的 Prompt 模板和数据模型编写指南。基于 `tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md` 的核心原则，结合新的 LLM 组合架构（Step 1 + Step 2 + Observer）进行定制。

**核心理念**：思考与填写是交织在一起的，不是"先思考完再填写"，而是"每填一个字段都伴随一次微型思考"。

---

## 第一部分：核心原则

### 1.1 职责边界

> **Prompt 教 LLM 如何思考，Schema 告诉 LLM 输出什么**

| 内容类型 | Prompt | Schema | 说明 |
|---------|--------|--------|------|
| 领域概念（三元模型、分区） | ✅ | ❌ | 全局知识 |
| 推理步骤（抽象） | ✅ | ❌ | HOW to think |
| 字段含义 | ❌ | ✅ `<what>` | 字段代表什么 |
| 填写条件 | ❌ | ✅ `<when>` | 何时填写 |
| 枚举选择规则 | ❌ | ✅ Enum `<rule>` | 如何选择枚举值 |
| 依赖关系 | ❌ | ✅ `<dependency>` | 字段间依赖 |
| 负面约束 | ❌ | ✅ `<must_not>` | 避免的错误 |

### 1.2 黄金法则

- 如果提到具体字段名 → 放在 Schema
- 如果是通用分析方法 → 放在 Prompt
- 枚举选择规则 → 只在 Enum docstring 的 `<rule>` 中
- Field 类型是 Enum 时 → Field description 只需 `<what>` 和 `<when>`

### 1.3 信息去重原则

**每种信息只在最相关位置出现一次**：

| 信息类型 | 唯一位置 |
|---------|---------|
| 枚举选择规则 | Enum docstring `<rule>` |
| 填写顺序 | Class docstring `<fill_order>` |
| 完整示例 | Class docstring `<examples>` |
| 反模式 | Class docstring `<anti_patterns>` |
| 字段含义 | Field `<what>` |
| 填写条件 | Field `<when>` |
| 依赖关系 | Field `<dependency>` |

### 1.4 语言规范

**必须使用全英文**，不要中英文混杂。

---

## 第二部分：XML 标签规范

### 2.1 Enum Docstring 标签

**两种格式**：

| 格式 | 适用场景 | 示例 |
|-----|---------|------|
| 带 `<rule>` | LLM 需要根据输入选择值 | CalcType, IntentType, ObserverDecision |
| 一行格式 | 只解释值含义，无选择逻辑 | RankStyle, SortDirection, AggregationType |

### 2.2 Class Docstring 标签

| 标签 | 用途 | 限制 |
|------|------|------|
| `<fill_order>` | 填写顺序 | 编号列表 |
| `<examples>` | 完整示例 | ≤2 个 |
| `<anti_patterns>` | 常见错误 | ≤3 个，用 X 前缀 |

### 2.3 Field Description 标签

| 标签 | 用途 | 必填 | 位置 |
|------|------|------|------|
| `<what>` | 字段含义 | ✅ | 第一 |
| `<when>` | 填写条件 | ✅ | 第二 |
| `<rule>` | 决策规则（非Enum相关） | 可选 | 中间 |
| `<dependency>` | 依赖关系 | 条件字段 | 中间 |
| `<must_not>` | 负面约束 | 推荐 | 最后 |

**关键规则**：如果字段类型是带 `<rule>` 的 Enum，Field description **不要重复** Enum 的规则。

### 2.4 Token 限制

| 位置 | 限制 |
|------|------|
| 每个 Field description | ≤100 tokens |
| Class docstring examples | ≤2 个 |
| Class docstring anti_patterns | ≤3 个 |

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
- How: SIMPLE (no computation) | COMPLEX (needs Step 2)

**Think step by step:**
Step 1: Understand user intent
Step 2: Extract business entities (use exact terms from question)
Step 3: Classify entity roles (dimension vs measure)
Step 4: Detect if complex computation needed (ranking, running total, LOD, etc.)
Step 5: Preserve partition intent (per month/within month etc.)

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

Process: Infer target → Infer calc_type → Infer partition_by → Fill params → Validate"""

    def get_specific_domain_knowledge(self) -> str:
        return """**Computation Model**
Computation = Target × CalcType × Partition × Params

**Think step by step:**
Step 1: Infer target from restated_question (must be in what.measures)
Step 2: Infer calc_type from question keywords (see CalcType enum rules)
Step 3: Infer partition_by from scope keywords (must be subset of where.dimensions)
Step 4: Fill params based on calc_type
Step 5: Validate all three checks

**Partition Keywords**
- global/total/no scope word → []
- per month/within month → [time dimension]
- per province → [province]"""

    def get_constraints(self) -> str:
        return """MUST: Infer from restated_question, Validate against Step 1, Report inconsistencies
MUST NOT: Infer partition_by not in dimensions, Fill params not matching calc_type"""
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

## 第四部分：数据模型设计概述

本部分概述数据模型设计的核心结构。详细的编写规范和完整案例请参见**第十部分**。

### 4.1 核心模型关系

```
Step1Output (语义理解)
├── restated_question: str
├── what: What (measures)
├── where: Where (dimensions + filters)
├── how_type: HowType (SIMPLE | COMPLEX)
└── intent: Intent

Step2Output (计算推理) - 仅当 how_type=COMPLEX 时触发
├── reasoning: str
├── computations: list[Computation]
└── validation: Step2Validation

Computation (核心计算抽象)
├── target: str
├── calc_type: CalcType
├── partition_by: list[str]
├── params: CalcParams
└── alias: str | None

ObserverOutput (一致性检查) - 仅当 validation.all_valid=False 时触发
├── is_consistent: bool
├── conflicts: list[Conflict]
├── decision: ObserverDecision
├── correction: Correction | None
└── final_result: Computation | None
```

### 4.2 数据流

```
用户问题 → Step1Output → (if COMPLEX) → Step2Output → (if validation failed) → ObserverOutput
```

### 4.3 关键设计原则

1. **信息去重**：每种信息只在最相关位置出现一次（详见第七部分）
2. **Enum 规则集中**：枚举选择规则只在 Enum docstring 的 `<rule>` 中
3. **Field 精简**：字段类型是 Enum 时，Field description 只需 `<what>` 和 `<when>`
4. **全英文**：所有 docstring 和 description 使用英文

---

## 第五部分：枚举类型定义

### 5.1 HowType

```python
class HowType(str, Enum):
    """Computation complexity: SIMPLE=no Step2 | COMPLEX=needs Step2"""
    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"
```

### 5.2 CalcType

```python
class CalcType(str, Enum):
    """Calculation type (Step2 output, platform-agnostic).
    
    <rule>
    Table Calculations:
    - ranking/Top N -> RANK, DENSE_RANK, PERCENTILE
    - running total/YTD -> RUNNING_TOTAL
    - moving average -> MOVING_CALC
    - percent of total -> PERCENT_OF_TOTAL
    - difference/change -> DIFFERENCE
    - growth rate/MoM -> PERCENT_DIFFERENCE
    
    LOD (change aggregation granularity):
    - per customer X/per product Y -> LOD_FIXED
    - add dimension -> LOD_INCLUDE
    - remove dimension -> LOD_EXCLUDE
    </rule>
    """
    # Ranking
    RANK = "RANK"
    DENSE_RANK = "DENSE_RANK"
    PERCENTILE = "PERCENTILE"
    # Running
    RUNNING_TOTAL = "RUNNING_TOTAL"
    MOVING_CALC = "MOVING_CALC"
    # Percent
    PERCENT_OF_TOTAL = "PERCENT_OF_TOTAL"
    # Difference
    DIFFERENCE = "DIFFERENCE"
    PERCENT_DIFFERENCE = "PERCENT_DIFFERENCE"
    # LOD
    LOD_FIXED = "LOD_FIXED"
    LOD_INCLUDE = "LOD_INCLUDE"
    LOD_EXCLUDE = "LOD_EXCLUDE"
```

### 5.3 IntentType

```python
class IntentType(str, Enum):
    """Intent type.
    
    <rule>
    complete query info -> DATA_QUERY
    needs clarification/unspecified values -> CLARIFICATION
    metadata/field question -> GENERAL
    off-topic/unrelated -> IRRELEVANT
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
    all checks pass -> ACCEPT
    small fixable conflict -> CORRECT
    large structural conflict -> RETRY
    cannot determine, need user -> CLARIFY
    </rule>
    """
    ACCEPT = "ACCEPT"
    CORRECT = "CORRECT"
    RETRY = "RETRY"
    CLARIFY = "CLARIFY"
```

### 5.5 Auxiliary Enums (One-line Format)

```python
class RankStyle(str, Enum):
    """Ranking style: COMPETITION=1,2,2,4 | DENSE=1,2,2,3 | UNIQUE=1,2,3,4"""
    COMPETITION = "COMPETITION"
    DENSE = "DENSE"
    UNIQUE = "UNIQUE"


class RelativeTo(str, Enum):
    """Difference reference: PREVIOUS=MoM | FIRST=vs start | LAST=vs end"""
    PREVIOUS = "PREVIOUS"
    NEXT = "NEXT"
    FIRST = "FIRST"
    LAST = "LAST"


class CalcAggregation(str, Enum):
    """Running/moving aggregation: SUM | AVG | MIN | MAX"""
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


class SortDirection(str, Enum):
    """Sort direction: DESC=descending (high to low) | ASC=ascending (low to high)"""
    ASC = "ASC"
    DESC = "DESC"


class AggregationType(str, Enum):
    """Aggregation type: SUM | AVG | COUNT | COUNTD (count distinct) | MIN | MAX | MEDIAN | STDEV | VAR"""
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNTD = "COUNTD"
    MIN = "MIN"
    MAX = "MAX"
    MEDIAN = "MEDIAN"
    STDEV = "STDEV"
    VAR = "VAR"
```

---

## 第六部分：LLM 自我验证参考信息

### 6.1 设计说明

**重要**：Step 2 的验证是 **LLM 自我验证**，不是代码验证。

```
Step 2 LLM 调用
├── 推理：从 restated_question 推断 target, calc_type, partition_by, params
└── 自我验证：LLM 自己检查推理结果是否与 Step 1 输出一致
    ├── target_check: target ∈ what.measures?
    ├── partition_by_check: partition_by ⊆ where.dimensions?
    └── calc_type_check: calc_type 与问题意图匹配?
```

### 6.2 Step2Validation 模型

```python
class Step2Validation(BaseModel):
    """Step 2 self-validation (LLM validates against Step 1).
    
    <fill_order>
    1. target_check
    2. partition_by_check
    3. calc_type_check
    4. all_valid
    5. inconsistencies (if any)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    target_check: ValidationCheck = Field(
        description="""<what>Check target in what.measures</what>
<when>ALWAYS</when>"""
    )
    
    partition_by_check: ValidationCheck = Field(
        description="""<what>Check partition_by subset of where.dimensions</what>
<when>ALWAYS</when>"""
    )
    
    calc_type_check: ValidationCheck = Field(
        description="""<what>Check calc_type matches question intent</what>
<when>ALWAYS</when>"""
    )
    
    all_valid: bool = Field(
        description="""<what>All checks passed</what>
<when>ALWAYS</when>
<rule>True only if all is_match=True</rule>"""
    )
    
    inconsistencies: list[str] = Field(
        default_factory=list,
        description="""<what>List of mismatches</what>
<when>If all_valid=False</when>"""
    )
```

### 6.3 为什么是 LLM 验证而非代码验证？

| 方式 | 优点 | 缺点 |
|------|------|------|
| **LLM 自我验证** | 可以理解语义、处理边界情况 | 可能出错 |
| **代码验证** | 100% 准确 | 无法处理语义模糊情况 |

我们选择 LLM 自我验证，因为：
1. LLM 可以理解"为什么不匹配"并给出 reasoning
2. Observer 可以复核 LLM 的验证结果
3. 形成 Step 1 → Step 2 → Observer 的闭环检查

---

## 第七部分：信息去重原则

### 7.1 JSON Schema 中 LLM 能看到的内容

Pydantic 的 `model_json_schema()` 会将以下内容序列化到 JSON Schema：

| 来源 | 是否进入 Schema | 说明 |
|------|----------------|------|
| Enum docstring | ✅ | 进入 `$defs.EnumName.description` |
| Class docstring | ✅ | 进入 `$defs.ClassName.description` |
| Field description | ✅ | 进入 `properties.fieldName.description` |
| Python 注释 (`#`) | ❌ | 不进入 Schema |
| 模块 docstring | ❌ | 不进入 Schema |

**结论**：Enum docstring、Class docstring、Field description 都会被 LLM 看到，因此需要避免重复。

### 7.2 信息分布原则

每种信息只在**最相关的位置**出现一次：

| 信息类型 | 应放位置 | 原因 |
|---------|---------|------|
| 枚举值选择规则 | Enum docstring `<rule>` | 枚举是值的"说明书" |
| 填写顺序 | Class docstring `<fill_order>` | 类级别的指导 |
| 完整示例 | Class docstring `<examples>` | 展示字段组合 |
| 反模式 | Class docstring `<anti_patterns>` | 类级别的错误 |
| 字段含义 | Field `<what>` | 字段级别 |
| 填写条件 | Field `<when>` | 字段级别 |
| 依赖关系 | Field `<dependency>` | 字段级别 |

### 7.3 去重示例

**错误**：CalcType 选择规则重复 3 次
```python
# 位置1: CalcType enum docstring
class CalcType(str, Enum):
    """<rule>ranking->RANK, running total->RUNNING_TOTAL...</rule>"""

# 位置2: Computation.calc_type Field (重复!)
calc_type: CalcType = Field(
    description="<rule>ranking->RANK, running total->RUNNING_TOTAL...</rule>"
)

# 位置3: Step2Validation.calc_type_check Field (重复!)
calc_type_check: ValidationCheck = Field(
    description="<rule>CalcType mapping: ranking->RANK...</rule>"
)
```

**正确**：只在 Enum docstring 出现一次
```python
# 位置1: CalcType enum docstring (唯一位置)
class CalcType(str, Enum):
    """<rule>
    ranking/Top N -> RANK, DENSE_RANK, PERCENTILE
    running total/YTD -> RUNNING_TOTAL
    ...
    </rule>"""

# 位置2: Computation.calc_type Field (不重复规则)
calc_type: CalcType = Field(
    description="<what>Calculation type</what><when>ALWAYS</when>"
)

# 位置3: Step2Validation.calc_type_check Field (不重复规则)
calc_type_check: ValidationCheck = Field(
    description="<what>Check calc_type matches question intent</what><when>ALWAYS</when>"
)
```

### 7.4 语言规范

**必须使用全英文**，不要中英文混杂。

**原因**：
- LLM 对英文理解更准确
- 避免编码问题
- 保持专业性和一致性

**正确**：
```python
class CalcType(str, Enum):
    """<rule>
    ranking/Top N -> RANK, DENSE_RANK, PERCENTILE
    running total/YTD -> RUNNING_TOTAL
    month-over-month growth -> PERCENT_DIFFERENCE
    per customer X -> LOD_FIXED
    </rule>"""
```

**错误**：
```python
class CalcType(str, Enum):
    """<rule>
    排名/Top N → RANK, DENSE_RANK, PERCENTILE
    累计/YTD → RUNNING_TOTAL
    环比增长 → PERCENT_DIFFERENCE
    每个客户的X → LOD_FIXED
    </rule>"""
```

### 7.5 精简原则

**Enum docstring**：只放选择规则，不放示例（示例放在使用该 Enum 的 Class docstring）

```python
# 精简的 Enum docstring
class RankStyle(str, Enum):
    """Ranking style: COMPETITION=1,2,2,4 | DENSE=1,2,2,3 | UNIQUE=1,2,3,4"""
    COMPETITION = "COMPETITION"
    DENSE = "DENSE"
    UNIQUE = "UNIQUE"
```

**Field description**：只放 `<what>` 和 `<when>`，如果 Enum 已有规则则不重复

```python
# 精简的 Field description
rank_style: RankStyle | None = Field(
    default=None,
    description="""<what>Ranking style</what>
<when>calc_type = RANK</when>"""
)
```

---

## 第八部分：设计原则速查

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
| 15 | 信息去重 | 每种信息只在最相关位置出现一次 |
| 16 | 全英文 | 不要中英文混杂 |
| 17 | Enum 规则集中 | 枚举选择规则只在 Enum docstring |

---

## 第九部分：检查清单

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

### 去重检查
- [ ] Enum 选择规则是否只在 Enum docstring 出现一次？
- [ ] Field description 是否避免重复 Enum 的规则？
- [ ] Class docstring 的 anti_patterns 是否与 Field 的 must_not 重复？
- [ ] 同一约束是否在多个位置重复？

### 语言检查
- [ ] 是否全英文？
- [ ] 是否有中英文混杂？

---

## 与原文档的差异

| 方面 | 原文档 | 本文档 |
|------|--------|--------|
| 架构 | 单步 LLM | LLM 组合（Step 1 + Step 2 + Observer） |
| 核心模型 | AnalysisSpec | Step1Output, Step2Output, Computation |
| 计算类型 | type 枚举 | HowType (SIMPLE/COMPLEX) + CalcType |
| 核心抽象 | 无 | partition_by 统一分区 |
| 验证机制 | Pydantic Validator | Step 2 自我验证 + Observer |
| 意图分类 | 无 | IntentType 四分类 |
| 字段描述 | 无限制 | ≤100 tokens |
| 决策树格式 | ASCII 艺术 | 编号列表 |
| 负面约束 | `<anti_patterns>` | `<must_not>` 标签 |
| 信息去重 | 无 | 每种信息只在最相关位置出现一次 |


---

## 第十部分：数据模型编写详细规范（基于实际代码）

本部分基于当前已实现的 `step2.py`、`computations.py`、`enums.py` 总结标签放置规则。

### 10.1 Enum Docstring 规范

**两种格式**：

**格式A - 带 `<rule>` 标签**（需要选择逻辑时）：
```python
class CalcType(str, Enum):
    """Calculation type (Step2 output, platform-agnostic).
    
    <rule>
    Table Calculations:
    - ranking/Top N -> RANK, DENSE_RANK, PERCENTILE
    - running total/YTD -> RUNNING_TOTAL
    - moving average -> MOVING_CALC
    - percent of total -> PERCENT_OF_TOTAL
    - difference/change -> DIFFERENCE
    - growth rate/MoM -> PERCENT_DIFFERENCE
    
    LOD (change aggregation granularity):
    - per customer X/per product Y -> LOD_FIXED
    - add dimension -> LOD_INCLUDE
    - remove dimension -> LOD_EXCLUDE
    </rule>
    """
    RANK = "RANK"
    # ...
```

**格式B - 一行格式**（只解释值含义，无选择逻辑）：
```python
class RankStyle(str, Enum):
    """Ranking style: COMPETITION=1,2,2,4 | DENSE=1,2,2,3 | UNIQUE=1,2,3,4"""
    COMPETITION = "COMPETITION"
    DENSE = "DENSE"
    UNIQUE = "UNIQUE"
```

**选择标准**：
- LLM需要根据输入决定选哪个值 → 用 `<rule>` 标签
- 只是解释每个值的含义 → 用一行格式

### 10.2 Class Docstring 规范

**标签**：
| 标签 | 用途 | 限制 |
|-----|------|------|
| `<fill_order>` | 填写顺序 | 编号列表 |
| `<examples>` | 完整示例 | ≤2 个 |
| `<anti_patterns>` | 常见错误 | ≤3 个，用 X 前缀 |

**示例**：
```python
class Computation(BaseModel):
    """Computation = Target x CalcType x Partition x Params
    
    <fill_order>
    1. target (ALWAYS)
    2. calc_type (ALWAYS)
    3. partition_by (ALWAYS, can be empty)
    4. params (based on calc_type)
    5. alias (optional, recommended for LOD)
    </fill_order>
    
    <examples>
    Ranking: {"target": "Sales", "calc_type": "RANK", "partition_by": ["Month"], "params": {"direction": "DESC"}}
    LOD: {"target": "OrderDate", "calc_type": "LOD_FIXED", "params": {"lod_dimensions": ["CustomerID"], "lod_aggregation": "MIN"}, "alias": "FirstPurchase"}
    </examples>
    
    <anti_patterns>
    X partition_by not subset of where.dimensions
    X calc_type and params mismatch
    </anti_patterns>
    """
```

### 10.3 Field Description 规范

**标签顺序**：
| 标签 | 用途 | 必填 | 位置 |
|-----|------|------|------|
| `<what>` | 字段含义 | ✅ | 第一 |
| `<when>` | 填写条件 | ✅ | 第二 |
| `<rule>` | 决策规则（非Enum相关） | 可选 | 中间 |
| `<dependency>` | 依赖关系 | 条件字段 | 中间 |
| `<must_not>` | 负面约束 | 推荐 | 最后 |

**关键规则**：如果字段类型是带 `<rule>` 的 Enum，Field description **不要重复** Enum 的规则，只需 `<what>` 和 `<when>`。

**示例 - 简单字段（Enum类型）**：
```python
calc_type: CalcType = Field(
    description="""<what>Calculation type</what>
<when>ALWAYS</when>"""
)
```

**示例 - 带依赖的字段**：
```python
lod_dimensions: list[str] | None = Field(
    default=None,
    description="""<what>LOD dimension list</what>
<when>calc_type in [LOD_FIXED, LOD_INCLUDE, LOD_EXCLUDE]</when>
<dependency>Required for LOD types</dependency>"""
)
```

**示例 - 带规则的字段（非Enum相关）**：
```python
is_match: bool = Field(
    description="""<what>Whether inferred matches reference</what>
<when>ALWAYS required</when>
<rule>True if semantically equivalent, False otherwise</rule>
<must_not>Mark as True when values are clearly different</must_not>"""
)
```

### 10.4 完整案例：CalcParams

```python
class CalcParams(BaseModel):
    """Calculation parameters (platform-agnostic).
    
    <fill_order>
    1. lod_dimensions, lod_aggregation (if LOD_*)
    2. direction, rank_style (if RANK/DENSE_RANK/PERCENTILE)
    3. relative_to (if DIFFERENCE/PERCENT_DIFFERENCE)
    4. aggregation, restart_every (if RUNNING_TOTAL)
    5. aggregation, window_previous, window_next, include_current (if MOVING_CALC)
    6. level_of (if PERCENT_OF_TOTAL)
    </fill_order>
    
    <anti_patterns>
    X Fill params not matching calc_type
    X LOD type without lod_dimensions/lod_aggregation
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    # LOD params (first, as LOD is computed before table calcs)
    lod_dimensions: list[str] | None = Field(
        default=None,
        description="""<what>LOD dimension list</what>
<when>calc_type in [LOD_FIXED, LOD_INCLUDE, LOD_EXCLUDE]</when>
<dependency>Required for LOD types</dependency>"""
    )
    
    lod_aggregation: AggregationType | None = Field(
        default=None,
        description="""<what>LOD aggregation function</what>
<when>calc_type in [LOD_FIXED, LOD_INCLUDE, LOD_EXCLUDE]</when>
<dependency>Required for LOD types</dependency>"""
    )
    
    # Ranking params
    direction: SortDirection | None = Field(
        default=None,
        description="""<what>Sort direction for ranking</what>
<when>calc_type in [RANK, DENSE_RANK, PERCENTILE]</when>"""
    )
    
    rank_style: RankStyle | None = Field(
        default=None,
        description="""<what>Ranking style</what>
<when>calc_type = RANK</when>"""
    )
    
    # Difference params
    relative_to: RelativeTo | None = Field(
        default=None,
        description="""<what>Difference reference position</what>
<when>calc_type in [DIFFERENCE, PERCENT_DIFFERENCE]</when>"""
    )
    
    # Running/Moving params
    aggregation: CalcAggregation | None = Field(
        default=None,
        description="""<what>Aggregation for running/moving calc</what>
<when>calc_type in [RUNNING_TOTAL, MOVING_CALC]</when>"""
    )
    
    restart_every: str | None = Field(
        default=None,
        description="""<what>Dimension to restart running calc</what>
<when>calc_type = RUNNING_TOTAL and needs restart (YTD, MTD)</when>"""
    )
    
    window_previous: int | None = Field(
        default=None,
        description="""<what>Number of previous values in window</what>
<when>calc_type = MOVING_CALC</when>"""
    )
    
    window_next: int | None = Field(
        default=None,
        description="""<what>Number of next values in window</what>
<when>calc_type = MOVING_CALC</when>"""
    )
    
    include_current: bool | None = Field(
        default=None,
        description="""<what>Include current value in window</what>
<when>calc_type = MOVING_CALC</when>"""
    )
    
    # Percent params
    level_of: str | None = Field(
        default=None,
        description="""<what>Level for percent calculation</what>
<when>calc_type = PERCENT_OF_TOTAL and needs specific level</when>"""
    )
```

### 10.5 完整案例：Step2Output

```python
class Step2Output(BaseModel):
    """Step 2 output: Computation reasoning + self-validation.
    
    <fill_order>
    1. reasoning (ALWAYS)
    2. computations (ALWAYS, can be multiple)
    3. validation (ALWAYS)
    </fill_order>
    
    <examples>
    Single: {"computations": [{"target": "Sales", "calc_type": "RANK", "partition_by": ["Month"]}]}
    Combination: {"computations": [{"calc_type": "LOD_FIXED", ...}, {"calc_type": "RANK", ...}]}
    </examples>
    
    <anti_patterns>
    X Combination outputs only one Computation
    X LOD after table calc (should be LOD first)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    reasoning: str = Field(
        description="""<what>Inference process</what>
<when>ALWAYS</when>"""
    )
    
    computations: list[Computation] = Field(
        description="""<what>Computation definitions</what>
<when>ALWAYS</when>
<rule>Combination: LOD first, then table calc</rule>"""
    )
    
    validation: Step2Validation = Field(
        description="""<what>Self-validation result</what>
<when>ALWAYS</when>"""
    )
```

### 10.6 去重检查清单

- [ ] Enum 选择规则只在 Enum docstring 的 `<rule>` 中出现一次？
- [ ] Field description 引用 Enum 时不重复 Enum 的规则？
- [ ] Class docstring 的 `<anti_patterns>` 与 Field 的 `<must_not>` 不重复？
- [ ] 全英文，无中英文混杂？
