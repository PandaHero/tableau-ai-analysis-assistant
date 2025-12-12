"""
Metadata Models Package

Contains metadata-related models:
- FieldMetadata, Metadata
- LogicalTable, DataModel
- DimensionHierarchyResult
"""

from tableau_assistant.src.models.metadata.metadata import (
    FieldMetadata,
    Metadata,
)

from tableau_assistant.src.models.metadata.data_model import (
    LogicalTable,
    LogicalTableRelationship,
    DataModel,
)

from tableau_assistant.src.models.metadata.dimension_hierarchy import (
    DimensionHierarchyResult,
    DimensionAttributes,
)

# 解析前向引用（Metadata 引用了 DataModel）
# 必须在所有模型导入后调用
Metadata.model_rebuild()

__all__ = [
    # Metadata
    "FieldMetadata",
    "Metadata",
    # Data Model
    "LogicalTable",
    "LogicalTableRelationship",
    "DataModel",
    # Dimension Hierarchy
    "DimensionHierarchyResult",
    "DimensionAttributes",
]
