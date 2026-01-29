# -*- coding: utf-8 -*-
"""
FieldRetriever 迁移测试

验证 FieldRetriever 迁移到 RAGService 后功能正常。

测试内容：
1. FieldRetriever 使用 RAGService 进行索引管理
2. 三层检索策略（L0/L1/L2）正常工作
3. 索引创建和检索功能正常

Requirements: 6.1 - FieldRetriever 迁移
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List

from analytics_assistant.src.agents.semantic_parser.components.field_retriever import (
    FieldRetriever,
    extract_categories_by_rules,
    match_field_name_or_caption,
)
from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import FieldCandidate


# ═══════════════════════════════════════════════════════════════════════════
# 测试数据
# ═══════════════════════════════════════════════════════════════════════════

def create_mock_field(
    name: str,
    caption: str,
    role: str = "dimension",
    data_type: str = "string",
    category: str = None,
) -> Dict[str, Any]:
    """创建模拟字段"""
    return {
        "name": name,
        "field_name": name,
        "fieldCaption": caption,
        "field_caption": caption,
        "role": role,
        "dataType": data_type,
        "data_type": data_type,
        "category": category,
    }


def create_mock_data_model(fields: List[Dict[str, Any]]) -> MagicMock:
    """创建模拟数据模型"""
    model = MagicMock()
    model.fields = fields
    return model


# ═══════════════════════════════════════════════════════════════════════════
# 单元测试
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldRetrieverMigration:
    """FieldRetriever 迁移测试"""
    
    def test_field_retriever_init_uses_rag_service(self):
        """测试 FieldRetriever 初始化时使用 RAGService"""
        retriever = FieldRetriever()
        
        # 验证使用了 RAGService
        assert hasattr(retriever, '_rag_service')
        assert retriever._rag_service is not None
    
    def test_field_retriever_no_cascade_retriever_param(self):
        """测试 FieldRetriever 不再接受 cascade_retriever 参数"""
        # 新的 FieldRetriever 不应该有 cascade_retriever 参数
        import inspect
        sig = inspect.signature(FieldRetriever.__init__)
        params = list(sig.parameters.keys())
        
        assert 'cascade_retriever' not in params
        assert 'self' in params
        assert 'default_top_k' in params
        assert 'full_schema_threshold' in params
        assert 'min_rule_match_dimensions' in params
    
    def test_field_retriever_has_index_prefix(self):
        """测试 FieldRetriever 有索引前缀常量"""
        assert hasattr(FieldRetriever, 'INDEX_PREFIX')
        assert FieldRetriever.INDEX_PREFIX == "fields_"
    
    def test_get_index_name(self):
        """测试索引名称生成"""
        retriever = FieldRetriever()
        
        index_name = retriever._get_index_name("ds_123")
        assert index_name == "fields_ds_123"
        
        index_name = retriever._get_index_name("test_datasource")
        assert index_name == "fields_test_datasource"
    
    def test_fields_to_documents(self):
        """测试字段转换为 IndexDocument"""
        retriever = FieldRetriever()
        
        fields = [
            create_mock_field("region", "地区", "dimension", "string", "geography"),
            create_mock_field("sales", "销售额", "measure", "real"),
        ]
        
        documents = retriever._fields_to_documents(fields)
        
        assert len(documents) == 2
        
        # 验证第一个文档
        doc1 = documents[0]
        assert doc1.id == "region"
        assert "region" in doc1.content
        assert "地区" in doc1.content
        assert doc1.metadata["role"] == "dimension"
        assert doc1.metadata["field_caption"] == "地区"
        
        # 验证第二个文档
        doc2 = documents[1]
        assert doc2.id == "sales"
        assert doc2.metadata["role"] == "measure"


class TestFieldRetrieverL0Strategy:
    """L0 全量返回策略测试"""
    
    @pytest.mark.asyncio
    async def test_l0_full_schema_mode(self):
        """测试 L0 全量模式（字段数 <= 阈值）"""
        retriever = FieldRetriever(full_schema_threshold=10)
        
        # 创建少量字段（小于阈值）
        fields = [
            create_mock_field("region", "地区"),
            create_mock_field("product", "产品"),
            create_mock_field("sales", "销售额", "measure"),
        ]
        data_model = create_mock_data_model(fields)
        
        candidates = await retriever.retrieve(
            question="各地区的销售额",
            data_model=data_model,
        )
        
        # L0 模式应该返回所有字段
        assert len(candidates) == 3
        
        # 验证来源是 full_schema
        for c in candidates:
            assert c.source == "full_schema"


class TestFieldRetrieverL1Strategy:
    """L1 规则匹配策略测试"""
    
    def test_extract_categories_by_rules(self):
        """测试类别关键词提取"""
        # 时间相关
        categories = extract_categories_by_rules("上个月的销售额")
        assert "time" in categories
        
        # 地理相关
        categories = extract_categories_by_rules("各地区的销售情况")
        assert "geography" in categories
        
        # 产品相关
        categories = extract_categories_by_rules("各产品的销量")
        assert "product" in categories
        
        # 多类别
        categories = extract_categories_by_rules("上个月各地区各产品的销售额")
        assert "time" in categories
        assert "geography" in categories
        assert "product" in categories
    
    def test_match_field_name_or_caption(self):
        """测试字段名/标题匹配"""
        fields = [
            create_mock_field("region", "地区"),
            create_mock_field("product_name", "产品名称"),
            create_mock_field("sales_amount", "销售额"),
        ]
        
        # 匹配标题
        matched = match_field_name_or_caption("各地区的销售额", fields)
        assert "region" in matched
        assert "sales_amount" in matched
        
        # 匹配字段名
        matched = match_field_name_or_caption("product_name 的统计", fields)
        assert "product_name" in matched


class TestFieldRetrieverRetrieveMethod:
    """retrieve 方法测试"""
    
    @pytest.mark.asyncio
    async def test_retrieve_with_empty_question(self):
        """测试空问题返回空列表"""
        retriever = FieldRetriever()
        
        candidates = await retriever.retrieve(question="")
        assert candidates == []
        
        candidates = await retriever.retrieve(question="   ")
        assert candidates == []
    
    @pytest.mark.asyncio
    async def test_retrieve_with_no_data_model(self):
        """测试无数据模型返回空列表"""
        retriever = FieldRetriever()
        
        candidates = await retriever.retrieve(
            question="各地区的销售额",
            data_model=None,
        )
        assert candidates == []
    
    @pytest.mark.asyncio
    async def test_retrieve_with_empty_fields(self):
        """测试空字段列表返回空列表"""
        retriever = FieldRetriever()
        data_model = create_mock_data_model([])
        
        candidates = await retriever.retrieve(
            question="各地区的销售额",
            data_model=data_model,
        )
        assert candidates == []
    
    @pytest.mark.asyncio
    async def test_retrieve_accepts_datasource_luid(self):
        """测试 retrieve 方法接受 datasource_luid 参数"""
        retriever = FieldRetriever(full_schema_threshold=100)
        
        fields = [
            create_mock_field("region", "地区"),
            create_mock_field("sales", "销售额", "measure"),
        ]
        data_model = create_mock_data_model(fields)
        
        # 应该能够接受 datasource_luid 参数
        candidates = await retriever.retrieve(
            question="各地区的销售额",
            data_model=data_model,
            datasource_luid="test_ds_123",
        )
        
        # L0 模式应该返回所有字段
        assert len(candidates) == 2


# ═══════════════════════════════════════════════════════════════════════════
# 集成测试
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldRetrieverIntegration:
    """FieldRetriever 集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_retrieval_flow(self):
        """测试完整的检索流程"""
        retriever = FieldRetriever(
            full_schema_threshold=5,  # 设置较小的阈值以触发 L1
            min_rule_match_dimensions=1,
        )
        
        # 创建较多字段（超过阈值）
        fields = [
            create_mock_field("region", "地区", "dimension", "string", "geography"),
            create_mock_field("city", "城市", "dimension", "string", "geography"),
            create_mock_field("product", "产品", "dimension", "string", "product"),
            create_mock_field("category", "品类", "dimension", "string", "product"),
            create_mock_field("date", "日期", "dimension", "date", "time"),
            create_mock_field("month", "月份", "dimension", "string", "time"),
            create_mock_field("sales", "销售额", "measure", "real"),
            create_mock_field("quantity", "数量", "measure", "integer"),
        ]
        data_model = create_mock_data_model(fields)
        
        # 执行检索
        candidates = await retriever.retrieve(
            question="各地区的销售额",
            data_model=data_model,
        )
        
        # 应该返回相关字段
        assert len(candidates) > 0
        
        # 验证返回的字段包含地区相关和销售相关
        field_names = {c.field_name for c in candidates}
        # 地区相关字段应该被匹配
        assert "region" in field_names or "city" in field_names
        # 销售相关字段应该被匹配
        assert "sales" in field_names
