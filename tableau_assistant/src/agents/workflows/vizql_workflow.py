"""
VizQL主工作流

使用LangGraph 1.0的完整特性：
- context_schema: 运行时上下文
- input_schema: 输入验证
- output_schema: 输出验证
- Store: 持久化存储（SQLite）
- astream_events: 流式输出
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from typing import Dict, Any, Optional

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState, VizQLInput, VizQLOutput
from tableau_assistant.src.capabilities.storage.persistent_store import PersistentStore


def create_vizql_workflow(store: Optional[PersistentStore] = None, db_path: str = "data/langgraph_store.db"):
    """
    创建VizQL主工作流
    
    工作流程：
    1. (可选) 问题Boost Agent - 优化问题
    2. 问题理解Agent - 理解用户意图
    3. 查询规划Agent - 生成查询计划
    4. 任务调度器 - 并行执行查询
    5. 洞察Agent - 分析结果
    6. 重规划Agent - 决定是否重规划
    7. 总结Agent - 生成最终报告
    
    Args:
        store: 可选的Store实例，如果不提供则创建新的PersistentStore
        db_path: 数据库文件路径（仅在store=None时使用）
    
    Returns:
        编译后的工作流应用
    """
    from tableau_assistant.src.agents.nodes.question_boost import question_boost_agent_node
    from tableau_assistant.src.agents.nodes.understanding import understanding_agent_node
    from tableau_assistant.src.agents.nodes.task_planner import query_planner_agent_node
    from tableau_assistant.src.capabilities.metadata.manager import MetadataManager
    
    # ========== 1. 创建Store（持久化存储） ==========
    if store is None:
        store = PersistentStore(db_path=db_path)
        print(f"✓ 使用持久化存储: {db_path}")
    
    # ========== 2. 创建StateGraph ==========
    graph = StateGraph(
        state_schema=VizQLState,  # 状态schema
        context_schema=VizQLContext,  # 上下文schema（不可变）
        input_schema=VizQLInput,  # 输入schema（自动验证）
        output_schema=VizQLOutput  # 输出schema（自动验证）
    )
    
    # ========== 3. 添加节点 ==========
    
    # 3.1 问题Boost节点（可选）
    def boost_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """问题Boost节点包装器"""
        from langgraph.runtime import Runtime
        if config is None:
            config = {}
        
        # 从config中提取VizQLContext需要的参数
        configurable = config.get("configurable", {})
        context = VizQLContext.from_config(
            datasource_luid=configurable.get("datasource_luid", ""),
            user_id=configurable.get("user_id", "default_user"),
            session_id=configurable.get("session_id", "default_session")
        )
        runtime = Runtime[VizQLContext](store=store, context=context)
        
        # 获取元数据（启用增强以获取 valid_max_date）
        metadata_manager = MetadataManager(runtime)
        metadata = metadata_manager.get_metadata(use_cache=True, enhance=True)
        
        return question_boost_agent_node(state, runtime, metadata)
    
    # 3.2 问题理解节点
    def understanding_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """问题理解节点包装器"""
        from langgraph.runtime import Runtime
        if config is None:
            config = {}
        
        # 从config中提取VizQLContext需要的参数
        configurable = config.get("configurable", {})
        context = VizQLContext.from_config(
            datasource_luid=configurable.get("datasource_luid", ""),
            user_id=configurable.get("user_id", "default_user"),
            session_id=configurable.get("session_id", "default_session")
        )
        runtime = Runtime[VizQLContext](store=store, context=context)
        return understanding_agent_node(state, runtime)
    
    # 3.3 查询规划节点
    def planning_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """查询规划节点包装器"""
        from langgraph.runtime import Runtime
        if config is None:
            config = {}
        
        # 从config中提取VizQLContext需要的参数
        configurable = config.get("configurable", {})
        context = VizQLContext.from_config(
            datasource_luid=configurable.get("datasource_luid", ""),
            user_id=configurable.get("user_id", "default_user"),
            session_id=configurable.get("session_id", "default_session")
        )
        runtime = Runtime[VizQLContext](store=store, context=context)
        
        # 获取元数据和维度层级（启用增强以获取 valid_max_date）
        metadata_manager = MetadataManager(runtime)
        metadata = metadata_manager.get_metadata(use_cache=True, enhance=True)
        
        from tableau_assistant.src.capabilities.storage.store_manager import StoreManager
        store_manager = StoreManager(runtime.store)
        dimension_hierarchy = store_manager.get_dimension_hierarchy(runtime.context.datasource_luid)
        
        # 如果没有维度层级，使用LLM解析
        if not dimension_hierarchy:
            from tableau_assistant.src.agents.nodes.dimension_hierarchy import dimension_hierarchy_agent
            hierarchy_state = {"metadata": metadata}
            # 移除await，直接同步调用（如果需要异步，整个函数需要改为async def）
            hierarchy_result = dimension_hierarchy_agent.execute(hierarchy_state, runtime)
            dimension_hierarchy = hierarchy_result.get("dimension_hierarchy", {})
        
        # 更新state
        state_with_metadata = {**state, "metadata": metadata, "dimension_hierarchy": dimension_hierarchy}
        return query_planner_agent_node(state_with_metadata, runtime)
    
    # 添加节点到图
    graph.add_node("boost", boost_node)
    graph.add_node("understanding", understanding_node)
    graph.add_node("planning", planning_node)
    
    # ========== 4. 添加边 ==========
    
    # 路由函数：决定是否执行Boost
    def should_boost(state: VizQLState) -> str:
        """决定是否执行问题Boost"""
        boost_question = state.get("boost_question", False)
        if boost_question:
            return "boost"
        else:
            return "understanding"
    
    # 添加条件边
    graph.add_conditional_edges(
        START,
        should_boost,
        {
            "boost": "boost",
            "understanding": "understanding"
        }
    )
    
    # Boost -> Understanding
    graph.add_edge("boost", "understanding")
    
    # Understanding -> Planning
    graph.add_edge("understanding", "planning")
    
    # Planning -> END (暂时，后续添加执行节点)
    graph.add_edge("planning", END)
    
    # ========== 5. 编译 ==========
    app = graph.compile(
        checkpointer=InMemorySaver(),  # 对话历史
        store=store  # 持久化存储
    )
    
    return app


def validate_input(input_data: Dict[str, Any]) -> VizQLInput:
    """
    验证输入数据并转换为VizQLInput格式
    
    注意：
        - 如果从API调用，数据已经通过VizQLQueryRequest验证
        - 如果直接调用工作流，这里提供基本验证
        - 主要用于类型转换和防御性编程
    
    Args:
        input_data: 原始输入数据
    
    Returns:
        验证后的VizQLInput
    
    Raises:
        ValueError: 如果输入格式不正确
    """
    # 验证必需字段
    if "question" not in input_data:
        raise ValueError("question字段是必需的")
    
    question = input_data["question"]
    if not isinstance(question, str):
        raise ValueError("question必须是字符串")
    
    if not question.strip():
        raise ValueError("question不能为空")
    
    # 验证可选字段
    boost_question = input_data.get("boost_question", False)
    if not isinstance(boost_question, bool):
        raise ValueError("boost_question必须是布尔值")
    
    # 构造验证后的输入
    validated: VizQLInput = {
        "question": question,
        "boost_question": boost_question
    }
    
    return validated


def request_to_input(request) -> VizQLInput:
    """
    将API请求转换为工作流输入
    
    这是推荐的方式：API层使用Pydantic验证，然后转换为工作流输入
    
    Args:
        request: VizQLQueryRequest实例（已验证）
    
    Returns:
        VizQLInput
    """
    from tableau_assistant.src.models.api import VizQLQueryRequest
    
    # 如果是Pydantic模型，直接提取字段
    if isinstance(request, VizQLQueryRequest):
        return {
            "question": request.question,
            "boost_question": request.boost_question
        }
    
    # 如果是字典，使用validate_input验证
    return validate_input(request)


def format_output(state: VizQLState) -> VizQLOutput:
    """
    格式化输出数据
    
    将State转换为符合output_schema的格式
    
    Args:
        state: 工作流状态
    
    Returns:
        格式化后的VizQLOutput
    """
    final_report = state.get("final_report", {})
    
    return VizQLOutput(
        final_report=final_report,
        executive_summary=final_report.get("executive_summary", ""),
        key_findings=final_report.get("key_findings", []),
        analysis_path=final_report.get("analysis_path", []),
        recommendations=final_report.get("recommendations", []),
        visualizations=state.get("visualizations", [])
    )


async def run_vizql_workflow_stream(
    input_data: VizQLInput,
    datasource_luid: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
    store: Optional[PersistentStore] = None,
    db_path: str = "data/langgraph_store.db"
):
    """
    运行VizQL工作流（流式输出）
    
    使用astream_events实现Token级流式输出
    
    为什么是异步的？
    - astream_events 是异步生成器（AsyncIterator）
    - 它需要等待 LLM 的每个 token 到达，这是 I/O 密集型操作
    - 使用异步可以在等待时不阻塞其他操作，提高并发效率
    - 前端可以通过 SSE 实时接收 token，提供更好的用户体验
    
    推荐使用方式：
        1. API层使用VizQLQueryRequest验证请求
        2. 使用request_to_input()转换为VizQLInput
        3. 调用此函数执行工作流
        4. 使用StreamingEventHandler处理事件并转换为前端格式
    
    Args:
        input_data: 工作流输入（已验证）
        datasource_luid: 数据源LUID
        user_id: 用户ID
        session_id: 会话ID
        store: 可选的Store实例
        db_path: 数据库文件路径（仅在store=None时使用）
    
    Yields:
        LangGraph原始事件（需要使用StreamingEventHandler转换）
    """
    from tableau_assistant.src.config.settings import settings
    
    # 创建工作流
    app = create_vizql_workflow(store=store, db_path=db_path)
    
    # 准备config（传递context）
    config = {
        "configurable": {
            "thread_id": session_id,
            "datasource_luid": datasource_luid,
            "user_id": user_id,
            "session_id": session_id,
            "max_replan_rounds": settings.max_replan_rounds,
            "parallel_upper_limit": settings.parallel_upper_limit,
            "max_retry_times": settings.max_retry_times,
            "max_subtasks_per_round": settings.max_subtasks_per_round
        }
    }
    
    # 流式执行 - 使用 astream_events 捕获所有事件
    # 包括：on_chat_model_stream (token流), on_chain_start/end (agent进度), 等
    async for event in app.astream_events(input_data, config=config, version="v2"):
        yield event


def run_vizql_workflow_sync(
    input_data: VizQLInput,
    datasource_luid: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
    store: Optional[PersistentStore] = None,
    db_path: str = "data/langgraph_store.db"
) -> VizQLOutput:
    """
    运行VizQL工作流（同步执行）
    
    推荐使用方式：
        1. API层使用VizQLQueryRequest验证请求
        2. 使用request_to_input()转换为VizQLInput
        3. 调用此函数执行工作流
    
    Args:
        input_data: 工作流输入（已验证）
        datasource_luid: 数据源LUID
        user_id: 用户ID
        session_id: 会话ID
        store: 可选的Store实例
        db_path: 数据库文件路径（仅在store=None时使用）
    
    Returns:
        VizQLOutput（自动验证）
    """
    from tableau_assistant.src.config.settings import settings
    
    # 创建工作流
    app = create_vizql_workflow(store=store, db_path=db_path)
    
    # 准备config（传递context）
    config = {
        "configurable": {
            "thread_id": session_id,
            "datasource_luid": datasource_luid,
            "user_id": user_id,
            "session_id": session_id,
            "max_replan_rounds": settings.max_replan_rounds,
            "parallel_upper_limit": settings.parallel_upper_limit,
            "max_retry_times": settings.max_retry_times,
            "max_subtasks_per_round": settings.max_subtasks_per_round
        }
    }
    
    # 同步执行
    result = app.invoke(input_data, config=config)
    
    # 格式化输出（自动验证）
    return format_output(result)


# 示例用法
if __name__ == "__main__":
    import asyncio
    
    # 测试输入验证
    print("=" * 60)
    print("测试输入验证")
    print("=" * 60)
    
    try:
        valid_input = validate_input({
            "question": "2016年各地区的销售额",
            "boost_question": False
        })
        print("✓ 输入验证通过")
        print(f"  问题: {valid_input['question']}")
        print(f"  Boost: {valid_input['boost_question']}")
    except ValueError as e:
        print(f"✗ 输入验证失败: {e}")
    
    # 测试无效输入
    try:
        invalid_input = validate_input({
            "boost_question": False
            # 缺少question字段
        })
        print("✗ 应该抛出验证错误")
    except ValueError as e:
        print(f"✓ 正确捕获验证错误: {e}")
    
    # 测试同步执行（TODO: 需要实现完整工作流）
    # print("\n" + "=" * 60)
    # print("测试同步执行")
    # print("=" * 60)
    # result = run_vizql_workflow_sync(
    #     question="2016年各地区的销售额",
    #     datasource_luid="abc123",
    #     user_id="user_456",
    #     session_id="session_789"
    # )
    # print(f"执行摘要: {result['executive_summary']}")
