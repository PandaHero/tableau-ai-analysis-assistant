# Analytics Assistant 前端设计文档

## 1. 技术方案概述

### 1.1 技术栈选型

| 技术 | 选择 | 理由 |
|-----|------|------|
| **框架** | Vue 3.5+ | 响应式、Composition API、生态成熟 |
| **语言** | TypeScript 5.0+ | 类型安全、IDE 支持好、减少运行时错误 |
| **构建工具** | Vite 6.0+ | 快速 HMR、优化的生产构建、开发体验好 |
| **状态管理** | Pinia 2.3+ | Vue 官方推荐、TypeScript 友好、轻量 |
| **路由** | Vue Router 4.5+ | Vue 官方路由、支持嵌套路由 |
| **UI 组件库** | Element Plus 2.12+ | 组件丰富、文档完善、Tableau 风格适配 |
| **AI 框架** | Vercel AI SDK 5.0+ (@ai-sdk/vue) | 统一 AI 接口、内置流式输出、TypeScript 优先 |
| **HTTP 客户端** | Axios 1.7+ | 拦截器、请求取消、错误处理 |
| **Markdown 渲染** | markdown-it 14.1+ | 可扩展、插件丰富、性能好 |
| **代码高亮** | highlight.js 11.11+ | 支持多语言、主题丰富 |
| **数据可视化** | ECharts 5.5+ (vue-echarts) | 功能强大、图表类型丰富、中文文档完善 |
| **工具库** | @vueuse/core 14.1+ | Vue 组合式工具集、常用 hooks |
| **测试框架** | Vitest 2.1+ | Vite 原生支持、快速、兼容 Jest API |
| **属性测试** | fast-check | 属性测试、生成测试数据 |
| **代码检查** | ESLint 9+ | 代码质量、统一规范 |
| **代码格式化** | Prettier 3.4+ | 自动格式化、团队协作 |

### 1.2 为什么选择 Vercel AI SDK？

**Vercel AI SDK 5.0 核心优势**:
1. **统一接口**: 支持 100+ AI 模型（OpenAI、Anthropic、Google、DeepSeek 等）
2. **内置流式输出**: 自动处理 SSE、自动重连、错误恢复
3. **TypeScript 优先**: 完整的类型定义，IDE 支持好
4. **框架无关**: 支持 React/Vue/Svelte，我们使用 `@ai-sdk/vue`
5. **生产级别**: Vercel 官方维护，稳定性和性能有保障
6. **工具调用支持**: 支持 Function Calling / Tool Use
7. **多模态支持**: 文本、图片、音频输入

**与自己实现 SSE 客户端对比**:
- ✅ 节省 2-3 天开发时间
- ✅ 自动处理重连、超时、错误恢复
- ✅ 内置消息管理和状态同步
- ✅ 生产级别的稳定性
- ❌ 增加依赖（但依赖质量高）

**为什么选择 Vue 3 而不是 React？**

**优势**:
1. **学习曲线平缓**: 模板语法直观，适合快速开发
2. **响应式系统**: 自动依赖追踪，减少手动优化
3. **Composition API**: 逻辑复用更灵活
4. **生态成熟**: Pinia、Vue Router、Element Plus 等官方/社区方案完善
5. **性能优秀**: 编译时优化、虚拟 DOM 优化
6. **TypeScript 支持**: 官方支持，类型推导好

**与 React 对比**:
- Vue 3 的模板语法更适合快速开发 UI
- Pinia 比 Redux/Zustand 更简洁
- Vue 3 的响应式系统比 React Hooks 更直观
- Element Plus 比 Ant Design 更轻量

**为什么选择 ECharts 做数据可视化？**

**优势**:
1. **功能强大**: 支持 20+ 图表类型，配置灵活
2. **中文文档**: 文档完善，示例丰富
3. **Vue 集成**: `vue-echarts` 提供完美的 Vue 3 支持
4. **性能优秀**: Canvas 渲染，支持大数据量
5. **主题定制**: 可以适配 Tableau 风格
6. **交互丰富**: Tooltip、图例、缩放、数据区域选择

**与其他可视化库对比**:
- Chart.js: 简单但功能有限
- D3.js: 强大但学习曲线陡峭
- Plotly: 功能强大但体积大
- ECharts: 功能、性能、易用性平衡最好


### 1.3 架构设计原则

1. **分层架构**: 展示层、状态层、服务层、工具层分离
2. **组件化**: 单一职责、可复用、可测试
3. **类型安全**: TypeScript 严格模式，减少运行时错误
4. **响应式优先**: 利用 Vue 3 响应式系统，减少手动 DOM 操作
5. **性能优化**: 虚拟滚动、懒加载、代码分割
6. **错误边界**: 优雅降级，用户友好的错误提示

## 2. 整体架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Tableau Dashboard                                │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │              Tableau Extension (manifest.trex)                     │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │                   Vue 3 Application                          │  │  │
│  │  │                                                              │  │  │
│  │  │  ┌──────────────────────────────────────────────────────┐   │  │  │
│  │  │  │            展示层 (Components)                        │   │  │  │
│  │  │  │  ┌─────────────────────────────────────────────┐     │   │  │  │
│  │  │  │  │ Layout Components                           │     │   │  │  │
│  │  │  │  │  - AppLayout.vue                            │     │   │  │  │
│  │  │  │  │  - HeaderBar.vue                            │     │   │  │  │
│  │  │  │  │  - InputArea.vue                            │     │   │  │  │
│  │  │  │  └─────────────────────────────────────────────┘     │   │  │  │
│  │  │  │  ┌─────────────────────────────────────────────┐     │   │  │  │
│  │  │  │  │ Chat Components                             │     │   │  │  │
│  │  │  │  │  - ChatContainer.vue                        │     │   │  │  │
│  │  │  │  │  - MessageList.vue                          │     │   │  │  │
│  │  │  │  │  - UserMessage.vue                          │     │   │  │  │
│  │  │  │  │  - AIMessage.vue                            │     │   │  │  │
│  │  │  │  │  - ThinkingIndicator.vue                    │     │   │  │  │
│  │  │  │  └─────────────────────────────────────────────┘     │   │  │  │
│  │  │  │  ┌─────────────────────────────────────────────┐     │   │  │  │
│  │  │  │  │ Content Components                          │     │   │  │  │
│  │  │  │  │  - MarkdownRenderer.vue                     │     │   │  │  │
│  │  │  │  │  - DataTable.vue                            │     │   │  │  │
│  │  │  │  │  - TableToolbar.vue                         │     │   │  │  │
│  │  │  │  └─────────────────────────────────────────────┘     │   │  │  │
│  │  │  │  ┌─────────────────────────────────────────────┐     │   │  │  │
│  │  │  │  │ Settings Components                         │     │   │  │  │
│  │  │  │  │  - SettingsPanel.vue                        │     │   │  │  │
│  │  │  │  │  - DataSourceSelector.vue                   │     │   │  │  │
│  │  │  │  └─────────────────────────────────────────────┘     │   │  │  │
│  │  │  └──────────────────────────────────────────────────────┘   │  │  │
│  │  │                            │                                 │  │  │
│  │  │  ┌──────────────────────────────────────────────────────┐   │  │  │
│  │  │  │            状态层 (Pinia Stores)                      │   │  │  │
│  │  │  │  ┌──────────┐ ┌────────────┐ ┌───────┐ ┌──────────┐  │   │  │  │
│  │  │  │  │chatStore │ │sessionStore│ │uiStore│ │tableauStore│ │   │  │  │
│  │  │  │  └──────────┘ └────────────┘ └───────┘ └──────────┘  │   │  │  │
│  │  │  │  ┌──────────┐                                          │   │  │  │
│  │  │  │  │settings  │                                          │   │  │  │
│  │  │  │  │Store     │                                          │   │  │  │
│  │  │  │  └──────────┘                                          │   │  │  │
│  │  │  └──────────────────────────────────────────────────────┘   │  │  │
│  │  │                            │                                 │  │  │
│  │  │  ┌──────────────────────────────────────────────────────┐   │  │  │
│  │  │  │            服务层 (Services)                          │   │  │  │
│  │  │  │  ┌──────────┐ ┌────────────────────┐                  │   │  │  │
│  │  │  │  │APIClient │ │  StorageService    │                  │   │  │  │
│  │  │  │  └──────────┘ └────────────────────┘                  │   │  │  │
│  │  │  │  ┌──────────┐                                          │   │  │  │
│  │  │  │  │Tableau   │                                          │   │  │  │
│  │  │  │  │Service   │                                          │   │  │  │
│  │  │  │  └──────────┘                                          │   │  │  │
│  │  │  └──────────────────────────────────────────────────────┘   │  │  │
│  │  │                            │                                 │  │  │
│  │  │  ┌──────────────────────────────────────────────────────┐   │  │  │
│  │  │  │            工具层 (Utils)                             │   │  │  │
│  │  │  │  - formatters.ts  (数据格式化)                        │   │  │  │
│  │  │  │  - validators.ts  (输入验证)                          │   │  │  │
│  │  │  │  - markdown.ts    (Markdown 工具)                     │   │  │  │
│  │  │  │  - errorMessages.ts (错误消息映射)                    │   │  │  │
│  │  │  └──────────────────────────────────────────────────────┘   │  │  │
│  │  └─────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                    │                                     │
│                    tableau.extensions.1.latest.min.js                    │
│                         (Tableau Extensions API)                         │
└─────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ SSE / REST
                                     ▼
                    ┌─────────────────────────────────┐
                    │    FastAPI Backend              │
                    │  (Analytics Assistant Agents)   │
                    └─────────────────────────────────┘
