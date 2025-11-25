# Prompt Optimization Design

## Overview

基于需求文档中确立的最佳实践，重新设计四个Agent的prompt模板：Question Boost、Understanding、Task Planner、Dimension Hierarchy。核心策略是采用"Schema优先 + 简洁隐式CoT + 领域特定规则"的方法，将响应时间从5-30秒降低到2-10秒，同时保持95%以上的准确率。

### 核心设计原则

#### 原则1：功能完整性优先于Token优化

**⚠️ 关键警告**：优化token是手段，不是目的。功能完整性永远是第一位的。

**必须保留的内容**：
- 所有关键的业务规则（如探索式问题的处理）
- 所有重要的决策逻辑（如何时拆分/不拆分）
- 所有必要的数据结构说明（mentioned_* vs *_aggregations）
- 所有关键的约束条件（如needs_exploration标记）

**可以删除的内容**：
- 重复的说明（schema已经说过的）
- 元指令和说教（"请仔细"、"重要"）
- 过度详细的步骤（"Step 1... Step 2..."）
- 通用能力的教学（LLM已知的）

**验证标准**：
- ✅ Token减少 + 准确率保持 = 成功
- ❌ Token减少 + 准确率下降 = 失败

#### 原则2：Schema优先

**关键洞察**：结构化I/O的Field description已经做了很多工作，prompt不应重复。

**三者的作用分工**：
1. **Input Schema (with description)**: 告诉LLM"输入是什么"
2. **Output Schema (with description)**: 告诉LLM"输出应该是什么样"
3. **Prompt模板**: 告诉LLM"如何从输入生成输出"（领域规则、决策逻辑）

**Prompt的独特价值**：
- 领域特定的决策规则（IF-THEN）
- 多个字段之间的关系
- 执行顺序和优先级
- Schema无法表达的约束

**避免重复**：
- ❌ 如果schema说"ALL entities"，prompt不再重复
- ❌ 如果schema说"ONLY aggregated"，prompt不再重复
- ✅ Prompt只说schema无法表达的内容（如决策规则）

#### 原则3：保留关键业务规则

**Understanding Agent必须保留的规则**：
- 探索式问题识别（why/reason/explain关键词）
- needs_exploration标记逻辑
- mentioned_* vs *_aggregations的区别
- 拆分决策表（何时拆分/不拆分）
- 实体分类规则（dimensions/measures/dates）

**Task Planner必须保留的规则**：
- 字段映射规则（category first, then name）
- Intent类型决策
- 粒度选择规则（prefer coarse level）
- TopN处理规则

**Question Boost必须保留的规则**：
- MUST补全 vs DON'T补全的清单
- 适度增强的平衡点

#### 原则4：语言一致性

**不要中英文夹杂**：
- ❌ 错误：`Keywords: "why", "reason", "为什么", "原因"`
- ✅ 正确：`Keywords: "why", "reason", "explain" (or Chinese equivalents)`

**原因**：
- 中英文夹杂会让LLM困惑
- 保持prompt语言的一致性
- 如果需要支持中文，用描述性语言说明

#### 原则5：测试驱动优化

**优化流程**：
1. 减少token
2. 测试准确率
3. 如果准确率下降 → 恢复关键规则
4. 重新测试
5. 重复直到达到平衡

**不要一次性删除太多**，逐步优化并验证。

## Architecture

### 当前架构（保持不变）
```
User Question
    ↓
Question Boost Agent (优化prompt)
    ↓
Understanding Agent (优化prompt)
    ↓
Task Planner Agent (优化prompt)
    ↓
Query Builder
```

### Base模板重构

**当前（6段式）**：
```
Role → Task → Context → Principles → Constraints → Output Requirements
```

**优化后（4段式 + Schema自动注入）**：
```
Role → Task → Domain Knowledge → Constraints → [Output Format (自动注入)]
```

**变化**：
- 移除Principles section（合并到Task中的简洁CoT）
- 移除Output Requirements section（依赖JSON Schema自动注入）
- Context重命名为Domain Knowledge（更明确）
- Output Format不算在4段式中，因为它是自动生成的技术细节

