# Tableau AI Analysis Assistant

基于 LangChain DeepAgents 的智能 Tableau 数据分析助手，支持自然语言查询、多轮对话和渐进式洞察生成。

## 🚀 项目状态

**当前阶段**：DeepAgent重构 - 设计阶段完成

- ✅ 需求文档完成
- ✅ 详细设计文档完成（15个文档）
- ✅ 任务分解完成（120+任务，10周工期）
- ⏳ 准备开始实施

## 📋 功能特性

### 核心功能
- **自然语言查询**：使用自然语言提问，自动生成VizQL查询
- **多轮对话**：支持上下文理解和多轮交互
- **智能字段映射**：基于RAG的语义字段映射系统
- **渐进式洞察**：大数据集的智能分块分析和早停机制
- **四层缓存**：Prompt Caching + Application Cache + Query Cache + Semantic Cache

### 技术架构
- **框架**：LangChain DeepAgents
- **子代理**：5个专业子代理（boost, understanding, planning, insight, replanner）
- **中间件**：3个自定义中间件（Metadata, VizQL, Cache）
- **工具**：8个Tableau工具封装

## 📚 文档

### 设计文档
- [需求文档](.kiro/specs/deepagents-refactor/requirements.md)
- [设计文档](.kiro/specs/deepagents-refactor/design.md)
- [任务列表](.kiro/specs/deepagents-refactor/tasks.md)

### 详细设计
- [字段语义推断系统](.kiro/specs/deepagents-refactor/design-appendix/field-semantics.md)
- [Task Planner与RAG集成](.kiro/specs/deepagents-refactor/design-appendix/task-planner-rag-integration.md)
- [渐进式洞察系统](.kiro/specs/deepagents-refactor/design-appendix/progressive-insights.md)
- [缓存系统设计](.kiro/specs/deepagents-refactor/design-appendix/caching-system.md)
- [API设计](.kiro/specs/deepagents-refactor/design-appendix/api-design.md)
- [更多设计文档...](.kiro/specs/deepagents-refactor/design-appendix/)

## 🏗️ 项目结构

```
tableau-ai-analysis-assistant/
├── .kiro/specs/deepagents-refactor/  # 设计文档
│   ├── requirements.md               # 需求文档
│   ├── design.md                     # 设计文档
│   ├── tasks.md                      # 任务列表
│   └── design-appendix/              # 详细设计文档
├── tableau_assistant/                # 主应用
│   ├── src/
│   │   ├── deepagents/              # DeepAgents实现
│   │   │   ├── subagents/           # 子代理
│   │   │   ├── middleware/          # 中间件
│   │   │   └── tools/               # 工具
│   │   ├── semantic_mapping/        # 语义映射
│   │   ├── progressive_insight/     # 渐进式洞察
│   │   ├── models/                  # 数据模型
│   │   └── components/              # 现有组件
│   └── tests/                       # 测试
└── README.md                        # 本文件
```

## 🛠️ 技术栈

- **Python 3.10+**
- **LangChain DeepAgents** - Agent编排框架
- **LangChain** - LLM应用框架
- **Anthropic Claude** - 主要LLM模型
- **FAISS** - 向量存储
- **SQLite** - 持久化存储
- **FastAPI** - API服务
- **Tableau REST API** - Tableau集成

## 📦 安装

```bash
# 克隆仓库
git clone https://github.com/PandaHero/tableau-ai-analysis-assistant.git
cd tableau-ai-analysis-assistant

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r tableau_assistant/requirements.txt

# 配置环境变量
cp tableau_assistant/.env.example tableau_assistant/.env
# 编辑 .env 文件，填入必要的配置
```

## 🚀 快速开始

```bash
# 启动开发服务器
python start.py

# 访问API文档
# http://localhost:8000/docs
```

## 📈 开发路线图

### 阶段1：基础架构（2天）
- [x] 项目结构重组
- [x] DeepAgents配置
- [x] 数据模型适配

### 阶段2：工具层（5.5天）
- [x] 核心工具封装（4个已完成）
- [ ] RAG语义映射工具
- [ ] 辅助工具封装

### 阶段3-10：详见 [tasks.md](.kiro/specs/deepagents-refactor/tasks.md)

**总工期**：约10周（69天）

## 🤝 贡献

欢迎贡献！请查看 [任务列表](.kiro/specs/deepagents-refactor/tasks.md) 了解当前进度和待完成任务。

## 📄 许可证

[MIT License](LICENSE)

## 👥 作者

- **PandaHero** - [GitHub](https://github.com/PandaHero)

## 🙏 致谢

- LangChain团队提供的优秀框架
- Anthropic提供的Claude模型
- Tableau提供的强大数据可视化平台

---

**最后更新**: 2025-01-15
**版本**: v1.0.0-alpha
