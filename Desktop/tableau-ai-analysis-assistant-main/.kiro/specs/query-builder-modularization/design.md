# Design Document

## Overview

本设计文档描述了查询构建器模块化和元数据模型化的技术实现方案。主要包括：
1. 创建标准的Metadata Pydantic模型
2. 重构MetadataManager和StoreManager以支持模型对象
3. 将query_builder.py拆分为多个职责清晰的模块
4. 实现Intent模型到VizQL模型的转换器
5. 适配相关Agent以使用Metadata模型

核心设计理念：
- 任务规划Agent输出Intent模型（中间层）
- QueryBuilder负责将Intent模型转换为VizQL模型（执行层）
- 转换器模块职责单一，易于测试和维护

## Architecture

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     Tableau API                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              MetadataManager (增强)                          │
│  - 获取元数据并转换为Metadata模型                            │
│  - 调用维度层级推断Agent                                      │
│  - 查询valid_max_date                                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              StoreManager (适配)                             │
│  - 序列化/反序列化Metadata模型                               │
│  - 缓存管理（TTL）                                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Metadata Model                                  │
│  - FieldMetadata: 字段元数据                                 │
│  - Metadata: 数据源元数据                                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│         Task Planning Agent (输出Intent模型)                 │
│  - DimensionIntent                                           │
│  - MeasureIntent                                             │
│  - DateFieldIntent                                           │
│  - DateFilterIntent                                          │
│  - FilterIntent                                              │
│  - TopNIntent                                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              QueryBuilder (模块化)                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  IntentConverter                                      │  │
│  │  - DimensionIntent → BasicField/FunctionField        │  │
│  │  - MeasureIntent → FunctionField                     │  │
│  │  - DateFieldIntent → BasicField/FunctionField        │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  DateFilterConverter                                  │  │
│  │  - DateFilterIntent → RelativeDateFilter             │  │
│  │  - DateFilterIntent → QuantitativeDateFilter         │  │
│  │  - 日期格式检测和DATEPARSE生成                        │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  FilterConverter                                      │  │
│  │  - FilterIntent → SetFilter/QuantitativeFilter/Match │  │
│  │  - TopNIntent → TopNFilter                           │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  QueryBuilder                                         │  │
│  │  - 主协调器                                           │  │
│  │  - 组装VizQLQuery                                     │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              VizQLQuery (输出)                               │
│  - fields: List[VizQLField]                                  │
│  - filters: List[VizQLFilter]                                │
└─────────────────────────────────────────────────────────────┘
```


## Data Models

### FieldMetadata Model

字段元数据模型，描述单个字段的详细信息。

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Literal

class FieldMetadata(BaseModel):
    """字段元数据模型"""
    
    # 基本信息
    name: str = Field(..., description="字段名称")
    fieldCaption: str = Field(..., description="字段显示名称")
    role: Literal["dimension", "measure"] = Field(..., description="字段角色")
    dataType: str = Field(..., description="数据类型：DATE/DATETIME/STRING/INTEGER/REAL等")
    
    # 可选信息
    dataCategory: Optional[str] = Field(None, description="数据类别")
    aggregation: Optional[str] = Field(None, description="聚合方式")
    formula: Optional[str] = Field(None, description="计算公式")
    description: Optional[str] = Field(None, description="字段描述")
    
    # 统计信息
    sample_values: Optional[List[str]] = Field(None, description="样本值")
    unique_count: Optional[int] = Field(None, description="唯一值数量")
    
    # 维度层级推断结果（由dimension_hierarchy_agent添加）
    category: Optional[str] = Field(None, description="维度类别（地理/时间/产品/客户/组织/财务/其他）")
    category_detail: Optional[str] = Field(None, description="详细类别描述")
    level: Optional[int] = Field(None, description="层级级别（1-5）")
    granularity: Optional[str] = Field(None, description="粒度描述")
    parent_dimension: Optional[str] = Field(None, description="父维度字段名")
    child_dimension: Optional[str] = Field(None, description="子维度字段名")
    
    # 日期字段特有
    valid_max_date: Optional[str] = Field(None, description="有效最大日期（用于日期筛选）")
    
    class Config:
        frozen = False  # 允许修改（用于添加维度层级推断结果和valid_max_date）
```


### Metadata Model

数据源元数据模型，包含所有字段信息和辅助方法。

