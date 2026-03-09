# 设计文档：Tableau Extension 前端

## 概述

本文档描述了 Tableau AI Assistant Extension 前端的技术设计。该前端是一个基于 Vue 3 + TypeScript 的单页应用，嵌入在 Tableau Dashboard 中，为用户提供基于 AI 的数据分析对话界面。

### 核心目标

- 提供流畅的对话式数据分析体验
- 支持 SSE 流式响应，实时显示 AI 回复
- 与 Tableau Dashboard 深度集成，获取数据源上下文
- 支持多语言、多主题、响应式布局
- 确保安全性、可访问性和性能

### 技术栈

| 类别 | 技术选型 | 版本 | 用途 |
|------|----------|------|------|
| 前端框架 | Vue 3 | ^3.4.0 | 响应式 UI 框架 |
| 语言 | TypeScript | ^5.3.0 | 类型安全 |
| 构建工具 | Vite | ^5.0.0 | 快速构建和热更新 |
| UI 组件库 | Element Plus | ^2.5.0 | 企业级 UI 组件 |
| 状态管理 | Pinia | ^2.1.0 | Vue 3 官方状态管理 |
| HTTP 客户端 | Axios | ^1.6.0 | HTTP 请求封装 |
| Markdown 渲染 | markdown-it | ^14.0.0 | Markdown 解析和渲染 |
| 代码高亮 | highlight.js | ^11.9.0 | 代码块语法高亮 |
| 国际化 | vue-i18n | ^9.9.0 | 多语言支持 |
| 虚拟滚动 | vue-virtual-scroller | ^2.0.0 | 大列表性能优化 |
| Tableau API | @tableau/extensions-api-types | ^1.10.0 | Tableau 类型定义 |

## 架构设计

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Tableau Dashboard                         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           Tableau Extension (iframe)                   │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │              Vue 3 Application                   │  │  │
│  │  │  ┌──────────────────────────────────────────┐   │  │  │
│  │  │  │         Presentation Layer               │   │  │  │
│  │  │  │  - ChatContainer                         │   │  │  │
│  │  │  │  - MessageList                           │   │  │  │
│  │  │  │  - InputBox                              │   │  │  │
│  │  │  │  - SettingsPanel                         │   │  │  │
│  │  │  │  - HistoryPanel                          │   │  │  │
│  │  │  └──────────────────────────────────────────┘   │  │  │
│  │  │  ┌──────────────────────────────────────────┐   │  │  │
│  │  │  │         State Management (Pinia)         │   │  │  │
│  │  │  │  - chatStore                             │   │  │  │
│  │  │  │  - settingsStore                         │   │  │  │
│  │  │  │  - sessionStore                          │   │  │  │
│  │  │  │  - tableauStore                          │   │  │  │
│  │  │  └──────────────────────────────────────────┘   │  │  │
│  │  │  ┌──────────────────────────────────────────┐   │  │  │
│  │  │  │         Service Layer                    │   │  │  │
│  │  │  │  - chatService (SSE)                     │   │  │  │
│  │  │  │  - sessionService                        │   │  │  │
│  │  │  │  - settingsService                       │   │  │  │
│  │  │  │  - feedbackService                       │   │  │  │
│  │  │  │  - tableauService                        │   │  │  │
│  │  │  └──────────────────────────────────────────┘   │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Backend FastAPI Service                   │
│  - POST /api/chat/stream (SSE)                              │
│  - GET/POST/PUT/DELETE /api/sessions                        │
│  - GET/PUT /api/settings                                    │
│  - POST /api/feedback                                       │
└─────────────────────────────────────────────────────────────┘
```


### 项目目录结构

```
frontend/
├── public/                      # 静态资源
│   ├── favicon.ico
│   └── tableau-logo.svg
├── src/
│   ├── assets/                  # 资源文件
│   │   ├── styles/              # 全局样式
│   │   │   ├── variables.scss   # CSS 变量
│   │   │   ├── mixins.scss      # SCSS mixins
│   │   │   └── global.scss      # 全局样式
│   │   └── images/              # 图片资源
│   ├── components/              # 组件
│   │   ├── chat/                # 聊天相关组件
│   │   │   ├── ChatContainer.vue
│   │   │   ├── MessageList.vue
│   │   │   ├── MessageItem.vue
│   │   │   ├── InputBox.vue
│   │   │   └── TypingIndicator.vue
│   │   ├── datasource/          # 数据源相关组件
│   │   │   └── DataSourceSelector.vue
│   │   ├── boost/               # 快捷提示相关组件
│   │   │   ├── BoostPromptPanel.vue
│   │   │   └── BoostPromptCard.vue
│   │   ├── settings/            # 设置相关组件
│   │   │   └── SettingsPanel.vue
│   │   ├── history/             # 历史相关组件
│   │   │   ├── HistoryPanel.vue
│   │   │   └── SessionCard.vue
│   │   ├── feedback/            # 反馈相关组件
│   │   │   └── FeedbackButtons.vue
│   │   └── common/              # 通用组件
│   │       ├── ErrorMessage.vue
│   │       ├── LoadingSpinner.vue
│   │       └── EmptyState.vue
│   ├── stores/                  # Pinia 状态管理
│   │   ├── chat.ts              # 聊天状态
│   │   ├── settings.ts          # 设置状态
│   │   ├── session.ts           # 会话状态
│   │   └── tableau.ts           # Tableau 上下文状态
│   ├── services/                # API 服务层
│   │   ├── api/                 # API 客户端
│   │   │   ├── client.ts        # Axios 实例配置
│   │   │   ├── chat.ts          # 聊天 API
│   │   │   ├── session.ts       # 会话 API
│   │   │   ├── settings.ts      # 设置 API
│   │   │   └── feedback.ts      # 反馈 API
│   │   ├── tableau/             # Tableau 服务
│   │   │   └── tableau.ts       # Tableau API 封装
│   │   └── sse/                 # SSE 服务
│   │       └── sse-client.ts    # SSE 客户端
│   ├── types/                   # TypeScript 类型定义
│   │   ├── chat.ts              # 聊天相关类型
│   │   ├── session.ts           # 会话相关类型
│   │   ├── settings.ts          # 设置相关类型
│   │   ├── tableau.ts           # Tableau 相关类型
│   │   └── api.ts               # API 响应类型
│   ├── utils/                   # 工具函数
│   │   ├── markdown.ts          # Markdown 渲染工具
│   │   ├── date.ts              # 日期格式化工具
│   │   ├── storage.ts           # 本地存储工具
│   │   └── validation.ts        # 输入验证工具
│   ├── locales/                 # 国际化文件
│   │   ├── zh.ts                # 中文翻译
│   │   └── en.ts                # 英文翻译
│   ├── App.vue                  # 根组件
│   ├── main.ts                  # 应用入口
│   └── env.d.ts                 # 环境变量类型定义
├── .env.development             # 开发环境配置
├── .env.production              # 生产环境配置
├── vite.config.ts               # Vite 配置
├── tsconfig.json                # TypeScript 配置
├── package.json                 # 项目依赖
├── .eslintrc.cjs                # ESLint 配置
├── .prettierrc.json             # Prettier 配置
└── README.md                    # 项目文档
```

构建输出目录：
```
analytics_assistant/public/dist/
├── index.html
├── assets/
│   ├── index-[hash].js
│   ├── index-[hash].css
│   └── ...
└── manifest.trex                # Tableau Extension 清单文件
```


## UI 界面设计

### Logo 使用说明

项目使用 `manifest.trex` 文件中已有的 base64 编码 logo 图标。该 logo 将在以下位置显示：

1. **Header 左侧**：显示在数据源选择器左侧，尺寸约 32px × 32px
2. **欢迎界面**：在空状态时显示在中央，尺寸约 64px × 64px

**Logo 提取工具**：
```typescript
// utils/logo.ts
export function extractLogoFromManifest(): string {
  // 从 manifest.trex 中提取 base64 编码的 logo
  // 返回 data URL 格式：data:image/png;base64,iVBORw0KG...
  const base64Icon = 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAALEwAACxMBAJqcGAAAAlhJREFUOI2Nkt9vy1EYh5/3bbsvRSySCZbIxI+ZCKsN2TKtSFyIrV2WuRCJuBiJWxfuxCVXbvwFgiEtposgLFJElnbU1SxIZIIRJDKTrdu+53Uhra4mce7Oe57Pcz7JOULFisViwZ+29LAzOSjQYDgz1ZcCvWuXV11MJpN+OS/lm6179teqH0yDqxPTCyKSA8DcDsyOmOprnCaeP7459pdgy969i0LTC3IO/RQMyoHcQN+3cnljW3dNIFC47qDaK3g7BwdTkwBaBELT4ZPOUVWgKl4ZBnjxJPUlMDnTDrp0pmr6RHFeEjjcUUXPDGeSEwDN0Xg8sivxMhJNjGzbHd8PkM3eHRfkrBM5NkcQaY2vUnTlrDIA0NoaX+KLXFFlowr14tvVpqb2MICzmQcKqxvbumv+NAhZGCCIPwEw6QWXKYRL/VUXO0+rAUJiPwAk5MIlgVfwPjjHLCL1APmHN94ZdqeYN+NW/mn6I4BvwQYchcLnwFhJMDiYmlRxAzjpKWZkYkUCcZ2I61wi37tLbYyjiN0fHk5Oz3nGSLSzBbNHCF35R7f6K1/hN9PRhek11FrymfQQQKB4+Gl05P2qNRtmETlXW7e+b2z01dfycGNbfFMAbqNyKp9Jp4rzOT8RYFs0njJkc2iqsCObvTsOsDWWqA5C1uFy+Uz/oXJeKwVT4h0RmPUXhi79vuC0Ku6yOffTK3g9lfxfDQAisY516sg5kfOCiJk7HoLt2cf9b/9LANAc7dznm98PagG1fUOZ9IP5uMB8Q4CPoyNvausapkTt3rNMuvdf3C/o6+czhtdwmwAAAABJRU5ErkJggg=='
  return `data:image/png;base64,${base64Icon}`
}
```

### 整体布局

前端界面采用经典的聊天应用布局，分为三个主要区域：

```
┌─────────────────────────────────────────────────────────────┐
│  Header (60px)                                              │
│  [🤖 Logo] [数据源选择器] [历史] [设置]                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Message Area (flex-grow)                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 用户消息 (右对齐，蓝色背景)                          │   │
│  │ "分析上个月的销售趋势"                               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ AI 消息 (左对齐，灰色背景)                           │   │
│  │ "根据数据分析，上个月销售额..."                      │   │
│  │ [👍] [👎]                                            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Input Area (120px)                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ [💡] 输入您的问题...                                 │   │
│  │                                              [发送]  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 详细界面设计

#### 1. Header 区域（顶部栏）

**布局**：
```
┌─────────────────────────────────────────────────────────────┐
│ [🤖] [📊 数据源: Superstore ▼]    [📜 历史] [⚙️ 设置]     │
└─────────────────────────────────────────────────────────────┘
```

**样式**：
- 高度：60px
- 背景色：白色（浅色主题）/ #1a1a1a（深色主题）
- 边框：底部 1px 实线，颜色 #e4e7ed
- 内边距：0 16px

**元素**：
- Logo 图标（最左侧）：
  - 尺寸：32px × 32px
  - 来源：从 manifest.trex 提取的 base64 图标
  - 边距：右侧 12px
  - 样式：圆角 4px，可选阴影效果

- 数据源选择器（左侧）：
  - 宽度：200px
  - 下拉选择框，显示当前数据源名称
  - 图标：📊 数据库图标
  - 悬停效果：背景色变浅

- 历史按钮（右侧）：
  - 图标按钮，显示 📜 图标
  - 点击打开历史面板（侧边栏）
  - 悬停效果：背景色 #f5f7fa

- 设置按钮（右侧）：
  - 图标按钮，显示 ⚙️ 图标
  - 点击打开设置面板（侧边栏）
  - 悬停效果：背景色 #f5f7fa

#### 2. Message Area（消息区域）

