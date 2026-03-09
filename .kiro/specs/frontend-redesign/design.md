# 设计文档 - Tableau AI Assistant 前端重设计

## 概述

本设计文档描述了 Tableau AI Assistant 前端应用的完整技术架构。该应用是一个嵌入在 Tableau Dashboard 中的 AI 驱动的数据分析对话界面,基于 Vue 3 + TypeScript + Vite + Pinia + Tailwind CSS 技术栈构建。

### 设计目标

1. **现代化架构**: 采用 Vue 3 Composition API 和 TypeScript,提供类型安全和更好的代码组织
2. **高性能**: 通过虚拟滚动、代码分割、懒加载等技术优化性能
3. **可访问性**: 符合 WCAG 2.1 AA 标准,支持键盘导航和屏幕阅读器
4. **响应式设计**: 适配桌面、平板和移动设备
5. **可维护性**: 清晰的模块划分、完善的类型定义和文档

### 技术栈

| 类别 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 前端框架 | Vue 3 | ^3.4.0 | Composition API |
| 语言 | TypeScript | ^5.3.0 | 类型安全 |
| 构建工具 | Vite | ^5.0.0 | 快速构建 |
| 状态管理 | Pinia | ^2.1.0 | Vue 3 官方状态管理 |
| 样式框架 | Tailwind CSS | ^3.4.0 | 实用优先的 CSS 框架 |
| HTTP 客户端 | Axios | ^1.6.0 | HTTP 请求 |
| Markdown 渲染 | markdown-it | ^14.0.0 | Markdown 解析 |
| 代码高亮 | highlight.js | ^11.9.0 | 语法高亮 |
| 国际化 | vue-i18n | ^9.9.0 | 多语言支持 |
| 虚拟滚动 | vue-virtual-scroller | ^2.0.0 | 性能优化 |

## 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     Presentation Layer                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Vue 组件   │  │  Composables │  │   Directives │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                      State Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  chatStore   │  │ settingsStore│  │ sessionStore │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                      Service Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  API Client  │  │  SSE Client  │  │ Tableau API  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                      Utility Layer                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   Markdown   │  │   Storage    │  │    Logger    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```


### 目录结构

```
frontend/
├── src/
│   ├── api/                    # API 服务层
│   │   ├── client.ts          # Axios 客户端配置
│   │   ├── sse.ts             # SSE 客户端
│   │   ├── chat.ts            # 聊天 API
│   │   ├── session.ts         # 会话 API
│   │   ├── datasource.ts      # 数据源 API
│   │   └── feedback.ts        # 反馈 API
│   ├── assets/                 # 静态资源
│   │   ├── styles/            # 全局样式
│   │   │   ├── main.css       # Tailwind 入口
│   │   │   ├── variables.css  # CSS 变量
│   │   │   └── themes.css     # 主题样式
│   │   └── images/            # 图片资源
│   ├── components/             # Vue 组件
│   │   ├── chat/              # 聊天相关组件
│   │   │   ├── ChatContainer.vue
│   │   │   ├── MessageList.vue
│   │   │   ├── MessageItem.vue
│   │   │   ├── InputBox.vue
│   │   │   ├── TypingIndicator.vue
│   │   │   └── FeedbackButtons.vue
│   │   ├── boost/             # 快捷提示组件
│   │   │   ├── BoostPromptPanel.vue
│   │   │   └── BoostPromptCard.vue
│   │   ├── session/           # 会话管理组件
│   │   │   ├── HistoryPanel.vue
│   │   │   └── SessionCard.vue
│   │   ├── settings/          # 设置组件
│   │   │   └── SettingsPanel.vue
│   │   ├── datasource/        # 数据源组件
│   │   │   └── DataSourceSelector.vue
│   │   ├── common/            # 通用组件
│   │   │   ├── EmptyState.vue
│   │   │   ├── LoadingSpinner.vue
│   │   │   ├── ErrorMessage.vue
│   │   │   └── Modal.vue
│   │   └── layout/            # 布局组件
│   │       ├── Header.vue
│   │       └── Sidebar.vue
│   ├── composables/            # 组合式函数
│   │   ├── useChat.ts         # 聊天逻辑
│   │   ├── useMarkdown.ts     # Markdown 渲染
│   │   ├── useTableau.ts      # Tableau 集成
│   │   ├── useTheme.ts        # 主题切换
│   │   └── useKeyboard.ts     # 键盘导航
│   ├── directives/             # 自定义指令
│   │   ├── focus.ts           # 焦点管理
│   │   └── clickOutside.ts    # 点击外部
│   ├── i18n/                   # 国际化
│   │   ├── index.ts           # i18n 配置
│   │   ├── zh-CN.ts           # 中文语言包
│   │   └── en-US.ts           # 英文语言包
│   ├── stores/                 # Pinia 状态管理
│   │   ├── chat.ts            # 聊天状态
│   │   ├── settings.ts        # 用户设置
│   │   ├── session.ts         # 会话管理
│   │   └── tableau.ts         # Tableau 上下文
│   ├── types/                  # TypeScript 类型定义
│   │   ├── api.ts             # API 类型
│   │   ├── chat.ts            # 聊天类型
│   │   ├── session.ts         # 会话类型
│   │   ├── settings.ts        # 设置类型
│   │   ├── datasource.ts      # 数据源类型
│   │   └── tableau.ts         # Tableau 类型
│   ├── utils/                  # 工具函数
│   │   ├── markdown.ts        # Markdown 工具
│   │   ├── storage.ts         # 本地存储
│   │   ├── logger.ts          # 日志工具
│   │   ├── validator.ts       # 验证工具
│   │   ├── formatter.ts       # 格式化工具
│   │   └── security.ts        # 安全工具
│   ├── App.vue                 # 根组件
│   ├── main.ts                 # 应用入口
│   └── env.d.ts                # 环境变量类型
├── public/                     # 公共资源
│   ├── manifest.trex          # Tableau Extension 清单
│   └── favicon.ico            # 网站图标
├── tests/                      # 测试文件
│   ├── unit/                  # 单元测试
│   └── e2e/                   # 端到端测试
├── .env.development           # 开发环境变量
├── .env.production            # 生产环境变量
├── vite.config.ts             # Vite 配置
├── tailwind.config.js         # Tailwind 配置
├── tsconfig.json              # TypeScript 配置
└── package.json               # 项目配置
```


## 组件设计

### 组件层次结构

```
App.vue
└── ChatContainer.vue (主容器)
    ├── Header.vue (顶部栏)
    │   ├── Logo (品牌标识)
    │   ├── DataSourceSelector.vue (数据源选择器)
    │   ├── HistoryButton (历史按钮)
    │   └── SettingsButton (设置按钮)
    ├── MessageList.vue (消息列表)
    │   ├── EmptyState.vue (空状态)
    │   └── MessageItem.vue[] (消息项)
    │       ├── TypingIndicator.vue (打字指示器)
    │       ├── MarkdownContent (Markdown 内容)
    │       └── FeedbackButtons.vue (反馈按钮)
    ├── InputBox.vue (输入框)
    │   ├── TextArea (文本输入)
    │   ├── SendButton (发送按钮)
    │   └── BoostPromptPanel.vue (快捷提示面板)
    │       └── BoostPromptCard.vue[] (快捷提示卡片)
    ├── SettingsPanel.vue (设置侧边栏)
    │   ├── LanguageSelector (语言选择)
    │   ├── DepthSelector (分析深度)
    │   ├── ThemeSelector (主题选择)
    │   └── ThinkingToggle (思考过程开关)
    └── HistoryPanel.vue (历史侧边栏)
        ├── NewSessionButton (新建会话按钮)
        └── SessionCard.vue[] (会话卡片)
            ├── SessionTitle (会话标题)
            ├── SessionTime (更新时间)
            └── SessionActions (操作按钮)
```

### 核心组件接口

#### ChatContainer.vue

主容器组件,负责整体布局和组件协调。

**Props**: 无

**Emits**: 无

**Composables**:
- `useChat()` - 聊天逻辑
- `useTableau()` - Tableau 集成
- `useTheme()` - 主题管理

**职责**:
- 初始化 Tableau Extension API
- 协调子组件通信
- 管理侧边栏显示状态
- 响应式布局控制

#### MessageList.vue

消息列表组件,支持虚拟滚动和自动滚动。

**Props**:
```typescript
interface Props {
  messages: Message[]
  loading?: boolean
  autoScroll?: boolean
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'feedback', payload: { messageId: string; type: 'like' | 'dislike' }): void
  (e: 'retry', messageId: string): void
}
```

**职责**:
- 渲染消息列表(虚拟滚动)
- 自动滚动到最新消息
- 处理用户手动滚动
- 显示空状态和加载状态

#### MessageItem.vue

单条消息组件,支持 Markdown 渲染和代码高亮。

**Props**:
```typescript
interface Props {
  message: Message
  showFeedback?: boolean
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'feedback', type: 'like' | 'dislike'): void
  (e: 'retry'): void
}
```

**Composables**:
- `useMarkdown()` - Markdown 渲染

**职责**:
- 渲染消息内容(文本/Markdown)
- 显示打字指示器(流式响应)
- 提供反馈按钮
- 代码块复制功能

#### InputBox.vue

输入框组件,支持多行输入和快捷提示。

**Props**:
```typescript
interface Props {
  disabled?: boolean
  placeholder?: string
  maxLength?: number
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'send', message: string): void
  (e: 'boost-prompt-select', prompt: string): void
}
```

**职责**:
- 接收用户输入
- 输入验证(长度、空白)
- 显示快捷提示面板
- 键盘快捷键(Enter 发送、Shift+Enter 换行)

#### BoostPromptPanel.vue

快捷提示面板组件,显示内置和自定义提示。

**Props**:
```typescript
interface Props {
  visible?: boolean
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'select', prompt: string): void
  (e: 'add', prompt: BoostPrompt): void
  (e: 'delete', promptId: string): void
}
```

**职责**:
- 显示快捷提示列表
- 分类显示(内置/自定义)
- 添加/删除自定义提示
- 键盘导航支持

