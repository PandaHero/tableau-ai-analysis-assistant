"""
证书配置模块

提供统一的 SSL 配置接口，支持：
- 从 cert_config.yaml 加载配置
- 环境变量展开 ${VAR_NAME} 或 ${VAR_NAME:-default}
- 多种 HTTP 客户端库的配置格式
"""
import os
import re
import ssl
import logging
from typing import Union, Optional, Dict, Any, Literal
from pathlib import Path
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)


# ============================================================
# 数据模型
# ============================================================

@dataclass
class BackendCertConfig:
    """后端服务器证书配置"""
    cert_file: str = "app_server.pem"
    key_file: str = "app_server_key.pem"


@dataclass
class CompanyCertConfig:
    """公司证书配置"""
    cert_file: str = ""
    key_file: str = ""
    ca_bundle: str = ""
    auto_fetch: bool = False
    fetch_url: str = ""
    auto_refresh: bool = False
    refresh_interval: int = 86400


@dataclass
class ApplicationConfig:
    """应用证书配置"""
    source: Literal["self-signed", "company"] = "self-signed"
    backend: BackendCertConfig = field(default_factory=BackendCertConfig)
    ca_bundle: str = "app_ca.pem"
    company: Optional[CompanyCertConfig] = None


@dataclass
class ServiceCertConfig:
    """第三方服务证书配置"""
    hostname: str = ""
    port: int = 443
    ca_bundle: str = ""
    auto_fetch: Union[bool, str] = False
    use_system_certs: bool = False


@dataclass
class CertConfigData:
    """证书管理器完整配置"""
    cert_dir: str = "tableau_assistant/src/infra/certs/store"
    verify_ssl: bool = True
    warning_days: int = 30
    application: ApplicationConfig = field(default_factory=ApplicationConfig)
    services: Dict[str, ServiceCertConfig] = field(default_factory=dict)
    
    def get_cert_path(self, filename: str) -> Path:
        return Path(self.cert_dir) / filename
    
    def get_app_cert_path(self) -> Path:
        return self.get_cert_path(self.application.backend.cert_file)
    
    def get_app_key_path(self) -> Path:
        return self.get_cert_path(self.application.backend.key_file)
    
    def get_app_ca_path(self) -> Path:
        return self.get_cert_path(self.application.ca_bundle)


# ============================================================
# 配置加载器
# ============================================================

class ConfigLoadError(Exception):
    """配置加载错误"""
    pass


