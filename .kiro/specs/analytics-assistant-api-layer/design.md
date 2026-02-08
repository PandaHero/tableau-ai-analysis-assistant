# Analytics Assistant API 层设计文档

## 1. 概述

### 1.1 设计目标

本设计文档定义 Analytics Assistant 的 API 层架构，包括：

- **FastAPI 应用层**：提供 RESTful API 和 SSE 流式端点
- **工作流编排层**：编排完整的查询执行流程（认证 → 数据源解析 → 数据模型加载 → semantic_parser 子图）
- **数据持久化层**：会话管理、用户设置、用户反馈
- **流式输出机制**：将后端 token 流转换为 SSE 事件
- **认证与授权**：基于 Tableau 用户身份的数据隔离

### 1.2 技术栈

| 组件 | 技术选型 | 版本 |
|------|---------|------|
| Web 框架 | FastAPI | 0.100+ |
| ASGI 服务器 | Uvicorn | 0.20+ |
| ORM | SQLAlchemy | 2.0+ |
| 数据验证 | Pydantic | 2.0+ |
| 工作流编排 | LangGraph | 0.0.30+ |
| 数据库（开发） | SQLite | 3.35+ |
| 数据库（生产） | PostgreSQL | 14+ |
| 异步驱动 | aiosqlite / asyncpg | 最新 |

### 1.3 架构原则

1. **全异步设计**：所有 I/O 操作使用 async/await
2. **依赖注入**：通过 FastAPI 依赖注入管理组件生命周期
3. **配置驱动**：所有可配置参数从 `app.yaml` 读取
4. **无状态设计**：支持水平扩展（会话状态存储在数据库）
5. **遵循规范**：严格遵循 `coding-standards.md`



## 2. 目录结构设计

### 2.1 API 层目录结构

```
analytics_assistant/src/api/
├── __init__.py
├── main.py                  # FastAPI 应用入口
├── dependencies.py          # 依赖注入（数据库会话、认证等）
├── middleware.py            # 中间件（CORS、日志、错误处理）
├── models/                  # Pydantic 模型
│   ├── __init__.py
│   ├── chat.py              # 聊天相关模型
│   ├── session.py           # 会话相关模型
│   ├── settings.py          # 设置相关模型
│   ├── feedback.py          # 反馈相关模型
│   └── common.py            # 通用模型（错误响应等）
├── routers/                 # API 路由
│   ├── __init__.py
│   ├── chat.py              # /api/chat/* 端点
│   ├── sessions.py          # /api/sessions/* 端点
│   ├── settings.py          # /api/settings/* 端点
│   ├── feedback.py          # /api/feedback/* 端点
│   └── health.py            # /health 端点
├── database/                # 数据库相关
│   ├── __init__.py
│   ├── connection.py        # 数据库连接管理
│   ├── models.py            # SQLAlchemy ORM 模型
│   └── migrations/          # 数据库迁移脚本
│       ├── __init__.py
│       └── init_db.py       # 初始化脚本
└── utils/                   # 工具函数
    ├── __init__.py
    ├── sse.py               # SSE 事件格式化
    ├── auth.py              # 认证工具
    └── logging.py           # 日志工具
```

### 2.2 工作流编排层目录结构

```
analytics_assistant/src/orchestration/
├── __init__.py
├── workflow/
│   ├── __init__.py
│   ├── context.py           # WorkflowContext（已存在）
│   ├── executor.py          # WorkflowExecutor（新增）
│   └── callbacks.py         # 流式输出回调（新增）
```



## 3. 架构设计

### 3.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端应用                                  │
│                    (Vue 3 + Vercel AI SDK)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/SSE
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI 应用层                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Chat Router │  │Session Router│  │Settings Router│          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                   │
│         │                  ▼                  ▼                   │
│         │          ┌─────────────────────────────┐               │
│         │          │   Database Layer (SQLite)   │               │
│         │          └─────────────────────────────┘               │
│         │                                                         │
│         ▼                                                         │
│  ┌─────────────────────────────────────────────────┐            │
│  │         WorkflowExecutor (编排层)                 │            │
│  │  ┌──────────────────────────────────────────┐   │            │
│  │  │  顶层 LangGraph 图                        │   │            │
│  │  │  ┌────────────┐  ┌────────────┐         │   │            │
│  │  │  │ Semantic   │→ │   Field    │         │   │            │
│  │  │  │  Parser    │  │   Mapper   │         │   │            │
│  │  │  └────────────┘  └────────────┘         │   │            │
│  │  │         │              │                 │   │            │
│  │  │         ▼              ▼                 │   │            │
│  │  │  ┌────────────┐  ┌────────────┐         │   │            │
│  │  │  │   Field    │→ │  Tableau   │         │   │            │
│  │  │  │  Semantic  │  │  GraphQL   │         │   │            │
│  │  │  └────────────┘  └────────────┘         │   │            │
│  │  └──────────────────────────────────────────┘   │            │
│  │                                                   │            │
│  │  SSE 回调注入 (on_token, on_node_start, ...)    │            │
│  └─────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    后端基础设施层                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  LLM Service │  │  RAG Service │  │Tableau Adapter│          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 请求处理流程

#### 3.2.1 SSE 流式聊天请求流程

```
1. 前端发送 POST /api/chat/stream
   ├─ 请求体: { messages, datasourceName, language, ... }
   └─ 请求头: X-Tableau-Username

2. FastAPI 路由处理
   ├─ 验证用户身份（X-Tableau-Username）
   ├─ 验证请求参数（Pydantic 模型）
   └─ 调用 WorkflowExecutor

3. WorkflowExecutor 初始化
   ├─ 创建 WorkflowContext
   ├─ 转换 datasourceName → datasourceLUID
   ├─ 使用 HistoryManager 裁剪对话历史
   └─ 注入 SSE 回调函数到 RunnableConfig

4. 执行顶层 LangGraph 图
   ├─ semantic_parser Agent
   │  ├─ 节点开始 → 发送 thinking event (understanding, running)
   │  ├─ LLM 调用 → 触发 on_token → 发送 token events
   │  └─ 节点完成 → 发送 thinking event (understanding, completed)
   │
   ├─ field_mapper Agent
   │  ├─ 节点开始 → 发送 thinking event (mapping, running)
   │  ├─ LLM 调用 → 触发 on_token → 发送 token events
   │  └─ 节点完成 → 发送 thinking event (mapping, completed)
   │
   ├─ field_semantic Agent
   │  └─ （类似流程）
   │
   ├─ query_adapter_node
   │  ├─ 节点开始 → 发送 thinking event (building, running)
   │  └─ 节点完成 → 发送 thinking event (building, completed)
   │
   ├─ Tableau GraphQL 查询
   │  ├─ 节点开始 → 发送 thinking event (executing, running)
   │  ├─ 查询完成 → 发送 data event (查询结果)
   │  └─ 节点完成 → 发送 thinking event (executing, completed)
   │
   └─ feedback_learner_node
      ├─ 节点开始 → 发送 thinking event (generating, running)
      ├─ 生成建议 → 发送 suggestions event
      └─ 节点完成 → 发送 thinking event (generating, completed)

5. 发送完成事件
   └─ 发送 complete event

6. 关闭 SSE 连接
```

#### 3.2.2 会话管理请求流程

```
1. 前端发送 GET /api/sessions
   └─ 请求头: X-Tableau-Username

2. FastAPI 路由处理
   ├─ 验证用户身份
   ├─ 查询数据库（过滤 tableau_username）
   └─ 返回会话列表

3. 数据库查询
   └─ SELECT * FROM sessions 
       WHERE tableau_username = ? 
       ORDER BY updated_at DESC
```



## 4. 工作流编排层设计

### 4.1 WorkflowExecutor 设计

`WorkflowExecutor` 是工作流编排的核心组件，负责：

1. 认证和数据源解析
2. 加载数据模型和字段语义
3. 创建 WorkflowContext 并注入 SSE 回调
4. 执行 semantic_parser 子图
5. 处理错误和超时

#### 4.1.1 WorkflowExecutor 接口

```python
# analytics_assistant/src/orchestration/workflow/executor.py

from typing import AsyncIterator, Dict, Any, Optional, List
from langgraph.graph import StateGraph
from langgraph.graph.state import RunnableConfig

from analytics_assistant.src.orchestration.workflow import WorkflowContext
from analytics_assistant.src.platform.base import BasePlatformAdapter


class WorkflowExecutor:
    """工作流执行器
    
    负责编排完整的查询工作流。
    
    核心职责：
    1. 认证和数据源解析（datasourceName → LUID）
    2. 加载数据模型和字段语义（使用 TableauDataLoader）
    3. 创建 WorkflowContext
    4. 执行 semantic_parser 子图（内部已包含所有 Agent 节点）
    5. 注入 SSE 回调函数
    6. 处理错误和超时
    
    重要说明：
    - semantic_parser 子图已经是完整的端到端流程
    - field_mapper 和 field_semantic 不是独立的顶层步骤
    - field_semantic 在 data_preparation 阶段通过 TableauDataLoader 调用
    - field_mapper 在 semantic_parser 子图内部调用
    
    Attributes:
        _tableau_username: Tableau 用户名（用于认证）
    """
    
    def __init__(
        self,
        tableau_username: str,
    ):
        """初始化 WorkflowExecutor
        
        Args:
            tableau_username: Tableau 用户名
        """
        self._tableau_username = tableau_username
    
    async def execute_stream(
        self,
        question: str,
        datasource_luid: str,
        history: Optional[List[Dict[str, str]]] = None,
        language: str = "zh",
        analysis_depth: str = "detailed",
        session_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """执行工作流并返回 SSE 事件流
        
        Args:
            question: 用户问题
            datasource_luid: 数据源 LUID
            history: 对话历史（已裁剪）
            language: 语言
            analysis_depth: 分析深度
            session_id: 会话 ID
        
        Yields:
            SSE 事件字典
        """
        # 实现见 4.3 节
        pass
```

