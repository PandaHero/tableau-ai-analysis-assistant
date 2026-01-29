# 设计文档

## 概述

本设计文档描述了 RAG 模块服务化重构的技术方案。重构的核心目标是将分散的 RAG 功能统一为一个服务层，解决当前存在的重复造轮子、索引分散管理、Embedding 调用不统一等问题。

### 设计目标

1. **统一入口**: 提供 `RAGService` 作为所有 RAG 功能的统一入口
2. **索引集中管理**: 通过 `IndexManager` 统一管理所有向量索引
3. **Embedding 统一**: 通过 `EmbeddingService` 统一所有向量化调用
4. **增量更新**: 支持增量索引更新，避免全量重建

### 设计原则

- 复用现有 `infra/rag` 基础设施（检索器、重排序器）
- 复用现有 `infra/storage` 存储能力（KV 存储、向量存储）
- 复用现有 `infra/ai` 模型管理能力
- 遵循项目编码规范（配置放 app.yaml，不延迟导入等）

## 架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        应用层 (Agents)                           │
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │FieldRetriever│  │FewShotManager   │  │DimensionHierarchy   │  │
│  └──────┬──────┘  └────────┬────────┘  └──────────┬──────────┘  │
│         │                  │                      │              │
│         └──────────────────┼──────────────────────┘              │
│                            ▼                                     │
├─────────────────────────────────────────────────────────────────┤
│                      RAG 服务层 (新增)                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      RAGService                              ││
│  │  ┌─────────────────┐ ┌─────────────┐ ┌───────────────────┐  ││
│  │  │EmbeddingService │ │IndexManager │ │RetrievalService   │  ││
│  │  └────────┬────────┘ └──────┬──────┘ └─────────┬─────────┘  ││
│  │           │                 │                  │             ││
│  └───────────┼─────────────────┼──────────────────┼─────────────┘│
│              │                 │                  │              │
├──────────────┼─────────────────┼──────────────────┼──────────────┤
│              ▼                 ▼                  ▼              │
│                      基础设施层 (infra)                          │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐│
│  │  infra/ai       │ │  infra/storage  │ │  infra/rag          ││
│  │  ModelManager   │ │  get_vector_store│ │  CascadeRetriever   ││
│  │  get_embeddings │ │  CacheManager   │ │  RetrievalPipeline  ││
│  └─────────────────┘ └─────────────────┘ └─────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 目录结构

```
infra/rag/
├── __init__.py           # 导出所有组件（更新）
├── models.py             # 数据模型（保留）
├── retriever.py          # 检索器（保留）
├── reranker.py           # 重排序器（保留）
├── service.py            # RAGService 主服务（新增）
├── embedding_service.py  # EmbeddingService（新增）
├── index_manager.py      # IndexManager（新增）
└── schemas/              # 服务层数据模型（新增）
    ├── __init__.py
    ├── index.py          # 索引相关模型
    └── search.py         # 搜索相关模型
```

## 组件和接口

### 1. RAGService（主服务）

RAGService 是 RAG 功能的统一入口，采用单例模式。

```python
class RAGService:
    """RAG 服务 - 统一入口"""
    
    _instance: Optional["RAGService"] = None
    
    @classmethod
    def get_instance(cls) -> "RAGService":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @property
    def embedding(self) -> EmbeddingService:
        """Embedding 服务"""
        ...
    
    @property
    def index(self) -> IndexManager:
        """索引管理器"""
        ...
    
    @property
    def retrieval(self) -> RetrievalService:
        """检索服务"""
        ...


def get_rag_service() -> RAGService:
    """获取 RAG 服务实例（便捷函数）"""
    return RAGService.get_instance()
```

### 2. EmbeddingService（Embedding 服务）

统一的 Embedding 服务，封装 `ModelManager` 的批量 Embedding 能力，提供统一的缓存统计信息。

**缓存策略决策**：复用 `ModelManager.embed_documents_batch()` 内置的缓存，通过修改 `ModelManager` 返回缓存命中信息来支持统计。

```python
@dataclass
class EmbeddingResult:
    """Embedding 结果（包含缓存信息）"""
    vectors: List[List[float]]
    cache_hits: int
    cache_misses: int


@dataclass
class EmbeddingStats:
    """Embedding 统计"""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    
    @property
    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total


class EmbeddingService:
    """统一的 Embedding 服务
    
    封装 ModelManager 的 Embedding 能力，提供统一的缓存统计信息。
    
    缓存策略：
    - 复用 ModelManager.embed_documents_batch() 内置的缓存
    - ModelManager 返回缓存命中信息，EmbeddingService 统计
    
    与 ModelManager 的关系：
    - ModelManager 负责模型配置、API 调用、缓存
    - EmbeddingService 负责业务层的统一入口和统计
    """
    
    def __init__(self):
        # 复用 ModelManager 的 Embedding 能力
        self._model_manager = get_model_manager()
        self._stats = EmbeddingStats()
    
    def embed_query(self, text: str) -> List[float]:
        """单文本向量化
        
        委托给 ModelManager，利用其内置缓存。
        """
        self._stats.total_requests += 1
        # ModelManager 返回 EmbeddingResult，包含缓存命中信息
        result = self._model_manager.embed_documents_batch_with_stats(
            texts=[text],
            use_cache=True,
        )
        self._stats.cache_hits += result.cache_hits
        self._stats.cache_misses += result.cache_misses
        return result.vectors[0] if result.vectors else []
    
    def embed_documents(
        self,
        texts: List[str],
        batch_size: int = 20,
        max_concurrency: int = 5,
    ) -> List[List[float]]:
        """批量文本向量化
        
        委托给 ModelManager.embed_documents_batch_with_stats()。
        """
        self._stats.total_requests += len(texts)
        result = self._model_manager.embed_documents_batch_with_stats(
            texts=texts,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            use_cache=True,
        )
        self._stats.cache_hits += result.cache_hits
        self._stats.cache_misses += result.cache_misses
        return result.vectors
    
    async def embed_documents_async(
        self,
        texts: List[str],
        batch_size: int = 20,
        max_concurrency: int = 5,
    ) -> List[List[float]]:
        """异步批量文本向量化
        
        委托给 ModelManager.embed_documents_batch_with_stats_async()。
        """
        self._stats.total_requests += len(texts)
        result = await self._model_manager.embed_documents_batch_with_stats_async(
            texts=texts,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            use_cache=True,
        )
        self._stats.cache_hits += result.cache_hits
        self._stats.cache_misses += result.cache_misses
        return result.vectors
    
    def get_stats(self) -> EmbeddingStats:
        """获取统计信息"""
        return self._stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = EmbeddingStats()
```

