# -*- coding: utf-8 -*-
"""
StatisticalAnalyzer 测试

参考 Tableau Pulse 洞察类型：
- 分布分析
- 帕累托分析 (Concentrated Contribution)
- 异常检测 (Unexpected Values)
- 趋势检测 (Current Trend + Trend Change Alert)
- 相关性分析 (Correlated Metrics)
- Top N 摘要 (Top Contributors)

注意：已移除聚类分析测试（性能瓶颈，Tableau Pulse 也不使用）
"""

import pytest
import numpy as np
import pandas as pd

from tableau_assistant.src.agents.insight.components.statistical_analyzer import StatisticalAnalyzer
from tableau_assistant.src.agents.insight.models import DataProfile, SemanticGroup, ColumnStats


def make_column_stats(values: np.ndarray) -> ColumnStats:
    """从数据创建 ColumnStats"""
    return ColumnStats(
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        std=float(np.std(values)),
        min=float(np.min(values)),
        max=float(np.max(values)),
        q25=float(np.percentile(values, 25)),
        q75=float(np.percentile(values, 75)),
    )


class TestDistributionAnalysis:
    """分布分析测试"""
    
    def test_normal_distribution(self):
        """测试正态分布检测"""
        np.random.seed(42)
        values = np.random.normal(100, 10, 1000)
        data = [{"value": v} for v in values]
        
        profile = DataProfile(
            row_count=1000,
            column_count=1,
            density=1.0,
            semantic_groups=[],
            statistics={"value": make_column_stats(values)},
        )
        
        analyzer = StatisticalAnalyzer()
        result = analyzer.analyze(data, profile)
        
        print(f"\n正态分布检测:")
        print(f"  分布类型: {result.distribution_type}")
        print(f"  偏度: {result.skewness:.3f}")
        print(f"  峰度: {result.kurtosis:.3f}")
        
        assert result.distribution_type == "normal"
        assert abs(result.skewness) < 0.5
    
    def test_long_tail_distribution(self):
        """测试长尾分布检测"""
        np.random.seed(42)
        # 指数分布是典型的长尾分布
        values = np.random.exponential(scale=10, size=1000)
        data = [{"value": v} for v in values]
        
        profile = DataProfile(
            row_count=1000,
            column_count=1,
            density=1.0,
            semantic_groups=[],
            statistics={"value": make_column_stats(values)},
        )
        
        analyzer = StatisticalAnalyzer()
        result = analyzer.analyze(data, profile)
        
        print(f"\n长尾分布检测:")
        print(f"  分布类型: {result.distribution_type}")
        print(f"  偏度: {result.skewness:.3f}")
        
        assert result.distribution_type == "long_tail"
        assert result.skewness > 1


class TestParetoAnalysis:
    """帕累托分析测试 (Concentrated Contribution)"""
    
    def test_pareto_distribution(self):
        """测试帕累托分布（80/20法则）"""
        np.random.seed(42)
        # 创建符合帕累托分布的数据
        values = np.random.pareto(a=1.5, size=100) * 100
        data = [{"value": v} for v in values]
        
        profile = DataProfile(
            row_count=100,
            column_count=1,
            density=1.0,
            semantic_groups=[],
            statistics={"value": make_column_stats(values)},
        )
        
        analyzer = StatisticalAnalyzer()
        result = analyzer.analyze(data, profile)
        
        print(f"\n帕累托分析:")
        print(f"  Top 20% 贡献比例: {result.pareto_ratio:.2%}")
        print(f"  贡献 80% 的数据占比: {result.pareto_threshold:.2%}")
        
        # 帕累托分布应该有较高的集中度
        assert result.pareto_ratio > 0.5  # Top 20% 贡献超过 50%


class TestAnomalyDetection:
    """异常检测测试 (Unexpected Values)"""
    
    def test_detect_outliers(self):
        """测试异常值检测"""
        np.random.seed(42)
        # 正常数据 + 异常值
        normal_values = np.random.normal(100, 10, 95)
        outliers = np.array([200, 250, 300, 5, 0])  # 5个异常值
        values = np.concatenate([normal_values, outliers])
        
        data = [{"value": v} for v in values]
        
        profile = DataProfile(
            row_count=100,
            column_count=1,
            density=1.0,
            semantic_groups=[],
            statistics={"value": make_column_stats(values)},
        )
        
        analyzer = StatisticalAnalyzer()
        result = analyzer.analyze(data, profile)
        
        print(f"\n异常检测:")
        print(f"  异常值数量: {len(result.anomaly_indices)}")
        print(f"  异常比例: {result.anomaly_ratio:.2%}")
        print(f"  检测方法: {result.anomaly_method}")
        
        # 应该检测到异常值
        assert len(result.anomaly_indices) >= 3
        assert result.anomaly_method == "IQR"


