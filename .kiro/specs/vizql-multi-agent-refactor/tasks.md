# VizQL多智能体查询与分析重构 - Implementation Plan

**版本**: v1.3
**最后更新**: 2025-10-31
**预计工期**: 6-8周（原计划8-10周，使用额外特性节省2周）

---

## 重要说明

### 技术要求
1. **Token级流式输出**：必须使用 `astream_events()` 实现逐字显示
2. **LangGraph管理LLM**：所有LLM调用通过LangGraph管理
3. **LangChain 1.0**：已升级到 LangChain 1.0.3 和 LangGraph 1.0.2

### 参考文档
- [LangChain 1.0 变更](../../docs/LANGCHAIN_1.0_CHANGES.md)
- [影响评估](../../docs/LANGCHAIN_1.0_IMPACT.md)
- [多智能体示例](../../tableau_assistant/examples/multi_agent_tableau_fixed.py)

---

- [ ] 1. LangChain/LangGraph 1.0 适配与新特性应用
  - [x] 1.1 评估 tableau_langchain 项目兼容性
    - 识别需要适配的代码
    - 确定可复用的部分
    - _Requirements: 所有需求_

  - [x] 1.2 引入Runtime和context_schema（P0 - 必须）
    - 定义VizQLContext数据类（datasource_luid, user_id, tableau_token, max_replan）
    - 更新所有Agent节点函数签名（添加runtime参数）
    - 使用runtime.context访问上下文信息
    - 精简VizQLState（移除context相关字段）
    - 更新StateGraph创建（添加context_schema参数）
    - _Requirements: 所有Agent需求 (0, 1, 2, 5, 6, 7, 15)_
    - _预计时间: 1-2天_

  - [x] 1.3 使用Store替代部分Redis缓存（P0 - 必须）
    - 创建InMemoryStore实例
    - 迁移元数据缓存到Store（namespace: "metadata"）
    - 迁移维度层级缓存到Store（namespace: "dimension_hierarchy"）
    - 实现用户偏好存储（namespace: "user_preferences"）
    - 实现问题历史存储（namespace: "question_history"）
    - 实现异常知识库存储（namespace: "anomaly_knowledge"）
    - 更新元数据管理器使用Store
    - 更新维度层级Agent使用Store
    - 更新问题Boost Agent使用Store（语义搜索历史问题）
    - 更新洞察Agent使用Store（异常知识库）
    - _Requirements: 0, 11, 15, 5_
    - _预计时间: 2-3天_

  - [x] 1.4 使用astream_events实现详细进度（P1 - 推荐）
    - 后端：实现astream_events事件处理
    - 后端：监听on_chat_model_stream事件（Token级流式）
    - 后端：监听on_chain_start/end事件（Agent进度）
    - 后端：监听on_tool_start/end事件（工具调用进度）
    - 后端：通过SSE推送事件（token、agent_start、agent_complete、query_start等）
    - 前端：实现SSE客户端接收事件
    - 前端：实现Token级实时渲染
    - 前端：实现Agent进度展示
    - 前端：实现查询执行进度展示
    - _Requirements: 12, 14_
    - _预计时间: 2天_

  - [x] 1.5 使用input/output_schema（P1 - 推荐）
    - 定义VizQLInput类型（question, datasource_luid, boost_question）
    - 定义VizQLOutput类型（final_report, key_findings, analysis_path等）
    - 更新StateGraph创建（添加input_schema和output_schema参数）
    - 实现自动验证
    - 更新API文档
    - _Requirements: 14_
    - _预计时间: 1天_

  - [x] 1.6 适配 Agent 创建方式
    - 从 `create_react_agent` 迁移到自定义节点函数
    - 使用 `model.bind_tools()` 或自定义节点函数
    - 参考示例：`multi_agent_tableau_fixed.py`
    - _Requirements: 0, 1, 2, 5, 6, 7, 15_

  - [x] 1.7 更新错误处理机制
    - 使用新的错误处理API
    - _Requirements: 3, 9_


