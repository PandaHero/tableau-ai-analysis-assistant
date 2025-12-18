# 设计文档

## 概述

本设计文档描述了 Semantic Parser Agent 和语义层重构的技术实现方案。核心目标是建立一个**高度抽象、平台无关的语义层**，支持多 BI 平台（Tableau、Power BI、Superset 等），让 LLM 输出纯粹的用户意图表示，由平台适配器转换为具体平台的查询语句。

### 设计原则

1. **意图驱动**：语义层描述"用户想要什么"，而非"BI 工具怎么实现"
2. **平台无关**：核心模型不包含任何平台特定概念（如 LOD、TableCalc、DAX）
3. **两步解析**：Step 1 语义理解与问题重述，Step 2 计算推理与验证
4. **三元模型**：所有查询都可以用 What × Where × How 描述
5. **LLM 组合**：Step 1 + Step 2 + Observer 形成闭环，减少幻觉

### 核心抽象

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        用户意图层（Platform-Agnostic）                    │
│                                                                          │
│  "各省份销售额排名"  →  SemanticQuery {                                   │
│                           what: [销售额],                                │
│                           where: [省份],                                 │
│                           how: RANKING                                   │
│                         }                                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │   Tableau   │ │  Power BI   │ │  Superset   │
            │   Adapter   │ │   Adapter   │ │   Adapter   │
            └─────────────┘ └─────────────┘ └─────────────┘
```

## 核心理论：三元模型

### 查询的本质

所有数据分析查询都可以用三元模型描述：

**查询 = What × Where × How**

- **What（目标）**：要计算什么数据（度量 + 聚合方式）
- **Where（范围）**：在什么范围内查看（维度 + 筛选）
- **How（操作）**：怎么计算（简单聚合 / 复杂计算）

### 计算的本质

所有复杂计算都可以用一个公式描述：

**计算 = 目标 × 分区 × 操作**

- **目标（Target）**：对什么度量计算
- **分区（Partition）**：在什么范围内计算（决定了计算的粒度和方向）
- **操作（Operation）**：做什么计算

### 分区的本质

分区回答的问题是：**"哪些维度保持不变，在剩余维度上计算"**

| partition_by | 含义 | Tableau | Power BI | SQL |
|--------------|------|---------|----------|-----|
| `[]` | 全局 | Partitioning=无 | ALL() | OVER () |
| `["月份"]` | 按月份分区 | Partitioning=月份 | ALLEXCEPT(月份) | PARTITION BY 月份 |
| `["省份", "月份"]` | 视图粒度 | Partitioning=全部 | VALUES() | 无 OVER |

## LLM 组合架构

### 核心理念

这个设计模拟了人类的**元认知**过程：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Semantic Parser Agent                             │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Step 1: 直觉（Intuition）                     │    │
│  │                                                                  │    │
│  │  • 理解问题，重述为完整的独立问题                                 │    │
│  │  • 提取结构化信息（What × Where × How）                          │    │
│  │  • 分类意图（DATA_QUERY / CLARIFICATION / GENERAL / IRRELEVANT） │    │
│  │                                                                  │    │
│  │  输出: restated_question + what/where/how_type + intent          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Step 2: 推理（Reasoning）                     │    │
│  │                    （仅 DATA_QUERY + 非 SIMPLE）                  │    │
│  │                                                                  │    │
│  │  • 从 restated_question 推断计算定义                             │    │
│  │  • 用 Step 1 的结构化输出验证推理结果                            │    │
│  │                                                                  │    │
│  │  输出: computations + validation（自我验证结果）                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                     │
│                                    ▼                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Observer: 元认知（Metacognition）             │    │
│  │                    （仅当 validation.all_valid == False）        │    │
│  │                                                                  │    │
│  │  • 检查重述完整性（是否丢失关键信息）                            │    │
│  │  • 复核结构一致性（Step 2 的验证结果）                           │    │
│  │  • 检查语义一致性（推理是否与重述语义一致）                      │    │
│  │                                                                  │    │
│  │  决策: ACCEPT / CORRECT / RETRY / CLARIFY                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 为什么这样能减少幻觉？

| 机制 | 说明 |
|------|------|
| **交叉验证** | Step 2 用 Step 1 的结构化输出验证自己的推理 |
| **一致性检查** | 如果两个独立推理结果不一致，说明可能有幻觉 |
| **闭环修正** | Observer 可以修正小错误，或请求重试/澄清 |

### 触发条件

```python
# Step 2 触发条件
if intent.type == IntentType.DATA_QUERY and how_type != HowType.SIMPLE:
    step2_output = await step2_reasoning(step1_output)

