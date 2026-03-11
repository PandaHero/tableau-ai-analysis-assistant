# Analytics Assistant 新后端设计文档

> 版本：v1.0  
> 日期：2026-03-10  
> 适用范围：`analytics_assistant/src` 后端  
> 文档类型：完整设计文档  
> 说明：本文件为新后端的目标设计，不涉及本次代码修改

---

## 1. 文档目标

这份文档用于定义 Analytics Assistant 后端的下一代目标实现。

它解决五类问题：

1. 当前后端为什么已经不适合继续围绕 `WorkflowExecutor` 增量演化。
2. 新后端的运行主干、模块边界和状态边界应该如何设计。
3. LangChain 和 LangGraph 在这个项目里分别负责什么，不负责什么。
4. 洞察节点为什么必须改成文件中间件驱动，以及文件中间件应该如何设计。
5. 如何将现有代码逐步迁移到新架构，而不是一次性推倒重写。

本文件不是“只给方向”的高层方案，也不是“只列 DDL 和接口”的附件。

本文件的目标是：

- 可直接拿去做架构评审
- 可直接拿去拆分研发任务
- 可作为后续 API、数据库、节点实现、测试设计的母文档

---

## 2. 设计范围

本文档覆盖：

- FastAPI 控制层
- LangGraph 运行层
- LangChain 模型与中间件层
- Tableau 集成层
- 业务存储层
- 缓存层
- artifact 与索引层
- 洞察文件中间件
- API / SSE / Resume 契约
- 错误模型、可观测性、安全与迁移

本文档不覆盖：

- 前端页面设计
- Tableau Extension UI 实现
- 具体模型选型采购策略
- 具体部署脚本与 IaC

---

## 3. 当前系统问题总结

当前系统已经具备以下能力：

- FastAPI + SSE 聊天接口
- 会话、设置、反馈 API
- LangGraph 语义解析子图
- Tableau 元数据加载与查询执行
- Insight Agent / Replanner Agent
- 基础缓存与模型路由

但当前系统的主要问题不是“没有功能”，而是“能力被错误地组织在一起”。

### 3.1 结构性问题

1. `WorkflowExecutor` 承担了过多总控逻辑。
2. LangGraph 只用于局部语义解析，而没有成为全局运行主干。
3. API 层知道太多编排细节。
4. 业务态、运行态、缓存态混在一起。
5. Tableau 认证、数据源解析、元数据加载、索引预热、查询执行耦合过深。
6. 洞察节点依赖摘要与工具混合探索，难以稳定处理大结果。
7. 中断机制不完整，`interrupt/resume` 没有成为主运行模型。
8. 错误边界不清楚，部分系统故障会伪装成空结果或 not found。

### 3.2 为什么不能继续围绕 `WorkflowExecutor` 改

继续围绕当前 `executor.py` 重构的坏处有三个：

1. 运行状态仍然会分散在本地变量、上下文对象、事件队列和多个子模块里。
2. 中断恢复和持久化恢复会继续依赖自定义协议。
3. 项目虽然表面上在用 LangGraph，但真正的状态机仍然是自定义 orchestrator。

因此，下一阶段不能把目标定义为“把 `WorkflowExecutor` 拆成更多类”。

正确目标必须是：

- 让 LangGraph 从局部语义子图上升为全局运行主干

---

## 4. 目标设计原则

新后端必须遵守以下原则。

### 4.1 运行主干原则

- 一个会话线程只由一个 `root_graph` 驱动
- `thread_id = session_id`
- 每一轮运行都可 checkpoint
- 所有需要用户确认的流程都走 `interrupt/resume`

### 4.2 边界原则

- API 层不做工作流总控
- LLM 不直接生成可执行 Tableau 查询
- LangGraph 不当业务主库
- 中间件不承担主编排职责
- artifact 不等于通用文件工作区

### 4.3 租户与数据源安全原则

- 所有 tenant-sensitive cache 都必须带租户维度
- 生产主链禁止 fuzzy datasource binding
- datasource identity 必须可审计
- 空结果与执行失败必须清晰区分

### 4.4 洞察原则

- 洞察节点必须基于结果文件进行探索
- `DataProfile` 只能作为辅助摘要
- 大结果不能直接塞给模型
- 洞察文件工具必须只读、受控、分页

### 4.5 迁移原则

- 先稳边界，再改主干
- 先引入 graph shell，再迁子图
- 先兼容现有 API，再逐步替换内部实现
- 禁止一次性大爆炸迁移

