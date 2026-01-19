"""
统一 RAG (Retrieval-Augmented Generation) 基础设施

本模块提供统一的字段语义检索和映射能力，支持两种检索模式：
- FAST_RECALL: 快速召回模式（SchemaLinking 用）
- HIGH_PRECISION: 高精度模式（FieldMapper 用）

主要组件：
- 数据模型：FieldChunk, RetrievalResult, EmbeddingResult
- 索引器：FieldIndexer (FAISS + 持久化)
- 检索器：BaseRetriever, EmbeddingRetriever, KeywordRetriever, HybridRetriever
- 重排序器：BaseReranker, RRFReranker, LLMReranker
- 嵌入提供者：EmbeddingProvider, CachedEmbeddingProvider
- 可观测性：RAGMetrics, RAGObserver

新增组件（来自 SchemaLinking 优化）：
- ExactRetriever: O(1) 精确匹配检索器
- BatchEmbeddingOptimizer: 批量 Embedding 优化器
- CascadeRetriever: 级联检索器（早停优化）

Usage:
    from tableau_assistant.src.infra.rag import (
        FieldIndexer,
        create_retriever,
        RetrievalMode,
    )
    
    # 创建索引器
    indexer = FieldIndexer()
    indexer.index_fields(fields)
    
    # 快速召回模式（SchemaLinking）
    retriever = create_retriever(mode=RetrievalMode.FAST_RECALL, field_indexer=indexer)
    results = await retriever.aretrieve("销售额")
    
    # 高精度模式（FieldMapper）
    retriever = create_retriever(mode=RetrievalMode.HIGH_PRECISION, field_indexer=indexer)
    results = await retriever.aretrieve("销售额")
"""

# 数据模型
from tableau_assistant.src.infra.rag.models import (
    EmbeddingResult,
    RetrievalResult,
    FieldChunk,
    MappingResult,
    RetrievalSource,
)

# 嵌入提供者
from tableau_assistant.src.infra.rag.embeddings import (
    EmbeddingProvider,
    ZhipuEmbedding,
    EmbeddingProviderFactory,
)

# 缓存
from tableau_assistant.src.infra.rag.cache import (
    CachedEmbeddingProvider,
)

# 索引器
from tableau_assistant.src.infra.rag.field_indexer import (
    FieldIndexer,
    IndexConfig,
)

# 检索器
from tableau_assistant.src.infra.rag.retriever import (
    BaseRetriever,
    EmbeddingRetriever,
    KeywordRetriever,
    HybridRetriever,
    RetrievalPipeline,
    RetrieverFactory,
    RetrievalConfig,
    MetadataFilter,
    Tokenizer,
)

# 重排序器
from tableau_assistant.src.infra.rag.reranker import (
    BaseReranker,
    DefaultReranker,
    RRFReranker,
    LLMReranker,
)

# 可观测性
from tableau_assistant.src.infra.rag.observability import (
    RAGStage,
    RetrievalLogEntry,
    RerankLogEntry,
    ErrorLogEntry,
    RAGMetrics,
    RAGObserver,
    get_observer,
    set_verbose,
    observe_retrieval,
)

# 检索模式配置
from tableau_assistant.src.infra.rag.config import (
    RetrievalMode,
    FAST_RECALL_CONFIG,
    HIGH_PRECISION_CONFIG,
    create_retriever,
)

# 新增：精确匹配检索器
from tableau_assistant.src.infra.rag.exact_retriever import (
    ExactRetriever,
    ExactRetrieverConfig,
)

# 新增：批量 Embedding 优化器
from tableau_assistant.src.infra.rag.batch_optimizer import (
    BatchEmbeddingOptimizer,
    BatchEmbeddingConfig,
)


__all__ = [
    # 数据模型
    "EmbeddingResult",
    "RetrievalResult",
    "FieldChunk",
    "MappingResult",
    "RetrievalSource",
    # 嵌入提供者
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "EmbeddingProviderFactory",
    # 缓存
    "CachedEmbeddingProvider",
    # 索引器
    "FieldIndexer",
    "IndexConfig",
    # 检索器
    "BaseRetriever",
    "EmbeddingRetriever",
    "KeywordRetriever",
    "HybridRetriever",
    "RetrievalPipeline",
    "RetrieverFactory",
    "RetrievalConfig",
    "MetadataFilter",
    "Tokenizer",
    # 重排序器
    "BaseReranker",
    "DefaultReranker",
    "RRFReranker",
    "LLMReranker",
    # 可观测性
    "RAGStage",
    "RetrievalLogEntry",
    "RerankLogEntry",
    "ErrorLogEntry",
    "RAGMetrics",
    "RAGObserver",
    "get_observer",
    "set_verbose",
    "observe_retrieval",
    # 检索模式配置
    "RetrievalMode",
    "FAST_RECALL_CONFIG",
    "HIGH_PRECISION_CONFIG",
    "create_retriever",
    # 精确匹配检索器
    "ExactRetriever",
    "ExactRetrieverConfig",
    # 批量 Embedding 优化器
    "BatchEmbeddingOptimizer",
    "BatchEmbeddingConfig",
]
