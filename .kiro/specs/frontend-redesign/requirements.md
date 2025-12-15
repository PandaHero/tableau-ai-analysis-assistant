# 需求文档

## 简介

本文档定义了 Tableau AI 助手前端界面的重新设计需求。作为 Tableau 扩展插件，前端需要提供流畅的对话式数据分析体验，同时融入 Tableau 的设计语言。

### 项目背景

**当前状态**：
- 已有基础前端框架（Vue 3 + TypeScript + Vite）
- 已实现 SSE 流式客户端
- 已有初版 UI 设计文档，但不够完善
- 后端工作流已完成，支持完整的分析流程

**目标收益**：
- 提供专业、现代的数据分析对话界面
- 无缝融入 Tableau 扩展生态
- 支持流式输出，实时展示分析进度
- 清晰展示数据结果和业务洞察

### 技术栈

| 组件 | 方案 | 说明 |
|-----|------|------|
| 框架 | Vue 3 + Composition API | 响应式 UI |
| 语言 | TypeScript | 类型安全 |
| 构建 | Vite | 快速开发 |
| 状态管理 | Pinia | Vue 官方推荐 |
| UI 组件 | 自定义 + Tailwind CSS | Tableau 风格 |
| 图表 | ECharts / Chart.js | 数据可视化 |
| Markdown | markdown-it + highlight.js | 内容渲染 |

## 术语表

- **Tableau_AI_Assistant（系统）**: 本文档所描述的 Tableau AI 助手前端应用
- **Tableau_Extension（扩展）**: Tableau 仪表板中嵌入的自定义 Web 应用
- **SSE（Server-Sent Events）**: 服务器推送事件，用于流式输出
- **SemanticQuery（语义查询）**: 用户问题的结构化表示
- **VizQL**: Tableau 的可视化查询语言，用于描述数据查询和可视化操作
- **Insight（洞察）**: 数据分析得出的业务发现，包含类型（发现/异常/建议）、标题、描述、置信度
- **Replanner（重规划器）**: 生成后续分析问题的组件
- **Message（消息）**: 对话中的单条记录，包含发送者、内容、时间戳
- **Session（会话）**: 一次完整的对话上下文，包含多条消息
- **CommonMark**: Markdown 的标准化规范，定义了 Markdown 语法的明确解析规则
- **GFM（GitHub Flavored Markdown）**: GitHub 扩展的 Markdown 语法，支持表格、任务列表等额外功能


## 需求列表

### 需求 1: 整体布局设计

**用户故事:** 作为 Tableau 用户，我希望 AI 助手界面简洁专业，以便我能专注于数据分析而不被复杂界面分散注意力。

**优先级**: P0（核心功能）

#### 验收标准

1. WHEN 用户打开 Tableau_Extension THEN THE Tableau_AI_Assistant SHALL 显示三区域布局：顶部导航栏（高度 48px ± 2px）、中间对话区域（可滚动、占据剩余空间）、底部输入区域（高度 64px ± 2px）
2. WHEN 显示顶部导航栏 THEN THE Tableau_AI_Assistant SHALL 包含居中显示的 Tableau 风格 Logo（32x32px）和标题文字"Tableau AI 助手"，右侧显示设置图标按钮（24x24px）
3. WHEN 对话区域有新 Message 添加 THEN THE Tableau_AI_Assistant SHALL 在 100ms 内自动滚动到最新 Message 位置
4. WHEN 用户调整窗口大小 THEN THE Tableau_AI_Assistant SHALL 响应式适配，支持最小宽度 320px 至最大宽度 1920px
5. WHEN Tableau_Extension 嵌入 Tableau 仪表板 THEN THE Tableau_AI_Assistant SHALL 使用 Tableau 主色调（#1F77B4）作为品牌色

### 需求 2: 对话消息设计

**用户故事:** 作为用户，我希望对话消息清晰区分用户和 AI，以便我能快速理解对话流程。

