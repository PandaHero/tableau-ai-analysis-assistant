# Tableau Assistant DeepAgents 重构设计文档

## 概述

本文档描述了将 Tableau Assistant 从当前的自定义多智能体架构迁移到 LangChain DeepAgents 框架的详细设计。重构的目标是：

1. **简化架构**: 利用 DeepAgents 的内置功能减少自定义代码
2. **提升性能**: 使用自动总结、缓存和并行执行优化
3. **增强可维护性**: 使用标准化的中间件和子代理模式
4. **保持兼容性**: 确保 API 接口不变，前端无需修改

## 架构对比

### 当前架构 (Before)

```
FastAPI
  ├─ VizQL Workflow (LangGraph)
  │   ├─ Question Boost Agent
  │   ├─ Understanding Agent
  │   ├─ Task Planner Agent
  │   ├─ Query Executor (Component)
  │   ├─ Insight Agent
  │   ├─ Replanner Agent
  │   └─ Summarizer Agent
  ├─ Custom Components
  │   ├─ MetadataManager
  │   ├─ DateParser
  │   ├─ QueryBuilder
  │   └─ PersistentStore
  └─ Tableau Tools
      ├─ VizQL Query Tool
      ├─ Metadata Tool
      └─ Field Mapping Tool
```

### 新架构 (After - DeepAgents)

```
FastAPI
  ├─ DeepAgent (Main Orchestrator)
  │   ├─ Built-in Middleware
  │   │   ├─ TodoListMiddleware (规划)
  │   │   ├─ FilesystemMiddleware (文件操作)
  │   │   ├─ SubAgentMiddleware (子代理委托)
  │   │   ├─ SummarizationMiddleware (自动总结)
  │   │   └─ AnthropicPromptCachingMiddleware (缓存)
  │   ├─ Custom Middleware
  │   │   ├─ TableauMetadataMiddleware
  │   │   ├─ VizQLQueryMiddleware
  │   │   └─ InsightGenerationMiddleware
  │   ├─ SubAgents
  │   │   ├─ understanding-agent
  │   │   ├─ planning-agent
  │   │   ├─ insight-agent
  │   │   └─ replanner-agent
  │   └─ Tableau Tools
  │       ├─ vizql_query
  │       ├─ get_metadata
  │       ├─ map_fields
  │       └─ parse_date
  └─ Backend (CompositeBackend)
      ├─ StateBackend (临时文件)
      └─ StoreBackend (持久化)
          ├─ /metadata/*
          ├─ /hierarchies/*
          └─ /preferences/*
```



## 组件设计

### 1. 主 Agent 创建

```python
# tableau_assistant/src/deepagents/agent_factory.py

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore

def create_tableau_agent(
    store: InMemoryStore,
    model_config: Optional[Dict] = None
):
    """
    创建 Tableau DeepAgent
    
    Args:
        store: LangGraph Store 实例
        model_config: 可选的模型配置
    
    Returns:
        编译后的 DeepAgent
    """
    # 1. 配置后端（混合存储）
    backend = CompositeBackend(
        default=StateBackend(),  # 临时文件
        routes={
            "/metadata/": StoreBackend(store=store),      # 元数据持久化
            "/hierarchies/": StoreBackend(store=store),   # 维度层级持久化
            "/preferences/": StoreBackend(store=store),   # 用户偏好持久化
        }
    )
    
    # 2. 导入 Tableau 工具
    from tableau_assistant.src.deepagents.tools import (
        vizql_query_tool,
        get_metadata_tool,
        map_fields_tool,
        parse_date_tool
    )
    
    # 3. 导入自定义中间件
    from tableau_assistant.src.deepagents.middleware import (
        TableauMetadataMiddleware,
        VizQLQueryMiddleware,
        InsightGenerationMiddleware
    )
    
    # 4. 定义子代理
    subagents = [
        {
            "name": "understanding-agent",
            "description": "理解用户问题意图，识别查询类型和复杂度",
            "prompt": UNDERSTANDING_AGENT_PROMPT,
            "tools": [get_metadata_tool, map_fields_tool],
            "model": model_config.get("model") if model_config else None
        },
        {
            "name": "planning-agent",
            "description": "生成查询计划，分解为可执行的子任务",
            "prompt": PLANNING_AGENT_PROMPT,
            "tools": [get_metadata_tool, parse_date_tool],
            "model": model_config.get("model") if model_config else None
        },
        {
            "name": "insight-agent",
            "description": "分析查询结果，生成洞察和建议",
            "prompt": INSIGHT_AGENT_PROMPT,
            "tools": [],
            "model": model_config.get("model") if model_config else None
        },
        {
            "name": "replanner-agent",
            "description": "评估当前结果，决定是否需要重新规划",
            "prompt": REPLANNER_AGENT_PROMPT,
            "tools": [get_metadata_tool],
            "model": model_config.get("model") if model_config else None
        }
    ]
    
    # 5. 创建 DeepAgent
    agent = create_deep_agent(
        model=model_config.get("model") if model_config else None,
        tools=[
            vizql_query_tool,
            get_metadata_tool,
            map_fields_tool,
            parse_date_tool
        ],
        system_prompt=TABLEAU_SYSTEM_PROMPT,
        middleware=[
            TableauMetadataMiddleware(),
            VizQLQueryMiddleware(),
            InsightGenerationMiddleware()
        ],
        subagents=subagents,
        backend=backend,
        store=store
    )
    
    return agent
```

