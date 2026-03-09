"""测试配置加载器

加载和管理测试配置：
- 从 YAML 文件加载配置
- 支持环境变量覆盖
- 验证配置完整性
- 提供配置查询接口
"""

from typing import Dict, Any, Optional
from pathlib import Path
import yaml
import os
import logging
import re


logger = logging.getLogger(__name__)


class TestConfigLoader:
    """测试配置加载器
    
    职责：
    - 加载测试配置文件
    - 支持环境变量覆盖（${VAR_NAME} 语法）
    - 验证配置完整性
    - 提供配置查询接口
    
    使用方式：
        config = TestConfigLoader.load_config()
        timeout = TestConfigLoader.get_timeout("semantic_parsing")
    """
    
    _config: Optional[Dict[str, Any]] = None

    @classmethod
    def _get_project_root(cls) -> Path:
        """获取仓库根目录。"""
        return Path(__file__).resolve().parents[3]

    @classmethod
    def _resolve_repo_path(cls, value: str) -> Path:
        """将仓库相对路径解析为绝对路径。"""
        path = Path(value)
        if path.is_absolute():
            return path
        return cls._get_project_root() / path
    
    @classmethod
    def load_config(cls, config_path: Optional[Path] = None) -> Dict[str, Any]:
        """加载测试配置
        
        Args:
            config_path: 配置文件路径，默认使用 test_config.yaml
        
        Returns:
            配置字典
        
        Raises:
            FileNotFoundError: 如果配置文件不存在
            ValueError: 如果配置格式不正确
        """
        # 如果已加载，直接返回缓存的配置
        if cls._config is not None:
            return cls._config
        
        # 确定配置文件路径
        if config_path is None:
            config_path = Path(__file__).parent / "test_config.yaml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        logger.info(f"加载测试配置: {config_path}")
        
        # 加载 YAML 配置
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # 环境变量替换
        cls._replace_env_vars(config)
        
        # 验证配置
        cls._validate_config(config)
        
        # 缓存配置
        cls._config = config
        
        logger.info("测试配置加载完成")
        return config
    
    @classmethod
    def _replace_env_vars(cls, config: Dict[str, Any]):
        """递归替换环境变量
        
        支持 ${VAR_NAME} 语法。
        如果环境变量不存在，保持原值。
        
        Args:
            config: 配置字典（会被原地修改）
        """
        env_var_pattern = re.compile(r'\$\{([^}]+)\}')
        
        def replace_value(value):
            """替换单个值中的环境变量"""
            if isinstance(value, str):
                # 查找所有环境变量引用
                matches = env_var_pattern.findall(value)
                for var_name in matches:
                    env_value = os.environ.get(var_name)
                    if env_value is not None:
                        value = value.replace(f"${{{var_name}}}", env_value)
                        logger.debug(f"环境变量替换: ${{{var_name}}} -> {env_value}")
                    else:
                        logger.warning(f"环境变量未设置: {var_name}")
            return value
        
        def replace_recursive(obj):
            """递归替换配置中的环境变量"""
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(value, dict):
                        replace_recursive(value)
                    elif isinstance(value, list):
                        obj[key] = [replace_value(item) for item in value]
                    else:
                        obj[key] = replace_value(value)
            elif isinstance(obj, list):
                return [replace_value(item) for item in obj]
        
        replace_recursive(config)
    
    @classmethod
    def _validate_config(cls, config: Dict[str, Any]):
        """验证配置完整性
        
        检查必需的配置键是否存在。
        
        Args:
            config: 配置字典
        
        Raises:
            ValueError: 如果配置缺少必需的键
        """
        required_keys = ["mode", "timeouts", "database", "test_data"]
        
        for key in required_keys:
            if key not in config:
                raise ValueError(f"配置缺少必需的键: {key}")
        
        logger.debug("配置验证通过")
    
    @classmethod
    def get_timeout(cls, operation: str) -> float:
        """获取操作超时时间
        
        Args:
            operation: 操作名称（如 semantic_parsing, field_mapping）
        
        Returns:
            超时时间（秒）
        """
        config = cls.load_config()
        timeouts = config.get("timeouts", {})
        timeout = timeouts.get(operation, timeouts.get("default", 60.0))
        
        logger.debug(f"获取超时配置: {operation} = {timeout}s")
        return timeout
    
    @classmethod
    def get_test_data_dir(cls) -> Path:
        """获取测试数据目录
        
        Returns:
            测试数据目录路径
        """
        config = cls.load_config()
        data_dir = cls._resolve_repo_path(config["test_data"]["dir"])
        
        logger.debug(f"测试数据目录: {data_dir}")
        return data_dir
    
    @classmethod
    def get_database_path(cls, db_name: str = "test_storage") -> Path:
        """获取测试数据库路径
        
        Args:
            db_name: 数据库名称（test_storage, test_data_model, test_field_semantic）
        
        Returns:
            数据库文件路径
        """
        config = cls.load_config()
        db_path = cls._resolve_repo_path(config["database"][db_name])
        
        logger.debug(f"数据库路径 [{db_name}]: {db_path}")
        return db_path

    @classmethod
    def get_log_file_path(cls) -> Path:
        """获取集成测试日志文件路径。"""
        config = cls.load_config()
        logging_config = config.get("logging", {})
        log_file = logging_config.get(
            "file",
            "analytics_assistant/tests/test_outputs/integration_tests.log",
        )
        return cls._resolve_repo_path(log_file)

    @classmethod
    def get_tableau_config(cls) -> Dict[str, Any]:
        """获取 Tableau 集成测试配置。"""
        config = cls.load_config()
        return config.get("tableau", {})
    
    @classmethod
    def get_performance_config(cls) -> Dict[str, Any]:
        """获取性能配置
        
        Returns:
            性能配置字典
        """
        config = cls.load_config()
        perf_config = config.get("performance", {})
        
        logger.debug(f"性能配置: {perf_config}")
        return perf_config
    
    @classmethod
    def get_retry_config(cls) -> Dict[str, Any]:
        """获取重试配置
        
        Returns:
            重试配置字典
        """
        config = cls.load_config()
        retry_config = config.get("retry", {})
        
        logger.debug(f"重试配置: {retry_config}")
        return retry_config
    
    @classmethod
    def get_hypothesis_config(cls) -> Dict[str, Any]:
        """获取 Hypothesis（PBT）配置
        
        Returns:
            Hypothesis 配置字典
        """
        config = cls.load_config()
        hypothesis_config = config.get("hypothesis", {})
        
        logger.debug(f"Hypothesis 配置: {hypothesis_config}")
        return hypothesis_config
    
    @classmethod
    def is_performance_monitoring_enabled(cls) -> bool:
        """检查是否启用性能监控
        
        Returns:
            True 如果启用性能监控
        """
        perf_config = cls.get_performance_config()
        enabled = perf_config.get("enable_monitoring", True)
        
        logger.debug(f"性能监控: {'启用' if enabled else '禁用'}")
        return enabled
    
    @classmethod
    def get_mode(cls) -> str:
        """获取测试模式
        
        Returns:
            测试模式（integration, quick, full）
        """
        config = cls.load_config()
        mode = config.get("mode", "integration")
        
        logger.debug(f"测试模式: {mode}")
        return mode
    
    @classmethod
    def reload_config(cls):
        """重新加载配置
        
        清除缓存的配置，强制重新加载。
        """
        cls._config = None
        logger.info("配置缓存已清除，将重新加载")
