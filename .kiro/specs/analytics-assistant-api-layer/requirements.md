# Analytics Assistant API 层需求文档

## 1. 项目概述

### 1.1 项目背景

Analytics Assistant 后端已完成 Agent 层（semantic_parser、field_mapper、field_semantic）和基础设施层的开发，但**完全缺少 API 层**，导致前端无法调用后端功能。

**当前状态**：
- ✅ Agent 层已完成（3 个 Agent，15+ 节点）
- ✅ 基础设施已完成（LLM、Embedding、存储、RAG、Tableau 集成）
- ✅ 工作流上下文管理已完成（WorkflowContext）
- ❌ **API 层完全缺失**（无 FastAPI 应用、无路由、无端点）
- ❌ **工作流编排层缺失**（无法执行完整查询流程）

**目标**：
- 创建完整的 FastAPI 应用层
- 实现 SSE 流式输出端点（`/api/chat/stream`）
- 实现会话管理 API（`/api/sessions`）
- 实现用户设置 API（`/api/settings`）
- 实现用户反馈 API（`/api/feedback`）
- 创建工作流编排层（编排查询执行流程）
- 确保前后端协议对齐（SSE 事件格式、多轮对话处理）

### 1.2 技术约束

| 约束项 | 说明 |
|--------|------|
| 框架 | FastAPI 0.100+ |
| Python 版本 | 3.10+ |
| 异步支持 | 全异步（async/await） |
| 流式输出 | SSE（Server-Sent Events） |
| 数据库 | SQLite（开发）/ PostgreSQL（生产） |
| 认证方式 | Tableau 用户身份（通过请求头传递） |
| CORS | 支持前端跨域请求 |

### 1.3 依赖关系

| 依赖项 | 状态 | 说明 |
|--------|------|------|
| semantic_parser Agent | ✅ 已完成 | 15 个节点的语义解析流程 |
| field_mapper Agent | ✅ 已完成 | 字段映射 |
| field_semantic Agent | ✅ 已完成 | 字段语义推断 |
| WorkflowContext | ✅ 已完成 | 工作流上下文管理 |
| Tableau 平台适配器 | ✅ 已完成 | GraphQL 集成、认证 |
| 前端应用 | ⏳ 待开发 | Vue 3 + Vercel AI SDK |



## 2. 核心需求

### 需求 1: FastAPI 应用入口

**用户故事**: 作为开发者，我希望有一个标准的 FastAPI 应用入口，以便启动和管理 API 服务。

**优先级**: P0（核心功能）

**验收标准**:
1. WHEN 运行 `python -m analytics_assistant.src.api.main` THEN 启动 FastAPI 应用
2. WHEN 访问 `/docs` THEN 显示 Swagger UI 文档
3. WHEN 访问 `/health` THEN 返回健康检查状态
4. WHEN 应用启动 THEN 自动加载配置（从 `config/app.yaml`）
5. WHEN 应用启动 THEN 初始化数据库连接
6. WHEN 应用启动 THEN 配置 CORS（允许前端跨域请求）
7. WHEN 应用关闭 THEN 优雅关闭所有连接

### 需求 2: SSE 流式输出端点

**用户故事**: 作为前端开发者，我希望通过 SSE 接收流式输出，以便实时展示 AI 思考过程和回复内容。

**优先级**: P0（核心功能）

**验收标准**:
1. WHEN POST `/api/chat/stream` THEN 返回 SSE 流（`Content-Type: text/event-stream`）
2. WHEN 请求包含 `messages` THEN 使用 `HistoryManager` 按 token 数量裁剪（max: 1000 tokens）
3. WHEN 请求包含 `datasourceName` THEN 自动转换为 `datasourceLUID`
4. WHEN 工作流执行到 LLM 调用节点 THEN 发送 `thinking` 事件（更新 ProcessingStage）
5. WHEN LLM 返回 token THEN 发送 `token` 事件（流式文本）
6. WHEN 查询返回数据 THEN 发送 `data` 事件（表格数据）
7. WHEN 生成图表配置 THEN 发送 `chart` 事件（图表配置）
8. WHEN 生成建议问题 THEN 发送 `suggestions` 事件（建议问题列表）
9. WHEN 工作流完成 THEN 发送 `complete` 事件
10. WHEN 工作流出错 THEN 发送 `error` 事件
11. WHEN 客户端断开连接 THEN 取消工作流执行
12. WHEN 请求超时（> 60 秒） THEN 自动取消并返回错误

### 需求 3: 多轮对话上下文处理

**用户故事**: 作为后端开发者，我希望自动处理多轮对话上下文，以便减少 Token 消耗并提高响应速度。

**优先级**: P0（核心功能）

**说明**: 后端已有 `HistoryManager` 组件处理对话历史，使用 **Token 数量**裁剪（而非轮数裁剪）

**后端实现**:
- 配置文件: `analytics_assistant/config/app.yaml`
  - `semantic_parser.token_optimization.max_history_tokens: 1000` - 对话历史最大 token 数
  - `semantic_parser.token_optimization.use_summarization: true` - 是否使用历史摘要（预留）
- 组件: `HistoryManager` (`analytics_assistant/src/agents/semantic_parser/components/history_manager.py`)
  - `truncate_history()` - 从最新消息开始保留，直到达到 token 限制
  - `estimate_history_tokens()` - 估算对话历史的 token 数（中文约 2 字符/token）
  - `format_history_for_prompt()` - 格式化对话历史用于 Prompt

