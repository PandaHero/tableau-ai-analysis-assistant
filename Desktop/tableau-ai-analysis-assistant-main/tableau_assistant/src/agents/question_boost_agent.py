"""
问题Boost Agent (v2 - 使用 BaseVizQLAgent 架构)

功能：
1. 优化和增强用户的数据分析问题
2. 补充缺失信息（时间范围、维度、度量等）
3. 生成相关问题建议
4. 检索相似历史问题

设计原则：
- AI做优化，代码做执行
- 不使用工具（遵循设计文档）
- 统一使用流式输出，手动解析 JSON
- 使用 BaseVizQLAgent 提供的统一架构

元数据预处理要求（需求 1.1-1.5）：
- 元数据应该在问题处理之前预加载
- 维度层级（dimension_hierarchy）应该已经推断完成
- Sample values 应该已经填充
- 元数据格式化由 MetadataManager 负责，Agent 直接使用
"""
from typing import Dict, Any, Optional
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.boost import QuestionBoost
from tableau_assistant.src.agents.base_agent import BaseVizQLAgent
from tableau_assistant.prompts.question_boost import QUESTION_BOOST_PROMPT


class QuestionBoostAgent(BaseVizQLAgent):
    """
    Question Boost Agent using BaseVizQLAgent architecture
    
    Enhances user questions by:
    - Adding missing context (time ranges, dimensions, measures)
    - Making questions more specific and actionable
    - Providing related suggestions
    """
    
    def __init__(self):
        """Initialize with Question Boost Prompt"""
        super().__init__(QUESTION_BOOST_PROMPT)
    
    def _prepare_input_data(
        self,
        state: VizQLState,
        metadata: Optional[Any] = None,
        use_metadata: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Prepare input data for question boost prompt
        
        Assumes metadata is already preprocessed with:
        - Dimension hierarchy inferred
        - Sample values populated
        - Enhanced structure ready
        
        Args:
            state: Current VizQL state (should contain preprocessed metadata)
            metadata: Optional metadata override (already preprocessed)
            use_metadata: Whether to use metadata (default True)
            **kwargs: Additional arguments
        
        Returns:
            Dict with question and metadata for prompt
        """
        # Get question from state
        question = state.get("question", "")
        if not question:
            raise ValueError("问题不能为空")
        
        # Get metadata (from parameter or state)
        # Metadata should already be preprocessed by MetadataManager
        if use_metadata:
            if metadata is None:
                metadata = state.get("metadata")
            
            # Metadata is expected to be already in the correct format
            # (preprocessed with dimension_hierarchy and sample_values)
            # Just pass it directly to the prompt
            metadata_for_prompt = metadata if metadata else {}
        else:
            metadata_for_prompt = {}
        
        return {
            "question": question,
            "metadata": metadata_for_prompt
        }
    
    def _process_result(
        self,
        result: QuestionBoost,
        state: VizQLState
    ) -> Dict[str, Any]:
        """
        Process question boost result
        
        Args:
            result: QuestionBoost model instance
            state: Current VizQL state
        
        Returns:
            Dict with boost result and boosted_question for state update
        """
        return {
            "boost": result,
            "boosted_question": result.boosted_question
        }


# Create agent instance for easy import
question_boost_agent = QuestionBoostAgent()


async def question_boost_agent_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext],
    metadata: Optional[Dict[str, Any]] = None,
    use_metadata: bool = False,
    model_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    问题Boost Agent节点（使用 BaseVizQLAgent 架构）
    
    职责：
    - 优化用户问题
    - 补充缺失信息
    - 生成相关建议
    
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
        状态更新（包含boost字段）
    """
    # Metadata should already be in state (preprocessed)
    # If not provided and not in state, try to get it
    if use_metadata and metadata is None and "metadata" not in state:
        try:
            from tableau_assistant.src.components.metadata_manager import MetadataManager
            
            metadata_manager = MetadataManager(runtime)
            # Get enhanced metadata with dimension_hierarchy and sample_values
            metadata_obj = await metadata_manager.get_metadata_async(
                use_cache=True,
                enhance=True  # Get enhanced metadata
            )
            
            # Convert to dict format expected by prompt
            # This should include dimension_hierarchy and sample_values
            metadata = metadata_obj.model_dump() if hasattr(metadata_obj, 'model_dump') else metadata_obj
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"获取元数据失败，将不使用元数据: {e}")
            metadata = None
    
    # 使用 agent 执行
    try:
        result = await question_boost_agent.execute(
            state=state,
            runtime=runtime,
            metadata=metadata,
            use_metadata=use_metadata,
            model_config=model_config
        )
        return result
    
    except Exception as e:
        # 错误处理：返回原问题
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"问题优化失败: {e}")
        
        question = state.get("question", "")
        return {
            "boost": QuestionBoost(
                is_data_analysis_question=True,
                original_question=question,
                boosted_question=question,
                changes=[],
                reasoning=f"优化失败: {str(e)}",
                confidence=0.0
            ),
            "boosted_question": question
        }


# ============= 导出 =============

__all__ = [
    "QuestionBoostAgent",
    "question_boost_agent",
    "question_boost_agent_node",
]
