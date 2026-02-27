# -*- coding: utf-8 -*-
"""
AI 模块数据模型

定义 ModelManager 相关的数据模型和枚举类型。
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════════════════
# Embedding 结果数据类
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class EmbeddingResult:
    """Embedding 结果（包含缓存信息）"""
    vectors: list[list[float]]
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
    BEARER = "bearer"
    API_KEY_HEADER = "apikey"
    CUSTOM_HEADER = "custom"
    NONE = "none"

class ModelStatus(str, Enum):
    """模型状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    TESTING = "testing"

class TaskType(str, Enum):
    """任务类型（用于智能路由）"""
    INTENT_CLASSIFICATION = "intent_classification"
    SEMANTIC_PARSING = "semantic_parsing"
    FIELD_MAPPING = "field_mapping"
    FIELD_SEMANTIC = "field_semantic"
    INSIGHT_GENERATION = "insight_generation"
    REPLANNING = "replanning"
    REASONING = "reasoning"
    EMBEDDING = "embedding"

# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

class ModelConfig(BaseModel):
    """模型配置"""
    # 基本信息
    id: str
    name: str
    description: str = ""
    model_type: ModelType
    
    # API 配置
    provider: str
    api_base: str
    api_endpoint: str = ""
    model_name: str
    
    # 兼容性标记
    openai_compatible: bool = True
    
    # 认证配置
    auth_type: AuthType = AuthType.BEARER
    auth_header: str = "Authorization"
    api_key: str = ""
    
    # 模型参数
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    
    # 特性配置
    supports_streaming: bool = True
    supports_json_mode: Optional[bool] = None
    supports_function_calling: bool = False
    supports_vision: bool = False
    is_reasoning_model: bool = False
    
    # 任务适配
    suitable_tasks: list[TaskType] = Field(default_factory=list)
    priority: int = 0
    
    # 网络配置
    timeout: float = 120.0
    verify_ssl: bool = True
    proxy: str = ""
    
    # 额外配置
    extra_headers: dict[str, str] = Field(default_factory=dict)
    extra_body: dict[str, Any] = Field(default_factory=dict)
    
    # 状态和元数据
    status: ModelStatus = ModelStatus.ACTIVE
    is_default: bool = False
    tags: list[str] = Field(default_factory=list)
    
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
    is_reasoning_model: bool = False
    suitable_tasks: list[TaskType] = Field(default_factory=list)
    priority: int = 0
    is_default: bool = False
    extra_body: dict[str, Any] = Field(default_factory=dict)

class ModelUpdateRequest(BaseModel):
    """更新模型配置请求"""
    name: Optional[str] = None
    status: Optional[ModelStatus] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    priority: Optional[int] = None
    is_default: Optional[bool] = None

__all__ = [
    "EmbeddingResult",
    "ModelType",
    "AuthType",
    "ModelStatus",
    "TaskType",
    "ModelConfig",
    "ModelCreateRequest",
    "ModelUpdateRequest",
]
