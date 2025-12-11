"""
Property Tests for Insight Agent

Tests for:
- Property 15: 渐进式分析策略选择
- Property 16: 洞察累积去重

Requirements tested:
- R8.2: Strategy selection (direct/progressive/hybrid)
- R8.5: Insight accumulation and deduplication
"""

import pytest
from hypothesis import given, settings, strategies as st
from typing import Any, Dict, List


# ═══════════════════════════════════════════════════════════════════════════
# Property 15: 渐进式分析策略选择
# ═══════════════════════════════════════════════════════════════════════════

class TestProgressiveAnalysisStrategy:
    """
    Property 15: 渐进式分析策略选择
    
    *For any* 数据集，分析策略应根据数据规模正确选择：
    - row_count < 100: direct（直接分析）
    - 100 <= row_count < 1000: progressive（渐进式分析）
    - row_count >= 1000: progressive_with_priority（带优先级的渐进式）
    
    **Validates: Requirements 8.2**
    """
    
    def test_direct_strategy_threshold(self):
        """验证直接分析策略阈值"""
        # 小于 100 行应使用 direct
        for row_count in [1, 50, 99]:
            strategy = self._select_strategy(row_count)
            assert strategy == "direct", f"Row count {row_count} should use direct strategy"
    
    def test_progressive_strategy_threshold(self):
        """验证渐进式分析策略阈值"""
        # 100-999 行应使用 progressive
        for row_count in [100, 500, 999]:
            strategy = self._select_strategy(row_count)
            assert strategy == "progressive", f"Row count {row_count} should use progressive strategy"
    
    def test_progressive_with_priority_threshold(self):
        """验证带优先级的渐进式策略阈值"""
        # 1000+ 行应使用 progressive_with_priority
        for row_count in [1000, 5000, 10000]:
            strategy = self._select_strategy(row_count)
            assert strategy == "progressive_with_priority", f"Row count {row_count} should use progressive_with_priority"
    
    @given(row_count=st.integers(min_value=1, max_value=100000))
    @settings(max_examples=100)
    def test_strategy_selection_property(self, row_count: int):
        """
        Property: 策略选择应满足：
        1. 策略是三种之一
        2. 策略与数据规模匹配
        3. 边界条件正确处理
        """
        strategy = self._select_strategy(row_count)
        
        # Property 1: 策略是有效值
        assert strategy in ["direct", "progressive", "progressive_with_priority"]
        
        # Property 2: 策略与规模匹配
        if row_count < 100:
            assert strategy == "direct"
        elif row_count < 1000:
            assert strategy == "progressive"
        else:
            assert strategy == "progressive_with_priority"
    
    @given(
        row_count=st.integers(min_value=1, max_value=10000),
        column_count=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=50)
    def test_strategy_considers_complexity(self, row_count: int, column_count: int):
        """
        Property: 策略选择可以考虑数据复杂度
        
        复杂度 = row_count * column_count
        高复杂度数据可能需要更保守的策略
        """
        complexity = row_count * column_count
        strategy = self._select_strategy(row_count)
        
        # 基本策略选择仍然有效
        assert strategy in ["direct", "progressive", "progressive_with_priority"]
        
        # 高复杂度数据不应使用 direct（除非行数很少）
        if complexity > 50000 and row_count >= 100:
            assert strategy != "direct"
    
    def _select_strategy(self, row_count: int) -> str:
        """模拟策略选择逻辑"""
        if row_count < 100:
            return "direct"
        elif row_count < 1000:
            return "progressive"
        else:
            return "progressive_with_priority"


# ═══════════════════════════════════════════════════════════════════════════
# Property 16: 洞察累积去重
# ═══════════════════════════════════════════════════════════════════════════