#### DataSourceSelector.vue

数据源选择器组件,显示可用数据源列表。

**Props**:
```typescript
interface Props {
  datasources: DataSource[]
  selected?: string
  loading?: boolean
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'change', datasourceId: string): void
}
```

**职责**:
- 显示数据源列表
- 切换当前数据源
- 显示加载和错误状态

#### HistoryPanel.vue

历史侧边栏组件,管理会话列表。

**Props**:
```typescript
interface Props {
  visible: boolean
  sessions: Session[]
  currentSessionId?: string
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'close'): void
  (e: 'new-session'): void
  (e: 'select-session', sessionId: string): void
  (e: 'delete-session', sessionId: string): void
  (e: 'rename-session', payload: { sessionId: string; name: string }): void
}
```

**职责**:
- 显示会话列表
- 创建/删除/重命名会话
- 切换会话
- 分页/懒加载

#### SettingsPanel.vue

设置侧边栏组件,管理用户设置。

**Props**:
```typescript
interface Props {
  visible: boolean
  settings: UserSettings
}
```

**Emits**:
```typescript
interface Emits {
  (e: 'close'): void
  (e: 'update', settings: Partial<UserSettings>): void
}
```

**职责**:
- 显示设置选项
- 更新用户设置
- 实时预览(主题切换)


## 数据模型设计

### 核心类型定义

#### Message (消息)

```typescript
// types/chat.ts

export enum MessageRole {
  USER = 'user',
  ASSISTANT = 'assistant',
  SYSTEM = 'system'
}

export enum MessageStatus {
  PENDING = 'pending',      // 等待发送
  SENDING = 'sending',      // 发送中
  STREAMING = 'streaming',  // 流式接收中
  COMPLETED = 'completed',  // 完成
  FAILED = 'failed'         // 失败
}

export interface Message {
  id: string                // 消息唯一标识
  sessionId: string         // 所属会话 ID
  role: MessageRole         // 消息角色
  content: string           // 消息内容
  status: MessageStatus     // 消息状态
  timestamp: number         // 时间戳(毫秒)
  metadata?: {              // 元数据
    thinking?: string       // AI 思考过程
    datasource?: string     // 关联数据源
    error?: string          // 错误信息
  }
  feedback?: {              // 用户反馈
    type: 'like' | 'dislike'
    timestamp: number
  }
}
```

#### Session (会话)

```typescript
// types/session.ts

export interface Session {
  id: string                // 会话唯一标识
  name: string              // 会话名称
  createdAt: number         // 创建时间(毫秒)
  updatedAt: number         // 更新时间(毫秒)
  messageCount: number      // 消息数量
  datasourceId?: string     // 关联数据源 ID
  metadata?: {              // 元数据
    tags?: string[]         // 标签
    archived?: boolean      // 是否归档
  }
}

export interface SessionWithMessages extends Session {
  messages: Message[]       // 会话消息列表
}
```

#### UserSettings (用户设置)

```typescript
// types/settings.ts

export enum Language {
  ZH_CN = 'zh-CN',
  EN_US = 'en-US'
}

export enum AnalysisDepth {
  STANDARD = 'standard',
  DEEP = 'deep'
}

export enum Theme {
  LIGHT = 'light',
  DARK = 'dark',
  AUTO = 'auto'
}

export interface UserSettings {
  language: Language        // 界面语言
  analysisDepth: AnalysisDepth  // 分析深度
  theme: Theme              // 主题
  showThinking: boolean     // 显示思考过程
  autoScroll: boolean       // 自动滚动
  soundEnabled: boolean     // 声音提示
}

export const DEFAULT_SETTINGS: UserSettings = {
  language: Language.ZH_CN,
  analysisDepth: AnalysisDepth.STANDARD,
  theme: Theme.AUTO,
  showThinking: false,
  autoScroll: true,
  soundEnabled: false
}
```

#### DataSource (数据源)

```typescript
// types/datasource.ts

export interface DataSource {
  id: string                // 数据源唯一标识(Tableau LUID)
  name: string              // 数据源名称
  type: string              // 数据源类型(如 'extract', 'live')
  connectionType?: string   // 连接类型(如 'sqlserver', 'postgres')
  fields?: DataSourceField[] // 字段列表
  metadata?: {              // 元数据
    lastRefresh?: number    // 最后刷新时间
    rowCount?: number       // 行数
  }
}

export interface DataSourceField {
  id: string                // 字段 ID
  name: string              // 字段名称
  dataType: string          // 数据类型
  role: 'dimension' | 'measure'  // 字段角色
  aggregation?: string      // 聚合方式
}
```

#### BoostPrompt (快捷提示)

```typescript
// types/chat.ts

export enum BoostPromptCategory {
  BUILTIN = 'builtin',      // 内置提示
  CUSTOM = 'custom'         // 自定义提示
}

export interface BoostPrompt {
  id: string                // 提示唯一标识
  category: BoostPromptCategory  // 提示类别
  title: string             // 提示标题
  content: string           // 提示内容
  icon?: string             // 图标(可选)
  order?: number            // 排序(可选)
}

export const BUILTIN_PROMPTS: BoostPrompt[] = [
  {
    id: 'summary',
    category: BoostPromptCategory.BUILTIN,
    title: '数据概览',
    content: '请帮我分析这个数据源的整体情况,包括主要维度和度量。',
    icon: '📊',
    order: 1
  },
  {
    id: 'trend',
    category: BoostPromptCategory.BUILTIN,
    title: '趋势分析',
    content: '请分析数据的时间趋势,找出关键变化点。',
    icon: '📈',
    order: 2
  },
  {
    id: 'comparison',
    category: BoostPromptCategory.BUILTIN,
    title: '对比分析',
    content: '请对比不同维度下的数据表现,找出差异。',
    icon: '⚖️',
    order: 3
  },
  {
    id: 'anomaly',
    category: BoostPromptCategory.BUILTIN,
    title: '异常检测',
    content: '请帮我找出数据中的异常值或异常模式。',
    icon: '🔍',
    order: 4
  },
  {
    id: 'insight',
    category: BoostPromptCategory.BUILTIN,
    title: '洞察发现',
    content: '请从数据中挖掘有价值的业务洞察。',
    icon: '💡',
    order: 5
  }
]
```

### API 请求/响应类型

#### Chat API

```typescript
// types/api.ts

export interface SendMessageRequest {
  sessionId: string
  message: string
  datasourceId?: string
  settings?: {
    analysisDepth?: AnalysisDepth
    showThinking?: boolean
  }
}

export interface SendMessageResponse {
  messageId: string
  sessionId: string
  streamUrl: string         // SSE 流地址
}

export interface StreamChunk {
  type: 'token' | 'thinking' | 'done' | 'error'
  content?: string
  metadata?: Record<string, any>
}
```

#### Session API

```typescript
export interface CreateSessionRequest {
  name?: string
  datasourceId?: string
}

export interface CreateSessionResponse {
  session: Session
}

export interface ListSessionsRequest {
  page?: number
  pageSize?: number
  sortBy?: 'createdAt' | 'updatedAt'
  order?: 'asc' | 'desc'
}

export interface ListSessionsResponse {
  sessions: Session[]
  total: number
  page: number
  pageSize: number
}

export interface GetSessionRequest {
  sessionId: string
}

export interface GetSessionResponse {
  session: SessionWithMessages
}

export interface UpdateSessionRequest {
  sessionId: string
  name?: string
  metadata?: Record<string, any>
}

export interface DeleteSessionRequest {
  sessionId: string
}
```

#### Feedback API

```typescript
export interface SubmitFeedbackRequest {
  messageId: string
  type: 'like' | 'dislike'
  comment?: string
}

export interface SubmitFeedbackResponse {
  success: boolean
}
```


## API 设计

### API 客户端配置

```typescript
// api/client.ts

import axios, { AxiosInstance, AxiosRequestConfig } from 'axios'
import { logger } from '@/utils/logger'

export class APIClient {
  private instance: AxiosInstance

  constructor(baseURL: string) {
    this.instance = axios.create({
      baseURL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json'
      }
    })

    // 请求拦截器
    this.instance.interceptors.request.use(
      (config) => {
        // 添加认证 token(如需要)
        const token = localStorage.getItem('auth_token')
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        logger.debug('API Request:', config.method?.toUpperCase(), config.url)
        return config
      },
      (error) => {
        logger.error('API Request Error:', error)
        return Promise.reject(error)
      }
    )

    // 响应拦截器
    this.instance.interceptors.response.use(
      (response) => {
        logger.debug('API Response:', response.status, response.config.url)
        return response
      },
      (error) => {
        logger.error('API Response Error:', error.response?.status, error.message)
        
        // 统一错误处理
        if (error.response) {
          switch (error.response.status) {
            case 401:
              // 认证失败,跳转登录
              window.location.href = '/login'
              break
            case 403:
              // 权限不足
              throw new Error('权限不足')
            case 404:
              throw new Error('资源不存在')
            case 500:
              throw new Error('服务器错误')
            default:
              throw new Error(error.response.data?.message || '请求失败')
          }
        } else if (error.request) {
          // 网络错误
          throw new Error('网络连接失败')
        } else {
          throw new Error('请求配置错误')
        }
      }
    )
  }

  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.get<T>(url, config)
    return response.data
  }

  async post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.post<T>(url, data, config)
    return response.data
  }

  async put<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.put<T>(url, data, config)
    return response.data
  }

  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.instance.delete<T>(url, config)
    return response.data
  }
}

export const apiClient = new APIClient(import.meta.env.VITE_API_BASE_URL)
```

### SSE 客户端

