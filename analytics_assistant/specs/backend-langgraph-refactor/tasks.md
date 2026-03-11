# Backend Refactor Tasks

> 状态: Draft v1.0
> 读取顺序: 12/12
> 上游文档: [requirements.md](./requirements.md), [design.md](./design.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [migration.md](./migration.md)
> 下游文档: 无
> 说明: 该文件用于项目排期和任务拆分，按阶段与依赖组织。

## 1. 架构与运行时

- [ ] 1.1 定义 `root_graph` 输入输出契约
  - 依赖: `requirements.md` 第 2 章, `design.md` 第 4 章
  - 产出: `RunState`、graph 输入模型、stream 输出模型

- [ ] 1.2 建立 `thread_id = session_id` 的运行线程模型
  - 依赖: `design.md` 第 4 章, `data-and-api.md` 第 3 章
  - 产出: checkpointer 接入方案

- [ ] 1.3 搭建 `context_graph / semantic_graph / query_graph / answer_graph` 子图骨架
  - 依赖: `design.md` 第 5 章
  - 产出: 子图边界和节点清单

## 2. 安全边界

- [ ] 2.1 修正 Tableau token cache key
  - 依赖: `requirements.md` 第 5 章需求 B, `data-and-api.md` 第 4 章

- [ ] 2.2 重写 datasource identity 解析规则
  - 依赖: `requirements.md` 第 5 章需求 B, `design.md` 第 5.1 节

- [ ] 2.3 修正 metadata cache key 和 artifact key
  - 依赖: `data-and-api.md` 第 3 章和第 4 章

## 3. API 与契约

- [ ] 3.1 收敛 `POST /api/chat/stream` 输入模型
  - 依赖: `data-and-api.md` 第 5.1 节

- [ ] 3.2 定义 `POST /api/chat/resume` 为 interrupt 恢复接口
  - 依赖: `requirements.md` 第 5 章需求 E, `data-and-api.md` 第 5.2 节

- [ ] 3.3 收敛 SSE 事件为稳定业务事件
  - 依赖: `data-and-api.md` 第 6 章

- [ ] 3.4 对齐 interrupt payload 与 resume payload 契约
  - 依赖: `interrupt-playbook.md`, `data-and-api.md` 第 6.4 与第 7 章

- [ ] 3.5 对齐节点错误码与 API 错误码目录
  - 依赖: `node-catalog.md` 第 1-6 章, `data-and-api.md` 第 8 章

## 4. 语义解析与查询

- [ ] 4.1 迁移 `semantic_parse` 到 schema-first 结构化输出
  - 依赖: `requirements.md` 第 5 章需求 C, `design.md` 第 5.2 节

- [ ] 4.2 实现 `semantic_guard` 的确定性校验
  - 依赖: `design.md` 第 5.2 节

- [ ] 4.3 保留并接管现有 `query_builder` 与 `adapter`
  - 依赖: `design.md` 第 7 章

- [ ] 4.4 实现 `normalize_result_table` 与 `materialize_result_artifacts`
  - 依赖: `design.md` 第 5.3 节, `data-and-api.md` 第 3 章

## 5. 中间件与洞察

- [ ] 5.1 盘点并保留现有框架内建 middleware
  - 依赖: `middleware.md` 第 2 章
  - 说明: 明确 `ModelRetryMiddleware`、`ToolRetryMiddleware`、`SummarizationMiddleware` 的使用边界

- [ ] 5.2 设计 `ArtifactStore` 与 `InsightWorkspaceManager`
  - 依赖: `middleware.md` 第 7 章, `data-and-api.md` 第 3 章

- [ ] 5.3 实现 `InsightFilesystemMiddleware`
  - 依赖: `middleware.md` 第 6 章

- [ ] 5.4 实现结果文件工具
  - 依赖: `middleware.md` 第 6.5 节
  - 产出: `list_result_files`, `describe_result_file`, `read_result_file`, `read_result_rows`, `read_spilled_artifact`

- [ ] 5.5 将洞察 agent 改为文件驱动探索
  - 依赖: `requirements.md` 第 5 章需求 D, `design.md` 第 8 章

- [ ] 5.6 实现全量统计与洞察工件生成
  - 依赖: `insight-large-result-design.md` 第 2 章
  - 说明: 生成 `profiles/*` 和 `result_manifest.json`

- [ ] 5.7 建立洞察重规划闭环
  - 依赖: `insight-large-result-design.md` 第 4 章与第 5 章

## 6. 存储与数据层

- [ ] 6.1 建立业务表 DDL
  - 依赖: `data-and-api.md` 第 2 章

- [ ] 6.2 接入 LangGraph checkpointer
  - 依赖: `data-and-api.md` 第 3.1 节

- [ ] 6.3 建立 artifact 目录规范和 manifest 格式
  - 依赖: `middleware.md` 第 6.4 节, `data-and-api.md` 第 3.2 节

- [ ] 6.4 将 sessions/settings/feedback 从通用 repository 中迁出
  - 依赖: `design.md` 第 7 章, `migration.md` Phase 7

## 7. 测试与发布

- [ ] 7.1 为 `interrupt/resume` 建立图级测试
  - 依赖: `design.md` 第 4.3 节, `migration.md` 第 2 章

- [ ] 7.2 为 datasource 安全和 token 隔离建立回归测试
  - 依赖: `requirements.md` 第 4.2 节

- [ ] 7.3 为洞察文件工具建立分页和越界测试
  - 依赖: `middleware.md` 第 6.8 节

- [ ] 7.4 制定灰度和回滚开关
  - 依赖: `migration.md` 第 4 章

- [ ] 7.5 建立 SSE 契约测试
  - 依赖: `data-and-api.md` 第 6 章

- [ ] 7.6 建立端到端冒烟测试
  - 依赖: `migration.md` 第 2 章

- [ ] 7.7 建立性能基准测试
  - 依赖: `design.md` 第 6 章
