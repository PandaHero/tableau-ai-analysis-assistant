# ReAct Agent 重构设计文档 v2.0

## 概述

本设计文档描述将当前 7 节点 StateGraph 工作流重构为基于 LangGraph Subgraph + langgraph-supervisor 的层级 Agent 架构。这是一次彻底的重构，不考虑向后兼容性。

### 设计原则

1. **层级编排**：使用 LangGraph Subgraph 实现节点内部编排
2. **Agent 自主决策**：LLM 决定工具调用顺序，而非硬编码流程
3. **结构化错误响应**：工具返回结构化错误，LLM 自主决定如何处理
4. **Tableau Pulse 对齐**：洞察分析对齐 Tableau Pulse 专业级标准
5. **遵循规范**：Prompt 和数据模型遵循 `appendix-e-prompt-model-guide.md`

### 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| langgraph | 1.0.5 | 核心编排框架 (Subgraph) |
| langchain | 1.1.3 | LLM 抽象层 |

**重要决策**：不使用 `create_react_agent` (langgraph-prebuilt)，原因：
1. **不支持 Middleware**：项目依赖 FilesystemMiddleware、ModelRetryMiddleware 等
2. **流式输出受限**：无法实现 token 级别的流式输出
3. **自定义 ReAct 循环**：使用 LangGraph StateGraph 实现，完全支持 middleware 和 streaming

---

## 完整目录结构

```
tableau_assistant/
├── src/
│   ├── __init__.py
│   ├── main.py                          # FastAPI 入口
│   │
│   ├── agents/                          # Agent 层（LLM 决策单元）
│   │   ├── __init__.py
│   │   ├── base/                        # Agent 基类
│   │   │   ├── __init__.py
│   │   │   ├── agent.py                 # BaseAgent 抽象类
│   │   │   ├── prompt.py                # VizQLPrompt 基类
│   │   │   └── middleware_runner.py     # Middleware 执行器
│   │   │
│   │   ├── semantic_parser/             # 语义解析 Agent (ReAct)
│   │   │   ├── __init__.py
│   │   │   ├── agent.py                 # SemanticParserAgent (ReAct 模式)
│   │   │   ├── node.py                  # StateGraph 节点适配
│   │   │   ├── subgraph.py              # 内部 Subgraph 定义
│   │   │   ├── components/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── step1.py             # Step1 语义理解
│   │   │   │   ├── step2.py             # Step2 计算推理
│   │   │   │   └── react_loop.py        # ReAct 循环实现
│   │   │   └── prompts/
│   │   │       ├── __init__.py
│   │   │       ├── step1.py             # Step1 Prompt
│   │   │       ├── step2.py             # Step2 Prompt
│   │   │       └── react.py             # ReAct Prompt
│   │   │
│   │   ├── insight/                     # 洞察分析 Agent (Subgraph)
│   │   │   ├── __init__.py
│   │   │   ├── agent.py                 # InsightAgent
│   │   │   ├── node.py                  # StateGraph 节点适配
│   │   │   ├── subgraph.py              # 内部 Subgraph 定义 ★新增
│   │   │   ├── components/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── profiler.py          # EnhancedDataProfiler ★增强
│   │   │   │   ├── anomaly_detector.py  # AnomalyDetector
│   │   │   │   ├── chunker.py           # SemanticChunker
│   │   │   │   ├── analyzer.py          # ChunkAnalyzer
│   │   │   │   ├── coordinator.py       # AnalysisCoordinator ★增强
│   │   │   │   ├── accumulator.py       # InsightAccumulator
│   │   │   │   ├── synthesizer.py       # InsightSynthesizer
│   │   │   │   └── statistical_analyzer.py
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   └── profile.py           # EnhancedDataProfile ★新增
│   │   │   └── prompts/
│   │   │       ├── __init__.py
│   │   │       ├── analyzer.py
│   │   │       ├── coordinator.py       # 主持人 Prompt ★增强
│   │   │       └── synthesizer.py
│   │   │
│   │   ├── replanner/                   # 重规划 Agent
│   │   │   ├── __init__.py
│   │   │   ├── agent.py                 # ReplannerAgent
│   │   │   ├── node.py                  # StateGraph 节点适配
│   │   │   └── prompt.py
│   │   │
│   │   ├── field_mapper/                # 字段映射 (转为 Tool)
│   │   │   ├── __init__.py
│   │   │   ├── llm_selector.py          # LLM 选择器
│   │   │   └── prompt.py
│   │   │
│   │   └── dimension_hierarchy/         # 维度层级
│   │       ├── __init__.py
│   │       ├── node.py
│   │       └── prompt.py
│   │
│   ├── orchestration/                   # 编排层
│   │   ├── __init__.py
│   │   │
│   │   ├── tools/                       # Tool 定义 ★重构
│   │   │   ├── __init__.py
│   │   │   ├── base.py                  # BaseTool 抽象类
│   │   │   ├── registry.py              # Tool 注册表
│   │   │   ├── models.py                # Tool 输入输出模型 ★新增
│   │   │   ├── map_fields_tool.py       # 字段映射 Tool ★新增
│   │   │   ├── build_query_tool.py      # 查询构建 Tool ★新增
│   │   │   ├── execute_query_tool.py    # 查询执行 Tool ★新增
│   │   │   ├── data_model_tool.py       # 数据模型 Tool
│   │   │   ├── metadata_tool.py         # 元数据 Tool
│   │   │   └── schema_tool.py           # Schema Tool
│   │   │
│   │   ├── middleware/                  # 中间件
│   │   │   ├── __init__.py
│   │   │   ├── filesystem.py            # FilesystemMiddleware
│   │   │   ├── output_validation.py     # OutputValidationMiddleware
│   │   │   └── patch_tool_calls.py      # PatchToolCallsMiddleware
│   │   │
│   │   └── workflow/                    # 工作流定义
│   │       ├── __init__.py
│   │       ├── factory.py               # 主工作流工厂 ★重构
│   │       ├── routes.py                # 路由函数 ★简化
│   │       ├── state.py                 # State 定义
│   │       ├── executor.py              # 执行器
│   │       ├── context.py               # 上下文管理
│   │       └── printer.py               # 调试打印
│   │
│   ├── core/                            # 核心模型
│   │   ├── __init__.py
│   │   ├── state.py                     # VizQLState ★更新
│   │   ├── exceptions.py
│   │   ├── interfaces/                  # 接口定义
│   │   │   ├── __init__.py
│   │   │   ├── field_mapper.py
│   │   │   ├── platform_adapter.py
│   │   │   └── query_builder.py
│   │   └── models/                      # 数据模型
│   │       ├── __init__.py
│   │       ├── computations.py
│   │       ├── data_model.py
│   │       ├── dimension_hierarchy.py
│   │       ├── enums.py
│   │       ├── execute_result.py
│   │       ├── field_mapping.py
│   │       ├── fields.py
│   │       ├── filters.py
│   │       ├── insight.py               # ★增强
│   │       ├── parse_result.py
│   │       ├── query_request.py
│   │       ├── query.py
│   │       ├── replan.py
│   │       ├── step1.py
│   │       ├── step2.py
│   │       └── validation.py
│   │
│   ├── platforms/                       # 平台适配层
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── tableau/
│   │       ├── __init__.py
│   │       ├── adapter.py
│   │       ├── auth.py
│   │       ├── client.py
│   │       ├── field_mapper.py
│   │       ├── metadata.py
│   │       ├── query_builder.py
│   │       ├── vizql_client.py
│   │       └── models/
│   │
│   ├── infra/                           # 基础设施
│   │   ├── __init__.py
│   │   ├── ai/
│   │   │   ├── __init__.py
│   │   │   ├── llm.py
│   │   │   ├── embeddings.py
│   │   │   ├── reranker.py
│   │   │   └── rag/
│   │   ├── config/
│   │   │   ├── __init__.py
│   │   │   └── settings.py
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   ├── langgraph_store.py
│   │   │   └── data_model_cache.py
│   │   └── monitoring/
│   │       ├── __init__.py
│   │       └── callbacks.py
│   │
│   ├── api/                             # API 层
│   │   ├── __init__.py
│   │   ├── chat.py
│   │   ├── models.py
│   │   └── cache.py
│   │
│   └── nodes/                           # ★删除（合并到 Tools）
│       └── (已废弃)
│
├── tests/                               # 测试
│   ├── __init__.py
│   ├── orchestration/
│   │   └── tools/
│   │       ├── test_map_fields_tool.py
│   │       ├── test_build_query_tool.py
│   │       └── test_execute_query_tool.py
│   ├── agents/
│   │   ├── semantic_parser/
│   │   │   ├── test_react_agent.py
│   │   │   └── test_subgraph.py
│   │   └── insight/
│   │       ├── test_enhanced_profiler.py
│   │       └── test_subgraph.py
│   ├── integration/
│   │   ├── test_semantic_parser_flow.py
│   │   ├── test_insight_flow.py
│   │   └── test_replan_loop.py
│   └── e2e/
│       └── test_complete_workflow.py
│
└── docs/
    ├── PROMPT_AND_MODEL_GUIDE.md
    └── architecture.md
```

---

## 核心架构：层级 Agent 编排

### 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         Main Workflow (StateGraph)                               │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    SemanticParserAgent (Subgraph)                          │  │
│  │                                                                            │  │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────────┐   │  │
│  │  │   Step1     │───▶│   Step2     │───▶│     ReAct Loop              │   │  │
│  │  │  (语义理解)  │    │ (计算推理)   │    │  ┌─────────────────────┐   │   │  │
│  │  └─────────────┘    └─────────────┘    │  │ Tools:              │   │   │  │
│  │                                         │  │ • map_fields        │   │   │  │
│  │                                         │  │ • build_query       │   │   │  │
│  │                                         │  │ • execute_query     │   │   │  │
│  │                                         │  └─────────────────────┘   │   │  │
│  │                                         └─────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                         │                                        │
│                                         ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    InsightAgent (Subgraph)                                 │  │
│  │                                                                            │  │
│  │  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    │  │
│  │  │ EnhancedProfiler │───▶│ Coordinator LLM  │───▶│   Synthesizer    │    │  │
│  │  │ (Tableau Pulse)  │    │   (主持人决策)    │    │   (洞察综合)     │    │  │
│  │  └──────────────────┘    └──────────────────┘    └──────────────────┘    │  │
│  │           │                      │                                        │  │
│  │           ▼                      ▼                                        │  │
│  │  ┌──────────────────┐    ┌──────────────────┐                            │  │
│  │  │ DimensionIndex   │    │ ChunkAnalyzer    │                            │  │
│  │  │ AnomalyIndex     │    │ (分块分析)       │                            │  │
│  │  └──────────────────┘    └──────────────────┘                            │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                         │                                        │
│                                         ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                    ReplannerAgent (单节点)                                 │  │
│  │                                                                            │  │
│  │  评估完成度 → 识别缺失 → 生成探索问题 → 决策: should_replan               │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                         │                                        │
│                    ┌────────────────────┴────────────────────┐                  │
│                    ▼                                         ▼                  │
│           should_replan=True                        should_replan=False         │
│                    │                                         │                  │
│                    ▼                                         ▼                  │
│           SemanticParserAgent                              END                  │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### LangGraph Subgraph 机制

