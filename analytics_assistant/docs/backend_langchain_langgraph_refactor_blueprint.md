# Analytics Assistant Backend Refactor Blueprint

> Version: v1.0
> Date: 2026-03-09
> Scope: `analytics_assistant/src` backend
> Target: Backend refactor and upgrade plan based on LangChain + LangGraph
> Nature: Architecture blueprint, no code changes

---

## 1. Document Purpose

This document is a delivery-grade backend blueprint for the current Analytics Assistant project.

It has three goals:

1. Re-audit the current backend by capability instead of only by file.
2. Define a concrete target backend architecture based on LangChain and LangGraph.
3. Provide a migration roadmap that can be used directly for technical review, task breakdown, and implementation planning.

This is not a framework advocacy document. The design is anchored to the current codebase, current functional boundaries, and current operational risks.

---

## 2. Executive Summary

The current backend already has the key raw materials of a usable AI analytics service:

- FastAPI entry layer
- SSE streaming chat
- Session, settings, and feedback APIs
- A LangGraph-based semantic parser subgraph
- Tableau metadata loading and query execution
- RAG indexing for field retrieval
- Insight and replanner agents
- A configurable model management layer

The main problem is not missing features. The main problem is that the system boundary is split across too many layers:

- API layer knows too much about workflow execution
- `WorkflowExecutor` acts as a god object
- Tableau integration mixes identity, datasource resolution, metadata loading, artifact preparation, and online execution
- LangGraph is used locally, but not as the end-to-end runtime backbone
- Business storage, runtime state, and cache state are not clearly separated

As a result, the backend currently suffers from five structural weaknesses:

1. Tenant and datasource identity boundaries are not strict enough.
2. Runtime state is fragmented across API, executor, graph state, and persistence.
3. Online request path does too much preparation work.
4. Error semantics are too fuzzy in several places.
5. Human-in-the-loop is only partially modeled with LangGraph interrupt/resume.

If I were rebuilding this backend for the same product, I would keep a large portion of the existing domain logic, but I would reorganize the backend around one LangGraph root graph with durable checkpoints, explicit state domains, strict datasource identity, and a thinner FastAPI control plane.

---

## 3. Current Backend Capability Audit

This section reviews the current backend by functional capability, not by package tree only.

### 3.1 API Entry, Middleware, and HTTP Boundary

Relevant files:

- `analytics_assistant/src/api/main.py`
- `analytics_assistant/src/api/middleware.py`
- `analytics_assistant/src/api/routers/chat.py`
- `analytics_assistant/src/api/models/chat.py`

Current implementation:

- FastAPI serves REST endpoints and SSE chat stream.
- Middleware injects `request_id`, logs request summary, and wraps global exceptions.
- The chat stream endpoint truncates history, creates `WorkflowExecutor`, and relays SSE events with heartbeat.

Current strengths:

- Clear entrypoint and router structure.
- Request logging and request ID already exist.
- Heartbeat support is present for SSE.

Current problems:

- The chat route is not just an HTTP adapter. It also participates in workflow setup.
- `ChatRequest` does not fully express runtime invariants. For example, "last message must be from user" is not enforced at schema level.
- The route still assumes "the final user question is `messages[-1].content`" rather than formalizing "resume" and "new turn" as distinct request modes.
- The API boundary is too thin in some places and too thick in others:
  - too thin for request contract
  - too thick for runtime orchestration

Refactor conclusion:

- Keep FastAPI.
- Keep SSE or add WebSocket only if needed later.
- Move all runtime orchestration out of router code.
- Split "start run" and "resume interrupt" into separate API contracts.

### 3.2 Authentication and Tenant Isolation

Relevant files:

- `analytics_assistant/src/api/dependencies.py`
- `analytics_assistant/src/platform/tableau/auth.py`

Current implementation:

- API user identity is derived from `Authorization` and `X-Tableau-Username`.
- Tableau auth supports JWT and PAT.
- Tableau token is cached in process memory.

Current strengths:

- There is already a concept of application identity and Tableau upstream auth.
- Token refresh semantics exist.

Current problems:

- API identity and Tableau upstream identity are not unified into one tenant context.
- Tableau token cache key is still effectively too coarse.
- Cache expiry is locally estimated instead of being modeled as a proper runtime auth artifact with tenant dimensions.
- The design still assumes a mostly single-site or low-complexity deployment.

Refactor conclusion:

- Introduce a first-class `TenantContext`.
- Every runtime must carry:
  - user identity
  - site
  - domain
  - auth method
  - scopes
  - upstream auth handle reference
- Token cache key must include tenant dimensions, not just domain.

### 3.3 Session, Settings, and Feedback

Relevant files:

- `analytics_assistant/src/api/routers/sessions.py`
- `analytics_assistant/src/api/routers/settings.py`
- `analytics_assistant/src/api/routers/feedback.py`
- `analytics_assistant/src/infra/storage/repository.py`
- `analytics_assistant/src/infra/storage/store_factory.py`

Current implementation:

- Sessions, settings, and feedback are stored through a generic `BaseRepository` built on LangGraph `BaseStore`.
- Session pagination is done by loading all rows for a user, sorting in memory, and slicing.

Current strengths:

- API surface is simple.
- Multi-namespace repository abstraction exists.
- Low implementation complexity for MVP.

Current problems:

- A generic KV-style repository is being used as business persistence.
- Storage exception semantics are too weak.
- Pagination is not database-native.
- Repository lifecycle and store lifecycle are not cleanly synchronized.
- Feedback is not strongly tied to run-level artifacts such as `run_id`, `query_id`, or `trace_id`.

Refactor conclusion:

- Move business entities to a real application database layer, preferably Postgres.
- Keep LangGraph persistence for workflow runtime only.
- Split session, message, run, interrupt, and feedback into explicit business tables.

### 3.4 Workflow Orchestration

Relevant files:

- `analytics_assistant/src/orchestration/workflow/executor.py`
- `analytics_assistant/src/orchestration/workflow/context.py`
- `analytics_assistant/src/orchestration/workflow/callbacks.py`
- `analytics_assistant/src/orchestration/workflow/history.py`

Current implementation:

- `WorkflowExecutor` authenticates, loads data model, prepares context, runs semantic parser, executes query, runs insight agent, runs replanner, and emits SSE events.
- `WorkflowContext` carries auth, datasource, data model, field semantic, field samples, platform adapter, schema hash, and helper methods.

Current strengths:

- A single workflow object makes the current runtime easy to follow initially.
- The context object already centralizes some of the right dependencies.
- There is already some concept of metrics and stage timing.

Current problems:

- `WorkflowExecutor` is too large and too central.
- Runtime state is spread between:
  - request payload
  - executor local variables
  - `WorkflowContext`
  - semantic graph state
  - repository and session state
  - SSE event queue
- SSE callback translation duplicates functionality LangGraph already exposes through stream modes.
- The current runtime model is difficult to checkpoint end-to-end.

Refactor conclusion:

- Replace `WorkflowExecutor` with a LangGraph root graph runner.
- Keep `WorkflowContext` ideas, but shrink it into:
  - immutable runtime references
  - tenant context
  - datasource context
  - artifact references

### 3.5 Semantic Parsing

Relevant files:

- `analytics_assistant/src/agents/semantic_parser/graph.py`
- `analytics_assistant/src/agents/semantic_parser/state.py`
- `analytics_assistant/src/agents/semantic_parser/routes.py`
- `analytics_assistant/src/agents/semantic_parser/nodes/*`

Current implementation:

- The semantic parser is already implemented as a LangGraph subgraph.
- It includes intent routing, cache lookup, retrieval, prompt preparation, semantic understanding, output validation, filter validation, query adaptation, error correction, and feedback learning.
- Filter value confirmation already uses `interrupt()`.

Current strengths:

- This is the strongest architectural piece in the current backend.
- The graph already captures real state transitions.
- Validation and clarification are not purely free-form.
- The state is mostly JSON-serializable, which aligns with checkpointing principles.

Current problems:

- The semantic graph is only one local runtime fragment, not the system runtime backbone.
- State is too broad and mixes public runtime state with internal node scratch space.
- Some graph branches still terminate by returning to executor-centric logic instead of living entirely within a durable root graph.
- Structured output is still partly implemented by custom schema prompting rather than fully leveraging LangChain native strategies.

Refactor conclusion:

- Keep the semantic graph concept.
- Narrow its state.
- Reattach it as a formal child graph under a root graph.
- Expand interrupt usage beyond filter confirmation.

### 3.6 Tableau Integration

Relevant files:

- `analytics_assistant/src/platform/tableau/auth.py`
- `analytics_assistant/src/platform/tableau/client.py`
- `analytics_assistant/src/platform/tableau/data_loader.py`
- `analytics_assistant/src/platform/tableau/adapter.py`
- `analytics_assistant/src/platform/tableau/query_builder.py`

Current implementation:

- `auth.py` handles Tableau signin.
- `client.py` handles VizQL, GraphQL, and datasource lookup.
- `data_loader.py` loads datasource metadata, field samples, field semantic, and indexes.
- `adapter.py` converts semantic output to execution.
- `query_builder.py` converts semantic output into Tableau VizQL payloads.

Current strengths:

- The query builder and adapter capture valuable domain knowledge and should not be discarded.
- Metadata loading is rich.
- The project already supports both VizQL and GraphQL metadata flows.

