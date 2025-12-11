# 工具层设计

## 概述

本文档描述工具层的详细设计，包括所有业务工具和工具注册表。

对应项目结构：`src/tools/`

---

## 工具分类

| 类型 | 说明 | 示例 |
|------|------|------|
| 业务工具 | 我们实现的工具，封装现有组件 | get_metadata, parse_date, get_schema_module |
| 中间件工具 | 由中间件自动注入的工具 | write_todos, read_file |

---

## 1. 工具注册表

```python
# tableau_assistant/src/tools/registry.py

class ToolRegistry:
    """
    工具注册表
    
    管理业务工具的注册。
    注意：
    - 中间件提供的工具（如 write_todos）由中间件自动注入，不在此注册
    - FieldMapper 是独立节点（RAG + LLM 混合），不是工具
    """
    
    _tools: Dict[str, List[BaseTool]] = {
        "understanding": [],  # 含原 Boost 功能
        "insight": [],
        "replanner": [],
    }
    
    @classmethod
    def register(cls, node_type: str, tool: BaseTool):
        """注册工具到指定节点"""
        cls._tools[node_type].append(tool)
    
    @classmethod
    def get_tools(cls, node_type: str) -> List[BaseTool]:
        """获取节点的工具列表"""
        return cls._tools.get(node_type, [])
    
    @classmethod
    def auto_discover(cls):
        """自动发现并注册业务工具"""
        # understanding_tools（含原 Boost 功能）
        cls.register("understanding", get_metadata)        # 元数据获取（原 Boost 功能）
        cls.register("understanding", get_schema_module)   # 动态 Schema 模块选择
        cls.register("understanding", parse_date)          # 日期解析
        cls.register("understanding", detect_date_format)  # 日期格式检测
        
        # replanner_tools
        # 注意：write_todos 由 TodoListMiddleware 自动注入
        
        # 说明：
        # - Boost Agent 已移除，功能合并到 Understanding Agent
        # - FieldMapper Node 是独立节点（RAG + LLM 混合），直接调用 SemanticMapper
        # - QueryBuilder Node 是纯代码节点，调用 ImplementationResolver + ExpressionGenerator
        # - Execute Node 是纯代码节点，直接调用 VizQL API
```

---

## 2. 元数据工具

```python
# tableau_assistant/src/tools/metadata_tool.py

from langchain_core.tools import tool
from tableau_assistant.src.capabilities.metadata import MetadataManager


@tool
async def get_metadata(
    use_cache: bool = True,
    enhance: bool = True,
    filter_role: Optional[str] = None,
    filter_category: Optional[str] = None
) -> str:
    """
    获取数据源元数据
    
    Args:
        use_cache: 是否使用缓存 (默认 True)
        enhance: 是否增强元数据 (默认 True)
        filter_role: 按角色过滤 (dimension/measure)
        filter_category: 按类别过滤
    
    Returns:
        LLM 友好的字段列表（全量返回，大结果由 FilesystemMiddleware 处理）
    """
    metadata = await metadata_manager.get_metadata_async(
        use_cache=use_cache,
        enhance=enhance
    )
    
    # 应用过滤
    fields = metadata.fields
    if filter_role:
        fields = [f for f in fields if f.role == filter_role]
    if filter_category:
        fields = [f for f in fields if f.category == filter_category]
    
    # 转换为 LLM 友好格式（全量返回）
    return _format_metadata_for_llm(fields)
```

---

## 3. 日期工具

### 3.1 设计原则

**核心问题**：LLM 返回的日期值格式是不确定的（可能是 "2024"、"2024年"、"2024-Q1"、"第一季度2024" 等），不能依赖正则匹配来猜测格式。

**解决方案**：
1. **与 VizQL API 对齐**：直接映射到 VizQL 的三种日期筛选类型
2. **LLM 输出 RFC 3339 日期**：绝对日期直接输出 `YYYY-MM-DD` 格式，无需 DateParser 再计算
3. **DateParser 只处理相对日期**：相对日期（最近3个月）需要计算，绝对日期直接透传
4. **使用枚举类型**：所有多值字段使用 Enum，不使用 Literal 或 Any

**VizQL API 日期筛选类型对照**：
| VizQL filterType | 用途 | 对应场景 |
|------------------|------|----------|
| `QUANTITATIVE_DATE` | 绝对日期范围 | "2024年"、"2024年1月到5月" |
| `DATE` (RelativeDateFilter) | 相对日期 | "最近3个月"、"年初至今" |
| `SET` | 多个离散日期 | "2024年1月和2月" |

**架构关系**：
```
用户问题: "2024年第一季度的销售额"
    ↓
Understanding Agent (LLM)
    ↓ 输出 TimeFilterSpec（结构化）
    {
        "mode": "absolute_range",
        "start_date": "2024-01-01",  # LLM 直接输出 RFC 3339 格式
        "end_date": "2024-03-31"
    }
    ↓
QueryBuilder（直接透传到 VizQL）
    ↓
VizQL Filter: {
    "filterType": "QUANTITATIVE_DATE",
    "quantitativeFilterType": "RANGE",
    "minDate": "2024-01-01",
    "maxDate": "2024-03-31"
}
```

### 3.2 日期场景完整分类

在设计数据模型之前，必须先完整罗列所有日期场景：