### 2. 自定义中间件

#### 2.1 TableauMetadataMiddleware

```python
# tableau_assistant/src/deepagents/middleware/tableau_metadata.py

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import tool

class TableauMetadataMiddleware(AgentMiddleware):
    """
    Tableau 元数据中间件
    
    功能：
    - 自动注入元数据查询工具
    - 在系统提示词中添加元数据使用指南
    - 缓存元数据以减少 API 调用
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = METADATA_SYSTEM_PROMPT
        self.tools = [self._create_metadata_tool()]
    
    def _create_metadata_tool(self):
        @tool
        def get_tableau_metadata(
            datasource_luid: str,
            use_cache: bool = True,
            enhance: bool = True
        ) -> Dict[str, Any]:
            """
            获取 Tableau 数据源元数据
            
            Args:
                datasource_luid: 数据源 LUID
                use_cache: 是否使用缓存
                enhance: 是否增强元数据（添加 valid_max_date 等）
            
            Returns:
                元数据字典
            """
            from tableau_assistant.src.components.metadata_manager import MetadataManager
            # 实现省略...
            pass
        
        return get_tableau_metadata
```

#### 2.2 VizQLQueryMiddleware

```python
# tableau_assistant/src/deepagents/middleware/vizql_query.py

class VizQLQueryMiddleware(AgentMiddleware):
    """
    VizQL 查询中间件
    
    功能：
    - 自动注入 VizQL 查询工具
    - 在系统提示词中添加查询语法指南
    - 自动处理查询错误和重试
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = VIZQL_SYSTEM_PROMPT
        self.tools = [self._create_query_tool()]
    
    def _create_query_tool(self):
        @tool
        def execute_vizql_query(
            query: Dict[str, Any],
            datasource_luid: str,
            max_retries: int = 3
        ) -> Dict[str, Any]:
            """
            执行 VizQL 查询
            
            Args:
                query: VizQL 查询对象
                datasource_luid: 数据源 LUID
                max_retries: 最大重试次数
            
            Returns:
                查询结果
            """
            from tableau_assistant.src.components.query_executor import QueryExecutor
            # 实现省略...
            pass
        
        return execute_vizql_query
```



### 3. 子代理定义

#### 3.1 Understanding Agent

```python
# tableau_assistant/src/deepagents/subagents/understanding.py

UNDERSTANDING_AGENT_PROMPT = """
你是一个专业的问题理解专家，专门分析用户的 Tableau 数据查询意图。

你的任务：
1. 识别问题类型（趋势、对比、排名、分布等）
2. 提取关键实体（维度、度量、时间范围）
3. 评估问题复杂度
4. 识别潜在的歧义

可用工具：
- get_metadata: 获取数据源元数据
- map_fields: 映射用户提到的字段到实际字段名

输出格式：
{
    "question_type": ["comparison", "trend"],
    "complexity": "medium",
    "entities": {
        "dimensions": ["地区", "产品类别"],
        "measures": ["销售额"],
        "time_range": "2016年"
    },
    "ambiguities": ["地区可能指省份或城市"],
    "confidence": 0.85
}
"""

# 子代理会自动获得：
# - get_metadata_tool
# - map_fields_tool
# - 所有 DeepAgents 内置工具（ls, read_file, write_file 等）
```

