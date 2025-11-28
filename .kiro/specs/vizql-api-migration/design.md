# 设计文档

## 概述

本设计文档描述了将 Tableau Assistant 升级到新版 VizQL Data Service API 并集成 DeepAgents 架构的技术方案。本次升级的核心目标是：

1. **支持表计算**：添加 TableCalcField 支持，实现累计总和、移动平均、排名等高级分析
2. **DeepAgents 集成**：使用 DeepAgents 框架和 6 个中间件增强系统能力
3. **工具封装**：将现有组件封装为 LangChain 工具
4. **类型安全**：使用 Pydantic v2 模型确保类型安全

### 升级背景

- **当前状态**：使用旧版 VizQL API，不支持表计算
- **目标状态**：升级到 Tableau 2025.1+ API，支持表计算和高级功能
- **架构变化**：从传统架构迁移到 DeepAgents 架构
- **技术选型**：使用现有的 requests 库 + Pydantic 模型（不使用官方 SDK）

### 升级策略

采用**直接升级**策略，一次性完成迁移：

```
┌─────────────────────────────────────────────────┐
│         用户问题（自然语言）                      │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│         DeepAgent（6 个中间件）                  │
│  - AnthropicPromptCaching (Claude only)         │
│  - Summarization                                │
│  - Filesystem                                   │
│  - ToolRetry                                    │
│  - TodoList                                     │
│  - HumanInTheLoop                               │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│         StateGraph 工作流（6 个节点）            │
│  Boost → Understanding → Planning →             │
│  Execute → Insight → Replanner                  │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│         8 个 LangChain 工具                      │
│  - get_metadata                                 │
│  - parse_date                                   │
│  - build_vizql_query (支持表计算)               │
│  - execute_vizql_query                          │
│  - semantic_map_fields                          │
│  - process_query_result                         │
│  - detect_statistics                            │
│  - get_dimension_hierarchy                      │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│         现有组件（增强）                          │
│  - QueryBuilder (添加表计算支持)                │
│  - QueryExecutor (添加 Pydantic 验证)           │
│  - MetadataManager (识别表计算字段)             │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│         VizQL Data Service API                  │
│  - 使用 requests 库                             │
│  - 复用现有认证（JWT/PAT）                      │
│  - Pydantic 模型验证                            │
└─────────────────────────────────────────────────┘
```

## 架构

### 系统架构图

```
用户问题
    ↓
DeepAgent (6 个中间件)
    ├── AnthropicPromptCaching (Claude only)
    ├── Summarization
    ├── Filesystem
    ├── ToolRetry
    ├── TodoList
    └── HumanInTheLoop
    ↓
StateGraph 工作流
    Boost → Understanding → Planning → Execute → Insight → Replanner
                                ↑___________________________|
    ↓
8 个 LangChain 工具
    ├── get_metadata
    ├── parse_date
    ├── build_vizql_query (支持表计算)
    ├── execute_vizql_query
    ├── semantic_map_fields
    ├── process_query_result
    ├── detect_statistics
    └── get_dimension_hierarchy
    ↓
组件层
    ├── MetadataManager
    ├── QueryBuilder (添加表计算支持)
    └── QueryExecutor (添加 Pydantic 验证)
    ↓
数据模型层
    ├── Intent 模型 (+ TableCalcIntent)
    └── VizQL 模型 (+ TableCalcField)
    ↓
API 层
    ├── 认证 (JWT/PAT)
    └── VizQL Data Service (requests + Pydantic)
```

### 分层架构说明

#### 1. 用户层
- 接收自然语言问题
- 返回分析洞察

#### 2. DeepAgent 层
- 使用 `create_deep_agent()` 创建
- 集成 6 个中间件
- 管理工具调用和状态

#### 3. 工作流层（StateGraph）
- **Boost 节点**：问题增强（可选）
- **Understanding 节点**：理解用户意图
- **Planning 节点**：生成查询计划（Intent → VizQLQuery）
- **Execute 节点**：执行查询
- **Insight 节点**：生成洞察
- **Replanner 节点**：重规划（可选）

#### 4. 工具层
8 个 LangChain 工具，封装现有组件

#### 5. 组件层
现有组件，增强以支持表计算

#### 6. 数据模型层
- Intent 模型：添加 TableCalcIntent
- VizQL 模型：添加 TableCalcField

#### 7. API 层
- 使用 requests 库
- 复用现有认证
- Pydantic 模型验证

## 组件和接口

### 1. DeepAgent 创建器

已实现于 `tableau_assistant/src/agents/deep_agent_factory.py`

```python
def create_tableau_deep_agent(
    tools: List[BaseTool],
    model_config: Optional[Dict[str, Any]] = None,
    store: Optional[BaseStore] = None,
    system_prompt: Optional[str] = None
) -> CompiledStateGraph:
    """
    创建 Tableau Assistant 的 DeepAgent
    
    配置 6 个中间件：
    1. AnthropicPromptCachingMiddleware (仅 Claude)
    2. SummarizationMiddleware (10 轮触发)
    3. FilesystemMiddleware (10MB 阈值)
    4. ToolRetryMiddleware (3 次重试)
    5. TodoListMiddleware (10 个任务)
    6. HumanInTheLoopMiddleware (5 分钟超时)
    """
```

### 2. 工具封装层

将 8 个组件封装为 LangChain 工具：

```python
from langchain.tools import tool

@tool
def get_metadata(datasource_luid: str) -> Dict[str, Any]:
    """
    获取数据源元数据
    
    Args:
        datasource_luid: 数据源 LUID
    
    Returns:
        包含字段信息的元数据字典
    """
    # 调用 MetadataManager
    pass

@tool
def build_vizql_query(intent: Dict[str, Any]) -> Dict[str, Any]:
    """
    构建 VizQL 查询
    
    支持：
    - DimensionIntent → BasicField
    - MeasureIntent → FunctionField
    - DateFieldIntent → FunctionField (with date function)
    - TableCalcIntent → TableCalcField (新增)
    
    Args:
        intent: Intent 对象字典
    
    Returns:
        VizQLQuery 对象字典
    """
    # 调用 QueryBuilder
    pass

@tool
def execute_vizql_query(
    datasource_luid: str,
    query: Dict[str, Any]
) -> Dict[str, Any]:
    """
    执行 VizQL 查询
    
    Args:
        datasource_luid: 数据源 LUID
        query: VizQLQuery 对象字典
    
    Returns:
        查询结果
    """
    # 调用 QueryExecutor
    pass
```