### 4.2 顶层 LangGraph 图设计

顶层图负责编排查询执行流程，并在关键节点注入回调。

#### 4.2.1 图结构

```python
# analytics_assistant/src/orchestration/workflow/graph.py

from typing import Dict, Any, Optional, List
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from analytics_assistant.src.agents.semantic_parser.graph import create_semantic_parser_graph


def create_top_level_graph() -> CompiledStateGraph:
    """创建顶层 LangGraph 图
    
    重要说明：
    - semantic_parser 子图已经是完整的端到端流程，内部包含：
      intent_router → query_cache → rule_prefilter → feature_cache →
      feature_extractor → field_retriever → dynamic_schema_builder →
      modular_prompt_builder → few_shot_manager → semantic_understanding →
      output_validator → filter_validator → query_adapter → error_corrector →
      feedback_learner
    - field_mapper 是 semantic_parser 子图内部通过 state 传递结果后调用的
    - field_semantic 是预处理步骤，在 TableauDataLoader 中调用
    
    因此顶层图只需要：
    1. data_preparation: 认证、数据源解析、数据模型加载、字段语义推断
    2. semantic_parser: 完整的语义解析子图（内部包含所有 Agent 节点）
    
    Returns:
        编译后的顶层图
    """
    # semantic_parser 是完整的 LangGraph 子图（15+ 节点）
    semantic_parser_graph = create_semantic_parser_graph()
    
    # 创建顶层图
    workflow = StateGraph(WorkflowState)
    
    # 添加节点
    # data_preparation: 加载数据模型、字段语义、创建 WorkflowContext
    workflow.add_node("data_preparation", data_preparation_node)
    # semantic_parser: 完整子图，内部包含所有 Agent 节点和条件路由
    workflow.add_node("semantic_parser", semantic_parser_graph)
    
    # 定义边
    workflow.set_entry_point("data_preparation")
    workflow.add_edge("data_preparation", "semantic_parser")
    workflow.add_edge("semantic_parser", END)
    
    return workflow.compile()


class WorkflowState(TypedDict):
    """顶层工作流状态
    
    注意：semantic_parser 子图使用自己的 SemanticParserState，
    顶层状态只需要传入初始参数和接收最终结果。
    """
    # 输入
    question: str
    datasource_luid: str
    history: Optional[List[Dict[str, str]]]
    language: str
    analysis_depth: str
    
    # data_preparation 输出（传递给 semantic_parser 子图）
    data_model: Optional[Dict[str, Any]]
    field_semantic: Optional[Dict[str, Any]]
    current_time: Optional[str]
    
    # semantic_parser 子图输出
    semantic_output: Optional[Dict[str, Any]]
    query_result: Optional[Dict[str, Any]]
    suggestions: Optional[List[str]]
    
    # 错误信息
    error: Optional[str]
```

### 4.3 SSE 回调注入机制

通过 `RunnableConfig.configurable` 注入回调函数，在节点执行时触发。

#### 4.3.1 回调函数定义

```python
# analytics_assistant/src/orchestration/workflow/callbacks.py

from typing import Callable, Awaitable, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SSECallbacks:
    """SSE 回调函数集合
    
    负责将后端事件转换为 SSE 事件。
    """
    
    def __init__(
        self,
        event_queue: asyncio.Queue,
    ):
        """初始化回调函数
        
        Args:
            event_queue: 事件队列（用于发送 SSE 事件）
        """
        self.event_queue = event_queue
    
    async def on_token(self, token: str) -> None:
        """Token 回调：LLM 返回 token 时触发
        
        Args:
            token: LLM 生成的 token
        """
        await self.event_queue.put({
            "type": "token",
            "content": token
        })
    
    async def on_thinking(self, thinking: str) -> None:
        """Thinking 回调：R1 模型思考过程
        
        Args:
            thinking: 思考内容
        """
        await self.event_queue.put({
            "type": "thinking_token",
            "content": thinking
        })
    
    async def on_node_start(self, node_name: str) -> None:
        """节点开始回调
        
        Args:
            node_name: 节点名称
        """
        stage = self._get_processing_stage(node_name)
        if stage:
            await self.event_queue.put({
                "type": "thinking",
                "stage": stage,
                "name": self._get_stage_display_name(stage),
                "status": "running"
            })
    
    async def on_node_end(self, node_name: str) -> None:
        """节点完成回调
        
        Args:
            node_name: 节点名称
        """
        stage = self._get_processing_stage(node_name)
        if stage:
            await self.event_queue.put({
                "type": "thinking",
                "stage": stage,
                "name": self._get_stage_display_name(stage),
                "status": "completed"
            })
    
    def _get_processing_stage(self, node_name: str) -> Optional[str]:
        """根据节点名称返回 ProcessingStage
        
        只有涉及 LLM 调用或用户可见的节点才返回 stage。
        
        Args:
            node_name: 节点名称
        
        Returns:
            ProcessingStage 或 None
        """
        # LLM 调用节点映射
        llm_node_mapping = {
            "feature_extractor_node": "understanding",
            "semantic_understanding_node": "understanding",
            "error_corrector_node": "understanding",
            "field_mapper": "mapping",
            "field_semantic": "understanding",
        }
        
        # 用户可见节点映射（不调用 LLM，但需要展示）
        visible_node_mapping = {
            "query_adapter": "building",
            "tableau_query": "executing",
            "feedback_learner": "generating",
        }
        
        # 合并映射
        all_mappings = {**llm_node_mapping, **visible_node_mapping}
        
        return all_mappings.get(node_name)
    
    def _get_stage_display_name(self, stage: str, language: str = "zh") -> str:
        """获取阶段的显示名称
        
        Args:
            stage: ProcessingStage
            language: 语言
        
        Returns:
            显示名称
        """
        names_zh = {
            "understanding": "理解问题",
            "mapping": "字段映射",
            "building": "构建查询",
            "executing": "执行分析",
            "generating": "生成洞察",
        }
        
        names_en = {
            "understanding": "Understanding",
            "mapping": "Mapping Fields",
            "building": "Building Query",
            "executing": "Executing Analysis",
            "generating": "Generating Insights",
        }
        
        return names_zh.get(stage, stage) if language == "zh" else names_en.get(stage, stage)
```



#### 4.3.2 WorkflowExecutor.execute_stream 实现

```python
# analytics_assistant/src/orchestration/workflow/executor.py (续)

import asyncio
import json
from typing import AsyncIterator, Dict, Any, Optional, List

async def execute_stream(
    self,
    question: str,
    datasource_name: str,
    history: Optional[List[Dict[str, str]]] = None,
    language: str = "zh",
    analysis_depth: str = "detailed",
    session_id: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """执行工作流并返回 SSE 事件流
    
    内部流程：
    1. 认证（获取 Tableau auth token）
    2. 数据源名称 → LUID 转换
    3. 加载数据模型和字段语义（使用 TableauDataLoader）
    4. 创建 WorkflowContext
    5. 执行 semantic_parser 子图
    
    Args:
        question: 用户问题
        datasource_name: 数据源名称（前端传入）
        history: 对话历史（已裁剪）
        language: 语言
        analysis_depth: 分析深度
        session_id: 会话 ID
    
    Yields:
        SSE 事件字典
    """
    # 创建事件队列
    event_queue = asyncio.Queue()
    
    # 创建回调函数
    callbacks = SSECallbacks(event_queue)
    
    # 创建 RunnableConfig，注入回调
    config = RunnableConfig(
        configurable={
            "on_token": callbacks.on_token,
            "on_thinking": callbacks.on_thinking,
            "on_node_start": callbacks.on_node_start,
            "on_node_end": callbacks.on_node_end,
        }
    )
    
    # 创建初始状态
    initial_state = {
        "question": question,
        "datasource_luid": datasource_luid,
        "history": history or [],
        "language": language,
        "analysis_depth": analysis_depth,
    }
    
    # 创建工作流执行任务
    async def run_workflow():
        try:
            # 使用 astream 监听节点执行
            async for event in self.workflow_graph.astream(
                initial_state,
                config,
                stream_mode="updates"
            ):
                for node_name, node_output in event.items():
                    # 节点开始
                    await callbacks.on_node_start(node_name)
                    
                    # 处理节点输出
                    if "query_result" in node_output:
                        # 发送查询结果数据
                        await event_queue.put({
                            "type": "data",
                            "tableData": node_output["query_result"]
                        })
                    
                    if "chart_config" in node_output:
                        # 发送图表配置
                        await event_queue.put({
                            "type": "chart",
                            "chartConfig": node_output["chart_config"]
                        })
                    
                    if "suggestions" in node_output:
                        # 发送建议问题
                        await event_queue.put({
                            "type": "suggestions",
                            "questions": node_output["suggestions"]
                        })
                    
                    # 节点完成
                    await callbacks.on_node_end(node_name)
            
            # 发送完成事件
            await event_queue.put({"type": "complete"})
        
        except Exception as e:
            logger.exception(f"工作流执行失败: {e}")
            # 发送错误事件
            await event_queue.put({
                "type": "error",
                "error": str(e)
            })
        
        finally:
            # 标记队列结束
            await event_queue.put(None)
    
    # 启动工作流任务
    workflow_task = asyncio.create_task(run_workflow())
    
    try:
        # 从队列中读取事件并 yield
        while True:
            event = await event_queue.get()
            if event is None:
                # 队列结束
                break
            yield event
    
    finally:
        # 确保工作流任务被取消
        if not workflow_task.done():
            workflow_task.cancel()
            try:
                await workflow_task
            except asyncio.CancelledError:
                pass
```

