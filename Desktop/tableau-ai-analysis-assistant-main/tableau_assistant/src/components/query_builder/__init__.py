"""
QueryBuilder模块

模块化的查询构建器，负责将Intent模型转换为VizQL模型。

组件：
- IntentConverter: 转换DimensionIntent/MeasureIntent/DateFieldIntent为VizQLField
- DateFilterConverter: 转换DateFilterIntent为VizQL日期筛选器
- FilterConverter: 转换FilterIntent/TopNIntent为VizQLFilter
- QueryBuilder: 主协调器，组装VizQLQuery
"""
from tableau_assistant.src.components.query_builder.builder import QueryBuilder
from tableau_assistant.src.components.query_builder.intent_converter import IntentConverter
from tableau_assistant.src.components.query_builder.date_filter_converter import DateFilterConverter
from tableau_assistant.src.components.query_builder.filter_converter import FilterConverter

__all__ = [
    "QueryBuilder",
    "IntentConverter",
    "DateFilterConverter",
    "FilterConverter",
]
