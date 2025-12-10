# 洞察系统设计（类 Tableau Pulse）

## 概述

本文档描述洞察系统的完整设计，采用**两阶段分析**架构：
1. **Phase 1**: 统计/ML 整体分析（不需要 LLM）
2. **Phase 2**: 智能分块 + 渐进式分析（主持人 + 分析师 LLM 协作）

对应项目结构：
- `src/agents/insight/` - Insight Agent
- `src/agents/replanner/` - Replanner Agent
- `src/components/insight/` - 洞察组件

---

## 设计原则

### 核心理念变化

```
旧设计：数据 → 分块 → 逐块分析 → 累积洞察
问题：先分块再分析，可能错过整体模式

新设计（类 Tableau Pulse）：
数据 → 统计/ML 整体分析 → 发现模式 → 智能分块 → 深入分析
优势：先了解整体，再有针对性地深入
```

### 关键设计决策

1. **洞察系统封装为组件**（AnalysisCoordinator），不暴露为工具
2. **两阶段分析**：先统计/ML 整体分析，再 LLM 深入分析
3. **主持人 + 分析师**：双 LLM 协作模式
4. **多问题重规划**：Replanner 生成多个探索问题，按优先级执行

---

## 维度层级（dimension_hierarchy）

### 完整的 category 类型

```python
category: Literal[
    "geographic",    # 地理维度：国家、省份、城市、区县
    "time",          # 时间维度：年、季度、月、周、日
    "product",       # 产品维度：类别、子类、品牌、SKU
    "customer",      # 客户维度：客户群、客户类型
    "organization",  # 组织维度：部门、团队、门店
    "financial",     # 财务维度：成本中心、账户
    "other"          # 其他
]
```


### DimensionAttributes 结构

```python
class DimensionAttributes(BaseModel):
    category: Literal["geographic", "time", "product", "customer", "organization", "financial", "other"]
    category_detail: str           # 如 "geographic-province", "time-month"
    level: int                     # 1-5，1 最粗，5 最细
    granularity: Literal["coarsest", "coarse", "medium", "fine", "finest"]
    unique_count: int              # 唯一值数量
    parent_dimension: Optional[str]  # 父维度
    child_dimension: Optional[str]   # 子维度
    sample_values: List[str]       # 样本值
    level_confidence: float        # 置信度
    reasoning: str                 # 推理说明
```

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           洞察系统架构（两阶段）                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Insight Agent (入口)                              │    │
│  │                                                                      │    │
│  │  输入：QueryResult, original_question, dimension_hierarchy           │    │
│  │  输出：InsightResult (findings, confidence, data_insight_profile)    │    │
│  └────────────────────────────┬────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                 AnalysisCoordinator (协调器)                         │    │
│  │                                                                      │    │
│  │  Phase 1: 统计/ML 整体分析                                           │    │
│  │  Phase 2: 智能分块 + 渐进式分析                                      │    │
│  └────────────────────────────┬────────────────────────────────────────┘    │
│                               │                                              │
│           ┌───────────────────┴───────────────────┐                         │
│           │                                       │                         │
│           ▼                                       ▼                         │
│  ┌─────────────────────────────────┐   ┌─────────────────────────────────┐  │
│  │     Phase 1: 统计/ML 分析       │   │     Phase 2: LLM 深入分析       │  │
│  │                                 │   │                                 │  │
│  │  ┌─────────────────────────┐   │   │  ┌─────────────────────────┐   │  │
│  │  │  StatisticalAnalyzer    │   │   │  │  主持人 LLM             │   │  │
│  │  │  - 分布分析             │   │   │  │  - 选择分块策略         │   │  │
│  │  │  - 异常检测             │   │   │  │  - 决定分析顺序         │   │  │
│  │  │  - 聚类分析             │   │   │  │  - 累积洞察             │   │  │
│  │  │  - 趋势检测             │   │   │  │  - 决定早停             │   │  │
│  │  │  - 相关性分析           │   │   │  └───────────┬─────────────┘   │  │
│  │  └───────────┬─────────────┘   │   │              │                 │  │
│  │              │                 │   │              ▼                 │  │
│  │              ▼                 │   │  ┌─────────────────────────┐   │  │
│  │  ┌─────────────────────────┐   │   │  │  分析师 LLM             │   │  │
│  │  │  DataInsightProfile     │   │   │  │  - 分析单个数据块       │   │  │
│  │  │  (整体洞察画像)         │───┼───│  │  - 结合整体画像解读     │   │  │
│  │  └─────────────────────────┘   │   │  │  - 生成结构化洞察       │   │  │
│  │                                 │   │  └─────────────────────────┘   │  │
│  └─────────────────────────────────┘   └─────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: 统计/ML 整体分析

### 目标

快速了解数据整体特征，发现宏观模式。**纯统计/ML 方法，不需要 LLM**。

### StatisticalAnalyzer 组件

```python
class StatisticalAnalyzer:
    """
    统计/ML 分析器 - Phase 1 整体分析
    
    纯统计/ML 方法，不需要 LLM
    """
    
    def analyze(self, data: List[Dict], profile: DataProfile) -> DataInsightProfile:
        """整体分析，生成数据洞察画像"""
        return DataInsightProfile(
            # 1. 分布分析
            distribution_type=self._detect_distribution(data),
            skewness=...,
            kurtosis=...,
            
            # 2. 帕累托分析
            pareto_ratio=self._calculate_pareto(data),
            
            # 3. 异常检测
            anomaly_indices=self._detect_anomalies(data),
            anomaly_method="IQR",
            
            # 4. 聚类分析
            clusters=self._cluster_analysis(data),
            optimal_k=...,
            
            # 5. 趋势检测（如果有时间列）
            trend=self._detect_trend(data),
            change_points=self._detect_change_points(data),
            
            # 6. 相关性分析
            correlations=self._calculate_correlations(data),
        )
```


### 统计方法详解

#### 1. 分布分析

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              分布分析                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  偏度 (Skewness):                                                           │
│    - |skew| < 0.5: 近似正态 → 使用均值±标准差分块                           │
│    - skew > 1: 右偏/长尾 → 使用对数分块或百分位分块                         │
│    - skew < -1: 左偏 → 使用反向百分位分块                                   │
│                                                                              │
│  峰度 (Kurtosis):                                                           │
│    - kurtosis > 3: 尖峰 → 数据集中，使用更细的分块                          │
│    - kurtosis < 3: 平峰 → 数据分散，使用更宽的分块                          │
│                                                                              │
│  分布类型:                                                                  │
│    - "normal": 正态分布                                                     │
│    - "long_tail": 长尾分布（常见于销售数据）                                │
│    - "bimodal": 双峰分布                                                    │
│    - "uniform": 均匀分布                                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 2. 帕累托分析（80/20 法则）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           帕累托分析                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  业务数据常见模式:                                                          │
│    - 20% 的客户贡献 80% 的收入                                              │
│    - 20% 的产品贡献 80% 的销售额                                            │
│                                                                              │
│  计算方法:                                                                  │
│    1. 按度量值降序排序                                                      │
│    2. 计算累积百分比                                                        │
│    3. 找到贡献 80% 的数据占比                                               │
│                                                                              │
│  输出:                                                                      │
│    - pareto_ratio: 0.82 (top 20% 贡献 82%)                                  │
│    - pareto_threshold: 0.18 (18% 的数据贡献 80%)                            │
│                                                                              │
│  分块策略:                                                                  │
│    - top_20%: 高价值数据（优先分析）                                        │
│    - mid_30%: 中等价值数据                                                  │
│    - bottom_50%: 低价值数据（摘要分析）                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 3. 聚类分析

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           聚类分析                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  K-Means:                                                                   │
│    - 自动发现 K 个自然分组                                                  │
│    - 使用 Elbow Method 或 Silhouette Score 确定最优 K                       │
│    - 每个聚类作为一个分块                                                   │
│                                                                              │
│  DBSCAN:                                                                    │
│    - 发现任意形状的聚类                                                     │
│    - 自动识别噪声点（异常值）                                               │
│    - 不需要预设 K 值                                                        │
│                                                                              │
│  输出:                                                                      │
│    clusters: [                                                              │
│      {cluster_id: 0, center: {...}, size: 120, label: "高绩效"},            │
│      {cluster_id: 1, center: {...}, size: 350, label: "中等"},              │
│      {cluster_id: 2, center: {...}, size: 30, label: "异常"},               │
│    ]                                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 4. 趋势检测（时间序列）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           趋势检测                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  线性回归:                                                                  │
│    - 计算整体趋势方向和斜率                                                 │
│    - trend: "increasing" | "decreasing" | "stable"                          │
│    - slope: 0.05 (每期增长 5%)                                              │
│                                                                              │
│  变点检测 (Change Point Detection):                                         │
│    - 检测数据突变点                                                         │
│    - 使用 PELT 或 Binary Segmentation 算法                                  │
│    - change_points: [idx_45, idx_120]                                       │
│                                                                              │
│  分块策略:                                                                  │
│    - 按变点分割数据                                                         │
│    - 每个时间段作为一个分块                                                 │
│    - 优先分析变化最大的段                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 5. 相关性分析

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           相关性分析                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  皮尔逊相关 (数值列):                                                       │
│    - 计算数值列之间的线性相关性                                             │
│    - correlations: {("Sales", "Profit"): 0.85}                              │
│                                                                              │
│  卡方检验 (分类列):                                                         │
│    - 检验分类列之间的独立性                                                 │
│    - chi_square: {("Region", "Category"): 0.02}  # p-value                  │
│                                                                              │
│  用途:                                                                      │
│    - 发现强相关的列，用于解释性分析                                         │
│    - 指导 Replanner 生成探索问题                                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```


### DataInsightProfile 模型

```python
class ClusterInfo(BaseModel):
    """聚类信息"""
    cluster_id: int
    center: Dict[str, float]      # 聚类中心
    size: int                     # 聚类大小
    label: str                    # 聚类标签（如"高绩效"、"异常"）
    indices: List[int]            # 属于该聚类的行索引

