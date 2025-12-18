"""
Reranker 模型管理

统一管理重排序模型的选择和配置。
专为 Tableau 扩展插件设计，无需下载大模型。

支持的重排序器类型：
- default: 默认重排序（按分数排序）
- rrf: RRF 融合重排序（推荐用于混合检索）
- llm: LLM 重排序（推荐，使用现有 LLM API）
"""
import logging
from typing import Optional, List, Callable

logger = logging.getLogger(__name__)

# 支持的 Reranker 类型
SUPPORTED_RERANKER_TYPES: List[str] = [
    "default",
    "rrf",
    "llm",
]


def select_reranker(
    reranker_type: str = "default",
    top_k: int = 5,
    # LLM 参数
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_call_fn: Optional[Callable[[str], str]] = None,
    # RRF 参数
    rrf_k: int = 60,
    **kwargs  # 忽略其他参数（向后兼容）
):
    """
    选择并配置重排序器
    
    Args:
        reranker_type: 重排序器类型
            - "default": 默认重排序（按分数排序）
            - "rrf": RRF 融合重排序（推荐用于混合检索）
            - "llm": LLM 重排序（推荐，使用现有 LLM API）
        top_k: 返回结果数量
        llm_provider: LLM 提供商（zhipu/deepseek/openai 等）
        llm_model: LLM 模型名称
        llm_call_fn: 自定义 LLM 调用函数
        rrf_k: RRF 参数 k
        
    Returns:
        配置好的 Reranker 实例
        
    Examples:
        >>> # 默认重排序
        >>> reranker = select_reranker("default")
        
        >>> # RRF 重排序（推荐用于混合检索）
        >>> reranker = select_reranker("rrf")
        
        >>> # LLM 重排序（推荐）
        >>> reranker = select_reranker(
        ...     "llm",
        ...     llm_provider="zhipu",
        ...     llm_model="glm-4-flash"
        ... )
    """
    from tableau_assistant.src.infra.ai.rag.reranker import (
        DefaultReranker,
        RRFReranker,
        LLMReranker,
    )
    
    if reranker_type == "default":
        return DefaultReranker(top_k=top_k)
    
    elif reranker_type == "rrf":
        return RRFReranker(top_k=top_k, k=rrf_k)
    
    elif reranker_type == "llm":
        return _create_llm_reranker(
            top_k=top_k,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_call_fn=llm_call_fn
        )
    
    else:
        raise ValueError(
            f"Unknown reranker type: {reranker_type}. "
            f"Supported types: {', '.join(SUPPORTED_RERANKER_TYPES)}"
        )


def _create_llm_reranker(
    top_k: int,
    llm_provider: Optional[str],
    llm_model: Optional[str],
    llm_call_fn: Optional[Callable[[str], str]]
):
    """创建 LLM 重排序器"""
    from tableau_assistant.src.infra.ai.rag.reranker import LLMReranker
    
    # 如果提供了自定义调用函数，直接使用
    if llm_call_fn is not None:
        return LLMReranker(top_k=top_k, llm_call_fn=llm_call_fn)
    
    # 如果提供了 provider 和 model，使用 select_model
    if llm_provider and llm_model:
        from tableau_assistant.src.infra.ai.llm import select_model
        llm = select_model(provider=llm_provider, model_name=llm_model, temperature=0.1)
    else:
        # 否则使用 get_llm（自动从环境变量读取配置）
        from tableau_assistant.src.infra.ai.llm import get_llm
        llm = get_llm(temperature=0.1)  # Reranker 需要精确判断，使用低 temperature
    
    def _llm_call_fn(prompt: str) -> str:
        return llm.invoke(prompt).content
    
    return LLMReranker(top_k=top_k, llm_call_fn=_llm_call_fn)


__all__ = [
    "select_reranker",
    "SUPPORTED_RERANKER_TYPES",
]