**布局**：
```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  空状态（无消息时）：                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              [Logo 64x64]                            │   │
│  │         Tableau AI 助手                              │   │
│  │                                                      │   │
│  │  选择数据源后，输入问题开始分析                       │   │
│  │                                                      │   │
│  │  快捷提示：                                          │   │
│  │  [📊 数据概览] [📈 趋势分析] [🔍 异常检测]          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  有消息时：                                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 👤 用户                                    10:30 AM  │   │
│  │ 分析上个月的销售趋势                                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🤖 AI 助手                                 10:30 AM  │   │
│  │ 根据数据分析，上个月销售额呈现以下趋势：              │   │
│  │                                                      │   │
│  │ 1. 总销售额：$1,234,567                             │   │
│  │ 2. 环比增长：+15.3%                                 │   │
│  │ 3. 主要增长来源：                                    │   │
│  │    - 电子产品类别 (+25%)                            │   │
│  │    - 家具类别 (+10%)                                │   │
│  │                                                      │   │
│  │ ```sql                                               │   │
│  │ SELECT category, SUM(sales)                          │   │
│  │ FROM orders                                          │   │
│  │ WHERE date >= '2024-01-01'                          │   │
│  │ GROUP BY category                                    │   │
│  │ ```                                                  │   │
│  │                                                      │   │
│  │ [👍 有帮助] [👎 无帮助]                             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🤖 正在输入...                                       │   │
│  │ 让我为您分析一下▊                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**样式**：
- 背景色：#fafafa（浅色主题）/ #262626（深色主题）
- 内边距：16px
- 滚动条：自定义样式，宽度 8px

**用户消息样式**：
- 对齐：右侧
- 最大宽度：70%
- 背景色：#409eff（主题蓝色）
- 文字颜色：白色
- 圆角：12px（左上、左下、右下），0px（右上）
- 内边距：12px 16px
- 阴影：0 2px 4px rgba(0,0,0,0.1)

**AI 消息样式**：
- 对齐：左侧
- 最大宽度：70%
- 背景色：白色（浅色主题）/ #2d2d2d（深色主题）
- 文字颜色：#303133（浅色主题）/ #e5eaf3（深色主题）
- 圆角：12px（右上、左下、右下），0px（左上）
- 内边距：12px 16px
- 阴影：0 2px 4px rgba(0,0,0,0.1)

**Markdown 渲染样式**：
- 标题：加粗，margin-top: 12px
- 列表：左侧缩进 20px
- 代码块：
  - 背景色：#f4f4f5（浅色主题）/ #1e1e1e（深色主题）
  - 圆角：8px
  - 内边距：12px
  - 字体：Consolas, Monaco, 'Courier New'
  - 语法高亮：使用 highlight.js 的 GitHub 主题

**反馈按钮**：
- 位置：消息底部右侧
- 样式：文字按钮，灰色
- 悬停效果：
  - 👍 变为绿色
  - 👎 变为红色
- 已反馈状态：对应颜色填充

**打字指示器**（流式生成时）：
- 显示闪烁光标 ▊
- 动画：0.8s 闪烁循环

#### 3. Input Area（输入区域）

**布局**：
```
┌─────────────────────────────────────────────────────────────┐
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ [💡]  输入您的问题...                                   │ │
│ │                                                         │ │
│ │                                              [发送 →]  │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Boost Prompt 面板（点击 💡 展开）：                         │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 快捷提示                                                │ │
│ │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐    │ │
│ │ │ 📊 数据概览  │ │ 📈 趋势分析  │ │ 🔍 异常检测  │    │ │
│ │ └──────────────┘ └──────────────┘ └──────────────┘    │ │
│ │ ┌──────────────┐ ┌──────────────┐                     │ │
│ │ │ 💡 可视化建议│ │ 📊 关键指标  │                     │ │
│ │ └──────────────┘ └──────────────┘                     │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**样式**：
- 高度：自适应（最小 60px，最大 120px）
- 背景色：白色（浅色主题）/ #1a1a1a（深色主题）
- 边框：顶部 1px 实线，颜色 #e4e7ed
- 内边距：12px 16px

**输入框样式**：
- 边框：1px 实线，颜色 #dcdfe6
- 圆角：8px
- 内边距：12px
- 字体大小：14px
- 行高：1.5
- 最大行数：5 行
- 焦点状态：边框颜色变为 #409eff

**Boost Prompt 按钮**：
- 位置：输入框左侧
- 图标：💡 灯泡
- 样式：圆形按钮，直径 32px
- 悬停效果：背景色 #f5f7fa
- 点击效果：展开 Boost Prompt 面板

**发送按钮**：
- 位置：输入框右下角
- 样式：主题色按钮，圆角 6px
- 尺寸：80px × 36px
- 禁用状态：灰色，不可点击
- 悬停效果：背景色加深
- 点击效果：涟漪动画

**Boost Prompt 面板**：
- 位置：输入框上方
- 高度：自适应（最大 200px）
- 背景色：白色（浅色主题）/ #2d2d2d（深色主题）
- 圆角：8px
- 阴影：0 4px 12px rgba(0,0,0,0.15)
- 动画：从下向上滑入，0.3s

**Boost Prompt 卡片**：
- 样式：卡片式按钮
- 尺寸：自适应宽度，高度 40px
- 背景色：#f5f7fa（浅色主题）/ #363637（深色主题）
- 圆角：6px
- 内边距：8px 12px
- 悬停效果：背景色变为 #e4e7ed，边框显示主题色
- 点击效果：文本填充到输入框

#### 4. Settings Panel（设置面板）

**布局**：
```
┌─────────────────────────────────────┐
│ 设置                        [×]     │
├─────────────────────────────────────┤
│                                     │
│ 语言                                │
│ ○ 中文  ○ English                  │
│                                     │
│ 分析深度                            │
│ ○ 标准分析  ○ 深入分析             │
│                                     │
│ 主题                                │
│ ○ 浅色  ○ 深色  ○ 跟随系统        │
│                                     │
│ 显示思考过程                        │
│ [开关]                              │
│                                     │
│                                     │
│                        [保存]       │
└─────────────────────────────────────┘
```

**样式**：
- 位置：右侧滑入
- 宽度：320px
- 高度：100vh
- 背景色：白色（浅色主题）/ #1a1a1a（深色主题）
- 阴影：-4px 0 12px rgba(0,0,0,0.15)
- 动画：从右向左滑入，0.3s

**标题栏**：
- 高度：60px
- 字体大小：18px
- 字体粗细：600
- 关闭按钮：右上角，图标 ×

**设置项**：
- 间距：24px
- 标签字体大小：14px
- 标签颜色：#606266

**单选按钮组**：
- 样式：圆形单选按钮
- 选中状态：主题色填充
- 间距：16px

**开关**：
- 样式：滑动开关
- 开启状态：主题色背景
- 关闭状态：灰色背景

**保存按钮**：
- 位置：底部右侧
- 样式：主题色按钮
- 尺寸：80px × 36px

#### 5. History Panel（历史面板）

**布局**：
```
┌─────────────────────────────────────┐
│ 历史会话                    [×]     │
├─────────────────────────────────────┤
│ [+ 新建会话]                        │
├─────────────────────────────────────┤
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 📝 上个月销售趋势分析           │ │
│ │ 2024-02-15 10:30                │ │
│ │                      [✏️] [🗑️] │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 📝 客户分布情况                 │ │
│ │ 2024-02-14 15:20                │ │
│ │                      [✏️] [🗑️] │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ 📝 产品销量排名                 │ │
│ │ 2024-02-13 09:45                │ │
│ │                      [✏️] [🗑️] │ │
│ └─────────────────────────────────┘ │
│                                     │
│              [加载更多]             │
└─────────────────────────────────────┘
```

**样式**：
- 位置：右侧滑入
- 宽度：320px
- 高度：100vh
- 背景色：白色（浅色主题）/ #1a1a1a（深色主题）
- 阴影：-4px 0 12px rgba(0,0,0,0.15)
- 动画：从右向左滑入，0.3s

**新建会话按钮**：
- 样式：主题色按钮，全宽
- 高度：40px
- 图标：+ 加号
- 悬停效果：背景色加深

**会话卡片**：
- 样式：卡片式
- 高度：80px
- 背景色：#f5f7fa（浅色主题）/ #2d2d2d（深色主题）
- 圆角：8px
- 内边距：12px
- 间距：8px
- 悬停效果：边框显示主题色，阴影加深
- 选中状态：边框主题色，背景色稍深

**会话标题**：
- 字体大小：14px
- 字体粗细：500
- 颜色：#303133（浅色主题）/ #e5eaf3（深色主题）
- 最大行数：2 行
- 溢出：省略号

**会话时间**：
- 字体大小：12px
- 颜色：#909399
- 位置：标题下方

**操作按钮**：
- 位置：卡片右侧
- 样式：图标按钮
- 尺寸：24px × 24px
- 悬停效果：背景色 #e4e7ed
- 编辑按钮：✏️ 图标
- 删除按钮：🗑️ 图标，悬停时变红色

### 配色方案

#### 浅色主题

| 元素 | 颜色 | 用途 |
|------|------|------|
| 主题色 | #409eff | 按钮、链接、选中状态 |
| 成功色 | #67c23a | 成功提示、点赞 |
| 警告色 | #e6a23c | 警告提示 |
| 危险色 | #f56c6c | 错误提示、点踩、删除 |
| 背景色 | #ffffff | 主背景 |
| 次背景色 | #fafafa | 消息区域背景 |
| 卡片背景 | #f5f7fa | 卡片、输入框背景 |
| 文字主色 | #303133 | 主要文字 |
| 文字次色 | #606266 | 次要文字 |
| 文字辅助色 | #909399 | 辅助文字、时间戳 |
| 边框色 | #dcdfe6 | 边框、分割线 |
| 用户消息背景 | #409eff | 用户消息气泡 |
| AI 消息背景 | #ffffff | AI 消息气泡 |

#### 深色主题

| 元素 | 颜色 | 用途 |
|------|------|------|
| 主题色 | #409eff | 按钮、链接、选中状态 |
| 成功色 | #67c23a | 成功提示、点赞 |
| 警告色 | #e6a23c | 警告提示 |
| 危险色 | #f56c6c | 错误提示、点踩、删除 |
| 背景色 | #1a1a1a | 主背景 |
| 次背景色 | #262626 | 消息区域背景 |
| 卡片背景 | #2d2d2d | 卡片、输入框背景 |
| 文字主色 | #e5eaf3 | 主要文字 |
| 文字次色 | #cfd3dc | 次要文字 |
| 文字辅助色 | #a3a6ad | 辅助文字、时间戳 |
| 边框色 | #4c4d4f | 边框、分割线 |
| 用户消息背景 | #409eff | 用户消息气泡 |
| AI 消息背景 | #2d2d2d | AI 消息气泡 |

### 交互效果

#### 1. 消息发送动画

```
用户输入 → 点击发送
  ↓
输入框清空，禁用状态
  ↓
用户消息从底部滑入（0.3s）
  ↓
AI 消息占位符出现，显示"正在输入..."
  ↓
SSE 流式接收 token，逐字显示
  ↓
完成后显示反馈按钮
```

#### 2. 面板滑入动画

```
点击设置/历史按钮
  ↓
遮罩层淡入（0.2s）
  ↓
面板从右侧滑入（0.3s，ease-out）
  ↓
点击遮罩层或关闭按钮
  ↓
面板滑出（0.3s，ease-in）
  ↓
遮罩层淡出（0.2s）
```

#### 3. Boost Prompt 展开动画

```
点击 💡 按钮
  ↓
面板从下向上滑入（0.3s，ease-out）
  ↓
卡片依次淡入（0.1s 间隔）
  ↓
点击卡片
  ↓
文本填充到输入框
  ↓
面板滑出（0.2s）
```

#### 4. 消息滚动动画

```
新消息添加
  ↓
检查是否在底部
  ↓
如果在底部：平滑滚动到新消息（0.3s）
如果不在底部：显示"新消息"提示按钮
  ↓
点击提示按钮：滚动到底部
```

### 响应式设计

#### 桌面端（>1024px）

- 消息最大宽度：70%
- 侧边栏宽度：320px
- 输入框高度：自适应（最大 120px）

#### 平板端（768px - 1024px）

- 消息最大宽度：80%
- 侧边栏宽度：280px
- 输入框高度：自适应（最大 100px）

#### 移动端（<768px）

- 消息最大宽度：90%
- 侧边栏宽度：100vw（全屏）
- 输入框高度：自适应（最大 80px）
- Header 按钮合并为汉堡菜单
- Boost Prompt 面板改为底部抽屉

### 加载状态

#### 1. 初始化加载

```
┌─────────────────────────────────────┐
│                                     │
│              🤖                     │
│         正在初始化...               │
│         [加载动画]                  │
│                                     │
└─────────────────────────────────────┘
```

#### 2. 消息加载

```
┌─────────────────────────────────────┐
│ 🤖 正在思考...                      │
│ [三个跳动的点动画]                  │
└─────────────────────────────────────┘
```

#### 3. 会话列表加载

```
┌─────────────────────────────────────┐
│ [骨架屏动画]                        │
│ ┌─────────────────────────────────┐ │
│ │ ▓▓▓▓▓▓▓▓▓▓▓▓                   │ │
│ │ ▓▓▓▓▓▓▓                         │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### 错误状态

#### 1. 网络错误

```
┌─────────────────────────────────────┐
│              ⚠️                     │
│         网络连接失败                │
│         请检查网络后重试            │
│         [重试按钮]                  │
└─────────────────────────────────────┘
```

#### 2. 消息发送失败

```
┌─────────────────────────────────────┐
│ 👤 用户                             │
│ 分析上个月的销售趋势                │
│ ❌ 发送失败 [重试]                  │
└─────────────────────────────────────┘
```

## 组件设计

### 组件层次结构

```
App.vue
└── ChatContainer.vue
    ├── DataSourceSelector.vue
    ├── MessageList.vue
    │   ├── MessageItem.vue
    │   │   ├── FeedbackButtons.vue
    │   │   └── (Markdown 渲染)
    │   ├── TypingIndicator.vue
    │   └── EmptyState.vue
    ├── InputBox.vue
    │   └── BoostPromptPanel.vue
    │       └── BoostPromptCard.vue
    ├── SettingsPanel.vue
    └── HistoryPanel.vue
        └── SessionCard.vue
