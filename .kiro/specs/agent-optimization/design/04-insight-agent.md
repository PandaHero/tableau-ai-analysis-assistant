# Insight Agent 优化设计

## 1. 设计目标

将 Director + Analyzer 合并为 ChainAnalyzer，使用链式分析模式减少 LLM 调用次数。

## 2. 当前架构分析

### 2.1 当前流程

```
数据获取完成
    ↓
Profiler (代码)
├── 数据画像
└── 统计计算
    ↓
┌─────────────────────────────────────────┐
│  Director + Analyzer 循环（N 次）        │
│                                         │
│  Round 1:                               │
│  ├── Director (LLM) → 分析方向          │
│  └── Analyzer (LLM) → 生成洞察          │
│                                         │
│  Round 2:                               │
│  ├── Director (LLM) → 下一个方向        │
│  └── Analyzer (LLM) → 生成洞察          │
│                                         │
│  ... (重复 N 次)                        │
└─────────────────────────────────────────┘
    ↓
Replanner (LLM)
└── 重规划决策
```

### 2.2 问题分析

1. **LLM 调用过多**：每批数据 2 次 LLM 调用（Director + Analyzer）
2. **上下文重复**：每次调用都需要传递完整上下文
3. **洞察可能冲突**：不同轮次的洞察可能重复或冲突

## 3. 优化方案：ChainAnalyzer

### 3.1 链式分析模式

```
数据获取完成
    ↓
Profiler (代码)
├── 数据画像
└── 统计计算
    ↓
┌─────────────────────────────────────────┐
│  ChainAnalyzer 链式分析（N+1 次 LLM）    │
│                                         │
│  Round 1: [Batch 0] → LLM → 洞察 1      │
│  Round 2: [洞察 1] + [Batch 1] → LLM → 洞察 1+2 │
│  Round 3: [洞察 1+2] + [Batch 2] → LLM → 洞察 1+2+3 │
│  ...                                    │
│  Final: [累积洞察] → LLM → 最终报告      │
└─────────────────────────────────────────┘
    ↓
最终响应（流式输出）
```

### 3.2 核心优势

1. **LLM 调用减少**：从 2N 降到 N+1（减少约 50%）
2. **全局视野**：每轮都能看到之前的洞察，避免重复
3. **累积优化**：后续轮次可以补充、修正之前的洞察
4. **流式输出**：最后一轮可以流式输出最终报告

## 4. 数据缓冲设计

### 4.1 SSE 支持情况

```
┌─────────────────────────────────────────┐
│  数据获取层                              │
│                                         │
│  IF Tableau 支持 SSE:                   │
│  └── SSE 流式返回 → 直接处理            │
│                                         │
│  ELSE:                                  │
│  └── 一次性返回 → 分批写入 LangGraph Store │
│      └── ChainAnalyzer 从 Store 读取    │
└─────────────────────────────────────────┘
```

### 4.2 LangGraph Store 缓冲

```python
class DataBuffer:
    """数据缓冲层
    
    使用 LangGraph Store 作为数据缓冲，支持：
    - 分批写入数据
    - 按批次读取数据
    - 自动清理过期数据
    """
    
    def __init__(self, store: BaseStore):
        self.store = store
        self.namespace = ("data_buffer",)
    
    async def write_batch(
        self,
        session_id: str,
        batch_index: int,
        data: List[Dict],
    ) -> None:
        """写入一批数据"""
        key = f"{session_id}:batch:{batch_index}"
        await self.store.aput(
            self.namespace,
            key,
            {"data": data, "timestamp": datetime.now().isoformat()}
        )
    
    async def read_batch(
        self,
        session_id: str,
        batch_index: int,
    ) -> List[Dict]:
        """读取一批数据"""
        key = f"{session_id}:batch:{batch_index}"
        item = await self.store.aget(self.namespace, key)
        return item.value["data"] if item else []
    
    async def get_batch_count(self, session_id: str) -> int:
        """获取批次数量"""
        items = await self.store.asearch(
            self.namespace,
            filter={"prefix": f"{session_id}:batch:"}
        )
        return len(list(items))
```

