# API设计详细文档 - Part 2

## 3. API端点实现

### 3.1 POST /api/v1/chat（同步查询）

**描述**：同步执行查询并返回完整结果。

**请求示例**：

```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "question": "华东地区的销售趋势如何？",
    "datasource_luid": "abc123-def456-ghi789",
    "boost_question": false
  }'
```

**实现**：

```python
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import JSONResponse
import logging

app = FastAPI(title="DeepAgent API", version="1.0.0")
logger = logging.getLogger(__name__)

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
) -> ChatResponse:
    """
    同步查询端点
    
    Args:
        request: 聊天请求
        current_user: 当前用户（从认证中获取）
    
    Returns:
        ChatResponse: 分析结果
    
    Raises:
        HTTPException: 400/500错误
    """
    
    try:
        # 1. 验证数据源访问权限
        if not await has_datasource_access(current_user.id, request.datasource_luid):
            raise HTTPException(
                status_code=403,
                detail="No access to this datasource"
            )
        
        # 2. 创建DeepAgent
        agent = create_deep_agent(
            datasource_luid=request.datasource_luid,
            user_id=current_user.id,
            model_config=request.model_config
        )
        
        # 3. 生成或使用thread_id
        thread_id = request.thread_id or generate_thread_id()
        
        # 4. 执行查询
        logger.info(f"Processing question: {request.question}")
        
        result = await agent.ainvoke(
            {
                "question": request.question,
                "boost_question": request.boost_question
            },
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "datasource_luid": request.datasource_luid,
                    "user_id": current_user.id
                }
            }
        )
        
        # 5. 构建响应
        response = ChatResponse(
            executive_summary=result["final_report"]["executive_summary"],
            key_findings=result["final_report"]["key_findings"],
            insights=result["final_report"]["insights"],
            recommendations=result["final_report"]["recommendations"],
            performance_metrics=result["performance_metrics"],
            thread_id=thread_id
        )
        
        logger.info(f"Successfully processed question in {result['performance_metrics']['total_time']:.2f}s")
        
        return response
    
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"Internal error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
```

---

### 3.2 POST /api/v1/chat/stream（流式查询）

**描述**：流式执行查询，实时返回进度和结果。

**SSE事件类型**：

| 事件类型 | 描述 | 数据格式 |
|---------|------|---------|
| `token` | LLM生成的Token | `{"content": "华东"}` |
| `agent_start` | Agent开始执行 | `{"agent": "understanding-agent"}` |
| `agent_end` | Agent执行完成 | `{"agent": "understanding-agent"}` |
| `tool_start` | 工具开始调用 | `{"tool": "get_metadata"}` |
| `tool_end` | 工具调用完成 | `{"tool": "get_metadata", "result": {...}}` |
| `insight` | 生成洞察 | `{"insight": {...}}` |
| `progress` | 进度更新 | `{"step": "analyzing", "progress": 0.5}` |
| `done` | 完成 | `{"final_result": {...}}` |
| `error` | 错误 | `{"message": "..."}` |

**请求示例**：

```javascript
// JavaScript客户端
const eventSource = new EventSource('/api/v1/chat/stream', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer YOUR_TOKEN'
  },
  body: JSON.stringify({
    question: "华东地区的销售趋势如何？",
    datasource_luid: "abc123-def456-ghi789"
  })
});

eventSource.addEventListener('token', (e) => {
  const data = JSON.parse(e.data);
  console.log('Token:', data.content);
});

eventSource.addEventListener('insight', (e) => {
  const data = JSON.parse(e.data);
  console.log('Insight:', data.insight);
});

eventSource.addEventListener('done', (e) => {
  const data = JSON.parse(e.data);
  console.log('Done:', data.final_result);
  eventSource.close();
});

eventSource.addEventListener('error', (e) => {
  const data = JSON.parse(e.data);
  console.error('Error:', data.message);
  eventSource.close();
});
```

**实现**：

```python
from fastapi.responses import StreamingResponse
import json
import asyncio

@app.post("/api/v1/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """
    流式查询端点
    
    Returns:
        StreamingResponse: SSE事件流
    """
    
    async def event_generator():
        """生成SSE事件"""
        
        try:
            # 1. 验证权限
            if not await has_datasource_access(current_user.id, request.datasource_luid):
                yield format_sse_event("error", {"message": "No access to this datasource"})
                return
            
            # 2. 创建Agent
            agent = create_deep_agent(
                datasource_luid=request.datasource_luid,
                user_id=current_user.id,
                model_config=request.model_config
            )
            
            thread_id = request.thread_id or generate_thread_id()
            
            # 3. 流式执行
            async for event in agent.astream_events(
                {
                    "question": request.question,
                    "boost_question": request.boost_question
                },
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "datasource_luid": request.datasource_luid,
                        "user_id": current_user.id
                    }
                },
                version="v2"
            ):
                # 处理不同类型的事件
                event_type = event["event"]
                
                # Token流
                if event_type == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    if hasattr(chunk, "content") and chunk.content:
                        yield format_sse_event("token", {"content": chunk.content})
                
                # Agent开始
                elif event_type == "on_chain_start":
                    agent_name = event.get("name", "")
                    if "agent" in agent_name.lower():
                        yield format_sse_event("agent_start", {"agent": agent_name})
                
                # Agent结束
                elif event_type == "on_chain_end":
                    agent_name = event.get("name", "")
                    if "agent" in agent_name.lower():
                        yield format_sse_event("agent_end", {"agent": agent_name})
                
                # 工具开始
                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "")
                    yield format_sse_event("tool_start", {"tool": tool_name})
                
                # 工具结束
                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "")
                    result = event["data"].get("output", {})
                    yield format_sse_event("tool_end", {
                        "tool": tool_name,
                        "result": result
                    })
            
            # 4. 发送完成事件
            yield format_sse_event("done", {"thread_id": thread_id})
        
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield format_sse_event("error", {"message": str(e)})
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用Nginx缓冲
        }
    )

def format_sse_event(event_type: str, data: Dict) -> str:
    """格式化SSE事件"""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
```

