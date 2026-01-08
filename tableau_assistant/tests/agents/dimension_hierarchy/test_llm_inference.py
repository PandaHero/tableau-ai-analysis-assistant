# -*- coding: utf-8 -*-
"""
LLM 推断集成测试

测试 LLM 维度推断模块的功能：
- 一次性推断（3-5 个字段）
- few-shot 构建
- 结果解析

使用真实 LLM API，不使用 mock。

Requirements: 1.2
"""
import pytest

from tableau_assistant.src.agents.dimension_hierarchy.llm_inference import (
    MAX_FIELDS_PER_INFERENCE,
    infer_dimensions_once,
    _build_few_shot_section,
)
from tableau_assistant.src.agents.dimension_hierarchy.seed_data import (
    get_seed_few_shot_examples,
)
from tableau_assistant.src.agents.dimension_hierarchy.models import (
    DimensionHierarchyResult,
)


# ═══════════════════════════════════════════════════════════
# Few-shot 构建测试
# ═══════════════════════════════════════════════════════════

class TestBuildFewShotSection:
    """Few-shot 构建测试"""
    
    def test_build_few_shot_section_basic(self):
        """测试基本 few-shot 构建"""
        examples = [
            {
                "field_caption": "年",
                "data_type": "integer",
                "category": "time",
                "category_detail": "time-year",
                "level": 1,
                "granularity": "coarsest",
            },
        ]
        
        result = _build_few_shot_section(examples)
        
        assert "Reference Examples from seed patterns:" in result
        assert "年" in result
        assert "time" in result
        assert "```json" in result
    
    def test_build_few_shot_section_empty(self):
        """测试空示例列表"""
        result = _build_few_shot_section([])
        
        assert result == ""
    
    def test_build_few_shot_section_max_examples(self):
        """测试最大示例数限制"""
        examples = get_seed_few_shot_examples(max_per_category=2)  # 12 个
        
        result = _build_few_shot_section(examples, max_examples=3)
        
        # 应该只包含 3 个示例
        # 计算 JSON 对象数量（通过 field_caption 出现次数）
        count = result.count('"field_caption"')
        assert count == 3
    
    def test_build_few_shot_section_from_seed(self):
        """测试从种子数据构建 few-shot"""
        examples = get_seed_few_shot_examples(max_per_category=1)
        
        result = _build_few_shot_section(examples)
        
        # 应该包含 6 个类别的示例
        assert "time" in result
        assert "geography" in result
        assert "product" in result
        assert "customer" in result
        assert "organization" in result
        assert "financial" in result


# ═══════════════════════════════════════════════════════════
# LLM 推断测试（集成测试，使用真实 API）
# ═══════════════════════════════════════════════════════════

