# 需求文档

## 简介

本文档概述了将 Tableau Assistant 从旧版 REST API 迁移到新的 VizQL Data Service API 的需求。VizQL Data Service 提供了一个现代化的无头 BI 接口，用于查询 Tableau 已发布的数据源，具有更好的性能、更完善的错误处理以及增强的查询功能，包括表计算、过滤器和参数。

VizQL Data Service 是 Tableau 2025.1+ 版本引入的新 API，提供了基于 OpenAPI 3.0.4 规范的标准化接口。该 API 支持同步和异步查询模式，并提供了官方的 Python SDK（vizql-data-service-py）用于简化集成。

## 可复用组件分析

项目中已存在以下可复用组件，迁移时应充分利用：

### 已有组件（100%复用）
1. **MetadataManager** (`tableau_assistant/src/components/metadata_manager.py`)
   - 元数据获取和缓存逻辑
   - 维度层级推断集成
   - 日期字段最大值查询
   - 可复用：缓存机制、增强逻辑、Store集成
   - **迁移方式**：封装为DeepAgents工具

2. **QueryExecutor** (`tableau_assistant/src/components/query_executor.py`)
   - 查询执行框架
   - 重试机制和错误处理
   - 性能监控
   - 可复用：重试逻辑、错误分类、性能指标收集
   - **迁移方式**：封装为DeepAgents工具

3. **QueryBuilder** (`tableau_assistant/src/components/query_builder/`)
   - Intent模型到VizQL查询的转换
   - 字段、过滤器、聚合的构建逻辑
   - 可复用：完整保留，仅需适配SDK模型输出
   - **迁移方式**：封装为DeepAgents工具

4. **VizQL类型定义** (`tableau_assistant/src/models/vizql_types.py`)
   - 完整的Pydantic v2模型
   - 字段类型（BasicField、FunctionField、CalculationField）
   - 过滤器类型（SetFilter、TopNFilter、RelativeDateFilter等）
   - 可复用：作为内部模型保留，需要转换器对接SDK模型

5. **Metadata模型** (`tableau_assistant/src/models/metadata.py`)
   - FieldMetadata和Metadata模型
   - 字段查询方法
   - 日期字段识别
   - 可复用：完整保留，作为系统内部统一的元数据模型

6. **QueryPlan和Intent模型** (`tableau_assistant/src/models/query_plan.py`, `intent.py`)
   - QuerySubTask和Intent模型
   - 查询规划结构
   - 可复用：完整保留，无需修改

7. **配置管理** (`tableau_assistant/src/config/settings.py`)
   - 环境变量管理
   - Tableau配置
   - 可复用：添加SDK相关配置项

8. **工具函数** (`tableau_assistant/src/utils/tableau/`)
   - 认证工具（auth.py）
   - 元数据查询（metadata.py）
   - 可复用：认证逻辑，元数据查询需要适配SDK

9. **DeepAgents架构** (`tableau_assistant/src/deepagents/`)
   - 主Agent编排
   - 5个子代理（boost, understanding, planning, insight, replanner）
   - 自定义中间件
   - 可复用：完整保留，是迁移的基础架构

### 需要新增的组件
1. **SDK客户端包装器** - 封装官方SDK的VizQLDataServiceClient，集成到现有工具中
2. **模型转换器** - 在内部VizQL模型和SDK模型之间双向转换
3. **SDK元数据适配器** - 将SDK的MetadataOutput转换为内部Metadata模型
4. **VizQL中间件增强** - 扩展VizQLQueryMiddleware以支持SDK模式
5. **功能标志管理** - 支持新旧API切换的配置系统

## 术语表

- **VizQL Data Service**: 新的 Tableau API 服务，提供对已发布数据源的编程查询访问，基于 OpenAPI 3.0.4 规范
- **Tableau Assistant**: AI 驱动的助手系统，帮助用户通过自然语言查询分析 Tableau 数据
- **Data Source（数据源）**: 可通过 API 查询的已发布 Tableau 数据源
- **LUID**: Tableau 用于标识资源的本地唯一标识符
- **Field（字段）**: 已发布数据源中的数据列，可以是维度、度量或计算字段
- **Query Plan（查询计划）**: VizQL 查询的结构化表示，包括字段、过滤器和参数
- **Metadata（元数据）**: 关于数据源结构的信息，包括字段名称、数据类型和关系
- **PAT**: 用于 Tableau Cloud 身份验证的个人访问令牌
- **Python SDK**: VizQL Data Service 官方 Python 客户端库（vizql-data-service-py），基于 Pydantic v2
- **TableauServerClient**: Tableau Server Client Python 库，用于身份验证和会话管理
- **VizQLDataServiceClient**: VizQL Data Service Python SDK 的客户端类，封装 HTTP 请求
- **Pydantic v2**: Python 数据验证库，用于类型安全的数据模型定义
- **SSL Context**: SSL/TLS 安全上下文，用于配置证书验证和自定义 CA 证书