**优先级**: P0（核心功能）

#### 验收标准

1. WHEN 用户发送 Message THEN THE Tableau_AI_Assistant SHALL 显示用户消息气泡（右对齐、背景色 #1F77B4、文字色 #FFFFFF、圆角 12px、最大宽度 80%）
2. WHEN AI 回复 Message THEN THE Tableau_AI_Assistant SHALL 显示 AI 消息区块（左对齐、背景色 #FFFFFF、边框色 #E0E0E0、边框宽度 1px、圆角 12px、最大宽度 90%）
3. WHEN AI Message 包含 Markdown 内容 THEN THE Tableau_AI_Assistant SHALL 正确渲染以下格式：标题（h1-h6）、有序/无序列表、加粗/斜体、代码块（带语法高亮）、链接、表格
4. WHEN Message 发送时间距当前超过 60 秒 THEN THE Tableau_AI_Assistant SHALL 显示相对时间戳（格式："X分钟前"、"X小时前"、"X天前"）
5. WHEN 用户点击 Message 内容区域 THEN THE Tableau_AI_Assistant SHALL 显示"复制"操作按钮，点击后复制纯文本内容到剪贴板
6. WHEN 用户输入空白字符串（仅包含空格、换行、制表符） THEN THE Tableau_AI_Assistant SHALL 阻止发送并保持输入框内容不变
7. WHEN 用户输入超过 2000 字符 THEN THE Tableau_AI_Assistant SHALL 显示字符计数器并阻止继续输入

### 需求 3: AI 回复结构化展示

**用户故事:** 作为用户，我希望 AI 回复结构清晰，以便我能快速获取分析结论和关键发现。

**优先级**: P0（核心功能）

**说明**：AI 回复采用结构化 Markdown 格式，包含：开场白、分析结果、关键发现、技术细节（可折叠）、推荐问题。

#### 验收标准

1. WHEN AI 回复分析结果 THEN THE Tableau_AI_Assistant SHALL 按固定顺序展示：开场白（1句话，最多 100 字符）→ 📊 分析结果区块 → 💡 关键发现区块 → 🔧 技术细节区块（默认折叠）→ 💬 推荐问题区块
2. WHEN 展示分析结果区块 THEN THE Tableau_AI_Assistant SHALL 使用加粗样式（font-weight: 600）和放大字号（1.25em）突出显示核心数据
3. WHEN 展示关键发现区块 THEN THE Tableau_AI_Assistant SHALL 使用编号列表格式，关键数字使用加粗样式，每条发现不超过 200 字符
4. WHEN 展示技术细节区块 THEN THE Tableau_AI_Assistant SHALL 默认折叠状态，显示折叠标题"查看 VizQL 查询 ▼"，点击后展开显示完整内容
5. WHEN 展示推荐问题区块 THEN THE Tableau_AI_Assistant SHALL 显示 2-3 个可点击的后续问题，每个问题不超过 50 字符

### 需求 4: 数据表格组件

**用户故事:** 作为用户，我希望查询结果以表格形式展示，以便我能查看详细数据。

**优先级**: P0（核心功能）

#### 验收标准

1. WHEN 查询返回结构化数据 THEN THE Tableau_AI_Assistant SHALL 在 Message 中内嵌显示数据表格组件
2. WHEN 数据行数超过 10 行 THEN THE Tableau_AI_Assistant SHALL 默认显示前 10 行，底部显示"展开全部（共 N 行）"按钮
3. WHEN 表格列数超过 5 列或总宽度超过容器宽度 THEN THE Tableau_AI_Assistant SHALL 启用水平滚动，显示滚动条
4. WHEN 用户点击表头单元格 THEN THE Tableau_AI_Assistant SHALL 按该列排序（首次点击升序、再次点击降序、第三次取消排序）
5. WHEN 用户点击"导出 CSV"按钮 THEN THE Tableau_AI_Assistant SHALL 生成 CSV 文件并触发浏览器下载，文件名格式为"tableau_data_YYYYMMDD_HHmmss.csv"
6. WHEN 显示数值类型列 THEN THE Tableau_AI_Assistant SHALL 自动格式化：整数使用千分位分隔符，小数保留 2 位，负数显示红色
7. WHEN 表格数据为空（0 行） THEN THE Tableau_AI_Assistant SHALL 显示空状态提示"暂无数据"
8. WHEN 单元格文本超过 3 行 THEN THE Tableau_AI_Assistant SHALL 默认显示 3 行并提供"展开"按钮，点击后显示完整内容和"收起"按钮