### 3. TableCalcIntent 模型

新增于 `tableau_assistant/src/models/intent.py`

```python
class TableCalcIntent(BaseModel):
    """
    表计算意图
    
    用于表达表计算需求，如累计总和、移动平均、排名等
    """
    model_config = ConfigDict(extra="forbid")
    
    business_term: str = Field(
        description="业务术语（如'销售额累计'、'产品排名'）"
    )
    
    technical_field: str = Field(
        description="技术字段名（从元数据映射）"
    )
    
    table_calc_type: Literal[
        "RUNNING_TOTAL",
        "MOVING_CALCULATION", 
        "RANK",
        "PERCENTILE",
        "PERCENT_OF_TOTAL",
        "PERCENT_FROM",
        "PERCENT_DIFFERENCE_FROM",
        "DIFFERENCE_FROM",
        "CUSTOM",
        "NESTED"
    ] = Field(
        description="表计算类型"
    )
    
    table_calc_config: Dict[str, Any] = Field(
        description="""表计算配置
        
        RUNNING_TOTAL:
            - aggregation: "SUM" | "AVG" | etc.
            - dimensions: List[str]
            - restartEvery: Optional[str]
        
        MOVING_CALCULATION:
            - aggregation: "SUM" | "AVG" | etc.
            - dimensions: List[str]
            - previous: int
            - next: int
            - includeCurrent: bool
        
        RANK:
            - dimensions: List[str]
            - rankType: "COMPETITION" | "DENSE" | "UNIQUE"
            - direction: "ASC" | "DESC"
        """
    )
    
    sort_direction: Optional[Literal["ASC", "DESC"]] = None
    sort_priority: Optional[int] = None
```

### 4. TableCalcField 模型

新增于 `tableau_assistant/src/models/vizql_types.py`

```python
class TableCalcSpecification(BaseModel):
    """表计算规范基类"""
    model_config = ConfigDict(extra="forbid")
    
    tableCalcType: Literal[
        "RUNNING_TOTAL",
        "MOVING_CALCULATION",
        "RANK",
        "PERCENTILE",
        "PERCENT_OF_TOTAL",
        "PERCENT_FROM",
        "PERCENT_DIFFERENCE_FROM",
        "DIFFERENCE_FROM",
        "CUSTOM",
        "NESTED"
    ]
    
    dimensions: List[str] = Field(
        description="计算维度（用于分组）"
    )


class RunningTotalTableCalcSpecification(TableCalcSpecification):
    """累计总计规范"""
    tableCalcType: Literal["RUNNING_TOTAL"] = "RUNNING_TOTAL"
    
    aggregation: FunctionEnum = Field(
        description="聚合函数（SUM、AVG 等）"
    )
    
    restartEvery: Optional[str] = Field(
        None,
        description="重新开始计算的维度"
    )
    
    secondaryTableCalculation: Optional['TableCalcSpecification'] = None


class MovingTableCalcSpecification(TableCalcSpecification):
    """移动计算规范"""
    tableCalcType: Literal["MOVING_CALCULATION"] = "MOVING_CALCULATION"
    
    aggregation: FunctionEnum
    previous: int = Field(ge=0, description="向前取值数量")
    next: int = Field(ge=0, description="向后取值数量")
    includeCurrent: bool = True
    fillInNull: Optional[bool] = None


class RankTableCalcSpecification(TableCalcSpecification):
    """排名计算规范"""
    tableCalcType: Literal["RANK"] = "RANK"
    
    rankType: Literal["COMPETITION", "DENSE", "UNIQUE"] = "COMPETITION"
    direction: Literal["ASC", "DESC"] = "ASC"


class TableCalcField(FieldBase):
    """
    表计算字段
    
    用于：
    - 累计总和：RUNNING_TOTAL
    - 移动平均：MOVING_CALCULATION
    - 排名：RANK
    - 百分比：PERCENT_OF_TOTAL
    
    Examples:
        # 累计总和
        TableCalcField(
            fieldCaption="Sales",
            tableCalculation=RunningTotalTableCalcSpecification(
                tableCalcType="RUNNING_TOTAL",
                aggregation=FunctionEnum.SUM,
                dimensions=["Category"]
            )
        )
        
        # 移动平均
        TableCalcField(
            fieldCaption="Sales",
            tableCalculation=MovingTableCalcSpecification(
                tableCalcType="MOVING_CALCULATION",
                aggregation=FunctionEnum.AVG,
                dimensions=["Order Date"],
                previous=2,
                next=0,
                includeCurrent=True
            )
        )
    """
    function: Optional[FunctionEnum] = None
    calculation: Optional[str] = None
    tableCalculation: Union[
        RunningTotalTableCalcSpecification,
        MovingTableCalcSpecification,
        RankTableCalcSpecification,
        # ... 其他类型
    ]
    nestedTableCalculations: Optional[List[TableCalcSpecification]] = None


# 更新 VizQLField 联合类型
VizQLField = Annotated[
    Union[BasicField, FunctionField, CalculationField, TableCalcField],
    Field(discriminator=None)
]
```

### 5. QueryBuilder 增强

扩展 `tableau_assistant/src/components/query_builder/` 以支持表计算

