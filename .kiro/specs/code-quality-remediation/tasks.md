# 实施计划：代码质量修复

## 概述

基于深度代码审查报告中发现的 130+ 个问题，按 6 个阶段（Phase 1-6）系统性修复。执行顺序遵循依赖关系：安全修复 → 性能基础设施 → 性能应用层 → 质量底层 → 质量重构 → 测试补充。所有修复遵循 `coding-standards.md` 编码规范。

## 任务

- [x] 1. Phase 1：P0 安全修复（需求 1-3）
  - [x] 1.1 修复 SSL 默认值（IAI-001）
    - 将 `infra/ai/custom_llm.py` 中 `CustomChatLLM.verify_ssl` 默认值从 `False` 改为 `True`
    - 确保与 `ModelConfig.verify_ssl = True` 保持一致
    - 验证 `app.yaml` 中 `ssl.verify: false` 可覆盖默认行为
    - _需求: 1.1, 1.2, 1.3_

  - [x] 1.2 实现 API Key 加密存储（IAI-002、IAI-010）
    - 在 `infra/ai/model_persistence.py` 中实现 `_encrypt_api_key` 和 `_decrypt_api_key` 方法，使用 `cryptography.fernet` 对称加密
    - 从环境变量 `ANALYTICS_ASSISTANT_ENCRYPTION_KEY` 读取加密密钥
    - 密钥不可用时回退到环境变量引用模式 `${ENV_VAR}`，记录 warning 日志
    - 将 `_config_to_dict` 替换为 `config.model_dump()`，序列化时加密 `api_key`
    - _需求: 2.1, 2.2, 2.3, 2.4_

  - [x] 1.3 编写 API Key 加密 round-trip 属性测试
    - **Property 1: API Key 加密 round-trip**
    - 在 `tests/infra/ai/test_api_key_encryption.py` 中使用 Hypothesis 验证 `decrypt(encrypt(key)) == key` 且 `encrypt(key) != key`
    - **验证: 需求 2.1, 2.2**

  - [x] 1.4 编写 ModelConfig 序列化完整性属性测试
    - **Property 2: ModelConfig 序列化完整性**
    - 在 `tests/infra/ai/test_api_key_encryption.py` 中验证 `model_dump()` 包含所有字段，且 `ModelConfig(**config.model_dump())` 产生等价对象
    - **验证: 需求 2.3**

  - [x] 1.5 实现 API 认证增强（API-001、API-002）
    - 在 `api/dependencies.py` 中增加 JWT token 验证逻辑，支持 `Authorization` 请求头
    - 缺少有效认证凭证时返回 HTTP 401
    - 在 `api/main.py` 中将 CORS `allowed_origins` 默认值改为空列表
    - 实现 `allow_credentials=True` 时禁止 `allowed_origins` 包含 `"*"` 的安全检查
    - 在 `app.yaml` 中添加 `api.auth` 和 `api.cors` 配置节
    - _需求: 3.1, 3.2, 3.3, 3.4_

  - [x] 1.6 编写认证验证属性测试
    - **Property 3: 无效认证凭证拒绝**
    - 在 `tests/api/test_auth.py` 中使用 FastAPI TestClient 验证无效凭证返回 HTTP 401
    - **验证: 需求 3.1**

  - [x] 1.7 编写 CORS 配置互斥属性测试
    - **Property 4: CORS credentials 与 wildcard 互斥**
    - 在 `tests/api/test_cors.py` 中验证 `allow_credentials=True` 且 `allowed_origins=["*"]` 时自动禁用 credentials
    - **验证: 需求 3.4**