```


### 2.2 目录结构

```
analytics_assistant_frontend/
├── public/
│   ├── manifest.trex                      # Tableau 扩展清单
│   ├── tableau.extensions.1.latest.min.js # Tableau Extensions API
│   └── favicon.ico
├── src/
│   ├── api/                               # API 层
│   │   ├── client.ts                      # HTTP 客户端（Axios + 拦截器）
│   │   ├── sessions.ts                    # 会话管理 API
│   │   ├── settings.ts                    # 设置 API
│   │   ├── feedback.ts                    # 反馈 API
│   │   └── types.ts                       # API 类型定义
│   ├── assets/                            # 静态资源
│   │   ├── logo.svg
│   │   └── styles/
│   │       ├── variables.css              # CSS 变量
│   │       └── main.css                   # 全局样式
│   ├── components/                        # Vue 组件
│   │   ├── layout/                        # 布局组件
│   │   │   ├── AppLayout.vue
│   │   │   ├── HeaderBar.vue
│   │   │   └── InputArea.vue
│   │   ├── chat/                          # 对话组件
│   │   │   ├── ChatContainer.vue
│   │   │   ├── MessageList.vue
│   │   │   ├── UserMessage.vue
│   │   │   ├── AIMessage.vue
│   │   │   └── ThinkingIndicator.vue
│   │   ├── content/                       # 内容展示组件
│   │   │   ├── MarkdownRenderer.vue
│   │   │   ├── DataTable.vue
│   │   │   ├── TableToolbar.vue
│   │   │   ├── DataChart.vue              # 数据图表（ECharts）
│   │   │   └── ChartToolbar.vue           # 图表工具栏
│   │   ├── settings/                      # 设置组件
│   │   │   ├── SettingsPanel.vue
│   │   │   └── DataSourceSelector.vue
│   │   ├── session/                       # 会话组件
│   │   │   ├── SessionList.vue            # 会话列表
│   │   │   └── SessionItem.vue            # 会话项
│   │   ├── feedback/                      # 反馈组件
│   │   │   ├── MessageActions.vue         # 消息操作按钮
│   │   │   ├── FeedbackDialog.vue         # 反馈对话框
│   │   │   └── SuggestedQuestions.vue     # 建议问题
│   │   ├── thinking/                      # 思考过程组件
│   │   │   ├── ThinkingSteps.vue          # 思考步骤列表
│   │   │   └── StepDetail.vue             # 步骤详情
│   │   └── common/                        # 通用组件
│   │       ├── ErrorMessage.vue
│   │       ├── LoadingSpinner.vue
│   │       └── EmptyState.vue
│   ├── composables/                       # 组合式函数
│   │   ├── useChat.ts                     # 对话管理（基于 Vercel AI SDK）
│   │   ├── useTableau.ts                  # Tableau 集成
│   │   ├── useResponsive.ts               # 响应式布局
│   │   ├── useFeedback.ts                 # 反馈管理
│   │   └── useChartConfig.ts              # 图表配置
│   ├── stores/                            # Pinia 状态管理
│   │   ├── chat.ts                        # 对话状态
│   │   ├── session.ts                     # 会话状态
│   │   ├── settings.ts                    # 设置状态
│   │   ├── tableau.ts                     # Tableau 状态
│   │   └── ui.ts                          # UI 状态
│   ├── types/                             # TypeScript 类型
│   │   ├── types.ts                       # 通用类型
│   │   ├── message.ts                     # 消息类型
│   │   ├── session.ts                     # 会话类型
│   │   ├── settings.ts                    # 设置类型
│   │   ├── chart.ts                       # 图表类型
│   │   ├── feedback.ts                    # 反馈类型
│   │   └── tableau.d.ts                   # Tableau API 类型
│   ├── utils/                             # 工具函数
│   │   ├── formatters.ts                  # 数据格式化
│   │   ├── validators.ts                  # 输入验证
│   │   ├── markdown.ts                    # Markdown 工具
│   │   ├── errorMessages.ts               # 错误消息映射
│   │   ├── chartUtils.ts                  # 图表工具
│   │   └── constants.ts                   # 常量定义
│   ├── views/                             # 页面视图
│   │   ├── WelcomeView.vue                # 欢迎页
│   │   └── ChatView.vue                   # 对话页
│   ├── App.vue                            # 根组件
│   ├── main.ts                            # 应用入口
│   └── router.ts                          # 路由配置
├── tests/                                 # 测试文件
│   ├── unit/                              # 单元测试
│   │   ├── components/
│   │   ├── stores/
│   │   └── utils/
│   └── properties/                        # 属性测试
│       ├── formatters.test.ts
│       └── validators.test.ts
├── .env.example                           # 环境变量示例
├── .eslintrc.js                           # ESLint 配置
├── .prettierrc                            # Prettier 配置
├── index.html                             # HTML 入口
├── package.json                           # 依赖配置
├── tsconfig.json                          # TypeScript 配置
├── vite.config.ts                         # Vite 配置
└── vitest.config.ts                       # Vitest 配置
```


## 3. 核心模块设计

### 3.1 Vercel AI SDK 集成

**文件**: `src/composables/useChat.ts`

**职责**: 使用 Vercel AI SDK 处理对话、流式输出、消息管理

**接口设计**:

```typescript
import { useChat } from '@ai-sdk/vue'
import { ref, computed } from 'vue'
import { useTableauStore } from '@/stores/tableau'
import { useSessionStore } from '@/stores/session'
import { useSettingsStore } from '@/stores/settings'

export function useChatComposable() {
  const tableauStore = useTableauStore()
  const sessionStore = useSessionStore()
  const settingsStore = useSettingsStore()
  
  // 使用 Vercel AI SDK 的 useChat hook
  const {
    messages,
    input,
    isLoading,
    error,
    append,
    reload,
    stop,
    setMessages
  } = useChat({
    // API 端点配置（根据环境自动选择）
    // 开发环境：使用 Vite 代理（相对路径）
    // 生产环境：使用完整 URL（需要后端 CORS 支持或同域部署）
    api: import.meta.env.DEV 
      ? '/api/chat/stream'  // 开发环境：Vite 代理转发
      : `${import.meta.env.VITE_API_BASE_URL}/api/chat/stream`,  // 生产环境：完整 URL
    body: computed(() => ({
      datasourceName: tableauStore.selectedDataSource?.name,
      sessionId: sessionStore.sessionId,
      language: settingsStore.language,
      analysisDepth: settingsStore.analysisDepth
    })),
    onFinish: (message) => {
      // 保存会话
      sessionStore.saveCurrentSession(messages.value)
    },
    onError: (error) => {
      console.error('Chat error:', error)
    }
  })
  
  // 发送消息（支持多轮对话上下文）
  const sendMessage = async (content: string) => {
    // 手动裁剪消息：只发送最近 10 轮对话（20 条消息）
    const maxMessages = 20 // 10 轮对话 = 20 条消息（用户+AI）
    
    // 如果消息数量超过限制，先裁剪再发送
    if (messages.value.length >= maxMessages) {
      const trimmedMessages = messages.value.slice(-maxMessages + 1) // 保留最近 19 条，加上新消息正好 20 条
      setMessages(trimmedMessages)
    }
    
    // 发送新消息（Vercel AI SDK 会自动将所有 messages 发送到后端）
    await append({
      role: 'user',
      content
    })
  }
  
  // 重新生成最后一条回复
  const regenerate = async () => {
    await reload()
  }
  
  // 停止生成
  const stopGeneration = () => {
    stop()
  }
  
  // 清空对话
  const clearMessages = () => {
    setMessages([])
    sessionStore.createNewSession()
  }
  
  return {
    messages,
    input,
    isLoading,
    error,
    sendMessage,
    regenerate,
    stopGeneration,
    clearMessages
  }
}
```

**Vercel AI SDK 自动处理**:
- ✅ SSE 流式输出
- ✅ 自动重连
- ✅ 错误恢复
- ✅ 消息状态管理

**消息裁剪策略**:
- 前端在发送消息前手动裁剪（在 `sendMessage()` 函数中）
- 只发送最近 10 轮对话（20 条消息：10 条用户 + 10 条 AI）
- 保持完整的对话历史在前端（用于显示和会话保存）
- 后端只接收裁剪后的上下文（减少 Token 消耗）
- **注意**：`@ai-sdk/vue` 的 `useChat()` 可能不支持 `onRequest` 回调，因此采用手动裁剪方案

### 3.2 状态管理（Pinia Stores）

#### 3.2.1 chatStore（对话状态）

**文件**: `src/stores/chat.ts`

**职责**: 管理对话消息、处理状态、建议问题

**状态设计**:

```typescript
export interface ChatState {
  // 消息列表（由 Vercel AI SDK 管理）
  messages: Message[]
  
  // 处理状态
  isProcessing: boolean
  processingStage: ProcessingStage | null
  
  // 建议问题
  suggestedQuestions: string[]
  
  // 思考步骤
  thinkingSteps: ThinkingStep[]
  
  // 错误信息
  error: string | null
}

export type ProcessingStage = 
  | 'understanding'  // 理解问题
  | 'mapping'        // 字段映射
  | 'building'       // 构建查询
  | 'executing'      // 执行分析
  | 'generating'     // 生成洞察

export interface ThinkingStep {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  details?: string
  timestamp: number
}

export const useChatStore = defineStore('chat', {
  state: (): ChatState => ({
    messages: [],
    isProcessing: false,
    processingStage: null,
    suggestedQuestions: [],
    thinkingSteps: [],
    error: null
  }),
  
  actions: {
    // 更新处理阶段
    updateProcessingStage(stage: ProcessingStage | null): void
    
    // 更新建议问题
    updateSuggestedQuestions(questions: string[]): void
    
    // 更新思考步骤
    updateThinkingSteps(steps: ThinkingStep[]): void
    
    // 添加思考步骤
    addThinkingStep(step: ThinkingStep): void
    
    // 更新步骤状态
    updateStepStatus(stepId: string, status: ThinkingStep['status'], details?: string): void
  }
})
```

#### 3.2.2 tableauStore（Tableau 状态）

**文件**: `src/stores/tableau.ts`

**职责**: 管理 Tableau 集成、数据源信息

**状态设计**:

```typescript
export interface TableauState {
  // 初始化状态
  isInitialized: boolean
  isInitializing: boolean
  initError: string | null
  
  // 仪表板信息
  dashboardName: string
  
  // 数据源列表
  dataSources: DataSourceInfo[]
  selectedDataSourceId: string | null
  
  // Tableau 环境信息
  tableauContext: TableauContext | null
}

export interface DataSourceInfo {
  id: string
  name: string
}

export type TableauContext = 'desktop' | 'server' | 'cloud'

export const useTableauStore = defineStore('tableau', {
  state: (): TableauState => ({
    isInitialized: false,
    isInitializing: false,
    initError: null,
    dashboardName: '',
    dataSources: [],
    selectedDataSourceId: null,
    tableauContext: null
  }),
  
  getters: {
    selectedDataSource: (state) => {
      return state.dataSources.find(ds => ds.id === state.selectedDataSourceId)
    },
    
    isInTableau: () => {
      return typeof window !== 'undefined' && 'tableau' in window
    },
    
    // 是否可以使用（有可用数据源）
    canUse: (state) => {
      return state.isInitialized && state.dataSources.length > 0
    }
  },
  
  actions: {
    // 初始化 Tableau Extension
    async initialize(): Promise<boolean>
    
    // 选择数据源
    selectDataSource(id: string): void
    
    // 重置状态
    reset(): void
  }
})
```


#### 3.2.3 sessionStore（会话状态）

**文件**: `src/stores/session.ts`

**职责**: 管理会话、与后端 API 同步

**状态设计**:

```typescript
export interface SessionState {
  // 当前会话 ID
  sessionId: string
  
  // 所有会话列表（从后端加载）
  sessions: Session[]
  
  // 加载状态
  isLoading: boolean
  
  // Tableau 用户名（从 Tableau Extensions API 获取）
  tableauUsername: string | null
}

export interface Session {
  id: string              // UUID v4
  tableauUsername: string // Tableau 用户名
  title: string           // 会话标题（自动生成或用户编辑）
  messages: Message[]     // 消息列表
  createdAt: number
  updatedAt: number
}

