# 附件A：Step 1 详细设计

## 概述

Step 1 的核心任务是：**语义理解与问题重述**

将用户问题（结合历史对话）重述为完整的独立问题，同时提取结构化信息用于 Step 2 验证。

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
    """Step 1 输出"""
    
    # ===== 核心输出 =====
    restated_question: str
    """重述后的完整问题（自然语言）
    
    这是 Step 2 的主要输入。
    关键：必须保留分区意图（每月、每省、当月、全国等）
    """
    
    # ===== 结构化输出（用于 Step 2 验证） =====
    what: What
    """目标（度量）"""
    
    where: Where
    """范围（维度 + 筛选）"""
    
    how_type: HowType
    """计算类型"""
    
    # ===== 意图分类 =====
    intent: Intent
    """意图分类"""


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


class HowType(str, Enum):
    SIMPLE = "SIMPLE"           # 简单聚合
    RANKING = "RANKING"         # 排名类
    CUMULATIVE = "CUMULATIVE"   # 累计类
    COMPARISON = "COMPARISON"   # 比较类（占比、同比环比）
    GRANULARITY = "GRANULARITY" # 粒度类（固定粒度聚合）


class Intent(BaseModel):
    type: IntentType
    reasoning: str


class IntentType(str, Enum):
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"
    IRRELEVANT = "IRRELEVANT"
```

## Prompt 设计

```
你是一个数据分析语义理解专家。

### 任务 ###
1. 将用户的问题（结合历史对话）重述为完整的独立问题
2. 提取结构化的查询信息（what/where/how_type）
3. 分类用户意图

### 问题重述规则 ###

**核心原则**：重述后的问题必须是完整的、独立的，包含所有必要的上下文。

**合并规则**：
1. 当前问题中明确提到的元素，优先使用
2. 当前问题中未提到的元素，从历史对话继承
3. 如果当前问题是修改某个元素，替换历史中的对应元素
4. 如果当前问题是叠加某个元素，与历史合并

**关键**：重述中必须保留分区意图！
- "每月排名" → 重述中必须包含"每个月内"或"按月"
- "占当月比例" → 重述中必须包含"当月"
- "同比增长" → 重述中必须包含"去年同期"或"同比"

### 三元组定义 ###

**What（目标）**: 用户想计算什么数据？
- 度量字段（如：销售额、利润、数量）
- 聚合方式（如：SUM、AVG、COUNT）

**Where（范围）**: 用户想在什么范围内查看？
- 维度（如：省份、月份、产品类别）
- 筛选条件（如：华东地区、2024年）

**How（操作类型）**: 用户想怎么计算？
- SIMPLE: 简单聚合，无复杂计算
- RANKING: 排名、Top N、排序
- CUMULATIVE: 累计、移动平均
- COMPARISON: 占比、同比、环比、增长率
- GRANULARITY: 固定粒度、不受筛选影响

### 意图分类规则 ###

| 意图 | 判断条件 |
|------|---------|
| DATA_QUERY | 有可查询的字段，信息完整 |
| CLARIFICATION | 引用了未指定的值或需要澄清 |
| GENERAL | 问数据集描述、字段信息 |
| IRRELEVANT | 与数据分析无关 |

### 元数据（辅助理解）###
可用维度: {{ dimensions }}
可用度量: {{ measures }}

### 历史对话 ###
{{ conversation_history }}

### 当前问题 ###
{{ question }}

### 输出格式 ###
{
    "restated_question": "重述后的完整问题（自然语言，必须保留分区意图）",
    
    "what": {
        "measures": [{"field": "字段名", "aggregation": "SUM/AVG/COUNT/..."}]
    },
    
    "where": {
        "dimensions": [{"field": "字段名", "granularity": "YEAR/MONTH/DAY（可选）"}],
        "filters": [{"field": "字段名", "type": "SET/DATE_RANGE/...", "values": [...]}]
    },
    
    "how_type": "SIMPLE/RANKING/CUMULATIVE/COMPARISON/GRANULARITY",
    
    "intent": {
        "type": "DATA_QUERY/CLARIFICATION/GENERAL/IRRELEVANT",
        "reasoning": "分类理由"
    }
}
```

## 示例

### 示例 1：简单查询

```
历史: []
当前: "各省份销售额"

