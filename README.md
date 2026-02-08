# Tableau AI Analysis Assistant

基于 LangGraph 的智能 Tableau 数据分析助手，采用 LLM 组合架构实现语义解析，支持自然语言查询、VizQL 查询生成和智能洞察分析。

## ✨ 核心特性

### 🎯 自然语言查询
- 用自然语言提问，自动生成 VizQL 查询
- 支持中英文混合查询
- 智能识别时间表达式（"上个月"、"去年同期"等）

### 🧠 LLM 组合架构 (Step1 + Step2 + ReAct)
- **Step1 语义理解**：三元模型提取 (What × Where × How)、意图分类
- **Step2 计算推理**：计算类型推断、LLM 自我验证
- **ReAct 错误修正**：智能错误分类、CORRECT/RETRY/CLARIFY 决策

### 🚀 Token 级流式输出
- 实时推送 LLM 生成的每个 token
- SSE (Server-Sent Events) 协议
- 提供流畅的用户体验

### 🔍 RAG 语义字段映射
- 两阶段检索：向量检索 top-K + LLM Rerank
- 高置信度快速路径（≥0.9 直接返回，无需 LLM）
- 字段映射缓存（24小时 TTL，基于 LangGraph SqliteStore）

### 📊 渐进式洞察分析
- **统计分析**：分布检测、异常检测、聚类分析、相关性分析
- **双 LLM 协作**：分析师 + 主持人
- **智能分块**：基于维度层级的优先级分块

### 🏗️ 纯语义中间层
- LLM 只做语义理解，输出平台无关的语义模型
- VizQL 转换由确定性代码完成（100% 语法正确）
- 支持表计算（累计、排名、占比、移动平均、同比环比）
- 支持 LOD 表达式（FIXED、INCLUDE、EXCLUDE）

## 🏗️ 系统架构

### SemanticParser LLM 组合架构

```
用户问题 → Step1 (语义理解) → Step2 (计算推理) → Pipeline (执行)
                ↓                    ↓                ↓
           意图分类            计算类型推断        字段映射→构建→执行
           三元模型提取         自我验证            ↓
           (What/Where/How)                    ReAct (错误修正)
```

### 三元模型 (What × Where × How)

| 元素 | 说明 | 示例 |
|------|------|------|
| What | 度量 + 聚合 | Sales (SUM) |
| Where | 维度 (分组) + 过滤器 (条件) | 维度: City, 过滤器: City="Beijing" |
| How | 计算复杂度 | SIMPLE / COMPLEX |

**Dimension vs Filter 区分**：
- Dimension: 分组字段，用于 "by X", "per X", "for each X"
- Filter: 值约束，用于 "in Beijing", "= X", 日期范围

### 计算类型 (CalcType)

**Table Calculations**:
- RANK, DENSE_RANK, PERCENTILE (排名)
- RUNNING_TOTAL (累计)
- MOVING_CALC (移动计算)
- PERCENT_OF_TOTAL (占比)
- DIFFERENCE, PERCENT_DIFFERENCE (差异/同比环比)

**LOD Expressions**:
- LOD_FIXED, LOD_INCLUDE, LOD_EXCLUDE

## 📁 项目结构

