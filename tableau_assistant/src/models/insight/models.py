"""
Insight System Data Models

Defines all data structures used by the insight analysis system.

Design Specification: Follows PROMPT_AND_MODEL_GUIDE.md
- Uses XML tags for field descriptions
- Includes decision trees for complex models
- Includes fill order and conditional groups

Progressive Insight Design: Follows progressive-insight-analysis/design.md
- Priority-based chunking (URGENT/HIGH/MEDIUM/LOW/DEFERRED)
- AI-driven next bite selection
- AI-driven insight accumulation
- Early stopping mechanism
"""

from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Dict, List, Any, Optional, Literal, Union
from datetime import datetime
from enum import IntEnum


class ChunkPriority(IntEnum):
    """
    数据块优先级
    
    <what>定义数据块的分析优先级，数值越小优先级越高</what>
    
    <design_note>
    基于"AI 宝宝吃饭"理念：
    - URGENT: 异常值（不好吃的或特别好吃的）→ 最先分析
    - HIGH: Top 数据（肉）→ 必须分析
    - MEDIUM: 中间数据（蔬菜）→ 选择性分析
    - LOW: 较低数据（汤）→ 可选分析
    - DEFERRED: 尾部数据（剩菜）→ AI 决定是否需要
    </design_note>
    """
    URGENT = 1    # 异常值，最优先
    HIGH = 2      # Top 100 行
    MEDIUM = 3    # 101-500 行
    LOW = 4       # 501-1000 行
    DEFERRED = 5  # 1000+ 行（尾部数据）


class ColumnStats(BaseModel):
    """
    Statistical information for a numeric column.
    
    <what>单个数值列的统计信息，包含均值、中位数、标准差等</what>
    
    <examples>
    Input: DataFrame column "Sales" with values [100, 200, 300, 400, 500]
    Output: {
        "mean": 300.0,
        "median": 300.0,
        "std": 158.11,
        "min": 100.0,
        "max": 500.0,
        "q25": 200.0,
        "q75": 400.0
    }
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    mean: float = Field(
        description="""<what>平均值</what>
<when>ALWAYS required</when>
<how>Sum of values / count of values</how>"""
    )
    
    median: float = Field(
        description="""<what>中位数</what>
<when>ALWAYS required</when>
<how>Middle value when sorted</how>"""
    )
    
    std: float = Field(
        description="""<what>标准差</what>
<when>ALWAYS required</when>
<how>Measure of dispersion</how>"""
    )
    
    min: float = Field(
        description="""<what>最小值</what>
<when>ALWAYS required</when>"""
    )
    
    max: float = Field(
        description="""<what>最大值</what>
<when>ALWAYS required</when>"""
    )
    
    q25: float = Field(
        description="""<what>25% 分位数</what>
<when>ALWAYS required</when>"""
    )
    
    q75: float = Field(
        description="""<what>75% 分位数</what>
<when>ALWAYS required</when>"""
    )


class SemanticGroup(BaseModel):
    """
    A group of columns with the same semantic type.
    
    <what>具有相同语义类型的列分组，来自 dimension_hierarchy</what>
    
    <design_note>
    语义分组直接从 metadata.dimension_hierarchy 获取，
    不使用硬编码关键词规则匹配。
    </design_note>
    
    <examples>
    Example 1 - Time group:
    {"type": "time", "columns": ["Order Date", "Ship Date"]}
    
    Example 2 - Geographic group:
    {"type": "geographic", "columns": ["Country", "State", "City"]}
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    type: Literal["time", "category", "numeric", "geographic"] = Field(
        description="""<what>语义类型</what>
<when>ALWAYS required</when>
<how>From dimension_hierarchy.category mapping</how>

<values>
- time: 时间列 (from category="time")
- geographic: 地理列 (from category="geographic")
- category: 分类列 (from category="product", "customer", "organization", etc.)
- numeric: 数值列 (measures)
</values>"""
    )
    
    columns: List[str] = Field(
        description="""<what>属于该语义组的列名列表</what>
<when>ALWAYS required</when>
<how>List of column names from dimension_hierarchy</how>"""
    )