class DataInsightProfile(BaseModel):
    """
    数据洞察画像 - Phase 1 统计/ML 分析结果
    
    传递给 Phase 2 和 Replanner，指导后续分析
    """
    # 分布分析
    distribution_type: Literal["normal", "long_tail", "bimodal", "uniform"]
    skewness: float
    kurtosis: float
    
    # 帕累托分析
    pareto_ratio: float           # top 20% 贡献的比例
    pareto_threshold: float       # 贡献 80% 的数据占比
    
    # 异常检测
    anomaly_indices: List[int]
    anomaly_ratio: float
    anomaly_method: str           # "IQR", "Z-Score", "Isolation Forest"
    
    # 聚类分析
    clusters: List[ClusterInfo]
    optimal_k: int
    clustering_method: str        # "KMeans", "DBSCAN"
    
    # 趋势检测（可选，仅时间序列数据）
    trend: Optional[Literal["increasing", "decreasing", "stable"]] = None
    trend_slope: Optional[float] = None
    change_points: Optional[List[int]] = None
    
    # 相关性分析
    correlations: Dict[str, float]  # {("col1", "col2"): correlation}
    
    # 推荐的分块策略
    recommended_chunking_strategy: Literal[
        "by_cluster",      # 按聚类分块
        "by_change_point", # 按变点分块
        "by_pareto",       # 按帕累托分块
        "by_semantic",     # 按语义值分块
        "by_statistics",   # 按统计特征分块
        "by_position"      # 按位置分块（最后手段）
    ]
```

---

## Phase 2: 智能分块 + 渐进式分析

### 分块策略选择（基于 Phase 1 结果）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        智能分块策略决策树                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  输入: DataInsightProfile, dimension_hierarchy                              │
│                                                                              │
│  IF 发现聚类 (clusters.length >= 2)                                         │
│  └─► 按聚类分块                                                             │
│      - 每个聚类作为一个分块                                                 │
│      - 优先分析异常聚类和最大聚类                                           │
│                                                                              │
│  ELIF 发现变点 (change_points.length >= 1)                                  │
│  └─► 按变点分块                                                             │
│      - 每个时间段作为一个分块                                               │
│      - 优先分析变化最大的段                                                 │
│                                                                              │
│  ELIF 长尾分布 (distribution_type == "long_tail")                           │
│  └─► 按帕累托分块                                                           │
│      - top_20%, mid_30%, bottom_50%                                         │
│      - 优先分析 top_20%                                                     │
│                                                                              │
│  ELIF 有合适语义列 (unique_count 在 3-20 之间)                              │
│  └─► 按语义值分块                                                           │
│      - 按时间/地理/类别值分块                                               │
│      - 使用 dimension_hierarchy 判断                                        │
│                                                                              │
│  ELIF 有数值列                                                              │
│  └─► 按统计特征分块                                                         │
│      - anomalies: IQR 异常值                                                │
│      - high_value: value > Q75                                              │
│      - medium_value: Q25 <= value <= Q75                                    │
│      - low_value: value < Q25                                               │
│                                                                              │
│  ELSE                                                                       │
│  └─► 按位置分块（最后手段）                                                 │
│      - top_100, mid_200, low_200, tail                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```


### 主持人 + 分析师 协作模式

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        主持人 + 分析师 协作                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    主持人 LLM (Coordinator)                          │    │
│  │                                                                      │    │
│  │  输入:                                                               │    │
│  │  - DataInsightProfile（整体画像）                                    │    │
│  │  - 已累积洞察                                                        │    │
│  │  - 剩余数据块                                                        │    │
│  │  - 原始问题                                                          │    │
│  │                                                                      │    │
│  │  职责:                                                               │    │
│  │  - 基于整体画像选择分块策略                                          │    │
│  │  - 决定分析顺序（优先级）                                            │    │
│  │  - 累积洞察，判断完成度                                              │    │
│  │  - 决定是否早停                                                      │    │
│  │                                                                      │    │
│  │  输出: NextBiteDecision                                              │    │
│  │  - should_continue: bool                                             │    │
│  │  - next_chunk_id: int                                                │    │
│  │  - reason: str                                                       │    │
│  │  - completeness_estimate: float                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      │ 调度                                  │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    分析师 LLM (ChunkAnalyzer)                        │    │
│  │                                                                      │    │
│  │  输入:                                                               │    │
│  │  - 单个数据块                                                        │    │
│  │  - DataInsightProfile（整体画像，包含统计信息）                      │    │
│  │  - top_n_summary（Top N 数据摘要，用于对比）                         │    │
│  │  - 已有洞察（避免重复）                                              │    │
│  │  - 原始问题                                                          │    │
│  │                                                                      │    │
│  │  关键：分析师如何知道"A店是第2名的5倍"？                             │    │
│  │  - DataInsightProfile.statistics 包含 max, q75, median 等           │    │
│  │  - top_n_summary 包含 Top 5 数据，分析师可以计算比值                 │    │
│  │                                                                      │    │
│  │  职责:                                                               │    │
│  │  - 分析单个数据块                                                    │    │
│  │  - 结合整体画像和 top_n_summary 解读局部数据                         │    │
│  │  - 生成结构化洞察                                                    │    │
│  │                                                                      │    │
│  │  输出: List[Insight]                                                 │    │
│  │  - type: "trend" | "anomaly" | "comparison" | "pattern"              │    │
│  │  - title: str                                                        │    │
│  │  - description: str                                                  │    │
│  │  - importance: float                                                 │    │
│  │  - evidence: Dict                                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 渐进式分析循环

```python
async def progressive_analysis(
    self,
    data: List[Dict],
    profile: DataInsightProfile,
    context: Dict,
) -> InsightResult:
    """
    渐进式分析主循环
    
    主持人 + 分析师 协作
    """
    # 1. 基于整体画像选择分块策略
    chunks = self.chunker.chunk_by_strategy(
        data=data,
        strategy=profile.recommended_chunking_strategy,
        profile=profile,
    )
    
    # 2. 渐进式分析循环
    accumulated_insights: List[Insight] = []
    remaining_chunks = chunks.copy()
    
    while remaining_chunks:
        # 主持人决定下一步
        decision = await self.coordinator_llm.decide_next_bite(
            profile=profile,
            accumulated_insights=accumulated_insights,
            remaining_chunks=remaining_chunks,
            question=context["question"],
        )
        
        if not decision.should_continue:
            logger.info(f"主持人决定早停: {decision.reason}")
            break
        
        # 获取下一个数据块
        next_chunk = self._get_chunk_by_id(remaining_chunks, decision.next_chunk_id)
        remaining_chunks.remove(next_chunk)
        
        # 分析师分析数据块
        # 关键：传递 top_n_summary 让分析师能够进行对比分析
        new_insights = await self.analyzer_llm.analyze_chunk(
            chunk=next_chunk,
            profile=profile,           # 整体画像（统计信息）
            top_n_summary=top_n_data,  # Top N 数据摘要（用于对比）
            existing_insights=accumulated_insights,
            question=context["question"],
        )
        
        # 累积洞察
        accumulated_insights.extend(new_insights)
    
    # 3. 合成最终结果
    return self.synthesizer.synthesize(
        insights=accumulated_insights,
        profile=profile,
    )
```

