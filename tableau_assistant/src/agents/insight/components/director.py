# -*- coding: utf-8 -*-
"""
AnalysisDirector Component

Analysis Director (总监) that orchestrates progressive insight analysis.

Responsibilities (from design.md):
1. Review enhanced data profile (Tableau Pulse-style insights)
2. Process analyst's output and execute insight actions (KEEP/MERGE/REPLACE/DISCARD)
3. Decide what to analyze next (chunk/dimension/anomaly)
4. Generate final summary when stopping

Architecture:
- Uses DirectorPrompt from prompts/director.py
- Uses DirectorOutputWithAccumulation as LLM output model
- Handles insight accumulation (not code-level, LLM-driven)
"""

import logging
import json
import re
from typing import Dict, List, Any, Optional

from tableau_assistant.src.agents.base import call_llm_with_tools
from tableau_assistant.src.agents.insight.models import (
    Insight,
    InsightQuality,
    PriorityChunk,
    EnhancedDataProfile,
)
from tableau_assistant.src.agents.insight.models.director import (
    DirectorAction,
    DirectorDecision,
    DirectorOutputWithAccumulation,
    InsightActionItem,
    InsightAction,
)
from tableau_assistant.src.agents.insight.prompts import DIRECTOR_PROMPT
from tableau_assistant.src.agents.insight.components.utils import format_insights_with_index


logger = logging.getLogger(__name__)