```python
class QueryBuilder:
    """查询构建器"""
    
    def build_field(self, intent: Union[
        DimensionIntent,
        MeasureIntent,
        DateFieldIntent,
        TableCalcIntent  # 新增
    ]) -> VizQLField:
        """
        根据 Intent 构建字段
        
        新增支持：
        - TableCalcIntent → TableCalcField
        """
        if isinstance(intent, TableCalcIntent):
            return self.build_table_calc_field(intent)
        # ... 现有逻辑
    
    def build_table_calc_field(
        self,
        intent: TableCalcIntent
    ) -> TableCalcField:
        """
        构建表计算字段
        
        根据 table_calc_type 创建相应的 TableCalcSpecification
        """
        calc_type = intent.table_calc_type
        config = intent.table_calc_config
        
        if calc_type == "RUNNING_TOTAL":
            spec = RunningTotalTableCalcSpecification(
                tableCalcType="RUNNING_TOTAL",
                aggregation=config["aggregation"],
                dimensions=config["dimensions"],
                restartEvery=config.get("restartEvery")
            )
        elif calc_type == "MOVING_CALCULATION":
            spec = MovingTableCalcSpecification(
                tableCalcType="MOVING_CALCULATION",
                aggregation=config["aggregation"],
                dimensions=config["dimensions"],
                previous=config["previous"],
                next=config["next"],
                includeCurrent=config.get("includeCurrent", True)
            )
        elif calc_type == "RANK":
            spec = RankTableCalcSpecification(
                tableCalcType="RANK",
                dimensions=config["dimensions"],
                rankType=config.get("rankType", "COMPETITION"),
                direction=config.get("direction", "ASC")
            )
        # ... 其他类型
        
        return TableCalcField(
            fieldCaption=intent.technical_field,
            tableCalculation=spec,
            sortDirection=intent.sort_direction,
            sortPriority=intent.sort_priority
        )
```

### 6. VizQL 客户端增强

增强 `tableau_assistant/src/bi_platforms/tableau/vizql_data_service.py`

```python
def query_vds(
    api_key: str,
    datasource_luid: str,
    url: str,
    query: Union[Dict[str, Any], VizQLQuery],  # 支持 Pydantic 模型
    site: str = None
) -> Dict[str, Any]:
    """
    执行 VizQL 查询
    
    增强：
    - 支持 Pydantic 模型输入
    - 自动验证请求
    - 统一错误处理
    """
    # 如果是 Pydantic 模型，序列化
    if isinstance(query, VizQLQuery):
        query_dict = query.model_dump(exclude_none=True)
    else:
        # 验证字典格式
        query_dict = VizQLQuery(**query).model_dump(exclude_none=True)
    
    full_url = f"{url}/api/v1/vizql-data-service/query-datasource"
    
    payload = {
        "datasource": {
            "datasourceLuid": datasource_luid
        },
        "query": query_dict
    }
    
    headers = {
        'X-Tableau-Auth': api_key,
        'Content-Type': 'application/json'
    }
    
    if site:
        headers['X-Tableau-Site'] = site
    
    response = requests.post(full_url, headers=headers, json=payload)
    
    if response.status_code == 200:
        # 验证响应
        return QueryOutput(**response.json()).model_dump()
    else:
        # 统一错误处理
        raise RuntimeError(f"Query failed: {response.status_code} - {response.text}")
```

## 组件和接口

### 日期管理器（DateManager）

**职责**: 统一管理所有日期相关功能，包括日期计算、解析和格式检测。

**架构设计**:

```
DateManager (统一入口)
├── DateCalculator (日期计算)
│   └── 相对日期计算 (LASTN, LAST, CURRENT, NEXT, NEXTN)
├── DateParser (日期解析)
│   └── TimeRange → 具体日期范围
└── DateFormatDetector (日期格式检测) ★ 新增
    └── STRING 字段日期格式检测和转换
```

**使用场景**:
- MetadataManager 使用 DateManager 检测 STRING 字段的日期格式
- QueryBuilder 使用 DateManager 解析日期范围和转换日期格式
- DateFilterConverter 使用 DateManager 构建日期过滤器

### 日期格式检测器（DateFormatDetector）

**职责**: 自动检测数据源中字符串类型日期字段的格式，并提供格式转换功能。

**接口设计**:

```python
class DateFormatType(Enum):
    """日期格式类型枚举"""
    ISO_DATE = "YYYY-MM-DD"           # 2024-01-15
    US_DATE = "MM/DD/YYYY"            # 01/15/2024
    EU_DATE = "DD/MM/YYYY"            # 15/01/2024
    US_DATE_DASH = "MM-DD-YYYY"       # 01-15-2024
    EU_DATE_DASH = "DD-MM-YYYY"       # 15-01-2024
    YEAR_MONTH = "YYYY-MM"            # 2024-01
    MONTH_YEAR = "MM/YYYY"            # 01/2024
    QUARTER = "YYYY-QN"               # 2024-Q1
    YEAR_ONLY = "YYYY"                # 2024
    LONG_DATE = "Month DD, YYYY"      # January 15, 2024
    SHORT_MONTH = "MMM DD, YYYY"      # Jan 15, 2024
    TIMESTAMP = "YYYY-MM-DD HH:MM:SS" # 2024-01-15 10:30:00
    EXCEL_DATE = "M/D/YYYY"           # 1/15/2024 (no leading zeros)
    UNKNOWN = "UNKNOWN"


class DateFormatDetector:
    """日期格式检测器"""
    
    def detect_format(
        self, 
        sample_values: List[str], 
        confidence_threshold: float = 0.7
    ) -> DateFormatType:
        """
        检测日期格式
        
        Args:
            sample_values: 样本日期值列表
            confidence_threshold: 置信度阈值（默认 0.7）
        
        Returns:
            检测到的日期格式类型
        
        算法:
        1. 对每种格式模式进行正则匹配
        2. 计算每种格式的匹配率（匹配数/总样本数）
        3. 选择匹配率最高且超过阈值的格式
        4. 对于美式/欧式格式歧义，通过分析日期范围区分
        """
        pass
    
    def convert_to_iso(
        self, 
        date_value: str, 
        source_format: DateFormatType
    ) -> Optional[str]:
        """
        转换日期为 ISO 格式（YYYY-MM-DD）
        
        Args:
            date_value: 原始日期值
            source_format: 源日期格式
        
        Returns:
            ISO 格式的日期字符串，转换失败返回 None
        """
        pass
    
    def get_format_info(self, format_type: DateFormatType) -> Dict[str, str]:
        """
        获取格式信息
        
        Returns:
            包含 name、pattern、example、description 的字典
        """
        pass
```