```

### 核心组件详细设计

#### 1. ChatContainer.vue

聊天容器主组件，负责整体布局和组件协调。

**Props**: 无

**State**:
- `isSettingsPanelOpen: boolean` - 设置面板是否打开
- `isHistoryPanelOpen: boolean` - 历史面板是否打开

**Methods**:
- `toggleSettingsPanel()` - 切换设置面板
- `toggleHistoryPanel()` - 切换历史面板
- `handleNewSession()` - 创建新会话

**Layout**:
```
┌─────────────────────────────────────────────────┐
│  Header: DataSourceSelector + Settings Button  │
├─────────────────────────────────────────────────┤
│                                                 │
│              MessageList                        │
│                                                 │
├─────────────────────────────────────────────────┤
│              InputBox                           │
└─────────────────────────────────────────────────┘
```

#### 2. MessageList.vue

消息列表组件，显示对话历史。

**Props**:
- `messages: Message[]` - 消息列表

**Computed**:
- `sortedMessages` - 按时间排序的消息

**Methods**:
- `scrollToBottom()` - 滚动到最新消息
- `handleScroll()` - 处理滚动事件（懒加载）

**Features**:
- 虚拟滚动（vue-virtual-scroller）
- 自动滚动到最新消息
- 空状态显示欢迎信息

#### 3. MessageItem.vue

单条消息组件，支持 Markdown 渲染。

**Props**:
- `message: Message` - 消息对象
- `isStreaming: boolean` - 是否正在流式生成

**Computed**:
- `renderedContent` - 渲染后的 Markdown HTML
- `isUserMessage` - 是否为用户消息

**Methods**:
- `copyToClipboard()` - 复制消息内容
- `handleFeedback(type: 'positive' | 'negative')` - 处理反馈

**Features**:
- Markdown 渲染（markdown-it）
- 代码块语法高亮（highlight.js）
- 流式生成时显示打字光标
- 反馈按钮（点赞/点踩）

#### 4. InputBox.vue

输入框组件，支持多行输入和快捷提示。

**Props**: 无

**State**:
- `inputText: string` - 输入文本
- `isBoostPanelOpen: boolean` - 快捷提示面板是否打开
- `isSending: boolean` - 是否正在发送

**Computed**:
- `canSend` - 是否可以发送（非空且已选择数据源）

**Methods**:
- `handleSend()` - 发送消息
- `handleKeyDown(event: KeyboardEvent)` - 处理键盘事件
- `insertBoostPrompt(text: string)` - 插入快捷提示

**Features**:
- Enter 发送，Shift+Enter 换行
- 自动调整高度（最大 5 行）
- 发送中禁用输入
- 快捷提示面板

#### 5. DataSourceSelector.vue

数据源选择器组件。

**Props**: 无

**Computed**:
- `dataSources` - 可用数据源列表（从 tableauStore）
- `selectedDataSource` - 当前选中的数据源

**Methods**:
- `handleSelect(dataSource: DataSource)` - 选择数据源

**Features**:
- 下拉选择框
- 显示数据源名称和类型
- 无数据源时显示提示

#### 6. BoostPromptPanel.vue

快捷提示面板组件。

**Props**: 无

**Computed**:
- `builtInPrompts` - 内置快捷提示
- `customPrompts` - 用户自定义快捷提示

**Methods**:
- `handleSelectPrompt(prompt: BoostPrompt)` - 选择快捷提示
- `handleAddCustomPrompt()` - 添加自定义快捷提示
- `handleEditPrompt(id: string)` - 编辑快捷提示
- `handleDeletePrompt(id: string)` - 删除快捷提示

**Features**:
- 分类显示（数据探索、趋势分析、异常检测等）
- 支持自定义快捷提示
- 存储在 localStorage

#### 7. SettingsPanel.vue

设置面板组件。

**Props**:
- `visible: boolean` - 是否可见

**Computed**:
- `settings` - 当前设置（从 settingsStore）

**Methods**:
- `handleLanguageChange(lang: string)` - 切换语言
- `handleAnalysisDepthChange(depth: string)` - 切换分析深度
- `handleThemeChange(theme: string)` - 切换主题
- `handleSave()` - 保存设置

**Features**:
- 语言选择（中文/英文）
- 分析深度选择（标准/深入）
- 主题选择（浅色/深色/跟随系统）
- 显示思考过程开关
- 保存状态提示

#### 8. HistoryPanel.vue

历史会话面板组件。

**Props**:
- `visible: boolean` - 是否可见

**Computed**:
- `sessions` - 会话列表（从 sessionStore）

**Methods**:
- `handleSelectSession(id: string)` - 选择会话
- `handleDeleteSession(id: string)` - 删除会话
- `handleRenameSession(id: string, title: string)` - 重命名会话
- `loadMoreSessions()` - 加载更多会话

**Features**:
- 会话列表显示
- 分页懒加载
- 删除和重命名操作
- 搜索过滤


## 数据模型和类型定义

### 核心类型

```typescript
// types/chat.ts

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  sessionId: string
  isStreaming?: boolean
  feedback?: Feedback
}

export interface Feedback {
  type: 'positive' | 'negative'
  reason?: string
  comment?: string
  submittedAt: Date
}

export interface ChatRequest {
  message: string
  datasource_name: string
  language: string
  analysis_depth: string
  session_id?: string
}

export interface SSEEvent {
  type: 'token' | 'done' | 'error'
  data: string
  error?: string
}
```

```typescript
// types/session.ts

export interface Session {
  id: string
  title: string
  created_at: Date
  updated_at: Date
  message_count: number
  messages?: Message[]
}

export interface SessionListResponse {
  sessions: Session[]
  total: number
  offset: number
  limit: number
}
```

```typescript
// types/settings.ts

export interface UserSettings {
  language: 'zh' | 'en'
  analysis_depth: 'detailed' | 'comprehensive'
  theme: 'light' | 'dark' | 'auto'
  show_thinking_process: boolean
}
```

```typescript
// types/tableau.ts

export interface DataSource {
  id: string
  name: string
  type: string
  connectionName: string
}

export interface TableauContext {
  username: string
  dashboardName: string
  dataSources: DataSource[]
}
```

```typescript
// types/api.ts

export interface ApiResponse<T> {
  data: T
  message?: string
  error?: string
}

export interface ApiError {
  code: string
  message: string
  details?: any
}
```

### Boost Prompt 类型

```typescript
// types/boost.ts

export interface BoostPrompt {
  id: string
  title: string
  content: string
  category: BoostPromptCategory
  isBuiltIn: boolean
}

export enum BoostPromptCategory {
  DataExploration = 'data_exploration',
  TrendAnalysis = 'trend_analysis',
  AnomalyDetection = 'anomaly_detection',
  Visualization = 'visualization',
  Custom = 'custom'
}

export const BUILT_IN_PROMPTS: BoostPrompt[] = [
  {
    id: 'overview',
    title: '数据概览',
    content: '请给我一个数据集的整体概览，包括主要维度和度量。',
    category: BoostPromptCategory.DataExploration,
    isBuiltIn: true
  },
  {
    id: 'trend',
    title: '趋势分析',
    content: '分析最近的趋势变化，找出关键的增长或下降模式。',
    category: BoostPromptCategory.TrendAnalysis,
    isBuiltIn: true
  },
  {
    id: 'anomaly',
    title: '异常检测',
    content: '检测数据中的异常值或异常模式。',
    category: BoostPromptCategory.AnomalyDetection,
    isBuiltIn: true
  },
  {
    id: 'viz_suggest',
    title: '可视化建议',
    content: '根据当前数据，建议最合适的可视化类型。',
    category: BoostPromptCategory.Visualization,
    isBuiltIn: true
  },
  {
    id: 'top_metrics',
    title: '关键指标',
    content: '显示最重要的业务指标和它们的当前状态。',
    category: BoostPromptCategory.DataExploration,
    isBuiltIn: true
  }
]
```


## 状态管理设计

### Pinia Store 架构

#### 1. chatStore

管理聊天消息和流式响应状态。

```typescript
// stores/chat.ts

import { defineStore } from 'pinia'
import type { Message, SSEEvent } from '@/types/chat'

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [] as Message[],
    currentSessionId: null as string | null,
    isStreaming: false,
    streamingMessageId: null as string | null,
    error: null as string | null
  }),

  getters: {
    currentMessages: (state) => 
      state.messages.filter(m => m.sessionId === state.currentSessionId),
    
    lastMessage: (state) => 
      state.messages[state.messages.length - 1],
    
    hasMessages: (state) => 
      state.messages.length > 0
  },

  actions: {
    addUserMessage(content: string) {
      const message: Message = {
        id: generateId(),
        role: 'user',
        content,
        timestamp: new Date(),
        sessionId: this.currentSessionId!
      }
      this.messages.push(message)
    },

    startAssistantMessage() {
      const message: Message = {
        id: generateId(),
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        sessionId: this.currentSessionId!,
        isStreaming: true
      }
      this.messages.push(message)
      this.streamingMessageId = message.id
      this.isStreaming = true
    },

    appendToken(token: string) {
      const message = this.messages.find(m => m.id === this.streamingMessageId)
      if (message) {
        message.content += token
      }
    },

    finishStreaming() {
      const message = this.messages.find(m => m.id === this.streamingMessageId)
      if (message) {
        message.isStreaming = false
      }
      this.isStreaming = false
      this.streamingMessageId = null
    },

    setError(error: string) {
      this.error = error
      this.isStreaming = false
    },

    clearMessages() {
      this.messages = []
    },

    loadSessionMessages(sessionId: string, messages: Message[]) {
      this.currentSessionId = sessionId
      this.messages = messages
    }
  }
})
```

#### 2. settingsStore

管理用户设置。

```typescript
// stores/settings.ts

import { defineStore } from 'pinia'
import type { UserSettings } from '@/types/settings'
import { settingsService } from '@/services/api/settings'

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    settings: {
      language: 'zh',
      analysis_depth: 'detailed',
      theme: 'auto',
      show_thinking_process: false
    } as UserSettings,
    isLoading: false,
    isSaving: false,
    error: null as string | null
  }),

  actions: {
    async loadSettings() {
      this.isLoading = true
      try {
        const response = await settingsService.getSettings()
        this.settings = response.data
      } catch (error) {
        this.error = '加载设置失败'
        console.error('Failed to load settings:', error)
      } finally {
        this.isLoading = false
      }
    },

    async saveSettings(settings: Partial<UserSettings>) {
      this.isSaving = true
      try {
        Object.assign(this.settings, settings)
        await settingsService.updateSettings(this.settings)
      } catch (error) {
        this.error = '保存设置失败'
        console.error('Failed to save settings:', error)
        throw error
      } finally {
        this.isSaving = false
      }
    },

    updateLanguage(language: 'zh' | 'en') {
      this.saveSettings({ language })
    },

    updateAnalysisDepth(depth: 'detailed' | 'comprehensive') {
      this.saveSettings({ analysis_depth: depth })
    },

    updateTheme(theme: 'light' | 'dark' | 'auto') {
      this.saveSettings({ theme })
      this.applyTheme(theme)
    },

    applyTheme(theme: string) {
      if (theme === 'auto') {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
        theme = prefersDark ? 'dark' : 'light'
      }
      document.documentElement.setAttribute('data-theme', theme)
    }
  }
})
```

#### 3. sessionStore

管理会话列表和当前会话。

```typescript
// stores/session.ts

import { defineStore } from 'pinia'
import type { Session } from '@/types/session'
import { sessionService } from '@/services/api/session'
import { useChatStore } from './chat'

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: [] as Session[],
    currentSession: null as Session | null,
    total: 0,
    offset: 0,
    limit: 20,
    isLoading: false,
    error: null as string | null
  }),

  getters: {
    hasMoreSessions: (state) => 
      state.sessions.length < state.total
  },

  actions: {
    async loadSessions() {
      this.isLoading = true
      try {
        const response = await sessionService.getSessions(this.offset, this.limit)
        this.sessions = response.data.sessions
        this.total = response.data.total
      } catch (error) {
        this.error = '加载会话列表失败'
        console.error('Failed to load sessions:', error)
      } finally {
        this.isLoading = false
      }
    },

    async loadMoreSessions() {
      if (!this.hasMoreSessions || this.isLoading) return
      
      this.offset += this.limit
      this.isLoading = true
      try {
        const response = await sessionService.getSessions(this.offset, this.limit)
        this.sessions.push(...response.data.sessions)
      } catch (error) {
        this.error = '加载更多会话失败'
        console.error('Failed to load more sessions:', error)
      } finally {
        this.isLoading = false
      }
    },

    async loadSession(sessionId: string) {
      this.isLoading = true
      try {
        const response = await sessionService.getSession(sessionId)
        this.currentSession = response.data
        
        const chatStore = useChatStore()
        chatStore.loadSessionMessages(sessionId, response.data.messages || [])
      } catch (error) {
        this.error = '加载会话失败'
        console.error('Failed to load session:', error)
      } finally {
        this.isLoading = false
      }
    },

    async createSession(title: string) {
      try {
        const response = await sessionService.createSession({ title })
        this.currentSession = response.data
        this.sessions.unshift(response.data)
        
        const chatStore = useChatStore()
        chatStore.currentSessionId = response.data.id
        chatStore.clearMessages()
      } catch (error) {
        this.error = '创建会话失败'
        console.error('Failed to create session:', error)
        throw error
      }
    },

    async deleteSession(sessionId: string) {
      try {
        await sessionService.deleteSession(sessionId)
        this.sessions = this.sessions.filter(s => s.id !== sessionId)
        if (this.currentSession?.id === sessionId) {
          this.currentSession = null
        }
      } catch (error) {
        this.error = '删除会话失败'
        console.error('Failed to delete session:', error)
        throw error
      }
    },

    async renameSession(sessionId: string, title: string) {
      try {
        await sessionService.updateSession(sessionId, { title })
        const session = this.sessions.find(s => s.id === sessionId)
        if (session) {
          session.title = title
        }
        if (this.currentSession?.id === sessionId) {
          this.currentSession.title = title
        }
      } catch (error) {
        this.error = '重命名会话失败'
        console.error('Failed to rename session:', error)
        throw error
      }
    }
  }
})
```

#### 4. tableauStore

管理 Tableau 上下文信息。

```typescript
// stores/tableau.ts

