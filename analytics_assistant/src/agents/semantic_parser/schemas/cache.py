# -*- coding: utf-8 -*-
"""Semantic parser 相关缓存模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class CachedQuery(BaseModel):
    """查询缓存条目。

    用于缓存成功解析后的最终查询结果，并通过 `schema_hash` 与 `scope_key`
    同时保证：
    - 数据模型变化后不会误命中旧缓存
    - 不同租户/站点/用户之间不会串缓存
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(description="用户原始问题")
    question_hash: str = Field(description="问题哈希，用于精确命中")
    question_embedding: Optional[list[float]] = Field(
        default=None,
        description="问题向量，用于语义相似匹配",
    )
    datasource_luid: str = Field(description="数据源 LUID")
    scope_key: str = Field(
        default="global",
        description="query cache 的租户/用户隔离键",
    )
    schema_hash: str = Field(description="当前数据模型的 schema hash")
    parser_version: Optional[str] = Field(
        default=None,
        description="语义解析缓存版本，用于代码升级后的主动失效",
    )
    semantic_output: dict[str, Any] = Field(description="序列化后的语义输出")
    query: Any = Field(description="生成的查询对象，兼容 str / dict / schema")
    analysis_plan: Optional[dict[str, Any]] = Field(
        default=None,
        description="复杂问题的 analysis_plan 快照",
    )
    global_understanding: Optional[dict[str, Any]] = Field(
        default=None,
        description="复杂问题的 global_understanding 快照",
    )
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    expires_at: datetime = Field(description="过期时间")
    hit_count: int = Field(default=0, ge=0, description="命中次数")


class CachedFieldValues(BaseModel):
    """字段值缓存条目。"""

    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(description="字段名称")
    datasource_luid: str = Field(description="数据源 LUID")
    values: list[str] = Field(description="字段值列表")
    cardinality: Optional[int] = Field(
        default=None,
        description="字段基数",
    )
    expires_at: datetime = Field(description="过期时间")
    cached_at: datetime = Field(default_factory=datetime.now, description="缓存时间")


class CachedFeature(BaseModel):
    """特征缓存条目。"""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(description="用户原始问题")
    question_hash: str = Field(description="问题哈希，用于精确命中")
    question_embedding: list[float] = Field(
        default_factory=list,
        description="问题向量，用于语义相似匹配",
    )
    datasource_luid: str = Field(description="数据源 LUID")
    parser_version: Optional[str] = Field(
        default=None,
        description="特征缓存版本",
    )
    feature_output: dict[str, Any] = Field(description="序列化后的特征提取结果")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    expires_at: datetime = Field(description="过期时间")
    hit_count: int = Field(default=0, ge=0, description="命中次数")


__all__ = [
    "CachedQuery",
    "CachedFeature",
    "CachedFieldValues",
]
