# 需求文档：洞察与重规划 Agent

## 简介

本功能为 Analytics Assistant 新增两个独立 Agent：Insight Agent（洞察生成）和 Replanner Agent（重规划），由 WorkflowExecutor 在主循环中编排执行。Insight Agent 通过 ReAct 循环渐进式分析查询结果数据，生成数据洞察；Replanner Agent 基于洞察结果决定是否需要后续分析，并生成新的分析问题或建议问题。

## 术语表

- **Insight_Agent**: 洞察生成 Agent，通过 ReAct 循环和工具调用渐进式分析数据，生成结构化洞察
- **Replanner_Agent**: 重规划 Agent，基于洞察结果决定是否需要后续分析并生成新问题
- **DataStore**: 数据存储后端，负责将大数据集持久化到文件系统（JSON 文件），提供分批读取和按条件筛选接口。位于 `agents/insight/components/data_store.py`
- **DataProfile**: 数据画像，包含预计算的统计信息（数值列：min/max/avg/median/std；分类列：unique_count/top_values），帮助 LLM 了解数据整体特征
- **DataProfiler**: 数据画像生成器，从 ExecuteResult 纯计算生成 DataProfile 的组件，位于 `agents/insight/components/data_profiler.py`
- **ReplanDecision**: 重规划决策模型，包含 should_replan（是否重规划）、reason（原因）、new_question（新问题，自然语言）、suggested_questions（建议问题列表）
- **InsightOutput**: 洞察输出模型，包含 findings（发现列表）、summary（摘要）、overall_confidence（置信度）
- **Finding**: 单条洞察发现，包含 finding_type（类型：异常、趋势、对比、分布等）、description（描述）、supporting_data（支撑数据）、confidence（置信度）
- **WorkflowExecutor**: 工作流执行器，编排 semantic_parser → 查询执行 → DataProfile → 数据持久化 → Insight → Replanner 的主循环
- **ExecuteResult**: 查询执行结果模型，包含 data、columns、row_count 字段（已存在于 core/schemas/）
- **SemanticOutput**: 语义解析输出模型，包含 restated_question、what、where 等字段（已存在于 agents/semantic_parser/schemas/）
- **ReAct_Loop**: ReAct 循环，LLM 通过工具调用（read_data_batch、read_filtered_data、get_column_stats、get_data_profile、finish_insight）分批读取数据并自主决定何时停止分析
- **Replan_History**: 重规划历史，记录之前各轮的 ReplanDecision，防止 Replanner 生成重复问题

## 需求

### 需求 1：数据存储与持久化

**用户故事：** 作为系统开发者，我希望查询结果数据能够持久化到文件系统，以便 Insight Agent 可以分批读取大数据集而不会耗尽内存。

#### 验收标准

1. WHEN ExecuteResult 数据被保存 THEN DataStore SHALL 将数据序列化为 JSON 文件并存储到从 app.yaml 读取的临时目录
2. WHEN 数据行数超过从 app.yaml 读取的内存阈值 THEN DataStore SHALL 自动将数据写入文件而非保留在内存中
3. WHEN 数据行数未超过内存阈值 THEN DataStore SHALL 将数据保留在内存中以提高读取速度
4. WHEN DataStore 接收分批读取请求（指定 offset 和 limit）THEN DataStore SHALL 返回对应范围的数据行
5. WHEN DataStore 接收按列筛选请求（指定列名和筛选值列表）THEN DataStore SHALL 返回满足条件的数据行
6. IF DataStore 读取的文件不存在或已损坏 THEN DataStore SHALL 返回描述性错误信息并记录 error 日志
7. WHEN 会话结束或 DataStore 实例被销毁 THEN DataStore SHALL 清理对应的临时文件

### 需求 2：数据画像生成

**用户故事：** 作为系统开发者，我希望在洞察分析前生成数据画像，以便 LLM 了解数据的整体特征并决定如何探索数据。

