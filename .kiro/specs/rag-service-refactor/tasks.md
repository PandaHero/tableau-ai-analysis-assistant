# 实现计划: RAG 服务化重构

## 概述

本实现计划将 RAG 模块重构为服务化架构，统一 Embedding 调用、索引管理和检索服务。实现采用增量方式，先构建核心服务层，再迁移现有组件。

## 任务

- [x] 1. 创建 RAG 服务层基础结构
  - [x] 1.1 创建 `infra/rag/schemas/` 目录和数据模型
    - 创建 `infra/rag/schemas/__init__.py`
    - 创建 `infra/rag/schemas/index.py`（IndexConfig、IndexDocument、IndexInfo、UpdateResult）
    - 创建 `infra/rag/schemas/search.py`（SearchResult）
    - 注意：EmbeddingResult 和 EmbeddingStats 定义在 embedding_service.py 中，不在 schemas 中重复定义
    - _Requirements: 2.5, 3.6_
  
  - [x] 1.2 创建 `infra/rag/exceptions.py` 异常定义
    - 定义 RAGError、EmbeddingError、IndexError、IndexExistsError、IndexNotFoundError、IndexCreationError、StorageError、RetrievalError
    - _Requirements: 错误处理_

- [x] 2. 扩展 ModelManager 支持缓存统计
  - [x] 2.1 修改 `infra/ai/model_manager.py`
    - 添加 `EmbeddingResult` 数据类（vectors、cache_hits、cache_misses）
    - 实现 `embed_documents_batch_with_stats()` 方法
    - 实现 `embed_documents_batch_with_stats_async()` 异步方法
    - 在现有缓存逻辑基础上统计命中/未命中次数
    - _Requirements: 1.8_

- [x] 3. 实现 EmbeddingService
  - [x] 3.1 创建 `infra/rag/embedding_service.py`
    - 实现 EmbeddingService 类
    - 实现 `embed_query(text)` 方法
    - 实现 `embed_documents(texts)` 方法
    - 实现 `embed_documents_async(texts)` 异步方法
    - 调用 ModelManager.embed_documents_batch_with_stats() 获取缓存信息
    - 实现 `get_stats()` 统计方法
    - 实现 `reset_stats()` 方法
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_
  
  - [x] 3.2 编写 EmbeddingService 属性测试
    - **Property 1: Embedding 缓存往返**
    - **Property 2: Embedding 统计一致性**
    - **Validates: Requirements 1.3, 1.4, 1.6**

- [x] 4. 实现 IndexManager
  - [x] 4.1 创建 `infra/rag/index_manager.py`
    - 实现 IndexManager 类
    - 实现 `create_index(name, config, documents)` 方法
    - 实现 `get_index(name)` 方法（懒加载模式）
    - 实现 `_load_index_from_storage(name)` 方法（从持久化存储加载索引）
    - 实现 `delete_index(name)` 方法
    - 实现 `list_indexes()` 方法
    - 实现 `get_index_info(name)` 方法
    - 实现索引注册表逻辑
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
  
  - [x] 4.2 实现增量更新功能
    - 实现 `add_documents(index_name, documents)` 方法
    - 实现 `update_documents(index_name, documents)` 方法
    - 实现 `delete_documents(index_name, doc_ids)` 方法
    - 实现文档哈希注册表（持久化到 KV 存储）
    - 实现 `_load_doc_hashes()` 和 `_save_doc_hashes()` 方法
    - 实现变更检测逻辑（分离 content_hash 和 metadata_hash）
    - 实现 `_reindex_documents()` 方法（重新向量化）
    - 实现 `_update_metadata_only()` 方法（仅更新元数据，不重新向量化）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  
  - [x] 4.3 编写 IndexManager 属性测试
    - **Property 3: 索引创建-获取往返**
    - **Property 4: 索引删除后不可获取**
    - **Property 5: 索引元数据完整性**
    - **Property 6: 增量添加文档**
    - **Property 7: 增量更新文档**
    - **Property 8: 文档删除**
    - **Property 9: 文档哈希跟踪**
    - **Validates: Requirements 2.2-2.7, 3.1-3.6**

- [x] 5. 实现 RetrievalService
  - [x] 5.1 创建 `infra/rag/retrieval_service.py`
    - 实现 RetrievalService 类
    - 实现 `search(index_name, query, top_k, filters, score_threshold)` 方法
    - 实现 `search_async(...)` 异步方法
    - 实现 `batch_search(...)` 方法
    - 实现 `batch_search_async(...)` 异步方法
    - 实现 `normalize_score(raw_score, score_type)` 静态方法
    - 实现元数据过滤逻辑
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
  
  - [x] 5.2 编写 RetrievalService 属性测试
    - **Property 10: 搜索分数归一化**
    - **Property 11: 元数据过滤正确性**
    - **Validates: Requirements 4.3, 4.4, 4.6**

