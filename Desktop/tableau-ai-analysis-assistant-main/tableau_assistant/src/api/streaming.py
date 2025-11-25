"""
流式API端点

提供SSE(Server-Sent Events)接口用于实时进度反馈
"""
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from typing import Dict, Any
import json

from tableau_assistant.tests.test_workflow import create_test_workflow
from tableau_assistant.src.workflows.streaming import stream_workflow_events

router = APIRouter(prefix="/api/stream", tags=["streaming"])

# 用于测试的工作流创建函数（可以被测试覆盖）
_workflow_factory = create_test_workflow


@router.post("/chat")
async def stream_chat(request: Request):
    """
    流式对话API
    
    使用SSE推送实时进度
    
    Request Body:
        {
            "question": str,  # 用户问题
            "datasource_luid": str,  # 数据源LUID
            "user_id": str,  # 用户ID
            "session_id": str,  # 会话ID
            "boost_question": bool  # 是否使用问题Boost（可选）
        }
    
    Response:
        SSE流，事件格式:
        {
            "type": str,  # 事件类型
            "data": dict,  # 事件数据
            "timestamp": float  # 时间戳
        }
    """
    # 解析请求
    body = await request.json()
    
    question = body.get("question")
    datasource_luid = body.get("datasource_luid")
    user_id = body.get("user_id")
    session_id = body.get("session_id", user_id)
    boost_question = body.get("boost_question", False)
    
    # 验证必需参数
    if not question:
        return {"error": "question is required"}
    if not datasource_luid:
        return {"error": "datasource_luid is required"}
    if not user_id:
        return {"error": "user_id is required"}
    
    # 创建工作流
    app = _workflow_factory()
    
    # 准备输入
    input_data = {
        "question": question,
        "boost_question": boost_question
    }
    
    # 准备config
    config = {
        "configurable": {
            "thread_id": session_id,
            "datasource_luid": datasource_luid,
            "user_id": user_id,
            "session_id": session_id,
            "max_replan_rounds": 2,
            "parallel_upper_limit": 3,
            "max_retry_times": 2,
            "max_subtasks_per_round": 10
        }
    }
    
    # 返回SSE流
    return StreamingResponse(
        stream_workflow_events(app, input_data, config),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用nginx缓冲
        }
    )


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


# 示例：如何在前端使用SSE
"""
// JavaScript示例
const eventSource = new EventSource('/api/stream/chat', {
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
    console.log('Event:', data.type, data.data);
    
    switch (data.type) {
        case 'token':
            // Token级流式渲染
            appendToken(data.data.token);
            break;
        case 'agent_start':
            // 显示Agent开始执行
            showAgentProgress(data.data.agent, 'running');
            break;
        case 'agent_complete':
            // 显示Agent完成
            showAgentProgress(data.data.agent, 'complete');
            break;
        case 'workflow_complete':
            // 工作流完成
            eventSource.close();
            break;
    }
};

eventSource.onerror = (error) => {
    console.error('SSE Error:', error);
    eventSource.close();
};
"""
