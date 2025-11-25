# 数据模型设计详解

本文档详细描述 DeepAgents 重构中的所有数据模型定义。

## 目录

1. [State 模型](#1-state-模型) - LangGraph 状态定义
2. [Context 模型](#2-context-模型) - 运行时上下文
3. [Question 模型](#3-question-模型) - 问题相关模型
4. [Query 模型](#4-query-模型) - 查询相关模型
5. [Insight 模型](#5-insight-模型) - 洞察相关模型
6. [Result 模型](#6-result-模型) - 结果相关模型
7. [Cache 模型](#7-cache-模型) - 缓存相关模型
8. [Error 模型](#8-error-模型) - 错误处理模型

---

## 1. State 模型

### DeepAgentState (LangGraph 状态)

```python
from typing import TypedDict, Annotated, List, Dict, Any, Optional
import operator

class DeepAgentState(TypedDict):
    """DeepAgent 主状态定义"""
    
    # === 用户输入 ===
    question: str  # 用户原始问题
    boost_question: bool  # 是否需要问题优化
    
    # === Agent 输出（按执行顺序） ===
    boosted_question: Optional[str]  # 优化后的问题
    understanding: Optional[Dict]  # 问题理解结果
    query_plan: Optional[Dict]  # 查询计划
    query_results: Annotated[List[Dict], operator.add]  # 查询结果（累积）
    insights: Annotated[List[Dict], operator.add]  # 洞察列表（累积）
    replan_decision: Optional[Dict]  # 重规划决策
    final_report: Optional[Dict]  # 最终报告
    
    # === 控制流程 ===
    current_round: int  # 当前轮次
    max_rounds: int  # 最大轮次
    needs_replan: bool  # 是否需要重规划
    
    # === 元数据 ===
    datasource_luid: str  # 数据源 LUID
    thread_id: str  # 会话 ID
    user_id: str  # 用户 ID
    
    # === 性能监控 ===
    start_time: float  # 开始时间
    performance_metrics: Dict[str, Any]  # 性能指标
```

### SubAgentState (子代理状态)

```python
class SubAgentState(TypedDict):
    """子代理状态定义"""
    
    # 输入
    input_data: Dict[str, Any]
    
    # 输出
    output_data: Optional[Dict[str, Any]]
    
    # 状态
    status: str  # pending/running/completed/failed
    error: Optional[str]
    
    # 性能
    start_time: Optional[float]
    end_time: Optional[float]
    token_usage: Optional[Dict[str, int]]
```

---

## 2. Context 模型

### DeepAgentContext (运行时上下文)

```python
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass(frozen=True)  # 不可变
class DeepAgentContext:
    """运行时上下文（不可变配置）"""
    
    # === 必需配置 ===
    datasource_luid: str
    user_id: str
    thread_id: str
    tableau_token: str
    
    # === 可选配置 ===
    max_replan: int = 3
    enable_boost: bool = False
    enable_cache: bool = True
    model_config: Optional[Dict[str, Any]] = None
    
    # === 性能配置 ===
    timeout: int = 300  # 5分钟总超时
    max_tokens_per_call: int = 4000
    temperature: float = 0.0
    
    # === 缓存配置 ===
    cache_ttl: int = 3600  # 1小时
    enable_prompt_cache: bool = True
    enable_query_cache: bool = True
```

### SessionContext (会话上下文)

```python
@dataclass
class SessionContext:
    """会话上下文（可变状态）"""
    
    thread_id: str
    created_at: float
    last_activity: float
    
    # 会话历史
    conversation_history: List[Dict[str, Any]]
    
    # 累积状态
    total_queries: int = 0
    total_tokens: int = 0
    cache_hits: int = 0
    
    # 用户偏好（学习得到）
    preferred_granularity: Optional[str] = None
    preferred_time_range: Optional[str] = None
```

---

## 3. Question 模型

### QuestionUnderstanding (问题理解)

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal

class QuestionUnderstanding(BaseModel):
    """问题理解结果"""
    
    # === 原始问题 ===
    original_question: str = Field(description="用户原始问题")
    
    # === 问题拆分 ===
    sub_questions: List[str] = Field(description="拆分的子问题")
    
    # === 问题分类 ===
    question_type: List[Literal[
        "comparison", "trend", "ranking", "distribution", 
        "correlation", "root_cause", "forecast"
    ]] = Field(description="问题类型")
    
    complexity: Literal["simple", "medium", "complex"] = Field(
        description="复杂度评估"
    )
    
    # === 实体提取 ===
    mentioned_dimensions: List[str] = Field(description="提到的维度")
    mentioned_measures: List[str] = Field(description="提到的度量")
    mentioned_date_fields: List[str] = Field(description="提到的日期字段")
    
    # === 分析需求 ===
    time_range: Optional[Dict[str, Any]] = Field(description="时间范围")
    filters: List[Dict[str, Any]] = Field(default_factory=list, description="过滤条件")
    sort_requirement: Optional[str] = Field(description="排序需求")
    topn_requirement: Optional[int] = Field(description="TopN需求")
    aggregation_intent: Optional[str] = Field(description="聚合意图")
    
    # === 隐含需求 ===
    implicit_requirements: List[str] = Field(
        default_factory=list, description="隐含需求"
    )
    
    # === 质量评估 ===
    confidence: float = Field(ge=0.0, le=1.0, description="理解置信度")
    reasoning: str = Field(description="推理过程")
```

### QuestionBoost (问题优化)

```python
class QuestionBoost(BaseModel):
    """问题优化结果"""
    
    original_question: str = Field(description="原始问题")
    boosted_question: str = Field(description="优化后的问题")
    
    improvements: List[str] = Field(description="改进点列表")
    suggestions: List[str] = Field(description="相关问题建议")
    
    confidence: float = Field(ge=0.0, le=1.0, description="优化置信度")
    reasoning: str = Field(description="优化推理过程")
```

---

## 4. Query 模型

### QueryPlan (查询计划)

```python
class QueryPlan(BaseModel):
    """查询计划"""
    
    plan_id: str = Field(description="计划ID")
    round_number: int = Field(description="轮次编号")
    
    queries: List['QuerySpec'] = Field(description="查询列表")
    
    execution_strategy: Literal[
        "sequential", "parallel", "pipeline", "adaptive"
    ] = Field(description="执行策略")
    
    dependencies: Dict[str, List[str]] = Field(
        default_factory=dict, description="依赖关系"
    )
    
    estimated_time: float = Field(description="预估执行时间（秒）")
    reasoning: str = Field(description="规划推理过程")

class QuerySpec(BaseModel):
    """单个查询规格"""
    
    query_id: str = Field(description="查询ID")
    question_text: str = Field(description="对应的问题文本")
    
    # === VizQL 查询结构 ===
    fields: List[Dict[str, Any]] = Field(description="字段列表")
    filters: List[Dict[str, Any]] = Field(default_factory=list, description="筛选条件")
    sort: Optional[Dict[str, Any]] = Field(description="排序规则")
    limit: Optional[int] = Field(description="结果限制")
    
    # === 执行控制 ===
    dependencies: List[str] = Field(default_factory=list, description="依赖的查询ID")
    priority: int = Field(default=0, description="优先级")
    
    # === 缓存 ===
    cache_key: Optional[str] = Field(description="缓存键")
    cache_ttl: Optional[int] = Field(description="缓存有效期")
    
    # === 元数据 ===
    reasoning: str = Field(description="查询推理过程")
```

### QueryResult (查询结果)

```python
class QueryResult(BaseModel):
    """查询结果"""
    
    query_id: str = Field(description="查询ID")
    
    # === 数据 ===
    data: List[Dict[str, Any]] = Field(description="数据行")
    schema: Dict[str, Any] = Field(description="字段schema")
    row_count: int = Field(description="行数")
    
    # === 文件存储（大数据） ===
    file_path: Optional[str] = Field(description="文件路径（如果数据过大）")
    
    # === 执行信息 ===
    execution_time: float = Field(description="执行时间（秒）")
    cache_hit: bool = Field(description="是否缓存命中")
    
    # === 统计信息 ===
    statistics: Optional[Dict[str, Any]] = Field(description="统计信息")
```

---

## 5. Insight 模型

### Insight (单个洞察)

```python
class Insight(BaseModel):
    """单个洞察"""
    
    insight_id: str = Field(description="洞察ID")
    
    # === 洞察内容 ===
    type: Literal[
        "trend", "anomaly", "pattern", "correlation", 
        "comparison", "distribution", "forecast"
    ] = Field(description="洞察类型")
    
    description: str = Field(description="洞察描述")
    evidence: List[str] = Field(description="支持证据")
    
    # === 质量评估 ===
    confidence: float = Field(ge=0.0, le=1.0, description="置信度")
    importance: Literal["high", "medium", "low"] = Field(description="重要性")
    novelty: float = Field(ge=0.0, le=1.0, description="新颖性")
    
    # === 关联信息 ===
    related_queries: List[str] = Field(description="相关查询ID")
    related_data: Dict[str, Any] = Field(description="相关数据")
    
    # === 可视化建议 ===
    visualization_suggestion: Optional['VisualizationSuggestion'] = Field(
        description="可视化建议"
    )
```

### InsightCollection (洞察集合)

```python
class InsightCollection(BaseModel):
    """洞察集合"""
    
    round_number: int = Field(description="轮次编号")
    
    # === 洞察列表 ===
    insights: List[Insight] = Field(description="洞察列表")
    
    # === 汇总信息 ===
    key_findings: List[str] = Field(description="关键发现")
    summary: str = Field(description="洞察摘要")
    
    # === 贡献分析 ===
    contribution_analysis: List['ContributionItem'] = Field(
        description="贡献分析"
    )
    
    # === 建议 ===
    recommendations: List[str] = Field(description="建议")
    
    # === 质量评估 ===
    overall_confidence: float = Field(ge=0.0, le=1.0, description="整体置信度")
    completeness_score: float = Field(ge=0.0, le=1.0, description="完整性评分")
```

### ContributionItem (贡献项)

```python
class ContributionItem(BaseModel):
    """贡献分析项"""
    
    dimension: str = Field(description="维度名称")
    dimension_value: str = Field(description="维度值")
    contribution_percentage: float = Field(description="贡献百分比")
    rank: int = Field(description="排名")
    
    # === 详细信息 ===
    absolute_value: Optional[float] = Field(description="绝对值")
    comparison_to_average: Optional[float] = Field(description="与平均值的比较")
```

### VisualizationSuggestion (可视化建议)

```python
class VisualizationSuggestion(BaseModel):
    """可视化建议"""
    
    type: Literal[
        "bar", "line", "pie", "scatter", "heatmap", 
        "table", "treemap", "waterfall"
    ] = Field(description="图表类型")
    
    title: str = Field(description="图表标题")
    
    # === 轴配置 ===
    x_axis: Optional[str] = Field(description="X轴字段")
    y_axis: Optional[str] = Field(description="Y轴字段")
    color: Optional[str] = Field(description="颜色字段")
    size: Optional[str] = Field(description="大小字段")
    
    # === 推荐理由 ===
    reasoning: str = Field(description="推荐理由")
    suitability_score: float = Field(ge=0.0, le=1.0, description="适用性评分")
```

---

## 6. Result 模型

### FinalReport (最终报告)

```python
class FinalReport(BaseModel):
    """最终分析报告"""
    
    # === 基本信息 ===
    report_id: str = Field(description="报告ID")
    thread_id: str = Field(description="会话ID")
    original_question: str = Field(description="原始问题")
    
    # === 执行摘要 ===
    executive_summary: str = Field(description="执行摘要")
    
    # === 主要内容 ===
    key_findings: List[str] = Field(description="关键发现")
    insights: List[Insight] = Field(description="所有洞察")
    recommendations: List[str] = Field(description="建议")
    
    # === 分析路径 ===
    analysis_rounds: List['AnalysisRound'] = Field(description="分析轮次")
    
    # === 性能指标 ===
    performance_metrics: 'PerformanceMetrics' = Field(description="性能指标")
    
    # === 元数据 ===
    created_at: float = Field(description="创建时间")
    total_analysis_time: float = Field(description="总分析时间")
```

### AnalysisRound (分析轮次)

```python
class AnalysisRound(BaseModel):
    """单轮分析记录"""
    
    round_number: int = Field(description="轮次编号")
    question: str = Field(description="本轮问题")
    
    # === 执行过程 ===
    query_plan: QueryPlan = Field(description="查询计划")
    query_results: List[QueryResult] = Field(description="查询结果")
    insights: InsightCollection = Field(description="洞察集合")
    
    # === 重规划决策 ===
    replan_decision: Optional['ReplanDecision'] = Field(description="重规划决策")
    
    # === 性能 ===
    execution_time: float = Field(description="执行时间")
    token_usage: Dict[str, int] = Field(description="Token使用量")
```

### ReplanDecision (重规划决策)

```python
class ReplanDecision(BaseModel):
    """重规划决策"""
    
    should_replan: bool = Field(description="是否应该重规划")
    reason: str = Field(description="决策理由")
    
    # === 新问题 ===
    new_questions: List[str] = Field(description="新问题列表")
    focus_areas: List[str] = Field(description="关注领域")
    expected_insights: List[str] = Field(description="期望洞察")
    
    # === 评估 ===
    confidence: float = Field(ge=0.0, le=1.0, description="决策置信度")
    completeness_score: float = Field(ge=0.0, le=1.0, description="当前完整性")
    max_rounds_reached: bool = Field(description="是否达到最大轮次")
```

---

## 7. Cache 模型

### CacheEntry (缓存条目)

```python
class CacheEntry(BaseModel):
    """缓存条目"""
    
    key: str = Field(description="缓存键")
    value: Any = Field(description="缓存值")
    
    # === 时间信息 ===
    created_at: float = Field(description="创建时间")
    expires_at: Optional[float] = Field(description="过期时间")
    last_accessed: float = Field(description="最后访问时间")
    
    # === 元数据 ===
    cache_type: Literal[
        "llm_response", "query_result", "metadata", "semantic_mapping"
    ] = Field(description="缓存类型")
    
    size_bytes: int = Field(description="大小（字节）")
    hit_count: int = Field(default=0, description="命中次数")
```

### CacheStats (缓存统计)

```python
class CacheStats(BaseModel):
    """缓存统计信息"""
    
    # === 命中率 ===
    total_requests: int = Field(description="总请求数")
    cache_hits: int = Field(description="缓存命中数")
    cache_misses: int = Field(description="缓存未命中数")
    hit_rate: float = Field(description="命中率")
    
    # === 存储信息 ===
    total_entries: int = Field(description="总条目数")
    total_size_bytes: int = Field(description="总大小")
    
    # === 性能 ===
    avg_hit_time_ms: float = Field(description="平均命中时间")
    avg_miss_time_ms: float = Field(description="平均未命中时间")
```

---

## 8. Error 模型

### DeepAgentError (错误信息)

```python
class DeepAgentError(BaseModel):
    """DeepAgent 错误信息"""
    
    error_id: str = Field(description="错误ID")
    error_type: Literal[
        "validation_error", "authentication_error", "api_error", 
        "timeout_error", "llm_error", "query_error", "system_error"
    ] = Field(description="错误类型")
    
    message: str = Field(description="错误消息")
    details: Optional[Dict[str, Any]] = Field(description="错误详情")
    
    # === 上下文 ===
    thread_id: Optional[str] = Field(description="会话ID")
    agent_name: Optional[str] = Field(description="出错的Agent")
    tool_name: Optional[str] = Field(description="出错的工具")
    
    # === 时间 ===
    timestamp: float = Field(description="错误时间")
    
    # === 恢复信息 ===
    is_retryable: bool = Field(description="是否可重试")
    retry_count: int = Field(default=0, description="重试次数")
    recovery_suggestion: Optional[str] = Field(description="恢复建议")
```

### PerformanceMetrics (性能指标)

```python
class PerformanceMetrics(BaseModel):
    """性能指标"""
    
    # === 时间指标 ===
    total_time: float = Field(description="总时间（秒）")
    first_insight_time: float = Field(description="首次洞察时间（秒）")
    
    # === Token 使用 ===
    total_tokens: int = Field(description="总Token数")
    input_tokens: int = Field(description="输入Token数")
    output_tokens: int = Field(description="输出Token数")
    
    # === 缓存效果 ===
    cache_hit_rate: float = Field(description="缓存命中率")
    tokens_saved: int = Field(description="节省的Token数")
    cost_saved: float = Field(description="节省的成本")
    
    # === 查询统计 ===
    total_queries: int = Field(description="总查询数")
    parallel_queries: int = Field(description="并行查询数")
    cached_queries: int = Field(description="缓存命中查询数")
    
    # === 质量指标 ===
    insight_count: int = Field(description="洞察数量")
    high_confidence_insights: int = Field(description="高置信度洞察数")
    replan_count: int = Field(description="重规划次数")
```

---

## 模型关系图

```
DeepAgentState (主状态)
├── QuestionUnderstanding (问题理解)
├── QueryPlan (查询计划)
│   └── QuerySpec[] (查询规格)
├── QueryResult[] (查询结果)
├── InsightCollection[] (洞察集合)
│   └── Insight[] (单个洞察)
│       └── VisualizationSuggestion (可视化建议)
├── ReplanDecision (重规划决策)
└── FinalReport (最终报告)
    ├── AnalysisRound[] (分析轮次)
    └── PerformanceMetrics (性能指标)

DeepAgentContext (运行时上下文)
├── SessionContext (会话上下文)
└── CacheStats (缓存统计)

CacheEntry[] (缓存条目)
DeepAgentError[] (错误信息)
```

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15
