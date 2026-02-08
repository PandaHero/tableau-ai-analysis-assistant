# 实现计划: Analytics Assistant API 层

## 概述

基于已完成的 Agent 层和基础设施层，创建 FastAPI API 层和工作流编排层。

关键架构认知：
- `semantic_parser` 子图已经是完整的端到端流程（15+ 节点），内部包含 field_mapper、error_corrector、feedback_learner 等
- `field_semantic` 是预处理步骤，在 `TableauDataLoader.load_datasource()` 中调用
- 顶层编排只需要：认证 → 数据源解析 → 数据模型加载 → 执行 semantic_parser 子图
- `TableauClient.get_datasource_luid_by_name()` 已存在，可直接使用
- `stream_llm_structured()` 已支持 `on_token`/`on_thinking` 回调，通过 `RunnableConfig.configurable` 注入

## Tasks

- [-] 1. 搭建 API 层基础结构和数据库
  - [-] 1.1 创建 API 目录结构和 FastAPI 应用入口
    - 创建 `analytics_assistant/src/api/__init__.py`
    - 创建 `analytics_assistant/src/api/main.py`：FastAPI 应用、lifespan 管理（初始化/关闭数据库）、CORS 配置（从 `app.yaml` 读取 `api.cors.allowed_origins`）
    - 创建 `analytics_assistant/src/api/dependencies.py`：`get_tableau_username()` 依赖（从 `X-Tableau-Username` 请求头获取）、`get_db()` 依赖
    - 创建 `analytics_assistant/src/api/middleware.py`：统一异常处理器（`exception_handler`）、请求日志中间件（`request_logging_middleware`）
    - 在 `analytics_assistant/config/app.yaml` 中添加 `api` 配置节（port、database.url、cors.allowed_origins、timeout.workflow_execution、timeout.sse_keepalive）
    - _Requirements: 1.1, 1.2, 1.4, 1.6, 1.7, 10.2, 10.3_

  - [ ] 1.2 创建数据库连接管理和 ORM 模型
    - 创建 `analytics_assistant/src/api/database/__init__.py`
    - 创建 `analytics_assistant/src/api/database/connection.py`：`init_database()`、`get_db_session()`、`close_database()`，使用 SQLAlchemy 2.0 异步 API + aiosqlite
    - 创建 `analytics_assistant/src/api/database/models.py`：`Session`（sessions 表）、`UserSettings`（user_settings 表）、`UserFeedback`（user_feedback 表）ORM 模型，包含索引定义
    - 创建 `analytics_assistant/src/api/database/migrations/__init__.py`
    - 创建 `analytics_assistant/src/api/database/migrations/init_db.py`：`create_tables()` 使用 `Base.metadata.create_all`
    - _Requirements: 1.5, 5.1-5.9, 6.1-6.5, 7.1-7.5_

  - [ ] 1.3 创建 Pydantic 请求/响应模型
    - 创建 `analytics_assistant/src/api/models/__init__.py`
    - 创建 `analytics_assistant/src/api/models/chat.py`：`Message`、`ChatRequest`（含 `datasource_name`、`messages`、`language`、`analysis_depth`、`session_id`）
    - 创建 `analytics_assistant/src/api/models/session.py`：`CreateSessionRequest`、`CreateSessionResponse`、`SessionModel`、`GetSessionsResponse`、`UpdateSessionRequest`
    - 创建 `analytics_assistant/src/api/models/settings.py`：`UserSettingsModel`、`UpdateSettingsRequest`
    - 创建 `analytics_assistant/src/api/models/feedback.py`：`FeedbackRequest`
    - 创建 `analytics_assistant/src/api/models/common.py`：`ErrorResponse`、`HealthResponse`
    - _Requirements: 2.1, 5.1-5.5, 6.1-6.2, 7.1_

  - [ ] 1.4 创建健康检查路由并注册所有路由
    - 创建 `analytics_assistant/src/api/routers/__init__.py`
    - 创建 `analytics_assistant/src/api/routers/health.py`：`GET /health` 端点（检查数据库连接）
    - 在 `main.py` 中注册 health 路由、配置异常处理器和日志中间件
    - _Requirements: 1.3_

