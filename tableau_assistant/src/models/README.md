# Models Package Structure

This package contains all data models for the Tableau Assistant, organized by workflow stage.

## Directory Structure

```
models/
├── __init__.py          # Main exports (backward compatible)
├── README.md            # This file
│
├── workflow/            # LangGraph workflow models
│   ├── state.py         # VizQLState, VizQLInput, VizQLOutput
│   └── context.py       # VizQLContext runtime context
│
├── semantic/            # Understanding Agent → FieldMapper
│   ├── enums.py         # AnalysisType, ComputationScope, FilterType, etc.
│   └── query.py         # SemanticQuery, MappedQuery, FieldMapping
│
├── vizql/               # QueryBuilder → Execute
│   ├── types.py         # VizQLQuery, field types, filter types
│   └── result.py        # QueryResult
│
├── question/            # Understanding Agent
│   ├── question.py      # QuestionUnderstanding, TimeRange
│   └── time_granularity.py # TimeGranularity enum
│
├── insight/             # Insight Agent
│   ├── result.py        # Legacy insight models (FinalReport, etc.)
│   └── models.py        # Progressive insight models (InsightResult, etc.)
│
├── replanner/           # Replanner Agent
│   └── replan_decision.py # ReplanDecision, ExplorationQuestion
│
├── metadata/            # Metadata related
│   ├── metadata.py      # FieldMetadata, Metadata
│   ├── data_model.py    # LogicalTable, DataModel
│   └── dimension_hierarchy.py # DimensionHierarchyResult
│
├── api/                 # API request/response
│   └── models.py        # VizQLQueryRequest, VizQLQueryResponse, etc.
│
└── common/              # Shared models
    └── errors.py        # TransientError, PermanentError, UserError
```

## Workflow Mapping

```
User Question
    │
    ▼
┌─────────────────────────────────────────┐
│ Understanding Agent                      │
│ Input: question (str)                    │
│ Output: SemanticQuery                    │
│ Models: question/, semantic/             │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ FieldMapper Node                         │
│ Input: SemanticQuery                     │
│ Output: MappedQuery                      │
│ Models: semantic/                        │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ QueryBuilder Node                        │
│ Input: MappedQuery                       │
│ Output: VizQLQuery                       │
│ Models: vizql/                           │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ Execute Node                             │
│ Input: VizQLQuery                        │
│ Output: QueryResult                      │
│ Models: vizql/                           │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ Insight Agent                            │
│ Input: QueryResult                       │
│ Output: InsightResult                    │
│ Models: insight/                         │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ Replanner Agent                          │
│ Input: InsightResult                     │
│ Output: ReplanDecision                   │
│ Models: replanner/                       │
└─────────────────────────────────────────┘
```

## Usage

```python
# Import from subpackages (recommended)
from tableau_assistant.src.models.semantic import SemanticQuery, MappedQuery
from tableau_assistant.src.models.vizql import VizQLQuery, QueryResult
from tableau_assistant.src.models.insight import InsightResult
from tableau_assistant.src.models.replanner import ReplanDecision

# Import from main package (backward compatible)
from tableau_assistant.src.models import (
    SemanticQuery,
    VizQLQuery,
    InsightResult,
    ReplanDecision,
)
```
