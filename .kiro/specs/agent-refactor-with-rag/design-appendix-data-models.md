# 设计附件：数据模型详细定义

## 概述

本文档详细定义了 Agent 重构中涉及的所有数据模型，遵循 `PROMPT_AND_MODEL_GUIDE.md` 编写规范。

**重要**：本文档中的纯语义中间层设计已迁移到 `design-appendix-semantic-layer.md`，请参考该文档获取最新的 SemanticQuery、AnalysisSpec 等数据模型定义。

## 核心设计原则：纯语义中间层

### 设计哲学

**核心原则**：LLM 只做语义理解，所有 VizQL 技术转换由确定性代码完成。

**为什么需要纯语义中间层？**
1. **准确性**：LLM 擅长语义理解，不擅长生成精确的技术语法
2. **可维护性**：VizQL 语法变化时只需修改代码规则，不需要重新训练/调整 LLM
3. **可测试性**：确定性代码可以 100% 覆盖测试，LLM 输出难以保证
4. **正交性**：语义理解和技术实现完全解耦，各自独立演进

### 架构对比

**旧架构（LLM 暴露 VizQL 概念）**：
```
用户问题 → LLM 理解 + 判断 addressing/partitioning → VizQL Query
                    ↑
            LLM 需要理解 VizQL 技术概念（容易出错）
```

**新架构（纯语义中间层）**：
```
用户问题 → LLM 纯语义理解 → SemanticQuery（纯语义）
                                    ↓
                            字段映射（RAG）
                                    ↓
                            寻址解析（代码规则）
                                    ↓
                            表达式生成（代码模板）
                                    ↓
                                VizQL Query
```

### 关键设计决策

| 决策 | 旧方案 | 新方案 | 原因 |
|------|--------|--------|------|
| addressing/partitioning | LLM 判断 | 代码规则推导 | VizQL 技术概念，LLM 不应该知道 |
| restart_every | LLM 填写 | 不需要（隐式分区） | 本质是分区，所有不在 addressing 的维度 |
| 表计算表达式 | LLM 生成 | 代码模板生成 | 确定性生成，100% 正确 |
| LOD 表达式 | LLM 生成 | 代码模板生成 | 确定性生成，100% 正确 |
| along_dimension | LLM 总是填写 | 仅当用户显式指定 | 减少 LLM 决策负担 |

