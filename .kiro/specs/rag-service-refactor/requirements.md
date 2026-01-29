# 需求文档

## 简介

本文档定义了 RAG（Retrieval-Augmented Generation）模块服务化重构的需求。当前 RAG 模块存在以下问题：

1. **重复造轮子**：`FewShotManager` 没有使用 `infra/rag` 的检索器，自己实现了 `_cosine_similarity()` 方法
2. **向量索引分散管理**：
   - `FieldRetriever` 使用 `fields_{datasource_luid}` 索引
   - `DimensionHierarchyInference` 使用 `dimension_patterns` 索引
   - `FewShotManager` 没有使用向量索引（全量遍历 + 手动计算相似度）
3. **Embedding 调用不统一**：
   - `FewShotManager` 直接调用 `get_embeddings().embed_query()`
   - `DimensionHierarchyInference` 使用 `manager.embed_documents_batch_async()` 批量调用
   - `FieldRetriever` 通过 `CascadeRetriever` 间接调用
4. **相似度计算方式不一致**：
   - `retriever.py` 使用 `1.0 / (1.0 + score)` 转换 FAISS L2 距离
   - `FewShotManager` 使用手动实现的余弦相似度
5. **索引初始化逻辑分散**：
   - `DimensionHierarchyInference._init_rag()` 包含复杂的索引初始化和一致性检查逻辑
   - `RetrieverFactory` 也有索引创建逻辑，两者重复

本次重构旨在将 RAG 功能封装为独立服务，统一索引管理，支持增量索引更新，并统一 Embedding 调用。

## 现有基础设施分析

### 可复用的组件

1. **`infra/rag/retriever.py`**：
   - `ExactRetriever`：O(1) 精确匹配
   - `EmbeddingRetriever`：向量检索
   - `CascadeRetriever`：级联检索（精确 → 向量）
   - `RetrievalPipeline`：检索管道
   - `RetrieverFactory`：检索器工厂

2. **`infra/rag/reranker.py`**：
   - `DefaultReranker`：按分数排序
   - `RRFReranker`：RRF 融合重排序
   - `LLMReranker`：LLM 重排序

3. **`infra/ai/model_manager.py`**：
   - `embed_documents_batch()`：批量 Embedding（已有缓存支持）
   - `embed_documents_batch_async()`：异步批量 Embedding

4. **`infra/storage/langgraph_store.py`**：
   - `get_vector_store()`：向量存储工厂
   - `CacheManager`：缓存管理

### 需要新增的组件

1. **`EmbeddingService`**：统一 Embedding 入口，封装缓存和批量逻辑
2. **`IndexManager`**：统一索引管理，支持增量更新
3. **`RetrievalService`**：统一检索入口，使用一致的相似度计算
4. **`RAGService`**：服务层入口，组合上述组件

## 术语表

- **RAG_Service**: RAG 服务层，提供统一的检索、索引管理、Embedding 调用接口
- **Index_Manager**: 索引管理器，负责向量索引的创建、更新、删除和生命周期管理
- **Embedding_Service**: Embedding 服务，提供统一的向量化接口，支持缓存和批量优化
- **Retrieval_Service**: 检索服务，提供统一的检索接口，支持多种检索策略
- **Index_Registry**: 索引注册表，记录所有索引的元数据和状态
- **Incremental_Update**: 增量更新，只对新增或变更的数据进行向量化和索引更新

## 需求

### 需求 1: 统一 Embedding 服务

**用户故事:** 作为开发者，我希望有一个统一的 Embedding 服务，以便所有组件使用相同的 Embedding 接口，并具有一致的缓存和批量处理策略。

#### 验收标准

1. THE Embedding_Service SHALL 提供统一的 `embed_query(text)` 方法用于单文本向量化
2. THE Embedding_Service SHALL 提供统一的 `embed_documents(texts)` 方法用于批量文本向量化
3. WHEN 进行文本向量化时, THE Embedding_Service SHALL 首先检查缓存，如果缓存命中则直接返回缓存的向量
4. WHEN 缓存未命中时, THE Embedding_Service SHALL 计算向量并将结果存入缓存
5. THE Embedding_Service SHALL 支持可配置的批量大小和并发数用于批量向量化
6. THE Embedding_Service SHALL 提供缓存统计信息，包括命中率、未命中次数和总请求数
7. THE Embedding_Service SHALL 复用 `ModelManager.embed_documents_batch_async()` 的批量处理逻辑
8. THE ModelManager SHALL 返回缓存命中信息，以便 Embedding_Service 统计缓存命中率

