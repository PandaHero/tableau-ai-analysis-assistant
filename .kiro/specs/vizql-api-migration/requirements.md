# 需求文档

## 简介

本文档概述了将 Tableau Assistant 升级到新版 VizQL Data Service API 并集成 DeepAgents 架构的需求。VizQL Data Service 提供了一个现代化的无头 BI 接口，用于查询 Tableau 已发布的数据源，具有更好的性能、更完善的错误处理以及增强的查询功能，包括表计算、过滤器和参数。

VizQL Data Service 是 Tableau 2025.1+ 版本引入的新 API，提供了基于 OpenAPI 3.0.4 规范的标准化接口。该 API 支持同步和异步查询模式，并提供了官方的 Python SDK（vizql-data-service-py）用于简化集成。

本次升级采用 **DeepAgents 架构**，使用 LangGraph 的 StateGraph 管理工作流，将现有组件封装为 LangChain 工具，并集成 6 个 DeepAgents 中间件以增强系统能力。

## 架构重构概述

本次升级采用 **DeepAgents 架构**，主要变化包括：

### 核心架构变化

1. **DeepAgents 框架集成**
   - 使用 `create_deep_agent()` 创建主 Agent
   - 集成 6 个 DeepAgents 中间件
   - 使用 LangGraph StateGraph 管理工作流节点

2. **工具封装策略**
   - 将现有组件封装为 LangChain 工具（使用 @tool 装饰器）
   - 8 个核心工具：get_metadata, parse_date, build_vizql_query, execute_vizql_query, semantic_map_fields, process_query_result, detect_statistics, get_dimension_hierarchy
   - 工具通过 DeepAgent 统一管理和调用

3. **StateGraph 工作流**
   - 6 个节点：Boost, Understanding, Planning, Execute, Insight, Replanner
   - 节点之间通过 VizQLContext 状态传递
   - 支持重规划循环（Replanner → Understanding）

4. **SDK 直接集成**
   - 直接使用官方 vizql-data-service-py SDK
   - 不需要功能标志或双模式支持（直接升级策略）
   - 一次性完成迁移，无需维护新旧两套代码

### 可复用组件（100%复用）

1. **MetadataManager** (`tableau_assistant/src/components/metadata_manager.py`)
   - 元数据获取和缓存逻辑
   - 维度层级推断集成
   - 日期字段最大值查询
   - **迁移方式**：封装为 `get_metadata` 工具

2. **QueryExecutor** (`tableau_assistant/src/components/query_executor.py`)
   - 查询执行框架
   - 重试机制和错误处理
   - 性能监控
   - **迁移方式**：封装为 `execute_vizql_query` 工具

3. **QueryBuilder** (`tableau_assistant/src/components/query_builder/`)
   - Intent 模型到 VizQL 查询的转换
   - 字段、过滤器、聚合的构建逻辑
   - **迁移方式**：封装为 `build_vizql_query` 工具

4. **VizQL 类型定义** (`tableau_assistant/src/models/vizql_types.py`)
   - 完整的 Pydantic v2 模型
   - **当前支持**：BasicField、FunctionField、CalculationField（3 种字段类型）
   - **当前不支持**：TableCalcField（表计算字段）
   - 过滤器类型（SetFilter、TopNFilter、RelativeDateFilter 等）
   - **迁移方式**：添加 TableCalcField 及相关的 TableCalcSpecification 类型
   - **注意**：这是新功能，当前系统无法处理表计算查询

5. **Metadata 模型** (`tableau_assistant/src/models/metadata.py`)
   - FieldMetadata 和 Metadata 模型
   - 字段查询方法
   - 日期字段识别
   - **迁移方式**：完整保留，作为系统内部统一的元数据模型

6. **QueryPlan 和 Intent 模型** (`tableau_assistant/src/models/query_plan.py`, `intent.py`)
   - QuerySubTask 和 Intent 模型
   - **当前支持**：DimensionIntent、MeasureIntent、DateFieldIntent、FilterIntent、TopNIntent（6 种意图类型）
   - **当前不支持**：TableCalcIntent（表计算意图）
   - 查询规划结构
   - **迁移方式**：添加 TableCalcIntent 类型
   - **注意**：这是新功能，当前 Planning Agent 无法识别表计算需求

