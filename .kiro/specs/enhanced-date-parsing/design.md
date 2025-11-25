# Design Document

## Overview

本设计文档定义了 Tableau Assistant 日期解析系统的增强方案。基于现有的 `DateCalculator` 和 `DateFilterConverter` 架构，借鉴 Datus-agent 的两阶段日期解析思路，使用代码逻辑实现日期提取、解析和验证，提升日期处理的准确性和可靠性。

### 核心设计原则

1. **代码优先，LLM 辅助**：优先使用正则表达式和日期计算库，复杂情况回退到 LLM
2. **基于现有架构**：扩展现有的 `TimeRange` 模型和 `DateCalculator`，而不是重写
3. **向后兼容**：保持现有 API 不变，新功能通过可选参数添加
4. **可追溯性**：记录完整的解析过程，便于调试和审计
5. **性能优化**：使用缓存避免重复计算，目标 <10ms 响应时间

## Architecture

### 整体架构

```
用户问题: "查询从1月到3月的销售数据"
    ↓
┌─────────────────────────────────────────────────────────┐
│ Understanding Agent (LLM)                               │
│  - 识别日期表达式: "从1月到3月"                         │
│  - 输出 TimeRange (type=absolute, value="01-03")       │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ DateParser (NEW - 代码逻辑)                             │
│  ├─ Step 1: 验证 TimeRange                             │
│  ├─ Step 2: 解析具体日期 (代码计算)                    │
│  ├─ Step 3: 验证日期范围                               │
│  └─ Step 4: 增强 TimeRange (添加追溯信息)              │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ DateCalculator (EXISTING - 扩展)                        │
│  - 计算相对日期                                         │
│  - 计算对比日期                                         │
│  - 格式化日期                                           │
└────────────────┬────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────┐
│ DateFilterConverter (EXISTING)                          │
│  - 转换为 VizQL 筛选器                                  │
└─────────────────────────────────────────────────────────┘
```

### 关键设计决策

**决策 1: 不改变 LLM 的职责**
- LLM 继续负责识别日期表达式和初步分类
- 代码负责验证、解析和增强
- 理由：LLM 擅长理解自然语言，代码擅长精确计算

**决策 2: 扩展 TimeRange 模型而不是创建新模型**
- 添加可选字段：`original_text`、`confidence`、`is_valid`、`validation_error`
- 保持向后兼容
- 理由：避免破坏现有代码

**决策 3: 创建新的 DateParser 类**
- 职责：验证、解析、增强 TimeRange
- 位置：`tableau_assistant/src/utils/date_parser.py`
- 理由：单一职责原则，DateCalculator 已经很复杂

## Components and Interfaces

### 1. TimeRange 模型扩展

```python
# tableau_assistant/src/models/question.py

class TimeRange(BaseModel):
    """Time range (EXTENDED)"""
    model_config = ConfigDict(extra="forbid")
    
    # ===== 现有字段 (保持不变) =====
    type: Optional[TimeRangeType] = None
    value: Optional[str] = None
    relative_type: Optional[RelativeType] = None
    period_type: Optional[PeriodType] = None
    range_n: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    
    # ===== 新增字段 (可选，向后兼容) =====
    original_text: Optional[str] = Field(
        None,
        description="原始日期表达式文本"
    )
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="解析置信度 (0.0-1.0)"
    )
    reference_date: Optional[str] = Field(
        None,
        description="参考日期 (用于相对时间计算)"
    )
    parsing_method: Optional[Literal["llm", "regex", "dateutil", "complex"]] = Field(
        None,
        description="解析方法"
    )
    is_valid: Optional[bool] = Field(
        None,
        description="验证结果"
    )
    validation_error: Optional[str] = Field(
        None,
        description="验证错误信息"
    )
    warnings: Optional[List[str]] = Field(
        None,
        description="警告列表"
    )
```

### 2. DateParser 类 (NEW)