class TestInferDimensionsOnce:
    """LLM 推断测试"""
    
    @pytest.mark.asyncio
    async def test_infer_empty_fields(self):
        """测试空字段列表"""
        result = await infer_dimensions_once([])
        
        assert isinstance(result, DimensionHierarchyResult)
        assert result.dimension_hierarchy == {}
    
    @pytest.mark.asyncio
    async def test_infer_single_field(self):
        """测试单个字段推断"""
        fields = [
            {
                "field_name": "year",
                "field_caption": "年份",
                "data_type": "integer",
                "sample_values": ["2020", "2021", "2022", "2023", "2024"],
                "unique_count": 5,
            },
        ]
        
        result = await infer_dimensions_once(fields)
        
        assert isinstance(result, DimensionHierarchyResult)
        assert "year" in result.dimension_hierarchy
        
        attrs = result.dimension_hierarchy["year"]
        assert attrs.category.value == "time"
        assert 1 <= attrs.level <= 5
        assert attrs.level_confidence > 0
    
    @pytest.mark.asyncio
    async def test_infer_multiple_fields(self):
        """测试多个字段推断"""
        fields = [
            {
                "field_name": "year",
                "field_caption": "年",
                "data_type": "integer",
                "sample_values": ["2020", "2021", "2022"],
                "unique_count": 5,
            },
            {
                "field_name": "province",
                "field_caption": "省份",
                "data_type": "string",
                "sample_values": ["北京", "上海", "广东", "浙江"],
                "unique_count": 31,
            },
            {
                "field_name": "category",
                "field_caption": "产品类别",
                "data_type": "string",
                "sample_values": ["电子产品", "服装", "食品"],
                "unique_count": 10,
            },
        ]
        
        result = await infer_dimensions_once(fields)
        
        assert isinstance(result, DimensionHierarchyResult)
        assert len(result.dimension_hierarchy) == 3
        
        # 验证各字段都有结果
        assert "year" in result.dimension_hierarchy
        assert "province" in result.dimension_hierarchy
        assert "category" in result.dimension_hierarchy
        
        # 验证类别推断合理
        assert result.dimension_hierarchy["year"].category.value == "time"
        assert result.dimension_hierarchy["province"].category.value == "geography"
        assert result.dimension_hierarchy["category"].category.value == "product"
    
    @pytest.mark.asyncio
    async def test_infer_without_sample_values(self):
        """测试无样例值的推断"""
        fields = [
            {
                "field_name": "city",
                "field_caption": "城市",
                "data_type": "string",
            },
        ]
        
        result = await infer_dimensions_once(fields)
        
        assert isinstance(result, DimensionHierarchyResult)
        # 即使没有样例值，也应该能推断
        assert "city" in result.dimension_hierarchy
        assert result.dimension_hierarchy["city"].category.value == "geography"
    
    @pytest.mark.asyncio
    async def test_infer_without_few_shot(self):
        """测试不使用 few-shot 的推断"""
        fields = [
            {
                "field_name": "month",
                "field_caption": "月份",
                "data_type": "integer",
                "sample_values": ["1", "2", "3", "4", "5", "6"],
                "unique_count": 12,
            },
        ]
        
        result = await infer_dimensions_once(fields, include_few_shot=False)
        
        assert isinstance(result, DimensionHierarchyResult)
        assert "month" in result.dimension_hierarchy
    
    @pytest.mark.asyncio
    async def test_infer_exceeds_max_fields(self):
        """测试超过最大字段数限制"""
        fields = [
            {
                "field_name": f"field_{i}",
                "field_caption": f"字段{i}",
                "data_type": "string",
            }
            for i in range(MAX_FIELDS_PER_INFERENCE + 1)
        ]
        
        with pytest.raises(ValueError) as exc_info:
            await infer_dimensions_once(fields)
        
        assert "超过最大限制" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_infer_result_has_required_fields(self):
        """测试推断结果包含必需字段"""
        fields = [
            {
                "field_name": "customer_name",
                "field_caption": "客户名称",
                "data_type": "string",
                "sample_values": ["张三", "李四", "王五"],
                "unique_count": 1000,
            },
        ]
        
        result = await infer_dimensions_once(fields)
        
        assert "customer_name" in result.dimension_hierarchy
        attrs = result.dimension_hierarchy["customer_name"]
        
        # 验证必需字段
        assert attrs.category is not None
        assert attrs.category_detail is not None
        assert attrs.level is not None
        assert attrs.granularity is not None
        assert attrs.level_confidence is not None
        assert attrs.reasoning is not None
    
    @pytest.mark.asyncio
    async def test_infer_chinese_and_english_fields(self):
        """测试中英文字段名推断"""
        fields = [
            {
                "field_name": "Order Date",
                "field_caption": "Order Date",
                "data_type": "date",
                "sample_values": ["2024-01-01", "2024-01-02"],
                "unique_count": 365,
            },
            {
                "field_name": "订单日期",
                "field_caption": "订单日期",
                "data_type": "date",
                "sample_values": ["2024-01-01", "2024-01-02"],
                "unique_count": 365,
            },
        ]
        
        result = await infer_dimensions_once(fields)
        
        assert len(result.dimension_hierarchy) == 2
        
        # 两个字段都应该被识别为时间维度
        for field_name in ["Order Date", "订单日期"]:
            assert field_name in result.dimension_hierarchy
            assert result.dimension_hierarchy[field_name].category.value == "time"
