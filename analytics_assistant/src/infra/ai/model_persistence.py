# -*- coding: utf-8 -*-
"""
ModelPersistence - 模型配置持久化

职责：将动态添加的模型配置持久化到 SQLite

从 ModelManager 拆分出来，专注于持久化逻辑。
API Key 使用 Fernet 对称加密后存储，密钥从环境变量读取。
"""
import logging
import os
from enum import Enum
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

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
    - API Key 使用 Fernet 对称加密后存储
    """
    
    NAMESPACE = "model_manager"
    KEY = "dynamic_configs"
    
    def __init__(self):
        """初始化持久化模块"""
        self._cache_manager = None
        self._enabled = False
        self._fernet = self._init_fernet()
        self._init_storage()
    
    def _init_fernet(self) -> Optional[Fernet]:
        """初始化 Fernet 加密器
        
        从环境变量 ANALYTICS_ASSISTANT_ENCRYPTION_KEY 读取密钥。
        密钥不可用时返回 None，回退到环境变量引用模式。
        
        Returns:
            Fernet 实例，或密钥不可用时返回 None
        """
        key = os.environ.get("ANALYTICS_ASSISTANT_ENCRYPTION_KEY")
        if key:
            try:
                return Fernet(key.encode() if isinstance(key, str) else key)
            except Exception as e:
                logger.warning(
                    f"加密密钥格式无效，API Key 将使用环境变量引用模式存储: {type(e).__name__}"
                )
                return None
        logger.warning("加密密钥不可用，API Key 将使用环境变量引用模式存储")
        return None

    def _encrypt_api_key(self, api_key: str) -> str:
        """加密 API Key
        
        使用 Fernet 对称加密，加密后格式为 "ENC:<密文>"。
        已加密或环境变量引用格式的值不会重复加密。
        
        Args:
            api_key: 原始 API Key
            
        Returns:
            加密后的字符串，或原始值（加密器不可用时）
        """
        if self._fernet and api_key and not api_key.startswith("${"):
            try:
                encrypted = self._fernet.encrypt(api_key.encode()).decode()
                return f"ENC:{encrypted}"
            except Exception as e:
                logger.error(
                    f"API Key 加密失败，返回原始值: {type(e).__name__}"
                )
                return api_key
        return api_key

    def _decrypt_api_key(self, stored_value: str) -> str:
        """解密 API Key
        
        识别 "ENC:" 前缀的加密值并解密。
        非加密格式的值直接返回。
        
        Args:
            stored_value: 存储的值（可能是加密的或明文的）
            
        Returns:
            解密后的 API Key，或原始值（非加密格式时）
        """
        if self._fernet and stored_value.startswith("ENC:"):
            try:
                return self._fernet.decrypt(stored_value[4:].encode()).decode()
            except InvalidToken as e:
                logger.error(
                    f"API Key 解密失败（密钥可能已变更），返回原始值: {type(e).__name__}"
                )
                return stored_value
            except Exception as e:
                logger.error(
                    f"API Key 解密异常，返回原始值: {type(e).__name__}"
                )
                return stored_value
        return stored_value

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
    
    def save(self, configs: list[ModelConfig]) -> None:
        """保存配置列表
        
        使用 model_dump() 序列化，并对 api_key 进行加密。
        
        Args:
            configs: 要保存的配置列表
        """
        if not self.enabled:
            return
        
        try:
            data = []
            for config in configs:
                config_dict = config.model_dump(mode="python")
                # 加密 api_key
                if config_dict.get("api_key"):
                    config_dict["api_key"] = self._encrypt_api_key(
                        config_dict["api_key"]
                    )
                # 枚举值转字符串，确保可序列化
                for key, val in config_dict.items():
                    if isinstance(val, Enum):
                        config_dict[key] = val.value
                    elif isinstance(val, list):
                        config_dict[key] = [
                            item.value if isinstance(item, Enum) else item
                            for item in val
                        ]
                data.append(config_dict)
            self._cache_manager.set(self.KEY, data)
            logger.debug(f"保存了 {len(data)} 个动态配置")
        except Exception as e:
            logger.warning(f"保存持久化配置失败: {e}")
    
    def load(self) -> list[dict[str, Any]]:
        """加载配置列表
        
        加载后自动解密 api_key 字段。
        
        Returns:
            配置字典列表
        """
        if not self.enabled:
            return []
        
        try:
            data = self._cache_manager.get(self.KEY)
            if data:
                # 解密每个配置中的 api_key
                for config_dict in data:
                    if config_dict.get("api_key"):
                        config_dict["api_key"] = self._decrypt_api_key(
                            config_dict["api_key"]
                        )
                logger.debug(f"加载了 {len(data)} 个持久化配置")
                return data
            return []
        except Exception as e:
            logger.warning(f"加载持久化配置失败: {e}")
            return []

__all__ = ["ModelPersistence"]
