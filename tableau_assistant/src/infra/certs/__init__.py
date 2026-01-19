"""
证书管理模块

提供 SSL/TLS 证书的获取、验证和管理功能。

主要功能：
- 配置加载：从 cert_config.yaml 加载配置
- 自签名证书：开发环境自动生成
- 公司证书：生产环境支持自动拉取
- 服务证书：第三方服务证书自动获取
- 热更新：证书文件变化自动重载

使用示例：
    from tableau_assistant.src.infra.certs import (
        CertificateManager,
        get_certificate_manager,
    )
    
    # 获取证书管理器
    manager = get_certificate_manager()
    
    # 初始化证书
    manager.initialize()
    
    # 获取 SSL 配置
    ssl_config = manager.get_app_ssl_config()
"""

from tableau_assistant.src.infra.certs.manager import CertificateManager
from tableau_assistant.src.infra.certs.config import (
    CertificateConfig,
    get_certificate_config,
    get_cert_config,
    ConfigLoader,
    ConfigLoadError,
    CertConfigData,
    ApplicationConfig,
    BackendCertConfig,
    CompanyCertConfig,
    ServiceCertConfig,
)
from tableau_assistant.src.infra.certs.fetcher import CertificateFetcher
from tableau_assistant.src.infra.certs.validator import CertificateValidator
from tableau_assistant.src.infra.certs.self_signed import SelfSignedGenerator
from tableau_assistant.src.infra.certs.hot_reload import HotReloader
from tableau_assistant.src.infra.certs.service_registry import ServiceRegistry, ServiceConfig


# 全局证书管理器实例
_certificate_manager: CertificateManager | None = None


def get_certificate_manager(
    config_path: str = "cert_config.yaml",
    force_new: bool = False
) -> CertificateManager:
    """
    获取全局证书管理器实例
    
    Args:
        config_path: 配置文件路径
        force_new: 是否强制创建新实例
    """
    global _certificate_manager
    if force_new or _certificate_manager is None:
        _certificate_manager = CertificateManager(config_path)
    return _certificate_manager


__all__ = [
    # 主要类
    "CertificateManager",
    "CertificateConfig",
    "ConfigLoader",
    "CertificateFetcher",
    "CertificateValidator",
    "SelfSignedGenerator",
    "HotReloader",
    "ServiceRegistry",
    
    # 数据模型
    "CertConfigData",
    "ApplicationConfig",
    "BackendCertConfig",
    "CompanyCertConfig",
    "ServiceCertConfig",
    "ServiceConfig",
    
    # 异常
    "ConfigLoadError",
    
    # 工厂函数
    "get_certificate_manager",
    "get_certificate_config",
    "get_cert_config",
]
