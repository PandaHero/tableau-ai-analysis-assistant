# Implementation Plan

**重要说明：** 本次重构建立高度抽象、平台无关的语义层架构，采用两步解析流程（Step 1 语义理解 + Step 2 计算推理）。

**核心理论：**
- 三元模型：查询 = What × Where × How
- 计算模型：计算 = 目标 × 分区 × 操作
- partition_by 是统一所有复杂计算的核心抽象

---

## 阶段 1：核心层目录结构

- [ ] 1. 创建 core/ 目录结构
  - [ ] 1.1 创建核心目录和 __init__.py 文件
    - 创建 `src/core/__init__.py`
    - 创建 `src/core/models/__init__.py`
    - 创建 `src/core/agents/__init__.py`
    - 创建 `src/core/interfaces/__init__.py`
    - _Requirements: 架构设计_

---

## 阶段 2：核心数据模型（平台无关）

- [ ] 2. 创建公共枚举类型
  - [ ] 2.1 创建 `src/core/models/enums.py`
    - `AggregationType`: SUM, AVG, COUNT, COUNT_DISTINCT, MIN, MAX, MEDIAN, STDEV, VAR
    - `DateGranularity`: YEAR, QUARTER, MONTH, WEEK, DAY, HOUR, MINUTE
    - `SortDirection`: ASC, DESC
    - `FilterType`: SET, DATE_RANGE, NUMERIC_RANGE, TEXT_MATCH, TOP_N
    - `DateRangeType`: CURRENT, PREVIOUS, PREVIOUS_N, NEXT, NEXT_N, TO_DATE, CUSTOM
    - `TextMatchType`: CONTAINS, STARTS_WITH, ENDS_WITH, EXACT, REGEX
    - `HowType`: SIMPLE, RANKING, CUMULATIVE, COMPARISON, GRANULARITY
    - `OperationType`: RANK, DENSE_RANK, TOP_N, RUNNING_SUM, RUNNING_AVG, RUNNING_COUNT, MOVING_AVG, MOVING_SUM, PERCENT, DIFFERENCE, GROWTH_RATE, YEAR_AGO, PERIOD_AGO, FIXED, INCLUDE, EXCLUDE, CUSTOM
    - `IntentType`: DATA_QUERY, CLARIFICATION, GENERAL, IRRELEVANT
    - _Requirements: 4.1, 5.1-5.6, 6.1-6.5, 9.1-9.5_

- [ ] 3. 创建字段模型
  - [ ] 3.1 创建 `src/core/models/fields.py`
    - `DimensionField`: field_name, date_granularity, alias
    - `MeasureField`: field_name, aggregation, alias
    - `Sort`: field_name, direction, priority
    - _Requirements: 4.1_

- [ ] 4. 创建计算模型（核心抽象）
  - [ ] 4.1 创建 `src/core/models/computations.py`
    - `Operation`: type (OperationType), params (dict)
    - `Computation`: target, partition_by, operation, alias
    - 添加验证：partition_by 必须是字符串列表
    - _Requirements: 5.1-5.6, 6.1-6.5, 附件B_

- [ ] 5. 创建过滤器模型
  - [ ] 5.1 创建 `src/core/models/filters.py`
    - `Filter` 基类: field_name, filter_type
    - `SetFilter`: values, exclude
    - `DateRangeFilter`: range_type, start_date, end_date, n, granularity
    - `NumericRangeFilter`: min_value, max_value, include_min, include_max
    - `TextMatchFilter`: pattern, match_type
    - 添加日期格式验证（RFC 3339）
    - _Requirements: 9.1-9.5, 10.1-10.5_

- [ ] 6. 创建语义查询模型
  - [ ] 6.1 创建 `src/core/models/query.py`
    - `SemanticQuery`: dimensions, measures, computations, filters, sorts, row_limit
    - _Requirements: 4.1, 附件C_

- [ ] 7. 创建 Step 1/Step 2 输入输出模型
  - [ ] 7.1 在 `src/core/models/` 中添加 Step 相关模型
    - `MeasureSpec`: field, aggregation
    - `DimensionSpec`: field, granularity
    - `FilterSpec`: field, type, values
    - `What`: measures (list[MeasureSpec])
    - `Where`: dimensions (list[DimensionSpec]), filters (list[FilterSpec])
    - `How`: type (HowType), hints (dict)
    - `Step1Output`: what, where, how, semantic_restatement
    - `Step2Output`: computations (list[Computation])
    - _Requirements: 附件A, 附件B_

- [ ] 8. 创建解析结果模型
  - [ ] 8.1 创建 `src/core/models/parse_result.py`
    - `Intent`: type (IntentType), reasoning
    - `ClarificationQuestion`: question, options, field_reference
    - `SemanticParseResult`: restated_question, intent, semantic_query, clarification, general_response
    - _Requirements: 1.1-1.6, 2.1-2.5, 3.1-3.5_