---

### 3.3 GET /api/v1/health（健康检查）

**描述**：检查服务健康状态。

**实现**：

```python
from pydantic import BaseModel

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    version: str
    dependencies: Dict[str, str]

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """健康检查端点"""
    
    # 检查依赖服务
    dependencies = {}
    
    # 检查数据库
    try:
        await check_database_connection()
        dependencies["database"] = "healthy"
    except Exception:
        dependencies["database"] = "unhealthy"
    
    # 检查LLM服务
    try:
        await check_llm_service()
        dependencies["llm"] = "healthy"
    except Exception:
        dependencies["llm"] = "unhealthy"
    
    # 检查Tableau服务
    try:
        await check_tableau_service()
        dependencies["tableau"] = "healthy"
    except Exception:
        dependencies["tableau"] = "unhealthy"
    
    # 判断整体状态
    all_healthy = all(status == "healthy" for status in dependencies.values())
    status = "healthy" if all_healthy else "degraded"
    
    return HealthResponse(
        status=status,
        version="1.0.0",
        dependencies=dependencies
    )
```

---

### 3.4 GET /api/v1/datasources（获取数据源列表）

**描述**：获取用户有权访问的数据源列表。

**实现**：

```python
class DataSource(BaseModel):
    """数据源"""
    luid: str
    name: str
    description: Optional[str]
    project_name: str
    created_at: str
    updated_at: str

class DataSourceListResponse(BaseModel):
    """数据源列表响应"""
    datasources: List[DataSource]
    total: int

@app.get("/api/v1/datasources", response_model=DataSourceListResponse)
async def list_datasources(
    current_user: User = Depends(get_current_user),
    limit: int = 100,
    offset: int = 0
):
    """获取数据源列表"""
    
    # 从Tableau获取用户有权访问的数据源
    datasources = await get_user_datasources(
        user_id=current_user.id,
        limit=limit,
        offset=offset
    )
    
    return DataSourceListResponse(
        datasources=datasources,
        total=len(datasources)
    )
```

---

### 3.5 GET /api/v1/datasources/{luid}/metadata（获取元数据）

**描述**：获取数据源的元数据。

**实现**：

```python
class FieldMetadata(BaseModel):
    """字段元数据"""
    name: str
    data_type: str
    role: str  # dimension/measure
    description: Optional[str]
    sample_values: List[str]

class DataSourceMetadata(BaseModel):
    """数据源元数据"""
    luid: str
    name: str
    fields: List[FieldMetadata]
    row_count: Optional[int]

@app.get(
    "/api/v1/datasources/{luid}/metadata",
    response_model=DataSourceMetadata
)
async def get_datasource_metadata(
    luid: str,
    current_user: User = Depends(get_current_user)
):
    """获取数据源元数据"""
    
    # 验证权限
    if not await has_datasource_access(current_user.id, luid):
        raise HTTPException(status_code=403, detail="No access to this datasource")
    
    # 获取元数据
    metadata = await fetch_datasource_metadata(luid)
    
    return metadata
```

---

### 3.6 GET /api/v1/threads/{thread_id}/history（获取会话历史）

**描述**：获取会话的历史消息。

**实现**：

```python
class Message(BaseModel):
    """消息"""
    role: str  # user/assistant
    content: str
    timestamp: str

class ThreadHistoryResponse(BaseModel):
    """会话历史响应"""
    thread_id: str
    messages: List[Message]

@app.get(
    "/api/v1/threads/{thread_id}/history",
    response_model=ThreadHistoryResponse
)
async def get_thread_history(
    thread_id: str,
    current_user: User = Depends(get_current_user)
):
    """获取会话历史"""
    
    # 验证thread所有权
    if not await is_thread_owner(thread_id, current_user.id):
        raise HTTPException(status_code=403, detail="No access to this thread")
    
    # 获取历史
    messages = await fetch_thread_messages(thread_id)
    
    return ThreadHistoryResponse(
        thread_id=thread_id,
        messages=messages
    )
```

---

