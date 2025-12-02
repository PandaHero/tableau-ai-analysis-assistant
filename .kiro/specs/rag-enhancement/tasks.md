# Implementation Plan

## 包结构说明

**新建 `rag` 包**：`tableau_assistant/src/capabilities/rag/`

```
rag/
├── __init__.py
├── embeddings.py          # EmbeddingProvider 抽象和实现（参考 DB-GPT embeddings）
├── field_indexer.py       # 字段索引器（参考 DB-GPT DBSchemaAssembler）
├── retriever.py           # 检索器抽象层（参考 DB-GPT BaseRetriever）
├── reranker.py            # 重排序器（参考 DB-GPT rerank.py）
├── semantic_mapper.py     # 语义映射器（参考 DB-GPT SchemaLinking）
├── assembler.py           # 知识组装器（参考 DB-GPT DBSchemaAssembler）
├── cache.py               # 缓存管理器
└── models.py              # RAG 相关数据模型
```

**设计参考**：
- 主要参考 DB-GPT 项目的 RAG 实现逻辑和架构设计
- 现有 `semantic_mapping` 包作为功能参考，了解当前业务需求

**与现有 `semantic_mapping` 包的关系**：
- 新的 `rag` 包是基于 DB-GPT 设计的增强版实现
- 保持 API 兼容性，现有代码可以平滑迁移
- 最终废弃 `semantic_mapping` 包

## Phase 1: 核心检索和映射能力

- [x] 1. 元数据 API 迁移（R14）



  - [x] 1.1 创建 VizQL 元数据客户端
    - 在 `tableau_assistant/src/bi_platforms/tableau/` 创建 `vizql_metadata.py`
    - 实现 `read_metadata()` 方法调用 VizQL `/read-metadata` API
    - 实现 `get_datasource_model()` 方法调用 VizQL `/get-datasource-model` API
    - 复用现有 `VizQLClient` 的连接池和重试机制
    - _Requirements: 14.1, 14.4_
  - [x] 1.2 编写属性测试：Role 推断正确性
    - **Property 3: Role 推断正确性**
    - **Validates: Requirements 1.7, 14.2**
  - [x] 1.3 实现 Role 推断逻辑
    - 在 `vizql_metadata.py` 中实现 `_infer_role()` 函数
    - `defaultAggregation` 为 null → dimension
    - `defaultAggregation` 非 null → measure
    - _Requirements: 14.2_
  - [x] 1.4 更新 FieldMetadata 模型
    - 在 `tableau_assistant/src/models/metadata.py` 中添加新字段
    - 添加 `fieldName`, `fieldCaption`, `columnClass`, `logicalTableId`, `logicalTableCaption`
    - 保持与现有字段的兼容性
    - _Requirements: 14.3, 14.5_


  - [x] 1.5 编写属性测试：后向兼容性
    - **Property 19: 后向兼容性**
    - **Validates: Requirements 14.5**
  - [x] 1.6 实现降级逻辑
    - VizQL API 不可用时降级到 GraphQL API
    - 添加日志记录降级事件
    - _Requirements: 14.6_

- [x] 2. Checkpoint - 确保所有测试通过


  - Ensure all tests pass, ask the user if questions arise.




- [x] 3. 数据模型获取（R12）



  - [x] 3.1 实现 DataModel 数据模型


    - 在 `tableau_assistant/src/models/` 创建 `data_model.py`
    - 定义 `LogicalTable`, `LogicalTableRelationship`, `DataModel` 类
    - 实现 `get_table_caption()` 方法
    - _Requirements: 12.2, 12.3_
  - [x] 3.2 编写属性测试：数据模型解析


    - **Property 12: 数据模型解析**
    - **Validates: Requirements 12.2, 12.3**
  - [x] 3.3 集成数据模型到 MetadataManager



    - 更新 `tableau_assistant/src/capabilities/metadata/manager.py`
    - 调用 VizQL `/get-datasource-model` API
    - 将 `logicalTableId` 映射到 `logicalTableCaption`
    - _Requirements: 12.1, 12.4_

  - [x] 3.4 实现数据模型缓存



    - 使用 SQLite 缓存数据模型
    - 设置 24 小时 TTL
    - _Requirements: 12.5_
  - [x] 3.5 实现优雅降级


    - 数据模型 API 不可用时继续使用字段元数据
    - _Requirements: 12.6_