#### 验收标准

1. WHEN ExecuteResult 被传入 DataProfiler THEN DataProfiler SHALL 为每个数值列计算 min、max、avg、median、std 统计信息
2. WHEN ExecuteResult 被传入 DataProfiler THEN DataProfiler SHALL 为每个分类列计算 unique_count 和 top_values（按频率排序的前 N 个值，N 从 app.yaml 读取）
3. WHEN ExecuteResult 被传入 DataProfiler THEN DataProfiler SHALL 生成包含 row_count、column_count、columns_profile 的 DataProfile 对象
4. IF ExecuteResult 数据为空 THEN DataProfiler SHALL 返回包含零值统计的 DataProfile 对象
5. IF DataProfiler 计算某列统计信息失败 THEN DataProfiler SHALL 跳过该列并在对应的 ColumnProfile 中标记 error 字段

### 需求 3：Insight Agent ReAct 循环

**用户故事：** 作为用户，我希望系统能够自动分析查询结果数据并生成有价值的洞察，以便我能快速理解数据背后的含义。

#### 验收标准

1. WHEN Insight_Agent 启动分析 THEN Insight_Agent SHALL 接收 DataProfile 作为初始上下文，并在系统 Prompt 中包含 DataProfile 摘要
2. WHEN Insight_Agent 执行 ReAct 循环 THEN Insight_Agent SHALL 在每轮中选择调用 read_data_batch、read_filtered_data、get_column_stats、get_data_profile 或 finish_insight 工具之一
3. WHEN Insight_Agent 调用 finish_insight 工具 THEN Insight_Agent SHALL 结束 ReAct 循环并输出 InsightOutput
4. WHILE Insight_Agent 执行 ReAct 循环 THEN Insight_Agent SHALL 限制最大循环轮数为从 app.yaml 读取的配置值
5. WHEN Insight_Agent 达到最大循环轮数且未调用 finish_insight THEN Insight_Agent SHALL 基于已收集的数据强制生成 InsightOutput
6. WHEN Insight_Agent 生成 InsightOutput THEN InsightOutput SHALL 包含 findings 列表（至少一条 Finding）、summary 摘要和 overall_confidence 置信度
7. WHEN Insight_Agent 生成 Finding THEN 每个 Finding SHALL 包含 finding_type（枚举：anomaly/trend/comparison/distribution/correlation）、description、supporting_data 和 confidence 字段

### 需求 4：Insight Agent 流式输出

**用户故事：** 作为用户，我希望在洞察生成过程中实时看到 LLM 的输出，以便获得更好的交互体验。

#### 验收标准

1. WHILE Insight_Agent 执行 LLM 调用 THEN Insight_Agent SHALL 通过 on_token 回调逐 token 流式输出
2. WHILE Insight_Agent 使用推理模型 THEN Insight_Agent SHALL 通过 on_thinking 回调流式输出思考过程
3. WHEN Insight_Agent 开始和结束 ReAct 循环的每一轮 THEN Insight_Agent SHALL 通过 SSE 事件通知前端当前分析进度（包含当前轮数和工具调用信息）

### 需求 5：Insight Agent 分析深度控制

**用户故事：** 作为用户，我希望能够控制分析的深度，以便在快速概览和深入分析之间选择。

#### 验收标准

1. WHEN analysis_depth 参数为 "detailed" THEN Insight_Agent SHALL 使用标准的 ReAct 循环轮数上限，以描述性洞察为主
2. WHEN analysis_depth 参数为 "comprehensive" THEN Insight_Agent SHALL 使用较多的 ReAct 循环轮数上限，进行深度诊断性分析
3. THE Insight_Agent SHALL 从 app.yaml 读取各深度级别对应的最大循环轮数配置

### 需求 6：Replanner Agent 决策

**用户故事：** 作为用户，我希望系统能够根据洞察结果自动判断是否需要进一步分析，以便发现更深层的数据规律。

