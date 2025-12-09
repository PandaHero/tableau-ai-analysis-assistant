# Implementation Plan

## Part 1: 维度层级推断性能优化

- [ ] 1. 实现缓存机制
  - [x] 1.1 添加缓存数据结构和方法


    - 在 `dimension_hierarchy/node.py` 中添加 `HierarchyCacheEntry` 数据类
    - 实现 `_get_cache_namespace()`, `_compute_field_hash()` 方法
    - 实现 `_get_from_cache()`, `_put_to_cache()` 方法
    - 使用 StoreManager 进行持久化
    - _Requirements: 1.1, 1.2_


  - [x] 1.2 集成缓存到主流程

    - 修改 `dimension_hierarchy_node()` 函数
    - 在推断前检查缓存
    - 缓存有效且 field_hash 相同时直接返回
    - 推断完成后更新缓存
    - _Requirements: 1.1, 1.2_

  - [ ] 1.3 写属性测试：缓存 Round-Trip 一致性
    - **Property 1: 缓存 Round-Trip 一致性**
    - **Validates: Requirements 1.1, 1.2**

- [ ] 2. 实现增量推断
  - [x] 2.1 添加增量推断逻辑


    - 实现 `_compute_incremental_fields()` 方法
    - 计算新增字段 = 当前字段 - 缓存字段
    - 计算删除字段 = 缓存字段 - 当前字段
    - _Requirements: 1.3_


  - [x] 2.2 实现增量推断流程

    - 修改 `dimension_hierarchy_node()` 支持增量推断
    - 仅对新增字段调用 LLM
    - 合并新推断结果与缓存结果
    - 删除已删除字段
    - _Requirements: 1.3, 1.4_

  - [ ] 2.3 写属性测试：增量推断完整性
    - **Property 2: 增量推断完整性**
    - **Validates: Requirements 1.3, 1.4**

- [ ] 3. 实现缓存过期检测
  - [x] 3.1 添加过期检测逻辑

    - 在 `HierarchyCacheEntry` 中添加 `is_expired` 属性
    - 默认 TTL 为 7 天
    - 过期时触发重新推断
    - _Requirements: 1.5_

  - [ ] 3.2 写属性测试：缓存过期检测
    - **Property 3: 缓存过期检测**
    - **Validates: Requirements 1.5**

- [ ] 4. 实现分批推断优化
  - [x] 4.1 添加分批推断逻辑


    - 实现 `_batch_inference()` 方法
    - 将字段分成每批 5 个
    - 每批独立调用 LLM
    - 合并所有批次结果
    - _Requirements: 1.6_

  - [x] 4.2 集成分批推断到首次推断流程






    - 首次推断时使用分批推断
    - 增量推断时直接推断（字段数少）
    - _Requirements: 1.6_

- [x] 5. Checkpoint - 确保所有测试通过




  - 运行 `pytest tableau_assistant/tests/` 确保测试通过
  - 运行 E2E 测试验证性能优化效果

## Part 2: FieldMapper 架构重构

- [x] 6. 创建 agents/field_mapper 目录结构
  - [x] 6.1 创建目录和 __init__.py

    - 创建 `agents/field_mapper/` 目录
    - 创建 `__init__.py` 导出 `field_mapper_node`, `FieldMapperNode`
    - _Requirements: 2.2_


  - [x] 6.2 创建 prompt.py
    - 创建 `FieldMapperPrompt` 类（继承 VizQLPrompt）
    - 实现 `get_role()`, `get_task()`, `get_specific_domain_knowledge()`
    - 实现 `get_constraints()`, `get_user_template()`, `get_output_model()`
    - _Requirements: 2.2, 3.1_


- [x] 7. 迁移核心代码
  - [x] 7.1 迁移 llm_selector.py
    - 复制 `nodes/field_mapper/llm_selector.py` 到 `agents/field_mapper/`
    - 更新 import 路径
    - 使用新的 `FieldMapperPrompt` 替换硬编码 prompt

    - _Requirements: 2.3_

  - [x] 7.2 迁移 node.py
    - 复制 `nodes/field_mapper/node.py` 到 `agents/field_mapper/`
    - 更新 import 路径

    - 保持原有的 RAG + LLM 混合策略
    - _Requirements: 2.1, 2.3_

  - [x] 7.3 合并 hierarchy_inferrer.py 到 dimension_hierarchy agent
    - `hierarchy_inferrer.py` 是单字段维度层级推断器
    - 将其功能合并到 `agents/dimension_hierarchy/node.py`
    - 添加 `infer_single_field()` 方法支持单字段推断
    - FieldMapper 改为调用 `dimension_hierarchy` agent

    - 保留旧文件以兼容（通过 nodes/field_mapper/__init__.py 重导出）
    - _Requirements: 2.3, 3.4_

- [x] 8. 更新引用


  - [x] 8.1 更新所有 import 语句
    - 搜索所有引用 `nodes.field_mapper` 的文件
    - 更新为 `agents.field_mapper`
    - _Requirements: 2.4_

  - [x] 8.2 更新测试文件
    - 更新测试文件中的 import 路径
    - 确保测试仍然通过
    - _Requirements: 2.4_

- [x] 9. 删除旧目录
  - [x] 9.1 删除 nodes/field_mapper 目录
    - 已删除 `nodes/field_mapper/` 目录
    - `hierarchy_inferrer.py` 功能已合并到 `dimension_hierarchy/node.py` 的 `infer_single_field()`
    - _Requirements: 2.5_

- [ ] 10. 写属性测试：功能等价性
  - **Property 4: FieldMapper 功能等价性**
  - **Validates: Requirements 2.3**

- [ ] 11. Final Checkpoint - 确保所有测试通过
  - 运行 `pytest tableau_assistant/tests/` 确保测试通过
  - 运行 E2E 测试验证重构后功能正常
