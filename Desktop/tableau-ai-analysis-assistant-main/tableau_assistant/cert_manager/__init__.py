"""
Certificate Manager Package

生产级别的SSL/TLS证书管理包
提供证书获取、验证、存储和配置功能

主要功能:
- 自动获取和更新证书
- 证书验证和过期检查
- 多环境配置支持
- 证书链完整性验证
- 统一的SSL配置接口

使用示例:
    from cert_manager import CertificateManager, get_ssl_config
    
    # 初始化证书管理器
    manager = CertificateManager()
    
    # 获取SSL配置
    ssl_config = get_ssl_config()
    
    # 使用在requests中
    import requests
    response = requests.get(url, **ssl_config.requests_kwargs())
"""

from .manager import CertificateManager
from .config import SSLConfig, get_ssl_config
from .validator import CertificateValidator
from .fetcher import CertificateFetcher

__version__ = "1.0.0"
__all__ = [
    "CertificateManager",
    "SSLConfig",
    "get_ssl_config",
    "CertificateValidator",
    "CertificateFetcher",
]