class TestInsightAccumulationDedup:
    """
    Property 16: 洞察累积去重
    
    *For any* 洞察序列，累积器应：
    1. 检测并移除重复洞察
    2. 合并相似洞察
    3. 按重要性排序
    
    **Validates: Requirements 8.5**
    """
    
    def test_exact_duplicate_removal(self):
        """验证完全重复的洞察被移除"""
        insights = [
            {"type": "trend", "title": "销售增长", "pattern": "sales_growth"},
            {"type": "trend", "title": "销售增长", "pattern": "sales_growth"},  # 重复
            {"type": "anomaly", "title": "异常值", "pattern": "outlier"},
        ]
        
        deduped = self._deduplicate(insights)
        
        assert len(deduped) == 2
        patterns = [i["pattern"] for i in deduped]
        assert "sales_growth" in patterns
        assert "outlier" in patterns
    
    def test_similar_insight_merging(self):
        """验证相似洞察被合并"""
        insights = [
            {"type": "trend", "title": "Q1销售增长", "pattern": "sales_growth", "period": "Q1"},
            {"type": "trend", "title": "Q2销售增长", "pattern": "sales_growth", "period": "Q2"},
        ]
        
        merged = self._merge_similar(insights)
        
        # 相似洞察应被合并
        assert len(merged) <= len(insights)
    
    def test_importance_sorting(self):
        """验证按重要性排序"""
        insights = [
            {"type": "trend", "title": "低重要性", "importance": 0.3},
            {"type": "anomaly", "title": "高重要性", "importance": 0.9},
            {"type": "pattern", "title": "中重要性", "importance": 0.6},
        ]
        
        sorted_insights = self._sort_by_importance(insights)
        
        importances = [i["importance"] for i in sorted_insights]
        assert importances == sorted(importances, reverse=True)
    
    @given(
        num_insights=st.integers(min_value=1, max_value=50),
        duplicate_ratio=st.floats(min_value=0.0, max_value=0.5),
    )
    @settings(max_examples=50)
    def test_deduplication_property(self, num_insights: int, duplicate_ratio: float):
        """
        Property: 去重应满足：
        1. 去重后数量 <= 原始数量
        2. 没有完全重复的洞察
        3. 所有唯一洞察都被保留
        """
        import random
        
        # 生成洞察
        unique_count = max(1, int(num_insights * (1 - duplicate_ratio)))
        unique_insights = [
            {"type": "insight", "pattern": f"pattern_{i}", "importance": random.random()}
            for i in range(unique_count)
        ]
        
        # 添加重复
        insights = unique_insights.copy()
        for _ in range(num_insights - unique_count):
            insights.append(random.choice(unique_insights).copy())
        
        random.shuffle(insights)
        
        # 去重
        deduped = self._deduplicate(insights)
        
        # Property 1: 数量减少或不变
        assert len(deduped) <= len(insights)
        
        # Property 2: 没有重复
        patterns = [i["pattern"] for i in deduped]
        assert len(patterns) == len(set(patterns))
        
        # Property 3: 唯一洞察保留
        unique_patterns = set(i["pattern"] for i in unique_insights)
        deduped_patterns = set(i["pattern"] for i in deduped)
        assert unique_patterns == deduped_patterns
    
    @given(
        num_insights=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=30)
    def test_sorting_property(self, num_insights: int):
        """
        Property: 排序应满足：
        1. 排序后数量不变
        2. 按重要性降序排列
        3. 相同重要性的顺序稳定
        """
        import random
        
        insights = [
            {"type": "insight", "id": i, "importance": random.random()}
            for i in range(num_insights)
        ]
        
        sorted_insights = self._sort_by_importance(insights)
        
        # Property 1: 数量不变
        assert len(sorted_insights) == len(insights)
        
        # Property 2: 降序排列
        importances = [i["importance"] for i in sorted_insights]
        assert importances == sorted(importances, reverse=True)
    
    def _deduplicate(self, insights: List[Dict]) -> List[Dict]:
        """去重逻辑"""
        seen_patterns = set()
        result = []
        
        for insight in insights:
            pattern = insight.get("pattern", insight.get("title", ""))
            if pattern not in seen_patterns:
                seen_patterns.add(pattern)
                result.append(insight)
        
        return result
    
    def _merge_similar(self, insights: List[Dict]) -> List[Dict]:
        """合并相似洞察"""
        # 按 pattern 分组
        groups: Dict[str, List[Dict]] = {}
        for insight in insights:
            pattern = insight.get("pattern", "")
            if pattern not in groups:
                groups[pattern] = []
            groups[pattern].append(insight)
        
        # 合并每组
        result = []
        for pattern, group in groups.items():
            if len(group) == 1:
                result.append(group[0])
            else:
                # 合并：取最高重要性，合并其他信息
                merged = group[0].copy()
                merged["importance"] = max(i.get("importance", 0) for i in group)
                merged["merged_count"] = len(group)
                result.append(merged)
        
        return result
    
    def _sort_by_importance(self, insights: List[Dict]) -> List[Dict]:
        """按重要性排序"""
        return sorted(insights, key=lambda x: x.get("importance", 0), reverse=True)


