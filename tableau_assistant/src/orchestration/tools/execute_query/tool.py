"""
execute_query Tool 实现

封装 ExecuteNode，提供 LangChain Tool 接口。

功能：
- 执行 VizQL API 调用
- 解析 API 响应
- 大结果集处理（通过 FilesystemMiddleware）

错误处理：执行失败直接返回结构化错误
"""
import logging
import time
from typing import Dict, Any, Optional

from langchain_core.tools import tool
from langgraph.types import RunnableConfig

from tableau_assistant.src.orchestration.tools.execute_query.models import (
    ExecuteQueryInput,
    ExecuteQueryOutput,
    ExecutionError,
    ExecutionErrorType,
)

logger = logging.getLogger(__name__)

# 大结果集阈值（行数）
LARGE_RESULT_THRESHOLD = 1000


@tool
def execute_query(
    vizql_query: Dict[str, Any],
    datasource_luid: str = "default",
) -> Dict[str, Any]:
    """
    Execute VizQL query against Tableau Data Service.
    
    执行 VizQL 查询并返回结果。
    
    Args:
        vizql_query: VizQLQueryRequest 的字典表示
        datasource_luid: 数据源标识符
    
    Returns:
        ExecuteQueryOutput 的字典表示，包含：
        - success: 是否成功
        - data: 查询结果数据（成功时）
        - columns: 列元数据
        - row_count: 返回的行数
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
        _execute_query_impl(
            vizql_query=vizql_query,
            datasource_luid=datasource_luid,
            config=None,
        )
    )
    return result.model_dump()


async def execute_query_async(
    vizql_query: Dict[str, Any],
    datasource_luid: str = "default",
    config: Optional[RunnableConfig] = None,
) -> ExecuteQueryOutput:
    """
    异步版本的 execute_query Tool。
    
    Args:
        vizql_query: VizQLQueryRequest 的字典表示
        datasource_luid: 数据源标识符
        config: LangGraph 运行时配置
    
    Returns:
        ExecuteQueryOutput
    """
    return await _execute_query_impl(
        vizql_query=vizql_query,
        datasource_luid=datasource_luid,
        config=config,
    )


async def _execute_query_impl(
    vizql_query: Dict[str, Any],
    datasource_luid: str,
    config: Optional[RunnableConfig],
) -> ExecuteQueryOutput:
    """
    execute_query 核心实现。
    
    直接使用 VizQLClient 执行查询。
    """
    start_time = time.time()
    
    try:
        # 延迟导入避免循环依赖
        from tableau_assistant.src.platforms.tableau.vizql_client import VizQLClient
        from tableau_assistant.src.platforms.tableau import ensure_valid_auth_async, TableauAuthError
        
        # 验证输入
        if not vizql_query:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return ExecuteQueryOutput.fail(
                error=ExecutionError(
                    type=ExecutionErrorType.MISSING_INPUT,
                    message="未提供 vizql_query",
                ),
                execution_time_ms=execution_time_ms
            )
        
        # 从 config 获取上下文
        api_key = None
        site = None
        domain = None
        
        if config:
            try:
                from tableau_assistant.src.orchestration.workflow.context import get_context
                ctx = get_context(config)
                if ctx:
                    datasource_luid = ctx.datasource_luid or datasource_luid
            except Exception as e:
                logger.warning(f"从 config 获取上下文失败: {e}")
        
        # 获取认证信息
        try:
            auth_ctx = await ensure_valid_auth_async(config)
            api_key = auth_ctx.api_key
            site = auth_ctx.site
            domain = auth_ctx.domain
            logger.debug(
                f"使用 Tableau 认证 (method={auth_ctx.auth_method}, "
                f"domain={domain}, remaining={auth_ctx.remaining_seconds:.0f}s)"
            )
        except TableauAuthError as e:
            logger.error(f"Tableau 认证失败: {e}")
            execution_time_ms = int((time.time() - start_time) * 1000)
            return ExecuteQueryOutput.fail(
                error=ExecutionError(
                    type=ExecutionErrorType.AUTH_ERROR,
                    message=f"Tableau 认证失败: {e}",
                    suggestion="请检查 API 密钥或重新登录"
                ),
                execution_time_ms=execution_time_ms
            )
        
        # 执行查询
        client = None
        try:
            client = VizQLClient(domain=domain)
            result = await client.query_datasource_async(
                datasource_luid=datasource_luid,
                query=vizql_query,
                api_key=api_key,
                site=site,
            )
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # 解析结果
            data = result.get('data', [])
            columns = result.get('columns', [])
            row_count = len(data)
            query_id = result.get('queryId')
            
            # 检查是否为大结果集
            is_large = row_count > LARGE_RESULT_THRESHOLD
            file_path = None
            
            # 大结果集处理（FilesystemMiddleware 会在外层处理）
            if is_large:
                logger.info(
                    f"Large result set detected: {row_count} rows "
                    f"(threshold: {LARGE_RESULT_THRESHOLD})"
                )
            
            logger.info(
                f"execute_query completed: {row_count} rows, "
                f"execution_time={execution_time_ms}ms"
            )
            
            return ExecuteQueryOutput.ok(
                data=data,
                columns=columns,
                row_count=row_count,
                query_id=query_id,
                file_path=file_path,
                is_large_result=is_large,
                execution_time_ms=execution_time_ms
            )
                
        finally:
            if client:
                client.close()
                
    except Exception as e:
        logger.error(f"execute_query failed: {e}", exc_info=True)
        execution_time_ms = int((time.time() - start_time) * 1000)
        
        error_type = _classify_error(str(e))
        return ExecuteQueryOutput.fail(
            error=ExecutionError(
                type=error_type,
                message=f"查询执行失败: {e}",
            ),
            execution_time_ms=execution_time_ms
        )


def _classify_error(error_msg: str) -> ExecutionErrorType:
    """
    根据错误消息分类错误类型。
    """
    if not error_msg:
        return ExecutionErrorType.EXECUTION_FAILED
    
    error_lower = error_msg.lower()
    
    if "timeout" in error_lower or "timed out" in error_lower:
        return ExecutionErrorType.TIMEOUT
    elif "auth" in error_lower or "unauthorized" in error_lower or "401" in error_lower:
        return ExecutionErrorType.AUTH_ERROR
    elif "invalid" in error_lower or "malformed" in error_lower:
        return ExecutionErrorType.INVALID_QUERY
    elif "api" in error_lower or "vizql" in error_lower:
        return ExecutionErrorType.API_ERROR
    else:
        return ExecutionErrorType.EXECUTION_FAILED


__all__ = [
    "execute_query",
    "execute_query_async",
]