class DataProfile(BaseModel):
    """
    Profile of a dataset including statistics and semantic groups.
    
    <what>数据集的画像，包含统计信息和语义分组</what>
    
    <examples>
    Input: DataFrame with 100 rows, 5 columns
    Output: {
        "row_count": 100,
        "column_count": 5,
        "density": 0.98,
        "statistics": {"Sales": {...}, "Profit": {...}},
        "semantic_groups": [
            {"type": "time", "columns": ["Order Date"]},
            {"type": "category", "columns": ["Category", "Region"]},
            {"type": "numeric", "columns": ["Sales", "Profit"]}
        ]
    }
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    row_count: int = Field(
        description="""<what>数据行数</what>
<when>ALWAYS required</when>"""
    )
    
    column_count: int = Field(
        description="""<what>数据列数</what>
<when>ALWAYS required</when>"""
    )
    
    density: float = Field(
        ge=0.0, le=1.0,
        description="""<what>数据密度（非空比例）</what>
<when>ALWAYS required</when>
<how>non_null_cells / total_cells</how>

<values>
- 1.0: 完全无空值
- 0.0: 全部为空
</values>"""
    )
    
    statistics: Dict[str, ColumnStats] = Field(
        default_factory=dict,
        description="""<what>每个数值列的统计信息</what>
<when>IF numeric columns exist</when>
<how>Key is column name, value is ColumnStats</how>"""
    )
    
    semantic_groups: List[SemanticGroup] = Field(
        default_factory=list,
        description="""<what>语义分组列表</what>
<when>ALWAYS (may be empty)</when>
<how>Built from dimension_hierarchy</how>"""
    )


class AnomalyDetail(BaseModel):
    """
    Details about a specific anomaly.
    
    <what>单个异常的详细信息</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    index: int = Field(
        description="""<what>异常行索引</what>
<when>ALWAYS required</when>"""
    )
    
    values: Dict[str, Any] = Field(
        description="""<what>异常行的值</what>
<when>ALWAYS required</when>"""
    )
    
    reason: str = Field(
        description="""<what>异常原因</what>
<when>ALWAYS required</when>
<how>Explain why this row is anomalous</how>"""
    )
    
    column: Optional[str] = Field(
        default=None,
        description="""<what>异常所在列</what>
<when>IF anomaly is column-specific</when>"""
    )
    
    severity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="""<what>严重程度</what>
<when>ALWAYS (default: 0.0)</when>

<values>
- 0.0-0.3: 轻微异常
- 0.3-0.7: 中等异常
- 0.7-1.0: 严重异常
</values>"""
    )


class AnomalyResult(BaseModel):
    """
    Result of anomaly detection.
    
    <what>异常检测的结果</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    outliers: List[int] = Field(
        default_factory=list,
        description="""<what>异常行索引列表</what>
<when>ALWAYS (may be empty)</when>"""
    )
    
    anomaly_ratio: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="""<what>异常比例</what>
<when>ALWAYS required</when>
<how>len(outliers) / total_rows</how>"""
    )
    
    anomaly_details: List[AnomalyDetail] = Field(
        default_factory=list,
        description="""<what>异常详情列表</what>
