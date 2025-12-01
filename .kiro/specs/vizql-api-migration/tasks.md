# 实施计划

本文档定义了 VizQL API 迁移和 DeepAgents 集成的实施任务列表。任务按照 8 个阶段组织，每个阶段包含具体的编码任务。

## ⚠️ 重要：编码规范

在实施任务前，**必须阅读并遵守**以下规范：

### 📋 Pydantic 数据模型规范

参考文档：`tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md`

**必须遵守**：
1. ✅ 包含 `model_config = ConfigDict(extra="forbid")`
2. ✅ 字段描述格式：Brief description + Usage + Values
3. ✅ 可选字段使用 `Optional[Type]` + `default=None`
4. ✅ 列表字段使用 `default_factory=list`（不要用 `default=[]`）
5. ✅ 添加适当的字段约束（ge, le, min_length, pattern 等）
6. ✅ 在 `json_schema_extra` 中提供示例

**示例**：
```python
class TableCalcIntent(BaseModel):
    """Table calculation intent for expressing table calc requirements."""
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="""Business terminology for the calculation.

Usage:
- Store user's original term (e.g., 'running total sales')

Values: Any business term string"""
    )
    
    confidence: float = Field(
        ge=0, le=1,
        description="""Confidence score for the mapping.

Usage:
- Indicate certainty level

Values: Float between 0 and 1
- 0.9-1.0: Perfect match
- 0.7-0.9: Good match"""
    )
```

### 📝 Prompt 模板规范

参考文档：`tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md`

**必须遵守**：
1. ✅ **全英文编写**（禁止中英文混杂）
2. ✅ 使用 4段式结构（Role, Task, Domain Knowledge, Constraints）
3. ✅ Constraints 使用正面指令（DO/ENSURE），避免负面约束（DON'T）
4. ✅ 根据任务类型设置正确的 temperature（参考 `src/config/model_config.py`）
5. ✅ 示例在 Pydantic 模型中定义，不要硬编码在 Prompt 中

**Temperature 配置**：
- Field Mapping: 0.0（确定性）
- Understanding: 0.1（一致性）
- Task Planner: 0.1（一致性）
- Insight: 0.7（创意性）
- Boost: 0.2（平衡）
- Replanner: 0.2（平衡）

---

## 任务列表

- [ ] 1. 数据模型扩展
  - 添加表计算相关的数据模型（TableCalcField、TableCalcIntent）
  - **⚠️ 必须遵守 Pydantic 数据模型规范**
  - _需求: 7.1, 7.2, 14.4, 15.1-7_

- [x] 1.1 添加 TableCalcSpecification 基类








  - 在 `vizql_types.py` 中创建 TableCalcSpecification 基类
  - 包含 tableCalcType 和 dimensions 字段
  - 使用 Pydantic v2 ConfigDict
  - _需求: 15.2_

- [x] 1.2 添加 RunningTotalTableCalcSpecification


  - 创建累计总计规范类
  - 包含 aggregation、restartEvery、secondaryTableCalculation 字段
  - 添加字段验证
  - _需求: 15.5_

- [x] 1.3 添加 MovingTableCalcSpecification


  - 创建移动计算规范类
  - 包含 aggregation、previous、next、includeCurrent、fillInNull 字段
  - 添加字段验证（previous 和 next >= 0）
  - _需求: 15.4_

- [x] 1.4 添加 RankTableCalcSpecification


  - 创建排名计算规范类
  - 包含 rankType 和 direction 字段
  - 支持 COMPETITION、DENSE、UNIQUE 三种排名类型
  - _需求: 15.6_



- [x] 1.5 添加其他 TableCalcSpecification 子类

  - PercentileTableCalcSpecification
  - PercentOfTotalTableCalcSpecification
  - PercentFromTableCalcSpecification
  - PercentDifferenceFromTableCalcSpecification
  - DifferenceFromTableCalcSpecification
  - CustomTableCalcSpecification
  - NestedTableCalcSpecification


  - _需求: 15.3_

