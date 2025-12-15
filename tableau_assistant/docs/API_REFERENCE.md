# Tableau AI Analysis Assistant API 参考文档

## 概述

本文档详细描述了 Tableau AI Analysis Assistant 提供的所有 API 端点、请求/响应格式和使用示例。

---

## 基础信息

### 基础 URL

```
http://localhost:8000/api
```

### 认证

所有 API 请求需要在请求体中包含 `datasource_luid` 参数，系统会自动处理 Tableau 认证。

### 响应格式

所有响应均为 JSON 格式（流式 API 除外）。

---

## API 端点

### 1. 流式查询 API

#### POST /api/chat/stream

通过 SSE (Server-Sent Events) 流式返回查询结果。

**请求**

```http
POST /api/chat/stream
Content-Type: application/json

{
    "question": "各产品类别的销售额是多少",
    "datasource_luid": "abc123-def456-ghi789",
    "thread_id": "optional-thread-id"
}
```

**请求参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `question` | string | 是 | 用户的自然语言问题 |
| `datasource_luid` | string | 是 | Tableau 数据源 LUID |
| `thread_id` | string | 否 | 会话线程 ID，用于多轮对话 |

**响应**

SSE 事件流，每个事件格式：

```
data: {"event_type": "xxx", "data": {...}, "timestamp": "2024-12-14T10:00:00Z"}
```

**事件类型**

| 事件类型 | 说明 | data 结构 |
|----------|------|-----------|
| `node_start` | 节点开始执行 | `{"node": "understanding"}` |
| `token` | LLM 生成的 token | `{"content": "销售"}` |
| `node_complete` | 节点执行完成 | `{"node": "understanding", "result": {...}}` |
| `insight` | 洞察结果 | `{"insights": [...]}` |
| `replan` | 重规划建议 | `{"suggestions": [...]}` |
| `error` | 错误信息 | `{"code": "xxx", "message": "xxx"}` |
| `complete` | 流程完成 | `{"final_result": {...}}` |

**示例响应**

```
data: {"event_type": "node_start", "data": {"node": "understanding"}, "timestamp": "2024-12-14T10:00:00Z"}

data: {"event_type": "token", "data": {"content": "{"}, "timestamp": "2024-12-14T10:00:01Z"}

data: {"event_type": "token", "data": {"content": "measures"}, "timestamp": "2024-12-14T10:00:01Z"}

data: {"event_type": "node_complete", "data": {"node": "understanding", "result": {"is_analysis": true}}, "timestamp": "2024-12-14T10:00:02Z"}

data: {"event_type": "complete", "data": {"final_result": {...}}, "timestamp": "2024-12-14T10:00:10Z"}
```

**前端使用示例**

```javascript
async function streamQuery(question, datasourceLuid) {
    const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            question: question,
            datasource_luid: datasourceLuid
        })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const text = decoder.decode(value);
        const lines = text.split('\n');
        
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const event = JSON.parse(line.slice(6));
                handleEvent(event);
            }
        }
    }
}

function handleEvent(event) {
    switch (event.event_type) {
        case 'token':
            appendToOutput(event.data.content);
            break;
        case 'insight':
            displayInsights(event.data.insights);
            break;
        case 'complete':
            showFinalResult(event.data.final_result);
            break;
        case 'error':
            showError(event.data.message);
            break;
    }
}
```

---

### 2. 预热 API

#### POST /api/preload/dimension-hierarchy

启动维度层级推断预热任务。

**请求**

```http
POST /api/preload/dimension-hierarchy
Content-Type: application/json

{
    "datasource_luid": "abc123-def456-ghi789"
}
```

**响应**

```json
{
    "task_id": "task_abc123",
    "status": "started",
    "message": "Dimension hierarchy inference started"
}
```

---

#### GET /api/preload/status/{task_id}

查询预热任务状态。

**请求**

```http
GET /api/preload/status/task_abc123
```

**响应**

```json
{
    "task_id": "task_abc123",
    "status": "completed",
    "progress": 100,
    "result": {
        "hierarchies": [
            {
                "name": "Geography",
                "levels": ["Country", "Region", "City"]
            }
        ]
    },
    "started_at": "2024-12-14T10:00:00Z",
    "completed_at": "2024-12-14T10:00:30Z"
}
```

**状态值**

| 状态 | 说明 |
|------|------|
| `pending` | 等待执行 |
| `running` | 执行中 |
| `completed` | 已完成 |
| `failed` | 执行失败 |

---

#### POST /api/preload/invalidate

使缓存失效。

**请求**

```http
POST /api/preload/invalidate
Content-Type: application/json

{
    "datasource_luid": "abc123-def456-ghi789",
    "cache_types": ["metadata", "dimension_hierarchy"]
}
```

**响应**

```json
{
    "success": true,
    "invalidated": ["metadata", "dimension_hierarchy"]
}
```

---

#### GET /api/preload/cache-status/{datasource_luid}

查询缓存状态。

**请求**

```http
GET /api/preload/cache-status/abc123-def456-ghi789
```

