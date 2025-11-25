# 渐进式累积洞察分析 - 实现方案

## 1. 核心实现策略

### 1.1 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Coordinator (主持人层)                              │
│ - 决策：选择分析策略                                          │
│ - 编排：控制分析流程                                          │
│ - 监控：跟踪质量和进度                                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Processing (处理层)                                 │
│ - Map: 并行分析数据块                                         │
│ - Accumulate: 累积洞察                                        │
│ - Filter: 质量过滤                                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Synthesis (合成层)                                  │
│ - Reduce: 合成最终洞察                                        │
│ - Summarize: 生成摘要                                         │
│ - Recommend: 提供建议                                         │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 关键设计模式

#### A. Map-Reduce Pattern (借鉴 LangChain)

```python
# Map 阶段：并行分析每个数据块
map_results = await asyncio.gather(*[
    analyze_chunk(chunk, context)
    for chunk in chunks
])

# Reduce 阶段：合成最终洞察
final_insights = reduce_insights(map_results)
```

#### B. Accumulator Pattern (借鉴 BettaFish)

```python
# 累积器模式
accumulator = InsightAccumulator()

for chunk_insights in map_results:
    # 过滤
    filtered = quality_filter(chunk_insights)
    
    # 累积
    accumulator.add(filtered)
    
    # 流式输出
    yield accumulator.get_current_state()
```

#### C. Coordinator Pattern (借鉴 BettaFish)

```python
# 主持人模式
class AnalysisCoordinator:
    async def coordinate(self, data):
        # 1. 评估
        strategy = self.evaluate_strategy(data)
        
        # 2. 执行
        if strategy == "direct":
            return await self.direct_analysis(data)
        else:
            return await self.progressive_analysis(data)
```

## 2. 详细实现

### 2.1 Coordinator (主持人)

```python
class AnalysisCoordinator:
    """
    分析协调器
    
    职责：
    1. 评估数据规模和复杂度
    2. 选择分析策略
    3. 监控分析质量
    4. 控制流程节奏
    """
    
    def __init__(self):
        self.profiler = DataProfiler()
        self.chunker = SemanticChunker()
        self.analyzer = ChunkAnalyzer()
        self.accumulator = InsightAccumulator()
        self.synthesizer = InsightSynthesizer()
    
    async def analyze(
        self,
        data: DataFrame,
        context: Dict
    ) -> InsightResult:
        """主分析流程"""
        
        # 1. 数据画像
        profile = self.profiler.profile(data)
        
        # 2. 选择策略
        strategy = self._select_strategy(profile)
        
        # 3. 执行分析
        if strategy == "direct":
            return await self._direct_analysis(data, context)
        elif strategy == "progressive":
            return await self._progressive_analysis(data, context, profile)
        elif strategy == "hybrid":
            return await self._hybrid_analysis(data, context, profile)
    
    def _select_strategy(self, profile: DataProfile) -> str:
        """
        选择分析策略
        
        规则：
        - 小数据（< 100 行）→ direct
        - 中等数据（100-1000 行）→ progressive
        - 大数据（> 1000 行）→ hybrid
        """
        if profile.row_count < 100:
            return "direct"
        elif profile.row_count < 1000:
            return "progressive"
        else:
            return "hybrid"
    
    async def _progressive_analysis(
        self,
        data: DataFrame,
        context: Dict,
        profile: DataProfile
    ) -> InsightResult:
        """
        渐进式分析（核心流程）
        """
        
        # 1. 语义分块
        chunks = self.chunker.chunk(data, profile)
        
        # 2. 初始化累积器
        self.accumulator.reset()
        
        # 3. 渐进式分析
        for i, chunk in enumerate(chunks):
            # 3.1 分析当前块
            chunk_insights = await self.analyzer.analyze(
                chunk=chunk,
                chunk_index=i,
                previous_context=self.accumulator.get_context(),
                global_context=context
            )
            
            # 3.2 质量过滤
            filtered = self._filter_quality(chunk_insights)
            
            # 3.3 累积
            self.accumulator.add(filtered)
            
            # 3.4 流式输出
            yield {
                "event": "chunk_analyzed",
                "progress": f"{i+1}/{len(chunks)}",
                "insights": filtered,
                "accumulated_count": len(self.accumulator.insights)
            }
            
            # 3.5 自适应调整
            if self._should_adjust(chunk_insights):
                chunks = self._adjust_chunks(chunks, i, chunk_insights)
        
        # 4. 合成最终洞察
        final_insights = self.synthesizer.synthesize(
            self.accumulator.insights
        )
        
        return final_insights
```

