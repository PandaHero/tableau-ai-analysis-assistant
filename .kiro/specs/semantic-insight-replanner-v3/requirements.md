# 需求文档：语义理解、洞察与重规划统一架构 V3

## 简介

本功能定义 Analytics Assistant 的下一代统一分析架构，覆盖以下三条主链：

- `语义理解`：从用户问题生成可执行的分析意图与查询计划
- `洞察生成`：从查询结果中产生结构化洞察、证据摘要和风险提示
- `重规划`：在已有证据基础上继续提出后续问题，并支持用户选择或自动推进

V3 的核心目标不是继续堆叠规则，而是将系统升级为“**LLM 主导理解，规则负责约束和兜底**”的分析系统。系统需要同时支持以下场景：

- 简单单步查询
- 复杂但可单条 VizQL 完成的查询
- 需要多步拆解的依赖型问题
- why 原因型问题
- 查询后自动洞察与继续分析
- 用户可见的完整阶段与步骤级进度

## 设计原则

1. **LLM 主导语义理解**：复杂问题类型识别、问题补全、步骤拆分、why 推理和重规划问题生成必须由 LLM 主导。
2. **规则只做约束与兜底**：规则只负责时间/TopN 等显式模式、平台约束校验、缓存 gating、明显错误修正，不承担复杂问题拆分主逻辑。
3. **每个 query step 必须重新做字段 grounding**：拆分后的每一步都必须重新走字段检索、step 级语义理解和 VizQL 构建，不能直接执行自然语言子问题。
4. **单查询优先**：只有当当前 backend + QueryBuilder 无法用单条 VizQL 完整表达问题时，系统才应进入多步拆解。
5. **why 问题优先构造证据链**：系统必须先验证现象、再定位异常、再找解释轴、最后归纳原因，禁止跳过证据直接生成原因文本。
6. **种子与字段语义作为语义先验**：字段种子、field semantic、层级信息、别名等应成为 LLM 的 grounding 上下文，而不是被大量手写 hints 重复替代。

## 术语表

- **Global Understanding**：全局语义理解阶段，对原问题做任务分类、单查询可行性判断、是否需要澄清和是否需要拆分。
- **Single_Query_Feasible**：在当前系统能力下，问题可以通过一条 `SemanticOutput -> VizQL` 完整表达。
- **AnalysisPlan**：全局规划结果，描述问题模式、拆分理由、步骤依赖和执行策略。
- **StepIntent**：单个分析步骤的意图描述，仍是待 grounding 的分析目标，不是可直接执行的查询。
- **Step Semantic Understanding**：对单个 `query step` 单独执行字段检索与语义理解，产出可执行 `SemanticOutput`。
- **SemanticOutput**：step 级可执行语义结果，可被 Tableau Adapter 校验并构建 VizQL。
- **Evidence Chain**：why 或复杂问题在多步查询后形成的结构化证据链。
- **Insight Round**：一次查询执行后，对当前结果生成洞察并追加到累积上下文的一轮分析。
- **Replanner**：基于当前证据链、洞察和未覆盖问题，生成后续候选问题的模块。

## 需求

### 需求 1：全局语义理解与问题分类

**用户故事：** 作为用户，我希望系统先正确理解我的问题类型，以便简单问题直接查，复杂问题按正确方式拆解，而不是盲目套模板。

#### 验收标准

1. WHEN 系统接收到用户问题 THEN 系统 SHALL 执行一次全局语义理解，而不是仅依赖关键词规则判断是否为复杂/why/多步问题。
2. WHEN 全局语义理解完成 THEN 系统 SHALL 输出问题模式分类，至少包含 `single_query`、`complex_single_query`、`multi_step_analysis`、`why_analysis` 四类。
3. WHEN 问题信息不足以支持后续分析 THEN 系统 SHALL 优先生成澄清问题，而不是强行拆分。
4. THE 系统 SHALL 允许全局语义理解参考对话历史、字段候选、字段语义、种子信息和平台约束。
5. THE 系统 SHALL 将全局分类结果与理由保存到状态中，供后续 executor、insight、replanner 复用。

### 需求 2：单查询可行性判断

**用户故事：** 作为系统开发者，我希望系统能判断一个复杂问题是否仍可由一条 VizQL 完成，以便避免不必要的多步拆解。

#### 验收标准

1. WHEN 系统完成全局语义理解 THEN 系统 SHALL 输出 `single_query_feasible` 布尔值。
2. WHEN `single_query_feasible=true` THEN 系统 SHALL 继续走单步语义理解路径，而不是进入多步执行。
3. WHEN `single_query_feasible=false` THEN 系统 SHALL 输出不能单查的理由，至少覆盖以下类型之一：跨步骤依赖、动态对象选择、动态解释轴选择、口径未闭合。
4. THE 单查询可行性判断 SHALL 同时考虑当前 Tableau QueryBuilder 的已实现能力，而非 Tableau 理论全能力。
5. IF 问题包含“先找出一批对象，再基于这些对象继续查询”的依赖 THEN 系统 SHALL 判定为 `single_query_feasible=false`。

