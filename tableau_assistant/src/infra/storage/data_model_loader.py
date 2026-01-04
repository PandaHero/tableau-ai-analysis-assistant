# -*- coding: utf-8 -*-
"""
数据模型加载器抽象接口

定义数据模型加载的抽象接口，具体实现由各平台提供。

使用示例:
    from tableau_assistant.src.platforms.tableau import TableauDataModelLoader
    
    loader = TableauDataModelLoader(auth_ctx)
    data_model = await loader.load_data_model(datasource_luid)
    hierarchy = await loader.infer_dimension_hierarchy(data_model)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any

from tableau_assistant.src.infra.storage.data_model import DataModel


class DataModelLoader(ABC):
    """
    数据模型加载器抽象基类
    
    定义加载数据模型和推断维度层级的接口。
    不同平台可以提供不同的实现。
    """
    
    @abstractmethod
    async def load_data_model(self, datasource_luid: str) -> DataModel:
        """
        从数据源加载数据模型
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            DataModel 对象
        """
        pass
    
    @abstractmethod
    async def infer_dimension_hierarchy(self, data_model: DataModel) -> Dict[str, Any]:
        """
        推断维度层级
        
        Args:
            data_model: DataModel 对象
        
        Returns:
            维度层级字典
        """
        pass


__all__ = [
    "DataModelLoader",
]
