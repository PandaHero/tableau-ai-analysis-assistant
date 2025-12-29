# React 模式重新设计方案（生产级）

## 问题分析

当前 React 模式的问题：
1. **角色定位错误** - 只是"错误分析专家"，不了解 VizQL 能力
2. **与 Step1/Step2 断裂** - 只能被动分析，不能主动指导
3. **缺少修正能力** - 只能 RETRY，不能直接 CORRECT
4. **领域知识缺失** - 不知道表计算可以覆盖派生度量等
5. **使用规则匹配** - 不够智能，无法处理复杂情况

## 设计原则

1. **完全用 LLM 处理错误** - 不用规则匹配，让 LLM 理解错误并决策
2. **角色升级为指导者** - 不只是分析错误，而是指导整个语义理解流程
3. **支持直接修正** - 对于简单问题，直接修正输出而不是重试
4. **符合 Prompt/Schema 规范** - 遵循规范文档的职责边界

---

## 新设计

### 1. 角色升级

从"错误分析专家"升级为"VizQL 语义理解指导专家"：

```python
def get_role(self) -> str:
    return """VizQL semantic understanding supervisor and error recovery expert.

Expertise: 
- VizQL query capabilities (table calculations, LOD expressions)
- Semantic parsing error diagnosis and correction
- Guiding Step1/Step2 to produce correct, executable output

Background:
- VizQL supports table calculations that can derive measures from base measures
- PERCENT_DIFFERENCE can compute YoY/MoM growth from a single base measure
- LOD expressions (FIXED/INCLUDE/EXCLUDE) change aggregation granularity
- Each field_name in a query must be unique
"""
```

### 2. Action 类型

```python
class ReActActionType(str, Enum):
    """React action types.
    
    <rule>
    CORRECT: Can directly fix the output without re-running LLM
      → Duplicate measures, simple field fixes
    RETRY: Need LLM to re-think with new guidance
      → Logic errors, missing information
    CLARIFY: Need user input to proceed
      → Ambiguous fields, unclear intent
    ABORT: Cannot recover, explain to user
      → Permission denied, data not available
    </rule>
    """
    CORRECT = "correct"    # 直接修正输出
    RETRY = "retry"        # 重试某个步骤（带指导）
    CLARIFY = "clarify"    # 向用户询问
    ABORT = "abort"        # 放弃
```

### 3. Correction 模型

```python
class CorrectionOperation(str, Enum):
    """Correction operation types.
    
    <rule>
    REMOVE_DUPLICATE_MEASURES: Remove measures with same field_name, keep base only
    REPLACE_FIELD: Replace a field reference with correct one
    REMOVE_FIELD: Remove a field from list
    ADD_FIELD: Add a field to list
    UPDATE_VALUE: Update a specific value
    </rule>
    """
    REMOVE_DUPLICATE_MEASURES = "remove_duplicate_measures"
    REPLACE_FIELD = "replace_field"
    REMOVE_FIELD = "remove_field"
    ADD_FIELD = "add_field"
    UPDATE_VALUE = "update_value"


class Correction(BaseModel):
    """Direct correction to Step1/Step2 output.
    
    <fill_order>
    1. target_step
    2. target_path
    3. operation
    4. reason
    5. corrected_value (if needed)
    </fill_order>
    """
    target_step: Literal["step1", "step2"] = Field(
        description="""<what>Which step's output to correct</what>
<when>ALWAYS</when>"""
    )
    
    target_path: str = Field(
        description="""<what>JSON path to the field to correct</what>
<when>ALWAYS</when>
<examples>what.measures, where.dimensions, computations[0].partition_by</examples>"""
    )
    
    operation: CorrectionOperation = Field(
        description="""<what>Type of correction operation</what>
<when>ALWAYS</when>"""
    )
    
    reason: str = Field(
        description="""<what>Why this correction is needed</what>
<when>ALWAYS</when>"""
    )
    
    corrected_value: Any = Field(
        default=None,
        description="""<what>The corrected value to use</what>
<when>For REPLACE_FIELD, ADD_FIELD, UPDATE_VALUE operations</when>"""
    )
```

