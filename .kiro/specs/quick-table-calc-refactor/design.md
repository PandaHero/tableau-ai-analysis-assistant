# 设计文档：快速表计算重构

## 概述

本设计文档描述将语义解析器中的表计算逻辑从自定义表计算重构为快速表计算的技术方案。核心目标是：
1. 简化枚举映射，消除多层转换
2. 结构化计算参数，替代 `params: dict`
3. 保持平台无关性，支持未来接入其他 BI
4. 按 Agent 划分 models 目录结构

## 编码规范

### 1. 不使用向后兼容

- 直接删除旧代码，不保留废弃的类/函数
- 不使用 `@deprecated` 装饰器
- 不保留旧的枚举值或字段

### 2. 禁止使用 Any 类型

- 所有字段必须有明确的类型注解
- 不使用 `Any`、`dict`（无类型参数）、`list`（无类型参数）
- 正确示例：`params: CalcParams`
- 错误示例：`params: dict`、`params: Any`

### 3. 禁止使用类型检查延迟注入

- 不使用 `TYPE_CHECKING` 导入
- 不使用字符串类型注解（如 `"Computation"`）
- 直接解决循环依赖问题：
  - 方案1：合并到同一文件
  - 方案2：提取公共基类到独立文件
  - 方案3：重新设计模块边界

## 数据模型与 Prompt 模板的职责划分

### 数据模型（Pydantic Model）的职责

**数据模型定义 LLM 输出的结构和约束**，是 LLM 输出的"容器"。

| 职责 | 说明 | 示例 |
|------|------|------|
| 定义字段结构 | 字段名、类型、是否必填 | `calc_type: CalcType` |
| 字段语义说明 | `<what>` 标签说明字段含义 | `<what>计算类型</what>` |
| 填写条件 | `<when>` 标签说明何时填写 | `<when>ALWAYS required</when>` |
| 决策规则 | `<rule>` 标签说明如何决策 | `<rule>排名→RANK, 累计→RUNNING_TOTAL</rule>` |
| 依赖关系 | `<dependency>` 标签说明字段间依赖 | `<dependency>partition_by ⊆ where.dimensions</dependency>` |
| 负面约束 | `<must_not>` 标签说明禁止行为 | `<must_not>Include dimension not in where.dimensions</must_not>` |
| 数据验证 | Pydantic Validator 进行代码级验证 | `@field_validator("target")` |

**数据模型不负责**：
- 教 LLM 如何分析问题
- 提供领域知识
- 定义推理步骤

### Prompt 模板的职责

**Prompt 模板教 LLM 如何思考和分析**，是 LLM 的"教练"。

| 职责 | 说明 | 示例 |
|------|------|------|
| 角色定义 | 定义 LLM 扮演的角色 | "Computation reasoning expert" |
| 任务定义 | 定义 LLM 要完成的任务 | "Infer computation from restated_question" |
| 领域知识 | 提供分析所需的背景知识 | "Computation = Target × Partition × Operation" |
| 推理步骤 | 定义思考的步骤 | "Step 1: Infer target, Step 2: Infer partition_by" |
| 全局约束 | 定义 MUST / MUST NOT 规则 | "MUST: Infer from restated_question" |

**Prompt 模板不负责**：
- 定义具体字段名
- 定义字段类型
- 定义字段间的依赖关系

### 职责边界总结

```
┌─────────────────────────────────────────────────────────────┐
│  Prompt 模板（教 LLM 如何思考）                              │
│  ├── 角色定义                                               │
│  ├── 任务定义                                               │
│  ├── 领域知识（三元模型、分区概念等）                        │
│  ├── 推理步骤（抽象的，不涉及具体字段）                      │
│  └── 全局约束（MUST / MUST NOT）                            │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼ LLM 思考后填写
┌─────────────────────────────────────────────────────────────┐
│  数据模型（定义 LLM 输出什么）                               │
│  ├── 字段结构（名称、类型、必填）                            │
│  ├── 字段语义（<what>）                                     │
│  ├── 填写条件（<when>）                                     │
│  ├── 决策规则（<rule>）← 思考→填写的桥梁                    │
│  ├── 依赖关系（<dependency>）                               │
│  ├── 负面约束（<must_not>）                                 │
│  └── 数据验证（Pydantic Validator）                         │
└─────────────────────────────────────────────────────────────┘
```

