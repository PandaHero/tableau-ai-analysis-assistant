# Tableau AI Analysis Assistant

基于 FastAPI、LangGraph、LangChain 和 Tableau 的数据分析助手后端工程。

当前仓库已经完成 `backend-langgraph-refactor` 主体重构，后端运行主干统一为 `root_graph`，复杂问题与 `why` 问题也已经纳入同一套 root-native 状态机。

## 当前状态

- 后端主干已统一为 `root_graph -> context_graph -> semantic_graph -> query_graph -> answer_graph`
- `interrupt / resume / checkpoint` 已接入正式运行链路
- `retrieval / memory / freshness / rebuild` 已按 spec 收口
- `why / 复杂问题` 已支持 planner、解释轴排序、screening wave、evidence bundle 和统一 final answer/replan
- SSE v2、展示语义、错误码映射和关键合同测试已落地

## 后端架构

### 1. 顶层编排

后端只有一个顶层总控：

```text
root_graph
  -> context_graph
  -> semantic_graph
  -> query_graph / planner_runtime
  -> answer_graph
```

其中：

- `context_graph` 负责 datasource 解析、上下文快照、freshness / degrade
- `semantic_graph` 负责语义解析、retrieval / memory、complex / why planning
- `query_graph` 负责查询编译、高风险闸门、结果物化
- `answer_graph` 负责最终洞察和最终重规划
- `planner_runtime` 负责复杂问题和 `why` 问题的多步执行

### 2. 问题类型

- 简单问题：单轮 `semantic -> query -> answer`
- 复杂但单查可解问题：仍走单轮链，只是语义更复杂
- 复杂多步问题：走 planner DAG
- `why` 问题：走专门的诊断型 planner，包含：
  - `verify_anomaly`
  - `rank_explanatory_axes`
  - `screen_top_axes`
  - `locate_anomalous_slice`
  - `synthesize_cause`

### 3. 最终回答模型

最终 `insight` 和最终 `replan` 已统一基于 `evidence_bundle` 工作：

- 简单问题：单次查询结果打包成 evidence bundle
- 复杂问题：planner synthesis 后的证据包进入 `answer_graph`
- `why` 问题：原因证据链进入 `answer_graph`

## 存储分层

当前后端按职责拆分存储：

- `business_storage`：业务表，如 `sessions / messages / feedback / runs / interrupts`
- `checkpointer`：LangGraph 运行恢复
- `storage`：缓存、memory、metadata 索引
- `vector_storage`：向量检索索引
- `artifacts/`：查询结果、字段索引、manifest、profiles 等文件产物

默认本地配置以 SQLite + FAISS + 文件系统为主，后续可替换为更强的生产后端，而不改业务接口。

## 快速开始

### 1. 准备环境

- Python 3.12+
- Windows 环境默认使用仓库根目录下的 `venv`

### 2. 安装依赖

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

### 3. 配置环境变量

复制环境变量模板并填写真实密钥：

```powershell
Copy-Item .env.example .env
```

主要配置文件：

- `.env`
- `analytics_assistant/config/app.yaml`

### 4. 启动服务

开发模式：

```powershell
venv\Scripts\python.exe start.py
```

只启动后端：

```powershell
venv\Scripts\python.exe start.py --backend-only
```

直接启动 FastAPI：

```powershell
venv\Scripts\python.exe -m analytics_assistant.src.api.main
```

## 测试

运行全部测试：

```powershell
venv\Scripts\pytest.exe
```

运行关键后端链路测试：

```powershell
venv\Scripts\pytest.exe analytics_assistant/tests/orchestration/workflow/test_root_graph_runner.py
venv\Scripts\pytest.exe analytics_assistant/tests/api/routers/test_chat.py
venv\Scripts\pytest.exe analytics_assistant/tests/platform/tableau/test_data_loader.py
```

## 文档入口

- 后端重构 spec 总入口：`analytics_assistant/specs/backend-langgraph-refactor/README.md`
- 当前 `why / complex` 专项说明：
  - `analytics_assistant/specs/backend-langgraph-refactor/why-and-complex-analysis-design.md`
  - `analytics_assistant/specs/backend-langgraph-refactor/why-and-complex-analysis-implementation-notes.md`
- 历史设计资料保留在：
  - `analytics_assistant/docs/`

## 目录概览

```text
analytics_assistant/
  src/
    api/
    orchestration/
    agents/
    platform/
    infra/
  specs/
    backend-langgraph-refactor/
  tests/
  config/
```

## 说明

这个仓库当前以后端重构后的实现为准，不再以 legacy executor 或旧 SSE 兼容路径作为主入口。阅读和继续开发时，优先参考 spec 目录下的重构文档与当前代码实现。
