"""
提示词模板模块

使用LangChain的ChatPromptTemplate创建结构化提示词
包含7个Agent的提示词模板和2个规则模板

架构（结构化模板）：
- base.py: 三层架构（BasePrompt → StructuredPrompt → DataAnalysisPrompt/VizQLPrompt）
- 6个标准化部分：ROLE, TASK, CONTEXT, PRINCIPLES, CONSTRAINTS, OUTPUT REQUIREMENTS
- question_boost.py: 使用结构化模板的问题增强 prompt
- understanding.py: 使用结构化模板的问题理解 prompt
- task_planner.py: 使用结构化模板的任务规划 prompt
- dimension_hierarchy.py: 使用结构化模板的维度层级推断 prompt
"""

# 基础架构
from .base import BasePrompt, StructuredPrompt, DataAnalysisPrompt, VizQLPrompt

# 结构化模板
from .question_boost import QuestionBoostPrompt, QUESTION_BOOST_PROMPT
from .understanding import UnderstandingPrompt, UNDERSTANDING_PROMPT
from .task_planner import TaskPlannerPrompt, ProcessingTaskPrompt, TASK_PLANNER_PROMPT, PROCESSING_TASK_PROMPT
from .dimension_hierarchy import DimensionHierarchyPrompt, DIMENSION_HIERARCHY_PROMPT

# 其他提示词
from .insight import INSIGHT_PROMPT
from .replanner import REPLANNER_PROMPT
from .summarizer import SUMMARIZER_PROMPT

__all__ = [
    # 基础架构
    "BasePrompt",
    "StructuredPrompt",
    "DataAnalysisPrompt",
    "VizQLPrompt",
    
    # 结构化模板
    "QuestionBoostPrompt",
    "QUESTION_BOOST_PROMPT",
    "UnderstandingPrompt",
    "UNDERSTANDING_PROMPT",
    "TaskPlannerPrompt",
    "ProcessingTaskPrompt",
    "TASK_PLANNER_PROMPT",
    "PROCESSING_TASK_PROMPT",
    "DimensionHierarchyPrompt",
    "DIMENSION_HIERARCHY_PROMPT",
    
    # 其他提示词
    "INSIGHT_PROMPT",
    "REPLANNER_PROMPT",
    "SUMMARIZER_PROMPT",
]
