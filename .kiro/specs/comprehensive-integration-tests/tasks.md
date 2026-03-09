# 实现计划: 完整集成测试套件

## 概述

本实现计划基于 design.md 中定义的 6 个阶段实现路线图，创建一套完整的集成测试套件。测试套件使用真实服务（DeepSeek LLM、Zhipu Embedding、Tableau Cloud）进行端到端测试，确保 Analytics Assistant 系统在生产环境下的可靠性和正确性。

实现周期：8-12 周
测试覆盖：14 个核心需求，81 个验收标准，10 个正确性属性

## 任务

- [-] 1. 阶段 1: 基础设施搭建（1-2 周）
  - [x] 1.1 创建测试基础设施核心组件
    - 创建 `analytics_assistant/tests/integration/base.py`
    - 实现 `BaseIntegrationTest` 基类，提供测试数据库隔离、日志记录、性能监控
    - 实现类级别和方法级别的 setup/teardown 逻辑
    - 实现测试数据库路径配置和自动清理
    - _需求: 10.4, 10.5, 10.6, 10.8_

  - [x] 1.2 实现测试数据管理器
    - 创建 `analytics_assistant/tests/integration/test_data_manager.py`
    - 实现 `TestDataManager` 类，支持从 YAML 加载测试问题
    - 实现 `TestQuestion` Pydantic 模型
    - 实现按类别、ID 查询测试数据的方法
    - 创建测试数据目录 `analytics_assistant/tests/integration/test_data/`
    - _需求: 11.1, 11.2, 11.6, 11.7, 11.8_

  - [x] 1.3 实现性能监控器
    - 创建 `analytics_assistant/tests/integration/performance_monitor.py`
    - 实现 `PerformanceMonitor` 类，收集性能指标（耗时、内存、API 调用次数）
    - 实现 `PerformanceMetric` 数据模型
    - 实现性能基线加载和对比功能
    - 实现性能退化检测逻辑（阈值可配置）
    - _需求: 7.9, 12.9_

  - [x] 1.4 创建测试配置管理
    - 创建 `analytics_assistant/tests/integration/test_config.yaml`
    - 定义超时配置、数据库配置、日志配置、性能配置、并发配置
    - 创建 `analytics_assistant/tests/integration/config_loader.py`
    - 实现 `TestConfigLoader` 类，支持环境变量覆盖
    - 实现配置验证逻辑
    - _需求: 10.1, 10.2, 10.3, 10.7_

  - [x] 1.5 配置测试环境和 CI/CD
    - 创建 `.github/workflows/integration-tests.yml`
    - 配置 P0（冒烟测试）、P1（核心测试）、P2（完整测试）、P3（性能测试）四个 job
    - 配置环境变量和 secrets
    - 配置测试报告上传和覆盖率上传
    - 创建 `pytest.ini` 配置文件，定义测试标记和并行运行策略
    - _需求: 10.10, 12.6, 12.7_


