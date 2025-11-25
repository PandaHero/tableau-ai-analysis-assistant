# 代码组件设计详解

本文档详细描�?个纯代码组件的设计，包括职责、算法、接口、错误处理和性能优化�?
---

## 目录

1. [元数据管理器](#1-元数据管理器)
2. [查询构建器](#2-查询构建�?
3. [查询执行器](#3-查询执行�?
4. [统计检测器](#4-统计检测器)
5. [数据合并器](#5-数据合并�?
6. [任务调度器](#6-任务调度�?

---

## 1. 元数据管理器

### 职责

获取和缓存数据源元数据，为Agent提供字段信息�?
### 设计决策

**为什么需要元数据管理器？**
- 集中管理元数据获取逻辑
- 统一缓存策略
- 支持多种数据源查找方�?
**为什么使用Redis缓存�?*
- 高性能（内存存储）
- 支持过期时间
- 支持分布式部�?
### 核心功能

#### 1. 元数据获�?
**通过Tableau Metadata API获取**�?```python
def get_metadata(self, datasource_luid: str) -> Dict:
    """获取数据源元数据"""
    # 检查缓�?    cache_key = f"metadata:{datasource_luid}"
    cached = self.cache.get(cache_key)
    if cached:
        return cached

    # 调用Tableau Metadata API
    metadata = self._fetch_from_tableau(datasource_luid)

    # 增强元数据（调用维度层级推断Agent�?    if not metadata.get("dimension_hierarchy"):
        metadata = self._enhance_metadata(metadata)

    # 缓存结果
    self.cache.set(cache_key, metadata, ttl=3600)  # 1小时

    return metadata
```

#### 2. 缓存管理

**缓存策略**�?- 基础元数据：1小时
- 维度层级�?4小时
- 缓存key格式：`metadata:{datasource_luid}`

**缓存失效**�?- 手动刷新
- 数据源结构变�?- 超过有效�?
#### 3. 数据源查�?
**支持多种匹配方式**�?```python
def find_datasource(self, identifier: str) -> Optional[str]:
    """查找数据源LUID"""
    # 1. 精确匹配（LUID�?    if self._is_valid_luid(identifier):
        return identifier

    # 2. 精确匹配（名称）
    luid = self._find_by_name(identifier)
    if luid:
        return luid

    # 3. 去括号匹�?    clean_name = self._remove_brackets(identifier)
    luid = self._find_by_name(clean_name)
    if luid:
        return luid

    # 4. 模糊匹配
    return self._fuzzy_match(identifier)
```


#### 4. 元数据增�?
**调用维度层级推断Agent**�?```python
def _enhance_metadata(self, metadata: Dict) -> Dict:
    """增强元数据（添加维度层级�?""
    dimensions = metadata.get("dimensions", [])

    # 调用维度层级推断Agent
    hierarchy_result = self.dimension_hierarchy_agent.infer_hierarchy(
        datasource_luid=metadata["luid"],
        dimensions=dimensions
    )

    # 合并结果
    metadata["dimension_hierarchy"] = hierarchy_result["dimension_hierarchy"]

    return metadata
```

### 接口设计

```python
class MetadataManager:
    """元数据管理器"""

    def __init__(
        self,
        tableau_client: TableauClient,
        cache: RedisCache,
        dimension_hierarchy_agent: DimensionHierarchyAgent
    ):
        self.tableau_client = tableau_client
        self.cache = cache
        self.dimension_hierarchy_agent = dimension_hierarchy_agent

    def get_metadata(self, datasource_luid: str) -> Dict:
        """获取数据源元数据"""
        pass

    def find_datasource(self, identifier: str) -> Optional[str]:
        """查找数据源LUID"""
        pass

    def refresh_metadata(self, datasource_luid: str) -> Dict:
        """刷新元数据（清除缓存�?""
        pass

    def list_datasources(self) -> List[Dict]:
        """列出所有数据源"""
        pass
```

### 错误处理

**错误类型**�?- 数据源不存在 �?返回404错误
- Tableau API调用失败 �?重试3�?- 维度层级推断失败 �?使用fallback规则

### 性能优化

**缓存命中率优�?*�?- 预加载常用数据源
- 延长缓存时间（维度层�?4小时�?- 批量获取元数�?
---

## 2. 查询构建�?
### 职责

根据语义级别的StructuredQuestionSpec生成技术级别的VizQL查询JSON，确保查�?00%正确�?
### 设计决策

**为什么使用代码而不是LLM�?*
- 确保100%正确（LLM可能出错�?- 性能更好（无需LLM调用�?- 易于调试和维�?
**为什么参考tableau_sdk�?*
- tableau_sdk提供完整的类型定�?- 确保生成的查询符合VizQL规范
- 利用Zod schema验证查询

### 核心功能

#### 1. 查询生成

**从语义Spec到技术JSON**�?```python
def build_query(self, spec: StructuredQuestionSpec) -> Dict:
    """构建VizQL查询"""
    query = {
        "fields": self._build_fields(spec),
        "filters": self._build_filters(spec),
        "limit": spec.limit
    }

    # 验证查询
    self._validate_query(query)

    return query

def _build_fields(self, spec: StructuredQuestionSpec) -> List[Dict]:
    """构建字段列表"""
    fields = []

    # 添加维度
    for dim in spec.dims:
        fields.append({
            "fieldCaption": dim
        })

    # 添加度量
    for metric in spec.metrics:
        field = {
            "fieldCaption": metric["field"],
            "function": metric["aggregation"].upper()
        }

        # 添加排序
        if spec.sort_by and spec.sort_by["field"] == metric["field"]:
            field["sortDirection"] = spec.sort_by["direction"].upper()
            field["sortPriority"] = 1

        fields.append(field)

    return fields
```

#### 2. tableau_sdk的使�?
**创建Python Pydantic模型**�?```python
from pydantic import BaseModel
from typing import Literal, Optional, Union

class FieldBase(BaseModel):
    fieldCaption: str
    fieldAlias: Optional[str] = None
    sortDirection: Optional[Literal["ASC", "DESC"]] = None
    sortPriority: Optional[int] = None

class FunctionField(FieldBase):
    function: Literal["SUM", "AVG", "COUNT", "MIN", "MAX", "YEAR", "MONTH", ...]

class CalculationField(FieldBase):
    calculation: str

Field = Union[FieldBase, FunctionField, CalculationField]

class Query(BaseModel):
    fields: List[Field]
    filters: List[Filter]
    limit: Optional[int] = None
```

#### 3. 日期字段处理

**设计决策**�?- 使用Python的`chinese-calendar`库处理中国节假日（而不是自己维护配置文件）
- 使用`lunarcalendar`库处理农历转�?- 日期配置从根目录的`.env`文件加载（不单独维护配置�?
**日期字段类型识别**�?```python
class DateFieldAnalyzer:
    """日期字段分析�?""
    
    def get_date_field_strategy(
        self,
        field_meta: Dict,
        filter_spec: Dict
    ) -> Dict:
        """根据字段类型和筛选需求决定策�?""
        data_type = field_meta["dataType"]
        
        # DATE/DATETIME类型：直接使用QuantitativeDateFilter
        if data_type in ("DATE", "DATETIME"):
            return {
                "strategy": "quantitative_date",
                "needs_dateparse": False,
                "date_format": None
            }
        
        # STRING类型：需要进一步判�?        if data_type == "STRING":
            return self._analyze_string_date_field(field_meta, filter_spec)
    
    def _analyze_string_date_field(self, field_meta: Dict, filter_spec: Dict) -> Dict:
        """分析STRING类型日期字段"""
        # 1. 检测日期格�?        date_format = self.detect_date_format(field_meta["sampleValues"])
        
        # 2. 根据筛选类型和基数决定策略
        filter_type = filter_spec.get("filter_type", "absolute")
        unique_count = field_meta.get("uniqueCount", 0)
        
        if filter_type == "absolute" and unique_count < 50:
            # 低基数绝对时间：使用SetFilter
            return {
                "strategy": "set",
                "needs_dateparse": False,
                "date_format": date_format
            }
        else:
            # 相对时间或高基数：使用DATEPARSE + QuantitativeDateFilter
            return {
                "strategy": "quantitative_date",
                "needs_dateparse": True,
                "date_format": date_format
            }
```

**日期格式检�?*�?```python
def detect_date_format(self, sample_values: List[str]) -> Optional[str]:
    """检测日期格式（支持8种常见格式）"""
    patterns = [
        (r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', 'yyyy-MM-dd HH:mm:ss'),
        (r'^\d{4}-\d{2}-\d{2}$', 'yyyy-MM-dd'),
        (r'^\d{4}/\d{2}/\d{2}$', 'yyyy/MM/dd'),
        (r'^\d{8}$', 'yyyyMMdd'),
        (r'^\d{2}/\d{2}/\d{4}$', None),  # 需要进一步判断dd/MM/yyyy vs MM/dd/yyyy
        (r'^\d{4}-\d{2}$', 'yyyy-MM'),
        (r'^\d{4}$', 'yyyy'),
    ]
    
    for pattern, format_str in patterns:
        if all(re.match(pattern, str(v)) for v in sample_values if v):
            if format_str is None:
                return self._detect_dmy_or_mdy(sample_values)
            return format_str
    
    return None
```

**DATEPARSE计算字段生成**�?```python
def generate_dateparse_calculation(self, field_caption: str, date_format: str) -> Dict:
    """生成DATEPARSE计算字段"""
    calc_name = f"{field_caption}"
    calc_formula = f"DATEPARSE('{date_format}', [{field_caption}])"
    
    return {
        "name": calc_name,
        "formula": calc_formula,
        "data_type": "DATE"
    }
```

#### 4. 日期计算

**相对日期计算**�?```python
class DateCalculator:
    """日期计算�?""
    
    def calculate_relative_date(
        self,
        period_type: str,
        offset: int,
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
```

**周范围计算（支持周开始日配置�?*�?```python
def calculate_week_range(
    self,
    anchor_date: datetime,
    date_features: Dict
) -> Tuple[datetime, datetime]:
    """计算周范围（支持周一/周日开始）"""
    # 从问题理解结果或配置获取周开始日
    week_start_day = self._get_week_start_day(date_features)
    
    # 计算当前是周几（0=周一�?=周日�?    current_weekday = anchor_date.weekday()
    
    # 计算到周开始的偏移
    days_since_week_start = (current_weekday - week_start_day) % 7
    
    # 周开始和结束日期
    week_start = anchor_date - timedelta(days=days_since_week_start)
    week_end = week_start + timedelta(days=6)
    
    return week_start, week_end

def _get_week_start_day(self, date_features: Dict) -> int:
    """获取周开始日（优先级：问题指�?> 环境配置 > 默认值）"""
    if date_features.get("week_start_day_mentioned"):
        return date_features["week_start_day"]
    return int(os.getenv('WEEK_START_DAY', '0'))
```

**周期完整性判断和上期计算**�?```python
def is_period_complete(self, anchor_date: datetime, period_type: str) -> bool:
    """判断当前周期是否完整"""
    if period_type == "DAYS":
        return True
    elif period_type == "WEEKS":
        return anchor_date.weekday() == 6  # 周日
    elif period_type == "MONTHS":
        last_day = monthrange(anchor_date.year, anchor_date.month)[1]
        return anchor_date.day == last_day
    # ... 其他周期类型

def calculate_previous_period(
    self,
    anchor_date: datetime,
    period_type: str,
    align_incomplete: bool = True
) -> Dict:
    """计算上期日期范围（支持周期对齐）"""
    is_complete = self.is_period_complete(anchor_date, period_type)
    
    # 如果当前周期未完整且align_incomplete=True，上期也取相同天�?    # 否则上期取完整周�?    # ... 详细实现见code-component-requirements.md
```

#### 5. 节假日处�?
**直接使用chinese-calendar�?*（不要自己造轮子）�?
```python
import chinese_calendar as calendar

# 判断是否是工作日
def is_working_day(date: datetime, date_features: Dict) -> bool:
    """判断是否是工作日"""
    # 如果问题不涉及节假日，只判断周末
    if not date_features.get("consider_holidays", False):
        return date.weekday() < 5
    
    # 直接使用chinese-calendar库（包含法定节假日和调休�?    return calendar.is_workday(date)

# 判断是否是节假日
def is_holiday(date: datetime) -> bool:
    """判断是否是节假日"""
    return calendar.is_holiday(date)

# 获取节假日名�?def get_holiday_name(date: datetime) -> Optional[str]:
    """获取节假日名�?""
    holiday = calendar.get_holiday_detail(date)
    return holiday.get('name') if holiday else None

# 计算工作日天�?def calculate_working_days(
    start_date: datetime,
    end_date: datetime,
    date_features: Dict
) -> int:
    """计算工作日天�?""
    if not date_features.get("consider_holidays", False):
        # 只计算周一到周�?        count = 0
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:
                count += 1
            current += timedelta(days=1)
        return count
    
    # 使用chinese-calendar�?    count = 0
    current = start_date
    while current <= end_date:
        if calendar.is_workday(current):
            count += 1
        current += timedelta(days=1)
    return count

# 获取工作日列表（用于SetFilter�?def filter_working_days(
    start_date: datetime,
    end_date: datetime,
    date_features: Dict
) -> List[str]:
    """获取工作日列�?""
    working_days = []
    current = start_date
    
    while current <= end_date:
        if is_working_day(current, date_features):
            working_days.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    
    return working_days
```

**chinese-calendar库的优势**�?- �?自动维护中国法定节假日和调休数据
- �?支持历史和未来年份（2004-2025+�?- �?无需手动维护配置文件
- �?社区维护，数据准�?- �?API简单：`is_workday()`, `is_holiday()`, `get_holiday_detail()`

**安装**�?```bash
pip install chinesecalendar
```

#### 6. 农历支持

**直接使用lunarcalendar�?*（不要自己造轮子）�?
```python
from lunarcalendar import Converter, Solar, Lunar

# 检查库是否可用
try:
    from lunarcalendar import Converter, Solar, Lunar
    LUNAR_AVAILABLE = True
except ImportError:
    LUNAR_AVAILABLE = False

# 阳历转农�?def solar_to_lunar(date: datetime) -> Optional[str]:
    """阳历转农�?""
    if not LUNAR_AVAILABLE:
        return None
    
    solar = Solar(date.year, date.month, date.day)
    lunar = Converter.Solar2Lunar(solar)
    
    return f"{lunar.year}年{lunar.month}月{lunar.day}�?

# 农历转阳�?def lunar_to_solar(year: int, month: int, day: int, leap: bool = False) -> Optional[datetime]:
    """农历转阳�?""
    if not LUNAR_AVAILABLE:
        return None
    
    lunar = Lunar(year, month, day, leap)
    solar = Converter.Lunar2Solar(lunar)
    
    return datetime(solar.year, solar.month, solar.day)

# 获取农历节日
def get_lunar_festivals(year: int) -> Dict[str, str]:
    """获取农历节日（转换为阳历日期�?""
    if not LUNAR_AVAILABLE:
        return {}
    
    festivals = {
        (year, 1, 1): "春节",
        (year, 1, 15): "元宵�?,
        (year, 5, 5): "端午�?,
        (year, 8, 15): "中秋�?,
    }
    
    solar_festivals = {}
    for (lunar_year, lunar_month, lunar_day), name in festivals.items():
        solar_date = lunar_to_solar(lunar_year, lunar_month, lunar_day)
        if solar_date:
            solar_festivals[solar_date.strftime('%Y-%m-%d')] = name
    
    return solar_festivals

# 处理农历相关问题
def handle_lunar_question(
    question: str,
    date_features: Dict,
    anchor_date: datetime
) -> Optional[Dict]:
    """处理农历相关问题"""
    if not date_features.get("support_lunar", False):
        return None
    
    if not LUNAR_AVAILABLE:
        raise ValueError("农历功能需要安装lunarcalendar�? pip install lunarcalendar")
    
    # 识别春节期间
    if "春节" in date_features.get("lunar_keywords", []):
        festivals = get_lunar_festivals(anchor_date.year)
        spring_festival_date = None
        
        for date_str, name in festivals.items():
            if name == "春节":
                spring_festival_date = datetime.fromisoformat(date_str)
                break
        
        if spring_festival_date:
            # 春节期间：春节前�?�?            start_date = spring_festival_date - timedelta(days=3)
            end_date = spring_festival_date + timedelta(days=3)
            
            return {
                "start_date": start_date.strftime('%Y-%m-%d'),
                "end_date": end_date.strftime('%Y-%m-%d'),
                "festival_name": "春节",
                "festival_date": spring_festival_date.strftime('%Y-%m-%d')
            }
    
    return None
```

**lunarcalendar库的优势**�?- �?专业的农历转换库
- �?支持阳历↔农历双向转�?- �?支持闰月处理
- �?API简单：`Converter.Solar2Lunar()`, `Converter.Lunar2Solar()`

**安装**�?```bash
pip install lunarcalendar
```

#### 7. 环境配置

**从根目录.env加载配置**�?```python
import os
from dotenv import load_dotenv

# 加载根目录的.env文件
load_dotenv()

class DateProcessingConfig:
    """日期处理配置"""
    
    def __init__(self):
        # 周开始日�?=周一�?=周日�?        self.WEEK_START_DAY = int(os.getenv('WEEK_START_DAY', '0'))
        
        # SetFilter阈�?        self.SET_FILTER_THRESHOLD = int(os.getenv('SET_FILTER_THRESHOLD', '50'))
```

**配置说明**�?- `WEEK_START_DAY`: 周开始日配置，影响周范围计算
- `SET_FILTER_THRESHOLD`: STRING类型日期字段使用SetFilter的阈�?
**不需要的配置**�?- �?`DEFAULT_DATE_FORMAT`: 日期格式应该自动检测，检测失败应报错
- �?`ANCHOR_DATE_CACHE_TTL`: 使用元数据缓存系统的统一TTL

**配置优先�?*�?1. **问题理解结果**（最高优先级�? 用户在问题中明确提到的配�?2. **环境配置**�?env文件�? 系统默认行为
3. **代码默认�?*（最低优先级�? fallback�?
#### 4. 查询验证

**基于tableau_sdk的schema验证**�?```python
def _validate_query(self, query: Dict) -> None:
    """验证查询结构"""
    # 使用Pydantic模型验证
    try:
        Query(**query)
    except ValidationError as e:
        raise QueryValidationError(f"Invalid query: {e}")

    # 业务规则验证
    if not query.get("fields"):
        raise QueryValidationError("Query must have at least one field")

    # 检查sortPriority不重�?    sort_priorities = [
        f.get("sortPriority")
        for f in query["fields"]
        if f.get("sortPriority")
    ]
    if len(sort_priorities) != len(set(sort_priorities)):
        raise QueryValidationError("sortPriority must be unique")
```

#### 5. Builder模式

**不同类型的查询使用不同的Builder**�?```python
class QueryBuilderFactory:
    """查询构建器工�?""

    @staticmethod
    def create_builder(question_type: str) -> QueryBuilder:
        """创建查询构建�?""
        if "趋势" in question_type:
            return TimeSeriesQueryBuilder()
        elif "排名" in question_type:
            return RankingQueryBuilder()
        elif "对比" in question_type:
            return ComparisonQueryBuilder()
        else:
            return BasicQueryBuilder()

class BasicQueryBuilder(QueryBuilder):
    """基础查询构建�?""
    pass

class TimeSeriesQueryBuilder(QueryBuilder):
    """时间序列查询构建�?""
    def _build_fields(self, spec: StructuredQuestionSpec) -> List[Dict]:
        # 添加时间粒度
        fields = super()._build_fields(spec)
        if spec.grain:
            fields.insert(0, {
                "fieldCaption": "订单日期",
                "function": spec.grain.upper()
            })
        return fields
```

### 接口设计

```python
class QueryBuilder:
    """查询构建器基�?""

    def build_query(self, spec: StructuredQuestionSpec) -> Dict:
        """构建VizQL查询"""
        pass

    def _build_fields(self, spec: StructuredQuestionSpec) -> List[Dict]:
        """构建字段列表"""
        pass

    def _build_filters(self, spec: StructuredQuestionSpec) -> List[Dict]:
        """构建筛选条�?""
        pass

    def _validate_query(self, query: Dict) -> None:
        """验证查询结构"""
        pass
```

### 性能优化

**查询缓存**�?- 缓存相同Spec的查询结�?- 缓存key：Spec的fingerprint
- 有效期：5分钟

---

## 3. 查询执行�?
### 职责

调用Tableau VDS API执行查询，处理分页和错误，确保查询稳定可靠�?
### 核心功能

#### 1. 查询执行

**调用Tableau VDS API**�?```python
def execute_query(self, query: Dict, datasource_luid: str) -> pd.DataFrame:
    """执行VizQL查询"""
    # 调用VDS API
    response = self.tableau_client.execute_vizql_query(
        datasource_luid=datasource_luid,
        query=query
    )

    # 处理分页
    all_data = []
    all_data.extend(response["data"])

    while response.get("hasMoreData"):
        response = self._fetch_next_page(response["nextPageToken"])
        all_data.extend(response["data"])

    # 转换为DataFrame
    return self._parse_response(all_data, response["schema"])
```

#### 2. 分页处理

**自动获取所有页**�?```python
def _fetch_next_page(self, next_page_token: str) -> Dict:
    """获取下一页数�?""
    response = self.tableau_client.fetch_page(next_page_token)
    return response
```

#### 3. 错误处理

**智能重试和超时控�?*�?```python
def execute_query_with_retry(
    self,
    query: Dict,
    datasource_luid: str,
    max_retries: int = 3
) -> pd.DataFrame:
    """执行查询（带重试�?""
    for attempt in range(max_retries):
        try:
            return self.execute_query(query, datasource_luid)
        except RetryableError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 指数退�?                time.sleep(wait_time)
            else:
                raise
        except NonRetryableError as e:
            raise
```

#### 4. 结果解析

**解析VDS响应**�?```python
def _parse_response(self, data: List, schema: Dict) -> pd.DataFrame:
    """解析VDS响应为DataFrame"""
    # 提取列名
    columns = [col["name"] for col in schema["columns"]]

    # 创建DataFrame
    df = pd.DataFrame(data, columns=columns)

    # 处理数据类型
    for col in schema["columns"]:
        if col["dataType"] == "REAL":
            df[col["name"]] = pd.to_numeric(df[col["name"]])
        elif col["dataType"] == "DATE":
            df[col["name"]] = pd.to_datetime(df[col["name"]])

    return df
```

### 接口设计

```python
class QueryExecutor:
    """查询执行�?""

    def __init__(self, tableau_client: TableauClient):
        self.tableau_client = tableau_client

    def execute_query(self, query: Dict, datasource_luid: str) -> pd.DataFrame:
        """执行VizQL查询"""
        pass

    def execute_query_with_retry(
        self,
        query: Dict,
        datasource_luid: str,
        max_retries: int = 3
    ) -> pd.DataFrame:
        """执行查询（带重试�?""
        pass
```

### 性能优化

**查询结果缓存**�?- 缓存相同查询的结�?- 缓存key：查询的fingerprint
- 有效期：5分钟

---

## 4. 统计检测器

### 职责

对查询结果进行客观的统计分析，检测异常值和趋势，为AI提供分析依据�?
### 核心功能

#### 1. 描述性统�?
**计算基础统计指标**�?```python
def calculate_descriptive_stats(self, df: pd.DataFrame, column: str) -> Dict:
    """计算描述性统�?""
    return {
        "mean": df[column].mean(),
        "median": df[column].median(),
        "std": df[column].std(),
        "min": df[column].min(),
        "max": df[column].max(),
        "q25": df[column].quantile(0.25),
        "q75": df[column].quantile(0.75)
    }
```

#### 2. 异常检�?
**使用统计方法检测异�?*�?```python
def detect_anomalies(self, df: pd.DataFrame, column: str) -> List[Dict]:
    """检测异常�?""
    anomalies = []

    # Z-score方法
    z_scores = np.abs((df[column] - df[column].mean()) / df[column].std())
    z_anomalies = df[z_scores > 3]

    # IQR方法
    q1 = df[column].quantile(0.25)
    q3 = df[column].quantile(0.75)
    iqr = q3 - q1
    iqr_anomalies = df[
        (df[column] < q1 - 1.5 * iqr) | (df[column] > q3 + 1.5 * iqr)
    ]

    # 合并结果
    for idx in z_anomalies.index:
        anomalies.append({
            "index": idx,
            "value": df.loc[idx, column],
            "method": "z-score",
            "severity": "high" if z_scores[idx] > 4 else "medium"
        })

    return anomalies
```

#### 3. 趋势分析

**分析时间序列趋势**�?```python
def analyze_trend(self, df: pd.DataFrame, time_col: str, value_col: str) -> Dict:
    """分析趋势"""
    # 线性回�?    x = np.arange(len(df))
    y = df[value_col].values
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

    # Mann-Kendall检�?    mk_result = mk.original_test(y)

    return {
        "slope": slope,
        "r_squared": r_value ** 2,
        "p_value": p_value,
        "trend_direction": "上升" if slope > 0 else "下降",
        "trend_significance": "显著" if p_value < 0.05 else "不显�?,
        "mk_trend": mk_result.trend
    }
```

#### 4. 数据质量检�?
**评估数据质量**�?```python
def check_data_quality(self, df: pd.DataFrame) -> Dict:
    """检查数据质�?""
    return {
        "completeness": 1 - df.isnull().sum().sum() / (df.shape[0] * df.shape[1]),
        "consistency": 1 - df.duplicated().sum() / len(df),
        "accuracy": self._calculate_accuracy(df)
    }
```

### 接口设计

```python
class StatisticsDetector:
    """统计检测器"""

    def calculate_descriptive_stats(self, df: pd.DataFrame, column: str) -> Dict:
        """计算描述性统�?""
        pass

    def detect_anomalies(self, df: pd.DataFrame, column: str) -> List[Dict]:
        """检测异常�?""
        pass

    def analyze_trend(self, df: pd.DataFrame, time_col: str, value_col: str) -> Dict:
        """分析趋势"""
        pass

    def check_data_quality(self, df: pd.DataFrame) -> Dict:
        """检查数据质�?""
        pass

    def generate_report(self, df: pd.DataFrame) -> Dict:
        """生成统计报告"""
        pass
```

---

## 5. 数据合并�?
### 职责

智能合并多个子任务的查询结果，自动处理数据对齐、补全和计算�?
### 核心功能

#### 1. 合并策略选择

**基于代码规则选择合并策略**�?```python
def select_merge_strategy(self, subtasks: List[Dict]) -> str:
    """选择合并策略"""
    # Union：相同结构的数据
    if self._has_same_structure(subtasks):
        return "union"

    # Join：基于共同维�?    common_dims = self._find_common_dimensions(subtasks)
    if common_dims:
        return "join"

    # Append：简单追�?    return "append"
```

#### 2. 数据对齐与补�?
**处理数据不一�?*�?```python
def align_and_fill(self, dfs: List[pd.DataFrame]) -> pd.DataFrame:
    """对齐和补全数�?""
    # 时间序列补点
    if self._is_time_series(dfs[0]):
        dfs = [self._fill_time_gaps(df) for df in dfs]

    # 维度组合补全
    all_combinations = self._get_all_combinations(dfs)
    dfs = [self._fill_dimension_combinations(df, all_combinations) for df in dfs]

    return dfs
```

#### 3. 数据去重与清�?
**确保数据质量**�?```python
def clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
    """清洗数据"""
    # 去重
    df = df.drop_duplicates()

    # 异常值处�?    df = self._handle_outliers(df)

    # 空值处�?    df = df.fillna(0)

    return df
```

#### 4. 聚合计算

**计算派生指标**�?```python
def calculate_aggregations(self, df: pd.DataFrame) -> pd.DataFrame:
    """计算聚合指标"""
    # 总计
    total = df.sum()

    # 占比
    df["占比"] = df["销售额"] / total["销售额"]

    # 排名
    df["排名"] = df["销售额"].rank(ascending=False)

    # 累计
    df["累计销售额"] = df["销售额"].cumsum()

    return df
```

### 接口设计

```python
class DataMerger:
    """数据合并�?""

    def merge_results(self, subtask_results: List[Dict]) -> Dict:
        """合并子任务结�?""
        pass

    def select_merge_strategy(self, subtasks: List[Dict]) -> str:
        """选择合并策略"""
        pass

    def align_and_fill(self, dfs: List[pd.DataFrame]) -> List[pd.DataFrame]:
        """对齐和补全数�?""
        pass

    def clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """清洗数据"""
        pass

    def calculate_aggregations(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算聚合指标"""
        pass
```

---

## 6. 任务调度�?
### 职责

高效执行多个子任务，实时推送进度，处理失败和超时�?
### 核心功能

#### 1. 任务调度

**按stage升序执行**�?```python
def execute_all_stages(self, tasks: List[Dict]) -> List[Dict]:
    """按stage顺序执行所有任�?""
    all_stages = sorted(set(t.get("stage", 1) for t in tasks))
    all_results = []

    for stage in all_stages:
        stage_results = self._execute_stage(tasks, stage)
        all_results.extend(stage_results)

    return all_results

def _execute_stage(self, tasks: List[Dict], stage: int) -> List[Dict]:
    """执行指定stage的所有任务（并行�?""
    stage_tasks = [t for t in tasks if t.get("stage") == stage]

    # 使用ThreadPoolExecutor并行执行
    with ThreadPoolExecutor(max_workers=self.parallel_limit) as executor:
        future_to_task = {
            executor.submit(self._execute_single_task, task): task
            for task in stage_tasks
        }

        results = []
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
```

#### 2. 超时控制

**动态超时时�?*�?```python
def _calculate_timeout(self, task: Dict) -> int:
    """计算动态超时时�?""
    base_timeout = 30
    complexity = task.get("complexity", "Simple")

    if complexity == "Complex":
        return min(base_timeout + 30, 120)
    elif complexity == "Medium":
        return min(base_timeout + 15, 120)
    else:
        return base_timeout
```

#### 3. 失败处理

**智能重试**�?```python
def _execute_single_task_with_retry(self, task: Dict, max_retries: int = 2) -> Dict:
    """执行单个任务（带重试�?""
    for attempt in range(max_retries + 1):
        try:
            return self._execute_single_task(task)
        except RetryableError as e:
            if attempt < max_retries:
                wait_time = 2 ** attempt  # 指数退�?                time.sleep(wait_time)
            else:
                return {
                    "task_id": task.get("question_id"),
                    "status": "error",
                    "error": str(e)
                }
        except NonRetryableError as e:
            return {
                "task_id": task.get("question_id"),
                "status": "error",
                "error": str(e)
            }
```

#### 4. 进度反馈

**SSE实时推�?*�?```python
def _send_progress(self, event_type: str, data: Dict):
    """发送进度事�?""
    event = {
        "type": event_type,
        "data": data,
        "timestamp": datetime.now().isoformat()
    }
    self.sse_queue.put(event)
```

### 接口设计

```python
class TaskScheduler:
    """任务调度�?""

    def __init__(self, parallel_limit: int = 3):
        self.parallel_limit = parallel_limit
        self.executor = ThreadPoolExecutor(max_workers=parallel_limit)
        self.sse_queue = Queue()

    def execute_all_stages(self, tasks: List[Dict]) -> List[Dict]:
        """按stage顺序执行所有任�?""
        pass

    def _execute_stage(self, tasks: List[Dict], stage: int) -> List[Dict]:
        """执行指定stage的所有任务（并行�?""
        pass

    def _execute_single_task(self, task: Dict) -> Dict:
        """执行单个任务"""
        pass

    def _calculate_timeout(self, task: Dict) -> int:
        """计算动态超时时�?""
        pass
```

---

**文档版本**: v1.0
**最后更�?*: 2025-10-30

