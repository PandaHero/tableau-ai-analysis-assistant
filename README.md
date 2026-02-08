# Analytics Assistant

基于 LangGraph 的智能数据分析助手，采用多 Agent 组合架构实现语义解析，支持自然语言查询、VizQL 查询生成和智能洞察分析。当前适配 Tableau 平台，架构设计支持扩展到其他 BI 平台。

## ✨ 核心特性

### 🎯 自然语言查询
- 用自然语言提问，自动生成 VizQL 查询
- 支持中英文混合查询
- 智能识别时间表达式（"上个月"、"去年同期"等）

### 🧠 多 Agent 组合架构
- **SemanticParser Agent**：三元模型提取 (What × Where × How)、意图分类、计算推理、ReAct 错误修正
- **FieldMapper Agent**：RAG 两阶段检索（向量 top-K + LLM Rerank），高置信度快速路径
- **FieldSemantic Agent**：字段语义推断（维度/度量分类），种子匹配 + LLM 批量推断

### 🚀 Token 级流式输出
- 实时推送 LLM 生成的每个 token
- SSE (Server-Sent Events) 协议

### 🔍 RAG 语义字段映射
- 两阶段检索：向量检索 top-K + LLM Rerank
- 高置信度快速路径（≥0.9 直接返回，无需 LLM）
- 字段映射缓存（基于 LangGraph SqliteStore）

### 🏗️ 纯语义中间层
- LLM 只做语义理解，输出平台无关的语义模型
- VizQL 转换由确定性代码完成（100% 语法正确）
- 支持表计算（累计、排名、占比、移动平均、同比环比）
- 支持 LOD 表达式（FIXED、INCLUDE、EXCLUDE）

## 🏗️ 系统架构

### 三元模型 (What × Where × How)

| 元素 | 说明 | 示例 |
|------|------|------|
| What | 度量 + 聚合 | Sales (SUM) |
| Where | 维度 (分组) + 过滤器 (条件) | 维度: City, 过滤器: City="Beijing" |
| How | 计算复杂度 | SIMPLE / COMPLEX |

### 计算类型 (CalcType)

**Table Calculations**: RANK, RUNNING_TOTAL, MOVING_CALC, PERCENT_OF_TOTAL, DIFFERENCE 等

**LOD Expressions**: LOD_FIXED, LOD_INCLUDE, LOD_EXCLUDE

## 📁 项目结构

```
analytics-assistant/
├── analytics_assistant/
│   ├── config/                         # 配置文件
│   │   └── app.yaml                    # 统一应用配置
│   ├── src/
│   │   ├── agents/                     # Agent 模块（LangGraph 工作流）
│   │   │   ├── base/                   # Agent 基础设施（node.py, middleware_runner.py）
│   │   │   ├── semantic_parser/        # 语义解析 Agent (Step1 + Step2 + ReAct)
│   │   │   │   ├── components/         # 业务组件
│   │   │   │   ├── prompts/            # Prompt 模板
│   │   │   │   ├── schemas/            # 数据模型
│   │   │   │   ├── seeds/              # 种子数据
│   │   │   │   ├── graph.py            # LangGraph 图定义
│   │   │   │   └── state.py            # State 定义
│   │   │   ├── field_mapper/           # 字段映射 Agent
│   │   │   │   ├── prompts/
│   │   │   │   ├── schemas/
│   │   │   │   └── node.py
│   │   │   └── field_semantic/         # 字段语义推断 Agent
│   │   │       ├── components/
│   │   │       ├── prompts/
│   │   │       ├── schemas/
│   │   │       └── inference.py
│   │   │
│   │   ├── core/                       # 核心模块（接口、异常、通用 Schema）
│   │   │   ├── schemas/                # 通用数据模型
│   │   │   ├── interfaces.py           # 抽象接口定义
│   │   │   └── exceptions.py           # 自定义异常
│   │   │
│   │   ├── infra/                      # 基础设施
│   │   │   ├── ai/                     # LLM、Embedding 封装
│   │   │   ├── storage/                # 存储（SqliteStore、缓存）
│   │   │   ├── config/                 # 配置管理
│   │   │   ├── rag/                    # RAG 检索
│   │   │   └── seeds/                  # 全局种子数据
│   │   │
│   │   ├── orchestration/              # 工作流编排
│   │   │   └── workflow/               # WorkflowContext
│   │   │
│   │   └── platform/                   # 平台适配器
│   │       ├── base.py                 # 平台注册表和工厂
│   │       └── tableau/                # Tableau 平台实现
│   │
│   ├── tests/                          # 测试
│   │   ├── agents/                     # Agent 模块测试
│   │   ├── integration/                # 集成测试
│   │   └── manual/                     # 手动测试脚本
│   │
│   ├── public/                         # Tableau Extension 静态资源
│   └── data/                           # 数据目录（缓存、索引、证书）
│
├── .env                                # 环境变量配置
├── pytest.ini                          # 测试配置
└── start.py                            # 启动脚本
```