**前后端协作方式**:
1. **前端**: 可以发送完整对话历史，或按轮数预裁剪（减少网络传输）
2. **后端**: 使用 `HistoryManager.truncate_history()` 按 token 数量精确裁剪
3. **优势**: 前端无需关心 token 计算，后端自动优化

**验收标准**:
1. WHEN 接收到 `messages` 列表 THEN 使用 `HistoryManager.truncate_history()` 裁剪
2. WHEN 对话历史 token 数 <= 1000 THEN 保留所有消息
3. WHEN 对话历史 token 数 > 1000 THEN 保留最近的消息（从最新开始累积，直到达到 1000 token）
4. WHEN 裁剪消息 THEN 保持消息顺序（最新消息在最后）
5. WHEN 裁剪消息 THEN 记录日志（原始消息数、裁剪后消息数、原始 token 数、裁剪后 token 数）
6. WHEN 配置 `max_history_tokens` 改变 THEN 自动应用新的限制

### 需求 4: ProcessingStage 映射

**用户故事**: 作为前端开发者，我希望接收到粗粒度的处理阶段，以便向用户展示 AI 思考进度。

**优先级**: P0（核心功能）

**说明**: 只有涉及 LLM 调用的节点才发送 `thinking` 事件到前端

**验收标准**:
1. WHEN 执行 `semantic_understanding_node` THEN 发送 `thinking` 事件（stage: `understanding`）
2. WHEN 执行 `field_mapper` Agent THEN 发送 `thinking` 事件（stage: `mapping`）
3. WHEN 执行 `query_adapter_node` THEN 发送 `thinking` 事件（stage: `building`）
4. WHEN 执行 Tableau GraphQL 查询 THEN 发送 `thinking` 事件（stage: `executing`）
5. WHEN 执行 `feedback_learner_node` THEN 发送 `thinking` 事件（stage: `generating`）
6. WHEN 其他节点执行 THEN 不发送 `thinking` 事件（前端不可见）

**节点到阶段的映射表**:

| 后端节点 | 是否调用 LLM | ProcessingStage | 说明 |
|---------|-------------|-----------------|------|
| `intent_router_node` | ❌ | - | 规则匹配，不发送事件 |
| `query_cache_node` | ❌ | - | 缓存查询，不发送事件 |
| `rule_prefilter_node` | ❌ | - | 规则预处理，不发送事件 |
| `feature_cache_node` | ❌ | - | 缓存查询，不发送事件 |
| `feature_extractor_node` | ✅ | `understanding` | 快速 LLM 调用 |
| `field_retriever_node` | ❌ | - | RAG 检索，不发送事件 |
| `dynamic_schema_builder_node` | ❌ | - | Schema 构建，不发送事件 |
| `modular_prompt_builder_node` | ❌ | - | Prompt 构建，不发送事件 |
| `few_shot_manager_node` | ❌ | - | 示例检索，不发送事件 |
| `semantic_understanding_node` | ✅ | `understanding` | 主要 LLM 调用 |
| `output_validator_node` | ❌ | - | 验证逻辑，不发送事件 |
| `filter_validator_node` | ❌ | - | 验证逻辑，不发送事件 |
| `query_adapter_node` | ❌ | `building` | 查询构建（不调用 LLM，但用户可见） |
| `error_corrector_node` | ✅ | `understanding` | LLM 修正 |
| `feedback_learner_node` | ❌ | `generating` | 缓存更新（不调用 LLM，但用户可见） |
| `field_mapper` Agent | ✅ | `mapping` | LLM 调用 |
| `field_semantic` Agent | ✅ | `understanding` | LLM 调用 |
| Tableau GraphQL 查询 | ❌ | `executing` | 数据查询（不调用 LLM，但用户可见） |



### 需求 5: 会话管理 API

**用户故事**: 作为前端开发者，我希望通过 REST API 管理用户会话，以便实现会话历史和跨设备同步。

**优先级**: P0（核心功能）

**说明**: 会话数据存储在数据库，使用 Tableau 用户身份进行数据隔离

**验收标准**:
1. WHEN POST `/api/sessions` THEN 创建新会话，返回 `sessionId`
2. WHEN GET `/api/sessions` THEN 返回当前用户的所有会话列表（按 `updatedAt` 倒序）
3. WHEN GET `/api/sessions/{sessionId}` THEN 返回会话详情（包含完整消息列表）
4. WHEN PUT `/api/sessions/{sessionId}` THEN 更新会话（标题、消息列表）
5. WHEN DELETE `/api/sessions/{sessionId}` THEN 删除会话
6. WHEN 请求头包含 `X-Tableau-Username` THEN 自动过滤该用户的会话
7. WHEN 请求头缺少 `X-Tableau-Username` THEN 返回 401 错误
8. WHEN 用户 A 尝试访问用户 B 的会话 THEN 返回 403 错误
9. WHEN 会话不存在 THEN 返回 404 错误

### 需求 6: 用户设置 API

**用户故事**: 作为前端开发者，我希望通过 REST API 管理用户设置，以便实现个性化配置和跨设备同步。

**优先级**: P0（核心功能）

**说明**: 用户设置存储在数据库，使用 Tableau 用户身份进行数据隔离

