# -*- coding: utf-8 -*-
"""
FieldRetriever 手动测试

测试字段检索功能：
- 三层检索策略（L0 全量 / L1 规则匹配 / L2 Embedding 兜底）
- 类别关键词匹配（从 SEED_PATTERNS 动态提取）
- 维度层级扩展
- 度量全量返回

运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    python -m pytest tests/manual/test_field_retriever.py -v
"""

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass
from typing import List, Optional

from analytics_assistant.src.agents.semantic_parser.components.field_retriever import (
    FieldCandidate,
    FieldRetriever,
    get_full_schema_threshold,
    get_default_top_k,
    get_category_keywords,
    extract_categories_by_rules,
    match_field_name_or_caption,
)


# ═══════════════════════════════════════════════════════════════════════════
# Mock 数据
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MockFieldChunk:
    """Mock FieldChunk"""
    field_name: str
    field_caption: str
    role: str
    data_type: str
    category: Optional[str] = None
    formula: Optional[str] = None
    logical_table_caption: Optional[str] = None
    sample_values: Optional[List[str]] = None
    metadata: dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MockRetrievalSource:
    """Mock RetrievalSource"""
    def __init__(self, value: str):
        self.value = value


@dataclass
class MockRetrievalResult:
    """Mock RetrievalResult"""
    field_chunk: MockFieldChunk
    score: float
    source: MockRetrievalSource
    rank: int


@dataclass
class MockFieldMetadata:
    """Mock FieldMetadata"""
    name: str
    fieldCaption: str
    role: str
    dataType: str
    description: Optional[str] = None
    sample_values: Optional[List[str]] = None
    category: Optional[str] = None
    formula: Optional[str] = None


class MockDataModel:
    """Mock DataModel"""
    def __init__(self, fields: List[MockFieldMetadata], datasource_luid: str = "test-ds"):
        self.fields = fields
        self.datasource_luid = datasource_luid


# ═══════════════════════════════════════════════════════════════════════════
# 测试配置加载
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigLoading:
    """测试配置加载"""
    
    def test_get_full_schema_threshold(self):
        """测试获取 L0 阈值"""
        threshold = get_full_schema_threshold()
        assert isinstance(threshold, int)
        assert threshold > 0
    
    def test_get_default_top_k(self):
        """测试获取默认 Top-K"""
        top_k = get_default_top_k()
        assert isinstance(top_k, int)
        assert top_k > 0
    
    def test_get_category_keywords(self):
        """测试获取类别关键词"""
        keywords = get_category_keywords()
        assert isinstance(keywords, dict)
        # 应该包含主要类别
        assert "time" in keywords
        assert "geography" in keywords
        assert "product" in keywords
        # 每个类别应该有关键词
        assert len(keywords["time"]) > 0
        assert len(keywords["geography"]) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 测试 FieldCandidate
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldCandidate:
    """测试 FieldCandidate 模型"""
    
    def test_create_candidate(self):
        """测试创建 FieldCandidate"""
        candidate = FieldCandidate(
            field_name="sales",
            field_caption="销售额",
            field_type="measure",
            data_type="float",
            confidence=0.95,
        )
        
        assert candidate.field_name == "sales"
        assert candidate.field_caption == "销售额"
        assert candidate.field_type == "measure"
        assert candidate.confidence == 0.95
    
    def test_confidence_validation(self):
        """测试置信度范围验证"""
        # 有效范围
        candidate = FieldCandidate(
            field_name="test",
            field_caption="测试",
            field_type="dimension",
            data_type="string",
            confidence=0.0,
        )
        assert candidate.confidence == 0.0
        
        candidate = FieldCandidate(
            field_name="test",
            field_caption="测试",
            field_type="dimension",
            data_type="string",
            confidence=1.0,
        )
        assert candidate.confidence == 1.0
        
        # 无效范围
        with pytest.raises(ValueError):
            FieldCandidate(
                field_name="test",
                field_caption="测试",
                field_type="dimension",
                data_type="string",
                confidence=1.5,
            )
    
    def test_hierarchy_fields(self):
        """测试维度层级字段"""
        candidate = FieldCandidate(
            field_name="province",
            field_caption="省份",
            field_type="dimension",
            data_type="string",
            confidence=0.9,
            hierarchy_level=2,
            hierarchy_category="geography",
            parent_dimension=None,
            child_dimension="city",
        )
        
        assert candidate.hierarchy_level == 2
        assert candidate.hierarchy_category == "geography"
        assert candidate.parent_dimension is None
        assert candidate.child_dimension == "city"