## 🚀 快速开始

### 1. 安装依赖

```bash
git clone https://github.com/PandaHero/tableau-ai-analysis-assistant.git
cd tableau-ai-analysis-assistant

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 配置

**环境变量** — 复制并编辑 `.env`：

```bash
cp .env.example .env
```

关键配置项：
```env
# Tableau 连接
TABLEAU_DOMAIN=https://your-tableau-server.com
TABLEAU_SITE=your-site
TABLEAU_JWT_CLIENT_ID=your-client-id
TABLEAU_JWT_SECRET_ID=your-secret-id
TABLEAU_JWT_SECRET=your-secret

# LLM 配置
ACTIVE_LLM=deepseek          # 可选: deepseek-r1 | deepseek | qwen3
LLM_API_BASE=https://api.deepseek.com
LLM_API_KEY=your-api-key

# Embedding 配置
ZHIPUAI_API_KEY=your-zhipu-api-key
```

**应用配置** — 编辑 `analytics_assistant/config/app.yaml`：

阈值、超时、缓存 TTL、RAG 参数等运行时配置统一在 `app.yaml` 中管理，参考 `app.example.yaml`。

### 3. 启动服务

```bash
python start.py
```

## 🛠️ 技术栈

| 组件 | 技术 |
|------|------|
| Agent 编排 | LangGraph 0.3+ |
| LLM 框架 | LangChain 0.3+ |
| API 框架 | FastAPI |
| 数据验证 | Pydantic v2 |
| 向量检索 | FAISS + Sentence Transformers |
| 缓存存储 | LangGraph SqliteStore |
| BI 平台 | Tableau VizQL Data Service |
| Embedding | 智谱 AI |
| LLM | DeepSeek / DeepSeek-R1 / Qwen3 |

## 🧪 测试

```bash
# 运行所有测试
pytest

# 运行集成测试
pytest analytics_assistant/tests/integration/

# 运行指定 Agent 测试
pytest analytics_assistant/tests/agents/
```

测试配置见 `pytest.ini`，PYTHONPATH 已自动设置。

## 🔌 支持的 LLM

| 提供商 | ACTIVE_LLM | 说明 |
|--------|------------|------|
| DeepSeek R1 (私有部署) | `deepseek-r1` | 公司内部部署，推理模型 |
| DeepSeek (官方) | `deepseek` | DeepSeek 官方 API |
| Qwen3 (私有部署) | `qwen3` | 公司内部部署 |

通过 `.env` 中的 `ACTIVE_LLM` 切换，对应的 API 地址和密钥自动生效。

## 📐 编码规范

项目遵循严格的编码规范，详见 `.kiro/steering/coding-standards.md`，核心要点：

- 所有导入在文件顶部，禁止延迟导入
- 配置参数统一放 `app.yaml`，禁止硬编码
- Prompt 放 `prompts/`，Schema 放 `schemas/`
- 使用 `typing` 模块泛型（`List[str]` 而非 `list[str]`）
- 复用 `infra/` 基础设施，禁止重复造轮子

## 📄 许可证

[MIT License](LICENSE)

## 👥 作者

- **PandaHero** - [GitHub](https://github.com/PandaHero)

---

**版本**: v3.0.0 | **更新**: 2026-02-08