- [x] 1.6 添加 TableCalcField 类

  - 继承 FieldBase
  - 包含 tableCalculation 必需字段

  - 包含 nestedTableCalculations 可选字段
  - 添加 docstring 和示例
  - _需求: 15.1_

- [x] 1.7 更新 VizQLField 联合类型


  - 将 TableCalcField 添加到 VizQLField 联合类型
  - 更新类型注解
  - _需求: 14.4_

- [x] 1.8 编写 TableCalcField 单元测试


  - 测试所有 10 种表计算类型的创建
  - 测试序列化和反序列化
  - 测试字段验证
  - 测试嵌套表计算
  - _需求: 9.5_

- [x] 1.9 编写属性测试：TableCalcField 序列化往返一致性



  - **属性 2: TableCalcField 序列化往返一致性**
  - 使用 Hypothesis 生成随机 TableCalcField
  - 验证序列化后再反序列化产生等价对象
  - 运行 100 次迭代

- [x] 1.10 添加 TableCalcIntent 类


  - 在 `intent.py` 中创建 TableCalcIntent 类
  - 包含 business_term、technical_field、table_calc_type、table_calc_config 字段
  - 添加字段验证
  - 添加 docstring
  - _需求: 7.2, 15.8_



- [x] 1.11 编写 TableCalcIntent 单元测试

  - 测试各种表计算类型的创建
  - 测试序列化和反序列化
  - 测试字段验证
  - _需求: 7.2_




- [x] 1.12 编写属性测试：TableCalcIntent 序列化往返一致性

  - **属性 1: TableCalcIntent 序列化往返一致性**
  - 使用 Hypothesis 生成随机 TableCalcIntent
  - 验证序列化后再反序列化产生等价对象
  - 运行 100 次迭代

- [x] 2. QueryBuilder 扩展





  - 扩展 QueryBuilder 以支持表计算
  - _需求: 3.4, 3.5, 15.9_


- [x] 2.1 添加 build_table_calc_field 方法

  - 在 QueryBuilder 中添加 `build_table_calc_field()` 方法
  - 接受 TableCalcIntent 参数
  - 返回 TableCalcField
  - _需求: 3.4_



- [x] 2.2 实现 RUNNING_TOTAL 类型构建

  - 从 table_calc_config 提取 aggregation、dimensions、restartEvery
  - 创建 RunningTotalTableCalcSpecification
  - 返回 TableCalcField

  - _需求: 3.5, 15.5_


- [x] 2.3 实现 MOVING_CALCULATION 类型构建

  - 从 table_calc_config 提取相关字段
  - 创建 MovingTableCalcSpecification
  - 返回 TableCalcField

  - _需求: 3.5, 15.4_

- [x] 2.4 实现 RANK 类型构建

  - 从 table_calc_config 提取相关字段
  - 创建 RankTableCalcSpecification
  - 返回 TableCalcField
  - _需求: 3.5, 15.6_

- [x] 2.5 实现其他表计算类型构建

  - PERCENTILE
  - PERCENT_OF_TOTAL
  - PERCENT_FROM
  - PERCENT_DIFFERENCE_FROM
  - DIFFERENCE_FROM
  - CUSTOM
  - NESTED
  - _需求: 3.5, 15.3_

- [x] 2.6 更新 build_field 方法

  - 添加 TableCalcIntent 类型检查
  - 调用 build_table_calc_field
  - 保持现有逻辑不变
  - _需求: 3.4_






- [x] 2.7 编写 QueryBuilder 单元测试



  - 测试 TableCalcIntent → TableCalcField 转换
  - 测试所有 10 种表计算类型
  - 测试错误处理
  - _需求: 3.4, 3.5_


- [x] 2.8 编写属性测试：TableCalcIntent 到 TableCalcField 转换正确性

  - **属性 3: TableCalcIntent 到 TableCalcField 转换正确性**
  - 使用 Hypothesis 生成随机 TableCalcIntent
  - 验证 QueryBuilder 生成的 TableCalcField 正确
  - 运行 100 次迭代




- [x] 2.9 编写属性测试：表计算类型完整性

  - **属性 4: 表计算类型完整性**
  - 测试所有 10 种表计算类型
  - 验证每种类型都能正确创建 TableCalcSpecification
  - 运行 100 次迭代

