# 字段语义推断系统设计

## 概述

字段语义推断系统是元数据增强的核心组件，为所有字段（维度、度量、日期）添加丰富的语义信息，以增强RAG的检索和映射能力。

## 为什么需要字段语义推断？

### 原始元数据的局限性

```yaml
# Tableau原始元数据
fields:
  - name: "[Region].[一级地区]"
    role: "dimension"
    data_type: "STRING"
    samples: ["华东"]  # 只有1个样本
    
  - name: "[Sales].[Sales Amount]"
    role: "measure"
    data_type: "REAL"
    samples: [1000.0]  # 只有1个样本

问题:
1. 字段名不清晰 - "一级地区"是什么级别？
2. 缺少业务含义 - "Sales Amount"是金额还是数量？
3. 缺少关系信息 - 字段之间的层级关系不明确
4. 样本太少 - 无法理解字段的值域
5. 缺少使用提示 - 不知道常用的聚合方式
```

### 增强后的元数据

```yaml
# 增强后的元数据
fields:
  - name: "[Region].[一级地区]"
    role: "dimension"
    data_type: "STRING"
    samples: ["华东", "华北", "华南", "华中", "西南"]  # ⭐ 更多样本
    
    # ⭐ 语义信息
    semantics:
      category: "geographic"
      subcategory: "region"
      level: 1                    # 最粗粒度
      granularity: "coarsest"
      parent: null
      child: "[Region].[二级地区]"
      business_meaning: "大区级别的地理区域划分"
    
  - name: "[Sales].[Sales Amount]"
    role: "measure"
    data_type: "REAL"
    samples: [1000.0, 2000.0, 3000.0, 5000.0, 10000.0]  # ⭐ 更多样本
    
    # ⭐ 语义信息
    semantics:
      category: "financial"
      subcategory: "revenue"
      unit: "元"
      value_range: {min: 0, max: 1000000, avg: 50000}
      suggested_aggregation: "SUM"
      business_meaning: "销售金额，表示交易的总金额"
```

---

## 统一的语义模型

### FieldSemantics 数据模型

```python
class FieldSemantics(BaseModel):
    """统一的字段语义模型（适用于所有字段类型）"""
    
    # ===== 通用语义信息（所有字段）=====
    category: str
    """主类别: geographic, temporal, product, customer, financial, operational等"""
    
    subcategory: Optional[str] = None
    """子类别: region/city/district, revenue/cost/profit等"""
    
    business_meaning: str
    """业务含义: 简短描述字段的业务意义"""
    
    # ===== 维度特有信息 =====
    level: Optional[int] = None
    """层级: 1-5 (1=最粗, 5=最细) (仅维度字段)"""
    
    granularity: Optional[str] = None
    """粒度: coarsest/coarse/medium/fine/finest (仅维度字段)"""
    
    parent: Optional[str] = None
    """父字段: 更粗粒度的字段 (仅维度字段)"""
    
    child: Optional[str] = None
    """子字段: 更细粒度的字段 (仅维度字段)"""
    
    # ===== 度量特有信息 =====
    value_range: Optional[Dict[str, float]] = None
    """值域: {"min": 0, "max": 1000000, "avg": 50000, "median": 45000} (仅度量字段)"""
    
    default_aggregation: Optional[str] = None
    """默认聚合: 从Tableau元数据获取 (仅度量字段)"""
    
    # ===== 历史学习信息（所有字段）=====
    usage_stats: Optional[Dict[str, Any]] = None
    """使用统计: 从历史查询中学习"""
```

---

## 分阶段推断策略

### 阶段1：基础语义推断（所有字段）

**目标**：为所有字段推断基本的语义信息

**推断内容**：
- 主类别 (category)
- 子类别 (subcategory)
- 业务含义 (business_meaning)

**方法**：LLM基于字段名和示例值

```python
async def basic_semantic_inference(metadata: Metadata) -> Dict[str, Dict]:
    """
    基础语义推断（所有字段）
    
    输入: 原始元数据
    输出: 每个字段的基础语义信息
    """
    prompt = """
    请为以下字段推断基础语义信息:
    
    字段列表:
    {fields}
    
    对每个字段，推断:
    1. category: 主类别 (geographic/temporal/product/customer/financial/operational/other)
    2. subcategory: 子类别 (更具体的分类)
    3. business_meaning: 业务含义 (1-2句话)
    
    输出JSON格式
    """
    
    result = await llm.invoke(prompt, input_data={"fields": metadata.fields})
    return result
```

