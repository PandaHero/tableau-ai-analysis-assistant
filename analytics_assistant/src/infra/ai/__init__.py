# -*- coding: utf-8 -*-
"""
AI 基础设施模块

提供统一的 LLM 和 Embedding 模型管理。
"""

from .model_manager import (
    ModelManager,
    get_model_manager,
    ModelType,
    ModelStatus,
    TaskType,
    ModelConfig,
    ModelCreateRequest,
    ModelUpdateRequest,
)
from .embeddings_wrapper import get_embeddings

__all__ = [
    "ModelManager",
    "get_model_manager",
    "ModelType",
    "ModelStatus",
    "TaskType",
    "ModelConfig",
    "ModelCreateRequest",
    "ModelUpdateRequest",
    "get_embeddings",
]