## 需求

### 需求 1

**用户故事:** 作为开发者，我想要理解新的 VizQL Data Service API 功能，以便有效规划迁移工作。

#### 验收标准

1. WHEN 审查系统文档时 THEN VizQL Data Service SHALL 提供四个主要端点：read-metadata、query-datasource、get-datasource-model 和 simple-request
2. WHEN 比较 API 功能时 THEN VizQL Data Service SHALL 支持高级功能，包括表计算、多种过滤器类型和参数传递
3. WHEN 分析查询结构时 THEN VizQL Data Service SHALL 接受包含 fields 数组、filters 数组和 parameters 数组的 Query 对象
4. WHEN 检查字段类型时 THEN VizQL Data Service SHALL 支持五种字段类型：DimensionField、MeasureField、CalculatedField、BinField 和 TableCalcField
5. WHEN 审查过滤器功能时 THEN VizQL Data Service SHALL 支持六种过滤器类型：QUANTITATIVE_DATE、QUANTITATIVE_NUMERICAL、SET、MATCH、DATE 和 TOP
6. WHEN 检查 Python SDK 时 THEN 系统 SHALL 使用官方 vizql-data-service-py 包，该包基于 Pydantic v2 并通过 datamodel-codegen 从 OpenAPI 规范生成
7. WHEN 检查身份验证方式时 THEN 系统 SHALL 支持三种身份验证方法：JWT、PAT 和用户名密码（仅限本地部署）
8. WHEN 检查 API 版本时 THEN 系统 SHALL 使用 /vizql-data-service/v1 作为基础路径，并支持 Tableau 2025.1+ 版本

### 需求 2

**用户故事:** 作为系统架构师，我想要将现有功能映射到新 API，以便在迁移过程中确保功能对等。

#### 验收标准

1. WHEN 映射元数据检索时 THEN 系统 SHALL 使用 read-metadata 端点替换现有的元数据获取逻辑
2. WHEN 映射查询执行时 THEN 系统 SHALL 使用 query-datasource 端点替换现有的查询执行逻辑
3. WHEN 映射数据源发现时 THEN 系统 SHALL 使用 get-datasource-model 端点检索数据源结构信息
4. WHEN 映射身份验证时 THEN 系统 SHALL 继续在新 API 端点中使用 PAT 身份验证
5. WHEN 映射错误处理时 THEN 系统 SHALL 适配新的 TableauError 响应格式，包含 errorCode、message 和 debug 字段

### 需求 3

**用户故事:** 作为开发者，我想要更新 QueryBuilder 组件，以便生成与新 VizQL Data Service API 兼容的查询。

#### 验收标准

1. WHEN 构建维度字段时 THEN QueryBuilder SHALL 生成包含 fieldCaption、可选 fieldAlias 和可选排序参数的 DimensionField 对象
2. WHEN 构建度量字段时 THEN QueryBuilder SHALL 生成包含 fieldCaption、function（聚合）和可选格式化参数的 MeasureField 对象
3. WHEN 构建计算字段时 THEN QueryBuilder SHALL 生成包含 fieldCaption 和 calculation 公式的 CalculatedField 对象
4. WHEN 构建过滤器时 THEN QueryBuilder SHALL 根据过滤器类型生成适当的过滤器对象，包含必需的 field 和 filterType 属性
5. WHEN 构建查询时 THEN QueryBuilder SHALL 构造包含 fields 数组以及可选 filters 和 parameters 数组的 Query 对象

### 需求 4

**用户故事:** 作为开发者，我想要更新 QueryExecutor 组件，以便使用新的 VizQL Data Service API 执行查询。

#### 验收标准

1. WHEN 执行查询时 THEN QueryExecutor SHALL 向 /vizql-data-service/v1/query-datasource 端点发送 POST 请求
2. WHEN 准备请求时 THEN QueryExecutor SHALL 在请求体中包含 datasourceLuid、query 对象和可选的连接凭据
3. WHEN 接收响应时 THEN QueryExecutor SHALL 解析包含 data 数组和可选 extraData 的 QueryOutput 对象
4. WHEN 处理错误时 THEN QueryExecutor SHALL 解析 TableauError 响应并提取 errorCode、message 和 debug 信息
5. WHEN 配置请求时 THEN QueryExecutor SHALL 支持可选的 QueryDatasourceOptions，包括 disaggregate 和 returnFormat 设置