<when>IF outliers exist</when>
<how>Top 10 anomalies with details</how>"""
    )


class DataChunk(BaseModel):
    """
    A chunk of data for progressive analysis.
    
    <what>用于渐进式分析的数据块</what>
    
    <examples>
    Example 1 - Chunk by category:
    {
        "data": [...],
        "chunk_id": 0,
        "chunk_name": "Category=Technology",
        "row_count": 50,
        "column_names": ["Category", "Sales", "Profit"],
        "group_key": "Category",
        "group_value": "Technology"
    }
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    data: List[Dict[str, Any]] = Field(
        description="""<what>数据记录列表</what>
<when>ALWAYS required</when>"""
    )
    
    chunk_id: int = Field(
        description="""<what>块 ID</what>
<when>ALWAYS required</when>"""
    )
    
    chunk_name: str = Field(
        description="""<what>块名称</what>
<when>ALWAYS required</when>
<how>Format: "{group_key}={group_value}" or "Chunk N"</how>"""
    )
    
    row_count: int = Field(
        description="""<what>行数</what>
<when>ALWAYS required</when>"""
    )
    
    column_names: List[str] = Field(
        description="""<what>列名列表</what>
<when>ALWAYS required</when>"""
    )
    
    group_key: Optional[str] = Field(
        default=None,
        description="""<what>分组键</what>
<when>IF chunked by column</when>"""
    )
    
    group_value: Optional[Any] = Field(
        default=None,
        description="""<what>分组值</what>
<when>IF chunked by column</when>

<dependency>
- field: group_key
- condition: group_key is not None
</dependency>"""
    )


class Insight(BaseModel):
    """
    单个洞察
    
    <what>一条具体的分析发现</what>
    
    <decision_tree>
    START
      │
      ├─► type = ? (ALWAYS fill first)
      │   │
      │   ├─► trend: 数据变化趋势
      │   ├─► anomaly: 异常值或离群点
      │   ├─► comparison: 不同维度的对比
      │   └─► pattern: 数据分布特征、规律
      │
      ├─► title = ? (ALWAYS fill)
      │
      ├─► description = ? (ALWAYS fill)
      │
      ├─► importance = ? (ALWAYS fill, default: 0.5)
      │
      ├─► evidence = ? (IF supporting data exists)
      │
      └─► related_columns = ? (IF columns are relevant)
      
    END
    </decision_tree>
    
    <fill_order>
    ┌────┬─────────────────────────┬─────────────────────────────────────┐
    │ #  │ Field                   │ Condition                           │
    ├────┼─────────────────────────┼─────────────────────────────────────┤
    │ 1  │ type                    │ ALWAYS (determines insight category)│
    │ 2  │ title                   │ ALWAYS                              │
    │ 3  │ description             │ ALWAYS                              │
    │ 4  │ importance              │ ALWAYS (default: 0.5)               │
    │ 5  │ evidence                │ IF supporting data exists           │
    │ 6  │ related_columns         │ IF columns are relevant             │
    └────┴─────────────────────────┴─────────────────────────────────────┘
    </fill_order>
    
    <examples>
    Example 1 - Trend insight:
    {
        "type": "trend",
        "title": "销售额持续增长",
        "description": "过去6个月销售额环比增长15%",
        "importance": 0.9,
        "evidence": {"growth_rate": 0.15, "period": "6 months"},
        "related_columns": ["Sales", "Order Date"]
    }
    
    Example 2 - Anomaly insight:
    {
        "type": "anomaly",
        "title": "检测到异常高值",
        "description": "Technology 类别在 West 地区的销售额异常高",
        "importance": 0.8,
        "evidence": {"value": 50000, "expected": 15000},
        "related_columns": ["Category", "Region", "Sales"]
    }
    </examples>
    
    <anti_patterns>
    ❌ ERROR 1: Using invalid type
    Wrong: {"type": "summary"}
    Right: {"type": "pattern"}
    
    ❌ ERROR 2: Missing required fields
    Wrong: {"type": "trend", "title": "..."}
    Right: {"type": "trend", "title": "...", "description": "..."}
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    type: Literal["trend", "anomaly", "comparison", "pattern"] = Field(
        description="""<what>洞察类型</what>
<when>ALWAYS required (fill first)</when>
<how>Choose based on insight nature</how>

<values>
- trend: 趋势洞察（数据变化趋势）
- anomaly: 异常洞察（异常值或离群点）
- comparison: 对比洞察（不同维度的对比）
- pattern: 模式洞察（数据分布特征、规律）
</values>

