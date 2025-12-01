# 需求文档：Tableau Assistant 统一重构

## 简介

本文档定义了 Tableau Assistant 的统一重构需求，整合 DeepAgents 框架迁移和 VizQL Data Service API 升级两个项目。

### 重构背景

当前系统面临两个核心挑战：

1. **架构复杂性**：手动编排的 LangGraph 工作流缺少 DeepAgents 的内置优化能力
2. **API 限制**：旧版 VizQL API 不支持表计算，导致复杂的多轮查询逻辑

### 重构目标

- 采用 DeepAgents 框架获得内置中间件能力
- 升级到 VizQL Data Service API 支持表计算
- 保持 StateGraph 固定流程控制
- 100% 复用现有业务组件

### 技术选型

- **DeepAgents**：LangChain 官方 Agent 框架，提供 7 个内置中间件
- **LangGraph StateGraph**：保持固定工作流程控制
- **VizQL Data Service API**：Tableau 2025.1+ 新版 API
- **Pydantic v2**：类型安全的数据模型

## 术语表

- **DeepAgents**: LangChain 官方 Agent 框架，提供中间件系统、工具管理和持久化存储
- **Middleware（中间件）**: DeepAgents 的插件系统，用于增强 Agent 能力
- **StateGraph**: LangGraph 的状态图，用于管理多节点工作流
- **VizQL Data Service**: Tableau 2025.1+ 的查询 API
- **TableCalcField**: 表计算字段，支持累计、排名、移动平均等高级分析
- **VizQLContext**: 运行时上下文，包含数据源、用户、会话等不可变信息
- **VizQLState**: 工作流状态，在节点间传递和累积
- **PersistentStore**: SQLite 持久化存储，用于元数据缓存和会话管理

## 需求

### 需求 1：DeepAgents 框架集成

**用户故事:** 作为开发者，我想要集成 DeepAgents 框架，以便利用内置中间件增强系统能力。

#### 验收标准

1. WHEN 创建主 Agent 时 THEN 系统 SHALL 使用 `create_deep_agent()` 函数创建 DeepAgent 实例
2. WHEN 配置 DeepAgent 时 THEN 系统 SHALL 自动获得 DeepAgents 框架提供的内置中间件能力（包括任务管理、文件系统处理、对话总结、Prompt 缓存、参数修复、子代理、人工介入等）
3. WHEN 配置 DeepAgent 时 THEN 系统 SHALL 传递空的 subagents 列表以禁用 SubAgentMiddleware 的子代理功能
4. WHEN 配置 DeepAgent 时 THEN 系统 SHALL 传递 PersistentStore 实例用于持久化存储
5. WHEN 使用 Claude 模型时 THEN AnthropicPromptCachingMiddleware SHALL 自动启用 Prompt 缓存
6. WHEN 对话超过配置的轮数时 THEN SummarizationMiddleware SHALL 自动触发对话总结
7. WHEN 工具输出超过配置的大小阈值时 THEN FilesystemMiddleware SHALL 自动将结果写入文件系统

### 需求 2：工具层封装

**用户故事:** 作为开发者，我想要将现有组件封装为 LangChain 工具，以便在 DeepAgent 中统一管理和调用。

#### 验收标准

1. WHEN 封装组件时 THEN 系统 SHALL 使用 `@tool` 装饰器将组件封装为 LangChain 工具
2. WHEN 定义工具时 THEN 系统 SHALL 提供完整的 docstring，包括参数说明、返回值说明和使用示例
3. WHEN 创建 DeepAgent 时 THEN 系统 SHALL 配置 7 个核心工具：get_metadata、parse_date、build_vizql_query、execute_vizql_query、semantic_map_fields、process_query_result、detect_statistics
4. WHEN 工具被调用时 THEN 系统 SHALL 保持原有组件的业务逻辑不变
5. WHEN 工具返回结果时 THEN 系统 SHALL 使用 Pydantic 模型验证输出格式
6. WHEN 工具调用失败时 THEN PatchToolCallsMiddleware SHALL 尝试自动修复参数错误

### 需求 3：StateGraph 工作流保持

**用户故事:** 作为开发者，我想要保持 StateGraph 固定工作流，以便确保业务流程的确定性和可控性。

#### 验收标准

