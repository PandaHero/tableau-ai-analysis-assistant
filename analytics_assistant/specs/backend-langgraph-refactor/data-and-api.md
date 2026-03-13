# Data, Cache And API Contract

> 状态: Draft v1.1
> 读取顺序: 6/14
> 上游文档: [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md)
> 下游文档: [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [insight-large-result-design.md](./insight-large-result-design.md), [migration.md](./migration.md), [tasks.md](./tasks.md)
> 关联文档: [requirements.md](./requirements.md), [interrupt-playbook.md](./interrupt-playbook.md), [sse-event-catalog.md](./sse-event-catalog.md)

## 1. 存储分层

后端存储必须拆成四层，职责不能混用：

- Postgres: 业务实体、运行记录、审计记录。
- LangGraph Checkpointer: 线程状态、节点执行快照、interrupt 恢复点。
- Redis: token/metadata/artifact ready 等高频缓存与限流状态。
- Artifact Store: 元数据快照、结果文件、统计工件、spill 文件。

## 2. Postgres 业务表

### 2.1 `chat_sessions`

建议字段：

- `id`
- `user_id`
- `site`
- `title`
- `status`
- `last_message_at`
- `created_at`
- `updated_at`

### 2.2 `chat_messages`

建议字段：

- `id`
- `session_id`
- `run_id`
- `role`
- `content`
- `model_name`
- `message_type`
- `token_usage`
- `created_at`

### 2.3 `analysis_runs`

建议字段：

- `id`
- `session_id`
- `thread_id`
- `request_id`
- `datasource_luid`
- `status`
- `started_at`
- `ended_at`
- `error_code`

### 2.4 `analysis_interrupts`

建议字段：

- `id`
- `run_id`
- `session_id`
- `interrupt_type`
- `payload_json`
- `resume_payload_json`
- `resolved_at`

### 2.5 `user_settings`

建议字段：

- `user_id`
- `site`
- `language`
- `analysis_depth`
- `default_datasource_luid`
- `show_thinking_process`
- `updated_at`

### 2.6 `message_feedback`

建议字段：

- `id`
- `message_id`
- `run_id`
- `query_id`
- `session_id`
- `user_id`
- `type`
- `reason`
- `comment`
- `created_at`

### 2.7 `query_audit_logs`

建议字段：

- `id`
- `run_id`
- `datasource_luid`
- `semantic_json`
- `query_plan_json`
- `row_count`
- `latency_ms`
- `created_at`

## 3. Checkpointer 与 Artifact

### 3.1 Checkpointer

LangGraph checkpointer 只保存：

- 线程状态
- 节点执行快照
- interrupt 恢复点

不保存：

- 结果文件本体
- 用户反馈等长期业务实体

### 3.2 Artifact Store

Artifact Store 保存：

- `metadata_snapshot`
- `field_semantic_index`
- `field_values_index`
- `result_manifest`
- `result_chunks`
- `column_profiles`
- `spilled_tool_artifacts`

建议目录约定：

```text
artifacts/
  {site}/
    {datasource_luid}/
      {schema_hash}/
        metadata/
        field-semantic/
        field-values/
    runs/
      {run_id}/
        result/
          result_manifest.json
          chunks/
          profiles/
        spill/
```

## 4. Redis 缓存设计

### 4.1 Tableau Token

缓存键：

```text
tableau:token:{domain}:{site}:{principal}:{auth_method}:{scope_hash}
```

### 4.2 Metadata

缓存键：

```text
meta:{site}:{datasource_luid}:{schema_hash}
```

### 4.3 字段值索引

缓存键：

```text
fieldvals:{site}:{datasource_luid}:{schema_hash}:{field_name}
```

### 4.4 Artifact Ready

缓存键：

```text
artifact:ready:{site}:{datasource_luid}:{schema_hash}:{artifact_type}
```

## 5. API 契约

### 5.1 `POST /api/chat/stream`

用途：

- 启动一轮新的 graph run。

输入建议：

- `session_id`
- `messages`
- `datasource_luid`
- `datasource_name`
- `project_name`
- `idempotency_key`

约束：

- 最后一条消息必须是 `user`。
- `datasource_luid` 优先级高于 `datasource_name`。
- 新请求必须进入 `root_graph`，不允许直接驱动旧 executor。

### 5.2 `POST /api/chat/resume`

用途：

- 恢复一个业务中断。

输入建议：

- `session_id`
- `interrupt_id`
- `resume_payload`

约束：

- `session_id + interrupt_id` 必须匹配当前待恢复中断。
- 该接口主语义是恢复 `interrupt`，不是断线重放事件。

### 5.3 `GET /api/sessions`

要求：

- 必须走数据库分页查询。
- 不允许全量加载后内存分页。

### 5.4 `GET/PUT /api/settings`

要求：

- 必须落正式业务表。

### 5.5 `POST /api/feedback`

要求：

- 至少绑定 `message_id + run_id`。

## 6. SSE 事件模型

版本策略：

- SSE 采用 v2 破坏式协议（统一外壳 + `data` 内嵌 payload）。
- 不要求兼容旧事件命名和旧扁平字段布局。

建议收敛为稳定业务事件：

- `status`
- `parse_result`
- `interrupt`
- `table_result`
- `insight`
- `replan`
- `complete`
- `error`

### 6.0 展示语义投影

SSE v2 是后端对前端的展示协议，不是后端内部事件总线的原样透出。后端必须负责把“LLM token 流”和“graph 业务事件流”投影成稳定的用户可见语义。

规则：

- LLM token 流只允许驱动 `main_answer` 这类主回答正文展示，不允许直接作为“过程面板”原样展示。
- graph 业务事件必须投影为人话的活动状态、决策卡片、结果卡片、artifact 面板，不允许前端根据内部节点名二次猜测。
- `thinking_token`、chain-of-thought、原始 prompt 片段默认不得直出给普通用户；若需要调试视图，必须走显式开关，且与正式 UI 语义隔离。
- 任一 SSE 事件若会被前端直接渲染，后端必须保证其用户文案、标题、摘要和交互意图稳定可用。

建议展示槽位：

- `main_answer`
- `activity_timeline`
- `decision_card`
- `result_card`
- `artifact_panel`

建议投影关系：

| SSE 事件 | 默认展示槽位 | 说明 |
| --- | --- | --- |
| `status` | `activity_timeline` | 阶段进度和短状态文案 |
| `parse_result` | `activity_timeline` | 仅显示解析结果摘要，不暴露内部 schema 细节 |
| `interrupt` | `decision_card` | 用户必须决策的卡片 |
| `table_result` | `result_card` | 表格、指标、结果摘要 |
| `insight` | `main_answer` / `result_card` | 主结论可进入正文，证据和摘要进卡片 |
| `replan` | `activity_timeline` / `decision_card` | 自动补查走进度，用户选择走卡片 |
| `complete` | 完成状态 | 不单独占主内容区 |
| `error` | 错误提示区 | 友好错误文案与重试提示 |

### 6.1 `interrupt`

字段：

- `run_id`
- `interrupt_id`
- `interrupt_type`
- `payload`

### 6.2 `table_result`

字段：

- `run_id`
- `row_count`
- `truncated`
- `result_manifest_ref`

### 6.3 `error`

字段：

- `run_id`
- `error_code`
- `message`
- `retryable`

### 6.3.1 用户展示文案约束

下列字段一旦出现在 SSE payload 中，就视为前端直接消费的展示语义，后端必须稳定产出：

- `message`
- `title`
- `summary`
- `options`
- `candidates`
- `next_question`

这些字段的生成要求：

- 必须是人话，不得泄露内部节点名、函数名、异常堆栈。
- 必须可脱离上下文阅读，不能只返回“需要确认”“继续吗”这类缺主语短句。
- 如果涉及用户操作，文案必须指出“为什么需要你确认”和“确认后会发生什么”。

## 6.4 Interrupt Payload 示例（系统 -> 用户）

### 6.4.1 datasource 歧义

```json
{
  "interrupt_id": "int_001",
  "interrupt_type": "datasource_disambiguation",
  "message": "找到多个数据源，请选择一个继续分析。",
  "choices": [
    {"datasource_luid": "ds_1", "project": "Sales", "name": "Revenue"},
    {"datasource_luid": "ds_2", "project": "Ops", "name": "Revenue"}
  ]
}
```

### 6.4.2 缺失槽位补全

```json
{
  "interrupt_id": "int_002",
  "interrupt_type": "missing_slot",
  "slot_name": "timeframe",
  "message": "缺少时间范围，请选择。",
  "options": ["last_7_days", "last_30_days", "last_90_days"]
}
```

### 6.4.3 值确认

```json
{
  "interrupt_id": "int_004",
  "interrupt_type": "value_confirm",
  "field": "region",
  "message": "检测到多个候选值，请确认。",
  "candidates": ["华东", "华南"]
}
```

### 6.4.4 高风险查询确认

```json
{
  "interrupt_id": "int_005",
  "interrupt_type": "high_risk_query_confirm",
  "message": "该查询预计扫描量较大，是否继续？",
  "risk_level": "high",
  "estimated_rows": 5000000
}
```

### 6.4.5 follow-up 选择

```json
{
  "interrupt_id": "int_003",
  "interrupt_type": "followup_select",
  "message": "是否继续补查？请选择后续问题。",
  "candidates": [
    {"id": "q1", "question": "按产品线拆分趋势"},
    {"id": "q2", "question": "按渠道拆分趋势"}
  ]
}
```

## 7. Resume Payload 形态（用户 -> 系统）

### 7.1 datasource 歧义

```json
{
  "selection_type": "datasource",
  "datasource_luid": "ds_1"
}
```

### 7.2 缺失槽位补全

```json
{
  "selection_type": "slot_fill",
  "slot_name": "timeframe",
  "value": "last_30_days"
}
```

### 7.3 值确认

```json
{
  "selection_type": "value_confirm",
  "field": "region",
  "value": "华东"
}
```

### 7.4 高风险查询确认

```json
{
  "selection_type": "high_risk_query",
  "confirm": true
}
```

### 7.5 follow-up 选择

```json
{
  "selection_type": "followup_question",
  "selected_question_id": "q1"
}
```

## 8. 错误码模型

错误码分层：

- 入口与身份层
- 语义与编译层
- 执行与结果层
- 洞察与持久化层

对外 API 的 `error_code` 必须使用稳定公共错误码；如果内部节点产生更细粒度但不稳定的运行时错误码，后端应将其映射到公共错误码，并可通过可选 `node_error_code` 保留原始值用于日志、调试与埋点。

建议核心错误码集合：

- `CLIENT_VALIDATION_ERROR`
- `SESSION_NOT_FOUND`
- `TENANT_AUTH_ERROR`
- `TABLEAU_AUTH_ERROR`
- `DATASOURCE_RESOLUTION_ERROR`
- `METADATA_NOT_READY`
- `ARTIFACT_NOT_READY`
- `FIELD_RETRIEVAL_ERROR`
- `SEMANTIC_PARSE_ERROR`
- `SEMANTIC_VALIDATION_ERROR`
- `QUERY_PLAN_ERROR`
- `QUERY_EXECUTION_ERROR`
- `TABLEAU_TIMEOUT`
- `NORMALIZATION_ERROR`
- `EMPTY_RESULT`
- `ARTIFACT_WRITE_ERROR`
- `WORKSPACE_INIT_ERROR`
- `INSIGHT_GENERATION_ERROR`
- `REPLAN_EXHAUSTED`
- `INTERRUPT_NOT_FOUND`
- `INTERRUPT_ALREADY_RESOLVED`
- `PERSIST_ERROR`

## 8.1 用户可见提示文案（建议）

| error_code | 用户提示 | 是否建议重试 |
| --- | --- | --- |
| CLIENT_VALIDATION_ERROR | 请求参数有误，请检查输入。 | 否 |
| SESSION_NOT_FOUND | 会话不存在或已过期。 | 否 |
| TENANT_AUTH_ERROR | 身份验证失败，请重新登录。 | 否 |
| TABLEAU_AUTH_ERROR | Tableau 认证失败，请稍后再试。 | 是 |
| DATASOURCE_RESOLUTION_ERROR | 无法找到或确定数据源，请选择或更换。 | 否 |
| METADATA_NOT_READY | 元数据未准备好，请稍后再试。 | 是 |
| SEMANTIC_PARSE_ERROR | 我没理解你的问题，请换个说法。 | 否 |
| SEMANTIC_VALIDATION_ERROR | 你的问题包含不一致的条件，请澄清。 | 否 |
| QUERY_EXECUTION_ERROR | 查询执行失败，请稍后重试。 | 是 |
| TABLEAU_TIMEOUT | 查询超时，请缩小范围后重试。 | 是 |
| EMPTY_RESULT | 没有查到结果，请调整条件。 | 否 |
| INSIGHT_GENERATION_ERROR | 洞察生成失败，请稍后重试。 | 是 |
| REPLAN_EXHAUSTED | 已达到补查上限，请手动确认是否继续。 | 否 |
| INTERRUPT_NOT_FOUND | 中断不存在或已过期，请重新发起分析。 | 否 |
| INTERRUPT_ALREADY_RESOLVED | 该中断已处理，无需重复提交。 | 否 |

## 9. 可观测字段

每轮运行建议统一记录：

- `request_id`
- `session_id`
- `thread_id`
- `run_id`
- `interrupt_id`
- `trace_id`
- `datasource_luid`
- `schema_hash`
- `model_name`
- `latency_ms`
- `token_usage`

## 10. 测试补全策略

建议至少覆盖：

- SSE 契约测试：验证事件类型和 payload schema。
- interrupt/resume 契约测试：覆盖 5 类 interrupt 与对应 resume payload。
- 端到端冒烟测试：覆盖 query -> insight -> follow-up 闭环。
- 性能基准测试：比较 `root_graph` 与旧 executor 的延迟和资源消耗。
- 回滚演练测试：验证灰度关闭后可退回旧路径。
