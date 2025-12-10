"""
InsightSynthesizer Component

Synthesizes final insights from accumulated analysis results.

Requirements:
- R8.6: Insight synthesis and final report generation
"""

import logging
from typing import Dict, List, Any, Optional

from .models import Insight, InsightResult

logger = logging.getLogger(__name__)


class InsightSynthesizer:
    """
    Insight Synthesizer - creates final insight reports.
    
    Features:
    - Sorts insights by importance
    - Generates summary
    - Calculates overall confidence
    - Merges multiple analysis results
    """
    
    def __init__(self, max_insights: int = 10):
        """
        Initialize synthesizer.
        
        Args:
            max_insights: Maximum number of insights in final result
        """
        self.max_insights = max_insights
    
    def synthesize(
        self,
        insights: List[Insight],
        strategy_used: str = "direct",
        chunks_analyzed: int = 0,
        total_rows: int = 0,
        execution_time: float = 0.0
    ) -> InsightResult:
        """
        Synthesize final insight result from accumulated insights.
        
        Args:
            insights: List of accumulated insights
            strategy_used: Analysis strategy used
            chunks_analyzed: Number of chunks analyzed
            total_rows: Total rows analyzed
            execution_time: Total execution time
            
        Returns:
            InsightResult with summary and findings
        """
        if not insights:
            return InsightResult(
                summary="未发现显著洞察",
                findings=[],
                confidence=0.0,
                strategy_used=strategy_used,
                chunks_analyzed=chunks_analyzed,
                total_rows_analyzed=total_rows,
                execution_time=execution_time,
            )
        
        # Sort by importance and limit
        sorted_insights = sorted(insights, key=lambda x: x.importance, reverse=True)
        top_insights = sorted_insights[:self.max_insights]
        
        # Generate summary
        summary = self._generate_summary(top_insights)
        
        # Calculate overall confidence
        confidence = self._calculate_confidence(top_insights)
        
        return InsightResult(
            summary=summary,
            findings=top_insights,
            confidence=confidence,
            strategy_used=strategy_used,
            chunks_analyzed=chunks_analyzed,
            total_rows_analyzed=total_rows,
            execution_time=execution_time,
        )
    
    def merge(self, results: List[InsightResult]) -> InsightResult:
        """
        Merge multiple insight results into one.
        
        Args:
            results: List of InsightResult objects to merge
            
        Returns:
            Merged InsightResult
        """
        if not results:
            return InsightResult(summary="无分析结果")
        
        if len(results) == 1:
            return results[0]
        
        # Collect all findings
        all_findings = []
        for result in results:
            all_findings.extend(result.findings)
        
        # Deduplicate
        unique_findings = self._deduplicate(all_findings)
        
        # Calculate totals
        total_chunks = sum(r.chunks_analyzed for r in results)
        total_rows = sum(r.total_rows_analyzed for r in results)
        total_time = sum(r.execution_time for r in results)
        
        # Synthesize merged result
        return self.synthesize(
            insights=unique_findings,
            strategy_used="hybrid",
            chunks_analyzed=total_chunks,
            total_rows=total_rows,
            execution_time=total_time,
        )
    
    def _generate_summary(self, insights: List[Insight]) -> str:
        """Generate a summary from top insights."""
        if not insights:
            return "未发现显著洞察"
        
        # Count by type (type is now a string literal, not enum)
        type_counts = {}
        for insight in insights:
            type_name = insight.type  # Now a string
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        # Build summary
        parts = []
        
        # Overall count
        parts.append(f"共发现 {len(insights)} 个关键洞察")
        
        # Type breakdown (only 4 valid types per spec)
        type_descriptions = {
            "trend": "趋势",
            "anomaly": "异常",
            "comparison": "对比",
            "pattern": "模式",
        }
        
        type_parts = []
        for type_name, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            desc = type_descriptions.get(type_name, type_name)
            type_parts.append(f"{count}个{desc}")
        
        if type_parts:
            parts.append(f"（{', '.join(type_parts)}）")
        
        # Top insight
        if insights:
            top = insights[0]
            parts.append(f"。最重要发现：{top.title}")
        
        return "".join(parts)
    
    def _calculate_confidence(self, insights: List[Insight]) -> float:
        """Calculate overall confidence from insights."""
        if not insights:
            return 0.0
        
        # Use importance as confidence (per spec, importance is 0-1)
        # Average importance of all insights
        total_importance = sum(insight.importance for insight in insights)
        return total_importance / len(insights)
    
    def _deduplicate(self, insights: List[Insight]) -> List[Insight]:
        """Remove duplicate insights."""
        seen_titles = set()
        unique = []
        
        for insight in insights:
            # Normalize title for comparison
            normalized_title = insight.title.lower().strip()
            
            if normalized_title not in seen_titles:
                seen_titles.add(normalized_title)
                unique.append(insight)
        
        return unique
