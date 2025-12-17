# 附件B：Step 2 详细设计

## 概述

Step 2 的核心任务是：**计算上下文推理**

基于 Step 1 的三元组，推断复杂计算的分区维度（partition_by），生成完整的计算定义。

## 触发条件

```python
if step1_output.how.type != HowType.SIMPLE:
    step2_output = await step2_reasoning(step1_output)
else:
    step2_output = None  # 简单查询，跳过 Step 2
```

## 输入定义

Step 1 的完整输出

## 输出定义

```python
class Step2Output(BaseModel):
    """Step 2 输出 - 计算定义"""
    computations: list[Computation]


class Computation(BaseModel):
    """计算 = 目标 × 分区 × 操作"""
    
    target: str
    """计算目标（度量字段）"""
    
    partition_by: list[str]
    """分区维度
    
    - [] = 全局（所有数据一起计算）
    - ["月份"] = 按月份分区
    - 视图维度全部 = 视图粒度
    
    计算方向 = 视图维度 - 分区维度
    """
    
    operation: Operation
    """计算操作"""


class Operation(BaseModel):
    type: OperationType
    params: dict = {}


class OperationType(str, Enum):
    # 排名类
    RANK = "RANK"
    DENSE_RANK = "DENSE_RANK"
    TOP_N = "TOP_N"
    
    # 累计类
    RUNNING_SUM = "RUNNING_SUM"
    RUNNING_AVG = "RUNNING_AVG"
    
    # 移动类
    MOVING_AVG = "MOVING_AVG"
    MOVING_SUM = "MOVING_SUM"
    
    # 比较类
    PERCENT = "PERCENT"
    DIFFERENCE = "DIFFERENCE"
    GROWTH_RATE = "GROWTH_RATE"
    
    # 时间比较类
    YEAR_AGO = "YEAR_AGO"
    PERIOD_AGO = "PERIOD_AGO"
    
    # 粒度类
    FIXED = "FIXED"
```

## 核心概念：partition_by

### partition_by 的本质

partition_by 回答的问题是：**"哪些维度保持不变，在剩余维度上计算"**

这与 Tableau 的 Partitioning 概念完全对应：
- partition_by = Partitioning 维度
- 计算方向 = 视图维度 - partition_by = Addressing 维度

### partition_by 与粒度的关系

| partition_by | 含义 | 等价粒度 |
|--------------|------|----------|
| `[]` | 全局 | ALL |
| `["月份"]` | 按月份分区 | FIXED(月份) |
| `["省份", "月份"]` | 视图粒度 | VIEW |

### 平台映射

| partition_by | Tableau | Power BI | SQL |
|--------------|---------|----------|-----|
| `[]` | Partitioning=无 | ALL() | OVER () |
| `["月份"]` | Partitioning=月份 | ALLEXCEPT(月份) | PARTITION BY 月份 |
| `["省份", "月份"]` | Partitioning=全部 | VALUES() | 无 OVER |

## Prompt 设计

```
你是一个数据分析计算专家。

### 任务 ###
基于 Step 1 的三元组，推理出完整的计算定义。

### 计算定义 = 目标 × 分区 × 操作 ###

**目标（target）**: 对什么度量计算
- 从 Step 1 的 What.measures 获取

**分区（partition_by）**: 在什么范围内计算
- [] = 全局（所有数据一起计算）
- ["月份"] = 按月份分区（每个月内单独计算）
- 视图维度全部 = 视图粒度（每行单独计算）

**操作（operation）**: 做什么计算
- RANK: 排名
- RUNNING_SUM: 累计求和
- PERCENT: 占比
- YEAR_AGO: 同比
- 等等

### Step 1 输出 ###
What: {{ what }}
Where: {{ where }}
How: {{ how }}
语义重述: {{ semantic_restatement }}

### 分区推断规则 ###

1. **排名类（RANKING）**
   - 默认 partition_by = []（全局排名）
   - 如果 hints 中有 "每月"、"每省" 等，提取对应维度作为 partition_by
   - 例如："每月排名" → partition_by = ["月份"]

2. **占比类（COMPARISON + "占"/"比例"）**
   - comparison_base = "全国"/"总体" → partition_by = []
   - comparison_base = "当月"/"所在月" → partition_by = ["月份"]
   - comparison_base = "所在区域" → partition_by = ["区域"]

3. **同比/环比类（COMPARISON + "同比"/"环比"）**
   - 默认 partition_by = 除时间维度外的所有维度
   - 例如：视图维度 = [省份, 月份]，时间维度 = 月份
   - → partition_by = [省份]

4. **累计类（CUMULATIVE）**
   - 默认 partition_by = []（全局累计）
   - 如果 hints 中有 "每省累计" 等，提取对应维度
   - 例如："每省累计" → partition_by = ["省份"]

5. **粒度类（GRANULARITY）**
   - partition_by = hints.fixed_dimensions
   - 这是特殊情况，表示固定到指定粒度聚合

### 输出格式 ###
{
    "computations": [
        {
            "target": "度量字段名",
            "partition_by": ["分区维度1", "分区维度2"],
            "operation": {
                "type": "操作类型",
                "params": {}
            }
        }
    ]
}
```

