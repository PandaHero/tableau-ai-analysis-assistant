# -*- coding: utf-8 -*-
"""
Insight Agent Schema 定义

包含：
- FindingType: 洞察发现类型枚举
- AnalysisLevel: 分析层级枚举
- Finding: 单条洞察发现
- InsightOutput: 洞察输出
- NumericStats: 数值列统计信息
- CategoricalStats: 分类列统计信息
- ColumnProfile: 单列画像
- DataProfile: 数据画像
"""
from .output import (
    AnalysisLevel,
    CategoricalStats,
    ColumnProfile,
    DataProfile,
    Finding,
    FindingType,
    InsightOutput,
    NumericStats,
)

__all__ = [
    "FindingType",
    "AnalysisLevel",
    "Finding",
    "InsightOutput",
    "NumericStats",
    "CategoricalStats",
    "ColumnProfile",
    "DataProfile",
]
