# 实现计划

本文档定义了 VizQL API 升级的实现任务列表。每个任务都是可执行的代码变更，按照依赖关系组织。

## 任务分类说明

- **[新增]**: 全新功能，之前不存在
- **[改造]**: 现有功能需要修改以使用新 SDK
- **[保留]**: 现有功能不受影响，无需修改

## 任务列表

- [ ] 1. 安装依赖和配置环境 **[改造]**
  - 安装 vizql-data-service-py 包（新依赖）
  - 安装 tableauserverclient 包（新依赖）
  - 更新 requirements.txt
  - 配置环境变量
  - 验证 Tableau Cloud 连接
  - _需求: 1.6, 1.7, 10.1, 10.2, 10.3, 10.4_

- [ ] 2. 实现证书管理器 **[新增]**
  - 创建 tableau_assistant/src/utils/certificate_manager.py
  - 创建 CertificateManager 类
  - 实现 get_ssl_context 方法（返回配置好的 SSL 上下文）
  - 实现 fetch_tableau_cloud_cert 方法（调用 cert_manager 工具）
  - 实现 validate_certificate 方法（验证证书有效性）
  - 集成到现有的 cert_manager 模块
  - _需求: 10.6, 10.7_

- [ ]* 2.1 编写证书管理器单元测试
  - 测试证书获取功能
  - 测试证书验证功能
  - 测试 SSL 上下文创建
  - _需求: 9.1, 9.4_

- [ ] 3. 扩展数据模型支持表计算 **[新增]**

**重要说明**: 表计算是 Tableau 2025.1+ 的核心新功能，包含 10 种表计算类型。每种类型都有特定的配置和用途。

- [ ] 3.1 添加表计算枚举和基础类型
  - 在 vizql_types.py 中添加 TableCalcType 枚举（10 种类型）
  - 添加 TableCalcComputedAggregation 枚举（SUM, AVG, MIN, MAX）
  - 添加 SortDirection 枚举（如果尚未存在）
  - _需求: 15.3_

- [ ] 3.2 添加表计算辅助类型
  - 实现 TableCalcFieldReference 类（引用其他字段）
    - fieldCaption: str（必需）
    - function: Optional[FunctionEnum]
  - 实现 TableCalcCustomSort 类（自定义排序）
    - fieldCaption: str（必需）
    - function: FunctionEnum（必需）
    - direction: SortDirection（必需）
  - _需求: 15.7_

- [ ] 3.3 添加 TableCalcSpecification 基类
  - 创建 TableCalcSpecification 基类
  - 添加 tableCalcType: str（必需，鉴别器字段）
  - 添加 dimensions: List[TableCalcFieldReference]（必需）
  - 配置 Pydantic 鉴别器（discriminator="tableCalcType"）
  - _需求: 15.2_

- [ ] 3.4 实现 CUSTOM 表计算类型
  - 实现 CustomTableCalcSpecification（继承 TableCalcSpecification）
  - 添加 levelAddress: Optional[TableCalcFieldReference]
  - 添加 restartEvery: Optional[TableCalcFieldReference]
  - 添加 customSort: Optional[TableCalcCustomSort]
  - 用途：自定义表计算公式
  - _需求: 15.3_

- [ ] 3.5 实现 NESTED 表计算类型
  - 实现 NestedTableCalcSpecification（继承 TableCalcSpecification）
  - 添加 fieldCaption: str（必需）
  - 添加 levelAddress, restartEvery, customSort（同 CUSTOM）
  - 用途：嵌套表计算，引用其他表计算结果
  - _需求: 15.7_

- [ ] 3.6 实现 DIFFERENCE_FROM 系列表计算类型
  - 实现 DifferenceTableCalcSpecification（继承 TableCalcSpecification）
  - 添加 levelAddress: Optional[TableCalcFieldReference]
  - 添加 relativeTo: Literal["PREVIOUS", "NEXT", "FIRST", "LAST"]（默认 "PREVIOUS"）
  - 添加 customSort: Optional[TableCalcCustomSort]
  - 用途：计算差异（DIFFERENCE_FROM, PERCENT_DIFFERENCE_FROM, PERCENT_FROM）
  - 注意：三种类型共享同一个 Specification 类
  - _需求: 15.3_

- [ ] 3.7 实现 PERCENT_OF_TOTAL 表计算类型
  - 实现 PercentOfTotalTableCalcSpecification（继承 TableCalcSpecification）
  - 添加 levelAddress: Optional[TableCalcFieldReference]
  - 添加 customSort: Optional[TableCalcCustomSort]
  - 用途：计算占总数的百分比
  - _需求: 15.3_

