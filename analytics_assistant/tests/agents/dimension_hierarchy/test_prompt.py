# -*- coding: utf-8 -*-
"""
维度层级推断 Prompt 单元测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import json


class TestSystemPrompt:
    """测试系统提示"""
    
    def test_system_prompt_exists(self):
        """测试系统提示存在"""
        from src.agents.dimension_hierarchy.prompt import SYSTEM_PROMPT
        
        assert SYSTEM_PROMPT is not None
        assert len(SYSTEM_PROMPT) > 0
    
    def test_system_prompt_contains_task_description(self):
        """测试系统提示包含任务描述"""
        from src.agents.dimension_hierarchy.prompt import SYSTEM_PROMPT
        
        assert "维度层级" in SYSTEM_PROMPT or "dimension" in SYSTEM_PROMPT.lower()
    
    def test_system_prompt_contains_categories(self):
        """测试系统提示包含类别说明"""
        from src.agents.dimension_hierarchy.prompt import SYSTEM_PROMPT
        
        categories = ["time", "geography", "product", "customer", "organization"]
        for cat in categories:
            assert cat in SYSTEM_PROMPT
    
    def test_system_prompt_contains_level_description(self):
        """测试系统提示包含层级说明"""
        from src.agents.dimension_hierarchy.prompt import SYSTEM_PROMPT
        
        assert "Level 1" in SYSTEM_PROMPT or "level" in SYSTEM_PROMPT.lower()
        assert "coarsest" in SYSTEM_PROMPT or "finest" in SYSTEM_PROMPT
    
    def test_get_system_prompt(self):
        """测试 get_system_prompt 函数"""
        from src.agents.dimension_hierarchy.prompt import get_system_prompt, SYSTEM_PROMPT
        
        result = get_system_prompt()
        assert result == SYSTEM_PROMPT


class TestBuildUserPrompt:
    """测试用户提示构建"""
    
    def test_build_user_prompt_basic(self):
        """测试基本用户提示构建"""
        from src.agents.dimension_hierarchy.prompt import build_user_prompt
        
        fields = [
            {"field_caption": "年份", "data_type": "integer"},
            {"field_caption": "城市", "data_type": "string"},
        ]
        
        prompt = build_user_prompt(fields, include_few_shot=False)
        
        assert "年份" in prompt
        assert "城市" in prompt
        assert "待分析字段" in prompt
    
    def test_build_user_prompt_with_few_shot(self):
        """测试包含 few-shot 示例的用户提示"""
        from src.agents.dimension_hierarchy.prompt import build_user_prompt
        
        fields = [{"field_caption": "年份", "data_type": "integer"}]
        
        prompt = build_user_prompt(fields, include_few_shot=True)
        
        assert "参考示例" in prompt
        assert "待分析字段" in prompt
    
    def test_build_user_prompt_without_few_shot(self):
        """测试不包含 few-shot 示例的用户提示"""
        from src.agents.dimension_hierarchy.prompt import build_user_prompt
        
        fields = [{"field_caption": "年份", "data_type": "integer"}]
        
        prompt = build_user_prompt(fields, include_few_shot=False)
        
        assert "参考示例" not in prompt
        assert "待分析字段" in prompt
    
    def test_build_user_prompt_with_sample_values(self):
        """测试包含样例值的用户提示"""
        from src.agents.dimension_hierarchy.prompt import build_user_prompt
        
        fields = [{
            "field_caption": "城市",
            "data_type": "string",
            "sample_values": ["北京", "上海", "广州", "深圳", "杭州", "成都"],
        }]
        
        prompt = build_user_prompt(fields, include_few_shot=False)
        
        # 应该只包含前 5 个样例值
        assert "北京" in prompt
        assert "上海" in prompt
    
    def test_build_user_prompt_with_unique_count(self):
        """测试包含唯一值数量的用户提示"""
        from src.agents.dimension_hierarchy.prompt import build_user_prompt
        
        fields = [{
            "field_caption": "城市",
            "data_type": "string",
            "unique_count": 100,
        }]
        
        prompt = build_user_prompt(fields, include_few_shot=False)
        
        assert "100" in prompt
    
    def test_build_user_prompt_empty_fields(self):
        """测试空字段列表"""
        from src.agents.dimension_hierarchy.prompt import build_user_prompt
        
        prompt = build_user_prompt([], include_few_shot=False)
        
        assert "待分析字段" in prompt
        assert "[]" in prompt
    
    def test_build_user_prompt_uses_caption_fallback(self):
        """测试使用 caption 作为 field_caption 的回退"""
        from src.agents.dimension_hierarchy.prompt import build_user_prompt
        
        fields = [{"caption": "年份", "data_type": "integer"}]
        
        prompt = build_user_prompt(fields, include_few_shot=False)
        
        assert "年份" in prompt


class TestBuildDimensionInferencePrompt:
    """测试完整 prompt 构建"""
    
    def test_build_dimension_inference_prompt(self):
        """测试完整 prompt 构建"""
        from src.agents.dimension_hierarchy.prompt import (
            build_dimension_inference_prompt, SYSTEM_PROMPT
        )
        
        fields = [{"field_caption": "年份", "data_type": "integer"}]
        
        prompt = build_dimension_inference_prompt(fields, include_few_shot=False)
        
        # 应该包含系统提示和用户提示
        assert SYSTEM_PROMPT in prompt
        assert "年份" in prompt
        assert "待分析字段" in prompt
    
    def test_build_dimension_inference_prompt_with_few_shot(self):
        """测试包含 few-shot 的完整 prompt"""
        from src.agents.dimension_hierarchy.prompt import build_dimension_inference_prompt
        
        fields = [{"field_caption": "年份", "data_type": "integer"}]
        
        prompt = build_dimension_inference_prompt(fields, include_few_shot=True)
        
        assert "参考示例" in prompt


class TestPromptModuleExports:
    """测试模块导出"""
    
    def test_prompt_module_exports(self):
        """测试 prompt 模块导出"""
        from src.agents.dimension_hierarchy.prompt import (
            SYSTEM_PROMPT,
            build_user_prompt,
            build_dimension_inference_prompt,
            get_system_prompt,
        )
        
        assert SYSTEM_PROMPT is not None
        assert callable(build_user_prompt)
        assert callable(build_dimension_inference_prompt)
        assert callable(get_system_prompt)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
