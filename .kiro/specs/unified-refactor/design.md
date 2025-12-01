# 设计文档：Tableau Assistant 统一重构

## 概述

本设计文档描述了 Tableau Assistant 统一重构的技术方案，整合 DeepAgents 框架迁移和 VizQL Data Service API 升级。

### 设计原则

1. **渐进式迁移**：保持现有业务逻辑，只改变调用方式
2. **类型安全**：全面使用 Pydantic v2 模型
3. **可测试性**：每个组件都可独立测试
4. **生产级别**：完善的错误处理、日志记录和监控

### 核心架构决策

#### 决策 1：混合架构

**使用 DeepAgents 基础功能 + StateGraph 流程控制**

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI 入口层                            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 DeepAgent (主 Agent)                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              内置 Middleware (7个)                    │   │
│  │  - TodoListMiddleware (任务管理)                     │   │
│  │  - FilesystemMiddleware (大文件处理)                 │   │
│  │  - SummarizationMiddleware (对话总结)                │   │
│  │  - AnthropicPromptCachingMiddleware (Claude缓存)     │   │
│  │  - PatchToolCallsMiddleware (参数修复)               │   │
│  │  - SubAgentMiddleware (禁用)                         │   │
│  │  - HumanInTheLoopMiddleware (人工介入)               │   │
│  └─────────────────────────────────────────────────────┘   │
│                              │                              │
│                              ▼                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  7 个 LangChain 工具                  │   │
│  │  - get_metadata                                      │   │
│  │  - parse_date                                        │   │
│  │  - build_vizql_query                                 │   │
│  │  - execute_vizql_query                               │   │
│  │  - semantic_map_fields                               │   │
│  │  - process_query_result                              │   │
│  │  - detect_statistics                                 │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              StateGraph 工作流 (固定流程)                    │
│                                                             │
│   START ──▶ [Boost?] ──▶ Understanding ──▶ Planning        │
│                │                              │              │
│                ▼                              ▼              │
│           (跳过)                          Execute           │
│                                               │              │
│                                               ▼              │
│                                           Insight           │
│                                               │              │
│                                               ▼              │
│                                          Replanner          │
│                                               │              │
│                              ┌────────────────┴──────┐      │
│                              ▼                       ▼      │
│                          Planning                 END       │
│                        (重规划回到规划)                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 VizQL Data Service API                       │
│  - /api/v1/vizql-data-service/query-datasource              │
│  - /api/v1/vizql-data-service/read-metadata                 │
│  - 支持表计算 (TableCalcField)                               │
└─────────────────────────────────────────────────────────────┘
```

**理由**：
- DeepAgents 提供内置中间件，减少自定义代码
- StateGraph 保持固定流程，满足业务需求
- 不使用 SubAgentMiddleware 的子代理功能，因为需要确定性流程

#### 决策 2：工具驱动架构

**所有业务逻辑通过工具暴露给 Agent**

```python
# 工具调用流程
DeepAgent
    │
    ├── 调用 get_metadata 工具
    │       └── MetadataManager.get_metadata()
    │
    ├── 调用 semantic_map_fields 工具
    │       └── SemanticMapper.map_fields()
    │
    ├── 调用 build_vizql_query 工具
    │       └── QueryBuilder.build_query()
    │
    └── 调用 execute_vizql_query 工具
            └── QueryExecutor.execute()
```

**理由**：
- 工具是 DeepAgents 的核心交互方式
- 保持现有组件逻辑，只封装接口
- 便于测试和维护

## 组件设计

### 1. DeepAgent 创建器

```python
# tableau_assistant/src/agents/deep_agent_factory.py

from deepagents import create_deep_agent
from langgraph.store.base import BaseStore
from typing import List, Optional, Dict, Any
from langchain_core.tools import BaseTool

