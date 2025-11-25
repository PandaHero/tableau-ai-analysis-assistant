# 设计文档

## 概述

本设计文档描述了如何修复 Tableau Assistant 系统中维度字段聚合逻辑错误的技术方案。核心问题是系统错误地为分组维度字段分配了聚合函数（如 COUNTD），导致生成的 VizQL 查询不符合 Tableau API 规范而失败。

## 架构

### 当前架构问题

```
用户问题: "各省份的销售额是多少？"
    ↓
问题理解Agent (Understanding Agent)
    ↓ 输出错误
    {
        "mentioned_dimensions": ["省份"],
        "dimension_aggregations": {"省份": "COUNTD"}  ❌ 错误！
    }
    ↓
任务规划Agent (Task Planner Agent)
    ↓ 传递错误
    {
        "dimension_intents": [{
            "technical_field": "pro_name",
            "aggregation": "COUNTD"  ❌ 错误！
        }]
    }
    ↓
查询构建器 (Query Builder)
    ↓ 生成错误查询
    {
        "fields": [{
            "fieldCaption": "pro_name",
            "function": "COUNTD"  ❌ 错误！导致查询失败
        }]
    }
    ↓
Tableau VizQL API ❌ 返回400错误
```

### 目标架构

```
用户问题: "各省份的销售额是多少？"
    ↓
问题理解Agent (Understanding Agent)
    ↓ 输出正确
    {
        "mentioned_dimensions": ["省份"],
        "dimension_aggregations": {}  ✅ 正确：分组维度无聚合
    }
    ↓
任务规划Agent (Task Planner Agent)
    ↓ 传递正确
    {
        "dimension_intents": [{
            "technical_field": "pro_name",
            "aggregation": None  ✅ 正确：无聚合
        }]
    }
    ↓
查询构建器 (Query Builder)
    ↓ 生成正确查询
    {
        "fields": [{
            "fieldCaption": "pro_name"
            // ✅ 正确：无function属性
        }]
    }
    ↓
Tableau VizQL API ✅ 成功返回数据
```

## 组件和接口

### 1. 问题理解Agent (Understanding Agent)

**文件位置**: `tableau_assistant/src/agents/understanding_agent.py`

**当前问题**:
- LLM 错误地为所有维度字段设置聚合函数
- 没有区分"分组维度"和"被计数维度"
- 数据模型描述不清晰，Prompt缺少判断逻辑

**修复方案**:

基于主流LLM上下文最佳实践（Anthropic、OpenAI、Google Gemini），采用"Schema优先 + Prompt判断逻辑"的设计模式：
- **数据模型**：说明字段的用途和语义
- **Prompt**：提供可执行的判断步骤

#### 1.1 数据模型优化

**文件位置**: `tableau_assistant/src/models/question.py`

**当前定义**:
```python
dimension_aggregations: Optional[dict[str, str]] = Field(
    None,
    description="Aggregations for dimensions listed in mentioned_dimensions. Use COUNTD for 'count/number of X'. E.g., if mentioned_dimensions=['region','product'], then {'product': 'COUNTD'}"
)
```

**优化后**（基于LLM先验知识边界）:
```python
dimension_aggregations: Optional[dict[str, str]] = Field(
    None,
    description="""Maps dimension names to aggregation functions.

Usage:
- Include dimension → Dimension has SQL aggregation
- Exclude dimension → Dimension is for GROUP BY
- null or {} → All dimensions are for GROUP BY

Values: 'COUNTD' (count distinct values)"""
)

measure_aggregations: Optional[dict[str, str]] = Field(
    None,
    description="""Maps measure names to aggregation functions.

Usage:
- Include ALL measures with aggregation function

Values: 'SUM' (default), 'AVG', 'MIN', 'MAX', 'COUNT'"""
)
```

**设计原则**:
- ✅ 只列出可用值
- ✅ 标注默认值（'SUM' (default)）
- ✅ 解释特殊值（'COUNTD' - Tableau特有，需说明）
- ❌ 不解释通用值（SUM、AVG等LLM已知）

**关键改进**:
- ✅ 说明字段是什么
- ✅ 说明有哪些值可用
- ✅ 说明怎么用这些值（完整的使用规则）
- ✅ 提供使用示例
- ❌ 不包含判断逻辑

#### 1.2 get_role() 优化