**最终呈现给LLM的结构**：
```
# ROLE
...

# TASK
...

# DOMAIN KNOWLEDGE
...

# CONSTRAINTS
...

# OUTPUT FORMAT
You must output JSON following this schema:
{json_schema}
```

**说明**：我们称之为"4段式"是因为关注点在业务逻辑（Role/Task/Knowledge/Constraints），Schema是自动注入的技术格式。

## Components and Interfaces

### 1. Base Prompt重构

**新的StructuredPrompt基类**：

```python
class StructuredPrompt(BasePrompt):
    """4段式结构化prompt"""
    
    def get_role(self) -> str:
        """角色定义（1句话，不超过20词）"""
        pass
    
    def get_task(self) -> str:
        """任务定义 + 简洁CoT（不超过50词）"""
        pass
    
    def get_domain_knowledge(self) -> str:
        """领域特定知识（不超过200词）"""
        pass
    
    def get_constraints(self) -> str:
        """约束列表（3-5条，每条不超过10词）"""
        pass
    
    def get_system_message(self) -> str:
        """组装system message"""
        sections = []
        if role := self.get_role():
            sections.append(f"# ROLE\n{role}")
        if task := self.get_task():
            sections.append(f"# TASK\n{task}")
        if knowledge := self.get_domain_knowledge():
            sections.append(f"# DOMAIN KNOWLEDGE\n{knowledge}")
        if constraints := self.get_constraints():
            sections.append(f"# CONSTRAINTS\n{constraints}")
        return "\n\n".join(sections)
```

### 2. Question Boost Agent

**目标**：
- Token: < 400 (当前~1500)
- 响应时间: < 2秒 (当前3-5秒)
- 策略: 适度增强（补全必要信息，不过度增强）
- **Schema优先**: Field description已说明各字段含义，prompt只说决策规则

**Prompt结构**：

```python
class QuestionBoostPrompt(DataAnalysisPrompt):
    
    def get_role(self) -> str:
        return "Data analyst who completes missing essential information."
    
    def get_task(self) -> str:
        return """Evaluate and add ONLY missing essential info.

Process: Check essentials → IF missing THEN add minimal context → ELSE return original"""
    
    def get_domain_knowledge(self) -> str:
        return """Metadata: {metadata}

Decision rules:
MUST补全: time (if trend/comparison), aggregation (if ambiguous), intent (if vague)
DON'T补全: dimensions, comparisons, TopN, sorting (unless explicit)"""
    
    def get_constraints(self) -> str:
        return """MUST NOT: change intent, add optional info, use technical names
MUST: preserve wording, minimal changes"""
```

**Token预算**：
- Role: ~10 tokens
- Task: ~30 tokens
- Domain Knowledge: ~60 tokens
- Constraints: ~30 tokens
- JSON Schema: ~200 tokens (schema description做主要工作)
- **Total: ~330 tokens** ✅ (比目标更优)

### 3. Understanding Agent

**目标**：
- Token: < 600 (当前~2000)
- 响应时间: 2-3秒 (当前5-10秒)
- 策略: 简洁隐式CoT + VizQL拆分规则
- **Schema优先**: Field description已说明mentioned_* vs *_aggregations区别，prompt只说决策规则

**Prompt结构**：

```python
class UnderstandingPrompt(VizQLPrompt):
    
    def get_role(self) -> str:
        return "Query analyzer who extracts entities and decides decomposition."
    
    def get_task(self) -> str:
        return """Extract entities, classify types, decide if split needed.

Process: Extract → Classify → Check aggregation → Decide split"""
    
    def get_domain_knowledge(self) -> str:
        return """Metadata: {metadata}

Split decision:
| Scenario | Action |
|----------|--------|
| Multiple time periods | Split (separate queries) |
| Cross-query calculation | Split (post-processing) |
| Exploratory (why/reason) | Don't split (needs_exploration=true) |
| Single query sufficient | Don't split |"""
    
    def get_constraints(self) -> str:
        return """MUST NOT: invent entities, use technical names, split exploratory
MUST: extract ALL entities, use business terms"""
```

**Token预算**：
- Role: ~12 tokens
- Task: ~25 tokens
- Domain Knowledge: ~80 tokens
- Constraints: ~30 tokens
- JSON Schema: ~400 tokens (schema description做主要工作)
- **Total: ~547 tokens** ✅ (比目标更优)

