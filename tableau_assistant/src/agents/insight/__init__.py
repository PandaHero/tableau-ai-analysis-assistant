"""
Insight Agent

LLM Agent that analyzes query results and generates insights.

Architecture (per insight-design.md):
- 双 LLM 协作模式：
  - 主持人 LLM (CoordinatorPrompt): 决定分析顺序、累积洞察、决定早停
  - 分析师 LLM (AnalystPrompt): 分析单个数据块、生成结构化洞察
- AnalysisCoordinator 协调两个 LLM 的协作
- ChunkAnalyzer 封装 LLM 调用

Import Note:
- 只在包级别导入 prompt（无循环依赖）
- node.py 需要单独导入：from tableau_assistant.src.agents.insight.node import ...
- 这样避免循环导入：
  components/analyzer.py → agents/insight/prompt.py → agents/insight/__init__.py
  如果 __init__.py 导入 node.py，node.py 又导入 components，就会循环
"""

from .prompt import (
    # Output Models
    InsightListOutput,
    CoordinatorDecisionOutput,
    # Prompt Classes
    CoordinatorPrompt,
    AnalystPrompt,
    DirectAnalysisPrompt,
    # Prompt Instances
    COORDINATOR_PROMPT,
    ANALYST_PROMPT,
    DIRECT_ANALYSIS_PROMPT,
)

# Components - 洞察分析组件
from .components import (
    # Components
    DataProfiler,
    AnomalyDetector,
    SemanticChunker,
    ChunkAnalyzer,
    InsightAccumulator,
    InsightSynthesizer,
    AnalysisCoordinator,
    StatisticalAnalyzer,
)

# 注意：不在包级别导入 node.py，避免循环导入
# 需要使用 node 时，请直接导入：
# from tableau_assistant.src.agents.insight.node import insight_node, InsightAgent

__all__ = [
    # Output Models
    "InsightListOutput",
    "CoordinatorDecisionOutput",
    # Prompt Classes
    "CoordinatorPrompt",
    "AnalystPrompt",
    "DirectAnalysisPrompt",
    # Prompt Instances
    "COORDINATOR_PROMPT",
    "ANALYST_PROMPT",
    "DIRECT_ANALYSIS_PROMPT",
    # Components
    "DataProfiler",
    "AnomalyDetector",
    "SemanticChunker",
    "ChunkAnalyzer",
    "InsightAccumulator",
    "InsightSynthesizer",
    "AnalysisCoordinator",
    "StatisticalAnalyzer",
]