7. **配置管理** (`tableau_assistant/src/config/settings.py`)
   - 环境变量管理
   - Tableau 配置
   - **迁移方式**：添加 SDK 相关配置项

8. **StateGraph 工作流** (`tableau_assistant/src/agents/`)
   - 6 个工作流节点实现
   - VizQLContext 状态管理
   - **迁移方式**：修改为使用 DeepAgent，保持节点逻辑不变

### 需要新增的组件

1. **DeepAgent 创建器** (`tableau_assistant/src/agents/deep_agent_factory.py`)
   - 创建配置了 6 个中间件的 DeepAgent
   - 管理工具注入和模型配置
   - 已实现 ✓

2. **VizQL 客户端增强** (`tableau_assistant/src/bi_platforms/tableau/vizql_data_service.py`)
   - 增强现有的 `query_vds` 和 `query_vds_metadata` 函数
   - 添加 Pydantic 模型验证（请求和响应）
   - 添加重试逻辑和错误处理
   - 复用现有的认证实现（`auth.py`）

3. **表计算模型** (`tableau_assistant/src/models/vizql_types.py`)
   - 添加 TableCalcField 和 TableCalcSpecification
   - 添加各种表计算类型（RunningTotal、Moving、Rank 等）

4. **表计算 Intent** (`tableau_assistant/src/models/intent.py`)
   - 添加 TableCalcIntent 类型
   - 支持表计算意图的表达

5. **工具封装层**
   - 将 8 个组件封装为 LangChain 工具
   - 提供完整的 docstring 和参数验证

## 术语表

- **VizQL Data Service**: 新的 Tableau API 服务，提供对已发布数据源的编程查询访问，基于 OpenAPI 3.0.4 规范
- **Tableau Assistant**: AI 驱动的助手系统，帮助用户通过自然语言查询分析 Tableau 数据
- **Data Source（数据源）**: 可通过 API 查询的已发布 Tableau 数据源
- **LUID**: Tableau 用于标识资源的本地唯一标识符
- **Field（字段）**: 已发布数据源中的数据列，可以是维度、度量或计算字段
- **Query Plan（查询计划）**: VizQL 查询的结构化表示，包括字段、过滤器和参数
- **Metadata（元数据）**: 关于数据源结构的信息，包括字段名称、数据类型和关系
- **PAT**: 用于 Tableau Cloud 身份验证的个人访问令牌
- **VizQL Data Service**: Tableau 2025.1+ 的查询 API，提供 `/api/v1/vizql-data-service/` 端点
- **VizQL Client**: 我们自己的客户端封装，使用 requests 库和 Pydantic 模型
- **Pydantic v2**: Python 数据验证库，用于类型安全的数据模型定义
- **SSL Context**: SSL/TLS 安全上下文，用于配置证书验证和自定义 CA 证书
- **DeepAgents**: LangChain 的 Agent 框架，提供中间件系统和工具管理
- **StateGraph**: LangGraph 的状态图，用于管理多节点工作流
- **LangChain Tool**: 使用 @tool 装饰器定义的可调用函数，供 Agent 使用
- **Middleware（中间件）**: DeepAgents 的插件系统，用于增强 Agent 能力（如缓存、总结、文件管理等）
- **VizQLContext**: StateGraph 的状态对象，在工作流节点之间传递数据

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

1. WHEN 构建维度字段时 THEN QueryBuilder SHALL 生成包含 fieldCaption、可选 fieldAlias 和可选排序参数的 BasicField 对象
2. WHEN 构建度量字段时 THEN QueryBuilder SHALL 生成包含 fieldCaption、function（聚合）和可选格式化参数的 FunctionField 对象
3. WHEN 构建计算字段时 THEN QueryBuilder SHALL 生成包含 fieldCaption 和 calculation 公式的 CalculationField 对象
4. WHEN 构建表计算字段时 THEN QueryBuilder SHALL 生成包含 fieldCaption 和 tableCalculation 规范的 TableCalcField 对象
5. WHEN 处理 TableCalcIntent 时 THEN QueryBuilder SHALL 根据 table_calc_type 创建相应的 TableCalcSpecification（RunningTotal、Moving、Rank 等）
6. WHEN 构建过滤器时 THEN QueryBuilder SHALL 根据过滤器类型生成适当的过滤器对象，包含必需的 field 和 filterType 属性
7. WHEN 构建查询时 THEN QueryBuilder SHALL 构造包含 fields 数组以及可选 filters 和 parameters 数组的 VizQLQuery 对象

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