- [x] 6. 实现 RAGService 主服务
  - [x] 6.1 创建 `infra/rag/service.py`
    - 实现 RAGService 单例类
    - 实现 `get_instance()` 类方法
    - 实现 `embedding` 属性（延迟初始化）
    - 实现 `index` 属性（延迟初始化）
    - 实现 `retrieval` 属性（延迟初始化）
    - 实现配置加载逻辑
    - 实现 `get_rag_service()` 便捷函数
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  
  - [x] 6.2 编写 RAGService 属性测试
    - **Property 12: RAG 服务单例**
    - **Validates: Requirements 5.1**
  
  - [x] 6.3 更新 `infra/rag/__init__.py` 导出
    - 导出 RAGService、get_rag_service
    - 导出 EmbeddingService、IndexManager、RetrievalService
    - 导出所有 schemas 和 exceptions
    - _Requirements: 5.1, 5.2_

- [x] 7. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 8. 添加配置支持
  - [x] 8.1 更新 `app.yaml` 添加 `rag_service` 配置节
    - 添加 embedding 配置（batch_size、max_concurrency）
    - 注意：Embedding 缓存由 ModelManager 管理，不在 rag_service 层配置
    - 添加 index 配置（registry_namespace、default_backend、persist_directory、doc_hash_namespace）
    - 添加 retrieval 配置（default_top_k、score_threshold、score_type）
    - 添加预定义索引配置
    - _Requirements: 5.3_
  
  - [x] 8.2 更新 `infra/config/config_loader.py` 添加配置读取方法
    - 添加 `get_rag_service_config()` 方法
    - _Requirements: 5.3_

- [x] 9. 迁移 FieldRetriever 组件
  - [x] 9.1 重构 `semantic_parser/components/field_retriever.py`
    - 移除直接创建 CascadeRetriever 的代码
    - 使用 `get_rag_service().retrieval.search()` 进行检索
    - 使用 `get_rag_service().index` 管理字段索引
    - 保持现有 `retrieve()` 方法签名不变
    - _Requirements: 6.1_
  
  - [x] 9.2 更新 `semantic_parser/graph.py`
    - 移除 `field_retriever_node` 中直接创建 CascadeRetriever 的代码
    - 使用 RAGService 进行索引管理
    - _Requirements: 6.1_
  
  - [x] 9.3 编写 FieldRetriever 迁移测试
    - 验证迁移后功能正常
    - _Requirements: 6.1_

- [x] 10. 迁移 FewShotManager 组件
  - [x] 10.1 重构 `semantic_parser/components/few_shot_manager.py`
    - 移除自定义 `_cosine_similarity()` 方法
    - 使用 `get_rag_service().embedding` 进行向量化
    - 使用 `get_rag_service().retrieval.search()` 进行示例检索
    - 使用 `get_rag_service().index` 管理示例索引
    - 保持现有 `retrieve()` 方法签名不变
    - _Requirements: 6.2_
  
  - [x] 10.2 编写 FewShotManager 迁移测试
    - 验证迁移后功能正常
    - _Requirements: 6.2_

- [x] 11. 迁移 DimensionHierarchyInference 组件
  - [x] 11.1 重构 `dimension_hierarchy/inference.py`
    - 移除 `_init_rag()` 方法中的直接 RAG 初始化代码
    - 使用 `get_rag_service().index` 管理维度模式索引
    - 使用 `get_rag_service().retrieval.search()` 进行模式检索
    - 使用 `get_rag_service().embedding` 进行批量向量化
    - 保持现有 `_rag_search()` 方法签名不变
    - _Requirements: 6.3_
  
  - [x] 11.2 编写 DimensionHierarchyInference 迁移测试
    - 验证迁移后功能正常
    - _Requirements: 6.3_

- [x] 12. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 13. 清理和文档
  - [x] 13.1 清理废弃代码
    - 移除 FieldRetriever 中不再使用的 CascadeRetriever 相关代码
    - 移除 FewShotManager 中不再使用的 `_cosine_similarity()` 方法
    - 移除 DimensionHierarchyInference 中不再使用的 RAG 初始化代码
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 14. 最终 Checkpoint
  - 确保所有测试通过，如有问题请询问用户。

## 备注

- 每个任务引用具体的需求以便追溯
- Checkpoint 任务用于确保增量验证
- 属性测试验证通用正确性属性
- 单元测试验证具体示例和边界情况
