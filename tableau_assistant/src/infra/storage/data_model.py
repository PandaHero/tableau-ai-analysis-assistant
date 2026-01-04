# -*- coding: utf-8 -*-
"""Data Model Definitions.

Defines the complete data model for Tableau data sources, including:
- FieldMetadata: Field metadata
- LogicalTable: Logical table
- LogicalTableRelationship: Table relationship
- DataModel: Data model

DataModel is the highest level abstraction containing complete structure information.

From VizQL API:
- /read-metadata -> Field metadata
- /get-datasource-model -> Logical tables and relationships

Note: Migrated from core/models/data_model.py per design document.
This is platform-specific metadata, not a platform-agnostic abstraction.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Literal


class FieldMetadata(BaseModel):
    """Field metadata model.
    
    Describes detailed information for a single field, including basic attributes,
    statistics, and dimension hierarchy inference results.
    
    Supports two data sources:
    1. GraphQL API: Uses name, role, dataType, aggregation etc.
    2. VizQL API: Uses fieldName, fieldCaption, columnClass, logicalTableId etc.
    """
    
    # Basic info
    name: str = Field(..., description="Field name")
    fieldCaption: str = Field(..., description="Field display name")
    role: Literal["dimension", "measure"] = Field(..., description="Field role")
    dataType: str = Field(..., description="Data type: DATE/DATETIME/STRING/INTEGER/REAL etc.")
    
    # Optional info
    dataCategory: Optional[str] = Field(None, description="Data category")
    aggregation: Optional[str] = Field(None, description="Aggregation method")
    formula: Optional[str] = Field(None, description="Calculation formula")
    description: Optional[str] = Field(None, description="Field description")
    
    # VizQL API fields
    fieldName: Optional[str] = Field(None, description="Underlying database column name")
    columnClass: Optional[str] = Field(None, description="Field type: COLUMN/BIN/GROUP/CALCULATION/TABLE_CALCULATION")
    logicalTableId: Optional[str] = Field(None, description="Logical table ID")
    logicalTableCaption: Optional[str] = Field(None, description="Logical table name")
    
    # Statistics
    sample_values: Optional[List[str]] = Field(None, description="Sample values")
    unique_count: Optional[int] = Field(None, description="Unique value count")
    
    # Dimension hierarchy inference results (added by dimension_hierarchy_agent)
    category: Optional[str] = Field(None, description="Dimension category (geography/time/product/customer/organization/financial/other)")
    category_detail: Optional[str] = Field(None, description="Detailed category description")
    level: Optional[int] = Field(None, description="Hierarchy level (1-5)")
    granularity: Optional[str] = Field(None, description="Granularity description")
    parent_dimension: Optional[str] = Field(None, description="Parent dimension field name")
    child_dimension: Optional[str] = Field(None, description="Child dimension field name")
    
    model_config = ConfigDict(frozen=False, extra="allow")
    
    @classmethod
    def from_vizql(
        cls,
        field_name: str,
        field_caption: str,
        data_type: str,
        role: Literal["dimension", "measure"],
        default_aggregation: Optional[str] = None,
        column_class: Optional[str] = None,
        formula: Optional[str] = None,
        logical_table_id: Optional[str] = None,
        logical_table_caption: Optional[str] = None,
        **kwargs
    ) -> "FieldMetadata":
        """Create FieldMetadata from VizQL API response."""
        return cls(
            name=field_name,
            fieldCaption=field_caption,
            dataType=data_type,
            role=role,
            aggregation=default_aggregation,
            fieldName=field_name,
            columnClass=column_class,
            formula=formula,
            logicalTableId=logical_table_id,
            logicalTableCaption=logical_table_caption,
            **kwargs
        )


class LogicalTable(BaseModel):
    """Logical table."""
    logicalTableId: str = Field(..., description="Logical table unique identifier")
    caption: str = Field(..., description="Logical table display name")
    
    model_config = ConfigDict(frozen=False)


class LogicalTableRelationship(BaseModel):
    """Logical table relationship."""
    fromLogicalTableId: str = Field(..., description="Source logical table ID")
    toLogicalTableId: str = Field(..., description="Target logical table ID")
    
    model_config = ConfigDict(frozen=False)


class DataModel(BaseModel):
    """Data model.
    
    Complete data model for a data source, the highest level abstraction.
    Contains all structure information: logical tables, relationships, field metadata.
    """
    # Data source basic info
    datasource_luid: str = Field(..., description="Data source LUID")
    datasource_name: str = Field(..., description="Data source name")
    datasource_description: Optional[str] = Field(None, description="Data source description")
    datasource_owner: Optional[str] = Field(None, description="Data source owner")
    
    # Logical table structure (optional, single table scenario may not have)
    logical_tables: List[LogicalTable] = Field(default_factory=list, description="Logical table list")
    logical_table_relationships: List[LogicalTableRelationship] = Field(default_factory=list, description="Logical table relationship list")
    
    # Field metadata (required)
    fields: List[FieldMetadata] = Field(..., description="Field metadata list")
    field_count: int = Field(..., description="Field count")
    
    # Dimension hierarchy (optional, inferred by LLM)
    dimension_hierarchy: Optional[Dict[str, Any]] = Field(None, description="Dimension hierarchy inference result")
    
    # Raw response (for debugging)
    raw_response: Optional[Dict[str, Any]] = Field(None, description="Raw API response")
    
    model_config = ConfigDict(frozen=False, extra="allow")
    
    @property
    def has_logical_tables(self) -> bool:
        """Whether has logical table structure."""
        return len(self.logical_tables) > 0
    
    @property
    def is_multi_table(self) -> bool:
        """Whether is multi-table data source."""
        return len(self.logical_tables) > 1
    
    def get_table_caption(self, table_id: str) -> Optional[str]:
        """Get table name by logical table ID."""
        for table in self.logical_tables:
            if table.logicalTableId == table_id:
                return table.caption
        return None
    
    def get_table_by_id(self, table_id: str) -> Optional[LogicalTable]:
        """Get logical table object by ID."""
        for table in self.logical_tables:
            if table.logicalTableId == table_id:
                return table
        return None
    
    def get_related_tables(self, table_id: str) -> List[LogicalTable]:
        """Get all tables related to the specified table."""
        related_ids = set()
        for rel in self.logical_table_relationships:
            if rel.fromLogicalTableId == table_id:
                related_ids.add(rel.toLogicalTableId)
            elif rel.toLogicalTableId == table_id:
                related_ids.add(rel.fromLogicalTableId)
        return [t for t in self.logical_tables if t.logicalTableId in related_ids]
    
    def get_field(self, field_name: str) -> Optional[FieldMetadata]:
        """Get field metadata by field name."""
        for field in self.fields:
            if field.name == field_name or field.fieldCaption == field_name:
                return field
        return None
    
    def get_date_fields(self) -> List[FieldMetadata]:
        """Get all date fields."""
        date_fields = []
        for field in self.fields:
            if field.dataType in ("DATE", "DATETIME"):
                date_fields.append(field)
            elif field.category and "time" in field.category.lower():
                date_fields.append(field)
        return date_fields
    
    def get_dimensions(self) -> List[FieldMetadata]:
        """Get all dimension fields."""
        return [field for field in self.fields if field.role == "dimension"]
    
    def get_measures(self) -> List[FieldMetadata]:
        """Get all measure fields."""
        return [field for field in self.fields if field.role == "measure"]
    
    def get_fields_by_table(self, table_id: str) -> List[FieldMetadata]:
        """Get all fields for a specific logical table."""
        return [field for field in self.fields if field.logicalTableId == table_id]


__all__ = [
    "FieldMetadata",
    "LogicalTable",
    "LogicalTableRelationship",
    "DataModel",
]
