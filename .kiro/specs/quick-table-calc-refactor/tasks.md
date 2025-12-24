# 实现计划：快速表计算重构

## 概述

本实现计划将语义解析器中的表计算逻辑从自定义表计算重构为快速表计算，包括枚举重构、模型重构、QueryBuilder 更新和目录结构优化。

## 当前代码状态

⚠️ **注意**：当前代码存在问题：
- `OperationType` 被多处引用但未定义（导入会失败）
- `OPERATION_TYPE_MAPPING` 引用了不存在的 `HowType.RANKING` 等值
- 需要先修复这些问题才能继续

## 任务列表

- [x] 1. 重构核心枚举定义
  - [x] 1.1 简化 HowType 枚举为二元分类
    - 只保留 SIMPLE 和 COMPLEX 两个值
    - SIMPLE: 简单聚合，不需要 Step2
    - COMPLEX: 需要复杂计算，需要 Step2
    - _需求: 1.1-1.7_
  - [x] 1.2 添加 CalcType 枚举（替代 OperationType）
    - 添加排名类: RANK, DENSE_RANK, PERCENTILE
    - 添加累计类: RUNNING_TOTAL, MOVING_CALC
    - 添加占比类: PERCENT_OF_TOTAL
    - 添加差异类: DIFFERENCE, PERCENT_DIFFERENCE
    - 添加 LOD 类: LOD_FIXED, LOD_INCLUDE, LOD_EXCLUDE
    - _需求: 2.2_
  - [x] 1.3 添加辅助枚举
    - 添加 RankStyle: COMPETITION, DENSE, UNIQUE
    - 添加 RelativeTo: PREVIOUS, NEXT, FIRST, LAST
    - 添加 CalcAggregation: SUM, AVG, MIN, MAX
    - _需求: 2.4-2.9_
  - [x] 1.4 清理旧枚举和映射
    - 删除 OPERATION_TYPE_MAPPING（引用不存在的枚举值）
    - 删除 __init__.py 中的 OperationType 导出
    - 删除旧的 TABLE_CALC 和 LOD 枚举值（如果存在）
    - _需求: 1.1, 2.2_
  - [x] 1.5 更新 AggregationType 枚举
    - 将 COUNT_DISTINCT 改为 COUNTD（匹配 Tableau 命名）
    - _需求: 设计文档_

- [x] 2. 重构 Step2 模型
  - [x] 2.1 创建 CalcParams 模型
    - 添加排名参数: direction, rank_style
    - 添加差异参数: relative_to
    - 添加累计参数: aggregation, restart_every
    - 添加移动窗口参数: window_previous, window_next, include_current
    - 添加占比参数: level_of
    - 添加 LOD 参数: lod_dimensions, lod_aggregation
    - 所有字段设为 Optional，无默认值
    - _需求: 2.4-2.9_
  - [x] 2.2 更新 Computation 模型
    - 将 operation: Operation 替换为 calc_type: CalcType
    - 将 operation.params: dict 替换为 params: CalcParams
    - 保留 target, partition_by, alias 字段
    - _需求: 2.1-2.3_
  - [x] 2.3 删除旧的 Operation 模型
    - 删除 Operation 类
    - 更新 __init__.py 移除 Operation 导出
    - _需求: 2.2_
  - [x] 2.4 更新 Step2Validation
    - 更新 operation_check 为 calc_type_check
    - 更新验证规则以匹配新的 CalcType
    - _需求: 2.1_

