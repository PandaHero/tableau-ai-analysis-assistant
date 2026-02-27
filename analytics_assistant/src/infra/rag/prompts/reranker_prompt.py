# -*- coding: utf-8 -*-
"""
重排序 Prompt 定义

用于 LLMReranker 的 Prompt 模板。

优化策略：
1. 引导 LLM 先分解查询中的核心业务术语
2. 提供结构化的候选字段信息（名称、别名、描述、公式、样例值）
3. 明确排序依据的优先级
4. 要求严格的输出格式，便于解析
"""

from typing import Any

RERANK_SYSTEM_PROMPT = """你是数据字段匹配专家。任务：根据用户查询，对候选字段按相关性排序。

## 排序步骤
1. 提取查询中的**核心业务术语**（忽略时间词如"本月"、"去年"、"2024"）
2. 对每个候选字段，判断其与核心术语的匹配程度

## 匹配优先级（从高到低）
1. **别名完全匹配**：字段别名包含核心术语（如查询"销售额"，别名含"销售额"）
2. **业务描述匹配**：描述中包含核心术语的语义
3. **字段名匹配**：字段名或显示名包含核心术语
4. **公式关联**：计算字段的公式引用了相关基础字段
5. **样例值关联**：样例值暗示字段含义（如样例含地名→地区字段）

## 区分易混淆术语
- "额"/"金额"/"收入"/"营收" → 金额类度量
- "量"/"数量"/"件数"/"笔数" → 数量类度量
- "率"/"比率"/"占比" → 比率类度量
- "利润"/"毛利"/"净利" → 利润类度量

## 输出格式
只输出一行：排序后的字段编号，用逗号分隔。
示例: 2,0,4,1,3"""


def build_rerank_prompt(query: str, candidates: list[Any]) -> str:
    """构建重排序提示

    为每个候选字段提供结构化信息，帮助 LLM 准确判断相关性。

    Args:
        query: 用户查询
        candidates: 候选结果列表（RetrievalResult 对象）

    Returns:
        完整的重排序提示
    """
    candidate_lines = []
    for i, c in enumerate(candidates):
        chunk = c.field_chunk
        metadata = chunk.metadata or {}

        # 基本信息行
        line = f"[{i}] {chunk.field_caption}"
        if chunk.field_name != chunk.field_caption:
            line += f" (name: {chunk.field_name})"
        line += f" | {chunk.role} | {chunk.data_type}"

        # 别名
        aliases = metadata.get("aliases")
        if aliases:
            if isinstance(aliases, list):
                aliases_str = ", ".join(str(a) for a in aliases[:5])
            else:
                aliases_str = str(aliases)
            if aliases_str:
                line += f" | 别名: {aliases_str}"

        # 业务描述
        desc = metadata.get("business_description")
        if desc:
            line += f" | 描述: {desc}"

        # 计算字段公式
        formula = chunk.formula or metadata.get("formula")
        if formula:
            formula_display = str(formula).strip().replace("\n", " ")
            if len(formula_display) > 100:
                formula_display = formula_display[:97] + "..."
            line += f" | 公式: {formula_display}"

        # 样例值
        samples = chunk.sample_values
        if not samples:
            samples = metadata.get("sample_values")
        if samples and isinstance(samples, list):
            samples_str = ", ".join(str(s) for s in samples[:5])
            line += f" | 样例: {samples_str}"

        # 度量类别
        measure_cat = metadata.get("measure_category")
        if measure_cat:
            line += f" | 度量类别: {measure_cat}"

        candidate_lines.append(line)

    return f"""{RERANK_SYSTEM_PROMPT}

查询: {query}

候选字段:
{chr(10).join(candidate_lines)}

排序结果:"""
