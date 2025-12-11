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
    QuestionBoostRequest,
    QuestionBoostResponse,
    MetadataInitRequest,
    MetadataInitResponse,
    ErrorResponse,
    StreamEvent
)
from tableau_assistant.src.workflow.executor import WorkflowExecutor, EventType

router = APIRouter(prefix="/api", tags=["chat"])


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
        # TODO: 迁移到新的 workflow 模块
        # from tableau_assistant.src.workflow.factory import create_tableau_workflow
        raise HTTPException(
            status_code=501,
            detail=ErrorResponse(
                error="NotImplemented",
                message="同步查询功能正在迁移中，请使用流式查询 /api/chat/stream"
            ).model_dump()
        )
        
        # 将API请求转换为工作流输入（已验证，无需重复验证）
        workflow_input = {"question": request.question, "boost_question": request.boost_question}
        
        # 执行工作流
        result = run_vizql_workflow_sync(
            input_data=workflow_input,
            datasource_luid=request.datasource_luid,
            user_id=request.user_id or "default_user",
            session_id=request.session_id or f"session_{int(time.time())}"
        )
        
        # 转换为API响应格式
        return VizQLQueryResponse(
            executive_summary=result.get("executive_summary", ""),
            key_findings=result.get("key_findings", []),
            analysis_path=result.get("analysis_path", []),
            recommendations=result.get("recommendations", []),
            visualizations=result.get("visualizations", []),
            metadata=result.get("metadata", {})
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
    session_id: str
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
    
    Yields:
        SSE格式的事件字符串
    """
    try:
        executor = WorkflowExecutor()
        
        async for event in executor.stream(question, thread_id=session_id):
            # 转换为前端友好的格式
            sse_event = StreamEvent(
                event_type=event.type.value,
                data={
                    "node": event.node_name,
                    "content": event.content,
                    "data": event.data,
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
        
        return StreamingResponse(
            generate_sse_events(
                question=request.question,
                session_id=session_id
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


@router.post(
    "/boost-question",
    response_model=QuestionBoostResponse,
    responses={
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    }
)
async def boost_question(request: QuestionBoostRequest) -> QuestionBoostResponse:
    """
    问题Boost API
    
    优化用户问题，提供相关建议
    
    Args:
        request: 问题Boost请求
    
    Returns:
        问题Boost响应
    
    Raises:
        HTTPException: 如果优化失败
    """
    try:
        # TODO: 实现问题Boost Agent
        # from tableau_assistant.src.agents.question_boost import boost_question_agent
        # result = boost_question_agent(
        #     question=request.question,
        #     datasource_luid=request.datasource_luid,
        #     user_id=request.user_id
        # )
        
        # 临时返回示例响应
        return QuestionBoostResponse(
            boosted_question=f"{request.question}（优化后）",
            suggestions=[
                "相关问题建议1",
                "相关问题建议2",
                "相关问题建议3"
            ],
            reasoning="问题优化理由",
            changes=["改动1", "改动2"]
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
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="InternalError",
                message=f"问题优化失败: {str(e)}"
            ).model_dump()
        )


@router.post(
    "/metadata/init-hierarchy",
    response_model=MetadataInitResponse,
    responses={
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"}
    }
)
async def init_metadata_hierarchy(request: MetadataInitRequest) -> MetadataInitResponse:
    """
    元数据初始化API
    
    后台异步初始化数据源的维度层级
    
    Args:
        request: 元数据初始化请求
    
    Returns:
        元数据初始化响应
    
    Raises:
        HTTPException: 如果初始化失败
    """
    try:
        # TODO: 实现后台任务
        # from tableau_assistant.src.capabilities.metadata.manager import ensure_dimension_hierarchy
        # background_tasks.add_task(
        #     ensure_dimension_hierarchy,
        #     datasource_luid=request.datasource_luid,
        #     force_refresh=request.force_refresh
        # )
        
        # 临时返回示例响应
        return MetadataInitResponse(
            status="initializing",
            datasource_luid=request.datasource_luid,
            message="后台正在初始化维度层级，预计3-5秒完成",
            cached=False,
            duration_ms=None
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
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error="InternalError",
                message=f"元数据初始化失败: {str(e)}"
            ).model_dump()
        )


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "timestamp": time.time()}


# 示例：如何在前端使用API
"""
// 同步查询示例
const response = await fetch('/api/chat', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        question: '2016年各地区的销售额',
        datasource_luid: 'abc123',
        user_id: 'user_456',
        boost_question: false
    })
});

const result = await response.json();
console.log('执行摘要:', result.executive_summary);
console.log('关键发现:', result.key_findings);

// 流式查询示例
const eventSource = new EventSource('/api/chat/stream', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        question: '2016年各地区的销售额',
        datasource_luid: 'abc123',
        user_id: 'user_456'
    })
});

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch (data.event_type) {
        case 'token':
            appendToken(data.data.content);
            break;
        case 'agent_start':
            showAgentProgress(data.data.agent, 'running');
            break;
        case 'done':
            eventSource.close();
            break;
    }
};
"""