**核心概念**：Subgraph 是将一个完整的 Graph 作为另一个 Graph 的节点使用。

```python
from langgraph.graph import StateGraph, START, END

# 1. 定义 Subgraph（内部编排）
def create_semantic_parser_subgraph() -> StateGraph:
    """SemanticParser 内部 Subgraph"""
    
    subgraph = StateGraph(SemanticParserState)
    
    # 内部节点
    subgraph.add_node("step1", step1_node)
    subgraph.add_node("step2", step2_node)
    subgraph.add_node("react_loop", react_loop_node)
    
    # 内部边
    subgraph.add_edge(START, "step1")
    subgraph.add_conditional_edges(
        "step1",
        route_after_step1,
        {"step2": "step2", "react_loop": "react_loop", "end": END}
    )
    subgraph.add_edge("step2", "react_loop")
    subgraph.add_edge("react_loop", END)
    
    return subgraph.compile()


# 2. 在主 Graph 中使用 Subgraph 作为节点
def create_main_workflow() -> StateGraph:
    """主工作流"""
    
    graph = StateGraph(VizQLState)
    
    # Subgraph 作为节点
    semantic_parser_subgraph = create_semantic_parser_subgraph()
    insight_subgraph = create_insight_subgraph()
    
    graph.add_node("semantic_parser", semantic_parser_subgraph)
    graph.add_node("insight", insight_subgraph)
    graph.add_node("replanner", replanner_node)
    
    # 主工作流边
    graph.add_edge(START, "semantic_parser")
    graph.add_conditional_edges(
        "semantic_parser",
        route_after_semantic_parser,
        {"insight": "insight", "end": END}
    )
    graph.add_edge("insight", "replanner")
    graph.add_conditional_edges(
        "replanner",
        route_after_replanner,
        {"semantic_parser": "semantic_parser", "end": END}
    )
    
    return graph.compile(checkpointer=MemorySaver())
```

---

## SemanticParserAgent Subgraph 详细设计

### 内部状态定义

```python
class SemanticParserState(TypedDict):
    """SemanticParser Subgraph 内部状态"""
    
    # 输入
    question: str
    history: List[BaseMessage]
    data_model: Dict[str, Any]
    
    # Step1 输出
    step1_output: Optional[Step1Output]
    
    # Step2 输出
    step2_output: Optional[Step2Output]
    
    # ReAct 循环
    semantic_query: Optional[SemanticQuery]
    react_observations: List[Dict[str, Any]]
    current_tool_input: Dict[str, Any]
    iteration_count: int
    
    # 最终输出
    mapped_query: Optional[MappedQuery]
    vizql_query: Optional[QueryRequest]
    query_result: Optional[ExecuteResult]
    error: Optional[str]
```

### Subgraph 定义

```python
def create_semantic_parser_subgraph() -> StateGraph:
    """
    SemanticParser 内部 Subgraph
    
    流程:
    START → step1 → [step2] → react_loop → END
    
    step2 仅在 how_type=COMPLEX 时执行
    """
    
    subgraph = StateGraph(SemanticParserState)
    
    # ===== 节点定义 =====
    
    async def step1_node(state: SemanticParserState) -> Dict:
        """Step1: 语义理解与问题重述"""
        from .components.step1 import execute_step1
        
        output = await execute_step1(
            question=state["question"],
            history=state["history"],
            data_model=state["data_model"],
        )
        
        return {"step1_output": output}
    
    async def step2_node(state: SemanticParserState) -> Dict:
        """Step2: 计算推理（仅 COMPLEX）"""
        from .components.step2 import execute_step2
        
        output = await execute_step2(
            step1_output=state["step1_output"],
            data_model=state["data_model"],
        )
        
        return {"step2_output": output}
    
    async def react_loop_node(state: SemanticParserState) -> Dict:
        """ReAct 循环: 工具调用"""
        from .components.react_loop import execute_react_loop
        
        # 构建 SemanticQuery
        semantic_query = build_semantic_query(
            state["step1_output"],
            state.get("step2_output"),
        )
        
        result = await execute_react_loop(
            semantic_query=semantic_query,
            max_iterations=5,
        )
        
        return {
            "semantic_query": semantic_query,
            "mapped_query": result.get("mapped_query"),
            "vizql_query": result.get("vizql_query"),
            "query_result": result.get("query_result"),
            "react_observations": result.get("observations", []),
            "error": result.get("error"),
        }
    
    # ===== 路由函数 =====
    
    def route_after_step1(state: SemanticParserState) -> str:
        """Step1 后路由"""
        step1 = state.get("step1_output")
        
        if not step1:
            return "end"
        
        # 非数据查询意图，直接结束
        if step1.intent.type != IntentType.DATA_QUERY:
            return "end"
        
        # COMPLEX 需要 Step2
        if step1.how_type == HowType.COMPLEX:
            return "step2"
        
        # SIMPLE/RANKING 直接进入 ReAct
        return "react_loop"
    
    # ===== 构建 Subgraph =====
    
    subgraph.add_node("step1", step1_node)
    subgraph.add_node("step2", step2_node)
    subgraph.add_node("react_loop", react_loop_node)
    
    subgraph.add_edge(START, "step1")
    subgraph.add_conditional_edges(
        "step1",
        route_after_step1,
        {"step2": "step2", "react_loop": "react_loop", "end": END}
    )
    subgraph.add_edge("step2", "react_loop")
    subgraph.add_edge("react_loop", END)
    
    return subgraph.compile()
```

### 混合架构：QueryPipeline + 外层 ReAct 决策

**核心设计决策**：

1. **Pipeline 保证执行顺序**：Step1+Step2 → 字段映射 → 查询构建 → 查询执行 是固定流程
2. **Pipeline 内部处理重试**：字段映射失败时使用 suggestions 重试，无需 LLM 介入
3. **外层 ReAct 只做决策**：成功 → 洞察，可重试 → 带 hints 重试，需澄清 → 问用户
4. **中间件全程介入**：MiddlewareRunner 在每个阶段执行对应钩子

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SemanticParserAgent (Subgraph)                            │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    QueryPipeline (固定流程)                          │    │
│  │                                                                      │    │
│  │  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │    │
│  │  │  Step1   │──▶│  Step2   │──▶│ MapFields│──▶│ BuildQuery       │ │    │
│  │  │(语义理解)│   │(计算推理)│   │(字段映射)│   │(查询构建)        │ │    │
│  │  └──────────┘   └──────────┘   └────┬─────┘   └────────┬─────────┘ │    │
│  │       │              │              │                  │           │    │
│  │       │              │              │ 内部重试         │           │    │
│  │       │              │              │ (suggestions)    │           │    │
│  │       │              │              ▼                  ▼           │    │
│  │       │              │         ┌──────────────────────────────┐   │    │
│  │       │              │         │      ExecuteQuery            │   │    │
│  │       │              │         │      (查询执行)              │   │    │
│  │       │              │         └──────────────────────────────┘   │    │
│  │       │              │                      │                     │    │
│  │       ▼              ▼                      ▼                     │    │
│  │  MiddlewareRunner.call_model_with_middleware()                    │    │
│  │  - OutputValidationMiddleware (格式验证)                          │    │
│  │  - ModelRetryMiddleware (LLM 重试)                                │    │
│  │                                                                      │    │
│  │  MiddlewareRunner.call_tool_with_middleware()                     │    │
│  │  - FilesystemMiddleware (大结果保存)                              │    │
│  │  - ToolRetryMiddleware (工具重试)                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    外层 ReAct 决策 (LLM)                            │    │
│  │                                                                      │    │
│  │  Pipeline 返回 QueryResult:                                         │    │
│  │  ├─ success=True  ──────────────────────────────▶ 进入 Insight     │    │
│  │  ├─ can_retry=True, retry_hint="..."  ──────────▶ 带 hints 重试    │    │
│  │  └─ needs_clarification=True, question="..."  ──▶ 问用户           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### QueryPipeline 实现

