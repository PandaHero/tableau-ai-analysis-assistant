# 后端代码审查与重构方案

> **审查范围**: `analytics_assistant/` 全部后端 Python 代码
> **框架基础**: FastAPI + LangChain + LangGraph
> **审查日期**: 2025-07

---

## 一、代码审查：问题清单

### 🔴 严重问题 (Critical)

| # | 文件 | 问题 | 影响 |
|---|------|------|------|
| C1 | `executor.py` (2155行) | **God Object 反模式** — 单文件 2155 行，`execute_stream()` 方法内定义了 20+ 个嵌套闭包函数，所有编排逻辑（认证、数据加载、图执行、查询执行、洞察生成、重规划、多步并行）全部耦合在一个 async generator 中 | 不可测试、不可维护、难以扩展 |
| C2 | `executor.py` | **闭包变量泄漏** — `_run_workflow()` 作为 `asyncio.create_task` 启动，其内部大量闭包捕获了外层 generator 的局部变量（`event_queue`, `stage_metrics`, `collected_metrics`, `replan_history_records` 等），形成隐式共享状态 | 并发安全隐患、GC 压力 |
| C3 | `sessions.py` / `settings.py` | **同步 I/O 阻塞事件循环** — Router 使用同步 `repo.save()` / `repo.find_all()` 等方法，FastAPI 会将其放入线程池执行，但 SQLite 的 `check_same_thread=False` 在多线程下无写锁保护 | 并发写入时数据损坏 |
| C4 | `store_factory.py` L241 | **SQLite 连接共享** — `sqlite3.connect(..., check_same_thread=False, isolation_level=None)` 创建单个连接供全局使用，`isolation_level=None` 开启 autocommit 模式，多线程并发写入无事务保护 | 数据不一致 |
| C5 | `dependencies.py` | **无 Repository 生命周期管理** — `BaseRepository` 通过 `lru_cache` 缓存为进程级单例，无连接池、无健康检查、无优雅关闭 | 长期运行内存泄漏 |

### 🟡 设计问题 (Design)

| # | 文件 | 问题 | 建议 |
|---|------|------|------|
| D1 | `context.py` (557行) | **WorkflowContext 职责过重** — 同时充当 DI 容器、认证管理器、字段语义加载器、缓存管理器，违反单一职责 | 拆分为 AuthContext + DataContext + FieldContext |
| D2 | `graph.py` + `executor.py` | **双层图执行** — `compile_semantic_parser_graph()` 编译为单例后在 `executor._run_workflow()` 中 `graph.astream()` 执行，但 executor 又在 `_execute_analysis_plan()` 中对同一 graph 二次 `ainvoke()`，形成递归调用 | 图编排与业务编排混杂 |
| D3 | `executor.py` | **SSE 事件契约未定义** — 20+ 种事件类型（`token`, `thinking`, `thinking_token`, `data`, `parse_result`, `insight`, `replan`, `candidate_questions`, `suggestions`, `planner`, `plan_step`, `clarification`, `error`, `complete`, `heartbeat`, `status`, `chart`）散落在代码中，无统一 schema 定义 | 需要契约文档 |
| D4 | `repository.py` | **find_all 全表扫描** — `find_all()` 先 `search(limit=1000)` 取全部数据再在 Python 层过滤，无索引利用 | 数据量大时性能差 |
| D5 | `chat.py` | **心跳与工作流超时重复实现** — chat router 有 `keepalive_interval` 心跳，executor 内部也有 30s 心跳和 `_timeout` 超时，逻辑重叠 | 统一到 executor 层 |
| D6 | `callbacks.py` | **节点名硬编码** — `_LLM_NODE_MAPPING` / `_VISIBLE_NODE_MAPPING` 通过字符串字面量绑定 LangGraph 节点名，新增节点需同步修改两处 | 枚举化或自动注册 |
| D7 | 跨模块 | **异常体系不统一** — `core/exceptions.py` 定义了 13 种异常，但 executor 中大量使用 `Exception` 基类 `except`，丢失了异常分类信息 | 异常需要分层处理 |
| D8 | `platform/base.py` | **PlatformRegistry 未实际使用** — 定义了完整的注册表模式，但 executor 中直接 `TableauAdapter(vizql_client=...)` 硬编码创建 | 注册表形同虚设 |
| D9 | `query_builder.py` | **过长的单一方法** — `build()` 方法处理维度、度量、计算、过滤器、排序，连同辅助方法共 1029 行，职责不清晰 | 按策略拆分 |
| D10 | `history.py` | **仅做 re-export** — 整个文件只是从 `agents/` 重新导出 `HistoryManager`，orchestration 层对 agents 层的依赖方向未真正解耦 | 定义接口而非 re-export |

### 🟢 代码风格问题 (Style)

| # | 范围 | 问题 |
|---|------|------|
| S1 | `query_builder.py` | 大量空行（几乎每行之间都有空行），文件膨胀约 40% |
| S2 | `schemas/__init__.py` | 同上，每个 import 之间都有空行 |
| S3 | `executor.py` | 日志消息中混用 f-string 和 `%s` 格式化，不一致 |
| S4 | 多处 | 中文注释和英文代码混合，部分注释与代码不一致 |
| S5 | `adapter.py` L92 | `logger.error(f"查询执行失败: {e}")` 后直接 `raise`，会在上层再次记录，日志重复 |

