"""
维度层级推断 Agent

功能：
- 根据字段元数据推断维度层级
- 识别维度的 category、level、granularity
- 识别父子关系
"""
from .node import dimension_hierarchy_node

__all__ = ["dimension_hierarchy_node"]
