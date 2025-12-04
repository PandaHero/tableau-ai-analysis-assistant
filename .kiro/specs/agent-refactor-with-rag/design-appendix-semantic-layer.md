# 设计附件：纯语义中间层架构

## 概述

本文档定义了**纯语义中间层**的完整设计，实现自然语言到 VizQL 查询的 100% 准确转换。

## 核心设计原则

### 设计哲学

**核心原则**：LLM 只做语义理解，所有 VizQL 技术转换由确定性代码完成。

**为什么需要纯语义中间层？**
1. **准确性**：LLM 擅长语义理解，不擅长生成精确的技术语法
2. **可维护性**：VizQL 语法变化时只需修改代码规则，不需要重新训练/调整 LLM
3. **可测试性**：确定性代码可以 100% 覆盖测试，LLM 输出难以保证
4. **正交性**：语义理解和技术实现完全解耦，各自独立演进

### 关键设计决策

| 决策 | 旧方案 | 新方案 | 原因 |
|------|--------|--------|------|
| 字段映射 | LLM 判断 | RAG + LLM 混合 | 高置信度直接用 RAG，低置信度用 LLM 判断 |
| addressing/partitioning | LLM 判断 | 混合策略（简单用代码，复杂用 LLM 语义判断） | 简单场景确定性，复杂场景需要语义理解 |
| restart_every | LLM 填写 | 不需要（隐式分区） | 本质是分区，所有不在 addressing 的维度 |
| 表计算表达式 | LLM 生成 | 代码模板生成 | 确定性生成，100% 正确 |
| LOD 表达式 | LLM 生成 | 代码模板生成 | 确定性生成，100% 正确 |
| along_dimension | LLM 总是填写 | 仅当用户显式指定 | 减少 LLM 决策负担 |
| LOD vs 表计算 | 分开处理 | 语义统一，代码判断实现方式 | 用户不关心技术实现 |

---

## 表计算 vs LOD：何时使用哪个？

### 核心区别

| 特性 | 表计算 (Table Calculation) | LOD (Level of Detail) |
|------|---------------------------|----------------------|
| 计算时机 | 查询结果之后 | 查询执行时（SQL 层面） |
| 数据范围 | 只能访问查询结果中的数据 | 可以访问不在视图中的维度 |
| 聚合粒度 | 受限于查询的维度 | 可以指定任意粒度 |
| 性能 | 客户端计算，数据量大时慢 | 服务端计算，通常更快 |

### 决策规则

```
用户需求
    ↓
是否需要访问视图外的维度？
    ├─ 是 → 必须用 LOD
    └─ 否 → 是否需要不同于视图的聚合粒度？
              ├─ 是 → 优先用 LOD
              └─ 否 → 用表计算
```

### 场景示例

| 场景 | 实现方式 | 原因 |
|------|---------|------|
| "各省份按月累计销售额" | 表计算 | 所有维度都在视图中 |
| "各省份销售额排名" | 表计算 | 所有维度都在视图中 |
| "各省份销售额占比" | 表计算 | TOTAL() 可以实现 |
| "各产品销售额，及其品类总销售额" | LOD | 需要品类级别聚合（比视图粗） |
| "各省份销售额，及该省客户数" | LOD | 需要访问客户维度（不在视图中） |
| "各省份销售额占全国比例" | 表计算 | TOTAL() 可以实现全局聚合 |

---

## 数据流转架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    自然语言 → VizQL 查询转换流程（纯语义中间层）               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  用户问题 (自然语言)                                                          │
│  "2024年各省份销售额按月趋势，显示累计总额"                                    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 1: Understanding Agent (纯语义理解层) - LLM                   │    │
│  │  输入: 用户问题                                                      │    │
│  │  输出: SemanticQuery (纯语义，无 VizQL 概念)                         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 2: FieldMapper (RAG + LLM 混合字段映射)                       │    │
│  │  输入: SemanticQuery 中的业务术语                                    │    │
│  │  输出: 业务术语 → 技术字段名 映射                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 3: ImplementationResolver (实现方式解析器)                    │    │
│  │  输入: AnalysisSpec + 已映射的维度列表                               │    │
│  │  输出: 使用表计算还是 LOD + addressing_dimensions                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 4: ExpressionGenerator (表达式生成器 - 代码模板)              │    │
│  │  输入: AnalysisSpec + implementation_type + addressing + 技术字段名  │    │
│  │  输出: VizQL 表达式                                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 5: QueryBuilder (VizQL 查询组装)                              │    │
│  │  输入: 所有转换结果                                                  │    │
│  │  输出: VizQLQuery                                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 6: QueryValidator (多层验证)                                  │    │
│  │  - Schema 验证、字段存在性验证、表达式语法验证                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  VizQL Data Service API 调用                                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 表计算场景完整覆盖

