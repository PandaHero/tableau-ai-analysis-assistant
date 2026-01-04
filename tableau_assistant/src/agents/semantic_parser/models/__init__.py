"""SemanticParser Agent data models package.

Contains Step1, Step2, ParseResult, Pipeline and ReAct related models.

Core layer models are used directly:
- MeasureField, DimensionField: from core.models.fields
- Filter and subclasses: from core.models.filters

Note: Observer models have been removed. ReAct error handling replaces Observer.
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

from tableau_assistant.src.agents.semantic_parser.models.parse_result import (
    ClarificationQuestion,
    SemanticParseResult,
)

from tableau_assistant.src.agents.semantic_parser.models.pipeline import (
    PipelineResult,
    QueryError,
    QueryErrorType,
)

from tableau_assistant.src.agents.semantic_parser.models.react import (
    ReActActionType,
    ErrorCategory,
    CorrectionOperation,
    Correction,
    ReActThought,
    ReActAction,
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
    # ParseResult models
    "ClarificationQuestion",
    "SemanticParseResult",
    # Pipeline models
    "PipelineResult",
    "QueryError",
    "QueryErrorType",
    # ReAct models
    "ReActActionType",
    "ErrorCategory",
    "CorrectionOperation",
    "Correction",
    "ReActThought",
    "ReActAction",
    "ReActOutput",
]
