# 实现计划

- [-] 1. 修复 FieldIndexer 置信度计算


  - [x] 1.1 修改 `_faiss_search()` 方法，移除 `(score + 1) / 2` 转换

    - 修改 `tableau_assistant/src/capabilities/rag/field_indexer.py`
    - 使用 `max(0.0, min(1.0, score))` 替代 `(score + 1.0) / 2.0`
    - 返回元组 `(field_name, confidence, raw_score)`
    - _Requirements: 1.1, 1.2_
  - [x] 1.2 修改 `search()` 方法，传递 raw_score 到 RetrievalResult


    - 更新 RetrievalResult 构造，添加 raw_score 参数
    - _Requirements: 1.3_
  - [ ] 1.3 编写属性测试：余弦相似度范围


    - **Property 1: 余弦相似度范围**
    - **Validates: Requirements 1.1**

- [-] 2. 更新 RetrievalResult 数据模型


  - [x] 2.1 添加 `raw_score` 字段到 RetrievalResult

    - 修改 `tableau_assistant/src/capabilities/rag/models.py`
    - 添加 `raw_score: Optional[float] = None` 字段
    - _Requirements: 1.3_
  - [ ] 2.2 编写属性测试：调试信息完整性
    - **Property 3: 调试信息完整性**
    - **Validates: Requirements 1.3**

- [-] 3. 整理缓存架构（统一使用 StoreManager）



  - [x] 3.1 删除 `FieldMappingCache` 类

    - 删除 `tableau_assistant/src/nodes/field_mapper/cache.py` 文件


    - 该类与 `MappingCache` 功能重复
    - _Requirements: 2.6_

  - [x] 3.2 删除 RAG cache.py 中的冗余类


    - 修改 `tableau_assistant/src/capabilities/rag/cache.py`
    - 删除 `VectorCache` 类（使用 StoreManager 替代）

    - 删除 `MappingCache` 类（使用 StoreManager 替代）
    - 删除 `CacheManager` 类（使用 StoreManager 替代）
    - 保留 `CachedEmbeddingProvider` 类（修改为使用 StoreManager）

    - _Requirements: 2.6_
  - [x] 3.3 修改 `CachedEmbeddingProvider` 使用 StoreManager


    - 修改 `tableau_assistant/src/capabilities/rag/cache.py`
    - 使用 `get_store_manager()` 获取全局实例
    - 使用命名空间 `("embedding_cache",)` 存储向量
    - TTL 设置为 7 天
    - _Requirements: 2.6_
  - [x] 3.4 修改 `FieldMapperNode` 使用 StoreManager

    - 修改 `tableau_assistant/src/nodes/field_mapper/node.py`
    - 删除 `FieldMappingCache` 导入
    - 使用 `get_store_manager()` 获取全局实例
    - 使用命名空间 `("field_mapping",)` 存储映射结果
    - TTL 设置为 24 小时
    - _Requirements: 2.6_


  - [x] 3.5 删除 `SemanticMapper` 中的历史复用机制




    - 修改 `tableau_assistant/src/capabilities/rag/semantic_mapper.py`
    - 删除 `_history` 列表和相关方法
    - 删除 `_check_history_reuse()` 方法
    - 删除 `_add_to_history()` 方法
    - _Requirements: 2.6_

- [-] 4. 修改 FieldMapperNode 使用两阶段检索架构
  - [x] 4.1 修改 `FieldMapperNode.__init__()` 集成 KnowledgeAssembler 和 LLMReranker


    - 修改 `tableau_assistant/src/nodes/field_mapper/node.py`
    - 添加 `_assembler: KnowledgeAssembler` 属性
    - 添加 `_reranker: LLMReranker` 属性（第二阶段精排）
    - _Requirements: 2.1, 2.3_

  - [x] 4.2 添加 `load_metadata()` 方法
    - 使用 KnowledgeAssembler 加载元数据
    - 使用 BY_FIELD 分块策略
    - 构建向量索引 + BM25 索引
    - _Requirements: 2.1_
  - [x] 4.3 修改 `map_field()` 方法实现两阶段检索

    - 第一阶段: HybridRetriever 召回 top-5 候选
    - 第二阶段: LLMReranker 精排返回 top-3
    - 保留现有的置信度评估逻辑
    - _Requirements: 2.2, 2.3_

  - [x] 4.4 添加延迟分解日志记录
    - 记录 embedding_ms、retrieval_ms、rerank_ms
    - _Requirements: 2.5_
  - [ ] 4.5 编写属性测试：延迟分解完整性
    - **Property 4: 延迟分解完整性**
    - **Validates: Requirements 2.5**


- [x] 5. 简化 SemanticMapper 为纯 RAG 检索层
  - [x] 5.1 修改 `SemanticMapper.map_field()` 方法

    - 删除缓存检查逻辑（由 FieldMapperNode 处理）
    - 保留两阶段检索（HybridRetriever + Reranker）
    - 简化返回值，只返回检索结果
    - _Requirements: 2.1, 2.2_

  - [x] 5.2 更新 `SemanticMapper` 配置
    - 删除 `enable_cache` 和 `enable_history_reuse` 配置（已在之前移除）
    - 保留 `use_two_stage` 和 `use_hybrid` 配置
    - _Requirements: 2.1_

- [-] 6. 确保 jieba 降级处理
  - [x] 6.1 验证 KeywordRetriever 的降级逻辑


    - 检查 `tableau_assistant/src/capabilities/rag/retriever.py` 中的 Tokenizer 类
    - 确保 jieba 不可用时使用简单分词
    - 添加 WARNING 日志
    - _Requirements: 2.4_

  - [ ] 6.2 编写单元测试：jieba 降级
    - 模拟 jieba 不可用场景
    - 验证使用简单分词
    - _Requirements: 2.4_

- [x] 7. 更新测试文件
  - [x] 7.1 修改 `test_e2e_workflow.py` 的 `step3_field_mapping()` 方法


    - 验证混合检索和重排序生效
    - 验证缓存使用 MappingCache
    - _Requirements: 2.1, 2.2, 2.3, 2.6_

- [x] 8. Checkpoint - 确保所有测试通过
  - 单元测试: 43 passed, 24 skipped
  - 属性测试: 131 passed
  - 注：部分集成测试因缺少 deepagents 模块跳过