# Observer 触发条件
if step2_output and not step2_output.validation.all_valid:
    observer_output = await observer.check(original_question, step1_output, step2_output)
```

### 设计理念

这个设计模拟了人类的**元认知**过程：

1. **Step 1（直觉）**：理解问题，重述为完整的独立问题
2. **Step 2（推理）**：从重述推断计算，同时自我验证
3. **Observer（元认知）**：检查一致性，发现幻觉，按需介入

### 为什么这样能减少幻觉？

- **交叉验证**：Step 2 用 Step 1 的结构化输出验证自己的推理
- **一致性检查**：如果两个独立推理结果不一致，说明可能有幻觉
- **闭环修正**：Observer 可以修正小错误，或请求重试/澄清

## Step 1: 语义理解与问题重述

### 核心职责

**将用户的跟进问题重述为完整的独立问题**

问题重述不是简单的字符串拼接，而是：**从历史对话中提取 What × Where × How，与当前问题合并**

```
历史: "各省份销售额"
  → What: 销售额, Where: 省份, How: 简单聚合

当前: "排名呢？"
  → How: 排名（用户想修改的部分）

合并后:
  → What: 销售额（继承）
  → Where: 省份（继承）
  → How: 排名（新增）
  
重述: "按省份分组，计算销售额总和，并按销售额降序排名"
```

### 输入输出

**输入：**
```python
question: str                       # 当前用户问题
conversation_history: list[Message] # 历史对话
metadata: DataSourceMetadata        # 数据源元数据（辅助理解）
```

**输出：**
```python
class Step1Output(BaseModel):
    # ===== 核心输出 =====
    restated_question: str
    """重述后的完整问题（自然语言）
    
    这是 Step 2 的主要输入。
    包含了从历史对话中继承的所有上下文。
    关键：必须保留分区意图（每月、每省、当月、全国等）
    """
    
    # ===== 结构化输出（用于 Step 2 验证） =====
    what: What          # 目标（度量）
    where: Where        # 范围（维度 + 筛选）
    how_type: HowType   # 计算类型
    
    # ===== 意图分类 =====
    intent: Intent
```

### 合并规则

| 场景 | 规则 |
|------|------|
| 当前问题明确提到 | 优先使用当前问题的值 |
| 当前问题未提到 | 从历史对话继承 |
| 当前问题是修改 | 替换历史中的对应元素 |
| 当前问题是叠加 | 与历史合并 |

详细的 Prompt 设计和示例见：[附件A：Step 1 详细设计](./appendix-a-step1-detail.md)

## 意图分类

Step 1 除了构建三元组，还需要对用户问题进行意图分类：

```python
class IntentType(str, Enum):
    DATA_QUERY = "DATA_QUERY"       # 有效的数据查询
    CLARIFICATION = "CLARIFICATION" # 需要澄清
    GENERAL = "GENERAL"             # 问元数据/字段信息
    IRRELEVANT = "IRRELEVANT"       # 与数据分析无关
```

### 分类规则

| 意图 | 判断条件 | 示例 |
|------|---------|------|
| DATA_QUERY | 有可查询的字段，信息完整 | "各省份销售额"、"总销售额" |
| CLARIFICATION | 引用了未指定的值或需要澄清 | "这些产品的销售额" |
| GENERAL | 问数据集描述、字段信息 | "有哪些字段？" |
| IRRELEVANT | 与数据分析无关 | "今天天气怎么样？" |

### 澄清问题生成

当意图为 `CLARIFICATION` 时，系统生成澄清问题：

```python
class ClarificationQuestion(BaseModel):
    question: str                    # 澄清问题
    options: list[str] | None = None # 可选值列表
    field_reference: str | None = None # 相关字段
