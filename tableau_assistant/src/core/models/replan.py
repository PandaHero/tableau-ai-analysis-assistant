# -*- coding: utf-8 -*-
"""
Replan Models

重规划相关的数据模型。

包含:
- ExplorationQuestion: 探索问题
- ReplanDecision: 重规划决策
"""
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class ExplorationQuestion(BaseModel):
    """探索问题 - 由 Replanner LLM 直接生成
    
    <what>单个探索问题，包含问题文本、类型、目标维度和优先级</what>
    
    <fill_order>
    1. question (ALWAYS)
    2. exploration_type (ALWAYS)
    3. target_dimension (ALWAYS)
    4. priority (ALWAYS)
    5. reasoning (ALWAYS)
    6. filter (optional)
    </fill_order>
    
    <examples>
    drill_down: {"question": "A店在各产品类别的销售额分布如何？", "exploration_type": "drill_down", "target_dimension": "产品类别", "priority": 2}
    time_series: {"question": "A店近12个月的销售额趋势如何？", "exploration_type": "time_series", "target_dimension": "月份", "priority": 1}
    </examples>
    
    <anti_patterns>
    ❌ 使用模板占位符: {"question": "{entity}的销售额"}
    ❌ 重复已回答的问题
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    question: str = Field(
        description="""<what>探索问题文本（由 LLM 生成）</what>
<when>ALWAYS required</when>
<rule>使用具体实体名称，不使用模板占位符</rule>
<must_not>使用 {entity} 等占位符</must_not>"""
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
<rule>
- drill_down: 需要更细粒度 → 向下钻取
- roll_up: 需要更粗粒度 → 向上汇总
- time_series: 需要时间分析 → 时间序列
- peer_comparison: 需要横向对比 → 同级对比
- cross_dimension: 需要多维分析 → 跨维度
- anomaly_investigation: 发现异常 → 异常调查
- correlation_analysis: 需要关系分析 → 相关性
</rule>"""
    )
    
    target_dimension: str = Field(
        description="""<what>目标维度</what>
<when>ALWAYS required</when>
<rule>从 dimension_hierarchy 中选择</rule>
<dependency>必须是 dimension_hierarchy 中存在的维度</dependency>"""
    )
    
    filter: Optional[str] = Field(
        default=None,
        description="""<what>过滤条件</what>
<when>需要限定范围时</when>"""
    )
    
    priority: int = Field(
        ge=1,
        le=10,
        description="""<what>优先级</what>
<when>ALWAYS required</when>
<rule>1=直接回答用户问题, 2-3=关键支撑信息, 4-6=深化理解, 7-10=边缘探索</rule>"""
    )
    
    reasoning: str = Field(
        description="""<what>推理说明</what>
<when>ALWAYS required</when>
<rule>解释为什么生成这个问题</rule>"""
    )


class ReplanDecision(BaseModel):
    """重规划决策 - 支持多问题并行执行
    
    <what>重规划决策，包含完整度评估和探索问题列表</what>
    
    <fill_order>
    1. completeness_score (ALWAYS first)
    2. should_replan (ALWAYS)
    3. reason (ALWAYS)
    4. missing_aspects (if should_replan=True)
    5. exploration_questions (if should_replan=True)
    6. confidence (ALWAYS)
    </fill_order>
    
    <examples>
    完成: {"completeness_score": 0.95, "should_replan": false, "reason": "核心问题已完全回答"}
    需重规划: {"completeness_score": 0.6, "should_replan": true, "missing_aspects": ["时间趋势"], "exploration_questions": [...]}
    </examples>
    
    <anti_patterns>
    ❌ completeness_score >= 0.9 但 should_replan = true
    ❌ should_replan = true 但 exploration_questions 为空
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    completeness_score: float = Field(
        ge=0.0,
        le=1.0,
        description="""<what>分析完整度评分</what>
<when>ALWAYS required</when>
<rule>>=0.9 完全回答, 0.7-0.9 基本回答, <0.7 需要重规划</rule>"""
    )
    
    should_replan: bool = Field(
        description="""<what>是否需要重规划</what>
<when>ALWAYS required</when>
<rule>completeness_score < 0.9 → true</rule>
<dependency>与 completeness_score 一致</dependency>"""
    )
    
    reason: str = Field(
        description="""<what>评估理由</what>
<when>ALWAYS required</when>
<rule>解释为什么需要/不需要重规划</rule>"""
    )
    
    missing_aspects: List[str] = Field(
        default_factory=list,
        description="""<what>缺失的分析方面</what>
<when>should_replan=True 时必填</when>
<dependency>should_replan == True</dependency>"""
    )
    
    exploration_questions: List[ExplorationQuestion] = Field(
        default_factory=list,
        description="""<what>探索问题列表</what>
<when>should_replan=True 时必填</when>
<rule>最多 5 个问题，按优先级排序</rule>
<dependency>should_replan == True</dependency>"""
    )
    
    parallel_execution: bool = Field(
        default=True,
        description="""<what>是否并行执行</what>
<when>Default True</when>"""
    )
    
    max_questions_per_round: int = Field(
        default=3,
        ge=1,
        le=5,
        description="""<what>每轮最多执行问题数</what>
<when>Default 3</when>"""
    )
    
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="""<what>决策置信度</what>
<when>ALWAYS required</when>"""
    )
    
    def get_top_questions(self, n: int = 3) -> List[ExplorationQuestion]:
        """获取优先级最高的 N 个问题"""
        sorted_questions = sorted(self.exploration_questions, key=lambda q: q.priority)
        return sorted_questions[:n]
    
    def get_questions_by_type(self, exploration_type: str) -> List[ExplorationQuestion]:
        """按探索类型筛选问题"""
        return [q for q in self.exploration_questions if q.exploration_type == exploration_type]


__all__ = [
    "ExplorationQuestion",
    "ReplanDecision",
]
