# -*- coding: utf-8 -*-
"""平台注册表和工厂。

提供集中的平台适配器注册和获取。
"""

from typing import Type

from analytics_assistant.src.core.interfaces import BasePlatformAdapter


class PlatformRegistry:
    """平台适配器注册表。
    
    单例模式，管理平台适配器的注册。
    """
    
    _instance: "PlatformRegistry | None" = None
    _adapters: dict[str, Type[BasePlatformAdapter]]
    
    def __new__(cls) -> "PlatformRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters = {}
        return cls._instance
    
    def register(self, name: str, adapter_class: Type[BasePlatformAdapter]) -> None:
        """注册平台适配器。
        
        Args:
            name: 平台名称（如 "tableau", "powerbi"）
            adapter_class: 实现 BasePlatformAdapter 的适配器类
        """
        self._adapters[name.lower()] = adapter_class
    
    def get(self, name: str, **kwargs) -> BasePlatformAdapter:
        """获取平台适配器实例。
        
        Args:
            name: 平台名称
            **kwargs: 传递给适配器构造函数的参数
            
        Returns:
            平台适配器实例
            
        Raises:
            ValueError: 平台未注册
        """
        name_lower = name.lower()
        if name_lower not in self._adapters:
            available = ", ".join(self._adapters.keys()) or "无"
            raise ValueError(f"平台 '{name}' 未注册。可用平台: {available}")
        return self._adapters[name_lower](**kwargs)
    
    def list_platforms(self) -> list[str]:
        """列出所有已注册的平台名称。"""
        return list(self._adapters.keys())
    
    def is_registered(self, name: str) -> bool:
        """检查平台是否已注册。"""
        return name.lower() in self._adapters


# 模块级便捷函数
_registry = PlatformRegistry()


def register_adapter(name: str, adapter_class: Type[BasePlatformAdapter]) -> None:
    """注册平台适配器。"""
    _registry.register(name, adapter_class)


def get_adapter(name: str, **kwargs) -> BasePlatformAdapter:
    """获取平台适配器实例。"""
    return _registry.get(name, **kwargs)
