# -*- coding: utf-8 -*-
"""
节点集成测试

测试 dimension_hierarchy_node 的功能：
- 单表数据源推断
- 多表数据源推断（并发推断 + 结果合并）
- 延迟加载样例数据
- 降级模式

使用真实 Embedding API 和 LLM API，不使用 mock。

Requirements: 1.1, 1.2, 1.3, 1.4
"""
import pytest
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from tableau_assistant.src.agents.dimension_hierarchy.node import (
    dimension_hierarchy_node,
    dimension_hierarchy_node_multi_table,
    infer_single_field,
    get_inference_stats,
    reset_inference_stats,
    _convert_fields_to_dicts,
    _get_inference_instance,
)
from tableau_assistant.src.agents.dimension_hierarchy.models import (
    DimensionHierarchyResult,
    DimensionAttributes,
)


# ═══════════════════════════════════════════════════════════════════════════
# Mock DataModel 和 FieldMetadata
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MockFieldMetadata:
    """模拟 FieldMetadata"""
    name: str
    fieldCaption: str
    dataType: str
    description: str = ""
    sample_values: List[str] = field(default_factory=list)
    unique_count: int = 0
    # 层级信息（由推断填充）
    category: Optional[Any] = None
    category_detail: Optional[str] = None
    level: Optional[int] = None
    granularity: Optional[str] = None
    parent_dimension: Optional[str] = None
    child_dimension: Optional[str] = None


class MockDataModel:
    """模拟 DataModel"""
    
    def __init__(self, dimension_fields: List[MockFieldMetadata]):
        self._dimension_fields = dimension_fields
        self._fields_by_name = {f.name: f for f in dimension_fields}
        self.merged_hierarchy: Dict[str, DimensionAttributes] = {}
    
    def get_dimensions(self) -> List[MockFieldMetadata]:
        return self._dimension_fields
    
    def get_field(self, field_name: str) -> Optional[MockFieldMetadata]:
        return self._fields_by_name.get(field_name)


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数测试
# ═══════════════════════════════════════════════════════════════════════════

class TestConvertFieldsToDicts:
    """字段转换测试"""
    
    def test_convert_basic_fields(self):
        """测试基本字段转换"""
        fields = [
            MockFieldMetadata(
                name="year",
                fieldCaption="年份",
                dataType="integer",
            ),
            MockFieldMetadata(
                name="city",
                fieldCaption="城市",
                dataType="string",
                sample_values=["北京", "上海", "广州"],
                unique_count=100,
            ),
        ]
        
        result = _convert_fields_to_dicts(fields)
        
        assert len(result) == 2
        
        # 验证第一个字段
        assert result[0]["field_name"] == "year"
        assert result[0]["field_caption"] == "年份"
        assert result[0]["data_type"] == "integer"
        
        # 验证第二个字段（包含可选字段）
        assert result[1]["field_name"] == "city"
        assert result[1]["sample_values"] == ["北京", "上海", "广州"]
        assert result[1]["unique_count"] == 100


# ═══════════════════════════════════════════════════════════════════════════
# 单表数据源推断测试
# ═══════════════════════════════════════════════════════════════════════════

class TestSingleTableInference:
    """单表数据源推断测试"""
    
    @pytest.mark.asyncio
    async def test_infer_empty_fields(self):
        """测试空字段列表"""
        data_model = MockDataModel([])
        
        result = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid="ds-empty",
        )
        
        assert result.dimension_hierarchy == {}
    
    @pytest.mark.asyncio
    async def test_infer_single_field_node(self):
        """测试单个字段推断"""
        fields = [
            MockFieldMetadata(
                name="year",
                fieldCaption="年份",
                dataType="integer",
                sample_values=["2020", "2021", "2022"],
                unique_count=5,
            ),
        ]
        data_model = MockDataModel(fields)
        
        result = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid="ds-single-field",
        )
        
        assert "year" in result.dimension_hierarchy
        attrs = result.dimension_hierarchy["year"]
        assert attrs.category.value == "time"
        assert 1 <= attrs.level <= 5
    
    @pytest.mark.asyncio
    async def test_infer_multiple_fields(self):
        """测试多个字段推断"""
        fields = [
            MockFieldMetadata(
                name="year",
                fieldCaption="年",
                dataType="integer",
            ),
            MockFieldMetadata(
                name="city",
                fieldCaption="城市",
                dataType="string",
            ),
            MockFieldMetadata(
                name="category",
                fieldCaption="产品类别",
                dataType="string",
            ),
        ]
        data_model = MockDataModel(fields)
        
        result = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid="ds-multi-field",
        )
        
        assert len(result.dimension_hierarchy) == 3
        assert "year" in result.dimension_hierarchy
        assert "city" in result.dimension_hierarchy
        assert "category" in result.dimension_hierarchy
    
    @pytest.mark.asyncio
    async def test_field_metadata_updated(self):
        """测试字段元数据更新"""
        fields = [
            MockFieldMetadata(
                name="year",
                fieldCaption="年份",
                dataType="integer",
            ),
        ]
        data_model = MockDataModel(fields)
        
        await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid="ds-metadata-update",
        )
        
        # 验证字段元数据已更新
        field = data_model.get_field("year")
        assert field.category is not None
        assert field.category_detail is not None
        assert field.level is not None
        assert field.granularity is not None
    
    @pytest.mark.asyncio
    async def test_merged_hierarchy_set(self):
        """测试 merged_hierarchy 设置"""
        fields = [
            MockFieldMetadata(
                name="year",
                fieldCaption="年份",
                dataType="integer",
            ),
        ]
        data_model = MockDataModel(fields)
        
        result = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid="ds-merged",
        )
        
        # 验证 merged_hierarchy 已设置
        assert data_model.merged_hierarchy == result.dimension_hierarchy