```python
# agents/semantic_parser/components/query_pipeline.py

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from tableau_assistant.src.agents.base.middleware_runner import (
    MiddlewareRunner,
    Runtime,
    get_middleware_from_config,
)


@dataclass
class QueryResult:
    """Pipeline 执行结果"""
    success: bool
    
    # 成功时的输出
    mapped_query: Optional[MappedQuery] = None
    vizql_query: Optional[QueryRequest] = None
    query_result: Optional[ExecuteResult] = None
    
    # 错误信息
    error: Optional[QueryError] = None
    
    # 控制信号
    can_retry: bool = False
    retry_hint: Optional[str] = None
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    suggestions: List[str] = None


@dataclass
class QueryError:
    """结构化错误"""
    stage: str  # "step1" | "step2" | "map_fields" | "build_query" | "execute"
    type: str   # 错误类型
    message: str
    can_retry: bool
    retry_hint: Optional[str] = None
    suggestions: List[str] = None


class QueryPipeline:
    """
    查询执行 Pipeline
    
    保证执行顺序：Step1 → Step2 → MapFields → BuildQuery → Execute
    内部处理重试，返回结构化结果供外层 ReAct 决策
    
    中间件集成点：
    - Step1/Step2: call_model_with_middleware (OutputValidationMiddleware)
    - MapFields: call_tool_with_middleware (内部重试)
    - BuildQuery: 纯逻辑，无中间件
    - Execute: call_tool_with_middleware (FilesystemMiddleware)
    """
    
    def __init__(
        self,
        middleware_runner: Optional[MiddlewareRunner] = None,
        runtime: Optional[Runtime] = None,
        max_field_mapping_retries: int = 2,
    ):
        self.runner = middleware_runner
        self.runtime = runtime
        self.max_field_mapping_retries = max_field_mapping_retries
    
    async def execute(
        self,
        question: str,
        history: List[BaseMessage],
        data_model: Dict[str, Any],
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> QueryResult:
        """
        执行完整 Pipeline
        
        Args:
            question: 用户问题
            history: 对话历史
            data_model: 数据模型
            retry_context: 重试上下文（包含上次错误的 hints）
        
        Returns:
            QueryResult 结构化结果
        """
        try:
            # ===== Stage 1: Step1 语义理解 =====
            step1_output = await self._execute_step1(
                question, history, data_model, retry_context
            )
            
            if step1_output.intent.type != IntentType.DATA_QUERY:
                # 非数据查询，直接返回成功（无需后续步骤）
                return QueryResult(
                    success=True,
                    error=None,
                )
            
            # ===== Stage 2: Step2 计算推理（仅 COMPLEX）=====
            step2_output = None
            if step1_output.how_type == HowType.COMPLEX:
                step2_output = await self._execute_step2(
                    step1_output, data_model
                )
            
            # 构建 SemanticQuery
            semantic_query = self._build_semantic_query(step1_output, step2_output)
            
            # ===== Stage 3: 字段映射（带内部重试）=====
            map_result = await self._execute_map_fields_with_retry(
                semantic_query, retry_context
            )
            
            if not map_result.success:
                return map_result
            
            # ===== Stage 4: 查询构建 =====
            build_result = await self._execute_build_query(map_result.mapped_query)
            
            if not build_result.success:
                return build_result
            
            # ===== Stage 5: 查询执行 =====
            execute_result = await self._execute_query(build_result.vizql_query)
            
            return execute_result
            
        except Exception as e:
            return QueryResult(
                success=False,
                error=QueryError(
                    stage="pipeline",
                    type="unexpected_error",
                    message=str(e),
                    can_retry=False,
                ),
            )
    
    async def _execute_step1(
        self,
        question: str,
        history: List[BaseMessage],
        data_model: Dict[str, Any],
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> Step1Output:
        """
        执行 Step1 语义理解
        
        使用 MiddlewareRunner.call_model_with_middleware:
        - OutputValidationMiddleware: 验证输出格式
        - ModelRetryMiddleware: LLM 调用重试
        """
        from .step1 import build_step1_messages, parse_step1_output
        
        messages = build_step1_messages(question, history, data_model, retry_context)
        
        if self.runner:
            response = await self.runner.call_model_with_middleware(
                model=self._get_llm(),
                messages=messages,
                state={"question": question, "data_model": data_model},
                runtime=self.runtime,
            )
            ai_message = response.result[0]
        else:
            ai_message = await self._get_llm().ainvoke(messages)
        
        return parse_step1_output(ai_message.content)
    
    async def _execute_step2(
        self,
        step1_output: Step1Output,
        data_model: Dict[str, Any],
    ) -> Step2Output:
        """
        执行 Step2 计算推理
        
        使用 MiddlewareRunner.call_model_with_middleware
        """
        from .step2 import build_step2_messages, parse_step2_output
        
        messages = build_step2_messages(step1_output, data_model)
        
        if self.runner:
            response = await self.runner.call_model_with_middleware(
                model=self._get_llm(),
                messages=messages,
                state={"step1_output": step1_output.model_dump()},
                runtime=self.runtime,
            )
            ai_message = response.result[0]
        else:
            ai_message = await self._get_llm().ainvoke(messages)
        
        return parse_step2_output(ai_message.content)
    
    async def _execute_map_fields_with_retry(
        self,
        semantic_query: SemanticQuery,
        retry_context: Optional[Dict[str, Any]] = None,
    ) -> QueryResult:
        """
        执行字段映射，带内部重试
        
        重试策略：
        1. 首次尝试
        2. 如果 field_not_found，使用 suggestions 重试
        3. 最多重试 max_field_mapping_retries 次
        
        使用 MiddlewareRunner.call_tool_with_middleware
        """
        current_query = semantic_query
        suggestions_used = retry_context.get("field_suggestions", []) if retry_context else []
        
        for attempt in range(self.max_field_mapping_retries + 1):
            result = await self._execute_map_fields(current_query, suggestions_used)
            
            if result.success:
                return result
            
            # 检查是否可以内部重试
            if result.error and result.error.type == "field_not_found":
                if result.suggestions and attempt < self.max_field_mapping_retries:
                    # 使用 suggestions 更新查询，重试
                    suggestions_used.extend(result.suggestions)
                    current_query = self._apply_suggestions(current_query, result.suggestions)
                    continue
            
            # 无法内部重试，返回错误
            return result
        
        return result
    
    async def _execute_map_fields(
        self,
        semantic_query: SemanticQuery,
        suggestions: List[str] = None,
    ) -> QueryResult:
        """执行单次字段映射"""
        from ..tools.map_fields_tool import map_fields_tool
        
        tool_call = {
            "name": "map_fields",
            "args": {"semantic_query": semantic_query.model_dump()},
            "id": f"map_fields_{id(semantic_query)}",
        }
        
        if self.runner:
            result = await self.runner.call_tool_with_middleware(
                tool=map_fields_tool,
                tool_call=tool_call,
                state={"semantic_query": semantic_query.model_dump()},
                runtime=self.runtime,
            )
        else:
            result = await map_fields_tool.ainvoke(tool_call["args"])
        
        # 解析结果
        if hasattr(result, 'content'):
            output = self._parse_tool_result(result.content)
        else:
            output = result
        
        if output.error:
            return QueryResult(
                success=False,
                error=QueryError(
                    stage="map_fields",
                    type=output.error.type,
                    message=output.error.message,
                    can_retry=output.error.type == "field_not_found",
                    retry_hint=f"尝试使用以下字段: {output.error.suggestions}",
                    suggestions=output.error.suggestions,
                ),
                can_retry=output.error.type == "field_not_found",
                suggestions=output.error.suggestions,
            )
        
        return QueryResult(
            success=True,
            mapped_query=output.mapped_query,
        )
    
    async def _execute_build_query(
        self,
        mapped_query: MappedQuery,
    ) -> QueryResult:
        """
        执行查询构建
        
        纯逻辑转换，无需中间件
        """
        from ..tools.build_query_tool import build_query_tool
        
        try:
            result = await build_query_tool.ainvoke({"mapped_query": mapped_query.model_dump()})
            
            if hasattr(result, 'error') and result.error:
                return QueryResult(
                    success=False,
                    error=QueryError(
                        stage="build_query",
                        type=result.error.type,
                        message=result.error.reason,
                        can_retry=False,  # 构建错误通常不可重试
                    ),
                )
            
            return QueryResult(
                success=True,
                mapped_query=mapped_query,
                vizql_query=result.query,
            )
            
        except Exception as e:
            return QueryResult(
                success=False,
                error=QueryError(
                    stage="build_query",
                    type="build_error",
                    message=str(e),
                    can_retry=False,
                ),
            )
    
    async def _execute_query(
        self,
        vizql_query: QueryRequest,
    ) -> QueryResult:
        """
        执行查询
        
        使用 MiddlewareRunner.call_tool_with_middleware:
        - FilesystemMiddleware: 大结果自动保存到 files
        - ToolRetryMiddleware: 工具调用重试
        """
        from ..tools.execute_query_tool import execute_query_tool
        
        tool_call = {
            "name": "execute_query",
            "args": {"query": vizql_query.model_dump()},
            "id": f"execute_query_{id(vizql_query)}",
        }
        
        if self.runner:
            result = await self.runner.call_tool_with_middleware(
                tool=execute_query_tool,
                tool_call=tool_call,
                state={"vizql_query": vizql_query.model_dump()},
                runtime=self.runtime,
            )
            
            # 处理 Command（FilesystemMiddleware 可能返回）
            if hasattr(result, 'update') and result.update:
                # 大结果被保存到 files
                files_update = result.update.get("files", {})
                messages = result.update.get("messages", [])
                
                # 从 messages 中提取文件路径
                file_path = self._extract_file_path(messages)
                
                return QueryResult(
                    success=True,
                    mapped_query=None,  # 已在之前设置
                    vizql_query=vizql_query,
                    query_result=ExecuteResult(
                        data=None,
                        file_reference=file_path,
                        row_count=0,  # 需要从 files 读取
                    ),
                )
        else:
            result = await execute_query_tool.ainvoke(tool_call["args"])
        
        # 解析结果
        if hasattr(result, 'content'):
            output = self._parse_tool_result(result.content)
        else:
            output = result
        
        if hasattr(output, 'error') and output.error:
            return QueryResult(
                success=False,
                error=QueryError(
                    stage="execute",
                    type=output.error.type,
                    message=output.error.message,
                    can_retry=output.error.type in ["timeout", "execution_failed"],
                    retry_hint="查询执行失败，可能需要简化查询或检查数据源连接",
                ),
                can_retry=output.error.type in ["timeout", "execution_failed"],
            )
        
        return QueryResult(
            success=True,
            vizql_query=vizql_query,
            query_result=output.result,
        )
```

### ReAct Loop 实现

**重要设计决策**：不使用 `create_react_agent` (langgraph-prebuilt)，原因：
1. **不支持 Middleware**：`create_react_agent` 无法集成 FilesystemMiddleware、ModelRetryMiddleware 等
2. **流式输出受限**：无法实现 token 级别的流式输出
3. **自定义控制**：需要更细粒度的错误处理和状态管理

**解决方案**：使用 QueryPipeline + 外层 ReAct 决策循环

