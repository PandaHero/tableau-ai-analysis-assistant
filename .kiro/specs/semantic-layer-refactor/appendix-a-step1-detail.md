# 附件A：Step 1 详细设计

## 概述

Step 1 的核心任务是：**语义理解与三元组构建**

将用户问题（结合历史对话）转换为结构化的 What × Where × How 三元组。

## 输入定义

```python
class Step1Input(BaseModel):
    question: str
    """当前用户问题"""
    
    conversation_history: list[Message]
    """历史对话列表"""
    
    metadata: DataSourceMetadata
    """数据源元数据（辅助 LLM 理解）"""
```

## 输出定义

```python
class Step1Output(BaseModel):
    """Step 1 输出 - 三元组"""
    
    what: What
    """目标（度量）"""
    
    where: Where
    """范围（维度 + 筛选）"""
    
    how: How
    """操作（计算意图）"""
    
    semantic_restatement: str
    """语义化重述"""


class What(BaseModel):
    """What - 目标"""
    measures: list[MeasureSpec]


class MeasureSpec(BaseModel):
    field: str
    """字段名（业务术语）"""
    
    aggregation: str = "SUM"
    """聚合方式"""


class Where(BaseModel):
    """Where - 范围"""
    dimensions: list[DimensionSpec]
    filters: list[FilterSpec]


class DimensionSpec(BaseModel):
    field: str
    """字段名"""
    
    granularity: str | None = None
    """日期粒度（如 YEAR, MONTH, DAY）"""


class FilterSpec(BaseModel):
    field: str
    type: str  # SET, DATE_RANGE, NUMERIC_RANGE, TEXT_MATCH
    values: list | dict


class How(BaseModel):
    """How - 操作"""
    type: HowType
    hints: dict = {}


class HowType(str, Enum):
    SIMPLE = "SIMPLE"           # 简单聚合
    RANKING = "RANKING"         # 排名类
    CUMULATIVE = "CUMULATIVE"   # 累计类
    COMPARISON = "COMPARISON"   # 比较类（占比、同比环比）
    GRANULARITY = "GRANULARITY" # 粒度类（固定粒度聚合）
```

## Prompt 设计

```
你是一个数据分析语义理解专家。

### 任务 ###
分析用户的问题，结合历史对话，构建完整的查询三元组：What × Where × How

### 三元组定义 ###

**What（目标）**: 用户想计算什么数据？
- 度量字段（如：销售额、利润、数量）
- 聚合方式（如：SUM、AVG、COUNT）

**Where（范围）**: 用户想在什么范围内查看？
- 维度（如：省份、月份、产品类别）
- 筛选条件（如：华东地区、2024年）

**How（操作）**: 用户想怎么计算？
- SIMPLE: 简单聚合，无复杂计算
- RANKING: 排名、Top N、排序
- CUMULATIVE: 累计、移动平均
- COMPARISON: 占比、同比、环比、增长率
- GRANULARITY: 固定粒度、不受筛选影响

### 合并规则 ###
1. 当前问题中明确提到的元素，优先使用
2. 当前问题中未提到的元素，从历史对话继承
3. 如果当前问题是修改某个元素，替换历史中的对应元素
4. 如果当前问题是叠加某个元素，与历史合并

### 元数据（辅助理解）###
可用维度: {{ dimensions }}
可用度量: {{ measures }}

### 历史对话 ###
{{ conversation_history }}

### 当前问题 ###
{{ question }}

### 输出格式 ###
{
    "what": {
        "measures": [{"field": "字段名", "aggregation": "SUM/AVG/COUNT/..."}]
    },
    "where": {
        "dimensions": [{"field": "字段名", "granularity": "YEAR/MONTH/DAY（可选）"}],
        "filters": [{"field": "字段名", "type": "SET/DATE_RANGE/...", "values": [...]}]
    },
    "how": {
        "type": "SIMPLE/RANKING/CUMULATIVE/COMPARISON/GRANULARITY",
        "hints": {
            "keywords": ["从问题中提取的关键词"],
            "comparison_base": "比较基准（如果是 COMPARISON）",
            "time_dimension": "时间维度（如果涉及时间计算）"
        }
    },
    "semantic_restatement": "用数据分析术语重述的完整问题"
}
```

## 示例

### 示例 1：简单查询

```
历史: []
当前: "各省份销售额"

输出:
{
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "省份"}], "filters": []},
    "how": {"type": "SIMPLE", "hints": {}},
    "semantic_restatement": "按省份分组，计算销售额总和"
}
```

### 示例 2：继承 + 新增操作

