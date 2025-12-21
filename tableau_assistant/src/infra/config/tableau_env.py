"""
Tableau 多环境配置管理

支持同时配置多个 Tableau 环境（Cloud 和 Server），
根据前端传入的域名自动匹配对应的认证凭证。
"""
import os
import logging
from dataclasses import dataclass
from typing import Optional, Dict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class TableauEnvConfig:
    """单个 Tableau 环境配置"""
    domain: str
    site: str
    api_version: str
    user: str
    jwt_client_id: str
    jwt_secret_id: str
    jwt_secret: str
    pat_name: str
    pat_secret: str
    
    @property
    def hostname(self) -> str:
        """提取域名主机部分"""
        parsed = urlparse(self.domain)
        return parsed.netloc or self.domain


class TableauEnvironmentManager:
    """
    Tableau 多环境管理器
    
    从环境变量加载多套配置，支持：
    - TABLEAU_CLOUD_* : Tableau Cloud 配置
    - TABLEAU_SERVER_* : Tableau Server 配置
    - TABLEAU_* : 默认配置（兼容旧代码）
    """
    
    # 环境前缀映射
    ENV_PREFIXES = {
        "cloud": "TABLEAU_CLOUD_",
        "server": "TABLEAU_SERVER_",
        "default": "TABLEAU_",
    }
    
    def __init__(self):
        self._configs: Dict[str, TableauEnvConfig] = {}
        self._domain_map: Dict[str, str] = {}  # hostname -> env_key
        self._load_all_configs()
    
    def _load_all_configs(self) -> None:
        """加载所有环境配置"""
        # 先加载命名环境
        for env_key, prefix in self.ENV_PREFIXES.items():
            if env_key == "default":
                continue
            config = self._load_config_with_prefix(prefix)
            if config:
                self._configs[env_key] = config
                self._domain_map[config.hostname.lower()] = env_key
                logger.info(f"已加载 Tableau 环境: {env_key} ({config.domain})")
        
        # 加载默认配置
        default_config = self._load_config_with_prefix("TABLEAU_")
        if default_config:
            self._configs["default"] = default_config
            # 默认配置也加入域名映射（如果还没有）
            hostname = default_config.hostname.lower()
            if hostname not in self._domain_map:
                self._domain_map[hostname] = "default"
    
    def _load_config_with_prefix(self, prefix: str) -> Optional[TableauEnvConfig]:
        """使用指定前缀加载配置"""
        domain = os.getenv(f"{prefix}DOMAIN", "")
        if not domain:
            return None
        
        return TableauEnvConfig(
            domain=domain,
            site=os.getenv(f"{prefix}SITE", ""),
            api_version=os.getenv(f"{prefix}API_VERSION", "3.24"),
            user=os.getenv(f"{prefix}USER", ""),
            jwt_client_id=os.getenv(f"{prefix}JWT_CLIENT_ID", ""),
            jwt_secret_id=os.getenv(f"{prefix}JWT_SECRET_ID", ""),
            jwt_secret=os.getenv(f"{prefix}JWT_SECRET", ""),
            pat_name=os.getenv(f"{prefix}PAT_NAME", ""),
            pat_secret=os.getenv(f"{prefix}PAT_SECRET", ""),
        )
    
    def _get_first_available(self) -> Optional[TableauEnvConfig]:
        """获取第一个可用的配置（优先 cloud，其次 server）"""
        for key in ["cloud", "server"]:
            if key in self._configs:
                return self._configs[key]
        return None
    
    def get_config(self, domain: Optional[str] = None, context: Optional[str] = None) -> TableauEnvConfig:
        """
        获取 Tableau 配置
        
        Args:
            domain: Tableau 域名（可选），如 "https://10ax.online.tableau.com"
                   如果不提供，根据 context 或返回第一个可用配置
            context: Tableau 运行环境（可选），如 "desktop", "server", "cloud"
                    当 domain 为空时，用于推断应该使用哪个配置
        
        Returns:
            匹配的环境配置
        
        Raises:
            ValueError: 如果找不到匹配的配置
        """
        if not domain:
            # 根据 context 推断配置
            if context:
                logger.info(f"根据 context '{context}' 推断 Tableau 配置")
                if context == "cloud":
                    # 明确是 Tableau Cloud 环境
                    if "cloud" in self._configs:
                        logger.info("使用 Tableau Cloud 配置")
                        return self._configs["cloud"]
                elif context == "server":
                    # 明确是 Tableau Server 环境（在 Server 上运行）
                    if "server" in self._configs:
                        logger.info("使用 Tableau Server 配置")
                        return self._configs["server"]
                # desktop 无法确定是连接到 Cloud 还是 Server
                # 由 resolve_datasource_luid 尝试所有环境
            
            # 使用第一个可用配置
            first = self._get_first_available()
            if first:
                return first
            raise ValueError("未配置任何 Tableau 环境，请在 .env 中配置 TABLEAU_CLOUD_* 或 TABLEAU_SERVER_*")
        
        # 解析域名
        parsed = urlparse(domain)
        hostname = (parsed.netloc or domain).lower()
        
        # 精确匹配
        if hostname in self._domain_map:
            env_key = self._domain_map[hostname]
            return self._configs[env_key]
        
        # 模糊匹配（检查是否包含）
        for config_hostname, env_key in self._domain_map.items():
            if hostname in config_hostname or config_hostname in hostname:
                logger.info(f"模糊匹配 Tableau 环境: {hostname} -> {env_key}")
                return self._configs[env_key]
        
        # 检查是否是 Tableau Cloud
        if "online.tableau.com" in hostname:
            if "cloud" in self._configs:
                return self._configs["cloud"]
        
        # 回退到第一个可用配置
        first = self._get_first_available()
        if first:
            logger.warning(f"未找到匹配的 Tableau 环境: {hostname}，使用 {first.domain}")
            return first
        
        raise ValueError(f"未找到匹配的 Tableau 环境配置: {domain}")
    
    def get_all_domains(self) -> list[str]:
        """获取所有已配置的域名"""
        return [config.domain for config in self._configs.values()]
    
    def is_cloud(self, domain: Optional[str] = None) -> bool:
        """检查是否是 Tableau Cloud"""
        if not domain:
            domain = self._configs.get("default", TableauEnvConfig("", "", "", "", "", "", "", "", "")).domain
        return "online.tableau.com" in domain.lower()


# 全局实例
_env_manager: Optional[TableauEnvironmentManager] = None


def get_tableau_env_manager() -> TableauEnvironmentManager:
    """获取 Tableau 环境管理器单例"""
    global _env_manager
    if _env_manager is None:
        _env_manager = TableauEnvironmentManager()
    return _env_manager


def get_tableau_config(domain: Optional[str] = None, context: Optional[str] = None) -> TableauEnvConfig:
    """
    获取 Tableau 配置的便捷函数
    
    Args:
        domain: Tableau 域名（可选）
        context: Tableau 运行环境（可选），如 "desktop", "server", "cloud"
    
    Returns:
        匹配的环境配置
    """
    return get_tableau_env_manager().get_config(domain, context)