### 黄金法则

| 判断条件 | 放置位置 |
|---------|---------|
| 提到具体字段名 | 数据模型 |
| 通用分析方法 | Prompt 模板 |
| 需要将思考转化为填写 | 数据模型的 `<rule>` |
| 领域概念（三元模型、分区） | Prompt 模板 |
| 字段间的依赖关系 | 数据模型的 `<dependency>` |

## 架构设计

### 数据流概览

```
用户问题
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Step1Output (语义理解层 - 平台无关)                         │
│  ├── how_type: HowType (SIMPLE / COMPLEX)                   │
│  ├── what: What (measures)                                  │
│  └── where: Where (dimensions, filters)                     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ (仅当 how_type == COMPLEX)
┌─────────────────────────────────────────────────────────────┐
│  Step2Output (计算推理层 - 平台无关)                         │
│  ├── computations: list[Computation]                        │
│  │   ├── target: str                                        │
│  │   ├── calc_type: CalcType                                │
│  │   ├── partition_by: list[str]                            │
│  │   └── params: CalcParams                                 │
│  └── validation: Step2Validation                            │
│                                                              │
│  注意：computations 可以同时包含 LOD 和表计算类型            │
│  例如：[{calc_type: LOD_FIXED, ...}, {calc_type: RANK, ...}]│
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  SemanticQuery (平台无关查询层)                              │
│  ├── dimensions                                             │
│  ├── measures                                               │
│  ├── computations (可包含多种类型)                          │
│  └── filters                                                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  TableauQueryBuilder (Tableau 适配层)                        │
│  1. 先处理 LOD 类型 → 生成 CalculatedField                   │
│  2. 再处理表计算类型 → 生成 TableCalcField                   │
│  CalcType → TableCalcType 转换                               │
│  CalcParams → VizQL 特定参数                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  VizQL API Request                                          │
│  fields: [                                                   │
│    ...dimensions,                                            │
│    ...measures,                                              │
│    ...calculatedFields (LOD),  ← 先生成                     │
│    ...tableCalcFields          ← 后生成（可引用LOD结果）     │
│  ]                                                           │
└─────────────────────────────────────────────────────────────┘
```

## 核心模型设计

### 1. 枚举定义

#### enums.py（通用枚举 - 跨 Agent 共享）

```python
class SortDirection(str, Enum):
    ASC = "ASC"
    DESC = "DESC"

class AggregationType(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    COUNT = "COUNT"
    COUNTD = "COUNTD"
    MIN = "MIN"
    MAX = "MAX"

class DateGranularity(str, Enum):
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
```

#### semantic_parser/enums.py（SemanticParser Agent 专用枚举）

