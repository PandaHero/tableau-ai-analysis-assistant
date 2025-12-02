"""
测试数据模型缓存功能

验证 StoreManager 的数据模型缓存方法。
"""
import pytest
import time
from unittest.mock import MagicMock

from tableau_assistant.src.capabilities.storage.store_manager import StoreManager
from tableau_assistant.src.models.data_model import DataModel, LogicalTable, LogicalTableRelationship
from langgraph.store.memory import InMemoryStore


class TestDataModelCache:
    """数据模型缓存测试"""
    
    @pytest.fixture
    def store_manager(self):
        """创建测试用的 StoreManager"""
        store = InMemoryStore()
        return StoreManager(store)
    
    @pytest.fixture
    def sample_data_model(self):
        """创建测试用的数据模型"""
        return DataModel(
            logicalTables=[
                LogicalTable(logicalTableId="t1", caption="订单表"),
                LogicalTable(logicalTableId="t2", caption="客户表"),
                LogicalTable(logicalTableId="t3", caption="产品表"),
            ],
            logicalTableRelationships=[
                LogicalTableRelationship(fromLogicalTableId="t1", toLogicalTableId="t2"),
                LogicalTableRelationship(fromLogicalTableId="t1", toLogicalTableId="t3"),
            ]
        )
    
    def test_put_and_get_data_model(self, store_manager, sample_data_model):
        """测试保存和获取数据模型"""
        datasource_luid = "test-datasource-123"
        
        # 保存数据模型
        result = store_manager.put_data_model(datasource_luid, sample_data_model)
        assert result is True
        
        # 获取数据模型
        cached_model = store_manager.get_data_model(datasource_luid)
        
        # 验证返回类型
        assert cached_model is not None
        assert isinstance(cached_model, DataModel)
        
        # 验证逻辑表
        assert len(cached_model.logicalTables) == 3
        assert cached_model.logicalTables[0].logicalTableId == "t1"
        assert cached_model.logicalTables[0].caption == "订单表"
        
        # 验证关系
        assert len(cached_model.logicalTableRelationships) == 2
        assert cached_model.logicalTableRelationships[0].fromLogicalTableId == "t1"
        assert cached_model.logicalTableRelationships[0].toLogicalTableId == "t2"
    
    def test_get_nonexistent_data_model(self, store_manager):
        """测试获取不存在的数据模型"""
        cached_model = store_manager.get_data_model("nonexistent-datasource")
        assert cached_model is None
    
    def test_data_model_methods_work_after_cache(self, store_manager, sample_data_model):
        """测试缓存后的数据模型方法仍然可用"""
        datasource_luid = "test-datasource-456"
        
        # 保存数据模型
        store_manager.put_data_model(datasource_luid, sample_data_model)
        
        # 获取数据模型
        cached_model = store_manager.get_data_model(datasource_luid)
        
        # 测试 get_table_caption 方法
        assert cached_model.get_table_caption("t1") == "订单表"
        assert cached_model.get_table_caption("t2") == "客户表"
        assert cached_model.get_table_caption("unknown") is None
        
        # 测试 get_table_by_id 方法
        table = cached_model.get_table_by_id("t1")
        assert table is not None
        assert table.caption == "订单表"
        
        # 测试 get_related_tables 方法
        related = cached_model.get_related_tables("t1")
        assert len(related) == 2
        related_captions = [t.caption for t in related]
        assert "客户表" in related_captions
        assert "产品表" in related_captions
    
    def test_clear_data_model_cache(self, store_manager, sample_data_model):
        """测试清除数据模型缓存"""
        datasource_luid = "test-datasource-789"
        
        # 保存数据模型
        store_manager.put_data_model(datasource_luid, sample_data_model)
        
        # 验证已保存
        assert store_manager.get_data_model(datasource_luid) is not None
        
        # 清除缓存
        result = store_manager.clear_data_model_cache(datasource_luid)
        assert result is True
        
        # 验证已清除
        assert store_manager.get_data_model(datasource_luid) is None
    
    def test_data_model_cache_preserves_empty_relationships(self, store_manager):
        """测试缓存保留空关系列表"""
        datasource_luid = "test-single-table"
        
        # 创建只有一个表、没有关系的数据模型
        single_table_model = DataModel(
            logicalTables=[
                LogicalTable(logicalTableId="t1", caption="单表")
            ],
            logicalTableRelationships=[]
        )
        
        # 保存和获取
        store_manager.put_data_model(datasource_luid, single_table_model)
        cached_model = store_manager.get_data_model(datasource_luid)
        
        # 验证
        assert cached_model is not None
        assert len(cached_model.logicalTables) == 1
        assert len(cached_model.logicalTableRelationships) == 0


class TestDataModelCacheTTL:
    """数据模型缓存 TTL 测试"""
    
    def test_cache_ttl_is_24_hours(self):
        """验证默认 TTL 是 24 小时"""
        assert StoreManager.DATA_MODEL_TTL == 86400  # 24 * 60 * 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
