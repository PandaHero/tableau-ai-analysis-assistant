# 工作流各阶段数据模型

本文档描述 Tableau Assistant 工作流各阶段的输入输出数据模型。

## 工作流概览

```
用户问题 (str)
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. Understanding Agent (LLM)                                     │
│ 输入: question (str)                                             │
│ 输出: is_analysis_question (bool), SemanticQuery                │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼ (如果 is_analysis_question=True)
┌─────────────────────────────────────────────────────────────────┐
│ 2. FieldMapper Node (RAG + LLM)                                  │
│ 输入: SemanticQuery (业务术语)                                   │
│ 输出: MappedQuery (技术字段映射)                                 │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. QueryBuilder Node (纯代码)                                    │
│ 输入: MappedQuery                                                │
│ 输出: VizQLQuery                                                 │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Execute Node (纯代码)                                         │
│ 输入: VizQLQuery                                                 │
│ 输出: QueryResult                                                │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Insight Agent (LLM)                                           │
│ 输入: QueryResult                                                │
│ 输出: InsightResult                                              │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Replanner Agent (LLM)                                         │
│ 输入: InsightResult                                              │
│ 输出: ReplanDecision                                             │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼ (如果 should_replan=True)
    └──────────────────────────────────────────────────────────────┐
                                                                   │
    ┌──────────────────────────────────────────────────────────────┘
    │
    ▼
  返回 Understanding Agent (使用新问题)
```

## 各阶段数据模型详解

### 1. Understanding Agent

**输入**:
- `question: str` - 用户的自然语言问题

**输出**:
- `is_analysis_question: bool` - 是否为数据分析问题
- `semantic_query: tableau_assistant.src.models.semantic.query.SemanticQuery` - 纯语义查询（业务术语）

**SemanticQuery 模型路径**: `tableau_assistant/src/models/semantic/query.py`

```python
class SemanticQuery(BaseModel):
    measures: List[MeasureSpec]      # 度量列表
    dimensions: List[DimensionSpec]  # 维度列表
    filters: List[FilterSpec]        # 筛选条件
    analyses: List[AnalysisSpec]     # 分析规格（累计、排名等）
    output_control: OutputControl    # 输出控制
```

### 2. FieldMapper Node

**输入**:
- `semantic_query: tableau_assistant.src.models.semantic.query.SemanticQuery` - 包含业务术语的语义查询

**输出**:
- `mapped_query: tableau_assistant.src.models.semantic.query.MappedQuery` - 字段映射后的查询

**MappedQuery 模型路径**: `tableau_assistant/src/models/semantic/query.py`

```python
class MappedQuery(BaseModel):
    semantic_query: SemanticQuery           # 原始语义查询
    field_mappings: List[FieldMapping]      # 字段映射列表
    low_confidence_fields: List[str]        # 低置信度字段
    mapping_metadata: Dict[str, Any]        # 映射元数据
```

**FieldMapping 模型路径**: `tableau_assistant/src/models/semantic/query.py`

```python
class FieldMapping(BaseModel):
    business_term: str              # 业务术语
    technical_field: str            # 技术字段名
    confidence: float               # 置信度 (0-1)
    mapping_source: MappingSource   # 映射来源 (rag/llm/cache)
    alternatives: List[str]         # 备选字段
```

### 3. QueryBuilder Node

**输入**:
- `mapped_query: tableau_assistant.src.models.semantic.query.MappedQuery` - 字段映射后的查询

**输出**:
- `vizql_query: tableau_assistant.src.models.vizql.types.VizQLQuery` - VizQL 查询

**VizQLQuery 模型路径**: `tableau_assistant/src/models/vizql/types.py`

```python
class VizQLQuery(BaseModel):
    fields: List[VizQLField]                # 字段列表
    filters: List[VizQLFilter]              # 筛选条件
    calculated_fields: List[CalculationField]  # 计算字段
    table_calc_fields: List[TableCalcField]    # 表计算字段
    options: QueryOptions                   # 查询选项
```

### 4. Execute Node

**输入**:
- `vizql_query: tableau_assistant.src.models.vizql.types.VizQLQuery` - VizQL 查询

**输出**:
- `query_result: tableau_assistant.src.models.vizql.result.QueryResult` - 查询结果

**QueryResult 模型路径**: `tableau_assistant/src/models/vizql/result.py`

```python
class QueryResult(BaseModel):
    data: List[Dict[str, Any]]      # 查询数据
    columns: List[str]              # 列名列表
    row_count: int                  # 行数
    execution_time: float           # 执行时间（秒）
    error: Optional[str]            # 错误信息
```

### 5. Insight Agent

**输入**:
- `query_result: tableau_assistant.src.models.vizql.result.QueryResult` - 查询结果

**输出**:
- `insight_result: tableau_assistant.src.models.insight.models.InsightResult` - 洞察结果

**InsightResult 模型路径**: `tableau_assistant/src/models/insight/models.py`

```python
class InsightResult(BaseModel):
    # 核心输出
    summary: Optional[str]                    # 一句话总结
    findings: List[Insight]                   # 洞察列表（按重要性降序）
    confidence: float                         # 整体置信度 (0-1)
    
    # Phase 1 统计/ML 分析结果
    data_insight_profile: Optional[DataInsightProfile]  # 数据洞察画像
    
    # 分析过程信息
    strategy_used: str                        # 分析策略 (direct/progressive/hybrid)
    chunks_analyzed: int                      # 分析的数据块数
    total_rows_analyzed: int                  # 分析的总行数
    execution_time: float                     # 执行时间（秒）
    
    # 重规划相关
    need_more_data: bool                      # 是否需要更多数据
    missing_aspects: List[str]                # 缺失的分析方面
    exploration_rounds: int                   # 探索轮数
    questions_executed: int                   # 执行的问题数
```

