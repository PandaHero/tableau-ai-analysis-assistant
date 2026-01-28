# -*- coding: utf-8 -*-
"""
FieldMapper Agent

将业务术语映射到技术字段名。

策略：
1. 缓存查找：检查 CacheManager 缓存
2. 精确匹配：如果术语与 field_name 或 field_caption 完全匹配，直接返回
3. RAG 检索：使用 infra/rag 的 UnifiedRetriever
4. 快速路径：置信度 >= 0.9，直接返回
5. LLM 回退：置信度 < 0.9，使用 LLM 从候选中选择

使用示例：
    from analytics_assistant.src.agents.field_mapper import (
        field_mapper_node,
        FieldMapperNode,
        MappedQuery,
        FieldMapping,
    )
    
    # 在 StateGraph 中使用
    graph.add_node("field_mapper", field_mapper_node)
"""

from .schemas import (
    FieldMappingConfig,
    FieldCandidate,
    SingleSelectionResult,
    AlternativeMapping,
    FieldMapping,
    MappedQuery,
)

from .node import (
    FieldMapperNode,
    field_mapper_node,
)

__all__ = [
    # 配置
    "FieldMappingConfig",
    
    # 数据模型
    "FieldCandidate",
    "SingleSelectionResult",
    "AlternativeMapping",
    "FieldMapping",
    "MappedQuery",
    
    # 节点
    "FieldMapperNode",
    "field_mapper_node",
]