### 分阶段实现计划

| 阶段 | 分析类型 | 函数 | 优先级 |
|------|---------|------|--------|
| **Phase 1** | cumulative | RUNNING_SUM/AVG/MIN/MAX/COUNT | P0 |
| **Phase 1** | moving | WINDOW_SUM/AVG/MIN/MAX/COUNT | P0 |
| **Phase 1** | ranking | RANK | P0 |
| **Phase 1** | percentage | X / TOTAL(X) | P0 |
| **Phase 1** | period_compare | LOOKUP (同比/环比) | P0 |
| **Phase 2** | difference | DIFFERENCE_FROM | P1 |
| **Phase 2** | percent_difference | PERCENT_DIFFERENCE_FROM | P1 |
| **Phase 2** | ranking_dense | RANK_DENSE | P1 |
| **Phase 2** | ranking_percentile | RANK_PERCENTILE | P1 |
| **Phase 3** | position | FIRST, LAST, INDEX, SIZE | P2 |

---

## Stage 1: SemanticQuery 数据模型

### 设计原则

SemanticQuery 是 LLM 输出的纯语义模型，**完全不包含任何 VizQL 技术概念**：
- 不包含 `addressing`、`partitioning`、`restart_every`
- 不包含 VizQL 函数名（RUNNING_SUM、WINDOW_AVG 等）
- 不包含 LOD 语法（{FIXED ...}）
- 只包含用户意图的语义表达

### 字段决策树与填写顺序

基于 Google Tree of Thoughts 和 Least-to-Most Prompting 研究，使用决策树替代依赖矩阵。

```
<decision_tree>
START
  │
  ├─► type = ? (ALWAYS fill first, determines conditional fields)
  │   │
  │   ├─► cumulative/moving/percentage
  │   │   │
  │   │   └─► dimensions.length > 1 ?
  │   │       ├─ YES → fill computation_scope (default: per_group)
  │   │       └─ NO  → skip computation_scope (null)
  │   │
  │   ├─► ranking
  │   │   ├─► fill order (default: desc)
  │   │   └─► dimensions.length > 1 ?
  │   │       ├─ YES → fill computation_scope
  │   │       └─ NO  → skip computation_scope
  │   │
  │   ├─► moving
  │   │   └─► fill window_size (required)
  │   │
  │   ├─► period_compare
  │   │   └─► fill compare_type (required)
  │   │
  │   └─► aggregation_at_level
  │       ├─► fill requires_external_dimension
  │       └─► fill target_granularity
  │
  ├─► target_measure = ? (ALWAYS fill)
  │
  ├─► aggregation = ? (ALWAYS fill, default: sum)
  │
  └─► along_dimension = ? (ONLY if user explicit)
  
END
</decision_tree>
```

```
<fill_order>
┌────┬─────────────────────────────┬─────────────────────────────────────────┐
│ #  │ Field                       │ Condition                               │
├────┼─────────────────────────────┼─────────────────────────────────────────┤
│ 1  │ type                        │ ALWAYS (determines other fields)        │
│ 2  │ target_measure              │ ALWAYS                                  │
│ 3  │ aggregation                 │ ALWAYS (default: sum)                   │
│ 4  │ order                       │ IF type = ranking                       │
│ 5  │ window_size                 │ IF type = moving                        │
│ 6  │ compare_type                │ IF type = period_compare                │
│ 7  │ requires_external_dimension │ IF type = aggregation_at_level          │
│ 8  │ target_granularity          │ IF type = aggregation_at_level          │
│ 9  │ computation_scope           │ IF dimensions.length > 1                │
│ 10 │ along_dimension             │ IF user explicitly specifies            │
└────┴─────────────────────────────┴─────────────────────────────────────────┘
</fill_order>

IMPORTANT: Fill fields in order. Earlier fields determine later fields.
```

```
<conditional_groups>
Group 1: ALWAYS fill (required fields)
├─ type
├─ target_measure
└─ aggregation (default: sum)

Group 2: type-dependent fields (fill based on type value)
├─ [type=ranking]              → order
├─ [type=moving]               → window_size
├─ [type=period_compare]       → compare_type
└─ [type=aggregation_at_level] → requires_external_dimension, target_granularity

Group 3: context-dependent fields (fill based on query context)
├─ [dimensions.length > 1]     → computation_scope
└─ [user explicit]             → along_dimension
</conditional_groups>
```