- [ ] 3.8 实现 RANK 表计算类型
  - 实现 RankTableCalcSpecification（继承 TableCalcSpecification）
  - 添加 rankType: Literal["COMPETITION", "MODIFIED COMPETITION", "DENSE", "UNIQUE"]（默认 "COMPETITION"）
  - 添加 direction: Optional[SortDirection]
  - 用途：排名计算
  - _需求: 15.6_

- [ ] 3.9 实现 PERCENTILE 表计算类型
  - 实现 PercentileTableCalcSpecification（继承 TableCalcSpecification）
  - 添加 direction: Optional[SortDirection]
  - 用途：百分位数计算
  - _需求: 15.6_

- [ ] 3.10 实现 RUNNING_TOTAL 表计算类型
  - 实现 RunningTotalTableCalcSpecification（继承 TableCalcSpecification）
  - 添加 aggregation: Optional[TableCalcComputedAggregation]（默认 "SUM"）
  - 添加 restartEvery: Optional[TableCalcFieldReference]
  - 添加 customSort: Optional[TableCalcCustomSort]
  - 添加 secondaryTableCalculation: Optional[TableCalcSpecification]（支持二级表计算）
  - 用途：累计总计
  - _需求: 15.5_

- [ ] 3.11 实现 MOVING_CALCULATION 表计算类型
  - 实现 MovingTableCalcSpecification（继承 TableCalcSpecification）
  - 添加 aggregation: Optional[TableCalcComputedAggregation]（默认 "SUM"）
  - 添加 previous: int（默认 -2，向前查看的行数）
  - 添加 next: int（默认 0，向后查看的行数）
  - 添加 includeCurrent: bool（默认 True，是否包含当前行）
  - 添加 fillInNull: bool（默认 False，是否填充空值）
  - 添加 customSort: Optional[TableCalcCustomSort]
  - 添加 secondaryTableCalculation: Optional[TableCalcSpecification]
  - 用途：移动平均、移动总和等
  - _需求: 15.4_

- [ ] 3.12 添加 TableCalcField 模型
  - 在 vizql_types.py 中添加 TableCalcField 类（继承 FieldBase）
  - 添加 function: Optional[FunctionEnum]（可选的聚合函数）
  - 添加 calculation: Optional[str]（可选的计算公式）
  - 添加 tableCalculation: TableCalcSpecification（必需，主表计算）
  - 添加 nestedTableCalculations: Optional[List[TableCalcSpecification]]（可选，嵌套表计算）
  - 更新 VizQLField 联合类型，包含 TableCalcField
  - _需求: 1.4, 7.1, 15.1_

- [ ]* 3.13 编写表计算数据模型单元测试
  - 测试每种表计算类型的创建和验证
  - 测试鉴别器功能（确保正确路由到子类）
  - 测试序列化和反序列化
  - 测试嵌套表计算
  - 测试二级表计算（RUNNING_TOTAL, MOVING_CALCULATION）
  - _需求: 9.1, 9.3_

- [ ]* 3.14 编写表计算数据模型属性测试
  - **属性 1**: 查询对象序列化往返一致性（包含表计算）
  - **属性 2**: 字段类型多态性（包含 TableCalcField）
  - **属性 23**: 模型序列化往返一致性（表计算模型）
  - _需求: 1.3, 1.4, 7.4_

- [ ] 4. 实现 VizQLClient 客户端封装 **[新增]**

**说明**: 这是全新的客户端封装层，封装官方 vizql-data-service-py SDK，提供简化接口。

- [ ] 4.1 创建 VizQLClient 类
  - 创建 tableau_assistant/src/utils/vizql_client.py
  - 实现构造函数，接受 server_url、auth、site 和 verify_ssl
  - 集成 CertificateManager（自动获取和配置证书）
  - 创建 TableauServerClient 实例
  - 创建 VizQLDataServiceClient 实例（官方 SDK）
  - 实现上下文管理器（自动登录/登出）
  - _需求: 13.2, 13.6_

- [ ] 4.2 实现同步查询方法
  - 实现 query_sync 方法
  - 接受 datasource_luid 和 VizQLQuery 对象
  - 构建 QueryRequest 对象（SDK 模型）
  - 调用 SDK 的 query_datasource.sync
  - 解析和返回 QueryOutput
  - 添加日志记录
  - _需求: 4.1, 4.2, 4.3, 13.4_

