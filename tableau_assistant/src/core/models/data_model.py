"""
数据模型定义

定义 Tableau 数据源的完整数据模型，包含：
- 字段元数据（FieldMetadata）
- 逻辑表（LogicalTable）
- 表关系（LogicalTableRelationship）
- 数据模型（DataModel）

数据模型是最高层次的抽象，包含了数据源的完整结构信息。

来自 VizQL API:
- /read-metadata → 字段元数据
- /get-datasource-model → 逻辑表和关系
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Literal


class FieldMetadata(BaseModel):
    """
    字段元数据模型
    
    描述单个字段的详细信息，包括基本属性、统计信息、维度层级推断结果等。
    
    支持两种数据来源：
    1. GraphQL API：使用 name, role, dataType, aggregation 等字段
    2. VizQL API：使用 fieldName, fieldCaption, columnClass, logicalTableId 等字段
    """
    
    # 基本信息
    name: str = Field(..., description="字段名称")
    fieldCaption: str = Field(..., description="字段显示名称")
    role: Literal["dimension", "measure"] = Field(..., description="字段角色")
    dataType: str = Field(..., description="数据类型：DATE/DATETIME/STRING/INTEGER/REAL等")
    
    # 可选信息
    dataCategory: Optional[str] = Field(None, description="数据类别")
    aggregation: Optional[str] = Field(None, description="聚合方式")
    formula: Optional[str] = Field(None, description="计算公式")
    description: Optional[str] = Field(None, description="字段描述")
    
    # VizQL API 字段
    fieldName: Optional[str] = Field(None, description="底层数据库列名")
    columnClass: Optional[str] = Field(None, description="字段类型：COLUMN/BIN/GROUP/CALCULATION/TABLE_CALCULATION")
    logicalTableId: Optional[str] = Field(None, description="所属逻辑表ID")
    logicalTableCaption: Optional[str] = Field(None, description="所属逻辑表名称")
    
    # 统计信息
    sample_values: Optional[List[str]] = Field(None, description="样本值")
    unique_count: Optional[int] = Field(None, description="唯一值数量")
    
    # 维度层级推断结果（由 dimension_hierarchy_agent 添加）
    category: Optional[str] = Field(None, description="维度类别（地理/时间/产品/客户/组织/财务/其他）")
    category_detail: Optional[str] = Field(None, description="详细类别描述")
    level: Optional[int] = Field(None, description="层级级别（1-5）")
    granularity: Optional[str] = Field(None, description="粒度描述")
    parent_dimension: Optional[str] = Field(None, description="父维度字段名")
    child_dimension: Optional[str] = Field(None, description="子维度字段名")
    
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
        """从 VizQL API 响应创建 FieldMetadata"""
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
    """逻辑表"""
    logicalTableId: str = Field(..., description="逻辑表唯一标识符")
    caption: str = Field(..., description="逻辑表显示名称")
    
    model_config = ConfigDict(frozen=False)


class LogicalTableRelationship(BaseModel):
    """逻辑表关系"""
    fromLogicalTableId: str = Field(..., description="源逻辑表 ID")
    toLogicalTableId: str = Field(..., description="目标逻辑表 ID")
    
    model_config = ConfigDict(frozen=False)


class DataModel(BaseModel):
    """
    数据模型
    
    数据源的完整数据模型，是最高层次的抽象。
    包含数据源的所有结构信息：逻辑表、表关系、字段元数据。
    """
    # 数据源基本信息
    datasource_luid: str = Field(..., description="数据源 LUID")
    datasource_name: str = Field(..., description="数据源名称")
    datasource_description: Optional[str] = Field(None, description="数据源描述")
    datasource_owner: Optional[str] = Field(None, description="数据源所有者")
    
    # 逻辑表结构（可选，单表场景可能没有）
    logical_tables: List[LogicalTable] = Field(default_factory=list, description="逻辑表列表")
    logical_table_relationships: List[LogicalTableRelationship] = Field(default_factory=list, description="逻辑表关系列表")
    
    # 字段元数据（必需）
    fields: List[FieldMetadata] = Field(..., description="字段元数据列表")
    field_count: int = Field(..., description="字段数量")
    
    # 维度层级（可选，由 LLM 推断）
    dimension_hierarchy: Optional[Dict[str, Any]] = Field(None, description="维度层级推断结果")
    
    # 原始响应（调试用）
    raw_response: Optional[Dict[str, Any]] = Field(None, description="原始 API 响应")
    
    model_config = ConfigDict(frozen=False, extra="allow")
    
    @property
    def has_logical_tables(self) -> bool:
        """是否有逻辑表结构"""
        return len(self.logical_tables) > 0
    
    @property
    def is_multi_table(self) -> bool:
        """是否是多表数据源"""
        return len(self.logical_tables) > 1
    
    def get_table_caption(self, table_id: str) -> Optional[str]:
        """通过逻辑表 ID 获取表名"""
        for table in self.logical_tables:
            if table.logicalTableId == table_id:
                return table.caption
        return None
    
    def get_table_by_id(self, table_id: str) -> Optional[LogicalTable]:
        """通过逻辑表 ID 获取逻辑表对象"""
        for table in self.logical_tables:
            if table.logicalTableId == table_id:
                return table
        return None
    
    def get_related_tables(self, table_id: str) -> List[LogicalTable]:
        """获取与指定表有关系的所有表"""
        related_ids = set()
        for rel in self.logical_table_relationships:
            if rel.fromLogicalTableId == table_id:
                related_ids.add(rel.toLogicalTableId)
            elif rel.toLogicalTableId == table_id:
                related_ids.add(rel.fromLogicalTableId)
        return [t for t in self.logical_tables if t.logicalTableId in related_ids]
    
    def get_field(self, field_name: str) -> Optional[FieldMetadata]:
        """根据字段名查询字段元数据"""
        for field in self.fields:
            if field.name == field_name or field.fieldCaption == field_name:
                return field
        return None
    
    def get_date_fields(self) -> List[FieldMetadata]:
        """获取所有日期字段"""
        date_fields = []
        for field in self.fields:
            if field.dataType in ("DATE", "DATETIME"):
                date_fields.append(field)
            elif field.category and "时间" in field.category:
                date_fields.append(field)
        return date_fields
    
    def get_dimensions(self) -> List[FieldMetadata]:
        """获取所有维度字段"""
        return [field for field in self.fields if field.role == "dimension"]
    
    def get_measures(self) -> List[FieldMetadata]:
        """获取所有度量字段"""
        return [field for field in self.fields if field.role == "measure"]
    
    def get_fields_by_table(self, table_id: str) -> List[FieldMetadata]:
        """获取指定逻辑表的所有字段"""
        return [field for field in self.fields if field.logicalTableId == table_id]


__all__ = [
    "FieldMetadata",
    "LogicalTable",
    "LogicalTableRelationship",
    "DataModel",
]