### 分析师 LLM 的上下文信息

分析师 LLM 需要足够的上下文才能生成有意义的洞察（如"是第2名的5倍"）：

```python
# 分析师 LLM 的输入
analyzer_context = {
    # 1. 当前数据块
    "chunk_data": chunk.data,
    "chunk_type": chunk.chunk_type,
    "chunk_description": chunk.description,
    
    # 2. 整体画像（来自 Phase 1 统计分析）
    "profile": {
        "distribution_type": "long_tail",
        "statistics": {
            "销售额": {"max": 1000万, "min": 1万, "mean": 50万, "median": 20万, "q75": 80万, "q25": 10万}
        },
        "anomaly_ratio": 0.02,
        "pareto_ratio": 0.78,  # top 20% 贡献 78%
    },
    
    # 3. Top N 数据摘要（关键！用于对比分析）
    "top_n_summary": [
        {"门店": "A店", "销售额": 1000万, "rank": 1},
        {"门店": "B店", "销售额": 200万, "rank": 2},
        {"门店": "C店", "销售额": 180万, "rank": 3},
        {"门店": "D店", "销售额": 150万, "rank": 4},
        {"门店": "E店", "销售额": 120万, "rank": 5},
    ],
    
    # 4. 已有洞察（避免重复）
    "existing_insights": [...],
    
    # 5. 原始问题
    "question": "哪个门店销售额最高？为什么？",
}

# 分析师可以计算：
# - A店是第2名的 1000/200 = 5 倍
# - A店占总销售额的 1000/(1000+200+180+...) = X%
# - A店比 Q75 高 1000/80 = 12.5 倍
```

---

## 重规划系统（Replanner）

### 多问题生成

Replanner 不再只生成一个问题，而是生成**多个探索问题**，按优先级执行。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        智能重规划：多问题生成                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  输入:                                                                      │
│  - original_question: "哪个门店销售额最高？为什么？"                        │
│  - insights: ["A店第1名", "异常高", "Top 10 占 60%"]                        │
│  - data_insight_profile: {distribution: "long_tail", ...}                   │
│  - dimension_hierarchy: {...}                                               │
│  - current_dimensions: ["门店"]                                             │
│                                                                              │
│  Replanner LLM 分析:                                                        │
│  1. 评估当前洞察的完成度                                                    │
│  2. 识别缺失的方面                                                          │
│  3. 基于 dimension_hierarchy 生成多个探索问题                               │
│  4. 为每个问题分配优先级                                                    │
│                                                                              │
│  输出 ReplanDecision:                                                       │
│  - should_replan: True                                                      │
│  - completeness_score: 0.5                                                  │
│  - missing_aspects: ["为什么A店销售额高"]                                   │
│  - exploration_questions: [                                                 │
│      {                                                                      │
│        question: "A店各产品类别的销售额分布？",                             │
│        exploration_type: "drill_down",                                      │
│        target_dimension: "产品类别",                                        │
│        priority: 1,                                                         │
│        reasoning: "按产品维度展开，找出主要贡献类别"                        │
│      },                                                                     │
│      {                                                                      │
│        question: "A店过去12个月的销售趋势？",                               │
│        exploration_type: "time_series",                                     │
│        target_dimension: "月份",                                            │
│        priority: 2,                                                         │
│        reasoning: "按时间维度展开，了解增长趋势"                            │
│      },                                                                     │
│      {                                                                      │
│        question: "A店与同城市其他门店的对比？",                             │
│        exploration_type: "peer_comparison",                                 │
│        target_dimension: "门店",                                            │
│        filter: "城市 = A店所在城市",                                        │
│        priority: 3,                                                         │
│        reasoning: "横向对比，了解是否是区域优势"                            │
│      }                                                                      │
│    ]                                                                        │
│  - execute_count: 1  # 本轮执行几个问题                                     │
│  - max_rounds: 3     # 最大重规划轮数                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```


### 探索类型（exploration_type）

```python
exploration_type: Literal[
    "drill_down",           # 向下钻取（大类→小类）
    "roll_up",              # 向上汇总（小类→大类）
    "time_series",          # 时间序列分析
    "peer_comparison",      # 同级对比
    "cross_dimension",      # 跨维度分析
    "anomaly_investigation",# 异常调查
    "correlation_analysis"  # 相关性分析
]
```

### 探索策略（基于 dimension_hierarchy）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        探索策略                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. 同类别向下钻取 (drill_down)                                             │
│     - 当前: 省份 (level=2) → 下一步: 城市 (level=3)                         │
│     - 使用 child_dimension 关系                                             │
│     - LLM 直接生成问题，无需模板                                            │
│                                                                              │
│  2. 同类别向上汇总 (roll_up)                                                │
│     - 当前: 城市 (level=3) → 下一步: 省份 (level=2)                         │
│     - 使用 parent_dimension 关系                                            │
│                                                                              │
│  3. 时间序列分析 (time_series)                                              │
│     - 添加时间维度，分析趋势                                                │
│                                                                              │
│  4. 同级对比 (peer_comparison)                                              │
│     - 与同类别的其他实体对比                                                │
│                                                                              │
│  5. 跨维度分析 (cross_dimension)                                            │
│     - 添加不同类别的维度                                                    │
│     - 当前: geographic → 下一步: product 或 time                            │
│                                                                              │
│  6. 异常调查 (anomaly_investigation)                                        │
│     - 深入分析异常值                                                        │
│                                                                              │
│  7. 相关性分析 (correlation_analysis)                                       │
│     - 分析相关列的关系                                                      │
│                                                                              │
│  注意：问题由 Replanner LLM 直接生成，不使用模板！                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### ReplanDecision 模型

```python
class ExplorationQuestion(BaseModel):
    """
    探索问题 - 由 Replanner LLM 直接生成
    
    注意：问题文本由 LLM 生成，不使用模板！
    exploration_type 仅用于分类和优先级排序。
    """
    question: str                 # LLM 生成的问题文本（不是模板！）
    exploration_type: Literal[
        "drill_down", "roll_up", "time_series", 
        "peer_comparison", "cross_dimension",
        "anomaly_investigation", "correlation_analysis"
    ]
    target_dimension: str         # 目标维度
    filter: Optional[str] = None  # 过滤条件
    priority: int                 # 优先级（1 最高）
    reasoning: str                # LLM 的推理说明

class ReplanDecision(BaseModel):
    """
    重规划决策 - 支持多问题并行执行
    
    类似 Tableau Pulse：一次生成多个探索问题，并行执行
    """
    should_replan: bool
    completeness_score: float     # 0-1，当前洞察的完成度
    missing_aspects: List[str]    # 缺失的方面
    
    # 多个探索问题（由 LLM 生成）
    exploration_questions: List[ExplorationQuestion]
    
    # 执行策略
    parallel_execution: bool = True    # 是否并行执行多个问题
    max_questions_per_round: int = 3   # 每轮最多执行几个问题
    max_rounds: int = 3                # 最大重规划轮数
```

---

