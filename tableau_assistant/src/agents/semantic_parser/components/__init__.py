"""Semantic Parser Agent components.

Internal components for the LangGraph Subgraph architecture:
- Step1Component: Semantic understanding and question restatement
- Step2Component: Computation reasoning and self-validation
- QueryPipeline: Core query execution pipeline (MapFields → BuildQuery → ExecuteQuery)
- ReActErrorHandler: Error analysis and recovery for QueryPipeline
- IntentRouter: Two-phase intent routing (L0 rules, L1 classifier, L2 fallback)
- SchemaLinking: Schema linking with fallback path (Requirements 0.13)
- PreprocessComponent: Preprocessing layer (0 LLM calls) - normalize, time extraction, slots

Note: 
- Observer has been removed. ReAct error handling replaces Observer.
- DecisionHandler has been removed. LangGraph node routing loop in subgraph.py
  handles the orchestration of QueryPipeline with ReAct error handling.
- Node functions (step1_node, step2_node, pipeline_node, react_error_handler_node,
  intent_router_node, preprocess_node) are defined in subgraph.py for the LangGraph node routing loop.
"""

from .step1 import Step1Component
from .step2 import Step2Component
from .query_pipeline import QueryPipeline
from .react_error_handler import ReActErrorHandler, RetryRecord
from .intent_router import IntentRouter, IntentType, IntentRouterOutput
from .schema_linking import (
    BatchEmbeddingConfig,
    BatchEmbeddingOptimizer,
    COMPUTATION_WORDS,
    FieldCandidate,
    SchemaCandidates,

    SchemaLinking,
    SchemaLinkingComponent,
    SchemaLinkingComponentConfig,
    SchemaLinkingConfig,
    SchemaLinkingFallbackReason,
    SchemaLinkingResult,
    ScoringWeights,
    STOPWORDS,
    TIME_WORDS,
    TermExtractor,
    TermExtractorConfig,
)


from .preprocess import (
    PreprocessComponent,
    PreprocessResult,
    TimeContext,
    MemorySlots,
    TimeGrain,
)

__all__ = [
    "BatchEmbeddingConfig",
    "BatchEmbeddingOptimizer",
    "COMPUTATION_WORDS",
    "FieldCandidate",
    "IntentRouter",


    "IntentRouterOutput",

    "IntentType",
    "MemorySlots",
    "PreprocessComponent",
    "PreprocessResult",
    "QueryPipeline",
    "ReActErrorHandler",
    "RetryRecord",
    "SchemaCandidates",
    "SchemaLinking",
    "SchemaLinkingComponent",
    "SchemaLinkingComponentConfig",
    "SchemaLinkingConfig",
    "SchemaLinkingFallbackReason",
    "SchemaLinkingResult",
    "ScoringWeights",
    "STOPWORDS",
    "Step1Component",
    "Step2Component",
    "TIME_WORDS",
    "TermExtractor",
    "TermExtractorConfig",
    "TimeContext",
    "TimeGrain",
]
