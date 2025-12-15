# Implementation Plan

## Phase 1: 核心对话功能

- [x] 1. 项目基础设置



  - [x] 1.1 配置 Tailwind CSS 和主题变量



    - 安装 Tailwind CSS 依赖
    - 配置 Tableau 配色变量（#1F77B4 等）
    - 设置深色/浅色主题 CSS 变量


    - _Requirements: 16.1, 16.6_
  - [-] 1.2 创建类型定义文件


    - 创建 `types/message.ts` 消息类型
    - 创建 `types/settings.ts` 设置类型
    - 创建 `types/insight.ts` 洞察类型
    - _Requirements: 2.1, 2.2_

- [ ] 2. 布局组件实现（两页面结构）
  - [x] 2.1 实现页面路由和状态管理


    - 首页（WelcomePage）和对话页面（ChatPage）切换
    - 使用 Vue Router 或组件条件渲染
    - 页面状态：`currentPage: 'home' | 'chat'`
    - _Requirements: 1.1, 1.4_

  - [x] 2.2 实现 LayoutContainer 三区域布局


    - HeaderBar (48px) + ContentArea (flex:1) + InputArea (64px)
    - 响应式断点：standard/compact/minimal
    - _Requirements: 1.1, 1.4, 15.1, 15.2, 15.3_
  - [ ]* 2.3 写属性测试：布局响应式适配
    - **Property 1: 布局响应式适配**

    - **Validates: Requirements 1.4, 15.1, 15.2, 15.3**
  - [x] 2.4 实现 HeaderBar 组件（两种状态）


    - 首页状态：Logo + 标题 + 设置按钮（无返回按钮）
    - 对话页面状态：返回按钮 + 设置按钮（无 Logo、无标题）

    - 返回按钮点击：回到首页，清空当前对话
    - _Requirements: 1.2_
  - [x] 2.5 实现 WelcomePage 首页组件

    - 欢迎信息卡片
    - 示例问题列表（可点击，填入输入框并发送）
    - _Requirements: 1.1_
  - [x] 2.6 实现 InputArea 组件

    - 多行文本输入框（自动扩展）
    - 发送按钮（禁用状态处理）
    - Enter 发送 / Shift+Enter 换行
    - 字符计数器（超过 2000 字符）
    - 发送后触发页面切换（首页 → 对话页面）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9_
  - [ ]* 2.7 写属性测试：输入验证规则
    - **Property 3: 输入验证规则**
    - **Validates: Requirements 2.6, 2.7, 8.5**

- [ ] 3. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户

- [ ] 4. 状态管理实现
  - [x] 4.1 实现 chatStore 对话状态


    - messages 数组管理
    - currentResponse 流式响应
    - isProcessing / processingStage 状态
    - sendMessage / clearMessages actions
    - currentPage 页面状态（'home' | 'chat'）
    - goToChat / goToHome actions（页面切换）
    - _Requirements: 2.1, 2.2, 11.1_
  - [x] 4.2 实现 sessionStore 会话状态


    - sessionId 生成（UUID v4）
    - localStorage 持久化
    - 会话归档逻辑（24小时）
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.6_
  - [ ]* 4.3 写属性测试：Session ID 格式和序列化
    - **Property 17: Session ID 格式**
    - **Property 18: Session 序列化 Round-Trip**
    - **Validates: Requirements 12.1, 12.6**



  - [x] 4.4 实现 uiStore UI 状态
    - theme 主题管理
    - layoutMode 响应式布局
    - windowWidth 监听
    - _Requirements: 15.1, 16.6_
  - [x] 4.5 实现 settingsStore 设置状态



    - language / analysisDepth / selectedModel / theme
    - customModels 自定义模型列表
    - localStorage 持久化
    - _Requirements: 新增设置功能_



