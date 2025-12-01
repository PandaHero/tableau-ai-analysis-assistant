"""
查询构建器包

提供将 Intent 模型转换为 VizQL 查询的功能。

主要组件：
- QueryBuilder: 主协调器，将 QuerySubTask 转换为 VizQLQuery
- IntentConverter: 将 Intent 转换为 VizQLField
- DateFilterConverter: 将 DateFilterIntent 转换为日期筛选器
- FilterConverter: 将 FilterIntent 转换为 VizQLFilter
- StringDateFilterBuilder: 处理 STRING 类型日期字段的筛选器
- build_vizql_query: LangChain 工具

使用示例：
    from tableau_assistant.src.capabilities.query.builder import QueryBuilder, build_vizql_query
    
    # 直接使用 QueryBuilder
    builder = QueryBuilder(metadata=metadata)
    vizql_query = builder.build_query(subtask)
    
    # 使用 LangChain 工具
    result = build_vizql_query(subtask_json, metadata_json)
"""
from tableau_assistant.src.capabilities.query.builder.builder import QueryBuilder
from tableau_assistant.src.capabilities.query.builder.intent_converter import IntentConverter
from tableau_assistant.src.capabilities.query.builder.date_filter_converter import DateFilterConverter
from tableau_assistant.src.capabilities.query.builder.filter_converter import FilterConverter
from tableau_assistant.src.capabilities.query.builder.string_date_filter_builder import StringDateFilterBuilder
from tableau_assistant.src.capabilities.query.builder.tool import build_vizql_query

__all__ = [
    "QueryBuilder",
    "IntentConverter",
    "DateFilterConverter",
    "FilterConverter",
    "StringDateFilterBuilder",
    "build_vizql_query",
]
