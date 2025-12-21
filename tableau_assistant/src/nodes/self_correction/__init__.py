# -*- coding: utf-8 -*-
"""
Self-Correction Node - 查询自我纠错

当 Execute 节点执行失败时，分析错误并尝试修复查询。

架构：
- 分析 VizQL API 返回的错误信息
- 识别常见错误模式（字段不存在、类型不匹配、语法错误等）
- 生成修复建议并重新构建查询
- 最多重试 max_correction_attempts 次

Requirements:
- 基于 MODULE_ARCHITECTURE_DEEP_ANALYSIS.md 中的 Self-Correction 改进建议
"""

from .node import self_correction_node, SelfCorrectionNode
from .corrector import QueryCorrector

__all__ = [
    "self_correction_node",
    "SelfCorrectionNode",
    "QueryCorrector",
]