```
历史: ["各省份销售额"]
当前: "排名呢？"

输出:
{
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "省份"}], "filters": []},
    "how": {"type": "RANKING", "hints": {"keywords": ["排名"]}},
    "semantic_restatement": "按省份分组，计算销售额总和，并按销售额降序排名"
}
```

### 示例 3：替换 What

```
历史: ["各省份销售额"]
当前: "利润呢？"

输出:
{
    "what": {"measures": [{"field": "利润", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "省份"}], "filters": []},
    "how": {"type": "SIMPLE", "hints": {}},
    "semantic_restatement": "按省份分组，计算利润总和"
}
```

### 示例 4：替换 Where

```
历史: ["各省份销售额"]
当前: "按月看"

输出:
{
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "订单日期", "granularity": "MONTH"}], "filters": []},
    "how": {"type": "SIMPLE", "hints": {}},
    "semantic_restatement": "按月分组，计算销售额总和"
}
```

### 示例 5：叠加 Where（筛选）

```
历史: ["各省份销售额"]
当前: "华东地区的"

输出:
{
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {
        "dimensions": [{"field": "省份"}],
        "filters": [{"field": "区域", "type": "SET", "values": ["华东"]}]
    },
    "how": {"type": "SIMPLE", "hints": {}},
    "semantic_restatement": "筛选华东地区，按省份分组，计算销售额总和"
}
```

### 示例 6：占比计算

```
历史: []
当前: "各省份销售额占全国的比例"

输出:
{
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "省份"}], "filters": []},
    "how": {
        "type": "COMPARISON",
        "hints": {
            "keywords": ["占", "比例"],
            "comparison_base": "全国"
        }
    },
    "semantic_restatement": "按省份分组，计算销售额总和，并计算每个省份占全国总销售额的比例"
}
```

### 示例 7：同比计算

```
历史: []
当前: "各月销售额同比增长"

输出:
{
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "订单日期", "granularity": "MONTH"}], "filters": []},
    "how": {
        "type": "COMPARISON",
        "hints": {
            "keywords": ["同比", "增长"],
            "comparison_base": "去年同期",
            "time_dimension": "订单日期"
        }
    },
    "semantic_restatement": "按月分组，计算销售额总和，并计算与去年同期的增长率"
}
```

### 示例 8：累计计算

```
历史: []
当前: "各月销售额累计"

输出:
{
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "订单日期", "granularity": "MONTH"}], "filters": []},
    "how": {
        "type": "CUMULATIVE",
        "hints": {
            "keywords": ["累计"],
            "time_dimension": "订单日期"
        }
    },
    "semantic_restatement": "按月分组，计算销售额总和，并计算累计值"
}
```

### 示例 9：多维度 + 分组排名

```
历史: []
当前: "各省份各月销售额，每月排名"

输出:
{
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {
        "dimensions": [
            {"field": "省份"},
            {"field": "订单日期", "granularity": "MONTH"}
        ],
        "filters": []
    },
    "how": {
        "type": "RANKING",
        "hints": {
            "keywords": ["每月", "排名"],
            "partition_hint": "月份"
        }
    },
    "semantic_restatement": "按省份和月份分组，计算销售额总和，并在每个月内按销售额排名"
}
```

### 示例 10：固定粒度聚合

```
历史: []
当前: "每个客户的总销售额，不受其他筛选影响"

输出:
{
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "客户"}], "filters": []},
    "how": {
        "type": "GRANULARITY",
        "hints": {
            "keywords": ["不受", "影响"],
            "fixed_dimensions": ["客户"]
        }
    },
    "semantic_restatement": "固定到客户粒度，计算每个客户的销售额总和，不受视图筛选影响"
}
```

## 合并逻辑伪代码

```python
def merge_with_history(current: Step1Output, history: list[Step1Output]) -> Step1Output:
    """合并当前问题与历史对话"""
    
    if not history:
        return current
    
    last = history[-1]
    
    # What: 如果当前有，用当前的；否则继承
    what = current.what if current.what.measures else last.what
    
    # Where.dimensions: 如果当前有，用当前的；否则继承
    dimensions = current.where.dimensions if current.where.dimensions else last.where.dimensions
    
    # Where.filters: 叠加
    filters = last.where.filters + current.where.filters
    
    # How: 如果当前有复杂计算，用当前的；否则继承
    how = current.how if current.how.type != HowType.SIMPLE else last.how
    
    return Step1Output(
        what=what,
        where=Where(dimensions=dimensions, filters=filters),
        how=how,
        semantic_restatement=generate_restatement(what, where, how)
    )
```
