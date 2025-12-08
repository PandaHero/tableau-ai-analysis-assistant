"""
Tableau Assistant 能力层

提供各种业务能力的实现，包括：

子包：
- data_model: 数据模型管理（获取、缓存、增强）
- query: 查询能力（构建、执行、结果处理）
- date_processing: 日期处理（解析、计算、格式检测）
- data_processing: 数据处理（同比、环比、统计）
- rag: RAG 增强检索（向量检索、语义映射、重排序）
- storage: 持久化存储（SQLite 缓存）

使用示例：
    # 数据模型管理
    from tableau_assistant.src.capabilities.data_model import DataModelManager
    
    # 查询执行
    from tableau_assistant.src.capabilities.query import QueryExecutor, QueryBuilder
    
    # 日期处理
    from tableau_assistant.src.capabilities.date_processing import DateManager
    
    # 数据处理
    from tableau_assistant.src.capabilities.data_processing import DataProcessor
    
    # RAG 增强检索
    from tableau_assistant.src.capabilities.rag import (
        SemanticMapper,
        FieldIndexer,
        EmbeddingProvider,
        KnowledgeAssembler,
    )
    
    # 存储
    from tableau_assistant.src.capabilities.storage import StoreManager
"""

__all__ = [
    "data_model",
    "query",
    "date_processing",
    "data_processing",
    "rag",
    "storage",
]
