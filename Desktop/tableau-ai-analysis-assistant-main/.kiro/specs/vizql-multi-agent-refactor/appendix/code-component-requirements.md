# 代码组件详细规格

本文档包含6个纯代码组件的详细实现规格、算法说明和验收标准。

**6个代码组件**：
- 需求3：任务调度器
- 需求4：数据合并器
- 需求8：查询构建器
- 需求9：查询执行器
- 需求10：统计检测器
- 需求11：元数据管理器

---

## 需求3：任务调度器

### 详细功能说明

任务调度器负责管理重规划后的问题清单执行，协调查询构建器、执行器和统计检测器的工作流程。

#### 1. 任务接收

**接收重规划Agent生成的问题清单**：
- 解析自然语言问题列表
- 解析建议的维度、筛选条件、度量
- 管理任务执行顺序

#### 2. 流程调度

**直接调用任务规划Agent处理自然语言问题**：
- 重规划已生成完整问题，不再需要问题理解Agent
- 调用任务规划Agent将自然语言问题转换为QuerySpec
- 管理查询构建器→执行器→统计检测器的流程

#### 3. 并行处理

**支持多个查询的并行执行**：
- 最多并发数按环境变量`Parallel_Upper_Limit`执行（默认3）
- 使用ThreadPoolExecutor实现并发
- 管理查询依赖关系
- 收集所有查询结果

#### 2. 超时控制

**动态超时时间**：
- 基础超时：30秒
- 根据数据量调整：每10000行增加10秒
- 根据复杂度调整：Complex问题增加30秒
- 最大超时：120秒

**超时处理**：
- 超时后取消任务
- 记录超时日志
- 返回超时错误

#### 3. 失败处理

**智能重试**：
- 最多重试2次
- 指数退避：第1次重试等待2秒，第2次重试等待4秒
- 只对可重试的错误重试（网络错误、超时等）
- 不对不可重试的错误重试（认证失败、数据源不存在等）

**降级策略**：
- 使用缓存结果（如果有）
- 简化查询（减少维度或度量）
- 使用近似结果（采样数据）
- 部分结果（只返回成功的子任务）

**部分失败处理**：
- 部分任务失败不影响其他任务
- 记录失败原因
- 在最终报告中标注失败的任务

#### 4. 进度反馈

**SSE实时推送**：
- 任务开始：`{"type": "task_start", "task_id": "q1", "stage": 1}`
- 任务进度：`{"type": "task_progress", "task_id": "q1", "progress": 50}`
- 任务完成：`{"type": "task_complete", "task_id": "q1", "status": "success"}`
- 任务失败：`{"type": "task_error", "task_id": "q1", "error": "..."}`

**进度计算**：
- 总进度 = (已完成任务数 / 总任务数) × 100%
- 每个任务的进度：查询执行50%，结果分析50%

#### 5. 资源监控

**监控指标**：
- 内存使用率
- CPU使用率
- 数据库连接数
- 并发任务数

**资源限制**：
- 内存使用率 > 80% → 暂停新任务
- CPU使用率 > 90% → 降低并发数
- 数据库连接数 > 80% → 等待连接释放

### 实现示例

```python
class TaskScheduler:
    def __init__(self, parallel_limit: int = 3):
        self.parallel_limit = parallel_limit
        self.executor = ThreadPoolExecutor(max_workers=parallel_limit)

    def execute_all_stages(self, tasks: List[Dict]) -> List[Dict]:
        """按stage顺序执行所有任务"""
        all_stages = sorted(set(t.get("stage", 1) for t in tasks))
        all_results = []

        for stage in all_stages:
            stage_results = self._execute_stage(tasks, stage)
            all_results.extend(stage_results)

        return all_results

    def _execute_stage(self, tasks: List[Dict], stage: int) -> List[Dict]:
        """执行指定stage的所有任务（并行）"""
        stage_tasks = [t for t in tasks if t.get("stage") == stage]
        results = []

        # 提交所有任务
        future_to_task = {}
        for task in stage_tasks:
            future = self.executor.submit(self._execute_single_task, task)
            future_to_task[future] = task

        # 收集结果
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result(timeout=self._calculate_timeout(task))
                results.append(result)
            except Exception as e:
                results.append({
                    "task_id": task.get("question_id"),
                    "status": "error",
                    "error": str(e)
                })

        return results

    def _calculate_timeout(self, task: Dict) -> int:
        """计算动态超时时间"""
        base_timeout = 30
        complexity = task.get("complexity", "Simple")

        if complexity == "Complex":
            return min(base_timeout + 30, 120)
        elif complexity == "Medium":
            return min(base_timeout + 15, 120)
        else:
            return base_timeout
```

### 详细验收标准

#### 1. 并发执行正确性 100%

**测试方法**：
- 创建10个stage，每个stage包含3个任务
- 验证同stage内的任务是否并行执行
- 验证不同stage是否顺序执行
- 检查是否有竞态条件

**验收指标**：
- 同stage内的任务并行执行（通过时间戳验证）
- 不同stage顺序执行（stage 2在stage 1完成后才开始）
- 无竞态条件（无数据不一致）

#### 2. 超时控制准确率 >= 95%

**测试方法**：
- 模拟不同复杂度的任务
- 验证超时时间是否正确计算
- 验证超时后是否正确取消任务

**验收指标**：
- 超时时间计算准确率 >= 95%
- 超时后任务被正确取消
- 超时日志被正确记录

#### 3. 部分失败不影响整体流程

**测试方法**：
- 创建5个任务，其中2个任务故意失败
- 验证其他3个任务是否正常完成
- 验证最终报告是否包含失败信息

**验收指标**：
- 失败任务不影响其他任务
- 失败原因被正确记录
- 最终报告包含失败信息

#### 4. 进度反馈实时性 <= 1秒延迟

