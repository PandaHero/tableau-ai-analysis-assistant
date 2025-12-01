# 实施计划：Tableau Assistant 统一重构

本文档定义了统一重构的实施任务列表。任务按照 6 个阶段组织，每个阶段包含具体的编码任务。

## ⚠️ 重要：编码规范

在实施任务前，**必须阅读并遵守**以下规范：

### 📋 Pydantic 数据模型规范

参考文档：`tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md`

**必须遵守**：
1. ✅ 包含 `model_config = ConfigDict(extra="forbid")`
2. ✅ 字段描述格式：Brief description + Usage + Values
3. ✅ 可选字段使用 `Optional[Type]` + `default=None`
4. ✅ 列表字段使用 `default_factory=list`

### 📝 工具封装规范

**必须遵守**：
1. ✅ 使用 `@tool(args_schema=InputSchema)` 装饰器
2. ✅ 提供完整的 docstring（Args、Returns、Example）
3. ✅ 输入输出使用 Pydantic 模型验证
4. ✅ 保持原有组件业务逻辑不变

---

## 已完成的工作（从 vizql-api-migration 继承）

以下任务已在 `vizql-api-migration` spec 中完成：

- [x] TableCalcSpecification 基类和 10 种子类
- [x] TableCalcField 类
- [x] TableCalcIntent 类
- [x] QueryBuilder 表计算支持
- [x] DateFormatDetector 类
- [x] DateManager 统一管理器
- [x] STRING 日期字段 DATEPARSE 支持
- [x] 相关单元测试和属性测试

---

## 任务列表

### 阶段 1: 工具层实现（已重构）

> **重构说明**：工具不再放在单独的 `tools/` 包中，而是分散到各个 capability 包的 `tool.py` 中。
> 每个 capability 包管理自己的工具，导入路径直接反映功能归属。

- [x] 1. 重构工具层结构
  - 移除独立的 `src/tools/` 目录
  - 工具分散到各 capability 包的 `tool.py` 中
  - 每个包通过 `__init__.py` 导出工具
  - _需求: 2.1, 2.2, 2.3_

- [x] 1.1 重构 query 包结构
  - 创建 `query/builder/` 子包（查询构建）
  - 创建 `query/executor/` 子包（查询执行）
  - 每个子包有独立的 `tool.py`
  - _需求: 2.1, 2.2_

- [x] 1.2 封装 build_vizql_query 工具
  - 位置: `capabilities/query/builder/tool.py`
  - 使用 @tool 装饰器
  - 封装 QueryBuilder.build_query()
  - 支持 TableCalcIntent
  - _需求: 2.1, 2.2, 2.4_

- [x] 1.3 封装 execute_vizql_query 工具
  - 位置: `capabilities/query/executor/tool.py`
  - 使用 @tool 装饰器
  - 封装 QueryExecutor.execute_query()
  - _需求: 2.1, 2.2, 2.4_

- [x] 1.4 封装 get_metadata 工具
  - 位置: `capabilities/metadata/tool.py`
  - 使用 @tool 装饰器
  - 封装 MetadataManager.get_metadata()
  - _需求: 2.1, 2.2, 2.4_

- [x] 1.5 封装 parse_date 工具
  - 位置: `capabilities/date_processing/tool.py`
  - 使用 @tool 装饰器
  - 封装 DateManager.parse_time_range()
  - _需求: 2.1, 2.2, 2.4_

- [x] 1.6 封装 semantic_map_fields 工具
  - 位置: `capabilities/semantic_mapping/tool.py`
  - 使用 @tool 装饰器
  - 封装 SemanticMapper.map_fields()
  - _需求: 2.1, 2.2, 2.4_

- [x] 1.7 封装 process_query_result 和 detect_statistics 工具
  - 位置: `capabilities/data_processing/tool.py`
  - 使用 @tool 装饰器
  - 封装 DataProcessor 和 StatisticsDetector
  - _需求: 2.1, 2.2, 2.4_

- [x] 1.8 封装 save_large_result 工具
  - 位置: `capabilities/storage/tool.py`
  - 使用 @tool 装饰器
  - 封装大结果存储功能
  - _需求: 2.1, 2.2, 2.4_

- [x] 1.9 编写工具层单元测试

  - 测试每个工具的输入验证
  - 测试每个工具的输出格式
  - 测试工具保持原有组件逻辑
  - 位置: `tests/unit/test_tools.py`
  - _需求: 9.2_