### 需求 5

**用户故事:** 作为开发者，我想要更新 MetadataManager 组件，以便使用新的 VizQL Data Service API 检索元数据。

#### 验收标准

1. WHEN 获取元数据时 THEN MetadataManager SHALL 向 /vizql-data-service/v1/read-metadata 端点发送 POST 请求
2. WHEN 准备元数据请求时 THEN MetadataManager SHALL 在 ReadMetadataRequest 请求体中包含 datasourceLuid
3. WHEN 接收元数据时 THEN MetadataManager SHALL 解析包含 FieldMetadata 对象数组的 MetadataOutput
4. WHEN 处理字段元数据时 THEN MetadataManager SHALL 提取 fieldName、fieldCaption、dataType、defaultAggregation、columnClass 和可选的 formula
5. WHEN 处理参数时 THEN MetadataManager SHALL 从 extraData.parameters 字段提取参数信息

### 需求 6

**用户故事:** 作为开发者，我想要实现向后兼容性，以便可以增量执行迁移而不破坏现有功能。

#### 验收标准

1. WHEN 迁移组件时 THEN 系统 SHALL 支持功能标志在旧版 API 和新 VizQL Data Service 之间切换
2. WHEN 使用旧版模式时 THEN 系统 SHALL 继续使用现有的 API 端点和数据结构
3. WHEN 使用新 API 模式时 THEN 系统 SHALL 使用 VizQL Data Service 端点和数据结构
4. WHEN 切换模式时 THEN 系统 SHALL 为下游组件维护一致的输出格式
5. WHEN 两种模式都可用时 THEN 系统 SHALL 提供配置选项以选择首选的 API 版本

### 需求 7

**用户故事:** 作为开发者，我想要更新数据模型，以便它们表示新的 VizQL Data Service API 结构。

#### 验收标准

1. WHEN 定义字段模型时 THEN 系统 SHALL 为 DimensionField、MeasureField、CalculatedField、BinField 和 TableCalcField 创建 Pydantic 模型
2. WHEN 定义过滤器模型时 THEN 系统 SHALL 为所有六种过滤器类型创建具有适当鉴别器配置的 Pydantic 模型
3. WHEN 定义查询模型时 THEN 系统 SHALL 创建包含 fields、filters 和 parameters 数组的 Query 模型
4. WHEN 定义响应模型时 THEN 系统 SHALL 创建与 API 规范匹配的 QueryOutput 和 MetadataOutput 模型
5. WHEN 定义错误模型时 THEN 系统 SHALL 创建包含 errorCode、message、messages、datetime 和 debug 字段的 TableauError 模型

### 需求 8

**用户故事:** 作为开发者，我想要实现全面的错误处理，以便系统优雅地处理 API 错误并提供有意义的反馈。

#### 验收标准

1. WHEN API 调用失败时 THEN 系统 SHALL 解析 TableauError 响应并提取结构化错误信息
2. WHEN 身份验证失败时 THEN 系统 SHALL 检测 401/403 错误并提供清晰的身份验证指导
3. WHEN 验证失败时 THEN 系统 SHALL 检测 400 错误并提供字段级验证反馈
4. WHEN 服务器错误发生时 THEN 系统 SHALL 检测 500 错误并实现带指数退避的重试逻辑
5. WHEN 网络错误发生时 THEN 系统 SHALL 检测连接失败并提供适当的回退行为

### 需求 9

**用户故事:** 作为开发者，我想要实现全面的测试，以便验证迁移并确保无回归。

#### 验收标准

1. WHEN 测试元数据检索时 THEN 系统 SHALL 验证所有字段类型的 FieldMetadata 对象的正确解析
2. WHEN 测试查询执行时 THEN 系统 SHALL 验证各种查询模式的正确查询构造和响应解析
3. WHEN 测试过滤器时 THEN 系统 SHALL 验证所有六种过滤器类型的正确过滤器构造
4. WHEN 测试错误处理时 THEN 系统 SHALL 验证所有错误场景的正确错误解析和处理
5. WHEN 测试向后兼容性时 THEN 系统 SHALL 验证功能标志在旧版和新 API 模式之间正确切换

### 需求 10

**用户故事:** 作为系统管理员，我想要配置 API 端点，以便系统可以连接到不同的 Tableau 环境。

#### 验收标准