| 场景类型 | 用户表达示例 | VizQL 筛选类型 | 说明 |
|----------|--------------|----------------|------|
| **单点绝对** | "2024年"、"本月"、"2024年Q1" | QUANTITATIVE_DATE | 单个时间点/周期 |
| **绝对范围** | "2024年1月到5月"、"从3月到6月" | QUANTITATIVE_DATE | 连续的日期范围 |
| **相对范围** | "最近3个月"、"年初至今" | DATE (RelativeDateFilter) | 相对于今天的范围 |
| **多离散点** | "2024年1月和2月"、"Q1和Q3" | SET | 多个不连续的时间点 |

### 3.3 TimeFilterSpec 数据模型（与 VizQL API 对齐）

```python
# tableau_assistant/src/models/semantic/enums.py

class TimeFilterMode(str, Enum):
    """
    时间筛选模式（与 VizQL filterType 对齐）
    
    <mapping_to_vizql>
    - ABSOLUTE_RANGE → filterType: "QUANTITATIVE_DATE"
    - RELATIVE → filterType: "DATE" (RelativeDateFilter)
    - SET → filterType: "SET"
    </mapping_to_vizql>
    """
    ABSOLUTE_RANGE = "absolute_range"  # 绝对日期范围（单点或范围）
    RELATIVE = "relative"              # 相对日期（最近N天/月/年）
    SET = "set"                        # 多个离散日期点


class PeriodType(str, Enum):
    """
    时间周期类型（与 VizQL PeriodType 完全对齐）
    
    <vizql_mapping>
    直接映射到 VizQL API 的 PeriodType enum
    </vizql_mapping>
    """
    MINUTES = "MINUTES"
    HOURS = "HOURS"
    DAYS = "DAYS"
    WEEKS = "WEEKS"
    MONTHS = "MONTHS"
    QUARTERS = "QUARTERS"
    YEARS = "YEARS"


class DateRangeType(str, Enum):
    """
    相对日期范围类型（与 VizQL dateRangeType 完全对齐）
    
    <vizql_mapping>
    直接映射到 VizQL API 的 RelativeDateFilter.dateRangeType
    </vizql_mapping>
    """
    CURRENT = "CURRENT"    # 当前周期（本月、今年）
    LAST = "LAST"          # 上一个周期（上个月、去年）
    LASTN = "LASTN"        # 最近N个周期（最近3个月）
    NEXT = "NEXT"          # 下一个周期
    NEXTN = "NEXTN"        # 未来N个周期
    TODATE = "TODATE"      # 至今（年初至今、月初至今）
```