class ConfigLoader:
    """从 cert_config.yaml 加载配置"""
    
    ENV_VAR_PATTERN = re.compile(r'\$\{([^}:]+)(?::-([^}]*))?\}')
    
    def __init__(
        self,
        config_path: str = "cert_config.yaml",
        fallback_path: str = "cert_config.example.yaml"
    ):
        self.config_path = Path(config_path)
        self.fallback_path = Path(fallback_path)
    
    def load(self) -> CertConfigData:
        config_file = self._resolve_config_file()
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigLoadError(f"YAML 解析错误: {e}")
        except Exception as e:
            raise ConfigLoadError(f"读取配置文件失败: {e}")
        
        expanded_data = self._expand_env_vars_recursive(raw_data)
        self._validate_schema(expanded_data)
        return self._parse_config(expanded_data)
    
    def _resolve_config_file(self) -> Path:
        if self.config_path.exists():
            logger.info(f"使用配置文件: {self.config_path}")
            return self.config_path
        if self.fallback_path.exists():
            logger.warning(f"使用示例配置: {self.fallback_path}")
            return self.fallback_path
        raise ConfigLoadError(f"配置文件不存在: {self.config_path}")
    
    def _expand_env_vars(self, value: str) -> str:
        def replace_env_var(match):
            var_name = match.group(1)
            default_value = match.group(2)
            env_value = os.environ.get(var_name)
            if env_value is not None:
                return env_value
            elif default_value is not None:
                return default_value
            return ""
        return self.ENV_VAR_PATTERN.sub(replace_env_var, value)
    
    def _expand_env_vars_recursive(self, data: Any) -> Any:
        if isinstance(data, str):
            return self._expand_env_vars(data)
        elif isinstance(data, dict):
            return {k: self._expand_env_vars_recursive(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._expand_env_vars_recursive(item) for item in data]
        return data
    
    def _validate_schema(self, data: Dict[str, Any]) -> None:
        app_config = data.get("application", {})
        source = app_config.get("source", "self-signed")
        if source not in ("self-signed", "company"):
            raise ConfigLoadError(f"无效的 source: {source}")

    
    def _parse_config(self, data: Dict[str, Any]) -> CertConfigData:
        app_data = data.get("application", {})
        backend_data = app_data.get("backend", {})
        company_data = app_data.get("company")
        
        backend = BackendCertConfig(
            cert_file=backend_data.get("cert_file", "app_server.pem"),
            key_file=backend_data.get("key_file", "app_server_key.pem"),
        )
        
        company = None
        if company_data:
            company = CompanyCertConfig(
                cert_file=company_data.get("cert_file", ""),
                key_file=company_data.get("key_file", ""),
                ca_bundle=company_data.get("ca_bundle", ""),
                auto_fetch=company_data.get("auto_fetch", False),
                fetch_url=company_data.get("fetch_url", ""),
                auto_refresh=company_data.get("auto_refresh", False),
                refresh_interval=company_data.get("refresh_interval", 86400),
            )
        
        application = ApplicationConfig(
            source=app_data.get("source", "self-signed"),
            backend=backend,
            ca_bundle=app_data.get("ca_bundle", "app_ca.pem"),
            company=company,
        )
        
        services_data = data.get("services", {})
        services = {}
        for service_id, svc in services_data.items():
            services[service_id] = ServiceCertConfig(
                hostname=svc.get("hostname", ""),
                port=int(svc.get("port", 443)),
                ca_bundle=svc.get("ca_bundle", ""),
                auto_fetch=svc.get("auto_fetch", False),
            )
        
        return CertConfigData(
            cert_dir=data.get("cert_dir", "tableau_assistant/src/infra/certs/store"),
            verify_ssl=data.get("verify_ssl", True),
            warning_days=data.get("warning_days", 30),
            application=application,
            services=services,
        )


# ============================================================
# SSL 配置类
# ============================================================

class CertificateConfig:
    """SSL 配置，提供多种 HTTP 客户端库的配置格式"""
    
    def __init__(self, verify: bool = True, ca_bundle: Optional[str] = None, cert_dir: Optional[str] = None):
        self.verify_ssl = verify
        self.ca_bundle = ca_bundle or ""
        self.cert_dir = cert_dir or "tableau_assistant/src/infra/certs/store"
        if not self.ca_bundle:
            self._auto_detect_cert_path()
    
    def _auto_detect_cert_path(self):
        cert_filenames = ["full_chain.pem", "ca_bundle.pem", "app_ca.pem"]
        search_paths = [
            Path.cwd() / self.cert_dir,
            Path.cwd() / "tableau_assistant" / "src" / "infra" / "certs" / "store",
        ]
        for search_path in search_paths:
            if not search_path.exists():
                continue
            for filename in cert_filenames:
                cert_path = search_path / filename
                if cert_path.exists():
                    self.ca_bundle = str(cert_path)
                    return
    
    def get_verify_param(self) -> Union[bool, str]:
        if not self.verify_ssl:
            return False
        if self.ca_bundle:
            return self.ca_bundle
        return True
    
    def get_ssl_context(self, check_hostname: bool = True) -> ssl.SSLContext:
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
        """
        获取 httpx 客户端的 SSL 配置
        
        httpx 的 verify 参数支持:
        - bool: True/False
        - str: CA 证书文件路径
        - ssl.SSLContext: SSL 上下文（不推荐，某些场景不兼容）
        
        这里优先返回证书路径字符串，兼容性最好
        """
        if not self.verify_ssl:
            return {"verify": False}
        if self.ca_bundle:
            # 返回证书路径字符串，而不是 SSLContext
            return {"verify": self.ca_bundle}
        return {"verify": True}
    
    def requests_kwargs(self) -> Dict[str, Any]:
        return {"verify": self.get_verify_param()}
    
    def aiohttp_kwargs(self) -> Dict[str, Any]:
        if not self.verify_ssl:
            return {"ssl": False}
        return {"ssl": self.get_ssl_context()}



# ============================================================
# 全局实例和工厂函数
# ============================================================

_global_cert_config: Optional[CertConfigData] = None
_global_ssl_config: Optional[CertificateConfig] = None


def get_cert_config(config_path: str = "cert_config.yaml", force_reload: bool = False) -> CertConfigData:
    """获取证书配置（从 cert_config.yaml 加载）"""
    global _global_cert_config
    if force_reload or _global_cert_config is None:
        loader = ConfigLoader(config_path)
        _global_cert_config = loader.load()
    return _global_cert_config


def get_certificate_config(
    verify: Optional[bool] = None,
    ca_bundle: Optional[str] = None,
    cert_dir: Optional[str] = None,
    force_new: bool = False
) -> CertificateConfig:
    """获取 SSL 配置实例"""
    global _global_ssl_config
    if force_new or _global_ssl_config is None:
        if verify is None and ca_bundle is None:
            try:
                cert_config = get_cert_config()
                verify = cert_config.verify_ssl
                cert_dir = cert_config.cert_dir
            except Exception:
                verify = True
        _global_ssl_config = CertificateConfig(
            verify=verify if verify is not None else True,
            ca_bundle=ca_bundle,
            cert_dir=cert_dir
        )
    return _global_ssl_config


__all__ = [
    "BackendCertConfig",
    "CompanyCertConfig",
    "ApplicationConfig",
    "ServiceCertConfig",
    "CertConfigData",
    "ConfigLoader",
    "ConfigLoadError",
    "CertificateConfig",
    "get_cert_config",
    "get_certificate_config",
]