```python
from typing import Dict, List, Optional

class Metadata(BaseModel):
    """数据源元数据模型"""
    
    # 数据源信息
    datasource_luid: str = Field(..., description="数据源LUID")
    datasource_name: str = Field(..., description="数据源名称")
    datasource_description: Optional[str] = Field(None, description="数据源描述")
    datasource_owner: Optional[str] = Field(None, description="数据源所有者")
    
    # 字段信息
    fields: List[FieldMetadata] = Field(..., description="字段列表")
    field_count: int = Field(..., description="字段数量")
    
    # 维度层级（可选）
    dimension_hierarchy: Optional[Dict] = Field(None, description="维度层级推断结果")
    
    # 原始响应（调试用）
    raw_response: Optional[Dict] = Field(None, description="原始GraphQL响应")
    
    def get_field(self, field_name: str) -> Optional[FieldMetadata]:
        """根据字段名查询字段元数据"""
        for field in self.fields:
            if field.name == field_name or field.fieldCaption == field_name:
                return field
        return None
    
    def get_date_fields(self) -> List[FieldMetadata]:
        """获取所有日期字段（包括STRING类型的日期字段）"""
        date_fields = []
        for field in self.fields:
            # 1. 原生DATE/DATETIME类型
            if field.dataType in ("DATE", "DATETIME"):
                date_fields.append(field)
            # 2. 通过维度推断识别的时间类别（STRING类型但category为时间）
            elif hasattr(field, 'category') and field.category and '时间' in field.category:
                date_fields.append(field)
        return date_fields
    
    def get_dimensions(self) -> List[FieldMetadata]:
        """获取所有维度字段"""
        return [field for field in self.fields if field.role == "dimension"]
    
    def get_measures(self) -> List[FieldMetadata]:
        """获取所有度量字段"""
        return [field for field in self.fields if field.role == "measure"]
    
    class Config:
        frozen = False  # 允许修改（用于添加dimension_hierarchy）
```


## Components and Interfaces

### MetadataManager (增强)

**职责：** 获取元数据并转换为Metadata模型对象

**关键变更：**
1. `get_metadata()` 返回 `Metadata` 对象而非字典
2. `get_metadata_async()` 返回 `Metadata` 对象而非字典
3. 将Tableau API响应转换为Metadata模型

**接口：**
```python
class MetadataManager:
    def __init__(self, runtime: Runtime[VizQLContext]):
        self.runtime = runtime
        self.store_manager = StoreManager(runtime.store)
    
    def get_metadata(
        self,
        use_cache: bool = True,
        enhance: bool = False
    ) -> Metadata:
        """获取数据源元数据（同步版本）"""
        pass
    
    async def get_metadata_async(
        self,
        use_cache: bool = True,
        enhance: bool = False
    ) -> Metadata:
        """获取数据源元数据（异步版本）"""
        pass
    
    def _convert_to_metadata_model(
        self,
        raw_metadata: Dict[str, Any]
    ) -> Metadata:
        """将原始元数据字典转换为Metadata模型"""
        pass
```


### StoreManager (适配)

**职责：** 处理Metadata模型对象的序列化和反序列化

**关键变更：**
1. `get_metadata()` 返回 `Metadata` 对象或 `None`
2. `put_metadata()` 接收 `Metadata` 对象
3. 使用Pydantic的序列化/反序列化方法

**接口：**
```python
class StoreManager:
    def get_metadata(self, datasource_luid: str) -> Optional[Metadata]:
        """从Store获取元数据"""
        namespace = ("metadata", datasource_luid)
        item = self.store.get(namespace, "data")
        
        if item and item.value:
            # 反序列化为Metadata对象
            return Metadata.model_validate(item.value)
        return None
    
    def put_metadata(self, datasource_luid: str, metadata: Metadata) -> None:
        """将元数据存入Store"""
        namespace = ("metadata", datasource_luid)
        
        # 序列化为字典
        metadata_dict = metadata.model_dump()
        
        self.store.put(
            namespace,
            "data",
            metadata_dict,
            index=False
        )
```


### IntentConverter

**职责：** 将Intent模型转换为VizQLField对象

**关键功能：**
1. 转换DimensionIntent为BasicField或FunctionField
2. 转换MeasureIntent为FunctionField
3. 转换DateFieldIntent为BasicField或FunctionField
4. 处理排序信息

