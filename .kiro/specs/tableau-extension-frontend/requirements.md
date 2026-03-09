# 需求文档：Tableau Extension 前端开发

## 介绍

本文档定义了 Tableau AI Assistant Extension 前端的功能需求。该前端是一个嵌入在 Tableau Dashboard 中的插件，为用户提供基于 AI 的数据分析对话界面。前端通过 HTTPS 与后端 FastAPI 服务通信，使用 Tableau Extensions API 获取 Dashboard 上下文信息。

## 术语表

- **Extension**：Tableau 插件，嵌入在 Dashboard 中运行的 Web 应用
- **Dashboard**：Tableau 仪表板，包含数据可视化和交互组件
- **Datasource**：Tableau 数据源，Extension 需要从中获取字段和数据
- **SSE**：Server-Sent Events，服务器推送事件，用于实时流式响应
- **Boost_Prompt**：快捷提示词，预设的常用问题模板
- **Session**：会话，一次完整的对话历史记录
- **Message**：消息，对话中的单条用户或 AI 回复
- **Backend_API**：后端 FastAPI 服务，提供聊天、会话管理等接口
- **Tableau_API**：Tableau Extensions API，用于获取 Dashboard 上下文
- **Chat_UI**：聊天用户界面，显示对话历史和输入框
- **Settings_Panel**：设置面板，用户配置语言、分析深度等选项
- **History_Panel**：历史面板，显示和管理历史会话列表

## 需求

### 需求 1：Extension 初始化和认证

**用户故事**：作为 Tableau 用户，我希望打开 Dashboard 时 Extension 能自动初始化并获取我的身份信息，以便系统识别我的会话和设置。

#### 验收标准

1. WHEN Extension 加载时，THE Extension SHALL 调用 Tableau API 初始化（`tableau.extensions.initializeAsync()`）
2. WHEN 初始化成功后，THE Extension SHALL 获取当前 Tableau 用户名（`tableau.extensions.environment.username`）
3. THE Extension SHALL 将 Tableau 用户名存储在前端状态中，用于后续 API 请求
4. WHEN 初始化失败时，THE Extension SHALL 显示错误提示并记录日志
5. THE Extension SHALL 在所有 Backend_API 请求的请求头中包含 `X-Tableau-Username` 字段

### 需求 2：数据源选择

**用户故事**：作为用户，我希望能够选择 Dashboard 中的数据源，以便 AI 基于正确的数据进行分析。

#### 验收标准

1. WHEN Extension 初始化完成后，THE Extension SHALL 调用 Tableau API 获取 Dashboard 中的所有数据源列表（`tableau.extensions.dashboardContent.dashboard.worksheets[].getDataSourcesAsync()`）
2. THE Extension SHALL 在 UI 中显示数据源选择下拉框，列出所有可用数据源名称
3. WHEN 用户选择数据源时，THE Extension SHALL 更新当前选中的数据源状态
4. THE Extension SHALL 在聊天请求中包含当前选中的数据源名称（`datasource_name` 字段）
5. IF Dashboard 中没有数据源，THEN THE Extension SHALL 显示提示信息"未找到可用数据源"
6. THE Extension SHALL 在 UI 顶部显示当前选中的数据源名称

### 需求 3：聊天界面和消息显示

**用户故事**：作为用户，我希望有一个清晰的聊天界面，能够看到我的问题和 AI 的回复，以便进行流畅的对话。

#### 验收标准

1. THE Chat_UI SHALL 包含消息列表区域和输入框区域
2. THE Chat_UI SHALL 按时间顺序显示所有消息（用户消息和 AI 回复）
3. THE Chat_UI SHALL 区分用户消息和 AI 消息的视觉样式（如头像、背景色、对齐方式）
4. THE Chat_UI SHALL 支持 Markdown 格式渲染（如标题、列表、代码块、表格）
5. THE Chat_UI SHALL 支持代码块语法高亮显示
6. WHEN 新消息添加时，THE Chat_UI SHALL 自动滚动到最新消息
7. THE Chat_UI SHALL 显示消息的时间戳
8. WHEN 消息列表为空时，THE Chat_UI SHALL 显示欢迎提示和使用说明

### 需求 4：用户输入和消息发送

**用户故事**：作为用户，我希望能够输入问题并发送给 AI，以便获得数据分析结果。

#### 验收标准