<decision_rule>
- 数据随时间变化 → trend
- 发现异常值/离群点 → anomaly
- 不同组之间对比 → comparison
- 数据分布/规律 → pattern
</decision_rule>"""
    )
    
    title: str = Field(
        description="""<what>洞察标题</what>
<when>ALWAYS required</when>
<how>One-line summary of the insight</how>

<examples>
- "销售额持续增长"
- "检测到 5 个异常值"
- "Technology 类别销售领先"
</examples>"""
    )
    
    description: str = Field(
        description="""<what>洞察描述</what>
<when>ALWAYS required</when>
<how>Detailed explanation of the insight</how>"""
    )
    
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="""<what>重要性评分</what>
<when>ALWAYS (default: 0.5)</when>
<how>Based on business impact and confidence</how>

<values>
- 0.8-1.0: 高重要性（关键发现）
- 0.5-0.8: 中等重要性
- 0.0-0.5: 低重要性
</values>"""
    )
    
    evidence: Optional[Dict[str, Any]] = Field(
        default=None,
        description="""<what>支持证据</what>
<when>IF supporting data exists</when>
<how>Dict with key metrics/values</how>

<examples>
- {"growth_rate": 0.15, "period": "6 months"}
- {"outlier_count": 5, "anomaly_ratio": 0.05}
</examples>"""
    )
    
    related_columns: List[str] = Field(
        default_factory=list,
        description="""<what>相关列</what>
<when>IF columns are relevant to insight</when>
<how>List of column names involved</how>"""
    )
    
    chunk_id: Optional[int] = Field(
        default=None,
        description="""<what>来源块 ID</what>
<when>IF insight from chunked analysis</when>"""
    )
    
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="""<what>创建时间</what>
<when>ALWAYS (auto-generated)</when>"""
    )


class TailDataSummary(BaseModel):
    """
    尾部数据摘要
    
    <what>1000+ 行尾部数据的摘要信息，不丢弃数据，让 AI 决定是否需要</what>
    
    <design_note>
    基于设计文档："剩菜也要留着"
    - 保留完整数据引用
    - 提供统计摘要
    - 提供采样数据
    - 检测尾部异常值
    </design_note>
    """
    model_config = ConfigDict(extra="forbid")
    
    total_rows: int = Field(
        description="""<what>尾部数据总行数</what>"""
    )
    
    sample_data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="""<what>采样数据（最多 100 行）</what>"""
    )
    
    statistics: Dict[str, Any] = Field(
        default_factory=dict,
        description="""<what>统计信息（均值、中位数、分布等）</what>"""
    )
    
    anomaly_count: int = Field(
        default=0,
        description="""<what>尾部数据中的异常值数量</what>"""
    )
    
    patterns: Dict[str, Any] = Field(
        default_factory=dict,
        description="""<what>检测到的模式（分布、趋势、聚类）</what>"""
    )


class PriorityChunk(BaseModel):
    """
    带优先级的数据块
    
    <what>用于渐进式分析的带优先级数据块</what>
    
    <design_note>
    基于"AI 宝宝吃饭"理念的智能优先级分块：
    - URGENT: 异常值数据
    - HIGH: Top 100 行
    - MEDIUM: 101-500 行
    - LOW: 501-1000 行
    - DEFERRED: 1000+ 行（尾部摘要）
    </design_note>
    """
    model_config = ConfigDict(extra="forbid")
    
    chunk_id: int = Field(
        description="""<what>块 ID</what>"""
    )
    
    chunk_type: str = Field(
        description="""<what>块类型</what>
        
<values>
位置分块:
- anomalies: 异常值数据
- top_data: Top 100 行（排名最高）
- mid_data: 101-500 行（中间层）
- low_data: 501-1000 行（较低层）
- tail_data: 1000+ 行（尾部数据摘要）

聚类分块:
- cluster_0, cluster_1, ...: 聚类分块

变点分块:
- segment_0, segment_1, ...: 时间段分块

帕累托分块:
- pareto_top_20: Top 20%
- pareto_mid_30: Mid 30%
- pareto_bottom_50: Bottom 50%

