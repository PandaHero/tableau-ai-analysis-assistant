# Requirements Document

## Introduction

本文档定义了 Tableau Assistant 工作流端到端测试的需求规范。测试目标是验证完整工作流从用户问题输入到最终洞察输出的全流程正确性，使用真实的 Tableau 环境和 LLM 服务，覆盖所有业务场景。

**核心测试理念：**
- 所有测试使用真实环境，不使用 mock 数据
- 测试完整的端到端流程，而非单独节点
- 重点验证维度层级 → 问题理解 → 查询执行 → 洞察分析 → 重规划的完整循环

工作流架构：
- **Understanding Agent** → 问题分类 + 语义理解 → SemanticQuery
- **FieldMapper Node** → RAG + LLM 字段映射 → MappedQuery  
- **QueryBuilder Node** → VizQL 查询生成 → VizQLQuery
- **Execute Node** → VizQL API 执行 → QueryResult
- **Insight Agent** → 数据洞察分析 → Insights
- **Replanner Agent** → 智能重规划决策 → ReplanDecision

## Glossary

- **VizQLState**: 工作流状态对象，包含所有节点的输入输出
- **SemanticQuery**: 纯语义查询对象，包含度量、维度、筛选器等
- **MappedQuery**: 字段映射后的查询对象，业务术语映射到技术字段
- **VizQLQuery**: VizQL API 查询对象
- **QueryResult**: 查询执行结果，包含数据行和列元信息
- **InsightResult**: 洞察分析结果，包含发现和摘要
- **ReplanDecision**: 重规划决策对象，包含完成度评分和探索问题
- **WorkflowExecutor**: 工作流执行器，封装工作流执行逻辑
- **E2E Test**: 端到端测试，使用真实环境验证完整流程
- **Dimension Hierarchy**: 维度层级，定义维度之间的父子关系和下钻路径
- **Progressive Analysis**: 渐进式分析，通过多轮重规划逐步深入分析数据

## Requirements

### Requirement 1: 简单聚合查询流程测试

**User Story:** As a 测试工程师, I want to 验证简单聚合查询的完整流程, so that 确保基础分析功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"各地区销售额是多少" THEN THE WorkflowExecutor SHALL 返回包含 SemanticQuery 的成功结果
2. WHEN 工作流执行简单 SUM 聚合 THEN THE Execute Node SHALL 返回非空的 QueryResult 数据
3. WHEN 查询结果返回 THEN THE Insight Agent SHALL 生成至少一条洞察
4. WHEN 用户提问"各产品类别的平均利润" THEN THE Understanding Agent SHALL 正确识别 AVG 聚合类型
5. WHEN 用户提问"订单数量统计" THEN THE Understanding Agent SHALL 正确识别 COUNT 聚合类型

### Requirement 2: COUNTD 去重计数流程测试

**User Story:** As a 测试工程师, I want to 验证 COUNTD 去重计数的完整流程, so that 确保复杂聚合功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"各产品类别有多少个不同客户" THEN THE Understanding Agent SHALL 识别为 COUNTD 聚合
2. WHEN COUNTD 查询执行 THEN THE QueryBuilder Node SHALL 生成包含 COUNTD 的 VizQL 表达式
3. WHEN COUNTD 结果返回 THEN THE QueryResult SHALL 包含去重后的计数值

### Requirement 3: LOD 表达式流程测试

**User Story:** As a 测试工程师, I want to 验证 LOD 表达式的完整流程, so that 确保高级计算功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"各子类别销售额及其所属类别的总销售额" THEN THE Understanding Agent SHALL 识别需要 FIXED LOD 表达式
2. WHEN LOD 查询构建 THEN THE QueryBuilder Node SHALL 生成正确的 FIXED 表达式语法
3. WHEN LOD 查询执行 THEN THE Execute Node SHALL 成功返回包含 LOD 计算结果的数据

### Requirement 4: 表计算流程测试

**User Story:** As a 测试工程师, I want to 验证表计算的完整流程, so that 确保累计、排名等计算功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"按月累计销售额" THEN THE Understanding Agent SHALL 识别需要 RUNNING_SUM 表计算
2. WHEN 用户提问"销售额排名" THEN THE Understanding Agent SHALL 识别需要 RANK 表计算
3. WHEN 表计算查询执行 THEN THE QueryResult SHALL 包含正确计算的累计或排名值

