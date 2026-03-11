# Analytics Assistant 后端重构升级蓝图

> 版本：v1.0  
> 日期：2026-03-09  
> 范围：`analytics_assistant/src` 后端代码  
> 目标：基于 LangChain 和 LangGraph 的后端重构升级方案  
> 说明：纯架构与方案文档，不涉及代码修改

---

## 1. 文档目标

这份文档解决三个问题：

1. 重新按“功能点”而不是只按“文件”审查当前后端。
2. 给出一套基于 LangChain 与 LangGraph 的落地型目标架构。
3. 给出可以直接用于评审、拆解任务、制定里程碑的迁移方案。

这不是泛泛而谈的“技术选型建议”，而是基于当前项目实际代码结构、已有能力、已有问题做出的重构蓝图。

---

## 2. 结论先行

当前后端并不是能力不足，而是能力分散：

- API 层承担了部分编排职责
- `WorkflowExecutor` 承担了过多总控逻辑
- LangGraph 只在语义解析子图中局部使用
- Tableau 集成层混合了认证、数据源解析、元数据加载、索引预热、查询执行
- 业务存储、运行态存储、缓存没有清晰分层

这导致系统目前有五个核心结构性问题：

1. 租户边界和数据源边界不够硬。
2. 运行态分散在 API、executor、graph state、repository 多处。
3. 在线请求链路承担了太多准备工作。
4. 错误语义不够清晰，部分故障会被伪装成“空结果”或“未找到”。
5. LangGraph 的 `interrupt/resume` 只在局部使用，没有成为完整的人机协同机制。

如果继续围绕当前 `WorkflowExecutor` 叠逻辑，后端复杂度会继续上升；正确方向不是继续扩 executor，而是把 LangGraph 提升为整个后端运行主干。

---

## 3. 当前后端功能点审计

下面按“现有功能、当前实现、主要问题、重构去向”来审查。

### 3.1 API 入口与请求边界

对应文件：

- `analytics_assistant/src/api/main.py`
- `analytics_assistant/src/api/middleware.py`
- `analytics_assistant/src/api/routers/chat.py`
- `analytics_assistant/src/api/models/chat.py`

当前实现：

- FastAPI 提供 REST 和 SSE。
- `chat.py` 接收聊天请求，截断历史，创建 `WorkflowExecutor`，并将事件流通过 SSE 输出。
- 中间件已经支持 `request_id` 注入和全局异常处理。

已有能力：

- API 基础框架清楚。
- SSE 保活机制已经存在。
- 请求日志和请求追踪已经有雏形。

主要问题：

- 路由层已经知道太多执行细节，不再只是“传输层”。
- `ChatRequest` 还没有把“最后一条必须是 user”这种运行约束固化成模型契约。
- “新的一轮请求”和“恢复一个中断”没有被建模成两种不同的 API。

重构去向：

- FastAPI 保留。
- 路由层只做鉴权、请求校验、启动 graph、恢复 graph、SSE 转发。
- 明确拆出 `start run` 和 `resume interrupt`。

### 3.2 鉴权与租户隔离

对应文件：

- `analytics_assistant/src/api/dependencies.py`
- `analytics_assistant/src/platform/tableau/auth.py`

当前实现：

- 应用层用户身份通过请求头与 JWT 解析。
- Tableau 上游认证支持 JWT 和 PAT。
- Tableau token 做了进程内缓存。

已有能力：

- 已经存在应用层身份和上游 Tableau 身份这两个层次。
- token 刷新与获取流程已经具备基础能力。

主要问题：

- API 身份和 Tableau 身份没有统一成一个正式的租户上下文。
- token cache 键粒度不够，隐含单 site/单 principal 假设。
- token 生命周期主要依赖本地 TTL 估算。

重构去向：

- 建立 `TenantContext`。
- 每次运行显式携带：
  - user identity
  - domain
  - site
  - auth method
  - scopes
  - auth handle ref
- 所有 token cache、artifact cache、datasource cache 全部带租户维度。

### 3.3 会话、设置、反馈

对应文件：

- `analytics_assistant/src/api/routers/sessions.py`
- `analytics_assistant/src/api/routers/settings.py`
- `analytics_assistant/src/api/routers/feedback.py`
- `analytics_assistant/src/infra/storage/repository.py`