```

## Step 2: 计算推理与自我验证

### 触发条件

```python
if step1_output.how_type != HowType.SIMPLE:
    step2_output = await step2_reasoning(step1_output)
else:
    step2_output = None  # 简单查询，跳过 Step 2
```

### 核心职责

1. **从 restated_question 推断计算定义**（主要任务）
2. **用 Step 1 的结构化输出验证推理结果**（自我验证）

### 输入

```python
# Step 1 的完整输出
restated_question: str      # 主要输入！
what: What                  # 用于验证 target
where: Where                # 用于验证 partition_by
how_type: HowType           # 用于验证 operation.type
```

### 输出

```python
class Step2Output(BaseModel):
    # ===== 推理结果 =====
    computations: list[Computation]
    
    # ===== 推理过程 =====
    reasoning: str
    """推理过程的自然语言描述"""
    
    # ===== 自我验证结果 =====
    validation: Step2Validation


class Step2Validation(BaseModel):
    """Step 2 对自己推理结果的验证"""
    
    target_check: ValidationCheck
    """target 是否与 what.measures 一致"""
    
    partition_by_check: ValidationCheck
    """partition_by 中的维度是否都在 where.dimensions 中"""
    
    operation_check: ValidationCheck
    """operation.type 是否与 how_type 一致"""
    
    all_valid: bool
    """所有检查是否都通过"""
    
    inconsistencies: list[str]
    """发现的不一致之处"""


class ValidationCheck(BaseModel):
    inferred_value: str | list[str]
    """从 restated_question 推断的值"""
    
    reference_value: str | list[str]
    """Step 1 结构化输出中的值"""
    
    is_match: bool
    """是否匹配"""
    
    note: str
    """说明"""
```

### 验证规则

| 检查点 | 检查内容 | 判断标准 |
|--------|---------|---------|
| target_check | target 是否在 what.measures 中 | target ∈ what.measures |
| partition_by_check | partition_by 是否都在 where.dimensions 中 | partition_by ⊆ where.dimensions |
| operation_check | operation.type 是否与 how_type 匹配 | 类型映射关系 |

### operation_check 的映射关系

```python
OPERATION_TYPE_MAPPING = {
    HowType.RANKING: [OperationType.RANK, OperationType.DENSE_RANK],
    HowType.CUMULATIVE: [OperationType.RUNNING_SUM, OperationType.RUNNING_AVG, 
                         OperationType.MOVING_AVG, OperationType.MOVING_SUM],
    HowType.COMPARISON: [OperationType.PERCENT, OperationType.DIFFERENCE, 
                         OperationType.GROWTH_RATE, OperationType.YEAR_AGO, 
                         OperationType.PERIOD_AGO],
    HowType.GRANULARITY: [OperationType.FIXED],
}
```

详细的 Prompt 设计和示例见：[附件B：Step 2 详细设计](./appendix-b-step2-detail.md)

## Observer: 一致性检查（按需介入）

### 触发条件

```python
if step2_output.validation.all_valid:
    # 验证通过，不需要 Observer
    return step2_output.computations
else:
    # 验证不通过，Observer 介入
    observer_result = await observer.check(original_question, step1_output, step2_output)
    return observer_result.final_result
```

### 核心职责

1. **检查重述完整性**：restated_question 是否完整保留了 original_question 的关键信息
2. **复核结构一致性**：复核 Step 2 的验证结果
3. **检查语义一致性**：Step 2 的推理是否与 restated_question 的语义一致
4. **做出决策**：ACCEPT / CORRECT / RETRY / CLARIFY

### 输入

```python
class ObserverInput(BaseModel):
    original_question: str      # 原始问题（用于回溯）
    step1: Step1Output          # Step 1 输出
    step2: Step2Output          # Step 2 输出
```

### 输出

```python
class ObserverOutput(BaseModel):
    is_consistent: bool
    """Step 1 和 Step 2 是否一致"""
    
    conflicts: list[Conflict]
    """发现的冲突"""
    
    decision: ObserverDecision
    """Observer 的决策"""
    
    correction: Correction | None
    """修正内容（仅当 decision=CORRECT）"""
    
    final_result: Computation | None
    """最终结果"""