1. WHEN 获取元数据时 THEN MetadataManager SHALL 向 /api/v1/vizql-data-service/read-metadata 端点发送 POST 请求
2. WHEN 准备元数据请求时 THEN MetadataManager SHALL 在请求体中包含 datasourceLuid
3. WHEN 接收元数据时 THEN MetadataManager SHALL 解析包含 FieldMetadata 对象数组的响应
4. WHEN 处理字段元数据时 THEN MetadataManager SHALL 提取 fieldName、fieldCaption、dataType、defaultAggregation、columnClass 和可选的 formula
5. WHEN 识别表计算字段时 THEN MetadataManager SHALL 检查 columnClass 是否为 "TABLE_CALCULATION"，并提取 formula 字段
6. WHEN 处理参数时 THEN MetadataManager SHALL 从 extraData.parameters 字段提取参数信息

### 需求 6

**用户故事:** 作为开发者，我想要集成 DeepAgents 架构，以便利用中间件系统增强 Agent 能力。

#### 验收标准

1. WHEN 创建 Agent 时 THEN 系统 SHALL 使用 create_deep_agent 函数创建配置了 6 个中间件的 DeepAgent
2. WHEN 配置中间件时 THEN 系统 SHALL 包含 AnthropicPromptCachingMiddleware（仅 Claude 模型）、SummarizationMiddleware、FilesystemMiddleware、ToolRetryMiddleware、TodoListMiddleware 和 HumanInTheLoopMiddleware
3. WHEN 配置中间件时 THEN 系统 SHALL 排除 SubAgentMiddleware，使用 StateGraph 替代
4. WHEN 使用 Claude 模型时 THEN 系统 SHALL 启用 AnthropicPromptCachingMiddleware 进行 Prompt 缓存
5. WHEN 使用非 Claude 模型时 THEN 系统 SHALL 不启用 AnthropicPromptCachingMiddleware
6. WHEN 对话超过 10 轮时 THEN SummarizationMiddleware SHALL 触发对话总结
7. WHEN 查询结果超过 10MB 时 THEN FilesystemMiddleware SHALL 将结果写入文件系统

### 需求 7

**用户故事:** 作为开发者，我想要更新数据模型，以便它们表示新的 VizQL Data Service API 结构。

#### 验收标准

1. WHEN 定义 VizQL 字段模型时 THEN 系统 SHALL 为 DimensionField、MeasureField、CalculatedField、BinField 和 TableCalcField 创建 Pydantic 模型
2. WHEN 定义 Intent 字段模型时 THEN 系统 SHALL 扩展 Intent 模型，添加 TableCalcIntent 类型以支持表计算意图
3. WHEN 定义过滤器模型时 THEN 系统 SHALL 为所有六种过滤器类型创建具有适当鉴别器配置的 Pydantic 模型
4. WHEN 定义查询模型时 THEN 系统 SHALL 创建包含 fields、filters 和 parameters 数组的 Query 模型
5. WHEN 定义响应模型时 THEN 系统 SHALL 创建与 API 规范匹配的 QueryOutput 和 MetadataOutput 模型
6. WHEN 定义错误模型时 THEN 系统 SHALL 创建包含 errorCode、message、messages、datetime 和 debug 字段的 TableauError 模型
7. WHEN Planning Agent 生成 Intent 时 THEN 系统 SHALL 能够识别表计算需求并生成 TableCalcIntent 对象

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
5. WHEN 测试表计算时 THEN 系统 SHALL 验证 TableCalcField 的正确构造和查询执行

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

**用户故事:** 作为开发者，我想要增强现有的 VizQL 客户端，以便获得类型安全和更好的错误处理。

#### 验收标准

1. WHEN 构建请求时 THEN 系统 SHALL 使用 Pydantic v2 模型对象而非原始 JSON 字典
2. WHEN 调用 API 时 THEN 系统 SHALL 复用现有的 `query_vds` 和 `query_vds_metadata` 函数
3. WHEN 处理响应时 THEN 系统 SHALL 使用 Pydantic 模型自动验证和解析响应数据
4. WHEN 配置客户端时 THEN 系统 SHALL 支持 SSL 验证配置（通过环境变量或配置文件）
5. WHEN 使用异步模式时 THEN 系统 SHALL 使用现有的异步函数（已实现）
6. WHEN 进行认证时 THEN 系统 SHALL 复用现有的认证实现（`auth.py` 中的 JWT 和 PAT 认证）
7. WHEN 处理错误时 THEN 系统 SHALL 提供统一的错误处理和重试逻辑
8. WHEN 缓存 token 时 THEN 系统 SHALL 使用现有的 10 分钟缓存机制

