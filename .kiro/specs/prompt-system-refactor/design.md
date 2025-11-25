# Design Document

## Overview

本设计文档描述了 Tableau Assistant Prompt 系统的重构方案。通过参考 BettaFish 项目和业界最佳实践，我们将建立一个清晰、可维护、高效的 prompt 架构，解决当前系统中的冗余、数据模型不一致和职责不清等问题。

### 设计目标

1. **清晰的架构**：建立统一的 Prompt 基类和 Agent 基类
2. **数据模型一致性**：严格遵守 Pydantic 模型定义
3. **职责分离**：明确各 Agent 的职责边界
4. **通用性**：避免硬编码规则，提高适应性
5. **可维护性**：简洁的 prompt 模板，易于理解和修改

### 核心设计原则

1. **Schema-Driven**: 使用 JSON Schema 自动约束输出格式
2. **Principle-Based**: 用原则而非规则指导 LLM
3. **Context-Rich**: 提供充分的上下文信息而非硬编码映射
4. **Separation of Concerns**: 清晰的职责分离
5. **Fail-Fast**: 早期验证，快速失败

## Architecture

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     Metadata Manager                         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Dimension Hierarchy Inference (Pre-processing)      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Agent Pipeline                          │
│                                                               │
│  ┌────────────────┐    ┌────────────────┐    ┌───────────┐ │
│  │ Question Boost │───▶│ Understanding  │───▶│   Task    │ │
│  │     Agent      │    │     Agent      │    │  Planner  │ │
│  └────────────────┘    └────────────────┘    └───────────┘ │
│         │                      │                     │       │
│         ▼                      ▼                     ▼       │
│  Business Terms        Business Terms        Technical      │
│                                               Field Names    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Base Infrastructure                       │
│                                                               │
│  ┌──────────────┐         ┌──────────────┐                  │
│  │  BasePrompt  │         │  BaseAgent   │                  │
│  │              │         │              │                  │
│  │ - get_system │         │ - execute()  │                  │
│  │ - get_user   │         │ - prepare()  │                  │
│  │ - get_model  │         │ - process()  │                  │
│  └──────────────┘         └──────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

### 数据流

```
User Question
     │
     ▼
[Metadata + Dimension Hierarchy] ──┐
     │                              │
     ▼                              │
Question Boost Agent                │
     │ (Business Terms)             │
     ▼                              │
Understanding Agent                 │
     │ (Business Terms)             │
     ▼                              │
Task Planner Agent ◀────────────────┘
     │ (Technical Fields)
     ▼
VizQL Query Specs
```



## Components and Interfaces

### 1. Base Prompt System

#### BasePrompt Class

```python
from abc import ABC, abstractmethod
from typing import Type, Dict, Any
from pydantic import BaseModel
import json

class BasePrompt(ABC):
    """Base class for all prompts with automatic JSON Schema injection"""
    
    @abstractmethod
    def get_system_message(self) -> str:
        """Get the system message defining role and core instructions"""
        pass
    
    @abstractmethod
    def get_user_template(self) -> str:
        """Get the user message template with placeholders"""
        pass
    
    @abstractmethod
    def get_output_model(self) -> Type[BaseModel]:
        """Get the Pydantic model for output validation"""
        pass
    
    def get_schema_instruction(self) -> str:
        """Get JSON Schema instruction (can be overridden)"""
        return """
## Output Format

You must output valid JSON that strictly follows this schema:

```json
{json_schema}
```

**Critical Requirements:**
- Output must be valid JSON (no markdown code blocks)
- All required fields must be present
- Field types must match exactly
- No additional fields beyond schema definition
"""
    
    def format_messages(self, **kwargs) -> list:
        """Format messages for LLM with automatic schema injection"""
        # Generate JSON schema
        output_model = self.get_output_model()
        json_schema = output_model.model_json_schema()
        
        # Add schema to kwargs
        kwargs_with_schema = {
            **kwargs,
            "json_schema": json.dumps(json_schema, indent=2, ensure_ascii=False)
        }
        
        # Build system message
        system_content = self.get_system_message() + self.get_schema_instruction()
        
        # Build user message
        user_content = self.get_user_template().format(**kwargs_with_schema)
        
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]
```