### 3. IndexManager（索引管理器）

统一的索引管理，支持增量更新。

**职责边界**：
- `IndexManager`：管理 What（元数据、注册、生命周期、增量更新）
- `RetrieverFactory`：管理 How（创建检索器实例、向量存储）
- IndexManager 内部调用 RetrieverFactory 来创建检索器

**文档哈希持久化策略**：
- 文档哈希注册表持久化到 KV 存储，key 格式为 `doc_hashes:{index_name}`
- 启动时从 KV 存储加载已有的哈希注册表
- 每次更新后同步写入 KV 存储
- 分离 `content_hash` 和 `metadata_hash`，只有内容变化才重新向量化

```python
class IndexManager:
    """索引管理器
    
    职责：
    1. 索引元数据管理（IndexInfo 注册表）
    2. 索引生命周期（创建、删除、状态追踪）
    3. 增量更新（文档哈希、变更检测）
    4. 持久化协调（委托给 RetrieverFactory）
    5. 启动时加载已有索引（懒加载模式）
    
    不负责：
    - 检索器实例创建（委托给 RetrieverFactory）
    - 向量存储创建（委托给 get_vector_store）
    """
    
    def __init__(self, registry_namespace: str = "index_registry"):
        self._registry = CacheManager(registry_namespace)
        self._indexes: Dict[str, CascadeRetriever] = {}
        # 文档哈希注册表（持久化到 KV 存储）
        # 格式: {index_name: {doc_id: {"content": hash, "metadata": hash}}}
        self._doc_hashes: Dict[str, Dict[str, Dict[str, str]]] = {}
        self._doc_hash_namespace = "rag_doc_hashes"
        self._load_doc_hashes()  # 启动时加载
        # 注意：索引实例采用懒加载模式，不在初始化时加载
        # 调用 get_index() 时如果内存中没有，会尝试从持久化存储加载
    
    def _load_doc_hashes(self) -> None:
        """从 KV 存储加载文档哈希注册表"""
        ...
    
    def _save_doc_hashes(self, index_name: str) -> None:
        """将指定索引的文档哈希保存到 KV 存储"""
        ...
    
    def _load_index_from_storage(self, name: str) -> Optional[CascadeRetriever]:
        """从持久化存储加载索引（懒加载）
        
        当 get_index() 发现内存中没有索引时调用。
        
        实现流程：
        1. 从 IndexRegistry 获取 IndexInfo
        2. 如果不存在，返回 None
        3. 根据 IndexInfo.config.persist_directory 加载 FAISS 索引
        4. 使用 RetrieverFactory 重建检索器实例
        5. 缓存到 _indexes[name]
        """
        # 1. 检查注册表
        index_info = self._registry.get(name)
        if index_info is None:
            return None
        
        # 2. 使用 RetrieverFactory 加载已有索引
        from analytics_assistant.src.infra.rag import RetrieverFactory
        
        try:
            retriever = RetrieverFactory.create_cascade_retriever(
                fields=[],  # 空列表，因为是加载已有索引
                collection_name=name,
                persist_directory=index_info.config.persist_directory,
                force_rebuild=False,  # 不重建，加载已有
            )
            
            # 3. 缓存到内存
            self._indexes[name] = retriever
            return retriever
            
        except Exception as e:
            logger.warning(f"加载索引 '{name}' 失败: {e}")
            return None
    
    def create_index(
        self,
        name: str,
        config: IndexConfig,
        documents: Optional[List[IndexDocument]] = None,
    ) -> IndexInfo:
        """创建索引
        
        实现流程：
        1. 将 IndexDocument 转换为 RetrieverFactory 所需的 fields 格式
        2. 调用 RetrieverFactory.create_cascade_retriever() 创建检索器
        3. 注册索引元数据到 IndexRegistry
        4. 缓存检索器实例
        5. 初始化文档哈希表（用于增量更新）
        """
        from analytics_assistant.src.infra.rag import RetrieverFactory
        
        # 1. 转换文档格式
        fields = self._convert_documents_to_fields(documents)
        
        # 2. 使用 RetrieverFactory 创建检索器
        retriever = RetrieverFactory.create_cascade_retriever(
            fields=fields,
            collection_name=name,
            persist_directory=config.persist_directory,
            force_rebuild=False,
        )
        
        # 3. 注册元数据
        index_info = IndexInfo(
            name=name,
            config=config,
            status=IndexStatus.READY,
            document_count=len(documents) if documents else 0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self._registry.put(name, index_info)
        
        # 4. 缓存检索器实例
        self._indexes[name] = retriever
        
        # 5. 初始化文档哈希表
        if documents:
            self._doc_hashes[name] = {
                doc.id: {
                    "content": doc.content_hash,
                    "metadata": doc.metadata_hash,
                }
                for doc in documents
            }
            self._save_doc_hashes(name)
        
        return index_info
    
    def _convert_documents_to_fields(
        self, documents: Optional[List[IndexDocument]]
    ) -> List[Dict]:
        """将 IndexDocument 转换为 RetrieverFactory 所需的 fields 格式"""
        if not documents:
            return []
        
        fields = []
        for doc in documents:
            field = {
                "field_name": doc.id,
                "field_caption": doc.content[:50],
                "index_text": doc.content,
                "metadata": doc.metadata,
            }
            fields.append(field)
        return fields
    
    def get_index(self, name: str) -> Optional[CascadeRetriever]:
        """获取检索器实例（懒加载）
        
        如果内存中没有，尝试从持久化存储加载。
        """
        if name in self._indexes:
            return self._indexes[name]
        
        # 尝试从持久化存储加载
        return self._load_index_from_storage(name)
    
    def delete_index(self, name: str) -> bool:
        """删除索引"""
        ...
    
    def list_indexes(self) -> List[IndexInfo]:
        """列出所有索引"""
        ...
    
    def add_documents(
        self,
        index_name: str,
        documents: List[IndexDocument],
    ) -> int:
        """添加文档（增量）"""
        ...
    
    def update_documents(
        self,
        index_name: str,
        documents: List[IndexDocument],
    ) -> UpdateResult:
        """更新文档（增量）
        
        增量更新策略：
        1. 比较 content_hash：变化则重新向量化
        2. 比较 metadata_hash：仅元数据变化则只更新元数据，不重新向量化
        3. 两者都没变：跳过
        """
        result = UpdateResult()
        existing_hashes = self._doc_hashes.get(index_name, {})
        
        docs_to_reindex = []  # 需要重新向量化
        docs_to_update_metadata = []  # 仅更新元数据
        
        for doc in documents:
            old_hash_data = existing_hashes.get(doc.id)
            
            if old_hash_data is None:
                # 新文档
                docs_to_reindex.append(doc)
                result.added += 1
            else:
                old_content_hash = old_hash_data.get("content")
                old_metadata_hash = old_hash_data.get("metadata")
                
                if doc.content_hash != old_content_hash:
                    # 内容变化 → 重新向量化
                    docs_to_reindex.append(doc)
                    result.updated += 1
                elif doc.metadata_hash != old_metadata_hash:
                    # 仅元数据变化 → 更新元数据，不重新向量化
                    docs_to_update_metadata.append(doc)
                    result.metadata_only_updated += 1
                else:
                    # 完全没变
                    result.unchanged += 1
        
        # 批量重新向量化
        if docs_to_reindex:
            self._reindex_documents(index_name, docs_to_reindex)
            for doc in docs_to_reindex:
                existing_hashes[doc.id] = {
                    "content": doc.content_hash,
                    "metadata": doc.metadata_hash,
                }
        
        # 批量更新元数据（不重新向量化）
        if docs_to_update_metadata:
            self._update_metadata_only(index_name, docs_to_update_metadata)
            for doc in docs_to_update_metadata:
                existing_hashes[doc.id]["metadata"] = doc.metadata_hash
        
        self._doc_hashes[index_name] = existing_hashes
        self._save_doc_hashes(index_name)
        return result
    
    def _reindex_documents(
        self, index_name: str, documents: List[IndexDocument]
    ) -> None:
        """重新向量化并更新索引"""
        ...
    
    def _update_metadata_only(
        self, index_name: str, documents: List[IndexDocument]
    ) -> None:
        """仅更新元数据（不重新向量化）"""
        ...
    
    def delete_documents(
        self,
        index_name: str,
        doc_ids: List[str],
    ) -> int:
        """删除文档"""
        ...
    
    def get_index_info(self, name: str) -> Optional[IndexInfo]:
        """获取索引信息"""
        ...
```