**接口：**
```python
class IntentConverter:
    def __init__(self, metadata: Metadata):
        self.metadata = metadata
    
    def convert_dimension_intent(self, intent: DimensionIntent) -> VizQLField:
        """
        转换维度意图为VizQLField
        
        规则：
        - 如果有aggregation（COUNT、COUNTD等），生成FunctionField
        - 否则生成BasicField
        """
        if intent.aggregation:
            return FunctionField(
                fieldCaption=intent.technical_field,
                function=FunctionEnum[intent.aggregation],
                sortDirection=intent.sort_direction,
                sortPriority=intent.sort_priority
            )
        else:
            return BasicField(
                fieldCaption=intent.technical_field,
                sortDirection=intent.sort_direction,
                sortPriority=intent.sort_priority
            )
    
    def convert_measure_intent(self, intent: MeasureIntent) -> FunctionField:
        """
        转换度量意图为FunctionField
        
        规则：
        - 度量必须有聚合函数，生成FunctionField
        """
        return FunctionField(
            fieldCaption=intent.technical_field,
            function=FunctionEnum[intent.aggregation],
            sortDirection=intent.sort_direction,
            sortPriority=intent.sort_priority
        )
    
    def convert_date_field_intent(self, intent: DateFieldIntent) -> VizQLField:
        """
        转换日期字段意图为VizQLField
        
        规则：
        - 如果有date_function（YEAR、MONTH等），生成FunctionField
        - 否则生成BasicField
        """
        if intent.date_function:
            return FunctionField(
                fieldCaption=intent.technical_field,
                function=FunctionEnum[intent.date_function],
                sortDirection=intent.sort_direction,
                sortPriority=intent.sort_priority
            )
        else:
            return BasicField(
                fieldCaption=intent.technical_field,
                sortDirection=intent.sort_direction,
                sortPriority=intent.sort_priority
            )
```


### DateFilterConverter

**职责：** 将DateFilterIntent转换为VizQL日期筛选器

**关键功能：**
1. 根据field_data_type选择处理策略
2. 对STRING类型日期字段进行格式检测和DATEPARSE转换
3. 使用DateCalculator计算日期范围
4. 处理节假日日期计算