### 4.4 数据源名称转换

将前端传入的 `datasourceName` 转换为 `datasourceLUID`。

```python
# analytics_assistant/src/orchestration/datasource/resolver.py

from typing import Optional
import logging

from analytics_assistant.src.core.interfaces import BasePlatformAdapter


logger = logging.getLogger(__name__)


class DataSourceNotFoundError(Exception):
    """数据源未找到异常"""
    
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class DataSourceResolver:
    """数据源解析器
    
    负责将数据源名称转换为 LUID。
    """
    
    def __init__(self, platform_adapter: BasePlatformAdapter):
        """初始化解析器
        
        Args:
            platform_adapter: 平台适配器
        """
        self.platform_adapter = platform_adapter
    
    async def resolve_datasource_luid(
        self,
        datasource_name: str,
    ) -> str:
        """将数据源名称转换为 LUID
        
        Args:
            datasource_name: 数据源名称
        
        Returns:
            数据源 LUID
        
        Raises:
            DataSourceNotFoundError: 数据源不存在
        """
        try:
            # 通过 Tableau GraphQL 查询 LUID
            luid = await self.platform_adapter.get_datasource_luid(datasource_name)
            
            if not luid:
                raise DataSourceNotFoundError(
                    f"数据源不存在: {datasource_name}"
                )
            
            logger.info(f"数据源名称转换: {datasource_name} → {luid}")
            return luid
        
        except Exception as e:
            logger.error(f"数据源名称转换失败: {datasource_name}, 错误: {e}")
            raise DataSourceNotFoundError(
                f"数据源名称转换失败: {datasource_name}"
            ) from e
```



## 5. 数据库设计

### 5.1 数据库连接管理

使用 SQLAlchemy 2.0 异步 API 管理数据库连接。

```python
# analytics_assistant/src/api/database/connection.py

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
import logging

from analytics_assistant.src.infra.config import get_config


logger = logging.getLogger(__name__)

# 声明基类
Base = declarative_base()

# 全局引擎和会话工厂
_engine = None
_async_session_factory = None


def get_database_url() -> str:
    """从配置获取数据库 URL
    
    Returns:
        数据库连接 URL
    """
    config = get_config()
    api_config = config.get("api", {})
    database_config = api_config.get("database", {})
    
    # 默认使用 SQLite
    return database_config.get(
        "url",
        "sqlite+aiosqlite:///./analytics_assistant.db"
    )


def init_database():
    """初始化数据库引擎和会话工厂"""
    global _engine, _async_session_factory
    
    database_url = get_database_url()
    logger.info(f"初始化数据库: {database_url}")
    
    # 创建异步引擎
    _engine = create_async_engine(
        database_url,
        echo=False,  # 生产环境设为 False
        pool_pre_ping=True,  # 连接池健康检查
    )
    
    # 创建会话工厂
    _async_session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（依赖注入）
    
    Yields:
        数据库会话
    """
    if _async_session_factory is None:
        raise RuntimeError("数据库未初始化，请先调用 init_database()")
    
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_database():
    """关闭数据库连接"""
    global _engine
    if _engine:
        await _engine.dispose()
        logger.info("数据库连接已关闭")
```

### 5.2 ORM 模型定义

```python
# analytics_assistant/src/api/database/models.py

from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    DateTime,
    Integer,
    Index,
    JSON,
)
from sqlalchemy.sql import func

from .connection import Base


class Session(Base):
    """会话表
    
    存储用户的聊天会话。
    """
    __tablename__ = "sessions"
    
    # 主键
    id = Column(String(36), primary_key=True)  # UUID v4
    
    # 用户身份
    tableau_username = Column(String(255), nullable=False, index=True)
    
    # 会话信息
    title = Column(String(500), nullable=False)
    messages = Column(JSON, nullable=False)  # List[Dict[str, str]]
    
    # 时间戳
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # 索引
    __table_args__ = (
        Index("idx_tableau_username_updated_at", "tableau_username", "updated_at"),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "tableau_username": self.tableau_username,
            "title": self.title,
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class UserSettings(Base):
    """用户设置表
    
    存储用户的个性化设置。
    """
    __tablename__ = "user_settings"
    
    # 主键
    tableau_username = Column(String(255), primary_key=True)
    
    # 设置字段
    language = Column(String(10), nullable=False, default="zh")
    analysis_depth = Column(String(20), nullable=False, default="detailed")
    theme = Column(String(20), nullable=False, default="light")
    default_datasource_id = Column(String(255), nullable=True)
    show_thinking_process = Column(Boolean, nullable=False, default=True)
    
    # 时间戳
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tableau_username": self.tableau_username,
            "language": self.language,
            "analysis_depth": self.analysis_depth,
            "theme": self.theme,
            "default_datasource_id": self.default_datasource_id,
            "show_thinking_process": self.show_thinking_process,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class UserFeedback(Base):
    """用户反馈表
    
    存储用户对 AI 回复的评价。
    """
    __tablename__ = "user_feedback"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 用户身份
    tableau_username = Column(String(255), nullable=False, index=True)
    
    # 反馈信息
    message_id = Column(String(255), nullable=False, index=True)
    type = Column(String(20), nullable=False)  # positive | negative
    reason = Column(String(500), nullable=True)
    comment = Column(Text, nullable=True)
    
    # 时间戳
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "tableau_username": self.tableau_username,
            "message_id": self.message_id,
            "type": self.type,
            "reason": self.reason,
            "comment": self.comment,
            "created_at": self.created_at.isoformat(),
        }
```

### 5.3 数据库迁移脚本

```python
# analytics_assistant/src/api/database/migrations/init_db.py

import asyncio
import logging

from analytics_assistant.src.api.database.connection import (
    init_database,
    Base,
    _engine,
)


logger = logging.getLogger(__name__)


async def create_tables():
    """创建所有表"""
    if _engine is None:
        raise RuntimeError("数据库未初始化")
    
    logger.info("开始创建数据库表...")
    
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("数据库表创建完成")


async def drop_tables():
    """删除所有表（仅用于开发）"""
    if _engine is None:
        raise RuntimeError("数据库未初始化")
    
    logger.warning("开始删除数据库表...")
    
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    logger.warning("数据库表删除完成")


async def main():
    """主函数"""
    init_database()
    await create_tables()


if __name__ == "__main__":
    asyncio.run(main())
```



## 6. API 端点设计

### 6.1 Pydantic 模型定义

#### 6.1.1 聊天相关模型

```python
# analytics_assistant/src/api/models/chat.py

from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class Message(BaseModel):
    """消息模型"""
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: Optional[datetime] = None


class ChatRequest(BaseModel):
    """聊天请求模型"""
    messages: List[Message] = Field(..., description="对话历史")
    datasource_name: str = Field(..., description="数据源名称")
    language: Literal["zh", "en"] = Field(default="zh", description="语言")
    analysis_depth: Literal["detailed", "comprehensive"] = Field(
        default="detailed",
        description="分析深度"
    )
    session_id: Optional[str] = Field(None, description="会话 ID")
```

#### 6.1.2 会话相关模型

```python
# analytics_assistant/src/api/models/session.py

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    title: Optional[str] = Field(None, description="会话标题")


class CreateSessionResponse(BaseModel):
    """创建会话响应"""
    session_id: str = Field(..., description="会话 ID")
    created_at: datetime = Field(..., description="创建时间")


class SessionModel(BaseModel):
    """会话模型"""
    id: str
    tableau_username: str
    title: str
    messages: List[Message]
    created_at: datetime
    updated_at: datetime


class GetSessionsResponse(BaseModel):
    """获取会话列表响应"""
    sessions: List[SessionModel]
    total: int


class UpdateSessionRequest(BaseModel):
    """更新会话请求"""
    title: Optional[str] = None
    messages: Optional[List[Message]] = None
```

#### 6.1.3 设置相关模型