## 数据流转架构（新版）

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
│  │              Understanding Agent (纯语义理解层)                      │    │
│  │  输入: 用户问题                                                      │    │
│  │  输出: SemanticQuery (纯语义，无 VizQL 概念)                         │    │
│  │        - measures: [MeasureSpec...]  (用户想要什么指标)              │    │
│  │        - dimensions: [DimensionSpec...]  (如何分组/展示)             │    │
│  │        - filters: [FilterSpec...]  (数据范围限制)                    │    │
│  │        - analyses: [AnalysisSpec...]  (派生计算)                     │    │
│  │        - output_control: OutputControl  (结果限制)                   │    │
│  │                                                                      │    │
│  │  LLM 不需要知道: addressing, partitioning, restart_every,           │    │
│  │                  RUNNING_SUM, WINDOW_AVG, LOD 语法等                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              FieldMapper (RAG 字段映射)                              │    │
│  │  输入: SemanticQuery 中的业务术语                                    │    │
│  │  输出: 业务术语 → 技术字段名 映射                                    │    │
│  │        "销售额" → "Sales"                                            │    │
│  │        "省份" → "State"                                              │    │
│  │        "月份" → "Order Date" (with date_function=MONTH)              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              AddressingResolver (寻址解析器 - 代码规则)              │    │
│  │  输入: AnalysisSpec + 已映射的维度列表                               │    │
│  │  输出: addressing_dimensions (计算方向)                              │    │
│  │                                                                      │    │
│  │  规则（确定性代码）:                                                  │    │
│  │  - 累计/移动计算 → 沿时间维度（最细粒度）                            │    │
│  │  - 排名 → 沿非时间维度（最细粒度）                                   │    │
│  │  - 占比 → 沿非时间维度                                               │    │
│  │  - 同比/环比 → 沿时间维度                                            │    │
│  │                                                                      │    │
│  │  分区 = 所有维度 - addressing（隐式，不需要显式指定）                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              ExpressionGenerator (表达式生成器 - 代码模板)           │    │
│  │  输入: AnalysisSpec + addressing_dimensions + 技术字段名             │    │
│  │  输出: VizQL 表达式                                                  │    │
│  │                                                                      │    │
│  │  模板（确定性代码）:                                                  │    │
│  │  - cumulative + SUM → "RUNNING_SUM(SUM([{field}]))"                  │    │
│  │  - ranking + desc → "RANK(SUM([{field}]), 'desc')"                   │    │
│  │  - percentage → "SUM([{field}]) / TOTAL(SUM([{field}]))"             │    │
│  │  - moving_avg + window=3 → "WINDOW_AVG(SUM([{field}]), -2, 0)"       │    │
│  │  - period_compare + yoy → "(SUM([{f}]) - LOOKUP(SUM([{f}]), -12))    │    │
│  │                            / ABS(LOOKUP(SUM([{f}]), -12))"           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │              QueryBuilder (VizQL 查询组装)                           │    │
│  │  输入: 所有转换结果                                                  │    │
│  │  输出: VizQLQuery                                                    │    │
│  │        - fields: [DimensionField, MeasureField, TableCalcField...]   │    │
│  │        - filters: [SetFilter, QuantitativeFilter...]                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  VizQL Data Service API 调用                                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```



## 第一层：语义理解层 (Understanding Agent 输出)

### 1.1 AdvancedAnalyticsRequirement (新增)

```python
class AdvancedAnalyticsType(str, Enum):
    """高级分析类型"""
    TABLE_CALC = "table_calc"      # 表计算
    LOD = "lod"                    # LOD 计算
    NONE = "none"                  # 无高级分析


class TableCalcRequirement(BaseModel):
    """
    表计算需求 - 语义层识别
    
    WHAT: 用户问题中识别出的表计算需求
    WHEN: 当用户问题包含累计、排名、移动平均、占比等关键词时
    HOW: 提取表计算类型和相关字段
    
    EXAMPLES:
    - "累计销售额" → {calc_type: "RUNNING_TOTAL", target_measure: "销售额"}
    - "销售额排名" → {calc_type: "RANK", target_measure: "销售额"}
    - "3个月移动平均" → {calc_type: "MOVING_CALCULATION", target_measure: null, window_size: 3}
    - "各省份销售额占比" → {calc_type: "PERCENT_OF_TOTAL", target_measure: "销售额"}
    """
    model_config = ConfigDict(extra="forbid")
    
    calc_type: Literal[
        "RUNNING_TOTAL",      # 累计: "累计", "running total", "cumulative"
        "MOVING_CALCULATION", # 移动计算: "移动平均", "moving average", "rolling"
        "RANK",               # 排名: "排名", "rank", "ranking"
        "PERCENT_OF_TOTAL",   # 占比: "占比", "百分比", "percent of total"
        "DIFFERENCE_FROM",    # 差异: "差异", "difference", "变化"
        "PERCENT_DIFFERENCE_FROM",  # 百分比差异: "增长率", "growth rate"
        "CUSTOM"              # 自定义: 其他复杂计算
    ] = Field(
        description="""表计算类型

WHAT: 识别出的表计算类型
HOW: 根据关键词映射

VALUES:
- RUNNING_TOTAL: "累计", "running total", "cumulative"
- MOVING_CALCULATION: "移动平均", "moving average", "rolling", "滚动"
- RANK: "排名", "rank", "ranking", "前N"
- PERCENT_OF_TOTAL: "占比", "百分比", "percent of total", "percentage"
- DIFFERENCE_FROM: "差异", "difference", "变化"
- PERCENT_DIFFERENCE_FROM: "增长率", "growth rate", "同比", "环比"
- CUSTOM: 其他复杂计算"""
    )
    
    target_measure: Optional[str] = Field(
        None,
        description="""目标度量字段（业务术语）

WHAT: 表计算应用的度量字段
WHEN: 当表计算针对特定度量时
HOW: 使用业务术语，不是技术字段名

EXAMPLES:
- "累计销售额" → "销售额"
- "利润排名" → "利润" """
    )
    
    partition_dimensions: List[str] = Field(
        default_factory=list,
        description="""分区维度（业务术语）

WHAT: 表计算的分区字段
WHEN: 当需要按维度分组计算时
HOW: 从问题中提取分组维度

EXAMPLES:
- "各省份的累计销售额" → ["省份"]
- "按品类和月份的排名" → ["品类", "月份"] """
    )
    
    addressing_dimensions: List[str] = Field(
        default_factory=list,
        description="""寻址维度（业务术语）

WHAT: 表计算的计算方向
WHEN: 当需要指定计算顺序时
HOW: 通常是时间维度或排序维度

EXAMPLES:
- "按月累计" → ["月份"]
- "按日期排名" → ["日期"] """
    )
    
    window_size: Optional[int] = Field(
        None,
        ge=1,
        description="""窗口大小

WHAT: 移动计算的窗口大小
WHEN: 仅用于 MOVING_CALCULATION 类型
HOW: 从问题中提取数字

EXAMPLES:
- "3个月移动平均" → 3
- "5日滚动求和" → 5"""
    )


