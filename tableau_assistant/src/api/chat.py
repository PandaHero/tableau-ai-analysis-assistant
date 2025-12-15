"""
对话API端点

使用Pydantic模型提供类型安全的API接口
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
import json
import time
from typing import AsyncGenerator

from tableau_assistant.src.models.api import (
    VizQLQueryRequest,
    VizQLQueryResponse,
    ErrorResponse,
    StreamEvent
)
from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType

router = APIRouter(prefix="/api", tags=["chat"])


async def resolve_datasource_luid(request: VizQLQueryRequest) -> str:
    """
    解析数据源 LUID
    
    优先使用 datasource_luid，如果未提供则通过 datasource_name 查找。
    使用缓存减少 API 调用。
    
    Args:
        request: 查询请求
        
    Returns:
        数据源 LUID
        
    Raises:
        HTTPException: 如果无法解析数据源
    """
    # 优先使用 LUID
    if request.datasource_luid:
        return request.datasource_luid
    
    # 通过名称查找
    if request.datasource_name:
        from tableau_assistant.src.bi_platforms.tableau import get_datasource_luid_by_name, get_tableau_auth_async
        from tableau_assistant.src.capabilities.storage.store_manager import get_store_manager
        from tableau_assistant.src.config.settings import settings
        
        # 尝试从缓存获取
        store = get_store_manager()
        cache_key = f"datasource_luid:{request.datasource_name}"
        cached_luid = store.get("datasource_luid_cache", cache_key)
        
        if cached_luid:
            return cached_luid
        
        # 获取认证信息
        try:
            auth_ctx = await get_tableau_auth_async()
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=ErrorResponse(
                    error="AuthError",
                    message=f"Tableau 认证失败: {str(e)}"
                ).model_dump()
            )
        
        # 调用 API 查找（同步函数，在线程池中执行）
        import asyncio
        try:
            luid = await asyncio.to_thread(
                get_datasource_luid_by_name,
                api_key=auth_ctx.token,
                domain=settings.tableau_server_url,
                datasource_name=request.datasource_name,
                site=settings.tableau_site_name
            )
            if luid:
                # 缓存 1 小时
                store.set("datasource_luid_cache", cache_key, luid, ttl=3600)
                return luid
            else:
                raise HTTPException(
                    status_code=400,
                    detail=ErrorResponse(
                        error="DatasourceNotFound",
                        message=f"无法找到数据源: {request.datasource_name}"
                    ).model_dump()
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error="DatasourceNotFound",
                    message=f"无法找到数据源: {request.datasource_name}，错误: {str(e)}"
                ).model_dump()
            )
    
    # 都没有提供，使用环境变量默认值
    from tableau_assistant.src.config.settings import settings
    if settings.datasource_luid:
        return settings.datasource_luid
    
    raise HTTPException(
        status_code=400,
        detail=ErrorResponse(
            error="MissingDatasource",
            message="请提供 datasource_luid 或 datasource_name"
        ).model_dump()
    )


@router.post(
    "/chat",
    response_model=VizQLQueryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    }
)
async def chat_query(request: VizQLQueryRequest) -> VizQLQueryResponse:
    """
    VizQL查询API（同步版本）
    
    接收用户问题，返回完整的分析报告
    
    注意：
        - FastAPI自动使用VizQLQueryRequest验证请求
        - 验证通过后，request已经是验证过的Pydantic模型
        - 无需在工作流中重复验证
    
    Args:
        request: VizQL查询请求（已验证）
    
    Returns:
        VizQL查询响应
    
    Raises:
        HTTPException: 如果查询失败
    """
    try:
        session_id = request.session_id or f"session_{int(time.time())}"
        
        # 解析数据源 LUID
        datasource_luid = await resolve_datasource_luid(request)
        
        # 使用 WorkflowExecutor 执行同步查询
        executor = WorkflowExecutor(datasource_luid=datasource_luid)
        result = await executor.run(
            question=request.question,
            thread_id=session_id,
        )
        
        # 检查执行结果
        if not result.success:
            raise HTTPException(
                status_code=500,
                detail=ErrorResponse(
                    error="WorkflowError",
                    message=result.error or "工作流执行失败"
                ).model_dump()
            )
        
        # 从 insights 提取关键发现
        key_findings = []
        recommendations = []
        if result.insights:
            for insight in result.insights:
                if hasattr(insight, 'finding'):
                    key_findings.append(insight.finding)
                if hasattr(insight, 'recommendation') and insight.recommendation:
                    recommendations.append(insight.recommendation)
        
        # 构建分析路径
        analysis_path = []
        if result.semantic_query:
            analysis_path.append({
                "step": "understanding",
                "description": f"理解问题: {result.question}",
                "output": result.semantic_query.model_dump() if hasattr(result.semantic_query, 'model_dump') else str(result.semantic_query)
            })
        if result.mapped_query:
            analysis_path.append({
                "step": "field_mapping",
                "description": "字段映射完成",
                "output": result.mapped_query.model_dump() if hasattr(result.mapped_query, 'model_dump') else str(result.mapped_query)
            })
        if result.vizql_query:
            analysis_path.append({
                "step": "query_building",
                "description": "VizQL 查询构建完成",
                "output": result.vizql_query.model_dump() if hasattr(result.vizql_query, 'model_dump') else str(result.vizql_query)
            })
        
        # 生成执行摘要
        executive_summary = ""
        if result.replan_decision and hasattr(result.replan_decision, 'summary'):
            executive_summary = result.replan_decision.summary or ""
        elif key_findings:
            executive_summary = "; ".join(key_findings[:3])
        
        return VizQLQueryResponse(
            executive_summary=executive_summary,
            key_findings=key_findings,
            analysis_path=analysis_path,
            recommendations=recommendations,
            visualizations=[],
            metadata={
                "duration": result.duration,
                "replan_count": result.replan_count,
                "is_analysis_question": result.is_analysis_question,
            }
        )
        
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="ValidationError",
                message="输入验证失败",
                details=[
                    {"code": err["type"], "message": err["msg"], "field": err["loc"][0]}
                    for err in e.errors()
                ]
            ).model_dump()
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="InternalError",
                message=f"查询执行失败: {str(e)}"
            ).model_dump()
        )


async def generate_sse_events(
    question: str,
    session_id: str,
    datasource_luid: str,
) -> AsyncGenerator[str, None]:
    """
    生成SSE事件流
    
    使用 WorkflowExecutor.stream() 获取工作流事件并转换为 SSE 格式。
    支持 token 级别的流式输出。
    
    事件类型：
    - node_start: 节点开始执行
    - token: LLM 生成的 token（实时流式）
    - node_complete: 节点执行完成
    - complete: 工作流完成
    - error: 错误
    
    Args:
        question: 用户问题
        session_id: 会话ID
        datasource_luid: 数据源LUID
    
    Yields:
        SSE格式的事件字符串
    """
    try:
        executor = WorkflowExecutor(datasource_luid=datasource_luid)
        
        async for event in executor.stream(question, thread_id=session_id):
            # 转换为前端友好的格式
            sse_event = StreamEvent(
                event_type=event.type.value,
                data={
                    "node": event.node_name,
                    "content": event.content,
                    "output": event.output.model_dump() if event.output else None,
                },
                timestamp=event.timestamp
            )
            yield f"data: {sse_event.model_dump_json()}\n\n"
            
            # 完成或错误时结束
            if event.type in (EventType.COMPLETE, EventType.ERROR):
                break
                
    except Exception as e:
        error_event = StreamEvent(
            event_type="error",
            data={"message": str(e)},
            timestamp=time.time()
        )
        yield f"data: {error_event.model_dump_json()}\n\n"


@router.post("/chat/stream")
async def chat_query_stream(request: VizQLQueryRequest):
    """
    VizQL查询API（流式版本）
    
    使用SSE推送实时进度，支持 token 级别的流式输出。
    
    事件类型：
    - node_start: 节点开始执行
    - token: LLM 生成的 token（实时流式）
    - node_complete: 节点执行完成
    - complete: 工作流完成
    - error: 错误
    
    Args:
        request: VizQL查询请求（已验证）
    
    Returns:
        SSE流式响应
    """
    try:
        session_id = request.session_id or f"session_{int(time.time())}"
        
        # 解析数据源 LUID
        datasource_luid = await resolve_datasource_luid(request)
        
        return StreamingResponse(
            generate_sse_events(
                question=request.question,
                session_id=session_id,
                datasource_luid=datasource_luid,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="ValidationError",
                message="输入验证失败",
                details=[
                    {"code": err["type"], "message": err["msg"], "field": err["loc"][0]}
                    for err in e.errors()
                ]
            ).model_dump()
        )


@router.get("/health")
async def health_check():
    """
    健康检查
    
    检查服务各组件状态：
    - LLM 连接
    - Tableau API 连接
    - 存储服务
    """
    import logging
    logger = logging.getLogger(__name__)
    
    checks = {
        "llm": {"status": "unknown", "message": ""},
        "tableau": {"status": "unknown", "message": ""},
        "storage": {"status": "unknown", "message": ""},
    }
    
    # 检查 LLM
    try:
        from tableau_assistant.src.model_manager import get_llm
        llm = get_llm()
        checks["llm"] = {"status": "ok", "message": "LLM 连接正常"}
    except Exception as e:
        checks["llm"] = {"status": "error", "message": str(e)}
        logger.warning(f"LLM health check failed: {e}")
    
    # 检查 Tableau API
    try:
        from tableau_assistant.src.bi_platforms.tableau import get_tableau_auth_async
        # 只检查配置是否存在，不实际调用 API
        from tableau_assistant.src.config.settings import settings
        if settings.tableau_server_url and settings.tableau_site_name:
            checks["tableau"] = {"status": "ok", "message": "Tableau 配置正常"}
        else:
            checks["tableau"] = {"status": "warning", "message": "Tableau 配置不完整"}
    except Exception as e:
        checks["tableau"] = {"status": "error", "message": str(e)}
        logger.warning(f"Tableau health check failed: {e}")
    
    # 检查存储
    try:
        from tableau_assistant.src.capabilities.storage.store_manager import get_store_manager
        store = get_store_manager()
        checks["storage"] = {"status": "ok", "message": "存储服务正常"}
    except Exception as e:
        checks["storage"] = {"status": "error", "message": str(e)}
        logger.warning(f"Storage health check failed: {e}")
    
    # 计算总体状态
    all_ok = all(c["status"] == "ok" for c in checks.values())
    has_error = any(c["status"] == "error" for c in checks.values())
    
    overall_status = "healthy" if all_ok else ("degraded" if not has_error else "unhealthy")
    
    return {
        "status": overall_status,
        "timestamp": time.time(),
        "checks": checks
    }



