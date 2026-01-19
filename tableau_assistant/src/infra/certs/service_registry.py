"""
服务注册模块

管理多个第三方API服务的证书。
"""
from typing import Dict, Optional, Any
from pathlib import Path
import logging
from datetime import datetime, timezone
from dataclasses import dataclass

from tableau_assistant.src.infra.certs.fetcher import CertificateFetcher
from tableau_assistant.src.infra.certs.validator import CertificateValidator


logger = logging.getLogger(__name__)


@dataclass
class ServiceConfig:
    """服务配置"""
    service_id: str
    hostname: str
    port: int = 443
    ca_bundle: Optional[str] = None
    last_fetched: Optional[datetime] = None
    validation_status: str = "unknown"


class ServiceRegistry:
    """
    服务证书注册表
    
    管理多个外部API服务的SSL证书。
    
    使用示例:
        registry = ServiceRegistry()
        registry.register_service("tableau", "tableau.example.com")
        config = registry.get_service_config("tableau")
    """
    
    def __init__(
        self,
        cert_dir: str = "tableau_assistant/src/infra/certs/store",
        timeout: int = 10,
        warning_days: int = 30
    ):
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        
        self._services: Dict[str, ServiceConfig] = {}
        
        self.fetcher = CertificateFetcher(timeout=timeout)
        self.validator = CertificateValidator(warning_days=warning_days)
    
    def register_service(
        self,
        service_id: str,
        hostname: str,
        port: int = 443,
        ca_bundle: Optional[str] = None,
        fetch_on_register: bool = True
    ) -> None:
        """注册服务"""
        config = ServiceConfig(
            service_id=service_id,
            hostname=hostname,
            port=port,
            ca_bundle=ca_bundle
        )
        
        if fetch_on_register and not ca_bundle:
            try:
                cert_paths = self._fetch_service_certificate(config)
                config.ca_bundle = cert_paths.get("server_cert")
                config.last_fetched = datetime.now(timezone.utc)
                config.validation_status = "valid"
            except Exception as e:
                logger.error(f"获取服务 {service_id} 证书失败: {e}")
                config.validation_status = "fetch_failed"
        
        self._services[service_id] = config
        logger.info(f"服务已注册: {service_id} ({hostname}:{port})")
    
    def _fetch_service_certificate(self, config: ServiceConfig) -> Dict[str, str]:
        """获取服务证书"""
        safe_hostname = config.hostname.replace('.', '_')
        cert_file = self.cert_dir / f"{config.service_id}_{safe_hostname}_cert.pem"
        
        _, _ = self.fetcher.fetch_server_certificate(
            config.hostname, config.port, str(cert_file)
        )
        
        return {"server_cert": str(cert_file)}
    
    def get_service_config(self, service_id: str) -> Optional[ServiceConfig]:
        """获取服务配置"""
        return self._services.get(service_id)
    
    def list_services(self) -> Dict[str, ServiceConfig]:
        """列出所有注册的服务"""
        return self._services.copy()
    
    def validate_service(self, service_id: str) -> Dict[str, Any]:
        """验证服务证书"""
        config = self._services.get(service_id)
        if not config:
            return {"valid": False, "errors": [f"服务未注册: {service_id}"]}
        
        if not config.ca_bundle:
            return {"valid": False, "errors": ["未配置证书"]}
        
        return self.validator.validate_certificate_file(config.ca_bundle)


__all__ = ["ServiceRegistry", "ServiceConfig"]