当前实现：

- session/settings/feedback 都经由通用 `BaseRepository` 存在 LangGraph BaseStore 上。
- session 列表采用“全量读取 -> 内存排序 -> 内存分页”的方式。

已有能力：

- 会话、设置、反馈功能都已经具备。
- API 表面上简单，开发成本低。

主要问题：

- 通用 KV repository 被当作业务数据库使用。
- 存储异常会被吞掉，导致系统故障被解释成空列表或 404。
- feedback 仅绑定 `message_id`，没有和 `run_id/query_id/trace_id` 建立强关联。

重构去向：

- session/message/run/interrupt/settings/feedback 全部迁到正式业务存储层。
- LangGraph persistence 只保留给运行态。
- feedback 必须能回链到某次执行、某条答案、某次查询。

### 3.4 工作流总控

对应文件：

- `analytics_assistant/src/orchestration/workflow/executor.py`
- `analytics_assistant/src/orchestration/workflow/context.py`
- `analytics_assistant/src/orchestration/workflow/callbacks.py`

当前实现：

- `WorkflowExecutor` 负责认证、加载数据模型、运行语义图、执行查询、生成洞察、触发重规划、发 SSE 事件。
- `WorkflowContext` 负责携带 auth、datasource、data_model、field_semantic、schema_hash、platform_adapter 等对象。

已有能力：

- 逻辑已经被串成一条完整链路。
- 上下文对象已经具备一定统一依赖容器的雏形。

主要问题：

- `WorkflowExecutor` 是典型 God Object。
- 状态分散在请求体、executor 局部变量、WorkflowContext、语义图 state、session 存储、事件队列中。
- SSE 回调层和 LangGraph 官方 stream 语义重复。

重构去向：

- 废弃 executor 主导地位。
- 用 `root_graph` 接管整轮运行。
- `WorkflowContext` 保留思想，但收缩成轻量运行引用和上下文载体。

### 3.5 语义解析

对应文件：

- `analytics_assistant/src/agents/semantic_parser/graph.py`
- `analytics_assistant/src/agents/semantic_parser/state.py`
- `analytics_assistant/src/agents/semantic_parser/routes.py`
- `analytics_assistant/src/agents/semantic_parser/nodes/*`

当前实现：

- 已经存在 LangGraph 子图。
- 节点覆盖 intent、cache、retrieval、prompt、semantic understanding、output validation、filter validation、query adapter、error corrector、feedback learner。
- filter value confirmation 已经使用 `interrupt()`。

已有能力：

- 这是当前后端架构最接近正确方向的一部分。
- graph 的状态大体是可序列化的，具备 checkpoint 基础。
- 澄清逻辑已经不完全是“自由文本”。

主要问题：

- 语义图还只是局部子图，不是整条运行链的主干。
- state 过胖，把很多临时中间态和公共态混在一起。
- structured output 仍有较多自定义 prompt/schema 注入逻辑。

重构去向：

- 保留语义图的核心节点思想。
- 缩减 state。
- 挂到 root graph 下，成为正式子图。
- 将中断能力从 filter confirmation 扩展到 datasource 歧义、follow-up 选择、缺失槽位补全。

### 3.6 Tableau 集成

对应文件：

- `analytics_assistant/src/platform/tableau/auth.py`
- `analytics_assistant/src/platform/tableau/client.py`
- `analytics_assistant/src/platform/tableau/data_loader.py`
- `analytics_assistant/src/platform/tableau/adapter.py`
- `analytics_assistant/src/platform/tableau/query_builder.py`

当前实现：

- auth 负责 Tableau 登录。
- client 同时处理 VizQL、GraphQL 和数据源名称解析。
- data_loader 同时承担数据源 LUID 解析、元数据加载、字段样本获取、字段语义推断、索引恢复/创建。
- query_builder 与 adapter 负责语义到查询的确定性转换和执行。

已有能力：

- `query_builder.py` 和 `adapter.py` 具有较高复用价值。
- GraphQL + VizQL 双通路已经打通。
- data model 和 field sample 体系已经有基础。

主要问题：

- `data_loader.py` 职责过多。
- 数据源解析仍带有模糊绑定风险。
- 在线链路仍会顺手做很多重准备工作。
- Tableau 能力没有被抽象成稳定的领域服务。

