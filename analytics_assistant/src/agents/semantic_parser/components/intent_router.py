# -*- coding: utf-8 -*-
"""
IntentRouter 组件 - 三层意图识别策略（简化版）

简化设计思路：
- 只判断问题是否属于"数据分析"或"元数据问答"
- 不再细分 CLARIFICATION（模糊问题由 SemanticUnderstanding 处理）
- 正向匹配数据分析关键词，而非排除法

三层策略：
- L0 规则层（0 LLM 调用）：关键词匹配
- L1 小模型分类（1 次低成本调用）：可选，默认禁用
- L2 兜底：返回 DATA_QUERY（让后续流程处理）

Requirements: 0.12 - IntentRouter 意图识别
"""

import logging
import re
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.seeds import (
    INTENT_KEYWORDS,
    IRRELEVANT_PATTERNS,
)

from ..schemas.intent import IntentType, IntentRouterOutput

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 模块级变量（用于外部访问）
# ═══════════════════════════════════════════════════════════════════════════

METADATA_KEYWORDS = INTENT_KEYWORDS["metadata"]
DATA_ANALYSIS_KEYWORDS = INTENT_KEYWORDS["data_analysis"]
SHORT_AMBIGUOUS_KEYWORDS = INTENT_KEYWORDS["ambiguous"]

# ═══════════════════════════════════════════════════════════════════════════
# IntentRouter 组件
# ═══════════════════════════════════════════════════════════════════════════

