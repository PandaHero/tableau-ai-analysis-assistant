# Requirements Document

## Introduction

本文档定义了 Tableau Assistant 项目的 RAG (Retrieval-Augmented Generation) 框架增强需求。通过借鉴 DB-GPT 项目的先进设计，我们将构建一个更强大、更灵活的 RAG 系统，专门针对 Tableau Published Datasource 的元数据检索、字段映射和维度层级推断场景进行优化。

### 项目背景

**当前痛点**：
1. 字段映射依赖纯 LLM，每次调用成本高、延迟大
2. 维度层级推断无法复用历史结果，重复计算
3. 任务规划缺乏历史经验参考，生成质量不稳定
4. 大数据源（100+ 字段）检索效率低

**目标收益**：
- 相似查询响应时间从 2-5秒 降至 0.5-1秒（4-10x 提升）
- LLM 调用成本降低 50-70%（通过缓存和智能跳过）
- 字段映射准确率提升 10-20%（通过 Rerank 和上下文增强）

### 当前技术栈

| 组件 | 当前方案 | 说明 |
|-----|---------|------|
| 向量存储 | FAISS | 本地免费，已集成 |
| Embedding | 智谱 AI embedding-2 | 付费，国内可用 |
| Embedding 备选 | BCEmbedding | 本地免费，需安装 |
| 持久化 | SQLite (LangGraph Store) | 已集成 |
| LUID 查找 | Tableau Metadata GraphQL API | 已集成，通过数据源名称查找 LUID |
| 字段元数据 | Tableau Metadata GraphQL API | 已集成，**待迁移到 VizQL API** |
| 数据模型 | VizQL Data Service `/get-datasource-model` | **待集成**，返回逻辑表和关系 |
| 数据查询 | VizQL Data Service `/query-datasource` | 已集成，用于执行查询 |

### 元数据 API 对比

| 属性 | GraphQL API (当前使用) | VizQL `/read-metadata` (目标) |
|-----|----------------------|----------------------|
| 字段名 | `name` | `fieldName` |
| 显示名 | `name` (同上) | `fieldCaption` |
| 角色 | `role` (dimension/measure) | 需从 `defaultAggregation` 推断 |
| 数据类型 | `dataType` | `dataType` |
| 聚合 | `aggregation` | `defaultAggregation` |
| 字段类型 | `__typename` (ColumnField/CalculatedField等) | `columnClass` |
| 公式 | `formula` | `formula` |
| 所属表 | **无** | `logicalTableId` ✅ |
| 样本值 | 需单独查询 | 需单独查询 |

### 元数据获取方案（混合）

**数据流**：
1. **LUID 查找**：继续使用 GraphQL API `get_datasource_luid_by_name()` 通过数据源名称查找 LUID
2. **字段元数据**：迁移到 VizQL `/read-metadata` API（包含 `logicalTableId`）
3. **数据模型**：使用 VizQL `/get-datasource-model` API 获取逻辑表和关系
4. **字段-表映射**：通过 `logicalTableId` 将字段映射到逻辑表

**迁移说明**：
- GraphQL API 仍用于 LUID 查找（VizQL API 不支持按名称查找）
- 字段元数据迁移到 VizQL API 以获取 `logicalTableId`
- 需要适配 `role` 字段（从 `defaultAggregation` 推断）

### 与 DB-GPT 的对比

| 功能 | DB-GPT | 我们的项目 | 借鉴点 |
|-----|--------|-----------|-------|
| Schema 检索 | DBSchemaRetriever | SemanticMapper | 表/字段分离索引 |
| Schema Linking | 向量+LLM 两阶段 | 向量+LLM | 已有，需优化 |
| Rerank | CrossEncoder/RRF | 无 | **需新增** |
| 知识组装 | DBSchemaAssembler | FieldIndexer | 需增强 |
| 数据模型 | 支持表关系 | 仅字段级 | **需新增** |

## Glossary