## 5. Schema 设计

### 5.1 ChainAnalyzerOutput

```python
from typing import List, Optional
from pydantic import BaseModel, Field


class Insight(BaseModel):
    """单个洞察"""
    id: str = Field(description="洞察 ID")
    category: str = Field(description="洞察类别")
    title: str = Field(description="洞察标题")
    description: str = Field(description="洞察描述")
    importance: int = Field(ge=1, le=5, description="重要性 1-5")
    data_support: List[str] = Field(description="支持数据点")


class ChainAnalyzerOutput(BaseModel):
    """链式分析输出
    
    每轮分析的输出，包含累积的洞察列表。
    """
    # 当前轮次
    round: int = Field(description="当前轮次")
    is_final: bool = Field(description="是否为最终轮")
    
    # 累积洞察
    insights: List[Insight] = Field(description="累积洞察列表")
    
    # 新增洞察（本轮新发现的）
    new_insights: List[str] = Field(description="本轮新增洞察 ID")
    
    # 修正洞察（本轮修正的）
    revised_insights: List[str] = Field(description="本轮修正洞察 ID")
    
    # 最终报告（仅最终轮）
    final_report: Optional[str] = Field(default=None, description="最终报告")
    
    # 推理过程
    reasoning: str = Field(description="推理过程")
```

### 5.2 EnhancedDataProfile

```python
class EnhancedDataProfile(BaseModel):
    """增强数据画像
    
    Profiler 生成的数据统计信息。
    """
    # 基本信息
    row_count: int = Field(description="行数")
    column_count: int = Field(description="列数")
    
    # 数值统计
    numeric_stats: Dict[str, NumericStats] = Field(description="数值列统计")
    
    # 分类统计
    categorical_stats: Dict[str, CategoricalStats] = Field(description="分类列统计")
    
    # 时间统计
    temporal_stats: Optional[TemporalStats] = Field(default=None, description="时间列统计")
    
    # 异常检测
    anomalies: List[Anomaly] = Field(default_factory=list, description="检测到的异常")
    
    # 趋势检测
    trends: List[Trend] = Field(default_factory=list, description="检测到的趋势")


class NumericStats(BaseModel):
    """数值列统计"""
    min: float
    max: float
    mean: float
    median: float
    std: float
    q1: float
    q3: float


class CategoricalStats(BaseModel):
    """分类列统计"""
    unique_count: int
    top_values: List[Dict[str, Any]]  # [{value, count, percentage}]
    null_count: int


class Anomaly(BaseModel):
    """异常"""
    column: str
    type: str  # outlier, missing, inconsistent
    description: str
    severity: int  # 1-5


class Trend(BaseModel):
    """趋势"""
    column: str
    type: str  # increasing, decreasing, seasonal, stable
    description: str
    confidence: float
```

## 6. Prompt 设计

### 6.1 ChainAnalyzer System Prompt