**文件位置**: `tableau_assistant/prompts/understanding.py`

**修改部分**: `get_role()` 方法

**优化策略**（定义SQL角色）:

```python
def get_role(self) -> str:
    return """Query analyzer who determines SQL roles of entities.

SQL Roles:
- Dimension: Aggregated (COUNT/COUNTD) or Grouped (GROUP BY)
- Measure: Always aggregated (SUM/AVG/MIN/MAX)"""
```

#### 1.3 Prompt 优化

**文件位置**: `tableau_assistant/prompts/understanding.py`

**修改部分**: `get_specific_domain_knowledge()` 方法

**优化策略**（只包含判断逻辑）:

```python
def get_specific_domain_knowledge(self) -> str:
    return """Metadata: {metadata}

Entity role determination:

For each dimension:
- Analyze: Is dimension being counted/aggregated in query?
- Determine SQL role: Aggregated or Grouped

For each measure:
- Analyze: What aggregation is requested in query?
- Determine SQL aggregation function

Split decision:
[Keep existing content...]

Date expression:
[Keep existing content...]"""
```

**约束条件更新**: `get_constraints()` 方法

```python
def get_constraints(self) -> str:
    return """MUST NOT: invent entities, use technical names, split exploratory questions
MUST: extract ALL entities, use business terms, set needs_exploration=true for why/reason questions, determine SQL role for each entity"""
```

#### 1.4 输出验证和代码修复

**文件位置**: `tableau_assistant/src/agents/understanding_agent.py`

添加代码修复逻辑，防御性编程：

```python
def _fix_dimension_aggregations(self, result: QuestionUnderstanding) -> QuestionUnderstanding:
    """
    Auto-fix common dimension_aggregations errors
    
    Rule: If all dimensions have aggregations, likely incorrect
    """
    for sq in result.sub_questions:
        if not hasattr(sq, 'mentioned_dimensions') or not hasattr(sq, 'dimension_aggregations'):
            continue
            
        dims = sq.mentioned_dimensions
        aggs = sq.dimension_aggregations or {}
        
        # Detect: All dimensions have aggregations → Likely error
        if dims and len(aggs) == len(dims):
            logger.warning(
                f"Auto-fix: All dimensions have aggregations, clearing dimension_aggregations. "
                f"Dimensions: {dims}, Aggregations: {aggs}"
            )
            sq.dimension_aggregations = {}
    
    return result
```

在 `execute()` 方法中调用：

```python
async def execute(self, state, runtime, model_config=None, **kwargs):
    result = await super().execute(state, runtime, model_config, **kwargs)
    
    # Auto-fix dimension_aggregations
    if 'understanding' in result:
        result['understanding'] = self._fix_dimension_aggregations(result['understanding'])
    
    return result
```

### 2. 任务规划Agent (Task Planner Agent)

**文件位置**: `tableau_assistant/src/agents/task_planner_agent.py`

**当前问题**:
- 直接传递 Understanding Agent 的错误输出
- 没有验证 dimension_aggregations 的正确性

**修复方案**:

#### 2.1 Prompt 优化

**文件位置**: `tableau_assistant/prompts/task_planner.py`

**修改部分**: `get_specific_domain_knowledge()` 方法

**优化策略**（精炼的通用规则）:

```python
def get_specific_domain_knowledge(self) -> str:
    return """Resources: {original_question}, {sub_questions}, {metadata}, {dimension_hierarchy}

DimensionIntent.aggregation mapping:
For each dimension in mentioned_dimensions:
- Dimension IN dimension_aggregations → aggregation = dict value
- Dimension NOT IN dimension_aggregations → aggregation = null

Mapping rules:
1. technical_field MUST be exact field name from metadata.fields
2. Match category first using dimension_hierarchy
3. Match name similarity within category
4. Prefer coarse level unless fine detail needed
5. Use aggregation from dimension_aggregations (null if not present)"""
```

**约束条件更新**: `get_constraints()` 方法

```python
def get_constraints(self) -> str:
    return """MUST NOT: use non-existent fields, modify TimeRange, add TopN without keywords
MUST: one subtask per sub-question, match category first, use exact field names, set aggregation per dimension_aggregations dict"""
```

#### 2.2 代码逻辑验证

在 `_prepare_input_data` 方法中添加验证逻辑：

