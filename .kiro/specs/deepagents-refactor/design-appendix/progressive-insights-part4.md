# 渐进式洞察系统详细设计 - Part 4

## 2.11 SummaryGenerator（摘要生成器）

**职责**：基于最终洞察生成执行摘要。

**摘要结构**：

```python
class ExecutiveSummary(BaseModel):
    """执行摘要"""
    overview: str  # 总体概述
    key_findings: List[str]  # 关键发现（3-5条）
    data_quality_note: Optional[str]  # 数据质量说明
    analysis_scope: str  # 分析范围说明
```

**实现**：

```python
class SummaryGenerator:
    """摘要生成器"""
    
    def __init__(self, llm_client: Any):
        self.llm = llm_client
    
    async def generate_summary(
        self,
        final_insights: List[FinalInsight],
        context: Dict
    ) -> ExecutiveSummary:
        """生成执行摘要"""
        
        # 1. 准备输入
        prompt = self._prepare_prompt(final_insights, context)
        
        # 2. 调用LLM
        response = await self.llm.ainvoke(prompt)
        
        # 3. 解析响应
        summary = self._parse_response(response.content)
        
        return summary
    
    def _prepare_prompt(
        self,
        insights: List[FinalInsight],
        context: Dict
    ) -> str:
        """准备Prompt"""
        
        # 提取Top洞察
        top_insights = insights[:5]
        
        insights_text = "\n".join([
            f"{i+1}. {insight.title}\n   {insight.description}\n   证据: {', '.join(insight.evidence[:3])}"
            for i, insight in enumerate(top_insights)
        ])
        
        prompt = f"""
你是一个数据分析专家。请基于以下洞察生成执行摘要。

**用户问题**: {context.get('question', '')}

**关键洞察**:
{insights_text}

**任务**:
生成一个简洁的执行摘要，包括：
1. 总体概述（2-3句话）
2. 关键发现（3-5条，每条一句话）
3. 数据质量说明（如果有问题）
4. 分析范围说明

**输出格式**（JSON）:
```json
{{
  "overview": "基于对XX数据的分析，我们发现...",
  "key_findings": [
    "华东地区销售额呈上升趋势，Q3较Q1增长50%",
    "存在3个异常值，可能是数据录入错误",
    "产品A与产品B销售额呈正相关"
  ],
  "data_quality_note": "数据完整性良好，但存在3个异常值需要关注",
  "analysis_scope": "分析了前200行数据（共500行），覆盖了主要趋势和异常"
}}

"""
        return prompt
    
    def _parse_response(self, response: str) -> ExecutiveSummary:
        """解析LLM响应"""
        try:
            data = json.loads(response)
            return ExecutiveSummary(**data)
        except Exception as e:
            logger.error(f"Failed to parse summary response: {e}")
            # 返回默认摘要
            return ExecutiveSummary(
                overview="分析完成",
                key_findings=["分析结果已生成"],
                data_quality_note=None,
                analysis_scope="完整数据集"
            )
```

---

## 2.12 RecommendGenerator（建议生成器）

**职责**：基于洞察生成行动建议。

**建议类型**：

1. **数据质量改进**：针对发现的数据问题
2. **业务行动**：针对发现的业务机会或风险
3. **进一步分析**：建议的后续分析方向

**实现**：

```python
class Recommendation(BaseModel):
    """建议"""
    type: str  # "data_quality" / "business_action" / "further_analysis"
    priority: str  # "high" / "medium" / "low"
    description: str
    rationale: str

class RecommendGenerator:
    """建议生成器"""
    
    def __init__(self, llm_client: Any):
        self.llm = llm_client
    
    async def generate_recommendations(
        self,
        final_insights: List[FinalInsight],
        context: Dict
    ) -> List[Recommendation]:
        """生成建议"""
        
        # 1. 准备输入
        prompt = self._prepare_prompt(final_insights, context)
        
        # 2. 调用LLM
        response = await self.llm.ainvoke(prompt)
        
        # 3. 解析响应
        recommendations = self._parse_response(response.content)
        
        return recommendations
    
    def _prepare_prompt(
        self,
        insights: List[FinalInsight],
        context: Dict
    ) -> str:
        """准备Prompt"""
        
        insights_text = "\n".join([
            f"- {insight.title}: {insight.description}"
            for insight in insights[:5]
        ])
        
        prompt = f"""
