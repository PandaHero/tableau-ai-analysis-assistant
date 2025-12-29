# -*- coding: utf-8 -*-
"""
AnalysisCoordinator Component - AI-driven progressive analysis coordinator.

Based on design document progressive-insight-analysis/design.md:
- AI-driven progressive analysis main loop
- Intelligent priority chunking
- AI decides what to analyze next
- AI decides when to stop
- Streaming output

Core concept: "AI baby eating"
- AI decides how to accumulate insights
- AI decides what to eat next
- AI decides when to stop

Architecture (Task 3.3.1):
- Uses EnhancedDataProfiler as single entry point for profiling
- EnhancedDataProfiler internally delegates to StatisticalAnalyzer and AnomalyDetector
- No direct calls to StatisticalAnalyzer or AnomalyDetector from coordinator
"""

import logging
import time
from typing import Dict, List, Any, Optional, AsyncGenerator
import pandas as pd

from tableau_assistant.src.agents.insight.models import (
    DataProfile,
    DataInsightProfile,
    InsightResult,
    Insight,
    PriorityChunk,
    NextBiteDecision,
    InsightQuality,
    ChunkPriority,
    InsightEvidence,
    AnomalyResult,
    AnomalyDetail,
)
from tableau_assistant.src.agents.insight.models.profile import EnhancedDataProfile
from .profiler import EnhancedDataProfiler
from .chunker import SemanticChunker
from .analyzer import ChunkAnalyzer
from .accumulator import InsightAccumulator
from .synthesizer import InsightSynthesizer

logger = logging.getLogger(__name__)


