# Implementation Plan

## Phase 1: 核心架构基础

- [ ] 1. 搭建工作流框架
  - [ ] 1.1 实现 `create_tableau_workflow()` 工厂函数
    - 创建 StateGraph 并配置 7 个中间件
    - 支持配置字典自定义参数
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [ ] 1.2 定义 VizQLState 数据模型
    - 使用 TypedDict 定义状态结构
    - 实现状态累积逻辑（Annotated[list, operator.add]）
    - _Requirements: 18.1, 18.2_
  - [ ]* 1.3 编写 Property Test：中间件配置完整性
    - **Property 1: 中间件配置完整性**
    - **Validates: Requirements 1.1, 1.2**

- [ ] 2. 实现自定义中间件
  - [ ] 2.1 实现 FilesystemMiddleware
    - 大结果自动转存（>20000 tokens）
    - 提供 read_file、write_file 工具
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_
  - [ ] 2.2 实现 PatchToolCallsMiddleware
    - 修复悬空工具调用
    - _Requirements: 13.1, 13.2, 13.3, 13.4_
  - [ ]* 2.3 编写 Property Test：大输出文件转存
    - **Property 7: 大输出文件转存**
    - **Validates: Requirements 3.5, 12.1**
  - [ ]* 2.4 编写 Property Test：悬空工具调用修复
    - **Property 19: 悬空工具调用修复**
    - **Validates: Requirements 13.1**


- [ ] 3. 实现 StateGraph 工作流编排
  - [ ] 3.1 创建 StateGraph 并添加 6 个节点
    - Boost、Understanding、QueryBuilder、Execute、Insight、Replanner
    - _Requirements: 2.1_
  - [ ] 3.2 实现条件边和路由逻辑
    - boost_question 条件跳过
    - 智能重规划路由：
      - should_replan=True → Understanding（重新理解新问题）
      - should_replan=False → END（结束分析）
    - _Requirements: 2.3, 2.4, 2.5, 17.4, 17.5, 17.6, 17.7_
  - [ ]* 3.3 编写 Property Test：工作流节点顺序
    - **Property 2: 工作流节点顺序保持**
    - **Validates: Requirements 2.2**
  - [ ]* 3.4 编写 Property Test：Boost 节点条件跳过
    - **Property 3: Boost 节点条件跳过**
    - **Validates: Requirements 2.3**
  - [ ]* 3.5 编写 Property Test：智能重规划路由正确性
    - **Property 4: 智能重规划路由正确性**
    - **Validates: Requirements 2.4, 17.4, 17.5**

- [ ] 4. 实现工具系统基础
  - [ ] 4.1 创建 ToolRegistry 工具注册表
    - 按节点分组工具
    - 支持依赖注入和动态更新
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_
  - [ ] 4.2 定义工具基础结构
    - 使用 @tool 装饰器和 Pydantic 输入验证
    - 实现结构化错误响应
    - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [ ]* 4.3 编写 Property Test：工具输入验证
    - **Property 6: 工具输入验证**
    - **Validates: Requirements 3.2, 3.3**

- [ ] 5. 实现错误处理与分类
  - [ ] 5.1 定义错误类型
    - TransientError、PermanentError、UserError
    - _Requirements: 21.1_
  - [ ] 5.2 实现错误分类和处理逻辑
    - 瞬态错误触发重试
    - 永久性错误立即终止
    - 用户错误返回友好消息
    - _Requirements: 21.2, 21.3, 21.4, 21.5_
  - [ ]* 5.3 编写 Property Test：错误分类正确性
    - **Property 20: 错误分类正确性**
    - **Validates: Requirements 21.1**

- [ ] 6. Checkpoint - Phase 1 完成
  - 确保所有测试通过，如有问题请询问用户。


## Phase 2: 核心工具实现

- [ ] 7. 实现 RAG 语义字段映射
  - [ ] 7.1 实现 semantic_map_fields 方法
    - RAG + LLM 混合模式
    - 快速路径（置信度 > 0.9 跳过 LLM）
    - 低置信度返回 top-3 备选项
    - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - [ ] 7.2 实现缓存和批量处理
    - SQLite 缓存，TTL 1 小时
    - asyncio 并发处理（最多 5 个）
    - _Requirements: 4.5, 4.6_
  - [ ] 7.3 实现维度层级信息支持
    - 字段索引包含 category、level、granularity
    - _Requirements: 4.7, 4.8_
  - [ ]* 7.4 编写 Property Test：RAG 高置信度快速路径
    - **Property 8: RAG 高置信度快速路径**
    - **Validates: Requirements 4.3**
  - [ ]* 7.5 编写 Property Test：RAG 低置信度备选返回
    - **Property 9: RAG 低置信度备选返回**
    - **Validates: Requirements 4.4**
  - [ ]* 7.6 编写 Property Test：字段映射缓存一致性
    - **Property 10: 字段映射缓存一致性**
    - **Validates: Requirements 4.5**

