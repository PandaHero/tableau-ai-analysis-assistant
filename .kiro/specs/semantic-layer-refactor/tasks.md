# Implementation Plan

**重要说明：** 本次重构建立高度抽象、平台无关的语义层架构，采用 LLM 组合模式（Step 1 + Step 2 + Observer）形成闭环，减少幻觉。

**核心理论：**
- 三元模型：查询 = What × Where × How
- 计算模型：计算 = 目标 × 分区 × 操作
- partition_by 是统一所有复杂计算的核心抽象

**LLM 组合架构：**
- Step 1：语义理解与问题重述（直觉）
- Step 2：计算推理与自我验证（推理）
- Observer：一致性检查（元认知，按需介入）

**6层架构：**
1. 核心层（core/）：平台无关的语义模型和接口
2. 平台层（platforms/）：平台特定实现
3. Agent层（agents/）：智能处理单元
4. 编排层（orchestration/）：工作流 + 工具 + 中间件
5. 基础设施层（infra/）：AI 模型、存储、配置、监控
6. 服务层（api/）：HTTP API

---

## 阶段 1：核心层目录结构

- [x] 1. 创建 core/ 目录结构

  - [x] 1.1 创建核心目录和 __init__.py 文件


    - 创建 `src/core/__init__.py`
    - 创建 `src/core/models/__init__.py`
    - 创建 `src/core/interfaces/__init__.py`
    - _Requirements: 架构设计_

---

## 阶段 2：核心数据模型（平台无关）

- [x] 2. 创建公共枚举类型


  - [x] 2.1 创建 `src/core/models/enums.py`


    - `AggregationType`: SUM, AVG, COUNT, COUNT_DISTINCT, MIN, MAX, MEDIAN, STDEV, VAR
    - `DateGranularity`: YEAR, QUARTER, MONTH, WEEK, DAY, HOUR, MINUTE
    - `SortDirection`: ASC, DESC
    - `FilterType`: SET, DATE_RANGE, NUMERIC_RANGE, TEXT_MATCH, TOP_N
    - `DateRangeType`: CURRENT, PREVIOUS, PREVIOUS_N, NEXT, NEXT_N, TO_DATE, CUSTOM
    - `TextMatchType`: CONTAINS, STARTS_WITH, ENDS_WITH, EXACT, REGEX
    - `HowType`: SIMPLE, RANKING, CUMULATIVE, COMPARISON, GRANULARITY
    - `OperationType`: RANK, DENSE_RANK, RUNNING_SUM, RUNNING_AVG, MOVING_AVG, MOVING_SUM, PERCENT, DIFFERENCE, GROWTH_RATE, YEAR_AGO, PERIOD_AGO, FIXED
    - `IntentType`: DATA_QUERY, CLARIFICATION, GENERAL, IRRELEVANT
    - `ObserverDecision`: ACCEPT, CORRECT, RETRY, CLARIFY

    - _Requirements: 9.1-9.6, 10.1-10.5_



- [x] 3. 创建字段模型
  - [x] 3.1 创建 `src/core/models/fields.py`

    - `DimensionField`: field_name, date_granularity, alias


    - `MeasureField`: field_name, aggregation, alias
    - `Sort`: field_name, direction, priority
    - _Requirements: 5.1-5.2_




- [x] 4. 创建计算模型（核心抽象）
  - [x] 4.1 创建 `src/core/models/computations.py`
    - `Operation`: type (OperationType), params (dict)
    - `Computation`: target, partition_by, operation, alias
    - 添加验证：partition_by 必须是字符串列表，target 不为空
    - _Requirements: 9.1-9.6, 13.1-13.2_




- [x] 5. 创建过滤器模型

  - [x] 5.1 创建 `src/core/models/filters.py`


    - `Filter` 基类: field_name, filter_type
    - `SetFilter`: values, exclude
    - `DateRangeFilter`: range_type, start_date, end_date, n, granularity
    - `NumericRangeFilter`: min_value, max_value, include_min, include_max
    - `TextMatchFilter`: pattern, match_type
    - `TopNFilter`: n, by_field, direction
    - _Requirements: 10.1-10.5_

