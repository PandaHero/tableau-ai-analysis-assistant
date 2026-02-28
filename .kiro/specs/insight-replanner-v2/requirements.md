# 需求文档：洞察与重规划系统 V2 — 根本性重构

## 简介

本功能对 Analytics Assistant 的洞察生成和重规划系统进行根本性重构。V1 版本依赖 ReAct 循环 + Tool Calling 架构，但核心 LLM（DeepSeek R1 via CustomChatLLM）不支持原生 function calling（bind_tools），导致整个工具调用链路失效。V2 版本从架构层面解决此问题，采用"一次性分析 + Prompt 驱动"方案替代 ReAct 循环，同时引入用户可控的重规划问题选择机制和渐进式累积洞察能力。

### V1 核心问题

1. **LLM 不支持工具调用**：CustomChatLLM（DeepSeek R1）的 `bind_tools()` 返回 self，上层检测后降级为无工具模式，LLM 输出空内容。整个 ReAct + Tool Calling 架构在当前 LLM 下完全不可用。
2. **重规划缺乏用户控制**：V1 的重规划要么全自动（系统决定 new_question 直接跑），要么全手动（只给 suggested_questions）。用户无法选择性地执行部分后续问题。
3. **洞察不累积**：每轮分析独立生成 InsightOutput，多轮之间的洞察没有关联和累积，无法形成递进式分析链。
4. **问题质量无保障**：重规划生成的后续问题没有完整性和价值判定机制。

### 设计参考

参考 2025-2026 年高 star 开源项目的架构思路：
- **PandasAI**：一次性将数据摘要注入 Prompt，LLM 直接输出分析结论（无工具调用）
- **LIDA (Microsoft)**：分阶段 Pipeline（Summarize → Goal → Visualize → Evaluate），每阶段独立 LLM 调用
- **Databricks Genie / Lakeview AI**：分层洞察策略（描述性 → 诊断性），优先级驱动
- **Microsoft Fabric Copilot**：渐进式分析，累积上下文

## 术语表

- **Insight_Agent_V2**: 重构后的洞察生成 Agent，采用"数据摘要注入 + 一次性 LLM 分析"方案，不依赖工具调用
- **Replanner_Agent_V2**: 重构后的重规划 Agent，支持多问题生成 + 用户选择机制
- **DataStore**: 数据存储后端（V1 已实现，V2 复用），负责数据持久化和分批读取
- **DataProfiler**: 数据画像生成器（V1 已实现，V2 复用），生成统计摘要
- **DataProfile**: 数据画像模型（V1 已实现，V2 复用）
- **DataSampler**: 新增组件，从 DataStore 中智能采样代表性数据行，注入 Prompt 供 LLM 直接分析
- **InsightOutput**: 洞察输出模型（V2 扩展，新增 round_number 和 cumulative_context 字段）
- **ReplanDecision_V2**: 重构后的重规划决策模型，支持多问题列表 + 优先级 + 预期信息增益评分
- **CumulativeInsightContext**: 新增模型，累积多轮洞察的上下文摘要，供后续轮次参考
- **QuestionCandidate**: 新增模型，表示一个候选后续问题，包含问题文本、类型、预期信息增益评分、优先级
- **One-Shot Analysis**: V2 核心策略 — 将数据画像 + 采样数据 + 用户问题一次性注入 Prompt，LLM 单次调用直接输出结构化洞察，不需要工具调用
- **User Question Selection**: 用户问题选择机制 — 重规划生成多个候选问题后，通过 interrupt() 暂停执行，等待用户选择要执行的问题
- **Cumulative Insight Chain**: 累积洞察链 — 多轮分析的洞察通过 CumulativeInsightContext 串联，后续轮次可参考前序洞察

## 需求

### 需求 1：数据采样组件（DataSampler）

**用户故事：** 作为系统开发者，我希望能从查询结果中智能采样代表性数据行，以便将采样数据直接注入 Prompt 供 LLM 分析，替代 ReAct 循环中的工具调用。

#### 验收标准