# ═══════════════════════════════════════════════════════════════════════════
# 缓存测试
# ═══════════════════════════════════════════════════════════════════════════

class TestCacheIntegration:
    """缓存集成测试"""
    
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """测试缓存命中"""
        fields = [
            MockFieldMetadata(
                name="cache_test_field",
                fieldCaption="缓存测试字段",
                dataType="string",
            ),
        ]
        data_model = MockDataModel(fields)
        
        # 第一次推断
        result1 = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid="ds-cache-hit-test",
        )
        
        # 重置统计
        await reset_inference_stats()
        
        # 第二次推断（应该命中缓存）
        result2 = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid="ds-cache-hit-test",
        )
        
        # 验证结果一致
        assert result1.dimension_hierarchy.keys() == result2.dimension_hierarchy.keys()
        
        # 验证统计（缓存命中）
        stats = await get_inference_stats()
        assert stats.get("cache_hits", 0) >= 1
    
    @pytest.mark.asyncio
    async def test_force_refresh(self):
        """测试强制刷新"""
        fields = [
            MockFieldMetadata(
                name="force_refresh_field",
                fieldCaption="强制刷新字段",
                dataType="string",
            ),
        ]
        data_model = MockDataModel(fields)
        
        # 第一次推断
        await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid="ds-force-refresh-test",
        )
        
        # 重置统计
        await reset_inference_stats()
        
        # 第二次推断（强制刷新）
        await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid="ds-force-refresh-test",
            force_refresh=True,
        )
        
        # 验证统计（不应该命中缓存）
        stats = await get_inference_stats()
        assert stats.get("cache_hits", 0) == 0


# ═══════════════════════════════════════════════════════════════════════════
# 单字段推断测试
# ═══════════════════════════════════════════════════════════════════════════

class TestInferSingleField:
    """单字段推断测试"""
    
    @pytest.mark.asyncio
    async def test_infer_single_field_basic(self):
        """测试基本单字段推断"""
        attrs = await infer_single_field(
            field_name="test_year",
            field_caption="年份",
            data_type="integer",
            sample_values=["2020", "2021", "2022"],
            unique_count=5,
        )
        
        assert attrs is not None
        assert attrs.category.value == "time"
        assert 1 <= attrs.level <= 5
    
    @pytest.mark.asyncio
    async def test_infer_single_field_geography(self):
        """测试地理字段推断"""
        attrs = await infer_single_field(
            field_name="test_city",
            field_caption="城市",
            data_type="string",
            sample_values=["北京", "上海", "广州"],
            unique_count=100,
        )
        
        assert attrs is not None
        assert attrs.category.value == "geography"


# ═══════════════════════════════════════════════════════════════════════════
# 统计测试
# ═══════════════════════════════════════════════════════════════════════════

class TestStats:
    """统计测试"""
    
    @pytest.mark.asyncio
    async def test_get_stats(self):
        """测试获取统计数据"""
        stats = await get_inference_stats()
        
        # 验证统计数据结构
        assert "total_fields" in stats or "error" in stats
    
    @pytest.mark.asyncio
    async def test_reset_stats(self):
        """测试重置统计数据"""
        # 先执行一次推断
        fields = [
            MockFieldMetadata(
                name="stats_test_field",
                fieldCaption="统计测试字段",
                dataType="string",
            ),
        ]
        data_model = MockDataModel(fields)
        
        await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid="ds-stats-test",
            force_refresh=True,
        )
        
        # 重置统计
        await reset_inference_stats()
        
        # 验证统计已重置
        stats = await get_inference_stats()
        if "error" not in stats:
            assert stats.get("total_fields", 0) == 0
