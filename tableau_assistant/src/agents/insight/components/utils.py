# -*- coding: utf-8 -*-
"""
Insight Components Utilities

Common utility functions shared across insight components.

Contains:
- to_dataframe: Convert various data formats to pandas DataFrame
- format_insights_with_index: Format insights list with indices for LLM
"""

import logging
from typing import Any, List, Optional

import pandas as pd

from tableau_assistant.src.agents.insight.models import Insight

logger = logging.getLogger(__name__)


def to_dataframe(data: Any) -> pd.DataFrame:
    """
    Convert various data formats to pandas DataFrame.
    
    Supports:
    - pd.DataFrame: returned as-is
    - List[Dict]: converted to DataFrame
    - List: converted to DataFrame
    - Dict: converted to single-row DataFrame
    
    Args:
        data: Input data in various formats
        
    Returns:
        pd.DataFrame (empty DataFrame if conversion fails)
    """
    if isinstance(data, pd.DataFrame):
        return data
    elif isinstance(data, list):
        if not data:
            return pd.DataFrame()
        if isinstance(data[0], dict):
            return pd.DataFrame(data)
        return pd.DataFrame(data)
    elif isinstance(data, dict):
        return pd.DataFrame([data])
    else:
        logger.warning(f"Unknown data type: {type(data)}, returning empty DataFrame")
        return pd.DataFrame()


def format_insights_with_index(
    insights: List[Insight],
    description_max_len: int = 150,
    include_evidence: bool = True,
) -> str:
    """
    Format insights list with indices for LLM consumption.
    
    Args:
        insights: List of Insight objects
        description_max_len: Maximum length for description truncation
        include_evidence: Whether to include evidence details
        
    Returns:
        Formatted string with indexed insights
    """
    if not insights:
        return "（无历史洞察）"
    
    lines = []
    for i, ins in enumerate(insights):
        lines.append(f"[{i}] [{ins.type}] {ins.title}")
        
        # Truncate description
        desc = ins.description
        if len(desc) > description_max_len:
            desc = desc[:description_max_len] + "..."
        lines.append(f"    描述: {desc}")
        lines.append(f"    重要性: {ins.importance:.2f}")
        
        # Evidence (optional)
        if include_evidence and ins.evidence:
            evidence_parts = []
            if ins.evidence.metric_name:
                evidence_parts.append(f"{ins.evidence.metric_name}={ins.evidence.metric_value}")
            if ins.evidence.ratio:
                evidence_parts.append(f"ratio: {ins.evidence.ratio}")
            if evidence_parts:
                lines.append(f"    证据: {', '.join(evidence_parts)}")
        
        lines.append("")  # Empty line between insights
    
    return "\n".join(lines)


__all__ = [
    "to_dataframe",
    "format_insights_with_index",
]
