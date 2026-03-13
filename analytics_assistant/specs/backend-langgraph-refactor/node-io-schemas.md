# Node IO Schemas (Examples)

> Status: Draft v1.1
> Purpose: Concrete IO payload examples for root/context/semantic/query/answer nodes.
> Read order: 10/14
> Upstream: [node-catalog.md](./node-catalog.md), [data-and-api.md](./data-and-api.md)
> Downstream: [interrupt-playbook.md](./interrupt-playbook.md), [tasks.md](./tasks.md)

---

## 1. Root Entry Nodes

### 1.1 ingress_validate
**Input (request):**
```json
{
  "session_id": "sess_001",
  "messages": [{"role":"user","content":"最近30天华东销售为何下降?"}],
  "idempotency_key": "idp_123"
}
```
**Output:**
```json
{
  "request_id": "req_123",
  "session_id": "sess_001",
  "user_message": "最近30天华东销售为何下降?"
}
```

### 1.2 hydrate_business_context
**Output:**
```json
{
  "session_summary_ref": "summaries/sess_001.json",
  "settings_ref": "settings/user_12.json",
  "last_interrupt_ref": null
}
```

### 1.3 resolve_tenant_context
**Output:**
```json
{
  "tenant": {
    "domain": "example.tableau.com",
    "site": "sales",
    "principal": "alice@example.com",
    "scopes": ["read:datasource","read:metadata"]
  }
}
```

---

## 2. context_graph

### 2.1 resolve_tableau_auth
**Output:**
```json
{
  "tableau_token_ref": "token_cache/tableau:token:example.tableau.com:sales:alice@example.com:pat:scope_5f2a"
}
```

### 2.2 resolve_datasource_identity
**Output:**
```json
{
  "datasource_luid": "ds_123"
}
```

### 2.3 load_metadata_snapshot
**Output:**
```json
{
  "metadata_snapshot_ref": "artifacts/sales/ds_123/schema_abc/metadata/snapshot.json",
  "schema_hash": "schema_abc"
}
```

### 2.4 load_ready_artifacts
**Output:**
```json
{
  "field_semantic_ref": "artifacts/sales/ds_123/schema_abc/field-semantic/index.json",
  "field_values_ref": "artifacts/sales/ds_123/schema_abc/field-values/index.json"
}
```

---

## 3. semantic_graph

### 3.1 retrieve_semantic_candidates
**Output:**
```json
{
  "candidate_fields": {
    "measures": ["sales", "profit"],
    "dimensions": ["region", "date", "product"],
    "time_fields": ["order_date"]
  }
}
```

### 3.2 semantic_parse (LLM)
**Output:**
```json
{
  "intent": "trend_explain",
  "measures": ["sales"],
  "dimensions": ["region","date"],
  "filters": {"region":"华东"},
  "timeframe": "last_30_days",
  "grain": "day",
  "confidence": 0.84,
  "ambiguity": []
}
```

### 3.3 semantic_guard
**Output (verified):**
```json
{
  "verified": true,
  "semantic": {
    "intent": "trend_explain",
    "measures": ["sales"],
    "dimensions": ["region","date"],
    "filters": {"region":"华东"},
    "timeframe": "last_30_days",
    "grain": "day"
  }
}
```

**Output (interrupt):**
```json
{
  "interrupt_type": "missing_slot",
  "slot_name": "timeframe",
  "options": ["last_7_days","last_30_days","last_90_days"]
}
```

---

## 4. query_graph

### 4.1 build_query_plan
**Output:**
```json
{
  "select": ["sales","date","region"],
  "filters": [{"field":"region","op":"=","value":"华东"}],
  "group_by": ["date","region"],
  "timeframe": "last_30_days",
  "limit": 50000
}
```

### 4.2 execute_tableau_query
**Output:**
```json
{
  "row_count": 100000,
  "data_preview": "omitted"
}
```

**Output (interrupt):**
```json
{
  "interrupt_type": "high_risk_query_confirm",
  "risk_level": "high",
  "estimated_rows": 5000000
}
```

### 4.3 normalize_result_table
**Output:**
```json
{
  "normalized": true,
  "row_count": 100000
}
```

### 4.4 materialize_result_artifacts
**Output:**
```json
{
  "result_manifest_ref": "artifacts/runs/run_001/result/result_manifest.json",
  "profiles_ref": "artifacts/runs/run_001/result/profiles/",
  "chunks_ref": "artifacts/runs/run_001/result/chunks/"
}
```

---

## 5. answer_graph (Insight + Replan coordination)

### 5.1 prepare_insight_workspace
**Output:**
```json
{
  "workspace_id": "ws_001",
  "artifact_root": "artifacts/runs/run_001/result/",
  "allowed_files": ["result_manifest.json","profiles/*","chunks/*"]
}
```

### 5.2 insight_generate (ReAct)
**Output:**
```json
{
  "summary": "华东销售下降主要发生在最近10天，产品线A贡献下降最大。",
  "findings": [
    {"type":"trend","evidence":"profiles/time_rollup_day.json"},
    {"type":"segment","evidence":"profiles/category_topk.json"}
  ],
  "replan_request": {
    "reason": "结果不足以支撑细分趋势结论",
    "adjustments": {"group_by": ["product_line"], "grain": "day"}
  },
  "followup_candidates": [
    {"id":"q1","question":"按产品线拆分趋势"},
    {"id":"q2","question":"按渠道拆分趋势"}
  ]
}
```

### 5.3 replan_decide
**Output (replan_query):**
```json
{
  "decision": "replan_query",
  "next_query_constraints": {
    "group_by": ["product_line"],
    "timeframe": "last_30_days"
  }
}
```

**Output (answer_with_caveat):**
```json
{
  "decision": "answer_with_caveat",
  "caveat": "当前结果缺少产品线维度，结论可信度有限。"
}
```

**Output (clarify_interrupt):**
```json
{
  "decision": "clarify_interrupt",
  "interrupt_type": "followup_select",
  "reason": "需要用户选择下一步分析方向。"
}
```

### 5.4 clarify_interrupt
**Output (interrupt):**
```json
{
  "interrupt_id": "int_003",
  "interrupt_type": "followup_select",
  "candidates": [
    {"id":"q1","question":"按产品线拆分趋势"},
    {"id":"q2","question":"按渠道拆分趋势"}
  ]
}
```

---

## 6. Finalization

### 6.1 persist_run_artifacts
**Output:**
```json
{
  "run_id": "run_001",
  "persisted": true
}
```

### 6.2 finalize_stream
**Output:**
```json
{"event":"complete","run_id":"run_001"}
```