```python
# tableau_assistant/src/models/semantic/query.py

class TimeFilterSpec(BaseModel):
    """
    时间筛选规格（与 VizQL API 对齐）
    
    <design_principles>
    1. 与 VizQL API 的三种日期筛选类型直接对应
    2. LLM 输出 RFC 3339 格式日期（YYYY-MM-DD），无需 DateParser 再计算
    3. 相对日期由 DateParser 计算，绝对日期直接透传
    4. 所有多值字段使用 Enum 类型
    </design_principles>
    
    <decision_tree>
    用户问题
      │
      ├─► 包含具体日期？
      │   ├─ YES: 是范围还是单点？
      │   │   ├─ 单点 ("2024年") → mode=ABSOLUTE_RANGE, start_date=..., end_date=...
      │   │   └─ 范围 ("1月到5月") → mode=ABSOLUTE_RANGE, start_date=..., end_date=...
      │   │
      │   └─ NO: 是相对日期还是多离散点？
      │       ├─ 相对 ("最近3个月") → mode=RELATIVE, period_type=..., date_range_type=...
      │       └─ 多点 ("1月和2月") → mode=SET, date_values=[...]
      │
    </decision_tree>
    
    <examples>
    # 场景1: 单点绝对 - "2024年"
    {
        "mode": "absolute_range",
        "start_date": "2024-01-01",
        "end_date": "2024-12-31"
    }
    
    # 场景2: 单点绝对 - "2024年Q1"
    {
        "mode": "absolute_range",
        "start_date": "2024-01-01",
        "end_date": "2024-03-31"
    }
    
    # 场景3: 绝对范围 - "2024年1月到5月"
    {
        "mode": "absolute_range",
        "start_date": "2024-01-01",
        "end_date": "2024-05-31"
    }
    
    # 场景4: 相对范围 - "最近3个月"
    {
        "mode": "relative",
        "period_type": "MONTHS",
        "date_range_type": "LASTN",
        "range_n": 3
    }
    
    # 场景5: 相对范围 - "年初至今"
    {
        "mode": "relative",
        "period_type": "YEARS",
        "date_range_type": "TODATE"
    }
    
    # 场景6: 相对范围 - "本月"
    {
        "mode": "relative",
        "period_type": "MONTHS",
        "date_range_type": "CURRENT"
    }
    
    # 场景7: 多离散点 - "2024年1月和2月"
    {
        "mode": "set",
        "date_values": ["2024-01", "2024-02"]
    }
    
    # 场景8: 多离散点 - "Q1和Q3"
    {
        "mode": "set",
        "date_values": ["2024-Q1", "2024-Q3"]
    }
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    mode: TimeFilterMode = Field(
        description="""时间筛选模式

<what>决定使用哪种 VizQL 筛选类型</what>
<when>ALWAYS required</when>

<decision_rule>
- 具体日期/日期范围 → ABSOLUTE_RANGE
- 相对表达（最近N、本月、年初至今）→ RELATIVE
- 多个离散日期点 → SET
</decision_rule>

<vizql_mapping>
- ABSOLUTE_RANGE → QuantitativeDateFilter (minDate, maxDate)
- RELATIVE → RelativeDateFilter (periodType, dateRangeType, rangeN)
- SET → SetFilter (values)
</vizql_mapping>"""
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # ABSOLUTE_RANGE 模式字段
    # ═══════════════════════════════════════════════════════════════════════
    
    start_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="""开始日期（RFC 3339 格式）

<what>日期范围的开始日期</what>
<when>REQUIRED when mode = ABSOLUTE_RANGE</when>
<format>YYYY-MM-DD（严格格式，LLM 必须计算并输出）</format>

<decision_rule>
LLM 必须将用户表达转换为具体日期：
- "2024年" → "2024-01-01"
- "2024年Q1" → "2024-01-01"
- "2024年3月" → "2024-03-01"
- "2024年1月到5月" → "2024-01-01"
</decision_rule>

<anti_patterns>
❌ 输出非标准格式: "2024-1-1", "2024/01/01"
❌ mode=RELATIVE 时设置此字段
</anti_patterns>"""
    )
    
    end_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="""结束日期（RFC 3339 格式）

<what>日期范围的结束日期</what>
<when>REQUIRED when mode = ABSOLUTE_RANGE</when>
<format>YYYY-MM-DD（严格格式，LLM 必须计算并输出）</format>

<decision_rule>
LLM 必须将用户表达转换为具体日期：
- "2024年" → "2024-12-31"
- "2024年Q1" → "2024-03-31"
- "2024年3月" → "2024-03-31"
- "2024年1月到5月" → "2024-05-31"
</decision_rule>

<note>
LLM 需要知道每月天数：
- 1,3,5,7,8,10,12月 → 31天
- 4,6,9,11月 → 30天
- 2月 → 28天（闰年29天）
</note>"""
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # RELATIVE 模式字段（与 VizQL RelativeDateFilter 对齐）
    # ═══════════════════════════════════════════════════════════════════════
    
    period_type: Optional[PeriodType] = Field(
        default=None,
        description="""时间周期类型

<what>相对日期的周期单位</what>
<when>REQUIRED when mode = RELATIVE</when>

<decision_rule>
- "天" / "日" → DAYS
- "周" → WEEKS
- "月" → MONTHS
- "季度" → QUARTERS
- "年" → YEARS
</decision_rule>

<vizql_mapping>
直接映射到 RelativeDateFilter.periodType
</vizql_mapping>"""
    )
    
    date_range_type: Optional[DateRangeType] = Field(
        default=None,
        description="""相对日期范围类型

<what>相对日期的计算方式</what>
<when>REQUIRED when mode = RELATIVE</when>

<decision_rule>
- "本月" / "今年" / "本周" → CURRENT
- "上个月" / "去年" / "上周" → LAST
- "最近3个月" / "最近7天" → LASTN
- "年初至今" / "月初至今" → TODATE
</decision_rule>

<vizql_mapping>
直接映射到 RelativeDateFilter.dateRangeType
</vizql_mapping>"""
    )
    
    range_n: Optional[int] = Field(
        default=None,
        ge=1,
        description="""周期数量

<what>最近/未来 N 个周期中的 N</what>
<when>REQUIRED when date_range_type = LASTN or NEXTN</when>

<decision_rule>
- "最近3个月" → 3
- "最近7天" → 7
- "最近2年" → 2
</decision_rule>

<vizql_mapping>
直接映射到 RelativeDateFilter.rangeN
</vizql_mapping>"""
    )
    
    anchor_date: Optional[str] = Field(
        default=None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="""锚定日期（可选）

<what>相对日期计算的参考日期</what>
<when>OPTIONAL, defaults to today</when>
<format>YYYY-MM-DD</format>

<vizql_mapping>
映射到 RelativeDateFilter.anchorDate
</vizql_mapping>"""
    )
    
    # ═══════════════════════════════════════════════════════════════════════
    # SET 模式字段
    # ═══════════════════════════════════════════════════════════════════════
    
    date_values: Optional[List[str]] = Field(
        default=None,
        description="""离散日期值列表

<what>多个不连续的日期点</what>
<when>REQUIRED when mode = SET</when>

<format>
支持多种粒度的日期值：
- 年: "2024"
- 季度: "2024-Q1", "2024-Q2"
- 月: "2024-01", "2024-02"
- 日: "2024-01-15", "2024-02-20"
</format>

<decision_rule>
- "2024年1月和2月" → ["2024-01", "2024-02"]
- "Q1和Q3" → ["2024-Q1", "2024-Q3"]
- "1月15日和2月20日" → ["2024-01-15", "2024-02-20"]
</decision_rule>

<vizql_mapping>
映射到 SetFilter.values
注意：VizQL SetFilter 需要具体日期值，
QueryBuilder 会根据粒度展开为具体日期
</vizql_mapping>"""
    )
    
    @model_validator(mode='after')
    def validate_mode_dependencies(self) -> 'TimeFilterSpec':
        """验证模式相关的字段依赖"""
        
        if self.mode == TimeFilterMode.ABSOLUTE_RANGE:
            if self.start_date is None:
                raise ValueError("start_date is required when mode=absolute_range")
            if self.end_date is None:
                raise ValueError("end_date is required when mode=absolute_range")
            # 清除其他模式的字段
            self.period_type = None
            self.date_range_type = None
            self.range_n = None
            self.date_values = None
        
        elif self.mode == TimeFilterMode.RELATIVE:
            if self.period_type is None:
                raise ValueError("period_type is required when mode=relative")
            if self.date_range_type is None:
                raise ValueError("date_range_type is required when mode=relative")
            if self.date_range_type in (DateRangeType.LASTN, DateRangeType.NEXTN):
                if self.range_n is None:
                    raise ValueError("range_n is required when date_range_type=LASTN/NEXTN")
            # 清除其他模式的字段
            self.start_date = None
            self.end_date = None
            self.date_values = None
        
        elif self.mode == TimeFilterMode.SET:
            if self.date_values is None or len(self.date_values) == 0:
                raise ValueError("date_values is required when mode=set")
            # 清除其他模式的字段
            self.start_date = None
            self.end_date = None
            self.period_type = None
            self.date_range_type = None
            self.range_n = None
        
        return self
```