```python
# analytics_assistant/src/api/models/settings.py

from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class UserSettingsModel(BaseModel):
    """用户设置模型"""
    tableau_username: str
    language: Literal["zh", "en"] = "zh"
    analysis_depth: Literal["detailed", "comprehensive"] = "detailed"
    theme: Literal["light", "dark", "system"] = "light"
    default_datasource_id: Optional[str] = None
    show_thinking_process: bool = True
    created_at: datetime
    updated_at: datetime


class UpdateSettingsRequest(BaseModel):
    """更新设置请求"""
    language: Optional[Literal["zh", "en"]] = None
    analysis_depth: Optional[Literal["detailed", "comprehensive"]] = None
    theme: Optional[Literal["light", "dark", "system"]] = None
    default_datasource_id: Optional[str] = None
    show_thinking_process: Optional[bool] = None
```

#### 6.1.4 反馈相关模型

```python
# analytics_assistant/src/api/models/feedback.py

from typing import Optional, Literal
from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    """反馈请求模型"""
    message_id: str = Field(..., description="消息 ID")
    type: Literal["positive", "negative"] = Field(..., description="反馈类型")
    reason: Optional[str] = Field(None, description="反馈原因")
    comment: Optional[str] = Field(None, description="反馈评论")
```

#### 6.1.5 通用模型

```python
# analytics_assistant/src/api/models/common.py

from typing import Optional, Any, Dict
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """错误响应模型"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str
    database: str
```

### 6.2 认证与依赖注入

```python
# analytics_assistant/src/api/dependencies.py

from typing import Optional
from fastapi import Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_assistant.src.api.database.connection import get_db_session


async def get_tableau_username(
    x_tableau_username: Optional[str] = Header(None, alias="X-Tableau-Username")
) -> str:
    """获取 Tableau 用户名（依赖注入）
    
    Args:
        x_tableau_username: 请求头中的用户名
    
    Returns:
        Tableau 用户名
    
    Raises:
        HTTPException: 401 - 缺少用户身份
    """
    if not x_tableau_username:
        raise HTTPException(
            status_code=401,
            detail="缺少 X-Tableau-Username 请求头"
        )
    return x_tableau_username


async def get_db(
) -> AsyncSession:
    """获取数据库会话（依赖注入）
    
    Yields:
        数据库会话
    """
    async for session in get_db_session():
        yield session
```

### 6.3 路由实现

#### 6.3.1 聊天路由

```python
# analytics_assistant/src/api/routers/chat.py

import json
import logging
from typing import AsyncIterator
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from analytics_assistant.src.api.models.chat import ChatRequest
from analytics_assistant.src.api.dependencies import get_tableau_username
from analytics_assistant.src.orchestration.workflow.executor import WorkflowExecutor
from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
    get_history_manager,
)
from analytics_assistant.src.platform.tableau.adapter import TableauAdapter


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    tableau_username: str = Depends(get_tableau_username),
):
    """SSE 流式聊天端点
    
    Args:
        request: 聊天请求
        tableau_username: Tableau 用户名
    
    Returns:
        SSE 流式响应
    """
    logger.info(
        f"收到聊天请求: user={tableau_username}, "
        f"datasource={request.datasource_name}, "
        f"messages={len(request.messages)}"
    )
    
    try:
        # 1. 裁剪对话历史
        history_manager = get_history_manager()
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
        truncated_history = history_manager.truncate_history(history)
        
        logger.info(
            f"对话历史裁剪: {len(history)} → {len(truncated_history)} 条消息"
        )
        
        # 2. 创建工作流执行器（内部处理认证、数据源解析、数据模型加载）
        executor = WorkflowExecutor(tableau_username)
        
        # 3. 执行工作流并返回 SSE 流
        async def event_generator() -> AsyncIterator[str]:
            try:
                async for event in executor.execute_stream(
                    question=request.messages[-1].content,
                    datasource_name=request.datasource_name,
                    history=truncated_history,
                    language=request.language,
                    analysis_depth=request.analysis_depth,
                    session_id=request.session_id,
                ):
                    # 转换为 SSE 格式
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            
            except Exception as e:
                logger.exception(f"工作流执行失败: {e}")
                error_event = {
                    "type": "error",
                    "error": "工作流执行失败，请稍后重试"
                }
                yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
            }
        )
    
    except HTTPException:
        raise  # 重新抛出 HTTP 异常
    
    except Exception as e:
        logger.exception(f"聊天请求处理失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")
```



#### 6.3.2 会话管理路由

```python
# analytics_assistant/src/api/routers/sessions.py

import uuid
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_assistant.src.api.models.session import (
    CreateSessionRequest,
    CreateSessionResponse,
    SessionModel,
    GetSessionsResponse,
    UpdateSessionRequest,
)
from analytics_assistant.src.api.database.models import Session
from analytics_assistant.src.api.dependencies import get_tableau_username, get_db


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.post("", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    tableau_username: str = Depends(get_tableau_username),
    db: AsyncSession = Depends(get_db),
):
    """创建新会话
    
    Args:
        request: 创建会话请求
        tableau_username: Tableau 用户名
        db: 数据库会话
    
    Returns:
        创建的会话信息
    """
    session_id = str(uuid.uuid4())
    title = request.title or "新对话"
    
    session = Session(
        id=session_id,
        tableau_username=tableau_username,
        title=title,
        messages=[],
    )
    
    db.add(session)
    await db.commit()
    
    logger.info(f"创建会话: id={session_id}, user={tableau_username}")
    
    return CreateSessionResponse(
        session_id=session_id,
        created_at=session.created_at,
    )


@router.get("", response_model=GetSessionsResponse)
async def get_sessions(
    tableau_username: str = Depends(get_tableau_username),
    db: AsyncSession = Depends(get_db),
):
    """获取用户的所有会话
    
    Args:
        tableau_username: Tableau 用户名
        db: 数据库会话
    
    Returns:
        会话列表
    """
    stmt = (
        select(Session)
        .where(Session.tableau_username == tableau_username)
        .order_by(Session.updated_at.desc())
    )
    
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    
    return GetSessionsResponse(
        sessions=[SessionModel(**s.to_dict()) for s in sessions],
        total=len(sessions),
    )


@router.get("/{session_id}", response_model=SessionModel)
async def get_session(
    session_id: str,
    tableau_username: str = Depends(get_tableau_username),
    db: AsyncSession = Depends(get_db),
):
    """获取会话详情
    
    Args:
        session_id: 会话 ID
        tableau_username: Tableau 用户名
        db: 数据库会话
    
    Returns:
        会话详情
    
    Raises:
        HTTPException: 404 - 会话不存在
        HTTPException: 403 - 无权访问
    """
    stmt = select(Session).where(Session.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    if session.tableau_username != tableau_username:
        raise HTTPException(status_code=403, detail="无权访问此会话")
    
    return SessionModel(**session.to_dict())


@router.put("/{session_id}", response_model=SessionModel)
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    tableau_username: str = Depends(get_tableau_username),
    db: AsyncSession = Depends(get_db),
):
    """更新会话
    
    Args:
        session_id: 会话 ID
        request: 更新请求
        tableau_username: Tableau 用户名
        db: 数据库会话
    
    Returns:
        更新后的会话
    
    Raises:
        HTTPException: 404 - 会话不存在
        HTTPException: 403 - 无权访问
    """
    stmt = select(Session).where(Session.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    if session.tableau_username != tableau_username:
        raise HTTPException(status_code=403, detail="无权访问此会话")
    
    # 更新字段
    if request.title is not None:
        session.title = request.title
    
    if request.messages is not None:
        session.messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.messages
        ]
    
    await db.commit()
    await db.refresh(session)
    
    logger.info(f"更新会话: id={session_id}, user={tableau_username}")
    
    return SessionModel(**session.to_dict())


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    tableau_username: str = Depends(get_tableau_username),
    db: AsyncSession = Depends(get_db),
):
    """删除会话
    
    Args:
        session_id: 会话 ID
        tableau_username: Tableau 用户名
        db: 数据库会话
    
    Returns:
        成功消息
    
    Raises:
        HTTPException: 404 - 会话不存在
        HTTPException: 403 - 无权访问
    """
    stmt = select(Session).where(Session.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    if session.tableau_username != tableau_username:
        raise HTTPException(status_code=403, detail="无权访问此会话")
    
    await db.delete(session)
    await db.commit()
    
    logger.info(f"删除会话: id={session_id}, user={tableau_username}")
    
    return {"message": "会话已删除"}
```

#### 6.3.3 设置路由