**美式/欧式格式区分策略**:

```python
def _disambiguate_us_eu_format(self, samples: List[str]) -> DateFormatType:
    """
    区分美式和欧式日期格式
    
    策略：
    1. 查找明显的区分标志（如月份>12的情况）
    2. 如果第一个数字>12，说明是欧式格式（DD/MM/YYYY）
    3. 如果第二个数字>12，说明是美式格式（MM/DD/YYYY）
    4. 如果都不明显，默认使用美式格式
    """
    us_indicators = 0
    eu_indicators = 0
    
    for sample in samples:
        match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', sample)
        if match:
            first_num = int(match.group(1))
            second_num = int(match.group(2))
            
            if first_num > 12:
                eu_indicators += 1
            elif second_num > 12:
                us_indicators += 1
    
    return DateFormatType.EU_DATE if eu_indicators > us_indicators else DateFormatType.US_DATE
```

**DateManager 统一接口**:

```python
class DateManager:
    """
    日期管理器 - 统一管理所有日期相关功能
    
    职责：
    1. 提供统一的日期功能入口
    2. 管理 DateCalculator、DateParser、DateFormatDetector
    3. 缓存日期格式检测结果
    """
    
    def __init__(
        self,
        anchor_date: Optional[datetime] = None,
        week_start_day: int = 0
    ):
        """初始化日期管理器"""
        self.calculator = DateCalculator(anchor_date, week_start_day)
        self.parser = DateParser(self.calculator)
        self.format_detector = DateFormatDetector()
        self.field_formats_cache: Dict[str, DateFormatType] = {}
    
    # ===== 日期计算功能 =====
    def calculate_relative_date(
        self,
        relative_type: str,
        period_type: str,
        range_n: Optional[int] = None
    ) -> Dict[str, str]:
        """计算相对日期范围（委托给 DateCalculator）"""
        return self.calculator.calculate_relative_date(
            relative_type, period_type, range_n
        )
    
    # ===== 日期解析功能 =====
    def parse_time_range(
        self,
        time_range: TimeRange,
        reference_date: Optional[datetime] = None,
        max_date: Optional[str] = None
    ) -> Tuple[str, str]:
        """解析 TimeRange 为具体日期范围（委托给 DateParser）"""
        return self.parser.calculate_date_range(
            time_range, reference_date, max_date
        )
    
    # ===== 日期格式检测功能 =====
    def detect_field_date_format(
        self,
        sample_values: List[str],
        confidence_threshold: float = 0.7
    ) -> DateFormatType:
        """检测字段的日期格式（委托给 DateFormatDetector）"""
        return self.format_detector.detect_format(
            sample_values, confidence_threshold
        )
    
    def convert_date_to_iso(
        self,
        date_value: str,
        source_format: DateFormatType
    ) -> Optional[str]:
        """转换日期为 ISO 格式（委托给 DateFormatDetector）"""
        return self.format_detector.convert_to_iso(
            date_value, source_format
        )
    
    def get_format_info(self, format_type: DateFormatType) -> Dict[str, str]:
        """获取格式信息（委托给 DateFormatDetector）"""
        return self.format_detector.get_format_info(format_type)
    
    # ===== 缓存管理 =====
    def cache_field_format(self, field_name: str, format_type: DateFormatType):
        """缓存字段的日期格式"""
        self.field_formats_cache[field_name] = format_type
    
    def get_cached_field_format(self, field_name: str) -> Optional[DateFormatType]:
        """获取缓存的字段日期格式"""
        return self.field_formats_cache.get(field_name)
```

**集成到 MetadataManager**:

```python
class MetadataManager:
    def __init__(self, date_manager: DateManager):
        """使用 DateManager 统一管理日期功能"""
        self.date_manager = date_manager
    
    def _detect_date_field_formats(self) -> Dict[str, DateFormatType]:
        """
        检测数据源中日期字段的格式
        
        Returns:
            字段名到日期格式类型的映射
        """
        field_formats = {}
        
        for field in self.metadata.fields:
            # DATE 类型字段使用 ISO 格式
            if field.dataType == "DATE":
                field_formats[field.name] = DateFormatType.ISO_DATE
                self.date_manager.cache_field_format(field.name, DateFormatType.ISO_DATE)
            
            # STRING 类型字段检测日期格式
            elif field.dataType == "STRING" and field.sample_values:
                detected_format = self.date_manager.detect_field_date_format(
                    field.sample_values,
                    confidence_threshold=0.7
                )
                
                if detected_format != DateFormatType.UNKNOWN:
                    field_formats[field.name] = detected_format
                    self.date_manager.cache_field_format(field.name, detected_format)
                    logger.info(f"✓ STRING 字段 {field.name} 检测为日期格式: {detected_format.value}")
        
        return field_formats
    
    def get_field_date_format(self, field_name: str) -> Optional[DateFormatType]:
        """获取字段的日期格式（从 DateManager 缓存）"""
        return self.date_manager.get_cached_field_format(field_name)
```

**集成到 QueryBuilder**:

```python
class QueryBuilder:
    def __init__(self, date_manager: DateManager):
        """使用 DateManager 统一管理日期功能"""
        self.date_manager = date_manager
    
    def _build_date_filter_for_string_field(
        self,
        field_name: str,
        start_date: str,
        end_date: str,
        date_format: DateFormatType
    ) -> VizQLFilter:
        """
        为 STRING 类型日期字段构建过滤器
        
        策略：
        1. 创建 DATEPARSE 计算字段
        2. 使用 QuantitativeDateFilter 过滤转换后的日期
        """
        # 获取格式信息
        format_info = self.date_manager.get_format_info(date_format)
        
        # 创建 DATEPARSE 计算字段
        dateparse_field = CalculationField(
            fieldCaption=f"{field_name}_parsed",
            calculation=f"DATEPARSE('{format_info['pattern']}', [{field_name}])"
        )
        
        # 使用 QuantitativeDateFilter
        return QuantitativeDateFilter(
            field=dateparse_field,
            filterType="QUANTITATIVE_DATE",
            minDate=start_date,  # ISO 格式
            maxDate=end_date     # ISO 格式
        )
```

## 数据模型

### Intent 模型层次结构

```
Intent 模型（intent.py）
├── DimensionIntent（维度意图）
├── MeasureIntent（度量意图）
├── DateFieldIntent（日期字段意图）
├── TableCalcIntent（表计算意图）★ 新增
├── DateFilterIntent（日期过滤意图）
├── FilterIntent（非日期过滤意图）
└── TopNIntent（TopN 意图）
```

### VizQL 模型层次结构

```
VizQLField（vizql_types.py）
├── BasicField（基础字段）
├── FunctionField（函数字段）
├── CalculationField（计算字段）
└── TableCalcField（表计算字段）★ 新增
    └── tableCalculation: TableCalcSpecification
        ├── RunningTotalTableCalcSpecification
        ├── MovingTableCalcSpecification
        ├── RankTableCalcSpecification
        ├── PercentileTableCalcSpecification
        ├── PercentOfTotalTableCalcSpecification
        ├── PercentFromTableCalcSpecification
        ├── PercentDifferenceFromTableCalcSpecification
        ├── DifferenceFromTableCalcSpecification
        ├── CustomTableCalcSpecification
        └── NestedTableCalcSpecification
```

### 表计算类型映射

| 用户关键词 | table_calc_type | TableCalcSpecification |
|-----------|----------------|----------------------|
| "累计"、"running total" | RUNNING_TOTAL | RunningTotalTableCalcSpecification |
| "移动平均"、"moving average" | MOVING_CALCULATION | MovingTableCalcSpecification |
| "排名"、"rank" | RANK | RankTableCalcSpecification |
| "百分比"、"percent of total" | PERCENT_OF_TOTAL | PercentOfTotalTableCalcSpecification |

## 正确性属性

*属性是系统在所有有效执行中应该保持为真的特征或行为——本质上是关于系统应该做什么的形式化陈述。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*


基于需求分析，以下是系统必须满足的正确性属性：

### 属性 1: TableCalcIntent 序列化往返一致性
*对于任何*有效的 TableCalcIntent 对象，序列化后再反序列化应该产生等价的对象
**验证需求: 7.2, 15.8**

### 属性 2: TableCalcField 序列化往返一致性
*对于任何*有效的 TableCalcField 对象，序列化后再反序列化应该产生等价的对象
**验证需求: 7.1, 15.1**

### 属性 3: TableCalcIntent 到 TableCalcField 转换正确性
*对于任何*有效的 TableCalcIntent，QueryBuilder 生成的 TableCalcField 应该包含正确的 tableCalculation 规范
**验证需求: 3.4, 3.5, 15.9**

### 属性 4: 表计算类型完整性
*对于任何*10 种表计算类型，系统应该能够正确创建相应的 TableCalcSpecification
**验证需求: 15.3**

### 属性 5: 工具封装业务逻辑保持
*对于任何*组件输入，工具封装前后的输出应该保持一致
**验证需求: 16.4, 16.5**

### 属性 6: 中间件配置完整性
*对于任何*模型配置，DeepAgent 应该包含所有必需的中间件（6 个），且不包含 SubAgentMiddleware
**验证需求: 6.1, 6.2, 6.3**

### 属性 7: StateGraph 节点顺序保持
*对于任何*工作流执行，节点执行顺序应该遵循 Boost → Understanding → Planning → Execute → Insight → Replanner
**验证需求: 17.1, 17.2**

### 属性 8: Boost 节点条件跳过
*对于任何*boost_question=False 的情况，系统应该跳过 Boost 节点
**验证需求: 17.4**

### 属性 9: 重规划循环路由
*对于任何*should_replan=True 的情况，系统应该从 Replanner 路由回 Understanding 节点
**验证需求: 17.5**

### 属性 10: VizQLQuery 结构完整性
*对于任何*有效的 VizQLQuery 对象，必须包含至少一个字段，且所有字段都是有效的 VizQLField
**验证需求: 3.7, 14.1**

### 属性 11: 表计算关键词识别正确性
*对于任何*包含表计算关键词的用户问题，Planning Agent 应该生成相应的 TableCalcIntent
**验证需求: 15.10, 15.11, 15.12, 15.13**

### 属性 12: Pydantic 模型验证正确性
*对于任何*无效的字段或过滤器定义，Pydantic 验证应该抛出 ValidationError
**验证需求: 19.5, 19.6**

### 属性 13: 日期格式检测一致性
*对于任何*具有相同格式的日期样本集，多次检测应该返回相同的格式类型
**验证需求: 24.2, 24.3**

### 属性 14: 日期格式转换往返一致性
*对于任何*有效的 ISO 日期，转换为其他格式后再转换回 ISO 格式应该保持不变
**验证需求: 24.5, 24.8**

### 属性 15: 美式/欧式格式区分正确性
*对于任何*包含明显区分标志（月份>12或日期>12）的样本集，格式检测应该正确区分美式和欧式格式
**验证需求: 24.4**

### 属性 16: STRING 日期字段 DATEPARSE 生成正确性
*对于任何*STRING 类型的日期字段，QueryBuilder 应该生成包含正确 DATEPARSE 公式的 CalculationField
**验证需求: 24.6**

## 错误处理

### 错误分类

系统将错误分为以下几类：

1. **网络错误** (NetworkError)
   - 连接超时
   - DNS 解析失败
   - 连接被拒绝
   - 处理策略：重试 + 回退到缓存

