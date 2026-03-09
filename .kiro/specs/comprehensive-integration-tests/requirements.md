# 需求文档 - 完整集成测试套件

## 引言

Analytics Assistant 是一个基于 LangGraph 的数据分析助手系统，目前已实现核心功能但缺少完整的端到端集成测试。本文档定义了一套完整的集成测试规范，确保系统在真实环境下的可靠性和正确性。

## 术语表

- **System**: Analytics Assistant 数据分析助手系统
- **Integration_Test**: 使用真实服务（LLM、Embedding、Tableau）的端到端测试
- **Test_Suite**: 集成测试套件，包含多个测试场景
- **Semantic_Parser**: 语义解析 Agent，将自然语言转换为结构化查询
- **Field_Mapper**: 字段映射 Agent，将业务术语映射到技术字段
- **Field_Semantic**: 字段语义推断 Agent，推断字段的维度/度量属性
- **Insight_Agent**: 洞察生成 Agent，基于查询结果生成数据洞察
- **Replanner**: 重规划 Agent，生成后续分析问题
- **VizQL**: Tableau 查询语言
- **SSE**: Server-Sent Events，服务器推送事件流
- **PBT**: Property-Based Testing，基于属性的测试
- **Round_Trip**: 往返测试，验证序列化/反序列化的对称性
- **Datasource**: Tableau 数据源
- **Real_Service**: 真实外部服务（DeepSeek LLM、Zhipu Embedding、Tableau Cloud）

## 需求

### 需求 1: 端到端语义解析测试

**用户故事:** 作为测试工程师，我希望验证从用户问题到结构化查询的完整流程，以确保语义解析的正确性。

#### 验收标准

1. WHEN 提供简单数据查询问题（单维度单度量），THE System SHALL 正确解析为 SemanticOutput
2. WHEN 提供多维度多度量查询问题，THE System SHALL 正确识别所有维度和度量字段
3. WHEN 提供带筛选条件的查询问题，THE System SHALL 正确解析筛选器类型和值
4. WHEN 提供带时间范围的查询问题，THE System SHALL 正确解析时间维度和日期范围
5. WHEN 提供带计算字段的查询问题，THE System SHALL 正确生成计算表达式
6. WHEN 提供带排序和限制的查询问题，THE System SHALL 正确解析排序字段和限制数量
7. WHEN 提供带聚合函数的查询问题，THE System SHALL 正确识别聚合类型（SUM、AVG、COUNT 等）
8. FOR ALL 有效查询，解析结果 SHALL 包含置信度分数（0.0-1.0）
9. FOR ALL 解析结果，字段名称 SHALL 与 Datasource Schema 匹配
10. THE System SHALL 在 60 秒内完成单次语义解析

### 需求 2: 字段映射准确性测试

**用户故事:** 作为测试工程师，我希望验证业务术语到技术字段的映射准确性，以确保用户可以使用自然语言描述字段。

#### 验收标准

1. WHEN 提供精确匹配的字段名称，THE Field_Mapper SHALL 返回置信度 >= 0.9 的映射结果
2. WHEN 提供模糊匹配的字段名称，THE Field_Mapper SHALL 返回相似度最高的候选字段
3. WHEN 提供同义词，THE Field_Mapper SHALL 正确映射到对应的技术字段
4. WHEN 提供多个业务术语，THE Field_Mapper SHALL 返回所有字段的映射结果
5. WHEN 提供不存在的字段名称，THE Field_Mapper SHALL 返回空结果或低置信度候选
6. FOR ALL 高置信度映射（>= 0.9），映射结果 SHALL 与预期字段完全匹配
7. FOR ALL 低置信度映射（< 0.7），THE System SHALL 提供多个备选字段
8. THE Field_Mapper SHALL 在 30 秒内完成单次映射

### 需求 3: 查询执行正确性测试