```typescript
// api/sse.ts

import { logger } from '@/utils/logger'
import type { StreamChunk } from '@/types/api'

export interface SSEClientOptions {
  onMessage: (chunk: StreamChunk) => void
  onError?: (error: Error) => void
  onComplete?: () => void
}

export class SSEClient {
  private eventSource: EventSource | null = null
  private options: SSEClientOptions

  constructor(options: SSEClientOptions) {
    this.options = options
  }

  connect(url: string): void {
    if (this.eventSource) {
      this.disconnect()
    }

    logger.debug('SSE connecting:', url)
    this.eventSource = new EventSource(url)

    this.eventSource.onmessage = (event) => {
      try {
        const chunk: StreamChunk = JSON.parse(event.data)
        this.options.onMessage(chunk)

        if (chunk.type === 'done') {
          this.options.onComplete?.()
          this.disconnect()
        }
      } catch (error) {
        logger.error('SSE parse error:', error)
        this.options.onError?.(error as Error)
      }
    }

    this.eventSource.onerror = (event) => {
      logger.error('SSE error:', event)
      this.options.onError?.(new Error('SSE connection error'))
      this.disconnect()
    }
  }

  disconnect(): void {
    if (this.eventSource) {
      logger.debug('SSE disconnecting')
      this.eventSource.close()
      this.eventSource = null
    }
  }

  isConnected(): boolean {
    return this.eventSource !== null && this.eventSource.readyState === EventSource.OPEN
  }
}
```

### Chat API

```typescript
// api/chat.ts

import { apiClient } from './client'
import type { SendMessageRequest, SendMessageResponse } from '@/types/api'

export const chatAPI = {
  /**
   * 发送消息
   */
  async sendMessage(request: SendMessageRequest): Promise<SendMessageResponse> {
    return apiClient.post<SendMessageResponse>('/api/chat/send', request)
  },

  /**
   * 重试消息
   */
  async retryMessage(messageId: string): Promise<SendMessageResponse> {
    return apiClient.post<SendMessageResponse>(`/api/chat/retry/${messageId}`)
  }
}
```

### Session API

```typescript
// api/session.ts

import { apiClient } from './client'
import type {
  CreateSessionRequest,
  CreateSessionResponse,
  ListSessionsRequest,
  ListSessionsResponse,
  GetSessionRequest,
  GetSessionResponse,
  UpdateSessionRequest,
  DeleteSessionRequest
} from '@/types/api'

export const sessionAPI = {
  /**
   * 创建会话
   */
  async createSession(request: CreateSessionRequest): Promise<CreateSessionResponse> {
    return apiClient.post<CreateSessionResponse>('/api/sessions', request)
  },

  /**
   * 获取会话列表
   */
  async listSessions(request: ListSessionsRequest = {}): Promise<ListSessionsResponse> {
    return apiClient.get<ListSessionsResponse>('/api/sessions', { params: request })
  },

  /**
   * 获取会话详情
   */
  async getSession(request: GetSessionRequest): Promise<GetSessionResponse> {
    return apiClient.get<GetSessionResponse>(`/api/sessions/${request.sessionId}`)
  },

  /**
   * 更新会话
   */
  async updateSession(request: UpdateSessionRequest): Promise<void> {
    return apiClient.put<void>(`/api/sessions/${request.sessionId}`, request)
  },

  /**
   * 删除会话
   */
  async deleteSession(request: DeleteSessionRequest): Promise<void> {
    return apiClient.delete<void>(`/api/sessions/${request.sessionId}`)
  }
}
```

### DataSource API

```typescript
// api/datasource.ts

import { apiClient } from './client'
import type { DataSource } from '@/types/datasource'

export const datasourceAPI = {
  /**
   * 获取数据源列表
   */
  async listDataSources(): Promise<DataSource[]> {
    return apiClient.get<DataSource[]>('/api/datasources')
  },

  /**
   * 获取数据源详情
   */
  async getDataSource(datasourceId: string): Promise<DataSource> {
    return apiClient.get<DataSource>(`/api/datasources/${datasourceId}`)
  }
}
```

### Feedback API

```typescript
// api/feedback.ts

import { apiClient } from './client'
import type { SubmitFeedbackRequest, SubmitFeedbackResponse } from '@/types/api'

export const feedbackAPI = {
  /**
   * 提交反馈
   */
  async submitFeedback(request: SubmitFeedbackRequest): Promise<SubmitFeedbackResponse> {
    return apiClient.post<SubmitFeedbackResponse>('/api/feedback', request)
  }
}
```


## 状态管理设计

### Chat Store

```typescript
// stores/chat.ts

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { chatAPI } from '@/api/chat'
import { SSEClient } from '@/api/sse'
import type { Message, MessageRole, MessageStatus } from '@/types/chat'
import type { StreamChunk } from '@/types/api'
import { logger } from '@/utils/logger'
import { nanoid } from 'nanoid'

export const useChatStore = defineStore('chat', () => {
  // 状态
  const messages = ref<Message[]>([])
  const currentMessageId = ref<string | null>(null)
  const isStreaming = ref(false)
  const sseClient = ref<SSEClient | null>(null)

  // 计算属性
  const sortedMessages = computed(() => {
    return [...messages.value].sort((a, b) => a.timestamp - b.timestamp)
  })

  const lastMessage = computed(() => {
    return sortedMessages.value[sortedMessages.value.length - 1]
  })

  const hasMessages = computed(() => messages.value.length > 0)

  // 操作
  async function sendMessage(content: string, sessionId: string, datasourceId?: string) {
    // 创建用户消息
    const userMessage: Message = {
      id: nanoid(),
      sessionId,
      role: MessageRole.USER,
      content,
      status: MessageStatus.COMPLETED,
      timestamp: Date.now()
    }
    messages.value.push(userMessage)

    // 创建 AI 消息占位符
    const aiMessage: Message = {
      id: nanoid(),
      sessionId,
      role: MessageRole.ASSISTANT,
      content: '',
      status: MessageStatus.PENDING,
      timestamp: Date.now()
    }
    messages.value.push(aiMessage)
    currentMessageId.value = aiMessage.id

    try {
      // 发送消息到后端
      const response = await chatAPI.sendMessage({
        sessionId,
        message: content,
        datasourceId
      })

      // 更新消息状态
      updateMessageStatus(aiMessage.id, MessageStatus.STREAMING)

      // 连接 SSE 流
      await connectStream(response.streamUrl, aiMessage.id)
    } catch (error) {
      logger.error('Send message error:', error)
      updateMessageStatus(aiMessage.id, MessageStatus.FAILED)
      updateMessageContent(aiMessage.id, '', { error: (error as Error).message })
      throw error
    }
  }

  async function connectStream(streamUrl: string, messageId: string) {
    isStreaming.value = true

    sseClient.value = new SSEClient({
      onMessage: (chunk: StreamChunk) => {
        handleStreamChunk(messageId, chunk)
      },
      onError: (error: Error) => {
        logger.error('SSE error:', error)
        updateMessageStatus(messageId, MessageStatus.FAILED)
        updateMessageContent(messageId, '', { error: error.message })
        isStreaming.value = false
      },
      onComplete: () => {
        updateMessageStatus(messageId, MessageStatus.COMPLETED)
        isStreaming.value = false
        currentMessageId.value = null
      }
    })

    sseClient.value.connect(streamUrl)
  }

  function handleStreamChunk(messageId: string, chunk: StreamChunk) {
    const message = messages.value.find(m => m.id === messageId)
    if (!message) return

    switch (chunk.type) {
      case 'token':
        // 追加 token 到消息内容
        message.content += chunk.content || ''
        break
      case 'thinking':
        // 更新思考过程
        if (!message.metadata) message.metadata = {}
        message.metadata.thinking = chunk.content || ''
        break
      case 'done':
        // 流式响应完成
        updateMessageStatus(messageId, MessageStatus.COMPLETED)
        break
      case 'error':
        // 错误处理
        updateMessageStatus(messageId, MessageStatus.FAILED)
        if (!message.metadata) message.metadata = {}
        message.metadata.error = chunk.content || '未知错误'
        break
    }
  }

  function updateMessageStatus(messageId: string, status: MessageStatus) {
    const message = messages.value.find(m => m.id === messageId)
    if (message) {
      message.status = status
    }
  }

  function updateMessageContent(messageId: string, content: string, metadata?: Record<string, any>) {
    const message = messages.value.find(m => m.id === messageId)
    if (message) {
      message.content = content
      if (metadata) {
        message.metadata = { ...message.metadata, ...metadata }
      }
    }
  }

  async function retryMessage(messageId: string) {
    const message = messages.value.find(m => m.id === messageId)
    if (!message) return

    updateMessageStatus(messageId, MessageStatus.PENDING)
    updateMessageContent(messageId, '')

    try {
      const response = await chatAPI.retryMessage(messageId)
      updateMessageStatus(messageId, MessageStatus.STREAMING)
      await connectStream(response.streamUrl, messageId)
    } catch (error) {
      logger.error('Retry message error:', error)
      updateMessageStatus(messageId, MessageStatus.FAILED)
      updateMessageContent(messageId, '', { error: (error as Error).message })
      throw error
    }
  }

  function submitFeedback(messageId: string, type: 'like' | 'dislike') {
    const message = messages.value.find(m => m.id === messageId)
    if (message) {
      message.feedback = {
        type,
        timestamp: Date.now()
      }
    }
  }

  function clearMessages() {
    messages.value = []
    currentMessageId.value = null
  }

  function loadMessages(sessionMessages: Message[]) {
    messages.value = sessionMessages
  }

  function disconnectStream() {
    if (sseClient.value) {
      sseClient.value.disconnect()
      sseClient.value = null
    }
    isStreaming.value = false
  }

  return {
    // 状态
    messages: sortedMessages,
    currentMessageId,
    isStreaming,
    lastMessage,
    hasMessages,
    // 操作
    sendMessage,
    retryMessage,
    submitFeedback,
    clearMessages,
    loadMessages,
    disconnectStream
  }
})
```

### Settings Store