1. WHEN DataSampler 接收 DataStore 和 DataProfile THEN DataSampler SHALL 根据数据特征选择采样策略（小数据集全量、大数据集分层采样）
2. WHEN 数据行数 <= 从 app.yaml 读取的 full_sample_threshold THEN DataSampler SHALL 返回全部数据行
3. WHEN 数据行数 > full_sample_threshold THEN DataSampler SHALL 执行分层采样：对每个分类列的 top 值确保覆盖，对数值列确保包含极值（min/max）附近的行，再随机补充至目标采样数
4. THE DataSampler SHALL 从 app.yaml 读取 target_sample_size（目标采样行数）和 full_sample_threshold 配置
5. WHEN DataSampler 生成采样结果 THEN DataSampler SHALL 返回采样行列表和采样策略描述（供 Prompt 说明）
6. IF DataStore 数据为空 THEN DataSampler SHALL 返回空列表和"数据为空"的策略描述

### 需求 2：One-Shot 洞察分析（替代 ReAct 循环）

**用户故事：** 作为用户，我希望系统能快速分析查询结果并生成有价值的洞察，即使底层 LLM 不支持工具调用也能正常工作。

#### 验收标准

1. WHEN Insight_Agent_V2 启动分析 THEN Insight_Agent_V2 SHALL 将 DataProfile 摘要 + DataSampler 采样数据 + 用户问题一次性注入 Prompt，通过单次 LLM 调用生成 InsightOutput
2. WHEN Insight_Agent_V2 执行 LLM 调用 THEN Insight_Agent_V2 SHALL 不依赖任何工具调用（bind_tools / function calling），仅使用 Prompt + JSON Mode 输出
3. WHEN Insight_Agent_V2 生成 InsightOutput THEN InsightOutput SHALL 包含 findings 列表（至少一条）、summary 摘要、overall_confidence 置信度和 round_number 轮次号
4. WHEN analysis_depth 为 "detailed" THEN Insight_Agent_V2 SHALL 以描述性洞察为主（统计摘要、排名、极值、分布概况）
5. WHEN analysis_depth 为 "comprehensive" THEN Insight_Agent_V2 SHALL 进行深度诊断性分析（异常归因、趋势验证、交叉对比），并在 Prompt 中注入更多采样数据
6. WHILE Insight_Agent_V2 执行 LLM 调用 THEN Insight_Agent_V2 SHALL 通过 on_token 回调逐 token 流式输出
7. WHILE Insight_Agent_V2 使用推理模型 THEN Insight_Agent_V2 SHALL 通过 on_thinking 回调流式输出思考过程
8. IF LLM 调用失败 THEN Insight_Agent_V2 SHALL 抛出异常，由上层 WorkflowExecutor 捕获并降级处理

### 需求 3：渐进式累积洞察

**用户故事：** 作为用户，我希望多轮分析的洞察能够累积和关联，以便后续分析能参考前序发现，形成递进式分析链。

#### 验收标准

1. WHEN 第一轮分析完成 THEN WorkflowExecutor SHALL 创建 CumulativeInsightContext，包含第一轮的 InsightOutput 摘要
2. WHEN 后续轮次分析启动 THEN Insight_Agent_V2 SHALL 接收 CumulativeInsightContext 作为额外上下文，注入 Prompt 中
3. WHEN 每轮分析完成 THEN WorkflowExecutor SHALL 将新的 InsightOutput 摘要追加到 CumulativeInsightContext
4. THE CumulativeInsightContext SHALL 包含 previous_rounds 列表（每轮的问题、关键发现摘要、置信度）和 cross_round_patterns 字段（跨轮次发现的模式）
5. WHEN Insight_Agent_V2 接收 CumulativeInsightContext THEN Insight_Agent_V2 SHALL 在 Prompt 中引导 LLM 参考前序发现，避免重复分析，聚焦新增信息

### 需求 4：重规划多问题生成与用户选择

**用户故事：** 作为用户，我希望系统生成多个有价值的后续分析问题，并让我选择要执行哪些，以便我能控制分析方向。

#### 验收标准

