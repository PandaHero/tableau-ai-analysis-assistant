# Prompt Optimization Requirements

## Introduction

基于业界公认的上下文工程（Prompt Engineering）最佳实践，重新设计prompt模板架构。目标是在保持准确率的前提下，将Understanding Agent从5-10秒降到2-3秒，Task Planner从30秒+降到5-10秒。

## Glossary

- **Prompt Engineering**: 上下文工程，设计和优化LLM输入的学科
- **Token Efficiency**: Token效率，用最少的token达到目标效果
- **Few-Shot Learning**: 少样本学习，通过少量示例引导LLM行为
- **Constitutional AI**: 宪法式AI，通过规则约束而非说教来引导行为
- **Chain-of-Thought (CoT)**: 思维链，通过展示或引导推理过程提高准确性
- **Implicit CoT**: 隐式思维链，在prompt中引导推理但不要求输出推理过程
- **Schema Linking**: 字段映射，将业务术语映射到技术字段（Text-to-SQL的瓶颈）
- **Baseline**: 基准，优化前的性能指标

## Requirements

### Requirement 1: 建立评判标准（基于业界最佳实践）

**User Story:** 作为系统架构师，我希望建立基于业界最佳实践的评判标准，以便有明确的优化目标

#### Acceptance Criteria

1. WHEN 评估prompt质量时，THE System SHALL 使用定量指标：Token效率、响应速度、准确率、成本
2. WHEN 评估prompt质量时，THE System SHALL 使用定性指标：清晰性、可维护性、可测试性、可扩展性
3. WHEN 优化prompt时，THE System SHALL 确保Understanding Agent的system message < 800 tokens
4. WHEN 优化prompt时，THE System SHALL 确保Task Planner的system message < 1200 tokens
5. WHEN 测试优化效果时，THE System SHALL 确保准确率不低于baseline的95%

**定量指标表：**

| Agent | 指标 | Baseline | Target | 测量方法 |
|-------|------|----------|--------|----------|
| Understanding | Token数 | ~2000 | < 800 | 统计system message tokens |
| Understanding | 响应时间 | 5-10s | 2-3s | P95延迟 |
| Understanding | 准确率 | 100% | > 95% | 与baseline对比 |
| Task Planner | Token数 | ~3000 | < 1200 | 统计system message tokens |
| Task Planner | 响应时间 | 30s+ | 5-10s | P95延迟 |
| Task Planner | 准确率 | 100% | > 95% | 与baseline对比 |

### Requirement 2: 采用Anthropic的Constitutional AI原则

**User Story:** 作为系统开发者，我希望采用Constitutional AI原则，以便用规则约束而非说教

#### Acceptance Criteria

1. WHEN 定义行为约束时，THE System SHALL 使用"MUST/MUST NOT"规则而非"请注意"、"重要"等说教
2. WHEN 提供规则时，THE System SHALL 使用简洁的陈述句（不超过10词）
3. WHEN 规则之间有冲突时，THE System SHALL 明确优先级（用编号）
4. WHEN 规则超过10条时，THE System SHALL 评估是否可以合并或删除
5. WHEN 使用XML标签时，THE System SHALL 明确分隔不同类型的信息（如`<rules>`, `<examples>`, `<context>`）

### Requirement 3: 采用OpenAI的Few-Shot最佳实践

**User Story:** 作为系统开发者，我希望采用Few-Shot最佳实践，以便用最少的示例达到最好的效果

#### Acceptance Criteria

1. WHEN 任务简单且schema清晰时，THE System SHALL 使用Zero-Shot（不提供示例）
2. WHEN 任务有歧义或特殊规则时，THE System SHALL 使用One-Shot（1个示例）
3. WHEN 任务复杂且有多种模式时，THE System SHALL 使用Few-Shot（2-3个示例）
4. WHEN 提供示例时，THE System SHALL 使用最简输入和最简输出（去除无关字段）
5. WHEN 示例能说明规则时，THE System SHALL 不再添加文字说明

### Requirement 4: 采用Microsoft的CRISPE简化框架

**User Story:** 作为系统架构师，我希望采用简化的CRISPE框架，以便结构清晰且易于维护

#### Acceptance Criteria

