# Backend Node Catalog (Detailed)

> Status: Draft v1.0  
> Purpose: Provide detailed node-by-node specs for the upgraded backend.  
> Read order: 7/12

This document lists every node in the upgraded backend, including:
- inputs/outputs
- state reads/writes
- side effects
- errors and retry
- interrupt behavior
- middleware/tool usage

---

## 0. API Layer (Non-Graph)

### 0.1 RequestLoggingMiddleware
**Role:** Inject `request_id/trace_id`, log latency.  
**Inputs:** HTTP request.  
**Outputs:** unchanged request.  
**Side effects:** logs only.  
**Errors:** none.  

### 0.2 ExceptionHandlers
**Role:** Map exceptions to error codes and JSON responses.  
**Inputs:** Exception.  
**Outputs:** normalized error response.  
**Side effects:** logs only.  

---

## 1. Root Graph Entry Nodes

### 1.1 ingress_validate
**Role:** Validate message schema and required fields.  
**Inputs:**  
- `messages[]`  
- `session_id`  
- `idempotency_key`  
**Outputs:** `ValidatedRequest`  
**State writes:** `request.*`  
**Errors:** `CLIENT_VALIDATION_ERROR`  
**Retry:** none  
**Interrupt:** none  

Example output:
```json
{
  "request_id": "req_123",
  "session_id": "sess_001",
  "user_message": "最近30天华东销售为何下降?"
}
```

### 1.2 hydrate_business_context
**Role:** Load session summary and settings.  
**Inputs:** `session_id`  
**Outputs:** `session_summary_ref`, `settings_ref`, `last_interrupt_ref`  
**State writes:** `conversation.*`  
**Errors:** `SESSION_NOT_FOUND`  
**Retry:** none  
**Interrupt:** none  

### 1.3 resolve_tenant_context
**Role:** Build tenant identity (domain/site/scopes).  
**Inputs:** `user_id`, auth headers  
**Outputs:** `tenant_context`  
**State writes:** `tenant.*`  
**Errors:** `TENANT_AUTH_ERROR`  
**Retry:** none  
**Interrupt:** none  

---

## 2. context_graph

### 2.1 resolve_tableau_auth
**Role:** Acquire Tableau token for tenant.  
**Inputs:** `tenant_context`  
**Outputs:** `tableau_token_ref`  
**State writes:** `tenant.auth_ref`  
**Errors:** `TABLEAU_AUTH_ERROR`  
**Retry:** yes (bounded, e.g. 1-2 times)  
**Interrupt:** none  
**Side effects:** token cache populate (Redis).  

### 2.2 resolve_datasource_identity
**Role:** Resolve a unique datasource.  
**Inputs:**  
- `datasource_luid` (preferred)  
- `datasource_name` + `project_name`  
**Outputs:** `datasource_luid`  
**State writes:** `datasource.*`  
**Errors:** `DATASOURCE_RESOLUTION_ERROR`  
**Interrupt:** `datasource_disambiguation` if multiple matches  

Interrupt payload (example):
```json
{
  "interrupt_type": "datasource_disambiguation",
  "choices": [
    {"datasource_luid":"ds_1","project":"Sales","name":"Revenue"},
    {"datasource_luid":"ds_2","project":"Ops","name":"Revenue"}
  ]
}
```

### 2.3 load_metadata_snapshot
**Role:** Load schema snapshot and schema hash.  
**Inputs:** `datasource_luid`  
**Outputs:** `metadata_snapshot_ref`, `schema_hash`  
**State writes:** `datasource.schema_hash`, `artifacts.metadata_snapshot_ref`  
**Errors:** `METADATA_NOT_READY`  
**Retry:** yes (bounded)  

### 2.4 load_ready_artifacts
**Role:** Load prebuilt field semantic/sample artifacts.  
**Inputs:** `schema_hash`  
**Outputs:** `field_semantic_ref`, `field_values_ref`  
**State writes:** `artifacts.*`  
**Errors:** `ARTIFACT_NOT_READY` (allow soft degradation)  
**Retry:** no (prefer degrade)  

---

## 3. semantic_graph

### 3.1 retrieve_semantic_candidates
**Role:** RAG-style retrieval for candidate fields.  
**Inputs:** `user_question`, `metadata_snapshot_ref`, `field_semantic_ref`  
**Outputs:** candidate fields list  
**State writes:** `semantic.candidates_ref`  
**Errors:** `FIELD_RETRIEVAL_ERROR`  
**Retry:** optional (bounded)  

### 3.2 semantic_parse (LLM)
**Role:** Convert question to structured semantics.  
**Inputs:** `user_question`, candidate fields  
**Outputs:** `SemanticOutput`  
**State writes:** `semantic.*`  
**Errors:** `SEMANTIC_PARSE_ERROR`  
**Retry:** optional via `ModelRetryMiddleware`  