1. WHEN 配置端点时 THEN 系统 SHALL 支持 Tableau 服务器基础 URL 的环境变量
2. WHEN 构造 API URL 时 THEN 系统 SHALL 将 /vizql-data-service/v1 路径附加到基础 URL
3. WHEN 使用 Tableau Cloud 时 THEN 系统 SHALL 支持格式为 https://[pod].online.tableau.com 的特定 pod URL
4. WHEN 使用 Tableau Server 时 THEN 系统 SHALL 支持格式为 https://[server]/ 的本地部署 URL
5. WHEN 验证配置时 THEN 系统 SHALL 使用 simple-request 健康检查端点验证 API 端点可访问性
6. WHEN 配置 SSL 时 THEN 系统 SHALL 支持三种 SSL 验证模式：系统默认 CA 证书、禁用验证和自定义 CA 证书文件
7. WHEN 使用自定义证书时 THEN 系统 SHALL 支持通过 SSL Context 对象加载自定义 CA 证书链

### 需求 11

**用户故事:** 作为开发者，我想要优化 API 使用，以便系统最小化延迟和 API 调用量。

#### 验收标准

1. WHEN 获取元数据时 THEN 系统 SHALL 使用可配置的 TTL 缓存元数据响应
2. WHEN 执行相同查询时 THEN 系统 SHALL 使用会话范围的 TTL 缓存查询结果
3. WHEN 进行 API 调用时 THEN 系统 SHALL 实现连接池以重用 HTTP 连接
4. WHEN 处理大型结果集时 THEN 系统 SHALL 在可用时支持分页或流式传输
5. WHEN 遇到速率限制时 THEN 系统 SHALL 实现指数退避和重试逻辑

### 需求 12

**用户故事:** 作为开发者，我想要记录迁移过程，以便团队成员可以理解和维护新实现。

#### 验收标准

1. WHEN 记录 API 变更时 THEN 系统 SHALL 提供旧版与新 API 端点的对比表
2. WHEN 记录数据模型时 THEN 系统 SHALL 为所有新 Pydantic 模型提供架构文档
3. WHEN 记录配置时 THEN 系统 SHALL 提供环境变量配置示例
4. WHEN 记录迁移步骤时 THEN 系统 SHALL 提供包含回滚程序的分步迁移指南
5. WHEN 记录测试时 THEN 系统 SHALL 提供测试覆盖率报告和示例测试用例

### 需求 13

**用户故事:** 作为开发者，我想要使用官方 Python SDK，以便简化 API 集成并获得类型安全保障。

#### 验收标准

1. WHEN 安装依赖时 THEN 系统 SHALL 通过 pip 安装 vizql-data-service-py 包并添加到 requirements.txt
2. WHEN 创建客户端时 THEN 系统 SHALL 使用 VizQLDataServiceClient 类，该类接受 server_url、TableauServerClient 实例和身份验证对象
3. WHEN 构建请求时 THEN 系统 SHALL 使用 SDK 的 Pydantic v2 模型对象而非原始 JSON 字典
4. WHEN 调用 API 时 THEN 系统 SHALL 支持 sync 和 sync_detailed 两种调用方式，前者仅返回数据，后者返回完整响应
5. WHEN 处理响应时 THEN 系统 SHALL 使用 SDK 的 Pydantic 模型自动验证和解析响应数据
6. WHEN 配置客户端时 THEN 系统 SHALL 支持通过 verify_ssl 参数配置 SSL 验证行为，包括 True（系统CA）、False（禁用）、字符串路径（自定义CA）和 SSLContext 对象
7. WHEN 使用异步模式时 THEN 系统 SHALL 支持 asyncio 和 asyncio_detailed 异步方法
8. WHEN 复用现有认证时 THEN 系统 SHALL 使用 tableauserverclient 的认证对象（JWTAuth、PersonalAccessTokenAuth、TableauAuth）

### 需求 14

**用户故事:** 作为开发者，我想要理解 Python SDK 的数据模型结构，以便正确构建查询请求。

#### 验收标准

1. WHEN 构建查询请求时 THEN 系统 SHALL 使用 QueryRequest 模型，该模型包含 datasource 和 query 两个必需字段
2. WHEN 指定数据源时 THEN 系统 SHALL 使用 Datasource 模型，该模型包含 datasourceLuid 必需字段和可选的 connections 数组
3. WHEN 构建查询对象时 THEN 系统 SHALL 使用 Query 模型，该模型包含 fields 必需数组和可选的 filters 和 parameters 数组
4. WHEN 定义字段时 THEN 系统 SHALL 使用 Field 联合类型，该类型包含 DimensionField、MeasureField、CalculatedField、BinField 和 TableCalcField 五种子类型
5. WHEN 定义过滤器时 THEN 系统 SHALL 使用 Filter 基类及其六种子类型，每种子类型通过 filterType 鉴别器区分
6. WHEN 接收元数据时 THEN 系统 SHALL 解析 MetadataOutput 模型，该模型包含 data 数组和可选的 extraData 对象
7. WHEN 接收查询结果时 THEN 系统 SHALL 解析 QueryOutput 模型，该模型包含 data 数组和可选的 extraData 对象
8. WHEN 处理错误时 THEN 系统 SHALL 解析 TableauError 模型，该模型包含 errorCode、message、datetime 和 debug 字段

