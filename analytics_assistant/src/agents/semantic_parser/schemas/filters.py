# -*- coding: utf-8 -*-
"""
Semantic Parser Filter Validation Models

筛选器验证相关模型定义：
- FilterValidationResult: 单个筛选条件的验证结果
- FilterValidationSummary: 所有筛选条件的验证汇总
- FilterConfirmation: 筛选值确认记录（多轮确认累积）
"""
from typing import List, Optional
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FilterValidationType(str, Enum):
    """筛选值验证类型
    
    - EXACT_MATCH: 精确匹配，值存在于字段中
    - FUZZY_MATCH: 模糊匹配，找到相似值
    - NOT_FOUND: 未找到匹配，也没有相似值
    - SKIPPED: 跳过验证（时间字段、高基数字段等）
    - NEEDS_CONFIRMATION: 需要用户确认（有相似值可选）
    """
    EXACT_MATCH = "exact_match"
    FUZZY_MATCH = "fuzzy_match"
    NOT_FOUND = "not_found"
    SKIPPED = "skipped"
    NEEDS_CONFIRMATION = "needs_confirmation"


class FilterValidationResult(BaseModel):
    """单个筛选条件的验证结果
    
    描述单个筛选值的验证状态和候选值。
    
    验证流程：
    1. 检查是否需要验证（时间字段、高基数字段跳过）
    2. 精确匹配：值存在 → is_valid=True
    3. 模糊匹配：找到相似值 → needs_confirmation=True
    4. 无匹配：没有相似值 → is_unresolvable=True
    """
    model_config = ConfigDict(extra="forbid")
    
    is_valid: bool = Field(
        description="验证是否通过"
    )
    field_name: str = Field(
        description="字段名称"
    )
    requested_value: str = Field(
        description="用户请求的筛选值"
    )
    matched_values: List[str] = Field(
        default_factory=list,
        description="匹配到的值列表"
    )
    similar_values: List[str] = Field(
        default_factory=list,
        description="相似的候选值列表（用于澄清）"
    )
    validation_type: FilterValidationType = Field(
        description="验证类型"
    )
    skip_reason: Optional[str] = Field(
        default=None,
        description="跳过验证的原因：time_field / numeric_range / high_cardinality"
    )
    needs_confirmation: bool = Field(
        default=False,
        description="是否需要用户确认（触发 LangGraph interrupt()）"
    )
    is_unresolvable: bool = Field(
        default=False,
        description="是否无法解决（没有相似值可选）"
    )
    message: Optional[str] = Field(
        default=None,
        description="给用户的提示信息"
    )


class FilterValidationSummary(BaseModel):
    """所有筛选条件的验证汇总
    
    汇总所有筛选条件的验证结果，用于决定后续流程：
    - all_valid=True: 继续执行查询
    - has_unresolvable_filters=True: 返回澄清请求（无相似值）
    - 有 needs_confirmation=True 的结果: 触发 interrupt() 等待用户确认
    """
    model_config = ConfigDict(extra="forbid")
    
    results: List[FilterValidationResult] = Field(
        default_factory=list,
        description="每个筛选条件的验证结果"
    )
    all_valid: bool = Field(
        default=True,
        description="所有筛选条件都验证通过"
    )
    has_unresolvable_filters: bool = Field(
        default=False,
        description="是否有无法解决的筛选条件（没有相似值可选）"
    )
    
    @classmethod
    def from_results(cls, results: List[FilterValidationResult]) -> "FilterValidationSummary":
        """从验证结果列表创建汇总"""
        all_valid = all(r.is_valid for r in results)
        has_unresolvable = any(r.is_unresolvable for r in results)
        return cls(
            results=results,
            all_valid=all_valid,
            has_unresolvable_filters=has_unresolvable,
        )


class FilterConfirmation(BaseModel):
    """筛选值确认记录
    
    用于累积多轮筛选值确认的结果，防止上下文丢失。
    
    多轮确认场景：
    1. 第一次确认 "北京" → "北京市"
    2. 第二次确认 "上海" → "上海市"
    两次确认都会保留在 confirmed_filters 列表中。
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="字段名称"
    )
    original_value: str = Field(
        description="用户原始输入的值"
    )
    confirmed_value: str = Field(
        description="用户确认后的值"
    )
    confirmed_at: datetime = Field(
        default_factory=datetime.now,
        description="确认时间"
    )


__all__ = [
    "FilterValidationType",
    "FilterValidationResult",
    "FilterValidationSummary",
    "FilterConfirmation",
]