- [ ] 4.3 实现异步查询方法
  - 实现 query_async 方法
  - 调用 SDK 的 query_datasource.asyncio
  - 支持并发查询（使用 asyncio.gather）
  - 实现批量查询方法 batch_query_async
  - _需求: 13.7_

- [ ] 4.4 实现元数据获取方法
  - 实现 read_metadata_sync 方法
  - 实现 read_metadata_async 方法
  - 接受 datasource_luid
  - 构建 ReadMetadataRequest 对象（SDK 模型）
  - 调用 SDK 的 read_metadata.sync/asyncio
  - 解析 MetadataOutput
  - _需求: 5.1, 5.2, 5.3_

- [ ] 4.5 实现 get_datasource_model 方法
  - 实现 get_datasource_model_sync 方法
  - 实现 get_datasource_model_async 方法
  - 调用 SDK 的 get_datasource_model 端点
  - 用于获取数据源结构信息
  - _需求: 1.1, 2.3_

- [ ] 4.6 实现 simple_request 健康检查方法
  - 实现 health_check 方法
  - 调用 SDK 的 simple_request 端点
  - 用于验证 API 连接
  - _需求: 1.1, 10.5_

- [ ]* 4.7 编写 VizQLClient 单元测试
  - 测试客户端初始化
  - 测试证书集成
  - 测试查询方法（同步和异步）
  - 测试元数据获取
  - 测试健康检查
  - 测试错误处理
  - _需求: 9.2, 9.4_

- [ ]* 4.8 编写 VizQLClient 属性测试
  - **属性 10**: 查询请求结构完整性
  - **属性 11**: 查询响应解析正确性
  - **属性 14**: 元数据请求结构完整性
  - **属性 15**: 元数据响应解析正确性
  - _需求: 4.2, 4.3, 5.2, 5.3_

- [ ] 5. 实现错误处理器
- [ ] 5.1 创建 ErrorHandler 类
  - 实现错误分类逻辑
  - 实现重试判断逻辑
  - 实现指数退避计算
  - _需求: 8.1, 8.4, 8.5_

- [ ] 5.2 实现错误响应模型
  - 创建 ErrorResponse 模型
  - 包含 error_type、error_code、message 等字段
  - _需求: 2.5, 7.5_

- [ ]* 5.3 编写错误处理器单元测试
  - 测试错误分类
  - 测试重试逻辑
  - 测试指数退避
  - _需求: 9.4_

- [ ]* 5.4 编写错误处理器属性测试
  - **属性 4**: 错误响应结构完整性
  - **属性 12**: 错误响应解析正确性
  - **属性 25**: API 错误解析正确性
  - **属性 26**: 重试逻辑指数退避
  - **属性 27**: 网络错误回退行为
  - **属性 30**: 速率限制重试逻辑
  - _需求: 2.5, 4.4, 8.1, 8.4, 8.5, 11.5_

- [ ] 6. 更新 QueryExecutor **[改造]**

**说明**: QueryExecutor 是现有组件，需要改造以使用新的 VizQLClient。保持现有接口不变，只更新内部实现。

- [ ] 6.1 重构 QueryExecutor 构造函数
  - 修改构造函数，接受 VizQLClient 实例
  - 移除旧的 HTTP 请求相关代码（query_vds 函数调用）
  - 保持其他参数不变（max_retries, retry_delay, timeout, metadata 等）
  - 向后兼容：如果未提供 VizQLClient，自动创建
  - _需求: 4.1_

- [ ] 6.2 更新 execute_query 方法
  - 替换 query_vds 调用为 VizQLClient.query_sync
  - 更新结果解析逻辑（适配 SDK 的 QueryOutput）
  - 保持现有接口不变（输入输出格式）
  - 保持性能监控逻辑
  - 保持日志记录
  - _需求: 4.3, 4.5_

- [ ] 6.3 更新 execute_subtask 方法
  - 确保与新的 VizQLClient 兼容
  - 保持现有功能不变
  - 测试 QueryBuilder 集成
  - _需求: 4.1_

- [ ] 6.4 更新 execute_multiple_queries 方法
  - 使用 VizQLClient 的批量查询功能
  - 考虑使用异步方法提高性能
  - 保持现有接口不变
  - _需求: 4.1_