### 需求 15

**用户故事:** 作为开发者，我想要理解表计算功能，以便支持高级分析查询。

#### 验收标准

1. WHEN 使用表计算时 THEN 系统 SHALL 支持 TableCalcField 字段类型，该类型包含 tableCalculation 必需字段
2. WHEN 定义表计算时 THEN 系统 SHALL 使用 TableCalcSpecification 基类，该类包含 tableCalcType 和 dimensions 两个必需字段
3. WHEN 指定表计算类型时 THEN 系统 SHALL 支持十种类型：CUSTOM、NESTED、DIFFERENCE_FROM、PERCENT_DIFFERENCE_FROM、PERCENT_FROM、PERCENT_OF_TOTAL、RANK、PERCENTILE、RUNNING_TOTAL 和 MOVING_CALCULATION
4. WHEN 使用移动计算时 THEN 系统 SHALL 支持 MovingTableCalcSpecification，该类型包含 aggregation、previous、next、includeCurrent 和 fillInNull 字段
5. WHEN 使用累计总计时 THEN 系统 SHALL 支持 RunningTotalTableCalcSpecification，该类型包含 aggregation、restartEvery 和 secondaryTableCalculation 字段
6. WHEN 使用排名计算时 THEN 系统 SHALL 支持 RankTableCalcSpecification，该类型包含 rankType 和 direction 字段
7. WHEN 嵌套表计算时 THEN 系统 SHALL 支持 nestedTableCalculations 数组字段用于定义多层表计算

### 需求 16

**用户故事:** 作为开发者，我想要复用现有组件，以便减少重复代码并保持系统一致性。

#### 验收标准

1. WHEN 实现元数据管理时 THEN 系统 SHALL 复用 MetadataManager 的缓存机制、Store 集成和增强逻辑
2. WHEN 实现查询执行时 THEN 系统 SHALL 复用 QueryExecutor 的重试机制、错误分类和性能监控框架
3. WHEN 定义内部数据模型时 THEN 系统 SHALL 保留现有的 Metadata、FieldMetadata 和 QueryPlan 模型
4. WHEN 处理配置时 THEN 系统 SHALL 扩展现有的 Settings 类以添加 SDK 相关配置项
5. WHEN 处理认证时 THEN 系统 SHALL 复用 tableauserverclient 的认证对象和会话管理
6. WHEN 构建查询时 THEN 系统 SHALL 保留现有的 QueryBuilder 逻辑，仅修改输出格式以适配 SDK 模型
7. WHEN 转换模型时 THEN 系统 SHALL 创建转换器在内部模型（vizql_types）和 SDK 模型（openapi_generated）之间转换

### 需求 17

**用户故事:** 作为开发者，我想要实现模型转换层，以便在内部模型和 SDK 模型之间无缝转换。

#### 验收标准

1. WHEN 转换字段模型时 THEN 系统 SHALL 将内部 VizQLField（BasicField、FunctionField、CalculationField）转换为 SDK Field 模型
2. WHEN 转换过滤器模型时 THEN 系统 SHALL 将内部 VizQLFilter 转换为 SDK Filter 模型，保持所有过滤器类型的语义
3. WHEN 转换查询模型时 THEN 系统 SHALL 将内部 VizQLQuery 转换为 SDK Query 模型
4. WHEN 转换元数据模型时 THEN 系统 SHALL 将 SDK MetadataOutput 转换为内部 Metadata 模型
5. WHEN 转换失败时 THEN 系统 SHALL 提供清晰的错误信息，指出不兼容的字段或值
6. WHEN 转换成功时 THEN 系统 SHALL 保留所有字段属性，包括 fieldAlias、sortDirection、maxDecimalPlaces 等
7. WHEN 处理可选字段时 THEN 系统 SHALL 正确处理 None 值，使用 exclude_none=True 序列化

### 需求 18

**用户故事:** 作为开发者，我想要实现 SDK 客户端包装器，以便统一管理 SDK 客户端的创建和配置。

#### 验收标准

