# 附件D：平台适配器设计

## 概述

平台适配器负责将平台无关的 SemanticQuery 转换为具体平台的查询语句。

## 适配器接口

```python
from abc import ABC, abstractmethod

class BasePlatformAdapter(ABC):
    """平台适配器基类"""
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """平台名称"""
        pass
    
    @abstractmethod
    async def execute_query(
        self,
        semantic_query: SemanticQuery,
        datasource_id: str
    ) -> QueryResult:
        """执行语义查询"""
        pass
    
    @abstractmethod
    def build_query(
        self,
        semantic_query: SemanticQuery
    ) -> Any:
        """将语义查询转换为平台特定查询"""
        pass
    
    @abstractmethod
    def validate_query(
        self,
        semantic_query: SemanticQuery
    ) -> ValidationResult:
        """验证语义查询"""
        pass
```

## Tableau 适配器

### 核心转换逻辑

```python
class TableauAdapter(BasePlatformAdapter):
    """Tableau 平台适配器"""
    
    @property
    def platform_name(self) -> str:
        return "Tableau"
    
    def build_query(self, semantic_query: SemanticQuery) -> VizQLQueryRequest:
        """将 SemanticQuery 转换为 VizQL 请求"""
        
        fields = []
        
        # 转换维度
        for dim in semantic_query.dimensions or []:
            fields.append(self._build_dimension_field(dim))
        
        # 转换度量
        for measure in semantic_query.measures or []:
            fields.append(self._build_measure_field(measure))
        
        # 转换计算
        for computation in semantic_query.computations or []:
            fields.append(self._build_computation_field(computation, semantic_query))
        
        # 转换筛选
        filters = [self._build_filter(f) for f in semantic_query.filters or []]
        
        return VizQLQueryRequest(fields=fields, filters=filters)
```

### partition_by → Tableau 表计算

```python
def _build_computation_field(
    self,
    computation: Computation,
    semantic_query: SemanticQuery
) -> dict:
    """将 Computation 转换为 Tableau 表计算字段"""
    
    # 获取视图维度
    view_dimensions = [d.field_name for d in semantic_query.dimensions or []]
    
    # 计算 Partitioning 和 Addressing
    partitioning = computation.partition_by
    addressing = [d for d in view_dimensions if d not in partitioning]
    
    # 根据操作类型构建表计算
    match computation.operation.type:
        case OperationType.RANK:
            return self._build_rank_table_calc(
                computation.target,
                partitioning,
                addressing
            )
        
        case OperationType.RUNNING_SUM:
            return self._build_running_sum_table_calc(
                computation.target,
                partitioning,
                addressing
            )
        
        case OperationType.PERCENT:
            return self._build_percent_table_calc(
                computation.target,
                partitioning,
                addressing
            )
        
        case OperationType.YEAR_AGO:
            return self._build_year_ago_table_calc(
                computation.target,
                partitioning,
                addressing,
                computation.operation.params
            )
        
        case OperationType.FIXED:
            return self._build_lod_field(
                computation.target,
                computation.partition_by
            )


def _build_rank_table_calc(
    self,
    target: str,
    partitioning: list[str],
    addressing: list[str]
) -> dict:
    """构建排名表计算
    
    RANK 不支持 restartEvery，分区语义通过 dimensions 表达
    """
    return {
        "fieldCaption": f"{target}_排名",
        "function": "SUM",
        "fieldName": target,
        "tableCalculation": {
            "tableCalcType": "RANK",
            "direction": "DESC",
            "dimensions": [{"fieldCaption": d} for d in partitioning]  # partitioning
        }
    }


def _build_running_sum_table_calc(
    self,
    target: str,
    partitioning: list[str],
    addressing: list[str]
) -> dict:
    """构建累计表计算
    
    RUNNING_TOTAL 支持 restartEvery，这里使用 dimensions 表达分区
    """
    return {
        "fieldCaption": f"{target}_累计",
        "function": "SUM",
        "fieldName": target,
        "tableCalculation": {
            "tableCalcType": "RUNNING_TOTAL",
            "dimensions": [{"fieldCaption": d} for d in partitioning]  # partitioning
        }
    }


def _build_percent_table_calc(
    self,
    target: str,
    partitioning: list[str],
    addressing: list[str]
) -> dict:
    """构建占比表计算
    
    PERCENT_OF_TOTAL 不支持 restartEvery，分区语义通过 dimensions 表达
    """
    return {
        "fieldCaption": f"{target}_占比",
        "function": "SUM",
        "fieldName": target,
        "tableCalculation": {
            "tableCalcType": "PERCENT_OF_TOTAL",
            "dimensions": [{"fieldCaption": d} for d in partitioning]  # partitioning
        }
    }


def _build_lod_field(
    self,
    target: str,
    fixed_dimensions: list[str]
) -> dict:
    """构建 LOD 表达式字段"""
    dims_str = ", ".join(f"[{d}]" for d in fixed_dimensions)
    calculation = f"{{FIXED {dims_str}: SUM([{target}])}}"
    
    return {
        "fieldCaption": f"{target}_固定",
        "calculation": calculation
    }
```