- [x] 5. 对话组件实现



  - [x] 5.1 实现 ChatContainer 和 MessageList

    - 消息列表渲染
    - 自动滚动到最新消息
    - _Requirements: 1.3_
  - [x] 5.2 实现 UserMessage 组件


    - 右对齐、蓝色背景、白色文字
    - 相对时间戳显示
    - _Requirements: 2.1, 2.4_
  - [ ]* 5.3 写属性测试：相对时间戳格式化
    - **Property 4: 相对时间戳格式化**

    - **Validates: Requirements 2.4**
  - [x] 5.4 实现 AIMessage 组件（思维链可视化）


    - 左对齐、白色背景、灰色边框
    - 支持多轮重规划展示：

      - 每轮分析卡片：❓问题标题 → 📊查询结果 → 💡发现
      - 💭思考气泡：显示 Replanner.reason，解释下一轮原因
      - 连接线 │▼：视觉连接轮次，表示因果关系
      - 分隔线 ════：区分分析过程和最终结论
      - 📝总结：汇总所有发现（最后一轮输出）
      - 💬继续探索：推荐问题
    - 单轮场景简化展示（不显示问题标题和思考气泡）
    - _Requirements: 2.2, 3.1, 3.2, 3.3, 3.4, 3.5_
  - [x] 5.5 实现 ThinkingIndicator 思考指示器


    - 三点动画 + 状态文字
    - 阶段切换：理解问题 → 构建查询 → 执行分析 → 生成洞察
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 6. Checkpoint - 确保所有测试通过

  - 确保所有测试通过，如有问题请询问用户

- [-] 7. Markdown 渲染实现

  - [x] 7.1 实现 MarkdownRenderer 组件

    - 配置 markdown-it（禁用 HTML、启用 linkify）
    - 集成 highlight.js 语法高亮（json、sql、python、javascript）
    - GFM 表格支持
    - _Requirements: 2.3, 17.1, 17.2, 17.3_
  - [ ]* 7.2 写属性测试：Markdown 渲染正确性
    - **Property 5: Markdown 渲染正确性**
    - **Validates: Requirements 2.3, 17.1, 17.4**

  - [ ] 7.3 实现 XSS 防护
    - 转义危险标签（script、onerror 等）
    - _Requirements: 14.5, 17.5_
  - [ ]* 7.4 写属性测试：XSS 向量转义
    - **Property 21: XSS 向量转义**
    - **Validates: Requirements 14.5, 17.5**





- [ ] 8. 流式输出实现
  - [ ] 8.1 扩展 SSEClient 流式客户端
    - 支持 token / node_start / node_complete / complete / error 事件
    - 请求参数包含 `analysis_depth` 和 `language`（从 settingsStore 获取）
    - 超时处理（60秒）
    - 断线重连（5秒）
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [ ]* 8.2 写属性测试：SSE 事件状态更新
    - **Property 15: SSE 事件状态更新**
    - **Validates: Requirements 11.1, 11.2, 11.3**
  - [ ] 8.3 实现流式 Markdown 渲染
    - 逐 token 追加渲染
    - 保证最终结构与一次性渲染一致
    - _Requirements: 11.7_
  - [x]* 8.4 写属性测试：流式 Markdown 渲染一致性


    - **Property 16: 流式 Markdown 渲染一致性**
    - **Validates: Requirements 11.7**




- [ ] 9. 错误处理实现
  - [ ] 9.1 实现 ErrorMessage 组件
    - 红色背景、红色边框、错误图标
    - 重试按钮（可选）
    - _Requirements: 14.6_
  - [x] 9.2 实现 HTTP 错误消息映射

    - 400/401/403/404/500 状态码映射
    - _Requirements: 14.1, 14.2, 14.3, 14.4_
  - [ ]* 9.3 写属性测试：HTTP 错误消息映射
    - **Property 20: HTTP 错误消息映射**
    - **Validates: Requirements 14.2**


- [ ] 10. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户

## Phase 2: 数据展示增强

