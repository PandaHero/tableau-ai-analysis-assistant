# Why And Complex Analysis Design

> Status: Draft v0.2
> Read order: 4/16
> Upstream: [requirements.md](./requirements.md), [design.md](./design.md)
> Downstream: [why-and-complex-analysis-implementation-notes.md](./why-and-complex-analysis-implementation-notes.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [node-catalog.md](./node-catalog.md), [node-io-schemas.md](./node-io-schemas.md), [tasks.md](./tasks.md)

## 1. 目标

这份文档专门定义 `why` 问题和一般复杂问题在后端中的目标执行方案，主要回答 5 件事：

- `why` 和复杂问题应该如何在 planner 中建模
- planner 中的“多个问题”到底分几类，分别如何执行
- 字段语义、字段层级、时间层级如何参与 why 诊断
- `insight` 和 `replan` 在复杂问题场景下应该如何分工
- 当前实现与目标态之间还有哪些差距

## 2. 问题定义

### 2.1 简单问题

简单问题指可以通过单次查询完成回答的问题，例如：

- 本月华东区销售额是多少
- 上周订单量按渠道分布如何

执行特点：

- 不需要 planner
- 查询结果出来后直接进入 `answer_graph`

### 2.2 复杂但单查可解问题

这类问题语义复杂，但仍然可以被编译成一条查询，例如：

- 比较今年和去年的利润率变化
- 计算不同区域的贡献率并排序

执行特点：

- 语义理解更复杂
- 运行时仍然走单轮 `query_graph -> answer_graph`

### 2.3 复杂多步问题

这类问题无法靠一条查询解决，需要多个步骤逐步完成，例如：

- 比较华东和华南最近三个月的销售和利润变化，并总结差异
- 分析销售下降与库存变化之间的关系

执行特点：

- 需要 planner
- planner 内部允许多个步骤
- 最终只生成一次正式答案

### 2.4 Why 问题

`why` 问题属于复杂问题，但它和普通多步问题的重点不同。

普通多步问题强调“任务拆解”；`why` 问题强调“建立解释链”。

例如：

- 为什么华东区销售下降了
- 为什么直营渠道利润率下降
- 为什么某类客户流失增加

执行特点：

- 必须先验证异常是否成立
- 必须先决定先看哪个解释轴
- 允许按层级逐步下钻
- 最终答案必须体现证据链，而不是只给一个自由文本结论

## 3. planner 中的三类“多个问题”

复杂问题里至少有 3 种“多个问题”，它们不能混用。

### 3.1 Planner Steps

`analysis_plan.sub_questions` 表示“回答同一个主问题所需的内部执行步骤”。

特点：

- 属于同一轮执行内部
- 可以形成 DAG
- 有依赖时串行执行
- 无依赖时允许受控并行

### 3.2 Axis Candidates

在 `why` 场景中，经常会出现多个候选解释轴，例如：

- 渠道
- 产品线
- 客户类型
- 地区层级
- 时间层级

这些不是独立的 follow-up 问题，而是当前 why 主问题内部的候选诊断方向。

规则：

- 先排序
- 再保留少量高价值 axis
- 禁止无界 fan-out

### 3.3 Follow-up Branches

`replan` 产出的 `candidate_questions` 表示“当前轮完成后，下一轮可以继续分析的候选方向”。

规则：

- 每次只允许一个 active branch
- `user_select` 由用户选 1 个
- `auto_continue` 由系统选 1 个
- 不允许同时展开多个 follow-up branches

## 4. 目标态总流程

```text
root_graph
  -> context_graph
  -> semantic_graph
  -> planner_graph
       -> verify_anomaly
       -> rank_explanatory_axes
       -> screening_wave
       -> locate_anomalous_slice / hierarchy_drill / compare_segments / validate_hypothesis
       -> synthesize_cause
  -> answer_graph
       -> final_insight
       -> final_replan
```

分工原则：

- planner 只负责“诊断计划与证据收集”
- `answer_graph` 只负责“最终回答、最终洞察、最终重规划”
- planner 内的 step insight 只用于证据累积，不直接替代最终答案

## 5. Why 问题的结构化 step kinds

目标态里，why planner 不应只输出自由文本步骤，而应该输出稳定的 `step_kind`。

### 5.1 `verify_anomaly`

先验证异常是否成立。

必须回答：

- 比较基线是什么
- 时间窗口是什么
- 指标是什么
- 变化方向和幅度是什么
- 是否达到进入归因分析的条件

如果基线不清或异常不成立：

- 直接中断澄清
- 或结束 why 流程

### 5.2 `rank_explanatory_axes`

对候选解释轴排序，而不是立刻把所有轴都展开。

产物：

- 有序 `candidate_axes`
- `axis_scores`
- 是否支持层级 drill

### 5.3 `screening_wave`

对前 `K` 个解释轴做一轮受控筛查，不无界 fan-out。

规则：

- `K` 由运行时参数控制
- 当前默认 `root_graph.planner.screening_top_k = 2`
- 筛查结果用于决定下一步优先沿哪条 axis 深挖

### 5.4 `locate_anomalous_slice`

在已选 axis 上定位异常集中区域。

目标：

- 找到贡献最大或差异最显著的 segment
- 判断问题是广泛发生还是集中发生

### 5.5 `hierarchy_drill`

若 axis 存在层级，则优先高层级，再决定是否继续下钻。

例如：

- 地理：大区 -> 省 -> 城市 -> 门店
- 产品：品类 -> 子类 -> SKU
- 时间：年 -> 季 -> 月 -> 周 -> 日

规则：

- 先高层
- 解释增益显著再进入下一层
- 增益不足就停或切换 axis

### 5.6 `compare_segments`

对异常组和对照组做差异对比，不只是继续切维度。

### 5.7 `validate_hypothesis`

对显式业务假设做验证，例如：

- 折扣变化是否解释了销量下滑
- 库存短缺是否集中在异常门店

### 5.8 `synthesize_cause`

汇总证据链，输出：

- 原因结论
- 证据摘要
- 未验证假设
- 剩余不确定性

## 6. 字段语义和层级为什么重要

字段语义对 why 不是锦上添花，而是核心决策输入。

可直接帮助 planner 的信息：

- 字段角色：指标、维度、时间、地理、组织、产品、客户
- 层级关系：父级、子级、自然 drill path
- 粒度：高层聚合还是低层明细
- 业务语义：销售、利润、库存、订单、价格、折扣
- 基数风险：是否适合直接下钻
- 时间类型：快照、流量、累计、周期性

## 7. Axis Ranking 的评分信号

`why` planner 应引入 axis ranking，评分至少考虑：

- `semantic_relevance`
  - axis 与问题文本、主指标的相关性
- `hierarchy_prior`
  - 有自然层级的 axis 优先级更高
- `explanation_gain`
  - 当前 axis 对异常差异的解释力
- `concentration_score`
  - 异常是否集中在少量切片
- `cardinality_penalty`
  - 高基数 axis 的直接下钻风险
- `business_priority`
  - 业务上更常见的解释路径优先

说明：

- 当前实现还没有做真正的统计建模
- 现阶段的 `axis_scores` 代表“已排序筛查结果的稳定证据”
- 后续可以继续升级为更强的解释力模型

## 8. Hierarchy Drill 规则

对存在层级的 axis，不应一开始就钻到底。

建议规则：

1. 先看高层级
2. 若解释增益显著，再进入下一层
3. 若当前层已足够解释问题，则停止下钻
4. 若下钻后解释增益很小，则回退并切换 axis

例如：

```text
为什么华东区销售下降了？
  -> 先看渠道层：直营 / 分销 / 电商
  -> 若直营贡献最大，再看直营下的团队或门店层
  -> 若产品线解释力更强，则切换到产品层级
```

## 9. Why 不只有“下钻”一种方法

why 诊断至少应支持 4 类方法：

### 9.1 Hierarchy Drill

沿自然层级定位异常集中区。

### 9.2 Axis Ranking And Screening

先筛最有解释力的 axis，而不是先选一个 axis 一路钻。

### 9.3 Segment Contrast

对异常组和对照组做分群对比。

### 9.4 Hypothesis Validation

对显式业务假设做验证。

这些方法可以组合，不互斥。

## 10. Insight 与 Replan 的分工

### 10.1 当前问题

当前 planner 路径里已经有：

- step insight
- planner synthesis insight
- replanner

单查询路径还有正式 `answer_graph`。

这意味着复杂问题路径与 `answer_graph` 存在职责重叠。

### 10.2 目标职责划分

#### Step Insight

只做证据摘要，不做最终用户答案。

产物：

- `step_artifact`
- `key_findings`
- `entity_scope`
- `validated_axes`

#### Planner Synthesis

只做证据汇总，不直接承担最终用户回答。

产物：

- `evidence_context`
- `synthesized_cause_draft`

#### Answer Graph

只在 planner 完成后运行一次，负责：

- 最终洞察
- 最终重规划

## 11. 多个问题时，answer_graph 怎么走

### 11.1 多个 planner steps

- 不在每个 step 后运行完整 `answer_graph`
- planner 结束后只运行一次 `answer_graph`

### 11.2 多个 axis candidates

- 不把每个 axis 当成独立 `answer_graph` 任务
- 先在 planner 内做 ranking / screening
- 再运行一次 `answer_graph`

### 11.3 多个 follow-up questions

- `answer_graph` 只负责产出候选和决策投影
- 每次只继续一个 follow-up branch

## 12. 当前实现状态

截至 2026-03-13，已经落地的部分：

- `root-native planner` 已接入 `root_graph`
- `step_kind` 已从 schema / prompt 元数据推进到运行时
- `rank_explanatory_axes` 的 `candidate_axes` 已进入 planner step payload、evidence 和后续 step 输入
- `locate_anomalous_slice` 会优先使用最近一次 axis ranking 的结果
- `root_graph.planner.screening_top_k` 已生效，当前默认值为 `2`
- `EvidenceContext.axis_scores` 已开始正式落盘
- planner 最终交给 `answer_graph` 的预构建 insight 已补充：
  - 已筛查解释轴
  - 已定位异常对象
  - 当前解释轴优先级

仍未完成的部分：

- 真正的多 axis `screening_wave` 执行节点
- hierarchy-aware drill runtime
- hypothesis validation runtime
- why/复杂问题主文档其余相关 spec 的编码清理与回填

## 13. 参考产品思路

这份方案参考了当前主流 BI 产品的做法，但不会照搬 UI 形式：

- Power BI `Decomposition tree`
  - 强调 explain-by 维度逐层拆解
- Power BI `Key influencers`
  - 强调因素排序和分群对比
- Tableau `Explain Data`
  - 强调对异常点给出候选解释

本方案的取舍是：

- 保留 decomposition tree 的轴选择与逐层拆解
- 借鉴 key influencers 的因素排序和分群对比
- 借鉴 Explain Data 的“候选解释”思路
- 执行上仍以 `root_graph + planner + answer_graph` 的后端状态机为主

## 14. 实施要求

后续实现必须满足：

1. `why` planner 从自由文本模板升级为结构化 step kinds
2. `verify_anomaly` 必须引入基线解析与异常成立校验
3. `axis ranking` 必须显式利用字段语义、字段层级、粒度与基数
4. `hierarchy drill` 必须采用“高层优先、解释增益驱动继续”的策略
5. planner 内只保留证据收集与证据合成
6. 最终 `insight` 与 `replan` 必须统一收敛到 `answer_graph`

## 15. 后续任务

建议新增以下实现任务：

1. 增加 `WhyAnalysisPlan / PlanStepKind / AxisCandidate` schema 完整约束
2. 增加 `baseline_spec` 与 `anomaly_spec` 解析
3. 增加 `screening_wave` 正式执行节点
4. 增加 hierarchy-aware drill runtime
5. 增加 hypothesis validation runtime
6. 将复杂 planner 最终答案统一进一步收敛到 `answer_graph`
7. 增加 why/复杂问题的端到端合同测试与黄金样例