```typescript
// stores/settings.ts

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { UserSettings, Language, AnalysisDepth, Theme } from '@/types/settings'
import { DEFAULT_SETTINGS } from '@/types/settings'
import { storage } from '@/utils/storage'
import { logger } from '@/utils/logger'

const SETTINGS_KEY = 'user_settings'

export const useSettingsStore = defineStore('settings', () => {
  // 状态
  const settings = ref<UserSettings>({ ...DEFAULT_SETTINGS })

  // 初始化:从本地存储加载设置
  function init() {
    try {
      const saved = storage.get<UserSettings>(SETTINGS_KEY)
      if (saved) {
        settings.value = { ...DEFAULT_SETTINGS, ...saved }
        logger.debug('Settings loaded from storage:', settings.value)
      }
    } catch (error) {
      logger.error('Failed to load settings:', error)
      settings.value = { ...DEFAULT_SETTINGS }
    }
  }

  // 监听设置变化,自动保存
  watch(
    settings,
    (newSettings) => {
      try {
        storage.set(SETTINGS_KEY, newSettings)
        logger.debug('Settings saved to storage:', newSettings)
      } catch (error) {
        logger.error('Failed to save settings:', error)
      }
    },
    { deep: true }
  )

  // 操作
  function updateSettings(partial: Partial<UserSettings>) {
    settings.value = { ...settings.value, ...partial }
  }

  function setLanguage(language: Language) {
    settings.value.language = language
  }

  function setAnalysisDepth(depth: AnalysisDepth) {
    settings.value.analysisDepth = depth
  }

  function setTheme(theme: Theme) {
    settings.value.theme = theme
    applyTheme(theme)
  }

  function toggleShowThinking() {
    settings.value.showThinking = !settings.value.showThinking
  }

  function toggleAutoScroll() {
    settings.value.autoScroll = !settings.value.autoScroll
  }

  function resetSettings() {
    settings.value = { ...DEFAULT_SETTINGS }
  }

  // 应用主题
  function applyTheme(theme: Theme) {
    const root = document.documentElement
    
    if (theme === Theme.AUTO) {
      // 根据系统偏好设置主题
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      root.classList.toggle('dark', prefersDark)
    } else {
      root.classList.toggle('dark', theme === Theme.DARK)
    }
  }

  // 初始化
  init()

  return {
    // 状态
    settings,
    // 操作
    updateSettings,
    setLanguage,
    setAnalysisDepth,
    setTheme,
    toggleShowThinking,
    toggleAutoScroll,
    resetSettings
  }
})
```


### Session Store

```typescript
// stores/session.ts

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { sessionAPI } from '@/api/session'
import type { Session, SessionWithMessages } from '@/types/session'
import { logger } from '@/utils/logger'
import { nanoid } from 'nanoid'
import { useChatStore } from './chat'

export const useSessionStore = defineStore('session', () => {
  // 状态
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<string | null>(null)
  const loading = ref(false)
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)

  // 计算属性
  const currentSession = computed(() => {
    return sessions.value.find(s => s.id === currentSessionId.value)
  })

  const sortedSessions = computed(() => {
    return [...sessions.value].sort((a, b) => b.updatedAt - a.updatedAt)
  })

  const hasMore = computed(() => {
    return sessions.value.length < total.value
  })

  // 操作
  async function createSession(name?: string, datasourceId?: string) {
    try {
      const response = await sessionAPI.createSession({ name, datasourceId })
      sessions.value.unshift(response.session)
      currentSessionId.value = response.session.id
      
      // 清空当前消息
      const chatStore = useChatStore()
      chatStore.clearMessages()
      
      logger.debug('Session created:', response.session)
      return response.session
    } catch (error) {
      logger.error('Create session error:', error)
      throw error
    }
  }

  async function loadSessions(reset = false) {
    if (reset) {
      page.value = 1
      sessions.value = []
    }

    loading.value = true
    try {
      const response = await sessionAPI.listSessions({
        page: page.value,
        pageSize: pageSize.value,
        sortBy: 'updatedAt',
        order: 'desc'
      })

      if (reset) {
        sessions.value = response.sessions
      } else {
        sessions.value.push(...response.sessions)
      }

      total.value = response.total
      page.value = response.page

      logger.debug('Sessions loaded:', response.sessions.length)
    } catch (error) {
      logger.error('Load sessions error:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function loadMoreSessions() {
    if (loading.value || !hasMore.value) return
    page.value += 1
    await loadSessions()
  }

  async function switchSession(sessionId: string) {
    if (currentSessionId.value === sessionId) return

    loading.value = true
    try {
      const response = await sessionAPI.getSession({ sessionId })
      currentSessionId.value = sessionId

      // 加载会话消息
      const chatStore = useChatStore()
      chatStore.loadMessages(response.session.messages)

      logger.debug('Session switched:', sessionId)
    } catch (error) {
      logger.error('Switch session error:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  async function renameSession(sessionId: string, name: string) {
    try {
      await sessionAPI.updateSession({ sessionId, name })
      
      const session = sessions.value.find(s => s.id === sessionId)
      if (session) {
        session.name = name
        session.updatedAt = Date.now()
      }

      logger.debug('Session renamed:', sessionId, name)
    } catch (error) {
      logger.error('Rename session error:', error)
      throw error
    }
  }

  async function deleteSession(sessionId: string) {
    try {
      await sessionAPI.deleteSession({ sessionId })
      
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      total.value -= 1

      // 如果删除的是当前会话,切换到第一个会话
      if (currentSessionId.value === sessionId) {
        if (sessions.value.length > 0) {
          await switchSession(sessions.value[0].id)
        } else {
          await createSession()
        }
      }

      logger.debug('Session deleted:', sessionId)
    } catch (error) {
      logger.error('Delete session error:', error)
      throw error
    }
  }

  function updateSessionTimestamp(sessionId: string) {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      session.updatedAt = Date.now()
      session.messageCount += 1
    }
  }

  return {
    // 状态
    sessions: sortedSessions,
    currentSessionId,
    currentSession,
    loading,
    hasMore,
    // 操作
    createSession,
    loadSessions,
    loadMoreSessions,
    switchSession,
    renameSession,
    deleteSession,
    updateSessionTimestamp
  }
})
```

### Tableau Store

```typescript
// stores/tableau.ts

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { DataSource } from '@/types/datasource'
import { logger } from '@/utils/logger'

declare global {
  interface Window {
    tableau: any
  }
}

export const useTableauStore = defineStore('tableau', () => {
  // 状态
  const initialized = ref(false)
  const datasources = ref<DataSource[]>([])
  const selectedDatasourceId = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 计算属性
  const selectedDatasource = computed(() => {
    return datasources.value.find(ds => ds.id === selectedDatasourceId.value)
  })

  const hasDatasources = computed(() => datasources.value.length > 0)

  // 操作
  async function initTableau() {
    if (initialized.value) return

    try {
      logger.debug('Initializing Tableau Extension API...')
      
      await window.tableau.extensions.initializeAsync()
      initialized.value = true
      
      logger.debug('Tableau Extension API initialized')
      
      // 加载数据源
      await loadDatasources()
      
      // 监听数据源变更
      window.tableau.extensions.dashboardContent.dashboard.addEventListener(
        window.tableau.TableauEventType.DatasourceChanged,
        handleDatasourceChanged
      )
    } catch (err) {
      logger.error('Tableau initialization error:', err)
      error.value = (err as Error).message
      throw err
    }
  }

  async function loadDatasources() {
    loading.value = true
    error.value = null

    try {
      const dashboard = window.tableau.extensions.dashboardContent.dashboard
      const worksheets = dashboard.worksheets
      
      const datasourceSet = new Set<string>()
      const datasourceList: DataSource[] = []

      // 遍历所有工作表获取数据源
      for (const worksheet of worksheets) {
        const datasourcesInWorksheet = await worksheet.getDataSourcesAsync()
        
        for (const ds of datasourcesInWorksheet) {
          if (!datasourceSet.has(ds.id)) {
            datasourceSet.add(ds.id)
            
            // 获取字段信息
            const fields = await ds.getFieldsAsync()
            
            datasourceList.push({
              id: ds.id,
              name: ds.name,
              type: ds.extractUpdateType || 'unknown',
              connectionType: ds.connectionName,
              fields: fields.map(field => ({
                id: field.id,
                name: field.name,
                dataType: field.dataType,
                role: field.role,
                aggregation: field.aggregation
              }))
            })
          }
        }
      }

      datasources.value = datasourceList
      
      // 自动选择第一个数据源
      if (datasourceList.length > 0 && !selectedDatasourceId.value) {
        selectedDatasourceId.value = datasourceList[0].id
      }

      logger.debug('Datasources loaded:', datasourceList.length)
    } catch (err) {
      logger.error('Load datasources error:', err)
      error.value = (err as Error).message
      throw err
    } finally {
      loading.value = false
    }
  }

  function selectDatasource(datasourceId: string) {
    if (datasources.value.some(ds => ds.id === datasourceId)) {
      selectedDatasourceId.value = datasourceId
      logger.debug('Datasource selected:', datasourceId)
    }
  }

  function handleDatasourceChanged() {
    logger.debug('Datasource changed event received')
    loadDatasources()
  }

  function cleanup() {
    if (initialized.value) {
      window.tableau.extensions.dashboardContent.dashboard.removeEventListener(
        window.tableau.TableauEventType.DatasourceChanged,
        handleDatasourceChanged
      )
    }
  }

  return {
    // 状态
    initialized,
    datasources,
    selectedDatasourceId,
    selectedDatasource,
    loading,
    error,
    hasDatasources,
    // 操作
    initTableau,
    loadDatasources,
    selectDatasource,
    cleanup
  }
})
```


## 样式设计

### Tailwind CSS 配置