class AnalysisDirector:
    """
    Analysis Director - orchestrates progressive insight analysis.
    
    Uses enhanced data profile (Tableau Pulse-style) to make intelligent
    decisions about what to analyze next.
    
    Features:
    - Profile-aware decision making
    - Dimension/anomaly precision targeting
    - Insight accumulation (LLM-driven KEEP/MERGE/REPLACE/DISCARD)
    - Quality-based early stopping
    - Final summary generation (when stopping)
    """
    
    def __init__(self, llm=None, max_iterations: int = 5):
        """
        Initialize director.
        
        Args:
            llm: LangChain LLM instance (created if not provided)
            max_iterations: Maximum analysis iterations
        """
        self._llm = llm
        self.max_iterations = max_iterations
    
    def _get_llm(self):
        """Get or create LLM instance."""
        if self._llm is None:
            from tableau_assistant.src.agents.base import get_llm
            self._llm = get_llm(agent_name="insight")
        return self._llm
    
    async def decide(
        self,
        user_question: str,
        enhanced_profile: EnhancedDataProfile,
        available_chunks: List[PriorityChunk],
        analyzed_chunk_ids: List[int],
        current_insights: List[Insight],
        iteration_count: int,
        analyst_new_insights: Optional[List[Insight]] = None,
        analyst_historical_actions: Optional[str] = None,
        data_coverage: float = 0.0,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> DirectorOutputWithAccumulation:
        """
        Make decision on next analysis action and process insights.
        
        Args:
            user_question: Original user question
            enhanced_profile: Tableau Pulse-style data profile
            available_chunks: List of available chunks
            analyzed_chunk_ids: IDs of already analyzed chunks
            current_insights: Currently accumulated insights
            iteration_count: Current iteration count
            analyst_new_insights: New insights from analyst (optional)
            analyst_historical_actions: Formatted historical actions from analyst (optional)
            data_coverage: Current data coverage ratio (0.0-1.0)
            state: Workflow state (for middleware, contains semantic_query)
            config: LangGraph config (for middleware)
            
        Returns:
            DirectorOutputWithAccumulation with decision, accumulated insights, and final summary
        """
        # Build profile summary (use semantic_query from state for dimensions/measures)
        profile_summary = self._build_profile_summary(enhanced_profile, state)
        
        # Build available targets
        available_targets = self._build_available_targets(
            enhanced_profile, available_chunks, analyzed_chunk_ids
        )
        
        # Build analyzed targets
        analyzed_targets = self._build_analyzed_targets(analyzed_chunk_ids)
        
        # Build current insights text
        insights_text = self._format_insights_with_index(current_insights)
        
        # Format analyst new insights
        analyst_new_text = self._format_insights(analyst_new_insights) if analyst_new_insights else "（无新洞察）"
        
        # Format analyst historical actions
        analyst_actions_text = analyst_historical_actions if analyst_historical_actions else "（无历史处理建议）"
        
        # Format messages using prompt
        messages = DIRECTOR_PROMPT.format_messages(
            user_question=user_question,
            profile_summary=profile_summary,
            available_targets=available_targets,
            analyzed_targets=analyzed_targets,
            current_insights=insights_text,
            analyst_new_insights=analyst_new_text,
            analyst_historical_actions=analyst_actions_text,
            data_coverage=f"{data_coverage:.1%}",
            iteration_count=iteration_count,
            max_iterations=self.max_iterations,
            analyzed_count=len(analyzed_chunk_ids),
        )
        
        # Get middleware
        middleware = None
        if config and "configurable" in config:
            middleware = config["configurable"].get("middleware")
        
        try:
            # Call LLM
            llm = self._get_llm()
            response = await call_llm_with_tools(
                llm=llm,
                messages=messages,
                tools=[],
                streaming=True,
                middleware=middleware,
                state=state or {},
                config=config,
            )
            
            # Parse response to DirectorOutputWithAccumulation
            output = self._parse_response(
                response.content,
                available_chunks,
                current_insights,
                analyst_new_insights,
            )
            
            logger.info(
                f"Director decision: action={output.decision.action}, "
                f"should_continue={output.decision.should_continue}, "
                f"accumulated_insights={len(output.accumulated_insights)}"
            )
            return output
            
        except Exception as e:
            logger.error(f"Director decision failed: {e}")
            return self._default_output(
                available_chunks, analyzed_chunk_ids, iteration_count,
                current_insights, analyst_new_insights
            )
    
    def _parse_response(
        self,
        content: str,
        available_chunks: List[PriorityChunk],
        current_insights: List[Insight],
        analyst_new_insights: Optional[List[Insight]] = None,
    ) -> DirectorOutputWithAccumulation:
        """Parse LLM response to DirectorOutputWithAccumulation."""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if not json_match:
                raise ValueError("No JSON found in response")
            
            data = json.loads(json_match.group())
            
            # Parse decision
            action_str = data.get("action", "stop")
            try:
                action = DirectorAction(action_str)
            except ValueError:
                action = DirectorAction.STOP
            
            decision = DirectorDecision(
                action=action,
                should_continue=data.get("should_continue", False),
                reason=data.get("reason", ""),
                target_chunk_id=data.get("target_chunk_id"),
                target_dimension=data.get("target_dimension"),
                target_dimension_value=data.get("target_dimension_value"),
                target_anomaly_indices=data.get("target_anomaly_indices"),
                quality_assessment=InsightQuality(
                    completeness=data.get("completeness", 0.5),
                    confidence=data.get("confidence", 0.5),
                    need_more_data=data.get("should_continue", False),
                    question_answered=data.get("question_answered", False),
                ),
            )
            
            # Parse insight actions
            insight_actions = []
            raw_actions = data.get("insight_actions", [])
            for raw_action in raw_actions:
                try:
                    action_item = InsightActionItem(
                        insight_index=raw_action.get("insight_index", 0),
                        action=InsightAction(raw_action.get("action", "KEEP")),
                        merge_with_index=raw_action.get("merge_with_index"),
                        reason=raw_action.get("reason", ""),
                    )
                    insight_actions.append(action_item)
                except Exception:
                    continue
            
            # Process accumulated insights
            accumulated_insights = self._process_insight_actions(
                current_insights, insight_actions, analyst_new_insights
            )
            
            # Get final summary if stopping
            final_summary = None
            if not decision.should_continue:
                final_summary = data.get("final_summary", "")
            
            return DirectorOutputWithAccumulation(
                decision=decision,
                insight_actions=insight_actions,
                new_insights_to_add=analyst_new_insights or [],
                accumulated_insights=accumulated_insights,
                final_summary=final_summary,
            )
            
        except Exception as e:
            logger.error(f"Failed to parse director response: {e}")
            # Return default with current insights preserved
            return self._default_output(
                available_chunks, [], 0, current_insights, analyst_new_insights
            )
    
    def _process_insight_actions(
        self,
        current_insights: List[Insight],
        actions: List[InsightActionItem],
        new_insights: Optional[List[Insight]] = None,
    ) -> List[Insight]:
        """Process insight actions and return accumulated insights."""
        # Start with current insights
        result = list(current_insights)
        
        # Build action map by index
        action_map = {a.insight_index: a for a in actions}
        
        # Process actions (in reverse order to handle removals correctly)
        indices_to_remove = set()
        for idx, action_item in action_map.items():
            if idx >= len(result):
                continue
            
            if action_item.action == InsightAction.DISCARD:
                indices_to_remove.add(idx)
            elif action_item.action == InsightAction.REPLACE and action_item.replacement_insight:
                result[idx] = action_item.replacement_insight
            elif action_item.action == InsightAction.MERGE and action_item.merge_with_index is not None:
                # Simple merge: keep the target, mark source for removal
                indices_to_remove.add(idx)
        
        # Remove discarded/merged insights
        result = [ins for i, ins in enumerate(result) if i not in indices_to_remove]
        
        # Add new insights from analyst
        if new_insights:
            result.extend(new_insights)
        
        return result
    
    def _default_output(
        self,
        available_chunks: List[PriorityChunk],
        analyzed_chunk_ids: List[int],
        iteration_count: int,
        current_insights: List[Insight],
        analyst_new_insights: Optional[List[Insight]] = None,
    ) -> DirectorOutputWithAccumulation:
        """Create default output when LLM fails."""
        # Find next unanalyzed chunk
        unanalyzed = [c for c in available_chunks if c.chunk_id not in analyzed_chunk_ids]
        
        if unanalyzed and iteration_count < self.max_iterations:
            # Continue with next chunk
            next_chunk = unanalyzed[0]
            decision = DirectorDecision(
                action=DirectorAction.ANALYZE_CHUNK,
                should_continue=True,
                reason="Default: analyzing next available chunk",
                target_chunk_id=next_chunk.chunk_id,
                quality_assessment=InsightQuality(
                    completeness=0.3,
                    confidence=0.3,
                    need_more_data=True,
                    question_answered=False,
                ),
            )
            accumulated = list(current_insights)
            if analyst_new_insights:
                accumulated.extend(analyst_new_insights)
            
            return DirectorOutputWithAccumulation(
                decision=decision,
                insight_actions=[],
                new_insights_to_add=analyst_new_insights or [],
                accumulated_insights=accumulated,
                final_summary=None,
            )
        else:
            # Stop analysis
            accumulated = list(current_insights)
            if analyst_new_insights:
                accumulated.extend(analyst_new_insights)
            
            decision = DirectorDecision(
                action=DirectorAction.STOP,
                should_continue=False,
                reason="No more chunks to analyze or max iterations reached",
                quality_assessment=InsightQuality(
                    completeness=0.5,
                    confidence=0.5,
                    need_more_data=False,
                    question_answered=len(accumulated) > 0,
                ),
            )
            
            summary = self._generate_default_summary(accumulated)
            
            return DirectorOutputWithAccumulation(
                decision=decision,
                insight_actions=[],
                new_insights_to_add=[],
                accumulated_insights=accumulated,
                final_summary=summary,
            )
    
    def _generate_default_summary(self, insights: List[Insight]) -> str:
        """Generate default summary from insights."""
        if not insights:
            return "分析完成，未发现显著洞察。"
        
        summaries = [ins.summary for ins in insights if ins.summary]
        if summaries:
            return "分析完成。主要发现：" + "；".join(summaries[:3])
        return f"分析完成，共发现 {len(insights)} 条洞察。"
    
    def _build_profile_summary(self, profile: EnhancedDataProfile, state: Optional[Dict[str, Any]] = None) -> str:
        """Build profile summary for prompt.
        
        Uses semantic_query from state for dimensions/measures if available,
        otherwise falls back to profile statistics.
        """
        lines = []
        
        # Basic info
        lines.append(f"数据行数: {profile.row_count}")
        lines.append(f"数据列数: {profile.column_count}")
        
        # Get dimensions and measures from semantic_query (preferred) or profile
        semantic_query = state.get("semantic_query") if state else None
        
        if semantic_query:
            # Use dimensions/measures from semantic_query
            if hasattr(semantic_query, 'dimensions') and semantic_query.dimensions:
                dim_names = [d.field_name for d in semantic_query.dimensions]
                lines.append(f"维度: {', '.join(dim_names)}")
            
            if hasattr(semantic_query, 'measures') and semantic_query.measures:
                measure_names = [m.field_name for m in semantic_query.measures]
                lines.append(f"度量: {', '.join(measure_names)}")
        else:
            # Fallback: use profile statistics keys as measure names
            if profile.statistics:
                col_names = list(profile.statistics.keys())
                lines.append(f"数值列: {', '.join(col_names)}")
            
            # Fallback: use dimension_indices for dimension names
            if profile.dimension_indices:
                dim_names = [di.dimension for di in profile.dimension_indices]
                lines.append(f"维度列: {', '.join(dim_names)}")
        
        # Contributor analyses (Tableau Pulse style)
        if profile.contributor_analyses:
            lines.append(f"贡献者分析数: {len(profile.contributor_analyses)}")
            for ca in profile.contributor_analyses:
                lines.append(f"  - {ca.dimension}/{ca.measure}: Top贡献 {ca.top_contribution_pct:.1%}")
        
        # Concentration risks
        if profile.concentration_risks:
            lines.append(f"集中度风险数: {len(profile.concentration_risks)}")
        
        # Anomaly index
        if profile.anomaly_index:
            ai = profile.anomaly_index
            lines.append(f"异常数: {ai.total_anomalies} ({ai.anomaly_ratio:.1%})")
        
        # Trend analyses
        if profile.trend_analyses:
            lines.append(f"趋势分析数: {len(profile.trend_analyses)}")
        
        return "\n".join(lines)
    
    def _build_available_targets(
        self,
        profile: EnhancedDataProfile,
        chunks: List[PriorityChunk],
        analyzed_ids: List[int],
    ) -> str:
        """Build available targets for prompt."""
        lines = []
        
        # Available chunks
        unanalyzed = [c for c in chunks if c.chunk_id not in analyzed_ids]
        if unanalyzed:
            lines.append("可用数据块:")
            for chunk in unanalyzed:
                lines.append(f"  [{chunk.chunk_id}] {chunk.chunk_type} - {chunk.row_count}行, 优先级:{chunk.priority}")
        
        # Available dimensions (from dimension_indices)
        if profile.dimension_indices:
            lines.append("可用维度分析:")
            for di in profile.dimension_indices:
                lines.append(f"  - {di.dimension}: {di.total_unique_values} unique values")
        
        # Available anomalies (from anomaly_index)
        if profile.anomaly_index and profile.anomaly_index.total_anomalies > 0:
            lines.append(f"可用异常分析: {profile.anomaly_index.total_anomalies} 个异常点")
        
        return "\n".join(lines) if lines else "（无可用目标）"
    
    def _build_analyzed_targets(self, analyzed_ids: List[int]) -> str:
        """Build analyzed targets for prompt."""
        if not analyzed_ids:
            return "（尚未分析任何目标）"
        return f"已分析数据块: {analyzed_ids}"
    
    def _format_insights_with_index(self, insights: List[Insight]) -> str:
        """Format insights with index for prompt."""
        return format_insights_with_index(insights, description_max_len=100)
    
    def _format_insights(self, insights: Optional[List[Insight]]) -> str:
        """Format insights without index."""
        if not insights:
            return "（无洞察）"
        
        lines = []
        for ins in insights:
            lines.append(f"- {ins.insight_type}: {ins.summary}")
        
        return "\n".join(lines)
