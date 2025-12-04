"""
维度层级推断Agent (v2 - 使用 BaseVizQLAgent 架构 + RAG 增强)

功能：
1. 根据字段元数据、统计信息推断维度层级
2. 识别维度的category、level、granularity
3. 识别父子关系
4. RAG 增强：复用历史推断结果作为 few-shot 示例

设计原则：
- 使用 BaseVizQLAgent 提供的统一架构
- 统一使用流式输出
- 专注于核心推断功能，移除复杂的后处理逻辑
- 必须使用LLM进行智能推断
- RAG 增强：检索相似历史模式，提供 few-shot 示例
"""
from typing import Dict, Any, Optional, List
import logging
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.dimension_hierarchy import DimensionHierarchyResult, DimensionAttributes
from tableau_assistant.src.agents.base_agent import BaseVizQLAgent
from tableau_assistant.prompts.dimension_hierarchy import DIMENSION_HIERARCHY_PROMPT

logger = logging.getLogger(__name__)


# ============= RAG 增强组件 =============

def _get_dimension_rag():
    """
    延迟加载 DimensionHierarchyRAG 组件
    
    Returns:
        DimensionHierarchyRAG 实例或 None（如果加载失败）
    """
    try:
        from tableau_assistant.src.capabilities.rag.dimension_pattern import DimensionHierarchyRAG
        return DimensionHierarchyRAG()
    except Exception as e:
        logger.warning(f"无法加载 DimensionHierarchyRAG: {e}")
        return None


def _build_few_shot_section(few_shot_examples: List[str]) -> str:
    """
    构建 few-shot 示例部分
    
    Args:
        few_shot_examples: few-shot 示例列表
    
    Returns:
        格式化的 few-shot 部分字符串
    """
    if not few_shot_examples:
        return ""
    
    section = """**Historical Reference Examples (from similar fields):**

The following are inference results from similar fields in the past. Use them as reference:

"""
    for i, example in enumerate(few_shot_examples[:3], 1):
        section += f"Example {i}:\n{example}\n\n"
    
    return section


# ============= Agent 类 =============