**用户故事:** 作为测试工程师，我希望验证 VizQL 查询生成和执行的正确性，以确保返回准确的数据结果。

#### 验收标准

1. WHEN 提供有效的 SemanticOutput，THE System SHALL 生成语法正确的 VizQL 查询
2. WHEN 执行 VizQL 查询，THE System SHALL 成功连接 Tableau 并返回结果
3. WHEN 查询包含筛选条件，THE System SHALL 正确应用筛选器到查询结果
4. WHEN 查询包含计算字段，THE System SHALL 正确计算派生值
5. WHEN 查询包含聚合函数，THE System SHALL 返回正确的聚合结果
6. WHEN 查询包含排序，THE System SHALL 按指定字段和方向排序结果
7. WHEN 查询包含限制，THE System SHALL 返回不超过限制数量的行
8. IF 查询超时（> 30 秒），THEN THE System SHALL 返回超时错误
9. IF 查询字段不存在，THEN THE System SHALL 返回字段不存在错误
10. FOR ALL 成功查询，结果 SHALL 包含列名和数据行

### 需求 4: 洞察生成质量测试

**用户故事:** 作为测试工程师，我希望验证洞察生成的质量和相关性，以确保 AI 提供有价值的分析。

#### 验收标准

1. WHEN 提供查询结果数据，THE Insight_Agent SHALL 生成至少 1 条洞察
2. WHEN 分析深度为 "detailed"，THE Insight_Agent SHALL 在 5 轮内完成分析
3. WHEN 分析深度为 "comprehensive"，THE Insight_Agent SHALL 在 10 轮内完成分析
4. FOR ALL 生成的洞察，内容 SHALL 与查询结果数据相关
5. FOR ALL 生成的洞察，SHALL 包含数据支持（具体数值或趋势）
6. THE Insight_Agent SHALL 使用 DataProfiler 工具分析数据分布
7. THE Insight_Agent SHALL 识别异常值、趋势、模式等数据特征
8. IF 数据行数 > 1000，THEN THE System SHALL 使用磁盘模式存储数据
9. IF 数据行数 <= 1000，THEN THE System SHALL 使用内存模式存储数据

### 需求 5: API 端点完整性测试

**用户故事:** 作为测试工程师，我希望验证所有 API 端点的功能完整性，以确保前端可以正常调用后端服务。

#### 验收标准

1. WHEN 调用 POST /api/chat/stream，THE System SHALL 返回 SSE 流式响应
2. WHEN 调用 POST /api/sessions，THE System SHALL 创建新会话并返回会话 ID
3. WHEN 调用 GET /api/sessions，THE System SHALL 返回会话列表（支持分页）
4. WHEN 调用 GET /api/sessions/{id}，THE System SHALL 返回指定会话的详细信息
5. WHEN 调用 PUT /api/sessions/{id}，THE System SHALL 更新会话标题
6. WHEN 调用 DELETE /api/sessions/{id}，THE System SHALL 删除指定会话
7. WHEN 调用 GET /api/settings，THE System SHALL 返回用户设置
8. WHEN 调用 PUT /api/settings，THE System SHALL 更新用户设置
9. WHEN 调用 POST /api/feedback，THE System SHALL 保存用户反馈
10. WHEN 调用 GET /health，THE System SHALL 返回健康状态
11. FOR ALL API 端点，响应 SHALL 符合 OpenAPI 规范定义的 Schema
12. FOR ALL 错误情况，API SHALL 返回适当的 HTTP 状态码和错误消息

### 需求 6: 错误处理鲁棒性测试

**用户故事:** 作为测试工程师，我希望验证系统在各种异常情况下的错误处理能力，以确保系统的鲁棒性。

#### 验收标准

