"""
工作流状态定义

工作流编排层使用的状态类型。
此模块位于 orchestration/workflow/ 因为状态是工作流编排的一部分，
而不是核心领域模型。

架构（依赖方向：orchestration → agents → core）：
- orchestration/workflow/state.py 可以从 agents/ 和 core/ 导入
- agents/ 可以从 core/ 导入
- core/ 没有外部依赖

节点输出（重构后的架构 - 3 个 Agent 节点）：
- SemanticParser Agent（子图）→ SemanticQuery（核心层），query_result
- Insight Agent（子图）→ Insight 列表（渐进累积）
- Replanner Agent（单节点）→ ReplanDecision，parallel_questions

并行执行：
- Replanner 可以生成多个探索问题
- Send() API 分发并行 SemanticParser 执行
- accumulated_insights 使用 merge_insights reducer 自动合并
"""
from __future__ import annotations

from typing import TypedDict, Annotated, List, Dict, Optional, Any
import operator

# LangChain 消息类型用于对话历史
from langchain_core.messages import BaseMessage

# 核心模型（平台无关）
# ⚠️ State 序列化原则：这些类型仅用于类型提示和文档，
# 实际存储时使用 Dict[str, Any]，支持 checkpoint/持久化/回放
from tableau_assistant.src.core.models.enums import IntentType

# 注意：以下导入已移除，State 中不再直接存储 Pydantic 对象
# - SemanticQuery, ExecuteResult, ReplanDecision, MappedQuery, Insight, EnhancedDataProfile
# 这些对象在写入 State 前必须调用 .model_dump() 转为 dict
# 从 State 读取后需要重新构造对象（使用 Model.model_validate(dict)）


# ═══════════════════════════════════════════════════════════════════════════
# 状态字段的自定义 Reducer
# ═══════════════════════════════════════════════════════════════════════════