**接口：**
```python
class DateFilterConverter:
    def __init__(
        self,
        metadata: Metadata,
        anchor_date: Optional[datetime] = None,
        week_start_day: int = 0
    ):
        self.metadata = metadata
        self.anchor_date = anchor_date
        self.week_start_day = week_start_day
        self.date_calculator = DateCalculator(week_start_day=week_start_day)
    
    def convert(
        self,
        intent: DateFilterIntent
    ) -> Tuple[Optional[VizQLFilter], Optional[CalculationField]]:
        """
        转换日期筛选意图为VizQL筛选器
        
        返回：
        - VizQL筛选器（RelativeDateFilter或QuantitativeDateFilter）
        - DATEPARSE计算字段（如果需要，用于STRING类型日期字段）
        
        规则：
        - DATE/DATETIME + relative → RelativeDateFilter
        - DATE/DATETIME + absolute → QuantitativeDateFilter
        - STRING + any → QuantitativeDateFilter + DATEPARSE字段
        """
        field_meta = self.metadata.get_field(intent.technical_field)
        if not field_meta:
            raise ValueError(f"字段 '{intent.technical_field}' 不存在")
        
        # 根据字段类型选择策略
        if field_meta.dataType in ("DATE", "DATETIME"):
            return self._convert_native_date_field(intent)
        else:
            return self._convert_string_date_field(intent, field_meta)
    
    def _convert_native_date_field(
        self,
        intent: DateFilterIntent
    ) -> Tuple[VizQLFilter, None]:
        """处理原生DATE/DATETIME字段"""
        if intent.time_range.type == "relative":
            return RelativeDateFilter(
                field=FilterField(fieldCaption=intent.technical_field),
                filterType="DATE",
                dateRangeType=intent.time_range.relative_type.upper(),
                periodType=intent.time_range.period_type.upper(),
                rangeN=intent.time_range.range_n,
                anchorDate=self.anchor_date.isoformat() if self.anchor_date else None
            ), None
        else:
            # absolute类型
            return QuantitativeDateFilter(
                field=FilterField(fieldCaption=intent.technical_field),
                filterType="QUANTITATIVE_DATE",
                quantitativeFilterType="RANGE",
                minDate=intent.time_range.start_date,
                maxDate=intent.time_range.end_date
            ), None
    
    def _convert_string_date_field(
        self,
        intent: DateFilterIntent,
        field_meta: FieldMetadata
    ) -> Tuple[VizQLFilter, CalculationField]:
        """处理STRING类型日期字段"""
        # 1. 检测日期格式
        date_format = self.detect_date_format(field_meta.sample_values)
        if not date_format:
            raise ValueError(
                f"无法识别字段 '{intent.technical_field}' 的日期格式。"
                f"样本值: {field_meta.sample_values[:3]}"
            )
        
        # 2. 生成DATEPARSE字段
        dateparse_field = create_dateparse_field(
            intent.technical_field,
            date_format
        )
        
        # 3. 计算日期范围
        anchor = self.anchor_date or field_meta.valid_max_date
        if intent.time_range.type == "relative":
            start_date, end_date = self.date_calculator.calculate_relative_date_range(
                intent.time_range.relative_type,
                intent.time_range.period_type,
                intent.time_range.range_n,
                anchor
            )
        else:
            start_date = intent.time_range.start_date
            end_date = intent.time_range.end_date
        
        # 4. 生成QuantitativeDateFilter
        filter_obj = QuantitativeDateFilter(
            field=FilterField(fieldCaption=dateparse_field.fieldCaption),
            filterType="QUANTITATIVE_DATE",
            quantitativeFilterType="RANGE",
            minDate=start_date,
            maxDate=end_date
        )
        
        return filter_obj, dateparse_field
    
    def detect_date_format(self, sample_values: List[str]) -> Optional[str]:
        """检测日期格式"""
        # 日期格式模式
        patterns = {
            r'^\d{4}-\d{2}-\d{2}$': 'yyyy-MM-dd',
            r'^\d{4}/\d{2}/\d{2}$': 'yyyy/MM/dd',
            r'^\d{2}/\d{2}/\d{4}$': 'dd/MM/yyyy',
            # ... 更多模式
        }
        
        for pattern, format_str in patterns.items():
            if all(re.match(pattern, str(val)) for val in sample_values[:5]):
                return format_str
        
        return None
```


### FilterConverter

**职责：** 将FilterIntent和TopNIntent转换为VizQLFilter

**关键功能：**
1. 转换FilterIntent为SetFilter、QuantitativeNumericalFilter或MatchFilter
2. 转换TopNIntent为TopNFilter

**接口：**
```python
class FilterConverter:
    def __init__(self, metadata: Metadata):
        self.metadata = metadata
    
    def convert_filter_intent(self, intent: FilterIntent) -> VizQLFilter:
        """
        转换筛选意图为VizQL筛选器
        
        规则：
        - filter_type="SET" → SetFilter
        - filter_type="QUANTITATIVE" → QuantitativeNumericalFilter
        - filter_type="MATCH" → MatchFilter
        """
        if intent.filter_type == "SET":
            return SetFilter(
                field=FilterField(fieldCaption=intent.technical_field),
                filterType="SET",
                values=intent.values,
                exclude=intent.exclude or False
            )
        
        elif intent.filter_type == "QUANTITATIVE":
            return QuantitativeNumericalFilter(
                field=FilterField(fieldCaption=intent.technical_field),
                filterType="QUANTITATIVE_NUMERICAL",
                quantitativeFilterType=intent.quantitative_filter_type,
                min=intent.min_value,
                max=intent.max_value,
                includeNulls=intent.include_nulls
            )
        
        elif intent.filter_type == "MATCH":
            kwargs = {}
            if intent.match_type == "startsWith":
                kwargs["startsWith"] = intent.match_value
            elif intent.match_type == "endsWith":
                kwargs["endsWith"] = intent.match_value
            elif intent.match_type == "contains":
                kwargs["contains"] = intent.match_value
            
            return MatchFilter(
                field=FilterField(fieldCaption=intent.technical_field),
                filterType="MATCH",
                exclude=intent.match_exclude or False,
                **kwargs
            )
    
    def convert_topn_intent(self, intent: TopNIntent) -> TopNFilter:
        """转换TopN意图为TopNFilter"""
        return TopNFilter(
            field=FilterField(fieldCaption=intent.technical_field),
            filterType="TOP",
            howMany=intent.n,
            fieldToMeasure=FilterField(fieldCaption=intent.technical_field),
            direction=intent.direction
        )
```