class LODRequirement(BaseModel):
    """
    LOD 计算需求 - 语义层识别
    
    WHAT: 用户问题中识别出的 LOD (Level of Detail) 计算需求
    WHEN: 当用户问题需要在不同粒度级别计算时
    HOW: 识别 LOD 类型和相关维度
    
    EXAMPLES:
    - "每个客户的总销售额（忽略产品维度）" → {lod_type: "FIXED", dimensions: ["客户"]}
    - "包含产品的客户数" → {lod_type: "INCLUDE", dimensions: ["产品"]}
    - "排除地区的平均利润" → {lod_type: "EXCLUDE", dimensions: ["地区"]}
    """
    model_config = ConfigDict(extra="forbid")
    
    lod_type: Literal["FIXED", "INCLUDE", "EXCLUDE"] = Field(
        description="""LOD 类型

WHAT: LOD 表达式类型
HOW: 根据语义判断

VALUES:
- FIXED: 固定粒度，忽略视图维度
  关键词: "固定", "总计", "全局", "忽略其他维度"
- INCLUDE: 包含额外维度，更细粒度
  关键词: "包含", "细分到", "按...细分"
- EXCLUDE: 排除维度，更粗粒度
  关键词: "排除", "不考虑", "忽略" """
    )
    
    dimensions: List[str] = Field(
        description="""LOD 维度（业务术语）

WHAT: LOD 计算涉及的维度
HOW: 使用业务术语

EXAMPLES:
- FIXED [客户] → ["客户"]
- INCLUDE [产品] → ["产品"]
- EXCLUDE [地区] → ["地区"] """
    )
    
    target_measure: str = Field(
        description="""目标度量（业务术语）

WHAT: LOD 计算的度量字段
HOW: 使用业务术语

EXAMPLES:
- "客户总销售额" → "销售额"
- "产品平均利润" → "利润" """
    )
    
    aggregation: Literal["SUM", "AVG", "COUNT", "COUNTD", "MIN", "MAX"] = Field(
        default="SUM",
        description="""聚合函数

WHAT: LOD 表达式中的聚合函数
HOW: 根据问题语义判断

VALUES:
- SUM: "总", "合计" (默认)
- AVG: "平均", "均值"
- COUNT: "次数"
- COUNTD: "多少", "几个"
- MIN/MAX: "最小", "最大" """
    )


