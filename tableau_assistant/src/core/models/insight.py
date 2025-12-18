# -*- coding: utf-8 -*-
"""
Insight Models

洞察分析相关的数据模型。

包含:
- ChunkPriority: 数据块优先级
- ColumnStats: 列统计信息
- SemanticGroup: 语义分组
- DataProfile: 数据画像
- AnomalyDetail/AnomalyResult: 异常检测结果
- DataChunk/PriorityChunk: 数据块
- TailDataSummary: 尾部数据摘要
- InsightEvidence/Insight: 洞察及证据
- InsightQuality: 洞察质量评估
- NextBiteDecision: 下一步分析决策
- ClusterInfo: 聚类信息
- DataInsightProfile: 数据洞察画像
- InsightResult: 洞察结果
"""
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Dict, List, Any, Optional, Literal, Union
from datetime import datetime
from enum import IntEnum


class ChunkPriority(IntEnum):
    """数据块优先级，数值越小优先级越高"""
    URGENT = 1    # 异常值，最优先
    HIGH = 2      # Top 100 行
    MEDIUM = 3    # 101-500 行
    LOW = 4       # 501-1000 行
    DEFERRED = 5  # 1000+ 行（尾部数据）


class ColumnStats(BaseModel):
    """单个数值列的统计信息"""
    model_config = ConfigDict(extra="forbid")
    
    mean: float = Field(description="平均值")
    median: float = Field(description="中位数")
    std: float = Field(description="标准差")
    min: float = Field(description="最小值")
    max: float = Field(description="最大值")
    q25: float = Field(description="25% 分位数")
    q75: float = Field(description="75% 分位数")


class SemanticGroup(BaseModel):
    """具有相同语义类型的列分组"""
    model_config = ConfigDict(extra="forbid")
    
    type: Literal["time", "category", "numeric", "geographic"] = Field(
        description="语义类型: time/geographic/category/numeric"
    )
    columns: List[str] = Field(description="属于该语义组的列名列表")


class DataProfile(BaseModel):
    """数据集画像，包含统计信息和语义分组"""
    model_config = ConfigDict(extra="forbid")
    
    row_count: int = Field(description="数据行数")
    column_count: int = Field(description="数据列数")
    density: float = Field(ge=0.0, le=1.0, description="数据密度（非空比例）")
    statistics: Dict[str, ColumnStats] = Field(default_factory=dict, description="每个数值列的统计信息")
    semantic_groups: List[SemanticGroup] = Field(default_factory=list, description="语义分组列表")


class AnomalyDetail(BaseModel):
    """单个异常的详细信息"""
    model_config = ConfigDict(extra="forbid")
    
    index: int = Field(description="异常行索引")
    values: Dict[str, Any] = Field(description="异常行的值")
    reason: str = Field(description="异常原因")
    column: Optional[str] = Field(default=None, description="异常所在列")
    severity: float = Field(default=0.0, ge=0.0, le=1.0, description="严重程度 (0-1)")


class AnomalyResult(BaseModel):
    """异常检测结果"""
    model_config = ConfigDict(extra="forbid")
    
    outliers: List[int] = Field(default_factory=list, description="异常行索引列表")
    anomaly_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="异常比例")
    anomaly_details: List[AnomalyDetail] = Field(default_factory=list, description="异常详情列表")


class DataChunk(BaseModel):
    """用于渐进式分析的数据块"""
    model_config = ConfigDict(extra="forbid")
    
    data: List[Dict[str, Any]] = Field(description="数据记录列表")
    chunk_id: int = Field(description="块 ID")
    chunk_name: str = Field(description="块名称")
    row_count: int = Field(description="行数")
    column_names: List[str] = Field(description="列名列表")
    group_key: Optional[str] = Field(default=None, description="分组键")
    group_value: Optional[Union[str, int, float, bool]] = Field(default=None, description="分组值")


class TailDataSummary(BaseModel):
    """尾部数据摘要（1000+ 行）"""
    model_config = ConfigDict(extra="forbid")
    
    total_rows: int = Field(description="尾部数据总行数")
    sample_data: List[Dict[str, Any]] = Field(default_factory=list, description="采样数据（最多 100 行）")
    statistics: Dict[str, Any] = Field(default_factory=dict, description="统计信息")
    anomaly_count: int = Field(default=0, description="尾部数据中的异常值数量")
    patterns: Dict[str, Any] = Field(default_factory=dict, description="检测到的模式")


class PriorityChunk(BaseModel):
    """带优先级的数据块"""
    model_config = ConfigDict(extra="forbid")
    
    chunk_id: int = Field(description="块 ID")
    chunk_type: str = Field(description="块类型: anomalies/top_data/mid_data/low_data/tail_data/cluster_N/segment_N 等")
    priority: int = Field(description="优先级（1-5，越小越优先）")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="数据记录列表")
    tail_summary: Optional[TailDataSummary] = Field(default=None, description="尾部数据摘要（仅 tail_data 类型）")
    row_count: int = Field(description="行数")
    column_names: List[str] = Field(default_factory=list, description="列名列表")
    description: str = Field(default="", description="块描述")
    estimated_value: str = Field(default="unknown", description="估算价值: high/medium/low/potential/unknown")