### QueryBuilder (简化)

**职责：** 主协调器，组装VizQLQuery对象

**关键功能：**
1. 初始化各个转换器
2. 接收QuerySubTask对象
3. 使用转换器将Intent模型转换为VizQL模型
4. 组装最终的VizQLQuery对象

**接口：**
```python
class QueryBuilder:
    def __init__(
        self,
        metadata: Metadata,
        anchor_date: Optional[datetime] = None,
        week_start_day: int = 0
    ):
        self.metadata = metadata
        self.anchor_date = anchor_date
        self.week_start_day = week_start_day
        
        # 初始化转换器
        self.intent_converter = IntentConverter(metadata=metadata)
        self.date_filter_converter = DateFilterConverter(
            metadata=metadata,
            anchor_date=anchor_date,
            week_start_day=week_start_day
        )
        self.filter_converter = FilterConverter(metadata=metadata)
    
    def build_query(self, subtask: QuerySubTask) -> VizQLQuery:
        """
        构建VizQL查询
        
        流程：
        1. 转换dimension_intents为VizQLField
        2. 转换measure_intents为VizQLField
        3. 转换date_field_intents为VizQLField
        4. 转换date_filter_intent为VizQL日期筛选器
        5. 转换filter_intents为VizQLFilter
        6. 转换topn_intent为TopNFilter
        7. 组装VizQLQuery
        """
        fields = []
        filters = []
        
        # 1. 转换维度
        for intent in subtask.dimension_intents:
            field = self.intent_converter.convert_dimension_intent(intent)
            fields.append(field)
        
        # 2. 转换度量
        for intent in subtask.measure_intents:
            field = self.intent_converter.convert_measure_intent(intent)
            fields.append(field)
        
        # 3. 转换日期字段
        for intent in subtask.date_field_intents:
            field = self.intent_converter.convert_date_field_intent(intent)
            fields.append(field)
        
        # 4. 转换日期筛选
        if subtask.date_filter_intent:
            filter_obj, dateparse_field = self.date_filter_converter.convert(
                subtask.date_filter_intent
            )
            if dateparse_field:
                fields.append(dateparse_field)
            if filter_obj:
                filters.append(filter_obj)
        
        # 5. 转换非日期筛选
        if subtask.filter_intents:
            for intent in subtask.filter_intents:
                filter_obj = self.filter_converter.convert_filter_intent(intent)
                filters.append(filter_obj)
        
        # 6. 转换TopN
        if subtask.topn_intent:
            filter_obj = self.filter_converter.convert_topn_intent(subtask.topn_intent)
            filters.append(filter_obj)
        
        # 7. 组装查询
        query = VizQLQuery(
            fields=fields,
            filters=filters if filters else None
        )
        
        return query
```


## Error Handling

### Metadata模型验证错误

当创建Metadata或FieldMetadata对象时，如果数据不符合模型定义，Pydantic会抛出ValidationError。

**处理策略：**
```python
from pydantic import ValidationError

try:
    metadata = Metadata(**raw_data)
except ValidationError as e:
    logger.error(f"元数据验证失败: {e}")
    # 记录详细错误信息
    for error in e.errors():
        logger.error(f"字段: {error['loc']}, 错误: {error['msg']}")
    raise RuntimeError("元数据格式不正确") from e
```

### 字段查询错误

当查询不存在的字段时，应提供清晰的错误信息。

**处理策略：**
```python
def get_field_or_raise(self, field_name: str) -> FieldMetadata:
    """查询字段，如果不存在则抛出异常"""
    field = self.metadata.get_field(field_name)
    if not field:
        available_fields = [f.name for f in self.metadata.fields]
        raise ValueError(
            f"字段 '{field_name}' 不存在于元数据中。"
            f"可用字段: {available_fields}"
        )
    return field
```

### 日期格式检测失败

当无法识别STRING类型日期字段的格式时，应提供样本值帮助调试。

