# 实现任务：洞察与重规划系统 V2

## 任务 1：V2 数据模型定义

- [ ] 1.1 扩展 InsightOutput，新增 `round_number` 字段
  - 文件：`agents/insight/schemas/output.py`
  - 在 InsightOutput 中新增 `round_number: int = Field(default=1, description="分析轮次号（从 1 开始）")`
  - 确保 `extra="forbid"` 保持不变
- [ ] 1.2 新增 SampleResult、RoundSummary、CumulativeInsightContext 模型
  - 文件：`agents/insight/schemas/output.py`
  - SampleResult：rows(list[dict[str, Any]])、strategy(str)、total_rows(int, ge=0)、sampled_count(int, ge=0)，ConfigDict(extra="forbid")
  - RoundSummary：round_number(int)、question(str)、key_findings(list[str])、confidence(float, 0-1)，ConfigDict(extra="forbid")
  - CumulativeInsightContext：previous_rounds(list[RoundSummary])、cross_round_patterns(list[str])，ConfigDict(extra="forbid")
- [ ] 1.3 新增 QuestionType、QuestionCandidate、ReplanDecision_V2 模型
  - 文件：`agents/replanner/schemas/output.py`
  - QuestionType(str, Enum)：TREND_VALIDATION / SCOPE_EXPANSION / ANGLE_SWITCH / DRILL_DOWN / COMPLEMENTARY，value 使用小写
  - QuestionCandidate：question(str)、question_type(QuestionType)、expected_info_gain(float, 0-1)、priority(int, 1-5)、rationale(str)，ConfigDict(extra="forbid")
  - ReplanDecision_V2：should_continue(bool)、reason(str)、candidate_questions(list[QuestionCandidate])，ConfigDict(extra="forbid")
  - ReplanDecision_V2 添加 model_validator：should_continue=True 时 candidate_questions 非空；按 priority 升序排序
  - 保留 V1 的 ReplanDecision 不删除
- [ ] 1.4 编写数据模型属性测试
  - 文件：`tests/agents/insight/test_schema_v2_properties.py`
  - Property 4：InsightOutput V2 序列化往返一致性（含 round_number）
  - 文件：`tests/agents/replanner/test_replan_v2_properties.py`
  - Property 5：ReplanDecision_V2 结构一致性（should_continue + candidate_questions 非空 + priority 排序 + 范围校验）
  - Property 6：QuestionCandidate 序列化往返一致性
  - Property 8：ReplanDecision_V2 序列化往返一致性
  - 文件：`tests/agents/insight/test_cumulative_context_properties.py`
  - Property 7：CumulativeInsightContext 累积正确性（N 轮更新后 previous_rounds 长度 == N）

## 任务 2：DataSampler 组件实现

- [ ] 2.1 实现 DataSampler 类
  - 文件：`agents/insight/components/data_sampler.py`
  - 从 app.yaml 读取 `agents.data_sampler.target_sample_size`（默认 50）和 `full_sample_threshold`（默认 50）
  - `sample(data_store, data_profile) -> SampleResult`：根据 row_count 选择全量或分层采样
  - `_full_sample(data_store) -> SampleResult`：全量返回
  - `_stratified_sample(data_store, data_profile) -> SampleResult`：分层采样（分类列 top 值覆盖 + 数值列极值 + 随机补充 + 去重）
  - `format_for_prompt(sample_result) -> str`：格式化为 Markdown 表格
  - 空数据返回空 SampleResult + "数据为空"策略描述
  - 分层采样失败时降级为前 N 行，记录 warning 日志
- [ ] 2.2 编写 DataSampler 属性测试
  - 文件：`tests/agents/insight/test_data_sampler_properties.py`
  - Property 1：全量采样正确性（行数 <= threshold 时 sampled_count == total_rows）
  - Property 2：分层采样覆盖性（sampled_count <= target_sample_size，分类列 top-1 值至少一行覆盖）
  - Property 3：空数据处理（空 DataStore 返回空 rows）
- [ ] 2.3 编写 DataSampler 单元测试
  - 文件：`tests/agents/insight/test_data_sampler.py`
  - 全量采样、分层采样、空数据、降级、format_for_prompt 输出格式

## 任务 3：V2 Prompt 重写

- [ ] 3.1 重写 Insight Prompt V2
  - 文件：`agents/insight/prompts/insight_prompt.py`
  - 保留 V1 的 `get_system_prompt()` 和 `build_user_prompt()` 函数签名（V1 代码可能仍有引用）
  - 新增 `get_system_prompt_v2()` 和 `build_user_prompt_v2()` 函数
  - SYSTEM_PROMPT_V2：移除工具调用引导，改为数据分析引导（直接基于采样数据分析）
  - build_user_prompt_v2 参数：data_profile_summary、sample_data_text、semantic_output_summary、analysis_depth、cumulative_context(Optional[CumulativeInsightContext])、round_number
  - Prompt 结构：分析任务 → 数据概览 → 采样数据（Markdown 表格）→ 前序分析上下文（后续轮次）→ 分析深度指导
- [ ] 3.2 重写 Replanner Prompt V2
  - 文件：`agents/replanner/prompts/replanner_prompt.py`
  - 保留 V1 的 `get_system_prompt()` 和 `build_user_prompt()` 函数签名
  - 新增 `get_system_prompt_v2()` 和 `build_user_prompt_v2()` 函数
  - SYSTEM_PROMPT_V2：多问题生成 + 信息增益评估 + 5 种问题类型说明
  - build_user_prompt_v2 参数：insight_summary、semantic_output_summary、data_profile_summary、cumulative_context_summary、replan_history_summary、analysis_depth
  - 注入 ReplanDecision_V2 的 JSON Schema

## 任务 4：Insight Agent V2 Graph 重写