### 2.2 Data Profiler (数据画像)

```python
class DataProfiler:
    """
    数据画像器
    
    职责：
    1. 分析数据特征
    2. 评估数据质量
    3. 推荐分块策略
    """
    
    def profile(self, data: DataFrame) -> DataProfile:
        """生成数据画像"""
        
        return DataProfile(
            row_count=len(data),
            column_count=len(data.columns),
            density=self._calculate_density(data),
            anomaly_ratio=self._calculate_anomaly_ratio(data),
            complexity=self._calculate_complexity(data),
            semantic_groups=self._identify_semantic_groups(data),
            recommended_chunk_size=self._recommend_chunk_size(data)
        )
    
    def _calculate_density(self, data: DataFrame) -> float:
        """
        计算数据密度
        
        密度 = 非空值比例 * 数值列比例
        """
        non_null_ratio = data.count().sum() / (len(data) * len(data.columns))
        numeric_ratio = len(data.select_dtypes(include=[np.number]).columns) / len(data.columns)
        return non_null_ratio * numeric_ratio
    
    def _calculate_anomaly_ratio(self, data: DataFrame) -> float:
        """
        计算异常值比例
        
        使用 IQR 方法检测异常值
        """
        numeric_cols = data.select_dtypes(include=[np.number]).columns
        anomaly_count = 0
        total_count = 0
        
        for col in numeric_cols:
            Q1 = data[col].quantile(0.25)
            Q3 = data[col].quantile(0.75)
            IQR = Q3 - Q1
            
            anomalies = ((data[col] < Q1 - 1.5 * IQR) | 
                        (data[col] > Q3 + 1.5 * IQR)).sum()
            
            anomaly_count += anomalies
            total_count += len(data)
        
        return anomaly_count / total_count if total_count > 0 else 0
    
    def _identify_semantic_groups(self, data: DataFrame) -> List[str]:
        """
        识别语义分组
        
        常见分组：
        - 时间列：date, datetime, timestamp
        - 类别列：category, type, class
        - 地理列：region, city, country
        """
        semantic_groups = []
        
        for col in data.columns:
            col_lower = col.lower()
            
            if any(kw in col_lower for kw in ['date', 'time', 'year', 'month']):
                semantic_groups.append(('time', col))
            elif any(kw in col_lower for kw in ['category', 'type', 'class', 'group']):
                semantic_groups.append(('category', col))
            elif any(kw in col_lower for kw in ['region', 'city', 'country', 'location']):
                semantic_groups.append(('geography', col))
        
        return semantic_groups
```

### 2.3 Semantic Chunker (语义分块器)

```python
class SemanticChunker:
    """
    语义分块器
    
    职责：
    1. 按业务逻辑分块
    2. 保持数据完整性
    3. 自适应块大小
    """
    
    def chunk(
        self,
        data: DataFrame,
        profile: DataProfile
    ) -> List[DataFrame]:
        """智能分块"""
        
        # 1. 选择分块策略
        strategy = self._select_strategy(profile)
        
        # 2. 执行分块
        if strategy == "semantic":
            return self._semantic_chunk(data, profile)
        elif strategy == "adaptive":
            return self._adaptive_chunk(data, profile)
        else:
            return self._fixed_chunk(data, profile.recommended_chunk_size)
    
    def _semantic_chunk(
        self,
        data: DataFrame,
        profile: DataProfile
    ) -> List[DataFrame]:
        """
        语义分块
        
        策略：
        1. 优先按时间分块（每月、每周）
        2. 其次按类别分块
        3. 最后按地理分块
        """
        chunks = []
        
        # 查找语义分组列
        for group_type, col in profile.semantic_groups:
            if group_type == "time":
                # 按时间分块
                if pd.api.types.is_datetime64_any_dtype(data[col]):
                    # 按月分块
                    for month, group in data.groupby(data[col].dt.to_period('M')):
                        if len(group) > 0:
                            chunks.append(group)
                    return chunks
            
            elif group_type == "category":
                # 按类别分块
                for category, group in data.groupby(col):
                    if len(group) > 0:
                        chunks.append(group)
                return chunks
        
        # 如果没有语义列，使用自适应分块
        return self._adaptive_chunk(data, profile)
    
    def _adaptive_chunk(
        self,
        data: DataFrame,
        profile: DataProfile
    ) -> List[DataFrame]:
        """
        自适应分块
        
        根据数据特征动态调整块大小
        """
        base_size = profile.recommended_chunk_size
        
        # 根据密度调整
        if profile.density > 0.8:
            chunk_size = int(base_size * 0.5)
        elif profile.density > 0.5:
            chunk_size = base_size
        else:
            chunk_size = int(base_size * 1.5)
        
        # 根据异常值调整
        if profile.anomaly_ratio > 0.1:
            chunk_size = int(chunk_size * 0.7)
        
        return self._fixed_chunk(data, chunk_size)
```

