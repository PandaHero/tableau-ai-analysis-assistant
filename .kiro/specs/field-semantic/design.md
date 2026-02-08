# 设计文档

## 概述

字段语义增强服务（Field Semantic Service）是对现有 `dimension_hierarchy` 模块的重构和扩展。该服务采用统一的架构来处理维度和度量字段的语义分析，通过一次 LLM 调用同时获取所有字段的语义属性，并生成增强的索引文本以改进 RAG 检索效果。

核心设计原则：
1. **统一模型**：使用单一数据模型表示所有字段类型的语义属性
2. **批量处理**：一次 LLM 调用处理所有字段，减少 API 调用次数
3. **增量推断**：复用现有缓存机制，只对新增/变更字段进行推断
4. **索引增强**：生成自然语言描述的索引文本，提高检索准确性

## 架构

### 推断流程

字段语义推断采用分层策略，按优先级依次尝试：

```
输入字段列表
    │
    ▼
┌─────────────────┐
│  1. 缓存检查    │ ← 检查字段是否已有缓存结果
└────────┬────────┘
         │ 缓存未命中的字段
         ▼
┌─────────────────┐
│  2. 增量计算    │ ← 识别新增/变更的字段
└────────┬────────┘
         │ 需要推断的字段
         ▼
┌─────────────────┐
│  3. 种子匹配    │ ← 精确匹配预置的种子数据
└────────┬────────┘
         │ 未匹配的字段
         ▼
┌─────────────────┐
│  4. RAG 检索    │ ← 向量检索相似的历史模式
└────────┬────────┘
         │ 未检索到的字段
         ▼
┌─────────────────┐
│  5. LLM 推断    │ ← 调用 LLM 进行语义分析
└────────┬────────┘
         │ 高置信度结果
         ▼
┌─────────────────┐
│  6. 自学习存储  │ ← 存入 RAG 供后续检索
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  7. 更新缓存    │ ← 缓存结果供下次使用
└─────────────────┘
         │
         ▼
    返回结果
```

### 外部依赖

| 组件 | 用途 |
|------|------|
| CacheManager | 缓存推断结果，支持增量更新 |
| RAGService | 向量检索和索引管理 |
| LLM Service | 调用大语言模型进行语义分析 |
| Seed Data | 预置的维度和度量种子数据 |

## 组件与接口

### 目录结构

```
analytics_assistant/src/agents/field_semantic/
├── __init__.py                 # 模块导出
├── inference.py                # 推断服务主类
├── schemas/
│   ├── __init__.py
│   └── output.py               # 数据模型定义
└── prompts/
    ├── __init__.py
    └── prompt.py               # Prompt 模板
```

### 核心接口

#### FieldSemanticInference

```python
class FieldSemanticInference:
    """字段语义推断服务"""
    
    def __init__(
        self,
        enable_rag: bool = True,
        enable_cache: bool = True,
        enable_self_learning: bool = True,
    ) -> None:
        """初始化推断服务"""
        ...
    
    async def infer(
        self,
        datasource_luid: str,
        fields: List[Field],
        table_id: Optional[str] = None,
        skip_cache: bool = False,
        on_token: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> FieldSemanticResult:
        """
        推断字段语义属性
        
        Args:
            datasource_luid: 数据源 LUID
            fields: Field 模型列表（包含维度和度量）
            table_id: 逻辑表 ID（多表数据源时使用）
            skip_cache: 是否跳过缓存
            on_token: Token 回调（用于流式输出展示）
        
        Returns:
            FieldSemanticResult 推断结果
        """
        ...
    
    def enrich_fields(self, fields: List[Field]) -> List[Field]:
        """使用推断结果更新 Field 对象"""
        ...
    
    def clear_cache(self, cache_key: Optional[str] = None) -> bool:
        """清除缓存"""
        ...
```

#### 便捷函数

```python
async def infer_field_semantic(
    datasource_luid: str,
    fields: List[Field],
    table_id: Optional[str] = None,
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,
) -> FieldSemanticResult:
    """便捷函数：推断字段语义属性"""
    ...
```

## 数据模型

### MeasureCategory 枚举

```python
class MeasureCategory(str, Enum):
    """度量类别枚举"""
    REVENUE = "revenue"      # 收入类：销售额、营业收入、GMV
    COST = "cost"            # 成本类：成本、费用、支出
    PROFIT = "profit"        # 利润类：利润、毛利、净利
    QUANTITY = "quantity"    # 数量类：数量、件数、订单数
    RATIO = "ratio"          # 比率类：占比、增长率、转化率
    COUNT = "count"          # 计数类：人数、次数、频次
    AVERAGE = "average"      # 平均类：均价、平均值
    OTHER = "other"          # 其他
```

