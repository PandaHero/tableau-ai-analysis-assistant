# 设计附件：Prompt 模板更新

## 概述

本文档详细说明 Understanding Agent 的 Prompt 模板设计，用于输出纯语义的 SemanticQuery。
遵循 `PROMPT_AND_MODEL_GUIDE.md` 的 4 段式结构和职责边界原则。

**重要变更**：
- 移除 Task Planner Agent（由确定性代码组件替代）
- Understanding Agent 输出 SemanticQuery（纯语义，无 VizQL 概念）
- LLM 不再判断 addressing/partitioning/LOD 语法等技术概念
- LLM 只判断语义意图：computation_scope、requires_external_dimension、target_granularity

## 职责边界

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           职责边界原则                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  LLM 职责 (语义理解):                                                        │
│  - 识别用户想要什么指标（measures）                                          │
│  - 识别如何分组/展示（dimensions）                                           │
│  - 识别数据范围限制（filters）                                               │
│  - 识别派生计算类型（analyses）                                              │
│  - 判断语义意图（computation_scope、requires_external_dimension）            │
│                                                                              │
│  代码职责 (技术转换):                                                        │
│  - 字段映射（FieldMapper: RAG + LLM 混合）                                   │
│  - 实现方式判断（ImplementationResolver: 表计算 vs LOD）                     │
│  - addressing 解析（代码规则 + LLM 语义意图）                                │
│  - 表达式生成（ExpressionGenerator: 代码模板）                               │
│                                                                              │
│  LLM 不需要知道:                                                             │
│  - addressing、partitioning、restart_every                                   │
│  - RUNNING_SUM、WINDOW_AVG、RANK 等函数名                                    │
│  - LOD 语法（{FIXED ...}）                                                   │
│  - 技术字段名                                                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 1. Understanding Agent Prompt

### 1.1 4 段式结构

