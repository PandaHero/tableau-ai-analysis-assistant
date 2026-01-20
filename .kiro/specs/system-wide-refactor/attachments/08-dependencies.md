# 附件 8：依赖和配置

本文档列出项目的关键依赖和配置示例。

## Python 依赖

### pyproject.toml

```toml
[tool.poetry]
name = "analytics-assistant"
version = "2.0.0"
description = "Analytics Assistant - 通用 BI 分析助手平台"
authors = ["Your Team <team@example.com>"]

[tool.poetry.dependencies]
python = "^3.10"

# Web 框架
fastapi = "^0.104.0"
uvicorn = {extras = ["standard"], version = "^0.24.0"}

# LangChain/LangGraph
langchain = "^0.1.0"
langgraph = "^0.0.20"
langchain-openai = "^0.0.2"
langchain-anthropic = "^0.0.1"

# 数据验证
pydantic = "^2.5.0"
pydantic-settings = "^2.1.0"

# AI/ML
openai = "^1.3.0"
anthropic = "^0.7.0"
sentence-transformers = "^2.2.0"
transformers = "^4.35.0"
torch = "^2.1.0"

# 向量存储
chromadb = "^0.4.0"
faiss-cpu = "^1.7.4"

# 存储（基于 LangGraph SqliteStore，无需 Redis）
sqlalchemy = "^2.0.0"

# Tableau
tableauserverclient = "^0.25.0"

# 日志和监控
structlog = "^23.2.0"
prometheus-client = "^0.19.0"
opentelemetry-api = "^1.21.0"
opentelemetry-sdk = "^1.21.0"
opentelemetry-instrumentation-fastapi = "^0.42b0"
opentelemetry-exporter-otlp = "^1.21.0"

# 测试
pytest = "^7.4.0"
pytest-asyncio = "^0.21.0"
pytest-cov = "^4.1.0"
hypothesis = "^6.92.0"

# 代码质量
black = "^23.12.0"
ruff = "^0.1.0"
mypy = "^1.7.0"

[tool.poetry.group.dev.dependencies]
ipython = "^8.18.0"
jupyter = "^1.0.0"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

---

## 配置文件示例

### development.yaml

```yaml
# 开发环境配置

environment: development

# API 配置
api:
  host: "0.0.0.0"
  port: 8000
  debug: true
  reload: true

# 模型配置
models:
  default_llm: "gpt-4"
  default_embedding: "text-embedding-3-small"
  
  # OpenAI
  openai:
    api_key: "${OPENAI_API_KEY}"
    api_base: "https://api.openai.com/v1"
    
  # 自定义模型
  custom:
    api_key: "${CUSTOM_LLM_API_KEY}"
    api_base: "${CUSTOM_LLM_API_BASE}"
    model_name: "custom-model"

# Tableau 配置
tableau:
  server_url: "https://tableau.example.com"
  token_name: "${TABLEAU_TOKEN_NAME}"
  token_value: "${TABLEAU_TOKEN_VALUE}"

# 存储配置（基于 LangGraph SqliteStore）
storage:
  sqlite_path: "data/langgraph_store.db"
  backup_enabled: true
  backup_interval_hours: 24

# 缓存配置
cache:
  ttl_seconds: 3600
  max_size: 10000
  backend: "sqlite"  # 使用 LangGraph SqliteStore

# 性能配置
performance:
  max_concurrent_requests: 10
  request_timeout_seconds: 30
  
# 日志配置
logging:
  level: "DEBUG"
  format: "console"  # console | json
  
# 监控配置
monitoring:
  enabled: true
  prometheus_port: 9090
  tracing_enabled: true
```

### production.yaml

```yaml
# 生产环境配置

environment: production

# API 配置
api:
  host: "0.0.0.0"
  port: 8000
  debug: false
  reload: false

# 模型配置
models:
  default_llm: "gpt-4"
  default_embedding: "text-embedding-3-small"
  
  openai:
    api_key: "${OPENAI_API_KEY}"
    api_base: "https://api.openai.com/v1"

# Tableau 配置
tableau:
  server_url: "${TABLEAU_SERVER_URL}"
  token_name: "${TABLEAU_TOKEN_NAME}"
  token_value: "${TABLEAU_TOKEN_VALUE}"

# Redis 配置
redis:
  url: "${REDIS_URL}"
  db: 0
  password: "${REDIS_PASSWORD}"

# 缓存配置
cache:
  ttl_seconds: 7200
  max_size: 100000

# 性能配置
performance:
  max_concurrent_requests: 100
  request_timeout_seconds: 60
  
# 日志配置
logging:
  level: "INFO"
  format: "json"
  
# 监控配置
monitoring:
  enabled: true
  prometheus_port: 9090
  tracing_enabled: true
  alerting_enabled: true
```

---

## 环境变量

### .env.example

```bash
# 环境
ENVIRONMENT=development

# OpenAI
OPENAI_API_KEY=sk-xxx

# 自定义 LLM
CUSTOM_LLM_API_KEY=xxx
CUSTOM_LLM_API_BASE=https://api.example.com/v1
CUSTOM_LLM_MODEL_NAME=custom-model

# 智谱 AI
ZHIPUAI_API_KEY=xxx

# Tableau
TABLEAU_SERVER_URL=https://tableau.example.com
TABLEAU_TOKEN_NAME=token-name
TABLEAU_TOKEN_VALUE=token-value

# Redis
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=

# 数据库
DATABASE_URL=sqlite:///./data/langgraph_store.db

# 日志
LOG_LEVEL=INFO
LOG_FORMAT=json

# 监控
PROMETHEUS_PORT=9090
TRACING_ENABLED=true
```

---

## Docker 配置

### Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源代码
COPY src/ ./src/
COPY config/ ./config/
COPY start.py .

# 暴露端口
EXPOSE 8000 9090

# 启动命令
CMD ["python", "start.py"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
      - "9090:9090"
    environment:
      - ENVIRONMENT=production
      - SQLITE_PATH=/app/data/langgraph_store.db
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    restart: unless-stopped

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9091:9090"
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
```

---

## CI/CD 配置

### .github/workflows/ci.yml

```yaml
name: CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.10'
    
    - name: Install dependencies
      run: |
        pip install poetry
        poetry install
    
    - name: Run linters
      run: |
        poetry run black --check src/
        poetry run ruff check src/
        poetry run mypy src/
    
    - name: Run tests
      run: |
        poetry run pytest tests/ --cov=src --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml

  build:
    runs-on: ubuntu-latest
    needs: test
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Build Docker image
      run: docker build -t analytics-assistant:${{ github.sha }} .
    
    - name: Push to registry
      if: github.ref == 'refs/heads/main'
      run: |
        echo "${{ secrets.DOCKER_PASSWORD }}" | docker login -u "${{ secrets.DOCKER_USERNAME }}" --password-stdin
        docker push analytics-assistant:${{ github.sha }}
```

---

## 总结

本文档提供了：

✅ **完整的依赖列表**：Python 包和版本  
✅ **配置文件示例**：开发和生产环境  
✅ **环境变量模板**：所有必需的环境变量  
✅ **Docker 配置**：容器化部署  
✅ **CI/CD 配置**：自动化测试和部署  

这些配置文件可以直接使用或根据实际需求调整。
