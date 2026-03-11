# Analytics Assistant 后端最终重构方案

> 版本：v1.0
> 日期：2026-03-09
> 范围：`analytics_assistant/src` 后端
> 目标：形成一份可直接用于评审、排期、拆任务的最终版重构方案
> 说明：本文件合并了两类输入
> 1. 基于现有代码审查形成的 LangChain + LangGraph 主干方案
> 2. `backend_refactoring_plan.md` 中更具体的 DDL、SSE 契约、时序图类附件思路

---

## 1. 文档定位

这份文档用于回答四个问题：

1. 当前后端到底哪里有结构性问题。
2. 最终应该选择什么架构方向，而不是继续在现有 `WorkflowExecutor` 上缝补。
3. 当前项目里的中间件哪些应直接复用框架，哪些不该重复造轮子。
4. `deepagents.FilesystemMiddleware` 不能直接沿用时，我们应该如何基于项目需求设计一个轻量、自主可控的替代中间件。

本文件是最终建议稿。后续如果要继续往下拆，可以再分成：

- 技术方案主文档
- 数据库与缓存设计附件
- API / SSE / Resume 契约附件
- 中间件设计与实现说明附件

---

## 2. 最终决策

### 2.1 主干架构决策

最终主干必须选择：

- `FastAPI 控制层`
- `LangGraph root_graph 运行主干`
- `context_graph / semantic_graph / query_graph / answer_graph` 四个子图
- `LangChain 仅负责模型、structured output、必要 middleware`
- `Tableau 只读领域服务`
- `业务存储 / 运行态存储 / 缓存 / artifact` 明确分层

不建议选择“继续保留自定义 orchestrator 作为长期主干，再把 executor 拆成多个 Stage”的路线。

原因很直接：

1. 这条路只能缓解 `executor.py` 过长，不能真正统一运行状态。
2. 它仍然会把核心编排留在自定义状态机里，而不是落到 LangGraph 的 checkpoint、interrupt、resume、streaming 语义上。
3. 它很容易形成“表面上用了 LangGraph，实际上还是自定义 orchestrator 控全局”的半重构状态。

### 2.2 对 Cascade 方案的最终取舍

`backend_refactoring_plan.md` 的定位应调整为：

- 不是最终主架构
- 而是可复用的实施附件来源

可以吸收的内容：

- DDL 草案的完整性
- SSE 事件 JSON 的具体度
- 时序图和阶段图
- 实施排期表达方式

不能直接照搬的内容：

- `WorkflowOrchestrator + Stage` 作为长期主干
- 把 `/api/chat/resume` 主要定义为“断线后事件重放”
- 保留过多历史 SSE 事件类型并长期制度化

### 2.3 最终选择原则

最终选择不是二选一，而是：

- 主架构采用本方案的 `root_graph` 路线
- 实施附件吸收 Cascade 方案中更细的 DDL / JSON / 时序图表达

---

## 3. 当前后端结构性结论

当前后端不是能力缺失，而是能力分散：

- API 层承担了部分编排职责
- `WorkflowExecutor` 承担了过多总控逻辑
- LangGraph 只在语义解析子图中局部使用
- Tableau 集成层同时做认证、数据源解析、元数据加载、索引预热、查询执行
- 通用 repository 被同时当业务数据库、运行状态容器和缓存入口使用

这导致五个核心结构问题：

1. 租户边界和数据源边界不够硬。
2. 运行态散落在 API、executor、graph state、repository、queue。
3. 在线请求链路承担了过多准备工作。
4. 故障语义不清楚，部分错误会伪装成空结果或未找到。
5. `interrupt/resume` 只是局部能力，不是完整运行模型。

---

## 4. 当前中间件审计

这一节专门解决“不要重复造轮子”的问题。

### 4.1 HTTP 层当前中间件

对应文件：

- `analytics_assistant/src/api/main.py`
- `analytics_assistant/src/api/middleware.py`

当前 HTTP 层实际在用的能力：

- `CORSMiddleware`：FastAPI / Starlette 自带
- `RequestLoggingMiddleware`：项目自定义
- `register_exception_handlers()`：基于 FastAPI 异常处理机制，不是自定义 HTTP middleware

结论：

- `CORS` 不需要自研，继续使用框架自带 `CORSMiddleware`
- 异常处理不需要改造成“全局异常中间件”，FastAPI 的 `exception_handler` 机制已经足够
- `RequestLoggingMiddleware` 可以保留，但应收缩职责，只做：
  - `request_id` 注入
  - 请求开始/结束日志
  - 关联 trace/run/session 字段

不建议在 HTTP 层重复自研：

- CORS
- 通用异常转 JSON
- 请求体验证
- 静态文件服务

如后续需要，可考虑框架现成能力：