### 4. 领域知识（Prompt）

只放"如何思考"，不放具体规则：

```python
def get_specific_domain_knowledge(self) -> str:
    return """**VizQL Query Execution Model**
Query = Step1(semantic) → Step2(computation) → map_fields → build_query → execute

**Think step by step:**
Step 1: Identify error source (which step caused the error?)
Step 2: Understand error semantics (what does the error mean?)
Step 3: Determine root cause (why did this happen?)
Step 4: Decide action type:
  - Can I directly fix the output? → CORRECT
  - Does LLM need to re-think? → RETRY with guidance
  - Need user clarification? → CLARIFY
  - Cannot recover? → ABORT
Step 5: Generate specific correction or guidance

**Error Source Analysis**
- execute_query error → Usually build_query or earlier step issue
- build_query error → Usually Step2 computation design issue
- map_fields error → Field reference issue
- step1/step2 error → Semantic understanding issue

**VizQL Constraints**
- Each field_name must be unique in query
- Table calculations derive from base measures (no need for duplicate measures)
- LOD dimensions must exist in data source
- Partition dimensions must be subset of query dimensions
"""
```

### 5. 错误类型（Schema）

放在模型的 `<rule>` 中：

```python
class ErrorCategory(str, Enum):
    """Error category for diagnosis.
    
    <rule>
    DUPLICATE_FIELD: Same field_name appears multiple times
      → CORRECT: remove duplicates
    FIELD_NOT_FOUND: Referenced field doesn't exist
      → RETRY map_fields or ABORT
    INVALID_COMPUTATION: Computation logic error
      → RETRY step2 with guidance
    TYPE_MISMATCH: Data type incompatibility
      → RETRY step1 or step2
    PERMISSION_DENIED: Access denied
      → ABORT
    TIMEOUT: Query timeout
      → ABORT or simplify query
    UNKNOWN: Cannot determine
      → RETRY or ABORT
    </rule>
    """
    DUPLICATE_FIELD = "duplicate_field"
    FIELD_NOT_FOUND = "field_not_found"
    INVALID_COMPUTATION = "invalid_computation"
    TYPE_MISMATCH = "type_mismatch"
    PERMISSION_DENIED = "permission_denied"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"
```

### 6. 完整的 ReActOutput 模型

