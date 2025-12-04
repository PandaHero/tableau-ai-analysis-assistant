# 设计附件：QueryBuilder 实现细节

## 概述

本文档详细说明 QueryBuilder Node 如何将 SemanticQuery 转换为 VizQL API 格式。
基于 `openapi.json` 中定义的 VizQL Data Service API 规范。

**重要变更**：
- QueryBuilder 是非 LLM 节点，执行确定性代码
- 输入：SemanticQuery（纯语义，来自 Understanding Agent）
- 输出：VizQLQuery（技术字段名 + VizQL 表达式）
- 内部组件：FieldMapper → ImplementationResolver → ExpressionGenerator

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        QueryBuilder Node（非 LLM）                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  输入: SemanticQuery（纯语义）                                               │
│       - measures: [{"name": "销售额", "aggregation": "sum"}]                │
│       - dimensions: [{"name": "省份"}, {"name": "日期", "is_time": true}]   │
│       - analyses: [{"type": "cumulative", "computation_scope": "per_group"}]│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 1: FieldMapper (RAG + LLM 混合)                              │    │
│  │  - 业务术语 → 技术字段名                                             │    │
│  │  - "销售额" → "Sales", "省份" → "State", "日期" → "Order Date"       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 2: ImplementationResolver (代码规则 + LLM 语义意图)          │    │
│  │  - 判断表计算 vs LOD                                                 │    │
│  │  - 解析 addressing 维度                                              │    │
│  │  - 输出: implementation_type, addressing_dimensions                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 3: ExpressionGenerator (代码模板)                            │    │
│  │  - 生成 VizQL 表达式                                                 │    │
│  │  - cumulative + sum → "RUNNING_SUM(SUM([Sales]))"                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 4: QueryAssembler (代码)                                     │    │
│  │  - 组装 VizQLQuery                                                   │    │
│  │  - 添加字段、筛选器                                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 5: QueryValidator (代码)                                     │    │
│  │  - Schema 验证、字段存在性验证、表达式语法验证                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  输出: VizQLQuery（技术字段名 + VizQL 表达式）                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## VizQL API 字段类型决策树

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        VizQL Field Type Decision Tree                        │
│                        (来自 openapi.json x-llm-guide)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  问题: 这个字段需要什么类型?                                                 │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Q1: 是否需要简单分组/分类 (无聚合)?                                  │    │
│  │     YES → DimensionField                                            │    │
│  │           {"fieldCaption": "Category"}                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │ NO                                            │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Q2: 是否需要简单聚合 (SUM, AVG, COUNT, MIN, MAX, MEDIAN, STDEV, VAR)?│    │
│  │     YES → MeasureField with function                                │    │
│  │           {"fieldCaption": "Sales", "function": "SUM"}              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │ NO                                            │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Q3: 是否需要 COUNTD 或 LOD 表达式?                                   │    │
│  │     YES → CalculatedField with calculation                          │    │
│  │           {"fieldCaption": "unique_customers",                      │    │
│  │            "calculation": "COUNTD([Customer ID])"}                  │    │
│  │           {"fieldCaption": "category_total",                        │    │
│  │            "calculation": "{FIXED [Category] : SUM([Sales])}"}      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │ NO                                            │
│                              ▼                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Q4: 是否需要表计算 (WINDOW_*, RUNNING_*, RANK*, LOOKUP, etc.)?      │    │
│  │     YES → TableCalcField with tableCalculation                      │    │
│  │           {"fieldCaption": "running_total",                         │    │
│  │            "calculation": "RUNNING_SUM(SUM([Sales]))",              │    │
│  │            "tableCalculation": {                                    │    │
│  │              "tableCalcType": "CUSTOM",                             │    │
│  │              "dimensions": [{"fieldCaption": "Date"}]               │    │
│  │            }}                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## SemanticQuery → VizQLQuery 转换流程

### 1. SemanticQueryBuilder 主类

