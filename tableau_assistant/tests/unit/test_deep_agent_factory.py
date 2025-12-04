"""
DeepAgent 创建器单元测试

测试 deep_agent_factory.py 中的功能：
- DeepAgent 创建
- 工具注入
- Store 集成
- 模型选择逻辑
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

# 测试辅助函数
from tableau_assistant.src.agents.deep_agent_factory import (
    _is_claude_model,
    _get_middleware_config,
    get_default_system_prompt,
    get_middleware_info,
    CLAUDE_MODEL_PREFIXES,
)


class TestIsClaudeModel:
    """测试 Claude 模型检测"""
    
    def test_claude_model_detected(self):
        """测试 Claude 模型被正确识别"""
        assert _is_claude_model("claude-3-5-sonnet-20241022") is True
        assert _is_claude_model("claude-3-opus-20240229") is True
        assert _is_claude_model("claude3-haiku") is True
        assert _is_claude_model("anthropic-claude") is True
    
    def test_non_claude_model(self):
        """测试非 Claude 模型"""
        assert _is_claude_model("gpt-4") is False
        assert _is_claude_model("deepseek-chat") is False
        assert _is_claude_model("qwen-turbo") is False
        assert _is_claude_model("llama-3") is False
    
    def test_empty_model_name(self):
        """测试空模型名称"""
        assert _is_claude_model("") is False
        assert _is_claude_model(None) is False
    
    def test_case_insensitive(self):
        """测试大小写不敏感"""
        assert _is_claude_model("CLAUDE-3-SONNET") is True
        assert _is_claude_model("Claude-3-Opus") is True


class TestGetMiddlewareConfig:
    """测试中间件配置获取"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = _get_middleware_config()
        
        assert "summarization_threshold" in config
        assert "filesystem_size_threshold" in config
        assert "filesystem_base_path" in config
        assert "todo_max_tasks" in config
        assert "hitl_timeout" in config
        assert "patch_max_retries" in config
    
    def test_default_values(self):
        """测试默认值"""
        # 清除可能存在的环境变量
        env_vars = [
            "DEEPAGENT_SUMMARIZATION_THRESHOLD",
            "DEEPAGENT_FILESYSTEM_SIZE_THRESHOLD",
            "DEEPAGENT_FILESYSTEM_BASE_PATH",
            "DEEPAGENT_TODO_MAX_TASKS",
            "DEEPAGENT_HITL_TIMEOUT",
            "DEEPAGENT_PATCH_MAX_RETRIES",
        ]
        
        original_values = {}
        for var in env_vars:
            original_values[var] = os.environ.pop(var, None)
        
        try:
            config = _get_middleware_config()
            
            assert config["summarization_threshold"] == 10
            assert config["filesystem_size_threshold"] == 10 * 1024 * 1024
            assert config["filesystem_base_path"] == "data/agent_files"
            assert config["todo_max_tasks"] == 10
            assert config["hitl_timeout"] == 300
            assert config["patch_max_retries"] == 3
        finally:
            # 恢复环境变量
            for var, value in original_values.items():
                if value is not None:
                    os.environ[var] = value
    
    def test_custom_config_from_env(self):
        """测试从环境变量读取自定义配置"""
        os.environ["DEEPAGENT_SUMMARIZATION_THRESHOLD"] = "20"
        os.environ["DEEPAGENT_TODO_MAX_TASKS"] = "15"
        
        try:
            config = _get_middleware_config()
            
            assert config["summarization_threshold"] == 20
            assert config["todo_max_tasks"] == 15
        finally:
            del os.environ["DEEPAGENT_SUMMARIZATION_THRESHOLD"]
            del os.environ["DEEPAGENT_TODO_MAX_TASKS"]


class TestGetDefaultSystemPrompt:
    """测试默认系统提示词"""
    
    def test_prompt_not_empty(self):
        """测试提示词不为空"""
        prompt = get_default_system_prompt()
        assert prompt is not None
        assert len(prompt) > 0
    
    def test_prompt_contains_key_concepts(self):
        """测试提示词包含关键概念"""
        prompt = get_default_system_prompt()
        
        # 检查关键概念而不是具体工具名
        assert "VizQL" in prompt
        assert "queries" in prompt.lower()
        assert "data" in prompt.lower()
    
    def test_prompt_contains_role(self):
        """测试提示词包含角色说明"""
        prompt = get_default_system_prompt()
        
        assert "Tableau" in prompt
        assert "data analysis" in prompt.lower()


