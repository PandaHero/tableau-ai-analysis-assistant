# Tableau AI Analysis Assistant

基于 LangGraph 的智能 Tableau 数据分析助手，支持自然语言查询、语义字段映射、VizQL 查询生成和智能洞察分析。

## ✨ 核心特性

### 🎯 自然语言查询
- 用自然语言提问，自动生成 VizQL 查询
- 支持中英文混合查询
- 智能识别时间表达式（"上个月"、"去年同期"等）

### 🔄 Token 级流式输出
- 实时推送 LLM 生成的每个 token
- SSE (Server-Sent Events) 协议
- 提供流畅的用户体验

### 🔍 RAG 语义字段映射
- 两阶段检索：向量检索 top-K + Rerank
- 高置信度快速路径（≥0.9 直接返回，无需 LLM）
- 低置信度 LLM 回退选择
- 字段映射缓存（24小时 TTL）

### 📊 智能洞察分析
- **渐进式分析**：AI 驱动的"宝宝吃饭"模式
- **Phase 1 统计分析**：分布检测、异常检测、聚类分析
- **Phase 2 LLM 分析**：语义理解、洞察生成
- **智能分块**：基于维度层级的优先级分块

### 🔄 智能重规划
- 评估分析完成度（completeness_score）
- 自动生成探索问题
- 支持多问题并行执行（类 Tableau Pulse）
- 基于维度层级的钻取/汇总建议

### 🏗️ 纯语义中间层
- LLM 只做语义理解，输出 SemanticQuery
- VizQL 转换由确定性代码完成（100% 语法正确）
- 支持表计算（累计、排名、占比、移动平均、同比环比）
- 支持 LOD 表达式（FIXED、INCLUDE、EXCLUDE）

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Tableau AI Analysis Assistant                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  用户问题 ──► /api/chat/stream (SSE)                                         │
│                    │                                                         │
│                    ▼                                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    LangGraph Workflow (6 节点)                        │   │
│  │                                                                       │   │
│  │         ┌──────────────────────────────────────────────────────┐      │   │
│  │         │                                                      │      │   │
│  │         ▼                                                      │      │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │      │   │
│  │  │Understanding│───►│FieldMapper │───►│QueryBuilder │        │      │   │
│  │  │   (LLM)     │    │ (RAG+LLM)  │    │   (Code)    │        │      │   │
│  │  └──────┬──────┘    └─────────────┘    └──────┬──────┘        │      │   │
│  │         │                                     │               │      │   │
│  │         │ (非分析问题)                         ▼               │      │   │
│  │         │                             ┌─────────────┐         │      │   │
│  │         ▼                             │   Execute   │         │      │   │
│  │       [END]                           │   (Code)    │         │      │   │
│  │                                       └──────┬──────┘         │      │   │
│  │                                              │                │      │   │
│  │                                              ▼                │      │   │
│  │                                       ┌─────────────┐         │      │   │
│  │                                       │   Insight   │         │      │   │
│  │                                       │   (LLM)     │         │      │   │
│  │                                       └──────┬──────┘         │      │   │
│  │                                              │                │      │   │
│  │                                              ▼                │      │   │
│  │                                       ┌─────────────┐         │      │   │
│  │                                       │  Replanner  │─────────┘      │   │
│  │                                       │   (LLM)     │ (重规划)       │   │
│  │                                       └──────┬──────┘                │   │
│  │                                              │                       │   │
│  │                                              ▼ (完成)                │   │
│  │                                            [END]                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                    │                                                         │
│                    ▼                                                         │
│  Token 流式输出 ◄── on_chat_model_stream 事件                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

工作流边：
  START ──► Understanding ──► FieldMapper ──► QueryBuilder ──► Execute ──► Insight ──► Replanner
                 │                                                                        │
                 ▼                                                                        │
                END (非分析问题)                                                           │
                 ▲                                                                        │
                 │ (完成)                              (重规划，回到 Understanding)        │
                 └────────────────────────────────────────────────────────────────────────┘
