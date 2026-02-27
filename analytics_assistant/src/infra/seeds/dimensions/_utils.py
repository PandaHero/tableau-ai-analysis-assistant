# -*- coding: utf-8 -*-
"""维度种子数据工具函数"""
from dataclasses import replace

from ._types import DimensionSeed

def generate_case_variants(seed: DimensionSeed) -> list[DimensionSeed]:
    """自动生成大小写变体，减少手工维护。

    规则：
    - 纯 ASCII 的 field_caption 才生成变体
    - 小写开头 → 额外生成首字母大写版本
    - 大写开头 → 额外生成全小写版本
    - 中文等非 ASCII 字符不生成变体

    Args:
        seed: 原始种子数据

    Returns:
        包含原始种子及其大小写变体的列表
    """
    variants = [seed]
    caption = seed.field_caption

    # 非 ASCII（中文等）不生成变体
    if not caption.isascii():
        return variants

    if caption[0].islower():
        capitalized = caption[0].upper() + caption[1:]
        if capitalized != caption:
            variants.append(replace(seed, field_caption=capitalized))
    elif caption[0].isupper():
        lowered = caption.lower()
        if lowered != caption:
            variants.append(replace(seed, field_caption=lowered))

    return variants

def expand_seeds(seeds: list[DimensionSeed]) -> list[DimensionSeed]:
    """对种子列表批量展开大小写变体"""
    result = []
    for seed in seeds:
        result.extend(generate_case_variants(seed))
    return result