**示例输出**：
```json
{
  "[Region].[一级地区]": {
    "category": "geographic",
    "subcategory": "region",
    "business_meaning": "大区级别的地理区域划分"
  },
  "[Sales].[Sales Amount]": {
    "category": "financial",
    "subcategory": "revenue",
    "business_meaning": "销售金额，表示交易的总金额"
  }
}
```

### 阶段2：维度层级推断（维度字段）

**目标**：为维度字段推断层级关系

**推断内容**：
- 层级 (level: 1-5)
- 粒度 (granularity)
- 父子关系 (parent/child)

**方法**：LLM基于字段名、示例值、唯一值数量

```python
async def dimension_hierarchy_inference(
    dimension_fields: List[Field]
) -> Dict[str, Dict]:
    """
    维度层级推断（仅维度字段）
    
    输入: 维度字段列表
    输出: 每个维度字段的层级信息
    """
    # 使用现有的 DimensionHierarchyAgent
    result = await dimension_hierarchy_agent.execute(dimension_fields)
    return result
```

**示例输出**：
```json
{
  "[Region].[一级地区]": {
    "level": 1,
    "granularity": "coarsest",
    "parent": null,
    "child": "[Region].[二级地区]"
  },
  "[Region].[二级地区]": {
    "level": 2,
    "granularity": "coarse",
    "parent": "[Region].[一级地区]",
    "child": "[Region].[三级地区]"
  }
}
```

### 阶段3：度量增强（度量字段）- 简化版

**目标**：为度量字段添加基础统计信息

**推断内容**：
- 值域 (value_range) - 统计计算 ✅
- ~~单位 (unit)~~ - 元数据中已有或不需要 ❌
- ~~建议聚合 (suggested_aggregation)~~ - 元数据中已有 ❌

**为什么简化？**

1. **建议聚合** - Tableau元数据中的`defaultAggregation`字段已经包含
2. **单位** - 通常不需要，或者可以从字段名推断（如果真的需要）
3. **度量名称不规范** - `sale_amount_30`, `sales_amount`等，LLM很难准确推断
4. **计算逻辑复杂** - `30`可能是前30天对比值，也可能是30天汇总值，需要理解数据结构

**简化方案**：只做基础统计

```python
async def measure_enhancement(measure_fields: List[Field]) -> Dict[str, Dict]:
    """
    度量增强（仅度量字段）- 简化版
    
    只做基础统计，不做复杂推断
    
    输入: 度量字段列表
    输出: 每个度量字段的统计信息
    """
    enhancements = {}
    
    for field in measure_fields:
        # 只做统计计算，不调用LLM
        enhancements[field.name] = {
            "value_range": {
                "min": min(field.sample_values) if field.sample_values else None,
                "max": max(field.sample_values) if field.sample_values else None,
                "avg": sum(field.sample_values) / len(field.sample_values) if field.sample_values else None,
                "median": calculate_median(field.sample_values) if field.sample_values else None
            },
            "default_aggregation": field.defaultAggregation  # 从元数据获取
        }
    
    return enhancements
```

**示例输出**：
```json
{
  "[Sales].[Sales Amount]": {
    "value_range": {
      "min": 0,
      "max": 1000000,
      "avg": 50000,
      "median": 45000
    },
    "default_aggregation": "SUM"  # 从元数据获取
  },
  "[Sales].[Quantity]": {
    "value_range": {
      "min": 0,
      "max": 10000,
      "avg": 500,
      "median": 450
    },
    "default_aggregation": "SUM"  # 从元数据获取
  }
}
```

**优势**：
- ✅ **简单可靠** - 只做统计，不需要LLM推断
- ✅ **避免错误** - 不会因为名称不规范而推断错误
- ✅ **足够用** - 值域信息对RAG检索已经足够
- ✅ **快速** - 不需要调用LLM

### 阶段4：历史学习（所有字段）⭐ 关键

**核心思想**：度量字段的语义很难预先推断，但可以从实际使用中学习

