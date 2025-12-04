# 设计文档：Agent 中间件集成

## 概述

本设计文档描述了 Tableau Assistant 的 Agent 中间件集成方案，基于 LangChain/LangGraph 中间件系统实现完整的 Agent 能力增强。

**重要决策**：本项目不依赖 `deepagents` 包。所有中间件要么来自 LangChain，要么由我们自主实现生产级代码。

### 设计原则

1. **利用现有框架**：直接使用 LangChain 提供的中间件，不重复造轮子
2. **自主实现关键功能**：FilesystemMiddleware 和 PatchToolCallsMiddleware 由我们自主实现，确保完全控制和生产级质量
3. **保持 StateGraph 架构**：使用 LangGraph StateGraph 进行工作流编排
4. **统一架构**：所有 Agent 节点通过工具系统交互，而不是直接调用 LLM
5. **生产级代码**：所有功能必须是完整的生产级别实现，不能简化
6. **可配置性**：所有中间件参数可通过环境变量或配置文件调整

### 中间件来源与分类

#### 来自 LangChain (`langchain.agents.middleware`) - 直接使用

| 中间件 | 功能 | 必需性 |
|--------|------|--------|
| `TodoListMiddleware` | 任务管理，提供 `write_todos` 工具 | ✅ 必需 |
| `SummarizationMiddleware` | 对话历史自动总结，避免 token 超限 | ✅ 必需 |
| `HumanInTheLoopMiddleware` | 工具调用前请求人工确认 | ✅ 必需 |
| `ModelRetryMiddleware` | LLM 调用失败自动重试 | ✅ 必需 |
| `ToolRetryMiddleware` | 工具调用失败自动重试 | ✅ 必需 |
| `ModelFallbackMiddleware` | LLM 调用失败时降级到备用模型 | ⭐ 可选 |
| `ModelCallLimitMiddleware` | 限制 LLM 调用次数 | ⭐ 可选 |
| `ToolCallLimitMiddleware` | 限制工具调用次数 | ⭐ 可选 |

#### 自主实现 - 生产级代码

| 中间件 | 功能 | 必需性 |
|--------|------|--------|
| `FilesystemMiddleware` | 大结果自动转存 + 文件系统工具（ls, read_file, write_file, edit_file, glob, grep） | ✅ 必需 |
| `PatchToolCallsMiddleware` | 修复悬空的工具调用（AIMessage 有 tool_calls 但没有对应的 ToolMessage） | ✅ 必需 |

