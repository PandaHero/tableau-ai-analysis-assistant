# -*- coding: utf-8 -*-
"""
Embedding 便捷函数

提供简单的 Embedding 获取接口，封装 ModelManager。
"""
import logging
from typing import Optional

from langchain_core.embeddings import Embeddings

logger = logging.getLogger(__name__)


def get_embeddings(
    model_id: Optional[str] = None,
    **kwargs
) -> Embeddings:
    """
    获取 Embedding 实例（便捷函数）
    
    统一的 Embedding 获取入口，从 ModelManager 获取模型配置并创建实例。
    
    Args:
        model_id: 模型 ID（可选，不指定则使用默认 Embedding）
        **kwargs: 其他参数（如 batch_size, dimensions）
    
    Returns:
        配置好的 LangChain Embeddings 实例
    
    Raises:
        ValueError: 未找到模型配置
    
    Examples:
        # 使用默认 Embedding
        embeddings = get_embeddings()
        
        # 指定模型
        embeddings = get_embeddings(model_id="env-zhipu-embedding")
        
        # 使用
        vectors = embeddings.embed_documents(["文本1", "文本2"])
        query_vector = embeddings.embed_query("查询文本")
    """
    from .model_manager import get_model_manager
    
    manager = get_model_manager()
    return manager.create_embedding(model_id=model_id, **kwargs)


__all__ = [
    "get_embeddings",
]
