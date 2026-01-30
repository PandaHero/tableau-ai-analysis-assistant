# -*- coding: utf-8 -*-
"""
FieldRetriever 测试

验证 FieldRetriever 基于 FeatureExtractionOutput 的检索功能。

测试内容：
1. FieldRetriever 使用 RetrieverFactory 进行检索
2. 基于 required_measures 和 required_dimensions 检索
3. 返回 FieldRAGResult（measures、dimensions、time_fields）
4. 降级模式（terms 为空时返回全部字段）

Requirements: 5.1-5.6 - FieldRetriever 字段检索
"""

import pytest
from unittest.mock import MagicMock
from typing import Any, Dict, List

from analytics_assistant.src.agents.semantic_parser.components.field_retriever import (
    FieldRetriever,
)
from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import (
    FeatureExtractionOutput,
    FieldRAGResult,
)
from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate


# =============================================================================
# 测试数据
# =============================================================================

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


def create_feature_output(
    required_measures: List[str] = None,
    required_dimensions: List[str] = None,
) -> FeatureExtractionOutput:
    """创建 FeatureExtractionOutput"""
    return FeatureExtractionOutput(
        required_measures=required_measures or [],
        required_dimensions=required_dimensions or [],
    )


# =============================================================================
# 单元测试
# =============================================================================

class TestFieldRetrieverInit:
    """FieldRetriever 初始化测试"""
    
    def test_field_retriever_init_with_defaults(self):
        """测试 FieldRetriever 使用默认配置初始化"""
        retriever = FieldRetriever()
        
        assert hasattr(retriever, 'top_k')
        assert hasattr(retriever, 'fallback_multiplier')
        assert retriever.top_k > 0
        assert retriever.fallback_multiplier >= 1.0
    
    def test_field_retriever_has_index_prefix(self):
        """测试 FieldRetriever 有索引前缀常量"""
        assert hasattr(FieldRetriever, 'INDEX_PREFIX')
        assert FieldRetriever.INDEX_PREFIX == "fields_"
    
    def test_field_retriever_config_params(self):
        """测试 FieldRetriever 配置参数"""
        retriever = FieldRetriever(top_k=10, fallback_multiplier=3.0)
        
        assert retriever.top_k == 10
        assert retriever.fallback_multiplier == 3.0


class TestFieldRetrieverDocuments:
    """FieldRetriever 字段转换测试"""
    
    def test_field_to_candidate(self):
        """测试字段转换为 FieldCandidate"""
        retriever = FieldRetriever()
        
        field = create_mock_field("region", "地区", "dimension", "string", "geography")
        
        candidate = retriever._field_to_candidate(field, confidence=0.9, source="test")
        
        assert candidate.field_name == "region"
        assert candidate.field_caption == "地区"
        assert candidate.field_type == "dimension"
        assert candidate.confidence == 0.9
        assert candidate.source == "test"


class TestFieldRetrieverRetrieve:
    """FieldRetriever retrieve 方法测试"""
    
    @pytest.mark.asyncio
    async def test_retrieve_returns_field_rag_result(self):
        """测试 retrieve 返回 FieldRAGResult"""
        retriever = FieldRetriever()
        
        fields = [
            create_mock_field("region", "地区"),
            create_mock_field("sales", "销售额", "measure"),
        ]
        data_model = create_mock_data_model(fields)
        feature_output = create_feature_output(
            required_measures=["销售额"],
            required_dimensions=["地区"],
        )
        
        result = await retriever.retrieve(
            feature_output=feature_output,
            data_model=data_model,
        )
        
        assert isinstance(result, FieldRAGResult)
        assert hasattr(result, 'measures')
        assert hasattr(result, 'dimensions')
        assert hasattr(result, 'time_fields')
    
    @pytest.mark.asyncio
    async def test_retrieve_with_no_data_model(self):
        """测试无数据模型返回空结果"""
        retriever = FieldRetriever()
        feature_output = create_feature_output(required_measures=["销售额"])
        
        result = await retriever.retrieve(
            feature_output=feature_output,
            data_model=None,
        )
        
        assert isinstance(result, FieldRAGResult)
        assert len(result.measures) == 0
        assert len(result.dimensions) == 0
    
    @pytest.mark.asyncio
    async def test_retrieve_with_empty_fields(self):
        """测试空字段列表返回空结果"""
        retriever = FieldRetriever()
        data_model = create_mock_data_model([])
        feature_output = create_feature_output(required_measures=["销售额"])
        
        result = await retriever.retrieve(
            feature_output=feature_output,
            data_model=data_model,
        )
        
        assert len(result.measures) == 0
        assert len(result.dimensions) == 0


class TestFieldRetrieverFallback:
    """FieldRetriever 降级模式测试"""
    
    @pytest.mark.asyncio
    async def test_fallback_mode_when_terms_empty(self):
        """测试 terms 为空时的降级模式"""
        retriever = FieldRetriever()
        
        fields = [
            create_mock_field("region", "地区"),
            create_mock_field("city", "城市"),
            create_mock_field("sales", "销售额", "measure"),
            create_mock_field("profit", "利润", "measure"),
        ]
        data_model = create_mock_data_model(fields)
        
        # required_measures 和 required_dimensions 都为空
        feature_output = create_feature_output()
        
        result = await retriever.retrieve(
            feature_output=feature_output,
            data_model=data_model,
        )
        
        # 降级模式应该返回所有字段
        assert len(result.measures) == 2  # sales, profit
        assert len(result.dimensions) == 2  # region, city
        
        # 验证来源是 fallback
        for c in result.measures:
            assert c.source == "fallback"
        for c in result.dimensions:
            assert c.source == "fallback"