- [x] 2.10 实现 DateFormatDetector 类
  - 在 `tableau_assistant/src/capabilities/date_processing/format_detector.py` 创建 DateFormatDetector
  - 实现 DateFormatType 枚举（13 种格式）
  - 实现 detect_format() 方法（置信度阈值 0.7）
  - 实现 convert_to_iso() 方法
  - 实现 _disambiguate_us_eu_format() 方法
  - 实现 get_format_info() 方法
  - _需求: 24.2, 24.3, 24.4, 24.8_

- [x] 2.11 创建 DateManager 统一管理器
  - 在 `tableau_assistant/src/capabilities/date_processing/manager.py` 创建 DateManager
  - 集成 DateCalculator、DateParser、DateFormatDetector
  - 实现统一的日期功能接口（计算、解析、格式检测）
  - 实现字段格式缓存功能
  - 更新 DateParser 使用 DateCalculator 实例
  - 创建独立的 date_processing capability 模块
  - 从 data_processing 中分离出日期处理功能
  - _需求: 24.10_

- [x] 2.12 集成 DateManager 到 MetadataManager


  - 在 MetadataManager.__init__() 中注入 DateManager
  - 实现 _detect_date_field_formats() 方法（使用 DateManager）
  - 在获取元数据后自动检测 STRING 类型日期字段
  - 实现 get_field_date_format() 方法（从 DateManager 缓存读取）
  - _需求: 24.1, 24.10_

- [x] 2.13 集成 DateManager 到 QueryBuilder



  - 在 QueryBuilder.__init__() 中注入 DateManager
  - 添加 _build_date_filter_for_string_field() 方法
  - 为 STRING 类型日期字段生成 DATEPARSE 计算字段
  - 使用 QuantitativeDateFilter 过滤转换后的日期
  - 根据字段格式转换日期值为 ISO 格式
  - _需求: 24.5, 24.6, 24.8_

- [x] 2.14 编写 DateManager 和日期格式检测单元测试



  - 测试 DateManager 统一接口
  - 测试 13 种日期格式的检测
  - 测试美式/欧式格式区分
  - 测试日期格式转换为 ISO
  - 测试 DATEPARSE 计算字段生成
  - 测试字段格式缓存功能
  - 测试错误处理（无法检测格式）
  - _需求: 24.2, 24.3, 24.4, 24.7_

- [x] 2.15 编写属性测试：日期格式检测一致性



  - **属性 13: 日期格式检测一致性**
  - 生成随机日期样本集
  - 验证多次检测返回相同格式
  - 运行 100 次迭代


- [ ] 2.16 编写属性测试：日期格式转换往返一致性

  - **属性 14: 日期格式转换往返一致性**
  - 生成随机 ISO 日期
  - 转换为其他格式后再转换回 ISO
  - 验证保持不变
  - 运行 100 次迭代


- [ ] 2.17 编写属性测试：美式/欧式格式区分正确性

  - **属性 15: 美式/欧式格式区分正确性**
  - 生成包含明显区分标志的样本集
  - 验证格式检测正确区分

  - 运行 100 次迭代

- [x] 2.18 编写属性测试：STRING 日期字段 DATEPARSE 生成正确性



  - **属性 16: STRING 日期字段 DATEPARSE 生成正确性**
  - 生成随机 STRING 类型日期字段
  - 验证 QueryBuilder 生成正确的 DATEPARSE 公式
  - 运行 100 次迭代

- [ ] 3. VizQL 客户端增强
  - 增强 VizQL 客户端以支持 Pydantic 模型
  - _需求: 13.1-7, 18.1-7_

- [ ] 3.1 更新 query_vds 函数签名
  - 修改 `query_vds()` 接受 Union[Dict, VizQLQuery]
  - 保持向后兼容
  - _需求: 13.2, 18.1_

- [ ] 3.2 添加请求验证
  - 如果输入是 Dict，使用 VizQLQuery 验证
  - 如果输入是 VizQLQuery，直接序列化
  - 使用 model_dump(exclude_none=True)
  - _需求: 13.1, 19.4_