- [ ] 4.1 实现 `run_insight_agent_v2()` 函数
  - 文件：`agents/insight/graph.py`
  - 保留 V1 的 `run_insight_agent()` 函数（不删除，避免影响其他引用）
  - 新增 `run_insight_agent_v2()` 异步函数
  - 参数：data_profile、sample_result、semantic_output_dict、analysis_depth、cumulative_context(Optional)、round_number、on_token、on_thinking
  - 获取 LLM（enable_json_mode=True），构建 V2 Prompt，中间件栈仅 ModelRetryMiddleware
  - 调用 `stream_llm_structured()` 无 tools 参数（One-Shot 模式）
  - 注入 round_number 到结果
  - 新增辅助函数 `_build_v2_middleware_stack()`、`_build_data_profile_summary()`（可复用 V1 已有的）、`_build_semantic_output_summary()`（可复用 V1 已有的）

## 任务 5：Replanner Agent V2 Graph 重写

- [ ] 5.1 实现 `run_replanner_agent_v2()` 函数
  - 文件：`agents/replanner/graph.py`
  - 保留 V1 的 `run_replanner_agent()` 函数
  - 新增 `run_replanner_agent_v2()` 异步函数
  - 参数：insight_output_dict、semantic_output_dict、data_profile_dict、cumulative_context(Optional)、replan_history、analysis_depth、on_token、on_thinking
  - 从 app.yaml 读取 `min_info_gain_threshold`（默认 0.3）
  - 获取 LLM（enable_json_mode=True），构建 V2 Prompt，中间件栈仅 ModelRetryMiddleware
  - 后处理：过滤 expected_info_gain < threshold 的问题，按 priority 排序，全部过滤则 should_continue=False
  - 新增辅助函数 `_build_cumulative_context_summary()`

## 任务 6：app.yaml V2 配置新增

- [ ] 6.1 在 app.yaml 的 agents 节下新增 V2 配置
  - 新增 `data_sampler` 配置节：target_sample_size(50)、full_sample_threshold(50)、detailed_sample_multiplier(1.0)、comprehensive_sample_multiplier(1.5)
  - 修改 `replanner` 配置节：新增 min_info_gain_threshold(0.3)、user_selection_timeout(300)；max_replan_rounds 改为 5

## 任务 7：SSE 回调扩展

- [ ] 7.1 在 callbacks.py 中新增 V2 节点映射和阶段
  - 文件：`orchestration/workflow/callbacks.py`
  - `_LLM_NODE_MAPPING` 新增 `"insight_agent_v2": "insight"` 和 `"replanner_agent_v2": "replanning"`
  - `_STAGE_NAMES_ZH` 新增 `"insight": "生成洞察"` 和 `"replanning": "分析规划"`
  - `_STAGE_NAMES_EN` 新增 `"insight": "Generating Insights"` 和 `"replanning": "Planning Analysis"`

## 任务 8：WorkflowExecutor V2 洞察重规划循环

- [ ] 8.1 实现 `_run_insight_replanner_loop()` 方法
  - 文件：`orchestration/workflow/executor.py`
  - 在 WorkflowExecutor 类中新增 `_run_insight_replanner_loop()` 异步方法
  - 参数：first_execute_result、first_semantic_output、callbacks、event_queue、ctx、graph、config、analysis_depth、language
  - 从 app.yaml 读取 max_rounds 和 user_selection_timeout
  - 初始化 CumulativeInsightContext 和 replan_history
  - 循环逻辑：第一轮复用已有结果，后续轮重新执行 semantic_parser → DataProfile → DataStore → DataSampler → Insight V2 → Replanner V2 → 用户选择
  - SSE 事件发送：data、chart、insight、candidate_questions、replan
  - 错误处理：Insight 失败跳过洞察、Replanner 失败停止循环
  - 循环结束清理 DataStore
- [ ] 8.2 实现 `_wait_for_user_selection()` 方法
  - 文件：`orchestration/workflow/executor.py`
  - 超时自动选择最高优先级问题
  - 用户选择 "__skip__" 返回 None
- [ ] 8.3 实现 `_update_cumulative_context()` 辅助函数
  - 文件：`orchestration/workflow/executor.py`
  - 从 InsightOutput 提取 key_findings（前 5 条 description）
  - 构建 RoundSummary 追加到 previous_rounds
- [ ] 8.4 在 `_run_workflow()` 中集成 V2 循环
  - 文件：`orchestration/workflow/executor.py`
  - 在 semantic_parser 子图执行完成后，检测到 query_result 时调用 `_run_insight_replanner_loop()`
  - 传入第一轮的 ExecuteResult 和 SemanticOutput

## 任务 9：删除 V1 ReAct 工具定义

- [ ] 9.1 删除 `data_tools.py`
  - 文件：`agents/insight/components/data_tools.py`
  - 确认 V2 graph.py 不再引用 `create_insight_tools`
  - 删除文件
  - 更新 `agents/insight/components/__init__.py`（如有导出）

## 任务 10：V2 单元测试

- [ ] 10.1 编写 Insight Prompt V2 单元测试
  - 文件：`tests/agents/insight/test_insight_prompt_v2.py`
  - 验证 build_user_prompt_v2 输出包含采样数据和累积上下文
  - 验证 analysis_depth 影响 Prompt 内容
- [ ] 10.2 编写 Replanner Prompt V2 单元测试
  - 文件：`tests/agents/replanner/test_replanner_prompt_v2.py`
  - 验证 build_user_prompt_v2 输出包含候选问题类型和信息增益
- [ ] 10.3 编写累积上下文更新单元测试
  - 文件：`tests/agents/insight/test_cumulative_context.py`
  - 验证 _update_cumulative_context 逻辑正确性