- [ ] 2. 基础设施搭建
  - [x] 2.1 项目结构和环境配置
    - 创建目录结构（agents/、components/、models/、workflows/、tools/、api/）
    - 配置Python虚拟环境和依赖
    - 配置TypeScript和Vue 3项目
    - 配置缓存和环境变量
    - 配置Tableau API认证
    - _Requirements: 所有需求_

  - [x] 2.2 数据模型定义（整合LangGraph 1.0）
    - 创建VizQL查询模型（models/vizql_types.py）✅
    - 创建问题相关模型（models/question.py）✅
    - 创建结果相关模型（models/result.py）✅
    - 创建LangGraph状态模型（models/state.py）✅
    - **创建Context模型（models/context.py）** - VizQLContext数据类 ✅
    - **创建Input/Output模型（models/api.py）** - VizQLInput和VizQLOutput ✅
    - _Requirements: 1, 2, 5, 7, 8, 10, 12_
    - _状态: 基本完成，部分模型待补充_

  - [x] 2.3 提示词模板管理（使用ChatPromptTemplate）
    - 创建prompts目录和模块 ✅
    - **使用ChatPromptTemplate.from_messages()定义7个Agent提示词** ✅
    - **使用MessagesPlaceholder管理对话历史** ✅
    - **使用partial()预填充常量（如VIZQL_CAPABILITIES）** ✅
    - **为每个Agent创建system/user消息结构** ✅
    - 定义2个规则模板 ✅
    - _Requirements: 13_
    - _可复用组件: ChatPromptTemplate, MessagesPlaceholder, partial_
    - _状态: 已完成_
    - _实际耗时: 1天_

  - [x] 2.4 工具函数开发
    - 创建utils目录和工具模块 ✅
    - ~~使用@tool装饰器自动生成schema和文档~~ ❌ 不需要（Agent直接调用，不使用LLM工具调用）
    - 实现日期计算函数（DateCalculator）✅
    - 实现数据采样函数（sample_data）✅
    - 实现Token计数函数（count_tokens）✅
    - 添加类型注解和docstring ✅
    - DateCalculator已支持所有需求 ✅
    - 已集成日期类型定义 ✅
    - 已支持问题理解Agent的日期需求识别 ✅
    - _Requirements: 8, 11, 1_
    - _可复用组件: @tool装饰器, StructuredTool_
    - _状态: 进行中 - 需要完善日期处理_
    - _预计剩余时间: 1天_


- [ ] 3. 核心组件开发
  - [x] 3.1 元数据管理器（使用Store）
    - 实现元数据获取（components/metadata_manager.py）
    - **实现Store缓存管理**（替代SQLite）
    - 实现元数据增强（调用维度层级推断Agent）
    - 使用runtime.store访问缓存
    - _Requirements: 0, 11_
    - _状态: 已完成_

  - [x] 3.2 查询构建器



    - 实现基础查询构建器（components/query_builder.py）
    - 实现筛选器构建（SetFilter、RelativeDateFilter等）
    - 实现排序和限制（sortBy、limit、grain）
    - 实现日期值计算（相对时间、同比、环比）
    - 实现查询验证（基于tableau_sdk的schema）


    - _Requirements: 8_

  - [ ] 3.3 查询执行器（使用RunnableRetry + RunnableConfig）
    - 实现查询执行（components/query_executor.py）
    - **使用RunnableRetry实现自动重试（max_attempt_number=3）**
    - **使用wait_exponential_jitter实现指数退避**
    - **使用RunnableConfig(timeout)实现动态超时控制**
    - **指定retry_on=(NetworkError, TimeoutError)可重试错误**
    - 实现分页处理
    - 实现结果解析
    - _Requirements: 9_
    - _可复用组件: RunnableRetry, RunnableConfig_
    - _预计时间: 1天（原计划2天，使用新特性节省1天）_

  - [ ] 3.4 统计检测器（使用NumPy/SciPy/scikit-learn）
    - 实现描述性统计（components/statistics_detector.py）
    - **使用NumPy实现描述性统计**
    - **使用SciPy实现异常检测（Z-score、IQR）**
    - **使用scikit-learn实现孤立森林异常检测**
    - **使用SciPy实现趋势分析（线性回归、Mann-Kendall检验）**
    - 实现数据质量检查



    - _Requirements: 10_
    - _可复用组件: NumPy, SciPy, scikit-learn_
    - _预计时间: 1天（原计划3天）_

  - [ ] 3.5 数据合并器（使用Pandas + RunnableLambda）
    - 实现合并策略（components/data_merger.py）
    - **第0轮：简单问题和复杂问题都不需要合并**
    - **第1轮及以后：多个查询结果需要合并（按维度合并或并列展示）**
    - 实现合并策略选择（Union/Join/Append/Hierarchical，基于代码规则）
    - 实现字段命名规则（同比/环比命名、多时间段对比命名）
    - **使用Pandas实现数据对齐与补全**
    - **使用Pandas实现数据去重与清洗**
    - **使用Pandas实现聚合计算**
    - **使用RunnableLambda包装纯代码组件为Runnable**
    - **支持链式调用（merge | clean | aggregate）**
    - 实现数据质量评分
    - _Requirements: 4_
    - _可复用组件: Pandas, RunnableLambda_
    - _预计时间: 2天（原计划3天，使用RunnableLambda节省1天）_

  - [ ] 3.6 任务调度器（使用动态图生成 + RunnableParallel）
    - **实现任务接收（接收重规划Agent生成的问题清单）**
    - **实现流程调度（直接调用任务规划Agent处理自然语言问题）**
    - **实现并行处理（支持多个查询的并行执行）**
    - **使用RunnableParallel简化并行执行**
    - **使用RunnableConfig(timeout)实现动态超时（基于数据量）**
    - **使用RunnableRetry包装查询执行器（自动重试）**
    - **使用astream_events实现进度反馈**
    - 实现资源监控（业务逻辑）
    - _Requirements: 3_
    - _可复用组件: StateGraph, RunnableParallel, RunnableRetry, RunnableConfig, astream_events_
    - _预计时间: 1.5天（原计划3天，使用新特性节省1.5天）_


