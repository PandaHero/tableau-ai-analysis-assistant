"""
Agent 模块

包含 StateGraph 工作流和各个 Agent 节点的实现。

子模块：
- nodes/: Agent 节点实现
  - understanding.py: 问题理解节点
  - task_planner.py: 任务规划节点
  - insight.py: 洞察生成节点
  - replanner.py: 重规划节点
  - question_boost.py: 问题优化节点
  - dimension_hierarchy.py: 维度层级推断节点
- workflows/: 工作流定义
  - vizql_workflow.py: VizQL 主工作流
  - streaming.py: 流式输出支持
- deep_agent_factory.py: DeepAgent 创建工厂

使用示例：
    from tableau_assistant.src.agents.workflows.vizql_workflow import create_vizql_workflow
    from tableau_assistant.src.agents.nodes.understanding import understanding_agent_node
"""

__all__ = [
    "nodes",
    "workflows",
]
