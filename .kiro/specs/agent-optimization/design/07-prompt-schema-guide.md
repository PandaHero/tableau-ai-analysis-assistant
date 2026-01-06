# Prompt 和 Schema 设计指南

## 1. 设计原则

### 1.1 核心原则：职责分离

```
┌─────────────────────────────────────────────────────────────────┐
│                    Prompt vs Schema 职责分离                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Prompt 负责：                                                   │
│  ├── 教 LLM 如何思考                                            │
│  ├── 什么情况下做什么决策                                        │
│  ├── 如何分析用户问题                                            │
│  └── 正确和错误的例子                                            │
│                                                                 │
│  Schema 负责：                                                   │
│  ├── 定义字段名称和类型                                          │
│  ├── 定义枚举值范围                                              │
│  ├── 定义必填/可选                                               │
│  └── 定义嵌套结构                                                │
│                                                                 │
│  Schema description 应该：                                       │
│  ✓ 说明字段"是什么" (What)                                      │
│  ✗ 不说明"什么时候填" (When) ← 属于 Prompt                      │
│  ✗ 不说明"怎么判断" (How) ← 属于 Prompt                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 设计规范

**Schema 设计**：
- description 只说"是什么"，不解释逻辑
- 枚举值精简（5 个以内最佳）
- 嵌套层级浅（2 层以内）
- 类型明确（使用 Literal、Enum 约束）

**Prompt 设计**：
- 身份定义简洁（1-2 句话）
- 能力边界清晰
- 决策规则选择合适的模式：
  - 表格映射：条件→结果的简单映射
  - IF-THEN：需要动态计算的规则
  - 关键词检测：基于关键词触发行为
  - 优先级规则：多选项按优先级选择
- XML 标签分块（复杂规则）
- 显式推理步骤
- 正反例对比
- 自我检查清单（具体的业务检查项）

## 2. Prompt 结构模板

### 2.1 标准结构

```xml
<identity>
你是 {role_name}，{role_description}。
你专注于 {domain}，擅长 {expertise}。
</identity>

<capabilities>
你可以：
- 能力 1
- 能力 2

你不能：
- 限制 1
- 限制 2
</capabilities>

<context>
{available_context}
</context>

<decision_rules>
## 规则类别 A
| 条件 | 结果 | 说明 |
|------|------|------|
| ... | ... | ... |

## 规则类别 B
IF 条件 THEN 动作
</decision_rules>

<thinking_steps>
在生成输出前，你必须按以下步骤思考：

1. **步骤 1**：描述
2. **步骤 2**：描述
3. **步骤 3**：描述
</thinking_steps>

<examples>
## 示例 1：标题

问题：...

<analysis>
分析过程...
</analysis>

输出：
```json
{...}
```

## 反例：标题

问题：...

正确输出：
```json
{...}
```

错误输出（不要这样做）：
```json
{...}
```

原因：...
</examples>

<self_correction>
在输出前检查：
1. 检查项 1
2. 检查项 2
3. 检查项 3
</self_correction>

<output_format>
{format_instructions}
</output_format>
```

### 2.2 XML 标签分块模式

来自 Cursor 等工具的最佳实践：

```xml
<!-- 身份定义 -->
<identity>
你是 Tableau 数据分析助手，专注于将自然语言问题转换为结构化查询。
</identity>

<!-- 能力边界 -->
<capabilities>
你可以：
- 理解用户的数据分析意图
- 提取维度、度量、筛选条件
- 识别复杂计算需求（排名、占比、累计、环比）

你不能：
- 执行 SQL 查询
- 访问外部数据源
- 修改数据模型
</capabilities>

<!-- 决策规则 -->
<decision_rules>
## 意图分类规则
| 条件 | 意图 | 说明 |
|------|------|------|
| 有具体度量 + 有具体维度 | DATA_QUERY | 完整的数据查询 |
| 缺少度量或维度 | CLARIFICATION | 需要澄清 |
| 询问字段/元数据 | GENERAL | 一般性问题 |

## 复杂计算检测规则
| 关键词 | calc_type | 说明 |
|-------|-----------|------|
| 排名、排行、第几名 | RANK | 添加排名列 |
| 占比、百分比、份额 | PERCENT | 计算占总量的比例 |
| 累计、YTD、累积 | RUNNING | 累计求和 |
| 环比、同比、增长率 | DIFF | 与上期比较 |
| 无以上关键词 | NONE | 简单聚合查询 |
</decision_rules>
```

## 3. Schema 设计规范

### 3.1 正确的 Schema 设计

```python
from enum import Enum
from typing import Literal, Optional, List
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════
# 枚举定义 - 只定义值，不解释逻辑
# ═══════════════════════════════════════════════════════════════