你是一个数据分析顾问。请基于以下洞察生成行动建议。

**用户问题**: {context.get('question', '')}

**关键洞察**:
{insights_text}

**任务**:
生成3-5条行动建议，包括：
1. 数据质量改进建议（如果发现数据问题）
2. 业务行动建议（基于发现的趋势和模式）
3. 进一步分析建议（建议的后续分析方向）

每条建议必须包含：
- 类型（data_quality/business_action/further_analysis）
- 优先级（high/medium/low）
- 描述（具体的行动建议）
- 理由（为什么需要这个行动）

**输出格式**（JSON）:
```json
[
  {{
    "type": "data_quality",
    "priority": "high",
    "description": "检查并修正3个异常销售额数据",
    "rationale": "发现3个销售额异常值（Z-score>3），可能是数据录入错误"
  }},
  {{
    "type": "business_action",
    "priority": "high",
    "description": "加大华东地区市场投入",
    "rationale": "华东地区销售额呈持续上升趋势，市场潜力大"
  }},
  {{
    "type": "further_analysis",
    "priority": "medium",
    "description": "分析产品A和产品B的关联销售策略",
    "rationale": "两者销售额呈正相关，可能存在关联销售机会"
  }}
]

"""
        return prompt
    
    def _parse_response(self, response: str) -> List[Recommendation]:
        """解析LLM响应"""
        try:
            data = json.loads(response)
            return [Recommendation(**item) for item in data]
        except Exception as e:
            logger.error(f"Failed to parse recommendations response: {e}")
            return []
```

---

## 3. 完整工作流程

### 3.1 主流程