```python
# analytics_assistant/src/api/routers/settings.py

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_assistant.src.api.models.settings import (
    UserSettingsModel,
    UpdateSettingsRequest,
)
from analytics_assistant.src.api.database.models import UserSettings
from analytics_assistant.src.api.dependencies import get_tableau_username, get_db


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=UserSettingsModel)
async def get_settings(
    tableau_username: str = Depends(get_tableau_username),
    db: AsyncSession = Depends(get_db),
):
    """获取用户设置
    
    如果用户首次访问，自动创建默认设置。
    
    Args:
        tableau_username: Tableau 用户名
        db: 数据库会话
    
    Returns:
        用户设置
    """
    stmt = select(UserSettings).where(
        UserSettings.tableau_username == tableau_username
    )
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()
    
    # 首次访问，创建默认设置
    if not settings:
        settings = UserSettings(tableau_username=tableau_username)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        logger.info(f"创建默认设置: user={tableau_username}")
    
    return UserSettingsModel(**settings.to_dict())


@router.put("", response_model=UserSettingsModel)
async def update_settings(
    request: UpdateSettingsRequest,
    tableau_username: str = Depends(get_tableau_username),
    db: AsyncSession = Depends(get_db),
):
    """更新用户设置
    
    Args:
        request: 更新请求
        tableau_username: Tableau 用户名
        db: 数据库会话
    
    Returns:
        更新后的设置
    """
    stmt = select(UserSettings).where(
        UserSettings.tableau_username == tableau_username
    )
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()
    
    # 如果不存在，创建新设置
    if not settings:
        settings = UserSettings(tableau_username=tableau_username)
        db.add(settings)
    
    # 更新字段
    if request.language is not None:
        settings.language = request.language
    
    if request.analysis_depth is not None:
        settings.analysis_depth = request.analysis_depth
    
    if request.theme is not None:
        settings.theme = request.theme
    
    if request.default_datasource_id is not None:
        settings.default_datasource_id = request.default_datasource_id
    
    if request.show_thinking_process is not None:
        settings.show_thinking_process = request.show_thinking_process
    
    await db.commit()
    await db.refresh(settings)
    
    logger.info(f"更新设置: user={tableau_username}")
    
    return UserSettingsModel(**settings.to_dict())
```

#### 6.3.4 反馈路由

```python
# analytics_assistant/src/api/routers/feedback.py

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_assistant.src.api.models.feedback import FeedbackRequest
from analytics_assistant.src.api.database.models import UserFeedback
from analytics_assistant.src.api.dependencies import get_tableau_username, get_db


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback(
    request: FeedbackRequest,
    tableau_username: str = Depends(get_tableau_username),
    db: AsyncSession = Depends(get_db),
):
    """提交用户反馈
    
    Args:
        request: 反馈请求
        tableau_username: Tableau 用户名
        db: 数据库会话
    
    Returns:
        成功消息
    """
    feedback = UserFeedback(
        tableau_username=tableau_username,
        message_id=request.message_id,
        type=request.type,
        reason=request.reason,
        comment=request.comment,
    )
    
    db.add(feedback)
    await db.commit()
    
    logger.info(
        f"收到反馈: user={tableau_username}, "
        f"message_id={request.message_id}, type={request.type}"
    )
    
    return {"message": "反馈已提交"}
```

#### 6.3.5 健康检查路由

```python
# analytics_assistant/src/api/routers/health.py

import logging
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_assistant.src.api.models.common import HealthResponse
from analytics_assistant.src.api.dependencies import get_db


logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: AsyncSession = Depends(get_db),
):
    """健康检查端点
    
    Args:
        db: 数据库会话
    
    Returns:
        健康状态
    """
    # 检查数据库连接
    try:
        await db.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        database_status = "error"
    
    return HealthResponse(
        status="ok" if database_status == "ok" else "degraded",
        version="1.0.0",
        database=database_status,
    )
```



### 6.4 FastAPI 应用入口

```python
# analytics_assistant/src/api/main.py

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analytics_assistant.src.api.database.connection import (
    init_database,
    close_database,
)
from analytics_assistant.src.api.routers import (
    chat,
    sessions,
    settings,
    feedback,
    health,
)
from analytics_assistant.src.infra.config import get_config


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理
    
    启动时：
    - 初始化数据库连接
    - 加载配置
    
    关闭时：
    - 关闭数据库连接
    """
    # 启动
    logger.info("启动 Analytics Assistant API...")
    
    # 初始化数据库
    init_database()
    logger.info("数据库初始化完成")
    
    yield
    
    # 关闭
    logger.info("关闭 Analytics Assistant API...")
    await close_database()
    logger.info("数据库连接已关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="Analytics Assistant API",
    description="Analytics Assistant 后端 API",
    version="1.0.0",
    lifespan=lifespan,
)


# 配置 CORS
def configure_cors():
    """配置 CORS"""
    config = get_config()
    api_config = config.get("api", {})
    cors_config = api_config.get("cors", {})
    
    allowed_origins = cors_config.get("allowed_origins", ["*"])
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    logger.info(f"CORS 配置完成: allowed_origins={allowed_origins}")


configure_cors()


# 注册路由
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(settings.router)
app.include_router(feedback.router)


# 根路径
@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Analytics Assistant API",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    
    # 从配置读取端口
    config = get_config()
    api_config = config.get("api", {})
    port = api_config.get("port", 8000)
    
    uvicorn.run(
        "analytics_assistant.src.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,  # 开发模式
    )
```



## 7. 配置管理设计

### 7.1 配置文件结构

在 `analytics_assistant/config/app.yaml` 中添加 API 层配置：

```yaml
# analytics_assistant/config/app.yaml

# ... 现有配置 ...

# API 层配置
api:
  # 服务器配置
  port: 8000
  host: "0.0.0.0"
  
  # 数据库配置
  database:
    # 开发环境使用 SQLite
    url: "sqlite+aiosqlite:///./analytics_assistant.db"
    
    # 生产环境使用 PostgreSQL（示例）
    # url: "postgresql+asyncpg://user:password@localhost/analytics_assistant"
    
    # 连接池配置
    pool_size: 10
    max_overflow: 20
    pool_pre_ping: true
  
  # CORS 配置
  cors:
    allowed_origins:
      - "http://localhost:3000"  # 前端开发服务器
      - "https://your-frontend-domain.com"  # 生产环境前端域名
  
  # 超时配置
  timeout:
    workflow_execution: 60  # 工作流执行超时（秒）
    sse_keepalive: 30  # SSE 保活间隔（秒）
  
  # 日志配置
  logging:
    level: "INFO"  # DEBUG | INFO | WARNING | ERROR
    format: "json"  # json | text
```

### 7.2 配置加载

配置加载由现有的 `infra/config` 模块处理，无需额外实现。

```python
from analytics_assistant.src.infra.config import get_config

config = get_config()
api_config = config.get("api", {})
port = api_config.get("port", 8000)
```



## 8. 错误处理与日志设计

### 8.1 统一错误处理中间件

```python
# analytics_assistant/src/api/middleware.py

import logging
import traceback
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


logger = logging.getLogger(__name__)


async def exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """统一异常处理器
    
    Args:
        request: 请求对象
        exc: 异常对象
    
    Returns:
        JSON 错误响应
    """
    # 记录完整错误堆栈
    logger.error(
        f"请求异常: {request.method} {request.url.path}\n"
        f"错误类型: {type(exc).__name__}\n"
        f"错误信息: {str(exc)}\n"
        f"堆栈:\n{traceback.format_exc()}"
    )
    
    # HTTP 异常
    if isinstance(exc, StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "code": f"HTTP_{exc.status_code}",
            }
        )
    
    # 请求验证错误
    if isinstance(exc, RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "请求参数验证失败",
                "detail": str(exc.errors()),
                "code": "VALIDATION_ERROR",
            }
        )
    
    # 业务异常（数据源未找到等）
    if isinstance(exc, DataSourceNotFoundError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": str(exc),
                "code": type(exc).__name__,
            }
        )
    
    # 未知异常
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "服务器内部错误",
            "code": "INTERNAL_SERVER_ERROR",
        }
    )


def register_exception_handlers(app):
    """注册异常处理器
    
    Args:
        app: FastAPI 应用
    """
    app.add_exception_handler(Exception, exception_handler)
```

### 8.2 请求日志中间件

```python
# analytics_assistant/src/api/middleware.py (续)

import time
from fastapi import Request


async def request_logging_middleware(request: Request, call_next):
    """请求日志中间件
    
    记录每个请求的：
    - 请求方法和路径
    - 用户身份
    - 请求参数
    - 响应状态码
    - 处理耗时
    
    Args:
        request: 请求对象
        call_next: 下一个中间件
    
    Returns:
        响应对象
    """
    start_time = time.time()
    
    # 提取用户身份
    tableau_username = request.headers.get("X-Tableau-Username", "anonymous")
    
    # 记录请求开始
    logger.info(
        f"请求开始: {request.method} {request.url.path} "
        f"user={tableau_username}"
    )
    
    # 处理请求
    response = await call_next(request)
    
    # 计算耗时
    duration = time.time() - start_time
    
    # 记录请求完成
    logger.info(
        f"请求完成: {request.method} {request.url.path} "
        f"user={tableau_username} "
        f"status={response.status_code} "
        f"duration={duration:.3f}s"
    )
    
    return response
```

### 8.3 结构化日志

```python
# analytics_assistant/src/api/utils/logging.py

import json
import logging
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """JSON 格式日志"""
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录
        
        Args:
            record: 日志记录
        
        Returns:
            JSON 格式的日志字符串
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # 添加额外字段
        if hasattr(record, "user"):
            log_data["user"] = record.user
        
        if hasattr(record, "duration"):
            log_data["duration"] = record.duration
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def configure_logging(level: str = "INFO", format_type: str = "json"):
    """配置日志
    
    Args:
        level: 日志级别
        format_type: 日志格式（json | text）
    """
    if format_type == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)
```



## 9. Correctness Properties

### 9.1 什么是 Correctness Properties

A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.

### 9.2 Properties