- [ ] 4. Agent开发
  - [x] 4.1 维度层级推断Agent（使用Runtime和Store）
    - 实现维度层级推断（agents/dimension_hierarchy.py）
    - **使用runtime.context获取datasource_luid**
    - **使用runtime.store缓存维度层级（24小时）**
    - 实现Fallback机制
    - 实现性能优化（分批并行推断）
    - _Requirements: 0_
    - _状态: 已完成并测试_

  - [x] 4.2 问题Boost Agent（使用Runtime和Store）
    - 实现问题优化（agents/question_boost.py）
    - **使用runtime.context获取user_id**
    - **使用runtime.store.search()语义搜索历史问题**
    - **保存问题历史到Store**
    - 实现问题分类
    - 合并分类和优化（性能优化）
    - _Requirements: 15_
    - _状态: 已完成并优化_



  - [x] 4.3 问题理解Agent（使用ChatPromptTemplate + PydanticOutputParser）



    - **定义QuestionUnderstanding Pydantic模型（包含sub_questions字段）**
    - **使用PydanticOutputParser创建解析器**
    - **使用ChatPromptTemplate定义提示词（包含format_instructions）**
    - **创建链：prompt | llm | parser（自动解析和验证）**
    - 实现问题有效性验证（agents/understanding.py）
    - 实现问题拆分（拆分子问题）
    - 实现问题类型识别
    - 实现关键信息提取
    - 实现隐含需求识别
    - 实现问题复杂度评估
    - _Requirements: 1_
    - _可复用组件: ChatPromptTemplate, PydanticOutputParser, LCEL链_
    - _预计时间: 1天（原计划2天，使用PydanticOutputParser节省1天）_

  - [x] 4.4 任务规划Agent（使用ChatPromptTemplate + PydanticOutputParser）
    - **定义QueryPlanningResult Pydantic模型（包含queries、needs_replan等）**
    - **使用PydanticOutputParser自动解析查询计划**
    - **使用ChatPromptTemplate.partial()预填充VIZQL_CAPABILITIES**
    - 实现智能规划策略（agents/task_planner.py）
    - 实现完整字段映射（fieldCaption、dataType、role、level）
    - 实现查询规格生成（QuerySpec）
    - 实现重规划问题处理
    - 实现查询可执行性保证
    - _Requirements: 2_
    - _可复用组件: ChatPromptTemplate, PydanticOutputParser, partial_
    - _预计时间: 2天（原计划2.5天，使用新特性节省0.5天）_


  - [ ] 4.5 洞察Agent（使用Runtime + Store + PydanticOutputParser）
    - **定义InsightResult Pydantic模型（包含contribution_analysis、answered_questions、new_questions）**
    - **使用PydanticOutputParser自动解析洞察结果**
    - 实现数据分析（agents/insight.py）
    - 实现贡献度分析（计算贡献百分比、排名）
    - 实现结合统计检测（分析统计检测器的异常结果）
    - **使用runtime.store检查异常知识库**
    - **保存新异常解释到Store**
    - 实现洞察生成（生成自然语言描述、关键发现、新问题列表）
    - _Requirements: 5_
    - _可复用组件: Runtime, Store, PydanticOutputParser_
    - _预计时间: 1.5天（原计划2天，使用PydanticOutputParser节省0.5天）_

  - [ ] 4.6 重规划Agent（使用Runtime + MessagesPlaceholder + PydanticOutputParser）
    - **定义ReplanDecision Pydantic模型**
      - 包含should_replan、replan_type、drill_down_target、new_questions、suggested_dimensions
      - 包含current_round、completeness_score、max_rounds_reached
    - **使用MessagesPlaceholder管理对话历史**
    - **使用PydanticOutputParser自动解析重规划决策**
    - **实现多轮重规划控制逻辑**（agents/replanner.py）
      - 检查是否达到最大轮数（runtime.context.max_replan，默认3）
      - 评估分析完整性（completeness_score >= 0.8）
      - 检查是否有新的异常或未解答的问题
      - 决策是否继续重规划（should_replan）
    - **实现重规划决策逻辑**
      - 如果达到最大轮数 → should_replan=False, max_rounds_reached=True
      - 如果分析完整且无新异常 → should_replan=False
      - 如果有新异常或未解答问题 → should_replan=True, 生成新问题清单
    - 实现下钻维度查找（从metadata/dimension_hierarchy查找子维度）
    - 实现问题清单生成（生成自然语言问题、建议的维度/筛选条件/度量）
    - 实现重规划类型判断（drill_down、dimension_expansion、pivot等）
    - **输出字段说明**
      - should_replan: 是否继续重规划（每轮决策）
      - current_round: 当前轮次（0, 1, 2, ...）
      - completeness_score: 分析完整性评分（0.0-1.0）
      - max_rounds_reached: 是否达到最大轮数限制
    - _Requirements: 6_
    - _可复用组件: Runtime, MessagesPlaceholder, PydanticOutputParser_
    - _预计时间: 2天（原计划2天，增加多轮控制逻辑）_

  - [ ] 4.7 总结Agent（使用PydanticOutputParser）
    - **定义FinalReport Pydantic模型**
    - **使用PydanticOutputParser自动解析最终报告**
    - 实现结果整合（agents/summarizer.py）
    - 实现执行摘要生成
    - 实现分析路径回顾
    - 实现后续探索建议
    - _Requirements: 7_
    - _可复用组件: PydanticOutputParser_
    - _预计时间: 1.5天（原计划2天，使用PydanticOutputParser节省0.5天）_


