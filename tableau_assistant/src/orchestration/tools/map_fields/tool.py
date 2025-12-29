"""
map_fields Tool 实现

封装 FieldMapperNode，提供 LangChain Tool 接口。

策略（保留现有 RAG+LLM 混合策略）：
1. 缓存检查 → 命中直接返回
2. RAG 检索 → confidence >= 0.9 直接返回
3. LLM Fallback → 从 top-k candidates 中选择
4. RAG 不可用 → LLM Only

错误处理：映射失败直接返回结构化错误，不做重试
"""
import logging
import time
from typing import Dict, Any, Optional, List

from langchain_core.tools import tool
from langgraph.types import RunnableConfig

from tableau_assistant.src.orchestration.tools.map_fields.models import (
    MapFieldsInput,
    MapFieldsOutput,
    FieldMappingError,
    FieldMappingErrorType,
    FieldSuggestion,
    MappingResultItem,
)

logger = logging.getLogger(__name__)

# 低置信度阈值
LOW_CONFIDENCE_THRESHOLD = 0.7


@tool
def map_fields(
    semantic_query: Dict[str, Any],
    datasource_luid: str = "default",
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Map business terms to technical field names.
    
    将 SemanticQuery 中的业务术语映射到数据源中的技术字段名。
    使用 RAG + LLM 混合策略进行智能匹配。
    
    Args:
        semantic_query: SemanticQuery 的字典表示
        datasource_luid: 数据源标识符
        context: 用户问题上下文（用于消歧）
    
    Returns:
        MapFieldsOutput 的字典表示，包含：
        - success: 是否成功
        - mapped_query: 映射后的查询（成功时）
        - field_mappings: 字段映射详情
        - error: 错误信息（失败时）
    """
    import asyncio
    
    # 同步包装异步实现
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    result = loop.run_until_complete(
        _map_fields_impl(
            semantic_query=semantic_query,
            datasource_luid=datasource_luid,
            context=context,
            config=None,
        )
    )
    return result.model_dump()


async def map_fields_async(
    semantic_query: Dict[str, Any],
    datasource_luid: str = "default",
    context: Optional[str] = None,
    data_model: Optional["DataModel"] = None,
    config: Optional[RunnableConfig] = None,
) -> MapFieldsOutput:
    """
    异步版本的 map_fields Tool。
    
    Args:
        semantic_query: SemanticQuery 的字典表示
        datasource_luid: 数据源标识符
        context: 用户问题上下文
        data_model: 数据模型（直接传递，优先于从 config 获取）
        config: LangGraph 运行时配置（包含 middleware）
    
    Returns:
        MapFieldsOutput
    """
    return await _map_fields_impl(
        semantic_query=semantic_query,
        datasource_luid=datasource_luid,
        context=context,
        data_model=data_model,
        config=config,
    )


async def _map_fields_impl(
    semantic_query: Dict[str, Any],
    datasource_luid: str,
    context: Optional[str],
    data_model: Optional["DataModel"],
    config: Optional[RunnableConfig],
) -> MapFieldsOutput:
    """
    map_fields 核心实现。
    
    调用 FieldMapperNode 进行字段映射。
    """
    start_time = time.time()
    
    try:
        # 延迟导入避免循环依赖
        from tableau_assistant.src.core.models.query import SemanticQuery
        from tableau_assistant.src.core.models.field_mapping import MappedQuery, FieldMapping
        from tableau_assistant.src.agents.field_mapper.node import FieldMapperNode
        
        # 解析 SemanticQuery
        try:
            sq = SemanticQuery.model_validate(semantic_query)
        except Exception as e:
            logger.error(f"Invalid semantic_query: {e}")
            latency_ms = int((time.time() - start_time) * 1000)
            return MapFieldsOutput.fail(
                error=FieldMappingError(
                    type=FieldMappingErrorType.MAPPING_FAILED,
                    field="",
                    message=f"无效的 SemanticQuery: {e}"
                ),
                latency_ms=latency_ms
            )
        
        # 提取需要映射的字段
        terms_to_map = _extract_terms_from_semantic_query(sq)
        
        if not terms_to_map:
            # 没有需要映射的字段，直接返回成功
            latency_ms = int((time.time() - start_time) * 1000)
            mapped_query = MappedQuery(
                semantic_query=sq,
                field_mappings={},
                overall_confidence=1.0,
            )
            return MapFieldsOutput.ok(
                mapped_query=mapped_query.model_dump(),
                field_mappings={},
                overall_confidence=1.0,
                low_confidence_fields=[],
                latency_ms=latency_ms
            )
        
        # 获取或创建 FieldMapperNode
        mapper = await _get_field_mapper(datasource_luid, data_model, config)
        
        if mapper is None:
            latency_ms = int((time.time() - start_time) * 1000)
            # 找出第一个需要映射的字段作为错误字段
            first_field = list(terms_to_map.keys())[0] if terms_to_map else ""
            return MapFieldsOutput.fail(
                error=FieldMappingError(
                    type=FieldMappingErrorType.NO_METADATA,
                    field=first_field,
                    message="无法获取数据源元数据，请确保工作流已正确初始化"
                ),
                latency_ms=latency_ms
            )
        
        # 执行批量映射
        mapping_results = await mapper.map_fields_batch(
            terms=list(terms_to_map.keys()),
            datasource_luid=datasource_luid,
            context=context,
            role_filters=terms_to_map,
            state={},
            config=config,
        )
        
        # 检查映射结果
        failed_fields = []
        field_mappings_dict: Dict[str, FieldMapping] = {}
        field_mappings_output: Dict[str, MappingResultItem] = {}
        
        for term, result in mapping_results.items():
            if result.technical_field is None or result.confidence < 0.3:
                # 映射失败
                failed_fields.append((term, result))
            else:
                # 映射成功
                field_mappings_dict[term] = FieldMapping(
                    business_term=result.business_term,
                    technical_field=result.technical_field,
                    confidence=result.confidence,
                    mapping_source=result.mapping_source,
                    category=result.category,
                    level=result.level,
                    granularity=result.granularity,
                    alternatives=result.alternatives,
                )
                field_mappings_output[term] = MappingResultItem(
                    business_term=result.business_term,
                    technical_field=result.technical_field,
                    confidence=result.confidence,
                    mapping_source=result.mapping_source,
                    category=result.category,
                    level=result.level,
                    granularity=result.granularity,
                )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 如果有映射失败的字段，返回错误
        if failed_fields:
            first_failed = failed_fields[0]
            term, result = first_failed
            
            # 构建建议列表
            suggestions = []
            if result.alternatives:
                for alt in result.alternatives[:3]:
                    suggestions.append(FieldSuggestion(
                        field_name=alt.get("technical_field", ""),
                        confidence=alt.get("confidence", 0.0),
                        reason=alt.get("reason", "")
                    ))
            
            return MapFieldsOutput.fail(
                error=FieldMappingError(
                    type=FieldMappingErrorType.FIELD_NOT_FOUND,
                    field=term,
                    message=f"无法找到字段 '{term}' 的匹配",
                    suggestions=suggestions
                ),
                latency_ms=latency_ms
            )
        
        # 构建 MappedQuery
        mapped_query = MappedQuery(
            semantic_query=sq,
            field_mappings=field_mappings_dict,
        )
        
        # 计算低置信度字段
        low_confidence_fields = [
            term for term, mapping in field_mappings_output.items()
            if mapping.confidence < LOW_CONFIDENCE_THRESHOLD
        ]
        
        logger.info(
            f"map_fields completed: {len(field_mappings_output)} fields mapped, "
            f"overall_confidence={mapped_query.overall_confidence:.2f}, "
            f"latency={latency_ms}ms"
        )
        
        return MapFieldsOutput.ok(
            mapped_query=mapped_query.model_dump(),
            field_mappings=field_mappings_output,
            overall_confidence=mapped_query.overall_confidence or 1.0,
            low_confidence_fields=low_confidence_fields,
            latency_ms=latency_ms
        )
        
    except Exception as e:
        logger.error(f"map_fields failed: {e}", exc_info=True)
        latency_ms = int((time.time() - start_time) * 1000)
        return MapFieldsOutput.fail(
            error=FieldMappingError(
                type=FieldMappingErrorType.MAPPING_FAILED,
                field="",
                message=f"字段映射失败: {e}"
            ),
            latency_ms=latency_ms
        )


def _extract_terms_from_semantic_query(
    semantic_query: "SemanticQuery"
) -> Dict[str, Optional[str]]:
    """
    从 SemanticQuery 中提取需要映射的业务术语。
    
    注意：不再基于 Step1 的语义分类（measure/dimension）来限制字段搜索范围。
    因为：
    1. 对维度字段使用 COUNT/COUNTD 是完全合法的（如 COUNT(Order ID)）
    2. 用户语义上的"度量"可能在数据源中是维度字段
    3. VizQL 和 SQL 都支持对维度字段进行聚合计算
    
    所以字段映射时应该在整个元数据中搜索最匹配的字段，而不是限制在特定角色中。
    
    Args:
        semantic_query: SemanticQuery Pydantic 对象
        
    Returns:
        Dict mapping business term to None (no role filter)
    """
    terms = {}
    
    # 提取 measures - 不限制角色
    for measure in semantic_query.measures or []:
        if measure.field_name:
            terms[measure.field_name] = None  # 不限制角色，在整个元数据中搜索
    
    # 提取 dimensions - 不限制角色
    for dimension in semantic_query.dimensions or []:
        if dimension.field_name:
            terms[dimension.field_name] = None  # 不限制角色，在整个元数据中搜索
    
    # 提取 filters - 不限制角色
    for filter_spec in semantic_query.filters or []:
        if filter_spec.field_name and filter_spec.field_name not in terms:
            terms[filter_spec.field_name] = None
    
    # 提取 computations 中的字段 - 不限制角色
    for computation in semantic_query.computations or []:
        if computation.target and computation.target not in terms:
            terms[computation.target] = None
        # partition_by is now list[DimensionField], extract field_name from each
        for partition_dim in computation.partition_by or []:
            field_name = partition_dim.field_name if hasattr(partition_dim, 'field_name') else partition_dim
            if field_name and field_name not in terms:
                terms[field_name] = None
    
    return terms


async def _get_field_mapper(
    datasource_luid: str,
    data_model: Optional["DataModel"],
    config: Optional[RunnableConfig]
) -> Optional["FieldMapperNode"]:
    """
    获取或创建 FieldMapperNode 实例。
    
    优先使用直接传递的 data_model，其次从 WorkflowContext 获取。
    KnowledgeAssembler 内部使用 SqliteStore 缓存向量索引。
    
    Args:
        datasource_luid: 数据源标识符
        data_model: 直接传递的数据模型（优先使用）
        config: LangGraph 运行时配置
    """
    from tableau_assistant.src.agents.field_mapper.node import FieldMapperNode
    
    mapper = FieldMapperNode()
    
    # 优先使用直接传递的 data_model
    if data_model is None and config:
        # 尝试从 WorkflowContext 获取
        try:
            from tableau_assistant.src.orchestration.workflow.context import get_context
            ctx = get_context(config)
            if ctx:
                data_model = ctx.data_model
                datasource_luid = ctx.datasource_luid or datasource_luid
                logger.debug(f"从 WorkflowContext 获取 data_model: {data_model is not None}")
        except Exception as e:
            logger.warning(f"从 config 获取 WorkflowContext 失败: {e}")
    
    if data_model is None:
        logger.warning("无法获取 data_model，mapper 将无法正常工作")
        return None
    
    # 初始化 mapper
    try:
        if hasattr(data_model, 'fields') and data_model.fields:
            # load_metadata 内部会使用 SqliteStore 缓存
            mapper.load_metadata(
                fields=data_model.fields,
                datasource_luid=datasource_luid
            )
            logger.info(f"FieldMapper 已加载 {len(data_model.fields)} 个字段")
        
        # 设置 SemanticMapper - 复用 KnowledgeAssembler 的 FieldIndexer
        from tableau_assistant.src.infra.ai.rag.semantic_mapper import SemanticMapper
        
        # 从 mapper.assembler 获取已有的 FieldIndexer，避免重复构建索引
        if mapper.assembler is not None and hasattr(mapper.assembler, '_indexer'):
            field_indexer = mapper.assembler._indexer
            logger.debug(f"复用 KnowledgeAssembler 的 FieldIndexer: {field_indexer.field_count} 个字段")
        else:
            # 回退：创建新的 FieldIndexer
            from tableau_assistant.src.infra.ai.rag.field_indexer import FieldIndexer
            
            field_indexer = FieldIndexer(datasource_luid=datasource_luid)
            
            # 如果有字段数据，调用 index_fields
            if hasattr(data_model, 'fields') and data_model.fields:
                field_indexer.index_fields(data_model.fields)
        
        semantic_mapper = SemanticMapper(field_indexer=field_indexer)
        mapper.set_semantic_mapper(semantic_mapper)
        
        return mapper
        
    except Exception as e:
        logger.error(f"初始化 FieldMapper 失败: {e}")
        return None


__all__ = [
    "map_fields",
    "map_fields_async",
]
