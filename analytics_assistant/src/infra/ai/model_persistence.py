# -*- coding: utf-8 -*-
"""
ModelPersistence - 模型配置持久化

职责：将动态添加的模型配置持久化到 SQLite

从 ModelManager 拆分出来，专注于持久化逻辑。
"""
import logging
from typing import Any, Dict, List, Optional

from .models import ModelConfig

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import CacheManager

logger = logging.getLogger(__name__)


class ModelPersistence:
    """模型配置持久化
    
    职责：将动态添加的模型配置持久化到 SQLite
    
    持久化策略：
    - YAML 配置文件中的模型：只读，不持久化
    - 通过 API 动态添加的模型：持久化到 SQLite
    """
    
    NAMESPACE = "model_manager"
    KEY = "dynamic_configs"
    
    def __init__(self):
        """初始化持久化模块"""
        self._cache_manager = None
        self._enabled = False
        self._init_storage()
    
    def _init_storage(self) -> None:
        """初始化存储"""
        try:
            config = get_config()
            ai_config = config.config.get("ai", {}).get("global", {})
            self._enabled = ai_config.get("enable_persistence", False)
            
            if self._enabled:
                self._cache_manager = CacheManager(
                    namespace=self.NAMESPACE,
                    default_ttl=None,  # 永久存储
                    enable_stats=False,
                )
                logger.info("ModelPersistence 存储已初始化")
            else:
                logger.info("ModelPersistence 已禁用")
                
        except Exception as e:
            logger.warning(f"初始化持久化存储失败: {e}")
            self._enabled = False
    
    @property
    def enabled(self) -> bool:
        """是否启用持久化"""
        return self._enabled and self._cache_manager is not None
    
    def enable(self, enable: bool = True) -> None:
        """启用或禁用持久化
        
        Args:
            enable: 是否启用
        """
        if enable and self._cache_manager is None:
            try:
                self._cache_manager = CacheManager(
                    namespace=self.NAMESPACE,
                    default_ttl=None,
                    enable_stats=False,
                )
                self._enabled = True
                logger.info("ModelPersistence 已启用")
            except Exception as e:
                logger.warning(f"启用持久化失败: {e}")
                self._enabled = False
        elif enable:
            self._enabled = True
        else:
            self._enabled = False
        
        logger.info(f"ModelPersistence: {'启用' if self._enabled else '禁用'}")
    
    def save(self, configs: List[ModelConfig]) -> None:
        """保存配置列表
        
        Args:
            configs: 要保存的配置列表
        """
        if not self.enabled:
            return
        
        try:
            data = [self._config_to_dict(c) for c in configs]
            self._cache_manager.set(self.KEY, data)
            logger.debug(f"保存了 {len(data)} 个动态配置")
        except Exception as e:
            logger.warning(f"保存持久化配置失败: {e}")
    
    def load(self) -> List[Dict[str, Any]]:
        """加载配置列表
        
        Returns:
            配置字典列表
        """
        if not self.enabled:
            return []
        
        try:
            data = self._cache_manager.get(self.KEY)
            if data:
                logger.debug(f"加载了 {len(data)} 个持久化配置")
                return data
            return []
        except Exception as e:
            logger.warning(f"加载持久化配置失败: {e}")
            return []
    
    def _config_to_dict(self, config: ModelConfig) -> Dict[str, Any]:
        """将配置转换为字典
        
        Args:
            config: 模型配置
            
        Returns:
            配置字典
        """
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


__all__ = ["ModelPersistence"]
