# 查询执行器增强需求文档

## 简介

本文档定义了查询执行器（QueryExecutor）的增强需求。查询执行器是Tableau AI分析助手的核心组件，负责执行VizQL查询并返回结果数据。当前的查询执行器已经具备基本功能，但需要进一步完善以支持新的模块化QueryBuilder、提供更好的错误处理、性能监控和批量执行能力。

## 术语表

- **QueryExecutor**: 查询执行器，负责执行VizQL查询并返回结果数据
- **VizQLQuery**: Tableau的可视化查询语言查询对象
- **QuerySubTask**: 查询子任务对象，包含意图信息（维度、度量、筛选器等）
- **QueryBuilder**: 查询构建器，将QuerySubTask转换为VizQLQuery
- **Metadata**: 元数据对象，包含数据源的字段信息
- **TableauAPI**: Tableau API客户端，用于与Tableau服务器通信
- **Performance Metrics**: 性能指标，包括执行时间、返回行数等

## 需求

### 需求 1: 支持多种查询输入格式

**用户故事**: 作为开发者，我希望查询执行器能够接受多种输入格式，以便在不同场景下灵活使用。

#### 验收标准

1. WHEN 提供VizQLQuery对象时，THE QueryExecutor SHALL 直接执行该查询并返回结果
2. WHEN 提供QuerySubTask对象时，THE QueryExecutor SHALL 使用QueryBuilder构建VizQLQuery后执行
3. WHEN 提供字典格式的查询时，THE QueryExecutor SHALL 将其转换为VizQLQuery后执行
4. THE QueryExecutor SHALL 在所有输入格式下返回统一的结果格式
5. IF 输入格式无效，THEN THE QueryExecutor SHALL 抛出清晰的错误信息

### 需求 2: 集成模块化QueryBuilder

**用户故事**: 作为开发者，我希望查询执行器能够与新的模块化QueryBuilder无缝集成，以便利用其增强的查询构建能力。

#### 验收标准

1. THE QueryExecutor SHALL 在初始化时接受Metadata对象作为可选参数
2. WHEN Metadata对象提供时，THE QueryExecutor SHALL 自动创建QueryBuilder实例
3. THE QueryExecutor SHALL 提供execute_subtask方法来执行QuerySubTask
4. THE QueryExecutor SHALL 在execute_subtask方法中使用QueryBuilder构建查询
5. THE QueryExecutor SHALL 记录查询构建时间作为性能指标的一部分

### 需求 3: 增强性能监控

**用户故事**: 作为开发者和运维人员，我希望查询执行器能够提供详细的性能指标，以便监控和优化查询性能。

#### 验收标准

1. THE QueryExecutor SHALL 记录每次查询的执行时间（秒）
2. THE QueryExecutor SHALL 记录每次查询返回的数据行数
3. THE QueryExecutor SHALL 记录每次查询的字段数量
4. THE QueryExecutor SHALL 记录每次查询的筛选器数量
5. WHEN 执行QuerySubTask时，THE QueryExecutor SHALL 额外记录查询构建时间
6. THE QueryExecutor SHALL 在查询结果中包含performance字段，包含所有性能指标
7. THE QueryExecutor SHALL 在日志中输出性能指标摘要

### 需求 4: 支持批量查询执行

**用户故事**: 作为开发者，我希望能够批量执行多个查询子任务，以便提高处理效率并获得统一的结果格式。

#### 验收标准

1. THE QueryExecutor SHALL 提供execute_multiple_subtasks方法接受QuerySubTask列表
2. THE QueryExecutor SHALL 按顺序执行列表中的每个子任务
3. THE QueryExecutor SHALL 为每个子任务返回独立的结果对象
4. WHEN 某个子任务执行失败时，THE QueryExecutor SHALL 继续执行剩余子任务
5. THE QueryExecutor SHALL 在每个结果对象中标记成功或失败状态
6. IF 子任务执行失败，THEN THE QueryExecutor SHALL 在结果对象中包含错误信息
7. THE QueryExecutor SHALL 记录批量执行的总时间和成功率
8. THE QueryExecutor SHALL 在日志中输出批量执行的进度信息