class AdvancedAnalyticsRequirement(BaseModel):
    """
    高级分析需求 - 语义层汇总
    
    WHAT: 汇总用户问题中的所有高级分析需求
    WHEN: 当问题包含表计算或 LOD 需求时
    HOW: 分别识别表计算和 LOD 需求
    
    EXAMPLES:
    
    Input: "2024年各省份销售额按月趋势，显示累计总额"
    Output: {
        "has_table_calc": true,
        "table_calc_requirements": [{
            "calc_type": "RUNNING_TOTAL",
            "target_measure": "销售额",
            "addressing_dimensions": ["月份"]
        }],
        "has_lod": false,
        "lod_requirements": []
    }
    
    Input: "每个客户的总销售额（固定粒度）"
    Output: {
        "has_table_calc": false,
        "table_calc_requirements": [],
        "has_lod": true,
        "lod_requirements": [{
            "lod_type": "FIXED",
            "dimensions": ["客户"],
            "target_measure": "销售额",
            "aggregation": "SUM"
        }]
    }
    """
    model_config = ConfigDict(extra="forbid")
    
    has_table_calc: bool = Field(
        default=False,
        description="是否包含表计算需求"
    )
    
    table_calc_requirements: List[TableCalcRequirement] = Field(
        default_factory=list,
        description="表计算需求列表"
    )
    
    has_lod: bool = Field(
        default=False,
        description="是否包含 LOD 需求"
    )
    
    lod_requirements: List[LODRequirement] = Field(
        default_factory=list,
        description="LOD 需求列表"
    )
```



### 1.2 QuestionUnderstanding 更新

```python
class QuestionUnderstanding(BaseModel):
    """
    问题理解结果 - 更新版本
    
    新增字段:
    - advanced_analytics: 高级分析需求（表计算、LOD）
    
    EXAMPLES:
    
    Input: "2024年各省份销售额按月趋势，显示累计总额和排名"
    Output: {
        "question": "2024年各省份销售额按月趋势，显示累计总额和排名",
        "is_valid": true,
        "reasoning": [...],
        "entities": [
            {"name": "省份", "type": "dimension", "role": "group_by"},
            {"name": "销售额", "type": "measure", "role": "aggregate", "aggregation": "SUM"},
            {"name": "日期", "type": "dimension", "role": "group_by", "date_function": "MONTH"}
        ],
        "time_range": {"type": "absolute", "value": "2024", "filter_field": "日期"},
        "advanced_analytics": {
            "has_table_calc": true,
            "table_calc_requirements": [
                {
                    "calc_type": "RUNNING_TOTAL",
                    "target_measure": "销售额",
                    "addressing_dimensions": ["日期"]
                },
                {
                    "calc_type": "RANK",
                    "target_measure": "销售额",
                    "partition_dimensions": ["日期"]
                }
            ],
            "has_lod": false,
            "lod_requirements": []
        },
        "question_types": ["趋势", "多维分解"],
        "complexity": "Complex"
    }
    """
    model_config = ConfigDict(extra="forbid")
    
    # ... 现有字段保持不变 ...
    
    # 新增字段
    advanced_analytics: Optional[AdvancedAnalyticsRequirement] = Field(
        None,
        description="""高级分析需求

WHAT: 表计算和 LOD 计算需求
WHEN: 当问题包含累计、排名、移动平均、LOD 等需求时
HOW: 识别关键词并提取相关信息

EXAMPLES:
- "累计销售额" → has_table_calc=true, calc_type=RUNNING_TOTAL
- "销售额排名" → has_table_calc=true, calc_type=RANK
- "固定粒度的客户总额" → has_lod=true, lod_type=FIXED"""
    )