```python
# tableau_assistant/src/utils/date_parser.py

class DateParser:
    """
    日期解析器
    
    职责：
    1. 验证 LLM 输出的 TimeRange
    2. 解析具体日期范围
    3. 验证日期范围合理性
    4. 增强 TimeRange (添加追溯信息)
    """
    
    def __init__(
        self,
        metadata: Optional[Metadata] = None,
        date_calculator: Optional[DateCalculator] = None
    ):
        self.metadata = metadata
        self.date_calculator = date_calculator or DateCalculator()
        self._cache = {}  # 简单的内存缓存
    
    def parse_and_validate(
        self,
        time_range: TimeRange,
        reference_date: Optional[datetime] = None
    ) -> TimeRange:
        """
        解析并验证 TimeRange
        
        Args:
            time_range: LLM 输出的 TimeRange
            reference_date: 参考日期 (默认使用 metadata 的 max_date)
        
        Returns:
            增强后的 TimeRange
        """
        # Step 1: 选择参考日期
        ref_date = self._select_reference_date(reference_date)
        
        # Step 2: 解析具体日期
        enhanced = self._parse_dates(time_range, ref_date)
        
        # Step 3: 验证日期范围
        validated = self._validate_dates(enhanced)
        
        # Step 4: 计算置信度
        validated.confidence = self._calculate_confidence(validated)
        
        return validated
```


### 3. TimeRange 模型扩展（支持日期范围格式）

**设计原则**：LLM 负责语义理解，代码只解析标准格式

**LLM 的职责**：
- 理解自然语言："从1月到3月" → 识别为日期范围
- 输出标准化格式：`TimeRange(type="absolute", start_date="01-01", end_date="03-31")`

**代码的职责**：
- 解析 LLM 输出的标准格式
- 补全年份（如果需要）
- 验证日期范围
- 格式化为 ISO 标准

**支持的 LLM 输出格式**：

```python
# 格式1: 使用 value 字段（现有）
TimeRange(type="absolute", value="2024")  # 年份
TimeRange(type="absolute", value="2024-Q1")  # 季度
TimeRange(type="absolute", value="2024-03")  # 月份
TimeRange(type="absolute", value="2024-03-15")  # 日期

# 格式2: 使用 start_date + end_date 字段（新增）
TimeRange(
    type="absolute",
    start_date="2024-01-01",  # LLM 输出
    end_date="2024-03-31"     # LLM 输出
)

# 格式3: 相对时间（现有）
TimeRange(
    type="relative",
    relative_type="LASTN",
    period_type="MONTHS",
    range_n=3
)
```

**DateParser 的处理逻辑**：

```python
def _parse_dates(self, time_range: TimeRange, ref_date: datetime) -> TimeRange:
    """
    解析 LLM 输出的标准格式（不做语义理解）
    """
    if time_range.type == "absolute":
        # 情况1: 已经有 start_date 和 end_date
        if time_range.start_date and time_range.end_date:
            # 直接使用，只需验证格式
            return time_range
        
        # 情况2: 使用 value 字段
        if time_range.value:
            # 解析标准格式（年份、季度、月份、日期）
            start, end = self._parse_value_format(time_range.value, ref_date)
            time_range.start_date = start
            time_range.end_date = end
    
    elif time_range.type == "relative":
        # 调用 DateCalculator 计算
        result = self.date_calculator.calculate_relative_date(...)
        time_range.start_date = result["start_date"]
        time_range.end_date = result["end_date"]
    
    return time_range
```

**关键点**：
- ✅ LLM 负责理解"从1月到3月"，输出 `start_date="01-01", end_date="03-31"`
- ✅ 代码只解析标准格式，补全年份
- ❌ 代码不用正则匹配自然语言
- ❌ 代码不做语义理解

### 4. Understanding Agent 集成