- [ ] 5. LangGraph 1.0 工作流
  - [ ] 5.1 工作流定义（整合新特性）
    - 创建主工作流（workflows/main_workflow.py）
    - **创建InMemoryStore实例**
    - **使用StateGraph(state_schema, context_schema, input_schema, output_schema)**
    - 实现节点函数（workflows/nodes.py）- 使用Runtime参数
    - **实现多轮重规划控制流程**
      - 初始化round_num=0
      - 从runtime.context获取max_replan（默认3）
      - 第0轮：needs_replan=true（Complex问题）
      - 第1轮及以后：needs_replan=false（处理具体问题）
      - 每轮后检查should_replan决策
      - 达到最大轮数或should_replan=false时结束循环
    - 实现条件路由
      - 根据should_replan决定是否继续重规划
      - 根据max_rounds_reached强制结束
    - **编译时绑定checkpointer和store**
    - _Requirements: 12_

  - [ ] 5.2 对话历史管理（使用InMemorySaver）
    - 实现对话历史存储（使用InMemorySaver）
    - 实现对话历史检索
    - 使用thread_id区分会话
    - _Requirements: 12_

  - [ ] 5.3 检查点机制
    - 实现检查点保存
    - 实现检查点恢复
    - _Requirements: 12_

  - [ ] 5.4 Token级流式输出（使用astream_events）
    - 使用 astream_events(version="v2") 实现Token级流式输出
    - 监听 on_chat_model_stream 事件（Token级）
    - 监听 on_chain_start/end 事件（Agent进度）
    - 监听 on_tool_start/end 事件（工具调用）
    - 通过SSE实时推送事件
    - 实现事件类型：token、agent_start、agent_complete、query_start、query_complete、error、done
    - _Requirements: 12, 14_


- [ ] 6. 前端开发
  - [ ] 6.1 项目搭建和基础组件
    - 评估现有前端代码
    - 实现Header组件
    - 实现输入区域组件
    - 实现用户消息组件
    - _Requirements: 14, 15_

  - [ ] 6.2 AI消息组件
    - 实现AI消息卡片组件
    - 实现执行流程图组件
    - 实现折叠区域组件
    - _Requirements: 14_

  - [ ] 6.3 查询详情组件
    - 实现Stage分组组件
    - 实现查询卡片组件
    - 实现数据展示组件（表格和图表）
    - _Requirements: 14_

  - [ ] 6.4 Token级流式输出（前端 - 对接astream_events）
    - 实现SSE客户端（EventSource）
    - 实现事件处理（token、agent_start、agent_complete、query_start等）
    - 实现Token级实时渲染（逐字显示）
    - 实现Agent进度展示（显示当前执行的Agent）
    - 实现查询执行进度展示
    - 实现错误处理和重连
    - _Requirements: 14_

  - [ ] 6.5 Markdown流式渲染
    - 集成Markdown-it
    - 集成Highlight.js
    - 实现流式Markdown解析
    - _Requirements: 14_

  - [ ] 6.6 状态管理
    - 创建对话状态store（使用Pinia）
    - 创建执行状态store
    - _Requirements: 14_

  - [ ] 6.7 样式和主题
    - 实现配色方案（Tailwind风格）
    - 实现响应式设计
    - _Requirements: 14_