- **RAG**: Retrieval-Augmented Generation，检索增强生成
- **Schema Linking**: 模式链接，将用户自然语言查询映射到数据源字段
- **Rerank**: 重排序，对初步检索结果进行二次排序以提高相关性
- **Chunk**: 文档块，将大文档分割成的小片段
- **Embedding**: 嵌入向量，将文本转换为数值向量
- **Vector Store**: 向量存储（本项目使用 FAISS）
- **FAISS**: Facebook AI Similarity Search，高效向量搜索库（免费）
- **Published Datasource**: Tableau 发布的数据源
- **Metadata**: 元数据（name, dataType, role, aggregation 等）
- **Data Model**: 数据模型，Tableau 中表、关系、计算字段的结构
- **Logical Table**: Tableau 数据模型中的逻辑表
- **Relationship**: Tableau 数据模型中表之间的关系
- **Dimension Hierarchy**: 维度层级，维度字段的父子关系和粒度
- **Field Mapping**: 字段映射，业务术语到技术字段名的映射
- **Cross-Encoder**: 交叉编码器，计算文本对相关性的模型
- **BM25**: 基于词频的经典检索算法
- **Hybrid Retrieval**: 混合检索，结合向量和关键词检索
- **BCEmbedding**: 北京智源的中文优化 Embedding 模型（本地免费）
- **VizQL Data Service**: Tableau 的数据查询 API

## Requirements

### Requirement 1: 字段元数据索引增强

**User Story:** As a developer, I want to build enhanced field metadata indexes, so that I can efficiently retrieve relevant fields from Tableau datasources.

**优先级**: P0（核心功能）

**与现有功能的关系**: 增强现有 `FieldIndexer`，优化索引文本构建和检索效率

**说明**: 
- Tableau Published Datasource 通常是扁平化的字段列表，不需要表级分离索引
- 需要优化字段索引的文本构建，包含更多语义信息
- **迁移到 VizQL `/read-metadata` API 获取字段元数据**（包含 `logicalTableId`）
- **VizQL API 返回的字段元数据结构**：
  - `fieldName`: 底层数据库列名
  - `fieldCaption`: 字段显示名称
  - `dataType`: STRING/BOOLEAN/INTEGER/REAL/DATETIME/DATE/SPATIAL/UNKNOWN
  - `defaultAggregation`: 默认聚合方式（用于推断 role）
  - `columnClass`: COLUMN/BIN/GROUP/CALCULATION/TABLE_CALCULATION
  - `formula`: 计算字段公式
  - `logicalTableId`: 字段所属逻辑表ID ✅
- **增强点**：
  - 通过 `logicalTableId` 映射到逻辑表名称（结合 R12 数据模型）
  - 添加维度层级推断结果（category, level, granularity）
  - 添加样本值（sample_values）用于语义匹配
  - 从 `defaultAggregation` 推断 role（null=dimension, 有值=measure）

#### Acceptance Criteria

1. WHEN the system initializes a datasource THEN the RAG_System SHALL create a vector index for all field metadata from VizQL `/read-metadata` API
2. WHEN building field index text THEN the RAG_System SHALL include fieldCaption, role (inferred from defaultAggregation), dataType, columnClass, category (from dimension hierarchy), formula (if calculation), and logical table caption (from R12 data model via logicalTableId)
3. WHEN a field has category information THEN the RAG_System SHALL include category as searchable metadata filter
4. WHEN the metadata changes THEN the RAG_System SHALL support incremental index updates without full rebuild
5. WHEN storing index THEN the RAG_System SHALL persist indexes to disk with datasource LUID as namespace
6. WHEN sample values are available THEN the RAG_System SHALL include top-5 sample values in index text for semantic matching
7. WHEN VizQL API returns field metadata THEN the RAG_System SHALL infer role from defaultAggregation (null → dimension, non-null → measure)

### Requirement 2: 两阶段检索策略

**User Story:** As a developer, I want a two-stage retrieval strategy, so that I can balance retrieval speed and accuracy.

**优先级**: P0（核心功能）

**与现有功能的关系**: 增强现有 `SemanticMapper.map_field()` 方法

#### Acceptance Criteria

