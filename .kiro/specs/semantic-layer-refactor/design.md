# 设计文档

## 概述

本设计文档描述了 Semantic Parser Agent 和语义层重构的技术实现方案。核心目标是建立一个**高度抽象、平台无关的语义层**，支持多 BI 平台（Tableau、Power BI、Superset 等），让 LLM 输出纯粹的用户意图表示，由平台适配器转换为具体平台的查询语句。

### 设计原则

1. **意图驱动**：语义层描述"用户想要什么"，而非"BI 工具怎么实现"
2. **平台无关**：核心模型不包含任何平台特定概念（如 LOD、TableCalc、DAX）
3. **两步解析**：Step 1 理解基础语义，Step 2 推理复杂计算
4. **三元模型**：所有查询都可以用 What × Where × How 描述

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

## 两步解析流程

```
用户问题 + 历史对话 + 元数据
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Step 1: 语义理解与三元组构建                                            │
│                                                                          │
│  职责:                                                                   │
│  1. 从历史对话提取已有的 What/Where/How                                  │
│  2. 从当前问题识别要修改/新增的部分                                       │
│  3. 合并为完整的三元组                                                   │
│  4. 生成语义化重述                                                       │
│                                                                          │
│  输出: What × Where × How                                                │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
    How.type == SIMPLE?
        │
    ┌───┴───┐
   Yes      No
    │       │
    ▼       ▼
  直接   ┌─────────────────────────────────────────────────────────────────┐
  构建   │  Step 2: 计算上下文推理                                          │
  查询   │                                                                  │
         │  职责:                                                           │
         │  1. 根据 How 确定计算类型                                        │
         │  2. 推断 partition_by（核心任务）                                │
         │  3. 生成完整的计算定义                                           │
         │                                                                  │
         │  输出: Target × Partition × Operation                            │
         └─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  合并为 SemanticQuery → 字段映射 → 平台适配器 → VizQL/DAX/SQL            │
└─────────────────────────────────────────────────────────────────────────┘
```

## Step 1: 语义理解与三元组构建

### 问题重述的本质

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
  
语义重述: "按省份分组，计算销售额总和，并按销售额降序排名"
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
    # 三元组
    what: What          # 目标（度量）
    where: Where        # 范围（维度 + 筛选）
    how: How            # 操作（计算意图）
    
    # 语义化重述
    semantic_restatement: str
```

### 合并规则

| 场景 | 规则 |
|------|------|
| 当前问题明确提到 | 优先使用当前问题的值 |
| 当前问题未提到 | 从历史对话继承 |
| 当前问题是修改 | 替换历史中的对应元素 |
| 当前问题是叠加 | 与历史合并 |

详细的 Prompt 设计和示例见：[附件A：Step 1 详细设计](./appendix-a-step1-detail.md)

## Step 2: 计算上下文推理

### 触发条件

```python
if step1_output.how.type != HowType.SIMPLE:
    step2_output = await step2_reasoning(step1_output)
else:
    step2_output = None  # 简单查询，跳过 Step 2
```

### 核心任务：推断 partition_by

Step 2 的核心任务是：**基于 Step 1 的三元组，推断计算的分区维度**

```python
class Computation(BaseModel):
    """通用计算定义 = 目标 × 分区 × 操作"""
    
    target: str
    """计算目标（度量字段）"""
    
    partition_by: list[str]
    """分区维度
    - [] = 全局（所有数据一起计算）
    - ["月份"] = 按月份分区
    - 视图维度全部 = 视图粒度
    """
    
    operation: Operation
    """计算操作"""
