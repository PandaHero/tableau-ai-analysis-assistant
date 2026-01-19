"""
AnomalyDetector Component

Detects anomalies and outliers in data using IQR method.

Requirements:
- R8.1: Anomaly detection using IQR method
"""

import logging
from typing import Dict, List, Any, Optional
import pandas as pd
import numpy as np

from tableau_assistant.src.agents.insight.models import AnomalyResult, AnomalyDetail
from tableau_assistant.src.agents.insight.components.utils import to_dataframe


logger = logging.getLogger(__name__)


class AnomalyDetector:
    """
    Anomaly Detector - identifies outliers and anomalies in data.
    
    Uses IQR (Interquartile Range) method for outlier detection.
    """
    
    def __init__(self, iqr_multiplier: float = 1.5, max_details: int = 10):
        """
        Initialize anomaly detector.
        
        Args:
            iqr_multiplier: Multiplier for IQR bounds (default 1.5)
            max_details: Maximum number of anomaly details to return
        """
        self.iqr_multiplier = iqr_multiplier
        self.max_details = max_details
    
    def detect(self, data: Any) -> AnomalyResult:
        """
        Detect anomalies in the data.
        
        Args:
            data: Input data (DataFrame, list of dicts, or dict)
            
        Returns:
            AnomalyResult with outliers and details
        """
        # Convert to DataFrame if needed
        df = self._to_dataframe(data)
        
        if df.empty:
            return AnomalyResult(
                outliers=[],
                anomaly_ratio=0.0,
                anomaly_details=[],
            )
        
        # Detect outliers
        outliers, column_outliers = self._detect_outliers(df)
        
        # Calculate anomaly ratio
        anomaly_ratio = len(outliers) / len(df) if len(df) > 0 else 0.0
        
        # Get anomaly details
        anomaly_details = self._get_anomaly_details(df, outliers, column_outliers)
        
        return AnomalyResult(
            outliers=list(outliers),
            anomaly_ratio=anomaly_ratio,
            anomaly_details=anomaly_details,
        )
    
    def _to_dataframe(self, data: Any) -> pd.DataFrame:
        """Convert various data formats to DataFrame."""
        return to_dataframe(data)
    
    def _detect_outliers(self, df: pd.DataFrame) -> tuple:
        """
        Detect outliers using IQR method.
        
        Returns:
            Tuple of (set of outlier indices, dict of column -> outlier indices)
        """
        outlier_indices = set()
        column_outliers = {}
        
        # Only check numeric columns
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            try:
                col_data = df[col].dropna()
                if len(col_data) < 4:  # Need at least 4 values for IQR
                    continue
                
                q1 = col_data.quantile(0.25)
                q3 = col_data.quantile(0.75)
                iqr = q3 - q1
                
                if iqr == 0:  # All values are the same
                    continue
                
                lower_bound = q1 - self.iqr_multiplier * iqr
                upper_bound = q3 + self.iqr_multiplier * iqr
                
                # Find outliers for this column
                col_outliers = df[
                    (df[col] < lower_bound) | (df[col] > upper_bound)
                ].index.tolist()
                
                if col_outliers:
                    column_outliers[col] = {
                        "indices": col_outliers,
                        "lower_bound": lower_bound,
                        "upper_bound": upper_bound,
                        "q1": q1,
                        "q3": q3,
                    }
                    outlier_indices.update(col_outliers)
                    
            except Exception as e:
                logger.warning(f"Failed to detect outliers for column {col}: {e}")
        
        return outlier_indices, column_outliers
    
    def _get_anomaly_details(
        self,
        df: pd.DataFrame,
        outlier_indices: set,
        column_outliers: Dict[str, Dict]
    ) -> List[AnomalyDetail]:
        """Get detailed information about anomalies."""
        details = []
        
        # Sort by index for consistent ordering
        sorted_indices = sorted(outlier_indices)[:self.max_details]
        
        for idx in sorted_indices:
            try:
                row = df.loc[idx]
                
                # Find which columns this row is an outlier in
                outlier_columns = []
                for col, info in column_outliers.items():
                    if idx in info["indices"]:
                        outlier_columns.append(col)
                
                # Generate reason
                reason = self._explain_anomaly(row, column_outliers, outlier_columns)
                
                # Calculate severity (how far from bounds)
                severity = self._calculate_severity(row, column_outliers, outlier_columns)
                
                details.append(AnomalyDetail(
                    index=int(idx),
                    values=row.to_dict(),
                    reason=reason,
                    column=outlier_columns[0] if outlier_columns else None,
                    severity=severity,
                ))
                
            except Exception as e:
                logger.warning(f"Failed to get anomaly details for index {idx}: {e}")
        
        return details
    
    def _explain_anomaly(
        self,
        row: pd.Series,
        column_outliers: Dict[str, Dict],
        outlier_columns: List[str]
    ) -> str:
        """Generate explanation for why a row is an anomaly."""
        if not outlier_columns:
            return "Unknown anomaly"
        
        explanations = []
        for col in outlier_columns:
            info = column_outliers.get(col, {})
            value = row.get(col)
            
            if value is not None and info:
                lower = info.get("lower_bound", 0)
                upper = info.get("upper_bound", 0)
                
                if value < lower:
                    explanations.append(f"{col}={value:.2f} 低于下界 {lower:.2f}")
                elif value > upper:
                    explanations.append(f"{col}={value:.2f} 高于上界 {upper:.2f}")
        
        return "; ".join(explanations) if explanations else "异常值"
    
    def _calculate_severity(
        self,
        row: pd.Series,
        column_outliers: Dict[str, Dict],
        outlier_columns: List[str]
    ) -> float:
        """Calculate severity score (0-1) for an anomaly."""
        if not outlier_columns:
            return 0.0
        
        max_severity = 0.0
        
        for col in outlier_columns:
            info = column_outliers.get(col, {})
            value = row.get(col)
            
            if value is not None and info:
                lower = info.get("lower_bound", 0)
                upper = info.get("upper_bound", 0)
                iqr = (info.get("q3", 0) - info.get("q1", 0))
                
                if iqr > 0:
                    if value < lower:
                        deviation = (lower - value) / iqr
                    else:
                        deviation = (value - upper) / iqr
                    
                    # Normalize to 0-1 scale (cap at 3 IQRs = 1.0)
                    severity = min(deviation / 3.0, 1.0)
                    max_severity = max(max_severity, severity)
        
        return max_severity