- `TrustedHostMiddleware`
- `HTTPSRedirectMiddleware`
- `GZipMiddleware`

但要注意：

- `GZipMiddleware` 不建议直接套在 SSE 流式聊天接口上，容易引入缓冲与流式体验问题

### 4.2 Agent / LLM 层当前中间件

对应文件：

- `analytics_assistant/src/agents/insight/graph.py`
- `analytics_assistant/src/agents/replanner/graph.py`
- `analytics_assistant/src/agents/base/middleware_runner.py`
- `analytics_assistant/src/agents/base/middleware/__init__.py`

当前已在用的 middleware：

- `ModelRetryMiddleware`：LangChain 内置
- `ToolRetryMiddleware`：LangChain 内置
- `SummarizationMiddleware`：LangChain 内置
- `FilesystemMiddleware`：`deepagents` 提供，不属于当前项目技术栈

当前还存在一层自定义执行器：

- `MiddlewareRunner`

它的作用是：

- 在自定义 graph 节点函数里执行 LangChain `AgentMiddleware`
- 兼容 `before_agent / before_model / wrap_model_call / after_model / wrap_tool_call / after_agent`

这里的判断要分开：

1. `ModelRetryMiddleware / ToolRetryMiddleware / SummarizationMiddleware`
   - 这些是 LangChain 已有能力
   - 不要重新发明
2. `MiddlewareRunner`
   - 这是为了兼容“当前项目没有直接使用 LangChain create_agent 主链”
   - 短期可保留
   - 但它不应该继续扩成“全项目统一编排器”
3. `deepagents.FilesystemMiddleware`
   - 不建议继续依赖
   - 应改成项目自有、职责更窄的中间件

### 4.3 当前框架已提供、应优先复用的中间件能力

基于当前环境，已经可以直接复用的框架能力包括：

- FastAPI / Starlette:
  - `CORSMiddleware`
  - exception handlers
  - 静态文件挂载
  - 路由验证
- LangChain:
  - `ModelRetryMiddleware`
  - `ToolRetryMiddleware`
  - `SummarizationMiddleware`
  - `HumanInTheLoopMiddleware`
  - `FilesystemFileSearchMiddleware`
  - `ShellToolMiddleware`
  - `ToolCallLimitMiddleware`
  - `ModelCallLimitMiddleware`
  - `ModelFallbackMiddleware`
  - `PIIMiddleware`

但是“框架有”不等于“项目应该用”。

对于当前项目，推荐：

- 继续使用：
  - `ModelRetryMiddleware`
  - `ToolRetryMiddleware`
  - `SummarizationMiddleware`
- 不建议作为主链核心使用：
  - `HumanInTheLoopMiddleware`
    - 因为本项目的主 HITL 机制应该统一走 LangGraph `interrupt/resume`
  - `FilesystemFileSearchMiddleware`
    - 当前不是代码代理类产品，不需要通用文件搜索
  - `ShellToolMiddleware`
    - 当前分析场景不应默认给 agent 提供 shell 能力

---

## 5. DeepAgent 文件中间件源码审查结论

审查来源：

- `venv/Lib/site-packages/deepagents/middleware/filesystem.py`
- `venv/Lib/site-packages/deepagents/middleware/_utils.py`

### 5.1 它实际做了什么

`deepagents.FilesystemMiddleware` 的职责远不只是“文件工具”。

它主要做了四类事：

1. 给 agent 注入通用文件系统工具
   - `ls`
   - `read_file`
   - `write_file`
   - `edit_file`
   - `glob`
   - `grep`
2. 若 backend 支持执行，还会动态注入 `execute` 工具
3. 在 `wrap_model_call` 中动态改写 system prompt
4. 在 `wrap_tool_call` 中拦截超大工具结果，把结果落到文件系统，再把引用和预览返回给模型

### 5.2 它最有价值的能力

真正值得借鉴的不是“通用文件系统能力”，而是两条能力：

- 大工具结果自动溢出到文件系统，避免上下文窗口被一次性塞爆
- 模型以文件方式分页读取结果，而不是一次性吞下整个工具返回值

这和我们当前项目非常相关，因为：

- `Insight Agent` 的工具调用会返回 JSON 结果
- `read_filtered_data()` 可能返回大量行
- `get_data_profile()` 在列很多时也可能偏大
- 目前虽然 `read_data_batch()` 有分页，但并不能覆盖所有大结果场景

### 5.3 它不适合直接拿来用的原因

不适合直接复用的原因有五个：

1. 它依赖 `deepagents` 的 backend 抽象和 state 组织方式。
2. 它默认提供的是“通用文件代理能力”，而不是“分析后端的领域能力”。
3. 它把文件编辑、写入、grep、glob、shell 执行也一起带进来，权限面过大。
4. 它的 state 模型偏“通用 agent 工作区”，不符合我们要的轻量运行态。
5. 我们项目真正要解决的是“大结果保护”，不是把 agent 改造成文件系统代理。

