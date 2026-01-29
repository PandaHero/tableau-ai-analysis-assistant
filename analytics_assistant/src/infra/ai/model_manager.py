# -*- coding: utf-8 -*-
"""
ModelManager - 统一的模型管理器

设计目标：
1. 统一接口：屏蔽不同提供商的 API 差异
2. 灵活配置：支持多模型、多提供商、动态切换
3. 智能路由：根据任务类型自动选择最优模型
4. 可扩展性：轻松添加新的模型提供商
5. 成本优化：支持模型降级和成本控制

使用示例：
    from analytics_assistant.src.infra.ai import get_model_manager
    
    manager = get_model_manager()
    
    # 使用默认 LLM
    llm = manager.create_llm()
    
    # 使用任务类型路由
    llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
    
    # 指定模型并覆盖参数
    llm = manager.create_llm(
        model_id="qwen3-local",
        temperature=0.8,
        enable_json_mode=True
    )
"""
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from pydantic import BaseModel, Field

from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Embedding 结果数据类
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class EmbeddingResult:
    """Embedding 结果（包含缓存信息）"""
    vectors: List[List[float]]
    cache_hits: int
    cache_misses: int


# ═══════════════════════════════════════════════════════════════════════════
# 枚举类型
# ═══════════════════════════════════════════════════════════════════════════

class ModelType(str, Enum):
    """模型类型"""
    LLM = "llm"
    EMBEDDING = "embedding"


class AuthType(str, Enum):
    """认证类型"""
    BEARER = "bearer"           # Authorization: Bearer <token>
    API_KEY_HEADER = "apikey"   # Apikey: <token>
    CUSTOM_HEADER = "custom"    # 自定义 header
    NONE = "none"               # 无认证


class ModelStatus(str, Enum):
    """模型状态"""
    ACTIVE = "active"           # 正常可用
    INACTIVE = "inactive"       # 已禁用
    ERROR = "error"             # 连接错误
    TESTING = "testing"         # 测试中


class TaskType(str, Enum):
    """任务类型（用于智能路由）"""
    INTENT_CLASSIFICATION = "intent_classification"  # 意图分类
    SEMANTIC_PARSING = "semantic_parsing"  # 语义解析
    FIELD_MAPPING = "field_mapping"  # 字段映射
    DIMENSION_HIERARCHY = "dimension_hierarchy"  # 维度层级
    INSIGHT_GENERATION = "insight_generation"  # 洞察生成
    REPLANNING = "replanning"  # 重新规划
    REASONING = "reasoning"  # 推理任务（需要深度思考）
    EMBEDDING = "embedding"  # 向量化


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

class ModelConfig(BaseModel):
    """模型配置"""
    # 基本信息
    id: str  # 唯一标识
    name: str  # 模型显示名称
    description: str = ""
    model_type: ModelType
    
    # API 配置
    provider: str  # 提供商（openai, azure, zhipu, deepseek, qwen, kimi, custom 等）
    api_base: str  # API 基础 URL
    api_endpoint: str = ""  # API 端点路径（留空使用默认）
    model_name: str  # 模型名称（API 参数）
    
    # 兼容性标记
    openai_compatible: bool = True  # 是否使用 OpenAI 兼容模式
    
    # 认证配置
    auth_type: AuthType = AuthType.BEARER
    auth_header: str = "Authorization"
    api_key: str = ""
    
    # 模型参数（None 表示使用模型默认值）
    temperature: Optional[float] = None  # 温度参数
    max_tokens: Optional[int] = None  # 最大 token 数
    top_p: Optional[float] = None  # Top-p 采样
    
    # 特性配置
    supports_streaming: bool = True  # 是否支持流式输出
    supports_json_mode: Optional[bool] = None  # 是否支持 JSON Mode
    supports_function_calling: bool = False  # 是否支持函数调用
    supports_vision: bool = False  # 是否支持视觉
    is_reasoning_model: bool = False  # 是否是推理模型（如 DeepSeek-R1）
    
    # 任务适配（用于智能路由）
    suitable_tasks: List[TaskType] = Field(default_factory=list)  # 适合的任务类型
    priority: int = 0  # 优先级（数字越大优先级越高）
    
    # 网络配置
    timeout: float = 120.0
    verify_ssl: bool = True
    proxy: str = ""
    
    # 额外配置
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    extra_body: Dict[str, Any] = Field(default_factory=dict)
    
    # 状态和元数据
    status: ModelStatus = ModelStatus.ACTIVE
    is_default: bool = False
    tags: List[str] = Field(default_factory=list)
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = None


class ModelCreateRequest(BaseModel):
    """创建模型配置请求"""
    name: str
    model_type: ModelType
    provider: str
    api_base: str
    model_name: str
    api_key: str = ""
    openai_compatible: bool = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    supports_streaming: bool = True
    supports_json_mode: Optional[bool] = None
    is_reasoning_model: bool = False  # 是否是推理模型
    suitable_tasks: List[TaskType] = Field(default_factory=list)
    priority: int = 0
    is_default: bool = False
    extra_body: Dict[str, Any] = Field(default_factory=dict)


class ModelUpdateRequest(BaseModel):
    """更新模型配置请求"""
    name: Optional[str] = None
    status: Optional[ModelStatus] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    priority: Optional[int] = None
    is_default: Optional[bool] = None


# ═══════════════════════════════════════════════════════════════════════════
# ModelManager 主类
# ═══════════════════════════════════════════════════════════════════════════