export const useSessionStore = defineStore('session', {
  state: (): SessionState => ({
    sessionId: '',
    sessions: [],
    isLoading: false,
    tableauUsername: null
  }),
  
  actions: {
    // 初始化（获取 Tableau 用户信息）
    async initialize(): Promise<void>
    
    // 创建新会话
    async createNewSession(): Promise<void>
    
    // 保存当前会话到后端
    async saveCurrentSession(messages: Message[]): Promise<void>
    
    // 从后端加载会话列表
    async loadSessions(): Promise<void>
    
    // 从后端加载特定会话
    async loadSession(sessionId: string): Promise<void>
    
    // 删除会话（后端）
    async deleteSession(sessionId: string): Promise<void>
    
    // 更新会话标题
    async updateSessionTitle(sessionId: string, title: string): Promise<void>
    
    // 导出会话
    async exportSession(sessionId: string, format: 'markdown' | 'pdf'): Promise<void>
  }
})
```

**会话恢复策略**：

Session ID 的生成、存储和恢复机制：

1. **初始化流程**：
   ```typescript
   async initialize() {
     // 1. 获取 Tableau 用户信息
     const tableauUser = getTableauUser()
     this.tableauUsername = tableauUser?.username || null
     
     // 2. 从后端获取该用户的最后一个会话（按 updatedAt 排序）
     const response = await getSessions() // 后端自动根据 tableauUsername 过滤
     
     if (response.sessions.length > 0) {
       // 3. 恢复最后一个会话
       const lastSession = response.sessions[0]
       this.sessionId = lastSession.id
       await this.loadSession(lastSession.id)
     } else {
       // 4. 如果没有历史会话，生成新 UUID v4 Session ID
       this.sessionId = crypto.randomUUID()
     }
   }
   ```

2. **Session ID 存储位置**：
   - Session ID **只存在 Pinia store 内存中**
   - 不存储在 localStorage 或 sessionStorage
   - 刷新页面会丢失，重新调用 `initialize()` 恢复

3. **新对话创建**：
   ```typescript
   async createNewSession() {
     // 生成新 UUID v4
     this.sessionId = crypto.randomUUID()
     // 清空当前消息
     const chatStore = useChatStore()
     chatStore.clearMessages()
   }
   ```

4. **跨设备同步**：
   - 用户在设备 A 创建会话 → 保存到后端数据库
   - 用户在设备 B 打开扩展 → `initialize()` 自动加载最后一个会话
   - Tableau 自动认证，无需手动登录
```

#### 3.2.4 settingsStore（设置状态）

**文件**: `src/stores/settings.ts`

**职责**: 管理用户设置、与后端 API 同步

**状态设计**:

```typescript
export interface SettingsState {
  // 语言
  language: 'zh' | 'en'
  
  // 分析深度
  analysisDepth: 'detailed' | 'comprehensive'
  
  // 主题
  theme: 'light' | 'dark' | 'system'
  
  // 默认数据源
  defaultDataSourceId: string | null
  
  // 是否显示思考过程
  showThinkingProcess: boolean
  
  // API 配置
  apiBaseUrl: string
  
  // 加载状态
  isLoading: boolean
  
  // Tableau 用户名
  tableauUsername: string | null
}

export const useSettingsStore = defineStore('settings', {
  state: (): SettingsState => ({
    language: 'zh',
    analysisDepth: 'detailed',
    theme: 'light',
    defaultDataSourceId: null,
    showThinkingProcess: true,
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
    isLoading: false,
    tableauUsername: null
  }),
  
  actions: {
    // 初始化（获取 Tableau 用户信息）
    async initialize(): Promise<void>
    
    // 从后端加载设置
    async loadSettings(): Promise<void>
    
    // 保存设置到后端
    async saveSettings(): Promise<void>
    
    // 设置语言
    async setLanguage(lang: 'zh' | 'en'): Promise<void>
    
    // 设置分析深度
    async setAnalysisDepth(depth: 'detailed' | 'comprehensive'): Promise<void>
    
    // 设置主题
    async setTheme(theme: 'light' | 'dark' | 'system'): Promise<void>
    
    // 设置默认数据源
    async setDefaultDataSource(dataSourceId: string): Promise<void>
    
    // 切换思考过程显示
    async toggleThinkingProcess(): Promise<void>
  }
})
```


### 3.3 数据模型

#### 3.3.1 消息模型

**文件**: `src/types/message.ts`

```typescript
// 基础消息（兼容 Vercel AI SDK）
export interface BaseMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  createdAt?: Date
}

// AI 消息扩展
export interface AIMessage extends BaseMessage {
  role: 'assistant'
  data?: TableData          // 查询结果数据
  chartConfig?: ChartConfig // 图表配置
  suggestedQuestions?: string[] // 建议问题
  thinkingSteps?: ThinkingStep[] // 思考步骤
}

// 用户消息
export interface UserMessage extends BaseMessage {
  role: 'user'
}

// 系统消息
export interface SystemMessage extends BaseMessage {
  role: 'system'
  level?: 'info' | 'warning' | 'error'
}

// 消息联合类型
export type Message = UserMessage | AIMessage | SystemMessage

// 表格数据
export interface TableData {
  columns: ColumnDef[]
  rows: Record<string, any>[]
  totalCount: number
}

export interface ColumnDef {
  key: string
  label: string
  type: 'string' | 'number' | 'date'
  align?: 'left' | 'center' | 'right'
}

// 图表配置
export interface ChartConfig {
  type: 'line' | 'bar' | 'pie' | 'scatter'
  title?: string
  xAxis?: AxisConfig
  yAxis?: AxisConfig
  series: SeriesConfig[]
  legend?: LegendConfig
}

export interface AxisConfig {
  name: string
  type: 'category' | 'value' | 'time'
  data?: any[]
}

export interface SeriesConfig {
  name: string
  type: 'line' | 'bar' | 'pie' | 'scatter'
  data: any[]
  smooth?: boolean
  areaStyle?: any
}

export interface LegendConfig {
  show: boolean
  position?: 'top' | 'bottom' | 'left' | 'right'
}

// 思考步骤
export interface ThinkingStep {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  details?: string
  timestamp: number
}
```

#### 3.3.2 API 请求/响应模型

**文件**: `src/api/types.ts`

```typescript
// 聊天请求（Vercel AI SDK 格式）
export interface ChatRequest {
  messages: Message[]  // 完整对话历史
  datasourceName: string
  language?: 'zh' | 'en'
  analysisDepth?: 'detailed' | 'comprehensive'
  sessionId?: string
}

// 会话 API
export interface CreateSessionRequest {
  title?: string
  tableauUsername: string  // Tableau 用户名
}

export interface CreateSessionResponse {
  sessionId: string
  createdAt: number
}

export interface UpdateSessionRequest {
  title?: string
  messages?: Message[]
}

export interface GetSessionsResponse {
  sessions: Session[]
  total: number
}

// 设置 API
export interface UserSettings {
  tableauUsername: string  // Tableau 用户名
  language: 'zh' | 'en'
  analysisDepth: 'detailed' | 'comprehensive'
  theme: 'light' | 'dark' | 'system'
  defaultDataSourceId: string | null
  showThinkingProcess: boolean
}

export interface UpdateSettingsRequest extends Partial<Omit<UserSettings, 'tableauUsername'>> {}

// 反馈请求
export interface FeedbackRequest {
  messageId: string
  type: 'positive' | 'negative'
  reason?: string
  comment?: string
  tableauUsername: string  // Tableau 用户名
}

// SSE 事件数据（后端返回）
export interface StreamEvent {
  type: 'token' | 'data' | 'chart' | 'suggestions' | 'thinking' | 'complete' | 'error'
  content?: string
  data?: TableData
  chartConfig?: ChartConfig
  suggestedQuestions?: string[]
  thinkingStep?: ThinkingStep
}
```

#### 3.3.3 反馈模型

**文件**: `src/types/feedback.ts`

```typescript
export interface MessageFeedback {
  messageId: string
  type: 'positive' | 'negative'
  reason?: FeedbackReason
  comment?: string
  timestamp: number
}

export type FeedbackReason =
  | 'accurate'        // 准确
  | 'helpful'         // 有帮助
  | 'inaccurate'      // 不准确
  | 'incomplete'      // 不完整
  | 'irrelevant'      // 不相关
  | 'unclear'         // 不清晰
  | 'other'           // 其他
```


### 3.4 核心组件设计

#### 3.4.1 AppLayout（应用布局）

**文件**: `src/components/layout/AppLayout.vue`

**职责**: 管理三区域布局

**Props**: 无

**结构**:
```vue
<template>
  <div class="app-layout">
    <HeaderBar />
    <div class="content-area">
      <router-view />
    </div>
    <InputArea v-if="showInput" />
  </div>
</template>
```

**样式**:
```css
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.content-area {
  flex: 1;
  overflow-y: auto;
}
```

#### 3.4.2 ChatContainer（对话容器）

**文件**: `src/components/chat/ChatContainer.vue`

**职责**: 管理消息列表、自动滚动

**Props**:
```typescript
interface ChatContainerProps {
  messages: Message[]
  isProcessing: boolean
}
```

**功能**:
- 渲染消息列表
- 自动滚动到最新消息
- 虚拟滚动（优化性能）

#### 3.4.3 AIMessage（AI 消息）

**文件**: `src/components/chat/AIMessage.vue`

**职责**: 渲染 AI 消息、支持流式输出

**Props**:
```typescript
interface AIMessageProps {
  message: AIMessage
  isStreaming?: boolean
}
```

**结构**:
```vue
<template>
  <div class="ai-message">
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      <MarkdownRenderer :content="message.content" :streaming="isStreaming" />
      <DataTable v-if="message.data" :data="message.data" />
    </div>
    <div class="message-actions">
      <el-button text @click="copyContent">复制</el-button>
    </div>
  </div>
</template>
```


#### 3.4.4 MarkdownRenderer（Markdown 渲染器）

**文件**: `src/components/content/MarkdownRenderer.vue`

**职责**: 渲染 Markdown 内容、语法高亮

**Props**:
```typescript
interface MarkdownRendererProps {
  content: string
  streaming?: boolean  // 是否流式渲染
}
```

**配置**:
```typescript
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

const md = new MarkdownIt({
  html: false,          // 禁用 HTML 标签（安全）
  linkify: true,        // 自动链接
  typographer: true,    // 排版优化
  highlight: (code: string, lang: string) => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch (e) {
        console.error('Highlight error:', e)
      }
    }
    return ''
  }
})
```

**安全性**:
- 禁用 HTML 标签
- 转义特殊字符
- XSS 防护

#### 3.4.5 DataTable（数据表格）

**文件**: `src/components/content/DataTable.vue`

**职责**: 渲染数据表格、支持排序、分页、导出

**Props**:
```typescript
interface DataTableProps {
  data: TableData
  pageSize?: number     // 默认 10
  sortable?: boolean    // 默认 true
  exportable?: boolean  // 默认 true
}
```

**功能**:
- 分页（固定 10 条/页）
- 排序（升序→降序→原始顺序）
- 导出 CSV
- 数值格式化（千分位、小数）
- 水平滚动（列数过多时）

**工具栏**:
```
[查询详情]     共 25 条  ◀ 1/3 ▶     [导出 CSV]
```


#### 3.4.6 ThinkingIndicator（思考指示器）

**文件**: `src/components/chat/ThinkingIndicator.vue`

**职责**: 显示 AI 处理状态

**Props**:
```typescript
interface ThinkingIndicatorProps {
  stage: ProcessingStage | null
  error?: string
}
```

**显示效果**:
```vue
<template>
  <div class="thinking-indicator" :class="{ error: !!error }">
    <div class="dots-animation">
      <span></span>
      <span></span>
      <span></span>
    </div>
    <div class="stage-text">{{ stageText }}</div>
  </div>
</template>
```