```python
class ReActThought(BaseModel):
    """LLM's analysis of the error.
    
    <fill_order>
    1. error_source (which step)
    2. error_category (what type)
    3. root_cause_analysis (why)
    4. can_correct (directly fixable?)
    5. can_retry (worth retrying?)
    6. needs_clarification (need user?)
    7. reasoning (decision explanation)
    </fill_order>
    """
    error_source: str = Field(
        description="""<what>Which step caused the error</what>
<when>ALWAYS</when>
<values>step1, step2, map_fields, build_query, execute_query</values>"""
    )
    
    error_category: ErrorCategory = Field(
        description="""<what>Category of the error</what>
<when>ALWAYS</when>"""
    )
    
    root_cause_analysis: str = Field(
        description="""<what>Deep analysis of why this error occurred</what>
<when>ALWAYS</when>"""
    )
    
    can_correct: bool = Field(
        description="""<what>Whether error can be fixed by direct correction</what>
<when>ALWAYS</when>
<rule>True if output can be fixed without re-running LLM</rule>"""
    )
    
    can_retry: bool = Field(
        description="""<what>Whether retrying with guidance could fix the error</what>
<when>ALWAYS</when>
<rule>True if LLM re-thinking could produce correct output</rule>"""
    )
    
    needs_clarification: bool = Field(
        description="""<what>Whether user clarification is needed</what>
<when>ALWAYS</when>
<rule>True if error is due to ambiguous user input</rule>"""
    )
    
    reasoning: str = Field(
        description="""<what>Step-by-step reasoning for the decision</what>
<when>ALWAYS</when>"""
    )


class ReActAction(BaseModel):
    """LLM's decision on what to do.
    
    <fill_order>
    1. action_type (ALWAYS)
    2. corrections (if CORRECT)
    3. retry_from, retry_guidance (if RETRY)
    4. clarification_question (if CLARIFY)
    5. user_message (if ABORT)
    </fill_order>
    """
    action_type: ReActActionType = Field(
        description="""<what>Action to take</what>
<when>ALWAYS</when>"""
    )
    
    # CORRECT
    corrections: list[Correction] | None = Field(
        default=None,
        description="""<what>List of corrections to apply</what>
<when>action_type = CORRECT</when>
<dependency>Required for CORRECT</dependency>"""
    )
    
    # RETRY
    retry_from: str | None = Field(
        default=None,
        description="""<what>Which step to retry from</what>
<when>action_type = RETRY</when>
<values>step1, step2, map_fields, build_query</values>"""
    )
    
    retry_guidance: str | None = Field(
        default=None,
        description="""<what>Specific guidance for the retry</what>
<when>action_type = RETRY</when>
<rule>Must be specific and actionable, in Chinese</rule>"""
    )
    
    # CLARIFY
    clarification_question: str | None = Field(
        default=None,
        description="""<what>Question to ask user</what>
<when>action_type = CLARIFY</when>
<rule>Must be clear and specific, in Chinese</rule>"""
    )
    
    # ABORT
    user_message: str | None = Field(
        default=None,
        description="""<what>Message to show user</what>
<when>action_type = ABORT</when>
<rule>Must be helpful and suggest alternatives, in Chinese</rule>"""
    )
```

---

## 工作流程

```
Error → React LLM
         │
         ├─ Thought: 分析错误源、类别、根因
         │
         └─ Action:
              ├─ CORRECT → 直接修正 Step1/Step2 输出 → 继续执行
              ├─ RETRY → 带指导重试指定步骤 → 重新执行
              ├─ CLARIFY → 向用户提问 → 等待用户输入
              └─ ABORT → 返回错误消息给用户
```

---

## 实现文件

1. `models/react.py` - 更新模型定义
2. `prompts/react_error.py` - 更新 Prompt
3. `components/react_error_handler.py` - 更新处理逻辑，支持 CORRECT action

---

## 预期效果

### Case 1: Duplicate Measures

**错误**: "Field Sales isn't unique"

**React 分析**:
- error_source: build_query
- error_category: DUPLICATE_FIELD
- root_cause: Step1 输出了两个 Sales 度量
- can_correct: True

**React 决策**:
- action_type: CORRECT
- corrections: [{target_step: "step1", target_path: "what.measures", operation: REMOVE_DUPLICATE_MEASURES}]

**结果**: 直接修正，继续执行

### Case 2: Field Not Found

**错误**: "Unknown field 'Revenue'"

**React 分析**:
- error_source: map_fields
- error_category: FIELD_NOT_FOUND
- root_cause: 用户说的"收入"映射到了不存在的 Revenue
- can_correct: False
- can_retry: True

**React 决策**:
- action_type: RETRY
- retry_from: map_fields
- retry_guidance: "字段 'Revenue' 不存在，请检查是否应该映射到 'Sales' 或其他字段"

**结果**: 重试 map_fields

### Case 3: Permission Denied

**错误**: "Access denied to datasource"

**React 分析**:
- error_source: execute_query
- error_category: PERMISSION_DENIED
- can_correct: False
- can_retry: False

**React 决策**:
- action_type: ABORT
- user_message: "抱歉，您没有访问该数据源的权限。请联系管理员获取权限。"

**结果**: 返回错误消息给用户