### 4. RetrievalService（检索服务）

统一的检索服务，复用现有的 `CascadeRetriever` 和 `RetrievalPipeline`。

**接口适配策略**：
- RetrievalService 作为适配层，将统一的 `search()` 接口转换为 `CascadeRetriever.retrieve()` 调用
- filters 格式转换：`Dict[str, Any]` → `MetadataFilter`
- 返回结果转换：`RetrievalResult` → `SearchResult`
- 分数归一化已在 CascadeRetriever 中完成，直接使用

```python
class RetrievalService:
    """检索服务 - 适配层
    
    复用现有的检索器实现：
    - ExactRetriever：O(1) 精确匹配
    - EmbeddingRetriever：向量检索
    - CascadeRetriever：级联检索
    - RetrievalPipeline：检索管道（支持重排序）
    
    统一的相似度归一化公式（已在 CascadeRetriever 中实现）：
    - FAISS L2 距离: similarity = 1.0 / (1.0 + distance)
    - 内积: similarity = (score + 1.0) / 2.0
    - 余弦: similarity = (score + 1.0) / 2.0
    """
    
    # 统一的相似度归一化公式
    SCORE_FORMULAS = {
        "l2": lambda d: 1.0 / (1.0 + d),
        "inner_product": lambda s: (s + 1.0) / 2.0,
        "cosine": lambda s: (s + 1.0) / 2.0,
    }
    
    def __init__(self, index_manager: IndexManager, embedding_service: EmbeddingService):
        self._index_manager = index_manager
        self._embedding_service = embedding_service
    
    def search(
        self,
        index_name: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: float = 0.0,
        strategy: str = "cascade",
    ) -> List[SearchResult]:
        """向量搜索
        
        Args:
            index_name: 索引名称
            query: 查询文本
            top_k: 返回结果数量
            filters: 元数据过滤条件
            score_threshold: 分数阈值
            strategy: 检索策略
                - "cascade": 级联检索（精确匹配 → 向量检索，默认）
                - "exact": 仅精确匹配（O(1) 哈希查找）
                - "embedding": 仅向量检索
        
        实现流程：
        1. 从 IndexManager 获取检索器实例（CascadeRetriever）
        2. 转换 filters 格式（Dict → MetadataFilter）
        3. 根据 strategy 选择检索方式：
           - cascade: 调用 CascadeRetriever.retrieve()
           - exact: 调用 CascadeRetriever._exact.retrieve()
           - embedding: 调用 CascadeRetriever._embedding.retrieve()
        4. 转换返回结果（RetrievalResult → SearchResult）
        """
        # 1. 获取检索器
        retriever = self._index_manager.get_index(index_name)
        if retriever is None:
            raise IndexNotFoundError(f"Index '{index_name}' not found")
        
        # 2. 转换 filters 格式
        metadata_filter = self._convert_filters(filters) if filters else None
        
        # 3. 根据 strategy 选择检索方式
        if strategy == "exact":
            # 仅精确匹配
            retrieval_results = retriever._exact.retrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
            )
        elif strategy == "embedding":
            # 仅向量检索
            retrieval_results = retriever._embedding.retrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        else:
            # 默认：级联检索
            retrieval_results = retriever.retrieve(
                query=query,
                top_k=top_k,
                filters=metadata_filter,
                score_threshold=score_threshold,
            )
        
        # 4. 转换返回结果
        return self._convert_results(retrieval_results)
    
    def _convert_filters(self, filters: Dict[str, Any]) -> "MetadataFilter":
        """将 Dict 格式转换为 MetadataFilter"""
        from analytics_assistant.src.infra.rag import MetadataFilter
        return MetadataFilter(
            role=filters.get("role"),
            data_type=filters.get("data_type"),
            category=filters.get("category"),
        )
    
    def _convert_results(
        self, retrieval_results: List["RetrievalResult"]
    ) -> List[SearchResult]:
        """将 RetrievalResult 转换为 SearchResult"""
        search_results = []
        for rank, result in enumerate(retrieval_results, start=1):
            # 分数已经在 retriever 中归一化，直接使用
            search_results.append(SearchResult(
                doc_id=result.field_chunk.field_name,
                content=result.field_chunk.index_text,
                score=result.score,  # 已归一化
                rank=rank,
                metadata={
                    "role": result.field_chunk.role,
                    "data_type": result.field_chunk.data_type,
                    "category": result.field_chunk.category,
                    **result.field_chunk.metadata,
                },
                raw_score=result.raw_score,
            ))
        return search_results
    
    async def search_async(
        self,
        index_name: str,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        score_threshold: float = 0.0,
        strategy: str = "cascade",
    ) -> List[SearchResult]:
        """异步向量搜索
        
        复用 CascadeRetriever.aretrieve()。
        """
        retriever = self._index_manager.get_index(index_name)
        if retriever is None:
            raise IndexNotFoundError(f"Index '{index_name}' not found")
        
        metadata_filter = self._convert_filters(filters) if filters else None
        
        retrieval_results = await retriever.aretrieve(
            query=query,
            top_k=top_k,
            filters=metadata_filter,
            score_threshold=score_threshold,
        )
        
        return self._convert_results(retrieval_results)
    
    def batch_search(
        self,
        index_name: str,
        queries: List[str],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[SearchResult]]:
        """批量搜索
        
        复用 RetrievalPipeline.batch_search()。
        """
        results = {}
        for query in queries:
            results[query] = self.search(
                index_name=index_name,
                query=query,
                top_k=top_k,
                filters=filters,
            )
        return results
    
    async def batch_search_async(
        self,
        index_name: str,
        queries: List[str],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[SearchResult]]:
        """异步批量搜索"""
        import asyncio
        tasks = [
            self.search_async(index_name, query, top_k, filters)
            for query in queries
        ]
        results_list = await asyncio.gather(*tasks)
        return dict(zip(queries, results_list))
    
    @staticmethod
    def normalize_score(raw_score: float, score_type: str = "l2") -> float:
        """归一化分数到 [0, 1] 范围
        
        使用统一的公式，替代各组件的不同实现。
        注意：CascadeRetriever 已经做了归一化，此方法仅供外部使用。
        """
        formula = RetrievalService.SCORE_FORMULAS.get(score_type)
        if formula:
            return max(0.0, min(1.0, formula(raw_score)))
        return max(0.0, min(1.0, raw_score))
```