### 1.1 AnalysisType 枚举

```python
from enum import Enum

class AnalysisType(str, Enum):
    """
    Analysis type enumeration - pure semantic, no VizQL functions.
    
    Phased implementation:
    - Phase 1 (P0): cumulative, moving, ranking, percentage, period_compare
    - Phase 2 (P1): difference, percent_difference, ranking_dense, ranking_percentile
    - Phase 3 (P2): position
    """
    
    # Phase 1: Core analysis types
    CUMULATIVE = "cumulative"
    MOVING = "moving"
    RANKING = "ranking"
    PERCENTAGE = "percentage"
    PERIOD_COMPARE = "period_compare"
    
    # Phase 2: Extended analysis types
    DIFFERENCE = "difference"
    PERCENT_DIFFERENCE = "percent_difference"
    RANKING_DENSE = "ranking_dense"
    RANKING_PERCENTILE = "ranking_percentile"
    
    # Phase 3: Position functions
    POSITION = "position"
    
    # LOD type (for accessing dimensions outside view)
    AGGREGATION_AT_LEVEL = "aggregation_at_level"
```

### 1.2 ComputationScope 枚举

```python
class ComputationScope(str, Enum):
    """
    Computation scope - LLM judges semantic intent.
    
    WHAT: Whether calculation is per-group or across all data.
    WHEN: Only needed when multiple dimensions exist.
    """
    PER_GROUP = "per_group"      # Calculate independently within each group
    ACROSS_ALL = "across_all"    # Calculate across all data
```


### 1.3 AnalysisSpec 完整定义（符合规范）

