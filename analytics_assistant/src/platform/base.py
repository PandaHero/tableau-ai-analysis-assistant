# -*- coding: utf-8 -*-
"""平台注册表和工厂。

提供集中的平台适配器注册和获取。
"""

import threading
from typing import Dict, List, Optional, Type

from analytics_assistant.src.core.interfaces import BasePlatformAdapter


class PlatformRegistry:
    """平台适配器注册表。
    
    单例模式，管理平台适配器的注册。
    线程安全：
    - 单例创建使用双重检查锁定
    - _adapters 字典操作使用 RLock 保护
    """
    
    _instance: Optional["PlatformRegistry"] = None
    _instance_lock: threading.Lock = threading.Lock()
    _adapters: Dict[str, Type[BasePlatformAdapter]]
    _adapters_lock: threading.RLock  # 实例级别的锁
    
    def __new__(cls) -> "PlatformRegistry":
        if cls._instance is None:
            with cls._instance_lock:
                # 双重检查锁定，确保线程安全
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._adapters = {}
                    instance._adapters_lock = threading.RLock()
                    cls._instance = instance
        return cls._instance
    
    def register(self, name: str, adapter_class: Type[BasePlatformAdapter]) -> None:
        """注册平台适配器（线程安全）。
        
        Args:
            name: 平台名称（如 "tableau", "powerbi"）
            adapter_class: 实现 BasePlatformAdapter 的适配器类
        """
        with self._adapters_lock:
            self._adapters[name.lower()] = adapter_class
    
    def get(self, name: str, **kwargs) -> BasePlatformAdapter:
        """获取平台适配器实例（线程安全）。
        
        Args:
            name: 平台名称
            **kwargs: 传递给适配器构造函数的参数
            
        Returns:
            平台适配器实例
            
        Raises:
            ValueError: 平台未注册
        """
        name_lower = name.lower()
        with self._adapters_lock:
            if name_lower not in self._adapters:
                available = ", ".join(self._adapters.keys()) or "无"
                raise ValueError(f"平台 '{name}' 未注册。可用平台: {available}")
            adapter_class = self._adapters[name_lower]
        # 在锁外创建实例，避免长时间持有锁
        return adapter_class(**kwargs)
    
    def list_platforms(self) -> List[str]:
        """列出所有已注册的平台名称（线程安全）。"""
        with self._adapters_lock:
            return list(self._adapters.keys())
    
    def is_registered(self, name: str) -> bool:
        """检查平台是否已注册（线程安全）。"""
        with self._adapters_lock:
            return name.lower() in self._adapters


# 模块级便捷函数
_registry = PlatformRegistry()


def register_adapter(name: str, adapter_class: Type[BasePlatformAdapter]) -> None:
    """注册平台适配器。"""
    _registry.register(name, adapter_class)


def get_adapter(name: str, **kwargs) -> BasePlatformAdapter:
    """获取平台适配器实例。"""
    return _registry.get(name, **kwargs)
