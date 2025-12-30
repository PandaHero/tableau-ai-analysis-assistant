# -*- coding: utf-8 -*-
"""
大数据性能测试 (10万行)

参考 Tableau Pulse 洞察类型，所有算法复杂度 <= O(n log n)：
- 分布分析: O(n)
- 帕累托分析: O(n log n)
- 异常检测: O(n)
- 趋势检测: O(n)
- 相关性分析: O(n)
- Top N 摘要: O(n log n)

注意：已移除聚类分析（O(n²) 性能瓶颈）
"""

import time
import numpy as np
import pandas as pd
import pytest

from tableau_assistant.src.agents.insight.components.profiler import EnhancedDataProfiler
from tableau_assistant.src.agents.insight.components.statistical_analyzer import StatisticalAnalyzer
from tableau_assistant.src.agents.insight.models import DataProfile, SemanticGroup, ColumnStats


def make_column_stats(values: np.ndarray) -> ColumnStats:
    return ColumnStats(
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        std=float(np.std(values)),
        min=float(np.min(values)),
        max=float(np.max(values)),
        q25=float(np.percentile(values, 25)),
        q75=float(np.percentile(values, 75)),
    )


def test_large_data_performance():
    """测试 10 万行数据性能"""
    np.random.seed(42)
    n_rows = 100000
    categories = [f"cat_{i}" for i in range(500)]
    
    print(f"\n{'='*60}")
    print(f"大数据性能测试: {n_rows:,} 行")
    print(f"{'='*60}\n")
    
    # 创建大数据集
    start = time.time()
    data = {
        "category": np.random.choice(categories, n_rows),
        "region": np.random.choice(["North", "South", "East", "West"], n_rows),
        "value": np.random.normal(100, 20, n_rows),
        "value2": np.random.normal(50, 10, n_rows),
        "value3": np.random.normal(200, 50, n_rows),
    }
    df = pd.DataFrame(data)
    print(f"数据创建: {time.time() - start:.3f}s")
    
    # 测试 StatisticalAnalyzer 各步骤
    print("\nStatisticalAnalyzer 分步耗时:")
    analyzer = StatisticalAnalyzer()
    
    values = df["value"].dropna()
    numeric_cols = ["value", "value2", "value3"]
    
    # 分布分析 O(n)
    start = time.time()
    analyzer._analyze_distribution(values)
    dist_time = time.time() - start
    print(f"  分布分析: {dist_time:.4f}s")
    
    # 帕累托分析 O(n log n)
    start = time.time()
    analyzer._analyze_pareto(values)
    pareto_time = time.time() - start
    print(f"  帕累托分析: {pareto_time:.4f}s")
    
    # 异常检测 O(n)
    start = time.time()
    analyzer._detect_anomalies(values)
    anomaly_time = time.time() - start
    print(f"  异常检测: {anomaly_time:.4f}s")
    
    # 相关性分析 O(n)
    start = time.time()
    analyzer._calculate_correlations(df, numeric_cols)
    corr_time = time.time() - start
    print(f"  相关性分析: {corr_time:.4f}s")
    
    # Top N 摘要 O(n log n)
    start = time.time()
    analyzer._generate_top_n_summary(df, "value")
    topn_time = time.time() - start
    print(f"  Top N 摘要: {topn_time:.4f}s")
    
    # 测试 EnhancedDataProfiler 完整流程
    print("\nEnhancedDataProfiler 完整流程:")
    profiler = EnhancedDataProfiler()
    
    start = time.time()
    profile = profiler.profile(df)
    total = time.time() - start
    
    print(f"  总耗时: {total:.3f}s")
    print(f"  维度索引数: {len(profile.dimension_indices)}")
    print(f"  推荐策略: {profile.recommended_strategy}")
    
    # 性能断言：10万行应该在 5 秒内完成
    assert total < 5.0, f"性能不达标: {total:.3f}s > 5s (10万行)"
    
    print(f"\n{'='*60}")
    print(f"✅ 性能测试通过: {total:.3f}s < 5s")
    print(f"{'='*60}")


def test_statistical_analyzer_only():
    """单独测试 StatisticalAnalyzer 性能"""
    np.random.seed(42)
    n_rows = 100000
    
    print(f"\n{'='*60}")
    print(f"StatisticalAnalyzer 性能测试: {n_rows:,} 行")
    print(f"{'='*60}\n")
    
    # 创建数据
    values = np.random.normal(100, 20, n_rows)
    data = [{"value": v} for v in values]
    
    profile = DataProfile(
        row_count=n_rows,
        column_count=1,
        density=1.0,
        semantic_groups=[],
        statistics={"value": make_column_stats(values)},
    )
    
    analyzer = StatisticalAnalyzer()
    
    start = time.time()
    result = analyzer.analyze(data, profile)
    elapsed = time.time() - start
    
    print(f"分析结果:")
    print(f"  分布类型: {result.distribution_type}")
    print(f"  帕累托比例: {result.pareto_ratio:.2%}")
    print(f"  异常值数: {len(result.anomaly_indices)}")
    print(f"  推荐策略: {result.recommended_chunking_strategy}")
    print(f"\n总耗时: {elapsed:.3f}s")
    
    # 性能断言：StatisticalAnalyzer 应该在 2 秒内完成
    assert elapsed < 2.0, f"性能不达标: {elapsed:.3f}s > 2s"
    
    print(f"\n✅ 性能测试通过: {elapsed:.3f}s < 2s")


def test_dimension_index_large_scale():
    """测试大规模维度索引构建性能"""
    np.random.seed(42)
    n_rows = 100000
    n_categories = 1000  # 1000 个唯一值
    
    print(f"\n{'='*60}")
    print(f"维度索引性能测试: {n_rows:,} 行, {n_categories} 唯一值")
    print(f"{'='*60}\n")
    
    categories = [f"cat_{i}" for i in range(n_categories)]
    data = {
        "category": np.random.choice(categories, n_rows),
        "value": np.random.normal(100, 20, n_rows),
    }
    df = pd.DataFrame(data)
    
    profiler = EnhancedDataProfiler()
    
    start = time.time()
    dim_index = profiler._build_single_dimension_index(df, "category")
    elapsed = time.time() - start
    
    print(f"维度索引构建:")
    print(f"  唯一值数: {dim_index.total_unique_values}")
    print(f"  耗时: {elapsed:.4f}s")
    
    # 性能断言：维度索引构建应该在 0.5 秒内完成
    assert elapsed < 0.5, f"性能不达标: {elapsed:.4f}s > 0.5s"
    
    print(f"\n✅ 性能测试通过: {elapsed:.4f}s < 0.5s")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