```python
# agents/semantic_parser/components/react_decision_loop.py

from typing import Dict, Any, List, Optional, AsyncIterator
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.language_models import BaseChatModel

from tableau_assistant.src.agents.base.middleware_runner import (
    MiddlewareRunner,
    Runtime,
    get_middleware_from_config,
)
from .query_pipeline import QueryPipeline, QueryResult


class ReActDecisionState(TypedDict):
    """外层 ReAct 决策状态"""
    # 输入
    question: str
    history: List[BaseMessage]
    data_model: Dict[str, Any]
    
    # Pipeline 结果
    pipeline_result: Optional[QueryResult]
    
    # 重试上下文
    retry_context: Optional[Dict[str, Any]]
    retry_count: int
    max_retries: int
    
    # 最终输出
    mapped_query: Optional[MappedQuery]
    vizql_query: Optional[QueryRequest]
    query_result: Optional[ExecuteResult]
    
    # 控制
    should_continue: bool
    needs_user_input: bool
    clarification_question: Optional[str]
    
    # Middleware 状态
    files: Dict[str, Any]


def create_react_decision_graph(
    llm: BaseChatModel,
) -> StateGraph:
    """
    创建外层 ReAct 决策 StateGraph
    
    流程:
    START → pipeline → decide → [retry | ask_user | end]
    
    Pipeline 内部保证执行顺序，外层只做决策
    """
    
    graph = StateGraph(ReActDecisionState)
    
    # ===== Pipeline 节点：执行固定流程 =====
    async def pipeline_node(state: ReActDecisionState, config: RunnableConfig) -> Dict:
        """
        执行 QueryPipeline
        
        Pipeline 内部处理：
        - Step1 + Step2 (带 OutputValidationMiddleware)
        - 字段映射 (带内部重试)
        - 查询构建
        - 查询执行 (带 FilesystemMiddleware)
        """
        # 获取 middleware
        middleware = get_middleware_from_config(config)
        runner = MiddlewareRunner(middleware) if middleware else None
        runtime = runner.build_runtime(config) if runner else None
        
        # 创建 Pipeline
        pipeline = QueryPipeline(
            middleware_runner=runner,
            runtime=runtime,
        )
        
        # 执行 Pipeline
        result = await pipeline.execute(
            question=state["question"],
            history=state["history"],
            data_model=state["data_model"],
            retry_context=state.get("retry_context"),
        )
        
        return {
            "pipeline_result": result,
            "retry_count": state.get("retry_count", 0) + 1,
        }
    
    # ===== Decide 节点：LLM 决策 =====
    async def decide_node(state: ReActDecisionState, config: RunnableConfig) -> Dict:
        """
        LLM 决策：根据 Pipeline 结果决定下一步
        
        决策逻辑：
        - success=True → 结束，进入 Insight
        - can_retry=True → 带 hints 重试
        - needs_clarification=True → 问用户
        - 其他错误 → 结束
        """
        result = state["pipeline_result"]
        
        if result.success:
            # 成功，提取结果
            return {
                "mapped_query": result.mapped_query,
                "vizql_query": result.vizql_query,
                "query_result": result.query_result,
                "should_continue": False,
                "needs_user_input": False,
            }
        
        # 检查是否可以重试
        if result.can_retry and state.get("retry_count", 0) < state.get("max_retries", 3):
            # 构建重试上下文
            retry_context = {
                "previous_error": result.error.message if result.error else None,
                "retry_hint": result.retry_hint,
                "field_suggestions": result.suggestions or [],
            }
            
            return {
                "retry_context": retry_context,
                "should_continue": True,
                "needs_user_input": False,
            }
        
        # 检查是否需要用户澄清
        if result.needs_clarification:
            return {
                "should_continue": False,
                "needs_user_input": True,
                "clarification_question": result.clarification_question,
            }
        
        # 无法处理的错误，结束
        return {
            "should_continue": False,
            "needs_user_input": False,
        }
    
    # ===== 路由函数 =====
    def route_after_decide(state: ReActDecisionState) -> str:
        """决策后路由"""
        if state.get("should_continue"):
            return "pipeline"  # 重试
        return "end"
    
    # ===== 构建图 =====
    graph.add_node("pipeline", pipeline_node)
    graph.add_node("decide", decide_node)
    
    graph.add_edge(START, "pipeline")
    graph.add_edge("pipeline", "decide")
    graph.add_conditional_edges(
        "decide",
        route_after_decide,
        {"pipeline": "pipeline", "end": END}
    )
    
    return graph.compile()


async def execute_semantic_parser(
    question: str,
    history: List[BaseMessage],
    data_model: Dict[str, Any],
    config: Optional[RunnableConfig] = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """
    执行语义解析
    
    使用 QueryPipeline + 外层 ReAct 决策
    
    Args:
        question: 用户问题
        history: 对话历史
        data_model: 数据模型
        config: RunnableConfig（包含 middleware）
        max_retries: 最大重试次数
    
    Returns:
        包含 mapped_query, vizql_query, query_result 的字典
    """
    from tableau_assistant.src.infra.ai.llm import get_llm
    
    llm = get_llm()
    react_graph = create_react_decision_graph(llm)
    
    initial_state = {
        "question": question,
        "history": history,
        "data_model": data_model,
        "pipeline_result": None,
        "retry_context": None,
        "retry_count": 0,
        "max_retries": max_retries,
        "mapped_query": None,
        "vizql_query": None,
        "query_result": None,
        "should_continue": True,
        "needs_user_input": False,
        "clarification_question": None,
        "files": {},
    }
    
    result = await react_graph.ainvoke(initial_state, config)
    
    return {
        "mapped_query": result.get("mapped_query"),
        "vizql_query": result.get("vizql_query"),
        "query_result": result.get("query_result"),
        "needs_user_input": result.get("needs_user_input", False),
        "clarification_question": result.get("clarification_question"),
        "files": result.get("files", {}),
    }


async def stream_semantic_parser(
    question: str,
    history: List[BaseMessage],
    data_model: Dict[str, Any],
    config: Optional[RunnableConfig] = None,
    max_retries: int = 3,
) -> AsyncIterator[Dict[str, Any]]:
    """
    流式执行语义解析
    
    支持 token 级别的流式输出
    
    Yields:
        事件字典:
        - {"type": "stage", "stage": "step1"} - 阶段开始
        - {"type": "token", "content": "..."} - LLM token
        - {"type": "stage_complete", "stage": "step1", "result": ...} - 阶段完成
        - {"type": "retry", "reason": "...", "hint": "..."} - 重试
        - {"type": "complete", "result": {...}} - 完成
    """
    from tableau_assistant.src.infra.ai.llm import get_llm
    
    llm = get_llm()
    react_graph = create_react_decision_graph(llm)
    
    initial_state = {
        "question": question,
        "history": history,
        "data_model": data_model,
        "pipeline_result": None,
        "retry_context": None,
        "retry_count": 0,
        "max_retries": max_retries,
        "mapped_query": None,
        "vizql_query": None,
        "query_result": None,
        "should_continue": True,
        "needs_user_input": False,
        "clarification_question": None,
        "files": {},
    }
    
    async for event in react_graph.astream_events(initial_state, config, version="v2"):
        event_type = event.get("event")
        
        # Token 流式输出
        if event_type == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content") and chunk.content:
                yield {"type": "token", "content": chunk.content}
        
        # 节点开始
        elif event_type == "on_chain_start":
            node_name = event.get("name", "")
            if node_name in ["step1", "step2", "map_fields", "build_query", "execute"]:
                yield {"type": "stage", "stage": node_name}
        
        # 节点结束
        elif event_type == "on_chain_end":
            node_name = event.get("name", "")
            if node_name == "pipeline":
                output = event.get("data", {}).get("output", {})
                pipeline_result = output.get("pipeline_result")
                
                if pipeline_result and not pipeline_result.success and pipeline_result.can_retry:
                    yield {
                        "type": "retry",
                        "reason": pipeline_result.error.message if pipeline_result.error else "Unknown",
                        "hint": pipeline_result.retry_hint,
                    }
            
            elif node_name == "LangGraph":
                output = event.get("data", {}).get("output", {})
                yield {
                    "type": "complete",
                    "result": {
                        "mapped_query": output.get("mapped_query"),
                        "vizql_query": output.get("vizql_query"),
                        "query_result": output.get("query_result"),
                        "needs_user_input": output.get("needs_user_input", False),
                        "clarification_question": output.get("clarification_question"),
                        "files": output.get("files", {}),
                    },
                }
```

---

## InsightAgent Subgraph 详细设计

### 内部状态定义

```python
class InsightState(TypedDict):
    """Insight Subgraph 内部状态"""
    
    # 输入
    query_result: Union[ExecuteResult, str]  # 数据或文件引用
    files: Dict[str, FileData]  # 大文件存储
    context: Dict[str, Any]  # 分析上下文
    
    # Phase 1: 数据画像
    enhanced_profile: Optional[EnhancedDataProfile]
    
    # Phase 2: 主持人决策
    coordinator_decisions: List[CoordinatorDecision]
    current_action: Optional[str]
    
    # Phase 3: 分块分析
    chunks: List[DataChunk]
    analyzed_chunks: List[int]
    chunk_insights: List[Insight]
    
    # Phase 4: 综合
    final_insights: List[Insight]
    summary: str
    
    # 控制
    iteration_count: int
    should_continue: bool
```

### Subgraph 定义

