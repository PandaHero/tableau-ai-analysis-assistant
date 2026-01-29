# -*- coding: utf-8 -*-
"""
RAG Prompts 模块

包含 RAG 相关的 Prompt 定义。
"""

from .reranker_prompt import (
    RERANK_SYSTEM_PROMPT,
    build_rerank_prompt,
)

__all__ = [
    "RERANK_SYSTEM_PROMPT",
    "build_rerank_prompt",
]