## 完整流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        完整流程：类 Tableau Pulse                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  用户问题: "哪个门店销售额最高？为什么？"                                    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Round 1: Understanding → Query → Data            │    │
│  │                                                                      │    │
│  │  QueryResult: [门店, 销售额] 500 行                                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Insight Agent                                     │    │
│  │                                                                      │    │
│  │  Phase 1: 统计/ML 整体分析                                           │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │  StatisticalAnalyzer.analyze():                              │    │    │
│  │  │  - distribution: "long_tail" (skew=2.3)                      │    │    │
│  │  │  - pareto: top 20% 贡献 78%                                  │    │    │
│  │  │  - anomalies: [0] (A店异常高)                                │    │    │
│  │  │  - clusters: 3 个自然分组                                    │    │    │
│  │  │    - cluster_0: 高绩效 (5 店, mean=800万)                    │    │    │
│  │  │    - cluster_1: 中绩效 (45 店, mean=100万)                   │    │    │
│  │  │    - cluster_2: 低绩效 (450 店, mean=10万)                   │    │    │
│  │  │  - recommended_strategy: "by_cluster"                        │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  │                                                                      │    │
│  │  Phase 2: 智能分块 + 渐进式分析                                      │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │  基于聚类结果分块:                                           │    │    │
│  │  │  - chunk_0: anomalies (A店)                                  │    │    │
│  │  │  - chunk_1: cluster_0 (高绩效 5 店)                          │    │    │
│  │  │  - chunk_2: cluster_1 (中绩效 45 店)                         │    │    │
│  │  │  - chunk_3: cluster_2 (低绩效 450 店, 摘要)                  │    │    │
│  │  │                                                              │    │    │
│  │  │  主持人 LLM:                                                 │    │    │
│  │  │  "整体呈长尾分布，发现3个聚类。先分析异常值A店。"            │    │    │
│  │  │                                                              │    │    │
│  │  │  分析师 LLM (chunk_0):                                       │    │    │
│  │  │  分析师 LLM (chunk_0 - anomalies):                            │    │    │
│  │  │  输入:                                                       │    │    │
│  │  │  - chunk_data: [{门店: "A店", 销售额: 1000万}]               │    │    │
│  │  │  - top_5_summary: [A店 1000万, B店 200万, C店 180万, ...]    │    │    │
│  │  │  - statistics: {max: 1000万, q75: 50万, median: 20万}        │    │    │
│  │  │                                                              │    │    │
│  │  │  分析师计算: 1000万 / 200万 = 5倍                            │    │    │
│  │  │  输出: "A店销售额1000万，是第2名的5倍，属于极端异常值。"     │    │    │
│  │  │                                                              │    │    │
│  │  │  主持人 LLM:                                                 │    │    │
│  │  │  "已回答'谁最高'，但'为什么'需要更多维度。早停。"            │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  │                                                                      │    │
│  │  输出 InsightResult:                                                │    │
│  │  - summary: "A店销售额最高（1000万），呈长尾分布"                   │    │
│  │  - confidence: 0.6                                                  │    │
│  │  - need_more_data: True                                             │    │
│  │  - data_insight_profile: {...}  # 传递给 Replanner                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Replanner Agent                                   │    │
│  │                                                                      │    │
│  │  输入:                                                              │    │
│  │  - insights + data_insight_profile                                  │    │
│  │  - dimension_hierarchy                                              │    │
│  │                                                                      │    │
│  │  LLM 分析:                                                          │    │
│  │  "A店异常高，需要从多个维度探索原因。"                              │    │
│  │                                                                      │    │
│  │  输出 ReplanDecision:                                               │    │
│  │  - should_replan: True                                              │    │
│  │  - completeness_score: 0.5                                          │    │
│  │  - exploration_questions: [  # LLM 直接生成，不是模板！             │    │
│  │      {q: "A店各产品类别销售额？", type: "drill_down", priority: 1}, │    │
│  │      {q: "A店过去12个月趋势？", type: "time_series", priority: 2},  │    │
│  │      {q: "A店与同城市门店对比？", type: "peer_comparison", pri: 3}  │    │
│  │    ]                                                                │    │
│  │  - parallel_execution: True                                         │    │
│  │  - max_questions_per_round: 3  # 本轮并行执行 top 3 个问题          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Round 2: 并行执行多个探索问题                     │    │
│  │                                                                      │    │
│  │  并行执行 3 个问题:                                                 │    │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐        │    │
│  │  │ Q1: 产品类别    │ │ Q2: 时间趋势    │ │ Q3: 同城对比    │        │    │
│  │  │ → Technology    │ │ → 持续增长      │ │ → 领先同城      │        │    │
│  │  │    占 60%       │ │    15%/月       │ │    3倍          │        │    │
│  │  └─────────────────┘ └─────────────────┘ └─────────────────┘        │    │
│  │                                                                      │    │
│  │  累积洞察:                                                          │    │
│  │  - "A店销售额最高（1000万）"                                        │    │
│  │  - "Technology 类别贡献 60%"                                        │    │
│  │  - "过去12个月持续增长 15%/月"                                      │    │
│  │  - "领先同城市其他门店 3 倍"                                        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Replanner Agent (Round 2)                         │    │
│  │                                                                      │    │
│  │  评估: completeness_score = 0.92                                    │    │
│  │  "已从产品、时间、地理三个维度回答了'为什么'，可以结束。"           │    │
│  │                                                                      │    │
│  │  输出: should_replan = False                                        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                               │                                              │
│                               ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    最终输出                                          │    │
│  │                                                                      │    │
│  │  InsightResult:                                                     │    │
│  │  - summary: "A店销售额最高（1000万），主要因为：                    │    │
│  │             1) Technology 类别贡献 60%                              │    │
│  │             2) 过去12个月持续增长                                   │    │
│  │             3) 领先同城市门店 3 倍"                                 │    │
│  │  - findings: [...]                                                  │    │
│  │  - confidence: 0.92                                                 │    │
│  │  - exploration_rounds: 2                                            │    │
│  │  - questions_executed: 3                                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```


---

## 组件详细设计

### 1. StatisticalAnalyzer（新增）

```python
# tableau_assistant/src/components/insight/statistical_analyzer.py