```python
class HowType(str, Enum):
    """Step1 输出的计算复杂度分类（二元分类）
    
    Step1 只判断"是否需要复杂计算"，具体计算类型由 Step2 推理。
    这样设计的好处：
    1. Step1 职责简单：只判断复杂度
    2. 天然支持组合：Step2 可以输出任意组合的 Computation
    3. 简化 Prompt：不需要在 Step1 区分 TABLE_CALC 和 LOD
    """
    SIMPLE = "SIMPLE"      # 简单聚合，不需要 Step2
    COMPLEX = "COMPLEX"    # 需要复杂计算（表计算、LOD、或组合），需要 Step2

class IntentType(str, Enum):
    """用户意图分类"""
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"
    IRRELEVANT = "IRRELEVANT"

class CalcType(str, Enum):
    """计算类型（Step2 输出，平台无关）
    
    Step2 根据用户问题推理出具体的计算类型。
    一个 Step2Output 可以包含多个不同类型的 Computation。
    """
    # 排名类（表计算）
    RANK = "RANK"
    DENSE_RANK = "DENSE_RANK"
    PERCENTILE = "PERCENTILE"
    
    # 累计类（表计算）
    RUNNING_TOTAL = "RUNNING_TOTAL"
    MOVING_CALC = "MOVING_CALC"
    
    # 占比类（表计算）
    PERCENT_OF_TOTAL = "PERCENT_OF_TOTAL"
    
    # 差异类（表计算）
    DIFFERENCE = "DIFFERENCE"
    PERCENT_DIFFERENCE = "PERCENT_DIFFERENCE"
    
    # LOD 类
    LOD_FIXED = "LOD_FIXED"
    LOD_INCLUDE = "LOD_INCLUDE"
    LOD_EXCLUDE = "LOD_EXCLUDE"

class RankStyle(str, Enum):
    """排名风格"""
    COMPETITION = "COMPETITION"    # 1,2,2,4
    DENSE = "DENSE"                # 1,2,2,3
    UNIQUE = "UNIQUE"              # 1,2,3,4

class RelativeTo(str, Enum):
    """差异计算参考位置"""
    PREVIOUS = "PREVIOUS"
    NEXT = "NEXT"
    FIRST = "FIRST"
    LAST = "LAST"

class CalcAggregation(str, Enum):
    """累计/移动计算聚合方式"""
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"
```

### 2. Step2 模型 - 计算推理

#### 默认值策略

**设计决策**：CalcParams 不设置默认值，默认值在 TableauQueryBuilder 中定义。

**原因**：
1. **平台无关性**：CalcParams 是核心模型，不应绑定 Tableau 特定默认值
2. **可追溯性**：能区分"用户指定"和"系统默认"
3. **灵活性**：未来接入其他 BI 时可以有不同默认值

#### semantic_parser/step2.py