---

## 5. 目标架构总览

新后端分为五层：

1. API 控制层
2. LangGraph 运行层
3. 领域服务层
4. 存储与缓存层
5. Artifact 与索引层

### 5.1 总体架构图

```text
┌──────────────────────────────────────────────────────────────┐
│                      API 控制层 (FastAPI)                    │
│  chat/stream  chat/resume  sessions  settings  feedback      │
└─────────────────────────────┬────────────────────────────────┘
                              │
┌─────────────────────────────┴────────────────────────────────┐
│                  LangGraph 运行层 (root_graph)               │
│  context_graph  semantic_graph  query_graph  answer_graph    │
└─────────────────────────────┬────────────────────────────────┘
                              │
┌─────────────────────────────┴────────────────────────────────┐
│                       领域服务层                              │
│  tenant service  tableau service  query service  answer svc  │
└─────────────────────────────┬────────────────────────────────┘
                              │
┌─────────────────────────────┴────────────────────────────────┐
│                      存储与缓存层                             │
│  Postgres  LangGraph Checkpointer  Redis  Audit Log          │
└─────────────────────────────┬────────────────────────────────┘
                              │
┌─────────────────────────────┴────────────────────────────────┐
│                     Artifact 与索引层                         │
│ metadata snapshot / field semantic / retrieval / result file │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. 各层职责定义

### 6.1 API 控制层

负责：

- 鉴权
- 请求校验
- 将 HTTP 请求转为 graph 输入
- 将 graph stream 转为 SSE / WebSocket
- 业务 CRUD API

不负责：

- 工作流总控
- Tableau 业务逻辑
- 语义解析流程控制
- 洞察流程控制

### 6.2 LangGraph 运行层

负责：

- root graph
- 子图组合
- state
- checkpoint
- interrupt/resume
- graph streaming

不负责：

- 当业务数据库
- 替代对象存储
- 直接处理 HTTP

### 6.3 领域服务层

负责：

- tenant context 解析
- datasource identity 解析
- metadata snapshot 加载
- query plan 生成
- query execute
- result normalize
- answer 组装

不负责：

- SSE 协议
- LangGraph 主状态存储

### 6.4 存储与缓存层

负责：

- 业务实体落库
- checkpoint 落库
- 缓存
- 审计日志

不负责：

- 把故障伪装成空值
- 直接暴露给 LLM 当工作区

### 6.5 Artifact 与索引层

负责：

- metadata snapshot
- field sample
- field semantic
- retrieval index
- 结果文件
- spill artifact

不负责：

- 在线主链默认重建
- 通用文件代理功能

---

## 7. 目标目录设计

建议目录：

```text
analytics_assistant/src/
  api/
    main.py
    middleware.py
    dependencies.py
    routers/
    models/
  graphs/
    root_graph.py
    state.py
    subgraphs/
      context_graph.py
      semantic_graph.py
      query_graph.py
      answer_graph.py
    nodes/
  domain/
    errors/
    services/
    policies/
    models/
  integrations/
    tableau/
      auth_service.py
      datasource_service.py
      metadata_service.py
      query_service.py
  persistence/
    postgres/
    checkpoint/
    cache/
    artifact_store/
  artifacts/
    builders/
    readers/
  observability/
    tracing.py
    logging.py
    metrics.py
  agents/
    insight/
    semantic_parser/
    replanner/
    middleware/
