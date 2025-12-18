"""
证书管理器主模块

提供统一的证书管理接口。
"""
from typing import Optional, Dict, Any
from pathlib import Path
import logging

from .config import CertificateConfig, get_certificate_config
from .fetcher import CertificateFetcher
from .validator import CertificateValidator

logger = logging.getLogger(__name__)


class CertificateManager:
    """
    证书管理器
    
    统一管理SSL证书的获取、验证和配置。
    
    使用示例:
        manager = CertificateManager()
        
        # 获取并保存证书
        cert_paths = manager.fetch_and_save_certificates("tableau.example.com")
        
        # 验证证书
        result = manager.validate_certificate()
        
        # 获取SSL配置
        ssl_config = manager.get_ssl_config()
    """
    
    def __init__(
        self,
        cert_dir: Optional[str] = None,
        verify: Optional[bool] = None,
        ca_bundle: Optional[str] = None,
        timeout: int = 10,
        warning_days: int = 30
    ):
        """
        初始化证书管理器
        
        Args:
            cert_dir: 证书目录
            verify: 是否启用SSL验证
            ca_bundle: 证书文件路径
            timeout: 网络超时时间
            warning_days: 证书过期警告天数
        """
        if cert_dir is None:
            cert_dir = "tableau_assistant/src/infra/certs/store"
        
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        self.fetcher = CertificateFetcher(timeout=timeout)
        self.validator = CertificateValidator(warning_days=warning_days)
        
        self.ssl_config = get_certificate_config(
            verify=verify,
            ca_bundle=ca_bundle,
            cert_dir=str(self.cert_dir)
        )
        
        logger.info(f"证书管理器已初始化: {self.ssl_config}")
    
    def fetch_and_save_certificates(
        self,
        hostname: str,
        port: int = 443,
        force: bool = False
    ) -> Dict[str, str]:
        """
        获取并保存服务器证书
        
        Args:
            hostname: 服务器主机名
            port: 端口号
            force: 强制重新获取
        
        Returns:
            证书文件路径字典
        """
        safe_hostname = hostname.replace('.', '_').replace(':', '_')
        cert_file = self.cert_dir / f"{safe_hostname}_cert.pem"
        
        if cert_file.exists() and not force:
            validation = self.validator.validate_certificate_file(str(cert_file))
            if validation["valid"]:
                logger.info(f"使用已存在的有效证书: {cert_file}")
                return {"server_cert": str(cert_file)}
        
        logger.info(f"正在获取证书: {hostname}:{port}")
        _, cert_pem = self.fetcher.fetch_server_certificate(
            hostname, port, str(cert_file)
        )
        
        return {"server_cert": str(cert_file)}
    
    def validate_certificate(
        self,
        cert_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        验证证书
        
        Args:
            cert_file: 证书文件路径,默认使用配置的证书
        
        Returns:
            验证结果
        """
        if cert_file is None:
            cert_file = self.ssl_config.ca_bundle
        
        if not cert_file:
            return {
                "valid": False,
                "errors": ["未配置证书文件"]
            }
        
        return self.validator.validate_certificate_file(cert_file)
    
    def validate_connection(
        self,
        hostname: str,
        port: int = 443
    ) -> Dict[str, Any]:
        """
        验证SSL连接
        
        Args:
            hostname: 主机名
            port: 端口号
        
        Returns:
            验证结果
        """
        return self.validator.validate_ssl_connection(
            hostname, port, self.ssl_config.ca_bundle
        )
    
    def get_ssl_config(self) -> CertificateConfig:
        """获取SSL配置"""
        return self.ssl_config


__all__ = ["CertificateManager"]