# ═══════════════════════════════════════════════════════════════════════════
# 测试规则匹配工具函数
# ═══════════════════════════════════════════════════════════════════════════

class TestCategoryExtraction:
    """测试类别关键词提取"""
    
    def test_geography_keywords(self):
        """测试地理类别关键词"""
        assert "geography" in extract_categories_by_rules("各地区的销售额")
        assert "geography" in extract_categories_by_rules("哪个省份卖得最好")
        assert "geography" in extract_categories_by_rules("门店销售排名")
    
    def test_time_keywords(self):
        """测试时间类别关键词"""
        assert "time" in extract_categories_by_rules("上个月的销售额")
        assert "time" in extract_categories_by_rules("今年的业绩")
        assert "time" in extract_categories_by_rules("最近一周的数据")
        assert "time" in extract_categories_by_rules("Q1的销售情况")
    
    def test_product_keywords(self):
        """测试产品类别关键词"""
        assert "product" in extract_categories_by_rules("各品类的销售额")
        assert "product" in extract_categories_by_rules("哪个品牌卖得最好")
        assert "product" in extract_categories_by_rules("SKU销售排名")
    
    def test_multiple_categories(self):
        """测试多类别匹配"""
        categories = extract_categories_by_rules("上个月各地区各品类的销售额")
        assert "time" in categories
        assert "geography" in categories
        assert "product" in categories
    
    def test_no_match(self):
        """测试无匹配"""
        categories = extract_categories_by_rules("总销售额是多少")
        # 可能匹配不到任何类别
        assert isinstance(categories, set)


class TestFieldNameMatching:
    """测试字段名/标题匹配"""
    
    def test_match_field_caption(self):
        """测试匹配字段标题"""
        fields = [
            MockFieldMetadata(name="sales", fieldCaption="销售额", role="MEASURE", dataType="float"),
            MockFieldMetadata(name="region", fieldCaption="地区", role="DIMENSION", dataType="string"),
        ]
        
        matched = match_field_name_or_caption("销售额是多少", fields)
        assert "sales" in matched
    
    def test_match_field_name(self):
        """测试匹配字段名"""
        fields = [
            MockFieldMetadata(name="sales", fieldCaption="销售额", role="MEASURE", dataType="float"),
        ]
        
        matched = match_field_name_or_caption("show me sales", fields)
        assert "sales" in matched
    
    def test_short_caption_not_matched(self):
        """测试短标题不匹配（避免单字误匹配）"""
        fields = [
            MockFieldMetadata(name="year", fieldCaption="年", role="DIMENSION", dataType="string"),
        ]
        
        # 单字标题不应该匹配
        matched = match_field_name_or_caption("今年的数据", fields)
        assert "year" not in matched


# ═══════════════════════════════════════════════════════════════════════════
# 测试 FieldRetriever - L0 全量模式
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldRetrieverL0FullSchema:
    """测试 L0 全量模式（字段数 <= 阈值）"""
    
    @pytest.fixture
    def small_data_model(self):
        """创建小数据模型（字段数 < 阈值）"""
        fields = [
            MockFieldMetadata(name="sales", fieldCaption="销售额", role="MEASURE", dataType="float"),
            MockFieldMetadata(name="profit", fieldCaption="利润", role="MEASURE", dataType="float"),
            MockFieldMetadata(name="region", fieldCaption="地区", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="date", fieldCaption="日期", role="DIMENSION", dataType="date"),
            MockFieldMetadata(name="product", fieldCaption="产品", role="DIMENSION", dataType="string"),
        ]
        return MockDataModel(fields)
    
    @pytest.mark.asyncio
    async def test_full_schema_mode_returns_all_fields(self, small_data_model):
        """测试全量模式返回所有字段"""
        retriever = FieldRetriever(full_schema_threshold=20)
        
        candidates = await retriever.retrieve(
            question="上个月各地区的销售额",
            data_model=small_data_model,
        )
        
        # 应该返回所有 5 个字段
        assert len(candidates) == 5
        
        # 检查字段名
        field_names = {c.field_name for c in candidates}
        assert field_names == {"sales", "profit", "region", "date", "product"}
    
    @pytest.mark.asyncio
    async def test_full_schema_mode_source(self, small_data_model):
        """测试全量模式的来源标记"""
        retriever = FieldRetriever(full_schema_threshold=20)
        
        candidates = await retriever.retrieve(
            question="测试问题",
            data_model=small_data_model,
        )
        
        # 所有字段的来源应该是 full_schema
        assert all(c.source == "full_schema" for c in candidates)
    
    @pytest.mark.asyncio
    async def test_full_schema_mode_confidence(self, small_data_model):
        """测试全量模式的置信度"""
        retriever = FieldRetriever(full_schema_threshold=20)
        
        candidates = await retriever.retrieve(
            question="测试问题",
            data_model=small_data_model,
        )
        
        # 全量模式的默认置信度是 0.8
        assert all(c.confidence == 0.8 for c in candidates)