#### Property 1: SSE Response Content-Type
*For any* valid chat request to `/api/chat/stream`, the response Content-Type should be `text/event-stream`.
**Validates: Requirements 2.1**

#### Property 2: History Truncation Token Limit
*For any* conversation history, after truncation the resulting token count should be <= the configured `max_history_tokens` limit, and if the original history was already within the limit, all messages should be preserved unchanged.
**Validates: Requirements 3.2, 3.3**

#### Property 3: History Truncation Order Preservation
*For any* truncated conversation history, the relative order of retained messages should be the same as in the original history (newest message last), and the retained messages should be a contiguous suffix of the original.
**Validates: Requirements 3.4**

#### Property 4: History Truncation Configurable Limit
*For any* configured `max_history_tokens` value, truncation should respect that specific limit rather than a hardcoded default.
**Validates: Requirements 3.6**

#### Property 5: ProcessingStage Mapping Correctness
*For any* node name, `_get_processing_stage()` should return the correct ProcessingStage for LLM-calling and user-visible nodes (as defined in the mapping table), and return None for all other nodes.
**Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

#### Property 6: SSE Token and Thinking Event Emission
*For any* LLM-calling node execution, a `thinking` event with the corresponding ProcessingStage should be emitted, and for any token returned by LLM, a `token` event should be emitted with that token content.
**Validates: Requirements 2.4, 2.5**

#### Property 7: SSE Data Event Emission
*For any* query result, chart configuration, or suggestions list produced by the workflow, the corresponding SSE event (`data`, `chart`, or `suggestions`) should be emitted with the correct payload.
**Validates: Requirements 2.6, 2.7, 2.8**

#### Property 8: Workflow Terminal Event
*For any* workflow execution, exactly one terminal event should be emitted: `complete` on success, or `error` on failure, and it should be the last event in the stream.
**Validates: Requirements 2.9, 2.10**

#### Property 9: Session CRUD Round-Trip
*For any* session created via POST, the session should be retrievable via GET with all its data intact, updatable via PUT with changes reflected in subsequent GETs, and after DELETE it should no longer be retrievable (returning 404).
**Validates: Requirements 5.1, 5.3, 5.4, 5.5**

#### Property 10: Session List Ordering
*For any* user's session list returned by GET `/api/sessions`, sessions should be ordered by `updatedAt` in descending order (newest first).
**Validates: Requirements 5.2**

#### Property 11: User Data Isolation
*For any* two distinct users, API requests by user A should never return sessions, settings, or feedback belonging to user B.
**Validates: Requirements 5.6, 6.4**

#### Property 12: Authentication Requirement
*For any* API request (except `/health`) missing the `X-Tableau-Username` header, the response should be 401 Unauthorized.
**Validates: Requirements 5.7, 6.5, 7.5**

#### Property 13: Cross-User Access Prevention
*For any* attempt by user A to access (GET, PUT, DELETE) a session belonging to user B, the response should be 403 Forbidden.
**Validates: Requirements 5.8**

#### Property 14: Non-Existent Resource Returns 404
*For any* non-existent session ID or datasource name, the API should return 404 Not Found.
**Validates: Requirements 5.9, 9.2**

#### Property 15: Settings Round-Trip with Auto-Creation
*For any* authenticated user, GET `/api/settings` should always return valid settings (creating defaults on first access), and any subsequent PUT should persist changes that are reflected in the next GET.
**Validates: Requirements 6.1, 6.2, 6.3**

#### Property 16: Feedback Persistence with User Association
*For any* valid feedback submission, the feedback should be persisted in the database with the correct `tableau_username`, `message_id`, and `type` fields matching the request.
**Validates: Requirements 7.1, 7.4**

#### Property 17: Agent Execution Order
*For any* workflow execution, agents should be invoked in the order: semantic_parser → field_mapper → field_semantic, and no agent should be skipped.
**Validates: Requirements 8.2**

#### Property 18: Datasource Name Resolution
*For any* valid datasource name, the resolver should return a non-empty LUID string, and for any non-existent datasource name, it should raise DataSourceNotFoundError.
**Validates: Requirements 2.3, 9.1, 9.2**

#### Property 19: Error Message Safety
*For any* exception handled by the API, the returned error message should not contain sensitive internal details such as stack traces, database connection strings, API keys, or file paths.
**Validates: Requirements 10.2**



## 10. 测试策略

### 10.1 测试方法

本项目采用**双重测试策略**：

1. **单元测试**：验证具体示例、边界情况和错误条件
2. **属性测试**：验证跨所有输入的通用属性

两者互补，共同确保全面覆盖：
- 单元测试捕获具体的 bug
- 属性测试验证通用的正确性

### 10.2 属性测试配置

- **测试库**：使用 `hypothesis` 进行属性测试
- **最小迭代次数**：每个属性测试至少运行 100 次
- **标签格式**：每个测试必须引用设计文档中的属性
  - 格式：`# Feature: analytics-assistant-api-layer, Property {number}: {property_text}`

### 10.3 测试覆盖范围

#### 10.3.1 单元测试覆盖

**FastAPI 应用层**：
- 应用启动和关闭
- 路由注册
- CORS 配置
- 中间件配置

**数据库层**：
- ORM 模型序列化/反序列化
- 数据库连接管理
- 迁移脚本执行

**工作流编排层**：
- WorkflowExecutor 初始化
- 回调函数注入
- 事件队列管理
- 超时处理

**API 端点**：
- 请求验证（Pydantic 模型）
- 响应格式
- 错误处理
- 认证和授权

#### 10.3.2 属性测试覆盖

**对话历史裁剪**：
- Property 2: 裁剪后 token 数 <= 限制，低于限制时保留所有消息
- Property 3: 消息顺序保持不变
- Property 4: 可配置的 token 限制

**ProcessingStage 映射**：
- Property 5: 节点名称到 ProcessingStage 的映射正确性

**SSE 事件**：
- Property 1: 响应类型正确
- Property 6: LLM 节点的 thinking 和 token 事件
- Property 7: data/chart/suggestions 事件
- Property 8: 工作流终止事件（complete/error）

**会话管理**：
- Property 9: 会话 CRUD 往返一致性
- Property 10: 会话列表排序

**数据隔离与认证**：
- Property 11: 用户数据隔离
- Property 12: 认证要求
- Property 13: 跨用户访问阻止
- Property 14: 不存在的资源返回 404

**用户设置与反馈**：
- Property 15: 设置往返一致性（含自动创建）
- Property 16: 反馈持久化

**工作流执行**：
- Property 17: Agent 执行顺序正确
- Property 18: 数据源名称解析

**安全性**：
- Property 19: 错误消息安全性

### 10.4 集成测试

**端到端测试**：
- 完整的聊天流程（从请求到 SSE 流输出）
- 会话管理流程（创建、查询、更新、删除）
- 用户设置流程（首次访问、更新）
- 用户反馈流程（提交、保存）

**数据库集成测试**：
- 并发写入
- 事务回滚
- 连接池管理

**工作流集成测试**：
- 完整查询流程执行
- 错误恢复
- 超时处理

### 10.5 性能测试

**负载测试**：
- 并发 SSE 连接数：100+
- API 响应时间：< 200ms（非流式）
- SSE 首字节时间：< 500ms
- Token 延迟：< 50ms

**压力测试**：
- 数据库连接池耗尽
- 内存泄漏检测
- 长时间运行稳定性



## 11. 部署架构设计

### 11.1 开发环境

```
┌─────────────────────────────────────────┐
│         开发机器                         │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │  FastAPI 应用                       │ │
│  │  - Uvicorn (reload=True)           │ │
│  │  - Port: 8000                      │ │
│  └────────────────────────────────────┘ │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │  SQLite 数据库                      │ │
│  │  - analytics_assistant.db          │ │
│  └────────────────────────────────────┘ │
│                                          │
│  ┌────────────────────────────────────┐ │
│  │  前端开发服务器                     │ │
│  │  - Vite                            │ │
│  │  - Port: 3000                      │ │
│  └────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

**启动命令**：
```bash
# 后端
cd analytics_assistant
python -m analytics_assistant.src.api.main

# 前端
cd frontend
npm run dev
```

### 11.2 生产环境

```
┌─────────────────────────────────────────────────────────────┐
│                      负载均衡器 (Nginx)                       │
│                    - SSL 终止                                │
│                    - 反向代理                                │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌─────────────────┐            ┌─────────────────┐
│  FastAPI 实例 1  │            │  FastAPI 实例 2  │
│  - Uvicorn      │            │  - Uvicorn      │
│  - Workers: 4   │            │  - Workers: 4   │
└────────┬────────┘            └────────┬────────┘
         │                               │
         └───────────────┬───────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │  PostgreSQL 数据库   │
              │  - 主从复制          │
              │  - 连接池            │
              └─────────────────────┘
```

**部署配置**：

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://user:password@db:5432/analytics_assistant
      - LOG_LEVEL=INFO
    depends_on:
      - db
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '2'
          memory: 4G
  
  db:
    image: postgres:14
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=analytics_assistant
    volumes:
      - postgres_data:/var/lib/postgresql/data
  
  nginx:
    image: nginx:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - api

volumes:
  postgres_data:
```