class ObserverDecision(str, Enum):
    ACCEPT = "ACCEPT"           # 一致，接受 Step 2 结果
    CORRECT = "CORRECT"         # 有小冲突，Observer 修正
    RETRY = "RETRY"             # 有大冲突，需要重新推理
    CLARIFY = "CLARIFY"         # 无法判断，需要用户澄清
```

详细的 Prompt 设计和示例见：[附件B：Step 2 详细设计](./appendix-b-step2-detail.md)

## 完整输出结构

Semantic Parser Agent 的最终输出是 `SemanticParseResult`：

```python
class SemanticParseResult(BaseModel):
    """语义解析完整结果"""
    
    restated_question: str
    """重述后的问题"""
    
    intent: Intent
    """意图分类"""
    
    semantic_query: SemanticQuery | None = None
    """语义查询（仅 DATA_QUERY 意图）"""
    
    clarification: ClarificationQuestion | None = None
    """澄清问题（仅 CLARIFICATION 意图）"""
    
    general_response: str | None = None
    """通用响应（仅 GENERAL 意图）"""
```

## 核心数据模型

### SemanticQuery（最终输出）

```python
class SemanticQuery(BaseModel):
    """核心语义查询（平台无关）"""
    
    dimensions: list[DimensionField] | None = None
    """维度字段列表"""
    
    measures: list[MeasureField] | None = None
    """度量字段列表"""
    
    computations: list[Computation] | None = None
    """计算列表"""
    
    filters: list[Filter] | None = None
    """筛选条件列表"""
    
    sorts: list[Sort] | None = None
    """排序规则列表"""
```

### Computation（计算定义）

```python
class Computation(BaseModel):
    """计算 = 目标 × 分区 × 操作"""
    
    target: str
    """计算目标（度量字段）"""
    
    partition_by: list[str]
    """分区维度"""
    
    operation: Operation
    """计算操作"""


class Operation(BaseModel):
    """计算操作"""
    type: OperationType
    params: dict = {}


class OperationType(str, Enum):
    """计算操作类型"""
    
    # 排名类
    RANK = "RANK"           # 排名（1, 2, 3, ...）
    DENSE_RANK = "DENSE_RANK"  # 密集排名（1, 2, 2, 3, ...）
    
    # 累计类
    RUNNING_SUM = "RUNNING_SUM"   # 累计求和
    RUNNING_AVG = "RUNNING_AVG"   # 累计平均
    
    # 移动类
    MOVING_AVG = "MOVING_AVG"     # 移动平均，params: {window_size: int}
    MOVING_SUM = "MOVING_SUM"     # 移动求和，params: {window_size: int}
    
    # 比较类
    PERCENT = "PERCENT"           # 占比（当前值 / 分区总值）
    DIFFERENCE = "DIFFERENCE"     # 差值
    GROWTH_RATE = "GROWTH_RATE"   # 增长率
    
    # 时间比较类
    YEAR_AGO = "YEAR_AGO"         # 去年同期
    PERIOD_AGO = "PERIOD_AGO"     # 上一周期
    
    # 粒度类
    FIXED = "FIXED"               # 固定粒度聚合（不受视图影响）
```

详细的数据模型定义见：[附件C：数据模型详细定义](./appendix-c-data-models.md)

## 系统架构

### 完整流程

```
用户问题 + 历史对话 + 元数据
        │
        ▼