- [ ] 9. 创建验证错误类型
  - [ ] 9.1 创建 `src/core/models/errors.py`
    - `SemanticValidationError`: error_type, field_path, message, suggestion
    - `ComputationValidationError`
    - `FilterValidationError`
    - `DateValidationError`
    - _Requirements: 12.1-12.4_

- [ ] 10. 创建模型入口文件
  - [ ] 10.1 更新 `src/core/models/__init__.py`
    - 导出所有核心模型类
    - _Requirements: 4.1_

- [ ] 11. Checkpoint - 确保核心模型可导入
  - 运行 `python -c "from src.core.models import *"` 确保无导入错误

---

## 阶段 3：核心接口定义

- [ ] 12. 创建平台适配器接口
  - [ ] 12.1 创建 `src/core/interfaces/platform_adapter.py`
    - `BasePlatformAdapter` 抽象基类
    - `platform_name` 属性
    - `execute_query(semantic_query, datasource_id)` 方法
    - `build_query(semantic_query)` 方法
    - `validate_query(semantic_query)` 方法
    - `QueryResult` 模型
    - `ColumnInfo` 模型
    - _Requirements: 7.1, 附件D_

- [ ] 13. 创建查询构建器接口
  - [ ] 13.1 创建 `src/core/interfaces/query_builder.py`
    - `BaseQueryBuilder` 抽象基类
    - `build(semantic_query)` 方法
    - `validate(semantic_query)` 方法
    - `ValidationResult` 模型
    - _Requirements: 7.1-7.6_

- [ ] 14. 创建字段映射器接口
  - [ ] 14.1 创建 `src/core/interfaces/field_mapper.py`
    - `BaseFieldMapper` 抽象基类
    - `map(semantic_query)` 方法
    - `map_single_field(field_name)` 方法
    - _Requirements: 8.1-8.4_

- [ ] 15. 更新接口入口文件
  - [ ] 15.1 更新 `src/core/interfaces/__init__.py`
    - 导出所有接口类
    - _Requirements: 架构设计_

---

## 阶段 4：Semantic Parser Agent

- [ ] 16. 创建 Semantic Parser Agent 目录
  - [ ] 16.1 创建目录结构
    - 创建 `src/core/agents/semantic_parser/__init__.py`
    - _Requirements: 架构设计_

- [ ] 17. 创建 Prompt 模板
  - [ ] 17.1 创建 `src/core/agents/semantic_parser/prompts.py`
    - `STEP1_SYSTEM_PROMPT`: 三元组构建指导
    - `STEP1_USER_TEMPLATE`: 包含 question, history, metadata 占位符
    - `STEP2_SYSTEM_PROMPT`: 分区推断规则
    - `STEP2_USER_TEMPLATE`: 包含 step1_output 占位符
    - 参考附件A和附件B的 Prompt 设计
    - _Requirements: 附件A, 附件B, 13.1-13.5, 14.1-14.4_

- [ ] 18. 实现 SemanticParserAgent
  - [ ] 18.1 创建 `src/core/agents/semantic_parser/agent.py`
    - `SemanticParserAgent` 类
    - `parse(question, history, metadata)` 主方法
    - `_step1_semantic_understanding()`: LLM 调用，输出 Step1Output
    - `_step2_computation_reasoning()`: LLM 调用，输出 Step2Output（仅 How.type != SIMPLE 时触发）
    - `_build_semantic_query()`: 合并 Step1 + Step2 为 SemanticQuery
    - `_classify_intent()`: 意图分类
    - `_generate_clarification()`: 生成澄清问题
    - _Requirements: 1.1-1.6, 2.1-2.5, 3.1-3.5, 4.1-4.4, 附件A, 附件B_

- [ ] 19. Checkpoint - 测试 Agent 基本流程
  - 编写简单测试验证 Agent 可以处理基本查询

---

## 阶段 5：平台层目录结构

- [ ] 20. 创建 platforms/ 目录结构
  - [ ] 20.1 创建平台层目录
    - 创建 `src/platforms/__init__.py`
    - 创建 `src/platforms/base.py`（平台注册和工厂）
    - 创建 `src/platforms/tableau/__init__.py`
    - 创建 `src/platforms/tableau/models/__init__.py`
    - _Requirements: 架构设计_

---

## 阶段 6：Tableau 平台实现

- [ ] 21. 创建 Tableau 特定模型
  - [ ] 21.1 创建 `src/platforms/tableau/models/vizql_types.py`
    - VizQL API 对齐的类型（参考 OpenAPI 规范）
    - `VizQLFunction` 枚举
    - `VizQLFilterType` 枚举
    - _Requirements: 5.1-5.6_

  - [ ] 21.2 创建 `src/platforms/tableau/models/table_calc.py`
    - `TableCalcType` 枚举: RANK, RUNNING_TOTAL, PERCENT_OF_TOTAL, MOVING_CALCULATION, DIFFERENCE_FROM
    - `TableCalcSpecification` 模型
    - `TableCalcDimension` 模型
    - _Requirements: 5.1-5.6, 附件D_

