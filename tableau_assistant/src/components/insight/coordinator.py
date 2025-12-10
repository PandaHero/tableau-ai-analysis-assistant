"""
AnalysisCoordinator Component - AI 驱动的渐进式分析协调器

基于设计文档 progressive-insight-analysis/design.md 实现：
- AI 驱动的渐进式分析主循环
- 智能优先级分块
- AI 决定下一口吃什么
- AI 决定什么时候停
- 流式输出

核心理念："AI 宝宝吃饭"
- AI 决定如何累积洞察
- AI 决定下一口吃什么
- AI 决定什么时候停
"""

import logging
import time
from typing import Dict, List, Any, Optional, AsyncGenerator
import pandas as pd

from .models import (
    DataProfile,
    DataInsightProfile,
    InsightResult,
    Insight,
    PriorityChunk,
    NextBiteDecision,
    InsightQuality,
    ChunkPriority,
)
from .profiler import DataProfiler
from .anomaly_detector import AnomalyDetector
from .chunker import SemanticChunker
from .analyzer import ChunkAnalyzer
from .accumulator import InsightAccumulator
from .synthesizer import InsightSynthesizer
from .statistical_analyzer import StatisticalAnalyzer

logger = logging.getLogger(__name__)


class AnalysisCoordinator:
    """
    AI 驱动的渐进式分析协调器
    
    核心流程（来自设计文档）：
    1. 初始化：准备所有数据块（智能优先级分块）
    2. 循环：
       a. AI 选择下一个数据块（基于已有洞察）
       b. AI 分析数据块并累积洞察
       c. 流式输出新洞察
       d. AI 判断是否继续
    3. 结束：合成最终洞察
    
    策略选择：
    - < 100 行: direct（直接分析）
    - 100-1000 行: progressive（渐进式分析）
    - > 1000 行: progressive with priority（带优先级的渐进式）
    """
    
    # 策略阈值
    DIRECT_THRESHOLD = 100
    PROGRESSIVE_THRESHOLD = 1000
    
    def __init__(
        self,
        dimension_hierarchy: Optional[Dict[str, Any]] = None,
        profiler: Optional[DataProfiler] = None,
        statistical_analyzer: Optional[StatisticalAnalyzer] = None,
        anomaly_detector: Optional[AnomalyDetector] = None,
        chunker: Optional[SemanticChunker] = None,
        analyzer: Optional[ChunkAnalyzer] = None,
        accumulator: Optional[InsightAccumulator] = None,
        synthesizer: Optional[InsightSynthesizer] = None,
    ):
        """
        初始化协调器
        
        Args:
            dimension_hierarchy: 维度层级信息
            profiler: 数据画像器
            statistical_analyzer: 统计/ML 分析器（Phase 1）
            anomaly_detector: 异常检测器
            chunker: 分块器
            analyzer: 分析器（Phase 2 LLM）
            accumulator: 累积器
            synthesizer: 合成器
        """
        self._dimension_hierarchy = dimension_hierarchy or {}
        
        self.profiler = profiler or DataProfiler(dimension_hierarchy=self._dimension_hierarchy)
        self.statistical_analyzer = statistical_analyzer or StatisticalAnalyzer()
        self.anomaly_detector = anomaly_detector or AnomalyDetector()
        self.chunker = chunker or SemanticChunker(dimension_hierarchy=self._dimension_hierarchy)
        self.analyzer = analyzer or ChunkAnalyzer()
        self.accumulator = accumulator or InsightAccumulator()
        self.synthesizer = synthesizer or InsightSynthesizer()
    
    def set_dimension_hierarchy(self, hierarchy: Dict[str, Any]):
        """设置维度层级信息"""
        self._dimension_hierarchy = hierarchy or {}
        self.profiler.set_dimension_hierarchy(self._dimension_hierarchy)
        self.chunker.set_dimension_hierarchy(self._dimension_hierarchy)
    
    async def analyze(
        self,
        data: Any,
        context: Dict[str, Any]
    ) -> InsightResult:
        """
        主分析入口 - 两阶段分析架构
        
        Phase 1: 统计/ML 整体分析（不需要 LLM）
        Phase 2: 智能分块 + 渐进式分析（主持人 + 分析师 LLM 协作）
        
        Args:
            data: 输入数据
            context: 分析上下文（question, dimensions, measures）
            
        Returns:
            InsightResult（包含 data_insight_profile）
        """
        start_time = time.time()
        
        # 转换数据
        data_list = self._normalize_data(data)
        
        if not data_list:
            return InsightResult(
                summary="无数据可分析",
                findings=[],
                confidence=0.0,
                execution_time=time.time() - start_time,
            )
        
        # ========== Phase 1: 统计/ML 整体分析 ==========
        logger.info("=" * 50)
        logger.info("Phase 1: 统计/ML 整体分析")
        logger.info("=" * 50)
        
        # 1.1 数据画像
        profile = self.profiler.profile(data_list)
        logger.info(f"数据画像: {profile.row_count} 行, {profile.column_count} 列")
        
        # 1.2 统计/ML 分析（生成 DataInsightProfile）
        insight_profile = self.statistical_analyzer.analyze(data_list, profile)
        logger.info(f"分布类型: {insight_profile.distribution_type}, 偏度: {insight_profile.skewness:.2f}")
        logger.info(f"帕累托: Top 20% 贡献 {insight_profile.pareto_ratio:.1%}")
        logger.info(f"异常值: {len(insight_profile.anomaly_indices)} 个 ({insight_profile.anomaly_ratio:.1%})")
        logger.info(f"聚类: {len(insight_profile.clusters)} 个")
        logger.info(f"推荐分块策略: {insight_profile.recommended_chunking_strategy}")
        
        # 1.3 异常检测（使用 Phase 1 的结果）
        anomalies = self.anomaly_detector.detect(data_list)
        
        # ========== Phase 2: 智能分块 + 渐进式分析 ==========
        logger.info("=" * 50)
        logger.info("Phase 2: 智能分块 + 渐进式分析")
        logger.info("=" * 50)
        
        # 2.1 选择策略
        strategy = self._select_strategy(profile)
        logger.info(f"分析策略: {strategy}")
        
        # 2.2 构建分析上下文
        analysis_context = {
            **context,
            "anomalies": anomalies,
            "profile": profile,
            "insight_profile": insight_profile,  # 传递 Phase 1 结果
            "top_n_summary": insight_profile.top_n_summary,  # Top N 摘要
        }
        
        # 2.3 执行分析
        if strategy == "direct":
            result = await self._direct_analysis(data_list, analysis_context, profile)
        else:
            # 使用 Phase 1 推荐的分块策略
            result = await self._progressive_analysis_two_phase(
                data_list, analysis_context, profile, insight_profile
            )
        
        # 更新结果
        result.execution_time = time.time() - start_time
        result.strategy_used = strategy
        result.total_rows_analyzed = profile.row_count
        result.data_insight_profile = insight_profile  # 附加整体画像
        
        logger.info(f"分析完成: {len(result.findings)} 个洞察, 耗时 {result.execution_time:.2f}s")
        
        return result
    
    async def analyze_streaming(
        self,
        data: Any,
        context: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式分析（带进度更新）
        
        Yields:
        - {"event": "start", "total_rows": N, "strategy": "..."}
        - {"event": "chunk_start", "chunk_type": "...", "priority": N}
        - {"event": "insight_found", "insight": Insight}
        - {"event": "ai_decision", "decision": NextBiteDecision}
        - {"event": "early_stop", "reason": "..."}
        - {"event": "complete", "result": InsightResult}
        """
        start_time = time.time()
        
        # 转换数据
        data_list = self._normalize_data(data)
        
        if not data_list:
            yield {"event": "complete", "result": InsightResult(summary="无数据可分析")}
            return
        
        # 数据画像
        profile = self.profiler.profile(data_list)
        
        # 异常检测
        anomalies = self.anomaly_detector.detect(data_list)
        
        # 选择策略
        strategy = self._select_strategy(profile)
        
        yield {
            "event": "start",
            "total_rows": profile.row_count,
            "strategy": strategy,
            "anomaly_count": len(anomalies.outliers),
        }
        
        analysis_context = {
            **context,
            "anomalies": anomalies,
            "profile": profile,
        }
        
        # 直接分析策略
        if strategy == "direct":
            result = await self._direct_analysis(data_list, analysis_context, profile)
            result.execution_time = time.time() - start_time
            yield {"event": "complete", "result": result}
            return
        
        # AI 驱动的渐进式分析
        async for event in self._progressive_analysis_streaming(
            data_list, analysis_context, profile, anomalies.outliers, start_time
        ):
            yield event
    
    async def _progressive_analysis_two_phase(
        self,
        data: List[Dict[str, Any]],
        context: Dict[str, Any],
        profile: DataProfile,
        insight_profile: DataInsightProfile,
    ) -> InsightResult:
        """
        两阶段渐进式分析（基于 Phase 1 结果）
        
        核心流程：
        1. 使用 Phase 1 推荐的分块策略
        2. 主持人 LLM 选择下一个数据块
        3. 分析师 LLM 分析并累积洞察
        4. 主持人 LLM 判断是否继续
        """
        # 1. 使用 Phase 1 推荐的分块策略
        chunks = self.chunker.chunk_by_strategy(
            data=data,
            strategy=insight_profile.recommended_chunking_strategy,
            insight_profile=insight_profile,
            semantic_groups=profile.semantic_groups,
        )
        
        logger.info(f"分块完成: {len(chunks)} 个块, 策略={insight_profile.recommended_chunking_strategy}")
        
        if not chunks:
            return InsightResult(summary="无法分块数据")
        
        # 2. 渐进式分析主循环
        accumulated_insights: List[Insight] = []
        remaining_chunks = chunks.copy()
        analyzed_count = 0
        
        while remaining_chunks:
            # 选择下一个数据块
            next_chunk = self._select_next_chunk(remaining_chunks, accumulated_insights)
            
            if next_chunk is None:
                logger.info("没有更多数据块需要分析")
                break
            
            remaining_chunks.remove(next_chunk)
            analyzed_count += 1
            
            logger.info(f"🍽️ 分析块 {analyzed_count}: {next_chunk.chunk_type} (优先级={next_chunk.priority})")
            
            # 分析师 LLM 分析（传递 Phase 1 上下文）
            analysis_context_with_profile = {
                **context,
                "insight_profile": insight_profile,
                "top_n_summary": insight_profile.top_n_summary,
                "statistics": insight_profile.statistics,
            }
            
            new_insights, next_decision, quality = await self.analyzer.analyze_with_ai_decision(
                next_chunk,
                analysis_context_with_profile,
                accumulated_insights,
                remaining_chunks,
            )
            
            # 累积新洞察
            for insight in new_insights:
                if not self._is_duplicate(insight, accumulated_insights):
                    accumulated_insights.append(insight)
                    logger.info(f"💡 新洞察: {insight.title}")
            
            # 主持人 LLM 决定是否继续
            if not next_decision.should_continue:
                logger.info(f"✅ 主持人决定早停: {next_decision.reason}")
                break
            
            # 如果主持人推荐了特定的下一个块，调整剩余块的顺序
            if next_decision.next_chunk_type:
                remaining_chunks = self._reorder_chunks(
                    remaining_chunks, next_decision.next_chunk_type
                )
            
            logger.info(f"➡️ 主持人决策: 继续分析 {next_decision.next_chunk_type or '下一个优先块'}")
        
        # 3. 合成最终结果
        return self.synthesizer.synthesize(
            insights=accumulated_insights,
            strategy_used=f"two_phase_{insight_profile.recommended_chunking_strategy}",
            chunks_analyzed=analyzed_count,
            total_rows=profile.row_count,
        )
    
    async def _progressive_analysis_ai_driven(
        self,
        data: List[Dict[str, Any]],
        context: Dict[str, Any],
        profile: DataProfile,
        detected_anomalies: List[int],
    ) -> InsightResult:
        """
        AI 驱动的渐进式分析（旧版，保留兼容）
        
        核心流程（来自设计文档）：
        1. 智能优先级分块
        2. AI 选择下一个数据块
        3. AI 分析并累积洞察
        4. AI 判断是否继续
        """
        # 1. 智能优先级分块
        chunks = self.chunker.chunk_with_priority(data, detected_anomalies)
        logger.info(f"Created {len(chunks)} priority chunks")
        
        if not chunks:
            return InsightResult(summary="无法分块数据")
        
        # 2. 渐进式分析主循环
        accumulated_insights: List[Insight] = []
        remaining_chunks = chunks.copy()
        analyzed_count = 0
        
        while remaining_chunks:
            # 选择下一个数据块
            next_chunk = self._select_next_chunk(remaining_chunks, accumulated_insights)
            
            if next_chunk is None:
                logger.info("No more chunks to analyze")
                break
            
            remaining_chunks.remove(next_chunk)
            analyzed_count += 1
            
            logger.info(f"🍽️ Analyzing chunk {analyzed_count}: {next_chunk.chunk_type} (priority={next_chunk.priority})")
            
            # AI 分析并决策
            new_insights, next_decision, quality = await self.analyzer.analyze_with_ai_decision(
                next_chunk,
                context,
                accumulated_insights,
                remaining_chunks,
            )
            
            # 累积新洞察
            for insight in new_insights:
                if not self._is_duplicate(insight, accumulated_insights):
                    accumulated_insights.append(insight)
                    logger.info(f"💡 New insight: {insight.title}")
            
            # AI 决定是否继续
            if not next_decision.should_continue:
                logger.info(f"✅ AI decided to stop: {next_decision.reason}")
                break
            
            # 如果 AI 推荐了特定的下一个块，调整剩余块的顺序
            if next_decision.next_chunk_type:
                remaining_chunks = self._reorder_chunks(
                    remaining_chunks, next_decision.next_chunk_type
                )
            
            logger.info(f"➡️ AI decision: continue with {next_decision.next_chunk_type}")
        
        # 3. 合成最终结果
        return self.synthesizer.synthesize(
            insights=accumulated_insights,
            strategy_used="progressive_ai_driven",
            chunks_analyzed=analyzed_count,
            total_rows=profile.row_count,
        )
    
    async def _progressive_analysis_streaming(
        self,
        data: List[Dict[str, Any]],
        context: Dict[str, Any],
        profile: DataProfile,
        detected_anomalies: List[int],
        start_time: float,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式渐进式分析
        """
        # 智能优先级分块
        chunks = self.chunker.chunk_with_priority(data, detected_anomalies)
        
        if not chunks:
            yield {"event": "complete", "result": InsightResult(summary="无法分块数据")}
            return
        
        yield {
            "event": "chunks_created",
            "total_chunks": len(chunks),
            "chunk_types": [c.chunk_type for c in chunks],
        }
        
        # 渐进式分析主循环
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
            
            # AI 分析
            new_insights, next_decision, quality = await self.analyzer.analyze_with_ai_decision(
                next_chunk,
                context,
                accumulated_insights,
                remaining_chunks,
            )
            
            # 流式输出新洞察
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
            
            # AI 决策
            yield {
                "event": "ai_decision",
                "decision": next_decision.model_dump(),
                "quality": quality.model_dump(),
            }
            
            # 早停
            if not next_decision.should_continue:
                yield {
                    "event": "early_stop",
                    "reason": next_decision.reason,
                    "analyzed_chunks": analyzed_count,
                    "total_chunks": len(chunks),
                }
                break
            
            # 调整顺序
            if next_decision.next_chunk_type:
                remaining_chunks = self._reorder_chunks(
                    remaining_chunks, next_decision.next_chunk_type
                )
        
        # 合成结果
        result = self.synthesizer.synthesize(
            insights=accumulated_insights,
            strategy_used="progressive_ai_driven",
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
        """
        选择下一个数据块
        
        默认按优先级顺序，但 AI 可以通过 next_decision 调整
        """
        if not remaining_chunks:
            return None
        
        # 按优先级排序
        sorted_chunks = sorted(remaining_chunks, key=lambda x: x.priority)
        return sorted_chunks[0]
    
    def _reorder_chunks(
        self,
        chunks: List[PriorityChunk],
        preferred_type: str,
    ) -> List[PriorityChunk]:
        """
        根据 AI 推荐重新排序数据块
        """
        preferred = [c for c in chunks if c.chunk_type == preferred_type]
        others = [c for c in chunks if c.chunk_type != preferred_type]
        
        # 优先分析 AI 推荐的类型
        return preferred + sorted(others, key=lambda x: x.priority)
    
    def _is_duplicate(self, insight: Insight, existing: List[Insight]) -> bool:
        """检查洞察是否重复"""
        for e in existing:
            if e.type == insight.type and e.title == insight.title:
                return True
            # 简单的相似度检查
            if e.type == insight.type:
                title_words = set(insight.title.lower().split())
                existing_words = set(e.title.lower().split())
                if title_words and existing_words:
                    overlap = len(title_words & existing_words) / len(title_words | existing_words)
                    if overlap > 0.8:
                        return True
        return False
    
    def _normalize_data(self, data: Any) -> List[Dict[str, Any]]:
        """转换各种数据格式为 list of dicts"""
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
        """选择分析策略"""
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
        profile: DataProfile
    ) -> InsightResult:
        """直接分析（小数据集）"""
        insights = await self.analyzer.analyze_full(data, context)
        
        # 添加异常洞察
        anomaly_insights = self._create_anomaly_insights(context.get("anomalies"))
        insights.extend(anomaly_insights)
        
        return self.synthesizer.synthesize(
            insights=insights,
            strategy_used="direct",
            chunks_analyzed=1,
            total_rows=profile.row_count,
        )
    
    def _create_anomaly_insights(self, anomalies) -> List[Insight]:
        """从检测到的异常创建洞察"""
        if not anomalies or not anomalies.anomaly_details:
            return []
        
        insights = []
        
        if anomalies.anomaly_ratio > 0.05:
            importance = 0.9 if anomalies.anomaly_ratio > 0.1 else 0.7
            
            evidence = None
            if anomalies.anomaly_details:
                first_detail = anomalies.anomaly_details[0]
                evidence = {
                    "outlier_count": len(anomalies.outliers),
                    "anomaly_ratio": anomalies.anomaly_ratio,
                    "sample_values": first_detail.values if hasattr(first_detail, 'values') else {},
                }
            
            insights.append(Insight(
                type="anomaly",
                title=f"检测到 {len(anomalies.outliers)} 个异常值",
                description=f"数据中有 {anomalies.anomaly_ratio:.1%} 的记录存在异常值，可能需要进一步调查。",
                importance=importance,
                evidence=evidence,
                related_columns=[d.column for d in anomalies.anomaly_details if d.column],
            ))
        
        return insights
