"""
6个纯代码组件

包含：
1. MetadataManager - 元数据管理器
2. QueryBuilder - 查询构建器（纯代码规则，参考tableau_sdk）
3. QueryExecutor - 查询执行器
4. StatisticsDetector - 统计检测器
5. DataMerger - 数据合并器
6. TaskScheduler - 任务调度器
"""

from .metadata_manager import MetadataManager
from .store_manager import StoreManager

__all__ = [
    "MetadataManager",
    "StoreManager",
]