- [ ] 3.3 添加响应验证
  - 使用 QueryOutput 模型验证响应
  - 返回验证后的数据
  - _需求: 13.3_

- [ ] 3.4 添加统一错误处理
  - 创建 ErrorHandler 类
  - 实现错误分类逻辑
  - 实现重试逻辑（指数退避）
  - _需求: 13.7, 18.4_

- [ ] 3.5 添加 SSL 配置支持
  - 从环境变量读取 VIZQL_VERIFY_SSL
  - 从环境变量读取 VIZQL_CA_BUNDLE
  - 传递给 requests.post(verify=...)
  - _需求: 13.4, 18.2, 21.1, 21.2_

- [ ] 3.6 添加超时配置支持
  - 从环境变量读取 VIZQL_TIMEOUT
  - 默认 30 秒
  - 传递给 requests.post(timeout=...)
  - _需求: 18.6, 21.3_

- [ ] 3.7 更新 query_vds_metadata 函数
  - 添加 Pydantic 模型验证
  - 使用 MetadataOutput 验证响应
  - 添加错误处理
  - _需求: 5.3, 13.3_

- [ ] 3.8 编写 VizQL 客户端单元测试
  - 测试 Pydantic 模型输入
  - 测试请求验证
  - 测试响应验证
  - 测试错误处理
  - 测试重试逻辑
  - _需求: 13.1-7_

- [ ] 4. Planning Agent 扩展
  - 扩展 Planning Agent 以识别表计算需求
  - **⚠️ 必须遵守 Prompt 模板规范（全英文、正面指令、正确 temperature）**
  - _需求: 7.7, 15.8-13_

- [ ] 4.1 添加表计算关键词识别
  - 识别"累计"、"running total" → RUNNING_TOTAL
  - 识别"排名"、"rank" → RANK
  - 识别"移动平均"、"moving average" → MOVING_CALCULATION
  - 识别"百分比"、"percent of total" → PERCENT_OF_TOTAL
  - _需求: 15.10, 15.11, 15.12, 15.13_

- [ ] 4.2 实现 TableCalcIntent 生成逻辑
  - 从用户问题提取 business_term
  - 映射到 technical_field（使用元数据）
  - 确定 table_calc_type
  - 构建 table_calc_config
  - _需求: 7.7, 15.8_

- [ ] 4.3 更新系统提示词
  - 添加表计算相关的指导
  - 添加示例
  - 说明何时使用 TableCalcIntent
  - _需求: 7.7_

- [ ] 4.4 更新 Intent 生成逻辑
  - 在现有 Intent 生成中添加 TableCalcIntent 检查
  - 保持现有逻辑不变
  - _需求: 7.7_

- [ ] 4.5 编写 Planning Agent 单元测试
  - 测试关键词识别
  - 测试 TableCalcIntent 生成
  - 测试各种表计算类型
  - _需求: 15.10-13_

- [ ] 4.6 编写属性测试：表计算关键词识别正确性
  - **属性 11: 表计算关键词识别正确性**
  - 生成包含表计算关键词的问题
  - 验证 Planning Agent 生成 TableCalcIntent
  - 运行 100 次迭代

- [ ] 5. 工具封装
  - 将 8 个组件封装为 LangChain 工具
  - _需求: 16.1-7_

- [ ] 5.1 封装 get_metadata 工具
  - 使用 @tool 装饰器
  - 封装 MetadataManager.get_metadata_async
  - 编写完整 docstring（参数、返回值、示例）
  - _需求: 16.1, 16.2_

- [ ] 5.2 封装 parse_date 工具
  - 使用 @tool 装饰器
  - 封装 DateParser 组件
  - 编写完整 docstring
  - _需求: 16.1, 16.2_

- [ ] 5.3 封装 build_vizql_query 工具
  - 使用 @tool 装饰器
  - 封装 QueryBuilder.build_query
  - 支持 TableCalcIntent
  - 编写完整 docstring
  - _需求: 16.1, 16.2_

