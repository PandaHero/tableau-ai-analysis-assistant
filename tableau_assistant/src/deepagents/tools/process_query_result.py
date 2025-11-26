"""
Process Query Result Tool - 查询结果处理工具

封装 DataProcessor 组件为 LangChain 工具，用于处理查询结果（同比、环比、增长率、占比等）。

特性：
- 支持多种处理类型（YoY, MoM, Growth Rate, Percentage, Custom）
- 使用 Pandas 进行数据处理
- 完整的错误处理和验证
- 性能监控
"""
import json
import logging
from typing import Dict, Any, List
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def process_query_result(
    subtask_json: str,
    query_results_json: str
) -> Dict[str, Any]:
    """Process query results to calculate derived metrics like YoY, MoM, growth rate, percentage.
    
    This tool takes multiple query results and performs data processing operations
    such as year-over-year comparison, month-over-month comparison, growth rate
    calculation, and percentage calculation.
    
    The tool uses Pandas for data processing and supports various processing types:
    - YoY (Year-over-Year): Compare data across years
    - MoM (Month-over-Month): Compare data across months
    - Growth Rate: Calculate growth rate between periods
    - Percentage: Calculate percentage/proportion
    - Custom: Custom calculations with formulas
    
    Args:
        subtask_json: JSON string of ProcessingSubTask object with fields:
            - question_id: Unique identifier for the processing task
            - question_text: The question text
            - processing_instruction: Processing instruction with:
                - processing_type: Type of processing (yoy, mom, growth_rate, percentage, custom)
                - source_tasks: List of source task IDs
                - calculation_formula: Optional formula for custom calculations
                - parameters: Optional parameters for the processing
        query_results_json: JSON string of query results dictionary.
            Format: {"task_id": {"data": [...], "columns": [...], ...}, ...}
            Each query result should contain:
            - data: List of data rows as dictionaries
            - columns: List of column names
            - row_count: Number of rows
    
    Returns:
        Dictionary with:
            - data: Processed data as list of dictionaries
            - row_count: Number of rows in processed data
            - columns: List of column names
            - processing_type: Type of processing performed
            - source_tasks: List of source task IDs used
            - processing_time_ms: Processing time in milliseconds
            - metadata: Additional metadata including:
                - question_text: The question text
                - calculation_formula: Formula used (if applicable)
    
    Examples:
        # Year-over-Year comparison
        >>> process_query_result(
        ...     subtask_json='{"question_id": "q3", "question_text": "YoY sales growth", '
        ...                  '"processing_instruction": {"processing_type": "yoy", '
        ...                  '"source_tasks": ["q1", "q2"]}}',
        ...     query_results_json='{"q1": {"data": [...], "columns": ["Year", "Sales"]}, '
        ...                       '"q2": {"data": [...], "columns": ["Year", "Sales"]}}'
        ... )
        {"data": [...], "row_count": 10, "processing_type": "yoy", ...}
        
        # Growth rate calculation
        >>> process_query_result(
        ...     subtask_json='{"question_id": "q4", "question_text": "Sales growth rate", '
        ...                  '"processing_instruction": {"processing_type": "growth_rate", '
        ...                  '"source_tasks": ["q1"]}}',
        ...     query_results_json='{"q1": {"data": [...], "columns": ["Month", "Sales"]}}'
        ... )
        {"data": [...], "row_count": 12, "processing_type": "growth_rate", ...}
        
        # Percentage calculation
        >>> process_query_result(
        ...     subtask_json='{"question_id": "q5", "question_text": "Sales percentage by region", '
        ...                  '"processing_instruction": {"processing_type": "percentage", '
        ...                  '"source_tasks": ["q1"]}}',
        ...     query_results_json='{"q1": {"data": [...], "columns": ["Region", "Sales"]}}'
        ... )
        {"data": [...], "row_count": 5, "processing_type": "percentage", ...}
    
    Note:
        - All data processing is done using Pandas DataFrames
        - Input validation ensures all source tasks are present
        - Output validation checks for NaN and Inf values
        - Processing time is monitored and returned
    """
    from tableau_assistant.src.components.data_processor import DataProcessor
    from tableau_assistant.src.models.query_result import QueryResult
    from tableau_assistant.src.models.query_plan import ProcessingSubTask
    
    try:
        # 1. Parse inputs
        subtask_dict = json.loads(subtask_json)
        query_results_dict = json.loads(query_results_json)
        
        # 2. Create model objects
        subtask = ProcessingSubTask(**subtask_dict)
        
        # 3. Convert query results to QueryResult objects
        query_results = {}
        for task_id, result_data in query_results_dict.items():
            query_results[task_id] = QueryResult.from_executor_result(
                task_id=task_id,
                executor_result=result_data
            )
        
        logger.info(
            f"Processing subtask: {subtask.question_id}, "
            f"type: {subtask.processing_instruction.processing_type}, "
            f"sources: {subtask.processing_instruction.source_tasks}"
        )
        
        # 4. Create DataProcessor
        processor = DataProcessor()
        
        # 5. Process the subtask
        result = processor.process_subtask(subtask, query_results)
        
        # 6. Convert result to dictionary
        # Convert Pandas DataFrame to list of dictionaries
        data_list = result.data.to_dict(orient='records')
        
        response = {
            "data": data_list,
            "row_count": result.row_count,
            "columns": result.columns,
            "processing_type": result.processing_type,
            "source_tasks": result.source_tasks,
            "processing_time_ms": result.processing_time_ms,
            "metadata": result.metadata
        }
        
        logger.info(
            f"✅ Processing completed: {subtask.question_id}, "
            f"{result.row_count} rows, {result.processing_time_ms}ms"
        )
        
        return response
    
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON input: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    except Exception as e:
        error_msg = f"Processing failed: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


# 导出
__all__ = ["process_query_result"]