```

## 📁 项目结构

```
tableau-ai-analysis-assistant/
├── tableau_assistant/              # 后端服务
│   ├── src/
│   │   ├── agents/                 # Agent 节点实现
│   │   │   ├── base/               # 基础工具（LLM调用、流式输出、Prompt模板）
│   │   │   ├── understanding/      # 问题理解 Agent（含问题分类）
│   │   │   ├── field_mapper/       # 字段映射 Agent (RAG+LLM 混合)
│   │   │   ├── insight/            # 洞察分析 Agent
│   │   │   ├── replanner/          # 重规划 Agent
│   │   │   └── dimension_hierarchy/# 维度层级 Agent
│   │   │
│   │   ├── nodes/                  # 纯代码节点（无 LLM）
│   │   │   ├── query_builder/      # VizQL 查询构建
│   │   │   │   ├── implementation_resolver.py  # 表计算 vs LOD 决策
│   │   │   │   └── expression_generator.py     # VizQL 表达式生成
│   │   │   └── execute/            # 查询执行
│   │   │
│   │   ├── components/             # 功能组件
│   │   │   └── insight/            # 渐进式洞察分析
│   │   │       ├── coordinator.py  # 分析协调器（主循环）
│   │   │       ├── profiler.py     # 数据画像
│   │   │       ├── statistical_analyzer.py  # 统计/ML 分析
│   │   │       ├── anomaly_detector.py      # 异常检测
│   │   │       ├── chunker.py      # 智能分块
│   │   │       ├── analyzer.py     # LLM 分析
│   │   │       ├── accumulator.py  # 洞察累积
│   │   │       └── synthesizer.py  # 洞察合成
│   │   │
│   │   ├── capabilities/           # 能力模块
│   │   │   ├── rag/                # RAG 语义映射
│   │   │   │   ├── semantic_mapper.py   # 语义映射器
│   │   │   │   ├── field_indexer.py     # 字段索引
│   │   │   │   ├── retriever.py         # 检索器（向量+BM25）
│   │   │   │   ├── reranker.py          # 重排序器
│   │   │   │   └── embeddings.py        # 向量化
│   │   │   ├── storage/            # 持久化存储（SQLite）
│   │   │   ├── date_processing/    # 日期处理
│   │   │   └── data_model/         # 数据模型管理
│   │   │
│   │   ├── bi_platforms/           # BI 平台集成
│   │   │   └── tableau/
│   │   │       ├── auth.py         # JWT/PAT 认证
│   │   │       ├── metadata.py     # 元数据 API
│   │   │       └── vizql_client.py # VizQL Data Service 客户端
│   │   │
│   │   ├── workflow/               # 工作流编排
│   │   │   ├── factory.py          # 工作流创建（含中间件配置）
│   │   │   ├── executor.py         # 执行器（支持流式）
│   │   │   ├── context.py          # 工作流上下文
│   │   │   └── routes.py           # 路由逻辑
│   │   │
│   │   ├── middleware/             # 中间件
│   │   │   ├── filesystem.py       # 大结果自动转存
│   │   │   └── patch_tool_calls.py # 工具调用修复
│   │   │
│   │   ├── model_manager/          # 模型管理
│   │   │   ├── llm.py              # LLM 选择器（支持多提供商）
│   │   │   ├── embeddings.py       # Embedding 提供者
│   │   │   └── reranker.py         # 重排序器
│   │   │
│   │   ├── models/                 # Pydantic 数据模型
│   │   │   ├── semantic/           # 语义层模型（SemanticQuery）
│   │   │   ├── vizql/              # VizQL 模型（VizQLQuery）
│   │   │   ├── field_mapper/       # 字段映射模型
│   │   │   ├── insight/            # 洞察模型
│   │   │   ├── replanner/          # 重规划模型
│   │   │   ├── workflow/           # 工作流状态
│   │   │   └── api/                # API 模型
│   │   │
│   │   ├── tools/                  # LangChain 工具
│   │   │   ├── metadata_tool.py    # 元数据获取
│   │   │   ├── date_tool.py        # 日期处理
│   │   │   ├── schema_tool.py      # Schema 获取
│   │   │   └── data_model_tool.py  # 数据模型工具
│   │   │
│   │   ├── api/                    # FastAPI 端点
│   │   │   ├── chat.py             # 聊天 API（含 SSE 流式）
│   │   │   └── preload.py          # 预加载 API
│   │   │
│   │   ├── services/               # 服务层
│   │   │   └── preload_service.py  # 预加载服务
│   │   │
│   │   └── config/                 # 配置
│   │       ├── settings.py         # 应用配置
│   │       └── model_config.py     # 模型配置
│   │
│   └── tests/                      # 测试
│       ├── unit/                   # 单元测试
│       ├── integration/            # 集成测试
│       └── property/               # 属性测试（Hypothesis）
│
├── tableau_extension/              # 前端扩展（Vue 3 + TypeScript）
│   ├── src/
│   │   ├── components/             # Vue 组件
│   │   ├── views/                  # 页面
│   │   ├── stores/                 # Pinia 状态管理
│   │   ├── api/                    # API 调用
│   │   └── types/                  # TypeScript 类型
│   └── public/                     # 静态资源
│
├── .kiro/specs/                    # 功能规格文档
├── data/                           # 数据目录（缓存、索引）
├── start.py                        # 一键启动脚本
└── .env                            # 环境配置
```


## 🚀 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/PandaHero/tableau-ai-analysis-assistant.git
cd tableau-ai-analysis-assistant

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r tableau_assistant/requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，配置 LLM 和 Tableau 连接
```