def create_tableau_deep_agent(
    tools: List[BaseTool],
    model_name: str = "claude-sonnet-4-20250514",
    store: Optional[BaseStore] = None,
    system_prompt: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None
) -> "CompiledStateGraph":
    """
    创建 Tableau Assistant 的 DeepAgent
    
    Args:
        tools: 7 个 VizQL 工具列表
        model_name: LLM 模型名称
        store: 持久化存储实例
        system_prompt: 系统提示词
        config: 额外配置
            - summarization_threshold: 触发总结的对话轮数 (默认 10)
            - filesystem_size_threshold: 触发文件写入的大小阈值 (默认 10MB)
    
    Returns:
        编译后的 DeepAgent 图
    
    注意:
        - 传递空的 subagents=[] 以禁用 SubAgentMiddleware 的子代理功能
        - 内置中间件会自动启用
    """
    config = config or {}
    
    # 创建 DeepAgent
    # 关键：subagents=[] 禁用子代理功能，但保留其他内置中间件
    agent = create_deep_agent(
        model=model_name,
        tools=tools,
        subagents=[],  # 禁用子代理功能
        store=store,
        system_prompt=system_prompt,
        # 内置中间件配置通过环境变量或默认值
    )
    
    return agent
```

### 2. 工具层设计

#### 2.1 工具注册表

```python
# tableau_assistant/src/tools/__init__.py

from typing import List
from langchain_core.tools import BaseTool

from .get_metadata import get_metadata_tool
from .parse_date import parse_date_tool
from .build_vizql_query import build_vizql_query_tool
from .execute_vizql_query import execute_vizql_query_tool
from .semantic_map_fields import semantic_map_fields_tool
from .process_query_result import process_query_result_tool
from .detect_statistics import detect_statistics_tool

def create_vizql_tools() -> List[BaseTool]:
    """
    创建所有 VizQL 工具
    
    Returns:
        7 个工具的列表
    """
    return [
        get_metadata_tool,
        parse_date_tool,
        build_vizql_query_tool,
        execute_vizql_query_tool,
        semantic_map_fields_tool,
        process_query_result_tool,
        detect_statistics_tool,
    ]
```

#### 2.2 工具依赖注入设计

为了支持依赖注入和测试，工具层使用工厂模式创建工具实例：

```python
# tableau_assistant/src/tools/factory.py

from typing import Optional
from langchain_core.tools import BaseTool

from tableau_assistant.src.capabilities.metadata.manager import MetadataManager
from tableau_assistant.src.capabilities.query.executor import QueryExecutor
from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient

class ToolDependencies:
    """工具依赖容器"""
    
    def __init__(
        self,
        metadata_manager: Optional[MetadataManager] = None,
        query_executor: Optional[QueryExecutor] = None,
        vizql_client: Optional[VizQLClient] = None,
    ):
        self.metadata_manager = metadata_manager or MetadataManager()
        self.query_executor = query_executor or QueryExecutor()
        self.vizql_client = vizql_client or VizQLClient()


def create_tools_with_dependencies(deps: ToolDependencies) -> list[BaseTool]:
    """
    使用依赖注入创建工具列表
    
    Args:
        deps: 工具依赖容器
    
    Returns:
        配置好依赖的工具列表
    """
    from .get_metadata import create_get_metadata_tool
    from .execute_vizql_query import create_execute_vizql_query_tool
    # ... 其他工具
    
    return [
        create_get_metadata_tool(deps.metadata_manager),
        create_execute_vizql_query_tool(deps.query_executor, deps.vizql_client),
        # ... 其他工具
    ]
```

#### 2.3 工具实现示例

```python
# tableau_assistant/src/tools/get_metadata.py

from langchain_core.tools import tool, StructuredTool
from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, Optional

from tableau_assistant.src.capabilities.metadata.manager import MetadataManager

class GetMetadataInput(BaseModel):
    """get_metadata 工具的输入参数"""
    model_config = ConfigDict(extra="forbid")
    
    datasource_luid: str = Field(
        description="数据源 LUID"
    )
    use_cache: bool = Field(
        default=True,
        description="是否使用缓存"
    )
    enhance: bool = Field(
        default=True,
        description="是否增强元数据（获取日期字段最大值等）"
    )

class GetMetadataOutput(BaseModel):
    """get_metadata 工具的输出"""
    model_config = ConfigDict(extra="forbid")
    
    fields: list = Field(description="字段列表")
    field_count: int = Field(description="字段数量")
    date_fields: list = Field(description="日期字段列表")
    valid_max_date: Optional[str] = Field(default=None, description="有效最大日期")


