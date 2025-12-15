"""
ChunkAnalyzer Component - 双 LLM 协作分析器

基于设计文档 insight-design.md 实现双 LLM 协作模式：
- 分析师 LLM：分析单个数据块，生成结构化洞察，输出 List[Insight]
- 主持人 LLM：决定分析顺序、累积洞察、决定早停，输出 NextBiteDecision

方法：
- analyze_chunk_with_analyst(): 使用分析师 LLM 分析数据块
- decide_next_with_coordinator(): 使用主持人 LLM 决定下一步
- analyze_full(): 直接分析小数据集（< 100 行）
"""

import logging
import json
import re
from typing import Dict, List, Any, Optional, Tuple

from tableau_assistant.src.models.insight import (
    Insight,
    InsightEvidence,
    PriorityChunk,
    NextBiteDecision,
    InsightQuality,
    DataInsightProfile,
)

# 直接从 prompt.py 模块导入，不从 agents/insight 包导入
# 这样避免触发 agents/insight/__init__.py 中的 node.py 导入（会导致循环依赖）
from tableau_assistant.src.agents.insight.prompt import (
    COORDINATOR_PROMPT,
    ANALYST_PROMPT,
    DIRECT_ANALYSIS_PROMPT,
)

logger = logging.getLogger(__name__)