- [ ] 5.4 封装 execute_vizql_query 工具
  - 使用 @tool 装饰器
  - 封装 QueryExecutor.execute_query
  - 编写完整 docstring
  - _需求: 16.1, 16.2_

- [ ] 5.5 封装 semantic_map_fields 工具
  - 使用 @tool 装饰器
  - 封装 SemanticMapper 组件
  - 编写完整 docstring
  - _需求: 16.1, 16.2_

- [ ] 5.6 封装 process_query_result 工具
  - 使用 @tool 装饰器
  - 封装 DataProcessor 组件
  - 编写完整 docstring
  - _需求: 16.1, 16.2_

- [ ] 5.7 封装 detect_statistics 工具
  - 使用 @tool 装饰器
  - 封装 StatisticsDetector 组件
  - 编写完整 docstring
  - _需求: 16.1, 16.2_

- [ ] 5.8 封装 get_dimension_hierarchy 工具
  - 使用 @tool 装饰器
  - 封装 DimensionHierarchy 组件
  - 编写完整 docstring
  - _需求: 16.1, 16.2_

- [ ] 5.9 编写工具封装单元测试
  - 测试每个工具的 @tool 装饰器
  - 测试 docstring 完整性
  - 测试参数验证
  - _需求: 16.2_

- [ ] 5.10 编写属性测试：工具封装业务逻辑保持
  - **属性 5: 工具封装业务逻辑保持**
  - 生成随机组件输入
  - 验证封装前后输出一致
  - 运行 100 次迭代

- [ ] 6. StateGraph 适配
  - 修改 StateGraph 以使用 DeepAgent
  - _需求: 17.1-7_

- [ ] 6.1 更新 create_vizql_workflow 函数
  - 修改函数以使用 create_tableau_deep_agent
  - 传递 8 个工具
  - 传递模型配置
  - 传递 Store 实例
  - _需求: 17.1_

- [ ] 6.2 确认 Boost 节点实现
  - 验证 Boost 节点使用 DeepAgent
  - 验证 boost_question=False 时跳过逻辑
  - 保持现有逻辑不变
  - _需求: 17.2, 17.4_

- [ ] 6.3 确认 Understanding 节点实现
  - 验证 Understanding 节点使用 DeepAgent
  - 保持现有逻辑不变
  - _需求: 17.2_

- [ ] 6.4 确认 Planning 节点实现
  - 验证 Planning 节点使用 DeepAgent
  - 验证支持 TableCalcIntent
  - 保持现有逻辑不变
  - _需求: 17.2_

- [ ] 6.5 确认 Execute 节点实现
  - 验证 Execute 节点使用 DeepAgent
  - 保持现有逻辑不变
  - _需求: 17.2_

- [ ] 6.6 确认 Insight 节点实现
  - 验证 Insight 节点使用 DeepAgent
  - 保持现有逻辑不变
  - _需求: 17.2_

- [ ] 6.7 确认 Replanner 节点实现
  - 验证 Replanner 节点使用 DeepAgent
  - 验证 should_replan=True 时路由回 Understanding
  - 保持现有逻辑不变
  - _需求: 17.2, 17.5_

- [ ] 6.8 编写 StateGraph 单元测试
  - 测试节点执行顺序
  - 测试 boost_question=False 时跳过 Boost
  - 测试 should_replan=True 时路由
  - 测试重规划次数限制
  - _需求: 17.1-7_

- [ ] 6.9 编写属性测试：StateGraph 节点顺序保持
  - **属性 7: StateGraph 节点顺序保持**
  - 验证节点执行顺序正确
  - 运行 100 次迭代

- [ ] 6.10 编写属性测试：Boost 节点条件跳过
  - **属性 8: Boost 节点条件跳过**
  - 生成随机 boost_question 值
  - 验证跳过逻辑正确
  - 运行 100 次迭代

- [ ] 6.11 编写属性测试：重规划循环路由
  - **属性 9: 重规划循环路由**
  - 验证 should_replan=True 时路由回 Understanding
  - 运行 100 次迭代

