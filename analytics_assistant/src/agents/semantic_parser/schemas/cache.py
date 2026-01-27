# -*- coding: utf-8 -*-
"""
Semantic Parser Cache Models

缓存相关模型定义：
- CachedQuery: 查询缓存条目
- CachedFieldValues: 字段值缓存条目
"""
from typing import List, Dict, Any, Optional
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CachedQuery(BaseModel):
    """查询缓存条目
    
    缓存成功执行的查询，支持精确匹配和语义相似匹配。
    通过 schema_hash 检测数据模型变更，自动失效过期缓存。
    
    缓存失效条件：
    1. TTL 过期（默认 24 小时）
    2. schema_hash 不匹配（数据模型变更）
    3. 手动失效（按数据源批量失效）
    """
    model_config = ConfigDict(extra="forbid")
    
    question: str = Field(
        description="用户原始问题"
    )
    question_hash: str = Field(
        description="问题的 hash 值（用于精确匹配）"
    )
    question_embedding: List[float] = Field(
        description="问题的向量表示（用于语义相似匹配）"
    )
    datasource_luid: str = Field(
        description="数据源 LUID"
    )
    schema_hash: str = Field(
        description="数据模型的 schema hash（用于失效检测）"
    )
    semantic_output: Dict[str, Any] = Field(
        description="语义理解输出（序列化的 SemanticOutput）"
    )
    query: str = Field(
        description="生成的查询语句"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="创建时间"
    )
    expires_at: datetime = Field(
        description="过期时间"
    )
    hit_count: int = Field(
        default=0,
        ge=0,
        description="命中次数统计"
    )


class CachedFieldValues(BaseModel):
    """字段值缓存条目
    
    缓存字段的可能值，用于筛选值验证。
    采用 LRU 淘汰策略，每个字段最多缓存 1000 个值。
    
    预热策略：
    - 只加载维度字段（DIMENSION role）
    - 只加载低基数字段（<500 唯一值）
    - 排除时间类型字段
    """
    model_config = ConfigDict(extra="forbid")
    
    field_name: str = Field(
        description="字段名称"
    )
    datasource_luid: str = Field(
        description="数据源 LUID"
    )
    values: List[str] = Field(
        description="字段值列表（最多 1000 个）"
    )
    cardinality: Optional[int] = Field(
        default=None,
        description="字段基数（唯一值数量）"
    )
    expires_at: datetime = Field(
        description="过期时间"
    )
    cached_at: datetime = Field(
        default_factory=datetime.now,
        description="缓存时间"
    )


__all__ = [
    "CachedQuery",
    "CachedFieldValues",
]