1. WHEN 提供无效问题（空字符串、特殊字符），THE System SHALL 返回验证错误
2. WHEN 提供无关问题（非数据分析问题），THE System SHALL 识别为 IRRELEVANT 意图
3. WHEN 数据源不存在，THE System SHALL 返回数据源不存在错误
4. WHEN 字段不存在，THE System SHALL 返回字段不存在错误
5. IF LLM 调用失败，THEN THE System SHALL 重试最多 3 次
6. IF LLM 调用仍失败，THEN THE System SHALL 返回服务不可用错误
7. IF Tableau 连接失败，THEN THE System SHALL 返回连接错误
8. IF 查询超时，THEN THE System SHALL 返回超时错误
9. FOR ALL 错误情况，THE System SHALL 记录详细的错误日志
10. FOR ALL 错误情况，THE System SHALL 返回用户友好的错误消息

### 需求 7: 性能基准测试

**用户故事:** 作为测试工程师，我希望建立性能基准，以监控系统性能并识别性能退化。

#### 验收标准

1. THE System SHALL 在 60 秒内完成单次端到端查询（从问题到结果）
2. THE System SHALL 在 30 秒内完成语义解析
3. THE System SHALL 在 20 秒内完成字段映射
4. THE System SHALL 在 30 秒内完成 VizQL 查询执行
5. THE System SHALL 支持至少 5 个并发查询
6. WHEN 缓存命中时，THE System SHALL 在 5 秒内返回结果
7. THE System SHALL 在处理 30 个字段时，字段语义推断耗时 < 60 秒
8. THE System SHALL 在内存使用 < 2GB 的情况下处理单次查询
9. FOR ALL 性能测试，THE System SHALL 记录详细的性能指标（响应时间、吞吐量、资源使用）

### 需求 8: 跨模块集成测试

**用户故事:** 作为测试工程师，我希望验证多个 Agent 之间的协作正确性，以确保端到端流程的顺畅。

#### 验收标准

1. WHEN 语义解析完成后，THE System SHALL 自动触发字段映射
2. WHEN 字段映射完成后，THE System SHALL 自动触发查询执行
3. WHEN 查询执行完成后，THE System SHALL 自动触发洞察生成
4. WHEN 洞察生成完成后，THE System SHALL 自动触发重规划
5. FOR ALL Agent 之间的数据传递，数据格式 SHALL 保持一致
6. FOR ALL Agent 之间的状态传递，状态 SHALL 正确累积
7. THE System SHALL 在 WorkflowContext 中正确管理认证状态
8. THE System SHALL 在 WorkflowContext 中正确缓存字段值
9. THE System SHALL 在 WorkflowContext 中正确跟踪 Schema 变更

### 需求 9: 数据正确性属性测试

**用户故事:** 作为测试工程师，我希望定义数据正确性属性，以使用 PBT 验证系统在各种输入下的正确性。

#### 验收标准

1. FOR ALL 有效的 SemanticOutput，序列化后反序列化 SHALL 得到等价对象（Round Trip 属性）
2. FOR ALL 字段映射结果，置信度 SHALL 在 [0.0, 1.0] 范围内（Invariant 属性）
3. FOR ALL 查询结果，行数 SHALL <= LIMIT 参数（Invariant 属性）
4. FOR ALL 筛选后的结果，所有行 SHALL 满足筛选条件（Invariant 属性）
5. FOR ALL 排序后的结果，相邻行 SHALL 满足排序顺序（Invariant 属性）
6. FOR ALL 聚合结果，聚合值 SHALL 与原始数据计算结果一致（Model-Based 属性）
7. FOR ALL 缓存操作，写入后读取 SHALL 返回相同值（Round Trip 属性）
8. FOR ALL 幂等操作（如创建索引），重复执行 SHALL 产生相同结果（Idempotence 属性）
9. FOR ALL 配置解析，解析后序列化 SHALL 得到等价配置（Round Trip 属性）

### 需求 10: 测试环境配置

**用户故事:** 作为测试工程师，我希望有明确的测试环境配置要求，以确保测试的可重复性。

#### 验收标准