1. WHEN 设计prompt结构时，THE System SHALL 采用"Role + Task + Context + Format"四段式
2. WHEN 定义Role时，THE System SHALL 用一句话说明（不超过20词）
3. WHEN 定义Task时，THE System SHALL 用一句话说明输入输出（不超过30词）
4. WHEN 提供Context时，THE System SHALL 只包含领域特定知识（不超过200词）
5. WHEN 定义Format时，THE System SHALL 依赖JSON Schema + 最多3条补充规则

### Requirement 5: 采用简洁的隐式CoT（核心策略）

**User Story:** 作为系统开发者，我希望采用简洁的隐式Chain-of-Thought，以便提高推理质量但不增加token消耗

#### Acceptance Criteria

1. WHEN 任务需要多步推理时，THE System SHALL 使用隐式CoT（引导推理但不要求输出）
2. WHEN 定义推理步骤时，THE System SHALL 限制在3-5步以内（学术研究表明超过5步收益递减）
3. WHEN 表达推理步骤时，THE System SHALL 使用简洁格式："1. X → Y, 2. A → B, 3. C → D"（不超过3行）
4. WHEN 推理涉及决策时，THE System SHALL 使用IF-THEN格式明确分支逻辑
5. WHEN 推理步骤可以通过示例展示时，THE System SHALL 优先使用示例（Few-Shot CoT）

**CoT最佳实践（基于学术研究）：**

| 方法 | 适用场景 | Token成本 | 准确率提升 | 我们的选择 |
|------|---------|----------|-----------|-----------|
| 无CoT | 简单任务 | 低 | Baseline | ❌ 任务复杂 |
| 详细CoT (10+步) | 极复杂任务 | 很高 | +2-5% | ❌ 成本太高 |
| 简洁CoT (3-5步) | 中等复杂任务 | 中 | +5-10% | ✅ 最佳平衡 |
| Few-Shot CoT | 有模式的任务 | 高 | +10-15% | ✅ 关键场景使用 |

**示例对比：**

❌ **详细CoT（当前，~100行）**：
```
Step 1: Extract ALL Entities
Scan the question and list every noun that could represent a data field.
Do not skip any entity - completeness is critical.
Write down all entities before proceeding to Step 2.

Step 2: Classify Each Entity
For each entity from Step 1, determine its type:
- Dimension: categorical data used for grouping or filtering
- Measure: numeric data that can be aggregated
- Date field: temporal data
...
```

✅ **简洁隐式CoT（优化后，~20行）**：
```
Task: Extract and classify entities.

Process:
1. Identify entities → mentioned_dimensions/measures/date_fields
2. Check aggregation → *_aggregations (only if aggregated)
3. Extract time → time_range (if present)

Rules:
- mentioned_* = ALL entities
- *_aggregations = ONLY aggregated ones
- IF exploratory THEN needs_exploration=true
```

### Requirement 6: 基于Text-to-SQL研究的核心优化

**User Story:** 作为系统架构师，我希望应用Text-to-SQL学术研究的核心发现，以便针对性地优化瓶颈

#### Acceptance Criteria

1. WHEN 优化Schema Linking时（字段映射瓶颈），THE System SHALL 在prompt中提供清晰的匹配规则（category first, then name）
2. WHEN 提供Schema信息时，THE System SHALL 确保metadata包含category和level信息（帮助快速匹配）
3. WHEN 使用Few-Shot时，THE System SHALL 限制在1-2个示例（研究表明超过3个收益递减）
4. WHEN 使用CoT时，THE System SHALL 采用简洁隐式CoT（3-5步，研究表明最佳平衡）
5. WHEN 评估优化效果时，THE System SHALL 重点测量Schema Linking的准确率（这是主要瓶颈）

**Text-to-SQL研究核心发现（Spider/WikiSQL Benchmark）：**

| 发现 | 影响 | 我们的应对 |
|------|------|-----------|
| Schema Linking是瓶颈 | 字段映射错误占70%+ | 优化Task Planner的映射规则 |
| Few-Shot收益递减 | 超过3个示例提升<2% | 限制在1-2个精准示例 |
| CoT有效但要简洁 | 3-5步最佳，10+步收益递减 | 使用简洁隐式CoT |
| Schema质量关键 | 好的schema > 复杂prompt | 确保metadata包含category/level |
| 规则要精准 | 10条精准规则 > 50条模糊规则 | 每个Agent限制5-10条核心规则 |