### 核心架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         中间件栈（8 个）                             │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  来自 LangChain (直接使用):                                      ││
│  │  1. TodoListMiddleware          - 任务管理                       ││
│  │  2. SummarizationMiddleware     - 对话总结                       ││
│  │  3. HumanInTheLoopMiddleware    - 人工介入（可选）               ││
│  │  4. ModelRetryMiddleware        - LLM 调用重试                   ││
│  │  5. ToolRetryMiddleware         - 工具调用重试                   ││
│  │                                                                   ││
│  │  自主实现 (生产级代码):                                          ││
│  │  6. FilesystemMiddleware        - 文件系统 + 大结果处理          ││
│  │  7. PatchToolCallsMiddleware    - 悬空工具调用修复               ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```


### 工作流架构与 Agent 工具分配

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         StateGraph 工作流                                    │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                                                                       │   │
│  │   START                                                               │   │
│  │     │                                                                 │   │
│  │     ▼                                                                 │   │
│  │  ┌─────────┐                                                          │   │
│  │  │ Boost?  │──── No ────────────────────────┐                        │   │
│  │  └────┬────┘                                │                        │   │
│  │       │ Yes                                 │                        │   │
│  │       ▼                                     │                        │   │
│  │  ┌─────────────────────────────────────┐   │                        │   │
│  │  │        Boost Agent (LLM)            │   │                        │   │
│  │  │  工具: get_metadata                 │   │                        │   │
│  │  │  输入: original_question            │   │                        │   │
│  │  │  输出: boosted_question             │   │                        │   │
│  │  └────────────────┬────────────────────┘   │                        │   │
│  │                   │                        │                        │   │
│  │                   ▼                        ▼                        │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │              Understanding Agent (LLM)                       │   │   │
│  │  │  工具: parse_date                                            │   │   │
│  │  │  输入: current_question                                      │   │   │
│  │  │  输出: QuestionUnderstanding                                │   │   │
│  │  │        (dimensions, measures, filters, table_calc_type,     │   │   │
│  │  │         table_calc_dimensions) - 使用语义字段名              │   │   │
│  │  └────────────────────────────┬────────────────────────────────┘   │   │
│  │                               │                                     │   │
│  │                               ▼                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                Planning Agent (LLM)                          │   │   │
│  │  │  工具: get_metadata, semantic_map_fields                     │   │   │
│  │  │  输入: QuestionUnderstanding                                 │   │   │
│  │  │  输出: QueryPlan                                             │   │   │
│  │  │        (dimensions, measures, filters, table_calc: Intent)   │   │   │
│  │  └────────────────────────────┬────────────────────────────────┘   │   │
│  │                               │                                     │   │
│  │                               ▼                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │              Execute Node (非 LLM，确定性执行)               │   │   │
│  │  │  功能:                                                       │   │   │
│  │  │    1. QueryPlan → VizQL Query 转换                          │   │   │
│  │  │       (TableCalcIntent → TableCalcField)                    │   │   │
│  │  │    2. 调用 VizQL Data Service API                           │   │   │
│  │  │    3. 返回查询结果                                          │   │   │
│  │  │  输入: QueryPlan                                             │   │   │
│  │  │  输出: QueryResult                                           │   │   │
│  │  └────────────────────────────┬────────────────────────────────┘   │   │
│  │                               │                                     │   │
│  │                               ▼                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │                Insight Agent (LLM)                           │   │   │
│  │  │  工具: detect_statistics, analyze_chunk                      │   │   │
│  │  │  输入: QueryResult, original_question                        │   │   │
│  │  │  输出: accumulated_insights                                  │   │   │
│  │  │  特性: 渐进式分析（大数据分块处理）                          │   │   │
│  │  └────────────────────────────┬────────────────────────────────┘   │   │
│  │                               │                                     │   │
│  │                               ▼                                     │   │
│  │  ┌─────────────────────────────────────────────────────────────┐   │   │
│  │  │               Replanner Agent (LLM)                          │   │   │
│  │  │  工具: analyze_completeness                                  │   │   │
│  │  │  输入: original_question, accumulated_insights, QueryResult  │   │   │
│  │  │  输出: ReplanDecision                                        │   │   │
│  │  │        (should_replan, completeness_score, new_question)     │   │   │
│  │  └────────────────────────────┬────────────────────────────────┘   │   │
│  │                               │                                     │   │
│  │                    ┌──────────┴──────────┐                         │   │
│  │                    │                     │                         │   │
│  │            should_replan?          completeness >= 0.9             │   │
│  │            replan_count < max?      或 replan_count >= max         │   │
│  │                    │                     │                         │   │
│  │                    ▼                     ▼                         │   │
│  │              ┌──────────┐          ┌──────────┐                    │   │
│  │              │ Planning │          │   END    │                    │   │
│  │              │ (跳过    │          └──────────┘                    │   │
│  │              │Understanding)                                       │   │
│  │              └──────────┘                                          │   │
│  │                                                                    │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent 工具分配表

| Agent | 类型 | 可用工具 | 输入 | 输出 |
|-------|------|---------|------|------|
| Boost Agent | LLM | get_metadata | original_question | boosted_question |
| Understanding Agent | LLM | parse_date | current_question | QuestionUnderstanding（语义字段名） |
| Planning Agent | LLM | get_metadata, semantic_map_fields | QuestionUnderstanding | QueryPlan（映射后字段名） |
| Execute Node | 非 LLM | 内部调用 VizQL API | QueryPlan | QueryResult |
| Insight Agent | LLM | detect_statistics, analyze_chunk | QueryResult, original_question | accumulated_insights |
| Replanner Agent | LLM | analyze_completeness | insights, QueryResult, original_question | ReplanDecision |


### 数据流转图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据流转                                        │
│                                                                              │
│  original_question                                                           │
│        │                                                                     │
│        ▼                                                                     │
│  ┌──────────┐     boosted_question                                          │
│  │  Boost   │ ─────────────────────┐                                        │
│  └──────────┘                      │                                        │
│        │                           │                                        │
│        ▼                           ▼                                        │
│  ┌──────────────────────────────────────┐                                   │
│  │         Understanding Agent          │                                   │
│  │                                      │                                   │
│  │  current_question (仅问题文本)       │                                   │
│  │            ↓                         │                                   │
│  │  QuestionUnderstanding (语义字段名): │                                   │
│  │  - question_type                     │                                   │
│  │  - dimensions: [语义字段名]          │                                   │
│  │  - measures: [语义字段名]            │                                   │
│  │  - filters: [语义字段名]             │                                   │
│  │  - table_calc_type: TableCalcType    │  ← 识别表计算类型                 │
│  │  - table_calc_dimensions: [语义名]   │  ← 识别表计算维度                 │
│  └──────────────────┬───────────────────┘                                   │
│                     │                                                        │
│                     ▼                                                        │
│  ┌──────────────────────────────────────┐                                   │
│  │           Planning Agent             │                                   │
│  │  工具: get_metadata, semantic_map    │                                   │
│  │                                      │                                   │
│  │  QuestionUnderstanding (语义字段名)  │                                   │
│  │            ↓                         │                                   │
│  │  调用 semantic_map_fields() 映射     │                                   │
│  │            ↓                         │                                   │
│  │  QueryPlan (映射后实际字段名):       │                                   │
│  │  - dimensions: [mapped_field]        │                                   │
│  │  - measures: [mapped_field]          │                                   │
│  │  - filters: [mapped_field]           │                                   │
│  │  - table_calc: TableCalcIntent       │  ← 中间层表计算意图               │
│  │  - topn: TopNIntent                  │                                   │
│  └──────────────────┬───────────────────┘                                   │
│                     │                                                        │
│                     ▼                                                        │
│  ┌──────────────────────────────────────┐                                   │
│  │         Execute Node (非 LLM)        │                                   │
│  │                                      │                                   │
│  │  QueryPlan (中间层)                  │                                   │
│  │            ↓                         │                                   │
│  │  转换为 VizQL Query:                 │                                   │
│  │  - DimensionIntent → DimensionField  │                                   │
│  │  - MeasureIntent → MeasureField      │                                   │
│  │  - FilterIntent → Filter             │                                   │
│  │  - TableCalcIntent → TableCalcField  │  ← 在这里转换！                   │
│  │            ↓                         │                                   │
│  │  调用 VizQL Data Service API         │                                   │
│  │            ↓                         │                                   │
│  │  QueryResult                         │                                   │
│  └──────────────────┬───────────────────┘                                   │
│                     │                                                        │
│                     ▼                                                        │
│  ┌──────────────────────────────────────┐                                   │
│  │           Insight Agent              │                                   │
│  │                                      │                                   │
│  │  QueryResult + original_question     │                                   │
│  │            ↓                         │                                   │
│  │  accumulated_insights                │                                   │
│  └──────────────────┬───────────────────┘                                   │
│                     │                                                        │
│                     ▼                                                        │
│  ┌──────────────────────────────────────┐                                   │
│  │          Replanner Agent             │                                   │
│  │                                      │                                   │
│  │  insights + QueryResult + question   │                                   │
│  │            ↓                         │                                   │
│  │  ReplanDecision:                     │                                   │
│  │  - should_replan: bool               │                                   │
│  │  - completeness_score: float         │                                   │
│  │  - new_question: str (如果重规划)    │                                   │
│  └──────────────────────────────────────┘                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```


