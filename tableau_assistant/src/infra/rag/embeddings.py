"""
Embedding 提供者

从 infra/ai/embeddings.py 导入并重新导出。
"""

# 从 infra/ai 导入并重新导出
from ..ai.embeddings import (
    EmbeddingProvider,
    ZhipuEmbedding,
    EmbeddingProviderFactory,
)

# EmbeddingResult 从 models.py 导入
from .models import EmbeddingResult


__all__ = [
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "EmbeddingProviderFactory",
    "EmbeddingResult",
]