### Requirement 5: 绝对日期筛选流程测试

**User Story:** As a 测试工程师, I want to 验证绝对日期筛选的完整流程, so that 确保日期筛选功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"2024年各产品类别销售额" THEN THE Understanding Agent SHALL 生成包含年份筛选的 SemanticQuery
2. WHEN 用户提问"2024年3月各地区销售额" THEN THE Understanding Agent SHALL 生成包含年月筛选的 SemanticQuery
3. WHEN 用户提问"2023年1月到2024年6月的销售趋势" THEN THE Understanding Agent SHALL 生成包含日期范围筛选的 SemanticQuery
4. WHEN 绝对日期筛选执行 THEN THE QueryResult SHALL 只包含指定日期范围内的数据

### Requirement 6: 相对日期筛选流程测试

**User Story:** As a 测试工程师, I want to 验证相对日期筛选的完整流程, so that 确保动态日期筛选功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"本月各产品类别销售额" THEN THE Understanding Agent SHALL 生成包含当前月份相对筛选的 SemanticQuery
2. WHEN 用户提问"上月各地区销售额" THEN THE Understanding Agent SHALL 生成包含上月相对筛选的 SemanticQuery
3. WHEN 用户提问"最近3个月的销售趋势" THEN THE Understanding Agent SHALL 生成包含最近N月相对筛选的 SemanticQuery
4. WHEN 用户提问"年初至今的销售情况" THEN THE Understanding Agent SHALL 生成包含 YTD 相对筛选的 SemanticQuery
5. WHEN 相对日期筛选执行 THEN THE QueryResult SHALL 只包含相对日期范围内的数据

### Requirement 7: 多维度分析流程测试

**User Story:** As a 测试工程师, I want to 验证多维度分析的完整流程, so that 确保复杂分析场景正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"各地区各产品类别的销售额" THEN THE Understanding Agent SHALL 生成包含两个维度的 SemanticQuery
2. WHEN 用户提问"各产品类别的销售额和利润" THEN THE Understanding Agent SHALL 生成包含两个度量的 SemanticQuery
3. WHEN 多维度查询执行 THEN THE QueryResult SHALL 包含所有维度组合的数据行

### Requirement 8: 非分析类问题路由测试

**User Story:** As a 测试工程师, I want to 验证非分析类问题的路由逻辑, so that 确保系统正确处理非数据分析请求。

#### Acceptance Criteria

1. WHEN 用户提问"你好，请问你是谁？" THEN THE Understanding Agent SHALL 设置 is_analysis_question=False
2. WHEN is_analysis_question=False THEN THE 工作流 SHALL 直接路由到 END 而不执行后续节点
3. WHEN 非分析类问题处理完成 THEN THE WorkflowResult SHALL 包含友好的非分析响应消息

### Requirement 9: 重规划流程测试

**User Story:** As a 测试工程师, I want to 验证重规划流程的完整性, so that 确保智能探索分析功能正常工作。

#### Acceptance Criteria

1. WHEN Insight Agent 完成分析 THEN THE Replanner Agent SHALL 评估分析完成度并返回 ReplanDecision
2. WHEN completeness_score < 0.9 且 replan_count < max_rounds THEN THE Replanner Agent SHALL 设置 should_replan=True
3. WHEN should_replan=True THEN THE 工作流 SHALL 路由回 Understanding Agent 进行新一轮分析
4. WHEN replan_count >= max_replan_rounds THEN THE 工作流 SHALL 强制路由到 END
5. WHEN should_replan=False THEN THE 工作流 SHALL 路由到 END 并返回最终结果

### Requirement 10: 流式执行测试

**User Story:** As a 测试工程师, I want to 验证流式执行功能, so that 确保实时反馈机制正常工作。

#### Acceptance Criteria

1. WHEN 使用 stream() 方法执行工作流 THEN THE WorkflowExecutor SHALL 产生 NODE_START 事件
2. WHEN 节点执行完成 THEN THE WorkflowExecutor SHALL 产生 NODE_COMPLETE 事件
3. WHEN LLM 生成响应 THEN THE WorkflowExecutor SHALL 产生 TOKEN 事件流
4. WHEN 工作流执行完成 THEN THE WorkflowExecutor SHALL 产生 COMPLETE 事件
5. WHEN 执行过程中发生错误 THEN THE WorkflowExecutor SHALL 产生 ERROR 事件