```python
class CalcParams(BaseModel):
    """计算参数（平台无关，无默认值）
    
    <what>不同 CalcType 使用的参数子集</what>
    
    <fill_order>
    1. direction, rank_style (if RANK/DENSE_RANK)
    2. relative_to (if DIFFERENCE/PERCENT_DIFFERENCE)
    3. aggregation, restart_every (if RUNNING_TOTAL)
    4. aggregation, window_previous, window_next, include_current (if MOVING_CALC)
    5. level_of (if PERCENT_OF_TOTAL)
    6. lod_dimensions, lod_aggregation (if LOD_*)
    </fill_order>
    
    <examples>
    RANK: {"direction": "DESC", "rank_style": "COMPETITION"}
    RUNNING_TOTAL: {"aggregation": "SUM", "restart_every": "年份"}
    LOD_FIXED: {"lod_dimensions": ["客户ID"], "lod_aggregation": "MIN"}
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    # 排名参数
    direction: SortDirection | None = Field(
        default=None,
        description="""<what>排序方向</what>
<when>RANK/DENSE_RANK/PERCENTILE 时填写</when>
<rule>DESC=降序排名（销售额高的排前面），ASC=升序排名</rule>"""
    )
    
    rank_style: RankStyle | None = Field(
        default=None,
        description="""<what>排名风格</what>
<when>RANK 时填写</when>
<rule>COMPETITION=1,2,2,4; DENSE=1,2,2,3; UNIQUE=1,2,3,4</rule>"""
    )
    
    # 差异参数
    relative_to: RelativeTo | None = Field(
        default=None,
        description="""<what>差异计算参考位置</what>
<when>DIFFERENCE/PERCENT_DIFFERENCE 时填写</when>
<rule>PREVIOUS=环比, FIRST=与期初比, LAST=与期末比</rule>"""
    )
    
    # 累计/移动计算参数
    aggregation: CalcAggregation | None = Field(
        default=None,
        description="""<what>累计/移动计算聚合方式</what>
<when>RUNNING_TOTAL/MOVING_CALC 时填写</when>
<rule>SUM=累计求和, AVG=累计平均</rule>"""
    )
    
    restart_every: str | None = Field(
        default=None,
        description="""<what>累计重新开始的维度</what>
<when>RUNNING_TOTAL 需要按某维度重新开始时填写</when>
<rule>YTD累计→restart_every="年份"</rule>"""
    )
    
    # 移动窗口参数
    window_previous: int | None = Field(
        default=None,
        description="""<what>向前取N个值</what>
<when>MOVING_CALC 时填写</when>
<rule>3个月移动平均→window_previous=2</rule>"""
    )
    
    window_next: int | None = Field(
        default=None,
        description="""<what>向后取N个值</what>
<when>MOVING_CALC 时填写</when>
<rule>通常为0（只看历史）</rule>"""
    )
    
    include_current: bool | None = Field(
        default=None,
        description="""<what>是否包含当前值</what>
<when>MOVING_CALC 时填写</when>
<rule>通常为True</rule>"""
    )
    
    # 占比参数
    level_of: str | None = Field(
        default=None,
        description="""<what>占比计算的级别</what>
<when>PERCENT_OF_TOTAL 需要指定级别时填写</when>
<rule>子类别占大类→level_of="大类"</rule>"""
    )
    
    # LOD 参数
    lod_dimensions: list[str] | None = Field(
        default=None,
        description="""<what>LOD 计算的维度列表</what>
<when>LOD_FIXED/LOD_INCLUDE/LOD_EXCLUDE 时填写</when>
<rule>每个客户的首购日期→lod_dimensions=["客户ID"]</rule>"""
    )
    
    lod_aggregation: AggregationType | None = Field(
        default=None,
        description="""<what>LOD 聚合函数</what>
<when>LOD_* 时填写</when>
<rule>首购日期→MIN, 终身消费→SUM</rule>"""
    )


class Computation(BaseModel):
    """计算定义
    
    <what>Computation = Target × CalcType × Partition × Params</what>
    
    <fill_order>
    1. target (ALWAYS)
    2. calc_type (ALWAYS)
    3. partition_by (ALWAYS, can be empty)
    4. params (根据 calc_type 填写对应参数)
    5. alias (optional)
    </fill_order>
    
    <examples>
    全局排名: {"target": "销售额", "calc_type": "RANK", "partition_by": [], "params": {"direction": "DESC"}}
    每月排名: {"target": "销售额", "calc_type": "RANK", "partition_by": ["月份"], "params": {"direction": "DESC"}}
    LOD首购: {"target": "订单日期", "calc_type": "LOD_FIXED", "params": {"lod_dimensions": ["客户ID"], "lod_aggregation": "MIN"}, "alias": "首购日期"}
    </examples>
    
    <anti_patterns>
    ❌ partition_by 包含不在 dimensions 中的字段
    ❌ calc_type 与 params 不匹配（如 RANK 却填了 lod_dimensions）
    ❌ LOD 类型却没有填 lod_dimensions
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    target: str = Field(
        description="""<what>目标度量字段</what>
<when>ALWAYS required</when>
<rule>Must be one of what.measures</rule>
<must_not>Use technical field name (will cause mapping error)</must_not>"""
    )
    
    calc_type: CalcType = Field(
        description="""<what>计算类型</what>
<when>ALWAYS required</when>
<rule>排名→RANK, 累计→RUNNING_TOTAL, 环比→PERCENT_DIFFERENCE, 首购日期→LOD_FIXED</rule>"""
    )
    
    partition_by: list[str] = Field(
        default_factory=list,
        description="""<what>分区维度（定义计算范围）</what>
<when>ALWAYS fill (can be empty list)</when>
<rule>全局→[], 每月内→[月份], 每省内→[省份]</rule>
<dependency>partition_by ⊆ where.dimensions</dependency>
<must_not>Include dimension not in where.dimensions</must_not>"""
    )
    
    params: CalcParams = Field(
        default_factory=CalcParams,
        description="""<what>计算参数</what>
<when>根据 calc_type 填写对应参数</when>
<dependency>params 字段与 calc_type 匹配</dependency>"""
    )
    
    alias: str | None = Field(
        default=None,
        description="""<what>结果别名</what>
<when>Optional, LOD 类型建议填写</when>"""
    )


class Step2Output(BaseModel):
    """Step2 输出：计算推理与自我验证
    
    <what>计算定义列表 + LLM 自我验证结果</what>
    
    <fill_order>
    1. reasoning (ALWAYS first)
    2. computations (ALWAYS, 可包含多种类型)
    3. validation (ALWAYS - LLM 自我验证)
    </fill_order>
    
    <examples>
    单一表计算: {"computations": [{"calc_type": "RANK", ...}]}
    LOD+表计算组合: {"computations": [{"calc_type": "LOD_FIXED", ...}, {"calc_type": "RANK", ...}]}
    </examples>
    
    <anti_patterns>
    ❌ 组合场景只输出一个 Computation
    ❌ LOD 和表计算顺序错误（应先 LOD 后表计算）
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    reasoning: str = Field(
        description="""<what>推理过程描述</what>
<when>ALWAYS required</when>
<rule>Explain how calc_type, partition_by, params were inferred</rule>"""
    )
    
    computations: list[Computation] = Field(
        description="""<what>计算定义列表（可包含多种类型）</what>
<when>ALWAYS required</when>
<rule>组合场景：先 LOD 类型，后表计算类型</rule>
<must_not>组合场景只输出单个 Computation</must_not>"""
    )
    
    validation: Step2Validation = Field(
        description="""<what>LLM 自我验证结果</what>
<when>ALWAYS required</when>
<rule>Check inference against Step 1 output</rule>"""
    )
```

