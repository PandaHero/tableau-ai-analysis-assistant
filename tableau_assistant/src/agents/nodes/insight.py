"""
洞察Agent (v2 - 使用 BaseVizQLAgent 架构)

功能：
1. 分析查询结果
2. 生成基础洞察（对比、趋势、排名、组成）
3. 描述性统计

设计原则：
- 使用 BaseVizQLAgent 提供的统一架构
- 统一使用流式输出
- AI 做分析，代码做计算
- 输出可操作的洞察
"""
from typing import Dict, Any, List, Optional
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.insight_result import InsightResult
from tableau_assistant.src.agents.base_agent import BaseVizQLAgent
from tableau_assistant.prompts.insight import INSIGHT_PROMPT


class InsightAgent(BaseVizQLAgent):
    """
    Insight Agent using BaseVizQLAgent architecture
    
    Analyzes query results to:
    - Generate insights (comparison, trend, ranking, composition)
    - Provide actionable recommendations
    - Identify key findings
    """
    
    def __init__(self):
        """Initialize with Insight Prompt"""
        super().__init__(INSIGHT_PROMPT)
    
    def _prepare_input_data(
        self,
        state: VizQLState,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Prepare input data for insight prompt
        
        Args:
            state: Current VizQL state
            **kwargs: Additional arguments
        
        Returns:
            Dict with query_results, statistics, and question for prompt
        """
        import json
        
        # 获取查询结果
        subtask_results = state.get("subtask_results", [])
        
        # 获取用户问题
        question = state.get("question", "")
        
        # 获取统计分析结果（如果有）
        statistics = state.get("statistics", {})
        
        # 格式化查询结果
        query_results_str = self._format_query_results(subtask_results)
        statistics_str = json.dumps(statistics, ensure_ascii=False, indent=2) if statistics else "{}"
        
        return {
            "query_results": query_results_str,
            "statistics": statistics_str,
            "question": question
        }
    
    def _format_query_results(self, subtask_results: List[Dict[str, Any]]) -> str:
        """
        格式化查询结果为可读文本
        
        Args:
            subtask_results: 子任务结果列表
        
        Returns:
            格式化的文本
        """
        if not subtask_results:
            return "(无查询结果)"
        
        formatted_parts = []
        
        for i, result in enumerate(subtask_results, 1):
            question_id = result.get("question_id", f"q{i}")
            question_text = result.get("question_text", "")
            data = result.get("data", [])
            
            formatted_parts.append(f"## 查询 {question_id}: {question_text}")
            formatted_parts.append("")
            
            if data:
                # 格式化为表格
                if len(data) > 0:
                    # 获取列名
                    columns = list(data[0].keys())
                    
                    # 表头
                    header = " | ".join(columns)
                    separator = " | ".join(["-" * len(col) for col in columns])
                    formatted_parts.append(header)
                    formatted_parts.append(separator)
                    
                    # 数据行（最多显示10行）
                    for row in data[:10]:
                        row_str = " | ".join([str(row.get(col, "")) for col in columns])
                        formatted_parts.append(row_str)
                    
                    if len(data) > 10:
                        formatted_parts.append(f"... (共{len(data)}行)")
            else:
                formatted_parts.append("(无数据)")
            
            formatted_parts.append("")
        
        return "\n".join(formatted_parts)
    
    def _process_result(
        self,
        result: InsightResult,
        state: VizQLState
    ) -> Dict[str, Any]:
        """
        Process insight result
        
        Args:
            result: InsightResult model instance
            state: Current VizQL state
        
        Returns:
            Dict with insights for state update
        """
        # 转换为字典
        insight_dict = result.model_dump()
        
        # 提取洞察列表
        insights = insight_dict.get("insights", [])
        
        # 添加元信息
        for insight in insights:
            insight["source"] = "insight_agent"
            insight["round"] = state.get("replan_count", 0) + 1
        
        return {
            "insights": insights,
            "all_insights": insights,  # 用于动态规划
            "current_stage": "replan"
        }


# Create agent instance for easy import
insight_agent = InsightAgent()


async def insight_agent_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext],
    model_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    洞察 Agent 节点（使用 BaseVizQLAgent 架构）
    
    职责：
    - 分析查询结果
    - 生成基础洞察
    - 提供可操作建议
    
    注意：
    - 使用 BaseVizQLAgent 提供的统一执行流程
    - 支持前端模型配置（model_config）
    - 统一使用流式输出
    - 使用 AGENT_TEMPERATURE_CONFIG 中的 InsightAgent 配置
    
    Args:
        state: 当前状态
        runtime: 运行时上下文
        model_config: 可选的模型配置（来自前端）
            - provider: "local", "azure", or "openai"
            - model_name: 模型名称
            - temperature: 温度设置
    
    Returns:
        状态更新（包含 insights 字段）
    """
    # 检查是否有查询结果
    subtask_results = state.get("subtask_results", [])
    if not subtask_results:
        return {
            "insights": [],
            "warnings": [{
                "type": "no_data",
                "message": "没有查询结果可供分析"
            }],
            "current_stage": "replan"
        }
    
    try:
        return await insight_agent.execute(
            state=state,
            runtime=runtime,
            model_config=model_config
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"洞察生成失败: {e}")
        
        return {
            "insights": [],
            "errors": [{
                "type": "insight_generation_failed",
                "message": f"洞察生成失败: {str(e)}"
            }],
            "current_stage": "replan"
        }


# ============= 导出 =============

__all__ = [
    "InsightAgent",
    "insight_agent",
    "insight_agent_node",
]