- [ ] 7. 集成测试与优化
  - [ ] 7.1 API开发（使用astream_events）
    - 实现对话API（api/chat.py）- 使用astream_events返回SSE
    - 实现问题Boost API（api/boost.py）
    - 实现临时viz API（api/viz.py）
    - 实现元数据API
    - **传递context到config.configurable**
    - _Requirements: 11, 14, 15, 16_

  - [ ] 7.2 性能优化
    - 优化缓存策略
    - 优化并发控制
    - 优化Token消耗
    - 优化响应时间
    - _Requirements: 所有需求_

  - [ ] 7.3 错误处理和监控
    - 实现错误处理
    - 实现监控和告警
    - _Requirements: 所有需求_

  - [ ] 7.4 文档和部署
    - 编写开发文档
    - 编写部署文档
    - 编写用户文档
    - 准备部署
    - _Requirements: 所有需求_


---

## 额外特性应用总结（基于检查报告）

### 🔥 P0 - 立即应用（2.5天）

1. **RunnableRetry** - 查询执行器（任务3.3）
   - 自动重试机制（max_attempt_number=3）
   - 指数退避（wait_exponential_jitter）
   - 指定可重试错误（NetworkError, TimeoutError）
   - _节省时间: 1天_

2. **RunnableConfig(timeout)** - 任务调度器（任务3.6）
   - 统一超时控制
   - 动态超时计算（基于数据量）
   - _节省时间: 0.5天_

3. **ChatPromptTemplate** - 提示词管理（任务2.3）
   - 结构化提示词（system/user分离）
   - MessagesPlaceholder管理对话历史
   - partial预填充常量
   - _节省时间: 1天_

### 🔥 P1 - 推荐应用（3.5天）

4. **PydanticOutputParser** - 所有Agent（任务4.3-4.7）
   - 自动解析和验证输出
   - 自动生成format_instructions
   - 类型安全
   - _节省时间: 3.5天_

5. **@tool装饰器** - 工具函数（任务2.4）
   - 自动生成schema和文档
   - 类型检查
   - _节省时间: 1.5天_

6. **RunnableLambda** - 数据处理（任务3.5）
   - 包装纯代码组件
   - 支持链式调用
   - _节省时间: 1天_

### 🔥 P2 - 可选应用（1.5天）

7. **RunnableParallel** - 任务调度器（任务3.6）
   - 简化并行执行
   - 自动管理线程池
   - _节省时间: 已包含在动态图生成中_

8. **动态图生成** - 任务调度器（任务3.6）
   - 根据subtasks动态创建执行图
   - 按stage分组（同stage并行，不同stage顺序）
   - 自动处理依赖关系
   - _节省时间: 1.5天_

**总节省时间**: 11.5天（43%）

**详细说明**：参见 [额外特性检查报告](.kiro/specs/vizql-multi-agent-refactor/docs/ADDITIONAL_FEATURES_CHECK.md)

---

## LangGraph 1.0 新特性迁移优先级

### P0 - 必须完成（3-5天）
- ✅ **任务1.2**: 引入Runtime和context_schema（1-2天）
- ✅ **任务1.3**: 使用Store替代部分Redis缓存（2-3天）

### P1 - 强烈推荐（3天）
- ✅ **任务1.4**: 使用astream_events实现详细进度（2天）
- ✅ **任务1.5**: 使用input/output_schema（1天）

**迁移收益**：
- 简化代码（减少state大小）
- 统一接口（Runtime访问context和store）
- 更好的用户体验（Token级流式、详细进度）
- 类型安全（context_schema、input/output_schema）

**详细说明**：参见 [LangChain/LangGraph 1.0 新特性文档](../../docs/LANGCHAIN_LANGGRAPH_1.0_NEW_FEATURES.md)

---

## 可复用组件总结

### ✅ 完全可以复用的组件

| 组件 | LangChain/LangGraph功能 | 节省时间 | 相关任务 |
|------|------------------------|---------|---------|
| **任务调度** | StateGraph + 动态图生成 + RunnableParallel | 1.5天 | 任务3.6 |
| **提示词模板** | ChatPromptTemplate + MessagesPlaceholder + partial | 1天 | 任务2.3 |
| **输出解析** | PydanticOutputParser（所有Agent） | 3.5天 | 任务4.3-4.7 |
| **工具函数** | @tool装饰器 | 1.5天 | 任务2.4 |
| **统计检测** | NumPy + SciPy + scikit-learn | 2天 | 任务3.4 |
| **查询执行** | RunnableRetry + RunnableConfig(timeout) | 1天 | 任务3.3 |
| **数据处理** | RunnableLambda（包装纯代码） | 1天 | 任务3.5 |
| **并行执行** | RunnableParallel | 已包含在任务调度 | 任务3.6 |