```python
from typing import Optional
import pandas as pd

class ProgressiveInsightSystem:
    """渐进式洞察系统"""
    
    def __init__(
        self,
        llm_client: Any,
        chunk_size: int = 100,
        max_chunks: int = 10
    ):
        # 初始化组件
        self.coordinator = ProgressiveInsightCoordinator()
        self.profiler = DataProfiler()
        self.chunker = SemanticChunker(chunk_size=chunk_size)
        self.pattern_detector = PatternDetector()
        self.anomaly_detector = AnomalyDetector()
        self.chunk_analyzer = ChunkAnalyzer(
            pattern_detector=self.pattern_detector,
            anomaly_detector=self.anomaly_detector,
            llm_client=llm_client
        )
        self.accumulator = InsightAccumulator(max_chunks=max_chunks)
        self.synthesizer = InsightSynthesizer()
        self.summary_generator = SummaryGenerator(llm_client)
        self.recommend_generator = RecommendGenerator(llm_client)
    
    async def analyze(
        self,
        df: pd.DataFrame,
        question: str,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        分析数据并生成洞察
        
        Args:
            df: 数据DataFrame
            question: 用户问题
            context: 上下文信息
        
        Returns:
            分析结果字典
        """
        
        context = context or {}
        context['question'] = question
        
        # 1. 决策：直接分析 vs 渐进式分析
        strategy = self.coordinator.decide_strategy(
            data_size=len(df),
            complexity=context.get('complexity', 'medium'),
            available_budget=context.get('budget', 100000)
        )
        
        if strategy == "direct":
            return await self._direct_analysis(df, context)
        else:
            return await self._progressive_analysis(df, context)
    
    async def _direct_analysis(
        self,
        df: pd.DataFrame,
        context: Dict
    ) -> Dict:
        """直接分析（小数据集）"""
        
        # 创建单个块
        chunk = DataChunk(
            chunk_id=1,
            priority=1,
            row_indices=list(range(len(df))),
            description="完整数据集",
            estimated_importance=1.0
        )
        
        # 分析
        insights = await self.chunk_analyzer.analyze_chunk(df, chunk, context)
        
        # 合成
        final_insights = self.synthesizer.synthesize(
            AccumulatedInsights(
                insights=insights,
                total_chunks_analyzed=1,
                should_stop=True,
                stop_reason="直接分析",
                confidence_score=0.9
            )
        )
        
        # 生成摘要和建议
        summary = await self.summary_generator.generate_summary(final_insights, context)
        recommendations = await self.recommend_generator.generate_recommendations(
            final_insights, context
        )
        
        return {
            "strategy": "direct",
            "insights": final_insights,
            "summary": summary,
            "recommendations": recommendations,
            "metadata": {
                "total_rows": len(df),
                "chunks_analyzed": 1
            }
        }
    
    async def _progressive_analysis(
        self,
        df: pd.DataFrame,
        context: Dict
    ) -> Dict:
        """渐进式分析（大数据集）"""
        
        # 1. 生成数据画像
        profile = self.profiler.generate_profile(df)
        
        # 2. 智能分块
        chunks = self.chunker.chunk_data(df, profile)
        
        # 3. 逐块分析
        accumulated = None
        chunks_analyzed = 0
        
        for chunk in chunks:
            # 分析当前块
            chunk_insights = await self.chunk_analyzer.analyze_chunk(df, chunk, context)
            
            # 累积洞察
            accumulated = self.accumulator.accumulate(chunk_insights, chunk)
            chunks_analyzed += 1
            
            # 检查早停
            if accumulated.should_stop:
                logger.info(f"Early stop: {accumulated.stop_reason}")
                break
        
        # 4. 合成最终洞察
        final_insights = self.synthesizer.synthesize(accumulated)
        
        # 5. 生成摘要和建议
        summary = await self.summary_generator.generate_summary(final_insights, context)
        recommendations = await self.recommend_generator.generate_recommendations(
            final_insights, context
        )
        
        return {
            "strategy": "progressive",
            "insights": final_insights,
            "summary": summary,
            "recommendations": recommendations,
            "metadata": {
                "total_rows": len(df),
                "chunks_analyzed": chunks_analyzed,
                "total_chunks": len(chunks),
                "early_stop": accumulated.should_stop,
                "stop_reason": accumulated.stop_reason,
                "confidence_score": accumulated.confidence_score
            }
        }
```

### 3.2 使用示例

```python
# 初始化系统
llm_client = ChatAnthropic(model="claude-3-5-sonnet-20241022")
system = ProgressiveInsightSystem(
    llm_client=llm_client,
    chunk_size=100,
    max_chunks=10
)

# 分析数据
df = pd.read_csv("sales_data.csv")  # 500行数据
result = await system.analyze(
    df=df,
    question="华东地区的销售趋势如何？",
    context={
        "complexity": "medium",
        "budget": 50000  # Token预算
    }
)

# 输出结果
print(f"分析策略: {result['strategy']}")
print(f"分析块数: {result['metadata']['chunks_analyzed']}")
print(f"\n执行摘要:")
print(result['summary'].overview)
print(f"\n关键发现:")
for finding in result['summary'].key_findings:
    print(f"- {finding}")
print(f"\n建议:")
for rec in result['recommendations']:
    print(f"- [{rec.priority}] {rec.description}")
```

---

## 4. 性能优化

### 4.1 并行处理

对于独立的数据块，可以并行分析：