- [-] 2. 阶段 2: 核心测试实现（2-3 周）
  - [x] 2.1 实现端到端语义解析测试
    - 创建 `analytics_assistant/tests/integration/test_e2e_semantic_parsing.py`
    - 实现简单查询测试（单维度单度量）
    - 实现多维度多度量查询测试
    - 实现带筛选条件的查询测试
    - 实现带时间范围的查询测试
    - 实现带计算字段的查询测试
    - 实现带排序和限制的查询测试
    - 实现带聚合函数的查询测试
    - 验证置信度分数范围
    - 验证字段名称与 Schema 匹配
    - 验证性能要求（<= 30 秒）
    - _需求: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

  - [ ]* 2.2 为语义解析编写属性测试
    - **属性 7: Schema 一致性**
    - **验证: 需求 1.9**
    - 使用 Hypothesis 生成随机问题
    - 验证所有解析的字段名称都在数据源 Schema 中

  - [ ] 2.3 实现字段映射准确性测试
    - 创建 `analytics_assistant/tests/integration/test_e2e_field_mapping.py`
    - 实现精确匹配测试（置信度 >= 0.9）
    - 实现模糊匹配测试
    - 实现同义词映射测试
    - 实现多字段映射测试
    - 实现不存在字段的处理测试
    - 验证高置信度映射的准确性
    - 验证低置信度映射返回多个候选
    - 验证性能要求（<= 20 秒）
    - _需求: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [ ]* 2.4 为字段映射编写属性测试
    - **属性 2: 数据范围不变量（置信度）**
    - **验证: 需求 9.2**
    - 使用 Hypothesis 生成随机映射结果
    - 验证所有置信度分数在 [0.0, 1.0] 范围内

  - [ ] 2.5 实现查询执行正确性测试
    - 创建 `analytics_assistant/tests/integration/test_e2e_query_execution.py`
    - 实现 VizQL 查询生成测试
    - 实现 Tableau 连接和查询执行测试
    - 实现筛选条件应用测试
    - 实现计算字段测试
    - 实现聚合函数测试
    - 实现排序测试
    - 实现限制测试
    - 实现超时错误处理测试
    - 实现字段不存在错误处理测试
    - 验证查询结果包含列名和数据行
    - _需求: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_

  - [ ]* 2.6 为查询执行编写属性测试
    - **属性 2: 数据范围不变量（行数限制）**
    - **验证: 需求 9.3**
    - 使用 Hypothesis 生成随机查询和 limit 参数
    - 验证查询结果行数 <= limit

  - [ ]* 2.7 为查询执行编写筛选和排序属性测试
    - **属性 3: 筛选结果不变量**
    - **验证: 需求 9.4**
    - 使用 Hypothesis 生成随机筛选条件
    - 验证所有筛选后的行满足筛选条件
    - **属性 4: 排序结果不变量**
    - **验证: 需求 9.5**
    - 使用 Hypothesis 生成随机排序规则
    - 验证排序后的相邻行满足排序顺序

  - [ ] 2.8 实现 API 端点完整性测试
    - 创建 `analytics_assistant/tests/integration/test_api_endpoints.py`
    - 使用 FastAPI TestClient 进行测试
    - 实现 POST /api/chat/stream 测试（SSE 流式响应）
    - 实现 POST /api/sessions 测试（创建会话）
    - 实现 GET /api/sessions 测试（会话列表，支持分页）
    - 实现 GET /api/sessions/{id} 测试（会话详情）
    - 实现 PUT /api/sessions/{id} 测试（更新会话）
    - 实现 DELETE /api/sessions/{id} 测试（删除会话）
    - 实现 GET /api/settings 测试（获取设置）
    - 实现 PUT /api/settings 测试（更新设置）
    - 实现 POST /api/feedback 测试（保存反馈）
    - 实现 GET /health 测试（健康检查）
    - 验证所有响应符合 OpenAPI Schema
    - 验证错误情况返回适当的 HTTP 状态码
    - _需求: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12_

  - [ ]* 2.9 为 API 端点编写属性测试
    - **属性 10: API 响应格式一致性**
    - **验证: 需求 5.11**
    - 使用 Hypothesis 生成随机请求数据
    - 使用 OpenAPI Schema 验证器验证所有响应

  - [ ] 2.10 实现错误处理鲁棒性测试
    - 创建 `analytics_assistant/tests/integration/test_error_handling.py`
    - 实现无效问题测试（空字符串、特殊字符）
    - 实现无关问题测试（识别为 IRRELEVANT）
    - 实现数据源不存在错误测试
    - 实现字段不存在错误测试
    - 实现 LLM 调用失败重试测试（最多 3 次）
    - 实现 LLM 调用失败后返回错误测试
    - 实现 Tableau 连接失败错误测试
    - 实现查询超时错误测试
    - 验证所有错误记录详细日志
    - 验证所有错误返回用户友好消息
    - _需求: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

  - [ ]* 2.11 为错误处理编写属性测试
    - **属性 8: 错误处理一致性**
    - **验证: 需求 5.12, 6.9, 6.10**
    - 使用 Hypothesis 生成各种错误场景
    - 验证错误日志、错误消息、HTTP 状态码的一致性


