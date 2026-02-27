# -*- coding: utf-8 -*-
"""
反馈学习数据模型

包含：
- FeedbackType: 反馈类型枚举
- FeedbackRecord: 反馈记录模型
- SynonymMapping: 同义词映射模型
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

class FeedbackType(str, Enum):
    """反馈类型枚举。
    
    用户对查询结果的反馈类型：
    - ACCEPT: 接受查询结果
    - MODIFY: 修改查询（用户调整了部分内容）
    - REJECT: 拒绝查询结果
    """
    ACCEPT = "accept"
    MODIFY = "modify"
    REJECT = "reject"

class FeedbackRecord(BaseModel):
    """反馈记录模型。
    
    记录用户对查询结果的反馈，用于持续学习和改进。
    
    Attributes:
        id: 反馈记录 ID
        question: 用户原始问题
        restated_question: 重述的问题
        semantic_output: 语义解析输出（SemanticOutput 的字典形式）
        query: 生成的查询语句
        feedback_type: 反馈类型
        modification: 用户修改内容（仅 MODIFY 类型）
        rejection_reason: 拒绝原因（仅 REJECT 类型）
        datasource_luid: 数据源 ID
        user_id: 用户 ID（可选）
        session_id: 会话 ID（可选）
        created_at: 创建时间
    """
    id: str = Field(description="反馈记录 ID")
    question: str = Field(description="用户原始问题")
    restated_question: Optional[str] = Field(
        default=None,
        description="重述的问题"
    )
    semantic_output: Optional[dict[str, Any]] = Field(
        default=None,
        description="语义解析输出"
    )
    query: Optional[str] = Field(
        default=None,
        description="生成的查询语句"
    )
    feedback_type: FeedbackType = Field(description="反馈类型")
    modification: Optional[dict[str, Any]] = Field(
        default=None,
        description="用户修改内容（仅 MODIFY 类型）"
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        description="拒绝原因（仅 REJECT 类型）"
    )
    datasource_luid: str = Field(description="数据源 ID")
    user_id: Optional[str] = Field(
        default=None,
        description="用户 ID"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="会话 ID"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="创建时间"
    )

class SynonymMapping(BaseModel):
    """同义词映射模型。
    
    记录用户确认的术语到字段的映射关系，用于自动学习同义词。
    
    Attributes:
        id: 映射 ID
        original_term: 用户使用的原始术语
        correct_field: 正确的字段名
        datasource_luid: 数据源 ID
        confirmation_count: 确认次数（达到阈值后自动添加到同义词表）
        created_at: 创建时间
        updated_at: 更新时间
    """
    id: str = Field(description="映射 ID")
    original_term: str = Field(description="用户使用的原始术语")
    correct_field: str = Field(description="正确的字段名")
    datasource_luid: str = Field(description="数据源 ID")
    confirmation_count: int = Field(
        default=1,
        description="确认次数"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        description="更新时间"
    )

__all__ = [
    "FeedbackType",
    "FeedbackRecord",
    "SynonymMapping",
]
