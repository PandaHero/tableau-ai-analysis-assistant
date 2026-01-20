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
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


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
    5. 持久化存储（LangGraph SqliteStore）
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._configs: Dict[str, ModelConfig] = {}
            self._defaults: Dict[ModelType, str] = {}
            self._store = None  # LangGraph SqliteStore（阶段 1.3 实现）
            logger.info("ModelManager initialized")
            
            # 从环境变量加载配置
            self._load_from_env()
            
            # 从 YAML 文件加载配置（如果存在）
            self._load_from_yaml()
    
    # ═══════════════════════════════════════════════════════════════════════
    # 配置加载
    # ═══════════════════════════════════════════════════════════════════════
    
    def _load_from_yaml(self, config_path: str = "config/models.yaml"):
        """从 YAML 文件加载配置"""
        try:
            from .config_loader import load_models_from_yaml
            
            # 加载配置
            config_data = load_models_from_yaml(config_path)
            
            # 加载 LLM 模型
            for model_data in config_data.get('llm_models', []):
                try:
                    self._create_from_dict(model_data)
                except Exception as e:
                    logger.warning(f"加载 LLM 模型配置失败 {model_data.get('id')}: {e}")
            
            # 加载 Embedding 模型
            for model_data in config_data.get('embedding_models', []):
                try:
                    self._create_from_dict(model_data)
                except Exception as e:
                    logger.warning(f"加载 Embedding 模型配置失败 {model_data.get('id')}: {e}")
            
            logger.info(f"从 YAML 加载了 {len(self._configs)} 个模型配置")
            
        except Exception as e:
            logger.debug(f"YAML 配置加载失败（将使用环境变量配置）: {e}")
    
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
    # 环境变量加载
    # ═══════════════════════════════════════════════════════════════════════
    
    def _load_from_env(self):
        """从环境变量加载默认配置"""
        # 加载 LLM 配置
        llm_api_base = os.getenv("LLM_API_BASE")
        llm_api_key = os.getenv("LLM_API_KEY")
        llm_model_name = os.getenv("LLM_MODEL_NAME", "qwen3")
        
        if llm_api_base and llm_api_key:
            # 创建默认 LLM 配置
            default_llm_config = ModelConfig(
                id="env-default-llm",
                name="Default LLM (from env)",
                model_type=ModelType.LLM,
                provider="local",
                api_base=llm_api_base,
                model_name=llm_model_name,
                api_key=llm_api_key,
                openai_compatible=True,
                temperature=0.7,
                supports_streaming=True,
                supports_json_mode=True,
                suitable_tasks=[
                    TaskType.SEMANTIC_PARSING,
                    TaskType.FIELD_MAPPING,
                    TaskType.DIMENSION_HIERARCHY,
                    TaskType.INSIGHT_GENERATION,
                    TaskType.REPLANNING,
                ],
                priority=10,
                is_default=True,
                status=ModelStatus.ACTIVE,
            )
            self._configs[default_llm_config.id] = default_llm_config
            self._defaults[ModelType.LLM] = default_llm_config.id
            logger.info(f"Loaded default LLM from env: {llm_model_name} at {llm_api_base}")
        
        # 加载 Embedding 配置
        zhipu_api_key = os.getenv("ZHIPUAI_API_KEY") or os.getenv("ZHIPU_API_KEY")
        if zhipu_api_key:
            # 创建智谱 Embedding 配置
            zhipu_embedding_config = ModelConfig(
                id="env-zhipu-embedding",
                name="Zhipu Embedding (from env)",
                model_type=ModelType.EMBEDDING,
                provider="zhipu",
                api_base="https://open.bigmodel.cn/api/paas/v4",
                model_name="embedding-2",
                api_key=zhipu_api_key,
                openai_compatible=True,
                suitable_tasks=[TaskType.EMBEDDING],
                priority=10,
                is_default=True,
                status=ModelStatus.ACTIVE,
            )
            self._configs[zhipu_embedding_config.id] = zhipu_embedding_config
            self._defaults[ModelType.EMBEDDING] = zhipu_embedding_config.id
            logger.info("Loaded Zhipu Embedding from env")
    
    # ═══════════════════════════════════════════════════════════════════════
    # CRUD 操作
    # ═══════════════════════════════════════════════════════════════════════
    
    def create(self, request: ModelCreateRequest) -> ModelConfig:
        """创建新模型配置"""
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
        
        # 如果是默认模型，更新默认配置
        if request.is_default:
            self._defaults[request.model_type] = model_id
        
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
        
        logger.info(f"Updated model config: {model_id}")
        return config
    
    def delete(self, model_id: str) -> bool:
        """删除模型配置"""
        if model_id in self._configs:
            del self._configs[model_id]
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


__all__ = [
    "ModelManager",
    "get_model_manager",
    "ModelType",
    "ModelStatus",
    "TaskType",
    "AuthType",
    "ModelConfig",
    "ModelCreateRequest",
    "ModelUpdateRequest",
]