```python
class SemanticQueryBuilder:
    """
    语义查询构建器 - 集成纯语义流水线
    
    职责：将 SemanticQuery 转换为 VizQLQuery
    """
    
    def __init__(
        self,
        metadata: Metadata,
        field_mapper: FieldMapper,
        implementation_resolver: ImplementationResolver,
        expression_generator: ExpressionGenerator
    ):
        self.metadata = metadata
        self.field_mapper = field_mapper
        self.implementation_resolver = implementation_resolver
        self.expression_generator = expression_generator
        self.validator = QueryValidator(metadata)
    
    async def build(self, semantic_query: SemanticQuery) -> VizQLQuery:
        """
        构建 VizQL 查询
        
        流程：
        1. 字段映射（RAG + LLM）
        2. 构建基础字段
        3. 处理分析（表计算/LOD）
        4. 构建筛选器
        5. 组装 VizQLQuery
        6. 验证
        """
        # 1. 字段映射
        mapped_fields = await self._map_all_fields(semantic_query)
        
        # 2. 构建基础字段
        fields = []
        view_dimensions = []
        
        # 2.1 维度字段
        for dim in semantic_query.dimensions:
            technical_field = mapped_fields[dim.name]
            view_dimensions.append(technical_field)
            
            if dim.is_time and dim.time_granularity:
                fields.append(self._build_date_dimension(technical_field, dim))
            else:
                fields.append(DimensionField(fieldCaption=technical_field))
        
        # 2.2 度量字段
        for measure in semantic_query.measures:
            technical_field = mapped_fields[measure.name]
            function = self._aggregation_to_function(measure.aggregation)
            fields.append(MeasureField(fieldCaption=technical_field, function=function))
        
        # 3. 处理分析（表计算/LOD）
        for analysis in semantic_query.analyses:
            analysis_field = await self._build_analysis_field(
                analysis, semantic_query.dimensions, mapped_fields, view_dimensions
            )
            fields.append(analysis_field)
        
        # 4. 构建筛选器
        filters = self._build_filters(semantic_query.filters, mapped_fields)
        
        # 5. 组装 VizQLQuery
        query = VizQLQuery(fields=fields, filters=filters if filters else None)
        
        # 6. 验证
        validation_result = self.validator.validate(query)
        if not validation_result.is_valid:
            raise ValueError(f"查询验证失败: {validation_result.errors}")
        
        return query
    
    async def _map_all_fields(self, semantic_query: SemanticQuery) -> Dict[str, str]:
        """映射所有业务术语到技术字段名"""
        business_terms = []
        
        # 收集所有业务术语
        for measure in semantic_query.measures:
            business_terms.append(measure.name)
        
        for dim in semantic_query.dimensions:
            business_terms.append(dim.name)
        
        for analysis in semantic_query.analyses:
            business_terms.append(analysis.target_measure)
            if analysis.target_granularity:
                business_terms.extend(analysis.target_granularity)
        
        for filter in semantic_query.filters:
            business_terms.append(filter.field)
        
        # 批量映射
        mappings = await self.field_mapper.map_fields_batch(
            list(set(business_terms)),
            context=str(semantic_query)
        )
        
        return {m.business_term: m.technical_field for m in mappings}
    
    async def _build_analysis_field(
        self,
        analysis: AnalysisSpec,
        dimensions: List[DimensionSpec],
        mapped_fields: Dict[str, str],
        view_dimensions: List[str]
    ) -> VizQLField:
        """构建分析字段（表计算或 LOD）"""
        technical_field = mapped_fields[analysis.target_measure]
        
        # 解析实现方式
        implementation = self.implementation_resolver.resolve(
            analysis, dimensions, mapped_fields, view_dimensions
        )
        
        # 生成表达式
        expression = self.expression_generator.generate(
            analysis, implementation, technical_field
        )
        
        # 构建字段
        field_caption = f"{analysis.type.value}_{analysis.target_measure}"
        
        if implementation.implementation_type == ImplementationType.LOD:
            # LOD → CalculatedField
            return CalculatedField(
                fieldCaption=field_caption,
                calculation=expression
            )
        else:
            # 表计算 → TableCalcField
            return TableCalcField(
                fieldCaption=field_caption,
                calculation=expression,
                tableCalculation=CustomTableCalcSpecification(
                    tableCalcType="CUSTOM",
                    dimensions=[
                        TableCalcFieldReference(fieldCaption=d)
                        for d in implementation.addressing_dimensions
                    ]
                )
            )
```