1. WHEN 创建工作流时 THEN 系统 SHALL 使用 LangGraph 的 StateGraph 定义 6 个节点：Boost、Understanding、Planning、Execute、Insight、Replanner
2. WHEN 节点执行时 THEN 系统 SHALL 通过 DeepAgent 调用工具，保持原有节点逻辑不变
3. WHEN 节点之间传递数据时 THEN 系统 SHALL 使用 VizQLState 状态对象
4. WHEN boost_question 为 False 时 THEN 系统 SHALL 跳过 Boost 节点直接进入 Understanding 节点
5. WHEN should_replan 为 True 时 THEN 系统 SHALL 从 Replanner 节点路由回 Planning 节点（跳过 Understanding，因为元数据和字段映射已完成，新问题可直接规划）
6. WHEN 重规划次数达到 max_replan_rounds 时 THEN 系统 SHALL 评估当前分析完成度，如果完成度 >= 0.7 则正常结束，否则生成部分结果并提示用户
7. WHEN 工作流完成时 THEN 系统 SHALL 返回符合 VizQLOutput schema 的最终结果
8. WHEN 重规划循环终止时 THEN 系统 SHALL 记录终止原因和当前完成度到 replan_history

### 需求 4：VizQL Data Service API 升级

**用户故事:** 作为开发者，我想要升级到新版 VizQL Data Service API，以便支持表计算等高级功能。

#### 验收标准

1. WHEN 执行查询时 THEN 系统 SHALL 向 `/api/v1/vizql-data-service/query-datasource` 端点发送 POST 请求
2. WHEN 获取元数据时 THEN 系统 SHALL 向 `/api/v1/vizql-data-service/read-metadata` 端点发送 POST 请求
3. WHEN 构建查询时 THEN 系统 SHALL 使用 Pydantic 模型验证请求参数
4. WHEN 接收响应时 THEN 系统 SHALL 使用 Pydantic 模型验证响应数据
5. WHEN API 调用失败时 THEN 系统 SHALL 实现带指数退避的重试逻辑
6. WHEN 配置 SSL 时 THEN 系统 SHALL 支持三种模式：系统默认 CA、禁用验证、自定义 CA 证书

### 需求 5：表计算支持

**用户故事:** 作为开发者，我想要支持表计算功能，以便用户可以进行累计、排名、移动平均等高级分析。

#### 验收标准

1. WHEN 定义表计算字段时 THEN 系统 SHALL 支持 TableCalcField 类型，包含 tableCalculation 必需字段
2. WHEN 指定表计算类型时 THEN 系统 SHALL 支持 10 种类型：RUNNING_TOTAL、MOVING_CALCULATION、RANK、PERCENTILE、PERCENT_OF_TOTAL、PERCENT_FROM、PERCENT_DIFFERENCE_FROM、DIFFERENCE_FROM、CUSTOM、NESTED
3. WHEN Understanding Agent 分析用户问题时 THEN 系统 SHALL 识别表计算需求并在 QuestionUnderstanding 中标记 table_calc_type 字段
4. WHEN Planning Agent 处理包含表计算需求的子问题时 THEN 系统 SHALL 创建 TableCalcIntent 对象，包含 dimensions 字段
5. WHEN QueryBuilder 处理 TableCalcIntent 时 THEN 系统 SHALL 将其转换为 TableCalcField 和相应的 TableCalcSpecification
6. WHEN 用户问题包含"累计"、"running total"关键词时 THEN Understanding Agent SHALL 识别为 RUNNING_TOTAL 表计算需求
7. WHEN 用户问题包含"排名"、"rank"关键词时 THEN Understanding Agent SHALL 识别为 RANK 表计算需求
8. WHEN 用户问题包含"移动平均"、"moving average"关键词时 THEN Understanding Agent SHALL 识别为 MOVING_CALCULATION 表计算需求
9. WHEN 确定表计算 dimensions 时 THEN 系统 SHALL 将计算操作 ACROSS 的字段放入 dimensions，将计算 RESTART 的字段排除在 dimensions 之外
10. WHEN 表计算涉及多个维度时 THEN 系统 SHALL 根据业务语义确定 dimensions：dimensions 中的字段定义计算作用域，不在 dimensions 中的字段定义独立计算组

### 需求 6：STRING 日期字段支持

**用户故事:** 作为开发者，我想要支持 STRING 类型的日期字段，以便系统能够处理各种日期格式的数据源。

#### 验收标准

