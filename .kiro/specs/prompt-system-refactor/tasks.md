# 实施计划

- [x] 1. 创建基础 Prompt 架构



  - 创建 `tableau_assistant/prompts/base.py`，包含 BasePrompt 和 VizQLPrompt 类
  - 在 `format_messages()` 中实现自动 JSON Schema 注入
  - 添加 `get_schema_instruction()` 方法，支持自定义 Schema 说明
  - _需求: 5.1, 5.2_




- [x] 2. 创建基础 Agent 架构

  - 创建 `tableau_assistant/src/agents/base_v2.py`，包含 BaseVizQLAgent 类
  - 实现统一的 `execute()` 方法，支持流式输出
  - 添加 `_prepare_input_data()` 和 `_process_result()` 模板方法
  - _需求: 5.1, 5.2_

- [x] 3. 重构 Question Boost Prompt


  - 创建 `tableau_assistant/prompts/question_boost_v2.py`，包含 QuestionBoostPrompt 类
  - 实现简洁的、基于原则的系统消息（无硬编码规则）
  - 专注于业务术语，避免使用技术字段名
  - 删除冗余示例，只保留 1-2 个代表性示例
  - _需求: 5.3, 7.1, 7.4_

- [x] 4. 重构 Understanding Prompt


  - 创建 `tableau_assistant/prompts/understanding_v2.py`，包含 UnderstandingPrompt 类
  - 简化 VizQL 能力描述（使用原则，而非详细规则）
  - 添加清晰的子问题关系标注要求
  - 专注于业务术语，移除字段映射逻辑
  - 通过覆盖 `format_messages()` 注入 VizQL 上下文
  - _需求: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.4, 7.2, 7.5_







- [x] 5. 重构 Task Planner Prompt


  - 创建 `tableau_assistant/prompts/task_planner_v2.py`，包含 TaskPlannerPrompt 类
  - 添加语义匹配原则（字段名相似度、类别对齐、sample_values 相关性）
  - 添加粒度选择指导（使用 dimension_hierarchy 的 level 和 unique_count）
  - 添加度量选择原则（基于意图、语义、上下文）
  - 保留字段类型约束（BasicField、FunctionField、CalculationField）


  - 通过覆盖 `format_messages()` 注入 VizQL 上下文和元数据
  - _需求: 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.3, 7.6_

- [x] 6. 更新 Question Boost Agent



  - 更新 `tableau_assistant/src/agents/question_boost_agent.py` 使用 BaseVizQLAgent

  - 实现 `_prepare_input_data()` 格式化问题和元数据
  - 实现 `_process_result()` 包装 QuestionBoost 结果
  - 更新 agent node 函数使用新的 agent 类
  - _需求: 2.1, 5.3_

- [x] 7. 更新 Understanding Agent

  - 更新 `tableau_assistant/src/agents/understanding_agent.py` 使用 BaseVizQLAgent

  - 实现 `_prepare_input_data()` 格式化问题和元数据
  - 实现 `_process_result()` 包装 QuestionUnderstanding 结果
  - 添加 sub_question_relationships 验证
  - 更新 agent node 函数使用新的 agent 类
  - _需求: 2.2, 3.1, 4.1, 5.4_





- [ ] 8. 更新 Task Planner Agent


  - 更新 `tableau_assistant/src/agents/task_planner_agent.py` 使用 BaseVizQLAgent
  - 实现 `_prepare_input_data()` 格式化 understanding、metadata 和 dimension_hierarchy
  - 实现 `_process_result()` 包装 QueryPlanningResult 结果
  - 添加字段名对元数据的验证
  - 更新 agent node 函数使用新的 agent 类
  - _需求: 2.3, 5.5, 6.1_


- [ ] 9. 实现元数据预加载
  - 更新 `tableau_assistant/tests/test_boost_understanding_planning.py` 预加载元数据
  - 将 metadata 和 dimension_hierarchy 加载移到问题处理之前
  - 使用预加载的 metadata 和 dimension_hierarchy 初始化状态
  - 从各个 agent 调用中移除冗余的元数据加载

  - _需求: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2_

- [ ] 10. 添加验证工具
  - 创建 `tableau_assistant/src/utils/validation.py`，包含验证函数
  - 实现 `validate_understanding()` 进行业务逻辑验证
  - 实现 `validate_query_plan()` 进行字段名验证
  - 实现 `validate_relationships()` 进行子问题关系验证


  - _需求: 2.4, 2.5, 2.6, 4.1, 8.3, 8.4, 8.5_

- [ ] 11. 更新测试套件
  - 更新现有测试使用新的 prompt 和 agent 类
  - 添加自动 Schema 注入的测试
  - 添加子问题关系验证的测试
  - 添加字段映射验证的测试（业务术语 → 技术字段）
  - 验证所有测试在新架构下通过
  - _需求: 8.3, 8.4, 8.5_

- [ ] 12. 文档和清理
  - 更新 README 或文档以反映新架构
  - 为新的基类添加内联文档
  - 移除或废弃旧的 prompt 文件
  - 添加未来 prompt 更新的迁移指南
  - _需求: All_