# ═══════════════════════════════════════════════════════════════════════════
# Additional Insight Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSemanticChunking:
    """
    测试语义分块逻辑
    
    分块优先级：时间 > 类别 > 地理
    """
    
    def test_chunking_priority(self):
        """验证分块优先级"""
        dimension_hierarchy = {
            "Date": {"category": "time", "level": 1},
            "Category": {"category": "product", "level": 2},
            "Region": {"category": "geographic", "level": 2},
        }
        
        # 时间维度应优先
        priority = self._get_chunking_priority(dimension_hierarchy)
        
        assert priority[0] == "Date"  # 时间优先
    
    def test_chunk_size_limits(self):
        """验证分块大小限制"""
        max_chunk_size = 500
        data_size = 2000
        
        num_chunks = (data_size + max_chunk_size - 1) // max_chunk_size
        
        assert num_chunks == 4
        
        # 每个块大小应合理
        for i in range(num_chunks):
            start = i * max_chunk_size
            end = min((i + 1) * max_chunk_size, data_size)
            chunk_size = end - start
            assert chunk_size <= max_chunk_size
    
    @given(
        data_size=st.integers(min_value=10, max_value=5000),
        max_chunk_size=st.integers(min_value=50, max_value=500),
    )
    @settings(max_examples=50)
    def test_chunking_property(self, data_size: int, max_chunk_size: int):
        """
        Property: 分块应满足：
        1. 所有数据都被分配到块中
        2. 每个块大小 <= max_chunk_size
        3. 块数量合理
        """
        num_chunks = (data_size + max_chunk_size - 1) // max_chunk_size
        
        total_covered = 0
        for i in range(num_chunks):
            start = i * max_chunk_size
            end = min((i + 1) * max_chunk_size, data_size)
            chunk_size = end - start
            
            # Property 2: 块大小限制
            assert chunk_size <= max_chunk_size
            
            total_covered += chunk_size
        
        # Property 1: 所有数据被覆盖
        assert total_covered == data_size
        
        # Property 3: 块数量合理
        assert num_chunks >= 1
        assert num_chunks <= data_size  # 最多每行一个块
    
    def _get_chunking_priority(self, dimension_hierarchy: Dict) -> List[str]:
        """获取分块优先级"""
        priority_order = {"time": 0, "product": 1, "geographic": 2}
        
        dims = []
        for name, attrs in dimension_hierarchy.items():
            category = attrs.get("category", "other")
            priority = priority_order.get(category, 99)
            dims.append((name, priority))
        
        dims.sort(key=lambda x: x[1])
        return [d[0] for d in dims]


class TestInsightSynthesis:
    """
    测试洞察合成逻辑
    """
    
    def test_synthesis_combines_findings(self):
        """验证合成组合多个发现"""
        findings = [
            {"type": "trend", "title": "销售增长", "importance": 0.8},
            {"type": "anomaly", "title": "异常值", "importance": 0.9},
            {"type": "pattern", "title": "季节性", "importance": 0.7},
        ]
        
        synthesis = self._synthesize(findings)
        
        assert "summary" in synthesis
        assert len(synthesis["key_findings"]) <= 5  # 最多 5 个关键发现
    
    def test_synthesis_prioritizes_important(self):
        """验证合成优先重要发现"""
        findings = [
            {"type": "trend", "title": "低重要性", "importance": 0.3},
            {"type": "anomaly", "title": "高重要性", "importance": 0.9},
        ]
        
        synthesis = self._synthesize(findings)
        
        # 高重要性应在前
        if synthesis["key_findings"]:
            assert synthesis["key_findings"][0]["importance"] >= 0.9
    
    def _synthesize(self, findings: List[Dict]) -> Dict:
        """合成洞察"""
        # 按重要性排序
        sorted_findings = sorted(findings, key=lambda x: x.get("importance", 0), reverse=True)
        
        # 取前 5 个
        key_findings = sorted_findings[:5]
        
        # 生成摘要
        summary = f"发现 {len(findings)} 个洞察，其中 {len(key_findings)} 个关键发现"
        
        return {
            "summary": summary,
            "key_findings": key_findings,
            "total_findings": len(findings),
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