```python
class AnalysisSpec(BaseModel):
    """
    Analysis specification - pure semantic, no VizQL concepts.
    
    <what>Derived calculation that user wants to perform</what>
    
    <decision_tree>
    START
      │
      ├─► type = ? (ALWAYS fill first)
      │   │
      │   ├─► cumulative/moving/percentage
      │   │   └─► dimensions.length > 1 ?
      │   │       ├─ YES → fill computation_scope
      │   │       └─ NO  → skip computation_scope
      │   │
      │   ├─► ranking → fill order (default: desc)
      │   ├─► moving → fill window_size
      │   ├─► period_compare → fill compare_type
      │   └─► aggregation_at_level
      │       ├─► fill requires_external_dimension
      │       └─► fill target_granularity
      │
      ├─► target_measure = ? (ALWAYS)
      ├─► aggregation = ? (ALWAYS, default: sum)
      └─► along_dimension = ? (ONLY if user explicit)
    END
    </decision_tree>
    
    <fill_order>
    1. type (determines other fields)
    2. target_measure
    3. aggregation (default: sum)
    4. order (IF type=ranking)
    5. window_size (IF type=moving)
    6. compare_type (IF type=period_compare)
    7. requires_external_dimension (IF type=aggregation_at_level)
    8. target_granularity (IF type=aggregation_at_level)
    9. computation_scope (IF dimensions.length > 1)
    10. along_dimension (IF user explicit)
    </fill_order>
    
    <conditional_groups>
    Group 1: ALWAYS fill
    ├─ type, target_measure, aggregation
    
    Group 2: type-dependent
    ├─ [ranking] → order
    ├─ [moving] → window_size
    ├─ [period_compare] → compare_type
    └─ [aggregation_at_level] → requires_external_dimension, target_granularity
    
    Group 3: context-dependent
    ├─ [dimensions.length > 1] → computation_scope
    └─ [user explicit] → along_dimension
    </conditional_groups>
    
    <examples>
    Example 1 - Simple cumulative (single dimension):
    Input: "按月累计销售额"
    Output: {
        "type": "cumulative",
        "target_measure": "销售额",
        "aggregation": "sum"
    }
    
    Example 2 - Multi-dimension cumulative (per_group):
    Input: "各省份按月累计销售额"
    Output: {
        "type": "cumulative",
        "target_measure": "销售额",
        "aggregation": "sum",
        "computation_scope": "per_group"
    }
    
    Example 3 - Ranking:
    Input: "各品类销售额排名"
    Output: {
        "type": "ranking",
        "target_measure": "销售额",
        "aggregation": "sum",
        "order": "desc"
    }
    
    Example 4 - LOD (different granularity):
    Input: "各产品销售额，及其品类总销售额"
    Output: {
        "type": "aggregation_at_level",
        "target_measure": "销售额",
        "aggregation": "sum",
        "target_granularity": ["品类"],
        "requires_external_dimension": false
    }
    
    Example 5 - LOD (external dimension):
    Input: "各省份销售额，及该省客户数"
    Output: {
        "type": "aggregation_at_level",
        "target_measure": "客户",
        "aggregation": "countd",
        "requires_external_dimension": true
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
    
    ❌ ERROR 3: Confusing percentage with LOD
    Input: "各省份销售额占全国比例"
    Wrong: {"type": "aggregation_at_level", "target_granularity": []}
    Right: {"type": "percentage"}
    
    ❌ ERROR 4: Missing order for ranking
    Input: "销售额排名"
    Wrong: {"type": "ranking"}
    Right: {"type": "ranking", "order": "desc"}
    
    ❌ ERROR 5: Setting requires_external_dimension incorrectly
    Input: "各产品销售额，及其品类总销售额"
    Wrong: {"requires_external_dimension": true}
    Right: {"requires_external_dimension": false}
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    # ═══════════════════════════════════════════════════════════════════════
    # REQUIRED FIELDS (Always fill) - Group 1
    # ═══════════════════════════════════════════════════════════════════════
    
    type: AnalysisType = Field(
        description="""Analysis type.

<what>The type of derived calculation user wants</what>

<when>ALWAYS required (fill first, determines other fields)</when>

<how>Detect from keywords in question</how>

<values>
- cumulative: "累计", "累积", "running total"
- moving: "移动平均", "滚动", "rolling"
- ranking: "排名", "rank", "前N名"
- percentage: "占比", "百分比", "比例"
- period_compare: "同比", "环比", "增长率"
- aggregation_at_level: "固定粒度", "品类总计", "在...级别"
</values>

<examples>
- "累计销售额" → cumulative
- "销售额排名" → ranking
- "各品类销售额占比" → percentage
- "各产品及其品类总销售额" → aggregation_at_level
</examples>"""
    )
    
    target_measure: str = Field(
        description="""Target measure (business term).

<what>The measure to apply analysis on</what>

<when>ALWAYS required</when>

<how>Use business term from question, NOT technical field name</how>

<examples>
- "累计销售额" → "销售额"
- "利润排名" → "利润"
- "客户数" → "客户"
</examples>

<anti_patterns>
❌ Using technical field names: "Sales" instead of "销售额"
</anti_patterns>"""
    )
    
    aggregation: Literal["sum", "avg", "count", "countd", "min", "max"] = Field(
        default="sum",
        description="""Aggregation function.

<what>How to aggregate the target measure</what>

<when>ALWAYS required (default: sum)</when>

<how>Detect from keywords</how>

<values>
- sum: "总", "合计" (DEFAULT)
- avg: "平均", "均值"
- count: "次数"
- countd: "多少个", "几种", "不重复"
- min/max: "最小", "最大"
</values>

<examples>
- "总销售额" → sum
- "平均利润" → avg
- "客户数" → countd
</examples>"""
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # CONDITIONAL FIELDS - Group 2: type-dependent
    # ═══════════════════════════════════════════════════════════════════════
    
    order: Optional[Literal["asc", "desc"]] = Field(
        default=None,
        description="""Sort order.

<what>Ascending or descending order for ranking</what>

<when>ONLY when type=ranking</when>

<how>Default to desc for ranking</how>

<dependency>
- field: type
- condition: type == "ranking"
- if_not_met: must be null
</dependency>

<values>
- desc: "前N名", "最高", "最大" (DEFAULT for ranking)
- asc: "后N名", "最低", "最小"
</values>

<decision_rule>
IF type != ranking THEN null (skip)
IF type == ranking THEN desc (default)
IF "最低" or "后N名" in question THEN asc
</decision_rule>

<examples>
- "销售额排名" → desc (default)
- "销售额最低的前10名" → asc
</examples>"""
    )
    
    window_size: Optional[int] = Field(
        default=None,
        ge=1,
        description="""Window size for moving calculation.

<what>Number of periods in moving window</what>

<when>ONLY when type=moving</when>

<how>Extract number from question</how>

<dependency>
- field: type
- condition: type == "moving"
- if_not_met: must be null
</dependency>

<examples>
- "3个月移动平均" → 3
- "5日滚动求和" → 5
</examples>"""
    )
    
    compare_type: Optional[Literal["yoy", "mom", "wow", "dod", "prev"]] = Field(
        default=None,
        description="""Period comparison type.

<what>Type of period-over-period comparison</what>

<when>ONLY when type=period_compare</when>

<how>Detect from keywords</how>

<dependency>
- field: type
- condition: type == "period_compare"
- if_not_met: must be null
</dependency>

<values>
- yoy: "同比" (Year over Year)
- mom: "环比月" (Month over Month)
- wow: "环比周" (Week over Week)
- dod: "环比日" (Day over Day)
- prev: "与上期对比" (Previous period)
</values>

<examples>
- "同比增长率" → yoy
- "环比变化" → mom
</examples>"""
    )
    
    requires_external_dimension: bool = Field(
        default=False,
        description="""Whether external dimension is needed.

<what>Whether calculation needs dimensions NOT in current query</what>

<when>ONLY when type=aggregation_at_level</when>

<how>Check if target granularity dimensions are in query dimensions</how>

<dependency>
- field: type
- condition: type == "aggregation_at_level"
- if_not_met: false (default)
</dependency>

<decision_rule>
IF type != aggregation_at_level THEN false (default)
IF target dimension can be derived from query dims THEN false
IF target dimension is NOT in query dims THEN true
</decision_rule>

<examples>
- "各产品销售额，及其品类总销售额" → false (Category derived from Product)
- "各省份销售额，及该省客户数" → true (Customer not in query)
</examples>

<anti_patterns>
❌ Setting true when target dimension is derivable from query dimensions
❌ Using this for percentage scenarios (use type=percentage instead)
</anti_patterns>"""
    )
    
    target_granularity: Optional[List[str]] = Field(
        default=None,
        description="""Target aggregation granularity (business terms).

<what>Dimensions to aggregate at (coarser than view granularity)</what>

<when>ONLY when type=aggregation_at_level</when>

<how>List dimension names using business terms (NOT technical field names)</how>

<dependency>
- field: type
- condition: type == "aggregation_at_level"
- if_not_met: must be null
</dependency>

<values>
- List of dimension names (business terms)
- Empty list [] means global aggregation (no dimensions)
</values>

<examples>
- "各产品销售额，及其品类总销售额" → ["品类"]
- "各省份销售额，及全国总销售额" → [] (global)
- "各客户销售额，及该客户所在省份的总销售额" → ["省份"]
</examples>

<anti_patterns>
❌ Using technical field names: ["Category"] instead of ["品类"]
❌ Setting when type != aggregation_at_level
</anti_patterns>"""
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # CONDITIONAL FIELDS - Group 3: context-dependent
    # ═══════════════════════════════════════════════════════════════════════
    
    computation_scope: Optional[ComputationScope] = Field(
        default=None,
        description="""Computation scope (semantic intent).

<what>Whether to calculate per-group or across all data</what>

<when>ONLY when query has MULTIPLE dimensions (len(dimensions) > 1)</when>

<how>Detect from keywords in question</how>

<dependency>
- field: dimensions (from SemanticQuery)
- condition: length > 1
- if_not_met: must be null (single dimension doesn't need scope)
</dependency>

<values>
- per_group: "各XX", "每个XX" → Calculate independently per group
- across_all: "总", "全部" → Calculate across all data
</values>

<decision_rule>
IF dimensions.length == 1 THEN null (don't fill)
IF "各XX" or "每个XX" in question THEN per_group
IF "总" or "全部" or "整体" in question THEN across_all
DEFAULT: per_group
</decision_rule>

<examples>
- "各省份按月累计销售额" → per_group (each province cumulates independently)
- "按月累计总销售额" → across_all (all data cumulates together)
- "按月累计销售额" (single dim) → null (don't fill)
</examples>

<anti_patterns>
❌ Setting computation_scope for single dimension query
❌ Defaulting to across_all without explicit "总" keyword
</anti_patterns>"""
    )
    
    along_dimension: Optional[str] = Field(
        default=None,
        description="""User-specified calculation direction (business term).

<what>Dimension to calculate along</what>

<when>ONLY when user EXPLICITLY specifies direction</when>

<how>Only fill if user explicitly mentions direction</how>

<dependency>
- condition: user explicit mention
- if_not_met: null (code will infer from context)
</dependency>

<examples>
- "按月累计" → "月份" (user explicit)
- "累计销售额" → null (user didn't specify, code infers)
</examples>

<anti_patterns>
❌ Guessing along_dimension when user doesn't specify
❌ Using technical field names
</anti_patterns>"""
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # VALIDATORS (Code-level enforcement)
    # ═══════════════════════════════════════════════════════════════════════
    
    @model_validator(mode='after')
    def validate_dependencies(self) -> 'AnalysisSpec':
        """Validate field dependencies."""
        
        # Rule 1: order only for ranking
        if self.order is not None and self.type != AnalysisType.RANKING:
            raise ValueError("order should only be set when type=ranking")
        
        # Rule 2: window_size only for moving
        if self.window_size is not None and self.type != AnalysisType.MOVING:
            raise ValueError("window_size should only be set when type=moving")
        
        # Rule 3: compare_type only for period_compare
        if self.compare_type is not None and self.type != AnalysisType.PERIOD_COMPARE:
            raise ValueError("compare_type should only be set when type=period_compare")
        
        # Rule 4: target_granularity only for aggregation_at_level
        if self.target_granularity is not None and self.type != AnalysisType.AGGREGATION_AT_LEVEL:
            raise ValueError("target_granularity should only be set when type=aggregation_at_level")
        
        return self
```