重构去向：

- Tableau 层收敛为 3 个只读服务：
  - `resolve_datasource`
  - `load_metadata_snapshot`
  - `query_datasource`
- 保留 query builder 作为确定性执行编译器。
- 索引创建、field sample、field semantic 推断改为后台预热任务。

### 3.7 模型管理与 LangChain 封装

对应文件：

- `analytics_assistant/src/infra/ai/model_manager.py`
- `analytics_assistant/src/infra/ai/model_router.py`
- `analytics_assistant/src/infra/ai/model_factory.py`
- `analytics_assistant/src/infra/ai/model_persistence.py`
- `analytics_assistant/src/agents/base/node.py`

当前实现：

- 已有 model registry、task router、model factory、持久化能力。
- LangChain 模型实例通过工厂创建。
- structured output 目前较多依赖 schema prompt 注入和 partial JSON 解析。

已有能力：

- 多模型路由机制已经存在。
- provider 抽象已经存在。

主要问题：

- 动态模型持久化的密钥边界不够安全。
- structured output 方案自定义成分过高。
- 模型路由、模型持久化、运行策略边界还不够清晰。

重构去向：

- 保留 ModelManager 的思路。
- 强化密钥持久化安全规则。
- 统一走 LangChain structured output 策略。
- LLM 节点统一由 graph runtime helper 驱动，不在每个节点重复造轮子。

### 3.8 RAG 与索引

对应文件：

- `analytics_assistant/src/infra/rag/service.py`
- `analytics_assistant/src/infra/rag/index_manager.py`
- `analytics_assistant/src/infra/rag/retrieval_service.py`

当前实现：

- RAG service 是 embedding/index/retrieval 的统一入口。
- field retrieval 和 artifact reuse 已经接入。

已有能力：

- 索引层和检索层已经不是散装逻辑。

主要问题：

- RAG 还是应用进程内单例导向。
- 索引生命周期和在线请求耦合太深。
- artifact readiness 没有正式进入运行态。

重构去向：

- 在线链路只做“读取 ready artifact + 检索”。
- 离线任务负责构建和刷新。
- 所有 artifact 以 `{site}:{datasource_luid}:{schema_hash}` 分区。

### 3.9 洞察与重规划

对应文件：

- `analytics_assistant/src/agents/insight/graph.py`
- `analytics_assistant/src/agents/replanner/graph.py`

当前实现：

- insight agent 已支持工具调用和流式输出。
- replanner 已支持结构化输出。

已有能力：

- 洞察和重规划已经是两个清晰能力块。

主要问题：

- 它们仍是 executor 尾部外挂能力。
- replanner 和前端 candidate question 协议耦合过深。

重构去向：

- 迁入 `answer_graph`。
- follow-up selection 统一变成 interrupt/resume。

---

## 4. 重构目标

后端重构后的目标应当是：

1. LangGraph 成为整条运行链主干。
2. FastAPI 退回到控制层。
3. LLM 只负责真正需要 LLM 的认知任务。
4. 查询计划与执行必须保持确定性、可审计。
5. 运行态和业务态完全分层。
6. 所有中断都能 durable resume。
7. 在线请求不再默认做重型准备工作。
8. 所有租户相关缓存和 artifact 都具备硬隔离。

---

## 5. 目标架构

### 5.1 总体分层

目标后端分五层：

1. API 控制层
2. LangGraph 运行层
3. 领域服务层
4. 存储与缓存层
5. Artifact 与索引层

### 5.2 各层职责

| 层 | 负责什么 | 不负责什么 |
|---|---|---|
| API 控制层 | 鉴权、请求校验、SSE/WebSocket 转发、CRUD API | 工作流总控 |
| LangGraph 运行层 | root graph、子图、状态迁移、interrupt、checkpoint、streaming | 当业务数据库 |
| 领域服务层 | datasource 解析、metadata 加载、query plan、query execute、answer 组装 | 直接处理 HTTP |
| 存储与缓存层 | 业务数据、运行 checkpoint、缓存、审计日志 | 吞掉故障并返回空结果 |
| Artifact 与索引层 | field sample、field semantic、schema snapshot、向量索引 | 在在线主链默认重建重索引 |