#### 3.2 Planning Agent

```python
# tableau_assistant/src/deepagents/subagents/planning.py

PLANNING_AGENT_PROMPT = """
你是一个查询规划专家，负责将用户问题分解为可执行的 VizQL 查询计划。

你的任务：
1. 根据问题理解结果生成查询计划
2. 分解为多个子任务（如果需要）
3. 确定子任务的执行顺序和依赖关系
4. 为每个子任务生成 VizQL 查询

可用工具：
- get_metadata: 获取字段信息
- parse_date: 解析相对日期（如"上个月"）
- write_file: 保存复杂的查询计划到文件

输出格式：
{
    "subtasks": [
        {
            "id": "task_1",
            "description": "查询2016年各地区销售额",
            "query": {...},  // VizQL 查询对象
            "dependencies": []
        },
        {
            "id": "task_2",
            "description": "查询2015年各地区销售额用于对比",
            "query": {...},
            "dependencies": []
        }
    ],
    "execution_strategy": "parallel"
}
"""
```

#### 3.3 Insight Agent

```python
# tableau_assistant/src/deepagents/subagents/insight.py

INSIGHT_AGENT_PROMPT = """
你是一个数据洞察专家，负责分析查询结果并生成有价值的洞察。

你的任务：
1. 分析查询结果中的模式和趋势
2. 识别异常值和有趣的发现
3. 生成可操作的建议
4. 提供数据可视化建议

可用工具：
- read_file: 读取大型查询结果（如果结果被保存到文件）
- write_file: 保存详细的分析报告

输出格式：
{
    "key_findings": [
        "华东地区销售额最高，占总销售额的35%",
        "相比2015年，2016年销售额增长了12%"
    ],
    "insights": [
        {
            "type": "trend",
            "description": "销售额呈现季节性波动",
            "confidence": 0.9
        }
    ],
    "recommendations": [
        "建议重点关注华东地区的市场策略",
        "可以进一步分析季节性因素"
    ],
    "visualization_suggestions": [
        {
            "type": "bar_chart",
            "x": "地区",
            "y": "销售额",
            "title": "2016年各地区销售额对比"
        }
    ]
}
"""
```

### 4. 工具定义

```python
# tableau_assistant/src/deepagents/tools/vizql.py

from langchain_core.tools import tool
from typing import Dict, Any

@tool
def vizql_query(
    query: Dict[str, Any],
    datasource_luid: str
) -> Dict[str, Any]:
    """
    执行 VizQL 查询
    
    Args:
        query: VizQL 查询对象，包含：
            - dimensions: 维度列表
            - measures: 度量列表
            - filters: 过滤器列表
            - sort: 排序规则
            - limit: 结果数量限制
        datasource_luid: 数据源 LUID
    
    Returns:
        查询结果，包含：
            - data: 数据行列表
            - schema: 字段schema
            - row_count: 行数
    
    Example:
        query = {
            "dimensions": ["地区"],
            "measures": [{"field": "销售额", "aggregation": "SUM"}],
            "filters": [
                {"field": "年份", "operator": "=", "value": 2016}
            ]
        }
        result = vizql_query(query, "abc123")
    """
    from tableau_assistant.src.components.query_executor import QueryExecutor
    from tableau_assistant.src.utils.tableau.auth import get_jwt_token
    
    # 获取认证 token
    token = get_jwt_token()
    
    # 执行查询
    executor = QueryExecutor(token, datasource_luid)
    result = executor.execute(query)
    
    return result


@tool
def get_metadata(
    datasource_luid: str,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    获取 Tableau 数据源元数据
    
    Args:
        datasource_luid: 数据源 LUID
        use_cache: 是否使用缓存（默认 True）
    
    Returns:
        元数据，包含：
            - fields: 字段列表
            - valid_max_date: 数据的最新日期
            - datasource_name: 数据源名称
    
    Example:
        metadata = get_metadata("abc123")
        fields = metadata["fields"]
    """
    from tableau_assistant.src.components.metadata_manager import MetadataManager
    
    manager = MetadataManager()
    metadata = manager.get_metadata(
        datasource_luid,
        use_cache=use_cache,
        enhance=True
    )
    
    return metadata


@tool
def map_fields(
    user_input: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    将用户输入的字段名映射到实际字段名
    
    Args:
        user_input: 用户输入的字段名（如"销售额"）
        metadata: 数据源元数据
    
    Returns:
        映射结果，包含：
            - matched_field: 匹配的字段名
            - confidence: 匹配置信度
            - alternatives: 其他可能的匹配
    
    Example:
        result = map_fields("销售额", metadata)
        field_name = result["matched_field"]
    """
    from tableau_assistant.src.components.field_mapper import FieldMapper
    
    mapper = FieldMapper(metadata)
    result = mapper.map(user_input)
    
    return result


@tool
def parse_date(
    date_expression: str,
    reference_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    解析相对日期表达式
    
    Args:
        date_expression: 日期表达式（如"上个月"、"去年"）
        reference_date: 参考日期（默认为今天）
    
    Returns:
        解析结果，包含：
            - start_date: 开始日期
            - end_date: 结束日期
            - date_type: 日期类型（day/week/month/year）
    
    Example:
        result = parse_date("上个月")
        # {"start_date": "2024-10-01", "end_date": "2024-10-31", "date_type": "month"}
    """
    from tableau_assistant.src.components.date_parser import DateParser
    
    parser = DateParser()
    result = parser.parse(date_expression, reference_date)
    
    return result
```



