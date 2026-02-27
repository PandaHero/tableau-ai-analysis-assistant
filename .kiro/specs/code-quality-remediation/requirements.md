# 需求文档：代码质量修复计划

## 简介

基于 `analytics_assistant/docs/deep_code_review.md` 深度代码审查报告，系统性修复项目中发现的 130+ 个问题。审查覆盖 15 个模块、约 124 个源文件，问题分布为 2 个 Critical、18 个 High、58 个 Medium、52 个 Low。本需求文档按优先级组织修复工作，确保安全关键问题优先处理，随后依次解决功能/性能、代码质量和长期改进问题。

## 术语表

- **Remediation_System**: 代码质量修复系统，负责按优先级执行所有修复任务
- **Security_Module**: 安全修复模块，处理 SSL、API Key、认证、CORS 等安全问题
- **Performance_Module**: 性能优化模块，处理重复调用、索引膨胀、异步阻塞等性能问题
- **Quality_Module**: 代码质量模块，处理代码重复、大文件拆分、规范统一等可维护性问题
- **Test_Module**: 测试补充模块，负责补充核心模块的单元测试和属性测试
- **Storage_Layer**: 存储层，包括 `infra/storage/` 中的 KV 存储、缓存管理、向量存储
- **RAG_Service**: RAG 检索服务，包括 `infra/rag/` 中的索引管理、检索服务、重排序
- **AI_Module**: AI 基础设施模块，包括 `infra/ai/` 中的 LLM 管理、Embedding 服务
- **Semantic_Parser**: 语义解析 Agent，包括 `agents/semantic_parser/` 中的 graph、components、schemas
- **Field_Mapper**: 字段映射 Agent，包括 `agents/field_mapper/` 中的 node、schemas
- **Field_Semantic**: 字段语义 Agent，包括 `agents/field_semantic/` 中的 inference、components
- **Orchestration_Layer**: 编排层，包括 `orchestration/workflow/` 中的 context、executor、callbacks
- **Platform_Layer**: 平台适配层，包括 `platform/tableau/` 中的 adapter、auth、client、data_loader
- **API_Layer**: API 层，包括 `api/` 中的路由、中间件、依赖注入

## 需求

### 需求 1：SSL 默认值修复

**用户故事：** 作为安全工程师，我希望 LLM 客户端默认启用 SSL 验证，以防止中间人攻击导致 API Key 泄露。

#### 验收标准

1. WHEN Security_Module 修复 `custom_llm.py` 时，THE Security_Module SHALL 将 `CustomChatLLM.verify_ssl` 的默认值从 `False` 改为 `True`（IAI-001）
2. THE Security_Module SHALL 确保 `CustomChatLLM.verify_ssl` 默认值与 `ModelConfig.verify_ssl` 默认值（`True`）保持一致
3. IF `app.yaml` 中 `ssl.verify` 配置为 `False`（开发环境），THEN THE Security_Module SHALL 允许通过配置覆盖 SSL 验证行为

### 需求 2：API Key 持久化安全加固

**用户故事：** 作为安全工程师，我希望 API Key 不以明文形式持久化到 SQLite，以防止数据库文件泄露时暴露所有密钥。

#### 验收标准

1. WHEN AI_Module 持久化模型配置时，THE AI_Module SHALL 对 `api_key` 字段进行加密后再存储到 SQLite（IAI-002）
2. WHEN AI_Module 从 SQLite 加载模型配置时，THE AI_Module SHALL 正确解密 `api_key` 字段
3. THE AI_Module SHALL 使用 `model_dump()` 替代手动序列化 29 个字段的方式（IAI-010），并在序列化时排除或加密 `api_key`
4. IF 加密密钥不可用，THEN THE AI_Module SHALL 记录 warning 日志并回退到环境变量引用模式（仅存储 `${ENV_VAR}` 格式的引用）

### 需求 3：API 认证增强

**用户故事：** 作为安全工程师，我希望 API 端点具备签名验证机制，以防止任意用户伪造身份访问他人数据。

#### 验收标准