输出:
{
    "restated_question": "按省份分组，计算销售额总和",
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "省份"}], "filters": []},
    "how_type": "SIMPLE",
    "intent": {"type": "DATA_QUERY", "reasoning": "用户想查询各省份的销售额汇总"}
}
```

### 示例 2：继承 + 新增操作（全局排名）

```
历史: ["各省份销售额"]
当前: "排名呢？"

输出:
{
    "restated_question": "按省份分组，计算销售额总和，并按销售额降序排名",
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "省份"}], "filters": []},
    "how_type": "RANKING",
    "intent": {"type": "DATA_QUERY", "reasoning": "用户想对之前的省份销售额数据进行排名"}
}
```

### 示例 3：带分区的排名

```
历史: ["各省份各月销售额"]
当前: "每月排名呢？"

输出:
{
    "restated_question": "按省份和月份分组，计算销售额总和，在每个月内按销售额降序排名",
                          ↑
                          关键：保留了"每个月内"这个分区意图
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {
        "dimensions": [{"field": "省份"}, {"field": "订单日期", "granularity": "MONTH"}],
        "filters": []
    },
    "how_type": "RANKING",
    "intent": {"type": "DATA_QUERY", "reasoning": "用户想在每个月内对省份销售额进行排名"}
}
```

### 示例 4：占比计算（全局）

```
历史: []
当前: "各省份销售额占全国的比例"

输出:
{
    "restated_question": "按省份分组，计算销售额总和，并计算每个省份占全国总销售额的比例",
                          ↑
                          关键：保留了"全国"这个分区意图（全局）
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "省份"}], "filters": []},
    "how_type": "COMPARISON",
    "intent": {"type": "DATA_QUERY", "reasoning": "用户想计算每个省份销售额占全国总额的比例"}
}
```

### 示例 5：占比计算（按月分区）

```
历史: ["各省份各月销售额"]
当前: "占当月的比例呢？"

输出:
{
    "restated_question": "按省份和月份分组，计算销售额总和，并计算每个省份占当月总销售额的比例",
                          ↑
                          关键：保留了"当月"这个分区意图
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {
        "dimensions": [{"field": "省份"}, {"field": "订单日期", "granularity": "MONTH"}],
        "filters": []
    },
    "how_type": "COMPARISON",
    "intent": {"type": "DATA_QUERY", "reasoning": "用户想计算每个省份销售额占当月总额的比例"}
}
```

### 示例 6：同比计算

```
历史: []
当前: "各省份各月销售额同比增长"

输出:
{
    "restated_question": "按省份和月份分组，计算销售额总和，并计算与去年同期相比的增长率",
                          ↑
                          关键：保留了"去年同期"这个时间比较意图
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {
        "dimensions": [{"field": "省份"}, {"field": "订单日期", "granularity": "MONTH"}],
        "filters": []
    },
    "how_type": "COMPARISON",
    "intent": {"type": "DATA_QUERY", "reasoning": "用户想计算销售额与去年同期的增长率"}
}
```

### 示例 7：累计计算

```
历史: []
当前: "各月销售额累计"

输出:
{
    "restated_question": "按月分组，计算销售额总和，并计算累计值",
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "订单日期", "granularity": "MONTH"}], "filters": []},
    "how_type": "CUMULATIVE",
    "intent": {"type": "DATA_QUERY", "reasoning": "用户想计算销售额的累计值"}
}
```

### 示例 8：每省累计

```
历史: ["各省份各月销售额"]
当前: "每省累计呢？"