1. WHEN Replanner_Agent_V2 执行 THEN Replanner_Agent_V2 SHALL 生成 ReplanDecision_V2，包含 candidate_questions 列表（多个 QuestionCandidate）
2. WHEN Replanner_Agent_V2 生成 QuestionCandidate THEN 每个 QuestionCandidate SHALL 包含 question（自然语言问题）、question_type（趋势验证/范围扩大/角度切换/下钻/互补查询）、expected_info_gain（预期信息增益 0-1）、priority（优先级 1-5，1 最高）和 rationale（推荐理由）
3. WHEN Replanner_Agent_V2 生成 candidate_questions THEN candidate_questions SHALL 按 priority 升序排列，至少包含 2 个不同 question_type 的问题
4. WHEN Replanner_Agent_V2 接收重规划历史 THEN Replanner_Agent_V2 SHALL 避免生成与历史中已有问题语义重复的候选问题
5. WHEN candidate_questions 生成完毕 THEN WorkflowExecutor SHALL 通过 SSE 事件将 candidate_questions 发送给前端，并通过 LangGraph interrupt() 暂停执行等待用户选择
6. WHEN 用户选择了一个或多个问题 THEN WorkflowExecutor SHALL 按优先级顺序依次执行选中的问题（每个问题走完整的 semantic_parser → 查询 → 洞察 流程）
7. WHEN 用户选择不执行任何问题（跳过） THEN WorkflowExecutor SHALL 结束重规划循环
8. WHEN 用户未在超时时间内响应 THEN WorkflowExecutor SHALL 自动选择 priority=1 的最高优先级问题执行（超时时间从 app.yaml 读取）
9. WHILE Replanner_Agent_V2 执行 LLM 调用 THEN Replanner_Agent_V2 SHALL 通过 on_token 回调逐 token 流式输出

### 需求 5：问题质量与完整性判定

**用户故事：** 作为系统开发者，我希望重规划生成的后续问题具有高质量和分析价值，以便避免生成无意义或重复的问题。

#### 验收标准

1. WHEN Replanner_Agent_V2 生成 candidate_questions THEN 每个 QuestionCandidate 的 expected_info_gain SHALL 基于以下因素评估：与已有洞察的差异度、覆盖未探索维度的程度、问题的具体性和可执行性
2. WHEN Replanner_Agent_V2 生成 candidate_questions THEN Replanner_Agent_V2 SHALL 在 Prompt 中引导 LLM 评估每个问题的信息增益，并过滤掉 expected_info_gain < 从 app.yaml 读取的 min_info_gain_threshold 的问题
3. WHEN 所有候选问题的 expected_info_gain 均低于阈值 THEN Replanner_Agent_V2 SHALL 设置 should_continue=False，建议结束分析
4. WHEN Replanner_Agent_V2 生成问题 THEN 每个 question SHALL 为自然语言格式，可直接作为 semantic_parser 的输入
5. THE Replanner_Agent_V2 SHALL 确保生成的问题覆盖多种分析角度（趋势验证、范围扩大、角度切换、下钻、互补查询），不集中在单一类型

### 需求 6：WorkflowExecutor 主循环重构

**用户故事：** 作为系统开发者，我希望 WorkflowExecutor 能编排 V2 版本的洞察和重规划循环，支持用户问题选择和累积洞察。

#### 验收标准

1. WHEN WorkflowExecutor 执行主循环 THEN WorkflowExecutor SHALL 按顺序执行：semantic_parser → 查询执行 → DataProfile 生成 → DataSampler 采样 → Insight_Agent_V2 → Replanner_Agent_V2 → 用户选择 → 循环
2. WHEN 第一轮完成 THEN WorkflowExecutor SHALL 复用 semantic_parser 已产生的 ExecuteResult 和 SemanticOutput
3. WHEN 后续轮次开始 THEN WorkflowExecutor SHALL 使用用户选中的问题重新执行 semantic_parser
4. WHILE WorkflowExecutor 执行主循环 THEN WorkflowExecutor SHALL 限制最大循环轮数为从 app.yaml 读取的配置值
5. WHEN 每轮循环产生查询结果 THEN WorkflowExecutor SHALL 通过 SSE 事件发送 data 和 chart 事件给前端（包含 round 字段）
6. WHEN 每轮洞察生成完毕 THEN WorkflowExecutor SHALL 通过 SSE 事件发送 insight 事件给前端（包含 round 字段）
7. WHEN Insight_Agent_V2 执行失败 THEN WorkflowExecutor SHALL 跳过洞察生成，返回查询结果并记录 error 日志
8. WHEN Replanner_Agent_V2 执行失败 THEN WorkflowExecutor SHALL 停止重规划循环，返回当前轮的洞察结果并记录 error 日志
9. WHEN 循环结束 THEN WorkflowExecutor SHALL 清理 DataStore 临时文件

### 需求 7：配置管理

**用户故事：** 作为系统开发者，我希望所有可调参数通过 app.yaml 配置，以便在不修改代码的情况下调整系统行为。