class TestFieldRetrieverExactMatch:
    """FieldRetriever 精确匹配测试"""
    
    @pytest.mark.asyncio
    async def test_exact_match_by_caption(self):
        """测试通过标题精确匹配"""
        retriever = FieldRetriever()
        
        fields = [
            create_mock_field("region", "地区"),
            create_mock_field("city", "城市"),
            create_mock_field("sales_amount", "销售额", "measure"),
            create_mock_field("profit", "利润", "measure"),
        ]
        data_model = create_mock_data_model(fields)
        
        feature_output = create_feature_output(
            required_measures=["销售额"],
            required_dimensions=["地区"],
        )
        
        result = await retriever.retrieve(
            feature_output=feature_output,
            data_model=data_model,
        )
        
        # 应该精确匹配到对应字段
        measure_names = {c.field_name for c in result.measures}
        dimension_names = {c.field_name for c in result.dimensions}
        
        assert "sales_amount" in measure_names
        assert "region" in dimension_names
    
    @pytest.mark.asyncio
    async def test_exact_match_confidence(self):
        """测试精确匹配的置信度"""
        retriever = FieldRetriever()
        
        fields = [
            create_mock_field("sales", "销售额", "measure"),
        ]
        data_model = create_mock_data_model(fields)
        
        feature_output = create_feature_output(required_measures=["销售额"])
        
        result = await retriever.retrieve(
            feature_output=feature_output,
            data_model=data_model,
        )
        
        # 精确匹配应该有高置信度
        assert len(result.measures) > 0
        assert result.measures[0].confidence >= 0.9


class TestFieldRetrieverTimeFields:
    """FieldRetriever 时间字段检索测试"""
    
    @pytest.mark.asyncio
    async def test_retrieve_time_fields_by_data_type(self):
        """测试通过数据类型检索时间字段"""
        retriever = FieldRetriever()
        
        fields = [
            create_mock_field("order_date", "订单日期", "dimension", "date"),
            create_mock_field("created_at", "创建时间", "dimension", "datetime"),
            create_mock_field("region", "地区", "dimension", "string"),
        ]
        data_model = create_mock_data_model(fields)
        
        feature_output = create_feature_output()
        
        result = await retriever.retrieve(
            feature_output=feature_output,
            data_model=data_model,
        )
        
        # 应该检索到时间字段
        time_field_names = {c.field_name for c in result.time_fields}
        assert "order_date" in time_field_names
        assert "created_at" in time_field_names
        assert "region" not in time_field_names


class TestFieldRetrieverConfig:
    """FieldRetriever 配置测试"""
    
    def test_config_loaded_from_yaml(self):
        """测试配置从 YAML 加载"""
        retriever = FieldRetriever()
        
        # 配置应该从 app.yaml 加载
        assert isinstance(retriever.top_k, int)
        assert isinstance(retriever.fallback_multiplier, float)
        assert retriever.top_k > 0
        assert retriever.fallback_multiplier >= 1.0
    
    def test_config_override(self):
        """测试配置覆盖"""
        retriever = FieldRetriever(top_k=20, fallback_multiplier=5.0)
        
        assert retriever.top_k == 20
        assert retriever.fallback_multiplier == 5.0


# =============================================================================
# 集成测试
# =============================================================================

class TestFieldRetrieverIntegration:
    """FieldRetriever 集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_retrieval_flow(self):
        """测试完整的检索流程"""
        retriever = FieldRetriever(top_k=5)
        
        fields = [
            create_mock_field("region", "地区", "dimension", "string"),
            create_mock_field("city", "城市", "dimension", "string"),
            create_mock_field("product", "产品", "dimension", "string"),
            create_mock_field("order_date", "订单日期", "dimension", "date"),
            create_mock_field("sales", "销售额", "measure", "real"),
            create_mock_field("profit", "利润", "measure", "real"),
            create_mock_field("quantity", "数量", "measure", "integer"),
        ]
        data_model = create_mock_data_model(fields)
        
        feature_output = create_feature_output(
            required_measures=["销售额", "利润"],
            required_dimensions=["地区", "产品"],
        )
        
        result = await retriever.retrieve(
            feature_output=feature_output,
            data_model=data_model,
        )
        
        # 验证返回结构
        assert isinstance(result, FieldRAGResult)
        
        # 验证度量字段
        measure_names = {c.field_name for c in result.measures}
        assert "sales" in measure_names
        assert "profit" in measure_names
        
        # 验证维度字段
        dimension_names = {c.field_name for c in result.dimensions}
        assert "region" in dimension_names
        assert "product" in dimension_names
        
        # 验证时间字段
        time_field_names = {c.field_name for c in result.time_fields}
        assert "order_date" in time_field_names
    
    @pytest.mark.asyncio
    async def test_top_k_limit(self):
        """测试 Top-K 限制"""
        retriever = FieldRetriever(top_k=2)
        
        # 创建多个度量字段
        fields = [
            create_mock_field(f"measure_{i}", f"度量{i}", "measure")
            for i in range(10)
        ]
        data_model = create_mock_data_model(fields)
        
        # 降级模式会返回所有字段，但应该被 Top-K 限制
        feature_output = create_feature_output(
            required_measures=[],  # 空列表触发降级模式
            required_dimensions=[],
        )
        
        result = await retriever.retrieve(
            feature_output=feature_output,
            data_model=data_model,
        )
        
        # 降级模式下，返回数量应该是 top_k * fallback_multiplier
        # top_k=2, fallback_multiplier=2.0, 所以最多返回 4 个
        assert len(result.measures) <= 4