## 数据模型

### 索引相关模型

```python
# infra/rag/schemas/index.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class IndexStatus(str, Enum):
    """索引状态"""
    CREATING = "creating"
    READY = "ready"
    UPDATING = "updating"
    ERROR = "error"
    DELETED = "deleted"


class IndexBackend(str, Enum):
    """索引后端"""
    FAISS = "faiss"
    CHROMA = "chroma"


@dataclass
class IndexConfig:
    """索引配置"""
    backend: IndexBackend = IndexBackend.FAISS
    persist_directory: Optional[str] = None
    embedding_model_id: Optional[str] = None
    
    # 检索配置
    default_top_k: int = 10
    score_threshold: float = 0.0
    
    # 元数据字段
    metadata_fields: List[str] = field(default_factory=list)


@dataclass
class IndexDocument:
    """索引文档"""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 缓存哈希（私有字段，懒加载）
    _content_hash: Optional[str] = field(default=None, init=False, repr=False)
    _metadata_hash: Optional[str] = field(default=None, init=False, repr=False)
    
    @property
    def content_hash(self) -> str:
        """内容哈希（懒加载，只计算一次）
        
        只基于 content 计算，不包含 metadata。
        内容变化才需要重新向量化。
        """
        if self._content_hash is None:
            import hashlib
            self._content_hash = hashlib.md5(self.content.encode()).hexdigest()
        return self._content_hash
    
    @property
    def metadata_hash(self) -> str:
        """元数据哈希（懒加载）
        
        只基于 metadata 计算。
        元数据变化不需要重新向量化，只更新元数据。
        """
        if self._metadata_hash is None:
            import hashlib
            meta_str = str(sorted(self.metadata.items()))
            self._metadata_hash = hashlib.md5(meta_str.encode()).hexdigest()
        return self._metadata_hash


@dataclass
class IndexInfo:
    """索引信息"""
    name: str
    config: IndexConfig
    status: IndexStatus
    document_count: int
    created_at: datetime
    updated_at: datetime
    
    # 统计信息
    total_searches: int = 0
    last_search_at: Optional[datetime] = None


@dataclass
class UpdateResult:
    """更新结果"""
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    metadata_only_updated: int = 0  # 仅元数据变化（不重新向量化）
    failed: int = 0
```