## 组件设计

### AgentMiddleware 钩子函数

LangChain 的 `AgentMiddleware` 基类提供了以下钩子函数，用于在 Agent 执行的不同阶段插入自定义逻辑：

| 钩子 | 异步版本 | 触发时机 | 用途 |
|------|----------|----------|------|
| `before_agent` | `abefore_agent` | Agent 执行开始前 | 初始化、状态预处理、修复悬空工具调用 |
| `after_agent` | `aafter_agent` | Agent 执行完成后 | 清理、状态后处理、资源释放 |
| `before_model` | `abefore_model` | LLM 调用前 | 修改请求、添加系统提示、触发总结 |
| `after_model` | `aafter_model` | LLM 调用后 | 处理响应、触发人工介入中断 |
| `wrap_model_call` | `awrap_model_call` | 包装 LLM 调用 | 重试逻辑、缓存、短路、降级 |
| `wrap_tool_call` | `awrap_tool_call` | 包装工具调用 | 重试逻辑、监控、大结果处理 |

**钩子执行顺序**：

```
Agent 执行开始
    │
    ▼
before_agent (所有中间件)
    │
    ▼
┌─────────────────────────────────┐
│  Agent 循环                      │
│    │                            │
│    ▼                            │
│  before_model (所有中间件)       │
│    │                            │
│    ▼                            │
│  wrap_model_call (嵌套调用)      │
│    │                            │
│    ▼                            │
│  [LLM 调用]                     │
│    │                            │
│    ▼                            │
│  after_model (所有中间件)        │
│    │                            │
│    ▼                            │
│  wrap_tool_call (嵌套调用)       │
│    │                            │
│    ▼                            │
│  [工具调用]                     │
│    │                            │
│    ▼                            │
│  (循环直到完成)                  │
└─────────────────────────────────┘
    │
    ▼
after_agent (所有中间件)
    │
    ▼
Agent 执行结束
```

**各中间件使用的钩子**：

