# -*- coding: utf-8 -*-
"""
LLM 模型管理

统一的 LLM 获取入口，所有模型通过 ModelManager 管理。

使用示例：
    from tableau_assistant.src.infra.ai import get_llm
    
    # 使用默认 LLM
    llm = get_llm()
    
    # 指定温度
    llm = get_llm(temperature=0.1)
    
    # 指定模型 ID
    llm = get_llm(model_id="my-gpt4")
"""
import logging
from typing import Optional, List

from langchain.chat_models.base import BaseChatModel

logger = logging.getLogger(__name__)


def get_llm(
    model_id: Optional[str] = None,
    temperature: Optional[float] = None,
    enable_json_mode: bool = False,
    **kwargs,
) -> BaseChatModel:
    """获取 LLM 实例
    
    统一的 LLM 获取入口，从 ModelManager 获取模型配置并创建实例。
    
    Args:
        model_id: 模型 ID（可选，不指定则使用默认 LLM）
        temperature: 温度参数（可选，覆盖模型配置的默认值）
        enable_json_mode: 是否启用 JSON Mode（Requirements 0.7）
        **kwargs: 其他参数（如 max_tokens）
    
    Returns:
        配置好的 LLM 实例（BaseChatModel）
    
    Raises:
        ValueError: 未找到模型配置
    
    Examples:
        # 使用默认 LLM
        llm = get_llm()
        
        # 指定温度
        llm = get_llm(temperature=0.1)
        
        # 启用 JSON Mode（Requirements 0.7）
        llm = get_llm(enable_json_mode=True)
        
        # 指定模型
        llm = get_llm(model_id="env-custom-llm")
        
        # 完全自定义
        llm = get_llm(model_id="my-gpt4", temperature=0.3, max_tokens=2048)
    """
    from tableau_assistant.src.infra.ai.model_manager import get_model_manager
    
    manager = get_model_manager()
    
    # 构建参数
    create_kwargs = {**kwargs}
    if temperature is not None:
        create_kwargs['temperature'] = temperature
    if enable_json_mode:
        create_kwargs['enable_json_mode'] = enable_json_mode
    
    return manager.create_llm(model_id=model_id, **create_kwargs)


def get_supported_providers() -> List[str]:
    """获取支持的 LLM 提供商列表
    
    动态获取 ModelManager 中注册的所有 LLM 提供商。
    
    Returns:
        提供商列表
    """
    from tableau_assistant.src.infra.ai.model_manager import get_model_manager, ModelType
    
    providers = set()
    
    try:
        manager = get_model_manager()
        for config in manager.list(model_type=ModelType.LLM):
            providers.add(config.provider)
    except Exception:
        pass
    
    return sorted(list(providers))


__all__ = [
    "get_llm",
    "get_supported_providers",
]