class TestTrendDetection:
    """趋势检测测试 (Current Trend + Trend Change Alert)"""
    
    def test_increasing_trend(self):
        """测试上升趋势"""
        np.random.seed(42)
        x = np.arange(100)
        y = 2 * x + np.random.normal(0, 5, 100)
        
        data = [{"date": f"2024-01-{i+1:02d}", "value": v} for i, v in enumerate(y)]
        
        profile = DataProfile(
            row_count=100,
            column_count=2,
            density=1.0,
            semantic_groups=[SemanticGroup(type="time", columns=["date"])],
            statistics={"value": make_column_stats(y)},
        )
        
        analyzer = StatisticalAnalyzer()
        result = analyzer.analyze(data, profile)
        
        print(f"\n上升趋势检测:")
        print(f"  趋势: {result.trend}")
        print(f"  斜率: {result.trend_slope:.4f}")
        
        assert result.trend == "increasing"
        assert result.trend_slope > 0
    
    def test_decreasing_trend(self):
        """测试下降趋势"""
        np.random.seed(42)
        x = np.arange(100)
        y = -1.5 * x + 200 + np.random.normal(0, 5, 100)
        
        data = [{"date": f"2024-01-{i+1:02d}", "value": v} for i, v in enumerate(y)]
        
        profile = DataProfile(
            row_count=100,
            column_count=2,
            density=1.0,
            semantic_groups=[SemanticGroup(type="time", columns=["date"])],
            statistics={"value": make_column_stats(y)},
        )
        
        analyzer = StatisticalAnalyzer()
        result = analyzer.analyze(data, profile)
        
        print(f"\n下降趋势检测:")
        print(f"  趋势: {result.trend}")
        print(f"  斜率: {result.trend_slope:.4f}")
        
        assert result.trend == "decreasing"
        assert result.trend_slope < 0


class TestCorrelationAnalysis:
    """相关性分析测试 (Correlated Metrics)"""
    
    def test_positive_correlation(self):
        """测试正相关"""
        np.random.seed(42)
        x = np.random.normal(100, 10, 100)
        y = x * 2 + np.random.normal(0, 5, 100)  # 强正相关
        
        data = [{"x": xi, "y": yi} for xi, yi in zip(x, y)]
        
        profile = DataProfile(
            row_count=100,
            column_count=2,
            density=1.0,
            semantic_groups=[],
            statistics={
                "x": make_column_stats(x),
                "y": make_column_stats(y),
            },
        )
        
        analyzer = StatisticalAnalyzer()
        result = analyzer.analyze(data, profile)
        
        print(f"\n相关性分析:")
        print(f"  相关性: {result.correlations}")
        
        # 应该检测到强正相关
        assert "x|y" in result.correlations
        assert result.correlations["x|y"] > 0.9


class TestTopNSummary:
    """Top N 摘要测试 (Top Contributors)"""
    
    def test_top_n_summary(self):
        """测试 Top N 摘要生成"""
        np.random.seed(42)
        values = np.random.exponential(scale=100, size=100)
        categories = [f"cat_{i}" for i in range(100)]
        
        data = [{"category": c, "value": v} for c, v in zip(categories, values)]
        
        profile = DataProfile(
            row_count=100,
            column_count=2,
            density=1.0,
            semantic_groups=[],
            statistics={"value": make_column_stats(values)},
        )
        
        analyzer = StatisticalAnalyzer(top_n=5)
        result = analyzer.analyze(data, profile)
        
        print(f"\nTop N 摘要:")
        for item in result.top_n_summary:
            print(f"  #{item['_rank']}: {item['category']} = {item['value']:.2f}")
        
        # 应该返回 5 个 Top 记录
        assert len(result.top_n_summary) == 5
        # 应该按值降序排列
        values_sorted = [item["value"] for item in result.top_n_summary]
        assert values_sorted == sorted(values_sorted, reverse=True)


