# 附录 D：数据模型传递策略

## 1. 核心原则

**不传递完整 DataModel 给 LLM**

```
原因：
1. Token 消耗大（完整数据模型可能 5000-10000 tokens）
2. 信息冗余（LLM 不需要所有字段信息）
3. 干扰决策（过多信息可能导致 LLM 混淆）
```

## 2. 传递策略

### 2.1 策略概述

```
┌─────────────────────────────────────────────────────────────────┐
│                    数据模型传递策略                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  SemanticParser:                                                │
│  ├── 不传递 DataModel                                           │
│  ├── 只传递用户问题和对话历史                                    │
│  └── 字段映射由 RAG + MapFields 工具处理                        │
│                                                                 │
│  MapFields 工具:                                                │
│  ├── RAG 检索候选字段                                           │
│  ├── 只传递 top-k 候选给 LLM（如需要）                          │
│  └── 不传递完整字段列表                                          │
│                                                                 │
│  ChainAnalyzer:                                                 │
│  ├── 传递数据结果（已查询的数据）                                │
│  ├── 传递数据画像（统计摘要）                                    │
│  └── 不传递原始 DataModel                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 各组件传递内容

| 组件 | 传递内容 | 不传递内容 |
|------|----------|-----------|
| SemanticParser | 用户问题、对话历史 | DataModel |
| MapFields | RAG 候选字段（top-k） | 完整字段列表 |
| BuildQuery | SemanticQuery | DataModel |
| ExecuteQuery | 查询参数 | DataModel |
| ChainAnalyzer | 数据结果、数据画像 | DataModel |

## 3. 数据画像（DataProfile）

### 3.1 数据画像内容

```python
class DataProfile(BaseModel):
    """数据画像 - 数据的统计摘要"""
    
    # 基本信息
    row_count: int = Field(description="行数")
    column_count: int = Field(description="列数")
    
    # 维度信息
    dimensions: List[DimensionProfile] = Field(description="维度画像")
    
    # 度量信息
    measures: List[MeasureProfile] = Field(description="度量画像")
    
    # 数据质量
    null_percentage: float = Field(description="空值比例")
    duplicate_percentage: float = Field(description="重复比例")


class DimensionProfile(BaseModel):
    """维度画像"""
    field: str = Field(description="字段名")
    cardinality: int = Field(description="基数（唯一值数量）")
    top_values: List[str] = Field(description="Top 5 值")


class MeasureProfile(BaseModel):
    """度量画像"""
    field: str = Field(description="字段名")
    min: float = Field(description="最小值")
    max: float = Field(description="最大值")
    mean: float = Field(description="平均值")
    median: float = Field(description="中位数")
```

### 3.2 数据画像生成

```python
class DataProfiler:
    """数据画像生成器"""
    
    def profile(self, data: pd.DataFrame) -> DataProfile:
        """生成数据画像"""
        return DataProfile(
            row_count=len(data),
            column_count=len(data.columns),
            dimensions=self._profile_dimensions(data),
            measures=self._profile_measures(data),
            null_percentage=data.isnull().mean().mean(),
            duplicate_percentage=data.duplicated().mean(),
        )
```

## 4. Token 消耗对比

### 4.1 传递完整 DataModel

```
假设数据模型有 100 个字段：
- 字段名：平均 20 字符
- 字段描述：平均 50 字符
- 字段类型：平均 10 字符
- 总计：100 × (20 + 50 + 10) = 8000 字符 ≈ 2000 tokens

每次 LLM 调用都传递 → 2000 tokens × N 次调用
```

### 4.2 使用 RAG + Candidate Fields

```
假设每次映射 5 个业务术语：
- RAG 返回 top-5 候选
- 每个候选：字段名 + 相似度 ≈ 30 字符
- 总计：5 × 5 × 30 = 750 字符 ≈ 200 tokens

Token 节省：(2000 - 200) / 2000 = 90%
```

## 5. 实现细节

### 5.1 SemanticParser 不传递 DataModel

```python
class UnifiedSemanticComponent:
    """统一语义解析组件"""
    
    async def parse(
        self,
        question: str,
        history: List[Dict],
        # 注意：不传递 data_model
    ) -> UnifiedSemanticOutput:
        """解析用户问题"""
        prompt = self._build_prompt(question, history)
        # 不包含 data_model 信息
        return await self._invoke_llm(prompt)
```

### 5.2 MapFields 使用 RAG 候选

```python
class MapFieldsTool:
    """字段映射工具"""
    
    async def map_field(
        self,
        business_term: str,
        data_model: DataModel,  # 用于 RAG 检索，不传给 LLM
    ) -> MappedFieldItem:
        """映射单个字段"""
        # 1. RAG 检索候选
        candidates = await self._rag_search(business_term, data_model)
        
        # 2. 高置信度直接返回
        if candidates[0].confidence >= 0.9:
            return self._create_result(candidates[0], "rag_direct")
        
        # 3. LLM 从候选中选择（只传候选，不传完整 data_model）
        selected = await self._llm_select(business_term, candidates)
        return self._create_result(selected, "rag_llm_fallback")
```

### 5.3 ChainAnalyzer 使用数据画像

```python
class ChainAnalyzer:
    """链式分析器"""
    
    async def analyze(
        self,
        data: pd.DataFrame,
        profile: DataProfile,  # 数据画像，不是 DataModel
        accumulated_insights: List[Insight],
    ) -> ChainAnalyzerOutput:
        """分析数据"""
        prompt = self._build_prompt(
            data=data,
            profile=profile,  # 传递数据画像
            accumulated_insights=accumulated_insights,
        )
        return await self._invoke_llm(prompt)
```

## 6. 监控指标

| 指标 | 说明 | 目标 |
|------|------|------|
| avg_tokens_per_call | 每次 LLM 调用的平均 Token 数 | < 2000 |
| data_model_token_ratio | DataModel 占总 Token 的比例 | < 10% |
| rag_candidate_count | RAG 候选字段数量 | 3-5 |