```python
def create_insight_subgraph() -> StateGraph:
    """
    Insight 内部 Subgraph
    
    流程:
    START → profiler → coordinator → [analyzer] → synthesizer → END
                          ↑              │
                          └──────────────┘ (循环直到完成)
    """
    
    subgraph = StateGraph(InsightState)
    
    # ===== 节点定义 =====
    
    async def profiler_node(state: InsightState) -> Dict:
        """Phase 1: 增强版数据画像"""
        from .components.profiler import EnhancedDataProfiler
        
        # 获取数据（可能从文件读取）
        data = get_data_from_state(state)
        
        profiler = EnhancedDataProfiler()
        profile = profiler.profile(data)
        
        # 基于画像推荐策略分块
        from .components.chunker import SemanticChunker
        chunker = SemanticChunker()
        chunks = chunker.chunk_by_strategy(
            data=data,
            strategy=profile.recommended_strategy,
            profile=profile,
        )
        
        return {
            "enhanced_profile": profile,
            "chunks": chunks,
            "analyzed_chunks": [],
            "chunk_insights": [],
        }
    
    async def coordinator_node(state: InsightState) -> Dict:
        """Phase 2: 主持人 LLM 决策"""
        from .components.coordinator import AnalysisCoordinator
        
        coordinator = AnalysisCoordinator()
        decision = await coordinator.decide(
            profile=state["enhanced_profile"],
            chunks=state["chunks"],
            analyzed_chunks=state["analyzed_chunks"],
            current_insights=state["chunk_insights"],
            context=state["context"],
        )
        
        decisions = state.get("coordinator_decisions", [])
        decisions.append(decision)
        
        return {
            "coordinator_decisions": decisions,
            "current_action": decision.action,
            "should_continue": decision.should_continue,
        }
    
    async def analyzer_node(state: InsightState) -> Dict:
        """Phase 3: 分块分析"""
        from .components.analyzer import ChunkAnalyzer
        
        decision = state["coordinator_decisions"][-1]
        analyzer = ChunkAnalyzer()
        
        if decision.action == "analyze_chunk":
            # 分析指定分块
            chunk_id = decision.target_chunk_id
            chunk = state["chunks"][chunk_id]
            insights = await analyzer.analyze(chunk, state["context"])
            
            analyzed = state["analyzed_chunks"] + [chunk_id]
            all_insights = state["chunk_insights"] + insights
            
        elif decision.action == "analyze_dimension":
            # 按维度精准读取分析
            data = read_by_dimension(
                state,
                decision.target_dimension,
                decision.target_dimension_value,
            )
            insights = await analyzer.analyze_data(data, state["context"])
            
            analyzed = state["analyzed_chunks"]
            all_insights = state["chunk_insights"] + insights
            
        elif decision.action == "analyze_anomaly":
            # 分析指定异常
            data = read_by_indices(state, decision.target_anomaly_indices)
            insights = await analyzer.analyze_anomalies(data, state["context"])
            
            analyzed = state["analyzed_chunks"]
            all_insights = state["chunk_insights"] + insights
        
        else:
            analyzed = state["analyzed_chunks"]
            all_insights = state["chunk_insights"]
        
        return {
            "analyzed_chunks": analyzed,
            "chunk_insights": all_insights,
            "iteration_count": state.get("iteration_count", 0) + 1,
        }
    
    async def synthesizer_node(state: InsightState) -> Dict:
        """Phase 4: 洞察综合"""
        from .components.synthesizer import InsightSynthesizer
        
        synthesizer = InsightSynthesizer()
        result = await synthesizer.synthesize(
            insights=state["chunk_insights"],
            profile=state["enhanced_profile"],
            context=state["context"],
        )
        
        return {
            "final_insights": result.insights,
            "summary": result.summary,
        }
    
    # ===== 路由函数 =====
    
    def route_after_coordinator(state: InsightState) -> str:
        """主持人决策后路由"""
        if not state.get("should_continue"):
            return "synthesizer"
        
        if state.get("iteration_count", 0) >= 10:  # 最大迭代
            return "synthesizer"
        
        return "analyzer"
    
    def route_after_analyzer(state: InsightState) -> str:
        """分析后路由"""
        return "coordinator"  # 回到主持人决策
    
    # ===== 构建 Subgraph =====
    
    subgraph.add_node("profiler", profiler_node)
    subgraph.add_node("coordinator", coordinator_node)
    subgraph.add_node("analyzer", analyzer_node)
    subgraph.add_node("synthesizer", synthesizer_node)
    
    subgraph.add_edge(START, "profiler")
    subgraph.add_edge("profiler", "coordinator")
    subgraph.add_conditional_edges(
        "coordinator",
        route_after_coordinator,
        {"analyzer": "analyzer", "synthesizer": "synthesizer"}
    )
    subgraph.add_edge("analyzer", "coordinator")  # 循环回主持人
    subgraph.add_edge("synthesizer", END)
    
    return subgraph.compile()
```

---

## Tool 定义

### Tool 输入输出模型

```python
# orchestration/tools/models.py

class MapFieldsInput(BaseModel):
    """map_fields Tool 输入"""
    semantic_query: SemanticQuery = Field(
        description="Platform-agnostic semantic query with business terms"
    )


class MapFieldsOutput(BaseModel):
    """map_fields Tool 输出"""
    mapped_query: Optional[MappedQuery] = None
    error: Optional[FieldMappingError] = None


class FieldMappingError(BaseModel):
    """字段映射错误"""
    type: Literal["field_not_found", "ambiguous_field"]
    field: str
    message: str
    suggestions: List[str] = Field(default_factory=list)


class BuildQueryInput(BaseModel):
    """build_query Tool 输入"""
    mapped_query: MappedQuery


class BuildQueryOutput(BaseModel):
    """build_query Tool 输出"""
    query: Optional[QueryRequest] = None
    error: Optional[QueryBuildError] = None


class QueryBuildError(BaseModel):
    """查询构建错误"""
    type: Literal["invalid_computation", "unsupported_operation"]
    reason: str
    computation: Optional[str] = None


class ExecuteQueryInput(BaseModel):
    """execute_query Tool 输入"""
    query: QueryRequest


class ExecuteQueryOutput(BaseModel):
    """execute_query Tool 输出"""
    result: Optional[ExecuteResult] = None
    error: Optional[ExecutionError] = None


class ExecutionError(BaseModel):
    """查询执行错误"""
    type: Literal["execution_failed", "timeout", "auth_error", "invalid_query"]
    code: str
    message: str
    details: Optional[str] = None
```

### Tool 实现

```python
# orchestration/tools/map_fields_tool.py

from langchain_core.tools import tool
from .models import MapFieldsInput, MapFieldsOutput, FieldMappingError


@tool
def map_fields(input: MapFieldsInput) -> MapFieldsOutput:
    """
    Map business terms to technical field names.
    
    Uses RAG + LLM hybrid approach:
    1. RAG retrieval for candidate fields
    2. LLM selection for best match
    
    Returns structured error if field not found or ambiguous.
    """
    from tableau_assistant.src.agents.field_mapper import FieldMapper
    
    try:
        mapper = FieldMapper()
        mapped_query = mapper.map(input.semantic_query)
        return MapFieldsOutput(mapped_query=mapped_query)
    
    except FieldNotFoundError as e:
        return MapFieldsOutput(
            error=FieldMappingError(
                type="field_not_found",
                field=e.field,
                message=str(e),
                suggestions=e.suggestions,
            )
        )
    
    except AmbiguousFieldError as e:
        return MapFieldsOutput(
            error=FieldMappingError(
                type="ambiguous_field",
                field=e.field,
                message=str(e),
                suggestions=e.candidates,
            )
        )
```

---

## EnhancedDataProfiler 设计

### Tableau Pulse 洞察类型对齐

| Tableau Pulse 洞察类型 | 优先级 | 我们的实现 |
|----------------------|-------|-----------|
| Period Over Period Change | P0 | PeriodChangeAnalysis |
| Unexpected Values | P0 | AnomalyIndex |
| Top Contributors | P0 | ContributorAnalysis |
| Concentrated Contribution Alert | P0 | ConcentrationRisk |
| Bottom Contributors | P1 | ContributorAnalysis |
| Top Drivers | P1 | (未来扩展) |
| Top Detractors | P1 | (未来扩展) |
| Current Trend | P1 | TrendAnalysis |
| Trend Change Alert | P2 | TrendAnalysis.change_points |

### 数据模型

```python
# agents/insight/models/profile.py

class EnhancedDataProfile(BaseModel):
    """增强版数据画像"""
    
    # 基础画像
    row_count: int
    column_count: int
    density: float
    statistics: Dict[str, ColumnStats]
    semantic_groups: List[SemanticGroup]
    
    # Tableau Pulse 风格洞察
    contributors: Optional[ContributorAnalysis] = None
    concentration_risk: Optional[ConcentrationRisk] = None
    period_changes: Optional[PeriodChangeAnalysis] = None
    trends: Optional[TrendAnalysis] = None
    
    # 智能索引
    dimension_index: Dict[str, DimensionIndex] = Field(default_factory=dict)
    anomaly_index: Optional[AnomalyIndex] = None
    
    # 分块策略推荐
    recommended_strategy: str = "by_position"
    strategy_reason: str = ""


class ContributorAnalysis(BaseModel):
    """贡献者分析"""
    dimension: str
    measure: str
    top_contributors: List[Contributor]
    bottom_contributors: List[Contributor]
    total_value: float


class Contributor(BaseModel):
    """单个贡献者"""
    dimension_value: str
    value: float
    percentage: float
    rank: int
    change_from_previous: Optional[float] = None


class ConcentrationRisk(BaseModel):
    """集中度风险"""
    dimension: str
    top_n_count: int
    top_n_percentage: float
    is_risky: bool
    risk_level: Literal["low", "medium", "high"]
    description: str


class PeriodChangeAnalysis(BaseModel):
    """同环比分析"""
    time_dimension: Optional[str] = None
    current_period_value: Optional[float] = None
    previous_period_value: Optional[float] = None
    change_value: Optional[float] = None
    change_percentage: Optional[float] = None
    change_direction: Literal["up", "down", "flat"] = "flat"


class TrendAnalysis(BaseModel):
    """趋势分析"""
    time_dimension: Optional[str] = None
    trend_direction: Literal["increasing", "decreasing", "stable", "volatile"] = "stable"
    trend_strength: float = 0.0
    change_points: List[int] = Field(default_factory=list)
    description: str = ""


class DimensionIndex(BaseModel):
    """维度索引 - 支持精准读取"""
    column: str
    unique_count: int
    value_ranges: Dict[str, ValueRange]


class ValueRange(BaseModel):
    """值范围"""
    start: int
    end: int
    count: int


class AnomalyIndex(BaseModel):
    """异常索引"""
    outlier_indices: List[int]
    anomaly_ratio: float
    by_column: Dict[str, List[int]]
    by_severity: Dict[str, List[int]]
```

---

## 主工作流 Factory

```python
# orchestration/workflow/factory.py

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from tableau_assistant.src.core.state import VizQLState
from tableau_assistant.src.agents.semantic_parser.subgraph import create_semantic_parser_subgraph
from tableau_assistant.src.agents.insight.subgraph import create_insight_subgraph
from tableau_assistant.src.agents.replanner.node import replanner_node
from .routes import route_after_semantic_parser, route_after_replanner


def create_workflow(
    use_sqlite_checkpointer: bool = False,
    sqlite_db_path: str = "data/workflow_checkpoints.db",
) -> StateGraph:
    """
    创建主工作流
    
    架构: 3 个 Agent 节点（2 个 Subgraph + 1 个单节点）
    
    流程:
    START → SemanticParser(Subgraph) → Insight(Subgraph) → Replanner → END
                                                              ↓
                                                    (should_replan=True)
                                                              ↓
                                                    SemanticParser(Subgraph)
    """
    
    graph = StateGraph(VizQLState)
    
    # ===== 创建 Subgraph =====
    semantic_parser_subgraph = create_semantic_parser_subgraph()
    insight_subgraph = create_insight_subgraph()
    
    # ===== 添加节点 =====
    # Subgraph 作为节点
    graph.add_node("semantic_parser", semantic_parser_subgraph)
    graph.add_node("insight", insight_subgraph)
    # 单节点
    graph.add_node("replanner", replanner_node)
    
    # ===== 添加边 =====
    graph.add_edge(START, "semantic_parser")
    
    graph.add_conditional_edges(
        "semantic_parser",
        route_after_semantic_parser,
        {"insight": "insight", "end": END}
    )
    
    graph.add_edge("insight", "replanner")
    
    graph.add_conditional_edges(
        "replanner",
        route_after_replanner,
        {"semantic_parser": "semantic_parser", "end": END}
    )
    
    # ===== 编译 =====
    if use_sqlite_checkpointer:
        from pathlib import Path
        import sqlite3
        Path(sqlite_db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(sqlite_db_path, check_same_thread=False)
        checkpointer = SqliteSaver(conn)
    else:
        checkpointer = MemorySaver()
    
    return graph.compile(checkpointer=checkpointer)
```

