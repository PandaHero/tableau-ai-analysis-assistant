# Middleware Strategy

> 状态: Draft v1.0
> 读取顺序: 4/12
> 上游文档: [design.md](./design.md)
> 下游文档: [data-and-api.md](./data-and-api.md), [tasks.md](./tasks.md)
> 关联文档: [requirements.md](./requirements.md), [migration.md](./migration.md)

## 1. 目的

这个文件专门回答两个问题：

1. 现有项目和框架已经自带哪些 middleware，不应重复造轮子。
2. 洞察阶段必须新增怎样的文件中间件，才能替代当前不合适的实现。

## 2. 直接复用的框架能力

### 2.1 FastAPI / Starlette

直接复用：

- `CORSMiddleware`
- `exception_handler`
- 请求体验证和响应模型

可选复用：

- `TrustedHostMiddleware`
- `HTTPSRedirectMiddleware`

不建议在 SSE 主链直接启用：

- `GZipMiddleware`

原因是 SSE 流式响应容易受到缓冲影响。

### 2.2 LangGraph

直接复用：

- `checkpointer`
- `interrupt()`
- `subgraph`
- `streaming`
- 线程状态恢复

结论：

- 用户澄清和 follow-up 选择应由 LangGraph `interrupt/resume` 负责。
- 不需要在业务主链额外自研一套“人工确认 middleware”。

### 2.3 LangChain

当前环境中可直接复用的 agent middleware 包括：

- `ModelRetryMiddleware`
- `ToolRetryMiddleware`
- `SummarizationMiddleware`
- `FilesystemFileSearchMiddleware`
- `HumanInTheLoopMiddleware`
- `ModelFallbackMiddleware`
- `ModelCallLimitMiddleware`

设计结论：

- `ModelRetryMiddleware`、`ToolRetryMiddleware` 继续直接复用。
- `SummarizationMiddleware` 只用于超长对话摘要，不用于替代文件洞察。
- `HumanInTheLoopMiddleware` 可以用于工具级审批，不作为会话主澄清机制；会话主澄清使用 LangGraph `interrupt()`。
- `FilesystemFileSearchMiddleware` 不足以承载本项目洞察文件需求。

## 3. 当前项目中间件复审

| 位置 | 当前能力 | 处理结论 |
| --- | --- | --- |
| `src/api/middleware.py` | 请求日志和异常注册 | 保留，但只做 request/trace/run 关联 |
| `src/agents/base/middleware_runner.py` | 自定义 middleware 执行器 | 保留为过渡层，长期应弱化 |
| `src/agents/insight/*` | 当前洞察工具 | 需要重构 |
| `src/agents/replanner/*` | 依赖现有 agent middleware | 保留 LangChain 部分，取消业务态自定义协议 |

## 3.1 业务级中断 vs 工具级审批

这两类交互必须明确区分：

| 类型 | 典型场景 | 推荐机制 | 结论 |
| --- | --- | --- | --- |
| 业务级中断 | datasource 歧义、缺失筛选、follow-up 选择 | LangGraph `interrupt/resume` | 主方案 |
| 工具级审批 | 是否允许执行某个工具、是否修改工具参数 | `HumanInTheLoopMiddleware` | 可选补充 |

关键点：

- `HumanInTheLoopMiddleware` 本质上也是在工具调用点触发 `interrupt`。
- 它更适合“approve/edit/reject tool call”，不适合承载完整业务交互协议。
- 因此系统要统一的不是“统一用某个类名的 middleware”，而是“统一用 `interrupt/resume` 作为恢复语义”。

## 4. 为什么现有洞察方式不行

当前洞察链路的问题是“摘要驱动 + 伪文件模式”：

- `DataProfile` 被当作主入口，而不是辅助摘要。
- 结果虽可 spill 到文件，但读取时又会重新整体加载。
- 工具更像“返回大 JSON”，而不是“操作结果文件的只读工作台”。

这会直接导致：

- 大结果上下文成本不可控。
- 结果探索粒度过粗。
- 模型容易被摘要先验锚定。

## 5. 对 `deepagents.FilesystemMiddleware` 的结论

可以借鉴的思想：

- 中间件向 agent 注入文件工具。
- 系统 prompt 中增加文件工作约束。
- 大内容可以 spill 到文件引用。
- 文件读取默认分页。

不能直接复用的原因：

- 当前项目不以 `deepagents` 作为主代理框架。
- 其能力范围过宽，包含读写编辑执行等面向通用代码代理的能力。
- 我们的需求是“只读结果文件探索”，不是“通用文件代理”。

## 6. 新增 `InsightFilesystemMiddleware`

### 6.1 目标

`InsightFilesystemMiddleware` 是洞察子图的专用中间件，职责非常窄：

- 暴露只读结果文件工具
- 管理洞察工作空间上下文
- 在 prompt 中注入文件探索规范
- 对大结果返回文件引用而不是整表内容

### 6.2 不负责

- 不负责 root graph 编排
- 不负责业务状态持久化
- 不提供任意写文件或执行 shell 的能力
- 不替代 LangGraph interrupt

### 6.3 工作空间模型