Current problems:

- Too many responsibilities live inside `data_loader.py`.
- Datasource identity resolution is not strict enough for production-grade tenant isolation.
- Online request path still tries to restore or create too many artifacts opportunistically.
- Tableau capability is not expressed as a small set of stable domain services.

Refactor conclusion:

- Collapse Tableau integration to three domain services:
  - `resolve_datasource`
  - `load_metadata_snapshot`
  - `query_datasource`
- Keep current query builder logic as the deterministic execution compiler.
- Move artifact preparation to background jobs.

### 3.7 Model Management and LangChain Integration

Relevant files:

- `analytics_assistant/src/infra/ai/model_manager.py`
- `analytics_assistant/src/infra/ai/model_router.py`
- `analytics_assistant/src/infra/ai/model_factory.py`
- `analytics_assistant/src/infra/ai/model_persistence.py`
- `analytics_assistant/src/agents/base/node.py`
- `analytics_assistant/src/agents/base/middleware_runner.py`

Current implementation:

- ModelManager supports model registry, persistence, task routing, and instance creation.
- LangChain chat model instances are created through a factory.
- Structured outputs are currently enforced through prompt injection and partial JSON parsing.
- Middleware support exists for model and tool retries and summarization.

Current strengths:

- Configurable multi-model routing already exists.
- LangChain abstraction is already in the project.
- Middleware concepts are already understood by the codebase.

Current problems:

- API key persistence boundary is too risky.
- Runtime structured output path is more custom than necessary.
- Model routing, persistence, and runtime policy need stronger separation.
- Not every LLM-invoking node should manually own streaming and schema enforcement logic.

Refactor conclusion:

- Keep ModelManager and ModelFactory ideas.
- Tighten persistence security.
- Standardize structured output around LangChain strategies.
- Push LLM node policy into reusable graph node helpers.

### 3.8 RAG and Indexing

Relevant files:

- `analytics_assistant/src/infra/rag/service.py`
- `analytics_assistant/src/infra/rag/index_manager.py`
- `analytics_assistant/src/infra/rag/retrieval_service.py`
- parts of `analytics_assistant/src/platform/tableau/data_loader.py`

Current implementation:

- RAG service is a singleton entrypoint for embedding, indexing, and retrieval.
- Indexes are used for field retrieval and artifact reuse.

Current strengths:

- Indexing and retrieval are already treated as reusable infrastructure.
- Artifact reuse exists.

Current problems:

- RAG is still too application-process-centric.
- Index lifecycle is mixed with online request behavior.
- Artifact readiness is not modeled as a first-class runtime concept.

Refactor conclusion:

- Keep RAG retrieval in online path.
- Move index creation, semantic enrichment, and sample acquisition to offline or prewarm flows.
- Partition all artifacts by tenant and schema identity.

### 3.9 Insight and Replanning

Relevant files:

- `analytics_assistant/src/agents/insight/graph.py`
- `analytics_assistant/src/agents/replanner/graph.py`

Current implementation:

- Insight uses a tool-using loop with LangChain middleware.
- Replanner uses structured output to decide next analysis direction.

Current strengths:

- Both functions already exist as conceptually separate capabilities.
- Replanner is already structured and not purely free-form.

Current problems:

- They live downstream of the executor instead of inside a unified runtime graph.
- Replanner output is still coupled to a custom candidate question event protocol.
- Human choice of next question should be an interrupt/resume branch, not just a front-end selection convention.

Refactor conclusion:

- Keep both capabilities.
- Move them into the root graph tail.
- Make follow-up selection a native interrupt branch.

---

## 4. Refactor Goals

The backend refactor should achieve the following:

1. Use LangGraph as the end-to-end runtime backbone.
2. Keep FastAPI thin and predictable.
3. Keep Tableau execution deterministic and auditable.
4. Keep LLM usage narrow, explicit, and structured.
5. Separate workflow runtime persistence from business persistence.
6. Treat tenant identity, datasource identity, and schema identity as first-class.
7. Support durable interrupt/resume for clarification and follow-up selection.
8. Remove heavy online preparation from the hot path.
9. Make errors precise enough for observability and safe enough for external exposure.

---

## 5. Target Architecture

### 5.1 Top-Level Shape

The target backend should have five major layers:

1. `API Control Plane`
2. `LangGraph Runtime Plane`
3. `Domain Services Plane`
4. `Persistence and Cache Plane`
5. `Artifact and Index Plane`

### 5.2 Layer Responsibilities

