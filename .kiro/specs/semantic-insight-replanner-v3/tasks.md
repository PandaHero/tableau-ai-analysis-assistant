# 实施任务：语义理解、洞察与重规划统一架构 V3

## Phase 1：统一数据结构与契约

- [ ] 1. 新增全局理解与多步执行核心 schema
  - 新增 `GlobalUnderstandingOutput`
  - 重构 `AnalysisPlan`
  - 新增 `StepIntent`
  - 新增 `EvidenceContext` / `WhyAnalysisContext`
  - 明确 `SemanticOutput` 仍然是 step 级可执行契约
  - _Requirements: 1, 2, 3, 4, 5, 9_

- [ ] 2. 梳理 `SemanticOutput` 与 `AnalysisPlan` 的边界
  - 移除“把多步计划塞进 SemanticOutput 并直接执行”的错误方向
  - 保留 `SemanticOutput` 的 query-only 角色
  - 为 step 级执行补充 `semantic_summary` 和 `table_summary` 契约
  - _Requirements: 3, 4, 14_

## Phase 2：接入 Global Understanding

- [ ] 3. 新增 `global_understanding_node`
  - 基于 LLM 输出问题模式、澄清需求、`single_query_feasible` 和 `AnalysisPlan`
  - 允许输入 feature 抽取结果、字段语义概览、系统能力摘要
  - _Requirements: 1, 2, 3, 5, 6_

- [ ] 4. 实现 `single_query_feasibility` 判定器
  - 将 LLM 判断与 QueryBuilder 能力约束结合
  - 输出不可单查原因枚举
  - _Requirements: 2, 5, 6, 13_

- [ ] 5. 降级规则 `analysis_planner_node`
  - 从主路径移除规则 planner 的主导作用
  - 仅保留最小 gating / fallback 作用，或完全由 `global_understanding_node` 替代
  - _Requirements: 1, 3, 6, 14_

## Phase 3：实现 Step 级 grounding 执行闭环

- [ ] 6. 抽出 step 级 query grounding pipeline
  - 支持 `StepIntent -> prefilter -> feature -> field_retriever -> understanding -> validator -> query_adapter`
  - 支持传入 `EvidenceContext`
  - _Requirements: 4, 5, 6, 9_

- [ ] 7. 重构 executor 多步执行逻辑
  - 停止直接执行自然语言 sub question
  - 让每个 `query step` 都重新生成 `SemanticOutput`
  - 支持 step 级澄清和 step 级失败
  - _Requirements: 4, 5, 11, 12_

- [ ] 8. 实现 why 专用证据链流程
  - 现象验证
  - 异常定位
  - 解释轴验证
  - 汇总归因
  - _Requirements: 5, 6, 9, 11_

## Phase 4：收敛语义先验与字段 hints

- [ ] 9. 新增 `SemanticLexiconBuilder`
  - 从 `MEASURE_SEEDS`、`DIMENSION_SEEDS`、`field_semantic`、层级、别名、样例值构建语义词典
  - _Requirements: 6, 7, 13_

- [ ] 10. 逐步下线 `understanding.py` 中的大量手写 measure/dimension hints
  - 将其收敛为 fallback
  - 改为优先使用 semantic lexicon
  - _Requirements: 7, 13, 14_

## Phase 5：接入 Insight Agent V2

- [ ] 11. 将 `insight-replanner-v2` 的 One-Shot Insight 接入 executor
  - query step 完成后生成 `InsightRound`
  - 支持小数据全量、大数据采样
  - 支持 step 级和 round 级洞察
  - _Requirements: 8, 9, 12_

- [ ] 12. 实现 `CumulativeInsightContext` / `EvidenceContext` 更新
  - 记录已完成步骤、关键发现、候选对象、异常对象、已验证解释轴
  - 为后续 step 和 replanner 提供上下文
  - _Requirements: 8, 9, 10_

## Phase 6：接入 Replanner V2

- [ ] 13. 接入 `Replanner` 候选问题生成
  - 基于当前问题、洞察、证据链、未解决风险生成后续问题
  - 输出优先级、预期信息增益、推荐理由
  - _Requirements: 10, 12_

- [ ] 14. 支持用户选择与自动继续两种模式
  - `user_select`
  - `auto_continue`
  - `stop`
  - _Requirements: 10, 11, 12_

## Phase 7：可观测性与前端协议

- [ ] 15. 扩展 SSE 协议
  - 接入 `planner`
  - 接入 `plan_step`
  - 接入 `insight`
  - 接入 `candidate_questions`
  - 接入 `replan`
  - _Requirements: 11, 12_

- [ ] 16. 扩展前端 streaming 消费模型
  - 增加 `planning`、`replanning` 阶段
  - 消费 `planner/plan_step/insight/candidate_questions/replan`
  - _Requirements: 11_

- [ ] 17. 补充阶段耗时与 step 级性能指标
  - Global Understanding
  - step grounding
  - query execute
  - insight
  - replanner
  - _Requirements: 12, 13_

## Phase 8：测试与回归

- [ ] 18. 补充 Global Understanding 单元测试
  - 问题模式分类
  - `single_query_feasible`
  - why 口径缺失澄清
  - _Requirements: 1, 2, 5_

- [ ] 19. 补充 step 级执行回归测试
  - 多步依赖问题
  - why 证据链
  - step 级 clarification
  - step 级失败降级
  - _Requirements: 4, 5, 9, 12_

- [ ] 20. 补充 Insight / Replanner 集成测试
  - 查询后洞察
  - 用户选择候选问题
  - 自动继续
  - _Requirements: 8, 9, 10_

- [ ] 21. 进行真实链路手工验证
  - 简单单步查询
  - 复杂单查询
  - 多步依赖查询
  - why 问题
  - _Requirements: 14_

## 建议实施顺序

1. 先完成 `GlobalUnderstandingOutput + StepIntent + single_query_feasibility`
2. 再把 executor 改成 `StepIntent -> step semantic grounding -> execute`
3. 然后接入 Insight V2 和累积上下文
4. 最后接入 Replanner V2 和前端交互闭环