#### 验收标准

1. WHEN Replanner_Agent 接收 InsightOutput、SemanticOutput、DataProfile、对话历史和重规划历史 THEN Replanner_Agent SHALL 生成 ReplanDecision
2. WHEN Replanner_Agent 决定需要重规划 THEN ReplanDecision SHALL 包含 should_replan=True、非空的 reason 和非空的 new_question 字段
3. WHEN Replanner_Agent 决定不需要重规划 THEN ReplanDecision SHALL 包含 should_replan=False 和 suggested_questions 列表（至少一条建议）
4. THE Replanner_Agent SHALL 生成多种类型的后续问题，包括但不限于趋势验证、范围扩大、不同角度分析和互补查询
5. WHILE Replanner_Agent 执行 LLM 调用 THEN Replanner_Agent SHALL 通过 on_token 回调逐 token 流式输出
6. WHEN Replanner_Agent 生成 new_question THEN new_question SHALL 为自然语言格式，可直接作为 semantic_parser 的输入
7. WHEN Replanner_Agent 接收重规划历史 THEN Replanner_Agent SHALL 避免生成与历史中已有问题语义重复的 new_question

### 需求 7：WorkflowExecutor 主循环编排

**用户故事：** 作为系统开发者，我希望 WorkflowExecutor 能够编排 semantic_parser → 查询执行 → Insight → Replanner 的循环，以便实现自动化的多轮分析。

#### 验收标准

1. WHEN WorkflowExecutor 执行主循环 THEN WorkflowExecutor SHALL 按顺序执行：semantic_parser → 查询执行 → DataProfile 生成 → 数据持久化 → Insight Agent → Replanner Agent
2. WHEN Replanner_Agent 返回 should_replan=True 且 new_question 非空 THEN WorkflowExecutor SHALL 使用 new_question 作为新问题开始下一轮循环
3. WHEN Replanner_Agent 返回 should_replan=False 或 new_question 为空 THEN WorkflowExecutor SHALL 将 suggested_questions 通过 SSE 事件发送给前端并结束循环
4. WHILE WorkflowExecutor 执行主循环 THEN WorkflowExecutor SHALL 限制最大循环轮数为从 app.yaml 读取的配置值
5. WHEN WorkflowExecutor 达到最大循环轮数 THEN WorkflowExecutor SHALL 结束循环并发送当前轮的 suggested_questions
6. WHEN 每轮循环开始重规划 THEN WorkflowExecutor SHALL 通过 SSE 事件通知前端正在进行重规划及新问题内容
7. WHEN 每轮循环产生查询结果 THEN WorkflowExecutor SHALL 通过 SSE 事件发送 data 和 chart 事件给前端

### 需求 8：配置管理

**用户故事：** 作为系统开发者，我希望所有可调参数通过 app.yaml 配置，以便在不修改代码的情况下调整系统行为。

#### 验收标准

1. THE Insight_Agent SHALL 从 app.yaml 读取 max_react_rounds（默认 10）和各 analysis_depth 对应的轮数映射配置
2. THE Replanner_Agent SHALL 从 app.yaml 读取 max_replan_rounds（默认 10）配置
3. THE DataStore SHALL 从 app.yaml 读取 memory_threshold（行数阈值，默认 1000）和 temp_dir（临时文件目录）配置
4. THE DataProfiler SHALL 从 app.yaml 读取 top_values_count（top values 数量，默认 10）配置
5. THE 中间件 SHALL 从 app.yaml 读取各自的配置参数（重试次数、延迟、token 阈值等）

### 需求 9：Agent 中间件栈

**用户故事：** 作为系统开发者，我希望 Insight Agent 和 Replanner Agent 具备中间件能力，以便实现 LLM 调用重试、工具调用重试、大结果截断、输出验证和消息历史摘要等横切关注点。

#### 验收标准

