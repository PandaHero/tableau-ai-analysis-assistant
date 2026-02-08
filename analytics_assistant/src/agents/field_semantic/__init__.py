# -*- coding: utf-8 -*-
"""
字段语义增强服务

支持维度和度量字段的统一语义分析，生成增强的索引文本以改进 RAG 检索效果。

主要功能：
- 统一推断维度和度量字段的语义属性
- 生成业务描述和别名
- 构建增强的索引文本
- 支持增量推断和自学习

使用示例：
    from analytics_assistant.src.agents.field_semantic import (
        FieldSemanticInference,
        infer_field_semantic,
    )
    
    # 方式 1：使用便捷函数
    result = await infer_field_semantic(datasource_luid, fields)
    
    # 方式 2：使用推断类
    inference = FieldSemanticInference()
    result = await inference.infer(datasource_luid, fields)
"""
from .inference import (
    FieldSemanticInference,
    FieldSemanticResult,
    FieldSemanticAttributes,
    infer_field_semantic,
    build_enhanced_index_text,
)
from .schemas import (
    FieldSemanticAttributes,
    FieldSemanticResult,
    LLMFieldSemanticOutput,
)
from analytics_assistant.src.core.schemas.enums import (
    DimensionCategory,
    MeasureCategory,
)

__all__ = [
    # 推断服务
    "FieldSemanticInference",
    "infer_field_semantic",
    "build_enhanced_index_text",
    # 数据模型
    "FieldSemanticAttributes",
    "FieldSemanticResult",
    "LLMFieldSemanticOutput",
    # 枚举
    "DimensionCategory",
    "MeasureCategory",
]