```python
# tableau_assistant/src/agents/understanding_agent.py

class UnderstandingAgent(BaseVizQLAgent):
    """Understanding Agent (MODIFIED)"""
    
    def _process_result(
        self,
        result: QuestionUnderstanding,
        state: VizQLState
    ) -> Dict[str, Any]:
        """
        Process understanding result (EXTENDED)
        
        新增：日期解析和验证
        """
        # 现有逻辑
        result = self._fix_dimension_aggregations(result)
        
        # 新增：日期解析和验证
        result = self._enhance_date_parsing(result, state)
        
        return {
            "understanding": result,
            "current_stage": "planning"
        }
    
    def _enhance_date_parsing(
        self,
        result: QuestionUnderstanding,
        state: VizQLState
    ) -> QuestionUnderstanding:
        """
        增强日期解析
        
        对每个子问题的 time_range 进行验证和增强
        """
        from tableau_assistant.src.utils.date_parser import DateParser
        
        # 获取元数据和参考日期
        metadata = state.get("metadata")
        reference_date = self._get_reference_date(metadata)
        
        # 创建 DateParser
        parser = DateParser(metadata=metadata)
        
        # 处理每个子问题
        for sq in result.sub_questions:
            if hasattr(sq, 'time_range') and sq.time_range:
                # 获取该子问题提到的日期字段（如果有）
                mentioned_date_field = None
                if hasattr(sq, 'filter_date_field') and sq.filter_date_field:
                    mentioned_date_field = sq.filter_date_field
                
                # 使用对应的参考日期（支持不同子问题用不同参考日期）
                reference_date = self._get_reference_date(metadata, mentioned_date_field)
                
                # 解析并验证
                sq.time_range = parser.parse_and_validate(
                    sq.time_range,
                    reference_date
                )
        
        return result
    
    def _get_reference_date(
        self,
        metadata: Optional[Any],
        mentioned_date_field: Optional[str] = None
    ) -> datetime:
        """
        获取参考日期（智能策略，支持多日期字段）
        
        优先级：
        1. 用户明确提到的日期字段的 valid_max_date（精确）
        2. 所有日期字段中最大的 valid_max_date（保守）
        3. 当前日期 - 1 天（兜底）
        
        Args:
            metadata: 元数据对象
            mentioned_date_field: 用户提到的日期字段名（从 filter_date_field 获取）
        
        Returns:
            参考日期（datetime 对象）
        
        Examples:
            # 场景1: 用户明确提到 "订单日期最近3个月"
            ref_date = self._get_reference_date(metadata, "订单日期")
            # 使用 "订单日期" 的 valid_max_date
            
            # 场景2: 用户只说 "最近3个月"
            ref_date = self._get_reference_date(metadata, None)
            # 使用所有日期字段中最大的 valid_max_date
        """
        if metadata:
            # 优先级1: 用户明确提到的日期字段
            if mentioned_date_field:
                field = metadata.get_field(mentioned_date_field)
                if field and field.valid_max_date:
                    try:
                        ref_date = datetime.fromisoformat(field.valid_max_date)
                        logger.info(
                            f"使用用户提到的日期字段: {mentioned_date_field} = {ref_date.date()}"
                        )
                        return ref_date
                    except Exception as e:
                        logger.warning(f"解析日期字段 {mentioned_date_field} 失败: {e}")
            
            # 优先级2: 所有日期字段中最大的日期（保守策略）
            date_fields_with_max = []
            for field in metadata.fields:
                if field.valid_max_date:
                    try:
                        date_fields_with_max.append({
                            "field": field.fieldCaption,
                            "date": datetime.fromisoformat(field.valid_max_date)
                        })
                    except Exception:
                        continue
            
            if date_fields_with_max:
                # 按日期排序，取最大的
                date_fields_with_max.sort(key=lambda x: x["date"], reverse=True)
                max_field = date_fields_with_max[0]
                
                logger.info(
                    f"使用最大日期字段: {max_field['field']} = {max_field['date'].date()}, "
                    f"可用字段: {[f['field'] for f in date_fields_with_max]}"
                )
                return max_field["date"]
        
        # 优先级3: 回退
        ref_date = datetime.now() - timedelta(days=1)
        logger.warning(f"无法从元数据获取参考日期，使用系统日期-1: {ref_date.date()}")
        return ref_date
```

