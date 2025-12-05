# 非 LLM 节点设计

## 概述

本文档描述非 LLM 节点的详细设计，包括 QueryBuilder 和 Execute 节点。

对应项目结构：`src/nodes/`

---

## 1. QueryBuilder Node

### 职责

- 将 SemanticQuery（纯语义）转换为 VizQLQuery（技术字段名 + 表达式）
- 代码优先 + LLM fallback 的混合模式

### 架构

```
QueryBuilder Node
    │
    ├── FieldMapper (RAG + LLM)
    │       ├── RAG 检索候选字段
    │       └── 置信度 < 0.9 时用 LLM 判断
    │
    ├── ImplementationResolver (代码规则 + LLM fallback)
    │       ├── 简单场景：代码规则（单维度、明确 LOD 等）
    │       └── 复杂场景：LLM 判断（多维度模糊语义、嵌套计算等）
    │
    └── ExpressionGenerator (代码模板)
            └── 100% 确定性
```

### 节点实现

```python
# tableau_assistant/src/nodes/query_builder/node.py

async def query_builder_node(state: VizQLState, runtime) -> Dict[str, Any]:
    """
    QueryBuilder 节点（代码优先 + LLM fallback）
    
    流程：
    1. FieldMapper: 业务术语 → 技术字段
    2. ImplementationResolver: 判断表计算/LOD + addressing
    3. ExpressionGenerator: 生成 VizQL 表达式
    4. QueryAssembler: 组装 VizQLQuery
    5. QueryValidator: 验证查询
    """
    semantic_query = state["semantic_query"]
    metadata = state["metadata"]
    
    # 初始化组件
    field_mapper = FieldMapper(metadata)
    impl_resolver = ImplementationResolver()
    expr_generator = ExpressionGenerator()
    query_builder = SemanticQueryBuilder(
        metadata, field_mapper, impl_resolver, expr_generator
    )
    
    # 构建 VizQL 查询
    vizql_query = await query_builder.build(semantic_query)
    
    return {
        "vizql_query": vizql_query,
        "query_builder_complete": True,
    }
```

### VizQL Field Type 决策树

```
问题: 这个字段需要什么类型?

Q1: 是否需要简单分组/分类 (无聚合)?
    YES → DimensionField
          {"fieldCaption": "Category"}

Q2: 是否需要简单聚合 (SUM, AVG, COUNT, MIN, MAX)?
    YES → MeasureField with function
          {"fieldCaption": "Sales", "function": "SUM"}

Q3: 是否需要 COUNTD 或 LOD 表达式?
    YES → CalculatedField with calculation
          {"fieldCaption": "unique_customers",
           "calculation": "COUNTD([Customer ID])"}

Q4: 是否需要表计算 (WINDOW_*, RUNNING_*, RANK*, LOOKUP)?
    YES → TableCalcField with tableCalculation
          {"fieldCaption": "running_total",
           "calculation": "RUNNING_SUM(SUM([Sales]))",
           "tableCalculation": {...}}
```

---

### SemanticQuery → VizQLQuery 转换示例

#### 示例 1: 简单聚合

**SemanticQuery**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [{"name": "品类", "is_time": false}]
}
```

**VizQL API Request**:
```json
{
    "fields": [
        {"fieldCaption": "Category"},
        {"fieldCaption": "Sales", "function": "SUM"}
    ]
}
```

#### 示例 2: 累计总额

**SemanticQuery**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [{"name": "日期", "is_time": true, "time_granularity": "month"}],
    "analyses": [{"type": "cumulative", "target_measure": "销售额"}]
}
```

**VizQL API Request**:
```json
{
    "fields": [
        {"fieldCaption": "Order Date", "dateFunction": "MONTH"},
        {"fieldCaption": "Sales", "function": "SUM"},
        {
            "fieldCaption": "cumulative_销售额",
            "calculation": "RUNNING_SUM(SUM([Sales]))",
            "tableCalculation": {
                "tableCalcType": "CUSTOM",
                "dimensions": [{"fieldCaption": "Order Date"}]
            }
        }
    ]
}
```

#### 示例 3: 多维度累计 (per_group)

**SemanticQuery**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [
        {"name": "省份", "is_time": false},
        {"name": "日期", "is_time": true, "time_granularity": "month"}
    ],
    "analyses": [{
        "type": "cumulative",
        "target_measure": "销售额",
        "computation_scope": "per_group"
    }]
}
```

**转换逻辑**:
- `computation_scope: "per_group"` → addressing 只包含时间维度
- 省份作为隐式分区，每个省份独立累计

**VizQL API Request**:
```json
{
    "fields": [
        {"fieldCaption": "State"},
        {"fieldCaption": "Order Date", "dateFunction": "MONTH"},
        {"fieldCaption": "Sales", "function": "SUM"},
        {
            "fieldCaption": "cumulative_销售额",
            "calculation": "RUNNING_SUM(SUM([Sales]))",
            "tableCalculation": {
                "tableCalcType": "CUSTOM",
                "dimensions": [{"fieldCaption": "Order Date"}]
            }
        }
    ]
}
```

#### 示例 4: LOD FIXED

**SemanticQuery**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [{"name": "产品", "is_time": false}],
    "analyses": [{
        "type": "aggregation_at_level",
        "target_measure": "销售额",
        "target_granularity": ["品类"],
        "requires_external_dimension": false
    }]
}
```

**VizQL API Request**:
```json
{
    "fields": [
        {"fieldCaption": "Product Name"},
        {"fieldCaption": "Sales", "function": "SUM"},
        {
            "fieldCaption": "aggregation_at_level_销售额",
            "calculation": "{FIXED [Category] : SUM([Sales])}"
        }
    ]
}
```

---

## 2. Execute Node

### 职责

- 执行 VizQL API 调用
- 处理 API 响应
- 大结果由 FilesystemMiddleware 自动处理

### 节点实现

```python
# tableau_assistant/src/nodes/execute/node.py

async def execute_node(state: VizQLState, runtime) -> Dict[str, Any]:
    """
    Execute 节点（非 LLM）
    
    流程：
    1. 构建 API 请求
    2. 调用 VizQL Data Service API
    3. 解析响应
    """
    vizql_query = state["vizql_query"]
    datasource = state["datasource"]
    
    # 构建请求
    request = {
        "datasource": {"datasourceName": datasource},
        "query": vizql_query.to_dict()
    }
    
    # 调用 API
    response = await vizql_api.query(request)
    
    # 解析响应
    result = QueryResult(
        data=response["data"],
        row_count=len(response["data"]),
        columns=response["columns"],
        execution_time=response.get("executionTime")
    )
    
    return {
        "query_result": result,
        "execute_complete": True,
    }
```

### 大结果处理

当查询结果超过 token 限制时，FilesystemMiddleware 自动介入：

```
Execute Node 输出 QueryResult
    │
    ▼ FilesystemMiddleware 检测 token 数量
    │
    ├─ < 20000 tokens → 直接传递
    │
    └─ >= 20000 tokens → 保存到文件，返回文件路径
```