1. WHEN API_Layer 接收请求时，THE API_Layer SHALL 验证请求中的 JWT token 或 API Key 签名，而非仅依赖 `X-Tableau-Username` 请求头（API-001）
2. IF 请求缺少有效的认证凭证，THEN THE API_Layer SHALL 返回 HTTP 401 状态码和描述性错误消息
3. THE API_Layer SHALL 将 CORS `allowed_origins` 默认值从 `["*"]` 改为空列表，要求在 `app.yaml` 中显式配置允许的域名（API-002）
4. WHILE `allow_credentials` 为 `True` 时，THE API_Layer SHALL 禁止 `allowed_origins` 包含 `"*"`

### 需求 4：消除语义推断重复执行

**用户故事：** 作为开发者，我希望字段语义推断在一次工作流中只执行一次，以避免 LLM 调用成本翻倍和延迟增加。

#### 验收标准

1. WHEN Platform_Layer 的 `data_loader._ensure_field_index()` 执行语义推断后，THE Orchestration_Layer SHALL 复用该推断结果，而非在 `WorkflowContext.load_field_semantic()` 中重新创建 `FieldSemanticInference` 实例并再次调用（PLAT-007）
2. THE Field_Semantic SHALL 将 `infer_field_semantic()` 便捷函数改为使用模块级单例，避免每次调用创建新实例（FS-009）
3. WHEN 语义推断结果已存在于 `data_model` 中时，THE Orchestration_Layer SHALL 直接使用已有结果而非重新推断

### 需求 5：RAG 检索结果实际使用

**用户故事：** 作为开发者，我希望 RAG 检索结果在字段语义推断中被实际使用，以减少不必要的 LLM 调用并提高推断效率。

#### 验收标准

1. WHEN Field_Semantic 的 `_infer_with_lock()` 执行步骤 4 时，THE Field_Semantic SHALL 在 `_init_rag()` 之后调用 `_rag_search()` 进行检索（FS-002）
2. WHEN RAG 检索命中高置信度结果时，THE Field_Semantic SHALL 直接使用该结果，仅将未命中的字段传递给 LLM 推断
3. THE Field_Semantic SHALL 确保自学习存入 RAG 的模式能被后续检索复用

### 需求 6：FAISS 索引完整性与膨胀修复

**用户故事：** 作为开发者，我希望 FAISS 索引支持真正的删除和更新操作，以防止索引膨胀和检索结果包含过期数据。

#### 验收标准

1. WHEN Storage_Layer 加载本地 FAISS 索引时，THE Storage_Layer SHALL 验证索引文件的 SHA-256 哈希完整性（ISTO-001）
2. WHEN RAG_Service 删除文档时，THE RAG_Service SHALL 同时从 FAISS 索引中移除对应向量，而非仅删除哈希记录（IRAG-001）
3. WHEN RAG_Service 更新文档时，THE RAG_Service SHALL 先删除旧向量再添加新向量，而非保留旧向量（IRAG-002）
4. WHEN RAG_Service 删除索引时，THE RAG_Service SHALL 同时清理磁盘上的 FAISS 索引文件（IRAG-010）

### 需求 7：异步阻塞与批量删除修复

**用户故事：** 作为开发者，我希望所有 LLM 调用在异步上下文中使用异步方式执行，并且缓存清理操作具备批量删除能力。

#### 验收标准

1. WHEN Semantic_Parser 的 `field_retriever` 执行 LLM reranker 时，THE Semantic_Parser SHALL 使用 `await llm.ainvoke()` 异步调用替代 `llm.invoke()` 同步调用（SP-012）
2. THE Storage_Layer SHALL 在存储层实现 `delete_by_filter` 批量删除方法，替代 `search(limit=10000)` + 循环删除模式（SP-013、SP-036）
3. WHEN Semantic_Parser 的 `invalidate_by_datasource` 清理缓存时，THE Semantic_Parser SHALL 使用批量删除方法而非逐条删除

### 需求 8：文件模式数据缓存