class InsightEvidence(BaseModel):
    """洞察证据 - 支持洞察的具体数据"""
    model_config = ConfigDict(extra="forbid")
    
    metric_name: Optional[str] = Field(default=None, description="指标名称")
    metric_value: Optional[float] = Field(default=None, description="指标值")
    comparison_value: Optional[float] = Field(default=None, description="对比值")
    ratio: Optional[float] = Field(default=None, description="比率")
    percentage: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="百分比")
    period: Optional[str] = Field(default=None, description="时间周期")
    additional_data: Optional[Dict[str, Union[str, int, float, bool]]] = Field(default=None, description="其他补充数据")


class Insight(BaseModel):
    """单个洞察 - 分析师 LLM 输出
    
    <what>单个数据洞察，包含类型、标题、描述和证据</what>
    
    <fill_order>
    1. type (ALWAYS)
    2. title (ALWAYS)
    3. description (ALWAYS)
    4. importance (ALWAYS)
    5. evidence (recommended)
    </fill_order>
    
    <examples>
    趋势: {"type": "trend", "title": "销售额持续增长", "description": "近6个月销售额环比增长15%", "importance": 0.9}
    异常: {"type": "anomaly", "title": "A店销售额异常高", "description": "A店销售额是第二名的5倍", "importance": 0.95}
    </examples>
    
    <anti_patterns>
    ❌ 无具体数据支撑: "销售额很高"（应包含具体数值）
    ❌ 重复已有洞察
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    type: Literal["trend", "anomaly", "comparison", "pattern"] = Field(
        description="""<what>洞察类型</what>
<when>ALWAYS required</when>
<rule>
- trend: 时间变化趋势
- anomaly: 异常值/意外发现
- comparison: 对比分析
- pattern: 分布/规律
</rule>"""
    )
    title: str = Field(
        description="""<what>洞察标题</what>
<when>ALWAYS required</when>
<rule>一句话总结，包含关键数据</rule>"""
    )
    description: str = Field(
        description="""<what>洞察描述</what>
<when>ALWAYS required</when>
<rule>详细解释，必须引用具体数据</rule>
<must_not>无数据支撑的泛泛描述</must_not>"""
    )
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="""<what>重要性评分</what>
<when>ALWAYS required</when>
<rule>0.9-1.0=关键发现, 0.7-0.9=重要, 0.5-0.7=一般, <0.5=次要</rule>"""
    )
    evidence: Optional[InsightEvidence] = Field(
        default=None,
        description="""<what>支持证据</what>
<when>推荐填写</when>
<rule>包含具体指标值、对比值、比率等</rule>"""
    )


class InsightQuality(BaseModel):
    """洞察质量评估 - 主持人 LLM 输出
    
    <what>当前洞察的质量评估</what>
    
    <fill_order>
    1. completeness (ALWAYS)
    2. confidence (ALWAYS)
    3. question_answered (ALWAYS)
    4. need_more_data (ALWAYS)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    completeness: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>完整度</what>
<when>ALWAYS required</when>
<rule>>=0.8 基本完整, 0.5-0.8 部分完整, <0.5 不完整</rule>"""
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>置信度</what>
<when>ALWAYS required</when>
<rule>基于数据质量和分析深度</rule>"""
    )
    need_more_data: bool = Field(
        default=True,
        description="""<what>是否需要更多数据</what>
<when>ALWAYS required</when>
<rule>completeness < 0.8 → true</rule>"""
    )
    question_answered: bool = Field(
        default=False,
        description="""<what>核心问题是否已回答</what>
<when>ALWAYS required</when>
<rule>洞察是否直接回答了用户问题</rule>"""
    )


class NextBiteDecision(BaseModel):
    """下一口决策 - 主持人 LLM 输出
    
    <what>主持人决定是否继续分析以及分析哪个数据块</what>
    
    <fill_order>
    1. should_continue (ALWAYS)
    2. completeness_estimate (ALWAYS)
    3. reason (ALWAYS)
    4. next_chunk_id (if should_continue=True)
    </fill_order>
    
    <examples>
    继续: {"should_continue": true, "next_chunk_id": 3, "reason": "异常数据块需要调查", "completeness_estimate": 0.6}
    停止: {"should_continue": false, "next_chunk_id": null, "reason": "核心问题已回答", "completeness_estimate": 0.9}
    </examples>
    
    <anti_patterns>
    ❌ should_continue=true 但 next_chunk_id=null
    ❌ completeness_estimate >= 0.9 但 should_continue=true
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    should_continue: bool = Field(
        description="""<what>是否继续分析</what>
<when>ALWAYS required</when>
<rule>completeness < 0.8 且有高价值块 → true</rule>"""
    )
    next_chunk_id: Optional[int] = Field(
        default=None,
        description="""<what>下一个要分析的块 ID</what>