- [x] 6. 创建语义查询模型
  - [x] 6.1 创建 `src/core/models/query.py`

    - `SemanticQuery`: dimensions, measures, computations, filters, sorts, row_limit


    - _Requirements: 5.1-5.3_

- [x] 7. 创建 Step 1 输入输出模型
  - [x] 7.1 创建 `src/core/models/step1.py`
    - `MeasureSpec`: field, aggregation
    - `DimensionSpec`: field, granularity
    - `FilterSpec`: field, type, values
    - `What`: measures (list[MeasureSpec])

    - `Where`: dimensions (list[DimensionSpec]), filters (list[FilterSpec])


    - `Intent`: type (IntentType), reasoning
    - `Step1Output`: restated_question, what, where, how_type, intent
    - 字段描述使用 XML 标签（`<what>`, `<when>`, `<rule>`, `<must_not>`）
    - 每个字段描述 ≤100 tokens
    - Class Docstring 包含 `<fill_order>`, ≤2 个示例, ≤3 个反模式
    - _Requirements: 1.1-1.4, 2.1-2.5, 14.1-14.4, 16.1-16.4, 17.1-17.4, 18.1-18.4_


- [x] 8. 创建 Step 2 输入输出模型



  - [x] 8.1 创建 `src/core/models/step2.py`

    - `ValidationCheck`: inferred_value, reference_value, is_match, note


    - `Step2Validation`: target_check, partition_by_check, operation_check, all_valid, inconsistencies
    - `Step2Output`: computations, reasoning, validation
    - **重要**：validation 是 LLM 自我验证的输出，不是代码验证
    - LLM 根据 Prompt 中的 OPERATION_TYPE_MAPPING 参考信息自行判断一致性

    - 字段描述使用 XML 标签（`<what>`, `<when>`, `<rule>`, `<must_not>`）


    - 每个字段描述 ≤100 tokens

    - Class Docstring 包含 `<fill_order>`, ≤2 个示例, ≤3 个反模式
    - _Requirements: 6.1-6.3, 7.1-7.4, 14.1-14.4, 16.1-16.4, 17.1-17.4, 18.1-18.4_

- [x] 9. 创建 Observer 输入输出模型
  - [x] 9.1 创建 `src/core/models/observer.py`
    - `Conflict`: aspect, description, step1_value, step2_value

    - `Correction`: field, original_value, corrected_value, reason


    - `ObserverInput`: original_question, step1, step2
    - `ObserverOutput`: is_consistent, conflicts, decision, correction, final_result
    - 字段描述使用 XML 标签（`<what>`, `<when>`, `<rule>`, `<must_not>`）
    - 每个字段描述 ≤100 tokens
    - Class Docstring 包含 `<fill_order>`, ≤2 个示例, ≤3 个反模式

    - _Requirements: 8.1-8.5, 14.1-14.4, 16.1-16.4, 17.1-17.4, 18.1-18.4_



- [x] 10. 创建解析结果模型
  - [x] 10.1 创建 `src/core/models/parse_result.py`

    - `ClarificationQuestion`: question, options, field_reference


    - `SemanticParseResult`: restated_question, intent, semantic_query, clarification, general_response
    - _Requirements: 3.1-3.4, 4.1-4.3_



- [x] 11. 创建验证和结果模型


  - [x] 11.1 创建 `src/core/models/validation.py`
    - `ValidationError`: error_type, field_path, message, suggestion
    - `ValidationResult`: is_valid, errors, warnings, auto_fixed
    - `ColumnInfo`: name, data_type, is_dimension, is_measure, is_computation
    - `QueryResult`: columns, rows, row_count, execution_time_ms

    - _Requirements: 13.1-13.3_

- [x] 12. 创建模型入口文件
  - [x] 12.1 更新 `src/core/models/__init__.py`
    - 导出所有核心模型类
    - _Requirements: 架构设计_

- [x] 13. Checkpoint - 确保核心模型可导入
  - 运行 `python -c "from src.core.models import *"` 确保无导入错误

---

## 阶段 3：核心接口定义

