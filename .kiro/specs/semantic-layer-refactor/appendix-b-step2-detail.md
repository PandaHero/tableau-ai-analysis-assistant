# 附件B：Step 2 详细设计

## 概述

Step 2 的核心任务是：**计算推理与自我验证**

1. 从 Step 1 的 `restated_question` 推断计算定义（主要任务）
2. 用 Step 1 的结构化输出验证推理结果（自我验证）

## 触发条件

```python
if step1_output.how_type != HowType.SIMPLE:
    step2_output = await step2_reasoning(step1_output)
else:
    step2_output = None  # 简单查询，跳过 Step 2
```

## 输入定义

```python
class Step2Input(BaseModel):
    """Step 2 输入 = Step 1 的完整输出"""
    
    restated_question: str
    """重述后的问题（主要输入）"""
    
    what: What
    """目标（用于验证 target）"""
    
    where: Where
    """范围（用于验证 partition_by）"""
    
    how_type: HowType
    """计算类型（用于验证 operation.type）"""
```

## 输出定义

```python
class Step2Output(BaseModel):
    """Step 2 输出"""
    
    # ===== 推理结果 =====
    computations: list[Computation]
    """计算定义列表"""
    
    # ===== 推理过程 =====
    reasoning: str
    """推理过程的自然语言描述"""
    
    # ===== 自我验证结果 =====
    validation: Step2Validation
    """验证结果"""


class Computation(BaseModel):
    """计算 = 目标 × 分区 × 操作"""
    
    target: str
    """计算目标（度量字段）"""
    
    partition_by: list[str]
    """分区维度
    
    - [] = 全局（所有数据一起计算）
    - ["月份"] = 按月份分区
    - 视图维度全部 = 视图粒度
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


class Step2Validation(BaseModel):
    """Step 2 自我验证结果"""
    
    target_check: ValidationCheck
    """target 验证"""
    
    partition_by_check: ValidationCheck
    """partition_by 验证"""
    
    operation_check: ValidationCheck
    """operation.type 验证"""
    
    all_valid: bool
    """所有检查是否都通过"""
    
    inconsistencies: list[str]
    """发现的不一致之处"""


class ValidationCheck(BaseModel):
    inferred_value: str | list[str]
    """从 restated_question 推断的值"""
    
    reference_value: str | list[str]
    """Step 1 结构化输出中的值"""
    
    is_match: bool
    """是否匹配"""
    
    note: str
    """说明"""
```

## 验证规则

### 三个检查点

| 检查点 | 检查内容 | 判断标准 |
|--------|---------|---------|
| target_check | target 是否在 what.measures 中 | target ∈ what.measures |
| partition_by_check | partition_by 是否都在 where.dimensions 中 | partition_by ⊆ where.dimensions |
| operation_check | operation.type 是否与 how_type 匹配 | 类型映射关系 |

### operation_check 的映射关系

```python
OPERATION_TYPE_MAPPING = {
    HowType.RANKING: [OperationType.RANK, OperationType.DENSE_RANK],
    HowType.CUMULATIVE: [OperationType.RUNNING_SUM, OperationType.RUNNING_AVG, 
                         OperationType.MOVING_AVG, OperationType.MOVING_SUM],
    HowType.COMPARISON: [OperationType.PERCENT, OperationType.DIFFERENCE, 
                         OperationType.GROWTH_RATE, OperationType.YEAR_AGO, 
                         OperationType.PERIOD_AGO],
    HowType.GRANULARITY: [OperationType.FIXED],
}

# 验证逻辑
is_match = operation.type in OPERATION_TYPE_MAPPING[how_type]
```

## Prompt 设计

