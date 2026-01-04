# -*- coding: utf-8 -*-
"""
Tableau 数据模型加载器

从 Tableau API 加载数据模型，并使用 LLM Agent 推断维度层级。

使用示例:
    from tableau_assistant.src.platforms.tableau import TableauDataModelLoader
    
    loader = TableauDataModelLoader(auth_ctx)
    data_model = await loader.load_data_model(datasource_luid)
    hierarchy = await loader.infer_dimension_hierarchy(data_model)
"""
import logging
import time
from typing import Dict, Any

from tableau_assistant.src.infra.storage.data_model_loader import DataModelLoader
from tableau_assistant.src.infra.storage.data_model import DataModel
from tableau_assistant.src.platforms.tableau.auth import TableauAuthContext

logger = logging.getLogger(__name__)


class TableauDataModelLoader(DataModelLoader):
    """
    Tableau 数据模型加载器实现
    
    从 Tableau API 加载数据模型，并使用 LLM Agent 推断维度层级。
    支持单表和多表数据源。
    """
    
    def __init__(self, auth_ctx: TableauAuthContext):
        """
        初始化加载器
        
        Args:
            auth_ctx: Tableau 认证上下文
        """
        self._auth = auth_ctx
    
    async def load_data_model(self, datasource_luid: str) -> DataModel:
        """
        从 Tableau API 加载数据模型
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            DataModel 对象
        """
        from tableau_assistant.src.platforms.tableau.data_model import get_datasource_metadata
        from tableau_assistant.src.infra.storage.data_model import (
            FieldMetadata,
            LogicalTable,
            LogicalTableRelationship,
        )
        
        start_time = time.time()
        
        # 调用 Tableau API
        raw = await get_datasource_metadata(
            datasource_luid=datasource_luid,
            tableau_token=self._auth.api_key,
            tableau_site=self._auth.site,
            tableau_domain=self._auth.domain,
        )
        
        # 转换字段
        fields = [FieldMetadata(**f) for f in raw.get("fields", [])]

        # 解析逻辑表结构（支持单表和多表场景）
        logical_tables = []
        logical_table_relationships = []
        raw_data_model = raw.get("data_model")
        
        if raw_data_model:
            if hasattr(raw_data_model, 'logicalTables'):
                # 已经是对象形式
                logical_tables = raw_data_model.logicalTables
                logical_table_relationships = raw_data_model.logicalTableRelationships
            elif isinstance(raw_data_model, dict):
                # 字典形式，需要转换
                for t in raw_data_model.get("logicalTables", []):
                    logical_tables.append(LogicalTable(
                        logicalTableId=t.get("logicalTableId", ""),
                        caption=t.get("caption", "")
                    ))
                for r in raw_data_model.get("logicalTableRelationships", []):
                    logical_table_relationships.append(LogicalTableRelationship(
                        fromLogicalTableId=r.get("fromLogicalTableId", ""),
                        toLogicalTableId=r.get("toLogicalTableId", "")
                    ))
        
        data_model = DataModel(
            datasource_luid=datasource_luid,
            datasource_name=raw.get("datasource_name", "Unknown"),
            datasource_description=raw.get("datasource_description"),
            datasource_owner=raw.get("datasource_owner"),
            logical_tables=logical_tables,
            logical_table_relationships=logical_table_relationships,
            fields=fields,
            field_count=len(fields),
            raw_response=raw.get("raw_response"),
        )
        
        duration = (time.time() - start_time) * 1000
        logger.info(
            f"数据模型加载完成: {datasource_luid}, "
            f"{len(fields)} 个字段, "
            f"{len(logical_tables)} 个逻辑表, "
            f"耗时: {duration:.1f}ms"
        )
        
        return data_model
    
    async def infer_dimension_hierarchy(self, data_model: DataModel) -> Dict[str, Any]:
        """
        推断维度层级
        
        使用 LLM Agent 分析字段元数据，推断维度层级结构。
        
        Args:
            data_model: DataModel 对象
        
        Returns:
            维度层级字典
        """
        from tableau_assistant.src.agents.dimension_hierarchy.node import dimension_hierarchy_node
        
        start_time = time.time()
        
        try:
            result = await dimension_hierarchy_node(
                data_model=data_model,
                datasource_luid=data_model.datasource_luid,
            )
            
            # 转换为字典格式
            hierarchy_dict = {}
            for field_name, attrs in result.dimension_hierarchy.items():
                hierarchy_dict[field_name] = attrs.model_dump()
            
            duration = (time.time() - start_time) * 1000
            logger.info(
                f"维度层级推断完成: {data_model.datasource_luid}, "
                f"{len(hierarchy_dict)} 个维度, "
                f"耗时: {duration:.1f}ms"
            )
            
            return hierarchy_dict
            
        except Exception as e:
            logger.error(f"维度层级推断失败: {data_model.datasource_luid}, error={e}")
            return {}


__all__ = [
    "TableauDataModelLoader",
]