### 需求 2: 统一索引管理

**用户故事:** 作为开发者，我希望有一个统一的索引管理系统，以便通过单一接口管理所有向量索引。

#### 验收标准

1. THE Index_Manager SHALL 提供 `create_index(name, config)` 方法用于创建新的向量索引
2. THE Index_Manager SHALL 提供 `get_index(name)` 方法用于获取已有索引
3. THE Index_Manager SHALL 提供 `delete_index(name)` 方法用于删除索引
4. THE Index_Manager SHALL 提供 `list_indexes()` 方法用于列出所有已注册的索引
5. THE Index_Registry SHALL 存储索引元数据，包括名称、创建时间、文档数量和状态
6. WHEN 创建索引时, THE Index_Manager SHALL 将其注册到 Index_Registry
7. WHEN 删除索引时, THE Index_Manager SHALL 将其从 Index_Registry 中移除

### 需求 3: 增量索引更新

**用户故事:** 作为开发者，我希望支持增量索引更新，以便高效更新索引而无需全量重建。

#### 验收标准

1. THE Index_Manager SHALL 提供 `add_documents(index_name, documents)` 方法用于向已有索引添加新文档
2. THE Index_Manager SHALL 提供 `update_documents(index_name, documents)` 方法用于更新已有文档
3. THE Index_Manager SHALL 提供 `delete_documents(index_name, doc_ids)` 方法用于从索引中删除文档
4. WHEN 添加文档时, THE Index_Manager SHALL 仅对新文档计算向量
5. WHEN 更新文档时, THE Index_Manager SHALL 通过比较内容哈希检测变更的文档
6. THE Index_Manager SHALL 将文档哈希注册表持久化到 KV 存储以跟踪文档版本

### 需求 4: 统一检索服务

**用户故事:** 作为开发者，我希望有一个统一的检索服务，以便所有组件使用相同的检索接口和一致的相似度计算。

#### 验收标准

1. THE Retrieval_Service SHALL 提供 `search(index_name, query, top_k)` 方法用于向量搜索
2. THE Retrieval_Service SHALL 提供 `batch_search(index_name, queries, top_k)` 方法用于批量搜索
3. THE Retrieval_Service SHALL 在所有搜索中使用一致的相似度分数归一化公式：`similarity = 1.0 / (1.0 + l2_distance)`
4. WHEN 执行搜索时, THE Retrieval_Service SHALL 返回归一化分数在 [0, 1] 范围内的结果
5. THE Retrieval_Service SHALL 支持可配置的检索策略（精确匹配、向量检索、级联检索）
6. THE Retrieval_Service SHALL 支持搜索查询中的元数据过滤
7. THE Retrieval_Service SHALL 复用现有的 `CascadeRetriever` 和 `RetrievalPipeline`

### 需求 5: 服务化封装

**用户故事:** 作为开发者，我希望 RAG 功能被封装为服务，以便轻松将 RAG 能力集成到不同组件中。

#### 验收标准

1. THE RAG_Service SHALL 提供通过 `get_rag_service()` 函数访问的单例实例
2. THE RAG_Service SHALL 将 Embedding_Service、Index_Manager 和 Retrieval_Service 作为属性暴露
3. THE RAG_Service SHALL 从 `app.yaml` 的 `rag_service` 配置节加载配置
4. THE RAG_Service SHALL 支持延迟初始化以避免启动开销
5. WHEN RAG_Service 初始化时, THE system SHALL 记录初始化状态和配置

### 需求 6: 现有组件迁移

**用户故事:** 作为开发者，我希望现有组件迁移到使用新的 RAG 服务，以便代码库保持一致和可维护。

#### 验收标准

1. THE FieldRetriever 组件 SHALL 使用 RAG_Service 进行字段检索，而不是直接使用 CascadeRetriever
2. THE FewShotManager 组件 SHALL 使用 RAG_Service 进行示例检索，而不是自定义相似度计算
3. THE DimensionHierarchyInference 组件 SHALL 使用 RAG_Service 进行模式检索，而不是直接初始化 RAG