### FieldSemanticAttributes

```python
class FieldSemanticAttributes(BaseModel):
    """字段语义属性"""
    
    # 通用属性
    role: Literal["dimension", "measure"]
    business_description: str
    aliases: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    
    # 维度专属属性（role="dimension" 时有效）
    category: Optional[DimensionCategory] = None
    category_detail: Optional[str] = None
    level: Optional[int] = Field(default=None, ge=1, le=5)
    granularity: Optional[Literal["coarsest", "coarse", "medium", "fine", "finest"]] = None
    parent_dimension: Optional[str] = None
    child_dimension: Optional[str] = None
    
    # 度量专属属性（role="measure" 时有效）
    measure_category: Optional[MeasureCategory] = None
    
    @model_validator(mode='after')
    def validate_role_specific_fields(self) -> 'FieldSemanticAttributes':
        """验证角色特定字段"""
        if self.role == "dimension":
            if self.category is None:
                self.category = DimensionCategory.OTHER
            if self.level is None:
                self.level = 3
            if self.granularity is None:
                self.granularity = "medium"
        elif self.role == "measure":
            if self.measure_category is None:
                self.measure_category = MeasureCategory.OTHER
        return self
```

### FieldSemanticResult

```python
class FieldSemanticResult(BaseModel):
    """字段语义推断结果"""
    field_semantic: Dict[str, FieldSemanticAttributes] = Field(
        description="字段语义字典，key 为字段名，value 为 FieldSemanticAttributes"
    )
```

### LLM 输出 Schema

```python
class LLMFieldSemanticItem(BaseModel):
    """LLM 输出的单个字段语义属性"""
    role: str
    business_description: str
    aliases: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    
    # 维度属性
    category: Optional[str] = None
    category_detail: Optional[str] = None
    level: Optional[int] = None
    granularity: Optional[str] = None
    
    # 度量属性
    measure_category: Optional[str] = None


class LLMFieldSemanticOutput(BaseModel):
    """LLM 输出的字段语义结果"""
    field_semantic: Dict[str, LLMFieldSemanticItem]
    
    def to_field_semantic_result(self) -> FieldSemanticResult:
        """转换为 FieldSemanticResult"""
        ...
```

## Prompt 设计

### System Prompt

```python
SYSTEM_PROMPT = """你是一个字段语义分析专家，负责推断数据字段的语义属性。

## 任务
分析每个字段，根据其角色（维度/度量）推断相应属性：

### 维度字段（role="dimension"）
1. category: 维度类别（time/geography/product/customer/organization/channel/financial/other）
2. category_detail: 详细类别，格式 'category-subcategory'
3. level: 层级 1-5（1 最粗，5 最细）
4. granularity: 粒度描述（coarsest/coarse/medium/fine/finest）

### 度量字段（role="measure"）
1. measure_category: 度量类别
   - revenue: 收入类（销售额、营业收入、GMV）
   - cost: 成本类（成本、费用、支出）
   - profit: 利润类（利润、毛利、净利）
   - quantity: 数量类（数量、件数、订单数）
   - ratio: 比率类（占比、增长率、转化率）
   - count: 计数类（人数、次数、频次）
   - average: 平均类（均价、平均值）
   - other: 其他

### 所有字段
1. business_description: 业务描述（一句话说明字段的业务含义）
2. aliases: 别名列表（用户可能使用的其他名称）
3. confidence: 置信度 0-1

## 业务描述规则
- 使用自然语言描述字段的业务含义
- 描述应简洁明了，不超过 50 字
- 包含字段的用途和典型使用场景

## 别名生成规则
- 包含常见的同义词和缩写
- 包含中英文对照（如适用）
- 包含业务术语的变体
- 每个字段 2-5 个别名

## 输出格式
返回 JSON 对象，格式如下：
```json
{
  "field_semantic": {
    "字段1": {
      "role": "dimension",
      "category": "geography",
      "category_detail": "geography-province",
      "level": 2,
      "granularity": "coarse",
      "business_description": "表示销售发生的省份区域",
      "aliases": ["省", "省份名称", "Province"],
      "confidence": 0.9
    },
    "字段2": {
      "role": "measure",
      "measure_category": "revenue",
      "business_description": "表示产品销售的总金额",
      "aliases": ["销售金额", "营收", "Sales Amount"],
      "confidence": 0.95
    }
  }
}
```"""
```