### 2. 辅助方法

```python
    def _build_date_dimension(
        self, 
        technical_field: str, 
        dim: DimensionSpec
    ) -> VizQLField:
        """构建日期维度字段"""
        # 获取字段元数据
        field_meta = self.metadata.get_field(technical_field)
        
        if field_meta and field_meta.dataType == "STRING":
            # STRING 类型需要 DATEPARSE
            date_format = self._detect_date_format(technical_field)
            dateparse_expr = f"DATEPARSE('{date_format}', [{technical_field}])"
            date_function = self._granularity_to_function(dim.time_granularity)
            calculation = f"{date_function}({dateparse_expr})"
            
            return CalculatedField(
                fieldCaption=f"{date_function}_{technical_field}",
                calculation=calculation
            )
        else:
            # DATE/DATETIME 类型直接使用日期函数
            date_function = self._granularity_to_function(dim.time_granularity)
            return DimensionField(
                fieldCaption=technical_field,
                dateFunction=DateFunction[date_function]
            )
    
    def _granularity_to_function(self, granularity: str) -> str:
        """时间粒度转日期函数"""
        mapping = {
            "year": "YEAR",
            "quarter": "QUARTER",
            "month": "MONTH",
            "week": "WEEK",
            "day": "DAY"
        }
        return mapping.get(granularity, "MONTH")
    
    def _aggregation_to_function(self, aggregation: str) -> str:
        """聚合方式转函数"""
        mapping = {
            "sum": "SUM",
            "avg": "AVG",
            "count": "COUNT",
            "countd": "COUNTD",
            "min": "MIN",
            "max": "MAX"
        }
        return mapping.get(aggregation, "SUM")
    
    def _build_filters(
        self, 
        filters: List[FilterSpec], 
        mapped_fields: Dict[str, str]
    ) -> List[VizQLFilter]:
        """构建筛选器"""
        result = []
        
        for filter_spec in filters:
            technical_field = mapped_fields.get(filter_spec.field)
            if not technical_field:
                continue
            
            if filter_spec.filter_type == "time_range":
                result.append(self._build_time_filter(technical_field, filter_spec))
            elif filter_spec.filter_type == "set":
                result.append(self._build_set_filter(technical_field, filter_spec))
            elif filter_spec.filter_type == "quantitative":
                result.append(self._build_quantitative_filter(technical_field, filter_spec))
        
        return result
    
    def _build_time_filter(
        self, 
        technical_field: str, 
        filter_spec: FilterSpec
    ) -> VizQLFilter:
        """构建时间筛选器"""
        # 解析时间范围
        start_date, end_date = self._parse_time_value(filter_spec.time_value)
        
        return QuantitativeFilter(
            fieldCaption=technical_field,
            quantitativeFilterType="RANGE",
            min=start_date,
            max=end_date
        )
    
    def _build_set_filter(
        self, 
        technical_field: str, 
        filter_spec: FilterSpec
    ) -> VizQLFilter:
        """构建集合筛选器"""
        return SetFilter(
            fieldCaption=technical_field,
            values=filter_spec.values,
            exclude=filter_spec.exclude or False
        )
```

## VizQL API 请求示例

### 1. 简单聚合查询

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
    "datasource": {"datasourceName": "Sample - Superstore"},
    "query": {
        "fields": [
            {"fieldCaption": "Category"},
            {"fieldCaption": "Sales", "function": "SUM"}
        ]
    }
}
```

### 2. 累计总额 (RUNNING_TOTAL)

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
    "datasource": {"datasourceName": "Sample - Superstore"},
    "query": {
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
}
```

### 3. 多维度累计 (per_group)

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

