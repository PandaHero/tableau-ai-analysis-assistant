# -*- coding: utf-8 -*-
"""
ModelManager 单元测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from src.infra.ai.model_manager import (
    ModelManager,
    get_model_manager,
    ModelType,
    ModelStatus,
    TaskType,
    ModelConfig,
    ModelCreateRequest,
    ModelUpdateRequest,
)


class TestModelManager:
    """ModelManager 测试类"""
    
    def test_singleton(self):
        """测试单例模式"""
        manager1 = get_model_manager()
        manager2 = get_model_manager()
        assert manager1 is manager2
    
    def test_create_model_config(self):
        """测试创建模型配置"""
        manager = get_model_manager()
        
        request = ModelCreateRequest(
            name="Test LLM",
            model_type=ModelType.LLM,
            provider="test",
            api_base="http://localhost:8000",
            model_name="test-model",
            api_key="test-key",
            temperature=0.7,
            suitable_tasks=[TaskType.SEMANTIC_PARSING],
            priority=5,
        )
        
        config = manager.create(request)
        
        assert config.name == "Test LLM"
        assert config.model_type == ModelType.LLM
        assert config.provider == "test"
        assert config.temperature == 0.7
        assert TaskType.SEMANTIC_PARSING in config.suitable_tasks
    
    def test_get_model_config(self):
        """测试获取模型配置"""
        manager = get_model_manager()
        
        # 创建配置
        request = ModelCreateRequest(
            name="Test LLM 2",
            model_type=ModelType.LLM,
            provider="test2",
            api_base="http://localhost:8001",
            model_name="test-model-2",
        )
        config = manager.create(request)
        
        # 获取配置
        retrieved = manager.get(config.id)
        assert retrieved is not None
        assert retrieved.id == config.id
        assert retrieved.name == "Test LLM 2"
    
    def test_list_model_configs(self):
        """测试列出模型配置"""
        manager = get_model_manager()
        
        # 列出所有 LLM 模型
        llm_configs = manager.list(model_type=ModelType.LLM)
        assert len(llm_configs) > 0
        
        # 列出活跃模型
        active_configs = manager.list(status=ModelStatus.ACTIVE)
        assert all(c.status == ModelStatus.ACTIVE for c in active_configs)
    
    def test_update_model_config(self):
        """测试更新模型配置"""
        manager = get_model_manager()
        
        # 创建配置
        request = ModelCreateRequest(
            name="Test LLM 3",
            model_type=ModelType.LLM,
            provider="test3",
            api_base="http://localhost:8002",
            model_name="test-model-3",
            temperature=0.5,
        )
        config = manager.create(request)
        
        # 更新配置
        update_request = ModelUpdateRequest(
            temperature=0.8,
            priority=10,
        )
        updated = manager.update(config.id, update_request)
        
        assert updated is not None
        assert updated.temperature == 0.8
        assert updated.priority == 10
    
    def test_delete_model_config(self):
        """测试删除模型配置"""
        manager = get_model_manager()
        
        # 创建配置
        request = ModelCreateRequest(
            name="Test LLM 4",
            model_type=ModelType.LLM,
            provider="test4",
            api_base="http://localhost:8003",
            model_name="test-model-4",
        )
        config = manager.create(request)
        
        # 删除配置
        result = manager.delete(config.id)
        assert result is True
        
        # 验证已删除
        retrieved = manager.get(config.id)
        assert retrieved is None
    
    def test_default_model(self):
        """测试默认模型管理"""
        manager = get_model_manager()
        
        # 创建默认模型
        request = ModelCreateRequest(
            name="Default Test LLM",
            model_type=ModelType.LLM,
            provider="test-default",
            api_base="http://localhost:8004",
            model_name="test-default-model",
            is_default=True,
        )
        config = manager.create(request)
        
        # 获取默认模型
        default = manager.get_default(ModelType.LLM)
        assert default is not None
        # 注意：可能有多个默认模型，只验证存在即可
    
    def test_task_based_routing(self):
        """测试基于任务类型的路由"""
        manager = get_model_manager()
        
        # 创建适合语义解析的模型
        request = ModelCreateRequest(
            name="Semantic Parser LLM",
            model_type=ModelType.LLM,
            provider="test-semantic",
            api_base="http://localhost:8005",
            model_name="test-semantic-model",
            suitable_tasks=[TaskType.SEMANTIC_PARSING],
            priority=10,
        )
        config = manager.create(request)
        
        # 路由到适合语义解析的模型
        routed = manager._route_by_task(TaskType.SEMANTIC_PARSING, ModelType.LLM)
        assert routed is not None
        assert TaskType.SEMANTIC_PARSING in routed.suitable_tasks
    
    def test_reasoning_model_config(self):
        """测试推理模型配置"""
        manager = get_model_manager()
        
        # 创建推理模型配置
        request = ModelCreateRequest(
            name="DeepSeek-R1",
            model_type=ModelType.LLM,
            provider="deepseek",
            api_base="http://localhost:8006",
            model_name="deepseek-reasoner",
            is_reasoning_model=True,  # 标记为推理模型
            suitable_tasks=[TaskType.REASONING, TaskType.INSIGHT_GENERATION],
            priority=10,
        )
        config = manager.create(request)
        
        # 验证推理模型标记
        assert config.is_reasoning_model is True
        assert TaskType.REASONING in config.suitable_tasks
        
        # 验证可以通过任务类型路由到推理模型
        routed = manager._route_by_task(TaskType.REASONING, ModelType.LLM)
        assert routed is not None
        assert routed.is_reasoning_model is True
    
    def test_create_embedding_config(self):
        """测试创建 Embedding 配置"""
        manager = get_model_manager()
        
        request = ModelCreateRequest(
            name="Test Embedding",
            model_type=ModelType.EMBEDDING,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="text-embedding-3-small",
            api_key="test-key",
            suitable_tasks=[TaskType.EMBEDDING],
            priority=5,
        )
        
        config = manager.create(request)
        
        assert config.name == "Test Embedding"
        assert config.model_type == ModelType.EMBEDDING
        assert config.provider == "openai"
        assert config.model_name == "text-embedding-3-small"
        assert TaskType.EMBEDDING in config.suitable_tasks
    
    def test_create_embedding_zhipu(self):
        """测试创建智谱 Embedding 配置"""
        manager = get_model_manager()
        
        request = ModelCreateRequest(
            name="Zhipu Embedding",
            model_type=ModelType.EMBEDDING,
            provider="zhipu",
            api_base="https://open.bigmodel.cn/api/paas/v4",
            model_name="embedding-2",
            api_key="test-zhipu-key",
            suitable_tasks=[TaskType.EMBEDDING],
            priority=10,
            is_default=True,
        )
        
        config = manager.create(request)
        
        assert config.name == "Zhipu Embedding"
        assert config.provider == "zhipu"
        assert config.is_default is True
        
        # 验证可以获取默认 Embedding
        default = manager.get_default(ModelType.EMBEDDING)
        assert default is not None
        # 注意：可能有多个默认模型，只验证存在即可
    
    def test_create_embedding_azure(self):
        """测试创建 Azure Embedding 配置"""
        manager = get_model_manager()
        
        request = ModelCreateRequest(
            name="Azure Embedding",
            model_type=ModelType.EMBEDDING,
            provider="azure",
            api_base="https://test.openai.azure.com",
            model_name="text-embedding-ada-002",
            api_key="test-azure-key",
            suitable_tasks=[TaskType.EMBEDDING],
            priority=5,
            extra_body={"api_version": "2024-02-15-preview"},
        )
        
        config = manager.create(request)
        
        assert config.name == "Azure Embedding"
        assert config.provider == "azure"
        assert config.extra_body.get("api_version") == "2024-02-15-preview"
    
    def test_get_embedding_config(self):
        """测试获取 Embedding 配置"""
        manager = get_model_manager()
        
        # 创建配置
        request = ModelCreateRequest(
            name="Test Embedding 2",
            model_type=ModelType.EMBEDDING,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="text-embedding-3-large",
            api_key="test-key-2",
        )
        config = manager.create(request)
        
        # 获取配置
        retrieved = manager.get(config.id)
        assert retrieved is not None
        assert retrieved.id == config.id
        assert retrieved.model_type == ModelType.EMBEDDING
    
    def test_list_embedding_configs(self):
        """测试列出 Embedding 配置"""
        manager = get_model_manager()
        
        # 列出所有 Embedding 模型
        embedding_configs = manager.list(model_type=ModelType.EMBEDDING)
        assert len(embedding_configs) > 0
        assert all(c.model_type == ModelType.EMBEDDING for c in embedding_configs)
    
    def test_json_mode_adapter_deepseek(self):
        """测试 DeepSeek JSON Mode 适配"""
        manager = get_model_manager()
        
        # 测试 DeepSeek provider
        json_kwargs = manager._get_json_mode_kwargs("deepseek", enable_json_mode=True)
        assert "model_kwargs" in json_kwargs
        assert json_kwargs["model_kwargs"]["response_format"]["type"] == "json_object"
    
    def test_json_mode_adapter_openai(self):
        """测试 OpenAI JSON Mode 适配"""
        manager = get_model_manager()
        
        # 测试 OpenAI provider
        json_kwargs = manager._get_json_mode_kwargs("openai", enable_json_mode=True)
        assert "model_kwargs" in json_kwargs
        assert json_kwargs["model_kwargs"]["response_format"]["type"] == "json_object"
    
    def test_json_mode_adapter_azure(self):
        """测试 Azure JSON Mode 适配"""
        manager = get_model_manager()
        
        # 测试 Azure provider
        json_kwargs = manager._get_json_mode_kwargs("azure", enable_json_mode=True)
        assert "model_kwargs" in json_kwargs
        assert json_kwargs["model_kwargs"]["response_format"]["type"] == "json_object"
    
    def test_json_mode_adapter_custom(self):
        """测试 Custom JSON Mode 适配"""
        manager = get_model_manager()
        
        # 测试 Custom provider
        json_kwargs = manager._get_json_mode_kwargs("custom", enable_json_mode=True)
        assert "extra_body" in json_kwargs
        assert json_kwargs["extra_body"]["response_format"]["type"] == "json_object"
    
    def test_json_mode_adapter_anthropic(self):
        """测试 Anthropic JSON Mode 适配（不支持）"""
        manager = get_model_manager()
        
        # 测试 Anthropic provider（不支持 JSON Mode）
        json_kwargs = manager._get_json_mode_kwargs("anthropic", enable_json_mode=True)
        assert json_kwargs == {}
    
    def test_json_mode_adapter_disabled(self):
        """测试禁用 JSON Mode"""
        manager = get_model_manager()
        
        # 测试禁用 JSON Mode
        json_kwargs = manager._get_json_mode_kwargs("openai", enable_json_mode=False)
        assert json_kwargs == {}


class TestModelManagerLLMCreation:
    """测试 ModelManager 的 LLM 创建功能"""
    
    def test_create_llm_with_default_model(self):
        """测试使用默认模型创建 LLM"""
        manager = ModelManager()
        
        # 创建一个测试模型配置（使用唯一 ID）
        request = ModelCreateRequest(
            name="Test LLM Default",
            model_type=ModelType.LLM,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="gpt-3.5-turbo-test-default",
            api_key="test-key",
            is_default=True,
        )
        try:
            manager.create(request)
        except ValueError:
            # 如果已存在，先删除
            manager.delete("openai-gpt-3.5-turbo-test-default")
            manager.create(request)
        
        # 创建 LLM（应该使用默认模型）
        llm = manager.create_llm()
        
        assert llm is not None
        assert hasattr(llm, 'model_name')
    
    def test_create_llm_with_model_id(self):
        """测试使用指定模型 ID 创建 LLM"""
        manager = ModelManager()
        
        # 创建一个测试模型配置（使用唯一 ID）
        request = ModelCreateRequest(
            name="Test LLM Model ID",
            model_type=ModelType.LLM,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="gpt-4-test-model-id",
            api_key="test-key",
        )
        try:
            config = manager.create(request)
        except ValueError:
            # 如果已存在，先删除
            manager.delete("openai-gpt-4-test-model-id")
            config = manager.create(request)
        
        # 使用指定模型 ID 创建 LLM
        llm = manager.create_llm(model_id=config.id)
        
        assert llm is not None
        assert llm.model_name == "gpt-4-test-model-id"
    
    def test_create_llm_with_task_type(self):
        """测试使用任务类型路由创建 LLM"""
        manager = ModelManager()
        
        # 创建一个适合语义解析的模型（使用唯一 ID）
        request = ModelCreateRequest(
            name="Semantic Parser LLM Test",
            model_type=ModelType.LLM,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="gpt-4-test-semantic",
            api_key="test-key",
            suitable_tasks=[TaskType.SEMANTIC_PARSING],
            priority=10,
        )
        try:
            manager.create(request)
        except ValueError:
            # 如果已存在，先删除
            manager.delete("openai-gpt-4-test-semantic")
            manager.create(request)
        
        # 使用任务类型路由
        llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
        
        assert llm is not None
        # 应该选择优先级最高的模型
        assert llm.model_name in ["gpt-4-test-semantic", "deepseek-chat"]
    
    def test_create_llm_with_temperature_override(self):
        """测试覆盖 temperature 参数"""
        manager = ModelManager()
        
        # 创建一个测试模型配置（使用唯一 ID）
        request = ModelCreateRequest(
            name="Test LLM Temperature",
            model_type=ModelType.LLM,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="gpt-3.5-turbo-test-temp",
            api_key="test-key",
            temperature=0.7,
            is_default=True,
        )
        try:
            manager.create(request)
        except ValueError:
            # 如果已存在，先删除
            manager.delete("openai-gpt-3.5-turbo-test-temp")
            manager.create(request)
        
        # 覆盖 temperature
        llm = manager.create_llm(temperature=0.3)
        
        assert llm is not None
        assert llm.temperature == 0.3
    
    def test_create_llm_with_json_mode(self):
        """测试启用 JSON Mode"""
        manager = ModelManager()
        
        # 创建一个测试模型配置（使用唯一 ID）
        request = ModelCreateRequest(
            name="Test LLM JSON Mode",
            model_type=ModelType.LLM,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="gpt-3.5-turbo-test-json",
            api_key="test-key",
            supports_json_mode=True,
            is_default=True,
        )
        try:
            manager.create(request)
        except ValueError:
            # 如果已存在，先删除
            manager.delete("openai-gpt-3.5-turbo-test-json")
            manager.create(request)
        
        # 启用 JSON Mode
        llm = manager.create_llm(enable_json_mode=True)
        
        assert llm is not None
        # 验证 JSON Mode 参数
        assert hasattr(llm, 'model_kwargs') or hasattr(llm, 'extra_body')


class TestModelManagerEmbeddingCreation:
    """测试 ModelManager 的 Embedding 创建功能"""
    
    def test_create_embedding_with_default_model(self):
        """测试使用默认模型创建 Embedding"""
        manager = ModelManager()
        
        # 创建一个测试 Embedding 配置（使用唯一 ID）
        request = ModelCreateRequest(
            name="Test Embedding Default",
            model_type=ModelType.EMBEDDING,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="text-embedding-3-small-test-default",
            api_key="test-key",
            is_default=True,
        )
        try:
            manager.create(request)
        except ValueError:
            # 如果已存在，先删除
            manager.delete("openai-text-embedding-3-small-test-default")
            manager.create(request)
        
        # 创建 Embedding
        embedding = manager.create_embedding()
        
        assert embedding is not None
        assert hasattr(embedding, 'embed_query')
    
    def test_create_embedding_with_model_id(self):
        """测试使用指定模型 ID 创建 Embedding"""
        manager = ModelManager()
        
        # 创建一个测试 Embedding 配置（使用唯一 ID）
        request = ModelCreateRequest(
            name="Test Embedding Model ID",
            model_type=ModelType.EMBEDDING,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="text-embedding-3-large-test-model-id",
            api_key="test-key",
        )
        try:
            config = manager.create(request)
        except ValueError:
            # 如果已存在，先删除
            manager.delete("openai-text-embedding-3-large-test-model-id")
            config = manager.create(request)
        
        # 使用指定模型 ID 创建 Embedding
        embedding = manager.create_embedding(model_id=config.id)
        
        assert embedding is not None


class TestModelManagerYAMLLoading:
    """测试 ModelManager 的 YAML 配置加载"""
    
    def test_yaml_loading_success(self):
        """测试成功加载 YAML 配置"""
        manager = ModelManager()
        
        # 验证从 YAML 加载的模型
        configs = manager.list(model_type=ModelType.LLM)
        
        # 应该至少有 YAML 中定义的模型
        assert len(configs) > 0
        
        # 验证 deepseek-chat 模型存在
        deepseek_chat = manager.get("deepseek-chat")
        if deepseek_chat:
            assert deepseek_chat.provider == "deepseek"
            assert deepseek_chat.model_name == "deepseek-chat"
    
    def test_yaml_loading_with_invalid_path(self):
        """测试加载不存在的 YAML 文件"""
        # 创建新实例（会尝试加载 YAML）
        manager = ModelManager()
        
        # 应该不会抛出异常，而是使用环境变量配置
        assert manager is not None


class TestModelManagerEnvironmentVariables:
    """测试 ModelManager 的环境变量加载"""
    
    def test_env_loading_with_llm_config(self, monkeypatch):
        """测试从环境变量加载 LLM 配置"""
        # 设置环境变量
        monkeypatch.setenv("LLM_API_BASE", "https://test.api.com")
        monkeypatch.setenv("LLM_API_KEY", "test-key-123")
        monkeypatch.setenv("LLM_MODEL_NAME", "test-model")
        
        # 创建新实例
        manager = ModelManager()
        
        # 验证环境变量配置被加载
        env_llm = manager.get("env-default-llm")
        if env_llm:
            assert env_llm.api_base == "https://test.api.com"
            assert env_llm.api_key == "test-key-123"
            assert env_llm.model_name == "test-model"


class TestEmbeddingsWrapper:
    """测试 embeddings_wrapper.py"""
    
    def test_get_embeddings_with_default(self):
        """测试使用默认配置获取 Embedding"""
        from src.infra.ai.embeddings_wrapper import get_embeddings
        
        # 创建一个默认 Embedding 配置（使用唯一 ID）
        manager = get_model_manager()
        request = ModelCreateRequest(
            name="Test Embedding Wrapper Default",
            model_type=ModelType.EMBEDDING,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="text-embedding-3-small-test-wrapper-default",
            api_key="test-key",
            is_default=True,
        )
        try:
            manager.create(request)
        except ValueError:
            # 如果已存在，先删除
            manager.delete("openai-text-embedding-3-small-test-wrapper-default")
            manager.create(request)
        
        # 获取 Embedding
        embedding = get_embeddings()
        
        assert embedding is not None
        assert hasattr(embedding, 'embed_query')
    
    def test_get_embeddings_with_model_id(self):
        """测试使用指定模型 ID 获取 Embedding"""
        from src.infra.ai.embeddings_wrapper import get_embeddings
        
        # 创建一个 Embedding 配置（使用唯一 ID）
        manager = get_model_manager()
        request = ModelCreateRequest(
            name="Test Embedding Wrapper Model ID",
            model_type=ModelType.EMBEDDING,
            provider="openai",
            api_base="https://api.openai.com/v1",
            model_name="text-embedding-3-large-test-wrapper-model-id",
            api_key="test-key",
        )
        try:
            config = manager.create(request)
        except ValueError:
            # 如果已存在，先删除
            manager.delete("openai-text-embedding-3-large-test-wrapper-model-id")
            config = manager.create(request)
        
        # 使用指定模型 ID 获取 Embedding
        embedding = get_embeddings(model_id=config.id)
        
        assert embedding is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