### 1.4 SemanticQuery 完整定义（符合规范）

```python
class SemanticQuery(BaseModel):
    """
    Semantic query - LLM output, pure semantic model.
    
    <what>Complete semantic representation of user's data analysis intent</what>
    
    <design_principles>
    1. NO VizQL concepts (addressing, partitioning, RUNNING_SUM, etc.)
    2. Business terms only (NOT technical field names)
    3. Each field independently decidable (orthogonal design)
    4. Semantic intent fields help code determine implementation
    </design_principles>
    
    <fill_order>
    1. measures (ALWAYS, at least one)
    2. dimensions (if grouping needed)
    3. filters (if data scope specified)
    4. analyses (if derived calculations needed)
    5. output_control (if result limit specified)
    </fill_order>
    
    <examples>
    Example 1 - Simple query:
    Input: "各省份的销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "省份", "is_time": false}],
        "filters": [],
        "analyses": []
    }
    
    Example 2 - With time filter:
    Input: "2024年各省份销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "省份", "is_time": false}],
        "filters": [{"field": "日期", "filter_type": "time_range", "time_value": "2024"}],
        "analyses": []
    }
    
    Example 3 - With cumulative analysis:
    Input: "2024年各省份销售额按月趋势，显示累计总额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [
            {"name": "省份", "is_time": false},
            {"name": "日期", "is_time": true, "time_granularity": "month"}
        ],
        "filters": [{"field": "日期", "filter_type": "time_range", "time_value": "2024"}],
        "analyses": [{
            "type": "cumulative",
            "target_measure": "销售额",
            "computation_scope": "per_group"
        }]
    }
    
    Example 4 - With LOD analysis:
    Input: "各产品销售额，以及该产品所属品类的总销售额"
    Output: {
        "measures": [{"name": "销售额", "aggregation": "sum"}],
        "dimensions": [{"name": "产品", "is_time": false}],
        "filters": [],
        "analyses": [{
            "type": "aggregation_at_level",
            "target_measure": "销售额",
            "target_granularity": ["品类"],
            "requires_external_dimension": false
        }]
    }
    </examples>
    
    <anti_patterns>
    ❌ ERROR 1: Using technical field names
    Wrong: {"measures": [{"name": "Sales"}]}
    Right: {"measures": [{"name": "销售额"}]}
    
    ❌ ERROR 2: Missing time dimension for cumulative
    Input: "累计销售额" (no time dimension mentioned)
    Wrong: {"analyses": [{"type": "cumulative"}], "dimensions": []}
    Right: Ask user to specify time dimension, or infer from context
    
    ❌ ERROR 3: Setting computation_scope for single dimension
    Input: "按月累计销售额"
    Wrong: {"computation_scope": "per_group"}
    Right: {} (omit computation_scope, only 1 dimension)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    measures: List[MeasureSpec] = Field(
        min_length=1,
        description="""Measure list.

<what>Numeric metrics user wants to see</what>

<when>ALWAYS required (at least one)</when>

<how>Identify numeric concepts in question, use business terms</how>

<examples>
- "销售额" → [{"name": "销售额", "aggregation": "sum"}]
- "平均利润" → [{"name": "利润", "aggregation": "avg"}]
</examples>

<anti_patterns>
❌ Using technical field names: "Sales" instead of "销售额"
❌ Empty measures list
</anti_patterns>"""
    )
    
    dimensions: List[DimensionSpec] = Field(
        default_factory=list,
        description="""Dimension list.

<what>Fields for grouping or categorizing</what>

<when>When question needs grouping (各XX, 按XX, 每个XX)</when>

<how>Identify categorical concepts, mark time dimensions</how>

<examples>
- "各省份" → [{"name": "省份", "is_time": false}]
- "按月" → [{"name": "日期", "is_time": true, "time_granularity": "month"}]
- "各省份按月" → [{"name": "省份", "is_time": false}, {"name": "日期", "is_time": true, "time_granularity": "month"}]
</examples>"""
    )
    
    filters: List[FilterSpec] = Field(
        default_factory=list,
        description="""Filter list.

<what>Data range restrictions</what>

<when>When question specifies data scope</when>

<how>Identify restriction conditions</how>

<examples>
- "2024年" → [{"field": "日期", "filter_type": "time_range", "time_value": "2024"}]
- "华东地区" → [{"field": "区域", "filter_type": "set", "values": ["华东"]}]
</examples>"""
    )
    
    analyses: List[AnalysisSpec] = Field(
        default_factory=list,
        description="""Analysis list (derived calculations).

<what>Derived calculations user wants</what>

<when>When question contains cumulative, ranking, percentage, etc.</when>

<how>Detect analysis keywords, fill AnalysisSpec according to its decision tree</how>

<examples>
- "累计销售额" → [{"type": "cumulative", "target_measure": "销售额"}]
- "销售额排名" → [{"type": "ranking", "target_measure": "销售额", "order": "desc"}]
</examples>

<anti_patterns>
❌ Setting computation_scope when only 1 dimension
❌ Missing order for ranking type
</anti_patterns>"""
    )
    
    output_control: Optional[OutputControl] = Field(
        default=None,
        description="""Output control.

<what>Result quantity limit</what>

<when>When question specifies result count (前N名, TopN)</when>

<how>Detect TopN keywords</how>

<examples>
- "前10名" → {"top_n": 10, "by_measure": "销售额", "order": "desc"}
</examples>"""
    )
```