关键配置项：
```env
# ========== Tableau 配置 ==========
TABLEAU_DOMAIN=https://your-tableau-server.com
TABLEAU_SITE=your-site
TABLEAU_USER=your-username
DATASOURCE_LUID=your-datasource-luid

# JWT 认证（推荐）
TABLEAU_JWT_CLIENT_ID=your-client-id
TABLEAU_JWT_SECRET_ID=your-secret-id
TABLEAU_JWT_SECRET=your-secret

# PAT 认证（备用）
TABLEAU_PAT_NAME=your-pat-name
TABLEAU_PAT_SECRET=your-pat-secret

# ========== LLM 配置 ==========
LLM_API_BASE=http://your-llm-api/v1
LLM_MODEL_PROVIDER=local  # local/openai/azure/deepseek/zhipu
TOOLING_LLM_MODEL=qwen3
LLM_API_KEY=your-api-key

# DeepSeek（可选）
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_API_KEY=your-deepseek-key

# 智谱 AI（可选）
ZHIPU_API_BASE=https://open.bigmodel.cn/api/paas/v4
ZHIPUAI_API_KEY=your-zhipu-key

# ========== 中间件配置 ==========
SUMMARIZATION_TOKEN_THRESHOLD=20000  # 对话历史总结阈值
MESSAGES_TO_KEEP=10                   # 保留的消息数
MODEL_MAX_RETRIES=3                   # LLM 重试次数
TOOL_MAX_RETRIES=3                    # 工具重试次数
FILESYSTEM_TOKEN_LIMIT=20000          # 大结果转存阈值

# ========== 缓存配置 ==========
METADATA_CACHE_TTL=86400              # 元数据缓存 24 小时
DIMENSION_HIERARCHY_CACHE_TTL=86400   # 维度层级缓存 24 小时

# ========== 重规划配置 ==========
MAX_REPLAN_ROUNDS=3                   # 最大重规划轮数
MAX_SUBTASKS_PER_ROUND=10             # 每轮最大子任务数
```

### 3. 启动服务

```bash
# 一键启动（推荐）
python start.py

# 或手动启动
python -m tableau_assistant.src.main
```

### 4. 测试流式输出

```bash
python -m tableau_assistant.tests.test_streaming
```

## 📡 API 端点

### 流式查询 (推荐)

```
POST /api/chat/stream
Content-Type: application/json

{
    "question": "各产品类别的销售额是多少",
    "datasource_luid": "your-datasource-luid"
}
```

