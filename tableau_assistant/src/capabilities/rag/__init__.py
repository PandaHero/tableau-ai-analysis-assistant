"""
RAG (Retrieval-Augmented Generation) 包

提供字段语义检索和映射能力，参考 DB-GPT 的 RAG 实现模式。

主要组件：
- EmbeddingProvider: 向量化提供者抽象
- FieldIndexer: 字段索引器
- SemanticMapper: 语义映射器
- Retriever: 检索器抽象层
- Reranker: 重排序器
- KnowledgeAssembler: 知识组装器
- CacheManager: 缓存管理器

Usage:
    from tableau_assistant.src.capabilities.rag import (
        EmbeddingProvider,
        ZhipuEmbedding,
        EmbeddingProviderFactory,
    )
    
    # 创建 Embedding 提供者
    provider = EmbeddingProviderFactory.create("zhipu")
    
    # 向量化文档
    vectors = provider.embed_documents(["销售额", "利润"])
    
    # 向量化查询
    query_vector = provider.embed_query("销售金额")
"""

from tableau_assistant.src.capabilities.rag.models import (
    EmbeddingResult,
    RetrievalResult,
    FieldChunk,
    MappingResult,
    RetrievalSource,
)
from tableau_assistant.src.capabilities.rag.embeddings import (
    EmbeddingProvider,
    ZhipuEmbedding,
    MockEmbedding,
    EmbeddingProviderFactory,
)
from tableau_assistant.src.capabilities.rag.cache import (
    VectorCache,
    CachedEmbeddingProvider,
)
from tableau_assistant.src.capabilities.rag.field_indexer import (
    FieldIndexer,
    IndexConfig,
)
from tableau_assistant.src.capabilities.rag.semantic_mapper import (
    SemanticMapper,
    MappingConfig,
    FieldMappingResult,
    MappingSource,
)
from tableau_assistant.src.capabilities.rag.retriever import (
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
from tableau_assistant.src.capabilities.rag.reranker import (
    BaseReranker,
    DefaultReranker,
    RRFReranker,
    LLMReranker,
    RerankerFactory,
)
from tableau_assistant.src.capabilities.rag.assembler import (
    ChunkStrategy,
    AssemblerConfig,
    KnowledgeAssembler,
)
from tableau_assistant.src.capabilities.rag.cache import (
    MappingCache,
    CacheManager,
)
from tableau_assistant.src.capabilities.rag.dimension_pattern import (
    DimensionPattern,
    PatternSearchResult,
    DimensionPatternStore,
    DimensionHierarchyRAG,
)
from tableau_assistant.src.capabilities.rag.observability import (
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
    "MockEmbedding",
    "EmbeddingProviderFactory",
    # 缓存
    "VectorCache",
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
    "RerankerFactory",
    # 知识组装器
    "ChunkStrategy",
    "AssemblerConfig",
    "KnowledgeAssembler",
    # 缓存管理器
    "MappingCache",
    "CacheManager",
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