### 5.3 目标目录建议

```text
analytics_assistant/src/
  api/
  graphs/
    root_graph.py
    state.py
    subgraphs/
      context_graph.py
      semantic_graph.py
      query_graph.py
      answer_graph.py
  domain/
  integrations/
    tableau/
  persistence/
  artifacts/
  observability/
```

---

## 6. LangGraph 运行设计

### 6.1 根图

整个后端应收敛为一个 `root_graph`。

关键规则：

- `thread_id = session_id`
- graph 输入为“已校验的 turn request”
- graph 输出为“最终答案”或“interrupt payload”
- graph 挂 durable checkpointer

根图负责：

- 一轮请求的完整执行
- 澄清中断
- follow-up 选择中断
- 重试边界
- 持久化恢复
- 最终流式输出

### 6.2 子图划分

根图拆成四个子图：

1. `context_graph`
2. `semantic_graph`
3. `query_graph`
4. `answer_graph`

#### `context_graph`

负责：

- 读取 session/settings/history summary
- 解析租户上下文
- 获取 Tableau auth
- 解析 datasource identity
- 加载 metadata snapshot
- 恢复 ready artifacts

#### `semantic_graph`

负责：

- retrieval
- semantic parse
- semantic validation
- clarification build
- clarification interrupt

#### `query_graph`

负责：

- deterministic query plan
- Tableau 查询执行
- 结果规范化
- query error 分类

#### `answer_graph`

负责：

- 洞察答案生成
- 重规划决策
- follow-up interrupt
- 收尾持久化

---

## 7. 节点详细设计

### 7.1 入口和上下文节点

| 节点 | 类型 | 输入 | 输出 | 失败语义 |
|---|---|---|---|---|
| `ingress_validate` | 确定性 | 原始请求 | `ValidatedRunRequest` | 4xx |
| `hydrate_business_context` | 确定性 | session_id/user_id | session/settings/history summary | `SESSION_NOT_FOUND` |
| `resolve_tenant_context` | 确定性 | 应用身份、配置 | tenant context | `TENANT_AUTH_ERROR` |
| `resolve_tableau_auth` | 确定性 | tenant context | auth handle ref | `TABLEAU_AUTH_ERROR` |
| `resolve_datasource_identity` | 确定性 | datasource selector | datasource identity | interrupt 或 `DATASOURCE_RESOLUTION_ERROR` |
| `load_metadata_snapshot` | 确定性 | datasource identity | snapshot ref + schema_hash | `METADATA_LOAD_ERROR` |
| `load_ready_artifacts` | 确定性 | datasource_luid/schema_hash | artifact refs | warning，不一定硬失败 |

### 7.2 语义节点

| 节点 | 类型 | 输入 | 输出 | 失败语义 |
|---|---|---|---|---|
| `retrieve_semantic_candidates` | 确定性 | question + artifact refs | 字段/值候选 | 可降级 |
| `semantic_parse` | LLM 结构化 | question + metadata hints | 结构化语义输出 | `SEMANTIC_PARSE_ERROR` |
| `semantic_guard` | 确定性 | 语义输出 + metadata | 校验后的语义输出或澄清请求 | `SEMANTIC_VALIDATION_ERROR` 或 interrupt |
| `clarification_interrupt` | interrupt | 澄清 payload | 挂起执行 | 等待 resume |

### 7.3 查询节点

| 节点 | 类型 | 输入 | 输出 | 失败语义 |
|---|---|---|---|---|
| `build_query_plan` | 确定性 | 校验后的语义输出 | query plan | `QUERY_PLAN_ERROR` |
| `execute_tableau_query` | IO + 确定性 | query plan + auth | 原始结果 | `QUERY_EXECUTION_ERROR`、`TABLEAU_TIMEOUT`、`TABLEAU_PERMISSION_ERROR` |
| `normalize_result_table` | 确定性 | raw result + metadata | 规范化结果 ref | `RESULT_NORMALIZATION_ERROR` |

### 7.4 答案节点

