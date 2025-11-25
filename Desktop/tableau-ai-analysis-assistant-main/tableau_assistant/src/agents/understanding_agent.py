"""
问题理解 Agent (v2 - 使用 BaseVizQLAgent 架构)

功能：
1. 理解用户问题的业务意图
2. 提取关键信息（时间范围、维度、度量等）
3. 识别问题类型和复杂度
4. 将复杂问题分解为子问题
5. 识别日期需求

设计原则：
- 使用 BaseVizQLAgent 提供的统一架构
- 统一使用流式输出
- 专注于语义理解，不验证字段
- AI 做理解，代码做执行
"""
from typing import Dict, Any, Optional
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.question import QuestionUnderstanding
from tableau_assistant.src.agents.base_agent import BaseVizQLAgent
from tableau_assistant.prompts.understanding import UNDERSTANDING_PROMPT


class UnderstandingAgent(BaseVizQLAgent):
    """
    Understanding Agent using BaseVizQLAgent architecture
    
    Analyzes user questions to:
    - Extract semantic information (dimensions, measures, filters)
    - Identify question type and complexity
    - Decompose complex questions into sub-questions
    - Identify date requirements
    """
    
    def __init__(self):
        """Initialize with Understanding Prompt"""
        super().__init__(UNDERSTANDING_PROMPT)
    
    def _prepare_input_data(
        self,
        state: VizQLState,
        metadata: Optional[Any] = None,
        use_metadata: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Prepare input data for understanding prompt
        
        Args:
            state: Current VizQL state
            metadata: Optional metadata (preprocessed)
            use_metadata: Whether to use metadata (default True)
            **kwargs: Additional arguments
        
        Returns:
            Dict with question, metadata, and max_date for prompt
        """
        # Get question (prefer boosted_question, fallback to original)
        question = state.get("boosted_question") or state.get("question", "")
        if not question:
            raise ValueError("问题不能为空")
        
        # Get metadata (from parameter or state)
        if use_metadata:
            if metadata is None:
                metadata = state.get("metadata")
            metadata_for_prompt = metadata if metadata else {}
        else:
            metadata_for_prompt = {}
        
        # Extract max_date from metadata for time range resolution
        max_date = "Unknown"
        if metadata and hasattr(metadata, 'max_date_by_field'):
            # Get the maximum date from all date fields
            max_dates = metadata.max_date_by_field
            if max_dates:
                # Use the first available max date
                max_date = next(iter(max_dates.values()), "Unknown")
        
        return {
            "question": question,
            "metadata": metadata_for_prompt,
            "max_date": max_date
        }
    
    def _fix_dimension_aggregations(self, result: QuestionUnderstanding) -> QuestionUnderstanding:
        """
        Auto-fix common dimension_aggregations errors (defensive programming)
        
        Rule: If all dimensions have aggregations, likely incorrect.
        Most queries have grouping dimensions without aggregations.
        
        Args:
            result: QuestionUnderstanding model instance
        
        Returns:
            Fixed QuestionUnderstanding model instance
        """
        import logging
        logger = logging.getLogger(__name__)
        
        for sq in result.sub_questions:
            # Only process QuerySubQuestion with dimension fields
            if not hasattr(sq, 'mentioned_dimensions') or not hasattr(sq, 'dimension_aggregations'):
                continue
            
            dims = sq.mentioned_dimensions
            aggs = sq.dimension_aggregations or {}
            
            # Detect error: All dimensions have aggregations → Likely incorrect
            if dims and len(aggs) == len(dims) and len(dims) > 1:
                logger.warning(
                    f"Auto-fix: All {len(dims)} dimensions have aggregations, clearing dimension_aggregations. "
                    f"Dimensions: {dims}, Aggregations: {aggs}. "
                    f"This is likely incorrect - most queries have grouping dimensions without aggregations."
                )
                sq.dimension_aggregations = {}
        
        return result
    
    def _process_result(
        self,
        result: QuestionUnderstanding,
        state: VizQLState
    ) -> Dict[str, Any]:
        """
        Process understanding result
        
        Args:
            result: QuestionUnderstanding model instance
            state: Current VizQL state
        
        Returns:
            Dict with understanding result for state update
        """
        # Apply defensive fix for dimension_aggregations
        result = self._fix_dimension_aggregations(result)
        
        return {
            "understanding": result,
            "current_stage": "planning"
        }


# Create agent instance for easy import
understanding_agent = UnderstandingAgent()


async def understanding_agent_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext],
    metadata: Optional[Dict[str, Any]] = None,
    use_metadata: bool = False,
    model_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    问题理解 Agent 节点（使用 BaseVizQLAgent 架构）
    
    职责：
    - 理解用户意图
    - 提取语义信息（不验证字段）
    - 识别问题类型和复杂度
    - 分解复杂问题
    
    注意：
    - 使用 BaseVizQLAgent 提供的统一执行流程
    - 可选使用元数据（参考字段信息）
    - 支持前端模型配置（model_config）
    - 统一使用流式输出
    
    Args:
        state: 当前状态
        runtime: 运行时上下文
        metadata: 可选的元数据（用于参考字段信息）
        use_metadata: 是否使用元数据（默认 True）
        model_config: 可选的模型配置（来自前端）
            - provider: "local", "azure", or "openai"
            - model_name: 模型名称
            - temperature: 温度设置
    
    Returns:
        状态更新（包含 understanding 字段）
    """
    return await understanding_agent.execute(
        state=state,
        runtime=runtime,
        metadata=metadata,
        use_metadata=use_metadata,
        model_config=model_config
    )


# ============= 导出 =============

__all__ = [
    "UnderstandingAgent",
    "understanding_agent",
    "understanding_agent_node",
]
