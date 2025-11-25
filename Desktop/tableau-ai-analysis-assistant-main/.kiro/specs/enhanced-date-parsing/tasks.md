# Implementation Plan

## Overview

本实施计划将日期解析系统从分散的工具函数重构为统一的组件化架构。核心思路是创建 `DateParser` 组件作为统一入口，扩展现有的 `DateCalculator` 和 `Metadata` 模型，并修复所有相关模块的代码。

## Task List

- [ ] 1. 扩展 Metadata 模型
  - 添加智能参考日期选择方法
  - 支持多日期字段场景
  - TimeRange 模型保持不变（已经定义了标准格式）
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 1.1 扩展 Metadata 模型




  - 在 `tableau_assistant/src/models/metadata.py` 中添加 `get_reference_date()` 方法
  - 实现智能参考日期选择逻辑：
    - 优先级1：用户提到的日期字段的 valid_max_date
    - 优先级2：所有日期字段中最大的 valid_max_date
    - 优先级3：返回 None
  - 支持多日期字段场景
  - 添加详细的文档字符串
  - _Requirements: 6.1, 6.2, 6.3_

- [ ] 1.2 添加单元测试
  - 创建 `tests/unit/models/test_metadata_date.py`
  - 测试单个日期字段场景
  - 测试多个日期字段场景
  - 测试用户指定字段场景
  - 测试无日期字段场景
  - _Requirements: 6.1, 6.2, 6.3_

- [x] 2. 创建 DateParser 组件



  - 创建统一的日期计算入口（在 Query Builder 阶段使用）
  - 实现标准格式解析和验证逻辑
  - 集成 DateCalculator
  - 不存储结果，每次调用时计算



  - _Requirements: 1.1, 1.2, 1.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 2.1 创建 DateParser 基础类

  - 创建 `tableau_assistant/src/components/date_parser.py`
  - 实现 `__init__()` 方法（接受 date_calculator）
  - 实现 `calculate_date_range()` 主方法：
    - 输入：TimeRange, reference_date
    - 输出：(start_date, end_date) 元组
  - 添加简单的内存缓存机制（可选优化）
  - _Requirements: 1.1, 1.2, 1.3, 10.1, 10.2, 10.3_

- [x] 2.2 实现日期计算逻辑

  - 实现 `_calculate_dates()` 方法
  - 解析 LLM 输出的标准格式：
    - `value` 字段（年份、季度、月份、日期）
    - `start_date` + `end_date` 字段（日期范围）
    - `relative_type` + `period_type` + `range_n`（相对时间）
  - 补全缺失信息（如年份）
  - 调用 DateCalculator 计算相对时间
  - **不做任何自然语言语义理解**
  - 返回 (start_date, end_date) 元组
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 9.1, 9.2, 9.3, 9.4_

- [x] 2.3 实现日期验证逻辑

  - 实现 `_validate_date_range()` 方法
  - 验证 start_date <= end_date
  - 验证日期格式是否符合 ISO 标准
  - 检测异常范围（如跨度超过10年）
  - 抛出 ValueError 如果验证失败
  - _Requirements: 4.1, 4.5_

- [x] 2.4 实现边界调整逻辑（可选）




  - 实现 `_adjust_boundaries()` 方法
  - 如果 end_date 超过 max_date，调整为 max_date
  - 记录警告日志
  - 这是可选功能，可以在后续优化
  - _Requirements: 4.2, 4.3, 4.4_

- [x] 3. 确认 TimeRange 数据模型

  - 检查现有 TimeRange 模型是否支持所有需要的格式
  - 数据模型定义输出格式，LLM 自动遵守 Pydantic 模型
  - 如果需要，扩展模型支持日期范围格式
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3.1 检查 TimeRange 模型现有字段


  - 查看 `tableau_assistant/src/models/question.py` 中的 `TimeRange` 模型
  - 确认已支持的字段：
    - `value`（用于年份、季度、月份、日期）
    - `relative_type`, `period_type`, `range_n`（用于相对时间）
    - `start_date`, `end_date`（检查是否已存在）
  - 如果 `start_date` 和 `end_date` 已存在，无需修改
  - _Requirements: 3.1, 3.2_

- [x] 3.2 扩展 TimeRange 模型（如果需要）

  - 如果 `start_date` 和 `end_date` 字段不存在，添加这两个可选字段
  - 更新字段文档，说明用于 LLM 直接输出日期范围
  - 确保向后兼容（设置为 Optional）
  - 数据模型的修改会自动约束 LLM 输出格式
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6_

- [x] 4. 集成到 DateFilterConverter


  - 在 DateFilterConverter 中使用 DateParser
  - 替代现有的日期计算逻辑
  - 保持接口不变
  - _Requirements: 1.1, 1.2, 1.3, 9.1, 9.2, 9.3_

