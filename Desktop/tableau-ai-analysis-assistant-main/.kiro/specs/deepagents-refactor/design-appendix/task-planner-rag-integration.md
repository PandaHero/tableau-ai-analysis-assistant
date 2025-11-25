# Task Planner与RAG集成设计

## 概述

本文档详细说明Task Planner Agent如何与RAG字段映射系统集成，实现从业务术语到技术字段的智能映射。

---

## 整体流程

```
Understanding Agent
  ↓ 输出: mentioned_dimensions, mentioned_measures, mentioned_date_fields
Task Planner Agent
  ├─ 1. 提取业务术语
  ├─ 2. 调用 semantic_map_fields 工具
  │    ├─ 向量检索 (FAISS)
  │    ├─ 历史映射检索 (PersistentStore)
  │    ├─ 配置文件提示 (YAML, 辅助)
  │    └─ LLM语义判断
  ├─ 3. 获取 FieldMappingResult
  └─ 4. 生成 Intent 模型
  ↓ 输出: QueryPlanningResult
Query Builder
```

---

## 详细设计

### 1. Task Planner Agent的调整

#### 原有流程（硬编码映射规则）

```python
# 旧版本：Prompt中包含映射规则
class TaskPlannerAgent:
    async def execute(self, state, runtime, model_config):
        understanding = state.get("understanding")
        metadata = state.get("metadata")
        
        # 准备输入数据（包含元数据）
        input_data = {
            "understanding": understanding,
            "metadata": metadata,  # 完整的元数据
            "dimension_hierarchy": dimension_hierarchy
        }
        
        # 调用LLM（Prompt中包含映射规则）
        result = await self._execute_with_prompt(input_data, runtime, model_config)
        
        return result
```

**Prompt中的映射规则**：
```
Step 1: For each business term, find technical field from metadata
- Match category first: Which category does this term belong to?
- Then match name: Search for fields within that category by name similarity
- Verify field existence: technical_field MUST be exact name from metadata.fields
```

**问题**：
- ❌ 映射规则硬编码在Prompt中
- ❌ LLM需要同时处理映射和Intent生成
- ❌ 无法利用向量检索和历史学习

#### 新流程（RAG辅助映射）

```python
# 新版本：使用RAG工具进行映射
class TaskPlannerAgent:
    async def execute(self, state, runtime, model_config):
        understanding = state.get("understanding")
        metadata = state.get("metadata")
        
        # 1. 提取业务术语
        business_terms = self._extract_business_terms(understanding)
        
        # 2. 调用RAG工具进行字段映射
        field_mapping_result = await self._call_semantic_mapping(
            business_terms=business_terms,
            question_context=understanding.original_question,
            metadata=metadata,
            datasource_luid=runtime.context.datasource_luid
        )
        
        # 3. 准备输入数据（包含映射结果）
        input_data = {
            "understanding": understanding,
            "field_mappings": field_mapping_result,  # ⭐ 映射结果
            "metadata": metadata  # 仍然需要，用于验证
        }
        
        # 4. 调用LLM（Prompt专注于Intent生成）
        result = await self._execute_with_prompt(input_data, runtime, model_config)
        
        return result
    
    def _extract_business_terms(self, understanding) -> List[str]:
        """从understanding中提取所有业务术语"""
        terms = []
        for sq in understanding.sub_questions:
            terms.extend(sq.mentioned_dimensions or [])
            terms.extend(sq.mentioned_measures or [])
            terms.extend(sq.mentioned_date_fields or [])
        return list(set(terms))  # 去重
    
    async def _call_semantic_mapping(
        self,
        business_terms: List[str],
        question_context: str,
        metadata: Metadata,
        datasource_luid: str
    ) -> FieldMappingResult:
        """调用RAG工具进行字段映射"""
        # 调用semantic_map_fields工具
        result = await semantic_map_fields(
            business_terms=business_terms,
            question_context=question_context,
            metadata=metadata,
            datasource_luid=datasource_luid
        )
        return result
```

**新Prompt（专注于Intent生成）**：
```
Resources: {understanding}, {field_mappings}, {metadata}

**Field mappings have been provided by the semantic mapping system:**
{field_mappings}

**Your task:**
1. Use the provided technical_field from field_mappings
2. Generate Intent models with correct:
   - aggregation functions (for measures)
   - date functions (for date fields)
   - sorting and filtering

**DO NOT re-map fields** - the mappings are already correct.
Focus on generating Intent models.
```