**验收标准**:
1. WHEN GET `/api/settings` THEN 返回当前用户的设置
2. WHEN PUT `/api/settings` THEN 更新用户设置
3. WHEN 用户首次访问 THEN 自动创建默认设置
4. WHEN 请求头包含 `X-Tableau-Username` THEN 自动过滤该用户的设置
5. WHEN 请求头缺少 `X-Tableau-Username` THEN 返回 401 错误

**设置字段**:
- `language`: 语言（`zh` | `en`）
- `analysisDepth`: 分析深度（`detailed` | `comprehensive`）
- `theme`: 主题（`light` | `dark` | `system`）
- `defaultDataSourceId`: 默认数据源 ID
- `showThinkingProcess`: 是否显示思考过程

### 需求 7: 用户反馈 API

**用户故事**: 作为前端开发者，我希望通过 REST API 提交用户反馈，以便收集用户对 AI 回复的评价。

**优先级**: P0（核心功能）

**验收标准**:
1. WHEN POST `/api/feedback` THEN 保存用户反馈到数据库
2. WHEN 反馈类型为 `positive` THEN 记录点赞
3. WHEN 反馈类型为 `negative` THEN 记录点踩和原因
4. WHEN 请求头包含 `X-Tableau-Username` THEN 关联到该用户
5. WHEN 请求头缺少 `X-Tableau-Username` THEN 返回 401 错误

**反馈字段**:
- `messageId`: 消息 ID
- `type`: 反馈类型（`positive` | `negative`）
- `reason`: 反馈原因（可选）
- `comment`: 反馈评论（可选）

### 需求 8: 工作流编排

**用户故事**: 作为后端开发者，我希望有一个统一的工作流编排器，以便管理完整的查询执行流程。

**优先级**: P0（核心功能）

**说明**: semantic_parser 子图已经是完整的端到端流程（15+ 节点），内部包含 field_mapper、error_corrector、feedback_learner 等。field_semantic 是预处理步骤，在数据模型加载时调用。

**验收标准**:
1. WHEN 创建 `WorkflowExecutor` THEN 接受 Tableau 用户名作为参数
2. WHEN 执行工作流 THEN 按顺序执行：认证 → 数据源解析 → 数据模型加载（含字段语义推断）→ semantic_parser 子图
3. WHEN 工作流执行 THEN 支持流式输出（通过回调函数注入 RunnableConfig）
4. WHEN semantic_parser 子图内部出错 THEN 子图内部的 error_corrector_node 自动处理
5. WHEN 工作流完成 THEN 子图内部的 feedback_learner_node 自动执行
6. WHEN 客户端断开连接 THEN 取消工作流执行
7. WHEN 工作流超时 THEN 自动取消并返回错误

### 需求 9: 数据源名称转换

**用户故事**: 作为后端开发者，我希望自动将数据源名称转换为 LUID，以便前端无需关心 LUID 的获取。

**优先级**: P0（核心功能）

**验收标准**:
1. WHEN 接收到 `datasourceName` THEN 通过 Tableau GraphQL 查询 LUID
2. WHEN 数据源不存在 THEN 返回 404 错误
3. WHEN GraphQL 查询失败 THEN 返回 500 错误
4. WHEN 转换成功 THEN 将 LUID 存入 WorkflowContext
5. WHEN 转换成功 THEN 记录日志（datasourceName → datasourceLUID）

### 需求 10: 错误处理与日志

**用户故事**: 作为运维人员，我希望有完善的错误处理和日志记录，以便快速定位和解决问题。

**优先级**: P0（核心功能）

**验收标准**:
1. WHEN 发生异常 THEN 记录完整的错误堆栈
2. WHEN 发生异常 THEN 返回用户友好的错误消息（不暴露内部细节）
3. WHEN API 调用 THEN 记录请求日志（用户名、端点、参数、耗时）
4. WHEN 工作流执行 THEN 记录每个节点的执行时间
5. WHEN 工作流出错 THEN 记录错误节点和错误原因
6. WHEN 日志级别为 DEBUG THEN 记录详细的中间结果
7. WHEN 日志级别为 INFO THEN 只记录关键事件



## 3. SSE 事件格式规范

### 3.1 事件类型定义

| 事件类型 | 字段 | 说明 | 触发时机 |
|---------|------|------|----------|
| `thinking` | `stage`, `name`, `status` | 处理阶段更新 | LLM 调用节点开始/完成 |
| `token` | `content` | 流式文本内容 | LLM 返回 token |
| `data` | `tableData` | 查询结果数据 | Tableau GraphQL 返回数据 |
| `chart` | `chartConfig` | 图表配置 | 自动生成图表配置 |
| `suggestions` | `questions` | 建议问题列表 | 工作流完成 |
| `complete` | - | 流式输出完成 | 工作流完成 |
| `error` | `error` | 错误信息 | 工作流出错 |

### 3.2 SSE 事件格式示例

**思考阶段更新**:
```
data: {"type":"thinking","stage":"understanding","name":"理解问题","status":"running"}

data: {"type":"thinking","stage":"understanding","name":"理解问题","status":"completed"}
```

**流式文本输出**:
```
data: {"type":"token","content":"根据"}

data: {"type":"token","content":"您的"}

data: {"type":"token","content":"问题"}
```

**查询结果数据**:
```json
data: {
  "type": "data",
  "tableData": {
    "columns": [
      {"key": "region", "label": "地区", "type": "string"},
      {"key": "sales", "label": "销售额", "type": "number"}
    ],
    "rows": [
      {"region": "华东", "sales": 1234567},
      {"region": "华南", "sales": 987654}
    ],
    "totalCount": 2
  }
}
```