```python
class UnderstandingPrompt(VizQLPrompt):
    """
    问题理解 Prompt - 纯语义中间层版本
    
    输出: SemanticQuery（纯语义，无 VizQL 概念）
    """
    
    def get_role(self) -> str:
        return """You are a semantic analyzer for data analysis questions.
Your job is to understand what the user wants to analyze and express it in pure semantic terms.
You do NOT need to know any technical details like VizQL syntax, addressing, or partitioning."""
    
    def get_task(self) -> str:
        return """Analyze the user's question and output a SemanticQuery that captures:
1. What metrics (measures) the user wants to see
2. How to group/display the data (dimensions)
3. What data range to filter (filters)
4. What derived calculations are needed (analyses)

Output ONLY business terms, NOT technical field names.
The technical field mapping will be done by a separate component."""
    
    def get_domain_knowledge(self) -> str:
        return """
═══════════════════════════════════════════════════════════════════════════════
                           ENTITY CLASSIFICATION
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│                              度量 (Measure)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  WHAT: 需要聚合计算的数值                                                    │
│  KEYWORDS: 销售额, 利润, 数量, 金额, 成本, 收入, 订单数                      │
│  AGGREGATION:                                                                │
│  - sum: "总", "合计", "总计" (默认)                                          │
│  - avg: "平均", "均值", "人均"                                               │
│  - count: "次数", "数量"                                                     │
│  - countd: "多少个", "几种", "不重复"                                        │
│  - min/max: "最小", "最大", "最低", "最高"                                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              维度 (Dimension)                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  WHAT: 用于分组或分类的字段                                                  │
│                                                                              │
│  时间维度 (is_time=true):                                                    │
│  - KEYWORDS: 日期, 时间, 年, 月, 季度, 周                                    │
│  - time_granularity: year, quarter, month, week, day                         │
│  - 识别规则: "按月" → month, "按年" → year, "按季度" → quarter               │
│                                                                              │
│  非时间维度 (is_time=false):                                                 │
│  - KEYWORDS: 省份, 城市, 品类, 产品, 客户, 区域                              │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                           ANALYSIS TYPE DETECTION
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│                         分析类型关键词映射                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┬────────────────────────────────────────────────────┐  │
│  │ type             │ Chinese Triggers                                   │  │
│  ├──────────────────┼────────────────────────────────────────────────────┤  │
│  │ cumulative       │ 累计, 累积, running total, cumulative              │  │
│  │ moving           │ 移动平均, 滚动, rolling, moving average            │  │
│  │ ranking          │ 排名, 排序, rank, ranking, 前N名                   │  │
│  │ percentage       │ 占比, 百分比, percent of total, 比例               │  │
│  │ period_compare   │ 同比, 环比, 增长率, growth rate                    │  │
│  │ difference       │ 差异, 变化量, 与...相比                            │  │
│  │ aggregation_at_level │ 固定粒度, 在...级别, 品类总计                  │  │
│  └──────────────────┴────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                         COMPUTATION SCOPE JUDGMENT
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│                    computation_scope 判断规则                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  WHAT: 计算是在每个分组内独立进行，还是跨所有数据                            │
│  WHEN: 当存在多个维度时需要判断                                              │
│                                                                              │
│  per_group (每个分组独立计算):                                               │
│  - "各省份按月累计" → 每个省份独立累计                                       │
│  - "每个品类的销售额排名" → 每个品类内独立排名                               │
│  - 关键词: "各", "每个", "分别", "独立"                                      │
│                                                                              │
│  across_all (跨所有数据计算):                                                │
│  - "按月累计总销售额" → 所有数据一起累计                                     │
│  - "全部产品销售额排名" → 所有产品一起排名                                   │
│  - 关键词: "总", "全部", "整体", "所有"                                      │
│                                                                              │
│  DEFAULT: 如果问题中有"各XX"、"每个XX"等词，通常是 per_group                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                    REQUIRES_EXTERNAL_DIMENSION JUDGMENT
═══════════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────────┐
│               requires_external_dimension 判断规则                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  WHAT: 计算是否需要访问不在当前查询维度中的字段                              │
│                                                                              │
│  true (需要外部维度):                                                        │
│  - "各省份销售额，及该省客户数" → 需要访问客户维度（不在视图中）             │
│  - "各产品销售额，及其品类总销售额" → 需要访问品类维度                       │
│                                                                              │
│  false (不需要外部维度):                                                     │
│  - "各省份销售额占全国比例" → 全国总计可以用 TOTAL() 实现                    │
│  - "各月累计销售额" → 所有维度都在视图中                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════════
                         STRUCTURED REASONING (5 Steps)
═══════════════════════════════════════════════════════════════════════════════

┌───────────┬─────────────────────┬────────────────────────────────────────────┐
│ Step      │ Purpose             │ Output Format                              │
├───────────┼─────────────────────┼────────────────────────────────────────────┤
│ intent    │ What user wants?    │ analysis: 用户想..., conclusion: 查询类型  │
│ entities  │ What terms?         │ analysis: 识别到..., conclusion: N个实体   │
│ roles     │ How each used?      │ analysis: X表示..., conclusion: X→role     │
│ time      │ Time scope?         │ analysis: 时间..., conclusion: 有/无       │
│ analysis  │ Derived calc?       │ analysis: 检测到..., conclusion: 类型+scope│
└───────────┴─────────────────────┴────────────────────────────────────────────┘
"""
    
    def get_constraints(self) -> str:
        return """MUST:
- Use business terms only (NOT technical field names)
- Detect analysis type keywords: 累计, 排名, 移动平均, 占比, 同比, 环比
- Judge computation_scope when multiple dimensions exist
- Judge requires_external_dimension when aggregation at different level is needed
- Set time_granularity for time dimensions

MUST NOT:
- Use technical field names like [Table].[Field]
- Generate VizQL expressions or function names
- Specify addressing or partitioning (these are VizQL concepts)
- Skip entities mentioned in question"""


## 2. SemanticQuery Schema 设计

### 2.1 Schema 字段说明（遵循 WHAT/WHEN/HOW/VALUES/EXAMPLES 格式）

```python
class SemanticQuery(BaseModel):
    """
    语义查询 - LLM 输出的纯语义模型
    
    设计原则：
    - 完全不包含 VizQL 技术概念
    - 只表达用户意图的语义
    - 每个字段独立决策（正交设计）
    """
    
    measures: List[MeasureSpec] = Field(
        min_length=1,
        description="""度量列表

WHAT: 用户想要查看的数值指标
WHEN: 每个问题至少有一个度量
HOW: 识别问题中的数值概念

EXAMPLES:
- "销售额" → {"name": "销售额", "aggregation": "sum"}
- "平均利润" → {"name": "利润", "aggregation": "avg"}
- "客户数" → {"name": "客户", "aggregation": "countd"}"""
    )
    
    dimensions: List[DimensionSpec] = Field(
        default_factory=list,
        description="""维度列表

WHAT: 用于分组或分类的字段
WHEN: 当问题需要按某个维度分组时
HOW: 识别问题中的分类概念

EXAMPLES:
- "各省份" → {"name": "省份", "is_time": false}
- "按月" → {"name": "日期", "is_time": true, "time_granularity": "month"}"""
    )
    
    filters: List[FilterSpec] = Field(
        default_factory=list,
        description="""筛选列表

WHAT: 数据范围限制
WHEN: 当问题指定了数据范围时
HOW: 识别问题中的限制条件

EXAMPLES:
- "2024年" → {"field": "日期", "filter_type": "time_range", "time_value": "2024"}
- "华东地区" → {"field": "区域", "filter_type": "set", "values": ["华东"]}"""
    )
    
    analyses: List[AnalysisSpec] = Field(
        default_factory=list,
        description="""分析列表（派生计算）

WHAT: 用户想要的派生计算
WHEN: 当问题包含累计、排名、占比等分析需求时
HOW: 识别分析类型关键词

EXAMPLES:
- "累计销售额" → {"type": "cumulative", "target_measure": "销售额"}
- "销售额排名" → {"type": "ranking", "target_measure": "销售额", "order": "desc"}"""
    )
    
    output_control: Optional[OutputControl] = Field(
        None,
        description="""输出控制

WHAT: 结果数量限制
WHEN: 当问题指定了结果数量时
HOW: 识别 TopN 关键词

EXAMPLES:
- "前10名" → {"top_n": 10, "by_measure": "销售额", "order": "desc"}"""
    )