---

## 二、重构方案

### 2.1 核心设计原则

1. **分层架构**: API → Service → Orchestration → Agent → Platform → Infra
2. **依赖倒置**: 上层定义接口，下层实现；orchestration 通过 Protocol 依赖 agent
3. **单一职责**: 每个模块/类只做一件事
4. **契约先行**: SSE 事件、API 请求/响应全部先定义 schema
5. **可测试性**: 所有外部依赖可 mock，核心逻辑有单元测试

---

## 附件一：模块职责图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          API Layer (FastAPI)                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────┐  │
│  │ chat.py  │ │sessions  │ │settings  │ │feedback  │ │  health    │  │
│  │ (SSE)    │ │ (CRUD)   │ │ (CRUD)   │ │ (CRUD)   │ │  (probe)   │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────────┘  │
│       │             │            │             │                       │
│  ┌────┴─────────────┴────────────┴─────────────┴───┐                  │
│  │              Middleware & Dependencies            │                  │
│  │  auth / logging / error_handler / rate_limit      │                  │
│  └───────────────────────┬───────────────────────────┘                  │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────────────┐
│                   Service Layer (新增)                                  │
│  ┌───────────────────────┴───────────────────────────┐                  │
│  │              ChatService                           │                  │
│  │  - 会话管理、历史截断、SSE 生命周期                  │                  │
│  └───────────────────────┬───────────────────────────┘                  │
│  ┌───────────────────────┴───────────────────────────┐                  │
│  │              SessionService / SettingsService       │                  │
│  │  - 业务校验、默认值逻辑                              │                  │
│  └───────────────────────┬───────────────────────────┘                  │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────────────┐
│               Orchestration Layer (LangGraph)                          │
│  ┌───────────────────────┴───────────────────────────┐                  │
│  │          WorkflowOrchestrator (重构后)              │                  │
│  │  职责：仅编排，不含业务逻辑                          │                  │
│  │  - 认证阶段 → AuthStage                            │                  │
│  │  - 数据准备阶段 → DataPrepStage                    │                  │
│  │  - 语义解析阶段 → SemanticParserGraph              │                  │
│  │  - 查询执行阶段 → QueryExecutionStage              │                  │
│  │  - 洞察生成阶段 → InsightStage                     │                  │
│  │  - 重规划阶段 → ReplanStage                        │                  │
│  └──┬──────────┬──────────┬──────────┬───────────┬───┘                  │
│     │          │          │          │           │                       │
│  ┌──┴───┐ ┌───┴───┐ ┌───┴───┐ ┌───┴────┐ ┌───┴────┐                  │
│  │Auth  │ │Data   │ │Parser │ │Query   │ │Insight │                  │
│  │Stage │ │Prep   │ │Graph  │ │Exec    │ │Stage   │                  │
│  │      │ │Stage  │ │       │ │Stage   │ │        │                  │
│  └──────┘ └───────┘ └───────┘ └────────┘ └────────┘                  │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────────────┐
│                    Agent Layer (LangChain)                              │
│  ┌─────────────┐ ┌──────────────┐ ┌───────────┐ ┌──────────────┐      │
│  │ Semantic     │ │ Field        │ │ Insight   │ │ Replanner    │      │
│  │ Parser       │ │ Mapper       │ │ Agent     │ │ Agent        │      │
│  │ (LangGraph   │ │ (RAG+LLM)   │ │ (LLM)    │ │ (LLM)        │      │
│  │  子图 11节点) │ │              │ │           │ │              │      │
│  └─────────────┘ └──────────────┘ └───────────┘ └──────────────┘      │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────────────┐
│                  Platform Layer (适配器)                                │
│  ┌─────────────────────────────────────────────────────┐               │
│  │  PlatformAdapter Protocol (core/interfaces.py)      │               │
│  └──────────┬──────────────────────────┬───────────────┘               │
│       ┌─────┴──────┐            ┌──────┴──────┐                        │
│       │ Tableau    │            │ Future:     │                        │
│       │ Adapter    │            │ PowerBI /   │                        │
│       │ + Builder  │            │ Superset    │                        │
│       │ + VizQL    │            │             │                        │
│       └────────────┘            └─────────────┘                        │
└──────────────────────────┼──────────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────────────┐
│                   Infrastructure Layer                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ Storage  │ │ Cache    │ │ Config   │ │ LLM      │ │ Vector   │    │
│  │ (DB)     │ │ (Redis/  │ │ (YAML)   │ │ Provider │ │ Store    │    │
│  │          │ │  Memory) │ │          │ │          │ │ (RAG)    │    │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 各层职责说明

| 层 | 职责 | 不做什么 |
|---|------|----------|
| **API** | 请求验证、认证、SSE 流生命周期、HTTP 状态码 | 不含业务逻辑 |
| **Service** (新增) | 业务规则校验、会话管理、事件流组装 | 不直接调用 LLM |
| **Orchestration** | 多阶段工作流编排、超时控制、并行调度 | 不含 LLM prompt |
| **Agent** | LLM 调用、prompt 管理、输出解析 | 不含平台特定逻辑 |
| **Platform** | 语义输出 → 平台查询转换、查询执行 | 不含 LLM 调用 |
| **Infra** | 存储、缓存、配置、日志、LLM Provider | 无业务逻辑 |

