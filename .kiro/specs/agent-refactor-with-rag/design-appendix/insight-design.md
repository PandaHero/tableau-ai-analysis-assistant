# 洞察系统设计

## 概述

本文档描述洞察系统的完整设计，包括 Insight Agent 和 AnalysisCoordinator 及其所有子组件。

对应项目结构：
- `src/agents/insight/` - Insight Agent
- `src/components/insight/` - 洞察组件

---

## 设计原则

**关键设计决策**：洞察系统封装为组件（AnalysisCoordinator），而不是暴露为工具。

好处：
- 流程由代码控制，更可靠
- LLM 只负责"思考"，不负责"决策流程"
- 组件内部可以使用 LLM，但对外暴露代码接口

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           洞察系统架构                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Insight Agent (LLM 节点)                          │    │
│  │                                                                      │    │
│  │  职责：调用 AnalysisCoordinator，生成最终洞察报告                    │    │
│  │  输入：QueryResult, original_question                                │    │
│  │  输出：accumulated_insights                                          │    │
│  └────────────────────────────┬────────────────────────────────────────┘    │
│                               │                                              │
│                               │ 代码直接调用（不是工具！）                   │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                 AnalysisCoordinator (主持人层)                       │    │
│  │                                                                      │    │
│  │  职责：                                                              │    │
│  │  1. 评估数据规模和复杂度                                             │    │
│  │  2. 选择分析策略 (direct/progressive/hybrid)                         │    │
│  │  3. 编排分析流程                                                     │    │
│  │  4. 监控分析质量                                                     │    │
│  └────────────────────────────┬────────────────────────────────────────┘    │
│                               │                                              │
│           ┌───────────────────┼───────────────────┐                         │
│           │                   │                   │                         │
│           ▼                   ▼                   ▼                         │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐               │
│  │  DataProfiler   │ │ AnomalyDetector │ │ SemanticChunker │               │
│  │  数据画像       │ │ 异常检测        │ │ 语义分块        │               │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘               │
│                               │                                              │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      ChunkAnalyzer (调用 LLM)                        │    │
│  │                      分析每个数据块                                  │    │
│  └────────────────────────────┬────────────────────────────────────────┘    │
│                               │                                              │
│           ┌───────────────────┴───────────────────┐                         │
│           ▼                                       ▼                         │
│  ┌─────────────────────────┐         ┌─────────────────────────┐           │
│  │   InsightAccumulator    │         │   InsightSynthesizer    │           │
│  │   洞察累积              │    →    │   洞察合成              │           │
│  └─────────────────────────┘         └─────────────────────────┘           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Insight Agent

### Prompt 模板

```python
# tableau_assistant/src/agents/insight/prompt.py

INSIGHT_SYSTEM_PROMPT = """你是数据分析专家，负责从查询结果中提取有价值的洞察。

## 任务
分析数据，提取关键洞察，包括：
1. 趋势分析：数据的变化趋势
2. 异常检测：异常值和离群点
3. 对比分析：不同维度的对比
4. 关键发现：最重要的业务洞察

## 输出格式
输出结构化的洞察报告，包含：
- summary: 一句话总结
- key_findings: 关键发现列表
- trends: 趋势分析
- anomalies: 异常情况
- recommendations: 建议
"""
```

### 节点实现

```python
# tableau_assistant/src/agents/insight/node.py

async def insight_node(state: VizQLState, runtime) -> Dict[str, Any]:
    """
    Insight Agent 节点
    
    流程：
    1. 调用 AnalysisCoordinator 进行渐进式分析
    2. 生成最终洞察报告
    """
    query_result = state["query_result"]
    question = state.get("question", "")
    
    # 初始化协调器
    coordinator = AnalysisCoordinator()
    
    # 执行分析
    context = {
        "question": question,
        "dimensions": state.get("semantic_query", {}).get("dimensions", []),
        "measures": state.get("semantic_query", {}).get("measures", []),
    }
    
    insights = await coordinator.analyze(query_result.data, context)
    
    return {
        "insights": insights.findings,
        "all_insights": state.get("all_insights", []) + insights.findings,
        "insight_complete": True,
    }
```

---

## 2. AnalysisCoordinator

### 职责

- 评估数据规模和复杂度
- 选择分析策略
- 编排分析流程
- 监控分析质量

### 实现