结论：

- 不能直接依赖 `deepagents.FilesystemMiddleware`
- 但应该保留它的两类核心思路：
  - 文件化分页读取
  - 大结果自动溢出

### 5.4 对当前洞察节点的修订结论

这里需要明确修正之前方案中的一个点：

- 当前洞察节点不能继续以“`DataProfile` 摘要 + `read_data_batch/read_filtered_data`”作为长期主方案

原因不是一句“它用了采样”就能概括，而是整个洞察链路目前仍然是摘要驱动、伪文件模式：

1. `build_user_prompt()` 先把模型锚定到 `DataProfile` 摘要。
2. `get_data_profile()` 返回的是压缩后的画像，不是可增量探索的原始结果。
3. `read_filtered_data()` 会直接回传匹配行 JSON，缺少文件化分页保护。
4. `DataStore` 虽然在大数据量时写临时文件，但读取时又会把整份 JSON 文件重新读回内存再切片，这不是真正的文件中间件模式。

所以对洞察节点的最终结论应当是：

- `Insight Agent` 必须改成文件中间件驱动
- 文件中间件成为洞察节点的核心探索机制
- `DataProfile` 只能退化为辅助摘要，不再是洞察主入口

### 5.5 LangChain 是否已有可直接替代的文件中间件

基于当前环境中的 `langchain.agents.middleware`，可以确认：

- 已有：
  - `ModelRetryMiddleware`
  - `ToolRetryMiddleware`
  - `SummarizationMiddleware`
  - `FilesystemFileSearchMiddleware`
  - `ShellToolMiddleware`
- 没有：
  - 一个可直接替代 `deepagents.FilesystemMiddleware` 的“文件分页读取 + 工具结果落盘 + 结果引用回写”一体化中间件

因此最终选型应是：

- 继续直接使用 LangChain 自带的 retry / summarization middleware
- 文件中间件不采用 LangChain 现成实现
- 参考 `deepagents.FilesystemMiddleware` 自研一个项目专用版本

---

## 6. 项目自研替代文件中间件方案

### 6.1 建议命名

建议自研中间件命名为：

- `InsightFilesystemMiddleware`

这个命名比单纯 `ArtifactSpillMiddleware` 更准确，因为它不是只做 spill guard，而是完整承接洞察节点的文件化读取模式。

它的核心职责是：

- 为洞察节点暴露只读结果文件工具
- 将超大工具结果自动溢出到 artifact/file store
- 把模型的探索模式从“直接吃 JSON 结果”改成“分页读取文件”

### 6.2 目标

`InsightFilesystemMiddleware` 的目标有五个：

1. 让洞察节点基于结果文件做探索，而不是只依赖画像摘要。
2. 防止超大工具结果直接灌满模型上下文。
3. 把大结果按 `run_id / query_id / tool_call_id` 写入可追踪 artifact store。
4. 向模型返回小而稳定的预览和引用。
5. 允许模型通过只读文件工具分页读取结果。

### 6.3 非目标

它不负责：

- 通用文件写入
- 任意目录浏览
- grep / glob
- shell 执行
- 文件编辑
- 将 artifact store 暴露成通用工作区

这点很重要。我们不是在做代码代理，不需要把 DeepAgent 的文件工作台搬进来。

### 6.4 适用范围

建议仅在以下节点使用：

- `insight_graph` 中的 tool-using agent

原则上不建议：

- 在 `semantic_graph` 使用
- 在 `query_graph` 使用
- 在 HTTP 层使用

原因：

- 它是洞察节点专用文件中间件，不是全局中间件

### 6.5 中间件职责拆分

`InsightFilesystemMiddleware` 应拆成四类职责：

#### A. 结果文件暴露

将当前查询结果或洞察可读结果集持久化为只读结果文件。

建议格式优先级：

1. `jsonl`
2. `csv`
3. `json`

不建议继续使用“整个 JSON 数组一次性读回”的方式作为主实现。

#### B. 文件分页读取工具

给模型暴露只读工具，例如：

- `list_result_files()`
- `read_result_file(path, offset, limit)`

要求：

- 只允许访问当前 run 下的受控目录
- 只允许只读
- 必须支持分页
- 返回内容必须有清晰的 offset / limit / has_more 语义

#### C. 超大结果检测

对工具返回内容进行标准化后估算大小：

- 若未超过阈值，原样返回
- 若超过阈值，触发 spill

大小判断建议：

- 优先按字符数近似 token 数
- 可配置 `chars_per_token = 4`
- 或在后续落地中接模型 tokenizer 做精确估计

#### D. Artifact 落盘

将内容写入项目自己的 artifact store，而不是 DeepAgent backend。

