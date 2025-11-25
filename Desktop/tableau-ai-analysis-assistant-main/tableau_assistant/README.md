# VizQL Multi-Agent Backend

基于LangChain + LangGraph的多智能体查询与分析系统后端，集成了Tableau数据源查询和分析功能。

## 技术栈

- Python 3.12+
- LangChain 0.3.21
- LangGraph 0.3.21
- FastAPI
- Pydantic
- Redis (缓存)
- Tableau VizQL Data Service
- JWT Authentication

## 项目结构

```
tableau_assistant/
├── src/                    # 源代码
│   ├── agents/            # 7个Agent实现
│   ├── components/        # 6个纯代码组件
│   ├── models/            # Pydantic数据模型
│   ├── api/               # FastAPI路由
│   ├── utils/             # 工具函数
│   │   └── tableau/       # Tableau集成工具
│   │       ├── auth.py           # JWT认证
│   │       ├── metadata.py       # 元数据API
│   │       ├── vizql_data_service.py  # VDS查询
│   │       ├── models.py         # LLM模型选择
│   │       ├── utils.py          # HTTP工具
│   │       └── simple_datasource_qa.py  # 数据源QA工具
│   ├── tools/             # LangChain工具
│   │   ├── prompts.py            # VDS查询提示词
│   │   └── simple_datasource_qa.py  # 数据源QA工具
│   └── config/            # 配置文件
├── tests/                 # 测试代码
├── docs/                  # 项目文档
└── requirements.txt       # Python依赖
```

## 快速开始

### 一键启动（推荐）

使用项目根目录的启动脚本，自动完成环境设置和服务启动：

```bash
python start.py
```

启动脚本会自动：
1. 检查Python版本（需要3.12+）
2. 创建虚拟环境（如果不存在）
3. 安装所有依赖
4. 验证环境配置
5. 启动FastAPI服务器

### 手动启动

如果需要手动控制每个步骤：

1. 激活虚拟环境：
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置环境变量：
```bash
cp .env.example .env
# 编辑.env文件，填入你的配置
```

必需的环境变量：
- `TABLEAU_DOMAIN`: Tableau服务器地址
- `TABLEAU_JWT_CLIENT_ID`: JWT客户端ID
- `TABLEAU_JWT_SECRET_ID`: JWT密钥ID
- `TABLEAU_JWT_SECRET`: JWT密钥
- `TABLEAU_USER`: Tableau用户名
- `DATASOURCE_LUID`: 数据源LUID
- `LLM_API_BASE`: LLM API地址
- `MODEL_PROVIDER`: 模型提供商（local/openai/azure）
- `TOOLING_MODEL`: 用于查询生成的模型

4. 运行开发服务器：
```bash
python src/main.py
```

## 开发指南

参见 [docs/development.md](docs/development.md)


## Tableau集成功能

本项目集成了Tableau的实验性工具和实用程序，提供以下功能：

### 认证
- JWT Connected App认证
- 自动token缓存（10分钟）
- 支持多种访问范围

### 元数据查询
- 通过LUID或名称查询数据源
- 获取字段元数据（类型、角色、聚合等）
- GraphQL API集成
- **智能字段精简**：
  - 自动去除隐藏字段
  - 仅保留必要信息（name, role, dataType, dataCategory, aggregation）
  - 智能去重：删除被计算字段引用的原始字段
  - 减少60-70%的元数据体积，优化LLM处理效率

### VizQL Data Service
- 自然语言查询转换为VDS查询
- 支持复杂过滤器（日期、数值、集合、Top N等）
- 自动查询优化和错误重试

### LangChain工具
- `simple_datasource_qa`: 数据源问答工具
- 支持相对日期查询（上周、本月、去年等）
- 智能字段映射和聚合

## API端点

启动服务器后，可以访问：

- **API文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health
- **根路径**: http://localhost:8000/

## 配置说明

### 模型提供商

支持三种LLM提供商：

1. **local**: 本地部署的OpenAI兼容API
   ```env
   MODEL_PROVIDER=local
   LLM_API_BASE=http://localhost:8000/v1
   LLM_API_KEY=your-api-key
   ```

2. **openai**: OpenAI官方API
   ```env
   MODEL_PROVIDER=openai
   OPENAI_API_KEY=your-openai-key
   ```

3. **azure**: Azure OpenAI服务
   ```env
   MODEL_PROVIDER=azure
   AZURE_OPENAI_API_KEY=your-azure-key
   AZURE_OPENAI_API_INSTANCE_NAME=your-instance
   ```

### Tableau配置

需要配置Tableau Connected App：

1. 在Tableau Server/Online中创建Connected App
2. 获取Client ID、Secret ID和Secret
3. 在.env中配置相应的值
4. 确保用户有足够的权限访问数据源