- [ ] 8. 实现维度层级 RAG 增强
  - [ ] 8.1 实现 HierarchyInferrer
    - 检索历史模式（相似度 > 0.8）
    - few-shot 示例构建
    - 推断成功后存储新模式
    - _Requirements: 4.1.1, 4.1.2, 4.1.3, 4.1.5_
  - [ ] 8.2 定义 DimensionPattern 索引 schema
    - 包含字段名、数据类型、样本值、唯一值数量、category/level
    - _Requirements: 4.1.4_
  - [ ]* 8.3 编写 Property Test：维度层级 RAG 增强
    - **Property 11: 维度层级 RAG 增强**
    - **Validates: Requirements 4.1.1, 4.1.2**

- [ ] 9. 实现元数据工具
  - [ ] 9.1 实现 get_metadata 工具
    - 薄封装 MetadataManager
    - 支持 filter_role、filter_category 参数
    - 返回全量字段，大结果由 FilesystemMiddleware 处理
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - [ ]* 9.2 编写 Property Test：元数据工具委托
    - **Property 12: 元数据工具委托**
    - **Validates: Requirements 5.1, 5.3**

- [ ] 10. 实现日期处理工具
  - [ ] 10.1 实现 parse_date 工具
    - 薄封装 DateManager
    - 支持相对/绝对日期表达式
    - 失败返回 null + 错误消息
    - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - [ ] 10.2 实现 detect_date_format 工具
    - 返回格式类型和转换建议
    - _Requirements: 6.5, 6.6_
  - [ ]* 10.3 编写 Property Test：日期解析往返一致性
    - **Property 13: 日期解析往返一致性**
    - **Validates: Requirements 6.2, 6.3**

- [ ] 11. Checkpoint - Phase 2 完成
  - 确保所有测试通过，如有问题请询问用户。


## Phase 3: 纯语义中间层实现

- [ ] 12. 实现 SemanticQuery 数据模型
  - [ ] 12.1 定义 AnalysisType 枚举
    - Phase 1: cumulative、moving、ranking、percentage、period_compare
    - Phase 2: difference、percent_difference、ranking_dense、ranking_percentile
    - Phase 3: position
    - _Requirements: 7.2.15, 7.2.16, 7.2.17_
  - [ ] 12.2 定义 AnalysisSpec 模型
    - 使用 XML 格式的字段描述
    - 实现决策树和填写顺序
    - 实现 model_validator 验证依赖关系
    - _Requirements: 7.2.1, 7.2.2_
  - [ ] 12.3 定义 SemanticQuery 模型
    - measures、dimensions、filters、analyses、output_control
    - _Requirements: 7.2.1_
  - [ ]* 12.4 编写 Property Test：SemanticQuery computation_scope 条件填写
    - **Property 23: SemanticQuery computation_scope 条件填写**
    - **Validates: Requirements 7.2.3, 7.2.11**

- [ ] 13. 实现 QueryBuilder Node
  - [ ] 13.1 实现 FieldMapper 组件
    - RAG + LLM 混合字段映射
    - 置信度 > 0.9 直接返回
    - 置信度 < 0.9 使用 LLM 判断
    - _Requirements: 7.2.5, 7.2.6, 7.2.7_
  - [ ] 13.2 实现 ImplementationResolver 组件
    - 代码规则 + LLM fallback
    - LOD 判断逻辑（requires_external_dimension、target_granularity）
    - addressing 推导逻辑（单维度/多维度场景）
    - _Requirements: 7.2.8, 7.2.9, 7.2.10, 7.2.11_
  - [ ] 13.3 实现 ExpressionGenerator 组件
    - 表计算模板（RUNNING_SUM、RANK、WINDOW_AVG 等）
    - LOD 模板（{FIXED ...}、{INCLUDE ...}、{EXCLUDE ...}）
    - 确保 100% 语法正确
    - _Requirements: 7.2.12, 7.2.13, 7.2.14_
  - [ ]* 13.4 编写 Property Test：ImplementationResolver LOD 判断
    - **Property 21: ImplementationResolver LOD 判断**
    - **Validates: Requirements 7.2.8, 7.2.9**
  - [ ]* 13.5 编写 Property Test：ExpressionGenerator 语法正确性
    - **Property 22: ExpressionGenerator 表达式语法正确性**
    - **Validates: Requirements 7.2.14**