- [ ] 6.12 编写属性测试：中间件配置完整性
  - **属性 6: 中间件配置完整性**
  - 生成随机模型配置
  - 验证 6 个必需中间件都被包含
  - 验证 SubAgentMiddleware 不被包含
  - 运行 100 次迭代

- [ ] 7. 集成测试
  - 运行所有测试，确保系统正常工作
  - _需求: 9.1-5, 22.1-7_

- [ ] 7.1 运行所有单元测试
  - 运行 TableCalcField 测试
  - 运行 TableCalcIntent 测试
  - 运行 QueryBuilder 测试
  - 运行 VizQL 客户端测试
  - 运行 Planning Agent 测试
  - 运行工具封装测试
  - 运行 StateGraph 测试
  - 修复所有失败的测试
  - _需求: 22.1_

- [ ] 7.2 运行所有属性测试
  - 运行 12 个正确性属性的属性测试
  - 每个测试至少 100 次迭代
  - 修复所有失败的测试
  - _需求: 22.7_

- [ ] 7.3 运行端到端集成测试
  - 测试完整的查询流程（用户问题 → 洞察）
  - 测试表计算功能（累计、排名、移动平均、百分比）
  - 测试重规划流程
  - 测试中间件协同工作
  - _需求: 22.6_

- [ ] 7.4 测试表计算功能
  - 测试 RUNNING_TOTAL
  - 测试 MOVING_CALCULATION
  - 测试 RANK
  - 测试 PERCENT_OF_TOTAL
  - 测试其他 6 种类型
  - _需求: 9.5_

- [ ] 7.5 性能测试
  - 测量查询响应时间
  - 测量 Prompt 缓存命中率（Claude）
  - 识别性能瓶颈
  - 进行必要的优化
  - _需求: 11.1-5_

- [ ] 7.6 修复发现的问题
  - 修复测试中发现的 bug
  - 修复性能问题
  - 更新文档

- [ ] 8. 文档和部署
  - 更新文档，准备部署
  - _需求: 12.1-5, 23.1-7_

- [ ] 8.1 更新 API 文档
  - 更新 OpenAPI 规范（如果有）
  - 添加表计算 API 说明
  - 添加示例请求和响应
  - _需求: 23.7_

- [ ] 8.2 更新架构文档
  - 更新架构图
  - 说明 DeepAgents 集成
  - 说明表计算支持
  - _需求: 23.1_

- [ ] 8.3 更新工具文档
  - 说明 8 个工具的功能和参数
  - 添加使用示例
  - _需求: 23.2_

- [ ] 8.4 更新中间件文档
  - 说明 6 个中间件的配置和作用
  - 添加配置示例
  - _需求: 23.3_

- [ ] 8.5 更新 StateGraph 文档
  - 说明 6 个节点的功能和路由逻辑
  - 添加流程图
  - _需求: 23.4_

- [ ] 8.6 编写迁移指南
  - 列出迁移步骤
  - 说明破坏性变更（如果有）
  - 提供回滚程序
  - _需求: 12.4, 23.6_

- [ ] 8.7 编写配置文档
  - 列出所有环境变量
  - 提供配置示例
  - 说明默认值
  - _需求: 23.5_

- [ ] 8.8 准备发布说明
  - 列出新功能（表计算支持）
  - 列出改进点（DeepAgents 集成）
  - 列出已知问题
  - _需求: 12.1-5_

- [ ] 8.9 最终检查
  - 确认所有测试通过
  - 确认文档完整
  - 确认代码质量
  - 准备发布

## 检查点

- [ ] 9. 检查点 1 - 数据模型扩展完成
  - 确保所有测试通过，询问用户是否有问题

- [ ] 10. 检查点 2 - QueryBuilder 和 VizQL 客户端完成
  - 确保所有测试通过，询问用户是否有问题

- [ ] 11. 检查点 3 - Planning Agent 和工具封装完成
  - 确保所有测试通过，询问用户是否有问题

- [ ] 12. 检查点 4 - StateGraph 适配完成
  - 确保所有测试通过，询问用户是否有问题

- [ ] 13. 最终检查点 - 所有任务完成
  - 确保所有测试通过，询问用户是否有问题
