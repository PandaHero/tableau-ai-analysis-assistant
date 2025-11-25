# 实现计划

- [x] 1. 改进TimeRange和RelativeType数据模型



  - 为RelativeType枚举添加英文注释说明每个值的含义
  - 改进TimeRange.relative_type字段的description
  - 改进TimeRange.range_n字段的description
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. 改进QuerySubQuestion数据模型



  - 创建DateFunction枚举（YEAR, QUARTER, MONTH, WEEK, DAY）
  - 修改date_field_functions字段类型为dict[str, DateFunction]
  - 改进date_field_functions字段的description（说明用于GROUP BY的时间粒度）
  - 改进mentioned_date_fields字段的description（说明用于时间分组）
  - 改进filter_date_field字段的description（说明用于时间范围筛选）
  - 改进mentioned_dimensions字段的description（说明包含所有维度）
  - 改进dimension_aggregations字段的description（添加通用示例，包含COUNTD/MAX/MIN）
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 3. 改进Understanding Prompt的分析引导



  - 在get_specific_domain_knowledge的Step 2中添加计数模式分析引导
  - 在get_specific_domain_knowledge的Step 4中改进日期字段分析引导（区分grouping和filtering）
  - 使用英文，通用规则，不包含具体示例
  - _Requirements: 2.9, 2.10_

- [x] 4. 实现Task Planner Agent的元数据格式化方法




  - 实现_format_metadata_by_category方法，按7个category分组
  - 修改plan_tasks方法，调用新的格式化方法
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 5. 改进Task Planner Prompt的映射规则



  - 在get_specific_domain_knowledge中更新映射规则（使用英文，通用规则）
  - 强调先匹配category，再匹配name
  - 说明COUNTD聚合优先选择细粒度字段
  - _Requirements: 3.4, 3.5_

- [x] 6. 修复Query Builder的日期计算公式生成



  - 根据DateFunction枚举生成正确的提取函数（YEAR/MONTH/DAY等）
  - 根据日期字段的dataType选择不同的处理方式：
    * STRING类型：使用DATEPARSE转换 + 提取函数
    * DATE/DATETIME类型：直接使用提取函数
  - 修改日期维度字段生成逻辑（date_field_intents → CalculationField）
  - 修改日期筛选生成逻辑（date_filter_intent → QuantitativeDateFilter）
  - 避免嵌套函数调用，不使用TRUNC_*函数
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 7. 修复Query Builder的排序优先级分配



  - 实现_assign_sort_priorities方法，为每个字段分配唯一的sortPriority
  - 度量字段优先级最高（值为0），维度字段递增（1, 2, 3...）
  - 添加_validate_sort_priorities验证方法
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 8. 运行集成测试验证修复效果



  - 运行test_complete_pipeline.py
  - 确认所有15个测试用例通过
  - 特别关注：date_filter_relative, date_dimension, counted_dimension, mixed_dimensions, diagnostic
