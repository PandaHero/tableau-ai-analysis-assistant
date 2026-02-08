# -*- coding: utf-8 -*-
"""
ModelRegistry - 模型配置注册表

职责：管理模型配置的 CRUD 操作

从 ModelManager 拆分出来，专注于配置管理。
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from .models import (
    ModelConfig,
    ModelCreateRequest,
    ModelUpdateRequest,
    ModelType,
    ModelStatus,
    TaskType,
    AuthType,
)

logger = logging.getLogger(__name__)


class ModelRegistry:
    """模型配置注册表
    
    职责：管理模型配置的 CRUD 操作
    
    不负责：
    - 模型实例创建（由 ModelFactory 负责）
    - 任务路由（由 TaskRouter 负责）
    - 持久化（由 ModelPersistence 负责）
    """
    
    def __init__(self):
        """初始化注册表"""
        self._configs: Dict[str, ModelConfig] = {}
        self._defaults: Dict[ModelType, str] = {}
    
    def register(self, config: ModelConfig) -> None:
        """注册模型配置
        
        Args:
            config: 模型配置
        """
        self._configs[config.id] = config
        if config.is_default:
            self._defaults[config.model_type] = config.id
        logger.debug(f"注册模型配置: {config.id}")
    
    def get(self, model_id: str) -> Optional[ModelConfig]:
        """获取模型配置
        
        Args:
            model_id: 模型 ID
            
        Returns:
            模型配置，不存在返回 None
        """
        return self._configs.get(model_id)
    
    def list(
        self,
        model_type: Optional[ModelType] = None,
        status: Optional[ModelStatus] = None,
        tags: Optional[List[str]] = None,
    ) -> List[ModelConfig]:
        """列出模型配置
        
        Args:
            model_type: 过滤模型类型
            status: 过滤状态
            tags: 过滤标签
            
        Returns:
            符合条件的模型配置列表
        """
        configs = list(self._configs.values())
        
        if model_type:
            configs = [c for c in configs if c.model_type == model_type]
        
        if status:
            configs = [c for c in configs if c.status == status]
        
        if tags:
            configs = [c for c in configs if any(tag in c.tags for tag in tags)]
        
        return configs
    
    def get_default(self, model_type: ModelType) -> Optional[ModelConfig]:
        """获取默认模型
        
        Args:
            model_type: 模型类型
            
        Returns:
            默认模型配置，不存在返回 None
        """
        default_id = self._defaults.get(model_type)
        return self._configs.get(default_id) if default_id else None
    
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
        
        self._defaults[config.model_type] = model_id
        config.is_default = True
        logger.info(f"设置默认 {config.model_type.value} 模型: {model_id}")
        return True
    
    def create(self, request: ModelCreateRequest) -> ModelConfig:
        """创建新模型配置
        
        Args:
            request: 创建请求
            
        Returns:
            创建的模型配置
            
        Raises:
            ValueError: 模型已存在
        """
        # 生成唯一 ID
        model_id = f"{request.provider}-{request.model_name}".replace("/", "-").replace(":", "-")
        
        if model_id in self._configs:
            raise ValueError(f"Model {model_id} already exists")
        
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
        
        if request.is_default:
            self._defaults[request.model_type] = model_id
        
        logger.info(f"创建模型配置: {model_id}")
        return config
    
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
        
        logger.info(f"更新模型配置: {model_id}")
        return config
    
    def delete(self, model_id: str) -> bool:
        """删除模型配置
        
        Args:
            model_id: 模型 ID
            
        Returns:
            是否删除成功
        """
        if model_id in self._configs:
            del self._configs[model_id]
            logger.info(f"删除模型配置: {model_id}")
            return True
        return False
    
    def create_from_dict(self, data: Dict) -> ModelConfig:
        """从字典创建模型配置
        
        Args:
            data: 配置字典
            
        Returns:
            创建的模型配置
        """
        # 转换 model_type
        model_type_str = data.get('model_type', 'llm')
        model_type = ModelType.LLM if model_type_str == 'llm' else ModelType.EMBEDDING
        
        # 转换 status
        status_str = data.get('status', 'active')
        status = ModelStatus.ACTIVE if status_str == 'active' else ModelStatus.INACTIVE
        
        # 转换 auth_type
        auth_type_str = data.get('auth_type', 'bearer')
        auth_type_map = {
            'bearer': AuthType.BEARER,
            'apikey': AuthType.API_KEY_HEADER,
            'custom': AuthType.CUSTOM_HEADER,
            'none': AuthType.NONE,
        }
        auth_type = auth_type_map.get(auth_type_str.lower(), AuthType.BEARER)
        
        # 转换 suitable_tasks
        suitable_tasks = []
        for task_str in data.get('suitable_tasks', []):
            try:
                task = TaskType(task_str)
                suitable_tasks.append(task)
            except ValueError:
                logger.warning(f"未知的任务类型: {task_str}")
        
        config = ModelConfig(
            id=data.get('id', f"{data['provider']}-{data['model_name']}"),
            name=data.get('name', data['model_name']),
            model_type=model_type,
            provider=data['provider'],
            api_base=data['api_base'],
            model_name=data['model_name'],
            api_key=data.get('api_key', ''),
            openai_compatible=data.get('openai_compatible', True),
            auth_type=auth_type,
            auth_header=data.get('auth_header', 'Authorization'),
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
        
        if config.is_default:
            self._defaults[model_type] = config.id
        
        logger.debug(f"从字典加载模型配置: {config.id}")
        return config
    
    def get_all_ids(self) -> List[str]:
        """获取所有模型 ID
        
        Returns:
            模型 ID 列表
        """
        return list(self._configs.keys())


__all__ = ["ModelRegistry"]