1. THE Chat_UI SHALL 包含文本输入框，支持多行输入
2. WHEN 用户按下 Enter 键（非 Shift+Enter）时，THE Extension SHALL 发送消息
3. WHEN 用户按下 Shift+Enter 时，THE Extension SHALL 在输入框中插入换行符
4. THE Chat_UI SHALL 包含发送按钮，点击时发送消息
5. WHEN 输入框为空或仅包含空白字符时，THE Extension SHALL 禁用发送按钮
6. WHEN 消息发送中时，THE Extension SHALL 禁用输入框和发送按钮，防止重复发送
7. WHEN 消息发送成功后，THE Extension SHALL 清空输入框
8. IF 未选择数据源，THEN THE Extension SHALL 阻止发送并提示"请先选择数据源"

### 需求 5：SSE 流式响应处理

**用户故事**：作为用户，我希望 AI 的回复能够实时显示，而不是等待全部生成完成，以便更快地看到结果。

#### 验收标准

1. WHEN 用户发送消息时，THE Extension SHALL 调用 `POST /api/chat/stream` 端点建立 SSE 连接
2. THE Extension SHALL 使用 EventSource 或 Fetch API 接收 SSE 事件流
3. WHEN 接收到 SSE 事件时，THE Extension SHALL 解析事件数据（JSON 格式）
4. WHEN 事件类型为 `token` 时，THE Extension SHALL 将 token 追加到当前 AI 消息的末尾
5. WHEN 事件类型为 `done` 时，THE Extension SHALL 标记消息生成完成
6. WHEN 事件类型为 `error` 时，THE Extension SHALL 显示错误提示
7. THE Extension SHALL 在 AI 回复生成过程中显示加载指示器（如闪烁光标）
8. IF SSE 连接断开或超时，THEN THE Extension SHALL 显示错误提示并允许用户重试

### 需求 6：Boost Prompt 快捷提示

**用户故事**：作为用户，我希望能够快速选择常用问题模板，以便更高效地提问。

#### 验收标准

1. THE Extension SHALL 在 Chat_UI 中显示 Boost Prompt 按钮或面板
2. THE Extension SHALL 预设至少 5 个常用问题模板（如"数据概览"、"趋势分析"、"异常检测"等）
3. WHEN 用户点击 Boost Prompt 时，THE Extension SHALL 将模板文本填充到输入框
4. THE Extension SHALL 支持用户自定义 Boost Prompt（添加、编辑、删除）
5. THE Extension SHALL 将自定义 Boost Prompt 存储在浏览器本地存储（localStorage）
6. WHEN 消息列表为空时，THE Extension SHALL 在欢迎界面显示推荐的 Boost Prompt
7. THE Extension SHALL 支持 Boost Prompt 的分类显示（如"数据探索"、"可视化建议"等）

### 需求 7：多语言支持

**用户故事**：作为用户，我希望能够切换界面语言，以便使用我熟悉的语言进行交互。

#### 验收标准

1. THE Extension SHALL 支持中文（zh）和英文（en）两种语言
2. THE Extension SHALL 在 Settings_Panel 中提供语言切换选项
3. WHEN 用户切换语言时，THE Extension SHALL 更新所有 UI 文本为选中的语言
4. THE Extension SHALL 将语言设置通过 `PUT /api/settings` 保存到后端
5. WHEN Extension 初始化时，THE Extension SHALL 从 `GET /api/settings` 加载用户的语言设置
6. THE Extension SHALL 在聊天请求中包含当前语言参数（`language` 字段）
7. THE Extension SHALL 翻译所有 UI 文本（按钮、标签、提示信息、错误消息等）

### 需求 8：分析深度选择

**用户故事**：作为用户，我希望能够选择分析的详细程度，以便根据需求获得快速概览或深入分析。

#### 验收标准

1. THE Extension SHALL 在 Settings_Panel 中提供分析深度选择选项
2. THE Extension SHALL 支持两种分析深度：标准分析（detailed）和深入分析（comprehensive）
3. WHEN 用户切换分析深度时，THE Extension SHALL 更新当前设置状态
4. THE Extension SHALL 将分析深度设置通过 `PUT /api/settings` 保存到后端
5. WHEN Extension 初始化时，THE Extension SHALL 从 `GET /api/settings` 加载用户的分析深度设置
6. THE Extension SHALL 在聊天请求中包含当前分析深度参数（`analysis_depth` 字段）
7. THE Extension SHALL 在 UI 中显示当前选中的分析深度