**为什么历史学习对度量字段特别重要？**

```
问题场景:
- sale_amount_30: 是前30天对比值？还是30天汇总值？
- sales_amount: 是总销售额？还是某个特定渠道的销售额？
- revenue_adjusted: 调整后的收入？调整逻辑是什么？

LLM预先推断: ❌ 很难准确
历史学习: ✅ 从实际使用中学习
```

**学习内容**：

1. **问题-字段映射历史**（最重要）
   - 记录：哪些问题使用了哪些度量字段
   - 示例：
     ```
     "销售额" → [Sales].[Sales Amount] (使用15次)
     "销售额" → [Sales].[sale_amount_30] (使用2次)
     "30天销售额" → [Sales].[sale_amount_30] (使用8次)
     ```

2. **常用聚合**
   - 记录：每个度量字段常用的聚合方式
   - 示例：
     ```
     [Sales].[Sales Amount]: {"SUM": 15, "AVG": 3}
     [Sales].[sale_amount_30]: {"SUM": 10}
     ```

3. **常用维度组合**
   - 记录：度量字段常与哪些维度一起使用
   - 示例：
     ```
     [Sales].[Sales Amount]: {"Region": 10, "Product": 8, "Date": 12}
     ```

4. **成功率统计**
   - 记录：映射后查询是否成功
   - 用于评估映射质量

**实现**：

```python
class UsageStats(BaseModel):
    """字段使用统计"""
    
    # 问题-字段映射历史
    question_mappings: Dict[str, int] = {}
    """{"销售额": 15, "30天销售额": 8}"""
    
    # 常用聚合
    aggregations: Dict[str, int] = {}
    """{"SUM": 15, "AVG": 3}"""
    
    # 常用维度组合
    common_dimensions: Dict[str, int] = {}
    """{"Region": 10, "Product": 8}"""
    
    # 成功率
    total_usage: int = 0
    successful_usage: int = 0
    success_rate: float = 0.0


async def update_usage_stats(
    field_name: str,
    business_term: str,
    usage_data: Dict,
    success: bool,
    store: PersistentStore
):
    """
    更新字段使用统计
    
    在每次查询执行后调用
    
    Args:
        field_name: 技术字段名
        business_term: 业务术语
        usage_data: 使用数据（聚合、维度等）
        success: 查询是否成功
    """
    key = f"usage_stats_{field_name}"
    stats = await store.get(("field_semantics", key)) or UsageStats().model_dump()
    
    # 1. 更新问题-字段映射历史
    stats["question_mappings"][business_term] = \
        stats["question_mappings"].get(business_term, 0) + 1
    
    # 2. 更新聚合统计
    if "aggregation" in usage_data:
        agg = usage_data["aggregation"]
        stats["aggregations"][agg] = stats["aggregations"].get(agg, 0) + 1
    
    # 3. 更新维度组合统计
    if "dimensions" in usage_data:
        for dim in usage_data["dimensions"]:
            stats["common_dimensions"][dim] = \
                stats["common_dimensions"].get(dim, 0) + 1
    
    # 4. 更新成功率
    stats["total_usage"] += 1
    if success:
        stats["successful_usage"] += 1
    stats["success_rate"] = stats["successful_usage"] / stats["total_usage"]
    
    await store.put(("field_semantics", key), stats)


async def get_field_usage_hints(
    business_term: str,
    datasource_luid: str,
    store: PersistentStore
) -> List[Dict]:
    """
    获取字段使用提示（用于RAG增强）
    
    根据业务术语，查找历史上常用的字段
    
    Returns:
        [
            {
                "field_name": "[Sales].[Sales Amount]",
                "usage_count": 15,
                "success_rate": 0.95
            },
            ...
        ]
    """
    # 查询所有字段的使用统计
    all_stats = await store.list(("field_semantics",))
    
    # 筛选包含该业务术语的字段
    hints = []
    for key, stats in all_stats:
        if business_term in stats.get("question_mappings", {}):
            hints.append({
                "field_name": key.replace("usage_stats_", ""),
                "usage_count": stats["question_mappings"][business_term],
                "success_rate": stats.get("success_rate", 0.0)
            })
    
    # 按使用次数和成功率排序
    hints.sort(
        key=lambda x: (x["usage_count"] * x["success_rate"]),
        reverse=True
    )
    
    return hints
```

