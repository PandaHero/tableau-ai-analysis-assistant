# -*- coding: utf-8 -*-
"""
FeatureExtractor Prompt 定义

精简 Prompt，目标 ~200 tokens 输入。

Requirements: 3.5
"""

from typing import Any

from ..schemas.prefilter import PrefilterResult

FEATURE_EXTRACTOR_SYSTEM_PROMPT = """你是一个数据分析助手，负责从用户问题中提取字段需求。

任务：
1. 验证规则提取的时间提示是否正确
2. 验证规则匹配的计算类型是否正确
3. 提取用户需要的度量和维度字段（业务术语）

输出 JSON 格式：
{
  "required_measures": ["度量1", "度量2"],
  "required_dimensions": ["维度1", "维度2"],
  "confirmed_time_hints": ["时间表达式1"],
  "confirmed_computations": ["计算种子名称"],
  "confirmation_confidence": 0.9
}

规则：
- required_measures: 用户需要分析的数值指标（如 销售额、利润）
- required_dimensions: 用户需要的所有维度，包括：
  * 分组维度（如 地区、产品）
  * 过滤维度（如 日期、时间）- 特别重要！如果问题涉及时间范围（本月、今年等），必须包含日期维度
- 只输出 JSON，不要其他内容"""

def build_feature_extractor_prompt(
    question: str,
    prefilter_result: PrefilterResult,
) -> str:
    """构建 FeatureExtractor 用户 Prompt。
    
    目标：~200 tokens
    
    Args:
        question: 用户问题
        prefilter_result: 规则预处理结果
        
    Returns:
        用户 Prompt 字符串
    """
    lines = [f"问题: {question}"]
    
    # 添加规则提取的时间提示
    if prefilter_result.time_hints:
        time_hints = [h.original_expression for h in prefilter_result.time_hints]
        lines.append(f"检测到的时间: {', '.join(time_hints)}")
    
    # 添加规则匹配的计算
    if prefilter_result.matched_computations:
        comps = [c.display_name for c in prefilter_result.matched_computations]
        lines.append(f"检测到的计算: {', '.join(comps)}")
    
    # 添加复杂度类型
    if prefilter_result.detected_complexity:
        complexity = [c.value for c in prefilter_result.detected_complexity]
        lines.append(f"复杂度: {', '.join(complexity)}")
    
    lines.append("\n请提取字段需求并验证上述检测结果。")
    
    return "\n".join(lines)

__all__ = [
    "FEATURE_EXTRACTOR_SYSTEM_PROMPT",
    "build_feature_extractor_prompt",
]