### 3. Tableau 适配层

#### platforms/tableau/models/table_calc.py（保持不变）

VizQL API 特定的模型保持在 platforms/tableau/models/ 下，不需要改动。

#### platforms/tableau/query_builder.py（更新转换逻辑）

```python
class TableauQueryBuilder(BaseQueryBuilder):
    """Tableau 查询构建器"""
    
    # Tableau 特定默认值
    DEFAULT_RANK_TYPE = RankStyle.COMPETITION
    DEFAULT_DIRECTION = SortDirection.DESC
    DEFAULT_RELATIVE_TO = RelativeTo.PREVIOUS
    DEFAULT_AGGREGATION = CalcAggregation.SUM
    DEFAULT_WINDOW_PREVIOUS = 2
    DEFAULT_WINDOW_NEXT = 0
    DEFAULT_INCLUDE_CURRENT = True
    
    # CalcType → TableCalcType 映射
    CALC_TYPE_MAPPING = {
        CalcType.RANK: TableCalcType.RANK,
        CalcType.DENSE_RANK: TableCalcType.RANK,
        CalcType.PERCENTILE: TableCalcType.PERCENTILE,
        CalcType.RUNNING_TOTAL: TableCalcType.RUNNING_TOTAL,
        CalcType.MOVING_CALC: TableCalcType.MOVING_CALCULATION,
        CalcType.PERCENT_OF_TOTAL: TableCalcType.PERCENT_OF_TOTAL,
        CalcType.DIFFERENCE: TableCalcType.DIFFERENCE_FROM,
        CalcType.PERCENT_DIFFERENCE: TableCalcType.PERCENT_DIFFERENCE_FROM,
    }
    
    # LOD 类型集合
    LOD_CALC_TYPES = {CalcType.LOD_FIXED, CalcType.LOD_INCLUDE, CalcType.LOD_EXCLUDE}
    
    def _build_computation_fields(self, computations: list[Computation]) -> list[dict]:
        """构建计算字段列表（先 LOD，后表计算）
        
        重要：必须先生成 LOD 字段，因为表计算可能引用 LOD 结果
        """
        lod_fields = []
        table_calc_fields = []
        
        for comp in computations:
            if comp.calc_type in self.LOD_CALC_TYPES:
                lod_fields.append(self._build_lod_field(comp))
            else:
                table_calc_fields.append(self._build_table_calc_field(comp))
        
        # 先 LOD，后表计算
        return lod_fields + table_calc_fields
    
    def _build_rank_spec(self, comp: Computation) -> dict:
        """构建排名表计算（应用默认值）"""
        params = comp.params
        rank_type = params.rank_style or self.DEFAULT_RANK_TYPE
        if comp.calc_type == CalcType.DENSE_RANK:
            rank_type = RankStyle.DENSE
        return {
            "tableCalcType": "RANK",
            "dimensions": self._build_dimensions(comp.partition_by),
            "rankType": rank_type.value,
            "direction": (params.direction or self.DEFAULT_DIRECTION).value,
        }
    
    def _build_running_total_spec(self, comp: Computation) -> dict:
        """构建累计表计算（应用默认值）"""
        params = comp.params
        spec = {
            "tableCalcType": "RUNNING_TOTAL",
            "dimensions": self._build_dimensions(comp.partition_by),
            "aggregation": (params.aggregation or self.DEFAULT_AGGREGATION).value,
        }
        if params.restart_every:
            spec["restartEvery"] = {"fieldCaption": params.restart_every}
        return spec
    
    def _build_moving_calc_spec(self, comp: Computation) -> dict:
        """构建移动计算（应用默认值）"""
        params = comp.params
        return {
            "tableCalcType": "MOVING_CALCULATION",
            "dimensions": self._build_dimensions(comp.partition_by),
            "aggregation": (params.aggregation or self.DEFAULT_AGGREGATION).value,
            "previous": params.window_previous if params.window_previous is not None else self.DEFAULT_WINDOW_PREVIOUS,
            "next": params.window_next if params.window_next is not None else self.DEFAULT_WINDOW_NEXT,
            "includeCurrent": params.include_current if params.include_current is not None else self.DEFAULT_INCLUDE_CURRENT,
        }
    
    def _build_lod_field(self, comp: Computation) -> dict:
        """构建 LOD 计算字段"""
        params = comp.params
        lod_type_map = {
            CalcType.LOD_FIXED: "FIXED",
            CalcType.LOD_INCLUDE: "INCLUDE",
            CalcType.LOD_EXCLUDE: "EXCLUDE",
        }
        lod_type = lod_type_map[comp.calc_type]
        
        # 构建 LOD 表达式字符串
        dims_str = ", ".join(f"[{d}]" for d in (params.lod_dimensions or []))
        agg = (params.lod_aggregation or AggregationType.SUM).value
        
        if dims_str:
            calculation = f"{{{lod_type} {dims_str} : {agg}([{comp.target}])}}"
        else:
            calculation = f"{{{agg}([{comp.target}])}}"
        
        return {
            "fieldCaption": comp.alias or f"LOD_{comp.target}",
            "calculation": calculation,
        }
```