统计分块:
- high_value: > Q75
- medium_value: Q25-Q75
- low_value: < Q25

语义分块:
- semantic_{column}: 按语义列分块
</values>"""
    )
    
    priority: int = Field(
        description="""<what>优先级（1-5，越小越优先）</what>"""
    )
    
    data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="""<what>数据记录列表</what>
<when>For anomalies/top_data/mid_data/low_data</when>"""
    )
    
    tail_summary: Optional[TailDataSummary] = Field(
        default=None,
        description="""<what>尾部数据摘要</what>
<when>ONLY for tail_data chunk type</when>"""
    )
    
    row_count: int = Field(
        description="""<what>行数</what>"""
    )
    
    column_names: List[str] = Field(
        default_factory=list,
        description="""<what>列名列表</what>"""
    )
    
    description: str = Field(
        default="",
        description="""<what>块描述（用于 AI 理解）</what>"""
    )
    
    estimated_value: str = Field(
        default="unknown",
        description="""<what>估算价值</what>
        
<values>
- high: 高价值（异常值、Top 数据）
- medium: 中等价值（中间数据）
- low: 较低价值（补充数据）
- potential: 潜在价值（尾部数据可能有宝藏）
- unknown: 未知
</values>"""
    )


class NextBiteDecision(BaseModel):
    """
    下一口决策（由 AI 生成）
    
    <what>AI 决定下一步分析哪个数据块</what>
    
    <design_note>
    基于"AI 宝宝吃饭"理念：
    - 吃了辣的 → 下一口选择清淡的
    - 发现第一名 → 分析为什么第一
    - 发现异常 → 深入调查
    - 吃饱了 → 早停
    </design_note>
    """
    model_config = ConfigDict(extra="forbid")
    
    should_continue: bool = Field(
        description="""<what>是否继续分析</what>
<when>ALWAYS required</when>

<decision_rule>
- 问题已充分回答 → False
- 洞察质量高且完整 → False
- 还有重要数据未分析 → True
- 发现异常需要深入 → True
</decision_rule>"""
    )
    
    next_chunk_type: Optional[Literal["anomalies", "top_data", "mid_data", "low_data", "tail_data"]] = Field(
        default=None,
        description="""<what>下一个要分析的块类型</what>
<when>IF should_continue is True</when>"""
    )
    
    reason: str = Field(
        default="",
        description="""<what>决策原因</what>"""
    )
    
    eating_strategy: str = Field(
        default="",
        description="""<what>吃饭策略说明</what>
        
<examples>
- "发现第一名，分析为什么第一"
- "吃了辣的，选择清淡的"
- "发现异常，深入调查"
- "吃饱了，该停了"
</examples>"""
    )
    
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="""<what>决策置信度</what>"""
    )


class InsightQuality(BaseModel):
    """
    洞察质量评估
    
    <what>评估当前洞察是否足够回答问题</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    completeness: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>完整度（是否充分回答了问题）</what>"""
    )
    
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>置信度</what>"""
    )
    
    need_more_data: bool = Field(
        default=True,
        description="""<what>是否需要更多数据</what>"""
    )
    
    question_answered: bool = Field(
        default=False,
        description="""<what>核心问题是否已回答</what>"""
    )


class ClusterInfo(BaseModel):
    """
    聚类信息
    
    <what>K-Means 聚类分析的单个聚类结果</what>
    
    <design_note>
    用于 Phase 1 统计/ML 分析，支持按聚类分块策略。
    </design_note>
    """
    model_config = ConfigDict(extra="forbid")
    
    cluster_id: int = Field(
        description="""<what>聚类 ID</what>"""
    )
    
    center: Dict[str, float] = Field(
        default_factory=dict,
        description="""<what>聚类中心（各数值列的均值）</what>"""
    )
    
    size: int = Field(
        description="""<what>聚类大小（行数）</what>"""
    )
    
    label: str = Field(
        default="",
        description="""<what>聚类标签</what>
        
<values>
- 高绩效: 数值最高的聚类
- 中等: 中间聚类
- 低绩效: 数值最低的聚类
- 异常: 异常值聚类
</values>"""
    )
    
    indices: List[int] = Field(
        default_factory=list,
        description="""<what>属于该聚类的行索引</what>"""
    )