### 3.4 DateParser 简化实现

由于 LLM 直接输出 RFC 3339 格式日期，DateParser 的职责大大简化：
- **绝对日期**：直接透传，无需计算
- **相对日期**：根据 period_type 和 date_range_type 计算具体日期
- **离散日期**：展开为具体日期列表

```python
# tableau_assistant/src/capabilities/date_processing/parser.py

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from calendar import monthrange
from typing import Tuple, List, Optional
from tableau_assistant.src.models.semantic.query import TimeFilterSpec
from tableau_assistant.src.models.semantic.enums import (
    TimeFilterMode, PeriodType, DateRangeType
)


class DateParser:
    """
    日期解析器（简化版）
    
    职责：
    1. 绝对日期：验证格式，直接透传
    2. 相对日期：计算具体日期范围
    3. 离散日期：展开为具体日期列表
    """
    
    def process_time_filter(
        self,
        time_filter: TimeFilterSpec,
        reference_date: Optional[datetime] = None
    ) -> dict:
        """
        处理时间筛选，返回 VizQL 兼容的筛选参数
        
        Args:
            time_filter: TimeFilterSpec 对象
            reference_date: 参考日期（用于相对时间计算，默认今天）
        
        Returns:
            VizQL 筛选参数字典
        """
        if reference_date is None:
            reference_date = datetime.now()
        
        if time_filter.mode == TimeFilterMode.ABSOLUTE_RANGE:
            return self._process_absolute_range(time_filter)
        elif time_filter.mode == TimeFilterMode.RELATIVE:
            return self._process_relative(time_filter, reference_date)
        elif time_filter.mode == TimeFilterMode.SET:
            return self._process_set(time_filter)
        else:
            raise ValueError(f"不支持的时间筛选模式: {time_filter.mode}")
    
    def _process_absolute_range(self, time_filter: TimeFilterSpec) -> dict:
        """
        处理绝对日期范围
        
        LLM 已输出 RFC 3339 格式，直接透传到 VizQL
        """
        # 验证日期格式
        self._validate_date_format(time_filter.start_date)
        self._validate_date_format(time_filter.end_date)
        
        return {
            "filter_type": "QUANTITATIVE_DATE",
            "quantitative_filter_type": "RANGE",
            "min_date": time_filter.start_date,
            "max_date": time_filter.end_date
        }
    
    def _process_relative(
        self,
        time_filter: TimeFilterSpec,
        reference_date: datetime
    ) -> dict:
        """
        处理相对日期
        
        两种输出方式：
        1. 直接使用 VizQL RelativeDateFilter（推荐）
        2. 计算为绝对日期范围（兼容性）
        """
        # 方式1: 直接返回 RelativeDateFilter 参数（推荐）
        result = {
            "filter_type": "DATE",
            "period_type": time_filter.period_type.value,
            "date_range_type": time_filter.date_range_type.value,
        }
        
        if time_filter.range_n is not None:
            result["range_n"] = time_filter.range_n
        
        if time_filter.anchor_date is not None:
            result["anchor_date"] = time_filter.anchor_date
        
        return result
    
    def calculate_relative_dates(
        self,
        time_filter: TimeFilterSpec,
        reference_date: Optional[datetime] = None
    ) -> Tuple[str, str]:
        """
        计算相对日期的具体日期范围（用于需要具体日期的场景）
        
        Returns:
            (start_date, end_date) 元组，格式为 "YYYY-MM-DD"
        """
        if reference_date is None:
            reference_date = datetime.now()
        
        period_type = time_filter.period_type
        date_range_type = time_filter.date_range_type
        range_n = time_filter.range_n or 1
        
        if date_range_type == DateRangeType.CURRENT:
            return self._calc_current_period(reference_date, period_type)
        elif date_range_type == DateRangeType.LAST:
            return self._calc_last_period(reference_date, period_type)
        elif date_range_type == DateRangeType.LASTN:
            return self._calc_lastn_periods(reference_date, period_type, range_n)
        elif date_range_type == DateRangeType.TODATE:
            return self._calc_todate(reference_date, period_type)
        else:
            raise ValueError(f"不支持的相对日期类型: {date_range_type}")
    
    def _calc_current_period(
        self, ref: datetime, period_type: PeriodType
    ) -> Tuple[str, str]:
        """计算当前周期"""
        if period_type == PeriodType.DAYS:
            return (ref.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.WEEKS:
            start = ref - timedelta(days=ref.weekday())
            end = start + timedelta(days=6)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.MONTHS:
            start = ref.replace(day=1)
            _, last_day = monthrange(ref.year, ref.month)
            end = ref.replace(day=last_day)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.QUARTERS:
            quarter = (ref.month - 1) // 3 + 1
            start_month = (quarter - 1) * 3 + 1
            end_month = quarter * 3
            start = ref.replace(month=start_month, day=1)
            _, last_day = monthrange(ref.year, end_month)
            end = ref.replace(month=end_month, day=last_day)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.YEARS:
            start = ref.replace(month=1, day=1)
            end = ref.replace(month=12, day=31)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _calc_last_period(
        self, ref: datetime, period_type: PeriodType
    ) -> Tuple[str, str]:
        """计算上一个周期"""
        if period_type == PeriodType.DAYS:
            last = ref - timedelta(days=1)
            return (last.strftime("%Y-%m-%d"), last.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.WEEKS:
            last_week_start = ref - timedelta(days=ref.weekday() + 7)
            last_week_end = last_week_start + timedelta(days=6)
            return (last_week_start.strftime("%Y-%m-%d"), last_week_end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.MONTHS:
            last_month = ref - relativedelta(months=1)
            start = last_month.replace(day=1)
            _, last_day = monthrange(last_month.year, last_month.month)
            end = last_month.replace(day=last_day)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.QUARTERS:
            # 上一个季度
            current_quarter = (ref.month - 1) // 3 + 1
            if current_quarter == 1:
                last_quarter = 4
                year = ref.year - 1
            else:
                last_quarter = current_quarter - 1
                year = ref.year
            start_month = (last_quarter - 1) * 3 + 1
            end_month = last_quarter * 3
            start = datetime(year, start_month, 1)
            _, last_day = monthrange(year, end_month)
            end = datetime(year, end_month, last_day)
            return (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.YEARS:
            last_year = ref.year - 1
            return (f"{last_year}-01-01", f"{last_year}-12-31")
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _calc_lastn_periods(
        self, ref: datetime, period_type: PeriodType, n: int
    ) -> Tuple[str, str]:
        """计算最近 N 个周期"""
        if period_type == PeriodType.DAYS:
            start = ref - timedelta(days=n - 1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.WEEKS:
            start = ref - timedelta(weeks=n)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.MONTHS:
            start = ref - relativedelta(months=n - 1)
            start = start.replace(day=1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.QUARTERS:
            start = ref - relativedelta(months=(n - 1) * 3)
            quarter = (start.month - 1) // 3 + 1
            start_month = (quarter - 1) * 3 + 1
            start = start.replace(month=start_month, day=1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.YEARS:
            start_year = ref.year - n + 1
            return (f"{start_year}-01-01", ref.strftime("%Y-%m-%d"))
        else:
            raise ValueError(f"不支持的周期类型: {period_type}")
    
    def _calc_todate(
        self, ref: datetime, period_type: PeriodType
    ) -> Tuple[str, str]:
        """计算至今（年初至今、月初至今等）"""
        if period_type == PeriodType.MONTHS:
            start = ref.replace(day=1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.QUARTERS:
            quarter = (ref.month - 1) // 3 + 1
            start_month = (quarter - 1) * 3 + 1
            start = ref.replace(month=start_month, day=1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        elif period_type == PeriodType.YEARS:
            start = ref.replace(month=1, day=1)
            return (start.strftime("%Y-%m-%d"), ref.strftime("%Y-%m-%d"))
        else:
            raise ValueError(f"不支持的至今类型: {period_type}")
    
    def _process_set(self, time_filter: TimeFilterSpec) -> dict:
        """
        处理离散日期集合
        
        将日期值展开为 VizQL SetFilter 格式
        """
        expanded_values = []
        for value in time_filter.date_values:
            expanded_values.extend(self._expand_date_value(value))
        
        return {
            "filter_type": "SET",
            "values": expanded_values,
            "exclude": False
        }
    
    def _expand_date_value(self, value: str) -> List[str]:
        """
        展开日期值为具体日期列表
        
        支持的格式：
        - "2024" → 年份（返回原值，由 VizQL 处理）
        - "2024-Q1" → 季度（展开为月份）
        - "2024-01" → 月份（返回原值）
        - "2024-01-15" → 具体日期（返回原值）
        """
        import re
        
        # 季度格式: 2024-Q1
        quarter_match = re.match(r'^(\d{4})-Q([1-4])$', value, re.IGNORECASE)
        if quarter_match:
            year = int(quarter_match.group(1))
            quarter = int(quarter_match.group(2))
            start_month = (quarter - 1) * 3 + 1
            return [f"{year}-{m:02d}" for m in range(start_month, start_month + 3)]
        
        # 其他格式直接返回
        return [value]
    
    def _validate_date_format(self, date_str: str) -> None:
        """验证日期格式是否为 YYYY-MM-DD"""
        import re
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            raise ValueError(f"日期格式错误，期望 YYYY-MM-DD，实际: {date_str}")
        
        # 验证日期有效性
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"无效的日期: {date_str}")
```

