"""
证书管理模块

提供 SSL/TLS 证书的获取、验证和管理功能。

主要功能：
- 证书获取：从服务器获取证书链
- 证书验证：验证证书有效性
- 证书存储：管理本地证书存储
- 服务注册：管理服务证书配置

使用示例：
    from tableau_assistant.src.infra.certs import (
        CertificateManager,
        CertificateConfig,
        get_certificate_manager,
    )
    
    # 获取证书管理器
    manager = get_certificate_manager()
    
    # 获取并保存证书
    cert_paths = manager.fetch_and_save_certificates("tableau.example.com")
"""

from .manager import CertificateManager
from .config import CertificateConfig, get_certificate_config, SSLConfig, get_ssl_config
from .fetcher import CertificateFetcher
from .validator import CertificateValidator
from .models import CertificateInfo, CertificateChain, ValidationResult
from .service_registry import ServiceRegistry, ServiceConfig

# 全局证书管理器实例
_certificate_manager: CertificateManager | None = None


def get_certificate_manager() -> CertificateManager:
    """获取全局证书管理器实例"""
    global _certificate_manager
    if _certificate_manager is None:
        _certificate_manager = CertificateManager()
    return _certificate_manager


__all__ = [
    "CertificateManager",
    "CertificateConfig",
    "CertificateFetcher",
    "CertificateValidator",
    "CertificateInfo",
    "CertificateChain",
    "ValidationResult",
    "ServiceRegistry",
    "ServiceConfig",
    "get_certificate_manager",
    "get_certificate_config",
    # 向后兼容别名
    "SSLConfig",
    "get_ssl_config",
]