### 路由函数

```python
# orchestration/workflow/routes.py

from typing import Literal
from tableau_assistant.src.core.state import VizQLState
from tableau_assistant.src.core.models.enums import IntentType


def route_after_semantic_parser(state: VizQLState) -> Literal["insight", "end"]:
    """
    SemanticParser 后路由
    
    Rules:
    - intent != DATA_QUERY → end
    - query_result.is_success() → insight
    - query_result.error → end
    """
    parse_result = state.get("semantic_parse_result")
    query_result = state.get("query_result")
    
    # 非数据查询意图
    if parse_result and parse_result.intent.type != IntentType.DATA_QUERY:
        return "end"
    
    # 查询成功
    if query_result and hasattr(query_result, 'is_success') and query_result.is_success():
        return "insight"
    
    # 查询失败或无结果
    return "end"


def route_after_replanner(state: VizQLState) -> Literal["semantic_parser", "end"]:
    """
    Replanner 后路由
    
    Rules:
    - should_replan=True and replan_count < max_rounds → semantic_parser
    - should_replan=False or replan_count >= max_rounds → end
    """
    decision = state.get("replan_decision")
    replan_count = state.get("replan_count", 0)
    max_rounds = state.get("max_replan_rounds", 3)
    
    if decision and decision.should_replan and replan_count < max_rounds:
        return "semantic_parser"
    
    return "end"
```

---

## State 定义更新

```python
# core/state.py

from typing import TypedDict, List, Dict, Any, Optional, Annotated
import operator
from langchain_core.messages import BaseMessage


class VizQLState(TypedDict):
    """
    主工作流状态
    
    重构变更:
    - 移除: correction_count, correction_exhausted (由 ReAct 循环替代)
    - 移除: field_mapper_complete, query_builder_complete, execute_complete (合并到 semantic_parser)
    - 新增: tool_observations (ReAct 工具调用记录)
    - 新增: enhanced_profile (增强版数据画像)
    """
    
    # ===== 对话历史 =====
    messages: Annotated[List[BaseMessage], operator.add]
    answered_questions: Annotated[List[str], operator.add]
    
    # ===== 用户输入 =====
    question: str
    
    # ===== SemanticParserAgent 输出 =====
    semantic_parse_result: Optional[Any]  # SemanticParseResult
    semantic_query: Optional[Any]  # SemanticQuery
    restated_question: Optional[str]
    mapped_query: Optional[Any]  # MappedQuery
    vizql_query: Optional[Any]  # QueryRequest
    query_result: Optional[Any]  # ExecuteResult | str (文件引用)
    tool_observations: List[Dict[str, Any]]  # ReAct 工具调用记录
    
    # ===== InsightAgent 输出 =====
    insights: Annotated[List[Any], operator.add]  # List[Insight]
    all_insights: Annotated[List[Any], operator.add]
    enhanced_profile: Optional[Any]  # EnhancedDataProfile
    data_insight_profile: Optional[Dict[str, Any]]
    
    # ===== ReplannerAgent 输出 =====
    replan_decision: Optional[Any]  # ReplanDecision
    replan_count: int
    max_replan_rounds: int
    replan_history: Annotated[List[Dict], operator.add]
    
    # ===== 控制流 =====
    current_stage: str
    execution_path: Annotated[List[str], operator.add]
    
    # ===== 节点完成标志 (简化) =====
    semantic_parser_complete: bool
    insight_complete: bool
    replanner_complete: bool
    
    # ===== 数据模型 =====
    datasource: Optional[str]
    data_model: Optional[Dict[str, Any]]
    dimension_hierarchy: Optional[Dict[str, Dict[str, Any]]]
    current_dimensions: List[str]
    pending_questions: List[Dict[str, Any]]
    
    # ===== 大文件存储 =====
    files: Dict[str, Any]  # FilesystemMiddleware 存储
    
    # ===== 错误处理 =====
    errors: Annotated[List[Any], operator.add]
    warnings: Annotated[List[Any], operator.add]
```

---

## 完整数据流

### 正常流程示例

```
用户问题: "各省份销售额排名"
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SemanticParserAgent (Subgraph)                            │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Step1 Node                                                           │    │
│  │ 输入: question="各省份销售额排名", history=[], data_model={...}      │    │
│  │ 输出: Step1Output {                                                  │    │
│  │   what: ["销售额"],                                                  │    │
│  │   where: ["省份"],                                                   │    │
│  │   how_type: RANKING,                                                 │    │
│  │   intent: {type: DATA_QUERY}                                         │    │
│  │ }                                                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    │ (how_type != COMPLEX, 跳过 Step2)       │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ ReAct Loop Node                                                      │    │
│  │                                                                      │    │
│  │ Iteration 1:                                                         │    │
│  │   Thought: 需要先映射字段                                            │    │
│  │   Action: map_fields(semantic_query)                                │    │
│  │   Observation: {mapped_query: {...}}                                │    │
│  │                                                                      │    │
│  │ Iteration 2:                                                         │    │
│  │   Thought: 字段映射成功，构建查询                                    │    │
│  │   Action: build_query(mapped_query)                                 │    │
│  │   Observation: {query: {...}}                                       │    │
│  │                                                                      │    │
│  │ Iteration 3:                                                         │    │
│  │   Thought: 查询构建成功，执行查询                                    │    │
│  │   Action: execute_query(query)                                      │    │
│  │   Observation: {result: {data: [...], row_count: 31}}               │    │
│  │                                                                      │    │
│  │ Iteration 4:                                                         │    │
│  │   Thought: 查询成功，返回结果                                        │    │
│  │   Final Answer: {query_result: {...}}                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Subgraph 输出: {                                                            │
│    semantic_parse_result: {...},                                            │
│    query_result: ExecuteResult,                                             │
│    tool_observations: [...]                                                 │
│  }                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        │ route: query_result.is_success() → insight
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    InsightAgent (Subgraph)                                   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Profiler Node                                                        │    │
│  │                                                                      │    │
│  │ EnhancedDataProfiler 输出:                                           │    │
│  │ - contributors: {top: [广东 25%, 江苏 18%, ...]}                     │    │
│  │ - concentration_risk: {is_risky: true, level: "medium"}             │    │
│  │ - dimension_index: {省份: {广东: rows 0-5, 江苏: rows 6-10, ...}}   │    │
│  │ - recommended_strategy: "by_contributor"                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Coordinator Node (主持人 LLM)                                        │    │
│  │                                                                      │    │
│  │ 输入: 画像摘要 + 索引                                                │    │
│  │ 决策: {                                                              │    │
│  │   action: "analyze_dimension",                                      │    │
│  │   target_dimension: "省份",                                         │    │
│  │   target_dimension_value: "广东",                                   │    │
│  │   reasoning: "广东贡献最大，优先分析"                                │    │
│  │ }                                                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Analyzer Node                                                        │    │
│  │                                                                      │    │
│  │ 按维度精准读取: 只读取广东省数据 (rows 0-5)                          │    │
│  │ 生成洞察: [Insight("广东省销售额最高，占比 25%")]                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    │ (循环回 Coordinator)                    │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Coordinator Node (第 2 轮)                                           │    │
│  │                                                                      │    │
│  │ 决策: {action: "stop", completeness: 0.9}                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Synthesizer Node                                                     │    │
│  │                                                                      │    │
│  │ 综合洞察: "广东省销售额最高，占比 25%，存在中等集中度风险..."        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Subgraph 输出: {                                                            │
│    insights: [...],                                                         │
│    enhanced_profile: {...}                                                  │
│  }                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ReplannerAgent (单节点)                                   │
│                                                                              │
│  评估: completeness_score = 0.7                                             │
│  缺失: ["城市级别分析", "时间趋势"]                                         │
│  探索问题: ["广东省各城市销售额排名"]                                        │
│  决策: should_replan = True                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        │ route: should_replan=True → semantic_parser
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SemanticParserAgent (Round 2)                             │
│                                                                              │
│  处理新问题: "广东省各城市销售额排名"                                        │
│  ... (重复上述流程)                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
        │
        ▼ (继续循环直到 should_replan=False 或达到 max_rounds)
       END
```

---

## 中间件集成架构

### 完整中间件栈（8 个中间件）

项目使用 8 个中间件，按执行顺序排列：

| # | 中间件 | 来源 | 功能 | 使用的钩子 |
|---|--------|------|------|-----------|
| 1 | TodoListMiddleware | LangChain | 任务队列管理 | `before_agent`, `after_agent` |
| 2 | SummarizationMiddleware | LangChain | 对话历史自动摘要 | `wrap_model_call` |
| 3 | ModelRetryMiddleware | LangChain | LLM 调用指数退避重试 | `wrap_model_call` |
| 4 | ToolRetryMiddleware | LangChain | 工具调用指数退避重试 | `wrap_tool_call` |
| 5 | FilesystemMiddleware | 自定义 | 大结果自动保存到 files | `wrap_model_call`, `wrap_tool_call` |
| 6 | PatchToolCallsMiddleware | 自定义 | 修复悬空工具调用 | `before_agent`, `wrap_model_call` |
| 7 | HumanInTheLoopMiddleware | LangChain (可选) | 人工确认敏感操作 | `wrap_tool_call` |
| 8 | OutputValidationMiddleware | 自定义 | LLM 输出格式验证 | `after_model`, `after_agent` |

