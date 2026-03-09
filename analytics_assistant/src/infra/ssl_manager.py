"""
SSL 证书管理器

功能：
1. 统一管理前后端 SSL 证书
2. 支持证书热更新（文件变化自动重新加载）
3. 证书有效性检查
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class SSLCertificateManager:
    """SSL 证书管理器，支持热更新"""
    
    def __init__(
        self,
        cert_file: str,
        key_file: str,
        reload_interval: int = 60,
    ):
        """
        初始化证书管理器
        
        Args:
            cert_file: 证书文件路径（相对于项目根目录）
            key_file: 密钥文件路径（相对于项目根目录）
            reload_interval: 证书热更新检查间隔（秒），0 表示禁用热更新
        """
        self.cert_file = Path(cert_file)
        self.key_file = Path(key_file)
        self.reload_interval = reload_interval
        
        # 证书文件的最后修改时间
        self._cert_mtime: Optional[float] = None
        self._key_mtime: Optional[float] = None
        
        # 最后检查时间
        self._last_check_time: float = 0
        
        # 验证证书文件存在
        self._validate_files()
        
        # 初始化时记录文件修改时间
        self._update_mtimes()
        
        logger.info(
            f"SSL 证书管理器已初始化: cert={self.cert_file}, "
            f"key={self.key_file}, reload_interval={self.reload_interval}s"
        )
    
    def _validate_files(self) -> None:
        """验证证书文件是否存在"""
        if not self.cert_file.exists():
            raise FileNotFoundError(f"证书文件不存在: {self.cert_file}")
        
        if not self.key_file.exists():
            raise FileNotFoundError(f"密钥文件不存在: {self.key_file}")
    
    def _update_mtimes(self) -> None:
        """更新文件修改时间记录"""
        self._cert_mtime = os.path.getmtime(self.cert_file)
        self._key_mtime = os.path.getmtime(self.key_file)
    
    def _has_changed(self) -> bool:
        """检查证书文件是否已变化"""
        try:
            cert_mtime = os.path.getmtime(self.cert_file)
            key_mtime = os.path.getmtime(self.key_file)
            
            return (
                cert_mtime != self._cert_mtime or
                key_mtime != self._key_mtime
            )
        except OSError as e:
            logger.error(f"检查证书文件修改时间失败: {e}")
            return False
    
    def should_reload(self) -> bool:
        """
        判断是否需要重新加载证书
        
        Returns:
            True 如果证书已变化且超过检查间隔
        """
        # 禁用热更新
        if self.reload_interval <= 0:
            return False
        
        current_time = time.time()
        
        # 未到检查间隔
        if current_time - self._last_check_time < self.reload_interval:
            return False
        
        # 更新检查时间
        self._last_check_time = current_time
        
        # 检查文件是否变化
        if self._has_changed():
            logger.info("检测到证书文件已更新，需要重新加载")
            self._update_mtimes()
            return True
        
        return False
    
    def get_cert_paths(self) -> Tuple[Path, Path]:
        """
        获取证书文件路径
        
        Returns:
            (cert_file, key_file) 元组
        """
        return (self.cert_file, self.key_file)
    
    def get_cert_info(self) -> dict:
        """
        获取证书信息
        
        Returns:
            证书信息字典
        """
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        
        try:
            with open(self.cert_file, 'rb') as f:
                cert_data = f.read()
            
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            
            return {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "not_valid_before": cert.not_valid_before_utc.isoformat(),
                "not_valid_after": cert.not_valid_after_utc.isoformat(),
                "serial_number": cert.serial_number,
                "is_expired": datetime.now() > cert.not_valid_after_utc.replace(tzinfo=None),
            }
        except Exception as e:
            logger.error(f"读取证书信息失败: {e}")
            return {}
    
    def validate_certificate(self) -> bool:
        """
        验证证书有效性
        
        Returns:
            True 如果证书有效
        """
        try:
            cert_info = self.get_cert_info()
            
            if not cert_info:
                return False
            
            if cert_info.get("is_expired"):
                logger.warning(f"证书已过期: {self.cert_file}")
                return False
            
            logger.info(f"证书有效: {cert_info.get('subject')}")
            return True
            
        except Exception as e:
            logger.error(f"验证证书失败: {e}")
            return False


def get_ssl_manager(config: dict) -> SSLCertificateManager:
    """
    从配置创建 SSL 证书管理器
    
    Args:
        config: app.yaml 配置字典
    
    Returns:
        SSLCertificateManager 实例
    """
    ssl_config = config.get("ssl", {})
    certificates = ssl_config.get("certificates", {})
    active_cert = ssl_config.get("active_cert", "localhost")
    
    if active_cert not in certificates:
        raise ValueError(f"未找到证书配置: {active_cert}")
    
    cert_config = certificates[active_cert]
    
    return SSLCertificateManager(
        cert_file=cert_config["cert_file"],
        key_file=cert_config["key_file"],
        reload_interval=cert_config.get("reload_interval", 60),
    )