**优势**：
- ✅ 职责分离：RAG负责映射，Task Planner负责Intent生成
- ✅ 利用向量检索和历史学习
- ✅ Prompt更简洁，LLM负担更轻

---

### 2. semantic_map_fields 工具设计

#### 工具接口

```python
from langchain_core.tools import tool

@tool
async def semantic_map_fields(
    business_terms: List[str],
    question_context: str,
    metadata: Dict,
    datasource_luid: str
) -> Dict:
    """
    语义字段映射工具
    
    将业务术语映射到技术字段名
    
    Args:
        business_terms: 业务术语列表，如 ["华东地区", "销售额"]
        question_context: 完整问题上下文
        metadata: Tableau元数据
        datasource_luid: 数据源唯一标识
    
    Returns:
        FieldMappingResult字典
    """
    # 实现见下文
    pass
```

#### 工具实现

```python
async def semantic_map_fields(
    business_terms: List[str],
    question_context: str,
    metadata: Dict,
    datasource_luid: str
) -> Dict:
    """语义字段映射工具实现"""
    
    # 1. 加载增强元数据（包含语义信息）
    enhanced_metadata = await store.get(
        namespace=("field_semantics", datasource_luid)
    ) or metadata
    
    # 2. 为每个业务术语进行映射
    mappings = {}
    
    for term in business_terms:
        # 2.1 向量检索（Top-5候选）
        vector_candidates = await vector_search(
            query=term,
            metadata=enhanced_metadata,
            top_k=5
        )
        
        # 2.2 历史映射检索
        usage_hints = await get_field_usage_hints(
            business_term=term,
            datasource_luid=datasource_luid,
            store=store
        )
        
        # 2.3 配置文件提示（可选）
        config_hints = await load_mapping_hints(datasource_luid)
        
        # 2.4 LLM语义判断
        mapping = await llm_semantic_judge(
            business_term=term,
            question_context=question_context,
            vector_candidates=vector_candidates,
            usage_hints=usage_hints,
            config_hints=config_hints
        )
        
        mappings[term] = mapping
    
    # 3. 返回结果
    return {
        "mappings": mappings,
        "overall_confidence": calculate_overall_confidence(mappings),
        "datasource_luid": datasource_luid
    }
```

#### LLM语义判断

```python
async def llm_semantic_judge(
    business_term: str,
    question_context: str,
    vector_candidates: List[Dict],
    usage_hints: List[Dict],
    config_hints: Dict
) -> Dict:
    """LLM语义判断"""
    
    prompt = f"""
你是一个Tableau字段映射专家。请将业务术语映射到正确的技术字段。

## 问题上下文
{question_context}

## 业务术语
{business_term}

## 向量检索候选（Top-5）
{format_vector_candidates(vector_candidates)}

## 历史使用提示
{format_usage_hints(usage_hints)}

## 映射提示（参考，非强制）
{format_config_hints(config_hints)}

## 分析步骤
1. 理解业务术语的含义
2. 分析问题上下文中的语义
3. **优先参考历史使用提示**（如果有高频且高成功率的记录）
4. 参考映射提示中的同义词和常见模式
5. 比较向量候选的描述和示例值
6. 考虑字段类型是否匹配

## 重要提示
- 历史使用提示的权重最高（特别是成功率 > 0.9 的记录）
- 映射提示仅供参考，可以根据上下文选择忽略
- 最终决策基于语义理解，而非规则匹配

## 输出格式
请以JSON格式输出:
{{
  "technical_field": "选择的技术字段名",
  "confidence": 0.95,
  "reasoning": "详细的推理过程",
  "alternatives": [
    {{"field": "备选字段1", "score": 0.85, "reason": "备选原因"}},
    {{"field": "备选字段2", "score": 0.75, "reason": "备选原因"}}
  ]
}}
"""
    
    result = await llm.ainvoke(prompt)
    return result
```

---

### 3. FieldMappingResult 数据模型