class Intent(str, Enum):
    """意图类型"""
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"


class CalcType(str, Enum):
    """计算类型（精简为 5 种）"""
    RANK = "RANK"           # 排名
    PERCENT = "PERCENT"     # 占比
    RUNNING = "RUNNING"     # 累计
    DIFF = "DIFF"           # 差异
    NONE = "NONE"           # 无复杂计算


# ═══════════════════════════════════════════════════════════════
# 数据模型 - description 只说"是什么"
# ═══════════════════════════════════════════════════════════════

class Dimension(BaseModel):
    """维度字段"""
    field: str = Field(description="字段名")
    granularity: Optional[Literal["YEAR", "MONTH", "DAY"]] = Field(
        default=None, 
        description="日期粒度"
    )


class Measure(BaseModel):
    """度量字段"""
    field: str = Field(description="字段名")
    aggregation: str = Field(default="SUM", description="聚合函数")


class Filter(BaseModel):
    """筛选条件"""
    field: str = Field(description="字段名")
    operator: str = Field(description="操作符")
    value: str | list = Field(description="筛选值")


class Computation(BaseModel):
    """复杂计算"""
    calc_type: CalcType = Field(description="计算类型")
    target: str = Field(description="目标度量字段")
    partition_by: List[str] = Field(default_factory=list, description="分区字段")


class SemanticQuery(BaseModel):
    """语义查询结果"""
    intent: Intent = Field(description="意图类型")
    dimensions: List[Dimension] = Field(default_factory=list, description="维度列表")
    measures: List[Measure] = Field(default_factory=list, description="度量列表")
    filters: List[Filter] = Field(default_factory=list, description="筛选条件")
    computation: Optional[Computation] = Field(default=None, description="复杂计算")
    clarification: Optional[str] = Field(default=None, description="澄清问题")
    reasoning: str = Field(description="推理过程")
```

### 3.2 错误的 Schema 设计（反例）

```python
# ❌ 错误：description 混入了业务逻辑
class Dimension(BaseModel):
    """维度字段
    
    当用户提到"按月"、"每月"时，设置 granularity 为 MONTH。  # ← 这是 Prompt 内容
    """
    field: str = Field(
        description="字段名称，必须从可用字段列表中选择"  # ← 这是 Prompt 内容
    )
    granularity: Optional[str] = Field(
        description="日期粒度，当用户提到时间相关词汇时设置"  # ← 这是 Prompt 内容
    )


# ❌ 错误：枚举值过多（11 种）
class CalcType(str, Enum):
    RANK = "RANK"
    DENSE_RANK = "DENSE_RANK"
    ROW_NUMBER = "ROW_NUMBER"
    PERCENT_OF_TOTAL = "PERCENT_OF_TOTAL"
    PERCENT_OF_PARENT = "PERCENT_OF_PARENT"
    RUNNING_SUM = "RUNNING_SUM"
    RUNNING_AVG = "RUNNING_AVG"
    DIFFERENCE = "DIFFERENCE"
    PERCENT_DIFFERENCE = "PERCENT_DIFFERENCE"
    MOVING_AVG = "MOVING_AVG"
    NONE = "NONE"
```

## 4. 示例设计模式

### 4.1 完整示例结构

```markdown
## 示例 1：简单查询

**问题：** 各省份的销售额

<analysis>
- 意图：DATA_QUERY（有具体度量"销售额"和维度"省份"）
- 度量：销售额，聚合 SUM
- 维度：省份
- 筛选：无
- 复杂计算：无（没有排名/占比/累计关键词）
</analysis>

**输出：**
```json
{
  "intent": "DATA_QUERY",
  "dimensions": [{"field": "省份"}],
  "measures": [{"field": "销售额", "aggregation": "SUM"}],
  "filters": [],
  "computation": null,
  "reasoning": "用户想查看各省份的销售额汇总"
}
```
```

### 4.2 反例设计模式

```markdown
## 反例：Top N 不是排名

**问题：** 销售额前10的省份

<analysis>
- 这是 Top N 筛选，不是排名计算
- 用户想要的是筛选后的子集，不是添加排名列
</analysis>

**正确输出：**
```json
{
  "filters": [{"field": "销售额", "operator": "top", "value": 10}],
  "computation": null
}
```

**错误输出（不要这样做）：**
```json
{
  "computation": {"calc_type": "RANK", ...}
}
```

**原因：** "前10名"表示筛选条件，不是要添加排名列
```

## 5. 决策规则模式

### 5.1 表格映射模式

```markdown
## 意图分类规则

| 条件 | 意图 | 说明 |
|------|------|------|
| 有具体度量 + 有具体维度 | DATA_QUERY | 完整的数据查询 |
| 缺少度量或维度 | CLARIFICATION | 需要澄清 |
| 询问字段/元数据 | GENERAL | 一般性问题 |
```

### 5.2 IF-THEN 条件模式

```markdown
## 日期处理规则