def create_get_metadata_tool(manager: MetadataManager) -> StructuredTool:
    """
    创建 get_metadata 工具（支持依赖注入）
    
    Args:
        manager: MetadataManager 实例
    
    Returns:
        配置好的 StructuredTool
    """
    def _get_metadata(
        datasource_luid: str,
        use_cache: bool = True,
        enhance: bool = True
    ) -> Dict[str, Any]:
        """
        获取数据源元数据
        
        从 Tableau 数据源获取字段信息，包括字段名称、数据类型、角色等。
        支持缓存以提高性能，支持增强模式获取日期字段最大值。
        
        Args:
            datasource_luid: 数据源的 LUID 标识符
            use_cache: 是否使用缓存（默认 True）
            enhance: 是否增强元数据（默认 True）
        
        Returns:
            包含字段信息的字典：
            - fields: 字段列表
            - field_count: 字段数量
            - date_fields: 日期字段列表
            - valid_max_date: 有效最大日期（如果 enhance=True）
        
        Example:
            >>> result = get_metadata_tool("abc123-def456")
            >>> print(result["field_count"])
            15
        """
        metadata = manager.get_metadata(
            datasource_luid=datasource_luid,
            use_cache=use_cache,
            enhance=enhance
        )
        
        return GetMetadataOutput(
            fields=metadata.fields,
            field_count=len(metadata.fields),
            date_fields=[f for f in metadata.fields if f.dataType == "DATE"],
            valid_max_date=metadata.valid_max_date
        ).model_dump()
    
    return StructuredTool.from_function(
        func=_get_metadata,
        name="get_metadata",
        description="获取数据源元数据，包括字段信息、数据类型等",
        args_schema=GetMetadataInput
    )
```

### 3. StateGraph 工作流设计

```python
# tableau_assistant/src/agents/workflows/vizql_workflow.py

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from typing import Dict, Any, Optional

from tableau_assistant.src.models.state import VizQLState, VizQLInput, VizQLOutput
from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.capabilities.storage.persistent_store import PersistentStore

def create_vizql_workflow(
    deep_agent,  # DeepAgent 实例
    store: Optional[PersistentStore] = None
):
    """
    创建 VizQL 主工作流
    
    工作流程：
    1. (可选) Boost - 问题优化
    2. Understanding - 理解用户意图
    3. Planning - 生成查询计划（支持表计算）
    4. Execute - 执行查询
    5. Insight - 分析结果
    6. Replanner - 决定是否重规划
    
    Args:
        deep_agent: DeepAgent 实例（用于调用工具）
        store: 持久化存储实例
    
    Returns:
        编译后的工作流应用
    """
    graph = StateGraph(
        state_schema=VizQLState,
        context_schema=VizQLContext,
        input_schema=VizQLInput,
        output_schema=VizQLOutput
    )
    
    # ========== 节点定义 ==========
    
    def boost_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """问题优化节点"""
        from tableau_assistant.src.agents.nodes.question_boost import question_boost_agent_node
        # 通过 DeepAgent 调用工具
        return question_boost_agent_node(state, deep_agent, config)
    
    def understanding_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """问题理解节点"""
        from tableau_assistant.src.agents.nodes.understanding import understanding_agent_node
        return understanding_agent_node(state, deep_agent, config)
    
    def planning_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """查询规划节点（支持表计算）"""
        from tableau_assistant.src.agents.nodes.task_planner import query_planner_agent_node
        return query_planner_agent_node(state, deep_agent, config)
    
    def execute_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """
        查询执行节点（纯执行节点，非 Agent）
        
        确定性执行，不使用 LLM：
        1. 遍历 query_plan.subtasks
        2. 对每个 QuerySubTask 调用 QueryBuilder + VizQLClient
        3. 收集结果到 subtask_results
        """
        from tableau_assistant.src.agents.nodes.execute import execute_query_node
        return execute_query_node(state, config)  # 不需要 deep_agent
    
    def insight_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """洞察生成节点"""
        from tableau_assistant.src.agents.nodes.insight import insight_agent_node
        return insight_agent_node(state, deep_agent, config)
    
    def replanner_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """重规划节点"""
        from tableau_assistant.src.agents.nodes.replanner import replanner_agent_node
        return replanner_agent_node(state, deep_agent, config)
    
    # ========== 添加节点 ==========
    graph.add_node("boost", boost_node)
    graph.add_node("understanding", understanding_node)
    graph.add_node("planning", planning_node)
    graph.add_node("execute", execute_node)
    graph.add_node("insight", insight_node)
    graph.add_node("replanner", replanner_node)
    
    # ========== 路由逻辑 ==========
    
    def should_boost(state: VizQLState) -> str:
        """决定是否执行 Boost"""
        return "boost" if state.get("boost_question", False) else "understanding"
    
    def should_replan(state: VizQLState) -> str:
        """
        决定是否重规划
        
        重规划类型：
        1. 补充缺失信息 - 原问题部分未回答，生成补充问题
        2. 深入分析异常 - 发现异常需要深入分析
        3. 洞察不足 - 分析过于表面，需要更深入
        
        路由策略：
        - 所有重规划问题都路由到 Planning 节点
        - 因为 Understanding 已经完成了原问题的理解
        - 新问题基于已有的元数据和字段映射
        """
        replan_decision = state.get("replan_decision", {})
        replan_count = state.get("replan_count", 0)
        max_rounds = state.get("max_replan_rounds", 3)
        completeness_score = state.get("completeness_score", 0.0)
        
        # 智能终止策略
        # 1. 完成度足够高，无需继续重规划
        if completeness_score >= 0.9:
            return END
        
        # 2. 达到硬限制
        if replan_count >= max_rounds:
            return END  # 记录终止原因到 replan_history
        
        # 3. Replanner 决定需要重规划且完成度不足
        if replan_decision.get("should_replan") and completeness_score < 0.7:
            return "planning"
        
        # 4. 完成度在 0.7-0.9 之间，由 Replanner 决定
        if replan_decision.get("should_replan"):
            return "planning"
        
        return END
    
    # ========== 添加边 ==========
    graph.add_conditional_edges(START, should_boost, {
        "boost": "boost",
        "understanding": "understanding"
    })
    
    graph.add_edge("boost", "understanding")
    graph.add_edge("understanding", "planning")
    graph.add_edge("planning", "execute")
    graph.add_edge("execute", "insight")
    graph.add_edge("insight", "replanner")
    
    graph.add_conditional_edges("replanner", should_replan, {
        "planning": "planning",  # 重规划直接回到 Planning
        END: END
    })
    
    # ========== 编译 ==========
    return graph.compile(
        checkpointer=InMemorySaver(),
        store=store
    )
