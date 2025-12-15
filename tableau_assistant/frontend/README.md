# Tableau AI Assistant Frontend

基于 Vue 3 + TypeScript 的 Tableau 扩展前端应用。

## 技术栈

- Vue 3.5+
- TypeScript 5.0+
- Vite 6.0+
- Pinia (状态管理)
- Vue Router (路由)
- Axios (HTTP 客户端)
- Tableau Embedding API v3

## 项目结构

```
frontend/
├── src/
│   ├── api/              # API 调用
│   │   ├── client.ts     # HTTP 客户端
│   │   └── streaming.ts  # SSE 流式处理
│   ├── assets/           # 静态资源
│   ├── components/       # Vue 组件
│   │   └── StreamingProgress.vue
│   ├── composables/      # 组合式函数
│   │   └── useStreaming.ts
│   ├── router/           # 路由配置
│   ├── stores/           # Pinia 状态管理
│   │   ├── analysis.ts   # 分析状态
│   │   └── tableau.ts    # Tableau 状态
│   ├── types/            # TypeScript 类型
│   │   ├── index.ts      # 通用类型
│   │   └── tableau.d.ts  # Tableau API 类型
│   ├── utils/            # 工具函数
│   │   └── tableau.ts    # Tableau 工具
│   ├── views/            # 页面视图
│   │   ├── AnalysisView.vue
│   │   ├── HomeView.vue
│   │   └── StreamingDemoView.vue
│   ├── App.vue           # 根组件
│   └── main.ts           # 应用入口
├── public/               # 公共资源
│   ├── manifest.trex     # Tableau 扩展清单
│   └── tableau.extensions.1.latest.min.js
├── package.json          # 依赖配置
├── tsconfig.json         # TypeScript 配置
└── vite.config.ts        # Vite 配置
```

## 快速开始

### 1. 安装依赖

```bash
cd tableau_assistant/frontend
npm install
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件
```

```env
VITE_API_BASE_URL=http://localhost:8000/api
```

### 3. 开发模式

```bash
npm run dev
```

### 4. 构建生产版本

```bash
npm run build
```

构建产物在 `dist/` 目录。

## 核心功能

### 流式查询

使用 SSE (Server-Sent Events) 实现实时流式输出：

```typescript
import { useStreaming } from '@/composables/useStreaming';

const { startStream, stopStream, tokens, isStreaming } = useStreaming();

// 开始流式查询
await startStream({
    question: '各地区销售额',
    datasourceLuid: 'abc123'
});
```

### Tableau 集成

通过 Tableau Extensions API 与 Tableau 交互：

```typescript
import { useTableauStore } from '@/stores/tableau';

const tableauStore = useTableauStore();

// 初始化扩展
await tableauStore.initialize();

// 获取当前数据源
const datasource = tableauStore.currentDatasource;
```

### 状态管理

使用 Pinia 管理应用状态：

```typescript
import { useAnalysisStore } from '@/stores/analysis';

const analysisStore = useAnalysisStore();

// 提交查询
await analysisStore.submitQuery('各产品类别的销售额');

// 获取结果
const results = analysisStore.results;
const insights = analysisStore.insights;
```

## 组件说明

### StreamingProgress

显示流式输出进度和内容：

```vue
<template>
  <StreamingProgress
    :tokens="tokens"
    :is-streaming="isStreaming"
    :current-node="currentNode"
  />
</template>
```

### AnalysisView

主分析页面，包含：
- 问题输入框
- 流式输出区域
- 洞察展示
- 推荐问题

## Tableau 扩展配置

### manifest.trex

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest manifest-version="0.1" xmlns="http://www.tableau.com/xml/extension_manifest">
  <dashboard-extension id="com.example.ai-assistant" extension-version="1.0.0">
    <default-locale>en_US</default-locale>
    <name resource-id="name"/>
    <description>AI Analysis Assistant</description>
    <author name="PandaHero" email="support@example.com" organization="Example" website="https://example.com"/>
    <min-api-version>1.0</min-api-version>
    <source-location>
      <url>http://localhost:5173</url>
    </source-location>
    <icon>icon.png</icon>
    <permissions>
      <permission>full data</permission>
    </permissions>
  </dashboard-extension>
</manifest>
```

## 开发指南

### 添加新页面

1. 在 `src/views/` 创建 Vue 组件
2. 在 `src/router/index.ts` 添加路由
3. 在导航中添加链接

### 添加新 API

1. 在 `src/api/` 添加 API 函数
2. 在 `src/types/` 添加类型定义
3. 在 Store 中调用 API

### 样式规范

- 使用 CSS 变量定义主题色
- 遵循 BEM 命名规范
- 响应式设计优先

## 测试

```bash
# 单元测试
npm run test:unit

# E2E 测试
npm run test:e2e
```

## 部署

### 开发环境

```bash
npm run dev
```

### 生产环境

```bash
npm run build
npm run preview
```

### Docker 部署

```dockerfile
FROM node:20-alpine as builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
```

---

**版本**: v2.2.0  
**最后更新**: 2024-12-14