## Data Models

### TimeRange 完整定义

```python
class TimeRange(BaseModel):
    """
    时间范围 (完整版)
    
    设计哲学：
    - LLM 负责识别和初步分类
    - 代码负责验证和增强
    - 保持向后兼容
    """
    model_config = ConfigDict(extra="forbid")
    
    # ===== 核心字段 (LLM 输出) =====
    type: Optional[TimeRangeType] = Field(None, description="时间范围类型")
    value: Optional[str] = Field(None, description="绝对时间值")
    relative_type: Optional[RelativeType] = Field(None, description="相对时间类型")
    period_type: Optional[PeriodType] = Field(None, description="周期类型")
    range_n: Optional[int] = Field(None, ge=1, description="相对时间数量")
    
    # ===== 解析结果 (代码计算) =====
    start_date: Optional[str] = Field(None, description="开始日期 (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="结束日期 (YYYY-MM-DD)")
    
    # ===== 追溯信息 (代码添加) =====
    original_text: Optional[str] = Field(None, description="原始表达式")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="置信度")
    reference_date: Optional[str] = Field(None, description="参考日期")
    reference_date_source: Optional[str] = Field(
        None, 
        description="参考日期来源（用于追溯和调试）"
        # 可能的值:
        # - "field:订单日期" - 使用用户提到的字段
        # - "max_field:订单日期" - 使用最大日期字段
        # - "system_date_minus_1" - 使用系统日期-1
    )
    parsing_method: Optional[Literal["llm", "regex", "dateutil", "complex"]] = Field(
        None, description="解析方法"
    )
    
    # ===== 验证结果 (代码验证) =====
    is_valid: Optional[bool] = Field(None, description="是否有效")
    validation_error: Optional[str] = Field(None, description="验证错误")
    warnings: Optional[List[str]] = Field(default_factory=list, description="警告列表")
```

### DateParseResult