#### 验收标准

1. THE Insight_Agent_V2 SHALL 从 app.yaml 读取 analysis_depth 对应的采样数据量配置（detailed 较少、comprehensive 较多）
2. THE Replanner_Agent_V2 SHALL 从 app.yaml 读取 max_replan_rounds（默认 5）和 min_info_gain_threshold（默认 0.3）配置
3. THE DataSampler SHALL 从 app.yaml 读取 target_sample_size（默认 50）和 full_sample_threshold（默认 50）配置
4. THE WorkflowExecutor SHALL 从 app.yaml 读取 user_selection_timeout（用户选择超时秒数，默认 300）配置
5. THE 所有配置 SHALL 有合理的默认值，配置加载失败时使用默认值并记录 warning 日志

### 需求 8：数据模型定义

**用户故事：** 作为系统开发者，我希望所有新增和修改的数据模型使用 Pydantic 定义并支持 JSON 序列化。

#### 验收标准

1. THE InsightOutput SHALL 在 V1 基础上新增 round_number（int，轮次号）字段
2. THE CumulativeInsightContext SHALL 使用 Pydantic BaseModel 定义，包含 previous_rounds（list[RoundSummary]）和 cross_round_patterns（list[str]）字段
3. THE RoundSummary SHALL 使用 Pydantic BaseModel 定义，包含 round_number（int）、question（str）、key_findings（list[str]）和 confidence（float）字段
4. THE QuestionCandidate SHALL 使用 Pydantic BaseModel 定义，包含 question（str）、question_type（QuestionType 枚举）、expected_info_gain（float, 0-1）、priority（int, 1-5）和 rationale（str）字段
5. THE ReplanDecision_V2 SHALL 使用 Pydantic BaseModel 定义，包含 should_continue（bool）、reason（str）、candidate_questions（list[QuestionCandidate]）字段
6. THE QuestionType SHALL 为枚举类型，包含 trend_validation / scope_expansion / angle_switch / drill_down / complementary 五种类型
7. FOR ALL 有效的新增数据模型对象，序列化（model_dump）后再反序列化（model_validate）SHALL 产生等价的对象
8. ALL 新增数据模型 SHALL 使用 `ConfigDict(extra="forbid")`

### 需求 9：V1 组件复用与清理

**用户故事：** 作为系统开发者，我希望最大化复用 V1 已验证的组件，同时清理不再需要的 ReAct 相关代码。

#### 验收标准

1. THE V2 SHALL 复用 V1 的 DataStore 组件（无需修改）
2. THE V2 SHALL 复用 V1 的 DataProfiler 组件（无需修改）
3. THE V2 SHALL 复用 V1 的 DataProfile、Finding、FindingType、AnalysisLevel 数据模型（无需修改）
4. THE V2 SHALL 移除 `agents/insight/components/data_tools.py`（ReAct 工具定义，不再需要）
5. THE V2 SHALL 重写 `agents/insight/graph.py`（从 ReAct 循环改为 One-Shot 分析）
6. THE V2 SHALL 重写 `agents/insight/prompts/insight_prompt.py`（从工具调用引导改为数据分析引导）
7. THE V2 SHALL 重写 `agents/replanner/graph.py`（支持多问题生成和用户选择）
8. THE V2 SHALL 重写 `agents/replanner/prompts/replanner_prompt.py`（支持多问题生成和信息增益评估）


### 需求 10：错误处理与降级

**用户故事：** 作为系统开发者，我希望系统在异常情况下能够优雅降级，不影响核心查询功能。

#### 验收标准

1. IF Insight_Agent_V2 执行失败 THEN WorkflowExecutor SHALL 跳过洞察生成，返回查询结果并记录 error 日志
2. IF Replanner_Agent_V2 执行失败 THEN WorkflowExecutor SHALL 停止重规划循环，返回当前轮的洞察结果并记录 error 日志
3. IF DataSampler 采样失败 THEN DataSampler SHALL 降级为返回前 N 行数据（N = target_sample_size）并记录 warning 日志
4. IF LLM 输出无法解析为目标 Pydantic 模型 THEN 调用方 SHALL 重试一次（通过 ModelRetryMiddleware），仍失败则抛出异常
5. IF 配置加载失败 THEN 各组件 SHALL 使用代码中的默认常量并记录 warning 日志