- [ ] 14. 实现表计算和 LOD 支持
  - [ ] 14.1 实现 TableCalcIntent → TableCalcField 转换
    - 支持 RUNNING_TOTAL、RANK、MOVING_CALCULATION、PERCENT_OF_TOTAL 等
    - 正确设置 tableCalculation.dimensions
    - _Requirements: 7.1.1, 7.1.2, 7.1.3, 7.1.4_
  - [ ] 14.2 实现 LODIntent → CalculatedField 转换
    - 支持 FIXED、INCLUDE、EXCLUDE
    - 生成正确的 LOD 语法
    - _Requirements: 7.1.5, 7.1.6, 7.1.7, 7.1.8_
  - [ ] 14.3 实现错误处理
    - 参数无效时返回清晰错误消息
    - 字段不存在时抛出 ValueError
    - _Requirements: 7.1.9, 7.1.10_
  - [ ]* 14.4 编写 Property Test：查询构建正确性
    - **Property 14: 查询构建正确性**
    - **Validates: Requirements 7.1**

- [ ] 15. Checkpoint - Phase 3 完成
  - 确保所有测试通过，如有问题请询问用户。


## Phase 4: Agent 节点实现

- [ ] 16. 实现 Boost Agent
  - [ ] 16.1 实现 Boost Node
    - 使用 get_metadata 工具获取字段信息
    - 输出 boosted_question
    - _Requirements: 2.1_

- [ ] 17. 实现 Understanding Agent
  - [ ] 17.1 实现 Understanding Node
    - 使用 get_schema_module、parse_date、detect_date_format 工具
    - 输出 SemanticQuery（纯语义，无 VizQL 概念）
    - _Requirements: 7.2.1, 7.2.2, 7.2.3, 7.2.4_
  - [ ] 17.2 实现 get_schema_module 工具
    - 动态 Schema 模块选择
    - 减少 token 消耗 40-60%
    - _Requirements: design-appendix-schema-tool.md_
  - [ ] 17.3 实现 Understanding Prompt
    - 4 段式结构（Role、Task、Domain Knowledge、Constraints）
    - 包含分析类型关键词映射表
    - 包含 computation_scope 判断规则
    - _Requirements: 7.2.18, 7.2.19, 7.2.20_
  - [ ]* 17.4 编写 Property Test：Schema 模块按需加载
    - **Property 24: Schema 模块按需加载**
    - **Validates: design-appendix-schema-tool.md**
  - [ ]* 17.5 编写 Property Test：Schema 模块名称验证
    - **Property 25: Schema 模块名称验证**
    - **Validates: design-appendix-schema-tool.md**

- [ ] 18. 实现 Execute Node
  - [ ] 18.1 实现 Execute Node
    - 调用 VizQL Data Service /query-datasource API
    - 返回 QueryResult 或结构化错误
    - 大结果由 FilesystemMiddleware 处理
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 19. 实现 Insight Agent
  - [ ] 19.1 实现 AnalysisCoordinator
    - 选择分析策略（direct/progressive/hybrid）
    - 编排分析流程
    - _Requirements: 8.1, 8.2_
  - [ ] 19.2 实现 DataProfiler 组件
    - 生成数据画像（row_count、density、statistics）
    - 包含统计信息（均值、中位数、标准差、分位数）
    - _Requirements: 8.1_
  - [ ] 19.3 实现 AnomalyDetector 组件
    - 检测离群值、异常比例、异常详情
    - _Requirements: 8.1_
  - [ ] 19.4 实现 SemanticChunker 组件
    - 按业务逻辑分块（时间 > 类别 > 地理）
    - _Requirements: 8.3_
  - [ ] 19.5 实现 ChunkAnalyzer 组件
    - 传递之前洞察摘要避免重复发现
    - _Requirements: 8.4_
  - [ ] 19.6 实现 InsightAccumulator 组件
    - 检查重复、合并相似洞察、按优先级排序
    - _Requirements: 8.5_
  - [ ] 19.7 实现 InsightSynthesizer 组件
    - 合成最终 InsightResult
    - _Requirements: 8.6_
  - [ ]* 19.8 编写 Property Test：渐进式分析策略选择
    - **Property 15: 渐进式分析策略选择**
    - **Validates: Requirements 8.2**
  - [ ]* 19.9 编写 Property Test：洞察累积去重
    - **Property 16: 洞察累积去重**
    - **Validates: Requirements 8.5**

