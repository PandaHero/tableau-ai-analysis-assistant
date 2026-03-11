# -*- coding: utf-8 -*-
"""
Core 层 - 平台无关的领域模型和接口

本模块包含：
1. 领域模型 (schemas/) - Field, Filter, Computation 等
2. 接口定义 (interfaces.py) - BasePlatformAdapter, BaseQueryBuilder 等
3. 异常定义 (exceptions.py)

注意：SemanticOutput（语义解析器输出）定义在 core/schemas/semantic_output.py
"""

from analytics_assistant.src.core.exceptions import ValidationError
from analytics_assistant.src.core.interfaces import (
    BasePlatformAdapter,
    BaseQueryBuilder,
    BaseFieldMapper,
)

__all__ = [
    "ValidationError",
    "BasePlatformAdapter",
    "BaseQueryBuilder",
    "BaseFieldMapper",
]
