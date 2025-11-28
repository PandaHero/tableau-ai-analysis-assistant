"""
维度层级推断Agent (v2 - 使用 BaseVizQLAgent 架构)

功能：
1. 根据字段元数据、统计信息推断维度层级
2. 识别维度的category、level、granularity
3. 识别父子关系

设计原则：
- 使用 BaseVizQLAgent 提供的统一架构
- 统一使用流式输出
- 专注于核心推断功能，移除复杂的后处理逻辑
- 必须使用LLM进行智能推断
"""
from typing import Dict, Any, Optional
import logging
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.models.state import VizQLState
from tableau_assistant.src.models.dimension_hierarchy import DimensionHierarchyResult, DimensionAttributes
from tableau_assistant.src.agents.base_agent import BaseVizQLAgent
from tableau_assistant.prompts.dimension_hierarchy import DIMENSION_HIERARCHY_PROMPT

logger = logging.getLogger(__name__)


# ============= Agent 类 =============

class DimensionHierarchyAgent(BaseVizQLAgent):
    """
    Dimension Hierarchy Agent using BaseVizQLAgent architecture
    
    Infers hierarchical attributes for dimension fields:
    - Category classification
    - Level assignment (1-5)
    - Parent-child relationships
    - Query and update valid_max_date for date fields
    """
    
    def __init__(self):
        """Initialize with Dimension Hierarchy Prompt"""
        super().__init__(DIMENSION_HIERARCHY_PROMPT)
    
    async def execute(
        self,
        state: VizQLState,
        runtime: Runtime[VizQLContext],
        model_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute dimension hierarchy inference with date field updates
        
        Override to add date field max value querying after inference
        
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
        
        return result
    
    def _prepare_input_data(
        self,
        state: VizQLState,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Prepare input data for dimension hierarchy prompt
        
        Args:
            state: Current VizQL state (should contain Metadata object)
            **kwargs: Additional arguments
        
        Returns:
            Dict with dimensions for prompt
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
        
        logger.info(f"准备推断 {len(dimension_info)} 个维度字段")
        
        return {
            "dimensions": dimension_info
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
        
        # Note: Date field updates happen in execute() method after this
        
        return {
            "dimension_hierarchy": hierarchy_dict,
            "current_stage": "understanding"
        }
    
    async def _update_date_fields_in_metadata(
        self,
        hierarchy_dict: Dict[str, Any],
        state: VizQLState,
        runtime: Runtime[VizQLContext]
    ) -> None:
        """
        获取日期字段的有效最大日期值并回写到元数据
        
        通过查询数据库获取每个日期字段的最大日期值（筛选度量>0）
        
        Args:
            hierarchy_dict: 维度层级字典
            state: 当前状态
            runtime: Runtime 对象（用于获取配置）
        """
        import asyncio
        from tableau_assistant.src.models.metadata import Metadata
        from tableau_assistant.src.bi_platforms.tableau.metadata import fetch_valid_max_date_async
        from tableau_assistant.src.capabilities.storage.store_manager import StoreManager
        from tableau_assistant.src.models.context import get_tableau_config
        
        # 识别日期字段（category包含"时间"、"日期"、"temporal"等关键词）
        date_fields = []
        for field_name, attrs in hierarchy_dict.items():
            category = attrs.get("category", "").lower()
            if any(keyword in category for keyword in ["时间", "日期", "time", "date", "temporal"]):
                date_fields.append(field_name)
        
        if not date_fields:
            logger.info("未识别到日期字段，跳过日期值更新")
            return
        
        logger.info(f"识别到 {len(date_fields)} 个日期字段: {date_fields}")
        
        # 获取元数据（Metadata 对象）
        metadata = state.get("metadata")
        if not metadata or not isinstance(metadata, Metadata):
            logger.warning("状态中没有有效的 Metadata 对象，无法更新日期字段")
            return
        
        # 获取第一个度量字段（用于筛选有效数据）
        measures = metadata.get_measures()
        if not measures:
            logger.warning("未找到度量字段，无法查询有效最大日期")
            return
        
        measure_field = measures[0].fieldCaption
        logger.info(f"使用度量字段: {measure_field}")
        
        # 获取 Tableau 配置
        store_manager = StoreManager(runtime.store)
        tableau_config = get_tableau_config(store_manager)
        tableau_token = tableau_config["tableau_token"]
        tableau_site = tableau_config["tableau_site"]
        tableau_domain = tableau_config["tableau_domain"]
        datasource_luid = runtime.context.datasource_luid
        
        # 异步查询每个日期字段的有效最大值
        tasks = []
        for date_field in date_fields:
            task = fetch_valid_max_date_async(
                api_key=tableau_token,
                domain=tableau_domain,
                datasource_luid=datasource_luid,
                date_field_name=date_field,
                measure_field_name=measure_field,
                site=tableau_site
            )
            tasks.append((date_field, task))
        
        # 并发执行所有查询
        results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
        
        # 更新元数据
        for (date_field, _), valid_max_date in zip(tasks, results):
            if isinstance(valid_max_date, Exception):
                logger.warning(f"查询日期字段 {date_field} 失败: {valid_max_date}")
                continue
            
            if valid_max_date:
                # 获取字段对象
                field_obj = metadata.get_field(date_field)
                if field_obj:
                    # 回写到字段
                    field_obj.valid_max_date = valid_max_date
                    logger.info(f"✓ 日期字段 {date_field} 的有效最大日期: {valid_max_date}")
                    
                    # 同时更新 hierarchy_dict
                    hierarchy_dict[date_field]["valid_max_date"] = valid_max_date


# Create agent instance for easy import
dimension_hierarchy_agent = DimensionHierarchyAgent()


# ============= 导出 =============

__all__ = [
    "DimensionHierarchyAgent",
    "dimension_hierarchy_agent",
]