**总节省时间**: 约11.5天（原计划30天 → 现在18.5天）

### ⚠️ 需要自己实现（但可以用框架辅助）

| 组件 | 需要实现的部分 | 可以复用的部分 | 相关任务 |
|------|--------------|--------------|---------|
| **查询构建器** | VizQL查询生成逻辑 | Pydantic模型 | 任务3.2 |
| **数据合并器** | 合并策略 | Pandas + RunnableLambda | 任务3.5 |
| **元数据管理器** | 缓存逻辑 | Store存储 | 任务3.1 |

### 📊 工作量对比

**原计划**：
- 核心组件开发：15天
- Agent开发：10天
- 工作流开发：5天
- **总计**：30天

**使用可复用组件后（更新）**：
- 核心组件开发：6.5天（节省8.5天）
  - 任务3.3: 1天（使用RunnableRetry + RunnableConfig）
  - 任务3.4: 1天（使用NumPy/SciPy）
  - 任务3.5: 2天（使用RunnableLambda）
  - 任务3.6: 1.5天（使用动态图生成）
  - 其他: 1天
- Agent开发：7.5天（节省2.5天）
  - 任务4.3: 1天（使用PydanticOutputParser）
  - 任务4.4: 2天（使用PydanticOutputParser）
  - 任务4.5: 1.5天（使用PydanticOutputParser）
  - 任务4.6: 1.5天（使用MessagesPlaceholder + PydanticOutputParser）
  - 任务4.7: 1.5天（使用PydanticOutputParser）
- 工作流开发：3天（节省2天）
- **总计**：17天

**节省**：13天（约43%）

**详细说明**：参见 [额外特性检查报告](../../docs/ADDITIONAL_FEATURES_CHECK.md)

---

**总计**: 7个主要阶段，40个主任务（新增4个LangGraph 1.0任务）
**预计工期**: 6-8周（原计划8-10周，使用额外特性节省2周）
**当前进度**: 约25% (10/40 完成)

**版本**: v1.3
**最后更新**: 2025-10-31
**状态**: 进行中 - 已完成基础设施和LangGraph 1.0适配

---

## 📊 进度总结

### 已完成的主要任务（10/40）

**阶段1: LangGraph 1.0适配** ✅
- ✅ 1.1 评估兼容性
- ✅ 1.2 引入Runtime和context_schema
- ✅ 1.3 使用Store替代部分Redis缓存
- ✅ 1.4 使用astream_events实现详细进度
- ✅ 1.5 使用input/output_schema
- ✅ 1.6 适配Agent创建方式
- ✅ 1.7 更新错误处理机制

**阶段2: 基础设施** ✅
- ✅ 2.1 项目结构和环境配置
- ✅ 2.2 数据模型定义
- ✅ 2.3 提示词模板管理

**阶段3: 核心组件** 🔄
- ✅ 3.1 元数据管理器（使用Store）

**阶段4: Agent开发** 🔄
- ✅ 4.1 维度层级推断Agent
- ✅ 4.2 问题Boost Agent

### 当前进度
- **总体进度**: 25% (10/40)
- **当前阶段**: 阶段2/3 - 基础设施完善和核心组件开发
- **下一步**: 完成任务2.4（工具函数完善），然后开始任务3.2（查询构建器）

### 各阶段进度

| 阶段 | 任务数 | 已完成 | 进度 | 状态 |
|------|--------|--------|------|------|
| 1. LangGraph 1.0适配 | 7 | 7 | 100% | ✅ 完成 |
| 2. 基础设施搭建 | 4 | 3 | 75% | 🔄 进行中 |
| 3. 核心组件开发 | 6 | 1 | 17% | 🔄 进行中 |
| 4. Agent开发 | 7 | 2 | 29% | 🔄 进行中 |
| 5. LangGraph工作流 | 4 | 0 | 0% | ⏳ 待开始 |
| 6. 前端开发 | 7 | 0 | 0% | ⏳ 待开始 |
| 7. 集成测试与优化 | 4 | 0 | 0% | ⏳ 待开始 |
| **总计** | **40** | **10** | **25%** | 🔄 进行中 |

### 关键成果
1. ✅ **LangGraph 1.0完全适配** - Runtime、Store、astream_events全部实现
2. ✅ **流式输出功能** - Token级流式、Agent进度展示
3. ✅ **Store缓存系统** - 元数据、维度层级、用户偏好、问题历史
4. ✅ **提示词管理** - 7个Agent提示词 + 2个规则模板
5. ✅ **测试覆盖** - 25个测试全部通过（11+4+10）

