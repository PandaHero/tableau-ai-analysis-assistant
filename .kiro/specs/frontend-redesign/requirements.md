# 需求文档 - Tableau AI Assistant 前端重设计

## 引言

Tableau AI Assistant 前端是一个嵌入在 Tableau Dashboard 中的 AI 驱动的数据分析对话界面。本项目旨在重新设计和优化现有前端实现，提供更现代化、高性能、可访问的用户体验。

### 项目目标

- 提供流畅的对话式数据分析体验
- 支持实时流式响应和 Markdown 渲染
- 实现响应式设计，适配多种设备
- 确保可访问性符合 WCAG 2.1 AA 标准
- 优化性能，支持大量消息历史记录
- 提供灵活的用户设置和会话管理

### 技术栈

- **前端框架**: Vue 3 (Composition API)
- **语言**: TypeScript
- **构建工具**: Vite
- **状态管理**: Pinia
- **样式**: Tailwind CSS
- **HTTP 客户端**: Axios
- **Markdown 渲染**: markdown-it
- **代码高亮**: highlight.js

## 术语表

- **System**: Tableau AI Assistant 前端应用
- **User**: 使用 Tableau Dashboard 的数据分析师或业务用户
- **Message**: 用户发送的问题或 AI 返回的回复
- **Session**: 一次完整的对话会话，包含多条消息
- **Datasource**: Tableau Dashboard 中的数据源
- **Boost_Prompt**: 预定义的快捷提示模板
- **SSE**: Server-Sent Events，服务器推送事件
- **Streaming_Response**: 流式响应，AI 逐字返回内容
- **Markdown**: 轻量级标记语言，用于格式化文本
- **Accessibility**: 可访问性，确保残障用户可以使用应用
- **WCAG**: Web Content Accessibility Guidelines，网页内容可访问性指南
- **ARIA**: Accessible Rich Internet Applications，无障碍富互联网应用
- **Tableau_Extension**: Tableau 扩展插件，嵌入在 Dashboard 中运行
- **Virtual_Scrolling**: 虚拟滚动，仅渲染可见区域的列表项以提升性能

## 需求

### 需求 1: 对话界面

**用户故事**: 作为数据分析师，我希望通过对话方式与 AI 交互，以便快速获取数据洞察。

#### 验收标准

1. THE System SHALL 显示一个聊天界面，包含消息列表和输入框
2. WHEN User 输入问题并提交，THE System SHALL 将消息添加到消息列表
3. WHEN User 提交空消息，THE System SHALL 阻止提交并显示提示
4. THE System SHALL 区分用户消息和 AI 消息的视觉样式
5. WHEN 消息列表为空，THE System SHALL 显示欢迎界面和使用提示
6. THE System SHALL 在消息列表底部自动滚动到最新消息
7. WHEN User 手动滚动消息列表，THE System SHALL 暂停自动滚动
8. WHEN User 滚动到底部，THE System SHALL 恢复自动滚动

### 需求 2: 流式响应

**用户故事**: 作为用户，我希望看到 AI 逐字输出回复，以便实时了解生成进度。

#### 验收标准

1. WHEN AI 开始生成回复，THE System SHALL 通过 SSE 接收流式数据
2. WHEN 接收到新的 token，THE System SHALL 立即追加到当前消息
3. WHEN 流式响应进行中，THE System SHALL 显示打字指示器动画
4. WHEN 流式响应完成，THE System SHALL 移除打字指示器
5. IF SSE 连接中断，THEN THE System SHALL 显示错误提示并允许重试
6. THE System SHALL 在流式响应期间禁用输入框
7. WHEN 流式响应完成，THE System SHALL 重新启用输入框

### 需求 3: Markdown 渲染

**用户故事**: 作为用户，我希望 AI 回复支持富文本格式，以便更清晰地展示结构化内容。

#### 验收标准

