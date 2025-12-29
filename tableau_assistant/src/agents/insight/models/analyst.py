# -*- coding: utf-8 -*-
"""Analyst Models.

Data models for the Chunk Analyst (分析师) LLM.

Contains:
- HistoricalInsightAction: Analyst's suggestion for handling historical insights
- AnalystOutputWithHistory: Analyst output with historical insight processing suggestions
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from enum import Enum

from .insight import Insight


class HistoricalInsightActionType(str, Enum):
    """Action type for historical insight processing.
    
    <rule>
    - KEEP: Keep the historical insight as-is (no change needed)
    - MERGE: Merge with a new insight (combine information)
    - REPLACE: Replace with a new/updated insight (new finding supersedes)
    - DISCARD: Discard the historical insight (duplicate or invalidated)
    </rule>
    """
    KEEP = "KEEP"
    MERGE = "MERGE"
    REPLACE = "REPLACE"
    DISCARD = "DISCARD"


class HistoricalInsightAction(BaseModel):
    """Analyst's suggestion for handling a historical insight.
    
    <what>Analyst suggests how to handle each historical insight based on new findings</what>
    
    <fill_order>
    1. historical_index (ALWAYS)
    2. action (ALWAYS)
    3. reason (ALWAYS)
    4. merged_insight (if action = MERGE)
    5. replacement_insight (if action = REPLACE)
    </fill_order>
    
    <examples>
    Keep: {"historical_index": 0, "action": "KEEP", "reason": "Still valid, no new information"}
    Merge: {"historical_index": 1, "action": "MERGE", "reason": "New data adds detail", "merged_insight": {...}}
    Replace: {"historical_index": 2, "action": "REPLACE", "reason": "New finding supersedes", "replacement_insight": {...}}
    Discard: {"historical_index": 3, "action": "DISCARD", "reason": "Duplicate of insight at index 0"}
    </examples>
    
    <anti_patterns>
    X action=MERGE but merged_insight is null
    X action=REPLACE but replacement_insight is null
    X historical_index out of range
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    historical_index: int = Field(
        description="""<what>Index of the historical insight being processed</what>
<when>ALWAYS required</when>
<rule>Must be a valid index in the historical insights list</rule>"""
    )
    action: HistoricalInsightActionType = Field(
        description="""<what>Suggested action for this historical insight</what>
<when>ALWAYS required</when>"""
    )
    reason: str = Field(
        description="""<what>Reason for the suggested action</what>
<when>ALWAYS required</when>
<rule>Explain why this action is appropriate based on new findings</rule>"""
    )
    merged_insight: Optional[Insight] = Field(
        default=None,
        description="""<what>Merged insight combining historical and new information</what>
<when>action = MERGE</when>
<dependency>action == MERGE</dependency>
<rule>Should combine the best of both historical and new insights</rule>"""
    )
    replacement_insight: Optional[Insight] = Field(
        default=None,
        description="""<what>New insight to replace the historical one</what>
<when>action = REPLACE</when>
<dependency>action == REPLACE</dependency>
<rule>Should be a more accurate or complete insight</rule>"""
    )


class AnalystOutputWithHistory(BaseModel):
    """Analyst output with historical insight processing suggestions.
    
    <what>Analyst output including new insights and suggestions for historical insights</what>
    
    <fill_order>
    1. new_insights (ALWAYS, can be empty)
    2. historical_actions (ALWAYS, one for each historical insight)
    3. analysis_summary (ALWAYS)
    4. data_coverage (ALWAYS)
    </fill_order>
    
    <examples>
    With new insights: {
        "new_insights": [{"type": "trend", "title": "...", ...}],
        "historical_actions": [{"historical_index": 0, "action": "KEEP", ...}],
        "analysis_summary": "Found new trend in sales data",
        "data_coverage": 0.3
    }
    No new insights: {
        "new_insights": [],
        "historical_actions": [{"historical_index": 0, "action": "KEEP", ...}],
        "analysis_summary": "No new findings in this chunk",
        "data_coverage": 0.4
    }
    </examples>
    
    <anti_patterns>
    X historical_actions length != historical insights length
    X new_insights duplicates historical insights without REPLACE action
    </anti_patterns>
    """
    model_config = ConfigDict(extra="forbid")
    
    new_insights: List[Insight] = Field(
        default_factory=list,
        description="""<what>New insights discovered from current chunk</what>
<when>ALWAYS required (can be empty)</when>
<rule>Only include genuinely new findings not covered by historical insights</rule>
<must_not>Include insights that duplicate historical ones without suggesting REPLACE</must_not>"""
    )
    historical_actions: List[HistoricalInsightAction] = Field(
        default_factory=list,
        description="""<what>Suggested actions for each historical insight</what>
<when>ALWAYS required</when>
<rule>Must have one action for each historical insight provided</rule>"""
    )
    analysis_summary: str = Field(
        description="""<what>Brief summary of the analysis</what>
<when>ALWAYS required</when>
<rule>Summarize what was found in this chunk and how it relates to historical insights</rule>"""
    )
    data_coverage: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="""<what>Estimated data coverage after this analysis</what>
<when>ALWAYS required</when>
<rule>Cumulative percentage of data analyzed so far</rule>"""
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="""<what>Confidence in the analysis</what>
<when>ALWAYS required</when>
<rule>Based on data quality and analysis depth</rule>"""
    )
    needs_further_analysis: bool = Field(
        default=True,
        description="""<what>Whether more analysis is recommended</what>
<when>ALWAYS required</when>
<rule>True if important aspects remain unexplored</rule>"""
    )
    suggested_next_focus: Optional[str] = Field(
        default=None,
        description="""<what>Suggested focus for next analysis</what>
<when>If needs_further_analysis = True</when>
<rule>E.g., "Investigate anomalies in Region X" or "Analyze time trend"</rule>"""
    )


__all__ = [
    "HistoricalInsightActionType",
    "HistoricalInsightAction",
    "AnalystOutputWithHistory",
]