| 中间件 | 使用的钩子 |
|--------|-----------|
| `TodoListMiddleware` | `wrap_model_call` (注入系统提示) |
| `SummarizationMiddleware` | `before_model` (检查并触发总结) |
| `HumanInTheLoopMiddleware` | `after_model` (检查并触发中断) |
| `ModelRetryMiddleware` | `wrap_model_call` (重试逻辑) |
| `ToolRetryMiddleware` | `wrap_tool_call` (重试逻辑) |
| `FilesystemMiddleware` | `wrap_model_call` (注入系统提示), `wrap_tool_call` (大结果处理) |
| `PatchToolCallsMiddleware` | `before_agent` (修复悬空工具调用) |

### 1. Agent 创建工厂

```python
# tableau_assistant/src/agents/agent_factory.py

from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool
from langchain.agents.middleware import (
    TodoListMiddleware,
    SummarizationMiddleware,
    HumanInTheLoopMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.prebuilt import create_react_agent

# 自主实现的中间件
from tableau_assistant.src.middleware.filesystem import FilesystemMiddleware
from tableau_assistant.src.middleware.patch_tool_calls import PatchToolCallsMiddleware
from tableau_assistant.src.middleware.backends import StateBackend, StoreBackend, CompositeBackend


def create_tableau_agent(
    tools: List[BaseTool],
    model_name: Optional[str] = None,
    store: Optional[BaseStore] = None,
    system_prompt: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> CompiledStateGraph:
    """
    创建 Tableau Assistant 的 Agent
    
    中间件配置：
    来自 LangChain (直接使用):
    - TodoListMiddleware: 任务管理
    - SummarizationMiddleware: 对话总结
    - HumanInTheLoopMiddleware: 人工介入（可选）
    - ModelRetryMiddleware: LLM 调用重试
    - ToolRetryMiddleware: 工具调用重试
    
    自主实现 (生产级代码):
    - FilesystemMiddleware: 文件系统工具 + 大结果处理
    - PatchToolCallsMiddleware: 悬空工具调用修复
    
    Args:
        tools: 业务工具列表
        model_name: LLM 模型名称
        store: 持久化存储实例
        system_prompt: 系统提示词
        config: 额外配置
            - summarization_token_threshold: 触发总结的 token 阈值 (默认 100000)
            - messages_to_keep: 总结后保留的消息数 (默认 10)
            - filesystem_token_limit: 触发文件写入的 token 阈值 (默认 20000)
            - model_max_retries: LLM 调用最大重试次数 (默认 3)
            - tool_max_retries: 工具调用最大重试次数 (默认 3)
            - interrupt_on: 需要人工确认的工具配置
    
    Returns:
        编译后的 Agent 图
    """
    config = config or {}
    
    # 配置文件系统后端
    if store:
        backend = CompositeBackend(
            default=lambda rt: StateBackend(rt),
            routes={"/persistent/": lambda rt: StoreBackend(rt, store)}
        )
    else:
        backend = lambda rt: StateBackend(rt)
    
    # 配置中间件列表
    middleware = [
        # 来自 LangChain - 直接使用
        TodoListMiddleware(),
        SummarizationMiddleware(
            model=model_name,
            trigger=("tokens", config.get("summarization_token_threshold", 100000)),
            keep=("messages", config.get("messages_to_keep", 10)),
        ),
        ModelRetryMiddleware(max_retries=config.get("model_max_retries", 3)),
        ToolRetryMiddleware(max_retries=config.get("tool_max_retries", 3)),
        
        # 自主实现 - 生产级代码
        FilesystemMiddleware(
            backend=backend,
            tool_token_limit_before_evict=config.get("filesystem_token_limit", 20000),
        ),
        PatchToolCallsMiddleware(),
    ]
    
    # 如果配置了人工介入
    if config.get("interrupt_on"):
        middleware.append(
            HumanInTheLoopMiddleware(interrupt_on=config["interrupt_on"])
        )
    
    # 创建 Agent（使用 LangGraph 的 create_react_agent）
    agent = create_react_agent(
        model=model_name,
        tools=tools,
        middleware=middleware,
        checkpointer=True,
    )
    
    return agent
```

### 2. 中间件配置详解

#### 2.1 TodoListMiddleware (来自 LangChain)

```python
from langchain.agents.middleware import TodoListMiddleware

TodoListMiddleware()

# 提供 write_todos 工具，用于任务管理
# 状态结构
class TodoItem(TypedDict):
    id: str
    description: str
    status: Literal["pending", "in_progress", "completed"]

# Agent 会在复杂任务时自动使用 write_todos 工具
# 任务状态会保存在 state["todos"] 中
```

#### 2.2 SummarizationMiddleware (来自 LangChain)