---

## Stage 2: FieldMapper (RAG + LLM 混合)

字段映射继续使用现有的 RAG + LLM 混合方案，详见 `requirements.md` 需求 4。

### 映射策略

```python
class FieldMapper:
    """
    Field mapper - RAG + LLM hybrid approach.
    
    Strategy:
    1. High confidence (>0.9): Use RAG result directly
    2. Low confidence (<0.9): RAG candidates + LLM judgment
    """
    
    async def map_field(self, business_term: str, context: str) -> FieldMapping:
        # 1. RAG retrieval
        candidates = await self.semantic_mapper.search(business_term, top_k=5)
        
        # 2. Check confidence
        if candidates[0].score > 0.9:
            return FieldMapping(
                business_term=business_term,
                technical_field=candidates[0].field_name,
                confidence=candidates[0].score,
                source="rag"
            )
        
        # 3. Low confidence, LLM judgment
        result = await self.llm_judge(business_term, candidates, context)
        return FieldMapping(
            business_term=business_term,
            technical_field=result.selected_field,
            confidence=result.confidence,
            source="rag+llm"
        )
```

---

## Stage 3: ImplementationResolver (实现方式解析器)

### 设计原则

**核心思想**：根据语义意图判断使用表计算还是 LOD，以及如何设置 addressing。

