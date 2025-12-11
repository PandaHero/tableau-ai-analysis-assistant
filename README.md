# Tableau AI Analysis Assistant

基于 LangGraph 的智能 Tableau 数据分析助手，支持自然语言查询、语义字段映射、VizQL 查询生成和智能洞察分析。

## ✨ 核心特性

- **自然语言查询** - 用自然语言提问，自动生成 VizQL 查询
- **Token 级流式输出** - 实时推送 LLM 生成的每个 token，提供流畅的用户体验
- **RAG 语义字段映射** - 向量检索 + LLM 混合匹配，高置信度快速路径
- **纯语义中间层** - LLM 只做语义理解，VizQL 转换由确定性代码完成
- **智能洞察分析** - 自动分析查询结果，生成数据洞察
- **智能重规划** - 评估分析完成度，自动生成探索问题

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
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐               │   │
│  │  │Understanding│───►│FieldMapper │───►│QueryBuilder │               │   │
│  │  │   (LLM)     │    │ (RAG+LLM)  │    │   (Code)    │               │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘               │   │
│  │         │                                     │                       │   │
│  │         │           ┌─────────────┐           │                       │   │
│  │         │           │  Replanner  │◄──────────┤                       │   │
│  │         │           │   (LLM)     │           │                       │   │
│  │         │           └─────────────┘           │                       │   │
│  │         │                  │                  ▼                       │   │
│  │         │           ┌─────────────┐    ┌─────────────┐               │   │
│  │         └──────────►│   Insight   │◄───│   Execute   │               │   │
│  │                     │   (LLM)     │    │   (Code)    │               │   │
│  │                     └─────────────┘    └─────────────┘               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                    │                                                         │
│                    ▼                                                         │
│  Token 流式输出 ◄── on_chat_model_stream 事件                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 📁 项目结构

```
tableau_assistant/
├── src/
│   ├── agents/                    # Agent 节点实现
│   │   ├── base/                  # 基础工具（LLM调用、流式输出）
│   │   ├── understanding/         # 问题理解 Agent
│   │   ├── field_mapper/          # 字段映射 Agent (RAG+LLM)
│   │   ├── insight/               # 洞察分析 Agent
│   │   └── replanner/             # 重规划 Agent
│   │
│   ├── nodes/                     # 纯代码节点
│   │   ├── query_builder/         # VizQL 查询构建
│   │   └── execute/               # 查询执行
│   │
│   ├── workflow/                  # 工作流编排
│   │   ├── factory.py             # 工作流创建
│   │   ├── executor.py            # 执行器（支持流式）
│   │   └── routes.py              # 路由逻辑
│   │
│   ├── api/                       # FastAPI 端点
│   │   └── chat.py                # 聊天 API（含 SSE 流式）
│   │
│   ├── capabilities/              # 能力模块
│   │   ├── rag/                   # RAG 语义映射
│   │   ├── storage/               # 缓存存储
│   │   └── date_processing/       # 日期处理
│   │
│   ├── models/                    # Pydantic 数据模型
│   │   ├── semantic/              # 语义层模型
│   │   ├── vizql/                 # VizQL 模型
│   │   ├── workflow/              # 工作流状态
│   │   └── api/                   # API 模型
│   │
│   ├── middleware/                # 中间件
│   │   ├── filesystem.py          # 大结果自动转存
│   │   └── patch_tool_calls.py    # 工具调用修复
│   │
│   ├── model_manager/             # 模型管理
│   │   ├── llm.py                 # LLM 选择器
│   │   ├── embeddings.py          # Embedding 提供者
│   │   └── reranker.py            # 重排序器
│   │
│   └── tools/                     # LangChain 工具
│       ├── metadata_tool.py       # 元数据获取
│       ├── date_tool.py           # 日期处理
│       └── schema_tool.py         # Schema 获取
│
└── tests/                         # 测试
    ├── test_streaming.py          # 流式输出测试
    └── integration/               # 集成测试
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
# LLM 配置
LLM_API_BASE=http://your-llm-api/v1
LLM_MODEL_PROVIDER=local
TOOLING_LLM_MODEL=qwen3

# Tableau 配置
TABLEAU_DOMAIN=https://your-tableau-server.com
TABLEAU_SITE=your-site
DATASOURCE_LUID=your-datasource-luid
```

### 3. 启动服务

```bash
python start.py
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
| Agent 编排 | LangGraph 1.0 |
| LLM 框架 | LangChain |
| API 框架 | FastAPI |
| 数据验证 | Pydantic v2 |
| 向量检索 | Sentence Transformers |
| 缓存存储 | SQLite |
| BI 平台 | Tableau VizQL Data Service |

## 📊 工作流节点

| 节点 | 类型 | 功能 |
|------|------|------|
| Understanding | LLM | 问题理解，输出 SemanticQuery |
| FieldMapper | RAG+LLM | 业务术语 → 技术字段映射 |
| QueryBuilder | Code | SemanticQuery → VizQL 转换 |
| Execute | Code | 执行 VizQL 查询 |
| Insight | LLM | 分析结果，生成洞察 |
| Replanner | LLM | 评估完成度，生成探索问题 |

## 🔧 中间件

- **SummarizationMiddleware** - 对话历史自动总结
- **ModelRetryMiddleware** - LLM 调用指数退避重试
- **ToolRetryMiddleware** - 工具调用重试
- **FilesystemMiddleware** - 大结果自动转存
- **PatchToolCallsMiddleware** - 修复悬空工具调用

## 📈 设计原则

基于 Google、Anthropic、OpenAI 等机构的前沿研究：

- **XML 结构化** - Schema 字段描述使用 XML 标签
- **决策树** - 用树状决策路径替代依赖矩阵
- **填写顺序** - 先简单后复杂
- **代码级验证** - Pydantic Validator 确保 100% 可靠

## 📄 许可证

[MIT License](LICENSE)

## 👥 作者

- **PandaHero** - [GitHub](https://github.com/PandaHero)

---

**最后更新**: 2025-12-11
**版本**: v2.1.0