### Requirement 7: Question Boost优化（找到平衡点）

**User Story:** 作为系统开发者，我希望优化Question Boost的增强策略，以便在"补全必要信息"和"不过度增强"之间找到平衡

#### Acceptance Criteria

1. WHEN 评估是否增强时，THE System SHALL 只补全缺失的必要信息（时间范围、度量聚合方式、分析意图）
2. WHEN 问题已包含足够信息时，THE System SHALL 不添加可选的增强（维度分解、对比分析、TopN、排序）
3. WHEN 定义增强规则时，THE System SHALL 使用"MUST补全 vs DON'T补全"清单（不超过10条）
4. WHEN 提供示例时，THE System SHALL 展示1-2个"适度增强"的示例（不是过度增强或不增强）
5. WHEN 测试优化效果时，THE System SHALL 确保增强后的问题保持用户原意且可执行

**增强判断标准：**

| 信息类型 | 判断 | 示例 |
|---------|------|------|
| 时间范围 | MUST补全（如果涉及趋势/对比） | "销售趋势" → "最近一个月的销售趋势" |
| 度量聚合 | MUST补全（如果有歧义） | "利润率" → "平均利润率" |
| 分析意图 | MUST补全（如果完全模糊） | "看一下销售" → "最近一个月的销售额" |
| 维度分解 | DON'T补全（除非明确暗示） | ❌ "销售额" → "各地区各产品的销售额" |
| 对比分析 | DON'T补全（除非明确要求） | ❌ "销售额" → "销售额与上月对比" |
| TopN限制 | DON'T补全（除非明确要求） | ❌ "产品销售额" → "销售额TOP10产品" |
| 排序方式 | DON'T补全（除非明确要求） | ❌ "各地区销售额" → "各地区销售额降序" |

**示例对比：**

| 输入 | ❌ 过度增强 | ✅ 适度增强 | ❌ 不增强 |
|------|-----------|-----------|---------|
| "看一下销售" | "最近一个月各地区各产品的销售额与上月对比TOP10" | "最近一个月的销售额" | "看一下销售" |
| "产品利润" | "各产品类别的平均利润率与去年同期对比" | "各产品的利润" | "产品利润" |
| "销售趋势" | "最近6个月各地区的销售额趋势与去年同期对比" | "最近一个月的销售额趋势" | "销售趋势" |

### Requirement 8: Understanding Agent优化（基于最佳实践）

**User Story:** 作为系统开发者，我希望基于最佳实践优化Understanding Agent，以便达到性能目标

#### Acceptance Criteria

1. WHEN 设计Understanding prompt时，THE System SHALL 采用"Role + Task + VizQL Rules + Output Constraints"结构
2. WHEN 定义Task时，THE System SHALL 说明"Extract and classify entities into dimensions/measures/dates"（不超过30词）
3. WHEN 提供VizQL Rules时，THE System SHALL 只包含拆分决策表（不超过15行）
4. WHEN 定义Output Constraints时，THE System SHALL 使用3-5条MUST/MUST NOT规则
5. WHEN 测试优化效果时，THE System SHALL 确保system message < 800 tokens且响应时间2-3秒

### Requirement 9: Task Planner Agent优化（针对Schema Linking瓶颈）

**User Story:** 作为系统开发者，我希望基于最佳实践优化Task Planner Agent，以便达到性能目标

#### Acceptance Criteria

1. WHEN 设计Task Planner prompt时，THE System SHALL 采用"Role + Task + Mapping Rules + Output Constraints"结构
2. WHEN 定义Task时，THE System SHALL 说明"Map business terms to technical fields and generate Intents"（不超过30词）
3. WHEN 提供Mapping Rules时，THE System SHALL 使用决策树或表格（不超过20行）
4. WHEN 定义Output Constraints时，THE System SHALL 使用3-5条MUST/MUST NOT规则
5. WHEN 测试优化效果时，THE System SHALL 确保system message < 1200 tokens且响应时间5-10秒