```

### 4. VizQL 客户端设计

```python
# tableau_assistant/src/bi_platforms/tableau/vizql_client.py

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Union
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from tableau_assistant.src.models.vizql_types import VizQLQuery, QueryOutput
from tableau_assistant.src.config.settings import settings

class VizQLClientConfig(BaseModel):
    """VizQL 客户端配置"""
    base_url: str = Field(description="Tableau 服务器 URL")
    verify_ssl: bool = Field(default=True, description="是否验证 SSL")
    ca_bundle: Optional[str] = Field(default=None, description="自定义 CA 证书路径")
    timeout: int = Field(default=30, description="请求超时时间（秒）")
    max_retries: int = Field(default=3, description="最大重试次数")

class VizQLClient:
    """
    VizQL Data Service 客户端
    
    封装新版 VizQL API 调用，提供：
    - Pydantic 模型验证
    - 自动重试
    - 统一错误处理
    - HTTP 连接池复用
    """
    
    def __init__(self, config: Optional[VizQLClientConfig] = None):
        self.config = config or VizQLClientConfig(
            base_url=settings.tableau_domain,
            verify_ssl=settings.vizql_verify_ssl,
            ca_bundle=settings.vizql_ca_bundle,
            timeout=settings.vizql_timeout,
            max_retries=settings.vizql_max_retries
        )
        # 使用 Session 实现连接池复用
        self._session = requests.Session()
        # 配置连接池大小
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=0  # 重试由 tenacity 处理
        )
        self._session.mount('http://', adapter)
        self._session.mount('https://', adapter)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    def query_datasource(
        self,
        datasource_luid: str,
        query: Union[Dict[str, Any], VizQLQuery],
        api_key: str,
        site: Optional[str] = None
    ) -> QueryOutput:
        """
        执行 VizQL 查询
        
        Args:
            datasource_luid: 数据源 LUID
            query: VizQL 查询对象或字典
            api_key: Tableau 认证 token
            site: Tableau 站点（可选）
        
        Returns:
            QueryOutput 对象
        
        Raises:
            VizQLError: API 调用失败
        """
        # 验证并序列化查询
        if isinstance(query, dict):
            query = VizQLQuery(**query)
        query_dict = query.model_dump(exclude_none=True)
        
        # 构建请求
        url = f"{self.config.base_url}/api/v1/vizql-data-service/query-datasource"
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json"
        }
        if site:
            headers["X-Tableau-Site"] = site
        
        payload = {
            "datasource": {"datasourceLuid": datasource_luid},
            "query": query_dict
        }
        
        # 配置 SSL
        verify = self.config.ca_bundle if self.config.ca_bundle else self.config.verify_ssl
        
        # 发送请求（使用连接池）
        response = self._session.post(
            url,
            headers=headers,
            json=payload,
            verify=verify,
            timeout=self.config.timeout
        )
        
        # 处理响应
        if response.status_code == 200:
            return QueryOutput(**response.json())
        else:
            self._handle_error(response)
    
    def _handle_error(self, response: requests.Response):
        """处理 API 错误"""
        from tableau_assistant.src.exceptions import VizQLError
        
        try:
            error_data = response.json()
            raise VizQLError(
                status_code=response.status_code,
                error_code=error_data.get("errorCode"),
                message=error_data.get("message"),
                debug=error_data.get("debug")
            )
        except ValueError:
            raise VizQLError(
                status_code=response.status_code,
                message=response.text
            )
    
    def close(self):
        """关闭连接池"""
        self._session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