### 3.5 日期工具实现

```python
# tableau_assistant/src/tools/date_tool.py

import json
from typing import Optional, List
from datetime import datetime
from langchain_core.tools import tool
from tableau_assistant.src.capabilities.date_processing.parser import DateParser
from tableau_assistant.src.models.semantic.query import TimeFilterSpec


# 全局解析器实例
_date_parser = DateParser()


@tool
def process_time_filter(
    time_filter_json: str,
    reference_date: Optional[str] = None
) -> str:
    """
    处理时间筛选，返回 VizQL 兼容的筛选参数
    
    LLM 输出 TimeFilterSpec 格式，此工具转换为 VizQL 筛选参数。
    
    Args:
        time_filter_json: TimeFilterSpec JSON 格式
        
            绝对日期范围示例（LLM 直接输出 RFC 3339 日期）:
            - {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-12-31"}
            - {"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-03-31"}
            
            相对日期示例:
            - {"mode": "relative", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
            - {"mode": "relative", "period_type": "MONTHS", "date_range_type": "CURRENT"}
            - {"mode": "relative", "period_type": "YEARS", "date_range_type": "TODATE"}
            
            离散日期示例:
            - {"mode": "set", "date_values": ["2024-01", "2024-02"]}
            - {"mode": "set", "date_values": ["2024-Q1", "2024-Q3"]}
        
        reference_date: 参考日期（YYYY-MM-DD），用于相对时间计算，默认今天
    
    Returns:
        JSON 格式的 VizQL 筛选参数:
        
        绝对日期范围:
        {"filter_type": "QUANTITATIVE_DATE", "quantitative_filter_type": "RANGE", 
         "min_date": "2024-01-01", "max_date": "2024-12-31"}
        
        相对日期:
        {"filter_type": "DATE", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
        
        离散日期:
        {"filter_type": "SET", "values": ["2024-01", "2024-02"], "exclude": false}
    
    Examples:
        # 绝对日期范围
        >>> process_time_filter('{"mode": "absolute_range", "start_date": "2024-01-01", "end_date": "2024-12-31"}')
        {"filter_type": "QUANTITATIVE_DATE", "quantitative_filter_type": "RANGE", "min_date": "2024-01-01", "max_date": "2024-12-31"}
        
        # 相对日期 - 最近3个月
        >>> process_time_filter('{"mode": "relative", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}')
        {"filter_type": "DATE", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}
        
        # 离散日期
        >>> process_time_filter('{"mode": "set", "date_values": ["2024-01", "2024-02"]}')
        {"filter_type": "SET", "values": ["2024-01", "2024-02"], "exclude": false}
    """
    try:
        time_filter = TimeFilterSpec(**json.loads(time_filter_json))
        ref_date = datetime.strptime(reference_date, "%Y-%m-%d") if reference_date else None
        result = _date_parser.process_time_filter(time_filter, ref_date)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def calculate_relative_dates(
    time_filter_json: str,
    reference_date: Optional[str] = None
) -> str:
    """
    计算相对日期的具体日期范围
    
    当需要将相对日期转换为具体日期时使用（例如用于 QUANTITATIVE_DATE 筛选）。
    
    Args:
        time_filter_json: TimeFilterSpec JSON 格式（mode 必须为 "relative"）
        reference_date: 参考日期（YYYY-MM-DD），默认今天
    
    Returns:
        JSON 格式: {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}
    
    Examples:
        # 最近3个月（假设今天是 2024-12-11）
        >>> calculate_relative_dates('{"mode": "relative", "period_type": "MONTHS", "date_range_type": "LASTN", "range_n": 3}')
        {"start_date": "2024-10-01", "end_date": "2024-12-11"}
        
        # 年初至今
        >>> calculate_relative_dates('{"mode": "relative", "period_type": "YEARS", "date_range_type": "TODATE"}')
        {"start_date": "2024-01-01", "end_date": "2024-12-11"}
    """
    try:
        time_filter = TimeFilterSpec(**json.loads(time_filter_json))
        if time_filter.mode.value != "relative":
            return json.dumps({"error": "此工具只处理相对日期（mode=relative）"})
        
        ref_date = datetime.strptime(reference_date, "%Y-%m-%d") if reference_date else None
        start_date, end_date = _date_parser.calculate_relative_dates(time_filter, ref_date)
        return json.dumps({"start_date": start_date, "end_date": end_date})
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def detect_date_format(sample_values: List[str]) -> str:
    """
    检测日期格式
    
    用于检测 STRING 类型字段的日期格式，帮助 LLM 理解数据源中的日期字段。
    
    Args:
        sample_values: 样本值列表（至少 3 个值）
    
    Returns:
        {"format_type": "ISO_DATE", "pattern": "YYYY-MM-DD", "conversion_hint": "..."}
    
    Examples:
        >>> detect_date_format(["2024-01-15", "2024-02-20", "2024-03-25"])
        {"format_type": "ISO_DATE", "pattern": "YYYY-MM-DD", "conversion_hint": "标准 ISO 日期格式"}
        
        >>> detect_date_format(["01/15/2024", "02/20/2024", "03/25/2024"])
        {"format_type": "US_DATE", "pattern": "MM/DD/YYYY", "conversion_hint": "美国日期格式"}
    """
    from tableau_assistant.src.capabilities.date_processing.manager import DateManager
    
    date_manager = DateManager()
    format_type = date_manager.detect_field_date_format(sample_values)
    
    if format_type:
        info = date_manager.get_format_info(format_type)
        return json.dumps({
            "format_type": format_type.value,
            "pattern": info["pattern"],
            "conversion_hint": info.get("description", f"使用 {info['pattern']} 格式解析")
        }, ensure_ascii=False)
    
    return json.dumps({"format_type": None, "error": "无法检测日期格式"}, ensure_ascii=False)
```

