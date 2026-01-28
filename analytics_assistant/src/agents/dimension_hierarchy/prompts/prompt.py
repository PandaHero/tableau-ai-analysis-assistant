# -*- coding: utf-8 -*-
"""
维度层级推断 Prompt

分为系统提示和用户提示：
- SYSTEM_PROMPT: 定义任务、规则、输出格式
- build_user_prompt(): 构建用户输入（字段列表 + few-shot 示例）
"""
import json
from typing import List, Dict, Any

from analytics_assistant.src.agents.dimension_hierarchy.seed_data import get_seed_few_shot_examples


# ══════════════════════════════════════════════════════════════
# 系统提示
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一个维度层级分析专家，负责推断维度字段的语义属性。

## 任务
分析每个维度字段，推断其：
1. category: 维度类别（time/geography/product/customer/organization/channel/financial/other）
2. category_detail: 详细类别，格式 'category-subcategory'
3. level: 层级 1-5（1 最粗，5 最细）
4. granularity: 粒度描述（coarsest/coarse/medium/fine/finest，与 level 对应）
5. level_confidence: 置信度 0-1

## 层级说明
- Level 1 (coarsest): 最粗粒度，如国家、年份、产品大类、一级渠道
- Level 2 (coarse): 粗粒度，如省份、季度、产品类别、二级渠道
- Level 3 (medium): 中等粒度，如城市、月份、子类别、品牌
- Level 4 (fine): 细粒度，如区县、周、产品名称
- Level 5 (finest): 最细粒度，如地址、日期、SKU、客户ID

## 推断依据
1. 字段名称的语义含义
2. 样例值的特征（如果提供）
3. 唯一值数量（数量越多通常粒度越细）

## 输出格式
返回 JSON 对象，格式如下：
```json
{
  "dimension_hierarchy": {
    "字段1": {
      "category": "geography",
      "category_detail": "geography-province",
      "level": 2,
      "granularity": "coarse",
      "level_confidence": 0.9
    },
    "字段2": {...}
  }
}
```"""


# ══════════════════════════════════════════════════════════════
# 用户提示构建
# ══════════════════════════════════════════════════════════════

def build_user_prompt(
    fields: List[Dict[str, Any]],
    include_few_shot: bool = True,
) -> str:
    """
    构建用户提示
    
    Args:
        fields: 要推断的字段列表
        include_few_shot: 是否包含 few-shot 示例
    
    Returns:
        用户提示字符串
    """
    parts = []
    
    # Few-shot 示例
    if include_few_shot:
        examples = get_seed_few_shot_examples(max_per_category=1)
        if examples:
            parts.append("## 参考示例")
            parts.append("```json")
            for ex in examples:
                # 移除 reasoning 字段，精简输出
                simplified = {k: v for k, v in ex.items() if k != "reasoning"}
                parts.append(json.dumps(simplified, ensure_ascii=False))
            parts.append("```")
    
    # 待分析字段
    fields_info = []
    for f in fields:
        info = {
            "field_caption": f.get("field_caption", f.get("caption", "")),
            "data_type": f.get("data_type", "string"),
        }
        if f.get("sample_values"):
            info["sample_values"] = f["sample_values"][:5]
        if f.get("unique_count") is not None:
            info["unique_count"] = f["unique_count"]
        fields_info.append(info)
    
    parts.append("\n## 待分析字段")
    parts.append("```json")
    parts.append(json.dumps(fields_info, ensure_ascii=False, indent=2))
    parts.append("```")
    parts.append("\n请分析以上字段，返回 dimension_hierarchy JSON。")
    
    return "\n".join(parts)


def build_dimension_inference_prompt(
    fields: List[Dict[str, Any]],
    include_few_shot: bool = True,
) -> str:
    """
    构建完整的维度层级推断 prompt（系统提示 + 用户提示）
    
    Args:
        fields: 要推断的字段列表
        include_few_shot: 是否包含 few-shot 示例
    
    Returns:
        完整的 prompt 字符串
    """
    user_prompt = build_user_prompt(fields, include_few_shot)
    return SYSTEM_PROMPT + "\n\n" + user_prompt


def get_system_prompt() -> str:
    """获取系统提示"""
    return SYSTEM_PROMPT


__all__ = [
    "SYSTEM_PROMPT",
    "build_user_prompt",
    "build_dimension_inference_prompt",
    "get_system_prompt",
]
