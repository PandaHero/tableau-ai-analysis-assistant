# -*- coding: utf-8 -*-
"""
维度层级 Schema 单元测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from pydantic import ValidationError


class TestDimensionCategory:
    """测试 DimensionCategory 枚举"""
    
    def test_all_categories_exist(self):
        """测试所有类别枚举值存在"""
        from src.agents.dimension_hierarchy.schemas import DimensionCategory
        
        expected = ["time", "geography", "product", "customer", 
                    "organization", "financial", "channel", "other"]
        actual = [c.value for c in DimensionCategory]
        
        assert set(expected) == set(actual)
    
    def test_category_from_string(self):
        """测试从字符串创建枚举"""
        from src.agents.dimension_hierarchy.schemas import DimensionCategory
        
        assert DimensionCategory("time") == DimensionCategory.TIME
        assert DimensionCategory("geography") == DimensionCategory.GEOGRAPHY
        assert DimensionCategory("other") == DimensionCategory.OTHER
    
    def test_invalid_category_raises(self):
        """测试无效类别抛出异常"""
        from src.agents.dimension_hierarchy.schemas import DimensionCategory
        
        with pytest.raises(ValueError):
            DimensionCategory("invalid_category")


class TestDimensionAttributes:
    """测试 DimensionAttributes 模型"""
    
    def test_valid_attributes(self):
        """测试有效属性创建"""
        from src.agents.dimension_hierarchy.schemas import (
            DimensionAttributes, DimensionCategory
        )
        
        attrs = DimensionAttributes(
            category=DimensionCategory.TIME,
            category_detail="time-year",
            level=1,
            granularity="coarsest",
            level_confidence=0.95,
            reasoning="年份是最粗粒度的时间维度",
        )
        
        assert attrs.category == DimensionCategory.TIME
        assert attrs.category_detail == "time-year"
        assert attrs.level == 1
        assert attrs.granularity == "coarsest"
        assert attrs.level_confidence == 0.95
    
    def test_level_granularity_auto_correction(self):
        """测试 level 和 granularity 自动校正"""
        from src.agents.dimension_hierarchy.schemas import (
            DimensionAttributes, DimensionCategory
        )
        
        # level=1 应该对应 coarsest，即使传入 fine
        attrs = DimensionAttributes(
            category=DimensionCategory.TIME,
            category_detail="time-year",
            level=1,
            granularity="fine",  # 错误的 granularity
            level_confidence=0.9,
            reasoning="test",
        )
        
        # 应该被自动校正为 coarsest
        assert attrs.granularity == "coarsest"
    
    def test_level_range_validation(self):
        """测试 level 范围验证 (1-5)"""
        from src.agents.dimension_hierarchy.schemas import (
            DimensionAttributes, DimensionCategory
        )
        
        # level=0 应该失败
        with pytest.raises(ValidationError):
            DimensionAttributes(
                category=DimensionCategory.TIME,
                category_detail="time-year",
                level=0,
                granularity="coarsest",
                level_confidence=0.9,
                reasoning="test",
            )
        
        # level=6 应该失败
        with pytest.raises(ValidationError):
            DimensionAttributes(
                category=DimensionCategory.TIME,
                category_detail="time-year",
                level=6,
                granularity="finest",
                level_confidence=0.9,
                reasoning="test",
            )
    
    def test_confidence_range_validation(self):
        """测试 confidence 范围验证 (0-1)"""
        from src.agents.dimension_hierarchy.schemas import (
            DimensionAttributes, DimensionCategory
        )
        
        # confidence > 1 应该失败
        with pytest.raises(ValidationError):
            DimensionAttributes(
                category=DimensionCategory.TIME,
                category_detail="time-year",
                level=1,
                granularity="coarsest",
                level_confidence=1.5,
                reasoning="test",
            )
        
        # confidence < 0 应该失败
        with pytest.raises(ValidationError):
            DimensionAttributes(
                category=DimensionCategory.TIME,
                category_detail="time-year",
                level=1,
                granularity="coarsest",
                level_confidence=-0.1,
                reasoning="test",
            )
    
    def test_optional_fields(self):
        """测试可选字段"""
        from src.agents.dimension_hierarchy.schemas import (
            DimensionAttributes, DimensionCategory
        )
        
        attrs = DimensionAttributes(
            category=DimensionCategory.GEOGRAPHY,
            category_detail="geography-country",
            level=1,
            granularity="coarsest",
            level_confidence=0.9,
            reasoning="test",
            parent_dimension=None,
            child_dimension="province",
            sample_values=["中国", "美国", "日本"],
            unique_count=195,
        )
        
        assert attrs.parent_dimension is None
        assert attrs.child_dimension == "province"
        assert attrs.sample_values == ["中国", "美国", "日本"]
        assert attrs.unique_count == 195


class TestDimensionHierarchyResult:
    """测试 DimensionHierarchyResult 模型"""
    
    def test_empty_result(self):
        """测试空结果"""
        from src.agents.dimension_hierarchy.schemas import DimensionHierarchyResult
        
        result = DimensionHierarchyResult(dimension_hierarchy={})
        assert result.dimension_hierarchy == {}
    
    def test_result_with_multiple_fields(self):
        """测试包含多个字段的结果"""
        from src.agents.dimension_hierarchy.schemas import (
            DimensionHierarchyResult, DimensionAttributes, DimensionCategory
        )
        
        attrs1 = DimensionAttributes(
            category=DimensionCategory.TIME,
            category_detail="time-year",
            level=1,
            granularity="coarsest",
            level_confidence=0.95,
            reasoning="年份",
        )
        
        attrs2 = DimensionAttributes(
            category=DimensionCategory.GEOGRAPHY,
            category_detail="geography-province",
            level=2,
            granularity="coarse",
            level_confidence=0.88,
            reasoning="省份",
        )
        
        result = DimensionHierarchyResult(
            dimension_hierarchy={
                "年份": attrs1,
                "省份": attrs2,
            }
        )
        
        assert len(result.dimension_hierarchy) == 2
        assert "年份" in result.dimension_hierarchy
        assert "省份" in result.dimension_hierarchy
        assert result.dimension_hierarchy["年份"].category == DimensionCategory.TIME


class TestLLMDimensionOutput:
    """测试 LLMDimensionOutput 模型"""
    
    def test_to_dimension_hierarchy_result(self):
        """测试转换为 DimensionHierarchyResult"""
        from src.agents.dimension_hierarchy.schemas import (
            LLMDimensionOutput, LLMDimensionItem, DimensionCategory
        )
        
        llm_output = LLMDimensionOutput(
            dimension_hierarchy={
                "年份": LLMDimensionItem(
                    category="time",
                    category_detail="time-year",
                    level=1,
                    granularity="coarsest",
                    level_confidence=0.95,
                    reasoning="年份是时间维度",
                ),
                "城市": LLMDimensionItem(
                    category="geography",
                    category_detail="geography-city",
                    level=3,
                    granularity="medium",
                    level_confidence=0.88,
                ),
            }
        )
        
        result = llm_output.to_dimension_hierarchy_result()
        
        assert len(result.dimension_hierarchy) == 2
        assert result.dimension_hierarchy["年份"].category == DimensionCategory.TIME
        assert result.dimension_hierarchy["城市"].category == DimensionCategory.GEOGRAPHY
        assert result.dimension_hierarchy["城市"].reasoning == "LLM 推断: 城市"  # 默认值
    
    def test_invalid_category_fallback_to_other(self):
        """测试无效类别回退到 OTHER"""
        from src.agents.dimension_hierarchy.schemas import (
            LLMDimensionOutput, LLMDimensionItem, DimensionCategory
        )
        
        llm_output = LLMDimensionOutput(
            dimension_hierarchy={
                "未知字段": LLMDimensionItem(
                    category="invalid_category",  # 无效类别
                    category_detail="unknown",
                    level=3,
                    granularity="medium",
                    level_confidence=0.5,
                ),
            }
        )
        
        result = llm_output.to_dimension_hierarchy_result()
        
        # 应该回退到 OTHER
        assert result.dimension_hierarchy["未知字段"].category == DimensionCategory.OTHER


class TestModuleExports:
    """测试模块导出"""
    
    def test_schema_exports(self):
        """测试 schema 模块导出"""
        from src.agents.dimension_hierarchy.schemas import (
            DimensionCategory,
            DimensionAttributes,
            DimensionHierarchyResult,
            LLMDimensionItem,
            LLMDimensionOutput,
        )
        
        # 验证导出存在
        assert DimensionCategory is not None
        assert DimensionAttributes is not None
        assert DimensionHierarchyResult is not None
        assert LLMDimensionItem is not None
        assert LLMDimensionOutput is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