class AnalysisSpec(BaseModel):
    """
    分析规格 - 纯语义，不包含 VizQL 概念
    """
    
    type: AnalysisType = Field(
        description="""分析类型

WHAT: 用户想要的计算类型
HOW: 根据关键词识别

VALUES:
- cumulative: "累计", "累积", "running total"
- moving: "移动平均", "滚动", "rolling"
- ranking: "排名", "rank", "前N名"
- percentage: "占比", "百分比", "比例"
- period_compare: "同比", "环比", "增长率"
- aggregation_at_level: "固定粒度", "在...级别聚合" """
    )
    
    target_measure: str = Field(
        description="""目标度量（业务术语）

WHAT: 分析应用的度量
HOW: 使用业务术语，不是技术字段名

EXAMPLES:
- "累计销售额" → "销售额"
- "利润排名" → "利润" """
    )
    
    computation_scope: Optional[ComputationScope] = Field(
        None,
        description="""计算范围（语义意图）

WHAT: 计算是在每个分组内独立进行，还是跨所有数据
WHEN: 当存在多个维度时需要判断
HOW: 根据问题语义判断

VALUES:
- per_group: "各省份的累计" → 按省份分区，每个省份独立累计
- across_all: "所有数据的累计" → 不分区，所有数据一起累计

EXAMPLES:
- "各省份按月累计销售额" → per_group（每个省份独立累计）
- "按月累计总销售额" → across_all（所有数据一起累计）"""
    )
    
    requires_external_dimension: bool = Field(
        default=False,
        description="""是否需要访问视图外的维度

WHAT: 计算是否需要访问不在当前查询维度中的字段
WHEN: 当需要在不同粒度聚合，或需要访问额外维度时
HOW: 根据问题语义判断

EXAMPLES:
- "各产品销售额，及其品类总销售额" → false（品类可以从产品推导）
- "各省份销售额，及该省客户数" → true（需要访问客户维度）"""
    )
    
    target_granularity: Optional[List[str]] = Field(
        None,
        description="""目标聚合粒度（业务术语）

WHAT: 计算应该在什么粒度进行
WHEN: 当需要在不同于视图的粒度聚合时
HOW: 列出目标粒度的维度

EXAMPLES:
- "各产品销售额，及其品类总销售额" → ["品类"]
- "各省份销售额，及全国总销售额" → []（空列表表示全局）"""
    )
    
    # 其他可选字段...
    order: Optional[Literal["asc", "desc"]] = Field(None)
    window_size: Optional[int] = Field(None, ge=1)
    compare_type: Optional[Literal["yoy", "mom", "wow", "dod", "prev"]] = Field(None)
    along_dimension: Optional[str] = Field(None)