### 搜索相关模型

```python
# infra/rag/schemas/search.py

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class SearchResult:
    """搜索结果"""
    doc_id: str
    content: str
    score: float  # 归一化分数 [0, 1]
    rank: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 原始分数（用于调试）
    raw_score: Optional[float] = None


# 注意：EmbeddingResult 和 EmbeddingStats 定义在 EmbeddingService 类中
# 不在 schemas/search.py 中重复定义，避免重复
```

### ModelManager 扩展

为支持 EmbeddingService 的缓存统计功能，需要扩展 ModelManager：

```python
# infra/ai/model_manager.py（扩展）

@dataclass
class EmbeddingResult:
    """Embedding 结果（包含缓存信息）"""
    vectors: List[List[float]]
    cache_hits: int
    cache_misses: int


class ModelManager:
    """模型管理器（扩展）"""
    
    def embed_documents_batch_with_stats(
        self,
        texts: List[str],
        batch_size: int = 20,
        max_concurrency: int = 5,
        use_cache: bool = True,
    ) -> EmbeddingResult:
        """批量 Embedding，返回缓存命中信息
        
        与 embed_documents_batch() 类似，但返回 EmbeddingResult 包含：
        - vectors: 向量列表
        - cache_hits: 缓存命中次数
        - cache_misses: 缓存未命中次数
        
        实现逻辑：
        1. 遍历 texts，检查每个文本是否在缓存中
        2. 统计 cache_hits 和 cache_misses
        3. 对未命中的文本调用 API 计算向量
        4. 将新计算的向量写入缓存
        5. 返回 EmbeddingResult
        """
        ...
    
    async def embed_documents_batch_with_stats_async(
        self,
        texts: List[str],
        batch_size: int = 20,
        max_concurrency: int = 5,
        use_cache: bool = True,
    ) -> EmbeddingResult:
        """异步批量 Embedding，返回缓存命中信息"""
        ...
```

## 配置

在 `app.yaml` 中添加 `rag_service` 配置节：

```yaml
# app.yaml

rag_service:
  # 索引管理配置
  index:
    registry_namespace: "rag_index_registry"
    doc_hash_namespace: "rag_doc_hashes"  # 文档哈希持久化命名空间
    default_backend: "faiss"
    persist_directory: "analytics_assistant/data/indexes"
  
  # Embedding 配置（由 ModelManager 管理，此处仅为文档说明）
  embedding:
    # 注意：Embedding 缓存由 ModelManager 管理，不在 RAGService 层配置
    # ModelManager 的缓存配置在 ai.embedding 节
    batch_size: 20
    max_concurrency: 5
  
  # 检索服务配置
  retrieval:
    default_top_k: 10
    score_threshold: 0.0
    score_type: "l2"  # l2, inner_product, cosine
  
  # 预定义索引
  indexes:
    fields:
      backend: "faiss"
      persist_directory: "analytics_assistant/data/indexes"
    dimension_patterns:
      backend: "faiss"
      persist_directory: "analytics_assistant/data/indexes"
    few_shot_examples:
      backend: "faiss"
      persist_directory: "analytics_assistant/data/indexes"
```


## 正确性属性

*正确性属性是一种特征或行为，应该在系统的所有有效执行中保持为真——本质上是关于系统应该做什么的形式化陈述。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*

### Property 1: Embedding 缓存往返

*For any* 文本字符串，首次调用 `embed_query(text)` 后再次调用相同文本，应该命中缓存并返回相同的向量。

**Validates: Requirements 1.3, 1.4**

### Property 2: Embedding 统计一致性

*For any* 一系列 Embedding 调用，统计信息中的 `total_requests` 应该等于 `cache_hits + cache_misses`。

**Validates: Requirements 1.6**

### Property 3: 索引创建-获取往返

*For any* 索引名称和配置，创建索引后调用 `get_index(name)` 应该返回非空结果，且索引信息应该出现在 `list_indexes()` 结果中。

**Validates: Requirements 2.2, 2.4, 2.6**

### Property 4: 索引删除后不可获取

*For any* 已创建的索引，删除后调用 `get_index(name)` 应该返回空结果，且索引信息不应该出现在 `list_indexes()` 结果中。

**Validates: Requirements 2.3, 2.7**

### Property 5: 索引元数据完整性

*For any* 创建的索引，其 `IndexInfo` 应该包含所有必需字段：name、config、status、document_count、created_at、updated_at。

**Validates: Requirements 2.5**

### Property 6: 增量添加文档

*For any* 索引和文档列表，添加文档后索引的 `document_count` 应该增加相应数量，且只有新文档会触发向量计算。

**Validates: Requirements 3.1, 3.4**

### Property 7: 增量更新文档

*For any* 索引和文档列表，更新文档时只有内容哈希变化的文档才会被更新，未变化的文档保持不变。

**Validates: Requirements 3.2, 3.5**

### Property 8: 文档删除

*For any* 索引和文档 ID 列表，删除文档后索引的 `document_count` 应该减少相应数量。

**Validates: Requirements 3.3**