建议路径模型：

```text
artifacts/runs/{run_id}/tool_results/{tool_call_id}.json
```

或对象存储 key：

```text
run/{run_id}/query/{query_id}/tool/{tool_call_id}
```

#### E. 引用回写

返回给模型的不是原始大结果，而是：

- artifact_id
- tool_call_id
- 内容摘要
- head / tail preview
- 如何继续分页读取的提示

### 6.6 建议的 state 扩展

中间件只需要极轻量 state：

```text
artifact_spill_state
- spilled_artifacts: dict[artifact_id, ArtifactRef]
- last_spilled_tool_call_id: optional[str]
```

`ArtifactRef` 建议字段：

```text
ArtifactRef
- artifact_id
- run_id
- query_id
- tool_call_id
- source_tool
- content_type
- char_count
- row_count(optional)
- storage_uri
- created_at
```

注意：

- state 里只存引用，不存大内容本体

### 6.7 建议的 ArtifactStore 抽象

建议定义项目自己的协议，而不是复用 `deepagents` backend：

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

    async def delete_expired(self, *, before: datetime) -> int: ...
```

实现建议：

- 开发环境：本地文件系统
- 生产环境：对象存储或专门 artifact bucket

### 6.8 建议暴露给模型的文件工具

这里要明确修正一个点：

- 如果洞察节点真正走文件中间件模式，那么模型至少要有“结果文件读取”能力，而不只是“溢出后补救读取”能力

不要暴露 DeepAgent 那种通用文件工作区能力，但应暴露受控的只读文件工具。

#### 工具 1：`list_result_files`

用途：

- 列出当前 run 下可供洞察节点读取的结果文件

输入：

- 无

返回建议：

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

#### 工具 2：`read_result_file`

用途：

- 分页读取当前 run 下的结果文件

输入建议：

```json
{
  "path": "/runs/{run_id}/query_result.jsonl",
  "offset": 0,
  "limit": 200
}
```

返回建议：

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

#### 工具 3：`read_spilled_artifact`

用途：

- 读取被中间件二次 spill 的超大工具结果

这是补充工具，不应再是唯一文件读取工具。

### 6.9 建议的 hook 设计

#### `awrap_tool_call`

这是核心 hook。

执行顺序：

1. 调用真实工具
2. 标准化工具结果为字符串
3. 判断是否超过 `spill_threshold`
4. 若超过：
   - 写入 artifact store
   - 更新 state 中的 artifact ref
   - 返回压缩后的 `ToolMessage`
5. 若未超过：
   - 原样返回

#### `awrap_model_call`

这是可选 hook。

只做一件事：

- 如果当前运行开启了 `InsightFilesystemMiddleware`，则给 system prompt 追加简短规则：
  - 结果文件是主探索入口
  - 需要更多数据时优先调用 `read_result_file`
  - 当工具结果提示已 spill 到 artifact store 时，再调用 `read_spilled_artifact`

不要在这里注入冗长的文件系统操作说明。

### 6.10 建议的主文件提示文本

进入洞察节点后，应先向模型暴露主结果文件，例如：

```text
Primary result file available:

- path: /runs/{run_id}/query_result.jsonl
- rows: 18342
- format: jsonl

Use `read_result_file(path="/runs/{run_id}/query_result.jsonl", offset=0, limit=200)` to inspect it incrementally.
```

### 6.11 建议的 spill 提示文本

中间件返回给模型的文本建议类似：

```text
Tool result too large. The full result was stored as artifact `artifact_123`.

Source tool: read_filtered_data
Estimated rows: 1842

Preview:
1: ...
2: ...
...
1838: ...
1839: ...

Use `read_spilled_artifact(artifact_id="artifact_123", offset=0, limit=200)` to read it incrementally.
```

### 6.12 建议替换当前洞察工具集

当前工具集：

- `read_data_batch`
- `read_filtered_data`
- `get_column_stats`
- `get_data_profile`
- `finish_insight`

建议重构后工具集：

- `list_result_files`
- `read_result_file`
- `get_column_stats`
- `get_data_profile_summary`
- `finish_insight`

可选补充：

- `read_spilled_artifact`

调整原则：

- `read_filtered_data` 不再作为主探索工具
- 如果保留过滤工具，也应返回文件引用而不是直接回大 JSON
- `get_data_profile` 应降级为画像摘要工具，而不是洞察主入口

### 6.13 工具排除策略

建议默认排除以下工具：

- `finish_insight`

可按实际情况排除：

- `get_column_stats`

默认不排除但重点监控：

- `read_filtered_data`
- `get_data_profile`
- `read_data_batch`

原因：

- `read_data_batch` 虽然有 `limit <= 200`，但行字段多时仍可能变大

### 6.14 配置建议

```yaml
agents:
  middleware:
    insight_filesystem:
      enabled: true
      spill_threshold_tokens: 2000
      chars_per_token: 4
      preview_head_lines: 5
      preview_tail_lines: 5
      max_read_lines_per_call: 200
      artifact_ttl_hours: 24
      excluded_tools:
        - finish_insight