| Layer | Responsibility | What it must not do |
|---|---|---|
| API Control Plane | auth, request validation, stream bridge, CRUD APIs | own workflow orchestration |
| LangGraph Runtime Plane | root graph, child graphs, state transitions, interrupts, checkpoints, streaming | become a business database |
| Domain Services Plane | datasource resolution, metadata access, query compilation, query execution, answer assembly | manage HTTP transport directly |
| Persistence and Cache Plane | business storage, runtime checkpoints, cache, audit logs | hide failures as empty results |
| Artifact and Index Plane | field samples, field semantic, schema snapshots, vector indexes | run heavy rebuilds by default in hot path |

### 5.3 Recommended Package Layout

Recommended target package layout:

```text
analytics_assistant/src/
  api/
    routers/
    models/
    transport/
  graphs/
    root_graph.py
    state.py
    subgraphs/
      context_graph.py
      semantic_graph.py
      query_graph.py
      answer_graph.py
  domain/
    tenant/
    datasource/
    semantic/
    query/
    answer/
    errors/
  integrations/
    tableau/
      auth_service.py
      datasource_service.py
      metadata_service.py
      query_service.py
  persistence/
    postgres/
    checkpoints/
    cache/
    repositories/
  artifacts/
    indexing/
    snapshots/
  observability/
    logging.py
    metrics.py
    tracing.py
```

This is not a cosmetic rename. The goal is to align packages with runtime responsibilities.

---

## 6. LangGraph Runtime Design

### 6.1 Root Graph

There should be one root graph per conversational runtime.

Key design:

- `thread_id = session_id`
- graph input = validated turn request
- graph output = final answer or interrupt payload
- graph persistence = durable checkpoint store

The root graph owns:

- turn execution
- clarification suspension
- follow-up selection suspension
- retry boundaries
- resumability
- state evolution

### 6.2 Child Graphs

The root graph should call four child graphs:

1. `context_graph`
2. `semantic_graph`
3. `query_graph`
4. `answer_graph`

#### `context_graph`

Responsibilities:

- hydrate business context
- resolve tenant auth context
- resolve datasource identity
- load metadata snapshot
- load ready artifacts

#### `semantic_graph`

Responsibilities:

- candidate retrieval
- semantic parse
- semantic validation
- clarification preparation
- clarification interrupt

#### `query_graph`

Responsibilities:

- deterministic query plan
- Tableau execution
- result normalization
- query-level error classification

#### `answer_graph`

Responsibilities:

- answer generation
- insight assembly
- replan decision
- follow-up interrupt when needed
- artifact persistence

---

## 7. Detailed Node Blueprint

The following nodes are the recommended end-to-end runtime.

### 7.1 Ingress and Context Nodes

| Node | Type | Input | Output | Failure mode |
|---|---|---|---|---|
| `ingress_validate` | deterministic | raw HTTP request model | validated run request | 4xx |
| `hydrate_business_context` | deterministic | session_id, user_id | session, settings, and history summary | `SESSION_NOT_FOUND`, `SETTINGS_LOAD_ERROR` |
| `resolve_tenant_context` | deterministic | API identity, config | tenant context | `TENANT_AUTH_ERROR` |
| `resolve_tableau_auth` | deterministic | tenant context | auth handle ref | `TABLEAU_AUTH_ERROR` |
| `resolve_datasource_identity` | deterministic | datasource selector | datasource identity | interrupt or `DATASOURCE_RESOLUTION_ERROR` |
| `load_metadata_snapshot` | deterministic | datasource identity | metadata snapshot ref, schema_hash | `METADATA_LOAD_ERROR` |
| `load_ready_artifacts` | deterministic | schema_hash, datasource_luid | artifact refs and readiness flags | warning, not hard failure by default |

### 7.2 Semantic Nodes

| Node | Type | Input | Output | Failure mode |
|---|---|---|---|---|
| `retrieve_semantic_candidates` | deterministic | question, artifact refs | field and value candidates | degraded mode allowed |
| `semantic_parse` | LLM structured | question, metadata hints, candidates | semantic output | `SEMANTIC_PARSE_ERROR` |
| `semantic_guard` | deterministic | semantic output, metadata | validated semantic output or clarification request | `SEMANTIC_VALIDATION_ERROR` or interrupt |
| `clarification_interrupt` | LangGraph interrupt | clarification payload | suspended run | resumes on user payload |

### 7.3 Query Nodes

| Node | Type | Input | Output | Failure mode |
|---|---|---|---|---|
| `build_query_plan` | deterministic | validated semantic output | query plan | `QUERY_PLAN_ERROR` |
| `execute_tableau_query` | deterministic IO | query plan, auth handle | raw result | `QUERY_EXECUTION_ERROR`, `TABLEAU_TIMEOUT`, `TABLEAU_PERMISSION_ERROR` |
| `normalize_result_table` | deterministic | raw result, metadata snapshot | normalized table ref, row count, profile | `RESULT_NORMALIZATION_ERROR` |