┌───────────────────┐
│  Step 1: 语义理解  │ ← LLM 调用
│  - 问题重述        │
│  - 提取结构        │
│  - 意图分类        │
└───────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│                    intent.type == ?                            │
├───────────────┬───────────────┬───────────────┬───────────────┤
│  DATA_QUERY   │ CLARIFICATION │    GENERAL    │  IRRELEVANT   │
└───────┬───────┴───────┬───────┴───────┬───────┴───────┬───────┘
        │               │               │               │
        ▼               ▼               ▼               ▼
  继续处理        生成澄清问题     生成通用响应      拒绝处理
        │               │               │               │
        │               ▼               ▼               ▼
        │         返回 clarification  返回 general_response  返回提示
        │
        ▼
    how_type == SIMPLE?
        │
    ┌───┴───┐
   Yes      No
    │       │
    ▼       ▼
  直接   ┌───────────────────┐
  构建   │  Step 2: 计算推理  │ ← LLM 调用
  查询   │  - 从重述推断计算   │
         │  - 自我验证        │
         └───────────────────┘
                │
                ▼
         validation.all_valid?
                │
            ┌───┴───┐
           Yes      No
            │       │
            ▼       ▼
         输出   ┌───────────────────┐
         结果   │  Observer: 检查    │ ← LLM 调用（按需）
               │  - 一致性检查       │
               │  - 决策            │
               └───────────────────┘
                        │
                        ▼
                ┌───────────────┐
                │ ACCEPT/CORRECT │ → 输出结果
                │ RETRY          │ → 重新执行
                │ CLARIFY        │ → 请求澄清
                └───────────────┘
        │
        ▼
┌───────────────────┐
│  SemanticQuery    │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  字段映射         │ ← 已有功能
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  平台适配器       │
│  ├─ Tableau       │
│  ├─ Power BI      │
│  └─ SQL           │
└───────────────────┘
        │
        ▼
    查询结果