## CalcType 映射表

### 用户问题 → CalcType

| 用户表述 | CalcType |
|---------|----------|
| 排名、Top N | RANK |
| 密集排名 | DENSE_RANK |
| 百分位 | PERCENTILE |
| 累计、YTD | RUNNING_TOTAL |
| 移动平均 | MOVING_CALC |
| 占比、百分比 | PERCENT_OF_TOTAL |
| 差异、变化 | DIFFERENCE |
| 增长率、环比 | PERCENT_DIFFERENCE |
| 每个客户的... | LOD_FIXED |

### CalcType → TableCalcType (VizQL)

| CalcType | TableCalcType | 额外参数 |
|----------|---------------|---------|
| RANK | RANK | rankType=COMPETITION |
| DENSE_RANK | RANK | rankType=DENSE |
| PERCENTILE | PERCENTILE | direction |
| RUNNING_TOTAL | RUNNING_TOTAL | aggregation, restartEvery |
| MOVING_CALC | MOVING_CALCULATION | previous, next, aggregation |
| PERCENT_OF_TOTAL | PERCENT_OF_TOTAL | levelAddress |
| DIFFERENCE | DIFFERENCE_FROM | relativeTo |
| PERCENT_DIFFERENCE | PERCENT_DIFFERENCE_FROM | relativeTo |
| LOD_* | CalculatedField | calculation 字符串 |

## 目录结构重构

### 当前结构（扁平，混乱）

```
tableau_assistant/src/core/models/
├── __init__.py
├── computations.py      # Computation 模型
├── data_model.py
├── dimension_hierarchy.py
├── enums.py             # 所有枚举混在一起
├── field_mapping.py
├── fields.py
├── filters.py
├── insight.py
├── observer.py
├── parse_result.py
├── query.py
├── replan.py
├── step1.py
├── step2.py
└── validation.py
```

