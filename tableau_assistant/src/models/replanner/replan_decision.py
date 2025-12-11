"""
Replanning Decision Models

支持多问题并行执行的重规划决策模型（类 Tableau Pulse）。

Design Specification: insight-design.md
- 多问题生成：Replanner 生成多个探索问题
- 并行执行：按优先级并行执行多个问题
- 探索类型：drill_down, roll_up, time_series, peer_comparison 等
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class ExplorationQuestion(BaseModel):
    """
    探索问题 - 由 Replanner LLM 直接生成
    
    <what>单个探索问题，用于深入分析</what>
    
    <design_note>
    问题文本由 LLM 生成，不使用模板！
    exploration_type 仅用于分类和优先级排序。
    </design_note>
    
    <examples>
    Example 1 - Drill down:
    {
        "question": "A店各产品类别的销售额分布？",
        "exploration_type": "drill_down",
        "target_dimension": "产品类别",
        "priority": 1,
        "reasoning": "按产品维度展开，找出主要贡献类别"
    }
    
    Example 2 - Time series:
    {
        "question": "A店过去12个月的销售趋势？",
        "exploration_type": "time_series",
        "target_dimension": "月份",
        "priority": 2,
        "reasoning": "按时间维度展开，了解增长趋势"
    }
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    question: str = Field(
        description="""<what>探索问题文本（由 LLM 生成）</what>
<when>ALWAYS required</when>
<how>LLM 直接生成，不使用模板！</how>

<examples>
- "A店各产品类别的销售额分布？"
- "A店过去12个月的销售趋势？"
- "A店与同城市其他门店的对比？"
</examples>"""
    )
    
    exploration_type: Literal[
        "drill_down",           # 向下钻取（大类→小类）
        "roll_up",              # 向上汇总（小类→大类）
        "time_series",          # 时间序列分析
        "peer_comparison",      # 同级对比
        "cross_dimension",      # 跨维度分析
        "anomaly_investigation",# 异常调查
        "correlation_analysis"  # 相关性分析
    ] = Field(
        description="""<what>探索类型</what>
<when>ALWAYS required</when>

<values>
- drill_down: 向下钻取（大类→小类）
- roll_up: 向上汇总（小类→大类）
- time_series: 时间序列分析
- peer_comparison: 同级对比
- cross_dimension: 跨维度分析
- anomaly_investigation: 异常调查
- correlation_analysis: 相关性分析
</values>

<decision_rule>
- 需要更细粒度 → drill_down
- 需要更粗粒度 → roll_up
- 需要时间趋势 → time_series
- 需要横向对比 → peer_comparison
- 需要跨维度关联 → cross_dimension
- 发现异常需要调查 → anomaly_investigation
- 需要分析相关性 → correlation_analysis
</decision_rule>"""
    )
    
    target_dimension: str = Field(
        description="""<what>目标维度</what>
<when>ALWAYS required</when>
<how>从 dimension_hierarchy 中选择</how>

<examples>
- "产品类别"
- "月份"
- "门店"
- "地区"
</examples>"""
    )
    
    filter: Optional[str] = Field(
        default=None,
        description="""<what>过滤条件</what>
<when>IF need to filter data</when>

<examples>
- "城市 = 'A店所在城市'"
- "时间 >= '2024-01'"
</examples>"""
    )
    
    priority: int = Field(
        ge=1,
        le=10,
        description="""<what>优先级（1 最高，10 最低）</what>
<when>ALWAYS required</when>

<decision_rule>
- 直接回答用户问题 → 1
- 补充关键信息 → 2-3
- 深入分析 → 4-6
- 边缘探索 → 7-10
</decision_rule>"""
    )
    
    reasoning: str = Field(
        description="""<what>LLM 的推理说明</what>
<when>ALWAYS required</when>
<how>解释为什么生成这个问题</how>

<examples>
- "按产品维度展开，找出主要贡献类别"
- "按时间维度展开，了解增长趋势"
- "横向对比，了解是否是区域优势"
</examples>"""
    )