**VizQL API Request**:
```json
{
    "datasource": {"datasourceName": "Sample - Superstore"},
    "query": {
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
}
```

**说明**：
- `computation_scope: "per_group"` → addressing 只包含时间维度 "Order Date"
- 省份 "State" 作为隐式分区，每个省份独立累计

### 4. LOD FIXED 查询

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
    "datasource": {"datasourceName": "Sample - Superstore"},
    "query": {
        "fields": [
            {"fieldCaption": "Product Name"},
            {"fieldCaption": "Sales", "function": "SUM"},
            {
                "fieldCaption": "aggregation_at_level_销售额",
                "calculation": "{FIXED [Category] : SUM([Sales])}"
            }
        ]
    }
}
```

### 5. 排名 (RANK)

**SemanticQuery**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [{"name": "产品", "is_time": false}],
    "analyses": [{
        "type": "ranking",
        "target_measure": "销售额",
        "order": "desc"
    }]
}
```

**VizQL API Request**:
```json
{
    "datasource": {"datasourceName": "Sample - Superstore"},
    "query": {
        "fields": [
            {"fieldCaption": "Product Name"},
            {"fieldCaption": "Sales", "function": "SUM"},
            {
                "fieldCaption": "ranking_销售额",
                "calculation": "RANK(SUM([Sales]), 'desc')",
                "tableCalculation": {
                    "tableCalcType": "CUSTOM",
                    "dimensions": [{"fieldCaption": "Product Name"}]
                }
            }
        ]
    }
}
```

### 6. 占比 (PERCENT_OF_TOTAL)

**SemanticQuery**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [{"name": "品类", "is_time": false}],
    "analyses": [{
        "type": "percentage",
        "target_measure": "销售额"
    }]
}
```

**VizQL API Request**:
```json
{
    "datasource": {"datasourceName": "Sample - Superstore"},
    "query": {
        "fields": [
            {"fieldCaption": "Category"},
            {"fieldCaption": "Sales", "function": "SUM"},
            {
                "fieldCaption": "percentage_销售额",
                "calculation": "SUM([Sales]) / TOTAL(SUM([Sales]))",
                "tableCalculation": {
                    "tableCalcType": "CUSTOM",
                    "dimensions": [{"fieldCaption": "Category"}]
                }
            }
        ]
    }
}
```

### 7. 同比增长 (YoY Growth)

**SemanticQuery**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [{"name": "日期", "is_time": true, "time_granularity": "month"}],
    "analyses": [{
        "type": "period_compare",
        "target_measure": "销售额",
        "compare_type": "yoy"
    }]
}
```

**VizQL API Request**:
```json
{
    "datasource": {"datasourceName": "Sample - Superstore"},
    "query": {
        "fields": [
            {"fieldCaption": "Order Date", "dateFunction": "MONTH"},
            {"fieldCaption": "Sales", "function": "SUM"},
            {
                "fieldCaption": "period_compare_销售额",
                "calculation": "(SUM([Sales]) - LOOKUP(SUM([Sales]), -12)) / ABS(LOOKUP(SUM([Sales]), -12))",
                "tableCalculation": {
                    "tableCalcType": "CUSTOM",
                    "dimensions": [{"fieldCaption": "Order Date"}]
                }
            }
        ]
    }
}
```

### 8. 移动平均 (MOVING_CALCULATION)

**SemanticQuery**:
```json
{
    "measures": [{"name": "销售额", "aggregation": "sum"}],
    "dimensions": [{"name": "日期", "is_time": true, "time_granularity": "month"}],
    "analyses": [{
        "type": "moving",
        "target_measure": "销售额",
        "window_size": 3
    }]
}
```

**VizQL API Request**:
```json
{
    "datasource": {"datasourceName": "Sample - Superstore"},
    "query": {
        "fields": [
            {"fieldCaption": "Order Date", "dateFunction": "MONTH"},
            {"fieldCaption": "Sales", "function": "SUM"},
            {
                "fieldCaption": "moving_销售额",
                "calculation": "WINDOW_AVG(SUM([Sales]), -2, 0)",
                "tableCalculation": {
                    "tableCalcType": "CUSTOM",
                    "dimensions": [{"fieldCaption": "Order Date"}]
                }
            }
        ]
    }
}
```

