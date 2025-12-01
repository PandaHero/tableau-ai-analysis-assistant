"""
工作流模块

包含 StateGraph 工作流的定义。

工作流：
- vizql_workflow: VizQL 主工作流
  - Boost → Understanding → Planning → Execute → Insight → Replanner
- streaming: 流式输出支持

使用示例：
    from tableau_assistant.src.agents.workflows.vizql_workflow import create_vizql_workflow
    
    workflow = create_vizql_workflow(store)
    result = workflow.invoke(input_data)
"""
from tableau_assistant.src.agents.workflows.vizql_workflow import create_vizql_workflow
from tableau_assistant.src.agents.workflows.streaming import StreamingEventHandler

__all__ = [
    "create_vizql_workflow",
    "StreamingEventHandler",
]