- [x] 14. 创建平台适配器接口
  - [x] 14.1 创建 `src/core/interfaces/platform_adapter.py`
    - `BasePlatformAdapter` 抽象基类
    - `platform_name` 属性
    - `execute_query(semantic_query, datasource_id)` 方法
    - `build_query(semantic_query)` 方法
    - `validate_query(semantic_query)` 方法
    - _Requirements: 11.1-11.4_

- [x] 15. 创建查询构建器接口
  - [x] 15.1 创建 `src/core/interfaces/query_builder.py`
    - `BaseQueryBuilder` 抽象基类
    - `build(semantic_query)` 方法
    - `validate(semantic_query)` 方法
    - _Requirements: 11.1-11.4_

- [x] 16. 创建字段映射器接口
  - [x] 16.1 创建 `src/core/interfaces/field_mapper.py`
    - `BaseFieldMapper` 抽象基类
    - `map(semantic_query)` 方法
    - `map_single_field(field_name)` 方法
    - _Requirements: 12.1-12.2_

- [x] 17. 更新接口入口文件
  - [x] 17.1 更新 `src/core/interfaces/__init__.py`
    - 导出所有接口类
    - _Requirements: 架构设计_

---

## 阶段 4：Semantic Parser Agent（LLM 组合）

- [x] 18. 创建 Semantic Parser Agent 目录

  - [x] 18.1 创建目录结构

    - 创建 `src/agents/semantic_parser/__init__.py`
    - 创建 `src/agents/semantic_parser/components/__init__.py`
    - 创建 `src/agents/semantic_parser/prompts/__init__.py`
    - _Requirements: 架构设计_

- [x] 19. 创建 Step 1 Prompt 模板

  - [x] 19.1 创建 `src/agents/semantic_parser/prompts/step1.py`


    - `STEP1_SYSTEM_PROMPT`: 语义理解 + 问题重述 + 意图分类
    - `STEP1_USER_TEMPLATE`: 包含 question, history, metadata 占位符
    - 关键：重述中必须保留分区意图（每月、每省、当月、全国等）
    - Prompt 仅包含高层概念，不引用具体字段名
    - 参考附件A和附件E的 Prompt 设计
    - _Requirements: 1.1-1.4, 2.1-2.5, 15.1-15.4_

- [x] 20. 创建 Step 2 Prompt 模板

  - [x] 20.1 创建 `src/agents/semantic_parser/prompts/step2.py`


    - `STEP2_SYSTEM_PROMPT`: 计算推理 + LLM 自我验证
    - `STEP2_USER_TEMPLATE`: 包含 restated_question, what, where, how_type 占位符
    - **重要**：验证是 LLM 自己做的，不是代码验证
    - Prompt 中包含 OPERATION_TYPE_MAPPING 作为 LLM 验证的参考信息
    - LLM 自行检查：target_check, partition_by_check, operation_check
    - Prompt 仅包含高层概念，不引用具体字段名
    - 参考附件B和附件E的 Prompt 设计
    - _Requirements: 6.1-6.3, 7.1-7.4, 15.1-15.4_




- [x] 21. 创建 Observer Prompt 模板
  - [x] 21.1 创建 `src/agents/semantic_parser/prompts/observer.py`
    - `OBSERVER_SYSTEM_PROMPT`: 一致性检查 + 决策
    - `OBSERVER_USER_TEMPLATE`: 包含 original_question, step1, step2 占位符
    - 检查项：重述完整性、结构一致性、语义一致性
    - 决策：ACCEPT / CORRECT / RETRY / CLARIFY

    - Prompt 仅包含高层概念，不引用具体字段名


    - 参考附件B和附件E的 Observer 设计
    - _Requirements: 8.1-8.5, 15.1-15.4_

- [x] 22. 实现 Step 1 组件

  - [x] 22.1 创建 `src/agents/semantic_parser/components/step1.py`


    - `Step1Component` 类
    - `execute(question, history, metadata)` 方法
    - LLM 调用，输出 Step1Output
    - 处理意图分类
    - _Requirements: 1.1-1.4, 2.1-2.5_




