# -*- coding: utf-8 -*-
"""
FieldMapper Node 单元测试

测试覆盖：
1. FieldMappingConfig - 配置加载
2. FieldCandidate 和 FieldMapping - 数据类
3. FieldMapperNode - 核心映射逻辑
4. 辅助函数
"""
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from analytics_assistant.src.agents.field_mapper.node import (
    FieldMapperNode,
    _extract_terms_from_semantic_query,
)
from analytics_assistant.src.agents.field_mapper.schemas import (
    FieldMappingConfig,
    FieldCandidate,
    FieldMapping,
)


# ══════════════════════════════════════════════════════════════════════════════
# 测试夹具
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_config():
    """模拟 YAML 配置"""
    return {
        "field_mapper": {
            "high_confidence_threshold": 0.9,
            "low_confidence_threshold": 0.7,
            "max_concurrency": 5,
            "cache_ttl": 86400,
            "top_k_candidates": 10,
            "max_alternatives": 3,
            "enable_cache": True,
            "enable_llm_fallback": True,
        }
    }


@pytest.fixture
def sample_field_chunks():
    """示例字段元数据"""
    @dataclass
    class MockField:
        field_name: str
        field_caption: str
        role: str
        data_type: str
        category: Optional[str] = None
        metadata: Optional[Dict] = None
        sample_values: Optional[List[str]] = None
    
    return [
        MockField(
            field_name="sales_amount",
            field_caption="销售额",
            role="measure",
            data_type="REAL",
            category="销售",
        ),
        MockField(
            field_name="order_count",
            field_caption="订单数",
            role="measure",
            data_type="INTEGER",
            category="销售",
        ),
        MockField(
            field_name="region",
            field_caption="地区",
            role="dimension",
            data_type="STRING",
            category="地理",
        ),
        MockField(
            field_name="order_date",
            field_caption="订单日期",
            role="dimension",
            data_type="DATE",
            category="时间",
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════════
# FieldMappingConfig 测试
# ══════════════════════════════════════════════════════════════════════════════

class TestFieldMappingConfig:
    """FieldMappingConfig 测试"""
    
    def test_default_values(self):
        """测试默认值"""
        config = FieldMappingConfig()
        assert config.high_confidence_threshold == 0.9
        assert config.low_confidence_threshold == 0.7
        assert config.max_concurrency == 5
        assert config.cache_ttl == 86400
        assert config.top_k_candidates == 10
        assert config.max_alternatives == 3
        assert config.enable_cache is True
        assert config.enable_llm_fallback is True
    
    def test_custom_values(self):
        """测试自定义值"""
        config = FieldMappingConfig(
            high_confidence_threshold=0.95,
            low_confidence_threshold=0.6,
            max_concurrency=10,
        )
        assert config.high_confidence_threshold == 0.95
        assert config.low_confidence_threshold == 0.6
        assert config.max_concurrency == 10


# ══════════════════════════════════════════════════════════════════════════════
# FieldCandidate 测试
# ══════════════════════════════════════════════════════════════════════════════

class TestFieldCandidate:
    """FieldCandidate 测试"""
    
    def test_creation(self):
        """测试创建"""
        candidate = FieldCandidate(
            field_name="sales_amount",
            field_caption="销售额",
            role="measure",
            data_type="REAL",
            score=0.95,
        )
        assert candidate.field_name == "sales_amount"
        assert candidate.field_caption == "销售额"
        assert candidate.role == "measure"
        assert candidate.data_type == "REAL"
        assert candidate.score == 0.95
        assert candidate.category is None
        assert candidate.level is None
    
    def test_with_optional_fields(self):
        """测试可选字段"""
        candidate = FieldCandidate(
            field_name="region",
            field_caption="地区",
            role="dimension",
            data_type="STRING",
            score=0.8,
            category="地理",
            level=1,
            granularity="省份",
            sample_values=["北京", "上海", "广州"],
        )
        assert candidate.category == "地理"
        assert candidate.level == 1
        assert candidate.granularity == "省份"
        assert candidate.sample_values == ["北京", "上海", "广州"]


# ══════════════════════════════════════════════════════════════════════════════
# FieldMapping 测试
# ══════════════════════════════════════════════════════════════════════════════

class TestFieldMapping:
    """FieldMapping 测试"""
    
    def test_creation(self):
        """测试创建"""
        result = FieldMapping(
            business_term="销售额",
            technical_field="sales_amount",
            confidence=0.95,
            mapping_source="rag_direct",
        )
        assert result.business_term == "销售额"
        assert result.technical_field == "sales_amount"
        assert result.confidence == 0.95
        assert result.mapping_source == "rag_direct"
        assert result.reasoning is None
        assert result.alternatives is None
        assert result.latency_ms == 0
    
    def test_with_alternatives(self):
        """测试带备选项"""
        result = FieldMapping(
            business_term="金额",
            technical_field="sales_amount",
            confidence=0.7,
            mapping_source="rag_llm_fallback",
            reasoning="根据上下文选择销售额",
            alternatives=[
                {"technical_field": "order_amount", "confidence": 0.6},
                {"technical_field": "total_amount", "confidence": 0.5},
            ],
        )
        assert len(result.alternatives) == 2
        assert result.reasoning == "根据上下文选择销售额"


# ══════════════════════════════════════════════════════════════════════════════
# FieldMapperNode 测试
# ══════════════════════════════════════════════════════════════════════════════

class TestFieldMapperNode:
    """FieldMapperNode 测试"""
    
    def test_init_default(self):
        """测试默认初始化"""
        with patch('analytics_assistant.src.agents.field_mapper.node.get_config', return_value={}):
            mapper = FieldMapperNode()
            assert mapper.config is not None
            assert mapper.rag_available is False
            assert mapper.field_count == 0
    
    def test_init_with_config(self):
        """测试带配置初始化"""
        config = FieldMappingConfig(
            high_confidence_threshold=0.95,
            enable_cache=False,
        )
        mapper = FieldMapperNode(config=config)
        assert mapper.config.high_confidence_threshold == 0.95
        assert mapper.config.enable_cache is False
    
    def test_make_cache_key(self):
        """测试缓存键生成"""
        mapper = FieldMapperNode(config=FieldMappingConfig(enable_cache=False))
        
        key1 = mapper._make_cache_key("销售额", "ds-123", None)
        key2 = mapper._make_cache_key("销售额", "ds-123", "measure")
        key3 = mapper._make_cache_key("销售额", "ds-456", None)
        
        # 相同参数应生成相同键
        assert key1 == mapper._make_cache_key("销售额", "ds-123", None)
        # 不同角色过滤应生成不同键
        assert key1 != key2
        # 不同数据源应生成不同键
        assert key1 != key3
    
    def test_set_field_chunks(self, sample_field_chunks):
        """测试设置字段元数据"""
        mapper = FieldMapperNode(config=FieldMappingConfig(enable_cache=False))
        mapper.set_field_chunks(sample_field_chunks)
        assert mapper.field_count == 4
    
    def test_get_stats(self):
        """测试获取统计信息"""
        mapper = FieldMapperNode(config=FieldMappingConfig(enable_cache=False))
        stats = mapper.get_stats()
        assert "total_mappings" in stats
        assert "cache_hits" in stats
        assert "cache_hit_rate" in stats
        assert "fast_path_hits" in stats
        assert "llm_fallback_count" in stats


# ══════════════════════════════════════════════════════════════════════════════
# 辅助函数测试
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractTermsFromSemanticQuery:
    """_extract_terms_from_semantic_query 测试"""
    
    def test_extract_measures(self):
        """测试提取度量"""
        @dataclass
        class MockMeasure:
            field_name: str
        
        @dataclass
        class MockQuery:
            measures: List[MockMeasure]
            dimensions: List = None
            filters: List = None
            computations: List = None
        
        query = MockQuery(measures=[
            MockMeasure(field_name="销售额"),
            MockMeasure(field_name="利润"),
        ])
        
        terms = _extract_terms_from_semantic_query(query)
        assert "销售额" in terms
        assert "利润" in terms
        # 不限制角色
        assert terms["销售额"] is None
        assert terms["利润"] is None
    
    def test_extract_dimensions(self):
        """测试提取维度"""
        @dataclass
        class MockDimension:
            field_name: str
        
        @dataclass
        class MockQuery:
            measures: List = None
            dimensions: List[MockDimension] = None
            filters: List = None
            computations: List = None
        
        query = MockQuery(dimensions=[
            MockDimension(field_name="地区"),
            MockDimension(field_name="产品类别"),
        ])
        
        terms = _extract_terms_from_semantic_query(query)
        assert "地区" in terms
        assert "产品类别" in terms
    
    def test_extract_filters(self):
        """测试提取过滤器"""
        @dataclass
        class MockFilter:
            field_name: str
        
        @dataclass
        class MockQuery:
            measures: List = None
            dimensions: List = None
            filters: List[MockFilter] = None
            computations: List = None
        
        query = MockQuery(filters=[
            MockFilter(field_name="订单日期"),
        ])
        
        terms = _extract_terms_from_semantic_query(query)
        assert "订单日期" in terms
    
    def test_empty_query(self):
        """测试空查询"""
        @dataclass
        class MockQuery:
            measures: List = None
            dimensions: List = None
            filters: List = None
            computations: List = None
        
        query = MockQuery()
        terms = _extract_terms_from_semantic_query(query)
        assert len(terms) == 0