1. THE Test_Suite SHALL 使用 app.yaml 中配置的真实 Tableau 数据源
2. THE Test_Suite SHALL 使用真实的 DeepSeek LLM 服务
3. THE Test_Suite SHALL 使用真实的 Zhipu Embedding 服务
4. THE Test_Suite SHALL 使用独立的测试数据库（避免污染生产数据）
5. THE Test_Suite SHALL 在测试前清理测试数据
6. THE Test_Suite SHALL 在测试后清理测试数据
7. THE Test_Suite SHALL 支持通过环境变量覆盖配置
8. THE Test_Suite SHALL 记录详细的测试日志到独立文件
9. THE Test_Suite SHALL 生成测试报告（包含通过率、失败原因、性能指标）
10. THE Test_Suite SHALL 支持 CI/CD 环境运行

### 需求 11: 测试数据管理

**用户故事:** 作为测试工程师，我希望有标准化的测试数据集，以确保测试的一致性和覆盖率。

#### 验收标准

1. THE Test_Suite SHALL 包含至少 20 个标准测试问题（覆盖各种查询类型）
2. THE Test_Suite SHALL 包含预期的 SemanticOutput 结果（用于验证）
3. THE Test_Suite SHALL 包含预期的查询结果（用于验证）
4. THE Test_Suite SHALL 包含边界情况测试数据（空值、极值、特殊字符）
5. THE Test_Suite SHALL 包含错误情况测试数据（无效输入、不存在的字段）
6. FOR ALL 测试数据，SHALL 包含详细的注释说明测试目的
7. FOR ALL 测试数据，SHALL 使用真实的 Tableau 数据源字段
8. THE Test_Suite SHALL 支持从 YAML 或 JSON 文件加载测试数据

### 需求 12: 回归测试支持

**用户故事:** 作为测试工程师，我希望集成测试可以作为回归测试运行，以防止功能退化。

#### 验收标准

1. THE Test_Suite SHALL 支持快速模式（仅运行核心测试，< 5 分钟）
2. THE Test_Suite SHALL 支持完整模式（运行所有测试，< 30 分钟）
3. THE Test_Suite SHALL 支持选择性运行（按模块、按标签）
4. THE Test_Suite SHALL 在测试失败时提供详细的失败信息
5. THE Test_Suite SHALL 在测试失败时保存失败时的状态快照
6. THE Test_Suite SHALL 支持并行运行独立测试（提高速度）
7. THE Test_Suite SHALL 生成 JUnit XML 格式的测试报告（用于 CI/CD）
8. THE Test_Suite SHALL 支持测试覆盖率报告
9. THE Test_Suite SHALL 支持性能趋势分析（对比历史数据）

### 需求 13: 多场景覆盖测试

**用户故事:** 作为测试工程师，我希望覆盖各种真实业务场景，以确保系统在实际使用中的可靠性。

#### 验收标准

1. THE Test_Suite SHALL 包含简单查询场景（单维度单度量）
2. THE Test_Suite SHALL 包含复杂查询场景（多维度多度量多筛选）
3. THE Test_Suite SHALL 包含时间序列分析场景（按日期聚合、时间范围筛选）
4. THE Test_Suite SHALL 包含多维分析场景（多个维度交叉分析）
5. THE Test_Suite SHALL 包含计算字段场景（同比、环比、占比）
6. THE Test_Suite SHALL 包含排名场景（Top N、Bottom N）
7. THE Test_Suite SHALL 包含筛选场景（精确匹配、模糊匹配、范围筛选）
8. THE Test_Suite SHALL 包含多轮对话场景（上下文累积、追问）
9. THE Test_Suite SHALL 包含错误恢复场景（重试、降级）
10. THE Test_Suite SHALL 包含并发场景（多用户同时查询）

### 需求 14: Parser 和 Serializer 测试

**用户故事:** 作为测试工程师，我希望验证所有数据解析和序列化的正确性，以确保数据格式的一致性。

