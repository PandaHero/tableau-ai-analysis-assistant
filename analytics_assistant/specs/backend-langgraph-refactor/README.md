# Analytics Assistant Backend Refactor Spec

> Status: Implemented v1.0
> Location: `analytics_assistant/specs/backend-langgraph-refactor`
> Read order: 1/15
> Upstream: none
> Downstream: [requirements.md](./requirements.md), [design.md](./design.md), [why-and-complex-analysis-design.md](./why-and-complex-analysis-design.md), [why-and-complex-analysis-implementation-notes.md](./why-and-complex-analysis-implementation-notes.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [insight-large-result-design.md](./insight-large-result-design.md), [node-catalog.md](./node-catalog.md), [node-io-schemas.md](./node-io-schemas.md), [interrupt-playbook.md](./interrupt-playbook.md), [sse-event-catalog.md](./sse-event-catalog.md), [migration.md](./migration.md), [tasks.md](./tasks.md)
> Related: [../../docs/backend_new_architecture_design.md](../../docs/backend_new_architecture_design.md), [../../docs/backend_final_refactor_plan.md](../../docs/backend_final_refactor_plan.md), [../../docs/backend_refactoring_plan.md](../../docs/backend_refactoring_plan.md)

## 1. 文档目标

这套 spec 是当前后端重构实现的正式说明，覆盖：

- `root_graph` 主干与状态机
- `context / semantic / query / answer` 子图分层
- `interrupt / resume / checkpoint`
- `retrieval / memory / freshness / rebuild`
- `why / complex analysis` 诊断型 planner
- API、SSE、存储分层、迁移与测试任务

## 2. 当前实现结论

当前实现已经完成以下主线收口：

- 顶层总控统一为 `LangGraph root_graph`
- 会话线程模型统一为 `thread_id = session_id`
- 复杂问题与 `why` 问题已纳入 root-native planner runtime
- 最终 `insight` 和最终 `replan` 已统一基于 `evidence_bundle`
- SSE v2、展示语义、错误码映射和关键合同测试已落地
- `tasks.md` 中的重构任务已全部完成

## 3. 推荐阅读顺序

1. [requirements.md](./requirements.md)
2. [design.md](./design.md)
3. [why-and-complex-analysis-design.md](./why-and-complex-analysis-design.md)
4. [why-and-complex-analysis-implementation-notes.md](./why-and-complex-analysis-implementation-notes.md)
5. [retrieval-and-memory.md](./retrieval-and-memory.md)
6. [middleware.md](./middleware.md)
7. [data-and-api.md](./data-and-api.md)
8. [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md)
9. [insight-large-result-design.md](./insight-large-result-design.md)
10. [node-catalog.md](./node-catalog.md)
11. [node-io-schemas.md](./node-io-schemas.md)
12. [interrupt-playbook.md](./interrupt-playbook.md)
13. [sse-event-catalog.md](./sse-event-catalog.md)
14. [migration.md](./migration.md)
15. [tasks.md](./tasks.md)

## 4. 文档分工

- `requirements.md`
  - 业务目标、硬约束、验收标准
- `design.md`
  - 总体分层、状态模型、运行主干
- `why-and-complex-analysis-design.md`
  - `why` 与复杂问题的目标诊断链路
- `why-and-complex-analysis-implementation-notes.md`
  - 当前 why / complex 实现说明与落地细节
- `retrieval-and-memory.md`
  - retrieval router、memory scope、失效矩阵
- `middleware.md`
  - 框架复用策略与通用中间件边界
- `data-and-api.md`
  - API、SSE、存储分层、公共契约
- `artifact-freshness-and-rebuild.md`
  - freshness、degrade、prewarm、incremental rebuild
- `insight-large-result-design.md`
  - 大结果洞察的文件化链路
- `node-catalog.md`
  - 核心节点职责、错误、interrupt
- `node-io-schemas.md`
  - 关键节点输入输出示例
- `interrupt-playbook.md`
  - interrupt / resume 标准流程
- `sse-event-catalog.md`
  - SSE v2 事件目录与 payload 规范
- `migration.md`
  - 存储、主干和运行时迁移方案
- `tasks.md`
  - 任务完成情况与阶段性备注

## 5. 当前架构摘要

```text
root_graph
  -> context_graph
  -> semantic_graph
  -> query_graph / planner_runtime
  -> answer_graph
```

其中：

- 简单问题：单轮 `semantic -> query -> answer`
- 复杂但单查可解问题：仍走单轮链
- 复杂多步问题：进入 planner runtime
- `why` 问题：进入诊断型 planner，包含 anomaly verification、axis ranking、screening wave、slice locate 和 cause synthesis

## 6. 旧文档映射

| 旧文档 | 新文档承接 |
| --- | --- |
| `docs/backend_new_architecture_design.md` | `design.md` + `data-and-api.md` + `migration.md` |
| `docs/backend_final_refactor_plan.md` | `requirements.md` + `middleware.md` + `why-and-complex-analysis-design.md` |
| `docs/backend_refactoring_plan.md` | `data-and-api.md` + `tasks.md` |
