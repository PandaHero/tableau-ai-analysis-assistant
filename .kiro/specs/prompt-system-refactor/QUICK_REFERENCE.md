# 结构化 Prompt 模板快速参考

## 🚀 快速开始

### 使用现有 v3 Prompts

```python
from tableau_assistant.prompts import (
    QUESTION_BOOST_PROMPT_V3,
    UNDERSTANDING_PROMPT_V3,
    TASK_PLANNER_PROMPT_V3
)

# 使用 Question Boost
messages = QUESTION_BOOST_PROMPT_V3.format_messages(
    question="显示销售额",
    metadata={...}
)

# 使用 Understanding
messages = UNDERSTANDING_PROMPT_V3.format_messages(
    question="显示各地区的销售额",
    metadata={...}
)

# 使用 Task Planner
messages = TASK_PLANNER_PROMPT_V3.format_messages(
    understanding={...},
    metadata={...},
    dimension_hierarchy={...}
)
```

## 📐 架构层次

```
BasePrompt (基础接口)
  └── StructuredPrompt (6个标准部分)
      └── DataAnalysisPrompt (数据分析)
          └── VizQLPrompt (VizQL专用)
              └── 你的自定义Prompt
```

## 🎯 6 个标准部分

| 部分 | 用途 | 必需? |
|------|------|-------|
| **ROLE** | 定义AI角色和专业领域 | 推荐 |
| **TASK** | 定义任务和预期结果 | 推荐 |
| **CONTEXT** | 提供领域知识和资源 | 可选 |
| **PRINCIPLES** | 定义决策原则 | 推荐 |
| **CONSTRAINTS** | 定义边界和限制 | 可选 |
| **OUTPUT REQUIREMENTS** | 定义质量标准 | 可选 |

## 📝 创建自定义 Prompt

### 选择基类

```python
# 数据分析任务 → 使用 DataAnalysisPrompt
from tableau_assistant.prompts.base import DataAnalysisPrompt

class MyDataPrompt(DataAnalysisPrompt):
    # 自动获得数据分析上下文
    pass

# VizQL 任务 → 使用 VizQLPrompt
from tableau_assistant.prompts.base import VizQLPrompt

class MyVizQLPrompt(VizQLPrompt):
    # 自动获得数据分析 + VizQL 上下文
    pass
```

### 实现标准部分

```python
from typing import Type
from pydantic import BaseModel
from tableau_assistant.prompts.base import DataAnalysisPrompt

class MyPrompt(DataAnalysisPrompt):
    """我的自定义 prompt"""
    
    def get_role(self) -> str:
        return """You are a [role] who [does what].
        
Your expertise includes [expertise areas]."""
    
    def get_task(self) -> str:
        return """[Task description]:

1. **[Outcome 1]**: [Description]
2. **[Outcome 2]**: [Description]
3. **[Outcome 3]**: [Description]

Expected outcome: [What success looks like]."""
    
    def get_specific_context(self) -> str:
        # 注意：使用 get_specific_context 而不是 get_context
        # get_context 会自动组合通用和特定上下文
        return """## Available Resources
- Resource 1: {placeholder1}
- Resource 2: {placeholder2}

## [Context Category]
- Context point 1
- Context point 2"""
    
    def get_principles(self) -> str:
        return """## [Principle Category]

1. **[Principle 1]**: [Description]
2. **[Principle 2]**: [Description]
3. **[Principle 3]**: [Description]

## [Decision Criteria]
- When X: Do Y
- When Z: Do W"""
    
    def get_constraints(self) -> str:
        return """## Must NOT
- Don't do X
- Avoid Y
- Never Z

## Edge Cases
- **[Case 1]**: [How to handle]
- **[Case 2]**: [How to handle]"""
    
    def get_output_requirements(self) -> str:
        return """## Quality Standards
Before outputting, verify:
- [ ] Requirement 1
- [ ] Requirement 2
- [ ] Requirement 3

## Common Mistakes to Avoid
- Mistake 1
- Mistake 2
- Mistake 3"""
    
    def get_user_template(self) -> str:
        return """Input: {input}
Context: {context}

[Instruction to AI]."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return MyOutputModel
```

## ✅ 验证 Prompt

```python
# 创建 prompt 实例
my_prompt = MyPrompt()

# 验证完整性
warnings = my_prompt.validate()
if warnings:
    print(f"警告: {warnings}")
else:
    print("✓ Prompt 完整")

# 生成消息
messages = my_prompt.format_messages(
    input="test",
    context="test context"
)
```

## 🎨 内容编写技巧

### ROLE 部分
```python
def get_role(self) -> str:
    return """You are a [具体角色] who [核心职责].

Your expertise includes [专业领域1], [专业领域2], and [专业领域3]."""
```

**要点**:
- 2-3 句话
- 清晰的角色定位
- 列出核心专业领域

### TASK 部分
```python
def get_task(self) -> str:
    return """[动词] the [对象] to [目标]:

1. **[子任务1]**: [具体描述]
2. **[子任务2]**: [具体描述]
3. **[子任务3]**: [具体描述]

Expected outcome: [成功标准]."""
```

**要点**:
- 使用动词开头（Analyze, Generate, Transform）
- 列表形式，具体可执行
- 明确预期结果

### CONTEXT 部分
```python
def get_specific_context(self) -> str:
    return """## Available Resources
- [资源1]: {placeholder}
- [资源2]: {placeholder}

## [领域知识类别]
- [知识点1]
- [知识点2]

## [能力/限制]
- [能力描述]
- [限制描述]"""
```

**要点**:
- 使用占位符 `{placeholder}` 表示动态内容
- 分类组织信息
- 提供充分的领域知识

