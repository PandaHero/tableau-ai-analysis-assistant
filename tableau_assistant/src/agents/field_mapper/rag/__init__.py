"""
RAG (Retrieval-Augmented Generation) Package

Provides field semantic retrieval and mapping capabilities.

Main components:
- EmbeddingProvider: Embedding provider abstraction
- FieldIndexer: Field indexer
- SemanticMapper: Semantic mapper
- Retriever: Retriever abstraction layer
- Reranker: Reranker
- KnowledgeAssembler: Knowledge assembler
- CachedEmbeddingProvider: Cached embedding provider (uses LangGraph SqliteStore)

Usage:
    from tableau_assistant.src.agents.field_mapper.rag import (
        EmbeddingProvider,
        ZhipuEmbedding,
        EmbeddingProviderFactory,
    )
    
    # Method 1: Auto-detect available embedding provider (recommended)
    provider = EmbeddingProviderFactory.get_default()
    if provider:
        vectors = provider.embed_documents(["sales", "profit"])
        query_vector = provider.embed_query("sales amount")
    
    # Method 2: Explicitly specify provider
    provider = EmbeddingProviderFactory.create("zhipu")  # or "openai"
"""

from .models import (
    EmbeddingResult,
    RetrievalResult,
    FieldChunk,
    MappingResult,
    RetrievalSource,
)
from .embeddings import (
    EmbeddingProvider,
    ZhipuEmbedding,
    EmbeddingProviderFactory,
)
from .cache import (
    CachedEmbeddingProvider,
)
from .field_indexer import (
    FieldIndexer,
    IndexConfig,
)
from .field_value_indexer import (
    FieldValueIndexer,
    ValueMatchResult,
    DistinctValuesResult,
)
from .semantic_mapper import (
    SemanticMapper,
    MappingConfig,
    FieldMappingResult,
    MappingSource,
)
from .retriever import (
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
from .reranker import (
    BaseReranker,
    DefaultReranker,
    RRFReranker,
    LLMReranker,
)
from .assembler import (
    ChunkStrategy,
    AssemblerConfig,
    KnowledgeAssembler,
)
# MappingCache and CacheManager removed, use LangGraph SqliteStore instead
from .dimension_pattern import (
    DimensionPattern,
    PatternSearchResult,
    DimensionPatternStore,
    DimensionHierarchyRAG,
)
from .observability import (
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
    # Data models
    "EmbeddingResult",
    "RetrievalResult", 
    "FieldChunk",
    "MappingResult",
    "RetrievalSource",
    # Embedding providers
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "EmbeddingProviderFactory",
    # Cache (VectorCache, MappingCache, CacheManager removed, use LangGraph SqliteStore instead)
    "CachedEmbeddingProvider",
    # Indexers
    "FieldIndexer",
    "IndexConfig",
    # Semantic mapper
    "SemanticMapper",
    "MappingConfig",
    "FieldMappingResult",
    "MappingSource",
    # Retrievers
    "BaseRetriever",
    "EmbeddingRetriever",
    "KeywordRetriever",
    "HybridRetriever",
    "RetrievalPipeline",
    "RetrieverFactory",
    "RetrievalConfig",
    "MetadataFilter",
    "Tokenizer",
    # Rerankers
    "BaseReranker",
    "DefaultReranker",
    "RRFReranker",
    "LLMReranker",
    # Knowledge assembler
    "ChunkStrategy",
    "AssemblerConfig",
    "KnowledgeAssembler",
    # Dimension hierarchy RAG
    "DimensionPattern",
    "PatternSearchResult",
    "DimensionPatternStore",
    "DimensionHierarchyRAG",
    # Observability
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