```

## 第二层：Intent 中间层 (Task Planner Agent 输出)

### 2.1 LODIntent (新增)

```python
class LODIntent(BaseModel):
    """
    LOD 计算意图 - Intent 中间层
    
    WHAT: 将语义层的 LODRequirement 转换为技术层的 LOD 意图
    WHEN: 当 QuestionUnderstanding 包含 LOD 需求时
    HOW: 映射业务术语到技术字段，生成 LOD 表达式
    
    EXAMPLES:
    
    Input (LODRequirement):
    {
        "lod_type": "FIXED",
        "dimensions": ["客户"],
        "target_measure": "销售额",
        "aggregation": "SUM"
    }
    
    Output (LODIntent):
    {
        "business_term": "客户总销售额",
        "lod_type": "FIXED",
        "lod_dimensions": [{"business_term": "客户", "technical_field": "Customer Name"}],
        "target_measure": {"business_term": "销售额", "technical_field": "Sales"},
        "aggregation": "SUM",
        "calculation_expression": "{FIXED [Customer Name] : SUM([Sales])}"
    }
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""业务术语

WHAT: LOD 计算的业务名称
HOW: 组合 LOD 类型和目标度量

EXAMPLES:
- "客户总销售额"
- "产品平均利润" """
    )
    
    lod_type: Literal["FIXED", "INCLUDE", "EXCLUDE"] = Field(
        description="""LOD 类型

WHAT: LOD 表达式类型
HOW: 从 LODRequirement 传递

VALUES:
- FIXED: {FIXED [dim] : AGG([measure])}
- INCLUDE: {INCLUDE [dim] : AGG([measure])}
- EXCLUDE: {EXCLUDE [dim] : AGG([measure])}"""
    )
    
    lod_dimensions: List[Dict[str, str]] = Field(
        description="""LOD 维度映射

WHAT: LOD 维度的业务术语到技术字段映射
HOW: 每个维度包含 business_term 和 technical_field

EXAMPLES:
- [{"business_term": "客户", "technical_field": "Customer Name"}]
- [{"business_term": "产品", "technical_field": "Product Name"}]"""
    )
    
    target_measure: Dict[str, str] = Field(
        description="""目标度量映射

WHAT: 目标度量的业务术语到技术字段映射
HOW: 包含 business_term 和 technical_field

EXAMPLES:
- {"business_term": "销售额", "technical_field": "Sales"}"""
    )
    
    aggregation: Literal["SUM", "AVG", "COUNT", "COUNTD", "MIN", "MAX"] = Field(
        description="""聚合函数

WHAT: LOD 表达式中的聚合函数
HOW: 从 LODRequirement 传递"""
    )
    
    calculation_expression: str = Field(
        description="""LOD 计算表达式

WHAT: 完整的 LOD 表达式字符串
HOW: 根据 lod_type、dimensions、measure、aggregation 生成

EXAMPLES:
- "{FIXED [Customer Name] : SUM([Sales])}"
- "{INCLUDE [Product Name] : COUNTD([Customer ID])}"
- "{EXCLUDE [Region] : AVG([Profit])}" """
    )
    
    sort_direction: Optional[Literal["ASC", "DESC"]] = Field(
        None,
        description="排序方向"
    )
    
    sort_priority: Optional[int] = Field(
        None,
        ge=0,
        description="排序优先级"
    )
