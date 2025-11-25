# VizQL Multi-Agent Frontend

基于Vue 3 + TypeScript的前端应用。

## 技术栈

- Vue 3.5+
- TypeScript 5.0+
- Vite 6.0+
- Pinia (状态管理)
- Vue Router (路由)
- Axios (HTTP客户端)
- Tableau Embedding API v3

## 项目结构

```
tableau_extension/
├── src/
│   ├── assets/           # 静态资源
│   ├── components/       # 组件
│   ├── views/            # 页面
│   ├── stores/           # Pinia状态管理
│   ├── router/           # 路由配置
│   ├── api/              # API调用
│   ├── types/            # TypeScript类型定义
│   ├── utils/            # 工具函数
│   ├── App.vue           # 根组件
│   └── main.ts           # 应用入口
├── public/               # 公共资源
├── tests/                # 测试代码
├── docs/                 # 项目文档
└── package.json          # 依赖配置
```

## 快速开始

1. 安装依赖：
```bash
npm install
```

2. 配置环境变量：
```bash
cp .env.example .env
# 编辑.env文件，填入你的配置
```

3. 运行开发服务器：
```bash
npm run dev
```

4. 构建生产版本：
```bash
npm run build
```

## 开发指南

参见 [docs/development.md](docs/development.md)
