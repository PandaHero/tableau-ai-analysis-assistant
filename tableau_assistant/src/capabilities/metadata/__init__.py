"""
元数据管理能力

提供 Tableau 数据源元数据的获取、缓存和增强功能。

主要组件：
- MetadataManager: 元数据管理器，负责获取、缓存和增强元数据
- ApplicationLevelCacheMiddleware: 应用级缓存中间件

使用示例：
    from tableau_assistant.src.capabilities.metadata import MetadataManager
    
    manager = MetadataManager(runtime)
    metadata = await manager.get_metadata_async()
"""
from tableau_assistant.src.capabilities.metadata.manager import MetadataManager
from tableau_assistant.src.capabilities.metadata.application_cache import ApplicationLevelCacheMiddleware

__all__ = [
    "MetadataManager",
    "ApplicationLevelCacheMiddleware",
]