class TestGetMiddlewareInfo:
    """测试中间件信息获取"""
    
    def test_empty_agent(self):
        """测试没有中间件的 agent"""
        mock_agent = Mock()
        del mock_agent.middleware  # 确保没有 middleware 属性
        
        info = get_middleware_info(mock_agent)
        
        assert info["middleware_count"] == 0
        assert info["middleware_types"] == []
        assert info["has_caching"] is False
        assert info["has_summarization"] is False
    
    def test_agent_with_middleware(self):
        """测试有中间件的 agent"""
        # 创建模拟中间件
        class MockCachingMiddleware:
            pass
        
        class MockSummarizationMiddleware:
            pass
        
        mock_agent = Mock()
        mock_agent.middleware = [
            MockCachingMiddleware(),
            MockSummarizationMiddleware()
        ]
        
        info = get_middleware_info(mock_agent)
        
        assert info["middleware_count"] == 2
        assert "MockCachingMiddleware" in info["middleware_types"]
        assert "MockSummarizationMiddleware" in info["middleware_types"]


class TestClaudePrefixes:
    """测试 Claude 前缀"""
    
    def test_claude_prefixes_defined(self):
        """测试 Claude 前缀已定义"""
        assert "claude-" in CLAUDE_MODEL_PREFIXES
        assert "claude3" in CLAUDE_MODEL_PREFIXES
        assert "anthropic" in CLAUDE_MODEL_PREFIXES


class TestCreateTableauDeepAgent:
    """测试 DeepAgent 创建函数"""
    
    @patch('tableau_assistant.src.agents.deep_agent_factory.DEEPAGENTS_AVAILABLE', False)
    def test_raises_when_deepagents_unavailable(self):
        """测试 DeepAgents 不可用时抛出异常"""
        from tableau_assistant.src.agents.deep_agent_factory import create_tableau_deep_agent
        
        with pytest.raises(ImportError) as exc_info:
            create_tableau_deep_agent(tools=[])
        
        assert "DeepAgents framework" in str(exc_info.value)
    
    @patch('tableau_assistant.src.agents.deep_agent_factory.DEEPAGENTS_AVAILABLE', True)
    @patch('tableau_assistant.src.agents.deep_agent_factory.create_deep_agent')
    @patch('tableau_assistant.src.agents.deep_agent_factory._get_model')
    def test_creates_agent_with_tools(self, mock_get_model, mock_create_agent):
        """测试使用工具创建 agent"""
        from tableau_assistant.src.agents.deep_agent_factory import create_tableau_deep_agent
        
        mock_model = Mock()
        mock_get_model.return_value = mock_model
        mock_agent = Mock()
        mock_create_agent.return_value = mock_agent
        
        # 创建模拟工具
        mock_tool = Mock()
        mock_tool.name = "test_tool"
        tools = [mock_tool]
        
        result = create_tableau_deep_agent(
            tools=tools,
            model_name="test-model",
            config={"provider": "local"}
        )
        
        # 验证 create_deep_agent 被调用
        mock_create_agent.assert_called_once()
        call_kwargs = mock_create_agent.call_args[1]
        
        assert call_kwargs["tools"] == tools
        assert call_kwargs["subagents"] == []  # 禁用子代理
        assert result == mock_agent
    
    @patch('tableau_assistant.src.agents.deep_agent_factory.DEEPAGENTS_AVAILABLE', True)
    @patch('tableau_assistant.src.agents.deep_agent_factory.create_deep_agent')
    @patch('tableau_assistant.src.agents.deep_agent_factory._get_model')
    def test_creates_agent_with_store(self, mock_get_model, mock_create_agent):
        """测试使用 Store 创建 agent"""
        from tableau_assistant.src.agents.deep_agent_factory import create_tableau_deep_agent
        
        mock_model = Mock()
        mock_get_model.return_value = mock_model
        mock_agent = Mock()
        mock_create_agent.return_value = mock_agent
        
        mock_store = Mock()
        
        create_tableau_deep_agent(
            tools=[],
            model_name="test-model",
            store=mock_store,
            config={"provider": "local"}
        )
        
        # 验证 store 被传递
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs["store"] == mock_store
    
    @patch('tableau_assistant.src.agents.deep_agent_factory.DEEPAGENTS_AVAILABLE', True)
    @patch('tableau_assistant.src.agents.deep_agent_factory.create_deep_agent')
    @patch('tableau_assistant.src.agents.deep_agent_factory._get_model')
    def test_creates_agent_with_system_prompt(self, mock_get_model, mock_create_agent):
        """测试使用系统提示词创建 agent"""
        from tableau_assistant.src.agents.deep_agent_factory import create_tableau_deep_agent
        
        mock_model = Mock()
        mock_get_model.return_value = mock_model
        mock_agent = Mock()
        mock_create_agent.return_value = mock_agent
        
        system_prompt = "You are a test assistant."
        
        create_tableau_deep_agent(
            tools=[],
            model_name="test-model",
            system_prompt=system_prompt,
            config={"provider": "local"}
        )
        
        # 验证 system_prompt 被传递
        call_kwargs = mock_create_agent.call_args[1]
        assert call_kwargs["system_prompt"] == system_prompt
    
    @patch('tableau_assistant.src.agents.deep_agent_factory.DEEPAGENTS_AVAILABLE', True)
    @patch('tableau_assistant.src.agents.deep_agent_factory._get_model')
    def test_passes_provider_to_get_model(self, mock_get_model):
        """测试 provider 被正确传递给 _get_model"""
        from tableau_assistant.src.agents.deep_agent_factory import create_tableau_deep_agent
        
        mock_model = Mock()
        mock_get_model.return_value = mock_model
        
        # 由于 _get_model 会调用 select_model，这里会抛出异常
        # 但我们可以验证 _get_model 被调用时的参数
        mock_get_model.side_effect = ValueError("Test error")
        
        with pytest.raises(ValueError):
            create_tableau_deep_agent(
                tools=[],
                model_name="test-model",
                config={"provider": "custom_provider"}
            )
        
        # 验证 provider 被传递
        mock_get_model.assert_called_once()
        call_kwargs = mock_get_model.call_args[1]
        assert call_kwargs["provider"] == "custom_provider"
    
    @patch('tableau_assistant.src.agents.deep_agent_factory.DEEPAGENTS_AVAILABLE', True)
    @patch('tableau_assistant.src.agents.deep_agent_factory._get_model')
    @patch('tableau_assistant.src.agents.deep_agent_factory.settings')
    def test_raises_when_model_name_missing(self, mock_settings, mock_get_model):
        """测试缺少模型名称时抛出异常"""
        from tableau_assistant.src.agents.deep_agent_factory import create_tableau_deep_agent
        
        # Mock settings to have empty tooling_llm_model
        mock_settings.tooling_llm_model = ""
        mock_settings.debug = False
        
        # 清除可能的环境变量
        original_model_name = os.environ.pop("MODEL_NAME", None)
        
        try:
            with pytest.raises(ValueError) as exc_info:
                create_tableau_deep_agent(
                    tools=[],
                    model_name=None,
                    config={"provider": "local"}
                )
            
            assert "model_name is required" in str(exc_info.value)
        finally:
            if original_model_name:
                os.environ["MODEL_NAME"] = original_model_name