---

## 附件二：完整时序图

### 2.1 主流程时序图（单次查询）

```
┌────┐    ┌─────┐    ┌───────────┐    ┌────────────┐    ┌────────┐    ┌────────┐    ┌────────┐
│User│    │ API │    │ChatService│    │Orchestrator│    │  Agent │    │Platform│    │  Infra │
└──┬─┘    └──┬──┘    └─────┬─────┘    └──────┬─────┘    └───┬────┘    └───┬────┘    └───┬────┘
   │         │             │                 │              │             │             │
   │ POST /api/chat/stream │                 │              │             │             │
   │ ───────>│             │                 │              │             │             │
   │         │             │                 │              │             │             │
   │         │ validate &  │                 │              │             │             │
   │         │ auth check  │                 │              │             │             │
   │         │ ───────────>│                 │              │             │             │
   │         │             │                 │              │             │             │
   │  SSE: connected       │                 │              │             │             │
   │ <───────│             │                 │              │             │             │
   │         │             │ truncate_history │              │             │             │
   │         │             │ ────────────────>│              │             │             │
   │         │             │                 │              │             │             │
   │         │             │  ┌──────────────┤              │             │             │
   │         │             │  │ Phase 1:     │              │             │             │
   │         │             │  │ Auth         │              │             │             │
   │         │             │  └──────────────┤              │             │             │
   │         │             │                 │ get_auth()   │             │             │
   │         │             │                 │ ─────────────┼─────────────┼────────────>│
   │         │             │                 │              │             │  JWT/PAT    │
   │         │             │                 │ <────────────┼─────────────┼─────────────│
   │         │             │                 │              │             │             │
   │  SSE: {"type":"thinking","stage":"preparing"}          │             │             │
   │ <───────│<────────────│<────────────────│              │             │             │
   │         │             │                 │              │             │             │
   │         │             │  ┌──────────────┤              │             │             │
   │         │             │  │ Phase 2:     │              │             │             │
   │         │             │  │ Data Prep    │              │             │             │
   │         │             │  └──────────────┤              │             │             │
   │         │             │                 │ load_data_model()          │             │
   │         │             │                 │ ─────────────┼────────────>│             │
   │         │             │                 │              │  VizQL API  │             │
   │         │             │                 │ <────────────┼─────────────│             │
   │         │             │                 │              │             │             │
   │         │             │                 │ load_field_semantic()      │             │
   │         │             │                 │ ─────────────┼─────────────┼────────────>│
   │         │             │                 │ <────────────┼─────────────┼─────────────│
   │         │             │                 │              │             │             │
   │         │             │  ┌──────────────┤              │             │             │
   │         │             │  │ Phase 3:     │              │             │             │
   │         │             │  │ Semantic     │              │             │             │
   │         │             │  │ Parse Graph  │              │             │             │
   │         │             │  └──────────────┤              │             │             │
   │         │             │                 │ graph.astream(state, config)│             │
   │         │             │                 │ ────────────>│             │             │
   │         │             │                 │              │             │             │
   │  SSE: {"type":"thinking","stage":"understanding"}      │             │             │
   │ <───────│<────────────│<────────────────│<─────────────│             │             │
   │         │             │                 │              │             │             │
   │  SSE: {"type":"token","content":"..."}  │   LLM call   │             │             │
   │ <───────│<────────────│<────────────────│<─────────────│             │             │
   │         │             │                 │              │             │             │
   │         │             │                 │  parse_result │             │             │
   │         │             │                 │ <─────────────│             │             │
   │         │             │                 │              │             │             │
   │  SSE: {"type":"parse_result",...}       │              │             │             │
   │ <───────│<────────────│<────────────────│              │             │             │
   │         │             │                 │              │             │             │
   │         │             │  ┌──────────────┤              │             │             │
   │         │             │  │ Phase 4:     │              │             │             │
   │         │             │  │ Query Exec   │              │             │             │
   │         │             │  └──────────────┤              │             │             │
   │         │             │                 │ execute_query()            │             │
   │         │             │                 │ ─────────────┼────────────>│             │
   │         │             │                 │              │  VizQL API  │             │
   │         │             │                 │ <────────────┼─────────────│             │
   │         │             │                 │              │             │             │
   │  SSE: {"type":"data","tableData":{...}} │              │             │             │
   │ <───────│<────────────│<────────────────│              │             │             │
   │         │             │                 │              │             │             │
   │         │             │  ┌──────────────┤              │             │             │
   │         │             │  │ Phase 5:     │              │             │             │
   │         │             │  │ Insight      │              │             │             │
   │         │             │  └──────────────┤              │             │             │
   │         │             │                 │ insight_agent()            │             │
   │         │             │                 │ ────────────>│             │             │
   │         │             │                 │ <────────────│             │             │
   │         │             │                 │              │             │             │
   │  SSE: {"type":"insight",...}            │              │             │             │
   │ <───────│<────────────│<────────────────│              │             │             │
   │         │             │                 │              │             │             │
   │         │             │  ┌──────────────┤              │             │             │
   │         │             │  │ Phase 6:     │              │             │             │
   │         │             │  │ Replan       │              │             │             │
   │         │             │  └──────────────┤              │             │             │
   │         │             │                 │ replanner()  │             │             │
   │         │             │                 │ ────────────>│             │             │
   │         │             │                 │ <────────────│             │             │
   │         │             │                 │              │             │             │
   │  SSE: {"type":"replan",...}             │              │             │             │
   │ <───────│<────────────│<────────────────│              │             │             │
   │  SSE: {"type":"suggestions",...}        │              │             │             │
   │ <───────│<────────────│<────────────────│              │             │             │
   │         │             │                 │              │             │             │
   │  SSE: {"type":"complete","workflowTimeMs":...}         │             │             │
   │ <───────│<────────────│<────────────────│              │             │             │
   │         │             │                 │              │             │             │
```

