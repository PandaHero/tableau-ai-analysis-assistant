"""
知识组装器

提供元数据加载和检索器创建能力。

主要功能：
- 加载数据源元数据
- 支持多种分块策略（by-field, by-table, by-category）
- 创建配置好的检索器实例
- 支持强制重建索引
- 使用 LangGraph SqliteStore 缓存向量索引
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Union

from tableau_assistant.src.infra.ai.rag.models import FieldChunk, RetrievalResult
from tableau_assistant.src.infra.ai.rag.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderFactory,
)
from tableau_assistant.src.infra.ai.rag.field_indexer import FieldIndexer, IndexConfig
from tableau_assistant.src.infra.ai.rag.retriever import (
    BaseRetriever,
    EmbeddingRetriever,
    KeywordRetriever,
    HybridRetriever,
    RetrievalConfig,
    MetadataFilter,
)
from tableau_assistant.src.infra.ai.rag.reranker import BaseReranker
from tableau_assistant.src.core.models import DataModel, FieldMetadata

logger = logging.getLogger(__name__)


class ChunkStrategy(str, Enum):
    """
    分块策略枚举
    
    Attributes:
        BY_FIELD: 按字段分块（每个字段一个分块）
        BY_TABLE: 按表分块（同一表的字段合并）
        BY_CATEGORY: 按类别分块（同一类别的字段合并）
    """
    BY_FIELD = "by-field"
    BY_TABLE = "by-table"
    BY_CATEGORY = "by-category"


@dataclass
class AssemblerConfig:
    """
    组装器配置
    
    Attributes:
        chunk_strategy: 分块策略
        embedding_provider: Embedding 提供者名称 (zhipu/mock)
        index_dir: 索引存储目录
        use_cache: 是否使用向量缓存
        max_samples: 最大样本值数量
        include_formula: 是否包含公式
        include_table_caption: 是否包含表名
        include_category: 是否包含维度类别
    """
    chunk_strategy: ChunkStrategy = ChunkStrategy.BY_FIELD
    embedding_provider: str = "zhipu"  # 默认使用智谱 AI embedding
    index_dir: str = "data/indexes"
    use_cache: bool = True
    max_samples: int = 5
    include_formula: bool = True
    include_table_caption: bool = True
    include_category: bool = True


class KnowledgeAssembler:
    """
    知识组装器
    

    负责加载元数据、构建索引、创建检索器。
    使用 LangGraph SqliteStore 缓存向量索引。
    
    Usage:
        # 创建组装器
        assembler = KnowledgeAssembler(
            datasource_luid="ds-123",
            config=AssemblerConfig(chunk_strategy=ChunkStrategy.BY_FIELD)
        )
        
        # 加载元数据
        assembler.load_metadata(fields)
        
        # 获取检索器
        retriever = assembler.as_retriever(top_k=10)
        
        # 检索
        results = retriever.retrieve("销售额")
    
    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
    """
    
    def __init__(
        self,
        datasource_luid: str,
        config: Optional[AssemblerConfig] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ):
        """
        初始化知识组装器
        
        Args:
            datasource_luid: 数据源 LUID（用作命名空间）
            config: 组装器配置
            embedding_provider: 自定义 Embedding 提供者（优先于配置）
        """
        self.datasource_luid = datasource_luid
        self.config = config or AssemblerConfig()
        
        # 创建 Embedding 提供者
        if embedding_provider:
            self._embedding_provider = embedding_provider
        else:
            self._embedding_provider = EmbeddingProviderFactory.create(
                self.config.embedding_provider
            )
        
        # 创建索引配置
        self._index_config = IndexConfig(
            max_samples=self.config.max_samples,
            include_formula=self.config.include_formula,
            include_table_caption=self.config.include_table_caption,
            include_category=self.config.include_category,
        )
        
        # 创建字段索引器
        self._indexer = FieldIndexer(
            embedding_provider=self._embedding_provider,
            index_config=self._index_config,
            datasource_luid=datasource_luid,
            index_dir=self.config.index_dir,
            use_cache=self.config.use_cache,
        )
        
        # 获取 LangGraph SqliteStore 用于缓存
        self._index_cache = None
        try:
            from tableau_assistant.src.infra.storage import get_langgraph_store, FieldIndexCache
            store = get_langgraph_store()
            self._index_cache = FieldIndexCache(store)
        except Exception as e:
            logger.warning(f"无法获取 FieldIndexCache，将不使用缓存: {e}")
        
        # 元数据存储
        self._fields: List[FieldMetadata] = []
        self._chunks: List[FieldChunk] = []
        self._is_loaded: bool = False
    
    def load_metadata(
        self,
        fields: List[FieldMetadata],
        force_rebuild: bool = False,
    ) -> int:
        """
        加载元数据并构建索引
        
        优先从 SqliteStore 缓存加载，如果缓存命中且元数据未变化则跳过重建。
        
        Args:
            fields: FieldMetadata 列表
            force_rebuild: 是否强制重建索引
        
        Returns:
            索引的字段/分块数量
        
        Requirements: 6.1, 6.3, 6.5
        """
        if not fields:
            logger.warning("字段列表为空")
            return 0
        
        self._fields = fields
        
        # 计算当前元数据哈希
        import hashlib
        import json
        field_data = []
        for f in sorted(fields, key=lambda x: x.name):
            field_data.append({
                "name": f.name,
                "caption": f.fieldCaption,
                "role": f.role,
                "dataType": f.dataType,
            })
        content = json.dumps(field_data, sort_keys=True)
        current_hash = hashlib.md5(content.encode()).hexdigest()
        
        # 尝试从 SqliteStore 缓存加载（如果不是强制重建）
        if not force_rebuild and self._index_cache:
            cached_data = self._index_cache.get(self.datasource_luid)
            if cached_data:
                cached_hash = cached_data.get("metadata_hash")
                if cached_hash == current_hash:
                    # 缓存命中且元数据未变化，恢复索引
                    if self._indexer.restore_from_cache(cached_data):
                        self._is_loaded = True
                        self._chunks = self._indexer.get_all_chunks()
                        logger.info(
                            f"从 SqliteStore 缓存恢复索引: {len(self._chunks)} 个字段, "
                            f"策略: {self.config.chunk_strategy.value}"
                        )
                        return len(self._chunks)
                else:
                    logger.info(f"元数据已变化，需要重建索引 (cached_hash={cached_hash[:8]}..., current_hash={current_hash[:8]}...)")
        
        # 根据分块策略处理字段
        if self.config.chunk_strategy == ChunkStrategy.BY_FIELD:
            chunk_count = self._load_by_field(fields, force_rebuild)
        elif self.config.chunk_strategy == ChunkStrategy.BY_TABLE:
            chunk_count = self._load_by_table(fields, force_rebuild)
        elif self.config.chunk_strategy == ChunkStrategy.BY_CATEGORY:
            chunk_count = self._load_by_category(fields, force_rebuild)
        else:
            # 默认按字段分块
            chunk_count = self._load_by_field(fields, force_rebuild)
        
        self._is_loaded = True
        self._chunks = self._indexer.get_all_chunks()
        
        # 保存到 SqliteStore 缓存
        if self._index_cache and chunk_count > 0:
            cache_data = self._indexer.export_for_cache()
            self._index_cache.put(self.datasource_luid, cache_data)
        
        logger.info(
            f"元数据加载完成: {len(fields)} 个字段, "
            f"{chunk_count} 个分块, 策略: {self.config.chunk_strategy.value}"
        )
        
        return chunk_count
    
    def _load_by_field(self, fields: List[FieldMetadata], force_rebuild: bool) -> int:
        """
        按字段分块加载
        
        每个字段作为一个独立的分块。
        
        Args:
            fields: FieldMetadata 列表
            force_rebuild: 是否强制重建
        
        Returns:
            分块数量
        """
        return self._indexer.index_fields(fields, force_rebuild=force_rebuild)
    
    def _load_by_table(self, fields: List[FieldMetadata], force_rebuild: bool) -> int:
        """
        按表分块加载
        
        同一表的字段合并为一个分块。
        
        Args:
            fields: FieldMetadata 列表
            force_rebuild: 是否强制重建
        
        Returns:
            分块数量
        """
        # 按表分组
        table_fields: Dict[str, List[Any]] = {}
        for field in fields:
            table_id = getattr(field, 'logicalTableId', None) or 'default'
            if table_id not in table_fields:
                table_fields[table_id] = []
            table_fields[table_id].append(field)
        
        # 为每个表创建合并的字段
        merged_fields = []
        for table_id, table_field_list in table_fields.items():
            if table_field_list:
                # 使用第一个字段作为基础，合并其他字段的信息
                merged = self._create_merged_field(
                    table_field_list,
                    group_type="table",
                    group_id=table_id
                )
                merged_fields.append(merged)
        
        return self._indexer.index_fields(merged_fields, force_rebuild=force_rebuild)
    
    def _load_by_category(self, fields: List[FieldMetadata], force_rebuild: bool) -> int:
        """
        按类别分块加载
        
        同一类别的字段合并为一个分块。
        
        Args:
            fields: FieldMetadata 列表
            force_rebuild: 是否强制重建
        
        Returns:
            分块数量
        """
        # 按类别分组
        category_fields: Dict[str, List[Any]] = {}
        for field in fields:
            category = getattr(field, 'category', None) or 'uncategorized'
            if category not in category_fields:
                category_fields[category] = []
            category_fields[category].append(field)
        
        # 为每个类别创建合并的字段
        merged_fields = []
        for category, category_field_list in category_fields.items():
            if category_field_list:
                merged = self._create_merged_field(
                    category_field_list,
                    group_type="category",
                    group_id=category
                )
                merged_fields.append(merged)
        
        return self._indexer.index_fields(merged_fields, force_rebuild=force_rebuild)
    
    def _create_merged_field(
        self,
        fields: List[FieldMetadata],
        group_type: str,
        group_id: str
    ) -> FieldMetadata:
        """
        创建合并的字段对象
        
        使用现有的 FieldMetadata 模型创建合并字段。
        
        Args:
            fields: 要合并的字段列表
            group_type: 分组类型（table/category）
            group_id: 分组 ID
        
        Returns:
            合并后的 FieldMetadata 对象
        """
        # 合并字段信息
        field_names = [f.fieldCaption for f in fields]
        roles = list(set(f.role for f in fields))
        data_types = list(set(f.dataType for f in fields))
        
        # 获取表名（如果是按表分组）
        table_caption = None
        if group_type == "table" and fields:
            table_caption = getattr(fields[0], 'logicalTableCaption', None)
        
        # 确定角色（如果混合则使用 dimension）
        merged_role = roles[0] if len(roles) == 1 else "dimension"
        
        # 创建合并字段（使用 FieldMetadata 模型）
        merged = FieldMetadata(
            name=f"{group_type}_{group_id}",
            fieldCaption=f"{group_type.title()}: {', '.join(field_names[:5])}{'...' if len(field_names) > 5 else ''}",
            role=merged_role,
            dataType=data_types[0] if len(data_types) == 1 else "STRING",
            category=group_id if group_type == "category" else None,
            logicalTableId=group_id if group_type == "table" else None,
            logicalTableCaption=table_caption,
            sample_values=field_names[:10],  # 使用字段名作为样本值
        )
        
        return merged
    
    def as_retriever(
        self,
        retriever_type: str = "hybrid",
        top_k: int = 10,
        score_threshold: float = 0.0,
    ) -> BaseRetriever:
        """
        创建配置好的检索器实例
        
        Args:
            retriever_type: 检索器类型（embedding/keyword/hybrid）
            top_k: 返回结果数量
            score_threshold: 分数阈值
        
        Returns:
            配置好的检索器实例
        
        Requirements: 6.4
        """
        if not self._is_loaded:
            logger.warning("元数据未加载，请先调用 load_metadata()")
        
        # 创建检索配置
        config = RetrievalConfig(
            top_k=top_k,
            score_threshold=score_threshold,
        )
        
        # 创建检索器
        if retriever_type == "embedding":
            return EmbeddingRetriever(
                field_indexer=self._indexer,
                config=config,
            )
        elif retriever_type == "keyword":
            return KeywordRetriever(
                field_indexer=self._indexer,
                config=config,
            )
        else:
            # hybrid（默认）
            if retriever_type != "hybrid":
                logger.warning(f"未知的检索器类型: {retriever_type}，使用 hybrid")
            
            embedding_retriever = EmbeddingRetriever(
                field_indexer=self._indexer,
                config=config,
            )
            keyword_retriever = KeywordRetriever(
                field_indexer=self._indexer,
                config=config,
            )
            return HybridRetriever(
                embedding_retriever=embedding_retriever,
                keyword_retriever=keyword_retriever,
                config=config,
            )
    
    def rebuild_index(self) -> int:
        """
        强制重建索引
        
        Returns:
            重建后的分块数量
        
        Requirements: 6.5
        """
        if not self._fields:
            logger.warning("没有已加载的字段，无法重建索引")
            return 0
        
        # 先使缓存失效
        if self._index_cache:
            self._index_cache.invalidate(self.datasource_luid)
        
        return self.load_metadata(self._fields, force_rebuild=True)
    
    def save_index(self) -> bool:
        """
        保存索引到磁盘
        
        Returns:
            是否保存成功
        
        Requirements: 6.3
        """
        return self._indexer.save_index()
    
    def load_index(self) -> bool:
        """
        从磁盘加载索引
        
        Returns:
            是否加载成功
        
        Requirements: 6.3
        """
        success = self._indexer.load_index()
        if success:
            self._is_loaded = True
            self._chunks = self._indexer.get_all_chunks()
        return success
    
    @property
    def is_loaded(self) -> bool:
        """是否已加载元数据"""
        return self._is_loaded
    
    @property
    def chunk_count(self) -> int:
        """分块数量"""
        return len(self._chunks)
    
    @property
    def field_count(self) -> int:
        """原始字段数量"""
        return len(self._fields)
    
    def get_chunks(self) -> List[FieldChunk]:
        """获取所有分块"""
        return self._chunks.copy()
    
    def get_chunk(self, field_name: str) -> Optional[FieldChunk]:
        """获取指定字段的分块"""
        return self._indexer.get_chunk(field_name)


__all__ = [
    "ChunkStrategy",
    "AssemblerConfig",
    "KnowledgeAssembler",
]