1. WHEN a user query is received THEN the RAG_System SHALL first perform vector similarity search to retrieve top-K candidates (K=10)
2. WHEN vector search completes THEN the RAG_System SHALL apply a reranker to reorder candidates by semantic relevance
3. WHEN multiple retrieval methods are available THEN the RAG_System SHALL support hybrid retrieval combining vector and BM25 search
4. WHEN filtering candidates THEN the RAG_System SHALL support metadata-based filtering by field role (dimension/measure), data type, and category
5. WHEN returning results THEN the RAG_System SHALL include relevance scores, retrieval source, and ranking position

### Requirement 3: Schema Linking 增强

**User Story:** As a developer, I want enhanced schema linking capabilities, so that I can accurately map business terms to technical field names.

**优先级**: P0（核心功能）

**与现有功能的关系**: 优化现有 `SemanticMapper`，参考 DB-GPT 的 `SchemaLinking`

#### Acceptance Criteria

1. WHEN a business term is provided THEN the Schema_Linker SHALL retrieve relevant field candidates using vector search with top-K=10
2. WHEN candidates are retrieved THEN the Schema_Linker SHALL use LLM to select the best matching field with reasoning
3. WHEN the question context is provided THEN the Schema_Linker SHALL consider context for disambiguation between similar fields
4. WHEN multiple fields have similar names THEN the Schema_Linker SHALL use field metadata (sample values, category, description) to distinguish them
5. WHEN no confident match is found (confidence < 0.7) THEN the Schema_Linker SHALL return top-3 alternatives with confidence scores

### Requirement 4: Rerank 模块

**User Story:** As a developer, I want a pluggable reranking system, so that I can improve retrieval quality with different reranking strategies.

**优先级**: P1（重要功能）

**与现有功能的关系**: 新增模块，参考 DB-GPT 的 `rerank.py`

#### Acceptance Criteria

1. WHEN reranking is enabled THEN the Reranker SHALL accept a list of candidates and return reordered results with updated scores
2. WHEN using CrossEncoder reranker THEN the Reranker SHALL compute pairwise relevance scores between query and each candidate
3. WHEN using LLM reranker THEN the Reranker SHALL use language model to judge relevance with structured output
4. WHEN using RRF (Reciprocal Rank Fusion) THEN the Reranker SHALL combine scores from multiple retrieval sources using formula: score = Σ(1/(k+rank))
5. WHEN reranking completes THEN the Reranker SHALL return top-K results sorted by final score

### Requirement 5: 检索器抽象层

**User Story:** As a developer, I want a unified retriever interface, so that I can easily switch between different retrieval strategies.

**优先级**: P1（重要功能）

**与现有功能的关系**: 重构现有 `VectorStoreManager`，参考 DB-GPT 的 `BaseRetriever`

#### Acceptance Criteria

1. WHEN creating a retriever THEN the Retriever_Factory SHALL support creating embedding, keyword, and hybrid retrievers
2. WHEN retrieving THEN the Base_Retriever SHALL provide both synchronous `retrieve()` and asynchronous `aretrieve()` methods
3. WHEN retrieving with scores THEN the Base_Retriever SHALL return chunks with relevance scores in range [0, 1]
4. WHEN filtering THEN the Base_Retriever SHALL support metadata filters for field role, data type, datasource LUID, and category
5. WHEN configuring THEN the Base_Retriever SHALL accept top-k, score threshold, and optional reranker parameters

### Requirement 6: 知识组装器

**User Story:** As a developer, I want a knowledge assembler, so that I can easily build and manage RAG indexes from Tableau metadata.

**优先级**: P1（重要功能）

**与现有功能的关系**: 增强现有 `FieldIndexer`，参考 DB-GPT 的 `DBSchemaAssembler`

#### Acceptance Criteria

