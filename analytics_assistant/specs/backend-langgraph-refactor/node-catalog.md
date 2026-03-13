# Backend Node Catalog

> Status: Draft v1.1
> Read order: 9/14
> Upstream: [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md)
> Downstream: [node-io-schemas.md](./node-io-schemas.md), [interrupt-playbook.md](./interrupt-playbook.md), [sse-event-catalog.md](./sse-event-catalog.md), [tasks.md](./tasks.md)

## 1. API 层（非图节点）

### 1.1 RequestLoggingMiddleware

- Role: 注入/透传 `request_id`，记录耗时
- Input: HTTP request
- Output: HTTP response（附 `X-Request-ID`）
- Error: none

### 1.2 ExceptionHandlers

- Role: 统一异常 -> 错误码 -> 响应体
- Input: Exception
- Output: 标准错误响应
- Error: none

## 2. root_graph 入口节点

### 2.1 `ingress_validate`

- 作用: 校验请求、提取用户问题、初始化 request context
- 关键输出: `request_id/session_id/latest_user_message`
- 可能错误: `CLIENT_VALIDATION_ERROR`
- 中断: 无

### 2.2 `hydrate_business_context`

- 作用: 读取会话摘要、用户设置、上次中断引用
- 关键输出: `session_summary_ref/settings_ref/last_interrupt_ref`
- 可能错误: `SESSION_NOT_FOUND`
- 中断: 无

### 2.3 `resolve_tenant_context`

- 作用: 解析租户身份与权限范围
- 关键输出: `tenant.domain/site/principal/scopes`
- 可能错误: `TENANT_AUTH_ERROR`
- 中断: 无

## 3. `context_graph`

### 3.1 `resolve_tableau_auth`

- 作用: 获取 Tableau token（含缓存）
- 输出: `tenant.auth_ref`
- 错误: `TABLEAU_AUTH_ERROR`
- 重试: 有界重试（建议 1-2 次）

### 3.2 `resolve_datasource_identity`

- 作用: 唯一化 datasource
- 输入优先级: `datasource_luid` > `datasource_name + project_name`
- 输出: `datasource_luid/project/schema_hash?`
- 错误: `DATASOURCE_RESOLUTION_ERROR`
- 中断: `datasource_disambiguation`

### 3.3 `load_metadata_snapshot`

- 作用: 加载 metadata snapshot 与 schema hash
- 输出: `metadata_snapshot_ref/schema_hash`
- 错误: `METADATA_NOT_READY`

### 3.4 `load_ready_artifacts`

- 作用: 加载 semantic/value artifacts + freshness report
- 输出: `field_semantic_ref/field_values_ref/freshness_ref/degrade_flags`
- 错误: `ARTIFACT_NOT_READY`（允许降级）

## 4. `semantic_graph`

### 4.1 `retrieve_semantic_candidates`

- 作用: 检索候选字段/值/few-shot
- 输出: `candidate_fields_ref/candidate_values_ref/fewshot_examples_ref/retrieval_trace_ref`
- 错误: `FIELD_RETRIEVAL_ERROR`

### 4.2 `semantic_parse`（LLM）

- 作用: 结构化语义解析（schema-first）
- 输出: `semantic.intent/measures/dimensions/filters/timeframe/grain/confidence`
- 错误: `SEMANTIC_PARSE_ERROR`

### 4.3 `semantic_guard`

- 作用: 确定性校验与补全
- 输出: `verified_semantic`
- 错误: `SEMANTIC_VALIDATION_ERROR`
- 中断: `missing_slot` / `value_confirm`

## 5. `query_graph`

### 5.1 `build_query_plan`

- 作用: 将 verified semantic 编译为确定性 query plan
- 输出: `query.plan_ref`
- 错误: `QUERY_PLAN_ERROR`

### 5.2 `execute_tableau_query`

- 作用: 执行查询
- 输出: `execute_result_ref/row_count`
- 错误: `QUERY_EXECUTION_ERROR`, `TABLEAU_TIMEOUT`, `EMPTY_RESULT`
- 中断: `high_risk_query_confirm`

### 5.3 `normalize_result_table`

- 作用: 统一数据类型、空值、时间语义
- 输出: `normalized_result_ref`
- 错误: `NORMALIZATION_ERROR`

### 5.4 `materialize_result_artifacts`

- 作用: 结果落盘并产出 manifest/chunks/profiles
- 输出: `result_manifest_ref/profiles_ref/chunks_ref`
- 错误: `ARTIFACT_WRITE_ERROR`

## 6. `answer_graph`

### 6.1 `prepare_insight_workspace`

- 作用: 构建洞察工作区与 allowlist
- 输出: `insight_workspace_ref`
- 错误: `WORKSPACE_INIT_ERROR`

### 6.2 `insight_generate`（LLM + file tools）

- 作用: 基于文件证据生成洞察
- 输出: `answer_ref/evidence_ref/replan_request?`
- 错误: `INSIGHT_GENERATION_ERROR`

### 6.3 `replan_decide`

- 作用: 决策是否补查
- 输出: `answer_with_caveat | replan_query | clarify_interrupt | stop`
- 错误: `REPLAN_EXHAUSTED`

### 6.4 `clarify_interrupt`

- 作用: 发送答案阶段澄清/选择中断
- 输出: interrupt payload
- 中断: `followup_select`

## 7. 结束节点

### 7.1 `persist_run_artifacts`

- 作用: 持久化运行摘要与引用
- 错误: `PERSIST_ERROR`

### 7.2 `finalize_stream`

- 作用: 输出 SSE 完成事件
- 错误: best effort，不影响主运行状态