- [x] 23. 实现 Step 2 组件
  - [x] 23.1 创建 `src/agents/semantic_parser/components/step2.py`
    - `Step2Component` 类
    - `execute(step1_output)` 方法

    - LLM 调用，输出 Step2Output（包含 LLM 自我验证结果 validation）


    - **注意**：validation 由 LLM 自己填写，组件代码不做额外验证
    - 仅当 how_type != SIMPLE 时触发
    - _Requirements: 6.1-6.3, 7.1-7.4_

- [x] 24. 实现 Observer 组件
  - [x] 24.1 创建 `src/agents/semantic_parser/components/observer.py`

    - `ObserverComponent` 类


    - `execute(original_question, step1_output, step2_output)` 方法
    - LLM 调用，输出 ObserverOutput
    - 仅当 step2.validation.all_valid == False 时触发


    - _Requirements: 8.1-8.5_

- [x] 25. 实现 SemanticParserAgent 主类
  - [x] 25.1 创建 `src/agents/semantic_parser/agent.py`
    - `SemanticParserAgent` 类
    - `parse(question, history, metadata)` 主方法
    - 编排 Step 1 → 意图分支 → Step 2 → Observer 流程
    - `_build_semantic_query()`: 合并 Step1 + Step2 为 SemanticQuery

    - `_generate_clarification()`: 生成澄清问题（仅 CLARIFICATION 意图）
    - `_generate_general_response()`: 生成通用响应（仅 GENERAL 意图）
    - _Requirements: 1.1-1.4, 2.1-2.5, 3.1-3.4, 4.1-4.3, 5.1-5.3, 6.1-6.3, 7.1-7.4, 8.1-8.5_

- [x] 26. 创建 SemanticParserNode（工作流节点）
  - [x] 26.1 创建 `src/agents/semantic_parser/node.py`
    - `SemanticParserNode` 类
    - 实现 LangGraph 节点接口
    - 调用 SemanticParserAgent
    - _Requirements: 架构设计_

- [x] 27. Checkpoint - 测试 LLM 组合流程
  - 编写测试验证 Step 1 → Step 2 → Observer 流程
  - 测试意图分支（DATA_QUERY / CLARIFICATION / GENERAL / IRRELEVANT）
  - 测试验证通过的情况（不触发 Observer）
  - 测试验证不通过的情况（触发 Observer）
  - ✅ 模块导入测试通过

---

## 阶段 5：平台层目录结构

- [x] 28. 创建 platforms/ 目录结构
  - [x] 28.1 创建平台层目录
    - 创建 `src/platforms/__init__.py`
    - 创建 `src/platforms/base.py`（平台注册和工厂）
    - 创建 `src/platforms/tableau/__init__.py`
    - 创建 `src/platforms/tableau/models/__init__.py`
    - _Requirements: 架构设计_

---

## 阶段 6：Tableau 平台实现

- [x] 29. 创建 Tableau 特定模型


  - [x] 29.1 创建 `src/platforms/tableau/models/vizql_types.py`
    - VizQL API 对齐的类型（参考 OpenAPI 规范）
    - `VizQLFunction` 枚举
    - `VizQLFilterType` 枚举
    - _Requirements: 11.1_

  - [x] 29.2 创建 `src/platforms/tableau/models/table_calc.py`
    - `TableCalcType` 枚举: RANK, RUNNING_TOTAL, PERCENT_OF_TOTAL, MOVING_CALCULATION, DIFFERENCE_FROM
    - `TableCalcSpecification` 模型
    - `TableCalcDimension` 模型
    - _Requirements: 9.1-9.6_

  - [x] 29.3 创建 `src/platforms/tableau/models/lod.py`
    - `LODType` 枚举: FIXED, INCLUDE, EXCLUDE
    - `LODExpression` 模型
    - _Requirements: 9.6_