```
tableau-ai-analysis-assistant/
├── tableau_assistant/
│   ├── src/
│   │   ├── agents/                     # Agent 节点
│   │   │   ├── base/                   # Agent 基类和工具
│   │   │   ├── semantic_parser/        # 语义解析 Agent (Step1 + Step2 + ReAct)
│   │   │   │   ├── components/         # Step1, Step2, Pipeline, ReAct 组件
│   │   │   │   ├── models/             # Step1Output, Step2Output, ReActOutput
│   │   │   │   ├── prompts/            # Prompt 模板
│   │   │   │   └── subgraph.py         # LangGraph Subgraph
│   │   │   ├── field_mapper/           # 字段映射 Agent
│   │   │   ├── field_semantic/         # 字段语义推断 Agent (维度+度量)
│   │   │   ├── insight/                # 洞察分析 Agent
│   │   │   │   ├── components/         # Profiler, Coordinator, Analyzer
│   │   │   │   └── models/             # Profile, Insight 模型
│   │   │   └── replanner/              # 重规划 Agent
│   │   │
│   │   ├── nodes/                      # 纯代码节点
│   │   │   ├── query_builder/          # 查询构建
│   │   │   ├── execute/                # 查询执行
│   │   │   └── self_correction/        # 自我修正
│   │   │
│   │   ├── core/                       # 核心层 (平台无关)
│   │   │   ├── models/                 # 语义层数据模型
│   │   │   │   ├── fields.py           # DimensionField, MeasureField
│   │   │   │   ├── filters.py          # SetFilter, DateRangeFilter, ...
│   │   │   │   ├── computations.py     # Computation, CalcParams
│   │   │   │   ├── enums.py            # CalcType, HowType, IntentType
│   │   │   │   └── query.py            # VizQLQuery
│   │   │   ├── interfaces/             # 抽象接口
│   │   │   └── exceptions.py           # 异常定义
│   │   │
│   │   ├── platforms/                  # 平台适配层
│   │   │   └── tableau/                # Tableau 平台实现
│   │   │       ├── models/             # TableCalc, LODExpression
│   │   │       ├── query_builder.py    # 查询构建器
│   │   │       ├── field_mapper.py     # 字段映射器
│   │   │       ├── vizql_client.py     # VizQL API 客户端
│   │   │       └── auth.py             # JWT/PAT 认证
│   │   │
│   │   ├── orchestration/              # 编排层
│   │   │   ├── workflow/               # 工作流定义
│   │   │   ├── middleware/             # 中间件栈
│   │   │   └── tools/                  # LangChain 工具
│   │   │
│   │   ├── infra/                      # 基础设施层
│   │   │   ├── ai/                     # LLM/Embedding/RAG
│   │   │   ├── storage/                # 存储 (缓存、索引)
│   │   │   ├── config/                 # 配置管理
│   │   │   ├── certs/                  # 证书管理
│   │   │   └── monitoring/             # 监控日志
│   │   │
│   │   └── api/                        # FastAPI 端点
│   │
│   ├── tests/                          # 测试
│   │   ├── unit/                       # 单元测试
│   │   └── integration/                # 集成测试
│   │
│   └── docs/                           # 文档
│
├── data/                               # 数据目录 (缓存、索引)
├── start.py                            # 一键启动脚本
└── .env                                # 环境配置
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
DATASOURCE_LUID=your-datasource-luid

# JWT 认证（推荐）
TABLEAU_JWT_CLIENT_ID=your-client-id
TABLEAU_JWT_SECRET_ID=your-secret-id
TABLEAU_JWT_SECRET=your-secret

# ========== LLM 配置 ==========
LLM_API_BASE=http://your-llm-api/v1
LLM_MODEL_PROVIDER=local
TOOLING_LLM_MODEL=qwen3
LLM_API_KEY=your-api-key
```

### 3. 启动服务

```bash
# 一键启动（推荐）
python start.py

# 或手动启动
python -m tableau_assistant.src.main
```

## 📡 API 端点

### 流式查询

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
data: {"event_type": "node_start", "data": {"node": "step1"}, ...}
data: {"event_type": "token", "data": {"content": "{"}, ...}
...
data: {"event_type": "complete", ...}
```

### 预热 API

```
POST /api/preload/dimension-hierarchy
Content-Type: application/json

{
    "datasource_luid": "your-datasource-luid"
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
| 缓存存储 | LangGraph SqliteStore |
| BI 平台 | Tableau VizQL Data Service |

## 📋 Prompt 与 Model 规范

遵循 `docs/PROMPT_AND_MODEL_GUIDE.md` 规范：

**核心原则**：
- Prompt 教 LLM 如何思考，Schema 告诉 LLM 输出什么
- 信息去重：每种信息只在最相关位置出现一次
- 全英文 docstring

**XML 标签规范**：
- Class docstring: `<fill_order>`, `<examples>` (≤2), `<anti_patterns>` (≤3)
- Field description: `<what>`, `<when>`, `<rule>`, `<dependency>`, `<must_not>`
- Enum docstring: `<rule>` (选择逻辑) 或一行格式 (值含义)

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行集成测试
pytest tableau_assistant/tests/integration/

# 运行 SemanticParser 测试
pytest tableau_assistant/tests/integration/test_semantic_parser_subgraph.py
```

## 🔌 支持的 LLM 提供商

| 提供商 | 配置 |
|--------|------|
| 本地部署 | `LLM_MODEL_PROVIDER=local` |
| OpenAI | `LLM_MODEL_PROVIDER=openai` |
| Azure OpenAI | `LLM_MODEL_PROVIDER=azure` |
| DeepSeek | `LLM_MODEL_PROVIDER=deepseek` |
| 智谱 AI | `LLM_MODEL_PROVIDER=zhipu` |

## 📄 许可证

[MIT License](LICENSE)

## 👥 作者

- **PandaHero** - [GitHub](https://github.com/PandaHero)

---

**版本**: v2.3.0 | **更新**: 2024-12-29