1. THE System SHALL 将 AI 消息中的 Markdown 语法渲染为 HTML
2. THE System SHALL 支持以下 Markdown 语法：标题、列表、粗体、斜体、链接、代码块、表格
3. WHEN 消息包含代码块，THE System SHALL 应用语法高亮
4. THE System SHALL 支持以下编程语言的语法高亮：Python、SQL、JavaScript、JSON
5. THE System SHALL 对 Markdown 渲染结果进行 XSS 清理
6. THE System SHALL 为代码块添加复制按钮
7. WHEN User 点击复制按钮，THE System SHALL 将代码复制到剪贴板并显示成功提示

### 需求 4: 数据源管理

**用户故事**: 作为用户，我希望选择要分析的数据源，以便 AI 基于正确的数据回答问题。

#### 验收标准

1. WHEN System 初始化，THE System SHALL 通过 Tableau Extension API 获取可用数据源列表
2. THE System SHALL 在界面顶部显示数据源选择器
3. WHEN User 选择数据源，THE System SHALL 更新当前活动数据源
4. WHEN 数据源切换，THE System SHALL 通知后端 API 更新上下文
5. IF 获取数据源失败，THEN THE System SHALL 显示错误提示
6. THE System SHALL 显示当前选中数据源的名称
7. WHEN Dashboard 中没有数据源，THE System SHALL 显示提示信息

### 需求 5: 快捷提示

**用户故事**: 作为用户，我希望使用预定义的快捷提示，以便快速开始常见的分析任务。

#### 验收标准

1. THE System SHALL 提供至少 5 个内置快捷提示
2. THE System SHALL 在输入框下方显示快捷提示面板
3. WHEN User 点击快捷提示，THE System SHALL 将提示文本填充到输入框
4. THE System SHALL 支持用户添加自定义快捷提示
5. THE System SHALL 将自定义快捷提示存储在浏览器本地存储
6. THE System SHALL 支持删除自定义快捷提示
7. THE System SHALL 按类别组织快捷提示（内置、自定义）
8. WHEN 快捷提示面板打开，THE System SHALL 支持键盘导航选择提示

### 需求 6: 会话管理

**用户故事**: 作为用户，我希望管理多个对话会话，以便组织不同的分析任务。

#### 验收标准

1. THE System SHALL 支持创建新会话
2. WHEN User 创建新会话，THE System SHALL 生成唯一会话 ID 并清空消息列表
3. THE System SHALL 在侧边栏显示会话历史列表
4. THE System SHALL 支持切换到历史会话
5. WHEN User 切换会话，THE System SHALL 加载该会话的消息历史
6. THE System SHALL 支持删除会话
7. THE System SHALL 支持重命名会话
8. THE System SHALL 为每个会话显示最后更新时间
9. THE System SHALL 按时间倒序排列会话列表
10. WHEN 会话列表超过 20 条，THE System SHALL 实现分页或懒加载

### 需求 7: 用户设置

**用户故事**: 作为用户，我希望自定义应用设置，以便获得个性化的使用体验。

#### 验收标准

1. THE System SHALL 提供设置面板，包含以下选项：语言、分析深度、主题、显示思考过程
2. THE System SHALL 支持语言切换（中文、英文）
3. WHEN User 切换语言，THE System SHALL 立即更新界面文本
4. THE System SHALL 支持分析深度选择（标准、深入）
5. THE System SHALL 支持主题切换（浅色、深色、自动）
6. WHEN User 选择自动主题，THE System SHALL 根据系统偏好设置主题
7. THE System SHALL 支持显示/隐藏 AI 思考过程
8. THE System SHALL 将用户设置持久化到浏览器本地存储
9. WHEN System 初始化，THE System SHALL 从本地存储加载用户设置

### 需求 8: 响应式设计

**用户故事**: 作为用户，我希望在不同设备上都能流畅使用应用，以便随时随地进行数据分析。

#### 验收标准