```javascript
// tailwind.config.js

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}'
  ],
  darkMode: 'class', // 使用 class 策略
  theme: {
    extend: {
      colors: {
        // 主色调
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a'
        },
        // 中性色
        gray: {
          50: '#f9fafb',
          100: '#f3f4f6',
          200: '#e5e7eb',
          300: '#d1d5db',
          400: '#9ca3af',
          500: '#6b7280',
          600: '#4b5563',
          700: '#374151',
          800: '#1f2937',
          900: '#111827'
        },
        // 语义色
        success: '#10b981',
        warning: '#f59e0b',
        error: '#ef4444',
        info: '#3b82f6'
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif'
        ],
        mono: [
          'Menlo',
          'Monaco',
          'Consolas',
          'Liberation Mono',
          'Courier New',
          'monospace'
        ]
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1rem' }],
        sm: ['0.875rem', { lineHeight: '1.25rem' }],
        base: ['1rem', { lineHeight: '1.5rem' }],
        lg: ['1.125rem', { lineHeight: '1.75rem' }],
        xl: ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
        '3xl': ['1.875rem', { lineHeight: '2.25rem' }]
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
        '128': '32rem'
      },
      borderRadius: {
        '4xl': '2rem'
      },
      boxShadow: {
        'soft': '0 2px 8px rgba(0, 0, 0, 0.08)',
        'medium': '0 4px 16px rgba(0, 0, 0, 0.12)',
        'strong': '0 8px 24px rgba(0, 0, 0, 0.16)'
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-in',
        'slide-in': 'slideIn 0.3s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite'
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' }
        },
        slideIn: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' }
        }
      }
    }
  },
  plugins: [
    require('@tailwindcss/typography'),
    require('@tailwindcss/forms')
  ]
}
```

### CSS 变量

```css
/* assets/styles/variables.css */

:root {
  /* 颜色 */
  --color-bg-primary: #ffffff;
  --color-bg-secondary: #f9fafb;
  --color-bg-tertiary: #f3f4f6;
  --color-text-primary: #111827;
  --color-text-secondary: #6b7280;
  --color-text-tertiary: #9ca3af;
  --color-border: #e5e7eb;
  --color-divider: #f3f4f6;
  
  /* 消息颜色 */
  --color-message-user-bg: #eff6ff;
  --color-message-user-text: #1e40af;
  --color-message-ai-bg: #f9fafb;
  --color-message-ai-text: #111827;
  
  /* 阴影 */
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.07);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1);
  
  /* 圆角 */
  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
  --radius-xl: 1rem;
  
  /* 间距 */
  --spacing-xs: 0.25rem;
  --spacing-sm: 0.5rem;
  --spacing-md: 1rem;
  --spacing-lg: 1.5rem;
  --spacing-xl: 2rem;
  
  /* 过渡 */
  --transition-fast: 150ms;
  --transition-base: 200ms;
  --transition-slow: 300ms;
  
  /* Z-index */
  --z-dropdown: 1000;
  --z-modal: 1100;
  --z-tooltip: 1200;
}

/* 深色主题 */
.dark {
  --color-bg-primary: #111827;
  --color-bg-secondary: #1f2937;
  --color-bg-tertiary: #374151;
  --color-text-primary: #f9fafb;
  --color-text-secondary: #d1d5db;
  --color-text-tertiary: #9ca3af;
  --color-border: #374151;
  --color-divider: #1f2937;
  
  --color-message-user-bg: #1e3a8a;
  --color-message-user-text: #dbeafe;
  --color-message-ai-bg: #1f2937;
  --color-message-ai-text: #f9fafb;
  
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 4px 6px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.5);
}
```

### 主题样式

```css
/* assets/styles/themes.css */

/* 全局样式 */
body {
  font-family: var(--font-sans);
  color: var(--color-text-primary);
  background-color: var(--color-bg-primary);
  transition: background-color var(--transition-base), color var(--transition-base);
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--color-bg-secondary);
}

::-webkit-scrollbar-thumb {
  background: var(--color-border);
  border-radius: var(--radius-md);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-tertiary);
}

/* 焦点样式 */
*:focus-visible {
  outline: 2px solid var(--color-primary-500);
  outline-offset: 2px;
}

/* 选择文本样式 */
::selection {
  background-color: var(--color-primary-200);
  color: var(--color-primary-900);
}

.dark ::selection {
  background-color: var(--color-primary-800);
  color: var(--color-primary-100);
}

/* 动画 */
@keyframes typing {
  0%, 100% { opacity: 0.2; }
  50% { opacity: 1; }
}

.typing-indicator span {
  animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

/* Markdown 样式 */
.markdown-content {
  @apply prose prose-sm max-w-none;
  @apply dark:prose-invert;
}

.markdown-content pre {
  @apply bg-gray-100 dark:bg-gray-800 rounded-lg p-4;
}

.markdown-content code {
  @apply bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm;
}

.markdown-content table {
  @apply w-full border-collapse;
}

.markdown-content th,
.markdown-content td {
  @apply border border-gray-300 dark:border-gray-600 px-4 py-2;
}

.markdown-content th {
  @apply bg-gray-100 dark:bg-gray-800 font-semibold;
}

.markdown-content tr:nth-child(even) {
  @apply bg-gray-50 dark:bg-gray-900;
}
```


## 性能优化策略

### 1. 虚拟滚动

对于消息列表,当消息数量超过 100 条时,使用虚拟滚动优化渲染性能。

```vue
<!-- components/chat/MessageList.vue -->
<template>
  <RecycleScroller
    v-if="messages.length > 100"
    :items="messages"
    :item-size="estimatedItemSize"
    key-field="id"
    class="message-list"
  >
    <template #default="{ item }">
      <MessageItem :message="item" @feedback="handleFeedback" />
    </template>
  </RecycleScroller>
  
  <div v-else class="message-list">
    <MessageItem
      v-for="message in messages"
      :key="message.id"
      :message="message"
      @feedback="handleFeedback"
    />
  </div>
</template>

<script setup lang="ts">
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

const estimatedItemSize = 120 // 估计的消息项高度
</script>
```

### 2. Markdown 渲染防抖

对于流式响应,使用防抖优化 Markdown 渲染频率。

```typescript
// composables/useMarkdown.ts

import { ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import { debounce } from 'lodash-es'

export function useMarkdown(content: Ref<string>, delay = 300) {
  const renderedHTML = ref('')
  const md = new MarkdownIt({
    html: false, // 禁用 HTML 标签(安全)
    linkify: true,
    typographer: true,
    highlight: (str, lang) => {
      if (lang && hljs.getLanguage(lang)) {
        try {
          return hljs.highlight(str, { language: lang }).value
        } catch (err) {
          console.error('Highlight error:', err)
        }
      }
      return ''
    }
  })

  // 防抖渲染函数
  const debouncedRender = debounce((text: string) => {
    renderedHTML.value = md.render(text)
  }, delay)

  // 监听内容变化
  watch(content, (newContent) => {
    debouncedRender(newContent)
  }, { immediate: true })

  return {
    renderedHTML
  }
}
```

### 3. 代码分割

使用 Vite 的动态导入实现路由级别和组件级别的代码分割。

```typescript
// main.ts

import { createApp } from 'vue'
import App from './App.vue'

const app = createApp(App)

// 懒加载大型组件
const SettingsPanel = defineAsyncComponent(() =>
  import('./components/settings/SettingsPanel.vue')
)

const HistoryPanel = defineAsyncComponent(() =>
  import('./components/session/HistoryPanel.vue')
)

app.component('SettingsPanel', SettingsPanel)
app.component('HistoryPanel', HistoryPanel)

app.mount('#app')
```

### 4. 图片懒加载

对于消息中的图片,使用懒加载优化首屏性能。

```vue
<template>
  <img
    v-lazy="imageSrc"
    :alt="imageAlt"
    class="message-image"
  />
</template>

<script setup lang="ts">
import { directive as vLazy } from 'vue3-lazy'
</script>
```

### 5. 缓存策略

#### Markdown 渲染缓存

```typescript
// utils/markdown.ts

import LRUCache from 'lru-cache'

const markdownCache = new LRUCache<string, string>({
  max: 500, // 最多缓存 500 条
  ttl: 1000 * 60 * 60 // 1 小时过期
})

export function renderMarkdown(content: string): string {
  const cached = markdownCache.get(content)
  if (cached) {
    return cached
  }

  const rendered = md.render(content)
  markdownCache.set(content, rendered)
  return rendered
}
```

#### API 响应缓存

```typescript
// api/client.ts

import { setupCache } from 'axios-cache-interceptor'

const cachedClient = setupCache(apiClient.instance, {
  ttl: 1000 * 60 * 5, // 5 分钟
  methods: ['get'],
  cachePredicate: {
    statusCheck: (status) => status >= 200 && status < 300
  }
})
```

### 6. 构建优化

```typescript
// vite.config.ts

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { visualizer } from 'rollup-plugin-visualizer'

export default defineConfig({
  plugins: [
    vue(),
    visualizer({
      open: true,
      gzipSize: true,
      brotliSize: true
    })
  ],
  build: {
    target: 'es2015',
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true, // 生产环境移除 console
        drop_debugger: true
      }
    },
    rollupOptions: {
      output: {
        manualChunks: {
          // 将大型依赖分离到单独的 chunk
          'vendor-vue': ['vue', 'pinia', 'vue-router'],
          'vendor-ui': ['element-plus'],
          'vendor-markdown': ['markdown-it', 'highlight.js'],
          'vendor-utils': ['axios', 'lodash-es', 'nanoid']
        }
      }
    },
    chunkSizeWarningLimit: 1000 // 提高警告阈值到 1MB
  },
  optimizeDeps: {
    include: [
      'vue',
      'pinia',
      'axios',
      'markdown-it',
      'highlight.js'
    ]
  }
})
```

### 7. 预加载和预连接

```html
<!-- index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  
  <!-- 预连接到 API 服务器 -->
  <link rel="preconnect" href="https://api.example.com">
  <link rel="dns-prefetch" href="https://api.example.com">
  
  <!-- 预加载关键资源 -->
  <link rel="preload" href="/fonts/inter.woff2" as="font" type="font/woff2" crossorigin>
  
  <title>Tableau AI Assistant</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
```

### 8. Web Workers

对于计算密集型任务(如大量数据处理),使用 Web Workers 避免阻塞主线程。