**图表配置**:
```json
data: {
  "type": "chart",
  "chartConfig": {
    "type": "bar",
    "title": "各地区销售额",
    "xAxis": {"name": "地区", "type": "category", "data": ["华东", "华南"]},
    "yAxis": {"name": "销售额", "type": "value"},
    "series": [{"name": "销售额", "type": "bar", "data": [1234567, 987654]}]
  }
}
```

**建议问题**:
```json
data: {
  "type": "suggestions",
  "questions": [
    "按月份查看销售趋势",
    "对比去年同期数据",
    "查看销售额前10的产品"
  ]
}
```

**完成事件**:
```
data: {"type":"complete"}
```

**错误事件**:
```json
data: {
  "type": "error",
  "error": "数据源连接失败，请检查 Tableau 连接"
}
```

### 3.3 ProcessingStage 定义

```typescript
export type ProcessingStage = 
  | 'understanding'  // 理解问题（semantic_understanding、feature_extractor、field_semantic）
  | 'mapping'        // 字段映射（field_mapper）
  | 'building'       // 构建查询（query_adapter）
  | 'executing'      // 执行分析（Tableau GraphQL 查询）
  | 'generating'     // 生成洞察（feedback_learner）
```



## 4. API 请求/响应模型

### 4.1 聊天 API

**请求模型** (`ChatRequest`):
```python
class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: Optional[datetime] = None

class ChatRequest(BaseModel):
    messages: List[Message]  # 完整对话历史（前端已裁剪到最近 10 轮）
    datasource_name: str     # 数据源名称（前端从 Tableau API 获取）
    language: Literal["zh", "en"] = "zh"
    analysis_depth: Literal["detailed", "comprehensive"] = "detailed"
    session_id: Optional[str] = None
```

**响应**: SSE 流（见 3.2 节）

### 4.2 会话管理 API

**创建会话请求** (`CreateSessionRequest`):
```python
class CreateSessionRequest(BaseModel):
    title: Optional[str] = None  # 会话标题（可选，默认自动生成）
```

**创建会话响应** (`CreateSessionResponse`):
```python
class CreateSessionResponse(BaseModel):
    session_id: str  # UUID v4
    created_at: datetime
```

**会话模型** (`Session`):
```python
class Session(BaseModel):
    id: str                    # UUID v4
    tableau_username: str      # Tableau 用户名
    title: str                 # 会话标题
    messages: List[Message]    # 消息列表
    created_at: datetime
    updated_at: datetime
```

**获取会话列表响应** (`GetSessionsResponse`):
```python
class GetSessionsResponse(BaseModel):
    sessions: List[Session]
    total: int
```

**更新会话请求** (`UpdateSessionRequest`):
```python
class UpdateSessionRequest(BaseModel):
    title: Optional[str] = None
    messages: Optional[List[Message]] = None
```

### 4.3 用户设置 API

**用户设置模型** (`UserSettings`):
```python
class UserSettings(BaseModel):
    tableau_username: str  # Tableau 用户名（主键）
    language: Literal["zh", "en"] = "zh"
    analysis_depth: Literal["detailed", "comprehensive"] = "detailed"
    theme: Literal["light", "dark", "system"] = "light"
    default_datasource_id: Optional[str] = None
    show_thinking_process: bool = True
    created_at: datetime
    updated_at: datetime
```

**更新设置请求** (`UpdateSettingsRequest`):
```python
class UpdateSettingsRequest(BaseModel):
    language: Optional[Literal["zh", "en"]] = None
    analysis_depth: Optional[Literal["detailed", "comprehensive"]] = None
    theme: Optional[Literal["light", "dark", "system"]] = None
    default_datasource_id: Optional[str] = None
    show_thinking_process: Optional[bool] = None
```

### 4.4 用户反馈 API

**反馈请求** (`FeedbackRequest`):
```python
class FeedbackRequest(BaseModel):
    message_id: str
    type: Literal["positive", "negative"]
    reason: Optional[str] = None
    comment: Optional[str] = None
```



## 5. 数据库设计

### 5.1 会话表 (`sessions`)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | VARCHAR(36) | PRIMARY KEY | UUID v4 |
| `tableau_username` | VARCHAR(255) | NOT NULL, INDEX | Tableau 用户名 |
| `title` | VARCHAR(500) | NOT NULL | 会话标题 |
| `messages` | JSON | NOT NULL | 消息列表（JSON 格式） |
| `created_at` | TIMESTAMP | NOT NULL | 创建时间 |
| `updated_at` | TIMESTAMP | NOT NULL | 更新时间 |

**索引**:
- `idx_tableau_username_updated_at`: (`tableau_username`, `updated_at` DESC)

### 5.2 用户设置表 (`user_settings`)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `tableau_username` | VARCHAR(255) | PRIMARY KEY | Tableau 用户名 |
| `language` | VARCHAR(10) | NOT NULL | 语言 |
| `analysis_depth` | VARCHAR(20) | NOT NULL | 分析深度 |
| `theme` | VARCHAR(20) | NOT NULL | 主题 |
| `default_datasource_id` | VARCHAR(255) | NULL | 默认数据源 ID |
| `show_thinking_process` | BOOLEAN | NOT NULL | 是否显示思考过程 |
| `created_at` | TIMESTAMP | NOT NULL | 创建时间 |
| `updated_at` | TIMESTAMP | NOT NULL | 更新时间 |