```python
from langchain.agents.middleware import SummarizationMiddleware

SummarizationMiddleware(
    model=model,
    trigger=("tokens", 100000),  # token 数超过阈值时触发
    keep=("messages", 10),       # 保留最近 10 条消息
)

# 工作流程：
# 1. 监控消息 token 数
# 2. 超过阈值时触发总结
# 3. 保留最近 N 条消息
# 4. 用总结替换旧消息
# 注意：仅总结对话历史，不处理 VizQLState.insights
```

#### 2.3 ModelRetryMiddleware (来自 LangChain)

```python
from langchain.agents.middleware import ModelRetryMiddleware

ModelRetryMiddleware(max_retries=3)

# LLM 调用失败时自动重试
# 支持指数退避策略
```

#### 2.4 ToolRetryMiddleware (来自 LangChain)

```python
from langchain.agents.middleware import ToolRetryMiddleware

ToolRetryMiddleware(max_retries=3)

# 工具调用失败时自动重试
# 支持指数退避策略
```

#### 2.5 HumanInTheLoopMiddleware (来自 LangChain)

```python
from langchain.agents.middleware import HumanInTheLoopMiddleware

HumanInTheLoopMiddleware(
    interrupt_on={
        "replan_decision": True,  # 重规划时暂停让用户选择
    }
)

# 主要用途：重规划阶段
# 1. Replanner Agent 生成 2-5 个后续分析问题
# 2. 触发 HumanInTheLoopMiddleware 暂停执行
# 3. 向用户展示问题列表，等待用户选择
# 4. 用户可以：选择部分问题、修改问题、执行所有、或拒绝继续
# 5. 将选中的问题添加到 TodoListMiddleware 执行队列
```

#### 2.6 FilesystemMiddleware (自主实现)

```python
# tableau_assistant/src/middleware/filesystem.py

from tableau_assistant.src.middleware.filesystem import FilesystemMiddleware

FilesystemMiddleware(
    backend=backend,
    tool_token_limit_before_evict=20000,  # 超过此阈值写入文件
)

# 提供的工具：
# - ls: 列出目录
# - read_file: 读取文件（支持 offset + limit 分页）
# - write_file: 写入文件
# - edit_file: 编辑文件（字符串替换）
# - glob: 文件模式匹配
# - grep: 文件内容搜索

# 大结果处理：
# 1. 当工具输出超过 tool_token_limit_before_evict 时
# 2. 自动写入 /large_tool_results/{tool_call_id}
# 3. 返回文件路径和前 10 行预览
# 4. Agent 可以使用 read_file 分页读取
```

#### 2.7 PatchToolCallsMiddleware (自主实现)

```python
# tableau_assistant/src/middleware/patch_tool_calls.py

from tableau_assistant.src.middleware.patch_tool_calls import PatchToolCallsMiddleware

PatchToolCallsMiddleware()

# 功能：修复悬空的工具调用
# 当 AIMessage 有 tool_calls 但没有对应的 ToolMessage 时
# 自动添加一个取消消息，避免 LLM 调用失败

# 工作流程：
# 1. 在 Agent 执行前检查消息历史
# 2. 找到所有 AIMessage 中的 tool_calls
# 3. 检查是否有对应的 ToolMessage
# 4. 如果没有，添加一个取消消息
```

**中间件架构说明**

中间件来源：
- `langchain.agents.middleware`：TodoListMiddleware、SummarizationMiddleware、HumanInTheLoopMiddleware、ModelRetryMiddleware、ToolRetryMiddleware
- `tableau_assistant.src.middleware`：FilesystemMiddleware、PatchToolCallsMiddleware（自主实现）

**中间件与 StateGraph 的协作**：

