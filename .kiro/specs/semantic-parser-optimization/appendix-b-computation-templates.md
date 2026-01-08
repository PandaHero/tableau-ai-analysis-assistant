# 附录 B: 计算模板库

## 概述

`ComputationPlanner` 使用模板库处理常见计算场景，只有模板无法覆盖时才调用 Step2 LLM。

## 内部 IR 与 OpenAPI 映射

内部 IR 使用 `calc_type`，最终转换为 OpenAPI 的 `tableCalcType`：

| 内部 calc_type | OpenAPI tableCalcType | 说明 |
|----------------|----------------------|------|
| `PERCENT_OF_TOTAL` | `PERCENT_OF_TOTAL` | 占比 |
| `RANK` | `RANK` | 排名 |
| `DENSE_RANK` | `RANK` (rankType=DENSE) | 密集排名 |
| `RUNNING_TOTAL` | `RUNNING_TOTAL` | 累计 |
| `MOVING_CALC` | `MOVING_CALCULATION` | 移动计算 |
| `DIFFERENCE` | `DIFFERENCE_FROM` | 差异 |
| `PERCENT_DIFFERENCE` | `PERCENT_DIFFERENCE_FROM` | 百分比差异 |
| `PERCENTILE` | `PERCENTILE` | 百分位 |
| `LOD_FIXED` | N/A (LOD 表达式) | 固定 LOD |
| `LOD_INCLUDE` | N/A (LOD 表达式) | 包含 LOD |
| `LOD_EXCLUDE` | N/A (LOD 表达式) | 排除 LOD |

## ⚠️ restartEvery 支持矩阵（关键约束）

**只有以下类型支持 `restartEvery` 字段**：

| tableCalcType | restartEvery | 分区方式 |
|---------------|--------------|----------|
| `RUNNING_TOTAL` | ✅ 支持 | 可用 restartEvery 或 dimensions |
| `CUSTOM` | ✅ 支持 | 可用 restartEvery 或 dimensions |
| `NESTED` | ✅ 支持 | 可用 restartEvery 或 dimensions |
| `PERCENT_OF_TOTAL` | ❌ 不支持 | 只能用 dimensions |
| `RANK` | ❌ 不支持 | 只能用 dimensions |
| `PERCENTILE` | ❌ 不支持 | 只能用 dimensions |
| `MOVING_CALCULATION` | ❌ 不支持 | 只能用 dimensions |
| `DIFFERENCE_FROM` | ❌ 不支持 | 只能用 dimensions |
| `PERCENT_DIFFERENCE_FROM` | ❌ 不支持 | 只能用 dimensions |

**设计约束**：
- 对于不支持 `restartEvery` 的类型，`partition_by` 必须映射到 `dimensions`
- 对于支持 `restartEvery` 的类型，可以选择使用 `dimensions` 或 `restartEvery` 表达分区语义

## LOD vs 表计算决策框架

基于 `computations.py` 中的决策框架，核心原则是：

```
Step 1 - 问题是否需要与查询不同粒度的指标？
  YES → LOD
    - LOD_FIXED: 指标锚定到特定维度（如"每客户销售额"）
    - LOD_INCLUDE: 需要更细粒度（添加维度）
    - LOD_EXCLUDE: 需要更粗粒度（移除维度）
  NO → 继续 Step 2

Step 2 - 问题是否需要对查询结果进行变换？
  YES → 表计算
    - RANK/DENSE_RANK/PERCENTILE: 排名
    - RUNNING_TOTAL: 累计（YTD、累计求和）
    - MOVING_CALC: 滑动窗口（移动平均）
    - PERCENT_OF_TOTAL: 占比/份额
    - DIFFERENCE/PERCENT_DIFFERENCE: 比较（MoM、YoY）
  NO → 基础聚合（无需 Computation）

组合场景（LOD + 表计算）：
当问题同时需要不同粒度和变换时。
示例："按首购日期对客户排名"
→ [LOD_FIXED 获取首购日期, 然后 RANK]
输出顺序：先 LOD，后表计算
```

## 关键规则

### 1. 占比/份额 → PERCENT_OF_TOTAL（表计算）

**不要用 LOD 计算总量来做占比**，直接使用 `PERCENT_OF_TOTAL`：

| 问题 | 正确做法 | 错误做法 |
|------|----------|----------|
| "各地区销售额占比" | `PERCENT_OF_TOTAL(target=Sales, partition_by=[])` | ❌ LOD_FIXED 算总量再除 |
| "各产品在地区内占比" | `PERCENT_OF_TOTAL(target=Sales, partition_by=[Region])` | ❌ LOD_EXCLUDE 算地区总量 |

### 2. LOD 只用于粒度改变场景

