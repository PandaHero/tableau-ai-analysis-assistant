# -*- coding: utf-8 -*-
"""
Agent 基础模块单元测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestAgentTemperature:
    """测试 Agent Temperature 配置"""
    
    def test_get_agent_temperature_semantic_parser(self):
        """测试 semantic_parser 的 temperature"""
        from src.agents.base.node import get_agent_temperature
        
        temp = get_agent_temperature("semantic_parser")
        assert temp == 0.1
    
    def test_get_agent_temperature_insight(self):
        """测试 insight 的 temperature"""
        from src.agents.base.node import get_agent_temperature
        
        temp = get_agent_temperature("insight")
        assert temp == 0.4
    
    def test_get_agent_temperature_default(self):
        """测试未知 agent 使用默认 temperature"""
        from src.agents.base.node import get_agent_temperature
        
        temp = get_agent_temperature("unknown_agent")
        assert temp == 0.2  # default
    
    def test_get_agent_temperature_case_insensitive(self):
        """测试大小写不敏感"""
        from src.agents.base.node import get_agent_temperature
        
        temp1 = get_agent_temperature("SEMANTIC_PARSER")
        temp2 = get_agent_temperature("Semantic_Parser")
        
        assert temp1 == 0.1
        assert temp2 == 0.1


class TestGetLLM:
    """测试 get_llm 函数"""
    
    @patch('src.agents.base.node.get_model_manager')
    def test_get_llm_with_agent_name(self, mock_get_manager):
        """测试使用 agent_name 获取 LLM"""
        from src.agents.base.node import get_llm
        
        # 设置 mock
        mock_manager = MagicMock()
        mock_llm = MagicMock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(agent_name="semantic_parser")
        
        # 验证
        mock_manager.create_llm.assert_called_once()
        call_kwargs = mock_manager.create_llm.call_args[1]
        assert call_kwargs['temperature'] == 0.1  # semantic_parser 的 temperature
        assert llm == mock_llm
    
    @patch('src.agents.base.node.get_model_manager')
    def test_get_llm_with_explicit_temperature(self, mock_get_manager):
        """测试显式指定 temperature（覆盖 agent_name）"""
        from src.agents.base.node import get_llm
        
        # 设置 mock
        mock_manager = MagicMock()
        mock_llm = MagicMock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用（显式指定 temperature=0.5，应覆盖 semantic_parser 的 0.1）
        llm = get_llm(agent_name="semantic_parser", temperature=0.5)
        
        # 验证
        call_kwargs = mock_manager.create_llm.call_args[1]
        assert call_kwargs['temperature'] == 0.5  # 显式指定的值
    
    @patch('src.agents.base.node.get_model_manager')
    def test_get_llm_with_task_type(self, mock_get_manager):
        """测试使用 task_type 获取 LLM"""
        from src.agents.base.node import get_llm, TaskType
        
        # 设置 mock
        mock_manager = MagicMock()
        mock_llm = MagicMock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(task_type=TaskType.SEMANTIC_PARSING)
        
        # 验证
        call_kwargs = mock_manager.create_llm.call_args[1]
        assert call_kwargs['task_type'] == TaskType.SEMANTIC_PARSING
    
    @patch('src.agents.base.node.get_model_manager')
    def test_get_llm_with_json_mode(self, mock_get_manager):
        """测试启用 JSON Mode"""
        from src.agents.base.node import get_llm
        
        # 设置 mock
        mock_manager = MagicMock()
        mock_llm = MagicMock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
        
        # 验证
        call_kwargs = mock_manager.create_llm.call_args[1]
        assert call_kwargs['enable_json_mode'] is True
    
    @patch('src.agents.base.node.get_model_manager')
    def test_get_llm_with_model_id(self, mock_get_manager):
        """测试显式指定 model_id"""
        from src.agents.base.node import get_llm
        
        # 设置 mock
        mock_manager = MagicMock()
        mock_llm = MagicMock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(model_id="deepseek-reasoner", temperature=0.7)
        
        # 验证
        call_kwargs = mock_manager.create_llm.call_args[1]
        assert call_kwargs['model_id'] == "deepseek-reasoner"
        assert call_kwargs['temperature'] == 0.7


class TestModuleExports:
    """测试模块导出"""
    
    def test_base_module_exports(self):
        """测试 agents.base 模块导出"""
        from src.agents.base import (
            get_llm,
            get_agent_temperature,
            stream_llm,
            stream_llm_structured,
            TaskType,
        )
        
        # 验证导出存在
        assert callable(get_llm)
        assert callable(get_agent_temperature)
        assert callable(stream_llm)
        assert callable(stream_llm_structured)
        assert hasattr(TaskType, 'SEMANTIC_PARSING')
    
    def test_task_type_values(self):
        """测试 TaskType 枚举值"""
        from src.agents.base import TaskType
        
        # 验证常用任务类型
        assert TaskType.SEMANTIC_PARSING.value == "semantic_parsing"
        assert TaskType.FIELD_MAPPING.value == "field_mapping"
        assert TaskType.INSIGHT_GENERATION.value == "insight_generation"
        assert TaskType.REASONING.value == "reasoning"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
