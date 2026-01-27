# -*- coding: utf-8 -*-
"""
维度模式种子数据单元测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest


class TestSeedPatterns:
    """测试种子数据"""
    
    def test_seed_patterns_exists(self):
        """测试种子数据存在"""
        from src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS
        
        assert SEED_PATTERNS is not None
        assert len(SEED_PATTERNS) > 0
    
    def test_seed_patterns_structure(self):
        """测试种子数据结构"""
        from src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS
        
        required_keys = ["field_caption", "data_type", "category", "category_detail", "level", "granularity"]
        
        for pattern in SEED_PATTERNS:
            for key in required_keys:
                assert key in pattern, f"缺少必需字段: {key}"
    
    def test_seed_patterns_categories(self):
        """测试种子数据包含所有类别"""
        from src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS
        
        categories = set(p["category"] for p in SEED_PATTERNS)
        
        expected_categories = {"time", "geography", "product", "customer", "organization"}
        for cat in expected_categories:
            assert cat in categories, f"缺少类别: {cat}"
    
    def test_seed_patterns_levels(self):
        """测试种子数据层级范围"""
        from src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS
        
        for pattern in SEED_PATTERNS:
            assert 1 <= pattern["level"] <= 5, f"层级超出范围: {pattern['level']}"
    
    def test_seed_patterns_granularity(self):
        """测试种子数据粒度值"""
        from src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS
        
        valid_granularities = {"coarsest", "coarse", "medium", "fine", "finest"}
        
        for pattern in SEED_PATTERNS:
            assert pattern["granularity"] in valid_granularities, \
                f"无效粒度: {pattern['granularity']}"
    
    def test_seed_patterns_level_granularity_consistency(self):
        """测试层级和粒度的一致性"""
        from src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS
        
        level_to_granularity = {
            1: "coarsest",
            2: "coarse",
            3: "medium",
            4: "fine",
            5: "finest",
        }
        
        for pattern in SEED_PATTERNS:
            expected = level_to_granularity[pattern["level"]]
            assert pattern["granularity"] == expected, \
                f"层级 {pattern['level']} 应对应粒度 {expected}，实际为 {pattern['granularity']}"
    
    def test_seed_patterns_chinese_fields(self):
        """测试种子数据包含中文字段"""
        from src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS
        
        chinese_fields = [p for p in SEED_PATTERNS if any('\u4e00' <= c <= '\u9fff' for c in p["field_caption"])]
        
        assert len(chinese_fields) > 0, "应包含中文字段"
    
    def test_seed_patterns_english_fields(self):
        """测试种子数据包含英文字段"""
        from src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS
        
        english_fields = [p for p in SEED_PATTERNS if p["field_caption"].isascii()]
        
        assert len(english_fields) > 0, "应包含英文字段"


class TestGetSeedFewShotExamples:
    """测试 few-shot 示例获取"""
    
    def test_get_seed_few_shot_examples_default(self):
        """测试默认参数获取 few-shot 示例"""
        from src.agents.dimension_hierarchy.seed_data import get_seed_few_shot_examples
        
        examples = get_seed_few_shot_examples()
        
        assert len(examples) > 0
    
    def test_get_seed_few_shot_examples_structure(self):
        """测试 few-shot 示例结构"""
        from src.agents.dimension_hierarchy.seed_data import get_seed_few_shot_examples
        
        examples = get_seed_few_shot_examples()
        
        required_keys = ["field_caption", "data_type", "category", "category_detail", "level", "granularity"]
        
        for ex in examples:
            for key in required_keys:
                assert key in ex, f"缺少必需字段: {key}"
            # 不应包含 reasoning 字段
            assert "reasoning" not in ex
    
    def test_get_seed_few_shot_examples_specific_categories(self):
        """测试指定类别获取 few-shot 示例"""
        from src.agents.dimension_hierarchy.seed_data import get_seed_few_shot_examples
        
        examples = get_seed_few_shot_examples(categories=["time", "geography"])
        
        categories = set(ex["category"] for ex in examples)
        
        assert categories <= {"time", "geography"}
    
    def test_get_seed_few_shot_examples_max_per_category(self):
        """测试每类别最大数量限制"""
        from src.agents.dimension_hierarchy.seed_data import get_seed_few_shot_examples
        
        examples = get_seed_few_shot_examples(max_per_category=2)
        
        # 统计每个类别的数量
        category_counts = {}
        for ex in examples:
            cat = ex["category"]
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        for cat, count in category_counts.items():
            assert count <= 2, f"类别 {cat} 超过最大数量限制"
    
    def test_get_seed_few_shot_examples_single_category(self):
        """测试单个类别获取"""
        from src.agents.dimension_hierarchy.seed_data import get_seed_few_shot_examples
        
        examples = get_seed_few_shot_examples(categories=["time"], max_per_category=3)
        
        for ex in examples:
            assert ex["category"] == "time"
    
    def test_get_seed_few_shot_examples_empty_category(self):
        """测试空类别列表"""
        from src.agents.dimension_hierarchy.seed_data import get_seed_few_shot_examples
        
        examples = get_seed_few_shot_examples(categories=[])
        
        assert examples == []
    
    def test_get_seed_few_shot_examples_nonexistent_category(self):
        """测试不存在的类别"""
        from src.agents.dimension_hierarchy.seed_data import get_seed_few_shot_examples
        
        examples = get_seed_few_shot_examples(categories=["nonexistent"])
        
        assert examples == []


class TestSeedDataModuleExports:
    """测试模块导出"""
    
    def test_seed_data_module_exports(self):
        """测试 seed_data 模块导出"""
        from src.agents.dimension_hierarchy.seed_data import (
            SEED_PATTERNS,
            get_seed_few_shot_examples,
        )
        
        assert SEED_PATTERNS is not None
        assert callable(get_seed_few_shot_examples)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
