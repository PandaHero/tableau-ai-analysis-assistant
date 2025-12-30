# -*- coding: utf-8 -*-
"""
StatisticalAnalyzer Component

Phase 1 统计分析 - 参考 Tableau Pulse 实现，纯统计方法，不需要 LLM。

Tableau Pulse 洞察类型：
- Period Over Period Change: 同环比变化
- Unexpected Values: 异常值检测（基于历史范围）
- Current Trend: 当前趋势（方向、变化率）
- Trend Change Alert: 趋势变点检测
- Top/Bottom Contributors: 贡献最大/最小的维度成员
- Top Drivers/Detractors: 变化最大的驱动因素
- Concentrated Contribution: 帕累托分析（少数贡献多数）
- Correlations: 指标相关性

注意：移除了聚类分析，因为：
1. 聚类分析 O(n²) 复杂度，10万行数据性能瓶颈
2. Tableau Pulse 不使用聚类，而是用 Top Contributors 等更直观的洞察
3. LLM 更容易理解 "华东区贡献60%" 而不是 "聚类2的中心是(0.3, 0.7)"
"""

import logging
from typing import Dict, List, Any, Optional, Tuple, Union
import pandas as pd
import numpy as np

from tableau_assistant.src.agents.insight.models import (
    DataProfile,
    DataInsightProfile,
    ColumnStats,
)

logger = logging.getLogger(__name__)