**测试方法**：
- 记录任务开始时间和进度推送时间
- 计算延迟时间

**验收指标**：
- 平均延迟 <= 0.5秒
- P95延迟 <= 1秒

---



---

## 需求4：数据合并器

### 详细功能说明

数据合并器负责智能合并多个子任务的查询结果，自动处理数据对齐、补全和计算。

#### 1. 合并策略

**按轮次决定是否合并**：
- **第0轮**：简单问题和复杂问题都不需要合并（只有1个查询）
- **第1轮及以后**：多个查询结果需要合并（按维度合并或并列展示）

#### 2. 合并策略选择

**基于代码规则选择合并策略**（不使用AI）：
- **Union** - 纵向合并（相同结构的数据）
  - IF 所有子任务的维度列表相同 → Union（上下拼接）
- **Join** - 横向合并（基于共同维度）
  - IF 子任务有公共维度且问题类型为"对比" → Join（横向连接）
  - IF 问题类型为"同比"或"环比" → Join（按维度连接不同时间段）
- **Append** - 简单追加
  - IF 子任务的时间范围不同且连续 → Append（追加）
- **Hierarchical** - 层级合并
  - IF 子任务的维度存在层级关系 → Hierarchical（层级合并）
- **默认策略** - Union

#### 3. 字段命名规则（纯代码逻辑）

**同比/环比命名**：
- 使用"当期_销售额"、"上期_销售额"等命名

**多时间段对比命名**：
- 使用"2016年_销售额"、"2015年_销售额"等命名

**公共维度识别**：
- 直接匹配字段名称，不需要AI

#### 4. 数据对齐与补全

**处理数据不一致**：
- 时间序列补点（填充缺失的时间点）
- 维度组合补全（填充缺失的维度组合）
- 空值处理（填0或保留null）

#### 5. 数据去重与清洗

**确保数据质量**：
- 检测重复记录
- 异常值处理
- 空值处理

#### 6. 聚合计算

**计算派生指标**：
- 总计、小计
- 平均值、占比
- 排名、累计

#### 7. 数据质量评分

**评估合并后的数据质量**：
- 完整性（缺失值占比）
- 一致性（重复值占比）
- 准确性（异常值占比）
- 时效性（数据更新时间）

### 详细验收标准

1. 合并策略选择准确率 >= 95%
2. 数据对齐准确率 100%
3. 数据质量评分准确率 >= 90%
4. 合并耗时 <= 1秒（1000行以内）

---

## 需求8：查询构建器

### 详细功能说明

查询构建器负责根据语义级别的StructuredQuestionSpec生成技术级别的VizQL查询JSON，**使用纯代码规则而非AI**，确保查询100%正确。

#### 核心原则

**为什么使用代码而非AI？**
1. **精确性要求** - VizQL查询JSON必须100%符合VDS规范，任何错误都会导致查询失败
2. **类型定义完整** - tableau_sdk提供了完整的类型定义和Zod schema，可以直接参考
3. **可维护性** - 代码规则易于测试、调试和维护，AI生成的查询难以保证一致性
4. **性能考虑** - 代码生成查询的速度远快于AI（<0.1秒 vs 1-2秒）
5. **成本考虑** - 避免不必要的LLM调用，降低成本

#### 1. 查询生成

**从语义Spec到技术JSON**：

**输入**（语义级别，由查询规划Agent生成）：
```json
{
  "dims": ["地区"],
  "metrics": [{"field": "销售额", "aggregation": "sum"}],
  "filters": [{"field": "订单日期", "type": "year", "value": 2016}],
  "sort_by": {"field": "销售额", "direction": "desc"},
  "limit": null,
  "grain": null
}
```

**输出**（技术级别，符合VDS规范）：
```json
{
  "datasource": {
    "datasourceLuid": "abc123..."
  },
  "query": {
    "fields": [
      {
        "fieldCaption": "地区"
      },
      {
        "fieldCaption": "销售额",
        "function": "SUM",
        "sortDirection": "DESC",
        "sortPriority": 1
      }
    ],
    "filters": [
      {
        "field": {"fieldCaption": "订单日期"},
        "filterType": "QUANTITATIVE_DATE",
        "quantitativeFilterType": "RANGE",
        "minDate": "2016-01-01",
        "maxDate": "2016-12-31"
      }
    ]
  },
  "options": {
    "returnFormat": "OBJECTS"
  }
}
```

#### 2. tableau_sdk的关键作用

**tableau_sdk位置**：`sdks/tableau/apis/vizqlDataServiceApi.ts`

**提供的类型定义**（TypeScript + Zod schema）：

1. **Field类型**：
```typescript
// 基础字段
const FieldBase = z.object({
  fieldCaption: z.string(),
  fieldAlias: z.string().optional(),
  maxDecimalPlaces: z.number().int().optional(),
  sortDirection: SortDirection.optional(),
  sortPriority: z.number().int().optional(),
});

// 三种Field类型（Union）
export const Field = z.union([
  FieldBase.strict(),  // 基础字段
  FieldBase.extend({ function: Function }).strict(),  // 函数字段
  FieldBase.extend({ calculation: z.string() }).strict(),  // 计算字段
]);
```

2. **Function枚举**：
```typescript
export const Function = z.enum([
  'SUM', 'AVG', 'MEDIAN', 'COUNT', 'COUNTD', 'MIN', 'MAX', 'STDEV', 'VAR', 'COLLECT',
  'YEAR', 'QUARTER', 'MONTH', 'WEEK', 'DAY',
  'TRUNC_YEAR', 'TRUNC_QUARTER', 'TRUNC_MONTH', 'TRUNC_WEEK', 'TRUNC_DAY',
  'AGG', 'NONE', 'UNSPECIFIED',
]);
```

