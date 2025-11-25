# Requirements Document

## Introduction

当前的查询构建器（QueryBuilder）将所有功能集中在一个文件中，包括元数据查询、筛选器构建、日期处理等多个职责，导致代码臃肿（近1000行）、难以维护。同时，元数据缺乏标准的数据模型，以字典形式传递，缺少类型安全和验证。

本需求旨在：
1. 将查询构建器模块化，拆分成职责清晰的独立模块
2. 创建标准的元数据数据模型（Pydantic），提供类型安全和验证
3. 由MetadataManager统一管理元数据模型，缓存到Store
4. QueryBuilder负责将Intent模型转换为VizQL模型

关键设计原则：
- 任务规划Agent输出Intent模型（DimensionIntent、MeasureIntent、DateFilterIntent等）
- QueryBuilder负责将Intent模型转换为VizQL模型（BasicField、FunctionField、VizQLFilter等）
- 创建Metadata Pydantic模型，替代字典格式
- MetadataManager负责元数据模型的创建、缓存和查询
- QueryBuilder接收Metadata模型对象和Intent模型，输出VizQL模型
- 不需要向后兼容，直接使用最新设计
- 每个模块职责单一，便于单元测试

## Glossary

- **QueryBuilder**: 查询构建器，负责将Intent模型转换为VizQL模型
- **IntentConverter**: Intent转换器，负责将各种Intent转换为对应的VizQL对象
- **FilterConverter**: 筛选器转换器，负责将FilterIntent转换为VizQLFilter
- **DateFilterConverter**: 日期筛选转换器，负责将DateFilterIntent转换为VizQL日期筛选器
- **Metadata**: 元数据Pydantic模型，包含数据源的所有字段信息
- **FieldMetadata**: 字段元数据Pydantic模型，包含单个字段的详细信息
- **Intent模型**: 中间层模型（DimensionIntent、MeasureIntent、DateFieldIntent、DateFilterIntent、FilterIntent、TopNIntent）
- **VizQLFilter**: VizQL筛选器类型（SET、TOP、MATCH、QUANTITATIVE_NUMERICAL、QUANTITATIVE_DATE、DATE）
- **VizQLField**: VizQL字段类型（BasicField、FunctionField、CalculationField）
- **MetadataManager**: 元数据管理器，负责从Tableau API获取元数据并转换为Metadata模型
- **StoreManager**: Store管理器，负责缓存管理（已存在）

## Requirements

### Requirement 1: 模块化架构设计

**User Story:** 作为开发者，我希望查询构建器采用模块化架构，以便每个模块职责清晰、易于维护和测试

#### Acceptance Criteria

1. WHEN 重构查询构建器时，THE System SHALL 将功能拆分为独立的模块文件
2. WHEN 每个模块被创建时，THE System SHALL 确保模块具有单一职责
3. WHEN 模块之间需要交互时，THE System SHALL 通过清晰的接口进行通信
4. WHEN 查看代码结构时，THE System SHALL 提供清晰的目录组织结构

### Requirement 2: Intent转换器模块

**User Story:** 作为开发者，我希望有独立的Intent转换器模块，以便将Intent模型转换为VizQL模型

#### Acceptance Criteria

1. WHEN 初始化IntentConverter时，THE IntentConverter SHALL 接收Metadata模型对象作为参数
2. WHEN 转换DimensionIntent时，THE IntentConverter SHALL 根据aggregation字段决定生成BasicField或FunctionField
3. WHEN 转换MeasureIntent时，THE IntentConverter SHALL 生成FunctionField并设置对应的聚合函数
4. WHEN 转换DateFieldIntent时，THE IntentConverter SHALL 根据date_function字段决定生成BasicField或FunctionField
5. WHEN Intent包含sort_direction时，THE IntentConverter SHALL 在生成的VizQLField中设置sortDirection和sortPriority
6. WHEN 转换失败时，THE IntentConverter SHALL 抛出包含详细信息的异常

### Requirement 3: 日期筛选转换器模块

**User Story:** 作为开发者，我希望有独立的日期筛选转换器模块，以便将DateFilterIntent转换为VizQL日期筛选器

#### Acceptance Criteria

1. WHEN 初始化DateFilterConverter时，THE DateFilterConverter SHALL 接收Metadata模型对象、anchor_date和week_start_day作为参数
2. WHEN 转换DateFilterIntent时，THE DateFilterConverter SHALL 根据field_data_type选择处理策略
3. WHEN 字段类型为DATE或DATETIME且time_range.type为relative时，THE DateFilterConverter SHALL 生成RelativeDateFilter
4. WHEN 字段类型为DATE或DATETIME且time_range.type为absolute时，THE DateFilterConverter SHALL 生成QuantitativeDateFilter
5. WHEN 字段类型为STRING时，THE DateFilterConverter SHALL 从Metadata模型获取字段的valid_max_date
6. WHEN 字段类型为STRING时，THE DateFilterConverter SHALL 使用DateCalculator计算日期范围
7. WHEN 字段类型为STRING时，THE DateFilterConverter SHALL 检测日期格式并生成DATEPARSE计算字段
8. WHEN 字段类型为STRING时，THE DateFilterConverter SHALL 生成QuantitativeDateFilter
9. WHEN 检测日期格式时，THE DateFilterConverter SHALL 使用样本值匹配预定义的日期格式模式
10. WHEN 无法识别日期格式时，THE DateFilterConverter SHALL 抛出包含样本值的详细错误信息
11. WHEN time_range包含节假日信息时，THE DateFilterConverter SHALL 使用DateCalculator计算节假日日期范围