```typescript
// workers/data-processor.worker.ts

self.addEventListener('message', (event) => {
  const { type, data } = event.data

  switch (type) {
    case 'PROCESS_LARGE_DATASET':
      const result = processLargeDataset(data)
      self.postMessage({ type: 'RESULT', result })
      break
  }
})

function processLargeDataset(data: any[]) {
  // 处理大量数据
  return data.map(item => {
    // 复杂计算
    return transformItem(item)
  })
}
```

```typescript
// composables/useWorker.ts

import { ref } from 'vue'
import DataProcessorWorker from '@/workers/data-processor.worker?worker'

export function useDataProcessor() {
  const worker = new DataProcessorWorker()
  const processing = ref(false)

  function processData(data: any[]) {
    return new Promise((resolve, reject) => {
      processing.value = true

      worker.postMessage({ type: 'PROCESS_LARGE_DATASET', data })

      worker.onmessage = (event) => {
        processing.value = false
        resolve(event.data.result)
      }

      worker.onerror = (error) => {
        processing.value = false
        reject(error)
      }
    })
  }

  return {
    processing,
    processData
  }
}
```

### 9. 性能监控

```typescript
// utils/performance.ts

export class PerformanceMonitor {
  private marks: Map<string, number> = new Map()

  mark(name: string): void {
    this.marks.set(name, performance.now())
  }

  measure(name: string, startMark: string): number {
    const start = this.marks.get(startMark)
    if (!start) {
      console.warn(`Start mark "${startMark}" not found`)
      return 0
    }

    const duration = performance.now() - start
    console.log(`[Performance] ${name}: ${duration.toFixed(2)}ms`)
    
    // 发送到监控服务
    if (duration > 1000) {
      this.reportSlowOperation(name, duration)
    }

    return duration
  }

  private reportSlowOperation(name: string, duration: number): void {
    // 发送到监控服务(如 Sentry、DataDog)
    console.warn(`Slow operation detected: ${name} took ${duration}ms`)
  }
}

export const perfMonitor = new PerformanceMonitor()
```

使用示例:

```typescript
// stores/chat.ts

import { perfMonitor } from '@/utils/performance'

async function sendMessage(content: string) {
  perfMonitor.mark('send-message-start')
  
  // 发送消息逻辑
  await chatAPI.sendMessage({ ... })
  
  perfMonitor.measure('Send Message', 'send-message-start')
}
```

### 10. 资源优化清单

| 优化项 | 目标 | 实现方式 |
|--------|------|----------|
| 首屏加载时间 | < 2s | 代码分割、预加载、压缩 |
| 消息渲染时间 | < 50ms | 虚拟滚动、防抖 |
| Markdown 渲染 | < 100ms | 缓存、防抖 |
| 构建产物大小 | < 1MB (gzip) | Tree shaking、压缩、分包 |
| 内存占用 | < 100MB | LRU 缓存、及时清理 |
| FPS | > 60 | 避免重排重绘、使用 transform |


## 错误处理

### 错误类型定义

```typescript
// types/error.ts

export enum ErrorType {
  NETWORK = 'network',
  API = 'api',
  VALIDATION = 'validation',
  TABLEAU = 'tableau',
  UNKNOWN = 'unknown'
}

export interface AppError {
  type: ErrorType
  message: string
  code?: string
  details?: any
  timestamp: number
  retryable: boolean
}

export class NetworkError extends Error implements AppError {
  type = ErrorType.NETWORK
  retryable = true
  timestamp = Date.now()

  constructor(message: string, public code?: string, public details?: any) {
    super(message)
    this.name = 'NetworkError'
  }
}

export class APIError extends Error implements AppError {
  type = ErrorType.API
  retryable: boolean
  timestamp = Date.now()

  constructor(
    message: string,
    public code?: string,
    public details?: any,
    retryable = false
  ) {
    super(message)
    this.name = 'APIError'
    this.retryable = retryable
  }
}

export class ValidationError extends Error implements AppError {
  type = ErrorType.VALIDATION
  retryable = false
  timestamp = Date.now()

  constructor(message: string, public code?: string, public details?: any) {
    super(message)
    this.name = 'ValidationError'
  }
}

export class TableauError extends Error implements AppError {
  type = ErrorType.TABLEAU
  retryable = false
  timestamp = Date.now()

  constructor(message: string, public code?: string, public details?: any) {
    super(message)
    this.name = 'TableauError'
  }
}
```

### 全局错误处理

```typescript
// utils/error-handler.ts

import { logger } from './logger'
import type { AppError } from '@/types/error'

export class ErrorHandler {
  private static instance: ErrorHandler

  static getInstance(): ErrorHandler {
    if (!ErrorHandler.instance) {
      ErrorHandler.instance = new ErrorHandler()
    }
    return ErrorHandler.instance
  }

  handle(error: Error | AppError): void {
    logger.error('Error occurred:', error)

    // 根据错误类型显示不同的提示
    if (this.isAppError(error)) {
      this.handleAppError(error)
    } else {
      this.handleUnknownError(error)
    }

    // 发送错误到监控服务
    this.reportError(error)
  }

  private isAppError(error: any): error is AppError {
    return 'type' in error && 'retryable' in error
  }

  private handleAppError(error: AppError): void {
    const message = this.getUserFriendlyMessage(error)
    
    // 显示错误提示(使用 UI 组件)
    window.$message?.error({
      message,
      duration: 5000,
      showClose: true
    })
  }

  private handleUnknownError(error: Error): void {
    window.$message?.error({
      message: '发生未知错误,请稍后重试',
      duration: 5000,
      showClose: true
    })
  }

  private getUserFriendlyMessage(error: AppError): string {
    switch (error.type) {
      case 'network':
        return '网络连接失败,请检查网络设置'
      case 'api':
        return error.message || 'API 请求失败'
      case 'validation':
        return error.message || '输入验证失败'
      case 'tableau':
        return 'Tableau 集成错误: ' + error.message
      default:
        return '发生错误: ' + error.message
    }
  }

  private reportError(error: Error | AppError): void {
    // 发送到错误监控服务(如 Sentry)
    if (import.meta.env.PROD) {
      // Sentry.captureException(error)
    }
  }
}

export const errorHandler = ErrorHandler.getInstance()
```

### 错误边界组件

```vue
<!-- components/common/ErrorBoundary.vue -->
<template>
  <div v-if="error" class="error-boundary">
    <div class="error-content">
      <h3>出错了</h3>
      <p>{{ error.message }}</p>
      <button @click="retry" class="retry-button">
        重试
      </button>
    </div>
  </div>
  <slot v-else />
</template>

<script setup lang="ts">
import { ref, onErrorCaptured } from 'vue'
import { logger } from '@/utils/logger'

const error = ref<Error | null>(null)

onErrorCaptured((err) => {
  error.value = err
  logger.error('Component error:', err)
  return false // 阻止错误继续传播
})

function retry() {
  error.value = null
}
</script>
```

## 测试策略

### 单元测试

使用 Vitest 进行单元测试,覆盖工具函数、Composables 和 Stores。

```typescript
// tests/unit/utils/validator.spec.ts

import { describe, it, expect } from 'vitest'
import { validateMessage, validateSessionName } from '@/utils/validator'

describe('Validator', () => {
  describe('validateMessage', () => {
    it('应该拒绝空消息', () => {
      expect(validateMessage('')).toBe(false)
      expect(validateMessage('   ')).toBe(false)
    })

    it('应该拒绝超长消息', () => {
      const longMessage = 'a'.repeat(5001)
      expect(validateMessage(longMessage)).toBe(false)
    })

    it('应该接受有效消息', () => {
      expect(validateMessage('Hello')).toBe(true)
      expect(validateMessage('这是一条测试消息')).toBe(true)
    })
  })

  describe('validateSessionName', () => {
    it('应该拒绝空会话名', () => {
      expect(validateSessionName('')).toBe(false)
    })

    it('应该拒绝超长会话名', () => {
      const longName = 'a'.repeat(101)
      expect(validateSessionName(longName)).toBe(false)
    })

    it('应该接受有效会话名', () => {
      expect(validateSessionName('新会话')).toBe(true)
    })
  })
})
```

```typescript
// tests/unit/stores/chat.spec.ts

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '@/stores/chat'
import { MessageRole, MessageStatus } from '@/types/chat'

describe('Chat Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('应该初始化为空消息列表', () => {
    const store = useChatStore()
    expect(store.messages).toEqual([])
    expect(store.hasMessages).toBe(false)
  })

  it('应该按时间戳排序消息', () => {
    const store = useChatStore()
    const messages = [
      { id: '1', timestamp: 1000, role: MessageRole.USER, content: 'A', status: MessageStatus.COMPLETED, sessionId: 's1' },
      { id: '2', timestamp: 500, role: MessageRole.USER, content: 'B', status: MessageStatus.COMPLETED, sessionId: 's1' },
      { id: '3', timestamp: 1500, role: MessageRole.USER, content: 'C', status: MessageStatus.COMPLETED, sessionId: 's1' }
    ]
    
    store.loadMessages(messages)
    
    expect(store.messages[0].id).toBe('2')
    expect(store.messages[1].id).toBe('1')
    expect(store.messages[2].id).toBe('3')
  })

  it('应该正确追加流式 token', () => {
    const store = useChatStore()
    const message = {
      id: 'm1',
      sessionId: 's1',
      role: MessageRole.ASSISTANT,
      content: 'Hello',
      status: MessageStatus.STREAMING,
      timestamp: Date.now()
    }
    
    store.loadMessages([message])
    
    // 模拟追加 token
    const msg = store.messages.find(m => m.id === 'm1')
    if (msg) {
      msg.content += ' World'
    }
    
    expect(store.messages[0].content).toBe('Hello World')
  })
})
```

### 属性测试(Property-Based Testing)

使用 fast-check 进行属性测试,验证通用属性。