```python
# tableau_assistant/src/components/insight/coordinator.py

class AnalysisCoordinator:
    """
    分析协调器 - 三层架构的主持人层
    """
    
    def __init__(self):
        self.profiler = DataProfiler()
        self.anomaly_detector = AnomalyDetector()
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
        
        # 2. 异常检测
        anomalies = self.anomaly_detector.detect(data)
        
        # 3. 选择策略
        strategy = self._select_strategy(profile)
        
        # 4. 执行分析
        analysis_context = {**context, "anomalies": anomalies, "profile": profile}
        
        if strategy == "direct":
            return await self._direct_analysis(data, analysis_context)
        elif strategy == "progressive":
            return await self._progressive_analysis(data, analysis_context, profile)
        else:
            return await self._hybrid_analysis(data, analysis_context, profile)
    
    def _select_strategy(self, profile: DataProfile) -> str:
        """
        选择分析策略
        
        - < 100 行: direct（直接分析）
        - 100-1000 行: progressive（渐进式分析）
        - > 1000 行: hybrid（混合分析）
        """
        if profile.row_count < 100:
            return "direct"
        elif profile.row_count < 1000:
            return "progressive"
        return "hybrid"
    
    async def _direct_analysis(
        self,
        data: DataFrame,
        context: Dict
    ) -> InsightResult:
        """直接分析（小数据集）"""
        insights = await self.analyzer.analyze_full(data, context)
        return InsightResult(findings=insights)
    
    async def _progressive_analysis(
        self,
        data: DataFrame,
        context: Dict,
        profile: DataProfile
    ) -> InsightResult:
        """渐进式分析（中等数据集）"""
        # 1. 语义分块
        chunks = self.chunker.chunk(data, profile.semantic_groups)
        
        # 2. 分析每个块
        all_insights = []
        for chunk in chunks:
            chunk_insights = await self.analyzer.analyze_chunk(chunk, context)
            all_insights.extend(chunk_insights)
            
            # 累积洞察
            self.accumulator.accumulate(chunk_insights)
        
        # 3. 合成最终洞察
        return self.synthesizer.synthesize(self.accumulator.get_accumulated())
    
    async def _hybrid_analysis(
        self,
        data: DataFrame,
        context: Dict,
        profile: DataProfile
    ) -> InsightResult:
        """混合分析（大数据集）"""
        # 1. 采样分析
        sample = data.sample(min(500, len(data)))
        sample_insights = await self._direct_analysis(sample, context)
        
        # 2. 聚合分析
        aggregated = self._aggregate_data(data, profile)
        agg_insights = await self._direct_analysis(aggregated, context)
        
        # 3. 合并洞察
        return self.synthesizer.merge([sample_insights, agg_insights])
```

---

## 3. DataProfiler

### 职责

- 数据画像
- 统计信息计算

### 实现

```python
# tableau_assistant/src/components/insight/profiler.py

class DataProfiler:
    """数据画像器"""
    
    def profile(self, data: DataFrame) -> DataProfile:
        return DataProfile(
            row_count=len(data),
            column_count=len(data.columns),
            density=self._calculate_density(data),
            statistics=self._calculate_statistics(data),
            semantic_groups=self._identify_semantic_groups(data)
        )
    
    def _calculate_density(self, data: DataFrame) -> float:
        """计算数据密度（非空比例）"""
        return data.notna().sum().sum() / (data.shape[0] * data.shape[1])
    
    def _calculate_statistics(self, data: DataFrame) -> Dict[str, ColumnStats]:
        """计算每列的统计信息"""
        stats = {}
        for col in data.columns:
            if data[col].dtype in ['int64', 'float64']:
                stats[col] = ColumnStats(
                    mean=data[col].mean(),
                    median=data[col].median(),
                    std=data[col].std(),
                    min=data[col].min(),
                    max=data[col].max(),
                    q25=data[col].quantile(0.25),
                    q75=data[col].quantile(0.75),
                )
        return stats
    
    def _identify_semantic_groups(self, data: DataFrame) -> List[SemanticGroup]:
        """识别语义分组"""
        groups = []
        
        # 识别时间列
        time_cols = [c for c in data.columns if self._is_time_column(data[c])]
        if time_cols:
            groups.append(SemanticGroup(type="time", columns=time_cols))
        
        # 识别分类列
        cat_cols = [c for c in data.columns if data[c].dtype == 'object']
        if cat_cols:
            groups.append(SemanticGroup(type="category", columns=cat_cols))
        
        # 识别数值列
        num_cols = [c for c in data.columns if data[c].dtype in ['int64', 'float64']]
        if num_cols:
            groups.append(SemanticGroup(type="numeric", columns=num_cols))
        
        return groups
```

---

## 4. AnomalyDetector

