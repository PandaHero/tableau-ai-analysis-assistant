"""
证书管理器主模块

提供统一的证书管理接口，支持：
- 从 cert_config.yaml 加载配置
- 自签名证书生成（开发环境）
- 公司证书加载和自动拉取（生产环境）
- 第三方服务证书自动获取
- 证书热更新
"""
import os
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization

from .config import (
    CertificateConfig, get_certificate_config, get_cert_config,
    CertConfigData, ServiceCertConfig
)
from .fetcher import CertificateFetcher
from .validator import CertificateValidator
from .self_signed import SelfSignedGenerator
from .hot_reload import HotReloader

logger = logging.getLogger(__name__)


class CertificateManager:
    """
    证书管理器
    
    统一管理 SSL 证书的获取、生成、验证和配置。
    
    使用示例:
        # 使用配置文件初始化
        manager = CertificateManager()
        manager.initialize()
        
        # 获取 SSL 配置供 uvicorn 使用
        ssl_config = manager.get_app_ssl_config()
        
        # 获取证书状态
        status = manager.get_status()
    """
    
    def __init__(
        self,
        config_path: str = "cert_config.yaml",
        timeout: int = 10
    ):
        """
        初始化证书管理器
        
        Args:
            config_path: 配置文件路径
            timeout: 网络超时时间
        """
        self.config_path = config_path
        self.timeout = timeout
        
        # 加载配置
        self.config: CertConfigData = get_cert_config(config_path)
        
        # 确保证书目录存在
        self.cert_dir = Path(self.config.cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化子组件
        self.fetcher = CertificateFetcher(timeout=timeout)
        self.validator = CertificateValidator(warning_days=self.config.warning_days)
        
        # 应用证书路径（初始化后设置）
        self._app_cert_path: Optional[str] = None
        self._app_key_path: Optional[str] = None
        self._app_ca_path: Optional[str] = None
        
        # 热更新器
        self._hot_reloader: Optional[HotReloader] = None
        
        # 初始化状态
        self._initialized = False
        
        logger.info(f"证书管理器已创建，配置: {config_path}")
    
    def initialize(self) -> bool:
        """
        初始化证书
        
        1. 根据 source 准备应用证书
        2. 获取第三方服务证书
        3. 验证所有证书
        
        Returns:
            True 如果初始化成功
        """
        logger.info("开始初始化证书...")
        
        try:
            # 1. 准备应用证书
            self._prepare_app_certificates()
            
            # 2. 获取服务证书
            self._fetch_service_certificates()
            
            # 3. 验证应用证书
            if not self._validate_app_certificates():
                logger.error("应用证书验证失败")
                return False
            
            self._initialized = True
            logger.info("证书初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"证书初始化失败: {e}")
            return False
    
    def _prepare_app_certificates(self) -> None:
        """准备应用证书"""
        source = self.config.application.source
        
        if source == "self-signed":
            self._generate_self_signed()
        elif source == "company":
            self._load_company_certs()
        else:
            raise ValueError(f"未知的证书来源: {source}")
    
    def _generate_self_signed(self) -> None:
        """生成自签名证书"""
        logger.info("使用自签名证书模式")
        
        generator = SelfSignedGenerator(str(self.cert_dir))
        paths = generator.generate()
        
        self._app_cert_path = paths["server_cert"]
        self._app_key_path = paths["server_key"]
        self._app_ca_path = paths["ca_cert"]
        
        logger.info(f"自签名证书已准备: {self._app_cert_path}")
    
    def _load_company_certs(self) -> None:
        """加载公司证书"""
        logger.info("使用公司证书模式")
        
        company = self.config.application.company
        if not company:
            raise ValueError("公司证书模式需要配置 application.company")
        
        # 如果启用自动拉取
        if company.auto_fetch and company.fetch_url:
            try:
                self._fetch_company_certs_from_server(company)
                logger.info("公司证书已从服务器拉取")
                return
            except Exception as e:
                logger.warning(f"公司证书拉取失败，尝试使用本地文件: {e}")
        
        # 使用本地文件
        cert_file = company.cert_file
        key_file = company.key_file
        ca_bundle = company.ca_bundle
        
        # 验证文件存在
        for name, path in [("证书", cert_file), ("私钥", key_file), ("CA", ca_bundle)]:
            if not path:
                raise ValueError(f"公司{name}路径未配置")
            if not Path(path).exists():
                raise FileNotFoundError(f"公司{name}文件不存在: {path}")
        
        self._app_cert_path = cert_file
        self._app_key_path = key_file
        self._app_ca_path = ca_bundle
        
        logger.info(f"公司证书已加载: {self._app_cert_path}")
    
    def _fetch_company_certs_from_server(self, company) -> None:
        """从公司证书服务器拉取证书"""
        from urllib.parse import urlparse
        import requests
        
        fetch_url = company.fetch_url
        parsed = urlparse(fetch_url)
        hostname = parsed.hostname
        port = parsed.port or 443
        
        # 使用现有的 CertificateFetcher 获取服务器证书
        ca_file = self.cert_dir / "company_ca.pem"
        self.fetcher.fetch_server_certificate(hostname, port, str(ca_file))
        
        # 下载证书文件
        response = requests.get(fetch_url, timeout=self.timeout, verify=str(ca_file))
        response.raise_for_status()
        
        cert_data = response.json()
        
        # 保存证书文件
        cert_file = self.cert_dir / "company_server.pem"
        key_file = self.cert_dir / "company_server_key.pem"
        
        cert_file.write_text(cert_data.get("certificate", ""))
        key_file.write_text(cert_data.get("private_key", ""))
        
        self._app_cert_path = str(cert_file)
        self._app_key_path = str(key_file)
        self._app_ca_path = str(ca_file)
    
    def _fetch_service_certificates(self) -> None:
        """获取第三方服务证书"""
        for service_id, service_config in self.config.services.items():
            try:
                self._fetch_service_cert(service_id, service_config)
            except Exception as e:
                logger.warning(f"获取服务 {service_id} 证书失败: {e}")
    
    def _fetch_service_cert(
        self,
        service_id: str,
        config: ServiceCertConfig
    ) -> None:
        """获取单个服务证书"""
        hostname = config.hostname
        
        if not hostname:
            logger.debug(f"服务 {service_id} 未配置主机名，跳过")
            return
        
        # 解析主机名（可能包含协议）
        if hostname.startswith("http"):
            parsed = urlparse(hostname)
            hostname = parsed.hostname or hostname
            if parsed.port:
                config.port = parsed.port
        
        # 处理 auto_fetch
        auto_fetch = config.auto_fetch
        
        # 智能模式：检测 Tableau Cloud
        if auto_fetch == "auto":
            if "online.tableau.com" in hostname.lower():
                logger.info(f"服务 {service_id}: Tableau Cloud，使用系统证书")
                config.use_system_certs = True
                return
            else:
                auto_fetch = True
        
        if not auto_fetch:
            logger.debug(f"服务 {service_id}: auto_fetch=false，跳过")
            return
        
        # 检查现有证书
        cert_file = self.cert_dir / config.ca_bundle
        if cert_file.exists():
            validation = self.validator.validate_certificate_file(str(cert_file))
            if validation["valid"]:
                logger.info(f"服务 {service_id}: 使用现有证书")
                return
        
        # 获取证书
        logger.info(f"获取服务 {service_id} 证书: {hostname}:{config.port}")
        try:
            self.fetcher.fetch_server_certificate(
                hostname,
                config.port,
                str(cert_file)
            )
            logger.info(f"服务 {service_id} 证书已保存: {cert_file}")
        except Exception as e:
            logger.warning(f"服务 {service_id} 证书获取失败: {e}")
    
    def _validate_app_certificates(self) -> bool:
        """验证应用证书"""
        if not self._app_cert_path or not self._app_key_path:
            logger.error("应用证书路径未设置")
            return False
        
        # 验证证书文件
        cert_result = self.validator.validate_certificate_file(self._app_cert_path)
        if not cert_result["valid"]:
            logger.error(f"证书验证失败: {cert_result['errors']}")
            return False
        
        # 验证私钥文件存在
        if not Path(self._app_key_path).exists():
            logger.error(f"私钥文件不存在: {self._app_key_path}")
            return False
        
        # 验证证书和私钥匹配
        if not self._verify_cert_key_match():
            logger.error("证书和私钥不匹配")
            return False
        
        # 检查过期
        self._check_expiration()
        
        return True
    
    def _verify_cert_key_match(self) -> bool:
        """验证证书和私钥是否匹配"""
        try:
            # 加载证书
            cert_pem = Path(self._app_cert_path).read_bytes()
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            
            # 加载私钥
            key_pem = Path(self._app_key_path).read_bytes()
            key = serialization.load_pem_private_key(
                key_pem, password=None, backend=default_backend()
            )
            
            # 比较公钥
            cert_public_key = cert.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            key_public_key = key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            return cert_public_key == key_public_key
        except Exception as e:
            logger.error(f"验证证书私钥匹配失败: {e}")
            return False
    
    def _check_expiration(self) -> None:
        """检查证书过期"""
        try:
            cert_pem = Path(self._app_cert_path).read_bytes()
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            
            now = datetime.now(timezone.utc)
            expires = cert.not_valid_after_utc
            days_left = (expires - now).days
            
            if days_left < 0:
                logger.error(f"证书已过期！过期时间: {expires}")
            elif days_left < self.config.warning_days:
                logger.warning(f"证书即将过期！剩余 {days_left} 天，过期时间: {expires}")
            else:
                logger.info(f"证书有效，剩余 {days_left} 天")
        except Exception as e:
            logger.warning(f"检查证书过期失败: {e}")
    
    def get_app_ssl_config(self) -> Dict[str, str]:
        """
        获取应用 SSL 配置（供 uvicorn 使用）
        
        Returns:
            {"ssl_certfile": "...", "ssl_keyfile": "..."}
        """
        if not self._initialized:
            raise RuntimeError("证书管理器未初始化，请先调用 initialize()")
        
        return {
            "ssl_certfile": self._app_cert_path,
            "ssl_keyfile": self._app_key_path,
        }
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取所有证书状态
        
        Returns:
            证书状态字典
        """
        status = {
            "initialized": self._initialized,
            "source": self.config.application.source,
            "application": None,
            "services": {},
        }
        
        # 应用证书状态
        if self._app_cert_path:
            status["application"] = self._get_cert_status(self._app_cert_path)
        
        # 服务证书状态
        for service_id, service_config in self.config.services.items():
            cert_file = self.cert_dir / service_config.ca_bundle
            if cert_file.exists():
                status["services"][service_id] = self._get_cert_status(str(cert_file))
            else:
                status["services"][service_id] = {
                    "valid": False,
                    "error": "证书文件不存在",
                    "use_system_certs": service_config.use_system_certs,
                }
        
        return status
    
    def _get_cert_status(self, cert_path: str) -> Dict[str, Any]:
        """获取单个证书状态"""
        try:
            cert_pem = Path(cert_path).read_bytes()
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            
            now = datetime.now(timezone.utc)
            expires = cert.not_valid_after_utc
            days_left = (expires - now).days
            
            return {
                "valid": days_left > 0,
                "cert_file": cert_path,
                "expires": expires.isoformat(),
                "days_until_expiry": days_left,
                "warning": days_left < self.config.warning_days,
                "subject": cert.subject.rfc4514_string(),
            }
        except Exception as e:
            return {
                "valid": False,
                "cert_file": cert_path,
                "error": str(e),
            }
    
    def export_to_env(self) -> Dict[str, str]:
        """
        导出证书路径为环境变量格式
        
        Returns:
            环境变量字典
        """
        if not self._initialized:
            return {}
        
        env_vars = {
            "SSL_CERT_FILE": self._app_cert_path or "",
            "SSL_KEY_FILE": self._app_key_path or "",
        }
        
        if self._app_ca_path:
            env_vars["REQUESTS_CA_BUNDLE"] = self._app_ca_path
        
        return env_vars
    
    def start_hot_reload(
        self,
        callback: Optional[Callable[[], None]] = None
    ) -> None:
        """
        启动证书热更新
        
        Args:
            callback: 证书重载后的回调函数
        """
        if self._hot_reloader:
            return
        
        watch_paths = []
        if self._app_cert_path:
            watch_paths.append(self._app_cert_path)
        if self._app_key_path:
            watch_paths.append(self._app_key_path)
        
        def on_reload() -> bool:
            """重载回调"""
            if not self._validate_app_certificates():
                return False
            if callback:
                callback()
            return True
        
        # 公司证书刷新回调
        refresh_callback = None
        refresh_interval = 0
        
        company = self.config.application.company
        if company and company.auto_refresh and company.fetch_url:
            refresh_interval = company.refresh_interval
            
            def on_refresh() -> bool:
                """刷新回调 - 重新拉取公司证书"""
                try:
                    self._fetch_company_certs_from_server(company)
                    logger.info("公司证书已刷新")
                    return True
                except Exception as e:
                    logger.error(f"证书刷新失败: {e}")
                    return False
            
            refresh_callback = on_refresh
        
        self._hot_reloader = HotReloader(
            watch_paths=watch_paths,
            callback=on_reload,
            refresh_callback=refresh_callback,
            refresh_interval=refresh_interval,
        )
        self._hot_reloader.start()
    
    def stop_hot_reload(self) -> None:
        """停止证书热更新"""
        if self._hot_reloader:
            self._hot_reloader.stop()
            self._hot_reloader = None
    
    # ========================================
    # 兼容旧 API
    # ========================================
    
    def fetch_and_save_certificates(
        self,
        hostname: str,
        port: int = 443,
        force: bool = False
    ) -> Dict[str, str]:
        """
        获取并保存服务器证书（兼容旧 API）
        """
        safe_hostname = hostname.replace('.', '_').replace(':', '_')
        cert_file = self.cert_dir / f"{safe_hostname}_cert.pem"
        
        if cert_file.exists() and not force:
            validation = self.validator.validate_certificate_file(str(cert_file))
            if validation["valid"]:
                logger.info(f"使用已存在的有效证书: {cert_file}")
                return {"server_cert": str(cert_file)}
        
        logger.info(f"正在获取证书: {hostname}:{port}")
        self.fetcher.fetch_server_certificate(hostname, port, str(cert_file))
        
        return {"server_cert": str(cert_file)}
    
    def validate_certificate(
        self,
        cert_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """验证证书（兼容旧 API）"""
        if cert_file is None:
            cert_file = self._app_cert_path
        
        if not cert_file:
            return {"valid": False, "errors": ["未配置证书文件"]}
        
        return self.validator.validate_certificate_file(cert_file)
    
    def validate_connection(
        self,
        hostname: str,
        port: int = 443
    ) -> Dict[str, Any]:
        """验证 SSL 连接（兼容旧 API）"""
        return self.validator.validate_ssl_connection(
            hostname, port, self._app_ca_path
        )
    
    def get_ssl_config(self) -> CertificateConfig:
        """获取 SSL 配置（兼容旧 API）"""
        return get_certificate_config(
            verify=self.config.verify_ssl,
            ca_bundle=self._app_ca_path,
            cert_dir=str(self.cert_dir)
        )


__all__ = ["CertificateManager"]