```python
def _prepare_input_data(self, state: VizQLState, **kwargs) -> Dict[str, Any]:
    # ... 现有代码 ...
    
    # 验证 dimension_aggregations 的正确性
    for sq in sub_questions_detailed:
        mentioned_dims = sq.get('mentioned_dimensions', [])
        dim_aggs = sq.get('dimension_aggregations') or {}
        
        # 警告：如果所有维度都有聚合，可能是错误的
        if mentioned_dims and len(dim_aggs) == len(mentioned_dims):
            logger.warning(
                f"可能的错误：所有维度都有聚合函数。"
                f"维度: {mentioned_dims}, 聚合: {dim_aggs}"
            )
    
    # ... 继续现有代码 ...
```

### 3. 查询构建器 (Query Builder)

**文件位置**: `tableau_assistant/src/components/query_builder.py`

**当前问题**:
- 可能没有正确处理 `aggregation=None` 的情况
- 可能为所有维度都添加了 function 属性

**修复方案**:

#### 3.1 字段构建逻辑

需要确保查询构建器正确处理 DimensionIntent：

```python
def _build_dimension_field(self, intent: DimensionIntent) -> Union[BasicField, FunctionField]:
    """
    构建维度字段
    
    规则：
    - 如果 intent.aggregation 为 None，返回 BasicField（无function）
    - 如果 intent.aggregation 有值，返回 FunctionField（有function）
    """
    if intent.aggregation is None:
        # 分组维度：不添加 function
        return BasicField(
            fieldCaption=intent.technical_field,
            fieldAlias=intent.business_term if intent.business_term != intent.technical_field else None,
            sortDirection=intent.sort_direction,
            sortPriority=intent.sort_priority
        )
    else:
        # 被计数维度：添加 function
        return FunctionField(
            fieldCaption=intent.technical_field,
            function=intent.aggregation,  # COUNTD
            fieldAlias=intent.business_term if intent.business_term != intent.technical_field else None,
            sortDirection=intent.sort_direction,
            sortPriority=intent.sort_priority
        )
```

#### 3.2 验证逻辑

添加查询验证，确保生成的 VizQL 符合规范：

```python
def _validate_query(self, query: VizQLQuery) -> None:
    """
    验证生成的 VizQL 查询
    
    检查：
    1. 分组维度字段不应有 function 属性
    2. 度量字段必须有 function 属性
    """
    for field in query.fields:
        field_dict = field.model_dump(exclude_none=True)
        field_caption = field_dict.get('fieldCaption')
        has_function = 'function' in field_dict
        
        # 根据元数据判断字段类型
        field_meta = self.metadata.get_field_by_name(field_caption)
        if field_meta:
            if field_meta.role == 'dimension' and has_function:
                # 检查是否是合法的维度聚合（COUNTD、MIN、MAX）
                func = field_dict.get('function')
                if func not in ['COUNTD', 'MIN', 'MAX']:
                    logger.warning(
                        f"维度字段 {field_caption} 有不合法的聚合函数: {func}"
                    )
            elif field_meta.role == 'measure' and not has_function:
                logger.error(
                    f"度量字段 {field_caption} 缺少聚合函数"
                )
                raise ValueError(f"度量字段必须有聚合函数: {field_caption}")
```

## 数据模型

### QuerySubQuestion (问题理解输出)

```python
class QuerySubQuestion(SubQuestionBase):
    mentioned_dimensions: List[str]  # 所有维度（包括分组和被计数）
    dimension_aggregations: Optional[dict[str, str]]  # 只包含被计数维度
    mentioned_measures: List[str]  # 所有度量
    measure_aggregations: Optional[dict[str, str]]  # 所有度量的聚合
```

**关键规则**:
- `dimension_aggregations` 为空字典 `{}` 或 `None` 表示所有维度都是分组维度
- `dimension_aggregations` 只包含需要计数的维度

### DimensionIntent (任务规划输出)

```python
class DimensionIntent(BaseModel):
    business_term: str
    technical_field: str
    field_data_type: str
    aggregation: Optional[Literal["COUNT", "COUNTD", "MIN", "MAX"]]  # 可选
```

**关键规则**:
- `aggregation=None` 表示分组维度（无聚合）
- `aggregation="COUNTD"` 表示被计数维度（有聚合）