### 需求 14

**用户故事:** 作为开发者，我想要定义完整的 Pydantic 数据模型，以便正确构建和验证查询请求。

#### 验收标准

1. WHEN 构建查询请求时 THEN 系统 SHALL 使用 VizQLQuery 模型（已存在于 vizql_types.py），该模型包含 fields 必需数组和可选的 filters 数组
2. WHEN 指定数据源时 THEN 系统 SHALL 使用 datasource_luid 字符串（在请求函数参数中传递）
3. WHEN 构建查询对象时 THEN 系统 SHALL 使用现有的 VizQLQuery 模型，扩展以支持 TableCalcField
4. WHEN 定义字段时 THEN 系统 SHALL 扩展 VizQLField 联合类型，添加 TableCalcField 类型（当前只有 BasicField、FunctionField、CalculationField）
5. WHEN 定义过滤器时 THEN 系统 SHALL 使用现有的 VizQLFilter 联合类型（已包含六种过滤器类型）
6. WHEN 接收元数据时 THEN 系统 SHALL 定义 MetadataOutput 模型，该模型包含 data 数组和可选的 extraData 对象
7. WHEN 接收查询结果时 THEN 系统 SHALL 使用现有的 QueryOutput 模型（已存在于 vizql_types.py）
8. WHEN 处理错误时 THEN 系统 SHALL 定义 TableauError 模型，该模型包含 errorCode、message、datetime 和 debug 字段

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
8. WHEN Planning Agent 识别表计算需求时 THEN 系统 SHALL 创建 TableCalcIntent 对象，包含 business_term、technical_field、table_calc_type 和 table_calc_config 字段
9. WHEN QueryBuilder 处理 TableCalcIntent 时 THEN 系统 SHALL 将其转换为 TableCalcField 和相应的 TableCalcSpecification 对象
10. WHEN 用户问题包含"累计"、"running total"关键词时 THEN Planning Agent SHALL 识别为 RUNNING_TOTAL 表计算需求
11. WHEN 用户问题包含"排名"、"rank"、"top N by"关键词时 THEN Planning Agent SHALL 识别为 RANK 表计算需求
12. WHEN 用户问题包含"移动平均"、"moving average"关键词时 THEN Planning Agent SHALL 识别为 MOVING_CALCULATION 表计算需求
13. WHEN 用户问题包含"百分比"、"percent of total"关键词时 THEN Planning Agent SHALL 识别为 PERCENT_OF_TOTAL 表计算需求

### 需求 16

**用户故事:** 作为开发者，我想要将现有组件封装为 LangChain 工具，以便在 DeepAgent 中统一管理和调用。

#### 验收标准

1. WHEN 封装组件时 THEN 系统 SHALL 使用 @tool 装饰器将组件封装为 LangChain 工具
2. WHEN 定义工具时 THEN 系统 SHALL 提供完整的 docstring，包括参数说明和返回值说明
3. WHEN 创建 Agent 时 THEN 系统 SHALL 配置恰好 8 个工具：get_metadata, parse_date, build_vizql_query, execute_vizql_query, semantic_map_fields, process_query_result, detect_statistics, get_dimension_hierarchy
4. WHEN 工具被调用时 THEN 系统 SHALL 保持原有组件的业务逻辑不变
5. WHEN 工具返回结果时 THEN 系统 SHALL 使用与原组件相同的数据格式
6. WHEN 工具调用失败时 THEN ToolRetryMiddleware SHALL 自动重试最多 3 次
7. WHEN 工具参数错误时 THEN ToolRetryMiddleware SHALL 尝试自动修复参数类型和默认值

### 需求 17

**用户故事:** 作为开发者，我想要使用 StateGraph 管理工作流，以便保持现有节点逻辑的同时集成 DeepAgent。

#### 验收标准

