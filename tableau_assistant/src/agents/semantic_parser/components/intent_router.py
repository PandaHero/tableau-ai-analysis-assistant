"""IntentRouter 组件 - 两阶段意图识别。

实现三层意图识别策略（从快到慢）：
- L0 规则层（0 LLM 调用）：规则匹配闲聊/元数据/澄清
- L1 小模型分类（1 次低成本调用）：严格 JSON 输出
- L2 Step1 兜底：当 L1 置信度低时返回 DATA_QUERY

设计来源：GPT-5.2 Section 8 - 主流 AI/BI 与 NL2SQL 实践对齐

核心思路：
- 把大量"非数据查询"的请求提前分流，减少 LLM token 与工具调用
- 对 DATA_QUERY 引入"候选约束 + 确定性校验"后，准确率上限更高

Requirements: 0.12 - IntentRouter 意图识别（两阶段路由）
"""

import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from langgraph.types import RunnableConfig

from tableau_assistant.src.infra.observability import get_metrics_from_config
from tableau_assistant.src.infra.config.settings import settings


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

class IntentType(str, Enum):
    """意图类型枚举。
    
    - DATA_QUERY: 数据查询（进入重路径：Schema Linking + Step1）
    - CLARIFICATION: 需要澄清（返回澄清请求）
    - GENERAL: 元数据问答（直接回答）
    - IRRELEVANT: 无关问题（礼貌拒绝）
    """
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"
    IRRELEVANT = "IRRELEVANT"


class IntentRouterOutput(BaseModel):
    """IntentRouter 输出模型。
    
    Attributes:
        intent_type: 识别的意图类型
        confidence: 置信度（0-1）
        reason: 识别原因说明
        source: 识别来源（L0/L1/L2）
        need_clarify_slots: 需要澄清的槽位列表（仅 CLARIFICATION 时有值）
    """
    intent_type: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    source: str = Field(description="识别来源：L0_RULES / L1_CLASSIFIER / L2_FALLBACK")
    need_clarify_slots: Optional[List[str]] = None


# ═══════════════════════════════════════════════════════════════════════════
# L0 规则模式
# ═══════════════════════════════════════════════════════════════════════════

# 闲聊/打招呼模式
GREETING_PATTERNS = [
    r"^(你好|您好|hi|hello|hey|嗨|哈喽|早上好|下午好|晚上好|早安|晚安)[\s,，.。!！?？]*$",
    r"^(谢谢|感谢|thanks|thank you|thx)[\s,，.。!！?？]*$",
    r"^(再见|拜拜|bye|goodbye|see you)[\s,，.。!！?？]*$",
    r"^(好的|ok|okay|嗯|哦|明白了|知道了|收到)[\s,，.。!！?？]*$",
]

# 无关问题模式（与数据分析无关的知识问答）
IRRELEVANT_PATTERNS = [
    r"(今天天气|天气怎么样|天气预报)",
    r"(讲个笑话|说个笑话|来个笑话)",
    r"(你是谁|你叫什么|介绍一下你自己)",
    r"(帮我写|写一篇|写一个)(文章|故事|诗|代码|程序)",
    r"(翻译|translate)",
    r"(新闻|热点|头条)",
    r"(股票|基金|理财|投资建议)",
    r"(菜谱|食谱|怎么做菜)",
]

# 元数据问答模式
METADATA_PATTERNS = [
    r"(有哪些|有什么|列出|显示|查看)(字段|维度|度量|指标|列|属性)",
    r"(数据源|数据集|表)(是什么|叫什么|名称|名字)",
    r"(字段|维度|度量|指标)(有哪些|列表|清单)",
    r"(schema|结构|元数据)(是什么|有哪些)",
    r"(可以查询|能查询|支持查询)(什么|哪些)",
    r"(数据|字段)(类型|格式)(是什么|有哪些)",
]

# 需要澄清的模式（问题太模糊）
VAGUE_PATTERNS = [
    r"^(帮我|请|麻烦)(分析|看看|查一下|查询)[\s,，.。!！?？]*$",
    r"^(分析一下|看一下|查一下)[\s,，.。!！?？]*$",
    r"^(数据|报表|报告)[\s,，.。!！?？]*$",
    r"^(怎么样|如何|情况)[\s,，.。!！?？]*$",
]


# ═══════════════════════════════════════════════════════════════════════════
# IntentRouter 组件
# ═══════════════════════════════════════════════════════════════════════════

