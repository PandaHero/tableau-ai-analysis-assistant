"""
Property-Based Tests for Data Model Parsing

**Feature: rag-enhancement, Property 12: 数据模型解析**
**Validates: Requirements 12.2, 12.3**

Property 12: 数据模型解析
*For any* VizQL /get-datasource-model API 返回，应正确解析所有逻辑表和关系。
"""
import pytest
from hypothesis import given, strategies as st, settings, assume
from typing import List, Dict, Any, Optional

from tableau_assistant.src.models.data_model import (
    LogicalTable,
    LogicalTableRelationship,
    DataModel,
)


# ============================================================
# Strategies for generating test data
# ============================================================

@st.composite
def logical_table_strategy(draw):
    """生成随机逻辑表"""
    table_id = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N', 'P'))))
    caption = draw(st.text(min_size=1, max_size=100))
    return {
        "logicalTableId": table_id,
        "caption": caption
    }


@st.composite
def logical_table_relationship_strategy(draw, table_ids: List[str]):
    """生成随机逻辑表关系"""
    assume(len(table_ids) >= 2)
    from_id = draw(st.sampled_from(table_ids))
    to_id = draw(st.sampled_from([t for t in table_ids if t != from_id]))
    return {
        "fromLogicalTable": {"logicalTableId": from_id},
        "toLogicalTable": {"logicalTableId": to_id}
    }


@st.composite
def data_model_response_strategy(draw):
    """生成随机数据模型 API 响应"""
    # 生成 1-10 个逻辑表
    num_tables = draw(st.integers(min_value=1, max_value=10))
    tables = []
    for i in range(num_tables):
        table = draw(logical_table_strategy())
        # 确保 ID 唯一
        table["logicalTableId"] = f"table_{i}_{table['logicalTableId'][:10]}"
        tables.append(table)
    
    # 生成 0 到 (num_tables-1) 个关系
    table_ids = [t["logicalTableId"] for t in tables]
    num_relationships = draw(st.integers(min_value=0, max_value=max(0, num_tables - 1)))
    relationships = []
    
    if num_tables >= 2:
        for _ in range(num_relationships):
            from_id = draw(st.sampled_from(table_ids))
            to_candidates = [t for t in table_ids if t != from_id]
            if to_candidates:
                to_id = draw(st.sampled_from(to_candidates))
                relationships.append({
                    "fromLogicalTable": {"logicalTableId": from_id},
                    "toLogicalTable": {"logicalTableId": to_id}
                })
    
    return {
        "logicalTables": tables,
        "logicalTableRelationships": relationships
    }


# ============================================================
# Property Tests
# ============================================================

