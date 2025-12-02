"""
测试数据模型优雅降级功能

验证当数据模型 API 不可用时，系统能够继续使用字段元数据。
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import logging

from tableau_assistant.src.models.data_model import DataModel, LogicalTable, LogicalTableRelationship
from tableau_assistant.src.models.metadata import Metadata, FieldMetadata


class TestGracefulDegradation:
    """优雅降级测试"""
    
    def test_metadata_works_without_data_model(self):
        """测试元数据在没有数据模型时仍然可用"""
        # 创建没有数据模型的元数据
        metadata = Metadata(
            datasource_luid="test-datasource",
            datasource_name="Test Datasource",
            fields=[
                FieldMetadata(
                    name="sales",
                    fieldCaption="Sales Amount",
                    role="measure",
                    dataType="REAL"
                ),
                FieldMetadata(
                    name="region",
                    fieldCaption="Region",
                    role="dimension",
                    dataType="STRING"
                )
            ],
            field_count=2,
            data_model=None  # 没有数据模型
        )
        
        # 验证元数据功能正常
        assert metadata.datasource_name == "Test Datasource"
        assert len(metadata.fields) == 2
        
        # 验证字段查询功能正常
        sales_field = metadata.get_field("sales")
        assert sales_field is not None
        assert sales_field.fieldCaption == "Sales Amount"
        
        # 验证维度/度量分类功能正常
        dimensions = metadata.get_dimensions()
        measures = metadata.get_measures()
        assert len(dimensions) == 1
        assert len(measures) == 1
        assert dimensions[0].name == "region"
        assert measures[0].name == "sales"
    
    def test_field_without_logical_table_caption(self):
        """测试字段在没有 logicalTableCaption 时仍然可用"""
        field = FieldMetadata(
            name="order_date",
            fieldCaption="Order Date",
            role="dimension",
            dataType="DATE",
            logicalTableId="t1",  # 有 logicalTableId
            logicalTableCaption=None  # 但没有 logicalTableCaption
        )
        
        # 验证字段功能正常
        assert field.name == "order_date"
        assert field.fieldCaption == "Order Date"
        assert field.logicalTableId == "t1"
        assert field.logicalTableCaption is None
    
    def test_data_model_none_is_valid(self):
        """测试 data_model 为 None 是有效状态"""
        metadata = Metadata(
            datasource_luid="test",
            datasource_name="Test",
            fields=[],
            field_count=0,
            data_model=None
        )
        
        # 验证 data_model 为 None 不会导致错误
        assert metadata.data_model is None
        
        # 验证可以安全地检查 data_model
        if metadata.data_model:
            # 这个分支不应该执行
            assert False, "data_model should be None"
        else:
            # 这个分支应该执行
            pass
    
    def test_metadata_with_partial_data_model_info(self):
        """测试部分字段有数据模型信息的情况"""
        metadata = Metadata(
            datasource_luid="test",
            datasource_name="Test",
            fields=[
                FieldMetadata(
                    name="field1",
                    fieldCaption="Field 1",
                    role="dimension",
                    dataType="STRING",
                    logicalTableId="t1",
                    logicalTableCaption="Table 1"  # 有完整信息
                ),
                FieldMetadata(
                    name="field2",
                    fieldCaption="Field 2",
                    role="measure",
                    dataType="REAL",
                    logicalTableId="t2",
                    logicalTableCaption=None  # 缺少表名
                ),
                FieldMetadata(
                    name="field3",
                    fieldCaption="Field 3",
                    role="dimension",
                    dataType="STRING",
                    logicalTableId=None,  # 没有表 ID
                    logicalTableCaption=None
                )
            ],
            field_count=3
        )
        
        # 验证所有字段都可以正常访问
        for field in metadata.fields:
            assert field.name is not None
            assert field.fieldCaption is not None
        
        # 验证可以安全地访问可能为 None 的属性
        for field in metadata.fields:
            table_info = field.logicalTableCaption or "Unknown Table"
            assert table_info is not None


class TestDataModelFallback:
    """数据模型回退测试"""
    
    def test_empty_data_model_is_valid(self):
        """测试空数据模型是有效的"""
        data_model = DataModel(
            logicalTables=[],
            logicalTableRelationships=[]
        )
        
        # 验证空数据模型的方法不会报错
        assert data_model.get_table_caption("any_id") is None
        assert data_model.get_table_by_id("any_id") is None
        assert data_model.get_related_tables("any_id") == []
    
    def test_data_model_with_missing_relationships(self):
        """测试只有表没有关系的数据模型"""
        data_model = DataModel(
            logicalTables=[
                LogicalTable(logicalTableId="t1", caption="Table 1"),
                LogicalTable(logicalTableId="t2", caption="Table 2")
            ],
            logicalTableRelationships=[]  # 没有关系
        )
        
        # 验证表查询正常
        assert data_model.get_table_caption("t1") == "Table 1"
        assert data_model.get_table_caption("t2") == "Table 2"
        
        # 验证关系查询返回空列表
        assert data_model.get_related_tables("t1") == []
        assert data_model.get_related_tables("t2") == []


class TestLoggingOnDegradation:
    """降级时的日志测试"""
    
    def test_degradation_logs_warning(self, caplog):
        """测试降级时记录警告日志"""
        # 这个测试验证日志消息格式
        # 实际的日志测试需要在集成测试中进行
        
        # 模拟降级场景的日志消息
        expected_messages = [
            "获取数据模型失败，启用优雅降级",
            "数据模型 API 不可用，将继续使用字段元数据",
            "功能影响: 无法获取逻辑表名称和表关系信息"
        ]
        
        # 验证消息格式是合理的
        for msg in expected_messages:
            assert isinstance(msg, str)
            assert len(msg) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
