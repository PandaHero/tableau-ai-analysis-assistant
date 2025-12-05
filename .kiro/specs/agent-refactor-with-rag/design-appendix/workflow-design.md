# 工作流层设计

## 概述

本文档描述工作流层的详细设计，包括 StateGraph 定义、路由逻辑和工厂函数。

对应项目结构：`src/workflow/`

---

## 工作流架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         StateGraph 工作流                                    │
│                                                                              │
│   START                                                                      │
│     │                                                                        │
│     ▼                                                                        │
│  ┌─────────┐                                                                 │
│  │ Boost?  │──── No ────────────────────────┐                               │
│  └────┬────┘                                │                               │
│       │ Yes                                 │                               │
│       ▼                                     │                               │
│  ┌─────────────────────────────────────┐   │                               │
│  │        Boost Agent (LLM)            │   │                               │
│  │  工具: get_metadata                 │   │                               │
│  │  输出: boosted_question             │   │                               │
│  └────────────────┬────────────────────┘   │                               │
│                   │                        │                               │
│                   ▼                        ▼                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Understanding Agent (LLM)                               │   │
│  │  工具: get_schema_module, parse_date, detect_date_format             │   │
│  │  输出: SemanticQuery (纯语义，无 VizQL 概念)                         │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │           QueryBuilder Node (代码优先 + LLM fallback)                │   │
│  │  组件: FieldMapper + ImplementationResolver + ExpressionGenerator    │   │
│  │  输出: VizQLQuery                                                    │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │              Execute Node (非 LLM)                                   │   │
│  │  功能: VizQL API 调用                                                │   │
│  │  输出: QueryResult                                                   │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                Insight Agent (LLM)                                   │   │
│  │  组件: AnalysisCoordinator (渐进式洞察)                              │   │
│  │  输出: accumulated_insights                                          │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                               ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               Replanner Agent (LLM)                                  │   │
│  │  工具: write_todos (来自 TodoListMiddleware)                         │   │
│  │  输出: ReplanDecision                                                │   │
│  └────────────────────────────┬────────────────────────────────────────┘   │
│                               │                                             │
│                    ┌──────────┴──────────┐                                  │
│                    │  智能重规划决策      │                                  │
│                    │  (LLM 评估完成度)    │                                  │
│                    └──────────┬──────────┘                                  │
│                               │                                             │
│           ┌───────────────────┴───────────────────┐                         │
│           │                                       │                         │
│    completeness < 0.9                    completeness >= 0.9                │
│    且 replan_count < max                 或 replan_count >= max             │
│           │                                       │                         │
│           ▼                                       ▼                         │
│    ┌──────────────┐                        ┌──────────┐                     │
│    │Understanding │                        │   END    │                     │
│    │ (重新理解)   │                        └──────────┘                     │
│    └──────────────┘                                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 工厂函数

```python
# tableau_assistant/src/workflow/factory.py

from typing import Dict, Any, Optional
from langchain.agents.middleware import (
    TodoListMiddleware,
    SummarizationMiddleware,
    HumanInTheLoopMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)
from langgraph.graph import StateGraph, START, END

from tableau_assistant.src.middleware.filesystem import FilesystemMiddleware
from tableau_assistant.src.middleware.patch_tool_calls import PatchToolCallsMiddleware
from tableau_assistant.src.workflow.state import VizQLState
from tableau_assistant.src.workflow.routes import route_after_replanner


def create_tableau_workflow(
    model_name: Optional[str] = None,
    store: Optional[BaseStore] = None,
    config: Optional[Dict[str, Any]] = None
) -> CompiledStateGraph:
    """
    创建 Tableau Assistant 的完整工作流
    
    工作流包含 6 个节点：Boost → Understanding → QueryBuilder → Execute → Insight → Replanner
    所有 LLM 节点共享同一套中间件栈。
    
    Args:
        model_name: LLM 模型名称
        store: 持久化存储实例
        config: 中间件和工作流配置
    
    Returns:
        编译后的 StateGraph 工作流
    """
    config = config or {}
    
    # 中间件栈（所有节点共享）
    middleware = [
        # LangChain 内置
        TodoListMiddleware(),
        SummarizationMiddleware(
            model=model_name,
            # 默认 20000，根据模型上下文长度调整
            trigger=("tokens", config.get("summarization_token_threshold", 20000)),
            keep=("messages", config.get("messages_to_keep", 10)),
        ),
        ModelRetryMiddleware(max_retries=config.get("model_max_retries", 3)),
        ToolRetryMiddleware(max_retries=config.get("tool_max_retries", 3)),
        
        # 自主实现
        FilesystemMiddleware(
            tool_token_limit_before_evict=config.get("filesystem_token_limit", 20000),
        ),
        PatchToolCallsMiddleware(),
    ]
    
    if config.get("interrupt_on"):
        middleware.append(HumanInTheLoopMiddleware(interrupt_on=config["interrupt_on"]))
    
    # 创建 StateGraph
    graph = StateGraph(VizQLState)
    
    # 添加节点
    graph.add_node("boost", boost_node)                    # LLM
    graph.add_node("understanding", understanding_node)    # LLM
    graph.add_node("query_builder", query_builder_node)    # 代码优先 + LLM fallback
    graph.add_node("execute", execute_node)                # 非 LLM
    graph.add_node("insight", insight_node)                # LLM
    graph.add_node("replanner", replanner_node)            # LLM
    
    # 条件边：是否跳过 Boost
    graph.add_conditional_edges(
        START,
        lambda state: "boost" if state.get("boost_question", True) else "understanding"
    )
    
    # 顺序边
    graph.add_edge("boost", "understanding")
    graph.add_edge("understanding", "query_builder")
    graph.add_edge("query_builder", "execute")
    graph.add_edge("execute", "insight")
    graph.add_edge("insight", "replanner")
    
    # 条件边：重规划路由
    graph.add_conditional_edges("replanner", route_after_replanner)
    
    return graph.compile(middleware=middleware, checkpointer=True)
```