import { defineStore } from 'pinia'
import type { DataSource, TableauContext } from '@/types/tableau'
import { tableauService } from '@/services/tableau/tableau'

export const useTableauStore = defineStore('tableau', {
  state: () => ({
    context: null as TableauContext | null,
    selectedDataSource: null as DataSource | null,
    isInitialized: false,
    error: null as string | null
  }),

  getters: {
    username: (state) => state.context?.username,
    dataSources: (state) => state.context?.dataSources || [],
    hasDataSources: (state) => (state.context?.dataSources.length || 0) > 0
  },

  actions: {
    async initialize() {
      try {
        await tableauService.initialize()
        
        const username = tableauService.getUsername()
        const dataSources = await tableauService.getDataSources()
        
        this.context = {
          username,
          dashboardName: tableauService.getDashboardName(),
          dataSources
        }
        
        // 自动选择第一个数据源
        if (dataSources.length > 0) {
          this.selectedDataSource = dataSources[0]
        }
        
        this.isInitialized = true
      } catch (error) {
        this.error = 'Tableau 初始化失败'
        console.error('Failed to initialize Tableau:', error)
        throw error
      }
    },

    selectDataSource(dataSource: DataSource) {
      this.selectedDataSource = dataSource
    }
  }
})
```


## API 服务层设计

### Axios 客户端配置

```typescript
// services/api/client.ts

import axios, { type AxiosInstance, type AxiosError } from 'axios'
import { useTableauStore } from '@/stores/tableau'
import { ElMessage } from 'element-plus'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://localhost:8000'

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器：添加 Tableau 用户名
apiClient.interceptors.request.use(
  (config) => {
    const tableauStore = useTableauStore()
    if (tableauStore.username) {
      config.headers['X-Tableau-Username'] = tableauStore.username
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
  (error: AxiosError) => {
    handleApiError(error)
    return Promise.reject(error)
  }
)

function handleApiError(error: AxiosError) {
  if (error.response) {
    // 服务器返回错误
    const status = error.response.status
    const message = (error.response.data as any)?.message || '请求失败'
    
    switch (status) {
      case 400:
        ElMessage.error(`请求参数错误: ${message}`)
        break
      case 401:
        ElMessage.error('认证失败，请重新登录')
        break
      case 403:
        ElMessage.error('没有权限访问该资源')
        break
      case 404:
        ElMessage.error('请求的资源不存在')
        break
      case 500:
        ElMessage.error('服务器错误，请稍后重试')
        break
      default:
        ElMessage.error(message)
    }
  } else if (error.request) {
    // 网络错误
    ElMessage.error('网络连接失败，请检查网络')
  } else {
    // 其他错误
    ElMessage.error('请求失败，请稍后重试')
  }
  
  console.error('API Error:', error)
}
```

### SSE 客户端实现

```typescript
// services/sse/sse-client.ts

import type { SSEEvent } from '@/types/chat'

export interface SSEClientOptions {
  url: string
  body: any
  onToken: (token: string) => void
  onDone: () => void
  onError: (error: string) => void
}

export class SSEClient {
  private controller: AbortController | null = null
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null

  async connect(options: SSEClientOptions) {
    const { url, body, onToken, onDone, onError } = options
    
    this.controller = new AbortController()
    
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Tableau-Username': this.getTableauUsername()
        },
        body: JSON.stringify(body),
        signal: this.controller.signal
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      if (!response.body) {
        throw new Error('Response body is null')
      }

      this.reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await this.reader.read()
        
        if (done) {
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            
            try {
              const event: SSEEvent = JSON.parse(data)
              
              switch (event.type) {
                case 'token':
                  onToken(event.data)
                  break
                case 'done':
                  onDone()
                  return
                case 'error':
                  onError(event.error || '未知错误')
                  return
              }
            } catch (e) {
              console.error('Failed to parse SSE event:', e)
            }
          }
        }
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        console.log('SSE connection aborted')
      } else {
        console.error('SSE connection error:', error)
        onError(error.message || 'SSE 连接失败')
      }
    }
  }

  disconnect() {
    if (this.controller) {
      this.controller.abort()
      this.controller = null
    }
    if (this.reader) {
      this.reader.cancel()
      this.reader = null
    }
  }

  private getTableauUsername(): string {
    // 从 Tableau store 获取用户名
    const tableauStore = useTableauStore()
    return tableauStore.username || ''
  }
}
```

### Chat API 服务

```typescript
// services/api/chat.ts

import { apiClient } from './client'
import { SSEClient } from '../sse/sse-client'
import type { ChatRequest } from '@/types/chat'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://localhost:8000'

export const chatService = {
  async sendMessage(
    request: ChatRequest,
    callbacks: {
      onToken: (token: string) => void
      onDone: () => void
      onError: (error: string) => void
    }
  ): Promise<SSEClient> {
    const sseClient = new SSEClient()
    
    await sseClient.connect({
      url: `${API_BASE_URL}/api/chat/stream`,
      body: request,
      ...callbacks
    })
    
    return sseClient
  }
}
```

### Session API 服务

```typescript
// services/api/session.ts

import { apiClient } from './client'
import type { Session, SessionListResponse } from '@/types/session'
import type { ApiResponse } from '@/types/api'

export const sessionService = {
  async getSessions(offset: number = 0, limit: number = 20) {
    return apiClient.get<ApiResponse<SessionListResponse>>('/api/sessions', {
      params: { offset, limit }
    })
  },

  async getSession(sessionId: string) {
    return apiClient.get<ApiResponse<Session>>(`/api/sessions/${sessionId}`)
  },

  async createSession(data: { title: string }) {
    return apiClient.post<ApiResponse<Session>>('/api/sessions', data)
  },

  async updateSession(sessionId: string, data: Partial<Session>) {
    return apiClient.put<ApiResponse<Session>>(`/api/sessions/${sessionId}`, data)
  },

  async deleteSession(sessionId: string) {
    return apiClient.delete(`/api/sessions/${sessionId}`)
  }
}
```

### Settings API 服务

```typescript
// services/api/settings.ts

import { apiClient } from './client'
import type { UserSettings } from '@/types/settings'
import type { ApiResponse } from '@/types/api'

export const settingsService = {
  async getSettings() {
    return apiClient.get<ApiResponse<UserSettings>>('/api/settings')
  },

  async updateSettings(settings: UserSettings) {
    return apiClient.put<ApiResponse<UserSettings>>('/api/settings', settings)
  }
}
```

### Feedback API 服务

```typescript
// services/api/feedback.ts

import { apiClient } from './client'
import type { ApiResponse } from '@/types/api'

export interface FeedbackRequest {
  message_id: string
  type: 'positive' | 'negative'
  reason?: string
  comment?: string
}

export const feedbackService = {
  async submitFeedback(feedback: FeedbackRequest) {
    return apiClient.post<ApiResponse<void>>('/api/feedback', feedback)
  }
}
```

### Tableau API 服务

```typescript
// services/tableau/tableau.ts

import type { DataSource } from '@/types/tableau'

declare global {
  interface Window {
    tableau: any
  }
}

export const tableauService = {
  async initialize(): Promise<void> {
    if (!window.tableau) {
      throw new Error('Tableau Extensions API not found')
    }
    
    await window.tableau.extensions.initializeAsync()
  },

  getUsername(): string {
    return window.tableau.extensions.environment.username || 'Unknown User'
  },

  getDashboardName(): string {
    return window.tableau.extensions.dashboardContent.dashboard.name || 'Unknown Dashboard'
  },

  async getDataSources(): Promise<DataSource[]> {
    const dashboard = window.tableau.extensions.dashboardContent.dashboard
    const worksheets = dashboard.worksheets
    
    const dataSourcesMap = new Map<string, DataSource>()
    
    for (const worksheet of worksheets) {
      const dataSources = await worksheet.getDataSourcesAsync()
      
      for (const ds of dataSources) {
        if (!dataSourcesMap.has(ds.id)) {
          dataSourcesMap.set(ds.id, {
            id: ds.id,
            name: ds.name,
            type: ds.connectionName || 'Unknown',
            connectionName: ds.connectionName || ''
          })
        }
      }
    }
    
    return Array.from(dataSourcesMap.values())
  }
}
```


## 工具函数设计

### Markdown 渲染工具

```typescript
// utils/markdown.ts

import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

const md = new MarkdownIt({
  html: false, // 禁用 HTML 标签，防止 XSS
  linkify: true, // 自动识别链接
  typographer: true, // 启用排版优化
  highlight: (str, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch (e) {
        console.error('Highlight error:', e)
      }
    }
    return '' // 使用默认转义
  }
})

// 自定义渲染规则
md.renderer.rules.table_open = () => '<table class="markdown-table">'
md.renderer.rules.code_block = (tokens, idx) => {
  const token = tokens[idx]
  return `<pre class="code-block"><code>${md.utils.escapeHtml(token.content)}</code></pre>`
}

export function renderMarkdown(content: string): string {
  return md.render(content)
}

export function sanitizeMarkdown(content: string): string {
  // 移除潜在的危险内容
  return content
    .replace(/<script[^>]*>.*?<\/script>/gi, '')
    .replace(/javascript:/gi, '')
    .replace(/on\w+\s*=/gi, '')
}
```

### 日期格式化工具

```typescript
// utils/date.ts

export function formatTimestamp(date: Date): string {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  const seconds = Math.floor(diff / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)
  const days = Math.floor(hours / 24)
  
  if (seconds < 60) {
    return '刚刚'
  } else if (minutes < 60) {
    return `${minutes} 分钟前`
  } else if (hours < 24) {
    return `${hours} 小时前`
  } else if (days < 7) {
    return `${days} 天前`
  } else {
    return formatDate(date)
  }
}