```

### 6.15 代码骨架建议

下面是建议实现骨架，供后续真正落地时使用：

```python
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse, ToolCallRequest
from langchain.tools import tool
from langchain_core.messages import ToolMessage


class InsightFilesystemMiddleware(AgentMiddleware):
    state_schema = InsightFilesystemState

    def __init__(
        self,
        *,
        artifact_store: ArtifactStore,
        spill_threshold_tokens: int = 2000,
        chars_per_token: int = 4,
        preview_head_lines: int = 5,
        preview_tail_lines: int = 5,
        excluded_tools: set[str] | None = None,
    ) -> None:
        self._artifact_store = artifact_store
        self._spill_threshold_tokens = spill_threshold_tokens
        self._chars_per_token = chars_per_token
        self._preview_head_lines = preview_head_lines
        self._preview_tail_lines = preview_tail_lines
        self._excluded_tools = excluded_tools or {"finish_insight"}

        @tool
        async def list_result_files() -> str:
            return self._list_primary_files_json()

        @tool
        async def read_result_file(
            path: str,
            offset: int = 0,
            limit: int = 200,
        ) -> str:
            result = await self._artifact_store.read_slice_by_path(
                path=path,
                offset=offset,
                limit=limit,
            )
            return result.model_dump_json()

        @tool
        async def read_spilled_artifact(
            artifact_id: str,
            offset: int = 0,
            limit: int = 200,
        ) -> str:
            result = await self._artifact_store.read_slice(
                artifact_id=artifact_id,
                offset=offset,
                limit=limit,
            )
            return result.model_dump_json()

        self.tools = [list_result_files, read_result_file, read_spilled_artifact]

    async def awrap_model_call(self, request: ModelRequest, handler):
        request = self._append_artifact_reading_hint(request)
        return await handler(request)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        result = await handler(request)

        if request.tool_call["name"] in self._excluded_tools:
            return result

        content = self._normalize_result_to_text(result)
        if not self._should_spill(content):
            return result

        artifact_ref = await self._spill_content(content, request)
        replacement = self._build_replacement_message(content, artifact_ref, request)
        return ToolMessage(
            content=replacement,
            tool_call_id=request.tool_call.get("id", ""),
            name=request.tool_call.get("name"),
        )