| 场景 | LOD 类型 | 示例 |
|------|----------|------|
| 每客户生命周期销售额 | LOD_FIXED | `dimensions=[CustomerID], aggregation=SUM` |
| 首购日期 | LOD_FIXED | `target=OrderDate, dimensions=[CustomerID], aggregation=MIN` |
| 查询粒度太粗，需下钻 | LOD_INCLUDE | 按地区查询时算"平均订单金额" |
| 查询粒度太细，需上卷 | LOD_EXCLUDE | 按子类别查询时算"类别总量" |

### 3. 组合规则：先 LOD 后表计算

```python
# 正确：LOD 在前，表计算在后
computations = [
    LODFixed(target="OrderDate", dimensions=["CustomerID"], aggregation="MIN", alias="FirstPurchase"),
    RankCalc(target="FirstPurchase", partition_by=[], direction="ASC"),
]

# 错误：表计算在前
computations = [
    RankCalc(...),  # ❌ 不能先做表计算
    LODFixed(...),
]
```

## 模板库

### 1. 占比/份额（PERCENT_OF_TOTAL）

**触发模式**: `占比|份额|比例|百分比|share|proportion|percent`

```python
# 全局占比
{
    "calc_type": "PERCENT_OF_TOTAL",
    "target": "Sales",
    "partition_by": []  # 空 = 全局总计占比
}

# 分组内占比（按地区分区）
{
    "calc_type": "PERCENT_OF_TOTAL",
    "target": "Sales",
    "partition_by": [{"field_name": "Region"}]  # 在地区内占比
}
```

**API 输出示例（分组内占比）**:
```json
{
  "tableCalcType": "PERCENT_OF_TOTAL",
  "dimensions": [{"fieldCaption": "Region"}]
}
```

**⚠️ 注意**: `PERCENT_OF_TOTAL` 不支持 `restartEvery`，分区只能通过 `dimensions` 表达。

**约束**: `partition_by ⊆ query_dimensions`（分区字段必须是查询维度的子集）

### 2. 同比（YoY - PERCENT_DIFFERENCE）

**触发模式**: `同比|YoY|year.over.year|去年同期|较去年`

```python
{
    "calc_type": "PERCENT_DIFFERENCE",
    "target": "Sales",
    "partition_by": [{"field_name": "Order Date", "date_granularity": "YEAR"}],
    "relative_to": "PREVIOUS"
}
```

**API 输出示例**:
```json
{
  "tableCalcType": "PERCENT_DIFFERENCE_FROM",
  "dimensions": [{"fieldCaption": "Order Date", "function": "YEAR"}],
  "relativeTo": "PREVIOUS"
}
```

**⚠️ date_granularity 到 OpenAPI 映射**：
- 内部 IR 的 `date_granularity: "YEAR"` 映射到 OpenAPI 的 `function: "YEAR"`
- 内部 IR 的 `date_granularity: "MONTH"` 映射到 OpenAPI 的 `function: "MONTH"`
- 如果数据源已有派生维度字段（如 "Order Year"），则直接使用该字段，无需 function

**⚠️ 注意**: `PERCENT_DIFFERENCE_FROM` 不支持 `restartEvery`，分区只能通过 `dimensions` 表达。

**前置条件**: 查询必须包含时间维度

### 3. 环比（MoM - PERCENT_DIFFERENCE）

**触发模式**: `环比|MoM|month.over.month|上月|较上月`

```python
{
    "calc_type": "PERCENT_DIFFERENCE",
    "target": "Sales",
    "partition_by": [{"field_name": "Order Date", "date_granularity": "MONTH"}],
    "relative_to": "PREVIOUS"
}
```

**API 输出示例**:
```json
{
  "tableCalcType": "PERCENT_DIFFERENCE_FROM",
  "dimensions": [{"fieldCaption": "Order Date", "function": "MONTH"}],
  "relativeTo": "PREVIOUS"
}
```

**⚠️ 注意**: `PERCENT_DIFFERENCE_FROM` 不支持 `restartEvery`。

### 4. 排名（RANK）

**触发模式**: `排名|排行|top|前\d+|rank`

```python
# 全局排名
{
    "calc_type": "RANK",
    "target": "Sales",
    "partition_by": [],  # 空 = 全局排名
    "direction": "DESC"  # 销售额高的排名靠前
}

# 分组内排名（按地区分区）
{
    "calc_type": "RANK",
    "target": "Sales",
    "partition_by": [{"field_name": "Region"}],  # 在地区内排名
    "direction": "DESC"
}

# Top N
{
    "calc_type": "RANK",
    "target": "Sales",
    "partition_by": [],
    "direction": "DESC",
    "top_n": 10
}
```

**API 输出示例（分组内排名）**:
```json
{
  "tableCalcType": "RANK",
  "dimensions": [{"fieldCaption": "Region"}],
  "rankType": "COMPETITION",
  "direction": "DESC"
}
```