**混合策略**：
- 简单场景（单维度）：代码规则
- 复杂场景（多维度）：根据 LLM 的 computation_scope 判断

### 实现代码

```python
class ImplementationType(str, Enum):
    """Implementation type."""
    TABLE_CALC = "table_calc"
    LOD = "lod"


@dataclass
class ResolvedImplementation:
    """Implementation resolution result."""
    implementation_type: ImplementationType
    addressing_dimensions: List[str]
    lod_type: Optional[Literal["FIXED", "INCLUDE", "EXCLUDE"]] = None
    lod_dimensions: Optional[List[str]] = None


class ImplementationResolver:
    """
    Implementation resolver - hybrid strategy.
    
    Responsibilities:
    1. Determine table calc vs LOD
    2. Resolve addressing dimensions
    """
    
    def resolve(
        self,
        analysis: AnalysisSpec,
        dimensions: List[DimensionSpec],
        mapped_dimensions: dict,
        view_dimensions: List[str]
    ) -> ResolvedImplementation:
        """
        Resolve implementation.
        
        Decision logic:
        1. If requires_external_dimension=True → LOD
        2. If target_granularity differs from view → LOD
        3. Otherwise → Table calc
        """
        
        # 1. Check if LOD needed
        if analysis.requires_external_dimension:
            return self._resolve_lod(analysis, mapped_dimensions)
        
        if analysis.target_granularity is not None:
            target_dims = set(analysis.target_granularity)
            view_dims = set(view_dimensions)
            if target_dims != view_dims:
                return self._resolve_lod(analysis, mapped_dimensions)
        
        # 2. Use table calc
        return self._resolve_table_calc(analysis, dimensions, mapped_dimensions)
```

---

## Stage 4: ExpressionGenerator (表达式生成器)