1. WHEN 检测字段类型时 THEN 系统 SHALL 识别 STRING 类型字段中包含的日期数据
2. WHEN 分析样本值时 THEN 系统 SHALL 自动检测日期格式，支持至少 10 种常见格式
3. WHEN 检测日期格式时 THEN 系统 SHALL 使用样本值进行模式匹配，置信度阈值为 0.7
4. WHEN 检测置信度低于 0.7 时 THEN 系统 SHALL 返回 UNKNOWN 格式类型并记录警告日志
5. WHEN 样本值为空或全部无效时 THEN 系统 SHALL 返回 UNKNOWN 格式类型
6. WHEN 遇到美式和欧式格式歧义时 THEN 系统 SHALL 通过分析日期范围进行区分
7. WHEN 字段为 STRING 类型日期时 THEN 系统 SHALL 在查询中使用 DATEPARSE 计算字段进行转换
8. WHEN 转换日期格式时 THEN 系统 SHALL 将所有日期统一转换为 ISO 格式
9. WHEN STRING 日期字段需要精确匹配筛选时 THEN 系统 SHALL 使用 SetFilter 配合原始格式的日期值
10. WHEN STRING 日期字段需要范围筛选时 THEN 系统 SHALL 使用 DATEPARSE 转换后配合 QuantitativeDateFilter
11. WHEN STRING 日期字段需要模糊匹配时 THEN 系统 SHALL 使用 MatchFilter 配合日期字符串模式

### 需求 7：错误处理和重试

**用户故事:** 作为开发者，我想要实现全面的错误处理，以便系统优雅地处理各种错误场景。

#### 验收标准

1. WHEN API 调用失败时 THEN 系统 SHALL 解析错误响应并提取结构化错误信息
2. WHEN 身份验证失败时 THEN 系统 SHALL 检测 401/403 错误并提供清晰的身份验证指导
3. WHEN 验证失败时 THEN 系统 SHALL 检测 400 错误并提供字段级验证反馈
4. WHEN 服务器错误发生时 THEN 系统 SHALL 检测 500 错误并实现带指数退避的重试逻辑
5. WHEN 网络错误发生时 THEN 系统 SHALL 检测连接失败并提供适当的回退行为
6. WHEN 工具调用参数错误时 THEN PatchToolCallsMiddleware SHALL 尝试自动修复参数

### 需求 8：持久化存储

**用户故事:** 作为开发者，我想要使用持久化存储，以便缓存元数据和管理会话状态。

#### 验收标准

1. WHEN 创建 Store 时 THEN 系统 SHALL 使用 SQLite 作为持久化后端
2. WHEN 获取元数据时 THEN 系统 SHALL 使用可配置的 TTL 缓存元数据响应
3. WHEN 存储维度层级时 THEN 系统 SHALL 按数据源 LUID 分区存储
4. WHEN 存储 Tableau 配置时 THEN 系统 SHALL 安全存储认证信息
5. WHEN 清理过期数据时 THEN 系统 SHALL 自动清理超过 TTL 的缓存条目

### 需求 9：测试覆盖

**用户故事:** 作为开发者，我想要实现全面的测试，以便验证重构的正确性。

#### 验收标准

1. WHEN 运行单元测试时 THEN 系统 SHALL 测试工具封装、中间件配置和 StateGraph 节点
2. WHEN 测试工具层时 THEN 系统 SHALL 验证工具保持原有组件的业务逻辑
3. WHEN 测试 StateGraph 时 THEN 系统 SHALL 验证节点执行顺序和条件路由
4. WHEN 运行属性测试时 THEN 系统 SHALL 使用 Hypothesis 库，每个测试至少 200 次迭代
5. WHEN 运行集成测试时 THEN 系统 SHALL 验证完整的查询流程和重规划流程

### 需求 10：性能要求

**用户故事:** 作为用户，我想要系统具有良好的响应性能，以便获得流畅的使用体验。

#### 验收标准

1. WHEN 执行单次 VizQL 查询时 THEN 系统 SHALL 在 30 秒内返回结果（不含网络延迟）
2. WHEN 获取元数据时 THEN 系统 SHALL 在 10 秒内返回结果（首次请求）
3. WHEN 使用缓存获取元数据时 THEN 系统 SHALL 在 100 毫秒内返回结果
4. WHEN 处理并发请求时 THEN 系统 SHALL 支持至少 10 个并发会话
5. WHEN VizQL 客户端发起请求时 THEN 系统 SHALL 使用连接池复用 HTTP 连接

### 需求 11：配置管理

**用户故事:** 作为系统管理员，我想要配置系统参数，以便根据部署环境调整行为。

#### 验收标准

1. WHEN 配置 SSL 时 THEN 系统 SHALL 支持环境变量 VIZQL_VERIFY_SSL 控制 SSL 验证行为
2. WHEN 配置超时时 THEN 系统 SHALL 支持环境变量 VIZQL_TIMEOUT 设置 API 调用超时时间
3. WHEN 配置重试时 THEN 系统 SHALL 支持环境变量 VIZQL_MAX_RETRIES 设置最大重试次数
4. WHEN 配置模型时 THEN 系统 SHALL 支持环境变量 MODEL_PROVIDER 和 MODEL_NAME 配置 LLM 模型
5. WHEN 配置 DeepAgents 时 THEN 系统 SHALL 支持环境变量配置中间件参数（总结阈值、文件大小阈值等）