class ReplanDecision(BaseModel):
    """
    重规划决策 - 支持多问题并行执行
    
    <what>Replanner Agent 输出的决策结果</what>
    
    <design_note>
    类似 Tableau Pulse：一次生成多个探索问题，并行执行。
    - 多问题生成：LLM 直接生成问题，不使用模板
    - 并行执行：按优先级并行执行多个问题
    - 智能停止：基于 completeness_score 决定是否继续
    </design_note>
    
    <fill_order>
    ┌────┬─────────────────────────┬─────────────────────────────────────┐
    │ #  │ Field                   │ Condition                           │
    ├────┼─────────────────────────┼─────────────────────────────────────┤
    │ 1  │ completeness_score      │ ALWAYS                              │
    │ 2  │ should_replan           │ ALWAYS (based on completeness_score)│
    │ 3  │ reason                  │ ALWAYS                              │
    │ 4  │ missing_aspects         │ IF should_replan = true             │
    │ 5  │ exploration_questions   │ IF should_replan = true             │
    │ 6  │ confidence              │ ALWAYS (default: 0.8)               │
    └────┴─────────────────────────┴─────────────────────────────────────┘
    </fill_order>
    
    <examples>
    Example - Need replan:
    {
        "completeness_score": 0.5,
        "should_replan": true,
        "reason": "已回答'谁最高'，但'为什么'需要更多维度分析",
        "missing_aspects": ["产品维度分析", "时间趋势分析", "区域对比"],
        "exploration_questions": [
            {"question": "A店各产品类别销售额？", "exploration_type": "drill_down", ...},
            {"question": "A店过去12个月趋势？", "exploration_type": "time_series", ...}
        ],
        "parallel_execution": true,
        "max_questions_per_round": 3
    }
    
    Example - Complete:
    {
        "completeness_score": 0.92,
        "should_replan": false,
        "reason": "已从产品、时间、地理三个维度回答了'为什么'",
        "missing_aspects": [],
        "exploration_questions": []
    }
    </examples>
    """
    model_config = ConfigDict(extra="forbid")
    
    completeness_score: float = Field(
        ge=0.0,
        le=1.0,
        description="""<what>分析完整度评分（0-1）</what>
<when>ALWAYS required</when>

<decision_rule>
评分标准：
- 0.9-1.0: 完全回答问题，洞察深入 → should_replan = false
- 0.7-0.9: 基本回答问题，可以更深入 → 考虑重规划
- 0.5-0.7: 部分回答问题，缺少关键信息 → should_replan = true
- <0.5: 未能回答问题 → should_replan = true
</decision_rule>"""
    )
    
    should_replan: bool = Field(
        description="""<what>是否需要重规划</what>
<when>ALWAYS required</when>

<decision_rule>
- completeness_score >= 0.9 → false
- completeness_score < 0.9 AND missing_aspects exist → true
- replan_count >= max_replan_rounds → false (强制结束)
</decision_rule>"""
    )
    
    reason: str = Field(
        description="""<what>评估理由</what>
<when>ALWAYS required</when>"""
    )
    
    missing_aspects: List[str] = Field(
        default_factory=list,
        description="""<what>缺失的分析方面</what>
<when>IF should_replan = true</when>

<examples>
- ["产品维度分析", "时间趋势分析", "区域对比"]
</examples>"""
    )
    
    # 新增：多问题支持
    exploration_questions: List[ExplorationQuestion] = Field(
        default_factory=list,
        description="""<what>探索问题列表（由 LLM 生成）</what>
<when>IF should_replan = true</when>

<design_note>
问题由 LLM 直接生成，不使用模板！
按 priority 排序，优先执行高优先级问题。
</design_note>"""
    )
    
    # 执行策略
    parallel_execution: bool = Field(
        default=True,
        description="""<what>是否并行执行多个问题</what>
<when>ALWAYS (default: true)</when>"""
    )
    
    max_questions_per_round: int = Field(
        default=3,
        ge=1,
        le=5,
        description="""<what>每轮最多执行几个问题</what>
<when>ALWAYS (default: 3)</when>"""
    )
    
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="""<what>决策置信度</what>
<when>ALWAYS (default: 0.8)</when>"""
    )
    
    def get_top_questions(self, n: int = 3) -> List[ExplorationQuestion]:
        """获取优先级最高的 N 个问题"""
        sorted_questions = sorted(self.exploration_questions, key=lambda q: q.priority)
        return sorted_questions[:n]
    
    def get_questions_by_type(self, exploration_type: str) -> List[ExplorationQuestion]:
        """按探索类型筛选问题"""
        return [q for q in self.exploration_questions if q.exploration_type == exploration_type]