class TestModelSelection:
    """测试模型选择逻辑"""
    
    def test_select_model_local(self):
        """测试本地模型选择"""
        from tableau_assistant.src.model_manager import select_model
        
        # 设置环境变量
        os.environ["LLM_API_BASE"] = "http://localhost:8000/v1"
        os.environ["LLM_API_KEY"] = "test-key"
        
        try:
            model = select_model(
                provider="local",
                model_name="test-model",
                temperature=0.0
            )
            
            assert model is not None
        finally:
            del os.environ["LLM_API_BASE"]
            del os.environ["LLM_API_KEY"]
    
    def test_select_model_deepseek(self):
        """测试 DeepSeek 模型选择"""
        from tableau_assistant.src.model_manager import select_model
        
        os.environ["DEEPSEEK_API_KEY"] = "test-deepseek-key"
        
        try:
            model = select_model(
                provider="deepseek",
                model_name="deepseek-chat",
                temperature=0.0
            )
            
            assert model is not None
        finally:
            del os.environ["DEEPSEEK_API_KEY"]
    
    def test_select_model_qwen(self):
        """测试 Qwen 模型选择"""
        from tableau_assistant.src.model_manager import select_model
        
        os.environ["QWEN_API_KEY"] = "test-qwen-key"
        os.environ["QWEN_API_BASE"] = "http://localhost:8000/v1"
        
        try:
            model = select_model(
                provider="qwen",
                model_name="qwen-turbo",
                temperature=0.0
            )
            
            assert model is not None
        finally:
            del os.environ["QWEN_API_KEY"]
            del os.environ["QWEN_API_BASE"]
    
    def test_select_model_raises_for_missing_config(self):
        """测试缺少配置时抛出异常"""
        from tableau_assistant.src.model_manager import select_model
        
        # 清除环境变量
        original_key = os.environ.pop("DEEPSEEK_API_KEY", None)
        original_llm_key = os.environ.pop("LLM_API_KEY", None)
        
        try:
            with pytest.raises(ValueError):
                select_model(
                    provider="deepseek",
                    model_name="deepseek-chat"
                )
        finally:
            if original_key:
                os.environ["DEEPSEEK_API_KEY"] = original_key
            if original_llm_key:
                os.environ["LLM_API_KEY"] = original_llm_key
    
    def test_select_model_raises_for_unknown_provider(self):
        """测试未知提供商抛出异常"""
        from tableau_assistant.src.model_manager import select_model
        
        with pytest.raises(ValueError) as exc_info:
            select_model(
                provider="unknown",
                model_name="test-model"
            )
        
        assert "Unknown provider" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
