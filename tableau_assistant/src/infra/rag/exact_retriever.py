"""
精确匹配检索器

实现 O(1) 精确匹配检索，用于 SchemaLinking 与 FieldMapper 的精确匹配路径。


性能目标：10000 字段下耗时 < 1ms

Requirements: 17.7.2 - 融合 SchemaLinking 的优化到统一 RAG
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from tableau_assistant.src.infra.rag.models import FieldChunk, RetrievalResult, RetrievalSource


logger = logging.getLogger(__name__)


@dataclass
class ExactRetrieverConfig:
    """精确匹配检索器配置
    
    Attributes:
        case_sensitive: 是否区分大小写（默认 False）
        match_caption_first: 是否优先匹配 caption（默认 True）
    """
    case_sensitive: bool = False
    match_caption_first: bool = True


class ExactRetriever:
    """精确匹配检索器 - O(1) 哈希查找
    
    实现精确匹配索引，支持：
    1. 字段名（name）精确匹配
    2. 字段标题（caption）精确匹配
    
    性能目标：10000 字段下精确匹配耗时 < 1ms
    
    Usage:
        retriever = ExactRetriever()
        retriever.build_index(fields)
        
        # 精确匹配
        results = retriever.retrieve("销售额")
    """
    
    def __init__(self, config: Optional[ExactRetrieverConfig] = None):
        """初始化精确匹配检索器
        
        Args:
            config: 检索器配置
        """
        self.config = config or ExactRetrieverConfig()
        
        # 精确匹配索引 O(1)
        self._name_index: Dict[str, FieldChunk] = {}  # field.name.lower() -> FieldChunk
        self._caption_index: Dict[str, FieldChunk] = {}  # field.caption.lower() -> FieldChunk
        
        # 索引统计
        self._field_count: int = 0
    
    def build_index(self, fields: List[Any]) -> None:
        """构建索引
        
        Args:
            fields: 字段元数据列表（FieldMetadata 或 FieldChunk）
        """
        # 清空现有索引
        self._name_index.clear()
        self._caption_index.clear()
        
        for field_obj in fields:
            # 支持 FieldMetadata 和 FieldChunk 两种输入
            if isinstance(field_obj, FieldChunk):
                chunk = field_obj
                field_name = chunk.field_name
                field_caption = chunk.field_caption
            else:
                # FieldMetadata
                chunk = FieldChunk.from_field_metadata(field_obj)
                field_name = field_obj.name
                field_caption = getattr(field_obj, 'fieldCaption', '') or ''
            
            # 构建索引键
            if self.config.case_sensitive:
                name_key = field_name
                caption_key = field_caption
            else:
                name_key = field_name.lower()
                caption_key = field_caption.lower() if field_caption else ''
            
            # 精确匹配索引
            self._name_index[name_key] = chunk
            if caption_key:
                self._caption_index[caption_key] = chunk
        
        self._field_count = len(fields)
        
        logger.debug(
            f"ExactRetriever built: {self._field_count} fields, "
            f"{len(self._name_index)} names, {len(self._caption_index)} captions"
        )
    
    def retrieve(
        self,
        query: str,
        top_k: int = 1,
    ) -> List[RetrievalResult]:
        """精确匹配检索 O(1)
        
        先匹配 caption，再匹配 name。
        
        Args:
            query: 搜索词
            top_k: 返回数量（精确匹配通常只返回 1 个）
        
        Returns:
            检索结果列表
        """
        if not query:
            return []
        
        # 构建查询键
        if self.config.case_sensitive:
            query_key = query
        else:
            query_key = query.lower()
        
        chunk = None
        
        # 优先匹配 caption（用户更可能使用显示名称）
        if self.config.match_caption_first:
            if query_key in self._caption_index:
                chunk = self._caption_index[query_key]
            elif query_key in self._name_index:
                chunk = self._name_index[query_key]
        else:
            if query_key in self._name_index:
                chunk = self._name_index[query_key]
            elif query_key in self._caption_index:
                chunk = self._caption_index[query_key]
        
        if chunk is None:
            return []
        
        # 精确匹配：置信度 1.0
        return [RetrievalResult(
            field_chunk=chunk,
            score=1.0,
            source=RetrievalSource.EXACT,
            rank=1,
            raw_score=1.0,
            original_term=query,
        )]
    
    async def aretrieve(
        self,
        query: str,
        top_k: int = 1,
    ) -> List[RetrievalResult]:
        """异步精确匹配检索
        
        精确匹配是 O(1) 操作，无需真正异步。
        
        Args:
            query: 搜索词
            top_k: 返回数量
        
        Returns:
            检索结果列表
        """
        return self.retrieve(query, top_k)
    
    def get_chunk(self, field_name: str) -> Optional[FieldChunk]:
        """根据字段名获取 FieldChunk
        
        Args:
            field_name: 字段名
        
        Returns:
            FieldChunk，未找到返回 None
        """
        key = field_name if self.config.case_sensitive else field_name.lower()
        return self._name_index.get(key)
    
    @property
    def field_count(self) -> int:
        """获取索引的字段数量"""
        return self._field_count


__all__ = [
    "ExactRetriever",
    "ExactRetrieverConfig",
]
