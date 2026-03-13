# SSE Event Catalog

> Status: Draft v1.1
> Read order: 12/14
> Upstream: [data-and-api.md](./data-and-api.md), [node-catalog.md](./node-catalog.md)
> Downstream: [migration.md](./migration.md), [tasks.md](./tasks.md)

## 0. 版本策略（破坏式升级）

- 本目录定义 `SSE v2`，采用破坏式升级。
- 旧事件命名与旧扁平 payload（如 `clarification`、`node_complete`）不再作为后端兼容目标。
- `candidate_questions`、`suggestions` 等旧 follow-up 事件名不再允许出现在 API 输出或内部投影边界。
- 后端以本文件为唯一事件契约，前端在后续重构阶段整体对齐。

## 1. 统一事件外壳

所有 SSE 事件建议使用统一字段：

```json
{
  "type": "status",
  "request_id": "req_001",
  "session_id": "sess_001",
  "thread_id": "sess_001",
  "run_id": "run_001",
  "timestamp": "2026-03-11T10:00:00Z",
  "data": {}
}
```

## 1.1 展示语义约束

SSE v2 面向前端时，必须优先表达“用户正在看到什么”，而不是“后端内部正在跑哪个节点”。

约束：

- 前端不得把底层 LLM token 流和底层 graph 事件流直接作为两条裸露时间线展示。
- 普通用户视图只展示投影后的语义对象，不展示内部节点名、内部路由名、原始 thinking token。
- `thinking` 类输出如果存在，只能进入调试视图；正式视图必须压缩成稳定的进度或推理摘要。
- 一个事件如果不能直接让产品经理或设计师判断怎么渲染，就说明该事件还不是合格的前端契约。

推荐 UI 槽位：

- 主回答区：最终回答正文、洞察结论。
- 过程区：阶段状态、进度、自动补查状态。
- 决策卡片：interrupt、确认、follow-up 选择。
- 结果卡片：表格、指标、洞察摘要、证据。
- 附件区：artifact、下载文件、workspace 引用。

## 2. 事件类型

### 2.1 `status`

```json
{
  "type": "status",
  "data": {
    "stage":"semantic_parse",
    "message":"Parsing question",
    "display_channel":"activity_timeline"
  }
}
```

渲染建议：

- 展示为过程区短状态，不进入主回答正文。
- `stage` 用于埋点和调试，`message` 才是前端默认展示文本。

### 2.2 `parse_result`

```json
{
  "type": "parse_result",
  "data": {
    "intent":"trend_explain",
    "confidence":0.84,
    "display_channel":"activity_timeline",
    "summary":"已识别为趋势解释问题"
  }
}
```

渲染建议：

- 默认只展示 `summary` 这类人话摘要。
- `intent`、`confidence` 更适合开发调试，不应直接面向普通用户。

### 2.3 `interrupt`

```json
{
  "type": "interrupt",
  "data": {
    "interrupt_id": "int_002",
    "interrupt_type": "missing_slot",
    "display_channel":"decision_card",
    "payload": {
      "slot_name":"timeframe",
      "options":["last_7_days","last_30_days","last_90_days"]
    }
  }
}
```

渲染建议：

- 必须渲染成强交互卡片，不得退化为聊天气泡纯文本。
- `interrupt_type` 决定组件类型，`payload` 决定具体字段和按钮。

### 2.4 `table_result`

```json
{
  "type": "table_result",
  "data": {
    "row_count": 100000,
    "truncated": true,
    "result_manifest_ref": "artifacts/runs/run_001/result/result_manifest.json",
    "display_channel":"result_card",
    "title":"查询结果",
    "summary":"结果行数较多，当前已截断展示"
  }
}
```

渲染建议：

- 渲染为结果卡片，允许附带预览表和下载入口。
- 不要求前端自己从 `row_count` 和 `truncated` 拼中文说明。

### 2.5 `insight`

```json
{
  "type": "insight",
  "data": {
    "summary": "华东销售下降主要由产品线A导致",
    "evidence_refs": ["profiles/time_rollup_day.json"],
    "display_channel":"main_answer"
  }
}
```

渲染建议：

- 核心结论可直接进入主回答区。
- 证据、补充摘要、引用链接可同时进入结果卡片或附件区。

### 2.6 `replan`

```json
{
  "type": "replan",
  "data": {
    "decision":"auto_continue",
    "next_question":"按产品线拆分趋势",
    "display_channel":"activity_timeline"
  }
}
```

渲染建议：

- `auto_continue` 展示为过程区状态。
- 需要用户选择时，应转成 `interrupt_type=followup_select` 的决策卡片，而不是让前端解析 `replan` 再自行弹窗。

### 2.7 `complete`

```json
{
  "type": "complete",
  "data": {"status":"ok","display_channel":"system"}
}
```

### 2.8 `error`

```json
{
  "type": "error",
  "data": {
    "error_code": "QUERY_EXECUTION_ERROR",
    "node_error_code": "planner_runtime_budget_exceeded",
    "message": "Tableau timeout",
    "retryable": true,
    "display_channel":"error_banner"
  }
}
```

渲染建议：

- 优先展示用户可执行动作，例如“重试”“缩小范围”。
- 详细诊断信息只进入日志或调试视图，不进入普通用户主界面。
- `error_code` 必须是稳定的公共错误码；如果底层节点使用更细粒度的内部错误码，可以通过可选 `node_error_code` 透出给日志、调试或埋点。
