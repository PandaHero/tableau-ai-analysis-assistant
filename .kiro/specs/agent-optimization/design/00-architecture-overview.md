# 架构总览

## 1. 重构目标

将当前 Agent 架构从 **5-13 次 LLM 调用/查询** 优化到 **N+2 次 LLM 调用/查询**（N 为数据批次数）。

### 优化策略

| 优化项 | 当前 | 优化后 | 减少 |
|--------|------|--------|------|
| SemanticParser | Step1(1) + Step2(1) | Unified(1) | -1 |
| Insight | Director(N) + Analyzer(N) | ChainAnalyzer(N+1) | -N+1 |
| Replanner | 必须(1) | 可选(0-1) | 0-1 |
| **总计** | **2-3 + 2N + 1** | **1 + N+1 + 0-1** | **~50%** |

## 2. 重构后架构图

```
用户问题
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  UnifiedSemanticParser (1 次 LLM)                                │
│  ├── 语义理解 (What/Where/How)                                  │
│  ├── 意图分类                                                    │
│  ├── 计算推理 (如需要)                                          │
│  └── 自我验证                                                    │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  Pipeline (工具调用)                                             │
│  ├── MapFields (RAG + Candidate Fields)                         │
│  ├── BuildQuery (代码)                                          │
│  └── ExecuteQuery (Tableau API)                                 │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  Observer (错误检查)                                             │
│  └── 检查执行结果，决定是否重试                                  │
└─────────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────────┐
│  数据获取层                                                      │
│  ├── 支持 SSE ──► SSE 流式返回                                  │
│  └── 不支持 SSE ──► 一次性返回 ──► 分批写入 LangGraph Store      │
└─────────────────────────────────────────────────────────────────┘
    ↓ (流式数据)
┌─────────────────────────────────────────────────────────────────┐
│  链式分析 (ChainAnalyzer) - N+1 次 LLM                          │
│  Round 1: [Batch 0] ──► LLM ──► 洞察 1                          │
│  Round 2: [洞察 1] + [Batch 1] ──► LLM ──► 洞察 1+2             │
│  ...                                                            │
│  Final: [累积洞察] ──► LLM ──► 最终报告 (流式输出)               │
└─────────────────────────────────────────────────────────────────┘
    ↓
最终响应 (数据 + 洞察报告)
```

## 3. 核心设计决策

### 3.1 保持 Observer 模式

**决策**: 保留 Observer，不使用 ReAct 模式

**原因**:
- Observer 已经实现且工作良好
- ReAct 模式（Thought → Action → Observation 循环）对当前场景过于复杂
- 专注于 Prompt 和 Schema 优化，而非架构重构

**Observer 职责**:
- 检查工具执行结果
- 判断是否需要重试
- 生成错误反馈

### 3.2 中间件简化

**决策**: 只保留 6 个核心中间件（从 8 个减少）

| 中间件 | 状态 | 来源 | 原因 |
|--------|------|------|------|
| TodoListMiddleware | ✅ 保留 | LangChain | 任务队列管理 |
| SummarizationMiddleware | ✅ 保留 | LangChain | 对话历史压缩，已实现 |
| ModelRetryMiddleware | ✅ 保留 | LangChain | LLM 调用重试，已实现 |
| ToolRetryMiddleware | ✅ 保留 | LangChain | 工具调用重试，已实现 |
| FilesystemMiddleware | ✅ 保留 | 自定义 | 大文件缓存，已实现 |
| HumanInTheLoopMiddleware | ✅ 保留 | LangChain | 人工确认（可选） |
| OutputValidationMiddleware | ❌ 移除 | 自定义 | JSON 模式 + Pydantic 已处理 |
| PatchToolCallsMiddleware | ❌ 移除 | 自定义 | JSON 模式不需要（修复悬空工具调用）|

**注意**：
- `with_structured_output()` 不支持流式输出
- 项目使用 JSON 模式 + `parse_json_response()` 模式
- SummarizationMiddleware、ModelRetryMiddleware、ToolRetryMiddleware 都是 LangChain 内置，已在项目中配置

### 3.3 RAG + Candidate Fields 策略

**决策**: 不传递完整 DataModel 给 LLM，使用 RAG 检索候选字段

**流程**:
```
用户问题 → Step1 提取实体 → RAG 检索候选字段 → LLM 从候选中选择
```

**优势**:
- Token 消耗少（只传候选字段）
- 准确率高（LLM 从候选中选择，而非生成）
- 可解释（可以看到 RAG 检索过程）

### 3.4 链式分析模式

**决策**: 合并 Director + Analyzer 为 ChainAnalyzer

**流程**:
```
Round 1: [Batch 0] → LLM → 洞察 1
Round 2: [洞察 1] + [Batch 1] → LLM → 洞察 1+2
...
Final: [累积洞察] → LLM → 最终报告
```

