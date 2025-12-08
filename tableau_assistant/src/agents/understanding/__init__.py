"""
Understanding Agent - 问题理解 Agent（含原 Boost 功能）

职责：
- 问题分类：判断是否为分析类问题（is_analysis_question）
- 元数据获取：调用 get_metadata 工具获取字段信息（原 Boost 功能）
- 语义理解：理解用户问题的语义
- 输出 SemanticQuery：纯语义，无 VizQL 概念

设计规范：遵循 `prompt-and-schema-design.md` 中定义的设计规范
"""

from .node import understanding_node
from .prompt import UnderstandingPrompt, UNDERSTANDING_PROMPT

__all__ = [
    "understanding_node",
    "UnderstandingPrompt",
    "UNDERSTANDING_PROMPT",
]
