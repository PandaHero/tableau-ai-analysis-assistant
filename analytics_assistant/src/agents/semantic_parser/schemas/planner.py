# -*- coding: utf-8 -*-
"""
Planner 相关数据模型

用于描述复杂问题和 why 问题的分析计划，帮助后续检索与语义理解节点
保留多步分析视角，而不是直接按简单聚合查询处理。
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PlanMode(str, Enum):
    """分析计划模式。"""

    DIRECT_QUERY = "direct_query"
    DECOMPOSED_QUERY = "decomposed_query"
    WHY_ANALYSIS = "why_analysis"


class AnalysisMode(str, Enum):
    """全局语义理解后的分析模式。"""

    SINGLE_QUERY = "single_query"
    COMPLEX_SINGLE_QUERY = "complex_single_query"
    MULTI_STEP_ANALYSIS = "multi_step_analysis"
    WHY_ANALYSIS = "why_analysis"


class QueryFeasibilityBlocker(str, Enum):
    """导致问题无法通过单条查询完成的阻塞原因。"""

    RESULT_SET_DEPENDENCY = "result_set_dependency"
    DYNAMIC_AXIS_SELECTION = "dynamic_axis_selection"
    MULTI_HOP_REASONING = "multi_hop_reasoning"
    MISSING_BASELINE = "missing_baseline"
    UNSUPPORTED_QUERY_BUILDER_PATTERN = "unsupported_query_builder_pattern"
    OPEN_BUSINESS_SCOPE = "open_business_scope"


class PlanStepType(str, Enum):
    """分析计划步骤类型。"""

    QUERY = "query"
    SYNTHESIS = "synthesis"
    REPLAN = "replan"


class PlanStepKind(str, Enum):
    """步骤的稳定语义类型。"""

    PRIMARY_QUERY = "primary_query"
    VERIFY_ANOMALY = "verify_anomaly"
    RANK_EXPLANATORY_AXES = "rank_explanatory_axes"
    SCREEN_TOP_AXES = "screen_top_axes"
    LOCATE_ANOMALOUS_SLICE = "locate_anomalous_slice"
    SUPPLEMENTAL_QUERY = "supplemental_query"
    SYNTHESIZE_CAUSE = "synthesize_cause"
    RESULT_SYNTHESIS = "result_synthesis"


class StepIntent(BaseModel):
    """V3 中单个分析步骤的语义意图。"""

    model_config = ConfigDict(extra="forbid")

    step_id: Optional[str] = Field(default=None, description="步骤唯一标识")
    title: str = Field(description="步骤标题")
    goal: Optional[str] = Field(default=None, description="该步骤要解决的核心目标")
    question: str = Field(description="子问题描述")
    purpose: Optional[str] = Field(default=None, description="该步骤的目的")
    step_type: PlanStepType = Field(
        default=PlanStepType.QUERY,
        description="步骤类型：query 表示需要执行查询，synthesis 表示汇总前序结果",
    )
    step_kind: Optional[PlanStepKind] = Field(
        default=None,
        description="步骤的稳定语义类型",
    )
    uses_primary_query: bool = Field(
        default=False,
        description="是否复用主问题的首跳查询结果，避免重复解析/执行",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="当前步骤依赖的前序步骤 ID 列表",
    )
    semantic_focus: list[str] = Field(
        default_factory=list,
        description="该步骤语义理解应重点关注的业务词/方向",
    )
    expected_output: Optional[str] = Field(
        default=None,
        description="期望输出的证据或结果摘要",
    )
    candidate_axes: list[str] = Field(
        default_factory=list,
        description="why/复杂问题下候选定位维度或解释轴",
    )
    targets_anomaly: bool = Field(
        default=False,
        description="是否显式用于定位异常对象或异常切片",
    )
    clarification_if_missing: list[str] = Field(
        default_factory=list,
        description="如果缺失这些业务口径，应优先发起澄清",
    )


class AnalysisPlanStep(StepIntent):
    """兼容旧代码的分析计划步骤模型。"""

    model_config = ConfigDict(extra="forbid")


class AxisEvidenceScore(BaseModel):
    """某个候选解释轴的证据强度。"""

    model_config = ConfigDict(extra="forbid")

    axis: str = Field(description="候选解释轴名称")
    explained_share: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="该解释轴解释掉的异常占比",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="解释轴证据置信度",
    )
    reason: str = Field(default="", description="该评分的简短原因")


class StepArtifact(BaseModel):
    """单个步骤沉淀到证据上下文中的结构化摘要。"""

    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(description="步骤 ID")
    title: str = Field(description="步骤标题")
    step_type: PlanStepType = Field(default=PlanStepType.QUERY)
    step_kind: Optional[PlanStepKind] = Field(default=None)
    query_id: Optional[str] = Field(default=None, description="执行查询 ID")
    restated_question: Optional[str] = Field(
        default=None,
        description="该步骤最终落地后的完整问题表述",
    )
    table_summary: Optional[str] = Field(
        default=None,
        description="结果表格摘要，供后续 step 或 synthesis 使用",
    )
    key_findings: list[str] = Field(
        default_factory=list,
        description="该步骤提炼出的关键发现",
    )
    entity_scope: list[str] = Field(
        default_factory=list,
        description="该步骤定位出的关键对象集合",
    )
    targets_anomaly: bool = Field(
        default=False,
        description="该步骤是否显式用于定位异常对象或异常切片",
    )
    validated_axes: list[str] = Field(
        default_factory=list,
        description="该步骤已经验证过的解释轴",
    )
    blocked_reason: Optional[str] = Field(
        default=None,
        description="如果该步骤被澄清或异常阻塞，记录原因",
    )


class EvidenceContext(BaseModel):
    """多步分析过程中逐步累积的结构化证据上下文。"""

    model_config = ConfigDict(extra="forbid")

    primary_question: str = Field(description="原始主问题")
    baseline_type: Optional[str] = Field(
        default=None,
        description="why 问题的比较基线，如同比/环比/目标差",
    )
    key_entities: list[str] = Field(
        default_factory=list,
        description="当前问题涉及的关键对象",
    )
    anomalous_entities: list[str] = Field(
        default_factory=list,
        description="已经定位出的异常对象集合",
    )
    validated_axes: list[str] = Field(
        default_factory=list,
        description="已验证过的解释轴",
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="仍未解决的问题或待验证假设",
    )
    step_artifacts: list[StepArtifact] = Field(
        default_factory=list,
        description="前序步骤的结构化摘要",
    )
    axis_scores: list[AxisEvidenceScore] = Field(
        default_factory=list,
        description="候选解释轴的证据评分",
    )


class GlobalUnderstandingOutput(BaseModel):
    """全局语义理解输出，负责决定是否单查、是否拆步以及如何拆步。"""

    model_config = ConfigDict(extra="forbid")

    analysis_mode: AnalysisMode = Field(
        default=AnalysisMode.SINGLE_QUERY,
        description="全局问题分析模式",
    )
    single_query_feasible: bool = Field(
        default=True,
        description="在当前系统能力下，是否可以通过单条查询表达",
    )
    single_query_blockers: list[QueryFeasibilityBlocker] = Field(
        default_factory=list,
        description="不能单查时的阻塞原因",
    )
    decomposition_reason: Optional[str] = Field(
        default=None,
        description="为什么需要拆分或保留单查的原因说明",
    )
    needs_clarification: bool = Field(
        default=False,
        description="进入 step grounding 前是否需要澄清",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="澄清问题",
    )
    clarification_options: list[str] = Field(
        default_factory=list,
        description="澄清选项",
    )
    primary_restated_question: Optional[str] = Field(
        default=None,
        description="补全上下文后的主问题重述",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="当前分析计划中的风险点，如口径不清、基线缺失等",
    )
    llm_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="LLM 对全局理解结果的置信度",
    )
    analysis_plan: Optional["AnalysisPlan"] = Field(
        default=None,
        description="全局理解生成的分析计划",
    )


class AnalysisPlan(BaseModel):
    """Planner 输出的分析计划。"""

    model_config = ConfigDict(extra="forbid")

    plan_mode: PlanMode = Field(
        default=PlanMode.DIRECT_QUERY,
        description="当前问题的分析模式",
    )
    single_query_feasible: bool = Field(
        default=True,
        description="在当前 QueryBuilder 能力下是否支持单条查询表达",
    )
    needs_planning: bool = Field(default=False, description="是否需要显式分析计划")
    requires_llm_reasoning: bool = Field(
        default=False,
        description="是否要求后续节点保留 LLM 推理路径",
    )
    decomposition_reason: Optional[str] = Field(
        default=None,
        description="为什么需要拆解或保留单查的原因",
    )
    goal: Optional[str] = Field(default=None, description="本次分析的总体目标")
    execution_strategy: str = Field(
        default="single_query",
        description="建议执行策略，如 single_query / sequential",
    )
    reasoning_focus: list[str] = Field(
        default_factory=list,
        description="推理时需要重点关注的方向",
    )
    sub_questions: list[AnalysisPlanStep] = Field(
        default_factory=list,
        description="拆解后的子问题列表",
    )
    risk_flags: list[str] = Field(
        default_factory=list,
        description="规划阶段发现的主要风险点",
    )
    needs_clarification: bool = Field(
        default=False,
        description="在进入 step 级语义理解前是否需要澄清",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="规划阶段的澄清问题",
    )
    clarification_options: list[str] = Field(
        default_factory=list,
        description="规划阶段的澄清选项",
    )
    retrieval_focus_terms: list[str] = Field(
        default_factory=list,
        description="建议检索重点关注的业务词",
    )
    planner_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="planner 对当前模式判断的置信度",
    )

    @property
    def steps(self) -> list[AnalysisPlanStep]:
        """V3 命名下的步骤访问别名，便于后续逐步迁移。"""

        return self.sub_questions


GlobalUnderstandingOutput.model_rebuild()


def parse_analysis_plan(
    raw_analysis_plan: Any = None,
    raw_global_understanding: Any = None,
) -> Optional[AnalysisPlan]:
    """从旧 analysis_plan 或新的 global_understanding 中解析 AnalysisPlan。

    迁移期优先读取旧字段，若不存在则回退到 global_understanding.analysis_plan。
    """

    if raw_analysis_plan:
        try:
            return AnalysisPlan.model_validate(raw_analysis_plan)
        except Exception:
            pass

    if raw_global_understanding:
        try:
            global_understanding = GlobalUnderstandingOutput.model_validate(
                raw_global_understanding
            )
        except Exception:
            return None
        return global_understanding.analysis_plan

    return None


def parse_step_intent(raw_step_intent: Any = None) -> Optional[StepIntent]:
    """安全解析当前步骤意图。"""

    if not raw_step_intent:
        return None
    try:
        return StepIntent.model_validate(raw_step_intent)
    except Exception:
        return None


__all__ = [
    "AnalysisMode",
    "QueryFeasibilityBlocker",
    "PlanMode",
    "PlanStepType",
    "PlanStepKind",
    "StepIntent",
    "AnalysisPlanStep",
    "AxisEvidenceScore",
    "StepArtifact",
    "EvidenceContext",
    "GlobalUnderstandingOutput",
    "AnalysisPlan",
    "parse_analysis_plan",
    "parse_step_intent",
]
