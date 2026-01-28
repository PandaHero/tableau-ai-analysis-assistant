# -*- coding: utf-8 -*-
"""
IntentRouter 数据模型

意图识别相关的枚举和输出模型。
"""

from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """意图类型枚举（简化版）。
    
    - DATA_QUERY: 数据分析问题（进入语义解析流程）
    - GENERAL: 元数据问答（直接返回字段/数据源信息）
    - IRRELEVANT: 无关问题（礼貌拒绝）
    """
    DATA_QUERY = "DATA_QUERY"
    GENERAL = "GENERAL"
    IRRELEVANT = "IRRELEVANT"


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