### 需求 9：会话管理

**用户故事**：作为用户，我希望能够保存和加载历史对话，以便继续之前的分析或回顾历史结果。

#### 验收标准

1. THE Extension SHALL 在 History_Panel 中显示用户的所有历史会话列表
2. WHEN Extension 初始化时，THE Extension SHALL 调用 `GET /api/sessions` 加载会话列表
3. THE Extension SHALL 显示每个会话的标题和最后更新时间
4. WHEN 用户点击历史会话时，THE Extension SHALL 调用 `GET /api/sessions/{id}` 加载会话详情
5. WHEN 加载会话后，THE Extension SHALL 在 Chat_UI 中显示该会话的所有消息
6. THE Extension SHALL 支持创建新会话（调用 `POST /api/sessions`）
7. THE Extension SHALL 支持删除会话（调用 `DELETE /api/sessions/{id}`）
8. THE Extension SHALL 支持重命名会话标题（调用 `PUT /api/sessions/{id}`）
9. WHEN 用户发送新消息时，THE Extension SHALL 自动保存消息到当前会话（调用 `PUT /api/sessions/{id}`）
10. THE Extension SHALL 支持会话列表的分页加载（使用 `offset` 和 `limit` 参数）

### 需求 10：用户反馈

**用户故事**：作为用户，我希望能够对 AI 的回复进行评价，以便帮助改进系统质量。

#### 验收标准

1. THE Extension SHALL 在每条 AI 消息下方显示反馈按钮（点赞和点踩）
2. WHEN 用户点击反馈按钮时，THE Extension SHALL 调用 `POST /api/feedback` 提交反馈
3. THE Extension SHALL 在反馈请求中包含消息 ID（`message_id`）和反馈类型（`type`）
4. THE Extension SHALL 支持用户添加反馈原因（`reason`）和评论（`comment`）
5. WHEN 反馈提交成功后，THE Extension SHALL 更新按钮状态为已反馈
6. THE Extension SHALL 防止用户对同一消息重复提交相同类型的反馈
7. WHEN 反馈提交失败时，THE Extension SHALL 显示错误提示

### 需求 11：设置面板

**用户故事**：作为用户，我希望有一个集中的设置面板，以便管理我的偏好设置。

#### 验收标准

1. THE Extension SHALL 提供设置按钮，点击后打开 Settings_Panel
2. THE Settings_Panel SHALL 包含语言选择、分析深度选择、主题选择等选项
3. THE Settings_Panel SHALL 支持主题切换（浅色、深色、跟随系统）
4. THE Settings_Panel SHALL 支持显示/隐藏思考过程的开关（`show_thinking_process`）
5. WHEN 用户修改设置时，THE Extension SHALL 调用 `PUT /api/settings` 保存设置
6. THE Settings_Panel SHALL 显示当前设置的保存状态（保存中、已保存、保存失败）
7. THE Extension SHALL 支持关闭 Settings_Panel（点击关闭按钮或点击外部区域）

### 需求 12：响应式设计

**用户故事**：作为用户，我希望 Extension 能够适配不同尺寸的 Dashboard 面板，以便在各种屏幕上都能正常使用。

#### 验收标准

1. THE Extension SHALL 使用响应式布局，适配不同宽度和高度的容器
2. WHEN 容器宽度小于 768px 时，THE Extension SHALL 切换到移动端布局
3. THE Extension SHALL 在移动端布局中隐藏或折叠次要功能（如 History_Panel）
4. THE Extension SHALL 确保输入框和发送按钮在所有尺寸下都可见和可用
5. THE Extension SHALL 使用相对单位（如 rem、%、vh/vw）而非固定像素
6. THE Extension SHALL 在容器尺寸变化时自动调整布局
7. THE Extension SHALL 确保文本在小屏幕上可读（最小字体 12px）

### 需求 13：错误处理和用户提示

**用户故事**：作为用户，我希望在出现错误时能够看到清晰的提示信息，以便了解问题并采取行动。

#### 验收标准