```

### 2.2 TableCalcIntent 更新

```python
class TableCalcIntent(BaseModel):
    """
    表计算意图 - Intent 中间层（更新版本）
    
    更新内容:
    - 添加 calculation_expression 字段用于 CUSTOM 类型
    - 完善 table_calc_config 的结构定义
    
    EXAMPLES:
    
    Input (TableCalcRequirement):
    {
        "calc_type": "RUNNING_TOTAL",
        "target_measure": "销售额",
        "addressing_dimensions": ["月份"]
    }
    
    Output (TableCalcIntent):
    {
        "business_term": "累计销售额",
        "technical_field": "Sales",
        "table_calc_type": "RUNNING_TOTAL",
        "table_calc_config": {
            "aggregation": "SUM",
            "dimensions": [{"fieldCaption": "Order Date"}]
        }
    }
    
    CUSTOM 类型示例:
    {
        "business_term": "同比增长率",
        "technical_field": "Sales",
        "table_calc_type": "CUSTOM",
        "calculation_expression": "(SUM([Sales]) - LOOKUP(SUM([Sales]), -12)) / ABS(LOOKUP(SUM([Sales]), -12))",
        "table_calc_config": {
            "dimensions": [{"fieldCaption": "Order Date"}]
        }
    }
    """
    model_config = ConfigDict(extra="forbid")
    
    # ... 现有字段保持不变 ...
    
    # 新增字段
    calculation_expression: Optional[str] = Field(
        None,
        description="""自定义计算表达式

WHAT: CUSTOM 类型的计算表达式
WHEN: 仅用于 table_calc_type="CUSTOM"
HOW: 使用 Tableau 表计算函数语法

EXAMPLES:
- "RUNNING_SUM(SUM([Sales]))"
- "RANK(SUM([Sales]), 'desc')"
- "(SUM([Sales]) - LOOKUP(SUM([Sales]), -1)) / ABS(LOOKUP(SUM([Sales]), -1))"

SUPPORTED FUNCTIONS:
- 位置函数: FIRST(), LAST(), INDEX(), SIZE()
- 查找函数: LOOKUP(expr, offset), PREVIOUS_VALUE(expr)
- 累计函数: RUNNING_SUM, RUNNING_AVG, RUNNING_MIN, RUNNING_MAX, RUNNING_COUNT
- 窗口函数: WINDOW_SUM, WINDOW_AVG, WINDOW_MIN, WINDOW_MAX, WINDOW_COUNT
- 排名函数: RANK, RANK_DENSE, RANK_MODIFIED, RANK_UNIQUE, RANK_PERCENTILE
- 总计函数: TOTAL(expr)"""
    )
```



### 2.3 QuerySubTask 更新

```python
class QuerySubTask(SubTaskBase):
    """
    VizQL 查询任务 - 更新版本
    
    新增字段:
    - lod_intents: LOD 计算意图列表
    
    EXAMPLES:
    
    包含 LOD 的查询:
    {
        "task_type": "query",
        "question_id": "q1",
        "question_text": "各省份销售额和客户总销售额",
        "stage": 1,
        "depends_on": [],
        "rationale": "需要同时显示省份销售额和固定粒度的客户总销售额",
        "dimension_intents": [
            {"business_term": "省份", "technical_field": "State", ...}
        ],
        "measure_intents": [
            {"business_term": "销售额", "technical_field": "Sales", "aggregation": "SUM", ...}
        ],
        "lod_intents": [
            {
                "business_term": "客户总销售额",
                "lod_type": "FIXED",
                "lod_dimensions": [{"business_term": "客户", "technical_field": "Customer Name"}],
                "target_measure": {"business_term": "销售额", "technical_field": "Sales"},
                "aggregation": "SUM",
                "calculation_expression": "{FIXED [Customer Name] : SUM([Sales])}"
            }
        ]
    }
    """
    task_type: Literal["query"] = "query"
    
    # ... 现有字段保持不变 ...
    
    # 新增字段
    lod_intents: List[LODIntent] = Field(
        default_factory=list,
        description="""LOD 计算意图列表

WHAT: LOD 计算的意图列表
WHEN: 当 QuestionUnderstanding 包含 LOD 需求时
HOW: 将 LODRequirement 转换为 LODIntent

EXAMPLES:
- FIXED: 固定粒度计算
- INCLUDE: 包含额外维度
- EXCLUDE: 排除维度"""
    )