- [ ] 20. 实现 Replanner Agent（智能重规划）
  - [ ] 20.1 实现 Replanner Node
    - 评估完成度（completeness_score）
    - 识别缺失方面（missing_aspects）
    - 生成新问题（new_questions）
    - 路由决策：should_replan=True → Understanding，should_replan=False → END
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6_
  - [ ] 20.2 实现重规划历史记录
    - 记录每轮重规划的原因、新问题、完成度评分
    - _Requirements: 17.9_

- [ ] 21. Checkpoint - Phase 4 完成
  - 确保所有测试通过，如有问题请询问用户。


## Phase 5: 中间件集成

- [ ] 22. 集成 LangChain 中间件
  - [ ] 22.1 集成 ModelRetryMiddleware
    - 指数退避策略（1s、2s、4s）
    - 最多重试 3 次
    - _Requirements: 9.1, 9.2, 9.3, 9.4_
  - [ ] 22.2 集成 ToolRetryMiddleware
    - 指数退避策略
    - 重试耗尽返回错误 ToolMessage
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - [ ] 22.3 集成 SummarizationMiddleware
    - token 超过阈值时触发总结
    - 只总结对话消息，不总结 insights
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
  - [ ] 22.4 集成 TodoListMiddleware
    - 提供 write_todos 工具
    - 任务状态持久化到 VizQLState.todos
    - _Requirements: 16.1, 16.2, 16.3, 16.4_
  - [ ] 22.5 集成 HumanInTheLoopMiddleware（可选）
    - 支持 interrupt_on 参数
    - 用户超时处理
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_
  - [ ]* 22.6 编写 Property Test：LLM 重试指数退避
    - **Property 17: LLM 重试指数退避**
    - **Validates: Requirements 9.2**
  - [ ]* 22.7 编写 Property Test：对话总结职责分离
    - **Property 18: 对话总结职责分离**
    - **Validates: Requirements 11.5**

- [ ] 23. 实现状态持久化
  - [ ] 23.1 实现 SQLite checkpointer
    - 会话检查点保存
    - 会话恢复
    - _Requirements: 18.4, 18.5_
  - [ ]* 23.2 编写 Property Test：状态累积保持
    - **Property 5: 状态累积保持**
    - **Validates: Requirements 2.6, 18.2**

- [ ] 24. Checkpoint - Phase 5 完成
  - 确保所有测试通过，如有问题请询问用户。

## Phase 6: 辅助功能

- [ ] 25. 实现配置管理
  - [ ] 25.1 实现 ConfigManager
    - 从环境变量和配置文件加载
    - 支持中间件参数和模型参数
    - 支持运行时重新加载
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_

- [ ] 26. 实现安全性基础
  - [ ] 26.1 实现 API 密钥管理
    - 使用环境变量或加密配置文件
    - _Requirements: 22.1_
  - [ ] 26.2 实现日志脱敏
    - 自动脱敏敏感信息
    - _Requirements: 22.2_
  - [ ] 26.3 实现会话数据隔离
    - 通过 session_id 和 user_id 隔离
    - _Requirements: 22.3, 22.5_

- [ ] 27. 实现可观测性
  - [ ] 27.1 实现节点执行日志
    - 记录节点名称、输入摘要、输出摘要、延迟
    - _Requirements: 19.1_
  - [ ] 27.2 实现工具调用日志
    - 记录工具名称、参数、结果摘要、延迟
    - _Requirements: 19.2_
  - [ ] 27.3 实现中间件执行日志
    - 记录中间件名称、采取的操作、错误
    - _Requirements: 19.3_
  - [ ] 27.4 实现 RAG 检索日志
    - 记录查询、候选数量、top-3 分数、延迟
    - _Requirements: 19.4_
  - [ ] 27.5 实现错误日志
    - 记录错误类型、消息、堆栈跟踪、上下文
    - _Requirements: 19.5_

- [ ] 28. Final Checkpoint - 全部完成
  - 确保所有测试通过，如有问题请询问用户。
