# Interrupt Playbook

> Status: Draft v1.1
> Read order: 11/14
> Upstream: [design.md](./design.md), [data-and-api.md](./data-and-api.md), [node-catalog.md](./node-catalog.md)
> Downstream: [migration.md](./migration.md), [tasks.md](./tasks.md)

## 1. 统一规则

- 所有业务级中断都必须通过 `interrupt()` 发出。
- 所有恢复请求都必须通过 `/api/chat/resume`。
- 恢复请求必须绑定：`session_id + interrupt_id`。
- 恢复后继续运行同一 `thread_id`。

## 2. 中断类型

### 2.1 `datasource_disambiguation`

触发：`resolve_datasource_identity` 匹配到多个候选数据源。

系统 -> 用户 payload:

```json
{
  "interrupt_id": "int_001",
  "interrupt_type": "datasource_disambiguation",
  "message": "找到多个同名数据源，请选择。",
  "choices": [
    {"datasource_luid":"ds_1","project":"Sales","name":"Revenue"},
    {"datasource_luid":"ds_2","project":"Ops","name":"Revenue"}
  ]
}
```

用户 -> 系统 resume:

```json
{
  "selection_type": "datasource",
  "datasource_luid": "ds_1"
}
```

### 2.2 `missing_slot`

触发：`semantic_guard` 发现关键槽位缺失（如 timeframe）。

系统 -> 用户 payload:

```json
{
  "interrupt_id": "int_002",
  "interrupt_type": "missing_slot",
  "slot_name": "timeframe",
  "message": "缺少时间范围，请选择。",
  "options": ["last_7_days", "last_30_days", "last_90_days"]
}
```

用户 -> 系统 resume:

```json
{
  "selection_type": "slot_fill",
  "slot_name": "timeframe",
  "value": "last_30_days"
}
```

### 2.3 `value_confirm`

触发：筛选值歧义，需用户确认。

系统 -> 用户 payload:

```json
{
  "interrupt_id": "int_003",
  "interrupt_type": "value_confirm",
  "field": "region",
  "message": "检测到多个候选值，请确认。",
  "candidates": ["华东", "华南"]
}
```

用户 -> 系统 resume:

```json
{
  "selection_type": "value_confirm",
  "field": "region",
  "value": "华东"
}
```

### 2.4 `high_risk_query_confirm`

触发：查询预估扫描成本过高。

系统 -> 用户 payload:

```json
{
  "interrupt_id": "int_004",
  "interrupt_type": "high_risk_query_confirm",
  "risk_level": "high",
  "estimated_rows": 5000000,
  "message": "该查询预计扫描量较大，是否继续？"
}
```

用户 -> 系统 resume:

```json
{
  "selection_type": "high_risk_query",
  "confirm": true
}
```

### 2.5 `followup_select`

触发：`answer_graph` 在 user_select 模式下给出候选后续问题。

系统 -> 用户 payload:

```json
{
  "interrupt_id": "int_005",
  "interrupt_type": "followup_select",
  "message": "请选择后续问题。",
  "candidates": [
    {"id":"q1","question":"按产品线拆分趋势"},
    {"id":"q2","question":"按渠道拆分趋势"}
  ]
}
```

用户 -> 系统 resume:

```json
{
  "selection_type": "followup_question",
  "selected_question_id": "q1"
}
```

## 3. 恢复失败处理

- `interrupt_id` 不存在：返回 `SESSION_NOT_FOUND` 或 `INTERRUPT_NOT_FOUND`。
- `session_id` 不匹配：返回 `TENANT_AUTH_ERROR`。
- payload schema 不合法：返回 `CLIENT_VALIDATION_ERROR`。
- 中断已解决：返回 `INTERRUPT_ALREADY_RESOLVED`。
