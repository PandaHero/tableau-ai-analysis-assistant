# Implementation Plan

- [x] 1. 创建测试基础设施
  - [x] 1.1 创建 conftest.py 共享 fixtures
    - 创建 executor fixture (WorkflowExecutor)
    - 创建 printer fixture (WorkflowPrinter)
    - 创建 settings fixture (Settings)
    - 创建 check_env fixture (环境检查)
    - _Requirements: 1.1, 14.1_

  - [x] 1.2 Write property test for workflow executor creation
    - **Property 1: 简单聚合查询成功执行**
    - **Validates: Requirements 1.1, 1.2**

- [x] 2. 实现简单聚合测试
  - [x] 2.1 创建 test_e2e_simple_aggregation.py
    - 实现 test_sum_aggregation (SUM 聚合)
    - 实现 test_avg_aggregation (AVG 聚合)
    - 实现 test_count_aggregation (COUNT 聚合)
    - 使用 printer 打印真实结果
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 2.2 Write property test for aggregation type recognition
    - **Property 2: 聚合类型正确识别**
    - **Validates: Requirements 1.4, 1.5**

- [x] 3. 实现 COUNTD 测试
  - [x] 3.1 创建 test_e2e_countd.py
    - 实现 test_countd_distinct_customers
    - 实现 test_countd_distinct_products
    - 验证 COUNTD 聚合识别和执行
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.2 Write property test for COUNTD recognition
    - **Property 3: COUNTD 聚合识别**
    - **Validates: Requirements 2.1, 2.2**

- [ ] 4. Checkpoint - 确保基础聚合测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 实现 LOD 表达式测试
  - [x] 5.1 创建 test_e2e_lod.py
    - 实现 test_fixed_lod_first_purchase
    - 实现 test_fixed_lod_category_total
    - 实现 test_include_lod_avg_orders
    - 实现 test_exclude_lod_category_avg
    - 验证 Understanding Agent 识别 LOD 需求
    - 验证 QueryBuilder 生成正确的 LOD 表达式
    - _Requirements: 3.1, 3.2, 3.3, 19.1-19.5, 20.1-20.4, 21.1-21.4_

  - [x] 5.2 Write property test for LOD expression recognition
    - **Property 4: LOD 表达式识别**
    - **Validates: Requirements 3.1, 19.1, 19.2, 20.1, 21.1**

- [x] 6. 实现表计算测试
  - [x] 6.1 创建 test_e2e_table_calc.py
    - 实现 test_running_sum_monthly
    - 实现 test_running_sum_quarterly
    - 实现 test_rank_sales
    - 实现 test_rank_profit
    - 实现 test_moving_avg
    - 实现 test_yoy_growth
    - 实现 test_mom_growth
    - 实现 test_percent_of_total
    - _Requirements: 4.1, 4.2, 4.3, 22.1-22.4, 23.1-23.4, 24.1-24.4, 25.1-25.3_

  - [x] 6.2 Write property test for table calculation recognition
    - **Property 5: 表计算识别**
    - **Validates: Requirements 4.1, 4.2, 22.1, 23.1, 24.1**

- [ ] 7. Checkpoint - 确保高级计算测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. 实现日期筛选测试
  - [x] 8.1 创建 test_e2e_date_filter.py - 绝对日期
    - 实现 test_absolute_year_filter
    - 实现 test_absolute_month_filter
    - 实现 test_absolute_date_range
    - 实现 test_absolute_quarter_filter
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 26.1-26.4_

  - [x] 8.2 实现相对日期筛选测试
    - 实现 test_current_month
    - 实现 test_last_month
    - 实现 test_last_n_months
    - 实现 test_year_to_date
    - 实现 test_current_week
    - 实现 test_last_week
    - 实现 test_last_n_days
    - 实现 test_today_yesterday
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 27.1-27.4, 28.1-28.5_

  - [x] 8.3 实现复合时间筛选测试
    - 实现 test_year_and_week
    - 实现 test_multi_year_quarter
    - 实现 test_weekday_weekend
    - _Requirements: 29.1-29.4_

  - [x] 8.4 Write property test for date filter recognition
    - **Property 6: 绝对日期筛选识别**
    - **Property 7: 相对日期筛选识别**
    - **Validates: Requirements 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4**

- [x] 9. 实现多维度测试
  - [x] 9.1 创建 test_e2e_multi_dimension.py
    - 实现 test_two_dimensions
    - 实现 test_multiple_measures
    - 实现 test_multi_dimension_multi_measure
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 9.2 Write property test for multi-dimension recognition
    - **Property 8: 多维度多度量识别**
    - **Validates: Requirements 7.1, 7.2**