### Requirement 11: 错误处理流程测试

**User Story:** As a 测试工程师, I want to 验证错误处理流程, so that 确保系统在异常情况下能够优雅降级。

#### Acceptance Criteria

1. WHEN VizQL API 返回错误 THEN THE Execute Node SHALL 将错误信息记录到 state.errors
2. WHEN 字段映射失败 THEN THE FieldMapper Node SHALL 返回包含错误信息的状态更新
3. WHEN 任意节点发生异常 THEN THE WorkflowResult SHALL 设置 success=False 并包含错误详情
4. WHEN 查询结果为空 THEN THE Insight Agent SHALL 返回"查询结果为空"的洞察摘要

### Requirement 12: 维度层级分析流程测试

**User Story:** As a 测试工程师, I want to 验证维度层级分析流程, so that 确保下钻分析功能正常工作。

#### Acceptance Criteria

1. WHEN 元数据包含维度层级信息 THEN THE Insight Agent SHALL 使用维度层级进行分析
2. WHEN Replanner 生成探索问题 THEN THE exploration_questions SHALL 包含基于维度层级的下钻建议
3. WHEN 执行下钻分析 THEN THE 新一轮查询 SHALL 使用更细粒度的维度

### Requirement 13: 会话持久化测试

**User Story:** As a 测试工程师, I want to 验证会话持久化功能, so that 确保工作流状态能够正确保存和恢复。

#### Acceptance Criteria

1. WHEN 使用 SQLite checkpointer 创建工作流 THEN THE 系统 SHALL 创建 SQLite 数据库文件
2. WHEN 工作流执行完成 THEN THE checkpointer SHALL 保存工作流状态到数据库
3. WHEN 使用相同 thread_id 恢复会话 THEN THE 工作流 SHALL 能够从上次状态继续执行

### Requirement 14: 性能基准测试

**User Story:** As a 测试工程师, I want to 验证工作流执行性能, so that 确保系统响应时间在可接受范围内。

#### Acceptance Criteria

1. WHEN 执行简单聚合查询 THEN THE 完整工作流执行时间 SHALL 小于 30 秒
2. WHEN 执行复杂多维度查询 THEN THE 完整工作流执行时间 SHALL 小于 60 秒
3. WHEN 执行包含重规划的查询 THEN THE 每轮重规划执行时间 SHALL 小于 45 秒

---

## 完整端到端循环流程测试

### Requirement 15: 维度层级到重规划完整循环测试

**User Story:** As a 测试工程师, I want to 验证从维度层级到重规划的完整循环流程, so that 确保渐进式分析功能端到端正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"分析各地区销售情况" THEN THE 工作流 SHALL 完成 Understanding → FieldMapper → QueryBuilder → Execute → Insight → Replanner 的完整流程
2. WHEN Replanner 决定重规划 THEN THE 工作流 SHALL 基于维度层级生成下钻问题并路由回 Understanding
3. WHEN 第二轮分析执行 THEN THE Understanding Agent SHALL 理解新问题并生成更细粒度的 SemanticQuery
4. WHEN 多轮分析完成 THEN THE all_insights SHALL 累积所有轮次的洞察结果
5. WHEN 达到完成度阈值或最大轮数 THEN THE 工作流 SHALL 正确终止并返回完整分析报告

### Requirement 16: 地理维度下钻完整流程测试

**User Story:** As a 测试工程师, I want to 验证地理维度下钻的完整流程, so that 确保地理层级分析功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"各地区销售额" THEN THE 第一轮分析 SHALL 返回地区级别的销售数据和洞察
2. WHEN Replanner 基于元数据中的维度层级信息识别地理下钻路径 THEN THE Replanner LLM SHALL 选择省份作为下钻维度并生成下钻问题
3. WHEN 执行省份下钻 THEN THE 第二轮查询 SHALL 使用省份维度替代地区维度
4. WHEN 省份分析完成 THEN THE Replanner LLM SHALL 基于维度层级评估是否需要继续下钻到城市级别
5. WHEN 完整地理下钻完成 THEN THE final_report SHALL 包含地区→省份→城市的完整分析链