class TestEmptyProfile:
    """空数据测试"""
    
    def test_empty_data(self):
        """测试空数据返回空画像"""
        analyzer = StatisticalAnalyzer()
        profile = DataProfile(
            row_count=0,
            column_count=0,
            density=0.0,
            semantic_groups=[],
            statistics={},
        )
        
        result = analyzer.analyze([], profile)
        
        assert result.distribution_type == "unknown"
        assert result.clusters == []
        assert result.optimal_k == 0
        assert result.trend is None
        assert result.primary_measure is None
        assert result.top_n_summary == []


class TestChunkingStrategy:
    """分块策略推荐测试"""
    
    def test_recommend_by_change_point(self):
        """测试变点分块策略推荐"""
        np.random.seed(42)
        # 创建有明显变点的数据
        y1 = np.random.normal(50, 5, 50)
        y2 = np.random.normal(150, 5, 50)  # 明显跳变
        y = np.concatenate([y1, y2])
        
        data = [{"date": f"2024-{i+1:03d}", "value": v} for i, v in enumerate(y)]
        
        profile = DataProfile(
            row_count=100,
            column_count=2,
            density=1.0,
            semantic_groups=[SemanticGroup(type="time", columns=["date"])],
            statistics={"value": make_column_stats(y)},
        )
        
        analyzer = StatisticalAnalyzer()
        result = analyzer.analyze(data, profile)
        
        print(f"\n分块策略推荐:")
        print(f"  推荐策略: {result.recommended_chunking_strategy}")
        print(f"  变点: {result.change_points}")
        
        # 应该检测到变点并推荐 by_change_point 策略
        if result.change_points:
            assert result.recommended_chunking_strategy == "by_change_point"
    
    def test_recommend_by_pareto(self):
        """测试帕累托分块策略推荐"""
        np.random.seed(42)
        # 创建长尾分布数据（无时间列）
        values = np.random.pareto(a=1.5, size=100) * 100
        data = [{"value": v} for v in values]
        
        profile = DataProfile(
            row_count=100,
            column_count=1,
            density=1.0,
            semantic_groups=[],
            statistics={"value": make_column_stats(values)},
        )
        
        analyzer = StatisticalAnalyzer()
        result = analyzer.analyze(data, profile)
        
        print(f"\n帕累托分块策略:")
        print(f"  分布类型: {result.distribution_type}")
        print(f"  推荐策略: {result.recommended_chunking_strategy}")
        
        # 长尾分布应该推荐 by_pareto 策略
        assert result.distribution_type == "long_tail"
        assert result.recommended_chunking_strategy == "by_pareto"


class TestProfilerPerformance:
    """Profiler 性能测试"""
    
    def test_dimension_index_performance(self):
        """测试维度索引构建性能（向量化优化）"""
        import time
        from tableau_assistant.src.agents.insight.components.profiler import EnhancedDataProfiler
        
        np.random.seed(42)
        n_rows = 10000
        categories = [f"cat_{i}" for i in range(100)]
        
        data = {
            "category": np.random.choice(categories, n_rows),
            "value": np.random.normal(100, 20, n_rows),
        }
        df = pd.DataFrame(data)
        
        profiler = EnhancedDataProfiler()
        
        start_time = time.time()
        dim_index = profiler._build_single_dimension_index(df, "category")
        index_elapsed = time.time() - start_time
        
        print(f"\n维度索引构建性能:")
        print(f"  数据量: {n_rows} 行")
        print(f"  索引构建耗时: {index_elapsed:.4f} 秒")
        print(f"  唯一值数: {dim_index.total_unique_values}")
        
        assert dim_index.dimension == "category"
        assert dim_index.total_unique_values == 100
        assert index_elapsed < 0.1, f"维度索引构建性能不达标: {index_elapsed:.4f}s > 0.1s"
    
    def test_full_profile_performance(self):
        """测试完整 profile 性能"""
        import time
        from tableau_assistant.src.agents.insight.components.profiler import EnhancedDataProfiler
        
        np.random.seed(42)
        n_rows = 1000
        categories = [f"cat_{i}" for i in range(20)]
        
        data = {
            "category": np.random.choice(categories, n_rows),
            "value": np.random.normal(100, 20, n_rows),
        }
        df = pd.DataFrame(data)
        
        profiler = EnhancedDataProfiler()
        
        start_time = time.time()
        profile = profiler.profile(df)
        elapsed = time.time() - start_time
        
        print(f"\n完整 profile 性能:")
        print(f"  数据量: {n_rows} 行")
        print(f"  分析耗时: {elapsed:.3f} 秒")
        
        assert profile.row_count == n_rows
        assert len(profile.dimension_indices) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])



if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
