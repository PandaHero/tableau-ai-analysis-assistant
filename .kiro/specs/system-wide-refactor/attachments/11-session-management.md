# 附件 11：多轮会话管理详细设计

本文档详细说明 Analytics Assistant 的多轮会话管理实现。

## 概述

系统使用 **LangGraph Checkpointer** 和 **SessionManager** 实现多轮会话管理，支持：
- ✅ 自动上下文理解（无需重复指定参数）
- ✅ 状态持久化（跨请求恢复）
- ✅ 对话压缩（节省 token）
- ✅ 灵活存储（SQLite/Redis）

---

## 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────┐
│                    API 层                                │
│  - POST /api/sessions (创建会话)                         │
│  - POST /api/chat (继续会话)                             │
│  - GET /api/sessions/:id (获取会话)                      │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              SessionManager（会话管理器）                 │
│  - 会话元数据管理（session_id, user_id, workspace_id）   │
│  - 会话创建、查询、更新、清理                             │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│         LangGraph Checkpointer（状态持久化）              │
│  - SqliteSaver（开发环境）                                │
│  - RedisSaver（生产环境，可选）                           │
│  - 自动保存工作流状态                                     │
│  - 自动管理对话历史                                       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│      SummarizationMiddleware（对话压缩）                  │
│  - 自动压缩长对话（超过 60K tokens）                      │
│  - 保留最近 10 条消息                                     │
└─────────────────────────────────────────────────────────┘
```

---

## SessionManager 实现

### 数据模型

```python
# infra/storage/managers/session_manager.py
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, Optional

class Session(BaseModel):
    """会话模型"""
    session_id: str
    user_id: str
    workspace_id: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    metadata: Dict = {}
    is_active: bool = True