### 2.4 Chunk Analyzer (块分析器)

```python
class ChunkAnalyzer:
    """
    数据块分析器
    
    职责：
    1. 分析单个数据块
    2. 提取关键信息
    3. 识别模式和异常
    """
    
    async def analyze(
        self,
        chunk: DataFrame,
        chunk_index: int,
        previous_context: str,
        global_context: Dict
    ) -> List[Insight]:
        """
        分析数据块
        
        关键：利用之前的洞察作为上下文
        """
        
        # 1. 生成统计摘要
        stats = self._generate_statistics(chunk)
        
        # 2. 构建 Prompt
        prompt = self._build_prompt(
            chunk_index=chunk_index,
            stats=stats,
            previous_context=previous_context,
            global_context=global_context
        )
        
        # 3. 调用 LLM
        response = await self.llm.ainvoke(prompt)
        
        # 4. 解析洞察
        insights = self._parse_insights(response)
        
        return insights
    
    def _build_prompt(
        self,
        chunk_index: int,
        stats: Dict,
        previous_context: str,
        global_context: Dict
    ) -> str:
        """
        构建分析 Prompt
        
        关键：包含之前的洞察作为上下文
        """
        return f"""
你是一个数据分析专家，正在进行渐进式数据分析。

**当前任务**：分析第 {chunk_index + 1} 块数据

**数据统计摘要**：
{json.dumps(stats, indent=2, ensure_ascii=False)}

**之前的发现**（已经分析过的数据）：
{previous_context}

**全局上下文**：
- 用户问题：{global_context.get('question', 'N/A')}
- 分析目标：{global_context.get('goal', 'N/A')}

**分析要求**：
1. 识别这块数据的关键模式和趋势
2. 发现异常值或有趣的现象
3. 与之前的发现进行对比和关联
4. **只报告新的、有价值的洞察**（避免重复）

**输出格式**（JSON）：
{{
  "insights": [
    {{
      "type": "trend|anomaly|pattern|comparison",
      "title": "简短标题",
      "description": "详细描述",
      "confidence": 0.0-1.0,
      "evidence": ["支持证据1", "支持证据2"],
      "priority": "high|medium|low"
    }}
  ]
}}

**注意**：
- 避免重复之前已经发现的洞察
- 关注新的模式和变化
- 提供具体的数值支持
"""
```

### 2.5 Insight Accumulator (洞察累积器)