| 节点 | 类型 | 输入 | 输出 | 失败语义 |
|---|---|---|---|---|
| `insight_generate` | LLM 结构化 | semantic + normalized table + metadata hints | answer/evidence/caveats/followups | `INSIGHT_GENERATION_ERROR` |
| `replan_decide` | 确定性或 LLM 结构化 | answer + profile + run history | stop/auto_continue/user_select | `REPLAN_DECISION_ERROR` |
| `followup_interrupt` | interrupt | candidate followups | 挂起执行 | 等待 resume |
| `persist_run_artifacts` | 确定性 | run state summary | 落库/审计 | `RUN_PERSISTENCE_ERROR` |
| `finalize_stream` | 确定性 | final state | complete event | N/A |

### 7.5 硬规则

- `semantic_parse` 与 `insight_generate` 是核心 LLM 节点。
- `replan_decide` 可以使用 LLM，但必须 schema-first。
- 除 LLM 认知节点外，其余主链全部尽量确定性。
- 不允许 LLM 直接产最终可执行 Tableau 查询字符串。

---

## 8. 状态模型

### 8.1 根状态

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

### 8.2 各状态域

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

### 8.3 状态设计原则

state 里应该放：

- ID
- 引用
- 摘要
- 小型结构化输出

state 里不应该放：

- 大块 metadata 原文
- 全量表格数据
- 重复历史消息副本
- 原始 secret

---

## 9. LangChain 落点

LangChain 负责：

- 模型实例抽象
- provider 切换
- structured output
- tool binding
- middleware

LangChain 不负责：

- 端到端工作流编排
- 业务数据库
- 全局运行状态机

structured output 建议策略：

1. provider 支持时优先走 provider-native structured output
2. 不支持时走 tool strategy
3. 只在兼容场景下保留 prompt 注入 schema fallback

建议结构化模型：

- `SemanticParseOutput`
- `ClarificationRequest`
- `InsightOutput`
- `ReplanDecision`
- `FollowupSelectionRequest`

---

## 10. Tableau 领域服务设计

### 10.1 `resolve_datasource`

输入优先级：

1. 前端直接传 `datasource_luid`
2. `site + project_name + exact datasource_name`

允许结果：

- 唯一命中
- 零命中
- 多命中

生产主链禁止：

- prefix 自动命中
- fuzzy 自动命中
- 全量扫描后取第一个返回

### 10.2 `load_metadata_snapshot`

职责：

- 读取 field metadata
- 生成/恢复 `schema_hash`
- 记录快照时间
- 返回 snapshot ref

不应默认做的事：

- 在线重建大索引
- 在线拉起重型 field semantic 任务

### 10.3 `query_datasource`

职责：

- 执行确定性 VizQL 请求
- 分类错误
- 返回原始结果和执行元数据

必须禁止：

- 执行未经校验的自由文本 LLM 查询
- 把上游失败伪装成空结果

### 10.4 `normalize_result_table`

必须显式处理：

- column type
- dimension/measure
- 时间字段及时区
- null 语义
- 截断
- row limit
- execution note

---

## 11. Artifact 与索引设计

建议 artifact 类型：

- metadata snapshot
- schema hash registry
- field sample values
- field semantic
- field alias index
- retrieval index

统一分区键：

```text
{site}:{datasource_luid}:{schema_hash}
```

在线链路可以做的事：

- 检查 artifact readiness
- 使用已就绪 artifact
- 在 artifact 缺失时显式降级

离线或后台链路负责：

- field sample 构建
- field semantic 推断
- index build/refresh
- schema 变化对账

---

## 12. 业务存储设计

推荐业务表：

- `chat_sessions`
- `chat_messages`
- `analysis_runs`
- `analysis_interrupts`
- `user_settings`
- `message_feedback`
- `tableau_metadata_snapshots`
- `query_audit_logs`

分层建议：

- 业务实体 -> Postgres
- workflow checkpoints -> LangGraph checkpointer
- 短期缓存 -> Redis
- 大型 artifact -> object store/vector store

为什么这么分：

- 业务数据要可查询、可迁移、可审计
- 运行态要可恢复
- 缓存要高性能和 TTL
- artifact 要独立生命周期

---

## 13. 缓存设计

建议 key 设计：

```text
tableau:token:{domain}:{site}:{principal}:{auth_method}:{scope_hash}
tableau:metadata:{site}:{datasource_luid}:{schema_hash}
tableau:fieldvals:{site}:{datasource_luid}:{field_name}
```