### 需求 5: 数据可视化组件（Phase 2 - 后续扩展）

**用户故事:** 作为用户，我希望数据能以图表形式可视化，以便直观理解数据趋势。

**优先级**: P2（后续扩展）

**说明**：Phase 1 阶段数据默认以表格形式展示。可视化图表功能将在 Phase 2 阶段扩展实现。

#### 验收标准

1. WHEN 查询结果包含可视化数据 THEN THE Tableau_AI_Assistant SHALL 默认以数据表格形式展示（Phase 1）
2. WHERE 可视化功能已启用（Phase 2） THEN THE Tableau_AI_Assistant SHALL 提供视图切换按钮组（表格/柱状图/折线图/饼图）
3. WHERE 可视化功能已启用 THEN THE Tableau_AI_Assistant SHALL 根据数据特征自动推荐图表类型：时间序列→折线图、分类数据→柱状图、占比数据→饼图
4. WHERE 可视化功能已启用 THEN THE Tableau_AI_Assistant SHALL 使用 Tableau 经典配色序列（#1F77B4, #FF7F0E, #2CA02C, #D62728, #9467BD, #8C564B, #E377C2, #7F7F7F, #BCBD22, #17BECF）
5. WHERE 可视化功能已启用 WHEN 用户悬停图表数据元素超过 200ms THEN THE Tableau_AI_Assistant SHALL 显示 tooltip，包含维度名称、度量值、占比（如适用）

### 需求 6: 洞察卡片组件

**用户故事:** 作为用户，我希望业务洞察以卡片形式突出展示，以便我能快速获取关键发现。

**优先级**: P0（核心功能）

#### 验收标准

