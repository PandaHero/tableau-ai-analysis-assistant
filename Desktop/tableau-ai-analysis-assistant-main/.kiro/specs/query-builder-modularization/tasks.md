# Implementation Plan

本实现计划将需求和设计转换为具体的编码任务。任务按照依赖关系组织，确保每个任务都可以独立完成并测试。

## Task Breakdown

- [x] 1. 创建IntentConverter模块
  - 创建 `components/query_builder/` 目录
  - 创建 `intent_converter.py` 文件
  - 实现IntentConverter类，接收Metadata对象
  - 实现 `convert_dimension_intent` 方法，根据aggregation决定生成BasicField或FunctionField
  - 实现 `convert_measure_intent` 方法，生成FunctionField
  - 实现 `convert_date_field_intent` 方法，根据date_function决定生成BasicField或FunctionField
  - 处理排序信息（sortDirection和sortPriority）
  - 编写单元测试验证各种Intent的转换
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 2. 创建DateFilterConverter模块
  - 创建 `date_filter_converter.py` 文件
  - 实现DateFilterConverter类，接收Metadata对象、anchor_date和week_start_day
  - 实现 `convert` 方法，根据field_data_type选择处理策略
  - 实现 `_convert_native_date_field` 方法，处理DATE/DATETIME字段
  - 实现 `_convert_string_date_field` 方法，处理STRING类型日期字段
  - 实现 `detect_date_format` 方法，使用样本值匹配日期格式模式
  - 定义日期格式模式常量（DATE_FORMAT_PATTERNS）
  - 处理节假日日期计算（使用DateCalculator）
  - 生成DATEPARSE计算字段（使用create_dateparse_field辅助函数）
  - 编写单元测试验证各种场景（DATE类型、STRING类型、格式检测、节假日）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11_

- [x] 3. 创建FilterConverter模块
  - 创建 `filter_converter.py` 文件
  - 实现FilterConverter类，接收Metadata对象
  - 实现 `convert_filter_intent` 方法，根据filter_type生成对应的VizQLFilter
  - 处理SET类型筛选（生成SetFilter）
  - 处理QUANTITATIVE类型筛选（生成QuantitativeNumericalFilter）
  - 处理MATCH类型筛选（生成MatchFilter）
  - 实现 `convert_topn_intent` 方法，生成TopNFilter
  - 编写单元测试验证各种筛选器的转换
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 4. 创建QueryBuilder主类
  - 创建 `builder.py` 文件
  - 实现QueryBuilder类，接收Metadata对象、anchor_date和week_start_day
  - 在初始化时创建IntentConverter、DateFilterConverter和FilterConverter实例
  - 实现 `build_query` 方法，接收QuerySubTask并返回VizQLQuery对象
  - 使用IntentConverter转换dimension_intents、measure_intents和date_field_intents
  - 使用DateFilterConverter转换date_filter_intent
  - 使用FilterConverter转换filter_intents和topn_intent
  - 组装最终的VizQLQuery对象
  - 添加错误处理和日志记录
  - 编写单元测试和集成测试
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10_

- [x] 5. 创建query_builder模块导出
  - 创建 `components/query_builder/__init__.py` 文件
  - 导出QueryBuilder类
  - 确保外部代码可以通过 `from tableau_assistant.src.components.query_builder import QueryBuilder` 导入
  - _Requirements: 6.10_

- [x] 6. 删除旧的query_builder.py文件
  - 确认所有功能已迁移到新的模块化结构
  - 更新所有导入语句，从旧的query_builder.py改为新的query_builder模块
  - 删除 `components/query_builder.py` 文件
  - _Requirements: 6.11_

- [x] 7. 端到端测试和验证
  - 运行完整的测试套件，确保所有测试通过
  - 进行端到端功能测试，验证查询构建流程
  - 验证元数据获取、缓存、Intent转换、VizQL生成的完整流程
  - 修复发现的任何问题
  - _Requirements: All_