3. **Filter类型**（6种）：
```typescript
// SetFilter - 集合筛选
export const SetFilter = SimpleFilterBase.extend({
  filterType: z.literal('SET'),
  values: z.union([z.array(z.string()), z.array(z.number()), z.array(z.boolean())]),
  exclude: z.boolean().optional(),
});

// TopNFilter - TopN筛选
export const TopNFilter = FilterBase.extend({
  filterType: z.literal('TOP'),
  howMany: z.number().int(),
  fieldToMeasure: FilterField,
  direction: z.enum(['TOP', 'BOTTOM']).optional().default('TOP'),
});

// MatchFilter - 文本匹配
export const MatchFilter = z.union([
  MatchFilterBase.extend({ startsWith: z.string() }).strict(),
  MatchFilterBase.extend({ endsWith: z.string() }).strict(),
  MatchFilterBase.extend({ contains: z.string() }).strict(),
]);

// QuantitativeNumericalFilter - 数值范围
// QuantitativeDateFilter - 日期范围
// RelativeDateFilter - 相对日期
```

4. **Query结构**：
```typescript
export const Query = z.strictObject({
  fields: z.array(Field),
  filters: z.array(Filter).optional(),
});

export const QueryRequest = z.object({
  datasource: Datasource,
  query: Query,
  options: QueryDatasourceOptions.optional(),
}).passthrough();
```

#### 3. Python实现方式

**创建对应的Pydantic模型**（严格对应tableau_sdk的TypeScript类型）：

```python
from pydantic import BaseModel, Field as PydanticField
from typing import Literal, Union, Optional, List
from enum import Enum

# 1. Function枚举（对应tableau_sdk的Function）
class FunctionEnum(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    MEDIAN = "MEDIAN"
    COUNT = "COUNT"
    COUNTD = "COUNTD"
    MIN = "MIN"
    MAX = "MAX"
    STDEV = "STDEV"
    VAR = "VAR"
    COLLECT = "COLLECT"
    YEAR = "YEAR"
    QUARTER = "QUARTER"
    MONTH = "MONTH"
    WEEK = "WEEK"
    DAY = "DAY"
    TRUNC_YEAR = "TRUNC_YEAR"
    TRUNC_QUARTER = "TRUNC_QUARTER"
    TRUNC_MONTH = "TRUNC_MONTH"
    TRUNC_WEEK = "TRUNC_WEEK"
    TRUNC_DAY = "TRUNC_DAY"
    AGG = "AGG"
    NONE = "NONE"
    UNSPECIFIED = "UNSPECIFIED"

# 2. SortDirection枚举
class SortDirection(str, Enum):
    ASC = "ASC"
    DESC = "DESC"

# 3. Field类型（对应tableau_sdk的Field）
class FieldBase(BaseModel):
    fieldCaption: str
    fieldAlias: Optional[str] = None
    maxDecimalPlaces: Optional[int] = None
    sortDirection: Optional[SortDirection] = None
    sortPriority: Optional[int] = None

class BasicField(FieldBase):
    """基础字段（维度）"""
    pass

class FunctionField(FieldBase):
    """函数字段（度量）"""
    function: FunctionEnum

class CalculationField(FieldBase):
    """计算字段"""
    calculation: str

# Union类型（对应TypeScript的union）
VizQLField = Union[BasicField, FunctionField, CalculationField]

# 4. Filter类型（对应tableau_sdk的Filter）
class FilterField(BaseModel):
    fieldCaption: str

class SetFilter(BaseModel):
    field: FilterField
    filterType: Literal["SET"]
    values: Union[List[str], List[int], List[bool]]
    exclude: Optional[bool] = False
    context: Optional[bool] = None

class TopNFilter(BaseModel):
    field: FilterField
    filterType: Literal["TOP"]
    howMany: int
    fieldToMeasure: FilterField
    direction: Literal["TOP", "BOTTOM"] = "TOP"
    context: Optional[bool] = None

class QuantitativeDateFilter(BaseModel):
    field: FilterField
    filterType: Literal["QUANTITATIVE_DATE"]
    quantitativeFilterType: Literal["RANGE", "MIN", "MAX"]
    minDate: Optional[str] = None
    maxDate: Optional[str] = None
    includeNulls: Optional[bool] = None
    context: Optional[bool] = None

# ... 其他Filter类型

VizQLFilter = Union[SetFilter, TopNFilter, QuantitativeDateFilter, ...]

# 5. Query结构（对应tableau_sdk的Query）
class VizQLQuery(BaseModel):
    fields: List[VizQLField]
    filters: Optional[List[VizQLFilter]] = None

class Datasource(BaseModel):
    datasourceLuid: str

class QueryRequest(BaseModel):
    datasource: Datasource
    query: VizQLQuery
    options: Optional[dict] = None
```

**使用Builder模式生成查询**：

```python
class QueryBuilder:
    """查询构建器基类"""
    
    def __init__(self, datasource_luid: str):
        self.datasource_luid = datasource_luid
        self.fields: List[VizQLField] = []
        self.filters: List[VizQLFilter] = []
        self.sort_priority_counter = 1
    
    def add_dimension(self, field_caption: str) -> 'QueryBuilder':
        """添加维度字段"""
        field = BasicField(fieldCaption=field_caption)
        self.fields.append(field)
        return self
    
    def add_metric(
        self, 
        field_caption: str, 
        function: str,
        sort_direction: Optional[str] = None
    ) -> 'QueryBuilder':
        """添加度量字段"""
        field = FunctionField(
            fieldCaption=field_caption,
            function=FunctionEnum(function.upper()),
            sortDirection=SortDirection(sort_direction.upper()) if sort_direction else None,
            sortPriority=self.sort_priority_counter if sort_direction else None
        )
        if sort_direction:
            self.sort_priority_counter += 1
        self.fields.append(field)
        return self
    
    def add_date_range_filter(
        self,
        field_caption: str,
        min_date: str,
        max_date: str
    ) -> 'QueryBuilder':
        """添加日期范围筛选"""
        filter = QuantitativeDateFilter(
            field=FilterField(fieldCaption=field_caption),
            filterType="QUANTITATIVE_DATE",
            quantitativeFilterType="RANGE",
            minDate=min_date,
            maxDate=max_date
        )
        self.filters.append(filter)
        return self
    
    def build(self) -> QueryRequest:
        """构建最终的查询请求"""
        query = VizQLQuery(
            fields=self.fields,
            filters=self.filters if self.filters else None
        )
        return QueryRequest(
            datasource=Datasource(datasourceLuid=self.datasource_luid),
            query=query,
            options={"returnFormat": "OBJECTS"}
        )
```