### 目标结构（按 Agent 划分）

```
tableau_assistant/src/core/models/
├── __init__.py
├── common/                    # 通用模型（跨 Agent 共享）
│   ├── __init__.py
│   ├── enums.py              # 通用枚举（SortDirection, AggregationType 等）
│   ├── fields.py             # DimensionField, MeasureField
│   ├── filters.py            # Filter 相关模型
│   └── query.py              # SemanticQuery
│
├── semantic_parser/           # SemanticParser Agent 模型
│   ├── __init__.py
│   ├── enums.py              # HowType, IntentType, CalcType 等
│   ├── step1.py              # Step1Output, What, Where
│   ├── step2.py              # Step2Output, Computation, CalcParams
│   └── validation.py         # Step2Validation
│
├── field_mapper/              # FieldMapper Agent 模型
│   ├── __init__.py
│   ├── enums.py              # MappingSource
│   └── mapping.py            # FieldMapping, MappedQuery
│
├── insight/                   # Insight Agent 模型
│   ├── __init__.py
│   └── insight.py            # InsightOutput
│
├── replanner/                 # Replanner Agent 模型
│   ├── __init__.py
│   └── replan.py             # ReplanOutput
│
└── observer/                  # Observer 模型
    ├── __init__.py
    └── observer.py           # ObserverOutput
```

## 测试策略

### 单元测试

1. CalcType 枚举序列化/反序列化
2. CalcParams 参数验证
3. Computation 模型约束验证
4. TableauQueryBuilder 转换逻辑

### 集成测试

1. 用户问题 → 端到端流程：
   - 排名问题 → RANK → VizQL RANK
   - 累计问题 → RUNNING_TOTAL → VizQL RUNNING_TOTAL
   - 增长率问题 → PERCENT_DIFFERENCE → VizQL PERCENT_DIFFERENCE_FROM

## 错误处理

| 错误类型 | 触发条件 | 处理方式 |
|---------|---------|---------|
| INVALID_CALC_TYPE | calc_type 不在枚举范围 | 返回验证错误 |
| INVALID_PARAMS | params 与 calc_type 不兼容 | 返回验证错误 |
| PARTITION_NOT_IN_DIMS | partition_by 包含不在 dimensions 中的字段 | 返回验证错误 |
| TARGET_NOT_IN_MEASURES | target 不在 measures 中 | 返回验证错误 |

## 正确性属性

*正确性属性是系统应该满足的形式化规范，用于验证实现的正确性。*

### Property 1: HowType 二元分类正确性
*对于任意* 用户问题，Step1 应当正确判断是否需要复杂计算（SIMPLE 或 COMPLEX）
**验证: 需求 1.2-1.5**

### Property 2: CalcType 枚举完整性
*对于任意* 复杂计算需求，Step2 应当能够映射到一个或多个有效的 CalcType 枚举值
**验证: 需求 2.2, 7.1**

### Property 3: CalcParams 参数一致性
*对于任意* CalcType，其对应的 CalcParams 应当只包含该类型所需的参数字段
**验证: 需求 2.4-2.9**

### Property 4: 分区维度子集约束
*对于任意* Computation，其 partition_by 应当是 SemanticQuery.dimensions 的子集
**验证: 需求 6.4-6.5**

### Property 5: TableCalcType 映射完整性
*对于任意* CalcType（除 LOD_* 外），应当存在唯一的 TableCalcType 映射
**验证: 需求 5.5-5.9**

### Property 6: LOD 表达式生成正确性
*对于任意* LOD_FIXED/LOD_INCLUDE/LOD_EXCLUDE 类型的 Computation，生成的 CalculatedField.calculation 应当是有效的 Tableau LOD 语法
**验证: 需求 3.3-3.7, 5.10**

### Property 7: 组合场景字段顺序正确性
*对于任意* 包含 LOD 和表计算组合的 computations 列表，QueryBuilder 应当先生成 CalculatedField，再生成 TableCalcField
**验证: 需求 7.2-7.3**
