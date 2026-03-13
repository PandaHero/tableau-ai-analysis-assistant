# Backend Refactor Design

> Status: Draft v1.2
> Read order: 3/14
> Upstream: [requirements.md](./requirements.md)
> Downstream: [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [node-catalog.md](./node-catalog.md), [migration.md](./migration.md), [tasks.md](./tasks.md)

## 1. 设计摘要

后端升级为“薄 API + root_graph 主干 + 横切平面（检索/记忆/新鲜度）”架构。

核心原则：

- 运行状态由 LangGraph 统一承载。
- 业务流程由确定性节点编排，LLM 仅用于语义理解与洞察生成。
- 大对象不进 state，仅保存引用（ref）。
- 业务中断统一 `interrupt/resume`，不走私有协议。

## 2. 分层架构

1. API Control Layer  
2. Graph Runtime Layer (`root_graph`)  
3. Domain Services Layer  
4. Storage & Cache Layer  
5. Artifact Layer

```text
FastAPI Router
  -> RootGraphRunner
      -> context_graph
      -> semantic_graph
      -> query_graph
      -> answer_graph
  -> Domain Services
  -> Postgres + Checkpointer + Redis + Artifact Store
```

## 3. API 层职责

API 层负责：

- HTTP 参数校验、用户鉴权、会话路由。
- 启动或恢复 graph run。
- graph 事件转 SSE。
- sessions/settings/feedback CRUD。

API 层不负责：

- 主状态机编排。
- Tableau 查询编译与执行细节。
- 洞察工具调度。

### 3.1 用户展示语义边界

流式协议内部可以同时存在两类底层输出：

- LLM token 流：用于模型逐 token 生成最终回答草稿。
- graph 业务事件流：用于节点状态、结果卡片、interrupt、replan 等业务事件。

但这两类流都不是前端的直接展示协议。展示语义必须由后端定义，前端只负责渲染，不负责猜内部状态。

约束：

- 前端不得直接把“原始 LLM token 流”和“原始 graph 节点流”作为两块裸露 UI 呈现给用户。
- 前端不得依赖内部节点名、内部路由名、内部 `thinking_token` 文本来推断展示语义。
- 后端必须把内部运行事件投影为稳定的用户可见对象，例如主回答区、活动时间线、决策卡片、结果卡片、artifact 面板。
- 普通用户默认不看原始 thinking 文本；`thinking` 只允许在调试或显式开关下暴露，常规模式必须降维成简短进度摘要。
- 任何影响用户交互决策的事件，都必须带稳定业务语义，不能把解释责任推给前端。

## 4. root_graph 设计

### 4.1 子图结构

- `context_graph`
- `semantic_graph`
- `query_graph`
- `answer_graph`

### 4.2 运行顺序

1. `ingress_validate`
2. `hydrate_business_context`
3. `resolve_tenant_context`
4. `context_graph`
5. `semantic_graph`
6. `query_graph`
7. `answer_graph`
8. `persist_run_artifacts`
9. `finalize_stream`

### 4.3 中断点

统一由 `interrupt()` 触发：

- datasource 歧义（`datasource_disambiguation`）
- 缺失槽位（`missing_slot`）
- 值确认（`value_confirm`）
- 高风险查询确认（`high_risk_query_confirm`）
- follow-up 选择（`followup_select`）

### 4.4 多问题语义边界

`root_graph` 需要明确区分两类“多个问题”：

- `analysis_plan.sub_questions`：复杂主问题内部的任务分解，属于同一轮运行内的 planner steps。
- `candidate_questions`：当前轮回答完成后的 follow-up 候选分支，属于轮与轮之间的继续分析选择。

设计约束：

- planner 路径由 `root_graph` 统一编排，但 `query_graph` 与 `answer_graph` 仍保持独立职责；不能再把复杂问题整体黑盒委托给第二个总控。
- `analysis_plan.sub_questions` 必须支持 DAG 执行模型：`depends_on` 控制先后顺序；互不依赖的 query steps 允许受控并行；`synthesis` 必须等待依赖满足。
- planner 并行只适用于“同一主问题下的证据收集步骤”，不适用于后续候选分支；并行执行必须受并发上限、step 上限和预算控制。
- `replan` 生成的 `candidate_questions` 只能形成单活跃分支：`user_select` 由用户选一个，`auto_continue` 由系统选一个；禁止把多个候选问题同时展开为搜索树。
- `replan_history` 仅用于记录 follow-up 决策历史与防环，不参与 planner 内部 DAG 依赖表达。

## 5. 子图职责

### 5.1 `context_graph`

节点：

- `resolve_tableau_auth`
- `resolve_datasource_identity`
- `load_metadata_snapshot`
- `load_ready_artifacts`

输出：

- tenant/auth 引用
- datasource identity（含 `datasource_luid` 与 `schema_hash`）
- metadata/semantic/value artifact refs

### 5.2 `semantic_graph`

节点：

- `retrieve_semantic_candidates`
- `semantic_parse`（LLM）
- `semantic_guard`

原则：

- parse 是模型能力，guard 是确定性校验。
- 不合格语义必须中断澄清，不能直接执行查询。

### 5.3 `query_graph`

节点：

- `build_query_plan`
- `execute_tableau_query`
- `normalize_result_table`
- `materialize_result_artifacts`

原则：

- 查询计划由编译器生成，禁止模型直出可执行查询。
- 结果落盘为 manifest + chunk + profile。

### 5.4 `answer_graph`

节点：

- `prepare_insight_workspace`
- `insight_generate`
- `replan_decide`
- `clarify_interrupt`

原则：

- 洞察必须文件驱动，读取受限。
- 自动重规划有上限，超限转用户选择。

## 6. 状态模型（RunState）

```text
RunState
- request: request_id, session_id, trace_id, idempotency_key, locale
- tenant: user_id, domain, site, principal, scopes, auth_ref
- conversation: latest_user_message, recent_messages_ref, session_summary_ref
- datasource: datasource_luid, project_name, schema_hash
- artifacts: metadata_snapshot_ref, field_semantic_ref, field_values_ref, result_manifest_ref
- semantic: intent, measures, dimensions, filters, timeframe, grain, confidence, ambiguity
- clarification: pending_type, interrupt_id, resume_value_ref
- query: plan_ref, retry_count, budget_ms, query_status
- result: row_count, truncated, empty_reason
- answer: answer_ref, evidence_ref, followup_ref
- ops: error_code, metrics_ref, token_usage_ref, retrieval_trace_ref, memory_write_refs
```

减重规则：

- 任何可能超过 10KB 的字段必须拆为 `*_ref`。
- state 只保留决策信号，不保留全量表数据。

## 7. 现有模块映射

| 现有模块 | 新架构定位 |
| --- | --- |
| `src/api/routers/chat.py` | 保留入口，内部改为 `RootGraphRunner` |
| `src/orchestration/workflow/executor.py` | 过渡层，逐步下线 |
| `src/agents/semantic_parser/graph.py` | 演进为 `semantic_graph` 核心 |
| `src/platform/tableau/query_builder.py` | 查询编译核心 |
| `src/platform/tableau/adapter.py` | 执行适配层 |
| `src/agents/insight/*` | 重构为文件驱动洞察 |
| `src/infra/storage/repository.py` | 仅保留业务表读写，不再承担全局运行存储 |

## 8. 横切平面与边界

- 检索平面：策略路由、rerank、trace 产出。
- 记忆平面：query cache、few-shot、value memory、synonym learning。
- 新鲜度平面：artifact readiness、degrade 策略、异步刷新。

边界规则：

- 检索/记忆只影响候选与提示，不可绕过 `semantic_guard` 与查询编译器。
- 新鲜度平面决定“可用/降级/失败”，但不直接重写业务状态机。

## 9. 展示投影层

`root_graph` 输出到 SSE 前，必须经过一层“展示投影”约束。该层不改变业务决策，只负责把内部事件归一为用户可理解的展示对象。

目标展示槽位：

- `main_answer`: 用户正在阅读的主回答正文，允许来自 LLM token 流。
- `activity_timeline`: 对当前阶段的人话描述，例如“正在理解问题”“正在执行查询”“正在生成洞察”。
- `decision_card`: 所有需要用户继续决策的 interrupt 卡片。
- `result_card`: 结构化结果卡片，例如表格、指标摘要、洞察摘要。
- `artifact_panel`: 可下载文件、workspace、manifest、证据引用等附件区域。

约束：

- `main_answer` 与 `activity_timeline` 必须分离，不能把过程描述直接混入最终答案正文。
- `decision_card` 必须来源于结构化 interrupt，不能由前端把任意错误或文本消息猜成弹窗。
- `result_card` 必须由后端携带足够的标题、摘要、引用信息；前端不负责从原始表结构二次编文案。
- 如果存在调试视图，必须与普通用户视图隔离，且不能影响正式业务事件契约。