class AnalysisCoordinator:
    """
    AI-driven progressive analysis coordinator.
    
    Core flow (from design document):
    1. Initialize: Prepare all data chunks (intelligent priority chunking)
    2. Loop:
       a. AI selects next data chunk (based on existing insights)
       b. AI analyzes data chunk and accumulates insights
       c. Stream output new insights
       d. AI decides whether to continue
    3. End: Synthesize final insights
    
    Strategy selection:
    - < 100 rows: direct (direct analysis)
    - 100-1000 rows: progressive (progressive analysis)
    - > 1000 rows: progressive with priority (progressive with priority)
    
    Architecture (Task 3.3.1):
    - Uses EnhancedDataProfiler as single entry point
    - EnhancedDataProfiler internally delegates to StatisticalAnalyzer and AnomalyDetector
    - No duplicate profiling/anomaly detection code
    """
    
    # Strategy thresholds
    DIRECT_THRESHOLD = 100
    PROGRESSIVE_THRESHOLD = 1000
    
    def __init__(
        self,
        dimension_hierarchy: Optional[Dict[str, Any]] = None,
        profiler: Optional[EnhancedDataProfiler] = None,
        chunker: Optional[SemanticChunker] = None,
        analyzer: Optional[ChunkAnalyzer] = None,
        accumulator: Optional[InsightAccumulator] = None,
        synthesizer: Optional[InsightSynthesizer] = None,
    ):
        """
        Initialize coordinator.
        
        Args:
            dimension_hierarchy: Dimension hierarchy info
            profiler: EnhancedDataProfiler instance (single entry point for profiling)
            chunker: SemanticChunker instance
            analyzer: ChunkAnalyzer instance (Phase 2 LLM)
            accumulator: InsightAccumulator instance
            synthesizer: InsightSynthesizer instance
        """
        self._dimension_hierarchy = dimension_hierarchy or {}
        
        # EnhancedDataProfiler is the single entry point for profiling
        # It internally delegates to StatisticalAnalyzer and AnomalyDetector
        self.profiler = profiler or EnhancedDataProfiler(dimension_hierarchy=self._dimension_hierarchy)
        self.chunker = chunker or SemanticChunker(dimension_hierarchy=self._dimension_hierarchy)
        self.analyzer = analyzer or ChunkAnalyzer()
        self.accumulator = accumulator or InsightAccumulator()
        self.synthesizer = synthesizer or InsightSynthesizer()
    
    def set_dimension_hierarchy(self, hierarchy: Dict[str, Any]):
        """Set dimension hierarchy info."""
        self._dimension_hierarchy = hierarchy or {}
        self.profiler.set_dimension_hierarchy(self._dimension_hierarchy)
        self.chunker.set_dimension_hierarchy(self._dimension_hierarchy)
    
    async def analyze(
        self,
        data: Any,
        context: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> InsightResult:
        """
        Main analysis entry point - two-phase analysis architecture.
        
        Phase 1: Statistical/ML overall analysis (via EnhancedDataProfiler)
        Phase 2: Intelligent chunking + progressive analysis (Director + Analyst LLM collaboration)
        
        Architecture (Task 3.3.1):
        - EnhancedDataProfiler is the single entry point for Phase 1
        - It internally delegates to StatisticalAnalyzer and AnomalyDetector
        - No duplicate code in coordinator
        
        Args:
            data: Input data
            context: Analysis context (question, dimensions, measures)
            state: Current workflow state (for middleware)
            config: LangGraph RunnableConfig (contains middleware)
            
        Returns:
            InsightResult (contains data_insight_profile)
        """
        start_time = time.time()
        
        # Normalize data
        data_list = self._normalize_data(data)
        
        if not data_list:
            return InsightResult(
                summary="No data to analyze",
                findings=[],
                confidence=0.0,
                execution_time=time.time() - start_time,
            )
        
        # ========== Phase 1: Statistical/ML Analysis via EnhancedDataProfiler ==========
        logger.info("=" * 50)
        logger.info("Phase 1: Statistical/ML Analysis (via EnhancedDataProfiler)")
        logger.info("=" * 50)
        
        # EnhancedDataProfiler is the single entry point
        # It internally calls StatisticalAnalyzer and AnomalyDetector
        enhanced_profile = self.profiler.profile(data_list)
        
        # Get DataInsightProfile for chunking strategy
        insight_profile = self.profiler.get_insight_profile(data_list)
        
        logger.info(f"Data profile: {enhanced_profile.row_count} rows, {enhanced_profile.column_count} columns")
        logger.info(f"Distribution type: {insight_profile.distribution_type}, skewness: {insight_profile.skewness:.2f}")
        logger.info(f"Pareto: Top 20% contribute {insight_profile.pareto_ratio:.1%}")
        logger.info(f"Anomalies: {len(insight_profile.anomaly_indices)} ({insight_profile.anomaly_ratio:.1%})")
        logger.info(f"Clusters: {len(insight_profile.clusters)}")
        logger.info(f"Recommended chunking strategy: {insight_profile.recommended_chunking_strategy}")
        
        # Build basic DataProfile for strategy selection
        basic_profile = DataProfile(
            row_count=enhanced_profile.row_count,
            column_count=enhanced_profile.column_count,
            density=1.0,  # Simplified
            statistics=enhanced_profile.statistics,
            semantic_groups=[],
        )
        
        # ========== Phase 2: Intelligent Chunking + Progressive Analysis ==========
        logger.info("=" * 50)
        logger.info("Phase 2: Intelligent Chunking + Progressive Analysis")
        logger.info("=" * 50)
        
        # Select strategy
        strategy = self._select_strategy(basic_profile)
        logger.info(f"Analysis strategy: {strategy}")
        
        # Build analysis context with anomaly info from enhanced_profile
        anomaly_result = self._build_anomaly_result_from_profile(enhanced_profile)
        
        analysis_context = {
            **context,
            "anomalies": anomaly_result,
            "profile": basic_profile,
            "insight_profile": insight_profile,
            "top_n_summary": insight_profile.top_n_summary,
        }
        
        # Execute analysis
        if strategy == "direct":
            result = await self._direct_analysis(data_list, analysis_context, basic_profile, state, config)
        else:
            result = await self._progressive_analysis_two_phase(
                data_list, analysis_context, basic_profile, insight_profile, state, config
            )
        
        # Update result
        result.execution_time = time.time() - start_time
        result.strategy_used = strategy
        result.total_rows_analyzed = basic_profile.row_count
        result.data_insight_profile = insight_profile
        
        logger.info(f"Analysis complete: {len(result.findings)} insights, took {result.execution_time:.2f}s")
        
        return result
    
    def _build_anomaly_result_from_profile(self, enhanced_profile: EnhancedDataProfile) -> Any:
        """Build anomaly result from EnhancedDataProfile for analysis context."""
        if not enhanced_profile.anomaly_index:
            return AnomalyResult(outliers=[], anomaly_ratio=0.0, anomaly_details=[])
        
        anomaly_index = enhanced_profile.anomaly_index
        
        # Collect all outlier indices
        all_outliers = []
        for severity_list in anomaly_index.by_severity.values():
            all_outliers.extend(severity_list)
        all_outliers = list(set(all_outliers))
        
        # Build anomaly details (simplified)
        details = []
        for idx in all_outliers[:10]:  # Limit to 10
            # Determine severity
            severity = 0.0
            for sev_name, indices in anomaly_index.by_severity.items():
                if idx in indices:
                    if sev_name == "critical":
                        severity = 0.9
                    elif sev_name == "high":
                        severity = 0.7
                    elif sev_name == "medium":
                        severity = 0.5
                    else:
                        severity = 0.3
                    break
            
            details.append(AnomalyDetail(
                index=idx,
                values={},
                reason="Anomaly detected",
                severity=severity,
            ))
        
        return AnomalyResult(
            outliers=all_outliers,
            anomaly_ratio=anomaly_index.anomaly_ratio,
            anomaly_details=details,
        )

    
    async def analyze_streaming(
        self,
        data: Any,
        context: Dict[str, Any],
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streaming analysis with progress updates - dual LLM collaboration mode.
        
        Architecture (Task 3.3.1):
        - Uses EnhancedDataProfiler as single entry point
        - No direct calls to StatisticalAnalyzer or AnomalyDetector
        
        Args:
            data: Input data
            context: Analysis context
            state: Current workflow state (for middleware)
            config: LangGraph RunnableConfig (contains middleware)
        """
        start_time = time.time()
        
        data_list = self._normalize_data(data)
        
        if not data_list:
            yield {"event": "complete", "result": InsightResult(summary="No data to analyze")}
            return
        
        # EnhancedDataProfiler is the single entry point
        enhanced_profile = self.profiler.profile(data_list)
        insight_profile = self.profiler.get_insight_profile(data_list)
        
        # Build basic DataProfile for strategy selection
        basic_profile = DataProfile(
            row_count=enhanced_profile.row_count,
            column_count=enhanced_profile.column_count,
            density=1.0,
            statistics=enhanced_profile.statistics,
            semantic_groups=[],
        )
        
        # Build anomaly result from enhanced_profile
        anomaly_result = self._build_anomaly_result_from_profile(enhanced_profile)
        
        strategy = self._select_strategy(basic_profile)
        
        yield {
            "event": "start",
            "total_rows": enhanced_profile.row_count,
            "strategy": strategy,
            "anomaly_count": len(anomaly_result.outliers) if anomaly_result else 0,
        }
        
        analysis_context = {
            **context,
            "anomalies": anomaly_result,
            "profile": basic_profile,
            "insight_profile": insight_profile,
            "top_n_summary": insight_profile.top_n_summary,
        }
        
        if strategy == "direct":
            result = await self._direct_analysis(data_list, analysis_context, basic_profile, state, config)
            result.execution_time = time.time() - start_time
            result.data_insight_profile = insight_profile
            yield {"event": "complete", "result": result}
            return
        
        async for event in self._progressive_analysis_streaming(
            data_list, analysis_context, basic_profile, insight_profile, start_time, state, config
        ):
            yield event
    
    async def _progressive_analysis_two_phase(
        self,
        data: List[Dict[str, Any]],
        context: Dict[str, Any],
        profile: DataProfile,
        insight_profile: DataInsightProfile,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> InsightResult:
        """Two-phase progressive analysis - dual LLM collaboration mode."""
        chunks = self.chunker.chunk_by_strategy(
            data=data,
            strategy=insight_profile.recommended_chunking_strategy,
            insight_profile=insight_profile,
            semantic_groups=profile.semantic_groups,
        )
        
        logger.info(f"Chunking complete: {len(chunks)} chunks, strategy={insight_profile.recommended_chunking_strategy}")
        
        if not chunks:
            return InsightResult(summary="Unable to chunk data")
        
        accumulated_insights: List[Insight] = []
        remaining_chunks = chunks.copy()
        analyzed_count = 0
        
        while remaining_chunks:
            next_chunk = self._select_next_chunk(remaining_chunks, accumulated_insights)
            
            if next_chunk is None:
                logger.info("No more chunks to analyze")
                break
            
            remaining_chunks.remove(next_chunk)
            analyzed_count += 1
            
            logger.info(f"Analyzing chunk {analyzed_count}: {next_chunk.chunk_type} (priority {next_chunk.priority})")
            
            new_insights = await self.analyzer.analyze_chunk_with_analyst(
                chunk=next_chunk,
                context=context,
                insight_profile=insight_profile,
                existing_insights=accumulated_insights,
                state=state,
                config=config,
            )
            
            for insight in new_insights:
                if not self._is_duplicate(insight, accumulated_insights):
                    accumulated_insights.append(insight)
                    logger.info(f"New insight: {insight.title}")
            
            next_decision, quality = await self.analyzer.decide_next_with_coordinator(
                context=context,
                insight_profile=insight_profile,
                accumulated_insights=accumulated_insights,
                remaining_chunks=remaining_chunks,
                analyzed_count=analyzed_count,
                state=state,
                config=config,
            )
            
            if not next_decision.should_continue:
                logger.info(f"Coordinator decided early stop: {next_decision.reason}")
                break
            
            if next_decision.next_chunk_id is not None:
                remaining_chunks = self._reorder_chunks_by_id(
                    remaining_chunks, next_decision.next_chunk_id
                )
            
            logger.info(
                f"Coordinator decision: continue analyzing chunk_id={next_decision.next_chunk_id}, "
                f"completeness {next_decision.completeness_estimate:.2f}"
            )
        
        return self.synthesizer.synthesize(
            insights=accumulated_insights,
            strategy_used=f"two_phase_{insight_profile.recommended_chunking_strategy}",
            chunks_analyzed=analyzed_count,
            total_rows=profile.row_count,
        )
    
    async def _progressive_analysis_streaming(
        self,
        data: List[Dict[str, Any]],
        context: Dict[str, Any],
        profile: DataProfile,
        insight_profile: DataInsightProfile,
        start_time: float,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Streaming progressive analysis - dual LLM collaboration mode."""
        chunks = self.chunker.chunk_by_strategy(
            data=data,
            strategy=insight_profile.recommended_chunking_strategy,
            insight_profile=insight_profile,
            semantic_groups=profile.semantic_groups,
        )
        
        if not chunks:
            yield {"event": "complete", "result": InsightResult(summary="Unable to chunk data")}
            return
        
        yield {
            "event": "chunks_created",
            "total_chunks": len(chunks),
            "chunk_types": [c.chunk_type for c in chunks],
        }
        
        accumulated_insights: List[Insight] = []
        remaining_chunks = chunks.copy()
        analyzed_count = 0
        
        while remaining_chunks:
            next_chunk = self._select_next_chunk(remaining_chunks, accumulated_insights)
            
            if next_chunk is None:
                break
            
            remaining_chunks.remove(next_chunk)
            analyzed_count += 1
            
            yield {
                "event": "chunk_start",
                "chunk_type": next_chunk.chunk_type,
                "priority": next_chunk.priority,
                "chunk_id": next_chunk.chunk_id,
                "analyzed_count": analyzed_count,
            }
            
            new_insights = await self.analyzer.analyze_chunk_with_analyst(
                chunk=next_chunk,
                context=context,
                insight_profile=insight_profile,
                existing_insights=accumulated_insights,
                state=state,
                config=config,
            )
            
            for insight in new_insights:
                if not self._is_duplicate(insight, accumulated_insights):
                    accumulated_insights.append(insight)
                    yield {
                        "event": "insight_found",
                        "insight": insight.model_dump(),
                    }
            
            yield {
                "event": "chunk_complete",
                "chunk_type": next_chunk.chunk_type,
                "insights_count": len(new_insights),
            }
            
            next_decision, quality = await self.analyzer.decide_next_with_coordinator(
                context=context,
                insight_profile=insight_profile,
                accumulated_insights=accumulated_insights,
                remaining_chunks=remaining_chunks,
                analyzed_count=analyzed_count,
                state=state,
                config=config,
            )
            
            yield {
                "event": "ai_decision",
                "decision": next_decision.model_dump(),
                "quality": quality.model_dump(),
            }
            
            if not next_decision.should_continue:
                yield {
                    "event": "early_stop",
                    "reason": next_decision.reason,
                    "analyzed_chunks": analyzed_count,
                    "total_chunks": len(chunks),
                }
                break
            
            if next_decision.next_chunk_id is not None:
                remaining_chunks = self._reorder_chunks_by_id(
                    remaining_chunks, next_decision.next_chunk_id
                )
        
        result = self.synthesizer.synthesize(
            insights=accumulated_insights,
            strategy_used=f"two_phase_{insight_profile.recommended_chunking_strategy}",
            chunks_analyzed=analyzed_count,
            total_rows=profile.row_count,
            execution_time=time.time() - start_time,
        )
        
        yield {"event": "complete", "result": result}
    
    def _select_next_chunk(
        self,
        remaining_chunks: List[PriorityChunk],
        accumulated_insights: List[Insight],
    ) -> Optional[PriorityChunk]:
        """Select next data chunk to analyze."""
        if not remaining_chunks:
            return None
        
        sorted_chunks = sorted(remaining_chunks, key=lambda x: x.priority)
        return sorted_chunks[0]
    
    def _reorder_chunks_by_id(
        self,
        chunks: List[PriorityChunk],
        preferred_chunk_id: int,
    ) -> List[PriorityChunk]:
        """Reorder chunks based on coordinator LLM's recommended chunk_id."""
        preferred = [c for c in chunks if c.chunk_id == preferred_chunk_id]
        others = [c for c in chunks if c.chunk_id != preferred_chunk_id]
        
        return preferred + sorted(others, key=lambda x: x.priority)
    
    def _is_duplicate(self, insight: Insight, existing: List[Insight]) -> bool:
        """Check if insight is a duplicate."""
        for e in existing:
            if e.type == insight.type and e.title == insight.title:
                return True
            if e.type == insight.type:
                title_words = set(insight.title.lower().split())
                existing_words = set(e.title.lower().split())
                if title_words and existing_words:
                    overlap = len(title_words & existing_words) / len(title_words | existing_words)
                    if overlap > 0.8:
                        return True
        return False
    
    def _normalize_data(self, data: Any) -> List[Dict[str, Any]]:
        """Convert various data formats to list of dicts."""
        if isinstance(data, list):
            if not data:
                return []
            if isinstance(data[0], dict):
                return data
            return [{"value": v} for v in data]
        
        if isinstance(data, pd.DataFrame):
            return data.to_dict('records')
        
        if isinstance(data, dict):
            return [data]
        
        if hasattr(data, 'data'):
            return data.data if isinstance(data.data, list) else []
        
        logger.warning(f"Unknown data type: {type(data)}")
        return []
    
    def _select_strategy(self, profile: DataProfile) -> str:
        """Select analysis strategy."""
        if profile.row_count < self.DIRECT_THRESHOLD:
            return "direct"
        elif profile.row_count < self.PROGRESSIVE_THRESHOLD:
            return "progressive"
        else:
            return "progressive_with_priority"
    
    async def _direct_analysis(
        self,
        data: List[Dict[str, Any]],
        context: Dict[str, Any],
        profile: DataProfile,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> InsightResult:
        """Direct analysis for small datasets."""
        insights = await self.analyzer.analyze_full(data, context, state, config)
        
        anomaly_insights = self._create_anomaly_insights(context.get("anomalies"))
        insights.extend(anomaly_insights)
        
        return self.synthesizer.synthesize(
            insights=insights,
            strategy_used="direct",
            chunks_analyzed=1,
            total_rows=profile.row_count,
        )
    
    def _create_anomaly_insights(self, anomalies) -> List[Insight]:
        """Create insights from detected anomalies."""
        if not anomalies or not anomalies.anomaly_details:
            return []
        
        insights = []
        
        if anomalies.anomaly_ratio > 0.05:
            importance = 0.9 if anomalies.anomaly_ratio > 0.1 else 0.7
            
            evidence = InsightEvidence(
                metric_name="Anomaly count",
                metric_value=float(len(anomalies.outliers)),
                percentage=anomalies.anomaly_ratio,
                additional_data={
                    "outlier_count": len(anomalies.outliers),
                } if anomalies.anomaly_details else None,
            )
            
            insights.append(Insight(
                type="anomaly",
                title=f"Detected {len(anomalies.outliers)} anomalies",
                description=f"{anomalies.anomaly_ratio:.1%} of records contain anomalies that may require further investigation.",
                importance=importance,
                evidence=evidence,
            ))
        
        return insights