1. THE System SHALL 在桌面端（>1024px）显示完整布局
2. THE System SHALL 在平板端（768px-1024px）调整布局以适配屏幕
3. THE System SHALL 在移动端（<768px）使用单列布局
4. WHEN 屏幕宽度小于 768px，THE System SHALL 将侧边栏改为抽屉式
5. THE System SHALL 确保所有交互元素的最小触摸目标为 44x44px
6. THE System SHALL 在不同屏幕尺寸下保持可读性
7. THE System SHALL 使用相对单位（rem、em、%）而非固定像素

### 需求 9: 可访问性

**用户故事**: 作为残障用户，我希望能够使用屏幕阅读器和键盘操作应用，以便无障碍地进行数据分析。

#### 验收标准

1. THE System SHALL 为所有交互元素添加适当的 ARIA 标签
2. THE System SHALL 支持完整的键盘导航（Tab、Enter、Esc、方向键）
3. WHEN User 使用 Tab 键导航，THE System SHALL 显示清晰的焦点指示器
4. THE System SHALL 确保颜色对比度符合 WCAG 2.1 AA 标准（至少 4.5:1）
5. THE System SHALL 为图标按钮提供文本替代（aria-label）
6. THE System SHALL 使用语义化 HTML 标签（header、main、nav、button）
7. WHEN 模态框打开，THE System SHALL 将焦点移动到模态框内
8. WHEN 模态框关闭，THE System SHALL 将焦点返回到触发元素
9. THE System SHALL 为动态内容更新提供屏幕阅读器通知（aria-live）

### 需求 10: 性能优化

**用户故事**: 作为用户，我希望应用快速响应，以便高效完成分析任务。

#### 验收标准

1. THE System SHALL 在首次加载时在 2 秒内显示界面
2. WHEN 消息列表超过 100 条，THE System SHALL 使用虚拟滚动渲染
3. THE System SHALL 对 Markdown 渲染实现防抖（300ms）
4. THE System SHALL 对代码高亮实现懒加载
5. THE System SHALL 使用代码分割减少初始加载体积
6. THE System SHALL 缓存已渲染的 Markdown 内容
7. WHEN 构建生产版本，THE System SHALL 压缩和混淆代码
8. THE System SHALL 确保构建产物总大小小于 1MB（gzip 后）

### 需求 11: 错误处理

**用户故事**: 作为用户，我希望在出现错误时获得清晰的提示，以便了解问题并采取行动。

#### 验收标准

1. WHEN API 请求失败，THE System SHALL 显示用户友好的错误消息
2. THE System SHALL 区分网络错误、服务器错误和客户端错误
3. WHEN 网络连接中断，THE System SHALL 显示离线提示
4. THE System SHALL 为可重试的错误提供重试按钮
5. WHEN 认证失败，THE System SHALL 提示用户重新登录
6. THE System SHALL 记录错误日志到浏览器控制台
7. IF 发生未预期的错误，THEN THE System SHALL 显示通用错误提示并保持应用可用

### 需求 12: 安全性

**用户故事**: 作为用户，我希望我的数据和隐私得到保护，以便安全地使用应用。

#### 验收标准

1. THE System SHALL 通过 HTTPS 加载所有资源
2. THE System SHALL 对用户输入进行验证和清理
3. THE System SHALL 对 Markdown 渲染结果进行 XSS 清理
4. THE System SHALL 实施 Content Security Policy
5. THE System SHALL 不在本地存储中保存敏感信息（密码、Token）
6. THE System SHALL 对 API 请求添加 CSRF 保护（如适用）
7. THE System SHALL 在生产环境禁用开发者工具的敏感信息输出

### 需求 13: 国际化

**用户故事**: 作为非中文用户，我希望使用英文界面，以便理解应用功能。

#### 验收标准

