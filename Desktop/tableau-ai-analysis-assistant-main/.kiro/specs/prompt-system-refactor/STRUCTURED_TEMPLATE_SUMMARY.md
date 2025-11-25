# 结构化模板系统实施总结

## 🎯 实施目标

基于用户反馈，建立一个标准化的 Prompt 模板结构，解决以下问题：
- 当前 prompt 结构不统一，随意性强
- 缺乏通用性，规则和示例过于具体
- 难以维护和扩展
- 缺乏质量保证机制

## 📐 设计方案

### 三层架构设计

```
┌─────────────────────────────────────────────────────┐
│ Layer 1: BasePrompt (通用基础)                       │
│ - 基本接口定义                                        │
│ - Schema 自动注入                                     │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ Layer 2: StructuredPrompt (结构化模板)               │
│ - 标准化的 6 个部分                                   │
│ - 自动组装逻辑                                        │
│ - 验证机制                                           │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│ Layer 3: Domain-Specific Prompts (领域专用)          │
│ - DataAnalysisPrompt (数据分析专用)                  │
│ - VizQLPrompt (VizQL 专用)                           │
│ - 预定义领域知识                                      │
└─────────────────────────────────────────────────────┘
```

### 6 个标准化部分

1. **ROLE** - 定义 AI 的角色和专业领域
2. **TASK** - 定义任务和预期结果
3. **CONTEXT** - 提供领域知识和可用资源
4. **PRINCIPLES** - 定义核心决策原则
5. **CONSTRAINTS** - 定义边界和限制
6. **OUTPUT REQUIREMENTS** - 定义输出格式和质量要求

## 🛠️ 实施内容

### 1. 基础架构 (base.py)

#### StructuredPrompt 基类
```python
class StructuredPrompt(BasePrompt):
    """6 个标准化部分的结构化模板"""
    
    def get_role(self) -> str: pass
    def get_task(self) -> str: pass
    def get_context(self) -> str: pass
    def get_principles(self) -> str: pass
    def get_constraints(self) -> str: pass
    def get_output_requirements(self) -> str: pass
    
    def get_system_message(self) -> str:
        """自动组装所有非空部分"""
        # 组装逻辑...
    
    def validate(self) -> List[str]:
        """验证完整性"""
        # 验证逻辑...
```

#### DataAnalysisPrompt 基类
```python
class DataAnalysisPrompt(StructuredPrompt):
    """数据分析领域专用基类"""
    
    def get_data_analysis_context(self) -> str:
        """通用数据分析原则"""
        return """
        - Work with business terminology
        - Focus on actionable insights
        - Consider data quality
        """
    
    def get_context(self) -> str:
        """组合通用和特定上下文"""
        base = self.get_data_analysis_context()
        specific = self.get_specific_context()
        return f"{base}\n\n{specific}"
```

#### VizQLPrompt 基类
```python
class VizQLPrompt(DataAnalysisPrompt):
    """VizQL 专用基类"""
    
    def get_vizql_capabilities(self) -> str:
        """VizQL 能力描述"""
        return """
        **Single Query Can Handle:**
        - Multiple dimensions and measures
        - Multiple filters
        ...
        
        **Single Query CANNOT Handle:**
        - Multiple independent time periods
        - Cross-query dependencies
        ...
        """
    
    def get_specific_context(self) -> str:
        return self.get_vizql_capabilities()
```

### 2. v3 Prompts 实现

#### Question Boost Prompt v3
```python
class QuestionBoostPrompt(DataAnalysisPrompt):
    def get_role(self) -> str:
        return "You are a business data analyst..."
    
    def get_task(self) -> str:
        return """Enhance the user's question to make it:
        1. Specific
        2. Actionable
        3. Structured"""
    
    def get_principles(self) -> str:
        return """
        1. Preserve Intent
        2. Add Context
        3. Add Value
        4. Use Business Language
        5. Be Minimal
        """
    
    # ... 其他部分
```