### 3.6 LLM Prompt 日期处理指南

Understanding Agent 的 Prompt 中需要包含以下日期处理指南，确保 LLM 输出正确的 TimeFilterSpec：

```markdown
## 日期筛选处理指南

### 日期场景识别

当用户问题包含时间条件时，你需要识别属于哪种场景：

| 场景 | 用户表达示例 | mode 值 |
|------|--------------|---------|
| 单点绝对 | "2024年"、"2024年Q1"、"3月" | absolute_range |
| 绝对范围 | "2024年1月到5月"、"从3月到6月" | absolute_range |
| 相对范围 | "最近3个月"、"年初至今"、"本月" | relative |
| 多离散点 | "2024年1月和2月"、"Q1和Q3" | set |

### 绝对日期输出规则（mode=absolute_range）

**你必须直接输出 RFC 3339 格式的日期（YYYY-MM-DD）**，不要输出模糊的值。

日期计算参考：
- 年份: "2024年" → start_date="2024-01-01", end_date="2024-12-31"
- 季度: "2024年Q1" → start_date="2024-01-01", end_date="2024-03-31"
  - Q1: 01-01 ~ 03-31
  - Q2: 04-01 ~ 06-30
  - Q3: 07-01 ~ 09-30
  - Q4: 10-01 ~ 12-31
- 月份: "2024年3月" → start_date="2024-03-01", end_date="2024-03-31"
  - 每月天数: 1,3,5,7,8,10,12月=31天; 4,6,9,11月=30天; 2月=28天(闰年29天)
- 日期: "2024年3月15日" → start_date="2024-03-15", end_date="2024-03-15"
- 范围: "2024年1月到5月" → start_date="2024-01-01", end_date="2024-05-31"

### 相对日期输出规则（mode=relative）

使用 VizQL API 的枚举值：

period_type 映射：
- "天/日" → "DAYS"
- "周" → "WEEKS"
- "月" → "MONTHS"
- "季度" → "QUARTERS"
- "年" → "YEARS"

date_range_type 映射：
- "本月/今年/本周" → "CURRENT"
- "上个月/去年/上周" → "LAST"
- "最近N个..." → "LASTN"（需要 range_n）
- "年初至今/月初至今" → "TODATE"

### 离散日期输出规则（mode=set）

date_values 格式：
- 年: ["2024", "2025"]
- 季度: ["2024-Q1", "2024-Q3"]
- 月: ["2024-01", "2024-02"]
- 日: ["2024-01-15", "2024-02-20"]

### 完整示例

**示例1: "2024年的销售额"**
```json
{
  "mode": "absolute_range",
  "start_date": "2024-01-01",
  "end_date": "2024-12-31"
}
```

**示例2: "2024年第一季度的销售额"**
```json
{
  "mode": "absolute_range",
  "start_date": "2024-01-01",
  "end_date": "2024-03-31"
}
```

**示例3: "2024年1月到5月的销售额"**
```json
{
  "mode": "absolute_range",
  "start_date": "2024-01-01",
  "end_date": "2024-05-31"
}
```

**示例4: "最近3个月的销售额"**
```json
{
  "mode": "relative",
  "period_type": "MONTHS",
  "date_range_type": "LASTN",
  "range_n": 3
}
```

**示例5: "年初至今的销售额"**
```json
{
  "mode": "relative",
  "period_type": "YEARS",
  "date_range_type": "TODATE"
}
```

**示例6: "本月的销售额"**
```json
{
  "mode": "relative",
  "period_type": "MONTHS",
  "date_range_type": "CURRENT"
}
```

**示例7: "2024年1月和2月的销售额"**
```json
{
  "mode": "set",
  "date_values": ["2024-01", "2024-02"]
}
```

**示例8: "Q1和Q3的销售额"**
```json
{
  "mode": "set",
  "date_values": ["2024-Q1", "2024-Q3"]
}
```
```