1. THE System SHALL 支持中文和英文两种语言
2. THE System SHALL 将所有界面文本外部化到语言文件
3. WHEN User 切换语言，THE System SHALL 更新所有界面文本
4. THE System SHALL 根据浏览器语言设置默认语言
5. THE System SHALL 为日期和时间使用本地化格式
6. THE System SHALL 确保不同语言下的布局不会错乱

### 需求 14: 消息反馈

**用户故事**: 作为用户，我希望对 AI 回复进行反馈，以便帮助改进 AI 质量。

#### 验收标准

1. THE System SHALL 为每条 AI 消息显示反馈按钮（点赞、点踩）
2. WHEN User 点击反馈按钮，THE System SHALL 记录反馈并更新按钮状态
3. THE System SHALL 将反馈数据发送到后端 API
4. THE System SHALL 防止用户对同一消息重复反馈
5. WHEN 反馈提交失败，THE System SHALL 显示错误提示并允许重试

### 需求 15: Tableau 集成

**用户故事**: 作为 Tableau 用户，我希望应用能够无缝集成到 Dashboard 中，以便在熟悉的环境中使用 AI 助手。

#### 验收标准

1. THE System SHALL 作为 Tableau Extension 运行
2. THE System SHALL 通过 Tableau Extension API 初始化
3. THE System SHALL 获取当前 Dashboard 的上下文信息
4. THE System SHALL 监听 Dashboard 的数据源变更事件
5. WHEN Dashboard 数据源变更，THE System SHALL 更新数据源列表
6. THE System SHALL 遵守 Tableau Extension 的安全策略
7. THE System SHALL 在 manifest.trex 文件中声明所需权限

### 需求 16: 数据表格展示

**用户故事**: 作为用户，我希望 AI 返回的数据以表格形式展示，以便清晰地查看结构化数据。

#### 验收标准

1. WHEN AI 消息包含表格数据，THE System SHALL 渲染为 HTML 表格
2. THE System SHALL 为表格添加边框和斑马纹样式
3. THE System SHALL 支持表格的水平滚动（当列数过多时）
4. THE System SHALL 为表格添加导出按钮（CSV 格式）
5. WHEN User 点击导出按钮，THE System SHALL 下载表格数据为 CSV 文件
6. THE System SHALL 确保表格在移动端可读（响应式设计）

### 需求 17: 加载状态

**用户故事**: 作为用户，我希望在等待响应时看到加载指示器，以便了解系统正在处理我的请求。

#### 验收标准

1. WHEN User 提交问题，THE System SHALL 显示加载指示器
2. THE System SHALL 在消息列表中显示"AI 正在思考"的占位符
3. WHEN 流式响应开始，THE System SHALL 移除占位符并显示实际内容
4. THE System SHALL 在输入框中显示禁用状态（当 AI 正在响应时）
5. WHEN 请求超时（超过 60 秒），THE System SHALL 显示超时提示并允许重试

### 需求 18: 配置管理

**用户故事**: 作为开发者，我希望通过环境变量管理配置，以便在不同环境中部署应用。

#### 验收标准

1. THE System SHALL 从环境变量读取 API 基础 URL
2. THE System SHALL 从环境变量读取应用标题
3. THE System SHALL 从环境变量读取日志级别
4. THE System SHALL 支持开发环境和生产环境的不同配置
5. THE System SHALL 在构建时将环境变量注入到代码中
6. THE System SHALL 验证必需的环境变量是否存在

### 需求 19: 解析器和序列化器（Round-trip 属性）

**用户故事**: 作为开发者，我希望确保数据序列化和反序列化的正确性，以便保证数据完整性。

#### 验收标准

1. WHEN System 序列化会话数据到 JSON，THE System SHALL 生成有效的 JSON 字符串
2. WHEN System 反序列化 JSON 到会话对象，THE System SHALL 恢复所有字段
3. FOR ALL 有效的会话对象，序列化后反序列化 SHALL 产生等价的对象（round-trip 属性）
4. WHEN System 序列化用户设置到 localStorage，THE System SHALL 生成有效的 JSON 字符串
5. WHEN System 反序列化 localStorage 数据，THE System SHALL 处理损坏的数据并使用默认值
6. FOR ALL 有效的用户设置对象，序列化后反序列化 SHALL 产生等价的对象（round-trip 属性）

