# -*- coding: utf-8 -*-
"""
JSON Mode Provider 适配层

根据不同 LLM Provider 的支持情况，提供统一的 JSON Mode 参数配置。

设计原则（来自 design.md 2.0.7）：
- 按 Provider 显式配置支持与否（而非自动探测）
- detect_provider_from_base_url() 仅作为默认推断
- 生产环境应通过配置文件明确指定 Provider

Provider 支持情况：
| Provider | JSON Mode 参数 | 传递方式 | 备注 |
|----------|---------------|----------|------|
| DeepSeek | response_format: {type: "json_object"} | model_kwargs | 本项目主要使用 |
| OpenAI | response_format: {type: "json_object"} | model_kwargs | 兼容 |
| CustomLLMChat | response_format: {type: "json_object"} | extra_body | 仓库现有实现 |
| Anthropic | 不支持原生 JSON Mode | Prompt 约束 | 依赖 json_repair |
| Local | 取决于具体实现 | model_kwargs | 需测试 |
"""
import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ProviderType(Enum):
    """LLM Provider 类型"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    CUSTOM = "custom"  # CustomLLMChat（仓库现有实现）
    ANTHROPIC = "anthropic"
    LOCAL = "local"  # 本地模型（如 Ollama）
    AZURE = "azure"  # Azure OpenAI


def get_json_mode_kwargs(
    provider: ProviderType,
    enable_json_mode: bool = True,
) -> dict[str, Any]:
    """获取 JSON Mode 参数 - Provider 适配层
    
    Args:
        provider: LLM Provider 类型
        enable_json_mode: 是否启用 JSON Mode
        
    Returns:
        传递给 LLM 构造函数的参数字典
        
    ⚠️ 注意：不同 Provider 使用不同的参数传递方式：
    - ChatOpenAI: 通过 model_kwargs.response_format
    - CustomLLMChat: 通过 extra_body.response_format
    """
    if not enable_json_mode:
        return {}
    
    if provider in (ProviderType.DEEPSEEK, ProviderType.OPENAI, ProviderType.AZURE):
        # DeepSeek、OpenAI、Azure 使用 ChatOpenAI，通过 model_kwargs 传递
        return {
            "model_kwargs": {
                "response_format": {"type": "json_object"}
            }
        }
    
    elif provider == ProviderType.CUSTOM:
        # CustomLLMChat（仓库现有实现）使用 extra_body 拼 payload
        # 见 custom_llm.py 的实现
        return {
            "extra_body": {
                "response_format": {"type": "json_object"}
            }
        }
    
    elif provider == ProviderType.LOCAL:
        # 本地模型（如通过 OpenAI 兼容 API 访问）
        # 优先尝试 model_kwargs
        return {
            "model_kwargs": {
                "response_format": {"type": "json_object"}
            }
        }
    
    elif provider == ProviderType.ANTHROPIC:
        # Anthropic 不支持原生 JSON Mode
        # 返回空，依赖 Prompt 约束 + json_repair
        logger.info("Anthropic does not support native JSON Mode, relying on prompt constraints")
        return {}
    
    return {}


def detect_provider_from_base_url(base_url: str | None) -> ProviderType:
    """从 base_url 推断 Provider 类型（仅作为默认推断，生产环境应显式配置）
    
    Args:
        base_url: API base URL
        
    Returns:
        推断的 Provider 类型
        
    ⚠️ 注意：此函数仅用于默认推断，requirements.md 要求生产环境通过配置显式指定 Provider。
    """
    if not base_url:
        return ProviderType.OPENAI  # 默认 OpenAI
    
    base_url_lower = base_url.lower()
    
    if "deepseek" in base_url_lower:
        return ProviderType.DEEPSEEK
    elif "anthropic" in base_url_lower:
        return ProviderType.ANTHROPIC
    elif "localhost" in base_url_lower or "127.0.0.1" in base_url_lower:
        return ProviderType.LOCAL
    elif "openai.azure.com" in base_url_lower:
        return ProviderType.AZURE
    elif "openai" in base_url_lower:
        return ProviderType.OPENAI
    
    # 默认假设本地/自定义模型
    return ProviderType.LOCAL


def get_provider_from_config(
    provider_str: str | None = None,
    base_url: str | None = None,
    openai_compatible: bool = True,
) -> ProviderType:
    """从配置获取 Provider 类型（推荐方式）
    
    Args:
        provider_str: 显式配置的 provider 字符串
        base_url: API base URL（用于回退推断）
        openai_compatible: 是否 OpenAI 兼容
        
    Returns:
        Provider 类型
    """
    # 显式配置优先
    if provider_str:
        provider_map = {
            "deepseek": ProviderType.DEEPSEEK,
            "openai": ProviderType.OPENAI,
            "custom": ProviderType.CUSTOM,
            "anthropic": ProviderType.ANTHROPIC,
            "local": ProviderType.LOCAL,
            "azure": ProviderType.AZURE,
        }
        
        provider_lower = provider_str.lower()
        if provider_lower in provider_map:
            return provider_map[provider_lower]
    
    # 非 OpenAI 兼容 → Custom
    if not openai_compatible:
        return ProviderType.CUSTOM
    
    # 未配置时回退到 URL 推断
    logger.debug("Provider not explicitly configured, falling back to URL detection")
    return detect_provider_from_base_url(base_url)


def supports_json_mode(provider: ProviderType) -> bool:
    """检查 Provider 是否支持 JSON Mode
    
    Args:
        provider: Provider 类型
        
    Returns:
        是否支持 JSON Mode
    """
    return provider not in (ProviderType.ANTHROPIC,)


__all__ = [
    "ProviderType",
    "get_json_mode_kwargs",
    "detect_provider_from_base_url",
    "get_provider_from_config",
    "supports_json_mode",
]