```

### 分区推断规则

| 用户表达 | partition_by | 说明 |
|---------|--------------|------|
| "排名" | [] | 默认全局排名 |
| "每月排名" | ["月份"] | 按月份分区 |
| "占全国比例" | [] | 分母是全局 |
| "占当月比例" | ["月份"] | 分母是当月 |
| "累计" | [] | 全局累计 |
| "每省累计" | ["省份"] | 按省份分区累计 |

### 计算类型与平台映射

| 计算类型 | partition_by | Tableau | Power BI | SQL |
|---------|--------------|---------|----------|-----|
| RANK | [] | RANK() Partitioning=无 | RANKX(ALL()) | RANK() OVER () |
| RANK | [月份] | RANK() Partitioning=月份 | RANKX(VALUES(月份)) | RANK() OVER (PARTITION BY 月份) |
| PERCENT | [] | PERCENT_OF_TOTAL() | DIVIDE + ALL() | SUM()/SUM() OVER () |
| RUNNING_SUM | [] | RUNNING_SUM() | CALCULATE + FILTER | SUM() OVER (ORDER BY) |
| YEAR_AGO | [省份] | LOOKUP(-1, YEAR) | SAMEPERIODLASTYEAR | LAG() OVER (PARTITION BY 省份) |

详细的 Prompt 设计和示例见：[附件B：Step 2 详细设计](./appendix-b-step2-detail.md)

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
    # 排名类
    RANK = "RANK"
    TOP_N = "TOP_N"
    
    # 累计类
    RUNNING_SUM = "RUNNING_SUM"
    RUNNING_AVG = "RUNNING_AVG"
    
    # 移动类
    MOVING_AVG = "MOVING_AVG"
    MOVING_SUM = "MOVING_SUM"
    
    # 比较类
    PERCENT = "PERCENT"
    DIFFERENCE = "DIFFERENCE"
    GROWTH_RATE = "GROWTH_RATE"
    
    # 时间比较类
    YEAR_AGO = "YEAR_AGO"
    PERIOD_AGO = "PERIOD_AGO"
    
    # 粒度类
    FIXED = "FIXED"
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
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  Step 2: 计算推理  │ ← LLM 调用（如需要）
└───────────────────┘
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

```
src/
├── core/                              # 【新建】平台无关的核心层
│   ├── __init__.py
│   ├── models/                        # 核心数据模型
│   │   ├── __init__.py
│   │   ├── enums.py                   # 公共枚举（AggregationType, ComputationType, FilterType 等）
│   │   ├── fields.py                  # DimensionField, MeasureField, Sort
│   │   ├── computations.py            # Computation（排名、累计、粒度聚合等）
│   │   ├── filters.py                 # Filter（集合、日期、数值、文本、TopN）
│   │   ├── query.py                   # SemanticQuery - 核心语义查询
│   │   ├── parse_result.py            # SemanticParseResult, Intent, ClarificationQuestion
│   │   └── errors.py                  # SemanticValidationError 等
│   │
│   ├── agents/                        # 平台无关的 Agent
│   │   ├── __init__.py
│   │   └── semantic_parser/           # 语义解析 Agent
│   │       ├── __init__.py
│   │       ├── agent.py               # SemanticParserAgent
│   │       └── prompts.py             # Prompt 模板
│   │
│   └── interfaces/                    # 抽象接口定义
│       ├── __init__.py
│       ├── platform_adapter.py        # BasePlatformAdapter 接口
│       ├── query_builder.py           # BaseQueryBuilder 接口
│       └── field_mapper.py            # BaseFieldMapper 接口
│
├── platforms/                         # 【新建】平台特定实现
│   ├── __init__.py
│   ├── base.py                        # 平台注册和工厂
│   │
│   ├── tableau/                       # Tableau 实现
│   │   ├── __init__.py
│   │   ├── adapter.py                 # TableauAdapter（实现 BasePlatformAdapter）
│   │   ├── query_builder.py           # TableauQueryBuilder（SemanticQuery → VizQL）
│   │   ├── field_mapper.py            # TableauFieldMapper（实现 BaseFieldMapper）
│   │   ├── client.py                  # VizQL API 客户端（保持现有）
│   │   └── models/                    # Tableau 特定模型
│   │       ├── __init__.py
│   │       ├── vizql_types.py         # VizQL API 类型（与 OpenAPI 对齐）
│   │       └── table_calc.py          # TableCalcSpecification, TableCalcType
│   │
│   ├── powerbi/                       # Power BI 实现（未来扩展）
│   │   └── ...
│   │
│   └── superset/                      # Superset 实现（未来扩展）
│       └── ...
│
├── agents/                            # 【保持现有】其他 Agent
│   ├── __init__.py
│   ├── base/
│   ├── field_mapper/                  # 现有 FieldMapper（可能迁移到 platforms/tableau/）
│   ├── insight/
│   ├── replanner/
│   └── understanding/                 # 旧 Understanding Agent（标记 deprecated）
│
├── api/                               # 【保持现有】API 层
│   ├── __init__.py
│   ├── chat.py
│   └── preload.py
│
├── bi_platforms/                      # 【保持现有】→ 逐步迁移到 platforms/
│   └── tableau/
│
├── capabilities/                      # 【保持现有】通用能力
│   ├── __init__.py
│   ├── data_model/
│   ├── date_processing/               # 日期验证（LLM 计算，代码验证）
│   ├── rag/                           # RAG 能力（字段映射用）
│   └── storage/
│
├── config/                            # 【保持现有】配置
│   ├── __init__.py
│   ├── model_config.py
│   └── settings.py
│
├── middleware/                        # 【保持现有】中间件
│   ├── __init__.py
│   ├── backends/
│   │   └── summarization.py           # SummarizationMiddleware（对话摘要）
│   ├── filesystem.py
│   ├── output_validation.py
│   └── patch_tool_calls.py
│
├── models/                            # 【保持现有】→ 逐步迁移到 core/models/
│   ├── __init__.py
│   ├── api/
│   ├── common/
│   ├── field_mapper/
│   ├── insight/
│   ├── metadata/
│   ├── replanner/
│   ├── semantic/                      # 旧语义模型（标记 deprecated）
│   ├── vizql/
│   └── workflow/
│
├── model_manager/                     # 【保持现有】模型管理
│   ├── __init__.py
│   ├── embeddings.py
│   ├── llm.py
│   └── reranker.py
│
├── nodes/                             # 【保持现有】工作流节点
│   ├── __init__.py
│   ├── execute/
│   └── query_builder/                 # 旧 QueryBuilder（标记 deprecated）
│
├── services/                          # 【保持现有】服务
│   ├── __init__.py
│   └── preload_service.py
│
├── tools/                             # 【保持现有】工具
│   ├── __init__.py
│   ├── base.py
│   ├── data_model_tool.py
│   ├── date_tool.py
│   ├── metadata_tool.py
│   ├── registry.py
│   └── schema_tool.py
│
├── utils/                             # 【保持现有】工具函数
│   ├── __init__.py
│   └── conversation.py                # 可能删除或内联
│
├── workflow/                          # 【保持现有】工作流
│   ├── __init__.py
│   ├── context.py
│   ├── executor.py
│   ├── factory.py                     # 需要更新以使用新架构
│   ├── printer.py
│   └── routes.py
│
├── __init__.py
├── exceptions.py
└── main.py
```

## 附件列表

- [附件A：Step 1 详细设计](./appendix-a-step1-detail.md) - Prompt 设计、输入输出定义、示例
- [附件B：Step 2 详细设计](./appendix-b-step2-detail.md) - Prompt 设计、分区推断规则、示例
- [附件C：数据模型详细定义](./appendix-c-data-models.md) - 完整的 Pydantic 模型定义
- [附件D：平台适配器设计](./appendix-d-platform-adapters.md) - Tableau/Power BI/SQL 适配器实现