### 3.7 QueryBuilder 日期筛选转换

QueryBuilder 将 TimeFilterSpec 转换为 VizQL Filter：

```python
# tableau_assistant/src/workflow/nodes/query_builder.py

def _build_date_filter(
    self,
    field_caption: str,
    time_filter: TimeFilterSpec
) -> dict:
    """
    将 TimeFilterSpec 转换为 VizQL Filter
    
    Args:
        field_caption: 日期字段名
        time_filter: TimeFilterSpec 对象
    
    Returns:
        VizQL Filter 字典
    """
    base_filter = {
        "field": {"fieldCaption": field_caption}
    }
    
    if time_filter.mode == TimeFilterMode.ABSOLUTE_RANGE:
        # 转换为 QuantitativeDateFilter
        return {
            **base_filter,
            "filterType": "QUANTITATIVE_DATE",
            "quantitativeFilterType": "RANGE",
            "minDate": time_filter.start_date,
            "maxDate": time_filter.end_date
        }
    
    elif time_filter.mode == TimeFilterMode.RELATIVE:
        # 转换为 RelativeDateFilter
        result = {
            **base_filter,
            "filterType": "DATE",
            "periodType": time_filter.period_type.value,
            "dateRangeType": time_filter.date_range_type.value
        }
        if time_filter.range_n is not None:
            result["rangeN"] = time_filter.range_n
        if time_filter.anchor_date is not None:
            result["anchorDate"] = time_filter.anchor_date
        return result
    
    elif time_filter.mode == TimeFilterMode.SET:
        # 转换为 SetFilter
        # 注意：需要展开日期值
        expanded_values = self._expand_date_values(time_filter.date_values)
        return {
            **base_filter,
            "filterType": "SET",
            "values": expanded_values,
            "exclude": False
        }
    
    else:
        raise ValueError(f"不支持的时间筛选模式: {time_filter.mode}")

def _expand_date_values(self, date_values: List[str]) -> List[str]:
    """
    展开日期值
    
    将季度等粗粒度日期展开为 VizQL 可接受的格式
    """
    import re
    expanded = []
    for value in date_values:
        # 季度格式: 2024-Q1 → 展开为月份
        quarter_match = re.match(r'^(\d{4})-Q([1-4])$', value, re.IGNORECASE)
        if quarter_match:
            year = int(quarter_match.group(1))
            quarter = int(quarter_match.group(2))
            start_month = (quarter - 1) * 3 + 1
            for m in range(start_month, start_month + 3):
                expanded.append(f"{year}-{m:02d}")
        else:
            expanded.append(value)
    return expanded
```