### 需求 5: 改进错误处理和日志

**用户故事**: 作为开发者，我希望查询执行器能够提供清晰的错误信息和详细的日志，以便快速定位和解决问题。

#### 验收标准

1. THE QueryExecutor SHALL 在开始执行查询时记录INFO级别日志
2. THE QueryExecutor SHALL 在查询成功时记录包含性能指标的INFO级别日志
3. THE QueryExecutor SHALL 在查询失败时记录包含错误详情的ERROR级别日志
4. THE QueryExecutor SHALL 在所有日志中包含查询的关键信息（字段数、筛选器数等）
5. WHEN 执行QuerySubTask时，THE QueryExecutor SHALL 在日志中包含子任务ID和问题文本
6. IF 查询执行失败，THEN THE QueryExecutor SHALL 抛出包含原始错误信息的异常
7. THE QueryExecutor SHALL 在异常信息中包含足够的上下文帮助调试

### 需求 6: 提供便捷的工厂方法

**用户故事**: 作为开发者，我希望有便捷的方法来创建配置完整的QueryExecutor实例，以减少重复代码。

#### 验收标准

1. THE QueryExecutor SHALL 提供create_with_metadata类方法
2. THE create_with_metadata方法 SHALL 接受TableauAPI和MetadataManager作为参数
3. WHEN MetadataManager提供时，THE create_with_metadata方法 SHALL 自动获取Metadata
4. THE create_with_metadata方法 SHALL 返回完全配置的QueryExecutor实例
5. THE 返回的QueryExecutor实例 SHALL 包含QueryBuilder（如果Metadata可用）

### 需求 7: 结果格式标准化

**用户故事**: 作为开发者，我希望查询执行器返回的结果格式统一且包含完整信息，以便后续处理。

#### 验收标准

1. THE QueryExecutor SHALL 返回包含data字段的字典对象
2. THE QueryExecutor SHALL 返回包含metadata字段的字典对象
3. THE QueryExecutor SHALL 返回包含performance字段的字典对象
4. WHEN 执行QuerySubTask时，THE QueryExecutor SHALL 在结果中包含subtask_info字段
5. THE subtask_info字段 SHALL 包含question_id、question_text和task_type
6. THE performance字段 SHALL 包含execution_time、row_count、fields_count和filters_count
7. WHEN 执行QuerySubTask时，THE performance字段 SHALL 额外包含build_time和total_time

## 非功能性需求

### 性能要求

1. THE QueryExecutor SHALL 在记录性能指标时产生的额外开销不超过1%
2. THE QueryExecutor SHALL 支持并发执行多个查询（通过异步方法）

### 兼容性要求

1. THE QueryExecutor SHALL 保持与现有代码的向后兼容性
2. THE QueryExecutor SHALL 支持Python 3.8及以上版本

### 可维护性要求

1. THE QueryExecutor SHALL 包含完整的类型注解
2. THE QueryExecutor SHALL 包含详细的docstring文档
3. THE QueryExecutor SHALL 遵循单一职责原则

## 约束条件

1. 必须使用异步编程模式（async/await）
2. 必须使用Python标准库的logging模块进行日志记录
3. 必须与现有的TableauAPI接口兼容
4. 必须与现有的数据模型（VizQLQuery、QuerySubTask等）兼容

## 依赖关系

1. 依赖TableauAPI组件执行实际的查询
2. 依赖QueryBuilder组件构建VizQL查询
3. 依赖Metadata模型提供字段信息
4. 依赖VizQLQuery和QuerySubTask数据模型

## 优先级

1. **高优先级**: 需求1（多种输入格式）、需求2（集成QueryBuilder）、需求3（性能监控）
2. **中优先级**: 需求4（批量执行）、需求5（错误处理）
3. **低优先级**: 需求6（工厂方法）、需求7（结果格式标准化）
