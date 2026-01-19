# -*- coding: utf-8 -*-
"""
ChunkAnalyzer Component - Analyst LLM wrapper

Wraps the Analyst LLM for analyzing data chunks.
Orchestration decisions are handled by AnalysisDirector (director.py).

Contains:
- analyze_chunk_with_analyst: Basic analysis (simple insights list)
- analyze_chunk_with_history: Enhanced analysis with historical insight processing
"""

import logging
import json
import re
from typing import Dict, List, Any, Optional

from tableau_assistant.src.agents.insight.models import (
    Insight,
    InsightEvidence,
    PriorityChunk,
    DataInsightProfile,
)
from tableau_assistant.src.agents.insight.models.analyst import (
    AnalystOutputWithHistory,
    HistoricalInsightAction,
    HistoricalInsightActionType,
)

from tableau_assistant.src.agents.insight.prompts import (
    ANALYST_PROMPT,
    ANALYST_PROMPT_WITH_HISTORY,
)
from tableau_assistant.src.agents.insight.components.utils import format_insights_with_index


from tableau_assistant.src.agents.base import call_llm_with_tools

logger = logging.getLogger(__name__)


class ChunkAnalyzer:
    """
    双 LLM 协作分析器
    
    核心功能（来自 insight-design.md）：
    1. 分析师 LLM：分析数据块并提取洞察
    2. 主持人 LLM：决定分析顺序、累积洞察、决定早停
    
    使用 call_llm_with_tools 模式支持：
    - 中间件（重试、摘要等）
    - Token 流式输出
    """
    
    def __init__(self, llm=None, max_sample_rows: int = 150):
        """
        初始化分析器
        
        Args:
            llm: LangChain LLM 实例
            max_sample_rows: Prompt 中包含的最大行数（默认 150 行）
        """
        self._llm = llm
        self.max_sample_rows = max_sample_rows
    
    def _get_llm(self):
        """获取或创建 LLM 实例"""
        if self._llm is None:
            from tableau_assistant.src.agents.base import get_llm
            self._llm = get_llm(agent_name="insight")
        return self._llm
    
    async def analyze_chunk_with_analyst(
        self,
        chunk: PriorityChunk,
        context: Dict[str, Any],
        insight_profile: DataInsightProfile,
        existing_insights: List[Insight],
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> List[Insight]:
        """
        使用分析师 LLM 分析数据块
        
        分析师 LLM 职责（来自 insight-design.md）：
        - 分析单个数据块
        - 结合整体画像和 top_n_summary 解读局部数据
        - 生成结构化洞察
        
        使用 call_llm_with_tools 支持中间件和流式输出。
        
        Args:
            chunk: 当前要分析的数据块
            context: 分析上下文（question, dimensions, measures）
            insight_profile: 整体数据画像（Phase 1 结果）
            existing_insights: 已有洞察（避免重复）
            state: 当前工作流状态（用于中间件）
            config: LangGraph RunnableConfig（包含中间件）
            
        Returns:
            List[Insight]: 新发现的洞察
        """
        # 准备数据样本
        if chunk.chunk_type == "tail_data" and chunk.tail_summary:
            data_sample = json.dumps(
                chunk.tail_summary.sample_data[:self.max_sample_rows],
                ensure_ascii=False,
                indent=2
            )
        else:
            data_sample = json.dumps(
                chunk.data[:self.max_sample_rows],
                ensure_ascii=False,
                indent=2
            )
        
        # 格式化已有洞察
        existing_text = "\n".join([
            f"- {ins.type}: {ins.title}"
            for ins in existing_insights
        ]) if existing_insights else "（无）"
        
        # 格式化 Top N 摘要
        top_n_summary = json.dumps(
            insight_profile.top_n_summary if insight_profile.top_n_summary else [],
            ensure_ascii=False,
            indent=2
        )
        
        # 格式化统计信息
        statistics_text = json.dumps(
            {k: v.model_dump() for k, v in insight_profile.statistics.items()},
            ensure_ascii=False,
            indent=2
        ) if insight_profile.statistics else "{}"
        
        try:
            messages = ANALYST_PROMPT.format_messages(
                question=context.get("question", ""),
                distribution_type=insight_profile.distribution_type,
                statistics=statistics_text,
                pareto_ratio=f"{insight_profile.pareto_ratio:.1%}",
                top_n_summary=top_n_summary,
                chunk_type=chunk.chunk_type,
                row_count=chunk.row_count,
                chunk_description=chunk.description,
                data_sample=data_sample,
                existing_insights=existing_text,
            )
            
            # 获取中间件
            middleware = None
            if config and "configurable" in config:
                middleware = config["configurable"].get("middleware")
            
            # 使用 call_llm_with_tools 支持中间件和流式输出
            llm = self._get_llm()
            response = await call_llm_with_tools(
                llm=llm,
                messages=messages,
                tools=[],  # 不需要工具
                streaming=True,
                middleware=middleware,
                state=state or {},
                config=config,
            )
            
            insights = self._parse_insights_response(response.content)
            logger.info(f"Analyst LLM analyzed {chunk.chunk_type}: {len(insights)} insights")
            return insights
            
        except Exception as e:
            logger.error(f"Analyst LLM analysis failed {chunk.chunk_type}: {e}")
            return []
    
    async def analyze_chunk_with_history(
        self,
        chunk: PriorityChunk,
        context: Dict[str, Any],
        insight_profile: DataInsightProfile,
        historical_insights: List[Insight],
        current_coverage: float = 0.0,
        state: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> AnalystOutputWithHistory:
        """
        Analyze data chunk with historical insight processing.
        
        Enhanced analyst that:
        - Generates NEW insights (not duplicating historical ones)
        - Suggests actions for each historical insight (KEEP/MERGE/REPLACE/DISCARD)
        
        Args:
            chunk: Current data chunk to analyze
            context: Analysis context (question, dimensions, measures)
            insight_profile: Overall data profile (Phase 1 result)
            historical_insights: Existing accumulated insights (with indices)
            current_coverage: Current data coverage ratio (0.0-1.0)
            state: Workflow state (for middleware)
            config: LangGraph RunnableConfig (for middleware)
            
        Returns:
            AnalystOutputWithHistory: New insights + historical action suggestions
        """
        # Prepare data sample
        if chunk.chunk_type == "tail_data" and chunk.tail_summary:
            data_sample = json.dumps(
                chunk.tail_summary.sample_data[:self.max_sample_rows],
                ensure_ascii=False,
                indent=2
            )
        else:
            data_sample = json.dumps(
                chunk.data[:self.max_sample_rows],
                ensure_ascii=False,
                indent=2
            )
        
        # Format historical insights with indices
        historical_text = self._format_historical_insights(historical_insights)
        
        # Format Top N summary
        top_n_summary = json.dumps(
            insight_profile.top_n_summary if insight_profile.top_n_summary else [],
            ensure_ascii=False,
            indent=2
        )
        
        # Format statistics
        statistics_text = json.dumps(
            {k: v.model_dump() for k, v in insight_profile.statistics.items()},
            ensure_ascii=False,
            indent=2
        ) if insight_profile.statistics else "{}"
        
        try:
            messages = ANALYST_PROMPT_WITH_HISTORY.format_messages(
                question=context.get("question", ""),
                distribution_type=insight_profile.distribution_type,
                statistics=statistics_text,
                pareto_ratio=f"{insight_profile.pareto_ratio:.1%}",
                top_n_summary=top_n_summary,
                chunk_type=chunk.chunk_type,
                row_count=chunk.row_count,
                chunk_description=chunk.description,
                data_sample=data_sample,
                historical_insights=historical_text,
                current_coverage=f"{current_coverage:.1%}",
            )
            
            # Get middleware
            middleware = None
            if config and "configurable" in config:
                middleware = config["configurable"].get("middleware")
            
            # Call LLM with middleware support
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
            
            output = self._parse_analyst_output_with_history(
                response.content, 
                historical_insights,
                current_coverage,
            )
            logger.info(
                f"Analyst LLM analyzed {chunk.chunk_type}: "
                f"{len(output.new_insights)} new insights, "
                f"{len(output.historical_actions)} historical actions"
            )
            return output
            
        except Exception as e:
            logger.error(f"Analyst LLM analysis failed {chunk.chunk_type}: {e}")
            # Return default output with all KEEP actions
            return self._create_default_analyst_output(historical_insights, current_coverage)
    
    def _format_historical_insights(self, insights: List[Insight]) -> str:
        """Format historical insights with indices for LLM."""
        return format_insights_with_index(insights, description_max_len=100)
    
    def _parse_analyst_output_with_history(
        self,
        content: str,
        historical_insights: List[Insight],
        current_coverage: float,
    ) -> AnalystOutputWithHistory:
        """Parse AnalystOutputWithHistory from LLM response."""
        try:
            json_str = self._extract_json(content)
            if not json_str:
                logger.warning("No JSON found in analyst response")
                return self._create_default_analyst_output(historical_insights, current_coverage)
            
            result = json.loads(json_str)
            
            # Parse new_insights
            new_insights = []
            raw_new = result.get("new_insights", [])
            for raw in raw_new:
                try:
                    insight = self._parse_single_insight(raw)
                    new_insights.append(insight)
                except Exception as e:
                    logger.warning(f"Failed to parse new insight: {e}")
            
            # Parse historical_actions
            historical_actions = []
            raw_actions = result.get("historical_actions", [])
            for raw_action in raw_actions:
                try:
                    action = self._parse_historical_action(raw_action)
                    historical_actions.append(action)
                except Exception as e:
                    logger.warning(f"Failed to parse historical action: {e}")
            
            # Ensure we have actions for all historical insights
            historical_actions = self._ensure_all_actions(
                historical_actions, 
                historical_insights
            )
            
            return AnalystOutputWithHistory(
                new_insights=new_insights,
                historical_actions=historical_actions,
                analysis_summary=result.get("analysis_summary", "Analysis completed"),
                data_coverage=float(result.get("data_coverage", current_coverage)),
                confidence=float(result.get("confidence", 0.5)),
                needs_further_analysis=result.get("needs_further_analysis", True),
                suggested_next_focus=result.get("suggested_next_focus"),
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse analyst JSON: {e}")
            return self._create_default_analyst_output(historical_insights, current_coverage)
        except Exception as e:
            logger.error(f"Error parsing analyst response: {e}")
            return self._create_default_analyst_output(historical_insights, current_coverage)
    
    def _parse_single_insight(self, raw: Dict[str, Any]) -> Insight:
        """Parse a single Insight from raw dict."""
        evidence = None
        raw_evidence = raw.get("evidence")
        if raw_evidence and isinstance(raw_evidence, dict):
            evidence = InsightEvidence(
                metric_name=raw_evidence.get("metric_name"),
                metric_value=raw_evidence.get("metric_value") or raw_evidence.get("value"),
                comparison_value=raw_evidence.get("comparison_value") or raw_evidence.get("second_place"),
                ratio=raw_evidence.get("ratio") or raw_evidence.get("growth_rate"),
                percentage=raw_evidence.get("percentage"),
                period=raw_evidence.get("period"),
                additional_data={
                    k: v for k, v in raw_evidence.items()
                    if k not in {"metric_name", "metric_value", "value", "comparison_value", 
                               "second_place", "ratio", "growth_rate", "percentage", "period"}
                    and isinstance(v, (str, int, float, bool))
                } or None,
            )
        
        return Insight(
            type=self._normalize_type(raw.get("type", "pattern")),
            title=raw.get("title", "Unnamed insight"),
            description=raw.get("description", ""),
            importance=float(raw.get("importance", 0.5)),
            evidence=evidence,
        )
    
    def _parse_historical_action(self, raw: Dict[str, Any]) -> HistoricalInsightAction:
        """Parse a HistoricalInsightAction from raw dict."""
        action_str = raw.get("action", "KEEP").upper()
        try:
            action = HistoricalInsightActionType(action_str)
        except ValueError:
            action = HistoricalInsightActionType.KEEP
        
        merged_insight = None
        if action == HistoricalInsightActionType.MERGE and raw.get("merged_insight"):
            merged_insight = self._parse_single_insight(raw["merged_insight"])
        
        replacement_insight = None
        if action == HistoricalInsightActionType.REPLACE and raw.get("replacement_insight"):
            replacement_insight = self._parse_single_insight(raw["replacement_insight"])
        
        return HistoricalInsightAction(
            historical_index=int(raw.get("historical_index", 0)),
            action=action,
            reason=raw.get("reason", ""),
            merged_insight=merged_insight,
            replacement_insight=replacement_insight,
        )
    
    def _ensure_all_actions(
        self,
        actions: List[HistoricalInsightAction],
        historical_insights: List[Insight],
    ) -> List[HistoricalInsightAction]:
        """Ensure we have actions for all historical insights."""
        if not historical_insights:
            return []
        
        # Build index set of existing actions
        existing_indices = {a.historical_index for a in actions}
        
        # Add KEEP actions for missing indices
        for i in range(len(historical_insights)):
            if i not in existing_indices:
                actions.append(HistoricalInsightAction(
                    historical_index=i,
                    action=HistoricalInsightActionType.KEEP,
                    reason="Default KEEP (no explicit action from analyst)",
                ))
        
        # Sort by index
        actions.sort(key=lambda a: a.historical_index)
        return actions
    
    def _create_default_analyst_output(
        self,
        historical_insights: List[Insight],
        current_coverage: float,
    ) -> AnalystOutputWithHistory:
        """Create default output when parsing fails."""
        # Default: KEEP all historical insights
        historical_actions = [
            HistoricalInsightAction(
                historical_index=i,
                action=HistoricalInsightActionType.KEEP,
                reason="Default KEEP (parsing failed)",
            )
            for i in range(len(historical_insights))
        ]
        
        return AnalystOutputWithHistory(
            new_insights=[],
            historical_actions=historical_actions,
            analysis_summary="Analysis parsing failed, keeping all historical insights",
            data_coverage=current_coverage,
            confidence=0.3,
            needs_further_analysis=True,
            suggested_next_focus=None,
        )
    
    def _parse_insights_response(self, content: str) -> List[Insight]:
        """解析洞察列表响应"""
        insights = []
        
        try:
            json_str = self._extract_json(content)
            if not json_str:
                logger.warning("LLM 响应中没有找到 JSON")
                return []
            
            result = json.loads(json_str)
            
            # 支持两种格式：{insights: [...]} 或 [...]
            if isinstance(result, dict) and "insights" in result:
                raw_insights = result["insights"]
            elif isinstance(result, list):
                raw_insights = result
            else:
                raw_insights = [result]
            
            for raw in raw_insights:
                try:
                    # 解析 evidence 字段
                    evidence = None
                    raw_evidence = raw.get("evidence")
                    if raw_evidence and isinstance(raw_evidence, dict):
                        evidence = InsightEvidence(
                            metric_name=raw_evidence.get("metric_name"),
                            metric_value=raw_evidence.get("metric_value") or raw_evidence.get("value"),
                            comparison_value=raw_evidence.get("comparison_value") or raw_evidence.get("second_place"),
                            ratio=raw_evidence.get("ratio") or raw_evidence.get("growth_rate"),
                            percentage=raw_evidence.get("percentage"),
                            period=raw_evidence.get("period"),
                            additional_data={
                                k: v for k, v in raw_evidence.items()
                                if k not in {"metric_name", "metric_value", "value", "comparison_value", 
                                           "second_place", "ratio", "growth_rate", "percentage", "period"}
                                and isinstance(v, (str, int, float, bool))
                            } or None,
                        )
                    
                    insight = Insight(
                        type=self._normalize_type(raw.get("type", "pattern")),
                        title=raw.get("title", "未命名洞察"),
                        description=raw.get("description", ""),
                        importance=float(raw.get("importance", 0.5)),
                        evidence=evidence,
                    )
                    insights.append(insight)
                except Exception as e:
                    logger.warning(f"解析洞察失败: {e}")
            
        except json.JSONDecodeError as e:
            logger.warning(f"解析 JSON 失败: {e}")
        except Exception as e:
            logger.error(f"解析响应时发生错误: {e}")
        
        return insights
    
    def _extract_json(self, content: str) -> Optional[str]:
        """从 LLM 响应中提取 JSON"""
        content_stripped = content.strip()
        
        # 尝试原始 JSON 对象
        if content_stripped.startswith('{') and content_stripped.endswith('}'):
            return content_stripped
        if content_stripped.startswith('[') and content_stripped.endswith(']'):
            return content_stripped
        
        # 尝试 ```json ... ``` 块
        match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if match:
            return match.group(1)
        
        # 尝试 ``` ... ``` 块
        match = re.search(r'```\s*([\s\S]*?)\s*```', content)
        if match:
            return match.group(1)
        
        # 尝试提取 JSON 对象
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            return match.group(0)
        
        # 尝试提取 JSON 数组
        match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', content)
        if match:
            return match.group(0)
        
        return None
    
    def _normalize_type(self, type_str: str) -> str:
        """标准化洞察类型"""
        valid_types = {"trend", "anomaly", "comparison", "pattern"}
        normalized = type_str.lower().strip()
        
        if normalized in valid_types:
            return normalized
        
        type_map = {
            "distribution": "pattern",
            "correlation": "pattern",
            "summary": "pattern",
            "outlier": "anomaly",
            "change": "trend",
            "difference": "comparison",
        }
        return type_map.get(normalized, "pattern")
