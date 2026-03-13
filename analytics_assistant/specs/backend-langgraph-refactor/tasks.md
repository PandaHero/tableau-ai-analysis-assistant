# Backend Refactor Tasks

> Status: In Progress
> Read order: 14/14
> Upstream: [requirements.md](./requirements.md), [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [migration.md](./migration.md)
> Downstream: none

## 1. 主干与状态机

- [x] 1.1 定义 `root_graph` 输入/输出契约
- [x] 1.2 建立 `thread_id = session_id` 线程模型
- [x] 1.3 落地 `context_graph / semantic_graph / query_graph / answer_graph` 骨架
- [x] 1.4 建立最小 `RunState` 与 `*_ref` 状态规范
- [x] 1.5 将复杂 planner 主干收口到 `root_graph`
  进度：复杂问题已经进入 root-native planner runtime，支持 `analysis_plan / sub_questions / depends_on / evidence_context`、step interrupt/replay、并行波次与 synthesis 汇总。
- [x] 1.6 将 `candidate_questions` 固定为单活跃 follow-up branch
  进度：`user_select / auto_continue` 每次只会继续一个问题，不再 fan-out。

## 2. 安全边界

- [x] 2.1 修正 Tableau token cache key 维度
- [x] 2.2 重写 datasource identity 解析规则
- [x] 2.3 统一 metadata / artifact cache key 维度
  进度：`query_cache`、retrieval candidate refs、retrieval trace、memory audit、filter value memory、synonym memory 已按 `scope_key + datasource_luid` 分区，并补上统一失效服务；`TableauDataLoader` 的 `DataModel` 进程缓存、freshness artifact key 与字段索引物理命名现已统一纳入 `site + datasource + schema_hash` 维度，语义检索读取路径也会显式命中当前 schema 对应的字段索引。`field_semantic_index / field_values_index` 仍共用同一份物理字段索引，这部分属于 `6.4` 的 artifact 拆分问题，不再混在本任务里。
- [x] 2.4 固化文件工具只读与路径 allowlist 校验

## 3. API 与契约

- [x] 3.1 收敛 `POST /api/chat/stream` 请求模型
- [x] 3.2 新增 `POST /api/chat/resume` 并绑定 `session_id + interrupt_id`
- [x] 3.3 收敛 SSE 事件为稳定业务事件目录
- [x] 3.4 对齐 API 错误码与节点错误码映射
  进度：SSE `error` 事件现已统一输出稳定 API `error_code`，并在内部节点错误需要折叠时保留 `node_error_code`；当前 root-native planner 的 `planner_*` 运行时错误已映射到 `QUERY_PLAN_ERROR / QUERY_EXECUTION_ERROR`。
- [x] 3.5 完成 SSE v2 破坏式切换并移除剩余旧兼容层
  进度：`answer_graph / root_graph / WorkflowExecutor` 已不再发出 `candidate_questions / suggestions` 旧事件；API SSE 投影层对这两类旧事件显式拒绝，只接受 `replan` 作为唯一后续分析事件。
- [x] 3.6 落地 SSE 背压与有界队列策略
  进度：`WorkflowExecutor` 现已使用配置化有界 `asyncio.Queue(maxsize=...)` 承载 SSE 事件，队列满时会对工作流生产者形成自然背压；`root_graph` 原生流路径保持逐事件拉取，不再引入额外无界缓冲。
- [x] 3.7 定义展示语义投影协议
- [x] 3.8 隔离普通用户视图与内部 thinking/debug 信息

## 4. 语义与查询

- [x] 4.1 将语义解析迁移为 schema-first 输出
- [x] 4.2 落地 `semantic_guard` 的确定性校验
  进度：`semantic_guard` 现已显式区分 `verified / compiler_ready / allowed_to_execute`，并稳定输出 `query_contract_mode / query_contract_source`；`root_graph / WorkflowExecutor / planner_runtime` 在进入查询前统一应用这道确定性闸门。
- [x] 4.3 让查询计划完全由编译器构建
  进度：`query_adapter` 现已固定只输出 `compiler_input` 契约，不再在语义图内构建可执行 Tableau 查询；缓存命中也会归一到同一契约，查询阶段统一由 `query_graph` 编译并执行。
- [x] 4.4 完成结果归一化与 artifact materialize
- [x] 4.5 在 planner 中支持 `analysis_plan.sub_questions` DAG 执行
  进度：root-native planner 已支持无依赖 step 受控并行、有依赖 step 按顺序执行、并发上限、step 上限、运行预算与 synthesis 汇总。

## 5. 检索与记忆平面

- [x] 5.1 定义 `RetrievalRouter` 策略路由接口
- [x] 5.2 保留 exact / BM25 / embedding / hybrid / rerank 策略
- [x] 5.3 接入 `query_cache / fewshot / value_memory / synonym_memory`
- [x] 5.4 明确 memory scope 与失效矩阵
  进度：已落地统一 `MemoryInvalidationService`；schema 变化会清理旧 schema 依赖的 `query_cache`、retrieval candidate artifacts、`filter_value_memory`、`synonym_memory`；`scope_reset / datasource_reset` 也已具备正式实现与测试。
- [x] 5.5 落地 `retrieval_trace_ref` 与 memory audit writes
  进度：retrieval trace 与审计写入已生成稳定 ref，并纳入 `root_graph / parse_result` 契约。

## 6. 新鲜度与重建

- [x] 6.1 实现 artifact freshness state report
- [x] 6.2 落地 online degrade 策略与指标
  进度：`context_graph` 现已输出结构化 `degrade_details`、`artifact_refresh_scheduled` 与稳定 `context_metrics`，覆盖 `ready / stale / building / missing + refresh_not_scheduled` 在线路径；`root_graph` 与 SSE `complete/parse_result` 事件会原样透传这些可观测字段。
- [x] 6.3 实现异步 prewarm / refresh builder
  进度：`prepare_datasource_artifacts` 已收口到正式 `ArtifactBuilderRuntime`，具备 request-key 去重、配置化并发上限、有界队列、运行时快照指标，并把 refresh 调度从零散 `create_task` 收成统一 builder 入口；当前是单进程 builder runtime，不再是隐式后台协程路径。
- [x] 6.4 优先增量重建 field semantic / value artifacts
  进度：`field_semantic_index / field_values_index` 已独立物理刷新，并真正执行 `prefer_incremental` 的增量/全量切换；对当前 schema 已删除字段会执行 tombstone，避免旧字段残留在检索索引中；当前 schema 准备完成后也会清理同 datasource/site 下被替代的旧 schema 索引。

## 7. 洞察重构

- [x] 7.1 设计并接入 `InsightFilesystemMiddleware`
- [x] 7.2 提供五个只读文件工具
- [x] 7.3 将洞察从摘要驱动迁移为文件驱动
- [x] 7.4 建立洞察-重规划闭环与次数上限
  进度：`answer_graph` 现已在确定性投影层统一处理 `user_select / auto_continue`，并对 `replan_history` 应用配置化最大轮数硬限制；达到上限后会停止继续分支，不再依赖 replanner agent 自行兜底。

## 8. 存储迁移

- [x] 8.1 建立业务表 DDL（`sessions / messages / settings / feedback / runs / interrupts`）
- [x] 8.2 接入 LangGraph checkpointer
- [x] 8.3 完成 artifact 目录规范与 manifest 规范
- [x] 8.4 将 `sessions / settings / feedback` 从通用仓储迁移到业务仓储
  进度：API 依赖入口和路由当前已统一使用 `SessionRepository / SettingsRepository / FeedbackRepository` 等结构化业务仓储，运行态不再通过通用 `BaseRepository` 承载这些业务实体。

## 9. 测试与发布

- [x] 9.1 interrupt / resume 合同测试
- [x] 9.2 SSE 合同测试
- [x] 9.3 root_graph 端到端烟测
- [x] 9.4 性能基线与回归门槛
  进度：已统一 `PerformanceMonitor` 的 baseline file 契约，默认基线文件为 `performance_baseline.json`；已提交 root-native 主链的 committed baseline，并补了 `root_graph_native_stream_smoke` 的 regression gate 与性能 smoke 测试。
- [x] 9.5 shadow compare 与黄金集评估
  进度：已提交 `root_graph_golden_cases.yaml` 黄金集，并落地 `test_root_graph_golden_set.py`。当前 shadow compare 的语义收口为“当前新栈执行结果 vs 提交版黄金快照”，不再引入旧 executor 双轨比较。
- [x] 9.6 feature flag 灰度与回滚演练
  进度：已落地 `why_screening_wave` 功能开关，支持 `app.yaml` 全局默认、租户覆盖、会话覆盖与请求覆盖；关闭开关后 why 仍留在 root-native planner，只回退为不含 `screen_top_axes` 的 4 步计划，并补齐 root/semantic/API 回滚演练测试。
- [x] 9.7 SSE v2 合同测试覆盖旧事件拒绝与新事件 schema 校验
  进度：已覆盖 `candidate_questions` 旧事件拒绝、`replan` 新 schema 投影，以及节点错误码映射到公共 `error_code` 的合同测试。
- [x] 9.8 展示语义合同测试
- [x] 9.9 复杂 planner 场景测试
  进度：已覆盖 root-native planner、step interrupt / replay、parallel wave、step limit、runtime budget，以及 planner synthesis 后的 `user_select / auto_continue` 多轮闭环与单活跃 follow-up branch。
