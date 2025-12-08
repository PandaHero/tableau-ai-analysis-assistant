"""
Schema Tool - Schema 模块选择工具

动态加载 Schema 模块，减少 token 消耗。

特性：
- 按需加载 Schema 模块
- 减少 token 消耗 40-60%
- 支持模块验证
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SchemaModule:
    """Schema 模块定义"""
    name: str
    description: str
    content: str


class SchemaModuleRegistry:
    """
    Schema 模块注册表
    
    管理所有可用的 Schema 模块，支持按需加载。
    """
    
    _modules: Dict[str, SchemaModule] = {}
    _initialized: bool = False
    
    @classmethod
    def _ensure_initialized(cls) -> None:
        """确保模块已初始化"""
        if cls._initialized:
            return
        
        cls._modules = {
            "measures": SchemaModule(
                name="measures",
                description="度量字段（销售额、利润等数值概念）",
                content="""
## measures（度量字段）

度量是可以进行数学运算的数值字段。

### 填写规则：
1. **field_name**: 必填，使用元数据中的精确字段名
2. **aggregation**: 可选，聚合方式
   - SUM: 求和（默认）
   - AVG: 平均值
   - COUNT: 计数
   - COUNTD: 去重计数
   - MIN: 最小值
   - MAX: 最大值
   - MEDIAN: 中位数

### 示例：
```json
{
  "measures": [
    {"field_name": "Sales", "aggregation": "SUM"},
    {"field_name": "Profit", "aggregation": "AVG"}
  ]
}
```

### 注意事项：
- 如果用户没有指定聚合方式，默认使用 SUM
- 对于"数量"类字段，通常使用 SUM
- 对于"单价"类字段，通常使用 AVG
"""
            ),
            
            "dimensions": SchemaModule(
                name="dimensions",
                description="维度字段（分组、分类概念）",
                content="""
## dimensions（维度字段）

维度是用于分组和分类的字段。

### 填写规则：
1. **field_name**: 必填，使用元数据中的精确字段名
2. **granularity**: 可选，时间粒度（仅时间维度需要）
   - YEAR: 年
   - QUARTER: 季度
   - MONTH: 月
   - WEEK: 周
   - DAY: 日

### 示例：
```json
{
  "dimensions": [
    {"field_name": "Region"},
    {"field_name": "Order Date", "granularity": "MONTH"}
  ]
}
```

### 注意事项：
- 非时间维度不需要 granularity
- 时间维度的 granularity 根据用户需求选择
- "按月"、"每月" → MONTH
- "按年"、"每年" → YEAR
"""
            ),
            
            "date_fields": SchemaModule(
                name="date_fields",
                description="日期分组字段（按年、按月）",
                content="""
## date_fields（日期分组字段）

用于时间维度的分组设置。

### 填写规则：
1. **field_name**: 必填，日期字段名
2. **granularity**: 必填，时间粒度
   - YEAR: 按年分组
   - QUARTER: 按季度分组
   - MONTH: 按月分组
   - WEEK: 按周分组
   - DAY: 按日分组

### 关键词映射：
- "按年"、"每年"、"年度" → YEAR
- "按季度"、"每季度"、"季度" → QUARTER
- "按月"、"每月"、"月度" → MONTH
- "按周"、"每周"、"周" → WEEK
- "按日"、"每日"、"日" → DAY

### 示例：
```json
{
  "date_fields": [
    {"field_name": "Order Date", "granularity": "MONTH"}
  ]
}
```
"""
            ),
            
            "date_filters": SchemaModule(
                name="date_filters",
                description="日期筛选条件（2024年、最近3个月）",
                content="""
## date_filters（日期筛选条件）

用于筛选特定时间范围的数据。

### 填写规则：
1. **field_name**: 必填，日期字段名
2. **filter_type**: 必填，筛选类型
   - relative: 相对日期（最近N天/月/年）
   - absolute: 绝对日期（具体日期范围）
3. **relative_type**: 相对日期类型（filter_type=relative 时必填）
   - LASTN: 最近N个周期
   - LAST: 上一个周期
   - CURRENT: 当前周期
   - NEXT: 下一个周期
   - NEXTN: 未来N个周期