**阶段文字**:
```typescript
const STAGE_LABELS: Record<ProcessingStage, string> = {
  understanding: '理解问题...',
  mapping: '字段映射...',
  building: '构建查询...',
  executing: '执行分析...',
  generating: '生成洞察...'
}
```

#### 3.4.7 InputArea（输入区域）

**文件**: `src/components/layout/InputArea.vue`

**职责**: 处理用户输入、发送消息

**功能**:
- 多行文本输入（自动扩展）
- Enter 发送、Shift+Enter 换行
- 输入验证（空白字符、长度限制）
- 字符计数器（接近 2000 字符时显示）
- 禁用状态（AI 处理时 或 无可用数据源时）
- 停止生成按钮（AI 回复时显示）

**结构**:
```vue
<template>
  <div class="input-area">
    <el-alert
      v-if="!tableauStore.canUse"
      type="error"
      :closable="false"
      show-icon
    >
      {{ errorMessage }}
    </el-alert>
    
    <el-input
      v-model="inputText"
      type="textarea"
      :autosize="{ minRows: 1, maxRows: 4 }"
      :placeholder="placeholder"
      :disabled="isProcessing || !tableauStore.canUse"
      @keydown.enter.exact.prevent="handleSend"
      @keydown.enter.shift.exact="handleNewLine"
    />
    <div class="input-actions">
      <span v-if="showCharCount" class="char-count">
        {{ inputText.length }} / 2000
      </span>
      <el-button
        v-if="isProcessing"
        type="danger"
        @click="handleStop"
      >
        ⏹️ 停止生成
      </el-button>
      <el-button
        v-else
        type="primary"
        :disabled="!canSend || !tableauStore.canUse"
        @click="handleSend"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTableauStore } from '@/stores/tableau'
import { useChatComposable } from '@/composables/useChat'

const tableauStore = useTableauStore()
const { isLoading, stopGeneration } = useChatComposable()

const errorMessage = computed(() => {
  if (tableauStore.initError) {
    return `无法获取数据源：${tableauStore.initError}`
  }
  if (tableauStore.dataSources.length === 0) {
    return '当前仪表板没有可用数据源'
  }
  return ''
})

const handleStop = () => {
  stopGeneration()
}
</script>
```

#### 3.4.8 MessageActions（消息操作）

**文件**: `src/components/feedback/MessageActions.vue`

**职责**: 显示消息操作按钮（点赞/点踩/复制/重新生成）

**Props**:
```typescript
interface MessageActionsProps {
  messageId: string
  content: string
  role: 'user' | 'assistant'
  canRegenerate: boolean
}
```

**结构**:
```vue
<template>
  <div class="message-actions">
    <el-button-group v-if="role === 'assistant'">
      <el-button
        text
        :icon="feedback === 'positive' ? 'ThumbsUpFilled' : 'ThumbsUp'"
        @click="handleFeedback('positive')"
      >
        {{ feedback === 'positive' ? '已点赞' : '' }}
      </el-button>
      <el-button
        text
        :icon="feedback === 'negative' ? 'ThumbsDownFilled' : 'ThumbsDown'"
        @click="handleFeedback('negative')"
      >
        {{ feedback === 'negative' ? '已点踩' : '' }}
      </el-button>
    </el-button-group>
    
    <el-button text icon="CopyDocument" @click="handleCopy">
      复制
    </el-button>
    
    <el-button
      v-if="canRegenerate && role === 'assistant'"
      text
      icon="Refresh"
      @click="handleRegenerate"
    >
      重新生成
    </el-button>
  </div>
</template>
```

#### 3.4.9 SuggestedQuestions（建议问题）

**文件**: `src/components/feedback/SuggestedQuestions.vue`

**职责**: 显示 AI 建议的相关问题

**Props**:
```typescript
interface SuggestedQuestionsProps {
  questions: string[]
}
```

**结构**:
```vue
<template>
  <div v-if="questions.length > 0" class="suggested-questions">
    <div class="label">💡 您可能还想问：</div>
    <div class="questions">
      <el-button
        v-for="(question, index) in questions"
        :key="index"
        type="info"
        plain
        @click="handleQuestionClick(question)"
      >
        {{ question }}
      </el-button>
    </div>
  </div>
</template>
```

#### 3.4.10 DataChart（数据图表）

**文件**: `src/components/content/DataChart.vue`

**职责**: 使用 ECharts 渲染数据图表

**Props**:
```typescript
interface DataChartProps {
  chartConfig: ChartConfig
  data: TableData
}
```

**结构**:
```vue
<template>
  <div class="data-chart">
    <ChartToolbar
      :chart-type="chartConfig.type"
      @export="handleExport"
      @switch-view="$emit('switch-view')"
    />
    <v-chart
      :option="chartOption"
      :autoresize="true"
      style="height: 400px"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, PieChart, ScatterChart } from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
} from 'echarts/components'

// 注册 ECharts 组件
use([
  CanvasRenderer,
  LineChart,
  BarChart,
  PieChart,
  ScatterChart,
  TitleComponent,
  TooltipComponent,
  LegendComponent,
  GridComponent
])

const chartOption = computed(() => {
  // 根据 chartConfig 生成 ECharts 配置
  return {
    title: {
      text: props.chartConfig.title
    },
    tooltip: {
      trigger: 'axis'
    },
    legend: props.chartConfig.legend,
    xAxis: props.chartConfig.xAxis,
    yAxis: props.chartConfig.yAxis,
    series: props.chartConfig.series
  }
})
</script>
```

#### 3.4.11 表格与图表切换机制

**实现方案**：

在 `AIMessage` 组件中，为每条包含 `data` 和 `chartConfig` 的消息添加视图切换功能。

**示例代码**：

```vue
<!-- src/components/chat/AIMessage.vue -->
<template>
  <div class="ai-message">
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      <MarkdownRenderer :content="message.content" :streaming="isStreaming" />
      
      <!-- 数据展示区域 -->
      <div v-if="message.data" class="data-display">
        <!-- 视图切换按钮 -->
        <el-button-group class="view-switcher">
          <el-button
            :type="viewMode === 'table' ? 'primary' : 'default'"
            @click="viewMode = 'table'"
          >
            📊 表格
          </el-button>
          <el-button
            v-if="message.chartConfig"
            :type="viewMode === 'chart' ? 'primary' : 'default'"
            @click="viewMode = 'chart'"
          >
            📈 图表
          </el-button>
        </el-button-group>
        
        <!-- 表格视图 -->
        <DataTable 
          v-show="viewMode === 'table'" 
          :data="message.data" 
        />
        
        <!-- 图表视图 -->
        <DataChart 
          v-if="message.chartConfig"
          v-show="viewMode === 'chart'" 
          :data="message.data" 
          :chart-config="message.chartConfig" 
        />
      </div>
    </div>
    <MessageActions :message="message" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  message: AIMessage
  isStreaming?: boolean
}>()

// 视图模式：table（表格）或 chart（图表）
const viewMode = ref<'table' | 'chart'>('table')
</script>

<style scoped>
.view-switcher {
  margin-bottom: 12px;
}

.data-display {
  margin-top: 16px;
}
</style>
```

**说明**：
- 默认显示表格视图
- 如果 AI 返回了 `chartConfig`，显示"图表"按钮
- 用户点击按钮切换视图
- 使用 `v-show` 而不是 `v-if`，避免重复渲染

#### 3.4.12 ThinkingSteps（思考步骤）

**文件**: `src/components/thinking/ThinkingSteps.vue`

**职责**: 显示 AI 思考过程的步骤列表

**Props**:
```typescript
interface ThinkingStepsProps {
  steps: ThinkingStep[]
  collapsed?: boolean
}
```

**结构**:
```vue
<template>
  <div class="thinking-steps">
    <div class="header" @click="toggleCollapse">
      <span class="title">
        {{ collapsed ? '▶' : '▼' }} AI 思考过程
      </span>
    </div>
    
    <el-collapse-transition>
      <div v-show="!collapsed" class="steps-list">
        <div
          v-for="step in steps"
          :key="step.id"
          class="step-item"
          :class="step.status"
        >
          <div class="step-header">
            <span class="status-icon">
              <el-icon v-if="step.status === 'completed'"><Check /></el-icon>
              <el-icon v-else-if="step.status === 'failed'"><Close /></el-icon>
              <el-icon v-else-if="step.status === 'running'" class="rotating"><Loading /></el-icon>
              <el-icon v-else><Clock /></el-icon>
            </span>
            <span class="step-name">{{ step.name }}</span>
          </div>
          <div v-if="step.details" class="step-details">
            {{ step.details }}
          </div>
        </div>
      </div>
    </el-collapse-transition>
  </div>
</template>

<style scoped>
.rotating {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
```


## 4. 数据流设计

### 4.1 消息发送流程

```
用户输入 ──► InputArea
              │
              ▼
        验证输入（非空、长度）
              │
              ▼
        useChatComposable().sendMessage()
              │
              ├──► Vercel AI SDK 自动添加用户消息到 messages[]
              │
              ├──► Vercel AI SDK 自动创建 SSE 连接
              │
              ├──► 构建请求（messages, datasourceName, language, analysisDepth）
              │
              ▼
        Vercel AI SDK 发送请求到后端
              │
              ▼
        后端 /api/chat/stream
              │
              ▼
        SSE 事件流（Vercel AI SDK 自动处理）
```

### 4.2 SSE 事件处理流程

```
SSE 事件 ──► Vercel AI SDK 自动处理
              │
              ▼
        自动更新 messages[] 状态
              │
              ├──► token 事件
              │     └──► 实时追加到当前消息
              │
              ├──► 自动处理重连
              │     └──► 指数退避策略
              │
              ├──► 自动错误恢复
              │     └──► 错误回调
              │
              └──► complete 事件
                    ├──► 触发 onFinish 回调
                    └──► 保存会话到后端
```

**说明**：
- Vercel AI SDK 自动处理所有 SSE 事件
- 无需手动实现 SSE 客户端
- 自动管理消息状态和重连逻辑

### 4.3 Tableau 初始化流程

```
应用启动 ──► main.ts
              │
              ▼
        tableauStore.initialize()
              │
              ├──► 检查 Tableau 环境
              │     └──► window.tableau 是否存在
              │
              ├──► 初始化 Tableau Extensions API
              │     └──► tableau.extensions.initializeAsync()
              │
              ├──► 获取仪表板信息
              │     └──► tableau.extensions.dashboardContent.dashboard
              │
              ├──► 获取数据源列表
              │     └──► 遍历 dashboard.worksheets，合并所有数据源并去重
              │
              └──► 选择默认数据源
                    └──► selectedDataSourceId = dataSources[0].id
```

### 4.4 应用初始化顺序

**启动流程（必须按此顺序，避免竞态条件）**:

```typescript
// src/main.ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import App from './App.vue'
import router from './router'

const app = createApp(App)
const pinia = createPinia()

// 1. 安装全局插件
app.use(pinia)
app.use(ElementPlus)
app.use(router)

// 2. 挂载应用
app.mount('#app')

// 3. 并行初始化 stores（避免串行等待）
import { useTableauStore } from '@/stores/tableau'
import { useSessionStore } from '@/stores/session'
import { useSettingsStore } from '@/stores/settings'

const tableauStore = useTableauStore()
const sessionStore = useSessionStore()
const settingsStore = useSettingsStore()

Promise.all([
  tableauStore.initialize(),   // 获取 Tableau 用户、数据源
  sessionStore.initialize(),   // 获取 Tableau 用户，恢复或创建会话
  settingsStore.initialize()   // 从后端加载用户设置
]).then(() => {
  console.log('Application initialized')
  // 路由到 ChatView（显示欢迎页或历史对话）
}).catch((error) => {
  console.error('Initialization failed:', error)
  // 显示错误提示
})
```

