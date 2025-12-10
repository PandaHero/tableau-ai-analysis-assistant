"""
ChunkAnalyzer Component - AI 驱动的数据块分析器

基于设计文档 progressive-insight-analysis/design.md 实现：
- AI 驱动的洞察累积
- AI 驱动的下一口选择
- 早停机制

这是 Insight 系统中唯一调用 LLM 的组件。
Prompt 使用 VizQLPrompt 基类，自动注入 JSON Schema。
"""

import logging
import json
from typing import Dict, List, Any, Optional, Tuple

from .models import (
    DataChunk, 
    Insight, 
    PriorityChunk,
    NextBiteDecision,
    InsightQuality,
)

# 延迟导入 prompt，避免循环导入
_prompts_loaded = False
INSIGHT_ANALYSIS_PROMPT = None
CHUNK_ANALYSIS_PROMPT = None
AI_ANALYSIS_PROMPT = None
InsightOutput = None
AIAnalysisOutput = None

def _load_prompts():
    """延迟加载 prompt 模块"""
    global _prompts_loaded
    global INSIGHT_ANALYSIS_PROMPT, CHUNK_ANALYSIS_PROMPT, AI_ANALYSIS_PROMPT
    global InsightOutput, AIAnalysisOutput
    
    if _prompts_loaded:
        return
    
    _prompts_loaded = True
    
    # 尝试多种导入方式
    import_errors = []
    
    # 方式 1: 相对导入（当作为包的一部分运行时）
    try:
        import importlib
        prompt_module = importlib.import_module('src.agents.insight.prompt')
        INSIGHT_ANALYSIS_PROMPT = getattr(prompt_module, 'INSIGHT_ANALYSIS_PROMPT', None)
        CHUNK_ANALYSIS_PROMPT = getattr(prompt_module, 'CHUNK_ANALYSIS_PROMPT', None)
        AI_ANALYSIS_PROMPT = getattr(prompt_module, 'AI_ANALYSIS_PROMPT', None)
        InsightOutput = getattr(prompt_module, 'InsightOutput', None)
        AIAnalysisOutput = getattr(prompt_module, 'AIAnalysisOutput', None)
        if INSIGHT_ANALYSIS_PROMPT is not None:
            logger.debug("成功通过 src.agents.insight.prompt 导入 prompt")
            return
    except ImportError as e:
        import_errors.append(f"src.agents.insight.prompt: {e}")
    
    # 方式 2: 绝对导入
    try:
        import importlib
        prompt_module = importlib.import_module('tableau_assistant.src.agents.insight.prompt')
        INSIGHT_ANALYSIS_PROMPT = getattr(prompt_module, 'INSIGHT_ANALYSIS_PROMPT', None)
        CHUNK_ANALYSIS_PROMPT = getattr(prompt_module, 'CHUNK_ANALYSIS_PROMPT', None)
        AI_ANALYSIS_PROMPT = getattr(prompt_module, 'AI_ANALYSIS_PROMPT', None)
        InsightOutput = getattr(prompt_module, 'InsightOutput', None)
        AIAnalysisOutput = getattr(prompt_module, 'AIAnalysisOutput', None)
        if INSIGHT_ANALYSIS_PROMPT is not None:
            logger.debug("成功通过 tableau_assistant.src.agents.insight.prompt 导入 prompt")
            return
    except ImportError as e:
        import_errors.append(f"tableau_assistant.src.agents.insight.prompt: {e}")
    
    # 方式 3: 直接文件导入
    try:
        import sys
        import os
        # 获取当前文件的目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # 向上两级到 src，然后进入 agents/insight
        prompt_path = os.path.join(current_dir, '..', '..', 'agents', 'insight')
        prompt_path = os.path.normpath(prompt_path)
        if prompt_path not in sys.path:
            sys.path.insert(0, prompt_path)
        
        from prompt import (
            INSIGHT_ANALYSIS_PROMPT as _INSIGHT,
            CHUNK_ANALYSIS_PROMPT as _CHUNK,
            AI_ANALYSIS_PROMPT as _AI,
            InsightOutput as _InsightOutput,
            AIAnalysisOutput as _AIAnalysisOutput,
        )
        INSIGHT_ANALYSIS_PROMPT = _INSIGHT
        CHUNK_ANALYSIS_PROMPT = _CHUNK
        AI_ANALYSIS_PROMPT = _AI
        InsightOutput = _InsightOutput
        AIAnalysisOutput = _AIAnalysisOutput
        logger.debug("成功通过直接文件导入 prompt")
        return
    except ImportError as e:
        import_errors.append(f"直接文件导入: {e}")
    
    logger.warning(f"无法导入 prompt 模块，尝试了以下方式: {import_errors}")

logger = logging.getLogger(__name__)


