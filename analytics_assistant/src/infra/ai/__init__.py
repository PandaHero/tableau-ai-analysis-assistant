# -*- coding: utf-8 -*-
"""
AI 基础设施模块

提供统一的 LLM 和 Embedding 模型管理。

模块结构（重构后）：
- models.py: 数据模型和枚举类型
- model_registry.py: 模型配置 CRUD 操作
- model_factory.py: 模型实例创建
- model_router.py: 任务路由
- model_persistence.py: 配置持久化
- model_manager.py: 门面类，组合上述模块
"""

# 数据模型（从 models.py 导入）
from .models import (
    EmbeddingResult,
    ModelType,
    ModelStatus,
    TaskType,
    AuthType,
    ModelConfig,
    ModelCreateRequest,
    ModelUpdateRequest,
)

# 拆分后的模块
from .model_registry import ModelRegistry
from .model_factory import ModelFactory
from .model_router import TaskRouter
from .model_persistence import ModelPersistence

# 门面类和便捷函数（保持向后兼容）
from .model_manager import (
    ModelManager,
    get_model_manager,
    get_embeddings,
    embed_documents_batch,
)

__all__ = [
    # 数据模型
    "EmbeddingResult",
    "ModelType",
    "ModelStatus",
    "TaskType",
    "AuthType",
    "ModelConfig",
    "ModelCreateRequest",
    "ModelUpdateRequest",
    # 拆分后的模块
    "ModelRegistry",
    "ModelFactory",
    "TaskRouter",
    "ModelPersistence",
    # 门面类和便捷函数
    "ModelManager",
    "get_model_manager",
    "get_embeddings",
    "embed_documents_batch",
]