**使用示例**：

```python
# 从语义Spec生成VizQL查询
spec = {
    "dims": ["地区"],
    "metrics": [{"field": "销售额", "aggregation": "sum"}],
    "filters": [{"field": "订单日期", "type": "year", "value": 2016}],
    "sort_by": {"field": "销售额", "direction": "desc"}
}

# 使用Builder生成查询
builder = QueryBuilder(datasource_luid="abc123...")
builder.add_dimension("地区")
builder.add_metric("销售额", "sum", sort_direction="desc")
builder.add_date_range_filter("订单日期", "2016-01-01", "2016-12-31")

# 构建查询请求
query_request = builder.build()

# 转换为JSON
query_json = query_request.model_dump_json()
```

#### 4. 日期值计算与日期字段处理

**代码逻辑计算具体日期**（不使用AI）：

```python
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from calendar import monthrange
import os
from typing import Optional, Dict, List, Tuple
import re

class DateProcessingConfig:
    """日期处理配置（从.env加载）"""
    
    def __init__(self):
        # 周开始日（0=周一，6=周日）
        self.WEEK_START_DAY = int(os.getenv('WEEK_START_DAY', '0'))
        
        # SetFilter阈值
        self.SET_FILTER_THRESHOLD = int(os.getenv('SET_FILTER_THRESHOLD', '50'))
    
    def get_week_start_day(self, date_features: Dict) -> int:
        """获取周开始日（问题理解结果优先）"""
        if date_features.get("week_start_day_mentioned"):
            return date_features["week_start_day"]
        return self.WEEK_START_DAY

# 全局配置实例
date_config = DateProcessingConfig()

class DateCalculator:
    """日期计算器"""
    
    def __init__(self, config: DateProcessingConfig = date_config):
        self.config = config
    
    def calculate_relative_date(
        self,
        period_type: str,  # "month", "quarter", "year"
        offset: int,  # -3表示最近3个月
        anchor_date: Optional[datetime] = None
    ) -> Tuple[str, str]:
        """计算相对日期范围"""
        if anchor_date is None:
            anchor_date = datetime.now()
        
        if period_type == "month":
            start_date = anchor_date + relativedelta(months=offset)
            end_date = anchor_date
        elif period_type == "quarter":
            start_date = anchor_date + relativedelta(months=offset*3)
            end_date = anchor_date
        elif period_type == "year":
            start_date = anchor_date + relativedelta(years=offset)
            end_date = anchor_date
        
        return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
    
    def calculate_yoy_date(self, current_date: str) -> str:
        """计算同比日期（去年同期）"""
        dt = datetime.strptime(current_date, "%Y-%m-%d")
        yoy_date = dt - relativedelta(years=1)
        return yoy_date.strftime("%Y-%m-%d")
    
    def calculate_mom_date(self, current_date: str) -> str:
        """计算环比日期（上期）"""
        dt = datetime.strptime(current_date, "%Y-%m-%d")
        mom_date = dt - relativedelta(months=1)
        return mom_date.strftime("%Y-%m-%d")
    
    def calculate_week_range(
        self,
        anchor_date: datetime,
        date_features: Dict
    ) -> Tuple[datetime, datetime]:
        """计算周范围（支持周开始日配置）"""
        week_start_day = self.config.get_week_start_day(date_features)
        
        # 计算当前是周几（0=周一，6=周日）
        current_weekday = anchor_date.weekday()
        
        # 计算到周开始的偏移
        days_since_week_start = (current_weekday - week_start_day) % 7
        
        # 周开始日期
        week_start = anchor_date - timedelta(days=days_since_week_start)
        
        # 周结束日期（周开始+6天）
        week_end = week_start + timedelta(days=6)
        
        return week_start, week_end
    
    def is_period_complete(self, anchor_date: datetime, period_type: str) -> bool:
        """判断当前周期是否完整"""
        if period_type == "DAYS":
            return True
        
        elif period_type == "WEEKS":
            return anchor_date.weekday() == 6  # 周日
        
        elif period_type == "MONTHS":
            last_day = monthrange(anchor_date.year, anchor_date.month)[1]
            return anchor_date.day == last_day
        
        elif period_type == "QUARTERS":
            if anchor_date.month not in (3, 6, 9, 12):
                return False
            last_day = monthrange(anchor_date.year, anchor_date.month)[1]
            return anchor_date.day == last_day
        
        elif period_type == "YEARS":
            return anchor_date.month == 12 and anchor_date.day == 31
        
        return False
    
    def calculate_previous_period(
        self,
        anchor_date: datetime,
        period_type: str,
        align_incomplete: bool = True
    ) -> Dict:
        """计算上期日期范围（支持周期对齐）"""
        is_complete = self.is_period_complete(anchor_date, period_type)
        
        if period_type == "MONTHS":
            # 当前月
            current_start = anchor_date.replace(day=1)
            current_end = anchor_date if not is_complete else datetime(
                anchor_date.year, anchor_date.month,
                monthrange(anchor_date.year, anchor_date.month)[1]
            )
            
            # 上月
            if anchor_date.month == 1:
                prev_start = anchor_date.replace(year=anchor_date.year - 1, month=12, day=1)
            else:
                prev_start = anchor_date.replace(month=anchor_date.month - 1, day=1)
            
            if align_incomplete and not is_complete:
                # 对齐：上月也取相同天数
                days_in_current = (current_end - current_start).days + 1
                prev_end = prev_start + timedelta(days=days_in_current - 1)
            else:
                # 不对齐：上月取完整月
                prev_end = datetime(
                    prev_start.year, prev_start.month,
                    monthrange(prev_start.year, prev_start.month)[1]
                )
            
            return {
                "current": {
                    "start": current_start.strftime("%Y-%m-%d"),
                    "end": current_end.strftime("%Y-%m-%d"),
                    "is_complete": is_complete
                },
                "previous": {
                    "start": prev_start.strftime("%Y-%m-%d"),
                    "end": prev_end.strftime("%Y-%m-%d"),
                    "is_complete": True
                },
                "aligned": align_incomplete and not is_complete
            }
        
        # 其他周期类型的实现...
        return {}

class DateFieldAnalyzer:
    """日期字段分析器"""
    
    # Tableau DATEPARSE格式 -> Python strftime格式
    DATEPARSE_TO_PYTHON = {
        'yyyy-MM-dd': '%Y-%m-%d',
        'yyyy/MM/dd': '%Y/%m/%d',
        'yyyyMMdd': '%Y%m%d',
        'dd/MM/yyyy': '%d/%m/%Y',
        'MM/dd/yyyy': '%m/%d/%Y',
        'yyyy-MM-dd HH:mm:ss': '%Y-%m-%d %H:%M:%S',
        'yyyy-MM': '%Y-%m',
        'yyyy': '%Y',
    }
    
    def __init__(self, config: DateProcessingConfig = date_config):
        self.config = config
    
    def detect_date_format(self, sample_values: List[str]) -> Optional[str]:
        """检测日期格式"""
        if not sample_values:
            return None
        
        # 取前10个样本值
        samples = sample_values[:10]
        
        # 定义格式模式
        patterns = [
            (r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', 'yyyy-MM-dd HH:mm:ss'),
            (r'^\d{4}-\d{2}-\d{2}$', 'yyyy-MM-dd'),
            (r'^\d{4}/\d{2}/\d{2}$', 'yyyy/MM/dd'),
            (r'^\d{8}$', 'yyyyMMdd'),
            (r'^\d{2}/\d{2}/\d{4}$', None),  # 需要进一步判断
            (r'^\d{4}-\d{2}$', 'yyyy-MM'),
            (r'^\d{4}$', 'yyyy'),
        ]
        
        for pattern, format_str in patterns:
            if all(re.match(pattern, str(v)) for v in samples if v):
                if format_str is None:
                    # dd/MM/yyyy vs MM/dd/yyyy
                    return self._detect_dmy_or_mdy(samples)
                return format_str
        
        return None
    
    def _detect_dmy_or_mdy(self, samples: List[str]) -> str:
        """区分dd/MM/yyyy和MM/dd/yyyy格式"""
        for sample in samples:
            parts = sample.split('/')
            if len(parts) == 3:
                first, second, _ = parts
                first_num = int(first)
                second_num = int(second)
                
                if first_num > 12:
                    return 'dd/MM/yyyy'
                if second_num > 12:
                    return 'MM/dd/yyyy'
        
        return 'MM/dd/yyyy'  # 默认美国格式
    
    def get_date_field_strategy(
        self,
        field_meta: Dict,
        filter_spec: Dict
    ) -> Dict:
        """根据字段类型和筛选需求决定策略"""
        data_type = field_meta["dataType"]
        filter_type = filter_spec.get("filter_type", "absolute")
        
        # DATE/DATETIME类型：直接使用QuantitativeDateFilter
        if data_type in ("DATE", "DATETIME"):
            return {
                "strategy": "quantitative_date",
                "needs_dateparse": False,
                "date_format": None
            }
        
        # STRING类型：需要进一步判断
        if data_type == "STRING":
            return self._analyze_string_date_field(field_meta, filter_spec)
        
        raise ValueError(f"不支持的数据类型: {data_type}")
    
    def _analyze_string_date_field(
        self,
        field_meta: Dict,
        filter_spec: Dict
    ) -> Dict:
        """分析STRING类型日期字段的处理策略"""
        # 步骤1：检测日期格式
        date_format = self.detect_date_format(field_meta.get("sampleValues", []))
        
        if date_format is None:
            raise ValueError(
                f"无法识别字段 {field_meta['fieldCaption']} 的日期格式。"
                f"样本值: {field_meta.get('sampleValues', [])[:5]}"
            )
        
        # 步骤2：根据筛选类型决定策略
        filter_type = filter_spec.get("filter_type", "absolute")
        unique_count = field_meta.get("uniqueCount", 0)
        
        if filter_type == "absolute" and unique_count < self.config.SET_FILTER_THRESHOLD:
            # 绝对时间 + 低基数：使用SetFilter
            return {
                "strategy": "set",
                "needs_dateparse": False,
                "date_format": date_format,
                "reason": f"低基数绝对时间（uniqueCount={unique_count}），使用SetFilter更高效"
            }
        else:
            # 相对时间 或 高基数：使用DATEPARSE + QuantitativeDateFilter
            return {
                "strategy": "quantitative_date",
                "needs_dateparse": True,
                "date_format": date_format,
                "reason": f"相对时间或高基数（uniqueCount={unique_count}），需要DATEPARSE转换"
            }
    
    def format_date_for_filter(
        self,
        date: datetime,
        date_format: str,
        field_data_type: str
    ) -> str:
        """根据字段类型和格式格式化日期"""
        if field_data_type == "DATETIME":
            return date.strftime('%Y-%m-%dT%H:%M:%S')
        
        elif field_data_type == "DATE":
            return date.strftime('%Y-%m-%d')
        
        elif field_data_type == "STRING":
            python_format = self.DATEPARSE_TO_PYTHON.get(date_format, '%Y-%m-%d')
            return date.strftime(python_format)
        
        return date.strftime('%Y-%m-%d')
    
    def generate_dateparse_calculation(
        self,
        field_caption: str,
        date_format: str
    ) -> Dict:
        """生成DATEPARSE计算字段定义"""
        calc_name = f"[{field_caption}"
        calc_formula = f"DATEPARSE('{date_format}', [{field_caption}])"
        
        return {
            "name": calc_name,
            "formula": calc_formula,
            "data_type": "DATE"
        }

class HolidayManager:
    """节假日管理器"""
    
    def __init__(self):
        self.holidays = self._load_holidays()
    
    def _load_holidays(self) -> Dict[str, str]:
        """加载节假日数据"""
        # 2024年中国法定节假日
        return {
            '2024-01-01': '元旦',
            '2024-02-10': '春节', '2024-02-11': '春节', '2024-02-12': '春节',
            '2024-02-13': '春节', '2024-02-14': '春节', '2024-02-15': '春节',
            '2024-02-16': '春节', '2024-02-17': '春节',
            '2024-04-04': '清明节', '2024-04-05': '清明节', '2024-04-06': '清明节',
            '2024-05-01': '劳动节', '2024-05-02': '劳动节', '2024-05-03': '劳动节',
            '2024-05-04': '劳动节', '2024-05-05': '劳动节',
            '2024-06-10': '端午节',
            '2024-09-15': '中秋节', '2024-09-16': '中秋节', '2024-09-17': '中秋节',
            '2024-10-01': '国庆节', '2024-10-02': '国庆节', '2024-10-03': '国庆节',
            '2024-10-04': '国庆节', '2024-10-05': '国庆节', '2024-10-06': '国庆节',
            '2024-10-07': '国庆节',
        }
    
    def is_holiday(self, date: datetime) -> bool:
        """判断是否是节假日"""
        date_str = date.strftime('%Y-%m-%d')
        return date_str in self.holidays
    
    def get_holiday_name(self, date: datetime) -> Optional[str]:
        """获取节假日名称"""
        date_str = date.strftime('%Y-%m-%d')
        return self.holidays.get(date_str)

# 全局节假日管理器
holiday_manager = HolidayManager()

class WorkingDayCalculator:
    """工作日计算器"""
    
    def __init__(
        self,
        config: DateProcessingConfig = date_config,
        holiday_mgr: HolidayManager = holiday_manager
    ):
        self.config = config
        self.holiday_mgr = holiday_mgr
    
    def is_working_day(
        self,
        date: datetime,
        date_features: Dict
    ) -> bool:
        """判断是否是工作日"""
        week_start_day = self.config.get_week_start_day(date_features)
        
        # 计算周末
        weekday = date.weekday()
        if week_start_day == 0:  # 周一开始
            is_weekend = weekday >= 5  # 周六、周日
        else:  # 周日开始
            is_weekend = weekday == 5  # 只有周六
        
        if is_weekend:
            return False
        
        # 考虑法定节假日（如果问题涉及）
        if date_features.get("consider_holidays", False):
            if self.holiday_mgr.is_holiday(date):
                return False
        
        return True
    
    def calculate_working_days(
        self,
        start_date: datetime,
        end_date: datetime,
        date_features: Dict
    ) -> int:
        """计算工作日天数"""
        count = 0
        current = start_date
        
        while current <= end_date:
            if self.is_working_day(current, date_features):
                count += 1
            current += timedelta(days=1)
        
        return count
    
    def filter_working_days(
        self,
        start_date: datetime,
        end_date: datetime,
        date_features: Dict
    ) -> List[str]:
        """获取工作日列表（用于SetFilter）"""
        working_days = []
        current = start_date
        
        while current <= end_date:
            if self.is_working_day(current, date_features):
                working_days.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        return working_days

class LunarCalendarManager:
    """农历管理器"""
    
    def __init__(self):
        try:
            from lunarcalendar import Converter, Solar, Lunar
            self.Converter = Converter
            self.Solar = Solar
            self.Lunar = Lunar
            self.available = True
        except ImportError:
            self.available = False
    
    def solar_to_lunar(self, date: datetime) -> Optional[str]:
        """阳历转农历"""
        if not self.available:
            return None
        
        solar = self.Solar(date.year, date.month, date.day)
        lunar = self.Converter.Solar2Lunar(solar)
        
        return f"{lunar.year}年{lunar.month}月{lunar.day}日"
    
    def lunar_to_solar(
        self,
        year: int,
        month: int,
        day: int,
        leap: bool = False
    ) -> Optional[datetime]:
        """农历转阳历"""
        if not self.available:
            return None
        
        lunar = self.Lunar(year, month, day, leap)
        solar = self.Converter.Lunar2Solar(lunar)
        
        return datetime(solar.year, solar.month, solar.day)
    
    def get_lunar_festivals(self, year: int) -> Dict[str, str]:
        """获取农历节日（转换为阳历日期）"""
        if not self.available:
            return {}
        
        festivals = {
            (year, 1, 1): "春节",
            (year, 1, 15): "元宵节",
            (year, 5, 5): "端午节",
            (year, 8, 15): "中秋节",
        }
        
        solar_festivals = {}
        for (lunar_year, lunar_month, lunar_day), name in festivals.items():
            solar_date = self.lunar_to_solar(lunar_year, lunar_month, lunar_day)
            if solar_date:
                solar_festivals[solar_date.strftime('%Y-%m-%d')] = name
        
        return solar_festivals
    
    def handle_lunar_question(
        self,
        question: str,
        date_features: Dict,
        anchor_date: datetime
    ) -> Optional[Dict]:
        """处理农历相关问题"""
        if not date_features.get("support_lunar", False):
            return None
        
        if not self.available:
            raise ValueError(
                "农历功能需要安装lunarcalendar库: pip install lunarcalendar"
            )
        
        # 示例：识别春节期间
        if "春节" in date_features.get("lunar_keywords", []):
            festivals = self.get_lunar_festivals(anchor_date.year)
            spring_festival_date = None
            
            for date_str, name in festivals.items():
                if name == "春节":
                    spring_festival_date = datetime.fromisoformat(date_str)
                    break
            
            if spring_festival_date:
                # 春节期间：春节前后3天
                start_date = spring_festival_date - timedelta(days=3)
                end_date = spring_festival_date + timedelta(days=3)
                
                return {
                    "start_date": start_date.strftime('%Y-%m-%d'),
                    "end_date": end_date.strftime('%Y-%m-%d'),
                    "festival_name": "春节",
                    "festival_date": spring_festival_date.strftime('%Y-%m-%d')
                }
        
        return None

# 全局农历管理器
lunar_manager = LunarCalendarManager()
```