1. WHEN API 请求失败时，THE Extension SHALL 显示错误提示消息
2. THE Extension SHALL 区分不同类型的错误（网络错误、认证错误、服务器错误等）
3. WHEN 网络连接断开时，THE Extension SHALL 显示"网络连接失败，请检查网络"
4. WHEN 认证失败时，THE Extension SHALL 显示"认证失败，请重新登录"
5. WHEN 服务器错误时，THE Extension SHALL 显示"服务器错误，请稍后重试"
6. THE Extension SHALL 提供重试按钮，允许用户重新发送失败的请求
7. THE Extension SHALL 在控制台记录详细的错误日志，便于调试
8. THE Extension SHALL 使用 Toast 或 Snackbar 组件显示临时提示信息

### 需求 14：性能优化

**用户故事**：作为用户，我希望 Extension 加载快速、响应流畅，以便获得良好的使用体验。

#### 验收标准

1. THE Extension SHALL 在 2 秒内完成首屏加载（包括初始化和设置加载）
2. THE Extension SHALL 使用虚拟滚动技术处理大量消息历史（超过 100 条）
3. THE Extension SHALL 对 Markdown 渲染进行防抖处理，避免频繁重渲染
4. THE Extension SHALL 使用懒加载技术加载历史会话列表
5. THE Extension SHALL 缓存已加载的会话数据，避免重复请求
6. THE Extension SHALL 使用 Web Worker 处理大量数据的计算任务（如有需要）
7. THE Extension SHALL 压缩和优化静态资源（JS、CSS、图片）
8. THE Extension SHALL 使用 CDN 加载第三方库（如 Tableau API、UI 库）

### 需求 15：安全性

**用户故事**：作为用户，我希望我的数据和隐私得到保护，以便安全地使用系统。

#### 验收标准

1. THE Extension SHALL 使用 HTTPS 协议与 Backend_API 通信
2. THE Extension SHALL 在渲染 Markdown 时防止 XSS 攻击（使用安全的渲染库）
3. THE Extension SHALL 不在前端存储敏感信息（如 API Key、密码）
4. THE Extension SHALL 使用 Content Security Policy（CSP）限制资源加载
5. THE Extension SHALL 验证所有用户输入，防止注入攻击
6. THE Extension SHALL 在开发环境使用自签名证书支持 HTTPS
7. THE Extension SHALL 在生产环境使用有效的 SSL 证书

### 需求 16：可访问性

**用户故事**：作为有特殊需求的用户，我希望 Extension 支持辅助技术，以便我也能正常使用。

#### 验收标准

1. THE Extension SHALL 为所有交互元素提供 ARIA 标签
2. THE Extension SHALL 支持键盘导航（Tab、Enter、Esc 等）
3. THE Extension SHALL 确保颜色对比度符合 WCAG AA 标准
4. THE Extension SHALL 为图标和按钮提供文本替代（alt、title、aria-label）
5. THE Extension SHALL 支持屏幕阅读器（如 NVDA、JAWS）
6. THE Extension SHALL 在焦点变化时提供视觉反馈
7. THE Extension SHALL 确保所有功能都可以通过键盘操作

### 需求 17：开发环境配置

**用户故事**：作为开发者，我希望能够快速搭建开发环境，以便开始前端开发工作。

#### 验收标准

1. THE Extension SHALL 使用 Vite 作为构建工具，支持热更新
2. THE Extension SHALL 配置 HTTPS 开发服务器（使用自签名证书）
3. THE Extension SHALL 在 `package.json` 中定义所有依赖和脚本命令
4. THE Extension SHALL 提供开发环境配置文件（`.env.development`）
5. THE Extension SHALL 提供生产环境配置文件（`.env.production`）
6. THE Extension SHALL 配置 ESLint 和 Prettier 进行代码检查和格式化
7. THE Extension SHALL 配置 TypeScript 类型检查
8. THE Extension SHALL 提供 README 文档，说明如何启动开发服务器

### 需求 18：构建和部署

**用户故事**：作为开发者，我希望能够构建生产版本并部署到服务器，以便用户使用。

#### 验收标准

1. THE Extension SHALL 支持构建生产版本（`npm run build`）
2. THE Extension SHALL 将构建产物输出到 `analytics_assistant/public/dist/` 目录
3. THE Extension SHALL 在构建时进行代码压缩和优化
4. THE Extension SHALL 生成 Source Map 文件，便于调试
5. THE Extension SHALL 更新 `manifest.trex` 中的 `source-location` 指向构建后的入口文件
6. THE Extension SHALL 支持环境变量配置（如 API 基础 URL）
7. THE Extension SHALL 提供部署文档，说明如何部署到 HTTPS 服务器