```
你是一个数据分析计算专家。

### 任务 ###
1. 基于 Step 1 的输出，推断计算定义（target, partition_by, operation）
2. 用 Step 1 的结构化输出验证你的推理是否正确

### 输入 ###

**重述后的问题（主要依据）**:
{{ restated_question }}

**结构化输出（用于验证）**:
- what: {{ what }}
- where: {{ where }}
- how_type: {{ how_type }}

### 推理任务 ###

**1. 推断 target**
- 从 restated_question 中识别要计算的度量
- 验证：target 是否在 what.measures 中？

**2. 推断 partition_by**
- 从 restated_question 中识别分区意图
- 分区意图关键词：
  | 关键词 | partition_by |
  |--------|--------------|
  | "全局"、"总"、无分区词 | [] |
  | "每月"、"月内"、"当月" | [时间维度] |
  | "每省"、"省内" | [省份维度] |
  | "去年同期"、"同比" | [非时间维度] |
- 验证：partition_by 中的维度是否都在 where.dimensions 中？

**3. 推断 operation.type**
- 从 restated_question 中识别计算类型
- 验证：operation.type 是否与 how_type 匹配？
  - RANKING → RANK, DENSE_RANK
  - CUMULATIVE → RUNNING_SUM, RUNNING_AVG, MOVING_AVG, MOVING_SUM
  - COMPARISON → PERCENT, DIFFERENCE, GROWTH_RATE, YEAR_AGO, PERIOD_AGO
  - GRANULARITY → FIXED

### 输出格式 ###
{
    "reasoning": "推理过程（自然语言）",
    
    "computations": [{
        "target": "度量字段名",
        "partition_by": ["分区维度"],
        "operation": {"type": "操作类型", "params": {}}
    }],
    
    "validation": {
        "target_check": {
            "inferred_value": "从 restated_question 推断的 target",
            "reference_value": ["what.measures 中的字段"],
            "is_match": true/false,
            "note": "说明"
        },
        "partition_by_check": {
            "inferred_value": ["从 restated_question 推断的分区维度"],
            "reference_value": ["where.dimensions 中的字段"],
            "is_match": true/false,
            "note": "说明"
        },
        "operation_check": {
            "inferred_value": "从 restated_question 推断的操作类型",
            "reference_value": "how_type",
            "is_match": true/false,
            "note": "说明"
        },
        "all_valid": true/false,
        "inconsistencies": ["不一致的地方"]
    }
}
```

## 示例

### 示例 1：全局排名（验证通过）

```
输入:
- restated_question: "按省份分组，计算销售额总和，并按销售额降序排名"
- what: {measures: [{field: "销售额", aggregation: "SUM"}]}
- where: {dimensions: [{field: "省份"}]}
- how_type: RANKING

输出:
{
    "reasoning": "从重述中识别：1) 目标是'销售额'；2) 没有分区词，推断为全局排名；3) '排名'表示 RANK 操作",
    
    "computations": [{
        "target": "销售额",
        "partition_by": [],
        "operation": {"type": "RANK"}
    }],
    
    "validation": {
        "target_check": {
            "inferred_value": "销售额",
            "reference_value": ["销售额"],
            "is_match": true,
            "note": "销售额 在 what.measures 中"
        },
        "partition_by_check": {
            "inferred_value": [],
            "reference_value": ["省份"],
            "is_match": true,
            "note": "空集是任何集合的子集"
        },
        "operation_check": {
            "inferred_value": "RANK",
            "reference_value": "RANKING",
            "is_match": true,
            "note": "RANK 属于 RANKING 类型"
        },
        "all_valid": true,
        "inconsistencies": []
    }
}
```

### 示例 2：每月排名（验证通过）