**设计要点**：
- 自动注入 JSON Schema，无需手动维护
- 可覆盖 `get_schema_instruction()` 自定义 Schema 说明
- 使用 `format_messages()` 统一消息格式

#### VizQLPrompt Class

```python
class VizQLPrompt(BasePrompt):
    """Base class for VizQL-specific prompts"""
    
    def get_vizql_context(self) -> str:
        """Get VizQL capabilities context (can be overridden)"""
        return """
## VizQL Query Capabilities

**Supported Operations:**
- SELECT fields (dimensions and measures)
- WHERE filters (categorical, numerical, date)
- GROUP BY dimensions
- ORDER BY with direction and priority
- TOP N filtering
- Basic aggregations (SUM, AVG, COUNT, COUNTD, MIN, MAX)
- Date functions (YEAR, QUARTER, MONTH, WEEK, DAY)

**Not Supported:**
- Table-level calculations (PREVIOUS, LOOKUP, WINDOW functions)
- Complex joins or subqueries
- Advanced statistical functions
"""
```

**设计要点**：
- 提供 VizQL 能力的通用描述
- 子类可以覆盖或扩展此方法


### 2. Agent Base Class

#### BaseVizQLAgent Class

```python
from typing import Dict, Any
from tableau_assistant.src.utils.streaming import invoke_with_streaming
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.core.runtime import Runtime
from tableau_assistant.prompts.base import BasePrompt

class BaseVizQLAgent:
    """Base class for VizQL agents with clean prompt integration"""
    
    def __init__(self, prompt: BasePrompt):
        self.prompt = prompt
    
    async def execute(
        self,
        state: VizQLState,
        runtime: Runtime,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute agent with streaming output"""
        # Get LLM
        llm = runtime.context.llm_manager.get_llm("gpt-4o-mini")
        
        # Prepare input data
        input_data = self._prepare_input_data(state, **kwargs)
        
        # Execute with streaming
        result = await invoke_with_streaming(
            prompt=self.prompt,
            llm=llm,
            input_data=input_data,
            output_model=self.prompt.get_output_model(),
            show_tokens=True
        )
        
        # Process result
        return self._process_result(result, state)
    
    def _prepare_input_data(self, state: VizQLState, **kwargs) -> Dict[str, Any]:
        """Prepare input data for the prompt - override in subclasses"""
        return kwargs
    
    def _process_result(self, result: Any, state: VizQLState) -> Dict[str, Any]:
        """Process the result - override in subclasses"""
        return {"result": result}
```

**设计要点**：
- 统一的执行流程：prepare → execute → process
- 自动使用 streaming 输出
- 子类只需实现 `_prepare_input_data` 和 `_process_result`

### 3. Prompt Implementations

#### Question Boost Prompt

```python
from typing import Type
from pydantic import BaseModel
from .base import BasePrompt
from ..src.models.boost import QuestionBoost

class QuestionBoostPrompt(BasePrompt):
    """Clean, focused prompt for question enhancement"""
    
    def get_system_message(self) -> str:
        return """# Role
You are a business data analyst who transforms vague questions into precise, analyzable queries.

# Task
Enhance the user's question to make it:
1. **Specific**: Add missing time ranges, dimensions, and measures
2. **Actionable**: Focus on business insights, not just data display
3. **Structured**: Clear what to analyze and how to compare

# Enhancement Principles
- Add time context when missing (default: "recent period")
- Specify dimensions and measures explicitly
- Add comparison or trend analysis when valuable
- Use business terminology, not technical field names
- Maintain the original intent while adding analytical value

# Available Data Context
{metadata}"""
    
    def get_user_template(self) -> str:
        return """Original Question: "{question}"

Enhance this question to be more specific and analytically valuable while preserving the original intent."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return QuestionBoost
```

**设计特点**：
- 简洁的角色定义
- 清晰的任务描述
- 原则而非规则
- 使用业务术语
- 不涉及技术字段映射


#### Understanding Prompt

