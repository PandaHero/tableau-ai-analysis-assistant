"""
语义映射能力

提供业务术语到技术字段名的智能映射功能。

主要组件：
- SemanticMapper: 语义映射器，使用 RAG+LLM 混合模型进行字段映射
- EmbeddingsProvider: 嵌入向量提供器
- FieldIndexer: 字段索引器
- VectorStoreManager: 向量存储管理器

使用示例：
    from tableau_assistant.src.capabilities.semantic_mapping import SemanticMapper
    
    mapper = SemanticMapper(metadata=metadata, llm=llm, embeddings_provider=embeddings)
    result = mapper.map_field(business_term="销售额", question_context="各地区的销售额")
"""
from tableau_assistant.src.capabilities.semantic_mapping.semantic_mapper import SemanticMapper
from tableau_assistant.src.capabilities.semantic_mapping.embeddings_provider import EmbeddingsProvider
from tableau_assistant.src.capabilities.semantic_mapping.field_indexer import FieldIndexer
from tableau_assistant.src.capabilities.semantic_mapping.vector_store_manager import VectorStoreManager

__all__ = [
    "SemanticMapper",
    "EmbeddingsProvider",
    "FieldIndexer",
    "VectorStoreManager",
]
