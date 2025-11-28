"""
证书管理器主模块

提供统一的证书管理接口
"""
from typing import Optional, Dict, Any
from pathlib import Path
import logging

from .config import SSLConfig, get_ssl_config
from .fetcher import CertificateFetcher
from .validator import CertificateValidator

logger = logging.getLogger(__name__)


class CertificateManager:
    """
    证书管理器
    
    统一管理SSL证书的获取、验证和配置
    
    使用示例:
        # 初始化
        manager = CertificateManager()
        
        # 获取DeepSeek证书
        manager.fetch_deepseek_certificates()
        
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
            cert_dir: 证书目录,默认为 tableau_assistant/certs
            verify: 是否启用SSL验证
            ca_bundle: 证书文件路径
            timeout: 网络超时时间
            warning_days: 证书过期警告天数
        """
        # 默认证书目录: tableau_assistant/certs
        if cert_dir is None:
            # 尝试找到项目根目录
            current_dir = Path.cwd()
            if (current_dir / "tableau_assistant").exists():
                # 在项目根目录
                cert_dir = "tableau_assistant/certs"
            elif (current_dir.parent / "tableau_assistant").exists():
                # 在子目录中
                cert_dir = "../tableau_assistant/certs"
            else:
                # 默认使用相对路径
                cert_dir = "tableau_assistant/certs"
        
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化组件
        self.fetcher = CertificateFetcher(timeout=timeout)
        self.validator = CertificateValidator(warning_days=warning_days)
        
        # 初始化SSL配置
        self.ssl_config = get_ssl_config(
            verify=verify,
            ca_bundle=ca_bundle,
            cert_dir=str(self.cert_dir)
        )
        
        logger.info(f"证书管理器已初始化: {self.ssl_config}")
    
    def fetch_deepseek_certificates(
        self,
        force: bool = False
    ) -> Dict[str, str]:
        """
        获取DeepSeek API证书
        
        Args:
            force: 强制重新获取,即使证书已存在
        
        Returns:
            证书文件路径字典
        """
        full_chain_file = self.cert_dir / "deepseek_full_chain.pem"
        
        # 如果证书已存在且不强制更新,先验证
        if full_chain_file.exists() and not force:
            logger.info("证书文件已存在,正在验证...")
            validation_result = self.validator.validate_certificate_file(
                str(full_chain_file)
            )
            
            if validation_result["valid"]:
                logger.info("现有证书有效,跳过获取")
                return {
                    "full_chain": str(full_chain_file),
                    "status": "existing",
                }
            else:
                logger.warning(f"现有证书无效: {validation_result['errors']}")
        
        # 获取证书
        logger.info("正在获取DeepSeek证书...")
        result = self.fetcher.fetch_deepseek_certificates(str(self.cert_dir))
        result["status"] = "fetched"
        
        # 验证获取的证书
        validation_result = self.validator.validate_certificate_file(
            result["full_chain"]
        )
        
        if not validation_result["valid"]:
            logger.error(f"获取的证书无效: {validation_result['errors']}")
            raise ValueError(f"证书验证失败: {validation_result['errors']}")
        
        logger.info("DeepSeek证书获取并验证成功")
        return result
    
    def fetch_tableau_certificates(
        self,
        tableau_domain: Optional[str] = None,
        force: bool = False
    ) -> Dict[str, str]:
        """
        获取Tableau Server证书
        
        Args:
            tableau_domain: Tableau服务器域名,None则从环境变量读取
            force: 强制重新获取
        
        Returns:
            证书文件路径字典
        """
        if tableau_domain is None:
            import os
            tableau_domain = os.getenv("TABLEAU_DOMAIN")
            if not tableau_domain:
                raise ValueError("未指定tableau_domain且环境变量TABLEAU_DOMAIN未设置")
        
        # 解析域名
        from urllib.parse import urlparse
        parsed = urlparse(tableau_domain)
        hostname = parsed.hostname or parsed.path.split('/')[0]
        safe_hostname = hostname.replace('.', '_')
        
        cert_file = self.cert_dir / f"tableau_{safe_hostname}_cert.pem"
        
        # 如果证书已存在且不强制更新,先验证
        if cert_file.exists() and not force:
            logger.info("Tableau证书文件已存在,正在验证...")
            validation_result = self.validator.validate_certificate_file(
                str(cert_file)
            )
            
            if validation_result["valid"]:
                logger.info("现有Tableau证书有效,跳过获取")
                return {
                    "server_cert": str(cert_file),
                    "hostname": hostname,
                    "status": "existing",
                }
            else:
                logger.warning(f"现有Tableau证书无效: {validation_result['errors']}")
        
        # 获取证书
        logger.info(f"正在获取Tableau Server证书: {tableau_domain}")
        result = self.fetcher.fetch_tableau_certificates(
            tableau_domain,
            str(self.cert_dir)
        )
        result["status"] = "fetched"
        
        # 验证获取的证书
        validation_result = self.validator.validate_certificate_file(
            result["server_cert"]
        )
        
        if not validation_result["valid"]:
            logger.error(f"获取的Tableau证书无效: {validation_result['errors']}")
            raise ValueError(f"Tableau证书验证失败: {validation_result['errors']}")
        
        logger.info("Tableau Server证书获取并验证成功")
        return result
    
    def fetch_certificate(
        self,
        hostname: str,
        port: int = 443,
        output_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取指定服务器的证书
        
        Args:
            hostname: 主机名
            port: 端口号
            output_file: 输出文件路径
        
        Returns:
            证书信息和文件路径
        """
        if not output_file:
            output_file = self.cert_dir / f"{hostname.replace('.', '_')}_cert.pem"
        
        cert_info, cert_pem = self.fetcher.fetch_server_certificate(
            hostname,
            port,
            str(output_file)
        )
        
        return {
            "cert_info": cert_info,
            "cert_file": str(output_file),
            "hostname": hostname,
            "port": port,
        }
    
    def validate_certificate(
        self,
        cert_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        验证证书文件
        
        Args:
            cert_file: 证书文件路径,None则验证当前配置的证书
        
        Returns:
            验证结果
        """
        if cert_file is None:
            if self.ssl_config.ca_bundle:
                cert_file = self.ssl_config.ca_bundle
            else:
                # 尝试查找默认证书
                default_cert = self.cert_dir / "deepseek_full_chain.pem"
                if default_cert.exists():
                    cert_file = str(default_cert)
                else:
                    return {
                        "valid": False,
                        "errors": ["未指定证书文件且未找到默认证书"]
                    }
        
        return self.validator.validate_certificate_file(cert_file)
    
    def validate_connection(
        self,
        hostname: str,
        port: int = 443,
        cert_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        验证SSL连接
        
        Args:
            hostname: 主机名
            port: 端口号
            cert_file: 证书文件路径
        
        Returns:
            验证结果
        """
        if cert_file is None and self.ssl_config.ca_bundle:
            cert_file = self.ssl_config.ca_bundle
        
        return self.validator.validate_ssl_connection(
            hostname,
            port,
            cert_file
        )
    
    def validate_certificate_chain(
        self,
        cert_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        验证证书链
        
        Args:
            cert_file: 证书链文件路径
        
        Returns:
            验证结果
        """
        if cert_file is None:
            if self.ssl_config.ca_bundle:
                cert_file = self.ssl_config.ca_bundle
            else:
                default_cert = self.cert_dir / "deepseek_full_chain.pem"
                if default_cert.exists():
                    cert_file = str(default_cert)
                else:
                    return {
                        "valid": False,
                        "errors": ["未指定证书文件且未找到默认证书"]
                    }
        
        return self.validator.validate_certificate_chain(cert_file)
    
    def get_ssl_config(self) -> SSLConfig:
        """获取SSL配置"""
        return self.ssl_config
    
    def update_ssl_config(
        self,
        verify: Optional[bool] = None,
        ca_bundle: Optional[str] = None
    ):
        """
        更新SSL配置
        
        Args:
            verify: 是否启用SSL验证
            ca_bundle: 证书文件路径
        """
        from .config import reset_ssl_config
        
        reset_ssl_config()
        self.ssl_config = get_ssl_config(
            verify=verify,
            ca_bundle=ca_bundle,
            cert_dir=str(self.cert_dir),
            force_new=True
        )
        
        logger.info(f"SSL配置已更新: {self.ssl_config}")
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取证书管理器状态
        
        Returns:
            状态信息字典
        """
        status = {
            "cert_dir": str(self.cert_dir),
            "ssl_config": self.ssl_config.to_dict(),
            "certificates": {},
        }
        
        # 检查证书文件
        cert_files = []
        
        # 扫描证书目录中的所有.pem文件
        if self.cert_dir.exists():
            cert_files = [f.name for f in self.cert_dir.glob("*.pem")]
        
        for cert_file in cert_files:
            cert_path = self.cert_dir / cert_file
            if cert_path.exists():
                validation = self.validator.validate_certificate_file(str(cert_path))
                status["certificates"][cert_file] = {
                    "exists": True,
                    "valid": validation["valid"],
                    "cert_count": validation.get("cert_count", 0),
                    "errors": validation.get("errors", []),
                    "warnings": validation.get("warnings", []),
                }
            else:
                status["certificates"][cert_file] = {
                    "exists": False,
                }
        
        return status
    
    def __repr__(self) -> str:
        """字符串表示"""
        return f"CertificateManager(cert_dir='{self.cert_dir}', ssl_config={self.ssl_config})"


    # ========== Enhanced Methods for Service Registry ==========
    
    def _init_service_registry(self):
        """Initialize service registry (lazy initialization)"""
        if not hasattr(self, '_service_registry'):
            from .service_registry import ServiceRegistry
            self._service_registry = ServiceRegistry(
                cert_dir=str(self.cert_dir),
                timeout=self.fetcher.timeout,
                warning_days=self.validator.warning_days
            )
        return self._service_registry
    
    def _init_app_cert_provider(self):
        """Initialize application certificate provider (lazy initialization)"""
        if not hasattr(self, '_app_cert_provider'):
            from .app_cert_provider import ApplicationCertificateProvider
            from .models import ApplicationCertConfig
            
            # Create default config
            config = ApplicationCertConfig(
                source="self-signed",
                cert_file="app_server.pem",
                key_file="app_server_key.pem",
                ca_bundle="app_ca.pem"
            )
            
            self._app_cert_provider = ApplicationCertificateProvider(
                cert_dir=str(self.cert_dir),
                config=config,
                warning_days=self.validator.warning_days
            )
        return self._app_cert_provider
    
    def register_service(
        self,
        service_id: str,
        hostname: str,
        port: int = 443,
        ca_bundle: Optional[str] = None,
        fetch_on_register: bool = True
    ) -> None:
        """
        Register a third-party service
        
        Args:
            service_id: Unique service identifier
            hostname: Server hostname
            port: Server port
            ca_bundle: CA bundle path
            fetch_on_register: Fetch certificate immediately
        """
        registry = self._init_service_registry()
        registry.register_service(
            service_id=service_id,
            hostname=hostname,
            port=port,
            ca_bundle=ca_bundle,
            fetch_on_register=fetch_on_register
        )
    
    def get_service_ssl_config(
        self,
        service_id: str,
        library: str = "requests"
    ) -> Dict[str, Any]:
        """
        Get SSL config for a specific service
        
        Args:
            service_id: Service identifier
            library: HTTP library ("requests", "httpx", "aiohttp")
            
        Returns:
            Library-specific SSL configuration
        """
        registry = self._init_service_registry()
        ca_bundle = registry.get_service_ca_bundle(service_id)
        
        # Create SSL config with service-specific certificate
        ssl_config = SSLConfig(
            verify=self.ssl_config.verify_ssl,
            ca_bundle=ca_bundle,
            cert_dir=str(self.cert_dir)
        )
        
        # Return library-specific configuration
        if library == "requests":
            return ssl_config.requests_kwargs()
        elif library == "httpx":
            return ssl_config.httpx_client_kwargs()
        elif library == "aiohttp":
            return ssl_config.aiohttp_kwargs()
        else:
            raise ValueError(f"Unsupported library: {library}")
    
    def get_application_ssl_config(
        self,
        component: str = "backend"
    ) -> Dict[str, Any]:
        """
        Get SSL config for application components
        
        Args:
            component: Component name ("backend", "frontend")
            
        Returns:
            SSL configuration for the component
        """
        provider = self._init_app_cert_provider()
        
        if component == "backend":
            cert_file, key_file = provider.get_server_certificate()
            return {
                "cert_file": cert_file,
                "key_file": key_file,
                "ca_bundle": provider.get_ca_bundle() if provider.config.ca_bundle else None
            }
        elif component == "frontend":
            return {
                "ca_bundle": provider.get_ca_bundle() if provider.config.ca_bundle else None
            }
        else:
            raise ValueError(f"Unknown component: {component}")
    
    def migrate_to_company_certificates(
        self,
        cert_file: str,
        key_file: str,
        ca_bundle: Optional[str] = None
    ) -> None:
        """
        Migrate from self-signed to company certificates
        
        Args:
            cert_file: Company certificate file
            key_file: Company private key file
            ca_bundle: Company CA bundle
        """
        provider = self._init_app_cert_provider()
        
        old_source = provider.get_certificate_source()
        logger.info(f"Migrating from {old_source} to company certificates")
        
        # Load company certificates
        provider.load_company_certificate(cert_file, key_file, ca_bundle)
        
        # Update SSL config
        self.update_ssl_config(ca_bundle=ca_bundle)
        
        logger.info("Successfully migrated to company certificates")
    
    def reload_certificates(self) -> None:
        """Reload all certificates from disk"""
        logger.info("Reloading all certificates")
        
        # Reset SSL config
        from .config import reset_ssl_config
        reset_ssl_config()
        
        # Reinitialize SSL config
        self.ssl_config = get_ssl_config(
            verify=self.ssl_config.verify_ssl,
            ca_bundle=self.ssl_config.ca_bundle,
            cert_dir=str(self.cert_dir),
            force_new=True
        )
        
        # Revalidate all service certificates
        if hasattr(self, '_service_registry'):
            for service_id in self._service_registry.list_services():
                try:
                    self._service_registry.validate_service(service_id)
                except Exception as e:
                    logger.error(f"Failed to validate {service_id}: {e}")
        
        logger.info("Certificate reload complete")


    def register_preconfigured_services(self, services: list = None) -> Dict[str, Any]:
        """
        Register pre-configured services
        
        Args:
            services: List of service IDs to register (None = all)
            
        Returns:
            Dictionary with registration results
        """
        from .preconfig import register_preconfigured_services, PRECONFIGURED_SERVICES
        
        if services is None:
            # Register all pre-configured services
            return register_preconfigured_services(self)
        else:
            # Register only specified services
            results = {}
            for service_id in services:
                if service_id not in PRECONFIGURED_SERVICES:
                    results[service_id] = {
                        "status": "failed",
                        "error": f"Service '{service_id}' is not pre-configured"
                    }
                    continue
                
                config = PRECONFIGURED_SERVICES[service_id]
                try:
                    self.register_service(
                        service_id=service_id,
                        hostname=config["hostname"],
                        port=config["port"],
                        ca_bundle=config["ca_bundle"],
                        fetch_on_register=config["auto_fetch"]
                    )
                    results[service_id] = {"status": "registered"}
                except Exception as e:
                    results[service_id] = {"status": "failed", "error": str(e)}
            
            return results
    
    def register_tableau_service(
        self,
        hostname: str = None,
        port: int = 443,
        ca_bundle: str = None,
        fetch_on_register: bool = False
    ) -> Dict[str, Any]:
        """
        Register Tableau Server service with dynamic hostname support
        
        This is a convenience method for registering Tableau Server,
        which supports dynamic hostname from environment variables.
        
        Args:
            hostname: Tableau Server hostname (if None, reads from TABLEAU_DOMAIN env var)
            port: Tableau Server port (default: 443)
            ca_bundle: CA bundle filename (default: auto-generated from hostname)
            fetch_on_register: Whether to fetch certificate immediately (default: False)
            
        Returns:
            Registration result dictionary
            
        Example:
            # Using environment variable
            manager.register_tableau_service()
            
            # Using explicit hostname
            manager.register_tableau_service(hostname='cpse.cpgroup.cn')
        """
        from .preconfig import register_tableau_service
        return register_tableau_service(
            self,
            hostname=hostname,
            port=port,
            ca_bundle=ca_bundle,
            fetch_on_register=fetch_on_register
        )
