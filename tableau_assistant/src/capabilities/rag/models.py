"""
RAG 相关数据模型

定义 RAG 系统中使用的数据结构。
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class RetrievalSource(Enum):
    """检索来源"""
    EMBEDDING = "embedding"  # 向量检索
    KEYWORD = "keyword"      # 关键词检索
    HYBRID = "hybrid"        # 混合检索


@dataclass
class EmbeddingResult:
    """
    向量化结果
    
    Attributes:
        text: 原始文本
        vector: 向量表示
        model: 使用的模型名称
        dimensions: 向量维度
    """
    text: str
    vector: List[float]
    model: str
    dimensions: int
    
    def __post_init__(self):
        if len(self.vector) != self.dimensions:
            raise ValueError(
                f"向量维度不匹配: 期望 {self.dimensions}, 实际 {len(self.vector)}"
            )


@dataclass
class FieldChunk:
    """
    字段分块
    
    用于索引的字段信息块。
    
    Attributes:
        field_name: 字段名称
        field_caption: 字段显示名称
        role: 字段角色 (dimension/measure)
        data_type: 数据类型
        index_text: 用于索引的文本（包含所有可搜索信息）
        metadata: 额外元数据
    """
    field_name: str
    field_caption: str
    role: str
    data_type: str
    index_text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 可选字段
    column_class: Optional[str] = None
    category: Optional[str] = None
    formula: Optional[str] = None
    logical_table_id: Optional[str] = None
    logical_table_caption: Optional[str] = None
    sample_values: Optional[List[str]] = None
    
    @classmethod
    def from_field_metadata(
        cls, 
        field_metadata: Any,
        max_samples: int = 5
    ) -> "FieldChunk":
        """
        从 FieldMetadata 创建 FieldChunk
        
        Args:
            field_metadata: FieldMetadata 对象
            max_samples: 最大样本值数量（默认 5）
        
        Returns:
            FieldChunk 实例
        """
        # 构建索引文本
        index_parts = [
            field_metadata.fieldCaption,
            field_metadata.name,
            field_metadata.role,
            field_metadata.dataType,
        ]
        
        # 添加可选信息
        if hasattr(field_metadata, 'category') and field_metadata.category:
            index_parts.append(field_metadata.category)
        
        if hasattr(field_metadata, 'logicalTableCaption') and field_metadata.logicalTableCaption:
            index_parts.append(field_metadata.logicalTableCaption)
        
        if hasattr(field_metadata, 'formula') and field_metadata.formula:
            index_parts.append(field_metadata.formula)
        
        if hasattr(field_metadata, 'sample_values') and field_metadata.sample_values:
            # 取样本值
            samples = field_metadata.sample_values[:max_samples]
            index_parts.extend(samples)
        
        index_text = " | ".join(filter(None, index_parts))
        
        return cls(
            field_name=field_metadata.name,
            field_caption=field_metadata.fieldCaption,
            role=field_metadata.role,
            data_type=field_metadata.dataType,
            index_text=index_text,
            column_class=getattr(field_metadata, 'columnClass', None),
            category=getattr(field_metadata, 'category', None),
            formula=getattr(field_metadata, 'formula', None),
            logical_table_id=getattr(field_metadata, 'logicalTableId', None),
            logical_table_caption=getattr(field_metadata, 'logicalTableCaption', None),
            sample_values=getattr(field_metadata, 'sample_values', None),
            metadata={
                "data_category": getattr(field_metadata, 'dataCategory', None),
                "aggregation": getattr(field_metadata, 'aggregation', None),
            }
        )


@dataclass
class RetrievalResult:
    """
    检索结果
    
    Attributes:
        field_chunk: 字段分块
        score: 归一化置信度 (0-1)
        source: 检索来源
        rank: 排名位置
        raw_score: 原始分数（用于调试），如 FAISS 内积分数
    """
    field_chunk: FieldChunk
    score: float
    source: RetrievalSource
    rank: int
    
    # 原始分数（用于调试）
    raw_score: Optional[float] = None
    
    # 可选的重排序信息
    rerank_score: Optional[float] = None
    original_rank: Optional[int] = None
    
    def __post_init__(self):
        if not 0 <= self.score <= 1:
            raise ValueError(f"分数必须在 0-1 之间: {self.score}")
        if self.rank < 1:
            raise ValueError(f"排名必须 >= 1: {self.rank}")


@dataclass
class MappingResult:
    """
    字段映射结果
    
    Attributes:
        user_field: 用户输入的字段名
        matched_field: 匹配的字段名
        confidence: 置信度 (0-1)
        alternatives: 备选字段列表（低置信度时提供）
        retrieval_results: 原始检索结果
    """
    user_field: str
    matched_field: Optional[str]
    confidence: float
    alternatives: List[str] = field(default_factory=list)
    retrieval_results: List[RetrievalResult] = field(default_factory=list)
    
    @property
    def is_confident(self) -> bool:
        """是否高置信度匹配"""
        return self.confidence >= 0.7
    
    @property
    def needs_disambiguation(self) -> bool:
        """是否需要消歧"""
        return not self.is_confident and len(self.alternatives) > 0


__all__ = [
    "RetrievalSource",
    "EmbeddingResult",
    "FieldChunk",
    "RetrievalResult",
    "MappingResult",
]
