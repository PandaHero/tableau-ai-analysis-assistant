# SSE Event Catalog

> Status: Draft v1.0
> Purpose: Document SSE event types and payload shapes.
> Read order: 10/12

---

## 1. status
```json
{"event":"status","stage":"semantic_parse","message":"Parsing question"}
```

## 2. parse_result
```json
{"event":"parse_result","intent":"trend_explain","confidence":0.84}
```

## 3. interrupt
```json
{"event":"interrupt","run_id":"run_001","interrupt_id":"int_002","payload":{"interrupt_type":"missing_slot","slot_name":"timeframe"}}
```

## 4. table_result
```json
{"event":"table_result","run_id":"run_001","row_count":100000,"result_manifest_ref":"..."}
```

## 5. insight
```json
{"event":"insight","summary":"华东销售下降主要由产品线A导致","evidence_refs":["profiles/time_rollup_day.json"]}
```

## 6. replan
```json
{"event":"replan","decision":"auto_continue","next_question":"华东按产品线趋势"}
```

## 7. complete
```json
{"event":"complete","run_id":"run_001"}
```

## 8. error
```json
{"event":"error","run_id":"run_001","error_code":"QUERY_EXECUTION_ERROR","message":"Tableau timeout","retryable":true}
```
