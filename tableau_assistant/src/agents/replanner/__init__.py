"""
Replanner Agent

智能重规划 Agent，支持多问题并行执行（类 Tableau Pulse）。

Design Specification: insight-design.md
- 多问题生成：LLM 直接生成探索问题，不使用模板
- 并行执行：按优先级并行执行多个问题
- 智能停止：基于 completeness_score 决定是否继续
"""

from .prompt import (
    REPLANNER_PROMPT,
    ReplannerPrompt,
)
from .agent import ReplannerAgent

__all__ = [
    "REPLANNER_PROMPT",
    "ReplannerPrompt",
    "ReplannerAgent",
]