### 职责

- 异常检测
- 离群值识别

### 实现

```python
# tableau_assistant/src/components/insight/anomaly_detector.py

class AnomalyDetector:
    """异常检测器"""
    
    def detect(self, data: DataFrame) -> AnomalyResult:
        outliers = self._detect_outliers(data)
        anomaly_ratio = len(outliers) / len(data) if len(data) > 0 else 0
        
        return AnomalyResult(
            outliers=outliers,
            anomaly_ratio=anomaly_ratio,
            anomaly_details=self._get_anomaly_details(data, outliers)
        )
    
    def _detect_outliers(self, data: DataFrame) -> List[int]:
        """使用 IQR 方法检测离群值"""
        outlier_indices = set()
        
        for col in data.select_dtypes(include=['int64', 'float64']).columns:
            q1 = data[col].quantile(0.25)
            q3 = data[col].quantile(0.75)
            iqr = q3 - q1
            
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            
            outliers = data[(data[col] < lower_bound) | (data[col] > upper_bound)].index
            outlier_indices.update(outliers)
        
        return list(outlier_indices)
    
    def _get_anomaly_details(
        self,
        data: DataFrame,
        outlier_indices: List[int]
    ) -> List[AnomalyDetail]:
        """获取异常详情"""
        details = []
        for idx in outlier_indices[:10]:  # 最多返回 10 个
            row = data.loc[idx]
            details.append(AnomalyDetail(
                index=idx,
                values=row.to_dict(),
                reason=self._explain_anomaly(row, data)
            ))
        return details
```

---

## 5. 其他组件

### SemanticChunker

```python
# tableau_assistant/src/components/insight/chunker.py

class SemanticChunker:
    """语义分块器"""
    
    def chunk(
        self,
        data: DataFrame,
        semantic_groups: List[SemanticGroup]
    ) -> List[DataChunk]:
        """按语义分组进行分块"""
        # 优先按分类列分块
        cat_group = next((g for g in semantic_groups if g.type == "category"), None)
        
        if cat_group and cat_group.columns:
            primary_col = cat_group.columns[0]
            return self._chunk_by_column(data, primary_col)
        
        # 否则按行数分块
        return self._chunk_by_size(data, chunk_size=100)
```

### ChunkAnalyzer

```python
# tableau_assistant/src/components/insight/analyzer.py

class ChunkAnalyzer:
    """块分析器（调用 LLM）"""
    
    async def analyze_chunk(
        self,
        chunk: DataChunk,
        context: Dict
    ) -> List[Insight]:
        """分析单个数据块"""
        prompt = self._build_analysis_prompt(chunk, context)
        response = await self.llm.ainvoke(prompt)
        return self._parse_insights(response.content)
    
    async def analyze_full(
        self,
        data: DataFrame,
        context: Dict
    ) -> List[Insight]:
        """分析完整数据集"""
        prompt = self._build_full_analysis_prompt(data, context)
        response = await self.llm.ainvoke(prompt)
        return self._parse_insights(response.content)
```

### InsightAccumulator

```python
# tableau_assistant/src/components/insight/accumulator.py

class InsightAccumulator:
    """洞察累积器"""
    
    def __init__(self):
        self._insights: List[Insight] = []
        self._seen_patterns: Set[str] = set()
    
    def accumulate(self, insights: List[Insight]):
        """累积洞察，去重"""
        for insight in insights:
            pattern = self._extract_pattern(insight)
            if pattern not in self._seen_patterns:
                self._insights.append(insight)
                self._seen_patterns.add(pattern)
    
    def get_accumulated(self) -> List[Insight]:
        return self._insights
```

### InsightSynthesizer

```python
# tableau_assistant/src/components/insight/synthesizer.py

class InsightSynthesizer:
    """洞察合成器"""
    
    def synthesize(self, insights: List[Insight]) -> InsightResult:
        """合成最终洞察"""
        # 按重要性排序
        sorted_insights = sorted(insights, key=lambda x: x.importance, reverse=True)
        
        # 生成摘要
        summary = self._generate_summary(sorted_insights[:5])
        
        return InsightResult(
            summary=summary,
            findings=sorted_insights,
            confidence=self._calculate_confidence(sorted_insights)
        )
    
    def merge(self, results: List[InsightResult]) -> InsightResult:
        """合并多个分析结果"""
        all_findings = []
        for result in results:
            all_findings.extend(result.findings)
        
        # 去重并排序
        unique_findings = self._deduplicate(all_findings)
        return self.synthesize(unique_findings)
```
