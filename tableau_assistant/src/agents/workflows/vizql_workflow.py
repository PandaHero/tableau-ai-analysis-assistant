"""
VizQL主工作流

使用LangGraph 1.0的完整特性：
- context_schema: 运行时上下文
- input_schema: 输入验证
- output_schema: 输出验证
- Store: 持久化存储（SQLite）
- astream_events: 流式输出
- DeepAgent: 集成工具调用
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from typing import Dict, Any, Optional, Callable

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState, VizQLInput, VizQLOutput
from tableau_assistant.src.capabilities.storage.persistent_store import PersistentStore


def create_vizql_workflow(
    store: Optional[PersistentStore] = None,
    db_path: str = "data/langgraph_store.db"
):
    """
    创建VizQL主工作流
    
    工作流程（6个节点）：
    1. (可选) Boost Agent - 优化问题
    2. Understanding Agent - 理解用户意图
    3. Planning Agent - 生成查询计划
    4. Execute Node - 执行查询（纯执行，非Agent）
    5. Insight Agent - 分析结果
    6. Replanner Agent - 决定是否重规划
    
    Args:
        store: 可选的Store实例，如果不提供则创建新的PersistentStore
        db_path: 数据库文件路径（仅在store=None时使用）
    
    Returns:
        编译后的工作流应用
    """
    from tableau_assistant.src.agents.nodes.question_boost import question_boost_agent_node
    from tableau_assistant.src.agents.nodes.understanding import understanding_agent_node
    from tableau_assistant.src.agents.nodes.task_planner import query_planner_agent_node
    from tableau_assistant.src.agents.nodes.insight import insight_agent_node
    from tableau_assistant.src.agents.nodes.replanner import replanner_agent_node
    # Execute 是纯执行节点，不是 Agent，从 capabilities 导入
    from tableau_assistant.src.capabilities.query.executor.execute_node import execute_query_node
    from tableau_assistant.src.capabilities.metadata.manager import MetadataManager
    
    # ========== 1. 创建Store（持久化存储） ==========
    if store is None:
        store = PersistentStore(db_path=db_path)
        print(f"✓ 使用持久化存储: {db_path}")
    
    # ========== 2. 创建StateGraph ==========
    graph = StateGraph(
        state_schema=VizQLState,
        context_schema=VizQLContext,
        input_schema=VizQLInput,
        output_schema=VizQLOutput
    )
    
    # ========== 3. 定义节点包装器 ==========
    
    def _create_runtime(config: Optional[Dict] = None):
        """创建 Runtime 实例"""
        from langgraph.runtime import Runtime
        if config is None:
            config = {}
        configurable = config.get("configurable", {})
        context = VizQLContext.from_config(
            datasource_luid=configurable.get("datasource_luid", ""),
            user_id=configurable.get("user_id", "default_user"),
            session_id=configurable.get("session_id", "default_session")
        )
        return Runtime[VizQLContext](store=store, context=context)
    
    # 3.1 Boost 节点 (async)
    async def boost_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """问题Boost节点"""
        runtime = _create_runtime(config)
        metadata_manager = MetadataManager(runtime)
        metadata = metadata_manager.get_metadata(use_cache=True, enhance=True)
        return await question_boost_agent_node(state, runtime, metadata)
    
    # 3.2 Understanding 节点 (async)
    async def understanding_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """问题理解节点"""
        runtime = _create_runtime(config)
        return await understanding_agent_node(state, runtime)
    
    # 3.3 Planning 节点 (async)
    async def planning_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """查询规划节点"""
        runtime = _create_runtime(config)
        metadata_manager = MetadataManager(runtime)
        metadata = metadata_manager.get_metadata(use_cache=True, enhance=True)
        
        from tableau_assistant.src.capabilities.storage.store_manager import StoreManager
        store_manager = StoreManager(runtime.store)
        dimension_hierarchy = store_manager.get_dimension_hierarchy(runtime.context.datasource_luid)
        
        if not dimension_hierarchy:
            from tableau_assistant.src.agents.nodes.dimension_hierarchy import dimension_hierarchy_agent
            hierarchy_state = {"metadata": metadata}
            hierarchy_result = await dimension_hierarchy_agent.execute(hierarchy_state, runtime)
            dimension_hierarchy = hierarchy_result.get("dimension_hierarchy", {})
        
        state_with_metadata = {**state, "metadata": metadata, "dimension_hierarchy": dimension_hierarchy}
        return await query_planner_agent_node(state_with_metadata, runtime)
    
    # 3.4 Execute 节点（纯执行，非Agent，同步）
    def execute_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """查询执行节点（确定性执行，不使用LLM）"""
        return execute_query_node(state, config)
    
    # 3.5 Insight 节点 (async)
    async def insight_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """洞察分析节点"""
        runtime = _create_runtime(config)
        return await insight_agent_node(state, runtime)
    
    # 3.6 Replanner 节点 (async)
    async def replanner_node(state: VizQLState, config=None) -> Dict[str, Any]:
        """重规划决策节点"""
        runtime = _create_runtime(config)
        result = await replanner_agent_node(state, runtime)
        
        # 计算 completeness_score
        replan_decision = result.get("replan_decision", {})
        completeness_score = _calculate_completeness_score(state, replan_decision)
        result["completeness_score"] = completeness_score
        
        return result
    
    # ========== 4. 添加节点到图 ==========
    graph.add_node("boost", boost_node)
    graph.add_node("understanding", understanding_node)
    graph.add_node("planning", planning_node)
    graph.add_node("execute", execute_node)
    graph.add_node("insight", insight_node)
    graph.add_node("replanner", replanner_node)
    
    # ========== 5. 定义路由函数 ==========
    
    def should_boost(state: VizQLState) -> str:
        """决定是否执行问题Boost"""
        boost_question = state.get("boost_question", False)
        return "boost" if boost_question else "understanding"
    
    def should_replan(state: VizQLState) -> str:
        """决定是否重规划"""
        replan_decision = state.get("replan_decision", {})
        should_replan_flag = replan_decision.get("should_replan", False)
        completeness_score = state.get("completeness_score", 1.0)
        
        # 智能终止策略：score >= 0.9 时终止
        if completeness_score >= 0.9:
            return "end"
        
        if should_replan_flag:
            return "planning"  # 重规划时跳过 Understanding，直接到 Planning
        return "end"
    
    # ========== 6. 添加边 ==========
    
    # START -> Boost 或 Understanding
    graph.add_conditional_edges(
        START,
        should_boost,
        {"boost": "boost", "understanding": "understanding"}
    )
    
    # Boost -> Understanding
    graph.add_edge("boost", "understanding")
    
    # Understanding -> Planning
    graph.add_edge("understanding", "planning")
    
    # Planning -> Execute
    graph.add_edge("planning", "execute")
    
    # Execute -> Insight
    graph.add_edge("execute", "insight")
    
    # Insight -> Replanner
    graph.add_edge("insight", "replanner")
    
    # Replanner -> Planning（重规划）或 END
    graph.add_conditional_edges(
        "replanner",
        should_replan,
        {"planning": "planning", "end": END}
    )
    
    # ========== 7. 编译 ==========
    app = graph.compile(
        checkpointer=InMemorySaver(),
        store=store
    )
    
    return app


def _calculate_completeness_score(state: VizQLState, replan_decision: Dict[str, Any]) -> float:
    """
    计算完成度分数
    
    评估维度：
    1. 问题覆盖度 - 用户问题是否被充分回答
    2. 数据完整性 - 查询结果是否完整
    3. 洞察深度 - 洞察是否有价值
    4. 异常处理 - 是否有未处理的错误
    
    Returns:
        0.0-1.0 之间的分数
    """
    # 从 replan_decision 获取 LLM 评估的分数
    llm_score = replan_decision.get("completeness_score", 0.5)
    
    # 数据完整性检查
    subtask_results = state.get("subtask_results", [])
    errors = state.get("errors", [])
    
    data_score = 1.0
    if not subtask_results:
        data_score = 0.0
    elif errors:
        # 有错误时降低分数
        error_ratio = len(errors) / max(len(subtask_results), 1)
        data_score = max(0.0, 1.0 - error_ratio)
    
    # 洞察深度检查
    insights = state.get("insights", [])
    insight_score = min(1.0, len(insights) / 3)  # 至少3个洞察得满分
    
    # 综合评分（加权平均）
    final_score = (
        llm_score * 0.5 +      # LLM 评估权重 50%
        data_score * 0.3 +     # 数据完整性权重 30%
        insight_score * 0.2    # 洞察深度权重 20%
    )
    
    return min(1.0, max(0.0, final_score))


def validate_input(input_data: Dict[str, Any]) -> VizQLInput:
    """验证输入数据并转换为VizQLInput格式"""
    if "question" not in input_data:
        raise ValueError("question字段是必需的")
    
    question = input_data["question"]
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question必须是非空字符串")
    
    boost_question = input_data.get("boost_question", False)
    if not isinstance(boost_question, bool):
        raise ValueError("boost_question必须是布尔值")
    
    return {"question": question, "boost_question": boost_question}


def request_to_input(request) -> VizQLInput:
    """将API请求转换为工作流输入"""
    from tableau_assistant.src.models.api import VizQLQueryRequest
    
    if isinstance(request, VizQLQueryRequest):
        return {"question": request.question, "boost_question": request.boost_question}
    return validate_input(request)


def format_output(state: VizQLState) -> VizQLOutput:
    """格式化输出数据"""
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
    
    Args:
        input_data: 工作流输入（已验证）
        datasource_luid: 数据源LUID
        user_id: 用户ID
        session_id: 会话ID
        store: 可选的Store实例
        db_path: 数据库文件路径
    
    Yields:
        LangGraph原始事件
    """
    from tableau_assistant.src.config.settings import settings
    
    app = create_vizql_workflow(store=store, db_path=db_path)
    
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
    
    Args:
        input_data: 工作流输入（已验证）
        datasource_luid: 数据源LUID
        user_id: 用户ID
        session_id: 会话ID
        store: 可选的Store实例
        db_path: 数据库文件路径
    
    Returns:
        VizQLOutput
    """
    from tableau_assistant.src.config.settings import settings
    
    app = create_vizql_workflow(store=store, db_path=db_path)
    
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
    
    result = app.invoke(input_data, config=config)
    return format_output(result)


if __name__ == "__main__":
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
    
    try:
        validate_input({"boost_question": False})
        print("✗ 应该抛出验证错误")
    except ValueError as e:
        print(f"✓ 正确捕获验证错误: {e}")