Example output:
```json
{
  "intent": "trend_explain",
  "measures": ["sales"],
  "dimensions": ["region","date"],
  "filters": {"region":"East","date":"last_30_days"},
  "confidence": 0.82,
  "ambiguity": []
}
```

### 3.3 semantic_guard
**Role:** Deterministic validation and normalization.  
**Inputs:** `SemanticOutput`  
**Outputs:** `VerifiedSemanticOutput`  
**Errors:** `SEMANTIC_VALIDATION_ERROR`  
**Interrupt:**  
- `missing_slot`  
- `value_confirm`  
**Retry:** none  

---

## 4. query_graph

### 4.1 build_query_plan
**Role:** Compile verified semantics into deterministic query plan.  
**Inputs:** `VerifiedSemanticOutput`  
**Outputs:** `QueryPlan`  
**State writes:** `query.plan_ref`  
**Errors:** `QUERY_PLAN_ERROR`  

Example output:
```json
{
  "select": ["sales","date","region"],
  "filters": [{"field":"region","op":"=","value":"East"}],
  "group_by": ["date","region"],
  "timeframe": "last_30_days",
  "limit": 50000
}
```

### 4.2 execute_tableau_query
**Role:** Execute query via Tableau adapter.  
**Inputs:** `QueryPlan`  
**Outputs:** `ExecuteResult`  
**Errors:** `QUERY_EXECUTION_ERROR`, `TABLEAU_TIMEOUT`, `EMPTY_RESULT`  
**Interrupt:** `high_risk_query_confirm` (when estimated scan cost exceeds threshold)  
**Retry:** yes (bounded)  
**Side effects:** query audit log entry  

### 4.3 normalize_result_table
**Role:** Normalize types/timezone/null semantics.  
**Inputs:** `ExecuteResult`  
**Outputs:** `NormalizedTable`  
**Errors:** `NORMALIZATION_ERROR`  
**Retry:** no  

### 4.4 materialize_result_artifacts
**Role:** Persist results and compute full statistics.  
**Inputs:** `NormalizedTable`  
**Outputs:**  
- `result_manifest_ref`  
- `profiles_ref`  
- `chunks_ref`  
**Errors:** `ARTIFACT_WRITE_ERROR`  
**Side effects:** artifact store writes  

Artifacts created:
- `result_manifest.json`
- `chunks/chunk-xxxx.jsonl`
- `profiles/column_profile.json`
- `profiles/numeric_stats.json`
- `profiles/category_topk.json`
- `profiles/time_rollup_day.json`

---

## 5. answer_graph (Insight + Replan coordination)

### 5.1 prepare_insight_workspace
**Role:** Build allowlist and workspace context.  
**Inputs:** `result_manifest_ref`  
**Outputs:** `insight_workspace`  
**Errors:** `WORKSPACE_INIT_ERROR`  

### 5.2 insight_generate (ReAct loop)
**Role:** Explore artifacts and produce evidence-backed insight.  
**Inputs:** `insight_workspace`, `profiles_ref`  
**Outputs:** `InsightOutput`, optional `replan_request`, optional `followup_candidates`  
**LLM calls:** 1+ (loop)  
**Errors:** `INSIGHT_GENERATION_ERROR`  
**Tools:**  
- `list_result_files`  
- `describe_result_file`  
- `read_result_file`  
- `read_result_rows`  
- `read_spilled_artifact`  
**Middleware:**  
- `InsightFilesystemMiddleware`  
- `ModelRetryMiddleware`  
- `ToolRetryMiddleware`  
- `SummarizationMiddleware`  
- `HumanInTheLoopMiddleware` (optional tool approvals)  

Text-based ReAct fallback:
```
Thought: ...
Action: {"tool":"read_result_rows","args":{...}}
Observation: ...
```

### 5.3 replan_decide
**Role:** Deterministic gate for requery decision.  
**Inputs:** `replan_request`  
**Outputs:** `answer_with_caveat` / `replan_query` / `followup_interrupt` / `stop`  
**Errors:** `REPLAN_EXHAUSTED`  
**Side effects:** loop control to `query_graph`  

### 5.4 followup_interrupt
**Role:** Emit follow-up candidate interrupt when user selection is required.  
**Inputs:** `followup_candidates`  
**Outputs:** interrupt payload  
**Interrupt:** `followup_select`  
**Errors:** none  

---

## 6. Finalization

### 6.1 persist_run_artifacts
**Role:** Persist run summary refs.  
**Inputs:** run_id + refs  
**Errors:** `PERSIST_ERROR`  

### 6.2 finalize_stream
**Role:** Stream SSE events to user.  
**Inputs:** event stream  
**Errors:** none (best-effort)  

---

## 7. Tool Schemas (Summary)
See `middleware.md` section 6.5.1 for full examples.

---

## 8. Interrupt Payloads
See `data-and-api.md` section 6.4 for full examples.

---

## 9. Error Messages
See `data-and-api.md` section 8.1 for user-facing hints.
