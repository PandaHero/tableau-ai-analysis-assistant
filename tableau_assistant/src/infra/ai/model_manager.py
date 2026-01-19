# -*- coding: utf-8 -*-
"""
模型管理器

生产级别的 LLM 和 Embedding 模型管理系统。

功能：
- 模型配置的 CRUD 操作（新增、查询、更新、删除）
- 持久化存储（LangGraph SqliteStore）
- 模型健康检查和连接测试
- 默认模型设置
- 模型使用统计
- 支持多种模型类型（LLM、Embedding）
- 支持自定义 API 端点（通过 URL 重写）

参考：
- OpenRouter: 多模型路由
- LiteLLM: 统一 API 接口
- One API: 模型管理和负载均衡
"""
import json
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, field_validator
import httpx

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 枚举和常量
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


# 存储命名空间
MODEL_CONFIG_NAMESPACE = ("model_manager", "configs")
MODEL_STATS_NAMESPACE = ("model_manager", "stats")
MODEL_DEFAULTS_NAMESPACE = ("model_manager", "defaults")


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

class ModelConfig(BaseModel):
    """模型配置
    
    统一的模型配置模型，支持 LLM、Embedding。
    
    设计原则：
    - temperature/max_tokens 等参数使用 None 表示"使用模型默认值"
    - 前端只需传必要字段，其他使用智能默认值
    - openai_compatible 标记是否使用 OpenAI 兼容模式
    """
    # 基本信息
    id: str = Field(..., description="模型唯一标识（自动生成或用户指定）")
    name: str = Field(..., description="模型显示名称")
    description: str = Field(default="", description="模型描述")
    model_type: ModelType = Field(..., description="模型类型")
    
    # API 配置
    provider: str = Field(..., description="提供商（openai, azure, zhipu, deepseek, qwen, kimi, custom 等）")
    api_base: str = Field(..., description="API 基础 URL")
    api_endpoint: str = Field(default="", description="API 端点路径（留空使用默认）")
    model_name: str = Field(..., description="模型名称（API 参数）")
    
    # ⭐ 兼容性标记（关键优化）
    openai_compatible: bool = Field(default=True, description="是否使用 OpenAI 兼容模式（大多数模型都兼容）")
    
    # 认证配置
    auth_type: AuthType = Field(default=AuthType.BEARER, description="认证类型")
    auth_header: str = Field(default="Authorization", description="认证 header 名称")
    api_key: str = Field(default="", description="API Key（加密存储）")
    
    # 模型参数（LLM）- None 表示使用模型默认值
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0, description="温度参数（None=使用模型默认）")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="最大 token 数（None=使用模型默认）")
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Top-p 采样（None=使用模型默认）")
    
    # 模型参数（Embedding）
    dimensions: Optional[int] = Field(default=None, ge=1, description="向量维度（None=使用模型默认）")
    batch_size: int = Field(default=32, ge=1, description="批量处理大小")
    
    # 特性配置
    supports_streaming: bool = Field(default=True, description="是否支持流式输出")
    supports_thinking: bool = Field(default=False, description="是否支持思考过程")
    thinking_tag: str = Field(default="think", description="思考过程标签名")
    supports_function_calling: bool = Field(default=False, description="是否支持函数调用")
    supports_vision: bool = Field(default=False, description="是否支持视觉")
    supports_json_mode: Optional[bool] = Field(
        default=None,
        description="是否支持 JSON Mode（显式配置优先；None=按 provider 默认能力判断）",
    )

    
    # 网络配置
    timeout: float = Field(default=120.0, ge=1.0, description="请求超时时间（秒）")
    verify_ssl: bool = Field(default=True, description="是否验证 SSL 证书")
    proxy: str = Field(default="", description="代理服务器")
    
    # 额外配置
    extra_headers: Dict[str, str] = Field(default_factory=dict, description="额外请求头")
    extra_body: Dict[str, Any] = Field(default_factory=dict, description="额外请求体参数")
    
    # 状态和元数据
    status: ModelStatus = Field(default=ModelStatus.ACTIVE, description="模型状态")
    is_default: bool = Field(default=False, description="是否为默认模型")
    tags: List[str] = Field(default_factory=list, description="标签")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    last_used_at: Optional[datetime] = Field(default=None, description="最后使用时间")
    last_health_check: Optional[datetime] = Field(default=None, description="最后健康检查时间")
    
    @field_validator('id', mode='before')
    @classmethod
    def generate_id(cls, v, info):
        """如果未提供 ID，自动生成"""
        if not v:
            import hashlib
            name = info.data.get('name', '')
            provider = info.data.get('provider', '')
            model_type = info.data.get('model_type', '')
            key = f"{name}:{provider}:{model_type}:{time.time()}"
            return hashlib.md5(key.encode()).hexdigest()[:12]
        return v
    
    def mask_api_key(self) -> str:
        """返回脱敏的 API Key"""
        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return "****"
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"
    
    def to_safe_dict(self) -> Dict[str, Any]:
        """返回安全的字典（API Key 脱敏）"""
        data = self.model_dump()
        data['api_key'] = self.mask_api_key()
        return data