- [ ] 6.5 更新错误处理逻辑
  - 集成 ErrorHandler
  - 适配 SDK 的错误类型（UnexpectedStatus 等）
  - 保持现有的错误分类（QueryErrorType）
  - 确保重试逻辑正常工作
  - _需求: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 6.6 移除旧的 API 调用代码
  - 移除 query_vds 函数的导入和调用
  - 移除 _build_url 方法（不再需要）
  - 清理不再使用的代码
  - _需求: 2.1, 2.2_

- [ ]* 6.7 更新 QueryExecutor 单元测试
  - 更新测试以使用 VizQLClient
  - 测试查询执行
  - 测试错误处理
  - 测试重试逻辑
  - 确保向后兼容性
  - _需求: 9.2, 9.4_

- [ ]* 6.8 编写 QueryExecutor 属性测试
  - **属性 13**: 查询选项支持
  - _需求: 4.5_

- [ ] 7. 更新 MetadataManager **[改造]**

**说明**: MetadataManager 是现有组件，需要改造以使用新的 VizQLClient。保持现有接口和缓存机制不变。

- [ ] 7.1 重构 MetadataManager 构造函数
  - 修改构造函数，接受 VizQLClient 实例
  - 移除旧的元数据获取代码（get_datasource_metadata 函数调用）
  - 保持 Runtime 和 StoreManager 不变
  - 向后兼容：如果未提供 VizQLClient，自动创建
  - _需求: 5.1_

- [ ] 7.2 更新 get_metadata_async 方法
  - 替换 get_datasource_metadata 调用为 VizQLClient.read_metadata_async
  - 调用 SDK 的 read_metadata 端点
  - 保持缓存逻辑不变（先检查缓存，未命中则调用 API）
  - 保持智能增强逻辑不变（维度层级推断）
  - _需求: 5.3, 5.4, 5.5_

- [ ] 7.3 实现元数据格式转换
  - 创建 _convert_sdk_metadata_to_internal 方法
  - 将 SDK 的 FieldMetadata 转换为内部 FieldMetadata 模型
  - 映射字段：
    - fieldName → name
    - fieldCaption → fieldCaption
    - dataType → dataType
    - defaultAggregation → aggregation
    - columnClass → 推断 role（COLUMN/CALCULATION → dimension/measure）
  - 提取参数信息（从 extraData.parameters）
  - 保持向后兼容
  - _需求: 5.4, 5.5_

- [ ] 7.4 更新 _convert_to_metadata_model 方法
  - 适配新的元数据格式
  - 确保与现有 Metadata 模型兼容
  - 保持维度层级集成不变
  - _需求: 5.3_

- [ ] 7.5 移除旧的 API 调用代码
  - 移除 get_datasource_metadata 函数的导入和调用
  - 移除 get_data_dictionary_async 的导入（如果有）
  - 清理不再使用的代码
  - _需求: 2.1, 2.2_

- [ ]* 7.6 更新 MetadataManager 单元测试
  - 更新测试以使用 VizQLClient
  - 测试元数据获取
  - 测试格式转换
  - 测试缓存机制
  - 测试维度层级集成
  - _需求: 9.1_

- [ ]* 7.7 编写 MetadataManager 属性测试
  - **属性 16**: 字段元数据提取完整性
  - **属性 17**: 参数提取正确性
  - **属性 28**: 元数据缓存 TTL 一致性
  - _需求: 5.4, 5.5, 11.1_

- [ ] 8. 更新 QueryBuilder 支持表计算 **[新增功能]**

**说明**: QueryBuilder 是现有组件，需要添加表计算支持。这是全新的功能，之前不存在。

- [ ] 8.1 添加表计算字段构建基础方法
  - 实现 build_table_calc_field 方法（基础方法）
  - 接受 field_caption, table_calc_type, dimensions 等参数
  - 返回 TableCalcField 对象
  - 添加参数验证
  - _需求: 15.1, 15.2_

- [ ] 8.2 实现 RUNNING_TOTAL 表计算构建
  - 实现 build_running_total_field 方法
  - 参数：field_caption, measure_field, dimensions, aggregation, restart_every
  - 用途：累计总计（如累计销售额）
  - 示例：计算每月累计销售额
  - _需求: 15.5_

- [ ] 8.3 实现 MOVING_CALCULATION 表计算构建
  - 实现 build_moving_calc_field 方法
  - 参数：field_caption, measure_field, dimensions, aggregation, previous, next, include_current
  - 用途：移动平均、移动总和
  - 示例：计算 3 个月移动平均销售额
  - _需求: 15.4_

