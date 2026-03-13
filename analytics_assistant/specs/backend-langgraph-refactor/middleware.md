# Middleware Strategy

> Status: Draft v1.2
> Read order: 5/14
> Upstream: [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md)
> Downstream: [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [insight-large-result-design.md](./insight-large-result-design.md), [tasks.md](./tasks.md)

## 1. 目标

明确三件事：

1. 哪些中间件必须直接复用框架能力。
2. 哪些能力需要自研且范围要收敛。
3. 如何避免“业务状态机逻辑”被中间件侵入。

## 2. 复用优先清单

### 2.1 FastAPI / Starlette

直接复用：

- `CORSMiddleware`
- 全局异常处理器
- 请求体验证与响应模型

按需复用：

- `TrustedHostMiddleware`
- `HTTPSRedirectMiddleware`

不建议用于 SSE 主链路：

- `GZipMiddleware`（可能影响事件及时性）

### 2.2 LangGraph

直接复用：

- `checkpointer`
- `interrupt()`
- `subgraph`
- `astream/streaming`

结论：

- 业务级交互（澄清、确认、follow-up）统一用 `interrupt/resume`。
- 不新增并行的人机交互协议。

### 2.3 LangChain

直接复用：

- `ModelRetryMiddleware`
- `ToolRetryMiddleware`
- `SummarizationMiddleware`
- `ModelFallbackMiddleware`
- `ModelCallLimitMiddleware`
- `HumanInTheLoopMiddleware`（仅工具级审批）

## 3. 业务中断与工具审批边界

| 类型 | 场景 | 机制 |
| --- | --- | --- |
| 业务中断 | datasource 歧义、缺失槽位、value confirm、高风险查询确认、follow-up 选择 | `interrupt/resume` |
| 工具审批 | 是否允许某工具执行、是否修改工具参数 | `HumanInTheLoopMiddleware` |

关键边界：

- 工具审批不能替代业务中断恢复语义。
- 业务中断必须可跨进程恢复，工具审批只是局部控制。

## 4. 为什么新增 `InsightFilesystemMiddleware`

当前缺口是“洞察阶段的安全文件探索”，而不是通用文件代理。

必须新增的原因：

- 需要只读文件工具与分页读取契约。
- 需要工作区隔离（仅当前 run 的 artifact root）。
- 需要统一注入洞察 prompt 的读取规范。

## 5. `InsightFilesystemMiddleware` 设计

### 5.1 职责

- 注入只读结果文件工具。
- 绑定洞察工作区（workspace）。
- 对路径、分页参数和读取范围做统一校验。

### 5.2 非职责

- 不负责编排 root_graph。
- 不持久化业务实体。
- 不提供任意写文件/执行 shell 能力。
- 不接管业务 interrupt 逻辑。

### 5.3 Workspace 模型

```text
InsightWorkspace
- workspace_id
- run_id
- session_id
- artifact_root
- result_manifest_path
- allowed_files
- default_page_size
- max_page_size
```

### 5.4 工具清单

- `list_result_files`
- `describe_result_file`
- `read_result_file`
- `read_result_rows`
- `read_spilled_artifact`

### 5.5 安全规则

- 所有路径必须命中 allowlist。
- 默认只读。
- 强制分页上限与列裁剪。
- 读取请求必须落在当前 workspace。

## 6. Prompt 注入规范

中间件应在洞察模型调用前注入最小规则：

- 先列目录，再读文件，不得假设文件存在。
- 优先读取 `manifest/profile`，再读 `rows/chunks`。
- 大文件必须分页读取。
- 每次读取都要说明目的（验证假设/补充证据）。

## 7. 与检索/记忆平面的关系

- 检索与记忆是“候选增强平面”，不是 middleware。
- `InsightFilesystemMiddleware` 只解决“结果文件探索”。
- 记忆写入、检索策略路由与失效治理应由平面服务统一管理。
