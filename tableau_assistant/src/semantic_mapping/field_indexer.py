"""
Field Indexer - 字段索引构建器

从 Metadata 构建字段向量索引。
"""
import logging
from typing import List
from langchain_core.documents import Document
from tableau_assistant.src.models.metadata import Metadata, FieldMetadata
from tableau_assistant.src.semantic_mapping.vector_store_manager import VectorStoreManager
from tableau_assistant.src.semantic_mapping.embeddings_provider import EmbeddingsProvider

logger = logging.getLogger(__name__)


class FieldIndexer:
    """
    字段索引构建器
    
    功能：
    - 从 Metadata 提取字段信息
    - 构建用于向量化的文本
    - 创建和管理字段向量索引
    """
    
    def __init__(
        self,
        metadata: Metadata,
        embeddings_provider: EmbeddingsProvider
    ):
        """
        初始化 Field Indexer
        
        Args:
            metadata: Metadata 对象
            embeddings_provider: Embeddings Provider 实例
        """
        self.metadata = metadata
        self.embeddings_provider = embeddings_provider
        
        # 创建 Vector Store Manager
        self.vector_store_manager = VectorStoreManager(
            datasource_luid=metadata.datasource_luid,
            embeddings=embeddings_provider.get_embeddings()
        )
    
    def build_index(self, force_rebuild: bool = False) -> VectorStoreManager:
        """
        构建字段向量索引
        
        Args:
            force_rebuild: 是否强制重建索引（默认 False）
        
        Returns:
            VectorStoreManager 实例
        """
        # 检查索引是否已存在
        if self.vector_store_manager.index_exists() and not force_rebuild:
            logger.info(
                f"字段索引已存在: {self.metadata.datasource_name} "
                f"({self.vector_store_manager.get_document_count()} 个字段)"
            )
            return self.vector_store_manager
        
        logger.info(
            f"开始构建字段索引: {self.metadata.datasource_name} "
            f"({self.metadata.field_count} 个字段)"
        )
        
        # 构建文档列表
        documents = self._build_documents()
        
        # 创建索引
        self.vector_store_manager.create_index(documents)
        
        logger.info(
            f"字段索引构建完成: {len(documents)} 个字段已索引"
        )
        
        return self.vector_store_manager
    
    def _build_documents(self) -> List[Document]:
        """
        从 Metadata 构建 Document 列表
        
        Returns:
            Document 列表
        """
        documents = []
        
        for field in self.metadata.fields:
            # 构建索引文本
            index_text = self._build_index_text(field)
            
            # 创建 Document
            doc = Document(
                page_content=index_text,
                metadata={
                    "field_name": field.name,
                    "field_caption": field.fieldCaption,
                    "data_type": field.dataType,
                    "role": field.role,
                    "aggregation": field.aggregation if hasattr(field, 'aggregation') else None,
                    "category": field.category if hasattr(field, 'category') else None,
                    "description": field.description if hasattr(field, 'description') else None
                }
            )
            
            documents.append(doc)
        
        return documents
    
    def _build_index_text(self, field: FieldMetadata) -> str:
        """
        构建用于向量化的文本
        
        策略：
        - 包含字段名、显示名、角色、数据类型
        - 包含类别、描述（如果有）
        - 包含示例值（如果有）
        - 使用空格分隔，便于向量化
        
        Args:
            field: FieldMetadata 对象
        
        Returns:
            索引文本
        """
        parts = []
        
        # 基础信息（必须）
        parts.append(field.fieldCaption)
        parts.append(field.name)
        parts.append(field.role)
        parts.append(field.dataType)
        
        # 聚合函数（如果有）
        if hasattr(field, 'aggregation') and field.aggregation:
            parts.append(field.aggregation)
        
        # 类别（如果有）
        if hasattr(field, 'category') and field.category:
            parts.append(field.category)
        
        # 描述（如果有）
        if hasattr(field, 'description') and field.description:
            parts.append(field.description)
        
        # 示例值（如果有，取前3个）
        if hasattr(field, 'sample_values') and field.sample_values:
            sample_values = field.sample_values[:3]
            parts.extend([str(v) for v in sample_values if v])
        
        # 拼接文本
        index_text = " ".join(parts)
        
        logger.debug(f"字段索引文本: {field.fieldCaption} -> {index_text[:100]}...")
        
        return index_text
    
    def update_field(self, field: FieldMetadata):
        """
        更新单个字段的索引
        
        Args:
            field: 要更新的字段
        """
        # 构建文档
        index_text = self._build_index_text(field)
        doc = Document(
            page_content=index_text,
            metadata={
                "field_name": field.name,
                "field_caption": field.fieldCaption,
                "data_type": field.dataType,
                "role": field.role
            }
        )
        
        # 增量添加
        self.vector_store_manager.add_documents([doc])
        
        logger.info(f"字段索引已更新: {field.fieldCaption}")
    
    def rebuild_index(self):
        """强制重建索引"""
        logger.info("强制重建字段索引")
        self.build_index(force_rebuild=True)
    
    def get_vector_store_manager(self) -> VectorStoreManager:
        """获取 Vector Store Manager 实例"""
        return self.vector_store_manager


# ============= 导出 =============

__all__ = ["FieldIndexer"]
