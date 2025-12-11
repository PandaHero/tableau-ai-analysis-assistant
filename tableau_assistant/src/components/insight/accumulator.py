"""
InsightAccumulator Component

累积洞察，处理去重和合并。

设计说明：
- 主持人 LLM 负责智能累积洞察（在 ChunkAnalyzer.decide_next_with_coordinator() 中判断完成度）
- 本组件提供基于代码逻辑的去重和合并
- 用于 AnalysisCoordinator 中的洞察去重

Requirements:
- R8.5: Insight accumulation and deduplication
"""

import logging
from typing import List, Set, Optional
import hashlib

from tableau_assistant.src.models.insight import Insight

logger = logging.getLogger(__name__)


class InsightAccumulator:
    """
    Insight Accumulator - collects and deduplicates insights.
    
    Features:
    - Pattern-based deduplication
    - Merges similar insights
    - Maintains importance ordering
    """
    
    def __init__(self, similarity_threshold: float = 0.8):
        """
        Initialize accumulator.
        
        Args:
            similarity_threshold: Threshold for considering insights similar
        """
        self._insights: List[Insight] = []
        self._seen_patterns: Set[str] = set()
        self.similarity_threshold = similarity_threshold
    
    def accumulate(self, insights: List[Insight]) -> None:
        """
        Accumulate new insights, deduplicating as needed.
        
        Args:
            insights: New insights to accumulate
        """
        for insight in insights:
            if self._is_duplicate(insight):
                logger.debug(f"Skipping duplicate insight: {insight.title}")
                continue
            
            # Check for similar insights to merge
            similar_idx = self._find_similar(insight)
            if similar_idx is not None:
                self._merge_insights(similar_idx, insight)
                logger.debug(f"Merged similar insight: {insight.title}")
            else:
                self._insights.append(insight)
                self._seen_patterns.add(self._extract_pattern(insight))
                logger.debug(f"Added new insight: {insight.title}")
    
    def get_accumulated(self) -> List[Insight]:
        """Get all accumulated insights, sorted by importance."""
        return sorted(self._insights, key=lambda x: x.importance, reverse=True)
    
    def get_summary(self) -> str:
        """Get a summary of accumulated insights for context passing."""
        if not self._insights:
            return ""
        
        summaries = []
        for insight in self._insights[:5]:  # Top 5 insights
            summaries.append(f"- {insight.title}: {insight.description[:100]}...")
        
        return "\n".join(summaries)
    
    def clear(self) -> None:
        """Clear all accumulated insights."""
        self._insights = []
        self._seen_patterns = set()
    
    def _is_duplicate(self, insight: Insight) -> bool:
        """Check if insight is a duplicate based on pattern."""
        pattern = self._extract_pattern(insight)
        return pattern in self._seen_patterns
    
    def _extract_pattern(self, insight: Insight) -> str:
        """
        Extract a pattern string for deduplication.
        
        Pattern is based on:
        - Insight type
        - Related columns
        - Key words in title
        """
        # Normalize title
        title_words = set(insight.title.lower().split())
        
        # Create pattern components (based on type and title)
        components = [
            insight.type,  # Now a string literal, not enum
            ",".join(sorted(title_words)),
        ]
        
        # Hash the pattern
        pattern_str = "|".join(components)
        return hashlib.md5(pattern_str.encode()).hexdigest()
    
    def _find_similar(self, insight: Insight) -> Optional[int]:
        """
        Find index of similar insight in accumulated list.
        
        Returns:
            Index of similar insight, or None if not found
        """
        for i, existing in enumerate(self._insights):
            if self._are_similar(existing, insight):
                return i
        return None
    
    def _are_similar(self, insight1: Insight, insight2: Insight) -> bool:
        """
        Check if two insights are similar enough to merge.
        
        Similarity is based on:
        - Same type
        - Similar titles
        """
        # Must be same type
        if insight1.type != insight2.type:
            return False
        
        # Check title similarity (simple word overlap)
        words1 = set(insight1.title.lower().split())
        words2 = set(insight2.title.lower().split())
        
        if words1 and words2:
            word_overlap = len(words1 & words2) / len(words1 | words2)
            return word_overlap >= self.similarity_threshold
        
        return False
    
    def _merge_insights(self, existing_idx: int, new_insight: Insight) -> None:
        """
        Merge new insight into existing one.
        
        Merging strategy:
        - Keep higher importance
        - Combine evidence
        - Combine related columns
        """
        existing = self._insights[existing_idx]
        
        # Update importance (take max)
        if new_insight.importance > existing.importance:
            # Create new insight with updated importance
            self._insights[existing_idx] = Insight(
                type=existing.type,
                title=existing.title,
                description=new_insight.description if len(new_insight.description) > len(existing.description) else existing.description,
                importance=new_insight.importance,
                evidence=self._merge_evidence(existing.evidence, new_insight.evidence),
            )
        else:
            # Just update evidence
            self._insights[existing_idx] = Insight(
                type=existing.type,
                title=existing.title,
                description=new_insight.description if len(new_insight.description) > len(existing.description) else existing.description,
                importance=existing.importance,
                evidence=self._merge_evidence(existing.evidence, new_insight.evidence),
            )
    
    def _merge_evidence(self, evidence1: Optional[dict], evidence2: Optional[dict]) -> Optional[dict]:
        """Merge two evidence dicts."""
        if evidence1 is None and evidence2 is None:
            return None
        if evidence1 is None:
            return evidence2
        if evidence2 is None:
            return evidence1
        
        # Merge dicts
        merged = {**evidence1, **evidence2}
        return merged
