"""
重规划 Agent (v2 - 使用 BaseVizQLAgent 架构)

功能：
1. 评估当前分析的完成度
2. 决定是否继续分析
3. 基础下钻决策

设计原则：
- 使用 BaseVizQLAgent 提供的统一架构
- 统一使用流式输出
- AI 做决策，代码做控制
- 使用 Runtime.context 控制重规划次数
- 输出可执行的新问题
"""
from typing import Dict, Any, List, Optional
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.replan_decision import ReplanDecision
from tableau_assistant.src.agents.base_agent import BaseVizQLAgent
from tableau_assistant.prompts.replanner import REPLANNER_PROMPT


class ReplannerAgent(BaseVizQLAgent):
    """
    Replanner Agent using BaseVizQLAgent architecture
    
    Evaluates analysis completeness and decides whether to:
    - Continue with more analysis (replan)
    - End the analysis workflow
    - Generate new questions for deeper analysis
    """
    
    def __init__(self):
        """Initialize with Replanner Prompt"""
        super().__init__(REPLANNER_PROMPT)
    
    def _prepare_input_data(
        self,
        state: VizQLState,
        max_replan_rounds: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Prepare input data for replanner prompt
        
        Args:
            state: Current VizQL state
            max_replan_rounds: Maximum number of replan rounds
            **kwargs: Additional arguments
        
        Returns:
            Dict with question, insights, replan_count, etc. for prompt
        """
        # 获取用户问题
        question = state.get("question", "")
        
        # 获取洞察结果
        insights = state.get("insights", [])
        
        # 获取重规划次数
        replan_count = state.get("replan_count", 0)
        
        # 格式化洞察
        insights_str = self._format_insights(insights)
        
        return {
            "question": question,
            "insights": insights_str,
            "replan_count": replan_count,
            "max_replan_rounds": max_replan_rounds,
            "chat_history": []  # MVP版本暂不使用对话历史
        }
    
    def _format_insights(self, insights: List[Dict[str, Any]]) -> str:
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
    
    def _process_result(
        self,
        result: ReplanDecision,
        state: VizQLState
    ) -> Dict[str, Any]:
        """
        Process replanner result
        
        Args:
            result: ReplanDecision model instance
            state: Current VizQL state
        
        Returns:
            Dict with replan_decision for state update
        """
        # 转换为字典
        replan_decision = result.model_dump()
        
        # 获取当前重规划次数
        replan_count = state.get("replan_count", 0)
        question = state.get("question", "")
        
        # 决定下一步
        should_replan = replan_decision.get("should_replan", False)
        
        if should_replan:
            # 需要重规划
            new_questions = replan_decision.get("new_questions", [])
            
            return {
                "replan_decision": replan_decision,
                "question": new_questions[0] if new_questions else question,
                "replan_count": replan_count + 1,
                "replan_history": [{
                    "round": replan_count + 1,
                    "reason": replan_decision.get("reason", ""),
                    "new_questions": new_questions,
                    "completeness_score": replan_decision.get("completeness_score", 0.0)
                }],
                "current_stage": "planning"  # 重规划时跳过 Understanding，直接到 Planning
            }
        else:
            # 不需要重规划，进入总结阶段
            return {
                "replan_decision": replan_decision,
                "current_stage": "summarize"
            }


# Create agent instance for easy import
replanner_agent = ReplannerAgent()


async def replanner_agent_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext],
    model_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    重规划 Agent 节点（使用 BaseVizQLAgent 架构）
    
    职责：
    - 评估完成度
    - 决定是否重规划
    - 生成新问题
    
    注意：
    - 使用 BaseVizQLAgent 提供的统一执行流程
    - 支持前端模型配置（model_config）
    - 统一使用流式输出
    - 使用 AGENT_TEMPERATURE_CONFIG 中的 ReplannerAgent 配置
    
    Args:
        state: 当前状态
        runtime: 运行时上下文
        model_config: 可选的模型配置（来自前端）
            - provider: "local", "azure", or "openai"
            - model_name: 模型名称
            - temperature: 温度设置
    
    Returns:
        状态更新（包含 replan_decision 字段）
    """
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
    
    # 获取最大重规划次数（从 Runtime.context）
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
    
    try:
        return await replanner_agent.execute(
            state=state,
            runtime=runtime,
            max_replan_rounds=max_replan_rounds,
            model_config=model_config
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"重规划决策失败: {e}")
        
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


# ============= 导出 =============

__all__ = [
    "ReplannerAgent",
    "replanner_agent",
    "replanner_agent_node",
]
