"""
Detect Statistics Tool - 统计检测工具

封装 StatisticsDetector 组件为 LangChain 工具，用于数据统计分析。

特性：
- 基本统计（min, max, mean, median, std, quartiles）
- 异常值检测（Z-score, IQR）
- 趋势检测（线性回归）
- 相关性检测（Pearson, Spearman）
- 分布分析（偏度、峰度、正态性）
- 数据质量评估（完整性、一致性、有效性）
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
    
    The tool is designed for use in the Insight Agent to provide statistical context
    for LLM-based insight generation.
    
    Args:
        data_json: JSON string of data to analyze.
            Format: {"columns": ["col1", "col2", ...], "data": [{...}, {...}, ...]}
            Or: [{"col1": val1, "col2": val2}, ...]
        z_score_threshold: Z-score threshold for anomaly detection (default: 3.0).
            Values with |z-score| > threshold are considered anomalies.
        iqr_multiplier: IQR multiplier for anomaly detection (default: 1.5).
            Values outside [Q1 - multiplier*IQR, Q3 + multiplier*IQR] are anomalies.
        include_basic_stats: Whether to compute basic statistics (default: True).
        include_anomalies: Whether to detect anomalies (default: True).
        include_trends: Whether to detect trends (default: True).
        include_correlations: Whether to detect correlations (default: True).
        include_distributions: Whether to analyze distributions (default: True).
        include_data_quality: Whether to assess data quality (default: True).
    
    Returns:
        Dictionary with statistical analysis results:
        - basic_stats: Basic statistics for each column
            - numeric_columns: List of numeric column stats (min, max, mean, median, std, quartiles)
            - categorical_columns: List of categorical column stats (unique count, top values)
            - date_columns: List of date column stats (min, max, unique count)
        - anomalies: Anomaly detection results
            - z_score_anomalies: Anomalies detected using Z-score method
            - iqr_anomalies: Anomalies detected using IQR method
        - trends: Trend detection results (linear regression)
            - direction: increasing, decreasing, or flat
            - strength: strong, moderate, or weak (based on R²)
            - slope, intercept, r_squared, p_value
        - correlations: Correlation analysis results
            - pearson_correlations: Pearson correlation matrix
            - spearman_correlations: Spearman correlation matrix
            - strong_correlations: List of strong correlations (|r| > 0.7)
        - distributions: Distribution analysis results
            - skewness, kurtosis, distribution_type
            - is_normal, normality_p_value (Shapiro-Wilk test)
        - data_quality: Data quality assessment
            - completeness: Null cell percentage
            - consistency: Duplicate row percentage
            - validity: Negative values, zero values, infinite values
    
    Examples:
        # Full statistical analysis
        >>> detect_statistics(
        ...     data_json='[{"Month": "Jan", "Sales": 1000, "Profit": 200}, '
        ...               '{"Month": "Feb", "Sales": 1200, "Profit": 250}, ...]'
        ... )
        {
            "basic_stats": {
                "numeric_columns": [
                    {"column": "Sales", "min": 1000, "max": 1200, "mean": 1100, ...},
                    {"column": "Profit", "min": 200, "max": 250, "mean": 225, ...}
                ],
                ...
            },
            "anomalies": {
                "z_score_anomalies": [...],
                "iqr_anomalies": [...]
            },
            "trends": [
                {"column": "Sales", "direction": "increasing", "strength": "strong", ...}
            ],
            ...
        }
        
        # Only anomaly detection
        >>> detect_statistics(
        ...     data_json='[...]',
        ...     include_basic_stats=False,
        ...     include_trends=False,
        ...     include_correlations=False,
        ...     include_distributions=False,
        ...     include_data_quality=False
        ... )
        {"anomalies": {...}}
        
        # Custom thresholds
        >>> detect_statistics(
        ...     data_json='[...]',
        ...     z_score_threshold=2.5,  # More sensitive
        ...     iqr_multiplier=2.0      # Less sensitive
        ... )
    
    Note:
        - All analysis is done using Pandas and SciPy
        - Trend detection requires at least 3 data points
        - Correlation analysis requires at least 2 numeric columns
        - Normality test (Shapiro-Wilk) is limited to 3-5000 samples
        - Large datasets may take longer to analyze
    """
    import pandas as pd
    from tableau_assistant.src.capabilities.data_processing.statistics import StatisticsDetector
    
    try:
        # 1. Parse input data
        data = json.loads(data_json)
        
        # 2. Convert to DataFrame
        if isinstance(data, dict) and "data" in data:
            # Format: {"columns": [...], "data": [...]}
            df = pd.DataFrame(data["data"])
        elif isinstance(data, list):
            # Format: [{...}, {...}, ...]
            df = pd.DataFrame(data)
        else:
            raise ValueError("Invalid data format. Expected list of dicts or dict with 'data' key")
        
        if df.empty:
            raise ValueError("Empty dataset provided")
        
        logger.info(
            f"Detecting statistics: shape={df.shape}, "
            f"z_threshold={z_score_threshold}, iqr_multiplier={iqr_multiplier}"
        )
        
        # 3. Create StatisticsDetector
        detector = StatisticsDetector(
            z_score_threshold=z_score_threshold,
            iqr_multiplier=iqr_multiplier
        )
        
        # 4. Perform selected analyses
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
        
        # 5. Add summary
        results["summary"] = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "analyses_performed": [
                key for key, value in {
                    "basic_stats": include_basic_stats,
                    "anomalies": include_anomalies,
                    "trends": include_trends,
                    "correlations": include_correlations,
                    "distributions": include_distributions,
                    "data_quality": include_data_quality
                }.items() if value
            ]
        }
        
        logger.info(
            f"✅ Statistics detection completed: "
            f"{len(results['summary']['analyses_performed'])} analyses performed"
        )
        
        return results
    
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON input: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    except Exception as e:
        error_msg = f"Statistics detection failed: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


# 导出
__all__ = ["detect_statistics"]