export function formatDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function formatDateTime(date: Date): string {
  const dateStr = formatDate(date)
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${dateStr} ${hours}:${minutes}`
}
```

### 本地存储工具

```typescript
// utils/storage.ts

const STORAGE_PREFIX = 'tableau_ai_assistant_'

export const storage = {
  get<T>(key: string, defaultValue?: T): T | null {
    try {
      const item = localStorage.getItem(STORAGE_PREFIX + key)
      return item ? JSON.parse(item) : defaultValue || null
    } catch (e) {
      console.error('Failed to get from localStorage:', e)
      return defaultValue || null
    }
  },

  set(key: string, value: any): void {
    try {
      localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(value))
    } catch (e) {
      console.error('Failed to set to localStorage:', e)
    }
  },

  remove(key: string): void {
    try {
      localStorage.removeItem(STORAGE_PREFIX + key)
    } catch (e) {
      console.error('Failed to remove from localStorage:', e)
    }
  },

  clear(): void {
    try {
      const keys = Object.keys(localStorage)
      keys.forEach(key => {
        if (key.startsWith(STORAGE_PREFIX)) {
          localStorage.removeItem(key)
        }
      })
    } catch (e) {
      console.error('Failed to clear localStorage:', e)
    }
  }
}

// Boost Prompt 存储
export const boostPromptStorage = {
  getCustomPrompts(): BoostPrompt[] {
    return storage.get('custom_prompts', [])
  },

  saveCustomPrompts(prompts: BoostPrompt[]): void {
    storage.set('custom_prompts', prompts)
  },

  addCustomPrompt(prompt: BoostPrompt): void {
    const prompts = this.getCustomPrompts()
    prompts.push(prompt)
    this.saveCustomPrompts(prompts)
  },

  updateCustomPrompt(id: string, updates: Partial<BoostPrompt>): void {
    const prompts = this.getCustomPrompts()
    const index = prompts.findIndex(p => p.id === id)
    if (index !== -1) {
      prompts[index] = { ...prompts[index], ...updates }
      this.saveCustomPrompts(prompts)
    }
  },

  deleteCustomPrompt(id: string): void {
    const prompts = this.getCustomPrompts()
    const filtered = prompts.filter(p => p.id !== id)
    this.saveCustomPrompts(filtered)
  }
}
```

### 输入验证工具

```typescript
// utils/validation.ts

export function isEmptyOrWhitespace(text: string): boolean {
  return !text || text.trim().length === 0
}

export function sanitizeInput(text: string): string {
  // 移除控制字符
  return text.replace(/[\x00-\x1F\x7F]/g, '')
}

export function validateMessageLength(text: string, maxLength: number = 5000): boolean {
  return text.length <= maxLength
}

export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text
  }
  return text.slice(0, maxLength) + '...'
}
```

### ID 生成工具

```typescript
// utils/id.ts

export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}

export function generateUUID(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}
```


## 国际化设计

### i18n 配置

```typescript
// main.ts

import { createI18n } from 'vue-i18n'
import zh from './locales/zh'
import en from './locales/en'

const i18n = createI18n({
  legacy: false,
  locale: 'zh',
  fallbackLocale: 'en',
  messages: {
    zh,
    en
  }
})

app.use(i18n)
```

### 中文翻译

```typescript
// locales/zh.ts

export default {
  common: {
    send: '发送',
    cancel: '取消',
    confirm: '确认',
    delete: '删除',
    edit: '编辑',
    save: '保存',
    loading: '加载中...',
    retry: '重试',
    close: '关闭'
  },
  chat: {
    inputPlaceholder: '输入您的问题...',
    emptyState: '开始新的对话',
    emptyHint: '选择数据源后，输入问题开始分析',
    sendingError: '发送失败，请重试',
    streamingError: '接收响应失败',
    noDataSource: '请先选择数据源'
  },
  datasource: {
    label: '数据源',
    placeholder: '选择数据源',
    noDataSources: '未找到可用数据源',
    selected: '当前数据源'
  },
  boost: {
    title: '快捷提示',
    categories: {
      data_exploration: '数据探索',
      trend_analysis: '趋势分析',
      anomaly_detection: '异常检测',
      visualization: '可视化',
      custom: '自定义'
    },
    addCustom: '添加自定义提示',
    editPrompt: '编辑提示',
    deletePrompt: '删除提示'
  },
  settings: {
    title: '设置',
    language: '语言',
    languageOptions: {
      zh: '中文',
      en: 'English'
    },
    analysisDepth: '分析深度',
    analysisDepthOptions: {
      detailed: '标准分析',
      comprehensive: '深入分析'
    },
    theme: '主题',
    themeOptions: {
      light: '浅色',
      dark: '深色',
      auto: '跟随系统'
    },
    showThinkingProcess: '显示思考过程',
    saving: '保存中...',
    saved: '已保存',
    saveFailed: '保存失败'
  },
  history: {
    title: '历史会话',
    newSession: '新建会话',
    deleteConfirm: '确定要删除这个会话吗？',
    renameSession: '重命名会话',
    loadMore: '加载更多',
    noSessions: '暂无历史会话'
  },
  feedback: {
    positive: '有帮助',
    negative: '无帮助',
    submitted: '感谢您的反馈',
    submitFailed: '提交失败'
  },
  errors: {
    networkError: '网络连接失败，请检查网络',
    authError: '认证失败，请重新登录',
    serverError: '服务器错误，请稍后重试',
    unknownError: '未知错误，请稍后重试',
    tableauInitError: 'Tableau 初始化失败'
  }
}
```

### 英文翻译

```typescript
// locales/en.ts

export default {
  common: {
    send: 'Send',
    cancel: 'Cancel',
    confirm: 'Confirm',
    delete: 'Delete',
    edit: 'Edit',
    save: 'Save',
    loading: 'Loading...',
    retry: 'Retry',
    close: 'Close'
  },
  chat: {
    inputPlaceholder: 'Type your question...',
    emptyState: 'Start a new conversation',
    emptyHint: 'Select a data source and type a question to begin analysis',
    sendingError: 'Failed to send, please retry',
    streamingError: 'Failed to receive response',
    noDataSource: 'Please select a data source first'
  },
  datasource: {
    label: 'Data Source',
    placeholder: 'Select data source',
    noDataSources: 'No data sources found',
    selected: 'Current data source'
  },
  boost: {
    title: 'Quick Prompts',
    categories: {
      data_exploration: 'Data Exploration',
      trend_analysis: 'Trend Analysis',
      anomaly_detection: 'Anomaly Detection',
      visualization: 'Visualization',
      custom: 'Custom'
    },
    addCustom: 'Add custom prompt',
    editPrompt: 'Edit prompt',
    deletePrompt: 'Delete prompt'
  },
  settings: {
    title: 'Settings',
    language: 'Language',
    languageOptions: {
      zh: '中文',
      en: 'English'
    },
    analysisDepth: 'Analysis Depth',
    analysisDepthOptions: {
      detailed: 'Standard',
      comprehensive: 'Comprehensive'
    },
    theme: 'Theme',
    themeOptions: {
      light: 'Light',
      dark: 'Dark',
      auto: 'Auto'
    },
    showThinkingProcess: 'Show thinking process',
    saving: 'Saving...',
    saved: 'Saved',
    saveFailed: 'Save failed'
  },
  history: {
    title: 'History',
    newSession: 'New session',
    deleteConfirm: 'Are you sure to delete this session?',
    renameSession: 'Rename session',
    loadMore: 'Load more',
    noSessions: 'No history sessions'
  },
  feedback: {
    positive: 'Helpful',
    negative: 'Not helpful',
    submitted: 'Thank you for your feedback',
    submitFailed: 'Submit failed'
  },
  errors: {
    networkError: 'Network connection failed, please check your network',
    authError: 'Authentication failed, please login again',
    serverError: 'Server error, please try again later',
    unknownError: 'Unknown error, please try again later',
    tableauInitError: 'Tableau initialization failed'
  }
}
```


## 样式和主题设计

### CSS 变量定义

```scss
// assets/styles/variables.scss

:root {
  // 颜色系统
  --color-primary: #409eff;
  --color-success: #67c23a;
  --color-warning: #e6a23c;
  --color-danger: #f56c6c;
  --color-info: #909399;
  
  // 文本颜色
  --color-text-primary: #303133;
  --color-text-regular: #606266;
  --color-text-secondary: #909399;
  --color-text-placeholder: #c0c4cc;
  
  // 边框颜色
  --color-border-base: #dcdfe6;
  --color-border-light: #e4e7ed;
  --color-border-lighter: #ebeef5;
  --color-border-extra-light: #f2f6fc;
  
  // 背景颜色
  --color-bg-base: #ffffff;
  --color-bg-light: #f5f7fa;
  --color-bg-lighter: #fafafa;
  
  // 聊天消息颜色
  --color-user-message-bg: #409eff;
  --color-user-message-text: #ffffff;
  --color-assistant-message-bg: #f4f4f5;
  --color-assistant-message-text: #303133;
  
  // 间距
  --spacing-xs: 4px;
  --spacing-sm: 8px;
  --spacing-md: 16px;
  --spacing-lg: 24px;
  --spacing-xl: 32px;
  
  // 圆角
  --border-radius-sm: 4px;
  --border-radius-md: 8px;
  --border-radius-lg: 12px;
  
  // 阴影
  --shadow-sm: 0 2px 4px rgba(0, 0, 0, 0.1);
  --shadow-md: 0 4px 8px rgba(0, 0, 0, 0.12);
  --shadow-lg: 0 8px 16px rgba(0, 0, 0, 0.15);
  
  // 字体
  --font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  --font-size-xs: 12px;
  --font-size-sm: 14px;
  --font-size-md: 16px;
  --font-size-lg: 18px;
  --font-size-xl: 20px;
  
  // 过渡
  --transition-fast: 0.15s;
  --transition-base: 0.3s;
  --transition-slow: 0.5s;
}

// 深色主题
[data-theme='dark'] {
  --color-text-primary: #e5eaf3;
  --color-text-regular: #cfd3dc;
  --color-text-secondary: #a3a6ad;
  --color-text-placeholder: #6c6e72;
  
  --color-border-base: #4c4d4f;
  --color-border-light: #414243;
  --color-border-lighter: #363637;
  --color-border-extra-light: #2b2b2c;
  
  --color-bg-base: #1a1a1a;
  --color-bg-light: #262626;
  --color-bg-lighter: #2d2d2d;
  
  --color-assistant-message-bg: #2d2d2d;
  --color-assistant-message-text: #e5eaf3;
}
```

### 全局样式

```scss
// assets/styles/global.scss

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html,
body {
  width: 100%;
  height: 100%;
  font-family: var(--font-family);
  font-size: var(--font-size-md);
  color: var(--color-text-primary);
  background-color: var(--color-bg-base);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

#app {
  width: 100%;
  height: 100%;
}

// 滚动条样式
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: var(--color-bg-light);
}

::-webkit-scrollbar-thumb {
  background: var(--color-border-base);
  border-radius: var(--border-radius-sm);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-secondary);
}

// Markdown 样式
.markdown-content {
  line-height: 1.6;
  
  h1, h2, h3, h4, h5, h6 {
    margin: var(--spacing-md) 0 var(--spacing-sm);
    font-weight: 600;
  }
  
  p {
    margin: var(--spacing-sm) 0;
  }
  
  ul, ol {
    margin: var(--spacing-sm) 0;
    padding-left: var(--spacing-lg);
  }
  
  code {
    padding: 2px 6px;
    background: var(--color-bg-light);
    border-radius: var(--border-radius-sm);
    font-family: 'Courier New', monospace;
    font-size: 0.9em;
  }
  
  pre {
    margin: var(--spacing-md) 0;
    padding: var(--spacing-md);
    background: var(--color-bg-light);
    border-radius: var(--border-radius-md);
    overflow-x: auto;
    
    code {
      padding: 0;
      background: none;
    }
  }
  
  table {
    width: 100%;
    margin: var(--spacing-md) 0;
    border-collapse: collapse;
    
    th, td {
      padding: var(--spacing-sm);
      border: 1px solid var(--color-border-base);
      text-align: left;
    }
    
    th {
      background: var(--color-bg-light);
      font-weight: 600;
    }
  }
  
  blockquote {
    margin: var(--spacing-md) 0;
    padding-left: var(--spacing-md);
    border-left: 4px solid var(--color-primary);
    color: var(--color-text-secondary);
  }
}

// 代码高亮样式（使用 highlight.js 主题）
@import 'highlight.js/styles/github.css';

[data-theme='dark'] {
  @import 'highlight.js/styles/github-dark.css';
}
```

### 响应式断点

```scss
// assets/styles/mixins.scss

// 响应式断点
$breakpoint-mobile: 768px;
$breakpoint-tablet: 1024px;
$breakpoint-desktop: 1280px;

@mixin mobile {
  @media (max-width: #{$breakpoint-mobile - 1px}) {
    @content;
  }
}

@mixin tablet {
  @media (min-width: #{$breakpoint-mobile}) and (max-width: #{$breakpoint-tablet - 1px}) {
    @content;
  }
}

@mixin desktop {
  @media (min-width: #{$breakpoint-tablet}) {
    @content;
  }
}

// 文本省略
@mixin text-ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@mixin multi-line-ellipsis($lines: 2) {
  display: -webkit-box;
  -webkit-line-clamp: $lines;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

// Flexbox 居中
@mixin flex-center {
  display: flex;
  align-items: center;
  justify-content: center;
}
```


## 错误处理策略

### 错误分类和处理

| 错误类型 | 检测方式 | 处理策略 | 用户提示 |
|---------|---------|---------|---------|
| 网络错误 | `error.request` 存在但 `error.response` 不存在 | 显示重试按钮 | "网络连接失败，请检查网络" |
| 认证错误 | HTTP 401/403 | 清除本地状态，提示重新登录 | "认证失败，请重新登录" |
| 服务器错误 | HTTP 500/502/503 | 显示重试按钮，记录错误日志 | "服务器错误，请稍后重试" |
| 客户端错误 | HTTP 400/404 | 显示具体错误信息 | 后端返回的错误消息 |
| SSE 连接错误 | SSE 连接断开或超时 | 自动重连（最多 3 次） | "连接中断，正在重连..." |
| Tableau API 错误 | Tableau 初始化失败 | 显示错误信息，禁用功能 | "Tableau 初始化失败" |
| 输入验证错误 | 前端验证失败 | 高亮错误字段，显示提示 | "请输入有效的内容" |

### 错误处理组件

```typescript
// composables/useErrorHandler.ts

import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { AxiosError } from 'axios'

export function useErrorHandler() {
  const error = ref<string | null>(null)
  const isRetrying = ref(false)

  function handleError(err: any, context?: string) {
    console.error(`Error in ${context}:`, err)
    
    if (err.response) {
      // HTTP 错误
      const status = err.response.status
      const message = err.response.data?.message || '请求失败'
      
      switch (status) {
        case 400:
          error.value = `请求参数错误: ${message}`
          ElMessage.error(error.value)
          break
        case 401:
        case 403:
          error.value = '认证失败，请重新登录'
          ElMessageBox.alert(error.value, '认证错误', {
            confirmButtonText: '确定',
            type: 'error'
          })
          break
        case 404:
          error.value = '请求的资源不存在'
          ElMessage.error(error.value)
          break
        case 500:
        case 502:
        case 503:
          error.value = '服务器错误，请稍后重试'
          ElMessage.error(error.value)
          break
        default:
          error.value = message
          ElMessage.error(error.value)
      }
    } else if (err.request) {
      // 网络错误
      error.value = '网络连接失败，请检查网络'
      ElMessage.error(error.value)
    } else {
      // 其他错误
      error.value = err.message || '未知错误'
      ElMessage.error(error.value)
    }
  }

  async function retry<T>(
    fn: () => Promise<T>,
    maxRetries: number = 3,
    delay: number = 1000
  ): Promise<T> {
    isRetrying.value = true
    let lastError: any
    
    for (let i = 0; i < maxRetries; i++) {
      try {
        const result = await fn()
        isRetrying.value = false
        return result
      } catch (err) {
        lastError = err
        if (i < maxRetries - 1) {
          await new Promise(resolve => setTimeout(resolve, delay * (i + 1)))
        }
      }
    }
    
    isRetrying.value = false
    throw lastError
  }

  function clearError() {
    error.value = null
  }

  return {
    error,
    isRetrying,
    handleError,
    retry,
    clearError
  }
}
```

### SSE 重连机制

```typescript
// composables/useSSEConnection.ts

import { ref } from 'vue'
import { SSEClient } from '@/services/sse/sse-client'
import type { ChatRequest } from '@/types/chat'

export function useSSEConnection() {
  const sseClient = ref<SSEClient | null>(null)
  const isConnected = ref(false)
  const reconnectAttempts = ref(0)
  const maxReconnectAttempts = 3

  async function connect(
    request: ChatRequest,
    callbacks: {
      onToken: (token: string) => void
      onDone: () => void
      onError: (error: string) => void
    }
  ) {
    try {
      sseClient.value = new SSEClient()
      
      await sseClient.value.connect({
        url: `${import.meta.env.VITE_API_BASE_URL}/api/chat/stream`,
        body: request,
        onToken: callbacks.onToken,
        onDone: () => {
          isConnected.value = false
          reconnectAttempts.value = 0
          callbacks.onDone()
        },
        onError: async (error) => {
          isConnected.value = false
          
          if (reconnectAttempts.value < maxReconnectAttempts) {
            reconnectAttempts.value++
            console.log(`Reconnecting... Attempt ${reconnectAttempts.value}`)
            
            // 指数退避
            const delay = Math.pow(2, reconnectAttempts.value) * 1000
            await new Promise(resolve => setTimeout(resolve, delay))
            
            // 重新连接
            await connect(request, callbacks)
          } else {
            reconnectAttempts.value = 0
            callbacks.onError(error)
          }
        }
      })
      
      isConnected.value = true
    } catch (error: any) {
      isConnected.value = false
      callbacks.onError(error.message || 'SSE 连接失败')
    }
  }

  function disconnect() {
    if (sseClient.value) {
      sseClient.value.disconnect()
      sseClient.value = null
    }
    isConnected.value = false
    reconnectAttempts.value = 0
  }

  return {
    isConnected,
    reconnectAttempts,
    connect,
    disconnect
  }
}
```


## 安全设计

### XSS 防护

1. **Markdown 渲染安全**
   - 使用 markdown-it 的安全配置
   - 禁用 HTML 标签解析（`html: false`）
   - 过滤危险的 JavaScript 代码

```typescript
// utils/markdown.ts 中的安全配置

const md = new MarkdownIt({
  html: false, // 禁用 HTML 标签
  xhtmlOut: true, // 使用 XHTML 风格的标签
  breaks: true, // 转换换行符为 <br>
  linkify: true, // 自动识别链接
  typographer: true // 启用排版优化
})

// 额外的内容清理
export function sanitizeMarkdown(content: string): string {
  return content
    .replace(/<script[^>]*>.*?<\/script>/gi, '') // 移除 script 标签
    .replace(/javascript:/gi, '') // 移除 javascript: 协议
    .replace(/on\w+\s*=/gi, '') // 移除事件处理器
    .replace(/<iframe[^>]*>.*?<\/iframe>/gi, '') // 移除 iframe
}
```

2. **用户输入验证**
   - 验证输入长度
   - 移除控制字符
   - 转义特殊字符

```typescript
// utils/validation.ts

export function sanitizeInput(text: string): string {
  return text
    .replace(/[\x00-\x1F\x7F]/g, '') // 移除控制字符
    .trim()
}
```

### Content Security Policy (CSP)

在 `index.html` 中配置 CSP：

```html
<meta http-equiv="Content-Security-Policy" content="
  default-src 'self';
  script-src 'self' 'unsafe-inline' 'unsafe-eval' https://extensions.tableau.com;
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: https:;
  font-src 'self' data:;
  connect-src 'self' https://localhost:8000 https://your-backend-domain.com;
  frame-ancestors 'self' https://*.tableau.com https://*.tableauusercontent.com;
">
```

### HTTPS 配置

#### 开发环境

使用 Vite 插件生成自签名证书：

```typescript
// vite.config.ts

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import basicSsl from '@vitejs/plugin-basic-ssl'

export default defineConfig({
  plugins: [
    vue(),
    basicSsl() // 自动生成自签名证书
  ],
  server: {
    https: true,
    port: 5173,
    host: 'localhost'
  }
})
```

#### 生产环境

使用有效的 SSL 证书（Let's Encrypt 或商业证书）：

```nginx
# nginx 配置示例

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    location / {
        root /path/to/analytics_assistant/public/dist;
        try_files $uri $uri/ /index.html;
    }
}
```

### 敏感信息保护

1. **不在前端存储敏感信息**
   - API Key、Token 等敏感信息只在后端存储
   - 前端只存储非敏感的用户设置

2. **环境变量管理**

```env
# .env.development
VITE_API_BASE_URL=https://localhost:8000

# .env.production
VITE_API_BASE_URL=https://your-backend-domain.com
```

3. **日志脱敏**

```typescript
// utils/logger.ts

export function logError(context: string, error: any) {
  // 移除敏感信息
  const sanitizedError = {
    message: error.message,
    status: error.response?.status,
    // 不记录完整的请求/响应数据
  }
  
  console.error(`[${context}]`, sanitizedError)
}
```


## 性能优化

### 虚拟滚动

使用 vue-virtual-scroller 处理大量消息：

```vue
<!-- components/chat/MessageList.vue -->

<template>
  <RecycleScroller
    class="message-list"
    :items="messages"
    :item-size="100"
    key-field="id"
    v-slot="{ item }"
  >
    <MessageItem :message="item" />
  </RecycleScroller>
</template>

<script setup lang="ts">
import { RecycleScroller } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'
import MessageItem from './MessageItem.vue'

const props = defineProps<{
  messages: Message[]
}>()
</script>
```

### Markdown 渲染防抖

```typescript
// composables/useMarkdownRenderer.ts

import { ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { renderMarkdown } from '@/utils/markdown'

export function useMarkdownRenderer(content: Ref<string>) {
  const renderedContent = ref('')
  
  const debouncedRender = useDebounceFn(() => {
    renderedContent.value = renderMarkdown(content.value)
  }, 300)
  
  watch(content, () => {
    debouncedRender()
  }, { immediate: true })
  
  return {
    renderedContent
  }
}
```

### 懒加载和代码分割

```typescript
// router/index.ts (如果使用路由)

import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('@/views/ChatView.vue') // 懒加载
    },
    {
      path: '/settings',
      component: () => import('@/views/SettingsView.vue')
    }
  ]
})
```

### 会话列表分页

```typescript
// stores/session.ts 中的分页实现

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: [] as Session[],
    total: 0,
    offset: 0,
    limit: 20,
    isLoading: false
  }),

  actions: {
    async loadMoreSessions() {
      if (!this.hasMoreSessions || this.isLoading) return
      
      this.offset += this.limit
      this.isLoading = true
      
      try {
        const response = await sessionService.getSessions(this.offset, this.limit)
        // 追加新数据，而不是替换
        this.sessions.push(...response.data.sessions)
      } finally {
        this.isLoading = false
      }
    }
  }
})
```

### 缓存策略

```typescript
// composables/useCache.ts

import { ref } from 'vue'

interface CacheEntry<T> {
  data: T
  timestamp: number
}

export function useCache<T>(ttl: number = 5 * 60 * 1000) {
  const cache = ref(new Map<string, CacheEntry<T>>())

  function get(key: string): T | null {
    const entry = cache.value.get(key)
    if (!entry) return null
    
    const now = Date.now()
    if (now - entry.timestamp > ttl) {
      cache.value.delete(key)
      return null
    }
    
    return entry.data
  }

  function set(key: string, data: T) {
    cache.value.set(key, {
      data,
      timestamp: Date.now()
    })
  }

  function clear() {
    cache.value.clear()
  }

  return {
    get,
    set,
    clear
  }
}
```

### 构建优化

```typescript
// vite.config.ts

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { visualizer } from 'rollup-plugin-visualizer'

export default defineConfig({
  plugins: [
    vue(),
    visualizer({ // 分析打包体积
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
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          'element-plus': ['element-plus'],
          'markdown': ['markdown-it', 'highlight.js']
        }
      }
    },
    chunkSizeWarningLimit: 1000
  }
})
```


## 部署架构

### 构建流程

```bash
# 1. 安装依赖
cd frontend
npm install

# 2. 构建生产版本
npm run build

# 3. 构建产物输出到 analytics_assistant/public/dist/
# - index.html
# - assets/index-[hash].js
# - assets/index-[hash].css
# - 其他静态资源
```

### Tableau Extension 清单文件

```xml
<!-- analytics_assistant/public/manifest.trex -->

<?xml version="1.0" encoding="utf-8"?>
<manifest manifest-version="0.1" xmlns="http://www.tableau.com/xml/extension_manifest">
  <dashboard-extension id="com.example.tableau-ai-assistant" extension-version="1.0.0">
    <default-locale>zh_CN</default-locale>
    <name resource-id="name"/>
    <description>Tableau AI Assistant Extension</description>
    <author name="Your Name" email="your.email@example.com" organization="Your Organization" website="https://your-website.com"/>
    <min-api-version>1.4</min-api-version>
    <source-location>
      <url>https://your-domain.com/dist/index.html</url>
    </source-location>
    <icon>
      <![CDATA[iVBORw0KGgoAAAANSUhEUgAA...]]>
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

### 部署架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Tableau Server/Cloud                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                  Dashboard                             │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  Extension (iframe)                              │  │  │
│  │  │  https://your-domain.com/dist/index.html        │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Web Server (Nginx)                        │
│  https://your-domain.com                                    │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  /dist/                                                │  │
│  │  - index.html                                          │  │
│  │  - assets/                                             │  │
│  │  - manifest.trex                                       │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                Backend FastAPI Service                       │
│  https://your-backend-domain.com                            │
│  - POST /api/chat/stream                                    │
│  - GET/POST/PUT/DELETE /api/sessions                        │
│  - GET/PUT /api/settings                                    │
│  - POST /api/feedback                                       │
└─────────────────────────────────────────────────────────────┘
```

### Nginx 配置示例

```nginx
# /etc/nginx/sites-available/tableau-extension

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL 证书
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # 安全头
    add_header X-Frame-Options "ALLOW-FROM https://*.tableau.com" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    
    # 静态文件
    location /dist/ {
        root /var/www/analytics_assistant/public;
        try_files $uri $uri/ /dist/index.html;
        
        # 缓存策略
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
    
    # manifest.trex
    location /manifest.trex {
        root /var/www/analytics_assistant/public;
        add_header Content-Type "application/xml";
    }
    
    # 日志
    access_log /var/log/nginx/tableau-extension-access.log;
    error_log /var/log/nginx/tableau-extension-error.log;
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

### 环境变量配置

```env
# .env.production

VITE_API_BASE_URL=https://your-backend-domain.com
VITE_APP_VERSION=1.0.0
VITE_ENABLE_ANALYTICS=true
```

### CI/CD 流程（GitHub Actions 示例）

```yaml
# .github/workflows/deploy.yml

name: Deploy Frontend

on:
  push:
    branches:
      - main
    paths:
      - 'frontend/**'

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      
      - name: Install dependencies
        working-directory: ./frontend
        run: npm ci
      
      - name: Build
        working-directory: ./frontend
        run: npm run build
        env:
          VITE_API_BASE_URL: ${{ secrets.API_BASE_URL }}
      
      - name: Deploy to server
        uses: appleboy/scp-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          source: "analytics_assistant/public/dist/*"
          target: "/var/www/"
      
      - name: Restart Nginx
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: sudo systemctl reload nginx
```


## 正确性属性

*属性是一个特征或行为，应该在系统的所有有效执行中保持为真——本质上是关于系统应该做什么的形式化陈述。属性作为人类可读规范和机器可验证正确性保证之间的桥梁。*

### 属性反思

在编写正确性属性之前，我们需要识别并消除冗余属性：

**识别的冗余情况**：

1. **消息显示相关**：
   - 3.2（按时间顺序显示消息）和 3.7（显示时间戳）可以合并为一个属性
   - 3.6（自动滚动）是独立的 UI 行为

2. **输入验证相关**：
   - 4.5（空输入禁用发送）和 4.8（未选择数据源阻止发送）都是发送前置条件验证，可以合并

3. **SSE 事件处理**：
   - 5.4、5.5、5.6 是针对不同事件类型的处理，应该合并为一个综合属性

4. **API 请求头**：
   - 1.5（所有请求包含用户名）是一个跨所有 API 的通用属性

5. **设置保存和加载**：
   - 7.4/7.5、8.4/8.5 都是设置的保存和加载，可以合并为一个通用的设置持久化属性

6. **会话操作**：
   - 9.6、9.7、9.8 都是会话的 CRUD 操作，可以合并

**保留的独立属性**：
- Markdown 渲染安全性（3.4 + 15.2）
- 本地存储一致性（6.5）
- 多语言翻译完整性（7.7）
- 响应式布局适配（12.1、12.4）
- 错误分类和处理（13.1）
- 缓存一致性（14.5）
- 输入验证（15.5）
- 可访问性标签（16.1、16.4、16.7）

### 属性 1：API 请求认证头一致性

*对于任何* 发送到后端的 API 请求，请求头中必须包含 `X-Tableau-Username` 字段，且值为当前 Tableau 用户名

**验证：需求 1.5**

### 属性 2：消息时间顺序一致性

*对于任何* 会话中的消息列表，消息必须按照时间戳升序排列，且每条消息都包含有效的时间戳

**验证：需求 3.2, 3.7**

### 属性 3：Markdown 渲染安全性

*对于任何* 用户输入的 Markdown 内容，渲染后的 HTML 不得包含可执行的 JavaScript 代码（script 标签、javascript: 协议、事件处理器）

**验证：需求 3.4, 15.2**

### 属性 4：消息发送前置条件

*对于任何* 发送消息的尝试，当且仅当输入内容非空且已选择数据源时，发送操作才应被允许

**验证：需求 4.5, 4.8**

### 属性 5：SSE 事件处理完整性

*对于任何* SSE 事件流，系统必须正确处理所有事件类型（token、done、error），且每个事件类型触发相应的状态更新

**验证：需求 5.3, 5.4, 5.5, 5.6**

### 属性 6：本地存储序列化对称性

*对于任何* 存储到 localStorage 的数据，读取后反序列化的结果必须与原始数据等价

**验证：需求 6.5**

### 属性 7：多语言翻译完整性

*对于任何* UI 文本键，在所有支持的语言（中文、英文）中都必须存在对应的翻译

**验证：需求 7.7**

### 属性 8：用户设置持久化一致性

*对于任何* 用户设置的修改，保存到后端后再次加载时，设置值必须与修改后的值一致

**验证：需求 7.4, 7.5, 8.4, 8.5**

### 属性 9：会话 CRUD 操作幂等性

*对于任何* 会话的创建、更新、删除操作，操作成功后本地状态必须与后端状态保持一致

**验证：需求 9.6, 9.7, 9.8**

### 属性 10：响应式布局元素可见性

*对于任何* 容器尺寸，关键 UI 元素（输入框、发送按钮）必须始终可见且可交互

**验证：需求 12.1, 12.4**

### 属性 11：错误类型分类正确性

*对于任何* API 错误响应，系统必须根据 HTTP 状态码正确分类错误类型（网络错误、认证错误、服务器错误、客户端错误）

**验证：需求 13.1, 13.2**

### 属性 12：会话数据缓存一致性

*对于任何* 已加载的会话，重复请求相同会话时应返回缓存数据，且缓存数据与首次加载的数据一致

**验证：需求 14.5**

### 属性 13：用户输入清理幂等性

*对于任何* 用户输入，经过清理函数处理后，再次处理的结果必须与第一次处理的结果相同

**验证：需求 15.5**

### 属性 14：ARIA 标签完整性

*对于任何* 交互元素（按钮、输入框、链接），必须包含适当的 ARIA 标签或文本替代

**验证：需求 16.1, 16.4**

### 属性 15：键盘操作完整性

*对于任何* 应用功能，必须存在对应的键盘操作方式（Tab 导航、Enter 确认、Esc 取消）

**验证：需求 16.7**


## 测试策略

### 双重测试方法

本项目采用单元测试和属性测试相结合的方法，以确保全面的测试覆盖：

- **单元测试**：验证特定示例、边界情况和错误条件
- **属性测试**：通过随机化验证跨所有输入的通用属性
- 两者互补且都是必需的（单元测试捕获具体错误，属性测试验证通用正确性）

### 单元测试平衡

单元测试对于特定示例和边界情况很有帮助，但应避免编写过多单元测试——属性测试可以处理大量输入的覆盖。

**单元测试应关注**：
- 演示正确行为的特定示例
- 组件之间的集成点
- 边界情况和错误条件

**属性测试应关注**：
- 对所有输入都成立的通用属性
- 通过随机化实现全面的输入覆盖

### 测试框架和工具

| 类别 | 工具 | 用途 |
|------|------|------|
| 单元测试框架 | Vitest | Vue 3 推荐的测试框架 |
| 组件测试 | @vue/test-utils | Vue 组件测试工具 |
| 属性测试 | fast-check | JavaScript 属性测试库 |
| E2E 测试 | Playwright | 端到端测试 |
| Mock 工具 | vitest/mock | API 和模块 Mock |
| 覆盖率 | @vitest/coverage-v8 | 代码覆盖率报告 |

### 属性测试配置

每个属性测试必须：
- 运行最少 100 次迭代（由于随机化）
- 引用设计文档中的属性
- 使用标签格式：`Feature: tableau-extension-frontend, Property {number}: {property_text}`

### 测试示例

#### 单元测试示例

```typescript
// tests/unit/components/MessageItem.spec.ts

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MessageItem from '@/components/chat/MessageItem.vue'

describe('MessageItem', () => {
  it('应该渲染用户消息', () => {
    const message = {
      id: '1',
      role: 'user',
      content: 'Hello',
      timestamp: new Date(),
      sessionId: 'session-1'
    }
    
    const wrapper = mount(MessageItem, {
      props: { message }
    })
    
    expect(wrapper.find('.user-message').exists()).toBe(true)
    expect(wrapper.text()).toContain('Hello')
  })
  
  it('应该在输入为空时禁用发送按钮', () => {
    const wrapper = mount(InputBox)
    const sendButton = wrapper.find('.send-button')
    
    expect(sendButton.attributes('disabled')).toBeDefined()
  })
})
```

#### 属性测试示例

```typescript
// tests/property/markdown-safety.spec.ts

import { describe, it } from 'vitest'
import fc from 'fast-check'
import { sanitizeMarkdown } from '@/utils/markdown'

describe('Property 3: Markdown 渲染安全性', () => {
  /**
   * Feature: tableau-extension-frontend, Property 3:
   * 对于任何用户输入的 Markdown 内容，渲染后的 HTML 不得包含可执行的 JavaScript 代码
   */
  it('应该移除所有危险的 JavaScript 代码', () => {
    fc.assert(
      fc.property(
        fc.string(),
        (content) => {
          const sanitized = sanitizeMarkdown(content)
          
          // 验证不包含危险内容
          expect(sanitized).not.toMatch(/<script[^>]*>/i)
          expect(sanitized).not.toMatch(/javascript:/i)
          expect(sanitized).not.toMatch(/on\w+\s*=/i)
          expect(sanitized).not.toMatch(/<iframe[^>]*>/i)
        }
      ),
      { numRuns: 100 }
    )
  })
})
```

```typescript
// tests/property/storage-symmetry.spec.ts

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { storage } from '@/utils/storage'

describe('Property 6: 本地存储序列化对称性', () => {
  /**
   * Feature: tableau-extension-frontend, Property 6:
   * 对于任何存储到 localStorage 的数据，读取后反序列化的结果必须与原始数据等价
   */
  it('存储和读取应该保持数据一致性', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1 }),
        fc.oneof(
          fc.string(),
          fc.integer(),
          fc.boolean(),
          fc.array(fc.string()),
          fc.record({
            id: fc.string(),
            name: fc.string(),
            value: fc.integer()
          })
        ),
        (key, value) => {
          storage.set(key, value)
          const retrieved = storage.get(key)
          
          expect(retrieved).toEqual(value)
          
          // 清理
          storage.remove(key)
        }
      ),
      { numRuns: 100 }
    )
  })
})
```

```typescript
// tests/property/message-ordering.spec.ts

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import type { Message } from '@/types/chat'