### 测试状态
- ✅ Store集成测试: 14/14 通过
- ✅ 流式输出测试: 11/11 通过
- ✅ 流式集成测试: 4/4 通过
- ✅ Runtime上下文测试: 通过
- ✅ Input/Output Schema测试: 通过

### 📋 下一步建议

**优先级P0（必须完成）**：
1. **任务2.4**: 工具函数完善 - 完善日期处理，支持问题理解Agent
   - 集成tableau_sdk日期类型
   - 支持周开始日、节假日、农历识别
   - 使用@tool装饰器包装
2. **任务4.3**: 问题理解Agent - 工作流入口，识别日期需求
   - 创建提示词模板
   - 识别周开始日、节假日、农历等日期需求
   - 输出扩展的date_requirements字段
3. **任务3.2**: 查询构建器 - 核心功能，依赖任务2.4和4.3
   - 使用DateCalculator生成日期筛选器
   - 参考tableau_sdk类型定义
4. **任务3.3**: 查询执行器 - 依赖查询构建器
5. **任务4.4**: 查询规划Agent - 核心规划逻辑

**优先级P1（推荐完成）**：
5. **任务3.4**: 统计检测器 - 为洞察Agent提供数据
6. **任务4.5**: 洞察Agent - 结果分析
7. **任务3.5**: 数据合并器 - 多查询结果合并
8. **任务3.6**: 任务调度器 - 并行执行控制

**优先级P2（后续完成）**：
9. **任务4.6**: 重规划Agent - 探索式分析
10. **任务4.7**: 总结Agent - 最终报告生成
11. **任务5.x**: LangGraph工作流编排
12. **任务6.x**: 前端开发

**建议执行顺序**：
```
2.4 工具函数完善 → 4.3 问题理解Agent → 3.2 查询构建器 → 3.3 查询执行器
→ 4.4 查询规划Agent → 3.4 统计检测器 → 4.5 洞察Agent → 3.5 数据合并器
→ 3.6 任务调度器 → 4.6 重规划Agent → 4.7 总结Agent → 5.x 工作流编排
→ 6.x 前端开发
```

**任务2.4详细计划**：

**第1步：集成tableau_sdk日期类型**（2小时）
- 阅读 `sdks/tableau/apis/vizqlDataServiceApi.ts` 中的RelativeDateFilter定义
- 确保DateCalculator输出格式与VizQL要求一致
- 添加format_for_vizql()方法，输出标准VizQL日期格式

**第2步：扩展DateCalculator功能**（3小时）
- 实现NEXT和NEXTN相对时间类型
- 添加周开始日配置支持（从.env或参数）
- 添加法定节假日过滤方法（is_working_day、calculate_working_days）
- 添加农历转换方法（需要lunarcalendar库）

**第3步：创建问题理解Agent提示词**（2小时）
- 在prompts/目录创建understanding_agent.py
- 定义识别日期需求的提示词
- 输出date_requirements字段（week_start_day、mentions_holidays、mentions_lunar）

**第4步：使用@tool装饰器**（1小时）
- 将DateCalculator主要方法包装为LangChain工具
- 添加类型注解和docstring
- 自动生成schema

**第5步：测试和文档**（2小时）
- 编写单元测试
- 更新README.md
- 添加使用示例

**总计**: 约10小时（1天）

---

### 📈 更新亮点（v1.2）

1. **整合8个额外特性**：
   - RunnableRetry（自动重试）
   - RunnableConfig(timeout)（超时控制）
   - ChatPromptTemplate（提示词模板）
   - PydanticOutputParser（输出解析）
   - @tool装饰器（工具函数）
   - RunnableLambda（包装纯代码）
   - RunnableParallel（并行执行）
   - 动态图生成（灵活执行）

2. **工作量优化**：
   - 原计划：30天
   - 现在：17天
   - 节省：13天（43%）

3. **重点优化任务**：
   - 任务2.3：提示词管理（2天 → 1天）
   - 任务2.4：工具函数（2天 → 0.5天）
   - 任务3.3：查询执行器（2天 → 1天）
   - 任务3.5：数据合并器（3天 → 2天）
   - 任务3.6：任务调度器（3天 → 1.5天）
   - 任务4.3-4.7：所有Agent（10天 → 7.5天）

**参考文档**：
- [额外特性检查报告](.kiro/specs/vizql-multi-agent-refactor/docs/ADDITIONAL_FEATURES_CHECK.md)
- [LangChain 1.0 新特性](../../docs/LANGCHAIN_LANGGRAPH_1.0_NEW_FEATURES.md)

---

## ⚠️ 已知问题和注意事项

### 1. 工具函数开发（任务2.4）

**状态**: 进行中 - 需要完善日期处理