- [ ] 3. 阶段 3: 高级测试实现（2-3 周）
  - [ ] 3.1 实现 SSE 流式响应验证器
    - 创建 `analytics_assistant/tests/integration/sse_validator.py`
    - 实现 `SSEStreamValidator` 类
    - 实现 `SSEEvent` 数据模型
    - 实现 SSE 流解析逻辑（解析 event、data、id 字段）
    - 实现事件顺序验证方法
    - 实现事件数据验证方法
    - 实现按类型获取事件的方法
    - 实现错误事件检测方法
    - 实现获取最终结果的方法
    - _需求: 5.1（SSE 流式响应验证）_

  - [ ] 3.2 实现洞察生成质量测试
    - 创建 `analytics_assistant/tests/integration/test_e2e_insight_generation.py`
    - 实现洞察生成基本测试（至少生成 1 条洞察）
    - 实现 detailed 深度测试（5 轮内完成）
    - 实现 comprehensive 深度测试（10 轮内完成）
    - 验证洞察内容与查询结果相关
    - 验证洞察包含数据支持（数值或趋势）
    - 验证 DataProfiler 工具使用
    - 验证异常值、趋势、模式识别
    - 验证数据存储模式选择（内存 vs 磁盘）
    - _需求: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

  - [ ] 3.3 实现跨模块集成测试
    - 创建 `analytics_assistant/tests/integration/test_cross_module_integration.py`
    - 实现语义解析到字段映射的自动触发测试
    - 实现字段映射到查询执行的自动触发测试
    - 实现查询执行到洞察生成的自动触发测试
    - 实现洞察生成到重规划的自动触发测试
    - 验证 Agent 之间数据格式一致性
    - 验证 Agent 之间状态正确累积
    - 验证 WorkflowContext 认证状态管理
    - 验证 WorkflowContext 字段值缓存
    - 验证 WorkflowContext Schema 变更跟踪
    - _需求: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9_

  - [ ] 3.4 实现多场景覆盖测试
    - 创建 `analytics_assistant/tests/integration/test_multi_scenario.py`
    - 实现简单查询场景测试（单维度单度量）
    - 实现复杂查询场景测试（多维度多度量多筛选）
    - 实现时间序列分析场景测试（按日期聚合、时间范围筛选）
    - 实现多维分析场景测试（多个维度交叉分析）
    - 实现计算字段场景测试（同比、环比、占比）
    - 实现排名场景测试（Top N、Bottom N）
    - 实现筛选场景测试（精确匹配、模糊匹配、范围筛选）
    - 实现多轮对话场景测试（上下文累积、追问）
    - 实现错误恢复场景测试（重试、降级）
    - 实现并发场景测试（多用户同时查询）
    - _需求: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10_

  - [x] 3.5 创建标准测试数据集
    - 创建 `analytics_assistant/tests/integration/test_data/questions.yaml`
    - 定义至少 20 个标准测试问题，覆盖各种查询类型
    - 包含简单查询（3 个）
    - 包含多维度查询（3 个）
    - 包含带筛选查询（3 个）
    - 包含时间序列查询（3 个）
    - 包含计算字段查询（2 个）
    - 包含排名查询（2 个）
    - 包含复杂查询（4 个）
    - 每个问题包含详细注释说明测试目的
    - _需求: 11.1, 11.6_

  - [ ] 3.6 创建预期结果数据集
    - 创建 `analytics_assistant/tests/integration/test_data/expected_outputs.yaml`
    - 为每个测试问题定义预期的 SemanticOutput（JSON 格式）
    - 定义预期的置信度范围
    - 定义预期的字段列表
    - _需求: 11.2_

  - [ ] 3.7 创建边界情况测试数据
    - 创建 `analytics_assistant/tests/integration/test_data/edge_cases.yaml`
    - 定义空字符串问题
    - 定义超长问题（> 1000 字符）
    - 定义特殊字符问题（emoji、中文标点）
    - 定义不存在的字段名称
    - 定义不存在的数据源
    - 定义无效的日期格式
    - 定义无效的数值范围
    - _需求: 11.4, 11.5_