```

---

## 8. 运行主干设计

### 8.1 root graph

整个后端收敛为一个 `root_graph`。

关键规则：

- `thread_id = session_id`
- graph 输入是“已校验的本轮请求”
- graph 输出是“最终结果”或“interrupt payload”
- graph 挂 durable checkpointer

### 8.2 root graph 负责的能力

- 一轮请求完整执行
- 澄清中断
- follow-up 中断
- 错误分类
- 状态持久化
- 恢复执行
- 最终流式输出

### 8.3 root graph 不负责的能力

- 存业务主表
- 直接给前端返回 HTTP
- 充当对象存储

---

## 9. 子图设计

新后端分四个子图：

1. `context_graph`
2. `semantic_graph`
3. `query_graph`
4. `answer_graph`

---

## 10. context_graph 设计

### 10.1 职责

- 加载会话上下文
- 加载用户设置
- 解析 tenant context
- 获取 Tableau auth
- 解析 datasource identity
- 加载 metadata snapshot
- 加载 ready artifacts

### 10.2 节点

#### `ingress_validate`

输入：

- 原始 API 请求

输出：

- `ValidatedRunRequest`

校验：

- `messages` 非空
- 最后一条必须是 `user`
- `datasource_luid` 优先于 `datasource_name`
- `session_id` 合法

失败：

- `CLIENT_VALIDATION_ERROR`

#### `hydrate_business_context`

输入：

- `session_id`
- `user_id`

输出：

- 会话信息
- 用户设置
- 历史摘要

失败：

- `SESSION_NOT_FOUND`

#### `resolve_tenant_context`

输入：

- API 用户身份
- 站点配置

输出：

- `TenantContext`

内容：

- `user_id`
- `tableau_username`
- `domain`
- `site`
- `scopes`
- `auth_method`

失败：

- `TENANT_AUTH_ERROR`

#### `resolve_tableau_auth`

输入：

- `TenantContext`

输出：

- `auth_handle_ref`

要求：

- token cache 必须带 `domain + site + principal + auth_method + scope_hash`

失败：

- `TABLEAU_AUTH_ERROR`

#### `resolve_datasource_identity`

输入：

- `datasource_luid` 或 `datasource_name + project_name`

输出：

- `datasource_luid`
- `datasource_name`
- `project_name`

规则：

- 优先 `datasource_luid`
- 否则只允许 `site + project + exact name`
- 零命中或多命中必须中断

失败：

- `DATASOURCE_RESOLUTION_ERROR`
- 或进入 `interrupt`

#### `load_metadata_snapshot`

输入：

- `datasource_luid`

输出：

- `metadata_snapshot_ref`
- `schema_hash`

不应在线默认做：

- 重建索引
- 跑重型 field semantic

#### `load_ready_artifacts`

输入：

- `datasource_luid`
- `schema_hash`

输出：

- `field_semantic_ref`
- `field_samples_ref`
- `rag_index_ref`

允许 degraded：

- artifact 缺失不一定直接失败
- 但必须明确记录 warning

---

## 11. semantic_graph 设计

### 11.1 职责

- 语义候选检索
- 结构化语义解析
- 语义校验
- 澄清生成
- 澄清中断

### 11.2 节点

#### `retrieve_semantic_candidates`

输入：

- 用户问题
- metadata refs
- retrieval refs

输出：

- measures 候选
- dimensions 候选
- values 候选

要求：

- 只针对元数据与字段语义做 RAG
- 不是聊天记录检索

#### `semantic_parse`

类型：

- LLM 结构化节点

输入：

- 用户问题
- 候选字段
- metadata hints

输出：

- `SemanticParseOutput`

约束：

- schema-first
- 优先 provider-native structured output
- 不允许自由文本协议

#### `semantic_guard`

类型：

- 确定性节点

校验：

- 字段存在性
- 字段权限
- 时间范围合法性
- 聚合与粒度冲突
- 筛选值合法性

输出：

- 通过后的语义结果
- 或 `ClarificationRequest`

#### `clarification_interrupt`

类型：

- `interrupt`

场景：

- datasource 歧义
- filter value confirmation
- missing slot fill

输出：

- interrupt payload

恢复：

- `resume_payload`

---

## 12. query_graph 设计

### 12.1 职责

- query plan 编译
- Tableau 查询执行
- 结果规范化
- 结果文件生成

### 12.2 节点

#### `build_query_plan`

输入：

- 语义输出
- metadata snapshot

输出：

- query plan

要求：

- 确定性
- 可审计
- 不由 LLM 直接写 VizQL

#### `execute_tableau_query`

输入：

- query plan
- auth handle

输出：

- `ExecuteResult`

失败分类：

- `TABLEAU_AUTH_ERROR`
- `TABLEAU_TIMEOUT`
- `TABLEAU_PERMISSION_ERROR`
- `QUERY_EXECUTION_ERROR`

#### `normalize_result_table`

输入：

- `ExecuteResult`
- metadata snapshot

输出：

- `NormalizedResult`

规范化内容：

- column type
- dimension / measure
- null 语义
- timezone
- truncation 标记
- row_count 语义

#### `materialize_result_files`

输入：

- `NormalizedResult`
- `run_id`
- `query_id`

输出：

- `result_file_refs`

建议文件格式：

- `jsonl` 主格式
- `csv` 可选导出
- `summary.json` 辅助索引

设计原则：

- 洞察节点读取的是结果文件，不是内存整表对象

---

## 13. answer_graph 设计

### 13.1 职责

- 洞察生成
- 重规划决策
- follow-up 中断
- 运行摘要持久化

### 13.2 节点

#### `insight_generate`

这是回答生成主节点，但要分两种实现模式：

1. 小结果模式
   - 可直接给 LLM 较小表结果摘要
2. 大结果模式
   - 必须走文件中间件驱动的 tool-using insight agent

本项目应将第二种模式视为长期主方案。

#### `replan_decide`

输入：

- insight output
- result profile
- run history

输出：

- `stop`
- `auto_continue`
- `user_select`

规则：

- 最多一次自动延伸
- 超出后必须中断或停止

#### `followup_interrupt`

类型：

- `interrupt`

场景：

- 用户选择下一步分析方向

#### `persist_run_artifacts`

写入：

- `analysis_runs`
- `analysis_interrupts`
- `query_audit_logs`
- `run_artifacts`

---

## 14. 根状态设计

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

### 14.1 `request_state`

- `request_id`
- `session_id`
- `thread_id`
- `trace_id`
- `idempotency_key`
- `turn_id`
- `locale`

### 14.2 `tenant_state`

- `user_id`
- `tableau_username`
- `domain`
- `site`
- `scopes`
- `auth_method`
- `auth_handle_ref`

### 14.3 `conversation_state`

- `latest_user_message`
- `recent_messages`
- `conversation_summary`
- `analysis_depth`
- `replan_mode`

### 14.4 `datasource_state`

- `datasource_selector`
- `datasource_luid`
- `datasource_name`
- `project_name`
- `schema_hash`
- `visibility_scope`

### 14.5 `artifact_state`

- `metadata_snapshot_ref`
- `field_samples_ref`
- `field_semantic_ref`
- `rag_index_ref`
- `result_file_refs`
- `spilled_artifact_refs`
- `artifacts_ready`

### 14.6 `semantic_state`

- `intent`
- `measures`
- `dimensions`
- `filters`
- `timeframe`
- `grain`
- `sort`
- `ambiguity_reason`
- `confidence`

### 14.7 `clarification_state`

- `pending`
- `interrupt_type`
- `interrupt_payload`
- `resume_payload`

### 14.8 `query_state`

- `query_plan`
- `query_status`
- `query_id`
- `retry_count`
- `execution_budget_ms`

### 14.9 `result_state`

- `normalized_result_ref`
- `row_count`
- `truncated`
- `empty_reason`

### 14.10 `answer_state`

- `answer_text`
- `evidence`
- `caveats`
- `suggested_followups`

### 14.11 `ops_state`

- `warnings`
- `error_code`
- `metrics`
- `token_usage`
- `audit_ref`

### 14.12 状态设计原则

state 里只放：

- ID
- 引用
- 摘要
- 小型结构化结果

state 里不放：

- 全量结果表
- 大块 metadata 原文
- 原始 token
- 原始 secret

---

## 15. LangChain 使用策略

### 15.1 LangChain 负责什么

- 模型抽象
- provider 切换
- structured output
- tool binding
- agent middleware

### 15.2 LangChain 不负责什么

- 工作流主编排
- 全局状态机
- 业务主库存储

### 15.3 必须复用的 LangChain 能力

- `ModelRetryMiddleware`
- `ToolRetryMiddleware`
- `SummarizationMiddleware`

### 15.4 不应当作主方案的能力

- `HumanInTheLoopMiddleware`
  - 本项目 HITL 主语义应统一由 LangGraph `interrupt/resume` 提供
- `FilesystemFileSearchMiddleware`
  - 当前不是代码代理产品
- `ShellToolMiddleware`
  - 当前分析后端不应默认给 agent 提供 shell

### 15.5 structured output 策略

1. provider-native structured output
2. tool strategy
3. prompt 注入 schema fallback

---

## 16. HTTP 层与中间件设计

### 16.1 HTTP 层保留框架自带能力

继续使用：

- `CORSMiddleware`
- FastAPI exception handlers
- 路由参数校验
- 静态文件挂载

不建议重复自研：

- 自定义 CORS
- 自定义全局错误 middleware
- 自定义参数校验 middleware

### 16.2 HTTP 层自定义中间件

只保留一个轻量自定义中间件：

- `RequestContextMiddleware`

职责：

- 注入 `request_id`
- 生成或透传 `trace_id`
- 记录请求开始/结束日志
- 回写 `X-Request-ID`

不负责：

- 错误转换
- 鉴权
- 业务逻辑

---

## 17. Tableau 领域服务设计

建议重组为三个只读服务：

1. `resolve_datasource`
2. `load_metadata_snapshot`
3. `query_datasource`

### 17.1 `resolve_datasource`

输入优先级：

1. `datasource_luid`
2. `site + project_name + exact datasource_name`

禁止：

- prefix 自动命中
- fuzzy 自动命中
- 扫全量后取第一个返回

### 17.2 `load_metadata_snapshot`

职责：

- 读取字段元数据
- 记录 snapshot
- 生成 / 恢复 `schema_hash`

禁止在线默认做：

- 大索引重建
- 重型 field semantic 推断

### 17.3 `query_datasource`

职责：

- 执行确定性 VizQL 请求
- 分类错误
- 返回 `ExecuteResult`

禁止：

- 直接执行 LLM 自由文本查询

---

## 18. 洞察节点新设计

这一节是新后端设计里最重要的变更之一。

### 18.1 当前洞察节点为什么必须重做

当前洞察链路的问题不在于一句“采样不行”，而在于它整体上仍然是摘要驱动、伪文件模式：

1. 模型先看到的是 `DataProfile` 摘要，而不是结果文件。
2. `read_filtered_data()` 直接回大 JSON。
3. `get_data_profile()` 强化了“先看摘要、后看数据”的模式。
4. `DataStore` 的文件模式本质上仍然会把整个文件重新读回内存。

这会导致三个问题：

1. 大结果场景下上下文不稳。
2. 模型的探索路径被摘要先验强烈影响。
3. 文件模式只是存储策略，不是 agent 探索策略。

### 18.2 新洞察设计原则

新洞察节点必须满足：

1. 结果文件是一等输入。
2. 洞察 agent 通过文件工具分页读取结果。
3. `DataProfile` 只作为辅助摘要。
4. 超大工具结果要自动 spill。
5. 文件工具必须只读、受控、可审计。

### 18.3 洞察节点执行模式

#### 模式 A：小结果快速模式

适用场景：

- 行数很小
- 列数很少
- 数据总字符量很小

策略：

- 可直接给 LLM 结构化结果摘要

#### 模式 B：文件驱动模式

适用场景：

- 默认主路径
- 尤其是中大结果场景

策略：

- 生成结果文件
- 使用 `InsightFilesystemMiddleware`
- 模型通过文件工具探索结果

本项目建议：

- 将文件驱动模式视为长期默认模式

---

## 19. InsightFilesystemMiddleware 设计

### 19.1 目标

`InsightFilesystemMiddleware` 是洞察节点专用中间件。

它的目标：

1. 让模型基于结果文件探索数据。
2. 防止大工具结果塞爆上下文。
3. 将大结果按 run/query/tool_call 落到 artifact store。
4. 返回预览与引用，而不是返回整份大结果。
5. 为洞察节点提供受控、只读、分页的文件工具。

### 19.2 非目标

它不负责：

- shell 执行
- 通用文件写入
- 任意目录浏览
- grep / glob
- 文件编辑
- 通用工作区能力

### 19.3 为什么不能直接用 LangChain 现成 middleware

当前 LangChain 没有一个可以直接替代的中间件，能够同时完成：

- 结果文件工具注入
- 大结果自动落盘
- 工具结果改写
- 结果文件分页读取

所以这里必须自研。

### 19.4 为什么不直接继续依赖 `deepagents`

因为：

- `deepagents` 带入了不属于本项目技术主线的 backend 抽象
- 它默认是通用 agent 文件工作台
- 权限面过大
- 不符合本项目的只读洞察需求

### 19.5 中间件职责

#### A. 主结果文件暴露

在进入洞察节点前，将查询结果物化为只读文件：

- `/runs/{run_id}/query_result.jsonl`
- `/runs/{run_id}/query_result.csv`
- `/runs/{run_id}/summary.json`

#### B. 文件工具注入

注入受控只读工具：

- `list_result_files`
- `read_result_file`
- `read_spilled_artifact`

#### C. 大结果自动 spill

在 `awrap_tool_call` 里拦截大返回值：

- 如果结果过大，写入 artifact
- 将工具响应改写成预览 + 引用

#### D. 模型提示修正

在 `awrap_model_call` 中追加简短规则：

- 优先使用结果文件工具
- spill 后使用 `read_spilled_artifact`

### 19.6 工具定义

#### `list_result_files`

用途：

- 返回当前 run 下可读取的结果文件列表

返回：

```json
{
  "files": [
    {
      "path": "/runs/{run_id}/query_result.jsonl",
      "content_type": "application/jsonl",
      "row_count": 18342
    }
  ]
}
```

#### `read_result_file`

用途：

- 分页读取结果文件

输入：

```json
{
  "path": "/runs/{run_id}/query_result.jsonl",
  "offset": 0,
  "limit": 200
}
```

返回：

```json
{
  "path": "/runs/{run_id}/query_result.jsonl",
  "offset": 0,
  "limit": 200,
  "total_lines": 18342,
  "content": "...",
  "has_more": true
}
```

#### `read_spilled_artifact`

用途：

- 读取被 spill 的工具结果

输入：

```json
{
  "artifact_id": "artifact_123",
  "offset": 0,
  "limit": 200
}
```

返回：

```json
{
  "artifact_id": "artifact_123",
  "offset": 0,
  "limit": 200,
  "content": "...",
  "has_more": true
}
```

### 19.7 状态扩展

```text
insight_filesystem_state
- result_file_refs: list[ResultFileRef]
- spilled_artifacts: dict[artifact_id, ArtifactRef]
- last_spilled_tool_call_id: optional[str]
```

### 19.8 ArtifactStore 抽象

```python
class ArtifactStore(Protocol):
    async def write_text(
        self,
        *,
        artifact_id: str,
        content: str,
        metadata: dict[str, Any],
    ) -> ArtifactRef: ...

    async def read_slice(
        self,
        *,
        artifact_id: str,
        offset: int = 0,
        limit: int = 200,
    ) -> ArtifactSlice: ...

    async def read_slice_by_path(
        self,
        *,
        path: str,
        offset: int = 0,
        limit: int = 200,
    ) -> ArtifactSlice: ...
