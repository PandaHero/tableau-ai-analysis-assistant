"""
SemanticParser Agent 数据模型包

包含 Step1、Step2、Observer、ParseResult、Pipeline 和 ReAct 相关模型。

核心层模型直接使用：
- MeasureField, DimensionField: 从 core.models.fields 导入
- Filter 及其子类: 从 core.models.filters 导入
"""

from tableau_assistant.src.agents.semantic_parser.models.step1 import (
    What,
    Where,
    Intent,
    FilterValidationCheck,
    Step1Validation,
    Step1Output,
)

from tableau_assistant.src.agents.semantic_parser.models.step2 import (
    ValidationCheck,
    Step2Validation,
    Step2Output,
)

from tableau_assistant.src.agents.semantic_parser.models.observer import (
    Conflict,
    Correction,
    Step1Correction,
    ObserverInput,
    ObserverOutput,
)

from tableau_assistant.src.agents.semantic_parser.models.parse_result import (
    ClarificationQuestion,
    SemanticParseResult,
)

from tableau_assistant.src.agents.semantic_parser.models.pipeline import (
    QueryResult,
    QueryError,
    QueryErrorType,
)

from tableau_assistant.src.agents.semantic_parser.models.react import (
    ReActThought,
    ReActAction,
    ReActActionType,
    ReActObservation,
    ReActOutput,
)


__all__ = [
    # Step1 models
    "What",
    "Where",
    "Intent",
    "FilterValidationCheck",
    "Step1Validation",
    "Step1Output",
    # Step2 models
    "ValidationCheck",
    "Step2Validation",
    "Step2Output",
    # Observer models
    "Conflict",
    "Correction",
    "Step1Correction",
    "ObserverInput",
    "ObserverOutput",
    # ParseResult models
    "ClarificationQuestion",
    "SemanticParseResult",
    # Pipeline models
    "QueryResult",
    "QueryError",
    "QueryErrorType",
    # ReAct models
    "ReActThought",
    "ReActAction",
    "ReActActionType",
    "ReActObservation",
    "ReActOutput",
]