- [x] 4. Checkpoint - 确保所有测试通过




  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 创建 RAG 包和 Embedding 提供者抽象（R11）




  - [x] 5.1 创建 RAG 包结构

    - 创建 `tableau_assistant/src/capabilities/rag/` 目录
    - 创建 `__init__.py` 和 `models.py`
    - _Requirements: 11.1_


  - [x] 5.2 创建 EmbeddingProvider 抽象基类

    - 在 `embeddings.py` 中定义 `EmbeddingProvider` 抽象基类
    - 定义 `embed_documents()` 和 `embed_query()` 方法

    - _Requirements: 11.1_

  - [x] 5.3 实现 ZhipuEmbedding 提供者

    - 参考 DB-GPT 的 `dbgpt-ext/rag/embeddings/` 实现模式
    - 封装智谱 AI embedding-2 调用
    - 支持批量处理（默认 batch_size=32）
    - _Requirements: 11.2, 11.4_



  - [x] 5.4 实现 EmbeddingProviderFactory
    - 支持配置不同的 Embedding 提供者
    - 预留扩展接口，方便后期对接其他 RAG 模型
    - _Requirements: 11.2_
  - [x] 5.5 编写属性测试：向量化提供者兼容性


    - **Property 16: 向量化提供者兼容性**
    - **Validates: Requirements 11.1**




  - [x] 5.6 实现向量缓存
    - 使用 SQLite 缓存向量
    - 以文本 hash 为 key

    - _Requirements: 11.5_
  - [x] 5.7 编写属性测试：向量缓存往返

    - **Property 14: 向量缓存往返**
    - **Validates: Requirements 11.5**

- [x] 6. Checkpoint - 确保所有测试通过



  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 字段索引增强（R1）



  - [x] 7.1 创建 FieldIndexer 增强版

    - 在 `tableau_assistant/src/capabilities/rag/` 创建 `field_indexer.py`
    - 参考 DB-GPT 的 `DBSchemaAssembler` 实现模式
    - 构建增强索引文本：fieldCaption, role, dataType, columnClass, category, formula, logicalTableCaption
    - _Requirements: 1.1, 1.2_

  - [x] 7.2 编写属性测试：索引完整性

    - **Property 1: 索引完整性**
    - **Validates: Requirements 1.1, 1.2**


  - [x] 7.3 实现元数据过滤
    - 支持按 category 过滤


    - _Requirements: 1.3_
  - [x] 7.4 实现增量更新
    - 检测元数据变化

    - 仅更新变化的字段
    - _Requirements: 1.4_
  - [x] 7.5 实现索引持久化




    - 使用 FAISS 持久化
    - 以 datasource LUID 为命名空间

    - _Requirements: 1.5_
  - [x] 7.6 编写属性测试：索引持久化往返

    - **Property 2: 索引持久化往返**

    - **Validates: Requirements 1.5, 6.3**
  - [x] 7.7 添加样本值到索引
    - 包含 top-5 样本值
    - _Requirements: 1.6_
  - [x] 7.8 编写属性测试：字段-表映射



    - **Property 13: 字段-表映射**
    - **Validates: Requirements 12.4, 1.2**

- [x] 8. Checkpoint - 确保所有测试通过



  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Schema Linking 增强（R3）




  - [x] 9.1 创建增强版 SemanticMapper

    - 在 `tableau_assistant/src/capabilities/rag/` 创建 `semantic_mapper.py`
    - 参考 DB-GPT 的 `SchemaLinking` 实现模式（两阶段检索 + LLM 判断）
    - 实现 `map_field()` 方法，支持上下文消歧
    - 保持与现有 API 的兼容性
    - _Requirements: 3.1, 3.2, 3.3_


  - [x] 9.2 编写属性测试：检索结果数量

    - **Property 4: 检索结果数量**
    - **Validates: Requirements 2.1, 3.1**

  - [x] 9.3 实现元数据消歧
    - 使用 sample_values, category, description 区分相似字段

    - _Requirements: 3.4_
  - [x] 9.4 实现低置信度处理
    - 置信度 < 0.7 时返回 top-3 备选
    - _Requirements: 3.5_
  - [x] 9.5 编写属性测试：低置信度备选
    - **Property 11: 低置信度备选**
    - **Validates: Requirements 3.5**

- [x] 10. Checkpoint - 确保所有测试通过


  - Ensure all tests pass, ask the user if questions arise.