### Requirement 17: 时间维度下钻完整流程测试

**User Story:** As a 测试工程师, I want to 验证时间维度下钻的完整流程, so that 确保时间层级分析功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"年度销售趋势" THEN THE 第一轮分析 SHALL 返回年度级别的销售数据和洞察
2. WHEN Replanner 基于元数据中的时间维度层级信息识别异常年份 THEN THE Replanner LLM SHALL 选择季度作为下钻维度并生成针对异常年份的下钻问题
3. WHEN 执行季度下钻 THEN THE 第二轮查询 SHALL 使用季度维度并筛选特定年份
4. WHEN 季度分析完成 THEN THE Replanner LLM SHALL 基于维度层级评估是否需要继续下钻到月份级别
5. WHEN 完整时间下钻完成 THEN THE final_report SHALL 包含年→季度→月的完整分析链

### Requirement 18: 产品维度下钻完整流程测试

**User Story:** As a 测试工程师, I want to 验证产品维度下钻的完整流程, so that 确保产品层级分析功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"各产品类别销售情况" THEN THE 第一轮分析 SHALL 返回类别级别的销售数据和洞察
2. WHEN Replanner 基于元数据中的产品维度层级信息识别重点类别 THEN THE Replanner LLM SHALL 选择子类别作为下钻维度并生成针对重点类别的下钻问题
3. WHEN 执行子类别下钻 THEN THE 第二轮查询 SHALL 使用子类别维度并筛选特定类别
4. WHEN 子类别分析完成 THEN THE Replanner LLM SHALL 基于维度层级评估是否需要继续下钻到产品名称级别
5. WHEN 完整产品下钻完成 THEN THE final_report SHALL 包含类别→子类别→产品的完整分析链

---

## 扩展 LOD 表达式测试

### Requirement 19: FIXED LOD 多场景测试

**User Story:** As a 测试工程师, I want to 验证 FIXED LOD 表达式的多种使用场景, so that 确保 FIXED 计算在各种情况下正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"每个客户的首次购买日期" THEN THE Understanding Agent SHALL 识别需要 FIXED LOD 计算并生成包含 lod_type=FIXED 的 SemanticQuery
2. WHEN Understanding Agent 输出 FIXED LOD 语义 THEN THE QueryBuilder SHALL 基于 SemanticQuery 生成 FIXED [客户] : MIN([订单日期]) 表达式
3. WHEN 用户提问"每个产品的总销售额占类别总销售额的比例" THEN THE Understanding Agent SHALL 识别需要 FIXED LOD 进行类别级别聚合
4. WHEN 用户提问"每个地区的客户数量" THEN THE Understanding Agent SHALL 识别需要 FIXED LOD 结合 COUNTD 聚合
5. WHEN 用户提问"每个销售员的平均订单金额与公司平均的对比" THEN THE Understanding Agent SHALL 识别需要全局 FIXED LOD（无维度）

### Requirement 20: INCLUDE LOD 测试

**User Story:** As a 测试工程师, I want to 验证 INCLUDE LOD 表达式的使用场景, so that 确保 INCLUDE 计算正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"各地区的平均客户订单数" THEN THE Understanding Agent SHALL 识别需要 INCLUDE LOD 计算并生成包含 lod_type=INCLUDE 的 SemanticQuery
2. WHEN Understanding Agent 输出 INCLUDE LOD 语义 THEN THE QueryBuilder SHALL 基于 SemanticQuery 生成 INCLUDE [客户] : COUNT([订单]) 表达式
3. WHEN 用户提问"各类别的平均产品销售额" THEN THE Understanding Agent SHALL 识别需要 INCLUDE [产品] 进行产品级别聚合后再平均
4. WHEN INCLUDE LOD 查询执行 THEN THE QueryResult SHALL 包含正确的聚合计算结果

### Requirement 21: EXCLUDE LOD 测试