```
输入:
- restated_question: "按省份和月份分组，计算销售额总和，在每个月内按销售额降序排名"
- what: {measures: [{field: "销售额", aggregation: "SUM"}]}
- where: {dimensions: [{field: "省份"}, {field: "订单日期", granularity: "MONTH"}]}
- how_type: RANKING

输出:
{
    "reasoning": "从重述中识别：1) 目标是'销售额'；2) '每个月内'表示按月分区；3) '排名'表示 RANK 操作",
    
    "computations": [{
        "target": "销售额",
        "partition_by": ["订单日期"],
        "operation": {"type": "RANK"}
    }],
    
    "validation": {
        "target_check": {
            "inferred_value": "销售额",
            "reference_value": ["销售额"],
            "is_match": true,
            "note": "销售额 在 what.measures 中"
        },
        "partition_by_check": {
            "inferred_value": ["订单日期"],
            "reference_value": ["省份", "订单日期"],
            "is_match": true,
            "note": "订单日期 在 where.dimensions 中"
        },
        "operation_check": {
            "inferred_value": "RANK",
            "reference_value": "RANKING",
            "is_match": true,
            "note": "RANK 属于 RANKING 类型"
        },
        "all_valid": true,
        "inconsistencies": []
    }
}
```

### 示例 3：占当月比例（验证通过）

```
输入:
- restated_question: "按省份和月份分组，计算销售额总和，并计算每个省份占当月总销售额的比例"
- what: {measures: [{field: "销售额", aggregation: "SUM"}]}
- where: {dimensions: [{field: "省份"}, {field: "订单日期", granularity: "MONTH"}]}
- how_type: COMPARISON

输出:
{
    "reasoning": "从重述中识别：1) 目标是'销售额'；2) '当月'表示分母是当月总额，按月分区；3) '比例'表示 PERCENT 操作",
    
    "computations": [{
        "target": "销售额",
        "partition_by": ["订单日期"],
        "operation": {"type": "PERCENT"}
    }],
    
    "validation": {
        "target_check": {
            "inferred_value": "销售额",
            "reference_value": ["销售额"],
            "is_match": true,
            "note": ""
        },
        "partition_by_check": {
            "inferred_value": ["订单日期"],
            "reference_value": ["省份", "订单日期"],
            "is_match": true,
            "note": "订单日期 在 where.dimensions 中"
        },
        "operation_check": {
            "inferred_value": "PERCENT",
            "reference_value": "COMPARISON",
            "is_match": true,
            "note": "PERCENT 属于 COMPARISON 类型"
        },
        "all_valid": true,
        "inconsistencies": []
    }
}
```

### 示例 4：同比增长（验证通过）

```
输入:
- restated_question: "按省份和月份分组，计算销售额总和，并计算与去年同期相比的增长率"
- what: {measures: [{field: "销售额", aggregation: "SUM"}]}
- where: {dimensions: [{field: "省份"}, {field: "订单日期", granularity: "MONTH"}]}
- how_type: COMPARISON

输出:
{
    "reasoning": "从重述中识别：1) 目标是'销售额'；2) '去年同期'表示同比计算，沿时间比较，在非时间维度上分区；3) '增长率'表示 YEAR_AGO + GROWTH_RATE",
    
    "computations": [{
        "target": "销售额",
        "partition_by": ["省份"],
        "operation": {"type": "YEAR_AGO", "params": {"calculation": "GROWTH_RATE"}}
    }],
    
    "validation": {
        "target_check": {
            "inferred_value": "销售额",
            "reference_value": ["销售额"],
            "is_match": true,
            "note": ""
        },
        "partition_by_check": {
            "inferred_value": ["省份"],
            "reference_value": ["省份", "订单日期"],
            "is_match": true,
            "note": "省份 在 where.dimensions 中"
        },
        "operation_check": {
            "inferred_value": "YEAR_AGO",
            "reference_value": "COMPARISON",
            "is_match": true,
            "note": "YEAR_AGO 属于 COMPARISON 类型"
        },
        "all_valid": true,
        "inconsistencies": []
    }
}
```

### 示例 5：验证不通过（幻觉）