**⚠️ 注意**: `RANK` 不支持 `restartEvery`，分区只能通过 `dimensions` 表达。

### 5. 累计/YTD（RUNNING_TOTAL）

**触发模式**: `累计|累积|YTD|年初至今|running|cumulative`

```python
# 累计求和（全局）
{
    "calc_type": "RUNNING_TOTAL",
    "target": "Sales",
    "partition_by": [],  # 空 = 全局累计
    "aggregation": "SUM"
}

# YTD（年初至今）- ✅ RUNNING_TOTAL 支持 restart_every
{
    "calc_type": "RUNNING_TOTAL",
    "target": "Sales",
    "partition_by": [],
    "aggregation": "SUM",
    "restart_every": "Year"  # ✅ 每年重新开始（仅 RUNNING_TOTAL 支持）
}

# MTD（月初至今）- ✅ RUNNING_TOTAL 支持 restart_every
{
    "calc_type": "RUNNING_TOTAL",
    "target": "Sales",
    "partition_by": [],
    "aggregation": "SUM",
    "restart_every": "Month"  # ✅ 每月重新开始
}

# 按地区分区的累计（✅ 统一使用 restart_every 表达分区）
# 设计决策：RUNNING_TOTAL 统一使用 restartEvery 方式，不使用 dimensions 表达分区
{
    "calc_type": "RUNNING_TOTAL",
    "target": "Sales",
    "partition_by": [],
    "aggregation": "SUM",
    "restart_every": "Region"  # ✅ 按地区分区（通过 restartEvery）
}
```

**API 输出示例（按地区分区的累计）**:
```json
{
  "tableCalcType": "RUNNING_TOTAL",
  "dimensions": [],
  "restartEvery": {"fieldCaption": "Region"},
  "aggregation": "SUM"
}
```

**⚠️ 设计决策**：RUNNING_TOTAL 同时支持 `restartEvery` 和 `dimensions` 两种分区表达方式，为保证生成一致性，本系统统一采用 `restartEvery` 方式。详见 design.md 4.3 节场景 4 说明。

### 6. 移动平均（MOVING_CALC）

**触发模式**: `移动平均|滚动平均|MA|moving.average|rolling`

```python
# 3期移动平均（全局）
{
    "calc_type": "MOVING_CALC",
    "target": "Sales",
    "partition_by": [],  # 空 = 全局
    "aggregation": "AVG",
    "window_previous": 2,  # 前2期
    "window_next": 0,      # 后0期
    "include_current": true  # 包含当前 = 共3期
}

# 7日滚动求和
{
    "calc_type": "MOVING_CALC",
    "target": "Sales",
    "partition_by": [],
    "aggregation": "SUM",
    "window_previous": 6,
    "window_next": 0,
    "include_current": true
}

# 按地区分区的移动平均
# ⚠️ 注意：MOVING_CALCULATION 不支持 restart_every！
# 分区语义通过 partition_by → dimensions 表达
{
    "calc_type": "MOVING_CALC",
    "target": "Sales",
    "partition_by": [{"field_name": "Region"}],  # 按地区分区
    "aggregation": "AVG",
    "window_previous": 2,
    "window_next": 0,
    "include_current": true
}
```

**API 输出示例（按地区分区）**:
```json
{
  "tableCalcType": "MOVING_CALCULATION",
  "dimensions": [{"fieldCaption": "Region"}],
  "aggregation": "AVG",
  "previous": 2,
  "next": 0,
  "includeCurrent": true
}
```

**⚠️ 注意**: `MOVING_CALCULATION` 不支持 `restartEvery`，分区只能通过 `dimensions` 表达。

### 7. 每客户/首购（LOD_FIXED）

**触发模式**: `每客户|客户生命周期|首购|首次|per.customer|lifetime|first`

```python
# 每客户销售额
{
    "calc_type": "LOD_FIXED",
    "target": "Sales",
    "dimensions": ["CustomerID"],
    "aggregation": "SUM",
    "alias": "CustomerLifetimeValue"
}

# 首购日期
{
    "calc_type": "LOD_FIXED",
    "target": "OrderDate",
    "dimensions": ["CustomerID"],
    "aggregation": "MIN",
    "alias": "FirstPurchaseDate"
}

# 首单金额
{
    "calc_type": "LOD_FIXED",
    "target": "Sales",
    "dimensions": ["CustomerID", "OrderDate"],
    "aggregation": "SUM",
    "alias": "FirstOrderAmount"
}
```

## 模板匹配实现