```
┌─────────────────────────────────────────────────────────────────┐
│                         Agent                                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    中间件栈                                │  │
│  │  TodoList | Summarization | Retry | Filesystem | Patch    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              ↓                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    StateGraph 工作流                       │  │
│  │  Boost → Understanding → Planning → Execute → Insight →   │  │
│  │  Replanner                                                 │  │
│  │                                                            │  │
│  │  每个节点通过工具系统与 Agent 交互，                       │  │
│  │  自动获得中间件能力                                        │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

各 StateGraph 节点（Understanding、Planning、Insight 等）作为工作流的一部分运行，共享 Agent 的中间件配置。中间件在以下时机自动生效：
- **SummarizationMiddleware**：对话 token 超过阈值时自动总结
- **ModelRetryMiddleware**：LLM 调用失败时自动重试
- **ToolRetryMiddleware**：工具调用失败时自动重试
- **FilesystemMiddleware**：工具输出超过阈值时自动写入文件
- **PatchToolCallsMiddleware**：Agent 执行前修复悬空工具调用
- **HumanInTheLoopMiddleware**：重规划时暂停等待用户选择


### 3. RAG 与 Planning 集成机制

Planning 阶段需要将用户的业务术语（如"销售额"、"地区"）映射到实际的技术字段名（如"Sales Amount"、"Region Name"）。

```
┌─────────────────────────────────────────────────────────────────┐
│                    Planning 节点执行流程                         │
│                                                                  │
│  输入: Understanding 结果                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ mentioned_dimensions: ["地区", "产品类别"]               │    │
│  │ mentioned_measures: ["销售额", "利润"]                   │    │
│  │ mentioned_date_fields: ["订单日期"]                      │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Step 1: 批量字段映射                                     │    │
│  │                                                          │    │
│  │ for term in all_business_terms:                          │    │
│  │     # 检查缓存                                           │    │
│  │     cached = await store.get(("semantic_mapping", term)) │    │
│  │     if cached:                                           │    │
│  │         field_mappings[term] = cached                    │    │
│  │     else:                                                │    │
│  │         # 调用 RAG 工具                                  │    │
│  │         result = await semantic_map_fields(              │    │
│  │             business_term=term,                          │    │
│  │             question_context=original_question,          │    │
│  │             metadata=metadata                            │    │
│  │         )                                                │    │
│  │         field_mappings[term] = result                    │    │
│  │         # 缓存结果 (TTL: 1小时)                          │    │
│  │         await store.put(("semantic_mapping", term), result) │ │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Step 2: 置信度检查                                       │    │
│  │                                                          │    │
│  │ low_confidence_mappings = []                             │    │
│  │ for term, result in field_mappings.items():              │    │
│  │     if result["confidence"] < 0.7:                       │    │
│  │         low_confidence_mappings.append({                 │    │
│  │             "term": term,                                │    │
│  │             "matched_field": result["matched_field"],    │    │
│  │             "confidence": result["confidence"],          │    │
│  │             "alternatives": result["alternatives"]       │    │
│  │         })                                               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Step 3: 生成查询规格                                     │    │
│  │                                                          │    │
│  │ # 使用映射后的技术字段名                                 │    │
│  │ mapped_dimensions = [                                    │    │
│  │     field_mappings[d]["matched_field"]                   │    │
│  │     for d in mentioned_dimensions                        │    │
│  │ ]                                                        │    │
│  │                                                          │    │
│  │ # 调用 Task Planner LLM 生成查询规格                     │    │
│  │ query_plan = await task_planner_llm(                     │    │
│  │     mapped_dimensions=mapped_dimensions,                 │    │
│  │     mapped_measures=mapped_measures,                     │    │
│  │     metadata=metadata                                    │    │
│  │ )                                                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  输出: QueryPlanningResult + 映射警告（如有）                    │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Understanding Agent 表计算识别

在现有的 `QuestionUnderstanding` 模型中添加表计算识别字段：

```python
class TableCalcType(str, Enum):
    RUNNING_TOTAL = "RUNNING_TOTAL"
    RANK = "RANK"
    MOVING_CALCULATION = "MOVING_CALCULATION"
    PERCENT_OF_TOTAL = "PERCENT_OF_TOTAL"
    DIFFERENCE_FROM = "DIFFERENCE_FROM"
    PERCENT_FROM = "PERCENT_FROM"
    PERCENT_DIFFERENCE_FROM = "PERCENT_DIFFERENCE_FROM"
    PERCENTILE = "PERCENTILE"

# QuestionUnderstanding 新增字段
table_calc_type: Optional[TableCalcType] = Field(default=None)
table_calc_dimensions: Optional[List[TableCalcFieldReference]] = Field(default=None)
```

### 5. 渐进式洞察与对话总结职责分离

| 系统 | 处理对象 | 存储位置 | 触发条件 |
|------|----------|----------|----------|
| 渐进式洞察 | 查询结果 DataFrame | VizQLState.insights | 数据行数 > 100 |
| SummarizationMiddleware | 对话历史 Messages | 压缩后的 Messages | 对话轮数 ≥ 10 |

**设计原则**：
- 渐进式洞察负责从大数据集中提取业务洞察（单次查询范围）
- SummarizationMiddleware 负责压缩长对话历史以节省 Token（整个会话范围）
- 两者物理隔离，不会产生冲突


## 数据模型

### VizQLContext
```python
@dataclass
class VizQLContext:
    """运行时上下文（不可变）"""
    datasource_luid: str
    user_id: str
    session_id: str
    max_replan_rounds: int = 3
    parallel_upper_limit: int = 5
    max_retry_times: int = 3
    max_subtasks_per_round: int = 10
```