class DataInsightProfile(BaseModel):
    """
    数据洞察画像 - Phase 1 统计/ML 分析结果
    
    <what>整体数据特征画像，用于指导 Phase 2 分块策略和 Replanner</what>
    
    <design_note>
    类似 Tableau Pulse 的设计理念：
    - 先用统计/ML 方法了解数据整体特征
    - 再有针对性地进行 LLM 深入分析
    - 传递给 Replanner 指导探索问题生成
    </design_note>
    
    <examples>
    Example - Long tail distribution:
    {
        "distribution_type": "long_tail",
        "skewness": 2.3,
        "kurtosis": 8.5,
        "pareto_ratio": 0.78,
        "pareto_threshold": 0.18,
        "anomaly_indices": [0, 5],
        "anomaly_ratio": 0.02,
        "clusters": [...],
        "recommended_chunking_strategy": "by_pareto"
    }
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    # 分布分析
    distribution_type: Literal["normal", "long_tail", "bimodal", "uniform", "unknown"] = Field(
        default="unknown",
        description="""<what>分布类型</what>
        
<values>
- normal: 正态分布（|skew| < 0.5）
- long_tail: 长尾分布（skew > 1 或 skew < -1）
- bimodal: 双峰分布
- uniform: 均匀分布
- unknown: 无法判断
</values>"""
    )
    
    skewness: float = Field(
        default=0.0,
        description="""<what>偏度</what>
<how>
- |skew| < 0.5: 近似正态
- skew > 1: 右偏/长尾
- skew < -1: 左偏
</how>"""
    )
    
    kurtosis: float = Field(
        default=0.0,
        description="""<what>峰度</what>
<how>
- kurtosis > 3: 尖峰（数据集中）
- kurtosis < 3: 平峰（数据分散）
</how>"""
    )
    
    # 帕累托分析
    pareto_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>帕累托比率（top 20% 贡献的比例）</what>
<how>典型业务数据：top 20% 贡献 80%</how>"""
    )
    
    pareto_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>帕累托阈值（贡献 80% 的数据占比）</what>"""
    )
    
    # 异常检测
    anomaly_indices: List[int] = Field(
        default_factory=list,
        description="""<what>异常值行索引</what>"""
    )
    
    anomaly_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>异常比例</what>"""
    )
    
    anomaly_method: str = Field(
        default="IQR",
        description="""<what>异常检测方法</what>
        
<values>
- IQR: 四分位距法
- Z-Score: Z 分数法
- Isolation Forest: 隔离森林
</values>"""
    )
    
    # 聚类分析
    clusters: List[ClusterInfo] = Field(
        default_factory=list,
        description="""<what>聚类结果</what>"""
    )
    
    optimal_k: int = Field(
        default=0,
        description="""<what>最优聚类数</what>"""
    )
    
    clustering_method: str = Field(
        default="KMeans",
        description="""<what>聚类方法</what>"""
    )
    
    # 趋势检测（可选，仅时间序列数据）
    trend: Optional[Literal["increasing", "decreasing", "stable"]] = Field(
        default=None,
        description="""<what>趋势方向</what>
<when>IF time column exists</when>"""
    )
    
    trend_slope: Optional[float] = Field(
        default=None,
        description="""<what>趋势斜率</what>
<when>IF trend is detected</when>"""
    )
    
    change_points: Optional[List[int]] = Field(
        default=None,
        description="""<what>变点索引</what>
<when>IF change points detected</when>"""
    )
    
    # 相关性分析
    correlations: Dict[str, float] = Field(
        default_factory=dict,
        description="""<what>列间相关性</what>
<how>Key format: "col1|col2", value: correlation coefficient</how>"""
    )
    
    # 统计信息（从 DataProfile 复制）
    statistics: Dict[str, ColumnStats] = Field(
        default_factory=dict,
        description="""<what>各数值列的统计信息</what>"""
    )
    
    # 推荐的分块策略
    recommended_chunking_strategy: Literal[
        "by_cluster",      # 按聚类分块
        "by_change_point", # 按变点分块
        "by_pareto",       # 按帕累托分块
        "by_semantic",     # 按语义值分块
        "by_statistics",   # 按统计特征分块
        "by_position"      # 按位置分块（最后手段）
    ] = Field(
        default="by_position",
        description="""<what>推荐的分块策略</what>
        
<decision_rule>
优先级：聚类 > 变点 > 帕累托 > 语义 > 统计 > 位置
- clusters >= 2 → by_cluster
- change_points >= 1 → by_change_point
- distribution_type == "long_tail" → by_pareto
- 有合适语义列 → by_semantic
- 有数值列 → by_statistics
- 其他 → by_position
</decision_rule>"""
    )
    
    # 主度量列
    primary_measure: Optional[str] = Field(
        default=None,
        description="""<what>主度量列名</what>"""
    )
    
    # Top N 数据摘要（用于分析师 LLM 对比）
    top_n_summary: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="""<what>Top N 数据摘要（默认 Top 5）</what>
<how>用于分析师 LLM 进行对比分析，如"是第2名的5倍"</how>"""
    )