**处理策略：**
```python
def detect_date_format_or_raise(
    self,
    field_name: str,
    sample_values: List[str]
) -> str:
    """检测日期格式，如果失败则抛出异常"""
    date_format = self.detect_date_format(sample_values)
    if not date_format:
        raise ValueError(
            f"无法识别字段 '{field_name}' 的日期格式。"
            f"样本值: {sample_values[:3]}"
        )
    return date_format
```


## Testing Strategy

### 单元测试

每个模块都应有独立的单元测试。

**FieldMetadata测试：**
```python
def test_field_metadata_creation():
    field = FieldMetadata(
        name="订单日期",
        fieldCaption="订单日期",
        role="dimension",
        dataType="DATE"
    )
    assert field.name == "订单日期"
    assert field.dataType == "DATE"

def test_field_metadata_validation():
    with pytest.raises(ValidationError):
        FieldMetadata(
            name="test",
            # 缺少必需字段
        )
```

**Metadata测试：**
```python
def test_metadata_get_field():
    metadata = Metadata(
        datasource_luid="test-luid",
        datasource_name="Test DS",
        fields=[
            FieldMetadata(name="field1", fieldCaption="Field 1", role="dimension", dataType="STRING"),
            FieldMetadata(name="field2", fieldCaption="Field 2", role="measure", dataType="REAL")
        ],
        field_count=2
    )
    
    field = metadata.get_field("field1")
    assert field is not None
    assert field.name == "field1"

def test_metadata_get_date_fields():
    metadata = Metadata(...)
    date_fields = metadata.get_date_fields()
    assert len(date_fields) == 1
    assert date_fields[0].dataType == "DATE"
```

**DateFilterHandler测试：**
```python
def test_process_relative_date_filter_for_date_field():
    # DATE类型字段应直接返回RelativeDateFilter
    pass

def test_process_relative_date_filter_for_string_field():
    # STRING类型字段应转换为QuantitativeDateFilter
    pass

def test_detect_date_format():
    handler = DateFilterHandler(...)
    format_str = handler.detect_date_format(["2024-01-01", "2024-01-02"])
    assert format_str == "yyyy-MM-dd"
```


### 集成测试

测试各模块之间的协作。

**QueryBuilder集成测试：**
```python
def test_query_builder_with_date_filter():
    # 创建Metadata对象
    metadata = Metadata(...)
    
    # 创建QueryBuilder
    builder = QueryBuilder(metadata=metadata)
    
    # 创建subtask（包含日期筛选器）
    subtask = SubTask(
        fields=[...],
        filters=[RelativeDateFilter(...)]
    )
    
    # 构建查询
    query = builder.build_query(subtask)
    
    # 验证结果
    assert query.fields is not None
    assert query.filters is not None
```

**MetadataManager集成测试：**
```python
async def test_metadata_manager_returns_model():
    manager = MetadataManager(runtime)
    
    # 获取元数据
    metadata = await manager.get_metadata_async()
    
    # 验证返回的是Metadata对象
    assert isinstance(metadata, Metadata)
    assert metadata.datasource_luid is not None
    assert len(metadata.fields) > 0
```


## Migration Strategy

### 阶段1：创建Metadata模型

1. 在 `models/metadata.py` 中创建 `FieldMetadata` 和 `Metadata` 模型
2. 编写单元测试验证模型功能
3. 确保模型可以正确序列化/反序列化

### 阶段2：更新StoreManager

1. 修改 `get_metadata` 方法返回 `Metadata` 对象
2. 修改 `put_metadata` 方法接收 `Metadata` 对象
3. 使用 `model_dump()` 和 `model_validate()` 进行序列化
4. 编写测试验证序列化/反序列化功能

### 阶段3：更新MetadataManager

1. 创建 `_convert_to_metadata_model` 方法
2. 修改 `get_metadata` 和 `get_metadata_async` 返回 `Metadata` 对象
3. 确保维度层级推断结果正确添加到模型
4. 确保valid_max_date正确添加到FieldMetadata
5. 编写测试验证转换逻辑

### 阶段4：创建QueryBuilder模块

1. 创建 `components/query_builder/` 目录
2. 实现 `date_filter_handler.py`
3. 实现 `filter_processor.py`
4. 实现 `builder.py`（主QueryBuilder类）
5. 创建 `__init__.py` 导出QueryBuilder
6. 编写单元测试和集成测试

### 阶段5：适配Agent