**优势**:
- LLM 调用次数从 2N 降到 N+1（减少约 50%）
- 保持全局视野，避免重复/冲突洞察
- 移除 Director/Analyzer 循环复杂度

## 4. 层级架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        API 层 (api/)                             │
│                  HTTP 端点、请求处理、响应格式化                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      编排层 (orchestration/)                     │
│          工作流编排、中间件、工具                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Agent 层 (agents/)                          │
│          SemanticParser、Insight、Replanner                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      核心层 (core/)                              │
│          接口定义、核心模型、状态定义                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
┌───────────────────────────┐   ┌───────────────────────────┐
│    平台层 (platforms/)     │   │    基础设施层 (infra/)     │
│    Tableau 适配器实现      │   │    LLM、存储、配置        │
└───────────────────────────┘   └───────────────────────────┘
```

## 5. 目录结构

```
tableau_assistant/src/
│
├── api/                                 # API 层
│   ├── chat.py                          # 聊天 API 端点
│   └── models.py                        # API 数据模型
│
├── core/                                # 核心层（平台无关）
│   ├── state.py                         # VizQLState 主状态定义
│   ├── exceptions.py                    # 核心异常定义
│   ├── interfaces/                      # 核心接口定义
│   │   ├── platform_adapter.py          # PlatformAdapter 抽象基类
│   │   ├── field_mapper.py              # FieldMapper 接口
│   │   └── query_builder.py             # QueryBuilder 接口
│   └── models/                          # 核心数据模型（7 个文件）
│       ├── enums.py                     # 语义层枚举
│       ├── fields.py                    # 字段抽象
│       ├── filters.py                   # 过滤器抽象
│       ├── computations.py              # 计算抽象
│       ├── query.py                     # SemanticQuery
│       ├── execute_result.py            # 执行结果抽象
│       └── validation.py                # 验证结果抽象
│
├── agents/                              # Agent 层
│   ├── semantic_parser/                 # SemanticParser Agent
│   │   ├── state.py                     # Agent 内部状态
│   │   ├── subgraph.py                  # Subgraph 定义
│   │   ├── node.py                      # 主工作流适配节点
│   │   ├── components/                  # 内部组件
│   │   │   ├── unified.py               # UnifiedSemanticComponent
│   │   │   ├── pipeline.py              # QueryPipeline
│   │   │   └── observer.py              # Observer（保留）
│   │   ├── schema/                      # Agent 特有 Schema
│   │   │   ├── unified.py               # UnifiedSemanticOutput
│   │   │   ├── pipeline.py              # QueryResult, QueryError
│   │   │   └── observer.py              # ObserverOutput
│   │   └── prompts/                     # Prompt 定义
│   │       ├── unified.py               # UnifiedSemanticPrompt
│   │       └── observer.py              # ObserverPrompt
│   │
│   ├── insight/                         # Insight Agent
│   │   ├── state.py                     # Agent 内部状态
│   │   ├── subgraph.py                  # Subgraph 定义
│   │   ├── node.py                      # 主工作流适配节点
│   │   ├── components/                  # 内部组件
│   │   │   ├── profiler.py              # EnhancedDataProfiler
│   │   │   ├── chain_analyzer.py        # ChainAnalyzer
│   │   │   └── data_buffer.py           # DataBufferMiddleware
│   │   ├── schema/                      # Agent 特有 Schema
│   │   │   ├── profile.py               # EnhancedDataProfile
│   │   │   ├── insight.py               # Insight
│   │   │   └── chain.py                 # ChainAnalyzerOutput
│   │   └── prompts/                     # Prompt 定义
│   │       └── chain_analyzer.py        # ChainAnalyzerPrompt
│   │
│   └── replanner/                       # Replanner Agent
│       ├── node.py                      # Replanner 节点
│       ├── schema/                      # Agent 特有 Schema
│       │   └── output.py                # ReplanDecision
│       └── prompts/                     # Prompt 定义
│           └── replanner.py             # ReplannerPrompt
│
├── orchestration/                       # 编排层
│   ├── workflow/                        # 主工作流
│   │   ├── factory.py                   # create_workflow()
│   │   ├── routes.py                    # 路由函数
│   │   └── state.py                     # VizQLState
│   ├── tools/                           # 工具定义
│   │   ├── base.py                      # BaseTool, ToolResult
│   │   ├── registry.py                  # 工具注册
│   │   ├── map_fields/                  # 字段映射工具
│   │   ├── build_query/                 # 查询构建工具
│   │   └── execute_query/               # 查询执行工具
│   └── middleware/                      # 中间件（4 个核心）
│       ├── runner.py                    # MiddlewareRunner
│       ├── summarization.py             # 对话历史压缩
│       ├── model_retry.py               # LLM 调用重试
│       ├── tool_retry.py                # 工具调用重试
│       └── filesystem.py                # 大文件缓存（已实现）
│
├── platforms/                           # 平台层
│   └── tableau/                         # Tableau 平台实现
│       ├── adapter.py                   # TableauAdapter
│       ├── vizql_client.py              # VizQL API 客户端
│       ├── data_model.py                # 数据模型服务
│       └── query_builder.py             # Tableau 查询构建器
│
└── infra/                               # 基础设施层
    ├── ai/                              # AI 相关
    │   ├── llm.py                       # LLM 客户端
    │   ├── embeddings.py                # 嵌入模型
    │   ├── custom_llm.py                # 自定义 LLM 实现
    │   └── model_manager.py             # 模型管理器
    ├── storage/                         # 存储
    │   ├── data_model_cache.py          # 数据模型缓存
    │   └── langgraph_store.py           # LangGraph Store
    └── config/                          # 配置
        └── settings.py                  # 全局设置
