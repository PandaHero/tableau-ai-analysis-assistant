# Backend Refactor Requirements

> 状态: Draft v1.0
> 读取顺序: 2/12
> 上游文档: [README.md](./README.md)
> 下游文档: [design.md](./design.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [migration.md](./migration.md)
> 关联文档: [tasks.md](./tasks.md)

## 1. 背景

当前后端已经具备聊天入口、Tableau 查询、语义解析、洞察和重规划能力，但这些能力被组织在错误的边界里：

- API 层承担了部分编排职责。
- `WorkflowExecutor` 承担了过多总控逻辑。
- LangGraph 只在语义解析子图里局部使用，没有成为全局运行主干。
- Tableau 认证、数据源解析、元数据加载、索引预热、查询执行耦合过深。
- 洞察节点仍然以摘要驱动为主，不适合可靠处理大结果集。

## 2. 目标

### 2.1 架构目标

系统必须收敛成以下主形态：

- FastAPI 只做控制层。
- LangGraph `root_graph` 成为整轮会话的运行主干。
- 运行线程使用 `thread_id = session_id`。
- 主图拆分为 `context_graph`、`semantic_graph`、`query_graph`、`answer_graph` 四个子图。
- LangChain 只负责模型接入、structured output 和必要 middleware。

### 2.2 数据与运行目标

系统必须满足以下边界：

- 业务数据、运行状态、缓存、artifact 分层存放。
- 多租户 token、datasource、metadata 缓存必须具备完整租户维度。
- datasource 生产主链禁止 fuzzy 绑定。
- 业务级人机交互必须以 `interrupt/resume` 作为正式协议，而不是临时事件拼接。
- 工具级审批可以额外使用 middleware，但底层恢复语义仍然不能绕开 `interrupt/resume`。

### 2.3 洞察能力目标

洞察节点必须从当前模式升级为文件驱动模式：

- 洞察主入口必须是结果文件，而不是 `DataProfile` 摘要。
- `DataProfile` 只保留为辅助提示信息。
- 洞察工具必须支持列目录、分页读取、局部过滤、artifact 引用和只读访问控制。
- 大结果不能直接整体注入模型上下文。

## 3. 非目标

本轮重构不包含以下内容：

- 前端 UI 改版。
- Tableau Extension 前端重写。
- 模型供应商采购或模型效果调优实验。
- 一次性推倒重写全部现有模块。

## 4. 硬约束

### 4.1 不重复造轮子

以下能力必须优先复用框架现成机制：

- FastAPI / Starlette 的 `CORSMiddleware`、异常处理、请求校验。
- LangGraph 的 `checkpointer`、`interrupt()`、streaming、subgraph 组合。
- LangChain 的 `ModelRetryMiddleware`、`ToolRetryMiddleware`、`SummarizationMiddleware` 等通用 agent middleware。

以下能力不能直接照搬第三方而必须按项目需求自研：

- 洞察结果文件中间件。

原因是当前项目不采用 `deepagents` 作为主运行框架，而 `deepagents.FilesystemMiddleware` 包含大量面向通用文件代理和代码代理的能力，范围过宽。

### 4.2 安全约束

- 所有 tenant-sensitive cache key 必须显式包含租户维度。
- 结果文件工具必须默认只读。
- resume 请求必须绑定 `interrupt_id` 和 `session_id`。
- 空结果与系统失败必须区分，不允许吞错后伪装成空数据。

### 4.3 性能约束

- 在线查询链路不得默认触发全量重索引或全量元数据预热。
- SSE 链路不得依赖无界队列承载无限事件。
- 大结果洞察必须通过分页文件读取控制 token 和内存成本。

## 5. 需求分组

### 需求 A: 全局运行主干

1. 系统必须以 LangGraph `root_graph` 承载整轮运行。
2. 所有中断型交互都必须统一走 `interrupt/resume`。
3. 会话线程必须能跨进程恢复。

### 需求 B: 租户与数据源安全

1. Tableau token 缓存键必须包含 `domain + site + principal + auth_method + scopes`。
2. datasource 解析必须优先使用 `datasource_luid`。
3. 当 `datasource_name` 不唯一时，系统必须进入澄清，而不是自动模糊命中。

### 需求 C: 语义解析与查询编译

1. 语义解析必须使用 schema-first 结构化输出。
2. 查询计划必须由确定性编译器生成。
3. 模型不得直接生成可执行 Tableau 查询并执行。

### 需求 D: 文件驱动洞察

1. 洞察节点必须通过只读文件工具探索结果。
2. 结果文件必须支持分页、按列选择、轻量过滤和片段读取。
3. 模型拿到的应该是“文件引用 + 需要的片段”，而不是整表 JSON。

### 需求 E: 存储与 API 契约

1. 业务表、checkpoint、缓存、artifact 必须分层。
2. `/api/chat/resume` 必须用于恢复业务中断，不只是断线重放事件。
3. SSE 事件必须收敛到稳定的业务事件模型。

## 6. 验收标准

### 6.1 架构验收

- 新请求从 API 入口进入后，能落到 `root_graph`，而不是直接驱动旧 executor 总控。
- 同一 `session_id` 的中断恢复可以在新进程中继续运行。

### 6.2 安全验收

- 多 site、多 principal 并发场景下不串 token。
- 同名 datasource 不会被自动绑到错误对象。

### 6.3 洞察验收

- 超大结果洞察不依赖一次性将全部 JSON 放入上下文。
- 洞察 agent 可以先列出结果文件，再读取所需分片，再生成结论。

### 6.4 运维验收

- 错误码能稳定区分 `EMPTY_RESULT`、`QUERY_EXECUTION_ERROR`、`TABLEAU_AUTH_ERROR`、`SEMANTIC_PARSE_ERROR`。
- 每轮运行都能关联 `request_id`、`session_id`、`thread_id`、`run_id`、`trace_id`。