洞察节点会拿到一个 `InsightWorkspace`：

```text
InsightWorkspace
- workspace_id
- run_id
- session_id
- result_manifest_path
- artifact_root
- allowed_files
- default_page_size
- max_page_size
```

### 6.4 结果文件组织

建议使用 manifest + 分片文件：

```text
result_manifest.json
- dataset_id
- row_count
- column_schema
- primary_result_file
- chunks[]
- derived_artifacts[]
```

结果文件形态建议：

- `result.parquet` 或 `result.jsonl`
- `chunks/chunk-0001.jsonl`
- `profiles/column_profile.json`
- `samples/head.jsonl`

### 6.5 中间件暴露的工具

必须提供以下工具：

- `list_result_files`
- `describe_result_file`
- `read_result_file`
- `read_result_rows`
- `read_spilled_artifact`

建议工具语义：

| 工具 | 作用 | 约束 |
| --- | --- | --- |
| `list_result_files` | 列出可访问结果文件 | 仅返回 allowlist |
| `describe_result_file` | 返回文件类型、行数、列信息、分片信息 | 不返回大内容 |
| `read_result_file` | 按页读取文本类 artifact | 默认分页 |
| `read_result_rows` | 按页读取表格行，可指定列和轻量过滤 | 限制每页大小 |
| `read_spilled_artifact` | 读取中间 spill 文件 | 仅限当前 workspace |

### 6.5.1 工具参数与返回结构（示例）

1) `list_result_files`

```
输入: {}
输出: {
  "files": [
    {"path": "result_manifest.json", "type": "manifest"},
    {"path": "profiles/column_profile.json", "type": "profile"},
    {"path": "chunks/chunk-0001.jsonl", "type": "chunk"}
  ]
}
```

2) `describe_result_file`

```
输入: {"file": "result_manifest.json"}
输出: {
  "path": "result_manifest.json",
  "row_count": 100000,
  "columns": [{"name": "region", "type": "string"}, ...],
  "chunks": [{"path": "chunks/chunk-0001.jsonl", "rows": 5000}, ...]
}
```

3) `read_result_file`

```
输入: {"file": "profiles/time_rollup_day.json", "offset": 0, "limit": 200}
输出: {
  "path": "profiles/time_rollup_day.json",
  "offset": 0,
  "limit": 200,
  "content": "文本内容或JSON片段"
}
```

4) `read_result_rows`

```
输入: {
  "file": "chunks/chunk-0001.jsonl",
  "columns": ["date","region","sales"],
  "filters": {"region": "East", "date": "last_30_days"},
  "offset": 0,
  "limit": 200
}
输出: {
  "rows": [{"date":"2025-02-01","region":"East","sales":123}, ...],
  "offset": 0,
  "limit": 200,
  "row_count": 200
}
```

5) `read_spilled_artifact`

```
输入: {"file": "spill/agent-temp-001.json", "offset": 0, "limit": 200}
输出: {"path":"spill/agent-temp-001.json","content":"..."}
```

### 6.6 prompt 注入规范

中间件必须在洞察模型调用前注入系统提示，至少包括：

- 先列出可用结果文件，再决定读取哪个文件
- 对大文件必须分页读取
- 优先读取 schema、manifest、局部行，而不是整表
- 不能假设未读取内容

### 6.7 状态与 hook

推荐 hook 设计：

- `before_agent`: 注入 workspace 和工具说明
- `before_model`: 把当前 result manifest 摘要写入 prompt
- `after_model`: 若模型请求整表，则重定向为文件读取提示
- `wrap_tool_call`: 统一做路径校验、页大小校验、审计和限流

### 6.8 安全规则

- 所有路径必须经过 allowlist 校验
- 只允许当前 `run_id` 对应的 artifact root
- 默认只读
- 所有读取都要带分页上限

### 6.9 与 LangChain/LangGraph 的边界

- 该中间件实现方式可以参考 LangChain `AgentMiddleware`。
- 但它的业务触发时机由 `answer_graph` 控制，不由中间件本身决定执行阶段。
- 业务澄清依然由 LangGraph `interrupt()` 控制，而不是中间件接管。
- 如果未来某个文件工具需要显式人工审批，可以在该工具上叠加 `HumanInTheLoopMiddleware`，但这属于工具级补充能力。

## 7. 推荐实现方式

实现层次建议如下：

1. `ArtifactStore`: 负责落盘、索引、读取文件和 manifest。
2. `InsightWorkspaceManager`: 负责为每轮 run 建立 allowlist。
3. `InsightFilesystemMiddleware`: 负责将 workspace 绑定到 agent 调用。
4. `ResultFileTools`: 负责提供只读文件工具。

## 8. 采用结论

最终策略如下：

- HTTP 层 middleware 继续优先使用 FastAPI/Starlette 内建能力。
- 通用 agent middleware 继续优先使用 LangChain 内建能力。
- 业务主链的人机中断继续使用 LangGraph `interrupt/resume`。
- 洞察文件探索中间件必须自研 `InsightFilesystemMiddleware`，参考 `deepagents` 的模式，但严格收缩到只读结果文件场景。