**User Story:** As a 测试工程师, I want to 验证 EXCLUDE LOD 表达式的使用场景, so that 确保 EXCLUDE 计算正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"各产品销售额与其类别平均销售额的差异" THEN THE Understanding Agent SHALL 识别需要 EXCLUDE LOD 计算并生成包含 lod_type=EXCLUDE 的 SemanticQuery
2. WHEN Understanding Agent 输出 EXCLUDE LOD 语义 THEN THE QueryBuilder SHALL 基于 SemanticQuery 生成 EXCLUDE [产品] : AVG([销售额]) 表达式
3. WHEN 用户提问"各月销售额与年度平均的对比" THEN THE Understanding Agent SHALL 识别需要 EXCLUDE [月份] 进行年度级别聚合
4. WHEN EXCLUDE LOD 查询执行 THEN THE QueryResult SHALL 包含正确的排除维度计算结果

---

## 扩展表计算测试

### Requirement 22: 累计计算多场景测试

**User Story:** As a 测试工程师, I want to 验证累计计算的多种场景, so that 确保累计功能在各种情况下正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"按月累计销售额" THEN THE QueryBuilder SHALL 生成 RUNNING_SUM(SUM([销售额])) 表计算
2. WHEN 用户提问"按季度累计利润" THEN THE QueryBuilder SHALL 生成 RUNNING_SUM(SUM([利润])) 表计算
3. WHEN 用户提问"按地区累计订单数" THEN THE QueryBuilder SHALL 生成 RUNNING_SUM(COUNT([订单])) 表计算
4. WHEN 累计计算执行 THEN THE QueryResult 中每行的累计值 SHALL 等于该行及之前所有行的总和

### Requirement 23: 排名计算多场景测试

**User Story:** As a 测试工程师, I want to 验证排名计算的多种场景, so that 确保排名功能在各种情况下正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"各产品销售额排名" THEN THE QueryBuilder SHALL 生成 RANK(SUM([销售额])) 表计算
2. WHEN 用户提问"各地区利润排名" THEN THE QueryBuilder SHALL 生成 RANK(SUM([利润])) 表计算
3. WHEN 用户提问"各客户订单数排名" THEN THE QueryBuilder SHALL 生成 RANK(COUNT([订单])) 表计算
4. WHEN 排名计算执行 THEN THE QueryResult 中排名值 SHALL 正确反映度量值的相对顺序

### Requirement 24: 移动计算测试

**User Story:** As a 测试工程师, I want to 验证移动计算的使用场景, so that 确保移动平均等功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"3个月移动平均销售额" THEN THE QueryBuilder SHALL 生成 WINDOW_AVG(SUM([销售额]), -2, 0) 表计算
2. WHEN 用户提问"同比增长率" THEN THE QueryBuilder SHALL 生成包含 LOOKUP 的同比计算表达式
3. WHEN 用户提问"环比增长率" THEN THE QueryBuilder SHALL 生成包含 LOOKUP 的环比计算表达式
4. WHEN 移动计算执行 THEN THE QueryResult SHALL 包含正确的移动窗口计算结果

### Requirement 25: 百分比计算测试

**User Story:** As a 测试工程师, I want to 验证百分比计算的使用场景, so that 确保占比分析功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"各产品类别销售额占比" THEN THE QueryBuilder SHALL 生成 SUM([销售额])/TOTAL(SUM([销售额])) 表计算
2. WHEN 用户提问"各地区利润占比" THEN THE QueryBuilder SHALL 生成 SUM([利润])/TOTAL(SUM([利润])) 表计算
3. WHEN 百分比计算执行 THEN THE QueryResult 中所有占比值的总和 SHALL 等于 100%

---

## 扩展时间筛选测试

### Requirement 26: 季度时间筛选测试

**User Story:** As a 测试工程师, I want to 验证季度时间筛选的使用场景, so that 确保季度筛选功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"2024年第一季度销售额" THEN THE Understanding Agent SHALL 生成包含 Q1 2024 筛选的 SemanticQuery
2. WHEN 用户提问"2023年Q3和Q4的销售对比" THEN THE Understanding Agent SHALL 生成包含多季度筛选的 SemanticQuery
3. WHEN 用户提问"上季度各产品类别销售额" THEN THE Understanding Agent SHALL 生成包含上季度相对筛选的 SemanticQuery
4. WHEN 季度筛选执行 THEN THE QueryResult SHALL 只包含指定季度范围内的数据

### Requirement 27: 周时间筛选测试

