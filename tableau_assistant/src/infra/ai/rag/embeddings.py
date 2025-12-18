"""
Embedding 提供者

推荐使用：
    from tableau_assistant.src.infra.ai import (
        EmbeddingProvider,
        ZhipuEmbedding,
        EmbeddingProviderFactory,
    )
"""

# 从 infra/ai 导入并重新导出
from tableau_assistant.src.infra.ai.embeddings import (
    EmbeddingProvider,
    ZhipuEmbedding,
    EmbeddingProviderFactory,
)

# EmbeddingResult 从 models.py 导入
from tableau_assistant.src.infra.ai.rag.models import EmbeddingResult


__all__ = [
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "EmbeddingProviderFactory",
    "EmbeddingResult",
]