### VizQL Field (查询构建输出)

```python
# 分组维度 → BasicField
{
    "fieldCaption": "pro_name"
    # 无 function 属性
}

# 被计数维度 → FunctionField
{
    "fieldCaption": "门店编码",
    "function": "COUNTD"
}

# 度量 → FunctionField
{
    "fieldCaption": "收入",
    "function": "SUM"
}
```

## 错误处理

### 1. LLM 输出验证

在 `BaseVizQLAgent._execute_with_prompt` 中添加验证：

```python
async def _execute_with_prompt(self, input_data, runtime, model_config):
    # ... 现有代码 ...
    
    try:
        result = output_model.model_validate_json(cleaned_content)
        
        # 额外验证：检查 dimension_aggregations
        if hasattr(result, 'sub_questions'):
            for sq in result.sub_questions:
                if hasattr(sq, 'dimension_aggregations'):
                    self._validate_dimension_aggregations(sq)
        
        return result
    except ValidationError as e:
        # ... 现有错误处理 ...
```

### 2. 查询执行前验证

在 `QueryExecutor.execute_query` 中添加验证：

```python
def execute_query(self, query: VizQLQuery, ...):
    # 验证查询结构
    self._validate_vizql_query(query)
    
    # ... 继续执行 ...

def _validate_vizql_query(self, query: VizQLQuery):
    """验证 VizQL 查询是否符合规范"""
    for field in query.fields:
        field_dict = field.model_dump(exclude_none=True)
        
        # 检查是否有不合理的 function
        if 'function' in field_dict:
            func = field_dict['function']
            field_caption = field_dict['fieldCaption']
            
            # 如果是维度字段，只允许 COUNTD、MIN、MAX
            # 如果是度量字段，必须有聚合函数
            # ... 验证逻辑 ...
```

## 测试策略

### 1. 单元测试

#### 1.1 Understanding Agent 测试

**文件**: `tableau_assistant/tests/test_understanding_agent.py`

```python
def test_grouping_dimension_no_aggregation():
    """测试：分组维度不应有聚合函数"""
    question = "各省份的销售额是多少？"
    result = understanding_agent.execute(question)
    
    assert "省份" in result.mentioned_dimensions
    assert result.dimension_aggregations == {} or result.dimension_aggregations is None

def test_counted_dimension_has_aggregation():
    """测试：被计数维度应有COUNTD聚合"""
    question = "每个省份有多少个门店？"
    result = understanding_agent.execute(question)
    
    assert "省份" in result.mentioned_dimensions
    assert "门店" in result.mentioned_dimensions
    assert result.dimension_aggregations.get("门店") == "COUNTD"
    assert "省份" not in result.dimension_aggregations
```

#### 1.2 Task Planner Agent 测试

**文件**: `tableau_assistant/tests/test_task_planner_agent.py`

```python
def test_dimension_intent_without_aggregation():
    """测试：分组维度的Intent不应有aggregation"""
    understanding = {
        "mentioned_dimensions": ["省份"],
        "dimension_aggregations": {}
    }
    result = task_planner_agent.execute(understanding)
    
    dim_intent = result.subtasks[0].dimension_intents[0]
    assert dim_intent.aggregation is None

def test_dimension_intent_with_aggregation():
    """测试：被计数维度的Intent应有aggregation"""
    understanding = {
        "mentioned_dimensions": ["省份", "门店"],
        "dimension_aggregations": {"门店": "COUNTD"}
    }
    result = task_planner_agent.execute(understanding)
    
    # 找到门店的Intent
    store_intent = next(
        i for i in result.subtasks[0].dimension_intents 
        if i.business_term == "门店"
    )
    assert store_intent.aggregation == "COUNTD"
```

#### 1.3 Query Builder 测试

**文件**: `tableau_assistant/tests/test_query_builder.py`

```python
def test_build_field_without_function():
    """测试：分组维度生成的字段不应有function"""
    intent = DimensionIntent(
        business_term="省份",
        technical_field="pro_name",
        field_data_type="STRING",
        aggregation=None
    )
    
    field = query_builder._build_dimension_field(intent)
    field_dict = field.model_dump(exclude_none=True)
    
    assert 'function' not in field_dict
    assert field_dict['fieldCaption'] == "pro_name"

def test_build_field_with_function():
    """测试：被计数维度生成的字段应有function"""
    intent = DimensionIntent(
        business_term="门店",
        technical_field="门店编码",
        field_data_type="STRING",
        aggregation="COUNTD"
    )
    
    field = query_builder._build_dimension_field(intent)
    field_dict = field.model_dump(exclude_none=True)
    
    assert field_dict['function'] == "COUNTD"
    assert field_dict['fieldCaption'] == "门店编码"
```