### 设计原则

**核心思想**：VizQL 表达式由代码模板生成，100% 确定性，100% 正确。

### 表达式模板

```python
class ExpressionGenerator:
    """
    Expression generator - deterministic code templates.
    """
    
    TABLE_CALC_TEMPLATES = {
        # Phase 1: Cumulative
        "cumulative_sum": "RUNNING_SUM(SUM([{field}]))",
        "cumulative_avg": "RUNNING_AVG(AVG([{field}]))",
        
        # Phase 1: Moving
        "moving_avg": "WINDOW_AVG(SUM([{field}]), -{prev}, {next})",
        
        # Phase 1: Ranking
        "ranking_desc": "RANK(SUM([{field}]), 'desc')",
        "ranking_asc": "RANK(SUM([{field}]), 'asc')",
        
        # Phase 1: Percentage
        "percentage": "SUM([{field}]) / TOTAL(SUM([{field}]))",
        
        # Phase 1: Period compare
        "yoy_rate": "(SUM([{field}]) - LOOKUP(SUM([{field}]), -12)) / ABS(LOOKUP(SUM([{field}]), -12))",
        "mom_rate": "(SUM([{field}]) - LOOKUP(SUM([{field}]), -1)) / ABS(LOOKUP(SUM([{field}]), -1))",
    }
    
    LOD_TEMPLATES = {
        "fixed": "{{FIXED [{dims}] : {agg}([{field}])}}",
        "fixed_global": "{{FIXED : {agg}([{field}])}}",
    }
```

---

## 总结

### 组件职责

| 组件 | 职责 | 实现方式 |
|------|------|---------|
| Understanding Agent | 语义理解 + 语义意图判断 | LLM |
| FieldMapper | 字段映射 | RAG + LLM 混合 |
| ImplementationResolver | 实现方式解析 + 寻址解析 | 代码规则 + LLM 语义意图 |
| ExpressionGenerator | 表达式生成 | 代码模板 |
| QueryBuilder | 查询组装 | 代码 |
| QueryValidator | 多层验证 | 代码 |

### LLM 需要判断的语义意图

| 字段 | 含义 | 何时需要 | 依赖 |
|------|------|---------|------|
| computation_scope | per_group / across_all | 多维度场景 | dimensions.length > 1 |
| requires_external_dimension | 是否需要视图外维度 | type=aggregation_at_level | type |
| target_granularity | 目标聚合粒度 | type=aggregation_at_level | type |
| along_dimension | 用户显式指定的计算方向 | 用户明确指定时 | (user explicit) |

### 设计原则应用（基于 PROMPT_AND_MODEL_GUIDE.md）

本文档应用了以下前沿研究指导的设计原则：

| 原则 | 应用 | 研究来源 |
|------|------|---------|
| XML 结构化 | 所有字段描述使用 `<what>`, `<when>`, `<how>`, `<dependency>` 等标签 | Anthropic |
| 决策树 | 用 `<decision_tree>` 替代依赖矩阵，表达树状决策路径 | Google Tree of Thoughts |
| 填写顺序 | 用 `<fill_order>` 明确字段填写顺序（先简单后复杂） | Google Least-to-Most |
| 条件分组 | 用 `<conditional_groups>` 按触发条件分组字段 | 认知科学 Chunking |
| 位置敏感 | 关键信息（`<what>`, `<when>`）放开头，示例放结尾 | Lost in the Middle |
| 外部验证 | Pydantic Validator 进行代码级验证（100% 可靠） | Calibration 研究 |
| 选项限制 | 枚举值 ≤ 7 个（如 aggregation 有 6 个选项） | 工作记忆限制 |

### XML 标签快速参考

| 标签 | 用途 | 位置 |
|------|------|------|
| `<what>` | 字段含义 | 开头（高注意力） |
| `<when>` | 填写条件 | 开头（高注意力） |
| `<how>` | 填写方式 | 中间 |
| `<dependency>` | 依赖关系 | 中间 |
| `<values>` | 取值范围 | 中间 |
| `<decision_rule>` | 决策规则 | 中间 |
| `<examples>` | 示例 | 结尾（高注意力） |
| `<anti_patterns>` | 常见错误 | 结尾（高注意力） |

### Class Docstring 标签

| 标签 | 用途 |
|------|------|
| `<decision_tree>` | 决策树（替代依赖矩阵） |
| `<fill_order>` | 填写顺序 |
| `<conditional_groups>` | 条件分组 |
| `<examples>` | 完整输入→输出示例 |
| `<anti_patterns>` | 常见错误模式 |