### 4. Task Planner Agent

**目标**：
- Token: < 900 (当前~3000)
- 响应时间: 5-10秒 (当前30秒+)
- 策略: 简洁映射规则 + 决策树
- **Schema优先**: Field description已说明Intent类型，prompt只说映射规则

**Prompt结构**：

```python
class TaskPlannerPrompt(VizQLPrompt):
    
    def get_role(self) -> str:
        return "Field mapper who converts business terms to technical fields."
    
    def get_task(self) -> str:
        return """Map business terms to fields, generate Intents.

Process: Match category → Match name → Generate Intent → Add filters"""
    
    def get_domain_knowledge(self) -> str:
        return """Resources: {original_question}, {sub_questions}, {metadata}, {dimension_hierarchy}

Mapping rules:
1. Match category first (product/geographic/temporal/organizational)
2. Then match name similarity within category
3. Prefer coarse level (1-2) unless fine detail needed
4. Use aggregation from sub-question's *_aggregations dict"""
    
    def get_constraints(self) -> str:
        return """MUST NOT: use non-existent fields, modify TimeRange, add TopN without keywords
MUST: one subtask per sub-question, match category first"""
```

**Token预算**：
- Role: ~12 tokens
- Task: ~25 tokens
- Domain Knowledge: ~120 tokens
- Constraints: ~40 tokens
- JSON Schema: ~600 tokens (schema description做主要工作)
- **Total: ~797 tokens** ✅ (比目标更优)

### 5. Dimension Hierarchy Agent

**目标**：
- Token: < 500 (当前~1200)
- 响应时间: < 3秒 (当前5-8秒)
- 策略: 简洁推断规则
- **Schema优先**: Field description已说明各字段含义，prompt只说推断规则

**Prompt结构**：

```python
class DimensionHierarchyPrompt(DataAnalysisPrompt):
    
    def get_role(self) -> str:
        return "Data modeler who infers dimension hierarchy attributes."
    
    def get_task(self) -> str:
        return """Infer category, level, and relationships for each dimension.

Process: Analyze name/samples → Assign category → Determine level → Identify parent/child"""
    
    def get_domain_knowledge(self) -> str:
        return """Dimensions: {dimensions}

Level assignment (1=coarsest, 5=finest):
- Semantic priority: explicit indicators (一级/二级) > category patterns > unique_count
- Category patterns: Country/Year/Top Category → 1, Province/Quarter → 2, City/Month → 3, District/Day → 4, Address/Timestamp → 5
- Unique count: <10 → 1-2, 10-50 → 2-3, 50-200 → 3-4, 200-1000 → 4, >1000 → 5

Category types: Geographic, Temporal, Product, Customer, Organizational, Financial, Other"""
    
    def get_constraints(self) -> str:
        return """MUST NOT: assign level outside 1-5, create circular relationships
MUST: prioritize semantic over count, assign appropriate category"""
```

**Token预算**：
- Role: ~10 tokens
- Task: ~25 tokens
- Domain Knowledge: ~150 tokens
- Constraints: ~30 tokens
- JSON Schema: ~250 tokens (schema description做主要工作)
- **Total: ~465 tokens** ✅

## Data Models

### 优化前后对比

| Agent | 当前Tokens | 优化后Tokens | 减少 | 当前响应时间 | 目标响应时间 |
|-------|-----------|-------------|------|-------------|-------------|
| Question Boost | ~1500 | ~330 | 78% | 3-5s | <2s |
| Understanding | ~2000 | ~547 | 73% | 5-10s | 2-3s |
| Task Planner | ~3000 | ~797 | 73% | 30s+ | 5-10s |
| Dimension Hierarchy | ~1200 | ~465 | 61% | 5-8s | <3s |

**关键优化**：采用"Schema优先"原则，让Field description承担更多工作，prompt只说决策规则。

### Token分配策略

**Question Boost (330 tokens)**:
- Role: 10 (3%)
- Task: 30 (9%)
- Domain Knowledge: 60 (18%)
- Constraints: 30 (9%)
- JSON Schema: 200 (61%) ← Schema做主要工作

