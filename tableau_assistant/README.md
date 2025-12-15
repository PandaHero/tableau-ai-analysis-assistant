# Tableau Assistant Backend

基于 LangGraph + LangChain 的智能数据分析后端，集成 Tableau VizQL Data Service 和企业级中间件栈。

## 技术栈

- Python 3.12+
- LangGraph 0.3+
- LangChain 0.3+
- FastAPI
- Pydantic v2
- SQLite (StoreManager)
- Tableau VizQL Data Service
- JWT/PAT Authentication

## 项目结构

```
tableau_assistant/
├── src/
│   ├── agents/                 # 6 个 Agent 节点
│   ├── nodes/                  # 纯代码节点
│   ├── components/insight/     # 渐进式洞察分析
│   ├── workflow/               # 工作流核心
│   ├── middleware/             # 自定义中间件
│   ├── capabilities/           # RAG、存储、日期处理
│   ├── bi_platforms/tableau/   # Tableau 集成
│   ├── services/               # 预热服务
│   ├── model_manager/          # LLM/Embedding 管理
│   ├── models/                 # Pydantic 数据模型
│   ├── tools/                  # LangChain 工具
│   ├── api/                    # FastAPI 端点
│   └── config/                 # 配置
├── cert_manager/               # SSL 证书管理
├── tests/                      # 测试
└── docs/                       # 文档
```

## 快速开始

```bash
# 一键启动
python start.py

# 或手动启动
pip install -r requirements.txt
python -m tableau_assistant.src.main
```

## 核心组件

### WorkflowContext

统一的依赖容器：

```python
ctx = WorkflowContext(auth=auth_ctx, store=store, datasource_luid="ds_123")
ctx = await ctx.ensure_metadata_loaded()
```

### 中间件栈（8 层）

| 中间件 | 功能 |
|--------|------|
| TodoListMiddleware | 任务队列管理 |
| SummarizationMiddleware | 对话历史总结 |
| ModelRetryMiddleware | LLM 重试 |
| ToolRetryMiddleware | 工具重试 |
| FilesystemMiddleware | 大结果转存 |
| PatchToolCallsMiddleware | 工具调用修复 |
| OutputValidationMiddleware | 输出校验 |
| HumanInTheLoopMiddleware | 人工确认 |

### 渐进式洞察（双 LLM 协作）

- Phase 1: 统计/ML 分析
- Phase 2: 分析师 + 主持人 LLM

## API 端点

| 端点 | 说明 |
|------|------|
| `/api/chat/stream` | 流式查询 |
| `/api/preload/dimension-hierarchy` | 预热 |
| `/api/health` | 健康检查 |

---

**版本**: v2.2.0 | **更新**: 2024-12-14
