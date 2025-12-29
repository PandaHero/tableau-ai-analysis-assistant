"""
RAG (Retrieval-Augmented Generation) 包

提供字段语义检索和映射能力

主要组件：
- EmbeddingProvider: 向量化提供者抽象
- FieldIndexer: 字段索引器
- SemanticMapper: 语义映射器
- Retriever: 检索器抽象层
- Reranker: 重排序器
- KnowledgeAssembler: 知识组装器
- CacheManager: 缓存管理器

Usage:
    from tableau_assistant.src.infra.ai.rag import (
        EmbeddingProvider,
        ZhipuEmbedding,
        EmbeddingProviderFactory,
    )
    
    # 方式 1: 自动检测可用的 Embedding 提供者（推荐）
    provider = EmbeddingProviderFactory.get_default()
    if provider:
        vectors = provider.embed_documents(["销售额", "利润"])
        query_vector = provider.embed_query("销售金额")
    
    # 方式 2: 显式指定提供者
    provider = EmbeddingProviderFactory.create("zhipu")  # 或 "openai"
"""

from tableau_assistant.src.infra.ai.rag.models import (
    EmbeddingResult,
    RetrievalResult,
    FieldChunk,
    MappingResult,
    RetrievalSource,
)
from tableau_assistant.src.infra.ai.rag.embeddings import (
    EmbeddingProvider,
    ZhipuEmbedding,
    EmbeddingProviderFactory,
)
from tableau_assistant.src.infra.ai.rag.cache import (
    CachedEmbeddingProvider,
)
from tableau_assistant.src.infra.ai.rag.field_indexer import (
    FieldIndexer,
    IndexConfig,
)
from tableau_assistant.src.infra.ai.rag.field_value_indexer import (
    FieldValueIndexer,
    ValueMatchResult,
    DistinctValuesResult,
)
from tableau_assistant.src.infra.ai.rag.semantic_mapper import (
    SemanticMapper,
    MappingConfig,
    FieldMappingResult,
    MappingSource,
)
from tableau_assistant.src.infra.ai.rag.retriever import (
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
from tableau_assistant.src.infra.ai.rag.reranker import (
    BaseReranker,
    DefaultReranker,
    RRFReranker,
    LLMReranker,
)
from tableau_assistant.src.infra.ai.rag.assembler import (
    ChunkStrategy,
    AssemblerConfig,
    KnowledgeAssembler,
)
# MappingCache 和 CacheManager 已删除，使用 LangGraph SqliteStore 替代
from tableau_assistant.src.infra.ai.rag.dimension_pattern import (
    DimensionPattern,
    PatternSearchResult,
    DimensionPatternStore,
    DimensionHierarchyRAG,
)
from tableau_assistant.src.infra.ai.rag.observability import (
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

__all__ = [
    # 数据模型
    "EmbeddingResult",
    "RetrievalResult", 
    "FieldChunk",
    "MappingResult",
    "RetrievalSource",
    # Embedding 提供者
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "EmbeddingProviderFactory",
    # 缓存（VectorCache, MappingCache, CacheManager 已删除，使用 LangGraph SqliteStore 替代）
    "CachedEmbeddingProvider",
    # 索引器
    "FieldIndexer",
    "IndexConfig",
    # 语义映射器
    "SemanticMapper",
    "MappingConfig",
    "FieldMappingResult",
    "MappingSource",
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
    # 知识组装器
    "ChunkStrategy",
    "AssemblerConfig",
    "KnowledgeAssembler",
    # 维度层级 RAG
    "DimensionPattern",
    "PatternSearchResult",
    "DimensionPatternStore",
    "DimensionHierarchyRAG",
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
]