```python
from typing import Type
from pydantic import BaseModel
from .base import VizQLPrompt
from ..src.models.question import QuestionUnderstanding

class UnderstandingPrompt(VizQLPrompt):
    """Clean, focused prompt for question understanding"""
    
    def get_system_message(self) -> str:
        return """# Role
You are a VizQL query analyst who decomposes business questions into executable data queries.

# Task
Analyze the enhanced question and:
1. **Decompose** into sub-questions that VizQL can answer
2. **Identify** relationships between sub-questions
3. **Extract** dimensions, measures, filters, and constraints
4. **Classify** question type and complexity

# Key Principles
- Each sub-question must be answerable by a single VizQL query
- For comparisons: create separate queries for each time period/dimension
- For breakdowns: separate total vs. parts queries
- Use business terms, not technical field names

# Sub-Question Relationships
- **comparison**: Different time periods or dimension values of same metric
- **breakdown**: Total vs. parts (for percentages/ratios)
- **drill_down**: Different granularity levels
- **independent**: Unrelated analyses

{vizql_context}

# Available Metadata
{metadata}"""
    
    def get_user_template(self) -> str:
        return """Enhanced Question: "{question}"

Analyze this question and decompose it into VizQL-executable sub-questions with their relationships."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return QuestionUnderstanding
    
    def format_messages(self, **kwargs) -> list:
        """Override to inject VizQL context"""
        kwargs['vizql_context'] = self.get_vizql_context()
        return super().format_messages(**kwargs)
```

**设计特点**：
- 专注于问题理解和拆分
- 明确子问题关系类型
- 基于 VizQL 能力判断拆分
- 使用业务术语
- 不涉及技术字段映射
- 特殊处理探索性问题（含"为什么"）：不拆分，标记 needs_exploration=true


#### Task Planner Prompt

```python
from typing import Type
from pydantic import BaseModel
from .base import VizQLPrompt
from ..src.models.query_plan import QueryPlanningResult

class TaskPlannerPrompt(VizQLPrompt):
    """Clean, focused prompt for VizQL query planning"""
    
    def get_system_message(self) -> str:
        return """# Role
You are a VizQL query generator who converts sub-questions into executable query specifications.

# Task
For each sub-question, generate a VizQL query specification with:
1. **Fields**: Correct field names from metadata with proper types
2. **Filters**: Appropriate date, categorical, or numerical filters
3. **Dependencies**: Proper sequencing for related queries

# Field Selection Principles
- **Semantic Matching**: Match business terms to technical fields based on:
  * Field caption similarity
  * Category alignment (产品 → category="产品")
  * Data type appropriateness
  * Context relevance
- **Granularity Selection**: Use dimension_hierarchy to choose appropriate level:
  * Prefer level 1-2 (coarse) for overview analysis
  * Avoid level 5 (fine) unless specifically required
  * Consider unique_count to avoid high-cardinality fields
- **Measure Selection**: Choose aggregation based on:
  * Question intent (total vs. average)
  * Field semantics (revenue → SUM, rate → AVG)
  * Analysis context

# Field Type Rules (Critical)
- **BasicField** (dimensions): Only fieldCaption, sortDirection, sortPriority
- **FunctionField** (measures): Must have fieldCaption + function
- **CalculationField** (computed): Must have fieldCaption + calculation

# Filter Rules
- Date filters: Use dateRangeType (LASTN, LAST, etc.) with anchorDate for offsets
- Set filters: Only use when values are known (not for dependent queries)
- Range filters: Must have min/max values (auto-fill if missing)

{vizql_context}

# Available Data
Metadata: {metadata}
Dimension Hierarchy: {dimension_hierarchy}"""
    
    def get_user_template(self) -> str:
        return """Question Understanding Result:
{understanding}

Generate VizQL query specifications for each sub-question."""
    
    def get_output_model(self) -> Type[BaseModel]:
        return QueryPlanningResult
```

**设计特点**：
- 负责业务术语到技术字段的映射
- 基于原则的字段选择（语义匹配、粒度选择）
- 利用元数据信息（category、level、unique_count,）
- 明确的字段类型约束
- 完整的 VizQL 规格生成