### 5. VizQL 异常类设计

```python
# tableau_assistant/src/exceptions.py

from typing import Optional, Dict, Any

class VizQLError(Exception):
    """
    VizQL API 错误基类
    
    Attributes:
        status_code: HTTP 状态码
        error_code: Tableau 错误代码
        message: 错误消息
        debug: 调试信息
        is_retryable: 是否可重试
    """
    
    def __init__(
        self,
        status_code: int,
        message: str,
        error_code: Optional[str] = None,
        debug: Optional[Dict[str, Any]] = None
    ):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.debug = debug
        self.is_retryable = self._determine_retryable()
        super().__init__(self.message)
    
    def _determine_retryable(self) -> bool:
        """判断错误是否可重试"""
        # 5xx 服务器错误可重试
        if 500 <= self.status_code < 600:
            return True
        # 429 速率限制可重试
        if self.status_code == 429:
            return True
        # 其他错误不可重试
        return False
    
    def __str__(self) -> str:
        return f"VizQLError({self.status_code}): {self.message}"


class VizQLAuthError(VizQLError):
    """认证错误 (401/403)"""
    pass


class VizQLValidationError(VizQLError):
    """验证错误 (400)"""
    pass


class VizQLServerError(VizQLError):
    """服务器错误 (5xx)"""
    pass


class VizQLRateLimitError(VizQLError):
    """速率限制错误 (429)"""
    
    def __init__(self, retry_after: Optional[int] = None, **kwargs):
        super().__init__(**kwargs)
        self.retry_after = retry_after
```
```

## 数据模型

### Intent 模型层次结构

```
Intent 模型（intent.py）
├── DimensionIntent（维度意图）
├── MeasureIntent（度量意图）
├── DateFieldIntent（日期字段意图）
├── TableCalcIntent（表计算意图）★ 已实现
├── DateFilterIntent（日期过滤意图）
├── FilterIntent（非日期过滤意图）
└── TopNIntent（TopN 意图）
```

### VizQL 模型层次结构

```
VizQLField（vizql_types.py）
├── BasicField（基础字段）
├── FunctionField（函数字段）
├── CalculationField（计算字段）
└── TableCalcField（表计算字段）★ 已实现
    └── tableCalculation: TableCalcSpecification
        ├── RunningTotalTableCalcSpecification
        ├── MovingTableCalcSpecification
        ├── RankTableCalcSpecification
        └── ... (共 10 种)