### 需求 3：AnalysisPlan 与 StepIntent 建模

**用户故事：** 作为系统开发者，我希望系统输出的是可执行的分析计划和步骤意图，而不是随意的自然语言子问题。

#### 验收标准

1. WHEN 问题需要多步分析 THEN 系统 SHALL 生成 `AnalysisPlan`。
2. THE `AnalysisPlan` SHALL 至少包含：问题模式、拆分理由、执行策略、步骤列表、步骤依赖、全局风险点、是否需要用户澄清。
3. THE `AnalysisPlan.steps[]` SHALL 使用 `StepIntent` 表达，每个 `StepIntent` 至少包含：`step_type`、`goal`、`depends_on`、`expected_output`、`semantic_focus`、`clarification_if_missing`。
4. THE `StepIntent` SHALL 区分 `query`、`synthesis`、`replan` 三种步骤类型。
5. THE `StepIntent` SHALL 表达“本步骤要解决什么问题”，但 SHALL NOT 直接视为可执行查询。

### 需求 4：每个 Query Step 的字段 grounding 与 step 级语义理解

**用户故事：** 作为系统开发者，我希望拆分后的每个查询步骤都重新做字段检索和语义理解，以便 step 最终能正确落成 VizQL。

#### 验收标准

1. WHEN executor 执行某个 `query step` THEN 系统 SHALL 对该 step 单独执行字段检索与 step 级语义理解。
2. WHEN step 级语义理解开始 THEN 系统 SHALL 允许输入该步骤的 `StepIntent`、前序步骤结构化上下文、字段候选、字段语义和对话历史。
3. WHEN step 级语义理解完成 THEN 系统 SHALL 输出可执行 `SemanticOutput`。
4. THE 系统 SHALL 对每个 step 的 `SemanticOutput` 单独执行 `validate_query()` 与 `build_query()`。
5. IF 某个 step 缺少必要字段、时间基线或筛选口径 THEN 系统 SHALL 为该 step 发起澄清，而不是继续执行下一个 step。

### 需求 5：为什么类型问题的证据链分析

**用户故事：** 作为用户，我希望 why 问题的回答基于真实数据证据，而不是 LLM 凭空编造原因。

#### 验收标准

1. WHEN 系统识别为 `why_analysis` THEN 系统 SHALL 构造证据链，而不是直接生成原因文本。
2. THE why 分析链至少 SHALL 包含以下阶段：现象验证、异常定位、解释轴验证、结论汇总。
3. WHEN 比较基线未明确（例如“下降”未说明是同比、环比、目标差） THEN 系统 SHALL 先发起澄清。
4. WHEN 现象验证结果表明问题前提不成立 THEN 系统 SHALL 停止 why 分析，并向用户说明前提不成立。
5. THE why 结论 SHALL 显式区分：数据已支持的证据、推断性解释、仍待确认的口径。

### 需求 6：定位维度与解释轴选择

**用户故事：** 作为系统开发者，我希望系统根据语义和数据共同决定下一步拆解维度，而不是固定写死先省份再产品。

#### 验收标准

1. WHEN 系统需要继续拆解一个聚合对象（例如华东区） THEN 系统 SHALL 优先选择与该对象同层级或下一级的定位维度。
2. WHEN 系统需要解释异常原因 THEN 系统 SHALL 在产品、渠道、客户、组织、价格/数量等候选解释轴中选择下一步。
3. THE 解释轴选择 SHALL 同时考虑语义相关性和数据解释力。
4. IF 当前候选解释轴均不能显著解释异常 THEN 系统 SHALL 允许重规划或向用户继续追问。
5. THE 系统 SHALL 基于字段语义、种子、层级和实际查询结果决定下一步，而 SHALL NOT 依赖固定维度顺序模板。

### 需求 7：种子与字段语义的正确使用

**用户故事：** 作为系统开发者，我希望已有种子和字段语义真正参与语义理解，而不是被重复的手写 hints 替代。

#### 验收标准

1. THE 系统 SHALL 将 measure/dimension seeds、field semantic、层级信息、别名、sample values 作为语义 grounding 的主要先验。
2. THE 系统 SHALL 能从 seeds 和字段语义自动派生 query-term 语义映射，而不是长期维护大量手写 hints 作为主语义来源。
3. IF 存在手写 hints THEN 这些 hints SHALL 只作为 fallback 或平台特定规则，不得主导复杂语义理解。
4. THE 系统 SHALL 允许 LLM 在 prompt 中直接看到字段的语义类别、层级、别名和样例值。
5. WHEN 字段语义与用户问题冲突 THEN 系统 SHALL 优先基于真实字段语义做澄清，而不是强行匹配。

### 需求 8：查询结果后的洞察生成

**用户故事：** 作为用户，我希望每次查询后系统能自动总结数据特征和初步洞察，帮助我继续分析。

#### 验收标准

1. WHEN 任一 query step 成功执行 THEN 系统 SHALL 生成 step 级或 round 级洞察。
2. THE 洞察生成 SHALL 支持小数据集全量分析和大数据集采样分析。
3. THE 洞察输出 SHALL 包含摘要、发现列表、置信度和风险提示。
4. THE 洞察生成 SHALL 允许使用描述性、诊断性两种深度模式。
5. IF 洞察模块失败 THEN 系统 SHALL 保留查询结果，并优雅降级而不影响核心查询流程。