### 5.3 用户反馈表 (`user_feedback`)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | 自增 ID |
| `tableau_username` | VARCHAR(255) | NOT NULL, INDEX | Tableau 用户名 |
| `message_id` | VARCHAR(255) | NOT NULL | 消息 ID |
| `type` | VARCHAR(20) | NOT NULL | 反馈类型 |
| `reason` | VARCHAR(500) | NULL | 反馈原因 |
| `comment` | TEXT | NULL | 反馈评论 |
| `created_at` | TIMESTAMP | NOT NULL | 创建时间 |

**索引**:
- `idx_tableau_username`: (`tableau_username`)
- `idx_message_id`: (`message_id`)



## 6. 非功能性需求

### NFR-1: 性能要求

| 指标 | 目标值 | 测量方法 |
|-----|-------|---------|
| API 响应时间（非流式） | < 200ms | 日志统计 |
| SSE 首字节时间 | < 500ms | 网络监控 |
| SSE token 延迟 | < 50ms | 网络监控 |
| 数据库查询时间 | < 100ms | 日志统计 |
| 并发连接数 | 100+ | 压力测试 |

### NFR-2: 安全性要求

| 要求 | 说明 |
|-----|------|
| 用户身份校验 | 所有 API 必须校验 `X-Tableau-Username` 请求头 |
| 数据隔离 | 不同用户的数据完全隔离（通过 `tableau_username` 过滤） |
| SQL 注入防护 | 使用参数化查询，禁止拼接 SQL |
| XSS 防护 | 转义所有用户输入 |
| CORS 配置 | 只允许前端域名跨域请求 |
| 日志脱敏 | 日志中不记录敏感信息（如 API Key） |

### NFR-3: 可维护性要求

| 要求 | 说明 |
|-----|------|
| 代码规范 | 遵循 `coding-standards.md` |
| 类型安全 | 使用 Pydantic 模型，严格类型检查 |
| 错误处理 | 统一错误处理中间件 |
| 日志规范 | 使用结构化日志（JSON 格式） |
| 测试覆盖 | 单元测试覆盖率 > 80% |
| 文档 | 所有 API 端点有 OpenAPI 文档 |

### NFR-4: 可扩展性要求

| 要求 | 说明 |
|-----|------|
| 异步支持 | 所有 I/O 操作使用 async/await |
| 数据库连接池 | 使用连接池管理数据库连接 |
| 缓存支持 | 支持 Redis 缓存（可选） |
| 水平扩展 | 支持多实例部署（无状态设计） |



## 7. 实施计划

### 阶段 1: 基础设施（1-2 天）

**目标**: 创建 FastAPI 应用骨架和数据库

**任务**:
- [ ] 创建 `analytics_assistant/src/api/main.py` - FastAPI 应用入口
- [ ] 创建 `analytics_assistant/src/api/models.py` - Pydantic 模型
- [ ] 创建 `analytics_assistant/src/api/database.py` - 数据库连接和 ORM
- [ ] 创建数据库迁移脚本（SQLite）
- [ ] 配置 CORS 和中间件
- [ ] 实现健康检查端点（`/health`）

**验收标准**:
- ✅ 可以启动 FastAPI 应用
- ✅ 可以访问 `/docs` 查看 Swagger UI
- ✅ 可以访问 `/health` 获取健康状态
- ✅ 数据库表已创建

### 阶段 2: 工作流编排（2-3 天）

**目标**: 创建工作流编排层

**任务**:
- [ ] 创建 `analytics_assistant/src/orchestration/workflow/executor.py` - WorkflowExecutor
- [ ] 创建 `analytics_assistant/src/orchestration/workflow/callbacks.py` - SSE 回调
- [ ] 实现流式输出回调机制
- [ ] 实现 ProcessingStage 映射逻辑
- [ ] 集成 TableauDataLoader 和 TableauClient 进行数据源解析和数据模型加载

**验收标准**:
- ✅ 可以创建 WorkflowExecutor 实例
- ✅ 可以执行完整工作流（认证 → 数据源解析 → 数据模型加载 → semantic_parser 子图）
- ✅ 可以通过回调函数接收流式输出
- ✅ 可以自动映射 ProcessingStage

### 阶段 3: SSE 流式输出端点（2-3 天）

**目标**: 实现 `/api/chat/stream` 端点

**任务**:
- [ ] 创建 `analytics_assistant/src/api/chat.py` - 聊天 API 路由
- [ ] 实现 SSE 流式输出逻辑
- [ ] 实现多轮对话上下文裁剪
- [ ] 实现 SSE 事件格式转换
- [ ] 实现客户端断开检测
- [ ] 实现超时处理

**验收标准**:
- ✅ 可以通过 POST `/api/chat/stream` 发送问题
- ✅ 可以接收 SSE 流式输出
- ✅ 可以接收所有类型的 SSE 事件（thinking、token、data、chart、suggestions、complete、error）
- ✅ 客户端断开时自动取消工作流

### 阶段 4: 会话管理 API（1-2 天）

**目标**: 实现会话管理 CRUD 接口

**任务**:
- [ ] 创建 `analytics_assistant/src/api/sessions.py` - 会话管理 API 路由
- [ ] 实现创建会话（POST `/api/sessions`）
- [ ] 实现获取会话列表（GET `/api/sessions`）
- [ ] 实现获取会话详情（GET `/api/sessions/{id}`）
- [ ] 实现更新会话（PUT `/api/sessions/{id}`）
- [ ] 实现删除会话（DELETE `/api/sessions/{id}`）
- [ ] 实现用户身份校验中间件

