# Backend Refactor Requirements

> Status: Draft v1.2
> Read order: 2/14
> Upstream: [README.md](./README.md)
> Downstream: [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [migration.md](./migration.md), [tasks.md](./tasks.md)

## 1. 背景

当前后端已经具备聊天入口、语义解析、Tableau 查询、洞察与重规划能力，但存在结构性问题：

- API 层承担了过多编排职责。
- `WorkflowExecutor` 过重，难以并行演进与灰度。
- 语义图仅作为局部子图，未形成全局运行主干。
- 检索、记忆、缓存新鲜度策略分散，缺少统一契约。
- 洞察阶段仍有“摘要驱动”路径，不适合大结果集。

## 2. 目标

### 2.1 架构目标

- 以 `LangGraph root_graph` 作为唯一运行主干。
- 会话级线程统一为 `thread_id = session_id`。
- 业务级人机交互统一为 `interrupt/resume`。
- API 层退化为薄控制层（鉴权、参数校验、流转换）。

### 2.2 数据与运行目标

- 业务表、运行状态、缓存、artifact 必须分层存储。
- 关键缓存键必须显式包含租户与数据源维度。
- datasource 解析默认禁止模糊命中。
- 在线请求路径默认不得触发全量重建。

### 2.3 洞察目标

- 洞察主入口必须是 `result_manifest` 与文件工具，而非摘要对象。
- 洞察阶段只读取必要片段，严格分页与限流。
- 允许 1 次低风险自动重规划，超限需用户确认。

## 3. 非目标

本轮不包含：

- 前端 UI 重写。
- Tableau Extension 协议重定义。
- LLM 供应商评测或模型效果专项优化。
- 一次性推倒重写全部模块。

## 4. 硬约束

### 4.1 复用优先

必须优先复用：

- FastAPI / Starlette：CORS、异常处理、请求校验。
- LangGraph：checkpointer、subgraph、interrupt、streaming。
- LangChain：模型/工具重试、摘要等通用 middleware。

仅在缺口明确时新增自研能力（如 `InsightFilesystemMiddleware`）。

### 4.2 安全约束

- 所有租户敏感缓存键必须包含租户维度。
- 文件工具默认只读，禁止越权路径。
- `resume` 必须绑定 `session_id + interrupt_id`。
- 必须区分 `EMPTY_RESULT` 与系统执行失败。

### 4.3 性能约束

- 在线链路默认不得触发全量 metadata/index rebuild。
- SSE 不得依赖无界队列承载无限事件。
- 大结果洞察必须通过分页文件读取控制 token 与内存成本。

## 5. 需求分组

### 需求 A：全局运行主干

1. 请求必须进入 `root_graph`，而非直接由旧 executor 总控。
2. 业务中断必须统一使用 `interrupt/resume`。
3. 同一 `session_id` 必须可跨进程恢复执行。

### 需求 B：租户与数据源安全

1. Tableau token key 必须包含：`domain + site + principal + auth_method + scopes`。
2. datasource 解析优先 `datasource_luid`。
3. `datasource_name` 非唯一时必须触发澄清中断。

### 需求 C：语义解析与查询编译

1. 语义解析输出必须 schema-first 且结构化。
2. 查询计划必须由确定性编译器构建。
3. 模型不得直接输出可执行 Tableau 查询并执行。

### 需求 D：文件驱动洞察

1. 洞察必须通过只读文件工具探索结果。
2. 结果文件必须支持分页、列裁剪、轻过滤与片段读取。
3. 模型只应拿到“引用 + 必要片段”，不应拿全量 JSON。

### 需求 E：检索与记忆平面

1. 检索必须保留 exact/BM25/embedding/hybrid/rerank 能力。
2. 记忆必须显式建模 `query_cache / fewshot / value memory / synonym learning`。
3. 记忆作用域必须绑定 `site + owner + datasource_luid + schema_hash + parser_version`。
4. 记忆写入必须可审计，可追踪到 `run_id/request_id`。

### 需求 F：Artifact 新鲜度

1. metadata identity 不匹配时必须硬失败。
2. semantic/value artifact 缺失时可按策略降级，但必须有显式 degrade 标记。
3. 优先增量重建，非必要不做全量重建。

### 需求 G：API 与 SSE 契约

1. `/api/chat/resume` 必须用于业务中断恢复，而非断线重放。
2. SSE 事件必须收敛到稳定业务事件模型。
3. API 错误码与节点错误码必须统一目录并映射。

### 需求 H：可观测与回归

1. 每轮运行必须关联 `request_id/session_id/thread_id/run_id/trace_id`。
2. 迁移期间必须支持 shadow compare 与黄金集评估。
3. 验收必须覆盖检索质量、缓存正确性、澄清率与答案可溯源性。

### 需求 I：复杂问题多步规划与重规划分支

1. `analysis_plan.sub_questions` 表示“回答同一个复杂主问题所需的内部执行步骤”，不是候选 follow-up 分支。
2. planner 必须支持 DAG 语义：有 `depends_on` 的步骤按依赖顺序执行；无依赖的 query steps 可以受控并行。
3. planner 并行执行必须受并发上限、总 step 数上限、单轮预算和高风险闸门约束，禁止无界 fan-out。
4. `synthesis` 步骤必须在依赖证据齐备后执行，只负责汇总前置步骤证据，不得绕过 query/guard 边界直接生成事实性结论。
5. `replan` 产出的 `candidate_questions` 表示“下一轮可能继续分析的候选分支”，每次运行只允许一个 active follow-up branch 继续。
6. `user_select` 与 `auto_continue` 都只能从 `candidate_questions` 中选择一个问题进入下一轮，禁止把多个候选问题同时展开执行。

## 6. 验收标准

### 6.1 架构验收

- API 入站后能稳定落到 `root_graph`。
- 同一会话在进程重启后可继续恢复。

### 6.2 安全验收

- 多租户并发不串 token。
- 同名 datasource 不会误绑定。
- 文件工具无法读取工作区外文件。

### 6.3 能力验收

- 大结果洞察不依赖一次性全量注入。
- interrupt/resume 五类场景可完整跑通。
- replan 与 insight 闭环可控，且存在次数上限。

### 6.4 运维验收

- 错误码稳定覆盖关键失败路径。
- 关键链路指标齐全：延迟、命中率、降级率、重建队列深度。
