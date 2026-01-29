# -*- coding: utf-8 -*-
"""
IntentRouter 数据模型

意图识别相关的输出模型。
IntentType 枚举从 core/schemas/enums.py 导入。
"""

from pydantic import BaseModel, Field

from analytics_assistant.src.core.schemas.enums import IntentType


class IntentRouterOutput(BaseModel):
    """IntentRouter 输出模型。
    
    Attributes:
        intent_type: 识别的意图类型
        confidence: 置信度（0-1）
        reason: 识别原因说明
        source: 识别来源（L0_RULES / L1_CLASSIFIER / L2_FALLBACK）
    """
    intent_type: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    source: str = Field(description="识别来源：L0_RULES / L1_CLASSIFIER / L2_FALLBACK")


__all__ = [
    "IntentType",
    "IntentRouterOutput",
]
