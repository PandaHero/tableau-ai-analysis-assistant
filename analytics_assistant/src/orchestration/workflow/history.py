# -*- coding: utf-8 -*-
"""
对话历史管理封装

封装 HistoryManager 的使用，供 API 层通过编排层间接调用，
避免 API 层直接导入 agents/ 模块（违反依赖方向）。
"""
from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
    HistoryManager,
    get_history_manager,
)

__all__ = [
    "HistoryManager",
    "get_history_manager",
]