```

## 3. LLM 调用流程对比

### 3.1 当前架构

```
用户问题
    ↓
Step1 (LLM #1) ──► 意图识别
    ↓
Step2 (LLM #2, 条件) ──► 计算推理
    ↓
Pipeline (工具) ──► MapFields → BuildQuery → Execute
    ↓
Observer (LLM #3, 错误时) ──► 错误检查
    ↓
Profiler (代码) ──► 数据画像
    ↓
Director (LLM #4) ◄──► Analyzer (LLM #5)  ← 循环 N 次
    ↓
Replanner (LLM #6) ──► 重规划决策

总计: 2-3 + 2N + 1 = 5-13 次 LLM 调用
```

### 3.2 优化后架构

```
用户问题
    ↓
UnifiedSemanticParser (LLM #1) ──► 语义理解 + 计算推理
    ↓
Pipeline (工具) ──► MapFields → BuildQuery → Execute
    ↓
Observer (LLM #2, 错误时) ──► 错误检查
    ↓
数据获取 (SSE/Store) ──► 流式数据
    ↓
ChainAnalyzer (LLM #3 ~ #N+2) ──► 链式分析
    ↓
Replanner (LLM #N+3, 可选) ──► 重规划决策

总计: 1 + 0-1 + N+1 + 0-1 = N+2 ~ N+3 次 LLM 调用
```

## 4. 组件对比

| 组件 | 当前 | 优化后 | 变化 |
|------|------|--------|------|
| SemanticParser | Step1 + Step2 | UnifiedSemantic | 合并 |
| Pipeline | MapFields + BuildQuery + Execute | 保持不变 | - |
| 错误处理 | Observer | Observer（保留） | 优化 Prompt |
| Insight | Profiler + Director + Analyzer | Profiler + ChainAnalyzer | 合并 Director/Analyzer |
| Replanner | 必须 | 可选 | 配置化 |

## 5. 中间件架构

### 5.1 核心中间件（6 个）

```
┌─────────────────────────────────────────────────────────────────┐
│                    MiddlewareRunner                              │
│                                                                  │
│  Agent 开始:                                                     │
│  ├── TodoListMiddleware.before_agent()                          │
│  │   └── 加载待处理任务                                         │
│                                                                  │
│  LLM 调用:                                                       │
│  ├── SummarizationMiddleware.wrap_model_call()                  │
│  │   └── 压缩对话历史（LangChain 内置，已配置）                 │
│  ├── ModelRetryMiddleware.wrap_model_call()                     │
│  │   └── LLM 调用失败时重试（LangChain 内置，指数退避）         │
│  └── FilesystemMiddleware.wrap_model_call()                     │
│      └── 注入 files 系统提示                                    │
│                                                                  │
│  工具调用:                                                       │
│  ├── ToolRetryMiddleware.wrap_tool_call()                       │
│  │   └── 工具调用失败时重试（LangChain 内置，网络/API 错误）    │
│  └── FilesystemMiddleware.wrap_tool_call()                      │
│      └── 大结果保存到 files                                     │
│                                                                  │
│  Agent 结束:                                                     │
│  └── TodoListMiddleware.after_agent()                           │
│      └── 更新任务状态                                           │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 移除的中间件

| 中间件 | 移除原因 |
|--------|---------|
| OutputValidationMiddleware | JSON 模式 + Pydantic 验证已处理（with_structured_output 不支持流式）|
| PatchToolCallsMiddleware | JSON 模式不会产生悬空工具调用 |

## 6. 数据流

### 6.1 正常流程

```
用户问题
    ↓
[SummarizationMiddleware] 压缩历史
    ↓
[UnifiedSemanticParser] 语义理解
    ↓
[ToolRetryMiddleware] RAG 检索候选字段
    ↓
[ToolRetryMiddleware] 执行查询
    ↓
[FilesystemMiddleware] 大结果保存
    ↓
[ChainAnalyzer] 链式分析
    ↓
最终响应
```

### 6.2 错误流程

```
Pipeline 执行失败
    ↓
Observer 检查错误 → 错误分类
    ↓
决策: CONTINUE | RETRY | CLARIFY | ABORT
    ↓
CONTINUE: 执行成功，继续下一步
RETRY: 回到指定步骤（map_fields/build_query/execute）
  - retry_step: 重试目标
  - retry_reason: 重试原因
  - max_retries: 最大重试次数（默认 2）
CLARIFY: 返回澄清问题
  - clarification_question: 澄清问题
  - suggestions: 建议选项列表
ABORT: 返回错误消息
  - error_code: 错误代码
  - error_message: 用户友好的错误消息
  - technical_details: 技术细节（调试用）
```

### 6.3 Observer 错误分类

| 错误类型 | 决策 | 处理方式 |
|---------|------|---------|
| 字段映射失败（RAG 无结果） | RETRY → map_fields | 使用 LLM Fallback |
| 字段映射失败（LLM 也无法映射） | CLARIFY | 询问用户字段含义 |
| 查询构建失败（语法错误） | RETRY → build_query | 修正查询语法 |
| 查询执行失败（权限错误） | ABORT | 返回权限错误消息 |
| 查询执行失败（超时） | RETRY → execute | 简化查询重试 |
| 查询执行失败（数据源不存在） | ABORT | 返回数据源错误 |
| 结果为空 | CLARIFY | 询问用户是否调整条件 |
| 网络错误 | RETRY | 由 ToolRetryMiddleware 处理 |

## 7. 性能指标

### 7.1 LLM 调用次数

| 场景 | 当前 | 优化后 | 减少 |
|------|------|--------|------|
| 简单查询 + 5批数据 | 1 + 0 + 10 + 1 = 12 | 1 + 6 = 7 | 42% |
| 复杂查询 + 5批数据 | 1 + 1 + 10 + 1 = 13 | 1 + 6 = 7 | 46% |
| 简单查询 + 10批数据 | 1 + 0 + 20 + 1 = 22 | 1 + 11 = 12 | 45% |
| 复杂查询 + 10批数据 | 1 + 1 + 20 + 1 = 23 | 1 + 11 = 12 | 48% |

### 7.2 响应时间

假设单次 LLM 调用平均 2 秒：

| 场景 | 当前 | 优化后 | 减少 |
|------|------|--------|------|
| 简单查询 + 5批数据 | 24s | 14s | 42% |
| 复杂查询 + 10批数据 | 46s | 24s | 48% |

### 7.3 Token 消耗

| 优化项 | 减少 Token |
|--------|-----------|
| 不传完整数据模型 | -5000 ~ -10000 tokens/调用 |
| 对话历史压缩 | -2000 ~ -5000 tokens/调用 |
| 减少 LLM 调用次数 | -50% 总 Token |

## 8. 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| langgraph | 1.0.5+ | 核心编排框架（Subgraph 支持） |
| langchain | 1.1.3+ | LLM 抽象层 |
| pydantic | 2.x | 数据模型验证 |
| aiohttp | 3.x | SSE 流式支持 |

## 9. 迁移策略

### 9.1 Phase 1: 中间件优化（P0）

1. 实现 SummarizationMiddleware
2. 实现 ModelRetryMiddleware
3. 实现 ToolRetryMiddleware
4. 优化 FilesystemMiddleware
5. 移除 OutputValidationMiddleware
6. 移除 PatchToolCallsMiddleware

### 9.2 Phase 2: SemanticParser 合并（P1）

1. 创建 UnifiedSemanticOutput 模型
2. 创建 UnifiedSemanticPrompt
3. 实现 UnifiedSemanticComponent
4. 更新 Subgraph
5. 保留 Observer

### 9.3 Phase 3: Insight 链式分析（P1）

1. 实现 VizQL SSE 客户端
2. 实现 DataBufferMiddleware
3. 实现 ChainAnalyzer
4. 更新 Subgraph
5. 删除 Director/Analyzer

### 9.4 Phase 4: Replanner 可选化（P2）

1. 添加配置开关
2. 修改主工作流

## 10. 回滚策略

通过配置开关支持新旧架构切换：

```python
class Settings:
    # 架构版本
    use_unified_semantic_parser: bool = True
    use_chain_analyzer: bool = True
    replanner_enabled: bool = False
```

## 11. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 合并后 Prompt 过长 | 中 | 使用 XML 标签分块，分层组织 |
| 单次调用准确率下降 | 高 | 增强 System Prompt，添加更多示例 |
| 链式分析上下文过长 | 中 | 压缩历史洞察，只保留关键信息 |
| Tableau 不支持 SSE | 低 | 使用 LangGraph Store 作为缓冲层 |
| RAG 候选字段不准确 | 中 | LLM Fallback 机制 |
