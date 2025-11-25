"""
洞察Agent（MVP版本）

功能：
1. 分析查询结果
2. 生成基础洞察（对比、趋势、排名、组成）
3. 描述性统计

MVP限制：
- 暂不支持贡献度分析
- 暂不支持异常检测
- 暂不支持趋势分析

设计原则：
- AI做分析，代码做计算
- 使用with_structured_output获取结构化输出
- 输出可操作的洞察
"""
from typing import Dict, Any, List
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.insight_result import InsightResult
from tableau_assistant.prompts.insight import INSIGHT_PROMPT


def insight_agent_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext]
) -> Dict[str, Any]:
    """
    洞察Agent节点（MVP版本）
    
    职责：
    - 分析查询结果
    - 生成基础洞察
    - 提供可操作建议
    
    MVP限制：
    - 只支持基础洞察类型（对比、趋势、排名、组成）
    - 暂不支持复杂统计分析
    
    Args:
        state: 当前状态
        runtime: 运行时上下文
    
    Returns:
        状态更新（包含insights字段）
    """
    # 获取查询结果
    subtask_results = state.get("subtask_results", [])
    if not subtask_results:
        return {
            "insights": [],
            "warnings": [{
                "type": "no_data",
                "message": "没有查询结果可供分析"
            }]
        }
    
    # 获取用户问题
    question = state.get("question", "")
    
    # 获取统计分析结果（如果有）
    statistics = state.get("statistics", {})
    
    # 创建LLM
    from tableau_assistant.src.utils.tableau.models import select_model
    from tableau_assistant.src.config.settings import settings
    
    llm = select_model(
        provider="local",
        model_name=settings.llm_model_provider,
        temperature=0
    )
    
    # 使用with_structured_output（统一方式）
    structured_llm = llm.with_structured_output(InsightResult)
    
    # 创建链：prompt | structured_llm
    chain = INSIGHT_PROMPT | structured_llm
    
    # 准备输入数据
    query_results_str = _format_query_results(subtask_results)
    import json
    statistics_str = json.dumps(statistics, ensure_ascii=False, indent=2) if statistics else "{}"
    
    # 执行链
    try:
        insight_result = chain.invoke({
            "query_results": query_results_str,
            "statistics": statistics_str,
            "question": question
        })
        
        # 转换为字典
        insight_dict = insight_result.model_dump()
        
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
    
    except Exception as e:
        # 错误处理
        return {
            "insights": [],
            "errors": [{
                "type": "insight_generation_failed",
                "message": f"洞察生成失败: {str(e)}"
            }],
            "current_stage": "error"
        }


def _format_query_results(subtask_results: List[Dict[str, Any]]) -> str:
    """
    格式化查询结果为可读文本
    
    Args:
        subtask_results: 子任务结果列表
    
    Returns:
        格式化的文本
    """
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


# ============= 导出 =============

__all__ = [
    "insight_agent_node",
]