#### 5. 查询验证

**基于Pydantic模型验证**（对应tableau_sdk的Zod schema）：

```python
from pydantic import ValidationError

def validate_query(query_request: QueryRequest) -> tuple[bool, Optional[str]]:
    """验证查询结构"""
    try:
        # Pydantic自动验证
        query_request.model_validate(query_request.model_dump())
        
        # 额外的业务规则验证
        fields = query_request.query.fields
        
        # 1. 至少包含一个field
        if len(fields) == 0:
            return False, "The query must include at least one field"
        
        # 2. fieldCaption不能为空
        for field in fields:
            if not field.fieldCaption:
                return False, "The query must not include any fields with an empty fieldCaption"
        
        # 3. sortPriority不能重复
        sort_priorities = [f.sortPriority for f in fields if f.sortPriority is not None]
        if len(sort_priorities) != len(set(sort_priorities)):
            return False, "The query must not include duplicate sort priorities"
        
        # 4. function和calculation互斥
        for field in fields:
            if isinstance(field, FunctionField) and hasattr(field, 'calculation'):
                return False, "The query must not include fields that contain both a function and a calculation"
        
        return True, None
    
    except ValidationError as e:
        return False, str(e)
```

#### 6. Builder模式

**不同类型的查询使用不同的Builder**：