```typescript
// tests/property/serialization.spec.ts

import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { serializeSession, deserializeSession } from '@/utils/storage'
import type { Session } from '@/types/session'

describe('Serialization Properties', () => {
  it('会话序列化/反序列化应该是对称的(round-trip)', () => {
    fc.assert(
      fc.property(
        fc.record({
          id: fc.string(),
          name: fc.string(),
          createdAt: fc.integer({ min: 0 }),
          updatedAt: fc.integer({ min: 0 }),
          messageCount: fc.integer({ min: 0 })
        }),
        (session: Session) => {
          const serialized = serializeSession(session)
          const deserialized = deserializeSession(serialized)
          
          // Round-trip 属性:序列化后反序列化应该得到等价对象
          expect(deserialized).toEqual(session)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('用户设置序列化/反序列化应该是对称的', () => {
    fc.assert(
      fc.property(
        fc.record({
          language: fc.constantFrom('zh-CN', 'en-US'),
          analysisDepth: fc.constantFrom('standard', 'deep'),
          theme: fc.constantFrom('light', 'dark', 'auto'),
          showThinking: fc.boolean(),
          autoScroll: fc.boolean(),
          soundEnabled: fc.boolean()
        }),
        (settings) => {
          const serialized = JSON.stringify(settings)
          const deserialized = JSON.parse(serialized)
          
          expect(deserialized).toEqual(settings)
        }
      ),
      { numRuns: 100 }
    )
  })
})
```

```typescript
// tests/property/validation.spec.ts

import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { validateMessage } from '@/utils/validator'

describe('Validation Properties', () => {
  it('空白字符串应该总是被拒绝', () => {
    fc.assert(
      fc.property(
        fc.string().filter(s => s.trim() === ''),
        (whitespaceString) => {
          // 错误条件属性:所有空白字符串都应该被拒绝
          expect(validateMessage(whitespaceString)).toBe(false)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('超长字符串应该总是被拒绝', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 5001 }),
        (longString) => {
          // 错误条件属性:所有超过 5000 字符的字符串都应该被拒绝
          expect(validateMessage(longString)).toBe(false)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('有效字符串应该总是被接受', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 5000 }).filter(s => s.trim() !== ''),
        (validString) => {
          // 正常条件属性:所有有效字符串都应该被接受
          expect(validateMessage(validString)).toBe(true)
        }
      ),
      { numRuns: 100 }
    )
  })
})
```

```typescript
// tests/property/invariants.spec.ts

import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { useChatStore } from '@/stores/chat'
import { setActivePinia, createPinia } from 'pinia'

describe('Invariant Properties', () => {
  it('消息列表应该始终按时间戳升序排列', () => {
    setActivePinia(createPinia())
    const store = useChatStore()

    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            id: fc.string(),
            sessionId: fc.string(),
            role: fc.constantFrom('user', 'assistant'),
            content: fc.string(),
            status: fc.constantFrom('pending', 'completed', 'failed'),
            timestamp: fc.integer({ min: 0 })
          }),
          { minLength: 2 }
        ),
        (messages) => {
          store.loadMessages(messages)
          
          // 不变性属性:消息列表应该始终按时间戳升序排列
          const timestamps = store.messages.map(m => m.timestamp)
          for (let i = 1; i < timestamps.length; i++) {
            expect(timestamps[i]).toBeGreaterThanOrEqual(timestamps[i - 1])
          }
        }
      ),
      { numRuns: 100 }
    )
  })
})
```

### 组件测试

使用 @vue/test-utils 进行组件测试。

```typescript
// tests/unit/components/MessageItem.spec.ts

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageItem from '@/components/chat/MessageItem.vue'
import { MessageRole, MessageStatus } from '@/types/chat'

describe('MessageItem', () => {
  it('应该渲染用户消息', () => {
    const wrapper = mount(MessageItem, {
      props: {
        message: {
          id: '1',
          sessionId: 's1',
          role: MessageRole.USER,
          content: 'Hello',
          status: MessageStatus.COMPLETED,
          timestamp: Date.now()
        }
      }
    })

    expect(wrapper.text()).toContain('Hello')
    expect(wrapper.classes()).toContain('message-user')
  })

  it('应该渲染 AI 消息', () => {
    const wrapper = mount(MessageItem, {
      props: {
        message: {
          id: '2',
          sessionId: 's1',
          role: MessageRole.ASSISTANT,
          content: 'Hi there',
          status: MessageStatus.COMPLETED,
          timestamp: Date.now()
        }
      }
    })

    expect(wrapper.text()).toContain('Hi there')
    expect(wrapper.classes()).toContain('message-ai')
  })

  it('应该显示打字指示器(流式响应中)', () => {
    const wrapper = mount(MessageItem, {
      props: {
        message: {
          id: '3',
          sessionId: 's1',
          role: MessageRole.ASSISTANT,
          content: '',
          status: MessageStatus.STREAMING,
          timestamp: Date.now()
        }
      }
    })

    expect(wrapper.find('.typing-indicator').exists()).toBe(true)
  })

  it('应该触发反馈事件', async () => {
    const wrapper = mount(MessageItem, {
      props: {
        message: {
          id: '4',
          sessionId: 's1',
          role: MessageRole.ASSISTANT,
          content: 'Test',
          status: MessageStatus.COMPLETED,
          timestamp: Date.now()
        },
        showFeedback: true
      }
    })

    await wrapper.find('.feedback-like').trigger('click')
    expect(wrapper.emitted('feedback')).toBeTruthy()
    expect(wrapper.emitted('feedback')?.[0]).toEqual(['like'])
  })
})
```

### 端到端测试

使用 Playwright 进行端到端测试。

```typescript
// tests/e2e/chat-flow.spec.ts

import { test, expect } from '@playwright/test'

test.describe('聊天流程', () => {
  test('应该能够发送消息并接收回复', async ({ page }) => {
    await page.goto('http://localhost:5173')

    // 等待应用加载
    await page.waitForSelector('.chat-container')

    // 输入消息
    const input = page.locator('.input-box textarea')
    await input.fill('请分析销售数据')

    // 发送消息
    await page.locator('.send-button').click()

    // 验证用户消息显示
    await expect(page.locator('.message-user').last()).toContainText('请分析销售数据')

    // 等待 AI 回复
    await page.waitForSelector('.message-ai', { timeout: 10000 })

    // 验证 AI 消息显示
    const aiMessage = page.locator('.message-ai').last()
    await expect(aiMessage).toBeVisible()
  })

  test('应该能够切换会话', async ({ page }) => {
    await page.goto('http://localhost:5173')

    // 打开历史面板
    await page.locator('.history-button').click()

    // 创建新会话
    await page.locator('.new-session-button').click()

    // 验证消息列表已清空
    await expect(page.locator('.message-item')).toHaveCount(0)

    // 验证显示空状态
    await expect(page.locator('.empty-state')).toBeVisible()
  })
})
```

### 测试覆盖率目标

| 类型 | 目标覆盖率 |
|------|-----------|
| 工具函数 | > 90% |
| Stores | > 85% |
| Composables | > 80% |
| 组件 | > 70% |
| 整体 | > 75% |


## 正确性属性

*属性是一个特征或行为,应该在系统的所有有效执行中保持为真——本质上是关于系统应该做什么的形式化陈述。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*

### 属性反思

在生成正确性属性之前,我们需要识别并消除冗余属性:

**识别的冗余**:
1. 需求 20.2(空白字符验证)和需求 1.3(提交空消息)测试相同的功能,可以合并为一个属性
2. 需求 21.1(消息列表排序)和需求 21.5(token 顺序)都涉及顺序不变性,但测试不同的场景,应保留两个属性
3. 需求 22.1-22.5 都是幂等性属性,但测试不同的操作,应保留所有属性

**合并决策**:
- 将需求 20.2 和 1.3 合并为"空白消息拒绝"属性
- 保留其他所有属性,因为它们测试不同的场景或不同的不变性

### 属性 1: 会话序列化 Round-trip

*对于任意*有效的会话对象,将其序列化为 JSON 后再反序列化,应该产生与原对象等价的会话对象。

**验证需求**: 19.3

### 属性 2: 用户设置序列化 Round-trip

*对于任意*有效的用户设置对象,将其序列化为 JSON 后再反序列化,应该产生与原对象等价的设置对象。

**验证需求**: 19.6

### 属性 3: 超长消息拒绝

*对于任意*长度超过 5000 字符的字符串,系统应该拒绝该消息并显示错误提示。

**验证需求**: 20.1

### 属性 4: 空白消息拒绝

*对于任意*仅包含空白字符(空格、制表符、换行符等)的字符串,系统应该拒绝该消息并显示错误提示。

**验证需求**: 20.2, 1.3

### 属性 5: 消息列表时间戳排序不变性

*对于任意*消息列表,无论以何种顺序添加消息,消息列表应该始终按时间戳升序排列。

**验证需求**: 21.1

### 属性 6: 会话切换消息数量不变性

*对于任意*会话,切换到其他会话后再切换回来,该会话的消息数量应该保持不变。

**验证需求**: 21.2

### 属性 7: 部分设置更新不变性

*对于任意*用户设置对象和部分更新,更新后未被修改的设置项应该保持原值不变。

**验证需求**: 21.3

### 属性 8: Markdown 渲染内容不变性

*对于任意*消息内容,Markdown 渲染后原始消息内容应该保持不变(渲染是纯函数)。

**验证需求**: 21.4

### 属性 9: 流式 Token 顺序不变性

*对于任意*token 序列,追加新 token 时,已接收 token 的顺序应该保持不变。

**验证需求**: 21.5

### 属性 10: 创建会话幂等性

*对于任意*会话创建请求,在短时间内多次执行应该只创建一个会话(防止重复点击)。

**验证需求**: 22.1

### 属性 11: 删除会话幂等性

*对于任意*会话 ID,多次删除同一会话应该与删除一次的效果相同(第二次及以后返回"不存在"错误)。

**验证需求**: 22.2

### 属性 12: 消息反馈幂等性

*对于任意*消息 ID 和反馈类型,对同一消息多次提交相同反馈应该只记录第一次反馈。

**验证需求**: 22.3

### 属性 13: Tableau API 初始化幂等性

*对于任意*初始化调用序列,多次调用 Tableau Extension API 初始化函数应该只执行一次初始化。

