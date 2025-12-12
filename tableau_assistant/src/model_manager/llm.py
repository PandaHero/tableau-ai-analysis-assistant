"""
LLM 模型管理

统一管理大语言模型的选择和配置。

支持的提供商：
- local: 公司内部自建 LLM（OpenAI 兼容 API）
- openai: OpenAI 官方 API
- azure: Azure OpenAI 服务
- claude: Anthropic Claude 模型
- deepseek: DeepSeek API
- qwen: 通义千问
- zhipu: 智谱 AI
"""
import os
import logging
from typing import Optional, List

import httpx
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain.chat_models.base import BaseChatModel

logger = logging.getLogger(__name__)

# 支持的 LLM 提供商
SUPPORTED_LLM_PROVIDERS: List[str] = [
    "local",
    "openai", 
    "azure",
    "claude",
    "deepseek",
    "qwen",
    "zhipu",
]

# 尝试导入证书管理器
try:
    from tableau_assistant.cert_manager import get_ssl_config
    def get_httpx_client_kwargs():
        return get_ssl_config().httpx_client_kwargs()
except ImportError:
    try:
        from tableau_assistant.src.utils.ssl_config import get_httpx_client_kwargs
    except ImportError:
        def get_httpx_client_kwargs():
            return {}

# 尝试导入 Anthropic 模型（可选依赖）
ANTHROPIC_AVAILABLE = False
try:
    from langchain_anthropic import ChatAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ChatAnthropic = None


def select_model(
    provider: str,
    model_name: str,
    temperature: float = 0.2
) -> BaseChatModel:
    """
    选择并配置大语言模型
    
    Args:
        provider: 模型提供商
            - "local": 公司内部自建 LLM（使用 OpenAI 兼容 API）
            - "openai": OpenAI 官方 API
            - "azure": Azure OpenAI 服务
            - "claude": Anthropic Claude 模型
            - "deepseek": DeepSeek API
            - "qwen": 通义千问
            - "zhipu": 智谱 AI
        model_name: 模型名称（必需，不使用默认值）
        temperature: 温度参数（默认 0.2）
        
    Returns:
        配置好的 BaseChatModel 实例
        
    Raises:
        ValueError: 配置缺失或提供商不支持
        
    Examples:
        >>> llm = select_model("deepseek", "deepseek-chat")
        >>> llm = select_model("local", "qwen2.5-72b", temperature=0.0)
    """
    if not provider:
        raise ValueError("provider is required")
    
    if not model_name:
        raise ValueError("model_name is required")
    
    # 从 settings 获取通用配置
    from tableau_assistant.src.config.settings import settings
    llm_api_base = settings.llm_api_base
    llm_api_key = settings.llm_api_key
    
    # 获取 SSL 配置
    ssl_kwargs = get_httpx_client_kwargs()
    http_client = httpx.Client(**ssl_kwargs) if ssl_kwargs.get("verify") is not True else None
    http_async_client = httpx.AsyncClient(**ssl_kwargs) if ssl_kwargs.get("verify") is not True else None
    
    if provider == "local":
        return _create_local_model(
            model_name, temperature, llm_api_base, llm_api_key,
            http_client, http_async_client
        )
    
    elif provider == "openai":
        return _create_openai_model(
            model_name, temperature, llm_api_base, llm_api_key,
            http_client, http_async_client
        )
    
    elif provider == "azure":
        return _create_azure_model(model_name, temperature)
    
    elif provider == "claude":
        return _create_claude_model(model_name, temperature)
    
    elif provider == "deepseek":
        return _create_deepseek_model(
            model_name, temperature, llm_api_key,
            http_client, http_async_client
        )
    
    elif provider == "qwen":
        return _create_qwen_model(
            model_name, temperature, llm_api_base, llm_api_key,
            http_client, http_async_client
        )
    
    elif provider == "zhipu":
        return _create_zhipu_model(
            model_name, temperature, llm_api_key,
            http_client, http_async_client
        )
    
    else:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported providers: {', '.join(SUPPORTED_LLM_PROVIDERS)}"
        )


def _create_local_model(
    model_name: str,
    temperature: float,
    api_base: Optional[str],
    api_key: Optional[str],
    http_client,
    http_async_client
) -> ChatOpenAI:
    """创建本地/内部 LLM"""
    if not api_base:
        raise ValueError("LLM_API_BASE must be set for local provider")
    if not api_key:
        raise ValueError("LLM_API_KEY must be set for local provider")
    
    return ChatOpenAI(
        base_url=api_base,
        api_key=api_key,
        model_name=model_name,
        temperature=temperature,
        http_client=http_client,
        http_async_client=http_async_client
    )


def _create_openai_model(
    model_name: str,
    temperature: float,
    api_base: Optional[str],
    api_key: Optional[str],
    http_client,
    http_async_client
) -> ChatOpenAI:
    """创建 OpenAI 模型"""
    if api_base and "api.openai.com" not in api_base:
        # OpenAI 兼容 API
        if not api_key:
            raise ValueError("LLM_API_KEY must be set for OpenAI-compatible API")
        return ChatOpenAI(
            base_url=api_base,
            api_key=api_key,
            model_name=model_name,
            temperature=temperature,
            http_client=http_client,
            http_async_client=http_async_client
        )
    else:
        # OpenAI 官方 API - 使用 LLM_API_KEY 作为 OpenAI key
        if not api_key:
            raise ValueError("LLM_API_KEY must be set for OpenAI official API")
        return ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            openai_api_key=api_key,
            http_client=http_client,
            http_async_client=http_async_client
        )