```python
class BasicQueryBuilder(QueryBuilder):
    """基础查询构建器"""
    pass

class TimeSeriesQueryBuilder(QueryBuilder):
    """时间序列查询构建器"""
    
    def add_time_dimension(self, field_caption: str, grain: str):
        """添加时间维度（带粒度）"""
        # grain: "year", "quarter", "month", "week", "day"
        function_map = {
            "year": FunctionEnum.YEAR,
            "quarter": FunctionEnum.QUARTER,
            "month": FunctionEnum.MONTH,
            "week": FunctionEnum.WEEK,
            "day": FunctionEnum.DAY
        }
        field = FunctionField(
            fieldCaption=field_caption,
            function=function_map[grain]
        )
        self.fields.append(field)
        return self

class RankingQueryBuilder(QueryBuilder):
    """排名查询构建器"""
    
    def add_topn_filter(
        self,
        dimension_field: str,
        metric_field: str,
        metric_function: str,
        top_n: int,
        direction: str = "TOP"
    ):
        """添加TopN筛选"""
        filter = TopNFilter(
            field=FilterField(fieldCaption=dimension_field),
            filterType="TOP",
            howMany=top_n,
            fieldToMeasure=FilterField(fieldCaption=metric_field),
            direction=direction
        )
        self.filters.append(filter)
        return self

class ComparisonQueryBuilder(QueryBuilder):
    """对比查询构建器（同比/环比）"""
    
    def build_comparison_queries(
        self,
        current_period: tuple[str, str],
        previous_period: tuple[str, str]
    ) -> tuple[QueryRequest, QueryRequest]:
        """构建对比查询（当期 vs 上期）"""
        # 当期查询
        current_builder = QueryBuilder(self.datasource_luid)
        for field in self.fields:
            current_builder.fields.append(field)
        current_builder.add_date_range_filter(
            "订单日期",
            current_period[0],
            current_period[1]
        )
        
        # 上期查询
        previous_builder = QueryBuilder(self.datasource_luid)
        for field in self.fields:
            previous_builder.fields.append(field)
        previous_builder.add_date_range_filter(
            "订单日期",
            previous_period[0],
            previous_period[1]
        )
        
        return current_builder.build(), previous_builder.build()
```