1. WHEN LLM 调用失败且错误类型为可重试 THEN ModelRetryMiddleware SHALL 使用指数退避策略自动重试，最大重试次数从 app.yaml 读取
2. WHEN LLM 调用重试达到最大次数仍失败 THEN ModelRetryMiddleware SHALL 抛出原始异常并记录 error 日志
3. WHEN 工具调用失败且错误类型为可重试 THEN ToolRetryMiddleware SHALL 自动重试，最大重试次数从 app.yaml 读取
4. WHEN 工具返回结果的 token 数超过从 app.yaml 读取的阈值 THEN FilesystemMiddleware SHALL 将完整结果保存到临时文件并将消息内容替换为截断摘要
5. WHEN LLM 输出的结构化数据不符合业务规则 THEN OutputValidationMiddleware SHALL 抛出 OutputValidationError 触发重试
6. WHEN ReAct 循环中消息历史 token 数超过从 app.yaml 读取的阈值 THEN SummarizationMiddleware SHALL 将早期消息摘要压缩，保留最近 N 轮完整消息
7. THE 中间件 SHALL 通过 `MiddlewareRunner` 的 6 钩子系统（`awrap_model_call`、`awrap_tool_call`、`abefore_model`、`aafter_model` 等）注入，在 ReAct 循环的每轮迭代中执行
8. THE Insight_Agent 中间件栈 SHALL 包含 SummarizationMiddleware、ModelRetryMiddleware、ToolRetryMiddleware、FilesystemMiddleware、OutputValidationMiddleware
9. THE Replanner_Agent 中间件栈 SHALL 包含 ModelRetryMiddleware、OutputValidationMiddleware

### 需求 10：错误处理与降级

**用户故事：** 作为系统开发者，我希望系统在异常情况下能够优雅降级，以便不影响核心查询功能。

#### 验收标准

1. IF Insight_Agent 执行失败 THEN WorkflowExecutor SHALL 跳过洞察生成，返回查询结果并记录 error 日志
2. IF Replanner_Agent 执行失败 THEN WorkflowExecutor SHALL 停止重规划循环，返回当前轮的洞察结果并记录 error 日志
3. IF DataStore 文件写入失败 THEN DataStore SHALL 降级为内存模式并记录 warning 日志
4. IF DataProfiler 计算某列统计信息失败 THEN DataProfiler SHALL 跳过该列并在对应的 ColumnProfile 中标记 error 字段

### 需求 11：数据模型定义

**用户故事：** 作为系统开发者，我希望所有数据模型使用 Pydantic 定义并支持 JSON 序列化，以便在 LangGraph State 中正确传递。

#### 验收标准

1. THE InsightOutput SHALL 使用 Pydantic BaseModel 定义，包含 findings（List[Finding]）、summary（str）和 overall_confidence（float, 0-1）字段
2. THE Finding SHALL 使用 Pydantic BaseModel 定义，包含 finding_type（FindingType 枚举）、description（str）、supporting_data（Dict）和 confidence（float, 0-1）字段
3. THE DataProfile SHALL 使用 Pydantic BaseModel 定义，包含 row_count（int）、column_count（int）和 columns_profile（List[ColumnProfile]）字段
4. THE ReplanDecision SHALL 使用 Pydantic BaseModel 定义，包含 should_replan（bool）、reason（str）、new_question（Optional[str]）和 suggested_questions（List[str]）字段
5. WHEN 数据模型实例调用 model_dump() THEN 数据模型 SHALL 返回可被 JSON 序列化的字典
6. FOR ALL 有效的 InsightOutput 对象，序列化（model_dump）后再反序列化（model_validate）SHALL 产生等价的对象
7. FOR ALL 有效的 ReplanDecision 对象，序列化（model_dump）后再反序列化（model_validate）SHALL 产生等价的对象
8. FOR ALL 有效的 DataProfile 对象，序列化（model_dump）后再反序列化（model_validate）SHALL 产生等价的对象
