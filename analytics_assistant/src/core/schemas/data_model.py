# -*- coding: utf-8 -*-
"""数据模型定义。

定义 Tableau 数据源的完整数据模型，包括：
- Field: 字段元数据
- LogicalTable: 逻辑表
- TableRelationship: 表关系
- DataModel: 数据模型
"""
import hashlib

from pydantic import BaseModel, Field as PydanticField, ConfigDict, PrivateAttr
from typing import Any, Optional

class Field(BaseModel):
    """字段元数据模型。
    
    描述单个字段的详细信息。
    """
    model_config = ConfigDict(extra="allow")
    
    # 基本信息
    name: str = PydanticField(..., description="字段名称")
    caption: str = PydanticField(..., description="字段显示名称")
    data_type: str = PydanticField(default="STRING", description="数据类型")
    role: str = PydanticField(default="DIMENSION", description="字段角色: DIMENSION/MEASURE")
    
    # 可选信息
    data_category: Optional[str] = PydanticField(default=None, description="数据类别")
    aggregation: Optional[str] = PydanticField(default=None, description="聚合方式")
    description: Optional[str] = PydanticField(default=None, description="字段描述")
    folder: Optional[str] = PydanticField(default=None, description="文件夹")
    hidden: bool = PydanticField(default=False, description="是否隐藏")
    calculation: Optional[str] = PydanticField(default=None, description="计算公式")
    upstream_tables: Optional[list[dict[str, str]]] = PydanticField(default=None, description="上游表信息")
    
    # 维度层级推断结果
    category: Optional[str] = PydanticField(default=None, description="维度类别")
    level: Optional[int] = PydanticField(default=None, description="层级级别")
    granularity: Optional[str] = PydanticField(default=None, description="粒度描述")
    
    # 可查询性标志（GraphQL 返回但 VizQL 查询失败的"幽灵字段"标记为 False）
    queryable: bool = PydanticField(default=True, description="是否可通过 VizQL 查询")
    
    @property
    def is_dimension(self) -> bool:
        """是否为维度字段。"""
        return self.role.upper() == "DIMENSION"
    
    @property
    def is_measure(self) -> bool:
        """是否为度量字段。"""
        return self.role.upper() == "MEASURE"

class LogicalTable(BaseModel):
    """逻辑表。"""
    model_config = ConfigDict(extra="allow")
    
    id: str = PydanticField(..., description="逻辑表唯一标识")
    name: str = PydanticField(..., description="逻辑表显示名称")
    field_count: int = PydanticField(default=0, description="字段数量")

class TableRelationship(BaseModel):
    """表关系。"""
    model_config = ConfigDict(extra="allow")
    
    from_table_id: str = PydanticField(..., description="源表 ID")
    from_table_name: Optional[str] = PydanticField(default=None, description="源表名称")
    to_table_id: str = PydanticField(..., description="目标表 ID")
    to_table_name: Optional[str] = PydanticField(default=None, description="目标表名称")
    join_conditions: list[dict[str, str]] = PydanticField(default_factory=list, description="关联条件")

class DataModel(BaseModel):
    """数据模型。
    
    数据源的完整数据模型，最高层抽象。
    包含所有结构信息：逻辑表、关系、字段元数据。
    """
    model_config = ConfigDict(extra="allow")
    
    # 数据源基本信息
    datasource_id: str = PydanticField(..., description="数据源 LUID")
    datasource_name: Optional[str] = PydanticField(default=None, description="数据源名称")
    datasource_description: Optional[str] = PydanticField(default=None, description="数据源描述")
    datasource_owner: Optional[str] = PydanticField(default=None, description="数据源所有者")
    
    # 逻辑表结构
    tables: list[LogicalTable] = PydanticField(default_factory=list, description="逻辑表列表")
    relationships: list[TableRelationship] = PydanticField(default_factory=list, description="表关系列表")
    
    # 字段元数据
    fields: list[Field] = PydanticField(default_factory=list, description="字段元数据列表")
    
    # 原始响应
    raw_metadata: Optional[dict[str, Any]] = PydanticField(default=None, description="原始 API 响应")
    
    # 缓存的 schema_hash（延迟计算）
    _cached_schema_hash: Optional[str] = PrivateAttr(default=None)
    
    @property
    def schema_hash(self) -> str:
        """计算数据模型的 schema hash。
        
        只包含影响查询生成的字段属性：
        - field.name: 字段名
        - field.data_type: 数据类型
        - field.role: 字段角色 (DIMENSION/MEASURE)
        
        不包含：
        - field.description: 描述变更不影响查询
        - field.caption: 显示名变更不影响查询
        
        结果会被缓存，避免重复计算。
        """
        if self._cached_schema_hash is None:
            if not self.fields:
                self._cached_schema_hash = hashlib.md5(b"empty").hexdigest()
            else:
                field_signatures = []
                for field in self.fields:
                    field_signatures.append(
                        f"{field.name}:{field.data_type}:{field.role}"
                    )
                field_signatures.sort()
                content = "|".join(field_signatures)
                self._cached_schema_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
        
        return self._cached_schema_hash
    
    @property
    def field_count(self) -> int:
        """字段数量。"""
        return len(self.fields)
    
    @property
    def has_tables(self) -> bool:
        """是否有逻辑表结构。"""
        return len(self.tables) > 0
    
    @property
    def is_multi_table(self) -> bool:
        """是否为多表数据源。"""
        return len(self.tables) > 1
    
    @property
    def dimensions(self) -> list[Field]:
        """获取所有维度字段。"""
        return [f for f in self.fields if f.is_dimension]
    
    @property
    def measures(self) -> list[Field]:
        """获取所有度量字段。"""
        return [f for f in self.fields if f.is_measure]
    
    def get_field(self, name: str) -> Optional[Field]:
        """根据名称获取字段。"""
        for field in self.fields:
            if field.name == name or field.caption == name:
                return field
        return None

__all__ = [
    "Field",
    "LogicalTable",
    "TableRelationship",
    "DataModel",
]
