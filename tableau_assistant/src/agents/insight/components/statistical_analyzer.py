# -*- coding: utf-8 -*-
"""
StatisticalAnalyzer Component

Phase 1 统计/ML 整体分析 - 纯统计方法，不需要 LLM。

Design Specification: insight-design.md
- 分布分析（偏度、峰度）
- 帕累托分析（80/20 法则）
- 异常检测（IQR 方法）
- 聚类分析（K-Means）
- 趋势检测（线性回归）
- 相关性分析（皮尔逊相关）
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np

from tableau_assistant.src.core.models import (
    DataProfile,
    DataInsightProfile,
    ClusterInfo,
    ColumnStats,
)

logger = logging.getLogger(__name__)


class StatisticalAnalyzer:
    """
    统计/ML 分析器 - Phase 1 整体分析
    
    纯统计/ML 方法，不需要 LLM。
    生成 DataInsightProfile 用于指导 Phase 2 分块策略。
    
    Design Note:
    类似 Tableau Pulse 的设计理念：
    - 先用统计/ML 方法快速了解数据整体特征
    - 发现宏观模式（分布、聚类、趋势）
    - 推荐最佳分块策略
    """
    
    def __init__(
        self,
        top_n: int = 5,
        min_cluster_samples: int = 10,
        max_clusters: int = 5,
    ):
        """
        Initialize StatisticalAnalyzer.
        
        Args:
            top_n: Top N 数据摘要的数量
            min_cluster_samples: 聚类分析的最小样本数
            max_clusters: 最大聚类数
        """
        self.top_n = top_n
        self.min_cluster_samples = min_cluster_samples
        self.max_clusters = max_clusters
    
    def analyze(
        self,
        data: List[Dict[str, Any]],
        profile: DataProfile,
    ) -> DataInsightProfile:
        """
        整体分析，生成数据洞察画像。
        
        Args:
            data: 数据列表
            profile: 数据画像（来自 DataProfiler）
            
        Returns:
            DataInsightProfile 整体洞察画像
        """
        df = pd.DataFrame(data)
        
        if df.empty:
            return self._empty_profile()
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        if not numeric_cols:
            return self._empty_profile()
        
        # 选择主度量列（第一个数值列）
        primary_measure = numeric_cols[0]
        values = df[primary_measure].dropna()
        
        if len(values) == 0:
            return self._empty_profile()
        
        logger.info(f"Phase 1 分析: {len(df)} 行, 主度量列: {primary_measure}")
        
        # 1. 分布分析
        distribution_type, skewness, kurtosis = self._analyze_distribution(values)
        logger.debug(f"分布分析: type={distribution_type}, skew={skewness:.2f}, kurt={kurtosis:.2f}")
        
        # 2. 帕累托分析
        pareto_ratio, pareto_threshold = self._analyze_pareto(values)
        logger.debug(f"帕累托分析: ratio={pareto_ratio:.2f}, threshold={pareto_threshold:.2f}")
        
        # 3. 异常检测
        anomaly_indices, anomaly_ratio = self._detect_anomalies(values)
        logger.debug(f"异常检测: {len(anomaly_indices)} 个异常值, ratio={anomaly_ratio:.2f}")
        
        # 4. 聚类分析
        clusters, optimal_k = self._cluster_analysis(df, numeric_cols)
        logger.debug(f"聚类分析: {len(clusters)} 个聚类, optimal_k={optimal_k}")
        
        # 5. 趋势检测（如果有时间列）
        trend, trend_slope, change_points = self._detect_trend(df, profile)
        if trend:
            logger.debug(f"趋势检测: trend={trend}, slope={trend_slope}")
        
        # 6. 相关性分析
        correlations = self._calculate_correlations(df, numeric_cols)
        
        # 7. 推荐分块策略
        recommended_strategy = self._recommend_chunking_strategy(
            distribution_type=distribution_type,
            clusters=clusters,
            change_points=change_points,
            profile=profile,
        )
        logger.info(f"推荐分块策略: {recommended_strategy}")
        
        # 8. 生成 Top N 摘要
        top_n_summary = self._generate_top_n_summary(df, primary_measure)
        
        return DataInsightProfile(
            distribution_type=distribution_type,
            skewness=skewness,
            kurtosis=kurtosis,
            pareto_ratio=pareto_ratio,
            pareto_threshold=pareto_threshold,
            anomaly_indices=anomaly_indices,
            anomaly_ratio=anomaly_ratio,
            anomaly_method="IQR",
            clusters=clusters,
            optimal_k=optimal_k,
            clustering_method="KMeans",
            trend=trend,
            trend_slope=trend_slope,
            change_points=change_points,
            correlations=correlations,
            statistics=profile.statistics,
            recommended_chunking_strategy=recommended_strategy,
            primary_measure=primary_measure,
            top_n_summary=top_n_summary,
        )
    
    def _empty_profile(self) -> DataInsightProfile:
        """返回空的洞察画像。"""
        return DataInsightProfile(
            distribution_type="unknown",
            skewness=0.0,
            kurtosis=0.0,
            pareto_ratio=0.0,
            pareto_threshold=0.0,
            anomaly_indices=[],
            anomaly_ratio=0.0,
            anomaly_method="IQR",
            clusters=[],
            optimal_k=0,
            clustering_method="KMeans",
            correlations={},
            statistics={},
            recommended_chunking_strategy="by_position",
        )
    
    def _analyze_distribution(
        self,
        values: pd.Series,
    ) -> Tuple[str, float, float]:
        """
        分析数据分布。
        
        Returns:
            (distribution_type, skewness, kurtosis)
        """
        try:
            skewness = float(values.skew())
            kurtosis = float(values.kurtosis())
        except Exception:
            return "unknown", 0.0, 0.0
        
        # 判断分布类型
        if abs(skewness) < 0.5:
            distribution_type = "normal"
        elif skewness > 1 or skewness < -1:
            distribution_type = "long_tail"
        else:
            # 简化处理，可以后续添加双峰检测
            distribution_type = "normal"
        
        return distribution_type, skewness, kurtosis
    
    def _analyze_pareto(
        self,
        values: pd.Series,
    ) -> Tuple[float, float]:
        """
        帕累托分析（80/20 法则）。
        
        Returns:
            (pareto_ratio, pareto_threshold)
            - pareto_ratio: top 20% 贡献的比例
            - pareto_threshold: 贡献 80% 的数据占比
        """
        if len(values) == 0:
            return 0.0, 0.0
        
        try:
            sorted_values = values.sort_values(ascending=False).reset_index(drop=True)
            cumsum = sorted_values.cumsum()
            total = sorted_values.sum()
            
            if total == 0:
                return 0.0, 0.0
            
            # top 20% 贡献的比例
            top_20_idx = max(1, int(len(sorted_values) * 0.2))
            pareto_ratio = float(cumsum.iloc[top_20_idx - 1] / total)
            
            # 贡献 80% 的数据占比
            cumsum_pct = cumsum / total
            threshold_mask = cumsum_pct >= 0.8
            if threshold_mask.any():
                threshold_idx = threshold_mask.idxmax()
                pareto_threshold = float((threshold_idx + 1) / len(sorted_values))
            else:
                pareto_threshold = 1.0
            
            return pareto_ratio, pareto_threshold
            
        except Exception as e:
            logger.warning(f"帕累托分析失败: {e}")
            return 0.0, 0.0
    
    def _detect_anomalies(
        self,
        values: pd.Series,
    ) -> Tuple[List[int], float]:
        """
        IQR 异常检测。
        
        Returns:
            (anomaly_indices, anomaly_ratio)
        """
        if len(values) < 4:
            return [], 0.0
        
        try:
            q1 = values.quantile(0.25)
            q3 = values.quantile(0.75)
            iqr = q3 - q1
            
            if iqr == 0:
                return [], 0.0
            
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            
            anomaly_mask = (values < lower_bound) | (values > upper_bound)
            anomaly_indices = values[anomaly_mask].index.tolist()
            anomaly_ratio = float(len(anomaly_indices) / len(values))
            
            return anomaly_indices, anomaly_ratio
            
        except Exception as e:
            logger.warning(f"异常检测失败: {e}")
            return [], 0.0
    
    def _cluster_analysis(
        self,
        df: pd.DataFrame,
        numeric_cols: List[str],
    ) -> Tuple[List[ClusterInfo], int]:
        """
        K-Means 聚类分析。
        
        Returns:
            (clusters, optimal_k)
        """
        if len(df) < self.min_cluster_samples or len(numeric_cols) == 0:
            return [], 0
        
        try:
            from sklearn.cluster import KMeans
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            logger.warning("sklearn 未安装，跳过聚类分析")
            return [], 0
        
        try:
            # 准备数据
            X = df[numeric_cols].fillna(0).values
            
            # 标准化
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            # 确定最优 K（简化：基于数据量）
            optimal_k = min(
                self.max_clusters,
                max(2, len(df) // 50)
            )
            
            if optimal_k < 2:
                return [], 0
            
            # 聚类
            kmeans = KMeans(
                n_clusters=optimal_k,
                random_state=42,
                n_init=10,
            )
            labels = kmeans.fit_predict(X_scaled)
            
            # 构建聚类信息
            clusters = []
            primary_col = numeric_cols[0]
            
            for i in range(optimal_k):
                mask = labels == i
                cluster_df = df[mask]
                
                if len(cluster_df) == 0:
                    continue
                
                # 计算聚类中心（原始尺度）
                center = {
                    col: float(cluster_df[col].mean())
                    for col in numeric_cols
                }
                
                clusters.append(ClusterInfo(
                    cluster_id=i,
                    center=center,
                    size=int(mask.sum()),
                    label="",  # 稍后设置
                    indices=df[mask].index.tolist(),
                ))
            
            # 按主度量排序并设置标签
            clusters.sort(
                key=lambda x: x.center.get(primary_col, 0),
                reverse=True,
            )
            
            for i, cluster in enumerate(clusters):
                if i == 0:
                    cluster.label = "高绩效"
                elif i == len(clusters) - 1:
                    cluster.label = "低绩效"
                else:
                    cluster.label = "中等"
                
                # 小聚类标记为异常
                if cluster.size < len(df) * 0.05:
                    cluster.label = "异常"
            
            return clusters, optimal_k
            
        except Exception as e:
            logger.warning(f"聚类分析失败: {e}")
            return [], 0
    
    def _detect_trend(
        self,
        df: pd.DataFrame,
        profile: DataProfile,
    ) -> Tuple[Optional[str], Optional[float], Optional[List[int]]]:
        """
        趋势检测（如果有时间列）。
        
        Returns:
            (trend, trend_slope, change_points)
        """
        # 查找时间列
        time_cols = []
        for group in profile.semantic_groups:
            if group.type == "time":
                time_cols.extend(group.columns)
        
        if not time_cols:
            return None, None, None
        
        # 查找数值列
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            return None, None, None
        
        try:
            # 简化：使用线性回归检测趋势
            from scipy import stats
            
            time_col = time_cols[0]
            value_col = numeric_cols[0]
            
            # 转换时间列为数值
            if pd.api.types.is_datetime64_any_dtype(df[time_col]):
                x = (df[time_col] - df[time_col].min()).dt.total_seconds().values
            else:
                x = np.arange(len(df))
            
            y = df[value_col].fillna(0).values
            
            # 线性回归
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            
            # 判断趋势
            if p_value < 0.05:  # 显著性检验
                if slope > 0:
                    trend = "increasing"
                elif slope < 0:
                    trend = "decreasing"
                else:
                    trend = "stable"
            else:
                trend = "stable"
            
            # 简化：不做变点检测
            change_points = None
            
            return trend, float(slope), change_points
            
        except Exception as e:
            logger.warning(f"趋势检测失败: {e}")
            return None, None, None
    
    def _calculate_correlations(
        self,
        df: pd.DataFrame,
        numeric_cols: List[str],
    ) -> Dict[str, float]:
        """
        计算数值列之间的相关性。
        
        Returns:
            {col1|col2: correlation}
        """
        if len(numeric_cols) < 2:
            return {}
        
        try:
            correlations = {}
            corr_matrix = df[numeric_cols].corr()
            
            for i, col1 in enumerate(numeric_cols):
                for col2 in numeric_cols[i + 1:]:
                    corr_value = corr_matrix.loc[col1, col2]
                    if not np.isnan(corr_value):
                        key = f"{col1}|{col2}"
                        correlations[key] = float(corr_value)
            
            return correlations
            
        except Exception as e:
            logger.warning(f"相关性分析失败: {e}")
            return {}
    
    def _recommend_chunking_strategy(
        self,
        distribution_type: str,
        clusters: List[ClusterInfo],
        change_points: Optional[List[int]],
        profile: DataProfile,
    ) -> str:
        """
        推荐分块策略。
        
        优先级：聚类 > 变点 > 帕累托 > 语义 > 统计 > 位置
        """
        # 1. 聚类分块
        if len(clusters) >= 2:
            return "by_cluster"
        
        # 2. 变点分块
        if change_points and len(change_points) >= 1:
            return "by_change_point"
        
        # 3. 帕累托分块（长尾分布）
        if distribution_type == "long_tail":
            return "by_pareto"
        
        # 4. 语义分块（检查是否有合适的语义列）
        for group in profile.semantic_groups:
            if group.type in ("time", "geography", "category"):
                return "by_semantic"
        
        # 5. 统计分块（有数值列）
        if profile.statistics:
            return "by_statistics"
        
        # 6. 位置分块（最后手段）
        return "by_position"
    
    def _generate_top_n_summary(
        self,
        df: pd.DataFrame,
        primary_measure: str,
    ) -> List[Dict[str, Any]]:
        """
        生成 Top N 数据摘要。
        
        用于分析师 LLM 进行对比分析（如"是第2名的5倍"）。
        """
        if primary_measure not in df.columns:
            return []
        
        try:
            # 按主度量排序
            df_sorted = df.sort_values(primary_measure, ascending=False)
            
            # 取 Top N
            top_n_df = df_sorted.head(self.top_n)
            
            # 添加排名
            result = []
            for i, (idx, row) in enumerate(top_n_df.iterrows()):
                record = row.to_dict()
                record["_rank"] = i + 1
                result.append(record)
            
            return result
            
        except Exception as e:
            logger.warning(f"生成 Top N 摘要失败: {e}")
            return []