- [x] 4.1 重构 DateFilterConverter._calculate_date_range()


  - 修改 `tableau_assistant/src/components/query_builder/date_filter_converter.py`
  - 在 `__init__()` 中创建 DateParser 实例
  - 在 `_calculate_date_range()` 中使用 DateParser
  - 获取参考日期：使用 `metadata.get_reference_date(mentioned_field)`
  - 调用 `date_parser.calculate_date_range(time_range, reference_date)`
  - 删除 `_parse_absolute_time()` 方法（DateParser 已实现）
  - _Requirements: 1.1, 1.2, 1.3, 9.1, 9.2, 9.3_

- [x] 5. 修复 date_tools.py 缺失问题


  - 创建缺失的 date_tools.py 文件
  - 或删除 __init__.py 中的错误引用
  - 确保导入不会失败
  - _Requirements: 11.1, 11.2, 11.3_

- [x] 5.1 评估 date_tools.py 的必要性


  - 检查项目中是否有地方使用了 `DATE_TOOLS` 或相关函数
  - 如果没有使用，删除 `tableau_assistant/src/tools/__init__.py` 中的引用
  - 如果有使用，创建 `tableau_assistant/src/tools/date_tools.py` 文件
  - _Requirements: 11.1, 11.2_

- [x] 5.2 创建 date_tools.py（如果需要）

  - 创建 `tableau_assistant/src/tools/date_tools.py`
  - 使用 `@tool` 装饰器包装 DateCalculator 方法
  - 实现 `calculate_relative_date_range()`
  - 实现 `calculate_comparison_dates()`
  - 实现 `calculate_period_dates()`
  - 实现 `calculate_working_days_count()`
  - 实现 `format_date_for_vizql()`
  - 创建 `DATE_TOOLS` 列表
  - _Requirements: 11.1, 11.2_

- [x] 6. 清理重复代码


  - 删除或重构 query_utils.py 中的重复逻辑
  - 统一使用 DateParser
  - 保持 API 兼容性
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 6.1 重构 query_utils.calculate_date_range()


  - 修改 `tableau_assistant/src/utils/query_utils.py` 中的 `calculate_date_range()` 函数
  - 使用 DateParser 替代内部逻辑
  - 保持函数签名不变（向后兼容）
  - 添加 deprecation 警告，建议使用 DateParser
  - _Requirements: 9.1, 9.2, 9.3_


- [ ] 6.2 删除重复的解析方法
  - 删除 `query_utils._parse_absolute_date()` 方法（DateParser 已实现）
  - 删除 `query_utils._format_date_output()` 方法（DateCalculator 已实现）
  - 更新所有调用这些方法的代码
  - _Requirements: 9.1, 9.2, 9.3_

- [x] 7. 添加日志和监控

  - 在 DateParser 中添加详细日志
  - 记录计算过程和性能指标
  - 便于调试和优化
  - _Requirements: 7.1, 7.2, 7.3, 10.1, 10.2_

- [x] 7.1 添加计算日志


  - 在 DateParser 中记录：
    - 输入的 TimeRange 格式
    - 使用的参考日期和来源
    - 计算方法（value/range/relative）
    - 计算结果（start_date, end_date）
    - 计算耗时
  - 使用 logger.debug 级别
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 7.2 添加性能监控（可选）

  - 记录计算时间
  - 记录缓存命中率（如果实现缓存）
  - 设置性能阈值告警
  - _Requirements: 10.1, 10.2_

- [ ] 8. 添加单元测试
  - 测试 TimeRange 模型扩展
  - 测试 Metadata.get_reference_date()
  - 测试 DateParser 核心功能
  - 测试 DateCalculator 新增方法
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [ ] 8.1 测试 Metadata.get_reference_date()
  - 创建 `tests/unit/models/test_metadata_date.py`
  - 测试单个日期字段场景
  - 测试多个日期字段场景
  - 测试用户指定字段场景
  - 测试无日期字段场景
  - _Requirements: 6.1, 6.2, 6.3, 12.1_

- [ ] 8.2 测试 DateParser 核心功能
  - 创建 `tests/unit/components/test_date_parser.py`
  - 测试绝对时间计算（value 格式）
  - 测试日期范围计算（start_date + end_date 格式）
  - 测试相对时间计算
  - 测试日期验证逻辑
  - 测试错误处理
  - _Requirements: 1.1, 1.2, 1.3, 3.1, 3.2, 3.3, 3.4, 4.1, 11.1, 12.2_

- [ ] 8.3 测试 DateFilterConverter 集成
  - 在 `tests/unit/components/test_date_filter_converter.py` 中添加测试
  - 测试使用 DateParser 后的功能
  - 测试各种 TimeRange 格式
  - 测试参考日期选择
  - 测试生成的 VizQL 筛选器
  - _Requirements: 9.1, 9.2, 9.3, 12.3_

- [ ]* 8.4 添加属性测试（可选）
  - 创建 `tests/property/test_date_parsing_properties.py`
  - 使用 Hypothesis 框架
  - 测试日期范围有效性属性
  - 测试相对时间计算一致性
  - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [ ] 9. 集成测试
  - 测试完整的日期解析流程
  - 测试 Understanding Agent 集成
  - 测试多日期字段场景
  - _Requirements: 12.5_