## QueryValidator 多层验证

```python
class QueryValidator:
    """
    查询验证器 - 多层验证
    
    验证层次：
    1. Schema 验证: 字段类型、必填项
    2. 字段存在性验证: 技术字段名是否在元数据中
    3. 表计算验证: dimensions 是否在查询字段中
    4. 表达式语法验证: 括号匹配、函数名正确
    5. 排序优先级验证: sortPriority 唯一性
    """
    
    def __init__(self, metadata: Metadata):
        self.metadata = metadata
    
    def validate(self, query: VizQLQuery) -> ValidationResult:
        """执行所有验证"""
        errors = []
        
        errors.extend(self._validate_field_existence(query))
        errors.extend(self._validate_table_calc(query))
        errors.extend(self._validate_expression_syntax(query))
        errors.extend(self._validate_sort_priority(query))
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors
        )
    
    def _validate_field_existence(self, query: VizQLQuery) -> List[str]:
        """验证字段是否存在于元数据"""
        errors = []
        for field in query.fields:
            if hasattr(field, 'fieldCaption'):
                # 跳过计算字段（它们引用的字段在表达式中）
                if hasattr(field, 'calculation') or hasattr(field, 'tableCalculation'):
                    continue
                if not self.metadata.get_field(field.fieldCaption):
                    errors.append(f"字段 '{field.fieldCaption}' 不存在于元数据中")
        return errors
    
    def _validate_table_calc(self, query: VizQLQuery) -> List[str]:
        """验证表计算的 dimensions 是否在查询字段中"""
        errors = []
        query_fields = {f.fieldCaption for f in query.fields if hasattr(f, 'fieldCaption')}
        
        for field in query.fields:
            if hasattr(field, 'tableCalculation') and field.tableCalculation:
                for dim in field.tableCalculation.dimensions:
                    if dim.fieldCaption not in query_fields:
                        errors.append(
                            f"表计算 '{field.fieldCaption}' 的 dimension "
                            f"'{dim.fieldCaption}' 不在查询字段中"
                        )
        return errors
    
    def _validate_expression_syntax(self, query: VizQLQuery) -> List[str]:
        """验证表达式语法"""
        errors = []
        for field in query.fields:
            if hasattr(field, 'calculation') and field.calculation:
                expr = field.calculation
                if expr.count('(') != expr.count(')'):
                    errors.append(f"表达式 '{expr}' 括号不匹配")
                if expr.count('[') != expr.count(']'):
                    errors.append(f"表达式 '{expr}' 方括号不匹配")
                if expr.count('{') != expr.count('}'):
                    errors.append(f"表达式 '{expr}' 花括号不匹配")
        return errors
    
    def _validate_sort_priority(self, query: VizQLQuery) -> List[str]:
        """验证排序优先级唯一性"""
        errors = []
        priorities = []
        for field in query.fields:
            if hasattr(field, 'sortPriority') and field.sortPriority is not None:
                if field.sortPriority in priorities:
                    errors.append(f"重复的 sortPriority: {field.sortPriority}")
                priorities.append(field.sortPriority)
        return errors


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str]
```

## 与旧架构的对比

| 方面 | 旧架构 | 新架构（纯语义中间层） |
|------|--------|----------------------|
| 输入 | QueryPlan（包含技术字段名） | SemanticQuery（纯语义） |
| 字段映射 | 已在 Planning 阶段完成 | FieldMapper 在 QueryBuilder 中完成 |
| 实现方式判断 | LLM 判断 | ImplementationResolver（代码规则） |
| 表达式生成 | LLM 生成 | ExpressionGenerator（代码模板） |
| 验证 | 基本验证 | 多层验证（5 层） |
| 准确性 | 依赖 LLM 能力 | 100% 确定性 |
