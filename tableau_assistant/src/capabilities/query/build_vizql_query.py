"""
Build VizQL Query Tool - VizQL 查询构建工具

封装 QueryBuilder 组件为 LangChain 工具，用于将 QuerySubTask 转换为 VizQLQuery。
"""
from datetime import datetime
from typing import Optional
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
        subtask_json: JSON string of QuerySubTask object with fields:
            - question_id: Unique identifier for the question
            - question_text: The question text
            - dimension_intents: List of dimension intents
            - measure_intents: List of measure intents
            - date_field_intents: List of date field intents
            - date_filter_intent: Optional date filter intent
            - filter_intents: Optional list of filter intents
            - topn_intent: Optional TopN intent
        metadata_json: JSON string of Metadata object containing:
            - datasource_name: Name of the data source
            - fields: List of field metadata
        anchor_date: Anchor date for relative date calculations (YYYY-MM-DD format).
            If not provided, uses current date - 1 day.
        week_start_day: Week start day (0=Monday, 6=Sunday). Default is 0.
    
    Returns:
        Dictionary with:
            - query: VizQLQuery object as dict with fields and filters
            - field_count: Number of fields in the query
            - filter_count: Number of filters in the query
            - has_date_filter: Whether the query has a date filter
            - has_topn: Whether the query has a TopN filter
    
    Examples:
        # Simple query with dimension and measure
        >>> build_vizql_query(
        ...     subtask_json='{"question_id": "q1", "question_text": "Sales by Region", '
        ...                  '"dimension_intents": [{"business_term": "Region", "technical_field": "Region"}], '
        ...                  '"measure_intents": [{"business_term": "Sales", "technical_field": "Sales", "aggregation": "SUM"}]}',
        ...     metadata_json='{"datasource_name": "Superstore", "fields": [...]}'
        ... )
        {"query": {...}, "field_count": 2, "filter_count": 0, ...}
        
        # Query with date filter
        >>> build_vizql_query(
        ...     subtask_json='{"question_id": "q2", ..., "date_filter_intent": {...}}',
        ...     metadata_json='{"datasource_name": "Superstore", "fields": [...]}',
        ...     anchor_date="2024-12-31"
        ... )
        {"query": {...}, "field_count": 2, "filter_count": 1, "has_date_filter": true, ...}
    """
    import json
    
    # Parse inputs from JSON
    subtask_dict = json.loads(subtask_json)
    metadata_dict = json.loads(metadata_json)
    
    # Create model objects
    subtask = QuerySubTask(**subtask_dict)
    metadata = Metadata(**metadata_dict)
    
    # Parse anchor_date if provided
    anchor_dt = None
    if anchor_date:
        anchor_dt = datetime.strptime(anchor_date, "%Y-%m-%d")
    
    # Create QueryBuilder
    builder = QueryBuilder(
        metadata=metadata,
        anchor_date=anchor_dt,
        week_start_day=week_start_day
    )
    
    # Build query
    vizql_query = builder.build_query(subtask)
    
    # Analyze query
    field_count = len(vizql_query.fields)
    filter_count = len(vizql_query.filters) if vizql_query.filters else 0
    
    # Check for date filter and TopN
    has_date_filter = False
    has_topn = False
    if vizql_query.filters:
        for f in vizql_query.filters:
            # Check if it's a date filter (filterType is "DATE" or "QUANTITATIVE_DATE")
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