- [ ] 11. 数据表格实现
  - [x] 11.1 实现 DataTable 组件（带分页）


    - 表头 + 数据行渲染
    - 分页功能：每页 10 条，翻页控件 `◀ 1 / 3 ▶`
    - 显示总条数 `共 N 条`
    - 数据 ≤ 10 条时不显示分页控件
    - 水平滚动（列数 > 5）
    - 空状态提示"暂无数据"
    - _Requirements: 4.1, 4.2, 4.3, 4.7_
  - [ ]* 11.2 写属性测试：表格分页行为
    - **Property 6: 表格分页行为**
    - **Validates: Requirements 4.2, 4.3, 4.7**

  - [ ] 11.3 实现表格排序功能
    - 点击表头排序（升序 → 降序 → 取消）
    - _Requirements: 4.4_
  - [ ]* 11.4 写属性测试：表格排序正确性
    - **Property 7: 表格排序正确性**

    - **Validates: Requirements 4.4**
  - [ ] 11.5 实现数值格式化
    - 千分位分隔符、小数保留 2 位、负数红色
    - _Requirements: 4.6_
  - [x]* 11.6 写属性测试：数值格式化正确性

    - **Property 8: 数值格式化正确性**
    - **Validates: Requirements 4.6**
  - [ ] 11.7 实现 CSV 导出功能
    - 生成 CSV 文件并下载（导出全部数据，不受分页限制）
    - 文件名格式：tableau_data_YYYYMMDD_HHmmss.csv
    - _Requirements: 4.5_
  - [ ]* 11.8 写属性测试：CSV 导出 Round-Trip
    - **Property 9: CSV 导出 Round-Trip**
    - **Validates: Requirements 4.5**

- [ ] 12. 洞察卡片实现
  - [x] 12.1 实现 InsightCards 组件


    - 垂直卡片列表
    - 类型图标和颜色（发现/异常/建议）
    - 按优先级排序
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [ ]* 12.2 写属性测试：洞察卡片排序与类型映射
    - **Property 11: 洞察卡片排序与类型映射**


    - **Validates: Requirements 6.3, 6.4**

- [x] 13. 推荐问题实现


  - [ ] 13.1 实现 SuggestedQuestions 组件
    - 可点击的问题芯片
    - 显示前 3 个 + "更多"按钮
    - 点击后填入输入框并发送
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_



  - [ ]* 13.2 写属性测试：推荐问题显示数量
    - **Property 13: 推荐问题显示数量**
    - **Validates: Requirements 3.5, 9.5**



- [ ] 14. 技术细节实现
  - [ ] 14.1 实现 TechDetails 可折叠组件
    - 默认折叠，点击展开
    - 显示 VizQL 查询 JSON（格式化）
    - 执行时间、返回行数
    - 复制按钮
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [ ]* 14.2 写属性测试：JSON Round-Trip 一致性
    - **Property 14: JSON Round-Trip 一致性**
    - **Validates: Requirements 10.6**

- [x] 15. Checkpoint - 确保所有测试通过


  - 确保所有测试通过，如有问题请询问用户

## Phase 3: 设置功能实现


- [ ] 16. 设置面板实现
  - [x] 16.1 实现 SettingsPanel 组件

    - 右侧滑出面板（320px 宽度）
    - 遮罩层 + 关闭按钮
    - 响应式：窗口 < 480px 时全屏

    - _Requirements: 新增设置功能_
  - [ ] 16.2 实现数据源选择
    - 下拉选择 Tableau 数据源
    - 从 Tableau Extensions API 获取列表

    - _Requirements: 13.1, 13.2_
  - [x] 16.3 实现语言设置
    - 中文 / 英文 切换
    - 默认从系统语言检测
    - 全局国际化支持（i18n）
    - localStorage 持久化
    - _Requirements: 新增设置功能_
  - [ ] 16.4 实现分析深度设置
    - 标准（detailed，完成度阈值 80%）/ 深入分析（comprehensive，完成度阈值 95%）
    - 影响后端 Replanner 的完成度判断阈值和 summary 输出详细程度
    - localStorage 持久化

    - _Requirements: 新增设置功能_
  - [ ] 16.5 实现主题设置
    - 浅色 / 深色 / 跟随系统
    - CSS 变量切换
    - _Requirements: 16.6_
  - [ ] 16.6 实现 AI 模型选择
    - 内置模型列表（DeepSeek/Qwen/GLM/Kimi/GPT/Claude）
    - 自定义模型列表（从后端加载）
    - 分组显示
    - _Requirements: 新增设置功能_