### User Prompt 构建

```python
def build_user_prompt(
    fields: List[Dict[str, Any]],
    include_few_shot: bool = True,
) -> str:
    """
    构建用户提示
    
    Args:
        fields: 要推断的字段列表，每个字段包含：
            - field_caption: 字段显示名称
            - data_type: 数据类型
            - role: 字段角色（dimension/measure）
            - sample_values: 样例值（可选）
        include_few_shot: 是否包含 few-shot 示例
    
    Returns:
        用户提示字符串
    """
    ...
```

## 索引文本增强

### 增强格式

```python
def build_enhanced_index_text(
    caption: str,
    business_description: str,
    aliases: List[str],
    role: str,
    data_type: str,
) -> str:
    """
    构建增强的索引文本
    
    格式：{caption}: {business_description}。别名: {aliases}。类型: {role}, {data_type}
    
    示例：
    - "省份: 表示销售发生的省份区域。别名: 省, 省份名称, Province。类型: dimension, string"
    - "销售额: 表示产品销售的总金额。别名: 销售金额, 营收, Sales Amount。类型: measure, real"
    """
    parts = [f"{caption}: {business_description}"]
    
    if aliases:
        parts.append(f"别名: {', '.join(aliases)}")
    
    parts.append(f"类型: {role}, {data_type}")
    
    return "。".join(parts)
```

### FieldChunk 增强

```python
@classmethod
def from_field_with_semantic(
    cls,
    field_metadata: Any,
    semantic_attrs: FieldSemanticAttributes,
    max_samples: int = 5,
) -> "FieldChunk":
    """
    从 FieldMetadata 和语义属性创建增强的 FieldChunk
    
    使用语义属性中的 business_description 和 aliases 构建增强的 index_text
    """
    ...
```

## 种子数据

### 种子数据位置

度量种子数据将放在 `analytics_assistant/src/infra/seeds/measure.py`，与现有的 `dimension.py` 并列：

```
analytics_assistant/src/infra/seeds/
├── __init__.py          # 导出 MEASURE_SEEDS
├── computation.py       # 计算公式种子
├── dimension.py         # 维度模式种子（已有）
├── measure.py           # 度量模式种子（新增）
├── keywords/            # 关键词类
└── patterns/            # 模式类
```

### 度量种子数据结构

```python
MEASURE_SEEDS: List[Dict[str, Any]] = [
    # Revenue 收入类
    {
        "field_caption": "销售额",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "表示产品或服务销售的总金额",
        "aliases": ["销售金额", "营收", "Sales", "Revenue"],
        "reasoning": "收入类度量，表示销售收入",
    },
    {
        "field_caption": "Sales",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "Total sales amount for products or services",
        "aliases": ["Sales Amount", "Revenue", "销售额"],
        "reasoning": "Revenue measure representing sales income",
    },
    # ... 更多种子数据
]
```

### 种子数据类别覆盖

| 类别 | 中文示例 | 英文示例 |
|------|----------|----------|
| revenue | 销售额、营业收入、GMV | Sales, Revenue, GMV |
| cost | 成本、费用、支出 | Cost, Expense, Spending |
| profit | 利润、毛利、净利 | Profit, Gross Profit, Net Profit |
| quantity | 数量、件数、订单数 | Quantity, Count, Order Count |
| ratio | 占比、增长率、转化率 | Ratio, Growth Rate, Conversion Rate |
| count | 人数、次数、频次 | Headcount, Frequency, Times |
| average | 均价、平均值 | Average Price, Mean Value |

## 配置管理

### app.yaml 配置节

```yaml
field_semantic:
  # 置信度阈值
  high_confidence_threshold: 0.85
  
  # 重试配置
  max_retry_attempts: 3
  
  # 缓存配置
  cache_namespace: "field_semantic"
  pattern_namespace: "field_semantic_patterns_metadata"
  
  # 增量推断
  incremental:
    enabled: true
  
  # RAG 索引
  index_name: "field_semantic_patterns"
```

## 错误处理

### 错误处理策略

| 错误类型 | 处理策略 | 日志级别 |
|----------|----------|----------|
| LLM 调用失败 | 重试 max_retry_attempts 次，全部失败返回默认值 | ERROR |
| RAG 检索失败 | 跳过 RAG 阶段，继续 LLM 推断 | WARNING |
| 缓存读取失败 | 继续执行推断，不影响主流程 | WARNING |
| 缓存写入失败 | 继续执行，下次重新推断 | WARNING |
| 种子数据加载失败 | 使用空种子数据，依赖 LLM 推断 | WARNING |