- [x] 2. Phase 1 检查点
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 3. Phase 2：P1 性能修复 - 基础设施层（需求 6-7）
  - [x] 3.1 实现 FAISS 索引完整性校验（ISTO-001）
    - 在 `infra/storage/vector_store.py` 中实现 `_verify_index_integrity` 方法，加载时验证 SHA-256 哈希
    - 保存索引时同时写入 `.sha256` 哈希文件
    - 无哈希文件时向前兼容（跳过验证）
    - _需求: 6.1_

  - [x] 3.2 编写 FAISS 索引完整性属性测试
    - **Property 5: FAISS 索引完整性校验**
    - 在 `tests/infra/storage/test_faiss_integrity.py` 中验证哈希不匹配时加载失败
    - **验证: 需求 6.1**

  - [x] 3.3 实现 FAISS 真正的文档删除和更新（IRAG-001、IRAG-002、IRAG-010）
    - 在 `infra/rag/index_manager.py` 中修改 `delete_documents` 方法，同时从 FAISS 索引中移除向量
    - 实现更新操作为先删除旧向量再添加新向量
    - 在 `delete_index` 中同时清理磁盘上的 FAISS 索引文件
    - _需求: 6.2, 6.3, 6.4_

  - [x] 3.4 编写索引操作一致性属性测试
    - **Property 6: 索引操作后检索一致性**
    - 在 `tests/infra/rag/test_index_operations.py` 中验证删除的文档不出现在检索结果中，更新的文档返回最新版本
    - **验证: 需求 6.2, 6.3**

  - [x] 3.5 修复异步阻塞调用（SP-012）
    - 将 `agents/semantic_parser/components/field_retriever.py` 中 `_llm_rerank` 的 `llm.invoke()` 改为 `await llm.ainvoke()`
    - _需求: 7.1_

  - [x] 3.6 实现批量删除方法（SP-013、SP-036）
    - 在 `infra/storage/cache.py` 的 `CacheManager` 中实现 `delete_by_filter` 方法
    - 将 `agents/semantic_parser/` 中 `invalidate_by_datasource` 的逐条删除改为使用批量删除
    - _需求: 7.2, 7.3_

  - [x] 3.7 编写批量删除正确性属性测试
    - **Property 7: 批量删除正确性**
    - 在 `tests/infra/storage/test_cache_manager.py` 中验证 `delete_by_filter` 删除所有满足条件的项且不影响其他项
    - **验证: 需求 7.2**

- [x] 4. Phase 2 检查点
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 5. Phase 3：P1 性能修复 - 应用层（需求 4-5、8）
  - [x] 5.1 启用 RAG 检索结果实际使用（FS-002）
    - 修改 `agents/field_semantic/inference.py` 的 `_infer_with_lock()` 步骤 4，在 `_init_rag()` 之后调用 `_rag_search()` 进行检索
    - RAG 高置信度命中结果直接使用，仅将未命中字段传递给 LLM 推断
    - 确保自学习存入 RAG 的模式能被后续检索复用
    - _需求: 5.1, 5.2, 5.3_

  - [x] 5.2 消除语义推断重复执行（PLAT-007、FS-009）
    - 将 `agents/field_semantic/inference.py` 中 `infer_field_semantic()` 便捷函数改为模块级单例模式（双重检查锁定）
    - 修改 `orchestration/workflow/context.py` 的 `load_field_semantic()` 检查 `data_model` 中是否已有语义结果，有则直接复用
    - 修改 `platform/tableau/data_loader.py` 的 `_ensure_field_index()` 将推断结果存入 `DataModel` 扩展属性
    - _需求: 4.1, 4.2, 4.3_

  - [x] 5.3 实现文件模式数据缓存（IN-001）
    - 在 `agents/insight/components/data_store.py` 中添加 `_cached_file_data` 属性
    - 文件模式下首次加载后缓存到内存，后续调用从缓存读取
    - _需求: 8.1, 8.2_

- [x] 6. Phase 3 检查点
  - 确保所有测试通过，如有问题请向用户确认。