- [ ] 2. Checkpoint - 验证基础结构
  - 确保 FastAPI 应用可以启动
  - 确保 `/docs` 可访问、`/health` 返回正确响应
  - 确保数据库表可以创建
  - 确保所有测试通过，如有问题请询问用户

- [ ] 3. 实现工作流编排层
  - [ ] 3.1 创建 SSE 回调机制
    - 创建 `analytics_assistant/src/orchestration/workflow/callbacks.py`：`SSECallbacks` 类
    - 实现 `on_token()`、`on_thinking()`、`on_node_start()`、`on_node_end()` 回调方法
    - 实现 `_get_processing_stage()` 节点到 ProcessingStage 映射（参考需求 4 的映射表）
    - 实现 `_get_stage_display_name()` 阶段显示名称（支持中英文）
    - 使用 `asyncio.Queue` 作为事件队列
    - _Requirements: 2.4, 2.5, 4.1-4.6_

  - [ ]* 3.2 编写 ProcessingStage 映射属性测试
    - **Property 5: ProcessingStage Mapping Correctness**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

  - [ ] 3.3 创建 WorkflowExecutor
    - 创建 `analytics_assistant/src/orchestration/workflow/executor.py`：`WorkflowExecutor` 类
    - 构造函数接受 `tableau_username: str`
    - 实现 `execute_stream()` 异步生成器方法，内部流程：
      1. 认证：调用 `get_tableau_auth_async()` 获取 auth token
      2. 数据源解析：使用 `TableauClient.get_datasource_luid_by_name()` 将 datasource_name 转为 LUID
      3. 数据模型加载：使用 `TableauDataLoader.load_datasource()` 加载数据模型和字段语义
      4. 创建 `WorkflowContext`（使用 `create_workflow_config()`）
      5. 注入 SSE 回调到 `RunnableConfig.configurable`（`on_token`、`on_thinking`）
      6. 使用 `semantic_parser_graph.astream()` 执行子图，监听节点事件
    - 实现超时控制（从 `app.yaml` 读取 `api.timeout.workflow_execution`）
    - 实现客户端断开时取消工作流（`asyncio.Task.cancel()`）
    - 更新 `analytics_assistant/src/orchestration/workflow/__init__.py` 导出
    - _Requirements: 8.1, 8.2, 8.3, 8.6, 8.7, 9.1, 9.2, 9.3, 9.4_

  - [ ]* 3.4 编写数据源解析属性测试
    - **Property 18: Datasource Name Resolution**
    - **Validates: Requirements 2.3, 9.1, 9.2**

- [ ] 4. Checkpoint - 验证工作流编排层
  - 确保 WorkflowExecutor 可以实例化
  - 确保 SSECallbacks 正确映射节点到 ProcessingStage
  - 确保所有测试通过，如有问题请询问用户

- [ ] 5. 实现 SSE 流式聊天端点
  - [ ] 5.1 创建 SSE 工具函数
    - 创建 `analytics_assistant/src/api/utils/__init__.py`
    - 创建 `analytics_assistant/src/api/utils/sse.py`：`format_sse_event()` 函数（将事件字典转为 SSE 格式字符串）
    - _Requirements: 2.1_

  - [ ] 5.2 创建聊天路由
    - 创建 `analytics_assistant/src/api/routers/chat.py`：`POST /api/chat/stream` 端点
    - 集成 `HistoryManager.truncate_history()` 进行对话历史裁剪
    - 创建 `WorkflowExecutor(tableau_username)` 并调用 `execute_stream()`
    - 返回 `StreamingResponse`（`media_type="text/event-stream"`，禁用缓冲）
    - 实现心跳保活机制（每 30 秒发送 `: heartbeat\n\n`）
    - 在 `main.py` 中注册路由
    - _Requirements: 2.1-2.12, 3.1-3.6_

  - [ ]* 5.3 编写 SSE 响应类型属性测试
    - **Property 1: SSE Response Content-Type**
    - **Validates: Requirements 2.1**

  - [ ]* 5.4 编写对话历史裁剪属性测试
    - **Property 2: History Truncation Token Limit**
    - **Property 3: History Truncation Order Preservation**
    - **Validates: Requirements 3.2, 3.3, 3.4**