#### Understanding Prompt v3
```python
class UnderstandingPrompt(VizQLPrompt):
    def get_role(self) -> str:
        return "You are a VizQL query analyst..."
    
    def get_principles(self) -> str:
        return """
        1. Single Query First
        2. Data Queries Only
        3. Business Terminology
        4. Explicit Relationships
        
        ## When to Split
        - Multiple time periods
        - Total + parts
        
        ## When NOT to Split
        - Single query sufficient
        - Exploratory questions
        """
    
    # ... 其他部分
```

#### Task Planner Prompt v3
```python
class TaskPlannerPrompt(VizQLPrompt):
    def get_role(self) -> str:
        return "You are a VizQL query generator..."
    
    def get_principles(self) -> str:
        return """
        ## Field Selection Principles
        
        ### 1. Semantic Matching
        - Field caption similarity
        - Category alignment
        - Sample values relevance
        
        ### 2. Granularity Selection
        - Prefer level 1-2
        - Avoid level 5
        - Consider unique_count
        
        ### 3. Measure Selection
        - Question intent
        - Field semantics
        - Analysis context
        """
    
    # ... 其他部分
```

### 3. 导出结构

```python
# tableau_assistant/prompts/__init__.py

# 基础架构
from .base import (
    BasePrompt,
    StructuredPrompt,
    DataAnalysisPrompt,
    VizQLPrompt
)

# v3 结构化模板（推荐使用）
from .question_boost_v3 import (
    QuestionBoostPrompt,
    QUESTION_BOOST_PROMPT_V3
)
from .understanding_v3 import (
    UnderstandingPrompt,
    UNDERSTANDING_PROMPT_V3
)
from .task_planner_v3 import (
    TaskPlannerPrompt,
    TASK_PLANNER_PROMPT_V3
)

# v2 重构后的提示词（向后兼容）
from .question_boost_v2 import (
    QuestionBoostPrompt as QuestionBoostPromptV2,
    QUESTION_BOOST_PROMPT_V2
)
# ... 其他 v2 prompts
```

## ✅ 实施成果

### 已创建的文件

1. **基础架构**
   - `tableau_assistant/prompts/base.py` - 更新，添加 StructuredPrompt, DataAnalysisPrompt, VizQLPrompt

2. **v3 Prompts**
   - `tableau_assistant/prompts/question_boost_v3.py` - 新建
   - `tableau_assistant/prompts/understanding_v3.py` - 新建
   - `tableau_assistant/prompts/task_planner_v3.py` - 新建

3. **测试**
   - `tableau_assistant/tests/test_structured_prompts_v3.py` - 新建

4. **导出**
   - `tableau_assistant/prompts/__init__.py` - 更新

### 验证结果

✅ 所有文件无语法错误
✅ 导入测试通过
✅ 结构化模板系统正常工作

## 🎨 设计优势

### 1. 标准化但灵活
- 6 个标准部分，但都是可选的
- 可以只实现需要的部分
- 易于扩展和定制

### 2. 分层复用
- **DataAnalysisPrompt** 提供通用数据分析知识
- **VizQLPrompt** 提供 VizQL 专用知识
- 具体 Agent 只需关注自己的逻辑

### 3. 清晰的职责分离
- **ROLE**: 身份定位
- **TASK**: 做什么
- **CONTEXT**: 领域知识
- **PRINCIPLES**: 如何思考
- **CONSTRAINTS**: 边界
- **OUTPUT**: 质量要求

### 4. 易于维护
- 每个部分独立修改
- 通用知识在基类中
- 验证机制确保完整性

### 5. 自文档化
- 结构本身就是文档
- 新人容易理解
- 代码即规范

## 📊 对比分析

### v1 (原始) vs v2 (原则驱动) vs v3 (结构化模板)