## 示例

### 示例 1：全局排名

```
Step 1 输出:
- What: {measures: [{field: "销售额", aggregation: "SUM"}]}
- Where: {dimensions: [{field: "省份"}], filters: []}
- How: {type: "RANKING", hints: {keywords: ["排名"]}}

推理过程:
1. How.type = RANKING → 排名计算
2. hints 中没有 "每月"、"每省" 等分区提示
3. 默认 partition_by = []（全局排名）

输出:
{
    "computations": [{
        "target": "销售额",
        "partition_by": [],
        "operation": {"type": "RANK"}
    }]
}
```

### 示例 2：每月排名

```
Step 1 输出:
- What: {measures: [{field: "销售额", aggregation: "SUM"}]}
- Where: {dimensions: [{field: "省份"}, {field: "订单日期", granularity: "MONTH"}], filters: []}
- How: {type: "RANKING", hints: {keywords: ["每月", "排名"], partition_hint: "月份"}}

推理过程:
1. How.type = RANKING → 排名计算
2. hints 中有 "每月" → partition_by = ["订单日期"]
3. 计算方向 = 视图维度 - partition_by = ["省份"]

输出:
{
    "computations": [{
        "target": "销售额",
        "partition_by": ["订单日期"],
        "operation": {"type": "RANK"}
    }]
}
```

### 示例 3：占全国比例

```
Step 1 输出:
- What: {measures: [{field: "销售额", aggregation: "SUM"}]}
- Where: {dimensions: [{field: "省份"}], filters: []}
- How: {type: "COMPARISON", hints: {keywords: ["占", "比例"], comparison_base: "全国"}}

推理过程:
1. How.type = COMPARISON + keywords 包含 "占比" → 占比计算
2. comparison_base = "全国" → partition_by = []（分母是全局）

输出:
{
    "computations": [{
        "target": "销售额",
        "partition_by": [],
        "operation": {"type": "PERCENT"}
    }]
}
```

### 示例 4：占当月比例

```
Step 1 输出:
- What: {measures: [{field: "销售额", aggregation: "SUM"}]}
- Where: {dimensions: [{field: "省份"}, {field: "订单日期", granularity: "MONTH"}], filters: []}
- How: {type: "COMPARISON", hints: {keywords: ["占", "当月", "比例"], comparison_base: "当月"}}

推理过程:
1. How.type = COMPARISON + keywords 包含 "占比" → 占比计算
2. comparison_base = "当月" → partition_by = ["订单日期"]（分母是当月总计）

输出:
{
    "computations": [{
        "target": "销售额",
        "partition_by": ["订单日期"],
        "operation": {"type": "PERCENT"}
    }]
}
```

### 示例 5：同比增长

```
Step 1 输出:
- What: {measures: [{field: "销售额", aggregation: "SUM"}]}
- Where: {dimensions: [{field: "省份"}, {field: "订单日期", granularity: "MONTH"}], filters: []}
- How: {type: "COMPARISON", hints: {keywords: ["同比", "增长"], comparison_base: "去年同期", time_dimension: "订单日期"}}

推理过程:
1. How.type = COMPARISON + comparison_base = "去年同期" → 同比计算
2. 时间维度 = 订单日期
3. partition_by = 视图维度 - 时间维度 = ["省份"]
4. 操作 = YEAR_AGO（去年同期）

输出:
{
    "computations": [{
        "target": "销售额",
        "partition_by": ["省份"],
        "operation": {
            "type": "YEAR_AGO",
            "params": {"calculation": "GROWTH_RATE"}
        }
    }]
}
```

### 示例 6：全局累计

```
Step 1 输出:
- What: {measures: [{field: "销售额", aggregation: "SUM"}]}
- Where: {dimensions: [{field: "订单日期", granularity: "MONTH"}], filters: []}
- How: {type: "CUMULATIVE", hints: {keywords: ["累计"], time_dimension: "订单日期"}}

推理过程:
1. How.type = CUMULATIVE → 累计计算
2. 没有分区提示 → partition_by = []（全局累计）
3. 累计方向 = 时间维度 = 订单日期

输出:
{
    "computations": [{
        "target": "销售额",
        "partition_by": [],
        "operation": {"type": "RUNNING_SUM"}
    }]
}
```

### 示例 7：每省累计