### 11.3 Nginx 配置

```nginx
# nginx.conf
upstream api_backend {
    least_conn;
    server api:8000 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name api.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;
    
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    # SSE 配置
    location /api/chat/stream {
        proxy_pass http://api_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE 关键配置
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        chunked_transfer_encoding on;
    }
    
    # 其他 API 端点
    location /api/ {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 11.4 Dockerfile

```dockerfile
# Dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY analytics_assistant/ ./analytics_assistant/

# 创建数据库目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "analytics_assistant.src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

### 11.5 环境变量配置

```bash
# .env.production
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/analytics_assistant
LOG_LEVEL=INFO
LOG_FORMAT=json
CORS_ALLOWED_ORIGINS=https://frontend.example.com
WORKFLOW_TIMEOUT=60
SSE_KEEPALIVE=30
```



## 12. 安全性设计

### 12.1 认证机制

**Tableau 用户身份校验**：
- 所有 API 端点（除 `/health`）必须包含 `X-Tableau-Username` 请求头
- 缺少请求头返回 401 Unauthorized
- 生产环境应通过反向代理（Nginx）验证 Tableau 会话

**实现示例**：
```python
# analytics_assistant/src/api/dependencies.py

async def get_tableau_username(
    x_tableau_username: Optional[str] = Header(None, alias="X-Tableau-Username")
) -> str:
    """获取并验证 Tableau 用户名"""
    if not x_tableau_username:
        raise HTTPException(
            status_code=401,
            detail="缺少 X-Tableau-Username 请求头"
        )
    
    # 生产环境：验证 Tableau 会话
    # if not await verify_tableau_session(x_tableau_username):
    #     raise HTTPException(status_code=401, detail="无效的 Tableau 会话")
    
    return x_tableau_username
```

### 12.2 授权机制

**数据隔离**：
- 所有数据库查询必须过滤 `tableau_username`
- 用户只能访问自己的数据（会话、设置、反馈）
- 跨用户访问返回 403 Forbidden

**实现示例**：
```python
# 会话查询示例
stmt = (
    select(Session)
    .where(Session.tableau_username == tableau_username)  # 强制过滤
    .order_by(Session.updated_at.desc())
)
```

### 12.3 SQL 注入防护

**使用参数化查询**：
- 所有数据库查询使用 SQLAlchemy ORM
- 禁止拼接 SQL 字符串
- 使用 Pydantic 模型验证输入

### 12.4 XSS 防护

**输入验证**：
- 使用 Pydantic 模型验证所有输入
- 限制字符串长度（标题 500 字符，评论 5000 字符）
- 前端负责转义输出

### 12.5 CORS 配置

**限制跨域访问**：
```python
# 只允许前端域名跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # 开发环境
        "https://frontend.example.com",  # 生产环境
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)
```

### 12.6 日志脱敏

**敏感信息脱敏**：
```python
# 日志中不记录敏感信息
logger.info(
    f"用户登录: user={tableau_username}, "
    f"ip={request.client.host}"
    # 不记录：密码、API Key、Token
)
```

### 12.7 速率限制

**防止滥用**：
```python
# 使用 slowapi 限制请求频率
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/api/chat/stream")
@limiter.limit("10/minute")  # 每分钟最多 10 次请求
async def chat_stream(...):
    ...
```



## 13. 监控与可观测性

### 13.1 健康检查

**端点**：`GET /health`

**检查项**：
- 应用状态
- 数据库连接
- 版本信息

**响应示例**：
```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "ok"
}
```

### 13.2 指标收集

**关键指标**：
- API 请求数（按端点、状态码）
- API 响应时间（P50、P95、P99）
- SSE 连接数（当前活跃）
- 工作流执行时间（按 Agent）
- 数据库查询时间
- 错误率

**实现方案**：
```python
# 使用 prometheus_client
from prometheus_client import Counter, Histogram, Gauge

# 请求计数器
request_counter = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

# 响应时间直方图
response_time = Histogram(
    'api_response_time_seconds',
    'API response time',
    ['method', 'endpoint']
)

# SSE 连接数
sse_connections = Gauge(
    'sse_connections_active',
    'Active SSE connections'
)
```

### 13.3 分布式追踪

**使用 OpenTelemetry**：
```python
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# 初始化追踪
tracer = trace.get_tracer(__name__)

# 自动追踪 FastAPI
FastAPIInstrumentor.instrument_app(app)

# 手动追踪工作流
async def execute_workflow(...):
    with tracer.start_as_current_span("workflow_execution") as span:
        span.set_attribute("user", tableau_username)
        span.set_attribute("datasource", datasource_luid)
        # 执行工作流
        ...
```

### 13.4 日志聚合

**结构化日志**：
```python
# 使用 JSON 格式日志
logger.info(
    "workflow_completed",
    extra={
        "user": tableau_username,
        "datasource": datasource_luid,
        "duration": duration,
        "agents": ["semantic_parser", "field_mapper", "field_semantic"],
    }
)
```

**日志收集**：
- 开发环境：输出到控制台
- 生产环境：输出到文件 + 日志聚合系统（ELK、Loki）

### 13.5 告警规则

**关键告警**：
- API 错误率 > 5%
- API P95 响应时间 > 1s
- 数据库连接池耗尽
- SSE 连接数 > 1000
- 磁盘使用率 > 80%



## 14. 性能优化

### 14.1 数据库优化

**连接池配置**：
```python
# 生产环境连接池配置
engine = create_async_engine(
    database_url,
    pool_size=10,  # 基础连接数
    max_overflow=20,  # 最大溢出连接数
    pool_pre_ping=True,  # 连接健康检查
    pool_recycle=3600,  # 连接回收时间（秒）
)
```

**索引优化**：
```python
# 会话表索引
Index("idx_tableau_username_updated_at", "tableau_username", "updated_at")

# 反馈表索引
Index("idx_tableau_username", "tableau_username")
Index("idx_message_id", "message_id")
```

**查询优化**：
- 使用 `select()` 而非 `query()`（SQLAlchemy 2.0 风格）
- 避免 N+1 查询（使用 `joinedload`）
- 限制返回字段（使用 `load_only`）

### 14.2 SSE 流式优化

**缓冲控制**：
```python
# 禁用响应缓冲
return StreamingResponse(
    event_generator(),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
    }
)
```

**心跳保活**：
```python
# 定期发送心跳，防止连接超时
async def event_generator():
    last_heartbeat = time.time()
    
    async for event in workflow_events:
        yield format_sse_event(event)
        
        # 每 30 秒发送心跳
        if time.time() - last_heartbeat > 30:
            yield ": heartbeat\n\n"
            last_heartbeat = time.time()
```

### 14.3 异步优化

**并发执行**：
```python
# 并发执行多个独立任务
results = await asyncio.gather(
    resolve_datasource_luid(datasource_name),
    get_user_settings(tableau_username),
    get_recent_sessions(tableau_username),
)
```

**异步上下文管理**：
```python
# 使用异步上下文管理器
async with AsyncSession() as session:
    async with session.begin():
        # 数据库操作
        ...
```

### 14.4 缓存策略

**用户设置缓存**：
```python
# 使用 LRU 缓存
from functools import lru_cache

@lru_cache(maxsize=1000)
async def get_user_settings_cached(tableau_username: str):
    # 缓存用户设置，减少数据库查询
    ...
```

**数据源 LUID 缓存**：
```python
# 缓存数据源名称 → LUID 映射
datasource_cache = {}

async def resolve_datasource_luid(datasource_name: str):
    if datasource_name in datasource_cache:
        return datasource_cache[datasource_name]
    
    luid = await platform_adapter.get_datasource_luid(datasource_name)
    datasource_cache[datasource_name] = luid
    return luid
```

### 14.5 资源限制

**请求大小限制**：
```python
# 限制请求体大小
app.add_middleware(
    RequestSizeLimitMiddleware,
    max_size=10 * 1024 * 1024  # 10MB
)
```

**超时控制**：
```python
# 工作流执行超时
async def execute_workflow_with_timeout(...):
    try:
        return await asyncio.wait_for(
            execute_workflow(...),
            timeout=60  # 60 秒超时
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="工作流执行超时")
```



## 15. 技术风险与缓解措施

### 15.1 风险矩阵

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| SSE 连接不稳定 | 高 | 中 | 实现自动重连、心跳检测、连接状态监控 |
| 工作流执行超时 | 中 | 中 | 设置合理超时、提供取消机制、优化 Agent 性能 |
| 数据库连接池耗尽 | 高 | 低 | 配置连接池大小、监控连接数、实现连接回收 |
| 用户身份伪造 | 高 | 中 | 生产环境使用反向代理验证、记录访问日志、定期审计 |
| LangGraph 状态管理复杂 | 中 | 中 | 使用 checkpointer 持久化状态、完善错误恢复、充分测试 |
| 多轮对话上下文丢失 | 中 | 低 | 前端裁剪逻辑、后端验证消息数量、记录裁剪日志 |
| SSE 事件顺序错乱 | 中 | 低 | 使用单一事件队列、确保串行发送、添加事件序号 |
| 数据库迁移失败 | 高 | 低 | 使用迁移工具（Alembic）、备份数据、测试回滚 |

### 15.2 详细缓解措施

