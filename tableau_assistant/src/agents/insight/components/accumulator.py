# -*- coding: utf-8 -*-
"""
InsightAccumulator Component

Accumulates insights with deduplication and action processing.

Features:
- Pattern-based deduplication (code-level fallback)
- Format insights with indices for LLM
- Apply LLM's processing suggestions (KEEP/MERGE/REPLACE/DISCARD)

Design:
- Director LLM is responsible for intelligent insight accumulation
- This component provides code-level deduplication as fallback
- Supports progressive accumulation with historical insight processing

Requirements:
- R8.5: Insight accumulation and deduplication
- Task 3.10: Insight accumulation helper module
"""

import logging
from typing import List, Set, Optional, Tuple
import hashlib

from tableau_assistant.src.agents.insight.models import Insight, InsightEvidence
from tableau_assistant.src.agents.insight.models.analyst import (
    HistoricalInsightAction,
    HistoricalInsightActionType,
)
from tableau_assistant.src.agents.insight.models.director import (
    InsightActionItem,
    InsightAction,
)
from tableau_assistant.src.agents.insight.components.utils import format_insights_with_index as _format_insights_with_index


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
        for insight in self._insights:
            summaries.append(f"- {insight.title}: {insight.description}")
        
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
    
    # ═══════════════════════════════════════════════════════════════════════════
    # Progressive Accumulation Methods (Task 3.10)
    # ═══════════════════════════════════════════════════════════════════════════
    
    def format_insights_with_index(self, insights: Optional[List[Insight]] = None) -> str:
        """
        Format insights with indices for LLM consumption.
        
        Args:
            insights: List of insights to format (uses accumulated if None)
            
        Returns:
            Formatted string with indexed insights
        """
        target_insights = insights if insights is not None else self._insights
        return _format_insights_with_index(target_insights, description_max_len=150)
    
    def apply_analyst_actions(
        self,
        historical_actions: List[HistoricalInsightAction],
        new_insights: List[Insight],
    ) -> Tuple[List[Insight], List[str]]:
        """
        Apply analyst's suggestions to accumulated insights.
        
        Args:
            historical_actions: Analyst's suggestions for each historical insight
            new_insights: New insights from analyst to add
            
        Returns:
            Tuple of (updated_insights, action_logs)
        """
        action_logs = []
        updated_insights = []
        
        # Process historical actions
        for action in sorted(historical_actions, key=lambda a: a.historical_index):
            idx = action.historical_index
            
            if idx >= len(self._insights):
                action_logs.append(f"[SKIP] Index {idx} out of range")
                continue
            
            original = self._insights[idx]
            
            if action.action == HistoricalInsightActionType.KEEP:
                updated_insights.append(original)
                action_logs.append(f"[KEEP] [{idx}] {original.title}")
                
            elif action.action == HistoricalInsightActionType.MERGE:
                if action.merged_insight:
                    updated_insights.append(action.merged_insight)
                    action_logs.append(f"[MERGE] [{idx}] {original.title} -> {action.merged_insight.title}")
                else:
                    # Fallback: keep original if no merged insight provided
                    updated_insights.append(original)
                    action_logs.append(f"[MERGE-FALLBACK] [{idx}] {original.title} (no merged insight)")
                    
            elif action.action == HistoricalInsightActionType.REPLACE:
                if action.replacement_insight:
                    updated_insights.append(action.replacement_insight)
                    action_logs.append(f"[REPLACE] [{idx}] {original.title} -> {action.replacement_insight.title}")
                else:
                    # Fallback: keep original if no replacement provided
                    updated_insights.append(original)
                    action_logs.append(f"[REPLACE-FALLBACK] [{idx}] {original.title} (no replacement)")
                    
            elif action.action == HistoricalInsightActionType.DISCARD:
                action_logs.append(f"[DISCARD] [{idx}] {original.title}: {action.reason}")
                # Don't add to updated_insights
        
        # Add new insights
        for new_ins in new_insights:
            # Check for duplicates before adding
            if not self._is_duplicate_in_list(new_ins, updated_insights):
                updated_insights.append(new_ins)
                action_logs.append(f"[ADD] {new_ins.title}")
            else:
                action_logs.append(f"[SKIP-DUP] {new_ins.title}")
        
        # Update internal state
        self._insights = updated_insights
        self._rebuild_patterns()
        
        return updated_insights, action_logs
    
    def apply_director_actions(
        self,
        insight_actions: List[InsightActionItem],
        new_insights: List[Insight],
    ) -> Tuple[List[Insight], List[str]]:
        """
        Apply director's insight actions to accumulated insights.
        
        Args:
            insight_actions: Director's actions for existing insights
            new_insights: New insights to add
            
        Returns:
            Tuple of (updated_insights, action_logs)
        """
        action_logs = []
        updated_insights = []
        
        # Build action map by index
        action_map = {a.insight_index: a for a in insight_actions}
        
        # Process each existing insight
        for idx, original in enumerate(self._insights):
            action_item = action_map.get(idx)
            
            if action_item is None:
                # No action specified, default to KEEP
                updated_insights.append(original)
                action_logs.append(f"[KEEP-DEFAULT] [{idx}] {original.title}")
                continue
            
            if action_item.action == InsightAction.KEEP:
                updated_insights.append(original)
                action_logs.append(f"[KEEP] [{idx}] {original.title}")
                
            elif action_item.action == InsightAction.MERGE:
                # For MERGE, we need merge_with_index
                if action_item.merge_with_index is not None:
                    # Skip this one, it will be merged with another
                    action_logs.append(f"[MERGE-SOURCE] [{idx}] {original.title} -> [{action_item.merge_with_index}]")
                else:
                    updated_insights.append(original)
                    action_logs.append(f"[MERGE-FALLBACK] [{idx}] {original.title}")
                    
            elif action_item.action == InsightAction.REPLACE:
                if action_item.replacement_insight:
                    updated_insights.append(action_item.replacement_insight)
                    action_logs.append(f"[REPLACE] [{idx}] {original.title} -> {action_item.replacement_insight.title}")
                else:
                    updated_insights.append(original)
                    action_logs.append(f"[REPLACE-FALLBACK] [{idx}] {original.title}")
                    
            elif action_item.action == InsightAction.DISCARD:
                action_logs.append(f"[DISCARD] [{idx}] {original.title}: {action_item.reason}")
        
        # Add new insights
        for new_ins in new_insights:
            if not self._is_duplicate_in_list(new_ins, updated_insights):
                updated_insights.append(new_ins)
                action_logs.append(f"[ADD] {new_ins.title}")
            else:
                action_logs.append(f"[SKIP-DUP] {new_ins.title}")
        
        # Update internal state
        self._insights = updated_insights
        self._rebuild_patterns()
        
        return updated_insights, action_logs
    
    def _is_duplicate_in_list(self, insight: Insight, insight_list: List[Insight]) -> bool:
        """Check if insight is duplicate of any in the list."""
        pattern = self._extract_pattern(insight)
        for existing in insight_list:
            if self._extract_pattern(existing) == pattern:
                return True
        return False
    
    def _rebuild_patterns(self) -> None:
        """Rebuild seen patterns from current insights."""
        self._seen_patterns = {self._extract_pattern(ins) for ins in self._insights}
    
    def set_insights(self, insights: List[Insight]) -> None:
        """Set insights directly (for initialization from state)."""
        self._insights = list(insights)
        self._rebuild_patterns()
    
    def count(self) -> int:
        """Get count of accumulated insights."""
        return len(self._insights)
