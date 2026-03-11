# Interrupt Playbook

> Status: Draft v1.0
> Purpose: Catalog all interrupt types, triggers, payloads, and resume shapes.
> Read order: 9/12

---

## 1. datasource_disambiguation
**Trigger:** `resolve_datasource_identity` finds multiple matches.  
**Payload (system → user):**
```json
{
  "interrupt_id": "int_001",
  "interrupt_type": "datasource_disambiguation",
  "choices": [
    {"datasource_luid":"ds_1","project":"Sales","name":"Revenue"},
    {"datasource_luid":"ds_2","project":"Ops","name":"Revenue"}
  ]
}
```
**Resume (user → system):**
```json
{
  "selection_type": "datasource",
  "datasource_luid": "ds_1"
}
```

---

## 2. missing_slot
**Trigger:** `semantic_guard` detects missing timeframe or key filter.  
**Payload:**
```json
{
  "interrupt_id": "int_002",
  "interrupt_type": "missing_slot",
  "slot_name": "timeframe",
  "options": ["last_7_days","last_30_days","last_90_days"]
}
```
**Resume:**
```json
{
  "selection_type": "slot_fill",
  "slot_name": "timeframe",
  "value": "last_30_days"
}
```

---

## 3. value_confirm
**Trigger:** `semantic_guard` finds ambiguous filter values.  
**Payload:**
```json
{
  "interrupt_id": "int_004",
  "interrupt_type": "value_confirm",
  "field": "region",
  "candidates": ["华东","华南"]
}
```
**Resume:**
```json
{
  "selection_type": "value_confirm",
  "field": "region",
  "value": "华东"
}
```

---

## 4. high_risk_query_confirm
**Trigger:** `execute_tableau_query` detects high estimated scan cost before execution.  
**Payload:**
```json
{
  "interrupt_id": "int_005",
  "interrupt_type": "high_risk_query_confirm",
  "risk_level": "high",
  "estimated_rows": 5000000,
  "message": "该查询预计扫描量较大，是否继续？"
}
```
**Resume:**
```json
{
  "selection_type": "high_risk_query",
  "confirm": true
}
```

---

## 5. followup_select
**Trigger:** `followup_interrupt` emits candidates in user-select mode.  
**Payload:**
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
**Resume:**
```json
{
  "selection_type": "followup_question",
  "selected_question_id": "q1"
}
```