class StatisticalAnalyzer:
    """
    统计分析器 - Phase 1 整体分析（参考 Tableau Pulse）
    
    纯统计方法，不需要 LLM。所有算法复杂度 <= O(n log n)。
    生成 DataInsightProfile 用于指导 Phase 2 分块策略。
    """
    
    def __init__(
        self,
        top_n: int = 5,
        significance_threshold: float = 0.05,
    ):
        """
        Initialize StatisticalAnalyzer.
        
        Args:
            top_n: Top N 数据摘要的数量
            significance_threshold: 显著性阈值（用于趋势检测）
        """
        self.top_n = top_n
        self.significance_threshold = significance_threshold
    
    def analyze(
        self,
        data: Union[List[Dict[str, Any]], pd.DataFrame],
        profile: DataProfile,
    ) -> DataInsightProfile:
        """
        整体分析，生成数据洞察画像。
        
        Args:
            data: Data list or DataFrame (DataFrame preferred for performance)
            profile: Data profile (from EnhancedDataProfiler)
            
        Returns:
            DataInsightProfile 整体洞察画像
        """
        # Support both DataFrame and list of dicts
        if isinstance(data, pd.DataFrame):
            df = data
        else:
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
        
        # 2. 帕累托分析 (Concentrated Contribution)
        pareto_ratio, pareto_threshold = self._analyze_pareto(values)
        logger.debug(f"帕累托分析: ratio={pareto_ratio:.2f}, threshold={pareto_threshold:.2f}")
        
        # 3. 异常检测 (Unexpected Values)
        anomaly_indices, anomaly_ratio = self._detect_anomalies(values)
        logger.debug(f"异常检测: {len(anomaly_indices)} 个异常值, ratio={anomaly_ratio:.2f}")
        
        # 4. 趋势检测 (Current Trend + Trend Change Alert)
        trend, trend_slope, change_points, change_point_method = self._detect_trend(df, profile)
        if trend:
            logger.debug(f"趋势检测: trend={trend}, slope={trend_slope}, method={change_point_method}")
        
        # 5. 相关性分析 (Correlated Metrics)
        correlations = self._calculate_correlations(df, numeric_cols)
        
        # 6. 推荐分块策略（移除 by_cluster）
        recommended_strategy = self._recommend_chunking_strategy(
            distribution_type=distribution_type,
            change_points=change_points,
            profile=profile,
        )
        logger.info(f"推荐分块策略: {recommended_strategy}")
        
        # 7. 生成 Top N 摘要 (Top Contributors)
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
            # 移除聚类相关字段
            clusters=[],
            optimal_k=0,
            clustering_method="None",
            trend=trend,
            trend_slope=trend_slope,
            change_points=change_points,
            change_point_method=change_point_method,
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
            clustering_method="None",
            trend=None,
            trend_slope=None,
            change_points=None,
            change_point_method=None,
            correlations={},
            statistics={},
            recommended_chunking_strategy="by_position",
            primary_measure=None,
            top_n_summary=[],
        )
    
    def _analyze_distribution(
        self,
        values: pd.Series,
    ) -> Tuple[str, float, float]:
        """
        分析数据分布。
        
        复杂度: O(n)
        
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
            distribution_type = "normal"
        
        return distribution_type, skewness, kurtosis
    
    def _analyze_pareto(
        self,
        values: pd.Series,
    ) -> Tuple[float, float]:
        """
        帕累托分析（Concentrated Contribution - Tableau Pulse 风格）。
        
        复杂度: O(n log n) - 排序
        
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
        IQR 异常检测（Unexpected Values - Tableau Pulse 风格）。
        
        复杂度: O(n)
        
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
    
    def _detect_trend(
        self,
        df: pd.DataFrame,
        profile: DataProfile,
    ) -> Tuple[Optional[str], Optional[float], Optional[List[int]], Optional[str]]:
        """
        趋势检测（Current Trend + Trend Change Alert - Tableau Pulse 风格）。
        
        复杂度: O(n)
        
        Returns:
            (trend, trend_slope, change_points, change_point_method)
        """
        # 查找时间列
        time_cols = []
        for group in profile.semantic_groups:
            if group.type == "time":
                time_cols.extend(group.columns)
        
        if not time_cols:
            return None, None, None, None
        
        # 查找数值列
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            return None, None, None, None
        
        try:
            from scipy import stats
            
            time_col = time_cols[0]
            value_col = numeric_cols[0]
            
            # 转换时间列为数值
            if pd.api.types.is_datetime64_any_dtype(df[time_col]):
                x = (df[time_col] - df[time_col].min()).dt.total_seconds().values
            else:
                x = np.arange(len(df))
            
            y = df[value_col].fillna(0).values
            
            # 线性回归 O(n)
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            
            # 判断趋势
            if p_value < self.significance_threshold:
                if slope > 0:
                    trend = "increasing"
                elif slope < 0:
                    trend = "decreasing"
                else:
                    trend = "stable"
            else:
                trend = "stable"
            
            # 变点检测
            change_points, change_point_method = self._detect_change_points_robust(y)
            
            return trend, float(slope), change_points, change_point_method
            
        except Exception as e:
            logger.warning(f"趋势检测失败: {e}")
            return None, None, None, None
    
    def _detect_change_points_robust(
        self,
        values: np.ndarray,
        min_size: int = 5,
        penalty: float = 3.0,
    ) -> Tuple[Optional[List[int]], Optional[str]]:
        """
        鲁棒变点检测（Trend Change Alert - Tableau Pulse 风格）。
        
        使用 ruptures PELT 算法，复杂度 O(n)。
        
        Args:
            values: 时间序列值
            min_size: 变点之间的最小段长度
            penalty: PELT 算法惩罚值（越高变点越少）
        
        Returns:
            (change_points, method)
        """
        if len(values) < min_size * 2:
            return None, None
        
        # 尝试 ruptures PELT 算法
        try:
            import ruptures as rpt
            
            algo = rpt.Pelt(model="rbf", min_size=min_size).fit(values)
            change_points = algo.predict(pen=penalty)
            
            # 移除最后一个点（总是等于 len(values)）
            if change_points and change_points[-1] == len(values):
                change_points = change_points[:-1]
            
            if change_points:
                logger.debug(f"PELT 检测到 {len(change_points)} 个变点: {change_points}")
                return change_points, "pelt"
            
            return None, None
            
        except ImportError:
            logger.debug("ruptures 未安装，使用 rolling mean 方法")
            return self._detect_change_points_simple(values, min_size)
        except Exception as e:
            logger.warning(f"PELT 变点检测失败: {e}，使用简单方法")
            return self._detect_change_points_simple(values, min_size)
    
    def _detect_change_points_simple(
        self,
        values: np.ndarray,
        min_size: int = 5,
        threshold_sigma: float = 2.0,
    ) -> Tuple[Optional[List[int]], Optional[str]]:
        """
        简单变点检测（rolling mean + std）。
        
        复杂度: O(n)
        
        Args:
            values: 时间序列值
            min_size: 窗口大小
            threshold_sigma: 变点检测阈值（标准差倍数）
        
        Returns:
            (change_points, method)
        """
        if len(values) < min_size * 2:
            return None, None
        
        try:
            series = pd.Series(values)
            rolling_mean = series.rolling(window=min_size, center=True).mean()
            
            global_mean = series.mean()
            global_std = series.std()
            
            if global_std == 0:
                return None, None
            
            change_points = []
            for i in range(min_size, len(values) - min_size):
                if pd.notna(rolling_mean.iloc[i]):
                    local_mean = rolling_mean.iloc[i]
                    deviation = abs(local_mean - global_mean) / global_std
                    
                    if deviation > threshold_sigma:
                        if not change_points or (i - change_points[-1]) >= min_size:
                            change_points.append(i)
            
            if change_points:
                logger.debug(f"Rolling mean 检测到 {len(change_points)} 个变点: {change_points}")
                return change_points, "rolling_mean"
            
            return None, None
            
        except Exception as e:
            logger.warning(f"简单变点检测失败: {e}")
            return None, None
    
    def _calculate_correlations(
        self,
        df: pd.DataFrame,
        numeric_cols: List[str],
    ) -> Dict[str, float]:
        """
        计算数值列之间的相关性（Correlated Metrics - Tableau Pulse 风格）。
        
        复杂度: O(n * k²) 其中 k 是数值列数量
        
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
        change_points: Optional[List[int]],
        profile: DataProfile,
    ) -> str:
        """
        推荐分块策略（移除 by_cluster）。
        
        优先级：变点 > 帕累托 > 语义 > 统计 > 位置
        """
        # 1. 变点分块
        if change_points and len(change_points) >= 1:
            return "by_change_point"
        
        # 2. 帕累托分块（长尾分布）
        if distribution_type == "long_tail":
            return "by_pareto"
        
        # 3. 语义分块（检查是否有合适的语义列）
        for group in profile.semantic_groups:
            if group.type in ("time", "geography", "category"):
                return "by_semantic"
        
        # 4. 统计分块（有数值列）
        if profile.statistics:
            return "by_statistics"
        
        # 5. 位置分块（最后手段）
        return "by_position"
    
    def _generate_top_n_summary(
        self,
        df: pd.DataFrame,
        primary_measure: str,
    ) -> List[Dict[str, Any]]:
        """
        生成 Top N 数据摘要（Top Contributors - Tableau Pulse 风格）。
        
        复杂度: O(n log n) - 排序
        
        用于分析师 LLM 进行对比分析（如"是第2名的5倍"）。
        """
        if primary_measure not in df.columns:
            return []
        
        try:
            df_sorted = df.sort_values(primary_measure, ascending=False)
            top_n_df = df_sorted.head(self.top_n)
            
            result = []
            for i, (idx, row) in enumerate(top_n_df.iterrows()):
                record = row.to_dict()
                record["_rank"] = i + 1
                result.append(record)
            
            return result
            
        except Exception as e:
            logger.warning(f"生成 Top N 摘要失败: {e}")
            return []