#### 验收标准

1. FOR ALL Pydantic 模型，THE System SHALL 提供 JSON 序列化方法
2. FOR ALL Pydantic 模型，THE System SHALL 提供 JSON 反序列化方法
3. FOR ALL 有效的 JSON 数据，反序列化 SHALL 成功并返回模型实例
4. FOR ALL 模型实例，序列化后反序列化 SHALL 得到等价对象（Round Trip 属性）
5. FOR ALL 无效的 JSON 数据，反序列化 SHALL 返回验证错误
6. THE System SHALL 提供 SemanticOutput 的 Pretty Printer
7. THE System SHALL 提供 DataModel 的 Pretty Printer
8. FOR ALL Pretty Printer 输出，解析后 SHALL 得到等价对象（Round Trip 属性）
9. THE System SHALL 验证所有必填字段的存在性
10. THE System SHALL 验证所有字段的类型正确性

## 测试数据要求

### 标准测试问题集

测试套件应包含以下类型的标准测试问题：

1. **简单查询**
   - "显示所有产品的销售额"
   - "各地区的订单数量"
   - "客户总数"

2. **多维度查询**
   - "按地区和产品类别显示销售额"
   - "各年份各季度的利润"

3. **带筛选查询**
   - "2024 年的销售额"
   - "华东地区的订单数量"
   - "销售额大于 10000 的产品"

4. **时间序列查询**
   - "过去 6 个月的销售趋势"
   - "2024 年第一季度的月度销售额"
   - "同比增长率"

5. **计算字段查询**
   - "各产品的利润率"
   - "销售额占比"
   - "环比增长"

6. **排名查询**
   - "销售额前 10 的产品"
   - "订单数量最少的 5 个地区"

7. **复杂查询**
   - "2024 年华东地区销售额前 10 的产品及其利润率"
   - "各季度各产品类别的销售额同比增长率"

### 预期结果数据

每个测试问题应包含：
- 预期的 SemanticOutput（JSON 格式）
- 预期的 VizQL 查询（字符串）
- 预期的查询结果（CSV 或 JSON 格式）
- 预期的置信度范围

### 边界情况数据

- 空字符串问题
- 超长问题（> 1000 字符）
- 特殊字符问题（emoji、中文标点）
- 不存在的字段名称
- 不存在的数据源
- 无效的日期格式
- 无效的数值范围

## 环境配置要求

### 必需的环境变量

```bash
# Tableau 配置（从 app.yaml 读取，可通过环境变量覆盖）
TABLEAU_DOMAIN=https://10ax.online.tableau.com
TABLEAU_SITE=tianci
TABLEAU_JWT_CLIENT_ID=...
TABLEAU_JWT_SECRET=...

# LLM 配置
DEEPSEEK_API_KEY=...
ZHIPU_API_KEY=...

# 测试配置
TEST_MODE=integration
TEST_DATABASE_PATH=analytics_assistant/data/test_storage.db
TEST_LOG_PATH=analytics_assistant/tests/test_outputs/integration_tests.log
```

### 测试数据库配置

测试应使用独立的数据库文件，避免污染生产数据：

```yaml
# test_config.yaml（覆盖 app.yaml）
storage:
  connection_string: analytics_assistant/data/test_storage.db
  namespaces:
    data_model:
      connection_string: analytics_assistant/data/test_data_model.db
    field_semantic_cache:
      connection_string: analytics_assistant/data/test_field_semantic.db
```

### CI/CD 配置

测试应支持在 CI/CD 环境运行：
- 使用环境变量配置敏感信息
- 生成 JUnit XML 格式的测试报告
- 支持并行运行（加速测试）
- 支持测试失败时的快速失败模式

## 正确性属性定义

### Round Trip 属性

用于验证序列化/反序列化的对称性：