### VizQLState
```python
class VizQLState(TypedDict):
    """工作流状态"""
    question: str
    boost_question: bool
    boosted_question: Optional[str]
    understanding: Optional[QuestionUnderstanding]
    query_plan: Optional[QueryPlanningResult]
    subtask_results: List[Dict[str, Any]]
    insights: List[Dict[str, Any]]  # 渐进式洞察存储位置
    all_insights: List[Dict[str, Any]]
    final_report: Dict[str, Any]
    replan_count: int
    current_stage: str
    metadata: Optional[Any]
    dimension_hierarchy: Optional[Dict[str, Any]]
    statistics: Optional[Dict[str, Any]]
    visualizations: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
```

### ReplanDecision
```python
class ReplanDecision(BaseModel):
    """重规划决策"""
    should_replan: bool
    completeness_score: float
    new_question: Optional[str]
    reasoning: str
```

## 正确性属性

*属性是一个特征或行为，应该在系统的所有有效执行中保持为真。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*

### 属性 1: 中间件配置完整性
*对于任何* Agent 创建请求，创建的 Agent 应该包含以下中间件：TodoListMiddleware、SummarizationMiddleware、ModelRetryMiddleware、ToolRetryMiddleware、FilesystemMiddleware（自主实现）、PatchToolCallsMiddleware（自主实现），以及可选的 HumanInTheLoopMiddleware
**验证需求: 1.2, 1.3**

### 属性 2: 工具配置完整性
*对于任何* DeepAgent 创建请求，创建的 Agent 应该配置所有必需的业务工具：get_metadata、parse_date、build_vizql_query、execute_vizql_query、semantic_map_fields、process_query_result、detect_statistics、save_large_result
**验证需求: 13.1-13.10**

### 属性 3: 工作流节点顺序保持
*对于任何* 工作流执行，当所有节点都需要执行时，节点执行顺序应该严格遵循：Boost → Understanding → Planning → Execute → Insight → Replanner
**验证需求: 2.2**

### 属性 4: Boost 节点条件跳过
*对于任何* 工作流执行，当 boost_question 标志为 False 时，工作流应该跳过 Boost 节点并直接从 Understanding 节点开始
**验证需求: 2.3**

### 属性 5: 重规划循环路由
*对于任何* 工作流执行，当 Replanner 节点决定需要重规划时（should_replan=True），工作流应该将执行路由回 Planning 节点（跳过 Understanding，因为重规划需要从元数据中选择字段，此时真实的技术字段名已经知道）
**验证需求: 2.4, 12.1, 12.2**

### 属性 6: 组件业务逻辑保持
*对于任何* 工具调用，工具封装前后对于相同输入应该产生相同的输出，证明业务逻辑未被改变
**验证需求: 13.10**

### 属性 7: 模型提供商切换支持
*对于任何* 支持的 LLM 提供商（Claude、DeepSeek、Qwen、OpenAI），系统应该能够通过配置切换而无需修改代码
**验证需求: 7.4, 16.2**

### 属性 8: 对话总结触发条件
*对于任何* 对话会话，当消息 token 数超过配置阈值时，系统应该触发 SummarizationMiddleware
**验证需求: 4.1**

### 属性 9: 总结内容选择性
*对于任何* 对话总结，生成的摘要应该包含对话交流内容但不应包含 VizQLState.insights 中的数据洞察内容
**验证需求: 4.6**

### 属性 10: 洞察内容保留
*对于任何* 对话总结，总结后的 VizQLState.insights 应该保留所有 Insight Agent 生成的数据洞察
**验证需求: 4.6**

### 属性 11: 大文件处理阈值
*对于任何* 工具输出，当输出 token 数超过配置阈值时，系统应该使用 FilesystemMiddleware 保存到文件系统
**验证需求: 5.1**

### 属性 12: 文件标识符唯一性
*对于任何* 两次不同的文件保存操作，生成的文件标识符应该是唯一的
**验证需求: 5.2**

### 属性 13: 文件系统往返一致性
*对于任何* 保存到文件系统的数据，使用返回的文件路径加载应该得到相同的数据
**验证需求: 5.2, 5.3**

### 属性 14: 会话文件清理
*对于任何* 用户会话，当会话终止时，与该会话关联的所有临时文件应该被删除
**验证需求: 5.7**

### 属性 15: 悬空工具调用修复
*对于任何* AIMessage 包含 tool_calls 但没有对应 ToolMessage 的情况，PatchToolCallsMiddleware 应该自动添加取消消息，避免 LLM 调用失败
**验证需求: 6.1**

### 属性 16: 悬空工具调用修复日志记录
*对于任何* 被自动修复的悬空工具调用，系统应该记录修复详情到日志中
**验证需求: 6.6**