响应：SSE 事件流
```
data: {"event_type": "node_start", "data": {"node": "understanding"}, ...}
data: {"event_type": "token", "data": {"content": "{"}, ...}
data: {"event_type": "token", "data": {"content": "measures"}, ...}
...
data: {"event_type": "node_complete", "data": {"node": "understanding"}, ...}
data: {"event_type": "complete", ...}
```

### 前端使用示例

```javascript
const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        question: '各产品类别的销售额',
        datasource_luid: 'abc123'
    })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const text = decoder.decode(value);
    const lines = text.split('\n');
    
    for (const line of lines) {
        if (line.startsWith('data: ')) {
            const event = JSON.parse(line.slice(6));
            
            if (event.event_type === 'token') {
                // 实时显示 token
                appendToOutput(event.data.content);
            }
        }
    }
}
```

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| Agent 编排 | LangGraph 0.3+ |
| LLM 框架 | LangChain 0.3+ |
| API 框架 | FastAPI |
| 数据验证 | Pydantic v2 |
| 向量检索 | Sentence Transformers |
| 缓存存储 | SQLite (LangGraph Store) |
| BI 平台 | Tableau VizQL Data Service |
| 前端框架 | Vue 3 + TypeScript + Vite |
| 状态管理 | Pinia |

## 📊 工作流节点

| 节点 | 类型 | 功能 | 输入 | 输出 |
|------|------|------|------|------|
| Understanding | LLM | 问题理解、分类 | 用户问题 | SemanticQuery |
| FieldMapper | RAG+LLM | 业务术语 → 技术字段 | SemanticQuery | MappedQuery |
| QueryBuilder | Code | 语义 → VizQL 转换 | MappedQuery | VizQLQuery |
| Execute | Code | 执行 VizQL 查询 | VizQLQuery | ExecuteResult |
| Insight | LLM | 渐进式洞察分析 | ExecuteResult | Insights |
| Replanner | LLM | 完成度评估、探索问题生成 | Insights | ReplanDecision |

## 🔧 中间件

| 中间件 | 功能 |
|--------|------|
| SummarizationMiddleware | 对话历史自动总结（防止上下文溢出） |
| ModelRetryMiddleware | LLM 调用指数退避重试 |
| ToolRetryMiddleware | 工具调用重试 |
| FilesystemMiddleware | 大结果自动转存到文件 |
| PatchToolCallsMiddleware | 修复悬空工具调用 |
| HumanInTheLoopMiddleware | 人工确认（可选） |

## 📈 设计原则

基于 Google、Anthropic、OpenAI 等机构的前沿研究：

### Prompt 设计
- **XML 结构化**：Schema 字段描述使用 XML 标签（`<decision_rule>`、`<fill_order>`）
- **决策树**：用树状决策路径替代依赖矩阵
- **填写顺序**：先简单后复杂，减少 LLM 认知负担

### 架构设计
- **纯语义中间层**：LLM 只输出语义，VizQL 转换由代码完成
- **两阶段字段映射**：向量检索 + LLM 回退
- **渐进式洞察**：AI 驱动的分块分析

### 代码质量
- **Pydantic Validator**：确保 100% 数据验证
- **Property-Based Testing**：使用 Hypothesis 进行属性测试
- **类型注解**：完整的 TypeScript/Python 类型支持

## 🔌 支持的 LLM 提供商

| 提供商 | 配置 |
|--------|------|
| 本地部署 | `LLM_MODEL_PROVIDER=local` |
| OpenAI | `LLM_MODEL_PROVIDER=openai` |
| Azure OpenAI | `LLM_MODEL_PROVIDER=azure` |
| DeepSeek | `LLM_MODEL_PROVIDER=deepseek` |
| 智谱 AI | `LLM_MODEL_PROVIDER=zhipu` |
| 通义千问 | `LLM_MODEL_PROVIDER=qwen` |

## 📄 许可证

[MIT License](LICENSE)

## 👥 作者

- **PandaHero** - [GitHub](https://github.com/PandaHero)

---

**最后更新**: 2025-12-12
**版本**: v2.1.0
