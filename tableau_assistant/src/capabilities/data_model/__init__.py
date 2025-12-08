"""
数据模型管理能力

提供 Tableau 数据源数据模型的获取、缓存和增强功能。

数据模型包含：
- 字段元数据（FieldMetadata）
- 逻辑表（LogicalTable）
- 表关系（LogicalTableRelationship）
- 维度层级（DimensionHierarchy）

主要组件：
- DataModelManager: 数据模型管理器，负责获取、缓存和增强数据模型

使用示例：
    from tableau_assistant.src.capabilities.data_model import DataModelManager
    
    manager = DataModelManager(runtime)
    data_model = await manager.get_data_model_async()
"""
from tableau_assistant.src.capabilities.data_model.manager import DataModelManager

__all__ = [
    "DataModelManager",
]
