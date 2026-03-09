# -*- coding: utf-8 -*-
"""
RulePrefilter - 规则预处理器

在 LLM 调用前进行规则预处理，组合调用现有工具：
- TimeHintGenerator: 时间提示生成
- ComputationMatcher: 计算种子匹配
- ComplexityDetector: 复杂度检测

不调用 LLM，目标 50ms 内完成。
"""

import logging
import re
from datetime import date
from typing import Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.seeds import COMPLEXITY_KEYWORDS

from ..prompts.time_hint_generator import TimeHintGenerator
from ..schemas.prefilter import (
    ComplexityType,
    MatchedComputation,
    PrefilterResult,
    RuleTimeHint,
)
from ..seeds import ComputationMatcher

logger = logging.getLogger(__name__)

class RulePrefilter:
    """规则预处理器
    
    组合调用现有工具进行规则预处理：
    - TimeHintGenerator: 时间提示生成
    - ComputationMatcher: 计算种子匹配
    - ComplexityDetector: 复杂度检测（基于 calc_type）
    
    不调用 LLM，目标 50ms 内完成。
    """
    
    # 默认配置
    _DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.7
    _DEFAULT_FISCAL_YEAR_START_MONTH = 1
    _DEFAULT_CONFIDENCE_WEIGHTS = {
        "time_hint": 0.3,
        "computation": 0.4,
        "complexity": 0.3,
    }
    
    def __init__(
        self,
        current_date: Optional[date] = None,
        fiscal_year_start_month: Optional[int] = None,
    ):
        """初始化 RulePrefilter。
        
        Args:
            current_date: 当前日期，默认使用 date.today()
            fiscal_year_start_month: 财年起始月份，默认从配置读取
        """
        self._load_config()
        
        self.current_date = current_date or date.today()
        self.fiscal_year_start_month = (
            fiscal_year_start_month 
            or self._config_fiscal_year_start_month
        )
        
        # 复用现有的 TimeHintGenerator
        self._time_hint_generator = TimeHintGenerator(
            current_date=self.current_date,
            fiscal_year_start_month=self.fiscal_year_start_month,
        )
        
        # 使用 ComputationMatcher
        self._computation_matcher = ComputationMatcher()
    
    def _load_config(self) -> None:
        """从 app.yaml 加载配置。"""
        try:
            config = get_config()
            optimization_config = config.get_semantic_parser_optimization_config()
            rule_prefilter_config = optimization_config.get("rule_prefilter", {})
            
            self.low_confidence_threshold = rule_prefilter_config.get(
                "low_confidence_threshold", 
                self._DEFAULT_LOW_CONFIDENCE_THRESHOLD
            )
            
            # 置信度计算权重
            weights_config = rule_prefilter_config.get("confidence_weights", {})
            self._confidence_weights = {
                "time_hint": weights_config.get("time_hint", self._DEFAULT_CONFIDENCE_WEIGHTS["time_hint"]),
                "computation": weights_config.get("computation", self._DEFAULT_CONFIDENCE_WEIGHTS["computation"]),
                "complexity": weights_config.get("complexity", self._DEFAULT_CONFIDENCE_WEIGHTS["complexity"]),
            }
            
            # 财年配置从 semantic_understanding 读取
            su_config = config.get("semantic_parser", {}).get("semantic_understanding", {})
            self._config_fiscal_year_start_month = su_config.get(
                "fiscal_year_start_month",
                self._DEFAULT_FISCAL_YEAR_START_MONTH
            )
            
        except Exception as e:
            logger.warning(f"加载配置失败，使用默认值: {e}")
            self.low_confidence_threshold = self._DEFAULT_LOW_CONFIDENCE_THRESHOLD
            self._confidence_weights = dict(self._DEFAULT_CONFIDENCE_WEIGHTS)
            self._config_fiscal_year_start_month = self._DEFAULT_FISCAL_YEAR_START_MONTH
    
    def prefilter(self, question: str) -> PrefilterResult:
        """执行规则预处理。
        
        Args:
            question: 用户问题
            
        Returns:
            PrefilterResult 包含时间提示、计算种子、复杂度类型
        """
        # 1. 检测语言
        detected_language = self._detect_language(question)
        
        # 2. 生成时间提示（复用 TimeHintGenerator）
        time_hints = self._generate_time_hints(question)
        
        # 3. 匹配计算种子（复用 computation_seeds）
        matched_computations = self._match_computations(question)
        
        # 4. 检测复杂度类型（复用 keywords_data）
        detected_complexity = self._detect_complexity(question, matched_computations)
        
        # 5. 计算匹配置信度
        match_confidence = self._calculate_confidence(
            time_hints, matched_computations, detected_complexity
        )
        
        return PrefilterResult(
            time_hints=time_hints,
            matched_computations=matched_computations,
            detected_complexity=detected_complexity,
            detected_language=detected_language,
            match_confidence=match_confidence,
            low_confidence=match_confidence < self.low_confidence_threshold,
        )
    
    def _detect_language(self, question: str) -> str:
        """检测问题语言。"""
        if re.search(r'[\u4e00-\u9fff]', question):
            return "zh"
        if re.search(r'[\u3040-\u309f\u30a0-\u30ff]', question):
            return "ja"
        return "en"
    
    def _generate_time_hints(self, question: str) -> list[RuleTimeHint]:
        """生成时间提示（复用 TimeHintGenerator）。"""
        raw_hints = self._time_hint_generator.generate_hints(question)
        
        return [
            RuleTimeHint(
                original_expression=hint.expression,
                hint_type=self._infer_hint_type(hint.expression),
                parsed_hint=f"{hint.start} 到 {hint.end}",
                confidence=1.0,
            )
            for hint in raw_hints
        ]
    
    def _infer_hint_type(self, expression: str) -> str:
        """推断时间提示类型。"""
        if re.match(r"最近\d+|过去\d+", expression):
            return "range"
        return "relative"
    
    def _match_computations(self, question: str) -> list[MatchedComputation]:
        """匹配计算种子（使用 ComputationMatcher）。"""
        seeds = self._computation_matcher.find_in_text(question)
        return [
            MatchedComputation(
                seed_name=seed.name,
                display_name=seed.display_name,
                calc_type=seed.calc_type,
                formula=seed.formula,
                keywords_matched=seed.keywords,
            )
            for seed in seeds
        ]
    
    def _detect_complexity(
        self, 
        question: str, 
        matched_computations: list[MatchedComputation],
    ) -> list[ComplexityType]:
        """检测复杂度类型（基于 matched_computations 的 calc_type）。
        
        复杂度主要从计算种子的 calc_type 推断，而不是重复匹配关键词。
        """
        detected: list[ComplexityType] = []
        
        # 从计算种子的 calc_type 推断复杂度
        calc_type_to_complexity = {
            "RATIO": ComplexityType.RATIO,
            "TABLE_CALC_PERCENT_OF_TOTAL": ComplexityType.SHARE,
            "TABLE_CALC_PERCENT_DIFF": ComplexityType.TIME_COMPARE,
            "TABLE_CALC_DIFFERENCE": ComplexityType.TIME_COMPARE,
            "TABLE_CALC_RANK": ComplexityType.RANK,
            "TABLE_CALC_RUNNING": ComplexityType.CUMULATIVE,
            "TABLE_CALC_MOVING": ComplexityType.CUMULATIVE,
        }
        
        for comp in matched_computations:
            complexity = calc_type_to_complexity.get(comp.calc_type)
            if complexity and complexity not in detected:
                detected.append(complexity)
        
        question_lower = question.lower()
        
        # 补充：检测排名/Top N（ranking 通常不会命中 computation_seeds）
        table_calc_keywords = COMPLEXITY_KEYWORDS.get("table_calc", [])
        if (
            any(kw.lower() in question_lower for kw in table_calc_keywords)
            or re.search(r"(?:前|后)\s*\d+", question)
            or re.search(r"(?:top|bottom)\s*\d+", question_lower)
        ):
            if ComplexityType.RANK not in detected:
                detected.append(ComplexityType.RANK)
        
        # 补充：检测同比/环比等时间比较表达
        time_calc_keywords = COMPLEXITY_KEYWORDS.get("time_calc", [])
        if any(kw in question_lower for kw in time_calc_keywords):
            if ComplexityType.TIME_COMPARE not in detected:
                detected.append(ComplexityType.TIME_COMPARE)
        
        # 补充：检测显式比率/占比类表达
        derived_metric_keywords = COMPLEXITY_KEYWORDS.get("derived_metric", [])
        if any(kw in question_lower for kw in derived_metric_keywords):
            if ComplexityType.RATIO not in detected:
                detected.append(ComplexityType.RATIO)
        
        # 补充：检测子查询（这个在 computation_seeds 中没有覆盖）
        subquery_keywords = COMPLEXITY_KEYWORDS.get("subquery", [])
        if any(kw in question_lower for kw in subquery_keywords):
            if ComplexityType.SUBQUERY not in detected:
                detected.append(ComplexityType.SUBQUERY)
        
        # 如果没有检测到复杂类型，标记为简单
        if not detected:
            detected.append(ComplexityType.SIMPLE)
        
        return detected
    
    def _calculate_confidence(
        self,
        time_hints: list[RuleTimeHint],
        matched_computations: list[MatchedComputation],
        detected_complexity: list[ComplexityType],
    ) -> float:
        """计算匹配置信度。
        
        置信度计算逻辑（权重从 app.yaml 读取）：
        - 时间提示匹配：+time_hint 权重
        - 计算种子匹配：+computation 权重
        - 复杂度检测（非 SIMPLE）：+complexity 权重
        """
        confidence = 0.0
        w = self._confidence_weights
        
        if time_hints:
            avg_hint_confidence = sum(h.confidence for h in time_hints) / len(time_hints)
            confidence += w["time_hint"] * min(1.0, avg_hint_confidence)
        
        if matched_computations:
            confidence += w["computation"]
        
        if detected_complexity and ComplexityType.SIMPLE not in detected_complexity:
            confidence += w["complexity"]
        
        return min(1.0, confidence)

__all__ = ["RulePrefilter"]
