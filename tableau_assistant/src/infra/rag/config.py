"""
RAG 检索模式配置

定义 RetrievalMode 枚举和预设配置，支持两种检索模式：
- FAST_RECALL: 快速召回模式（SchemaLinking 用）
- HIGH_PRECISION: 高精度模式（FieldMapper 用）

Requirements: 17.7.3 - 实现 RetrievalMode 配置
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from tableau_assistant.src.infra.rag.retriever import BaseRetriever
    from tableau_assistant.src.infra.rag.field_indexer import FieldIndexer



class RetrievalMode(Enum):
    """检索模式枚举
    
    Attributes:
        FAST_RECALL: 快速召回模式（SchemaLinking 用）
            - 使用级联检索（ExactRetriever → FuzzyRetriever → EmbeddingRetriever）
            - 早停优化
            - 无 LLMReranker
            - 超时 100ms
        HIGH_PRECISION: 高精度模式（FieldMapper 用）
            - 使用 HybridRetriever（Embedding + BM25）
            - 并行检索 + RRF 融合
            - LLMReranker
            - 超时 500ms
    """
    FAST_RECALL = "fast_recall"
    HIGH_PRECISION = "high_precision"


@dataclass
class RetrievalModeConfig:
    """检索模式配置
    
    Attributes:
        mode: 检索模式
        top_k: 返回结果数量
        timeout_ms: 超时时间（毫秒）
        use_reranker: 是否使用重排序器
        reranker_type: 重排序器类型（llm/rrf/default）
        use_cascade: 是否使用级联检索（早停）
        use_exact_match: 是否使用精确匹配
        use_fuzzy_match: 是否使用模糊匹配
        use_embedding: 是否使用向量检索
        use_keyword: 是否使用关键词检索（BM25）
        score_threshold: 分数阈值
        early_stop_threshold: 早停阈值（级联模式）
    """
    mode: RetrievalMode
    top_k: int = 10
    timeout_ms: int = 500
    use_reranker: bool = False
    reranker_type: Optional[str] = None
    use_cascade: bool = False
    use_exact_match: bool = True
    use_fuzzy_match: bool = True
    use_embedding: bool = True
    use_keyword: bool = True
    score_threshold: float = 0.0
    early_stop_threshold: float = 0.9


# 预设配置：快速召回模式（SchemaLinking 用）
FAST_RECALL_CONFIG = RetrievalModeConfig(
    mode=RetrievalMode.FAST_RECALL,
    top_k=30,
    timeout_ms=100,
    use_reranker=False,
    reranker_type=None,
    use_cascade=True,
    use_exact_match=True,
    use_fuzzy_match=True,
    use_embedding=True,
    use_keyword=False,  # 快速模式不使用 BM25
    score_threshold=0.3,
    early_stop_threshold=0.9,  # 精确匹配命中时早停
)


# 预设配置：高精度模式（FieldMapper 用）
HIGH_PRECISION_CONFIG = RetrievalModeConfig(
    mode=RetrievalMode.HIGH_PRECISION,
    top_k=10,
    timeout_ms=500,
    use_reranker=True,
    reranker_type="llm",
    use_cascade=False,
    use_exact_match=True,
    use_fuzzy_match=True,
    use_embedding=True,
    use_keyword=True,  # 高精度模式使用 BM25
    score_threshold=0.0,
    early_stop_threshold=0.95,
)


def create_retriever(
    mode: RetrievalMode,
    field_indexer: "FieldIndexer",
    config: Optional[RetrievalModeConfig] = None,
    embedding_provider: Optional[Any] = None,
) -> "BaseRetriever":
    """创建检索器工厂函数
    
    根据检索模式创建相应的检索器。
    
    Args:
        mode: 检索模式
        field_indexer: 字段索引器
        config: 检索模式配置（可选，默认使用预设配置）
        embedding_provider: Embedding 提供者（可选）
    
    Returns:
        配置好的检索器
    
    Examples:
        # 快速召回模式（SchemaLinking）
        retriever = create_retriever(
            mode=RetrievalMode.FAST_RECALL,
            field_indexer=indexer,
        )
        
        # 高精度模式（FieldMapper）
        retriever = create_retriever(
            mode=RetrievalMode.HIGH_PRECISION,
            field_indexer=indexer,
        )
    """
    from tableau_assistant.src.infra.rag.retriever import (
        RetrievalConfig,
        EmbeddingRetriever,
        KeywordRetriever,
        HybridRetriever,
        RetrievalPipeline,
    )
    from tableau_assistant.src.infra.rag.reranker import DefaultReranker, RRFReranker, LLMReranker

    
    # 使用预设配置或自定义配置
    if config is None:
        if mode == RetrievalMode.FAST_RECALL:
            config = FAST_RECALL_CONFIG
        else:
            config = HIGH_PRECISION_CONFIG
    
    # 创建检索配置
    retrieval_config = RetrievalConfig(
        top_k=config.top_k,
        score_threshold=config.score_threshold,
        use_reranker=config.use_reranker,
    )
    
    # 根据模式创建检索器
    if mode == RetrievalMode.FAST_RECALL:
        # 快速召回模式：使用级联检索
        # 目前简化实现：使用 EmbeddingRetriever
        # TODO: 实现 CascadeRetriever
        retriever = EmbeddingRetriever(field_indexer, retrieval_config)
        
        # 快速模式不使用重排序器
        return retriever
    
    else:
        # 高精度模式：使用混合检索 + 重排序
        retriever = HybridRetriever(
            embedding_retriever=EmbeddingRetriever(field_indexer, retrieval_config),
            keyword_retriever=KeywordRetriever(field_indexer, retrieval_config),
            config=retrieval_config,
            use_rrf=True,
        )
        
        # 创建重排序器
        reranker = None
        if config.use_reranker:
            if config.reranker_type == "llm":
                try:
                    from tableau_assistant.src.infra.ai.llm import get_llm

                    llm = get_llm()
                    reranker = LLMReranker(
                        top_k=config.top_k,
                        llm_call_fn=lambda p: llm.invoke(p).content
                    )
                except Exception:
                    # LLM 不可用，降级到 RRF
                    reranker = RRFReranker(top_k=config.top_k)
            elif config.reranker_type == "rrf":
                reranker = RRFReranker(top_k=config.top_k)
            else:
                reranker = DefaultReranker(top_k=config.top_k)
        
        if reranker:
            return RetrievalPipeline(retriever=retriever, reranker=reranker)
        
        return retriever


__all__ = [
    "RetrievalMode",
    "RetrievalModeConfig",
    "FAST_RECALL_CONFIG",
    "HIGH_PRECISION_CONFIG",
    "create_retriever",
]