### 7.4 Answer Nodes

| Node | Type | Input | Output | Failure mode |
|---|---|---|---|---|
| `insight_generate` | LLM structured | semantic output, normalized result, metadata hints | answer, evidence, caveats, and followups | `INSIGHT_GENERATION_ERROR` |
| `replan_decide` | deterministic or LLM structured | result profile, answer payload, run history | stop, auto_continue, or user_select decision | `REPLAN_DECISION_ERROR` |
| `followup_interrupt` | LangGraph interrupt | follow-up candidates | suspended run | resumes on user selection |
| `persist_run_artifacts` | deterministic | run state summary | audit and persistence writes | `RUN_PERSISTENCE_ERROR` |
| `finalize_stream` | deterministic | final state | stream completion event | N/A |

### 7.5 Important Design Rules

- `semantic_parse` and `insight_generate` are the primary LLM nodes.
- `replan_decide` can be LLM-backed, but should be schema-first and bounded.
- Everything that can be deterministic should stay deterministic.
- Query execution must never be delegated to free-form LLM generation.

---

## 8. State Model

### 8.1 Root State

```text
RootRunState
- request_state
- tenant_state
- conversation_state
- datasource_state
- artifact_state
- semantic_state
- clarification_state
- query_state
- result_state
- answer_state
- ops_state
```

### 8.2 State Domains

#### `request_state`

- `request_id`
- `session_id`
- `trace_id`
- `idempotency_key`
- `turn_id`
- `locale`

#### `tenant_state`

- `user_id`
- `tableau_username`
- `domain`
- `site`
- `scopes`
- `auth_method`
- `auth_handle_ref`

#### `conversation_state`

- `latest_user_message`
- `recent_messages`
- `conversation_summary`
- `analysis_depth`
- `replan_mode`

#### `datasource_state`

- `datasource_selector`
- `datasource_luid`
- `datasource_name`
- `project_name`
- `schema_hash`
- `visibility_scope`

#### `artifact_state`

- `metadata_snapshot_ref`
- `field_samples_ref`
- `field_semantic_ref`
- `rag_index_ref`
- `artifacts_ready`

#### `semantic_state`

- `intent`
- `measures`
- `dimensions`
- `filters`
- `timeframe`
- `grain`
- `sort`
- `ambiguity_reason`
- `confidence`

#### `clarification_state`

- `pending`
- `interrupt_type`
- `interrupt_payload`
- `resume_payload`

#### `query_state`

- `query_plan`
- `retry_count`
- `execution_budget_ms`
- `query_status`
- `query_id`

#### `result_state`

- `table_ref`
- `result_profile_ref`
- `row_count`
- `truncated`
- `empty_reason`

#### `answer_state`

- `answer_text`
- `evidence`
- `caveats`
- `suggested_followups`

#### `ops_state`

- `warnings`
- `error_code`
- `metrics`
- `token_usage`
- `audit_ref`

### 8.3 State Design Rules

State should store:

- IDs
- refs
- summaries
- compact structured outputs

State should not store:

- large metadata blobs
- full table payloads unless small
- duplicated session history copies
- raw secret material

This is one of the key corrections to the current semantic parser state design.

---

## 9. LangChain Design

### 9.1 Role of LangChain

LangChain should be used for:

- model instance abstraction
- structured output
- tool binding where needed
- middleware where needed
- provider switching

LangChain should not be used as:

- the global workflow engine
- the source of truth for business persistence
- the place to hide runtime state transitions

### 9.2 Structured Output Strategy

Target policy:

1. Prefer provider-native structured output when the model supports it.
2. Otherwise use tool strategy.
3. Only keep prompt-injected schema fallback as a compatibility escape hatch.

Recommended structured outputs:

- `SemanticParseOutput`
- `ClarificationRequest`
- `InsightOutput`
- `ReplanDecision`
- `FollowupSelectionRequest`

### 9.3 Middleware Policy

Keep middleware only where it adds value:

- model retry
- summarization for long tool loops
- tool retry for safe read-only tools

Do not treat middleware as the main orchestration mechanism.

---

## 10. Tableau Domain Service Design

### 10.1 `resolve_datasource`

Input priority:

1. `datasource_luid`
2. `site + project_name + exact datasource_name`

Allowed outcomes:

- exact resolution
- no match
- multi match

Disallowed production behavior:

- prefix auto-bind
- fuzzy auto-bind
- first-hit return from unordered full datasource scans

If no exact resolution is possible, the runtime should raise an interrupt for datasource selection.

### 10.2 `load_metadata_snapshot`

Responsibilities:

- load datasource fields and metadata
- build or retrieve `schema_hash`
- return a snapshot reference
- attach snapshot freshness metadata

It should not:

- force online artifact rebuilding by default
- fetch huge derived artifacts synchronously unless explicitly requested

### 10.3 `query_datasource`

Responsibilities:

- execute deterministic VizQL request
- classify upstream errors
- return raw result plus execution metadata

It should not:

- accept arbitrary free-form LLM-generated queries without validation
- hide upstream execution failure as an empty result

### 10.4 `normalize_result_table`

This should be a domain-level normalization step with explicit handling of:

- column type
- dimension vs measure
- time columns and timezone semantics
- null handling
- truncation
- row limits
- execution notes

---

## 11. Artifact and Index Design

### 11.1 Artifact Types

Recommended artifact types:

- metadata snapshot
- schema hash registry
- field sample values
- field semantic attributes
- field alias index
- retrieval index

### 11.2 Partitioning Key

Artifacts should be partitioned by:

```text
{site}:{datasource_luid}:{schema_hash}
```

This avoids stale cross-schema reuse and tenant leakage.

### 11.3 Online vs Offline Boundary

Online path may:

- read artifact readiness
- use ready artifacts
- degrade gracefully if artifact is absent

Offline or background path should:

- build field samples
- infer field semantic
- build or refresh retrieval indexes
- reconcile schema changes

### 11.4 Degradation Policy

If artifacts are not ready:

- semantic retrieval quality may degrade
- query execution should still be possible if metadata is available
- the runtime must record a warning
- the system must never silently bootstrap unbounded heavy jobs in the hot path

---

## 12. Business Persistence Design

### 12.1 Recommended Tables

#### `chat_sessions`

- `id`
- `user_id`
- `site`
- `title`
- `status`
- `last_message_at`
- `created_at`
- `updated_at`

#### `chat_messages`

- `id`
- `session_id`
- `run_id`
- `role`
- `content`
- `message_type`
- `created_at`

#### `analysis_runs`

- `id`
- `session_id`
- `thread_id`
- `request_id`
- `datasource_luid`
- `status`
- `started_at`
- `ended_at`
- `error_code`

#### `analysis_interrupts`

- `id`
- `run_id`
- `interrupt_type`
- `payload_json`
- `resume_payload_json`
- `resolved_at`

#### `user_settings`

- `user_id`
- `site`
- `language`
- `analysis_depth`
- `default_datasource_luid`
- `show_thinking_process`
- `updated_at`

#### `message_feedback`

- `id`
- `message_id`
- `run_id`
- `query_id`
- `user_id`
- `feedback_type`
- `reason`
- `comment`
- `created_at`

#### `tableau_metadata_snapshots`

- `site`
- `datasource_luid`
- `schema_hash`
- `artifact_uri`
- `refreshed_at`

#### `query_audit_logs`

- `run_id`
- `query_id`
- `datasource_luid`
- `semantic_json`
- `query_plan_json`
- `row_count`
- `latency_ms`
- `created_at`

### 12.2 Persistence Split

Recommended split:

- Business entities -> Postgres
- Workflow checkpoints -> LangGraph checkpointer
- Short-lived cache -> Redis
- Large artifacts -> object store or vector store

This split is deliberate:

- business data needs queryability, migrations, and auditability
- workflow runtime needs resumability
- cache needs TTL and speed
- artifacts need independent lifecycle management

---

## 13. Cache Design

### 13.1 Token Cache

Recommended key:

```text
tableau:token:{domain}:{site}:{principal}:{auth_method}:{scope_hash}
```

### 13.2 Metadata Cache

Recommended key:

```text
tableau:metadata:{site}:{datasource_luid}:{schema_hash}
```

### 13.3 Field Value Cache

Recommended key:

```text
tableau:fieldvals:{site}:{datasource_luid}:{field_name}
```

### 13.4 Runtime Safeguards

- bound memory usage
- explicit TTLs
- no ambiguous cache keys
- cache misses must not silently mutate business semantics

---

## 14. API Contract Redesign

### 14.1 Start Stream

`POST /api/chat/stream`

Purpose:

- start a new normal analysis turn

Recommended input:

```json
{
  "session_id": "string",
  "messages": [
    {"role": "user", "content": "..."}
  ],
  "datasource_luid": "optional-string",
  "datasource_name": "optional-string",
  "project_name": "optional-string",
  "language": "zh",
  "analysis_depth": "detailed",
  "replan_mode": "user_select",
  "idempotency_key": "optional-string"
}
```

Validation rules:

- `messages` must not be empty
- last message must be `user`
- `datasource_luid` is preferred over `datasource_name`

### 14.2 Resume Interrupt

`POST /api/chat/resume`

Purpose:

- resume a suspended graph execution

Recommended input:

```json
{
  "session_id": "string",
  "interrupt_id": "string",
  "resume_payload": {
    "type": "followup_selection",
    "selection": "..."
  }
}
```

### 14.3 SSE Event Contract

Recommended event types:

- `status`
- `parse_result`
- `interrupt`
- `table_result`
- `insight`
- `replan`
- `complete`
- `error`

The payload should be structured and stable. Avoid event shapes that depend on executor internals.

---

## 15. Interrupt and Human-in-the-Loop Design

### 15.1 Interrupt Types

Recommended interrupt types:

- `datasource_disambiguation`
- `filter_value_confirmation`
- `missing_slot_fill`
- `followup_selection`

### 15.2 Why Interrupt Should Be Native

The current project already uses `interrupt()` in one narrow branch.

That should be expanded because interrupt/resume is the correct model for:

- user clarification
- user disambiguation
- user follow-up selection
- cross-process resumability
- explicit run suspension

### 15.3 Resume Payload Requirements

Every interrupt payload should be:

- typed
- JSON-serializable
- resumable without reconstructing hidden executor context

---

## 16. Streaming Design

### 16.1 Current Issue

The current runtime uses a custom event queue and callback bridge.

This works, but it duplicates graph-runtime semantics and introduces backpressure concerns.

### 16.2 Target Design

Use LangGraph streaming modes:

- `messages` for model token stream
- `updates` for state transition events
- `custom` for domain events

Recommended mapping:

| Stream mode | Usage |
|---|---|
| `messages` | token streaming from LLM nodes |
| `updates` | node status and state transitions |
| `custom` | parse result, interrupt payload, normalized table summary, replan result |

### 16.3 API Bridge

FastAPI transport layer should only:

- subscribe to graph stream
- translate internal events to SSE
- attach `request_id` and `trace_id`

It should not invent additional runtime semantics.

---

## 17. Error Model and Observability

### 17.1 Error Taxonomy

Recommended public and internal error split:

| Public code | Meaning |
|---|---|
| `CLIENT_VALIDATION_ERROR` | request invalid |
| `TENANT_AUTH_ERROR` | application identity invalid |
| `TABLEAU_AUTH_ERROR` | upstream Tableau auth failed |
| `DATASOURCE_RESOLUTION_ERROR` | datasource cannot be uniquely resolved |
| `METADATA_LOAD_ERROR` | metadata cannot be loaded |
| `SEMANTIC_PARSE_ERROR` | model output invalid |
| `SEMANTIC_VALIDATION_ERROR` | parsed request invalid against metadata |
| `QUERY_EXECUTION_ERROR` | upstream query failed |
| `EMPTY_RESULT` | valid execution but no data |
| `INSIGHT_GENERATION_ERROR` | answer generation failed |
| `RUN_PERSISTENCE_ERROR` | artifact persistence failed |

### 17.2 Logging

Every run should be log-correlated by:

- `request_id`
- `trace_id`
- `session_id`
- `thread_id`
- `run_id`
- `query_id`

### 17.3 Metrics

Recommended metrics:

- run latency
- semantic parse latency
- query execution latency
- insight generation latency
- interrupt count
- empty result rate
- Tableau auth failure rate
- token usage by node

### 17.4 Tracing

Recommended tracing:

- LangSmith for graph and model traces
- application traces for API and database calls
- audit logs for datasource, query plan, and result summary

---

## 18. Security Design

### 18.1 Hard Rules

- never auto-bind datasource by fuzzy match in production path
- never store raw API keys if encryption guarantees are not satisfied
- never expose raw upstream secrets or file paths in user-facing errors
- never let cache keys omit tenant dimensions
- never let empty results mask execution failures

### 18.2 Secret Handling

Preferred strategy:

- environment or secret manager as source of truth
- encrypted references only if persistence is required
- no plaintext fallback for persisted model secrets

### 18.3 Tenant Boundary

Tenant boundary must include:

- application identity
- Tableau site
- datasource identity
- artifact partition
- cache partition
- audit partition

---

## 19. Migration Plan

### Phase 0: Stabilize Boundaries

Goal:

- make the current system observable and safe enough to migrate

Deliverables:

- unified run IDs and error codes
- strict datasource identity policy
- strict token cache key policy
- storage error classification

Acceptance criteria:

- no datasource ambiguity in production path
- no token collision across sites or principals
- no empty-result masking of upstream failures

### Phase 1: Introduce Root Graph Skeleton

Goal:

- introduce `root_graph` without breaking current API

Deliverables:

- root graph shell
- checkpointer integration
- compatibility API adapter

Acceptance criteria:

- `/api/chat/stream` still works for current frontend contract
- runtime has `thread_id = session_id`

