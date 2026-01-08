# -*- coding: utf-8 -*-
"""
LLM 维度推断模块

提供维度层级的 LLM 推断功能，作为 RAG 未命中时的兜底方案。

职责：
- 一次性推断维度层级（单次 LLM 调用）
- 构建 few-shot 示例（从种子数据获取）
- 支持流式输出

与 RAG 配合：
- RAG 命中：直接复用缓存结果
- RAG 未命中：调用此模块进行 LLM 推断

Requirements: 1.2
"""
from typing import List, Dict, Any, Optional, Callable
import json
import logging

from tableau_assistant.src.agents.base.node import (
    get_llm,
    invoke_llm,
    stream_llm_call,
    parse_json_response,
)
from tableau_assistant.src.agents.dimension_hierarchy.models import (
    DimensionHierarchyResult,
)
from tableau_assistant.src.agents.dimension_hierarchy.prompt import (
    DIMENSION_HIERARCHY_PROMPT,
)
from .seed_data import get_seed_few_shot_examples

logger = logging.getLogger(__name__)

# 每次推断的最大字段数（防止 prompt 过长）
MAX_FIELDS_PER_INFERENCE = 30


# ═══════════════════════════════════════════════════════════
# Few-shot 构建
# ═══════════════════════════════════════════════════════════

def _build_few_shot_section(
    examples: List[Dict[str, Any]],
    max_examples: int = 6,
) -> str:
    """
    构建 few-shot 示例部分
    
    文案：Reference Examples from seed patterns
    
    Args:
        examples: few-shot 示例列表
        max_examples: 最大示例数
    
    Returns:
        格式化的 few-shot 文本，如果没有示例则返回空字符串
    """
    if not examples:
        return ""
    
    examples = examples[:max_examples]
    
    lines = ["Reference Examples from seed patterns:"]
    lines.append("```json")
    
    for ex in examples:
        example_obj = {
            "field_caption": ex["field_caption"],
            "data_type": ex["data_type"],
            "category": ex["category"],
            "category_detail": ex["category_detail"],
            "level": ex["level"],
            "granularity": ex["granularity"],
        }
        lines.append(json.dumps(example_obj, ensure_ascii=False))
    
    lines.append("```")
    lines.append("")
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# LLM 推断
# ═══════════════════════════════════════════════════════════

async def infer_dimensions_once(
    fields: List[Dict[str, Any]],
    include_few_shot: bool = True,
    stream: bool = False,
    on_token: Optional[Callable[[str], None]] = None,
) -> DimensionHierarchyResult:
    """
    一次性推断维度层级（单次 LLM 调用）
    
    流程：
    1. 构建 few-shot 示例（从种子数据获取）
    2. 格式化字段信息
    3. 调用 LLM 推断
    4. 解析返回结果
    
    Args:
        fields: 要推断的字段列表，每个字段包含：
            - field_name: 字段名
            - field_caption: 字段标题
            - data_type: 数据类型
            - sample_values: 样例值列表（可选）
            - unique_count: 唯一值数量（可选）
        include_few_shot: 是否包含 few-shot 示例
        stream: 是否流式输出
        on_token: 流式输出回调函数
    
    Returns:
        DimensionHierarchyResult 推断结果
    
    Raises:
        ValueError: 字段数超过 MAX_FIELDS_PER_INFERENCE
    
    Example:
        fields = [
            {
                "field_name": "year",
                "field_caption": "年份",
                "data_type": "integer",
                "sample_values": ["2020", "2021", "2022"],
                "unique_count": 5,
            },
        ]
        result = await infer_dimensions_once(fields)
    """
    if not fields:
        return DimensionHierarchyResult(dimension_hierarchy={})
    
    if len(fields) > MAX_FIELDS_PER_INFERENCE:
        raise ValueError(
            f"字段数 {len(fields)} 超过最大限制 {MAX_FIELDS_PER_INFERENCE}，"
            f"请分批调用"
        )
    
    # 1. 构建 few-shot 示例
    few_shot_section = ""
    if include_few_shot:
        # 获取种子数据作为 few-shot 示例（每类别 1 个，共 6 个）
        examples = get_seed_few_shot_examples(max_per_category=1)
        few_shot_section = _build_few_shot_section(examples)
    
    # 2. 格式化字段信息
    dimensions_info = []
    for f in fields:
        dim_info = {
            "field_name": f["field_name"],
            "field_caption": f["field_caption"],
            "data_type": f["data_type"],
        }
        
        # 添加可选字段
        if f.get("sample_values"):
            dim_info["sample_values"] = f["sample_values"][:10]  # 最多 10 个
        if f.get("unique_count") is not None:
            dim_info["unique_count"] = f["unique_count"]
        
        dimensions_info.append(dim_info)
    
    # 3. 构建 prompt 输入
    dimensions_str = json.dumps(dimensions_info, ensure_ascii=False, indent=2)
    if few_shot_section:
        dimensions_str = few_shot_section + dimensions_str
    
    input_data = {"dimensions": dimensions_str}
    
    # 4. 调用 LLM
    try:
        llm = get_llm(agent_name="dimension_hierarchy")
        messages = DIMENSION_HIERARCHY_PROMPT.format_messages(**input_data)
        
        if stream and on_token:
            response = await stream_llm_call(llm, messages, on_token)
        else:
            response = await invoke_llm(llm, messages)
        
        # 5. 解析结果
        result = parse_json_response(response, DimensionHierarchyResult)
        
        logger.info(f"LLM 推断完成: {len(result.dimension_hierarchy)} 个字段")
        return result
        
    except Exception as e:
        logger.error(f"LLM 推断失败: {e}", exc_info=True)
        return DimensionHierarchyResult(dimension_hierarchy={})


__all__ = [
    "MAX_FIELDS_PER_INFERENCE",
    "infer_dimensions_once",
    "_build_few_shot_section",
]
