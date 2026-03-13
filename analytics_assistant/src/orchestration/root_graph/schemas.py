from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def _normalize_session_id(session_id: Optional[str]) -> str:
    normalized = str(session_id or "").strip()
    if normalized:
        return normalized
    return f"sess_{uuid4().hex[:12]}"


class RootGraphRequest(BaseModel):
    """Stable API-to-runtime contract for root_graph ingress."""

    request_id: str
    session_id: str
    thread_id: Optional[str] = None
    user_id: str
    latest_user_message: str
    recent_messages: list[dict[str, str]] = Field(default_factory=list)
    datasource_luid: Optional[str] = None
    datasource_name: Optional[str] = None
    project_name: Optional[str] = None
    locale: str = "zh"
    analysis_depth: str = "detailed"
    replan_mode: str = "user_select"
    selected_candidate_question: Optional[str] = None
    feature_flags: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_contract(self) -> "RootGraphRequest":
        self.session_id = _normalize_session_id(self.session_id)
        self.thread_id = self.session_id

        if not self.latest_user_message.strip():
            raise ValueError("latest_user_message must not be empty")
        if not self.datasource_luid and not self.datasource_name:
            raise ValueError("datasource_luid or datasource_name is required")

        return self

    def to_executor_kwargs(self) -> dict[str, Any]:
        return {
            "question": self.latest_user_message,
            "datasource_name": self.datasource_name,
            "datasource_luid": self.datasource_luid,
            "project_name": self.project_name,
            "history": self.recent_messages,
            "language": self.locale,
            "analysis_depth": self.analysis_depth,
            "replan_mode": self.replan_mode,
            "selected_candidate_question": self.selected_candidate_question,
            "feature_flags": dict(self.feature_flags),
            "session_id": self.session_id,
        }


class RequestState(BaseModel):
    request_id: str
    session_id: str
    thread_id: str
    locale: str = "zh"
    feature_flags: dict[str, bool] = Field(default_factory=dict)


class TenantState(BaseModel):
    user_id: str
    auth_ref: Optional[str] = None


class ConversationState(BaseModel):
    latest_user_message: str
    recent_messages_ref: Optional[str] = None
    session_summary_ref: Optional[str] = None


class DatasourceState(BaseModel):
    datasource_luid: Optional[str] = None
    datasource_name: Optional[str] = None
    project_name: Optional[str] = None
    schema_hash: Optional[str] = None


class ArtifactState(BaseModel):
    metadata_snapshot_ref: Optional[str] = None
    field_semantic_ref: Optional[str] = None
    field_values_ref: Optional[str] = None
    candidate_fields_ref: Optional[str] = None
    candidate_values_ref: Optional[str] = None
    fewshot_examples_ref: Optional[str] = None
    result_manifest_ref: Optional[str] = None


class SemanticState(BaseModel):
    intent: Optional[str] = None
    confidence: Optional[float] = None


class ClarificationState(BaseModel):
    pending_type: Optional[str] = None
    interrupt_id: Optional[str] = None
    resume_value_ref: Optional[str] = None


class QueryState(BaseModel):
    plan_ref: Optional[str] = None
    retry_count: int = 0
    query_status: Optional[str] = None


class ResultState(BaseModel):
    row_count: Optional[int] = None
    truncated: Optional[bool] = None
    empty_reason: Optional[str] = None


class AnswerState(BaseModel):
    answer_ref: Optional[str] = None
    evidence_ref: Optional[str] = None
    followup_ref: Optional[str] = None


class OpsState(BaseModel):
    error_code: Optional[str] = None
    metrics_ref: Optional[str] = None
    token_usage_ref: Optional[str] = None
    retrieval_trace_ref: Optional[str] = None
    memory_write_refs: list[str] = Field(default_factory=list)


class RunState(BaseModel):
    """Minimal state contract for the root_graph transition layer."""

    request: RequestState
    tenant: TenantState
    conversation: ConversationState
    datasource: DatasourceState
    artifacts: ArtifactState = Field(default_factory=ArtifactState)
    semantic: SemanticState = Field(default_factory=SemanticState)
    clarification: ClarificationState = Field(default_factory=ClarificationState)
    query: QueryState = Field(default_factory=QueryState)
    result: ResultState = Field(default_factory=ResultState)
    answer: AnswerState = Field(default_factory=AnswerState)
    ops: OpsState = Field(default_factory=OpsState)