### 5. API 集成

```python
# tableau_assistant/src/api/deepagents_chat.py

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from tableau_assistant.src.models.api import VizQLQueryRequest, VizQLQueryResponse
from tableau_assistant.src.deepagents.agent_factory import create_tableau_agent
from tableau_assistant.src.components.persistent_store import PersistentStore

router = APIRouter(prefix="/api/v2", tags=["deepagents"])

# 全局 Store 实例
store = PersistentStore(db_path="data/deepagents_store.db")


@router.post("/chat", response_model=VizQLQueryResponse)
async def chat_sync(request: VizQLQueryRequest):
    """
    同步查询端点（使用 DeepAgents）
    
    Args:
        request: 查询请求
    
    Returns:
        完整的查询结果
    """
    # 创建 Agent
    agent = create_tableau_agent(
        store=store.store,
        model_config=request.model_config
    )
    
    # 准备输入
    input_data = {
        "question": request.question
    }
    
    # 准备配置
    config = {
        "configurable": {
            "thread_id": request.session_id,
            "datasource_luid": request.datasource_luid,
            "user_id": request.user_id or "default_user"
        }
    }
    
    # 执行
    try:
        result = agent.invoke(input_data, config=config)
        
        # 格式化输出
        return VizQLQueryResponse(
            executive_summary=result.get("final_report", {}).get("executive_summary", ""),
            key_findings=result.get("final_report", {}).get("key_findings", []),
            analysis_path=result.get("final_report", {}).get("analysis_path", []),
            recommendations=result.get("final_report", {}).get("recommendations", []),
            visualizations=result.get("visualizations", [])
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: VizQLQueryRequest):
    """
    流式查询端点（使用 DeepAgents）
    
    Args:
        request: 查询请求
    
    Returns:
        SSE 流
    """
    # 创建 Agent
    agent = create_tableau_agent(
        store=store.store,
        model_config=request.model_config
    )
    
    # 准备输入
    input_data = {
        "question": request.question
    }
    
    # 准备配置
    config = {
        "configurable": {
            "thread_id": request.session_id,
            "datasource_luid": request.datasource_luid,
            "user_id": request.user_id or "default_user"
        }
    }
    
    async def event_generator():
        """生成 SSE 事件"""
        try:
            # 使用 astream_events 获取所有事件
            async for event in agent.astream_events(input_data, config=config, version="v2"):
                event_type = event.get("event")
                
                # Token 流
                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        token = chunk.content
                        if token:
                            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                
                # Agent 进度
                elif event_type == "on_chain_start":
                    name = event.get("name", "")
                    if "agent" in name.lower():
                        yield f"data: {json.dumps({'type': 'agent_start', 'agent': name})}\n\n"
                
                elif event_type == "on_chain_end":
                    name = event.get("name", "")
                    if "agent" in name.lower():
                        yield f"data: {json.dumps({'type': 'agent_end', 'agent': name})}\n\n"
                
                # 工具调用
                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "")
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': tool_name})}\n\n"
                
                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "")
                    yield f"data: {json.dumps({'type': 'tool_end', 'tool': tool_name})}\n\n"
            
            # 完成
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

### 6. 执行流程

#### 6.1 典型查询流程

```
用户: "2016年各地区的销售额"
  ↓
