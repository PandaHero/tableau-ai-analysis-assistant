# Implementation Plan: Dimension Hierarchy Agent 优化

## Overview

采用 **RAG 优先 + LLM 兜底 + 延迟加载样例数据** 方案优化 Dimension Hierarchy Agent，实现：
- 存储分离：FAISS（向量索引）+ LangGraph Store（缓存和元数据）
- 增量推断：只对新增/变更字段进行推断（支持检测字段元数据变化）
- 延迟加载：只对 RAG 未命中字段查询样例数据
- 自学习：高置信度结果存入 RAG，越用越聪明

## Requirements 映射

| 需求编号 | 需求名称 | 验收标准 |
|---------|---------|---------|
| 1.1 | RAG 优先推断 | RAG 相似度 >= 0.92（seed/verified）或 >= 0.95（llm/unverified）直接复用 |
| 1.2 | LLM 兜底 | RAG 未命中时调用 LLM |
| 1.3 | 自学习 | 高置信度(>=0.85)结果存入 RAG |
| 1.4 | 命中率统计 | 记录 RAG 命中率 |
| 2.1 | 批量 Embedding | N 字段 = 1 次 API 调用 |
| 2.2 | 批量检索 | 支持批量向量检索 |
| 2.3 | 持久化索引 | FAISS 索引持久化到磁盘 |
| 3.1 | 种子数据 | 预置 44 个常见维度模式（6 个类别） |
| 3.2 | 自动初始化 | 索引为空时自动初始化 |
| 3.3 | 中英文支持 | 支持中英文字段名 |
| 4.1 | 性能指标 | 记录命中率、调用次数、延迟 |
| 4.2 | 指标导出 | 支持指标导出 |

## Tasks

- [-] 1. 缓存存储层实现（LangGraph Store）
  - [x] 1.1 创建 `cache_storage.py` 文件
    - 定义 namespace 常量：`NS_HIERARCHY_CACHE`, `NS_DIMENSION_PATTERNS_METADATA`
    - 定义阈值常量：`RAG_SIMILARITY_THRESHOLD=0.92`, `RAG_SIMILARITY_THRESHOLD_UNVERIFIED=0.95`, `RAG_STORE_CONFIDENCE_THRESHOLD=0.85`
    - 定义并发控制常量：`MAX_LOCKS=1000`, `LOCK_EXPIRE_SECONDS=3600`
    - 实现 `PatternSource` 枚举（seed, llm, manual）
    - 实现 `compute_field_hash_metadata_only()` 函数（整体 hash）
    - 实现 `compute_single_field_hash()` 函数（单字段 hash，用于检测变更）
    - _Requirements: 1.1, 1.3_
  - [x] 1.2 实现 `DimensionHierarchyCacheStorage` 类
    - 实现 `get_hierarchy_cache()`, `put_hierarchy_cache()`（**包含 field_meta_hashes**）, `delete_hierarchy_cache()`
    - 实现 `get_pattern_metadata()`, `store_pattern_metadata()`, `delete_pattern_metadata()`
    - 实现 `update_pattern_verified()`, `get_all_pattern_metadata()`, `clear_pattern_metadata()`
    - _Requirements: 1.1, 1.3_
  - [ ] 1.3 编写缓存存储层单元测试并通过
    - 测试缓存 CRUD 操作（get/put/delete）
    - 测试模式元数据 CRUD 操作（get/store/delete/clear/get_all）
    - 测试 `update_pattern_verified()` 验证状态更新
    - 测试 field_hash 计算（仅用元数据，不含样例数据）
    - 测试 single_field_hash 计算
    - **验收标准**：所有测试通过
    - _Requirements: 1.1, 1.3_

- [ ] 2. FAISS 向量索引实现
  - [ ] 2.1 创建 `faiss_store.py` 文件
    - 实现 `DimensionPatternFAISS` 类
    - 实现 `load_or_create()`, `_create_empty_index()`
    - 实现 `_normalize_vectors()` 辅助方法（**L2 归一化**）
    - 实现 `add_pattern()`, `batch_add_patterns()`（**入库时 L2 归一化**）
    - 实现 `search()`, `batch_search()`（**查询时 L2 归一化**）
    - 实现 `save()`, `rebuild_index()`
    - 实现 `count` 属性
    - _Requirements: 1.1, 2.1, 2.2, 2.3_
  - [ ] 2.2 编写 FAISS 向量索引单元测试并通过
    - 测试索引创建和加载（持久化）
    - 测试单个/批量添加模式
    - 测试单个/批量检索
    - 测试 `rebuild_index()` 重建索引
    - **验收标准**：所有测试通过
    - _Requirements: 2.1, 2.2, 2.3_
  - [ ] 2.3 相似度阈值校准验证（用真实 Embedding API，不用 mock）
    - 测试同义词相似度："年" vs "年份" 应 > 0.85
    - 测试中英同义："城市" vs "City" 应 > 0.85
    - 测试不同类别："年" vs "城市" 应 < 0.80
    - 测试不同类别："客户名称" vs "产品类别" 应 < 0.80
    - **验收标准**：阈值验证通过，确认 0.92/0.95 能有效区分同义/非同义
    - _Requirements: 1.1_