**Insight 单个洞察结构**（分析师 LLM 输出）:

```python
class Insight(BaseModel):
    type: Literal["trend", "anomaly", "comparison", "pattern"]  # 洞察类型
    title: str                                # 洞察标题
    description: str                          # 详细描述
    importance: float                         # 重要性评分 (0-1)
    evidence: Optional[Dict[str, Any]]        # 支持证据
```

**NextBiteDecision 主持人决策**（主持人 LLM 输出）:

```python
class NextBiteDecision(BaseModel):
    should_continue: bool                     # 是否继续分析
    next_chunk_id: Optional[int]              # 下一个要分析的块 ID
    reason: str                               # 决策原因
    completeness_estimate: float              # 完成度估计 (0-1)
```

### 6. Replanner Agent

**输入**:
- `insight_result: tableau_assistant.src.models.insight.models.InsightResult` - 洞察结果

**输出**:
- `replan_decision: tableau_assistant.src.models.replanner.replan_decision.ReplanDecision` - 重规划决策

**ReplanDecision 模型路径**: `tableau_assistant/src/models/replanner/replan_decision.py`

```python
class ReplanDecision(BaseModel):
    completeness_score: float           # 完整度评分 (0-1)
    should_replan: bool                 # 是否需要重规划
    reason: str                         # 评估理由
    missing_aspects: List[str]          # 缺失的分析方面
    exploration_questions: List[ExplorationQuestion]  # 探索问题列表
    parallel_execution: bool            # 是否并行执行
    max_questions_per_round: int        # 每轮最多执行问题数
    confidence: float                   # 决策置信度
```

**ExplorationQuestion 模型路径**: `tableau_assistant/src/models/replanner/replan_decision.py`

```python
class ExplorationQuestion(BaseModel):
    question: str                       # 探索问题文本
    exploration_type: str               # 探索类型
    target_dimension: str               # 目标维度
    filter: Optional[str]               # 过滤条件
    priority: int                       # 优先级 (1-10)
    reasoning: str                      # 推理说明
```

## 工作流状态模型

**VizQLState 模型路径**: `tableau_assistant/src/models/workflow/state.py`

```python
class VizQLState(TypedDict):
    # 输入
    question: str                       # 用户问题
    
    # Understanding 输出
    is_analysis_question: bool          # 是否为分析问题
    semantic_query: Optional[SemanticQuery]  # 语义查询
    
    # FieldMapper 输出
    mapped_query: Optional[MappedQuery]      # 映射后的查询
    
    # QueryBuilder 输出
    vizql_query: Optional[VizQLQuery]        # VizQL 查询
    
    # Execute 输出
    query_result: Optional[QueryResult]      # 查询结果
    
    # Insight 输出
    insight_result: Optional[InsightResult]  # 洞察结果
    accumulated_insights: Annotated[List[Insight], operator.add]  # 累积洞察
    
    # Replanner 输出
    replan_decision: Optional[ReplanDecision]  # 重规划决策
    replan_count: int                    # 重规划次数
    
    # 错误处理
    errors: Annotated[List[str], operator.add]  # 错误列表
```

**VizQLInput 模型路径**: `tableau_assistant/src/models/workflow/state.py`

```python
class VizQLInput(BaseModel):
    question: str                       # 用户问题
    session_id: Optional[str]           # 会话 ID
    config: Optional[Dict[str, Any]]    # 配置
```

**VizQLOutput 模型路径**: `tableau_assistant/src/models/workflow/state.py`

```python
class VizQLOutput(BaseModel):
    answer: str                         # 回答
    insights: List[Insight]             # 洞察列表
    query_result: Optional[QueryResult] # 查询结果
    replan_history: List[ReplanDecision]  # 重规划历史
```

## 模型导入路径汇总

| 模型 | 完整导入路径 |
|------|-------------|
| SemanticQuery | `tableau_assistant.src.models.semantic.query.SemanticQuery` |
| MappedQuery | `tableau_assistant.src.models.semantic.query.MappedQuery` |
| FieldMapping | `tableau_assistant.src.models.semantic.query.FieldMapping` |
| VizQLQuery | `tableau_assistant.src.models.vizql.types.VizQLQuery` |
| QueryResult | `tableau_assistant.src.models.vizql.result.QueryResult` |
| InsightResult | `tableau_assistant.src.models.insight.models.InsightResult` |
| ReplanDecision | `tableau_assistant.src.models.replanner.replan_decision.ReplanDecision` |
| ExplorationQuestion | `tableau_assistant.src.models.replanner.replan_decision.ExplorationQuestion` |
| VizQLState | `tableau_assistant.src.models.workflow.state.VizQLState` |
| VizQLInput | `tableau_assistant.src.models.workflow.state.VizQLInput` |
| VizQLOutput | `tableau_assistant.src.models.workflow.state.VizQLOutput` |

## 从 models 包导入

所有模型都可以从 `tableau_assistant.src.models` 包直接导入：

```python
from tableau_assistant.src.models import (
    # Semantic
    SemanticQuery,
    MappedQuery,
    FieldMapping,
    
    # VizQL
    VizQLQuery,
    QueryResult,
    
    # Insight
    InsightResult,
    Insight,
    DataProfile,
    
    # Replanner
    ReplanDecision,
    ExplorationQuestion,
    
    # Workflow
    VizQLState,
    VizQLInput,
    VizQLOutput,
)
```