当前时间：{current_time}

IF 用户说"今年" THEN 转换为 {current_year}-01-01 到 今天
IF 用户说"去年" THEN 转换为 {last_year}-01-01 到 {last_year}-12-31
IF 用户说"上个月" THEN 转换为 上月第一天 到 上月最后一天
IF 用户说"最近7天" THEN 转换为 7天前 到 今天
```

### 5.3 关键词检测模式

```markdown
## 复杂计算检测规则

| 关键词 | calc_type | 说明 |
|-------|-----------|------|
| 排名、排行、第几名、Rank | RANK | 添加排名列 |
| 占比、百分比、份额、% of | PERCENT | 计算占总量的比例 |
| 累计、YTD、累积、Running | RUNNING | 累计求和 |
| 环比、同比、增长率、MoM、YoY | DIFF | 与上期比较 |
| 无以上关键词 | NONE | 简单聚合查询 |

**注意：**
- "前10名"、"Top N" 是筛选，不是排名计算
- 一个问题只能有一种复杂计算类型
```

## 6. 自我纠错检查清单

### 6.1 SemanticParser 检查清单

```xml
<self_correction>
## 自我检查规则

在输出前，检查以下内容：

1. **字段检查**：所有字段名是否来自"可用字段"列表？
   - 如果不是，返回 CLARIFICATION

2. **日期检查**：日期筛选是否转换为具体日期？
   - 不要保留"今年"这样的相对表达

3. **计算检查**：是否正确区分了 Top N 筛选和排名计算？
   - "前10名" → 筛选
   - "排名" → 计算

4. **完整性检查**：DATA_QUERY 是否至少有一个度量？
   - 如果没有，返回 CLARIFICATION
</self_correction>
```

### 6.2 Cursor 风格的 non_compliance 模式

```xml
<non_compliance>
- 如果未更新 TODO，下一轮立即纠正
- 如果未提供状态更新，下一轮纠正
</non_compliance>
```

### 6.3 复杂计算检查清单

```markdown
## 复杂计算检查

1. "前N名"、"Top N" → 是筛选，不是 RANK
2. "占比" → 需要确定分母（总计 vs 分组）
3. "环比" → 需要确定时间粒度（月 vs 周）
4. "累计" → 需要确定累计维度（时间 vs 其他）
```

## 7. 决策规则模式选择

### 7.1 何时使用表格映射

**适用场景**：条件和结果之间是简单的一对一映射

```markdown
## 意图分类规则

| 条件 | 意图 | 说明 |
|------|------|------|
| 有具体度量 + 有具体维度 | DATA_QUERY | 完整的数据查询 |
| 缺少度量或维度 | CLARIFICATION | 需要澄清 |
| 询问字段/元数据 | GENERAL | 一般性问题 |
```

### 7.2 何时使用 IF-THEN 条件

**适用场景**：需要动态计算或转换的规则

```markdown
## 日期处理规则

当前时间：{current_time}

IF 用户说"今年" THEN 转换为 {current_year}-01-01 到 今天
IF 用户说"去年" THEN 转换为 {last_year}-01-01 到 {last_year}-12-31
IF 用户说"上个月" THEN 转换为 上月第一天 到 上月最后一天
```

### 7.3 何时使用关键词检测

**适用场景**：基于关键词触发特定行为

```markdown
## 复杂计算检测规则

| 关键词 | calc_type | 说明 |
|-------|-----------|------|
| 排名、排行、第几名 | RANK | 添加排名列 |
| 占比、百分比、份额 | PERCENT | 计算占总量的比例 |
| 累计、YTD、累积 | RUNNING | 累计求和 |
| 环比、同比、增长率 | DIFF | 与上期比较 |
| 无以上关键词 | NONE | 简单聚合查询 |
```

### 7.4 何时使用优先级规则

**适用场景**：多个选项需要按优先级选择

```markdown
## 工具选择优先级

1. 文件操作：优先使用专用工具
   - 读取文件 → Read (不用 cat/head/tail)
   - 编辑文件 → Edit (不用 sed/awk)

2. 搜索策略：
   - 精确匹配 → Grep
   - 语义搜索 → Codebase Search
```

## 8. 参考资料

详细的 Prompt 和 Schema 设计模式请参考：
- `docs/prompt-and-schema-design-guide.md` - 完整的设计指南（包含具体示例）
- `docs/appendix-prompt-schema-patterns.md` - 设计模式详解
- `appendix/a-prompt-patterns.md` - Prompt 设计模式
- `appendix/b-schema-patterns.md` - Schema 设计模式