4. **period_type**: 周期类型
   - YEARS, QUARTERS, MONTHS, WEEKS, DAYS
5. **range_n**: 周期数量（LASTN/NEXTN 时必填）
6. **start_date/end_date**: 绝对日期范围（filter_type=absolute 时必填）

### 示例：
```json
// 最近3个月
{
  "date_filters": [{
    "field_name": "Order Date",
    "filter_type": "relative",
    "relative_type": "LASTN",
    "period_type": "MONTHS",
    "range_n": 3
  }]
}

// 2024年
{
  "date_filters": [{
    "field_name": "Order Date",
    "filter_type": "absolute",
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
  }]
}
```
"""
            ),
            
            "filters": SchemaModule(
                name="filters",
                description="非日期筛选条件（华东地区、销售额>1000）",
                content="""
## filters（非日期筛选条件）

用于筛选特定维度值或度量范围。

### 填写规则：
1. **field_name**: 必填，字段名
2. **operator**: 必填，操作符
   - 维度：IN, NOT_IN, EQUALS, NOT_EQUALS
   - 度量：GT, GTE, LT, LTE, BETWEEN
3. **values**: 筛选值（IN/NOT_IN 时为数组）
4. **value**: 单个筛选值（EQUALS/NOT_EQUALS/比较操作符）
5. **min_value/max_value**: 范围值（BETWEEN 时使用）

### 示例：
```json
// 华东地区
{
  "filters": [{
    "field_name": "Region",
    "operator": "IN",
    "values": ["华东"]
  }]
}

// 销售额大于1000
{
  "filters": [{
    "field_name": "Sales",
    "operator": "GT",
    "value": 1000
  }]
}

// 销售额在1000到5000之间
{
  "filters": [{
    "field_name": "Sales",
    "operator": "BETWEEN",
    "min_value": 1000,
    "max_value": 5000
  }]
}
```
"""
            ),
            
            "topn": SchemaModule(
                name="topn",
                description="TopN 筛选（前10名、TOP5）",
                content="""
## topn（TopN 筛选）

用于获取排名前N或后N的数据。

### 填写规则：
1. **field_name**: 必填，排序依据的度量字段
2. **n**: 必填，数量
3. **direction**: 必填，方向
   - TOP: 前N名（最大的N个）
   - BOTTOM: 后N名（最小的N个）
4. **by_dimension**: 可选，分组维度（按维度分别取TopN）

### 关键词映射：
- "前10"、"TOP10"、"最高10" → direction=TOP, n=10
- "后5"、"最低5"、"倒数5" → direction=BOTTOM, n=5

### 示例：
```json
// 销售额前10名
{
  "topn": {
    "field_name": "Sales",
    "n": 10,
    "direction": "TOP"
  }
}

// 每个地区销售额前5名
{
  "topn": {
    "field_name": "Sales",
    "n": 5,
    "direction": "TOP",
    "by_dimension": "Region"
  }
}
```
"""
            ),
            
            "table_calcs": SchemaModule(
                name="table_calcs",
                description="表计算（累计、排名、占比）",
                content="""
## table_calcs（表计算）

用于计算累计值、排名、占比等。

### 填写规则：
1. **calc_type**: 必填，计算类型
   - RUNNING_TOTAL: 累计求和
   - RUNNING_AVG: 累计平均
   - RANK: 排名
   - RANK_DENSE: 密集排名
   - PERCENT_OF_TOTAL: 占比
   - MOVING_AVG: 移动平均
   - DIFFERENCE: 差值
   - PERCENT_DIFFERENCE: 百分比差值
2. **source_field**: 必填，源度量字段
3. **addressing**: 可选，计算方向（沿哪个维度计算）
4. **window_size**: 可选，窗口大小（移动计算时使用）

### 关键词映射：
- "累计"、"累积"、"running total" → RUNNING_TOTAL
- "排名"、"排序"、"rank" → RANK
- "占比"、"百分比"、"percent" → PERCENT_OF_TOTAL
- "移动平均"、"滚动平均" → MOVING_AVG
- "同比"、"环比" → DIFFERENCE 或 PERCENT_DIFFERENCE