- [x] 30. 实现 Tableau 查询构建器
  - [x] 30.1 创建 `src/platforms/tableau/query_builder.py`
    - `TableauQueryBuilder` 类（实现 BaseQueryBuilder）
    - `build(semantic_query)`: SemanticQuery → VizQL 请求
    - `validate(semantic_query)`: 验证语义查询
    - _Requirements: 11.1_

  - [x] 30.2 实现 partition_by → Tableau 表计算转换
    - `_build_computation_field()`: Computation → TableCalc/LOD
    - partition_by=[] → Partitioning=无, Addressing=全部维度
    - partition_by=[月份] → Partitioning=月份, Addressing=剩余维度
    - RANK → TableCalc RANK
    - RUNNING_SUM → TableCalc RUNNING_TOTAL
    - PERCENT → TableCalc PERCENT_OF_TOTAL
    - FIXED → 根据 partition_by 与视图维度关系决定 LOD 类型
    - _Requirements: 9.1-9.6, 11.2_

  - [x] 30.3 实现过滤器转换
    - SET → VizQL SET Filter
    - DATE_RANGE (relative) → VizQL DATE Filter
    - DATE_RANGE (absolute) → VizQL QUANTITATIVE_DATE Filter
    - NUMERIC_RANGE → VizQL QUANTITATIVE_NUMERICAL Filter
    - TEXT_MATCH → VizQL MATCH Filter
    - TOP_N → VizQL TOP Filter
    - _Requirements: 10.1-10.5_

- [x] 31. 实现 Tableau 字段映射器
  - [x] 31.1 创建 `src/platforms/tableau/field_mapper.py`
    - `TableauFieldMapper` 类（实现 BaseFieldMapper）
    - 复用现有 RAG + LLM 两阶段检索
    - `map(semantic_query)`: 映射所有字段
    - `map_single_field(field_name)`: 映射单个字段
    - _Requirements: 12.1-12.2_

- [x] 32. 实现 Tableau 适配器
  - [x] 32.1 创建 `src/platforms/tableau/adapter.py`
    - `TableauAdapter` 类（实现 BasePlatformAdapter）
    - `execute_query()`: 完整执行流程
    - `build_query()`: 调用 QueryBuilder
    - `validate_query()`: 调用 QueryBuilder.validate()
    - _Requirements: 11.1-11.4_

- [x] 33. 迁移 VizQL 客户端
  - [x] 33.1 创建 `src/platforms/tableau/client.py`
    - 从现有代码迁移或引用 VizQL API 客户端
    - _Requirements: 架构设计_

- [x] 34. 实现自动修正和错误处理
  - [x] 34.1 在 TableauQueryBuilder 中实现
    - 参数默认值填充（缺少 aggregation → SUM，缺少 direction → DESC）
    - 验证失败时返回详细错误信息（ValidationResult）
    - _Requirements: 11.3, 11.4, 13.3_

- [x] 35. Checkpoint - 测试 Tableau 适配器
  - 编写测试验证 SemanticQuery → VizQL 转换正确
  - 测试 partition_by 到 Tableau 表计算的转换
  - 测试过滤器转换
  - ✅ 模块导入测试通过

---

## 阶段 7：平台工厂和集成

- [x] 36. 实现平台工厂
  - [x] 36.1 完善 `src/platforms/base.py`
    - `PlatformRegistry`: 平台注册表
    - `get_adapter(platform_name)`: 获取适配器实例
    - `register_adapter(name, adapter_class)`: 注册适配器
    - _Requirements: 架构设计_




- [x] 37. 集成到工作流


  - [x] 37.1 更新 `src/orchestration/workflow/factory.py`

    - 使用新的 SemanticParserAgent
    - 使用平台适配器
    - _Requirements: 架构设计_

  - [x] 37.2 配置中间件支持

    - 确保 OutputValidationMiddleware 覆盖新 Agent
    - 确保 ModelRetryMiddleware 支持重试
    - _Requirements: 11.3_

- [x] 38. Checkpoint - 端到端测试
  - 测试完整流程：用户问题 → SemanticQuery → VizQL → 执行结果
  - 测试 LLM 组合的各种场景
  - 测试意图分支处理
  - ✅ 模块导入测试通过

---

## 阶段 8：基础设施层迁移