- [ ] 9.1 测试端到端日期解析流程
  - 创建 `tests/integration/test_date_parsing_e2e.py`
  - 测试从用户问题到 VizQL 筛选器的完整流程
  - 测试各种日期表达式
  - 测试多子问题场景
  - 测试错误处理和降级
  - _Requirements: 1.1, 1.2, 1.3, 12.5_

- [ ] 9.2 测试 Understanding Prompt 更新
  - 测试 LLM 是否输出标准化格式
  - 测试各种日期表达式的输出
  - 确保 LLM 正确理解语义并输出标准格式
  - _Requirements: 3.1, 3.2, 12.5_

- [ ] 10. 文档更新
  - 更新 API 文档
  - 添加使用示例
  - 更新架构图
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [ ] 10.1 更新组件文档
  - 创建 `docs/components/date_parser.md`
  - 文档化 DateParser 的使用方法
  - 添加代码示例
  - 说明在 Query Builder 阶段使用
  - 说明参考日期选择逻辑
  - _Requirements: 7.1, 7.2, 7.3_

- [ ] 10.2 更新 Metadata 文档
  - 更新 `Metadata` 模型的文档字符串
  - 文档化 `get_reference_date()` 方法
  - 添加使用示例
  - 说明多日期字段处理
  - _Requirements: 7.1, 7.2, 7.3_

- [ ] 10.3 更新架构文档
  - 更新日期处理流程图
  - 说明 LLM 输出标准格式 → Query Builder 计算具体日期
  - 说明组件之间的关系
  - _Requirements: 7.4, 7.5, 7.6_

- [ ] 11. 性能测试和优化（可选）
  - 测试日期计算性能
  - 评估是否需要缓存
  - 优化热点代码
  - _Requirements: 10.1, 10.2, 10.3_


- [x] 11.1 性能基准测试

  - 测试标准日期计算性能（目标 < 10ms）
  - 测试各种 TimeRange 格式的计算时间
  - 对比重构前后的性能
  - _Requirements: 10.1, 10.2_

- [ ] 11.2 评估缓存必要性（可选）


  - 分析是否需要缓存（代码计算很快）
  - 如果需要，实现简单的 LRU 缓存
  - 测试缓存效果
  - _Requirements: 10.3, 10.4_

- [ ] 12. 最终验证和部署
  - 运行所有测试
  - 性能基准测试
  - 代码审查
  - 灰度发布
  - _Requirements: ALL_

- [ ] 12.1 运行完整测试套件
  - 运行所有单元测试
  - 运行所有集成测试
  - 运行属性测试（如果实现）
  - 确保测试覆盖率 > 80%
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [ ] 12.2 性能基准测试
  - 测试标准日期解析性能（目标 < 10ms）
  - 测试复杂表达式解析性能（目标 < 50ms）
  - 测试缓存命中率（目标 > 80%）
  - 对比重构前后的性能
  - _Requirements: 10.1, 10.2, 10.3_

- [ ] 12.3 代码审查和清理
  - 代码审查所有修改
  - 清理调试代码和注释
  - 确保代码风格一致
  - 更新 CHANGELOG
  - _Requirements: ALL_

- [ ] 12.4 灰度发布
  - 在测试环境验证
  - 小范围用户测试
  - 监控错误率和性能
  - 全量发布
  - _Requirements: ALL_

## Implementation Notes

### 关键设计决策

1. **组件化而非工具化**：DateParser 作为组件而不是工具函数，便于状态管理和复用
2. **向后兼容**：所有新增字段都是可选的，不破坏现有代码
3. **智能参考日期**：支持多日期字段场景，优先使用用户提到的字段
4. **完整追溯**：记录解析过程的所有关键信息
5. **优雅降级**：解析失败不中断流程，自动回退

### 依赖关系

- Task 1 必须在 Task 2 之前完成（模型扩展 → DateParser 创建）
- Task 2 必须在 Task 4 之前完成（DateParser 创建 → Understanding Agent 集成）
- Task 3 可以与 Task 2 并行（DateCalculator 扩展独立）
- Task 5, 6, 7 可以在 Task 4 之后并行进行（修复和清理）
- Task 8, 9 在核心功能完成后进行（测试）
- Task 10, 11 可以与测试并行（文档和优化）
- Task 12 在所有任务完成后进行（最终验证）

### 风险和缓解

**风险1**：破坏现有功能
- 缓解：保持向后兼容，添加完整测试

**风险2**：性能下降
- 缓解：添加缓存，性能监控，基准测试

**风险3**：多日期字段逻辑复杂
- 缓解：详细的日志记录，完整的测试覆盖

### 预期收益

- ✅ 统一的日期解析入口
- ✅ 支持更复杂的日期表达式
- ✅ 完整的追溯信息
- ✅ 更好的错误处理
- ✅ 更高的代码质量
- ✅ 更容易维护和扩展