## Data Models

### Metadata Structure

```python
{
    "fields": [
        {
            "fieldCaption": "分类一级名称",
            "dataType": "string",
            "role": "dimension",
            "category": "产品",
            "unique_count": 15,
            "sample_values": ["食品", "饮料", "日用品"]
        },
        {
            "fieldCaption": "收入",
            "dataType": "real",
            "role": "measure",
            "category": "财务",
            "aggregation": "sum"
        }
    ],
    "dimension_hierarchy": {
        "产品": [
            {
                "fieldCaption": "分类一级名称",
                "level": 1,
                "unique_count": 15,
                "parent": null
            },
            {
                "fieldCaption": "分类二级名称",
                "level": 2,
                "unique_count": 45,
                "parent": "分类一级名称"
            }
        ],
        "地理": [
            {
                "fieldCaption": "pro_name",
                "level": 1,
                "unique_count": 34,
                "parent": null
            }
        ]
    }
}
```

### State Flow

```python
# Initial State
{
    "original_question": "显示各地区各产品类别的销售额和利润",
    "metadata": {...},  # Pre-loaded with dimension_hierarchy
    "dimension_hierarchy": {...}  # Pre-loaded
}

# After Question Boost
{
    ...previous state,
    "boost_result": QuestionBoost(
        is_data_analysis_question=True,
        original_question="...",
        boosted_question="...",
        changes=[...],
        reasoning="...",
        confidence=0.9
    )
}

# After Understanding
{
    ...previous state,
    "understanding": QuestionUnderstanding(
        original_question="...",
        sub_questions=["..."],
        sub_question_relationships=[...],
        question_type=["对比"],
        mentioned_dimensions=["地区", "产品类别"],
        mentioned_metrics=["销售额", "利润"],
        ...
    )
}

# After Task Planning
{
    ...previous state,
    "query_plan": QueryPlanningResult(
        subtasks=[...],
        reasoning="...",
        complexity="Medium",
        estimated_rows=1000
    )
}
```



## Error Handling

### Validation Strategy

```python
# 1. Schema Validation (Automatic)
try:
    result = output_model.model_validate_json(llm_output)
except ValidationError as e:
    # Pydantic automatically validates:
    # - Required fields presence
    # - Field types
    # - Constraints (min_length, ge, le, etc.)
    # - No extra fields (with extra="forbid")
    raise ValueError(f"LLM output does not conform to schema: {e}")

# 2. Business Logic Validation (Manual)
def validate_understanding(understanding: QuestionUnderstanding):
    """Validate business logic consnts"""
    # Check sub-question relationships
    if len(understanding.sub_questions) > 1:
        if not understanding.sub_question_relationships:
            raise ValueError("Multiple sub-questions must have relationships")
    
    # Check relationship indices
    for rel in understanding.sub_question_relationships:
        for idx in rel.question_indices:
            if idx >= len(understanding.sub_questions):
                raise ValueError(f"Invalid question index: {idx}")
    
    # Check comparison dimension
    if rel.relation_type == "comparison" and not rel.comparison_dimension:
        raise ValueError("Comparison relationship must specify dimension")

# 3. Field Mapping Validation
def validate_query_plan(plan: QueryPlanningResult, metadata: dict):
    """Validate field names against metadata"""
    valid_fields = {f["fieldCaption"] for f in metadata["fields"]}
    
    for subtask in plan.subtasks:
        for field in subtask.fields:
            if field.fieldCaption not in valid_fields:
                raise ValueError(
                    f"Unknown field: {field.fieldCaption}. "
                    f"Availablelid_fields}"
                )
```

### Error Recovery

```python
# Retry with clarific def execute_with_retry(agent, state, runtime, max_retries=2):
    """Execute agent with automatic retry on validation errors"""
    for attempt in range(max_retries):
        try:
            result = await agent.execute(state, runtime)
            # Validate result
            validate_result(result)
            return result
        except ValidationError as e:
            if attempt == max_retries - 1:
                raise
            # Add error feedback to state
            state['validation_error'] = str(e)
         te['retry_attempt'] = attempt + 1
```