### 示例：
```json
// 累计销售额
{
  "table_calcs": [{
    "calc_type": "RUNNING_TOTAL",
    "source_field": "Sales"
  }]
}

// 销售额排名
{
  "table_calcs": [{
    "calc_type": "RANK",
    "source_field": "Sales"
  }]
}

// 销售额占比
{
  "table_calcs": [{
    "calc_type": "PERCENT_OF_TOTAL",
    "source_field": "Sales"
  }]
}

// 3个月移动平均
{
  "table_calcs": [{
    "calc_type": "MOVING_AVG",
    "source_field": "Sales",
    "window_size": 3
  }]
}
```
"""
            ),
        }
        
        cls._initialized = True
        logger.info(f"SchemaModuleRegistry initialized with {len(cls._modules)} modules")
    
    @classmethod
    def get_all_module_names(cls) -> List[str]:
        """获取所有模块名称"""
        cls._ensure_initialized()
        return list(cls._modules.keys())
    
    @classmethod
    def get_module(cls, name: str) -> Optional[SchemaModule]:
        """获取指定模块"""
        cls._ensure_initialized()
        return cls._modules.get(name)
    
    @classmethod
    def get_modules(cls, names: List[str]) -> str:
        """
        获取多个模块的内容
        
        Args:
            names: 模块名称列表
        
        Returns:
            合并后的模块内容
        """
        cls._ensure_initialized()
        
        contents = []
        for name in names:
            module = cls._modules.get(name)
            if module:
                contents.append(module.content)
        
        return "\n\n---\n\n".join(contents)
    
    @classmethod
    def get_module_index(cls) -> str:
        """
        获取模块索引（名称和简介）
        
        用于 LLM 决定需要加载哪些模块。
        """
        cls._ensure_initialized()
        
        lines = ["# 可用的 Schema 模块", ""]
        for name, module in cls._modules.items():
            lines.append(f"- **{name}**: {module.description}")
        
        return "\n".join(lines)


class GetSchemaModuleInput(BaseModel):
    """get_schema_module 工具输入参数"""
    module_names: List[str] = Field(
        description="需要的模块列表"
    )


@tool
def get_schema_module(module_names: List[str]) -> str:
    """
    获取指定数据模型模块的详细填写规则
    
    在生成结构化输出之前调用此工具，只获取你需要的模块！
    这样可以减少 token 消耗，提高响应速度。
    
    Args:
        module_names: 需要的模块列表，可选值：
            - measures: 度量字段（销售额、利润等数值）
            - dimensions: 维度字段（分组、分类）
            - date_fields: 日期分组字段（按年、按月）
            - date_filters: 日期筛选条件（2024年、最近3个月）
            - filters: 非日期筛选条件（华东地区、销售额>1000）
            - topn: TopN 筛选（前10名、TOP5）
            - table_calcs: 表计算（累计、排名、占比）
    
    Returns:
        所选模块的详细填写规则
    
    Examples:
        获取度量和维度模块：
        >>> get_schema_module(["measures", "dimensions"])
        
        获取日期相关模块：
        >>> get_schema_module(["date_fields", "date_filters"])
        
        获取高级分析模块：
        >>> get_schema_module(["table_calcs", "topn"])
    """
    # 验证模块名称
    valid_modules = SchemaModuleRegistry.get_all_module_names()
    invalid_modules = [m for m in module_names if m not in valid_modules]
    
    if invalid_modules:
        return f"<error>无效的模块名称: {invalid_modules}。可用模块: {valid_modules}</error>"
    
    if not module_names:
        return f"<error>请指定至少一个模块。可用模块: {valid_modules}</error>"
    
    # 获取模块内容
    content = SchemaModuleRegistry.get_modules(module_names)
    
    logger.info(f"get_schema_module: loaded {len(module_names)} modules: {module_names}")
    
    return content


__all__ = [
    "get_schema_module",
    "SchemaModuleRegistry",
    "SchemaModule",
    "GetSchemaModuleInput",
]