```
Step 1 输出:
- What: {measures: [{field: "销售额", aggregation: "SUM"}]}
- Where: {dimensions: [{field: "省份"}, {field: "订单日期", granularity: "MONTH"}], filters: []}
- How: {type: "CUMULATIVE", hints: {keywords: ["每省", "累计"], partition_hint: "省份", time_dimension: "订单日期"}}

推理过程:
1. How.type = CUMULATIVE → 累计计算
2. hints 中有 "每省" → partition_by = ["省份"]
3. 累计方向 = 视图维度 - partition_by = ["订单日期"]

输出:
{
    "computations": [{
        "target": "销售额",
        "partition_by": ["省份"],
        "operation": {"type": "RUNNING_SUM"}
    }]
}
```

### 示例 8：移动平均

```
Step 1 输出:
- What: {measures: [{field: "销售额", aggregation: "SUM"}]}
- Where: {dimensions: [{field: "订单日期", granularity: "MONTH"}], filters: []}
- How: {type: "CUMULATIVE", hints: {keywords: ["移动平均", "3个月"], window_size: 3, time_dimension: "订单日期"}}

推理过程:
1. How.type = CUMULATIVE + keywords 包含 "移动平均" → 移动平均计算
2. window_size = 3
3. partition_by = []（全局）

输出:
{
    "computations": [{
        "target": "销售额",
        "partition_by": [],
        "operation": {
            "type": "MOVING_AVG",
            "params": {"window_size": 3}
        }
    }]
}
```

### 示例 9：固定粒度聚合

```
Step 1 输出:
- What: {measures: [{field: "销售额", aggregation: "SUM"}]}
- Where: {dimensions: [{field: "客户"}], filters: []}
- How: {type: "GRANULARITY", hints: {keywords: ["不受", "影响"], fixed_dimensions: ["客户"]}}

推理过程:
1. How.type = GRANULARITY → 固定粒度聚合
2. fixed_dimensions = ["客户"]
3. 这是特殊情况，partition_by 表示固定到的粒度

输出:
{
    "computations": [{
        "target": "销售额",
        "partition_by": ["客户"],
        "operation": {"type": "FIXED"}
    }]
}
```

## 分区推断逻辑伪代码

```python
def infer_partition_by(step1: Step1Output) -> list[str]:
    """推断 partition_by"""
    
    how = step1.how
    view_dimensions = [d.field for d in step1.where.dimensions]
    
    # 排名类
    if how.type == HowType.RANKING:
        if "partition_hint" in how.hints:
            return [how.hints["partition_hint"]]
        return []  # 默认全局排名
    
    # 占比类
    if how.type == HowType.COMPARISON and "占" in how.hints.get("keywords", []):
        base = how.hints.get("comparison_base", "")
        if base in ["全国", "总体", "全部"]:
            return []
        if base in ["当月", "所在月"]:
            return [d for d in view_dimensions if is_time_dimension(d)]
        # 其他情况，尝试从 base 中提取维度
        return extract_dimensions_from_base(base, view_dimensions)
    
    # 同比/环比类
    if how.type == HowType.COMPARISON and how.hints.get("comparison_base") in ["去年同期", "上月"]:
        time_dim = how.hints.get("time_dimension")
        return [d for d in view_dimensions if d != time_dim]
    
    # 累计类
    if how.type == HowType.CUMULATIVE:
        if "partition_hint" in how.hints:
            return [how.hints["partition_hint"]]
        return []  # 默认全局累计
    
    # 粒度类
    if how.type == HowType.GRANULARITY:
        return how.hints.get("fixed_dimensions", [])
    
    return []
```

## 平台适配示例

### partition_by → Tableau

```python
def to_tableau_partitioning(partition_by: list[str], view_dimensions: list[str]) -> dict:
    """转换为 Tableau 表计算配置"""
    
    if not partition_by:
        # 全局：Partitioning = 无，Addressing = 全部维度
        return {
            "partitioning": [],
            "addressing": view_dimensions
        }
    
    # 分区：Partitioning = partition_by，Addressing = 剩余维度
    addressing = [d for d in view_dimensions if d not in partition_by]
    return {
        "partitioning": partition_by,
        "addressing": addressing
    }
```

### partition_by → Power BI

```python
def to_powerbi_calculate(partition_by: list[str], view_dimensions: list[str]) -> str:
    """转换为 Power BI CALCULATE 表达式"""
    
    if not partition_by:
        # 全局：ALL()
        return "CALCULATE([Measure], ALL())"
    
    if set(partition_by) == set(view_dimensions):
        # 视图粒度：无需 CALCULATE
        return "[Measure]"
    
    # 分区：ALLEXCEPT
    except_dims = ", ".join(partition_by)
    return f"CALCULATE([Measure], ALLEXCEPT(Table, {except_dims}))"
```

### partition_by → SQL

```python
def to_sql_over(partition_by: list[str]) -> str:
    """转换为 SQL OVER 子句"""
    
    if not partition_by:
        # 全局
        return "OVER ()"
    
    # 分区
    partition_clause = ", ".join(partition_by)
    return f"OVER (PARTITION BY {partition_clause})"
```
