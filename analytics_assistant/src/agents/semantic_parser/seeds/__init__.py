# -*- coding: utf-8 -*-
"""
Seeds 包 - 种子数据和规则匹配器

本包提供语义解析器的规则匹配逻辑。

种子数据已迁移到 infra/seeds/ 包，本包重新导出以保持兼容：
- COMPUTATION_SEEDS: 计算公式种子
- COMPLEXITY_KEYWORDS: 复杂度检测关键词
- INTENT_KEYWORDS: 意图识别关键词
- IRRELEVANT_PATTERNS: 无关问题检测正则

规则匹配器（matchers/）：
- computation_matcher.py: 计算种子匹配
- complexity_detector.py: 复杂度检测
- intent_matcher.py: 意图匹配

用法：
    from analytics_assistant.src.agents.semantic_parser.seeds import (
        # 种子数据（从 infra/seeds 重新导出）
        COMPUTATION_SEEDS,
        COMPLEXITY_KEYWORDS,
        INTENT_KEYWORDS,
        IRRELEVANT_PATTERNS,
        ComputationSeed,
        # 匹配器
        ComputationMatcher,
        ComplexityDetector,
        IntentMatcher,
    )
"""

# 种子数据（从 infra/seeds 导入）
from analytics_assistant.src.infra.seeds import (
    ComputationSeed,
    COMPUTATION_SEEDS,
    COMPLEXITY_KEYWORDS,
    INTENT_KEYWORDS,
    IRRELEVANT_PATTERNS,
)

# 匹配器
from .matchers import ComputationMatcher, ComplexityDetector, IntentMatcher

__all__ = [
    # 种子数据
    "ComputationSeed",
    "COMPUTATION_SEEDS",
    "COMPLEXITY_KEYWORDS",
    "INTENT_KEYWORDS",
    "IRRELEVANT_PATTERNS",
    # 匹配器
    "ComputationMatcher",
    "ComplexityDetector",
    "IntentMatcher",
]
