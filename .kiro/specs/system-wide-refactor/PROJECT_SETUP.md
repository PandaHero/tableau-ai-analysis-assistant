# Analytics Assistant 项目初始化指南

## 项目概述

**项目名称**：`analytics-assistant`

**项目定位**：通用 BI 分析助手平台
- 目前实现：Tableau 平台支持
- 未来扩展：Power BI、Looker 等其他 BI 平台

**重要决策**：
- ✅ 创建全新项目目录 `analytics-assistant/`
- ✅ 不修改原始 `tableau_assistant/` 代码
- ✅ 从现有代码迁移和重构到新项目

---

## 初始目录结构

```
analytics-assistant/
├── src/                          # 源代码根目录
│   ├── __init__.py
│   ├── api/                      # API 层
│   ├── core/                     # Core 层（核心领域层）
│   ├── platform/                 # Platform 层（平台适配层）
│   ├── agents/                   # Agent 层（智能体层）
│   ├── orchestration/            # Orchestration 层（编排层）
│   ├── infra/                    # Infrastructure 层（基础设施层）
│   └── main.py                   # 应用入口
│
├── tests/                        # 测试目录
│   ├── unit/                     # 单元测试
│   ├── property/                 # 属性测试
│   └── integration/              # 集成测试
│
├── data/                         # 数据目录
│   ├── indexes/                  # 索引文件
│   └── langgraph_store.db        # LangGraph 持久化存储
│
├── docs/                         # 文档
│   ├── architecture.md           # 架构文档
│   ├── api.md                    # API 文档
│   └── development.md            # 开发指南
│
├── scripts/                      # 脚本
│   ├── seed_data.py              # 种子数据生成
│   └── build_indexes.py          # 索引构建脚本
│
├── config/                       # 配置文件
│   ├── development.yaml          # 开发环境配置
│   └── production.yaml           # 生产环境配置
│
├── frontend/                     # 前端代码（Vue.js）
│   ├── src/
│   ├── public/
│   └── package.json
│
├── .env.example                  # 环境变量示例
├── .gitignore                    # Git 忽略文件
├── requirements.txt              # Python 依赖
├── pyproject.toml                # 项目配置
├── pytest.ini                    # Pytest 配置
└── README.md                     # 项目说明
```

详细的目录结构请参考：[附件 7：目录结构](./attachments/07-directory-structure.md)

---

## 初始化步骤

### 1. 创建项目根目录

```bash
mkdir analytics-assistant
cd analytics-assistant
```

### 2. 创建基础目录结构

```bash
# 源代码目录
mkdir -p src/{api,core,platform,agents,orchestration,infra}
mkdir -p src/core/{models,interfaces}
mkdir -p src/platform/tableau
mkdir -p src/agents/{base,semantic_parser,field_mapper,dimension_hierarchy,insight,replanner}
mkdir -p src/orchestration/{workflow,middleware}
mkdir -p src/infra/{ai,rag,storage,config,observability}

# 测试目录
mkdir -p tests/{unit,property,integration}

# 数据目录
mkdir -p data/indexes

# 文档目录
mkdir -p docs

# 脚本目录
mkdir -p scripts

# 配置目录
mkdir -p config

# 前端目录（如果需要）
mkdir -p frontend
```

### 3. 创建 Python 包初始化文件

```bash
# 创建所有 __init__.py 文件
find src -type d -exec touch {}/__init__.py \;
find tests -type d -exec touch {}/__init__.py \;
```

### 4. 创建配置文件

#### pyproject.toml

```toml
[tool.poetry]
name = "analytics-assistant"
version = "0.1.0"
description = "通用 BI 分析助手平台 - 基于 LangChain/LangGraph"
authors = ["Your Name <your.email@example.com>"]
readme = "README.md"
packages = [{include = "src"}]

[tool.poetry.dependencies]
python = "^3.11"
langchain = "^0.1.0"
langgraph = "^0.1.0"
fastapi = "^0.109.0"
uvicorn = "^0.27.0"
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"
httpx = "^0.26.0"
faiss-cpu = "^1.7.4"
chromadb = "^0.4.22"
openai = "^1.10.0"
structlog = "^24.1.0"
prometheus-client = "^0.19.0"
opentelemetry-api = "^1.22.0"
opentelemetry-sdk = "^1.22.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.4.4"
pytest-asyncio = "^0.23.3"
pytest-cov = "^4.1.0"
hypothesis = "^6.98.0"
black = "^24.1.1"
ruff = "^0.1.14"
mypy = "^1.8.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
addopts = "-v --cov=src --cov-report=html --cov-report=term"

[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

#### .env.example

```bash
# LLM 配置
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# Embedding 配置
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

# 存储配置
STORAGE_BACKEND=sqlite
SQLITE_DB_PATH=data/langgraph_store.db

# 向量数据库配置
VECTOR_DB=faiss
FAISS_INDEX_PATH=data/indexes/

# Tableau 配置
TABLEAU_SERVER_URL=https://your-tableau-server.com
TABLEAU_USERNAME=your_username
TABLEAU_PASSWORD=your_password

# 日志配置
LOG_LEVEL=INFO
LOG_FORMAT=json

# API 配置
API_HOST=0.0.0.0
API_PORT=8000
```

#### .gitignore

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
ENV/
env/
.venv

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.hypothesis/

# Data
data/*.db
data/indexes/*
!data/indexes/.gitkeep

# Environment
.env
.env.local

# Logs
*.log
logs/

# OS
.DS_Store
Thumbs.db
```

### 5. 创建 README.md

```markdown
# Analytics Assistant

通用 BI 分析助手平台 - 基于 LangChain/LangGraph

## 项目概述

Analytics Assistant 是一个通用的 BI 分析助手平台，通过自然语言理解用户的分析需求，自动生成查询并提供洞察。

**当前支持**：
- Tableau 平台

**未来扩展**：
- Power BI
- Looker
- 其他 BI 平台

## 架构特点

- **五层架构**：Core → Platform → Agent → Orchestration → API
- **基于 LangChain/LangGraph**：利用成熟的 LLM 编排框架
- **模块化设计**：清晰的分层和接口定义
- **可扩展性**：易于添加新的 BI 平台支持

## 快速开始

### 安装依赖

```bash
# 使用 Poetry
poetry install

# 或使用 pip
pip install -r requirements.txt
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的配置
```

### 运行开发服务器

```bash
python src/main.py
```

### 运行测试

```bash
pytest
```

## 文档

- [架构设计](docs/architecture.md)
- [API 文档](docs/api.md)
- [开发指南](docs/development.md)

## 许可证

[Your License]
```

---

## 下一步

1. ✅ 项目目录结构已规划
2. ✅ 配置文件模板已准备
3. 🔄 **待执行**：创建实际的项目目录和文件
4. 🔄 **待执行**：开始阶段 1 - 基础设施层重构

---

## 参考文档

- [需求文档](./requirements.md)
- [设计文档](./design.md)
- [任务清单](./tasks.md)
- [目录结构详细说明](./attachments/07-directory-structure.md)