2. **认证错误** (AuthenticationError)
   - 401 Unauthorized
   - 403 Forbidden
   - Token 过期
   - 处理策略：不重试，返回明确错误信息

3. **验证错误** (ValidationError)
   - 400 Bad Request
   - Pydantic 验证失败
   - 字段类型不匹配
   - 处理策略：不重试，返回字段级错误信息

4. **服务器错误** (ServerError)
   - 500 Internal Server Error
   - 502 Bad Gateway
   - 503 Service Unavailable
   - 处理策略：指数退避重试

5. **速率限制错误** (RateLimitError)
   - 429 Too Many Requests
   - 处理策略：指数退避重试，遵守 Retry-After 头

6. **数据错误** (DataError)
   - 数据源不存在
   - 字段不存在
   - 表计算配置无效
   - 处理策略：不重试，返回明确错误信息

### 错误处理流程

```
API 调用
    ↓
成功？
    ├── 是 → Pydantic 验证响应
    │         ├── 成功 → 返回结果
    │         └── 失败 → ValidationError
    │
    └── 否 → 解析错误 → 错误类型？
              ├── 网络错误 → 重试次数 < 3？
              │              ├── 是 → 等待 + 重试 → API 调用
              │              └── 否 → 返回错误 + 缓存数据
              │
              ├── 认证错误 → 返回认证错误
              ├── 验证错误 → 返回验证错误
              │
              ├── 服务器错误 → 重试次数 < 3？
              │                ├── 是 → 指数退避 + 重试 → API 调用
              │                └── 否 → 返回服务器错误
              │
              ├── 速率限制 → 重试次数 < 3？
              │              ├── 是 → 遵守 Retry-After + 重试 → API 调用
              │              └── 否 → 返回速率限制错误
              │
              └── 数据错误 → 返回数据错误
```

### 错误处理实现

```python
class ErrorHandler:
    """统一错误处理器"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
    
    def handle_error(
        self,
        error: Exception,
        attempt: int
    ) -> Tuple[bool, Optional[float]]:
        """
        处理错误
        
        Returns:
            (should_retry, delay_seconds)
        """
        error_type = self._classify_error(error)
        
        # 不可重试的错误
        if error_type in [ErrorType.AUTH, ErrorType.VALIDATION, ErrorType.DATA]:
            return False, None
        
        # 达到最大重试次数
        if attempt >= self.max_retries:
            return False, None
        
        # 速率限制：遵守 Retry-After
        if error_type == ErrorType.RATE_LIMIT:
            delay = self._get_retry_after(error)
            return True, delay
        
        # 网络或服务器错误：指数退避
        if error_type in [ErrorType.NETWORK, ErrorType.SERVER]:
            delay = self.base_delay * (2 ** attempt)
            return True, delay
        
        return False, None
```

## 测试策略

### 双重测试方法

系统采用**单元测试**和**基于属性的测试**相结合的方法：

- **单元测试**：验证特定示例、边缘情况和错误条件
- **基于属性的测试**：验证应该在所有输入上成立的通用属性

两者互补，共同提供全面的测试覆盖：单元测试捕获具体的 bug，属性测试验证通用的正确性。

### 单元测试

单元测试覆盖以下方面：

1. **TableCalcIntent 测试**
   - 各种表计算类型的创建
   - 序列化和反序列化
   - 字段验证

2. **TableCalcField 测试**
   - TableCalcSpecification 创建
   - 嵌套表计算
   - 序列化和反序列化

3. **QueryBuilder 测试**
   - TableCalcIntent → TableCalcField 转换
   - 各种表计算类型的构建
   - 错误处理

4. **工具封装测试**
   - @tool 装饰器
   - docstring 完整性
   - 参数验证

5. **中间件配置测试**
   - Claude 模型启用 AnthropicPromptCaching
   - 非 Claude 模型不启用
   - 6 个必需中间件都被配置
   - SubAgentMiddleware 被排除

6. **StateGraph 测试**
   - 节点执行顺序
   - boost_question=False 时跳过 Boost
   - should_replan=True 时路由回 Understanding

### 基于属性的测试

使用 **Hypothesis** 库进行基于属性的测试。

#### 测试配置

```python
from hypothesis import given, settings, strategies as st
import pytest

# 配置：每个属性测试运行 100 次
@settings(max_examples=100)
```

#### 属性测试示例

```python
# 属性 1: TableCalcIntent 序列化往返一致性
@given(table_calc_intent=table_calc_intent_strategy())
@settings(max_examples=100)
def test_table_calc_intent_serialization_roundtrip(table_calc_intent: TableCalcIntent):
    """
    Feature: vizql-api-migration, Property 1: TableCalcIntent 序列化往返一致性
    
    对于任何有效的 TableCalcIntent 对象，序列化后再反序列化应该产生等价的对象
    """
    # 序列化
    json_str = table_calc_intent.model_dump_json()
    
    # 反序列化
    restored = TableCalcIntent.model_validate_json(json_str)
    
    # 验证等价性
    assert restored == table_calc_intent
    assert restored.table_calc_type == table_calc_intent.table_calc_type
    assert restored.technical_field == table_calc_intent.technical_field


# 属性 3: TableCalcIntent 到 TableCalcField 转换正确性
@given(table_calc_intent=table_calc_intent_strategy())
@settings(max_examples=100)
def test_table_calc_intent_to_field_conversion(table_calc_intent: TableCalcIntent):
    """
    Feature: vizql-api-migration, Property 3: TableCalcIntent 到 TableCalcField 转换正确性
    
    对于任何有效的 TableCalcIntent，QueryBuilder 生成的 TableCalcField 应该包含正确的 tableCalculation 规范
    """
    query_builder = QueryBuilder()
    
    # 转换
    field = query_builder.build_table_calc_field(table_calc_intent)
    
    # 验证
    assert isinstance(field, TableCalcField)
    assert field.fieldCaption == table_calc_intent.technical_field
    assert field.tableCalculation.tableCalcType == table_calc_intent.table_calc_type


# 属性 11: 表计算关键词识别正确性
@given(
    question=st.text(min_size=10, max_size=100),
    keyword=st.sampled_from(["累计", "running total", "排名", "rank", "移动平均", "moving average"])
)
@settings(max_examples=100)
def test_table_calc_keyword_recognition(question: str, keyword: str):
    """
    Feature: vizql-api-migration, Property 11: 表计算关键词识别正确性
    
    对于任何包含表计算关键词的用户问题，Planning Agent 应该生成相应的 TableCalcIntent
    """
    # 构造包含关键词的问题
    question_with_keyword = f"{question} {keyword}"
    
    # Planning Agent 处理
    planning_agent = PlanningAgent()
    intents = planning_agent.generate_intents(question_with_keyword)
    
    # 验证至少有一个 TableCalcIntent
    table_calc_intents = [i for i in intents if isinstance(i, TableCalcIntent)]
    assert len(table_calc_intents) > 0
```

