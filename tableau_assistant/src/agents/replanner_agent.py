"""
重规划Agent（MVP版本）

功能：
1. 评估当前分析的完成度
2. 决定是否继续分析
3. 基础下钻决策

MVP限制：
- 只支持简单的完成度评估
- 只支持基于贡献度阈值的下钻决策
- 暂不支持交叉分析决策
- 暂不支持异常调查决策

设计原则：
- AI做决策，代码做控制
- 使用Runtime.context控制重规划次数
- 输出可执行的新问题
"""
from typing import Dict, Any
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.replan_decision import ReplanDecision
from tableau_assistant.prompts.replanner import REPLANNER_PROMPT


def replanner_agent_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext]
) -> Dict[str, Any]:
    """
    重规划Agent节点（MVP版本）
    
    职责：
    - 评估完成度
    - 决定是否重规划
    - 生成新问题
    
    MVP限制：
    - 只支持简单的完成度评估
    - 只支持基于贡献度的下钻决策
    
    Args:
        state: 当前状态
        runtime: 运行时上下文
    
    Returns:
        状态更新（包含replan_decision字段）
    """
    # 获取用户问题
    question = state.get("question", "")
    
    # 获取洞察结果
    insights = state.get("insights", [])
    if not insights:
        # 没有洞察，无法评估，直接结束
        return {
            "replan_decision": {
                "should_replan": False,
                "reason": "没有洞察结果，无法评估完成度",
                "completeness_score": 0.0
            },
            "current_stage": "summarize"
        }
    
    # 获取重规划次数
    replan_count = state.get("replan_count", 0)
    
    # 获取最大重规划次数（从Runtime.context）
    max_replan_rounds = runtime.context.max_replan_rounds
    
    # 检查是否已达到最大重规划次数
    if replan_count >= max_replan_rounds:
        return {
            "replan_decision": {
                "should_replan": False,
                "reason": f"已达到最大重规划次数（{max_replan_rounds}）",
                "completeness_score": 1.0  # 强制结束
            },
            "current_stage": "summarize"
        }
    
    # 创建LLM
    from tableau_assistant.src.utils.tableau.models import select_model
    from tableau_assistant.src.config.settings import settings
    
    llm = select_model(
        provider="local",
        model_name=settings.llm_model_provider,
        temperature=0
    )
    
    # 使用with_structured_output（统一方式）
    structured_llm = llm.with_structured_output(ReplanDecision)
    
    # 创建链：prompt | structured_llm
    chain = REPLANNER_PROMPT | structured_llm
    
    # 准备输入数据
    insights_str = _format_insights(insights)
    
    # 执行链
    try:
        replan_result = chain.invoke({
            "question": question,
            "insights": insights_str,
            "replan_count": replan_count,
            "max_replan_rounds": max_replan_rounds,
            "chat_history": []  # MVP版本暂不使用对话历史
        })
        
        # 转换为字典
        replan_decision = replan_result.model_dump()
        
        # 决定下一步
        should_replan = replan_decision.get("should_replan", False)
        
        if should_replan:
            # 需要重规划
            new_questions = replan_decision.get("new_questions", [])
            
            # 更新状态
            return {
                "replan_decision": replan_decision,
                "question": new_questions[0] if new_questions else question,  # 使用第一个新问题
                "replan_count": replan_count + 1,
                "replan_history": [{
                    "round": replan_count + 1,
                    "reason": replan_decision.get("reason", ""),
                    "new_questions": new_questions,
                    "completeness_score": replan_decision.get("completeness_score", 0.0)
                }],
                "current_stage": "understanding"  # 重新开始流程
            }
        else:
            # 不需要重规划，进入总结阶段
            return {
                "replan_decision": replan_decision,
                "current_stage": "summarize"
            }
    
    except Exception as e:
        # 错误处理 - 默认不重规划
        return {
            "replan_decision": {
                "should_replan": False,
                "reason": f"重规划决策失败: {str(e)}",
                "completeness_score": 0.5
            },
            "errors": [{
                "type": "replan_decision_failed",
                "message": f"重规划决策失败: {str(e)}"
            }],
            "current_stage": "summarize"
        }


def _format_insights(insights: list) -> str:
    """
    格式化洞察结果为可读文本
    
    Args:
        insights: 洞察列表
    
    Returns:
        格式化的文本
    """
    if not insights:
        return "(无洞察)"
    
    formatted_parts = []
    
    for i, insight in enumerate(insights, 1):
        title = insight.get("title", "")
        description = insight.get("description", "")
        importance = insight.get("importance", "medium")
        insight_type = insight.get("insight_type", "")
        
        formatted_parts.append(f"{i}. [{importance.upper()}] {title}")
        formatted_parts.append(f"   类型: {insight_type}")
        formatted_parts.append(f"   描述: {description}")
        formatted_parts.append("")
    
    return "\n".join(formatted_parts)


# ============= 导出 =============

__all__ = [
    "replanner_agent_node",
]