**验证需求**: 22.4

### 属性 14: 会话加载幂等性

*对于任意*会话 ID,多次加载同一会话应该产生相同的消息列表。

**验证需求**: 22.5

### 属性 15: 虚拟滚动内容等价性

*对于任意*消息列表,使用虚拟滚动渲染应该显示与完整渲染相同的消息内容(仅渲染方式不同)。

**验证需求**: 23.1

### 属性 16: 防抖渲染结果等价性

*对于任意*Markdown 内容,使用防抖优化的渲染最终应该产生与立即渲染相同的 HTML 结果。

**验证需求**: 23.2

### 属性 17: 虚拟滚动渲染数量约束

*对于任意*长度为 N 的消息列表,虚拟滚动实际渲染的消息数量应该小于或等于 N。

**验证需求**: 23.5

### 属性 18: 消息添加后列表增长

*对于任意*有效消息内容,发送消息后消息列表的长度应该增加(至少增加 1,用户消息)。

**验证需求**: 1.2

### 属性 19: 流式 Token 追加累积

*对于任意*token 序列,按顺序追加所有 token 后,消息内容应该等于所有 token 的连接。

**验证需求**: 2.2

### 属性 20: Markdown 渲染输出为 HTML

*对于任意*包含 Markdown 语法的文本,渲染后的输出应该是有效的 HTML 字符串。

**验证需求**: 3.1

### 属性 21: 会话 ID 唯一性

*对于任意*会话创建序列,每次创建的会话 ID 应该是唯一的(不与已有会话 ID 重复)。

**验证需求**: 6.2

### 属性 22: 新会话消息列表为空

*对于任意*新创建的会话,其消息列表应该为空(长度为 0)。

**验证需求**: 6.2


## 安全性设计

### Content Security Policy

```html
<!-- index.html -->
<meta http-equiv="Content-Security-Policy" content="
  default-src 'self';
  script-src 'self' 'unsafe-inline' 'unsafe-eval';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: https:;
  font-src 'self' data:;
  connect-src 'self' https://api.example.com;
  frame-ancestors 'self' https://*.tableau.com;
">
```

### XSS 防护

```typescript
// utils/security.ts

import DOMPurify from 'dompurify'

/**
 * 清理 HTML 内容,防止 XSS 攻击
 */
export function sanitizeHTML(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'ul', 'ol', 'li', 'a', 'code', 'pre', 'blockquote', 'table', 'thead',
      'tbody', 'tr', 'th', 'td'
    ],
    ALLOWED_ATTR: ['href', 'class', 'id'],
    ALLOW_DATA_ATTR: false
  })
}

/**
 * 清理用户输入
 */
export function sanitizeInput(input: string): string {
  return input
    .trim()
    .replace(/[<>]/g, '') // 移除尖括号
    .slice(0, 5000) // 限制长度
}

/**
 * 验证 URL 是否安全
 */
export function isSafeURL(url: string): boolean {
  try {
    const parsed = new URL(url)
    return ['http:', 'https:'].includes(parsed.protocol)
  } catch {
    return false
  }
}
```

### 输入验证

```typescript
// utils/validator.ts

/**
 * 验证消息内容
 */
export function validateMessage(content: string): boolean {
  if (!content || content.trim().length === 0) {
    return false
  }
  if (content.length > 5000) {
    return false
  }
  return true
}

/**
 * 验证会话名称
 */
export function validateSessionName(name: string): boolean {
  if (!name || name.trim().length === 0) {
    return false
  }
  if (name.length > 100) {
    return false
  }
  return true
}

/**
 * 验证数据源 ID
 */
export function validateDatasourceId(id: string): boolean {
  // Tableau LUID 格式: 32 个十六进制字符,带连字符
  const luidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
  return luidPattern.test(id)
}
```

### 敏感信息保护

```typescript
// utils/storage.ts

/**
 * 安全的本地存储封装
 */
export class SecureStorage {
  private readonly prefix = 'tableau_ai_'

  /**
   * 存储数据(不存储敏感信息)
   */
  set<T>(key: string, value: T): void {
    try {
      const serialized = JSON.stringify(value)
      localStorage.setItem(this.prefix + key, serialized)
    } catch (error) {
      logger.error('Storage set error:', error)
    }
  }

  /**
   * 获取数据
   */
  get<T>(key: string): T | null {
    try {
      const item = localStorage.getItem(this.prefix + key)
      if (!item) return null
      return JSON.parse(item) as T
    } catch (error) {
      logger.error('Storage get error:', error)
      return null
    }
  }

  /**
   * 删除数据
   */
  remove(key: string): void {
    localStorage.removeItem(this.prefix + key)
  }

  /**
   * 清空所有数据
   */
  clear(): void {
    const keys = Object.keys(localStorage)
    keys.forEach(key => {
      if (key.startsWith(this.prefix)) {
        localStorage.removeItem(key)
      }
    })
  }
}

export const storage = new SecureStorage()
```

## 部署配置

### 环境变量

```bash
# .env.development
VITE_API_BASE_URL=http://localhost:8000
VITE_APP_TITLE=Tableau AI Assistant (Dev)
VITE_LOG_LEVEL=debug
VITE_ENABLE_MOCK=true

# .env.production
VITE_API_BASE_URL=https://api.example.com
VITE_APP_TITLE=Tableau AI Assistant
VITE_LOG_LEVEL=error
VITE_ENABLE_MOCK=false
```

### Vite 配置

```typescript
// vite.config.ts

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [vue()],
    
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src')
      }
    },

    server: {
      port: 5173,
      https: {
        key: './certs/localhost-key.pem',
        cert: './certs/localhost.pem'
      },
      proxy: {
        '/api': {
          target: env.VITE_API_BASE_URL,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, '')
        }
      }
    },

    build: {
      target: 'es2015',
      outDir: 'dist',
      assetsDir: 'assets',
      sourcemap: mode === 'development',
      minify: 'terser',
      terserOptions: {
        compress: {
          drop_console: mode === 'production',
          drop_debugger: true
        }
      },
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-vue': ['vue', 'pinia'],
            'vendor-ui': ['element-plus'],
            'vendor-markdown': ['markdown-it', 'highlight.js'],
            'vendor-utils': ['axios', 'lodash-es']
          }
        }
      }
    }
  }
})
```

### Tableau Extension 清单

```xml
<!-- public/manifest.trex -->
<?xml version="1.0" encoding="utf-8"?>
<manifest manifest-version="0.1" xmlns="http://www.tableau.com/xml/extension_manifest">
  <dashboard-extension id="com.example.tableau-ai-assistant" extension-version="1.0.0">
    <default-locale>zh_CN</default-locale>
    <name resource-id="name"/>
    <description>AI-powered data analysis assistant for Tableau</description>
    <author name="Your Company" email="support@example.com" organization="Your Company" website="https://example.com"/>
    <min-api-version>1.4</min-api-version>
    <source-location>
      <url>https://your-domain.com</url>
    </source-location>
    <icon>
      iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAALEwAACxMBAJqcGAAAAVlpVFh0WE1MOmNvbS5hZG9iZS54bXAAAAAAADx4OnhtcG1ldGEgeG1sbnM6eD0iYWRvYmU6bnM6bWV0YS8iIHg6eG1wdGs9IlhNUCBDb3JlIDUuNC4wIj4KICAgPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4KICAgICAgPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIvPgogICA8L3JkZjpSREY+CjwveDp4bXBtZXRhPgo=
    </icon>
    <permissions>
      <permission>full data</permission>
    </permissions>
  </dashboard-extension>
  <resources>
    <resource id="name">
      <text locale="zh_CN">Tableau AI 助手</text>
      <text locale="en_US">Tableau AI Assistant</text>
    </resource>
  </resources>
</manifest>
```

### Nginx 配置

```nginx
# nginx.conf

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    root /var/www/tableau-ai-assistant;
    index index.html;

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/javascript application/json application/xml+rss;

    # 安全头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https://api.example.com; frame-ancestors 'self' https://*.tableau.com;" always;

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # SPA 路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 代理
    location /api/ {
        proxy_pass https://api.example.com/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

### Docker 部署

```dockerfile
# Dockerfile

FROM node:18-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
```

```yaml
# docker-compose.yml

version: '3.8'

services:
  frontend:
    build: .
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./certs:/etc/nginx/certs:ro
    environment:
      - NODE_ENV=production
    restart: unless-stopped
```

### CI/CD 流程

```yaml
# .github/workflows/deploy.yml

name: Deploy

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run tests
        run: npm test

      - name: Build
        run: npm run build
        env:
          VITE_API_BASE_URL: ${{ secrets.API_BASE_URL }}

      - name: Deploy to server
        uses: easingthemes/ssh-deploy@v2
        env:
          SSH_PRIVATE_KEY: ${{ secrets.SSH_PRIVATE_KEY }}
          REMOTE_HOST: ${{ secrets.REMOTE_HOST }}
          REMOTE_USER: ${{ secrets.REMOTE_USER }}
          TARGET: /var/www/tableau-ai-assistant
          SOURCE: dist/
```

## 总结

本设计文档描述了 Tableau AI Assistant 前端应用的完整技术架构,包括:

1. **组件设计**: 清晰的组件层次结构和接口定义
2. **数据模型**: 完整的 TypeScript 类型定义
3. **API 设计**: RESTful API 和 SSE 流式接口
4. **状态管理**: 基于 Pinia 的响应式状态管理
5. **样式设计**: Tailwind CSS 配置和主题系统
6. **性能优化**: 虚拟滚动、代码分割、缓存策略等
7. **错误处理**: 统一的错误处理机制
8. **测试策略**: 单元测试、属性测试、组件测试和端到端测试
9. **正确性属性**: 22 个可验证的正确性属性
10. **安全性设计**: XSS 防护、输入验证、CSP 配置
11. **部署配置**: 环境变量、构建配置、Nginx 配置、Docker 部署

该设计遵循现代前端开发最佳实践,确保应用的可维护性、可扩展性、性能和安全性。