1. WHEN loading metadata THEN the Knowledge_Assembler SHALL convert Tableau Metadata object to indexable Document list
2. WHEN chunking THEN the Knowledge_Assembler SHALL support configurable chunk strategies: by-field (default), by-table, by-category
3. WHEN persisting THEN the Knowledge_Assembler SHALL save indexes to FAISS with proper metadata tags
4. WHEN creating retriever THEN the Knowledge_Assembler SHALL return a configured retriever instance via `as_retriever()` method
5. WHEN rebuilding THEN the Knowledge_Assembler SHALL support `force_rebuild=True` option to clear and recreate indexes

### Requirement 7: 缓存与性能优化

**User Story:** As a developer, I want caching and performance optimizations, so that the RAG system responds quickly to repeated queries.

**优先级**: P1（重要功能）

**与现有功能的关系**: 增强现有 `StoreManager` 缓存机制

#### Acceptance Criteria

1. WHEN a query is repeated within 1 hour THEN the Cache_Manager SHALL return cached results without re-computation
2. WHEN embedding is computed THEN the Cache_Manager SHALL cache embedding vectors with query text as key
3. WHEN loading index THEN the Vector_Store SHALL load from disk cache if index file exists
4. WHEN batch processing THEN the RAG_System SHALL support concurrent retrieval for up to 10 queries using asyncio.gather
5. WHEN memory exceeds 500MB THEN the RAG_System SHALL support lazy loading of indexes on demand

### Requirement 8: 可观测性与调试

**User Story:** As a developer, I want observability features, so that I can debug and optimize RAG performance.

**优先级**: P2（辅助功能）

**与现有功能的关系**: 增强现有日志系统

#### Acceptance Criteria

1. WHEN retrieval is performed THEN the RAG_System SHALL log query text, candidate count, top-3 scores, and latency in milliseconds
2. WHEN reranking is performed THEN the RAG_System SHALL log before and after rankings with score changes
3. WHEN errors occur THEN the RAG_System SHALL provide detailed error messages including query, stage, and stack trace
4. WHEN debugging THEN the RAG_System SHALL support `verbose=True` mode with step-by-step trace output
5. WHEN monitoring THEN the RAG_System SHALL expose metrics: avg_retrieval_latency, cache_hit_rate, llm_skip_rate

### Requirement 9: 维度层级推断 RAG 增强

**User Story:** As a developer, I want to use RAG to enhance dimension hierarchy inference, so that I can improve inference accuracy and reduce LLM costs.

**优先级**: P1（重要功能）

**与现有功能的关系**: 增强现有 `DimensionHierarchyAgent`

#### Acceptance Criteria

1. WHEN inferring dimension hierarchy THEN the Hierarchy_Inferrer SHALL first retrieve similar dimension patterns from historical inferences with similarity > 0.8
2. WHEN similar patterns are found THEN the Hierarchy_Inferrer SHALL provide top-3 patterns as few-shot examples to LLM
3. WHEN inference completes successfully THEN the Hierarchy_Inferrer SHALL store the result as a new pattern for future retrieval
4. WHEN building pattern index THEN the Hierarchy_Inferrer SHALL include field name, data type, sample values, unique count, and inferred category/level
5. WHEN no similar patterns exist (similarity < 0.8) THEN the Hierarchy_Inferrer SHALL fall back to pure LLM inference

### Requirement 10: 任务规划 RAG 增强

**User Story:** As a developer, I want to use RAG to enhance task planning, so that I can generate better query plans based on similar historical queries.

**优先级**: P1（重要功能）

**与现有功能的关系**: 增强现有 `TaskPlannerAgent`

#### Acceptance Criteria

1. WHEN planning a query THEN the Task_Planner SHALL retrieve similar historical query plans with similarity > 0.75
2. WHEN similar plans are found THEN the Task_Planner SHALL provide top-3 plans as examples to LLM with their execution results
3. WHEN a plan is executed successfully (no errors, has results) THEN the Task_Planner SHALL store it for future retrieval
4. WHEN building plan index THEN the Task_Planner SHALL include question text, intent type, field mappings, filter types, and aggregation types
5. WHEN retrieving plans THEN the Task_Planner SHALL filter by datasource LUID and optionally by intent type

### Requirement 11: Embedding 提供者抽象