- [x] 1.10 编写属性测试：工具封装业务逻辑保持

  - **属性 1: 工具封装业务逻辑保持**
  - 生成随机组件输入
  - 验证封装前后输出一致
  - 运行 100 次迭代
  - 位置: `tests/test_tools_properties.py`

### 阶段 2: DeepAgent 集成

- [x] 2. 更新 DeepAgent 创建器



  - 更新 `src/agents/deep_agent_factory.py`
  - 使用 `create_deep_agent()` 函数
  - 配置 subagents=[] 禁用子代理功能
  - _需求: 1.1, 1.2, 1.3, 1.4_

- [x] 2.1 实现 DeepAgent 创建函数


  - 接受 tools、model_name、store、system_prompt 参数
  - 配置内置中间件参数
  - 返回编译后的 DeepAgent
  - _需求: 1.1, 1.2_



- [x] 2.2 添加模型选择逻辑
  - 支持 Claude、DeepSeek、Qwen、OpenAI 模型
  - 根据 MODEL_PROVIDER 环境变量选择
  - Claude 模型自动启用 Prompt 缓存
  - _需求: 1.5, 10.4_

- [x] 2.3 添加 Store 集成
  - 传递 PersistentStore 实例
  - 配置 SQLite 数据库路径
  - _需求: 1.4, 8.1_

- [x] 2.4 编写 DeepAgent 单元测试


  - 测试 DeepAgent 创建
  - 测试工具注入
  - 测试 Store 集成
  - _需求: 9.1_

### 阶段 3: VizQL 客户端增强

- [x] 3. 创建 VizQL 客户端类



  - 创建 `src/bi_platforms/tableau/vizql_client.py`
  - 实现 VizQLClient 类
  - _需求: 4.1, 4.2_



- [x] 3.1 实现 VizQLClientConfig 模型
  - 包含 base_url、verify_ssl、ca_bundle、timeout、max_retries
  - 从环境变量读取默认值
  - _需求: 4.6, 10.1, 10.2, 10.3_

- [x] 3.2 实现 query_datasource 方法
  - 接受 VizQLQuery 或 Dict 输入
  - 使用 Pydantic 验证请求
  - 返回 QueryOutput 对象
  - _需求: 4.1, 4.3, 4.4_

- [x] 3.3 实现 read_metadata 方法
  - 向 read-metadata 端点发送请求
  - 使用 Pydantic 验证响应
  - _需求: 4.2, 4.4_

- [x] 3.4 实现重试逻辑
  - 使用 tenacity 库
  - 指数退避策略
  - 最大重试次数可配置
  - _需求: 4.5, 7.4_

- [x] 3.5 创建 VizQL 异常类
  - 在 `src/exceptions.py` 创建 VizQLError 基类
  - 创建 VizQLAuthError、VizQLValidationError、VizQLServerError、VizQLRateLimitError 子类
  - 实现 is_retryable 属性判断
  - _需求: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 3.6 实现错误处理逻辑
  - 在 VizQLClient 中实现 _handle_error 方法
  - 解析 API 错误响应
  - 根据状态码分类错误类型


  - _需求: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 3.7 编写 VizQL 客户端单元测试







  - 测试请求构建
  - 测试响应解析
  - 测试错误处理

  - 测试重试逻辑
  - 测试连接池复用
  - _需求: 9.1, 10.5_

### 阶段 4: StateGraph 适配


- [ ] 4. 更新 StateGraph 工作流
  - 更新 `src/agents/workflows/vizql_workflow.py`
  - 集成 DeepAgent

  - _需求: 3.1, 3.2, 3.3_

- [x] 4.1 更新 create_vizql_workflow 函数

  - 接受 DeepAgent 实例参数

  - 保持 6 个节点结构
  - _需求: 3.1_

- [x] 4.2 更新 Boost 节点

  - 通过 DeepAgent 调用工具
  - 保持现有逻辑
  - _需求: 3.2, 3.4_

- [x] 4.3 更新 Understanding 节点

  - 通过 DeepAgent 调用工具
  - 保持现有逻辑
  - _需求: 3.2_







- [x] 4.4 更新 Planning 节点

  - 通过 DeepAgent 调用工具
  - 支持 TableCalcIntent
  - 保持现有逻辑
  - _需求: 3.2, 5.3, 5.4_