## Power BI 适配器

### 核心转换逻辑

```python
class PowerBIAdapter(BasePlatformAdapter):
    """Power BI 平台适配器"""
    
    @property
    def platform_name(self) -> str:
        return "Power BI"
    
    def build_query(self, semantic_query: SemanticQuery) -> DAXQuery:
        """将 SemanticQuery 转换为 DAX 查询"""
        
        measures = []
        
        # 转换基础度量
        for measure in semantic_query.measures or []:
            measures.append(self._build_measure(measure))
        
        # 转换计算
        for computation in semantic_query.computations or []:
            measures.append(self._build_computation_measure(computation, semantic_query))
        
        return DAXQuery(
            dimensions=[d.field_name for d in semantic_query.dimensions or []],
            measures=measures,
            filters=self._build_filters(semantic_query.filters)
        )
```

### partition_by → Power BI DAX

```python
def _build_computation_measure(
    self,
    computation: Computation,
    semantic_query: SemanticQuery
) -> str:
    """将 Computation 转换为 DAX 度量"""
    
    view_dimensions = [d.field_name for d in semantic_query.dimensions or []]
    partition_by = computation.partition_by
    
    match computation.operation.type:
        case OperationType.RANK:
            return self._build_rank_dax(computation.target, partition_by, view_dimensions)
        
        case OperationType.RUNNING_SUM:
            return self._build_running_sum_dax(computation.target, partition_by)
        
        case OperationType.PERCENT:
            return self._build_percent_dax(computation.target, partition_by)
        
        case OperationType.YEAR_AGO:
            return self._build_year_ago_dax(computation.target, computation.operation.params)
        
        case OperationType.FIXED:
            return self._build_fixed_dax(computation.target, partition_by)


def _build_rank_dax(
    self,
    target: str,
    partition_by: list[str],
    view_dimensions: list[str]
) -> str:
    """构建排名 DAX"""
    
    if not partition_by:
        # 全局排名
        return f"""
        RANKX(
            ALL({view_dimensions[0]}),
            [Sum of {target}],
            ,
            DESC
        )
        """
    else:
        # 分区排名
        except_dims = ", ".join(partition_by)
        return f"""
        RANKX(
            ALLEXCEPT(Table, {except_dims}),
            [Sum of {target}],
            ,
            DESC
        )
        """


def _build_percent_dax(
    self,
    target: str,
    partition_by: list[str]
) -> str:
    """构建占比 DAX"""
    
    if not partition_by:
        # 占全局
        return f"""
        DIVIDE(
            [Sum of {target}],
            CALCULATE([Sum of {target}], ALL())
        )
        """
    else:
        # 占分区
        except_dims = ", ".join(partition_by)
        return f"""
        DIVIDE(
            [Sum of {target}],
            CALCULATE([Sum of {target}], ALLEXCEPT(Table, {except_dims}))
        )
        """


def _build_year_ago_dax(
    self,
    target: str,
    params: dict
) -> str:
    """构建同比 DAX"""
    
    calculation = params.get("calculation", "VALUE")
    
    if calculation == "VALUE":
        return f"CALCULATE([Sum of {target}], SAMEPERIODLASTYEAR(Date[Date]))"
    elif calculation == "GROWTH_RATE":
        return f"""
        VAR CurrentValue = [Sum of {target}]
        VAR LastYearValue = CALCULATE([Sum of {target}], SAMEPERIODLASTYEAR(Date[Date]))
        RETURN DIVIDE(CurrentValue - LastYearValue, LastYearValue)
        """


def _build_fixed_dax(
    self,
    target: str,
    fixed_dimensions: list[str]
) -> str:
    """构建固定粒度 DAX"""
    
    dims = ", ".join(fixed_dimensions)
    return f"CALCULATE([Sum of {target}], ALLEXCEPT(Table, {dims}))"
```

