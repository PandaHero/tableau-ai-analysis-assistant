# -*- coding: utf-8 -*-
"""
AI 基础设施模块

提供统一的 LLM 和 Embedding 模型管理。
"""

from .model_manager import (
    ModelManager,
    get_model_manager,
    get_embeddings,
    embed_documents_batch,
    ModelType,
    ModelStatus,
    TaskType,
    ModelConfig,
    ModelCreateRequest,
    ModelUpdateRequest,
)

__all__ = [
    "ModelManager",
    "get_model_manager",
    "get_embeddings",
    "embed_documents_batch",
    "ModelType",
    "ModelStatus",
    "TaskType",
    "ModelConfig",
    "ModelCreateRequest",
    "ModelUpdateRequest",
]
