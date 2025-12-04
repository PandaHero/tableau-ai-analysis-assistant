"""
Feature Detector for Dynamic Prompt System

Rule-based detection of question features to determine which
prompt modules should be activated.

Design Principles:
- Pattern-based: Use regex patterns for detection
- Extensible: Easy to add new patterns
- Fast: O(n) where n is number of patterns
"""
import re
from typing import Set, List, Dict, Tuple
from .feature_tags import FeatureTag


class FeatureDetector:
    """Detect question features using rule-based patterns.
    
    Each feature has associated trigger patterns (regex).
    Multiple features can be detected for a single question.
    
    Usage:
        detector = FeatureDetector()
        features = detector.detect("各省份的销售额")
        # Returns: {FeatureTag.DIMENSION, FeatureTag.MEASURE, FeatureTag.GROUPING, FeatureTag.AGGREGATION}
    """
    
    # Pattern definitions: (pattern, feature_tag)
    # Patterns are compiled for performance
    PATTERNS: List[Tuple[str, FeatureTag]] = [
        # ===== Entity Patterns =====
        # Dimension indicators
        (r"各\w+|按\w+|每个\w+|分\w+", FeatureTag.DIMENSION),
        (r"省份|地区|城市|产品|品类|类别|客户|部门|渠道", FeatureTag.DIMENSION),
        
        # Measure indicators
        (r"销售额|利润|收入|成本|数量|金额|营收", FeatureTag.MEASURE),
        (r"总\w+|平均\w+|最高\w+|最低\w+", FeatureTag.MEASURE),
        
        # Date field indicators
        (r"按年|按月|按季度|按周|按天|各年|各月|每月|每年", FeatureTag.DATE_FIELD),
        (r"年度|月度|季度|周度|日度", FeatureTag.DATE_FIELD),
        
        # ===== Operation Patterns =====
        # Aggregation indicators
        (r"总\w+|合计|汇总|累计", FeatureTag.AGGREGATION),
        (r"平均|均值|平均值", FeatureTag.AGGREGATION),
        (r"最高|最大|最低|最小", FeatureTag.AGGREGATION),
        
        # Grouping indicators
        (r"各\w+|按\w+分|每个\w+|分\w+看", FeatureTag.GROUPING),
        
        # Filtering indicators
        (r"只看|仅|筛选|过滤|排除", FeatureTag.FILTERING),
        (r"华东|华南|华北|华中|西南|西北|东北", FeatureTag.FILTERING),  # Common region filters
        
        # Counting indicators
        (r"多少\w+|几个\w+|数量|个数", FeatureTag.COUNTING),
        
        # ===== Time Patterns =====
        # Absolute time
        (r"\d{4}年|\d{4}", FeatureTag.TIME_ABSOLUTE),
        (r"Q[1-4]|第[一二三四]季度", FeatureTag.TIME_ABSOLUTE),
        (r"\d{1,2}月|[一二三四五六七八九十]+月", FeatureTag.TIME_ABSOLUTE),
        
        # Relative time
        (r"最近\d+个?[天周月季年]", FeatureTag.TIME_RELATIVE),
        (r"本月|当月|本年|今年|本季度", FeatureTag.TIME_RELATIVE),
        (r"上个?月|上季度|去年|上一?年", FeatureTag.TIME_RELATIVE),
        (r"年初至今|月初至今|季初至今", FeatureTag.TIME_RELATIVE),
        
        # Time comparison
        (r"同比|环比|年同比|月环比", FeatureTag.TIME_COMPARISON),
        (r"与去年|与上月|比去年|比上月", FeatureTag.TIME_COMPARISON),
        
        # ===== Analysis Patterns =====
        # Trend
        (r"趋势|变化|走势|演变", FeatureTag.TREND),
        
        # Ranking
        (r"排名|前\d+|Top\s?\d+|最高的?\d+个?|最低的?\d+个?", FeatureTag.RANKING),
        
        # Comparison
        (r"对比|比较|vs|VS|和\w+比", FeatureTag.COMPARISON),
        
        # Proportion
        (r"占比|比例|百分比|份额", FeatureTag.PROPORTION),
        
        # Breakdown (multi-dimensional)
        (r"各\w+的\w+|按\w+分析", FeatureTag.BREAKDOWN),
        
        # ===== Advanced Patterns =====
        # Table calculations
        (r"累计|移动平均|滚动|排名计算", FeatureTag.TABLE_CALC),
        
        # Exploration
        (r"为什么|原因|分析原因|怎么回事", FeatureTag.EXPLORATION),
    ]
    
    def __init__(self):
        """Initialize detector with compiled patterns."""
        self._compiled_patterns: List[Tuple[re.Pattern, FeatureTag]] = [
            (re.compile(pattern, re.IGNORECASE), tag)
            for pattern, tag in self.PATTERNS
        ]
    
    def detect(self, question: str) -> Set[FeatureTag]:
        """Detect features in a question.
        
        Args:
            question: User's question text
            
        Returns:
            Set of detected feature tags
        """
        detected: Set[FeatureTag] = set()
        
        for pattern, tag in self._compiled_patterns:
            if pattern.search(question):
                detected.add(tag)
        
        # Post-processing: Add implied features
        detected = self._add_implied_features(detected)
        
        return detected
    
    def _add_implied_features(self, detected: Set[FeatureTag]) -> Set[FeatureTag]:
        """Add features implied by other features.
        
        Some features imply others:
        - COUNTING implies DIMENSION (counting distinct dimension values)
        - TREND implies DATE_FIELD (trend requires time axis)
        - TIME_COMPARISON implies TIME_RELATIVE (comparison needs time context)
        """
        result = detected.copy()
        
        # Counting implies dimension
        if FeatureTag.COUNTING in result:
            result.add(FeatureTag.DIMENSION)
        
        # Trend implies date field
        if FeatureTag.TREND in result:
            result.add(FeatureTag.DATE_FIELD)
        
        # Time comparison implies time handling
        if FeatureTag.TIME_COMPARISON in result:
            result.add(FeatureTag.TIME_RELATIVE)
        
        # Breakdown implies grouping
        if FeatureTag.BREAKDOWN in result:
            result.add(FeatureTag.GROUPING)
        
        return result
    
    def detect_with_matches(self, question: str) -> Dict[FeatureTag, List[str]]:
        """Detect features and return matched text for each.
        
        Useful for debugging and understanding why features were detected.
        
        Args:
            question: User's question text
            
        Returns:
            Dict mapping feature tags to list of matched strings
        """
        matches: Dict[FeatureTag, List[str]] = {}
        
        for pattern, tag in self._compiled_patterns:
            found = pattern.findall(question)
            if found:
                if tag not in matches:
                    matches[tag] = []
                matches[tag].extend(found)
        
        return matches


# Singleton instance for convenience
_detector = FeatureDetector()


def detect_features(question: str) -> Set[FeatureTag]:
    """Convenience function to detect features.
    
    Args:
        question: User's question text
        
    Returns:
        Set of detected feature tags
    """
    return _detector.detect(question)


__all__ = [
    "FeatureDetector",
    "detect_features",
]