#### 测试数据生成策略

```python
from hypothesis import strategies as st

# TableCalcIntent 生成策略
@st.composite
def table_calc_intent_strategy(draw):
    calc_type = draw(st.sampled_from([
        "RUNNING_TOTAL",
        "MOVING_CALCULATION",
        "RANK",
        "PERCENT_OF_TOTAL"
    ]))
    
    if calc_type == "RUNNING_TOTAL":
        config = {
            "aggregation": draw(st.sampled_from(["SUM", "AVG", "COUNT"])),
            "dimensions": draw(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=3))
        }
    elif calc_type == "MOVING_CALCULATION":
        config = {
            "aggregation": draw(st.sampled_from(["SUM", "AVG"])),
            "dimensions": draw(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=3)),
            "previous": draw(st.integers(min_value=0, max_value=10)),
            "next": draw(st.integers(min_value=0, max_value=10)),
            "includeCurrent": draw(st.booleans())
        }
    elif calc_type == "RANK":
        config = {
            "dimensions": draw(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=3)),
            "rankType": draw(st.sampled_from(["COMPETITION", "DENSE", "UNIQUE"])),
            "direction": draw(st.sampled_from(["ASC", "DESC"]))
        }
    else:  # PERCENT_OF_TOTAL
        config = {
            "dimensions": draw(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=3))
        }
    
    return TableCalcIntent(
        business_term=draw(st.text(min_size=1, max_size=50)),
        technical_field=draw(st.text(min_size=1, max_size=50)),
        table_calc_type=calc_type,
        table_calc_config=config
    )


# TableCalcField 生成策略
@st.composite
def table_calc_field_strategy(draw):
    calc_type = draw(st.sampled_from([
        "RUNNING_TOTAL",
        "MOVING_CALCULATION",
        "RANK"
    ]))
    
    dimensions = draw(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=3))
    
    if calc_type == "RUNNING_TOTAL":
        spec = RunningTotalTableCalcSpecification(
            tableCalcType="RUNNING_TOTAL",
            aggregation=draw(st.sampled_from([FunctionEnum.SUM, FunctionEnum.AVG])),
            dimensions=dimensions
        )
    elif calc_type == "MOVING_CALCULATION":
        spec = MovingTableCalcSpecification(
            tableCalcType="MOVING_CALCULATION",
            aggregation=draw(st.sampled_from([FunctionEnum.SUM, FunctionEnum.AVG])),
            dimensions=dimensions,
            previous=draw(st.integers(min_value=0, max_value=10)),
            next=draw(st.integers(min_value=0, max_value=10)),
            includeCurrent=draw(st.booleans())
        )
    else:  # RANK
        spec = RankTableCalcSpecification(
            tableCalcType="RANK",
            dimensions=dimensions,
            rankType=draw(st.sampled_from(["COMPETITION", "DENSE", "UNIQUE"])),
            direction=draw(st.sampled_from(["ASC", "DESC"]))
        )
    
    return TableCalcField(
        fieldCaption=draw(st.text(min_size=1, max_size=50)),
        tableCalculation=spec
    )
```

### 测试覆盖目标

- **单元测试覆盖率**: ≥ 80%
- **属性测试数量**: 每个正确性属性至少一个测试（12 个属性）
- **集成测试**: 覆盖所有主要用户流程
- **表计算测试**: 覆盖所有 10 种表计算类型

## 实施路径

### 阶段 1: 数据模型扩展（1-2 天）

**目标**: 添加表计算相关的数据模型

**任务**:
1. 在 `vizql_types.py` 中添加 TableCalcSpecification 及其子类
2. 添加 TableCalcField 类
3. 更新 VizQLField 联合类型
4. 在 `intent.py` 中添加 TableCalcIntent 类
5. 编写单元测试验证模型

**验证**:
- Pydantic 模型验证通过
- 序列化/反序列化测试通过
- 所有 10 种表计算类型都能正确创建

### 阶段 2: QueryBuilder 扩展（1-2 天）

**目标**: 扩展 QueryBuilder 以支持表计算

**任务**:
1. 添加 `build_table_calc_field()` 方法
2. 更新 `build_field()` 方法以处理 TableCalcIntent
3. 实现各种表计算类型的构建逻辑
4. 编写单元测试

**验证**:
- TableCalcIntent → TableCalcField 转换正确
- 所有表计算类型都能正确构建
- 单元测试通过

### 阶段 3: VizQL 客户端增强（1 天）

**目标**: 增强 VizQL 客户端以支持 Pydantic 模型

**任务**:
1. 更新 `query_vds()` 函数以接受 Pydantic 模型
2. 添加请求验证
3. 添加响应验证
4. 添加统一错误处理
5. 编写单元测试

**验证**:
- Pydantic 模型输入正常工作
- 请求和响应验证正确
- 错误处理正确

### 阶段 4: Planning Agent 扩展（2-3 天）

**目标**: 扩展 Planning Agent 以识别表计算需求

**任务**:
1. 添加表计算关键词识别逻辑
2. 实现 TableCalcIntent 生成
3. 更新系统提示词
4. 编写单元测试

