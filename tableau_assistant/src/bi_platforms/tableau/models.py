import os
import httpx
from langchain_openai import ChatOpenAI, AzureChatOpenAI, OpenAIEmbeddings, AzureOpenAIEmbeddings
from langchain.chat_models.base import BaseChatModel
from langchain.embeddings.base import Embeddings

# 使用新的证书管理包
try:
    from tableau_assistant.cert_manager import get_ssl_config
    def get_httpx_client_kwargs():
        return get_ssl_config().httpx_client_kwargs()
except ImportError:
    # 兼容旧版本
    from tableau_assistant.src.utils.ssl_config import get_httpx_client_kwargs

# 尝试导入 Anthropic 模型（可选依赖）
ANTHROPIC_AVAILABLE = False
try:
    from langchain_anthropic import ChatAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ChatAnthropic = None


def select_model(provider: str, model_name: str, temperature: float = 0.2) -> BaseChatModel:
    """
    Select and configure a language model based on the provider.
    
    生产级别的模型选择逻辑，支持：
    - local: 公司内部自建LLM（使用OpenAI兼容API）
    - openai: OpenAI官方API或OpenAI兼容的公共API（如DeepSeek）
    - azure: Azure OpenAI服务
    - claude: Anthropic Claude 模型（自动启用 Prompt 缓存）
    - deepseek: DeepSeek API（使用 OpenAI 兼容接口）
    - qwen: 通义千问（使用 OpenAI 兼容接口）
    
    Args:
        provider: Model provider - "local", "openai", "azure", "claude", "deepseek", "qwen"
        model_name: Name of the model to use (required, no defaults)
        temperature: Temperature setting for the model
        
    Returns:
        Configured BaseChatModel instance
        
    Raises:
        ValueError: If required configuration is missing
    """
    if not provider:
        raise ValueError("provider is required")
    
    if not model_name:
        raise ValueError("model_name is required")
    
    # 从环境变量获取配置
    llm_api_base = os.environ.get("LLM_API_BASE")
    llm_api_key = os.environ.get("LLM_API_KEY")
    
    # 使用统一的SSL配置
    ssl_kwargs = get_httpx_client_kwargs()
    http_client = httpx.Client(**ssl_kwargs) if ssl_kwargs.get("verify") is not True else None
    http_async_client = httpx.AsyncClient(**ssl_kwargs) if ssl_kwargs.get("verify") is not True else None
    
    if provider == "local":
        # 公司内部自建LLM（OpenAI兼容API）
        if not llm_api_base:
            raise ValueError("LLM_API_BASE must be set for local provider")
        
        if not llm_api_key:
            raise ValueError("LLM_API_KEY must be set for local provider")
        
        return ChatOpenAI(
            base_url=llm_api_base,
            api_key=llm_api_key,
            model_name=model_name,
            temperature=temperature,
            http_client=http_client,
            http_async_client=http_async_client
        )
    
    elif provider == "openai":
        # OpenAI官方API或OpenAI兼容的公共API（如DeepSeek）
        
        if llm_api_base and "api.openai.com" not in llm_api_base:
            # 使用OpenAI兼容的公共API（如DeepSeek）
            if not llm_api_key:
                raise ValueError("LLM_API_KEY must be set for OpenAI-compatible API")
            
            return ChatOpenAI(
                base_url=llm_api_base,
                api_key=llm_api_key,
                model_name=model_name,
                temperature=temperature,
                http_client=http_client,
                http_async_client=http_async_client
            )
        else:
            # 使用OpenAI官方API
            openai_api_key = os.environ.get("OPENAI_API_KEY")
            if not openai_api_key:
                raise ValueError("OPENAI_API_KEY must be set for OpenAI official API")
            
            return ChatOpenAI(
                model_name=model_name,
                temperature=temperature,
                openai_api_key=openai_api_key,
                http_client=http_client,
                http_async_client=http_async_client
            )
    
    elif provider == "azure":
        # Azure OpenAI服务
        azure_deployment = os.environ.get("AZURE_OPENAI_AGENT_DEPLOYMENT_NAME")
        azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
        azure_instance = os.environ.get("AZURE_OPENAI_API_INSTANCE_NAME")
        azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        
        if not all([azure_deployment, azure_api_version, azure_instance, azure_api_key]):
            raise ValueError(
                "Azure OpenAI configuration incomplete. Required: "
                "AZURE_OPENAI_AGENT_DEPLOYMENT_NAME, AZURE_OPENAI_API_VERSION, "
                "AZURE_OPENAI_API_INSTANCE_NAME, AZURE_OPENAI_API_KEY"
            )
        
        return AzureChatOpenAI(
            azure_deployment=azure_deployment,
            openai_api_version=azure_api_version,
            azure_endpoint=f"https://{azure_instance}.openai.azure.com",
            openai_api_key=azure_api_key,
            model_name=model_name,
            temperature=temperature
        )
    
    elif provider == "claude":
        # Anthropic Claude 模型（自动启用 Prompt 缓存）
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "langchain-anthropic is required for Claude models. "
                "Install with: pip install langchain-anthropic"
            )
        
        anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set for Claude provider")
        
        # Claude 模型自动启用 Prompt 缓存
        return ChatAnthropic(
            model=model_name,
            temperature=temperature,
            anthropic_api_key=anthropic_api_key,
            # 启用 beta 头以支持 Prompt 缓存
            model_kwargs={
                "extra_headers": {
                    "anthropic-beta": "prompt-caching-2024-07-31"
                }
            }
        )
    
    elif provider == "deepseek":
        # DeepSeek API（使用 OpenAI 兼容接口）
        deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY") or llm_api_key
        deepseek_base_url = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        
        if not deepseek_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY or LLM_API_KEY must be set for DeepSeek provider"
            )
        
        return ChatOpenAI(
            base_url=deepseek_base_url,
            api_key=deepseek_api_key,
            model_name=model_name,
            temperature=temperature,
            http_client=http_client,
            http_async_client=http_async_client
        )
    
    elif provider == "qwen":
        # 通义千问（使用 OpenAI 兼容接口）
        qwen_api_key = os.environ.get("QWEN_API_KEY") or llm_api_key
        qwen_base_url = os.environ.get("QWEN_API_BASE") or llm_api_base
        
        if not qwen_api_key:
            raise ValueError(
                "QWEN_API_KEY or LLM_API_KEY must be set for Qwen provider"
            )
        
        if not qwen_base_url:
            raise ValueError(
                "QWEN_API_BASE or LLM_API_BASE must be set for Qwen provider"
            )
        
        return ChatOpenAI(
            base_url=qwen_base_url,
            api_key=qwen_api_key,
            model_name=model_name,
            temperature=temperature,
            http_client=http_client,
            http_async_client=http_async_client
        )
    
    else:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported providers: local, openai, azure, claude, deepseek, qwen"
        )


