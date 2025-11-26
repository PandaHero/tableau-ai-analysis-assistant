# Prompt模板和数据模型编写指南

## 目录
1. [Prompt模板是什么？](#prompt模板是什么)
2. [数据模型是什么？](#数据模型是什么)
3. [为什么需要它们？](#为什么需要它们)
4. [如何编写Prompt模板](#如何编写prompt模板)
5. [如何编写数据模型](#如何编写数据模型)
6. [最佳实践](#最佳实践)

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

#### 4. **字段描述格式**

**标准格式**：
```python
field_name: str = Field(
    description="""Brief one-line description.

Usage:
- When to include this field
- When to set it to null/empty

Values: What values are valid
- Value 1: explanation
- Value 2: explanation"""
)
```

**示例**：
```python
confidence: float = Field(
    description="""Mapping confidence score.

Usage:
- Indicate confidence in the mapping

Values: Float between 0 and 1
- 0.9-1.0: Perfect match
- 0.7-0.9: Good match
- 0.5-0.7: Acceptable match
- 0.0-0.5: Poor match"""
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

### 5. 示例和测试

**提供使用示例**：
```python
class FieldMappingResult(BaseModel):
    # ...
    
    class Config:
        json_schema_extra = {
            "example": {
                "business_term": "sales",
                "matched_field": "Sales Amount",
                "confidence": 0.95,
                "reasoning": "Perfect semantic match"
            }
        }
```

### 6. 避免过度设计

**保持简单**：
- 只定义必要的字段
- 避免过深的嵌套
- 优先使用简单类型

---

## 总结

### Prompt模板

**是什么**：给LLM的结构化指令模板

**作用**：
- 指导LLM行为
- 保证输出质量
- 提高一致性
- 便于维护

**如何写**：
1. 继承`VizQLPrompt`
2. 实现4个方法（Role, Task, Domain Knowledge, Constraints）
3. 全英文编写
4. 清晰的步骤和约束

### 数据模型

**是什么**：使用Pydantic定义的数据结构

**作用**：
- 类型安全
- 数据验证
- 文档化
- IDE支持

**如何写**：
1. 继承`BaseModel`
2. 设置`model_config = ConfigDict(extra="forbid")`
3. 详细的字段描述（Usage + Values）
4. 适当的类型和验证规则

### 关键原则

1. **一致性** - 与项目其他模块保持一致
2. **清晰性** - 描述清晰，易于理解
3. **完整性** - 包含所有必要信息
4. **简洁性** - 避免冗余和过度设计
5. **可维护性** - 易于修改和扩展