- [ ] 7. Phase 4：P2 质量修复 - 底层先行（需求 15-18）
  - [x] 7.1 修正依赖方向（CS-003、PLAT-004、API-003）
    - 将 `SemanticOutput` 和 `DerivedComputation` 从 `agents/semantic_parser/schemas/output.py` 移到 `core/schemas/semantic_output.py`
    - 在原文件中改为从 `core/schemas/` 导入并重新导出（过渡期）
    - 更新 `platform/tableau/adapter.py` 等所有导入路径
    - 将 `api/routers/chat.py` 中对 `agents/semantic_parser/components/history_manager` 的直接导入改为通过 `orchestration/` 层间接使用
    - _需求: 15.1, 15.2, 15.3_

  - [x] 7.2 统一大写泛型为小写泛型（CS-004）
    - 将约 19 个文件中的 `List[`、`Dict[`、`Tuple[`、`Set[` 替换为 `list[`、`dict[`、`tuple[`、`set[`
    - 涉及目录：`platform/tableau/`（6 文件）、`orchestration/workflow/`（3 文件）、`infra/storage/`（4 文件）、`infra/seeds/`（3 文件）、`infra/rag/`（3 文件）
    - 保留 `Optional[X]` 不变
    - _需求: 16.1, 16.2_

  - [x] 7.3 迁移硬编码配置参数到 app.yaml（CS-001、FM-007、ISTO-005、SP-026、SP-037）
    - 在 `app.yaml` 中添加配置节：`platform.tableau.data_loader.batch_size`、`field_mapper.low_confidence_threshold`、`storage.sqlite.sweep_interval_minutes`、`semantic_parser.filter_validator.max_concurrency`、`semantic_parser.rule_prefilter.confidence_weights`
    - 修改对应代码文件通过 `get_config()` 读取，保留 `_DEFAULT_*` 常量作为 fallback
    - _需求: 17.1, 17.2_

  - [x] 7.4 字符串替换为枚举类型（FM-006、SP-049、ISED-003）
    - 在 `agents/field_mapper/schemas/mapping.py` 中定义 `MappingSource` 枚举
    - 在 `agents/semantic_parser/schemas/` 中定义 `IntentSource` 枚举
    - 将 `infra/seeds/computation.py` 中 `ComputationSeed.calc_type` 改为引用 `core/schemas/enums.py` 中的枚举类型
    - 更新所有使用字符串字面量的地方改为使用枚举
    - _需求: 18.1, 18.2, 18.3_

- [x] 8. Phase 4 检查点
  - 确保所有测试通过，如有问题请向用户确认。

