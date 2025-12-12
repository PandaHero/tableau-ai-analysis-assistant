# 上下文和缓存架构

## 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LangGraph Workflow                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    WorkflowExecutor.run()                            │   │
│  │  1. get_tableau_auth_async() → TableauAuthContext                   │   │
│  │     └── 使用内存缓存（10分钟 TTL）                                   │   │
│  │  2. create_config_with_auth(thread_id, auth_ctx)                    │   │
│  │  3. workflow.ainvoke(state, config)                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    RunnableConfig                                    │   │
│  │  {                                                                   │   │
│  │    "configurable": {                                                 │   │
│  │      "thread_id": "thread_xxx",                                      │   │
│  │      "tableau_auth": {                                               │   │
│  │        "api_key": "xxx",                                             │   │
│  │        "site": "xxx",                                                │   │
│  │        "domain": "xxx",                                              │   │
│  │        "expires_at": 1234567890.0,                                   │   │
│  │        "auth_method": "jwt"                                          │   │
│  │      }                                                               │   │
│  │    }                                                                 │   │
│  │  }                                                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                    ┌───────────────┼───────────────┐                       │
│                    ▼               ▼               ▼                       │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐           │
│  │  Understanding   │ │   FieldMapper    │ │    Execute       │           │
│  │     Node         │ │      Node        │ │     Node         │           │
│  │                  │ │                  │ │                  │           │
│  │ get_metadata()   │ │ StoreManager     │ │ ensure_valid_auth│           │
│  │ ↓                │ │ 字段映射缓存     │ │ _async(config)   │           │
│  │ DataModelManager │ │                  │ │ ↓                │           │
│  │ ↓                │ │                  │ │ TableauAuthContext│           │
│  │ get_tableau_     │ │                  │ │                  │           │
│  │ config()         │ │                  │ │                  │           │
│  │ ↓                │ │                  │ │                  │           │
│  │ get_tableau_auth │ │                  │ │                  │           │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 认证模块位置

认证相关代码统一放在 `bi_platforms/tableau/auth.py`：

```
tableau_assistant/src/bi_platforms/tableau/
├── __init__.py          # 导出所有认证相关类和函数
├── auth.py              # 认证模块（包含 TableauAuthContext）
├── metadata.py          # 元数据服务
└── vizql_client.py      # VizQL 客户端
```

## Token 使用场景

| 组件 | 需要 Token | 获取方式 |
|------|-----------|----------|
| **Execute Node** | ✅ 执行 VizQL 查询 | `ensure_valid_auth_async(config)` |
| **DataModelManager** | ✅ 获取元数据 | `get_tableau_config()` → `get_tableau_auth()` |
| **metadata.py** | ✅ 调用 Tableau API | 参数传入 `api_key` |
| **Understanding Node** | ✅ 通过 get_metadata 工具 | DataModelManager |
| **FieldMapper Node** | ❌ 使用本地缓存 | - |
| **QueryBuilder Node** | ❌ 纯代码转换 | - |

## 缓存策略

### 认证缓存（内存）

```python
# bi_platforms/tableau/auth.py
_CTX_TTL_SEC: int = 600  # 10 分钟
_ctx_cache: Dict[str, Any] = {}
_ctx_cached_at: float = 0.0
```

- 使用模块级变量缓存
- 10 分钟 TTL
- 不缓存失败的认证结果

### 数据缓存（SQLite）

| 缓存类型 | 命名空间 | TTL | 用途 |
|----------|----------|-----|------|
| **元数据** | `metadata` | 1小时 | 数据源字段信息 |
| **维度层级** | `dimension_hierarchy` | 24小时 | 维度层级结构 |
| **数据模型** | `data_model` | 24小时 | 表关系 |
| **字段映射** | `field_mapping` | 24小时 | 业务术语→技术字段 |

## 关键函数

### 认证获取

```python
from tableau_assistant.src.bi_platforms.tableau import (
    TableauAuthContext,      # 认证上下文 Pydantic 模型
    TableauAuthError,        # 认证错误
    get_tableau_auth,        # 同步获取认证
    get_tableau_auth_async,  # 异步获取认证
    ensure_valid_auth,       # 确保有效认证（同步）
    ensure_valid_auth_async, # 确保有效认证（异步）
)
```

### RunnableConfig 集成

```python
from tableau_assistant.src.bi_platforms.tableau import (
    create_config_with_auth,  # 创建带认证的配置
    get_auth_from_config,     # 从配置获取认证
)
```

## 使用示例

### 执行工作流

```python
from tableau_assistant.src.workflow.executor import WorkflowExecutor

executor = WorkflowExecutor()
result = await executor.run("各产品类别的销售额是多少")
# 认证自动处理，无需手动管理
```

### 在节点中使用

```python
from tableau_assistant.src.bi_platforms.tableau import ensure_valid_auth_async

async def my_node(state, config):
    # 获取有效认证（自动处理过期刷新）
    auth_ctx = await ensure_valid_auth_async(config)
    
    # 使用认证
    api_key = auth_ctx.api_key
    site = auth_ctx.site
```

### 获取 Tableau 配置

```python
from tableau_assistant.src.models.workflow.context import get_tableau_config

config = get_tableau_config()
# 返回: {"tableau_token": "...", "tableau_site": "...", "tableau_domain": "..."}
```

## 设计原则

1. **单一职责**：认证代码放在 `bi_platforms/tableau/auth.py`，数据模型放在 `models/`
2. **统一缓存**：使用内存缓存认证信息，避免重复 HTTP 请求
3. **自动刷新**：Token 过期时自动刷新，无需手动干预
4. **向后兼容**：`models/workflow/__init__.py` 重新导出认证类，保持兼容性
