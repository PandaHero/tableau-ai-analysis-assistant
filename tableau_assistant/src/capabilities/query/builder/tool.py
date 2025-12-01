"""
Build VizQL Query Tool - VizQL 查询构建工具

封装 QueryBuilder 组件为 LangChain 工具，用于将 QuerySubTask 转换为 VizQLQuery。
"""
from datetime import datetime
from typing import Optional
import json
from langchain_core.tools import tool

from tableau_assistant.src.capabilities.query.builder.builder import QueryBuilder
from tableau_assistant.src.models.query_plan import QuerySubTask
from tableau_assistant.src.models.metadata import Metadata


@tool
def build_vizql_query(
    subtask_json: str,
    metadata_json: str,
    anchor_date: Optional[str] = None,
    week_start_day: int = 0
) -> dict:
    """Build a VizQL query from a QuerySubTask.
    
    This tool converts a QuerySubTask (containing Intent models) into a VizQLQuery
    (containing VizQL models) that can be executed against Tableau.
    
    The tool handles:
    - Converting dimension/measure/date field intents to VizQL fields
    - Converting filter intents to VizQL filters
    - Converting date filter intents to VizQL date filters
    - Converting TopN intents to VizQL TopN filters
    - Handling STRING-type date fields with DATEPARSE
    - Assigning sort priorities
    
    Args:
        subtask_json: JSON string of QuerySubTask object
        metadata_json: JSON string of Metadata object
        anchor_date: Anchor date for relative date calculations (YYYY-MM-DD format)
        week_start_day: Week start day (0=Monday, 6=Sunday). Default is 0.
    
    Returns:
        Dictionary with query, field_count, filter_count, has_date_filter, has_topn
    """
    subtask_dict = json.loads(subtask_json)
    metadata_dict = json.loads(metadata_json)
    
    subtask = QuerySubTask(**subtask_dict)
    metadata = Metadata(**metadata_dict)
    
    anchor_dt = None
    if anchor_date:
        anchor_dt = datetime.strptime(anchor_date, "%Y-%m-%d")
    
    builder = QueryBuilder(
        metadata=metadata,
        anchor_date=anchor_dt,
        week_start_day=week_start_day
    )
    
    vizql_query = builder.build_query(subtask)
    
    field_count = len(vizql_query.fields)
    filter_count = len(vizql_query.filters) if vizql_query.filters else 0
    
    has_date_filter = False
    has_topn = False
    if vizql_query.filters:
        for f in vizql_query.filters:
            if hasattr(f, 'filterType'):
                if f.filterType in ["DATE", "QUANTITATIVE_DATE"]:
                    has_date_filter = True
                elif f.filterType == "TOP":
                    has_topn = True
    
    return {
        "query": vizql_query.model_dump(exclude_none=True),
        "field_count": field_count,
        "filter_count": filter_count,
        "has_date_filter": has_date_filter,
        "has_topn": has_topn
    }


__all__ = ["build_vizql_query"]