**验收标准**:
- ✅ 可以创建、查询、更新、删除会话
- ✅ 不同用户的会话完全隔离
- ✅ 缺少 `X-Tableau-Username` 时返回 401
- ✅ 访问其他用户会话时返回 403

### 阶段 5: 用户设置和反馈 API（1 天）

**目标**: 实现用户设置和反馈接口

**任务**:
- [ ] 创建 `analytics_assistant/src/api/settings.py` - 设置 API 路由
- [ ] 创建 `analytics_assistant/src/api/feedback.py` - 反馈 API 路由
- [ ] 实现获取设置（GET `/api/settings`）
- [ ] 实现更新设置（PUT `/api/settings`）
- [ ] 实现提交反馈（POST `/api/feedback`）

**验收标准**:
- ✅ 可以获取和更新用户设置
- ✅ 首次访问时自动创建默认设置
- ✅ 可以提交用户反馈

### 阶段 6: 测试和优化（1-2 天）

**目标**: 完善测试和性能优化

**任务**:
- [ ] 编写单元测试（覆盖率 > 80%）
- [ ] 编写集成测试（端到端测试）
- [ ] 性能测试和优化
- [ ] 错误处理完善
- [ ] 日志完善
- [ ] 文档完善

**验收标准**:
- ✅ 单元测试覆盖率 > 80%
- ✅ 所有集成测试通过
- ✅ 性能指标达标
- ✅ 错误处理完善
- ✅ OpenAPI 文档完整

**总时间估算**: 8-13 天



## 8. 技术风险与缓解措施

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| SSE 连接不稳定 | 高 | 中 | 实现自动重连机制、心跳检测 |
| 工作流执行超时 | 中 | 中 | 设置合理的超时时间、提供取消机制 |
| 数据库性能瓶颈 | 中 | 低 | 使用连接池、添加索引、考虑 Redis 缓存 |
| 用户身份伪造 | 高 | 中 | 记录访问日志、定期审计、生产环境使用反向代理 |
| LangGraph 状态管理复杂 | 中 | 中 | 使用 checkpointer 持久化状态、完善错误恢复 |
| 多轮对话上下文丢失 | 中 | 低 | 前端裁剪逻辑、后端验证消息数量 |

## 9. 依赖与前置条件

### 后端依赖

| 依赖项 | 版本 | 说明 |
|--------|------|------|
| FastAPI | 0.100+ | Web 框架 |
| Uvicorn | 0.20+ | ASGI 服务器 |
| SQLAlchemy | 2.0+ | ORM |
| Pydantic | 2.0+ | 数据验证 |
| LangGraph | 0.0.30+ | 工作流编排 |
| aiosqlite | 0.19+ | 异步 SQLite 驱动 |

### 前端依赖

| 依赖项 | 状态 | 说明 |
|--------|------|------|
| Vue 3 应用 | ⏳ 待开发 | 前端应用 |
| Vercel AI SDK | ⏳ 待集成 | SSE 客户端 |
| Tableau Extensions API | ✅ 已集成 | 获取用户信息和数据源 |

### 开发环境

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 运行时环境 |
| SQLite | 3.35+ | 开发数据库 |
| Postman | 最新 | API 测试 |
| curl | 最新 | SSE 测试 |

## 10. 附录

### 10.1 多轮对话裁剪逻辑

**后端实现**（使用 `HistoryManager`）:

后端使用 `HistoryManager` 组件按 **token 数量**裁剪对话历史，而非按轮数裁剪。

```python
from analytics_assistant.src.agents.semantic_parser.components.history_manager import (
    HistoryManager,
    get_history_manager,
)

# 在 /api/chat/stream 端点中使用
async def chat_stream(request: ChatRequest):
    # 1. 将前端消息格式转换为后端格式
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in request.messages
    ]
    
    # 2. 使用 HistoryManager 裁剪历史（按 token 数量）
    manager = get_history_manager()
    truncated_history = manager.truncate_history(history)
    
    # 3. 记录裁剪信息
    original_tokens = manager.estimate_history_tokens(history)
    truncated_tokens = manager.estimate_history_tokens(truncated_history)
    
    logger.info(
        f"对话历史裁剪: {len(history)} → {len(truncated_history)} 条消息, "
        f"{original_tokens} → {truncated_tokens} tokens"
    )
    
    # 4. 使用裁剪后的历史执行工作流
    workflow_context = WorkflowContext(
        question=request.messages[-1].content,
        history=truncated_history,
        ...
    )
```

**HistoryManager 核心方法**:

```python
class HistoryManager:
    """对话历史管理器
    
    配置来源: analytics_assistant/config/app.yaml
    - semantic_parser.token_optimization.max_history_tokens: 1000
    - semantic_parser.token_optimization.use_summarization: true
    """
    
    def truncate_history(
        self,
        history: Optional[List[Dict[str, str]]],
        max_tokens: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """截断对话历史（保留最近消息）
        
        从最新的消息开始保留，直到达到 token 限制。
        这确保了最近的上下文被保留。
        
        Args:
            history: 对话历史列表
            max_tokens: 最大 token 数（None 使用配置值 1000）
        
        Returns:
            截断后的历史列表（保留最近消息）
        """
        if not history:
            return []
        
        max_tokens = max_tokens or self.max_history_tokens  # 默认 1000
        
        # 检查是否需要截断
        total_tokens = estimate_history_tokens(history)
        if total_tokens <= max_tokens:
            return history
        
        # 从最新消息开始保留
        truncated = []
        current_tokens = 0
        
        # 反向遍历（从最新到最旧）
        for msg in reversed(history):
            msg_tokens = estimate_message_tokens(msg)
            
            if current_tokens + msg_tokens > max_tokens:
                # 达到限制，停止添加
                break
            
            truncated.insert(0, msg)  # 插入到开头以保持顺序
            current_tokens += msg_tokens
        
        logger.info(
            f"对话历史已截断: {len(history)} -> {len(truncated)} 条消息, "
            f"{total_tokens} -> {current_tokens} tokens"
        )
        
        return truncated
    
    def estimate_history_tokens(self, history: List[Dict[str, str]]) -> int:
        """估算对话历史的总 token 数
        
        使用简单的字符数估算：
        - 中文约 2 字符/token
        - 英文约 4 字符/token
        - 这里使用保守估计（2 字符/token）
        """
        if not history:
            return 0
        return sum(estimate_message_tokens(msg) for msg in history)
```

**前端建议**（可选优化）:

前端可以按轮数预裁剪（减少网络传输），后端会再按 token 数量精确裁剪：

```typescript
const sendMessage = async (content: string) => {
  // 可选：前端预裁剪到最近 10 轮对话（20 条消息）
  const maxMessages = 20
  
  if (messages.value.length >= maxMessages) {
    const trimmedMessages = messages.value.slice(-maxMessages + 1)
    setMessages(trimmedMessages)
  }
  
  // 后端会再按 token 数量（1000 tokens）精确裁剪
  await append({ role: 'user', content })
}
```

### 10.2 Token 流式输出与 SSE 集成

**后端现有实现**:

后端已有完整的 token 流式输出机制，通过 `stream_llm_structured()` 函数实现：

```python
# analytics_assistant/src/agents/base/node.py
async def stream_llm_structured(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    output_model: Type[T],
    *,
    on_token: Optional[Callable[[str], Awaitable[None]]] = None,  # Token 回调
    on_partial: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,  # 部分 JSON 回调
    on_thinking: Optional[Callable[[str], Awaitable[None]]] = None,  # Thinking 回调（R1 模型）
    return_thinking: bool = False,
) -> Union[T, tuple[T, str]]:
    """
    流式调用 LLM 并返回结构化输出
    
    同时提供：
    1. Token 级别流式输出（通过 on_token 回调）
    2. 部分 JSON 对象流式输出（通过 on_partial 回调）
    3. 完整的 Pydantic 对象返回
    4. Thinking 输出（R1 模型，可选）
    """
    # 内部使用 llm.astream() 获取 token 流
    async for chunk in llm.astream(augmented_messages, config=config):
        if hasattr(chunk, "content") and chunk.content:
            token = chunk.content
            collected_content.append(token)
            if on_token:
                await on_token(token)  # 实时回调每个 token
```

**在 LangGraph 节点中使用**:

```python
# analytics_assistant/src/agents/semantic_parser/graph.py
async def semantic_understanding_node(
    state: SemanticParserState,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    # 从 config 中获取流式回调
    on_token = None
    on_thinking = None
    if config:
        configurable = config.get("configurable", {})
        on_token = configurable.get("on_token")  # API 层注入的回调
        on_thinking = configurable.get("on_thinking")
    
    # 调用 LLM，自动触发 on_token 回调
    result, thinking = await stream_llm_structured(
        llm=llm,
        messages=messages,
        output_model=SemanticOutput,
        on_token=on_token,  # 传递回调
        on_thinking=on_thinking,
        return_thinking=True,
    )
```

**API 层集成方案**:

在 `/api/chat/stream` 端点中，通过 `RunnableConfig` 注入回调函数，将 token 转换为 SSE 事件：