### 2.2 多步分析时序图（Analysis Plan）

```
┌────┐    ┌────────────┐    ┌────────┐    ┌────────┐
│User│    │Orchestrator│    │  Agent │    │Platform│
└──┬─┘    └──────┬─────┘    └───┬────┘    └───┬────┘
   │             │              │             │
   │  (Phase 3 产出 analysis_plan.needs_planning=true)
   │             │              │             │
   │  SSE: planner event       │             │
   │ <───────────│              │             │
   │             │              │             │
   │  ┌─────────┤              │             │
   │  │ Primary │              │             │
   │  │ Step    │              │             │
   │  └─────────┤              │             │
   │             │ execute primary query      │
   │             │ ─────────────┼────────────>│
   │  SSE: plan_step(running)  │             │
   │ <───────────│              │             │
   │  SSE: data  │              │             │
   │ <───────────│              │             │
   │  SSE: plan_step(completed)│             │
   │ <───────────│              │             │
   │             │ insight_agent(step)        │
   │             │ ────────────>│             │
   │  SSE: insight(plan_step)  │             │
   │ <───────────│<─────────────│             │
   │             │              │             │
   │  ┌─────────┤              │             │
   │  │ Wave N  │  (依赖图调度，支持并行)     │
   │  │ Steps   │              │             │
   │  └─────────┤              │             │
   │             │  ┌───────────────────┐     │
   │             │  │ parallel gather   │     │
   │             │  │ step-2, step-3    │     │
   │             │  └───────────────────┘     │
   │             │ graph.ainvoke(step-N)      │
   │             │ ────────────>│             │
   │             │ <────────────│             │
   │             │ execute query(step-N)      │
   │             │ ─────────────┼────────────>│
   │             │ <────────────┼─────────────│
   │  SSE: plan_step(completed)│             │
   │ <───────────│              │             │
   │             │              │             │
   │  ┌─────────┤              │             │
   │  │Synthesis│              │             │
   │  │ Step    │              │             │
   │  └─────────┤              │             │
   │  SSE: plan_step(synthesis)│             │
   │ <───────────│              │             │
   │             │              │             │
   │  ┌─────────┤              │             │
   │  │ Post    │              │             │
   │  │ Planner │              │             │
   │  │ Agents  │              │             │
   │  └─────────┤              │             │
   │             │ replanner(evidence)        │
   │             │ ────────────>│             │
   │  SSE: insight + replan    │             │
   │ <───────────│<─────────────│             │
   │             │              │             │
   │  SSE: complete            │             │
   │ <───────────│              │             │
```

### 2.3 SemanticParser 子图内部时序

```
┌──────────┐   ┌──────┐   ┌─────────┐   ┌────────┐   ┌─────────┐   ┌────────┐   ┌─────────┐
│IntentRtr │   │Cache │   │Unified  │   │Parallel│   │Prepare  │   │Semantic│   │Output   │
│          │   │      │   │Feature  │   │Retriev │   │Prompt   │   │Underst │   │Validatr │
└────┬─────┘   └──┬───┘   └────┬────┘   └───┬────┘   └────┬────┘   └───┬────┘   └────┬────┘
     │            │            │             │             │             │             │
 question         │            │             │             │             │             │
 ───>│            │            │             │             │             │             │
     │ intent     │            │             │             │             │             │
     │ ─────────> │ (data_query)             │             │             │             │
     │            │ cache check│             │             │             │             │
     │            │ ──────────>│ (cache_miss) │             │             │             │
     │            │            │ rule_prefilter              │             │             │
     │            │            │ + feature_extract           │             │             │
     │            │            │ + global_understanding      │             │             │
     │            │            │ ────────────>│             │             │             │
     │            │            │             │ field_retriever            │             │
     │            │            │             │ ∥ few_shot_manager         │             │
     │            │            │             │ (parallel)   │             │             │
     │            │            │             │ ────────────>│             │             │
     │            │            │             │             │ schema_build │             │
     │            │            │             │             │ + prompt_build             │
     │            │            │             │             │ ────────────>│             │
     │            │            │             │             │             │  LLM call   │
     │            │            │             │             │             │ (SemanticOutput)
     │            │            │             │             │             │ ────────────>│
     │            │            │             │             │             │             │
     │            │            │             │             │             │  validate   │
     │            │            │             │             │             │             │

 ┌────────┐   ┌─────────┐   ┌──────────┐
 │Filter  │   │Query    │   │Feedback  │
 │Validtr │   │Adapter  │   │Learner   │
 └───┬────┘   └────┬────┘   └────┬─────┘
     │             │             │
 ───>│ (valid)     │             │
     │ ──────────> │             │
     │             │ build query │
     │             │ ──────────> │
     │             │             │ save feedback
     │             │             │ ──> parse_result
     │             │             │
     │  (error) ───┼────> ErrorCorrector ──> retry → OutputValidator
```