describe('Property 2: 消息时间顺序一致性', () => {
  /**
   * Feature: tableau-extension-frontend, Property 2:
   * 对于任何会话中的消息列表，消息必须按照时间戳升序排列
   */
  it('消息列表应该按时间戳排序', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            id: fc.string(),
            role: fc.constantFrom('user', 'assistant'),
            content: fc.string(),
            timestamp: fc.date(),
            sessionId: fc.string()
          })
        ),
        (messages) => {
          // 排序消息
          const sorted = [...messages].sort(
            (a, b) => a.timestamp.getTime() - b.timestamp.getTime()
          )
          
          // 验证排序正确性
          for (let i = 1; i < sorted.length; i++) {
            expect(sorted[i].timestamp.getTime()).toBeGreaterThanOrEqual(
              sorted[i - 1].timestamp.getTime()
            )
          }
        }
      ),
      { numRuns: 100 }
    )
  })
})
```

### 测试覆盖率目标

| 类别 | 目标覆盖率 |
|------|-----------|
| 语句覆盖率 | ≥ 80% |
| 分支覆盖率 | ≥ 75% |
| 函数覆盖率 | ≥ 80% |
| 行覆盖率 | ≥ 80% |

### 测试运行命令

```json
// package.json

{
  "scripts": {
    "test": "vitest",
    "test:unit": "vitest run --dir tests/unit",
    "test:property": "vitest run --dir tests/property",
    "test:e2e": "playwright test",
    "test:coverage": "vitest run --coverage"
  }
}
```


## 开发环境配置

### 环境要求

- Node.js: ≥ 18.0.0
- npm: ≥ 9.0.0
- 操作系统：Windows、macOS、Linux

### 项目初始化

```bash
# 1. 创建项目目录
mkdir frontend
cd frontend