**Understanding (547 tokens)**:
- Role: 12 (2%)
- Task: 25 (5%)
- Domain Knowledge: 80 (15%)
- Constraints: 30 (5%)
- JSON Schema: 400 (73%) ← Schema做主要工作

**Task Planner (797 tokens)**:
- Role: 12 (2%)
- Task: 25 (3%)
- Domain Knowledge: 120 (15%)
- Constraints: 40 (5%)
- JSON Schema: 600 (75%) ← Schema做主要工作

**Dimension Hierarchy (465 tokens)**:
- Role: 10 (2%)
- Task: 25 (5%)
- Domain Knowledge: 150 (32%)
- Constraints: 30 (6%)
- JSON Schema: 250 (54%) ← Schema做主要工作

**关键发现**：JSON Schema占比50-75%，这是正确的！Schema的Field description应该承担主要的说明工作。

## Error Handling

### 准确率保障

**测试策略**：
1. 准备20个真实问题作为测试集
2. 运行baseline和优化版本
3. 对比关键字段：
   - Question Boost: boosted_question, changes
   - Understanding: mentioned_*, sub_questions, needs_exploration
   - Task Planner: field mappings, Intent types

**失败处理**：
- 如果准确率 < 95%，分析失败case
- 识别pattern（如特定类型的问题）
- 调整对应的Domain Knowledge或Constraints
- 重新测试直到达标

### 降级策略

如果优化版本准确率不达标：
1. **Phase 1**: 增加1个Few-Shot示例（+100-200 tokens）
2. **Phase 2**: 扩展Domain Knowledge（+50-100 tokens）
3. **Phase 3**: 如果仍不达标，回退到baseline

## Testing Strategy

### 测试计划

**阶段1：Token统计**
- 统计每个Agent的system message tokens
- 确保：Question Boost < 500, Understanding < 800, Task Planner < 1200

**阶段2：速度测试**
- 测试20个问题的P95延迟
- 确保：Question Boost < 2s, Understanding 2-3s, Task Planner 5-10s

**阶段3：准确率测试**
- 对比baseline输出的关键字段
- 确保：匹配率 > 95%

**阶段4：失败分析**
- 分析不匹配的case
- 识别pattern并调整prompt

**阶段5：回归测试**
- 重新测试所有case
- 确保调整后仍满足标准

### 测试数据集

准备20个真实问题，覆盖：
- 简单问题（5个）：单一度量，明确时间
- 中等问题（10个）：多维度，需要拆分
- 复杂问题（5个）：探索式，多时间段对比

### 成功标准

| 指标 | 目标 | 测量方法 |
|------|------|----------|
| Token数 | Question Boost < 400, Understanding < 600, Task Planner < 900, Dimension Hierarchy < 500 | 统计system message |
| 响应时间 | Question Boost < 2s, Understanding 2-3s, Task Planner 5-10s, Dimension Hierarchy < 3s | P95延迟 |
| 准确率 | > 95% | 关键字段匹配率 |
| 用户满意度 | > 90% | 人工评估（可选） |

### 重要提醒

**不在prompt中添加示例**：
- 示例会大幅增加token消耗（每个示例~100-200 tokens）
- 如果准确率不达标，优先优化Field description和决策规则
- 只有在其他方法都失败时，才考虑添加1个精准示例

## Implementation Plan

### Phase 1: Base模板重构
1. 修改StructuredPrompt基类（4段式）
2. 更新get_system_message()方法
3. 测试基类功能

### Phase 2: Question Boost优化
1. 实现新的QuestionBoostPrompt
2. 统计token数（目标 < 500）
3. 测试准确率（目标 > 95%）

### Phase 3: Understanding优化
1. 实现新的UnderstandingPrompt
2. 统计token数（目标 < 800）
3. 测试准确率（目标 > 95%）

### Phase 4: Task Planner优化
1. 实现新的TaskPlannerPrompt
2. 统计token数（目标 < 1200）
3. 测试准确率（目标 > 95%）

### Phase 5: 集成测试
1. 端到端测试20个问题
2. 测量响应时间和准确率
3. 如果不达标，执行降级策略

### Phase 6: 部署和监控
1. 部署优化版本
2. 监控性能指标
3. 收集用户反馈