---

## 附件三：数据库 DDL 草案

### 设计说明

- **当前状态**: 使用 LangGraph `BaseStore` (SQLite KV 存储)，无 schema，数据为 JSON blob
- **重构目标**: 引入关系型 DDL，保留 KV 存储用于缓存，结构化数据使用关系表
- **兼容策略**: 支持 SQLite (开发) 和 PostgreSQL (生产)

```sql
-- ═══════════════════════════════════════════════════════════════
-- 1. 用户与认证
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE users (
    id              TEXT PRIMARY KEY,               -- UUID
    tableau_username TEXT NOT NULL UNIQUE,           -- Tableau 用户名
    display_name    TEXT,
    email           TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at   TIMESTAMP
);

CREATE INDEX idx_users_tableau_username ON users(tableau_username);

-- ═══════════════════════════════════════════════════════════════
-- 2. 会话管理
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,               -- UUID
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL DEFAULT '新对话',
    datasource_name TEXT,                           -- 绑定的数据源名称
    datasource_luid TEXT,                           -- 数据源 LUID
    is_pinned       BOOLEAN NOT NULL DEFAULT FALSE,
    message_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_updated_at ON sessions(updated_at DESC);

-- ═══════════════════════════════════════════════════════════════
-- 3. 消息记录
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,               -- UUID
    session_id      TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,                  -- 消息文本内容
    metadata        TEXT,                           -- JSON: 附加元数据
    parent_msg_id   TEXT REFERENCES messages(id),   -- 用于消息树结构
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_session_id ON messages(session_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);

-- ═══════════════════════════════════════════════════════════════
-- 4. 工作流执行记录（可选，用于调试/审计）
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE workflow_runs (
    id              TEXT PRIMARY KEY,               -- request_id / UUID
    session_id      TEXT REFERENCES sessions(id) ON DELETE SET NULL,
    user_id         TEXT NOT NULL REFERENCES users(id),
    question        TEXT NOT NULL,
    datasource_luid TEXT NOT NULL,
    language        TEXT NOT NULL DEFAULT 'zh',
    analysis_depth  TEXT NOT NULL DEFAULT 'standard',
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'timed_out')),
    started_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP,
    elapsed_ms      REAL,
    metrics         TEXT,                           -- JSON: stage_metrics 快照
    error_message   TEXT
);

CREATE INDEX idx_workflow_runs_user_id ON workflow_runs(user_id);
CREATE INDEX idx_workflow_runs_session_id ON workflow_runs(session_id);
CREATE INDEX idx_workflow_runs_status ON workflow_runs(status);

-- ═══════════════════════════════════════════════════════════════
-- 5. 查询结果快照（支持 Resume / 回放）
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE query_snapshots (
    id              TEXT PRIMARY KEY,               -- query_id
    workflow_run_id TEXT NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    plan_step_index INTEGER,                        -- NULL = 单次查询, 1~N = 多步
    semantic_output TEXT NOT NULL,                  -- JSON: SemanticOutput 序列化
    vizql_request   TEXT,                           -- JSON: 发送的 VizQL 请求
    table_data      TEXT,                           -- JSON: 返回的表数据
    row_count       INTEGER,
    execution_ms    REAL,
    is_cache_hit    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_query_snapshots_workflow ON query_snapshots(workflow_run_id);

-- ═══════════════════════════════════════════════════════════════
-- 6. 用户设置
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE user_settings (
    user_id         TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    language        TEXT NOT NULL DEFAULT 'zh',
    theme           TEXT NOT NULL DEFAULT 'system',
    analysis_depth  TEXT NOT NULL DEFAULT 'standard',
    replan_mode     TEXT NOT NULL DEFAULT 'user_select',
    custom_config   TEXT,                           -- JSON: 扩展配置
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ═══════════════════════════════════════════════════════════════
-- 7. 用户反馈
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE feedback (
    id              TEXT PRIMARY KEY,               -- UUID
    user_id         TEXT NOT NULL REFERENCES users(id),
    message_id      TEXT REFERENCES messages(id),
    workflow_run_id TEXT REFERENCES workflow_runs(id),
    rating          INTEGER CHECK (rating BETWEEN 1 AND 5),
    feedback_type   TEXT CHECK (feedback_type IN ('thumbs_up', 'thumbs_down', 'correction', 'comment')),
    content         TEXT,                           -- 用户反馈文本
    context         TEXT,                           -- JSON: 反馈时的上下文快照
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_feedback_user_id ON feedback(user_id);
CREATE INDEX idx_feedback_workflow ON feedback(workflow_run_id);

-- ═══════════════════════════════════════════════════════════════
-- 8. 查询缓存（保留 KV 方式，但规范 schema）
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE query_cache (
    cache_key       TEXT PRIMARY KEY,               -- hash(datasource_luid + normalized_question)
    datasource_luid TEXT NOT NULL,
    question_hash   TEXT NOT NULL,
    semantic_output TEXT NOT NULL,                  -- JSON
    query           TEXT,                           -- JSON: 构建好的查询
    hit_count       INTEGER NOT NULL DEFAULT 0,
    schema_hash     TEXT NOT NULL,                  -- 数据源 schema 版本
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP                       -- TTL
);

CREATE INDEX idx_query_cache_datasource ON query_cache(datasource_luid);
CREATE INDEX idx_query_cache_expires ON query_cache(expires_at);

-- ═══════════════════════════════════════════════════════════════
-- 9. 字段语义缓存
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE field_semantic_cache (
    datasource_luid TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    schema_hash     TEXT NOT NULL,                  -- 失效依据
    semantic_info   TEXT NOT NULL,                  -- JSON: 字段语义信息
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (datasource_luid, field_name)
);

CREATE INDEX idx_field_semantic_schema ON field_semantic_cache(datasource_luid, schema_hash);
```