- [ ] 17. 自定义模型功能实现
  - [ ] 17.1 实现 CustomModelDialog 对话框
    - 模型名称、API 地址、API Key、模型标识
    - 表单验证
    - 测试连接按钮

    - _Requirements: 新增设置功能_
  - [ ] 17.2 实现后端自定义模型 API
    - GET /api/models/custom - 获取列表
    - POST /api/models/custom - 添加模型
    - DELETE /api/models/custom/{name} - 删除模型
    - POST /api/models/custom/test - 测试连接
    - 使用 StoreManager 持久化（custom_models 命名空间）
    - _Requirements: 新增设置功能_
  - [ ] 17.3 实现自定义模型删除功能
    - 下拉列表中显示删除按钮
    - 确认删除
    - _Requirements: 新增设置功能_

- [ ] 18. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户

## Phase 4: Tableau 集成与优化

- [ ] 19. Tableau 集成
  - [x] 19.1 完善 Tableau Extensions API 集成

    - 初始化检测


    - 获取仪表板名称和数据源列表（只能获取名称，非 LUID）
    - 获取活动筛选器
    - _Requirements: 13.1, 13.2, 13.3_
  - [x] 19.2 实现后端数据源名称到 LUID 转换
    - 修改 API 接口支持 `datasource_name` 参数
    - 使用现有 `get_datasource_luid_by_name()` 函数转换
    - 使用 StoreManager 缓存 name → LUID 映射（TTL 1小时）
    - 缓存命名空间：`datasource_luid_cache`
    - _Requirements: 13.1, 13.2_
  - [ ] 19.3 实现后端 analysis_depth 参数支持和思维链输出
    - 修改 API 接口支持 `analysis_depth` 和 `language` 参数
    - Replanner Agent 由 LLM 动态评估 completeness_score（0-100）
    - 根据 analysis_depth 设置完成度阈值（detailed: 80% / comprehensive: 95%）
    - 设置最大轮数兜底（detailed: 3轮 / comprehensive: 5轮）
    - Replanner Agent 输出增加字段：
      - `reason`: 解释为什么要继续分析（思维链，展示给用户）
      - `next_question`: 下一轮要回答的问题（should_replan=true 时）
    - Replanner Agent 仅在 should_replan=false 时输出 summary
    - summary 详细程度根据 analysis_depth 调整
    - _Requirements: 新增设置功能_
  - [ ] 19.4 实现 Tableau 设置持久化
    - 使用 tableau.extensions.settings 保存配置
    - 扩展重新加载时恢复配置
    - _Requirements: 13.5, 13.6_

- [x] 20. 响应式优化

  - [ ] 20.1 完善响应式布局
    - 标准布局（>= 768px）
    - 紧凑布局（480-768px）
    - 最小化布局（320-480px）
    - 窗口过小提示（< 320px）

    - _Requirements: 15.1, 15.2, 15.3, 15.4_
  - [ ] 20.2 表格响应式优化
    - 水平滚动指示器
    - _Requirements: 15.5_

- [ ] 21. 性能优化
  - [ ] 21.1 组件懒加载
    - DataTable、InsightCards 等大组件懒加载
    - _Requirements: NFR-1_
  - [ ] 21.2 虚拟滚动（可选）
    - 消息列表虚拟滚动（消息数量大时）


    - _Requirements: NFR-1_

- [ ] 22. Final Checkpoint - 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户