```

### 表计算 dimensions 字段规范

#### 数据模型定义

```python
dimensions: List[TableCalcFieldReference] = Field(
    min_length=1,
    description="""Fields that define calculation scope.

Usage:
- Include fields where calculation operates ACROSS their values
- Exclude fields where calculation RESTARTS for each value
- Must be subset of query's dimension fields

Values: List of TableCalcFieldReference
- fieldCaption: Field name from query dimensions
- function: Optional, for date fields (YEAR, MONTH, etc.)

Examples:

1. RUNNING_TOTAL - "Running total of sales by region over time"
   Query dimensions: [Region, Order Date]
   dimensions: [TableCalcFieldReference(fieldCaption="Order Date")]
   Why: Calculate across dates, restart for each region

2. RANK - "Rank products by sales within each category"
   Query dimensions: [Category, Product]
   dimensions: [TableCalcFieldReference(fieldCaption="Product")]
   Why: Rank across products, restart for each category

3. PERCENT_OF_TOTAL - "Each region's percent of total sales"
   Query dimensions: [Region]
   dimensions: [TableCalcFieldReference(fieldCaption="Region")]
   Why: Calculate percent across all regions

4. DIFFERENCE_FROM - "Month over month sales change"
   Query dimensions: [Order Date(MONTH)]
   dimensions: [TableCalcFieldReference(fieldCaption="Order Date", function="MONTH")]
   Why: Compare across months"""
)
```

#### Prompt 模板规则

```
**Table Calculation dimensions determination:**

Rule: dimensions = fields where calculation operates ACROSS
      partition = fields where calculation RESTARTS (NOT in dimensions)

Step 1: List all dimension fields in query

Step 2: For each dimension, ask:
- "Should calculation operate ACROSS this field's values?" → Include in dimensions
- "Should calculation RESTART for each value of this field?" → Exclude from dimensions

Step 3: Verify
- dimensions must be non-empty
- dimensions must be subset of query dimensions
```

#### 表计算类型分类

| Category | Types | dimensions Question |
|----------|-------|---------------------|
| Sequential | RUNNING_TOTAL, MOVING_CALCULATION | "Calculate ACROSS which field in order?" |
| Range-based | RANK, PERCENTILE, PERCENT_OF_TOTAL | "Calculate WITHIN which field's scope?" |
| Comparison | DIFFERENCE_FROM, PERCENT_FROM, PERCENT_DIFFERENCE_FROM | "Compare ALONG which field?" |

## 正确性属性

*属性是系统在所有有效执行中应该保持为真的特征或行为。*

### 属性 1: 工具封装业务逻辑保持
*对于任何*组件输入，工具封装前后的输出应该保持一致
**验证需求: 2.4**

### 属性 2: StateGraph 节点顺序保持
*对于任何*工作流执行，节点执行顺序应该遵循 Boost → Understanding → Planning → Execute → Insight → Replanner
**验证需求: 3.1, 3.2**

### 属性 3: Boost 节点条件跳过
*对于任何*boost_question=False 的情况，系统应该跳过 Boost 节点
**验证需求: 3.4**

### 属性 4: 重规划循环路由
*对于任何*should_replan=True 且 replan_count < max_rounds 且 completeness_score < 0.9 的情况，系统应该从 Replanner 路由回 Planning 节点（跳过 Understanding，因为元数据和字段映射已完成）
**验证需求: 3.5, 3.6**

### 属性 5: TableCalcIntent 到 TableCalcField 转换正确性
*对于任何*有效的 TableCalcIntent，QueryBuilder 生成的 TableCalcField 应该包含正确的 tableCalculation 规范
**验证需求: 5.4, 5.5**

### 属性 6: 日期格式检测一致性
*对于任何*具有相同格式的日期样本集，多次检测应该返回相同的格式类型
**验证需求: 6.3**

### 属性 7: STRING 日期字段 DATEPARSE 生成正确性
*对于任何*STRING 类型的日期字段，QueryBuilder 应该生成包含正确 DATEPARSE 公式的 CalculationField
**验证需求: 6.7**

### 属性 8: Pydantic 模型验证正确性
*对于任何*无效的字段或过滤器定义，Pydantic 验证应该抛出 ValidationError
**验证需求: 4.3, 4.4**

### 属性 9: 表计算 dimensions 子集验证
*对于任何*表计算查询，dimensions 中的字段必须是查询维度字段的子集
**验证需求: 5.9, 5.10**

### 属性 10: 智能终止策略正确性
*对于任何*completeness_score >= 0.9 的情况，系统应该终止重规划循环
**验证需求: 3.6**

### 属性 11: 表计算关键词识别正确性
*对于任何*包含"累计"、"running total"、"排名"、"rank"、"移动平均"、"moving average"关键词的用户问题，Understanding Agent 应该正确识别对应的表计算类型
**验证需求: 5.6, 5.7, 5.8**

### 属性 12: 持久化存储 TTL 正确性
*对于任何*缓存的元数据条目，超过 TTL 后应该被自动清理或标记为过期
**验证需求: 8.2, 8.5**

### 属性 13: VizQL 客户端连接池复用
*对于任何*连续的 API 请求，系统应该复用 HTTP 连接而不是每次创建新连接
**验证需求: 10.5**

## 重规划策略

### 重规划类型

| 类型 | 触发条件 | 生成的新问题 |
|------|---------|-------------|
| 补充缺失信息 | 原问题部分未回答 | 针对缺失部分的补充问题 |
| 深入分析异常 | 发现数据异常 | 针对异常的深入分析问题 |
| 洞察不足 | 分析过于表面 | 更深入的分析问题 |

### 智能终止策略

```
completeness_score >= 0.9  →  直接结束（已足够好）
replan_count >= max_rounds →  强制结束（硬限制）
completeness_score < 0.7   →  继续重规划（明显不足）
0.7 <= score < 0.9         →  由 Replanner 决定
```

### 完成度评估维度

- **问题覆盖度**：是否回答了用户问题的所有方面
- **数据完整性**：是否获取了所需的所有数据
- **洞察深度**：分析是否足够深入
- **异常处理**：是否解释了发现的异常

## 错误处理

### 错误分类

| 错误类型 | HTTP 状态码 | 处理策略 |
|---------|------------|---------|
| 网络错误 | N/A | 重试 + 回退到缓存 |
| 认证错误 | 401/403 | 不重试，返回明确错误 |
| 验证错误 | 400 | 不重试，返回字段级错误 |
| 服务器错误 | 500 | 指数退避重试 |
| 速率限制 | 429 | 遵守 Retry-After 重试 |

### 错误处理流程

```
API 调用
    │
    ├── 成功 → Pydantic 验证响应 → 返回结果
    │
    └── 失败 → 分类错误
              │
              ├── 可重试错误 → 重试次数 < 3?
              │                 ├── 是 → 等待 + 重试
              │                 └── 否 → 返回错误
              │
              └── 不可重试错误 → 返回错误