### KV 存储保留范围

| 用途 | 存储方式 | 说明 |
|------|---------|------|
| LangGraph Checkpointer | BaseStore (SQLite/Postgres) | 用于子图状态持久化和回放 |
| 向量索引 | VectorStore | 字段 embedding 索引 |
| 临时数据 (DataStore) | InMemoryStore | 单次请求的 DataProfiler 结果 |

---

## 附件四：SSE / Resume JSON 契约

### 4.1 SSE 通用信封格式

所有 SSE 事件遵循统一信封：

```
data: <JSON>\n\n
```

JSON 结构：

```jsonc
{
  "type": "<event_type>",          // 必填，事件类型枚举
  "timestamp": "2025-07-01T...",   // 可选，ISO8601
  "request_id": "uuid",           // 可选，关联请求
  // ... 事件特定字段
}
```

### 4.2 SSE 事件类型定义

#### 4.2.1 连接与生命周期

```jsonc
// 心跳 (SSE comment 格式)
: heartbeat\n\n

// 工作流完成
{
  "type": "complete",
  "workflowTimeMs": 12345.6,
  "optimization_metrics": { ... }
}

// 错误
{
  "type": "error",
  "error": "错误描述（已脱敏）",
  "error_code": "WORKFLOW_TIMEOUT",   // 新增：结构化错误码
  "optimization_metrics": { ... }
}
```

#### 4.2.2 进度与思考

```jsonc
// 阶段进度
{
  "type": "thinking",
  "stage": "preparing|understanding|mapping|building|executing|generating|replanning",
  "name": "准备数据",                // 显示名称（中/英文）
  "status": "running|completed"
}

// LLM token 流
{
  "type": "token",
  "content": "你"
}

// 推理模型思考过程
{
  "type": "thinking_token",
  "content": "让我分析一下..."
}

// 状态消息
{
  "type": "status",
  "message": "正在执行数据查询..."
}
```

#### 4.2.3 语义解析结果

```jsonc
{
  "type": "parse_result",
  "success": true,
  "query_id": "uuid",
  "summary": {
    "restated_question": "查询各地区上月销售额",
    "measures": ["销售额"],
    "dimensions": ["地区"],
    "filters": ["日期"]
  },
  "is_degraded": false,
  "query_cache_hit": false,
  "analysis_plan": { ... },          // 仅多步分析时存在
  "global_understanding": { ... },   // 仅复杂查询时存在
  "planStep": { ... },               // 仅多步分析的步骤时存在
  "optimization_metrics": { ... }
}
```

#### 4.2.4 数据结果

```jsonc
{
  "type": "data",
  "tableData": {
    "columns": [
      { "name": "地区", "dataType": "STRING", "role": "dimension" },
      { "name": "SUM(销售额)", "dataType": "REAL", "role": "measure" }
    ],
    "rows": [
      { "地区": "华东", "SUM(销售额)": 125000 },
      { "地区": "华北", "SUM(销售额)": 98000 }
    ],
    "rowCount": 2,
    "executionTimeMs": 450
  },
  "planStep": { ... },              // 仅多步分析时存在
  "summary": "...",                  // 仅多步分析时存在
  "optimization_metrics": { ... }
}
```

#### 4.2.5 洞察

```jsonc
{
  "type": "insight",
  "source": "single_query|plan_step|planner_synthesis",
  "summary": "销售额整体呈上升趋势...",
  "findings": [
    {
      "title": "华东地区领先",
      "description": "华东地区销售额占比 35%",
      "importance": "high|medium|low"
    }
  ],
  "planStep": { ... },
  "optimization_metrics": { ... }
}
```

#### 4.2.6 多步分析计划