主 Agent 接收查询
  ↓
主 Agent 使用 write_todos 创建任务列表:
  - [ ] 理解问题意图
  - [ ] 生成查询计划
  - [ ] 执行查询
  - [ ] 分析结果
  - [ ] 生成报告
  ↓
主 Agent 调用 task(description="理解问题...", subagent_type="understanding-agent")
  ↓
Understanding SubAgent 执行:
  - 调用 get_metadata 获取字段信息
  - 调用 map_fields 映射"地区"和"销售额"
  - 返回理解结果
  ↓
主 Agent 更新 todos，标记"理解问题意图"为完成
  ↓
主 Agent 调用 task(description="生成查询计划...", subagent_type="planning-agent")
  ↓
Planning SubAgent 执行:
  - 调用 parse_date 解析"2016年"
  - 生成 VizQL 查询对象
  - 返回查询计划
  ↓
主 Agent 更新 todos，标记"生成查询计划"为完成
  ↓
主 Agent 直接调用 vizql_query 工具执行查询
  ↓
查询结果很大，FilesystemMiddleware 自动保存到 /results/query_1.json
  ↓
主 Agent 调用 task(description="分析结果...", subagent_type="insight-agent")
  ↓
Insight SubAgent 执行:
  - 调用 read_file 读取 /results/query_1.json
  - 分析数据，生成洞察
  - 返回洞察结果
  ↓
主 Agent 更新 todos，标记"分析结果"为完成
  ↓
主 Agent 生成最终报告
  ↓
返回给用户
```

#### 6.2 并行执行示例

```
用户: "对比2015年和2016年各地区的销售额"
  ↓
主 Agent 理解需要两个独立查询
  ↓
主 Agent 并行调用两个 task:
  - task(description="查询2015年数据", subagent_type="planning-agent")
  - task(description="查询2016年数据", subagent_type="planning-agent")
  ↓
两个 Planning SubAgent 并行执行
  ↓
主 Agent 收集两个结果
  ↓
主 Agent 调用 task(description="对比分析", subagent_type="insight-agent")
  ↓
返回对比分析结果
```

### 7. 数据模型

#### 7.1 State Schema

```python
# DeepAgents 使用内置的 State 管理
# 我们只需要定义自定义字段

from typing import TypedDict, List, Dict, Any, Optional

class TableauAgentState(TypedDict):
    """
    Tableau Agent 状态
    
    注意：DeepAgents 会自动添加以下字段：
    - messages: 对话历史
    - todos: 任务列表
    - files: 文件系统状态
    """
    # 用户输入
    question: str
    
    # 理解结果
    understanding: Optional[Dict[str, Any]]
    
    # 查询计划
    query_plan: Optional[Dict[str, Any]]
    
    # 查询结果
    query_results: List[Dict[str, Any]]
    
    # 洞察
    insights: List[Dict[str, Any]]
    
    # 最终报告
    final_report: Optional[Dict[str, Any]]
    
    # 元数据（从 Store 加载）
    metadata: Optional[Dict[str, Any]]
```

#### 7.2 Context Schema

```python
from typing import TypedDict

class TableauContext(TypedDict):
    """
    Tableau 运行时上下文（不可变）
    """
    datasource_luid: str
    user_id: str
    session_id: str
```



## 错误处理

### 1. LLM 调用失败

```python
# DeepAgents 内置重试机制
# 我们可以在工具层面添加额外的错误处理

@tool
def vizql_query_with_retry(query: Dict, datasource_luid: str) -> Dict:
    """带重试的 VizQL 查询"""
    from tableau_assistant.src.utils.retry import retry_with_backoff
    
    @retry_with_backoff(max_attempts=3, backoff_factor=2)
    def _execute():
        return execute_query(query, datasource_luid)
    
    try:
        return _execute()
    except Exception as e:
        # 如果所有重试都失败，返回错误信息
        return {
            "error": str(e),
            "suggestion": "请检查查询语法或数据源连接"
        }
```

### 2. 子代理执行失败

```python
# 主 Agent 可以捕获子代理错误并尝试替代方案