### Property 9: 文档哈希跟踪

*For any* 添加到索引的文档，应该能够通过文档 ID 查询到其内容哈希值。

**Validates: Requirements 3.6**

### Property 10: 搜索分数归一化

*For any* 搜索结果，其 `score` 字段应该在 [0, 1] 范围内。

**Validates: Requirements 4.3, 4.4**

### Property 11: 元数据过滤正确性

*For any* 带有元数据过滤条件的搜索，返回的所有结果应该满足过滤条件。

**Validates: Requirements 4.6**

### Property 12: RAG 服务单例

*For any* 多次调用 `get_rag_service()`，应该返回同一个实例（对象 ID 相同）。

**Validates: Requirements 5.1**

## 错误处理

### 1. Embedding 服务错误处理

| 错误场景 | 处理策略 |
|---------|---------|
| Embedding API 调用失败 | 重试 3 次，失败后抛出 `EmbeddingError` |
| 缓存读取失败 | 记录警告日志，继续计算向量 |
| 缓存写入失败 | 记录警告日志，返回计算结果 |
| 批量处理部分失败 | 返回成功的结果，记录失败的文本 |

### 2. 索引管理错误处理

| 错误场景 | 处理策略 |
|---------|---------|
| 创建已存在的索引 | 抛出 `IndexExistsError` |
| 获取不存在的索引 | 返回 `None` |
| 删除不存在的索引 | 返回 `False` |
| 向量存储创建失败 | 抛出 `IndexCreationError` |
| 持久化目录不可写 | 抛出 `StorageError` |

### 3. 检索服务错误处理

| 错误场景 | 处理策略 |
|---------|---------|
| 索引不存在 | 抛出 `IndexNotFoundError` |
| 查询向量化失败 | 抛出 `EmbeddingError` |
| 向量搜索失败 | 记录错误日志，返回空结果 |
| 分数归一化溢出 | 截断到 [0, 1] 范围 |

### 4. 自定义异常

```python
# infra/rag/exceptions.py

class RAGError(Exception):
    """RAG 服务基础异常"""
    pass


class EmbeddingError(RAGError):
    """Embedding 相关错误"""
    pass


class IndexError(RAGError):
    """索引相关错误"""
    pass


class IndexExistsError(IndexError):
    """索引已存在"""
    pass


class IndexNotFoundError(IndexError):
    """索引不存在"""
    pass


class IndexCreationError(IndexError):
    """索引创建失败"""
    pass


class StorageError(RAGError):
    """存储相关错误"""
    pass


class RetrievalError(RAGError):
    """检索相关错误"""
    pass
```

## 测试策略

### 单元测试

单元测试用于验证具体示例和边界情况：

1. **EmbeddingService 单元测试**
   - 测试单文本向量化返回正确维度
   - 测试批量向量化返回正确数量的向量
   - 测试空文本处理
   - 测试超长文本处理

2. **IndexManager 单元测试**
   - 测试创建索引成功
   - 测试创建重复索引抛出异常
   - 测试删除不存在的索引返回 False
   - 测试空文档列表处理

3. **RetrievalService 单元测试**
   - 测试搜索返回正确数量的结果
   - 测试空索引搜索返回空结果
   - 测试 top_k 参数生效
   - 测试分数阈值过滤

### 属性测试

属性测试用于验证通用属性，使用 Hypothesis 库：

1. **Embedding 缓存属性测试**
   - Property 1: 缓存往返
   - Property 2: 统计一致性

2. **索引管理属性测试**
   - Property 3: 创建-获取往返
   - Property 4: 删除后不可获取
   - Property 5: 元数据完整性
   - Property 6: 增量添加
   - Property 7: 增量更新
   - Property 8: 文档删除
   - Property 9: 哈希跟踪

3. **检索服务属性测试**
   - Property 10: 分数归一化
   - Property 11: 元数据过滤

4. **服务层属性测试**
   - Property 12: 单例模式

### 测试配置

- 属性测试最少运行 100 次迭代
- 每个属性测试需要标注对应的设计文档属性编号
- 标注格式: `**Feature: rag-service-refactor, Property {number}: {property_text}**`

### 集成测试

1. **端到端流程测试**
   - 创建索引 → 添加文档 → 搜索 → 验证结果
   - 创建索引 → 更新文档 → 搜索 → 验证更新生效

2. **组件迁移测试**
   - 验证 FieldRetriever 使用 RAG_Service 后功能正常
   - 验证 FewShotManager 使用 RAG_Service 后功能正常
   - 验证 DimensionHierarchyInference 使用 RAG_Service 后功能正常


## RAG 工作流详解

本节详细描述重构后 RAG 系统的完整工作流，包括缓存、持久化、索引管理等各个环节。

### 整体数据流架构

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              应用层调用                                          │
│  FieldRetriever / FewShotManager / DimensionHierarchyInference                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           RAGService (单例)                                      │
│  ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────────────┐│
│  │  EmbeddingService   │ │   IndexManager      │ │   RetrievalService          ││
│  │  • embed_query()    │ │   • create_index()  │ │   • search()                ││
│  │  • embed_documents()│ │   • get_index()     │ │   • search_async()          ││
│  │  • get_stats()      │ │   • update_docs()   │ │   • batch_search()          ││
│  └──────────┬──────────┘ └──────────┬──────────┘ └─────────────┬───────────────┘│
└─────────────┼────────────────────────┼─────────────────────────┼────────────────┘
              │                        │                         │
              ▼                        ▼                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              基础设施层                                          │