```

### 6.16 为什么这版设计比当前洞察节点更合适

因为它：

- 把“文件”变成洞察节点的一等输入，而不是补救措施
- 不再让模型过度依赖 `DataProfile` 摘要
- 支持真正的增量读取
- 能把大结果控制在可治理范围内
- 更符合“基于全量结果文件做洞察”的要求

### 6.17 为什么这版设计比直接搬 DeepAgent 更适合本项目

因为它：

- 只做洞察节点真正需要的文件读取和大结果溢出保护
- 不把项目引向通用文件代理范式
- 不引入 shell、edit、write、grep、glob 权限面
- 和 `run_id / query_id / artifact` 体系天然一致
- 更符合 `LangGraph state 只存引用` 的原则

---

## 7. 中间件最终策略

### 7.1 HTTP 层

保留：

- `CORSMiddleware`
- 自定义 `RequestContextMiddleware` 或现有 `RequestLoggingMiddleware` 的轻量版
- FastAPI exception handlers

不建议新增：

- 自定义 CORS
- 自定义通用错误 middleware
- 自定义参数校验 middleware

建议将当前 `RequestLoggingMiddleware` 重命名和收缩为：

- `RequestContextMiddleware`

职责仅保留：

- `request_id`
- `trace_id`
- 日志上下文
- 响应头回写

### 7.2 Graph 运行层

不应存在“Graph middleware”概念泛化。

Graph 层应使用：

- node
- subgraph
- checkpoint
- interrupt
- streaming

不要把原本属于节点或运行时的事再包装成一层自定义 graph middleware。

### 7.3 LLM / Agent 层

建议最终策略：

- `semantic_graph`
  - 通常不使用 agent middleware
  - 主要走 structured output + graph node
- `query_graph`
  - 不使用 agent middleware
  - 纯确定性
- `answer_graph`
  - 若使用工具型 insight agent，则允许：
    - `ModelRetryMiddleware`
    - `ToolRetryMiddleware`
    - `SummarizationMiddleware`
    - `InsightFilesystemMiddleware`

### 7.4 不要让中间件承担主编排职责

中间件只负责横切面：

- retry
- summarization
- spill guard
- redaction

不负责：

- 主业务状态机
- query planning
- permission routing
- datasource resolution

---

## 8. 目标架构

### 8.1 总体分层

最终后端分五层：

1. API 控制层
2. LangGraph 运行层
3. 领域服务层
4. 存储与缓存层
5. Artifact 与索引层

### 8.2 各层职责

| 层 | 负责什么 | 不负责什么 |
|---|---|---|
| API 控制层 | 鉴权、请求校验、SSE / WebSocket 转发、CRUD API | 工作流总控 |
| LangGraph 运行层 | `root_graph`、子图、state、interrupt、checkpoint、streaming | 业务数据库 |
| 领域服务层 | datasource 解析、metadata 加载、query plan、query execute、answer 组装 | 直接处理 HTTP |
| 存储与缓存层 | 业务数据、运行 checkpoint、缓存、审计日志 | 用空结果掩盖故障 |
| Artifact 与索引层 | metadata snapshot、field semantic、field sample、retrieval index、spilled artifacts | 在线主链默认重建 |

### 8.3 目标目录建议

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

## 9. LangGraph 运行主干

### 9.1 根图

整个后端收敛到一个 `root_graph`。

关键规则：

- `thread_id = session_id`
- graph 输入是已校验的一轮请求
- graph 输出是最终答案或 interrupt payload
- graph 挂 durable checkpointer

### 9.2 子图划分

`root_graph` 拆成四个子图：

1. `context_graph`
2. `semantic_graph`
3. `query_graph`
4. `answer_graph`

#### `context_graph`

负责：

- 读取 session / settings / history summary
- 解析 tenant context
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
- Tableau query execute
- normalize result
- query error 分类

#### `answer_graph`

负责：

- insight generate
- replan decide
- follow-up interrupt
- persist run artifacts

---

## 10. 节点设计

### 10.1 入口与上下文节点

| 节点 | 类型 | 输入 | 输出 | 失败语义 |
|---|---|---|---|---|
| `ingress_validate` | 确定性 | 原始请求 | `ValidatedRunRequest` | 4xx |
| `hydrate_business_context` | 确定性 | session_id / user_id | session/settings/history summary | `SESSION_NOT_FOUND` |
| `resolve_tenant_context` | 确定性 | 应用身份、配置 | tenant context | `TENANT_AUTH_ERROR` |
| `resolve_tableau_auth` | 确定性 | tenant context | auth handle ref | `TABLEAU_AUTH_ERROR` |
| `resolve_datasource_identity` | 确定性 | datasource selector | datasource identity | interrupt 或 `DATASOURCE_RESOLUTION_ERROR` |
| `load_metadata_snapshot` | 确定性 | datasource identity | snapshot ref + schema_hash | `METADATA_LOAD_ERROR` |
| `load_ready_artifacts` | 确定性 | datasource_luid/schema_hash | artifact refs | warning 或 degraded |

### 10.2 语义节点

| 节点 | 类型 | 输入 | 输出 | 失败语义 |
|---|---|---|---|---|
| `retrieve_semantic_candidates` | 确定性 | question + artifact refs | 候选字段和值 | degraded |
| `semantic_parse` | LLM 结构化 | question + metadata hints | `SemanticParseOutput` | `SEMANTIC_PARSE_ERROR` |
| `semantic_guard` | 确定性 | 语义输出 + metadata | 校验结果或澄清请求 | `SEMANTIC_VALIDATION_ERROR` 或 interrupt |
| `clarification_interrupt` | interrupt | clarification payload | 挂起 | 等待 resume |

### 10.3 查询节点

| 节点 | 类型 | 输入 | 输出 | 失败语义 |
|---|---|---|---|---|
| `build_query_plan` | 确定性 | 校验后语义输出 | query plan | `QUERY_PLAN_ERROR` |
| `execute_tableau_query` | IO + 确定性 | query plan + auth | raw result | `QUERY_EXECUTION_ERROR` / `TABLEAU_TIMEOUT` / `TABLEAU_PERMISSION_ERROR` |
| `normalize_result_table` | 确定性 | raw result + metadata | normalized result ref | `RESULT_NORMALIZATION_ERROR` |

### 10.4 答案节点

| 节点 | 类型 | 输入 | 输出 | 失败语义 |
|---|---|---|---|---|
| `insight_generate` | LLM 结构化 | semantic + normalized table + metadata hints | answer/evidence/caveats/followups | `INSIGHT_GENERATION_ERROR` |
| `replan_decide` | 确定性或 LLM 结构化 | answer + profile + run history | stop / auto_continue / user_select | `REPLAN_DECISION_ERROR` |
| `followup_interrupt` | interrupt | candidate followups | 挂起 | 等待 resume |
| `persist_run_artifacts` | 确定性 | run summary | 落库 / 审计 | `RUN_PERSISTENCE_ERROR` |
| `finalize_stream` | 确定性 | final state | complete event | N/A |

---

## 11. 状态模型

### 11.1 根状态

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

### 11.2 各状态域

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
- `spilled_artifact_refs`
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

### 11.3 状态设计原则

state 里只放：

- ID
- 引用
- 摘要
- 小型结构化结果

state 里不放：

- 大块 metadata 原文
- 全量表格数据
- 全量 SSE 事件历史
- 原始 secret

---

## 12. LangChain 使用边界

LangChain 负责：

- 模型实例抽象
- provider 切换
- structured output
- tool binding
- agent middleware

LangChain 不负责：

- 全局工作流编排
- 业务主数据库
- 主运行状态机

structured output 策略：

1. provider 支持时优先用 provider-native structured output
2. 不支持时退到 tool strategy
3. 只在兼容场景下保留 prompt 注入 schema fallback

建议结构化模型：

- `SemanticParseOutput`
- `ClarificationRequest`
- `InsightOutput`
- `ReplanDecision`
- `FollowupSelectionRequest`

---

## 13. Tableau 领域服务设计

Tableau 层只保留三个只读服务：

### 13.1 `resolve_datasource`

输入优先级：

1. 前端直接传 `datasource_luid`
2. `site + project_name + exact datasource_name`

生产主链禁止：

- prefix 自动命中
- fuzzy 自动命中
- 全量扫描后取第一个返回

### 13.2 `load_metadata_snapshot`

职责：

- 读取 field metadata
- 生成 / 恢复 `schema_hash`
- 记录快照时间
- 返回 snapshot ref

不应在线默认做：

- 重建大索引
- 拉起重型 field semantic 任务

### 13.3 `query_datasource`

职责：

- 执行确定性 VizQL 请求
- 分类错误
- 返回原始结果和执行元数据

必须禁止：

- 执行未经校验的自由文本 LLM 查询
- 把上游失败伪装成空结果

---

## 14. 数据、缓存与 Artifact 设计

### 14.1 业务存储最终建议

建议业务表：

- `chat_sessions`
- `chat_messages`
- `analysis_runs`
- `analysis_interrupts`
- `user_settings`
- `message_feedback`
- `tableau_metadata_snapshots`
- `query_audit_logs`
- `run_artifacts`

### 14.2 存储分层

- 业务实体：Postgres
- workflow checkpoints：LangGraph checkpointer
- 短期缓存：Redis
- 大型 artifact：对象存储 / 文件存储 / 向量存储

### 14.3 缓存键建议

```text
tableau:token:{domain}:{site}:{principal}:{auth_method}:{scope_hash}
tableau:metadata:{site}:{datasource_luid}:{schema_hash}
tableau:fieldvals:{site}:{datasource_luid}:{field_name}
artifact:spill:{run_id}:{tool_call_id}
```

规则：

- 必须有租户维度
- 必须有 TTL
- cache miss 不能改变业务语义

---

## 15. DDL 采用策略

这一节吸收 `backend_refactoring_plan.md` 的优点，但不原样照搬。

### 15.1 可以直接吸收的思路

- `sessions / messages / workflow_runs / feedback` 这类关系表拆分方式
- `query_cache`、`field_semantic_cache` 的单独建表思路
- 事件日志与查询快照分表的想法

### 15.2 需要修正的地方

#### A. `workflow_runs` 应改为 `analysis_runs`

并补齐关键字段：

- `thread_id`
- `request_id`
- `trace_id`
- `query_id`
- `schema_hash`
- `site`
- `project_name`

#### B. 必须新增 `analysis_interrupts`

这是 graph-native 方案下的一等公民。

最少字段：

- `id`
- `run_id`
- `thread_id`
- `interrupt_type`
- `payload_json`
- `status`
- `resolved_at`
- `resume_payload_json`

#### C. `workflow_event_log` 不能承担主 resume 语义

如果保留事件日志，只能用于：

- 调试
- 观测
- 可选的前端断线后事件回放

不能把它当成真正的“恢复执行”机制。

真正的 resume 语义必须来自：

- LangGraph checkpoint
- `interrupt_id + resume_payload`

#### D. `query_cache` 和 `field_semantic_cache` 必须带租户维度

至少补：

- `site`
- `schema_hash`

必要时补：

- `domain`
- `principal_scope`

### 15.3 最终建议表

最终建议优先落地这些表：

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

---

## 16. API、SSE 与 Resume 最终契约

### 16.1 `POST /api/chat/stream`

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

### 16.2 `POST /api/chat/resume`

用途：

- 恢复一个被 interrupt 挂起的 graph 执行

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

注意：

- 这个接口是“恢复执行”
- 不是“断线后事件重放”

### 16.3 可选的事件回放接口

如果前端确实需要“断线后补事件”，建议单独设计为：

- `GET /api/runs/{run_id}/events?after=N`

或：

- `POST /api/chat/replay`

不要让 `resume` 同时承担两种完全不同的语义。

### 16.4 SSE 事件最终收敛建议

建议最终稳定事件只保留：

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

不建议长期保留过细且高度实现绑定的事件类型：

- `candidate_questions`
- `suggestions`
- `planner`
- `plan_step`
- `chart`
- `thinking_token`

如果确实需要其中一部分，应把它们折叠为 `custom` 业务事件，而不是让协议继续膨胀。

### 16.5 Streaming 语义

建议直接对齐 LangGraph：

- `messages`：模型 token
- `updates`：状态迁移 / 节点更新
- `custom`：领域事件

API 层只做 SSE 封装，不再自创一套新的运行语义。

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

每次运行至少要串起这些键：

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
- token usage per node
- artifact spill count
- artifact readback count

---

## 18. 安全设计

硬规则：

- 生产主链禁止 fuzzy datasource binding
- 不满足加密要求时禁止持久化原始 API key
- 对外错误信息禁止泄露路径、secret、token
- 所有缓存必须带租户维度
- 空结果和执行失败必须明确区分
- 分析 agent 不默认拥有 shell / 文件编辑能力

对中间件的特别要求：

- `InsightFilesystemMiddleware` 必须是洞察节点专用只读文件中间件
- 不能借机扩展成通用文件操作接口
- artifact 访问必须带运行范围校验

---

## 19. 迁移实施路线

### Phase 0：先稳边界

交付：

- run_id / error code
- datasource identity 策略收紧
- token cache key 收紧
- storage error 分类

验收：

- 不再出现模糊 datasource 命中
- 多 site / principal 不串 token
- 上游故障不再被解释成空结果

### Phase 1：引入 root graph 骨架

交付：

- `root_graph` shell
- checkpointer 接入
- API compatibility adapter

验收：

- `/api/chat/stream` 对前端无破坏
- `thread_id = session_id`

### Phase 2：迁移 semantic runtime

交付：

- semantic child graph
- clarification interrupt / resume
- state 收缩

验收：

- clarification 可跨进程恢复

### Phase 3：迁移 query runtime

交付：

- query plan node
- Tableau execute node
- normalize node

验收：

- permission failure / timeout / empty result 稳定区分

### Phase 4：迁移 answer runtime

交付：

- structured insight node
- structured replanner node
- follow-up interrupt

验收：

- follow-up selection 不再依赖自定义 executor 协议

### Phase 5：迁移业务存储

交付：

- Postgres repository
- 正式业务表
- feedback 到 run/query/message 的完整绑定

验收：

- 分页原生数据库化
- repository 故障不再表现成 not found

### Phase 6：引入自研 `InsightFilesystemMiddleware`

交付：

- `ArtifactStore` 抽象
- `InsightFilesystemMiddleware`
- `list_result_files` / `read_result_file`
- `read_spilled_artifact`
- spill 计数与审计
- 主结果文件生命周期管理

验收：

- 洞察节点以结果文件为主探索入口
- `read_filtered_data` 等大结果不再直接挤爆上下文
- 模型可通过 `read_result_file` 和 `read_spilled_artifact` 分页读取
- 不引入 shell、edit、write 等额外权限面

### Phase 7：下线旧 executor

交付：

- graph-native runtime bridge
- 移除 executor-specific event logic

验收：

- 所有生产聊天链路都以 `root_graph` 为主

---

## 20. 最终保留 / 替换建议

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
- `agents/base/middleware_runner.py`

建议拆解或替换：

- `orchestration/workflow/executor.py`
- `platform/tableau/data_loader.py`
- `platform/tableau/client.py`
- `infra/storage/repository.py`
- `deepagents.FilesystemMiddleware` 依赖

---

## 21. 最终建议

当前项目下一阶段最重要的不是继续优化 `WorkflowExecutor`，而是：

- 把 LangGraph 从“局部语义子图”提升为“全局运行主干”
- 把中间件从“框架能力混用 + 第三方代理能力借用”收敛为“只复用必要框架能力 + 仅对项目缺口自研”

最终原则只有三条：

1. 能用 FastAPI / LangChain / LangGraph 现成能力的，不重复造轮子。
2. 真正需要自研的，只做项目缺口，不把通用代理框架整套搬进来。
3. 任何中间件都不允许越权成为主编排器。

对本项目而言，这意味着：

- HTTP 层继续用框架自带能力
- Agent 层继续用 LangChain 自带 retry / summarization
- 洞察节点自研一个参考 DeepAgent、但职责收缩后的 `InsightFilesystemMiddleware`

这条路线最符合当前代码现状、团队维护成本和后续演进方向。