class IntentRouter:
    """意图识别器 - 三层策略（简化版）。
    
    简化设计：
    - 只判断是否是"数据分析"或"元数据问答"
    - 正向匹配数据分析关键词
    - 模糊问题由后续 SemanticUnderstanding 处理
    
    三层策略：
    - L0 规则层（0 LLM）：关键词匹配
    - L1 小模型分类（可选）：LLM 判断
    - L2 兜底：返回 DATA_QUERY
    
    配置来源：
    - 优先从 app.yaml 的 intent_router 节读取
    - 未配置时使用默认值
    
    Attributes:
        l1_confidence_threshold: L1 置信度阈值（默认 0.8）
        enable_l1: 是否启用 L1 小模型分类（默认 False）
    
    Examples:
        >>> router = IntentRouter()
        >>> result = await router.route("上个月各地区的销售额")
        >>> print(result.intent_type)  # IntentType.DATA_QUERY
        
        >>> result = await router.route("有哪些字段")
        >>> print(result.intent_type)  # IntentType.GENERAL
    """
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 默认置信度常量（可被 YAML 配置覆盖）
    # ═══════════════════════════════════════════════════════════════════════════
    
    _DEFAULT_BASE_CONFIDENCE: float = 0.7
    _DEFAULT_CONFIDENCE_INCREMENT: float = 0.1
    _DEFAULT_MAX_CONFIDENCE: float = 0.95
    _DEFAULT_HIGH_CONFIDENCE: float = 0.95
    _DEFAULT_FALLBACK_CONFIDENCE: float = 0.5
    _DEFAULT_SHORT_QUESTION_THRESHOLD: int = 10
    _DEFAULT_L1_CONFIDENCE_THRESHOLD: float = 0.8
    
    def __init__(
        self,
        l1_confidence_threshold: Optional[float] = None,
        enable_l1: Optional[bool] = None,
    ):
        """初始化 IntentRouter。
        
        Args:
            l1_confidence_threshold: L1 置信度阈值（None 则从配置读取）
            enable_l1: 是否启用 L1 小模型分类（None 则从配置读取）
        """
        # 从 YAML 配置加载
        self._load_config()
        
        # 参数覆盖配置
        if l1_confidence_threshold is not None:
            self.l1_confidence_threshold = l1_confidence_threshold
        if enable_l1 is not None:
            self.enable_l1 = enable_l1
    
    def _load_config(self) -> None:
        """从 YAML 配置加载参数（仅加载阈值等运行时参数）。
        
        关键词从 keywords_data.py 导入，不从 YAML 读取。
        """
        try:
            config = get_config()
            intent_config = config.get("intent_router", {})
            confidence_config = intent_config.get("confidence", {})
            l1_config = intent_config.get("l1", {})
            rules_config = intent_config.get("rules", {})
            
            # 置信度配置
            self.BASE_CONFIDENCE = confidence_config.get("base", self._DEFAULT_BASE_CONFIDENCE)
            self.CONFIDENCE_INCREMENT = confidence_config.get("increment", self._DEFAULT_CONFIDENCE_INCREMENT)
            self.MAX_CONFIDENCE = confidence_config.get("max", self._DEFAULT_MAX_CONFIDENCE)
            self.HIGH_CONFIDENCE = confidence_config.get("high", self._DEFAULT_HIGH_CONFIDENCE)
            self.FALLBACK_CONFIDENCE = confidence_config.get("fallback", self._DEFAULT_FALLBACK_CONFIDENCE)
            
            # L1 配置
            self.enable_l1 = l1_config.get("enabled", False)
            self.l1_confidence_threshold = l1_config.get("threshold", self._DEFAULT_L1_CONFIDENCE_THRESHOLD)
            
            # 规则配置
            self.SHORT_QUESTION_THRESHOLD = rules_config.get("short_question_threshold", self._DEFAULT_SHORT_QUESTION_THRESHOLD)
            
            logger.debug("IntentRouter 配置加载成功")
            
        except Exception as e:
            logger.warning(f"加载 IntentRouter 配置失败，使用默认值: {e}")
            # 使用默认值
            self.BASE_CONFIDENCE = self._DEFAULT_BASE_CONFIDENCE
            self.CONFIDENCE_INCREMENT = self._DEFAULT_CONFIDENCE_INCREMENT
            self.MAX_CONFIDENCE = self._DEFAULT_MAX_CONFIDENCE
            self.HIGH_CONFIDENCE = self._DEFAULT_HIGH_CONFIDENCE
            self.FALLBACK_CONFIDENCE = self._DEFAULT_FALLBACK_CONFIDENCE
            self.SHORT_QUESTION_THRESHOLD = self._DEFAULT_SHORT_QUESTION_THRESHOLD
            self.enable_l1 = False
            self.l1_confidence_threshold = self._DEFAULT_L1_CONFIDENCE_THRESHOLD
        
        # 编译无关问题正则（性能优化）
        self._irrelevant_patterns = [
            re.compile(p, re.IGNORECASE) for p in IRRELEVANT_PATTERNS
        ]
        
        # 关键词从 seeds 包导入（预处理为小写用于匹配）
        self._metadata_keywords = [kw.lower() for kw in INTENT_KEYWORDS["metadata"]]
        self._data_analysis_keywords = [kw.lower() for kw in INTENT_KEYWORDS["data_analysis"]]
        self._ambiguous_keywords = [kw.lower() for kw in INTENT_KEYWORDS["ambiguous"]]
    
    async def route(
        self,
        question: str,
        context: Optional[dict[str, Any]] = None,
    ) -> IntentRouterOutput:
        """执行意图识别。
        
        三层策略：
        1. L0 规则层：关键词匹配
        2. L1 小模型分类：LLM 判断（可选）
        3. L2 兜底：返回 DATA_QUERY
        
        Args:
            question: 用户问题
            context: 上下文信息（可选）
        
        Returns:
            IntentRouterOutput
        """
        # L0: 规则层
        l0_result = self._try_l0_rules(question)
        if l0_result is not None:
            logger.info(
                f"IntentRouter L0 命中: intent={l0_result.intent_type.value}, "
                f"reason={l0_result.reason}"
            )
            return l0_result
        
        # L1: 小模型分类（可选）
        if self.enable_l1:
            l1_result = await self._try_l1_classifier(question, context)
            if l1_result is not None and l1_result.confidence >= self.l1_confidence_threshold:
                logger.info(
                    f"IntentRouter L1 命中: intent={l1_result.intent_type.value}, "
                    f"confidence={l1_result.confidence:.2f}"
                )
                return l1_result
        
        # L2: 兜底 - 默认当作数据查询处理
        logger.info("IntentRouter L2 兜底: 返回 DATA_QUERY")
        return IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=self.FALLBACK_CONFIDENCE,
            reason="L0 规则未命中，默认进入数据分析流程",
            source="L2_FALLBACK",
        )
    
    def _try_l0_rules(self, question: str) -> Optional[IntentRouterOutput]:
        """L0 规则层 - 关键词匹配（重构版）。
        
        匹配优先级：
        1. 明确无关问题 → IRRELEVANT（高置信度拒绝）
        2. 元数据关键词 → GENERAL
        3. 数据分析关键词 → DATA_QUERY
        4. 未命中 → None（进入下一层）
        
        Args:
            question: 用户问题
        
        Returns:
            IntentRouterOutput 或 None
        """
        question_lower = question.strip().lower()
        
        # 策略模式：按优先级检查
        if result := self._check_irrelevant(question):
            return result
        
        if result := self._check_metadata(question_lower):
            return result
        
        if result := self._check_data_analysis(question_lower):
            return result
        
        return None
    
    def _check_irrelevant(self, question: str) -> Optional[IntentRouterOutput]:
        """检查明确无关问题（正则匹配）。
        
        Args:
            question: 原始问题（保留大小写，用于正则匹配）
        
        Returns:
            IntentRouterOutput 或 None
        """
        for pattern in self._irrelevant_patterns:
            if pattern.search(question):
                return IntentRouterOutput(
                    intent_type=IntentType.IRRELEVANT,
                    confidence=self.HIGH_CONFIDENCE,
                    reason="检测到与数据分析无关的问题",
                    source="L0_RULES",
                )
        return None
    
    def _check_metadata(self, question_lower: str) -> Optional[IntentRouterOutput]:
        """检查元数据关键词。
        
        Args:
            question_lower: 小写化的问题
        
        Returns:
            IntentRouterOutput 或 None
        """
        for keyword in self._metadata_keywords:
            if keyword in question_lower:
                return IntentRouterOutput(
                    intent_type=IntentType.GENERAL,
                    confidence=self.HIGH_CONFIDENCE,
                    reason=f"检测到元数据问答关键词: {keyword}",
                    source="L0_RULES",
                )
        return None
    
    def _check_data_analysis(self, question_lower: str) -> Optional[IntentRouterOutput]:
        """检查数据分析关键词。
        
        Args:
            question_lower: 小写化的问题
        
        Returns:
            IntentRouterOutput 或 None
        """
        matched_keywords = [
            kw for kw in self._data_analysis_keywords
            if kw in question_lower
        ]
        
        if not matched_keywords:
            return None
        
        # 过滤弱关键词
        strong_keywords = self._filter_weak_keywords(matched_keywords)
        
        # 短问题且只有模糊关键词，不匹配
        if not strong_keywords and len(question_lower) < self.SHORT_QUESTION_THRESHOLD:
            return None
        
        # 计算置信度
        confidence = self._calculate_confidence(len(matched_keywords))
        
        return IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=confidence,
            reason=f"检测到数据分析关键词: {', '.join(matched_keywords[:3])}",
            source="L0_RULES",
        )
    
    def _filter_weak_keywords(self, keywords: list[str]) -> list[str]:
        """过滤弱关键词（太短/太模糊的词）。
        
        Args:
            keywords: 匹配到的关键词列表
        
        Returns:
            过滤后的强关键词列表
        """
        return [kw for kw in keywords if kw not in self._ambiguous_keywords]
    
    def _calculate_confidence(self, match_count: int) -> float:
        """根据匹配数量计算置信度。
        
        Args:
            match_count: 匹配的关键词数量
        
        Returns:
            置信度（0-1）
        """
        return min(
            self.BASE_CONFIDENCE + match_count * self.CONFIDENCE_INCREMENT,
            self.MAX_CONFIDENCE
        )
    
    async def _try_l1_classifier(
        self,
        question: str,
        context: Optional[dict[str, Any]],
    ) -> Optional[IntentRouterOutput]:
        """L1 小模型分类 - LLM 判断。
        
        当前版本为占位实现，返回 None。
        后续可接入小模型进行分类。
        
        Args:
            question: 用户问题
            context: 上下文信息
        
        Returns:
            IntentRouterOutput 或 None
        """
        # TODO: 实现 L1 小模型分类
        # Prompt 示例：
        # """
        # 判断以下问题是否与数据分析相关。
        # 
        # 数据分析相关问题示例：
        # - 查询销售额、利润、订单数等指标
        # - 按时间、地区、产品等维度统计
        # - 趋势分析、对比分析、排名等
        # 
        # 问题：{question}
        # 
        # 请回答：
        # - is_data_analysis: true/false
        # - confidence: 0-1
        # - reason: 判断理由
        # """
        
        logger.debug("L1 小模型分类未实现，跳过")
        return None

__all__ = [
    "IntentType",
    "IntentRouterOutput",
    "IntentRouter",
    "METADATA_KEYWORDS",
    "DATA_ANALYSIS_KEYWORDS",
]
