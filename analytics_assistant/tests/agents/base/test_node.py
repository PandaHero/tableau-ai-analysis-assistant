"""
测试 agents/base/node.py 的 get_llm() 函数

测试目标：
1. 验证 get_llm() 正确调用 ModelManager.create_llm()
2. 验证 agent_name 自动选择 temperature
3. 验证 temperature 参数覆盖
4. 验证任务类型路由
5. 验证 JSON Mode 支持
"""
import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from src.agents.base.node import (
    get_llm,
    get_agent_temperature,
    AGENT_TEMPERATURE_CONFIG,
)
from src.infra.ai import TaskType


class TestGetAgentTemperature:
    """测试 get_agent_temperature() 函数"""
    
    def test_semantic_parser_temperature(self):
        """测试语义解析器的 temperature"""
        temp = get_agent_temperature("semantic_parser")
        assert temp == 0.1
    
    def test_insight_temperature(self):
        """测试洞察生成的 temperature"""
        temp = get_agent_temperature("insight")
        assert temp == 0.4
    
    def test_default_temperature(self):
        """测试未知 agent 的默认 temperature"""
        temp = get_agent_temperature("unknown_agent")
        assert temp == 0.2
    
    def test_case_insensitive(self):
        """测试大小写不敏感"""
        temp1 = get_agent_temperature("SEMANTIC_PARSER")
        temp2 = get_agent_temperature("semantic_parser")
        assert temp1 == temp2 == 0.1


class TestGetLLM:
    """测试 get_llm() 函数"""
    
    @patch('src.agents.base.node.get_model_manager')
    def test_basic_call(self, mock_get_manager):
        """测试基本调用"""
        # 设置 mock
        mock_manager = Mock()
        mock_llm = Mock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm()
        
        # 验证
        assert llm == mock_llm
        mock_manager.create_llm.assert_called_once()
    
    @patch('src.agents.base.node.get_model_manager')
    def test_agent_name_temperature(self, mock_get_manager):
        """测试 agent_name 自动选择 temperature"""
        # 设置 mock
        mock_manager = Mock()
        mock_llm = Mock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(agent_name="semantic_parser")
        
        # 验证
        assert llm == mock_llm
        mock_manager.create_llm.assert_called_once_with(
            model_id=None,
            task_type=None,
            temperature=0.1,  # semantic_parser 的 temperature
            enable_json_mode=False,
        )
    
    @patch('src.agents.base.node.get_model_manager')
    def test_explicit_temperature_override(self, mock_get_manager):
        """测试显式 temperature 覆盖 agent_name"""
        # 设置 mock
        mock_manager = Mock()
        mock_llm = Mock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(agent_name="semantic_parser", temperature=0.5)
        
        # 验证
        assert llm == mock_llm
        mock_manager.create_llm.assert_called_once_with(
            model_id=None,
            task_type=None,
            temperature=0.5,  # 显式指定的 temperature
            enable_json_mode=False,
        )
    
    @patch('src.agents.base.node.get_model_manager')
    def test_task_type_routing(self, mock_get_manager):
        """测试任务类型路由"""
        # 设置 mock
        mock_manager = Mock()
        mock_llm = Mock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(task_type=TaskType.SEMANTIC_PARSING)
        
        # 验证
        assert llm == mock_llm
        mock_manager.create_llm.assert_called_once_with(
            model_id=None,
            task_type=TaskType.SEMANTIC_PARSING,
            temperature=None,
            enable_json_mode=False,
        )
    
    @patch('src.agents.base.node.get_model_manager')
    def test_json_mode_enabled(self, mock_get_manager):
        """测试启用 JSON Mode"""
        # 设置 mock
        mock_manager = Mock()
        mock_llm = Mock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
        
        # 验证
        assert llm == mock_llm
        mock_manager.create_llm.assert_called_once_with(
            model_id=None,
            task_type=None,
            temperature=0.1,
            enable_json_mode=True,
        )
    
    @patch('src.agents.base.node.get_model_manager')
    def test_explicit_model_id(self, mock_get_manager):
        """测试显式指定模型 ID"""
        # 设置 mock
        mock_manager = Mock()
        mock_llm = Mock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(model_id="deepseek-reasoner", temperature=0.7)
        
        # 验证
        assert llm == mock_llm
        mock_manager.create_llm.assert_called_once_with(
            model_id="deepseek-reasoner",
            task_type=None,
            temperature=0.7,
            enable_json_mode=False,
        )
    
    @patch('src.agents.base.node.get_model_manager')
    def test_combined_parameters(self, mock_get_manager):
        """测试组合参数"""
        # 设置 mock
        mock_manager = Mock()
        mock_llm = Mock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(
            agent_name="semantic_parser",
            task_type=TaskType.SEMANTIC_PARSING,
            enable_json_mode=True,
            temperature=0.3,
        )
        
        # 验证
        assert llm == mock_llm
        mock_manager.create_llm.assert_called_once_with(
            model_id=None,
            task_type=TaskType.SEMANTIC_PARSING,
            temperature=0.3,  # 显式参数优先
            enable_json_mode=True,
        )
    
    @patch('src.agents.base.node.get_model_manager')
    def test_extra_kwargs_passed_through(self, mock_get_manager):
        """测试额外参数传递"""
        # 设置 mock
        mock_manager = Mock()
        mock_llm = Mock()
        mock_manager.create_llm.return_value = mock_llm
        mock_get_manager.return_value = mock_manager
        
        # 调用
        llm = get_llm(
            agent_name="semantic_parser",
            max_tokens=2048,
            streaming=True,
        )
        
        # 验证
        assert llm == mock_llm
        mock_manager.create_llm.assert_called_once_with(
            model_id=None,
            task_type=None,
            temperature=0.1,
            enable_json_mode=False,
            max_tokens=2048,
            streaming=True,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
