# -*- coding: utf-8 -*-
"""FieldSemanticInference 组件模块

将 inference.py 的职责拆分为独立的组件类：
- CacheMixin: 缓存管理（读写、序列化/反序列化）
- SeedMatchMixin: 种子数据精确匹配和初始化
- RAGMixin: RAG 索引初始化、检索匹配、自学习存储
- LLMMixin: LLM 批量推断（维度/度量并行）
"""

from .cache_mixin import CacheMixin
from .seed_match_mixin import SeedMatchMixin
from .rag_mixin import RAGMixin
from .llm_mixin import LLMMixin

__all__ = [
    "CacheMixin",
    "SeedMatchMixin",
    "RAGMixin",
    "LLMMixin",
]
