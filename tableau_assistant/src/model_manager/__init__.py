"""
模型管理器

统一管理所有 AI 模型的选择、配置和创建。

主要功能：
- LLM 模型管理（select_model）
- Embedding 模型管理（select_embeddings, EmbeddingProvider）
- Reranker 模型管理（select_reranker）
- 模型配置管理（ModelConfig, AgentType）

使用示例：
    from tableau_assistant.src.model_manager import (
        select_model,
        select_embeddings,
        select_reranker,
        ModelConfig,
        AgentType,
    )
    
    # 选择 LLM
    llm = select_model(provider="deepseek", model_name="deepseek-chat")
    
    # 选择 Embedding
    embeddings = select_embeddings(provider="zhipu", model_name="embedding-2")
    
    # 选择 Reranker
    reranker = select_reranker(reranker_type="cross_encoder")
"""

# LLM 模型管理
from tableau_assistant.src.model_manager.llm import (
    select_model,
    SUPPORTED_LLM_PROVIDERS,
)

# Embedding 模型管理
from tableau_assistant.src.model_manager.embeddings import (
    select_embeddings,
    EmbeddingProvider,
    ZhipuEmbedding,
    OpenAIEmbedding,
    MockEmbedding,
    EmbeddingProviderFactory,
    SUPPORTED_EMBEDDING_PROVIDERS,
)

# Reranker 模型管理
from tableau_assistant.src.model_manager.reranker import (
    select_reranker,
    SUPPORTED_RERANKER_TYPES,
)

# 模型配置
from tableau_assistant.src.model_manager.config import (
    AgentType,
    ModelConfig,
)

__all__ = [
    # LLM
    "select_model",
    "SUPPORTED_LLM_PROVIDERS",
    # Embedding
    "select_embeddings",
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "OpenAIEmbedding",
    "MockEmbedding",
    "EmbeddingProviderFactory",
    "SUPPORTED_EMBEDDING_PROVIDERS",
    # Reranker
    "select_reranker",
    "SUPPORTED_RERANKER_TYPES",
    # Config
    "AgentType",
    "ModelConfig",
]
