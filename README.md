# Tableau AI Analysis Assistant

基于 LangGraph 的智能 Tableau 数据分析助手，支持自然语言查询、语义字段映射和 VizQL 查询生成。

## 🚀 项目状态

**当前阶段**：Agent 重构 + RAG 增强 - 设计阶段

- ✅ 需求文档完成
- ✅ 详细设计文档完成
- ✅ Prompt 模板和数据模型编写指南完成（基于前沿研究）
- ⏳ 纯语义中间层设计中

## 📋 功能特性

### 核心功能
- **自然语言查询**：使用自然语言提问，自动生成 VizQL 查询
- **语义字段映射**：基于 RAG 的智能字段映射系统（向量检索 + LLM 判断）
- **纯语义中间层**：LLM 只做语义理解，VizQL 技术转换由确定性代码完成
- **表计算支持**：累计、移动平均、排名、占比、同比环比等
- **LOD 表达式**：支持不同粒度的聚合计算

### 设计原则
基于 Google、Anthropic、OpenAI 等机构的前沿研究：
- **XML 结构化**：Schema 字段描述使用 XML 标签（Anthropic 研究）
- **决策树**：用树状决策路径替代依赖矩阵（Google Tree of Thoughts）
- **填写顺序**：先简单后复杂（Google Least-to-Most Prompting）
- **位置敏感**：关键信息放开头/结尾（Lost in the Middle 研究）
- **代码级验证**：Pydantic Validator 确保 100% 可靠（Calibration 研究）

## 📚 文档

### 规范文档
- [Prompt 模板和数据模型编写指南](tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md) - **核心规范**

### 设计文档
- [需求文档](.kiro/specs/agent-refactor-with-rag/requirements.md)
- [设计文档](.kiro/specs/agent-refactor-with-rag/design.md)
- [纯语义中间层设计](.kiro/specs/agent-refactor-with-rag/design-appendix-semantic-layer.md)
- [Prompt 设计](.kiro/specs/agent-refactor-with-rag/design-appendix-prompts.md)
- [数据模型设计](.kiro/specs/agent-refactor-with-rag/design-appendix-data-models.md)
- [QueryBuilder 设计](.kiro/specs/agent-refactor-with-rag/design-appendix-query-builder.md)

## 🏗️ 项目结构

```
tableau-ai-analysis-assistant/
├── .kiro/specs/                      # 设计文档
│   └── agent-refactor-with-rag/      # 当前重构设计
│       ├── requirements.md           # 需求文档
│       ├── design.md                 # 设计文档
│       └── design-appendix-*.md      # 详细设计文档
├── tableau_assistant/                # 主应用
│   ├── docs/                         # 文档
│   │   └── PROMPT_AND_MODEL_GUIDE.md # Prompt和数据模型编写指南
│   ├── prompts/                      # Prompt 模板
│   │   ├── understanding.py          # 问题理解 Prompt
│   │   ├── field_mapping.py          # 字段映射 Prompt
│   │   └── modules/                  # 动态模块化 Prompt
│   ├── src/
│   │   ├── agents/                   # Agent 实现
│   │   │   └── nodes/                # LangGraph 节点
│   │   ├── capabilities/             # 能力模块
│   │   │   ├── rag/                  # RAG 语义映射
│   │   │   └── metadata/             # 元数据管理
│   │   ├── bi_platforms/             # BI 平台集成
│   │   │   └── tableau/              # Tableau 集成
│   │   ├── models/                   # Pydantic 数据模型
│   │   └── model_manager/            # 模型管理器
│   └── tests/                        # 测试
│       ├── unit/                     # 单元测试
│       └── integration/              # 集成测试
└── README.md                         # 本文件
```

## 🛠️ 技术栈

- **Python 3.10+**
- **LangGraph** - Agent 编排框架
- **LangChain** - LLM 应用框架
- **Anthropic Claude / OpenAI GPT** - LLM 模型
- **Sentence Transformers** - 向量嵌入
- **SQLite** - 向量缓存存储
- **Pydantic** - 数据验证和 Schema 生成
- **VizQL Data Service** - Tableau 数据查询

## 📦 安装

```bash
# 克隆仓库
git clone https://github.com/PandaHero/tableau-ai-analysis-assistant.git
cd tableau-ai-analysis-assistant

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入必要的配置
```

## 🚀 快速开始

```bash
# 启动服务
python start.py

# 访问 API 文档
# http://localhost:8000/docs
```

## 📐 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    自然语言 → VizQL 查询转换流程                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  用户问题 (自然语言)                                                          │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 1: Understanding Agent (纯语义理解层) - LLM                   │    │
│  │  输出: SemanticQuery (纯语义，无 VizQL 概念)                         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 2: FieldMapper (RAG + LLM 混合字段映射)                       │    │
│  │  输出: 业务术语 → 技术字段名 映射                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Stage 3-6: 确定性代码转换                                           │    │
│  │  ImplementationResolver → ExpressionGenerator → QueryBuilder         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│       │                                                                      │
│       ▼                                                                      │
│  VizQL Data Service API 调用                                                 │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 📈 设计原则（15条）

基于前沿研究的设计原则，详见 [PROMPT_AND_MODEL_GUIDE.md](tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md)：

| # | 原则 | 核心思想 | 研究来源 |
|---|------|---------|---------|
| 1 | 最小激活 | 高密度关键词 | Sparse Attention |
| 2 | 正交分解 | 独立决策 | 认知科学 |
| 3 | 语义一致 | 统一术语 | Instruction Tuning |
| 4 | 渐进约束 | 先理解后结构化 | CoT |
| 5 | ICL本质 | 模式激活 | Meta研究 |
| 6 | 信息瓶颈 | 保留相关信息 | 信息论 |
| 7 | MDL | 最短描述 | 信息论 |
| 8 | XML结构化 | 显式边界标记 | Anthropic |
| 9 | 位置敏感 | 开头/结尾高注意力 | Lost in the Middle |
| 10 | 决策树 | 树状决策路径 | Tree of Thoughts |
| 11 | 填写顺序 | 先简单后复杂 | Least-to-Most |
| 12 | 选项限制 | ≤7个选项 | 工作记忆 |
| 13 | 双向显式 | 正反关系都说明 | Reversal Curse |
| 14 | 外部验证 | 代码级验证 | Calibration |
| 15 | 格式标准化 | 统一格式 | Prompt Sensitivity |

## 🤝 贡献

欢迎贡献！请查看设计文档了解当前进度和待完成任务。

## 📄 许可证

[MIT License](LICENSE)

## 👥 作者

- **PandaHero** - [GitHub](https://github.com/PandaHero)

---

**最后更新**: 2024-12-04
**版本**: v2.0.0-alpha