class DimensionHierarchyAgent(BaseVizQLAgent):
    """
    Dimension Hierarchy Agent using BaseVizQLAgent architecture with RAG enhancement
    
    Infers hierarchical attributes for dimension fields:
    - Category classification
    - Level assignment (1-5)
    - Parent-child relationships
    - Query and update valid_max_date for date fields
    
    RAG Enhancement:
    - Retrieves similar historical patterns as few-shot examples
    - Stores successful inferences for future retrieval
    """
    
    def __init__(self):
        """Initialize with Dimension Hierarchy Prompt"""
        super().__init__(DIMENSION_HIERARCHY_PROMPT)
        self._rag = None  # 延迟初始化
    
    @property
    def rag(self):
        """延迟加载 RAG 组件"""
        if self._rag is None:
            self._rag = _get_dimension_rag()
        return self._rag
    
    async def execute(
        self,
        state: VizQLState,
        runtime: Runtime[VizQLContext],
        model_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute dimension hierarchy inference with RAG enhancement and date field updates
        
        Args:
            state: Current VizQL state
            runtime: Runtime context
            model_config: Optional model configuration
            **kwargs: Additional arguments
        
        Returns:
            Dict with dimension_hierarchy for state update
        """
        # Call parent execute to do the inference
        result = await super().execute(state, runtime, model_config, **kwargs)
        
        # Get hierarchy from result
        hierarchy_dict = result.get("dimension_hierarchy")
        if hierarchy_dict:
            # Update date fields with valid_max_date (async query)
            await self._update_date_fields_in_metadata(hierarchy_dict, state, runtime)
            
            # Store successful inferences to RAG (for future retrieval)
            self._store_inference_results(hierarchy_dict, state)
        
        return result
    
    def _prepare_input_data(
        self,
        state: VizQLState,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Prepare input data for dimension hierarchy prompt with RAG enhancement
        
        Args:
            state: Current VizQL state (should contain Metadata object)
            **kwargs: Additional arguments
        
        Returns:
            Dict with dimensions and few_shot_section for prompt
        """
        from tableau_assistant.src.models.metadata import Metadata
        
        # Get metadata from state
        metadata = state.get("metadata")
        if not metadata:
            raise ValueError("元数据不存在，无法推断维度层级")
        
        # Ensure it's a Metadata object
        if not isinstance(metadata, Metadata):
            raise ValueError(f"元数据类型错误，期望 Metadata 对象，实际: {type(metadata)}")
        
        # Get dimension fields from Metadata object
        dimension_fields = metadata.get_dimensions()
        
        if not dimension_fields:
            raise ValueError("没有维度字段")
        
        # Prepare dimension info for prompt
        dimension_info = []
        all_few_shot_examples = []
        
        for field in dimension_fields:
            info = {
                "name": field.name,
                "caption": field.fieldCaption,
                "dataType": field.dataType,
                "description": field.description or "",
                "unique_count": field.unique_count or 0,
                "sample_values": (field.sample_values or [])[:5]  # Max 5
            }
            dimension_info.append(info)
            
            # RAG: Get few-shot examples for this field
            if self.rag:
                try:
                    rag_context = self.rag.get_inference_context(
                        field_caption=field.fieldCaption,
                        data_type=field.dataType,
                        sample_values=field.sample_values or [],
                        unique_count=field.unique_count or 0
                    )
                    
                    if rag_context.get("has_similar_patterns"):
                        # Collect up to 2 examples per field
                        examples = rag_context.get("few_shot_examples", [])[:2]
                        all_few_shot_examples.extend(examples)
                        logger.debug(f"RAG: 字段 '{field.fieldCaption}' 找到 {len(examples)} 个相似模式")
                except Exception as e:
                    logger.warning(f"RAG 检索失败: {e}")
        
        # Build few-shot section (limit to 5 examples total)
        few_shot_section = _build_few_shot_section(all_few_shot_examples[:5])
        
        logger.info(f"准备推断 {len(dimension_info)} 个维度字段, RAG 示例: {len(all_few_shot_examples[:5])} 个")
        
        return {
            "dimensions": dimension_info,
            "few_shot_section": few_shot_section
        }
    
    def _process_result(
        self,
        result: DimensionHierarchyResult,
        state: VizQLState
    ) -> Dict[str, Any]:
        """
        Process dimension hierarchy result
        
        Args:
            result: DimensionHierarchyResult model instance
            state: VizQLState
        
        Returns:
            Dict with dimension_hierarchy for state update
        """
        # Convert to dict format
        hierarchy_dict = {}
        for field_name, attrs in result.dimension_hierarchy.items():
            hierarchy_dict[field_name] = attrs.model_dump()
        
        # Calculate average confidence
        confidences = [attrs.level_confidence for attrs in result.dimension_hierarchy.values()]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        logger.info(f"维度层级推断完成，平均置信度: {avg_confidence:.2f}")
        
        return {
            "dimension_hierarchy": hierarchy_dict,
            "current_stage": "understanding"
        }
    
    def _store_inference_results(
        self,
        hierarchy_dict: Dict[str, Any],
        state: VizQLState
    ) -> None:
        """
        Store successful inference results to RAG for future retrieval
        
        存储所有成功的推断结果（不仅仅是高置信度），在检索时按 confidence 加权。
        这样可以积累更多的历史数据，提高 RAG 的覆盖率。
        
        **Validates: Requirements 9.3**
        
        Args:
            hierarchy_dict: Inference results
            state: VizQL state containing metadata
        """
        if not self.rag:
            return
        
        try:
            from tableau_assistant.src.models.metadata import Metadata
            
            metadata = state.get("metadata")
            if not isinstance(metadata, Metadata):
                return
            
            datasource_luid = getattr(metadata, 'datasource_luid', None)
            stored_count = 0
            skipped_count = 0
            
            for field_name, attrs in hierarchy_dict.items():
                confidence = attrs.get("level_confidence", 0)
                
                # 跳过置信度为 0 的结果（可能是推断失败）
                if confidence <= 0:
                    skipped_count += 1
                    continue
                
                # Find the field metadata
                field = None
                for f in metadata.get_dimensions():
                    if f.name == field_name:
                        field = f
                        break
                
                if not field:
                    skipped_count += 1
                    continue
                
                try:
                    self.rag.store_inference_result(
                        field_name=field_name,
                        field_caption=field.fieldCaption,
                        data_type=field.dataType,
                        sample_values=field.sample_values or [],
                        unique_count=field.unique_count or 0,
                        category=attrs.get("category", "other"),
                        category_detail=attrs.get("category_detail", ""),
                        level=attrs.get("level", 3),
                        granularity=attrs.get("granularity", "medium"),
                        reasoning=attrs.get("reasoning", ""),
                        confidence=confidence,
                        datasource_luid=datasource_luid
                    )
                    stored_count += 1
                except Exception as e:
                    logger.debug(f"存储推断结果失败: {field_name}, {e}")
                    skipped_count += 1
            
            if stored_count > 0:
                logger.info(f"RAG: 存储了 {stored_count} 个推断结果 (跳过 {skipped_count} 个)")
                
        except Exception as e:
            logger.warning(f"存储推断结果到 RAG 失败: {e}")


# Create agent instance for easy import
dimension_hierarchy_agent = DimensionHierarchyAgent()


# ============= 导出 =============

__all__ = [
    "DimensionHierarchyAgent",
    "dimension_hierarchy_agent",
]
