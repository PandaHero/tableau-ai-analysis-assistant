# -*- coding: utf-8 -*-
"""
Replanner Agent 输出数据模型

定义重规划决策相关的 Pydantic 模型。
"""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

class ReplanDecision(BaseModel):
    """重规划决策。"""

    model_config = ConfigDict(extra="forbid")

    should_replan: bool = Field(description="是否需要重规划")
    reason: str = Field(description="决策原因")
    new_question: Optional[str] = Field(
        default=None,
        description="新问题（自然语言，should_replan=True 时非空）",
    )
    suggested_questions: list[str] = Field(
        default_factory=list,
        description="建议问题列表",
    )

    @model_validator(mode="after")
    def validate_consistency(self) -> "ReplanDecision":
        """验证 should_replan 与 new_question/suggested_questions 的一致性。"""
        if self.should_replan and not self.new_question:
            raise ValueError(
                "should_replan=True 时 new_question 不能为空"
            )
        if not self.should_replan and not self.suggested_questions:
            raise ValueError(
                "should_replan=False 时 suggested_questions 不能为空"
            )
        return self