```

## 第三层：VizQL 执行层 (QueryBuilder 输出)

### 3.1 CalculatedField (LOD 支持)

```python
class CalculatedField(BaseModel):
    """
    计算字段 - 支持 LOD 表达式
    
    WHAT: VizQL API 的计算字段，支持 LOD 表达式
    HOW: 使用 calculation 属性存储 LOD 表达式
    
    EXAMPLES:
    
    LOD FIXED:
    {
        "fieldCaption": "customer_total_sales",
        "calculation": "{FIXED [Customer Name] : SUM([Sales])}"
    }
    
    LOD INCLUDE:
    {
        "fieldCaption": "product_customer_count",
        "calculation": "{INCLUDE [Product Name] : COUNTD([Customer ID])}"
    }
    
    LOD EXCLUDE:
    {
        "fieldCaption": "region_excluded_avg_profit",
        "calculation": "{EXCLUDE [Region] : AVG([Profit])}"
    }
    
    COUNTD (非 LOD):
    {
        "fieldCaption": "unique_customers",
        "calculation": "COUNTD([Customer ID])"
    }
    """
    fieldCaption: str = Field(
        description="字段名称"
    )
    
    calculation: str = Field(
        description="""计算表达式

WHAT: Tableau 计算表达式
HOW: 支持聚合函数和 LOD 表达式

SUPPORTED:
- 聚合函数: SUM, AVG, COUNT, COUNTD, MIN, MAX, MEDIAN, STDEV, VAR
- LOD 表达式: {FIXED [dim] : AGG([measure])}, {INCLUDE ...}, {EXCLUDE ...}

EXAMPLES:
- "COUNTD([Customer ID])"
- "{FIXED [Category] : SUM([Sales])}"
- "{INCLUDE [Product] : COUNTD([Customer])}" """
    )
    
    fieldAlias: Optional[str] = Field(
        None,
        description="字段别名"
    )
    
    sortDirection: Optional[SortDirection] = Field(
        None,
        description="排序方向"
    )
    
    sortPriority: Optional[int] = Field(
        None,
        description="排序优先级"
    )
```

## Intent → VizQL 转换规则

### 4.1 LODIntent → CalculatedField

```python
def convert_lod_intent(intent: LODIntent) -> CalculatedField:
    """
    将 LODIntent 转换为 CalculatedField
    
    转换规则:
    1. fieldCaption: 使用 business_term 或生成唯一名称
    2. calculation: 使用 calculation_expression
    
    Args:
        intent: LODIntent 对象
    
    Returns:
        CalculatedField 对象
    
    Examples:
        >>> intent = LODIntent(
        ...     business_term="客户总销售额",
        ...     lod_type="FIXED",
        ...     calculation_expression="{FIXED [Customer Name] : SUM([Sales])}"
        ... )
        >>> field = convert_lod_intent(intent)
        >>> field.fieldCaption
        "客户总销售额"
        >>> field.calculation
        "{FIXED [Customer Name] : SUM([Sales])}"
    """
    return CalculatedField(
        fieldCaption=intent.business_term,
        calculation=intent.calculation_expression,
        sortDirection=SortDirection[intent.sort_direction] if intent.sort_direction else None,
        sortPriority=intent.sort_priority
    )