- [ ] 9. Phase 5：P2 质量修复 - 代码去重与重构（需求 9-14、19-20）
  - [x] 9.1 WorkflowContext 重建代码消除重复（ORCH-001）
    - 将 `orchestration/workflow/context.py` 中 `refresh_auth_if_needed()`、`update_current_time()`、`load_field_semantic()` 的手动构造替换为 `self.model_copy(update={...})`
    - _需求: 9.1, 9.2_

  - [x] 9.2 批量 Embedding 代码去重与框架对齐（IAI-003、IAI-004、IAI-005、IAI-012）
    - 在 `infra/ai/model_manager.py` 中提取 `_embed_batch_core_async` 公共核心方法
    - 使用 `ModelFactory.create_embedding()` 替代直接 aiohttp 调用
    - 为 `ModelManager` 单例添加 `threading.Lock` 双重检查锁定
    - 统一 Embedding 缓存 TTL 从 `app.yaml` 的 `ai.embedding_cache_ttl` 读取
    - _需求: 12.1, 12.2, 12.3, 12.4_

  - [x] 9.3 编写 ModelManager 单例线程安全属性测试
    - **Property 8: ModelManager 单例线程安全**
    - 在 `tests/infra/ai/test_model_manager_singleton.py` 中验证并发线程获得同一实例
    - **验证: 需求 12.3**

  - [x] 9.4 流式处理逻辑去重（ABAS-001、ABAS-002）
    - 在 `agents/base/node.py` 中提取 `_collect_stream_chunks` 公共流式 chunk 处理函数
    - 提取 `_inject_schema_instruction` JSON Schema 注入函数
    - 将 `_stream_structured_internal`、`_stream_structured_with_tools`、`_stream_structured_with_middleware` 改为调用公共函数
    - _需求: 13.1, 13.2_

  - [x] 9.5 auth.py 同步/异步代码去重（PLAT-001）
    - 在 `platform/tableau/auth.py` 中提取 `_build_jwt_auth_request` 和 `_parse_auth_response` 公共逻辑函数
    - 将 4 对同步/异步认证函数改为调用公共逻辑，仅在 HTTP 调用处区分同步/异步
    - _需求: 14.1, 14.2_

  - [x] 9.6 Semantic Parser graph.py 拆分（SP-001、SP-002、SP-003）
    - 创建 `agents/semantic_parser/nodes/` 目录，将 16 个节点函数拆分到独立文件（`intent.py`、`cache.py`、`optimization.py`、`retrieval.py`、`understanding.py`、`validation.py`、`execution.py`）
    - 提取 8 个路由函数到 `routes.py`
    - 提取 `parse_field_candidates`、`classify_fields`、`merge_metrics` 到 `node_utils.py`
    - 在 `graph.py` 中仅保留 `create_semantic_parser_graph()` 和 `compile_semantic_parser_graph()`
    - 删除死代码 `route_after_validation`
    - _需求: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 9.7 FieldMapperNode 拆分与代码去重（FM-001、FM-002、FM-005）
    - 创建 `agents/field_mapper/components/` 目录，拆分为 `cache_mixin.py`、`rag_mixin.py`、`llm_mixin.py`
    - 在 `llm_mixin.py` 中提取 `_llm_select_from_candidates` 公共方法，消除 `_map_field_with_llm_only` 和 `_map_field_with_llm_fallback` 的重复
    - 将 `FieldMappingConfig` 从 `dataclass` 改为 Pydantic `BaseModel`，放入 `schemas/config.py`
    - _需求: 11.1, 11.2, 11.3_

  - [x] 9.8 维度种子数据重构（ISED-001、ISED-002）
    - 将 `infra/seeds/dimension.py`（2434 行）拆分为 `infra/seeds/dimensions/` 目录，按类别分文件（`time.py`、`geography.py`、`product.py`、`customer.py`、`organization.py`、`channel.py`、`financial.py`、`common.py`）
    - 定义 `DimensionSeed` 和 `MeasureSeed` dataclass 替代 `list[dict[str, Any]]`
    - 实现 `generate_case_variants` 自动生成大小写变体函数
    - 在 `__init__.py` 中汇总导出 `DIMENSION_SEEDS`
    - _需求: 19.1, 19.2, 19.3_

  - [x] 9.9 编写种子数据类型完整性属性测试
    - **Property 9: 种子数据类型完整性**
    - 在 `tests/infra/seeds/test_dimension_seeds.py` 中验证 `DimensionSeed` 的 `granularity` 与 `level` 一致，必填字段不为空
    - **验证: 需求 19.2**

  - [x] 9.10 编写大小写变体生成正确性属性测试
    - **Property 10: 大小写变体生成正确性**
    - 在 `tests/infra/seeds/test_dimension_seeds.py` 中验证变体列表包含原始种子，且仅 `field_caption` 大小写不同
    - **验证: 需求 19.3**

  - [x] 9.11 Orchestration 层改进（ORCH-003、ORCH-006、ORCH-007）
    - 将 `orchestration/workflow/context.py` 中 `refresh_auth_if_needed()` 的硬编码 `get_tableau_auth_async` 改为通过 `platform_adapter` 接口抽象
    - 在 `orchestration/workflow/executor.py` 中增加总超时控制（超时值从 `app.yaml` 读取）
    - 在 `orchestration/workflow/callbacks.py` 中补充 `_VISIBLE_NODE_MAPPING` 缺失的节点映射（`rule_prefilter`、`filter_validator`、`output_validator`、`error_corrector`）
    - _需求: 20.1, 20.2, 20.3_

- [x] 10. Phase 5 检查点
  - 确保所有测试通过，如有问题请向用户确认。