**User Story:** As a developer, I want a unified embedding provider interface, so that I can easily switch between different embedding services.

**优先级**: P0（核心功能）

**与现有功能的关系**: 重构现有 `EmbeddingsProvider`

**说明**：
- 当前使用智谱 AI embedding-2 作为默认提供者
- 不再支持本地 BCEmbedding（后期计划对接其他云端 RAG 模型）
- 设计可扩展接口，方便后期添加新的 Embedding 提供者

#### Acceptance Criteria

1. WHEN creating embeddings THEN the Embedding_Provider SHALL support configurable providers with zhipu as default
2. WHEN zhipu API key is set and API is reachable THEN the Embedding_Provider SHALL use zhipu as the default provider
3. WHEN adding new provider THEN the Embedding_Provider SHALL support extensible interface for future RAG model integration
4. WHEN embedding documents THEN the Embedding_Provider SHALL support batch processing with configurable batch size (default 32)
5. WHEN caching is enabled THEN the Embedding_Provider SHALL cache embedding vectors in SQLite with text hash as key

### Requirement 12: Tableau 数据模型信息获取

**User Story:** As a developer, I want to retrieve Tableau Data Model information, so that I can understand the complete table structure and field relationships for better metadata management.

**优先级**: P1（重要功能）

**与现有功能的关系**: 扩展现有 `MetadataManager`，补全数据模型查询能力

**说明**: 
- 当前元数据管理只有单表的字段元数据，缺少完整的数据模型信息
- VizQL Data Service 提供了 `/get-datasource-model` API 可以获取数据模型
- **API 返回结构**（根据 OpenAPI Schema）：
  - `logicalTables`: 逻辑表数组，包含 `logicalTableId` 和 `caption`
  - `logicalTableRelationships`: 逻辑表关系数组，包含 `fromLogicalTable` 和 `toLogicalTable`
- **注意**：VizQL API 只暴露**逻辑表（Logical Tables）**，不暴露物理表。这是 Tableau 数据模型的设计：
  - 逻辑表是用户在 Tableau 中看到的表，可能是物理表的抽象
  - 物理表是底层数据库的实际表，由 Tableau 内部处理
- 数据模型信息对于以下场景很重要：
  - 理解字段来源（属于哪个逻辑表）
  - 字段索引增强（添加表级上下文）
  - 调试和数据结构可视化
  - 未来可能的表级检索优化

#### Acceptance Criteria

1. WHEN loading datasource THEN the Metadata_Manager SHALL call VizQL Data Service `/get-datasource-model` API to retrieve data model
2. WHEN data model is retrieved THEN the Metadata_Manager SHALL parse and store logical tables (logicalTableId, caption)
3. WHEN data model is retrieved THEN the Metadata_Manager SHALL parse and store logical table relationships (fromLogicalTable, toLogicalTable)
4. WHEN building field index THEN the Metadata_Manager SHALL include logical table caption as field metadata for context
5. WHEN caching THEN the Metadata_Manager SHALL persist data model information with 24-hour TTL in SQLite
6. WHEN data model API is unavailable THEN the Metadata_Manager SHALL continue with field-only metadata (graceful degradation)

### Requirement 13: 性能优化与智能降级

**User Story:** As a developer, I want performance optimizations and smart fallback strategies, so that the system responds quickly and reliably.

**优先级**: P0（核心功能）

**与现有功能的关系**: 贯穿所有 RAG 相关模块

#### Acceptance Criteria

1. WHEN vector search top-1 confidence is above 0.9 THEN the RAG_System SHALL skip LLM judgment and return directly (fast path)
2. WHEN similar historical results exist with similarity > 0.95 THEN the RAG_System SHALL reuse cached results without LLM call
3. WHEN LLM is unavailable or times out (> 30s) THEN the RAG_System SHALL fall back to pure vector search top-1 result
4. WHEN batch processing multiple fields THEN the RAG_System SHALL process up to 5 queries concurrently using asyncio
5. WHEN measuring performance THEN the RAG_System SHALL track and log latency for stages: embedding, retrieval, rerank, llm

