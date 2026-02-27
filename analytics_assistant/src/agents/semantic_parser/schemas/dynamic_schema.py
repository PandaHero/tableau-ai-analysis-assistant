# -*- coding: utf-8 -*-
"""
动态 Schema 构建结果数据模型

从 components/dynamic_schema_builder.py 迁移到 schemas/ 目录，
遵循编码规范 4.1（数据模型放在 schemas/ 目录）。
"""

from pydantic import BaseModel, ConfigDict, Field

from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
from .prefilter import ComplexityType

class DynamicSchemaResult(BaseModel):
    """动态 Schema 构建结果

    包含筛选后的字段列表和裁剪后的 Schema JSON。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    field_candidates: list[FieldCandidate] = Field(default_factory=list)
    """筛选后的字段候选列表（Top-K）"""

    schema_text: str = ""
    """裁剪后的 Schema JSON 字符串（直接传给 PromptBuilder）"""

    modules: set[str] = Field(default_factory=set)
    """选择的模块集合（存储 SchemaModule.value 字符串）"""

    detected_complexity: list[ComplexityType] = Field(default_factory=list)
    """检测到的复杂度类型"""

    allowed_calc_types: list[str] = Field(default_factory=list)
    """允许的 CalcType 枚举值"""

    time_expressions: list[str] = Field(default_factory=list)
    """时间表达式类型（如果包含 TIME 模块）"""

__all__ = ["DynamicSchemaResult"]
