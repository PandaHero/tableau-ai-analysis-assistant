"""
Configuration File Parser Module

Provides YAML configuration file parsing with environment variable substitution.
"""
import os
import re
from typing import Dict, Any, Optional
from pathlib import Path
import logging

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)


class ConfigurationParser:
    """
    Configuration file parser with environment variable substitution
    
    Supports:
    - YAML configuration files
    - Environment variable substitution (${VAR_NAME})
    - Configuration validation
    - Default values
    
    Usage:
        parser = ConfigurationParser()
        config = parser.load_config("cert_config.yaml")
    """
    
    def __init__(self):
        """Initialize the configuration parser"""
        if yaml is None:
            logger.warning("PyYAML not installed, YAML config files not supported")
        
        self._env_var_pattern = re.compile(r'\$\{([^}]+)\}')
    
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """
        Load configuration from YAML file
        
        Args:
            config_file: Path to configuration file
            
        Returns:
            Configuration dictionary
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If YAML parsing fails
        """
        config_path = Path(config_file)
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        
        if yaml is None:
            raise ImportError("PyYAML is required for YAML config files. Install with: pip install pyyaml")
        
        logger.info(f"Loading configuration from: {config_file}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_text = f.read()
            
            # Substitute environment variables
            config_text = self._substitute_env_vars(config_text)
            
            # Parse YAML
            config = yaml.safe_load(config_text)
            
            if config is None:
                config = {}
            
            logger.info(f"Configuration loaded successfully")
            return config
            
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse YAML configuration: {e}")
            raise ValueError(f"Invalid YAML configuration: {e}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def _substitute_env_vars(self, text: str) -> str:
        """
        Substitute environment variables in text
        
        Supports ${VAR_NAME} syntax. If variable is not set, keeps the original text.
        Special handling for TABLEAU_HOSTNAME and TABLEAU_PORT:
        - If not set, automatically parse from TABLEAU_DOMAIN
        
        Args:
            text: Text with environment variable placeholders
            
        Returns:
            Text with substituted values
        """
        # 自动从 TABLEAU_DOMAIN 解析 TABLEAU_HOSTNAME 和 TABLEAU_PORT
        self._ensure_tableau_env_vars()
        
        def replace_var(match):
            var_name = match.group(1)
            var_value = os.environ.get(var_name)
            
            if var_value is None:
                logger.warning(f"Environment variable '{var_name}' not set, keeping placeholder")
                return match.group(0)
            
            logger.debug(f"Substituting ${{{var_name}}} with value from environment")
            return var_value
        
        return self._env_var_pattern.sub(replace_var, text)
    
    def _ensure_tableau_env_vars(self) -> None:
        """
        确保 TABLEAU_HOSTNAME 和 TABLEAU_PORT 环境变量存在
        
        如果没有设置，从 TABLEAU_DOMAIN 自动解析
        例如: https://cpse.cpgroup.cn:11080 -> hostname=cpse.cpgroup.cn, port=11080
        """
        from urllib.parse import urlparse
        
        # 如果已经设置了，直接返回
        if os.environ.get('TABLEAU_HOSTNAME') and os.environ.get('TABLEAU_PORT'):
            return
        
        tableau_domain = os.environ.get('TABLEAU_DOMAIN')
        if not tableau_domain:
            return
        
        try:
            parsed = urlparse(tableau_domain)
            hostname = parsed.hostname
            port = parsed.port
            
            # 如果没有端口，根据协议设置默认端口
            if port is None:
                port = 443 if parsed.scheme == 'https' else 80
            
            if hostname and not os.environ.get('TABLEAU_HOSTNAME'):
                os.environ['TABLEAU_HOSTNAME'] = hostname
                logger.debug(f"Auto-set TABLEAU_HOSTNAME={hostname} from TABLEAU_DOMAIN")
            
            if port and not os.environ.get('TABLEAU_PORT'):
                os.environ['TABLEAU_PORT'] = str(port)
                logger.debug(f"Auto-set TABLEAU_PORT={port} from TABLEAU_DOMAIN")
                
        except Exception as e:
            logger.warning(f"Failed to parse TABLEAU_DOMAIN: {e}")
    
    def validate_config(
        self,
        config: Dict[str, Any],
        check_file_paths: bool = False
    ) -> Dict[str, Any]:
        """
        Validate configuration structure
        
        Args:
            config: Configuration dictionary
            check_file_paths: Whether to check if file paths exist
            
        Returns:
            Validation result with 'valid' flag and 'errors' list
        """
        errors = []
        warnings = []
        
        # Validate global settings
        if 'cert_dir' in config:
            if not isinstance(config['cert_dir'], str):
                errors.append("'cert_dir' must be a string")
            elif check_file_paths:
                cert_dir = Path(config['cert_dir'])
                if not cert_dir.exists():
                    warnings.append(f"Certificate directory does not exist: {config['cert_dir']}")
        
        if 'verify_ssl' in config:
            if not isinstance(config['verify_ssl'], bool):
                errors.append("'verify_ssl' must be a boolean")
        
        if 'warning_days' in config:
            if not isinstance(config['warning_days'], int) or config['warning_days'] < 0:
                errors.append("'warning_days' must be a non-negative integer")
        
        # Validate application configuration
        if 'application' in config:
            app_config = config['application']
            
            if not isinstance(app_config, dict):
                errors.append("'application' must be a dictionary")
            else:
                if 'source' in app_config:
                    if app_config['source'] not in ['self-signed', 'company']:
                        errors.append("'application.source' must be 'self-signed' or 'company'")
                
                if 'backend' in app_config:
                    backend = app_config['backend']
                    if not isinstance(backend, dict):
                        errors.append("'application.backend' must be a dictionary")
                    else:
                        if 'cert_file' not in backend:
                            errors.append("'application.backend.cert_file' is required")
                        if 'key_file' not in backend:
                            errors.append("'application.backend.key_file' is required")
        
        # Validate services configuration
        if 'services' in config:
            services = config['services']
            
            if not isinstance(services, dict):
                errors.append("'services' must be a dictionary")
            else:
                for service_id, service_config in services.items():
                    if not isinstance(service_config, dict):
                        errors.append(f"Service '{service_id}' configuration must be a dictionary")
                        continue
                    
                    if 'hostname' not in service_config:
                        errors.append(f"Service '{service_id}' missing required field 'hostname'")
                    
                    if 'port' in service_config:
                        port = service_config['port']
                        if not isinstance(port, int) or port < 1 or port > 65535:
                            errors.append(f"Service '{service_id}' port must be between 1 and 65535")
                    
                    # Check certificate file paths if requested
                    if check_file_paths and 'ca_bundle' in service_config:
                        ca_bundle = service_config['ca_bundle']
                        cert_dir = Path(config.get('cert_dir', 'tableau_assistant/certs'))
                        cert_path = Path(ca_bundle)
                        
                        if not cert_path.is_absolute():
                            cert_path = cert_dir / cert_path
                        
                        if not cert_path.exists():
                            warnings.append(f"Service '{service_id}' certificate file not found: {ca_bundle}")
        
        # Check application certificate files if requested
        if check_file_paths and 'application' in config:
            app_config = config['application']
            cert_dir = Path(config.get('cert_dir', 'tableau_assistant/certs'))
            
            if 'backend' in app_config:
                backend = app_config['backend']
                
                if 'cert_file' in backend:
                    cert_file = Path(backend['cert_file'])
                    if not cert_file.is_absolute():
                        cert_file = cert_dir / cert_file
                    if not cert_file.exists():
                        warnings.append(f"Application certificate file not found: {backend['cert_file']}")
                
                if 'key_file' in backend:
                    key_file = Path(backend['key_file'])
                    if not key_file.is_absolute():
                        key_file = cert_dir / key_file
                    if not key_file.exists():
                        warnings.append(f"Application key file not found: {backend['key_file']}")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    def get_default_config(self) -> Dict[str, Any]:
        """
        Get default configuration
        
        Returns:
            Default configuration dictionary
        """
        return {
            'cert_dir': 'tableau_assistant/certs',
            'verify_ssl': True,
            'warning_days': 30,
            'application': {
                'source': 'self-signed',
                'backend': {
                    'cert_file': 'app_server.pem',
                    'key_file': 'app_server_key.pem'
                },
                'ca_bundle': 'app_ca.pem'
            },
            'services': {}
        }
    
    def merge_configs(
        self,
        *configs: Dict[str, Any],
        precedence: str = "last"
    ) -> Dict[str, Any]:
        """
        Merge multiple configuration dictionaries
        
        Args:
            *configs: Configuration dictionaries to merge
            precedence: Merge strategy - "last" (later configs override) or "first" (earlier configs take precedence)
            
        Returns:
            Merged configuration dictionary
        """
        if not configs:
            return {}
        
        if precedence == "first":
            configs = reversed(configs)
        
        result = {}
        
        for config in configs:
            result = self._deep_merge(result, config)
        
        return result
    
    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep merge two dictionaries
        
        Args:
            base: Base dictionary
            override: Override dictionary
            
        Returns:
            Merged dictionary
        """
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def load_config_with_precedence(
        self,
        config_file: Optional[str] = None,
        env_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Load configuration with precedence rules
        
        Precedence (highest to lowest):
        1. Environment variables (env_config)
        2. Configuration file
        3. Defaults
        
        Args:
            config_file: Path to configuration file (optional)
            env_config: Configuration from environment variables (optional)
            
        Returns:
            Merged configuration dictionary
        """
        # Start with defaults
        config = self.get_default_config()
        
        # Load from file if provided
        if config_file and Path(config_file).exists():
            try:
                file_config = self.load_config(config_file)
                config = self.merge_configs(config, file_config)
            except Exception as e:
                logger.warning(f"Failed to load config file, using defaults: {e}")
        
        # Apply environment config (highest precedence)
        if env_config:
            config = self.merge_configs(config, env_config)
        
        return config
    
    def extract_env_config(self) -> Dict[str, Any]:
        """
        Extract configuration from environment variables
        
        Supported environment variables:
        - CERT_DIR: Certificate directory
        - LLM_VERIFY_SSL: Enable/disable SSL verification
        - LLM_CA_BUNDLE: CA bundle path
        - CERT_WARNING_DAYS: Warning days before expiration
        
        Returns:
            Configuration dictionary from environment
        """
        env_config = {}
        
        # Global settings
        if 'CERT_DIR' in os.environ:
            env_config['cert_dir'] = os.environ['CERT_DIR']
        
        if 'LLM_VERIFY_SSL' in os.environ:
            verify_ssl = os.environ['LLM_VERIFY_SSL'].lower()
            env_config['verify_ssl'] = verify_ssl in ('true', '1', 'yes', 'on')
        
        if 'CERT_WARNING_DAYS' in os.environ:
            try:
                env_config['warning_days'] = int(os.environ['CERT_WARNING_DAYS'])
            except ValueError:
                logger.warning(f"Invalid CERT_WARNING_DAYS value: {os.environ['CERT_WARNING_DAYS']}")
        
        # Application certificate source
        if 'APP_CERT_SOURCE' in os.environ:
            if 'application' not in env_config:
                env_config['application'] = {}
            env_config['application']['source'] = os.environ['APP_CERT_SOURCE']
        
        # Company certificates
        if 'COMPANY_CERT_FILE' in os.environ:
            if 'application' not in env_config:
                env_config['application'] = {}
            if 'company' not in env_config['application']:
                env_config['application']['company'] = {}
            env_config['application']['company']['cert_file'] = os.environ['COMPANY_CERT_FILE']
        
        if 'COMPANY_KEY_FILE' in os.environ:
            if 'application' not in env_config:
                env_config['application'] = {}
            if 'company' not in env_config['application']:
                env_config['application']['company'] = {}
            env_config['application']['company']['key_file'] = os.environ['COMPANY_KEY_FILE']
        
        if 'COMPANY_CA_BUNDLE' in os.environ:
            if 'application' not in env_config:
                env_config['application'] = {}
            if 'company' not in env_config['application']:
                env_config['application']['company'] = {}
            env_config['application']['company']['ca_bundle'] = os.environ['COMPANY_CA_BUNDLE']
        
        return env_config