### 属性 17: API 向后兼容性
*对于任何* 前端 API 请求，中间件集成后的响应格式应该与集成前保持一致
**验证需求: 16.3**

### 属性 18: LLM 调用重试
*对于任何* LLM 调用失败，ModelRetryMiddleware 应该自动重试最多 N 次（可配置）
**验证需求: 新增**

### 属性 19: 工具调用重试
*对于任何* 工具调用失败，ToolRetryMiddleware 应该自动重试最多 N 次（可配置）
**验证需求: 新增**

### 属性 20: Planning 阶段字段映射调用
*对于任何* Planning 节点执行，当 Understanding 结果包含业务术语时，系统应该为每个业务术语调用 semantic_map_fields 工具
**验证需求: 14.1, 14.2**

### 属性 21: 字段映射向量检索
*对于任何* semantic_map_fields 工具调用，系统应该使用 FAISS 向量检索返回 Top-5 候选字段
**验证需求: 14.3**

### 属性 22: 字段映射 LLM 判断条件
*对于任何* 向量检索结果，当候选字段数量大于 1 且最高分与次高分的相似度差异小于 0.2 时，系统应该调用 LLM 进行语义判断
**验证需求: 14.4**

### 属性 23: 映射后字段名使用
*对于任何* 查询规格生成，系统应该使用 semantic_map_fields 返回的技术字段名（matched_field）而非原始业务术语
**验证需求: 14.5**

### 属性 24: 低置信度映射警告
*对于任何* 字段映射结果，当置信度低于 0.7 时，系统应该在响应中包含映射不确定性警告
**验证需求: 14.6**

### 属性 25: 字段映射缓存命中
*对于任何* 相同业务术语的重复映射请求（在 1 小时内），系统应该从 Store 缓存返回结果而不重新执行向量检索
**验证需求: 14.8**

### 属性 26: 字段映射往返一致性
*对于任何* 业务术语，多次调用 semantic_map_fields 应该返回相同的映射结果
**验证需求: 14.8**


## 错误处理

### 中间件错误处理策略

| 中间件 | 错误类型 | 处理策略 |
|--------|----------|----------|
| SummarizationMiddleware | 总结失败 | 保留原始消息，记录警告日志 |
| ModelRetryMiddleware | 重试耗尽 | 抛出异常，由上层处理 |
| ToolRetryMiddleware | 重试耗尽 | 返回错误 ToolMessage |
| FilesystemMiddleware | 文件写入失败 | 返回原始内容，记录警告日志 |
| PatchToolCallsMiddleware | 修复失败 | 保留原始消息，记录警告日志 |
| HumanInTheLoopMiddleware | 用户超时 | 根据配置执行默认操作 |


## 测试策略

### 单元测试

- 每个自主实现的中间件需要完整的单元测试
- 测试覆盖率要求 >= 80%
- 测试文件位置：`tableau_assistant/tests/unit/middleware/`

### 集成测试

- 测试中间件与 StateGraph 的协作
- 测试中间件链的执行顺序
- 测试文件位置：`tableau_assistant/tests/integration/`

### 属性测试

- 使用 Hypothesis 框架
- 每个属性测试运行 100 次迭代
- 测试标注格式：`**Feature: middleware-integration, Property {number}: {property_text}**`emantic_map_fields（在元数据未变更的情况下）应该返回相同的 matched_field
**验证需求: 14.2, 14.5**

## 错误处理

### 错误类型

1. **配置错误**: 缺少必需的配置参数、无效的模型提供商
2. **工具调用错误**: 工具不存在、参数验证失败、工具执行异常
3. **工作流错误**: 节点执行失败、状态转换错误、超时错误
4. **存储错误**: 文件系统访问失败、SQLite 数据库错误
5. **中间件错误**: 中间件初始化失败、中间件执行异常

### 错误处理策略

- 配置错误：启动时验证，失败则拒绝启动
- 工具调用错误：PatchToolCallsMiddleware 尝试修复，失败则返回清晰错误
- 工作流错误：记录错误状态，支持重试
- 存储错误：降级处理，使用内存存储
- 中间件错误：跳过失败的中间件，记录警告

## 测试策略

### 单元测试
- 测试每个工具的封装正确性
- 测试中间件配置
- 测试 StateGraph 节点执行

### 属性测试
- 使用 Hypothesis 框架
- 每个属性测试运行 100 次迭代
- 测试标注格式：`**Feature: deepagents-integration, Property {number}: {property_text}**`

### 集成测试
- 端到端工作流测试
- RAG 字段映射端到端测试
- 中间件协同工作测试