class InsightResult(BaseModel):
    """
    洞察结果
    
    <what>Insight Agent 输出的分析洞察</what>
    
    <examples>
    Example - Complete result:
    {
        "summary": "共发现 5 个关键洞察（2个趋势, 2个对比, 1个异常）",
        "findings": [...],
        "confidence": 0.85,
        "strategy_used": "progressive",
        "chunks_analyzed": 3,
        "total_rows_analyzed": 500,
        "execution_time": 5.2
    }
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    summary: Optional[str] = Field(
        default=None,
        description="""<what>一句话总结</what>
<when>ALWAYS (may be empty for no insights)</when>
<how>Format: "共发现 N 个关键洞察（X个类型1, Y个类型2）"</how>"""
    )
    
    findings: List[Insight] = Field(
        default_factory=list,
        description="""<what>洞察列表</what>
<when>ALWAYS (may be empty)</when>
<how>Sorted by importance descending</how>"""
    )
    
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>整体置信度</what>
<when>ALWAYS required</when>
<how>Average importance of findings</how>"""
    )
    
    strategy_used: str = Field(
        default="direct",
        description="""<what>使用的分析策略</what>
<when>ALWAYS required</when>

<values>
- direct: 直接分析（<100 行）
- progressive: 渐进式分析（100-1000 行）
- hybrid: 混合分析（>1000 行）
</values>"""
    )
    
    chunks_analyzed: int = Field(
        default=0,
        description="""<what>分析的块数</what>
<when>ALWAYS required</when>"""
    )
    
    total_rows_analyzed: int = Field(
        default=0,
        description="""<what>分析的总行数</what>
<when>ALWAYS required</when>"""
    )
    
    execution_time: float = Field(
        default=0.0,
        description="""<what>执行时间（秒）</what>
<when>ALWAYS required</when>"""
    )
    
    # 新增：整体画像（传递给 Replanner）
    data_insight_profile: Optional[DataInsightProfile] = Field(
        default=None,
        description="""<what>数据洞察画像</what>
<when>IF Phase 1 analysis completed</when>
<how>传递给 Replanner 指导探索问题生成</how>"""
    )
    
    # 新增：是否需要更多数据
    need_more_data: bool = Field(
        default=False,
        description="""<what>是否需要更多数据</what>"""
    )
    
    missing_aspects: List[str] = Field(
        default_factory=list,
        description="""<what>缺失的方面</what>
<how>用于指导 Replanner 生成探索问题</how>"""
    )