### PRINCIPLES 部分
```python
def get_principles(self) -> str:
    return """## [原则类别]

1. **[原则名称]**: [原则描述]
2. **[原则名称]**: [原则描述]

## [决策标准]
- **When [条件]**: [行动]
- **When [条件]**: [行动]

## [优先级]
When conflicts arise:
1. [最高优先级]
2. [次优先级]
3. [最低优先级]"""
```

**要点**:
- 原则而非规则（"如何思考"而非"做什么"）
- 分层组织
- 提供决策标准和优先级

### CONSTRAINTS 部分
```python
def get_constraints(self) -> str:
    return """## Must NOT
- [禁止事项1]
- [禁止事项2]
- [禁止事项3]

## Edge Cases
- **[边缘情况1]**: [处理方式]
- **[边缘情况2]**: [处理方式]

## [边界/限制]
- [边界描述]
- [限制描述]"""
```

**要点**:
- 明确禁止事项
- 处理边缘情况
- 定义清晰边界

### OUTPUT REQUIREMENTS 部分
```python
def get_output_requirements(self) -> str:
    return """## Quality Standards
Before outputting, verify:
- [ ] [质量标准1]
- [ ] [质量标准2]
- [ ] [质量标准3]

## Validation Checklist
- [验证项1]
- [验证项2]

## Common Mistakes to Avoid
- [常见错误1]
- [常见错误2]
- [常见错误3]"""
```

**要点**:
- 使用 checklist 格式
- 列出常见错误
- 关注质量而非格式（Schema 自动注入）

## 🔄 继承和复用

### 继承 DataAnalysisPrompt

```python
class MyPrompt(DataAnalysisPrompt):
    # 自动获得:
    # - Data Analysis Fundamentals
    # - 业务术语优先
    # - 可操作洞察
    # - 数据质量考虑
    
    def get_specific_context(self) -> str:
        # 添加你的特定上下文
        return "..."
```

### 继承 VizQLPrompt

```python
class MyPrompt(VizQLPrompt):
    # 自动获得:
    # - Data Analysis Fundamentals
    # - VizQL Query Capabilities
    # - 单查询能力和限制
    # - vizql_context 占位符
    
    def get_specific_context(self) -> str:
        # 添加你的特定上下文
        return "..."
```

## 📊 版本对比

### 何时使用哪个版本?

| 场景 | 推荐版本 | 原因 |
|------|---------|------|
| 新功能开发 | v3 | 最佳结构和可维护性 |
| 现有功能维护 | v2 | 已验证，稳定 |
| 快速原型 | v2 | 更简单，更快 |
| 复杂 Agent | v3 | 更好的组织和复用 |
| 团队协作 | v3 | 标准化，易理解 |

### 迁移路径

```python
# v2 → v3 迁移
# 1. 改变基类
from tableau_assistant.prompts.base import VizQLPrompt  # v3

# 2. 拆分 get_system_message 为 6 个部分
class MyPrompt(VizQLPrompt):
    def get_role(self) -> str:
        # 从原 system_message 提取 role 部分
        return "..."
    
    def get_task(self) -> str:
        # 从原 system_message 提取 task 部分
        return "..."
    
    # ... 其他部分
```

## 🐛 常见问题

### Q: 为什么使用 `get_specific_context` 而不是 `get_context`?

A: `get_context()` 在 `DataAnalysisPrompt` 中已经实现，它会自动组合通用数据分析上下文和你的特定上下文。你应该覆盖 `get_specific_context()` 来添加你的特定内容。

```python
# ✗ 错误
def get_context(self) -> str:
    return "My context"  # 会覆盖通用上下文

# ✓ 正确
def get_specific_context(self) -> str:
    return "My context"  # 会追加到通用上下文
```

### Q: 如何在 prompt 中使用占位符?

A: 在任何返回字符串的方法中使用 `{placeholder}` 格式：

```python
def get_specific_context(self) -> str:
    return """## Available Data
- Metadata: {metadata}
- User input: {question}"""

# 使用时
messages = prompt.format_messages(
    metadata={...},
    question="..."
)
```

### Q: 所有 6 个部分都必须实现吗?

A: 不是。只有 `get_user_template()` 和 `get_output_model()` 是必需的（来自 `BasePrompt`）。但推荐至少实现 ROLE, TASK, PRINCIPLES 以获得最佳效果。

### Q: 如何处理向后兼容性?

A: v3 prompts 通过 `format_messages()` 自动注入 `vizql_context`，保持与 v2 模板的兼容性。

## 📚 更多资源

- **完整示例**: `tableau_assistant/examples/structured_prompt_usage.py`
- **测试用例**: `tableau_assistant/tests/test_structured_prompts_v3.py`
- **实施总结**: `.kiro/specs/prompt-system-refactor/STRUCTURED_TEMPLATE_SUMMARY.md`
- **设计文档**: `.kiro/specs/prompt-system-refactor/design.md`

## 🎓 最佳实践清单

- [ ] 选择合适的基类（DataAnalysisPrompt 或 VizQLPrompt）
- [ ] 实现至少 ROLE, TASK, PRINCIPLES 三个部分
- [ ] 使用 `get_specific_context()` 而不是 `get_context()`
- [ ] 在内容中使用 `{placeholder}` 表示动态数据
- [ ] 运行 `validate()` 检查完整性
- [ ] 编写测试用例验证功能
- [ ] 添加完整的 docstring
- [ ] 提供预实例化的常量（如 `MY_PROMPT_V3`）

---

**版本**: v3.0  
**更新日期**: 2024  
**状态**: ✅ 可用