```

### 19.9 文件格式建议

主格式：

- `jsonl`

原因：

- 适合逐行分页
- 不需要整文件反序列化
- 比单个大 JSON 数组更适合增量读取

### 19.10 与当前 DataStore 的关系

当前 `DataStore` 不应再作为洞察主读取模型。

它可以：

- 被保留作兼容层
- 或重写为结果文件写入器

但不能继续维持“文件模式 = 存完再整份读回”的方案。

### 19.11 洞察工具重构建议

当前工具：

- `read_data_batch`
- `read_filtered_data`
- `get_column_stats`
- `get_data_profile`
- `finish_insight`

新工具建议：

- `list_result_files`
- `read_result_file`
- `get_column_stats`
- `get_data_profile_summary`
- `finish_insight`
- `read_spilled_artifact`（补充）

原则：

- `read_filtered_data` 不再是主探索工具
- 如果保留过滤工具，也必须返回文件引用或强分页结果
- `get_data_profile` 降级为摘要工具

### 19.12 middleware 骨架

```python
class InsightFilesystemMiddleware(AgentMiddleware):
    state_schema = InsightFilesystemState

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        spill_threshold_tokens: int = 2000,
        chars_per_token: int = 4,
    ) -> None:
        self._artifact_store = artifact_store
        self._spill_threshold_tokens = spill_threshold_tokens
        self._chars_per_token = chars_per_token

        @tool
        async def list_result_files() -> str:
            ...

        @tool
        async def read_result_file(
            path: str,
            offset: int = 0,
            limit: int = 200,
        ) -> str:
            ...

        @tool
        async def read_spilled_artifact(
            artifact_id: str,
            offset: int = 0,
            limit: int = 200,
        ) -> str:
            ...

        self.tools = [list_result_files, read_result_file, read_spilled_artifact]

    async def awrap_model_call(self, request: ModelRequest, handler):
        request = self._append_filesystem_hint(request)
        return await handler(request)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        result = await handler(request)
        content = self._normalize_tool_result(result)
        if not self._should_spill(content):
            return result
        artifact_ref = await self._spill(content, request)
        return self._build_replacement_tool_message(result, artifact_ref)
