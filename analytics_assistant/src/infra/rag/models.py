"""
RAG 相关数据模型

定义 RAG 系统中使用的数据结构。
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum

from analytics_assistant.src.infra.config import get_config

import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_confidence_threshold() -> float:
    """获取字段映射高置信度阈值。"""
    try:
        config = get_config()
        return config.config.get("field_mapper", {}).get("low_confidence_threshold", 0.7)
    except Exception as e:
        logger.warning(f"获取置信度阈值失败，使用默认值: {e}")
        return 0.7


class RetrievalSource(Enum):
    """检索来源"""
    EMBEDDING = "embedding"  # 向量检索
    KEYWORD = "keyword"      # 关键词检索
    BM25 = "bm25"            # BM25 关键词检索
    HYBRID = "hybrid"        # 混合检索
    EXACT = "exact"          # 精确匹配
    FUZZY = "fuzzy"          # 模糊匹配
    CASCADE = "cascade"      # 级联检索


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
                f"向量维度不匹配：期望 {self.dimensions}, 实际 {len(self.vector)}"
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
        
        支持两种字段格式：
        - 旧格式：fieldCaption, dataType 等
        - 新格式：caption, data_type 等（core/schemas/data_model.py 的 Field）
        - 字典格式：直接从字典获取值
        
        Args:
            field_metadata: FieldMetadata 对象或字典
            max_samples: 最大样本值数量（默认 5）
        
        Returns:
            FieldChunk 实例
        """
        # 辅助函数：从对象或字典获取属性
        def get_attr(obj: Any, *names, default=None):
            """从对象或字典中获取属性，支持多个候选名称"""
            for name in names:
                if isinstance(obj, dict):
                    if name in obj:
                        return obj[name]
                else:
                    if hasattr(obj, name):
                        return getattr(obj, name)
            return default
        
        # 兼容新旧格式和字典格式
        field_name = get_attr(field_metadata, 'name', 'field_name', default='')
        field_caption = get_attr(
            field_metadata, 'caption', 'fieldCaption', 'field_caption', default=field_name
        )
        role = get_attr(field_metadata, 'role', default='dimension')
        data_type = get_attr(
            field_metadata, 'data_type', 'dataType', default='string'
        )
        
        # 构建索引文本
        index_parts = [
            field_caption,
            field_name,
            role,
            data_type,
        ]
        
        # 添加可选信息
        category = get_attr(field_metadata, 'category', default=None)
        if category:
            index_parts.append(category)
        
        logical_table_caption = get_attr(
            field_metadata, 'logical_table_caption', 'logicalTableCaption', default=None
        )
        if logical_table_caption:
            index_parts.append(logical_table_caption)
        
        formula = get_attr(field_metadata, 'calculation', 'formula', default=None)
        if formula:
            index_parts.append(formula)
        
        sample_values = get_attr(field_metadata, 'sample_values', default=None)
        if sample_values:
            # 取样本值
            samples = sample_values[:max_samples]
            index_parts.extend(samples)
        
        index_text = " | ".join(filter(None, index_parts))
        
        logical_table_id = get_attr(
            field_metadata, 'logical_table_id', 'logicalTableId', default=None
        )
        
        return cls(
            field_name=field_name,
            field_caption=field_caption,
            role=role,
            data_type=data_type,
            index_text=index_text,
            column_class=get_attr(field_metadata, 'columnClass', 'column_class', default=None),
            category=category,
            formula=formula,
            logical_table_id=logical_table_id,
            logical_table_caption=logical_table_caption,
            sample_values=sample_values,
            metadata={
                "data_category": get_attr(field_metadata, 'data_category', 'dataCategory', default=None),
                "aggregation": get_attr(field_metadata, 'aggregation', default=None),
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
    
    # 原始术语（用于追溯）
    original_term: Optional[str] = None
    
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
        return self.confidence >= _get_confidence_threshold()
    
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