# 在系统提示词中添加错误处理指南：
TABLEAU_SYSTEM_PROMPT = """
...

## 错误处理

如果子代理执行失败：
1. 检查错误信息
2. 如果是查询语法错误，尝试简化查询
3. 如果是数据源连接错误，通知用户
4. 如果是超时错误，尝试减少数据量

示例：
- 子代理返回错误 -> 分析错误原因 -> 调整参数 -> 重新调用
- 如果多次失败 -> 向用户说明情况 -> 提供替代方案
"""
```

### 3. 查询结果过大

```python
# DeepAgents 的 FilesystemMiddleware 会自动处理

# 当工具返回超过 20k tokens 的结果时：
# 1. 自动保存到文件系统
# 2. 返回文件路径和前 10 行预览
# 3. Agent 可以使用 read_file 工具分页读取

# 示例：
result = vizql_query(large_query, datasource_luid)
# 如果结果过大，FilesystemMiddleware 自动保存
# Agent 收到：
# {
#   "file_path": "/results/query_1.json",
#   "preview": [...前10行...],
#   "row_count": 10000
# }

# Agent 可以：
# 1. 使用 read_file("/results/query_1.json", offset=0, limit=100) 分页读取
# 2. 或者直接基于 preview 生成洞察
```

## 测试策略

### 1. 单元测试

```python
# tests/test_deepagents/test_tools.py

import pytest
from tableau_assistant.src.deepagents.tools import vizql_query, get_metadata

def test_vizql_query_tool():
    """测试 VizQL 查询工具"""
    query = {
        "dimensions": ["地区"],
        "measures": [{"field": "销售额", "aggregation": "SUM"}]
    }
    result = vizql_query(query, "test_datasource_luid")
    
    assert "data" in result
    assert "schema" in result
    assert len(result["data"]) > 0


def test_get_metadata_tool():
    """测试元数据工具"""
    metadata = get_metadata("test_datasource_luid")
    
    assert "fields" in metadata
    assert len(metadata["fields"]) > 0
```

### 2. 子代理测试

```python
# tests/test_deepagents/test_subagents.py

import pytest
from tableau_assistant.src.deepagents.agent_factory import create_tableau_agent

@pytest.mark.asyncio
async def test_understanding_agent():
    """测试理解子代理"""
    agent = create_tableau_agent(store=test_store)
    
    input_data = {
        "question": "2016年各地区的销售额"
    }
    
    config = {
        "configurable": {
            "thread_id": "test_thread",
            "datasource_luid": "test_luid",
            "user_id": "test_user"
        }
    }
    
    # 直接调用子代理
    result = await agent.invoke(
        {
            "messages": [{
                "role": "user",
                "content": "使用 understanding-agent 理解这个问题：2016年各地区的销售额"
            }]
        },
        config=config
    )
    
    # 验证结果
    assert "understanding" in result
    assert result["understanding"]["question_type"] is not None
```

### 3. 集成测试

```python
# tests/test_deepagents/test_integration.py

@pytest.mark.asyncio
async def test_complete_query_flow():
    """测试完整查询流程"""
    agent = create_tableau_agent(store=test_store)
    
    input_data = {
        "question": "对比2015年和2016年各地区的销售额"
    }
    
    config = {
        "configurable": {
            "thread_id": "test_thread",
            "datasource_luid": "test_luid",
            "user_id": "test_user"
        }
    }
    
    result = await agent.ainvoke(input_data, config=config)
    
    # 验证完整流程
    assert "final_report" in result
    assert "executive_summary" in result["final_report"]
    assert len(result["final_report"]["key_findings"]) > 0
```

### 4. 性能测试

```python
# tests/test_deepagents/test_performance.py

import time

def test_parallel_execution_performance():
    """测试并行执行性能"""
    agent = create_tableau_agent(store=test_store)
    
    # 测试串行执行
    start = time.time()
    result_serial = agent.invoke({
        "question": "分别查询2015、2016、2017年的销售额",
        "execution_mode": "serial"
    })
    serial_time = time.time() - start
    
    # 测试并行执行
    start = time.time()
    result_parallel = agent.invoke({
        "question": "分别查询2015、2016、2017年的销售额",
        "execution_mode": "parallel"
    })
    parallel_time = time.time() - start
    
    # 并行应该更快
    assert parallel_time < serial_time * 0.7  # 至少快30%
