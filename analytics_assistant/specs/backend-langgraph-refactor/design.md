# Backend Refactor Design

> 状态: Draft v1.0
> 读取顺序: 3/12
> 上游文档: [requirements.md](./requirements.md)
> 下游文档: [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [migration.md](./migration.md)
> 关联文档: [tasks.md](./tasks.md)

## 1. 设计摘要

新的后端设计采用五层结构：

1. FastAPI 控制层
2. LangGraph 运行层
3. 领域服务层
4. 存储与缓存层
5. Artifact 与索引层

核心原则是：

- 用 LangGraph 统一运行状态。
- 用确定性节点承载业务逻辑。
- 用 LangChain 仅承载模型接入与结构化输出。
- 用结果文件中间件承载大结果洞察。

## 2. 当前功能点复审

| 功能点 | 当前主要模块 | 当前问题 | 新设计结论 |
| --- | --- | --- | --- |
| 聊天入口 | `src/api/routers/chat.py` | 路由层知道过多编排细节 | 保留为薄控制层，内部改为 graph runner |
| 请求日志与异常 | `src/api/middleware.py` | 能力可用，但错误分层不足 | 保留请求日志，错误码单独建模 |
| 鉴权与租户隔离 | `src/api/dependencies.py`, `src/platform/tableau/auth.py` | API 身份和 Tableau 身份未统一成租户上下文 | 新增统一 tenant context |
| 会话/设置/反馈 | `src/api/routers/sessions.py`, `settings.py`, `feedback.py` | 更像 KV 存档，不是正式业务层 | 迁移到正式业务表 |
| 工作流编排 | `src/orchestration/workflow/executor.py` | 总控过重 | 逐步退役，由 `root_graph` 接管 |
| 语义解析 | `src/agents/semantic_parser/graph.py` | 方向正确但只是局部子图 | 升级为 `semantic_graph` |
| Tableau 集成 | `src/platform/tableau/*.py` | 认证、解析、元数据、执行耦合过深 | 收敛为只读领域服务 |
| 洞察 | `src/agents/insight/*` | 当前为摘要驱动 + 伪文件模式 | 重构为文件驱动洞察 |
| 重规划 | `src/agents/replanner/*` | 与前端事件协议耦合太深 | 统一改为 interrupt/resume |
| 存储与缓存 | `src/infra/storage/*` | repository 同时当业务库和运行库 | 拆分业务表、checkpoint、Redis、artifact store |

## 3. 总体架构

```text
API Control Layer
  -> Root Graph Runtime
     -> Context Graph
     -> Semantic Graph
     -> Query Graph
     -> Answer Graph
  -> Domain Services
  -> Postgres / Checkpointer / Redis / Artifact Store
```

### 3.1 API 控制层职责

负责：

- HTTP 请求校验
- 用户鉴权
- 启动或恢复 graph
- graph stream 到 SSE / WebSocket 的转换
- 会话、设置、反馈 CRUD

不负责：

- 工作流主状态机
- Tableau 查询编译
- 洞察工具调度

### 3.2 LangGraph 运行层职责

负责：

- `thread_id = session_id`
- checkpoint
- subgraph 组合
- `interrupt/resume`
- 流式事件输出
- 运行状态聚合

不负责：

- 长期业务数据存储
- 大文件物理持久化

## 4. Root Graph 设计

### 4.1 根图结构

`root_graph` 包含四个子图：

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

统一使用 LangGraph `interrupt()` 处理：

- datasource 歧义
- 缺失筛选槽位
- 筛选值歧义确认（`value_confirm`）
- 候选 follow-up 问题选择
- 可能的高风险查询确认（`high_risk_query_confirm`）

说明：

- 这里说的“统一”是指业务级中断语义统一落在 `interrupt/resume` 上。
- 如果某些工具调用需要审批，可以在节点内部叠加 `HumanInTheLoopMiddleware`。
- 但 `HumanInTheLoopMiddleware` 不能替代业务级状态恢复协议。

## 5. 子图详细设计

### 5.1 `context_graph`

节点：

- `load_runtime_context`
- `resolve_tableau_auth`
- `resolve_datasource_identity`
- `load_metadata_snapshot`
- `load_ready_artifacts`

输出：

- tenant context
- datasource identity
- metadata/artifact refs

### 5.2 `semantic_graph`

节点：

- `retrieve_semantic_candidates`
- `semantic_parse`
- `semantic_guard`
- `clarification_interrupt`

实现原则：

- `semantic_parse` 是 LLM 节点。
- `semantic_guard` 是确定性校验节点。
- 结构化输出必须是 schema-first。

### 5.3 `query_graph`

节点：

- `build_query_plan`
- `execute_tableau_query`
- `normalize_result_table`
- `materialize_result_artifacts`

实现原则：

- 查询计划由编译器生成，不由 LLM 直接生成。
- `normalize_result_table` 负责把原始结果转换成统一表结构。
- `materialize_result_artifacts` 负责把结果落盘为只读 artifact，供后续洞察使用。

### 5.4 `answer_graph`

节点：

- `prepare_insight_workspace`
- `insight_generate`
- `replan_decide`
- `followup_interrupt`

实现原则：

- `insight_generate` 不再依赖压缩摘要作为唯一入口。
- 洞察阶段通过文件工具探索结果文件。
- `replan_decide` 最多允许一次低风险自动重规划，其余走用户选择。

## 6. 状态模型

```text
RunState
- request: request_id, session_id, trace_id, idempotency_key, locale
- tenant: user_id, domain, site, principal, scopes, auth_ref
- conversation: latest_user_message, recent_messages, session_summary
- datasource: selector, datasource_luid, project_name, schema_hash, visibility_scope
- artifacts: metadata_ref, field_semantic_ref, field_values_ref, result_manifest_ref
- semantic: intent, measures, dimensions, filters, timeframe, grain, ambiguity, confidence
- clarification: pending_type, interrupt_payload, resume_value
- query: plan, retry_count, budget_ms, query_status
- result: table_profile_ref, result_file_ref, row_count, empty_reason, truncated
- answer: answer_text, evidence, caveats, followups
- ops: warnings, error_code, metrics, token_usage, audit_ref
```

设计要求：

### 6.1 减重原则

- state 中只保存“引用、摘要、决策信号”，不保存大对象本体。
- 大结果表内容、统计工件、长文本一律走 artifact store。
- 高频但小体量字段可以保留在 state；中体量数据尽量走 Redis。
- 任意字段只要可能超过 10KB，应拆为引用 + 边界元信息。

### 6.2 建议的最小化状态结构

```text
RunState (minimized)
- request: request_id, session_id, trace_id, idempotency_key, locale
- tenant: user_id, domain, site, principal, scopes, auth_ref
- conversation: latest_user_message, recent_messages_ref, session_summary_ref
- datasource: datasource_luid, project_name, schema_hash
- artifacts: result_manifest_ref, metadata_snapshot_ref, field_semantic_ref
- semantic: intent, measures, dimensions, filters, timeframe, grain, confidence, ambiguity
- clarification: pending_type, interrupt_id, resume_value_ref
- query: plan_ref, retry_count, budget_ms, query_status
- result: row_count, truncated, empty_reason
- answer: answer_ref, evidence_ref, followup_ref
- ops: error_code, metrics_ref, token_usage_ref, audit_ref
```

### 6.3 典型“降重替换”

- `recent_messages` → `recent_messages_ref`
- `session_summary` → `session_summary_ref`
- `query_plan` → `plan_ref`
- `normalized_table` → `result_manifest_ref`
- `answer_text` → `answer_ref`
- `evidence` → `evidence_ref`
- `metrics` → `metrics_ref`

## 7. 模块映射

| 现有模块 | 新模块定位 |
| --- | --- |
| `src/api/routers/chat.py` | 保留为兼容入口，内部改走 graph runner |
| `src/orchestration/workflow/executor.py` | 过渡期兼容，最终退役 |
| `src/agents/semantic_parser/graph.py` | 升级为 `semantic_graph` 的主体 |
| `src/platform/tableau/query_builder.py` | 保留为查询计划编译核心 |
| `src/platform/tableau/adapter.py` | 保留为执行适配层 |
| `src/agents/insight/*` | 以文件驱动方式重构 |
| `src/infra/storage/repository.py` | 业务表 repository，不能继续承担全部存储角色 |

## 8. 洞察节点重设计结论

当前洞察链路不能作为最终方案，原因不是单一组件问题，而是整体模式有缺陷：

- prompt 仍然先锚定在压缩摘要上
- 大结果访问仍然会回到整份 JSON 读入内存
- 工具层没有真正的文件分页和 workspace 约束

因此新设计要求：

- 洞察主入口必须是结果文件 manifest
- agent 先定位文件，再读取所需分片
- 模型看到的是文件工具与局部结果，而不是整个结果集

中间件细节见 [middleware.md](./middleware.md)。