---

## 路由逻辑

### 智能重规划路由

Replanner Agent 是智能的，它会：
1. **评估完成度**（completeness_score 0-1）
2. **识别缺失方面**（missing_aspects）
3. **生成新问题**（new_questions）
4. **智能路由**：根据分析状态决定下一步

```python
# tableau_assistant/src/workflow/routes.py

from langgraph.graph import END
from tableau_assistant.src.workflow.state import VizQLState


def route_after_replanner(state: VizQLState) -> str:
    """
    智能重规划路由逻辑
    
    决策规则（由 Replanner Agent LLM 决定）：
    1. completeness_score >= 0.9 → END（分析完整）
    2. completeness_score < 0.9 且 replan_count < max → 重规划
       - 如果新问题只需要补充数据 → query_builder（跳过语义理解）
       - 如果新问题需要重新理解 → understanding
    3. replan_count >= max → END（强制结束）
    
    路由规则：
    - should_replan=True 且 replan_count < max → understanding（重新理解新问题）
    - should_replan=False 或 replan_count >= max → END（结束分析）
    
    注意：Planning 节点已移除，重规划时直接回到 Understanding 节点重新理解新问题。
    """
    decision = state.get("replan_decision", {})
    replan_count = state.get("replan_count", 0)
    max_rounds = state.get("max_replan_rounds", 3)
    
    # 检查是否达到最大重规划次数
    if replan_count >= max_rounds:
        return END
    
    # 根据 Replanner 的智能决策路由
    should_replan = decision.get("should_replan", False)
    
    if should_replan:
        # 重规划：回到 Understanding 节点重新理解新问题
        return "understanding"
    
    return END


def route_after_start(state: VizQLState) -> str:
    """
    起始路由逻辑
    
    决策规则：
    1. 如果 boost_question=True → 返回 boost
    2. 否则 → 返回 understanding
    """
    if state.get("boost_question", True):
        return "boost"
    return "understanding"
```

### 重规划决策流程

```
Replanner Agent (LLM)
    │
    ├─ 评估完成度 (completeness_score)
    │   ├─ 0.9-1.0: 完全回答，无需重规划
    │   ├─ 0.7-0.9: 基本回答，考虑重规划
    │   ├─ 0.5-0.7: 部分回答，建议重规划
    │   └─ <0.5: 未能回答，必须重规划
    │
    ├─ 识别缺失方面 (missing_aspects)
    │   └─ 例: ["利润率分析", "华东地区异常原因"]
    │
    ├─ 生成新问题 (new_questions)
    │   └─ 例: ["各地区的利润率是多少？", "华东地区利润率低的原因？"]
    │
    └─ 决定下一步
        ├─ should_replan=True → Understanding（重新理解新问题）
        └─ should_replan=False → END（结束分析）
```

---

## 中间件配置

### 中间件来源与分类

| 中间件 | 来源 | 功能 | 提供的工具 |
|--------|------|------|-----------|
| `TodoListMiddleware` | LangChain | 任务队列管理 | `write_todos`, `read_todos` |
| `SummarizationMiddleware` | LangChain | 对话历史自动总结 | 无（自动触发） |
| `ModelRetryMiddleware` | LangChain | LLM 调用失败自动重试 | 无（自动触发） |
| `ToolRetryMiddleware` | LangChain | 工具调用失败自动重试 | 无（自动触发） |
| `HumanInTheLoopMiddleware` | LangChain | 人工确认（可选） | 无（自动触发） |
| `FilesystemMiddleware` | 自主实现 | 大结果自动转存 | `read_file`, `write_file` |
| `PatchToolCallsMiddleware` | 自主实现 | 修复悬空工具调用 | 无（自动触发） |

### 配置参数

```python
DEFAULT_CONFIG = {
    # SummarizationMiddleware
    # 根据模型上下文长度调整，预留 30% 空间给输出
    # - Claude 3.5: 200K context → 阈值 ~60K
    # - DeepSeek: 64K context → 阈值 ~20K
    # - Qwen: 32K context → 阈值 ~10K
    # 默认使用保守值，适配大多数模型
    "summarization_token_threshold": 20000,
    "messages_to_keep": 10,
    
    # RetryMiddleware
    "model_max_retries": 3,
    "tool_max_retries": 3,
    
    # FilesystemMiddleware
    "filesystem_token_limit": 20000,
    
    # HumanInTheLoopMiddleware
    "interrupt_on": None,  # 设置为 ["write_todos"] 启用人工确认
    
    # Replanner
    "max_replan_rounds": 3,
}
```

### 模型上下文长度参考

| 模型 | 上下文长度 | 建议 summarization_token_threshold |
|------|-----------|-----------------------------------|
| Claude 3.5 Sonnet | 200K | 60000 |
| DeepSeek V3 | 64K | 20000 |
| Qwen 2.5 | 32K | 10000 |
| GPT-4o | 128K | 40000 |

**计算公式**：`threshold = context_length * 0.3`（预留 70% 空间给系统提示、工具定义和输出）
