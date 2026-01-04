"""
基础设施层

为上层提供基础能力支撑：AI 模型、存储、配置、证书管理、异常处理。

子模块：
- ai/: AI 模型管理（LLM、Embedding、Reranker）
- storage/: 存储管理（缓存、持久化）
- config/: 配置管理
- certs/: 证书管理（SSL/TLS）
- exceptions.py: 异常定义
"""

# 导出常用组件
from tableau_assistant.src.infra.config import settings
from tableau_assistant.src.infra.ai import get_llm, get_embeddings
from tableau_assistant.src.infra.exceptions import (
    VizQLError, VizQLAuthError, VizQLValidationError, VizQLServerError,
    VizQLRateLimitError, VizQLTimeoutError, VizQLNetworkError,
)
from tableau_assistant.src.infra.certs import (
    CertificateManager,
    CertificateConfig,
    get_certificate_manager,
    get_certificate_config,
)

__all__ = [
    # Config
    "settings",
    # AI
    "get_llm",
    "get_embeddings",
    # Certs
    "CertificateManager",
    "CertificateConfig",
    "get_certificate_manager",
    "get_certificate_config",
    # Exceptions
    "VizQLError",
    "VizQLAuthError",
    "VizQLValidationError",
    "VizQLServerError",
    "VizQLRateLimitError",
    "VizQLTimeoutError",
    "VizQLNetworkError",
]