**用户故事：** 作为开发者，我希望 Insight Agent 在文件模式下首次加载数据后缓存到内存，以避免 ReAct 循环中重复读取文件。

#### 验收标准

1. WHEN Insight Agent 的 `data_store.read_batch()` 在文件模式下被调用时，THE Insight Agent SHALL 在首次加载后将数据缓存到内存（IN-001）
2. WHEN 后续调用 `read_batch()` 时，THE Insight Agent SHALL 从内存缓存中读取数据而非重新加载文件

### 需求 9：WorkflowContext 重建代码消除重复

**用户故事：** 作为开发者，我希望 WorkflowContext 的更新操作使用 `model_copy(update={})` 模式，以消除 3 处手动构造的重复代码。

#### 验收标准

1. THE Orchestration_Layer SHALL 将 `refresh_auth_if_needed()`、`update_current_time()`、`load_field_semantic()` 中的手动 WorkflowContext 构造替换为 `self.model_copy(update={...})` 调用（ORCH-001）
2. WHEN 新增 WorkflowContext 字段时，THE Orchestration_Layer SHALL 无需修改任何更新方法

### 需求 10：Semantic Parser graph.py 拆分

**用户故事：** 作为开发者，我希望 `graph.py`（1647 行）被拆分为 `nodes/` 目录结构，以提高代码可维护性和可读性。

#### 验收标准

1. THE Semantic_Parser SHALL 将 16 个节点函数拆分到 `nodes/` 目录下的独立文件中（SP-001）
2. THE Semantic_Parser SHALL 将 8 个路由函数提取到 `routes.py` 文件中
3. THE Semantic_Parser SHALL 在 `graph.py` 中仅保留 `create_semantic_parser_graph()` 和 `compile_semantic_parser_graph()` 图组装函数
4. THE Semantic_Parser SHALL 提取公共辅助函数（`parse_field_candidates`、`classify_fields`、`merge_metrics`）到 `node_utils.py`（SP-002）
5. THE Semantic_Parser SHALL 删除死代码 `route_after_validation`（SP-003）

### 需求 11：FieldMapperNode 拆分与代码去重

**用户故事：** 作为开发者，我希望 `FieldMapperNode`（750 行）被拆分为 Mixin 组件，并消除 LLM 选择逻辑的重复代码。

#### 验收标准

1. THE Field_Mapper SHALL 将 `FieldMapperNode` 拆分为 `CacheMixin`、`RAGMixin`、`LLMMixin` 三个组件（FM-001）
2. THE Field_Mapper SHALL 提取 `_map_field_with_llm_only` 和 `_map_field_with_llm_fallback` 的公共逻辑为 `_llm_select_from_candidates` 方法（FM-002）
3. THE Field_Mapper SHALL 将 `FieldMappingConfig` 从 `dataclass` 改为 Pydantic `BaseModel`（FM-005）

### 需求 12：批量 Embedding 代码去重与框架对齐

**用户故事：** 作为开发者，我希望批量 Embedding 的约 200 行重复代码被消除，并使用 LangChain Embedding 接口替代直接 aiohttp 调用。

#### 验收标准

1. THE AI_Module SHALL 提取 `embed_documents_batch_async` 和 `embed_documents_batch_with_stats_async` 的公共逻辑为 `_embed_batch_core_async` 方法（IAI-003）
2. THE AI_Module SHALL 使用 `ModelFactory.create_embedding()` 创建的 LangChain `Embeddings` 实例替代直接 aiohttp 调用（IAI-004）
3. THE AI_Module SHALL 为 `ModelManager` 单例添加 `threading.Lock` 双重检查锁定（IAI-005）
4. THE AI_Module SHALL 统一 Embedding 缓存 TTL，从 `app.yaml` 读取而非硬编码 3600s 和 86400s（IAI-012）

### 需求 13：流式处理逻辑去重

**用户故事：** 作为开发者，我希望 `agents/base/node.py` 中重复 3 次的流式 chunk 处理逻辑被提取为公共函数。

#### 验收标准