### 需求 20: 输入验证（错误条件）

**用户故事**: 作为开发者，我希望系统正确处理无效输入，以便提高应用的健壮性。

#### 验收标准

1. WHEN User 输入超过 5000 字符的消息，THE System SHALL 显示错误提示并阻止提交
2. WHEN User 输入仅包含空白字符的消息，THE System SHALL 显示错误提示并阻止提交
3. WHEN API 返回无效的 JSON 数据，THE System SHALL 记录错误并显示友好提示
4. WHEN 会话 ID 格式无效，THE System SHALL 拒绝加载并显示错误
5. WHEN 本地存储数据损坏，THE System SHALL 清除损坏数据并使用默认值
6. WHEN 用户设置包含无效值，THE System SHALL 使用默认值并记录警告

### 需求 21: 不变性属性

**用户故事**: 作为开发者，我希望确保关键数据结构的不变性，以便避免意外的状态变更。

#### 验收标准

1. WHEN 消息添加到消息列表，THE System SHALL 保持消息列表的顺序不变（按时间升序）
2. WHEN 会话切换，THE System SHALL 保持当前会话的消息数量不变
3. WHEN 用户设置更新，THE System SHALL 保持未修改设置项的值不变
4. WHEN Markdown 渲染，THE System SHALL 保持原始消息内容不变
5. WHEN 流式响应追加 token，THE System SHALL 保持已接收 token 的顺序不变

### 需求 22: 幂等性属性

**用户故事**: 作为开发者，我希望某些操作具有幂等性，以便避免重复操作产生副作用。

#### 验收标准

1. WHEN User 多次点击"创建新会话"按钮，THE System SHALL 仅创建一个新会话
2. WHEN User 多次点击"删除会话"按钮，THE System SHALL 仅删除一次
3. WHEN User 多次点击消息反馈按钮，THE System SHALL 仅记录一次反馈
4. WHEN System 多次初始化 Tableau Extension API，THE System SHALL 仅初始化一次
5. WHEN System 多次加载相同会话，THE System SHALL 产生相同的消息列表

### 需求 23: 性能基准（元形态属性）

**用户故事**: 作为开发者，我希望确保性能优化不会降低功能正确性，以便在性能和质量之间取得平衡。

#### 验收标准

1. WHEN 使用虚拟滚动渲染消息列表，THE System SHALL 显示与完整渲染相同的消息内容
2. WHEN 使用防抖优化 Markdown 渲染，THE System SHALL 最终产生与立即渲染相同的结果
3. WHEN 使用代码分割，THE System SHALL 加载所有必需的功能模块
4. WHEN 使用缓存优化，THE System SHALL 在缓存失效后重新获取最新数据
5. FOR ALL 消息列表长度 N，虚拟滚动渲染的消息数量 SHALL 小于或等于 N

## 正确性属性总结

本需求文档包含以下类型的正确性属性：

1. **不变性属性**（需求 21）
   - 消息列表顺序不变
   - 会话消息数量不变
   - 原始内容不变

2. **Round-trip 属性**（需求 19）
   - 会话数据序列化/反序列化对称性
   - 用户设置序列化/反序列化对称性

3. **幂等性属性**（需求 22）
   - 创建会话幂等
   - 删除会话幂等
   - 反馈提交幂等
   - API 初始化幂等

4. **元形态属性**（需求 23）
   - 虚拟滚动与完整渲染等价
   - 防抖渲染与立即渲染等价
   - 渲染消息数量关系

5. **错误条件**（需求 20）
   - 输入长度验证
   - 空白字符验证
   - 无效数据处理
   - 损坏数据恢复

这些属性确保系统在各种场景下的正确性、健壮性和性能。