# ═══════════════════════════════════════════════════════════════════════════
# 测试 FieldRetriever - L1 规则匹配模式
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldRetrieverL1RuleMatch:
    """测试 L1 规则匹配模式（字段数 > 阈值）"""
    
    @pytest.fixture
    def large_data_model(self):
        """创建大数据模型（字段数 > 阈值）"""
        # 创建 30 个字段
        fields = [
            # 度量 (5个)
            MockFieldMetadata(name="sales", fieldCaption="销售额", role="MEASURE", dataType="float"),
            MockFieldMetadata(name="profit", fieldCaption="利润", role="MEASURE", dataType="float"),
            MockFieldMetadata(name="cost", fieldCaption="成本", role="MEASURE", dataType="float"),
            MockFieldMetadata(name="quantity", fieldCaption="数量", role="MEASURE", dataType="integer"),
            MockFieldMetadata(name="discount", fieldCaption="折扣", role="MEASURE", dataType="float"),
            # 地理维度 (5个)
            MockFieldMetadata(name="country", fieldCaption="国家", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="province", fieldCaption="省份", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="city", fieldCaption="城市", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="district", fieldCaption="区县", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="store", fieldCaption="门店", role="DIMENSION", dataType="string"),
            # 时间维度 (5个)
            MockFieldMetadata(name="year", fieldCaption="年份", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="quarter", fieldCaption="季度", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="month", fieldCaption="月份", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="week", fieldCaption="周", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="date", fieldCaption="日期", role="DIMENSION", dataType="date"),
            # 产品维度 (5个)
            MockFieldMetadata(name="category", fieldCaption="品类", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="subcategory", fieldCaption="子品类", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="brand", fieldCaption="品牌", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="product_name", fieldCaption="产品名称", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="sku", fieldCaption="SKU", role="DIMENSION", dataType="string"),
            # 其他维度 (10个)
            MockFieldMetadata(name="customer", fieldCaption="客户", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="channel", fieldCaption="渠道", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="salesperson", fieldCaption="销售员", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="order_id", fieldCaption="订单号", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="payment_method", fieldCaption="支付方式", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="shipping_method", fieldCaption="配送方式", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="status", fieldCaption="状态", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="source", fieldCaption="来源", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="campaign", fieldCaption="活动", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="segment", fieldCaption="细分", role="DIMENSION", dataType="string"),
        ]
        return MockDataModel(fields)
    
    @pytest.fixture
    def dimension_hierarchy(self):
        """创建维度层级信息"""
        return {
            # 地理层级
            "country": {"category": "geography", "level": 1, "parent_dimension": None, "child_dimension": "province"},
            "province": {"category": "geography", "level": 2, "parent_dimension": "country", "child_dimension": "city"},
            "city": {"category": "geography", "level": 3, "parent_dimension": "province", "child_dimension": "district"},
            "district": {"category": "geography", "level": 4, "parent_dimension": "city", "child_dimension": "store"},
            "store": {"category": "geography", "level": 5, "parent_dimension": "district", "child_dimension": None},
            # 时间层级
            "year": {"category": "time", "level": 1, "parent_dimension": None, "child_dimension": "quarter"},
            "quarter": {"category": "time", "level": 2, "parent_dimension": "year", "child_dimension": "month"},
            "month": {"category": "time", "level": 3, "parent_dimension": "quarter", "child_dimension": "week"},
            "week": {"category": "time", "level": 4, "parent_dimension": "month", "child_dimension": "date"},
            "date": {"category": "time", "level": 5, "parent_dimension": "week", "child_dimension": None},
            # 产品层级
            "category": {"category": "product", "level": 1, "parent_dimension": None, "child_dimension": "subcategory"},
            "subcategory": {"category": "product", "level": 2, "parent_dimension": "category", "child_dimension": "brand"},
            "brand": {"category": "product", "level": 3, "parent_dimension": "subcategory", "child_dimension": "product_name"},
            "product_name": {"category": "product", "level": 4, "parent_dimension": "brand", "child_dimension": "sku"},
            "sku": {"category": "product", "level": 5, "parent_dimension": "product_name", "child_dimension": None},
            # 其他
            "customer": {"category": "customer", "level": 3, "parent_dimension": None, "child_dimension": None},
            "channel": {"category": "channel", "level": 2, "parent_dimension": None, "child_dimension": None},
            "salesperson": {"category": "organization", "level": 4, "parent_dimension": None, "child_dimension": None},
        }
    
    @pytest.mark.asyncio
    async def test_rule_match_geography(self, large_data_model, dimension_hierarchy):
        """测试地理类别规则匹配"""
        retriever = FieldRetriever(full_schema_threshold=10)  # 强制进入 L1
        
        candidates = await retriever.retrieve(
            question="各地区的销售额",
            data_model=large_data_model,
            dimension_hierarchy=dimension_hierarchy,
        )
        
        # 应该包含所有度量
        measure_names = {c.field_name for c in candidates if c.field_type == "measure"}
        assert measure_names == {"sales", "profit", "cost", "quantity", "discount"}
        
        # 应该包含地理维度
        dimension_names = {c.field_name for c in candidates if c.field_type == "dimension"}
        assert "province" in dimension_names or "city" in dimension_names or "country" in dimension_names
    
    @pytest.mark.asyncio
    async def test_measures_always_full(self, large_data_model, dimension_hierarchy):
        """测试度量始终全量返回"""
        retriever = FieldRetriever(full_schema_threshold=10)
        
        candidates = await retriever.retrieve(
            question="各品类的数据",
            data_model=large_data_model,
            dimension_hierarchy=dimension_hierarchy,
        )
        
        # 所有度量都应该返回
        measure_names = {c.field_name for c in candidates if c.field_type == "measure"}
        assert measure_names == {"sales", "profit", "cost", "quantity", "discount"}