def select_embeddings(provider: str, model_name: str) -> Embeddings:
    """
    Select and configure an embeddings model based on the provider.
    
    Args:
        provider: Model provider - "local", "azure", or "openai"
        model_name: Name of the embeddings model to use (required)
        
    Returns:
        Configured Embeddings instance
        
    Raises:
        ValueError: If required configuration is missing
    """
    if not provider:
        raise ValueError("provider is required")
    
    if not model_name:
        raise ValueError("model_name is required")
    
    llm_api_base = os.environ.get("LLM_API_BASE")
    llm_api_key = os.environ.get("LLM_API_KEY")
    
    # 使用统一的SSL配置
    ssl_kwargs = get_httpx_client_kwargs()
    http_client = httpx.Client(**ssl_kwargs) if ssl_kwargs.get("verify") is not True else None
    http_async_client = httpx.AsyncClient(**ssl_kwargs) if ssl_kwargs.get("verify") is not True else None
    
    if provider == "local":
        if not llm_api_base:
            raise ValueError("LLM_API_BASE must be set for local provider")
        
        if not llm_api_key:
            raise ValueError("LLM_API_KEY must be set for local provider")
        
        return OpenAIEmbeddings(
            base_url=llm_api_base,
            api_key=llm_api_key,
            model=model_name,
            http_client=http_client,
            http_async_client=http_async_client
        )
    
    elif provider == "azure":
        azure_deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")
        azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
        azure_instance = os.environ.get("AZURE_OPENAI_API_INSTANCE_NAME")
        azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        
        if not all([azure_deployment, azure_api_version, azure_instance, azure_api_key]):
            raise ValueError(
                "Azure OpenAI configuration incomplete. Required: "
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME, AZURE_OPENAI_API_VERSION, "
                "AZURE_OPENAI_API_INSTANCE_NAME, AZURE_OPENAI_API_KEY"
            )
        
        return AzureOpenAIEmbeddings(
            azure_deployment=azure_deployment,
            openai_api_version=azure_api_version,
            azure_endpoint=f"https://{azure_instance}.openai.azure.com",
            openai_api_key=azure_api_key,
            model=model_name
        )
    
    else:  # openai
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set for OpenAI embeddings")
        
        return OpenAIEmbeddings(
            model=model_name,
            openai_api_key=openai_api_key
        )