```

### 19.13 安全约束

- 只允许访问当前 run 目录
- 不允许任意路径
- 不允许写文件
- 不允许 shell
- 所有读取行为必须可审计

---

## 20. 数据与存储设计

### 20.1 存储分层

- 业务实体：Postgres
- workflow checkpoints：LangGraph checkpointer
- 缓存：Redis
- artifact：对象存储 / 受控文件存储

### 20.2 业务表

建议最终业务表：

1. `chat_sessions`
2. `chat_messages`
3. `analysis_runs`
4. `analysis_interrupts`
5. `user_settings`
6. `message_feedback`
7. `tableau_metadata_snapshots`
8. `query_audit_logs`
9. `run_artifacts`
10. `run_result_files`

### 20.3 表职责

#### `chat_sessions`

- 会话主表

#### `chat_messages`

- 消息记录

#### `analysis_runs`

- 一轮运行一条

关键字段：

- `run_id`
- `thread_id`
- `session_id`
- `request_id`
- `trace_id`
- `query_id`
- `datasource_luid`
- `status`

#### `analysis_interrupts`

- 中断记录

关键字段：

- `interrupt_id`
- `run_id`
- `thread_id`
- `interrupt_type`
- `payload_json`
- `resume_payload_json`
- `status`

#### `run_artifacts`

- spill artifact
- metadata artifact

#### `run_result_files`

- 主结果文件引用

关键字段：

- `run_id`
- `query_id`
- `path`
- `content_type`
- `row_count`
- `byte_size`

### 20.4 为什么 LangGraph 不能当业务主库

因为：

- 业务实体需要原生查询能力
- 业务实体需要迁移能力
- 业务实体需要审计能力
- LangGraph checkpoint 的职责是运行恢复，不是通用关系查询

---

## 21. 缓存设计

建议缓存键：

```text
tableau:token:{domain}:{site}:{principal}:{auth_method}:{scope_hash}
tableau:metadata:{site}:{datasource_luid}:{schema_hash}
tableau:fieldvals:{site}:{datasource_luid}:{field_name}
artifact:resultfile:{run_id}:{query_id}
artifact:spill:{run_id}:{tool_call_id}
```

规则：

- 必须有 tenant 维度
- 必须有 TTL
- cache miss 不能改变业务语义

---

## 22. API 设计

### 22.1 `POST /api/chat/stream`

用途：

- 启动一轮普通分析请求

输入：

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

强约束：

- `messages` 非空
- 最后一条必须是 `user`
- `datasource_luid` 优先于 `datasource_name`

### 22.2 `POST /api/chat/resume`

用途：

- 恢复一个被 interrupt 挂起的 graph 执行

输入：

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

注意：

- 这是恢复执行
- 不是事件回放

### 22.3 可选事件回放接口

如果前端需要断线补事件，另行设计：

- `GET /api/runs/{run_id}/events?after=N`

不要把它和 `resume` 混在一起。

### 22.4 CRUD API

保留：

- `/api/sessions`
- `/api/settings`
- `/api/feedback`

但内部实现改为正式业务存储。

---

## 23. SSE 契约设计

### 23.1 事件类型

最终收敛为：

- `status`
- `parse_result`
- `interrupt`
- `table_result`
- `insight`
- `replan`
- `complete`
- `error`

可选：

- `token`

### 23.2 与 LangGraph stream 对齐

- `messages` -> token
- `updates` -> 状态与节点更新
- `custom` -> 领域事件

### 23.3 不建议长期保留的事件

- `candidate_questions`
- `suggestions`
- `planner`
- `plan_step`
- `chart`
- `thinking_token`

如确实需要，应折叠为稳定 `custom` 事件，而不是继续扩散协议种类。

---

## 24. 错误模型

建议统一错误码：

- `CLIENT_VALIDATION_ERROR`
- `SESSION_NOT_FOUND`
- `TENANT_AUTH_ERROR`
- `TABLEAU_AUTH_ERROR`
- `DATASOURCE_RESOLUTION_ERROR`
- `METADATA_LOAD_ERROR`
- `SEMANTIC_PARSE_ERROR`
- `SEMANTIC_VALIDATION_ERROR`
- `QUERY_PLAN_ERROR`
- `QUERY_EXECUTION_ERROR`
- `EMPTY_RESULT`
- `INSIGHT_GENERATION_ERROR`
- `RUN_PERSISTENCE_ERROR`

关键原则：

- `EMPTY_RESULT` 是业务结果，不是系统故障
- 上游故障不能伪装为空结果

---

## 25. 可观测性设计

每次运行至少要串起：

- `request_id`
- `trace_id`
- `session_id`
- `thread_id`
- `run_id`
- `query_id`

### 25.1 指标

- run latency
- semantic parse latency
- query execution latency
- insight latency
- interrupt count
- empty result rate
- token usage per node
- result file materialization latency
- spill count
- read_result_file count

### 25.2 tracing

建议：

- LangSmith trace
- 应用 trace
- Tableau query 审计

### 25.3 日志

日志应至少记录：

- tenant
- datasource
- run_id
- query_id
- interrupt_id
- artifact_id

---

## 26. 安全设计

硬规则：

- 生产主链禁止 fuzzy datasource binding
- 不满足加密要求时禁止持久化原始 API key
- 缓存必须带租户维度
- 空结果与执行失败必须明确区分
- 分析 agent 不默认拥有 shell / 文件编辑能力

对 `InsightFilesystemMiddleware` 的额外要求：

- 只读
- 路径受控
- 按 run 作用域隔离
- spill artifact 有 TTL

---

## 27. 测试策略

### 27.1 节点级测试

覆盖：

- 输入校验
- 输出 schema
- 失败分类
- state mutation

### 27.2 图级测试

覆盖：

- 正常单轮执行
- clarification interrupt / resume
- datasource interrupt / resume
- follow-up interrupt / resume
- retry / timeout 边界

### 27.3 洞察节点专项测试

必须覆盖：

- 小结果模式
- 大结果文件模式
- `read_result_file` 分页
- spill 后 `read_spilled_artifact`
- 路径越界拒绝
- 同 run 与跨 run 隔离

### 27.4 集成测试

覆盖：

- API -> graph bridge
- graph -> Tableau service
- graph checkpoint / resume
- result file materialization
- insight filesystem middleware

---

## 28. 迁移计划

### Phase 0：先稳边界

交付：

- run_id / error code
- datasource identity 收紧
- token cache key 收紧
- storage error 分类

### Phase 1：引入 root graph 骨架

交付：

- `root_graph`
- checkpointer
- API compatibility adapter

### Phase 2：迁移 semantic runtime

交付：

- semantic child graph
- clarification interrupt / resume
- state 收缩

### Phase 3：迁移 query runtime

交付：

- query plan node
- Tableau execute node
- normalize node
- result file materialization

### Phase 4：重做洞察节点

交付：

- 新 insight agent prompt
- 结果文件驱动读取
- `DataProfile` 降级为摘要

### Phase 5：引入 `InsightFilesystemMiddleware`

交付：

- `ArtifactStore`
- `InsightFilesystemMiddleware`
- `list_result_files`
- `read_result_file`
- `read_spilled_artifact`

验收：

- 洞察节点以结果文件为主探索入口
- 大结果不再直接挤爆上下文
- 不引入 shell、edit、write 权限面

### Phase 6：迁移业务存储

交付：

- Postgres repository
- 正式业务表
- feedback 与 run/query/message 完整绑定

### Phase 7：下线旧 executor

交付：

- graph-native runtime bridge
- 移除 executor-specific event logic

---

## 29. 现有模块保留与替换建议

优先保留并重构利用：

- `platform/tableau/query_builder.py`
- `platform/tableau/adapter.py`
- `agents/semantic_parser/graph.py`
- `infra/ai/model_manager.py`
- `agents/replanner/graph.py`

保留但重写内部逻辑：

- `agents/insight/graph.py`
- `agents/insight/components/data_store.py`
- `agents/insight/components/data_tools.py`

只保留兼容层意义：

- `api/routers/chat.py`
- `orchestration/workflow/callbacks.py`
- `agents/base/middleware_runner.py`

建议替换：

- `orchestration/workflow/executor.py`
- `platform/tableau/data_loader.py`
- `platform/tableau/client.py`
- `infra/storage/repository.py`
- `deepagents.FilesystemMiddleware` 依赖

---

## 30. 最终结论

新后端的最终形态不应该是：

- 一个被拆成若干 Stage 的 `WorkflowExecutor`

而应该是：

- 以 `root_graph` 为主干的 graph-native 后端

这意味着：

- LangGraph 负责运行主干
- LangChain 负责模型与中间件
- Tableau 能力收敛为只读领域服务
- 洞察节点改成文件中间件驱动
- 业务存储、运行存储、缓存、artifact 明确分层

特别强调：

- 洞察节点必须重做
- `DataProfile` 不再是洞察主入口
- `InsightFilesystemMiddleware` 是新架构中的关键能力，不是可选优化项

这套设计是当前项目从“功能已存在但结构失控”走向“可持续演进的分析后端”的必要步骤。
