# -*- coding: utf-8 -*-
"""Replanner Agent 输出 schema。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CandidateQuestion(BaseModel):
    """结构化 follow-up 候选问题。"""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(description="候选后续问题")
    question_type: str = Field(default="followup", description="问题类型")
    priority: int = Field(
        default=1,
        ge=1,
        le=10,
        description="优先级，越小越优先",
    )
    expected_info_gain: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="预期信息增益",
    )
    rationale: str = Field(default="", description="推荐理由")
    estimated_mode: str = Field(
        default="single_query",
        description=(
            "预计执行模式：single_query / complex_single_query / "
            "multi_step_analysis / why_analysis"
        ),
    )

    @model_validator(mode="after")
    def validate_question(self) -> "CandidateQuestion":
        """保证字段文本稳定且问题本身非空。"""
        self.question = self.question.strip()
        self.question_type = self.question_type.strip() or "followup"
        self.rationale = self.rationale.strip()
        self.estimated_mode = self.estimated_mode.strip() or "single_query"
        if not self.question:
            raise ValueError("candidate_questions.question 不能为空")
        return self


class ReplanDecision(BaseModel):
    """最终重规划决策。"""

    model_config = ConfigDict(extra="forbid")

    should_replan: bool = Field(description="是否需要继续分析")
    reason: str = Field(description="决策原因")
    new_question: Optional[str] = Field(
        default=None,
        description="主后续问题；当 should_replan=True 时必须可推出非空问题",
    )
    suggested_questions: list[str] = Field(
        default_factory=list,
        description="兼容旧展示链路的候选问题文本",
    )
    candidate_questions: list[CandidateQuestion] = Field(
        default_factory=list,
        description="结构化候选问题列表",
    )

    @model_validator(mode="after")
    def validate_consistency(self) -> "ReplanDecision":
        """统一 candidate/suggested/new_question，避免输出自相矛盾。"""
        self.reason = self.reason.strip()
        self.new_question = self.new_question.strip() if self.new_question else None
        self.suggested_questions = [
            question.strip()
            for question in self.suggested_questions
            if isinstance(question, str) and question.strip()
        ]

        normalized_candidates: list[CandidateQuestion] = []
        seen_questions: set[str] = set()

        def _append_candidate(
            question: str,
            *,
            priority: int,
            rationale: Optional[str] = None,
            question_type: str = "followup",
            expected_info_gain: float = 0.5,
            estimated_mode: str = "single_query",
        ) -> None:
            normalized_question = str(question or "").strip()
            if not normalized_question:
                return
            key = normalized_question.lower()
            if key in seen_questions:
                return
            seen_questions.add(key)
            normalized_candidates.append(
                CandidateQuestion(
                    question=normalized_question,
                    question_type=question_type,
                    priority=max(1, min(priority, 10)),
                    expected_info_gain=max(0.0, min(expected_info_gain, 1.0)),
                    rationale=(rationale or self.reason or "").strip(),
                    estimated_mode=estimated_mode,
                )
            )

        if self.new_question:
            _append_candidate(
                self.new_question,
                priority=1,
                rationale=self.reason,
                question_type="primary_followup",
            )

        for index, candidate in enumerate(self.candidate_questions, start=1):
            _append_candidate(
                candidate.question,
                priority=candidate.priority or index,
                rationale=candidate.rationale or self.reason,
                question_type=candidate.question_type,
                expected_info_gain=candidate.expected_info_gain,
                estimated_mode=candidate.estimated_mode,
            )

        for index, question in enumerate(self.suggested_questions, start=2):
            _append_candidate(
                question,
                priority=index,
                rationale=self.reason,
            )

        self.candidate_questions = normalized_candidates
        if self.should_replan and not self.new_question:
            if self.candidate_questions:
                self.new_question = self.candidate_questions[0].question
            else:
                raise ValueError(
                    "should_replan=True 时，new_question 或 candidate_questions 不能为空"
                )

        if not self.suggested_questions and self.candidate_questions:
            self.suggested_questions = [
                candidate.question
                for candidate in self.candidate_questions
                if candidate.question != self.new_question
            ]
        return self


__all__ = [
    "CandidateQuestion",
    "ReplanDecision",
]