**重要说明**：
- 步骤 3 的三个 store 初始化应该**并行**执行（`Promise.all`），而不是串行等待
- 如果串行执行，启动时间会增加 3 倍
- 如果 Tableau 初始化失败，应该显示友好的错误提示并禁用功能


## 5. 关键技术实现

### 5.1 流式输出方案说明

**方案选择**: 使用 Vercel AI SDK 处理 SSE 流式输出

**原因**:
- ✅ Vercel AI SDK 自动处理 SSE 连接、解析、重连
- ✅ 内置错误恢复和超时处理
- ✅ 生产级别的稳定性
- ✅ 节省 2-3 天开发时间

**前端无需自己实现 SSE 客户端**，Vercel AI SDK 的 `useChat()` hook 已经包含完整的 SSE 处理逻辑。

**后端 SSE 事件格式要求**:

后端需要返回与 Vercel AI SDK 兼容的 SSE 事件格式。标准格式如下：

```
data: {"type":"token","content":"你好"}

data: {"type":"data","data":{"columns":[...],"rows":[...]}}

data: {"type":"complete"}
```

**⚠️ 重要警告 - Vercel AI SDK 自定义事件限制**：
- Vercel AI SDK 的 `useChat()` 原生只支持 `text` 和 `tool_calls` 事件的自动处理
- 自定义事件（`data`、`chart`、`suggestions`、`thinking`）需要前端手动解析
- **推荐方案**：将自定义数据嵌入到 `text` 事件的 metadata 或 annotations 字段中
- **备选方案**：前端单独实现 SSE 事件监听器，在 `useChat()` 之外处理自定义事件
- **最小联调要求**：开发初期必须进行前后端协议联调测试，确保事件格式兼容

**重要说明**：
- 后端必须实现与 `@ai-sdk/vue` 的 `useChat()` hook 兼容的 SSE 响应协议
- 建议在开发初期进行最小联调用例测试，确保前后端协议一致
- 如果后端使用 LangChain 的流式输出，需要添加适配层将事件格式转换为 Vercel AI SDK 兼容格式

**事件类型契约**:

| 事件类型 | 字段 | 说明 | 处理方式 |
|---------|------|------|----------|
| `token` | `content: string` | 流式文本内容（逐字输出） | Vercel AI SDK 自动处理 |
| `data` | `data: TableData` | 查询结果数据 | 需要前端手动解析 |
| `chart` | `chartConfig: ChartConfig` | 图表配置 | 需要前端手动解析 |
| `suggestions` | `suggestedQuestions: string[]` | 建议问题 | 需要前端手动解析 |
| `thinking` | `thinkingStep: ThinkingStep` | 思考步骤（更新处理阶段） | 需要前端手动解析 |
| `complete` | 无 | 流式输出完成 | Vercel AI SDK 自动处理 |
| `error` | `error: string` | 错误信息 | Vercel AI SDK 自动处理 |

**完整 SSE 响应示例**:

```
# 1. 思考步骤开始
data: {"type":"thinking","thinkingStep":{"id":"step-1","name":"理解问题","status":"running","timestamp":1707234567890}}

# 2. 流式文本输出（多次）
data: {"type":"token","content":"根据"}

data: {"type":"token","content":"您的"}

data: {"type":"token","content":"问题"}

# 3. 思考步骤完成
data: {"type":"thinking","thinkingStep":{"id":"step-1","name":"理解问题","status":"completed","timestamp":1707234568000}}

# 4. 查询结果数据
data: {"type":"data","data":{"columns":[{"key":"region","label":"地区","type":"string"},{"key":"sales","label":"销售额","type":"number"}],"rows":[{"region":"华东","sales":1234567},{"region":"华南","sales":987654}],"totalCount":2}}

# 5. 图表配置
data: {"type":"chart","chartConfig":{"type":"bar","title":"各地区销售额","xAxis":{"name":"地区","type":"category","data":["华东","华南"]},"yAxis":{"name":"销售额","type":"value"},"series":[{"name":"销售额","type":"bar","data":[1234567,987654]}]}}

# 6. 建议问题
data: {"type":"suggestions","suggestedQuestions":["按月份查看销售趋势","对比去年同期数据","查看销售额前10的产品"]}

# 7. 流式输出完成
data: {"type":"complete"}
```

**错误响应示例**:

```
# 错误情况
data: {"type":"error","error":"数据源连接失败，请检查 Tableau 连接"}
```

**前端处理自定义事件的方案**:

由于 Vercel AI SDK 不自动处理自定义事件，前端需要：

1. **方案 A（推荐）**：在 `onFinish` 回调中解析消息内容
   ```typescript
   onFinish: (message) => {
     // 解析消息中的自定义数据
     try {
       const customData = JSON.parse(message.content)
       if (customData.type === 'data') {
         // 处理表格数据
       } else if (customData.type === 'chart') {
         // 处理图表配置
       }
     } catch (e) {
       // 正常文本消息
     }
   }
   ```

2. **方案 B（备选）**：单独实现 SSE 监听器
   ```typescript
   const eventSource = new EventSource('/api/chat/stream')
   eventSource.addEventListener('data', (e) => {
     const event = JSON.parse(e.data)
     if (event.type === 'data') {
       // 处理表格数据
     }
   })
   ```

**重连和错误恢复**:
- Vercel AI SDK 自动处理重连（指数退避策略）
- 自动处理超时和网络错误
- 前端只需处理 `onError` 回调

### 5.2 Tableau Extensions API 集成

**初始化**:

```typescript
// src/utils/tableau.ts
export async function initializeTableauExtension(): Promise<void> {
  if (!isInTableauEnvironment()) {
    throw new Error('Not in Tableau environment')
  }

  await tableau.extensions.initializeAsync()
}

export function isInTableauEnvironment(): boolean {
  return typeof window !== 'undefined' && 'tableau' in window
}

// 获取当前 Tableau 用户信息
export function getTableauUser(): { username: string; displayName: string } | null {
  if (!isInTableauEnvironment()) {
    return null
  }
  
  const user = tableau.extensions.environment.user
  return {
    username: user?.username || 'anonymous',
    displayName: user?.displayName || 'Anonymous User'
  }
}

// 获取当前仪表板的所有数据源（遍历所有 worksheet 并去重）
export async function getAllDataSources(): Promise<DataSourceInfo[]> {
  const dashboard = tableau.extensions.dashboardContent.dashboard
  const worksheets = dashboard.worksheets
  
  if (worksheets.length === 0) {
    return []
  }
  
  // 遍历当前仪表板的所有 worksheet，收集数据源
  const dataSourceMap = new Map<string, DataSourceInfo>()
  
  for (const worksheet of worksheets) {
    try {
      const dataSources = await worksheet.getDataSourcesAsync()
      for (const ds of dataSources) {
        // 使用 id 去重
        if (!dataSourceMap.has(ds.id)) {
          dataSourceMap.set(ds.id, {
            id: ds.id,
            name: ds.name
          })
        }
      }
    } catch (error) {
      console.warn(`Failed to get data sources from worksheet ${worksheet.name}:`, error)
      // 继续处理其他 worksheet
    }
  }
  
  return Array.from(dataSourceMap.values())
}

export function getDashboardName(): string {
  return tableau.extensions.dashboardContent.dashboard.name
}

export function getTableauContext(): 'desktop' | 'server' | 'cloud' {
  const context = tableau.extensions.environment.context
  return context as 'desktop' | 'server' | 'cloud'
}
```

**重要说明**:
- Tableau Extensions API 只能获取数据源名称（`name`），无法直接获取 LUID
- 前端传递 `datasourceName` 给后端
- 后端通过 GraphQL 将名称转换为 LUID
- **不允许手动输入数据源名称**，必须从 Tableau API 获取的数据源列表中选择
- 如果 Tableau API 调用失败或数据源列表为空，禁用输入功能并显示错误提示
- **使用 `tableau.extensions.environment.user` 获取当前用户信息**，用于后端 API 的用户身份识别
- **获取的是"当前仪表板（dashboard）的数据源"**，通过遍历 `dashboard.worksheets` 并调用 `getDataSourcesAsync()` 获取，然后去重
- **不是获取"所有已发布的数据源"**，只获取当前仪表板使用的数据源

### 5.3 会话和设置的后端 API 集成

**存储方案**: 会话和设置数据存储在后端数据库，使用 Tableau 用户身份进行数据隔离

**会话管理 API**:

```typescript
// src/api/sessions.ts
import apiClient from './client'

// 创建新会话
export async function createSession(title?: string): Promise<CreateSessionResponse> {
  const response = await apiClient.post('/api/sessions', { title })
  return response.data
}

// 获取所有会话（当前 Tableau 用户）
export async function getSessions(): Promise<GetSessionsResponse> {
  const response = await apiClient.get('/api/sessions')
  return response.data
}

// 获取特定会话
export async function getSession(sessionId: string): Promise<Session> {
  const response = await apiClient.get(`/api/sessions/${sessionId}`)
  return response.data
}

// 更新会话
export async function updateSession(
  sessionId: string,
  data: UpdateSessionRequest
): Promise<void> {
  await apiClient.put(`/api/sessions/${sessionId}`, data)
}

// 删除会话
export async function deleteSession(sessionId: string): Promise<void> {
  await apiClient.delete(`/api/sessions/${sessionId}`)
}

// 导出会话
export async function exportSession(
  sessionId: string,
  format: 'markdown' | 'pdf'
): Promise<Blob> {
  const response = await apiClient.get(`/api/sessions/${sessionId}/export`, {
    params: { format },
    responseType: 'blob'
  })
  return response.data
}
```

**设置管理 API**:

```typescript
// src/api/settings.ts
import apiClient from './client'

// 获取用户设置（当前 Tableau 用户）
export async function getSettings(): Promise<UserSettings> {
  const response = await apiClient.get('/api/settings')
  return response.data
}

// 更新用户设置
export async function updateSettings(settings: UpdateSettingsRequest): Promise<void> {
  await apiClient.put('/api/settings', settings)
}
```

**反馈 API**:

```typescript
// src/api/feedback.ts
import apiClient from './client'

// 提交反馈
export async function submitFeedback(feedback: Omit<FeedbackRequest, 'tableauUsername'>): Promise<void> {
  await apiClient.post('/api/feedback', feedback)
}
```

**Axios 配置**:

```typescript
// src/api/client.ts
import axios from 'axios'
import { getTableauUser } from '@/utils/tableau'

// 创建 axios 实例
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 60000
})

// 请求拦截器：自动添加 Tableau 用户信息到请求头
apiClient.interceptors.request.use(
  (config) => {
    const tableauUser = getTableauUser()
    if (tableauUser) {
      config.headers['X-Tableau-Username'] = tableauUser.username
      config.headers['X-Tableau-DisplayName'] = tableauUser.displayName
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器：统一错误处理
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 403) {
      // Tableau 用户无权限
      console.error('Tableau user not authorized')
    }
    return Promise.reject(error)
  }
)

export default apiClient
```