def _create_azure_model(model_name: str, temperature: float) -> AzureChatOpenAI:
    """创建 Azure OpenAI 模型
    
    注意：Azure 配置暂时保留使用 os.environ，因为这些是 Azure 特定的配置，
    如果需要使用 Azure，请在 .env 中配置相关环境变量。
    """
    azure_deployment = os.environ.get("AZURE_OPENAI_AGENT_DEPLOYMENT_NAME")
    azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
    azure_instance = os.environ.get("AZURE_OPENAI_API_INSTANCE_NAME")
    azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    
    if not all([azure_deployment, azure_api_version, azure_instance, azure_api_key]):
        raise ValueError(
            "Azure OpenAI configuration incomplete. Required in .env: "
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


def _create_claude_model(model_name: str, temperature: float):
    """创建 Claude 模型
    
    注意：Anthropic 配置暂时保留使用 os.environ，因为这是 Anthropic 特定的配置，
    如果需要使用 Claude，请在 .env 中配置 ANTHROPIC_API_KEY。
    """
    if not ANTHROPIC_AVAILABLE:
        raise ImportError(
            "langchain-anthropic is required for Claude models. "
            "Install with: pip install langchain-anthropic"
        )
    
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY must be set in .env for Claude provider")
    
    return ChatAnthropic(
        model=model_name,
        temperature=temperature,
        anthropic_api_key=anthropic_api_key,
        model_kwargs={
            "extra_headers": {
                "anthropic-beta": "prompt-caching-2024-07-31"
            }
        }
    )


def _create_deepseek_model(
    model_name: str,
    temperature: float,
    llm_api_key: Optional[str],
    http_client,
    http_async_client
) -> ChatOpenAI:
    """创建 DeepSeek 模型"""
    from tableau_assistant.src.config.settings import settings
    deepseek_api_key = settings.deepseek_api_key or llm_api_key
    deepseek_base_url = settings.deepseek_api_base
    
    if not deepseek_api_key:
        raise ValueError(
            "DEEPSEEK_API_KEY or LLM_API_KEY must be set in .env for DeepSeek provider"
        )
    
    return ChatOpenAI(
        base_url=deepseek_base_url,
        api_key=deepseek_api_key,
        model_name=model_name,
        temperature=temperature,
        http_client=http_client,
        http_async_client=http_async_client
    )


def _create_qwen_model(
    model_name: str,
    temperature: float,
    llm_api_base: Optional[str],
    llm_api_key: Optional[str],
    http_client,
    http_async_client
) -> ChatOpenAI:
    """创建通义千问模型
    
    使用 LLM_API_BASE 和 LLM_API_KEY 作为 Qwen 的配置。
    """
    qwen_api_key = llm_api_key
    qwen_base_url = llm_api_base
    
    if not qwen_api_key:
        raise ValueError(
            "LLM_API_KEY must be set in .env for Qwen provider"
        )
    if not qwen_base_url:
        raise ValueError(
            "LLM_API_BASE must be set in .env for Qwen provider"
        )
    
    return ChatOpenAI(
        base_url=qwen_base_url,
        api_key=qwen_api_key,
        model_name=model_name,
        temperature=temperature,
        http_client=http_client,
        http_async_client=http_async_client
    )


def _create_zhipu_model(
    model_name: str,
    temperature: float,
    llm_api_key: Optional[str],
    http_client,
    http_async_client
) -> ChatOpenAI:
    """创建智谱 AI 模型"""
    from tableau_assistant.src.config.settings import settings
    zhipu_api_key = settings.zhipuai_api_key or llm_api_key
    zhipu_base_url = settings.zhipu_api_base
    
    if not zhipu_api_key:
        raise ValueError(
            "ZHIPUAI_API_KEY must be set in .env for Zhipu provider"
        )
    
    return ChatOpenAI(
        base_url=zhipu_base_url,
        api_key=zhipu_api_key,
        model_name=model_name,
        temperature=temperature,
        http_client=http_client,
        http_async_client=http_async_client
    )


# ═══════════════════════════════════════════════════════════════════════════
# 高层 API：自动从环境变量读取配置
# ═══════════════════════════════════════════════════════════════════════════

def get_llm(
    temperature: Optional[float] = None,
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
) -> BaseChatModel:
    """
    获取 LLM 实例（自动从环境变量读取配置）
    
    这是推荐的高层 API，自动从环境变量读取 provider 和 model_name。
    
    环境变量：
        - LLM_MODEL_PROVIDER: 模型提供商（默认 "local"）
        - LLM_MODEL_NAME: 模型名称（默认 "qwen2.5-72b"）
        - TOOLING_LLM_MODEL: 工具调用模型（优先级高于 LLM_MODEL_NAME）
        - LLM_TEMPERATURE: 默认温度（默认 0.2）
    
    Args:
        temperature: 温度参数（可选，覆盖环境变量默认值）
        model_name: 模型名称（可选，覆盖环境变量）
        provider: 提供商（可选，覆盖环境变量）
    
    Returns:
        配置好的 LLM 实例
    
    Examples:
        # 使用默认配置（从环境变量读取）
        llm = get_llm()
        
        # 指定 temperature
        llm = get_llm(temperature=0.1)
        
        # 完全自定义
        llm = get_llm(temperature=0.3, model_name="gpt-4o", provider="openai")
    """
    from tableau_assistant.src.config.settings import settings
    _provider = provider or settings.llm_model_provider
    _model_name = model_name or settings.tooling_llm_model or "qwen2.5-72b"
    _temperature = temperature if temperature is not None else settings.llm_temperature
    
    return select_model(
        provider=_provider,
        model_name=_model_name,
        temperature=_temperature
    )


__all__ = [
    # 底层 API
    "select_model",
    "SUPPORTED_LLM_PROVIDERS",
    # 高层 API
    "get_llm",
]