```
输入:
- restated_question: "按省份分组，计算销售额总和，并排名"
- what: {measures: [{field: "销售额", aggregation: "SUM"}]}
- where: {dimensions: [{field: "省份"}]}
- how_type: RANKING

假设 LLM 幻觉，输出了错误的 partition_by:

输出:
{
    "reasoning": "从重述中识别：1) 目标是'销售额'；2) 按月分区；3) 排名",
    
    "computations": [{
        "target": "销售额",
        "partition_by": ["月份"],  // 幻觉！重述中没有月份
        "operation": {"type": "RANK"}
    }],
    
    "validation": {
        "target_check": {
            "inferred_value": "销售额",
            "reference_value": ["销售额"],
            "is_match": true,
            "note": ""
        },
        "partition_by_check": {
            "inferred_value": ["月份"],
            "reference_value": ["省份"],
            "is_match": false,
            "note": "月份 不在 where.dimensions 中，where.dimensions 只有 [省份]"
        },
        "operation_check": {
            "inferred_value": "RANK",
            "reference_value": "RANKING",
            "is_match": true,
            "note": ""
        },
        "all_valid": false,
        "inconsistencies": ["partition_by 包含 '月份'，但 where.dimensions 中没有这个维度"]
    }
}
```

---

## Observer 设计

### 触发条件

```python
if step2_output.validation.all_valid:
    # 验证通过，不需要 Observer
    return step2_output.computations
else:
    # 验证不通过，Observer 介入
    observer_result = await observer.check(original_question, step1_output, step2_output)
    return observer_result.final_result
```

### 输入定义

```python
class ObserverInput(BaseModel):
    original_question: str
    """原始问题（用于回溯）"""
    
    step1: Step1Output
    """Step 1 输出"""
    
    step2: Step2Output
    """Step 2 输出"""
```

### 输出定义

```python
class ObserverOutput(BaseModel):
    is_consistent: bool
    """Step 1 和 Step 2 是否一致"""
    
    conflicts: list[Conflict]
    """发现的冲突"""
    
    decision: ObserverDecision
    """Observer 的决策"""
    
    correction: Correction | None
    """修正内容（仅当 decision=CORRECT）"""
    
    final_result: Computation | None
    """最终结果"""


class Conflict(BaseModel):
    aspect: str
    """冲突的方面（restatement/structure/semantic）"""
    
    description: str
    """冲突描述"""
    
    step1_value: str
    """Step 1 的值"""
    
    step2_value: str
    """Step 2 的值"""


class Correction(BaseModel):
    field: str
    """要修正的字段"""
    
    original_value: str | list[str]
    """原值"""
    
    corrected_value: str | list[str]
    """修正值"""
    
    reason: str
    """修正原因"""


class ObserverDecision(str, Enum):
    ACCEPT = "ACCEPT"           # 一致，接受 Step 2 结果
    CORRECT = "CORRECT"         # 有小冲突，Observer 修正
    RETRY = "RETRY"             # 有大冲突，需要重新推理
    CLARIFY = "CLARIFY"         # 无法判断，需要用户澄清
```

### Observer Prompt 设计

```
你是一个数据分析质量检查专家。

### 任务 ###
检查 Step 1（语义理解）和 Step 2（计算推理）的结果是否一致。

### 输入 ###
原始问题: {{ original_question }}

Step 1 输出:
- 重述问题: {{ step1.restated_question }}
- what: {{ step1.what }}
- where: {{ step1.where }}
- how_type: {{ step1.how_type }}

Step 2 输出:
- computations: {{ step2.computations }}
- reasoning: {{ step2.reasoning }}
- validation: {{ step2.validation }}

### 检查项 ###

**1. 重述完整性检查**
- restated_question 是否完整保留了 original_question 的关键信息？
- 特别注意：分区词（每月、每省、当月、全国等）
- 特别注意：比较基准（同比、环比、去年同期等）

**2. 结构一致性检查**
- 复核 Step 2 的 validation 中报告的不一致

**3. 语义一致性检查**
- Step 2 的 computations 是否与 restated_question 的语义一致？
- partition_by 是否与重述中的分区意图一致？
- operation.type 是否与重述中的计算意图一致？

### 决策规则 ###

| 情况 | 决策 |
|------|------|
| 所有检查通过 | ACCEPT |
| 有小冲突，可以明确修正 | CORRECT |
| 有大冲突，需要重新推理 | RETRY |
| 无法判断，信息不足 | CLARIFY |

### 输出格式 ###
{
    "is_consistent": true/false,
    
    "conflicts": [
        {
            "aspect": "restatement/structure/semantic",
            "description": "冲突描述",
            "step1_value": "Step 1 的值",
            "step2_value": "Step 2 的值"
        }
    ],
    
    "decision": "ACCEPT/CORRECT/RETRY/CLARIFY",
    
    "correction": {  // 仅当 decision=CORRECT 时
        "field": "要修正的字段",
        "original_value": "原值",
        "corrected_value": "修正值",
        "reason": "修正原因"
    },
    
    "final_result": {  // 最终的 Computation
        "target": "...",
        "partition_by": [...],
        "operation": {...}
    }
}
```