- [x] 4.5 创建 Execute 节点（纯执行节点，非 Agent）

  - 在 `src/agents/nodes/` 创建 `execute.py` 文件
  - 实现 execute_query_node 函数（确定性执行，不使用 LLM）

  - 遍历 query_plan.subtasks，对每个 QuerySubTask：
    - 调用 QueryBuilder.build_query() 构建 VizQL 查询
    - 调用 VizQLClient.query_datasource() 执行查询
    - 收集结果到 subtask_results

  - 使用新的 VizQLClient（带连接池）
  - _需求: 3.2_

- [x] 4.6 更新 Insight 节点

  - 通过 DeepAgent 调用工具

  - 保持现有逻辑
  - _需求: 3.2_


- [ ] 4.7 更新 Replanner 节点
  - 通过 DeepAgent 调用工具

  - 保持重规划逻辑
  - _需求: 3.2, 3.5, 3.6_

- [x] 4.7.1 实现 completeness_score 计算逻辑



  - 在 Replanner 节点中实现完成度评估
  - 评估维度：问题覆盖度、数据完整性、洞察深度、异常处理
  - 返回 0.0-1.0 之间的分数
  - _需求: 3.6_

- [x] 4.8 验证路由逻辑

  - 验证 should_boost 条件
  - 验证 should_replan 条件
  - 验证重规划次数限制
  - _需求: 3.4, 3.5, 3.6_


- [ ] 4.9 编写 StateGraph 单元测试

  - 测试节点执行顺序
  - 测试条件路由
  - 测试重规划循环
  - _需求: 9.3_

- [x] 4.10 编写属性测试：StateGraph 节点顺序保持



  - **属性 2: StateGraph 节点顺序保持**
  - 验证节点执行顺序正确
  - 运行 200 次迭代

- [ ] 4.11 编写属性测试：Boost 节点条件跳过

  - **属性 3: Boost 节点条件跳过**
  - 生成随机 boost_question 值
  - 验证跳过逻辑正确
  - 运行 200 次迭代

- [ ] 4.12 编写属性测试：重规划循环路由

  - **属性 4: 重规划循环路由**
  - 验证 should_replan=True 且 completeness_score < 0.9 时路由回 Planning（跳过 Understanding）
  - 运行 200 次迭代

- [ ] 4.13 编写属性测试：TableCalcIntent 转换正确性

  - **属性 5: TableCalcIntent 到 TableCalcField 转换正确性**
  - 生成随机 TableCalcIntent
  - 验证 QueryBuilder 生成正确的 TableCalcField
  - 运行 200 次迭代
  - _需求: 5.4, 5.5_

- [ ] 4.14 编写属性测试：日期格式检测一致性

  - **属性 6: 日期格式检测一致性**
  - 生成相同格式的日期样本集
  - 验证多次检测返回相同格式类型
  - 运行 200 次迭代
  - _需求: 6.3_

- [ ] 4.15 编写属性测试：STRING 日期字段 DATEPARSE 生成

  - **属性 7: STRING 日期字段 DATEPARSE 生成正确性**
  - 生成随机 STRING 类型日期字段
  - 验证 QueryBuilder 生成正确的 DATEPARSE 公式
  - 运行 200 次迭代
  - _需求: 6.7_

- [ ] 4.16 编写属性测试：Pydantic 模型验证

  - **属性 8: Pydantic 模型验证正确性**
  - 生成无效的字段或过滤器定义
  - 验证 Pydantic 抛出 ValidationError
  - 运行 200 次迭代
  - _需求: 4.3, 4.4_

- [ ] 4.17 编写属性测试：表计算 dimensions 子集验证

  - **属性 9: 表计算 dimensions 子集验证**
  - 生成随机表计算查询
  - 验证 dimensions 是查询维度字段的子集
  - 运行 200 次迭代
  - _需求: 5.9, 5.10_

- [ ] 4.18 编写属性测试：智能终止策略

  - **属性 10: 智能终止策略正确性**
  - 生成随机 completeness_score 值
  - 验证 score >= 0.9 时终止重规划
  - 运行 200 次迭代
  - _需求: 3.6_

- [ ] 4.19 编写属性测试：表计算关键词识别

  - **属性 11: 表计算关键词识别正确性**
  - 生成包含表计算关键词的用户问题
  - 验证 Understanding Agent 正确识别表计算类型
  - 运行 200 次迭代
  - _需求: 5.6, 5.7, 5.8_