<when>should_continue=True 时必填</when>
<dependency>should_continue == True</dependency>"""
    )
    reason: str = Field(
        default="",
        description="""<what>决策原因</what>
<when>ALWAYS required</when>
<rule>解释为什么继续/停止</rule>"""
    )
    completeness_estimate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>完成度估计</what>
<when>ALWAYS required</when>
<rule>>=0.8 基本完成, 0.5-0.8 部分完成, <0.5 刚开始</rule>"""
    )


class ClusterInfo(BaseModel):
    """聚类信息"""
    model_config = ConfigDict(extra="forbid")
    
    cluster_id: int = Field(description="聚类 ID")
    center: Dict[str, float] = Field(default_factory=dict, description="聚类中心")
    size: int = Field(description="聚类大小（行数）")
    label: str = Field(default="", description="聚类标签: 高绩效/中等/低绩效/异常")
    indices: List[int] = Field(default_factory=list, description="属于该聚类的行索引")


class DataInsightProfile(BaseModel):
    """数据洞察画像 - Phase 1 统计/ML 分析结果"""
    model_config = ConfigDict(extra="forbid")
    
    # 分布分析
    distribution_type: Literal["normal", "long_tail", "bimodal", "uniform", "unknown"] = Field(
        default="unknown", description="分布类型"
    )
    skewness: float = Field(default=0.0, description="偏度")
    kurtosis: float = Field(default=0.0, description="峰度")
    
    # 帕累托分析
    pareto_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="帕累托比率（top 20% 贡献的比例）")
    pareto_threshold: float = Field(default=0.0, ge=0.0, le=1.0, description="帕累托阈值（贡献 80% 的数据占比）")
    
    # 异常检测
    anomaly_indices: List[int] = Field(default_factory=list, description="异常值行索引")
    anomaly_ratio: float = Field(default=0.0, ge=0.0, le=1.0, description="异常比例")
    anomaly_method: str = Field(default="IQR", description="异常检测方法: IQR/Z-Score/Isolation Forest")
    
    # 聚类分析
    clusters: List[ClusterInfo] = Field(default_factory=list, description="聚类结果")
    optimal_k: int = Field(default=0, description="最优聚类数")
    clustering_method: str = Field(default="KMeans", description="聚类方法")
    
    # 趋势检测（可选）
    trend: Optional[Literal["increasing", "decreasing", "stable"]] = Field(default=None, description="趋势方向")
    trend_slope: Optional[float] = Field(default=None, description="趋势斜率")
    change_points: Optional[List[int]] = Field(default=None, description="变点索引")
    
    # 相关性分析
    correlations: Dict[str, float] = Field(default_factory=dict, description="列间相关性")
    
    # 统计信息
    statistics: Dict[str, ColumnStats] = Field(default_factory=dict, description="各数值列的统计信息")
    
    # 推荐的分块策略
    recommended_chunking_strategy: Literal[
        "by_cluster", "by_change_point", "by_pareto", "by_semantic", "by_statistics", "by_position"
    ] = Field(default="by_position", description="推荐的分块策略")
    
    # 主度量列
    primary_measure: Optional[str] = Field(default=None, description="主度量列名")
    
    # Top N 数据摘要
    top_n_summary: List[Dict[str, Any]] = Field(default_factory=list, description="Top N 数据摘要")


class InsightResult(BaseModel):
    """洞察结果 - Insight Agent 最终输出"""
    model_config = ConfigDict(extra="forbid")
    
    # 核心输出字段
    summary: Optional[str] = Field(default=None, description="一句话总结")
    findings: List[Insight] = Field(default_factory=list, description="洞察列表")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="整体置信度")
    
    # Phase 1 统计/ML 分析结果
    data_insight_profile: Optional[DataInsightProfile] = Field(default=None, description="数据洞察画像")
    
    # 分析过程信息
    strategy_used: str = Field(default="direct", description="使用的分析策略: direct/progressive/hybrid")
    chunks_analyzed: int = Field(default=0, description="分析的块数")
    total_rows_analyzed: int = Field(default=0, description="分析的总行数")
    execution_time: float = Field(default=0.0, description="执行时间（秒）")
    
    # 重规划相关字段
    need_more_data: bool = Field(default=False, description="是否需要更多数据")
    missing_aspects: List[str] = Field(default_factory=list, description="缺失的方面")
    exploration_rounds: int = Field(default=1, description="探索轮数")
    questions_executed: int = Field(default=0, description="执行的问题数")


__all__ = [
    # Priority and Stats
    "ChunkPriority",
    "ColumnStats",
    "SemanticGroup",
    "DataProfile",
    # Anomaly
    "AnomalyDetail",
    "AnomalyResult",
    # Chunks
    "DataChunk",
    "PriorityChunk",
    "TailDataSummary",
    # Insights
    "InsightEvidence",
    "Insight",
    "InsightQuality",
    "InsightResult",
    # Decisions
    "NextBiteDecision",
    # Analysis Profile
    "ClusterInfo",
    "DataInsightProfile",
]