class ChunkAnalyzer:
    """
    AI 驱动的数据块分析器
    
    核心功能：
    1. 分析数据块并提取洞察
    2. AI 驱动的洞察累积（理解语义，避免重复）
    3. AI 驱动的下一口选择
    4. 早停决策
    
    使用 VizQLPrompt 基类，自动注入 JSON Schema。
    """
    
    def __init__(self, llm=None, max_sample_rows: int = 50):
        """
        初始化分析器
        
        Args:
            llm: LangChain LLM 实例
            max_sample_rows: Prompt 中包含的最大行数
        """
        self._llm = llm
        self.max_sample_rows = max_sample_rows
    
    def _get_llm(self):
        """获取或创建 LLM 实例"""
        if self._llm is None:
            from tableau_assistant.src.model_manager import get_llm
            self._llm = get_llm()
        return self._llm
    
    async def analyze_with_ai_decision(
        self,
        chunk: PriorityChunk,
        context: Dict[str, Any],
        accumulated_insights: List[Insight],
        remaining_chunks: List[PriorityChunk],
    ) -> Tuple[List[Insight], NextBiteDecision, InsightQuality]:
        """
        AI 驱动的分析与决策
        
        核心理念（来自设计文档）：
        1. AI 分析当前数据块，提取洞察
        2. AI 累积洞察（理解含义，不是代码逻辑）
        3. AI 根据累积的洞察，智能选择下一口吃什么
        
        Args:
            chunk: 当前要分析的数据块
            context: 分析上下文（question, dimensions, measures）
            accumulated_insights: 已累积的洞察
            remaining_chunks: 剩余的数据块
            
        Returns:
            (new_insights, next_bite_decision, insights_quality)
        """
        # 准备数据
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
        if accumulated_insights:
            insights_text = "\n".join([
                f"- 洞察 {i+1} ({ins.type}): {ins.title}\n  描述: {ins.description[:100]}..."
                for i, ins in enumerate(accumulated_insights[:5])
            ])
        else:
            insights_text = "（还没有洞察，这是第一口）"
        
        # 格式化剩余数据块
        if remaining_chunks:
            remaining_text = "\n".join([
                f"- {rc.chunk_type} (优先级={rc.priority}): {rc.description}, 估算价值={rc.estimated_value}"
                for rc in remaining_chunks
            ])
        else:
            remaining_text = "（没有剩余数据块了）"
        
        try:
            # 延迟加载 prompt
            _load_prompts()
            
            if AI_ANALYSIS_PROMPT is None:
                logger.warning("AI_ANALYSIS_PROMPT 未加载，使用默认响应")
                return self._default_response(chunk.chunk_id, remaining_chunks)
            
            # 使用 Prompt 类格式化消息（自动注入 JSON Schema）
            messages = AI_ANALYSIS_PROMPT.format_messages(
                question=context.get("question", ""),
                accumulated_insights=insights_text,
                chunk_type=chunk.chunk_type,
                priority=chunk.priority,
                row_count=chunk.row_count,
                chunk_description=chunk.description,
                data_sample=data_sample,
                remaining_chunks=remaining_text,
            )
            
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            
            result = self._parse_ai_analysis_response(response.content, chunk.chunk_id)
            
            logger.info(
                f"AI analysis of {chunk.chunk_type}: "
                f"{len(result[0])} insights, "
                f"continue={result[1].should_continue}, "
                f"next={result[1].next_chunk_type}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to analyze chunk {chunk.chunk_type}: {e}")
            return self._default_response(chunk.chunk_id, remaining_chunks)
    
    def _parse_ai_analysis_response(
        self,
        content: str,
        chunk_id: int,
    ) -> Tuple[List[Insight], NextBiteDecision, InsightQuality]:
        """解析 AI 分析响应"""
        try:
            json_str = self._extract_json(content)
            if not json_str:
                logger.warning("No JSON found in AI response")
                return self._default_response(chunk_id, [])
            
            result = json.loads(json_str)
            
            # 解析新洞察
            new_insights = []
            for raw in result.get("new_insights", []):
                try:
                    insight = Insight(
                        type=self._normalize_type(raw.get("type", "pattern")),
                        title=raw.get("title", "未命名洞察"),
                        description=raw.get("description", ""),
                        importance=float(raw.get("importance", 0.5)),
                        evidence=raw.get("evidence"),
                        related_columns=raw.get("related_columns", []),
                        chunk_id=chunk_id,
                    )
                    new_insights.append(insight)
                except Exception as e:
                    logger.warning(f"Failed to parse insight: {e}")
            
            # 解析下一口决策
            nbd = result.get("next_bite_decision", {})
            next_bite = NextBiteDecision(
                should_continue=nbd.get("should_continue", True),
                next_chunk_type=nbd.get("next_chunk_type"),
                reason=nbd.get("reason", ""),
                eating_strategy=nbd.get("eating_strategy", ""),
                confidence=float(nbd.get("confidence", 0.5)),
            )
            
            # 解析洞察质量
            iq = result.get("insights_quality", {})
            quality = InsightQuality(
                completeness=float(iq.get("completeness", 0.0)),
                confidence=float(iq.get("confidence", 0.0)),
                need_more_data=iq.get("need_more_data", True),
                question_answered=iq.get("question_answered", False),
            )
            
            return (new_insights, next_bite, quality)
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return self._default_response(chunk_id, [])
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return self._default_response(chunk_id, [])
    
    def _default_response(
        self,
        chunk_id: int,
        remaining_chunks: List[PriorityChunk],
    ) -> Tuple[List[Insight], NextBiteDecision, InsightQuality]:
        """返回默认响应"""
        next_type = None
        if remaining_chunks:
            sorted_chunks = sorted(remaining_chunks, key=lambda x: x.priority)
            next_type = sorted_chunks[0].chunk_type if sorted_chunks else None
        
        return (
            [],
            NextBiteDecision(
                should_continue=bool(remaining_chunks),
                next_chunk_type=next_type,
                reason="解析失败，使用默认决策",
                eating_strategy="按优先级顺序继续",
                confidence=0.3,
            ),
            InsightQuality(
                completeness=0.0,
                confidence=0.0,
                need_more_data=True,
                question_answered=False,
            ),
        )
    
    async def analyze_chunk(
        self,
        chunk: DataChunk,
        context: Dict[str, Any],
        previous_insights: Optional[List[Insight]] = None
    ) -> List[Insight]:
        """
        分析单个数据块（兼容旧接口）
        """
        sample_data = chunk.data[:self.max_sample_rows]
        data_sample = json.dumps(sample_data, ensure_ascii=False, indent=2)
        
        # 格式化已有洞察
        if previous_insights:
            prev_text = "\n".join([f"- {i.title}" for i in previous_insights[:5]])
        else:
            prev_text = "（无）"
        
        try:
            # 延迟加载 prompt
            _load_prompts()
            
            if CHUNK_ANALYSIS_PROMPT is None:
                logger.warning("CHUNK_ANALYSIS_PROMPT 未加载")
                return []
            
            messages = CHUNK_ANALYSIS_PROMPT.format_messages(
                chunk_name=chunk.chunk_name,
                row_count=chunk.row_count,
                columns=", ".join(chunk.column_names),
                data_sample=data_sample,
                question=context.get("question", ""),
                dimensions=", ".join([d.get("name", str(d)) if isinstance(d, dict) else str(d) for d in context.get("dimensions", [])]),
                measures=", ".join([m.get("name", str(m)) if isinstance(m, dict) else str(m) for m in context.get("measures", [])]),
                previous_insights=prev_text,
            )
            
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            
            insights = self._parse_insights_response(response.content, chunk.chunk_id)
            logger.info(f"Analyzed chunk {chunk.chunk_name}: {len(insights)} insights")
            return insights
            
        except Exception as e:
            logger.error(f"Failed to analyze chunk {chunk.chunk_name}: {e}")
            return []
    
    async def analyze_full(
        self,
        data: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[Insight]:
        """
        分析完整数据集（用于小数据集 < 100 行）
        """
        sample_data = data[:self.max_sample_rows]
        data_str = json.dumps(sample_data, ensure_ascii=False, indent=2)
        columns = list(data[0].keys()) if data else []
        
        try:
            # 延迟加载 prompt
            _load_prompts()
            
            if INSIGHT_ANALYSIS_PROMPT is None:
                logger.warning("INSIGHT_ANALYSIS_PROMPT 未加载")
                return []
            
            messages = INSIGHT_ANALYSIS_PROMPT.format_messages(
                row_count=len(data),
                columns=", ".join(columns),
                data=data_str,
                question=context.get("question", ""),
                dimensions=", ".join([d.get("name", str(d)) if isinstance(d, dict) else str(d) for d in context.get("dimensions", [])]),
                measures=", ".join([m.get("name", str(m)) if isinstance(m, dict) else str(m) for m in context.get("measures", [])]),
            )
            
            llm = self._get_llm()
            response = await llm.ainvoke(messages)
            
            insights = self._parse_insights_response(response.content)
            logger.info(f"Analyzed full dataset: {len(insights)} insights")
            return insights
            
        except Exception as e:
            logger.error(f"Failed to analyze full dataset: {e}")
            return []
    
    def _parse_insights_response(
        self,
        content: str,
        chunk_id: Optional[int] = None
    ) -> List[Insight]:
        """解析洞察列表响应"""
        insights = []
        
        try:
            json_str = self._extract_json(content)
            if not json_str:
                logger.warning("No JSON found in LLM response")
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
                    insight = Insight(
                        type=self._normalize_type(raw.get("type", "pattern")),
                        title=raw.get("title", "未命名洞察"),
                        description=raw.get("description", ""),
                        importance=float(raw.get("importance", 0.5)),
                        evidence=raw.get("evidence"),
                        related_columns=raw.get("related_columns", []),
                        chunk_id=chunk_id,
                    )
                    insights.append(insight)
                except Exception as e:
                    logger.warning(f"Failed to parse insight: {e}")
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        
        return insights
    
    def _extract_json(self, content: str) -> Optional[str]:
        """从 LLM 响应中提取 JSON"""
        import re
        
        # 尝试原始 JSON 对象（不在代码块中）
        # 这是规范要求的格式
        content_stripped = content.strip()
        if content_stripped.startswith('{') and content_stripped.endswith('}'):
            return content_stripped
        if content_stripped.startswith('[') and content_stripped.endswith(']'):
            return content_stripped
        
        # 尝试 ```json ... ``` 块（兼容旧格式）
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
