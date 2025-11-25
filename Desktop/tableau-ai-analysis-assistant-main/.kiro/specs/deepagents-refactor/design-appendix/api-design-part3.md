# API设计详细文档 - Part 3

## 4. 错误处理

### 4.1 错误响应格式

```python
class ErrorResponse(BaseModel):
    """错误响应"""
    error: str = Field(description="错误类型")
    message: str = Field(description="错误消息")
    details: Optional[Dict] = Field(default=None, description="错误详情")
    request_id: str = Field(description="请求ID（用于追踪）")

# 示例
{
    "error": "ValidationError",
    "message": "Invalid datasource_luid format",
    "details": {
        "field": "datasource_luid",
        "expected": "UUID format",
        "received": "invalid-luid"
    },
    "request_id": "req_abc123"
}
```

### 4.2 HTTP状态码

| 状态码 | 含义 | 使用场景 |
|--------|------|---------|
| 200 | OK | 请求成功 |
| 400 | Bad Request | 请求参数错误 |
| 401 | Unauthorized | 未认证 |
| 403 | Forbidden | 无权限访问 |
| 404 | Not Found | 资源不存在 |
| 429 | Too Many Requests | 请求过于频繁 |
| 500 | Internal Server Error | 服务器内部错误 |
| 503 | Service Unavailable | 服务不可用 |

### 4.3 错误处理中间件

```python
from fastapi import Request, status
from fastapi.responses import JSONResponse
import uuid
import traceback

@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    """错误处理中间件"""
    
    # 生成请求ID
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    try:
        response = await call_next(request)
        return response
    
    except ValueError as e:
        # 验证错误
        logger.error(f"Validation error: {e}", extra={"request_id": request_id})
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "ValidationError",
                "message": str(e),
                "request_id": request_id
            }
        )
    
    except PermissionError as e:
        # 权限错误
        logger.error(f"Permission error: {e}", extra={"request_id": request_id})
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "PermissionError",
                "message": str(e),
                "request_id": request_id
            }
        )
    
    except Exception as e:
        # 未知错误
        logger.error(
            f"Internal error: {e}",
            extra={"request_id": request_id},
            exc_info=True
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "InternalServerError",
                "message": "An unexpected error occurred",
                "request_id": request_id
            }
        )

# 自定义异常处理器
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP异常处理器"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.detail,
            "request_id": getattr(request.state, "request_id", "unknown")
        }
    )
```

---

## 5. 认证和授权

### 5.1 认证方式

使用JWT（JSON Web Token）进行认证。

**Token格式**：

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Token内容**：

```json
{
  "sub": "user_id_123",
  "username": "john.doe",
  "exp": 1735689600,
  "iat": 1735603200,
  "roles": ["analyst", "viewer"]
}
```

### 5.2 认证实现

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from datetime import datetime, timedelta

# JWT配置
SECRET_KEY = "your-secret-key"  # 应从环境变量读取
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

security = HTTPBearer()

class User(BaseModel):
    """用户模型"""
    id: str
    username: str
    roles: List[str]

