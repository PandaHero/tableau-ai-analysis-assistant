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
    
    group_value: Optional[Union[str, int, float, bool]] = Field(
        default=None,
        description="""<what>分组值</what>
<when>IF chunked by column</when>

<dependency>
- field: group_key
- condition: group_key is not None
</dependency>"""
    )


class InsightEvidence(BaseModel):
    """
    洞察证据 - 支持洞察的具体数据
    
    <what>洞察的数据支撑，包含关键指标和对比数据</what>
    """
    model_config = ConfigDict(extra="forbid")
    
    metric_name: Optional[str] = Field(
        default=None,
        description="""<what>指标名称</what>
<when>IF insight involves a specific metric</when>"""
    )
    
    metric_value: Optional[float] = Field(
        default=None,
        description="""<what>指标值</what>
<when>IF insight involves a specific metric</when>"""
    )
    
    comparison_value: Optional[float] = Field(
        default=None,
        description="""<what>对比值（如第二名、中位数等）</what>
<when>IF insight involves comparison</when>"""
    )
    
    ratio: Optional[float] = Field(
        default=None,
        description="""<what>比率（如是第二名的几倍）</what>
<when>IF insight involves ratio comparison</when>"""
    )
    
    percentage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="""<what>百分比（如占总量的比例）</what>
<when>IF insight involves percentage</when>"""
    )
    
    period: Optional[str] = Field(
        default=None,
        description="""<what>时间周期</what>
<when>IF insight involves time-based analysis</when>"""
    )
    
    additional_data: Optional[Dict[str, Union[str, int, float, bool]]] = Field(
        default=None,
        description="""<what>其他补充数据</what>
<when>IF standard fields don't cover all evidence</when>"""
    )


class Insight(BaseModel):
    """
    单个洞察 - 分析师 LLM 输出
    
    <what>一条具体的分析发现，由分析师 LLM 生成</what>
    
    <fill_order>
    1. type - 决定洞察类型
    2. title - 一句话总结
    3. description - 详细描述
    4. importance - 评估重要性
    5. evidence - 提供数据支撑
    </fill_order>
    
    <examples>
    Example 1 - Trend insight:
    {
        "type": "trend",
        "title": "销售额持续增长",
        "description": "过去6个月销售额环比增长15%",
        "importance": 0.9,
        "evidence": {"metric_name": "销售额", "ratio": 0.15, "period": "6 months"}
    }
    
    Example 2 - Anomaly insight:
    {
        "type": "anomaly",
        "title": "A店销售额异常高",
        "description": "A店销售额1000万，是第2名的5倍，属于极端异常值",
        "importance": 0.95,
        "evidence": {"metric_value": 1000, "comparison_value": 200, "ratio": 5.0}
    }
    
    Example 3 - Comparison insight:
    {
        "type": "comparison",
        "title": "Technology 类别贡献 60%",
        "description": "Technology 类别销售额占总销售额的 60%，远超其他类别",
        "importance": 0.85,
        "evidence": {"metric_name": "Technology", "percentage": 0.6}
    }
    </examples>
    
    <anti_patterns>
    ❌ Missing evidence for claims
    ❌ Vague descriptions without numbers
    ❌ Wrong type classification (e.g., using "pattern" for time-based changes)
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    # ===== 核心字段（分析师 LLM 输出）=====
    type: Literal["trend", "anomaly", "comparison", "pattern"] = Field(
        description="""<what>洞察类型</what>
<when>ALWAYS required</when>

<decision_rule>
IF data shows change over time → trend
IF data shows outliers or unexpected values → anomaly
IF data compares different groups/categories → comparison
IF data shows distribution or recurring patterns → pattern
</decision_rule>

<values>
- trend: 趋势洞察（数据随时间变化）
- anomaly: 异常洞察（异常值或离群点）
- comparison: 对比洞察（不同维度的对比）
- pattern: 模式洞察（数据分布特征、规律）
</values>"""
    )
    
    title: str = Field(
        description="""<what>洞察标题</what>
<when>ALWAYS required</when>
<how>一句话总结洞察内容，包含关键数据</how>