- [ ] 4. 阶段 4: 属性测试实现（1-2 周）
  - [ ] 4.1 创建 Hypothesis 测试策略
    - 创建 `analytics_assistant/tests/integration/strategies.py`
    - 实现 `semantic_output_strategy()` - 生成随机 SemanticOutput
    - 实现 `field_mapping_strategy()` - 生成随机 FieldMapping
    - 实现 `query_result_strategy()` - 生成随机查询结果
    - 实现 `filter_condition_strategy()` - 生成随机筛选条件
    - 实现 `question_strategy()` - 生成随机问题文本
    - 实现 `request_data_strategy()` - 生成随机 API 请求数据
    - 配置 Hypothesis 全局设置（max_examples=100, deadline=60000）
    - _需求: 9（属性测试基础）_

  - [ ] 4.2 实现序列化往返对称性属性测试
    - 创建 `analytics_assistant/tests/integration/test_pbt_serialization.py`
    - **属性 1: 序列化往返对称性**
    - **验证: 需求 9.1, 9.7, 9.9, 14.4**
    - 实现 SemanticOutput 序列化往返测试
    - 实现配置解析往返测试
    - 实现缓存值序列化往返测试
    - 使用 `@given` 装饰器和 Hypothesis 策略
    - 验证 `deserialize(serialize(obj)) == obj`

  - [ ]* 4.3 实现聚合结果一致性属性测试
    - 创建 `analytics_assistant/tests/integration/test_pbt_aggregation.py`
    - **属性 5: 聚合结果一致性**
    - **验证: 需求 9.6**
    - 使用 Hypothesis 生成随机数据和聚合函数
    - 对比系统聚合结果和简单 Python 实现
    - 验证浮点误差在容忍范围内（< 1e-6）
    - 测试 SUM、AVG、COUNT、MIN、MAX 聚合函数

  - [ ]* 4.4 实现幂等操作不变量属性测试
    - 创建 `analytics_assistant/tests/integration/test_pbt_idempotence.py`
    - **属性 6: 幂等操作不变量**
    - **验证: 需求 9.8**
    - 实现索引创建幂等性测试
    - 实现缓存写入幂等性测试
    - 验证重复执行产生相同结果

  - [ ] 4.5 实现 Parser 和 Serializer 测试
    - 创建 `analytics_assistant/tests/integration/test_parser_serializer.py`
    - 实现所有 Pydantic 模型的 JSON 序列化测试
    - 实现所有 Pydantic 模型的 JSON 反序列化测试
    - 实现有效 JSON 数据的反序列化成功测试
    - 实现模型实例序列化后反序列化的等价性测试
    - 实现无效 JSON 数据的验证错误测试
    - 实现 SemanticOutput Pretty Printer 测试
    - 实现 DataModel Pretty Printer 测试
    - 验证 Pretty Printer 输出的往返对称性
    - 验证所有必填字段的存在性
    - 验证所有字段的类型正确性
    - _需求: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10_

  - [ ] 4.6 配置 PBT 测试标记和运行参数
    - 在 `conftest.py` 中配置 Hypothesis 全局设置
    - 注册 "integration" profile（max_examples=100, deadline=60000）
    - 配置 pytest 标记 `@pytest.mark.pbt`
    - 配置 pytest 标记 `@pytest.mark.property(number=X, name="...")`
    - 确保所有属性测试使用正确的标签格式
    - _需求: 9（属性测试配置）_