```python
class ComputationPlanner:
    """计算规划器 - 模板优先"""
    
    TEMPLATES = [
        # 占比/份额 → PERCENT_OF_TOTAL
        {
            "pattern": r"(占比|份额|比例|百分比|share|proportion|percent)",
            "builder": "_build_percent_of_total",
            "priority": 1,
        },
        # 同比 → PERCENT_DIFFERENCE (YoY)
        {
            "pattern": r"(同比|YoY|year.over.year|去年同期|较去年)",
            "builder": "_build_yoy",
            "priority": 2,
        },
        # 环比 → PERCENT_DIFFERENCE (MoM)
        {
            "pattern": r"(环比|MoM|month.over.month|上月|较上月)",
            "builder": "_build_mom",
            "priority": 2,
        },
        # 排名 → RANK
        {
            "pattern": r"(排名|排行|top\s*\d*|前\d+|rank)",
            "builder": "_build_rank",
            "priority": 3,
        },
        # 累计/YTD → RUNNING_TOTAL
        {
            "pattern": r"(累计|累积|YTD|年初至今|MTD|月初至今|running|cumulative)",
            "builder": "_build_running_total",
            "priority": 4,
        },
        # 移动平均 → MOVING_CALC
        {
            "pattern": r"(移动平均|滚动平均|MA|moving.average|rolling)",
            "builder": "_build_moving_calc",
            "priority": 5,
        },
        # 每客户/首购 → LOD_FIXED
        {
            "pattern": r"(每客户|客户生命周期|首购|首次|per.customer|lifetime|first)",
            "builder": "_build_lod_fixed",
            "priority": 6,
        },
    ]
    
    def plan(
        self,
        step1_output: Step1Output,
        data_model: DataModel,
        canonical_question: str,  # 从 state.preprocess_result 传入
    ) -> tuple[list[Computation], bool]:
        """
        规划计算
        
        Args:
            step1_output: Step1 输出
            data_model: 数据模型
            canonical_question: 规范化问题（从 state.preprocess_result.canonical_question 获取）
        
        Returns:
            (computations, needs_llm_fallback)
        """
        if step1_output.how_type == HowType.SIMPLE:
            return [], False
        
        # ⚠️ canonical_question 从参数传入，不从 step1_output 获取
        # 遵循"单一事实来源"原则：canonical_question 由 PreprocessResult 产出
        question = canonical_question
        
        # 按优先级尝试模板匹配
        for template in sorted(self.TEMPLATES, key=lambda t: t["priority"]):
            if re.search(template["pattern"], question, re.I):
                builder = getattr(self, template["builder"])
                try:
                    computation = builder(step1_output, data_model)
                    return [computation], False
                except ValueError as e:
                    # 模板无法处理，继续尝试下一个
                    logger.debug(f"模板 {template['builder']} 无法处理: {e}")
                    continue
        
        # 无法匹配，需要 LLM fallback
        return [], True
```

## partition_by 推断规则

`partition_by` 必须是查询维度的子集：

```python
def _infer_partition_by(
    self,
    step1_output: Step1Output,
    computation_type: str,
) -> list[DimensionField]:
    """推断 partition_by"""
    query_dims = step1_output.where.dimensions
    
    if computation_type in ["PERCENT_OF_TOTAL"]:
        # 占比：默认全局（空），或按非时间维度分组
        non_time_dims = [d for d in query_dims if not d.date_granularity]
        return non_time_dims[:1] if non_time_dims else []
    
    elif computation_type in ["PERCENT_DIFFERENCE", "DIFFERENCE"]:
        # 同比/环比：按时间维度分组
        time_dims = [d for d in query_dims if d.date_granularity]
        return time_dims[:1] if time_dims else []
    
    elif computation_type in ["RANK", "RUNNING_TOTAL", "MOVING_CALC"]:
        # 排名/累计/移动：默认全局
        return []
    
    return []
```

## 层级信息辅助决策

维度层级信息可以帮助更准确地推断 `partition_by` 和 LOD 维度：

```python
def _use_hierarchy_for_partition(
    self,
    step1_output: Step1Output,
    hierarchy_info: dict,
) -> list[DimensionField]:
    """使用层级信息推断 partition_by"""
    # 示例：如果查询包含 [Region, State, City]
    # 且层级是 Region > State > City
    # 则 partition_by 应该是更高层级的维度
    
    query_dims = step1_output.where.dimensions
    
    for dim in query_dims:
        if dim.field_name in hierarchy_info:
            parent = hierarchy_info[dim.field_name].get("parent")
            if parent and parent in [d.field_name for d in query_dims]:
                return [DimensionField(field_name=parent)]
    
    return []
```

## 模板覆盖率目标

| 计算类型 | 预期覆盖率 | 说明 |
|----------|------------|------|
| 占比/份额 | 95% | 模式明确 |
| 同比/环比 | 90% | 需要时间维度 |
| 排名 | 85% | Top N 变体多 |
| 累计/YTD | 90% | 模式明确 |
| 移动平均 | 80% | 窗口大小变化 |
| LOD | 70% | 场景复杂 |

**总体目标**: 模板覆盖 80%+ 的计算场景，Step2 LLM 只处理长尾。