class ChunkAnalyzer:
    """
    双 LLM 协作分析器
    
    核心功能（来自 insight-design.md）：
    1. 分析师 LLM：分析数据块并提取洞察
    2. 主持人 LLM：决定分析顺序、累积洞察、决定早停
    """
    
    def __init__(self, llm=None, max_sample_rows: int = 150):
        """
        初始化分析器
        
        Args:
            llm: LangChain LLM 实例
            max_sample_rows: Prompt 中包含的最大行数（默认 150 行，确保 LLM 有足够数据样本）
        """
        self._llm = llm
        self.max_sample_rows = max_sample_rows
    
    def _get_llm(self):
        """获取或创建 LLM 实例"""
        if self._llm is None:
            from tableau_assistant.src.model_manager import get_llm
            self._llm = get_llm()
        return self._llm
    
    async def analyze_chunk_with_analyst(
        self,
        chunk: PriorityChunk,
        context: Dict[str, Any],
        insight_profile: DataInsightProfile,
        existing_insights: List[Insight],
    ) -> List[Insight]:
        """
        使用分析师 LLM 分析数据块
        
        分析师 LLM 职责（来自 insight-design.md）：
        - 分析单个数据块
        - 结合整体画像和 top_n_summary 解读局部数据
        - 生成结构化洞察
        
        Args:
            chunk: 当前要分析的数据块
            context: 分析上下文（question, dimensions, measures）
            insight_profile: 整体数据画像（Phase 1 结果）
            existing_insights: 已有洞察（避免重复）
            
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
            
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            
            insights = self._parse_insights_response(response.content)
            logger.info(f"分析师 LLM 分析 {chunk.chunk_type}: {len(insights)} 个洞察")
            return insights
            
        except Exception as e:
            logger.error(f"分析师 LLM 分析失败 {chunk.chunk_type}: {e}")
            return []
    
    async def decide_next_with_coordinator(
        self,
        context: Dict[str, Any],
        insight_profile: DataInsightProfile,
        accumulated_insights: List[Insight],
        remaining_chunks: List[PriorityChunk],
        analyzed_count: int,
    ) -> Tuple[NextBiteDecision, InsightQuality]:
        """
        使用主持人 LLM 决定下一步
        
        主持人 LLM 职责（来自 insight-design.md）：
        - 决定分析顺序（优先级）
        - 累积洞察，判断完成度
        - 决定是否早停
        
        Args:
            context: 分析上下文（question）
            insight_profile: 整体数据画像（Phase 1 结果）
            accumulated_insights: 已累积的洞察
            remaining_chunks: 剩余的数据块
            analyzed_count: 已分析的块数
            
        Returns:
            (NextBiteDecision, InsightQuality)
        """
        # 格式化已有洞察
        insights_text = "\n".join([
            f"- 洞察 {i+1} ({ins.type}): {ins.title}\n  描述: {ins.description}"
            for i, ins in enumerate(accumulated_insights)
        ]) if accumulated_insights else "（还没有洞察）"
        
        # 格式化剩余数据块
        remaining_text = "\n".join([
            f"- chunk_id={rc.chunk_id}, {rc.chunk_type} (优先级={rc.priority}): {rc.description}, 估算价值={rc.estimated_value}"
            for rc in remaining_chunks
        ]) if remaining_chunks else "（没有剩余数据块了）"
        
        try:
            messages = COORDINATOR_PROMPT.format_messages(
                question=context.get("question", ""),
                distribution_type=insight_profile.distribution_type,
                pareto_ratio=f"{insight_profile.pareto_ratio:.1%}",
                anomaly_ratio=f"{insight_profile.anomaly_ratio:.1%}",
                cluster_count=len(insight_profile.clusters),
                chunking_strategy=insight_profile.recommended_chunking_strategy,
                accumulated_insights=insights_text,
                remaining_chunks=remaining_text,
                analyzed_count=analyzed_count,
            )
            
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            
            decision, quality = self._parse_coordinator_response(response.content, remaining_chunks)
            logger.info(
                f"主持人 LLM 决策: continue={decision.should_continue}, "
                f"next_chunk_id={decision.next_chunk_id}, "
                f"completeness={decision.completeness_estimate:.2f}"
            )
            return decision, quality
            
        except Exception as e:
            logger.error(f"主持人 LLM 决策失败: {e}")
            return self._default_coordinator_response(remaining_chunks)
    
    async def analyze_full(
        self,
        data: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[Insight]:
        """
        直接分析完整数据集（用于小数据集 < 100 行）
        """
        sample_data = data[:self.max_sample_rows]
        data_str = json.dumps(sample_data, ensure_ascii=False, indent=2)
        columns = list(data[0].keys()) if data else []
        
        try:
            messages = DIRECT_ANALYSIS_PROMPT.format_messages(
                row_count=len(data),
                columns=", ".join(columns),
                data=data_str,
                question=context.get("question", ""),
                dimensions=", ".join([
                    d.get("name", str(d)) if isinstance(d, dict) else str(d) 
                    for d in context.get("dimensions", [])
                ]),
                measures=", ".join([
                    m.get("name", str(m)) if isinstance(m, dict) else str(m) 
                    for m in context.get("measures", [])
                ]),
            )
            
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            
            insights = self._parse_insights_response(response.content)
            logger.info(f"直接分析完成: {len(insights)} 个洞察")
            return insights
            
        except Exception as e:
            logger.error(f"直接分析失败: {e}")
            return []
    
    def _parse_coordinator_response(
        self,
        content: str,
        remaining_chunks: List[PriorityChunk],
    ) -> Tuple[NextBiteDecision, InsightQuality]:
        """解析主持人 LLM 响应"""
        try:
            json_str = self._extract_json(content)
            if not json_str:
                logger.warning("主持人响应中没有找到 JSON")
                return self._default_coordinator_response(remaining_chunks)
            
            result = json.loads(json_str)
            
            # 解析下一口决策
            nbd = result.get("next_bite_decision", {})
            next_bite = NextBiteDecision(
                should_continue=nbd.get("should_continue", True),
                next_chunk_id=nbd.get("next_chunk_id"),
                reason=nbd.get("reason", ""),
                completeness_estimate=float(nbd.get("completeness_estimate", 0.0)),
            )
            
            # 解析洞察质量
            iq = result.get("insights_quality", {})
            quality = InsightQuality(
                completeness=float(iq.get("completeness", 0.0)),
                confidence=float(iq.get("confidence", 0.0)),
                need_more_data=iq.get("need_more_data", True),
                question_answered=iq.get("question_answered", False),
            )
            
            return (next_bite, quality)
            
        except json.JSONDecodeError as e:
            logger.warning(f"解析主持人响应 JSON 失败: {e}")
            return self._default_coordinator_response(remaining_chunks)
        except Exception as e:
            logger.error(f"解析主持人响应时发生错误: {e}")
            return self._default_coordinator_response(remaining_chunks)
    
    def _default_coordinator_response(
        self,
        remaining_chunks: List[PriorityChunk],
    ) -> Tuple[NextBiteDecision, InsightQuality]:
        """返回默认的主持人响应"""
        next_chunk_id = None
        if remaining_chunks:
            sorted_chunks = sorted(remaining_chunks, key=lambda x: x.priority)
            next_chunk_id = sorted_chunks[0].chunk_id if sorted_chunks else None
        
        return (
            NextBiteDecision(
                should_continue=bool(remaining_chunks),
                next_chunk_id=next_chunk_id,
                reason="解析失败，使用默认决策",
                completeness_estimate=0.0,
            ),
            InsightQuality(
                completeness=0.0,
                confidence=0.0,
                need_more_data=True,
                question_answered=False,
            ),
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