### 核心设计：MiddlewareRunner 全程介入

**关键原则**：所有 LLM 调用和工具调用都必须通过 MiddlewareRunner，确保中间件正确执行。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         QueryPipeline 中间件集成                             │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Stage: Step1 / Step2 (LLM 调用)                                     │    │
│  │                                                                      │    │
│  │  MiddlewareRunner.call_model_with_middleware()                      │    │
│  │  ├─ before_model hooks                                              │    │
│  │  ├─ wrap_model_call chain (洋葱模型，从外到内):                      │    │
│  │  │   ├─ SummarizationMiddleware: 对话历史超长时自动摘要             │    │
│  │  │   ├─ ModelRetryMiddleware: 指数退避重试 (1s→2s→4s)              │    │
│  │  │   ├─ FilesystemMiddleware: 注入 filesystem 系统提示              │    │
│  │  │   └─ PatchToolCallsMiddleware: 修复悬空工具调用                  │    │
│  │  └─ after_model hooks:                                              │    │
│  │      └─ OutputValidationMiddleware: 验证 JSON 输出格式              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Stage: MapFields / ExecuteQuery (工具调用)                          │    │
│  │                                                                      │    │
│  │  MiddlewareRunner.call_tool_with_middleware()                       │    │
│  │  └─ wrap_tool_call chain (洋葱模型，从外到内):                       │    │
│  │      ├─ ToolRetryMiddleware: 工具调用指数退避重试                   │    │
│  │      ├─ FilesystemMiddleware: 大结果自动保存到 files                │    │
│  │      │   - 检测结果大小 > token_limit (默认 20000)                  │    │
│  │      │   - 保存到 state["files"]                                    │    │
│  │      │   - 返回 Command(update={"files": {...}})                    │    │
│  │      └─ HumanInTheLoopMiddleware: 敏感操作人工确认 (可选)           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Stage: BuildQuery (纯逻辑)                                          │    │
│  │                                                                      │    │
│  │  无中间件介入，直接执行 QueryBuilder 逻辑                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 各中间件详细说明

#### 1. TodoListMiddleware (LangChain)
- **功能**：管理任务队列，支持多轮探索问题的调度
- **钩子**：`before_agent`, `after_agent`
- **集成点**：ReplannerAgent 生成的探索问题通过此中间件管理

#### 2. SummarizationMiddleware (LangChain)
- **功能**：当对话历史超过 token 阈值时自动摘要
- **钩子**：`wrap_model_call`
- **配置**：
  - `summarization_token_threshold`: 触发摘要的 token 阈值（默认根据模型调整）
  - `messages_to_keep`: 保留的最近消息数

#### 3. ModelRetryMiddleware (LangChain)
- **功能**：LLM 调用失败时指数退避重试
- **钩子**：`wrap_model_call`
- **配置**：
  - `model_max_retries`: 最大重试次数（默认 3）
  - `model_initial_delay`: 初始延迟（默认 1.0s）
  - `model_backoff_factor`: 退避因子（默认 2.0）
  - `model_max_delay`: 最大延迟（默认 60.0s）
  - `jitter`: 添加随机抖动防止雷群效应

#### 4. ToolRetryMiddleware (LangChain)
- **功能**：工具调用失败时指数退避重试
- **钩子**：`wrap_tool_call`
- **配置**：与 ModelRetryMiddleware 类似

#### 5. FilesystemMiddleware (自定义)
- **功能**：
  - 大结果自动保存到 `state["files"]`
  - 提供 `read_file`, `write_file`, `edit_file`, `glob`, `grep` 工具
- **钩子**：`wrap_model_call` (注入系统提示), `wrap_tool_call` (拦截大结果)
- **配置**：
  - `tool_token_limit_before_evict`: 触发保存的 token 阈值（默认 20000）
- **返回**：大结果时返回 `Command(update={"files": {...}, "messages": [...]})`

#### 6. PatchToolCallsMiddleware (自定义)
- **功能**：检测并修复悬空的工具调用（有 tool_call 但无对应 tool_result）
- **钩子**：`before_agent`, `wrap_model_call`
- **场景**：
  - 执行中断
  - 工具执行错误未正确处理
  - 用户在工具完成前发送新消息

#### 7. HumanInTheLoopMiddleware (LangChain, 可选)
- **功能**：敏感操作需要人工确认
- **钩子**：`wrap_tool_call`
- **配置**：
  - `interrupt_on`: 需要确认的工具名列表，如 `["write_todos", "execute_query"]`

#### 8. OutputValidationMiddleware (自定义)
- **功能**：
  - 验证 LLM 输出是否为有效 JSON
  - 使用 Pydantic Schema 验证输出结构
  - 验证最终状态是否包含必需字段
- **钩子**：`after_model`, `after_agent`
- **配置**：
  - `expected_schema`: 期望的 Pydantic 模型
  - `required_state_fields`: 必需的状态字段列表
  - `strict`: 严格模式，失败时抛出异常
  - `retry_on_failure`: 失败时触发 ModelRetryMiddleware 重试

### 中间件钩子执行时机

| 阶段 | 钩子 | 中间件 | 说明 |
|------|------|--------|------|
| Agent 开始 | `before_agent` | TodoListMiddleware | 加载待处理任务 |
| Agent 开始 | `before_agent` | PatchToolCallsMiddleware | 修复历史中的悬空工具调用 |
| Step1/Step2 | `wrap_model_call` | SummarizationMiddleware | 对话历史摘要 |
| Step1/Step2 | `wrap_model_call` | ModelRetryMiddleware | LLM 调用失败时指数退避重试 |
| Step1/Step2 | `wrap_model_call` | FilesystemMiddleware | 注入 filesystem 系统提示 |
| Step1/Step2 | `wrap_model_call` | PatchToolCallsMiddleware | 修复请求中的悬空工具调用 |
| Step1/Step2 | `after_model` | OutputValidationMiddleware | 验证 LLM 输出是否符合 JSON Schema |
| MapFields | `wrap_tool_call` | ToolRetryMiddleware | 字段映射失败时重试 |
| ExecuteQuery | `wrap_tool_call` | ToolRetryMiddleware | 查询执行失败时重试 |
| ExecuteQuery | `wrap_tool_call` | FilesystemMiddleware | 大结果自动保存到 files |
| ExecuteQuery | `wrap_tool_call` | HumanInTheLoopMiddleware | 敏感查询人工确认 (可选) |
| Agent 结束 | `after_agent` | TodoListMiddleware | 保存任务状态 |
| Agent 结束 | `after_agent` | OutputValidationMiddleware | 验证最终状态必需字段 |

### FilesystemMiddleware 大结果处理

**关键机制**：当工具返回结果超过 `tool_token_limit_before_evict` 时，自动保存到 `state["files"]`

```python
# FilesystemMiddleware 处理流程
async def awrap_tool_call(self, request, handler):
    # 1. 执行工具
    tool_result = await handler(request)
    
    # 2. 检查结果大小
    if len(tool_result.content) > 4 * self.tool_token_limit_before_evict:
        # 3. 保存到 files
        file_path = f"/large_tool_results/{sanitized_id}"
        self.backend.write(file_path, tool_result.content)
        
        # 4. 返回 Command 更新状态
        return Command(update={
            "files": {file_path: FileData(content=..., created_at=..., modified_at=...)},
            "messages": [ToolMessage(
                content=f"Tool result saved at: {file_path}\nUse read_file to read.",
                tool_call_id=request.tool_call["id"],
            )]
        })
    
    return tool_result
```

### QueryPipeline 中间件集成代码

```python
class QueryPipeline:
    """查询执行 Pipeline，全程集成中间件"""
    
    def __init__(
        self,
        middleware_runner: Optional[MiddlewareRunner] = None,
        runtime: Optional[Runtime] = None,
    ):
        self.runner = middleware_runner
        self.runtime = runtime
    
    async def _execute_step1(self, question, history, data_model, retry_context):
        """Step1: 使用 call_model_with_middleware"""
        messages = build_step1_messages(question, history, data_model, retry_context)
        
        if self.runner:
            # 通过 MiddlewareRunner 调用 LLM
            # OutputValidationMiddleware 会验证输出格式
            # ModelRetryMiddleware 会处理重试
            response = await self.runner.call_model_with_middleware(
                model=self._get_llm(),
                messages=messages,
                state={"question": question, "data_model": data_model},
                runtime=self.runtime,
            )
            ai_message = response.result[0]
        else:
            ai_message = await self._get_llm().ainvoke(messages)
        
        return parse_step1_output(ai_message.content)
    
    async def _execute_map_fields(self, semantic_query, suggestions):
        """MapFields: 使用 call_tool_with_middleware"""
        tool_call = {
            "name": "map_fields",
            "args": {"semantic_query": semantic_query.model_dump()},
            "id": f"map_fields_{id(semantic_query)}",
        }
        
        if self.runner:
            # 通过 MiddlewareRunner 调用工具
            # ToolRetryMiddleware 会处理重试
            result = await self.runner.call_tool_with_middleware(
                tool=map_fields_tool,
                tool_call=tool_call,
                state={"semantic_query": semantic_query.model_dump()},
                runtime=self.runtime,
            )
        else:
            result = await map_fields_tool.ainvoke(tool_call["args"])
        
        return self._parse_map_fields_result(result)
    
    async def _execute_query(self, vizql_query):
        """ExecuteQuery: 使用 call_tool_with_middleware，处理大结果"""
        tool_call = {
            "name": "execute_query",
            "args": {"query": vizql_query.model_dump()},
            "id": f"execute_query_{id(vizql_query)}",
        }
        
        if self.runner:
            # 通过 MiddlewareRunner 调用工具
            # FilesystemMiddleware 会处理大结果
            result = await self.runner.call_tool_with_middleware(
                tool=execute_query_tool,
                tool_call=tool_call,
                state={"vizql_query": vizql_query.model_dump()},
                runtime=self.runtime,
            )
            
            # 处理 Command（FilesystemMiddleware 返回）
            if hasattr(result, 'update') and result.update:
                files_update = result.update.get("files", {})
                messages = result.update.get("messages", [])
                file_path = self._extract_file_path(messages)
                
                return QueryResult(
                    success=True,
                    vizql_query=vizql_query,
                    query_result=ExecuteResult(
                        data=None,
                        file_reference=file_path,  # 大结果保存在文件中
                    ),
                )
        else:
            result = await execute_query_tool.ainvoke(tool_call["args"])
        
        return self._parse_execute_result(result)
```