- [ ] 22. 实现 Tableau 查询构建器
  - [ ] 22.1 创建 `src/platforms/tableau/query_builder.py`
    - `TableauQueryBuilder` 类（实现 BaseQueryBuilder）
    - `build(semantic_query)`: SemanticQuery → VizQL 请求
    - `validate(semantic_query)`: 验证语义查询
    - _Requirements: 7.1_

  - [ ] 22.2 实现 partition_by → Tableau 表计算转换
    - `_build_computation_field()`: Computation → TableCalc/LOD
    - partition_by=[] → Partitioning=无, Addressing=全部维度
    - partition_by=[月份] → Partitioning=月份, Addressing=剩余维度
    - RANK → TableCalc RANK
    - RUNNING_SUM → TableCalc RUNNING_TOTAL
    - PERCENT → TableCalc PERCENT_OF_TOTAL
    - FIXED → LOD {FIXED:...}
    - _Requirements: 5.1-5.6, 6.1-6.5, 7.2, 7.3, 附件D_

  - [ ] 22.3 实现过滤器转换
    - SET → VizQL SET Filter
    - DATE_RANGE (relative) → VizQL DATE Filter
    - DATE_RANGE (absolute) → VizQL QUANTITATIVE_DATE Filter
    - NUMERIC_RANGE → VizQL QUANTITATIVE_NUMERICAL Filter
    - TEXT_MATCH → VizQL MATCH Filter
    - TOP_N → VizQL TOP Filter
    - _Requirements: 9.1-9.5, 10.1-10.2_

- [ ] 23. 实现 Tableau 字段映射器
  - [ ] 23.1 创建 `src/platforms/tableau/field_mapper.py`
    - `TableauFieldMapper` 类（实现 BaseFieldMapper）
    - 复用现有 `capabilities/rag/` 的 RAG + LLM 两阶段检索
    - `map(semantic_query)`: 映射所有字段
    - `map_single_field(field_name)`: 映射单个字段
    - _Requirements: 8.1-8.4_

- [ ] 24. 实现 Tableau 适配器
  - [ ] 24.1 创建 `src/platforms/tableau/adapter.py`
    - `TableauAdapter` 类（实现 BasePlatformAdapter）
    - `execute_query()`: 完整执行流程
    - `build_query()`: 调用 QueryBuilder
    - `validate_query()`: 调用 QueryBuilder.validate()
    - _Requirements: 7.1-7.6, 附件D_

- [ ] 25. 迁移 VizQL 客户端
  - [ ] 25.1 创建 `src/platforms/tableau/client.py`
    - 从 `bi_platforms/tableau/vizql_client.py` 迁移或引用
    - _Requirements: 架构设计_

- [ ] 26. 实现自动修正和错误处理
  - [ ] 26.1 在 TableauQueryBuilder 中实现
    - 参数默认值填充（缺少 aggregation → SUM，缺少 direction → DESC）
    - 验证失败时返回详细错误信息
    - _Requirements: 7.4, 7.5, 7.6_

- [ ] 27. Checkpoint - 测试 Tableau 适配器
  - 编写测试验证 SemanticQuery → VizQL 转换正确

---

## 阶段 7：平台工厂和集成

- [ ] 28. 实现平台工厂
  - [ ] 28.1 完善 `src/platforms/base.py`
    - `PlatformRegistry`: 平台注册表
    - `get_adapter(platform_name)`: 获取适配器实例
    - `register_adapter(name, adapter_class)`: 注册适配器
    - _Requirements: 架构设计_

- [ ] 29. 集成到工作流
  - [ ] 29.1 更新 `src/workflow/factory.py`
    - 使用新的 SemanticParserAgent
    - 使用平台适配器
    - _Requirements: 1.1-1.6, 2.1-2.5, 3.1-3.5, 4.1-4.4_

  - [ ] 29.2 配置中间件支持
    - 确保 OutputValidationMiddleware 覆盖新 Agent
    - 确保 ModelRetryMiddleware 支持重试
    - _Requirements: 7.5_

- [ ] 30. Checkpoint - 端到端测试
  - 测试完整流程：用户问题 → SemanticQuery → VizQL → 执行结果

---

## 阶段 8：清理和文档

- [ ] 31. 标记旧代码为 deprecated
  - [ ] 31.1 添加 deprecation 警告
    - `agents/understanding/` 添加 DeprecationWarning
    - `models/semantic/` 添加 DeprecationWarning
    - `nodes/query_builder/implementation_resolver.py` 添加 DeprecationWarning
    - _Requirements: 代码整洁_

- [ ] 32. Final Checkpoint - 确保所有测试通过
  - 运行完整测试套件
  - 确保新旧代码可以共存（渐进式迁移）
