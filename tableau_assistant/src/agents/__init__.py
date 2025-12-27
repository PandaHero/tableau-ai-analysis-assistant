"""
Agent 模块

包含 Agent 节点的实现，使用统一的 base 包提供基础能力。

架构：
- base/: 基础能力（LLM 调用、工具处理、Prompt 模板）
- semantic_parser/: 语义解析 Agent（LLM 组合：Step1 + Step2 + Observer）
- dimension_hierarchy/: 维度层级推断 Agent
- field_mapper/: 字段映射 Agent（RAG + LLM 混合）
- insight/: 洞察生成 Agent（Prompt 定义）
- replanner/: 重规划 Agent（多问题并行执行）

工作流定义在 src/orchestration/workflow/ 目录：
- factory.py: 创建工作流
- routes.py: 路由逻辑
- state.py: 工作流状态定义

使用示例：
    # Import directly from submodules to avoid circular imports
    from tableau_assistant.src.agents.semantic_parser import semantic_parser_node
    from tableau_assistant.src.agents.dimension_hierarchy import dimension_hierarchy_node
    from tableau_assistant.src.agents.field_mapper import field_mapper_node
    from tableau_assistant.src.agents.replanner import ReplannerAgent
    from tableau_assistant.src.orchestration.workflow.factory import create_workflow

Note:
    This module does NOT re-export agent nodes at the package level.
    This is intentional to avoid circular imports with orchestration/workflow/state.py.
    Always import directly from the specific agent submodule.
"""

# No imports here to avoid circular imports
# Import directly from submodules:
#   from tableau_assistant.src.agents.semantic_parser import semantic_parser_node
#   from tableau_assistant.src.agents.field_mapper import field_mapper_node
#   etc.

__all__: list[str] = []