### Phase 2: Migrate Semantic Runtime

Goal:

- move semantic parse and clarification fully under graph control

Deliverables:

- semantic child graph attached to root
- interrupt and resume for clarification
- narrowed semantic state

Acceptance criteria:

- clarification can be resumed after process restart
- semantic parse contract test suite passes

### Phase 3: Migrate Query Runtime

Goal:

- make query execution deterministic inside `query_graph`

Deliverables:

- query plan node
- Tableau execution node
- result normalization node

Acceptance criteria:

- permission failure, timeout, and empty result are distinct outcomes
- normalized result schema is stable

### Phase 4: Migrate Answer and Replan Runtime

Goal:

- move insight and replanning into `answer_graph`

Deliverables:

- structured insight node
- structured replanner node
- follow-up interrupt flow

Acceptance criteria:

- follow-up selection is no longer a custom executor protocol
- candidate follow-ups can be resumed via interrupt

### Phase 5: Migrate Business Persistence

Goal:

- move business entities off generic BaseStore persistence

Deliverables:

- Postgres business repositories
- session, message, run, and interrupt tables
- feedback linkage to run, query, and message

Acceptance criteria:

- pagination is database-native
- repository failures no longer masquerade as not-found

### Phase 6: Retire Legacy Executor

Goal:

- remove `WorkflowExecutor` from the main runtime path

Deliverables:

- graph-native runtime bridge
- removal of executor-specific event logic from hot path

Acceptance criteria:

- no production route depends on executor-centric orchestration

---

## 20. Testing Strategy

### 20.1 Contract Tests

Each important node should have contract tests for:

- input validation
- output schema
- failure classification
- state mutation

### 20.2 Graph Tests

Graph-level tests should cover:

- normal one-turn run
- clarification interrupt and resume
- datasource disambiguation interrupt and resume
- follow-up selection interrupt and resume
- retry and timeout boundaries

### 20.3 Integration Tests

Integration tests should cover:

- API to graph bridge
- graph to Tableau read-only service
- graph persistence and resume
- session, run, and feedback persistence

### 20.4 Regression Focus

High-priority regression focus:

- same datasource names under different projects
- multi-site token isolation
- schema change handling
- empty result semantics
- candidate follow-up selection semantics

---

## 21. What Should Be Reused vs Rewritten

### Reuse with Refactor

- Tableau query builder domain logic
- Tableau adapter deterministic execution path
- semantic parser node concepts
- model manager and model factory ideas
- insight and replanner capability split

### Keep as Compatibility Layer Only

- current chat SSE route shape
- current callback event bridge
- current selected-candidate-question compatibility behavior

### Rewrite or Split

- `WorkflowExecutor`
- datasource lookup semantics
- online artifact preparation path
- generic repository as primary business storage

---

## 22. Implementation Principles If This Were a New Project

If I were building the same backend from scratch on LangChain and LangGraph, I would follow these hard rules:

1. Only two core LLM reasoning stages in the hot path:
   - semantic parse
   - answer generation
2. All execution semantics stay deterministic.
3. All clarification is interrupt and resume based.
4. All runtime state is checkpointable.
5. All business data lives outside the workflow state store.
6. All tenant-sensitive caches include tenant identity.
7. No fuzzy datasource binding in production execution.
8. No heavy artifact generation by default in online requests.

---

## 23. Recommended Review Questions

This document should be reviewed with the following questions:

1. Is `session_id = thread_id` acceptable for the product's conversation model?
2. Should datasource selection move fully to frontend, or should backend still support exact-name fallback?
3. What is the expected SLA for metadata freshness versus online latency?
4. Which artifact types are mandatory online, and which can be degraded?
5. Is Postgres acceptable as the business persistence source of truth?
6. Should follow-up selection always be human-driven, or do some product modes require auto-continue?

---

## 24. Official Framework References

These references are the framework anchors for the target design:

- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- LangGraph subgraphs: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph human-in-the-loop: https://docs.langchain.com/oss/python/langgraph/human-in-the-loop
- LangGraph streaming: https://docs.langchain.com/oss/python/langgraph/streaming
- LangChain structured output: https://docs.langchain.com/oss/python/langchain/structured-output

---

## 25. Final Recommendation

The current backend should not continue to grow around `WorkflowExecutor`.

The correct next step is not "incrementally optimize the executor" but "promote LangGraph from local semantic graph to global runtime spine".

That shift allows the backend to gain, in one consistent move:

- durable runtime state
- native human-in-the-loop
- clearer error boundaries
- thinner API layer
- stricter tenant isolation
- cleaner persistence separation
- better observability
- lower long-term complexity

This is the refactor direction that best fits the current codebase, current feature set, and current operational risks.
