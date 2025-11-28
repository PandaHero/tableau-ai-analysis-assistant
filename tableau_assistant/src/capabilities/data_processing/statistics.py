"""
Statistics Detector - 统计检测器

提供数据统计分析功能，用于洞察分析。

功能：
- 基本统计（min, max, mean, median, std, quartiles）
- 异常值检测（Z-score, IQR）
- 趋势检测（线性回归）
- 周期性检测（自相关）
- 相关性检测（Pearson, Spearman）
- 分布分析（偏度、峰度）
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from scipy import stats
from scipy.signal import find_peaks
import logging

logger = logging.getLogger(__name__)


class StatisticsDetector:
    """
    统计检测器
    
    提供全面的统计分析功能，用于数据洞察分析。
    """
    
    def __init__(self, z_score_threshold: float = 3.0, iqr_multiplier: float = 1.5):
        """
        初始化统计检测器
        
        Args:
            z_score_threshold: Z-score 异常值阈值（默认3.0）
            iqr_multiplier: IQR 异常值倍数（默认1.5）
        """
        self.z_score_threshold = z_score_threshold
        self.iqr_multiplier = iqr_multiplier
        logger.info(
            f"StatisticsDetector initialized: "
            f"z_threshold={z_score_threshold}, iqr_multiplier={iqr_multiplier}"
        )
    
    def detect_all(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        执行全面的统计检测
        
        Args:
            df: 输入数据（Pandas DataFrame）
        
        Returns:
            统计检测结果字典
        """
        logger.info(f"Starting comprehensive statistics detection: shape={df.shape}")
        
        results = {
            "basic_stats": self.compute_basic_stats(df),
            "anomalies": self.detect_anomalies(df),
            "trends": self.detect_trends(df),
            "correlations": self.detect_correlations(df),
            "distributions": self.analyze_distributions(df),
            "data_quality": self.assess_data_quality(df)
        }
        
        logger.info("Statistics detection completed")
        return results
    
    def compute_basic_stats(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        计算基本统计信息
        
        Args:
            df: 输入数据
        
        Returns:
            基本统计信息字典
        """
        stats_dict = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "numeric_columns": [],
            "categorical_columns": [],
            "date_columns": []
        }
        
        # 分类列
        for col in df.columns:
            dtype = df[col].dtype
            
            if pd.api.types.is_numeric_dtype(dtype):
                # 数值列统计
                col_stats = {
                    "column": col,
                    "count": int(df[col].count()),
                    "null_count": int(df[col].isna().sum()),
                    "null_percentage": float(df[col].isna().sum() / len(df) * 100),
                    "min": float(df[col].min()) if not df[col].isna().all() else None,
                    "max": float(df[col].max()) if not df[col].isna().all() else None,
                    "mean": float(df[col].mean()) if not df[col].isna().all() else None,
                    "median": float(df[col].median()) if not df[col].isna().all() else None,
                    "std": float(df[col].std()) if not df[col].isna().all() else None,
                    "q25": float(df[col].quantile(0.25)) if not df[col].isna().all() else None,
                    "q75": float(df[col].quantile(0.75)) if not df[col].isna().all() else None,
                    "unique_count": int(df[col].nunique())
                }
                stats_dict["numeric_columns"].append(col_stats)
                
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                # 日期列统计
                col_stats = {
                    "column": col,
                    "count": int(df[col].count()),
                    "null_count": int(df[col].isna().sum()),
                    "min": str(df[col].min()) if not df[col].isna().all() else None,
                    "max": str(df[col].max()) if not df[col].isna().all() else None,
                    "unique_count": int(df[col].nunique())
                }
                stats_dict["date_columns"].append(col_stats)
                
            else:
                # 分类列统计
                col_stats = {
                    "column": col,
                    "count": int(df[col].count()),
                    "null_count": int(df[col].isna().sum()),
                    "unique_count": int(df[col].nunique()),
                    "top_values": df[col].value_counts().head(5).to_dict()
                }
                stats_dict["categorical_columns"].append(col_stats)
        
        logger.debug(
            f"Basic stats computed: "
            f"{len(stats_dict['numeric_columns'])} numeric, "
            f"{len(stats_dict['categorical_columns'])} categorical, "
            f"{len(stats_dict['date_columns'])} date columns"
        )
        
        return stats_dict
    
    def detect_anomalies(self, df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
        """
        检测异常值
        
        使用两种方法：
        1. Z-score 方法（适用于正态分布）
        2. IQR 方法（适用于偏态分布）
        
        Args:
            df: 输入数据
        
        Returns:
            异常值检测结果
        """
        anomalies = {
            "z_score_anomalies": [],
            "iqr_anomalies": []
        }
        
        for col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col].dtype):
                continue
            
            # 跳过全空列
            if df[col].isna().all():
                continue
            
            # Z-score 方法
            z_scores = np.abs(stats.zscore(df[col].dropna()))
            z_anomaly_indices = np.where(z_scores > self.z_score_threshold)[0]
            
            if len(z_anomaly_indices) > 0:
                anomalies["z_score_anomalies"].append({
                    "column": col,
                    "method": "z_score",
                    "threshold": self.z_score_threshold,
                    "anomaly_count": int(len(z_anomaly_indices)),
                    "anomaly_percentage": float(len(z_anomaly_indices) / len(df) * 100),
                    "anomaly_values": df[col].iloc[z_anomaly_indices].tolist()[:10]  # 最多10个
                })
            
            # IQR 方法
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower_bound = Q1 - self.iqr_multiplier * IQR
            upper_bound = Q3 + self.iqr_multiplier * IQR
            
            iqr_anomalies = df[(df[col] < lower_bound) | (df[col] > upper_bound)]
            
            if len(iqr_anomalies) > 0:
                anomalies["iqr_anomalies"].append({
                    "column": col,
                    "method": "iqr",
                    "lower_bound": float(lower_bound),
                    "upper_bound": float(upper_bound),
                    "anomaly_count": int(len(iqr_anomalies)),
                    "anomaly_percentage": float(len(iqr_anomalies) / len(df) * 100),
                    "anomaly_values": iqr_anomalies[col].tolist()[:10]  # 最多10个
                })
        
        logger.debug(
            f"Anomalies detected: "
            f"{len(anomalies['z_score_anomalies'])} z-score, "
            f"{len(anomalies['iqr_anomalies'])} IQR"
        )
        
        return anomalies
    
    def detect_trends(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        检测趋势（线性回归）
        
        Args:
            df: 输入数据
        
        Returns:
            趋势检测结果
        """
        trends = []
        
        # 查找数值列
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        if len(numeric_cols) == 0:
            return trends
        
        # 假设第一列是索引（时间或序列）
        if len(df) < 3:  # 至少需要3个点才能检测趋势
            return trends
        
        x = np.arange(len(df))
        
        for col in numeric_cols:
            if df[col].isna().all():
                continue
            
            y = df[col].fillna(df[col].mean())  # 填充缺失值
            
            # 线性回归
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            
            # 判断趋势方向
            if abs(slope) < 1e-10:
                trend_direction = "flat"
            elif slope > 0:
                trend_direction = "increasing"
            else:
                trend_direction = "decreasing"
            
            # 判断趋势强度（基于 R²）
            r_squared = r_value ** 2
            if r_squared > 0.7:
                trend_strength = "strong"
            elif r_squared > 0.4:
                trend_strength = "moderate"
            else:
                trend_strength = "weak"
            
            trends.append({
                "column": col,
                "direction": trend_direction,
                "strength": trend_strength,
                "slope": float(slope),
                "intercept": float(intercept),
                "r_squared": float(r_squared),
                "p_value": float(p_value),
                "significant": bool(p_value < 0.05)
            })
        
        logger.debug(f"Trends detected: {len(trends)} columns analyzed")
        
        return trends
    
    def detect_correlations(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        检测相关性
        
        Args:
            df: 输入数据
        
        Returns:
            相关性检测结果
        """
        numeric_df = df.select_dtypes(include=[np.number])
        
        if len(numeric_df.columns) < 2:
            return {
                "pearson_correlations": [],
                "spearman_correlations": [],
                "strong_correlations": []
            }
        
        # Pearson 相关系数（线性相关）
        pearson_corr = numeric_df.corr(method='pearson')
        
        # Spearman 相关系数（单调相关）
        spearman_corr = numeric_df.corr(method='spearman')
        
        # 提取强相关（|r| > 0.7）
        strong_correlations = []
        
        for i in range(len(pearson_corr.columns)):
            for j in range(i + 1, len(pearson_corr.columns)):
                col1 = pearson_corr.columns[i]
                col2 = pearson_corr.columns[j]
                pearson_r = pearson_corr.iloc[i, j]
                spearman_r = spearman_corr.iloc[i, j]
                
                if abs(pearson_r) > 0.7 or abs(spearman_r) > 0.7:
                    strong_correlations.append({
                        "column1": col1,
                        "column2": col2,
                        "pearson_r": float(pearson_r),
                        "spearman_r": float(spearman_r),
                        "correlation_type": "positive" if pearson_r > 0 else "negative",
                        "strength": "very_strong" if abs(pearson_r) > 0.9 else "strong"
                    })
        
        logger.debug(f"Correlations detected: {len(strong_correlations)} strong correlations")
        
        return {
            "pearson_correlations": pearson_corr.to_dict(),
            "spearman_correlations": spearman_corr.to_dict(),
            "strong_correlations": strong_correlations
        }
    
    def analyze_distributions(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        分析数据分布
        
        Args:
            df: 输入数据
        
        Returns:
            分布分析结果
        """
        distributions = []
        
        for col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col].dtype):
                continue
            
            if df[col].isna().all():
                continue
            
            data = df[col].dropna()
            
            # 偏度（Skewness）
            skewness = float(stats.skew(data))
            
            # 峰度（Kurtosis）
            kurtosis = float(stats.kurtosis(data))
            
            # 正态性检验（Shapiro-Wilk test）
            if len(data) >= 3 and len(data) <= 5000:  # Shapiro-Wilk 限制
                _, p_value = stats.shapiro(data)
                is_normal = bool(p_value > 0.05)
            else:
                p_value = None
                is_normal = None
            
            # 判断分布类型
            if abs(skewness) < 0.5:
                distribution_type = "symmetric"
            elif skewness > 0:
                distribution_type = "right_skewed"
            else:
                distribution_type = "left_skewed"
            
            distributions.append({
                "column": col,
                "skewness": skewness,
                "kurtosis": kurtosis,
                "distribution_type": distribution_type,
                "is_normal": is_normal,
                "normality_p_value": float(p_value) if p_value is not None else None
            })
        
        logger.debug(f"Distributions analyzed: {len(distributions)} columns")
        
        return distributions
    
    def assess_data_quality(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        评估数据质量
        
        Args:
            df: 输入数据
        
        Returns:
            数据质量评估结果
        """
        total_cells = len(df) * len(df.columns)
        null_cells = df.isna().sum().sum()
        
        quality = {
            "completeness": {
                "total_cells": int(total_cells),
                "null_cells": int(null_cells),
                "completeness_rate": float((total_cells - null_cells) / total_cells * 100) if total_cells > 0 else 0,
                "columns_with_nulls": df.columns[df.isna().any()].tolist()
            },
            "consistency": {
                "duplicate_rows": int(df.duplicated().sum()),
                "duplicate_percentage": float(df.duplicated().sum() / len(df) * 100) if len(df) > 0 else 0
            },
            "validity": {
                "negative_values": {},
                "zero_values": {},
                "infinite_values": {}
            }
        }
        
        # 检查数值列的有效性
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col].dtype):
                # 负值
                negative_count = int((df[col] < 0).sum())
                if negative_count > 0:
                    quality["validity"]["negative_values"][col] = negative_count
                
                # 零值
                zero_count = int((df[col] == 0).sum())
                if zero_count > 0:
                    quality["validity"]["zero_values"][col] = zero_count
                
                # 无穷值
                if pd.api.types.is_float_dtype(df[col].dtype):
                    inf_count = int(np.isinf(df[col]).sum())
                    if inf_count > 0:
                        quality["validity"]["infinite_values"][col] = inf_count
        
        logger.debug(
            f"Data quality assessed: "
            f"completeness={quality['completeness']['completeness_rate']:.1f}%, "
            f"duplicates={quality['consistency']['duplicate_rows']}"
        )
        
        return quality


# ============= 导出 =============

__all__ = ["StatisticsDetector"]
