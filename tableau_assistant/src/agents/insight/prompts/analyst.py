# -*- coding: utf-8 -*-
"""
Analyst Prompt

Analyst LLM prompt templates for analyzing data chunks.

Contains:
- AnalystPrompt: Basic analyst prompt (simple insights list)
- AnalystPromptWithHistory: Enhanced prompt with historical insight processing

Responsibilities (from design.md):
1. Analyze single data chunk
2. Use overall profile and top_n_summary for context
3. Generate structured insights
4. (WithHistory) Suggest actions for historical insights
"""

from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.agents.insight.models.analyst import (
    AnalystLLMOutput,
    AnalystOutputWithHistory,
)


class AnalystPrompt(VizQLPrompt):
    """
    Basic Analyst LLM Prompt
    
    Responsibilities (from insight-design.md):
    1. Analyze single data chunk
    2. Use overall profile and top_n_summary for context
    3. Generate structured insights
    """
    
    def get_role(self) -> str:
        return "Data analyst who extracts insights from a single data chunk, using overall profile for context."
    
    def get_task(self) -> str:
        return """Analyze the current data chunk and extract meaningful insights.

**IMPORTANT: Focus primarily on the actual data sample provided below.**

Process:
1. **Analyze data sample first** -> Examine actual values, patterns, relationships
2. Understand chunk context -> What type of data is this?
3. Use profile as reference -> Compare findings with overall statistics
4. Extract insights -> Generate 2-5 structured insights based on data evidence"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: **Analyze the actual data sample (PRIMARY FOCUS)**
- Read through the data rows carefully
- Identify specific values, entities, and their relationships
- Look for patterns, outliers, and notable data points

Step 2: Understand chunk context
- What type of data chunk is this?
- What is the business meaning of this data?

Step 3: Use profile as reference (SECONDARY)
- How does this chunk differ from overall statistics?
- Use statistics as comparison baseline

Step 4: Extract insights
- **Each insight MUST reference specific data points from the sample**
- Avoid repeating existing insights"""
    
    def get_constraints(self) -> str:
        return """MUST: Write insights in Chinese, cite specific data points
MUST NOT: Repeat existing insights, invent data not in sample"""
    
    def get_user_template(self) -> str:
        return """## 原始问题
{question}

## 整体数据画像（用于对比）
- 分布类型：{distribution_type}
- 统计信息：{statistics}
- 帕累托比率：{pareto_ratio}

## Top N 数据摘要（用于排名对比）
{top_n_summary}

## 当前数据块
- 类型：{chunk_type}
- 行数：{row_count}
- 描述：{chunk_description}

数据样本：
{data_sample}

## 已有洞察（避免重复）
{existing_insights}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return AnalystLLMOutput


class AnalystPromptWithHistory(VizQLPrompt):
    """
    Enhanced Analyst LLM Prompt with Historical Insight Processing
    
    Responsibilities:
    1. Analyze single data chunk
    2. Use overall profile and top_n_summary for context
    3. Generate NEW insights (not duplicating historical ones)
    4. Suggest actions for each historical insight (KEEP/MERGE/REPLACE/DISCARD)
    
    This prompt is used for progressive insight accumulation where the analyst
    must consider existing insights and suggest how to handle them.
    """
    
    def get_role(self) -> str:
        return "Data analyst who extracts insights from data chunks and manages insight accumulation by suggesting how to handle historical insights."
    
    def get_task(self) -> str:
        return """Analyze the current data chunk and manage insight accumulation.

**TWO RESPONSIBILITIES:**

1. **Extract NEW insights** from current data chunk
   - Only include genuinely new findings
   - Do NOT duplicate historical insights

2. **Suggest actions for EACH historical insight**
   - KEEP: Historical insight is still valid, no changes needed
   - MERGE: Combine historical insight with new information (provide merged_insight)
   - REPLACE: New finding supersedes historical insight (provide replacement_insight)
   - DISCARD: Historical insight is duplicate or invalidated

Process:
1. Analyze data sample -> Find patterns, anomalies, trends
2. Compare with historical insights -> Identify overlaps and new findings
3. Generate new_insights -> Only genuinely new discoveries
4. Generate historical_actions -> One action for EACH historical insight"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: **Analyze the actual data sample**
- Read through the data rows carefully
- Identify specific values, entities, and their relationships
- Look for patterns, outliers, and notable data points

Step 2: **Review historical insights**
- For each historical insight, determine if:
  - It's still valid (KEEP)
  - New data adds detail (MERGE - provide merged insight)
  - New finding supersedes it (REPLACE - provide replacement)
  - It's duplicate or invalidated (DISCARD)

Step 3: **Extract NEW insights**
- Only include findings NOT covered by historical insights
- Each insight MUST reference specific data points
- If a finding overlaps with historical, use MERGE/REPLACE instead

Step 4: **Generate output**
- new_insights: List of genuinely new insights (can be empty)
- historical_actions: One action for EACH historical insight (required)
- analysis_summary: Brief summary of findings
- data_coverage: Estimated cumulative data coverage (0.0-1.0)

**Action Guidelines:**
- KEEP: Use when historical insight is accurate and complete
- MERGE: Use when new data adds detail to historical insight
- REPLACE: Use when new finding is more accurate/complete
- DISCARD: Use when historical insight is wrong or duplicate"""
    
    def get_constraints(self) -> str:
        return """MUST: 
- Write insights in Chinese
- Cite specific data points
- Provide one action for EACH historical insight
- Provide merged_insight when action=MERGE
- Provide replacement_insight when action=REPLACE

MUST NOT:
- Include duplicate insights in new_insights
- Skip any historical insight in historical_actions
- Invent data not in sample"""
    
    def get_user_template(self) -> str:
        return """## 原始问题
{question}

## 整体数据画像（用于对比）
- 分布类型：{distribution_type}
- 统计信息：{statistics}
- 帕累托比率：{pareto_ratio}

## Top N 数据摘要（用于排名对比）
{top_n_summary}

## 当前数据块
- 类型：{chunk_type}
- 行数：{row_count}
- 描述：{chunk_description}

数据样本：
{data_sample}

## 历史洞察（需要处理每一个）
{historical_insights}

## 当前数据覆盖率
已分析数据占比：{current_coverage}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return AnalystOutputWithHistory


ANALYST_PROMPT = AnalystPrompt()
ANALYST_PROMPT_WITH_HISTORY = AnalystPromptWithHistory()


__all__ = [
    "AnalystPrompt",
    "AnalystPromptWithHistory",
    "ANALYST_PROMPT",
    "ANALYST_PROMPT_WITH_HISTORY",
]