**RAG如何利用历史学习**：

```python
async def semantic_map_fields_with_history(
    business_terms: List[str],
    question_context: str,
    metadata: Metadata,
    datasource_luid: str
) -> FieldMappingResult:
    """
    语义字段映射（增强版：利用历史学习）
    """
    mappings = {}
    
    for term in business_terms:
        # 1. 向量检索（Top-5候选）
        vector_candidates = await vector_search(term, metadata)
        
        # 2. 历史学习提示
        usage_hints = await get_field_usage_hints(term, datasource_luid, store)
        
        # 3. LLM判断（综合考虑向量相似度和历史使用）
        mapping = await llm.invoke(f"""
        业务术语: {term}
        问题上下文: {question_context}
        
        向量检索候选:
        {vector_candidates}
        
        历史使用提示:
        {usage_hints}
        
        请选择最合适的字段。
        
        注意:
        - 如果历史使用提示中有高频且高成功率的字段，优先考虑
        - 向量相似度只是参考，历史使用更可靠
        - 考虑问题上下文，如"30天销售额"应该选择包含"30"的字段
        """)
        
        mappings[term] = mapping
    
    return FieldMappingResult(mappings=mappings)
```

**示例：历史学习如何帮助选择正确的度量**

```
用户问题: "30天销售额"

向量检索候选:
1. [Sales].[Sales Amount] (相似度: 0.92)
2. [Sales].[sale_amount_30] (相似度: 0.88)
3. [Sales].[Revenue] (相似度: 0.85)

历史使用提示:
1. [Sales].[sale_amount_30]
   - "30天销售额" 使用8次，成功率100%
   - "销售额" 使用2次，成功率50%

2. [Sales].[Sales Amount]
   - "销售额" 使用15次，成功率95%
   - "30天销售额" 使用0次

LLM判断:
虽然[Sales].[Sales Amount]的向量相似度更高，
但历史数据显示"30天销售额"这个问题更常用[Sales].[sale_amount_30]，
且成功率100%。

选择: [Sales].[sale_amount_30] (置信度: 0.95)
```

---

## 完整的实现流程

```python
async def enhance_field_semantics(
    datasource_luid: str,
    metadata: Metadata
) -> Dict[str, Any]:
    """
    完整的字段语义推断流程
    
    步骤:
    1. 增强示例值（从数据源获取更多样本）
    2. 基础语义推断（所有字段）
    3. 维度层级推断（维度字段）
    4. 度量增强（度量字段）
    5. 合并结果
    6. 保存到PersistentStore
    7. 构建向量索引
    """
    # 1. 增强示例值
    for field in metadata.fields:
        if not field.sample_values or len(field.sample_values) < 5:
            field.sample_values = await fetch_field_samples(
                datasource_luid,
                field.name,
                sample_count=10 if field.role == "dimension" else 5
            )
    
    # 2. 基础语义推断（所有字段）
    basic_semantics = await basic_semantic_inference(metadata)
    
    # 3. 维度层级推断（维度字段）
    dimension_fields = metadata.get_dimensions()
    dimension_hierarchy = await dimension_hierarchy_inference(dimension_fields)
    
    # 4. 度量增强（度量字段）
    measure_fields = metadata.get_measures()
    measure_enhancements = await measure_enhancement(measure_fields)
    
    # 5. 合并结果
    enhanced_fields = {}
    for field in metadata.fields:
        enhanced_fields[field.name] = {
            "original": field.model_dump(),
            "semantics": {
                **basic_semantics.get(field.name, {}),
                **dimension_hierarchy.get(field.name, {}),
                **measure_enhancements.get(field.name, {})
            }
        }
    
    # 6. 保存
    await store.put(
        namespace=("field_semantics", datasource_luid),
        value=enhanced_fields
    )
    
    # 7. 构建向量索引
    await build_field_index(datasource_luid, enhanced_fields)
    
    return enhanced_fields
```

---

## RAG如何利用语义信息

### 字段富文本生成