1. WHEN 创建客户端包装器时 THEN 系统 SHALL 封装 VizQLDataServiceClient 的初始化逻辑
2. WHEN 配置 SSL 时 THEN 系统 SHALL 支持从环境变量或配置文件读取 SSL 设置
3. WHEN 管理会话时 THEN 系统 SHALL 复用 tableauserverclient 的 Server 实例和认证令牌
4. WHEN 处理 API 调用时 THEN 系统 SHALL 提供统一的错误处理和日志记录
5. WHEN 使用客户端时 THEN 系统 SHALL 支持上下文管理器（with 语句）自动管理资源
6. WHEN 配置超时时 THEN 系统 SHALL 支持自定义超时设置，默认使用合理的超时值
7. WHEN 处理重连时 THEN 系统 SHALL 在认证令牌过期时自动刷新令牌

### 需求 19

**用户故事:** 作为开发者，我想要实现增量迁移策略，以便在不影响现有功能的情况下逐步迁移到新 API。

#### 验收标准

1. WHEN 启用功能标志时 THEN 系统 SHALL 支持通过环境变量 USE_VIZQL_SDK 控制是否使用新 SDK
2. WHEN 功能标志为 False 时 THEN 系统 SHALL 使用现有的 vizql_data_service.py 实现
3. WHEN 功能标志为 True 时 THEN 系统 SHALL 使用新的 SDK 客户端包装器
4. WHEN 切换 API 版本时 THEN 系统 SHALL 保持对外接口不变，确保下游组件无需修改
5. WHEN 两种模式共存时 THEN 系统 SHALL 在日志中清晰标识当前使用的 API 版本
6. WHEN 迁移完成后 THEN 系统 SHALL 提供清理旧代码的指南，包括可以安全删除的文件列表
7. WHEN 回滚时 THEN 系统 SHALL 支持快速切换回旧版 API，无需代码修改

### 需求 20

**用户故事:** 作为开发者，我想要更新现有的 vizql_data_service.py，以便支持 SDK 模式和传统模式的切换。

#### 验收标准

1. WHEN 检测功能标志时 THEN 系统 SHALL 在 vizql_data_service.py 中检查 USE_VIZQL_SDK 环境变量
2. WHEN 使用 SDK 模式时 THEN query_vds 函数 SHALL 调用 SDK 客户端包装器执行查询
3. WHEN 使用传统模式时 THEN query_vds 函数 SHALL 使用现有的 requests 库实现
4. WHEN 使用 SDK 模式时 THEN query_vds_metadata 函数 SHALL 调用 SDK 的 read_metadata 方法
5. WHEN 使用传统模式时 THEN query_vds_metadata 函数 SHALL 使用现有的 REST API 实现
6. WHEN 返回结果时 THEN 系统 SHALL 确保两种模式返回相同格式的数据结构
7. WHEN 处理错误时 THEN 系统 SHALL 将 SDK 异常转换为与传统模式一致的 RuntimeError

### 需求 21

**用户故事:** 作为开发者，我想要验证迁移的正确性，以便确保新旧 API 返回一致的结果。

#### 验收标准

1. WHEN 执行对比测试时 THEN 系统 SHALL 提供工具脚本同时调用新旧 API 并比较结果
2. WHEN 比较元数据时 THEN 系统 SHALL 验证字段数量、字段名称、数据类型和聚合方式一致
3. WHEN 比较查询结果时 THEN 系统 SHALL 验证返回的行数、列数和数据值一致
4. WHEN 发现差异时 THEN 系统 SHALL 生成详细的差异报告，包括不一致的字段和值
5. WHEN 测试过滤器时 THEN 系统 SHALL 验证所有过滤器类型在新旧 API 中产生相同的结果
6. WHEN 测试排序时 THEN 系统 SHALL 验证排序结果在新旧 API 中一致
7. WHEN 测试聚合时 THEN 系统 SHALL 验证聚合计算结果在新旧 API 中一致，允许浮点数精度差异在可接受范围内

### 需求 22

**用户故事:** 作为系统管理员，我想要配置 SDK 相关参数，以便根据部署环境调整 API 行为。

#### 验收标准

