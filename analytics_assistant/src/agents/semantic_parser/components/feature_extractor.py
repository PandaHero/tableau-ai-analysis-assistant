# -*- coding: utf-8 -*-
"""
FeatureExtractor - 特征提取器

使用快速 LLM 验证和修正 RulePrefilter 的结果：
- 验证时间提示
- 验证计算种子匹配
- 提取 required_measures 和 required_dimensions

配置来源：
- analytics_assistant/config/app.yaml -> semantic_parser.optimization.feature_extractor

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

import asyncio
import json
import logging
import re
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.seeds import DIMENSION_SEEDS, MEASURE_SEEDS
from langchain_core.messages import HumanMessage, SystemMessage

from analytics_assistant.src.agents.base.node import get_llm, stream_llm_structured
from analytics_assistant.src.infra.ai.models import TaskType

from ..schemas.planner import EvidenceContext, StepIntent
from ..schemas.prefilter import (
    ComplexityType,
    FeatureExtractionOutput,
    PrefilterResult,
)
from ..prompts.feature_extractor_prompt import (
    build_feature_extractor_prompt,
    FEATURE_EXTRACTOR_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

_RULE_FAST_PATH_MIN_CONFIDENCE = 0.70
_RULE_FAST_PATH_MAX_TERMS = 3
_ASCII_TERM_PATTERN = re.compile(r"^[a-z0-9_ ]+$")
_TIME_DIMENSION_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("每个月", "各月", "月份", "月度", "按月"), "月份"),
    (("季度", "各季度", "按季度", "q1", "q2", "q3", "q4"), "季度"),
    (("每周", "各周", "周度", "按周"), "周"),
    (("每天", "每日", "日期", "按日"), "日期"),
    (("每年", "各年", "按年", "年度"), "年份"),
)

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def get_feature_extractor_config() -> dict[str, Any]:
    """获取 FeatureExtractor 配置。"""
    try:
        config = get_config()
        return config.get_semantic_parser_optimization_config().get(
            "feature_extractor", {}
        )
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}

# ═══════════════════════════════════════════════════════════════════════════
# FeatureExtractor 组件
# ═══════════════════════════════════════════════════════════════════════════

class FeatureExtractor:
    """特征提取器
    
    使用快速 LLM 验证 RulePrefilter 的结果，提取字段需求。
    
    设计原则：
    - 使用项目模型管理系统获取 LLM
    - 精简 Prompt（~200 tokens）
    - 超时后降级到规则结果
    
    Examples:
        >>> extractor = FeatureExtractor()
        >>> result = await extractor.extract(
        ...     question="上个月各地区的利润率",
        ...     prefilter_result=prefilter_result,
        ... )
    """
    
    def __init__(self):
        """初始化 FeatureExtractor。
        
        配置从 app.yaml 加载，LLM 通过项目模型管理系统获取。
        """
        config = get_feature_extractor_config()
        
        # 从配置加载超时时间（毫秒）
        self.timeout_ms = config.get("timeout_ms", 500)
        self._llm = None

    def _get_llm(self):
        """懒加载 LLM，避免规则快路径也初始化模型。

        使用 TaskType.FIELD_MAPPING 获取专用快模型，而非复用
        SemanticUnderstanding 的主模型。
        """
        if self._llm is None:
            self._llm = get_llm(
                agent_name="semantic_parser",
                task_type=TaskType.FIELD_MAPPING,
                enable_json_mode=True,
            )
        return self._llm
    
    async def extract(
        self,
        question: str,
        prefilter_result: PrefilterResult,
        current_step_intent: Optional[StepIntent] = None,
        evidence_context: Optional[EvidenceContext] = None,
    ) -> FeatureExtractionOutput:
        """提取特征
        
        Args:
            question: 用户问题
            prefilter_result: 规则预处理结果
            
        Returns:
            FeatureExtractionOutput 特征提取输出
        """
        step_requires_context = self._step_requires_contextual_extraction(
            current_step_intent
        )
        rule_fast_path = None
        if not step_requires_context:
            rule_fast_path = self._try_rule_fast_path(question, prefilter_result)
        if rule_fast_path is not None:
            rule_fast_path = self._apply_step_intent_hints(
                rule_fast_path,
                current_step_intent,
            )
            logger.info(
                "FeatureExtractor: 命中规则快路径, "
                f"measures={rule_fast_path.required_measures}, "
                f"dimensions={rule_fast_path.required_dimensions}, "
                f"confidence={rule_fast_path.confirmation_confidence:.2f}"
            )
            return rule_fast_path
        if step_requires_context:
            logger.info(
                "FeatureExtractor: 跳过规则快路径，使用 step intent 上下文增强抽取"
            )

        try:
            # 如果配置了超时且大于 0，则使用超时
            if self.timeout_ms > 0:
                timeout_seconds = self.timeout_ms / 1000.0
                result = await asyncio.wait_for(
                    self._extract_with_llm(
                        question,
                        prefilter_result,
                        current_step_intent=current_step_intent,
                        evidence_context=evidence_context,
                    ),
                    timeout=timeout_seconds,
                )
            else:
                # 不设置超时
                result = await self._extract_with_llm(
                    question,
                    prefilter_result,
                    current_step_intent=current_step_intent,
                    evidence_context=evidence_context,
                )
            return self._apply_step_intent_hints(result, current_step_intent)
            
        except asyncio.TimeoutError:
            logger.warning(
                f"FeatureExtractor 超时 ({self.timeout_ms}ms)，使用降级模式"
            )
            return self._apply_step_intent_hints(
                self._create_degraded_output(prefilter_result),
                current_step_intent,
            )
            
        except Exception as e:
            logger.error(f"FeatureExtractor 失败: {e}")
            return self._apply_step_intent_hints(
                self._create_degraded_output(prefilter_result),
                current_step_intent,
            )
    
    async def _extract_with_llm(
        self,
        question: str,
        prefilter_result: PrefilterResult,
        current_step_intent: Optional[StepIntent] = None,
        evidence_context: Optional[EvidenceContext] = None,
    ) -> FeatureExtractionOutput:
        """使用 LLM 提取特征（结构化输出）。"""
        user_prompt = build_feature_extractor_prompt(
            question,
            prefilter_result,
            current_step_intent=current_step_intent,
            evidence_context=evidence_context,
        )
        llm = self._get_llm()

        messages = [
            SystemMessage(content=FEATURE_EXTRACTOR_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        try:
            result = await stream_llm_structured(
                llm=llm,
                messages=messages,
                output_model=FeatureExtractionOutput,
            )
            result.is_degraded = False
            return result
        except Exception as e:
            logger.warning(f"FeatureExtractor 结构化输出解析失败，使用降级模式: {e}")
            return self._create_degraded_output(prefilter_result)
    
    def _create_degraded_output(
        self,
        prefilter_result: PrefilterResult,
    ) -> FeatureExtractionOutput:
        """创建降级输出。
        
        使用 RulePrefilter 的结果作为降级方案。
        """
        # 从时间提示中提取
        confirmed_time_hints = [
            hint.original_expression for hint in prefilter_result.time_hints
        ]
        
        # 从计算种子中提取
        confirmed_computations = [
            comp.seed_name for comp in prefilter_result.matched_computations
        ]
        
        return FeatureExtractionOutput(
            required_measures=[],  # 降级模式下为空，由 FieldRetriever 使用全量检索
            required_dimensions=[],
            confirmed_time_hints=confirmed_time_hints,
            confirmed_computations=confirmed_computations,
            confirmation_confidence=prefilter_result.match_confidence,
            is_degraded=True,
        )

    def _try_rule_fast_path(
        self,
        question: str,
        prefilter_result: PrefilterResult,
    ) -> Optional[FeatureExtractionOutput]:
        """简单查询优先走规则快路径，减少默认 LLM 调用。"""
        if prefilter_result.detected_complexity != [ComplexityType.SIMPLE]:
            return None

        question_lower = question.lower()
        required_measures = self._match_seed_terms(
            question_lower,
            MEASURE_SEEDS,
            value_key="field_caption",
            category_key="measure_category",
        )
        required_dimensions = self._match_seed_terms(
            question_lower,
            DIMENSION_SEEDS,
            value_key="field_caption",
            category_key="category",
        )

        inferred_time_dimension = self._infer_time_dimension(question_lower, prefilter_result)
        if inferred_time_dimension and inferred_time_dimension not in required_dimensions:
            required_dimensions.append(inferred_time_dimension)

        if not required_measures and not required_dimensions:
            return None

        confirmation_confidence = self._estimate_rule_confidence(
            required_measures=required_measures,
            required_dimensions=required_dimensions,
            prefilter_result=prefilter_result,
        )
        if confirmation_confidence < _RULE_FAST_PATH_MIN_CONFIDENCE:
            return None

        return FeatureExtractionOutput(
            required_measures=required_measures,
            required_dimensions=required_dimensions,
            confirmed_time_hints=[
                hint.original_expression for hint in prefilter_result.time_hints
            ],
            confirmed_computations=[
                comp.seed_name for comp in prefilter_result.matched_computations
            ],
            confirmation_confidence=confirmation_confidence,
            is_degraded=False,
        )

    def _match_seed_terms(
        self,
        question_lower: str,
        seeds: list[dict[str, Any]],
        *,
        value_key: str,
        category_key: str,
    ) -> list[str]:
        """从种子数据中提取最可能的业务术语。"""
        matches: list[tuple[float, str]] = []

        for seed in seeds:
            field_caption = str(seed.get(value_key, "")).strip()
            if not field_caption:
                continue

            candidate_terms = [field_caption, *seed.get("aliases", [])]
            best_score = 0.0
            best_term = ""
            for term in candidate_terms:
                raw_term = str(term).strip()
                normalized = raw_term.lower()
                if not raw_term or not normalized:
                    continue
                if not self._term_in_question(question_lower, normalized):
                    continue

                score = float(len(normalized))
                if normalized == field_caption.lower():
                    score += 3.0
                if seed.get(category_key):
                    score += 0.2
                if score > best_score:
                    best_score = score
                    best_term = raw_term

            if best_score > 0:
                matches.append((best_score, best_term or field_caption))

        ordered_terms: list[str] = []
        seen_terms: set[str] = set()
        for _, matched_term in sorted(matches, key=lambda item: item[0], reverse=True):
            dedupe_key = matched_term.strip().lower()
            if dedupe_key in seen_terms:
                continue
            seen_terms.add(dedupe_key)
            ordered_terms.append(matched_term)
            if len(ordered_terms) >= _RULE_FAST_PATH_MAX_TERMS:
                break

        return ordered_terms

    def _term_in_question(self, question_lower: str, term: str) -> bool:
        """判断术语是否出现在问题中。"""
        if not term:
            return False

        if _ASCII_TERM_PATTERN.fullmatch(term):
            pattern = rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])"
            return re.search(pattern, question_lower) is not None

        if len(term) < 2:
            return False

        return term in question_lower

    def _infer_time_dimension(
        self,
        question_lower: str,
        prefilter_result: PrefilterResult,
    ) -> Optional[str]:
        """根据时间提示推断应补充的时间维度术语。"""
        if not prefilter_result.time_hints:
            return None

        for keywords, dimension in _TIME_DIMENSION_HINTS:
            if any(keyword in question_lower for keyword in keywords):
                return dimension

        return "日期"

    def _estimate_rule_confidence(
        self,
        *,
        required_measures: list[str],
        required_dimensions: list[str],
        prefilter_result: PrefilterResult,
    ) -> float:
        """估算规则快路径的确认置信度。

        权重设计原则：只有同时满足多个条件的高确定性查询才应超过阈值(0.85)，
        避免歧义场景（如"销售"可能匹配"销售额"或"销售数量"）被跳过 LLM 验证。
        """
        confidence = 0.0
        if required_measures:
            confidence += 0.35
        if required_dimensions:
            confidence += 0.15
        # 多字段命中说明语义更明确
        if len(required_measures) > 1:
            confidence += 0.05
        if len(required_dimensions) > 1:
            confidence += 0.05
        # 时间提示和简单复杂度作为辅助信号
        if prefilter_result.time_hints:
            confidence += 0.1
        if prefilter_result.detected_complexity == [ComplexityType.SIMPLE]:
            confidence += 0.1
        # 同时有度量和维度的组合加分
        if required_measures and required_dimensions:
            confidence += 0.1
        return min(0.9, confidence)

    def _step_requires_contextual_extraction(
        self,
        current_step_intent: Optional[StepIntent],
    ) -> bool:
        """依赖前序证据的 follow-up step 不走规则快路径。"""
        if current_step_intent is None:
            return False
        return bool(
            current_step_intent.depends_on
            or current_step_intent.semantic_focus
            or current_step_intent.candidate_axes
            or current_step_intent.expected_output
        )

    def _apply_step_intent_hints(
        self,
        output: FeatureExtractionOutput,
        current_step_intent: Optional[StepIntent],
    ) -> FeatureExtractionOutput:
        """把 step intent 中的解释轴补充回字段需求。"""
        if current_step_intent is None or not current_step_intent.candidate_axes:
            return output

        required_dimensions = list(output.required_dimensions)
        seen_dimensions = {item.strip().lower() for item in required_dimensions if item}
        added = False
        for axis in current_step_intent.candidate_axes:
            normalized = axis.strip()
            if not normalized:
                continue
            dedupe_key = normalized.lower()
            if dedupe_key in seen_dimensions:
                continue
            required_dimensions.append(normalized)
            seen_dimensions.add(dedupe_key)
            added = True

        if not added:
            return output

        return output.model_copy(
            update={
                "required_dimensions": required_dimensions,
            }
        )

__all__ = ["FeatureExtractor", "get_feature_extractor_config"]
