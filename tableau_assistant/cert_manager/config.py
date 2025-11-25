"""
SSL配置模块

提供统一的SSL配置接口,支持多种HTTP客户端库
"""
import os
import ssl
from typing import Union, Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class SSLConfig:
    """
    SSL配置管理器
    
    统一管理SSL/TLS证书配置,支持:
    - 系统证书库
    - 自定义证书文件
    - 禁用SSL验证(仅开发环境)
    
    环境变量:
        LLM_VERIFY_SSL: 是否启用SSL验证 (true/false)
        LLM_CA_BUNDLE: 自定义证书文件路径
        CERT_MANAGER_DEBUG: 启用调试日志 (true/false)
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
        # 从环境变量或参数获取配置
        self.verify_ssl = (
            verify if verify is not None 
            else os.getenv("LLM_VERIFY_SSL", "true").lower() == "true"
        )
        
        self.ca_bundle = ca_bundle or os.getenv("LLM_CA_BUNDLE", "")
        self.cert_dir = cert_dir or os.getenv("CERT_MANAGER_DIR", "tableau_assistant/certs")
        
        # 调试模式
        self.debug = os.getenv("CERT_MANAGER_DEBUG", "false").lower() == "true"
        
        # 自动检测证书路径
        if not self.ca_bundle:
            self._auto_detect_cert_path()
        
        # 验证配置
        self._validate_config()
        
        if self.debug:
            logger.debug(f"SSL配置初始化: {self}")
    
    def _auto_detect_cert_path(self):
        """自动检测证书文件路径"""
        # 可能的证书文件名
        cert_filenames = [
            "deepseek_full_chain.pem",
            "full_chain.pem",
            "ca_bundle.pem",
            "cert_chain.pem",
        ]
        
        # 可能的证书目录
        search_paths = [
            Path.cwd() / self.cert_dir,  # 配置的证书目录
            Path.cwd() / "tableau_assistant" / "certs",  # 项目证书目录
            Path("/opt/tableau-assistant/certs"),  # 生产环境标准路径
            Path.cwd() / "certs",  # 兼容旧版本
            Path.cwd(),  # 当前目录(最后查找)
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
                logger.error(f"证书文件不存在: {self.ca_bundle}")
                raise FileNotFoundError(f"证书文件不存在: {self.ca_bundle}")
            
            if not cert_path.is_file():
                logger.error(f"证书路径不是文件: {self.ca_bundle}")
                raise ValueError(f"证书路径不是文件: {self.ca_bundle}")
            
            # 检查文件权限
            if not os.access(cert_path, os.R_OK):
                logger.error(f"证书文件不可读: {self.ca_bundle}")
                raise PermissionError(f"证书文件不可读: {self.ca_bundle}")
            
            if self.debug:
                logger.debug(f"证书文件验证通过: {self.ca_bundle}")
    
    def get_verify_param(self) -> Union[bool, str]:
        """
        获取SSL验证参数
        
        用于requests、httpx等库的verify参数
        
        Returns:
            - True: 使用系统默认证书
            - False: 禁用SSL验证(不推荐)
            - str: 自定义证书文件路径
        """
        if not self.verify_ssl:
            return False
        
        if self.ca_bundle:
            return self.ca_bundle
        
        return True
    
    def get_ssl_context(self, check_hostname: bool = True) -> ssl.SSLContext:
        """
        创建SSL上下文
        
        用于底层socket连接
        
        Args:
            check_hostname: 是否检查主机名
        
        Returns:
            配置好的SSLContext对象
        """
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
    
    def get_aiohttp_ssl_param(self) -> Union[bool, ssl.SSLContext]:
        """
        获取aiohttp的SSL参数
        
        Returns:
            - False: 禁用SSL验证
            - SSLContext: 自定义SSL上下文
        """
        if not self.verify_ssl:
            return False
        
        return self.get_ssl_context()
    
    def httpx_client_kwargs(self) -> Dict[str, Any]:
        """
        获取httpx.Client的初始化参数
        
        Returns:
            包含verify参数的字典
        """
        return {"verify": self.get_verify_param()}
    
    def requests_kwargs(self) -> Dict[str, Any]:
        """
        获取requests的请求参数
        
        Returns:
            包含verify参数的字典
        """
        return {"verify": self.get_verify_param()}
    
    def aiohttp_kwargs(self) -> Dict[str, Any]:
        """
        获取aiohttp的请求参数
        
        Returns:
            包含ssl参数的字典
        """
        return {"ssl": self.get_aiohttp_ssl_param()}
    
    @property
    def is_enabled(self) -> bool:
        """SSL验证是否启用"""
        return self.verify_ssl
    
    @property
    def is_using_custom_cert(self) -> bool:
        """是否使用自定义证书"""
        return bool(self.ca_bundle)
    
    @property
    def cert_source(self) -> str:
        """证书来源描述"""
        if not self.verify_ssl:
            return "disabled"
        elif self.ca_bundle:
            return f"custom:{self.ca_bundle}"
        else:
            return "system"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "verify_ssl": self.verify_ssl,
            "ca_bundle": self.ca_bundle,
            "cert_dir": self.cert_dir,
            "cert_source": self.cert_source,
            "is_enabled": self.is_enabled,
            "is_using_custom_cert": self.is_using_custom_cert,
        }
    
    def __repr__(self) -> str:
        """字符串表示"""
        if not self.verify_ssl:
            return "SSLConfig(verify=False)"
        elif self.ca_bundle:
            return f"SSLConfig(verify=True, ca_bundle='{self.ca_bundle}')"
        else:
            return "SSLConfig(verify=True, system_certs)"
    
    def __str__(self) -> str:
        """用户友好的字符串表示"""
        return self.__repr__()


# 全局SSL配置实例
_global_ssl_config: Optional[SSLConfig] = None


def get_ssl_config(
    verify: Optional[bool] = None,
    ca_bundle: Optional[str] = None,
    cert_dir: Optional[str] = None,
    force_new: bool = False
) -> SSLConfig:
    """
    获取SSL配置实例(单例模式)
    
    Args:
        verify: 是否启用SSL验证
        ca_bundle: 证书文件路径
        cert_dir: 证书目录
        force_new: 强制创建新实例
    
    Returns:
        SSLConfig实例
    """
    global _global_ssl_config
    
    if force_new or _global_ssl_config is None:
        _global_ssl_config = SSLConfig(
            verify=verify,
            ca_bundle=ca_bundle,
            cert_dir=cert_dir
        )
    
    return _global_ssl_config


def reset_ssl_config():
    """重置全局SSL配置"""
    global _global_ssl_config
    _global_ssl_config = None