```jsonc
// 计划总览
{
  "type": "planner",
  "planMode": "direct_query|decomposed_query|why_analysis",
  "goal": "分析各地区销售下降原因",
  "executionStrategy": "sequential|parallel",
  "reasoningFocus": ["trend", "comparison"],
  "steps": [
    {
      "index": 1,
      "total": 3,
      "stepId": "step-1",
      "title": "查询整体销售趋势",
      "question": "近6个月的整体销售额趋势",
      "stepType": "query|synthesis",
      "usesPrimaryQuery": true,
      "dependsOn": []
    }
  ],
  "optimization_metrics": { ... }
}

// 步骤进度
{
  "type": "plan_step",
  "status": "running|completed|error|clarification",
  "step": { "index": 1, "total": 3, "stepId": "step-1", ... },
  "message": "正在执行规划步骤 1/3",     // running 时
  "queryId": "uuid",                      // completed 时
  "semanticSummary": { ... },             // completed 时
  "summary": "...",                       // completed 时
  "error": "...",                         // error 时
  "question": "...",                      // clarification 时
  "options": [...],                       // clarification 时
  "optimization_metrics": { ... }
}
```

#### 4.2.7 重规划与建议

```jsonc
// 候选问题
{
  "type": "candidate_questions",
  "source": "single_query|planner_synthesis",
  "questions": [
    {
      "question": "各地区的销售增长率如何？",
      "reason": "深入分析增长趋势",
      "priority": "high|medium|low"
    }
  ],
  "optimization_metrics": { ... }
}

// 重规划决策
{
  "type": "replan",
  "source": "single_query|planner_synthesis",
  "mode": "user_select|auto_continue",
  "action": "await_user_select|auto_continue|stop",
  "shouldReplan": true,
  "reason": "发现了显著的地区差异",
  "newQuestion": "为什么华南地区销售额下降？",
  "selectedQuestion": null,               // auto_continue 时填充
  "questions": ["问题1", "问题2"],
  "candidateQuestions": [ ... ],
  "optimization_metrics": { ... }
}

// 建议问题（简化版，供 UI 展示）
{
  "type": "suggestions",
  "source": "single_query|planner_synthesis",
  "questions": ["问题1", "问题2"],
  "candidateQuestions": [ ... ],
  "optimization_metrics": { ... }
}
```

#### 4.2.8 澄清请求

```jsonc
{
  "type": "clarification",
  "question": "您指的"销售额"是含税还是不含税？",
  "options": ["含税销售额", "不含税销售额", "两者都查"],
  "source": "semantic_understanding|filter_validator",
  "optimization_metrics": { ... }
}
```

#### 4.2.9 图表配置（预留）

```jsonc
{
  "type": "chart",
  "chartConfig": {
    "chartType": "bar|line|pie|scatter",
    "xAxis": "地区",
    "yAxis": "SUM(销售额)",
    "title": "各地区销售额对比"
  }
}
```

### 4.3 Resume 契约（新增功能设计）

#### 设计目标

当 SSE 连接断开后，客户端可通过 Resume 机制恢复流，避免重新执行整个工作流。

#### Resume 请求

```http
POST /api/chat/resume
Content-Type: application/json
X-Tableau-Username: admin

{
  "request_id": "original-request-uuid",
  "last_event_index": 42,
  "session_id": "session-uuid"
}
```

#### Resume 响应

返回 SSE 流，从 `last_event_index + 1` 开始重放：

```
data: {"type":"resume_start","request_id":"...","resumed_from":43,"total_events":87}\n\n
data: {"type":"data","tableData":{...},"_event_index":43}\n\n
data: {"type":"insight",...,"_event_index":44}\n\n
...
data: {"type":"resume_end","replayed_count":44}\n\n
```

#### 事件索引机制

每个 SSE 事件附加 `_event_index` 字段（单调递增）：

```jsonc
{
  "type": "token",
  "content": "你",
  "_event_index": 1           // 新增：全局事件序号
}
```

#### 服务端存储

工作流执行期间，所有 SSE 事件暂存至 `workflow_event_log` 表：

```sql
CREATE TABLE workflow_event_log (
    workflow_run_id TEXT NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE,
    event_index     INTEGER NOT NULL,
    event_type      TEXT NOT NULL,
    event_data      TEXT NOT NULL,                  -- JSON
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (workflow_run_id, event_index)
);

-- 定期清理已完成超过 N 小时的事件日志
CREATE INDEX idx_event_log_created ON workflow_event_log(created_at);
```

#### Resume 状态机

```
                ┌──────────┐
    连接断开 ──> │ RESUMABLE │ ──(TTL 过期)──> EXPIRED
                └────┬─────┘
                     │
              POST /resume
                     │
                ┌────┴─────┐
                │ REPLAYING │ ──(完成)──> COMPLETED
                └──────────┘
```

### 4.4 错误码枚举（新增）

```jsonc
// 建议标准化的错误码
{
  "AUTH_FAILED":            "认证失败",
  "AUTH_EXPIRED":           "认证已过期",
  "DATASOURCE_NOT_FOUND":  "数据源未找到",
  "DATASOURCE_LOAD_FAILED":"数据模型加载失败",
  "QUERY_VALIDATION_FAILED":"查询验证失败",
  "QUERY_EXECUTION_FAILED": "查询执行失败",
  "QUERY_TIMEOUT":          "查询执行超时",
  "LLM_CALL_FAILED":       "LLM 调用失败",
  "LLM_OUTPUT_INVALID":    "LLM 输出解析失败",
  "WORKFLOW_TIMEOUT":       "工作流总超时",
  "WORKFLOW_CANCELLED":     "工作流已取消",
  "RATE_LIMITED":           "请求频率限制",
  "INTERNAL_ERROR":         "内部错误"
}
```