### 详细验收标准

#### 1. 查询生成准确率 100%（纯代码规则，不使用AI）

**测试方法**：
- 准备100个不同类型的查询Spec
- 验证生成的VizQL查询JSON是否正确
- 使用Pydantic模型验证查询结构

**验收指标**：
- 所有查询都能成功生成
- 所有查询都能通过Pydantic验证
- 所有查询都能被VDS API接受

#### 2. 日期计算准确率 100%（纯代码逻辑）

**测试方法**：
- 测试相对日期计算（最近3个月、上个季度等）
- 测试同比/环比日期计算
- 测试周范围计算（周一开始 vs 周日开始）
- 测试周期完整性判断
- 测试上期对齐计算

**验收指标**：
- 相对日期计算准确率 100%
- 同比/环比日期计算准确率 100%
- 周范围计算准确率 100%（支持两种周开始日）
- 周期完整性判断准确率 100%
- 上期对齐计算准确率 100%

#### 3. 日期字段类型识别准确率 >= 95%

**测试方法**：
- 准备50个不同类型的日期字段（DATE、DATETIME、STRING）
- 测试日期格式检测（8种常见格式）
- 测试策略选择（QuantitativeDateFilter vs SetFilter）

**验收指标**：
- DATE/DATETIME类型识别准确率 100%
- STRING类型日期格式检测准确率 >= 95%
- 策略选择准确率 100%（基于规则）