### 默认属性

```python
def _default_dimension_attrs(name: str) -> FieldSemanticAttributes:
    """维度字段默认属性"""
    return FieldSemanticAttributes(
        role="dimension",
        category=DimensionCategory.OTHER,
        category_detail="other-unknown",
        level=3,
        granularity="medium",
        business_description=name,
        aliases=[],
        confidence=0.0,
        reasoning=f"推断失败: {name}",
    )

def _default_measure_attrs(name: str) -> FieldSemanticAttributes:
    """度量字段默认属性"""
    return FieldSemanticAttributes(
        role="measure",
        measure_category=MeasureCategory.OTHER,
        business_description=name,
        aliases=[],
        confidence=0.0,
        reasoning=f"推断失败: {name}",
    )
```

## 正确性属性

*正确性属性是系统应该在所有有效执行中保持的特性——本质上是关于系统应该做什么的形式化陈述。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*



基于需求文档中的验收标准，以下是可测试的正确性属性：

### Property 1: 维度属性完整性

*For any* FieldSemanticAttributes 实例，当 role="dimension" 时，category、level、granularity 字段应该包含有效值（非 None），且 level 在 1-5 范围内，granularity 与 level 对应。

**Validates: Requirements 2.3**

### Property 2: 度量属性完整性

*For any* FieldSemanticAttributes 实例，当 role="measure" 时，measure_category 字段应该包含有效的 MeasureCategory 枚举值（非 None）。

**Validates: Requirements 2.4**

### Property 3: User Prompt 字段信息完整性

*For any* 字段列表输入，构建的 User Prompt 应该包含每个字段的 caption、data_type、role 信息。如果字段有 sample_values，Prompt 也应该包含样例值。

**Validates: Requirements 3.4**

### Property 4: LLM 输出转换一致性

*For any* 有效的 LLMFieldSemanticOutput 实例，调用 to_field_semantic_result() 方法应该产生一个有效的 FieldSemanticResult，且所有字段名和核心属性值保持一致。

**Validates: Requirements 3.6**

### Property 5: 增量推断缓存复用

*For any* 字段列表，如果字段的 caption 和 data_type 未发生变化，第二次调用 infer 方法应该从缓存返回相同的结果，而不是重新进行 LLM 推断。

**Validates: Requirements 4.2**

### Property 6: 度量种子数据结构完整性

*For any* MEASURE_SEEDS 中的条目，应该包含 field_caption、data_type、measure_category、business_description、aliases、reasoning 字段，且 measure_category 是有效的 MeasureCategory 枚举值。

**Validates: Requirements 5.3**

### Property 7: 索引文本格式正确性

*For any* 字段的语义属性，生成的 index_text 应该遵循格式 `{caption}: {business_description}。别名: {aliases}。类型: {role}, {data_type}`，其中 caption、business_description、role、data_type 必须存在，aliases 部分在别名列表为空时省略。

**Validates: Requirements 6.1, 6.2, 6.3**

### Property 8: 高置信度结果存储

*For any* 推断结果，当 confidence >= high_confidence_threshold 且结果来源为 LLM（非种子匹配或 RAG 匹配）时，该结果应该被存入 RAG 索引。

**Validates: Requirements 7.2**

### Property 9: RAG 文档结构完整性

*For any* 存入 RAG 索引的文档，其 content 应该是增强的 index_text，metadata 应该包含 field_caption、role、source、verified 字段，以及 category（维度）或 measure_category（度量）字段。

**Validates: Requirements 7.3, 7.4**

## 测试策略

### 双重测试方法

本服务采用单元测试和属性测试相结合的方式：

- **单元测试**：验证特定示例、边界情况和错误条件
- **属性测试**：验证所有有效输入的通用属性

### 属性测试配置

- **测试库**：使用 Hypothesis 进行属性测试
- **迭代次数**：每个属性测试至少运行 100 次
- **标签格式**：`Feature: field-semantic, Property {number}: {property_text}`

### 测试覆盖

| 测试类型 | 覆盖范围 |
|----------|----------|
| 单元测试 | 模块结构、接口签名、配置加载、错误处理 |
| 属性测试 | 数据模型验证、Prompt 生成、索引文本格式、缓存行为 |
| 集成测试 | 完整推断流程、RAG 存储、LLM 调用 |

### 边界情况测试

- 空字段列表
- 只有维度字段
- 只有度量字段
- 字段没有业务描述
- 字段没有别名
- 缓存失效
- RAG 检索失败
- LLM 调用超时