**User Story:** As a 测试工程师, I want to 验证周时间筛选的使用场景, so that 确保周筛选功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"本周销售额" THEN THE Understanding Agent SHALL 生成包含本周相对筛选的 SemanticQuery
2. WHEN 用户提问"上周各地区销售额" THEN THE Understanding Agent SHALL 生成包含上周相对筛选的 SemanticQuery
3. WHEN 用户提问"最近4周的销售趋势" THEN THE Understanding Agent SHALL 生成包含最近N周相对筛选的 SemanticQuery
4. WHEN 周筛选执行 THEN THE QueryResult SHALL 只包含指定周范围内的数据

### Requirement 28: 日时间筛选测试

**User Story:** As a 测试工程师, I want to 验证日时间筛选的使用场景, so that 确保日筛选功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"今天的销售额" THEN THE Understanding Agent SHALL 生成包含今天相对筛选的 SemanticQuery
2. WHEN 用户提问"昨天各产品类别销售额" THEN THE Understanding Agent SHALL 生成包含昨天相对筛选的 SemanticQuery
3. WHEN 用户提问"最近7天的销售趋势" THEN THE Understanding Agent SHALL 生成包含最近N天相对筛选的 SemanticQuery
4. WHEN 用户提问"2024年12月1日的销售明细" THEN THE Understanding Agent SHALL 生成包含具体日期筛选的 SemanticQuery
5. WHEN 日筛选执行 THEN THE QueryResult SHALL 只包含指定日期范围内的数据

### Requirement 29: 复合时间筛选测试

**User Story:** As a 测试工程师, I want to 验证复合时间筛选的使用场景, so that 确保复杂时间条件筛选功能正常工作。

#### Acceptance Criteria

1. WHEN 用户提问"2024年每个月的第一周销售额" THEN THE Understanding Agent SHALL 生成包含年份和周筛选的复合 SemanticQuery
2. WHEN 用户提问"每年Q4的销售趋势" THEN THE Understanding Agent SHALL 生成包含季度筛选的多年对比 SemanticQuery
3. WHEN 用户提问"工作日与周末的销售对比" THEN THE Understanding Agent SHALL 生成包含星期筛选的 SemanticQuery
4. WHEN 复合时间筛选执行 THEN THE QueryResult SHALL 正确应用所有时间条件

---

## 洞察与查询联动测试

### Requirement 30: 洞察驱动的查询优化测试

**User Story:** As a 测试工程师, I want to 验证洞察分析如何驱动后续查询优化, so that 确保智能分析功能正常工作。

#### Acceptance Criteria

1. WHEN Insight Agent 识别数据异常 THEN THE Replanner SHALL 生成针对异常的深入分析问题
2. WHEN Insight Agent 识别帕累托分布 THEN THE Replanner SHALL 生成针对 Top N 的详细分析问题
3. WHEN Insight Agent 识别趋势变化 THEN THE Replanner SHALL 生成针对变化点的原因分析问题
4. WHEN 洞察驱动的新查询执行 THEN THE 新一轮分析 SHALL 聚焦于洞察发现的关键点

### Requirement 31: 多轮洞察累积测试

**User Story:** As a 测试工程师, I want to 验证多轮分析中洞察的正确累积, so that 确保渐进式分析的完整性。

#### Acceptance Criteria

1. WHEN 第一轮分析完成 THEN THE insights 列表 SHALL 包含第一轮的所有洞察
2. WHEN 第二轮分析完成 THEN THE all_insights 列表 SHALL 包含第一轮和第二轮的所有洞察
3. WHEN 多轮分析完成 THEN THE final_report SHALL 综合所有轮次的洞察生成完整报告
4. WHEN 洞察累积 THEN THE 系统 SHALL 避免重复的洞察内容

### Requirement 32: 查询结果到洞察的完整链路测试

**User Story:** As a 测试工程师, I want to 验证从查询结果到洞察生成的完整链路, so that 确保数据分析的准确性。

#### Acceptance Criteria

1. WHEN QueryResult 包含数据 THEN THE Insight Agent SHALL 基于实际数据生成洞察
2. WHEN QueryResult 包含多个维度 THEN THE Insight Agent SHALL 分析维度间的关系
3. WHEN QueryResult 包含时间序列 THEN THE Insight Agent SHALL 识别趋势和周期性
4. WHEN QueryResult 包含异常值 THEN THE Insight Agent SHALL 标识并解释异常