class IntentRouter:
    """意图识别器 - 三层策略。
    
    实现三层意图识别策略（从快到慢）：
    - L0 规则层（0 LLM 调用）：规则匹配
    - L1 小模型分类（1 次低成本调用）：严格 JSON 输出
    - L2 Step1 兜底：当 L1 置信度低时返回 DATA_QUERY
    
    Attributes:
        l1_confidence_threshold: L1 置信度阈值（默认 0.8）
        enable_l1: 是否启用 L1 小模型分类（默认 False，当前版本仅实现 L0）
    
    Requirements: 0.12 - IntentRouter 意图识别（两阶段路由）
    """
    
    def __init__(
        self,
        l1_confidence_threshold: float = settings.intent_router_l1_confidence_threshold,
        enable_l1: bool = False,
    ):
        """初始化 IntentRouter。
        
        Args:
            l1_confidence_threshold: L1 置信度阈值
            enable_l1: 是否启用 L1 小模型分类
        """
        self.l1_confidence_threshold = l1_confidence_threshold
        self.enable_l1 = enable_l1
        
        # 编译正则表达式（性能优化）
        self._greeting_patterns = [re.compile(p, re.IGNORECASE) for p in GREETING_PATTERNS]
        self._irrelevant_patterns = [re.compile(p, re.IGNORECASE) for p in IRRELEVANT_PATTERNS]
        self._metadata_patterns = [re.compile(p, re.IGNORECASE) for p in METADATA_PATTERNS]
        self._vague_patterns = [re.compile(p, re.IGNORECASE) for p in VAGUE_PATTERNS]
    
    async def route(
        self,
        question: str,
        context: Optional[Dict[str, Any]] = None,
        config: Optional[RunnableConfig] = None,
    ) -> IntentRouterOutput:
        """执行意图识别。
        
        三层策略：
        1. L0 规则层：0 LLM 调用，规则匹配
        2. L1 小模型分类：1 次低成本调用（可选）
        3. L2 Step1 兜底：返回 DATA_QUERY
        
        Args:
            question: 用户问题
            context: 上下文信息（可选）
            config: RunnableConfig（用于获取 metrics）
        
        Returns:
            IntentRouterOutput 包含意图类型、置信度、原因等
        """
        metrics = get_metrics_from_config(config)
        
        # L0: 规则层（0 LLM 调用）
        l0_result = self._try_l0_rules(question)
        if l0_result is not None:
            logger.info(
                f"IntentRouter L0 命中: intent={l0_result.intent_type.value}, "
                f"reason={l0_result.reason}"
            )
            metrics.intent_router_l0_hit_count += 1
            return l0_result
        
        # L1: 小模型分类（可选，当前版本默认禁用）
        if self.enable_l1:
            # ⚠️ 修复（Requirements 0.12）：记录 L1 调用次数（用于计算调用率）
            metrics.intent_router_l1_call_count += 1
            
            l1_result = await self._try_l1_classifier(question, context, config)
            if l1_result is not None and l1_result.confidence >= self.l1_confidence_threshold:
                logger.info(
                    f"IntentRouter L1 命中: intent={l1_result.intent_type.value}, "
                    f"confidence={l1_result.confidence:.2f}"
                )
                metrics.intent_router_l1_hit_count += 1
                return l1_result
        
        # L2: Step1 兜底
        logger.info("IntentRouter L2 兜底: 返回 DATA_QUERY")
        metrics.intent_router_l2_fallback_count += 1
        
        return IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=0.5,
            reason="L0 规则未命中，L1 未启用或置信度不足，进入 Step1 兜底",
            source="L2_FALLBACK",
        )
    
    def _try_l0_rules(self, question: str) -> Optional[IntentRouterOutput]:
        """L0 规则层 - 0 LLM 调用。
        
        规则优先级：
        1. 闲聊/打招呼 → IRRELEVANT
        2. 无关问题 → IRRELEVANT
        3. 元数据问答 → GENERAL
        4. 问题太模糊 → CLARIFICATION
        
        Args:
            question: 用户问题
        
        Returns:
            IntentRouterOutput 或 None（未命中）
        """
        question_stripped = question.strip()
        
        # 1. 闲聊/打招呼检测
        for pattern in self._greeting_patterns:
            if pattern.search(question_stripped):
                return IntentRouterOutput(
                    intent_type=IntentType.IRRELEVANT,
                    confidence=1.0,
                    reason="检测到打招呼或闲聊",
                    source="L0_RULES",
                )
        
        # 2. 无关问题检测
        for pattern in self._irrelevant_patterns:
            if pattern.search(question_stripped):
                return IntentRouterOutput(
                    intent_type=IntentType.IRRELEVANT,
                    confidence=0.95,
                    reason="检测到与数据分析无关的问题",
                    source="L0_RULES",
                )
        
        # 3. 元数据问答检测
        for pattern in self._metadata_patterns:
            if pattern.search(question_stripped):
                return IntentRouterOutput(
                    intent_type=IntentType.GENERAL,
                    confidence=1.0,
                    reason="检测到元数据问答",
                    source="L0_RULES",
                )
        
        # 4. 问题太模糊检测
        for pattern in self._vague_patterns:
            if pattern.search(question_stripped):
                return IntentRouterOutput(
                    intent_type=IntentType.CLARIFICATION,
                    confidence=0.9,
                    reason="问题太模糊，需要更多信息",
                    source="L0_RULES",
                    need_clarify_slots=["object", "measure", "dimension"],
                )
        
        # 未命中任何规则
        return None
    
    async def _try_l1_classifier(
        self,
        question: str,
        context: Optional[Dict[str, Any]],
        config: Optional[RunnableConfig],
    ) -> Optional[IntentRouterOutput]:
        """L1 小模型分类 - 1 次低成本 LLM 调用。
        
        当前版本为占位实现，返回 None。
        后续可接入小模型（如 GPT-3.5-turbo）进行分类。
        
        Args:
            question: 用户问题
            context: 上下文信息
            config: RunnableConfig
        
        Returns:
            IntentRouterOutput 或 None
        """
        # TODO: 实现 L1 小模型分类
        # 1. 构建分类 prompt
        # 2. 调用小模型（如 GPT-3.5-turbo）
        # 3. 解析 JSON 输出
        # 4. 返回 IntentRouterOutput
        
        logger.debug("L1 小模型分类未实现，跳过")
        return None


__all__ = [
    "IntentType",
    "IntentRouterOutput",
    "IntentRouter",
    "GREETING_PATTERNS",
    "IRRELEVANT_PATTERNS",
    "METADATA_PATTERNS",
    "VAGUE_PATTERNS",
]