class ModelStats(BaseModel):
    """模型使用统计"""
    model_id: str
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests
    
    @property
    def avg_latency_ms(self) -> float:
        """平均延迟"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency_ms / self.successful_requests


class HealthCheckResult(BaseModel):
    """健康检查结果"""
    model_id: str
    success: bool
    latency_ms: float = 0.0
    error: Optional[str] = None
    checked_at: datetime = Field(default_factory=datetime.now)


class ModelCreateRequest(BaseModel):
    """创建模型请求
    
    前端只需传必要字段，其他使用智能默认值。
    
    必填字段：
    - name: 模型显示名称
    - model_type: 模型类型（llm/embedding）
    - provider: 提供商
    - api_base: API 地址
    - model_name: 模型名称
    - api_key: API Key
    
    可选字段（有智能默认值）：
    - openai_compatible: 是否 OpenAI 兼容（默认 True）
    - temperature/max_tokens: None 表示使用模型默认值
    """
    # 必填
    name: str
    model_type: ModelType
    provider: str
    api_base: str
    model_name: str
    api_key: str
    
    # 可选 - 基本信息
    description: str = ""
    api_endpoint: str = ""
    
    # ⭐ 兼容性标记（默认 True，大多数模型都兼容 OpenAI API）
    openai_compatible: bool = True
    
    # 可选 - 认证（默认 Bearer Token）
    auth_type: AuthType = AuthType.BEARER
    auth_header: str = "Authorization"
    
    # 可选 - 模型参数（None = 使用模型默认值，不传给 API）
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    dimensions: Optional[int] = None
    batch_size: int = 32
    
    # 可选 - 特性（有合理默认值）
    supports_streaming: bool = True
    supports_thinking: bool = False
    thinking_tag: str = "think"
    supports_function_calling: bool = False
    supports_vision: bool = False
    
    # 可选 - 网络
    timeout: float = 120.0
    verify_ssl: bool = True
    proxy: str = ""
    
    # 可选 - 扩展
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    extra_body: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    is_default: bool = False


class ModelUpdateRequest(BaseModel):
    """更新模型请求（所有字段可选）"""
    name: Optional[str] = None
    description: Optional[str] = None
    api_base: Optional[str] = None
    api_endpoint: Optional[str] = None
    model_name: Optional[str] = None
    openai_compatible: Optional[bool] = None
    auth_type: Optional[AuthType] = None
    auth_header: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    dimensions: Optional[int] = None
    batch_size: Optional[int] = None
    supports_streaming: Optional[bool] = None
    supports_thinking: Optional[bool] = None
    thinking_tag: Optional[str] = None
    supports_function_calling: Optional[bool] = None
    supports_vision: Optional[bool] = None
    timeout: Optional[float] = None
    verify_ssl: Optional[bool] = None
    proxy: Optional[str] = None
    extra_headers: Optional[Dict[str, str]] = None
    extra_body: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    status: Optional[ModelStatus] = None
    is_default: Optional[bool] = None


# ═══════════════════════════════════════════════════════════════════════════
# 模型管理器
# ═══════════════════════════════════════════════════════════════════════════

class ModelManager:
    """模型管理器
    
    生产级别的模型管理系统，支持：
    - 模型配置的 CRUD 操作
    - 持久化存储（LangGraph SqliteStore）
    - 模型健康检查
    - 默认模型管理
    - 使用统计
    
    使用示例：
        manager = get_model_manager()
        
        # 创建模型
        config = manager.create(ModelCreateRequest(
            name="GPT-4",
            model_type=ModelType.LLM,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="gpt-4",
            api_key="sk-xxx",
        ))
        
        # 获取模型
        config = manager.get("model_id")
        
        # 更新模型
        config = manager.update("model_id", ModelUpdateRequest(temperature=0.5))
        
        # 删除模型
        manager.delete("model_id")
        
        # 获取默认模型
        llm_config = manager.get_default(ModelType.LLM)
        
        # 健康检查
        result = await manager.health_check("model_id")
    """
    
    _instance: Optional["ModelManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._store = None
        self._configs: Dict[str, ModelConfig] = {}
        self._stats: Dict[str, ModelStats] = {}
        self._defaults: Dict[ModelType, str] = {}
        
        # 初始化存储
        self._init_store()
        
        # 从存储加载配置
        self._load_from_store()
        
        # 从环境变量加载预配置模型
        self._load_from_env()
        
        self._initialized = True
    
    def _init_store(self) -> None:
        """初始化存储"""
        try:
            from tableau_assistant.src.infra.storage import get_langgraph_store
            self._store = get_langgraph_store()
            logger.info("模型管理器存储初始化成功")
        except Exception as e:
            logger.warning(f"模型管理器存储初始化失败，将使用内存存储: {e}")
            self._store = None
    
    def _load_from_store(self) -> None:
        """从持久化存储加载配置"""
        if not self._store:
            return
        
        try:
            # 加载模型配置
            # 注意：LangGraph SqliteStore.search 默认 limit=10，必须显式传递较大值
            items = self._store.search(MODEL_CONFIG_NAMESPACE, limit=1000)
            for item in items:
                try:
                    config = ModelConfig(**item.value)
                    self._configs[config.id] = config
                except Exception as e:
                    logger.warning(f"加载模型配置失败: {e}")
            
            # 加载统计信息
            stats_items = self._store.search(MODEL_STATS_NAMESPACE, limit=1000)
            for item in stats_items:
                try:
                    stats = ModelStats(**item.value)
                    self._stats[stats.model_id] = stats
                except Exception as e:
                    logger.warning(f"加载模型统计失败: {e}")
            
            # 加载默认模型设置
            defaults_item = self._store.get(MODEL_DEFAULTS_NAMESPACE, "defaults")
            if defaults_item:
                for model_type_str, model_id in defaults_item.value.items():
                    try:
                        model_type = ModelType(model_type_str)
                        self._defaults[model_type] = model_id
                    except ValueError:
                        pass
            
            logger.info(f"从存储加载了 {len(self._configs)} 个模型配置")
            
        except Exception as e:
            logger.warning(f"从存储加载配置失败: {e}")
    
    def _load_from_env(self) -> None:
        """从环境变量加载预配置模型"""
        from tableau_assistant.src.infra.config import settings
        
        # 加载自定义 LLM（如果配置了且不存在）
        if settings.custom_llm_api_base and settings.custom_llm_api_key:
            model_id = "env-custom-llm"
            if model_id not in self._configs:
                config = ModelConfig(
                    id=model_id,
                    name="自定义大模型",
                    description="从环境变量加载的自定义大模型",
                    model_type=ModelType.LLM,
                    provider="custom",
                    api_base=settings.custom_llm_api_base,
                    api_endpoint=settings.custom_llm_api_endpoint,
                    model_name=settings.custom_llm_model_name or "custom-model",
                    openai_compatible=False,  # 自定义 API 默认不兼容
                    auth_type=AuthType.API_KEY_HEADER,
                    api_key=settings.custom_llm_api_key,
                    # temperature/max_tokens 不设置，使用模型默认值
                    supports_thinking=True,
                    thinking_tag="think",
                    verify_ssl=False,
                    tags=["env", "custom"],
                )
                self._configs[model_id] = config
                logger.info(f"从环境变量加载自定义 LLM: {model_id}")
                
                # 如果没有默认 LLM，设置为默认
                if ModelType.LLM not in self._defaults:
                    self._defaults[ModelType.LLM] = model_id
        
        # 加载智谱 Embedding（如果配置了且不存在）
        if settings.zhipuai_api_key:
            model_id = "env-zhipu-embedding"
            if model_id not in self._configs:
                config = ModelConfig(
                    id=model_id,
                    name="智谱 Embedding",
                    description="智谱 AI embedding-2 模型",
                    model_type=ModelType.EMBEDDING,
                    provider="zhipu",
                    api_base="https://open.bigmodel.cn/api/paas/v4",
                    model_name="embedding-2",
                    openai_compatible=False,  # 智谱使用专用 SDK
                    auth_type=AuthType.BEARER,
                    api_key=settings.zhipuai_api_key,
                    dimensions=1024,
                    tags=["env", "zhipu"],
                )
                self._configs[model_id] = config
                logger.info(f"从环境变量加载智谱 Embedding: {model_id}")
                
                # 如果没有默认 Embedding，设置为默认
                if ModelType.EMBEDDING not in self._defaults:
                    self._defaults[ModelType.EMBEDDING] = model_id
    
    def _save_config(self, config: ModelConfig) -> None:
        """保存单个配置到存储"""
        if not self._store:
            return
        
        try:
            self._store.put(
                MODEL_CONFIG_NAMESPACE,
                config.id,
                config.model_dump(mode='json'),
            )
        except Exception as e:
            logger.error(f"保存模型配置失败: {e}")
    
    def _delete_config(self, model_id: str) -> None:
        """从存储删除配置"""
        if not self._store:
            return
        
        try:
            self._store.delete(MODEL_CONFIG_NAMESPACE, model_id)
        except Exception as e:
            logger.error(f"删除模型配置失败: {e}")
    
    def _save_defaults(self) -> None:
        """保存默认模型设置"""
        if not self._store:
            return
        
        try:
            defaults_dict = {k.value: v for k, v in self._defaults.items()}
            self._store.put(
                MODEL_DEFAULTS_NAMESPACE,
                "defaults",
                defaults_dict,
            )
        except Exception as e:
            logger.error(f"保存默认模型设置失败: {e}")
    
    def _save_stats(self, stats: ModelStats) -> None:
        """保存统计信息"""
        if not self._store:
            return
        
        try:
            self._store.put(
                MODEL_STATS_NAMESPACE,
                stats.model_id,
                stats.model_dump(mode='json'),
            )
        except Exception as e:
            logger.error(f"保存模型统计失败: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # CRUD 操作
    # ═══════════════════════════════════════════════════════════════════════
    
    def create(self, request: ModelCreateRequest) -> ModelConfig:
        """创建新模型配置
        
        Args:
            request: 创建请求
            
        Returns:
            创建的模型配置
            
        Raises:
            ValueError: 模型名称已存在
        """
        # 检查名称是否重复
        for config in self._configs.values():
            if config.name == request.name and config.model_type == request.model_type:
                raise ValueError(f"模型名称已存在: {request.name}")
        
        # 创建配置
        config = ModelConfig(
            id="",  # 自动生成
            **request.model_dump(),
        )
        
        # 如果设置为默认，更新默认设置
        if request.is_default:
            self._defaults[config.model_type] = config.id
            # 取消其他同类型模型的默认状态
            for other in self._configs.values():
                if other.model_type == config.model_type and other.is_default:
                    other.is_default = False
                    self._save_config(other)
        
        # 保存
        self._configs[config.id] = config
        self._save_config(config)
        self._save_defaults()
        
        logger.info(f"创建模型配置: {config.id} ({config.name})")
        return config
    
    def get(self, model_id: str) -> Optional[ModelConfig]:
        """获取模型配置
        
        Args:
            model_id: 模型 ID
            
        Returns:
            模型配置，不存在返回 None
        """
        return self._configs.get(model_id)
    
    def get_by_name(self, name: str, model_type: Optional[ModelType] = None) -> Optional[ModelConfig]:
        """按名称获取模型配置
        
        Args:
            name: 模型名称
            model_type: 模型类型（可选）
            
        Returns:
            模型配置，不存在返回 None
        """
        for config in self._configs.values():
            if config.name == name:
                if model_type is None or config.model_type == model_type:
                    return config
        return None
    
    def list(
        self,
        model_type: Optional[ModelType] = None,
        status: Optional[ModelStatus] = None,
        tags: Optional[List[str]] = None,
        include_api_key: bool = False,
    ) -> List[ModelConfig]:
        """列出模型配置
        
        Args:
            model_type: 按类型过滤
            status: 按状态过滤
            tags: 按标签过滤（任意匹配）
            include_api_key: 是否包含完整 API Key
            
        Returns:
            模型配置列表
        """
        results = []
        
        for config in self._configs.values():
            # 类型过滤
            if model_type and config.model_type != model_type:
                continue
            
            # 状态过滤
            if status and config.status != status:
                continue
            
            # 标签过滤
            if tags:
                if not any(tag in config.tags for tag in tags):
                    continue
            
            # 脱敏处理
            if not include_api_key:
                config_copy = config.model_copy()
                config_copy.api_key = config.mask_api_key()
                results.append(config_copy)
            else:
                results.append(config)
        
        # 按创建时间排序
        results.sort(key=lambda x: x.created_at, reverse=True)
        return results
    
    def update(self, model_id: str, request: ModelUpdateRequest) -> Optional[ModelConfig]:
        """更新模型配置
        
        Args:
            model_id: 模型 ID
            request: 更新请求
            
        Returns:
            更新后的配置，不存在返回 None
        """
        config = self._configs.get(model_id)
        if not config:
            return None
        
        # 更新字段
        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(config, field, value)
        
        # 更新时间戳
        config.updated_at = datetime.now()
        
        # 处理默认模型设置
        if request.is_default is True:
            self._defaults[config.model_type] = config.id
            # 取消其他同类型模型的默认状态
            for other in self._configs.values():
                if other.id != config.id and other.model_type == config.model_type and other.is_default:
                    other.is_default = False
                    self._save_config(other)
        elif request.is_default is False and self._defaults.get(config.model_type) == config.id:
            del self._defaults[config.model_type]
        
        # 保存
        self._save_config(config)
        self._save_defaults()
        
        logger.info(f"更新模型配置: {config.id} ({config.name})")
        return config
    
    def delete(self, model_id: str) -> bool:
        """删除模型配置
        
        Args:
            model_id: 模型 ID
            
        Returns:
            是否删除成功
        """
        config = self._configs.get(model_id)
        if not config:
            return False
        
        # 如果是默认模型，清除默认设置
        if self._defaults.get(config.model_type) == model_id:
            del self._defaults[config.model_type]
            self._save_defaults()
        
        # 删除配置
        del self._configs[model_id]
        self._delete_config(model_id)
        
        # 删除统计信息
        if model_id in self._stats:
            del self._stats[model_id]
        
        logger.info(f"删除模型配置: {model_id}")
        return True

    # ═══════════════════════════════════════════════════════════════════════
    # 默认模型管理
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_default(self, model_type: ModelType) -> Optional[ModelConfig]:
        """获取默认模型
        
        Args:
            model_type: 模型类型
            
        Returns:
            默认模型配置，未设置返回 None
        """
        model_id = self._defaults.get(model_type)
        if model_id:
            return self._configs.get(model_id)
        return None
    
    def set_default(self, model_id: str) -> bool:
        """设置默认模型
        
        Args:
            model_id: 模型 ID
            
        Returns:
            是否设置成功
        """
        config = self._configs.get(model_id)
        if not config:
            return False
        
        # 取消旧默认模型的标记
        old_default_id = self._defaults.get(config.model_type)
        if old_default_id and old_default_id in self._configs:
            old_config = self._configs[old_default_id]
            old_config.is_default = False
            self._save_config(old_config)
        
        # 设置新默认
        self._defaults[config.model_type] = model_id
        config.is_default = True
        self._save_config(config)
        self._save_defaults()
        
        logger.info(f"设置默认 {config.model_type.value} 模型: {model_id}")
        return True
    
    def get_defaults(self) -> Dict[ModelType, Optional[ModelConfig]]:
        """获取所有默认模型
        
        Returns:
            各类型的默认模型配置
        """
        return {
            model_type: self.get_default(model_type)
            for model_type in ModelType
        }
    
    # ═══════════════════════════════════════════════════════════════════════
    # 健康检查
    # ═══════════════════════════════════════════════════════════════════════
    
    async def health_check(self, model_id: str) -> HealthCheckResult:
        """执行模型健康检查
        
        Args:
            model_id: 模型 ID
            
        Returns:
            健康检查结果
        """
        config = self._configs.get(model_id)
        if not config:
            return HealthCheckResult(
                model_id=model_id,
                success=False,
                error="模型不存在",
            )
        
        start_time = time.time()
        
        try:
            if config.model_type == ModelType.LLM:
                await self._check_llm(config)
            elif config.model_type == ModelType.EMBEDDING:
                await self._check_embedding(config)
            
            latency_ms = (time.time() - start_time) * 1000
            
            # 更新状态
            config.status = ModelStatus.ACTIVE
            config.last_health_check = datetime.now()
            self._save_config(config)
            
            return HealthCheckResult(
                model_id=model_id,
                success=True,
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = str(e)
            
            # 更新状态
            config.status = ModelStatus.ERROR
            config.last_health_check = datetime.now()
            self._save_config(config)
            
            # 更新统计
            stats = self._get_or_create_stats(model_id)
            stats.last_error = error_msg
            stats.last_error_at = datetime.now()
            self._save_stats(stats)
            
            return HealthCheckResult(
                model_id=model_id,
                success=False,
                latency_ms=latency_ms,
                error=error_msg,
            )
    
    async def _check_llm(self, config: ModelConfig) -> None:
        """检查 LLM 连接"""
        import httpx
        
        url = config.api_base.rstrip('/')
        endpoint = config.api_endpoint or "/v1/chat/completions"
        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint
        url = f"{url}{endpoint}"
        
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            if config.auth_type == AuthType.BEARER:
                headers["Authorization"] = f"Bearer {config.api_key}"
            elif config.auth_type == AuthType.API_KEY_HEADER:
                headers["Apikey"] = config.api_key
            elif config.auth_type == AuthType.CUSTOM_HEADER:
                headers[config.auth_header] = config.api_key
        
        payload = {
            "model": config.model_name,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 5,
        }
        
        async with httpx.AsyncClient(verify=config.verify_ssl, timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
    
    async def _check_embedding(self, config: ModelConfig) -> None:
        """检查 Embedding 连接"""
        import httpx
        
        url = config.api_base.rstrip('/')
        endpoint = config.api_endpoint or "/v1/embeddings"
        if not endpoint.startswith('/'):
            endpoint = '/' + endpoint
        url = f"{url}{endpoint}"
        
        headers = {"Content-Type": "application/json"}
        if config.api_key:
            if config.auth_type == AuthType.BEARER:
                headers["Authorization"] = f"Bearer {config.api_key}"
            elif config.auth_type == AuthType.API_KEY_HEADER:
                headers["Apikey"] = config.api_key
            elif config.auth_type == AuthType.CUSTOM_HEADER:
                headers[config.auth_header] = config.api_key
        
        payload = {
            "model": config.model_name,
            "input": ["test"],
        }
        
        async with httpx.AsyncClient(verify=config.verify_ssl, timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
    
    async def health_check_all(self) -> List[HealthCheckResult]:
        """检查所有活跃模型的健康状态
        
        Returns:
            所有模型的健康检查结果
        """
        import asyncio
        
        active_configs = [c for c in self._configs.values() if c.status != ModelStatus.INACTIVE]
        
        tasks = [self.health_check(c.id) for c in active_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return [r for r in results if isinstance(r, HealthCheckResult)]
    
    # ═══════════════════════════════════════════════════════════════════════
    # 统计信息
    # ═══════════════════════════════════════════════════════════════════════
    
    def _get_or_create_stats(self, model_id: str) -> ModelStats:
        """获取或创建统计信息"""
        if model_id not in self._stats:
            self._stats[model_id] = ModelStats(model_id=model_id)
        return self._stats[model_id]
    
    def record_request(
        self,
        model_id: str,
        success: bool,
        latency_ms: float,
        tokens: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """记录请求统计
        
        Args:
            model_id: 模型 ID
            success: 是否成功
            latency_ms: 延迟（毫秒）
            tokens: 使用的 token 数
            error: 错误信息
        """
        stats = self._get_or_create_stats(model_id)
        stats.total_requests += 1
        
        if success:
            stats.successful_requests += 1
            stats.total_latency_ms += latency_ms
            stats.total_tokens += tokens
        else:
            stats.failed_requests += 1
            stats.last_error = error
            stats.last_error_at = datetime.now()
        
        # 更新最后使用时间
        config = self._configs.get(model_id)
        if config:
            config.last_used_at = datetime.now()
            self._save_config(config)
        
        self._save_stats(stats)
    
    def get_stats(self, model_id: str) -> Optional[ModelStats]:
        """获取模型统计信息
        
        Args:
            model_id: 模型 ID
            
        Returns:
            统计信息
        """
        return self._stats.get(model_id)
    
    def get_all_stats(self) -> Dict[str, ModelStats]:
        """获取所有模型的统计信息"""
        return self._stats.copy()
    
    # ═══════════════════════════════════════════════════════════════════════
    # 模型实例创建
    # ═══════════════════════════════════════════════════════════════════════
    
    def create_llm(self, model_id: Optional[str] = None, **kwargs) -> Any:
        """创建 LLM 实例
        
        Args:
            model_id: 模型 ID（不指定则使用默认）
            **kwargs: 覆盖参数（如 temperature）
            
        Returns:
            LangChain BaseChatModel 实例
        """
        if model_id:
            config = self.get(model_id)
        else:
            config = self.get_default(ModelType.LLM)
        
        if not config:
            raise ValueError("未找到 LLM 模型配置")
        
        if config.model_type != ModelType.LLM:
            raise ValueError(f"模型类型不匹配: {config.model_type}")
        
        return self._create_llm_from_config(config, **kwargs)
    
    def _create_llm_from_config(self, config: ModelConfig, **kwargs) -> Any:
        """从配置创建 LLM 实例
        
        路由逻辑：
        1. Azure OpenAI → AzureChatOpenAI
        2. 非 OpenAI 兼容（自定义端点）→ CustomLLMChat
        3. OpenAI 兼容 → ChatOpenAI
        
        参数处理：
        - kwargs 可覆盖配置中的参数
        - enable_json_mode: 是否启用 JSON Mode（通过 Provider 适配层）
        """
        from langchain_openai import ChatOpenAI, AzureChatOpenAI
        from tableau_assistant.src.infra.ai.json_mode_adapter import (
            get_json_mode_kwargs,
            get_provider_from_config,
            supports_json_mode,
        )
        
        # 合并参数：kwargs 优先，然后是 config
        temperature = kwargs.get('temperature', config.temperature)
        max_tokens = kwargs.get('max_tokens', config.max_tokens)
        enable_json_mode = kwargs.pop('enable_json_mode', False)
        
        # Azure OpenAI（特殊处理）
        if config.provider == "azure":
            azure_kwargs = {
                "azure_deployment": config.model_name,
                "azure_endpoint": config.api_base,
                "openai_api_key": config.api_key,
                "openai_api_version": config.extra_body.get("api_version", "2024-02-15-preview"),
            }
            if temperature is not None:
                azure_kwargs["temperature"] = temperature
            if max_tokens is not None:
                azure_kwargs["max_tokens"] = max_tokens
            
            # JSON Mode 支持
            if enable_json_mode:
                from tableau_assistant.src.infra.ai.json_mode_adapter import ProviderType

                json_kwargs = get_json_mode_kwargs(ProviderType.AZURE, True)
                if json_kwargs.get("model_kwargs"):
                    azure_kwargs["model_kwargs"] = json_kwargs["model_kwargs"]
                    logger.debug(f"JSON Mode enabled for Azure OpenAI model {config.model_name}")
            
            return AzureChatOpenAI(**azure_kwargs)
        
        # 非 OpenAI 兼容模型（自定义端点）→ 使用 CustomLLMChat
        if not config.openai_compatible:
            from tableau_assistant.src.infra.ai.custom_llm import CustomLLMChat, CustomLLMConfig
            from tableau_assistant.src.infra.ai.custom_llm import AuthType as CustomAuthType
            from tableau_assistant.src.infra.ai.json_mode_adapter import ProviderType

            
            # 转换 AuthType
            auth_type_map = {
                AuthType.BEARER: CustomAuthType.BEARER,
                AuthType.API_KEY_HEADER: CustomAuthType.API_KEY_HEADER,
                AuthType.CUSTOM_HEADER: CustomAuthType.CUSTOM_HEADER,
                AuthType.NONE: CustomAuthType.NONE,
            }
            
            # 准备 extra_body，合并 JSON Mode 参数
            extra_body = dict(config.extra_body or {})
            json_mode_fallback_provider = None
            if enable_json_mode:
                json_mode_supported = (
                    config.supports_json_mode
                    if config.supports_json_mode is not None
                    else True
                )
                if json_mode_supported:
                    json_kwargs = get_json_mode_kwargs(ProviderType.CUSTOM, True)
                    if json_kwargs.get("extra_body"):
                        extra_body.update(json_kwargs["extra_body"])
                        logger.debug(f"JSON Mode enabled for CustomLLMChat model {config.model_name}")
                else:
                    json_mode_fallback_provider = ProviderType.CUSTOM.value
                    logger.info(
                        "JSON Mode not supported for custom provider, relying on prompt constraints",
                        extra={"json_mode_fallback": True, "provider": ProviderType.CUSTOM.value},
                    )

            
            custom_config = CustomLLMConfig(
                name=config.name,
                display_name=config.name,
                description=config.description,
                api_base=config.api_base,
                api_endpoint=config.api_endpoint or "/v1/chat/completions",
                model_name=config.model_name,
                auth_type=auth_type_map.get(config.auth_type, CustomAuthType.BEARER),
                auth_header=config.auth_header,
                api_key=config.api_key,
                temperature=temperature if temperature is not None else 0.2,
                max_tokens=max_tokens if max_tokens is not None else 4096,
                timeout=config.timeout,
                supports_streaming=config.supports_streaming,
                supports_thinking=config.supports_thinking,
                thinking_tag=config.thinking_tag,
                verify_ssl=config.verify_ssl,
                extra_headers=config.extra_headers or {},
                extra_body=extra_body,
            )
            llm = CustomLLMChat(config=custom_config)
            try:
                setattr(llm, "_provider", ProviderType.CUSTOM.value)
            except Exception:
                pass
            if enable_json_mode and json_mode_fallback_provider:
                try:
                    setattr(llm, "_json_mode_fallback", True)
                    setattr(llm, "_json_mode_fallback_provider", json_mode_fallback_provider)
                except Exception:
                    pass
            return llm

        
        # OpenAI 兼容模型 → 使用 ChatOpenAI
        openai_kwargs = {
            "model_name": config.model_name,
            "api_key": config.api_key,
        }
        
        # 非 OpenAI 官方 API 设置 base_url
        if "api.openai.com" not in config.api_base:
            openai_kwargs["base_url"] = config.api_base
        
        if temperature is not None:
            openai_kwargs["temperature"] = temperature
        if max_tokens is not None:
            openai_kwargs["max_tokens"] = max_tokens
        
        # JSON Mode 支持
        json_mode_fallback_provider = None
        if enable_json_mode:
            provider = get_provider_from_config(
                provider_str=config.provider,
                base_url=config.api_base,
                openai_compatible=config.openai_compatible,
            )
            json_mode_supported = (
                config.supports_json_mode
                if config.supports_json_mode is not None
                else supports_json_mode(provider)
            )
            if json_mode_supported:
                json_kwargs = get_json_mode_kwargs(provider, True)
                if json_kwargs.get("model_kwargs"):
                    openai_kwargs["model_kwargs"] = json_kwargs["model_kwargs"]
                    logger.debug(f"JSON Mode enabled for {provider.value} model {config.model_name}")
            else:
                # JSON Mode 降级（Requirements 0.7）
                # 这里只做“能力判定 + 标记”，真正的 metrics 累加在调用侧完成（避免 infra 层依赖 workflow/state）
                json_mode_fallback_provider = provider.value
                logger.info(
                    f"JSON Mode not supported for {provider.value}, relying on prompt constraints",
                    extra={"json_mode_fallback": True, "provider": provider.value},
                )

        
        # 额外 headers
        if config.extra_headers:
            openai_kwargs["default_headers"] = config.extra_headers
        
        # SSL 验证
        if not config.verify_ssl:
            openai_kwargs["http_client"] = httpx.Client(verify=False, timeout=config.timeout)
            openai_kwargs["http_async_client"] = httpx.AsyncClient(verify=False, timeout=config.timeout)
        
        llm = ChatOpenAI(**openai_kwargs)
        try:
            setattr(llm, "_provider", provider.value)
        except Exception:
            pass
        if enable_json_mode and json_mode_fallback_provider:
            # 供调用侧（有 RunnableConfig/metrics）累加 json_mode_fallback_count
            try:
                setattr(llm, "_json_mode_fallback", True)
                setattr(llm, "_json_mode_fallback_provider", json_mode_fallback_provider)
            except Exception:
                # 某些模型/封装可能禁止 setattr；忽略但保留日志。
                pass
        return llm


    
    def create_embedding(self, model_id: Optional[str] = None, **kwargs) -> Any:
        """创建 Embedding 实例
        
        Args:
            model_id: 模型 ID（不指定则使用默认）
            **kwargs: 覆盖参数
            
        Returns:
            EmbeddingProvider 实例
        """
        if model_id:
            config = self.get(model_id)
        else:
            config = self.get_default(ModelType.EMBEDDING)
        
        if not config:
            raise ValueError("未找到 Embedding 模型配置")
        
        if config.model_type != ModelType.EMBEDDING:
            raise ValueError(f"模型类型不匹配: {config.model_type}")
        
        return self._create_embedding_from_config(config, **kwargs)
    
    def _create_embedding_from_config(self, config: ModelConfig, **kwargs) -> Any:
        """从配置创建 Embedding 实例
        
        路由逻辑：
        1. provider=zhipu → ZhipuEmbedding（智谱专用 SDK）
        2. openai_compatible=True → OpenAIEmbedding（支持大多数 Embedding API）
        3. 其他 → 抛出异常
        """
        from tableau_assistant.src.infra.ai.embeddings import (
            ZhipuEmbedding,
            OpenAIEmbedding,
        )
        
        batch_size = kwargs.get('batch_size', config.batch_size)
        dimensions = kwargs.get('dimensions', config.dimensions)
        
        # 智谱 Embedding（使用专用 SDK）
        if config.provider == "zhipu":
            return ZhipuEmbedding(
                api_key=config.api_key,
                model_name=config.model_name,
                batch_size=batch_size,
            )
        
        # OpenAI 兼容 Embedding
        if config.openai_compatible:
            embed_kwargs = {
                "api_key": config.api_key,
                "model_name": config.model_name,
                "batch_size": batch_size,
            }
            if dimensions is not None:
                embed_kwargs["dimensions"] = dimensions
            
            # 非 OpenAI 官方 API 设置 base_url
            if "api.openai.com" not in config.api_base:
                embed_kwargs["base_url"] = config.api_base
            
            return OpenAIEmbedding(**embed_kwargs)
        
        raise ValueError(f"不支持的 Embedding 配置: provider={config.provider}, openai_compatible={config.openai_compatible}")


# ═══════════════════════════════════════════════════════════════════════════
# 单例访问
# ═══════════════════════════════════════════════════════════════════════════

_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """获取模型管理器单例"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager


def reset_model_manager() -> None:
    """重置模型管理器（用于测试）"""
    global _model_manager
    if _model_manager:
        ModelManager._instance = None
    _model_manager = None


__all__ = [
    # 枚举
    "ModelType",
    "AuthType",
    "ModelStatus",
    # 数据模型
    "ModelConfig",
    "ModelStats",
    "HealthCheckResult",
    "ModelCreateRequest",
    "ModelUpdateRequest",
    # 管理器
    "ModelManager",
    "get_model_manager",
    "reset_model_manager",
]