- [ ] 3. RAG 检索器实现
  - [ ] 3.1 创建 `rag_retriever.py` 文件
    - 实现 `DimensionRAGRetriever` 类
    - 实现 `batch_search_metadata_only()`（仅用元数据检索，返回 pattern + similarity）
    - 实现 `_build_query_text_metadata_only()`
    - 实现 `generate_pattern_id(field_caption, data_type, datasource_luid)` 静态方法（**包含 data_type 避免碰撞**）
    - 实现 `store_pattern()`（同步方法，存入 FAISS + Store，含重复检查）
    - 实现 `_get_effective_threshold(pattern)` 方法（**根据 source/verified 返回不同阈值**）
    - _Requirements: 1.1, 2.1, 2.2_
  - [ ] 3.2 编写 RAG 检索器单元测试并通过
    - 测试批量检索（返回 pattern + similarity）
    - 测试 pattern_id 生成（**验证包含 data_type，同名不同类型不碰撞**）
    - 测试模式存储（含重复检查，已存在时跳过）
    - 测试阈值分层（seed/verified=0.92, llm/unverified=0.95）
    - **验收标准**：所有测试通过
    - _Requirements: 1.1, 2.1, 2.2_

- [ ] 4. 种子数据模块实现
  - [ ] 4.1 创建 `seed_data.py` 文件
    - 定义 `SEED_PATTERNS` 列表（44 个常见维度模式，覆盖 6 个类别，含中英文）
    - 实现 `get_seed_few_shot_examples()` 函数
    - 实现 `initialize_seed_patterns()` 异步函数（批量添加到 FAISS + 统一保存一次）
    - _Requirements: 3.1, 3.2, 3.3_
  - [ ] 4.2 编写种子数据单元测试并通过
    - 测试种子数据初始化（验证 44 个模式全部入库）
    - 测试 few-shot 示例获取
    - **验收标准**：所有测试通过，FAISS 索引包含 44 个向量
    - _Requirements: 3.1, 3.2, 3.3_

- [ ] 5. LLM 推断模块实现
  - [ ] 5.1 创建 `llm_inference.py` 文件
    - 定义 `MAX_FIELDS_PER_INFERENCE=30` 常量
    - 实现 `infer_dimensions_once()` 异步函数（一次性推断）
    - 实现 `_build_few_shot_section()` 辅助函数（文案：Reference Examples from seed patterns）
    - _Requirements: 1.2_
  - [ ] 5.2 编写 LLM 推断集成测试并通过（用真实 LLM API，不用 mock）
    - 测试一次性推断（3-5 个字段）
    - 测试 few-shot 构建
    - **验收标准**：所有测试通过，返回有效的 DimensionHierarchyResult
    - _Requirements: 1.2_

- [ ] 6. Checkpoint - 确保基础模块测试通过
  - 运行所有单元测试
  - **验收标准**：
    - 所有单元测试通过
    - `batch_search()` 20 字段只触发 1 次 Embedding API 调用
    - 相似度阈值校准验证通过
    - pattern_id 不因 data_type 冲突覆盖（同名不同类型生成不同 ID）
  - 如有问题，与用户讨论