**响应**

```json
{
    "datasource_luid": "abc123-def456-ghi789",
    "caches": {
        "metadata": {
            "exists": true,
            "created_at": "2024-12-14T08:00:00Z",
            "expires_at": "2024-12-15T08:00:00Z"
        },
        "dimension_hierarchy": {
            "exists": true,
            "created_at": "2024-12-14T08:00:00Z",
            "expires_at": "2024-12-15T08:00:00Z"
        }
    }
}
```

---

### 3. 问题优化 API

#### POST /api/boost-question

优化用户问题，使其更适合数据分析。

**请求**

```http
POST /api/boost-question
Content-Type: application/json

{
    "question": "数据怎么样",
    "datasource_luid": "abc123-def456-ghi789"
}
```

**响应**

```json
{
    "original_question": "数据怎么样",
    "boosted_questions": [
        "各产品类别的销售额是多少",
        "最近一个月的销售趋势如何",
        "销售额前10的地区有哪些"
    ],
    "suggestions": [
        "请指定具体的度量（如销售额、订单数）",
        "请指定分析维度（如地区、产品类别）"
    ]
}
```

---

### 4. 健康检查 API

#### GET /api/health

检查服务健康状态。

**请求**

```http
GET /api/health
```

**响应**

```json
{
    "status": "healthy",
    "version": "2.2.0",
    "components": {
        "database": "healthy",
        "llm": "healthy",
        "tableau": "healthy"
    },
    "timestamp": "2024-12-14T10:00:00Z"
}
```

---

## 数据模型

### SemanticQuery

语义查询模型，LLM 理解用户问题后的输出。

```typescript
interface SemanticQuery {
    measures: string[];           // 度量列表
    dimensions: string[];         // 维度列表
    filters: Filter[];            // 过滤条件
    sort: Sort[];                 // 排序
    limit?: number;               // 限制数量
    calculations?: Calculation[]; // 计算字段
}

interface Filter {
    field: string;
    operator: 'eq' | 'ne' | 'gt' | 'lt' | 'gte' | 'lte' | 'in' | 'between';
    value: any;
}

interface Sort {
    field: string;
    direction: 'asc' | 'desc';
}
```

### Insight

洞察结果模型。

```typescript
interface Insight {
    id: string;
    type: 'trend' | 'anomaly' | 'comparison' | 'distribution' | 'correlation';
    title: string;
    description: string;
    confidence: number;  // 0-1
    data: any;
    suggestions?: string[];
}
```

### ReplanDecision

重规划决策模型。

```typescript
interface ReplanDecision {
    should_continue: boolean;
    completeness_score: number;  // 0-1
    answered_questions: string[];
    exploration_suggestions: ExplorationSuggestion[];
}

interface ExplorationSuggestion {
    type: 'drill_down' | 'roll_up' | 'compare' | 'filter';
    question: string;
    reason: string;
}
```

---

## 错误处理

### 错误响应格式

```json
{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human readable error message",
        "details": {}
    }
}
```

### 错误代码

| 代码 | HTTP 状态 | 说明 |
|------|-----------|------|
| `AUTH_001` | 401 | 认证失败 |
| `AUTH_002` | 401 | Token 过期 |
| `QUERY_001` | 400 | 查询参数无效 |
| `QUERY_002` | 400 | 字段映射失败 |
| `LLM_001` | 503 | LLM 服务不可用 |
| `LLM_002` | 500 | LLM 响应解析失败 |
| `VIZQL_001` | 500 | VizQL 执行失败 |
| `VIZQL_002` | 404 | 数据源不存在 |
| `INTERNAL_001` | 500 | 内部服务器错误 |

---

## 速率限制

| 端点 | 限制 |
|------|------|
| `/api/chat/stream` | 10 请求/分钟/用户 |
| `/api/preload/*` | 5 请求/分钟/数据源 |
| `/api/boost-question` | 20 请求/分钟/用户 |

超过限制时返回 HTTP 429 状态码。

---

## WebSocket API（规划中）

未来版本将支持 WebSocket 连接，提供更低延迟的双向通信。

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat');

ws.onopen = () => {
    ws.send(JSON.stringify({
        type: 'query',
        question: '各地区销售额',
        datasource_luid: 'abc123'
    }));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    // 处理消息
};
```

---

## SDK（规划中）

### Python SDK

```python
from tableau_assistant import Client

client = Client(base_url="http://localhost:8000")

# 同步查询
result = client.query("各地区销售额", datasource_luid="abc123")

# 流式查询
for event in client.stream("各地区销售额", datasource_luid="abc123"):
    print(event)
```

### JavaScript SDK

```javascript
import { TableauAssistant } from 'tableau-assistant-sdk';

const client = new TableauAssistant({ baseUrl: 'http://localhost:8000' });

// 流式查询
await client.stream('各地区销售额', {
    datasourceLuid: 'abc123',
    onToken: (token) => console.log(token),
    onComplete: (result) => console.log(result)
});
```

---

**文档版本**: v2.2.0  
**最后更新**: 2024-12-14