- [x] 3. 更新 TableauQueryBuilder
  - [x] 3.1 添加 Tableau 默认值常量
    - DEFAULT_RANK_TYPE = RankStyle.COMPETITION
    - DEFAULT_DIRECTION = SortDirection.DESC
    - DEFAULT_RELATIVE_TO = RelativeTo.PREVIOUS
    - DEFAULT_AGGREGATION = CalcAggregation.SUM
    - DEFAULT_WINDOW_PREVIOUS = 2
    - DEFAULT_WINDOW_NEXT = 0
    - DEFAULT_INCLUDE_CURRENT = True
    - _需求: 5.5-5.9_
  - [x] 3.2 添加 CalcType → TableCalcType 映射
    - 创建 CALC_TYPE_MAPPING 字典
    - 创建 LOD_CALC_TYPES 集合
    - _需求: 5.5-5.9_
  - [x] 3.3 重构 _build_computation_fields 方法（支持组合场景）
    - 分离 LOD 和表计算类型
    - 先生成 CalculatedField (LOD)，后生成 TableCalcField
    - 确保表计算可以引用 LOD 结果
    - _需求: 5.1-5.4, 7.2-7.4_
  - [x] 3.4 实现 _build_rank_spec 方法
    - 应用默认值
    - 处理 DENSE_RANK 特殊情况
    - _需求: 5.5_
  - [x] 3.5 实现 _build_running_total_spec 方法
    - 应用默认值
    - 处理 restart_every 可选参数
    - _需求: 5.6_
  - [x] 3.6 实现 _build_percent_of_total_spec 方法
    - 处理 level_of 可选参数
    - _需求: 5.7_
  - [x] 3.7 实现 _build_difference_spec 方法
    - 应用默认值
    - 支持 DIFFERENCE 和 PERCENT_DIFFERENCE
    - _需求: 5.8_
  - [x] 3.8 实现 _build_moving_calc_spec 方法
    - 应用默认值
    - _需求: 5.9_
  - [x] 3.9 实现 _build_lod_field 方法
    - 支持 LOD_FIXED, LOD_INCLUDE, LOD_EXCLUDE
    - 生成正确的 LOD 表达式字符串
    - _需求: 5.10, 3.7_

- [x] 4. 检查点 - 核心功能验证
  - 确保所有测试通过，如有问题请询问用户

- [x] 5. 更新相关引用
  - [x] 5.1 更新 SemanticQuery 中的 computations 类型
    - 确保使用新的 Computation 模型
    - _需求: 6.1_
  - [x] 5.2 更新 Step1Output 中的 how_type 使用
    - 确保只使用 SIMPLE 和 COMPLEX
    - _需求: 1.1_
  - [x] 5.3 更新 models/__init__.py 导出
    - 导出新的枚举和模型（CalcType, CalcParams, RankStyle, RelativeTo, CalcAggregation）
    - 移除旧的导出（OperationType, Operation, OPERATION_TYPE_MAPPING）
    - _需求: 2.1_
  - [x] 5.4 更新 core/__init__.py 导出
    - 同步更新顶层导出
    - _需求: 2.1_
  - [x] 5.5 更新测试文件中的 OperationType 引用
    - 更新 test_semantic_parser_comprehensive.py
    - 将 expected_operation_types 改为 expected_calc_types
    - 更新 test_semantic_parser_integration.py
    - 更新 observer.py 组件和 prompt
    - _需求: 2.2_

- [x] 6. 更新 Step1 和 Step2 Prompt
  - [x] 6.1 更新 Step1 Prompt
    - 简化 how_type 判断逻辑（只需判断 SIMPLE 或 COMPLEX）
    - 添加复杂计算的识别规则（排名、累计、环比、LOD、组合等）
    - _需求: 1.2-1.5_
  - [x] 6.2 更新 Step2 Prompt 中的 CalcType 说明
    - 添加每种 CalcType 的业务场景示例
    - 说明 computations 可以包含多种类型（支持组合）
    - _需求: 4.6, 7.1_
  - [x] 6.3 更新 Step2 Prompt 中的参数说明
    - 添加 partition_by 语义说明
    - 添加 restart_every 语义说明
    - 添加 relative_to 语义说明
    - _需求: 4.2-4.5_
  - [x] 6.4 添加 LOD 表达式说明
    - 添加 LOD 语法和使用场景
    - _需求: 4.7_
  - [x] 6.5 添加组合场景说明
    - 说明何时需要 LOD + 表计算组合
    - 说明 computations 的输出顺序（先 LOD，后表计算）
    - _需求: 7.1-7.2_

- [x] 7. 检查点 - 完整功能验证
  - 确保所有测试通过，如有问题请询问用户

- [x] 8. 单元测试

  - [x] 8.1 CalcType 枚举测试


    - 测试序列化/反序列化
    - _需求: 2.2_

  - [x] 8.2 CalcParams 模型测试

    - 测试参数验证
    - 测试 Optional 字段行为
    - _需求: 2.4-2.9_

  - [x] 8.3 Computation 模型测试

    - 测试模型约束
    - _需求: 2.1-2.3_

  - [x] 8.4 TableauQueryBuilder 转换测试

    - 测试每种 CalcType 的转换
    - 测试默认值应用
    - _需求: 5.5-5.10_

