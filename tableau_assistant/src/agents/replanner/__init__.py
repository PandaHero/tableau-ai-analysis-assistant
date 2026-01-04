"""
Replanner Agent

智能重规划 Agent，支持多问题并行执行（类 Tableau Pulse）。

Design Specification: insight-design.md
- 多问题生成：LLM 直接生成探索问题，不使用模板
- 并行执行：按优先级并行执行多个问题
- 智能停止：基于 completeness_score 决定是否继续
"""

# Models first (no dependencies on other modules in this package)
from .models import (
    ExplorationQuestion,
    ReplanDecision,
)

# Then prompts (depends on models)
from .prompts import (
    REPLANNER_PROMPT,
    ReplannerPrompt,
)

# Then agent (depends on models and prompts)
from .agent import ReplannerAgent

__all__ = [
    # Models
    "ExplorationQuestion",
    "ReplanDecision",
    # Prompt
    "REPLANNER_PROMPT",
    "ReplannerPrompt",
    # Agent
    "ReplannerAgent",
]