```python
def build_field_rich_text(
    field: FieldMetadata,
    semantics: FieldSemantics
) -> str:
    """
    生成包含语义信息的富文本
    """
    parts = []
    
    # 基础信息
    parts.append(f"字段名: {field.name}")
    parts.append(f"角色: {field.role}")
    parts.append(f"类型: {field.data_type}")
    
    # 示例值
    if field.sample_values:
        samples = ", ".join(str(v) for v in field.sample_values[:10])
        parts.append(f"示例值: {samples}")
    
    # 语义信息
    parts.append(f"类别: {semantics.category}")
    if semantics.subcategory:
        parts.append(f"子类别: {semantics.subcategory}")
    parts.append(f"业务含义: {semantics.business_meaning}")
    
    # 维度特有
    if semantics.level:
        parts.append(f"层级: {semantics.level} ({semantics.granularity})")
    if semantics.parent:
        parts.append(f"父字段: {semantics.parent}")
    if semantics.child:
        parts.append(f"子字段: {semantics.child}")
    
    # 度量特有
    if semantics.unit:
        parts.append(f"单位: {semantics.unit}")
    if semantics.value_range:
        parts.append(f"值域: {semantics.value_range['min']} ~ {semantics.value_range['max']}")
    if semantics.suggested_aggregation:
        parts.append(f"建议聚合: {semantics.suggested_aggregation}")
    
    return " | ".join(parts)
```

### RAG检索示例

```
用户问题: "华东地区的销售额"

业务术语: "华东地区", "销售额"

向量检索结果:

1. [Region].[一级地区]
   字段名: [Region].[一级地区] | 角色: dimension | 类型: STRING | 
   示例值: 华东, 华北, 华南, 华中, 西南 | 
   类别: geographic | 子类别: region | 
   业务含义: 大区级别的地理区域划分 | 
   层级: 1 (coarsest) | 父字段: null | 子字段: [Region].[二级地区]
   相似度: 0.95

2. [Sales].[Sales Amount]
   字段名: [Sales].[Sales Amount] | 角色: measure | 类型: REAL | 
   示例值: 1000.0, 2000.0, 3000.0, 5000.0, 10000.0 | 
   类别: financial | 子类别: revenue | 
   业务含义: 销售金额，表示交易的总金额 | 
   单位: 元 | 值域: 0 ~ 1000000 | 建议聚合: SUM
   相似度: 0.98

LLM判断:
- "华东地区" → [Region].[一级地区] (示例值匹配，层级合适)
- "销售额" → [Sales].[Sales Amount] (业务含义匹配，单位是"元")
```

---

## 性能优化

### 1. 批量推断

```python
# 不要逐个字段推断
for field in fields:
    semantics = await infer_semantics(field)  # ❌ 慢

# 批量推断
semantics = await infer_semantics_batch(fields)  # ✅ 快
```

### 2. 缓存推断结果

```python
# 检查是否已有推断结果
cached = await store.get(("field_semantics", datasource_luid))
if cached:
    return cached  # 直接使用缓存

# 否则进行推断
semantics = await enhance_field_semantics(datasource_luid, metadata)
```

### 3. 增量更新

```python
# 只推断新增或修改的字段
new_fields = detect_new_fields(metadata, cached_semantics)
if new_fields:
    new_semantics = await enhance_field_semantics_incremental(new_fields)
    cached_semantics.update(new_semantics)
```

---

## 总结

### 字段语义推断 vs RAG

| 维度 | 字段语义推断 | RAG字段映射 |
|------|-------------|------------|
| **运行时机** | 系统初始化（一次性） | 每次查询 |
| **输入** | 原始元数据 | 业务术语 + 增强元数据 |
| **输出** | 增强的元数据 | 字段映射结果 |
| **作用** | 元数据增强 | 字段选择 |
| **处理对象** | 所有字段 | 业务术语 |
| **是否必需** | 强烈推荐 | 必需 |

### 实现优先级

| 阶段 | 内容 | 难度 | 优先级 |
|------|------|------|--------|
| **阶段1** | 基础语义推断 | ⭐⭐ | P0 (必需) |
| **阶段2** | 维度层级推断 | ⭐⭐⭐ | P0 (必需) |
| **阶段3** | 度量增强 | ⭐⭐ | P1 (推荐) |
| **阶段4** | 历史学习 | ⭐ | P1 (推荐) |