- [x] 11. 性能优化与智能降级（R13）

  - [x] 11.1 实现高置信度快速路径

    - 向量检索 top-1 置信度 > 0.9 时跳过 LLM
    - _Requirements: 13.1_

  - [x] 11.2 编写属性测试：高置信度快速路径



    - **Property 10: 高置信度快速路径**
    - **Validates: Requirements 13.1**

  - [x] 11.3 实现历史结果复用


    - 相似度 > 0.95 时复用缓存结果

    - _Requirements: 13.2_
  - [x] 11.4 编写属性测试：缓存一致性


    - **Property 9: 缓存一致性**

    - **Validates: Requirements 7.1, 7.2**
  - [x] 11.5 实现 LLM 降级
    - LLM 不可用或超时时降级到向量检索 top-1
    - _Requirements: 13.3_
  - [x] 11.6 实现并发处理

    - 使用 asyncio 并发处理最多 5 个查询
    - _Requirements: 13.4_

  - [x] 11.7 编写属性测试：批量处理并发

    - **Property 15: 批量处理并发**
    - **Validates: Requirements 7.4, 13.4**

  - [x] 11.8 实现延迟追踪

    - 记录 embedding, retrieval, rerank, llm 各阶段延迟
    - _Requirements: 13.5_

- [x] 12. Checkpoint - 确保所有测试通过



  - Ensure all tests pass, ask the user if questions arise.

## Phase 2: 检索增强和抽象层

- [ ] 13. 检索器抽象层（R5）
  - [ ] 13.1 创建 BaseRetriever 抽象基类
    - 在 `tableau_assistant/src/capabilities/rag/` 创建 `retriever.py`
    - 参考 DB-GPT 的 `BaseRetriever` 实现模式
    - 定义 `retrieve()` 和 `aretrieve()` 方法
    - _Requirements: 5.2_
  - [ ] 13.2 实现 EmbeddingRetriever
    - 封装 FAISS 向量检索
    - _Requirements: 5.1_
  - [ ] 13.3 实现 KeywordRetriever
    - 实现 BM25 关键词检索
    - _Requirements: 5.1_
  - [ ] 13.4 实现 HybridRetriever
    - 组合向量和关键词检索
    - _Requirements: 5.1_
  - [ ] 13.5 编写属性测试：分数范围
    - **Property 5: 分数范围**
    - **Validates: Requirements 5.3**
  - [ ] 13.6 实现元数据过滤
    - 支持 role, dataType, datasource LUID, category 过滤
    - _Requirements: 5.4_
  - [ ] 13.7 编写属性测试：元数据过滤
    - **Property 6: 元数据过滤**
    - **Validates: Requirements 2.4, 5.4**
  - [ ] 13.8 实现配置参数
    - 支持 top-k, score_threshold, reranker 参数
    - _Requirements: 5.5_

- [ ] 14. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. 两阶段检索策略（R2）
  - [ ] 15.1 集成两阶段检索到 SemanticMapper
    - 第一阶段：向量检索 top-K (K=10)
    - 第二阶段：Rerank
    - _Requirements: 2.1, 2.2_
  - [ ] 15.2 实现混合检索
    - 组合向量和 BM25 检索
    - _Requirements: 2.3_
  - [ ] 15.3 实现结果增强
    - 返回 relevance scores, retrieval source, ranking position
    - _Requirements: 2.5_

- [ ] 16. Rerank 模块（R4）
  - [ ] 16.1 创建 BaseReranker 抽象基类
    - 在 `tableau_assistant/src/capabilities/rag/` 创建 `reranker.py`
    - 参考 DB-GPT 的 `rerank.py` 实现模式
    - 定义 `rerank()` 方法
    - _Requirements: 4.1_
  - [ ] 16.2 实现 CrossEncoderReranker
    - 使用交叉编码器计算相关性分数
    - _Requirements: 4.2_
  - [ ] 16.3 实现 LLMReranker
    - 使用 LLM 判断相关性
    - _Requirements: 4.3_
  - [ ] 16.4 实现 RRFReranker
    - 使用 RRF 公式: score = Σ(1/(k+rank))
    - _Requirements: 4.4_
  - [ ] 16.5 编写属性测试：RRF 公式正确性
    - **Property 8: RRF 公式正确性**
    - **Validates: Requirements 4.4**
  - [ ] 16.6 编写属性测试：Rerank 排序
    - **Property 7: Rerank 排序**
    - **Validates: Requirements 4.5**