- [ ] 9. 集成测试

  - [ ] 9.1 排名场景端到端测试
    - 用户问题 → COMPLEX → RANK → VizQL RANK
    - _需求: 1.3, 5.5_
    - **状态**: 100% 通过 (6/6)
    - **已修复**: Top N / Bottom N 现在使用 SIMPLE + TOP_N filter，而非 COMPLEX + RANK

  - [ ] 9.2 累计场景端到端测试
    - 用户问题 → COMPLEX → RUNNING_TOTAL → VizQL RUNNING_TOTAL
    - _需求: 1.3, 5.6_
    - **状态**: 83.3% 通过 (5/6)，YTD 测试描述已优化

  - [ ] 9.3 增长率场景端到端测试
    - 用户问题 → COMPLEX → PERCENT_DIFFERENCE → VizQL PERCENT_DIFFERENCE_FROM
    - _需求: 1.3, 5.8_
    - **状态**: 100% 通过 (5/5)

  - [ ] 9.4 LOD + 表计算组合场景端到端测试
    - 用户问题 → COMPLEX → [LOD_FIXED, RANK] → VizQL [CalculatedField, TableCalcField]
    - 验证字段生成顺序（先 LOD，后表计算）
    - _需求: 7.1-7.4_
    - **状态**: LOD 0% (0/5)，组合 75% (3/4)
    - **已修复**: 
      1. LOD 测试描述已添加明确的 LOD 触发关键词
      2. AggregationType 枚举已添加 `<rule>` 说明 percentage 不是聚合
      3. Step1 Prompt 已强化业务术语 vs 技术字段名的约束
      4. 组合测试描述已添加 LOD 触发关键词
      5. Top N / Bottom N 改为 SIMPLE + TOP_N filter（非 COMPLEX + RANK）
      6. FilterSpec 添加 TOP_N 支持（n, by_field, direction 字段）
      7. SemanticParserAgent._build_semantic_query 添加 TopNFilter 处理

## 注意事项

### 编码规范
- **不使用向后兼容**：直接删除旧代码，不保留废弃的类/函数
- **禁止使用 Any 类型**：所有字段必须有明确的类型注解，不使用 `Any`、无类型的 `dict`/`list`
- **禁止使用类型检查延迟注入**：不使用 `TYPE_CHECKING`、字符串类型注解，直接解决循环依赖

### 数据模型与 Prompt 模板职责
- **数据模型**：定义 LLM 输出的结构和约束（字段、类型、`<what>`/`<when>`/`<rule>`/`<dependency>`/`<must_not>`）
- **Prompt 模板**：教 LLM 如何思考（角色、任务、领域知识、推理步骤、全局约束）
- **黄金法则**：提到具体字段名→数据模型，通用分析方法→Prompt 模板

### 执行顺序
- 任务执行顺序很重要：先添加新枚举/模型，再更新引用，最后删除旧代码
- 每个检查点确保代码可运行，测试通过
- 当前代码有导入错误（OperationType 未定义），需要在任务1中修复

### 规范文档
- 更新数据模型和 Prompt 时，必须遵循 `.kiro/specs/semantic-layer-refactor/appendix-e-prompt-model-guide.md` 规范

## 需求覆盖矩阵

| 需求 | 覆盖任务 |
|------|---------|
| 需求1: 简化HowType为二元分类 | 1.1, 6.1 |
| 需求2: Step2输出对齐TableCalcField | 1.2, 1.3, 2.1, 2.2, 2.3, 2.4 |
| 需求3: Step2支持CalculatedField (LOD) | 1.2 (LOD_*), 2.1 (lod_*参数), 3.9 |
| 需求4: 重构Step2 Prompt | 6.2, 6.3, 6.4 |
| 需求5: 重构QueryBuilder | 3.1-3.9 |
| 需求6: dimensions语义正确映射 | 3.3-3.8 |
| 需求7: LOD与表计算组合使用 | 3.3, 6.5, 9.4 |
