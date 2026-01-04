"""
AI 模型管理

统一管理所有 AI 模型的选择、配置和创建。

主要功能：
- LLM 模型管理（get_llm）
- Embedding 模型管理（get_embeddings, EmbeddingProvider）
- 模型配置管理（ModelManager）

使用示例：
    from tableau_assistant.src.infra.ai import (
        get_llm,           # 推荐：自动从 ModelManager 获取配置
        get_embeddings,    # 推荐：自动从 ModelManager 获取配置
    )
    
    # 使用默认 LLM
    llm = get_llm()
    llm = get_llm(temperature=0.1)  # 指定 temperature
    
    # 使用默认 Embedding
    embeddings = get_embeddings()
"""

# LLM 模型管理
from tableau_assistant.src.infra.ai.llm import (
    get_llm,
    get_supported_providers,
)

# 自定义 LLM（公司内部部署的模型）
from tableau_assistant.src.infra.ai.custom_llm import (
    CustomLLMChat,
    CustomLLMConfig,
    AuthType,
)

# 模型管理器
from tableau_assistant.src.infra.ai.model_manager import (
    ModelManager,
    ModelConfig,
    ModelStats,
    ModelType,
    ModelStatus,
    ModelCreateRequest,
    ModelUpdateRequest,
    HealthCheckResult,
    get_model_manager,
    reset_model_manager,
)

# Embedding 模型管理
from tableau_assistant.src.infra.ai.embeddings import (
    get_embeddings,
    select_embeddings,
    EmbeddingProvider,
    ZhipuEmbedding,
    OpenAIEmbedding,
    EmbeddingProviderFactory,
)

__all__ = [
    # LLM
    "get_llm",
    "get_supported_providers",
    # 自定义 LLM
    "CustomLLMChat",
    "CustomLLMConfig",
    "AuthType",
    # 模型管理器
    "ModelManager",
    "ModelConfig",
    "ModelStats",
    "ModelType",
    "ModelStatus",
    "ModelCreateRequest",
    "ModelUpdateRequest",
    "HealthCheckResult",
    "get_model_manager",
    "reset_model_manager",
    # Embedding
    "get_embeddings",
    "select_embeddings",
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "OpenAIEmbedding",
    "EmbeddingProviderFactory",
]
