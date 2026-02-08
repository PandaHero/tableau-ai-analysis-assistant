# -*- coding: utf-8 -*-
"""
重排序 Prompt 定义

用于 LLMReranker 的 Prompt 模板。
"""

from typing import List, Any


RERANK_SYSTEM_PROMPT = """你是一个数据分析专家。请根据用户查询中的**核心业务术语**，对以下数据字段按相关性从高到低排序。

排序规则:
1. 只关注查询中的**核心业务术语**（如"销售额"、"省份"、"数量"），忽略时间限定词（"2024"、"去年"）
2. 字段的**别名**和**业务描述**是判断相关性的关键依据，优先级高于字段名
3. 字段名称、别名或业务描述与核心业务术语最匹配的排在前面
4. 注意区分：
   - "额"/"金额"/"amt" 表示金额类度量
   - "量"/"数量"/"num"/"qty" 表示数量类度量
   - "率"/"rate" 表示比率类度量
5. 考虑字段角色（dimension/measure）是否符合查询意图
6. 样例值可辅助判断字段含义（如样例值包含地名则可能是地区字段）

请只返回排序后的字段编号，用逗号分隔。例如: 2,0,1,3"""


def build_rerank_prompt(query: str, candidates: List[Any]) -> str:
    """
    构建重排序提示

    Args:
        query: 用户查询
        candidates: 候选结果列表（RetrievalResult 对象）

    Returns:
        完整的重排序提示
    """
    candidate_list = []
    for i, c in enumerate(candidates):
        chunk = c.field_chunk
        parts = [f"{i}. {chunk.field_caption}"]

        # 基本属性
        attrs = [f"角色: {chunk.role}", f"类型: {chunk.data_type}"]
        if chunk.category:
            attrs.append(f"类别: {chunk.category}")
        parts.append(f"({', '.join(attrs)})")

        # 别名（从 metadata 或 FieldChunk 直接属性获取）
        aliases = chunk.metadata.get("aliases") if chunk.metadata else None
        if aliases:
            if isinstance(aliases, list):
                aliases_str = ", ".join(aliases)
            else:
                aliases_str = str(aliases)
            if aliases_str:
                parts.append(f"  别名: {aliases_str}")

        # 业务描述
        desc = chunk.metadata.get("business_description") if chunk.metadata else None
        if desc:
            parts.append(f"  描述: {desc}")

        # 样例值
        samples = chunk.sample_values
        if not samples and chunk.metadata:
            samples = chunk.metadata.get("sample_values")
        if samples and isinstance(samples, list):
            samples_str = ", ".join(str(s) for s in samples[:5])
            parts.append(f"  样例: {samples_str}")

        candidate_list.append("\n".join(parts))

    return f"""{RERANK_SYSTEM_PROMPT}

用户查询: {query}

候选字段:
{chr(10).join(candidate_list)}
"""
