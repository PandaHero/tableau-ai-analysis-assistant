# Models Package Structure

This package contains all data models for the Tableau Assistant, organized into logical subpackages.

## Directory Structure

```
models/
├── __init__.py          # Main exports (backward compatible)
├── README.md            # This file
│
├── workflow/            # LangGraph workflow models
│   ├── __init__.py
│   ├── state.py         # VizQLState, VizQLInput, VizQLOutput
│   └── context.py       # VizQLContext runtime context
│
├── semantic/            # Pure semantic layer (no VizQL concepts) ✅ UPDATED
│   ├── __init__.py
│   ├── enums.py         # AnalysisType, ComputationScope, FilterType, etc.
│   └── query.py         # SemanticQuery, MappedQuery, FieldMapping
│
├── vizql/               # VizQL technical models
│   ├── __init__.py
│   ├── types.py         # VizQLQuery, field types, filter types
│   └── result.py        # QueryResult, ProcessingResult
│
├── common/              # Shared models
│   ├── __init__.py
│   └── errors.py        # TransientError, PermanentError, UserError
│
└── [legacy files]       # ⚠️ LEGACY - Kept for backward compatibility
    ├── api.py           # API request/response models (keep)
    ├── boost.py         # QuestionBoost (legacy, used by question_boost_agent)
    ├── data_model.py    # LogicalTable, DataModel (keep)
    ├── dimension_hierarchy.py  # DimensionHierarchyResult (keep)
    ├── field_mapping.py # Legacy FieldMapping (replaced by semantic/query.py)
    ├── insight_result.py # InsightResult (keep)
    ├── intent.py        # Legacy Intent models (replaced by semantic/query.py)
    ├── metadata.py      # FieldMetadata, Metadata (keep)
    ├── query_plan.py    # Legacy QueryPlanningResult (used by task_planner)
    ├── query_result.py  # Legacy QueryResult (used by data_processing)
    ├── question.py      # Legacy QuestionUnderstanding (used by understanding_agent)
    ├── replan_decision.py # ReplanDecision (keep)
    ├── result.py        # Insight, FinalReport (keep)
    ├── time_granularity.py # TimeGranularity enum (keep)
    └── vizql_types.py   # Legacy VizQL types (moved to vizql/)
```

## Architecture

The models follow the refactored architecture:

```
User Question
    │
    ▼
┌─────────────────────────────────────────┐
│ Understanding Agent                      │
│ Output: SemanticQuery (pure semantic)    │
│ Location: models/semantic/query.py       │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ FieldMapper Node                         │
│ Output: MappedQuery (technical fields)   │
│ Location: models/semantic/query.py       │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ QueryBuilder Node                        │
│ Output: VizQLQuery (technical query)     │
│ Location: models/vizql/types.py          │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ Execute Node                             │
│ Output: QueryResult                      │
│ Location: models/vizql/result.py         │
└─────────────────────────────────────────┘
```

## Usage

### Recommended (New Style)

```python
# Import from subpackages
from tableau_assistant.src.models.workflow import VizQLState, create_initial_state
from tableau_assistant.src.models.semantic import SemanticQuery, MappedQuery
from tableau_assistant.src.models.vizql import VizQLQuery, QueryResult
from tableau_assistant.src.models.common import TransientError, PermanentError
```

### Backward Compatible

```python
# Import from main package (still works)
from tableau_assistant.src.models import (
    VizQLState,
    SemanticQuery,
    VizQLQuery,
    TransientError,
)
```

## Key Models

### Workflow Models (`workflow/`)

- **VizQLState**: LangGraph state TypedDict with all workflow data
- **VizQLContext**: Runtime context (datasource_luid, user_id, etc.)

### Semantic Models (`semantic/`) ✅ UPDATED

按照规范文档 `.kiro/specs/agent-refactor-with-rag/design-appendix/data-models.md` 更新：

- **SemanticQuery**: Pure semantic representation of user intent
  - `measures`: List[MeasureSpec] - 度量规格
  - `dimensions`: List[DimensionSpec] - 维度规格（包含 `is_time` 字段）
  - `filters`: List[FilterSpec] - 筛选规格（使用 `FilterType` 枚举）
  - `analyses`: List[AnalysisSpec] - 分析规格
  - `output_control`: OutputControl - 输出控制

- **MappedQuery**: SemanticQuery with fields mapped to technical names
  - `semantic_query`: SemanticQuery - 原始语义查询
  - `field_mappings`: Dict[str, FieldMapping] - 字段映射
  - `overall_confidence`: float - 整体置信度

- **FieldMapping**: 单个字段的映射结果
  - `business_term`: str - 业务术语
  - `technical_field`: str - 技术字段名
  - `confidence`: float - 映射置信度
  - `mapping_source`: MappingSource - 映射来源

- **Enums**:
  - `AnalysisType`: cumulative, ranking, percentage, period_compare, moving
  - `ComputationScope`: per_group, across_all
  - `FilterType`: time_range, set, quantitative, match
  - `MappingSource`: rag_high_confidence, rag_llm_fallback, cache_hit, exact_match

### VizQL Models (`vizql/`)

- **VizQLQuery**: Technical query for VizQL Data Service API
- **QueryResult**: Query execution result with DataFrame

### Common Models (`common/`)

- **TransientError**: Retryable errors (network, rate limit)
- **PermanentError**: Non-retryable errors (auth, config)
- **UserError**: Errors requiring user action

---

## Legacy Models Migration Plan

以下遗留模型仍在被使用，需要在新架构完全实现后清理：

### 高优先级清理（新架构已有替代）

| 遗留文件 | 替代方案 | 依赖模块 | 状态 |
|---------|---------|---------|------|
| `intent.py` | `semantic/query.py` | query_plan.py, query builder | 待迁移 |
| `field_mapping.py` | `semantic/query.py` FieldMapping | prompts/field_mapping.py | 待迁移 |
| `question.py` | `semantic/query.py` SemanticQuery | understanding_agent, date_processing | 待迁移 |

### 中优先级清理（需要重构依赖模块）

| 遗留文件 | 说明 | 依赖模块 |
|---------|------|---------|
| `boost.py` | QuestionBoost 模型 | question_boost_agent |
| `query_plan.py` | QueryPlanningResult | task_planner, data_processing |
| `query_result.py` | QueryResult, ProcessingResult | data_processing |

### 保留（核心功能）

| 文件 | 说明 |
|-----|------|
| `api.py` | API 请求/响应模型 |
| `data_model.py` | 数据模型定义 |
| `dimension_hierarchy.py` | 维度层级推断 |
| `insight_result.py` | 洞察结果 |
| `metadata.py` | 元数据模型 |
| `replan_decision.py` | 重规划决策 |
| `result.py` | 最终报告模型 |
| `time_granularity.py` | 时间粒度枚举 |

---

## Design Principles

遵循 `prompt-and-schema-design.md` 中定义的设计规范：

1. **思考与填写交织**：LLM 是逐 token 生成的，每填一个字段都是一次"微型思考"
2. **XML 标签定位**：为每次微型思考提供精确的规则定位锚点
3. **`<decision_rule>` 桥梁**：将 Prompt 中的抽象思考转化为具体填写动作

字段描述格式：
- `<what>`: 字段含义
- `<when>`: 何时填写
- `<how>`: 如何填写
- `<decision_rule>`: 决策规则
- `<dependency>`: 字段依赖
- `<examples>`: 示例
- `<anti_patterns>`: 反模式
