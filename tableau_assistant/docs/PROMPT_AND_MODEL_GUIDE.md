# Prompt模板和数据模型编写指南

## 目录
1. [前沿研究综述](#前沿研究综述)
2. [理论基础：LLM的本质](#理论基础llm的本质)
3. [LLM工作原理](#llm工作原理)
4. [Prompt模板是什么？](#prompt模板是什么)
5. [数据模型是什么？](#数据模型是什么)
6. [为什么需要它们？](#为什么需要它们)
7. [Prompt与数据模型的职责边界](#prompt与数据模型的职责边界)
8. [如何编写Prompt模板](#如何编写prompt模板)
9. [如何编写数据模型](#如何编写数据模型)
10. [底层优化原则](#底层优化原则)
11. [最佳实践](#最佳实践)

---

## 前沿研究综述

本章节总结了 Google、Anthropic、OpenAI、Meta 等机构在 Prompt 优化和结构化输出方面的前沿研究，这些研究直接指导我们的设计决策。

### Google 的研究发现

| 研究 | 核心发现 | 对我们的启示 |
|------|---------|-------------|
| **Chain-of-Thought (CoT)** | "Let's think step by step" 能显著提升推理能力 | 结构化思考路径比简单指令更有效 |
| **Self-Consistency** | 多次采样 + 投票 > 单次输出 | 关键决策可以让 LLM 从多角度验证 |
| **Least-to-Most Prompting** | 先解决简单子问题，再解决复杂问题 | 字段填写顺序很重要，先填简单字段 |
| **Tree of Thoughts (ToT)** | 探索多个推理路径，可回溯错误 | 决策规则应该是树状的，而非线性的 |

### Anthropic 的研究发现

| 研究 | 核心发现 | 对我们的启示 |
|------|---------|-------------|
| **XML 标签结构** | LLM 对 XML 结构理解更准确（训练数据中大量 HTML/XML） | Schema 字段描述使用 XML 标签 |
| **Constitutional AI** | 规则应该是原则性的，而非枚举性的 | 决策规则 = 原则 + 示例 |
| **Attention Sink** | LLM 对开头和结尾的 token 注意力更高 | 关键信息放在开头或结尾 |
| **Sparse Attention** | 长上下文中只有少数 token 获得高权重 | 关键词密度比总长度更重要 |

### OpenAI 的研究发现

| 研究 | 核心发现 | 对我们的启示 |
|------|---------|-------------|
| **Structured Outputs** | JSON Schema 约束可实现 100% 符合率 | Schema 越严格，输出越可靠 |
| **Function Calling** | 结构化输出比自由文本更可靠 | 优先使用结构化输出 |
| **System Prompt 最佳实践** | 角色要具体，约束用否定句，示例覆盖边界 | Prompt 设计的具体指导 |

### Meta (LLaMA) 的研究发现

| 研究 | 核心发现 | 对我们的启示 |
|------|---------|-------------|
| **Instruction Tuning 本质** | 不是教新知识，而是激活已有知识的正确输出格式 | Prompt 的作用是"格式化"而非"教学" |
| **RLHF 的影响** | 模糊指令导致保守输出 | 指令要具体、明确 |

### 学术界的最新发现

| 研究 | 核心发现 | 对我们的启示 |
|------|---------|-------------|
| **Prompt Sensitivity** | 微小变化（标点、空格）可能导致巨大输出差异 | Prompt 格式要标准化 |
| **Lost in the Middle** | LLM 对长上下文的中间部分注意力最低 | 关键信息放在开头或结尾 |
| **Reversal Curse** | 学会 "A is B" 不代表学会 "B is A" | 双向关系需要显式说明 |
| **Calibration** | LLM 的置信度不等于准确度 | 需要外部验证机制（Pydantic Validator） |

### 认知科学的启发

| 理论 | 核心发现 | 对我们的启示 |
|------|---------|-------------|
| **工作记忆限制** | 人类工作记忆约 7±2 个项目 | 一次不要给太多选项（枚举值 ≤ 7） |
| **Chunking（分块）** | 将信息组织成有意义的块减少认知负担 | 相关字段应该分组 |
| **Dual Process Theory** | System 1（快速模式匹配）vs System 2（慢速逻辑推理） | LLM 更像 System 1，利用模式匹配 |

### 研究启示总结

基于以上研究，我们得出以下设计原则：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           设计原则金字塔                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Level 4: 验证层                                                             │
│  ├─ Pydantic Validator（代码级 100% 可靠）                                   │
│  └─ 外部验证机制（LLM 置信度 ≠ 准确度）                                      │
│                                                                              │
│  Level 3: 结构层                                                             │
│  ├─ XML 标签（显式边界，Attention 集中）                                     │
│  ├─ 决策树（树状决策，非线性矩阵）                                           │
│  └─ 填写顺序（先简单后复杂，Least-to-Most）                                  │
│                                                                              │
│  Level 2: 内容层                                                             │
│  ├─ 原则 + 示例（Constitutional AI）                                        │
│  ├─ 关键信息位置（开头/结尾，Lost in the Middle）                            │
│  └─ 关键词密度（Sparse Attention）                                          │
│                                                                              │
│  Level 1: 格式层                                                             │
│  ├─ 标准化格式（Prompt Sensitivity）                                        │
│  ├─ 选项数量 ≤ 7（工作记忆限制）                                            │
│  └─ 相关字段分组（Chunking）                                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 理论基础：LLM的本质

在深入具体的编写方法之前，我们需要从底层理解LLM的工作原理。这些理论基础将指导我们做出更好的设计决策。

### 1. LLM是条件概率分布器

LLM的核心是一个**条件概率模型**：

```
P(next_token | context)
```

**关键洞察**：LLM不是在"理解"，而是在**激活相关的模式**。

### 2. 知识的存储方式

LLM的"知识"不是存储在某个位置，而是分布在：
- **词嵌入空间**：语义相似性
- **注意力权重**：关联模式
- **FFN层**：知识记忆

**这意味着**：
- Prompt的作用是**激活正确的知识子空间**
- Schema的作用是**约束输出的概率分布**

### 3. 语言是压缩的思维

```
人类思维（高维、连续） 
    ↓ 压缩
语言表达（低维、离散）
    ↓ 解压
LLM理解（重建高维表征）
```

**问题理解的本质**：
```
"各省份的销售额"
    ↓
这不是一个字符串，而是一个压缩的意图：
- 隐含主语：我想知道
- 隐含动作：查询/分析
- 隐含范围：所有数据
- 显式维度：省份
- 显式指标：销售额
- 隐含聚合：求和（默认）
```

### 4. 语言的组合性（Compositionality）

```
语言的意义 = 部分的意义 + 组合规则

"各省份的销售额" = 
  "各" (分组操作) + 
  "省份" (分组对象) + 
  "的" (所属关系) + 
  "销售额" (度量对象)
```

**关键洞察**：我们需要教LLM的不是"模式"，而是**组合规则**。

### 5. Prompt和Schema的本质作用

| 组件 | 传统理解 | 底层本质 |
|------|---------|---------|
| Prompt | 给LLM的指令 | 导航到正确的知识子空间 |
| Schema | 定义输出格式 | 塑造输出的概率分布 |

```
LLM的知识空间是一个高维流形
Prompt = 导航坐标
Schema = 着陆区域
```

---

## LLM工作原理

理解LLM的工作原理对于编写有效的Prompt和数据模型至关重要。

### LLM的本质

LLM是一个**条件概率模型**，根据前面所有的token来预测下一个token：
```
P(next_token | previous_tokens)
```

### 注意力机制

当LLM生成输出时，会对所有输入token计算**注意力权重**：

```
输入tokens: [System Prompt] + [Schema] + [User Input] + [已生成的tokens]
                  ↓              ↓            ↓              ↓
            注意力权重w1    注意力权重w2  注意力权重w3    注意力权重w4
                  └──────────────┴────────────┴──────────────┘
                                        ↓
                               加权求和 → 预测下一个token
```

### 结构化输出的生成过程

当生成JSON输出时，LLM逐token生成：

```
Step 1: 生成 "{"
Step 2: 生成 "\"mentioned_dimensions\""  ← LLM知道要填这个字段
Step 3: 生成 ":"
Step 4: 生成 "["
Step 5: 生成 "\"省份\""  ← LLM决定填什么值（关键步骤！）
Step 6: 生成 "]"
...
```

### 关键洞察：Schema Description的高注意力

当LLM生成某个字段的值时，该字段的Schema description会获得**很高的注意力权重**：

```
生成 mentioned_dimensions 的值时:
┌─────────────────────────────────────────────────────────────────┐
│ System Prompt: "...维度是分类字段..."                            │  ← 注意力 w1 (中)
│ Schema: "mentioned_dimensions: 所有维度实体..."                  │  ← 注意力 w2 (高!)
│ User Input: "各省份的销售额"                                     │  ← 注意力 w3 (高!)
│ 已生成: {"mentioned_dimensions": [                               │  ← 注意力 w4
└─────────────────────────────────────────────────────────────────┘
```

**因此**：
- **Schema description** 是影响字段值生成的最直接因素
- **Prompt** 提供全局上下文，但对特定字段的影响较间接

### 设计原则

基于LLM的工作原理，我们得出以下设计原则：

| 信息类型 | 放在Prompt | 放在Schema | 原因 |
|---------|-----------|-----------|------|
| 领域概念定义 | ✅ | ❌ | 全局知识，所有字段都需要 |
| 推理的逻辑顺序 | ✅ | ❌ | 帮助LLM组织思路 |
| 字段的精确语义 | ❌ | ✅ | 生成该字段时注意力最高 |
| 字段的填写规则 | ❌ | ✅ | 生成该字段时注意力最高 |
| 具体示例 | ❌ | ✅ | 生成该字段时最需要参考 |

**Prompt和Schema应该互补而不是重复**

---

## Prompt模板是什么？

### 定义

**Prompt模板** 是给LLM的指令模板，定义了：
- LLM扮演什么角色（Role）
- LLM要完成什么任务（Task）
- LLM需要什么领域知识（Domain Knowledge）
- LLM必须遵守什么约束（Constraints）

### 作用

```
用户输入 → Prompt模板 → LLM → 结构化输出（Pydantic模型）
```

**Prompt模板的作用**：
1. **指导LLM行为** - 告诉LLM如何思考和回答
2. **保证输出质量** - 通过约束确保输出符合要求
3. **提高一致性** - 相同输入得到相似输出
4. **便于维护** - 集中管理Prompt，易于调试和优化

### 示例对比

**❌ 不好的做法（硬编码）**：
```python
# Prompt直接写在代码里，难以维护
prompt = f"""你是一个字段映射专家。
请将业务术语'{term}'映射到技术字段。
候选字段：{candidates}
返回JSON格式..."""

response = llm.invoke(prompt)
```

**✅ 好的做法（使用模板）**：
```python
# 使用结构化模板
class FieldMappingPrompt(VizQLPrompt):
    def get_role(self) -> str:
        return "Field mapping expert..."
    
    def get_task(self) -> str:
        return "Map business terms to technical fields..."
    
    # ...

# 使用时
prompt = FIELD_MAPPING_PROMPT
result = await agent.execute(state, runtime, prompt)
```

---

## 数据模型是什么？

### 定义

**数据模型** 是使用Pydantic定义的数据结构，描述了：
- 数据有哪些字段
- 每个字段的类型
- 每个字段的含义和用法
- 字段的验证规则

### 作用

```
LLM输出（JSON） → Pydantic验证 → 数据模型实例 → 类型安全的代码
```

**数据模型的作用**：
1. **类型安全** - 编译时检查类型错误
2. **数据验证** - 自动验证数据格式和约束
3. **文档化** - 字段描述即文档
4. **IDE支持** - 自动补全和类型提示
5. **JSON Schema** - 自动生成Schema供LLM使用

### 示例对比

**❌ 不好的做法（普通字典）**：
```python
# 使用字典，没有类型检查
result = {
    "matched_field": "Sales Amount",
    "confidence": 0.95,
    "reasoning": "..."
}

# 容易出错
print(result["confidance"])  # 拼写错误，运行时才发现
print(result["confidence"] + "test")  # 类型错误，运行时才发现
```

**✅ 好的做法（Pydantic模型）**：
```python
# 使用Pydantic模型
class FieldMappingResult(BaseModel):
    matched_field: Optional[str]
    confidence: float
    reasoning: str

result = FieldMappingResult(
    matched_field="Sales Amount",
    confidence=0.95,
    reasoning="..."
)

# IDE会提示错误
print(result.confidance)  # IDE立即提示拼写错误
print(result.confidence + "test")  # IDE立即提示类型错误
```

---

## 为什么需要它们？

### 问题场景

假设我们要实现字段映射功能：

**没有模板和模型的问题**：
```python
# 问题1：Prompt散落在代码各处
def map_field_v1(term):
    prompt = f"Map {term} to field..."  # Prompt A
    
def map_field_v2(term):
    prompt = f"Please map {term}..."    # Prompt B (不一致！)

# 问题2：输出格式不统一
result1 = {"field": "Sales"}           # 格式A
result2 = {"matched": "Sales"}         # 格式B (不一致！)

# 问题3：没有类型检查
result["confidence"] = "high"          # 应该是数字，但没人检查
```

**使用模板和模型的好处**：
```python
# 好处1：Prompt集中管理
class FieldMappingPrompt(VizQLPrompt):
    # 所有Prompt逻辑在一个地方
    pass

# 好处2：输出格式统一
class FieldMappingResult(BaseModel):
    matched_field: str
    confidence: float  # 必须是数字，自动验证

# 好处3：类型安全
result = FieldMappingResult(
    matched_field="Sales",
    confidence="high"  # 错误！Pydantic会立即报错
)
```

---

## Prompt与数据模型的职责边界

### 核心原则

> **Prompt教LLM如何思考，Schema告诉LLM输出什么**

### 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: System Context (系统上下文)                        │
│  ├─ Role: 你是谁                                            │
│  ├─ Capabilities: 你能做什么                                 │
│  └─ Global Constraints: 全局约束                             │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Task Reasoning (任务推理) - Prompt模板             │
│  ├─ Task: 具体要做什么                                       │
│  ├─ Domain Knowledge: 领域概念 (不涉及具体字段名)             │
│  ├─ Reasoning Steps: 思考步骤 (HOW to think)                 │
│  ├─ Decision Rules: 决策规则                                 │
│  └─ Fill Order: 填充顺序指导                                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Output Schema (输出模式) - 数据模型                 │
│  ├─ Class Docstring:                                         │
│  │   ├─ EXAMPLES: 完整输入输出示例                           │
│  │   └─ ANTI-PATTERNS: 常见错误                              │
│  ├─ Field Definitions:                                       │
│  │   ├─ WHAT: 字段含义                                       │
│  │   ├─ WHEN: 何时填写 (条件)                                │
│  │   ├─ HOW: 如何填写 (格式)                                 │
│  │   ├─ DEPENDENCY: 依赖关系                                 │
│  │   └─ VALUES: 取值范围和示例                               │
│  └─ Validators: 自验证逻辑                                   │
└─────────────────────────────────────────────────────────────┘
```

### 职责划分表

| 内容类型 | 放在Prompt | 放在Schema | 说明 |
|---------|-----------|-----------|------|
| 分析方法 | ✅ | ❌ | 如何分析问题 |
| 推理步骤 | ✅ | ❌ | 思考的过程 |
| 决策规则 | ✅ | ❌ | 如何做判断 |
| 领域概念 | ✅ | ❌ | 什么是dimension/measure |
| 字段含义 | ❌ | ✅ | 每个字段代表什么 |
| 取值范围 | ❌ | ✅ | 字段可以填什么值 |
| 填写规则 | ❌ | ✅ | 什么时候填、怎么填 |
| 依赖关系 | ❌ | ✅ | 字段之间的依赖 |

### 黄金法则

> 如果一段描述提到了具体字段名，它应该在 Schema 里；
> 如果一段描述是通用的分析方法，它应该在 Prompt 里。

### 检查清单

**Prompt检查**：
- [ ] 是否提到了具体字段名？→ 如果是，移到Schema
- [ ] 是否在教LLM如何分析？→ 应该保留
- [ ] 是否有重复的字段说明？→ 删除，只保留Schema中的

**Schema检查**：
- [ ] 是否在教LLM如何分析？→ 如果是，移到Prompt
- [ ] 字段描述是否包含WHAT/WHEN/HOW？→ 应该包含
- [ ] 是否有完整的输入输出示例？→ 应该在docstring中提供

### 示例对比

**❌ 错误：Prompt中包含字段填写规则**
```python
def get_specific_domain_knowledge(self) -> str:
    return """Step 2: Determine SQL role for EACH dimension
    - If dimension is counted → set dimension_aggregations[dim] = "COUNTD"
    - If dimension is grouped → don't include in dimension_aggregations"""
```

**✅ 正确：Prompt只教如何思考**
```python
def get_specific_domain_knowledge(self) -> str:
    return """Step 2: Determine SQL role for EACH dimension
    - Is this dimension being counted/aggregated?
    - Or is it being used for grouping (GROUP BY)?"""
```

**✅ 正确：Schema中说明字段填写规则**
```python
dimension_aggregations: Optional[dict[str, str]] = Field(
    description="""Aggregation functions for dimensions.

WHAT: Maps dimension names to their SQL aggregation functions
WHEN: Only include dimensions that need aggregation (COUNT/COUNTD/MAX/MIN)
HOW: Key is dimension name, value is aggregation function

VALUES: 'COUNTD', 'MAX', 'MIN'

EXAMPLES:
- "多少产品" → {"产品": "COUNTD"}
- "最新日期" → {"日期": "MAX"}
- "按省份分析" → null (省份 is for GROUP BY, not aggregated)"""
)
```

---

## 如何编写Prompt模板

### 模板结构

项目使用**4段式结构**（继承自`VizQLPrompt`）：

```python
class YourPrompt(VizQLPrompt):
    def get_role(self) -> str:
        """定义LLM的角色"""
        
    def get_task(self) -> str:
        """定义LLM的任务"""
        
    def get_specific_domain_knowledge(self) -> str:
        """提供领域知识和思考步骤"""
        
    def get_constraints(self) -> str:
        """定义约束条件"""
        
    def get_user_template(self) -> str:
        """定义用户输入模板"""
        
    def get_output_model(self) -> Type[BaseModel]:
        """指定输出模型"""
```

### 编写规则

#### 1. **语言规则**

**✅ 正确**：全英文
```python
def get_role(self) -> str:
    return """Field mapping expert who maps business terms to technical fields.

Expertise:
- Semantic understanding
- Context-aware disambiguation"""
```

**❌ 错误**：中英文混杂
```python
def get_role(self) -> str:
    return """字段映射专家 who maps business terms to technical fields.

Expertise:
- 语义理解
- Context-aware disambiguation"""
```

**原因**：
- LLM对英文理解更准确
- 避免编码问题
- 保持专业性和一致性

#### 2. **Role部分**

**作用**：定义LLM的身份和专长

**编写要点**：
- 简洁明确（2-3句话）
- 突出专业领域
- 列出核心能力

**示例**：
```python
def get_role(self) -> str:
    return """Field mapping expert who maps business terms to technical fields.

Expertise:
- Semantic understanding of business terminology
- Field metadata analysis (role, type, category)
- Context-aware disambiguation
- Synonym and multi-language handling"""
```

#### 3. **Task部分**

**作用**：定义LLM要完成的任务

**编写要点**：
- 一句话概括任务
- 列出处理流程（Process）
- 使用箭头（→）表示步骤

**示例**：
```python
def get_task(self) -> str:
    return """Map business terms to technical fields using RAG candidates.

Process: Analyze term → Review candidates → Match semantics → Score confidence"""
```

#### 4. **Domain Knowledge部分**

**作用**：提供领域知识和思考步骤

**编写要点**：
- 使用"Think step by step"引导
- 每个步骤清晰编号
- 提供决策表格（可选）
- 包含示例（可选）

**示例**：
```python
def get_specific_domain_knowledge(self) -> str:
    return """Available data: {question_context}, {candidates}

**Think step by step:**

Step 1: Analyze business term
- What does this term mean?
- Is it dimension or measure?
- What category does it belong to?

Step 2: Review candidates
- Examine metadata: role, type, category
- Note similarity scores
- Identify semantic matches

Step 3: Match based on semantics
| Criterion | Weight | Consideration |
|-----------|--------|---------------|
| Semantic meaning | High | Does meaning match? |
| Role match | High | Dimension vs measure |
| Category match | Medium | Category alignment |

Step 4: Score confidence
- 0.9-1.0: Perfect match
- 0.7-0.9: Good match
- 0.5-0.7: Acceptable match"""
```

#### 5. **Constraints部分**

**作用**：定义必须遵守的约束

**编写要点**：
- 分为MUST和MUST NOT
- 简洁列举
- 避免冗长解释

**示例**：
```python
def get_constraints(self) -> str:
    return """MUST: select from candidates, consider role, use context, provide reasoning
MUST NOT: invent fields, ignore role mismatch, give high confidence without evidence"""
```

#### 6. **User Template部分**

**作用**：定义用户输入的格式

**编写要点**：
- 使用占位符（{variable}）
- 格式清晰
- 包含所有必要信息

**示例**：
```python
def get_user_template(self) -> str:
    return """Map these business terms:

Terms: {business_terms}
Context: {question_context}

Candidates:
{candidates}"""
```

---

## 如何编写数据模型

### 模型结构

使用Pydantic BaseModel：

```python
from pydantic import BaseModel, Field, ConfigDict

class YourModel(BaseModel):
    """模型文档字符串"""
    model_config = ConfigDict(extra="forbid")
    
    field_name: FieldType = Field(
        description="""字段描述

Usage:
- 使用场景说明

Values: 值的范围或示例"""
    )
```

### 编写规则

#### 1. **模型文档**

**作用**：说明模型的用途

**示例**：
```python
class FieldMappingResult(BaseModel):
    """
    Field mapping result for a single business term
    
    Contains the matched field, confidence score, reasoning, and alternatives.
    """
```

#### 2. **配置设置**

**必须包含**：
```python
model_config = ConfigDict(extra="forbid")
```

**作用**：禁止额外字段，确保数据严格符合定义

#### 3. **字段定义**

**格式**：
```python
field_name: FieldType = Field(
    description="""字段描述

Usage:
- 使用场景

Values: 值范围"""
)
```

**字段类型**：
- 基础类型：`str`, `int`, `float`, `bool`
- 可选类型：`Optional[str]`
- 列表类型：`List[str]`
- 字典类型：`Dict[str, Any]`
- 枚举类型：`Literal["a", "b"]` 或自定义Enum
- 嵌套模型：其他Pydantic模型

**字段约束**：
```python
# 必填字段
field1: str = Field(description="...")

# 可选字段（默认None）
field2: Optional[str] = Field(default=None, description="...")

# 默认值
field3: int = Field(default=0, description="...")

# 列表最小长度
field4: List[str] = Field(min_length=1, description="...")

# 数值范围
field5: int = Field(ge=0, le=100, description="...")

# 字符串模式
field6: str = Field(pattern=r"^q\d+$", description="...")
```

#### 4. **字段描述格式（XML 增强版）**

##### 为什么使用 XML 格式？

**理论基础**：Google 和 Anthropic 的研究表明，LLM 对 XML 结构的理解更准确。原因如下：

1. **训练数据优势**：LLM 训练数据包含大量 HTML/XML（网页、配置文件、API 响应），已内化 XML 语义结构
2. **显式边界标记**：`<tag>` 和 `</tag>` 是明确的开始/结束标记，而 Markdown 的 `WHAT:` 只有开始标记
3. **Attention 机制友好**：XML 标签让 Attention 权重更集中，减少边界推断的认知负担
4. **层级关系清晰**：XML 天然支持嵌套，可表达复杂的依赖关系

```
Attention 机制对比：

XML 结构:
<what>字段含义</what>
     ↑         ↑
  开始标记   结束标记  → 边界清晰，Attention 集中在标签内容

Markdown 结构:
WHAT: 字段含义
WHEN: 何时填写
  ↑
只有开始标记，结束边界模糊 → LLM 需要推断边界，Attention 分散
```

##### XML 格式规范

**标准 XML 标签**：

| 标签 | 含义 | 必填 | 说明 |
|------|------|------|------|
| `<what>` | 字段含义 | ✅ | 字段代表什么 |
| `<when>` | 填写条件 | ✅ | 何时填写（条件） |
| `<how>` | 填写方式 | ✅ | 如何填写（格式） |
| `<dependency>` | 依赖关系 | 条件字段必填 | 依赖哪些其他字段 |
| `<values>` | 取值范围 | 推荐 | 可选值列表 |
| `<examples>` | 示例 | 推荐 | 输入→输出示例 |
| `<anti_patterns>` | 常见错误 | 推荐 | 避免的错误模式 |
| `<decision_rule>` | 决策规则 | 复杂条件推荐 | 决策逻辑（伪代码或表格） |

**简单字段示例（必填字段）**：
```python
confidence: float = Field(
    description="""Mapping confidence score.

<what>Confidence level of the mapping result</what>
<when>Always required</when>
<how>Float between 0 and 1</how>

<values>
- 0.9-1.0: Perfect match
- 0.7-0.9: Good match
- 0.5-0.7: Acceptable match
- 0.0-0.5: Poor match
</values>"""
)
```

**条件字段示例（有依赖关系）**：
```python
computation_scope: Optional[ComputationScope] = Field(
    default=None,
    description="""Computation scope (semantic intent).

<what>Whether to calculate per-group or across all data</what>

<when>ONLY when query has MULTIPLE dimensions (len(dimensions) > 1)</when>

<how>Detect from keywords in question</how>

<dependency>
- field: dimensions
- condition: length > 1
- reason: Single dimension doesn't need scope specification
</dependency>

<values>
- per_group: "各XX", "每个XX" → Calculate independently per group
- across_all: "总", "全部" → Calculate across all data
</values>

<decision_rule>
IF dimensions.length == 1 THEN null (don't fill)
IF "各XX" or "每个XX" in question THEN per_group
IF "总" or "全部" or "整体" in question THEN across_all
DEFAULT: per_group
</decision_rule>

<examples>
- "各省份按月累计销售额" → per_group (each province cumulates independently)
- "按月累计总销售额" → across_all (all data cumulates together)
- "按月累计销售额" (single dim) → null (don't fill)
</examples>

<anti_patterns>
❌ Setting computation_scope for single dimension query
❌ Defaulting to across_all without explicit "总" keyword
</anti_patterns>"""
)
```

**复杂依赖字段示例**：
```python
target_granularity: Optional[List[str]] = Field(
    default=None,
    description="""Target aggregation granularity (business terms).

<what>Dimensions to aggregate at (coarser than view granularity)</what>

<when>ONLY when type=aggregation_at_level</when>

<how>List dimension names using business terms (NOT technical field names)</how>

<dependency>
- field: type
- condition: type == "aggregation_at_level"
- reason: Only LOD calculations need target granularity
</dependency>

<values>
- List of dimension names (business terms)
- Empty list [] means global aggregation (no dimensions)
</values>

<examples>
- "各产品销售额，及其品类总销售额" → ["品类"]
- "各省份销售额，及全国总销售额" → [] (global)
- "各客户销售额，及该客户所在省份的总销售额" → ["省份"]
</examples>

<anti_patterns>
❌ Using technical field names: ["Category"] instead of ["品类"]
❌ Setting target_granularity when type != aggregation_at_level
❌ Confusing with percentage type (use percentage for "占比" scenarios)
</anti_patterns>"""
)
```

##### Class Docstring 的 XML 格式

**模型级别的示例和反模式也应使用 XML 格式**：

```python
class AnalysisSpec(BaseModel):
    """
    Analysis specification - pure semantic, no VizQL concepts.
    
    <what>Derived calculation that user wants to perform</what>
    
    <examples>
    Example 1 - Simple cumulative (single dimension):
    Input: "按月累计销售额"
    Output: {
        "type": "cumulative",
        "target_measure": "销售额",
        "aggregation": "sum"
    }
    
    Example 2 - Multi-dimension cumulative (per_group):
    Input: "各省份按月累计销售额"
    Output: {
        "type": "cumulative",
        "target_measure": "销售额",
        "aggregation": "sum",
        "computation_scope": "per_group"
    }
    </examples>
    
    <anti_patterns>
    ❌ ERROR 1: Setting computation_scope for single dimension
    Input: "按月累计销售额" (only one dimension: 月)
    Wrong: {"computation_scope": "per_group"}
    Right: {} (omit computation_scope)
    
    ❌ ERROR 2: Using technical field names
    Wrong: {"target_measure": "Sales"}
    Right: {"target_measure": "销售额"}
    </anti_patterns>
    """
```

##### 字段依赖关系：决策树 vs 矩阵

**为什么用决策树替代矩阵？**

基于 Google 的 Tree of Thoughts 研究和 Least-to-Most Prompting 研究：
- **矩阵是二维的，但决策是树状的**：矩阵只能表达 "A 依赖 B"，无法表达 "如果 A=x 则填 B，如果 A=y 则填 C"
- **矩阵是静态的，但填写是动态的**：LLM 逐字段生成，需要明确的填写顺序
- **矩阵缺少决策路径**：只说了"什么时候填"，没说"怎么决定填什么值"

**决策树格式**（推荐）：

```python
class AnalysisSpec(BaseModel):
    """
    Analysis specification - pure semantic, no VizQL concepts.
    
    <decision_tree>
    START
      │
      ├─► type = ? (ALWAYS fill first, determines conditional fields)
      │   │
      │   ├─► cumulative/moving/ranking/percentage/period_compare
      │   │   │
      │   │   └─► dimensions.length > 1 ?
      │   │       ├─ YES → fill computation_scope (default: per_group)
      │   │       └─ NO  → skip computation_scope (null)
      │   │
      │   ├─► ranking
      │   │   └─► fill order (default: desc)
      │   │
      │   ├─► moving
      │   │   └─► fill window_size (required)
      │   │
      │   ├─► period_compare
      │   │   └─► fill compare_type (required)
      │   │
      │   └─► aggregation_at_level
      │       ├─► fill requires_external_dimension
      │       └─► fill target_granularity
      │
      ├─► target_measure = ? (ALWAYS fill)
      │
      ├─► aggregation = ? (ALWAYS fill, default: sum)
      │
      └─► along_dimension = ? (ONLY if user explicit)
      
    END
    </decision_tree>
    """
```

**填写顺序指令**（基于 Least-to-Most Prompting）：

```python
class AnalysisSpec(BaseModel):
    """
    ...
    
    <fill_order>
    ┌────┬─────────────────────────┬─────────────────────────────────────┐
    │ #  │ Field                   │ Condition                           │
    ├────┼─────────────────────────┼─────────────────────────────────────┤
    │ 1  │ type                    │ ALWAYS (determines other fields)    │
    │ 2  │ target_measure          │ ALWAYS                              │
    │ 3  │ aggregation             │ ALWAYS (default: sum)               │
    │ 4  │ order                   │ IF type = ranking                   │
    │ 5  │ window_size             │ IF type = moving                    │
    │ 6  │ compare_type            │ IF type = period_compare            │
    │ 7  │ requires_external_dim   │ IF type = aggregation_at_level      │
    │ 8  │ target_granularity      │ IF type = aggregation_at_level      │
    │ 9  │ computation_scope       │ IF dimensions.length > 1            │
    │ 10 │ along_dimension         │ IF user explicitly specifies        │
    └────┴─────────────────────────┴─────────────────────────────────────┘
    </fill_order>
    
    IMPORTANT: Fill fields in order. Earlier fields determine later fields.
    """
```

**条件字段分组**（基于认知科学的 Chunking 理论）：

```python
class AnalysisSpec(BaseModel):
    """
    ...
    
    <conditional_groups>
    Group 1: ALWAYS fill (required fields)
    ├─ type
    ├─ target_measure
    └─ aggregation (default: sum)
    
    Group 2: type-dependent fields (fill based on type value)
    ├─ [type=ranking]           → order
    ├─ [type=moving]            → window_size
    ├─ [type=period_compare]    → compare_type
    └─ [type=aggregation_at_level] → requires_external_dimension, target_granularity
    
    Group 3: context-dependent fields (fill based on query context)
    ├─ [dimensions.length > 1]  → computation_scope
    └─ [user explicit]          → along_dimension
    </conditional_groups>
    """
```

**旧格式（矩阵）vs 新格式（决策树）对比**：

| 方面 | 依赖矩阵 | 决策树 + 填写顺序 |
|------|---------|------------------|
| 决策路径 | 隐式 | 显式 |
| 填写顺序 | 无 | 明确 |
| 条件分支 | 无法表达 | 天然支持 |
| 认知负担 | 高（需推断） | 低（直接跟随） |
| 符合 LLM 生成过程 | 否 | 是 |

##### 旧格式（Markdown）vs 新格式（XML）对比

| 方面 | Markdown 格式 | XML 格式 |
|------|--------------|----------|
| 边界清晰度 | 隐式（需推断） | 显式（标签标记） |
| Attention 分布 | 分散 | 集中 |
| 层级表达 | 困难 | 天然支持 |
| 信息检索 | 需要模式匹配 | 直接定位标签 |
| LLM 理解准确度 | 中等 | 高 |

**迁移建议**：
- 新字段：使用 XML 格式
- 现有字段：逐步迁移到 XML 格式
- 简单字段：可保持 Markdown 格式（成本收益比低）
- 条件字段：强烈建议使用 XML 格式（依赖关系复杂）
)
```

#### 5. **可选字段处理**

**规则**：
- 使用`Optional[Type]`表示可选
- 设置`default=None`
- 在描述中说明何时为null

**示例**：
```python
matched_field: Optional[str] = Field(
    default=None,
    description="""Matched technical field name.

Usage:
- Include if match found
- null if no suitable match

Values: Field name string or null"""
)
```

#### 6. **列表字段处理**

**规则**：
- 使用`List[Type]`
- 考虑是否需要`min_length`
- 使用`default_factory=list`而不是`default=[]`

**示例**：
```python
# 可以为空的列表
alternatives: List[Dict[str, Any]] = Field(
    default_factory=list,
    description="""Alternative matches.

Usage:
- Include when confidence < 0.9
- Empty list if no alternatives

Values: List of alternative dictionaries"""
)

# 至少一个元素的列表
business_terms: List[str] = Field(
    min_length=1,
    description="""Business terms to map.

Usage:
- Include all terms needing mapping

Values: List of term strings"""
)
```

---

## 底层优化原则

基于LLM的工作原理和语言的本质，我们总结出以下底层优化原则。

### 原则1：最小激活原则

**理论基础**：Prompt中的每个词都在竞争Attention权重。冗余词汇会稀释关键信息的注意力。

```
❌ 低效 Prompt：
"Dimension is a categorical field that is typically used for 
grouping data in SQL queries, such as GROUP BY clauses..."

问题：
- 太多冗余词汇稀释 attention
- 关键信息被噪声淹没

✅ 高效 Prompt：
"Dimension = GROUP BY field
 Measure = aggregated numeric field"

优势：
- 关键词密度高
- Attention 集中在核心概念
```

**实践指南**：
- 用最少的token激活最精确的知识
- 删除解释性文字，保留关键词
- 使用符号（=, →, |）代替连接词

### 原则2：正交分解原则

**理论基础**：Schema的字段应该是正交的（独立的决策）。字段之间的依赖关系增加了LLM的认知负担。

```python
# ❌ 有依赖的设计
mentioned_dimensions: List[str]           # 先填这个
dimension_aggregations: Dict[str, str]    # 再填这个，key必须在上面

# 问题：LLM需要两步决策，且要保持一致性

# ✅ 正交的设计
class Entity(BaseModel):
    name: str
    role: Literal["group_by", "aggregate", "filter"]
    aggregation: Optional[str] = None

entities: List[Entity]  # 每个实体独立决策
```

**实践指南**：
- 每个字段应该可以独立决策
- 避免字段之间的引用依赖
- 考虑将相关信息合并为嵌套结构

### 原则3：语义一致性原则

**理论基础**：Prompt的概念和Schema的字段名应该语义一致。不一致会增加LLM的映射成本。

```python
# ❌ 不一致
# Prompt 说
"Dimension: Categorical field for grouping"
# Schema 用
mentioned_dimensions  # "mentioned" 这个词在 Prompt 中没出现

# ✅ 一致
# Prompt 说
"GROUP_BY: 分组字段"
# Schema 用
group_by_fields: List[str]
```

**实践指南**：
- Prompt和Schema使用相同的术语
- 字段名应该直接反映其语义
- 避免引入Prompt中未定义的概念

### 原则4：渐进式约束原则

**理论基础**：从宽松到严格，逐步收紧约束。一开始就要求完美的结构化输出会增加出错概率。

```
阶段1：意图理解（低约束）
- 让LLM先理解问题的整体意图
- 不强制结构化

阶段2：实体识别（中约束）
- 识别所有相关实体
- 简单分类

阶段3：结构化输出（高约束）
- 填充完整的结构化字段
- 严格验证
```

**实践指南**：
- 复杂任务考虑分阶段处理
- 先理解后结构化
- 验证逻辑放在最后

### 原则5：In-Context Learning的本质

**理论基础**：ICL不是"学习"，是"模式匹配"。示例的作用不是"教"，而是"唤醒"。

```
传统理解：
Prompt中的示例 → LLM学习新规则 → 应用规则

实际机制：
Prompt中的示例 → 激活相似的预训练模式 → 模式迁移
```

**实践指南**：
- 一个精准示例 > 十个平庸示例
- 示例应该覆盖边界情况
- 不需要详细解释（LLM已经"知道"，只需要"提醒"）

### 原则6：信息瓶颈理论

**理论基础**：最优表示 = 最大化任务相关信息 + 最小化无关信息

```
对于问题理解任务：
- 任务相关：实体、角色、关系、意图
- 任务无关：语气、修辞、冗余表达
```

**实践指南**：
- Prompt应该帮助LLM过滤无关信息
- Schema字段应该只包含任务必需的信息
- 避免收集"可能有用"的信息

### 原则7：最小描述长度（MDL）

**理论基础**：最优模型 = 最短的描述 + 最小的误差

```
对于Schema设计：
- 字段数量应该最小化
- 每个字段应该承载最大信息量
- 冗余字段增加描述长度，降低效率
```

**实践指南**：
- 问自己：这个字段真的必要吗？
- 合并语义相近的字段
- 删除可以从其他字段推导的信息

### 原则8：显式边界标记原则（XML 结构化）

**理论基础**：LLM 的 Attention 机制在处理结构化信息时，需要识别信息的边界。显式的边界标记（如 XML 标签）比隐式边界（如 Markdown 格式）更容易被准确识别。

**为什么 XML 对 LLM 更友好？**

1. **训练数据优势**：
   - LLM 训练数据包含大量 HTML/XML（网页、配置文件、API 响应、代码注释）
   - LLM 已经内化了 XML 的语义结构：`<tag>` = 开始，`</tag>` = 结束

2. **Attention 机制友好**：
   ```
   XML: <what>字段含义</what>
              ↑         ↑
           开始标记   结束标记  → 边界清晰，Attention 集中
   
   Markdown: WHAT: 字段含义
                   ↑
              只有开始标记 → 边界模糊，需要推断
   ```

3. **信息检索效率**：
   - XML：找到 `<when>` → 提取到 `</when>` 之间的内容（O(1) 定位）
   - Markdown：找到 `WHEN:` → 推断内容边界 → 提取内容（需要额外推理）

4. **层级关系表达**：
   ```xml
   <dependency>
     <field>dimensions</field>
     <condition>length > 1</condition>
     <reason>Single dimension doesn't need scope</reason>
   </dependency>
   ```
   XML 天然支持嵌套，可以表达复杂的依赖关系。

**实践指南**：
- 条件字段的描述使用 XML 格式（依赖关系复杂）
- 简单字段可保持 Markdown 格式（成本收益比低）
- 使用标准化的 XML 标签：`<what>`, `<when>`, `<how>`, `<dependency>`, `<values>`, `<examples>`, `<anti_patterns>`
- 在 Class Docstring 中使用 `<dependency_matrix>` 表达字段依赖关系

**对比示例**：

```python
# ❌ Markdown 格式（边界模糊）
computation_scope: Optional[str] = Field(
    description="""Computation scope.

WHAT: Whether to calculate per-group or across all data
WHEN: ONLY when query has MULTIPLE dimensions
DEPENDENCY: Requires dimensions.length > 1

VALUES:
- per_group: Calculate independently per group
- across_all: Calculate across all data"""
)

# ✅ XML 格式（边界清晰）
computation_scope: Optional[str] = Field(
    description="""Computation scope.

<what>Whether to calculate per-group or across all data</what>

<when>ONLY when query has MULTIPLE dimensions (len(dimensions) > 1)</when>

<dependency>
- field: dimensions
- condition: length > 1
</dependency>

<values>
- per_group: Calculate independently per group
- across_all: Calculate across all data
</values>"""
)
```

### 原则9：位置敏感原则（Lost in the Middle）

**理论基础**：学术研究发现 LLM 对长上下文的中间部分注意力最低，开头和结尾的信息更容易被记住。

```
Attention 分布（长上下文）：
┌─────────────────────────────────────────────────────────────┐
│ 开头 ████████████████                                        │ ← 高注意力
│ 中间         ████                                            │ ← 低注意力（Lost in the Middle）
│ 结尾                                    ████████████████████ │ ← 高注意力
└─────────────────────────────────────────────────────────────┘
```

**实践指南**：
- 关键信息放在开头（如：字段的 `<what>` 和 `<when>`）
- 示例放在结尾（最近的上下文，最高的参考价值）
- 中间放次要信息（如：详细解释、边界情况）

**应用示例**：
```python
field: str = Field(
    description="""
<what>核心含义（开头，高注意力）</what>
<when>填写条件（开头，高注意力）</when>

<how>填写方式（中间，次要）</how>
<dependency>依赖关系（中间，次要）</dependency>

<examples>
示例1（结尾，高注意力）
示例2（结尾，高注意力）
</examples>"""
)
```

### 原则10：决策树原则（Tree of Thoughts）

**理论基础**：Google 的 Tree of Thoughts 研究表明，树状决策路径比线性决策更有效。LLM 可以探索多个推理路径并回溯错误。

**为什么决策树优于依赖矩阵？**

| 方面 | 依赖矩阵 | 决策树 |
|------|---------|--------|
| 决策路径 | 隐式（需推断） | 显式（直接跟随） |
| 条件分支 | 无法表达 | 天然支持 |
| 填写顺序 | 无 | 明确 |
| 回溯能力 | 无 | 支持 |

**实践指南**：
- 用 `<decision_tree>` 替代 `<dependency_matrix>`
- 明确决策的起点和终点
- 每个分支都有明确的条件和结果

### 原则11：填写顺序原则（Least-to-Most）

**理论基础**：Google 的 Least-to-Most Prompting 研究表明，先解决简单子问题，再解决复杂问题，可以显著提升准确率。

**应用到 Schema 设计**：
- 先填写无依赖的字段（简单）
- 再填写有依赖的字段（复杂）
- 依赖字段的值由先填字段决定

**实践指南**：
- 在 Class Docstring 中添加 `<fill_order>` 指令
- 必填字段排在前面
- 条件字段按触发条件分组

### 原则12：选项数量限制原则（工作记忆）

**理论基础**：认知科学研究表明，人类工作记忆约 7±2 个项目。LLM 的"工作记忆"也有类似限制。

**实践指南**：
- 枚举值数量 ≤ 7
- 如果超过 7 个，考虑分组或分层
- 使用 `Literal` 类型限制选项

```python
# ❌ 太多选项（超过工作记忆限制）
status: Literal["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"]

# ✅ 分组或减少选项
status: Literal["pending", "in_progress", "completed", "failed"]  # 4 个
```

### 原则13：双向关系显式化原则（Reversal Curse）

**理论基础**：学术研究发现 LLM 学会 "A is B" 不代表学会 "B is A"（逆转诅咒）。

**实践指南**：
- 双向关系需要显式说明
- 不要假设 LLM 能自动推断逆向关系

```python
# ❌ 只说明正向关系
"""
<dependency>
type=ranking → fill order
</dependency>
"""

# ✅ 同时说明正向和逆向关系
"""
<dependency>
type=ranking → fill order (required)
type≠ranking → skip order (must be null)
</dependency>
"""
```

### 原则14：外部验证原则（Calibration）

**理论基础**：研究表明 LLM 的置信度不等于准确度。高置信度输出可能是错的。

**实践指南**：
- 不要依赖 LLM 的自我评估
- 使用 Pydantic Validator 进行代码级验证（100% 可靠）
- 关键决策使用外部验证机制

```python
@model_validator(mode='after')
def validate_dependencies(self) -> 'AnalysisSpec':
    """代码级验证，100% 可靠"""
    # Rule: order only for ranking
    if self.order is not None and self.type != AnalysisType.RANKING:
        raise ValueError("order should only be set when type=ranking")
    return self
```

### 原则15：格式标准化原则（Prompt Sensitivity）

**理论基础**：研究发现微小的 Prompt 变化（标点、空格、换行）可能导致巨大的输出差异。

**实践指南**：
- Prompt 格式要标准化
- 使用模板而非手写
- 避免不必要的格式变化

```python
# ❌ 格式不一致
"""WHAT: 字段含义
WHEN:填写条件
HOW : 填写方式"""

# ✅ 格式标准化
"""<what>字段含义</what>
<when>填写条件</when>
<how>填写方式</how>"""
```

### 原则总结表

| 原则 | 核心思想 | 应用场景 | 研究来源 |
|------|---------|---------|---------|
| 最小激活 | 高密度关键词 | Prompt精简化 | Sparse Attention |
| 正交分解 | 独立决策 | Schema结构设计 | 认知科学 |
| 语义一致 | 统一术语 | Prompt-Schema对齐 | Instruction Tuning |
| 渐进约束 | 先理解后结构化 | 复杂任务分解 | CoT |
| ICL本质 | 模式激活 | 示例设计 | Meta研究 |
| 信息瓶颈 | 保留相关信息 | 字段选择 | 信息论 |
| MDL | 最短描述 | 整体简化 | 信息论 |
| XML结构化 | 显式边界标记 | Schema字段描述 | Anthropic |
| 位置敏感 | 开头/结尾高注意力 | 信息布局 | Lost in the Middle |
| 决策树 | 树状决策路径 | 条件字段 | Tree of Thoughts |
| 填写顺序 | 先简单后复杂 | 字段顺序 | Least-to-Most |
| 选项限制 | ≤7个选项 | 枚举设计 | 工作记忆 |
| 双向显式 | 正反关系都说明 | 依赖关系 | Reversal Curse |
| 外部验证 | 代码级验证 | 关键决策 | Calibration |
| 格式标准化 | 统一格式 | Prompt模板 | Prompt Sensitivity |

---

## 最佳实践

### 1. 保持一致性

**与项目其他模块保持一致**：
- 使用相同的4段式Prompt结构
- 使用相同的字段描述格式
- 使用相同的命名约定

### 2. 文档即代码

**字段描述要详细**：
```python
# ❌ 不好
field: str = Field(description="The field")

# ✅ 好
field: str = Field(
    description="""Technical field name.

Usage:
- Store exact field name from metadata

Values: Field name string (e.g., '[Sales].[Sales Amount]')"""
)
```

### 3. 类型安全

**使用严格的类型**：
```python
# ❌ 不好
field: Any

# ✅ 好
field: Union[str, int]  # 明确可能的类型
```

### 4. 验证规则

**添加适当的验证**：
```python
# 数值范围
confidence: float = Field(ge=0, le=1)

# 字符串模式
task_id: str = Field(pattern=r"^q\d+$")

# 列表长度
items: List[str] = Field(min_length=1)
```

### 5. 示例驱动的Schema设计

**在Class Docstring中提供完整示例**：
```python
class QuestionUnderstanding(BaseModel):
    """Question understanding result.
    
    EXAMPLES:
    
    Input: "各省份的销售额"
    Output: {
        "original_question": "各省份的销售额",
        "mentioned_dimensions": ["省份"],
        "mentioned_measures": ["销售额"],
        "dimension_aggregations": null,
        "measure_aggregations": {"销售额": "SUM"}
    }
    
    Input: "每个品类有多少产品"
    Output: {
        "original_question": "每个品类有多少产品",
        "mentioned_dimensions": ["品类", "产品"],
        "dimension_aggregations": {"产品": "COUNTD"},
        "mentioned_measures": []
    }
    
    ANTI-PATTERNS (常见错误):
    ❌ Using technical field names like "[Sales].[Amount]"
    ❌ Missing dimensions in "count of X per Y" patterns
    ❌ Setting needs_exploration=true for simple queries
    """
```

### 6. 自验证逻辑

**添加model_validator确保一致性**：
```python
from pydantic import model_validator

class QuestionUnderstanding(BaseModel):
    # ... fields ...
    
    @model_validator(mode='after')
    def validate_consistency(self) -> 'QuestionUnderstanding':
        # 验证: aggregated dimensions必须在mentioned_dimensions中
        if self.dimension_aggregations:
            for dim in self.dimension_aggregations.keys():
                if dim not in self.mentioned_dimensions:
                    raise ValueError(
                        f"Aggregated dimension '{dim}' not in mentioned_dimensions"
                    )
        return self
```

### 7. 避免过度设计

**保持简单**：
- 只定义必要的字段
- 避免过深的嵌套
- 优先使用简单类型

---

## 动态模块化 Prompt 系统

### 设计动机

传统的静态 Prompt 存在以下问题：
1. **上下文噪声**：每次都包含所有规则，即使大部分不相关
2. **注意力稀释**：无关信息竞争 Attention 权重
3. **维护困难**：修改一处可能影响其他场景

### 架构设计

```
用户问题
    ↓
FeatureDetector（特征检测）
    ↓
检测到的特征标签 {DIMENSION, MEASURE, TIME_RELATIVE, ...}
    ↓
DynamicPromptBuilder（动态构建）
    ↓
只包含相关模块的 Prompt
```

### 核心组件

#### 1. FeatureTag（特征标签）

```python
class FeatureTag(str, Enum):
    # 实体特征
    DIMENSION = "dimension"      # 有维度实体
    MEASURE = "measure"          # 有度量实体
    DATE_FIELD = "date_field"    # 有日期字段
    
    # 操作特征
    AGGREGATION = "aggregation"  # 需要聚合
    GROUPING = "grouping"        # 需要分组
    COUNTING = "counting"        # 计数操作
    
    # 时间特征
    TIME_ABSOLUTE = "time_absolute"    # 绝对时间
    TIME_RELATIVE = "time_relative"    # 相对时间
    TIME_COMPARISON = "time_comparison" # 时间对比
    
    # 分析特征
    TREND = "trend"              # 趋势分析
    RANKING = "ranking"          # 排名分析
    COMPARISON = "comparison"    # 对比分析
```

#### 2. PromptModule（提示词模块）

```python
@dataclass
class PromptModule:
    name: str                    # 模块名称
    tags: Set[FeatureTag]        # 激活标签
    knowledge: str               # 领域知识
    priority: int = 100          # 加载优先级
    required: bool = False       # 是否必须包含
```

#### 3. FeatureDetector（特征检测器）

```python
class FeatureDetector:
    PATTERNS = [
        (r"各\w+|按\w+|每个\w+", FeatureTag.DIMENSION),
        (r"销售额|利润|收入", FeatureTag.MEASURE),
        (r"最近\d+个?[天周月季年]", FeatureTag.TIME_RELATIVE),
        # ...
    ]
    
    def detect(self, question: str) -> Set[FeatureTag]:
        """检测问题中的特征"""
```

#### 4. DynamicPromptBuilder（动态构建器）

```python
class DynamicPromptBuilder:
    def build_prompt(self, question: str) -> str:
        features = self.detect_features(question)
        modules = self.select_modules(features)
        return self.build_knowledge(modules)
```

### 使用示例

```python
from tableau_assistant.prompts.modules import (
    DynamicPromptBuilder,
    ModularUnderstandingPrompt
)

# 方式1：直接使用构建器
builder = DynamicPromptBuilder()
knowledge = builder.build_prompt("各省份最近3个月的销售额趋势")
# 只包含: DIMENSION, MEASURE, TIME_RELATIVE, TREND 相关模块

# 方式2：使用模块化 Prompt
prompt = ModularUnderstandingPrompt()
messages = prompt.format_messages(
    question="各省份最近3个月的销售额趋势",
    max_date="2024-12-04"
)
```

### 优势

| 方面 | 静态 Prompt | 动态 Prompt |
|------|------------|------------|
| 上下文长度 | 固定（长） | 按需（短） |
| 注意力分布 | 分散 | 集中 |
| 维护成本 | 高（耦合） | 低（模块化） |
| 扩展性 | 差 | 好（添加模块） |

---

## 结构化 Chain-of-Thought (CoT)

### 设计动机

对于复杂问题，直接输出结果容易出错。结构化 CoT 提供：
1. **可追溯性**：可以看到每个决策的原因
2. **准确性**：强制系统性思考
3. **可调试性**：容易定位推理错误

### 推理步骤设计

```python
class ReasoningStep(BaseModel):
    step_name: str      # 步骤名称
    analysis: str       # 分析过程
    conclusion: str     # 步骤结论
```

### 5 步推理流程

| 步骤 | 目的 | 示例分析 | 示例结论 |
|------|------|---------|---------|
| intent | 理解用户意图 | "用户想按省份分组查看销售额汇总" | "多维分解查询" |
| entities | 提取业务术语 | "识别到'省份'和'销售额'两个术语" | "2个实体" |
| roles | 分类 SQL 角色 | "'各省份'表示分组，'销售额'需要聚合" | "省份→group_by, 销售额→aggregate(SUM)" |
| time | 识别时间范围 | "问题中没有时间限定词" | "无时间范围" |
| validation | 验证一致性 | "所有实体分类完整，无冲突" | "验证通过" |

### 输出示例

```json
{
  "question": "各省份的销售额",
  "is_valid": true,
  "reasoning": [
    {
      "step_name": "intent",
      "analysis": "用户想按省份分组查看销售额的汇总数据",
      "conclusion": "多维分解查询"
    },
    {
      "step_name": "entities",
      "analysis": "识别到两个业务术语：'省份'（分类字段）和'销售额'（数值字段）",
      "conclusion": "2个实体"
    },
    {
      "step_name": "roles",
      "analysis": "'各省份'表示按省份分组，'销售额'需要聚合求和",
      "conclusion": "省份→group_by, 销售额→aggregate(SUM)"
    },
    {
      "step_name": "time",
      "analysis": "问题中没有时间限定词",
      "conclusion": "无时间范围"
    },
    {
      "step_name": "validation",
      "analysis": "所有实体分类完整，无冲突",
      "conclusion": "验证通过"
    }
  ],
  "entities": [
    {"name": "省份", "type": "dimension", "role": "group_by"},
    {"name": "销售额", "type": "measure", "role": "aggregate", "aggregation": "SUM"}
  ],
  "time_range": null,
  "question_types": ["多维分解"],
  "complexity": "Simple"
}
```

### 何时使用 CoT

| 问题类型 | 是否需要 CoT | 原因 |
|---------|-------------|------|
| 简单查询 | 可选 | 直接输出即可 |
| 多实体查询 | 推荐 | 需要分别分类 |
| 时间相关 | 推荐 | 时间解析复杂 |
| 复杂分析 | 必须 | 多步推理 |

---

## 总结

### Prompt模板

**是什么**：给LLM的结构化指令模板

**本质作用**：导航到正确的知识子空间

**职责**：教LLM **如何思考** (HOW to think)

**包含**：
- Role: 身份定义（激活相关知识）
- Task: 任务描述（聚焦注意力）
- Domain Knowledge: 领域概念、分析方法、推理步骤
- Constraints: 全局约束

**不包含**：
- 具体字段名
- 字段填写规则
- 取值范围说明

### 数据模型

**是什么**：使用Pydantic定义的数据结构

**本质作用**：塑造输出的概率分布

**职责**：告诉LLM **输出什么** (WHAT to output)

**包含**：
- Class Docstring: 完整示例 + 常见错误（使用 `<examples>` 和 `<anti_patterns>` 标签）
- Field Description: 使用 XML 标签（`<what>`, `<when>`, `<how>`, `<dependency>`, `<values>`, `<examples>`）
- Validators: 自验证逻辑（Pydantic model_validator）
- Dependency Matrix: 字段依赖关系矩阵（使用 `<dependency_matrix>` 标签）

**不包含**：
- 分析方法
- 推理步骤
- 决策逻辑

### 职责边界黄金法则

> **Prompt教LLM如何思考，Schema告诉LLM输出什么**
> 
> 如果提到具体字段名 → 放在Schema
> 如果是通用分析方法 → 放在Prompt

### 设计原则层次

**第一层：职责分离**
- Prompt和Schema各司其职，不重复
- Prompt提供认知框架，Schema提供结构约束

**第二层：底层优化**
- 最小激活：高密度关键词，减少冗余
- 正交分解：字段独立决策，减少依赖
- 语义一致：Prompt和Schema术语统一
- 渐进约束：先理解后结构化
- **XML结构化**：显式边界标记，提高 Attention 效率

**第三层：实践规范**
- 示例驱动：Schema中提供完整的输入输出示例
- 错误预防：Schema中列出常见错误(Anti-patterns)
- 依赖明确：条件字段使用 `<dependency>` 标签说明依赖关系
- 自验证：添加model_validator确保一致性（代码级 100% 可靠）

### 核心洞察

```
LLM的知识空间是一个高维流形
Prompt = 导航坐标（激活正确的知识）
Schema = 着陆区域（约束输出分布）
XML标签 = 边界标记（提高信息检索效率）
决策树 = 路径指引（引导填写顺序）
Validator = 安全网（代码级100%可靠验证）

优化的核心（基于前沿研究）：
1. 用最少的token激活最精确的知识（Sparse Attention）
2. 用正交的字段分解复杂决策（认知科学）
3. 用一致的语义连接Prompt和Schema（Instruction Tuning）
4. 用渐进的约束引导输出（CoT）
5. 用XML标签标记信息边界（Anthropic研究）
6. 用决策树替代依赖矩阵（Tree of Thoughts）
7. 用填写顺序指导生成（Least-to-Most）
8. 关键信息放开头/结尾（Lost in the Middle）
9. 枚举值≤7个（工作记忆限制）
10. 双向关系显式说明（Reversal Curse）
11. 代码级验证关键决策（Calibration）
```

### XML 格式快速参考

**标准 XML 标签**：
| 标签 | 用途 | 必填 | 位置建议 |
|------|------|------|---------|
| `<what>` | 字段含义 | ✅ | 开头（高注意力） |
| `<when>` | 填写条件 | ✅ | 开头（高注意力） |
| `<how>` | 填写方式 | ✅ | 中间 |
| `<dependency>` | 依赖关系 | 条件字段 | 中间 |
| `<values>` | 取值范围 | 推荐 | 中间 |
| `<decision_rule>` | 决策规则 | 复杂条件 | 中间 |
| `<examples>` | 示例 | 推荐 | 结尾（高注意力） |
| `<anti_patterns>` | 常见错误 | 推荐 | 结尾（高注意力） |

**Class Docstring 标签**：
| 标签 | 用途 | 说明 |
|------|------|------|
| `<decision_tree>` | 决策树 | 替代 dependency_matrix，表达树状决策路径 |
| `<fill_order>` | 填写顺序 | 明确字段填写顺序（先简单后复杂） |
| `<conditional_groups>` | 条件分组 | 按触发条件分组字段 |
| `<examples>` | 完整示例 | 输入→输出示例 |
| `<anti_patterns>` | 常见错误 | 避免的错误模式 |

**使用原则**：
- 条件字段（有依赖关系）：**必须**使用 XML 格式
- 简单字段（无依赖）：可选使用 XML 格式
- Class Docstring：使用 `<decision_tree>`, `<fill_order>`, `<examples>`, `<anti_patterns>`
- 信息布局：关键信息放开头/结尾，次要信息放中间

### 15 条设计原则速查

| # | 原则 | 核心思想 | 研究来源 |
|---|------|---------|---------|
| 1 | 最小激活 | 高密度关键词 | Sparse Attention |
| 2 | 正交分解 | 独立决策 | 认知科学 |
| 3 | 语义一致 | 统一术语 | Instruction Tuning |
| 4 | 渐进约束 | 先理解后结构化 | CoT |
| 5 | ICL本质 | 模式激活 | Meta研究 |
| 6 | 信息瓶颈 | 保留相关信息 | 信息论 |
| 7 | MDL | 最短描述 | 信息论 |
| 8 | XML结构化 | 显式边界标记 | Anthropic |
| 9 | 位置敏感 | 开头/结尾高注意力 | Lost in the Middle |
| 10 | 决策树 | 树状决策路径 | Tree of Thoughts |
| 11 | 填写顺序 | 先简单后复杂 | Least-to-Most |
| 12 | 选项限制 | ≤7个选项 | 工作记忆 |
| 13 | 双向显式 | 正反关系都说明 | Reversal Curse |
| 14 | 外部验证 | 代码级验证 | Calibration |
| 15 | 格式标准化 | 统一格式 | Prompt Sensitivity |