运行规则：

- 必须有明确 TTL
- 必须有租户维度
- 不允许模糊 key
- cache miss 不能悄悄改变业务语义

---

## 14. API 与事件契约

### 14.1 `POST /api/chat/stream`

用途：

- 启动一轮普通分析请求

建议输入：

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

必做校验：

- `messages` 不能为空
- 最后一条必须是 `user`
- `datasource_luid` 优先于 `datasource_name`

### 14.2 `POST /api/chat/resume`

用途：

- 恢复一个中断中的 graph 执行

建议输入：

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

### 14.3 SSE 事件类型

建议统一事件：

- `status`
- `parse_result`
- `interrupt`
- `table_result`
- `insight`
- `replan`
- `complete`
- `error`

原则：

- payload 必须稳定、结构化
- 不允许事件 shape 依赖某个 executor 局部实现细节

---

## 15. interrupt 与 Human-in-the-Loop 设计

推荐 interrupt 类型：

- `datasource_disambiguation`
- `filter_value_confirmation`
- `missing_slot_fill`
- `followup_selection`

为什么必须用 interrupt：

- 用户澄清本质上就是一次挂起和恢复
- follow-up 选择本质上也是一次挂起和恢复
- 只有 interrupt/resume 才能天然支持跨进程恢复和 durable checkpoint

resume payload 要求：

- typed
- JSON 可序列化
- 不依赖隐藏 executor 内存态

---

## 16. Streaming 设计

当前问题：

- 自定义事件队列和 callback bridge 与 LangGraph 官方 streaming 语义重复
- 无界队列存在背压风险

目标方案：

- `messages`：模型 token 流
- `updates`：状态迁移、节点状态
- `custom`：领域事件，如 parse_result、interrupt、table_result、replan

API 层只负责：

- 订阅 graph stream
- 转换成 SSE
- 附加 `request_id` 和 `trace_id`

API 层不负责：

- 发明新的运行语义

---

## 17. 错误模型与可观测性

建议公共错误码：

- `CLIENT_VALIDATION_ERROR`
- `TENANT_AUTH_ERROR`
- `TABLEAU_AUTH_ERROR`
- `DATASOURCE_RESOLUTION_ERROR`
- `METADATA_LOAD_ERROR`
- `SEMANTIC_PARSE_ERROR`
- `SEMANTIC_VALIDATION_ERROR`
- `QUERY_EXECUTION_ERROR`
- `EMPTY_RESULT`
- `INSIGHT_GENERATION_ERROR`
- `RUN_PERSISTENCE_ERROR`

每次运行至少应具备这些关联键：

- `request_id`
- `trace_id`
- `session_id`
- `thread_id`
- `run_id`
- `query_id`

建议指标：

- run latency
- semantic parse latency
- query execution latency
- insight latency
- interrupt count
- empty result rate
- Tableau auth failure rate
- token usage per node

建议 tracing：

- LangSmith trace
- 应用层 trace
- datasource/query plan/result summary 审计日志

---

## 18. 安全设计

硬规则：

- 生产主链禁止 fuzzy datasource binding
- 不满足加密要求时禁止持久化原始 API key
- 对外错误信息禁止泄露路径、secret、原始 token
- 所有缓存必须带租户维度
- 空结果和执行失败必须明确区分

secret 处理建议：

- 以环境变量或 secret manager 为源
- 如必须持久化，只允许加密引用或加密密文
- 不允许明文 fallback

---

## 19. 迁移阶段

### Phase 0：先稳边界

目标：

- 在不大动架构前先把边界收紧

交付：

- run_id/error code
- datasource identity 策略收紧
- token cache key 收紧
- storage error 分类

验收：

- 不再出现模糊 datasource 命中
- 多 site/principal 不串 token
- 上游故障不再被解释成空结果

### Phase 1：引入 root graph 骨架

目标：

- 在不破坏现有 API 的前提下引入根图

交付：

- root graph shell
- checkpointer 接入
- API compatibility adapter

验收：

- `/api/chat/stream` 对前端无破坏
- `thread_id = session_id`

### Phase 2：迁移 semantic runtime

目标：

- 让语义解析和澄清全部回到 graph 中

交付：