class ModelManager:
    """
    模型管理器（单例）
    
    职责：
    1. 管理所有模型配置（CRUD 操作）
    2. 提供统一的模型获取接口
    3. 智能路由（根据任务类型选择最优模型）
    4. 健康检查和统计信息
    5. 持久化存储（使用 CacheManager）
    
    持久化策略：
    - YAML 配置文件中的模型：只读，不持久化（重启后从 YAML 重新加载）
    - 通过 API 动态添加的模型：持久化到 SQLite（重启后自动恢复）
    """
    
    _instance = None
    
    # 持久化存储的命名空间
    PERSISTENCE_NAMESPACE = "model_manager"
    PERSISTENCE_KEY = "dynamic_configs"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._configs: Dict[str, ModelConfig] = {}
            self._defaults: Dict[ModelType, str] = {}
            self._dynamic_config_ids: set = set()  # 记录动态添加的配置 ID
            self._persistence_enabled = False
            self._cache_manager = None
            logger.info("ModelManager initialized")
            
            # 初始化持久化存储
            self._init_persistence()
            
            # 从统一配置文件加载配置
            self._load_from_unified_config()
            
            # 从持久化存储加载动态配置
            self._load_from_persistence()
    
    # ═══════════════════════════════════════════════════════════════════════
    # 持久化存储
    # ═══════════════════════════════════════════════════════════════════════
    
    def _init_persistence(self):
        """初始化持久化存储"""
        try:
            from ..config.config_loader import get_config
            
            # 检查是否启用持久化
            app_config = get_config()
            ai_config = app_config.config.get("ai", {})
            global_config = ai_config.get("global", {})
            self._persistence_enabled = global_config.get("enable_persistence", False)
            
            if not self._persistence_enabled:
                logger.info("ModelManager 持久化已禁用")
                return
            
            # 创建 CacheManager
            from ..storage import CacheManager
            self._cache_manager = CacheManager(
                namespace=self.PERSISTENCE_NAMESPACE,
                default_ttl=None,  # 永久存储
                enable_stats=False
            )
            
            logger.info("ModelManager 持久化存储已初始化")
            
        except Exception as e:
            logger.warning(f"初始化持久化存储失败: {e}")
            self._persistence_enabled = False
    
    def _load_from_persistence(self):
        """从持久化存储加载动态配置"""
        if not self._persistence_enabled or self._cache_manager is None:
            return
        
        try:
            # 获取持久化的配置列表
            stored_data = self._cache_manager.get(self.PERSISTENCE_KEY)
            
            if stored_data is None:
                logger.debug("没有持久化的动态配置")
                return
            
            # 解析并加载配置
            for config_data in stored_data:
                try:
                    config_id = config_data.get("id")
                    
                    # 跳过已存在的配置（YAML 配置优先）
                    if config_id in self._configs:
                        logger.debug(f"跳过已存在的配置: {config_id}")
                        continue
                    
                    # 创建配置
                    self._create_from_dict(config_data)
                    self._dynamic_config_ids.add(config_id)
                    
                except Exception as e:
                    logger.warning(f"加载持久化配置失败: {e}")
            
            logger.info(f"从持久化存储加载了 {len(self._dynamic_config_ids)} 个动态配置")
            
        except Exception as e:
            logger.warning(f"加载持久化配置失败: {e}")
    
    def _save_to_persistence(self):
        """保存动态配置到持久化存储"""
        if not self._persistence_enabled or self._cache_manager is None:
            return
        
        try:
            # 只保存动态添加的配置
            dynamic_configs = []
            for config_id in self._dynamic_config_ids:
                config = self._configs.get(config_id)
                if config:
                    dynamic_configs.append(self._config_to_dict(config))
            
            # 保存到持久化存储
            self._cache_manager.set(self.PERSISTENCE_KEY, dynamic_configs)
            
            logger.debug(f"保存了 {len(dynamic_configs)} 个动态配置到持久化存储")
            
        except Exception as e:
            logger.warning(f"保存持久化配置失败: {e}")
    
    def _config_to_dict(self, config: ModelConfig) -> Dict[str, Any]:
        """将 ModelConfig 转换为字典（用于持久化）"""
        return {
            "id": config.id,
            "name": config.name,
            "description": config.description,
            "model_type": config.model_type.value,
            "provider": config.provider,
            "api_base": config.api_base,
            "api_endpoint": config.api_endpoint,
            "model_name": config.model_name,
            "openai_compatible": config.openai_compatible,
            "auth_type": config.auth_type.value,
            "auth_header": config.auth_header,
            "api_key": config.api_key,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "supports_streaming": config.supports_streaming,
            "supports_json_mode": config.supports_json_mode,
            "supports_function_calling": config.supports_function_calling,
            "supports_vision": config.supports_vision,
            "is_reasoning_model": config.is_reasoning_model,
            "suitable_tasks": [t.value for t in config.suitable_tasks],
            "priority": config.priority,
            "timeout": config.timeout,
            "verify_ssl": config.verify_ssl,
            "proxy": config.proxy,
            "extra_headers": config.extra_headers,
            "extra_body": config.extra_body,
            "status": config.status.value,
            "is_default": config.is_default,
            "tags": config.tags,
        }
    
    def enable_persistence(self, enable: bool = True):
        """
        启用或禁用持久化
        
        Args:
            enable: 是否启用持久化
        """
        if enable and self._cache_manager is None:
            # 尝试初始化 CacheManager
            try:
                from ..storage import CacheManager
                self._cache_manager = CacheManager(
                    namespace=self.PERSISTENCE_NAMESPACE,
                    default_ttl=None,  # 永久存储
                    enable_stats=False
                )
                self._persistence_enabled = True
                logger.info("ModelManager 持久化存储已启用")
            except Exception as e:
                logger.warning(f"启用持久化失败: {e}")
                self._persistence_enabled = False
        elif enable:
            self._persistence_enabled = True
        else:
            self._persistence_enabled = False
        
        logger.info(f"ModelManager 持久化: {'启用' if self._persistence_enabled else '禁用'}")
    
    def is_persistence_enabled(self) -> bool:
        """检查持久化是否启用"""
        return self._persistence_enabled and self._cache_manager is not None
    
    def get_dynamic_config_ids(self) -> List[str]:
        """获取动态添加的配置 ID 列表"""
        return list(self._dynamic_config_ids)
    
    def _load_from_unified_config(self):
        """从统一配置文件加载配置"""
        try:
            from ..config.config_loader import get_config
            
            # 获取统一配置
            app_config = get_config()
            
            # 加载 LLM 模型
            llm_models = app_config.get_llm_models()
            for model_data in llm_models:
                try:
                    self._create_from_dict(model_data)
                except Exception as e:
                    logger.warning(f"加载 LLM 模型配置失败 {model_data.get('id')}: {e}")
            
            # 加载 Embedding 模型
            embedding_models = app_config.get_embedding_models()
            for model_data in embedding_models:
                try:
                    self._create_from_dict(model_data)
                except Exception as e:
                    logger.warning(f"加载 Embedding 模型配置失败 {model_data.get('id')}: {e}")
            
            logger.info(f"从统一配置加载了 {len(self._configs)} 个模型配置")
            
        except Exception as e:
            logger.warning(f"统一配置加载失败: {e}")
            logger.info("将使用空配置，请确保 config/app.yaml 存在")
    
    
    def _create_from_dict(self, data: Dict[str, Any]) -> ModelConfig:
        """从字典创建模型配置"""
        # 转换 model_type
        model_type_str = data.get('model_type', 'llm')
        model_type = ModelType.LLM if model_type_str == 'llm' else ModelType.EMBEDDING
        
        # 转换 status
        status_str = data.get('status', 'active')
        status = ModelStatus.ACTIVE if status_str == 'active' else ModelStatus.INACTIVE
        
        # 转换 suitable_tasks
        suitable_tasks = []
        for task_str in data.get('suitable_tasks', []):
            try:
                task = TaskType(task_str)
                suitable_tasks.append(task)
            except ValueError:
                logger.warning(f"未知的任务类型: {task_str}")
        
        # 创建配置
        config = ModelConfig(
            id=data.get('id', f"{data['provider']}-{data['model_name']}"),
            name=data.get('name', data['model_name']),
            model_type=model_type,
            provider=data['provider'],
            api_base=data['api_base'],
            model_name=data['model_name'],
            api_key=data.get('api_key', ''),
            openai_compatible=data.get('openai_compatible', True),
            temperature=data.get('temperature'),
            max_tokens=data.get('max_tokens'),
            supports_streaming=data.get('supports_streaming', True),
            supports_json_mode=data.get('supports_json_mode'),
            is_reasoning_model=data.get('is_reasoning_model', False),
            suitable_tasks=suitable_tasks,
            priority=data.get('priority', 0),
            is_default=data.get('is_default', False),
            extra_body=data.get('extra_body', {}),
            status=status,
        )
        
        # 检查是否已存在
        if config.id in self._configs:
            logger.debug(f"模型配置已存在，跳过: {config.id}")
            return self._configs[config.id]
        
        self._configs[config.id] = config
        
        # 如果是默认模型，更新默认配置
        if config.is_default:
            self._defaults[model_type] = config.id
        
        logger.debug(f"加载模型配置: {config.id}")
        return config
    
    # ═══════════════════════════════════════════════════════════════════════
    # CRUD 操作
    # ═══════════════════════════════════════════════════════════════════════
    
    def create(self, request: ModelCreateRequest) -> ModelConfig:
        """创建新模型配置（动态添加，支持持久化）"""
        # 生成唯一 ID
        model_id = f"{request.provider}-{request.model_name}".replace("/", "-").replace(":", "-")
        
        # 检查是否已存在
        if model_id in self._configs:
            raise ValueError(f"Model {model_id} already exists")
        
        # 创建配置
        config = ModelConfig(
            id=model_id,
            name=request.name,
            model_type=request.model_type,
            provider=request.provider,
            api_base=request.api_base,
            model_name=request.model_name,
            api_key=request.api_key,
            openai_compatible=request.openai_compatible,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            supports_streaming=request.supports_streaming,
            supports_json_mode=request.supports_json_mode,
            is_reasoning_model=request.is_reasoning_model,
            suitable_tasks=request.suitable_tasks,
            priority=request.priority,
            is_default=request.is_default,
            extra_body=request.extra_body,
            status=ModelStatus.ACTIVE,
        )
        
        self._configs[model_id] = config
        
        # 标记为动态配置
        self._dynamic_config_ids.add(model_id)
        
        # 如果是默认模型，更新默认配置
        if request.is_default:
            self._defaults[request.model_type] = model_id
        
        # 持久化
        self._save_to_persistence()
        
        logger.info(f"Created model config: {model_id}")
        return config
    
    def get(self, model_id: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        return self._configs.get(model_id)
    
    def list(
        self,
        model_type: Optional[ModelType] = None,
        status: Optional[ModelStatus] = None,
        tags: Optional[List[str]] = None,
    ) -> List[ModelConfig]:
        """列出模型配置"""
        configs = list(self._configs.values())
        
        # 过滤模型类型
        if model_type:
            configs = [c for c in configs if c.model_type == model_type]
        
        # 过滤状态
        if status:
            configs = [c for c in configs if c.status == status]
        
        # 过滤标签
        if tags:
            configs = [c for c in configs if any(tag in c.tags for tag in tags)]
        
        return configs
    
    def update(self, model_id: str, request: ModelUpdateRequest) -> Optional[ModelConfig]:
        """更新模型配置"""
        config = self._configs.get(model_id)
        if not config:
            return None
        
        # 更新字段
        if request.name is not None:
            config.name = request.name
        if request.status is not None:
            config.status = request.status
        if request.temperature is not None:
            config.temperature = request.temperature
        if request.max_tokens is not None:
            config.max_tokens = request.max_tokens
        if request.priority is not None:
            config.priority = request.priority
        if request.is_default is not None:
            config.is_default = request.is_default
            if request.is_default:
                self._defaults[config.model_type] = model_id
        
        config.updated_at = datetime.now()
        
        # 如果是动态配置，持久化
        if model_id in self._dynamic_config_ids:
            self._save_to_persistence()
        
        logger.info(f"Updated model config: {model_id}")
        return config
    
    def delete(self, model_id: str) -> bool:
        """删除模型配置"""
        if model_id in self._configs:
            del self._configs[model_id]
            
            # 如果是动态配置，从集合中移除并持久化
            if model_id in self._dynamic_config_ids:
                self._dynamic_config_ids.discard(model_id)
                self._save_to_persistence()
            
            logger.info(f"Deleted model config: {model_id}")
            return True
        return False
    
    # ═══════════════════════════════════════════════════════════════════════
    # 默认模型管理
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_default(self, model_type: ModelType) -> Optional[ModelConfig]:
        """获取默认模型"""
        default_id = self._defaults.get(model_type)
        if default_id:
            return self._configs.get(default_id)
        return None
    
    def set_default(self, model_id: str) -> bool:
        """设置默认模型"""
        config = self._configs.get(model_id)
        if not config:
            return False
        
        self._defaults[config.model_type] = model_id
        config.is_default = True
        logger.info(f"Set default {config.model_type.value} model: {model_id}")
        return True
    
    # ═══════════════════════════════════════════════════════════════════════
    # 模型实例创建
    # ═══════════════════════════════════════════════════════════════════════
    
    def create_llm(
        self,
        model_id: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        创建 LLM 实例
        
        Args:
            model_id: 指定模型 ID（优先级最高）
            task_type: 任务类型（用于智能路由）
            **kwargs: 运行时参数，可覆盖配置中的默认值
                - temperature: 温度参数
                - max_tokens: 最大 token 数
                - top_p: top_p 参数
                - enable_json_mode: 是否启用 JSON Mode
                - streaming: 是否启用流式输出（默认 False）
        
        Returns:
            LangChain BaseChatModel 实例
        
        Examples:
            # 使用默认配置
            llm = manager.create_llm()
            
            # 使用任务类型路由
            llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
            
            # 覆盖参数
            llm = manager.create_llm(
                model_id="qwen3-local",
                temperature=0.8,
                enable_json_mode=True,
                streaming=True
            )
        """
        # 1. 选择模型配置
        config = None
        
        if model_id:
            # 显式指定模型 ID
            config = self.get(model_id)
            if not config:
                raise ValueError(f"Model {model_id} not found")
        elif task_type:
            # 使用任务类型路由
            config = self._route_by_task(task_type, ModelType.LLM)
        else:
            # 使用默认模型
            config = self.get_default(ModelType.LLM)
        
        if not config:
            raise ValueError("No LLM model available")
        
        # 2. 创建 LLM 实例
        return self._create_llm_from_config(config, **kwargs)
    
    def _route_by_task(self, task_type: TaskType, model_type: ModelType) -> Optional[ModelConfig]:
        """根据任务类型路由到最优模型"""
        # 获取适合该任务的模型
        suitable_models = []
        for config in self.list(model_type=model_type, status=ModelStatus.ACTIVE):
            if task_type in config.suitable_tasks:
                suitable_models.append(config)
        
        if not suitable_models:
            # 降级到默认模型
            return self.get_default(model_type)
        
        # 按优先级排序（优先级越大越优先）
        suitable_models.sort(key=lambda m: m.priority, reverse=True)
        
        return suitable_models[0]
    
    def _create_llm_from_config(self, config: ModelConfig, **kwargs) -> BaseChatModel:
        """
        从配置创建 LLM 实例
        
        路由逻辑（按优先级）：
        1. Azure OpenAI → AzureChatOpenAI（可选，企业用户）
        2. 非 OpenAI 兼容（自定义端点）→ CustomLLMChat
        3. OpenAI 兼容 → ChatOpenAI（默认，支持大多数模型）
        """
        from langchain_openai import ChatOpenAI
        
        # 合并参数：kwargs 优先，然后是 config
        temperature = kwargs.get('temperature', config.temperature)
        max_tokens = kwargs.get('max_tokens', config.max_tokens)
        enable_json_mode = kwargs.pop('enable_json_mode', False)
        streaming = kwargs.pop('streaming', False)
        
        # ═══════════════════════════════════════════════════════════════════
        # 路由 1：Azure OpenAI（可选，企业用户）
        # ═══════════════════════════════════════════════════════════════════
        if config.provider == "azure":
            from langchain_openai import AzureChatOpenAI
            
            azure_kwargs = {
                "azure_deployment": config.model_name,
                "azure_endpoint": config.api_base,
                "openai_api_key": config.api_key,
                "openai_api_version": config.extra_body.get("api_version", "2024-02-15-preview"),
                "streaming": streaming,
            }
            if temperature is not None:
                azure_kwargs["temperature"] = temperature
            if max_tokens is not None:
                azure_kwargs["max_tokens"] = max_tokens
            
            # JSON Mode 支持（使用适配器）
            if enable_json_mode:
                json_mode_kwargs = self._get_json_mode_kwargs(config.provider, enable_json_mode)
                azure_kwargs.update(json_mode_kwargs)
            
            return AzureChatOpenAI(**azure_kwargs)
        
        # ═══════════════════════════════════════════════════════════════════
        # 路由 2：非 OpenAI 兼容模型（自定义端点）
        # ═══════════════════════════════════════════════════════════════════
        if not config.openai_compatible:
            # TODO: 实现 CustomLLMChat（后续任务）
            raise NotImplementedError("CustomLLMChat not implemented yet")
        
        # ═══════════════════════════════════════════════════════════════════
        # 路由 3：OpenAI 兼容模型（默认，支持大多数模型）
        # ═══════════════════════════════════════════════════════════════════
        openai_kwargs = {
            "model_name": config.model_name,
            "api_key": config.api_key,
            "streaming": streaming,
        }
        
        # 非 OpenAI 官方 API 设置 base_url
        if "api.openai.com" not in config.api_base:
            openai_kwargs["base_url"] = config.api_base
        
        if temperature is not None:
            openai_kwargs["temperature"] = temperature
        if max_tokens is not None:
            openai_kwargs["max_tokens"] = max_tokens
        
        # JSON Mode 支持（使用适配器）
        if enable_json_mode:
            json_mode_kwargs = self._get_json_mode_kwargs(config.provider, enable_json_mode)
            openai_kwargs.update(json_mode_kwargs)
        
        # 更新最后使用时间
        config.last_used_at = datetime.now()
        
        # 为推理模型添加标记（用于后续处理）
        llm_instance = ChatOpenAI(**openai_kwargs)
        if config.is_reasoning_model:
            # 标记为推理模型，便于 Agent 层识别
            llm_instance._is_reasoning_model = True
            llm_instance._model_config = config
        
        return llm_instance
    
    def _get_json_mode_kwargs(self, provider: str, enable_json_mode: bool = True) -> Dict[str, Any]:
        """
        获取 JSON Mode 参数（适配不同提供商）
        
        根据不同 LLM Provider 的支持情况，提供统一的 JSON Mode 参数配置。
        
        Provider 支持情况：
        - DeepSeek, OpenAI, Azure: 通过 model_kwargs.response_format
        - Custom: 通过 extra_body.response_format
        - Anthropic: 不支持原生 JSON Mode（返回空）
        - Local: 尝试 model_kwargs（取决于具体实现）
        
        Args:
            provider: Provider 名称（如 "deepseek", "openai", "azure"）
            enable_json_mode: 是否启用 JSON Mode
            
        Returns:
            传递给 LLM 构造函数的参数字典
        """
        if not enable_json_mode:
            return {}
        
        provider_lower = provider.lower()
        
        # DeepSeek、OpenAI、Azure、Local 使用 model_kwargs
        if provider_lower in ("deepseek", "openai", "azure", "local", "qwen", "kimi"):
            return {
                "model_kwargs": {
                    "response_format": {"type": "json_object"}
                }
            }
        
        # Custom 使用 extra_body
        elif provider_lower == "custom":
            return {
                "extra_body": {
                    "response_format": {"type": "json_object"}
                }
            }
        
        # Anthropic 不支持原生 JSON Mode
        elif provider_lower == "anthropic":
            logger.info("Anthropic does not support native JSON Mode, relying on prompt constraints")
            return {}
        
        # 默认使用 model_kwargs（兼容大多数 OpenAI 兼容模型）
        else:
            logger.debug(f"Unknown provider '{provider}', using default JSON Mode configuration")
            return {
                "model_kwargs": {
                    "response_format": {"type": "json_object"}
                }
            }
    
    def create_embedding(
        self,
        model_id: Optional[str] = None,
        **kwargs
    ) -> Embeddings:
        """创建 Embedding 实例"""
        # 1. 选择模型配置
        config = None
        
        if model_id:
            config = self.get(model_id)
            if not config:
                raise ValueError(f"Model {model_id} not found")
        else:
            config = self.get_default(ModelType.EMBEDDING)
        
        if not config:
            raise ValueError("No Embedding model available")
        
        # 2. 创建 Embedding 实例
        return self._create_embedding_from_config(config, **kwargs)
    
    def _create_embedding_from_config(self, config: ModelConfig, **kwargs) -> Embeddings:
        """从配置创建 Embedding 实例"""
        from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings
        
        # ═══════════════════════════════════════════════════════════════════
        # 路由 1：Azure OpenAI Embeddings
        # ═══════════════════════════════════════════════════════════════════
        if config.provider == "azure":
            azure_kwargs = {
                "azure_deployment": config.model_name,
                "azure_endpoint": config.api_base,
                "openai_api_key": config.api_key,
                "openai_api_version": config.extra_body.get("api_version", "2024-02-15-preview"),
            }
            return AzureOpenAIEmbeddings(**azure_kwargs)
        
        # ═══════════════════════════════════════════════════════════════════
        # 路由 2：OpenAI 兼容 Embeddings（默认）
        # ═══════════════════════════════════════════════════════════════════
        # 支持：
        # - OpenAI 官方（text-embedding-3-small, text-embedding-3-large）
        # - 智谱 AI（embedding-2）
        # - 阿里云（text-embedding-v2）
        # - 本地模型（bge-large-zh-v1.5, m3e-base）
        
        openai_kwargs = {
            "model": config.model_name,
            "api_key": config.api_key,
        }
        
        # 非 OpenAI 官方 API 设置 base_url
        if "api.openai.com" not in config.api_base:
            openai_kwargs["base_url"] = config.api_base
        
        # 更新最后使用时间
        config.last_used_at = datetime.now()
        
        return OpenAIEmbeddings(**openai_kwargs)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 批量 Embedding
    # ═══════════════════════════════════════════════════════════════════════
    
    def _get_batch_embedding_defaults(self) -> Dict[str, Any]:
        """从配置获取批量 Embedding 默认参数"""
        try:
            from ..config import get_config
            config = get_config()
            batch_config = config.get_batch_embedding_config()
            return {
                'batch_size': batch_config.get('batch_size', 20),
                'max_concurrency': batch_config.get('max_concurrency', 5),
                'use_cache': batch_config.get('use_cache', True),
            }
        except Exception:
            return {'batch_size': 20, 'max_concurrency': 5, 'use_cache': True}
    
    def embed_documents_batch(
        self,
        texts: List[str],
        model_id: Optional[str] = None,
        batch_size: int = None,
        max_concurrency: int = None,
        use_cache: bool = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[List[float]]:
        """
        批量生成文档 Embedding（同步版本）
        
        优化策略：
        1. 缓存：已计算的 embedding 直接从缓存读取
        2. 批量：将文本分批处理，每批 batch_size 条
        3. 并发：max_concurrency 个批次同时执行
        
        例如：200 条文本，batch_size=20，max_concurrency=5
        - 分成 10 个批次
        - 每轮并发执行 5 个批次（100 条）
        - 2 轮完成全部
        
        Args:
            texts: 文本列表
            model_id: 模型 ID（可选）
            batch_size: 每批文本数量（默认从配置读取）
            max_concurrency: 最大并发批次数（默认从配置读取）
            use_cache: 是否使用缓存（默认从配置读取）
            progress_callback: 进度回调函数 (completed, total)
        
        Returns:
            Embedding 向量列表，与输入文本一一对应
        
        Examples:
            manager = get_model_manager()
            
            texts = ["文本1", "文本2", "文本3", ...]
            vectors = manager.embed_documents_batch(
                texts,
                progress_callback=lambda done, total: print(f"{done}/{total}")
            )
        """
        import asyncio
        
        # 从配置获取默认值
        defaults = self._get_batch_embedding_defaults()
        actual_batch_size = batch_size if batch_size is not None else defaults['batch_size']
        actual_max_concurrency = max_concurrency if max_concurrency is not None else defaults['max_concurrency']
        actual_use_cache = use_cache if use_cache is not None else defaults['use_cache']
        
        # 在新的事件循环中运行异步版本
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已有事件循环在运行，使用 run_in_executor
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.embed_documents_batch_async(
                            texts, model_id, actual_batch_size, actual_max_concurrency, 
                            actual_use_cache, progress_callback
                        )
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.embed_documents_batch_async(
                        texts, model_id, actual_batch_size, actual_max_concurrency,
                        actual_use_cache, progress_callback
                    )
                )
        except RuntimeError:
            # 没有事件循环，创建新的
            return asyncio.run(
                self.embed_documents_batch_async(
                    texts, model_id, actual_batch_size, actual_max_concurrency,
                    actual_use_cache, progress_callback
                )
            )
    
    async def embed_documents_batch_async(
        self,
        texts: List[str],
        model_id: Optional[str] = None,
        batch_size: int = None,
        max_concurrency: int = None,
        use_cache: bool = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[List[float]]:
        """
        批量生成文档 Embedding（异步版本）
        
        Args:
            texts: 文本列表
            model_id: 模型 ID（可选）
            batch_size: 每批文本数量（默认从配置读取）
            max_concurrency: 最大并发批次数（默认从配置读取）
            use_cache: 是否使用缓存（默认从配置读取）
            progress_callback: 进度回调函数
        
        Returns:
            Embedding 向量列表
        """
        import asyncio
        import hashlib
        import aiohttp
        
        if not texts:
            return []
        
        # 从配置获取默认值
        defaults = self._get_batch_embedding_defaults()
        actual_batch_size = batch_size if batch_size is not None else defaults['batch_size']
        actual_max_concurrency = max_concurrency if max_concurrency is not None else defaults['max_concurrency']
        actual_use_cache = use_cache if use_cache is not None else defaults['use_cache']
        
        total = len(texts)
        results: List[Optional[List[float]]] = [None] * total
        
        # 初始化缓存
        cache = None
        if actual_use_cache:
            try:
                from ..storage import CacheManager
                cache = CacheManager(namespace="embedding", default_ttl=3600)
            except Exception as e:
                logger.warning(f"无法初始化 embedding 缓存: {e}")
        
        # 获取 embedding 模型配置
        config = None
        if model_id:
            config = self.get(model_id)
        else:
            config = self.get_default(ModelType.EMBEDDING)
        
        if not config:
            raise ValueError("No Embedding model available")
        
        # 计算缓存 key
        def make_cache_key(text: str) -> str:
            return hashlib.md5(text.encode('utf-8')).hexdigest()
        
        # 检查缓存，分离已缓存和未缓存的文本
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []
        
        for i, text in enumerate(texts):
            if cache:
                cache_key = make_cache_key(text)
                cached = cache.get(cache_key)
                if cached is not None:
                    results[i] = cached
                    continue
            uncached_indices.append(i)
            uncached_texts.append(text)
        
        cached_count = total - len(uncached_texts)
        if cached_count > 0:
            logger.info(f"Embedding 缓存命中: {cached_count}/{total}")
        
        if progress_callback:
            progress_callback(cached_count, total)
        
        # 如果全部命中缓存，直接返回
        if not uncached_texts:
            return results
        
        # 分批处理未缓存的文本
        batches = [
            uncached_texts[i:i + actual_batch_size]
            for i in range(0, len(uncached_texts), actual_batch_size)
        ]
        batch_indices = [
            uncached_indices[i:i + actual_batch_size]
            for i in range(0, len(uncached_indices), actual_batch_size)
        ]
        
        logger.info(f"开始批量 Embedding: {len(uncached_texts)} 条文本, {len(batches)} 批次, 并发={actual_max_concurrency}")
        
        # 并发控制
        semaphore = asyncio.Semaphore(actual_max_concurrency)
        completed = cached_count
        completed_lock = asyncio.Lock()
        
        async def call_embedding_api(batch_texts: List[str]) -> List[List[float]]:
            """异步调用 embedding API"""
            # 构建请求
            api_base = config.api_base.rstrip('/')
            url = f"{api_base}/embeddings"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}",
            }
            
            payload = {
                "model": config.model_name,
                "input": batch_texts,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"Embedding API 错误 {resp.status}: {error_text}")
                    
                    data = await resp.json()
                    # 按 index 排序确保顺序正确
                    embeddings_data = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
                    return [item["embedding"] for item in embeddings_data]
        
        async def process_batch(batch_texts: List[str], indices: List[int]) -> None:
            nonlocal completed
            
            async with semaphore:
                try:
                    # 异步调用 embedding API
                    batch_vectors = await call_embedding_api(batch_texts)
                    
                    # 存储结果和缓存
                    for idx, text, vector in zip(indices, batch_texts, batch_vectors):
                        results[idx] = vector
                        if cache:
                            cache_key = make_cache_key(text)
                            cache.set(cache_key, vector)
                    
                    # 更新进度
                    async with completed_lock:
                        completed += len(batch_texts)
                        if progress_callback:
                            progress_callback(completed, total)
                    
                except Exception as e:
                    logger.error(f"批量 Embedding 失败: {e}")
                    # 失败的批次使用空向量
                    for idx in indices:
                        if results[idx] is None:
                            results[idx] = []
        
        # 并发执行所有批次
        tasks = [
            process_batch(batch_texts, indices)
            for batch_texts, indices in zip(batches, batch_indices)
        ]
        await asyncio.gather(*tasks)
        
        logger.info(f"批量 Embedding 完成: {total} 条文本")
        return results
    
    def embed_documents_batch_with_stats(
        self,
        texts: List[str],
        model_id: Optional[str] = None,
        batch_size: int = None,
        max_concurrency: int = None,
        use_cache: bool = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> EmbeddingResult:
        """
        批量生成文档 Embedding，返回缓存命中信息（同步版本）
        
        与 embed_documents_batch() 类似，但返回 EmbeddingResult 包含：
        - vectors: 向量列表
        - cache_hits: 缓存命中次数
        - cache_misses: 缓存未命中次数
        
        Args:
            texts: 文本列表
            model_id: 模型 ID（可选）
            batch_size: 每批文本数量（默认从配置读取）
            max_concurrency: 最大并发批次数（默认从配置读取）
            use_cache: 是否使用缓存（默认从配置读取）
            progress_callback: 进度回调函数 (completed, total)
        
        Returns:
            EmbeddingResult 包含向量和缓存统计信息
        """
        import asyncio
        
        # 从配置获取默认值
        defaults = self._get_batch_embedding_defaults()
        actual_batch_size = batch_size if batch_size is not None else defaults['batch_size']
        actual_max_concurrency = max_concurrency if max_concurrency is not None else defaults['max_concurrency']
        actual_use_cache = use_cache if use_cache is not None else defaults['use_cache']
        
        # 在新的事件循环中运行异步版本
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.embed_documents_batch_with_stats_async(
                            texts, model_id, actual_batch_size, actual_max_concurrency, 
                            actual_use_cache, progress_callback
                        )
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.embed_documents_batch_with_stats_async(
                        texts, model_id, actual_batch_size, actual_max_concurrency,
                        actual_use_cache, progress_callback
                    )
                )
        except RuntimeError:
            return asyncio.run(
                self.embed_documents_batch_with_stats_async(
                    texts, model_id, actual_batch_size, actual_max_concurrency,
                    actual_use_cache, progress_callback
                )
            )
    
    async def embed_documents_batch_with_stats_async(
        self,
        texts: List[str],
        model_id: Optional[str] = None,
        batch_size: int = None,
        max_concurrency: int = None,
        use_cache: bool = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> EmbeddingResult:
        """
        批量生成文档 Embedding，返回缓存命中信息（异步版本）
        
        Args:
            texts: 文本列表
            model_id: 模型 ID（可选）
            batch_size: 每批文本数量（默认从配置读取）
            max_concurrency: 最大并发批次数（默认从配置读取）
            use_cache: 是否使用缓存（默认从配置读取）
            progress_callback: 进度回调函数
        
        Returns:
            EmbeddingResult 包含向量和缓存统计信息
        """
        import asyncio
        import hashlib
        import aiohttp
        
        if not texts:
            return EmbeddingResult(vectors=[], cache_hits=0, cache_misses=0)
        
        # 从配置获取默认值
        defaults = self._get_batch_embedding_defaults()
        actual_batch_size = batch_size if batch_size is not None else defaults['batch_size']
        actual_max_concurrency = max_concurrency if max_concurrency is not None else defaults['max_concurrency']
        actual_use_cache = use_cache if use_cache is not None else defaults['use_cache']
        
        total = len(texts)
        results: List[Optional[List[float]]] = [None] * total
        
        # 缓存统计
        cache_hits = 0
        cache_misses = 0
        
        # 初始化缓存
        cache = None
        if actual_use_cache:
            try:
                from ..storage import CacheManager
                cache = CacheManager(namespace="embedding", default_ttl=86400)
            except Exception as e:
                logger.warning(f"无法初始化 embedding 缓存: {e}")
        
        # 获取 embedding 模型配置
        config = None
        if model_id:
            config = self.get(model_id)
        else:
            config = self.get_default(ModelType.EMBEDDING)
        
        if not config:
            raise ValueError("No Embedding model available")
        
        # 计算缓存 key
        def make_cache_key(text: str) -> str:
            return hashlib.md5(text.encode('utf-8')).hexdigest()
        
        # 检查缓存，分离已缓存和未缓存的文本
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []
        
        for i, text in enumerate(texts):
            if cache:
                cache_key = make_cache_key(text)
                cached = cache.get(cache_key)
                if cached is not None:
                    results[i] = cached
                    cache_hits += 1
                    continue
            uncached_indices.append(i)
            uncached_texts.append(text)
        
        cache_misses = len(uncached_texts)
        
        if cache_hits > 0:
            logger.info(f"Embedding 缓存命中: {cache_hits}/{total}")
        
        if progress_callback:
            progress_callback(cache_hits, total)
        
        # 如果全部命中缓存，直接返回
        if not uncached_texts:
            return EmbeddingResult(vectors=results, cache_hits=cache_hits, cache_misses=cache_misses)
        
        # 分批处理未缓存的文本
        batches = [
            uncached_texts[i:i + actual_batch_size]
            for i in range(0, len(uncached_texts), actual_batch_size)
        ]
        batch_indices = [
            uncached_indices[i:i + actual_batch_size]
            for i in range(0, len(uncached_indices), actual_batch_size)
        ]
        
        logger.info(f"开始批量 Embedding: {len(uncached_texts)} 条文本, {len(batches)} 批次, 并发={actual_max_concurrency}")
        
        # 并发控制
        semaphore = asyncio.Semaphore(actual_max_concurrency)
        completed = cache_hits
        completed_lock = asyncio.Lock()
        
        async def call_embedding_api(batch_texts: List[str]) -> List[List[float]]:
            """异步调用 embedding API"""
            api_base = config.api_base.rstrip('/')
            url = f"{api_base}/embeddings"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}",
            }
            
            payload = {
                "model": config.model_name,
                "input": batch_texts,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"Embedding API 错误 {resp.status}: {error_text}")
                    
                    data = await resp.json()
                    embeddings_data = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
                    return [item["embedding"] for item in embeddings_data]
        
        async def process_batch(batch_texts: List[str], indices: List[int]) -> None:
            nonlocal completed
            
            async with semaphore:
                try:
                    batch_vectors = await call_embedding_api(batch_texts)
                    
                    for idx, text, vector in zip(indices, batch_texts, batch_vectors):
                        results[idx] = vector
                        if cache:
                            cache_key = make_cache_key(text)
                            cache.set(cache_key, vector)
                    
                    async with completed_lock:
                        completed += len(batch_texts)
                        if progress_callback:
                            progress_callback(completed, total)
                    
                except Exception as e:
                    logger.error(f"批量 Embedding 失败: {e}")
                    for idx in indices:
                        if results[idx] is None:
                            results[idx] = []
        
        # 并发执行所有批次
        tasks = [
            process_batch(batch_texts, indices)
            for batch_texts, indices in zip(batches, batch_indices)
        ]
        await asyncio.gather(*tasks)
        
        logger.info(f"批量 Embedding 完成: {total} 条文本 (缓存命中: {cache_hits}, 未命中: {cache_misses})")
        return EmbeddingResult(vectors=results, cache_hits=cache_hits, cache_misses=cache_misses)


# ═══════════════════════════════════════════════════════════════════════════
# 全局单例访问
# ═══════════════════════════════════════════════════════════════════════════

_model_manager_instance: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """获取 ModelManager 单例实例"""
    global _model_manager_instance
    if _model_manager_instance is None:
        _model_manager_instance = ModelManager()
    return _model_manager_instance


def get_embeddings(model_id: Optional[str] = None, **kwargs) -> Embeddings:
    """
    获取 Embedding 实例（便捷函数）
    
    统一的 Embedding 获取入口，从 ModelManager 获取模型配置并创建实例。
    
    Args:
        model_id: 模型 ID（可选，不指定则使用默认 Embedding）
        **kwargs: 其他参数
    
    Returns:
        配置好的 LangChain Embeddings 实例
    
    Examples:
        from analytics_assistant.src.infra.ai import get_embeddings
        
        # 使用默认 Embedding
        embeddings = get_embeddings()
        
        # 指定模型
        embeddings = get_embeddings(model_id="zhipu-embedding")
        
        # 使用
        vectors = embeddings.embed_documents(["文本1", "文本2"])
        query_vector = embeddings.embed_query("查询文本")
    """
    manager = get_model_manager()
    return manager.create_embedding(model_id=model_id, **kwargs)


def embed_documents_batch(
    texts: List[str],
    model_id: Optional[str] = None,
    batch_size: int = None,
    max_concurrency: int = None,
    use_cache: bool = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[List[float]]:
    """
    批量生成文档 Embedding（便捷函数）
    
    优化策略：
    1. 缓存：已计算的 embedding 直接从缓存读取
    2. 批量：将文本分批处理，每批 batch_size 条
    3. 异步并发：max_concurrency 个批次同时调用 API
    
    Args:
        texts: 文本列表
        model_id: 模型 ID（可选）
        batch_size: 每批文本数量（默认从配置读取）
        max_concurrency: 最大并发批次数（默认从配置读取）
        use_cache: 是否使用缓存（默认从配置读取）
        progress_callback: 进度回调函数 (completed, total)
    
    Returns:
        Embedding 向量列表，与输入文本一一对应
    
    Examples:
        from analytics_assistant.src.infra.ai import embed_documents_batch
        
        texts = ["文本1", "文本2", "文本3", ...]
        vectors = embed_documents_batch(
            texts,
            progress_callback=lambda done, total: print(f"进度: {done}/{total}")
        )
    """
    manager = get_model_manager()
    return manager.embed_documents_batch(
        texts=texts,
        model_id=model_id,
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        use_cache=use_cache,
        progress_callback=progress_callback,
    )


__all__ = [
    "ModelManager",
    "get_model_manager",
    "get_embeddings",
    "embed_documents_batch",
    "EmbeddingResult",
    "ModelType",
    "ModelStatus",
    "TaskType",
    "AuthType",
    "ModelConfig",
    "ModelCreateRequest",
    "ModelUpdateRequest",
]