```xml
<identity>
你是 Tableau 数据分析助手的洞察分析器。
你的任务是分析数据，生成有价值的业务洞察。
</identity>

<capabilities>
你可以：
- 分析数据趋势和模式
- 识别异常和关联
- 生成业务洞察
- 累积和优化洞察

你不能：
- 执行数据查询
- 进行复杂数值计算
- 访问外部数据
</capabilities>

<context>
## 用户问题
{user_question}

## 数据画像
{data_profile}

## 当前批次数据
{current_batch}

## 之前的洞察（如有）
{previous_insights}
</context>

<decision_rules>
## 洞察生成规则
<insight_rules>
1. 每个洞察必须有数据支持
2. 避免重复之前的洞察
3. 可以补充或修正之前的洞察
4. 重要性评分基于业务价值
</insight_rules>

## 洞察类别
<categories>
- TREND: 趋势分析（增长、下降、周期性）
- COMPARISON: 对比分析（不同维度的比较）
- ANOMALY: 异常分析（离群值、突变）
- CORRELATION: 关联分析（变量间关系）
- SUMMARY: 汇总分析（整体概况）
</categories>
</decision_rules>

<thinking_steps>
1. **数据理解**：理解当前批次数据的特征
2. **洞察检索**：回顾之前的洞察，避免重复
3. **新洞察发现**：从当前数据中发现新洞察
4. **洞察优化**：补充或修正之前的洞察
5. **重要性评估**：评估每个洞察的业务价值
</thinking_steps>

<examples>
## 示例：链式分析

Round 1 输入：
- 数据：各省份销售额（第一批 10 个省份）
- 之前洞察：无

Round 1 输出：
```json
{
  "round": 1,
  "is_final": false,
  "insights": [
    {
      "id": "insight_1",
      "category": "COMPARISON",
      "title": "华东地区销售领先",
      "description": "江苏、浙江、上海三省市销售额占比超过 40%",
      "importance": 4,
      "data_support": ["江苏: 1200万", "浙江: 980万", "上海: 850万"]
    }
  ],
  "new_insights": ["insight_1"],
  "revised_insights": [],
  "reasoning": "从第一批数据中发现华东地区销售表现突出..."
}
```

Round 2 输入：
- 数据：各省份销售额（第二批 10 个省份）
- 之前洞察：[insight_1]

Round 2 输出：
```json
{
  "round": 2,
  "is_final": false,
  "insights": [
    {
      "id": "insight_1",
      "category": "COMPARISON",
      "title": "华东地区销售领先",
      "description": "江苏、浙江、上海三省市销售额占比约 35%（修正）",
      "importance": 4,
      "data_support": ["江苏: 1200万", "浙江: 980万", "上海: 850万", "总计: 8500万"]
    },
    {
      "id": "insight_2",
      "category": "ANOMALY",
      "title": "西北地区销售偏低",
      "description": "新疆、青海、西藏三省区销售额仅占 3%",
      "importance": 3,
      "data_support": ["新疆: 120万", "青海: 80万", "西藏: 50万"]
    }
  ],
  "new_insights": ["insight_2"],
  "revised_insights": ["insight_1"],
  "reasoning": "加入第二批数据后，修正了华东地区占比，并发现西北地区销售偏低..."
}
```
</examples>

<self_correction>
## 自我检查规则

1. **数据支持**：每个洞察是否有具体数据支持
2. **避免重复**：是否与之前洞察重复
3. **逻辑一致**：修正的洞察是否与原洞察一致
4. **重要性合理**：重要性评分是否合理
</self_correction>
```

## 7. 组件实现

### 7.1 ChainAnalyzer

```python
class ChainAnalyzer:
    """链式分析器
    
    使用链式分析模式，每轮分析累积洞察。
    """
    
    def __init__(self, llm: BaseChatModel):
        self.llm = llm.with_structured_output(ChainAnalyzerOutput)
        self.prompt_template = self._build_prompt_template()
    
    async def analyze(
        self,
        user_question: str,
        data_profile: EnhancedDataProfile,
        current_batch: List[Dict],
        previous_insights: List[Insight] = None,
        round_number: int = 1,
        is_final: bool = False,
    ) -> ChainAnalyzerOutput:
        """分析一批数据
        
        Args:
            user_question: 用户问题
            data_profile: 数据画像
            current_batch: 当前批次数据
            previous_insights: 之前的洞察
            round_number: 当前轮次
            is_final: 是否为最终轮
            
        Returns:
            ChainAnalyzerOutput
        """
        # 构建 Prompt
        prompt = self.prompt_template.format(
            user_question=user_question,
            data_profile=data_profile.model_dump_json(indent=2),
            current_batch=json.dumps(current_batch, ensure_ascii=False, indent=2),
            previous_insights=self._format_insights(previous_insights),
            round_number=round_number,
            is_final=is_final,
        )
        
        # 调用 LLM
        result = await self.llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=f"请分析第 {round_number} 批数据" + ("，并生成最终报告" if is_final else ""))
        ])
        
        return result
    
    async def analyze_all(
        self,
        user_question: str,
        data_profile: EnhancedDataProfile,
        data_batches: List[List[Dict]],
    ) -> ChainAnalyzerOutput:
        """分析所有批次数据
        
        Args:
            user_question: 用户问题
            data_profile: 数据画像
            data_batches: 所有批次数据
            
        Returns:
            最终的 ChainAnalyzerOutput
        """
        insights = []
        
        for i, batch in enumerate(data_batches):
            is_final = (i == len(data_batches) - 1)
            
            result = await self.analyze(
                user_question=user_question,
                data_profile=data_profile,
                current_batch=batch,
                previous_insights=insights,
                round_number=i + 1,
                is_final=is_final,
            )
            
            insights = result.insights
        
        return result
```