1. WHEN 创建工作流时 THEN 系统 SHALL 使用 LangGraph 的 StateGraph 定义 6 个节点：Boost, Understanding, Planning, Execute, Insight, Replanner
2. WHEN 节点执行时 THEN 系统 SHALL 使用 DeepAgent 调用工具，保持原有节点逻辑不变
3. WHEN 节点之间传递数据时 THEN 系统 SHALL 使用 VizQLContext 状态对象
4. WHEN boost_question 为 False 时 THEN 系统 SHALL 跳过 Boost 节点
5. WHEN should_replan 为 True 时 THEN 系统 SHALL 从 Replanner 节点路由回 Understanding 节点
6. WHEN 重规划次数达到最大值时 THEN 系统 SHALL 终止重规划循环
7. WHEN 工作流完成时 THEN 系统 SHALL 返回最终的洞察结果

### 需求 18

**用户故事:** 作为开发者，我想要增强现有的 VizQL 客户端函数，以便提供更好的错误处理和类型安全。

#### 验收标准

1. WHEN 增强客户端时 THEN 系统 SHALL 保持现有的 `query_vds` 和 `query_vds_metadata` 函数签名
2. WHEN 配置 SSL 时 THEN 系统 SHALL 支持从环境变量读取 SSL 设置（使用 requests 的 verify 参数）
3. WHEN 管理会话时 THEN 系统 SHALL 复用现有的认证实现（`_get_tableau_context_from_env`）
4. WHEN 处理 API 调用时 THEN 系统 SHALL 添加统一的错误处理和日志记录
5. WHEN 验证请求时 THEN 系统 SHALL 使用 Pydantic 模型验证请求参数
6. WHEN 配置超时时 THEN 系统 SHALL 支持自定义超时设置（通过 requests timeout 参数）
7. WHEN 处理重连时 THEN 系统 SHALL 使用现有的 token 缓存机制（10 分钟 TTL）

### 需求 19

**用户故事:** 作为开发者，我想要使用统一的 Pydantic 模型，以便在整个系统中保持类型安全。

#### 验收标准

1. WHEN 构建查询时 THEN 系统 SHALL 使用 vizql_types.py 中的 VizQLField 模型（BasicField、FunctionField、CalculationField、TableCalcField）
2. WHEN 构建过滤器时 THEN 系统 SHALL 使用 vizql_types.py 中的 VizQLFilter 模型（六种过滤器类型）
3. WHEN 构建查询时 THEN 系统 SHALL 使用 VizQLQuery 模型，该模型包含 fields 和 filters 数组
4. WHEN 序列化请求时 THEN 系统 SHALL 使用 model_dump(exclude_none=True) 生成 JSON
5. WHEN 解析响应时 THEN 系统 SHALL 使用 Pydantic 模型验证响应数据
6. WHEN 验证失败时 THEN 系统 SHALL 提供清晰的错误信息，指出不兼容的字段或值
7. WHEN 处理可选字段时 THEN 系统 SHALL 正确处理 None 值，使用 exclude_none=True 序列化

### 需求 20

**用户故事:** 作为开发者，我想要实现重规划功能，以便用户可以基于初始洞察进行深入分析。

#### 验收标准

1. WHEN Replanner 节点执行时 THEN 系统 SHALL 生成 2-5 个建议问题
2. WHEN 生成建议问题后 THEN HumanInTheLoopMiddleware SHALL 暂停执行等待用户响应
3. WHEN 用户选择问题时 THEN TodoListMiddleware SHALL 管理任务队列
4. WHEN 执行任务时 THEN 系统 SHALL 通过完整工作流序列（Understanding → Planning → Execute → Insight）
5. WHEN 所有任务完成时 THEN 系统 SHALL 聚合所有洞察结果
6. WHEN 用户拒绝继续时 THEN 系统 SHALL 终止工作流
7. WHEN 超时 5 分钟时 THEN 系统 SHALL 自动执行所有建议问题

### 需求 21

**用户故事:** 作为系统管理员，我想要配置 SDK 相关参数，以便根据部署环境调整 API 行为。

#### 验收标准