**验证**:
- 关键词识别正确
- TableCalcIntent 生成正确
- 单元测试通过

### 阶段 5: 工具封装（1-2 天）

**目标**: 将组件封装为 LangChain 工具

**任务**:
1. 创建 8 个工具函数
2. 添加 @tool 装饰器
3. 编写完整的 docstring
4. 编写单元测试

**验证**:
- 所有工具都有完整的 docstring
- 工具调用正常工作
- 业务逻辑保持不变

### 阶段 6: StateGraph 适配（1 天）

**目标**: 修改 StateGraph 以使用 DeepAgent

**任务**:
1. 更新 `create_vizql_workflow()` 函数
2. 使用 `create_tableau_deep_agent()` 创建 Agent
3. 传递 8 个工具
4. 保持现有节点逻辑
5. 编写单元测试

**验证**:
- StateGraph 正常工作
- 节点执行顺序正确
- 工具调用正常

### 阶段 7: 集成测试（2-3 天）

**目标**: 运行所有测试，确保系统正常工作

**任务**:
1. 运行所有单元测试
2. 运行所有属性测试（Hypothesis）
3. 运行集成测试
4. 测试表计算功能
5. 修复发现的问题

**验证**:
- 所有测试通过
- 表计算功能正常
- 性能满足要求

### 阶段 8: 文档和部署（1 天）

**目标**: 更新文档，准备部署

**任务**:
1. 更新 API 文档
2. 更新架构文档
3. 编写迁移指南
4. 准备发布说明

**验证**:
- 文档完整
- 迁移指南清晰
- 准备发布

## 编码规范和最佳实践

### Pydantic 数据模型编写规范

**必须遵守的规则**（参考 `docs/PROMPT_AND_MODEL_GUIDE.md`）：

#### 1. 模型配置
```python
class YourModel(BaseModel):
    """模型文档字符串 - 说明模型用途"""
    model_config = ConfigDict(extra="forbid")  # 必须包含！
```

#### 2. 字段定义格式
```python
field_name: FieldType = Field(
    description="""Brief one-line description.

Usage:
- When to include this field
- When to set it to null/empty

Values: What values are valid
- Value 1: explanation
- Value 2: explanation"""
)
```

#### 3. 字段类型规范
- 基础类型：`str`, `int`, `float`, `bool`
- 可选类型：`Optional[str]` + `default=None`
- 列表类型：`List[str]` + `default_factory=list`（不要用 `default=[]`）
- 枚举类型：`Literal["a", "b"]` 或自定义 Enum
- 嵌套模型：其他 Pydantic 模型

#### 4. 字段约束
```python
# 数值范围
confidence: float = Field(ge=0, le=1, description="...")

# 列表最小长度
items: List[str] = Field(min_length=1, description="...")

# 字符串模式
task_id: str = Field(pattern=r"^q\d+$", description="...")
```

### Prompt 模板编写规范

**必须遵守的规则**（参考 `docs/PROMPT_AND_MODEL_GUIDE.md`）：

#### 1. 语言规则
- ✅ **全英文编写** - LLM 对英文理解更准确
- ❌ **禁止中英文混杂** - 避免编码问题和不一致

#### 2. 4段式结构
```python
class YourPrompt(VizQLPrompt):
    def get_role(self) -> str:
        """定义 LLM 的角色和专长（2-3句话）"""
        
    def get_task(self) -> str:
        """定义任务和处理流程（使用箭头 →）"""
        
    def get_specific_domain_knowledge(self) -> str:
        """提供领域知识和思考步骤（Think step by step）"""
        
    def get_constraints(self) -> str:
        """定义约束条件（使用 DO/ENSURE，避免 DON'T）"""
```

#### 3. Constraints 编写规范
```python
# ✅ 正确：使用正面指令
"""DO:
- Select matched_field from provided candidates only
- Match field role (dimension vs measure)
- Provide confidence score between 0 and 1

ENSURE:
- Every mapping references an actual candidate field
- Confidence reflects true certainty level"""

# ❌ 错误：使用负面约束
"""MUST NOT: invent fields, ignore role mismatch"""
```

#### 4. Temperature 配置规范
根据任务类型使用不同的 temperature（参考 `src/config/model_config.py`）：

| 任务类型 | Temperature | 原因 |
|---------|-------------|------|
| Field Mapping | 0.0 | 确定性任务，单一正确答案 |
| Understanding | 0.1 | 需要一致性，允许少量变化 |
| Task Planner | 0.1 | 需要一致的规划 |
| Insight | 0.7 | 需要创意和多样化 |
| Boost | 0.2 | 平衡理解和扩展 |
| Replanner | 0.2 | 平衡分析和方案 |

#### 5. 示例处理规范
- ✅ **在 Pydantic 模型中定义示例**（使用 `json_schema_extra`）
- ✅ **从元数据动态生成示例**
- ✅ **利用 RAG 候选作为 Few-shot**
- ❌ **不要在 Prompt 模板中硬编码示例**

### 关键原则

1. **一致性** - 与项目其他模块保持一致
2. **清晰性** - 描述清晰，易于理解
3. **完整性** - 包含所有必要信息
4. **简洁性** - 避免冗余和过度设计
5. **可维护性** - 易于修改和扩展

## 总结

本设计文档描述了 VizQL API 迁移和 DeepAgents 集成的完整技术方案。主要特点：

1. **表计算支持**：添加 TableCalcField 和 TableCalcIntent，支持 10 种表计算类型
2. **DeepAgents 架构**：使用 6 个中间件增强系统能力
3. **工具封装**：将 8 个组件封装为 LangChain 工具
4. **类型安全**：使用 Pydantic v2 模型确保类型安全
5. **直接升级**：一次性完成迁移，无需功能标志
6. **复用现有实现**：使用 requests 库和现有认证
7. **遵守编码规范**：严格遵守 Pydantic 和 Prompt 编写规范

预计实施时间：10-15 天
