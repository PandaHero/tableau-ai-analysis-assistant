# -*- coding: utf-8 -*-
"""
重排序 Prompt 定义

用于 LLMReranker 的 Prompt 模板。
"""

from typing import List, Any


RERANK_SYSTEM_PROMPT = """你是一个数据分析专家。请根据用户查询中的**核心业务术语**，对以下数据字段按相关性从高到低排序。

排序规则:
1. 只关注查询中的**核心业务术语**（如"销售额"、"省份"、"数量"），忽略时间限定词（"2024"、"去年"）
2. 字段名称或含义与核心业务术语最匹配的排在前面
3. 注意区分：
   - "额"/"金额"/"amt" 表示金额类度量
   - "量"/"数量"/"num"/"qty" 表示数量类度量
   - "率"/"rate" 表示比率类度量
4. 考虑字段角色（dimension/measure）是否符合查询意图

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
        info = f"{i}. {chunk.field_caption}"
        info += f" (角色: {chunk.role}, 类型: {chunk.data_type}"
        if chunk.category:
            info += f", 类别: {chunk.category}"
        info += ")"
        candidate_list.append(info)
    
    return f"""{RERANK_SYSTEM_PROMPT}

用户查询: {query}

候选字段：
{chr(10).join(candidate_list)}
"""