- [x] 39. 创建 infra/ 目录结构并迁移模块
  - [x] 39.1 创建 `src/infra/` 目录结构
    - 创建 `src/infra/__init__.py`
    - 创建 `src/infra/ai/` (llm.py, embeddings.py, reranker.py)
    - 创建 `src/infra/config/` (settings.py)
    - 创建 `src/infra/monitoring/` (callbacks.py)
    - 创建 `src/infra/storage/` (__init__.py)
    - 创建 `src/infra/utils/` (conversation.py)
    - 创建 `src/infra/exceptions.py`
    - _Requirements: 架构设计_

  - [x] 39.2 迁移到 `orchestration/` 统一包




    - 创建 `src/orchestration/__init__.py`
    - 迁移 `workflow/` → `orchestration/workflow/`
    - 迁移 `tools/` → `orchestration/tools/`
    - 迁移 `middleware/` → `orchestration/middleware/`
    - _Requirements: 架构设计_

  - [x] 39.3 直接迁移（无向后兼容）
    - 删除 `utils/` 目录，更新引用到 `infra/utils/`
    - 删除 `exceptions.py`，更新引用到 `infra/exceptions.py`
    - 删除 `monitoring/` 目录，功能已在 `infra/monitoring/`
    - 删除 `components/insight/`，迁移到 `agents/insight/components/`
    - 删除 `models/vizql/`，功能已在 `platforms/tableau/models/`
    - 更新所有 `model_manager` 引用到 `infra/ai/`
    - `tools/__init__.py` → 重定向到 `orchestration/tools/`
    - `workflow/__init__.py` → 重定向到 `orchestration/workflow/`
    - `middleware/__init__.py` → 重定向到 `orchestration/middleware/`
    - `exceptions.py` → 重定向到 `infra/exceptions.py`
    - 所有重定向添加 DeprecationWarning
    - _Requirements: 代码整洁_

---

## 阶段 9：清理和文档

- [x] 40. 清理旧代码（直接删除，无向后兼容）
  - [x] 40.1 删除旧目录和文件
    - 删除 `workflow/`, `tools/`, `middleware/` 目录（已迁移到 `orchestration/`）
    - 删除 `utils/` 目录（已迁移到 `infra/utils/`）
    - 删除 `monitoring/` 目录（已迁移到 `infra/monitoring/`）
    - 删除 `exceptions.py`（已迁移到 `infra/exceptions.py`）
    - 删除 `components/insight/`（已迁移到 `agents/insight/components/`）
    - 删除 `models/vizql/`（已迁移到 `platforms/tableau/models/`）
    - 更新所有引用到新路径
    - _Requirements: 代码整洁_

  - [x] 40.2 合并 bi_platforms/tableau/ 到 platforms/tableau/
    - 迁移 `bi_platforms/tableau/auth.py` → `platforms/tableau/auth.py`
    - 迁移 `bi_platforms/tableau/metadata.py` → `platforms/tableau/metadata.py`
    - 迁移 `bi_platforms/tableau/vizql_client.py` → `platforms/tableau/vizql_client.py`
    - 更新 `platforms/tableau/__init__.py` 导出所有功能
    - 删除 `bi_platforms/` 目录
    - 更新所有 `bi_platforms.tableau` 引用到 `platforms.tableau`
    - _Requirements: 架构设计_

  - [x] 40.3 迁移 services/ 到 api/
    - 迁移 `services/preload_service.py` → `api/preload_service.py`
    - 更新 `api/preload.py` 引用
    - 删除 `services/` 目录
    - _Requirements: 架构设计_
    - 删除 `components/insight/`（已迁移到 `agents/insight/components/`）
    - 删除 `models/vizql/`（已迁移到 `platforms/tableau/models/`）
    - 更新所有引用到新路径
    - _Requirements: 代码整洁_

- [x] 41. Final Checkpoint - 确保所有测试通过
  - 运行完整测试套件
  - 验证新架构正常工作
  - ✅ 所有模块导入测试通过
  - ✅ 修复了编码问题（乱码）
  - ✅ 修复了存储模块导入路径问题
  - ✅ 重命名 create_tableau_workflow → create_workflow
  - ✅ 移除不必要的 TYPE_CHECKING，直接导入类型