```python
class DateParseResult(BaseModel):
    """
    日期解析结果
    
    用于内部传递解析结果
    """
    success: bool = Field(description="是否成功")
    start_date: Optional[str] = Field(None, description="开始日期")
    end_date: Optional[str] = Field(None, description="结束日期")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度")
    method: str = Field(description="解析方法")
    error: Optional[str] = Field(None, description="错误信息")
    warnings: List[str] = Field(default_factory=list, description="警告列表")
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 日期提取完整性

*For any* 用户问题，如果问题包含 N 个日期表达式，则系统应该提取出 N 个日期表达式，且顺序保持一致
**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: TimeRange 模型完整性

*For any* TimeRange 对象，如果它表示日期范围，则必须同时包含 start_date 和 end_date 字段，且 start_date <= end_date
**Validates: Requirements 2.1, 2.2**

### Property 3: TimeRange 序列化往返一致性

*For any* TimeRange 对象，序列化后再反序列化应该得到等价的对象（所有字段值相同）
**Validates: Requirements 2.6**

### Property 4: 相对时间计算一致性

*For any* 相对时间表达式（如"最近N个月"），使用相同的参考日期计算应该得到相同的日期范围
**Validates: Requirements 3.3, 3.4**

### Property 5: 日期范围验证正确性

*For any* 解析后的日期范围，如果 start_date > end_date，则系统应该标记为无效（is_valid=false）
**Validates: Requirements 4.1**

### Property 6: 日期范围边界调整

*For any* 解析后的日期范围，如果 end_date 超过数据源的 max_date，则系统应该调整 end_date 为 max_date 并记录警告
**Validates: Requirements 4.2**

### Property 7: 日期格式标准化

*For any* 解析后的日期，无论输入格式如何，输出格式应该统一为 ISO 标准（YYYY-MM-DD）
**Validates: Requirements 4.5**

### Property 8: 置信度分数合理性

*For any* 日期解析结果，置信度分数应该在 0.0-1.0 范围内，且绝对日期的置信度应该高于相对日期
**Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

### Property 9: 参考日期优先级

*For any* 日期解析过程，如果元数据包含 max_date，则应该优先使用 max_date 作为参考日期，而不是当前系统日期
**Validates: Requirements 6.1, 6.2**

### 参考日期来源说明（支持多日期字段）

**reference_date 的智能获取逻辑**：

**优先级 1：用户明确提到的日期字段**
- 来源：`filter_date_field` 指定的字段的 `valid_max_date`
- 场景：用户说"订单日期最近3个月"
- 逻辑：使用 `metadata.get_field("订单日期").valid_max_date`
- 示例：`"2024-12-31"`
- 追溯：`reference_date_source = "field:订单日期"`

**优先级 2：所有日期字段中最大的日期（保守策略）**
- 来源：遍历所有日期字段，取最大的 `valid_max_date`
- 场景：用户只说"最近3个月"，没有明确提到字段
- 逻辑：
  ```python
  date_fields = [
      ("订单日期", "2024-12-31"),
      ("发货日期", "2024-12-30"),
      ("收货日期", "2024-12-28")
  ]
  reference_date = max(date_fields) = "2024-12-31"
  ```
- 追溯：`reference_date_source = "max_field:订单日期"`

**优先级 3：当前日期 - 1 天（兜底）**
- 来源：系统当前日期减去 1 天
- 场景：元数据不可用或没有日期字段
- 理由：避免使用未来日期，数据通常有延迟
- 示例：如果今天是 2025-01-15，则使用 2025-01-14
- 追溯：`reference_date_source = "system_date_minus_1"`

**为什么需要 reference_date？**

相对时间表达式（如"最近3个月"、"去年同期"）需要一个基准日期来计算具体的日期范围：
- "最近3个月" + reference_date=2024-12-31 → 2024-10-01 to 2024-12-31
- "去年同期" + reference_date=2024-12-31 → 2023-12-01 to 2023-12-31

**多日期字段场景示例**：

```python
# 场景1: 用户明确提到日期字段
用户问题: "订单日期最近3个月的数据"
filter_date_field = "订单日期"
reference_date = "2024-12-31"  # 使用订单日期的 valid_max_date
reference_date_source = "field:订单日期"

# 场景2: 用户没有明确提到
用户问题: "最近3个月的数据"
filter_date_field = None
reference_date = "2024-12-31"  # 使用最大的日期字段
reference_date_source = "max_field:订单日期"

# 场景3: 多个子问题，不同日期字段
用户问题: "订单日期和发货日期最近3个月的对比"
sub_question_1.filter_date_field = "订单日期"
  → reference_date = "2024-12-31"
  → reference_date_source = "field:订单日期"
sub_question_2.filter_date_field = "发货日期"
  → reference_date = "2024-12-30"
  → reference_date_source = "field:发货日期"
```

**valid_max_date 的来源**：

在现有代码中，每个日期字段的 `valid_max_date` 通过以下方式获取：
```python
# tableau_assistant/src/utils/tableau/metadata.py
# fetch_valid_max_date_async() 函数

# 1. 查询数据源获取 MAX(date_field)
result = await execute_vizql_query(f"SELECT MAX({date_field_name})")

# 2. 与今天-1比较，取最小值
datasource_max_date = parse_date(result)
valid_max_date = min(datasource_max_date, today_minus_1)