### Requirement 14: 元数据 API 迁移

**User Story:** As a developer, I want to migrate field metadata retrieval from GraphQL API to VizQL API, so that I can get logicalTableId for field-table mapping.

**优先级**: P0（核心功能，R1 前置依赖）

**与现有功能的关系**: 重构现有 `metadata.py`，迁移字段元数据获取逻辑

**说明**: 
- **保留 GraphQL API**：用于通过数据源名称查找 LUID（`get_datasource_luid_by_name()`）
- **迁移到 VizQL API**：用于获取字段元数据（`/read-metadata`）
- **新增 VizQL API**：用于获取数据模型（`/get-datasource-model`）
- **字段映射**：
  - `fieldName` → `name`（底层数据库列名）
  - `fieldCaption` → `fieldCaption`（显示名称，用于查询）
  - `defaultAggregation` → `role`（null=dimension, 非null=measure）
  - `columnClass` → `__typename` 的替代
  - `logicalTableId` → 新增，用于字段-表映射

#### Acceptance Criteria

1. WHEN retrieving field metadata THEN the Metadata_Manager SHALL call VizQL `/read-metadata` API instead of GraphQL API
2. WHEN VizQL API returns field metadata THEN the Metadata_Manager SHALL map `defaultAggregation` to role (null → dimension, non-null → measure)
3. WHEN VizQL API returns field metadata THEN the Metadata_Manager SHALL preserve `logicalTableId` for field-table mapping
4. WHEN looking up datasource LUID by name THEN the Metadata_Manager SHALL continue using GraphQL API `get_datasource_luid_by_name()`
5. WHEN migrating THEN the Metadata_Manager SHALL maintain backward compatibility with existing `FieldMetadata` model
6. WHEN VizQL API is unavailable THEN the Metadata_Manager SHALL fall back to GraphQL API (graceful degradation)

## Non-Functional Requirements

### NFR-1: 性能要求

- 单字段映射延迟 < 500ms（缓存命中）
- 单字段映射延迟 < 2000ms（需要 LLM）
- 索引构建延迟 < 5s（100 字段）
- 内存占用 < 500MB（单数据源索引）

### NFR-2: 可靠性要求

- LLM 调用失败时自动降级到向量检索
- 网络超时自动重试（最多 3 次）
- 缓存损坏时自动重建索引

### NFR-3: 兼容性要求

- 兼容现有 `SemanticMapper` API
- 兼容现有 `StoreManager` 缓存机制
- 兼容现有 `MetadataManager` 元数据获取

## Implementation Priority

| 阶段 | 需求 | 说明 |
|-----|------|------|
| Phase 1 | R14, R12, R1, R3, R11, R13 | 核心检索和映射能力（元数据API迁移、数据模型获取、字段索引增强、Schema Linking、Embedding 抽象、智能降级） |
| Phase 2 | R2, R4, R5, R6 | 检索增强和抽象层（两阶段检索、Rerank、检索器抽象、知识组装器） |
| Phase 3 | R7, R9, R10 | 缓存和 RAG 增强（缓存优化、维度层级 RAG、任务规划 RAG） |
| Phase 4 | R8 | 可观测性（日志监控） |

**Phase 1 实现顺序说明**：
1. **R14（元数据API迁移）**：首先迁移字段元数据获取到 VizQL API，获取 `logicalTableId`
2. **R12（数据模型获取）**：获取逻辑表和关系，建立 `logicalTableId` → 表名映射
3. **R1（字段索引增强）**：基于新的元数据结构构建增强索引
4. **R3, R11, R13**：Schema Linking、Embedding 抽象、智能降级

**关于数据模型的说明**：
- 当前元数据管理只有单表的字段元数据，需要补全数据模型信息
- VizQL Data Service 的 `/read-metadata` API 返回 `logicalTableId`，可以映射字段到逻辑表
- VizQL Data Service 的 `/get-datasource-model` API 可以获取逻辑表和关系
- GraphQL API 仍用于通过数据源名称查找 LUID

