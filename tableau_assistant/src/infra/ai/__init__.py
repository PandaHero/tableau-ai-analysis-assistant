"""
AI 模型管理

统一管理所有 AI 模型的选择、配置和创建。

主要功能：
- LLM 模型管理（get_llm, select_model）
- Embedding 模型管理（select_embeddings, EmbeddingProvider）
- Reranker 模型管理（select_reranker）

使用示例：
    from tableau_assistant.src.infra.ai import (
        get_llm,           # 推荐：自动从环境变量读取配置
        select_model,      # 底层 API：显式指定 provider/model
        select_embeddings,
        select_reranker,
    )
    
    # 推荐方式：自动从环境变量读取配置
    llm = get_llm()
    llm = get_llm(temperature=0.1)  # 指定 temperature
    
    # 底层 API：显式指定
    llm = select_model(provider="deepseek", model_name="deepseek-chat")
    
    # Embedding
    embeddings = select_embeddings(provider="zhipu", model_name="embedding-2")
    
    # Reranker
    reranker = select_reranker(reranker_type="llm")
"""

# LLM 模型管理
from tableau_assistant.src.infra.ai.llm import (
    select_model,
    get_llm,
    SUPPORTED_LLM_PROVIDERS,
)

# DeepSeek R1 推理模型
from tableau_assistant.src.infra.ai.deepseek_r1 import DeepSeekR1Chat

# Embedding 模型管理
from tableau_assistant.src.infra.ai.embeddings import (
    select_embeddings,
    EmbeddingProvider,
    ZhipuEmbedding,
    OpenAIEmbedding,
    EmbeddingProviderFactory,
    SUPPORTED_EMBEDDING_PROVIDERS,
)

# Reranker 模型管理
from tableau_assistant.src.infra.ai.reranker import (
    select_reranker,
    SUPPORTED_RERANKER_TYPES,
)

__all__ = [
    # LLM
    "select_model",
    "get_llm",
    "SUPPORTED_LLM_PROVIDERS",
    "DeepSeekR1Chat",
    # Embedding
    "select_embeddings",
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "OpenAIEmbedding",
    "EmbeddingProviderFactory",
    "SUPPORTED_EMBEDDING_PROVIDERS",
    # Reranker
    "select_reranker",
    "SUPPORTED_RERANKER_TYPES",
]