```

### 完整目录结构

项目架构以**通用语义模型**为核心，采用分层设计：

1. **核心层**：平台无关的语义模型和接口（最重要）
2. **平台层**：平台特定的实现（Tableau、Power BI 等）
3. **Agent 层**：智能处理单元 + 工具定义
4. **编排层**：LangGraph 工作流编排 + 中间件
5. **基础设施层**：AI 模型、存储、配置、监控、异常
6. **服务层**：对外 HTTP API

```
src/
│
├── ==================== 1. 核心层（通用语义模型）====================
│   这是整个系统的核心，定义平台无关的语义模型和接口
│
├── core/                              # 【新建】平台无关的核心层
│   ├── __init__.py
│   │
│   ├── models/                        # 核心数据模型（平台无关）
│   │   ├── __init__.py                # 导出所有模型
│   │   ├── enums.py                   # 公共枚举
│   │   │                              #   - AggregationType, DateGranularity, SortDirection
│   │   │                              #   - FilterType, HowType, OperationType
│   │   │                              #   - IntentType, ObserverDecision
│   │   ├── fields.py                  # DimensionField, MeasureField, Sort
│   │   ├── computations.py            # Operation, Computation（核心抽象）
│   │   ├── filters.py                 # Filter 及其子类
│   │   ├── query.py                   # SemanticQuery（核心输出）
│   │   ├── step1.py                   # Step1Output, What, Where, Intent
│   │   ├── step2.py                   # Step2Output, Step2Validation
│   │   ├── observer.py                # ObserverInput, ObserverOutput
│   │   ├── parse_result.py            # SemanticParseResult, ClarificationQuestion
│   │   ├── data_models.py             # 【重命名】DataModel, FieldInfo, RelationInfo
│   │   │                              #   （原 metadata.py，现在管理完整数据模型）
│   │   └── validation.py              # ValidationError, ValidationResult, QueryResult
│   │
│   └── interfaces/                    # 抽象接口定义
│       ├── __init__.py
│       ├── platform_adapter.py        # BasePlatformAdapter 抽象基类
│       ├── query_builder.py           # BaseQueryBuilder 抽象基类
│       └── field_mapper.py            # BaseFieldMapper 抽象基类
│
├── ==================== 2. 平台层（平台特定实现）====================
│   将通用语义模型转换为平台特定的查询
│
├── platforms/                         # 【新建】平台特定实现
│   ├── __init__.py
│   ├── base.py                        # PlatformRegistry 平台注册和工厂
│   │
│   ├── tableau/                       # Tableau 实现
│   │   ├── __init__.py
│   │   ├── adapter.py                 # TableauAdapter（实现 BasePlatformAdapter）
│   │   ├── query_builder.py           # TableauQueryBuilder（实现 BaseQueryBuilder）
│   │   │                              #   - Computation → TableCalc/LOD 转换
│   │   │                              #   - Filter → VizQL Filter 转换
│   │   ├── field_mapper.py            # TableauFieldMapper（实现 BaseFieldMapper）
│   │   ├── client.py                  # VizQL API 客户端
│   │   └── models/                    # Tableau 特定模型
│   │       ├── __init__.py
│   │       ├── vizql_types.py         # VizQL API 类型
│   │       ├── table_calc.py          # 表计算模型（TableCalcType, TableCalcSpecification）
│   │       └── lod.py                 # LOD 表达式模型（LODType, LODExpression）
│   │
│   ├── powerbi/                       # Power BI 实现（未来扩展）
│   └── superset/                      # Superset 实现（未来扩展）
│
├── ==================== 3. Agent 层（智能处理单元）====================
│   每个 Agent 是一个智能处理单元，有自己的组件和 Prompt
│
├── agents/                            # Agent 定义
│   ├── __init__.py
│   ├── base/                          # Agent 基类
│   │   ├── __init__.py
│   │   ├── node.py                    # BaseAgentNode
│   │   ├── prompt.py                  # BasePrompt
│   │   └── middleware_runner.py       # 中间件运行器
│   │
│   ├── semantic_parser/               # 【新建】语义解析 Agent
│   │   ├── __init__.py                #   组件：Step 1 + Step 2 + Observer
│   │   ├── node.py                    # SemanticParserNode（工作流节点）
│   │   ├── agent.py                   # SemanticParserAgent（LLM 组合编排）
│   │   ├── components/                # Agent 内部组件
│   │   │   ├── __init__.py
│   │   │   ├── step1.py               # Step 1: 语义理解与问题重述
│   │   │   ├── step2.py               # Step 2: 计算推理与自我验证
│   │   │   └── observer.py            # Observer: 一致性检查
│   │   └── prompts/                   # Prompt 模板
│   │       ├── __init__.py
│   │       ├── step1.py
│   │       ├── step2.py
│   │       └── observer.py
│   │
│   ├── insight/                       # 洞察 Agent
│   │   ├── __init__.py                #   组件：主持人 + 分析师 + ...
│   │   ├── node.py                    # InsightNode（工作流节点）
│   │   ├── components/                # Agent 内部组件
│   │   │   ├── __init__.py
│   │   │   ├── coordinator.py         # 主持人（协调器）
│   │   │   ├── analyzer.py            # 分析师
│   │   │   ├── profiler.py            # 数据画像
│   │   │   ├── anomaly_detector.py    # 异常检测
│   │   │   ├── statistical_analyzer.py
│   │   │   ├── chunker.py
│   │   │   ├── accumulator.py
│   │   │   └── synthesizer.py
│   │   └── prompts/
│   │
│   ├── replanner/                     # 重规划 Agent
│   │   ├── __init__.py
│   │   ├── node.py
│   │   ├── agent.py
│   │   └── prompts/
│   │
│   ├── field_mapper/                  # 字段映射 Agent
│   │   ├── __init__.py
│   │   ├── node.py
│   │   ├── llm_selector.py
│   │   └── prompts/
│   │
│   └── dimension_hierarchy/           # 维度层级 Agent
│       ├── __init__.py
│       ├── node.py
│       └── prompts/
│
├── nodes/                             # 非 Agent 节点（工作流中的处理节点）
│   ├── __init__.py
│   ├── query_builder/                 # 查询构建节点
│   │   ├── __init__.py
│   │   └── node.py                    # QueryBuilderNode
│   └── execute/                       # 查询执行节点
│       ├── __init__.py
│       └── node.py                    # ExecuteNode
│
├── ==================== 4. 编排层（Orchestration）====================
│   统一管理工作流编排、工具定义和中间件
│
├── orchestration/                     # 【新建】编排层统一包
│   ├── __init__.py
│   │
│   ├── workflow/                      # LangGraph 工作流编排
│   │   ├── __init__.py
│   │   ├── factory.py                 # 工作流工厂（构建 LangGraph）
│   │   ├── executor.py                # 工作流执行器
│   │   ├── context.py                 # 工作流上下文（State）
│   │   ├── routes.py                  # 路由定义（条件边）
│   │   └── printer.py                 # 输出打印
│   │
│   ├── tools/                         # LangGraph 工具定义（Agent 能力扩展）
│   │   ├── __init__.py
│   │   ├── base.py                    # 工具基类
│   │   ├── registry.py                # 工具注册表
│   │   ├── data_model_tool.py         # 数据模型查询工具
│   │   ├── date_tool.py               # 日期解析工具
│   │   └── schema_tool.py             # Schema 查询工具
│   │
│   └── middleware/                    # 中间件（横切关注点）
│       ├── __init__.py
│       ├── output_validation.py       # 输出验证
│       ├── patch_tool_calls.py        # 工具调用补丁
│       ├── filesystem.py              # 文件系统
│       └── backends/                  # 后端实现
│
├── ==================== 5. 基础设施层（Infrastructure）====================
│   为上层提供基础能力支撑：AI 模型、存储、配置、监控、异常
│
├── infra/                             # 基础设施
│   ├── __init__.py
│   │
│   ├── ai/                            # AI 模型管理
│   │   ├── __init__.py
│   │   ├── llm.py                     # LLM 客户端（统一接口）
│   │   ├── embeddings.py              # Embedding 模型
│   │   └── reranker.py                # Reranker 模型
│   │
│   ├── storage/                       # 存储管理
│   │   ├── __init__.py
│   │   ├── cache.py                   # 缓存（Redis/内存）
│   │   ├── vector_store.py            # 向量存储（Milvus/Chroma）
│   │   └── persistence.py             # 持久化（文件/数据库）
│   │
│   ├── config/                        # 配置管理
│   │   ├── __init__.py
│   │   ├── settings.py                # 应用配置
│   │   └── model_config.py            # AI 模型配置
│   │
│   ├── monitoring/                    # 监控与日志
│   │   ├── __init__.py
│   │   ├── callbacks.py               # LangGraph 回调
│   │   └── logger.py                  # 日志配置
│   │
│   ├── exceptions.py                  # 异常定义
│   │
│   └── utils/                         # 工具函数
│       ├── __init__.py
│       └── conversation.py            # 对话处理工具
│
├── ==================== 6. 服务层（API）====================
│   对外暴露的 HTTP API 接口
│
├── api/                               # HTTP API
│   ├── __init__.py
│   ├── chat.py                        # 聊天 API
│   ├── preload.py                     # 预加载 API
│   └── models.py                      # API 请求/响应模型
│
├── __init__.py
└── main.py                            # 入口
```

### 迁移说明

| 现有位置 | 迁移目标 | 说明 |
|---------|---------|------|
| `agents/understanding/` | `agents/semantic_parser/` | 重构为 LLM 组合架构 |
| `agents/insight/` + `components/insight/` | `agents/insight/components/` | 合并到一个目录 |
| `models/semantic/` | `core/models/` | 平台无关模型 |
| `models/vizql/` | `platforms/tableau/models/` | Tableau 特定模型 |
| `models/metadata/` | `core/models/data_models.py` | 重命名为数据模型 |
| `bi_platforms/tableau/` | `platforms/tableau/` | 平台实现 |
| `workflow/` | `orchestration/workflow/` | 工作流编排迁移到编排层 |
| `workflow/tools/` | `orchestration/tools/` | 工具定义迁移到编排层 |
| `middleware/` | `orchestration/middleware/` | 中间件迁移到编排层 |
| `nodes/query_builder/implementation_resolver.py` | 废弃 | 由 partition_by 抽象替代 |

## 附件列表

- [附件A：Step 1 详细设计](./appendix-a-step1-detail.md) - Prompt 设计、输入输出定义、示例
- [附件B：Step 2 详细设计](./appendix-b-step2-detail.md) - Prompt 设计、验证规则、Observer 设计、示例
- [附件C：数据模型详细定义](./appendix-c-data-models.md) - 完整的 Pydantic 模型定义
- [附件D：平台适配器设计](./appendix-d-platform-adapters.md) - Tableau/Power BI/SQL 适配器实现
- [附件E：Prompt 模板与数据模型编写指南](./appendix-e-prompt-model-guide.md) - 基于新架构的 Prompt 和 Schema 编写规范