```python
from pydantic import BaseModel, Field
from typing import Dict, List, Optional

class FieldMapping(BaseModel):
    """单个字段的映射结果"""
    business_term: str
    """业务术语"""
    
    technical_field: str
    """技术字段名"""
    
    confidence: float
    """置信度 (0-1)"""
    
    reasoning: str
    """推理过程"""
    
    alternatives: List[Dict]
    """备选方案"""
    
    field_data_type: str
    """字段数据类型"""
    
    field_role: str
    """字段角色: dimension/measure"""


class FieldMappingResult(BaseModel):
    """字段映射结果"""
    mappings: Dict[str, FieldMapping]
    """业务术语到映射结果的字典"""
    
    overall_confidence: float
    """整体置信度"""
    
    datasource_luid: str
    """数据源唯一标识"""
```

---

### 4. Task Planner Prompt调整

#### 调整前（包含映射规则）

```python
def get_specific_domain_knowledge(self) -> str:
    return """
Step 1: For each business term, find technical field from metadata
- Review available fields: Examine metadata.fields list carefully
- Identify semantic match: Find field with matching business meaning
  * Match category first: Which category does this term belong to?
  * Then match name: Search for fields within that category by name similarity
- Verify field existence: CRITICAL - technical_field MUST be exact name from metadata.fields
  * Check: Does this exact field name appear in metadata.fields?
  * If no exact match: Choose semantically closest field from metadata
- Double-check: Confirm selected field appears in metadata.fields list
  * Never use business term directly as technical_field
  * Never invent field names

Step 2: Determine Intent type for each entity
...
"""
```

#### 调整后（专注Intent生成）

```python
def get_specific_domain_knowledge(self) -> str:
    return """
Resources: {understanding}, {field_mappings}, {metadata}

**Field mappings have been provided by the semantic mapping system:**
{field_mappings}

**Mapping confidence levels:**
- High (> 0.8): Use directly with confidence
- Medium (0.5-0.8): Use but note in rationale
- Low (< 0.5): Consider alternatives provided

**Your task:**
Use the provided technical_field from field_mappings and generate Intent models.

**Think step by step:**

Step 1: Review field mappings
- Check mapping confidence for each field
- Note any low-confidence mappings
- Review alternatives if confidence < 0.8

Step 2: Generate Intent models
- For dimensions: Use technical_field from mapping
  * Add aggregation ONLY if counting (COUNTD)
- For measures: Use technical_field + determine aggregation
  * Use aggregation from sub-question's measure_aggregations
  * Default to SUM if not specified
- For date fields: Use technical_field + determine date_function
  * Use date_function from sub-question's date_field_functions

Step 3: Add filters and sorting
- Date filters: Use mapped date field + time_range from sub-question
- Other filters: Use mapped fields + filter conditions
- Sorting: Based on question requirements

**CRITICAL**: 
- Use technical_field from field_mappings (do not re-map)
- If mapping confidence is low, include alternatives in rationale
- Focus on generating correct Intent models, not field mapping
"""
```

---

### 5. 完整的执行流程示例

```python
# 用户问题
question = "华东地区的销售额是多少？"

# 1. Understanding Agent
understanding = {
    "original_question": question,
    "sub_questions": [
        {
            "text": "华东地区的销售额",
            "mentioned_dimensions": ["华东地区"],
            "mentioned_measures": ["销售额"],
            "execution_type": "query"
        }
    ]
}

# 2. Task Planner Agent - 提取业务术语
business_terms = ["华东地区", "销售额"]

# 3. semantic_map_fields 工具
field_mapping_result = {
    "mappings": {
        "华东地区": {
            "business_term": "华东地区",
            "technical_field": "[Region].[一级地区]",
            "confidence": 0.95,
            "reasoning": "根据示例值匹配，'华东'出现在一级地区的示例中",
            "alternatives": [
                {"field": "[Region].[二级地区]", "score": 0.75}
            ],
            "field_data_type": "STRING",
            "field_role": "dimension"
        },
        "销售额": {
            "business_term": "销售额",
            "technical_field": "[Sales].[Sales Amount]",
            "confidence": 0.98,
            "reasoning": "业务含义匹配，历史使用频率高",
            "alternatives": [
                {"field": "[Sales].[Revenue]", "score": 0.85}
            ],
            "field_data_type": "REAL",
            "field_role": "measure"
        }
    },
    "overall_confidence": 0.965,
    "datasource_luid": "xxx"
}

# 4. Task Planner Agent - 生成Intent
query_planning_result = {
    "subtasks": [
        {
            "task_type": "query",
            "question_id": "q1",
            "question_text": "华东地区的销售额",
            "stage": 1,
            "depends_on": [],
            "dimension_intents": [
                {
                    "business_term": "华东地区",
                    "technical_field": "[Region].[一级地区]",
                    "field_data_type": "STRING",
                    "aggregation": null,
                    "mapping_confidence": 0.95  # ⭐ 新增
                }
            ],
            "measure_intents": [
                {
                    "business_term": "销售额",
                    "technical_field": "[Sales].[Sales Amount]",
                    "field_data_type": "REAL",
                    "aggregation": "SUM",
                    "mapping_confidence": 0.98  # ⭐ 新增
                }
            ],
            "rationale": "使用RAG映射的字段生成查询Intent"
        }
    ]
}

# 5. Query Builder - 构建VizQL查询
vizql_query = {
    "datasource": "xxx",
    "fields": [
        {"name": "[Region].[一级地区]", "role": "dimension"},
        {"name": "[Sales].[Sales Amount]", "role": "measure", "aggregation": "SUM"}
    ]
}
```