- [x] 11. Phase 6：P3 测试补充与其他质量修复（需求 21-22）
  - [x] 11.1 添加 `ConfigurationError` 异常类（CORE-005）
    - 在 `core/exceptions.py` 中添加 `ConfigurationError` 异常类，包含 `config_key` 属性
    - _需求: 22.1_

  - [x] 11.2 重命名冲突的 `ValidationError`（CORE-012）
    - 将 `core/schemas/validation.py` 中的 `ValidationError` 重命名为 `ValidationErrorDetail`
    - 更新所有引用该类的导入路径
    - _需求: 22.2_

  - [x] 11.3 移除向后兼容的 `rows` 属性（CORE-013）
    - 移除 `core/schemas/execute_result.py` 中标注"向后兼容"的 `rows` 属性
    - 更新所有使用 `rows` 的调用方改为使用正确的属性
    - _需求: 22.3_

  - [x] 11.4 合并 FieldCandidate 语义重复字段（CORE-008）
    - 将 `core/schemas/field_candidate.py` 中 `field_type`/`role` 合并为 `role`，`confidence`/`score` 合并为 `confidence`
    - 更新所有引用旧字段名的代码
    - _需求: 22.4_

  - [x] 11.5 重命名 `IndexError` 为 `RAGIndexError`（IRAG-004）
    - 将 `infra/rag/exceptions.py` 中的 `IndexError` 重命名为 `RAGIndexError`，避免与 Python 内置异常同名
    - 更新所有引用该异常的导入路径
    - _需求: 22.5_

  - [x] 11.6 修复历史截断 O(n²) 复杂度（SP-028）
    - 修改 `agents/semantic_parser/components/history_manager.py` 的 `truncate_history` 方法，将 `insert(0, msg)` 改为从尾部收集后反转
    - _需求: 22.6_

  - [x] 11.7 编写历史截断正确性属性测试
    - **Property 14: 历史截断正确性**
    - 在 `tests/agents/semantic_parser/components/test_history_manager.py` 中验证截断结果总 token 不超限、保留最新消息、顺序一致
    - **验证: 需求 22.6**

  - [x] 11.8 添加重规划轮数上限控制（RP-003）
    - 在 `agents/replanner/graph.py` 中添加重规划轮数上限，从 `app.yaml` 的 `replanner.max_replan_rounds` 读取
    - _需求: 22.7_

  - [x] 11.9 API 端点 session_id UUID 格式验证（API-005）
    - 在 `api/routers/sessions.py` 中为 `session_id` 路径参数添加 UUID 格式验证
    - _需求: 22.8_

  - [x] 11.10 编写 UUID 格式验证属性测试
    - **Property 15: UUID 格式验证**
    - 在 `tests/api/test_uuid_validation.py` 中验证非 UUID 字符串返回 HTTP 422，有效 UUID 正常处理
    - **验证: 需求 22.8**

  - [x] 11.11 会话列表分页参数支持（API-004）
    - 在 `api/routers/sessions.py` 中为会话列表查询添加 `offset` 和 `limit` 分页参数
    - _需求: 22.9_

  - [x] 11.12 编写分页参数正确性属性测试
    - **Property 16: 分页参数正确性**
    - 在 `tests/api/test_pagination.py` 中验证返回结果数量不超过 `limit`，且是完整列表从 `offset` 开始的子序列
    - **验证: 需求 22.9**

  - [x] 11.13 编写 Pydantic 模型序列化 round-trip 属性测试
    - **Property 11: Pydantic 模型序列化 round-trip**
    - 在 `tests/core/schemas/test_schemas_roundtrip.py` 中使用 Hypothesis 对 `Field`、`DataModel`、`ExecuteResult`、`FieldCandidate`、`ValidationResult` 等模型验证 `model_validate(m.model_dump()) == m`
    - **验证: 需求 21.1, 21.6**

  - [x] 11.14 编写 CacheManager 存取对称性属性测试
    - **Property 12: CacheManager 存取对称性**
    - 在 `tests/infra/storage/test_cache_manager.py` 中验证 `set(key, value)` 后 `get(key)` 返回等价对象
    - **验证: 需求 21.2**

  - [x] 11.15 编写 ExactRetriever 精确匹配正确性属性测试
    - **Property 13: ExactRetriever 精确匹配正确性**
    - 在 `tests/infra/rag/test_exact_retriever.py` 中验证精确匹配字段名或 caption 时返回置信度 1.0
    - **验证: 需求 21.3**

  - [x] 11.16 编写错误模式检测单元测试
    - 在 `tests/agents/semantic_parser/components/test_error_corrector.py` 中测试错误模式检测逻辑
    - Mock LLM 调用，验证错误分类和修正建议
    - _需求: 21.4_

  - [x] 11.17 编写字段映射核心逻辑单元测试
    - 在 `tests/agents/field_mapper/test_field_mapper.py` 中测试字段映射核心逻辑
    - Mock LLM 调用，验证缓存命中、RAG 检索、LLM fallback 等路径
    - _需求: 21.5_

- [x] 12. 最终检查点
  - 确保所有测试通过，如有问题请向用户确认。

## 备注

- 所有任务（包括属性测试和单元测试）均为必须完成的任务
- 每个任务引用了具体的需求编号和问题 ID，确保可追溯性
- 检查点任务确保增量验证，避免问题累积
- 属性测试验证通用正确性属性，单元测试验证具体示例和边界情况
- Phase 4 的依赖方向修正（任务 7.1）必须在 Phase 5 的文件拆分（任务 9.6、9.7）之前完成
