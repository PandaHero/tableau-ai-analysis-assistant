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
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

class IntentType(str, Enum):
    """意图类型枚举（简化版）。
    
    - DATA_QUERY: 数据分析问题（进入语义解析流程）
    - GENERAL: 元数据问答（直接返回字段/数据源信息）
    - IRRELEVANT: 无关问题（礼貌拒绝）
    """
    DATA_QUERY = "DATA_QUERY"
    GENERAL = "GENERAL"
    IRRELEVANT = "IRRELEVANT"


class IntentRouterOutput(BaseModel):
    """IntentRouter 输出模型。
    
    Attributes:
        intent_type: 识别的意图类型
        confidence: 置信度（0-1）
        reason: 识别原因说明
        source: 识别来源（L0_RULES / L1_CLASSIFIER / L2_FALLBACK）
    """
    intent_type: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    source: str = Field(description="识别来源：L0_RULES / L1_CLASSIFIER / L2_FALLBACK")


# ═══════════════════════════════════════════════════════════════════════════
# L0 规则模式 - 正向匹配
# ═══════════════════════════════════════════════════════════════════════════

# 元数据问答关键词（优先级最高）
METADATA_KEYWORDS = [
    # 字段相关
    "有哪些字段", "有什么字段", "字段列表", "字段有哪些",
    "有哪些维度", "有什么维度", "维度列表", "维度有哪些",
    "有哪些度量", "有什么度量", "度量列表", "度量有哪些",
    "有哪些指标", "有什么指标", "指标列表", "指标有哪些",
    # 数据源相关
    "数据源是什么", "数据源叫什么", "数据源名称",
    "数据集是什么", "数据集叫什么", "数据集名称",
    "表是什么", "表叫什么", "表名称", "表名",
    # 元数据查询
    "可以查询什么", "能查询什么", "支持查询什么",
    "可以查哪些", "能查哪些", "支持查哪些",
    "schema", "元数据", "数据结构",
]

# 数据分析关键词（正向匹配）
DATA_ANALYSIS_KEYWORDS = [
    # 度量/指标
    "销售额", "销售量", "销售", "利润", "利润率", "成本", "收入", "金额",
    "数量", "订单", "订单数", "客户数", "用户数", "访问量", "转化率",
    "增长率", "占比", "比例", "平均", "总计", "合计", "累计",
    # 分析动作
    "统计", "查询", "分析", "对比", "比较", "排名", "排序",
    "趋势", "变化", "增长", "下降", "波动",
    "top", "前几", "最高", "最低", "最大", "最小",
    # 时间维度
    "上个月", "本月", "这个月", "上月",
    "上季度", "本季度", "这个季度",
    "去年", "今年", "本年", "上一年",
    "昨天", "今天", "上周", "本周", "这周",
    "同比", "环比", "年度", "季度", "月度", "周度", "日度",
    # 空间/分类维度
    "地区", "区域", "省份", "城市", "国家",
    "部门", "团队", "员工",
    "产品", "品类", "类别", "分类", "品牌",
    "渠道", "来源", "客户", "用户",
    # 聚合/分组
    "按", "分", "各", "每", "group by", "分组",
    # 筛选
    "筛选", "过滤", "条件", "where", "只看", "仅看",
]

# 明确无关的模式（高置信度拒绝）
IRRELEVANT_PATTERNS = [
    # 纯打招呼
    r"^(你好|您好|hi|hello|hey|嗨|哈喽)[\s,，.。!！?？]*$",
    r"^(谢谢|感谢|thanks|thank you)[\s,，.。!！?？]*$",
    r"^(再见|拜拜|bye|goodbye)[\s,，.。!！?？]*$",
    r"^(好的|ok|okay|嗯|哦|明白|知道了|收到)[\s,，.。!！?？]*$",
    # 明确无关话题
    r"(天气|天气预报|气温)",
    r"(讲个笑话|说个笑话|来个笑话)",
    r"(你是谁|你叫什么|介绍.*你自己)",
    r"(帮我写|写一篇|写一个).*(文章|故事|诗|小说)",
    r"(翻译|translate)",
    r"(新闻|热点|头条|八卦)",
    r"(股票|基金|理财|投资建议|炒股)",
    r"(菜谱|食谱|做菜|烹饪)",
    r"(电影|音乐|游戏|小说)推荐",
    r"推荐.*(电影|音乐|游戏|小说|书)",  # 推荐个电影
]