# 3. 存储到 FieldMetadata
field.valid_max_date = valid_max_date.isoformat()
```

这个设计确保了：
1. 使用数据的实际最大日期（而不是今天）
2. 避免查询未来数据
3. 支持多日期字段场景
4. 完整的追溯信息

### Property 10: 追溯信息完整性

*For any* 解析后的 TimeRange，应该包含 original_text、reference_date、reference_date_source、parsing_method 等追溯字段
**Validates: Requirements 7.1, 7.2, 7.3**

### Property 11: 错误处理优雅性

*For any* 日期解析失败的情况，系统应该返回包含错误信息的 TimeRange 对象，而不是抛出异常
**Validates: Requirements 11.1, 11.2, 11.3**

### Property 12: 缓存一致性

*For any* 相同的日期表达式和参考日期，多次解析应该得到相同的结果（缓存命中）
**Validates: Requirements 10.3**

## Error Handling

### 错误分类

1. **解析错误**：无法识别的日期表达式
   - 处理：返回 confidence=0.0，记录错误信息
   - 不中断流程

2. **验证错误**：日期范围不合理（如 start > end）
   - 处理：设置 is_valid=false，记录验证错误
   - 不中断流程

3. **边界错误**：日期超出数据范围
   - 处理：自动调整，记录警告
   - 不中断流程

4. **系统错误**：代码异常（如库导入失败）
   - 处理：回退到 LLM 解析，记录错误
   - 不中断流程

### 错误处理策略

```python
def parse_and_validate(self, time_range: TimeRange) -> TimeRange:
    """解析并验证（带错误处理）"""
    try:
        # 尝试代码解析
        result = self._parse_dates(time_range)
    except Exception as e:
        logger.warning(f"代码解析失败，回退到 LLM: {e}")
        # 回退策略：保持 LLM 的原始输出
        result = time_range
        result.parsing_method = "llm"
        result.confidence = 0.7
        result.warnings = [f"代码解析失败: {str(e)}"]
    
    # 验证（总是执行）
    try:
        result = self._validate_dates(result)
    except Exception as e:
        logger.error(f"验证失败: {e}")
        result.is_valid = False
        result.validation_error = str(e)
    
    return result
```

## Testing Strategy

### 单元测试

**测试范围**：
- TimeRange 模型的字段验证
- DateParser 的各个方法
- DateCalculator 的新增方法
- 边界情况和错误处理

**测试工具**：pytest

**示例测试**：
```python
def test_time_range_serialization():
    """测试 TimeRange 序列化往返"""
    original = TimeRange(
        type=TimeRangeType.ABSOLUTE,
        value="2024",
        start_date="2024-01-01",
        end_date="2024-12-31",
        confidence=1.0
    )
    
    # 序列化
    json_str = original.model_dump_json()
    
    # 反序列化
    restored = TimeRange.model_validate_json(json_str)
    
    # 验证
    assert restored == original
```

### 属性测试

**测试框架**：Hypothesis

**核心属性**：
1. 日期范围有效性：start_date <= end_date
2. 置信度范围：0.0 <= confidence <= 1.0
3. 序列化往返一致性
4. 相对时间计算一致性

**示例属性测试**：
```python
from hypothesis import given, strategies as st

@given(
    relative_type=st.sampled_from(["LAST", "LASTN"]),
    period_type=st.sampled_from(["DAYS", "MONTHS", "YEARS"]),
    range_n=st.integers(min_value=1, max_value=100),
    reference_date=st.datetimes()
)
def test_relative_date_calculation_consistency(
    relative_type, period_type, range_n, reference_date
):
    """属性：相同输入应该得到相同输出"""
    calculator = DateCalculator(anchor_date=reference_date)
    
    # 计算两次
    result1 = calculator.calculate_relative_date(
        relative_type, period_type, range_n
    )
    result2 = calculator.calculate_relative_date(
        relative_type, period_type, range_n
    )
    
    # 应该相同
    assert result1 == result2
```

### 集成测试

**测试场景**：
1. Understanding Agent → DateParser → DateCalculator 完整流程
2. 各种日期表达式的端到端测试
3. 与现有 DateFilterConverter 的集成

**测试数据**：
- 真实用户问题样本
- 边界情况（跨年、闰年、月末等）
- 错误情况（无效日期、格式错误等）

## Performance Considerations

### 性能目标

- 标准日期解析：< 10ms
- 复杂表达式解析：< 50ms
- 缓存命中率：> 80%

### 优化策略

1. **正则表达式预编译**
```python
class DateParser:
    # 类级别预编译
    PATTERNS = {
        "month_range": re.compile(r"从(\d+)月到(\d+)月"),
        "year_start_to_now": re.compile(r"(\d{4})年初到现在"),
        # ...
    }
