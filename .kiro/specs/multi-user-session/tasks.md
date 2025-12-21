# Implementation Plan: Multi-User Session Management

## Overview

实现多用户会话管理系统，包括后端认证、会话管理、前端集成三个阶段。

## Tasks

- [ ] 1. 数据库和基础设施
  - [ ] 1.1 创建数据库 schema 和迁移脚本
    - 创建 `tableau_assistant/src/infra/storage/schema.sql`
    - 包含 users、sessions、session_messages 表
    - 添加必要索引
    - _Requirements: 3.1, 3.4_

  - [ ] 1.2 实现 SessionRepository 数据访问层
    - 创建 `tableau_assistant/src/infra/storage/session_repository.py`
    - 实现 CRUD 操作
    - 使用 aiosqlite 异步访问
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 1.3 写属性测试：Session CRUD 一致性
    - **Property 4: Session CRUD Consistency**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

- [ ] 2. 认证系统
  - [ ] 2.1 实现 JWT 工具函数
    - 创建 `tableau_assistant/src/api/auth/jwt_utils.py`
    - 实现 create_token、verify_token、decode_token
    - 配置过期时间和密钥
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]* 2.2 写属性测试：JWT Token Round-Trip
    - **Property 1: JWT Token Round-Trip**
    - **Validates: Requirements 1.1**

  - [ ] 2.3 实现 AuthMiddleware
    - 创建 `tableau_assistant/src/api/middleware/auth.py`
    - 处理 JWT 验证和匿名用户
    - 注入 user_id 到 request.state
    - _Requirements: 1.1, 1.3, 1.4_

  - [ ] 2.4 实现 Auth API Router
    - 创建 `tableau_assistant/src/api/auth/router.py`
    - POST /api/auth/login - 登录
    - POST /api/auth/logout - 登出
    - GET /api/auth/me - 获取当前用户
    - _Requirements: 1.1, 1.2, 1.5_

- [ ] 3. Checkpoint - 确保认证系统测试通过
  - 确保所有测试通过，如有问题请询问用户

- [ ] 4. 会话管理
  - [ ] 4.1 实现 SessionManager 核心类
    - 创建 `tableau_assistant/src/orchestration/session/manager.py`
    - 实现会话 CRUD 操作
    - 实现所有权验证
    - 集成 LangGraph SqliteSaver
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3_

  - [ ]* 4.2 写属性测试：Session Isolation
    - **Property 2: Session Isolation**
    - **Validates: Requirements 2.2, 2.3, 2.4**

  - [ ]* 4.3 写属性测试：Checkpoint State Round-Trip
    - **Property 3: Checkpoint State Round-Trip**
    - **Validates: Requirements 3.5, 3.6**

  - [ ] 4.4 实现会话级锁机制
    - 在 SessionManager 中添加 _locks 字典
    - 实现 acquire_lock、release_lock 方法
    - 添加超时处理
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 4.5 写属性测试：Concurrent Request Handling
    - **Property 5: Concurrent Request Handling**
    - **Validates: Requirements 6.1, 6.2**

  - [ ] 4.6 实现 Session API Router
    - 创建 `tableau_assistant/src/api/sessions/router.py`
    - GET /api/sessions - 列出会话
    - POST /api/sessions - 创建会话
    - GET /api/sessions/{id} - 获取会话详情
    - DELETE /api/sessions/{id} - 删除会话
    - PUT /api/sessions/{id}/archive - 归档会话
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [ ] 5. Checkpoint - 确保会话管理测试通过
  - 确保所有测试通过，如有问题请询问用户

- [ ] 6. 增强 Chat API
  - [ ] 6.1 修改 chat.py 集成 SessionManager
    - 使用复合 thread_id (user_id:session_id)
    - 添加会话锁获取/释放
    - 处理 409 Conflict 响应
    - _Requirements: 2.1, 6.1, 6.2_

  - [ ] 6.2 修改 WorkflowExecutor 支持复合 thread_id
    - 更新 executor.py 中的 thread_id 处理
    - 确保 checkpointer 使用正确的 key
    - _Requirements: 3.2, 3.3, 3.4_

- [ ] 7. 会话清理
  - [ ] 7.1 实现会话清理任务
    - 创建 `tableau_assistant/src/orchestration/session/cleanup.py`
    - 实现 archive_old_sessions (30天)
    - 实现 delete_archived_sessions (90天)
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 7.2 写属性测试：Session Cleanup by Age
    - **Property 6: Session Cleanup by Age**
    - **Validates: Requirements 7.1, 7.2**

  - [ ] 7.3 配置定时任务
    - 使用 APScheduler 或 asyncio 定时器
    - 可配置清理间隔
    - _Requirements: 7.4_

- [ ] 8. Checkpoint - 确保后端测试通过
  - 确保所有测试通过，如有问题请询问用户

- [ ] 9. 前端认证集成
  - [ ] 9.1 实现 authStore
    - 创建 `tableau_assistant/frontend/src/stores/auth.ts`
    - 管理 token、user 状态
    - 实现 login、logout、getAuthHeader
    - localStorage 持久化
    - _Requirements: 1.1, 1.5_

  - [ ] 9.2 实现登录页面组件
    - 创建 `tableau_assistant/frontend/src/components/LoginPage.vue`
    - 用户名/密码表单
    - 错误提示
    - 匿名继续选项
    - _Requirements: 1.1, 1.4_

  - [ ] 9.3 更新 API 客户端添加认证头
    - 修改 `tableau_assistant/frontend/src/api/client.ts`
    - 自动添加 Authorization header
    - 处理 401 响应跳转登录
    - _Requirements: 1.3_

- [ ] 10. 前端会话管理
  - [ ] 10.1 更新 sessionStore 与后端同步
    - 修改 `tableau_assistant/frontend/src/stores/session.ts`
    - 从后端获取会话列表
    - 创建/删除会话调用 API
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ] 10.2 实现会话列表侧边栏
    - 创建 `tableau_assistant/frontend/src/components/SessionSidebar.vue`
    - 显示会话列表
    - 支持切换、删除、归档
    - _Requirements: 4.1, 4.3, 4.5_

  - [ ] 10.3 更新 useStreaming 传递 session_id
    - 修改 `tableau_assistant/frontend/src/composables/useStreaming.ts`
    - 请求中包含 session_id
    - 处理 409 Conflict 错误
    - _Requirements: 6.2_

- [ ] 11. Checkpoint - 确保前端集成测试通过
  - 确保所有测试通过，如有问题请询问用户

- [ ] 12. 集成和注册路由
  - [ ] 12.1 注册所有新路由到 FastAPI app
    - 修改 `tableau_assistant/src/main.py`
    - 添加 AuthMiddleware
    - 注册 auth_router、sessions_router
    - _Requirements: 1.1, 4.1_

  - [ ] 12.2 更新 OpenAPI 文档
    - 添加认证说明
    - 更新 API 示例
    - _Requirements: 文档_

- [ ] 13. Final Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户

## Notes

- 任务标记 `*` 为可选测试任务
- 每个 Checkpoint 确保阶段性功能完整
- 属性测试使用 Hypothesis 库
- 前端测试可使用 Vitest + Vue Test Utils