1. WHEN 配置 SDK 时 THEN 系统 SHALL 支持环境变量 USE_VIZQL_SDK 控制是否启用 SDK（默认 false）
2. WHEN 配置 SSL 时 THEN 系统 SHALL 支持环境变量 VIZQL_SDK_VERIFY_SSL 控制 SSL 验证行为（默认 true）
3. WHEN 配置自定义 CA 时 THEN 系统 SHALL 支持环境变量 VIZQL_SDK_CA_BUNDLE 指定自定义 CA 证书路径
4. WHEN 配置超时时 THEN 系统 SHALL 支持环境变量 VIZQL_SDK_TIMEOUT 设置 API 调用超时时间（默认 30 秒）
5. WHEN 配置重试时 THEN 系统 SHALL 支持环境变量 VIZQL_SDK_MAX_RETRIES 设置最大重试次数（默认 3 次）
6. WHEN 配置日志时 THEN 系统 SHALL 支持环境变量 VIZQL_SDK_DEBUG 启用详细日志（默认 false）
7. WHEN 验证配置时 THEN 系统 SHALL 在启动时验证所有 SDK 相关配置的有效性，并在配置无效时提供清晰的错误信息

### 需求 23

**用户故事:** 作为开发者，我想要将 SDK 集成到 DeepAgents 工具层，以便在保持现有架构的同时使用新 API。

#### 验收标准

1. WHEN 实现 vizql_query 工具时 THEN 系统 SHALL 根据 USE_VIZQL_SDK 标志选择使用 SDK 或传统 API
2. WHEN 使用 SDK 模式时 THEN vizql_query 工具 SHALL 调用 SDK 客户端包装器执行查询
3. WHEN 使用传统模式时 THEN vizql_query 工具 SHALL 调用现有的 query_vds 函数
4. WHEN 实现 get_metadata 工具时 THEN 系统 SHALL 根据 USE_VIZQL_SDK 标志选择使用 SDK 或传统 API
5. WHEN 使用 SDK 模式时 THEN get_metadata 工具 SHALL 调用 SDK 的 read_metadata 方法
6. WHEN 使用传统模式时 THEN get_metadata 工具 SHALL 调用现有的 query_vds_metadata 函数
7. WHEN 工具返回结果时 THEN 系统 SHALL 确保两种模式返回相同格式的数据结构，对下游组件透明

### 需求 24

**用户故事:** 作为开发者，我想要在 VizQLQueryMiddleware 中集成 SDK 支持，以便统一管理查询工具的注入和配置。

#### 验收标准

1. WHEN VizQLQueryMiddleware 初始化时 THEN 系统 SHALL 检查 USE_VIZQL_SDK 环境变量
2. WHEN USE_VIZQL_SDK 为 true 时 THEN 中间件 SHALL 创建 SDK 客户端包装器实例
3. WHEN USE_VIZQL_SDK 为 false 时 THEN 中间件 SHALL 使用传统的 requests 实现
4. WHEN 中间件注入工具时 THEN 系统 SHALL 将 SDK 客户端或传统实现传递给工具函数
5. WHEN 中间件添加系统提示词时 THEN 系统 SHALL 根据使用的 API 版本调整提示词内容
6. WHEN 中间件处理错误时 THEN 系统 SHALL 统一处理 SDK 异常和传统 API 异常
7. WHEN 中间件记录日志时 THEN 系统 SHALL 清晰标识当前使用的 API 版本（SDK 或传统）

### 需求 25

**用户故事:** 作为开发者，我想要实现 Planning Agent 与 SDK 的集成，以便生成符合 SDK 模型规范的查询。

#### 验收标准

1. WHEN Planning Agent 生成查询计划时 THEN 系统 SHALL 使用现有的 Intent 模型（无需修改）
2. WHEN QueryBuilder 构建查询时 THEN 系统 SHALL 根据 USE_VIZQL_SDK 标志选择输出格式
3. WHEN USE_VIZQL_SDK 为 true 时 THEN QueryBuilder SHALL 输出 SDK 的 Query 模型对象
4. WHEN USE_VIZQL_SDK 为 false 时 THEN QueryBuilder SHALL 输出内部的 VizQLQuery 模型对象
5. WHEN 转换为 SDK 模型时 THEN 系统 SHALL 使用模型转换器进行转换
6. WHEN 转换失败时 THEN 系统 SHALL 提供详细的错误信息并回退到传统模式
7. WHEN Planning Agent 完成时 THEN 系统 SHALL 确保生成的查询计划与 SDK 模型完全兼容

### 需求 26

**用户故事:** 作为开发者，我想要保持 DeepAgents 子代理的独立性，以便 SDK 迁移不影响其他子代理的功能。

#### 验收标准