### Requirement 10: 保留领域特定逻辑，移除通用说教

**User Story:** 作为系统开发者，我希望保留领域特定的执行逻辑，但移除通用能力的说教，以便在准确性和效率之间找到平衡

#### Acceptance Criteria

1. WHEN 执行方式是领域特定时，THE System SHALL 保留"怎么做"的说明
2. WHEN 执行方式是LLM通用能力时，THE System SHALL 只说明"做什么"
3. WHEN 有多种执行路径时，THE System SHALL 明确决策逻辑（IF-THEN格式）
4. WHEN 需要保证一致性时，THE System SHALL 说明执行顺序（"First X, then Y"）
5. WHEN 评估内容时，THE System SHALL 删除所有元指令和说教内容

**判断标准：保留 vs 删除**

| 场景 | 保留（领域特定） | 删除（通用能力/说教） |
|------|----------------|---------------------|
| 数据结构 | ✅ "mentioned_* = ALL, *_aggregations = ONLY aggregated" | ❌ "Make sure to include all" |
| 决策逻辑 | ✅ "IF exploratory THEN don't split" | ❌ "When you see exploratory keywords, you should..." |
| 执行顺序 | ✅ "First extract, then classify, then identify aggregations" | ❌ "Step 1: Read. Step 2: Think. Step 3: Extract..." |
| 匹配规则 | ✅ "Match by category first, then name similarity" | ❌ "Carefully compare field names" |
| 约束 | ✅ "MUST NOT: invent fields" | ❌ "It's critical not to invent fields" |
| 任务定义 | ✅ "Extract entities" | ❌ "Scan every word to find nouns" |

**保留"怎么做"的4个场景：**
1. 领域特定的数据结构（如mentioned_* vs *_aggregations的区别）
2. 有多种可能路径的决策逻辑（如何时拆分/不拆分）
3. 需要保证一致性的执行顺序（如先提取再分类）
4. 容易产生歧义的匹配规则（如category优先于name）

**删除"怎么做"的3个场景：**
1. LLM的通用能力（如如何提取实体、如何分类）
2. 元指令和说教（如"仔细"、"重要"、"注意"）
3. 过度详细的步骤分解（如"Step 1... Step 2... Step 3..."）

### Requirement 11: 重构base模板架构

**User Story:** 作为系统架构师，我希望重构base模板架构，以便支持最佳实践

#### Acceptance Criteria

1. WHEN 设计base模板时，THE System SHALL 采用"Role + Task + Context + Constraints"四段式（不是6段式）
2. WHEN 实现StructuredPrompt时，THE System SHALL 移除Principles和Output Requirements sections
3. WHEN 提供Context时，THE System SHALL 使用get_domain_knowledge()方法（子类override）
4. WHEN 提供Constraints时，THE System SHALL 使用get_constraints()方法返回简洁列表（不超过5条）
5. WHEN 注入JSON Schema时，THE System SHALL 使用简洁的指令（不超过50词）

### Requirement 12: 性能验证和A/B测试

**User Story:** 作为系统开发者，我希望进行严格的性能验证和A/B测试，以便确保优化效果

#### Acceptance Criteria

1. WHEN 优化完成后，THE System SHALL 准备测试数据集（至少20个真实问题）
2. WHEN 测试时，THE System SHALL 同时运行baseline和优化版本
3. WHEN 收集指标时，THE System SHALL 记录token数、响应时间、准确率
4. WHEN 评估准确率时，THE System SHALL 对比输出的关键字段（entities, sub_questions, intents）
5. WHEN 准确率低于95%时，THE System SHALL 分析失败case并调整prompt

**测试计划：**

| 阶段 | 测试内容 | 成功标准 |
|------|---------|---------|
| 1. Token统计 | 统计system message tokens | Understanding < 800, Task Planner < 1200 |
| 2. 速度测试 | 测试20个问题的P95延迟 | Understanding 2-3s, Task Planner 5-10s |
| 3. 准确率测试 | 对比baseline输出 | 关键字段匹配率 > 95% |
| 4. 失败分析 | 分析不匹配的case | 识别pattern并调整 |
| 5. 回归测试 | 重新测试所有case | 确保调整后仍满足标准 |
