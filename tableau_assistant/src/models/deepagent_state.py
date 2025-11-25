"""DeepAgent 状态模型

定义 DeepAgent 使用的状态结构，兼容现有的数据模型。

注意：
- 这是用于 DeepAgent 框架的状态模型
- 与现有的 VizQLState (state.py) 是并行的两套系统
- 用于渐进式迁移：先搭建 DeepAgent 框架，再逐步迁移功能
- 详见 README_MODELS.md
"""
from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator

class DeepAgentState(TypedDict):
    """DeepAgent 主状态定义
    
    这个状态在整个分析流程中传递，包含所有必要的信息。
    使用 TypedDict 确保类型安全，同时保持与 LangGraph 的兼容性。
    """
    
    # === 用户输入 ===
    question: str  # 用户原始问题
    boost_question: bool  # 是否需要问题优化
    
    # === Agent 输出（按执行顺序） ===
    boosted_question: Optional[str]  # 优化后的问题
    understanding: Optional[Dict[str, Any]]  # 问题理解结果
    query_plan: Optional[Dict[str, Any]]  # 查询计划
    query_results: Annotated[List[Dict[str, Any]], operator.add]  # 查询结果（累积）
    insights: Annotated[List[Dict[str, Any]], operator.add]  # 洞察列表（累积）
    replan_decision: Optional[Dict[str, Any]]  # 重规划决策
    final_report: Optional[Dict[str, Any]]  # 最终报告
    
    # === 控制流程 ===
    current_round: int  # 当前轮次
    max_rounds: int  # 最大轮次
    needs_replan: bool  # 是否需要重规划
    
    # === 元数据 ===
    datasource_luid: str  # 数据源 LUID
    thread_id: str  # 会话 ID
    user_id: str  # 用户 ID
    
    # === 性能监控 ===
    start_time: float  # 开始时间
    performance_metrics: Dict[str, Any]  # 性能指标


def create_initial_state(
    question: str,
    datasource_luid: str,
    thread_id: str,
    user_id: str,
    boost_question: bool = False,
    max_rounds: int = 3
) -> DeepAgentState:
    """创建初始状态
    
    Args:
        question: 用户问题
        datasource_luid: 数据源 LUID
        thread_id: 会话 ID
        user_id: 用户 ID
        boost_question: 是否需要问题优化
        max_rounds: 最大轮次
    
    Returns:
        初始化的 DeepAgentState
    """
    import time
    
    return DeepAgentState(
        # 用户输入
        question=question,
        boost_question=boost_question,
        
        # Agent 输出（初始为空）
        boosted_question=None,
        understanding=None,
        query_plan=None,
        query_results=[],
        insights=[],
        replan_decision=None,
        final_report=None,
        
        # 控制流程
        current_round=0,
        max_rounds=max_rounds,
        needs_replan=False,
        
        # 元数据
        datasource_luid=datasource_luid,
        thread_id=thread_id,
        user_id=user_id,
        
        # 性能监控
        start_time=time.time(),
        performance_metrics={}
    )