<examples>
- "A店销售额是第2名的5倍"
- "Technology 类别贡献 60% 销售额"
- "过去6个月销售额环比增长15%"
</examples>"""
    )
    
    description: str = Field(
        description="""<what>洞察描述</what>
<when>ALWAYS required</when>
<how>详细解释洞察内容，包含具体数据和业务含义</how>"""
    )
    
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="""<what>重要性评分</what>
<when>ALWAYS required</when>

<decision_rule>
IF anomaly with high business impact → 0.8-1.0
IF key finding answering user question → 0.7-0.9
IF supporting information → 0.5-0.7
IF minor observation → 0.0-0.5
</decision_rule>

<values>
- 0.8-1.0: 高重要性（关键发现）
- 0.5-0.8: 中等重要性
- 0.0-0.5: 低重要性
</values>"""
    )
    
    evidence: Optional[InsightEvidence] = Field(
        default=None,
        description="""<what>支持证据</what>
<when>ALWAYS required for meaningful insights</when>
<how>使用 InsightEvidence 结构提供数据支撑</how>"""
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
    下一口决策 - 主持人 LLM 输出
    
    <what>主持人 LLM 决定下一步分析哪个数据块</what>
    
    <decision_tree>
    START
      │
      ├─► Assess completeness_estimate
      │   │
      │   ├─► >= 0.8 AND core question answered
      │   │   └─► should_continue = False, reason = "充分回答"
      │   │
      │   ├─► >= 0.6 AND remaining chunks low value
      │   │   └─► should_continue = False, reason = "剩余价值低"
      │   │
      │   └─► < 0.6 OR important aspects missing
      │       └─► should_continue = True
      │           │
      │           └─► Select next_chunk_id
      │               ├─ Prefer anomaly chunks (highest priority)
      │               ├─ Then cluster/pareto chunks (high priority)
      │               └─ Then other chunks by estimated_value
      │
    END
    </decision_tree>
    
    <fill_order>
    1. completeness_estimate - 评估当前完成度
    2. should_continue - 基于完成度决定是否继续
    3. next_chunk_id - IF should_continue, 选择下一个块
    4. reason - 解释决策原因
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    should_continue: bool = Field(
        description="""<what>是否继续分析</what>
<when>ALWAYS required</when>

<decision_rule>
IF completeness_estimate >= 0.8 AND core question answered → False
IF completeness_estimate >= 0.6 AND remaining chunks have low value → False
IF important aspects still missing → True
IF anomaly discovered needs investigation → True
</decision_rule>"""
    )
    
    next_chunk_id: Optional[int] = Field(
        default=None,
        description="""<what>下一个要分析的块 ID</what>

<when>IF should_continue is True</when>

<dependency>
- field: should_continue
- condition: should_continue == True
- reason: Only need to select next chunk if continuing
</dependency>

<how>从剩余数据块中选择，优先选择高价值块</how>"""
    )
    
    reason: str = Field(
        default="",
        description="""<what>决策原因</what>
<when>ALWAYS required</when>
<how>解释为什么选择这个块或为什么停止</how>

<examples>
- "核心问题已充分回答，Top 3 门店及其原因已明确"
- "发现异常值，需要分析 anomalies 块深入调查"
- "缺少时间维度分析，选择 segment_0 块"
</examples>"""
    )
    
    completeness_estimate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>完成度估计</what>
<when>ALWAYS required (fill first)</when>
<how>估计当前洞察对问题的回答完成度</how>

<decision_rule>
IF no insights yet → 0.0-0.2
IF basic answer found but no explanation → 0.3-0.5
IF answer with partial explanation → 0.5-0.7
IF comprehensive answer with evidence → 0.7-0.9
IF fully answered with multiple perspectives → 0.9-1.0
</decision_rule>

<values>
- 0.0-0.3: 刚开始，需要更多分析
- 0.3-0.6: 部分回答，还有重要方面未覆盖
- 0.6-0.8: 大部分回答，可以考虑停止
- 0.8-1.0: 充分回答，可以停止
</values>"""
    )


