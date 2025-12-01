"""
Data Processing Tools - 数据处理工具

封装数据处理组件为 LangChain 工具。

工具列表：
- detect_statistics: 统计检测工具
- process_query_result: 查询结果处理工具
"""
import json
import logging
from typing import Dict, Any
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def detect_statistics(
    data_json: str,
    z_score_threshold: float = 3.0,
    iqr_multiplier: float = 1.5,
    include_basic_stats: bool = True,
    include_anomalies: bool = True,
    include_trends: bool = True,
    include_correlations: bool = True,
    include_distributions: bool = True,
    include_data_quality: bool = True
) -> Dict[str, Any]:
    """Detect statistical patterns and anomalies in data for insight analysis.
    
    This tool performs comprehensive statistical analysis on query results to identify:
    - Basic statistics (min, max, mean, median, std, quartiles)
    - Anomalies using Z-score and IQR methods
    - Trends using linear regression
    - Correlations between numeric columns
    - Distribution characteristics (skewness, kurtosis, normality)
    - Data quality metrics (completeness, consistency, validity)
    
    Args:
        data_json: JSON string of data to analyze
        z_score_threshold: Z-score threshold for anomaly detection (default: 3.0)
        iqr_multiplier: IQR multiplier for anomaly detection (default: 1.5)
        include_basic_stats: Whether to compute basic statistics (default: True)
        include_anomalies: Whether to detect anomalies (default: True)
        include_trends: Whether to detect trends (default: True)
        include_correlations: Whether to detect correlations (default: True)
        include_distributions: Whether to analyze distributions (default: True)
        include_data_quality: Whether to assess data quality (default: True)
    
    Returns:
        Dictionary with statistical analysis results
    """
    import pandas as pd
    from tableau_assistant.src.capabilities.data_processing.statistics import StatisticsDetector
    
    try:
        data = json.loads(data_json)
        
        if isinstance(data, dict) and "data" in data:
            df = pd.DataFrame(data["data"])
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            raise ValueError("Invalid data format")
        
        if df.empty:
            raise ValueError("Empty dataset provided")
        
        detector = StatisticsDetector(
            z_score_threshold=z_score_threshold,
            iqr_multiplier=iqr_multiplier
        )
        
        results = {}
        
        if include_basic_stats:
            results["basic_stats"] = detector.compute_basic_stats(df)
        if include_anomalies:
            results["anomalies"] = detector.detect_anomalies(df)
        if include_trends:
            results["trends"] = detector.detect_trends(df)
        if include_correlations:
            results["correlations"] = detector.detect_correlations(df)
        if include_distributions:
            results["distributions"] = detector.analyze_distributions(df)
        if include_data_quality:
            results["data_quality"] = detector.assess_data_quality(df)
        
        results["summary"] = {
            "row_count": len(df),
            "column_count": len(df.columns)
        }
        
        logger.info(f"✅ Statistics detection completed")
        return results
    
    except Exception as e:
        logger.error(f"Statistics detection failed: {e}")
        raise


@tool
def process_query_result(
    subtask_json: str,
    result_json: str,
    processing_type: str = "default"
) -> Dict[str, Any]:
    """Process query results for further analysis.
    
    This tool processes raw query results and prepares them for insight generation.
    It supports various processing types including YoY, MoM, growth rate calculations.
    
    For complex processing (yoy, mom, growth_rate, percentage, custom), this tool
    uses the DataProcessor with ProcessingSubTask. For simple processing, it
    performs basic data transformation.
    
    Args:
        subtask_json: JSON string of the subtask containing:
            - question_id: Task identifier
            - question_text: Task description
            - For complex processing: processing_instruction with processing_type and source_tasks
        result_json: JSON string of the query result containing:
            - data: List of data rows
            - row_count: Number of rows
            - columns: List of column names
        processing_type: Type of processing to apply:
            - "default": Return data as-is with basic formatting
            - "yoy": Year-over-year calculation (requires DataProcessor)
            - "mom": Month-over-month calculation (requires DataProcessor)
            - "growth_rate": Growth rate calculation (requires DataProcessor)
            - "percentage": Percentage calculation (requires DataProcessor)
            - "custom": Custom calculation (requires DataProcessor)
    
    Returns:
        Dictionary with:
            - question_id: Task identifier
            - processing_type: Type of processing applied
            - data: Processed data (list of dicts)
            - row_count: Number of rows
            - columns: List of column names
    """
    import pandas as pd
    from tableau_assistant.src.capabilities.data_processing.processor import DataProcessor
    from tableau_assistant.src.models.query_result import QueryResult, ProcessingResult
    from tableau_assistant.src.models.query_plan import ProcessingSubTask
    
    try:
        subtask_dict = json.loads(subtask_json)
        result_dict = json.loads(result_json)
        
        # 提取数据
        if isinstance(result_dict, dict) and "data" in result_dict:
            data_list = result_dict["data"]
        elif isinstance(result_dict, list):
            data_list = result_dict
        else:
            data_list = [result_dict]
        
        df = pd.DataFrame(data_list)
        question_id = subtask_dict.get("question_id", "unknown")
        
        # 对于复杂处理类型，使用 DataProcessor
        if processing_type in ("yoy", "mom", "growth_rate", "percentage", "custom"):
            # 检查是否有 processing_instruction
            if "processing_instruction" not in subtask_dict:
                raise ValueError(
                    f"Processing type '{processing_type}' requires processing_instruction in subtask"
                )
            
            # 创建 ProcessingSubTask 对象
            subtask = ProcessingSubTask(**subtask_dict)
            
            # 创建 QueryResult 对象
            source_task_id = subtask.processing_instruction.source_tasks[0]
            query_result = QueryResult(
                task_id=source_task_id,
                data=df,
                row_count=len(df),
                columns=list(df.columns)
            )
            
            # 使用 DataProcessor 处理
            processor = DataProcessor()
            processing_result = processor.process_subtask(
                subtask=subtask,
                query_results={source_task_id: query_result}
            )
            
            logger.info(f"✅ Query result processed with DataProcessor: {processing_type}")
            return {
                "question_id": processing_result.task_id,
                "processing_type": processing_result.processing_type,
                "data": processing_result.data.to_dict(orient='records'),
                "row_count": processing_result.row_count,
                "columns": processing_result.columns
            }
        
        # 对于默认处理，直接返回格式化的数据
        logger.info(f"✅ Query result processed: {processing_type}")
        return {
            "question_id": question_id,
            "processing_type": processing_type,
            "data": df.to_dict(orient='records'),
            "row_count": len(df),
            "columns": list(df.columns)
        }
    
    except Exception as e:
        logger.error(f"Query result processing failed: {e}")
        raise


__all__ = ["detect_statistics", "process_query_result"]
