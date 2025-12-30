# -*- coding: utf-8 -*-
"""
Director Prompt

Analysis Director LLM prompt template.

Responsibilities:
1. Review enhanced data profile (Tableau Pulse-style insights)
2. Process analyst's output and execute insight actions
3. Decide what to analyze next (chunk/dimension/anomaly)
4. Generate final summary when stopping
"""

from typing import Type
from pydantic import BaseModel

from tableau_assistant.src.agents.base.prompt import VizQLPrompt
from tableau_assistant.src.agents.insight.models.director import DirectorOutputWithAccumulation


class DirectorPrompt(VizQLPrompt):
    """
    Director LLM Prompt
    
    Responsibilities:
    1. Review Tableau Pulse-style data profile summary
    2. Process analyst's output (new insights + historical action suggestions)
    3. Execute insight actions (KEEP/MERGE/REPLACE/DISCARD)
    4. Decide next analysis action
    5. Generate comprehensive final summary when stopping
    """
    
    def get_role(self) -> str:
        return "Analysis director who orchestrates progressive data analysis, manages insight accumulation, and generates comprehensive summaries."
    
    def get_task(self) -> str:
        return """Process analyst output, manage insight accumulation, and decide next steps.

**THREE RESPONSIBILITIES:**

1. **Execute insight actions** based on analyst suggestions
   - Review analyst's historical_actions for each existing insight
   - Execute: KEEP (no change), MERGE (combine), REPLACE (update), DISCARD (remove)
   - Add analyst's new_insights to accumulation

2. **Decide next action**
   - Evaluate if core question is answered
   - Identify high-value remaining targets
   - Choose: analyze_chunk, analyze_dimension, analyze_anomaly, or stop

3. **Generate final summary** (when stopping)
   - Comprehensive summary answering user's question
   - Reference key insights and evidence
   - Written in Chinese

Process:
1. Process analyst output -> Execute insight actions
2. Update accumulated_insights -> Apply MERGE/REPLACE/DISCARD, add new insights
3. Assess completeness -> Is core question answered?
4. Decide next action -> Continue or Stop
5. If stopping -> Generate final_summary"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: **Process analyst's historical_actions**
For each action in analyst's suggestions:
- KEEP: Keep insight unchanged in accumulated_insights
- MERGE: Use analyst's merged_insight to replace original
- REPLACE: Use analyst's replacement_insight to replace original
- DISCARD: Remove insight from accumulated_insights

Step 2: **Add new insights**
- Add all insights from analyst's new_insights to accumulated_insights
- These are genuinely new findings not covered by historical insights

Step 3: **Assess completeness**
- Do accumulated insights answer the user's core question?
- What aspects are still missing?
- How confident are we? (completeness, confidence scores)

Step 4: **Decide next action**
- If question_answered=True with high confidence -> STOP
- If high-value targets remain -> CONTINUE
- If max iterations reached -> STOP

Step 5: **Generate final_summary** (if stopping)
- Comprehensive answer to user's question
- Reference specific insights and evidence
- Written in Chinese
- Structure: 核心发现 → 关键洞察 → 建议/结论

**Decision Priority:**
1. Anomalies (if anomaly_ratio > 10%) -> analyze_anomaly
2. High concentration dimensions -> analyze_dimension
3. Unanalyzed high-priority chunks -> analyze_chunk
4. Stop when question answered or no valuable targets"""
    
    def get_constraints(self) -> str:
        return """MUST:
- Execute ALL analyst's historical_actions
- Add ALL analyst's new_insights
- Generate final_summary in Chinese when stopping
- Provide accumulated_insights after processing

MUST NOT:
- Skip any analyst suggestion
- Lose insights during processing
- Stop without final_summary
- Continue indefinitely without progress
- Analyze data directly (that's the analyst's job)"""
    
    def get_user_template(self) -> str:
        return """## 用户问题
{user_question}

## 数据画像摘要（Tableau Pulse 风格）
{profile_summary}

## 分析师输出（需要处理）

### 新发现的洞察
{analyst_new_insights}

### 历史洞察处理建议
{analyst_historical_actions}

## 当前累积洞察（处理前）
{current_insights}

## 可用分析目标
{available_targets}

## 已分析目标
{analyzed_targets}

## 分析进度
- 当前迭代: {iteration_count} / {max_iterations}
- 已分析块数: {analyzed_count}
- 数据覆盖率: {data_coverage}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return DirectorOutputWithAccumulation


DIRECTOR_PROMPT = DirectorPrompt()


__all__ = [
    "DirectorPrompt",
    "DIRECTOR_PROMPT",
]