- semantic child graph
- clarification interrupt/resume
- state 收缩

验收：

- clarification 可跨进程恢复

### Phase 3：迁移 query runtime

目标：

- 让 query plan、query execute、result normalize 全部 graph 内化

交付：

- query plan node
- Tableau execute node
- normalize node

验收：

- permission failure、timeout、empty result 三类稳定区分

### Phase 4：迁移 answer runtime

目标：

- 洞察生成和重规划正式并入 graph

交付：

- structured insight node
- structured replanner node
- follow-up interrupt

验收：

- follow-up selection 不再依赖 custom executor protocol

### Phase 5：迁移业务存储

目标：

- session/message/run/feedback 从通用 BaseStore 迁出

交付：

- Postgres repository
- 正式业务表
- feedback 到 run/query/message 的完整绑定

验收：

- 分页数据库原生化
- repository 故障不再表现为 not found

### Phase 6：下线旧 executor

目标：

- 让生产链路不再依赖 `WorkflowExecutor`

交付：

- graph-native runtime bridge
- 移除 executor-specific event logic

验收：

- 所有生产聊天链路都以 root graph 为主

---

## 20. 测试与验收策略

节点级契约测试覆盖：

- 输入校验
- 输出 schema
- 失败分类
- state mutation

图级测试覆盖：

- 正常单轮执行
- clarification interrupt/resume
- datasource interrupt/resume
- follow-up interrupt/resume
- retry/timeout 边界

集成测试覆盖：

- API -> graph bridge
- graph -> Tableau service
- graph persistence/resume
- session/run/feedback persistence

重点回归场景：

- 同名 datasource，不同 project
- 多 site token 隔离
- schema change
- empty result 语义
- candidate follow-up selection

---

## 21. 当前模块保留与重写建议

优先保留并重构利用：

- `platform/tableau/query_builder.py`
- `platform/tableau/adapter.py`
- `agents/semantic_parser/graph.py`
- `infra/ai/model_manager.py`
- `agents/insight/graph.py`
- `agents/replanner/graph.py`

只保留兼容层意义：

- `api/routers/chat.py`
- `orchestration/workflow/callbacks.py`

建议拆解或替换：

- `orchestration/workflow/executor.py`
- `platform/tableau/data_loader.py`
- `platform/tableau/client.py`
- `infra/storage/repository.py`

---

## 22. 如果从头基于 LangChain 和 LangGraph 做类似项目

我会坚持这些原则：

1. 热路径核心 LLM 节点最多两个：
   - semantic parse
   - answer generation
2. 执行链路确定性优先。
3. 所有用户澄清都走 interrupt/resume。
4. 运行态必须可 checkpoint、可恢复。
5. LangGraph state 不当业务主库。
6. 所有 tenant-sensitive cache 必须带 tenant key。
7. 生产主链禁止 fuzzy datasource binding。
8. 在线请求不默认做重型 artifact 构建。

---

## 23. 评审时建议讨论的问题

1. `session_id = thread_id` 是否符合产品会话模型？
2. datasource 选择是完全交给前端，还是允许后端 exact-name fallback？
3. metadata freshness 和在线延迟之间的 SLA 怎么定？
4. 哪些 artifact 是在线必须项，哪些允许降级？
5. 业务主库存储是否统一选 Postgres？
6. follow-up selection 是否允许某些模式下 auto-continue？

---

## 24. 官方能力参考

- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
- LangGraph subgraphs: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- LangGraph human-in-the-loop: https://docs.langchain.com/oss/python/langgraph/human-in-the-loop
- LangGraph streaming: https://docs.langchain.com/oss/python/langgraph/streaming
- LangChain structured output: https://docs.langchain.com/oss/python/langchain/structured-output

---

## 25. 最终建议

当前后端下一阶段最重要的不是继续优化 `WorkflowExecutor`，而是把 LangGraph 从“局部语义子图”提升为“全局运行主干”。

一旦完成这一步，后端会同时获得：

- durable runtime state
- 原生 human-in-the-loop
- 更清晰的错误边界
- 更薄的 API 层
- 更硬的租户隔离
- 更清楚的持久化分层
- 更强的可观测性
- 更低的长期复杂度

这条路线最符合当前项目的现状、问题类型和未来演进方向。
