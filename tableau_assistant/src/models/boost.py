"""
问题Boost相关的数据模型

包含：
1. QuestionBoost - 问题优化结果
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional


class QuestionBoost(BaseModel):
    """
    问题优化结果
    
    由问题Boost Agent输出，包含优化后的问题和相关建议
    """
    model_config = ConfigDict(extra="forbid")
    
    is_data_analysis_question: bool = Field(
        ...,
        description="""Whether this is a data analysis question.

Usage:
- Set to true for data queries requiring analysis
- Set to false for greetings, help requests, or non-analytical questions

Values: Boolean
- true: Data analysis question
- false: Non-data question"""
    )
    original_question: str = Field(
        ...,
        description="""Original user question (unchanged).

Usage:
- Store the exact original question
- Never modify this field

Values: Original question string"""
    )
    boosted_question: str = Field(
        ...,
        description="""Enhanced question (must be different from original for single metrics).

Usage:
- Enhanced version with added context for incomplete questions
- Must be grammatically correct and fluent
- Must avoid word repetition
- Same as original only if already complete

Values: Enhanced question string
- For single metric: Add aggregation + time + complete question
- For incomplete phrase: Add missing parts + complete question
- For complete question: Keep as is or minimal changes
- For exploratory question: Keep completely unchanged"""
    )
    changes: List[str] = Field(
        default_factory=list,
        description="""List of specific changes made.

Usage:
- Empty list if no changes
- List specific modifications if changed

Values: List of change descriptions
- 'Added aggregation: total'
- 'Added time range: past week'
- 'Formed complete question'
- Empty list if unchanged"""
    )
    reasoning: str = Field(
        ...,
        description="""Explanation of the enhancement decision.

Usage:
- Explain why changed or not changed
- Reference specific analysis steps
- Provide transparency for debugging

Values: Natural language explanation string"""
    )
    similar_questions: List[str] = Field(
        default_factory=list,
        description="""Similar historical questions from Store.

Usage:
- Include when historical questions retrieved
- Empty list if no history or history disabled

Values: List of similar question strings"""
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="""Confidence in the enhancement quality.

Usage:
- Indicate confidence level in the decision

Values: Float between 0 and 1
- 0.9-1.0: Very confident in enhancement
- 0.7-0.9: Confident in enhancement
- 0.5-0.7: Moderate confidence
- 0.0-0.5: Low confidence"""
    )


# ============= 导出 =============

__all__ = [
    "QuestionBoost",
]