```

## 3. 完整示例

### 3.1 简单累计（单维度）

**用户问题**: "按月累计销售额"

**Understanding Agent 输出 (SemanticQuery)**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [{"name": "日期", "is_time": true, "time_granularity": "month"}],
    "filters": [],
    "analyses": [{"type": "cumulative", "target_measure": "销售额"}]
}
```

**后续处理（代码组件）**:
- FieldMapper: "销售额" → "Sales", "日期" → "Order Date"
- ImplementationResolver: 单维度 → 代码规则 → addressing=["Order Date"]
- ExpressionGenerator: cumulative + sum → "RUNNING_SUM(SUM([Sales]))"

### 3.2 复杂累计（多维度，per_group）

**用户问题**: "各省份按月累计销售额"

**Understanding Agent 输出 (SemanticQuery)**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [
        {"name": "省份", "is_time": false},
        {"name": "日期", "is_time": true, "time_granularity": "month"}
    ],
    "filters": [],
    "analyses": [{
        "type": "cumulative", 
        "target_measure": "销售额",
        "computation_scope": "per_group"
    }]
}
```

**后续处理（代码组件）**:
- FieldMapper: "省份" → "State", "销售额" → "Sales", "日期" → "Order Date"
- ImplementationResolver: 多维度 + per_group → addressing=["Order Date"]（省份作为隐式分区）
- ExpressionGenerator: cumulative + sum → "RUNNING_SUM(SUM([Sales]))"

### 3.3 需要 LOD 的场景

**用户问题**: "各产品销售额，以及该产品所属品类的总销售额"

**Understanding Agent 输出 (SemanticQuery)**:
```json
{
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
```

**后续处理（代码组件）**:
- FieldMapper: "产品" → "Product Name", "销售额" → "Sales", "品类" → "Category"
- ImplementationResolver: target_granularity ≠ 视图维度 → LOD
- ExpressionGenerator: LOD + FIXED → "{FIXED [Category] : SUM([Sales])}"

### 3.4 排名场景

**用户问题**: "各品类销售额排名"

**Understanding Agent 输出 (SemanticQuery)**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [{"name": "品类", "is_time": false}],
    "filters": [],
    "analyses": [{
        "type": "ranking",
        "target_measure": "销售额",
        "order": "desc"
    }]
}
```

**后续处理（代码组件）**:
- FieldMapper: "品类" → "Category", "销售额" → "Sales"
- ImplementationResolver: 单维度 + ranking → addressing=["Category"]
- ExpressionGenerator: ranking + desc → "RANK(SUM([Sales]), 'desc')"

### 3.5 同比增长场景

**用户问题**: "各月销售额同比增长率"

**Understanding Agent 输出 (SemanticQuery)**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [{"name": "日期", "is_time": true, "time_granularity": "month"}],
    "filters": [],
    "analyses": [{
        "type": "period_compare",
        "target_measure": "销售额",
        "compare_type": "yoy"
    }]
}
```

**后续处理（代码组件）**:
- FieldMapper: "销售额" → "Sales", "日期" → "Order Date"
- ImplementationResolver: 单维度 + period_compare → addressing=["Order Date"]
- ExpressionGenerator: yoy_rate → "(SUM([Sales]) - LOOKUP(SUM([Sales]), -12)) / ABS(LOOKUP(SUM([Sales]), -12))"

## 4. 与旧架构的对比

| 方面 | 旧架构 | 新架构（纯语义中间层） |
|------|--------|----------------------|
| LLM 输出 | QuestionUnderstanding + QueryPlan | SemanticQuery（纯语义） |
| 字段映射 | LLM 在 Planning 阶段完成 | FieldMapper（RAG + LLM 混合） |
| 表计算/LOD 判断 | LLM 判断 | ImplementationResolver（代码规则） |
| addressing 判断 | LLM 判断 | ImplementationResolver（代码规则 + LLM 语义意图） |
| 表达式生成 | LLM 生成 | ExpressionGenerator（代码模板） |
| 准确性 | 依赖 LLM 能力 | 100% 确定性（代码生成） |

## 5. Prompt 模块化扩展

### 5.1 Feature Tags（简化版）

```python
class FeatureTag(str, Enum):
    # 分析类型特征
    ANALYSIS_CUMULATIVE = "analysis_cumulative"
    ANALYSIS_MOVING = "analysis_moving"
    ANALYSIS_RANKING = "analysis_ranking"
    ANALYSIS_PERCENTAGE = "analysis_percentage"
    ANALYSIS_PERIOD_COMPARE = "analysis_period_compare"
    ANALYSIS_LOD = "analysis_lod"
    
    # 维度特征
    DIMENSION_TIME = "dimension_time"
    DIMENSION_MULTI = "dimension_multi"
