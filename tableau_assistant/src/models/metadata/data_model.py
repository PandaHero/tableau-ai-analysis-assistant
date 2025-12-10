"""
数据模型定义

定义 Tableau 数据源的逻辑表和关系模型。
来自 VizQL /get-datasource-model API。

Usage:
    from tableau_assistant.src.models.metadata.data_model import DataModel, LogicalTable, LogicalTableRelationship
    
    data_model = DataModel(
        logicalTables=[LogicalTable(logicalTableId="t1", caption="订单表")],
        logicalTableRelationships=[]
    )
    caption = data_model.get_table_caption("t1")  # "订单表"
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class LogicalTable:
    """
    逻辑表
    
    Attributes:
        logicalTableId: 逻辑表唯一标识符
        caption: 逻辑表显示名称
    """
    logicalTableId: str
    caption: str


@dataclass
class LogicalTableRelationship:
    """
    逻辑表关系
    
    Attributes:
        fromLogicalTableId: 源逻辑表 ID
        toLogicalTableId: 目标逻辑表 ID
    """
    fromLogicalTableId: str
    toLogicalTableId: str


@dataclass
class DataModel:
    """
    数据模型
    
    包含数据源的所有逻辑表和它们之间的关系。
    来自 VizQL /get-datasource-model API。
    
    Attributes:
        logicalTables: 逻辑表列表
        logicalTableRelationships: 逻辑表关系列表
    """
    logicalTables: List[LogicalTable]
    logicalTableRelationships: List[LogicalTableRelationship]
    
    def get_table_caption(self, table_id: str) -> Optional[str]:
        """
        通过逻辑表 ID 获取表名
        
        Args:
            table_id: 逻辑表 ID
            
        Returns:
            逻辑表名称，未找到返回 None
        """
        for table in self.logicalTables:
            if table.logicalTableId == table_id:
                return table.caption
        return None
    
    def get_table_by_id(self, table_id: str) -> Optional[LogicalTable]:
        """
        通过逻辑表 ID 获取逻辑表对象
        
        Args:
            table_id: 逻辑表 ID
            
        Returns:
            LogicalTable 对象，未找到返回 None
        """
        for table in self.logicalTables:
            if table.logicalTableId == table_id:
                return table
        return None
    
    def get_related_tables(self, table_id: str) -> List[LogicalTable]:
        """
        获取与指定表有关系的所有表
        
        Args:
            table_id: 逻辑表 ID
            
        Returns:
            相关逻辑表列表
        """
        related_ids = set()
        for rel in self.logicalTableRelationships:
            if rel.fromLogicalTableId == table_id:
                related_ids.add(rel.toLogicalTableId)
            elif rel.toLogicalTableId == table_id:
                related_ids.add(rel.fromLogicalTableId)
        
        return [t for t in self.logicalTables if t.logicalTableId in related_ids]


__all__ = [
    "LogicalTable",
    "LogicalTableRelationship",
    "DataModel",
]
