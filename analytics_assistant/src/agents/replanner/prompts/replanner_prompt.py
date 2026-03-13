# -*- coding: utf-8 -*-
"""Replanner Agent prompt 定义。"""

from __future__ import annotations

import json

from ..schemas.output import ReplanDecision


SYSTEM_PROMPT = """你是一名数据分析重规划专家。

你的任务不是重复总结当前答案，而是判断：
1. 当前分析是否已经足够回答用户问题
2. 如果继续分析，最值得继续的后续问题是什么

输入会同时提供：
- 当前语义任务摘要
- 当前洞察摘要
- 正式 evidence bundle 摘要
- 已经执行过的重规划历史

## 核心判断原则

### 可以继续重规划的场景
- 当前结论仍存在明显未解释的异常、趋势或差异
- 当前 evidence bundle 已经指向一个高价值的后续方向
- 继续分析的预期信息增益明显高于成本
- why / complex 分析里仍存在关键 open questions

### 不应继续重规划的场景
- 当前结论已经足够回答用户问题
- 后续问题与已完成分析高度重复
- 继续分析只会做低价值展开，信息增益很低
- 已经达到多轮重规划上限或明显进入循环

## 候选问题要求
- 候选问题必须具体、可执行、与当前 evidence bundle 有直接关系
- 可以是下钻、对比、验证、补充说明，但不能泛泛而谈
- 严禁生成和历史 follow-up 语义重复的问题
- 候选问题数量控制在 1-3 个

## 输出要求
- 直接输出 JSON
- 必须符合下面的 schema

```json
{output_schema}
```
""".format(
    output_schema=json.dumps(
        ReplanDecision.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )
)

_DEPTH_GUIDANCE = {
    "detailed": (
        "## 分析深度: 标准模式\n"
        "- 只有当后续问题有明确增益时才建议继续\n"
        "- 优先推荐 1 个最有价值的问题\n"
        "- 对重复路径要更保守\n"
    ),
    "comprehensive": (
        "## 分析深度: 深入模式\n"
        "- 可以更积极地探索高价值 follow-up\n"
        "- 允许为 why / complex 问题保留 2-3 个候选方向\n"
        "- 仍然必须避免与历史路径重复\n"
    ),
}


def get_system_prompt() -> str:
    """返回系统提示词。"""
    return SYSTEM_PROMPT


def build_user_prompt(
    insight_summary: str,
    semantic_output_summary: str,
    evidence_bundle_summary: str,
    replan_history_summary: str,
    analysis_depth: str = "detailed",
    field_semantic_summary: str = "",
) -> str:
    """构建用户提示词。"""
    depth_guidance = _DEPTH_GUIDANCE.get(
        analysis_depth,
        _DEPTH_GUIDANCE["detailed"],
    )
    parts = [
        f"## 原始语义任务\n{semantic_output_summary}",
        f"## 当前证据包\n{evidence_bundle_summary}",
        f"## 当前洞察结果\n{insight_summary}",
    ]
    if field_semantic_summary:
        parts.append(
            "## 可用字段范围\n"
            "以下字段来自当前数据源，生成 follow-up 时优先使用这些事实边界：\n"
            f"{field_semantic_summary}"
        )
    if replan_history_summary:
        parts.append(f"## 重规划历史\n{replan_history_summary}")
    parts.append(depth_guidance)
    parts.append(
        "请判断是否需要继续分析，并输出符合 schema 的 JSON。"
        "如果建议继续，优先给出和当前 evidence bundle 最相关的候选问题。"
    )
    return "\n\n".join(parts)


__all__ = [
    "build_user_prompt",
    "get_system_prompt",
]