```

## 迁移计划

### 阶段 1: 基础设施（1-2 周）

1. **安装 DeepAgents**
   ```bash
   pip install deepagents
   ```

2. **创建基础结构**
   - `src/deepagents/` 目录
   - `agent_factory.py` - Agent 创建工厂
   - `tools/` - 工具定义
   - `middleware/` - 自定义中间件
   - `subagents/` - 子代理定义

3. **配置后端**
   - 实现 CompositeBackend
   - 配置路由规则
   - 测试持久化存储

### 阶段 2: 工具迁移（1 周）

1. **迁移现有工具**
   - `vizql_query` - VizQL 查询
   - `get_metadata` - 元数据查询
   - `map_fields` - 字段映射
   - `parse_date` - 日期解析

2. **添加工具文档**
   - 每个工具添加详细的 docstring
   - 添加使用示例

### 阶段 3: 子代理实现（2 周）

1. **实现 4 个核心子代理**
   - Understanding Agent
   - Planning Agent
   - Insight Agent
   - Replanner Agent

2. **测试子代理**
   - 单元测试
   - 集成测试

### 阶段 4: 中间件开发（1 周）

1. **实现自定义中间件**
   - TableauMetadataMiddleware
   - VizQLQueryMiddleware
   - InsightGenerationMiddleware

2. **测试中间件**
   - 验证工具注入
   - 验证提示词注入

### 阶段 5: API 集成（1 周）

1. **创建新的 API 端点**
   - `/api/v2/chat` - 同步端点
   - `/api/v2/chat/stream` - 流式端点

2. **保持向后兼容**
   - 保留 `/api/chat` 端点
   - 添加版本切换配置

### 阶段 6: 测试和优化（1-2 周）

1. **完整测试**
   - 单元测试
   - 集成测试
   - 性能测试
   - 压力测试

2. **性能优化**
   - 调整缓存策略
   - 优化并行执行
   - 调整总结阈值

### 阶段 7: 文档和部署（1 周）

1. **编写文档**
   - 架构文档
   - API 文档
   - 迁移指南

2. **部署**
   - 灰度发布
   - 监控和调优

## 预期收益

### 1. 代码简化

- **减少自定义代码**: 约 30-40% 的代码可以被 DeepAgents 内置功能替代
- **统一架构**: 使用标准的中间件和子代理模式
- **更好的可维护性**: 清晰的职责分离

### 2. 性能提升

- **自动并行执行**: 独立子任务自动并行
- **智能缓存**: Anthropic 提示词缓存可节省 50-90% 成本
- **自动总结**: 长上下文自动总结，减少 token 消耗

### 3. 功能增强

- **文件系统**: 自动处理大型结果
- **人工审批**: 敏感操作可配置审批
- **更好的错误处理**: 内置重试和错误恢复

### 4. 开发效率

- **快速迭代**: 添加新功能只需定义工具或子代理
- **标准化**: 使用 LangChain 生态系统的最佳实践
- **社区支持**: 可以利用 DeepAgents 的更新和改进

## 风险和缓解

### 风险 1: 学习曲线

**风险**: 团队需要学习 DeepAgents 框架

**缓解**:
- 提供详细的培训文档
- 逐步迁移，保留现有系统作为参考
- 创建示例和最佳实践指南

### 风险 2: 性能回归

**风险**: 新架构可能不如优化过的旧架构快

**缓解**:
- 在迁移前进行性能基准测试
- 逐步迁移，对比性能
- 使用 DeepAgents 的优化功能（缓存、并行等）

### 风险 3: 兼容性问题

**风险**: 新 API 可能与前端不兼容

**缓解**:
- 保留旧 API 端点
- 使用版本化 API（/api/v2）
- 提供适配层确保响应格式一致

### 风险 4: 依赖外部框架

**风险**: 依赖 DeepAgents 的更新和维护

**缓解**:
- DeepAgents 是 LangChain 官方项目，维护有保障
- 核心逻辑保持独立，可以切换到其他框架
- 定期更新依赖，跟踪框架变化

## 总结

将 Tableau Assistant 迁移到 DeepAgents 框架是一个战略性的架构升级，可以带来：

1. **更简洁的代码**: 利用内置功能减少自定义代码
2. **更好的性能**: 自动优化和并行执行
3. **更强的扩展性**: 标准化的中间件和子代理模式
4. **更低的维护成本**: 使用成熟的开源框架

迁移过程预计需要 **7-9 周**，采用渐进式迁移策略，确保系统稳定性和向后兼容性。