def create_access_token(data: dict) -> str:
    """创建访问Token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """获取当前用户"""
    
    token = credentials.credentials
    
    try:
        # 解码Token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        roles: List[str] = payload.get("roles", [])
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        
        return User(id=user_id, username=username, roles=roles)
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

# 登录端点
@app.post("/api/v1/auth/login")
async def login(username: str, password: str):
    """登录"""
    
    # 验证用户名和密码（这里简化处理）
    user = await authenticate_user(username, password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # 创建Token
    access_token = create_access_token(
        data={
            "sub": user.id,
            "username": user.username,
            "roles": user.roles
        }
    )
    
    return {"access_token": access_token, "token_type": "bearer"}
```

### 5.3 权限检查

```python
from functools import wraps

def require_role(required_role: str):
    """要求特定角色"""
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = Depends(get_current_user), **kwargs):
            if required_role not in current_user.roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{required_role}' required"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

# 使用示例
@app.post("/api/v1/admin/users")
@require_role("admin")
async def create_user(user_data: Dict, current_user: User = Depends(get_current_user)):
    """创建用户（仅管理员）"""
    pass
```

---

## 6. 限流和配额

### 6.1 限流策略

使用滑动窗口算法限制请求频率。

**限流规则**：
- 普通用户：100请求/小时
- 高级用户：1000请求/小时
- 管理员：无限制

**实现**：

```python
from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# 初始化限流器
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 应用限流
@app.post("/api/v1/chat")
@limiter.limit("100/hour")  # 每小时100次
async def chat(
    request: Request,
    chat_request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """聊天端点（带限流）"""
    pass

# 动态限流（根据用户角色）
def get_rate_limit(user: User) -> str:
    """根据用户角色获取限流规则"""
    if "admin" in user.roles:
        return "10000/hour"  # 管理员
    elif "premium" in user.roles:
        return "1000/hour"  # 高级用户
    else:
        return "100/hour"  # 普通用户

@app.post("/api/v1/chat")
async def chat_with_dynamic_limit(
    request: Request,
    chat_request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """聊天端点（动态限流）"""
    
    # 获取限流规则
    rate_limit = get_rate_limit(current_user)
    
    # 应用限流
    limiter.limit(rate_limit)(lambda: None)()
    
    # 处理请求
    pass
```

### 6.2 配额管理

```python
class QuotaManager:
    """配额管理器"""
    
    def __init__(self, store: InMemoryStore):
        self.store = store
    
    async def check_quota(
        self,
        user_id: str,
        quota_type: str,
        amount: int = 1
    ) -> bool:
        """检查配额"""
        
        # 获取用户配额
        quota_key = f"quota:{user_id}:{quota_type}"
        current_usage = await self.store.aget(("quotas",), quota_key) or 0
        
        # 获取配额限制
        quota_limit = await self._get_quota_limit(user_id, quota_type)
        
        # 检查是否超限
        if current_usage + amount > quota_limit:
            return False
        
        return True
    
    async def consume_quota(
        self,
        user_id: str,
        quota_type: str,
        amount: int = 1
    ):
        """消耗配额"""
        
        quota_key = f"quota:{user_id}:{quota_type}"
        current_usage = await self.store.aget(("quotas",), quota_key) or 0
        
        # 更新使用量
        await self.store.aput(
            ("quotas",),
            quota_key,
            current_usage + amount
        )
    
    async def _get_quota_limit(
        self,
        user_id: str,
        quota_type: str
    ) -> int:
        """获取配额限制"""
        
        # 从数据库或配置获取
        # 这里简化处理
        default_limits = {
            "queries": 1000,  # 每月1000次查询
            "tokens": 1000000  # 每月100万Token
        }
        
        return default_limits.get(quota_type, 0)

# 使用示例
quota_manager = QuotaManager(persistent_store)

@app.post("/api/v1/chat")
async def chat_with_quota(
    request: ChatRequest,
    current_user: User = Depends(get_current_user)
):
    """聊天端点（带配额检查）"""
    
    # 检查配额
    if not await quota_manager.check_quota(current_user.id, "queries"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Monthly query quota exceeded"
        )
    
    # 处理请求
    result = await process_chat(request)
    
    # 消耗配额
    await quota_manager.consume_quota(current_user.id, "queries")
    await quota_manager.consume_quota(
        current_user.id,
        "tokens",
        amount=result["performance_metrics"]["total_tokens"]
    )
    
    return result
```

---

## 7. API文档

### 7.1 OpenAPI/Swagger

FastAPI自动生成OpenAPI文档。

**访问地址**：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

**自定义文档**：

```python
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    """自定义OpenAPI文档"""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="DeepAgent API",
        version="1.0.0",
        description="""
        DeepAgent API提供智能数据分析服务。
        
        ## 功能特性
        - 自然语言查询
        - 流式响应
        - 多轮对话
        - 渐进式洞察
        
        ## 认证
        使用JWT Bearer Token认证。
        """,
        routes=app.routes,
    )
    
    # 添加安全方案
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

---

## 8. 客户端SDK示例

### 8.1 Python客户端

```python
import requests
from typing import Iterator, Dict

class DeepAgentClient:
    """DeepAgent Python客户端"""
    
    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }
    
    def chat(
        self,
        question: str,
        datasource_luid: str,
        boost_question: bool = False,
        thread_id: str = None
    ) -> Dict:
        """同步查询"""
        
        response = requests.post(
            f"{self.base_url}/api/v1/chat",
            headers=self.headers,
            json={
                "question": question,
                "datasource_luid": datasource_luid,
                "boost_question": boost_question,
                "thread_id": thread_id
            }
        )
        
        response.raise_for_status()
        return response.json()
    
    def chat_stream(
        self,
        question: str,
        datasource_luid: str,
        boost_question: bool = False,
        thread_id: str = None
    ) -> Iterator[Dict]:
        """流式查询"""
        
        response = requests.post(
            f"{self.base_url}/api/v1/chat/stream",
            headers=self.headers,
            json={
                "question": question,
                "datasource_luid": datasource_luid,
                "boost_question": boost_question,
                "thread_id": thread_id
            },
            stream=True
        )
        
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    data = json.loads(line_str[6:])
                    yield data

# 使用示例
client = DeepAgentClient(
    base_url="http://localhost:8000",
    api_token="your-token"
)

# 同步查询
result = client.chat(
    question="华东地区的销售趋势如何？",
    datasource_luid="abc123"
)
print(result["executive_summary"])

# 流式查询
for event in client.chat_stream(
    question="华东地区的销售趋势如何？",
    datasource_luid="abc123"
):
    print(event)
```

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15