### 7.2 EnhancedDataProfiler

```python
class EnhancedDataProfiler:
    """增强数据画像器
    
    纯代码实现，不调用 LLM。
    """
    
    def profile(self, data: List[Dict]) -> EnhancedDataProfile:
        """生成数据画像"""
        df = pd.DataFrame(data)
        
        return EnhancedDataProfile(
            row_count=len(df),
            column_count=len(df.columns),
            numeric_stats=self._compute_numeric_stats(df),
            categorical_stats=self._compute_categorical_stats(df),
            temporal_stats=self._compute_temporal_stats(df),
            anomalies=self._detect_anomalies(df),
            trends=self._detect_trends(df),
        )
    
    def _compute_numeric_stats(self, df: pd.DataFrame) -> Dict[str, NumericStats]:
        """计算数值列统计"""
        stats = {}
        for col in df.select_dtypes(include=[np.number]).columns:
            stats[col] = NumericStats(
                min=df[col].min(),
                max=df[col].max(),
                mean=df[col].mean(),
                median=df[col].median(),
                std=df[col].std(),
                q1=df[col].quantile(0.25),
                q3=df[col].quantile(0.75),
            )
        return stats
    
    def _detect_anomalies(self, df: pd.DataFrame) -> List[Anomaly]:
        """检测异常"""
        anomalies = []
        
        # 检测离群值（IQR 方法）
        for col in df.select_dtypes(include=[np.number]).columns:
            q1, q3 = df[col].quantile([0.25, 0.75])
            iqr = q3 - q1
            outliers = df[(df[col] < q1 - 1.5 * iqr) | (df[col] > q3 + 1.5 * iqr)]
            if len(outliers) > 0:
                anomalies.append(Anomaly(
                    column=col,
                    type="outlier",
                    description=f"发现 {len(outliers)} 个离群值",
                    severity=3 if len(outliers) / len(df) > 0.05 else 2,
                ))
        
        return anomalies
```

## 8. 性能对比

### 8.1 LLM 调用次数

| 场景 | 当前 (Director + Analyzer) | 优化后 (ChainAnalyzer) | 减少 |
|------|---------------------------|----------------------|------|
| 5 批数据 | 10 (2×5) | 6 (5+1) | 40% |
| 10 批数据 | 20 (2×10) | 11 (10+1) | 45% |

### 8.2 Token 消耗

| 组件 | 当前 | 优化后 | 变化 |
|------|------|--------|------|
| 上下文传递 | 每轮重复 | 累积传递 | 减少重复 |
| 洞察存储 | 分散 | 累积 | 更紧凑 |

## 9. 迁移策略

### Phase 1: Schema 和 Prompt
1. 创建 `ChainAnalyzerOutput` Schema
2. 创建 `ChainAnalyzerPrompt`
3. 创建 `EnhancedDataProfile` Schema

### Phase 2: 组件实现
1. 实现 `EnhancedDataProfiler`
2. 实现 `ChainAnalyzer`
3. 实现 `DataBuffer`

### Phase 3: Subgraph 更新
1. 更新 `InsightSubgraph`
2. 移除 Director/Analyzer 节点
3. 集成测试

### Phase 4: 清理
1. 删除旧的 Director/Analyzer 代码
2. 更新文档