```python
class InsightAccumulator:
    """
    洞察累积器
    
    职责：
    1. 累积洞察
    2. 去重和合并
    3. 优先级排序
    """
    
    def __init__(self):
        self.insights: List[Insight] = []
        self.categories = {
            "trends": [],
            "anomalies": [],
            "patterns": [],
            "comparisons": []
        }
    
    def add(self, new_insights: List[Insight]):
        """
        添加新洞察
        
        策略：
        1. 检查重复
        2. 合并相似洞察
        3. 分类存储
        """
        for insight in new_insights:
            # 1. 查找相似洞察
            similar = self._find_similar(insight)
            
            if similar:
                # 2. 合并洞察
                merged = self._merge_insights(insight, similar)
                self.insights.remove(similar)
                self.insights.append(merged)
            else:
                # 3. 添加新洞察
                self.insights.append(insight)
            
            # 4. 分类
            self.categories[insight.type].append(insight)
    
    def get_context(self) -> str:
        """
        获取当前累积的洞察摘要
        
        用于：作为下一块分析的上下文
        """
        if not self.insights:
            return "暂无发现"
        
        # 按优先级排序
        sorted_insights = sorted(
            self.insights,
            key=lambda x: x.priority_score(),
            reverse=True
        )
        
        # 生成摘要（只取前5个）
        summary_parts = []
        for insight in sorted_insights[:5]:
            summary_parts.append(
                f"- [{insight.type}] {insight.title}: {insight.description[:100]}"
            )
        
        return "\n".join(summary_parts)
    
    def _find_similar(self, insight: Insight) -> Optional[Insight]:
        """
        查找相似洞察
        
        使用：
        1. 文本相似度（embedding）
        2. 类型匹配
        3. 主题匹配
        """
        for existing in self.insights:
            if existing.type == insight.type:
                similarity = self._calculate_similarity(
                    insight.description,
                    existing.description
                )
                if similarity > 0.8:
                    return existing
        return None
    
    def _merge_insights(
        self,
        new: Insight,
        existing: Insight
    ) -> Insight:
        """
        合并两个相似洞察
        
        策略：
        1. 保留更高的置信度
        2. 合并证据
        3. 增强描述
        """
        return Insight(
            type=existing.type,
            title=existing.title,
            description=f"{existing.description} {new.description}",
            confidence=max(new.confidence, existing.confidence),
            evidence=list(set(new.evidence + existing.evidence)),
            priority=max(new.priority, existing.priority)
        )
```

## 3. 流式输出实现

```python
async def progressive_analysis_stream(
    data: DataFrame,
    context: Dict
) -> AsyncGenerator[Dict, None]:
    """
    流式渐进式分析
    
    实时输出分析进度和结果
    """
    
    coordinator = AnalysisCoordinator()
    
    # 1. 数据画像
    yield {"event": "profiling", "message": "正在分析数据特征..."}
    profile = coordinator.profiler.profile(data)
    yield {"event": "profile_complete", "profile": profile.to_dict()}
    
    # 2. 分块
    yield {"event": "chunking", "message": "正在智能分块..."}
    chunks = coordinator.chunker.chunk(data, profile)
    yield {"event": "chunks_ready", "chunk_count": len(chunks)}
    
    # 3. 渐进式分析
    for i, chunk in enumerate(chunks):
        yield {
            "event": "chunk_start",
            "chunk_index": i,
            "progress": f"{i+1}/{len(chunks)}"
        }
        
        # 分析块
        insights = await coordinator.analyzer.analyze(
            chunk, i,
            coordinator.accumulator.get_context(),
            context
        )
        
        # 过滤
        filtered = coordinator._filter_quality(insights)
        
        # 累积
        coordinator.accumulator.add(filtered)
        
        yield {
            "event": "chunk_complete",
            "chunk_index": i,
            "insights": [ins.to_dict() for ins in filtered],
            "accumulated_count": len(coordinator.accumulator.insights)
        }
    
    # 4. 合成
    yield {"event": "synthesizing", "message": "正在合成最终洞察..."}
    final = coordinator.synthesizer.synthesize(coordinator.accumulator.insights)
    
    yield {
        "event": "complete",
        "final_insights": final.to_dict()
    }
```

## 4. 集成到现有 Workflow

```python
# 在 Task Scheduler 中集成

async def analyze_result(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    分析结果节点（支持大数据）
    """
    task_id = state["task_id"]
    result = state["result"]
    
    # 判断数据规模
    if len(result) < 100:
        # 小数据：直接分析
        insight = await simple_analysis(result)
    else:
        # 大数据：渐进式分析
        insight = await progressive_analysis(result)
    
    yield {
        "insights": [insight]
    }
```

## 5. 性能优化

### 5.1 并行处理

```python
# 并行分析多个块
async def parallel_chunk_analysis(chunks):
    tasks = [analyze_chunk(chunk) for chunk in chunks]
    results = await asyncio.gather(*tasks)
    return results
```

### 5.2 缓存机制

```python
# 缓存相似数据块的分析结果
@lru_cache(maxsize=100)
def get_cached_analysis(chunk_hash):
    return cached_results.get(chunk_hash)
```

### 5.3 Token 优化

```python
# 智能摘要，减少 Token 使用
def compress_context(context: str, max_tokens: int) -> str:
    if len(context) > max_tokens:
        # 使用摘要模型压缩
        return summarize(context, max_length=max_tokens)
    return context
```

这个实现方案完整吗？需要我继续完善哪些部分？