1. THE Remediation_System SHALL 提取 `_stream_structured_internal`、`_stream_structured_with_tools`、`_stream_structured_with_middleware` 中的公共流式 chunk 处理逻辑为独立函数（ABAS-001）
2. THE Remediation_System SHALL 提取 JSON Schema 注入逻辑为 `_inject_schema_instruction` 函数（ABAS-002）

### 需求 14：auth.py 同步/异步代码去重

**用户故事：** 作为开发者，我希望 `auth.py` 中 4 对同步/异步认证函数的约 400 行重复代码被消除。

#### 验收标准

1. THE Platform_Layer SHALL 提取认证函数的公共逻辑（请求构建、响应解析）为内部函数，仅在 HTTP 调用处区分同步/异步（PLAT-001）
2. THE Platform_Layer SHALL 确保修改认证逻辑时只需改一处而非 8 个函数

### 需求 15：依赖方向修正

**用户故事：** 作为开发者，我希望 `platform/` 模块不再直接导入 `agents/` 层的类型，以符合编码规范 12A.2 的依赖方向要求。

#### 验收标准

1. THE Quality_Module SHALL 将 `SemanticOutput` 和 `DerivedComputation` 从 `agents/semantic_parser/schemas/output.py` 移到 `core/schemas/` 目录（CS-003、PLAT-004）
2. THE Quality_Module SHALL 更新所有导入路径，确保 `platform/` 和 `agents/` 都从 `core/schemas/` 导入这些类型
3. THE Quality_Module SHALL 将 `api/routers/chat.py` 中对 `agents/semantic_parser/components/history_manager` 的直接导入改为通过 `orchestration/` 层间接使用（API-003）

### 需求 16：大写泛型统一修复

**用户故事：** 作为开发者，我希望项目中约 19 个文件的大写泛型（`List[str]`）统一为小写泛型（`list[str]`），以符合编码规范 17.4。

#### 验收标准

1. THE Quality_Module SHALL 将 `platform/tableau/`（6 文件）、`orchestration/workflow/`（3 文件）、`infra/storage/`（4 文件）、`infra/seeds/`（3 文件）、`infra/rag/`（3 文件）中的 `List[`、`Dict[`、`Tuple[`、`Set[` 替换为 `list[`、`dict[`、`tuple[`、`set[`（CS-004）
2. THE Quality_Module SHALL 保留 `Optional[X]` 不变（遵循编码规范 17.2）

### 需求 17：硬编码配置参数迁移

**用户故事：** 作为开发者，我希望散落在代码中的硬编码配置参数被迁移到 `app.yaml`，以符合编码规范 2.1。

#### 验收标准

1. THE Quality_Module SHALL 将以下硬编码参数迁移到 `app.yaml`：
   - `data_loader.py` 中 `batch_size = 5`（CS-001）
   - `schemas/mapping.py` 中置信度阈值 `0.7`（FM-007）
   - `store_factory.py` 中 `sweep_interval_minutes: 60`（ISTO-005）
   - `filter_validator.py` 中 `_DEFAULT_MAX_CONCURRENCY = 5`（SP-026）
   - `rule_prefilter.py` 中置信度权重 `(0.3, 0.4, 0.3)`（SP-037）
2. THE Quality_Module SHALL 确保每个迁移的参数在代码中通过 `get_config()` 读取，并保留合理的 fallback 默认值

### 需求 18：字符串替换为枚举类型

**用户故事：** 作为开发者，我希望多处使用字符串表示的类型字段被替换为枚举类型，以提高类型安全性。

#### 验收标准

1. THE Quality_Module SHALL 为 `FieldMapping.mapping_source` 定义 `MappingSource` 枚举（FM-006）
2. THE Quality_Module SHALL 为 `IntentRouterOutput.source` 定义 `IntentSource` 枚举（SP-049）
3. THE Quality_Module SHALL 将 `ComputationSeed.calc_type` 改为引用 `core/schemas/enums.py` 中的枚举类型（ISED-003）

### 需求 19：维度种子数据重构

**用户故事：** 作为开发者，我希望 `dimension.py`（2434 行）被按类别拆分为多个文件，并使用类型化数据结构替代 `Dict[str, Any]`。