```

## 测试策略

### 单元测试

1. **工具封装测试**
   - 验证每个工具的输入/输出格式
   - 验证工具保持原有组件逻辑

2. **StateGraph 测试**
   - 验证节点执行顺序
   - 验证条件路由逻辑

3. **VizQL 客户端测试**
   - 验证请求构建
   - 验证响应解析
   - 验证错误处理

### 属性测试

使用 Hypothesis 库进行属性测试，每个属性至少 200 次迭代。

```python
from hypothesis import given, settings, strategies as st

@given(...)
@settings(max_examples=200)
def test_property_xxx(...):
    """Feature: unified-refactor, Property X: ..."""
    pass
```

### 集成测试

1. 完整查询流程测试
2. 表计算功能测试
3. 重规划流程测试

## 实施路径

### 阶段 1: 工具层实现 (5 天)

1. 创建 `src/tools/` 目录结构
2. 实现 7 个工具封装
3. 编写工具单元测试

### 阶段 2: DeepAgent 集成 (3 天)

1. 更新 `deep_agent_factory.py`
2. 配置内置中间件
3. 编写 DeepAgent 测试

### 阶段 3: StateGraph 适配 (3 天)

1. 更新 `vizql_workflow.py`
2. 修改节点以使用 DeepAgent
3. 编写 StateGraph 测试

### 阶段 4: VizQL 客户端增强 (2 天)

1. 实现 `VizQLClient` 类
2. 添加 Pydantic 验证
3. 添加重试逻辑

### 阶段 5: 集成测试 (3 天)

1. 运行所有单元测试
2. 运行属性测试
3. 运行集成测试
4. 修复发现的问题

### 阶段 6: 文档和部署 (2 天)

1. 更新 API 文档
2. 更新架构文档
3. 准备发布

**总计: 约 18 天（3.5 周）**

## 编码规范

### Pydantic 模型规范

```python
class ExampleModel(BaseModel):
    """模型文档字符串"""
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="""Brief description.

Usage:
- When to use this field

Values: Valid values"""
    )
```

### 工具规范

```python
@tool(args_schema=InputSchema)
def tool_name(param: str) -> Dict[str, Any]:
    """
    工具简短描述
    
    详细描述工具功能。
    
    Args:
        param: 参数说明
    
    Returns:
        返回值说明
    
    Example:
        >>> result = tool_name("value")
    """
    pass
```
