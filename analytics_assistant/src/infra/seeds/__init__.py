# -*- coding: utf-8 -*-
"""
Seeds 包 - 领域知识种子数据

本包集中管理所有领域知识数据，与运行时配置（config）分离：
- config: 阈值、超时、开关等运行时参数
- seeds: 关键词、模式、公式等领域知识

目录结构：
- computation.py: 计算公式种子（利润率、同比增长等）
- dimension.py: 维度模式种子（时间、地理、产品等层级）
- keywords/: 关键词类
  - complexity.py: 复杂度检测关键词
  - intent.py: 意图识别关键词
- patterns/: 模式类
  - irrelevant.py: 无关问题检测正则

用法：
    from analytics_assistant.src.infra.seeds import (
        # 计算种子
        COMPUTATION_SEEDS,
        ComputationSeed,
        # 维度种子
        DIMENSION_SEEDS,
        # 关键词
        COMPLEXITY_KEYWORDS,
        INTENT_KEYWORDS,
        # 模式
        IRRELEVANT_PATTERNS,
    )
"""

# 计算种子
from .computation import ComputationSeed, COMPUTATION_SEEDS

# 维度种子
from .dimension import DIMENSION_SEEDS, get_dimension_few_shot_examples

# 度量种子
from .measure import MEASURE_SEEDS, get_measure_few_shot_examples

# 关键词
from .keywords import COMPLEXITY_KEYWORDS, INTENT_KEYWORDS

# 模式
from .patterns import IRRELEVANT_PATTERNS

__all__ = [
    # 计算种子
    "ComputationSeed",
    "COMPUTATION_SEEDS",
    # 维度种子
    "DIMENSION_SEEDS",
    "get_dimension_few_shot_examples",
    # 度量种子
    "MEASURE_SEEDS",
    "get_measure_few_shot_examples",
    # 关键词
    "COMPLEXITY_KEYWORDS",
    "INTENT_KEYWORDS",
    # 模式
    "IRRELEVANT_PATTERNS",
]