# ═══════════════════════════════════════════════════════════════════════════
# 测试 FieldRetriever - 维度层级增强
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldRetrieverHierarchyEnrichment:
    """测试维度层级信息增强"""
    
    @pytest.fixture
    def data_model_with_dimensions(self):
        """创建包含维度的数据模型"""
        fields = [
            MockFieldMetadata(name="province", fieldCaption="省份", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="city", fieldCaption="城市", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="sales", fieldCaption="销售额", role="MEASURE", dataType="float"),
        ]
        return MockDataModel(fields)
    
    @pytest.fixture
    def dimension_hierarchy(self):
        """创建维度层级信息"""
        return {
            "province": {
                "category": "geography",
                "level": 2,
                "granularity": "coarse",
                "parent_dimension": None,
                "child_dimension": "city",
            },
            "city": {
                "category": "geography",
                "level": 3,
                "granularity": "medium",
                "parent_dimension": "province",
                "child_dimension": None,
            },
        }
    
    @pytest.mark.asyncio
    async def test_hierarchy_enrichment_full_schema(
        self, data_model_with_dimensions, dimension_hierarchy
    ):
        """测试全量模式下的层级信息增强"""
        retriever = FieldRetriever(full_schema_threshold=50)
        
        candidates = await retriever.retrieve(
            question="各省份的销售额",
            data_model=data_model_with_dimensions,
            dimension_hierarchy=dimension_hierarchy,
        )
        
        # 找到省份字段
        province = next((c for c in candidates if c.field_name == "province"), None)
        assert province is not None
        assert province.hierarchy_level == 2
        assert province.hierarchy_category == "geography"
        assert province.child_dimension == "city"
        
        # 找到城市字段
        city = next((c for c in candidates if c.field_name == "city"), None)
        assert city is not None
        assert city.hierarchy_level == 3
        assert city.parent_dimension == "province"
    
    @pytest.mark.asyncio
    async def test_hierarchy_expansion(self, data_model_with_dimensions, dimension_hierarchy):
        """测试层级扩展（匹配城市时也返回省份）"""
        retriever = FieldRetriever(full_schema_threshold=2)  # 强制进入 L1
        
        candidates = await retriever.retrieve(
            question="各城市的销售额",
            data_model=data_model_with_dimensions,
            dimension_hierarchy=dimension_hierarchy,
        )
        
        dimension_names = {c.field_name for c in candidates if c.field_type == "dimension"}
        
        # 应该包含城市（直接匹配）和省份（层级扩展）
        assert "city" in dimension_names
        # 省份作为父维度也应该被扩展进来
        assert "province" in dimension_names