- [ ] 5. 阶段 5: 性能测试和报告（1 周）
  - [ ] 5.1 实现性能基准测试
    - 创建 `analytics_assistant/tests/integration/test_performance_benchmarks.py`
    - 实现端到端查询性能测试（<= 60 秒）
    - 实现语义解析性能测试（<= 30 秒）
    - 实现字段映射性能测试（<= 20 秒）
    - 实现 VizQL 查询执行性能测试（<= 30 秒）
    - 实现并发查询性能测试（至少 5 个并发）
    - 实现缓存命中性能测试（<= 5 秒）
    - 实现字段语义推断性能测试（30 个字段 < 60 秒）
    - 实现内存使用测试（< 2GB）
    - 记录详细的性能指标（响应时间、吞吐量、资源使用）
    - _需求: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9_

  - [ ]* 5.2 为性能测试编写属性测试
    - **属性 9: 性能要求**
    - **验证: 需求 1.10, 2.8, 7.1-7.8**
    - 使用 Hypothesis 生成随机输入
    - 验证所有操作在规定时间内完成
    - 记录性能指标到 PerformanceMonitor

  - [ ] 5.3 建立性能基线
    - 运行完整的性能测试套件
    - 收集所有测试的性能指标
    - 创建 `analytics_assistant/tests/test_outputs/performance_baseline.json`
    - 记录每个测试的基线时间、内存使用、API 调用次数
    - 文档化性能基线的建立过程
    - _需求: 7.9, 12.9_

  - [ ] 5.4 实现性能回归检测
    - 创建 `scripts/check_performance_regression.py`
    - 实现性能指标加载逻辑
    - 实现性能对比逻辑（当前 vs 基线）
    - 实现退化检测逻辑（可配置阈值，默认 1.2）
    - 实现详细的退化报告生成
    - 集成到 CI/CD workflow 中
    - _需求: 12.9_

  - [ ] 5.5 实现测试报告生成器
    - 创建 `analytics_assistant/tests/integration/report_generator.py`
    - 实现 `TestReportGenerator` 类
    - 实现 HTML 报告生成（包含测试摘要、详情、性能指标）
    - 实现 JUnit XML 报告生成（用于 CI/CD）
    - 实现测试覆盖率报告生成
    - 实现性能趋势图表生成（可选）
    - _需求: 10.9, 12.7_

  - [ ] 5.6 实现错误处理和重试策略
    - 创建 `analytics_assistant/tests/integration/error_handler.py`
    - 实现 `ErrorHandler` 类
    - 实现错误分类（CRITICAL, ERROR, WARNING, INFO）
    - 实现错误上下文记录
    - 实现错误统计和摘要
    - 创建 `analytics_assistant/tests/integration/retry_strategy.py`
    - 实现 `RetryStrategy` 装饰器
    - 实现指数退避重试逻辑
    - 实现可重试异常配置
    - _需求: 6（错误处理）_

  - [ ] 5.7 实现失败快照保存
    - 创建 `analytics_assistant/tests/integration/snapshot.py`
    - 实现 `FailureSnapshot` 类
    - 实现失败状态快照保存逻辑
    - 保存测试名称、时间戳、错误信息、状态数据
    - 实现快照加载和分析功能
    - _需求: 12.5_

  - [ ] 5.8 实现异步测试辅助器
    - 创建 `analytics_assistant/tests/integration/async_helper.py`
    - 实现 `AsyncTestHelper` 类
    - 实现 `@async_test` 装饰器（支持超时控制）
    - 实现 `run_with_timeout` 方法
    - 实现 `gather_with_timeout` 方法（并发运行多个协程）
    - _需求: 7.5（并发测试）_