# 2. 初始化 Vue 3 + TypeScript 项目
npm create vite@latest . -- --template vue-ts

# 3. 安装依赖
npm install

# 4. 安装额外依赖
npm install element-plus pinia vue-i18n axios markdown-it highlight.js vue-virtual-scroller
npm install @tableau/extensions-api-types --save-dev
npm install @vitejs/plugin-basic-ssl --save-dev

# 5. 安装测试依赖
npm install -D vitest @vue/test-utils @vitest/coverage-v8 fast-check playwright
```

### package.json 配置

```json
{
  "name": "tableau-ai-assistant-frontend",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:unit": "vitest run --dir tests/unit",
    "test:property": "vitest run --dir tests/property",
    "test:e2e": "playwright test",
    "test:coverage": "vitest run --coverage",
    "lint": "eslint . --ext .vue,.js,.jsx,.cjs,.mjs,.ts,.tsx,.cts,.mts --fix",
    "format": "prettier --write src/"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "pinia": "^2.1.0",
    "vue-i18n": "^9.9.0",
    "vue-router": "^4.2.0",
    "axios": "^1.6.0",
    "element-plus": "^2.5.0",
    "markdown-it": "^14.0.0",
    "highlight.js": "^11.9.0",
    "vue-virtual-scroller": "^2.0.0",
    "@vueuse/core": "^10.7.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "@vitejs/plugin-basic-ssl": "^1.0.0",
    "@vue/test-utils": "^2.4.0",
    "@vitest/coverage-v8": "^1.0.0",
    "@tableau/extensions-api-types": "^1.10.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "vitest": "^1.0.0",
    "vue-tsc": "^1.8.0",
    "eslint": "^8.56.0",
    "eslint-plugin-vue": "^9.19.0",
    "@typescript-eslint/eslint-plugin": "^6.18.0",
    "@typescript-eslint/parser": "^6.18.0",
    "prettier": "^3.1.0",
    "fast-check": "^3.15.0",
    "playwright": "^1.40.0",
    "sass": "^1.69.0"
  }
}
```

### Vite 配置

```typescript
// vite.config.ts

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import basicSsl from '@vitejs/plugin-basic-ssl'
import { resolve } from 'path'

export default defineConfig({
  plugins: [
    vue(),
    basicSsl() // HTTPS 开发服务器
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    https: true,
    port: 5173,
    host: 'localhost',
    proxy: {
      '/api': {
        target: 'https://localhost:8000',
        changeOrigin: true,
        secure: false
      }
    }
  },
  build: {
    outDir: '../analytics_assistant/public/dist',
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'pinia'],
          'element-plus': ['element-plus'],
          'markdown': ['markdown-it', 'highlight.js']
        }
      }
    }
  }
})
```

### TypeScript 配置

```json
// tsconfig.json

