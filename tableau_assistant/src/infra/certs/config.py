"""
SSL/证书配置模块

提供统一的SSL配置接口,支持多种HTTP客户端库。
"""
import os
import ssl
from typing import Union, Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class CertificateConfig:
    """
    SSL/证书配置管理器
    
    统一管理SSL/TLS证书配置,支持:
    - 系统证书库
    - 自定义证书文件
    - 禁用SSL验证(仅开发环境)
    
    环境变量:
        VIZQL_VERIFY_SSL: 是否启用SSL验证 (true/false)
        VIZQL_CA_BUNDLE: 自定义证书文件路径
    """
    
    def __init__(
        self,
        verify: Optional[bool] = None,
        ca_bundle: Optional[str] = None,
        cert_dir: Optional[str] = None
    ):
        """
        初始化SSL配置
        
        Args:
            verify: 是否启用SSL验证,None则从环境变量读取
            ca_bundle: 证书文件路径,None则从环境变量读取
            cert_dir: 证书目录,用于自动查找证书文件
        """
        # 从 settings 或参数获取配置
        if verify is not None:
            self.verify_ssl = verify
        else:
            try:
                from tableau_assistant.src.infra.config.settings import settings
                self.verify_ssl = settings.vizql_verify_ssl
            except ImportError:
                self.verify_ssl = True
        
        if ca_bundle:
            self.ca_bundle = ca_bundle
        else:
            try:
                from tableau_assistant.src.infra.config.settings import settings
                self.ca_bundle = settings.vizql_ca_bundle or ""
            except ImportError:
                self.ca_bundle = ""
        
        self.cert_dir = cert_dir or "tableau_assistant/src/infra/certs/store"
        
        # 调试模式
        try:
            from tableau_assistant.src.infra.config.settings import settings
            self.debug = settings.debug
        except ImportError:
            self.debug = False
        
        # 自动检测证书路径
        if not self.ca_bundle:
            self._auto_detect_cert_path()
        
        # 验证配置
        self._validate_config()
        
        if self.debug:
            logger.debug(f"SSL配置初始化: {self}")
    
    def _auto_detect_cert_path(self):
        """自动检测证书文件路径"""
        cert_filenames = [
            "full_chain.pem",
            "ca_bundle.pem",
            "cert_chain.pem",
        ]
        
        search_paths = [
            Path.cwd() / self.cert_dir,
            Path.cwd() / "tableau_assistant" / "src" / "infra" / "certs" / "store",
            Path.cwd() / "tableau_assistant" / "certs",  # 兼容旧路径
            Path("/opt/tableau-assistant/certs"),
            Path.cwd() / "certs",
            Path.cwd(),
        ]
        
        for search_path in search_paths:
            if not search_path.exists():
                continue
                
            for filename in cert_filenames:
                cert_path = search_path / filename
                if cert_path.exists() and cert_path.is_file():
                    self.ca_bundle = str(cert_path)
                    if self.debug:
                        logger.debug(f"自动检测到证书: {self.ca_bundle}")
                    return
    
    def _validate_config(self):
        """验证配置有效性"""
        if not self.verify_ssl:
            logger.warning("SSL验证已禁用,这在生产环境中不安全!")
            return
        
        if self.ca_bundle:
            cert_path = Path(self.ca_bundle)
            if not cert_path.exists():
                logger.warning(f"证书文件不存在: {self.ca_bundle}")
                return
            
            if not cert_path.is_file():
                logger.error(f"证书路径不是文件: {self.ca_bundle}")
                raise ValueError(f"证书路径不是文件: {self.ca_bundle}")
            
            if not os.access(cert_path, os.R_OK):
                logger.error(f"证书文件不可读: {self.ca_bundle}")
                raise PermissionError(f"证书文件不可读: {self.ca_bundle}")
            
            if self.debug:
                logger.debug(f"证书文件验证通过: {self.ca_bundle}")
    
    def get_verify_param(self) -> Union[bool, str]:
        """获取SSL验证参数(用于requests、httpx等)"""
        if not self.verify_ssl:
            return False
        if self.ca_bundle:
            return self.ca_bundle
        return True
    
    def get_ssl_context(self, check_hostname: bool = True) -> ssl.SSLContext:
        """创建SSL上下文"""
        if not self.verify_ssl:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            return context
        
        context = ssl.create_default_context()
        context.check_hostname = check_hostname
        
        if self.ca_bundle:
            context.load_verify_locations(self.ca_bundle)
        
        return context
    
    def httpx_client_kwargs(self) -> Dict[str, Any]:
        """获取httpx.Client的初始化参数"""
        if not self.verify_ssl:
            return {"verify": False}
        if self.ca_bundle:
            ssl_context = ssl.create_default_context(cafile=self.ca_bundle)
            return {"verify": ssl_context}
        return {"verify": True}
    
    def requests_kwargs(self) -> Dict[str, Any]:
        """获取requests的请求参数"""
        return {"verify": self.get_verify_param()}
    
    def aiohttp_kwargs(self) -> Dict[str, Any]:
        """获取aiohttp的请求参数"""
        if not self.verify_ssl:
            return {"ssl": False}
        return {"ssl": self.get_ssl_context()}
    
    @property
    def is_enabled(self) -> bool:
        """SSL验证是否启用"""
        return self.verify_ssl
    
    @property
    def is_using_custom_cert(self) -> bool:
        """是否使用自定义证书"""
        return bool(self.ca_bundle)
    
    def __repr__(self) -> str:
        if not self.verify_ssl:
            return "CertificateConfig(verify=False)"
        elif self.ca_bundle:
            return f"CertificateConfig(verify=True, ca_bundle='{self.ca_bundle}')"
        else:
            return "CertificateConfig(verify=True, system_certs)"


# 全局配置实例
_global_config: Optional[CertificateConfig] = None


def get_certificate_config(
    verify: Optional[bool] = None,
    ca_bundle: Optional[str] = None,
    cert_dir: Optional[str] = None,
    force_new: bool = False
) -> CertificateConfig:
    """获取证书配置实例(单例模式)"""
    global _global_config
    
    if force_new or _global_config is None:
        _global_config = CertificateConfig(
            verify=verify,
            ca_bundle=ca_bundle,
            cert_dir=cert_dir
        )
    
    return _global_config


# 向后兼容别名
SSLConfig = CertificateConfig
get_ssl_config = get_certificate_config


__all__ = [
    "CertificateConfig",
    "get_certificate_config",
    "SSLConfig",
    "get_ssl_config",
]