│  ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────────────┐│
│  │   ModelManager      │ │  RetrieverFactory   │ │   CascadeRetriever          ││
│  │   (Embedding缓存)   │ │  (检索器创建)        │ │   (检索执行)                 ││
│  └──────────┬──────────┘ └──────────┬──────────┘ └─────────────┬───────────────┘│
│             │                       │                          │                │
│             ▼                       ▼                          ▼                │
│  ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────────────┐│
│  │   CacheManager      │ │   get_vector_store  │ │   ExactRetriever            ││
│  │   (SQLite KV)       │ │   (FAISS/Chroma)    │ │   EmbeddingRetriever        ││
│  └──────────┬──────────┘ └──────────┬──────────┘ └─────────────────────────────┘│
└─────────────┼────────────────────────┼──────────────────────────────────────────┘
              │                        │
              ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              持久化层                                            │
│  ┌─────────────────────────────────┐ ┌─────────────────────────────────────────┐│
│  │   SQLite (storage.db)           │ │   文件系统 (data/indexes/)              ││
│  │   • Embedding 缓存              │ │   • FAISS 索引文件 (.faiss)             ││
│  │   • 索引注册表                   │ │   • Chroma 持久化目录                   ││
│  │   • 文档哈希表                   │ │                                         ││
│  └─────────────────────────────────┘ └─────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 工作流 1：索引创建流程

```
用户调用: rag_service.index.create_index("fields_xxx", config, documents)
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 1: IndexManager.create_index()                                             │
│   • 检查索引是否已存在（查询 IndexRegistry）                                      │
│   • 如果存在，抛出 IndexExistsError                                              │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 2: 转换文档格式                                                             │
│   • IndexDocument → RetrieverFactory 所需的 fields 格式                          │
│   • 提取 id, content, metadata                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 3: RetrieverFactory.create_cascade_retriever()                             │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ 3.1 构建 chunks 和 metadata                                              │   │
│   │     • 为每个 field 创建 FieldChunk                                       │   │
│   │     • 提取 index_text 用于向量化                                         │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                     │                                           │
│                                     ▼                                           │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ 3.2 检查索引是否已存在（文件系统）                                        │   │
│   │     • 检查 persist_directory/{collection_name}.faiss 是否存在            │   │
│   │     • 如果存在且 force_rebuild=False，加载已有索引                        │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                     │                                           │
│                                     ▼                                           │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ 3.3 创建向量存储 (get_vector_store)                                      │   │
│   │     • 调用 EmbeddingService.embed_documents() 向量化所有文本              │   │
│   │       └─→ ModelManager.embed_documents_batch_with_stats()                │   │
│   │           └─→ 检查缓存 → 未命中则调用 API → 写入缓存                      │   │
│   │     • 创建 FAISS/Chroma 向量存储                                         │   │
│   │     • 持久化到文件系统                                                    │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                     │                                           │
│                                     ▼                                           │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ 3.4 创建检索器实例                                                        │   │
│   │     • ExactRetriever(chunks) - 精确匹配                                   │   │
│   │     • EmbeddingRetriever(vector_store, chunks) - 向量检索                 │   │
│   │     • CascadeRetriever(exact, embedding) - 级联检索                       │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 4: 注册索引元数据                                                           │
│   • 创建 IndexInfo（name, config, status, document_count, timestamps）          │
│   • 写入 IndexRegistry（SQLite KV 存储）                                         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 5: 初始化文档哈希表                                                         │
│   • 为每个文档计算 content_hash 和 metadata_hash                                 │
│   • 存储到 _doc_hashes[index_name]                                              │
│   • 持久化到 KV 存储（namespace="rag_doc_hashes"）                               │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 6: 缓存检索器实例                                                           │
│   • 存储到 IndexManager._indexes[name]                                          │
│   • 后续检索直接使用内存中的实例                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 工作流 2：检索流程

```
用户调用: rag_service.retrieval.search("fields_xxx", "销售额", top_k=10)
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 1: RetrievalService.search()                                               │
│   • 从 IndexManager 获取检索器实例                                               │
│   • 如果索引不存在，抛出 IndexNotFoundError                                       │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 2: 转换 filters 格式                                                        │
│   • Dict[str, Any] → MetadataFilter                                             │
│   • 例如: {"role": "measure"} → MetadataFilter(role="measure")                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 3: CascadeRetriever.retrieve()                                             │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ 3.1 ExactRetriever（精确匹配）                                           │   │
│   │     • O(1) 哈希查找                                                      │   │
│   │     • 如果精确匹配成功，直接返回（score=1.0）                              │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                     │                                           │
│                                     ▼ (未命中)                                   │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ 3.2 EmbeddingRetriever（向量检索）                                       │   │
│   │     • 向量化查询文本                                                      │   │
│   │       └─→ EmbeddingService.embed_query("销售额")                         │   │
│   │           └─→ ModelManager（检查缓存 → 命中则返回 / 未命中则调用API）      │   │
│   │     • FAISS 相似度搜索                                                    │   │
│   │     • 分数归一化: similarity = 1.0 / (1.0 + l2_distance)                 │   │
│   │     • 应用 score_threshold 过滤                                          │   │
│   │     • 应用 metadata_filter 过滤                                          │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 4: 转换返回结果                                                             │
│   • RetrievalResult → SearchResult                                              │
│   • 添加 rank 字段                                                               │
│   • 保留 raw_score 用于调试                                                      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 工作流 3：增量更新流程