1. WHEN Boost Agent 执行时 THEN 系统 SHALL 不受 SDK 迁移影响，继续使用现有逻辑
2. WHEN Understanding Agent 执行时 THEN 系统 SHALL 不受 SDK 迁移影响，继续使用现有逻辑
3. WHEN Insight Agent 执行时 THEN 系统 SHALL 不受 SDK 迁移影响，继续使用现有逻辑
4. WHEN Replanner Agent 执行时 THEN 系统 SHALL 不受 SDK 迁移影响，继续使用现有逻辑
5. WHEN Planning Agent 调用工具时 THEN 系统 SHALL 通过工具层的抽象隔离 SDK 实现细节
6. WHEN 子代理之间传递数据时 THEN 系统 SHALL 使用统一的内部模型，不暴露 SDK 模型
7. WHEN 添加新子代理时 THEN 系统 SHALL 确保新子代理可以透明地使用 SDK 或传统 API

### 需求 27

**用户故事:** 作为开发者，我想要利用 DeepAgents 的缓存机制，以便与 SDK 的查询缓存协同工作。

#### 验收标准

1. WHEN 系统使用 AnthropicPromptCachingMiddleware 时 THEN 系统 SHALL 缓存包含元数据的系统提示词
2. WHEN 系统使用 ApplicationLevelCacheMiddleware 时 THEN 系统 SHALL 缓存 LLM 响应
3. WHEN 系统使用查询结果缓存时 THEN 系统 SHALL 在 PersistentStore 中缓存 VizQL 查询结果
4. WHEN 使用 SDK 模式时 THEN 系统 SHALL 将 SDK 返回的结果转换为内部格式后缓存
5. WHEN 使用传统模式时 THEN 系统 SHALL 直接缓存传统 API 返回的结果
6. WHEN 检查缓存时 THEN 系统 SHALL 使用统一的 query_key 生成算法，确保两种模式的缓存可以共享
7. WHEN 缓存命中时 THEN 系统 SHALL 记录缓存来源（SDK 或传统），用于性能分析

### 需求 28

**用户故事:** 作为开发者，我想要实现渐进式迁移策略，以便在 DeepAgents 架构下安全地迁移到 SDK。

#### 验收标准

1. WHEN 系统启动时 THEN 系统 SHALL 记录当前使用的 API 版本（SDK 或传统）到日志
2. WHEN 系统处理查询时 THEN 系统 SHALL 在性能指标中标识使用的 API 版本
3. WHEN 系统发生错误时 THEN 系统 SHALL 在错误日志中标识使用的 API 版本
4. WHEN 系统切换 API 版本时 THEN 系统 SHALL 无需重启，通过重新加载配置即可生效
5. WHEN 系统运行在混合模式时 THEN 系统 SHALL 支持部分查询使用 SDK，部分使用传统 API
6. WHEN 系统完成迁移后 THEN 系统 SHALL 提供清理脚本，安全删除传统 API 相关代码
7. WHEN 系统需要回滚时 THEN 系统 SHALL 支持快速切换回传统 API，无需代码修改

### 需求 29

**用户故事:** 作为开发者，我想要更新测试套件以支持 SDK，以便验证迁移的正确性。

#### 验收标准

1. WHEN 运行单元测试时 THEN 系统 SHALL 支持测试 SDK 模式和传统模式
2. WHEN 测试模型转换器时 THEN 系统 SHALL 验证内部模型和 SDK 模型之间的双向转换
3. WHEN 测试工具层时 THEN 系统 SHALL 验证工具在两种模式下返回相同的结果
4. WHEN 测试中间件时 THEN 系统 SHALL 验证 VizQLQueryMiddleware 在两种模式下的行为一致
5. WHEN 测试子代理时 THEN 系统 SHALL 验证子代理不受 SDK 迁移影响
6. WHEN 运行集成测试时 THEN 系统 SHALL 验证完整的查询流程在两种模式下产生相同结果
7. WHEN 运行性能测试时 THEN 系统 SHALL 比较 SDK 模式和传统模式的性能差异

### 需求 30

**用户故事:** 作为开发者，我想要更新文档以反映 SDK 集成，以便团队成员理解新架构。

#### 验收标准

1. WHEN 查看架构文档时 THEN 系统 SHALL 提供 SDK 集成的架构图
2. WHEN 查看工具文档时 THEN 系统 SHALL 说明工具如何支持双模式
3. WHEN 查看中间件文档时 THEN 系统 SHALL 说明 VizQLQueryMiddleware 的 SDK 支持
4. WHEN 查看配置文档时 THEN 系统 SHALL 列出所有 SDK 相关的环境变量
5. WHEN 查看迁移指南时 THEN 系统 SHALL 提供从传统 API 到 SDK 的迁移步骤
6. WHEN 查看故障排除文档时 THEN 系统 SHALL 提供 SDK 相关问题的解决方案
7. WHEN 查看 API 参考时 THEN 系统 SHALL 说明 SDK 模型和内部模型的对应关系
