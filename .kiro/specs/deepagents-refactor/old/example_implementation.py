"""
Tableau Assistant DeepAgents 重构示例代码

这个文件展示了如何将现有的 Tableau Assistant 迁移到 DeepAgents 框架
"""

# ============================================================================
# 1. 安装依赖
# ============================================================================
"""
pip install deepagents tavily-python
pip install langchain langchain-anthropic langgraph
"""

# ============================================================================
# 2. 创建 Tableau Agent Factory
# ============================================================================

from typing import Optional, Dict, Any
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore
from langchain_core.tools import tool


def create_tableau_deep_agent(
    store: InMemoryStore,
    model_config: Optional[Dict[str, Any]] = None
):
    """
    创建 Tableau DeepAgent
    
    这个函数替代了原来的 create_vizql_workflow()
    
    Args:
        store: LangGraph Store 实例
        model_config: 可选的模型配置
            - provider: "local", "azure", or "openai"
            - model_name: 模型名称
            - temperature: 温度设置
    
    Returns:
        编译后的 DeepAgent
    """
    
    # ========== 1. 配置后端（混合存储） ==========
    backend = CompositeBackend(
        default=StateBackend(),  # 临时文件（查询结果等）
        routes={
            "/metadata/": StoreBackend(store=store),      # 元数据持久化
            "/hierarchies/": StoreBackend(store=store),   # 维度层级持久化
            "/preferences/": StoreBackend(store=store),   # 用户偏好持久化
        }
    )
    
    # ========== 2. 定义 Tableau 工具 ==========
    
    @tool
    def vizql_query(
        query: Dict[str, Any],
        datasource_luid: str
    ) -> Dict[str, Any]:
        """
        执行 VizQL 查询
        
        Args:
            query: VizQL 查询对象
            datasource_luid: 数据源 LUID
        
        Returns:
            查询结果
        """
        from tableau_assistant.src.components.query_executor import QueryExecutor
        from tableau_assistant.src.utils.tableau.auth import get_jwt_token
        
        token = get_jwt_token()
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
            use_cache: 是否使用缓存
        
        Returns:
            元数据字典
        """
        from tableau_assistant.src.components.metadata_manager import MetadataManager
        from langgraph.runtime import Runtime
        
        # 注意：在实际使用中，runtime 会自动注入
        # 这里只是示例
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
            user_input: 用户输入的字段名
            metadata: 数据源元数据
        
        Returns:
            映射结果
        """
        # 简化的字段映射逻辑
        fields = metadata.get("fields", [])
        
        # 模糊匹配
        for field in fields:
            if user_input.lower() in field["name"].lower():
                return {
                    "matched_field": field["name"],
                    "confidence": 0.9,
                    "alternatives": []
                }
        
        return {
            "matched_field": None,
            "confidence": 0.0,
            "alternatives": [f["name"] for f in fields[:5]]
        }
    
    @tool
    def parse_date(
        date_expression: str,
        reference_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        解析相对日期表达式
        
        Args:
            date_expression: 日期表达式（如"上个月"）
            reference_date: 参考日期
        
        Returns:
            解析结果
        """
        from tableau_assistant.src.components.date_parser import DateParser
        
        parser = DateParser()
        result = parser.parse(date_expression, reference_date)
        
        return result
    
    # ========== 3. 定义子代理 ==========
    
    # 3.1 Understanding Agent
    understanding_agent = {
        "name": "understanding-agent",
        "description": "理解用户问题意图，识别查询类型、实体和复杂度",
        "prompt": """
你是一个专业的问题理解专家，专门分析用户的 Tableau 数据查询意图。

你的任务：
1. 识别问题类型（趋势、对比、排名、分布等）
2. 提取关键实体（维度、度量、时间范围）
3. 评估问题复杂度
4. 识别潜在的歧义

可用工具：
- get_metadata: 获取数据源元数据
- map_fields: 映射用户提到的字段到实际字段名

输出格式（JSON）：
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
""",
        "tools": [get_metadata, map_fields],
        "model": model_config.get("model") if model_config else None
    }
    
    # 3.2 Planning Agent
    planning_agent = {
        "name": "planning-agent",
        "description": "生成查询计划，分解为可执行的子任务",
        "prompt": """
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

输出格式（JSON）：
{
    "subtasks": [
        {
            "id": "task_1",
            "description": "查询2016年各地区销售额",
            "query": {
                "dimensions": ["地区"],
                "measures": [{"field": "销售额", "aggregation": "SUM"}],
                "filters": [{"field": "年份", "operator": "=", "value": 2016}]
            },
            "dependencies": []
        }
    ],
    "execution_strategy": "parallel"
}
""",
        "tools": [get_metadata, parse_date],
        "model": model_config.get("model") if model_config else None
    }
    
    # 3.3 Insight Agent
    insight_agent = {
        "name": "insight-agent",
        "description": "分析查询结果，生成洞察和建议",
        "prompt": """
你是一个数据洞察专家，负责分析查询结果并生成有价值的洞察。

你的任务：
1. 分析查询结果中的模式和趋势
2. 识别异常值和有趣的发现
3. 生成可操作的建议
4. 提供数据可视化建议

可用工具：
- read_file: 读取大型查询结果（如果结果被保存到文件）
- write_file: 保存详细的分析报告

输出格式（JSON）：
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
        "建议重点关注华东地区的市场策略"
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
""",
        "tools": [],  # 只使用 DeepAgents 内置的文件工具
        "model": model_config.get("model") if model_config else None
    }
    
    # ========== 4. 定义系统提示词 ==========
    
    system_prompt = """
你是一个专业的 Tableau 数据分析助手，帮助用户分析和理解数据。

## 你的能力

1. **问题理解**: 理解用户的自然语言查询意图
2. **查询规划**: 将复杂问题分解为可执行的查询
3. **数据分析**: 分析查询结果，生成洞察
4. **可视化建议**: 提供合适的数据可视化方案

## 工作流程

1. 使用 `task()` 工具委托给 understanding-agent 理解问题
2. 使用 `task()` 工具委托给 planning-agent 生成查询计划
3. 使用 `vizql_query` 工具执行查询
4. 使用 `task()` 工具委托给 insight-agent 分析结果
5. 生成最终报告

## 重要提示

- 对于复杂任务，使用 `write_todos` 创建任务列表
- 对于独立的子任务，并行调用多个 `task()` 工具
- 如果查询结果很大，它会自动保存到文件，使用 `read_file` 分页读取
- 始终提供清晰、可操作的洞察

## 示例

用户: "2016年各地区的销售额"

你的思考过程：
1. 这是一个简单的查询，需要理解意图
2. 调用 understanding-agent 理解问题
3. 调用 planning-agent 生成查询计划
4. 执行查询
5. 调用 insight-agent 分析结果
6. 生成报告

开始工作吧！
"""
    
    # ========== 5. 创建 DeepAgent ==========
    
    agent = create_deep_agent(
        model=model_config.get("model") if model_config else "claude-sonnet-4-5-20250929",
        tools=[
            vizql_query,
            get_metadata,
            map_fields,
            parse_date
        ],
        system_prompt=system_prompt,
        middleware=[],  # 可以添加自定义中间件
        subagents=[
            understanding_agent,
            planning_agent,
            insight_agent
        ],
        backend=backend,
        store=store
    )
    
    return agent


# ============================================================================
# 3. API 集成示例
# ============================================================================

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import json

router = APIRouter(prefix="/api/v2", tags=["deepagents"])

# 全局 Store 实例
from tableau_assistant.src.components.persistent_store import PersistentStore
store = PersistentStore(db_path="data/deepagents_store.db")


@router.post("/chat")
async def chat_sync(
    question: str,
    datasource_luid: str,
    user_id: str = "default_user",
    session_id: str = "default_session"
):
    """
    同步查询端点（使用 DeepAgents）
    """
    # 创建 Agent
    agent = create_tableau_deep_agent(store=store.store)
    
    # 准备输入
    input_data = {
        "question": question
    }
    
    # 准备配置
    config = {
        "configurable": {
            "thread_id": session_id,
            "datasource_luid": datasource_luid,
            "user_id": user_id
        }
    }
    
    # 执行
    try:
        result = agent.invoke(input_data, config=config)
        
        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(
    question: str,
    datasource_luid: str,
    user_id: str = "default_user",
    session_id: str = "default_session"
):
    """
    流式查询端点（使用 DeepAgents）
    """
    # 创建 Agent
    agent = create_tableau_deep_agent(store=store.store)
    
    # 准备输入
    input_data = {
        "question": question
    }
    
    # 准备配置
    config = {
        "configurable": {
            "thread_id": session_id,
            "datasource_luid": datasource_luid,
            "user_id": user_id
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


# ============================================================================
# 4. 使用示例
# ============================================================================

if __name__ == "__main__":
    import asyncio
    
    # 创建 Store
    from langgraph.store.memory import InMemoryStore
    store = InMemoryStore()
    
    # 创建 Agent
    agent = create_tableau_deep_agent(store=store)
    
    # 准备输入
    input_data = {
        "question": "2016年各地区的销售额"
    }
    
    # 准备配置
    config = {
        "configurable": {
            "thread_id": "test_session",
            "datasource_luid": "your_datasource_luid",
            "user_id": "test_user"
        }
    }
    
    # 同步执行
    print("=" * 60)
    print("同步执行示例")
    print("=" * 60)
    result = agent.invoke(input_data, config=config)
    print(f"结果: {result}")
    
    # 流式执行
    print("\n" + "=" * 60)
    print("流式执行示例")
    print("=" * 60)
    
    async def stream_example():
        async for event in agent.astream_events(input_data, config=config, version="v2"):
            event_type = event.get("event")
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content"):
                    print(chunk.content, end="", flush=True)
    
    asyncio.run(stream_example())
