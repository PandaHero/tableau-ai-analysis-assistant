"""
对话API端点

使用Pydantic模型提供类型安全的API接口
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
import json
import time
from typing import AsyncGenerator, Optional

from tableau_assistant.src.api.models import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    StreamEvent,
    KeyFinding,
    AnalysisStep,
    Recommendation,
    Visualization,
)
from tableau_assistant.src.orchestration.workflow.executor import WorkflowExecutor, EventType

router = APIRouter(prefix="/api", tags=["chat"])


async def resolve_datasource_luid(request: ChatRequest) -> tuple[str, str]:
    """
    解析数据源 LUID 和对应的 Tableau 域名
    
    优先使用 datasource_luid，如果未提供则通过 datasource_name 查找。
    使用缓存减少 API 调用。
    支持多 Tableau 环境：
    - 如果提供了 tableau_domain，直接使用对应配置
    - 如果是 desktop 环境且未提供 domain，尝试所有配置找到数据源
    
    Args:
        request: 查询请求
        
    Returns:
        (datasource_luid, tableau_domain) 元组
        
    Raises:
        HTTPException: 如果无法解析数据源
    """
    import logging
    import asyncio
    logger = logging.getLogger(__name__)
    
    # 调试日志：打印收到的 Tableau 环境信息
    logger.info(f"收到请求 - tableau_domain: {request.tableau_domain}, tableau_site: {request.tableau_site}, tableau_context: {request.tableau_context}")
    logger.info(f"数据源连接信息: {request.datasource_connection_info}")
    logger.info(f"数据源: datasource_luid={request.datasource_luid}, datasource_name='{request.datasource_name}'")
    
    from tableau_assistant.src.platforms.tableau import get_datasource_luid_by_name, get_tableau_auth_async
    from tableau_assistant.src.infra.storage import get_langgraph_store
    from tableau_assistant.src.infra.config.settings import settings
    
    store = get_langgraph_store()
    tableau_config = settings.get_tableau_config()
    
    # 优先使用 LUID
    if request.datasource_luid:
        return request.datasource_luid, tableau_config.domain
    
    # 通过名称查找
    if request.datasource_name:
        return await _find_datasource_in_env(
            request.datasource_name,
            tableau_config.domain,
            request.tableau_site or tableau_config.site,
            store,
            logger
        )
    
    # 都没有提供，使用环境变量默认值
    if settings.datasource_luid:
        return settings.datasource_luid, tableau_config.domain
    
    raise HTTPException(
        status_code=400,
        detail=ErrorResponse(
            error="MissingDatasource",
            message="请提供 datasource_luid 或 datasource_name"
        ).model_dump()
    )


async def _find_datasource_in_env(
    datasource_name: str,
    tableau_domain: str,
    tableau_site: str,
    store,
    logger
) -> tuple[str, str]:
    """
    在指定的 Tableau 环境中查找数据源
    
    Args:
        datasource_name: 数据源名称
        tableau_domain: Tableau 域名
        tableau_site: Tableau 站点
        store: 缓存存储
        logger: 日志记录器
        
    Returns:
        (datasource_luid, tableau_domain) 元组
        
    Raises:
        HTTPException: 如果无法找到数据源
    """
    import asyncio
    from tableau_assistant.src.platforms.tableau import get_datasource_luid_by_name, get_tableau_auth_async
    
    # 尝试从缓存获取
    cache_key = f"datasource_luid:{tableau_domain}:{datasource_name}"
    cached_item = store.get(namespace=("datasource_luid_cache",), key=cache_key)
    
    if cached_item:
        cached_luid = cached_item.value.get("luid")
        logger.info(f"从缓存获取数据源 LUID: {cached_luid}")
        return cached_luid, tableau_domain
    
    # 获取认证信息
    try:
        auth_ctx = await get_tableau_auth_async(tableau_domain)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="AuthError",
                message=f"Tableau 认证失败 ({tableau_domain}): {str(e)}"
            ).model_dump()
        )
    
    # 调用 API 查找
    try:
        logger.info(f"查找数据源: name='{datasource_name}', domain={tableau_domain}, site={tableau_site}")
        luid = await asyncio.to_thread(
            get_datasource_luid_by_name,
            api_key=auth_ctx.api_key,
            domain=tableau_domain,
            datasource_name=datasource_name,
            site=tableau_site
        )
        logger.info(f"查找结果: luid={luid}")
        if luid:
            # 缓存 1 小时
            store.put(namespace=("datasource_luid_cache",), key=cache_key, value={"luid": luid}, ttl=3600)
            return luid, tableau_domain
        else:
            raise HTTPException(
                status_code=400,
                detail=ErrorResponse(
                    error="DatasourceNotFound",
                    message=f"无法找到数据源: {datasource_name}"
                ).model_dump()
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error="DatasourceNotFound",
                message=f"无法找到数据源: {datasource_name}，错误: {str(e)}"
            ).model_dump()
        )


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    }
)
async def chat_query(request: ChatRequest) -> ChatResponse:
    """
    聊天查询API（同步版本）
    
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
        
        # 解析数据源 LUID 和对应的 Tableau 域名
        datasource_luid, tableau_domain = await resolve_datasource_luid(request)
        
        # 使用 WorkflowExecutor 执行同步查询（多环境支持）
        executor = WorkflowExecutor(
            datasource_luid=datasource_luid,
            tableau_domain=tableau_domain,
        )
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
        
        # 处理非分析问题（澄清、通用响应等）
        if not result.is_analysis_question:
            return ChatResponse(
                executive_summary=result.non_analysis_response or result.general_response or result.clarification_question or "",
                clarification_question=result.clarification_question,
                general_response=result.general_response,
                metadata={
                    "duration": result.duration,
                    "is_analysis_question": False,
                }
            )
        
        # 从 insights 提取关键发现（Insight 模型有 type, title, description, importance, evidence）
        key_findings = []
        if result.insights:
            for insight in result.insights:
                key_findings.append(KeyFinding(
                    finding=insight.title,  # 使用 title 作为发现内容
                    importance="high" if insight.importance >= 0.7 else ("medium" if insight.importance >= 0.4 else "low"),
                    category=insight.type  # trend/anomaly/comparison/pattern
                ))
        
        # 构建分析路径
        analysis_path = []
        step_number = 1
        if result.semantic_query:
            analysis_path.append(AnalysisStep(
                step_number=step_number,
                agent_name="语义解析Agent",
                description=f"理解问题: {result.question[:50]}...",
                duration_ms=None
            ))
            step_number += 1
        if result.mapped_query:
            analysis_path.append(AnalysisStep(
                step_number=step_number,
                agent_name="字段映射Agent",
                description="将业务术语映射到数据字段",
                duration_ms=None
            ))
            step_number += 1
        if result.vizql_query:
            analysis_path.append(AnalysisStep(
                step_number=step_number,
                agent_name="查询构建Agent",
                description="构建VizQL查询",
                duration_ms=None
            ))
            step_number += 1
        if result.query_result:
            analysis_path.append(AnalysisStep(
                step_number=step_number,
                agent_name="执行Agent",
                description="执行查询并获取数据",
                duration_ms=None
            ))
            step_number += 1
        if result.insights:
            analysis_path.append(AnalysisStep(
                step_number=step_number,
                agent_name="洞察Agent",
                description=f"分析数据，发现 {len(result.insights)} 个洞察",
                duration_ms=None
            ))
        
        # 生成执行摘要
        executive_summary = ""
        if result.replan_decision and result.replan_decision.reason:
            executive_summary = result.replan_decision.reason
        elif result.insights:
            # 使用最重要的洞察作为摘要
            sorted_insights = sorted(result.insights, key=lambda x: x.importance, reverse=True)
            executive_summary = sorted_insights[0].description if sorted_insights else ""
        
        # 构建推荐问题（从 replan_decision 获取）
        recommendations = []
        if result.replan_decision and result.replan_decision.exploration_questions:
            for i, eq in enumerate(result.replan_decision.exploration_questions):
                recommendations.append(Recommendation(
                    question=eq.question,
                    reason=eq.reasoning,  # ExplorationQuestion 使用 reasoning 字段
                    priority="high" if i == 0 else ("medium" if i < 3 else "low")
                ))
        
        # 构建可视化数据（包含查询结果）
        # ⚠️ State 序列化：query_result 可能是 dict（ExecuteResult.model_dump()）或 Pydantic 对象
        visualizations = []
        query_result = result.query_result
        query_data = None
        query_columns = []
        
        if query_result:
            if isinstance(query_result, dict):
                # dict 访问方式（正确）
                query_data = query_result.get("data")
                query_columns = query_result.get("columns", [])
            elif hasattr(query_result, 'data'):
                # 兼容旧的对象访问方式（向后兼容）
                query_data = query_result.data
                query_columns = getattr(query_result, 'columns', [])
        
        if query_data:
            visualizations.append(Visualization(
                viz_type="table",
                title="查询结果",
                data={"rows": query_data},
                config={"columns": query_columns}
            ))
        
        return ChatResponse(
            executive_summary=executive_summary,
            key_findings=key_findings,
            analysis_path=analysis_path,
            recommendations=recommendations,
            visualizations=visualizations,
            metadata={
                "duration": result.duration,
                "replan_count": result.replan_count,
                "is_analysis_question": result.is_analysis_question,
                "row_count": len(query_data) if query_data else 0,
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
    tableau_domain: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    生成SSE事件流
    
    使用 WorkflowExecutor.stream() 获取工作流事件并转换为 SSE 格式。
    支持 token 级别的流式输出和多环境。
    
    事件类型：
    - node_start: 节点开始执行
    - token: LLM 生成的 token（实时流式）
    - node_complete: 节点执行完成
    - complete: 工作流完成
    - error: 错误
    
    SSE 格式说明：
    - 每个事件以 "data: " 开头
    - 事件之间用两个换行符分隔
    - token 事件会立即发送，不做缓冲
    
    Args:
        question: 用户问题
        session_id: 会话ID
        datasource_luid: 数据源LUID
        tableau_domain: Tableau 域名（多环境支持）
    
    Yields:
        SSE格式的事件字符串
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        executor = WorkflowExecutor(
            datasource_luid=datasource_luid,
            tableau_domain=tableau_domain,
        )
        
        token_count = 0
        
        async for event in executor.stream(question, thread_id=session_id):
            # 转换为前端友好的格式
            if event.type == EventType.TOKEN:
                # Token 事件：精简格式，减少传输开销
                token_count += 1
                sse_data = {
                    "event_type": "token",
                    "data": {"content": event.content, "node": event.node_name},
                    "timestamp": event.timestamp
                }
                yield f"data: {json.dumps(sse_data, ensure_ascii=False)}\n\n"
            else:
                # 其他事件：完整格式
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
                logger.info(f"SSE 流结束: {event.type.value}, 共输出 {token_count} 个 token")
                break
                
    except Exception as e:
        logger.error(f"SSE 生成错误: {e}", exc_info=True)
        error_event = StreamEvent(
            event_type="error",
            data={"message": str(e)},
            timestamp=time.time()
        )
        yield f"data: {error_event.model_dump_json()}\n\n"


@router.post("/chat/stream")
async def chat_query_stream(request: ChatRequest):
    """
    聊天查询API（流式版本）
    
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
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"chat_query_stream 收到请求: question='{request.question[:50] if request.question else 'None'}...'")
        
        session_id = request.session_id or f"session_{int(time.time())}"
        
        # 解析数据源 LUID 和对应的 Tableau 域名
        datasource_luid, tableau_domain = await resolve_datasource_luid(request)
        
        logger.info(f"chat_query_stream 数据源解析成功: luid={datasource_luid}, domain={tableau_domain}")
        
        return StreamingResponse(
            generate_sse_events(
                question=request.question,
                session_id=session_id,
                datasource_luid=datasource_luid,
                tableau_domain=tableau_domain,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    except ValidationError as e:
        logger.error(f"chat_query_stream ValidationError: {e}")
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"chat_query_stream 未知错误: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="InternalError",
                message=f"服务器内部错误: {str(e)}"
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
        from tableau_assistant.src.infra.ai import get_llm
        llm = get_llm()
        checks["llm"] = {"status": "ok", "message": "LLM 连接正常"}
    except Exception as e:
        checks["llm"] = {"status": "error", "message": str(e)}
        logger.warning(f"LLM health check failed: {e}")
    
    # 检查 Tableau API
    try:
        from tableau_assistant.src.infra.config.settings import settings
        tableau_config = settings.get_tableau_config()
        
        if tableau_config.domain:
            checks["tableau"] = {
                "status": "ok", 
                "message": f"Tableau 配置正常: {tableau_config.domain}"
            }
        else:
            checks["tableau"] = {"status": "warning", "message": "Tableau 配置不完整"}
    except Exception as e:
        checks["tableau"] = {"status": "error", "message": str(e)}
        logger.warning(f"Tableau health check failed: {e}")
    
    # 检查存储
    try:
        from tableau_assistant.src.infra.storage import get_langgraph_store
        store = get_langgraph_store()
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



