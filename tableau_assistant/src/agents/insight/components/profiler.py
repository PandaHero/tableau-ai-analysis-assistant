# -*- coding: utf-8 -*-
"""
EnhancedDataProfiler Component

Single entry point for data profiling with Tableau Pulse-aligned analyses.

Architecture (Task 3.3.1):
- EnhancedDataProfiler is the single entry point
- Delegates to StatisticalAnalyzer for distribution/clustering/correlation analysis
- Delegates to AnomalyDetector for anomaly detection
- Generates unified EnhancedDataProfile

Requirements:
- R8.1: Generate data profile (row_count, density, statistics)
- Enhanced: Top/Bottom contributor analysis
- Enhanced: Concentration risk detection
- Enhanced: Period-over-period change analysis (MoM, YoY)
- Enhanced: Trend detection and analysis
- Enhanced: Dimension index for precise reading
- Enhanced: Anomaly index grouped by severity
- Enhanced: Chunking strategy recommendation

Design Principles:
- Uses metadata.dimension_hierarchy for semantic grouping
- Generates Tableau Pulse style insights
- Builds indices for precise data access
- Single entry point - no duplicate code

Performance Note (Task 3.3.5 - 不实现缓存):
- 查询结果数据不做缓存，原因：
  1. 大数据序列化/反序列化比重新查询还慢
  2. 占用大量内存/存储
  3. 数据时效性问题，重新查询能拿到最新数据
- 如需数据，直接重新执行查询
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

from tableau_assistant.src.agents.insight.models import (
    DataProfile,
    ColumnStats,
    SemanticGroup,
    DataInsightProfile,
    ClusterInfo,
)
from tableau_assistant.src.agents.insight.models.profile import (
    EnhancedDataProfile,
    ContributorAnalysis,
    ConcentrationRisk,
    PeriodChangeAnalysis,
    TrendAnalysis,
    DimensionIndex,
    AnomalyIndex,
    ChunkingStrategy,
)
from .statistical_analyzer import StatisticalAnalyzer
from .anomaly_detector import AnomalyDetector
from .utils import to_dataframe

logger = logging.getLogger(__name__)


class EnhancedDataProfiler:
    """
    Enhanced Data Profiler - single entry point for data profiling.
    
    Architecture (Task 3.3.1):
    - Delegates statistical analysis to StatisticalAnalyzer
    - Delegates anomaly detection to AnomalyDetector
    - Generates unified EnhancedDataProfile with all analyses
    
    Analyzes:
    - Basic statistics (count, density, column stats)
    - Top/Bottom contributors (Tableau Pulse style)
    - Concentration risk (HHI index)
    - Period-over-period changes (MoM, YoY, etc.)
    - Trend detection (slope, R², change points) - delegated to StatisticalAnalyzer
    - Dimension indices (for precise reading)
    - Anomaly indices (grouped by severity) - delegated to AnomalyDetector
    - Chunking strategy recommendation
    - Distribution/Clustering/Correlation - delegated to StatisticalAnalyzer
    
    Design Note:
    Semantic grouping uses dimension_hierarchy from DimensionHierarchyAgent.
    """
    
    # Configuration constants
    TOP_N_CONTRIBUTORS = 5
    SIGNIFICANT_CHANGE_THRESHOLD = 0.05  # 5%
    TREND_R2_STRONG = 0.8
    TREND_R2_MODERATE = 0.5
    
    def __init__(
        self,
        dimension_hierarchy: Optional[Dict[str, Any]] = None,
        statistical_analyzer: Optional[StatisticalAnalyzer] = None,
        anomaly_detector: Optional[AnomalyDetector] = None,
    ):
        """
        Initialize enhanced profiler.
        
        Args:
            dimension_hierarchy: Dimension hierarchy info (from metadata.dimension_hierarchy)
                Format: {field_name: DimensionAttributes}
            statistical_analyzer: StatisticalAnalyzer instance (created if not provided)
            anomaly_detector: AnomalyDetector instance (created if not provided)
        """
        self._dimension_hierarchy = dimension_hierarchy or {}
        self._statistical_analyzer = statistical_analyzer or StatisticalAnalyzer()
        self._anomaly_detector = anomaly_detector or AnomalyDetector()
        self._last_insight_profile: Optional[DataInsightProfile] = None
    
    def set_dimension_hierarchy(self, hierarchy: Dict[str, Any]):
        """Set dimension hierarchy info."""
        self._dimension_hierarchy = hierarchy or {}
    
    def profile(self, data: Any) -> EnhancedDataProfile:
        """
        Generate an enhanced profile of the data.
        
        This is the single entry point for all profiling operations.
        Delegates to StatisticalAnalyzer and AnomalyDetector internally.
        
        Args:
            data: Input data (DataFrame, list of dicts, or dict)
            
        Returns:
            EnhancedDataProfile with all Tableau Pulse-aligned analyses
        """
        df = self._to_dataframe(data)
        
        if df.empty:
            self._last_insight_profile = self._statistical_analyzer._empty_profile()
            return EnhancedDataProfile(
                row_count=0,
                column_count=0,
                statistics={},
                recommended_strategy=ChunkingStrategy.BY_POSITION,
                strategy_reason="Empty dataset",
            )
        
        # Basic statistics
        statistics = self._calculate_statistics(df)
        
        # Identify column types
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        time_cols = self._identify_time_columns(df)
        
        # Build basic DataProfile for StatisticalAnalyzer
        basic_profile = self._build_basic_profile(df, statistics, time_cols, categorical_cols, numeric_cols)
        
        # Delegate to StatisticalAnalyzer for distribution/clustering/correlation
        # Pass DataFrame directly for better performance (avoid list conversion)
        # Cache the result to avoid duplicate computation in get_insight_profile()
        insight_profile = self._statistical_analyzer.analyze(df, basic_profile)
        self._last_insight_profile = insight_profile
        
        # Delegate to AnomalyDetector (also supports DataFrame directly)
        anomaly_result = self._anomaly_detector.detect(df)
        
        # Tableau Pulse style analyses (unique to EnhancedDataProfiler)
        contributor_analyses = self._analyze_contributors(df, categorical_cols, numeric_cols)
        concentration_risks = self._analyze_concentration(df, categorical_cols, numeric_cols)
        period_changes = self._analyze_period_changes(df, time_cols, numeric_cols)
        
        # Use trend from StatisticalAnalyzer instead of duplicating
        trend_analyses = self._convert_trend_from_insight_profile(insight_profile, time_cols, numeric_cols)
        
        # Build indices
        dimension_indices = self._build_dimension_indices(df, categorical_cols)
        
        # Build anomaly index from AnomalyDetector result
        anomaly_index = self._build_anomaly_index_from_result(df, anomaly_result, numeric_cols)
        
        # Recommend strategy (unified logic)
        strategy, reason = self._recommend_strategy(
            df=df,
            contributor_analyses=contributor_analyses,
            concentration_risks=concentration_risks,
            insight_profile=insight_profile,
            anomaly_index=anomaly_index,
        )
        
        # Generate summary
        profile_summary = self._generate_summary(
            df, contributor_analyses, concentration_risks,
            period_changes, trend_analyses, anomaly_index
        )
        
        profile = EnhancedDataProfile(
            row_count=len(df),
            column_count=len(df.columns),
            statistics=statistics,
            contributor_analyses=contributor_analyses,
            concentration_risks=concentration_risks,
            period_changes=period_changes,
            trend_analyses=trend_analyses,
            dimension_indices=dimension_indices,
            anomaly_index=anomaly_index,
            recommended_strategy=strategy,
            strategy_reason=reason,
            profile_summary=profile_summary,
        )
        
        return profile
    
    def get_insight_profile(self, data: Any) -> DataInsightProfile:
        """
        Get DataInsightProfile for chunking strategy.
        
        This method provides access to the StatisticalAnalyzer's output
        which is used by SemanticChunker to determine chunking strategy.
        
        Note: If profile() was called first, returns cached result to avoid
        duplicate computation.
        
        Args:
            data: Input data
            
        Returns:
            DataInsightProfile from StatisticalAnalyzer
        """
        # Return cached result if available (from profile() call)
        if self._last_insight_profile is not None:
            return self._last_insight_profile
        
        # Otherwise compute fresh
        df = self._to_dataframe(data)
        if df.empty:
            return self._statistical_analyzer._empty_profile()
        
        statistics = self._calculate_statistics(df)
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        time_cols = self._identify_time_columns(df)
        
        basic_profile = self._build_basic_profile(df, statistics, time_cols, categorical_cols, numeric_cols)
        
        # Pass DataFrame directly for better performance
        return self._statistical_analyzer.analyze(df, basic_profile)
    
    def _build_basic_profile(
        self,
        df: pd.DataFrame,
        statistics: Dict[str, ColumnStats],
        time_cols: List[str],
        categorical_cols: List[str],
        numeric_cols: List[str],
    ) -> DataProfile:
        """Build basic DataProfile for StatisticalAnalyzer."""
        # Build semantic groups
        semantic_groups = []
        
        if time_cols:
            semantic_groups.append(SemanticGroup(type="time", columns=time_cols))
        if categorical_cols:
            semantic_groups.append(SemanticGroup(type="category", columns=categorical_cols))
        if numeric_cols:
            semantic_groups.append(SemanticGroup(type="numeric", columns=numeric_cols))
        
        # Calculate density
        total_cells = df.size
        non_null_cells = df.count().sum()
        density = non_null_cells / total_cells if total_cells > 0 else 0.0
        
        return DataProfile(
            row_count=len(df),
            column_count=len(df.columns),
            density=density,
            statistics=statistics,
            semantic_groups=semantic_groups,
        )
    
    def _to_dataframe(self, data: Any) -> pd.DataFrame:
        """Convert various data formats to DataFrame."""
        return to_dataframe(data)
    
    def _calculate_statistics(self, df: pd.DataFrame) -> Dict[str, ColumnStats]:
        """Calculate statistics for numeric columns."""
        stats = {}
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            try:
                col_data = df[col].dropna()
                if len(col_data) == 0:
                    continue
                
                stats[col] = ColumnStats(
                    mean=float(col_data.mean()),
                    median=float(col_data.median()),
                    std=float(col_data.std()) if len(col_data) > 1 else 0.0,
                    min=float(col_data.min()),
                    max=float(col_data.max()),
                    q25=float(col_data.quantile(0.25)),
                    q75=float(col_data.quantile(0.75)),
                )
            except Exception as e:
                logger.warning(f"Failed to calculate stats for column {col}: {e}")
        
        return stats
    
    def _identify_time_columns(self, df: pd.DataFrame) -> List[str]:
        """Identify time-related columns."""
        time_cols = []
        
        # Check dimension hierarchy first
        for col in df.columns:
            if col in self._dimension_hierarchy:
                attrs = self._dimension_hierarchy[col]
                category = attrs.get("category") if isinstance(attrs, dict) else getattr(attrs, "category", None)
                if category == "time":
                    time_cols.append(col)
                    continue
        
        # Check datetime dtype
        for col in df.columns:
            if col not in time_cols:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    time_cols.append(col)
        
        return time_cols


    def _analyze_contributors(
        self, 
        df: pd.DataFrame, 
        categorical_cols: List[str], 
        numeric_cols: List[str]
    ) -> List[ContributorAnalysis]:
        """
        Analyze top/bottom contributors - Tableau Pulse style.
        
        For each categorical dimension and numeric measure combination,
        identifies top and bottom contributors.
        """
        analyses = []
        
        if not categorical_cols or not numeric_cols:
            return analyses
        
        # Limit to first 3 categorical and first 2 numeric columns
        cat_cols = categorical_cols[:3]
        num_cols = numeric_cols[:2]
        
        for dim_col in cat_cols:
            for measure_col in num_cols:
                try:
                    analysis = self._analyze_single_contributor(df, dim_col, measure_col)
                    if analysis:
                        analyses.append(analysis)
                except Exception as e:
                    logger.warning(f"Failed to analyze contributors for {dim_col}/{measure_col}: {e}")
        
        return analyses
    
    def _analyze_single_contributor(
        self, 
        df: pd.DataFrame, 
        dim_col: str, 
        measure_col: str
    ) -> Optional[ContributorAnalysis]:
        """Analyze contributors for a single dimension/measure pair."""
        # Group by dimension and sum measure
        grouped = df.groupby(dim_col)[measure_col].sum().sort_values(ascending=False)
        
        if len(grouped) == 0:
            return None
        
        total = grouped.sum()
        if total == 0:
            return None
        
        # Top contributors
        top_n = min(self.TOP_N_CONTRIBUTORS, len(grouped))
        top_contributors = []
        for value, amount in grouped.head(top_n).items():
            top_contributors.append({
                "value": str(value),
                "amount": float(amount),
                "percentage": float(amount / total) if total != 0 else 0.0,
            })
        
        # Bottom contributors
        bottom_contributors = []
        for value, amount in grouped.tail(top_n).items():
            bottom_contributors.append({
                "value": str(value),
                "amount": float(amount),
                "percentage": float(amount / total) if total != 0 else 0.0,
            })
        
        # Top contribution percentage
        top_contribution_pct = sum(c["percentage"] for c in top_contributors)
        
        # Concentration warning
        concentration_warning = None
        if top_contribution_pct > 0.8:
            concentration_warning = f"Top {top_n} contributors account for {top_contribution_pct*100:.1f}% of total"
        
        return ContributorAnalysis(
            dimension=dim_col,
            measure=measure_col,
            top_contributors=top_contributors,
            bottom_contributors=bottom_contributors,
            top_contribution_pct=top_contribution_pct,
            concentration_warning=concentration_warning,
        )
    
    def _analyze_concentration(
        self, 
        df: pd.DataFrame, 
        categorical_cols: List[str], 
        numeric_cols: List[str]
    ) -> List[ConcentrationRisk]:
        """
        Analyze concentration risk - Tableau Pulse style.
        
        Uses Herfindahl-Hirschman Index (HHI) to measure concentration.
        """
        risks = []
        
        if not categorical_cols or not numeric_cols:
            return risks
        
        # Limit to first 3 categorical and first 2 numeric columns
        cat_cols = categorical_cols[:3]
        num_cols = numeric_cols[:2]
        
        for dim_col in cat_cols:
            for measure_col in num_cols:
                try:
                    risk = self._analyze_single_concentration(df, dim_col, measure_col)
                    if risk:
                        risks.append(risk)
                except Exception as e:
                    logger.warning(f"Failed to analyze concentration for {dim_col}/{measure_col}: {e}")
        
        return risks
    
    def _analyze_single_concentration(
        self, 
        df: pd.DataFrame, 
        dim_col: str, 
        measure_col: str
    ) -> Optional[ConcentrationRisk]:
        """Analyze concentration for a single dimension/measure pair."""
        grouped = df.groupby(dim_col)[measure_col].sum()
        
        if len(grouped) == 0:
            return None
        
        total = grouped.sum()
        if total == 0:
            return None
        
        # Calculate HHI (sum of squared market shares)
        shares = grouped / total
        hhi = float((shares ** 2).sum())
        
        # Determine risk level
        if hhi >= 0.5:
            risk_level = "critical"
        elif hhi >= 0.25:
            risk_level = "high"
        elif hhi >= 0.15:
            risk_level = "medium"
        else:
            risk_level = "low"
        
        # Calculate top N for 80%
        sorted_shares = shares.sort_values(ascending=False)
        cumsum = sorted_shares.cumsum()
        top_n_for_80 = int((cumsum <= 0.8).sum()) + 1
        top_n_for_80 = min(top_n_for_80, len(sorted_shares))
        
        # Recommendation
        recommendation = None
        if risk_level in ["medium", "high", "critical"]:
            recommendation = f"Consider diversifying {dim_col} to reduce concentration risk"
        
        return ConcentrationRisk(
            dimension=dim_col,
            measure=measure_col,
            hhi_index=hhi,
            risk_level=risk_level,
            top_n_for_80_pct=top_n_for_80,
            recommendation=recommendation,
        )
    
    def _analyze_period_changes(
        self, 
        df: pd.DataFrame, 
        time_cols: List[str], 
        numeric_cols: List[str]
    ) -> List[PeriodChangeAnalysis]:
        """
        Analyze period-over-period changes - Tableau Pulse style.
        
        Detects MoM, YoY, etc. changes based on time granularity.
        """
        changes = []
        
        if not time_cols or not numeric_cols:
            return changes
        
        time_col = time_cols[0]  # Use first time column
        num_cols = numeric_cols[:2]  # Limit to first 2 measures
        
        for measure_col in num_cols:
            try:
                change = self._analyze_single_period_change(df, time_col, measure_col)
                if change:
                    changes.append(change)
            except Exception as e:
                logger.warning(f"Failed to analyze period change for {measure_col}: {e}")
        
        return changes
    
    def _analyze_single_period_change(
        self, 
        df: pd.DataFrame, 
        time_col: str, 
        measure_col: str
    ) -> Optional[PeriodChangeAnalysis]:
        """Analyze period change for a single measure."""
        # Sort by time
        df_sorted = df.sort_values(time_col)
        
        # Group by time and sum measure
        grouped = df_sorted.groupby(time_col)[measure_col].sum()
        
        if len(grouped) < 2:
            return None
        
        # Get current and previous values
        current_value = float(grouped.iloc[-1])
        previous_value = float(grouped.iloc[-2])
        
        if previous_value == 0:
            return None
        
        # Calculate changes
        absolute_change = current_value - previous_value
        percentage_change = (absolute_change / previous_value) * 100
        
        # Determine direction
        if percentage_change > 1:
            change_direction = "up"
        elif percentage_change < -1:
            change_direction = "down"
        else:
            change_direction = "stable"
        
        # Determine significance
        is_significant = abs(percentage_change) > self.SIGNIFICANT_CHANGE_THRESHOLD * 100
        
        # Determine period type (simplified)
        period_type = "custom"
        
        return PeriodChangeAnalysis(
            measure=measure_col,
            period_type=period_type,
            current_value=current_value,
            previous_value=previous_value,
            absolute_change=absolute_change,
            percentage_change=percentage_change,
            change_direction=change_direction,
            is_significant=is_significant,
            current_period=str(grouped.index[-1]),
            previous_period=str(grouped.index[-2]),
        )


    def _convert_trend_from_insight_profile(
        self,
        insight_profile: DataInsightProfile,
        time_cols: List[str],
        numeric_cols: List[str],
    ) -> List[TrendAnalysis]:
        """
        Convert trend info from DataInsightProfile to TrendAnalysis list.
        
        This avoids duplicating trend detection logic - we use StatisticalAnalyzer's
        trend detection and convert the result to TrendAnalysis format.
        """
        trends = []
        
        if not insight_profile.trend or not time_cols or not numeric_cols:
            return trends
        
        # Convert StatisticalAnalyzer's trend to TrendAnalysis
        time_col = time_cols[0]
        measure_col = insight_profile.primary_measure or (numeric_cols[0] if numeric_cols else "unknown")
        
        # Map trend direction
        trend_direction = insight_profile.trend
        if trend_direction not in ["increasing", "decreasing", "stable"]:
            trend_direction = "volatile"
        
        # Determine trend strength based on slope
        slope = insight_profile.trend_slope or 0.0
        # Simple heuristic: if we have trend, assume moderate strength
        # (StatisticalAnalyzer doesn't calculate R² directly)
        trend_strength = "moderate" if insight_profile.trend else "weak"
        
        # Convert change points
        change_points = []
        if insight_profile.change_points:
            for idx in insight_profile.change_points:
                change_points.append({
                    "index": idx,
                    "date": None,
                    "type": "change",
                })
        
        trends.append(TrendAnalysis(
            measure=measure_col,
            time_dimension=time_col,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            slope=slope,
            r_squared=0.5,  # Default, StatisticalAnalyzer doesn't expose this
            change_points=change_points,
            change_point_method=insight_profile.change_point_method,
        ))
        
        return trends
    
    def _build_dimension_indices(
        self, 
        df: pd.DataFrame, 
        categorical_cols: List[str]
    ) -> List[DimensionIndex]:
        """
        Build dimension value indices for precise reading.
        
        Maps each dimension value to its row indices.
        """
        indices = []
        
        # Limit to first 5 categorical columns
        cat_cols = categorical_cols[:5]
        
        for col in cat_cols:
            try:
                index = self._build_single_dimension_index(df, col)
                if index:
                    indices.append(index)
            except Exception as e:
                logger.warning(f"Failed to build dimension index for {col}: {e}")
        
        return indices
    
    def _build_single_dimension_index(
        self, 
        df: pd.DataFrame, 
        col: str
    ) -> Optional[DimensionIndex]:
        """
        Build index for a single dimension.
        
        Optimized using pandas groupby for better performance on large datasets.
        """
        # Use pandas groupby.groups for vectorized index mapping
        # This is much faster than Python loops for large datasets
        grouped = df.groupby(col, sort=False)
        
        # Get value to indices mapping (vectorized)
        value_to_indices: Dict[str, List[int]] = {
            str(value): list(indices)
            for value, indices in grouped.groups.items()
        }
        
        # Get value counts (vectorized)
        value_counts: Dict[str, int] = {
            str(value): count
            for value, count in df[col].value_counts().items()
        }
        
        return DimensionIndex(
            dimension=col,
            value_to_indices=value_to_indices,
            total_unique_values=len(value_to_indices),
            value_counts=value_counts,
        )
    
    def _build_anomaly_index_from_result(
        self,
        df: pd.DataFrame,
        anomaly_result: Any,
        numeric_cols: List[str],
    ) -> Optional[AnomalyIndex]:
        """
        Build AnomalyIndex from AnomalyDetector result.
        
        Converts AnomalyResult to AnomalyIndex format with severity grouping.
        """
        if not anomaly_result or not anomaly_result.outliers:
            return AnomalyIndex(
                total_anomalies=0,
                anomaly_ratio=0.0,
                by_severity={},
                by_column={},
                detection_method="IQR",
            )
        
        # Group by severity using AnomalyDetail
        by_severity: Dict[str, List[int]] = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
        }
        by_column: Dict[str, List[int]] = {}
        
        for detail in anomaly_result.anomaly_details:
            idx = detail.index
            severity = detail.severity
            
            # Map severity score to level
            if severity >= 0.75:
                by_severity["critical"].append(idx)
            elif severity >= 0.5:
                by_severity["high"].append(idx)
            elif severity >= 0.25:
                by_severity["medium"].append(idx)
            else:
                by_severity["low"].append(idx)
            
            # Group by column
            if detail.column:
                if detail.column not in by_column:
                    by_column[detail.column] = []
                by_column[detail.column].append(idx)
        
        return AnomalyIndex(
            total_anomalies=len(anomaly_result.outliers),
            anomaly_ratio=anomaly_result.anomaly_ratio,
            by_severity=by_severity,
            by_column=by_column,
            detection_method="IQR",
        )
    
    def _recommend_strategy(
        self,
        df: pd.DataFrame,
        contributor_analyses: List[ContributorAnalysis],
        concentration_risks: List[ConcentrationRisk],
        insight_profile: DataInsightProfile,
        anomaly_index: Optional[AnomalyIndex],
    ) -> Tuple[ChunkingStrategy, str]:
        """
        Recommend chunking strategy based on data characteristics.
        
        Unified logic using both EnhancedDataProfiler analyses and
        StatisticalAnalyzer's DataInsightProfile.
        
        Priority order:
        1. High anomaly ratio -> by_anomaly (isolate anomalies for priority analysis)
        2. High concentration -> by_pareto (focus on top contributors)
        3. Change points detected -> by_change_point
        4. Long tail distribution -> by_pareto
        5. Clear semantic groups -> by_semantic
        6. Default -> by_position
        """
        # Check anomaly ratio - isolate anomalies for priority analysis
        if anomaly_index and anomaly_index.anomaly_ratio > 0.1:
            return (
                ChunkingStrategy.BY_ANOMALY,
                f"High anomaly ratio ({anomaly_index.anomaly_ratio*100:.1f}%), recommend isolating anomalies"
            )
        
        # Check concentration
        high_concentration = any(
            risk.risk_level in ["high", "critical"] 
            for risk in concentration_risks
        )
        if high_concentration:
            return (
                ChunkingStrategy.BY_PARETO,
                "High concentration detected, recommend focusing on top contributors"
            )
        
        # Check change points from StatisticalAnalyzer
        if insight_profile.change_points and len(insight_profile.change_points) >= 1:
            return (
                ChunkingStrategy.BY_CHANGE_POINT,
                "Significant change points detected, recommend splitting at change points"
            )
        
        # Check long tail distribution
        if insight_profile.distribution_type == "long_tail":
            return (
                ChunkingStrategy.BY_PARETO,
                "Long tail distribution detected, recommend Pareto-based chunking"
            )
        
        # Check semantic groups
        if self._dimension_hierarchy:
            return (
                ChunkingStrategy.BY_SEMANTIC,
                "Clear semantic groupings available, recommend grouping by semantic type"
            )
        
        # Default
        return (
            ChunkingStrategy.BY_POSITION,
            "No special patterns detected, using position-based chunking"
        )
    
    def _generate_summary(
        self,
        df: pd.DataFrame,
        contributor_analyses: List[ContributorAnalysis],
        concentration_risks: List[ConcentrationRisk],
        period_changes: List[PeriodChangeAnalysis],
        trend_analyses: List[TrendAnalysis],
        anomaly_index: Optional[AnomalyIndex],
    ) -> str:
        """Generate natural language summary for Director LLM."""
        parts = []
        
        # Basic info
        parts.append(f"Dataset: {len(df)} rows, {len(df.columns)} columns.")
        
        # Top contributors
        if contributor_analyses:
            top_analysis = contributor_analyses[0]
            if top_analysis.top_contributors:
                top_value = top_analysis.top_contributors[0]["value"]
                top_pct = top_analysis.top_contributors[0]["percentage"] * 100
                parts.append(
                    f"Top contributor: {top_value} ({top_pct:.1f}% of {top_analysis.measure})."
                )
        
        # Concentration risks
        critical_risks = [r for r in concentration_risks if r.risk_level in ["high", "critical"]]
        if critical_risks:
            parts.append(
                f"Warning: {len(critical_risks)} high concentration risk(s) detected."
            )
        
        # Period changes
        significant_changes = [c for c in period_changes if c.is_significant]
        if significant_changes:
            change = significant_changes[0]
            direction = "increased" if change.change_direction == "up" else "decreased"
            parts.append(
                f"{change.measure} {direction} {abs(change.percentage_change):.1f}% vs previous period."
            )
        
        # Trends
        strong_trends = [t for t in trend_analyses if t.trend_strength == "strong"]
        if strong_trends:
            trend = strong_trends[0]
            parts.append(
                f"Strong {trend.trend_direction} trend in {trend.measure} (R²={trend.r_squared:.2f})."
            )
        
        # Anomalies
        if anomaly_index and anomaly_index.total_anomalies > 0:
            critical_count = len(anomaly_index.by_severity.get("critical", []))
            if critical_count > 0:
                parts.append(f"{critical_count} critical anomalies detected.")
            else:
                parts.append(f"{anomaly_index.total_anomalies} anomalies detected.")
        
        return " ".join(parts)
    
    # =========================================================================
    # Utility methods
    # =========================================================================
    
    def get_columns_by_category(self, category: str) -> List[str]:
        """
        Get columns by category.
        
        Args:
            category: Category name (geography, time, product, etc.)
            
        Returns:
            List of column names in that category
        """
        columns = []
        for col, attrs in self._dimension_hierarchy.items():
            col_category = attrs.get("category") if isinstance(attrs, dict) else getattr(attrs, "category", None)
            if col_category == category:
                columns.append(col)
        return columns
    
    def get_hierarchy_level(self, column: str) -> Optional[int]:
        """
        Get hierarchy level for a column.
        
        Args:
            column: Column name
            
        Returns:
            Hierarchy level (1-5), or None if not in hierarchy
        """
        if column in self._dimension_hierarchy:
            attrs = self._dimension_hierarchy[column]
            return attrs.get("level") if isinstance(attrs, dict) else getattr(attrs, "level", None)
        return None


__all__ = [
    "EnhancedDataProfiler",
]
