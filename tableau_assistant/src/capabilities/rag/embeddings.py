"""
Embedding 提供者（向后兼容）

此模块已迁移到 tableau_assistant.src.model_manager.embeddings
保留此文件以保持向后兼容性。

推荐使用：
    from tableau_assistant.src.model_manager import (
        EmbeddingProvider,
        ZhipuEmbedding,
        MockEmbedding,
        EmbeddingProviderFactory,
    )
"""

# 从新位置导入并重新导出
from tableau_assistant.src.model_manager.embeddings import (
    EmbeddingProvider,
    ZhipuEmbedding,
    MockEmbedding,
    EmbeddingProviderFactory,
)

# EmbeddingResult 从 models.py 导入
from tableau_assistant.src.capabilities.rag.models import EmbeddingResult


__all__ = [
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "MockEmbedding",
    "EmbeddingProviderFactory",
    "EmbeddingResult",
]
