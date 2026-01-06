# 附录 B：Schema 设计模式

## 1. 核心原则

### 1.1 职责分离

```
Schema description 应该：
✓ 说明字段"是什么" (What)
✗ 不说明"什么时候填" (When) ← 属于 Prompt
✗ 不说明"怎么判断" (How) ← 属于 Prompt
```

### 1.2 枚举设计原则

```python
# 原则：枚举值越少越好（5个以内最佳）

# ✅ 简化的枚举
class CalcType(str, Enum):
    RANK = "RANK"           # 排名
    PERCENT = "PERCENT"     # 占比
    RUNNING = "RUNNING"     # 累计
    DIFF = "DIFF"           # 差异
    NONE = "NONE"           # 无复杂计算

# ❌ 过于复杂的枚举（11种）
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

## 2. 正确的 Schema 设计

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
    """计算类型"""
    RANK = "RANK"
    PERCENT = "PERCENT"
    RUNNING = "RUNNING"
    DIFF = "DIFF"
    NONE = "NONE"


# ═══════════════════════════════════════════════════════════════
# 数据模型 - 只定义结构，description 只说"是什么"
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

## 3. 错误的 Schema 设计（反例）

```python
# ❌ 错误的 Schema 设计（混入了业务逻辑）
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
```

## 4. Schema 设计规范

### 4.1 字段命名

- 使用 snake_case
- 名称应自解释
- 避免缩写

### 4.2 类型约束

- 使用 `Literal` 约束字符串值
- 使用 `Enum` 定义枚举
- 使用 `Optional` 标记可选字段
- 使用 `List` 标记数组字段

### 4.3 嵌套层级

- 最多 2 层嵌套
- 复杂结构拆分为多个模型
- 避免深层嵌套

### 4.4 默认值

- 可选字段提供合理默认值
- 使用 `default_factory` 处理可变默认值
- 避免 `None` 作为默认值（除非有意义）

## 5. Tool 定义模式

### 5.1 标准 Tool 定义结构

```json
{
  "name": "tool_name",
  "description": "工具的主要用途描述。\n\n**When to use:**\n• 场景 1\n• 场景 2\n\n**When NOT to use:**\n• 场景 1\n• 场景 2\n\n**What you get:**\n• 返回内容 1\n• 返回内容 2",
  "parameters": {
    "type": "object",
    "properties": {
      "param1": {
        "type": "string",
        "description": "参数描述，包含示例"
      },
      "param2": {
        "type": "array",
        "items": {"type": "string"},
        "description": "数组参数描述"
      }
    },
    "required": ["param1"]
  }
}
```

### 5.2 Tool 使用指南模式

```markdown
## Tool: read_file

**Purpose:** 读取文件内容

**Usage Notes:**
- 必须在编辑前先读取文件
- 大文件使用 query 参数定位
- 支持图片文件

**Parameters:**
- `file_path` (required): 文件绝对路径
- `query` (optional): 大文件搜索关键词
- `start_line` (optional): 起始行号
- `end_line` (optional): 结束行号

**Best Practices:**
1. 小文件直接读取全部
2. 大文件使用 query 定位
3. 批量读取相关文件

**Anti-patterns:**
- ❌ 不要用 cat/head/tail 命令
- ❌ 不要猜测文件内容
```