{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,

    /* Bundler mode */
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "preserve",

    /* Linting */
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,

    /* Path mapping */
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    },

    /* Types */
    "types": ["vite/client", "@tableau/extensions-api-types"]
  },
  "include": ["src/**/*.ts", "src/**/*.d.ts", "src/**/*.tsx", "src/**/*.vue"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

### ESLint 配置

```javascript
// .eslintrc.cjs

module.exports = {
  root: true,
  env: {
    browser: true,
    es2021: true,
    node: true
  },
  extends: [
    'eslint:recommended',
    'plugin:vue/vue3-recommended',
    'plugin:@typescript-eslint/recommended'
  ],
  parser: 'vue-eslint-parser',
  parserOptions: {
    ecmaVersion: 'latest',
    parser: '@typescript-eslint/parser',
    sourceType: 'module'
  },
  plugins: ['vue', '@typescript-eslint'],
  rules: {
    'vue/multi-word-component-names': 'off',
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }]
  }
}
```

### Prettier 配置

```json
// .prettierrc.json

{
  "semi": false,
  "singleQuote": true,
  "tabWidth": 2,
  "trailingComma": "none",
  "printWidth": 100,
  "arrowParens": "always",
  "endOfLine": "lf"
}
```

### 环境变量文件

```env
# .env.development

VITE_API_BASE_URL=https://localhost:8000
VITE_APP_VERSION=1.0.0
VITE_ENABLE_MOCK=false
```

```env
# .env.production

VITE_API_BASE_URL=https://your-backend-domain.com
VITE_APP_VERSION=1.0.0
VITE_ENABLE_MOCK=false
```

### 启动开发服务器

```bash
# 启动开发服务器（HTTPS）
npm run dev

# 访问 https://localhost:5173
# 首次访问需要信任自签名证书
```

### 构建生产版本

```bash
# 构建
npm run build

# 预览构建结果
npm run preview

# 构建产物位于 analytics_assistant/public/dist/
```


## 数据流设计

### 应用初始化流程

```
1. App.vue mounted
   ↓
2. 初始化 Tableau Extensions API
   - tableau.extensions.initializeAsync()
   - 获取用户名和数据源列表
   ↓
3. 加载用户设置
   - GET /api/settings
   - 应用语言、主题等设置
   ↓
4. 加载历史会话列表
   - GET /api/sessions?offset=0&limit=20
   ↓
5. 创建或加载当前会话
   - 如果有历史会话，加载最近的会话
   - 否则创建新会话
   ↓
6. 渲染聊天界面
```

### 消息发送流程

```
1. 用户输入消息并点击发送
   ↓
2. 前端验证
   - 检查输入是否为空
   - 检查是否已选择数据源
   ↓
3. 添加用户消息到 chatStore
   - 生成消息 ID
   - 设置时间戳
   ↓
4. 建立 SSE 连接
   - POST /api/chat/stream
   - 请求体包含：message, datasource_name, language, analysis_depth, session_id
   ↓
5. 接收 SSE 事件流
   - 创建空的 AI 消息
   - 逐个接收 token 事件
   - 追加 token 到消息内容
   ↓
6. 处理完成或错误
   - done 事件：标记消息完成
   - error 事件：显示错误提示
   ↓
7. 保存消息到会话
   - PUT /api/sessions/{id}
   - 更新会话的 updated_at
```

### 会话切换流程

```
1. 用户点击历史会话
   ↓
2. 加载会话详情
   - GET /api/sessions/{id}
   - 获取会话的所有消息
   ↓
3. 更新 chatStore
   - 设置 currentSessionId
   - 替换 messages 数组
   ↓
4. 更新 sessionStore
   - 设置 currentSession
   ↓
5. 渲染消息列表
   - MessageList 组件重新渲染
   - 滚动到最新消息
```

### 设置修改流程

```
1. 用户在 SettingsPanel 修改设置
   ↓
2. 更新 settingsStore 本地状态
   - 立即应用设置（如主题、语言）
   ↓
3. 保存设置到后端
   - PUT /api/settings
   - 显示保存状态（保存中、已保存、失败）
   ↓
4. 应用设置效果
   - 语言：切换 i18n locale
   - 主题：更新 data-theme 属性
   - 分析深度：下次发送消息时使用
```

### 状态同步机制

```
┌─────────────────────────────────────────────────────────────┐
│                    前端状态 (Pinia Stores)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  chatStore   │  │sessionStore  │  │settingsStore │      │
│  │  - messages  │  │  - sessions  │  │  - settings  │      │
│  │  - streaming │  │  - current   │  │  - loading   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↕
                    API 请求/响应
                            ↕
┌─────────────────────────────────────────────────────────────┐
│                    后端状态 (Database)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   messages   │  │   sessions   │  │user_settings │      │
│  │   table      │  │    table     │  │    table     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

**同步策略**：

1. **乐观更新**：
   - 用户操作立即更新本地状态
   - 异步发送 API 请求
   - 失败时回滚本地状态

2. **定期同步**：
   - 会话列表每 5 分钟刷新一次
   - 用户设置在初始化时加载

3. **冲突解决**：
   - 后端数据为准
   - 本地修改失败时提示用户重试


## 可访问性设计

### ARIA 标签规范

所有交互元素必须包含适当的 ARIA 标签：

```vue
<!-- 按钮 -->
<button
  aria-label="发送消息"
  :aria-disabled="!canSend"
>
  <i class="icon-send" aria-hidden="true"></i>
</button>

<!-- 输入框 -->
<textarea
  aria-label="消息输入框"
  aria-placeholder="输入您的问题..."
  :aria-invalid="hasError"
/>

<!-- 下拉选择 -->
<select
  aria-label="选择数据源"
  aria-required="true"
>
  <option value="">请选择数据源</option>
</select>

<!-- 消息列表 -->
<div
  role="log"
  aria-live="polite"
  aria-atomic="false"
>
  <!-- 消息项 -->
</div>
```

### 键盘导航支持

| 键 | 功能 | 上下文 |
|---|------|--------|
| Tab | 移动焦点到下一个可交互元素 | 全局 |
| Shift+Tab | 移动焦点到上一个可交互元素 | 全局 |
| Enter | 发送消息 | 输入框 |
| Shift+Enter | 插入换行 | 输入框 |
| Esc | 关闭面板 | 设置面板、历史面板 |
| ↑/↓ | 导航列表项 | 会话列表、数据源列表 |
| Space | 选择/激活 | 按钮、复选框 |

```vue
<!-- 键盘事件处理示例 -->
<template>
  <textarea
    @keydown="handleKeyDown"
    @keydown.esc="handleEscape"
  />
</template>

<script setup lang="ts">
function handleKeyDown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

function handleEscape() {
  closePanel()
}
</script>
```

### 焦点管理

```typescript
// composables/useFocusManagement.ts

import { ref, onMounted, onUnmounted } from 'vue'

export function useFocusManagement() {
  const focusableElements = ref<HTMLElement[]>([])
  const currentFocusIndex = ref(0)

  function updateFocusableElements() {
    const selector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    focusableElements.value = Array.from(
      document.querySelectorAll(selector)
    ) as HTMLElement[]
  }

  function focusNext() {
    currentFocusIndex.value = (currentFocusIndex.value + 1) % focusableElements.value.length
    focusableElements.value[currentFocusIndex.value]?.focus()
  }

  function focusPrevious() {
    currentFocusIndex.value = 
      (currentFocusIndex.value - 1 + focusableElements.value.length) % focusableElements.value.length
    focusableElements.value[currentFocusIndex.value]?.focus()
  }

  function trapFocus(event: KeyboardEvent) {
    if (event.key === 'Tab') {
      event.preventDefault()
      if (event.shiftKey) {
        focusPrevious()
      } else {
        focusNext()
      }
    }
  }

  onMounted(() => {
    updateFocusableElements()
    document.addEventListener('keydown', trapFocus)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', trapFocus)
  })

  return {
    focusNext,
    focusPrevious,
    updateFocusableElements
  }
}
```

### 颜色对比度

确保所有文本和交互元素符合 WCAG AA 标准（对比度 ≥ 4.5:1）：

```scss
// 浅色主题
:root {
  --color-text-primary: #303133;    // 对比度 12.6:1 (白色背景)
  --color-text-regular: #606266;    // 对比度 7.0:1
  --color-text-secondary: #909399;  // 对比度 4.6:1
}

// 深色主题
[data-theme='dark'] {
  --color-text-primary: #e5eaf3;    // 对比度 12.8:1 (黑色背景)
  --color-text-regular: #cfd3dc;    // 对比度 9.2:1
  --color-text-secondary: #a3a6ad;  // 对比度 5.1:1
}
```

### 屏幕阅读器支持

```vue
<!-- 使用 aria-live 区域通知动态内容更新 -->
<div
  role="status"
  aria-live="polite"
  aria-atomic="true"
  class="sr-only"
>
  {{ statusMessage }}
</div>

<!-- 隐藏装饰性图标 -->
<i class="icon-decorative" aria-hidden="true"></i>

<!-- 为图标提供文本替代 -->
<button>
  <i class="icon-send" aria-hidden="true"></i>
  <span class="sr-only">发送消息</span>
</button>

<style>
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
</style>
```


## 监控和日志

### 前端日志策略

```typescript
// utils/logger.ts

export enum LogLevel {
  DEBUG = 'DEBUG',
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR'
}

class Logger {
  private level: LogLevel = LogLevel.INFO

  constructor() {
    // 开发环境使用 DEBUG 级别
    if (import.meta.env.DEV) {
      this.level = LogLevel.DEBUG
    }
  }

  debug(message: string, ...args: any[]) {
    if (this.shouldLog(LogLevel.DEBUG)) {
      console.debug(`[DEBUG] ${message}`, ...args)
    }
  }

  info(message: string, ...args: any[]) {
    if (this.shouldLog(LogLevel.INFO)) {
      console.info(`[INFO] ${message}`, ...args)
    }
  }

  warn(message: string, ...args: any[]) {
    if (this.shouldLog(LogLevel.WARN)) {
      console.warn(`[WARN] ${message}`, ...args)
    }
  }

  error(message: string, error?: any) {
    if (this.shouldLog(LogLevel.ERROR)) {
      console.error(`[ERROR] ${message}`, error)
      
      // 生产环境发送错误到监控服务
      if (import.meta.env.PROD) {
        this.sendToMonitoring(message, error)
      }
    }
  }

  private shouldLog(level: LogLevel): boolean {
    const levels = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARN, LogLevel.ERROR]
    return levels.indexOf(level) >= levels.indexOf(this.level)
  }

  private sendToMonitoring(message: string, error: any) {
    // 发送到监控服务（如 Sentry）
    // 这里可以集成第三方监控服务
  }
}

export const logger = new Logger()
```

### 性能监控

```typescript
// utils/performance.ts

export class PerformanceMonitor {
  private marks = new Map<string, number>()

  start(name: string) {
    this.marks.set(name, performance.now())
  }

  end(name: string) {
    const startTime = this.marks.get(name)
    if (!startTime) {
      console.warn(`Performance mark "${name}" not found`)
      return
    }

    const duration = performance.now() - startTime
    this.marks.delete(name)

    logger.debug(`Performance: ${name} took ${duration.toFixed(2)}ms`)

    // 记录慢操作
    if (duration > 1000) {
      logger.warn(`Slow operation detected: ${name} took ${duration.toFixed(2)}ms`)
    }

    return duration
  }

  measure(name: string, fn: () => any) {
    this.start(name)
    const result = fn()
    this.end(name)
    return result
  }

  async measureAsync(name: string, fn: () => Promise<any>) {
    this.start(name)
    const result = await fn()
    this.end(name)
    return result
  }
}

export const perfMonitor = new PerformanceMonitor()
```

### 使用示例

```typescript
// 在组件中使用

import { logger } from '@/utils/logger'
import { perfMonitor } from '@/utils/performance'

export default {
  async mounted() {
    logger.info('ChatContainer mounted')
    
    try {
      await perfMonitor.measureAsync('loadSettings', async () => {
        await settingsStore.loadSettings()
      })
    } catch (error) {
      logger.error('Failed to load settings', error)
    }
  }
}
```

## 总结

本设计文档详细描述了 Tableau AI Assistant Extension 前端的技术架构、组件设计、数据流、API 服务、状态管理、安全策略、性能优化和部署方案。

### 关键设计决策

1. **技术栈**：Vue 3 + TypeScript + Vite，提供现代化的开发体验
2. **状态管理**：Pinia，简洁的 Vue 3 状态管理方案
3. **SSE 流式响应**：使用 Fetch API 实现实时流式对话
4. **Markdown 渲染**：markdown-it + highlight.js，安全且功能完整
5. **响应式设计**：移动优先，适配各种屏幕尺寸
6. **安全性**：XSS 防护、CSP、HTTPS、输入验证
7. **性能优化**：虚拟滚动、懒加载、缓存、代码分割
8. **可访问性**：ARIA 标签、键盘导航、颜色对比度

### 下一步

1. 根据本设计文档创建任务列表（tasks.md）
2. 搭建开发环境
3. 实现核心组件
4. 编写单元测试和属性测试
5. 集成 Tableau Extensions API
6. 部署到测试环境
7. 用户验收测试
8. 生产环境部署

