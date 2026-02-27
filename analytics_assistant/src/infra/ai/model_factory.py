# -*- coding: utf-8 -*-
"""
ModelFactory - 模型实例工厂

职责：根据配置创建 LLM 和 Embedding 实例

从 ModelManager 拆分出来，专注于实例创建。
"""
import logging
from datetime import datetime
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI, AzureChatOpenAI, OpenAIEmbeddings, AzureOpenAIEmbeddings

from .custom_llm import CustomChatLLM
from .models import ModelConfig, AuthType

logger = logging.getLogger(__name__)

class ModelFactory:
    """模型实例工厂
    
    职责：根据配置创建 LLM 和 Embedding 实例
    
    支持的 Provider：
    - Azure OpenAI
    - OpenAI 兼容模型（DeepSeek、智谱、Qwen、Kimi 等）
    """
    
    def create_llm(
        self,
        config: ModelConfig,
        **kwargs,
    ) -> BaseChatModel:
        """创建 LLM 实例
        
        Args:
            config: 模型配置
            **kwargs: 运行时参数
                - temperature: 温度参数
                - max_tokens: 最大 token 数
                - enable_json_mode: 是否启用 JSON Mode
                - streaming: 是否启用流式输出
        
        Returns:
            LangChain BaseChatModel 实例
        """
        # 合并参数：kwargs 优先，然后是 config
        temperature = kwargs.get('temperature', config.temperature)
        max_tokens = kwargs.get('max_tokens', config.max_tokens)
        enable_json_mode = kwargs.pop('enable_json_mode', False)
        streaming = kwargs.pop('streaming', False)
        
        # 路由到具体实现
        if config.provider == "azure":
            return self._create_azure_llm(
                config, temperature, max_tokens, enable_json_mode, streaming
            )
        
        if not config.openai_compatible:
            return self._create_custom_llm(
                config, temperature, max_tokens, enable_json_mode, streaming
            )
        
        return self._create_openai_compatible_llm(
            config, temperature, max_tokens, enable_json_mode, streaming
        )
    
    def _create_azure_llm(
        self,
        config: ModelConfig,
        temperature: Optional[float],
        max_tokens: Optional[int],
        enable_json_mode: bool,
        streaming: bool,
    ) -> AzureChatOpenAI:
        """创建 Azure OpenAI LLM"""
        azure_kwargs = {
            "azure_deployment": config.model_name,
            "azure_endpoint": config.api_base,
            "openai_api_key": config.api_key,
            "openai_api_version": config.extra_body.get("api_version", "2024-02-15-preview"),
            "streaming": streaming,
        }
        
        if temperature is not None:
            azure_kwargs["temperature"] = temperature
        if max_tokens is not None:
            azure_kwargs["max_tokens"] = max_tokens
        
        if enable_json_mode:
            json_mode_kwargs = self._get_json_mode_kwargs(config.provider, enable_json_mode)
            azure_kwargs.update(json_mode_kwargs)
        
        return AzureChatOpenAI(**azure_kwargs)
    
    def _create_custom_llm(
        self,
        config: ModelConfig,
        temperature: Optional[float],
        max_tokens: Optional[int],
        enable_json_mode: bool,
        streaming: bool,
    ) -> CustomChatLLM:
        """创建自定义 LLM（非标准 OpenAI 兼容 API）
        
        用于：
        - 使用非标准端点的 API（如 /api/v1/offline/deep/think）
        - 需要自定义认证 header 的 API
        """
        # 构建完整 API URL
        api_url = config.api_base
        if config.api_endpoint:
            # 如果配置了 api_endpoint，拼接到 api_base
            api_url = config.api_base.rstrip("/") + config.api_endpoint
        
        custom_kwargs: dict[str, Any] = {
            "api_base": api_url,
            "model_name": config.model_name,
            "api_key": config.api_key,
            "auth_header": config.auth_header,
            "streaming": streaming,
            "is_reasoning_model": config.is_reasoning_model,
            "timeout": config.timeout,
            "verify_ssl": config.verify_ssl,
        }
        
        if temperature is not None:
            custom_kwargs["temperature"] = temperature
        if max_tokens is not None:
            custom_kwargs["max_tokens"] = max_tokens
        
        # 添加 response_format（如果启用 json_mode 且 API 支持）
        if enable_json_mode and config.supports_json_mode:
            custom_kwargs["response_format"] = {"type": "json_object"}
            logger.debug(f"CustomChatLLM 启用 JSON Mode: model={config.model_name}")
        
        logger.info(
            f"创建 CustomChatLLM: model={config.model_name}, "
            f"api_url={api_url}, auth_header={config.auth_header}"
        )
        
        # 更新最后使用时间
        config.last_used_at = datetime.now()
        
        llm_instance = CustomChatLLM(**custom_kwargs)
        
        # 为推理模型添加标记
        if config.is_reasoning_model:
            llm_instance._is_reasoning_model = True
            llm_instance._model_config = config
        
        return llm_instance
    
    def _create_openai_compatible_llm(
        self,
        config: ModelConfig,
        temperature: Optional[float],
        max_tokens: Optional[int],
        enable_json_mode: bool,
        streaming: bool,
    ) -> ChatOpenAI:
        """创建 OpenAI 兼容的 LLM"""
        openai_kwargs = {
            "model_name": config.model_name,
            "streaming": streaming,
        }
        
        # 非 OpenAI 官方 API 设置 base_url
        if "api.openai.com" not in config.api_base:
            openai_kwargs["base_url"] = config.api_base
        
        if temperature is not None:
            openai_kwargs["temperature"] = temperature
        if max_tokens is not None:
            openai_kwargs["max_tokens"] = max_tokens
        
        if enable_json_mode:
            json_mode_kwargs = self._get_json_mode_kwargs(config.provider, enable_json_mode)
            openai_kwargs.update(json_mode_kwargs)
        
        # 处理认证方式
        if config.auth_type == AuthType.CUSTOM_HEADER:
            # 自定义 header 认证（如 apikey: xxx）
            # ChatOpenAI 需要 api_key，但实际认证通过 default_headers
            openai_kwargs["api_key"] = "dummy"  # 占位，实际不使用
            openai_kwargs["default_headers"] = {
                config.auth_header: config.api_key
            }
            logger.debug(f"使用自定义认证 header: {config.auth_header}")
        else:
            # 标准 Bearer 认证
            openai_kwargs["api_key"] = config.api_key
        
        # 更新最后使用时间
        config.last_used_at = datetime.now()
        
        llm_instance = ChatOpenAI(**openai_kwargs)
        
        # 为推理模型添加标记
        if config.is_reasoning_model:
            llm_instance._is_reasoning_model = True
            llm_instance._model_config = config
        
        return llm_instance
    
    def _get_json_mode_kwargs(self, provider: str, enable_json_mode: bool = True) -> dict[str, Any]:
        """获取 JSON Mode 参数（适配不同提供商）"""
        if not enable_json_mode:
            return {}
        
        provider_lower = provider.lower()
        
        # DeepSeek、OpenAI、Azure、Local 使用 model_kwargs
        if provider_lower in ("deepseek", "openai", "azure", "local", "qwen", "kimi"):
            return {
                "model_kwargs": {
                    "response_format": {"type": "json_object"}
                }
            }
        
        # Custom 使用 extra_body
        elif provider_lower == "custom":
            return {
                "extra_body": {
                    "response_format": {"type": "json_object"}
                }
            }
        
        # Anthropic 不支持原生 JSON Mode
        elif provider_lower == "anthropic":
            logger.info("Anthropic does not support native JSON Mode")
            return {}
        
        # 默认使用 model_kwargs
        else:
            logger.debug(f"Unknown provider '{provider}', using default JSON Mode configuration")
            return {
                "model_kwargs": {
                    "response_format": {"type": "json_object"}
                }
            }
    
    def create_embedding(
        self,
        config: ModelConfig,
        **kwargs,
    ) -> Embeddings:
        """创建 Embedding 实例
        
        Args:
            config: 模型配置
            **kwargs: 其他参数
        
        Returns:
            LangChain Embeddings 实例
        """
        if config.provider == "azure":
            return self._create_azure_embedding(config)
        
        return self._create_openai_compatible_embedding(config)
    
    def _create_azure_embedding(self, config: ModelConfig) -> AzureOpenAIEmbeddings:
        """创建 Azure OpenAI Embedding"""
        azure_kwargs = {
            "azure_deployment": config.model_name,
            "azure_endpoint": config.api_base,
            "openai_api_key": config.api_key,
            "openai_api_version": config.extra_body.get("api_version", "2024-02-15-preview"),
        }
        return AzureOpenAIEmbeddings(**azure_kwargs)
    
    def _create_openai_compatible_embedding(self, config: ModelConfig) -> OpenAIEmbeddings:
        """创建 OpenAI 兼容的 Embedding"""
        openai_kwargs = {
            "model": config.model_name,
            "api_key": config.api_key,
        }
        
        # 非 OpenAI 官方 API 设置 base_url
        if "api.openai.com" not in config.api_base:
            openai_kwargs["base_url"] = config.api_base
            # 非 OpenAI API 禁用 tiktoken（避免 tokenizer 不兼容问题）
            # 智谱、DeepSeek 等模型使用不同的 tokenizer，启用 tiktoken 会导致 embedding 结果错误
            openai_kwargs["tiktoken_enabled"] = False
            openai_kwargs["check_embedding_ctx_length"] = False
        
        # 更新最后使用时间
        config.last_used_at = datetime.now()
        
        return OpenAIEmbeddings(**openai_kwargs)

__all__ = ["ModelFactory"]
