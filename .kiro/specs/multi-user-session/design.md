# Design Document: Multi-User Session Management

## Overview

本设计实现多用户会话管理系统，确保不同用户的问题和输出完全隔离。系统采用 JWT 认证、SQLite 持久化和会话级锁机制，支持跨设备访问和并发请求处理。

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Frontend                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │ authStore   │  │ sessionStore│  │ chatStore   │                 │
│  │ - token     │  │ - sessions  │  │ - messages  │                 │
│  │ - user_id   │  │ - current   │  │ - streaming │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/SSE (JWT in Header)
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           Backend API                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │ AuthRouter  │  │ SessionAPI  │  │ ChatAPI     │                 │
│  │ /api/auth/* │  │ /api/sess/* │  │ /api/chat/* │                 │
│  └─────────────┘  └─────────────┘  └─────────────┘                 │
│         │                │                │                         │
│         ▼                ▼                ▼                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    AuthMiddleware                            │   │
│  │  - JWT 验证                                                  │   │
│  │  - 匿名用户处理                                              │   │
│  │  - user_id 注入到 request.state                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│         │                │                │                         │
│         ▼                ▼                ▼                         │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   SessionManager                             │   │
│  │  - 会话 CRUD                                                 │   │
│  │  - 会话级锁 (asyncio.Lock per session)                      │   │
│  │  - 所有权验证                                                │   │
│  └─────────────────────────────────────────────────────────────┘   │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                   SQLite Storage                             │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐    │   │
│  │  │ users         │  │ sessions      │  │ checkpoints   │    │   │
│  │  │ - id          │  │ - id          │  │ - thread_id   │    │   │
│  │  │ - username    │  │ - user_id     │  │ - checkpoint  │    │   │
│  │  │ - password_h  │  │ - created_at  │  │ - metadata    │    │   │
│  │  │ - created_at  │  │ - archived    │  │ - created_at  │    │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘    │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. AuthMiddleware

FastAPI 中间件，处理所有请求的认证。

```python
class AuthMiddleware:
    """
    认证中间件
    
    处理流程：
    1. 检查 Authorization header
    2. 有 token -> 验证 JWT -> 提取 user_id
    3. 无 token -> 生成匿名 user_id (anon_xxx)
    4. 将 user_id 注入 request.state
    """
    
    async def __call__(self, request: Request, call_next):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        
        if token:
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
                request.state.user_id = payload["user_id"]
                request.state.is_anonymous = False
            except jwt.ExpiredSignatureError:
                raise HTTPException(401, "Token expired")
            except jwt.InvalidTokenError:
                raise HTTPException(401, "Invalid token")
        else:
            # 匿名模式：从 cookie 或生成新 ID
            anon_id = request.cookies.get("anon_id") or f"anon_{uuid4().hex[:12]}"
            request.state.user_id = anon_id
            request.state.is_anonymous = True
        
        response = await call_next(request)
        
        # 设置匿名 ID cookie
        if request.state.is_anonymous:
            response.set_cookie("anon_id", request.state.user_id, max_age=86400*30)
        
        return response
```

### 2. SessionManager

会话管理核心类，处理会话的创建、查询、删除和锁定。

```python
class SessionManager:
    """
    会话管理器
    
    职责：
    - 会话 CRUD 操作
    - 会话所有权验证
    - 会话级锁管理
    - 与 LangGraph Checkpointer 集成
    """
    
    def __init__(self, db_path: str = "data/sessions.db"):
        self._db_path = db_path
        self._locks: Dict[str, asyncio.Lock] = {}  # session_id -> Lock
        self._checkpointer = SqliteSaver.from_conn_string(db_path)
    
    def _get_thread_id(self, user_id: str, session_id: str) -> str:
        """生成复合 thread_id"""
        return f"{user_id}:{session_id}"
    
    async def create_session(self, user_id: str, title: str = "") -> Session:
        """创建新会话"""
        session_id = str(uuid4())
        thread_id = self._get_thread_id(user_id, session_id)
        # 存储到数据库...
        return Session(id=session_id, user_id=user_id, thread_id=thread_id)
    
    async def get_session(self, user_id: str, session_id: str) -> Optional[Session]:
        """获取会话（验证所有权）"""
        session = await self._fetch_session(session_id)
        if session and session.user_id != user_id:
            raise PermissionError("Access denied")
        return session
    
    async def list_sessions(self, user_id: str) -> List[Session]:
        """列出用户的所有会话"""
        return await self._fetch_sessions_by_user(user_id)
    
    async def acquire_lock(self, session_id: str, timeout: float = 30.0) -> bool:
        """获取会话锁"""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        
        try:
            await asyncio.wait_for(
                self._locks[session_id].acquire(),
                timeout=timeout
            )
            return True
        except asyncio.TimeoutError:
            return False
    
    def release_lock(self, session_id: str):
        """释放会话锁"""
        if session_id in self._locks and self._locks[session_id].locked():
            self._locks[session_id].release()
```

### 3. Session API Router

```python
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

@router.get("")
async def list_sessions(request: Request) -> List[SessionSummary]:
    """列出当前用户的所有会话"""
    user_id = request.state.user_id
    return await session_manager.list_sessions(user_id)

@router.post("")
async def create_session(request: Request, body: CreateSessionRequest) -> Session:
    """创建新会话"""
    user_id = request.state.user_id
    return await session_manager.create_session(user_id, body.title)

@router.get("/{session_id}")
async def get_session(request: Request, session_id: str) -> SessionDetail:
    """获取会话详情"""
    user_id = request.state.user_id
    return await session_manager.get_session(user_id, session_id)

@router.delete("/{session_id}")
async def delete_session(request: Request, session_id: str):
    """删除会话"""
    user_id = request.state.user_id
    await session_manager.delete_session(user_id, session_id)
    return {"status": "deleted"}

@router.put("/{session_id}/archive")
async def archive_session(request: Request, session_id: str):
    """归档会话"""
    user_id = request.state.user_id
    await session_manager.archive_session(user_id, session_id)
    return {"status": "archived"}
```

### 4. Enhanced Chat API

```python
@router.post("/chat/stream")
async def chat_query_stream(request: Request, body: ChatRequest):
    """流式聊天（带会话锁）"""
    user_id = request.state.user_id
    session_id = body.session_id or await session_manager.create_session(user_id)
    
    # 获取会话锁
    if not await session_manager.acquire_lock(session_id, timeout=5.0):
        raise HTTPException(409, "Session is busy, please wait")
    
    try:
        thread_id = session_manager._get_thread_id(user_id, session_id)
        
        return StreamingResponse(
            generate_sse_events(
                question=body.question,
                thread_id=thread_id,  # 使用复合 thread_id
                datasource_luid=datasource_luid,
            ),
            media_type="text/event-stream",
        )
    finally:
        session_manager.release_lock(session_id)
```

### 5. Frontend Auth Store

```typescript
// stores/auth.ts
export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('auth_token'))
  const user = ref<User | null>(null)
  const isAuthenticated = computed(() => !!token.value && !isAnonymous.value)
  const isAnonymous = computed(() => user.value?.id?.startsWith('anon_') ?? true)

  async function login(username: string, password: string) {
    const response = await api.post('/api/auth/login', { username, password })
    token.value = response.data.token
    user.value = response.data.user
    localStorage.setItem('auth_token', token.value)
  }

  async function logout() {
    await api.post('/api/auth/logout')
    token.value = null
    user.value = null
    localStorage.removeItem('auth_token')
  }

  function getAuthHeader(): Record<string, string> {
    return token.value ? { Authorization: `Bearer ${token.value}` } : {}
  }

  return { token, user, isAuthenticated, isAnonymous, login, logout, getAuthHeader }
})
```

## Data Models

### Database Schema

```sql
-- 用户表
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE,
    password_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

-- 会话表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived BOOLEAN DEFAULT FALSE,
    archived_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 会话消息表（可选，用于快速查询）
CREATE TABLE session_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user' | 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

-- 索引
CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_archived ON sessions(archived);
CREATE INDEX idx_session_messages_session_id ON session_messages(session_id);
```

### Pydantic Models

```python
class User(BaseModel):
    id: str
    username: Optional[str] = None
    is_anonymous: bool = False
    created_at: datetime

class Session(BaseModel):
    id: str
    user_id: str
    thread_id: str  # 复合 ID: user_id:session_id
    title: str = ""
    created_at: datetime
    updated_at: datetime
    archived: bool = False
    message_count: int = 0

class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    archived: bool
    message_count: int
    last_message_preview: Optional[str] = None

class SessionDetail(Session):
    messages: List[Message] = []
    checkpoints: List[CheckpointMeta] = []
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: JWT Token Round-Trip

*For any* valid user credentials, authenticating and then decoding the returned JWT token should produce the same user_id.

**Validates: Requirements 1.1**

### Property 2: Session Isolation

*For any* two distinct users A and B, and any session S owned by user A, user B should not be able to access, modify, or delete session S.

**Validates: Requirements 2.2, 2.3, 2.4**

### Property 3: Checkpoint State Round-Trip

*For any* valid workflow state containing Pydantic models, serializing to SQLite and deserializing should produce an equivalent state.

**Validates: Requirements 3.5, 3.6**

### Property 4: Session CRUD Consistency

*For any* session created by a user, the session should appear in the user's session list, be retrievable by ID, and be deletable.

**Validates: Requirements 4.1, 4.2, 4.3, 4.4**

### Property 5: Concurrent Request Handling

*For any* session with an active request, subsequent requests to the same session should receive 409 Conflict until the first request completes.

**Validates: Requirements 6.1, 6.2**

### Property 6: Session Cleanup by Age

*For any* session older than 30 days, the system should mark it as archived. *For any* archived session older than 90 days, the system should delete it.

**Validates: Requirements 7.1, 7.2**

## Error Handling

| Error | HTTP Code | Response |
|-------|-----------|----------|
| Invalid credentials | 401 | `{"error": "InvalidCredentials", "message": "用户名或密码错误"}` |
| Token expired | 401 | `{"error": "TokenExpired", "message": "登录已过期，请重新登录"}` |
| Session not found | 404 | `{"error": "SessionNotFound", "message": "会话不存在"}` |
| Access denied | 403 | `{"error": "AccessDenied", "message": "无权访问此会话"}` |
| Session busy | 409 | `{"error": "SessionBusy", "message": "会话正在处理中，请稍后重试"}` |
| Lock timeout | 408 | `{"error": "LockTimeout", "message": "获取会话锁超时"}` |

## Testing Strategy

### Unit Tests

- JWT token generation and validation
- Session CRUD operations
- Lock acquisition and release
- Database schema migrations

### Property-Based Tests

使用 Hypothesis (Python) 进行属性测试：

1. **JWT Round-Trip**: 生成随机用户数据，验证 encode/decode 一致性
2. **Session Isolation**: 生成随机用户和会话，验证跨用户访问被拒绝
3. **State Round-Trip**: 生成随机工作流状态，验证序列化/反序列化一致性
4. **Concurrent Requests**: 模拟并发请求，验证锁机制正确性

### Integration Tests

- 完整认证流程（注册 → 登录 → 操作 → 登出）
- 会话生命周期（创建 → 使用 → 归档 → 删除）
- 跨设备会话同步
- 服务器重启后会话恢复