### 中间件配置

### Middleware 集成架构

**核心机制**：使用 `MiddlewareRunner` 在自定义 StateGraph 节点中执行 middleware

```python
# 在节点函数中使用 MiddlewareRunner
async def my_node(state: Dict, config: RunnableConfig) -> Dict:
    # 1. 从 config 获取 middleware
    middleware = get_middleware_from_config(config)
    runner = MiddlewareRunner(middleware) if middleware else None
    runtime = runner.build_runtime(config) if runner else None
    
    # 2. before_agent 钩子
    if runner:
        state = await runner.run_before_agent(state, runtime)
    
    # 3. LLM 调用（带 wrap_model_call 钩子）
    if runner:
        response = await runner.call_model_with_middleware(
            model=llm,
            messages=messages,
            tools=tools,
            state=state,
            runtime=runtime,
        )
    else:
        response = await llm.ainvoke(messages)
    
    # 4. 工具调用（带 wrap_tool_call 钩子）
    # FilesystemMiddleware 在这里处理大结果
    if runner:
        tool_result = await runner.call_tool_with_middleware(
            tool=tool,
            tool_call=tool_call,
            state=state,
            runtime=runtime,
        )
    
    # 5. after_agent 钩子
    if runner:
        state = await runner.run_after_agent(state, runtime)
    
    return state
```

### 保留的中间件

| 中间件 | 应用层级 | 钩子 | 说明 |
|--------|---------|------|------|
| SummarizationMiddleware | Agent 级别 | wrap_model_call | 对话历史摘要 |
| ModelRetryMiddleware | LLM 调用级别 | wrap_model_call | 指数退避重试 |
| ToolRetryMiddleware | Tool 调用级别 | wrap_tool_call | 工具调用重试 |
| FilesystemMiddleware | Tool 调用级别 | wrap_tool_call | 大结果自动保存到 files |
| HumanInTheLoopMiddleware | Tool 级别 | wrap_tool_call | 人工确认 |
| PatchToolCallsMiddleware | Agent 级别 | after_model | 修复悬空工具调用 |

### FilesystemMiddleware 集成

**关键**：大数据必须通过 FilesystemMiddleware 处理

```python
# FilesystemMiddleware 在 wrap_tool_call 中拦截大结果
# 当工具返回结果超过 token_limit 时：
# 1. 自动保存到 state["files"]
# 2. 返回文件引用而非完整内容
# 3. 提供 read_file 工具用于分页读取

# 示例：execute_query 返回大结果
tool_result = await runner.call_tool_with_middleware(
    tool=execute_query_tool,
    tool_call={"name": "execute_query", "args": {...}},
    state=state,
    runtime=runtime,
)

# 如果结果太大，tool_result 可能是 Command：
# Command(update={
#     "files": {"/large_tool_results/xxx": FileData(...)},
#     "messages": [ToolMessage("Tool result saved at: /large_tool_results/xxx")]
# })
```

### 中间件与 MiddlewareRunner 集成

**核心机制**：使用 `MiddlewareRunner` 在自定义 StateGraph 节点中执行 middleware

```python
# 在节点函数中使用 MiddlewareRunner
async def my_node(state: Dict, config: RunnableConfig) -> Dict:
    # 1. 从 config 获取 middleware
    middleware = get_middleware_from_config(config)
    runner = MiddlewareRunner(middleware) if middleware else None
    runtime = runner.build_runtime(config) if runner else None
    
    # 2. before_agent 钩子 (TodoListMiddleware, PatchToolCallsMiddleware)
    if runner:
        state = await runner.run_before_agent(state, runtime)
    
    # 3. LLM 调用（带 wrap_model_call 钩子）
    # 执行: SummarizationMiddleware, ModelRetryMiddleware, 
    #       FilesystemMiddleware, PatchToolCallsMiddleware
    if runner:
        response = await runner.call_model_with_middleware(
            model=llm,
            messages=messages,
            tools=tools,
            state=state,
            runtime=runtime,
        )
    else:
        response = await llm.ainvoke(messages)
    
    # 4. after_model 钩子 (OutputValidationMiddleware)
    # 自动在 call_model_with_middleware 内部执行
    
    # 5. 工具调用（带 wrap_tool_call 钩子）
    # 执行: ToolRetryMiddleware, FilesystemMiddleware, HumanInTheLoopMiddleware
    if runner:
        tool_result = await runner.call_tool_with_middleware(
            tool=tool,
            tool_call=tool_call,
            state=state,
            runtime=runtime,
        )
    
    # 6. after_agent 钩子 (TodoListMiddleware, OutputValidationMiddleware)
    if runner:
        state = await runner.run_after_agent(state, runtime)
    
    return state
```

### FilesystemMiddleware 大结果处理

**关键**：大数据必须通过 FilesystemMiddleware 处理

```python
# FilesystemMiddleware 在 wrap_tool_call 中拦截大结果
# 当工具返回结果超过 token_limit (默认 20000) 时：
# 1. 自动保存到 state["files"]
# 2. 返回文件引用而非完整内容
# 3. 提供 read_file 工具用于分页读取

# 示例：execute_query 返回大结果
tool_result = await runner.call_tool_with_middleware(
    tool=execute_query_tool,
    tool_call={"name": "execute_query", "args": {...}},
    state=state,
    runtime=runtime,
)

# 如果结果太大，tool_result 可能是 Command：
# Command(update={
#     "files": {"/large_tool_results/xxx": FileData(...)},
#     "messages": [ToolMessage("Tool result saved at: /large_tool_results/xxx\nUse read_file to read.")]
# })
```

### Token 级别流式输出

**实现方式**：通过 `astream_events` API（真正的实时流式）

当前项目已经实现了真正的 token 级别实时流式输出：

```python
# 方式 1: llm.astream() - 真正的流式，每个 chunk 实时到达
async for chunk in llm.astream(messages, config=config):
    if hasattr(chunk, "content") and chunk.content:
        # 每个 token 到达时立即处理，不等待完整响应
        collected_content.append(chunk.content)

# 方式 2: astream_events - 真正的流式，捕获所有事件
async for event in workflow.astream_events(state, config, version="v2"):
    if event_type == "on_chat_model_stream":
        chunk = event.get("data", {}).get("chunk")
        if chunk and chunk.content:
            # 每个 token 实时 yield 给前端
            yield WorkflowEvent(
                type=EventType.TOKEN,
                node_name=current_node,
                content=chunk.content,
            )
```

**关键特性**：
- `llm.astream()` 和 `astream_events()` 都是**真正的实时流式**
- 每个 token 到达时立即 yield，不会等待完整响应
- 在 ReAct 循环中，`think` 节点的 LLM 调用也支持流式输出
- 通过 `config` 参数传递 callbacks，使 LangGraph 能捕获嵌套的流式事件

---

## 对比总结

| 方面 | 当前架构 | 新架构 |
|------|---------|--------|
| 节点数 | 7 | 3 (2 Subgraph + 1 单节点) |
| 路由函数 | 4 | 2 |
| 错误处理 | Observer + SelfCorrection | ReAct 循环内 |
| 工具调用 | 无 | 3 个 Tools |
| 内部编排 | 无 | Subgraph |
| 洞察分析 | 简单画像 | Tableau Pulse 对齐 |
| 扩展性 | 修改 factory.py | 添加 Tool 或 Subgraph 节点 |
| 代码量 | 多 | 减少 ~30% |
| 灵活性 | 固定流程 | LLM 自主决策 |

---

## 关键设计决策

| 决策 | 原因 | 影响 |
|------|------|------|
| 使用 Subgraph | LangGraph 原生支持，节点内部可编排 | 复杂逻辑封装 |
| ReAct 替代 Observer | 减少 LLM 调用，错误处理更自然 | 延迟降低 |
| Tableau Pulse 对齐 | 专业级数据分析标准 | 洞察质量提升 |
| 维度索引 | 支持精准读取 | 大数据处理效率 |
| 策略推荐 | 自动选择最佳分块策略 | 适应不同数据 |

---

## 依赖更新

```txt
# requirements.txt 无需新增依赖
# 使用现有的:
# - langgraph 1.0.5
# - langchain 1.1.3
# - 自定义 MiddlewareRunner (已存在)

# 移除（如果之前添加了）:
# - langgraph-prebuilt (不使用 create_react_agent)
# - langgraph-supervisor (不需要)
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Subgraph 状态传递 | 高 | 明确定义输入输出 Schema |
| ReAct 循环不稳定 | 高 | 设置 max_iterations，详细日志 |
| 大数据内存溢出 | 高 | FilesystemMiddleware + 索引精准读取 |
| 重规划死循环 | 高 | max_replan_rounds + answered_questions 去重 |

---

## 附录：完整功能清单

### SemanticParserAgent 功能

1. **Step1 语义理解**
   - 提取 what (度量)、where (维度)、how_type (计算类型)
   - 识别意图类型 (DATA_QUERY, CLARIFICATION, etc.)
   - 问题重述

2. **Step2 计算推理** (仅 COMPLEX)
   - 推断计算定义
   - 验证计算可行性

3. **ReAct 工具调用**
   - map_fields: 字段映射 (RAG + LLM)
   - build_query: 查询构建 (纯代码)
   - execute_query: 查询执行 (VizQL API)
   - 错误自主处理

### InsightAgent 功能

1. **EnhancedDataProfiler**
   - 基础统计 (row_count, density, etc.)
   - Tableau Pulse 洞察 (Contributors, Concentration, Period Change, Trend)
   - 智能索引 (DimensionIndex, AnomalyIndex)
   - 策略推荐

2. **AnalysisCoordinator (主持人)**
   - 查看画像摘要
   - 决策分析目标 (analyze_chunk, analyze_dimension, analyze_anomaly, stop)
   - 评估完成度

3. **ChunkAnalyzer**
   - 分块分析
   - 按维度精准读取
   - 异常分析

4. **InsightSynthesizer**
   - 洞察去重
   - 洞察综合
   - 生成摘要

### ReplannerAgent 功能

1. **完成度评估**
   - 基于洞察覆盖度
   - 基于维度层级

2. **缺失识别**
   - 未分析的维度
   - 未探索的方向

3. **探索问题生成**
   - 下钻问题
   - 对比问题
   - 趋势问题

4. **决策**
   - should_replan
   - 问题优先级排序