输出:
{
    "restated_question": "按省份和月份分组，计算销售额总和，在每个省份内按月累计",
                          ↑
                          关键：保留了"每个省份内"这个分区意图
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {
        "dimensions": [{"field": "省份"}, {"field": "订单日期", "granularity": "MONTH"}],
        "filters": []
    },
    "how_type": "CUMULATIVE",
    "intent": {"type": "DATA_QUERY", "reasoning": "用户想在每个省份内计算销售额的累计值"}
}
```

### 示例 9：固定粒度聚合

```
历史: []
当前: "每个客户的总销售额，不受其他筛选影响"

输出:
{
    "restated_question": "固定到客户粒度，计算每个客户的销售额总和，不受视图筛选影响",
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [{"field": "客户"}], "filters": []},
    "how_type": "GRANULARITY",
    "intent": {"type": "DATA_QUERY", "reasoning": "用户想计算固定粒度的客户销售额"}
}
```

### 示例 10：需要澄清

```
历史: []
当前: "这些产品的销售额"

输出:
{
    "restated_question": "计算指定产品的销售额",
    "what": {"measures": [{"field": "销售额", "aggregation": "SUM"}]},
    "where": {"dimensions": [], "filters": []},
    "how_type": "SIMPLE",
    "intent": {
        "type": "CLARIFICATION",
        "reasoning": "用户说'这些产品'但没有指定具体是哪些产品"
    }
}
```

## 合并逻辑说明

> **注意**：以下是 **LLM 行为的描述**，不是需要实现的代码。LLM 根据 Prompt 中的"合并规则"自动完成历史对话的合并。

```python
def merge_with_history(current_question: str, history: list[Message]) -> str:
    """描述 LLM 如何合并当前问题与历史对话"""
    
    # 1. 从历史对话中提取 What × Where × How
    history_what = extract_what(history)
    history_where = extract_where(history)
    history_how = extract_how(history)
    
    # 2. 从当前问题中识别要修改/新增的部分
    current_what = extract_what(current_question)
    current_where = extract_where(current_question)
    current_how = extract_how(current_question)
    
    # 3. 合并
    final_what = current_what if current_what else history_what
    final_where = merge_where(history_where, current_where)
    final_how = current_how if current_how else history_how
    
    # 4. 生成重述
    return generate_restatement(final_what, final_where, final_how)
```

## 澄清问题生成

当意图为 `CLARIFICATION` 时，系统生成澄清问题帮助用户完善查询：

```python
class ClarificationQuestion(BaseModel):
    question: str                    # 澄清问题
    options: list[str] | None = None # 可选值列表（从元数据获取）
    field_reference: str | None = None # 相关字段
```

**示例**：
- "这些产品的销售额" → "您指的是哪些产品？数据源中包含以下产品类别：[家具、办公用品、技术产品]"
- "上个月的数据" → "您需要查看哪个指标的数据？可选指标包括：[销售额、利润、订单数量]"

## 关键设计点

1. **意图分类是第一个分支点**
   - Step 1 输出后，**先判断 intent.type**
   - 只有 `DATA_QUERY` 意图才继续后续处理
   - 其他意图直接走各自的处理分支并返回

2. **意图分类决定后续流程**
   ```
   intent.type == ?
       │
       ├── DATA_QUERY ──────→ 继续判断 how_type
       │                           │
       │                       ┌───┴───┐
       │                      SIMPLE   其他
       │                       │       │
       │                       ▼       ▼
       │                    直接构建  Step 2 → Observer
       │                    查询
       │
       ├── CLARIFICATION ───→ 生成澄清问题 → 返回
       │
       ├── GENERAL ─────────→ 生成通用响应 → 返回
       │
       └── IRRELEVANT ──────→ 拒绝处理 → 返回
   ```

3. **restated_question 是 Step 2 的主要输入**
   - 必须是完整的、独立的问题
   - 必须保留分区意图（每月、每省、当月、全国等）

4. **结构化输出用于 Step 2 验证**
   - what.measures → 验证 target
   - where.dimensions → 验证 partition_by
   - how_type → 验证 operation.type