| 特性 | v1 | v2 | v3 |
|------|----|----|-----|
| 结构化程度 | 低 | 中 | 高 |
| 可维护性 | 低 | 中 | 高 |
| 通用性 | 低 | 高 | 高 |
| 学习曲线 | 陡峭 | 中等 | 平缓 |
| 质量保证 | 无 | 部分 | 完整 |
| 代码复用 | 低 | 中 | 高 |

### 迁移路径

```
v1 (原始)
  ↓ 重构
v2 (原则驱动) ← 当前生产环境
  ↓ 结构化
v3 (结构化模板) ← 推荐使用
```

## 🚀 使用示例

### 创建新的 Prompt

```python
from tableau_assistant.prompts.base import VizQLPrompt
from pydantic import BaseModel

class MyPrompt(VizQLPrompt):
    """我的自定义 prompt"""
    
    def get_role(self) -> str:
        return "You are a..."
    
    def get_task(self) -> str:
        return "Your task is to..."
    
    def get_principles(self) -> str:
        return """
        1. Principle 1
        2. Principle 2
        """
    
    def get_constraints(self) -> str:
        return """
        ## Must NOT
        - Don't do X
        - Avoid Y
        """
    
    def get_user_template(self) -> str:
        return "Input: {input}"
    
    def get_output_model(self):
        return MyOutputModel

# 使用
my_prompt = MyPrompt()
messages = my_prompt.format_messages(input="test")

# 验证
warnings = my_prompt.validate()
if warnings:
    print(f"Warnings: {warnings}")
```

### 继承层次示例

```python
# 继承 DataAnalysisPrompt（数据分析任务）
class MyDataPrompt(DataAnalysisPrompt):
    # 自动获得数据分析上下文
    pass

# 继承 VizQLPrompt（VizQL 任务）
class MyVizQLPrompt(VizQLPrompt):
    # 自动获得数据分析 + VizQL 上下文
    pass
```

## 📝 后续工作

### 短期（已完成）
- [x] 创建基础架构（StructuredPrompt, DataAnalysisPrompt, VizQLPrompt）
- [x] 实现 v3 版本的 3 个核心 prompts
- [x] 创建测试套件
- [x] 更新导出

### 中期（待完成）
- [ ] 更新 Agent 使用 v3 prompts
- [ ] 迁移其他 prompts 到 v3 架构
- [ ] 添加更多测试用例
- [ ] 性能对比测试

### 长期
- [ ] 逐步废弃 v1 prompts
- [ ] 建立 prompt 质量评估体系
- [ ] 创建 prompt 开发最佳实践文档

## 🎓 最佳实践

### 1. Prompt 开发流程
1. 确定继承哪个基类（DataAnalysisPrompt 或 VizQLPrompt）
2. 实现 6 个标准部分（至少 ROLE, TASK, PRINCIPLES）
3. 运行 `validate()` 检查完整性
4. 编写测试用例
5. 与 v2 版本对比效果

### 2. 内容编写原则
- **ROLE**: 2-3 句话，清晰定位
- **TASK**: 列表形式，具体可执行
- **CONTEXT**: 提供充分信息，使用占位符
- **PRINCIPLES**: 原则而非规则，分层组织
- **CONSTRAINTS**: 明确边界，处理边缘情况
- **OUTPUT**: 质量标准，常见错误

### 3. 代码组织
- 一个文件一个 Prompt 类
- 提供预实例化的常量（如 `QUESTION_BOOST_PROMPT_V3`）
- 完整的 docstring
- 清晰的 `__all__` 导出

## 📚 参考资料

- [BettaFish 项目](https://github.com/example/bettafish) - 参考的优秀实践
- [Prompt Engineering Guide](https://www.promptingguide.ai/) - Prompt 工程指南
- [Pydantic Documentation](https://docs.pydantic.dev/) - 数据验证

## 🙏 致谢

感谢用户提出的宝贵建议，使得这个结构化模板系统得以实现。这个系统将大大提高 prompt 的可维护性和质量。

---

**实施日期**: 2024
**版本**: v3.0
**状态**: ✅ 已完成基础实施