- [ ] 8.4 实现 RANK 表计算构建
  - 实现 build_rank_field 方法
  - 参数：field_caption, measure_field, dimensions, rank_type, direction
  - 用途：排名（如销售额排名）
  - 示例：按销售额对产品排名
  - _需求: 15.6_

- [ ] 8.5 实现 PERCENT_OF_TOTAL 表计算构建
  - 实现 build_percent_of_total_field 方法
  - 参数：field_caption, measure_field, dimensions, level_address
  - 用途：占总数百分比
  - 示例：每个类别占总销售额的百分比
  - _需求: 15.3_

- [ ] 8.6 实现 DIFFERENCE_FROM 系列表计算构建
  - 实现 build_difference_from_field 方法
  - 参数：field_caption, measure_field, dimensions, relative_to, calc_type
  - 支持三种类型：DIFFERENCE_FROM, PERCENT_DIFFERENCE_FROM, PERCENT_FROM
  - 用途：计算差异（如与上月相比的增长）
  - 示例：计算每月销售额与上月的差异
  - _需求: 15.3_

- [ ] 8.7 实现 PERCENTILE 表计算构建
  - 实现 build_percentile_field 方法
  - 参数：field_caption, measure_field, dimensions, direction
  - 用途：百分位数计算
  - 示例：计算销售额的 90 分位数
  - _需求: 15.6_

- [ ] 8.8 实现 CUSTOM 和 NESTED 表计算构建
  - 实现 build_custom_table_calc_field 方法
  - 实现 build_nested_table_calc_field 方法
  - 用于高级自定义场景
  - _需求: 15.3, 15.7_

- [ ] 8.9 更新 build_query 方法
  - 支持 TableCalcField（已在 VizQLField 联合类型中）
  - 确保表计算字段能正确序列化
  - 保持向后兼容（现有字段类型不受影响）
  - _需求: 3.5_

- [ ] 8.10 添加表计算辅助方法
  - 实现 _create_table_calc_field_reference 方法
  - 实现 _create_table_calc_custom_sort 方法
  - 实现 _validate_table_calc_dimensions 方法
  - 用于简化表计算构建
  - _需求: 15.7_

- [ ] 8.11 添加表计算示例和文档
  - 在 QueryBuilder 类中添加详细的 docstring
  - 为每种表计算类型添加使用示例
  - 创建 examples/table_calculations.py 示例文件
  - 更新 README.md
  - _需求: 12.1, 12.3_

- [ ]* 8.12 编写 QueryBuilder 表计算单元测试
  - 测试每种表计算类型的构建
  - 测试参数验证
  - 测试边缘情况（如空 dimensions）
  - 测试嵌套表计算
  - 测试二级表计算
  - _需求: 9.2, 9.3_

- [ ]* 8.13 编写 QueryBuilder 属性测试
  - **属性 5**: 维度字段构建正确性
  - **属性 6**: 度量字段构建正确性
  - **属性 7**: 计算字段构建正确性
  - **属性 8**: 过滤器构建正确性
  - **属性 9**: 查询构建完整性（包含表计算）
  - _需求: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 9. 集成测试和验证
- [ ] 9.1 编写端到端集成测试
  - 测试完整的查询流程
  - 测试元数据获取流程
  - 测试表计算功能
  - _需求: 9.2_

- [ ] 9.2 编写性能测试
  - 测试查询响应时间
  - 测试并发查询性能
  - 测试缓存性能
  - _需求: 11.1, 11.2, 11.3_

- [ ]* 9.3 编写性能属性测试
  - **属性 29**: 查询结果缓存一致性
  - _需求: 11.2_

- [ ] 9.4 运行所有测试
  - 运行单元测试
  - 运行属性测试
  - 运行集成测试
  - 确保测试覆盖率 ≥ 80%
  - _需求: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 10. 文档和部署
- [ ] 10.1 更新 API 文档
  - 记录新的 API 端点
  - 记录表计算功能
  - 提供代码示例
  - _需求: 12.1, 12.2, 12.3_

- [ ] 10.2 创建迁移指南
  - 记录升级步骤
  - 提供故障排查指南
  - 记录已知限制
  - _需求: 12.4_

- [ ] 10.3 部署到生产环境
  - 更新依赖
  - 配置环境变量
  - 部署新代码
  - _需求: 10.1, 10.2, 10.3, 10.4_

- [ ] 10.4 监控和优化
  - 设置监控指标
  - 收集性能数据
  - 优化性能瓶颈
  - _需求: 11.1, 11.2, 11.3, 11.4, 11.5_