### 2. 集成测试

**文件**: `tableau_assistant/tests/test_complete_pipeline.py`

使用现有的测试用例，验证修复后的完整流程：

```python
# 场景1：简单分组查询
test_case = {
    "id": "simple_grouping",
    "question": "各省份的销售额是多少？",
    "expected_vizql": {
        "fields": [
            {"fieldCaption": "pro_name"},  # 无function
            {"fieldCaption": "收入", "function": "SUM"}
        ]
    }
}

# 场景2：计数查询
test_case = {
    "id": "count_query",
    "question": "每个省份有多少个门店？",
    "expected_vizql": {
        "fields": [
            {"fieldCaption": "pro_name"},  # 分组维度，无function
            {"fieldCaption": "门店编码", "function": "COUNTD"}  # 被计数维度，有function
        ]
    }
}
```

### 3. 回归测试

确保修复不会破坏现有功能：

1. 运行所有现有测试用例
2. 验证之前失败的测试现在能通过
3. 验证之前通过的测试仍然通过

## 性能考虑

### 1. Prompt 长度

添加详细的示例会增加 Prompt 长度，可能影响：
- LLM 推理时间
- Token 消耗

**优化方案**:
- 使用精简的示例
- 只在必要时包含详细说明
- 考虑使用 Few-shot learning

### 2. 验证开销

添加验证逻辑会增加处理时间：
- Understanding Agent 输出验证
- Task Planner Agent 输入验证
- Query Builder 查询验证

**优化方案**:
- 只在开发/测试环境启用详细验证
- 生产环境使用轻量级验证
- 使用日志记录而不是抛出异常

## 部署计划

### 阶段1：Prompt 优化（低风险）

1. 更新 Understanding Agent Prompt
2. 更新 Task Planner Agent Prompt
3. 运行测试验证

### 阶段2：代码逻辑修复（中风险）

1. 修复 Query Builder 的字段构建逻辑
2. 添加验证逻辑
3. 运行完整测试套件

### 阶段3：生产部署（高风险）

1. 在测试环境验证
2. 灰度发布（10% 流量）
3. 监控错误率和查询成功率
4. 逐步扩大到100%

## 监控和日志

### 关键指标

1. **查询成功率**
   - 修复前后对比
   - 按查询类型分组

2. **维度聚合错误率**
   - 检测到的错误数量
   - 自动修复的数量

3. **LLM 输出质量**
   - dimension_aggregations 为空的比例
   - 需要人工干预的比例

### 日志记录

```python
# Understanding Agent
logger.info(f"维度识别: {mentioned_dimensions}")
logger.info(f"维度聚合: {dimension_aggregations}")
if dimension_aggregations and len(dimension_aggregations) == len(mentioned_dimensions):
    logger.warning("可能的错误：所有维度都有聚合")

# Task Planner Agent
logger.info(f"生成 DimensionIntent: {dim_intent}")
if dim_intent.aggregation is None:
    logger.debug(f"分组维度: {dim_intent.technical_field}")
else:
    logger.debug(f"被计数维度: {dim_intent.technical_field} ({dim_intent.aggregation})")

# Query Builder
logger.info(f"生成 VizQL 字段: {field_dict}")
if 'function' not in field_dict:
    logger.debug(f"分组字段: {field_dict['fieldCaption']}")
```

## 回滚计划

如果修复导致问题：

1. **立即回滚 Prompt**
   - 恢复到之前的版本
   - 重启服务

2. **回滚代码更改**
   - Git revert
   - 重新部署

3. **数据修复**
   - 检查是否有缓存的错误结果
   - 清除相关缓存

## 未来改进

1. **自动学习**
   - 收集用户反馈
   - 优化 Prompt 示例

2. **智能验证**
   - 使用机器学习检测异常模式
   - 自动建议修复

3. **性能优化**
   - 缓存常见查询模式
   - 减少验证开销