## SQL 适配器

### 核心转换逻辑

```python
class SQLAdapter(BasePlatformAdapter):
    """SQL 平台适配器"""
    
    @property
    def platform_name(self) -> str:
        return "SQL"
    
    def build_query(self, semantic_query: SemanticQuery) -> str:
        """将 SemanticQuery 转换为 SQL"""
        
        # 基础 SELECT
        select_columns = []
        
        # 维度
        for dim in semantic_query.dimensions or []:
            select_columns.append(self._build_dimension_column(dim))
        
        # 度量
        for measure in semantic_query.measures or []:
            select_columns.append(self._build_measure_column(measure))
        
        # 计算
        for computation in semantic_query.computations or []:
            select_columns.append(self._build_computation_column(computation, semantic_query))
        
        # 构建完整 SQL
        sql = f"SELECT {', '.join(select_columns)}"
        sql += f" FROM {self.table_name}"
        
        # WHERE
        if semantic_query.filters:
            sql += f" WHERE {self._build_where_clause(semantic_query.filters)}"
        
        # GROUP BY
        if semantic_query.dimensions:
            group_by = [d.field_name for d in semantic_query.dimensions]
            sql += f" GROUP BY {', '.join(group_by)}"
        
        return sql
```

### partition_by → SQL OVER

```python
def _build_computation_column(
    self,
    computation: Computation,
    semantic_query: SemanticQuery
) -> str:
    """将 Computation 转换为 SQL 列"""
    
    view_dimensions = [d.field_name for d in semantic_query.dimensions or []]
    partition_by = computation.partition_by
    
    match computation.operation.type:
        case OperationType.RANK:
            return self._build_rank_sql(computation.target, partition_by, view_dimensions)
        
        case OperationType.RUNNING_SUM:
            return self._build_running_sum_sql(computation.target, partition_by, view_dimensions)
        
        case OperationType.PERCENT:
            return self._build_percent_sql(computation.target, partition_by)
        
        case OperationType.YEAR_AGO:
            return self._build_year_ago_sql(computation.target, partition_by, computation.operation.params)


def _build_rank_sql(
    self,
    target: str,
    partition_by: list[str],
    view_dimensions: list[str]
) -> str:
    """构建排名 SQL"""
    
    over_clause = self._build_over_clause(partition_by, f"SUM({target}) DESC")
    return f"RANK() {over_clause} AS {target}_rank"


def _build_running_sum_sql(
    self,
    target: str,
    partition_by: list[str],
    view_dimensions: list[str]
) -> str:
    """构建累计 SQL"""
    
    # 确定排序维度（通常是时间维度）
    order_by = [d for d in view_dimensions if d not in partition_by][0]
    
    partition_clause = f"PARTITION BY {', '.join(partition_by)}" if partition_by else ""
    
    return f"""
    SUM(SUM({target})) OVER (
        {partition_clause}
        ORDER BY {order_by}
        ROWS UNBOUNDED PRECEDING
    ) AS {target}_running_sum
    """


def _build_percent_sql(
    self,
    target: str,
    partition_by: list[str]
) -> str:
    """构建占比 SQL"""
    
    partition_clause = f"PARTITION BY {', '.join(partition_by)}" if partition_by else ""
    
    return f"""
    SUM({target}) * 1.0 / SUM(SUM({target})) OVER ({partition_clause}) AS {target}_percent
    """


def _build_year_ago_sql(
    self,
    target: str,
    partition_by: list[str],
    params: dict
) -> str:
    """构建同比 SQL"""
    
    partition_clause = f"PARTITION BY {', '.join(partition_by)}" if partition_by else ""
    calculation = params.get("calculation", "VALUE")
    
    if calculation == "VALUE":
        return f"""
        LAG(SUM({target}), 12) OVER ({partition_clause} ORDER BY date_column) AS {target}_year_ago
        """
    elif calculation == "GROWTH_RATE":
        return f"""
        (SUM({target}) - LAG(SUM({target}), 12) OVER ({partition_clause} ORDER BY date_column)) 
        / NULLIF(LAG(SUM({target}), 12) OVER ({partition_clause} ORDER BY date_column), 0) 
        AS {target}_yoy_growth
        """


def _build_over_clause(
    self,
    partition_by: list[str],
    order_by: str | None = None
) -> str:
    """构建 OVER 子句"""
    
    parts = []
    
    if partition_by:
        parts.append(f"PARTITION BY {', '.join(partition_by)}")
    
    if order_by:
        parts.append(f"ORDER BY {order_by}")
    
    return f"OVER ({' '.join(parts)})"
```