#### 15.2.1 SSE 连接稳定性

**问题**：网络不稳定导致 SSE 连接断开

**缓解措施**：
1. **心跳机制**：每 30 秒发送心跳，保持连接活跃
2. **自动重连**：前端检测断开后自动重连
3. **连接监控**：记录连接时长、断开原因
4. **优雅降级**：连接失败时提示用户刷新

```python
# 心跳实现
async def event_generator():
    last_heartbeat = time.time()
    
    try:
        async for event in workflow_events:
            yield format_sse_event(event)
            
            # 心跳
            if time.time() - last_heartbeat > 30:
                yield ": heartbeat\n\n"
                last_heartbeat = time.time()
    
    except asyncio.CancelledError:
        logger.info("SSE 连接被取消")
        yield format_sse_event({"type": "error", "error": "连接已断开"})
```

#### 15.2.2 工作流超时处理

**问题**：工作流执行时间过长导致超时

**缓解措施**：
1. **合理超时**：设置 60 秒超时（可配置）
2. **取消机制**：支持客户端主动取消
3. **性能优化**：优化 Agent 执行速度
4. **进度反馈**：实时反馈执行进度

```python
# 超时处理
async def execute_workflow_with_timeout(...):
    try:
        return await asyncio.wait_for(
            execute_workflow(...),
            timeout=config.get("api", {}).get("timeout", {}).get("workflow_execution", 60)
        )
    except asyncio.TimeoutError:
        logger.error(f"工作流执行超时: user={tableau_username}")
        raise HTTPException(status_code=504, detail="工作流执行超时，请稍后重试")
```

#### 15.2.3 数据库连接池管理

**问题**：高并发时连接池耗尽

**缓解措施**：
1. **连接池配置**：pool_size=10, max_overflow=20
2. **连接监控**：监控连接池使用率
3. **连接回收**：pool_recycle=3600（1 小时）
4. **健康检查**：pool_pre_ping=True

```python
# 连接池监控
from prometheus_client import Gauge

db_pool_size = Gauge('db_pool_size', 'Database connection pool size')
db_pool_overflow = Gauge('db_pool_overflow', 'Database connection pool overflow')

# 定期更新指标
async def update_db_metrics():
    while True:
        db_pool_size.set(_engine.pool.size())
        db_pool_overflow.set(_engine.pool.overflow())
        await asyncio.sleep(10)
```

#### 15.2.4 用户身份验证

**问题**：用户身份可能被伪造

**缓解措施**：
1. **反向代理验证**：生产环境通过 Nginx 验证 Tableau 会话
2. **访问日志**：记录所有 API 访问
3. **定期审计**：定期审计异常访问
4. **IP 白名单**：限制 API 访问来源

```nginx
# Nginx 配置示例
location /api/ {
    # 验证 Tableau 会话
    auth_request /auth/verify;
    
    # 传递用户名
    proxy_set_header X-Tableau-Username $tableau_username;
    
    proxy_pass http://api_backend;
}

location = /auth/verify {
    internal;
    proxy_pass http://tableau_server/verify_session;
}
```



## 16. 开发指南

### 16.1 本地开发环境搭建

**前置条件**：
- Python 3.10+
- SQLite 3.35+
- Git

**步骤**：

1. **克隆代码**：
```bash
git clone <repository_url>
cd analytics_assistant
```

2. **安装依赖**：
```bash
pip install -r requirements.txt
```

3. **初始化数据库**：
```bash
python -m analytics_assistant.src.api.database.migrations.init_db
```

4. **启动应用**：
```bash
python -m analytics_assistant.src.api.main
```

5. **访问文档**：
```
http://localhost:8000/docs
```

### 16.2 代码规范

**必须遵循 `coding-standards.md`**：

1. **导入规范**：
   - 禁止延迟导入（函数内导入）
   - 包内使用相对导入，跨包使用绝对导入

2. **配置管理**：
   - 所有可配置参数放入 `app.yaml`
   - 禁止硬编码阈值、超时等参数

3. **Prompt 和 Schema**：
   - Prompt 文件放在 `prompts/` 目录
   - Schema 文件放在 `schemas/` 目录

4. **错误处理**：
   - 使用统一的异常处理中间件
   - 不暴露内部错误细节

5. **日志规范**：
   - 使用结构化日志（JSON 格式）
   - 不记录敏感信息

### 16.3 测试运行

**单元测试**：
```bash
pytest tests/unit/
```

**属性测试**：
```bash
pytest tests/property/ --hypothesis-profile=dev
```

**集成测试**：
```bash
pytest tests/integration/
```

**覆盖率报告**：
```bash
pytest --cov=analytics_assistant.src.api --cov-report=html
```

### 16.4 调试技巧

**启用 DEBUG 日志**：
```yaml
# config/app.yaml
api:
  logging:
    level: "DEBUG"
```

**使用 FastAPI 自动重载**：
```bash
uvicorn analytics_assistant.src.api.main:app --reload
```

**调试 SSE 流**：
```bash
# 使用 curl 测试 SSE
curl -N -H "X-Tableau-Username: test_user" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"测试"}],"datasource_name":"test"}' \
  http://localhost:8000/api/chat/stream
```

**数据库调试**：
```python
# 启用 SQL 日志
engine = create_async_engine(
    database_url,
    echo=True,  # 打印所有 SQL 语句
)
```

### 16.5 常见问题

**Q: 数据库连接失败**
```
A: 检查数据库 URL 配置，确保数据库文件路径正确
```

**Q: SSE 连接立即断开**
```
A: 检查 Nginx 配置，确保禁用了缓冲（proxy_buffering off）
```

**Q: 工作流执行超时**
```
A: 增加超时配置（api.timeout.workflow_execution）或优化 Agent 性能
```

**Q: 导入循环依赖**
```
A: 检查导入顺序，避免在函数内导入，重构代码结构
```



## 17. 未来扩展

### 17.1 短期扩展（1-3 个月）

**WebSocket 支持**：
- 替代 SSE，支持双向通信
- 支持用户主动取消工作流
- 支持实时协作

**Redis 缓存**：
- 缓存用户设置
- 缓存数据源 LUID 映射
- 缓存 RAG 检索结果

**批量操作 API**：
- 批量创建会话
- 批量删除会话
- 批量导出数据

### 17.2 中期扩展（3-6 个月）

**多租户支持**：
- 支持多个 Tableau 站点
- 租户级别的数据隔离
- 租户级别的配置管理

**高级认证**：
- OAuth 2.0 集成
- JWT Token 认证
- API Key 认证

**数据分析**：
- 用户行为分析
- 查询模式分析
- 性能分析

### 17.3 长期扩展（6-12 个月）

**微服务拆分**：
- 工作流服务
- 会话服务
- 用户服务
- 通知服务

**消息队列**：
- 异步工作流执行
- 任务队列管理
- 事件驱动架构

**多语言支持**：
- 国际化（i18n）
- 多语言 UI
- 多语言文档



## 18. 总结

### 18.1 设计亮点

1. **全异步架构**：所有 I/O 操作使用 async/await，支持高并发
2. **流式输出**：通过 SSE 实现实时流式输出，提升用户体验
3. **工作流编排**：统一的 WorkflowExecutor 管理完整的查询执行流程
4. **数据隔离**：基于 Tableau 用户身份的严格数据隔离
5. **配置驱动**：所有可配置参数从 `app.yaml` 读取，易于调整
6. **可观测性**：完善的日志、指标、追踪体系
7. **安全性**：认证、授权、SQL 注入防护、XSS 防护
8. **可扩展性**：无状态设计，支持水平扩展

### 18.2 关键技术决策

| 决策 | 理由 |
|------|------|
| FastAPI | 高性能、异步支持、自动文档生成 |
| SQLAlchemy 2.0 | 异步 ORM、类型安全、成熟稳定 |
| SQLite（开发）/ PostgreSQL（生产） | 开发简单、生产可靠 |
| SSE（而非 WebSocket） | 单向通信足够、实现简单、兼容性好 |
| LangGraph | 已有 Agent 基于 LangGraph，保持一致性 |
| Pydantic | 数据验证、类型安全、与 FastAPI 集成 |

### 18.3 实施优先级

**P0（核心功能）**：
- FastAPI 应用入口
- SSE 流式输出端点
- 工作流编排层
- 会话管理 API
- 用户设置 API
- 数据库设计和迁移

**P1（重要功能）**：
- 用户反馈 API
- 错误处理和日志
- 健康检查
- 单元测试和属性测试

**P2（优化功能）**：
- 性能优化
- 监控和告警
- 部署配置
- 文档完善

### 18.4 成功标准

1. **功能完整性**：所有需求的验收标准通过
2. **性能达标**：API 响应时间 < 200ms，SSE 首字节 < 500ms
3. **测试覆盖**：单元测试覆盖率 > 80%，所有属性测试通过
4. **安全性**：通过安全审计，无高危漏洞
5. **可维护性**：代码遵循规范，文档完善
6. **可扩展性**：支持 100+ 并发连接

---

**文档版本**: v1.0  
**创建日期**: 2026-02-06  
**最后更新**: 2026-02-06  
**审核状态**: 待审核  
**作者**: Kiro AI Assistant

