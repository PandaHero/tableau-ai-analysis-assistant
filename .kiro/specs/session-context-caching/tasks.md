# 实现计划

## 阶段 1：添加新组件

- [x] 1. 创建 LangGraph SqliteStore 全局实例




  - [x] 1.1 创建 `tableau_assistant/src/infra/storage/langgraph_store.py`


    - 实现 `get_langgraph_store()` 单例函数
    - 配置 TTL: default_ttl=1440, refresh_on_read=True
    - 配置数据库路径: `data/langgraph_store.db`
    - 实现 `reset_langgraph_store()` 用于测试
    - _Requirements: 1.1, 1.2_

  - [x] 1.2 编写属性测试：缓存存储命名空间一致性


    - **Property 1: 缓存存储命名空间一致性**
    - **验证: 需求 1.4**



- [x] 2. 创建 DataModelCache 封装类

  - [x] 2.1 创建 `tableau_assistant/src/infra/storage/data_model_cache.py`

    - 实现 `DataModelCache` 类
    - 实现 `get_or_load()` 方法（缓存优先）
    - 实现 `_get_from_cache()` 私有方法
    - 实现 `_put_to_cache()` 私有方法
    - 实现 `invalidate()` 方法
    - 定义命名空间常量: DATA_MODEL_NAMESPACE, HIERARCHY_NAMESPACE
    - _Requirements: 2.1, 2.2, 2.3, 2.5_



  - [x] 2.2 编写属性测试：缓存命中时跳过 API 调用
    - **Property 2: 缓存命中时跳过 API 调用**
    - **验证: 需求 2.2, 3.2, 3.3**

  - [x] 2.3 编写属性测试：缓存写入 TTL 一致性

    - **Property 3: 缓存写入 TTL 一致性**
    - **验证: 需求 2.5**

  - [x] 2.4 编写属性测试：缓存读写往返一致性

    - **Property 5: 缓存读写往返一致性**
    - **验证: 需求 2.5, 2.6**

- [x] 3. 创建 DataModelLoader 接口和实现


  - [x] 3.1 创建 `tableau_assistant/src/infra/storage/data_model_loader.py`


    - 定义 `DataModelLoader` 抽象基类
    - 实现 `TableauDataModelLoader` 类
    - 实现 `load_data_model()` 方法（调用 Tableau API）
    - 实现 `infer_dimension_hierarchy()` 方法（调用 LLM Agent）
    - _Requirements: 2.3, 2.4_



- [x] 4. Checkpoint - 确保所有测试通过

  - 确保所有测试通过，如有问题请询问用户。

## 阶段 2：修改 WorkflowExecutor

- [x] 5. 修改 WorkflowExecutor 使用新缓存
  - [x] 5.1 修改 `tableau_assistant/src/orchestration/workflow/executor.py`
    - 在 `__init__()` 中初始化 `_langgraph_store` 和 `_data_model_cache`
    - 在 `run()` 中使用 `DataModelCache.get_or_load()` 替代 `ctx.ensure_metadata_loaded()`
    - 在 `stream()` 中同样使用 `DataModelCache.get_or_load()`
    - 移除对 `ctx.ensure_metadata_loaded()` 的调用
    - _Requirements: 2.1, 2.2, 2.6_

  - [x] 5.2 编写属性测试：TTL 过期后重新加载
    - **Property 4: TTL 过期后重新加载**
    - **验证: 需求 4.1**

- [x] 6. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

## 阶段 3：清理旧代码

- [x] 7. 清理 WorkflowContext 中的旧缓存逻辑
  - [x] 7.1 修改 `tableau_assistant/src/orchestration/workflow/context.py`
    - 移除 `ensure_metadata_loaded()` 方法
    - 移除 `_load_data_model_from_cache()` 方法
    - 移除 `_ensure_hierarchy_exists()` 方法
    - 移除 `_wait_for_preload()` 方法
    - 移除 `_load_data_model_sync()` 方法
    - 移除 `_with_data_model()` 方法
    - 保留 `MetadataLoadStatus` 类（向后兼容）
    - 保留 `WorkflowContext` 核心功能（auth, store, data_model 属性）
    - _Requirements: 1.1_

- [x] 8. 删除 PreloadService 和 preload API
  - [x] 8.1 删除 `tableau_assistant/src/api/preload_service.py`
    - 删除整个文件
    - _Requirements: 1.1_

  - [x] 8.2 删除 `tableau_assistant/src/api/preload.py`
    - 删除整个文件（不需要向后兼容）
    - _Requirements: 1.1_

  - [x] 8.3 更新引用代码
    - 更新 `tableau_assistant/src/api/__init__.py` 移除 preload_router
    - 更新 `tableau_assistant/src/main.py` 使用 cache_router 替代 preload_router
    - 更新 `tableau_assistant/tests/integration/test_all_backend.py` 测试
    - _Requirements: 1.1_

- [ ] 9. 清理 StoreManager 中的 metadata 相关方法
  - [ ] 9.1 修改 `tableau_assistant/src/infra/storage/store_manager.py`
    - 保留 `get_metadata()` 方法（向后兼容，但标记为废弃）
    - 保留 `put_metadata()` 方法（向后兼容，但标记为废弃）
    - 保留 `clear_metadata_cache()` 方法（向后兼容，但标记为废弃）
    - 保留 `get_dimension_hierarchy()` 方法（向后兼容，但标记为废弃）
    - 保留 `put_dimension_hierarchy()` 方法（向后兼容，但标记为废弃）
    - 保留 `clear_dimension_hierarchy_cache()` 方法（向后兼容，但标记为废弃）
    - 保留其他功能（user_preferences, question_history, anomaly_knowledge 等）
    - _Requirements: 1.1_
    - **注意**: 这些方法暂时保留以确保向后兼容，新代码应使用 DataModelCache

- [x] 10. 更新 storage 模块导出
  - [x] 10.1 修改 `tableau_assistant/src/infra/storage/__init__.py`
    - 添加 `get_langgraph_store`, `reset_langgraph_store` 导出
    - 添加 `DataModelCache`, `DATA_MODEL_NAMESPACE`, `HIERARCHY_NAMESPACE`, `DEFAULT_TTL_MINUTES` 导出
    - 添加 `DataModelLoader`, `TableauDataModelLoader` 导出
    - _Requirements: 1.1_

- [x] 11. Checkpoint - 确保所有测试通过
  - 所有 9 个属性测试通过

## 阶段 4：添加缓存失效 API

- [x] 12. 添加缓存管理 API
  - [x] 12.1 创建 `tableau_assistant/src/api/cache.py`
    - 添加 `POST /api/cache/invalidate` 端点
    - 添加 `GET /api/cache/status/{datasource_luid}` 端点
    - 添加 `POST /api/cache/preload` 端点
    - 接受 `datasource_luid` 参数
    - 调用 `DataModelCache.invalidate()` / `get_or_load()`
    - 返回操作结果
    - _Requirements: 4.2, 4.3_

- [x] 13. Final Checkpoint - 确保所有测试通过
  - 所有 9 个属性测试通过
  - 新的缓存 API 已创建（`/api/cache/*`）
  - 旧的预热 API 已删除（`/api/preload/*`）