- [ ] 17. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 18. 知识组装器（R6）
  - [ ] 18.1 创建 KnowledgeAssembler
    - 在 `tableau_assistant/src/capabilities/rag/` 创建 `assembler.py`
    - 参考 DB-GPT 的 `DBSchemaAssembler` 实现模式
    - 实现 `load_metadata()` 方法
    - _Requirements: 6.1_
  - [ ] 18.2 实现分块策略
    - 支持 by-field, by-table, by-category 策略
    - _Requirements: 6.2_
  - [ ] 18.3 实现 as_retriever() 方法
    - 返回配置好的检索器实例
    - _Requirements: 6.4_
  - [ ] 18.4 实现 force_rebuild 选项
    - 支持强制重建索引
    - _Requirements: 6.5_

- [ ] 19. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Phase 3: 缓存和 RAG 增强

- [ ] 20. 缓存与性能优化（R7）
  - [ ] 20.1 创建 CacheManager
    - 在 `tableau_assistant/src/capabilities/rag/` 创建 `cache.py`
    - 实现查询结果缓存（1 小时 TTL）
    - _Requirements: 7.1_
  - [ ] 20.2 实现向量缓存
    - 缓存 embedding 向量
    - _Requirements: 7.2_
  - [ ] 20.3 实现索引磁盘缓存
    - 从磁盘加载已有索引
    - _Requirements: 7.3_
  - [ ] 20.4 实现批量并发检索
    - 使用 asyncio.gather 并发处理最多 10 个查询
    - _Requirements: 7.4_

- [ ] 21. 维度层级推断 RAG 增强（R9）
  - [ ] 21.1 创建维度模式索引
    - 索引历史推断结果
    - 包含 field name, data type, sample values, unique count, category/level
    - _Requirements: 9.4_
  - [ ] 21.2 实现模式检索
    - 检索相似度 > 0.8 的历史模式
    - _Requirements: 9.1_
  - [ ] 21.3 实现 few-shot 示例提供
    - 提供 top-3 模式作为 LLM 示例
    - _Requirements: 9.2_
  - [ ] 21.4 实现模式存储
    - 成功推断后存储新模式
    - _Requirements: 9.3_
  - [ ] 21.5 编写属性测试：维度层级模式存储
    - **Property 17: 维度层级模式存储**
    - **Validates: Requirements 9.3**
  - [ ] 21.6 实现降级逻辑
    - 无相似模式时降级到纯 LLM 推断
    - _Requirements: 9.5_

- [ ] 22. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 23. 任务规划 RAG 增强（R10）
  - [ ] 23.1 创建查询计划索引
    - 索引历史查询计划
    - 包含 question text, intent type, field mappings, filter types, aggregation types
    - _Requirements: 10.4_
  - [ ] 23.2 实现计划检索
    - 检索相似度 > 0.75 的历史计划
    - 支持按 datasource LUID 和 intent type 过滤
    - _Requirements: 10.1, 10.5_
  - [ ] 23.3 实现示例提供
    - 提供 top-3 计划及执行结果作为 LLM 示例
    - _Requirements: 10.2_
  - [ ] 23.4 实现计划存储
    - 成功执行的计划存储供未来检索
    - _Requirements: 10.3_
  - [ ] 23.5 编写属性测试：查询计划存储
    - **Property 18: 查询计划存储**
    - **Validates: Requirements 10.3**

- [ ] 24. Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Phase 4: 可观测性

- [ ] 25. 可观测性与调试（R8）
  - [ ] 25.1 实现检索日志
    - 记录 query text, candidate count, top-3 scores, latency
    - _Requirements: 8.1_
  - [ ] 25.2 实现 Rerank 日志
    - 记录 before/after rankings 和 score changes
    - _Requirements: 8.2_
  - [ ] 25.3 实现错误日志
    - 详细错误信息：query, stage, stack trace
    - _Requirements: 8.3_
  - [ ] 25.4 实现 verbose 模式
    - 支持 `verbose=True` 输出详细追踪
    - _Requirements: 8.4_
  - [ ] 25.5 实现指标暴露
    - 暴露 avg_retrieval_latency, cache_hit_rate, llm_skip_rate
    - _Requirements: 8.5_

- [ ] 26. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Phase 5: 迁移和清理

- [ ] 27. 迁移现有代码到 RAG 包
  - [ ] 27.1 更新现有调用点
    - 将 `semantic_mapping` 的导入改为 `rag` 包
    - 更新 `semantic_map_fields` 工具使用新的 `rag` 包
    - _Requirements: 14.5_
  - [ ] 27.2 添加兼容性适配器
    - 在 `semantic_mapping/__init__.py` 中添加重导出
    - 添加废弃警告（DeprecationWarning）
    - _Requirements: 14.5_
  - [ ] 27.3 更新文档
    - 更新 README 说明新的 `rag` 包
    - 添加迁移指南

- [ ] 28. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.