---

## 4. FieldMapper Node（独立节点，非工具）

**注意**：FieldMapper 已从工具提升为独立的工作流节点，详见 `node-design.md`。

**设计变更说明**：
- **旧设计**：`semantic_map_fields` 是工具，供 FieldMapper 组件内部调用
- **新设计**：FieldMapper 是独立节点（RAG + LLM 混合），直接调用 SemanticMapper

**架构关系**：
```
Understanding Node
    ↓ SemanticQuery（业务术语）
FieldMapper Node（RAG + LLM 混合节点）
    ├── SemanticMapper.search()  ← RAG 检索（已实现）
    ├── 置信度 >= 0.9? → 直接返回（快速路径，无需 LLM）
    └── 置信度 < 0.9? → LLM 从 top-k 候选中选择
    ↓ MappedQuery（技术字段）
QueryBuilder Node（纯代码）
```

**优势**：
1. 清晰分离职责：语义理解 → 字段映射 → 查询构建
2. 减少冗余封装：不再需要 `semantic_map_fields` 工具
3. 更好的可观测性：FieldMapper 作为独立节点，可以单独监控和调试

---

## 5. Schema 模块选择工具

```python
# tableau_assistant/src/tools/schema_tool.py

from langchain_core.tools import tool
from tableau_assistant.src.capabilities.schema.registry import SchemaModuleRegistry


@tool
def get_schema_module(module_names: List[str]) -> str:
    """
    获取指定数据模型模块的详细填写规则。
    
    在生成结构化输出之前调用此工具，只获取你需要的模块！
    这样可以减少 token 消耗，提高响应速度。
    
    Args:
        module_names: 需要的模块列表，可选值:
            - measures: 度量字段（销售额、利润等数值）
            - dimensions: 维度字段（分组、分类）
            - date_fields: 日期分组字段（按年、按月）
            - date_filters: 日期筛选条件（2024年、最近3个月）
            - filters: 非日期筛选条件（华东地区、销售额>1000）
            - topn: TopN 筛选（前10名、TOP5）
            - table_calcs: 表计算（累计、排名、占比）
    
    Returns:
        所选模块的详细填写规则
    """
    valid_modules = SchemaModuleRegistry.get_all_module_names()
    invalid_modules = [m for m in module_names if m not in valid_modules]
    
    if invalid_modules:
        return f"<error>无效的模块名称: {invalid_modules}。可用模块: {valid_modules}</error>"
    
    return SchemaModuleRegistry.get_modules(module_names)
```

### Schema 模块注册表

```python
# tableau_assistant/src/capabilities/schema/registry.py

SCHEMA_MODULES = {
    "measures": SchemaModule(
        name="measures",
        description="度量字段（销售额、利润等数值概念）",
        content="..."  # 详细填写规则
    ),
    "dimensions": SchemaModule(
        name="dimensions",
        description="维度字段（分组、分类概念）",
        content="..."
    ),
    "date_fields": SchemaModule(
        name="date_fields",
        description="日期分组字段（按年、按月）",
        content="..."
    ),
    "date_filters": SchemaModule(
        name="date_filters",
        description="日期筛选条件（2024年、最近3个月）",
        content="..."
    ),
    "filters": SchemaModule(
        name="filters",
        description="非日期筛选条件（华东地区、销售额>1000）",
        content="..."
    ),
    "topn": SchemaModule(
        name="topn",
        description="TopN 筛选（前10名、TOP5）",
        content="..."
    ),
    "table_calcs": SchemaModule(
        name="table_calcs",
        description="表计算（累计、排名、占比）",
        content="..."
    ),
}
```

### Token 节省效果

```
传统方式（全量注入）：
  Prompt = 系统指令 + 完整 Schema（所有模块）+ 用户问题
  Token 消耗: ~1400 tokens

新方式（按需拉取）：
  Prompt = 系统指令 + 模块索引（只有名称和简介）+ 用户问题
  LLM 调用 get_schema_module(["measures", "dimensions"])
  Token 消耗: ~600 tokens

节省: ~57%
```