**重要说明**:
- ✅ 会话和设置数据存储在后端数据库
- ✅ 使用 Tableau 用户名（`tableauUsername`）进行数据隔离
- ✅ 支持跨设备访问（Tableau 自动认证）
- ✅ 不同 Tableau 用户的数据完全隔离
- ✅ 通过请求头（`X-Tableau-Username`）传递用户身份
- ✅ 所有 API 调用统一使用 `apiClient`（带拦截器），自动添加用户身份信息

**⚠️ 安全性注意 - 用户身份校验**：

前端传递的 `tableauUsername` 可被伪造，后端必须实现额外的身份校验：

1. **推荐方案（生产环境）**：
   - Tableau Server/Cloud 环境下，通过反向代理（如 Nginx）在请求头中注入真实用户信息
   - 前端不应直接传递用户名，而是由代理层自动添加
   - 后端只信任代理层注入的用户信息

2. **备选方案（中等安全）**：
   - 前端使用 Tableau Extensions API 获取数字签名的用户 token
   - 后端验证签名后再使用用户信息
   - 需要 Tableau Server 提供签名验证接口

3. **最小方案（开发/测试环境）**：
   - 后端记录所有 API 访问日志（用户名、IP、时间戳）
   - 定期审计异常访问模式
   - 仅用于开发和测试，不适合生产环境

**重要**：不同 Tableau 用户的数据隔离依赖于正确的身份校验，如果校验失败会导致数据泄露。

### 5.4 错误处理

**HTTP 错误映射**:

```typescript
// src/utils/errorMessages.ts
export const HTTP_ERROR_MESSAGES: Record<number, string> = {
  400: '请求格式错误，请检查输入',
  401: '未授权，请重新登录',
  403: '无访问权限',
  404: '资源不存在',
  500: '服务器内部错误，请稍后重试',
  502: '网关错误，请稍后重试',
  503: '服务暂时不可用，请稍后重试'
}

export function getErrorMessage(statusCode: number): string {
  return HTTP_ERROR_MESSAGES[statusCode] || `未知错误（${statusCode}）`
}

export function isNetworkError(error: any): boolean {
  return !error.response && error.request
}
```

**全局错误处理**:

```typescript
// src/main.ts
import { createApp } from 'vue'
import App from './App.vue'

const app = createApp(App)

// 全局错误处理器
app.config.errorHandler = (err, instance, info) => {
  console.error('Global error:', err)
  console.error('Error info:', info)
  
  // 显示用户友好的错误提示
  ElMessage.error({
    message: '应用发生错误，请刷新页面重试',
    duration: 5000,
    showClose: true
  })
}

app.mount('#app')
```

**组件级错误处理**:

```typescript
// src/composables/useErrorHandler.ts
export function useErrorHandler() {
  const showError = (error: Error | string) => {
    const message = typeof error === 'string' ? error : error.message
    
    ElMessage.error({
      message,
      duration: 5000,
      showClose: true
    })
  }
  
  const handleAPIError = (error: any) => {
    if (isNetworkError(error)) {
      showError('网络连接失败，请检查网络后重试')
    } else if (error.response) {
      const message = getErrorMessage(error.response.status)
      showError(message)
    } else {
      showError('未知错误，请稍后重试')
    }
  }
  
  return {
    showError,
    handleAPIError
  }
}
```

**Vue 3 错误捕获**:

```vue
<!-- src/components/common/ErrorBoundary.vue -->
<script setup lang="ts">
import { onErrorCaptured, ref } from 'vue'

const error = ref<Error | null>(null)

onErrorCaptured((err) => {
  error.value = err
  console.error('Component error:', err)
  return false // 阻止错误继续传播
})
</script>

<template>
  <div v-if="error" class="error-boundary">
    <p>组件加载失败</p>
    <button @click="error = null">重试</button>
  </div>
  <slot v-else />
</template>
```

### 5.5 输入验证

```typescript
// src/utils/validators.ts
export function validateInput(text: string): {
  valid: boolean
  error?: string
} {
  // 检查是否为空或仅空白字符
  if (!text || text.trim().length === 0) {
    return { valid: false, error: '请输入问题' }
  }
  
  // 检查长度
  if (text.length > 2000) {
    return { valid: false, error: '输入内容过长（最多 2000 字符）' }
  }
  
  return { valid: true }
}

export function sanitizeInput(text: string): string {
  // 移除首尾空白
  return text.trim()
}
```


## 6. 样式与主题

### 6.1 CSS 变量

```css
/* src/assets/styles/variables.css */
:root {
  /* Tableau 配色 */
  --color-primary: #1F77B4;      /* Tableau 蓝 */
  --color-success: #2CA02C;      /* 绿色 */
  --color-warning: #FF7F0E;      /* 橙色 */
  --color-danger: #D62728;       /* 红色 */
  --color-info: #9467BD;         /* 紫色 */
  
  /* 中性色 */
  --color-text-primary: #333333;
  --color-text-secondary: #666666;
  --color-text-placeholder: #999999;
  --color-border: #E0E0E0;
  --color-bg-primary: #FFFFFF;
  --color-bg-secondary: #F5F5F5;
  
  /* 间距 */
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  
  /* 圆角 */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  
  /* 阴影 */
  --shadow-sm: 0 2px 4px rgba(0, 0, 0, 0.1);
  --shadow-md: 0 4px 8px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 8px 16px rgba(0, 0, 0, 0.1);
  
  /* 字体 */
  --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  --font-family-mono: 'Consolas', 'Monaco', 'Courier New', monospace;
  
  /* 字号 */
  --font-size-xs: 12px;
  --font-size-sm: 14px;
  --font-size-md: 16px;
  --font-size-lg: 18px;
  --font-size-xl: 20px;
  
  /* 动画 */
  --transition-fast: 150ms;
  --transition-base: 300ms;
  --transition-slow: 500ms;
}
```

### 6.2 响应式断点

```css
/* 响应式断点 */
@media (max-width: 480px) {
  /* 最小化布局 */
  :root {
    --spacing-md: 8px;
    --spacing-lg: 12px;
  }
}

@media (min-width: 480px) and (max-width: 768px) {
  /* 紧凑布局 */
  :root {
    --spacing-md: 12px;
    --spacing-lg: 16px;
  }
}

@media (min-width: 768px) {
  /* 标准布局 */
  :root {
    --spacing-md: 16px;
    --spacing-lg: 24px;
  }
}
```


## 7. 性能优化

### 7.1 代码分割

```typescript
// src/router.ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'welcome',
      component: () => import('./views/WelcomeView.vue')  // 懒加载
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('./views/ChatView.vue')  // 懒加载
    }
  ]
})
```

### 7.2 虚拟滚动

**方案选择**: 使用 `@vueuse/core` 的 `useVirtualList`

**原因**:
- Element Plus 没有 `el-virtual-scroll` 组件
- `@vueuse/core` 提供了生产级别的虚拟滚动实现
- 轻量、性能好、TypeScript 支持完善

**实现示例**:

```vue
<!-- src/components/chat/MessageList.vue -->
<script setup lang="ts">
import { useVirtualList } from '@vueuse/core'
import { ref, computed } from 'vue'

const props = defineProps<{
  messages: Message[]
}>()

const containerRef = ref<HTMLElement>()

const { list, containerProps, wrapperProps } = useVirtualList(
  computed(() => props.messages),
  {
    itemHeight: 100, // 预估每条消息高度
    overscan: 5      // 缓冲区大小
  }
)
</script>

<template>
  <div ref="containerRef" v-bind="containerProps" class="message-list">
    <div v-bind="wrapperProps">
      <component
        v-for="{ data: message, index } in list"
        :key="message.id"
        :is="getMessageComponent(message.role)"
        :message="message"
      />
    </div>
  </div>
</template>
```

**⚠️ 虚拟滚动高度计算风险**：

`itemHeight: 100` 是预估值，对于可变高度的消息列表可能导致滚动精度问题：

- **问题**：AI 消息高度差异大（短文本 vs 长文本 + 表格 + 图表）
- **影响**：滚动条位置不准确、内容闪烁、跳跃

**解决方案**：

1. **推荐方案**：使用 `@vueuse/core` 的 `useVirtualList` 并接受一定的滚动偏差
   - 适用于大部分场景（消息数量 > 100 条）
   - 性能优先，用户体验可接受

2. **备选方案**：改用支持可变高度的虚拟滚动库
   - 如 `vue-virtual-scroller`
   - 性能略差，但滚动精度更高

3. **简化方案**：不超过 100 条消息时关闭虚拟滚动
   - 直接渲染所有消息
   - 性能足够，无滚动精度问题

**备选方案**: 如果消息数量不大（< 100 条），可以不使用虚拟滚动，直接渲染所有消息。

### 7.3 防抖与节流

```typescript
// src/composables/useDebounce.ts
import { ref, watch } from 'vue'

export function useDebounce<T>(value: Ref<T>, delay: number = 300) {
  const debouncedValue = ref(value.value) as Ref<T>
  let timeoutId: ReturnType<typeof setTimeout>
  
  watch(value, (newValue) => {
    clearTimeout(timeoutId)
    timeoutId = setTimeout(() => {
      debouncedValue.value = newValue
    }, delay)
  })
  
  return debouncedValue
}
```

### 7.4 图片懒加载

```vue
<template>
  <img
    v-lazy="imageUrl"
    :alt="altText"
  />
</template>
```

### 7.5 Memo 化

```typescript
// src/composables/useMemoize.ts
import { computed } from 'vue'

export function useMemoize<T>(fn: () => T) {
  return computed(fn)
}
```


## 8. 测试策略

### 8.1 单元测试

**测试框架**: Vitest

**测试覆盖**:
- 工具函数（formatters, validators）
- Store actions 和 getters
- Composables
- 纯函数组件

**示例**:

```typescript
// tests/unit/utils/formatters.test.ts
import { describe, it, expect } from 'vitest'
import { formatNumber, formatRelativeTime } from '@/utils/formatters'

describe('formatNumber', () => {
  it('should format integer with thousand separator', () => {
    expect(formatNumber(1234567)).toBe('1,234,567')
  })
  
  it('should format decimal with 2 digits', () => {
    expect(formatNumber(3.14159)).toBe('3.14')
  })
  
  it('should display negative numbers in red', () => {
    const result = formatNumber(-100)
    expect(result).toContain('color: red')
  })
})
```

### 8.2 属性测试

**测试框架**: fast-check

**测试属性**:

```typescript
// tests/properties/validators.test.ts
import { test } from 'vitest'
import fc from 'fast-check'
import { validateInput } from '@/utils/validators'

test('Property: 空白字符串应验证失败', () => {
  fc.assert(
    fc.property(
      fc.stringOf(fc.constantFrom(' ', '\n', '\t')),
      (whitespace) => {
        const result = validateInput(whitespace)
        return !result.valid
      }
    )
  )
})

test('Property: 超过 2000 字符应验证失败', () => {
  fc.assert(
    fc.property(
      fc.string({ minLength: 2001 }),
      (longString) => {
        const result = validateInput(longString)
        return !result.valid
      }
    )
  )
})

test('Property: 有效输入应验证成功', () => {
  fc.assert(
    fc.property(
      fc.string({ minLength: 1, maxLength: 2000 }).filter(s => s.trim().length > 0),
      (validString) => {
        const result = validateInput(validString)
        return result.valid
      }
    )
  )
})
```