#### 验收标准

1. THE Quality_Module SHALL 将 `dimension.py` 拆分为 `infra/seeds/dimensions/` 目录，按类别分文件（`time.py`、`geography.py`、`product.py` 等）（ISED-001）
2. THE Quality_Module SHALL 定义 `DimensionSeed` 和 `MeasureSeed` dataclass 替代 `List[Dict[str, Any]]`（ISED-002）
3. THE Quality_Module SHALL 实现自动生成大小写变体的函数，减少手工维护的重复数据

### 需求 20：Orchestration 层改进

**用户故事：** 作为开发者，我希望编排层的认证刷新通过平台适配器抽象，并且 executor 具备总超时控制。

#### 验收标准

1. THE Orchestration_Layer SHALL 将 `refresh_auth_if_needed()` 中硬编码的 `get_tableau_auth_async` 调用改为通过 `platform_adapter` 接口抽象（ORCH-003）
2. THE Orchestration_Layer SHALL 在 `executor.execute_stream()` 中增加总超时控制，防止持续产生 token 的长查询无限执行（ORCH-006）
3. THE Orchestration_Layer SHALL 补充 `SSECallbacks` 中缺失的节点映射（`rule_prefilter`、`filter_validator`、`output_validator` 等），改善前端进度展示（ORCH-007）

### 需求 21：核心模块测试补充

**用户故事：** 作为开发者，我希望核心模块具备基本的单元测试和属性测试覆盖，以提高代码变更的信心。

#### 验收标准

1. THE Test_Module SHALL 为 `core/schemas/` 中的 Pydantic 模型添加序列化/反序列化对称性属性测试（CORE-016）
2. THE Test_Module SHALL 为 `infra/storage/` 中的 `CacheManager` 添加存取对称性单元测试（ISTO-008）
3. THE Test_Module SHALL 为 `infra/rag/` 中的 `ExactRetriever` 添加精确匹配正确性单元测试（IRAG-014）
4. THE Test_Module SHALL 为 `agents/semantic_parser/components/error_corrector` 添加错误模式检测单元测试（SP-024）
5. THE Test_Module SHALL 为 `agents/field_mapper/` 添加字段映射核心逻辑单元测试（FM-012）
6. FOR ALL 有效的 Pydantic 模型实例 `m`，解析然后序列化再解析 SHALL 产生等价对象（`model_validate(m.model_dump()) == m`，round-trip 属性）

### 需求 22：其他代码质量修复

**用户故事：** 作为开发者，我希望审查报告中的其他中低优先级问题被系统性修复，以提升整体代码质量。

#### 验收标准

1. THE Quality_Module SHALL 添加 `ConfigurationError` 异常类到 `core/exceptions.py`（CORE-005）
2. THE Quality_Module SHALL 将 `validation.py` 中的 `ValidationError` 重命名为 `ValidationErrorDetail`，避免与 `core/exceptions.py` 中的同名异常冲突（CORE-012）
3. THE Quality_Module SHALL 移除 `execute_result.py` 中标注"向后兼容"的 `rows` 属性（CORE-013）
4. THE Quality_Module SHALL 将 `FieldCandidate` 中语义重复的字段（`field_type`/`role`、`confidence`/`score`）合并为单一字段（CORE-008）
5. THE Quality_Module SHALL 重命名 `infra/rag/exceptions.py` 中的 `IndexError` 为 `RAGIndexError`，避免与 Python 内置异常同名（IRAG-004）
6. THE Quality_Module SHALL 为 `history_manager.py` 的 `truncate_history` 方法修复 `insert(0, msg)` 导致的 O(n²) 复杂度问题（SP-028）
7. THE Quality_Module SHALL 添加重规划轮数上限控制，从 `app.yaml` 读取最大轮数（RP-003）
8. THE Quality_Module SHALL 为 API 端点的 `session_id` 路径参数添加 UUID 格式验证（API-005）
9. THE Quality_Module SHALL 为会话列表查询添加分页参数支持（API-004）