```python
import asyncio

async def _progressive_analysis_parallel(
    self,
    df: pd.DataFrame,
    context: Dict
) -> Dict:
    """渐进式分析（并行版本）"""
    
    # 1. 生成数据画像
    profile = self.profiler.generate_profile(df)
    
    # 2. 智能分块
    chunks = self.chunker.chunk_data(df, profile)
    
    # 3. 并行分析前N个块
    N = min(3, len(chunks))  # 并行分析前3个块
    tasks = [
        self.chunk_analyzer.analyze_chunk(df, chunk, context)
        for chunk in chunks[:N]
    ]
    
    chunk_insights_list = await asyncio.gather(*tasks)
    
    # 4. 累积洞察
    accumulated = None
    for i, chunk_insights in enumerate(chunk_insights_list):
        accumulated = self.accumulator.accumulate(chunk_insights, chunks[i])
        
        if accumulated.should_stop:
            break
    
    # 5. 如果需要，继续分析后续块（串行）
    if not accumulated.should_stop:
        for chunk in chunks[N:]:
            chunk_insights = await self.chunk_analyzer.analyze_chunk(df, chunk, context)
            accumulated = self.accumulator.accumulate(chunk_insights, chunk)
            
            if accumulated.should_stop:
                break
    
    # 6. 合成最终洞察
    final_insights = self.synthesizer.synthesize(accumulated)
    
    # ... 后续步骤同串行版本
```

### 4.2 缓存优化

对于相似的数据块，可以复用分析结果：

```python
class CachedChunkAnalyzer(ChunkAnalyzer):
    """带缓存的块分析器"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cache = {}
    
    async def analyze_chunk(
        self,
        df: pd.DataFrame,
        chunk: DataChunk,
        context: Dict
    ) -> List[ChunkInsight]:
        """分析数据块（带缓存）"""
        
        # 生成缓存Key
        chunk_df = df.iloc[chunk.row_indices]
        cache_key = self._generate_cache_key(chunk_df, context)
        
        # 检查缓存
        if cache_key in self.cache:
            logger.info(f"Cache hit for chunk {chunk.chunk_id}")
            return self.cache[cache_key]
        
        # 分析
        insights = await super().analyze_chunk(df, chunk, context)
        
        # 保存到缓存
        self.cache[cache_key] = insights
        
        return insights
    
    def _generate_cache_key(self, df: pd.DataFrame, context: Dict) -> str:
        """生成缓存Key"""
        # 简化：基于数据摘要和问题
        data_hash = hashlib.md5(df.to_string().encode()).hexdigest()
        question_hash = hashlib.md5(context.get('question', '').encode()).hexdigest()
        return f"{data_hash}_{question_hash}"
```

---

## 5. 监控和调试

### 5.1 性能指标

```python
class PerformanceMetrics(BaseModel):
    """性能指标"""
    total_time: float  # 总耗时（秒）
    chunks_analyzed: int  # 分析块数
    total_chunks: int  # 总块数
    early_stop: bool  # 是否早停
    llm_calls: int  # LLM调用次数
    total_tokens: int  # 总Token数
    cost_estimate: float  # 成本估算（美元）

# 在分析过程中收集指标
import time

start_time = time.time()
llm_calls = 0
total_tokens = 0

# ... 分析过程 ...

metrics = PerformanceMetrics(
    total_time=time.time() - start_time,
    chunks_analyzed=chunks_analyzed,
    total_chunks=len(chunks),
    early_stop=accumulated.should_stop,
    llm_calls=llm_calls,
    total_tokens=total_tokens,
    cost_estimate=total_tokens * 0.000003  # Claude价格
)
```

### 5.2 调试日志

```python
import logging

logger = logging.getLogger(__name__)

# 在关键步骤添加日志
logger.info(f"Strategy: {strategy}")
logger.info(f"Data profile: {profile.total_rows} rows, {profile.total_columns} columns")
logger.info(f"Chunks: {len(chunks)}")
logger.info(f"Analyzing chunk {chunk.chunk_id}/{len(chunks)}")
logger.info(f"Accumulated insights: {len(accumulated.insights)}")
logger.info(f"Early stop: {accumulated.should_stop}, reason: {accumulated.stop_reason}")
```

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15

