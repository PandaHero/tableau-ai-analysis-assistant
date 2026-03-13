# -*- coding: utf-8 -*-
"""
统一应用配置管理器

所有模块的配置都从这里获取，避免配置分散。

使用方式：
    from analytics_assistant.src.infra.config import get_config
    
    config = get_config()
    ai_config = config.get_ai_config()
    storage_config = config.get_storage_config()
"""
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional
from threading import Lock

import yaml

logger = logging.getLogger(__name__)

class ConfigLoadError(Exception):
    """配置加载错误"""
    pass

class AppConfig:
    """
    统一应用配置管理器（单例）
    
    所有模块的配置都从这里获取：
    - AI 模型配置
    - 存储配置
    - RAG 配置
    - 日志配置
    
    特性：
    - 单例模式：全局唯一实例
    - 支持环境变量展开：${VAR_NAME:-default}
    - 自动加载配置文件
    - 线程安全
    """
    
    _instance: Optional['AppConfig'] = None
    _lock = Lock()
    
    # 环境变量模式：${VAR_NAME} 或 ${VAR_NAME:-default}
    ENV_VAR_PATTERN = re.compile(r'\$\{([^}:]+)(?::-([^}]*))?\}')
    
    def __new__(cls, config_path: Optional[str] = None):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径（可选）
        """
        if self._initialized:
            return
        
        self.config_path = Path(config_path) if config_path else self._find_config_path()
        self.fallback_path = self._find_fallback_path()
        self.config: dict[str, Any] = {}
        self._loaded_dotenv_values: dict[str, str] = {}
        
        self._load_dotenv_files()
        self._load_config()
        self._initialized = True
    
    def _find_config_path(self) -> Path:
        """查找配置文件路径"""
        # 尝试多个可能的路径
        candidates = [
            Path("analytics_assistant/config/app.yaml"),  # 从项目根目录运行
            Path("config/app.yaml"),  # 从 analytics_assistant 目录运行
            Path(__file__).parent.parent.parent.parent / "config" / "app.yaml",  # 相对于模块位置
        ]
        
        for path in candidates:
            if path.exists():
                return path
        
        # 默认返回第一个候选路径
        return candidates[0]
    
    def _find_fallback_path(self) -> Path:
        """查找备用配置文件路径"""
        candidates = [
            Path("analytics_assistant/config/app.example.yaml"),
            Path("config/app.example.yaml"),
            Path(__file__).parent.parent.parent.parent / "config" / "app.example.yaml",
        ]
        
        for path in candidates:
            if path.exists():
                return path
        
        return candidates[0]

    def _find_dotenv_paths(self) -> list[Path]:
        """查找支持的 dotenv 文件路径。"""
        active_config_path = self.config_path if self.config_path.exists() else self.fallback_path
        config_dir = active_config_path.resolve().parent

        candidate_roots = [config_dir.parent.parent, config_dir.parent]
        dotenv_paths: list[Path] = []
        seen: set[Path] = set()

        for root in candidate_roots:
            for filename in (".env", ".env.local"):
                path = root / filename
                if path in seen:
                    continue
                seen.add(path)
                dotenv_paths.append(path)

        return dotenv_paths

    def _parse_dotenv_file(self, path: Path) -> dict[str, str]:
        """解析 dotenv 文件。"""
        values: dict[str, str] = {}

        try:
            # Accept UTF-8 BOM because PowerShell often writes `.env` files with BOM on Windows.
            with open(path, "r", encoding="utf-8-sig") as file:
                lines = file.readlines()
        except Exception as exc:
            raise ConfigLoadError(f"dotenv 文件读取失败: {path} ({exc})") from exc

        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[7:].lstrip()

            if "=" not in line:
                logger.warning("忽略格式错误的 dotenv 行: %s:%s", path, line_number)
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                logger.warning("忽略空 dotenv key: %s:%s", path, line_number)
                continue

            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]

            values[key] = value

        return values

    def _apply_dotenv_values(self, values: dict[str, str]) -> None:
        """合并 dotenv 值到当前进程环境，不覆盖真实环境变量。"""
        previous_values = dict(self._loaded_dotenv_values)

        for key, old_value in previous_values.items():
            current_value = os.environ.get(key)
            if current_value == old_value and key not in values:
                os.environ.pop(key, None)

        loaded_values: dict[str, str] = {}
        for key, value in values.items():
            current_value = os.environ.get(key)
            if current_value is None or (key in previous_values and current_value == previous_values[key]):
                os.environ[key] = value
                loaded_values[key] = value

        self._loaded_dotenv_values = loaded_values

    def _load_dotenv_files(self) -> None:
        """在展开 YAML 环境变量前加载 dotenv。"""
        dotenv_values: dict[str, str] = {}

        for path in self._find_dotenv_paths():
            if not path.exists():
                continue
            dotenv_values.update(self._parse_dotenv_file(path))
            logger.info(f"加载 dotenv 文件: {path}")

        self._apply_dotenv_values(dotenv_values)
    
    def _load_config(self):
        """加载配置文件"""
        # 尝试加载主配置文件
        config_file = self.config_path
        if not config_file.exists():
            logger.warning(f"配置文件不存在: {config_file}")
            
            # 尝试备用配置文件
            if self.fallback_path.exists():
                logger.info(f"使用备用配置文件: {self.fallback_path}")
                config_file = self.fallback_path
            else:
                logger.warning("配置文件不存在，使用空配置")
                self.config = {}
                return
        
        # 加载 YAML
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                raw_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigLoadError(f"YAML 解析错误: {e}")
        except Exception as e:
            raise ConfigLoadError(f"配置文件读取失败: {e}")
        
        # 展开环境变量
        self.config = self._expand_env_vars(raw_data)
        
        # 解析相对路径为绝对路径
        self._resolve_paths()
        
        logger.info(f"配置加载成功: {config_file}")
    
    def _get_project_root(self) -> Path:
        """获取项目根目录
        
        通过配置文件位置确定项目根目录。
        配置文件位于 analytics_assistant/config/app.yaml，
        所以项目根目录是配置文件向上 2 级。
        
        注意：需要先将相对路径转换为绝对路径，再计算项目根目录。
        """
        # 使用实际找到的配置文件路径来确定项目根目录
        if self.config_path.exists():
            # 先转换为绝对路径
            abs_config_path = self.config_path.resolve()
            # config_path: .../analytics_assistant/config/app.yaml
            # 项目根目录: 向上 2 级（config -> analytics_assistant -> project_root）
            return abs_config_path.parent.parent.parent
        
        # 备用方案：通过模块位置确定
        # 当前文件: analytics_assistant/src/infra/config/config_loader.py
        # 项目根目录: 向上 5 级
        return Path(__file__).resolve().parent.parent.parent.parent.parent
    
    def _resolve_paths(self):
        """解析配置中的相对路径为绝对路径
        
        将以 'analytics_assistant/' 开头的相对路径解析为绝对路径，
        确保无论从哪个工作目录运行，路径都是一致的。
        """
        project_root = self._get_project_root()
        
        # 需要解析路径的配置项
        path_keys = [
            ('storage', 'connection_string'),
            ('vector_storage', 'index_dir'),
            ('vector_storage', 'chroma', 'persist_directory'),
            ('ssl', 'cert_dir'),
            ('rag_service', 'index', 'persist_directory'),
        ]
        
        # 存储命名空间中的 connection_string
        namespaces = self.config.get('storage', {}).get('namespaces', {})
        for ns_name in namespaces:
            path_keys.append(('storage', 'namespaces', ns_name, 'connection_string'))
        
        # RAG 服务预定义索引中的 persist_directory
        indexes = self.config.get('rag_service', {}).get('indexes', {})
        for idx_name in indexes:
            path_keys.append(('rag_service', 'indexes', idx_name, 'persist_directory'))
        
        for keys in path_keys:
            self._resolve_path_in_config(keys, project_root)
    
    def _resolve_path_in_config(self, keys: tuple, project_root: Path):
        """解析配置中指定路径的值
        
        Args:
            keys: 配置键路径，如 ('storage', 'connection_string')
            project_root: 项目根目录
        """
        # 遍历到倒数第二层
        current = self.config
        for key in keys[:-1]:
            if not isinstance(current, dict) or key not in current:
                return
            current = current[key]
        
        # 获取并解析最后一个键的值
        last_key = keys[-1]
        if not isinstance(current, dict) or last_key not in current:
            return
        
        value = current[last_key]
        if not isinstance(value, str) or not value:
            return
        
        # 如果以 analytics_assistant/ 开头，解析为绝对路径
        if value.startswith('analytics_assistant/') or value.startswith('analytics_assistant\\'):
            resolved = project_root / value
            current[last_key] = str(resolved)
            logger.debug(f"路径解析: {value} -> {resolved}")
    
    def _expand_env_vars(self, data: Any) -> Any:
        """
        递归展开环境变量
        
        支持格式：
        - ${VAR_NAME}: 读取环境变量，不存在则保持原样
        - ${VAR_NAME:-default}: 读取环境变量，不存在则使用默认值
        """
        if isinstance(data, str):
            return self._expand_string(data)
        elif isinstance(data, dict):
            return {k: self._expand_env_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._expand_env_vars(item) for item in data]
        else:
            return data
    
    def _expand_string(self, value: str) -> str:
        """展开字符串中的环境变量"""
        def replace_match(match):
            var_name = match.group(1)
            default_value = match.group(2) if match.group(2) is not None else match.group(0)
            
            # 获取环境变量
            env_value = os.environ.get(var_name)
            
            if env_value is not None:
                return env_value
            else:
                # 使用默认值
                return default_value
        
        return self.ENV_VAR_PATTERN.sub(replace_match, value)
    
    # ============================================
    # AI 配置
    # ============================================
    
    def get_ai_config(self) -> dict[str, Any]:
        """获取 AI 配置"""
        return self.config.get('ai', {})
    
    def get_llm_models(self) -> list:
        """获取 LLM 模型配置"""
        return self.get_ai_config().get('llm_models', [])
    
    def get_embedding_models(self) -> list:
        """获取 Embedding 模型配置"""
        return self.get_ai_config().get('embedding_models', [])
    
    def get_ai_global_config(self) -> dict[str, Any]:
        """获取 AI 全局配置"""
        return self.get_ai_config().get('global', {})
    
    # ============================================
    # 存储配置
    # ============================================
    
    def get_storage_config(self) -> dict[str, Any]:
        """获取存储配置"""
        return self.config.get('storage', {})
    
    def get_storage_backend(self) -> str:
        """获取存储后端类型"""
        return self.get_storage_config().get('backend', 'sqlite')
    
    def get_storage_connection_string(self) -> Optional[str]:
        """获取存储连接字符串"""
        return self.get_storage_config().get('connection_string')
    
    def get_storage_ttl(self) -> Optional[int]:
        """获取存储默认 TTL"""
        return self.get_storage_config().get('ttl')
    
    def get_storage_namespace_config(self, namespace: str) -> dict[str, Any]:
        """获取存储命名空间配置"""
        namespaces = self.get_storage_config().get('namespaces', {})
        return namespaces.get(namespace, {})
    
    # ============================================
    # RAG 配置
    # ============================================
    
    def get_rag_config(self) -> dict[str, Any]:
        """获取 RAG 配置"""
        return self.config.get('rag', {})
    
    # ============================================
    # RAG 服务层配置
    # ============================================
    
    def get_rag_service_config(self) -> dict[str, Any]:
        """获取 RAG 服务层配置"""
        return self.config.get('rag_service', {})
    
    def get_rag_service_index_config(self) -> dict[str, Any]:
        """获取 RAG 服务索引管理配置"""
        return self.get_rag_service_config().get('index', {})
    
    def get_rag_service_embedding_config(self) -> dict[str, Any]:
        """获取 RAG 服务 Embedding 配置"""
        return self.get_rag_service_config().get('embedding', {})
    
    def get_rag_service_retrieval_config(self) -> dict[str, Any]:
        """获取 RAG 服务检索配置"""
        return self.get_rag_service_config().get('retrieval', {})
    
    def get_rag_service_indexes_config(self) -> dict[str, Any]:
        """获取 RAG 服务预定义索引配置"""
        return self.get_rag_service_config().get('indexes', {})
    
    # ============================================
    # Tableau 配置
    # ============================================
    
    def get_tableau_config(self) -> dict[str, Any]:
        """获取 Tableau 配置"""
        return self.config.get('tableau', {})
    
    def get_tableau_domain(self) -> str:
        """获取 Tableau 域名"""
        return self.get_tableau_config().get('domain', '')
    
    def get_tableau_site(self) -> str:
        """获取 Tableau site"""
        return self.get_tableau_config().get('site', '')
    
    def get_tableau_api_version(self) -> str:
        """获取 Tableau API 版本"""
        return self.get_tableau_config().get('api_version', '3.21')
    
    def get_tableau_jwt_config(self) -> dict[str, Any]:
        """获取 Tableau JWT 配置"""
        return self.get_tableau_config().get('jwt', {})
    
    def get_tableau_pat_config(self) -> dict[str, Any]:
        """获取 Tableau PAT 配置"""
        return self.get_tableau_config().get('pat', {})
    
    def get_tableau_token_cache_ttl(self) -> int:
        """获取 Tableau token 缓存 TTL（秒）"""
        return self.get_tableau_config().get('token_cache_ttl', 600)
    
    # ============================================
    # VizQL 配置
    # ============================================
    
    def get_vizql_config(self) -> dict[str, Any]:
        """获取 VizQL 配置"""
        return self.config.get('vizql', {})
    
    def get_vizql_timeout(self) -> int:
        """获取 VizQL 请求超时（秒）"""
        return self.get_vizql_config().get('timeout', 60)
    
    def get_vizql_max_retries(self) -> int:
        """获取 VizQL 最大重试次数"""
        return self.get_vizql_config().get('max_retries', 3)
    
    # ============================================
    # SSL 配置
    # ============================================
    
    def get_ssl_config(self) -> dict[str, Any]:
        """获取 SSL 配置"""
        return self.config.get('ssl', {})
    
    def get_ssl_verify(self) -> bool:
        """获取是否验证 SSL 证书"""
        return self.get_ssl_config().get('verify', True)
    
    def get_ssl_ca_bundle(self) -> Optional[str]:
        """获取 SSL CA 证书路径"""
        return self.get_ssl_config().get('ca_bundle')
    
    # ============================================
    # 日志配置（未来扩展）
    # ============================================
    
    def get_logging_config(self) -> dict[str, Any]:
        """获取日志配置"""
        return self.config.get('logging', {})
    
    # ============================================
    # 字段语义配置
    # ============================================
    
    def get_field_semantic_config(self) -> dict[str, Any]:
        """获取字段语义推断配置"""
        return self.config.get('field_semantic', {})
    
    def get_rag_threshold_seed(self) -> float:
        """获取 RAG seed/verified 数据阈值"""
        return self.get_field_semantic_config().get('rag_threshold_seed', 0.85)
    
    def get_rag_threshold_unverified(self) -> float:
        """获取 RAG llm/unverified 数据阈值"""
        return self.get_field_semantic_config().get('rag_threshold_unverified', 0.90)
    
    # ============================================
    # 语义解析器配置
    # ============================================
    
    def get_semantic_parser_config(self) -> dict[str, Any]:
        """获取语义解析器配置"""
        return self.config.get('semantic_parser', {})
    
    def get_semantic_parser_optimization_config(self) -> dict[str, Any]:
        """获取语义解析器优化配置
        
        包含：
        - enabled: 是否启用优化
        - low_confidence_threshold: 低置信度阈值
        - field_retriever: 字段检索配置
        - max_schema_fields: 最大 Schema 字段数
        - feature_extractor: 特征提取器配置
        - feature_cache: 特征缓存配置
        """
        return self.get_semantic_parser_config().get('optimization', {})
    
    def get_field_retriever_config(self) -> dict[str, Any]:
        """获取字段检索器配置"""
        return self.get_semantic_parser_optimization_config().get('field_retriever', {})
    
    def get_feature_extractor_config(self) -> dict[str, Any]:
        """获取特征提取器配置"""
        return self.get_semantic_parser_optimization_config().get('feature_extractor', {})
    
    def get_feature_cache_config(self) -> dict[str, Any]:
        """获取特征缓存配置"""
        return self.get_semantic_parser_optimization_config().get('feature_cache', {})
    
    # ============================================
    # 批量 Embedding 配置
    # ============================================
    
    def get_batch_embedding_config(self) -> dict[str, Any]:
        """获取批量 Embedding 配置"""
        return self.config.get('batch_embedding', {})
    
    def get_batch_embedding_batch_size(self) -> int:
        """获取批量 Embedding 每批数量"""
        return self.get_batch_embedding_config().get('batch_size', 20)
    
    def get_batch_embedding_max_concurrency(self) -> int:
        """获取批量 Embedding 最大并发数"""
        return self.get_batch_embedding_config().get('max_concurrency', 5)
    
    def get_batch_embedding_use_cache(self) -> bool:
        """获取批量 Embedding 是否使用缓存"""
        return self.get_batch_embedding_config().get('use_cache', True)
    
    # ============================================
    # 通用方法
    # ============================================
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self.config.get(key, default)

    def get_nested_config(self, *keys: str, default: Any = None) -> Any:
        """按路径获取嵌套配置项

        Args:
            *keys: 配置键路径，如 ("semantic_parser", "query_cache")
            default: 所有键都不存在时的默认值，默认为 {}

        Returns:
            对应路径的配置字典或 default

        Examples:
            config.get_nested_config("semantic_parser", "query_cache")
            config.get_nested_config("rag", "reranking", default=None)
        """
        if default is None:
            default = {}
        result = self.config
        for key in keys:
            if not isinstance(result, dict):
                return default
            result = result.get(key)
            if result is None:
                return default
        return result

    # ============================================
    # 语义解析器子模块配置
    # ============================================

    def get_query_cache_config(self) -> dict[str, Any]:
        """获取查询缓存配置"""
        return self.get_semantic_parser_config().get('query_cache', {})

    def get_intent_router_config(self) -> dict[str, Any]:
        """获取意图路由配置（顶层配置项）"""
        return self.config.get('intent_router', {})

    def get_error_corrector_config(self) -> dict[str, Any]:
        """获取错误纠正器配置"""
        return self.get_semantic_parser_config().get('error_corrector', {})

    def get_token_optimization_config(self) -> dict[str, Any]:
        """获取 token 优化配置（包含历史管理器参数）"""
        return self.get_semantic_parser_config().get('token_optimization', {})

    def get_feedback_config(self) -> dict[str, Any]:
        """获取反馈学习器配置"""
        return self.get_semantic_parser_config().get('feedback', {})

    def get_few_shot_config(self) -> dict[str, Any]:
        """获取少样本管理器配置"""
        return self.get_semantic_parser_config().get('few_shot', {})

    def get_filter_validator_config(self) -> dict[str, Any]:
        """获取筛选验证器配置"""
        return self.get_semantic_parser_config().get('filter_validator', {})

    def get_field_value_cache_config(self) -> dict[str, Any]:
        """获取字段值缓存配置"""
        return self.get_semantic_parser_config().get('field_value_cache', {})

    def get_semantic_understanding_config(self) -> dict[str, Any]:
        """获取语义理解配置"""
        return self.get_semantic_parser_config().get('semantic_understanding', {})

    def reload(self):
        """重新加载配置"""
        self._load_dotenv_files()
        self._load_config()

# ============================================
# 全局配置实例
# ============================================

_config_instance: Optional[AppConfig] = None

def get_config(config_path: Optional[str] = None) -> AppConfig:
    """
    获取全局配置实例
    
    Args:
        config_path: 配置文件路径（可选，仅首次调用有效）
    
    Returns:
        AppConfig 实例
    
    Examples:
        from analytics_assistant.src.infra.config import get_config
        
        config = get_config()
        ai_config = config.get_ai_config()
        storage_config = config.get_storage_config()
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = AppConfig(config_path)
    return _config_instance

__all__ = [
    "AppConfig",
    "ConfigLoadError",
    "get_config",
]