- [ ] 4.20 编写属性测试：持久化存储 TTL

  - **属性 12: 持久化存储 TTL 正确性**
  - 生成带 TTL 的缓存条目
  - 验证超过 TTL 后条目被清理或标记过期
  - 运行 200 次迭代
  - _需求: 8.2, 8.5_

- [ ] 4.21 编写属性测试：连接池复用

  - **属性 13: VizQL 客户端连接池复用**
  - 发起连续 API 请求
  - 验证 HTTP 连接被复用
  - 运行 200 次迭代
  - _需求: 10.5_

### 阶段 5: 集成测试

- [ ] 5. 运行所有测试
  - 运行单元测试
  - 运行属性测试
  - 修复发现的问题
  - _需求: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 5.1 运行工具层测试
  - 运行 7 个工具的单元测试
  - 验证工具封装正确性
  - _需求: 9.2_

- [ ] 5.2 运行 DeepAgent 测试
  - 运行 DeepAgent 创建测试
  - 验证中间件配置
  - _需求: 9.1_

- [ ] 5.3 运行 VizQL 客户端测试
  - 运行客户端单元测试
  - 验证请求/响应处理
  - _需求: 9.1_

- [ ] 5.4 运行 StateGraph 测试
  - 运行工作流测试
  - 验证节点执行和路由
  - _需求: 9.3_

- [ ] 5.5 运行属性测试
  - 运行所有属性测试
  - 每个测试至少 200 次迭代
  - _需求: 9.4_

- [ ] 5.6 运行端到端集成测试
  - 测试完整查询流程
  - 测试表计算功能
  - 测试重规划流程
  - _需求: 9.5_

- [ ] 5.7 修复发现的问题
  - 修复测试中发现的 bug
  - 更新相关代码

### 阶段 6: 文档和部署

- [ ] 6. 更新文档
  - 更新架构文档
  - 更新 API 文档
  - 更新配置文档

- [ ] 6.1 更新架构文档
  - 说明 DeepAgents 集成
  - 说明工具层设计
  - 添加架构图

- [ ] 6.2 更新工具文档
  - 说明 7 个工具的功能和参数
  - 添加使用示例

- [ ] 6.3 更新配置文档
  - 列出所有环境变量
  - 提供配置示例
  - 说明默认值

- [ ] 6.4 编写迁移指南
  - 列出迁移步骤
  - 说明破坏性变更
  - 提供回滚程序

- [ ] 6.5 最终检查
  - 确认所有测试通过
  - 确认文档完整
  - 准备发布

---

## 检查点

- [ ] 检查点 1 - 工具层完成
  - 确保所有工具测试通过
  - 询问用户是否有问题

- [ ] 检查点 2 - DeepAgent 和 VizQL 客户端完成
  - 确保所有测试通过
  - 询问用户是否有问题

- [ ] 检查点 3 - StateGraph 适配完成
  - 确保所有测试通过
  - 询问用户是否有问题

- [ ] 检查点 4 - 集成测试完成
  - 确保所有测试通过
  - 询问用户是否有问题

- [ ] 最终检查点 - 所有任务完成
  - 确保所有测试通过
  - 确认文档完整
  - 准备发布

---

## 时间估算

| 阶段 | 任务数 | 预计时间 | 状态 |
|------|--------|---------|------|
| 阶段 1: 工具层实现 | 10 | 3 天 | ✅ 已完成（重构） |
| 阶段 2: DeepAgent 集成 | 4 | 2 天 | 待开始 |
| 阶段 3: VizQL 客户端增强 | 7 | 2.5 天 | 待开始 |
| 阶段 4: StateGraph 适配 | 22 | 6 天 | 待开始 |
| 阶段 5: 集成测试 | 7 | 3 天 | 待开始 |
| 阶段 6: 文档和部署 | 5 | 2 天 | 待开始 |
| **总计** | **55** | **18.5 天（约 3.5 周）** |

---

## 注意事项

1. **保持向后兼容**：所有现有 API 接口保持不变
2. **渐进式迁移**：每个阶段完成后进行测试验证
3. **代码复用**：100% 复用现有业务组件
4. **类型安全**：全面使用 Pydantic v2 模型
5. **测试覆盖**：每个组件都有对应的测试
