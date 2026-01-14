"""
RAG (Retrieval-Augmented Generation) Package

⚠️ 注意：核心 RAG 组件已迁移到 infra/rag/
本模块保留向后兼容性，从 infra/rag 重新导出。

推荐直接使用：
    from tableau_assistant.src.infra.rag import (
        FieldIndexer,
        create_retriever,
        RetrievalMode,
    )

FieldMapper 专用组件（保留在此处）：
- KnowledgeAssembler: 知识组装器
- DimensionPattern: 维度模式
- FieldValueIndexer: 字段值索引
- SemanticMapper: 语义映射器
"""

# 从 infra/rag 重新导出核心组件（向后兼容）
from tableau_assistant.src.infra.rag import (
    # 数据模型
    EmbeddingResult,
    RetrievalResult,
    FieldChunk,
    MappingResult,
    RetrievalSource,
    # 嵌入提供者
    EmbeddingProvider,
    ZhipuEmbedding,
    EmbeddingProviderFactory,
    # 缓存
    CachedEmbeddingProvider,
    # 索引器
    FieldIndexer,
    IndexConfig,
    # 检索器
    BaseRetriever,
    EmbeddingRetriever,
    KeywordRetriever,
    HybridRetriever,
    RetrievalPipeline,
    RetrieverFactory,
    RetrievalConfig,
    MetadataFilter,
    Tokenizer,
    # 重排序器
    BaseReranker,
    DefaultReranker,
    RRFReranker,
    LLMReranker,
    # 可观测性
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

# FieldMapper 专用组件（保留在此处）
from .assembler import (
    ChunkStrategy,
    AssemblerConfig,
    KnowledgeAssembler,
)
from .dimension_pattern import (
    DimensionPattern,
    PatternSearchResult,
    DimensionPatternStore,
    DimensionHierarchyRAG,
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

__all__ = [
    # 数据模型（从 infra/rag 重新导出）
    "EmbeddingResult",
    "RetrievalResult", 
    "FieldChunk",
    "MappingResult",
    "RetrievalSource",
    # 嵌入提供者（从 infra/rag 重新导出）
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "EmbeddingProviderFactory",
    # 缓存（从 infra/rag 重新导出）
    "CachedEmbeddingProvider",
    # 索引器（从 infra/rag 重新导出）
    "FieldIndexer",
    "IndexConfig",
    # 检索器（从 infra/rag 重新导出）
    "BaseRetriever",
    "EmbeddingRetriever",
    "KeywordRetriever",
    "HybridRetriever",
    "RetrievalPipeline",
    "RetrieverFactory",
    "RetrievalConfig",
    "MetadataFilter",
    "Tokenizer",
    # 重排序器（从 infra/rag 重新导出）
    "BaseReranker",
    "DefaultReranker",
    "RRFReranker",
    "LLMReranker",
    # FieldMapper 专用组件
    "ChunkStrategy",
    "AssemblerConfig",
    "KnowledgeAssembler",
    "DimensionPattern",
    "PatternSearchResult",
    "DimensionPatternStore",
    "DimensionHierarchyRAG",
    "FieldValueIndexer",
    "ValueMatchResult",
    "DistinctValuesResult",
    "SemanticMapper",
    "MappingConfig",
    "FieldMappingResult",
    "MappingSource",
    # 可观测性（从 infra/rag 重新导出）
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