1. WHEN 配置 SSL 时 THEN 系统 SHALL 支持环境变量 VIZQL_VERIFY_SSL 控制 SSL 验证行为（默认 true）
2. WHEN 配置自定义 CA 时 THEN 系统 SHALL 支持环境变量 VIZQL_CA_BUNDLE 指定自定义 CA 证书路径
3. WHEN 配置超时时 THEN 系统 SHALL 支持环境变量 VIZQL_TIMEOUT 设置 API 调用超时时间（默认 30 秒）
4. WHEN 配置重试时 THEN 系统 SHALL 支持环境变量 VIZQL_MAX_RETRIES 设置最大重试次数（默认 3 次）
5. WHEN 配置日志时 THEN 系统 SHALL 支持环境变量 VIZQL_DEBUG 启用详细日志（默认 false）
6. WHEN 验证配置时 THEN 系统 SHALL 在启动时验证所有配置的有效性，并在配置无效时提供清晰的错误信息
7. WHEN 配置模型时 THEN 系统 SHALL 支持环境变量 MODEL_PROVIDER 和 MODEL_NAME 配置 LLM 模型
8. WHEN 配置认证时 THEN 系统 SHALL 使用现有的环境变量（TABLEAU_DOMAIN、TABLEAU_PAT_NAME、TABLEAU_PAT_SECRET 或 JWT 相关变量）

### 需求 22

**用户故事:** 作为开发者，我想要更新测试套件，以便验证 DeepAgents 集成和 SDK 迁移的正确性。

#### 验收标准

1. WHEN 运行单元测试时 THEN 系统 SHALL 测试工具封装、中间件配置和 StateGraph 节点
2. WHEN 测试模型转换器时 THEN 系统 SHALL 验证内部模型和 SDK 模型之间的双向转换
3. WHEN 测试工具层时 THEN 系统 SHALL 验证工具保持原有组件的业务逻辑
4. WHEN 测试中间件时 THEN 系统 SHALL 验证 6 个中间件都被正确配置
5. WHEN 测试 StateGraph 时 THEN 系统 SHALL 验证节点执行顺序和条件路由
6. WHEN 运行集成测试时 THEN 系统 SHALL 验证完整的查询流程和重规划流程
7. WHEN 运行属性测试时 THEN 系统 SHALL 使用 Hypothesis 库，每个测试至少 100 次迭代

### 需求 23

**用户故事:** 作为开发者，我想要更新文档以反映架构重构，以便团队成员理解新架构。

#### 验收标准

1. WHEN 查看架构文档时 THEN 系统 SHALL 提供 DeepAgents 集成的架构图
2. WHEN 查看工具文档时 THEN 系统 SHALL 说明 8 个工具的功能和参数
3. WHEN 查看中间件文档时 THEN 系统 SHALL 说明 6 个中间件的配置和作用
4. WHEN 查看 StateGraph 文档时 THEN 系统 SHALL 说明 6 个节点的功能和路由逻辑
5. WHEN 查看配置文档时 THEN 系统 SHALL 列出所有环境变量和配置项
6. WHEN 查看迁移指南时 THEN 系统 SHALL 提供从旧架构到新架构的迁移步骤
7. WHEN 查看 API 参考时 THEN 系统 SHALL 说明 SDK 模型和内部模型的对应关系

### 需求 24

**用户故事:** 作为开发者，我想要支持字符串类型的日期字段，以便系统能够处理各种日期格式的数据源。

#### 验收标准

1. WHEN 检测字段类型时 THEN 系统 SHALL 识别 STRING 类型字段中包含的日期数据
2. WHEN 分析样本值时 THEN 系统 SHALL 自动检测日期格式，支持至少 10 种常见格式（ISO、美式、欧式、季度、年月等）
3. WHEN 检测日期格式时 THEN 系统 SHALL 使用样本值进行模式匹配，置信度阈值为 0.7
4. WHEN 遇到美式和欧式格式歧义时 THEN 系统 SHALL 通过分析日期范围（如月份>12）进行区分
5. WHEN 构建日期过滤器时 THEN 系统 SHALL 根据字段的实际格式转换日期值
6. WHEN 字段为 STRING 类型日期时 THEN 系统 SHALL 在查询中使用 DATEPARSE 计算字段进行转换
7. WHEN 无法检测日期格式时 THEN 系统 SHALL 返回明确的错误信息，提示用户手动指定格式
8. WHEN 转换日期格式时 THEN 系统 SHALL 将所有日期统一转换为 ISO 格式（YYYY-MM-DD）
9. WHEN 处理时间戳格式时 THEN 系统 SHALL 提取日期部分并忽略时间部分
10. WHEN 缓存元数据时 THEN 系统 SHALL 包含检测到的日期格式信息，避免重复检测
