"""
Agent 模块

包含 Agent 节点的实现，使用统一的 base 包提供基础能力。

架构：
- base/: 基础能力（LLM 调用、工具处理、Prompt 模板）
- understanding/: 问题理解 Agent（含原 Boost 功能）
- dimension_hierarchy/: 维度层级推断 Agent
- field_mapper/: 字段映射 Agent（RAG + LLM 混合）
- insight/: 洞察生成 Agent（Prompt 定义）
- replanner/: 重规划 Agent（多问题并行执行）

工作流定义在 src/workflow/ 目录：
- factory.py: 创建工作流
- routes.py: 路由逻辑

使用示例：
    from tableau_assistant.src.agents.understanding import understanding_node
    from tableau_assistant.src.agents.dimension_hierarchy import dimension_hierarchy_node
    from tableau_assistant.src.agents.field_mapper import field_mapper_node
    from tableau_assistant.src.agents.replanner import ReplannerAgent
    from tableau_assistant.src.workflow.factory import create_tableau_workflow
"""

# 导出主要 Agent 节点
from .understanding import understanding_node
from .dimension_hierarchy import dimension_hierarchy_node
from .field_mapper import field_mapper_node, FieldMapperNode

# 导出 Replanner Agent
from .replanner import ReplannerAgent, REPLANNER_PROMPT

__all__ = [
    "understanding_node",
    "dimension_hierarchy_node",
    "field_mapper_node",
    "FieldMapperNode",
    # Replanner
    "ReplannerAgent",
    "REPLANNER_PROMPT",
]