### 8.3 组件测试

```typescript
// tests/unit/components/AIMessage.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AIMessage from '@/components/chat/AIMessage.vue'

describe('AIMessage', () => {
  it('should render markdown content', () => {
    const wrapper = mount(AIMessage, {
      props: {
        message: {
          id: '1',
          type: 'ai',
          content: '**Bold** text',
          timestamp: Date.now()
        }
      }
    })
    
    expect(wrapper.html()).toContain('<strong>Bold</strong>')
  })
  
  it('should render data table when data is provided', () => {
    const wrapper = mount(AIMessage, {
      props: {
        message: {
          id: '1',
          type: 'ai',
          content: 'Result:',
          data: {
            columns: [{ key: 'name', label: 'Name', type: 'string' }],
            rows: [{ name: 'Test' }],
            totalCount: 1
          },
          timestamp: Date.now()
        }
      }
    })
    
    expect(wrapper.findComponent({ name: 'DataTable' }).exists()).toBe(true)
  })
})
```

### 8.4 E2E 测试（可选）

**测试框架**: Playwright

**测试场景**:
- 用户发送消息并获得回复
- 流式输出正常工作
- 数据表格排序和导出
- 会话管理
- 错误处理


## 9. 部署方案

### 9.1 开发环境

```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev

# 访问 http://localhost:5173
```

**环境变量** (`.env.development`):
```env
VITE_API_BASE_URL=http://localhost:8000
VITE_TABLEAU_EXTENSION_ID=com.analytics.assistant
```

**Vite 代理配置** (`vite.config.ts`):

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
```

**说明**：
- 开发环境使用 Vite 代理解决跨域问题（前端 → Vite Dev Server → 后端）
- `useChat()` 根据环境自动选择：开发用相对路径，生产用完整 URL
- 前端请求 `/api/chat/stream` → Vite 代理转发到 `http://localhost:8000/api/chat/stream`

### 9.2 生产环境

```bash
# 构建生产版本
npm run build

# 预览构建结果
npm run preview
```

**环境变量** (`.env.production`):
```env
VITE_API_BASE_URL=https://api.example.com
VITE_TABLEAU_EXTENSION_ID=com.analytics.assistant
```

### 9.2.1 生产环境跨域解决方案

生产环境有三种部署架构，跨域处理方式不同：

#### 方案 1：同域部署（推荐，无跨域问题）

**架构**：
```
https://analytics.example.com
├── /                    # 前端静态文件（Nginx）
└── /api/*               # 后端 API（反向代理到 FastAPI）
```

**Nginx 配置**：
```nginx
server {
    listen 443 ssl;
    server_name analytics.example.com;
    
    # SSL 配置
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # 前端静态文件
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
    
    # 后端 API 反向代理
    location /api/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        
        # SSE 必需配置
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding on;
        
        # 超时配置（SSE 长连接）
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
        
        # 转发真实 IP 和 Host
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**前端配置**：
```env
# .env.production
VITE_API_BASE_URL=  # 留空，使用相对路径
```

**优点**：
- ✅ 无跨域问题
- ✅ 统一域名，SSL 证书管理简单
- ✅ 可以在 Nginx 层注入真实用户信息（安全）

#### 方案 2：跨域部署 + CORS（适用于独立后端）

**架构**：
```
前端：https://app.example.com
后端：https://api.example.com
```

**后端 CORS 配置**（FastAPI）：
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.example.com",  # 生产环境前端域名
        "http://localhost:5173",    # 开发环境
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
```

**前端配置**：
```env
# .env.production
VITE_API_BASE_URL=https://api.example.com
```

**优点**：
- ✅ 前后端独立部署
- ✅ 后端可以服务多个前端

**缺点**：
- ⚠️ 需要后端配置 CORS
- ⚠️ 浏览器会发送 OPTIONS 预检请求（性能略差）
- ⚠️ 用户身份校验更复杂（需要验证 Origin）

#### 方案 3：Tableau Server 内部部署（企业环境）

**架构**：
```
Tableau Server (https://tableau.company.com)
├── /extensions/analytics-assistant/  # 前端（Nginx）
└── /api/analytics-assistant/*        # 后端（反向代理）
```

**Tableau Server 反向代理配置**：
```nginx
# 在 Tableau Server 的 Nginx 配置中添加
location /extensions/analytics-assistant/ {
    alias /opt/analytics-assistant/frontend/;
    try_files $uri $uri/ /extensions/analytics-assistant/index.html;
}

location /api/analytics-assistant/ {
    proxy_pass http://analytics-backend:8000/api/;
    
    # SSE 配置
    proxy_http_version 1.1;
    proxy_set_header Connection '';
    proxy_buffering off;
    
    # 注入 Tableau 用户信息（安全）
    proxy_set_header X-Tableau-Username $remote_user;
    proxy_set_header X-Tableau-DisplayName $http_x_tableau_displayname;
}
```

**前端配置**：
```env
# .env.production
VITE_API_BASE_URL=/api/analytics-assistant
```

**优点**：
- ✅ 与 Tableau Server 集成，统一认证
- ✅ 反向代理层注入真实用户信息（最安全）
- ✅ 无跨域问题

**缺点**：
- ⚠️ 需要 Tableau Server 管理员权限配置

### 9.2.2 生产环境部署检查清单

| 检查项 | 说明 |
|--------|------|
| ✅ HTTPS | 生产环境必须使用 HTTPS |
| ✅ CORS 配置 | 如果跨域部署，确保后端 CORS 配置正确 |
| ✅ SSE 配置 | Nginx 必须禁用 buffering（`proxy_buffering off`） |
| ✅ 超时配置 | SSE 长连接需要增加超时时间（`proxy_read_timeout 300s`） |
| ✅ 环境变量 | `VITE_API_BASE_URL` 设置为生产环境后端地址 |
| ✅ 用户身份 | 生产环境应使用反向代理注入用户信息，不信任前端传递 |
| ✅ 错误日志 | 配置错误日志收集（Sentry、CloudWatch 等） |
| ✅ 性能监控 | 配置性能监控（Google Analytics、Mixpanel 等） |

### 9.3 Tableau Extension 配置

**manifest.trex**:

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest manifest-version="0.1" xmlns="http://www.tableau.com/xml/extension_manifest">
  <dashboard-extension id="com.analytics.assistant" extension-version="1.0.0">
    <default-locale>zh_CN</default-locale>
    <name resource-id="name"/>
    <description>Analytics Assistant - AI 数据分析助手</description>
    <author name="Your Name" email="your@email.com" organization="Your Org" website="https://example.com"/>
    <min-api-version>1.0</min-api-version>
    <source-location>
      <url>https://your-domain.com</url>
    </source-location>
    <icon>icon.png</icon>
    <permissions>
      <permission>full data</permission>
    </permissions>
  </dashboard-extension>
</manifest>
```

### 9.4 Docker 部署

```dockerfile
# Dockerfile
FROM node:20-alpine as builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

**nginx.conf** (仅前端静态文件):

```nginx
server {
    listen 80;
    server_name _;
    
    root /usr/share/nginx/html;
    index index.html;
    
    # 前端路由（SPA）
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # 启用 gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    
    # 缓存静态资源
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

**nginx.conf** (前端 + 后端反向代理，推荐生产环境):

```nginx
upstream backend {
    server backend:8000;
}