```

2. **简单缓存**
```python
def parse_and_validate(self, time_range: TimeRange) -> TimeRange:
    # 生成缓存键
    cache_key = self._generate_cache_key(time_range)
    
    # 检查缓存
    if cache_key in self._cache:
        return self._cache[cache_key]
    
    # 解析
    result = self._parse_dates(time_range)
    
    # 缓存结果
    self._cache[cache_key] = result
    return result
```

3. **延迟计算**
```python
# 只在需要时才计算具体日期
if time_range.start_date is None:
    time_range.start_date = self._calculate_start_date(time_range)
```

## Migration Strategy

### 阶段 1: 模型扩展（第 1 周）

1. 扩展 TimeRange 模型（添加可选字段）
2. 更新 Pydantic 验证规则
3. 确保向后兼容

### 阶段 2: DateParser 实现（第 2 周）

1. 创建 DateParser 类
2. 实现核心解析逻辑
3. 添加单元测试

### 阶段 3: DateCalculator 扩展（第 3 周）

1. 添加复杂表达式解析方法
2. 扩展现有方法支持新场景
3. 添加单元测试

### 阶段 4: Understanding Agent 集成（第 4 周）

1. 在 Understanding Agent 中集成 DateParser
2. 添加集成测试
3. 性能测试和优化

### 阶段 5: 验证和部署（第 5 周）

1. 端到端测试
2. 性能基准测试
3. 文档更新
4. 灰度发布

## Dependencies

### 现有依赖

- `pydantic`: 数据模型验证
- `datetime`: 日期计算
- `calendar`: 月份天数计算
- `chinese_calendar`: 节假日支持（可选）

### 新增依赖

- `python-dateutil`: 复杂日期解析（推荐）
  - 理由：强大的相对日期解析能力
  - 安装：`pip install python-dateutil`

- `arrow`: 人性化的日期处理（备选）
  - 理由：更简洁的 API
  - 安装：`pip install arrow`

### 依赖选择建议

推荐使用 `python-dateutil`，因为：
1. 更成熟稳定
2. 标准库风格的 API
3. 与现有 `datetime` 代码集成更好

## Security Considerations

### 输入验证

1. **日期范围限制**：防止超大范围查询
```python
MAX_DATE_RANGE_DAYS = 3650  # 10年

def _validate_date_range(self, start: datetime, end: datetime):
    if (end - start).days > MAX_DATE_RANGE_DAYS:
        raise ValueError(f"日期范围超过限制: {MAX_DATE_RANGE_DAYS}天")
```

2. **正则表达式安全**：使用预编译的正则，避免 ReDoS 攻击

3. **缓存大小限制**：防止内存溢出
```python
MAX_CACHE_SIZE = 1000

def _add_to_cache(self, key, value):
    if len(self._cache) >= MAX_CACHE_SIZE:
        # LRU 清理
        self._cache.pop(next(iter(self._cache)))
    self._cache[key] = value
```

## Monitoring and Logging

### 关键指标

1. **解析成功率**：成功解析的日期表达式比例
2. **置信度分布**：各置信度区间的分布
3. **解析时间**：P50、P95、P99 延迟
4. **缓存命中率**：缓存命中次数 / 总请求次数
5. **验证失败率**：验证失败的比例

### 日志记录

```python
logger.info(
    "日期解析完成",
    extra={
        "original_text": time_range.original_text,
        "start_date": result.start_date,
        "end_date": result.end_date,
        "confidence": result.confidence,
        "method": result.parsing_method,
        "duration_ms": duration
    }
)
```

## Future Enhancements

### 短期（3 个月内）

1. 支持更多复杂表达式（如"每个月的第一周"）
2. 机器学习模型辅助日期识别
3. 用户反馈收集和学习

### 长期（6 个月以上）

1. 多语言支持（英文、日文等）
2. 自定义日期表达式规则
3. 智能日期推荐（基于历史查询）