1. 更新维度层级推断Agent接收Metadata对象
2. 更新任务规划Agent接收Metadata对象
3. 更新其他使用元数据的Agent
4. 验证所有Agent正常工作

### 阶段6：清理和验证

1. 删除旧的 `query_builder.py` 文件
2. 更新所有导入语句
3. 运行完整的测试套件
4. 验证端到端功能


## File Structure

```
tableau_assistant/
├── src/
│   ├── models/
│   │   ├── metadata.py          # 新增：Metadata和FieldMetadata模型
│   │   ├── intent.py            # 保持不变：Intent中间层模型
│   │   ├── vizql_types.py       # 保持不变：VizQL查询语句模型
│   │   └── context.py           # 保持不变
│   │
│   ├── components/
│   │   ├── metadata_manager.py  # 修改：返回Metadata对象
│   │   ├── store_manager.py     # 修改：处理Metadata序列化
│   │   │
│   │   ├── query_builder/       # 新增：模块化目录
│   │   │   ├── __init__.py      # 导出QueryBuilder
│   │   │   ├── builder.py       # 主QueryBuilder类
│   │   │   ├── intent_converter.py        # Intent到VizQLField转换
│   │   │   ├── date_filter_converter.py   # DateFilterIntent到VizQL日期筛选器转换
│   │   │   └── filter_converter.py        # FilterIntent到VizQLFilter转换
│   │   │
│   │   └── query_builder.py     # 删除：旧文件
│   │
│   ├── agents/
│   │   ├── dimension_hierarchy_agent.py  # 修改：接收Metadata对象
│   │   └── task_planning_agent.py        # 保持不变：输出Intent模型
│   │
│   └── utils/
│       └── date_calculator.py   # 保持不变
│
└── tests/
    ├── models/
    │   └── test_metadata.py     # 新增：Metadata模型测试
    │
    └── components/
        ├── test_metadata_manager.py  # 修改：测试Metadata对象
        ├── test_store_manager.py     # 修改：测试序列化
        │
        └── query_builder/
            ├── test_intent_converter.py        # 新增
            ├── test_date_filter_converter.py   # 新增
            ├── test_filter_converter.py        # 新增
            └── test_builder.py                 # 新增
```


## Key Design Decisions

### 1. 为什么创建独立的metadata.py而不是放在vizql_types.py？

**决策：** 创建独立的 `models/metadata.py` 文件

**理由：**
- Metadata描述的是数据源的元信息，与VizQL查询语句是不同的概念
- vizql_types.py专注于VizQL查询语句的数据模型（基于tableau_sdk TypeScript定义）
- 分离关注点，便于独立维护和理解
- Metadata可能会有独立的演进路径

### 2. 为什么使用Pydantic模型而不是dataclass？

**决策：** 使用Pydantic BaseModel

**理由：**
- 提供强大的数据验证功能
- 内置序列化/反序列化支持（model_dump/model_validate）
- 与LangChain生态系统兼容
- 提供更好的类型提示和IDE支持
- 可以定义复杂的验证规则

### 3. 为什么将QueryBuilder拆分为多个转换器模块？

**决策：** 创建 `query_builder/` 目录，包含多个转换器模块

**理由：**
- 原文件近1000行，难以维护
- Intent到VizQL的转换逻辑复杂，按类型拆分更清晰
- 单一职责原则，每个转换器职责清晰
- 便于单元测试和代码复用
- 降低代码耦合度
- 符合开闭原则（新增Intent类型只需添加新转换器）

### 4. 为什么Metadata模型设置frozen=False？

**决策：** 允许修改Metadata和FieldMetadata对象

**理由：**
- 需要在获取元数据后添加dimension_hierarchy
- 需要在查询后添加valid_max_date到FieldMetadata
- 这些是增强操作，不是初始化时就有的数据
- 如果frozen=True，需要重新创建对象，效率较低

### 5. 为什么使用转换器模式而不是直接在Agent中生成VizQL？

**决策：** 任务规划Agent输出Intent模型，QueryBuilder负责转换为VizQL模型

**理由：**
- 关注点分离：Agent专注业务逻辑，QueryBuilder专注执行细节
- Intent模型更简洁，LLM更容易生成正确的输出
- 转换逻辑可以用代码实现，更可靠和可测试
- 便于调试：可以分别检查Intent和VizQL
- 灵活性：修改VizQL生成逻辑不需要重新训练Agent