# 太短/太模糊的关键词，需要额外上下文才能判断为数据分析
# 这些词单独出现时不应该匹配
SHORT_AMBIGUOUS_KEYWORDS = [
    "分析", "查询", "统计", "对比", "比较", "变化",
    "按", "分", "各", "每",
]


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
    
    def __init__(
        self,
        l1_confidence_threshold: float = 0.8,
        enable_l1: bool = False,
    ):
        """初始化 IntentRouter。
        
        Args:
            l1_confidence_threshold: L1 置信度阈值
            enable_l1: 是否启用 L1 小模型分类
        """
        self.l1_confidence_threshold = l1_confidence_threshold
        self.enable_l1 = enable_l1
        
        # 编译无关问题正则（性能优化）
        self._irrelevant_patterns = [
            re.compile(p, re.IGNORECASE) for p in IRRELEVANT_PATTERNS
        ]
        
        # 预处理关键词为小写（用于匹配）
        self._metadata_keywords = [kw.lower() for kw in METADATA_KEYWORDS]
        self._data_analysis_keywords = [kw.lower() for kw in DATA_ANALYSIS_KEYWORDS]
    
    async def route(
        self,
        question: str,
        context: Optional[Dict[str, Any]] = None,
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
            confidence=0.5,
            reason="L0 规则未命中，默认进入数据分析流程",
            source="L2_FALLBACK",
        )
    
    def _try_l0_rules(self, question: str) -> Optional[IntentRouterOutput]:
        """L0 规则层 - 关键词匹配。
        
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
        
        # 1. 检查明确无关问题（正则匹配）
        for pattern in self._irrelevant_patterns:
            if pattern.search(question):
                return IntentRouterOutput(
                    intent_type=IntentType.IRRELEVANT,
                    confidence=0.95,
                    reason="检测到与数据分析无关的问题",
                    source="L0_RULES",
                )
        
        # 2. 检查元数据关键词（优先级高于数据分析）
        for keyword in self._metadata_keywords:
            if keyword in question_lower:
                return IntentRouterOutput(
                    intent_type=IntentType.GENERAL,
                    confidence=0.95,
                    reason=f"检测到元数据问答关键词: {keyword}",
                    source="L0_RULES",
                )
        
        # 3. 检查数据分析关键词
        matched_keywords = []
        for keyword in self._data_analysis_keywords:
            if keyword in question_lower:
                matched_keywords.append(keyword)
        
        if matched_keywords:
            # 过滤掉太短/太模糊的关键词（单独出现时不算）
            strong_keywords = [
                kw for kw in matched_keywords 
                if kw not in [k.lower() for k in SHORT_AMBIGUOUS_KEYWORDS]
            ]
            
            # 如果只有模糊关键词，且问题很短，不匹配
            if not strong_keywords and len(question_lower) < 10:
                return None
            
            # 根据匹配数量调整置信度
            confidence = min(0.7 + len(matched_keywords) * 0.1, 0.95)
            return IntentRouterOutput(
                intent_type=IntentType.DATA_QUERY,
                confidence=confidence,
                reason=f"检测到数据分析关键词: {', '.join(matched_keywords[:3])}",
                source="L0_RULES",
            )
        
        # 未命中任何规则
        return None
    
    async def _try_l1_classifier(
        self,
        question: str,
        context: Optional[Dict[str, Any]],
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
    "IRRELEVANT_PATTERNS",
]
