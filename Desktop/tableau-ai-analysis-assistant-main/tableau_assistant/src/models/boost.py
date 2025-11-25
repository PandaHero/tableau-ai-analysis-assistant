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
        description="是否是数据分析问题"
    )
    original_question: str = Field(
        ...,
        description="原始问题"
    )
    boosted_question: str = Field(
        ...,
        description="优化后的问题"
    )
    changes: List[str] = Field(
        default_factory=list,
        description="具体改动列表"
    )
    reasoning: str = Field(
        ...,
        description="优化理由说明"
    )
    similar_questions: List[str] = Field(
        default_factory=list,
        description="相似历史问题（从Store检索）"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="优化置信度（0-1）"
    )


# ============= 导出 =============

__all__ = [
    "QuestionBoost",
]