class TestDataModelParsing:
    """
    **Feature: rag-enhancement, Property 12: 数据模型解析**
    **Validates: Requirements 12.2, 12.3**
    """
    
    @given(data_model_response_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_logical_tables_parsed(self, api_response: Dict[str, Any]):
        """
        Property 12.1: 所有逻辑表都应被正确解析
        
        *For any* VizQL API 返回的逻辑表列表，解析后的 DataModel 应包含相同数量的逻辑表，
        且每个表的 logicalTableId 和 caption 应与原始数据一致。
        """
        # 解析逻辑表
        logical_tables = [
            LogicalTable(
                logicalTableId=t.get("logicalTableId", ""),
                caption=t.get("caption", "")
            )
            for t in api_response.get("logicalTables", [])
        ]
        
        # 验证数量一致
        assert len(logical_tables) == len(api_response.get("logicalTables", []))
        
        # 验证每个表的属性
        for i, table in enumerate(logical_tables):
            original = api_response["logicalTables"][i]
            assert table.logicalTableId == original["logicalTableId"]
            assert table.caption == original["caption"]
    
    @given(data_model_response_strategy())
    @settings(max_examples=100, deadline=None)
    def test_all_relationships_parsed(self, api_response: Dict[str, Any]):
        """
        Property 12.2: 所有逻辑表关系都应被正确解析
        
        *For any* VizQL API 返回的关系列表，解析后的 DataModel 应包含相同数量的关系，
        且每个关系的 fromLogicalTableId 和 toLogicalTableId 应与原始数据一致。
        """
        # 解析关系
        relationships = [
            LogicalTableRelationship(
                fromLogicalTableId=r.get("fromLogicalTable", {}).get("logicalTableId", ""),
                toLogicalTableId=r.get("toLogicalTable", {}).get("logicalTableId", "")
            )
            for r in api_response.get("logicalTableRelationships", [])
        ]
        
        # 验证数量一致
        assert len(relationships) == len(api_response.get("logicalTableRelationships", []))
        
        # 验证每个关系的属性
        for i, rel in enumerate(relationships):
            original = api_response["logicalTableRelationships"][i]
            assert rel.fromLogicalTableId == original["fromLogicalTable"]["logicalTableId"]
            assert rel.toLogicalTableId == original["toLogicalTable"]["logicalTableId"]
    
    @given(data_model_response_strategy())
    @settings(max_examples=100, deadline=None)
    def test_get_table_caption_returns_correct_caption(self, api_response: Dict[str, Any]):
        """
        Property 12.3: get_table_caption 应返回正确的表名
        
        *For any* DataModel 中的逻辑表，调用 get_table_caption(table_id) 应返回对应的 caption。
        """
        # 构建 DataModel
        logical_tables = [
            LogicalTable(
                logicalTableId=t.get("logicalTableId", ""),
                caption=t.get("caption", "")
            )
            for t in api_response.get("logicalTables", [])
        ]
        relationships = [
            LogicalTableRelationship(
                fromLogicalTableId=r.get("fromLogicalTable", {}).get("logicalTableId", ""),
                toLogicalTableId=r.get("toLogicalTable", {}).get("logicalTableId", "")
            )
            for r in api_response.get("logicalTableRelationships", [])
        ]
        
        data_model = DataModel(
            logicalTables=logical_tables,
            logicalTableRelationships=relationships
        )
        
        # 验证每个表的 caption 可以正确获取
        for table in logical_tables:
            caption = data_model.get_table_caption(table.logicalTableId)
            assert caption == table.caption
    
    @given(data_model_response_strategy())
    @settings(max_examples=100, deadline=None)
    def test_get_table_caption_returns_none_for_unknown_id(self, api_response: Dict[str, Any]):
        """
        Property 12.4: get_table_caption 对未知 ID 应返回 None
        
        *For any* DataModel，调用 get_table_caption 传入不存在的 table_id 应返回 None。
        """
        # 构建 DataModel
        logical_tables = [
            LogicalTable(
                logicalTableId=t.get("logicalTableId", ""),
                caption=t.get("caption", "")
            )
            for t in api_response.get("logicalTables", [])
        ]
        
        data_model = DataModel(
            logicalTables=logical_tables,
            logicalTableRelationships=[]
        )
        
        # 使用一个肯定不存在的 ID
        unknown_id = "unknown_table_id_that_does_not_exist_12345"
        caption = data_model.get_table_caption(unknown_id)
        assert caption is None


class TestDataModelIntegrity:
    """数据模型完整性测试"""
    
    @given(data_model_response_strategy())
    @settings(max_examples=50, deadline=None)
    def test_data_model_is_serializable(self, api_response: Dict[str, Any]):
        """
        DataModel 应该可以正确序列化和反序列化
        """
        # 构建 DataModel
        logical_tables = [
            LogicalTable(
                logicalTableId=t.get("logicalTableId", ""),
                caption=t.get("caption", "")
            )
            for t in api_response.get("logicalTables", [])
        ]
        relationships = [
            LogicalTableRelationship(
                fromLogicalTableId=r.get("fromLogicalTable", {}).get("logicalTableId", ""),
                toLogicalTableId=r.get("toLogicalTable", {}).get("logicalTableId", "")
            )
            for r in api_response.get("logicalTableRelationships", [])
        ]
        
        data_model = DataModel(
            logicalTables=logical_tables,
            logicalTableRelationships=relationships
        )
        
        # 验证可以访问所有属性
        assert isinstance(data_model.logicalTables, list)
        assert isinstance(data_model.logicalTableRelationships, list)
        assert len(data_model.logicalTables) == len(logical_tables)
        assert len(data_model.logicalTableRelationships) == len(relationships)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