---

## 三、重构实施路线图

### Phase 1: 基础设施 (1-2 周)

1. **引入 SQLAlchemy + Alembic** — 替代 raw SQLite，支持数据库迁移
2. **定义 SSE 事件 Pydantic 模型** — 替代散落的 dict 字面量
3. **统一异常处理** — 结构化错误码
4. **存储层重构** — 关系数据用 SQLAlchemy，缓存保留 BaseStore

### Phase 2: Service 层引入 (1 周)

1. **提取 ChatService** — 从 `chat.py` + `executor.py` 中提取 SSE 生命周期管理
2. **提取 SessionService** — 从 router 中提取业务逻辑
3. **提取 SettingsService** — 同上

### Phase 3: Executor 拆分 (2-3 周)

1. **拆分 WorkflowOrchestrator** — 将 2155 行的 executor 拆分为：
   - `AuthStage` — 认证
   - `DataPrepStage` — 数据模型加载 + 字段语义
   - `QueryExecutionStage` — 单次查询执行
   - `InsightStage` — 洞察生成
   - `ReplanStage` — 重规划
   - `AnalysisPlanExecutor` — 多步分析调度
2. **每个 Stage 独立可测试**

### Phase 4: Resume 功能 (1 周)

1. **实现事件日志** — 工作流执行期间持久化 SSE 事件
2. **实现 Resume 端点** — `/api/chat/resume`
3. **客户端断线重连** — 前端 EventSource reconnect

### Phase 5: 可观测性 (持续)

1. **结构化日志** — 替代 f-string 日志
2. **Metrics 采集** — 各阶段耗时、LLM token 用量
3. **Tracing** — OpenTelemetry 集成

---

## 四、关键重构示例

### 4.1 SSE 事件 Pydantic 模型（示例）

```python
from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel

class SSEEventType(str, Enum):
    THINKING = "thinking"
    TOKEN = "token"
    THINKING_TOKEN = "thinking_token"
    STATUS = "status"
    PARSE_RESULT = "parse_result"
    DATA = "data"
    INSIGHT = "insight"
    PLANNER = "planner"
    PLAN_STEP = "plan_step"
    CANDIDATE_QUESTIONS = "candidate_questions"
    REPLAN = "replan"
    SUGGESTIONS = "suggestions"
    CLARIFICATION = "clarification"
    CHART = "chart"
    ERROR = "error"
    COMPLETE = "complete"
    HEARTBEAT = "heartbeat"

class ThinkingEvent(BaseModel):
    type: str = SSEEventType.THINKING
    stage: str
    name: str
    status: str  # "running" | "completed"

class TokenEvent(BaseModel):
    type: str = SSEEventType.TOKEN
    content: str

class DataEvent(BaseModel):
    type: str = SSEEventType.DATA
    tableData: dict[str, Any]
    planStep: Optional[dict[str, Any]] = None
    summary: Optional[str] = None
    optimization_metrics: Optional[dict[str, Any]] = None

class ErrorEvent(BaseModel):
    type: str = SSEEventType.ERROR
    error: str
    error_code: Optional[str] = None
    optimization_metrics: Optional[dict[str, Any]] = None

class CompleteEvent(BaseModel):
    type: str = SSEEventType.COMPLETE
    workflowTimeMs: float
    optimization_metrics: Optional[dict[str, Any]] = None

# Union type for type-safe event emission
SSEEvent = Union[
    ThinkingEvent, TokenEvent, DataEvent,
    ErrorEvent, CompleteEvent,
    # ... 其他事件类型
]
```

### 4.2 Stage 拆分示例

```python
# orchestration/stages/auth_stage.py
class AuthStage:
    """认证阶段 — 独立可测试"""
    
    async def execute(
        self,
        username: str,
        event_emitter: EventEmitter,
    ) -> AuthResult:
        await event_emitter.emit(ThinkingEvent(
            stage="preparing", name="认证", status="running"
        ))
        auth = await get_tableau_auth_async(username)
        await event_emitter.emit(ThinkingEvent(
            stage="preparing", name="认证", status="completed"
        ))
        return AuthResult(auth=auth, elapsed_ms=...)

# orchestration/orchestrator.py
class WorkflowOrchestrator:
    """工作流编排器 — 仅组合各 Stage"""
    
    def __init__(self):
        self.auth_stage = AuthStage()
        self.data_prep_stage = DataPrepStage()
        self.query_stage = QueryExecutionStage()
        self.insight_stage = InsightStage()
        self.replan_stage = ReplanStage()
    
    async def execute_stream(self, request: WorkflowRequest) -> AsyncIterator[SSEEvent]:
        auth = await self.auth_stage.execute(...)
        data_ctx = await self.data_prep_stage.execute(auth, ...)
        parse_result = await self._run_parser_graph(data_ctx, ...)
        
        if parse_result.analysis_plan:
            async for event in self._execute_plan(...):
                yield event
        else:
            query_result = await self.query_stage.execute(...)
            yield DataEvent(tableData=query_result)
            
            insight = await self.insight_stage.execute(...)
            yield InsightEvent(**insight)
```