### 需求 9：渐进式累积洞察与证据上下文

**用户故事：** 作为用户，我希望多轮分析能累积证据和洞察，而不是每一步都像重新开始。

#### 验收标准

1. WHEN 第一步分析完成 THEN 系统 SHALL 创建可持续追加的 `EvidenceContext` / `CumulativeInsightContext`。
2. WHEN 后续步骤开始 THEN 系统 SHALL 将前序步骤的结构化摘要、洞察和关键对象注入上下文。
3. THE 累积上下文 SHALL 至少包含：步骤摘要、关键发现、候选对象集、异常对象集、已验证解释轴、未解决问题。
4. THE 系统 SHALL 避免后续步骤重复做与前序相同的分析。
5. THE 系统 SHALL 支持在多步完成后基于证据上下文生成统一总结。

### 需求 10：重规划与后续问题生成

**用户故事：** 作为用户，我希望系统在当前分析不完整时继续提出高价值后续问题，并让我决定是否继续。

#### 验收标准

1. WHEN 当前问题分析完毕但仍存在高价值未覆盖方向 THEN 系统 SHALL 生成重规划候选问题。
2. THE 重规划候选问题 SHALL 基于当前问题、证据链、洞察上下文和未解决风险点生成。
3. EACH 候选问题 SHALL 包含：问题文本、问题类型、优先级、预期信息增益、推荐理由、预估是否需要多步。
4. THE 系统 SHALL 支持两种模式：用户选择执行、自动按优先级继续执行。
5. IF 候选问题信息增益低于阈值 THEN 系统 SHALL 建议结束分析而不是继续发散。

### 需求 11：用户可见的完整阶段与步骤级进度

**用户故事：** 作为用户，我希望清楚看到系统现在是在理解问题、规划步骤、执行查询、生成洞察还是重规划。

#### 验收标准

1. THE 系统 SHALL 通过 SSE 暴露完整的阶段级进度，至少包含 `preparing`、`understanding`、`planning`、`building`、`executing`、`generating`、`replanning`。
2. WHEN 进入多步分析 THEN 系统 SHALL 发送整体 `planner` 事件和逐步 `plan_step` 事件。
3. WHEN 任一 step 完成语义理解 THEN 系统 SHALL 发送 step 级 `parse_result` 摘要。
4. WHEN 任一 step 完成数据执行 THEN 系统 SHALL 发送带 `step` / `round` 上下文的 `data` 事件。
5. WHEN why 问题中某一步需要澄清 THEN 系统 SHALL 告知用户阻塞在哪一步以及缺少什么口径。

### 需求 12：错误处理与降级

**用户故事：** 作为系统开发者，我希望系统在复杂链路中出错时能准确降级，而不是整个流程完全失败。

#### 验收标准

1. IF Global Understanding 失败 THEN 系统 SHALL 回退为单步语义理解，并记录该次失败。
2. IF 某个 query step 的语义理解失败 THEN 系统 SHALL 将失败定位到该 step，并允许澄清或终止后续步骤。
3. IF 洞察生成失败 THEN 系统 SHALL 保留查询结果和已完成步骤，不得回滚已完成证据链。
4. IF 重规划失败 THEN 系统 SHALL 结束当前轮，并返回已有结果。
5. THE 系统 SHALL 为单步、多步、why、洞察、重规划各阶段记录可观测指标。

### 需求 13：缓存与性能策略

**用户故事：** 作为系统开发者，我希望在保留 LLM 主导语义理解的前提下控制延迟和成本。

#### 验收标准

1. THE 系统 SHALL 允许对简单高置信度问题继续使用快路径或快模型。
2. THE 系统 SHALL 对复杂问题、why 问题和多步问题优先保留推理路径，不得为了节省时间直接规则化替代。
3. THE 系统 SHALL 支持 query cache、feature cache、field semantic cache、schema cache 等现有缓存能力。
4. THE 系统 SHALL 允许对多步分析中的字段检索、洞察和重规划设置独立性能预算。
5. THE 系统 SHALL 记录单步解析耗时、step 解析耗时、洞察耗时、重规划耗时和总工作流耗时。

### 需求 14：设计文档与实施计划对齐

**用户故事：** 作为系统开发者，我希望该架构能直接映射到实际代码改造任务，以便分阶段落地。

#### 验收标准

1. THE 设计文档 SHALL 明确现状、问题、目标架构、数据结构、场景流程和 SSE 协议。
2. THE 任务清单 SHALL 将改造拆成可执行的阶段任务，而不是笼统描述。
3. THE 任务清单 SHALL 明确哪些现有模块复用、哪些模块重写、哪些规则需要降级为 fallback。
4. THE 文档 SHALL 覆盖至少以下场景：简单查询、复杂单查询、多步依赖查询、why 问题、why 口径缺失澄清、查询后洞察、重规划用户选择、重规划自动推进、部分失败降级。