- [ ] 7. 主推断流程实现
  - [ ] 7.1 创建 `inference.py` 文件
    - 实现 `compute_single_field_hash()` 函数
    - 实现 `compute_incremental_fields()` 函数（**返回 new/changed/deleted/unchanged 四类**）
    - 实现 `build_cache_key()` 函数
    - 实现 `DimensionHierarchyInference` 类
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [ ] 7.2 实现并发控制
    - 实现 `_get_lock()`, `_cleanup_old_locks()` 方法
    - 按 cache_key 粒度加锁
    - _Requirements: 1.1_
  - [ ] 7.3 实现种子数据初始化和一致性检查
    - 实现 `_ensure_seed_data()` 方法（首次调用时自动初始化）
    - 实现 `_auto_repair_consistency()` 方法（**从 metadata 重新构造 query_text，再 rebuild FAISS**）
    - _Requirements: 3.1, 3.2_
  - [ ] 7.4 实现主推断逻辑
    - 实现 `infer()` 方法（入口，获取锁，支持 `force_refresh`、`skip_rag_store`、`logical_table_id` 参数）
    - 实现 `_infer_with_lock()` 方法（缓存检查 + 增量推断 + RAG + LLM）
    - 实现 `_infer_with_llm_batched()` 方法（分批 LLM 推断，每批 ≤30 字段）
    - 实现 `_store_to_rag()` 方法（高置信度 ≥0.85 结果存入 RAG）
    - 实现 `get_stats()`, `reset_stats()` 方法
    - **RAG 命中时 sample_values=None, unique_count=None**
    - **缓存存储时包含 field_meta_hashes**
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [ ] 7.5 编写主推断流程单元测试并通过
    - 测试缓存完全命中场景（直接返回）
    - 测试增量推断场景 - 新增字段（进入 RAG/LLM）
    - 测试增量推断场景 - 删除字段（从结果中移除）
    - **测试增量推断场景 - 字段变更（caption/dataType 变化触发重推断）**
    - 测试 RAG 命中场景（**验证 sample_values=None**）
    - 测试 LLM 推断场景（高置信度存入 RAG）
    - 测试并发控制（**同一 cache_key 并发 5 次只做 1 次 LLM 调用**）
    - 测试 `force_refresh` 参数（跳过缓存）
    - 测试 `skip_rag_store` 参数（不存入 RAG）
    - **测试一致性自动修复（从 metadata 重建 FAISS，验证 query_text 正确构造）**
    - 测试阈值分层（seed=0.92, llm/unverified=0.95）
    - **验收标准**：所有测试通过
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 8. 模型修改
  - [ ] 8.1 修改 `DimensionAttributes` 模型
    - 将 `unique_count` 改为 `Optional[int]`，默认 `None`
    - 将 `sample_values` 改为 `Optional[List[str]]`，默认 `None`
    - 更新字段描述，说明 RAG 命中时可为 None
    - _Requirements: 1.1_

- [ ] 9. 节点集成
  - [ ] 9.1 更新 `node.py` 维度层级推断节点
    - 创建 `DimensionHierarchyInference` 实例
    - 实现单表数据源处理逻辑（直接推断，**设置 merged_hierarchy**）
    - 实现多表数据源处理逻辑（按表分组，`asyncio.gather` 并发推断，合并结果）
    - 实现 `sample_value_fetcher` 延迟加载函数
    - 实现 `_update_fields_with_hierarchy()` 辅助函数
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [ ] 9.2 编写节点集成测试并通过
    - 测试单表数据源推断
    - 测试多表数据源推断（并发推断 + 结果合并）
    - 测试延迟加载样例数据（**只查 RAG 未命中字段**）
    - **验收标准**：所有测试通过
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 10. Checkpoint - 确保集成测试通过
  - 运行所有测试
  - **验收标准**：
    - 所有单元测试和集成测试通过
    - RAG 命中时返回 sample_values=None
    - 并发同 cache_key 5 次调用只做 1 次 LLM 调用（其余复用）
    - 延迟加载只查询 RAG 未命中字段的样例数据
    - 字段 caption/dataType 变化时触发重推断
    - 一致性修复时正确从 metadata 构造 query_text
  - 如有问题，与用户讨论

- [ ] 11. 性能监控实现
  - [ ] 11.1 添加性能指标收集
    - 在 `DimensionHierarchyInference` 中添加统计字段
    - 实现 `get_stats()` 方法返回 RAG 命中率、LLM 调用次数等
    - _Requirements: 4.1, 4.2_
  - [ ] 11.2 编写性能监控测试并通过
    - 测试统计数据收集
    - 测试统计重置
    - **验收标准**：所有测试通过
    - _Requirements: 4.1, 4.2_

- [ ] 12. Final Checkpoint - 完整功能验证
  - 运行所有测试
  - **验收标准**：
    - 所有测试通过
    - 20 字段推断耗时 < 2s（80% RAG 命中时）
    - RAG 命中率统计正确
    - 阈值分层生效（seed=0.92, llm/unverified=0.95）
    - 字段变更检测生效
  - 如有问题，与用户讨论

## Notes

- All tasks are required (including unit tests)
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation with quantifiable acceptance criteria
- 实现顺序：存储层 → FAISS → RAG 检索器 → 种子数据 → LLM 推断 → 主流程 → 节点集成
- 关键依赖：FAISS 依赖 embedding_provider，RAG 检索器依赖 FAISS 和 LangGraph Store
- **测试策略**：使用真实 Embedding API 和 LLM API，不使用 mock（确保真实行为验证）

## 关键实现约束

1. **向量归一化**：入库和查询时都必须 L2 归一化，否则相似度分数无意义
2. **pattern_id 规则**：`md5(field_caption|data_type|scope)[:16]`，包含 data_type 避免碰撞
3. **阈值分层**：seed/verified=0.92, llm/unverified=0.95，防止 RAG 污染
4. **增量推断**：支持检测字段变更（new + changed 都进入 RAG/LLM），缓存包含 field_meta_hashes
5. **一致性修复**：rebuild_index 时从 metadata 重新构造 query_text
6. **单进程假设**：当前锁机制为进程内，多实例部署需额外处理
7. **FAISS 安全**：`allow_dangerous_deserialization=True` 仅用于本地可信索引文件