```
用户调用: rag_service.index.update_documents("fields_xxx", updated_documents)
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 1: 加载已有文档哈希                                                         │
│   • 从 _doc_hashes[index_name] 获取                                             │
│   • 格式: {doc_id: {"content": hash, "metadata": hash}}                         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 2: 变更检测（遍历每个文档）                                                  │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ Case A: doc_id 不存在于已有哈希表                                         │   │
│   │   → 新文档，加入 docs_to_reindex                                         │   │
│   │   → result.added += 1                                                    │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ Case B: content_hash 变化                                                │   │
│   │   → 内容变化，需要重新向量化                                              │   │
│   │   → 加入 docs_to_reindex                                                 │   │
│   │   → result.updated += 1                                                  │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ Case C: 仅 metadata_hash 变化                                            │   │
│   │   → 仅元数据变化，不需要重新向量化                                         │   │
│   │   → 加入 docs_to_update_metadata                                         │   │
│   │   → result.metadata_only_updated += 1                                    │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │ Case D: 两个哈希都没变                                                    │   │
│   │   → 跳过                                                                 │   │
│   │   → result.unchanged += 1                                                │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 3: 批量重新向量化（docs_to_reindex）                                        │
│   • 调用 EmbeddingService.embed_documents([doc.content for doc in ...])         │
│   • 更新 FAISS 索引中的向量                                                      │
│   • 更新哈希表                                                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 4: 批量更新元数据（docs_to_update_metadata）                                │
│   • 直接更新 chunks 中的 metadata 字段                                           │
│   • 不调用 Embedding API（节省成本）                                             │
│   • 更新哈希表中的 metadata_hash                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ Step 5: 持久化哈希表                                                             │
│   • 将更新后的哈希表写入 KV 存储                                                  │
│   • key: "doc_hashes:{index_name}"                                              │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 缓存层级说明

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              缓存架构（单层）                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    ModelManager Embedding 缓存                           │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │   │
│  │  │  存储位置: SQLite (storage.db)                                   │    │   │
│  │  │  命名空间: "embedding"                                           │    │   │
│  │  │  TTL: 86400 秒（24小时）                                         │    │   │
│  │  │  Key: MD5(text)                                                  │    │   │
│  │  │  Value: List[float] (向量)                                       │    │   │
│  │  └─────────────────────────────────────────────────────────────────┘    │   │
│  │                                                                          │   │
│  │  缓存流程:                                                               │   │
│  │  1. 计算 cache_key = MD5(text)                                          │   │
│  │  2. 查询缓存: cache.get(cache_key)                                      │   │
│  │  3. 命中 → 返回缓存向量，cache_hits += 1                                 │   │
│  │  4. 未命中 → 调用 API，写入缓存，cache_misses += 1                       │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    EmbeddingService 统计层                               │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │   │
│  │  │  不做缓存，只做统计                                               │    │   │
│  │  │  • total_requests: 总请求数                                      │    │   │
│  │  │  • cache_hits: 缓存命中数（从 ModelManager 获取）                 │    │   │
│  │  │  • cache_misses: 缓存未命中数（从 ModelManager 获取）             │    │   │
│  │  │  • hit_rate: cache_hits / (cache_hits + cache_misses)            │    │   │
│  │  └─────────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 持久化存储说明

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              持久化存储架构                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  1. SQLite KV 存储 (analytics_assistant/data/storage.db)                │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │   │
│  │  │  命名空间                    │ 内容                              │    │   │
│  │  │  ─────────────────────────────────────────────────────────────  │    │   │
│  │  │  "embedding"                │ Embedding 向量缓存                │    │   │
│  │  │  "rag_index_registry"       │ 索引元数据（IndexInfo）           │    │   │
│  │  │  "rag_doc_hashes"           │ 文档哈希表                        │    │   │
│  │  │  "dimension_patterns_meta"  │ 维度模式元数据                    │    │   │
│  │  │  "few_shot"                 │ Few-shot 示例元数据               │    │   │
│  │  └─────────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │  2. 文件系统 (analytics_assistant/data/indexes/)                        │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │   │
│  │  │  文件                        │ 内容                              │    │   │
│  │  │  ─────────────────────────────────────────────────────────────  │    │   │
│  │  │  fields_{luid}.faiss        │ 字段索引向量                      │    │   │
│  │  │  dimension_patterns.faiss   │ 维度模式索引向量                  │    │   │
│  │  │  few_shot_{luid}.faiss      │ Few-shot 示例索引向量             │    │   │
│  │  │  *.pkl                      │ FAISS 索引元数据                  │    │   │
│  │  └─────────────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 索引生命周期状态机

```
                    ┌─────────────┐
                    │   (初始)    │
                    └──────┬──────┘
                           │ create_index()
                           ▼
                    ┌─────────────┐
                    │  CREATING   │
                    └──────┬──────┘
                           │ 创建成功
                           ▼
    ┌──────────────────────────────────────────────┐
    │                                              │
    │  ┌─────────────┐                             │
    │  │    READY    │◄────────────────────────────┤
    │  └──────┬──────┘                             │
    │         │                                    │
    │         │ update_documents()                 │
    │         ▼                                    │
    │  ┌─────────────┐                             │
    │  │  UPDATING   │─────────────────────────────┘
    │  └──────┬──────┘     更新完成
    │         │
    │         │ 更新失败
    │         ▼
    │  ┌─────────────┐
    │  │    ERROR    │
    │  └─────────────┘
    │
    │  delete_index()
    │         │
    │         ▼
    │  ┌─────────────┐
    └─►│   DELETED   │
       └─────────────┘
```

### 组件职责边界总结

| 组件 | 职责 | 不负责 |
|------|------|--------|
| **RAGService** | 单例入口、组件组合、配置加载 | 具体业务逻辑 |
| **EmbeddingService** | 统一入口、统计信息 | 缓存（委托给 ModelManager） |
| **IndexManager** | 元数据管理、生命周期、增量更新、哈希跟踪 | 检索器创建（委托给 RetrieverFactory） |
| **RetrievalService** | 接口适配、结果转换 | 检索执行（委托给 CascadeRetriever） |
| **RetrieverFactory** | 检索器实例创建、向量存储创建 | 元数据管理、增量更新 |
| **ModelManager** | Embedding API 调用、缓存 | 业务层统计 |
| **CascadeRetriever** | 检索执行、分数归一化 | 索引管理 |