### Observer 示例

#### 示例 1：重述丢失关键信息

```
输入:
- original_question: "占当月比例呢？"
- step1.restated_question: "计算销售额占比"  // 丢失了"当月"！
- step2.computations: [{target: "销售额", partition_by: [], operation: {type: PERCENT}}]

Observer 输出:
{
    "is_consistent": false,
    
    "conflicts": [{
        "aspect": "restatement",
        "description": "原始问题说'当月'，但重述中丢失了这个关键信息",
        "step1_value": "计算销售额占比",
        "step2_value": "partition_by: []（全局）"
    }],
    
    "decision": "CORRECT",
    
    "correction": {
        "field": "partition_by",
        "original_value": [],
        "corrected_value": ["订单日期"],
        "reason": "原始问题明确说'当月'，应该按月分区"
    },
    
    "final_result": {
        "target": "销售额",
        "partition_by": ["订单日期"],
        "operation": {"type": "PERCENT"}
    }
}
```

#### 示例 2：Step 2 幻觉

```
输入:
- original_question: "排名呢？"
- step1.restated_question: "按省份分组，计算销售额总和，并排名"
- step1.where.dimensions: ["省份"]
- step2.computations: [{target: "销售额", partition_by: ["月份"], operation: {type: RANK}}]
- step2.validation.partition_by_check.is_match: false

Observer 输出:
{
    "is_consistent": false,
    
    "conflicts": [{
        "aspect": "structure",
        "description": "Step 2 推断的 partition_by 包含 '月份'，但 where.dimensions 中没有这个维度",
        "step1_value": "where.dimensions: [省份]",
        "step2_value": "partition_by: [月份]"
    }],
    
    "decision": "CORRECT",
    
    "correction": {
        "field": "partition_by",
        "original_value": ["月份"],
        "corrected_value": [],
        "reason": "重述中没有分区词，且 where.dimensions 中没有月份，应该是全局排名"
    },
    
    "final_result": {
        "target": "销售额",
        "partition_by": [],
        "operation": {"type": "RANK"}
    }
}
```

## 分区推断规则总结

| restated_question 中的关键词 | partition_by | 说明 |
|---------------------------|--------------|------|
| "排名"（无分区词） | [] | 全局排名 |
| "每月排名"、"月内排名" | [时间维度] | 按月分区 |
| "每省排名" | [省份] | 按省份分区 |
| "占全国比例"、"占总体" | [] | 分母是全局 |
| "占当月比例" | [时间维度] | 分母是当月 |
| "同比"、"去年同期" | [非时间维度] | 沿时间比较 |
| "累计"（无分区词） | [] | 全局累计 |
| "每省累计" | [省份] | 按省份分区累计 |

## 平台映射

| partition_by | Tableau | Power BI | SQL |
|--------------|---------|----------|-----|
| `[]` | Partitioning=无 | ALL() | OVER () |
| `["月份"]` | Partitioning=月份 | ALLEXCEPT(月份) | PARTITION BY 月份 |
| `["省份", "月份"]` | Partitioning=全部 | VALUES() | 无 OVER |