1. WHEN AI 生成 Insight 列表 THEN THE Tableau_AI_Assistant SHALL 以垂直卡片列表形式展示，每个 Insight 独立一张卡片，卡片间距 12px
2. WHEN 展示 Insight 卡片 THEN THE Tableau_AI_Assistant SHALL 包含以下元素：类型图标（24x24px）、标题、描述
3. WHEN Insight 类型为"发现"/"异常"/"建议" THEN THE Tableau_AI_Assistant SHALL 分别使用图标和颜色：💡蓝色(#1F77B4) / ⚠️橙色(#FF7F0E) / ✅绿色(#2CA02C)
4. WHEN 多个 Insight 存在 THEN THE Tableau_AI_Assistant SHALL 按优先级降序排列（高优先级在前）
5. WHEN Insight 列表为空 THEN THE Tableau_AI_Assistant SHALL 不显示洞察卡片区块


### 需求 7: 思考状态指示器

**用户故事:** 作为用户，我希望在 AI 处理时看到进度提示，以便我知道系统正在工作。

**优先级**: P0（核心功能）

**说明**：采用简洁的状态提示，不展示复杂的 Agent 流程图。

#### 验收标准

1. WHEN AI 开始处理用户请求 THEN THE Tableau_AI_Assistant SHALL 显示思考状态指示器（三点动画 + 状态文字），动画周期 1.5 秒
2. WHEN 处理进入不同阶段 THEN THE Tableau_AI_Assistant SHALL 更新状态文字：理解问题 → 构建查询 → 执行分析 → 生成洞察
3. WHEN 状态文字切换 THEN THE Tableau_AI_Assistant SHALL 使用 300ms 淡入淡出过渡动画
4. WHEN 处理完成 THEN THE Tableau_AI_Assistant SHALL 在 200ms 内隐藏思考指示器，显示完整回复内容
5. WHEN 处理过程出错 THEN THE Tableau_AI_Assistant SHALL 将指示器变为错误状态（红色 #D62728），显示错误消息文字

### 需求 8: 输入区域设计

**用户故事:** 作为用户，我希望输入区域简洁易用，以便我能快速提问。

**优先级**: P0（核心功能）

#### 验收标准

1. WHEN 显示输入区域 THEN THE Tableau_AI_Assistant SHALL 包含多行文本输入框（最小高度 40px、最大高度 120px、自动扩展）和发送按钮（40x40px）
2. WHEN 用户按 Enter 键且输入框有有效内容 THEN THE Tableau_AI_Assistant SHALL 发送 Message
3. WHEN 用户按 Shift+Enter 组合键 THEN THE Tableau_AI_Assistant SHALL 在输入框中插入换行符而不发送
4. WHEN Message 发送成功后 THEN THE Tableau_AI_Assistant SHALL 清空输入框内容并保持输入框焦点状态
5. WHEN 输入框内容为空或仅包含空白字符 THEN THE Tableau_AI_Assistant SHALL 禁用发送按钮（opacity: 0.5、cursor: not-allowed）
6. WHEN AI 正在处理请求 THEN THE Tableau_AI_Assistant SHALL 禁用输入框和发送按钮，显示"AI 正在思考..."占位文字
7. WHEN 输入框获得焦点 THEN THE Tableau_AI_Assistant SHALL 显示蓝色边框（#1F77B4、2px）
8. WHEN 用户输入空白字符串（仅包含空格、换行、制表符） THEN THE Tableau_AI_Assistant SHALL 阻止发送并保持输入框内容不变
9. WHEN 用户输入超过 2000 字符 THEN THE Tableau_AI_Assistant SHALL 显示字符计数器并阻止继续输入


### 需求 9: 推荐问题交互

**用户故事:** 作为用户，我希望能快速选择推荐问题继续分析，以便降低思考成本。

**优先级**: P1（重要功能）

#### 验收标准

1. WHEN AI 回复包含推荐问题列表 THEN THE Tableau_AI_Assistant SHALL 在回复末尾显示可点击的问题芯片（Chip）组件
2. WHEN 用户点击推荐问题芯片 THEN THE Tableau_AI_Assistant SHALL 将问题文本填入输入框并自动发送
3. WHEN 显示推荐问题芯片 THEN THE Tableau_AI_Assistant SHALL 使用芯片样式（背景色 #F5F5F5、边框色 #E0E0E0、圆角 16px、内边距 8px 16px）
4. WHEN 用户悬停推荐问题芯片 THEN THE Tableau_AI_Assistant SHALL 显示悬停状态（背景色 #E8E8E8、cursor: pointer）
5. WHEN 推荐问题数量超过 3 个 THEN THE Tableau_AI_Assistant SHALL 显示前 3 个，末尾显示"更多 ▼"展开按钮
6. WHEN 用户已发送新 Message THEN THE Tableau_AI_Assistant SHALL 隐藏之前回复中的推荐问题芯片

### 需求 10: 可折叠技术细节

**用户故事:** 作为高级用户，我希望能查看 VizQL 查询等技术细节，以便调试和学习。

**优先级**: P1（重要功能）

#### 验收标准

1. WHEN AI 回复包含技术细节数据 THEN THE Tableau_AI_Assistant SHALL 默认折叠显示，标题为"🔧 查看 VizQL 查询 ▼"
2. WHEN 用户点击折叠标题 THEN THE Tableau_AI_Assistant SHALL 使用 300ms 滑动动画展开内容，图标变为"▲"
3. WHEN 展开技术细节 THEN THE Tableau_AI_Assistant SHALL 显示以下信息：SemanticQuery JSON（格式化缩进 2 空格）、执行时间（毫秒）、返回行数
4. WHEN 显示 JSON 代码块 THEN THE Tableau_AI_Assistant SHALL 使用等宽字体（font-family: 'Consolas', 'Monaco', monospace）和语法高亮
5. WHEN 用户点击代码块右上角"复制"按钮 THEN THE Tableau_AI_Assistant SHALL 复制 JSON 文本到剪贴板，按钮文字变为"已复制 ✓"持续 2 秒
6. WHEN JSON 解析后重新序列化 THEN THE Tableau_AI_Assistant SHALL 保证 JSON.parse(JSON.stringify(data)) 与原始数据结构等价（round-trip 一致性）


### 需求 11: 流式输出支持

**用户故事:** 作为用户，我希望看到 AI 实时生成回复，以便获得更好的交互体验。

**优先级**: P0（核心功能）

#### 验收标准

1. WHEN 后端发送 SSE token 事件 THEN THE Tableau_AI_Assistant SHALL 在 50ms 内实时追加显示文字（打字机效果）
2. WHEN 后端发送 SSE node_start 事件 THEN THE Tableau_AI_Assistant SHALL 更新思考状态指示器为对应阶段
3. WHEN 后端发送 SSE node_complete 事件 THEN THE Tableau_AI_Assistant SHALL 更新对应节点状态为完成（显示 ✓ 标记）
4. WHEN 后端发送 SSE complete 事件 THEN THE Tableau_AI_Assistant SHALL 结束流式输出，渲染完整 Markdown 内容
5. WHEN 后端发送 SSE error 事件 THEN THE Tableau_AI_Assistant SHALL 显示错误消息并立即停止流式输出
6. WHEN SSE 连接中断超过 5 秒 THEN THE Tableau_AI_Assistant SHALL 显示"连接已断开"提示和"重新连接"按钮
7. WHEN 流式输出过程中收到 Markdown 内容 THEN THE Tableau_AI_Assistant SHALL 保证渲染后的 HTML 结构与完整内容一次性渲染结果一致

### 需求 12: 会话管理

**用户故事:** 作为用户，我希望能管理对话历史，以便回顾之前的分析。

**优先级**: P2（辅助功能）

#### 验收标准

1. WHEN 用户开始新对话 THEN THE Tableau_AI_Assistant SHALL 自动生成 UUID v4 格式的 Session ID
2. WHEN 用户刷新页面 THEN THE Tableau_AI_Assistant SHALL 从 localStorage 恢复当前 Session 的 Message 历史
3. WHEN 用户点击"新对话"按钮 THEN THE Tableau_AI_Assistant SHALL 清空当前对话区域，生成新 Session ID，保留旧 Session 数据
4. WHEN Session 创建时间超过 24 小时 THEN THE Tableau_AI_Assistant SHALL 将该 Session 标记为已归档状态
5. WHEN 用户在设置面板点击"清除所有历史" THEN THE Tableau_AI_Assistant SHALL 删除 localStorage 中所有 Session 数据，显示确认对话框
6. WHEN Session 数据序列化存储后反序列化 THEN THE Tableau_AI_Assistant SHALL 保证数据完整性（所有 Message 字段值不变）


### 需求 13: Tableau 集成

**用户故事:** 作为 Tableau 用户，我希望扩展能与 Tableau 仪表板无缝集成，以便获取上下文信息。

**优先级**: P1（重要功能）

#### 验收标准

1. WHEN Tableau_Extension 初始化 THEN THE Tableau_AI_Assistant SHALL 调用 Tableau Extensions API 获取仪表板名称和数据源列表
2. WHEN 成功获取数据源信息 THEN THE Tableau_AI_Assistant SHALL 自动设置 datasource_luid 参数，无需用户手动输入
3. WHEN 仪表板存在活动筛选器 THEN THE Tableau_AI_Assistant SHALL 将筛选器上下文（字段名、筛选值）传递给后端 API
4. WHEN Tableau Extensions API 调用失败或不可用 THEN THE Tableau_AI_Assistant SHALL 显示"无法连接 Tableau，请手动输入数据源 ID"提示和输入框
5. WHEN 用户完成扩展配置 THEN THE Tableau_AI_Assistant SHALL 调用 tableau.extensions.settings.saveAsync() 持久化配置
6. WHEN 扩展重新加载 THEN THE Tableau_AI_Assistant SHALL 从 Tableau 扩展设置恢复之前的配置

### 需求 14: 错误处理与用户反馈

**用户故事:** 作为用户，我希望在出错时获得清晰的提示，以便我知道如何处理。

**优先级**: P0（核心功能）

#### 验收标准

1. WHEN HTTP 请求返回网络错误（status 0 或 fetch 异常） THEN THE Tableau_AI_Assistant SHALL 显示"网络连接失败，请检查网络后重试"和"重试"按钮
2. WHEN 后端返回 4xx/5xx 错误 THEN THE Tableau_AI_Assistant SHALL 显示用户友好消息（映射表：400→"请求格式错误"、401→"请重新登录"、403→"无访问权限"、404→"资源不存在"、500→"服务器内部错误，请稍后重试"）
3. WHEN 请求超时（超过 60 秒无响应） THEN THE Tableau_AI_Assistant SHALL 显示"分析时间较长，请稍候或尝试简化问题"和"取消"按钮
4. WHEN 数据源连接失败 THEN THE Tableau_AI_Assistant SHALL 显示"数据源连接失败（错误码：XXX），请联系管理员"
5. WHEN 用户输入包含潜在注入字符（<script>、javascript:等） THEN THE Tableau_AI_Assistant SHALL 转义特殊字符后再显示
6. WHEN 错误消息显示 THEN THE Tableau_AI_Assistant SHALL 使用红色背景（#FEE2E2）、红色边框（#D62728）、红色图标（⚠️）


### 需求 15: 响应式设计

**用户故事:** 作为用户，我希望界面在不同尺寸下都能正常使用，以便在各种设备上使用。

**优先级**: P1（重要功能）

#### 验收标准

1. WHEN 窗口宽度 >= 768px THEN THE Tableau_AI_Assistant SHALL 使用标准布局（完整导航栏、标准间距 16px）
2. WHEN 窗口宽度 >= 480px 且 < 768px THEN THE Tableau_AI_Assistant SHALL 使用紧凑布局（隐藏标题文字、缩小间距至 12px）
3. WHEN 窗口宽度 >= 320px 且 < 480px THEN THE Tableau_AI_Assistant SHALL 使用最小化布局（仅显示 Logo 和必要按钮、间距 8px）
4. WHEN 窗口宽度 < 320px THEN THE Tableau_AI_Assistant SHALL 显示"窗口过小"提示，建议用户调整窗口大小
5. WHEN 表格宽度超出容器宽度 THEN THE Tableau_AI_Assistant SHALL 启用水平滚动，显示滚动指示器
6. WHEN 图表容器尺寸变化 THEN THE Tableau_AI_Assistant SHALL 在 resize 事件后 300ms 内完成图表重绘

### 需求 16: 主题与配色

**用户故事:** 作为用户，我希望界面风格与 Tableau 一致，以便获得统一的视觉体验。

**优先级**: P1（重要功能）

#### 验收标准

1. WHEN 渲染界面元素 THEN THE Tableau_AI_Assistant SHALL 使用 Tableau 经典配色：主蓝(#1F77B4)、橙(#FF7F0E)、绿(#2CA02C)、红(#D62728)、紫(#9467BD)
2. WHEN 显示主要操作按钮（发送、确认） THEN THE Tableau_AI_Assistant SHALL 使用 Tableau 蓝色(#1F77B4)背景、白色(#FFFFFF)文字
3. WHEN 显示成功状态（操作完成、连接成功） THEN THE Tableau_AI_Assistant SHALL 使用 Tableau 绿色(#2CA02C)
4. WHEN 显示警告状态（数据异常、性能警告） THEN THE Tableau_AI_Assistant SHALL 使用 Tableau 橙色(#FF7F0E)
5. WHEN 显示错误状态（请求失败、验证错误） THEN THE Tableau_AI_Assistant SHALL 使用 Tableau 红色(#D62728)
6. WHERE 用户在设置中启用深色模式 THEN THE Tableau_AI_Assistant SHALL 切换至深色主题（背景 #1E1E1E、文字 #E0E0E0、卡片 #2D2D2D）


### 需求 17: Markdown 渲染正确性

**用户故事:** 作为用户，我希望 Markdown 内容能正确渲染，以便我能阅读格式化的分析结果。

**优先级**: P0（核心功能）

**说明**：Markdown 解析和渲染是核心功能，需要保证正确性。

#### 验收标准

1. WHEN 渲染 Markdown 内容 THEN THE Tableau_AI_Assistant SHALL 支持 CommonMark 规范的所有基础语法
2. WHEN 渲染代码块 THEN THE Tableau_AI_Assistant SHALL 使用 highlight.js 进行语法高亮，支持 json、sql、python、javascript 语言
3. WHEN 渲染表格 THEN THE Tableau_AI_Assistant SHALL 正确解析 GFM 表格语法，支持列对齐（左/中/右）
4. WHEN Markdown 源文本经过 parse → render → 提取纯文本 流程 THEN THE Tableau_AI_Assistant SHALL 保证纯文本内容与原始文本语义等价
5. WHEN 渲染包含 XSS 攻击向量的内容（如 `<script>`、`onerror`） THEN THE Tableau_AI_Assistant SHALL 转义危险标签，输出安全 HTML

## 非功能性需求

### NFR-1: 性能要求

| 指标 | 目标值 | 测量方法 |
|-----|-------|---------|
| 首屏加载时间（FCP） | < 1.5s | Lighthouse |
| 可交互时间（TTI） | < 2.5s | Lighthouse |
| 消息渲染延迟 | < 100ms | Performance API |
| 流式输出延迟 | < 50ms | 网络监控 |
| 内存占用（稳定态） | < 80MB | Chrome DevTools |
| 内存占用（峰值） | < 150MB | Chrome DevTools |
| 图表渲染时间 | < 500ms | Performance API |

### NFR-2: 兼容性要求

| 平台 | 最低版本 |
|-----|---------|
| Chrome | 90+ |
| Edge | 90+ |
| Safari | 14+ |
| Firefox | 88+ |
| Tableau Desktop | 2021.1+ |
| Tableau Server | 2021.1+ |
| Tableau Cloud | 当前版本 |

- 支持触摸屏操作（点击、滑动）
- 支持高 DPI 显示器（2x、3x 缩放）

### NFR-3: 可访问性要求

| 标准 | 要求 |
|-----|------|
| 键盘导航 | 所有交互元素可通过 Tab 键访问 |
| 屏幕阅读器 | 所有图片和图标有 aria-label |
| 颜色对比度 | 符合 WCAG 2.1 AA 标准（对比度 ≥ 4.5:1） |
| 焦点指示 | 可见的焦点轮廓（2px 蓝色边框） |

## 实施优先级

| 阶段 | 需求 | 说明 |
|-----|------|------|
| Phase 1 | R1, R2, R3, R7, R8, R11, R14, R17 | 核心对话功能 + Markdown 渲染 |
| Phase 2 | R4, R6, R9, R10 | 数据展示增强 |
| Phase 2+ | R5 | 可视化图表扩展（后续研究） |
| Phase 3 | R12, R13, R15, R16（不含深色模式） | 集成与优化 |
| Phase 4 | R16.6（深色模式） | 可选增强功能 |