```

### 5.2 检测模式

```python
class FeatureDetector:
    PATTERNS = [
        # 分析类型
        (r"累计|累积|running total|cumulative", FeatureTag.ANALYSIS_CUMULATIVE),
        (r"移动平均|滚动|rolling|moving average", FeatureTag.ANALYSIS_MOVING),
        (r"排名|排序|rank|ranking|前\d+名", FeatureTag.ANALYSIS_RANKING),
        (r"占比|百分比|percent of total|比例", FeatureTag.ANALYSIS_PERCENTAGE),
        (r"同比|环比|增长率|growth rate", FeatureTag.ANALYSIS_PERIOD_COMPARE),
        (r"固定粒度|在.*级别|品类总计|不管", FeatureTag.ANALYSIS_LOD),
        
        # 维度特征
        (r"按月|按年|按季度|按周|按日", FeatureTag.DIMENSION_TIME),
        (r"各.*各|每个.*每个", FeatureTag.DIMENSION_MULTI),
    ]
```

### 5.3 动态 Prompt 组装

```python
class DynamicPromptBuilder:
    """
    动态 Prompt 构建器
    
    根据检测到的特征，动态添加相关的领域知识模块
    """
    
    def build(self, question: str) -> str:
        features = self.detector.detect(question)
        
        prompt_parts = [
            self.base_prompt.get_role(),
            self.base_prompt.get_task(),
        ]
        
        # 动态添加领域知识
        domain_knowledge = self.base_prompt.get_domain_knowledge()
        
        if FeatureTag.ANALYSIS_CUMULATIVE in features:
            domain_knowledge += self._get_cumulative_examples()
        
        if FeatureTag.ANALYSIS_RANKING in features:
            domain_knowledge += self._get_ranking_examples()
        
        if FeatureTag.DIMENSION_MULTI in features:
            domain_knowledge += self._get_multi_dimension_guidance()
        
        prompt_parts.append(domain_knowledge)
        prompt_parts.append(self.base_prompt.get_constraints())
        
        return "\n\n".join(prompt_parts)
```