### Requirement 4: 筛选器转换器模块

**User Story:** 作为开发者，我希望有独立的筛选器转换器模块，以便将FilterIntent转换为VizQLFilter

#### Acceptance Criteria

1. WHEN 初始化FilterConverter时，THE FilterConverter SHALL 接收Metadata模型对象作为参数
2. WHEN 转换FilterIntent且filter_type为SET时，THE FilterConverter SHALL 生成SetFilter
3. WHEN 转换FilterIntent且filter_type为QUANTITATIVE时，THE FilterConverter SHALL 生成QuantitativeNumericalFilter
4. WHEN 转换FilterIntent且filter_type为MATCH时，THE FilterConverter SHALL 生成MatchFilter
5. WHEN 转换TopNIntent时，THE FilterConverter SHALL 生成TopNFilter
6. WHEN 转换失败时，THE FilterConverter SHALL 抛出包含详细信息的异常

### Requirement 5: 主查询构建器简化

**User Story:** 作为开发者，我希望主查询构建器类保持简洁，只负责协调各个转换器完成查询构建

#### Acceptance Criteria

1. WHEN 初始化QueryBuilder时，THE QueryBuilder SHALL 接收Metadata模型对象、anchor_date和week_start_day作为参数
2. WHEN 初始化QueryBuilder时，THE QueryBuilder SHALL 创建IntentConverter实例
3. WHEN 初始化QueryBuilder时，THE QueryBuilder SHALL 创建DateFilterConverter实例
4. WHEN 初始化QueryBuilder时，THE QueryBuilder SHALL 创建FilterConverter实例
5. WHEN 构建查询时，THE QueryBuilder SHALL 接收QuerySubTask对象
6. WHEN 构建查询时，THE QueryBuilder SHALL 使用IntentConverter转换dimension_intents、measure_intents和date_field_intents为VizQLField列表
7. WHEN 构建查询时，THE QueryBuilder SHALL 使用DateFilterConverter转换date_filter_intent为VizQL日期筛选器
8. WHEN 构建查询时，THE QueryBuilder SHALL 使用FilterConverter转换filter_intents和topn_intent为VizQLFilter列表
9. WHEN 构建查询时，THE QueryBuilder SHALL 组装最终的VizQLQuery对象
10. WHEN 构建失败时，THE QueryBuilder SHALL 记录错误并抛出异常

### Requirement 6: 代码组织结构

**User Story:** 作为开发者，我希望有清晰的目录结构，以便快速定位和理解各个模块

#### Acceptance Criteria

1. WHEN 创建数据模型时，THE System SHALL 在models目录下创建metadata.py文件
2. WHEN 创建数据模型时，THE System SHALL 在metadata.py中定义FieldMetadata和Metadata Pydantic模型
3. WHEN 创建数据模型时，THE System SHALL 保持vizql_types.py专注于VizQL查询语句的数据模型
4. WHEN 创建数据模型时，THE System SHALL 保持intent.py专注于Intent中间层模型
5. WHEN 创建模块文件时，THE System SHALL 将查询构建器模块放在components/query_builder目录下
6. WHEN 组织文件时，THE System SHALL 创建intent_converter.py用于Intent到VizQLField的转换
7. WHEN 组织文件时，THE System SHALL 创建date_filter_converter.py用于DateFilterIntent到VizQL日期筛选器的转换
8. WHEN 组织文件时，THE System SHALL 创建filter_converter.py用于FilterIntent到VizQLFilter的转换
9. WHEN 组织文件时，THE System SHALL 创建builder.py作为主QueryBuilder类
10. WHEN 组织文件时，THE System SHALL 创建__init__.py导出QueryBuilder类
11. WHEN 组织文件时，THE System SHALL 删除旧的query_builder.py文件

### Requirement 7: 辅助函数模块化

**User Story:** 作为开发者，我希望将辅助函数（如日期格式检测）独立出来，以便复用和测试

#### Acceptance Criteria

1. WHEN 创建辅助函数时，THE System SHALL 将日期格式检测逻辑放在date_filter_converter.py中
2. WHEN 创建辅助函数时，THE System SHALL 将日期格式模式定义为模块级常量
3. WHEN 使用辅助函数时，THE System SHALL 确保函数具有清晰的输入输出和错误处理