```python
# analytics_assistant/src/api/chat.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langgraph.graph import RunnableConfig

router = APIRouter()

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE 流式输出端点"""
    
    async def event_generator():
        # 定义 token 回调：将 token 转换为 SSE 事件
        async def on_token(token: str):
            event = {
                "type": "token",
                "content": token
            }
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        
        # 定义 thinking 回调（R1 模型）
        async def on_thinking(thinking: str):
            event = {
                "type": "thinking_token",  # 可选：区分思考过程
                "content": thinking
            }
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        
        # 定义节点开始/完成回调：发送 ProcessingStage 事件
        async def on_node_start(node_name: str):
            stage = get_processing_stage(node_name)
            if stage:  # 只有 LLM 调用节点才发送
                event = {
                    "type": "thinking",
                    "stage": stage,
                    "name": get_stage_display_name(stage),
                    "status": "running"
                }
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        
        async def on_node_end(node_name: str):
            stage = get_processing_stage(node_name)
            if stage:
                event = {
                    "type": "thinking",
                    "stage": stage,
                    "name": get_stage_display_name(stage),
                    "status": "completed"
                }
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        
        # 创建 RunnableConfig，注入回调
        config = RunnableConfig(
            configurable={
                "on_token": on_token,  # Token 回调
                "on_thinking": on_thinking,  # Thinking 回调
                "on_node_start": on_node_start,  # 节点开始回调
                "on_node_end": on_node_end,  # 节点完成回调
            }
        )
        
        # 执行工作流
        try:
            # 使用 astream 监听节点执行
            async for event in workflow_graph.astream(initial_state, config, stream_mode="updates"):
                for node_name, node_output in event.items():
                    # 节点开始
                    await on_node_start(node_name)
                    
                    # 节点执行（on_token 会在内部自动触发）
                    # ...
                    
                    # 节点完成
                    await on_node_end(node_name)
                    
                    # 处理其他事件（data、chart、suggestions）
                    if "query_result" in node_output:
                        yield format_data_event(node_output["query_result"])
                    if "chart_config" in node_output:
                        yield format_chart_event(node_output["chart_config"])
            
            # 发送完成事件
            yield f"data: {json.dumps({'type': 'complete'}, ensure_ascii=False)}\n\n"
        
        except Exception as e:
            # 发送错误事件
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

**关键点**:

1. **回调注入**: 通过 `RunnableConfig.configurable` 注入 `on_token`、`on_thinking` 回调
2. **自动触发**: `stream_llm_structured()` 内部会自动调用这些回调
3. **SSE 转换**: 回调函数将 token 转换为 SSE 事件格式
4. **异步生成器**: 使用 `async def event_generator()` 生成 SSE 流
5. **节点监听**: 使用 `graph.astream(stream_mode="updates")` 监听节点执行

**优势**:

- ✅ 无需修改现有 Agent 代码
- ✅ 回调机制已经存在，只需在 API 层注入
- ✅ 支持多种事件类型（token、thinking、stage、data、chart）
- ✅ 完全异步，性能优秀

### 10.3 ProcessingStage 映射实现

```python
def get_processing_stage(node_name: str) -> Optional[str]:
    """根据节点名称返回 ProcessingStage"""
    
    # LLM 调用节点映射
    llm_node_mapping = {
        "feature_extractor_node": "understanding",
        "semantic_understanding_node": "understanding",
        "error_corrector_node": "understanding",
        "field_mapper": "mapping",
        "field_semantic": "understanding",
    }
    
    # 用户可见节点映射（不调用 LLM，但需要展示）
    visible_node_mapping = {
        "query_adapter_node": "building",
        "tableau_graphql_query": "executing",
        "feedback_learner_node": "generating",
    }
    
    # 合并映射
    all_mappings = {**llm_node_mapping, **visible_node_mapping}
    
    return all_mappings.get(node_name)


def get_stage_display_name(stage: str, language: str = "zh") -> str:
    """获取阶段的显示名称"""
    names_zh = {
        "understanding": "理解问题",
        "mapping": "字段映射",
        "building": "构建查询",
        "executing": "执行分析",
        "generating": "生成洞察",
    }
    
    names_en = {
        "understanding": "Understanding",
        "mapping": "Mapping Fields",
        "building": "Building Query",
        "executing": "Executing Analysis",
        "generating": "Generating Insights",
    }
    
    return names_zh.get(stage, stage) if language == "zh" else names_en.get(stage, stage)
```

### 10.4 SSE 事件发送示例

```python
async def send_sse_event(event_type: str, data: dict):
    """发送 SSE 事件"""
    event_data = {"type": event_type, **data}
    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

# 使用示例
async def stream_workflow():
    # 发送思考阶段
    yield send_sse_event("thinking", {
        "stage": "understanding",
        "name": "理解问题",
        "status": "running"
    })
    
    # 发送流式文本（通过 on_token 回调自动触发）
    async def on_token(token: str):
        yield send_sse_event("token", {"content": token})
    
    # 发送完成事件
    yield send_sse_event("complete", {})
```

### 10.5 完整的 SSE 流式输出流程

```
用户请求
    ↓
POST /api/chat/stream
    ↓
创建 event_generator()
    ↓
注入回调到 RunnableConfig
    ├─ on_token: token → SSE event
    ├─ on_thinking: thinking → SSE event
    ├─ on_node_start: node → thinking event (stage: running)
    └─ on_node_end: node → thinking event (stage: completed)
    ↓
执行 workflow_graph.astream()
    ↓
监听节点执行
    ├─ semantic_understanding_node
    │   ├─ 发送: thinking event (understanding, running)
    │   ├─ 调用: stream_llm_structured()
    │   │   └─ 触发: on_token() → 发送 token events
    │   └─ 发送: thinking event (understanding, completed)
    ├─ field_mapper
    │   ├─ 发送: thinking event (mapping, running)
    │   ├─ 调用: stream_llm_structured()
    │   │   └─ 触发: on_token() → 发送 token events
    │   └─ 发送: thinking event (mapping, completed)
    ├─ query_adapter_node
    │   ├─ 发送: thinking event (building, running)
    │   ├─ 构建查询（无 LLM 调用）
    │   └─ 发送: thinking event (building, completed)
    ├─ tableau_graphql_query
    │   ├─ 发送: thinking event (executing, running)
    │   ├─ 执行查询
    │   ├─ 发送: data event (查询结果)
    │   └─ 发送: thinking event (executing, completed)
    └─ feedback_learner_node
        ├─ 发送: thinking event (generating, running)
        ├─ 生成建议
        ├─ 发送: suggestions event (建议问题)
        └─ 发送: thinking event (generating, completed)
    ↓
发送 complete event
    ↓
关闭 SSE 连接
```

---

**文档版本**: v1.1  
**创建日期**: 2026-02-06  
**最后更新**: 2026-02-06  
**审核状态**: 待审核