class InsightQuality(BaseModel):
    """
    洞察质量评估
    
    <what>评估当前洞察是否足够回答问题</what>
    
    <fill_order>
    1. question_answered - 核心问题是否已回答
    2. completeness - 回答的完整程度
    3. confidence - 对回答的置信度
    4. need_more_data - 是否需要更多数据
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    completeness: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>完整度（是否充分回答了问题）</what>
<when>ALWAYS required</when>

<values>
- 0.0-0.3: 仅有初步发现
- 0.3-0.6: 部分回答，缺少关键方面
- 0.6-0.8: 大部分回答，细节可补充
- 0.8-1.0: 完整回答
</values>"""
    )
    
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>置信度</what>
<when>ALWAYS required</when>

<values>
- 0.0-0.3: 低置信度（数据不足或矛盾）
- 0.3-0.6: 中等置信度
- 0.6-0.8: 较高置信度
- 0.8-1.0: 高置信度（充分证据支撑）
</values>"""
    )
    
    need_more_data: bool = Field(
        default=True,
        description="""<what>是否需要更多数据</what>
<when>ALWAYS required</when>

<decision_rule>
IF completeness < 0.6 → True
IF confidence < 0.5 → True
IF question_answered == False → True
ELSE → False
</decision_rule>"""
    )
    
    question_answered: bool = Field(
        default=False,
        description="""<what>核心问题是否已回答</what>
<when>ALWAYS required</when>
<how>判断用户的核心问题是否得到直接回答</how>"""
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
    洞察结果 - Insight Agent 最终输出
    
    <what>Insight Agent 输出的分析洞察，包含 Phase 1 和 Phase 2 的结果</what>
    
    <design_note>
    根据 insight-design.md，InsightResult 包含：
    - summary: 一句话总结
    - findings: 洞察列表（分析师 LLM 生成）
    - confidence: 整体置信度
    - data_insight_profile: 数据画像（Phase 1 统计/ML 分析结果）
    - need_more_data: 是否需要更多数据
    - exploration_rounds: 探索轮数
    - questions_executed: 执行的问题数
    </design_note>
    
    <examples>
    Example - Complete result:
    {
        "summary": "A店销售额最高（1000万），主要因为：1) Technology 类别贡献 60% 2) 过去12个月持续增长 3) 领先同城市门店 3 倍",
        "findings": [...],
        "confidence": 0.92,
        "strategy_used": "progressive",
        "chunks_analyzed": 3,
        "total_rows_analyzed": 500,
        "execution_time": 5.2,
        "exploration_rounds": 2,
        "questions_executed": 3
    }
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    # ===== 核心输出字段 =====
    summary: Optional[str] = Field(
        default=None,
        description="""<what>一句话总结</what>
<when>ALWAYS required</when>
<how>综合所有洞察的总结性描述</how>"""
    )
    
    findings: List[Insight] = Field(
        default_factory=list,
        description="""<what>洞察列表</what>
<when>ALWAYS (may be empty)</when>
<how>按重要性降序排列</how>"""
    )
    
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>整体置信度</what>
<when>ALWAYS required</when>
<how>基于洞察的完整度和质量</how>"""
    )
    
    # ===== Phase 1 统计/ML 分析结果 =====
    data_insight_profile: Optional[DataInsightProfile] = Field(
        default=None,
        description="""<what>数据洞察画像</what>
<when>ALWAYS (Phase 1 分析结果)</when>
<how>传递给 Replanner 指导探索问题生成</how>"""
    )
    
    # ===== 分析过程信息 =====
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
    
    # ===== 重规划相关字段 =====
    need_more_data: bool = Field(
        default=False,
        description="""<what>是否需要更多数据</what>
<how>由主持人 LLM 判断</how>"""
    )
    
    missing_aspects: List[str] = Field(
        default_factory=list,
        description="""<what>缺失的方面</what>
<how>用于指导 Replanner 生成探索问题</how>"""
    )
    
    exploration_rounds: int = Field(
        default=1,
        description="""<what>探索轮数</what>
<how>包括初始分析和重规划轮数</how>"""
    )
    
    questions_executed: int = Field(
        default=0,
        description="""<what>执行的问题数</what>
<how>重规划过程中执行的探索问题总数</how>"""
    )