# ═══════════════════════════════════════════════════════════════════════════
# 测试 FieldRetriever - 边界情况
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldRetrieverEdgeCases:
    """测试边界情况"""
    
    @pytest.mark.asyncio
    async def test_empty_question(self):
        """测试空问题"""
        retriever = FieldRetriever()
        
        candidates = await retriever.retrieve(question="")
        assert candidates == []
        
        candidates = await retriever.retrieve(question="   ")
        assert candidates == []
    
    @pytest.mark.asyncio
    async def test_no_data_model(self):
        """测试无数据模型"""
        retriever = FieldRetriever()
        
        candidates = await retriever.retrieve(
            question="测试问题",
            data_model=None,
        )
        
        assert candidates == []
    
    @pytest.mark.asyncio
    async def test_empty_fields(self):
        """测试空字段列表"""
        retriever = FieldRetriever()
        data_model = MockDataModel(fields=[])
        
        candidates = await retriever.retrieve(
            question="测试问题",
            data_model=data_model,
        )
        
        assert candidates == []
    
    @pytest.mark.asyncio
    async def test_only_measures(self):
        """测试只有度量的情况"""
        fields = [
            MockFieldMetadata(name="sales", fieldCaption="销售额", role="MEASURE", dataType="float"),
            MockFieldMetadata(name="profit", fieldCaption="利润", role="MEASURE", dataType="float"),
        ]
        data_model = MockDataModel(fields)
        
        retriever = FieldRetriever(full_schema_threshold=10)
        
        candidates = await retriever.retrieve(
            question="各地区的销售额",
            data_model=data_model,
        )
        
        # 应该返回所有度量
        assert len(candidates) == 2
        assert all(c.field_type == "measure" for c in candidates)
    
    @pytest.mark.asyncio
    async def test_only_dimensions(self):
        """测试只有维度的情况"""
        fields = [
            MockFieldMetadata(name="region", fieldCaption="地区", role="DIMENSION", dataType="string"),
            MockFieldMetadata(name="date", fieldCaption="日期", role="DIMENSION", dataType="date"),
        ]
        data_model = MockDataModel(fields)
        
        retriever = FieldRetriever(full_schema_threshold=10)
        
        candidates = await retriever.retrieve(
            question="各地区的数据",
            data_model=data_model,
        )
        
        # 应该返回所有维度
        assert len(candidates) == 2
        assert all(c.field_type == "dimension" for c in candidates)


# ═══════════════════════════════════════════════════════════════════════════
# 测试策略切换阈值
# ═══════════════════════════════════════════════════════════════════════════

class TestFieldRetrieverThreshold:
    """测试策略切换阈值"""
    
    @pytest.mark.asyncio
    async def test_below_threshold_uses_full_schema(self):
        """测试字段数低于阈值时使用全量模式"""
        fields = [
            MockFieldMetadata(name=f"field_{i}", fieldCaption=f"字段{i}", role="DIMENSION", dataType="string")
            for i in range(10)
        ]
        data_model = MockDataModel(fields)
        
        retriever = FieldRetriever(full_schema_threshold=20)
        candidates = await retriever.retrieve(
            question="测试问题",
            data_model=data_model,
        )
        
        # 应该返回所有字段
        assert len(candidates) == 10
        assert all(c.source == "full_schema" for c in candidates)
    
    @pytest.mark.asyncio
    async def test_above_threshold_uses_rule_match(self):
        """测试字段数高于阈值时使用规则匹配"""
        fields = [
            MockFieldMetadata(name=f"dim_{i}", fieldCaption=f"维度{i}", role="DIMENSION", dataType="string")
            for i in range(25)
        ]
        fields.append(MockFieldMetadata(name="sales", fieldCaption="销售额", role="MEASURE", dataType="float"))
        data_model = MockDataModel(fields)
        
        dimension_hierarchy = {
            "dim_0": {"category": "geography", "level": 2, "parent_dimension": None, "child_dimension": None},
        }
        
        retriever = FieldRetriever(full_schema_threshold=10)
        candidates = await retriever.retrieve(
            question="各地区的销售额",
            data_model=data_model,
            dimension_hierarchy=dimension_hierarchy,
        )
        
        # 不应该返回所有字段
        assert len(candidates) < 26
        # 但应该包含度量
        assert any(c.field_name == "sales" for c in candidates)


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