```

### 4.2 TableCalcIntent → TableCalcField

```python
def convert_table_calc_intent(intent: TableCalcIntent) -> TableCalcField:
    """
    将 TableCalcIntent 转换为 TableCalcField
    
    转换规则:
    1. 根据 table_calc_type 选择对应的 TableCalcSpecification
    2. 如果是 CUSTOM 类型，使用 calculation_expression
    3. 构建 dimensions 列表
    
    Args:
        intent: TableCalcIntent 对象
    
    Returns:
        TableCalcField 对象
    
    Examples:
        >>> # RUNNING_TOTAL 示例
        >>> intent = TableCalcIntent(
        ...     business_term="累计销售额",
        ...     technical_field="Sales",
        ...     table_calc_type="RUNNING_TOTAL",
        ...     table_calc_config={
        ...         "aggregation": "SUM",
        ...         "dimensions": [{"fieldCaption": "Order Date"}]
        ...     }
        ... )
        >>> field = convert_table_calc_intent(intent)
        
        >>> # CUSTOM 示例
        >>> intent = TableCalcIntent(
        ...     business_term="同比增长率",
        ...     technical_field="Sales",
        ...     table_calc_type="CUSTOM",
        ...     calculation_expression="(SUM([Sales]) - LOOKUP(SUM([Sales]), -12)) / ABS(LOOKUP(SUM([Sales]), -12))",
        ...     table_calc_config={
        ...         "dimensions": [{"fieldCaption": "Order Date"}]
        ...     }
        ... )
        >>> field = convert_table_calc_intent(intent)
        >>> field.calculation
        "(SUM([Sales]) - LOOKUP(SUM([Sales]), -12)) / ABS(LOOKUP(SUM([Sales]), -12))"
    """
    # 构建 dimensions
    dimensions = [
        TableCalcFieldReference(fieldCaption=dim["fieldCaption"])
        for dim in intent.table_calc_config.get("dimensions", [])
    ]
    
    # 根据类型构建 specification
    if intent.table_calc_type == "CUSTOM":
        spec = CustomTableCalcSpecification(
            tableCalcType="CUSTOM",
            dimensions=dimensions
        )
        return TableCalcField(
            fieldCaption=intent.business_term,
            calculation=intent.calculation_expression,
            tableCalculation=spec,
            sortDirection=SortDirection[intent.sort_direction] if intent.sort_direction else None,
            sortPriority=intent.sort_priority
        )
    
    # 其他类型的转换逻辑...
    # (参见现有的 QueryBuilder.build_table_calc_field 实现)
```

## 模型验证规则

### 5.1 QuestionUnderstanding 验证

```python
@model_validator(mode='after')
def validate_advanced_analytics(self) -> 'QuestionUnderstanding':
    """验证高级分析需求的一致性"""
    if self.advanced_analytics:
        # 验证表计算需求
        for tc in self.advanced_analytics.table_calc_requirements:
            # 目标度量必须在 entities 中
            if tc.target_measure:
                measure_names = [e.name for e in self.entities if e.type == EntityType.MEASURE]
                if tc.target_measure not in measure_names:
                    raise ValueError(
                        f"表计算目标度量 '{tc.target_measure}' 不在 entities 中"
                    )
        
        # 验证 LOD 需求
        for lod in self.advanced_analytics.lod_requirements:
            # LOD 维度必须在 entities 中或是新维度
            # (LOD 可以引用不在视图中的维度)
            pass
    
    return self
```

### 5.2 LODIntent 验证

```python
@model_validator(mode='after')
def validate_lod_expression(self) -> 'LODIntent':
    """验证 LOD 表达式的正确性"""
    # 验证 calculation_expression 格式
    expr = self.calculation_expression
    
    # 检查 LOD 类型匹配
    if self.lod_type == "FIXED" and not expr.startswith("{FIXED"):
        raise ValueError("FIXED 类型的表达式必须以 {FIXED 开头")
    if self.lod_type == "INCLUDE" and not expr.startswith("{INCLUDE"):
        raise ValueError("INCLUDE 类型的表达式必须以 {INCLUDE 开头")
    if self.lod_type == "EXCLUDE" and not expr.startswith("{EXCLUDE"):
        raise ValueError("EXCLUDE 类型的表达式必须以 {EXCLUDE 开头")
    
    # 检查维度和度量是否在表达式中
    for dim in self.lod_dimensions:
        if dim["technical_field"] not in expr:
            raise ValueError(
                f"维度 '{dim['technical_field']}' 不在表达式中"
            )
    
    if self.target_measure["technical_field"] not in expr:
        raise ValueError(
            f"度量 '{self.target_measure['technical_field']}' 不在表达式中"
        )
    
    return self
```

