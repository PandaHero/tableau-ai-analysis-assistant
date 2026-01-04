"""
build_query Tool 实现

封装 QueryBuilderNode，提供 LangChain Tool 接口。

功能：
- 应用字段映射到 SemanticQuery
- 使用 TableauQueryBuilder 构建 VizQL 请求
- 支持表计算和 LOD 表达式

错误处理：构建失败直接返回结构化错误
"""
import logging
import time
from typing import Dict, Any, Optional, Union

from langchain_core.tools import tool
from langgraph.types import RunnableConfig

from tableau_assistant.src.agents.field_mapper.models import MappedQuery
from tableau_assistant.src.orchestration.tools.build_query.models import (
    BuildQueryInput,
    BuildQueryOutput,
    QueryBuildError,
    QueryBuildErrorType,
)

logger = logging.getLogger(__name__)


@tool
def build_query(
    mapped_query: Dict[str, Any],
    datasource_luid: str = "default",
    field_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build VizQL query from mapped query.
    
    将 MappedQuery 转换为 VizQL API 请求格式。
    
    Args:
        mapped_query: MappedQuery 的字典表示
        datasource_luid: 数据源标识符
        field_metadata: 字段元数据（用于日期类型检测）
    
    Returns:
        BuildQueryOutput 的字典表示，包含：
        - success: 是否成功
        - vizql_query: VizQL 查询请求（成功时）
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
        _build_query_impl(
            mapped_query=mapped_query,
            datasource_luid=datasource_luid,
            field_metadata=field_metadata,
            config=None,
        )
    )
    return result.model_dump()


async def build_query_async(
    mapped_query: Union[MappedQuery, Dict[str, Any], None],
    datasource_luid: str = "default",
    field_metadata: Optional[Dict[str, Any]] = None,
    config: Optional[RunnableConfig] = None,
) -> BuildQueryOutput:
    """
    异步版本的 build_query Tool。
    
    Args:
        mapped_query: MappedQuery 对象或字典表示
        datasource_luid: 数据源标识符
        field_metadata: 字段元数据
        config: LangGraph 运行时配置
    
    Returns:
        BuildQueryOutput
    """
    return await _build_query_impl(
        mapped_query=mapped_query,
        datasource_luid=datasource_luid,
        field_metadata=field_metadata,
        config=config,
    )


async def _build_query_impl(
    mapped_query: Union[MappedQuery, Dict[str, Any], None],
    datasource_luid: str,
    field_metadata: Optional[Dict[str, Any]],
    config: Optional[RunnableConfig],
) -> BuildQueryOutput:
    """
    build_query 核心实现。
    
    直接使用 TableauQueryBuilder 进行查询构建。
    
    Args:
        mapped_query: MappedQuery 对象或字典表示
    """
    start_time = time.time()
    
    try:
        from tableau_assistant.src.platforms.tableau.query_builder import TableauQueryBuilder
        
        # 解析 MappedQuery - 支持对象或字典
        if not mapped_query:
            latency_ms = int((time.time() - start_time) * 1000)
            return BuildQueryOutput.fail(
                error=QueryBuildError(
                    type=QueryBuildErrorType.MISSING_INPUT,
                    message="未提供 mapped_query",
                ),
                latency_ms=latency_ms
            )
        
        # 如果已经是 MappedQuery 对象，直接使用
        if isinstance(mapped_query, MappedQuery):
            mq = mapped_query
        else:
            # 否则从 dict 解析
            try:
                mq = MappedQuery.model_validate(mapped_query)
            except Exception as e:
                logger.error(f"Invalid mapped_query: {e}")
                latency_ms = int((time.time() - start_time) * 1000)
                return BuildQueryOutput.fail(
                    error=QueryBuildError(
                        type=QueryBuildErrorType.VALIDATION_FAILED,
                        message=f"无效的 MappedQuery: {e}",
                    ),
                    latency_ms=latency_ms
                )
        
        # 从 config 获取 datasource_luid
        if config:
            try:
                from tableau_assistant.src.orchestration.workflow.context import get_context
                ctx = get_context(config)
                if ctx and ctx.datasource_luid:
                    datasource_luid = ctx.datasource_luid
                # 获取 field_metadata
                if ctx and ctx.data_model and not field_metadata:
                    fields = getattr(ctx.data_model, 'fields', [])
                    field_metadata = {
                        getattr(f, 'name', ''): {
                            'dataType': getattr(f, 'data_type', ''),
                            'role': getattr(f, 'role', ''),
                        }
                        for f in fields
                    }
            except Exception as e:
                logger.warning(f"从 config 获取上下文失败: {e}")
        
        # 从 MappedQuery 获取 SemanticQuery
        semantic_query = mq.semantic_query
        if not semantic_query:
            latency_ms = int((time.time() - start_time) * 1000)
            return BuildQueryOutput.fail(
                error=QueryBuildError(
                    type=QueryBuildErrorType.VALIDATION_FAILED,
                    message="MappedQuery 中缺少 semantic_query",
                ),
                latency_ms=latency_ms
            )
        
        # 使用 TableauQueryBuilder 构建查询
        builder = TableauQueryBuilder()
        
        # 先验证
        validation_result = builder.validate(semantic_query)
        if not validation_result.is_valid:
            error_msgs = [e.message for e in validation_result.errors]
            latency_ms = int((time.time() - start_time) * 1000)
            return BuildQueryOutput.fail(
                error=QueryBuildError(
                    type=QueryBuildErrorType.VALIDATION_FAILED,
                    message=f"查询验证失败: {'; '.join(error_msgs)}",
                ),
                latency_ms=latency_ms
            )
        
        # 构建 VizQL 查询
        vizql_dict = builder.build(
            semantic_query,
            datasource_id=datasource_luid,
            field_metadata=field_metadata or {}
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 统计信息
        fields = vizql_dict.get('fields', [])
        filters = vizql_dict.get('filters') or []
        sorts = vizql_dict.get('sorts') or []
        
        # 检查是否有计算字段
        has_computations = any(
            'tableCalculation' in f or 'calculation' in f
            for f in fields
        )
        
        logger.info(
            f"build_query completed: {len(fields)} fields, "
            f"{len(filters)} filters, {len(sorts)} sorts, "
            f"latency={latency_ms}ms"
        )
        
        return BuildQueryOutput.ok(
            vizql_query=vizql_dict,
            field_count=len(fields),
            has_filters=len(filters) > 0,
            has_sorts=len(sorts) > 0,
            has_computations=has_computations,
            latency_ms=latency_ms
        )
        
    except Exception as e:
        logger.error(f"build_query failed: {e}", exc_info=True)
        latency_ms = int((time.time() - start_time) * 1000)
        
        # 判断错误类型
        error_type = QueryBuildErrorType.BUILD_FAILED
        error_msg = str(e)
        
        if "computation" in error_msg.lower():
            error_type = QueryBuildErrorType.INVALID_COMPUTATION
        elif "unsupported" in error_msg.lower():
            error_type = QueryBuildErrorType.UNSUPPORTED_OPERATION
        
        return BuildQueryOutput.fail(
            error=QueryBuildError(
                type=error_type,
                message=f"查询构建失败: {e}",
            ),
            latency_ms=latency_ms
        )


__all__ = [
    "build_query",
    "build_query_async",
]