---

### 6. 历史映射保存

```python
async def save_mapping_history(
    field_mapping_result: FieldMappingResult,
    question_context: str,
    datasource_luid: str,
    store: PersistentStore
):
    """
    保存映射历史
    
    在Task Planner执行后调用
    """
    for term, mapping in field_mapping_result.mappings.items():
        await save_single_mapping_history(
            business_term=term,
            technical_field=mapping.technical_field,
            question_context=question_context,
            confidence=mapping.confidence,
            datasource_luid=datasource_luid,
            store=store
        )


async def update_mapping_success(
    field_mapping_result: FieldMappingResult,
    query_success: bool,
    datasource_luid: str,
    store: PersistentStore
):
    """
    更新映射成功率
    
    在查询执行后调用
    """
    for term, mapping in field_mapping_result.mappings.items():
        await update_field_usage_stats(
            field_name=mapping.technical_field,
            business_term=term,
            usage_data={},
            success=query_success,
            store=store
        )
```

---

## 性能优化

### 1. 批量映射

```python
# 不要逐个术语映射
for term in business_terms:
    mapping = await semantic_map_fields([term], ...)  # ❌ 慢

# 批量映射
mappings = await semantic_map_fields(business_terms, ...)  # ✅ 快
```

### 2. 缓存映射结果

```python
# 检查是否已有映射缓存
cache_key = f"mapping_{datasource_luid}_{hash(tuple(business_terms))}"
cached = await store.get(("mapping_cache",), cache_key)
if cached:
    return cached

# 否则进行映射
result = await semantic_map_fields(...)
await store.put(("mapping_cache",), cache_key, result, ttl=3600)
```

### 3. 并行处理

```python
# 并行处理独立的映射
import asyncio

tasks = [
    semantic_map_single_field(term, ...)
    for term in business_terms
]
results = await asyncio.gather(*tasks)
```

---

## 错误处理

### 1. 低置信度映射

```python
if mapping.confidence < 0.5:
    # 记录警告
    logger.warning(f"Low confidence mapping: {term} -> {mapping.technical_field}")
    
    # 在Intent中标记
    intent.mapping_confidence = mapping.confidence
    intent.mapping_alternatives = mapping.alternatives
```

### 2. 映射失败

```python
try:
    mapping_result = await semantic_map_fields(...)
except Exception as e:
    # 降级：使用原有的Prompt映射
    logger.error(f"Semantic mapping failed: {e}")
    mapping_result = await fallback_to_prompt_mapping(...)
```

### 3. 字段不存在

```python
# 验证映射的字段是否存在于元数据中
for term, mapping in mapping_result.mappings.items():
    if not field_exists_in_metadata(mapping.technical_field, metadata):
        raise ValueError(f"Mapped field not found: {mapping.technical_field}")
```

---

## 总结

### Task Planner与RAG集成的优势

| 维度 | 旧方案（硬编码规则） | 新方案（RAG集成） |
|------|---------------------|------------------|
| **映射准确性** | 中 | 高 |
| **支持同义词** | 否 | 是 |
| **历史学习** | 否 | 是 |
| **Prompt复杂度** | 高 | 低 |
| **LLM负担** | 重 | 轻 |
| **可维护性** | 低 | 高 |

### 实现优先级

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| **阶段1** | 基础RAG映射 | P0 (必需) |
| **阶段2** | 历史学习 | P0 (必需) |
| **阶段3** | 配置文件提示 | P1 (推荐) |
| **阶段4** | 性能优化 | P2 (可选) |