server {
    listen 80;
    server_name _;
    
    root /usr/share/nginx/html;
    index index.html;
    
    # 前端路由（SPA）
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # 后端 API 反向代理
    location /api/ {
        proxy_pass http://backend;
        
        # SSE 必需配置（关键！）
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_buffering off;           # 禁用缓冲，立即转发数据
        proxy_cache off;               # 禁用缓存
        chunked_transfer_encoding on;  # 启用分块传输
        
        # 超时配置（SSE 长连接）
        proxy_read_timeout 300s;       # 5 分钟超时
        proxy_connect_timeout 75s;
        proxy_send_timeout 300s;
        
        # 转发真实 IP 和 Host
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 注入 Tableau 用户信息（如果使用 Tableau Server 认证）
        # proxy_set_header X-Tableau-Username $remote_user;
    }
    
    # 启用 gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;
    
    # 缓存静态资源
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

**docker-compose.yml** (前端 + 后端一起部署):

```yaml
version: '3.8'

services:
  frontend:
    build: .
    ports:
      - "80:80"
    depends_on:
      - backend
    networks:
      - app-network
  
  backend:
    image: analytics-assistant-backend:latest
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/analytics
    networks:
      - app-network
  
  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=analytics
    volumes:
      - postgres-data:/var/lib/postgresql/data
    networks:
      - app-network

networks:
  app-network:
    driver: bridge

volumes:
  postgres-data:
```

**重要说明**：
- 如果前后端一起部署（推荐），使用第二个 nginx.conf（带反向代理）
- SSE 配置中 `proxy_buffering off` 是关键，否则流式输出会被缓冲
- 生产环境建议使用 HTTPS（添加 SSL 证书配置）


## 10. 开发规范

### 10.1 代码规范

**ESLint 配置** (`.eslintrc.js`):

```javascript
module.exports = {
  root: true,
  env: {
    browser: true,
    es2021: true,
    node: true
  },
  extends: [
    'plugin:vue/vue3-recommended',
    'eslint:recommended',
    '@vue/typescript/recommended',
    '@vue/prettier'
  ],
  parserOptions: {
    ecmaVersion: 2021
  },
  rules: {
    'vue/multi-word-component-names': 'off',
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }]
  }
}
```

**Prettier 配置** (`.prettierrc`):

```json
{
  "semi": false,
  "singleQuote": true,
  "printWidth": 100,
  "trailingComma": "none",
  "arrowParens": "avoid"
}
```

### 10.2 Git 提交规范

**Commit Message 格式**:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type**:
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构
- `perf`: 性能优化
- `test`: 测试
- `chore`: 构建/工具链

**示例**:

```
feat(chat): 实现流式输出功能

- 添加 SSEClient 类
- 实现自动重连机制
- 添加超时控制

Closes #123
```

### 10.3 组件命名规范

- **组件文件**: PascalCase（如 `AIMessage.vue`）
- **组件名称**: PascalCase（如 `<AIMessage />`）
- **Props**: camelCase（如 `isStreaming`）
- **Events**: kebab-case（如 `@message-sent`）
- **Store**: camelCase（如 `useChatStore`）
- **Composables**: camelCase with `use` prefix（如 `useStreaming`）


## 11. 风险与缓解措施

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| Tableau Extensions API 限制 | 高 | 中 | 提前验证 API 能力，明确告知用户必须在 Tableau 环境中使用 |
| Tableau API 调用失败 | 高 | 低 | 显示清晰错误提示，禁用输入功能，引导用户检查 Tableau 连接 |
| 数据源列表为空 | 高 | 低 | 显示"当前仪表板没有可用数据源"提示，引导用户添加数据源 |
| SSE 连接不稳定 | 中 | 中 | 实现自动重连（指数退避）、提供手动重试按钮 |
| 浏览器兼容性问题 | 中 | 低 | 使用 Polyfill、在多浏览器测试、提供兼容性提示 |
| 性能问题（大数据量） | 中 | 中 | 虚拟滚动、分页加载、懒加载、代码分割 |
| 后端 API 变更 | 高 | 低 | 定义清晰的接口契约、版本管理、向后兼容 |
| 内存泄漏 | 中 | 低 | 及时清理事件监听器、使用 WeakMap、定期内存分析 |
| XSS 攻击 | 高 | 低 | 禁用 HTML 标签、转义特殊字符、CSP 策略 |

## 12. 时间估算

### 完整生产级别产品（5-6 周）

| 模块 | 任务 | 时间 | 负责人 |
|------|------|------|--------|
| **基础设施** | 项目初始化、环境配置、构建工具 | 1 天 | 前端开发 |
| | TypeScript 配置、ESLint/Prettier | 0.5 天 | 前端开发 |
| | 目录结构、路由配置 | 0.5 天 | 前端开发 |
| | Vercel AI SDK 集成 | 1 天 | 前端开发 |
| **核心服务** | Tableau Extensions API 集成 | 2 天 | 前端开发 |
| | HTTP 客户端（Axios + 拦截器） | 1 天 | 前端开发 |
| | 会话管理 API 集成 | 1 天 | 前端开发 |
| | 设置 API 集成 | 0.5 天 | 前端开发 |
| | 反馈 API 集成 | 0.5 天 | 前端开发 |
| | 错误处理服务 | 0.5 天 | 前端开发 |
| **状态管理** | chatStore（对话状态 + 建议问题 + 思考步骤） | 1.5 天 | 前端开发 |
| | tableauStore（Tableau 状态） | 1 天 | 前端开发 |
| | sessionStore（会话管理 + 后端同步） | 2 天 | 前端开发 |
| | settingsStore（设置状态 + 后端同步） | 1.5 天 | 前端开发 |
| | uiStore（UI 状态） | 0.5 天 | 前端开发 |
| **布局组件** | AppLayout（应用布局） | 0.5 天 | 前端开发 |
| | HeaderBar（顶部栏） | 1 天 | 前端开发 |
| | InputArea（输入区域 + 停止按钮） | 1.5 天 | 前端开发 |
| **对话组件** | ChatContainer（对话容器） | 1 天 | 前端开发 |
| | MessageList（消息列表，含虚拟滚动） | 1.5 天 | 前端开发 |
| | UserMessage（用户消息） | 0.5 天 | 前端开发 |
| | AIMessage（AI 消息） | 1 天 | 前端开发 |
| | ThinkingIndicator（思考指示器） | 0.5 天 | 前端开发 |
| **内容组件** | MarkdownRenderer（Markdown 渲染） | 1.5 天 | 前端开发 |
| | DataTable（数据表格） | 2 天 | 前端开发 |
| | TableToolbar（表格工具栏） | 0.5 天 | 前端开发 |
| | DataChart（ECharts 图表） | 2 天 | 前端开发 |
| | ChartToolbar（图表工具栏） | 0.5 天 | 前端开发 |
| **反馈组件** | MessageActions（消息操作按钮） | 1 天 | 前端开发 |
| | FeedbackDialog（反馈对话框） | 1 天 | 前端开发 |
| | SuggestedQuestions（建议问题） | 1 天 | 前端开发 |
| **思考过程组件** | ThinkingSteps（思考步骤列表） | 1.5 天 | 前端开发 |
| | StepDetail（步骤详情） | 0.5 天 | 前端开发 |
| **设置组件** | SettingsPanel（设置面板） | 1.5 天 | 前端开发 |
| | DataSourceSelector（数据源选择器） | 1 天 | 前端开发 |
| **会话组件** | SessionList（会话列表） | 1.5 天 | 前端开发 |
| | SessionItem（会话项） | 0.5 天 | 前端开发 |
| **通用组件** | ErrorMessage（错误消息） | 0.5 天 | 前端开发 |
| | LoadingSpinner（加载指示器） | 0.5 天 | 前端开发 |
| | EmptyState（空状态） | 0.5 天 | 前端开发 |
| **工具函数** | formatters（数据格式化） | 0.5 天 | 前端开发 |
| | validators（输入验证） | 0.5 天 | 前端开发 |
| | markdown（Markdown 工具） | 0.5 天 | 前端开发 |
| | errorMessages（错误消息映射） | 0.5 天 | 前端开发 |
| | chartUtils（图表工具） | 0.5 天 | 前端开发 |
| | constants（常量定义） | 0.5 天 | 前端开发 |
| **样式与主题** | CSS 变量、全局样式 | 1 天 | 前端开发 |
| | 响应式设计（多断点适配） | 1.5 天 | 前端开发 |
| | 组件样式优化 | 1 天 | 前端开发 |
| **性能优化** | 代码分割、懒加载 | 0.5 天 | 前端开发 |
| | 虚拟滚动优化 | 0.5 天 | 前端开发 |
| | 防抖节流 | 0.5 天 | 前端开发 |
| **测试** | 单元测试（工具函数、Store） | 2 天 | 前端开发 |
| | 属性测试（关键功能） | 1 天 | 前端开发 |
| | 组件测试 | 1.5 天 | 前端开发 |
| **集成与部署** | 前后端联调 | 2 天 | 前端+后端 |
| | Tableau Extension 配置 | 0.5 天 | 前端开发 |
| | Docker 配置、Nginx 配置 | 0.5 天 | 前端开发 |
| | 生产环境部署测试 | 1 天 | 前端开发 |
| **文档** | 用户使用手册 | 1 天 | 前端开发 |
| | 开发者指南 | 0.5 天 | 前端开发 |
| | API 文档 | 0.5 天 | 前端开发 |

**总计**: 约 54 天（基础开发时间）

**风险缓冲时间**: +10 天（应对以下风险）
- 前后端 SSE 协议联调（2-3 天）
- Tableau Extensions API 限制调试（2-3 天）
- 用户身份安全方案实施（2-3 天）
- 虚拟滚动和性能优化调整（1-2 天）

**实际总时间**: 约 64 天（6-7 周）

**关键路径**:
1. 基础设施 → 核心服务 → 状态管理 → 组件开发 → 测试 → 部署
2. 并行开发：组件可以并行开发，工具函数可以提前准备
3. 测试驱动：边开发边测试，确保质量

**关键里程碑**:
- Week 1-2: 基础设施 + 核心服务 + 状态管理
- Week 3-4: 组件开发（布局、对话、内容展示）
- Week 5: 组件开发（反馈、思考过程、设置、会话）
- Week 6: 前后端联调 + 测试 + 性能优化
- Week 7: 部署配置 + 文档 + 缓冲时间

**新增功能时间**（相比原方案）:
- Vercel AI SDK 集成：+1 天（但节省 SSE 客户端开发 2 天）
- 消息操作按钮：+1 天
- 建议问题组件：+1 天
- 数据可视化（ECharts）：+2.5 天
- 思考过程可视化：+2 天
- 反馈系统：+1 天
- 会话后端存储：+2 天
- 设置后端存储：+1 天

**移除功能节省时间**：
- 用户认证系统（登录/注册/JWT）：-3 天

**净增加时间**：约 7.5 天（1.5 周）

**风险应对计划**:

| 风险 | 概率 | 影响 | 应对措施 | 预留时间 |
|------|------|------|----------|----------|
| Vercel AI SDK 自定义事件不兼容 | 中 | 高 | 开发初期进行最小 MVP 联调验证 | 2-3 天 |
| Tableau API 限制或 Bug | 中 | 中 | 提前验证关键 API，准备降级方案 | 2-3 天 |
| 用户身份校验方案实施复杂 | 低 | 高 | 与后端和运维团队提前沟通方案 | 2-3 天 |
| 虚拟滚动性能问题 | 低 | 中 | 准备备选方案（关闭虚拟滚动） | 1-2 天 |

**建议**:
- 第 1 周完成基础设施后，立即进行前后端 SSE 协议联调
- 第 2 周完成 Tableau 集成后，进行完整的 API 验证
- 第 6 周预留为联调和调试周，不安排新功能开发

## 13. 交付物

### 13.1 代码交付

- ✅ 完整的前端代码（Vue 3 + TypeScript + Vercel AI SDK）
- ✅ 所有核心功能（对话、流式输出、数据表格、数据可视化、会话管理、设置面板）
- ✅ AI 产品最佳实践（多轮对话、消息操作、建议问题、思考过程可视化）
- ✅ 后端集成（会话 API、设置 API、反馈 API）
- ✅ Tableau 用户身份集成（自动获取用户信息，无需独立认证）
- ✅ 响应式设计（支持多种屏幕尺寸）
- ✅ 性能优化（虚拟滚动、代码分割、懒加载）
- ✅ 单元测试（覆盖率 > 80%）
- ✅ 属性测试（关键功能）
- ✅ 组件测试
- ✅ README 文档
- ✅ API 文档

### 13.2 部署交付

- ✅ 构建产物（dist/）
- ✅ Docker 镜像和 docker-compose 配置
- ✅ Nginx 配置文件
- ✅ Tableau Extension 清单（manifest.trex）
- ✅ 环境变量配置示例（.env.example）
- ✅ 部署文档（包含生产环境部署步骤）

### 13.3 文档交付

- ✅ 技术设计文档（本文档）
- ✅ 需求文档
- ✅ 用户使用手册
- ✅ 开发者指南
- ✅ API 接口文档
- ✅ 故障排查指南
- ✅ Vercel AI SDK 集成指南

### 13.4 质量保证

- ✅ 代码质量：通过 ESLint + Prettier 检查
- ✅ 类型安全：TypeScript 严格模式，无 any 类型
- ✅ 性能指标：FCP < 2s, TTI < 3s, 内存占用 < 100MB
- ✅ 兼容性测试：Chrome, Edge, Safari, Firefox 多浏览器测试
- ✅ 安全性：XSS 防护、HTTPS、数据隐私保护
- ✅ 可维护性：组件化、文档完善、测试覆盖充分
- ✅ AI 产品体验：符合 2025-2026 主流 AI 产品标准

---

**这是一个完整的生产级别产品，采用主流 AI 前端框架（Vercel AI SDK），会话和设置数据存储在后端数据库，使用 Tableau Server 自带认证（无需独立认证系统），支持多用户和跨设备同步，包含所有核心功能和 AI 产品最佳实践。**

---

**文档版本**: v3.0  
**创建日期**: 2026-02-06  
**更新日期**: 2026-02-06  
**审核状态**: 已修复关键问题  
**作者**: Kiro AI Assistant

**v3.0 更新内容**:
- ✅ 移除自定义 SSEClient 实现（使用 Vercel AI SDK）
- ✅ 移除 Tableau Extensions Settings API 代码（使用后端数据库）
- ✅ 修复 useChat.ts 缺少 settingsStore 导入
- ✅ 添加消息裁剪策略（最近 10 轮对话）
- ✅ 优化 Tableau 数据源获取逻辑（遍历所有 worksheet 并去重）
- ✅ 修复虚拟滚动方案（使用 @vueuse/core）
- ✅ 补充全局错误处理机制
- ✅ 统一流式方案和存储方案
- ✅ 修复文档重复和破损代码块