```python
# 属性 1: SemanticOutput 序列化往返
FOR ALL valid_semantic_output:
    parsed = SemanticOutput.model_validate_json(
        valid_semantic_output.model_dump_json()
    )
    ASSERT parsed == valid_semantic_output

# 属性 2: 配置解析往返
FOR ALL valid_config:
    serialized = yaml.dump(valid_config)
    parsed = yaml.safe_load(serialized)
    ASSERT parsed == valid_config
```

### Invariant 属性

用于验证不变量：

```python
# 属性 3: 置信度范围不变量
FOR ALL mapping_result:
    ASSERT 0.0 <= mapping_result.confidence <= 1.0

# 属性 4: 查询结果行数不变量
FOR ALL query_result WITH limit:
    ASSERT len(query_result.rows) <= limit

# 属性 5: 筛选结果不变量
FOR ALL filtered_result WITH filter_condition:
    FOR ALL row IN filtered_result.rows:
        ASSERT row.satisfies(filter_condition)
```

### Idempotence 属性

用于验证幂等操作：

```python
# 属性 6: 索引创建幂等性
FOR ALL index_name:
    create_index(index_name)
    result1 = get_index(index_name)
    create_index(index_name)  # 重复创建
    result2 = get_index(index_name)
    ASSERT result1 == result2

# 属性 7: 缓存写入幂等性
FOR ALL key, value:
    cache.set(key, value)
    result1 = cache.get(key)
    cache.set(key, value)  # 重复写入
    result2 = cache.get(key)
    ASSERT result1 == result2 == value
```

### Model-Based 属性

用于验证实现与模型的一致性：

```python
# 属性 8: 聚合结果一致性
FOR ALL query_result WITH aggregation:
    expected = simple_aggregation(query_result.raw_data, aggregation)
    actual = query_result.aggregated_value
    ASSERT abs(expected - actual) < EPSILON

# 属性 9: 排序结果一致性
FOR ALL query_result WITH sort_field, sort_order:
    expected = simple_sort(query_result.rows, sort_field, sort_order)
    actual = query_result.rows
    ASSERT expected == actual
```

### Metamorphic 属性

用于验证变换关系：

```python
# 属性 10: 筛选后行数减少
FOR ALL query_result WITH filter:
    filtered = apply_filter(query_result, filter)
    ASSERT len(filtered.rows) <= len(query_result.rows)

# 属性 11: 排序不改变行数
FOR ALL query_result WITH sort:
    sorted_result = apply_sort(query_result, sort)
    ASSERT len(sorted_result.rows) == len(query_result.rows)
```

## 测试组织结构

建议的测试目录结构：

```
analytics_assistant/tests/integration/
├── __init__.py
├── conftest.py                      # 共享 fixtures
├── test_data/                       # 测试数据
│   ├── questions.yaml               # 标准测试问题
│   ├── expected_outputs.yaml        # 预期输出
│   └── edge_cases.yaml              # 边界情况
├── test_e2e_semantic_parsing.py     # 需求 1
├── test_e2e_field_mapping.py        # 需求 2
├── test_e2e_query_execution.py      # 需求 3
├── test_e2e_insight_generation.py   # 需求 4
├── test_api_endpoints.py            # 需求 5
├── test_error_handling.py           # 需求 6
├── test_performance_benchmarks.py   # 需求 7
├── test_cross_module_integration.py # 需求 8
├── test_data_correctness_pbt.py     # 需求 9（PBT）
├── test_parser_serializer_pbt.py    # 需求 14（PBT）
└── test_multi_scenario.py           # 需求 13
```

## 成功标准

集成测试套件被认为成功实现，当且仅当：

1. 所有 14 个需求的验收标准全部通过
2. 测试覆盖率 >= 80%（针对核心模块）
3. 所有测试可以在 CI/CD 环境自动运行
4. 测试失败时提供清晰的失败原因和调试信息
5. 性能基准测试建立并记录基线数据
6. 测试文档完整，包含运行说明和故障排查指南