```

### SessionManager 类

```python
class SessionManager:
    """会话管理器 - 管理多轮对话的会话状态"""
    
    def __init__(self, store: BaseStore):
        self.store = store
        self.namespace = "sessions"
    
    async def create_session(
        self, 
        user_id: str, 
        workspace_id: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """创建新会话
        
        Args:
            user_id: 用户 ID
            workspace_id: 工作空间 ID
            metadata: 可选的元数据
            
        Returns:
            session_id: 新创建的会话 ID
        """
        session_id = self._generate_session_id()
        session = Session(
            session_id=session_id,
            user_id=user_id,
            workspace_id=workspace_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            message_count=0,
            metadata=metadata or {},
            is_active=True
        )
        
        await self.store.put(
            f"{self.namespace}/{session_id}", 
            session.dict()
        )
        
        return session_id
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话信息
        
        Args:
            session_id: 会话 ID
            
        Returns:
            Session 对象，如果不存在返回 None
        """
        data = await self.store.get(f"{self.namespace}/{session_id}")
        if data is None:
            return None
        return Session(**data)
    
    async def update_session(
        self, 
        session_id: str, 
        updates: Dict
    ):
        """更新会话信息
        
        Args:
            session_id: 会话 ID
            updates: 要更新的字段
        """
        session = await self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        
        # 更新字段
        for key, value in updates.items():
            if hasattr(session, key):
                setattr(session, key, value)
        
        # 更新时间戳
        session.updated_at = datetime.now()
        
        await self.store.put(
            f"{self.namespace}/{session_id}", 
            session.dict()
        )
    
    async def increment_message_count(self, session_id: str):
        """增加消息计数
        
        Args:
            session_id: 会话 ID
        """
        session = await self.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        
        await self.update_session(session_id, {
            "message_count": session.message_count + 1
        })
    
    async def deactivate_session(self, session_id: str):
        """停用会话
        
        Args:
            session_id: 会话 ID
        """
        await self.update_session(session_id, {"is_active": False})
    
    async def cleanup_expired_sessions(self, days: int = 7):
        """清理过期会话
        
        Args:
            days: 过期天数（默认 7 天）
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # 获取所有会话
        all_keys = await self.store.list_keys(self.namespace)
        
        for key in all_keys:
            session_data = await self.store.get(key)
            if session_data is None:
                continue
            
            session = Session(**session_data)
            
            # 如果会话超过 7 天未活跃，且未标记为保留
            if (session.updated_at < cutoff_date and 
                session.is_active and 
                not session.metadata.get("keep", False)):
                await self.deactivate_session(session.session_id)
    
    def _generate_session_id(self) -> str:
        """生成唯一的会话 ID"""
        import uuid
        return f"session_{uuid.uuid4().hex[:16]}"
```

---

## LangGraph Checkpointer 集成

### 配置 Checkpointer

```python
# orchestration/workflow/factory.py
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.redis import RedisSaver
from infra.config.settings import get_settings

def create_checkpointer():
    """创建 Checkpointer（根据配置选择后端）"""
    settings = get_settings()
    
    if settings.checkpoint_backend == "redis":
        # 生产环境：使用 Redis
        return RedisSaver.from_conn_string(settings.redis_url)
    else:
        # 开发环境：使用 SQLite（默认）
        return SqliteSaver.from_conn_string("checkpoints.db")

def create_workflow_with_checkpointer():
    """创建带检查点的工作流"""
    # 创建 Checkpointer
    checkpointer = create_checkpointer()
    
    # 创建工作流
    workflow = create_workflow()
    
    # 编译时传入 checkpointer
    app = workflow.compile(checkpointer=checkpointer)
    
    return app
```

### 配置文件

```python
# .env
CHECKPOINT_BACKEND=sqlite  # 或 redis
REDIS_URL=redis://localhost:6379/0
```

---

## API 层实现

### 创建会话

```python
# api/chat.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class CreateSessionRequest(BaseModel):
    user_id: str
    workspace_id: str
    metadata: Optional[Dict] = None

class CreateSessionResponse(BaseModel):
    session_id: str
    created_at: datetime

@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """创建新会话"""
    session_manager = get_session_manager()
    
    session_id = await session_manager.create_session(
        user_id=request.user_id,
        workspace_id=request.workspace_id,
        metadata=request.metadata
    )
    
    session = await session_manager.get_session(session_id)
    
    return CreateSessionResponse(
        session_id=session_id,
        created_at=session.created_at
    )
```

### 继续会话

```python
class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    session_id: str
    message: str
    insights: List[str]
    metadata: Dict

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """继续现有会话"""
    session_manager = get_session_manager()
    
    # 1. 验证会话存在
    session = await session_manager.get_session(request.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not session.is_active:
        raise HTTPException(status_code=400, detail="Session is inactive")
    
    # 2. 使用 session_id 作为 thread_id 恢复状态
    config = {
        "configurable": {
            "thread_id": request.session_id,
            "checkpoint_ns": session.workspace_id
        }
    }
    
    # 3. 调用工作流（自动加载历史状态）
    app = get_workflow_app()
    result = await app.ainvoke(
        {"messages": [HumanMessage(content=request.message)]},
        config=config
    )
    
    # 4. 更新会话统计
    await session_manager.increment_message_count(request.session_id)
    
    # 5. 返回结果
    return ChatResponse(
        session_id=request.session_id,
        message=result["messages"][-1].content,
        insights=result.get("insights", []),
        metadata=result.get("metadata", {})
    )
```

### 获取会话

```python
@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """获取会话信息"""
    session_manager = get_session_manager()
    
    session = await session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return session
```

---

## 对话压缩（SummarizationMiddleware）

### 配置

```python
# orchestration/workflow/factory.py
from langchain.agents.middleware import SummarizationMiddleware

def create_middleware_stack():
    middleware = []
    
    # ... 其他中间件
    
    # 对话摘要（长对话压缩）
    middleware.append(SummarizationMiddleware(
        model=get_model_manager().create_llm(),
        trigger=("tokens", 60000),  # 60K tokens 触发摘要
        keep=("messages", 10),      # 保留最近 10 条消息
    ))
    
    return middleware
```

### 工作原理

1. **触发条件**：对话历史超过 60K tokens
2. **摘要生成**：使用 LLM 生成对话摘要
3. **历史替换**：用摘要替换旧消息，保留最近 10 条
4. **Token 节省**：减少 70-80% 的 token 消耗

---

## 多轮对话示例

### 示例 1：销售分析

**第一轮**：
```json
POST /api/sessions
{
    "user_id": "user123",
    "workspace_id": "workspace456"
}
→ 返回 session_id: "session_abc123"

POST /api/chat
{
    "session_id": "session_abc123",
    "message": "过去7天的销售额趋势"
}
→ 返回趋势图和分析
```

**第二轮**（基于上下文）：
```json
POST /api/chat
{
    "session_id": "session_abc123",
    "message": "按区域分组"
}
→ 系统理解上下文：销售额 + 过去7天 + 按区域分组
→ 返回各区域的销售额趋势
```

**第三轮**（继续细化）：
```json
POST /api/chat
{
    "session_id": "session_abc123",
    "message": "只看华东区"
}
→ 系统理解上下文：销售额 + 过去7天 + 华东区
→ 返回华东区的销售额趋势
```

### 示例 2：跨会话恢复

**会话 1**（今天）：
```json
POST /api/chat
{
    "session_id": "session_abc123",
    "message": "过去30天的销售额趋势"
}
→ 返回趋势图
```

**会话 2**（明天，恢复）：
```json
POST /api/chat
{
    "session_id": "session_abc123",
    "message": "和去年同期对比"
}
→ 系统自动加载昨天的上下文
→ 理解：销售额 + 过去30天 + 同比去年
→ 返回同比分析
```

---

## 会话生命周期

```
创建会话
  ↓
[is_active = True]
  ↓
多轮对话（自动保存状态）
  ↓
[超过 7 天未活跃]
  ↓
自动停用（is_active = False）
  ↓
[可选：手动删除]
```

**清理策略**：
- 自动清理：超过 7 天未活跃的会话
- 手动清理：用户主动结束会话
- 保留策略：重要会话可标记为 `metadata.keep = True`

---

## 性能优化

### 1. 缓存策略

**会话元数据缓存**：
- 使用 Redis 缓存热会话（最近 1 小时活跃）
- TTL: 1 小时
- 减少数据库查询

**Checkpointer 缓存**：
- LangGraph 自动缓存工作流状态
- 无需额外配置

### 2. 对话压缩

**触发条件**：
- 对话历史超过 60K tokens
- 自动触发 SummarizationMiddleware

**压缩效果**：
- 减少 70-80% 的 token 消耗
- 保留最近 10 条消息的完整内容
- 旧消息用摘要替代

### 3. 并发控制

**会话锁**：
- 同一会话同时只能有一个请求
- 使用分布式锁（Redis）
- 避免状态冲突

---

## 监控和告警

### 关键指标

| 指标 | 说明 | 告警阈值 |
|------|------|---------|
| 活跃会话数 | 当前活跃的会话数量 | > 10000 |
| 平均会话时长 | 会话从创建到停用的平均时长 | > 7 天 |
| 平均消息数 | 每个会话的平均消息数 | > 100 |
| 对话压缩率 | 触发对话压缩的会话比例 | > 20% |
| 会话恢复延迟 | 恢复会话状态的平均延迟 | > 500ms |

### 日志记录

```python
# 会话创建
logger.info(
    "Session created",
    session_id=session_id,
    user_id=user_id,
    workspace_id=workspace_id
)

# 会话恢复
logger.info(
    "Session resumed",
    session_id=session_id,
    message_count=session.message_count,
    last_active=session.updated_at
)

# 对话压缩
logger.info(
    "Conversation summarized",
    session_id=session_id,
    original_tokens=original_tokens,
    compressed_tokens=compressed_tokens,
    compression_ratio=compression_ratio
)
```

---

## 测试策略

### 单元测试

```python
# tests/infra/storage/test_session_manager.py
import pytest
from infra.storage.managers.session_manager import SessionManager

@pytest.mark.asyncio
async def test_create_session():
    """测试创建会话"""
    manager = SessionManager(store=get_test_store())
    
    session_id = await manager.create_session(
        user_id="user123",
        workspace_id="workspace456"
    )
    
    assert session_id.startswith("session_")
    
    session = await manager.get_session(session_id)
    assert session.user_id == "user123"
    assert session.workspace_id == "workspace456"
    assert session.is_active is True

@pytest.mark.asyncio
async def test_increment_message_count():
    """测试增加消息计数"""
    manager = SessionManager(store=get_test_store())
    
    session_id = await manager.create_session("user123", "workspace456")
    
    await manager.increment_message_count(session_id)
    await manager.increment_message_count(session_id)
    
    session = await manager.get_session(session_id)
    assert session.message_count == 2

@pytest.mark.asyncio
async def test_cleanup_expired_sessions():
    """测试清理过期会话"""
    manager = SessionManager(store=get_test_store())
    
    # 创建旧会话（8 天前）
    session_id = await manager.create_session("user123", "workspace456")
    await manager.update_session(session_id, {
        "updated_at": datetime.now() - timedelta(days=8)
    })
    
    # 清理过期会话
    await manager.cleanup_expired_sessions(days=7)
    
    # 验证会话已停用
    session = await manager.get_session(session_id)
    assert session.is_active is False
```

### 集成测试

```python
# tests/integration/test_multi_turn_conversation.py
import pytest
from api.chat import create_session, chat

@pytest.mark.asyncio
async def test_multi_turn_conversation():
    """测试多轮对话"""
    # 创建会话
    response = await create_session(CreateSessionRequest(
        user_id="user123",
        workspace_id="workspace456"
    ))
    session_id = response.session_id
    
    # 第一轮
    response1 = await chat(ChatRequest(
        session_id=session_id,
        message="过去7天的销售额趋势"
    ))
    assert "销售额" in response1.message
    
    # 第二轮（基于上下文）
    response2 = await chat(ChatRequest(
        session_id=session_id,
        message="按区域分组"
    ))
    assert "区域" in response2.message
    # 验证系统理解了上下文（销售额 + 过去7天）
    
    # 第三轮（继续细化）
    response3 = await chat(ChatRequest(
        session_id=session_id,
        message="只看华东区"
    ))
    assert "华东" in response3.message
```

---

## 总结

本文档详细说明了多轮会话管理的实现：

✅ **SessionManager**：管理会话元数据和生命周期  
✅ **LangGraph Checkpointer**：自动保存和恢复工作流状态  
✅ **SummarizationMiddleware**：自动压缩长对话，节省 token  
✅ **API 层**：提供会话创建、继续、查询接口  
✅ **性能优化**：缓存、压缩、并发控制  
✅ **监控告警**：关键指标和日志记录  
✅ **测试策略**：单元测试和集成测试  

通过这套方案，系统能够支持流畅的多轮对话，自动理解上下文，提升用户体验。
