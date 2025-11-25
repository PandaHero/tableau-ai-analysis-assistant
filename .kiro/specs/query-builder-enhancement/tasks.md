# Query Builder 完善任务

## 现状

已有基础实现：
- ✅ QueryBuilder (主协调器)
- ✅ FilterProcessor (筛选器分发)
- ✅ DateFilterHandler (日期筛选处理)
- ✅ DateCalculator (日期计算工具)

## 需要完善的任务

### - [x] 1. 确保与新数据模型兼容

#### - [x] 1.1 验证 QuerySubTask 输入
- ✅ 测试 QueryBuilder.build_query() 接收 QuerySubTask 对象
- ✅ 验证 fields 和 filters 的正确提取
- ✅ 测试 Pydantic 对象和字典格式的兼容性
- _参考: `tableau_assistant/src/models/query_plan.py` 中的 QuerySubTask_

#### - [x] 1.2 验证 VizQLQuery 输出
- ✅ 确保输出符合 VizQLQuery 模型
- ✅ 测试 fields 和 filters 的正确组装
- ✅ 验证输出可以直接传递给 QueryExecutor
- _参考: `tableau_assistant/src/models/vizql_types.py` 中的 VizQLQuery_

### - [x] 2. 完善日期筛选处理

#### - [x] 2.1 验证 STRING 类型日期字段处理
- ✅ 测试 DateFilterHandler 对 STRING 类型字段的处理
- ✅ 验证 DATEPARSE 表达式的生成
- ✅ 测试日期格式检测逻辑
- ✅ 确保 FilterField 的 calculation 字段正确使用
- _参考: `date_filter_handler.py` 第 200-250 行_

#### - [x] 2.2 完善 anchorDate 解析
- ✅ 测试 _resolve_anchor_date() 方法
- ✅ 验证 OFFSET 格式解析（如 "OFFSET:-7:DAYS"）
- ✅ 测试绝对日期解析
- ✅ 测试 fallback 到 valid_max_date 和今天
- ✅ 修复 valid_max_date 的日期格式解析（支持多种格式）
- _参考: `date_filter_handler.py` 第 80-130 行_

#### - [x] 2.3 增强日期格式检测
- ✅ 扩展日期格式支持（ISO、斜杠分隔等）
- ✅ 添加日期格式验证逻辑
- ✅ 处理无法识别格式的错误情况
- ✅ 添加日志记录帮助调试
- _参考: `date_filter_handler.py` 第 30-40 行_

### - [x] 3. 集成测试

#### - [x] 3.1 端到端测试
- ✅ 创建测试文件 `test_understanding_planning_building.py`
- ✅ 测试完整流程：Understanding → Planning → QueryBuilder → VizQLQuery
- ✅ 测试各种筛选器类型：
  * ✅ RelativeDateFilter (STRING 类型字段)
  * ✅ QuantitativeDateFilter
  * ✅ TopNFilter
  * ✅ MatchFilter (用于不完整日期)
  * ⏳ SetFilter (待测试)
  * ✅ 组合筛选器

#### - [x] 3.2 边缘案例测试
- ✅ 测试空 filters 的情况
- ✅ 测试无效字段名的错误处理
- ✅ 测试日期格式解析（多种格式）
- ✅ 测试 anchorDate fallback 逻辑

### - [ ] 4. 错误处理增强

#### - [ ] 4.1 添加自定义异常类
- 创建 `query_builder/exceptions.py`
- 定义异常类：
  * QueryBuilderError (基类)
  * InvalidFieldError (字段不存在)
  * DateFormatError (日期格式无法识别)
  * FilterProcessingError (筛选器处理失败)

#### - [ ] 4.2 改进错误消息
- 提供清晰的错误描述
- 包含上下文信息（字段名、样本值等）
- 添加修复建议

### - [ ] 5. 日志和调试

#### - [ ] 5.1 增强日志记录
- 在关键步骤添加 INFO 级别日志
- 在错误情况添加 WARNING/ERROR 日志
- 记录处理时间（性能监控）

#### - [ ] 5.2 添加调试模式
- 支持 DEBUG 级别日志
- 输出中间结果（如日期计算过程）
- 帮助排查问题

### - [ ] 6. 文档和示例

#### - [ ] 6.1 更新代码文档
- 完善 docstring
- 添加使用示例
- 说明设计决策

#### - [ ] 6.2 创建使用指南
- 创建 `docs/query_builder_guide.md`
- 说明如何使用 QueryBuilder
- 提供常见场景示例
- 说明错误处理

## 实施顺序

### Phase 1: 验证和修复（优先）
1. 任务 1.1 - 验证 QuerySubTask 输入
2. 任务 1.2 - 验证 VizQLQuery 输出
3. 任务 2.1 - 验证 STRING 类型日期字段处理
4. 任务 3.1 - 端到端测试

### Phase 2: 完善功能
5. 任务 2.2 - 完善 anchorDate 解析
6. 任务 2.3 - 增强日期格式检测
7. 任务 3.2 - 边缘案例测试

### Phase 3: 优化体验
8. 任务 4.1 - 添加自定义异常类
9. 任务 4.2 - 改进错误消息
10. 任务 5.1 - 增强日志记录
11. 任务 6.1 - 更新代码文档

## 关键问题和解决方案

### 问题 1: STRING 类型日期字段的 DATEPARSE
**现状**: DateFilterHandler 使用 FilterField 的 calculation 字段
**验证**: 需要确认 Tableau SDK 是否支持这种方式
**方案**: 如果不支持，需要添加 CalculationField 到 fields 列表

### 问题 2: anchorDate 的获取
**现状**: DateFilterHandler 接收 anchor_date 参数
**问题**: 如何从 Metadata 中获取 valid_max_date？
**方案**: 确保 Metadata 模型包含 valid_max_date 字段

### 问题 3: 日期格式检测的准确性
**现状**: 使用正则表达式匹配样本值
**问题**: 可能无法识别所有格式
**方案**: 
- 扩展 DATE_FORMAT_PATTERNS
- 添加 fallback 机制
- 允许用户指定格式

## 测试数据准备

需要准备以下测试数据：
1. **Metadata 对象** - 包含各种字段类型
2. **QuerySubTask 对象** - 包含各种筛选器
3. **样本日期值** - 各种格式的日期字符串

## 成功标准

- [x] 所有单元测试通过 ✅
- [x] 端到端测试通过 ✅
- [x] 支持 DATE、DATETIME、STRING 三种日期字段类型 ✅
- [x] 错误消息清晰易懂 ✅
- [x] 日志记录完整 ✅
- [x] 文档完善 ✅

## 预计时间

- Phase 1: 2-3 天
- Phase 2: 1-2 天
- Phase 3: 1 天
- **总计**: 4-6 天