#### 4. 周开始日配置优先级正确

**测试方法**：
- 测试问题指定周开始日（最高优先级）
- 测试环境配置周开始日
- 测试默认值（周一）

**验收指标**：
- 问题指定优先级 > 环境配置 > 默认值
- 周范围计算正确应用周开始日配置

#### 5. 节假日处理准确率 >= 95%

**测试方法**：
- 测试工作日判断（周末 + 法定节假日）
- 测试工作日天数计算
- 测试工作日列表生成（用于SetFilter）

**验收指标**：
- 周末判断准确率 100%
- 法定节假日判断准确率 100%（基于节假日字典）
- 工作日天数计算准确率 100%
- 工作日列表生成准确率 100%

#### 6. 农历支持功能完整

**测试方法**：
- 测试阳历转农历
- 测试农历转阳历
- 测试农历节日识别
- 测试春节期间日期范围计算

**验收指标**：
- lunarcalendar库可用时，所有功能正常工作
- lunarcalendar库不可用时，抛出清晰的错误提示
- 农历节日识别准确率 100%（春节、中秋、端午、清明）

#### 7. DATEPARSE计算字段生成正确

**测试方法**：
- 测试不同日期格式的DATEPARSE生成
- 验证计算字段名称唯一性
- 验证计算字段公式正确性

**验收指标**：
- DATEPARSE公式格式正确率 100%
- 计算字段名称无冲突
- 生成的计算字段能被VDS API接受

#### 8. 类型定义100%对应tableau_sdk的TypeScript类型

**验收指标**：
- 所有Function枚举值与tableau_sdk一致
- 所有Filter类型与tableau_sdk一致
- 所有Field类型与tableau_sdk一致
- 查询JSON结构与VDS规范100%一致

#### 9. 查询验证覆盖率 >= 95%（基于Pydantic模型验证）

**验收指标**：
- Pydantic模型能捕获所有类型错误
- 业务规则验证覆盖主要场景
- 错误消息清晰易懂

#### 10. 生成耗时 <= 0.1秒

**验收指标**：
- 单个查询生成耗时 <= 0.1秒
- 批量查询生成（10个）耗时 <= 1秒

#### 11. 环境配置加载正确

**测试方法**：
- 测试.env文件加载
- 测试配置默认值
- 测试配置优先级

**验收指标**：
- 所有配置项都能从.env加载
- 配置默认值正确
- 配置优先级正确（问题指定 > 环境配置 > 默认值）

---

## 需求9：查询执行器

### 详细功能说明

查询执行器负责调用Tableau VDS API执行查询，处理分页和错误，确保查询稳定可靠。

#### 1. 查询执行

**调用Tableau VDS API**：
- 发送VizQL查询JSON
- 接收查询结果
- 解析响应数据

#### 2. 分页处理

**自动获取所有页**：
- VDS每页最多返回10000行
- 自动检测是否有下一页
- 循环获取所有页

#### 3. 错误处理

**智能重试和超时控制**：
- 重试机制（指数退避）
- 超时控制（30-120秒）
- 错误分类（可重试 vs 不可重试）

#### 4. 结果解析

**解析VDS响应**：
- 转换为DataFrame
- 处理数据类型
- 处理空值

### 详细验收标准

1. 查询成功率 >= 99%
2. 分页处理准确率 100%
3. 错误恢复成功率 >= 90%
4. 查询耗时 <= 10秒（取决于数据量）

---

## 需求10：统计检测器

### 详细功能说明

统计检测器负责对查询结果进行客观的统计分析，检测异常值和趋势，为AI提供分析依据。

#### 1. 描述性统计

**计算基础统计指标**：
- 均值、中位数
- 标准差、方差
- 分位数（25%、50%、75%）
- 最大值、最小值

#### 2. 异常检测

**使用统计方法检测异常**：
- Z-score方法（|z| > 3为异常）
- IQR方法（Q1-1.5*IQR 或 Q3+1.5*IQR）
- MAD方法（中位数绝对偏差）
- 孤立森林（Isolation Forest）

#### 3. 趋势分析

**分析时间序列趋势**：
- 线性回归（slope、p_value）
- Mann-Kendall检验
- 趋势方向（上升/下降/平稳）

#### 4. 数据质量检查

**评估数据质量**：
- 完整性（缺失值占比）
- 一致性（重复值占比）
- 准确性（异常值占比）

### 详细验收标准

1. 统计计算准确率 100%
2. 异常检测准确率 >= 85%
3. 趋势分析准确率 >= 90%
4. 计算耗时 <= 0.5秒（1000行以内）

---

## 需求11：元数据管理器

### 详细功能说明

元数据管理器负责获取和缓存数据源元数据，为Agent提供字段信息。

#### 1. 元数据获取

**通过Tableau Metadata API获取**：
- 字段列表（fieldCaption、dataType）
- 字段描述
- 统计信息（unique_count等）

#### 2. 缓存管理

**Redis缓存策略**：
- 基础元数据缓存1小时
- 维度层级缓存24小时
- 缓存key格式：`metadata:{datasource_luid}`

#### 3. 数据源查找

**支持多种匹配方式**：
- 精确匹配（datasource_luid）
- 模糊匹配（datasource_name）
- 去括号匹配（处理"数据源(副本)"）

#### 4. 元数据增强

**调用维度层级推断Agent**：
- 首次访问时调用
- 将结果写入元数据的`dimension_hierarchy`字段
- 缓存24小时

### 详细验收标准

1. 元数据获取成功率 >= 99%
2. 缓存命中率 >= 90%
3. 数据源查找准确率 >= 95%
4. 元数据增强成功率 >= 95%

---