## 验证结果模型

```python
class ValidationResult(BaseModel):
    """验证结果"""
    
    is_valid: bool
    """是否验证通过"""
    
    errors: list[ValidationError] = []
    """错误列表"""
    
    warnings: list[str] = []
    """警告列表"""
    
    auto_fixed: bool = False
    """是否进行了自动修正"""
```

## 平台映射总结

### 计算类型映射

| OperationType | partition_by | Tableau | Power BI | SQL |
|---------------|--------------|---------|----------|-----|
| RANK | [] | RANK() Addressing=全部 | RANKX(ALL()) | RANK() OVER () |
| RANK | [月份] | RANK() Partitioning=月份 | RANKX(ALLEXCEPT(月份)) | RANK() OVER (PARTITION BY 月份) |
| DENSE_RANK | [] | RANK(DENSE) | RANKX(..., DENSE) | DENSE_RANK() OVER () |
| PERCENT | [] | PERCENT_OF_TOTAL() | DIVIDE + ALL() | SUM()/SUM() OVER () |
| PERCENT | [月份] | PERCENT_OF_TOTAL() Partitioning=月份 | DIVIDE + ALLEXCEPT(月份) | SUM()/SUM() OVER (PARTITION BY 月份) |
| RUNNING_SUM | [] | RUNNING_SUM() | CALCULATE + FILTER | SUM() OVER (ORDER BY) |
| RUNNING_SUM | [省份] | RUNNING_SUM() Partitioning=省份 | CALCULATE + FILTER + ALLEXCEPT | SUM() OVER (PARTITION BY 省份 ORDER BY) |
| RUNNING_AVG | [] | RUNNING_AVG() | CALCULATE + FILTER | AVG() OVER (ORDER BY) |
| MOVING_AVG | [] | WINDOW_AVG() | AVERAGEX + DATESINPERIOD | AVG() OVER (ROWS N PRECEDING) |
| MOVING_SUM | [] | WINDOW_SUM() | SUMX + DATESINPERIOD | SUM() OVER (ROWS N PRECEDING) |
| YEAR_AGO | [省份] | LOOKUP(-1, YEAR) | SAMEPERIODLASTYEAR | LAG() OVER (PARTITION BY 省份) |
| PERIOD_AGO | [省份] | LOOKUP(-1) | DATEADD | LAG() OVER (PARTITION BY 省份) |
| DIFFERENCE | [] | 当前值 - LOOKUP(-1) | 当前值 - 上期值 | 当前值 - LAG() |
| GROWTH_RATE | [] | (当前-上期)/上期 | DIVIDE(当前-上期, 上期) | (当前-LAG())/LAG() |
| FIXED | [客户] | {FIXED [客户]: SUM()} | CALCULATE + ALLEXCEPT(客户) | 子查询 |

### FIXED 类型的特殊处理

`FIXED` 是粒度类操作，平台适配器根据 `partition_by` 与视图维度的关系，自动决定具体实现：

| partition_by 与视图维度关系 | Tableau LOD 类型 | 说明 |
|---------------------------|-----------------|------|
| partition_by 与视图维度无关 | FIXED | 固定到指定粒度 |
| partition_by 是视图维度的子集 | EXCLUDE | 排除某些维度，更粗粒度 |
| partition_by 包含视图维度外的字段 | INCLUDE | 包含额外维度，更细粒度 |

```python
def determine_lod_type(partition_by: list[str], view_dimensions: list[str]) -> str:
    """根据 partition_by 与视图维度的关系，决定 LOD 类型"""
    
    partition_set = set(partition_by)
    view_set = set(view_dimensions)
    
    if partition_set == view_set:
        return "NONE"  # 视图粒度，无需 LOD
    elif partition_set.issubset(view_set):
        return "EXCLUDE"  # 排除某些维度
    elif partition_set.issuperset(view_set):
        return "INCLUDE"  # 包含额外维度
    else:
        return "FIXED"  # 完全独立的粒度
```