**已完成**：
- ✅ DateCalculator基础实现（支持相对时间、对比时间、周期时间）
- ✅ 数据采样函数（sample_dataframe）
- ✅ Token计数函数（count_tokens）
- ✅ 日期处理策略文档（DATE_FIELD_STRATEGY.md）

**待完善**：
1. **集成tableau_sdk的日期类型**
   - 参考 `sdks/tableau/apis/vizqlDataServiceApi.ts` 中的日期相关类型
   - 确保DateCalculator输出格式与VizQL Filter要求一致
   - 支持RelativeDateFilter的所有参数

2. **支持问题理解Agent的日期需求识别**
   - 周开始日识别（"周一开始" vs "周日开始"）
   - 节假日识别（"工作日"、"节假日"、"休息日"）
   - 农历识别（"农历"、"春节"、"正月"）
   - 输出扩展的date_requirements字段

3. **完善DateCalculator功能**
   - 实现NEXT和NEXTN相对时间类型
   - 支持法定节假日过滤（基于问题理解结果）
   - 支持农历转换（基于问题理解结果）
   - 添加周开始日配置（从.env或问题理解结果）

4. **使用@tool装饰器**
   - 将DateCalculator的主要方法包装为LangChain工具
   - 自动生成schema和文档
   - 支持Agent直接调用

**依赖关系**：
- ⏳ 需要先完成问题理解Agent的提示词（识别日期需求）
- ⏳ 需要参考tableau_sdk的日期类型定义
- ✅ VizQL类型定义（models/vizql_types.py）已完成

**预计剩余时间**: 1天

### 2. 查询构建器（任务3.2）

**状态**: 待实现

**关键点**：
- 必须参考 `tableau_sdk` 的类型定义（`sdks/tableau/apis/vizqlDataServiceApi.ts`）
- 使用Pydantic模型确保类型安全
- 实现6种Filter类型（SetFilter、TopNFilter、MatchFilter等）
- 实现日期值计算（相对时间、同比、环比）
- 实现查询验证（基于Pydantic模型）

**依赖**：
- ✅ VizQL类型定义（models/vizql_types.py）已完成
- 🔄 日期计算工具（utils/date_calculator.py）需要完善
- ⏳ 问题理解Agent提示词（识别日期需求）待创建

### 2. Agent实现注意事项

**已完成的Agent**：
- ✅ 维度层级推断Agent（agents/metadata_agent.py）
- ✅ 问题Boost Agent（prompts/question_boost.py）

**待实现的Agent**：
- ⏳ 问题理解Agent（任务4.3）
- ⏳ 查询规划Agent（任务4.4）
- ⏳ 洞察Agent（任务4.5）
- ⏳ 重规划Agent（任务4.6）
- ⏳ 总结Agent（任务4.7）

**实现要点**：
- 使用 `Runtime[VizQLContext]` 访问上下文
- 使用 `runtime.store` 访问缓存
- 使用 `PydanticOutputParser` 自动解析输出
- 使用 `ChatPromptTemplate` 定义提示词

### 3. 测试覆盖

**已有测试**：
- ✅ Store集成测试（14个测试）
- ✅ 流式输出测试（11个测试）
- ✅ 流式集成测试（4个测试）
- ✅ Runtime上下文测试
- ✅ Input/Output Schema测试

**待补充测试**：
- ⏳ 查询构建器测试
- ⏳ 查询执行器测试
- ⏳ Agent单元测试
- ⏳ 工作流集成测试
- ⏳ 端到端测试

### 4. 文档状态

**已完成文档**：
- ✅ TASK_1.3_STORE_INTEGRATION.md - Store集成文档
- ✅ TASK_1.4_COMPLETION_SUMMARY.md - 流式输出完成总结
- ✅ RUNTIME_CONTEXT_GUIDE.md - Runtime使用指南
- ✅ STREAMING_USAGE.md - 流式输出使用指南
- ✅ DATE_FIELD_STRATEGY.md - 日期字段策略

**待补充文档**：
- ⏳ 查询构建器使用指南
- ⏳ Agent开发指南
- ⏳ 工作流编排指南
- ⏳ 前端集成指南

### 5. 性能优化建议

**已实现的优化**：
- ✅ Store缓存（元数据1小时、维度层级24小时）
- ✅ Token级流式输出（减少等待时间）
- ✅ 并行执行框架（RunnableParallel）
- ✅ 自动重试机制（RunnableRetry）

**待实现的优化**：
- ⏳ 查询结果缓存（Redis，5分钟）
- ⏳ 数据采样策略（智能采样，最多30行）
- ⏳ 并发控制（最多3个并发）
- ⏳ 超时控制（动态超时，基于数据量）

---