- [ ] 10. Checkpoint - 确保筛选和多维度测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. 实现路由测试
  - [x] 11.1 创建 test_e2e_routing.py
    - 实现 test_non_analysis_greeting
    - 实现 test_non_analysis_help
    - 实现 test_non_analysis_bye
    - 验证 is_analysis_question=False 时直接路由到 END
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 11.2 Write property test for non-analysis routing
    - **Property 9: 非分析类问题路由**
    - **Validates: Requirements 8.1, 8.2, 8.3**

- [x] 12. 实现重规划测试
  - [x] 12.1 创建 test_e2e_replanning.py
    - 实现 test_replanner_returns_decision
    - 实现 test_replan_when_incomplete
    - 实现 test_no_replan_when_complete
    - 实现 test_max_replan_rounds_limit
    - 实现 test_replan_routing_to_understanding
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 12.2 Write property test for replanning decision
    - **Property 10: 重规划决策正确性**
    - **Property 11: 重规划路由正确性**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5**

- [x] 13. 实现流式执行测试
  - [x] 13.1 创建 test_e2e_streaming.py
    - 实现 test_stream_node_start_events
    - 实现 test_stream_node_complete_events
    - 实现 test_stream_token_events
    - 实现 test_stream_complete_event
    - 实现 test_stream_error_event
    - 使用 printer.print_event() 打印流式输出
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 13.2 Write property test for streaming events
    - **Property 12: 流式执行事件完整性**
    - **Validates: Requirements 10.1, 10.2, 10.4**

- [ ] 14. Checkpoint - 确保路由和流式测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. 实现错误处理测试
  - [x] 15.1 创建 test_e2e_error_handling.py
    - 实现 test_vizql_api_error
    - 实现 test_field_mapping_error
    - 实现 test_workflow_exception
    - 实现 test_empty_query_result
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 15.2 Write property test for error handling
    - **Property 13: 错误处理正确性**
    - **Property 14: 洞察生成正确性**
    - **Validates: Requirements 11.1, 11.2, 11.3, 1.3, 11.4**

- [x] 16. 实现完整循环流程测试
  - [x] 16.1 创建 test_e2e_full_cycle.py
    - 实现 test_full_workflow_cycle
    - 实现 test_multi_round_analysis
    - 实现 test_insights_accumulation
    - 验证 Understanding → FieldMapper → QueryBuilder → Execute → Insight → Replanner 完整流程
    - 验证多轮分析中 all_insights 正确累积
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 31.1, 31.2, 31.3, 31.4_

  - [x] 16.2 Write property test for insights accumulation
    - **Property 15: 洞察累积正确性**
    - **Validates: Requirements 15.4, 31.1, 31.2**

- [ ] 17. Checkpoint - 确保完整循环测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 18. 实现维度下钻测试
  - [x] 18.1 创建 test_e2e_dimension_drilldown.py
    - 实现 test_geo_drilldown_region_to_province
    - 实现 test_geo_drilldown_province_to_city
    - 实现 test_time_drilldown_year_to_quarter
    - 实现 test_time_drilldown_quarter_to_month
    - 实现 test_product_drilldown_category_to_subcategory
    - 验证 Replanner LLM 基于维度层级选择下钻维度
    - 使用流式输出打印完整的多轮下钻过程
    - _Requirements: 12.1, 12.2, 12.3, 16.1-16.5, 17.1-17.5, 18.1-18.5_

  - [x] 18.2 Write property test for dimension drilldown
    - **Property 18: 维度下钻决策正确性**
    - **Validates: Requirements 12.2, 16.2, 17.2, 18.2**

- [x] 19. 实现洞察与查询联动测试
  - [x] 19.1 创建 test_e2e_insight_query_linkage.py
    - 实现 test_insight_driven_drilldown
    - 实现 test_anomaly_driven_analysis
    - 实现 test_pareto_driven_top_n
    - 实现 test_trend_driven_analysis
    - 验证洞察如何驱动后续查询优化
    - _Requirements: 30.1, 30.2, 30.3, 30.4, 32.1, 32.2, 32.3, 32.4_

- [ ] 20. Checkpoint - 确保下钻和联动测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 21. 实现持久化测试
  - [x] 21.1 创建 test_e2e_persistence.py
    - 实现 test_sqlite_checkpointer_creation
    - 实现 test_workflow_state_persistence
    - 实现 test_session_restore
    - _Requirements: 13.1, 13.2, 13.3_

  - [x] 21.2 Write property test for SQLite persistence
    - **Property 16: SQLite Checkpointer 持久化**
    - **Validates: Requirements 13.1, 13.2**

- [x] 22. 实现性能测试
  - [x] 22.1 创建 test_e2e_performance.py
    - 实现 test_simple_query_performance
    - 实现 test_complex_query_performance
    - 实现 test_replan_round_performance
    - 验证执行时间在可接受范围内
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 22.2 Write property test for performance baseline
    - **Property 17: 性能基准**
    - **Validates: Requirements 14.1**

- [ ] 23. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.