def merge_insights(existing: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    合并来自并行执行分支的洞察。
    
    此 reducer 与 Annotated[List[Dict[str, Any]], merge_insights] 一起使用，
    在并行分支完成时自动合并洞察。
    
    ⚠️ State 序列化：洞察存储为 dict（Insight.model_dump()），非 Pydantic 对象
    
    去重策略：
    - 使用洞察标题作为唯一标识符
    - 如果发现重复，保留质量分数更高的洞察
    - 保持顺序：现有洞察在前，新洞察在后
    
    Args:
        existing: 当前累积的洞察（dict 列表）
        new: 来自并行分支的新洞察（dict 列表）
        
    Returns:
        合并并去重后的洞察列表（dict 列表）
    """
    if not new:
        return existing
    if not existing:
        return new
    
    # 按标题构建现有洞察索引用于去重
    existing_by_title: Dict[str, Dict[str, Any]] = {}
    for insight in existing:
        # insight 是 dict，直接访问 title 键
        title = insight.get('title', str(insight))
        existing_by_title[title] = insight
    
    # 合并新洞察，处理重复
    result = list(existing)
    for new_insight in new:
        title = new_insight.get('title', str(new_insight))
        
        if title in existing_by_title:
            # 发现重复 - 保留质量分数更高的
            existing_insight = existing_by_title[title]
            existing_score = existing_insight.get('quality_score', 0) or 0
            new_score = new_insight.get('quality_score', 0) or 0
            
            if new_score > existing_score:
                # 用更高质量的洞察替换
                idx = result.index(existing_insight)
                result[idx] = new_insight
                existing_by_title[title] = new_insight
        else:
            # 新的唯一洞察
            result.append(new_insight)
            existing_by_title[title] = new_insight
    
    return result


# ═══════════════════════════════════════════════════════════════════════════
# 状态字段的类型定义
# ═══════════════════════════════════════════════════════════════════════════

class ErrorRecord(TypedDict):
    """错误记录结构"""
    node: str
    error: str
    type: str


class WarningRecord(TypedDict):
    """警告记录结构"""
    node: str
    message: str
    type: str


class ReplanHistoryRecord(TypedDict):
    """重规划历史记录结构"""
    round: int
    decision: str
    reason: str
    questions: List[str]


class PerformanceMetrics(TypedDict, total=False):
    """性能指标结构"""
    start_time: float
    end_time: float
    token_count: int
    llm_calls: int
    vds_calls: int
    total_duration: float


class VisualizationData(TypedDict, total=False):
    """可视化数据结构"""
    type: str
    title: str
    data: List[Dict[str, str]]
    config: Dict[str, str]


class VizQLState(TypedDict):
    """
    VizQL 分析管道的工作流状态。
    
    包含确保工作流完整性和可追溯性所需的所有数据。
    使用 Annotated + operator.add 进行自动累积。
    使用 Annotated + merge_insights 进行并行洞察合并。
    
    架构（重构后 - 3 个 Agent 节点）：
    - SemanticParser Agent（子图）：Step1 → Step2 → MapFields → BuildQuery → Execute
    - Insight Agent（子图）：Profiler → Director → Analyzer（循环）
    - Replanner Agent（单节点）：决定继续/结束，生成并行问题
    
    并行执行：
    - parallel_questions: 用于并行 SemanticParser 执行的问题列表
    - accumulated_insights: 使用 merge_insights reducer 自动合并并去重
    
    注意：
    - 上下文信息（datasource_luid、user_id 等）通过 Runtime 传递
    - 平台特定的查询类型（如 VizQLQuery）存储为 Any
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # 对话历史（用于 LLM 上下文和 SummarizationMiddleware）
    # ═══════════════════════════════════════════════════════════════════════
    messages: Annotated[List[BaseMessage], operator.add]
    answered_questions: Annotated[List[str], operator.add]
    
    # ═══════════════════════════════════════════════════════════════════════
    # 用户输入
    # ═══════════════════════════════════════════════════════════════════════
    question: str
    
    # ═══════════════════════════════════════════════════════════════════════
    # 意图分类（SemanticParser Agent 输出 - 扁平化）
    # ⚠️ State 序列化：intent_type 存储为字符串值（IntentType.value），非枚举对象
    # ═══════════════════════════════════════════════════════════════════════
    is_analysis_question: bool
    intent_type: Optional[str]               # 意图类型（字符串值，如 "DATA_QUERY"）
    intent_reasoning: Optional[str]          # 意图分类推理
    general_response: Optional[str]
    non_analysis_response: Optional[str]
    
    # 澄清字段（从 ClarificationQuestion 扁平化）
    clarification_question: Optional[str]    # 澄清问题文本
    clarification_options: Optional[List[str]]  # 用户可选项
    clarification_field: Optional[str]       # 需要澄清的相关字段
    
    # ═══════════════════════════════════════════════════════════════════════
    # SemanticParser Agent 输出（仅核心层类型）
    # ⚠️ State 序列化：存储为 dict（.model_dump()），非 Pydantic 对象
    # ═══════════════════════════════════════════════════════════════════════
    semantic_query: Optional[Dict[str, Any]]  # SemanticQuery.model_dump()
    restated_question: Optional[str]         # Step 1 重述的问题
    
    # ═══════════════════════════════════════════════════════════════════════
    # QueryPipeline 输出（SemanticParser 子图内部）
    # ⚠️ State 序列化：存储为 dict（.model_dump()），非 Pydantic 对象
    # ═══════════════════════════════════════════════════════════════════════
    mapped_query: Optional[Dict[str, Any]]   # MappedQuery.model_dump()
    vizql_query: Optional[Dict[str, Any]]    # 构建的查询请求（平台特定）
    query_result: Optional[Dict[str, Any]]   # ExecuteResult.model_dump()
    tool_observations: Annotated[List[Dict[str, Any]], operator.add]  # 工具执行观察
    
    # ═══════════════════════════════════════════════════════════════════════
    # Insight Agent 输出（渐进累积）
    # ⚠️ State 序列化：存储为 dict（.model_dump()），非 Pydantic 对象
    # ═══════════════════════════════════════════════════════════════════════
    enhanced_profile: Optional[Dict[str, Any]]  # EnhancedDataProfile.model_dump()
    insights: Annotated[List[Dict[str, Any]], operator.add]  # [Insight.model_dump(), ...]
    all_insights: Annotated[List[Dict[str, Any]], operator.add]
    accumulated_insights: Annotated[List[Dict[str, Any]], merge_insights]  # 并行合并并去重
    
    # ═══════════════════════════════════════════════════════════════════════
    # Replanner Agent 输出（支持并行执行）
    # ⚠️ State 序列化：存储为 dict（.model_dump()），非 Pydantic 对象
    # ═══════════════════════════════════════════════════════════════════════
    replan_decision: Optional[Dict[str, Any]]  # ReplanDecision.model_dump()
    replan_count: int
    max_replan_rounds: int
    replan_history: Annotated[List[ReplanHistoryRecord], operator.add]
    final_report: Optional[Dict[str, str]]
    parallel_questions: List[str]  # 用于并行 SemanticParser 执行的问题
    
    # ═══════════════════════════════════════════════════════════════════════
    # 控制流
    # ═══════════════════════════════════════════════════════════════════════
    current_stage: str
    execution_path: Annotated[List[str], operator.add]
    
    # 节点完成标志（简化 - 仅 3 个 agent 节点）
    semantic_parser_complete: bool
    insight_complete: bool
    replanner_complete: bool
    
    # ═══════════════════════════════════════════════════════════════════════
    # 数据模型（工作流启动时加载）
    # ═══════════════════════════════════════════════════════════════════════
    datasource: Optional[str]
    data_model: Optional[Dict[str, str]]
    dimension_hierarchy: Optional[Dict[str, Dict[str, str]]]
    data_insight_profile: Optional[Dict[str, Any]]
    current_dimensions: List[str]
    pending_questions: List[Dict[str, Any]]
    
    # ═══════════════════════════════════════════════════════════════════════
    # 错误处理
    # ═══════════════════════════════════════════════════════════════════════
    errors: Annotated[List[ErrorRecord], operator.add]
    warnings: Annotated[List[WarningRecord], operator.add]
    
    # ═══════════════════════════════════════════════════════════════════════
    # 性能监控
    # ═══════════════════════════════════════════════════════════════════════
    performance: Optional[PerformanceMetrics]
    
    # ═══════════════════════════════════════════════════════════════════════
    # 可视化数据
    # ═══════════════════════════════════════════════════════════════════════
    visualizations: Annotated[List[VisualizationData], operator.add]


def create_initial_state(
    question: str,
    max_replan_rounds: int = 3,
    datasource: Optional[str] = None,
) -> VizQLState:
    """
    创建初始工作流状态。
    
    Args:
        question: 用户问题
        max_replan_rounds: 最大重规划轮数（默认：3）
        datasource: 数据源名称/LUID
    
    Returns:
        初始化的 VizQLState
    """
    import time
    from langchain_core.messages import HumanMessage
    
    initial_message = HumanMessage(
        content=question,
        additional_kwargs={"source": "user"}
    )
    
    return VizQLState(
        # 对话历史
        messages=[initial_message],
        answered_questions=[],
        
        # 用户输入
        question=question,
        
        # 意图分类（扁平化）
        is_analysis_question=True,
        intent_type=None,
        intent_reasoning=None,
        general_response=None,
        non_analysis_response=None,
        
        # 澄清字段（扁平化）
        clarification_question=None,
        clarification_options=None,
        clarification_field=None,
        
        # SemanticParser 输出（仅核心层类型）
        semantic_query=None,
        restated_question=None,
        
        # QueryPipeline 输出
        mapped_query=None,
        vizql_query=None,
        query_result=None,
        tool_observations=[],
        
        # Insight 输出
        enhanced_profile=None,
        insights=[],
        all_insights=[],
        accumulated_insights=[],
        
        # Replanner 输出
        replan_decision=None,
        replan_count=0,
        max_replan_rounds=max_replan_rounds,
        replan_history=[],
        final_report=None,
        parallel_questions=[],
        
        # 控制流
        current_stage="semantic_parser",
        execution_path=[],
        
        # 节点完成标志（简化 - 仅 3 个 agent 节点）
        semantic_parser_complete=False,
        insight_complete=False,
        replanner_complete=False,
        
        # 数据模型
        datasource=datasource,
        data_model=None,
        dimension_hierarchy=None,
        data_insight_profile=None,
        current_dimensions=[],
        pending_questions=[],
        
        # 错误处理
        errors=[],
        warnings=[],
        
        # 性能监控
        performance={
            "start_time": time.time(),
            "token_count": 0,
            "llm_calls": 0,
            "vds_calls": 0
        },
        
        # 可视化数据
        visualizations=[]
    )


__all__ = [
    # 状态类型
    "VizQLState",
    "create_initial_state",
    # Reducer
    "merge_insights",
    # 辅助类型
    "ErrorRecord",
    "WarningRecord",
    "ReplanHistoryRecord",
    "PerformanceMetrics",
    "VisualizationData",
]