class StatisticalAnalyzer:
    """
    统计/ML 分析器 - Phase 1 整体分析
    
    纯统计/ML 方法，不需要 LLM
    """
    
    def analyze(self, data: List[Dict], profile: DataProfile) -> DataInsightProfile:
        """整体分析，生成数据洞察画像"""
        df = pd.DataFrame(data)
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        if not numeric_cols:
            return self._empty_profile()
        
        # 选择主度量列（第一个数值列）
        primary_measure = numeric_cols[0]
        values = df[primary_measure].dropna()
        
        # 1. 分布分析
        distribution_type, skewness, kurtosis = self._analyze_distribution(values)
        
        # 2. 帕累托分析
        pareto_ratio, pareto_threshold = self._analyze_pareto(values)
        
        # 3. 异常检测
        anomaly_indices, anomaly_ratio = self._detect_anomalies(values)
        
        # 4. 聚类分析
        clusters, optimal_k = self._cluster_analysis(df, numeric_cols)
        
        # 5. 趋势检测（如果有时间列）
        trend, trend_slope, change_points = self._detect_trend(df, profile)
        
        # 6. 相关性分析
        correlations = self._calculate_correlations(df, numeric_cols)
        
        # 7. 推荐分块策略
        recommended_strategy = self._recommend_chunking_strategy(
            distribution_type, clusters, change_points, profile
        )
        
        return DataInsightProfile(
            distribution_type=distribution_type,
            skewness=skewness,
            kurtosis=kurtosis,
            pareto_ratio=pareto_ratio,
            pareto_threshold=pareto_threshold,
            anomaly_indices=anomaly_indices,
            anomaly_ratio=anomaly_ratio,
            anomaly_method="IQR",
            clusters=clusters,
            optimal_k=optimal_k,
            clustering_method="KMeans",
            trend=trend,
            trend_slope=trend_slope,
            change_points=change_points,
            correlations=correlations,
            recommended_chunking_strategy=recommended_strategy,
        )
    
    def _analyze_distribution(self, values: pd.Series) -> Tuple[str, float, float]:
        """分析数据分布"""
        skewness = float(values.skew())
        kurtosis = float(values.kurtosis())
        
        if abs(skewness) < 0.5:
            distribution_type = "normal"
        elif skewness > 1:
            distribution_type = "long_tail"
        elif skewness < -1:
            distribution_type = "long_tail"  # 左偏也是长尾
        else:
            # 检查是否双峰
            distribution_type = "normal"  # 简化处理
        
        return distribution_type, skewness, kurtosis
    
    def _analyze_pareto(self, values: pd.Series) -> Tuple[float, float]:
        """帕累托分析（80/20 法则）"""
        sorted_values = values.sort_values(ascending=False)
        cumsum = sorted_values.cumsum()
        total = sorted_values.sum()
        
        # top 20% 贡献的比例
        top_20_idx = int(len(sorted_values) * 0.2)
        pareto_ratio = float(cumsum.iloc[top_20_idx] / total) if top_20_idx > 0 else 0.0
        
        # 贡献 80% 的数据占比
        threshold_idx = (cumsum >= total * 0.8).idxmax()
        pareto_threshold = float((sorted_values.index.get_loc(threshold_idx) + 1) / len(sorted_values))
        
        return pareto_ratio, pareto_threshold
    
    def _detect_anomalies(self, values: pd.Series) -> Tuple[List[int], float]:
        """IQR 异常检测"""
        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1
        
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        anomaly_mask = (values < lower_bound) | (values > upper_bound)
        anomaly_indices = values[anomaly_mask].index.tolist()
        anomaly_ratio = float(len(anomaly_indices) / len(values))
        
        return anomaly_indices, anomaly_ratio
    
    def _cluster_analysis(
        self, df: pd.DataFrame, numeric_cols: List[str]
    ) -> Tuple[List[ClusterInfo], int]:
        """K-Means 聚类分析"""
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        
        if len(df) < 10 or len(numeric_cols) == 0:
            return [], 0
        
        # 标准化
        X = df[numeric_cols].fillna(0).values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # 确定最优 K（简化：使用 3）
        optimal_k = min(3, len(df) // 10)
        if optimal_k < 2:
            return [], 0
        
        # 聚类
        kmeans = KMeans(n_clusters=optimal_k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(X_scaled)
        
        # 构建聚类信息
        clusters = []
        for i in range(optimal_k):
            mask = labels == i
            cluster_df = df[mask]
            
            # 计算聚类中心（原始尺度）
            center = {col: float(cluster_df[col].mean()) for col in numeric_cols}
            
            # 生成标签
            if i == 0:
                label = "高绩效"
            elif i == optimal_k - 1:
                label = "低绩效"
            else:
                label = "中等"
            
            clusters.append(ClusterInfo(
                cluster_id=i,
                center=center,
                size=int(mask.sum()),
                label=label,
                indices=df[mask].index.tolist(),
            ))
        
        # 按大小排序
        clusters.sort(key=lambda x: x.center.get(numeric_cols[0], 0), reverse=True)
        
        return clusters, optimal_k
    
    def _recommend_chunking_strategy(
        self,
        distribution_type: str,
        clusters: List[ClusterInfo],
        change_points: Optional[List[int]],
        profile: DataProfile,
    ) -> str:
        """推荐分块策略"""
        # 优先级：聚类 > 变点 > 帕累托 > 语义 > 统计 > 位置
        
        if len(clusters) >= 2:
            return "by_cluster"
        
        if change_points and len(change_points) >= 1:
            return "by_change_point"
        
        if distribution_type == "long_tail":
            return "by_pareto"
        
        # 检查是否有合适的语义列
        for group in profile.semantic_groups:
            if group.type in ["time", "geographic", "category"]:
                return "by_semantic"
        
        # 检查是否有数值列
        if profile.statistics:
            return "by_statistics"
        
        return "by_position"
```

### 2. SemanticChunker（更新）

```python
# tableau_assistant/src/components/insight/chunker.py

class SemanticChunker:
    """
    智能分块器
    
    基于 Phase 1 的 DataInsightProfile 选择分块策略
    """
    
    def chunk_by_strategy(
        self,
        data: List[Dict],
        strategy: str,
        profile: DataInsightProfile,
        data_profile: DataProfile,
    ) -> List[PriorityChunk]:
        """
        根据推荐策略执行分块
        """
        if strategy == "by_cluster":
            return self._chunk_by_cluster(data, profile.clusters)
        elif strategy == "by_change_point":
            return self._chunk_by_change_point(data, profile.change_points)
        elif strategy == "by_pareto":
            return self._chunk_by_pareto(data, profile.pareto_threshold)
        elif strategy == "by_semantic":
            return self._chunk_by_semantic(data, data_profile)
        elif strategy == "by_statistics":
            return self._chunk_by_statistics(data, data_profile.statistics)
        else:
            return self._chunk_by_position(data)
    
    def _chunk_by_cluster(
        self, data: List[Dict], clusters: List[ClusterInfo]
    ) -> List[PriorityChunk]:
        """按聚类分块"""
        chunks = []
        df = pd.DataFrame(data)
        
        for i, cluster in enumerate(clusters):
            cluster_data = df.iloc[cluster.indices].to_dict('records')
            
            # 异常聚类优先级最高
            if cluster.label == "异常" or cluster.size < len(df) * 0.05:
                priority = ChunkPriority.URGENT
            elif i == 0:  # 第一个聚类（通常是高绩效）
                priority = ChunkPriority.HIGH
            elif i == len(clusters) - 1:  # 最后一个聚类
                priority = ChunkPriority.LOW
            else:
                priority = ChunkPriority.MEDIUM
            
            chunks.append(PriorityChunk(
                chunk_id=i,
                chunk_type=f"cluster_{cluster.cluster_id}",
                priority=priority,
                data=cluster_data,
                row_count=cluster.size,
                column_names=df.columns.tolist(),
                description=f"聚类 {cluster.cluster_id}: {cluster.label} ({cluster.size} 行)",
                estimated_value="high" if priority <= ChunkPriority.HIGH else "medium",
            ))
        
        return sorted(chunks, key=lambda x: x.priority)
    
    def _chunk_by_pareto(
        self, data: List[Dict], pareto_threshold: float
    ) -> List[PriorityChunk]:
        """按帕累托分块（80/20 法则）"""
        df = pd.DataFrame(data)
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        if len(numeric_cols) == 0:
            return self._chunk_by_position(data)
        
        # 按主度量排序
        primary_col = numeric_cols[0]
        df_sorted = df.sort_values(primary_col, ascending=False)
        
        # 计算分割点
        top_20_idx = int(len(df) * 0.2)
        mid_50_idx = int(len(df) * 0.5)
        
        chunks = []
        
        # Top 20%
        top_data = df_sorted.head(top_20_idx).to_dict('records')
        chunks.append(PriorityChunk(
            chunk_id=0,
            chunk_type="pareto_top_20",
            priority=ChunkPriority.HIGH,
            data=top_data,
            row_count=len(top_data),
            column_names=df.columns.tolist(),
            description=f"Top 20% ({len(top_data)} 行，贡献约 80% 价值)",
            estimated_value="high",
        ))
        
        # Mid 30%
        mid_data = df_sorted.iloc[top_20_idx:mid_50_idx].to_dict('records')
        chunks.append(PriorityChunk(
            chunk_id=1,
            chunk_type="pareto_mid_30",
            priority=ChunkPriority.MEDIUM,
            data=mid_data,
            row_count=len(mid_data),
            column_names=df.columns.tolist(),
            description=f"Mid 30% ({len(mid_data)} 行)",
            estimated_value="medium",
        ))
        
        # Bottom 50%
        bottom_data = df_sorted.iloc[mid_50_idx:].to_dict('records')
        chunks.append(PriorityChunk(
            chunk_id=2,
            chunk_type="pareto_bottom_50",
            priority=ChunkPriority.LOW,
            data=bottom_data,
            row_count=len(bottom_data),
            column_names=df.columns.tolist(),
            description=f"Bottom 50% ({len(bottom_data)} 行)",
            estimated_value="low",
        ))
        
        return chunks
    
    def _chunk_by_statistics(
        self, data: List[Dict], statistics: Dict[str, ColumnStats]
    ) -> List[PriorityChunk]:
        """按统计特征分块（Q25/Q75）"""
        df = pd.DataFrame(data)
        
        if not statistics:
            return self._chunk_by_position(data)
        
        # 选择主度量
        primary_col = list(statistics.keys())[0]
        stats = statistics[primary_col]
        
        chunks = []
        
        # 异常值（IQR 方法）
        iqr = stats.q75 - stats.q25
        lower_bound = stats.q25 - 1.5 * iqr
        upper_bound = stats.q75 + 1.5 * iqr
        
        anomaly_mask = (df[primary_col] < lower_bound) | (df[primary_col] > upper_bound)
        if anomaly_mask.any():
            anomaly_data = df[anomaly_mask].to_dict('records')
            chunks.append(PriorityChunk(
                chunk_id=0,
                chunk_type="anomalies",
                priority=ChunkPriority.URGENT,
                data=anomaly_data,
                row_count=len(anomaly_data),
                column_names=df.columns.tolist(),
                description=f"异常值 ({len(anomaly_data)} 行)",
                estimated_value="high",
            ))
        
        # 高价值（> Q75）
        high_mask = (df[primary_col] > stats.q75) & ~anomaly_mask
        if high_mask.any():
            high_data = df[high_mask].to_dict('records')
            chunks.append(PriorityChunk(
                chunk_id=1,
                chunk_type="high_value",
                priority=ChunkPriority.HIGH,
                data=high_data,
                row_count=len(high_data),
                column_names=df.columns.tolist(),
                description=f"高价值 (> Q75, {len(high_data)} 行)",
                estimated_value="high",
            ))
        
        # 中等价值（Q25-Q75）
        mid_mask = (df[primary_col] >= stats.q25) & (df[primary_col] <= stats.q75)
        if mid_mask.any():
            mid_data = df[mid_mask].to_dict('records')
            chunks.append(PriorityChunk(
                chunk_id=2,
                chunk_type="medium_value",
                priority=ChunkPriority.MEDIUM,
                data=mid_data,
                row_count=len(mid_data),
                column_names=df.columns.tolist(),
                description=f"中等价值 (Q25-Q75, {len(mid_data)} 行)",
                estimated_value="medium",
            ))
        
        # 低价值（< Q25）
        low_mask = (df[primary_col] < stats.q25) & ~anomaly_mask
        if low_mask.any():
            low_data = df[low_mask].to_dict('records')
            chunks.append(PriorityChunk(
                chunk_id=3,
                chunk_type="low_value",
                priority=ChunkPriority.LOW,
                data=low_data,
                row_count=len(low_data),
                column_names=df.columns.tolist(),
                description=f"低价值 (< Q25, {len(low_data)} 行)",
                estimated_value="low",
            ))
        
        return sorted(chunks, key=lambda x: x.priority)
```


### 3. AnalysisCoordinator（更新）

```python
# tableau_assistant/src/components/insight/coordinator.py

class AnalysisCoordinator:
    """
    分析协调器 - 两阶段分析
    
    Phase 1: 统计/ML 整体分析
    Phase 2: 智能分块 + 渐进式分析（主持人 + 分析师）
    """
    
    def __init__(self, ...):
        self.statistical_analyzer = StatisticalAnalyzer()
        self.profiler = DataProfiler(dimension_hierarchy=dimension_hierarchy)
        self.chunker = SemanticChunker(dimension_hierarchy=dimension_hierarchy)
        self.coordinator_llm = CoordinatorLLM()  # 主持人
        self.analyzer_llm = ChunkAnalyzer()      # 分析师
        self.synthesizer = InsightSynthesizer()
    
    async def analyze(self, data: Any, context: Dict) -> InsightResult:
        """主分析入口"""
        data_list = self._normalize_data(data)
        
        # Phase 1: 统计/ML 整体分析
        data_profile = self.profiler.profile(data_list)
        insight_profile = self.statistical_analyzer.analyze(data_list, data_profile)
        
        logger.info(f"Phase 1 完成: distribution={insight_profile.distribution_type}, "
                   f"clusters={len(insight_profile.clusters)}, "
                   f"strategy={insight_profile.recommended_chunking_strategy}")
        
        # Phase 2: 智能分块 + 渐进式分析
        if data_profile.row_count < 100:
            # 小数据集直接分析
            result = await self._direct_analysis(data_list, context, insight_profile)
        else:
            # 渐进式分析
            result = await self._progressive_analysis(
                data_list, context, data_profile, insight_profile
            )
        
        # 附加整体画像到结果
        result.data_insight_profile = insight_profile
        
        return result
    
    async def _progressive_analysis(
        self,
        data: List[Dict],
        context: Dict,
        data_profile: DataProfile,
        insight_profile: DataInsightProfile,
    ) -> InsightResult:
        """渐进式分析（主持人 + 分析师协作）"""
        
        # 1. 基于整体画像选择分块策略
        chunks = self.chunker.chunk_by_strategy(
            data=data,
            strategy=insight_profile.recommended_chunking_strategy,
            profile=insight_profile,
            data_profile=data_profile,
        )
        
        logger.info(f"分块完成: {len(chunks)} 个块, 策略={insight_profile.recommended_chunking_strategy}")
        
        # 2. 渐进式分析循环
        accumulated_insights: List[Insight] = []
        remaining_chunks = chunks.copy()
        analyzed_count = 0
        
        while remaining_chunks:
            # 主持人决定下一步
            decision = await self.coordinator_llm.decide_next_bite(
                profile=insight_profile,
                accumulated_insights=accumulated_insights,
                remaining_chunks=remaining_chunks,
                question=context.get("question", ""),
            )
            
            if not decision.should_continue:
                logger.info(f"主持人决定早停: {decision.reason}")
                break
            
            # 获取下一个数据块
            next_chunk = self._get_chunk_by_id(remaining_chunks, decision.next_chunk_id)
            if not next_chunk:
                next_chunk = remaining_chunks[0]
            remaining_chunks.remove(next_chunk)
            analyzed_count += 1
            
            logger.info(f"分析块 {analyzed_count}: {next_chunk.chunk_type}")
            
            # 分析师分析数据块
            new_insights = await self.analyzer_llm.analyze_chunk(
                chunk=next_chunk,
                profile=insight_profile,
                existing_insights=accumulated_insights,
                question=context.get("question", ""),
            )
            
            # 累积洞察（去重）
            for insight in new_insights:
                if not self._is_duplicate(insight, accumulated_insights):
                    accumulated_insights.append(insight)
                    logger.info(f"新洞察: {insight.title}")
        
        # 3. 合成最终结果
        return self.synthesizer.synthesize(
            insights=accumulated_insights,
            profile=insight_profile,
            chunks_analyzed=analyzed_count,
            total_rows=data_profile.row_count,
        )
```

---

## 数据模型更新

### InsightResult（更新）

```python
class InsightResult(BaseModel):
    """洞察结果"""
    summary: Optional[str] = None
    findings: List[Insight] = Field(default_factory=list)
    confidence: float = 0.0
    
    # 策略信息
    strategy_used: str = "direct"
    chunks_analyzed: int = 0
    total_rows_analyzed: int = 0
    execution_time: float = 0.0
    
    # 新增：整体画像（传递给 Replanner）
    data_insight_profile: Optional[DataInsightProfile] = None
    
    # 新增：是否需要更多数据
    need_more_data: bool = False
    missing_aspects: List[str] = Field(default_factory=list)
```

### PriorityChunk（更新）

```python
class PriorityChunk(BaseModel):
    """带优先级的数据块"""
    chunk_id: int
    chunk_type: str  # 更灵活，支持 "cluster_0", "pareto_top_20" 等
    priority: int
    data: List[Dict[str, Any]] = Field(default_factory=list)
    tail_summary: Optional[TailDataSummary] = None
    row_count: int
    column_names: List[str] = Field(default_factory=list)
    description: str = ""
    estimated_value: str = "unknown"
    
    # 新增：聚类信息（如果是聚类分块）
    cluster_info: Optional[ClusterInfo] = None
```

---

## 中间件集成

洞察系统与中间件层的交互是系统设计的重要部分。本节描述各中间件如何与洞察系统协作。

### 中间件与洞察系统交互概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    中间件与洞察系统交互                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    Insight Agent                                     │    │
│  │                                                                      │    │
│  │  输入: QueryResult (可能很大)                                        │    │
│  │  输出: InsightResult + exploration_questions                         │    │
│  └────────────────────────────┬────────────────────────────────────────┘    │
│                               │                                              │
│           ┌───────────────────┼───────────────────┐                         │
│           │                   │                   │                         │
│           ▼                   ▼                   ▼                         │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐                │
│  │ Filesystem      │ │ Summarization   │ │ TodoList        │                │
│  │ Middleware      │ │ Middleware      │ │ Middleware      │                │
│  │                 │ │                 │ │                 │                │
│  │ 大数据块转存    │ │ 只总结消息      │ │ 存储探索问题    │                │
│  │ 到临时文件      │ │ 不总结洞察      │ │ 供用户审查      │                │
│  └─────────────────┘ └─────────────────┘ └─────────────────┘                │
│                                                     │                        │
│                                                     ▼                        │
│                                          ┌─────────────────┐                │
│                                          │ HumanInTheLoop  │                │
│                                          │ Middleware      │                │
│                                          │                 │                │
│                                          │ 用户审查问题    │                │
│                                          │ 选择/修改/拒绝  │                │
│                                          └─────────────────┘                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1. FilesystemMiddleware 与大数据块处理

**场景**: 当数据块超过 token 限制时，自动转存到文件。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FilesystemMiddleware 与洞察系统                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  问题场景:                                                                  │
│  - QueryResult 返回 10000 行数据                                            │
│  - 直接传给 LLM 会超过 token 限制                                           │
│                                                                              │
│  解决方案:                                                                  │
│  1. 洞察系统内部处理大数据（分块、采样）                                    │
│  2. FilesystemMiddleware 处理工具返回结果                                   │
│                                                                              │
│  交互流程:                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. QueryResult 返回 10000 行                                        │    │
│  │     ↓                                                                │    │
│  │  2. Insight Agent 内部分块处理                                       │    │
│  │     - Phase 1: 统计分析（全量数据）                                  │    │
│  │     - Phase 2: 分块分析（每块 < 500 行）                             │    │
│  │     ↓                                                                │    │
│  │  3. 分析师 LLM 只看到当前块 + top_n_summary                          │    │
│  │     - 当前块: 500 行                                                 │    │
│  │     - top_n_summary: 5 行                                            │    │
│  │     - 统计信息: 几十个数字                                           │    │
│  │     ↓                                                                │    │
│  │  4. 如果单个块仍然太大（> 20000 tokens）                             │    │
│  │     → FilesystemMiddleware 自动转存                                  │    │
│  │     → 返回文件路径，LLM 可用 read_file 读取                          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  关键点:                                                                    │
│  - 洞察系统内部已经做了分块，通常不会触发 FilesystemMiddleware             │
│  - FilesystemMiddleware 是最后的安全网                                      │
│  - 大数据块的 tail_summary 已经是压缩后的摘要                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**代码示例**:

```python
# 洞察系统内部已经控制了数据大小
class ChunkAnalyzer:
    """分析师 LLM"""
    
    async def analyze_chunk(
        self,
        chunk: PriorityChunk,
        profile: DataInsightProfile,
        top_n_summary: List[Dict],  # 只有 5 行
        existing_insights: List[Insight],
        question: str,
    ) -> List[Insight]:
        # 构建 prompt 时控制数据大小
        prompt_data = {
            "chunk_data": chunk.data[:500],  # 最多 500 行
            "chunk_summary": chunk.tail_summary if chunk.row_count > 500 else None,
            "top_n_summary": top_n_summary,  # 5 行
            "statistics": profile.statistics,  # 几十个数字
        }
        
        # 如果仍然太大，FilesystemMiddleware 会自动处理
        # 但通常不会触发，因为我们已经控制了大小
```

### 2. SummarizationMiddleware 与洞察保护

**关键原则**: SummarizationMiddleware 只总结对话消息，**不总结洞察结果**。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SummarizationMiddleware 与洞察系统                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  问题场景:                                                                  │
│  - 多轮对话后，消息历史超过 100000 tokens                                   │
│  - 需要总结以释放 context window                                            │
│  - 但洞察结果不能被总结（会丢失细节）                                       │
│                                                                              │
│  解决方案:                                                                  │
│  - SummarizationMiddleware 只处理 HumanMessage 和 AIMessage                 │
│  - InsightResult 存储在 state 中，不在消息历史中                            │
│  - 累积洞察通过 InsightAccumulator 管理，不受总结影响                       │
│                                                                              │
│  消息类型分类:                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  会被总结的消息:                                                     │    │
│  │  - HumanMessage: "哪个门店销售额最高？"                              │    │
│  │  - AIMessage: "让我分析一下数据..."                                  │    │
│  │  - ToolMessage: 工具调用结果                                         │    │
│  │                                                                      │    │
│  │  不会被总结的数据:                                                   │    │
│  │  - state["insights"]: 累积的洞察列表                                 │    │
│  │  - state["data_insight_profile"]: 整体画像                           │    │
│  │  - state["exploration_questions"]: 探索问题                          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  总结触发时:                                                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Before:                                                             │    │
│  │  messages = [                                                        │    │
│  │    HumanMessage("哪个门店销售额最高？"),                             │    │
│  │    AIMessage("让我分析..."),                                         │    │
│  │    ToolMessage("QueryResult: 500 rows..."),                          │    │
│  │    AIMessage("A店销售额最高..."),                                    │    │
│  │    HumanMessage("为什么？"),                                         │    │
│  │    ...                                                               │    │
│  │  ]                                                                   │    │
│  │  state["insights"] = [Insight1, Insight2, ...]  # 不变               │    │
│  │                                                                      │    │
│  │  After (总结后):                                                     │    │
│  │  messages = [                                                        │    │
│  │    SystemMessage("对话摘要: 用户询问门店销售额，发现A店最高..."),    │    │
│  │    HumanMessage("最近的问题..."),  # 保留最近 10 条                  │    │
│  │  ]                                                                   │    │
│  │  state["insights"] = [Insight1, Insight2, ...]  # 保持不变！         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**代码示例**:

```python
# 洞察存储在 state 中，不在消息历史中
class InsightAgentState(TypedDict):
    """Insight Agent 状态"""
    messages: Annotated[List[BaseMessage], add_messages]  # 会被总结
    
    # 以下不会被总结
    insights: List[Insight]                    # 累积洞察
    data_insight_profile: DataInsightProfile   # 整体画像
    exploration_questions: List[ExplorationQuestion]  # 探索问题
    current_round: int                         # 当前轮次

# SummarizationMiddleware 配置
summarization_middleware = SummarizationMiddleware(
    model="gpt-4",
    trigger=("tokens", 100000),
    keep=("messages", 10),
    # 只处理 messages，不处理 state 中的其他字段
)
```

### 3. TodoListMiddleware 与探索问题管理

**场景**: Replanner 生成的探索问题存储在 TodoList 中，供用户审查。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TodoListMiddleware 与探索问题                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  流程:                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. Replanner 生成探索问题                                           │    │
│  │     exploration_questions = [                                        │    │
│  │       {q: "A店各产品类别销售额？", priority: 1},                     │    │
│  │       {q: "A店过去12个月趋势？", priority: 2},                       │    │
│  │       {q: "A店与同城市门店对比？", priority: 3},                     │    │
│  │     ]                                                                │    │
│  │     ↓                                                                │    │
│  │  2. Replanner 调用 write_todos 存储问题                              │    │
│  │     write_todos([                                                    │    │
│  │       "[P1] A店各产品类别销售额？",                                  │    │
│  │       "[P2] A店过去12个月趋势？",                                    │    │
│  │       "[P3] A店与同城市门店对比？",                                  │    │
│  │     ])                                                               │    │
│  │     ↓                                                                │    │
│  │  3. HumanInTheLoopMiddleware 暂停（如果配置）                        │    │
│  │     用户可以:                                                        │    │
│  │     - 选择要执行的问题                                               │    │
│  │     - 修改问题文本                                                   │    │
│  │     - 添加新问题                                                     │    │
│  │     - 拒绝所有问题（结束探索）                                       │    │
│  │     ↓                                                                │    │
│  │  4. 继续执行选中的问题                                               │    │
│  │     read_todos() → 获取用户确认的问题列表                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  TodoList 格式:                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  [P1] A店各产品类别销售额？                                          │    │
│  │       type: drill_down                                               │    │
│  │       target: 产品类别                                               │    │
│  │       reasoning: 按产品维度展开，找出主要贡献类别                    │    │
│  │                                                                      │    │
│  │  [P2] A店过去12个月趋势？                                            │    │
│  │       type: time_series                                              │    │
│  │       target: 月份                                                   │    │
│  │       reasoning: 按时间维度展开，了解增长趋势                        │    │
│  │                                                                      │    │
│  │  [P3] A店与同城市门店对比？                                          │    │
│  │       type: peer_comparison                                          │    │
│  │       target: 门店                                                   │    │
│  │       filter: 城市 = A店所在城市                                     │    │
│  │       reasoning: 横向对比，了解是否是区域优势                        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**代码示例**:

```python
# Replanner 调用 write_todos 存储探索问题
class ReplannerAgent:
    async def replan(self, context: Dict) -> ReplanDecision:
        decision = await self._generate_replan_decision(context)
        
        if decision.should_replan and decision.exploration_questions:
            # 格式化问题为 TodoList 格式
            todos = []
            for q in decision.exploration_questions:
                todo = f"[P{q.priority}] {q.question}\n"
                todo += f"       type: {q.exploration_type}\n"
                todo += f"       target: {q.target_dimension}\n"
                if q.filter:
                    todo += f"       filter: {q.filter}\n"
                todo += f"       reasoning: {q.reasoning}"
                todos.append(todo)
            
            # 调用 write_todos 存储
            await self.tools["write_todos"](todos)
        
        return decision
```

### 4. HumanInTheLoopMiddleware 与用户审查

**场景**: 在执行探索问题前，允许用户审查和修改。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HumanInTheLoopMiddleware 与探索问题审查                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  配置:                                                                      │
│  human_middleware = HumanInTheLoopMiddleware(                               │
│      interrupt_on=["write_todos"],  # 在写入 todos 时暂停                   │
│  )                                                                          │
│                                                                              │
│  用户交互界面:                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  🔍 Replanner 建议以下探索问题:                                      │    │
│  │                                                                      │    │
│  │  ☑ [P1] A店各产品类别销售额？                                        │    │
│  │        → 按产品维度展开，找出主要贡献类别                            │    │
│  │                                                                      │    │
│  │  ☑ [P2] A店过去12个月趋势？                                          │    │
│  │        → 按时间维度展开，了解增长趋势                                │    │
│  │                                                                      │    │
│  │  ☐ [P3] A店与同城市门店对比？                                        │    │
│  │        → 横向对比，了解是否是区域优势                                │    │
│  │                                                                      │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │ + 添加自定义问题...                                          │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  │                                                                      │    │
│  │  [继续执行选中问题]  [跳过所有问题]  [结束探索]                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  用户操作:                                                                  │
│  - 勾选/取消勾选问题                                                        │
│  - 点击问题文本进行编辑                                                     │
│  - 添加自定义问题                                                           │
│  - 选择执行策略                                                             │
│                                                                              │
│  执行结果:                                                                  │
│  - 继续执行: 执行选中的问题                                                 │
│  - 跳过所有: 跳过本轮，继续下一轮重规划                                     │
│  - 结束探索: 停止重规划，返回当前洞察                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**代码示例**:

```python
# 中间件配置
def create_insight_middleware_stack(config: Dict) -> List[Middleware]:
    middleware = [
        # 基础中间件
        ModelRetryMiddleware(max_retries=3),
        ToolRetryMiddleware(max_retries=3),
        FilesystemMiddleware(tool_token_limit_before_evict=20000),
        PatchToolCallsMiddleware(),
        
        # 总结中间件（只总结消息，不总结洞察）
        SummarizationMiddleware(
            model=config.get("model_name", "gpt-4"),
            trigger=("tokens", 100000),
            keep=("messages", 10),
        ),
        
        # TodoList 中间件
        TodoListMiddleware(),
    ]
    
    # 可选：人工审查
    if config.get("enable_human_review", False):
        middleware.append(HumanInTheLoopMiddleware(
            interrupt_on=["write_todos"],
        ))
    
    return middleware
```

### 5. 中间件与洞察系统的完整交互流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    完整交互流程                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Round 1: 初始分析                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. 用户: "哪个门店销售额最高？为什么？"                             │    │
│  │     ↓                                                                │    │
│  │  2. Query Agent 执行查询                                             │    │
│  │     → QueryResult: 500 行                                            │    │
│  │     → FilesystemMiddleware: 不触发（500行 < 20000 tokens）           │    │
│  │     ↓                                                                │    │
│  │  3. Insight Agent 分析                                               │    │
│  │     → Phase 1: 统计分析（全量 500 行）                               │    │
│  │     → Phase 2: 分块分析（3 个块，每块 ~150 行）                      │    │
│  │     → 输出: InsightResult + DataInsightProfile                       │    │
│  │     → state["insights"] = [Insight1, Insight2]  # 存储在 state       │    │
│  │     ↓                                                                │    │
│  │  4. Replanner 评估                                                   │    │
│  │     → completeness_score = 0.5                                       │    │
│  │     → 生成 3 个探索问题                                              │    │
│  │     → 调用 write_todos([...])                                        │    │
│  │     → TodoListMiddleware: 存储问题                                   │    │
│  │     → HumanInTheLoopMiddleware: 暂停（如果配置）                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  用户审查（如果启用）:                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  用户选择执行 Q1 和 Q2，跳过 Q3                                      │    │
│  │  → 修改 TodoList                                                     │    │
│  │  → 继续执行                                                          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Round 2: 并行执行探索问题                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  1. 读取 TodoList                                                    │    │
│  │     → read_todos() → [Q1, Q2]                                        │    │
│  │     ↓                                                                │    │
│  │  2. 并行执行 Q1 和 Q2                                                │    │
│  │     → Query Agent × 2                                                │    │
│  │     → Insight Agent × 2                                              │    │
│  │     → 累积洞察: state["insights"] += [Insight3, Insight4, Insight5]  │    │
│  │     ↓                                                                │    │
│  │  3. 消息历史增长                                                     │    │
│  │     → 如果超过 100000 tokens                                         │    │
│  │     → SummarizationMiddleware 触发                                   │    │
│  │     → 总结消息历史，但 state["insights"] 保持不变！                  │    │
│  │     ↓                                                                │    │
│  │  4. Replanner 再次评估                                               │    │
│  │     → completeness_score = 0.92                                      │    │
│  │     → should_replan = False                                          │    │
│  │     → 结束探索                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  最终输出:                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  InsightResult:                                                     │    │
│  │  - findings: [Insight1, Insight2, Insight3, Insight4, Insight5]     │    │
│  │  - summary: "A店销售额最高，主要因为..."                            │    │
│  │  - confidence: 0.92                                                 │    │
│  │  - exploration_rounds: 2                                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 中间件配置总结

| 中间件 | 与洞察系统的关系 | 配置建议 |
|--------|------------------|----------|
| FilesystemMiddleware | 大数据块转存（通常不触发） | `token_limit=20000` |
| SummarizationMiddleware | 只总结消息，不总结洞察 | `trigger=100000, keep=10` |
| TodoListMiddleware | 存储探索问题 | 默认启用 |
| HumanInTheLoopMiddleware | 用户审查探索问题 | `interrupt_on=["write_todos"]`，可选 |
| ModelRetryMiddleware | LLM 调用重试 | `max_retries=3` |
| ToolRetryMiddleware | 工具调用重试 | `max_retries=3` |
| PatchToolCallsMiddleware | 修复悬空工具调用 | 默认启用 |

---

## 总结

### 设计变化

| 方面 | 旧设计 | 新设计 |
|------|--------|--------|
| 分析流程 | 分块 → 分析 | 整体分析 → 分块 → 深入分析 |
| 整体理解 | 无 | Phase 1 统计/ML 分析 |
| 分块策略 | 固定（位置/语义） | 动态（基于数据特征） |
| 重规划 | 单问题 | 多问题，按优先级 |
| dimension_hierarchy | 部分使用 | 完整使用所有 category |

### 新增组件

1. **StatisticalAnalyzer**: 统计/ML 整体分析
2. **DataInsightProfile**: 整体洞察画像
3. **ExplorationQuestion**: 探索问题模型
4. **ClusterInfo**: 聚类信息模型

### 关键改进

1. **先整体后局部**: 先用统计/ML 了解数据整体特征，再有针对性地深入
2. **智能分块**: 基于数据特征（聚类/变点/帕累托）选择最佳分块策略
3. **多问题探索**: Replanner 生成多个探索问题，按优先级执行
4. **完整维度支持**: 使用 dimension_hierarchy 的所有 7 种 category