- [ ] 6. 实现会话管理 API
  - [ ] 6.1 创建会话管理路由
    - 创建 `analytics_assistant/src/api/routers/sessions.py`
    - 实现 `POST /api/sessions`：创建新会话（生成 UUID v4）
    - 实现 `GET /api/sessions`：获取用户会话列表（按 `updated_at` 倒序，过滤 `tableau_username`）
    - 实现 `GET /api/sessions/{session_id}`：获取会话详情（含跨用户 403 检查）
    - 实现 `PUT /api/sessions/{session_id}`：更新会话标题和消息（含跨用户 403 检查）
    - 实现 `DELETE /api/sessions/{session_id}`：删除会话（含跨用户 403 检查）
    - 在 `main.py` 中注册路由
    - _Requirements: 5.1-5.9_

  - [ ]* 6.2 编写会话 CRUD 属性测试
    - **Property 9: Session CRUD Round-Trip**
    - **Property 10: Session List Ordering**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

  - [ ]* 6.3 编写认证和数据隔离属性测试
    - **Property 11: User Data Isolation**
    - **Property 12: Authentication Requirement**
    - **Property 13: Cross-User Access Prevention**
    - **Property 14: Non-Existent Resource Returns 404**
    - **Validates: Requirements 5.6, 5.7, 5.8, 5.9, 6.4, 6.5, 7.5, 9.2**

- [ ] 7. 实现用户设置和反馈 API
  - [ ] 7.1 创建用户设置路由
    - 创建 `analytics_assistant/src/api/routers/settings.py`
    - 实现 `GET /api/settings`：获取用户设置（首次访问自动创建默认值）
    - 实现 `PUT /api/settings`：更新用户设置（部分更新，只更新非 None 字段）
    - 在 `main.py` 中注册路由
    - _Requirements: 6.1-6.5_

  - [ ] 7.2 创建用户反馈路由
    - 创建 `analytics_assistant/src/api/routers/feedback.py`
    - 实现 `POST /api/feedback`：提交用户反馈（关联 `tableau_username`）
    - 在 `main.py` 中注册路由
    - _Requirements: 7.1-7.5_

  - [ ]* 7.3 编写设置往返属性测试
    - **Property 15: Settings Round-Trip with Auto-Creation**
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [ ]* 7.4 编写反馈持久化属性测试
    - **Property 16: Feedback Persistence with User Association**
    - **Validates: Requirements 7.1, 7.4**

- [ ] 8. Checkpoint - 验证所有 API 端点
  - 确保所有 CRUD 端点正常工作
  - 确保认证和数据隔离正确
  - 确保所有测试通过，如有问题请询问用户

- [ ] 9. 错误处理完善和安全加固
  - [ ] 9.1 完善统一错误处理
    - 确保 `middleware.py` 中的异常处理器覆盖所有异常类型（HTTP 异常、验证错误、业务异常、未知异常）
    - 确保错误响应不暴露内部细节（堆栈、连接字符串、API Key）
    - 确保所有异常记录完整堆栈（使用 `logger.exception`）
    - _Requirements: 10.1, 10.2_

  - [ ]* 9.2 编写错误消息安全性属性测试
    - **Property 19: Error Message Safety**
    - **Validates: Requirements 10.2**

- [ ] 10. Final Checkpoint - 确保所有测试通过
  - 运行所有单元测试和属性测试
  - 确保所有测试通过，如有问题请询问用户

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using `hypothesis`
- 所有代码必须遵循 `coding-standards.md` 规范
- 配置参数必须放入 `app.yaml`，禁止硬编码
- 导入必须在文件顶部，禁止延迟导入（`__init__` 获取单例除外）
- Pydantic 模型放在 `api/models/` 目录，ORM 模型放在 `api/database/models.py`
- 使用 `List[str]` 而非 `list[str]`，使用 `Optional[X]` 而非 `X | None`