- [ ] 6. 阶段 6: 文档和优化（1 周）
  - [ ] 6.1 编写测试运行文档
    - 创建 `analytics_assistant/tests/integration/README.md`
    - 文档化测试套件架构和组件
    - 文档化测试运行方式（本地、CI/CD）
    - 文档化测试模式（smoke, core, full, performance）
    - 文档化环境变量配置要求
    - 文档化测试数据准备步骤
    - 提供快速开始指南
    - 提供常见问题解答
    - _需求: 10（测试环境配置）_

  - [ ] 6.2 编写故障排查指南
    - 在 README.md 中添加故障排查章节
    - 文档化常见问题和解决方案
    - 测试超时问题排查
    - 测试数据库冲突问题排查
    - API 认证失败问题排查
    - 性能测试不稳定问题排查
    - 属性测试失败问题排查
    - 提供调试技巧和工具推荐
    - _需求: 12.4（测试失败时提供详细信息）_

  - [ ] 6.3 实现测试选择器和优先级管理
    - 创建 `analytics_assistant/tests/integration/test_selector.py`
    - 实现 `TestSelector` 类
    - 定义测试优先级（P0, P1, P2, P3）
    - 实现按优先级选择测试的逻辑
    - 实现 pytest 标记表达式生成
    - 实现测试文件列表生成
    - 文档化测试标记使用规范
    - _需求: 12.1, 12.2, 12.3_

  - [ ] 6.4 优化测试性能
    - 配置 pytest-xdist 并行运行测试
    - 优化测试数据加载（使用缓存）
    - 优化共享资源管理（session scope fixtures）
    - 实现测试隔离策略（独立数据库、独立缓存）
    - 优化 Hypothesis 策略生成速度
    - 减少不必要的外部 API 调用
    - 确保冒烟测试 < 5 分钟
    - 确保核心测试 < 15 分钟
    - 确保完整测试 < 30 分钟
    - _需求: 12.1, 12.2, 12.6_

  - [ ] 6.5 实现测试数据模型
    - 创建 `analytics_assistant/tests/integration/schemas.py`
    - 实现 `TestQuestion` 模型
    - 实现 `ExpectedSemanticOutput` 模型
    - 实现 `TestResult` 模型
    - 实现 `PerformanceBenchmark` 模型
    - 实现 `TestReport` 模型
    - 实现 `TestConfig` 模型
    - 确保所有模型使用 Pydantic 进行验证
    - _需求: 11（测试数据管理）_

  - [ ] 6.6 创建 conftest.py 共享 fixtures
    - 创建 `analytics_assistant/tests/integration/conftest.py`
    - 实现 `isolated_database` fixture（function scope）
    - 实现 `isolated_cache` fixture（function scope）
    - 实现 `shared_llm` fixture（session scope）
    - 实现 `shared_embeddings` fixture（session scope）
    - 实现 `test_data_manager` fixture（session scope）
    - 实现 `performance_monitor` fixture（session scope）
    - 实现 `test_client` fixture（FastAPI TestClient）
    - 配置 Hypothesis 全局设置
    - 配置 pytest 日志和超时
    - _需求: 10（测试环境配置）_

  - [ ] 6.7 代码审查和重构
    - 审查所有测试代码，确保符合编码规范
    - 消除重复代码，提取公共逻辑
    - 优化测试可读性和可维护性
    - 确保所有测试有清晰的文档字符串
    - 确保所有测试引用正确的需求编号
    - 运行 linter 和 formatter（black, isort, flake8）
    - 确保测试覆盖率 >= 80%
    - _需求: 12.8（测试覆盖率）_

  - [ ] 6.8 最终验证和发布准备
    - 运行完整的测试套件（所有模式）
    - 验证所有 14 个需求的验收标准通过
    - 验证所有 10 个正确性属性测试通过
    - 验证性能基准符合要求
    - 验证 CI/CD 集成正常工作
    - 生成最终测试报告
    - 更新项目文档
    - 准备演示和培训材料
    - _需求: 所有需求的最终验证_

- [ ] 7. Checkpoint - 确保所有测试通过
  - 运行完整的测试套件，确保所有测试通过
  - 验证测试覆盖率 >= 80%
  - 验证性能基准符合要求
  - 验证 CI/CD 集成正常工作
  - 如有问题，请向用户报告

## 注意事项

- 任务标记 `*` 的为可选测试任务（属性测试），可根据时间和优先级决定是否实现
- 所有集成测试必须使用真实服务（DeepSeek LLM、Zhipu Embedding、Tableau Cloud），禁止 Mock
- 每个测试必须引用具体的需求编号，确保可追溯性
- 属性测试必须运行至少 100 次迭代
- 所有测试必须支持在 CI/CD 环境自动运行
- 测试失败时必须提供详细的失败信息和调试上下文
- 性能测试必须建立基线并持续监控性能退化
- 测试数据必须使用真实的 Tableau 数据源字段

## 成功标准

测试套件被认为成功实现，当且仅当：

1. ✅ 所有 14 个需求的验收标准全部通过
2. ✅ 测试覆盖率 >= 80%（针对核心模块）
3. ✅ 所有测试可以在 CI/CD 环境自动运行
4. ✅ 测试失败时提供清晰的失败原因和调试信息
5. ✅ 性能基准测试建立并记录基线数据
6. ✅ 测试文档完整，包含运行说明和故障排查指南
7. ✅ 冒烟测试 < 5 分钟
8. ✅ 核心测试 < 15 分钟
9. ✅ 完整测试 < 30 分钟
10. ✅ 所有属性测试运行 >= 100 次迭代
