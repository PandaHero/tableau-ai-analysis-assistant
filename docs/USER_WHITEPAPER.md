# Tableau AI Analysis Assistant 用户白皮书

## 产品概述

**Tableau AI Analysis Assistant** 是一款基于大语言模型（LLM）和 LangGraph 框架的智能数据分析助手，专为 Tableau 用户设计。它允许用户通过自然语言与数据进行对话，自动生成 VizQL 查询，并提供深度数据洞察分析。

### 核心价值

| 价值点 | 描述 |
|--------|------|
| 🎯 自然语言交互 | 用中文或英文提问，无需学习 VizQL 语法 |
| ⚡ 实时流式响应 | Token 级流式输出，即时看到分析过程 |
| 🔍 智能字段映射 | 自动将业务术语映射到技术字段 |
| 📊 深度洞察分析 | AI 驱动的多维度数据洞察 |
| 🔄 渐进式探索 | 自动生成探索问题，深入挖掘数据价值 |

---

## 目录

1. [功能详解](#功能详解)
2. [系统架构](#系统架构)
3. [使用指南](#使用指南)
4. [技术特性](#技术特性)
5. [部署配置](#部署配置)
6. [常见问题](#常见问题)

---

## 功能详解

### 1. 自然语言查询

#### 1.1 基础查询

用户可以使用自然语言提出数据分析问题：

**支持的查询类型**：

| 查询类型 | 示例 | 说明 |
|---------|------|------|
| 简单聚合 | "各产品类别的销售额是多少" | 按维度分组，计算度量 |
| 多维分析 | "各省份各月的销售额趋势" | 多维度交叉分析 |
| 筛选查询 | "2024年华东地区的销售额" | 带条件筛选 |
| 排名分析 | "销售额前10的产品" | TOP N 分析 |
| 占比分析 | "各产品类别销售额占比" | 百分比计算 |
| 同比环比 | "各月销售额同比增长率" | 时间对比分析 |
| 累计计算 | "按月累计销售额" | 累计值计算 |
| 移动平均 | "销售额3个月移动平均" | 滑动窗口计算 |

#### 1.2 智能时间表达式

系统自动识别并解析中文时间表达式：

| 表达式 | 解析结果 |
|--------|---------|
| "上个月" | 自动计算上月日期范围 |
| "去年同期" | 自动计算去年同期日期 |
| "最近3个月" | 自动计算最近3个月范围 |
| "2024年Q1" | 2024-01-01 至 2024-03-31 |
| "本周" | 自动计算本周日期范围 |

#### 1.3 意图分类

系统自动识别用户意图并进行智能路由：

| 意图类型 | 描述 | 处理方式 |
|---------|------|---------|
| DATA_QUERY | 数据查询请求 | 执行完整分析流程 |
| CLARIFICATION | 需要澄清的问题 | 返回澄清问题 |
| GENERAL | 一般性问题（如字段说明） | 直接回答 |
| IRRELEVANT | 与数据分析无关 | 友好提示 |

---

### 2. 智能字段映射（RAG + LLM）

#### 2.1 三级映射策略

系统采用三级策略确保字段映射的准确性和效率：

```
业务术语 → [缓存查找] → 命中? → 返回结果
              ↓ 未命中
         [RAG 检索] → 置信度 ≥ 0.9? → 快速返回
              ↓ 置信度 < 0.9
         [LLM 选择] → 从候选中选择最佳匹配
```

**策略说明**：

| 策略 | 触发条件 | 响应时间 | 准确率 |
|------|---------|---------|--------|
| 缓存命中 | 24小时内查询过 | < 10ms | 100% |
| RAG 快速路径 | 置信度 ≥ 0.9 | < 100ms | > 95% |
| LLM 回退 | 置信度 < 0.9 | < 2s | > 90% |

#### 2.2 支持的映射场景

| 场景 | 示例 | 说明 |
|------|------|------|
| 同义词 | "销售额" → "Sales Amount" | 中英文同义词 |
| 缩写 | "GMV" → "Gross Merchandise Value" | 业务缩写 |
| 别名 | "营收" → "Revenue" | 业务别名 |
| 模糊匹配 | "销售" → "Sales Amount" | 部分匹配 |
| 上下文消歧 | "金额"（销售上下文）→ "Sales Amount" | 基于上下文 |

---

### 3. 渐进式洞察分析

#### 3.1 分析流程

系统采用"AI 宝宝吃饭"模式进行渐进式分析：

```
┌─────────────────────────────────────────────────────────────┐
│                    渐进式洞察分析流程                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Phase 1: 统计分析（无 LLM）                                 │
│  ├─ 数据画像：分布、异常值、缺失值                           │
│  ├─ 异常检测：Z-Score、IQR 方法                             │
│  ├─ 聚类分析：K-Means 自动分群                              │
│  └─ 帕累托分析：80/20 法则识别                              │
│                                                              │
│  Phase 2: LLM 分析（双 LLM 协作）                            │
│  ├─ 分析师 LLM：生成数据洞察                                │
│  └─ 主持人 LLM：评估完成度，决定是否继续                     │
│                                                              │
│  Phase 3: 智能分块                                           │
│  ├─ 基于维度层级的优先级分块                                 │
│  └─ 大数据集自动分批处理                                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### 3.2 洞察类型

| 洞察类型 | 描述 | 示例 |
|---------|------|------|
| 趋势洞察 | 时间序列趋势分析 | "销售额呈上升趋势，月均增长5%" |
| 异常洞察 | 异常值识别 | "3月销售额异常偏高，超出均值2个标准差" |
| 对比洞察 | 维度间对比 | "华东地区销售额占比最高，达35%" |
| 关联洞察 | 维度关联分析 | "高端产品在一线城市销售更好" |
| 预测洞察 | 趋势预测 | "按当前趋势，Q4销售额预计达到..." |

---

### 4. 智能重规划

#### 4.1 重规划机制

系统自动评估分析完成度，生成探索问题：

```
┌─────────────────────────────────────────────────────────────┐
│                    重规划决策流程                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  评估当前洞察 → 计算完成度分数 (0-1)                         │
│       │                                                      │
│       ├─ 完成度 ≥ 0.8 → 分析完成，结束                       │
│       │                                                      │
│       └─ 完成度 < 0.8 → 识别缺失方面                         │
│              │                                               │
│              ├─ 基于维度层级生成下钻问题                     │
│              ├─ 基于数据特征生成探索问题                     │
│              └─ 按优先级排序，执行下一轮分析                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

#### 4.2 探索问题类型

| 类型 | 描述 | 示例 |
|------|------|------|
| 下钻分析 | 从高层级到低层级 | "华东地区各省份的销售额" |
| 上卷分析 | 从低层级到高层级 | "各大区的销售额汇总" |
| 切片分析 | 固定某维度值 | "2024年各产品类别销售额" |
| 对比分析 | 不同维度值对比 | "华东 vs 华南销售额对比" |
| 时间分析 | 时间维度深入 | "销售额的月度趋势" |

---

### 5. 高级计算支持

#### 5.1 表计算

| 计算类型 | 语法示例 | 说明 |
|---------|---------|------|
| 累计 | "按月累计销售额" | RUNNING_SUM |
| 排名 | "销售额排名" | RANK |
| 占比 | "销售额占比" | PERCENT_OF_TOTAL |
| 移动平均 | "3个月移动平均" | WINDOW_AVG |
| 同比 | "销售额同比增长" | YoY |
| 环比 | "销售额环比增长" | MoM |

#### 5.2 LOD 表达式

| 表达式类型 | 语法示例 | 说明 |
|-----------|---------|------|
| FIXED | "各产品的品类总销售额" | 固定维度计算 |
| INCLUDE | "包含子类别的销售额" | 包含额外维度 |
| EXCLUDE | "排除日期的销售额" | 排除某维度 |

---

### 6. 流式输出

#### 6.1 SSE 事件流

系统支持 Token 级流式输出，提供实时反馈：

**事件类型**：

| 事件类型 | 描述 | 数据内容 |
|---------|------|---------|
| `node_start` | 节点开始执行 | 节点名称 |
| `token` | LLM 生成的 token | token 内容 |
| `node_complete` | 节点执行完成 | 节点输出 |
| `insight` | 洞察生成 | 洞察内容 |
| `complete` | 分析完成 | 完整结果 |
| `error` | 错误发生 | 错误信息 |

#### 6.2 前端集成示例

```javascript
// 使用 EventSource 接收流式响应
const eventSource = new EventSource('/api/chat/stream');

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch (data.event_type) {
        case 'token':
            // 实时显示 token
            appendToOutput(data.content);
            break;
        case 'insight':
            // 显示洞察
            displayInsight(data.insight);
            break;
        case 'complete':
            // 分析完成
            showFinalResult(data.result);
            break;
    }
};
```

---

## 系统架构

### 整体架构图

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
│  │  ┌─────────────────────────────────────────────────────────────┐     │   │
│  │  │                    Middleware Stack (8 层)                   │     │   │
│  │  │  TodoList → Summarization → ModelRetry → ToolRetry →        │     │   │
│  │  │  Filesystem → PatchToolCalls → OutputValidation → HITL      │     │   │
│  │  └─────────────────────────────────────────────────────────────┘     │   │
│  │                                                                       │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │   │
│  │  │SemanticParser───►│FieldMapper │───►│QueryBuilder │              │   │
│  │  │   (LLM)     │    │ (RAG+LLM)  │    │   (Code)    │              │   │
│  │  └──────┬──────┘    └─────────────┘    └──────┬──────┘              │   │
│  │         │                                     │                     │   │
│  │         │ (非分析问题)                         ▼                     │   │
│  │         │                             ┌─────────────┐               │   │
│  │         ▼                             │   Execute   │               │   │
│  │       [END]                           │   (VizQL)   │               │   │
│  │                                       └──────┬──────┘               │   │
│  │                                              │                      │   │
│  │                                              ▼                      │   │
│  │                                       ┌─────────────┐               │   │
│  │                                       │   Insight   │               │   │
│  │                                       │ (双LLM协作) │               │   │
│  │                                       └──────┬──────┘               │   │
│  │                                              │                      │   │
│  │                                              ▼                      │   │
│  │                                       ┌─────────────┐               │   │
│  │                                       │  Replanner  │───────────────┘   │
│  │                                       │   (LLM)     │ (重规划)          │
│  │                                       └──────┬──────┘                   │
│  │                                              │                          │
│  │                                              ▼ (完成)                   │
│  │                                            [END]                        │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                    │                                                         │
│                    ▼                                                         │
│  Token 流式输出 ◄── on_chat_model_stream 事件                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 工作流节点说明

| 节点 | 类型 | 功能 | 输入 | 输出 |
|------|------|------|------|------|
| SemanticParser | LLM Agent | 语义解析、意图分类 | 用户问题 | SemanticQuery |
| FieldMapper | RAG+LLM | 业务术语→技术字段 | SemanticQuery | MappedQuery |
| QueryBuilder | Pure Code | 语义→VizQL 转换 | MappedQuery | VizQLQuery |
| Execute | Pure Code | 执行 VizQL 查询 | VizQLQuery | QueryResult |
| Insight | 双LLM | 渐进式洞察分析 | QueryResult | Insights |
| Replanner | LLM Agent | 完成度评估、探索问题 | Insights | ReplanDecision |

---

## 使用指南

### 快速开始

#### 1. 环境准备

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

#### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件
```

**关键配置项**：

```env
# ========== Tableau 配置 ==========
TABLEAU_DOMAIN=https://your-tableau-server.com
TABLEAU_SITE=your-site
TABLEAU_USER=your-username
DATASOURCE_LUID=your-datasource-luid

# JWT 认证（推荐）
TABLEAU_JWT_CLIENT_ID=your-client-id
TABLEAU_JWT_SECRET_ID=your-secret-id
TABLEAU_JWT_SECRET=your-secret

# ========== LLM 配置 ==========
LLM_API_BASE=http://your-llm-api/v1
LLM_MODEL_PROVIDER=local  # local/openai/deepseek/zhipu
TOOLING_LLM_MODEL=qwen3
LLM_API_KEY=your-api-key
```

#### 3. 启动服务

```bash
# 一键启动（推荐）
python start.py

# 开发模式（热重载）
python start.py --dev

# 生产模式
python start.py --prod
```

### API 使用

#### 流式查询 API

```http
POST /api/chat/stream
Content-Type: application/json

{
    "question": "各产品类别的销售额是多少",
    "datasource_luid": "your-datasource-luid"
}
```

**响应**：SSE 事件流

```
data: {"event_type": "node_start", "data": {"node": "semantic_parser"}}
data: {"event_type": "token", "data": {"content": "正在分析..."}}
data: {"event_type": "insight", "data": {"content": "销售额最高的是..."}}
data: {"event_type": "complete", "data": {"result": {...}}}
```

#### 健康检查 API

```http
GET /api/health
```

**响应**：

```json
{
    "status": "healthy",
    "checks": {
        "llm": {"status": "ok"},
        "tableau": {"status": "ok"},
        "storage": {"status": "ok"}
    }
}
```

---

## 技术特性

### 1. 企业级中间件栈

| 中间件 | 功能 | 说明 |
|--------|------|------|
| SummarizationMiddleware | 对话历史自动总结 | 防止上下文溢出 |
| ModelRetryMiddleware | LLM 调用重试 | 指数退避，最多3次 |
| ToolRetryMiddleware | 工具调用重试 | 自动重试失败的工具 |
| OutputValidationMiddleware | 输出验证 | JSON/Schema 校验 |
| FilesystemMiddleware | 大结果转存 | 超过阈值自动保存文件 |
| PatchToolCallsMiddleware | 工具调用修复 | 修复悬空工具调用 |

### 2. 多 LLM 提供商支持

| 提供商 | 配置值 | 说明 |
|--------|--------|------|
| 本地部署 | `local` | Ollama 等本地模型 |
| OpenAI | `openai` | GPT-4, GPT-3.5 |
| Azure OpenAI | `azure` | Azure 托管 |
| DeepSeek | `deepseek` | DeepSeek Chat |
| 智谱 AI | `zhipu` | GLM-4 |
| 通义千问 | `qwen` | Qwen 系列 |

### 3. 缓存系统

| 缓存类型 | TTL | 说明 |
|---------|-----|------|
| 元数据缓存 | 24小时 | 数据源字段信息 |
| 字段映射缓存 | 24小时 | 业务术语→技术字段 |
| 维度层级缓存 | 24小时 | 维度层级关系 |
| LLM 响应缓存 | 可配置 | 相同问题缓存结果 |

### 4. 安全特性

| 特性 | 说明 |
|------|------|
| JWT 认证 | 支持 Tableau JWT 认证 |
| PAT 认证 | 支持个人访问令牌 |
| SSL/TLS | 支持 HTTPS |
| 证书管理 | 自动证书获取和热重载 |

---

## 部署配置

### 环境变量完整列表

```env
# ========== Tableau 配置 ==========
TABLEAU_DOMAIN=https://your-tableau-server.com
TABLEAU_SITE=your-site
TABLEAU_API_VERSION=3.24
TABLEAU_USER=your-username
DATASOURCE_LUID=your-datasource-luid

# JWT 认证
TABLEAU_JWT_CLIENT_ID=your-client-id
TABLEAU_JWT_SECRET_ID=your-secret-id
TABLEAU_JWT_SECRET=your-secret

# PAT 认证（备用）
TABLEAU_PAT_NAME=your-pat-name
TABLEAU_PAT_SECRET=your-pat-secret

# ========== LLM 配置 ==========
LLM_API_BASE=http://your-llm-api/v1
LLM_MODEL_PROVIDER=local
TOOLING_LLM_MODEL=qwen3
LLM_API_KEY=your-api-key
LLM_TEMPERATURE=0.2

# DeepSeek（可选）
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_API_KEY=your-deepseek-key

# 智谱 AI（可选）
ZHIPU_API_BASE=https://open.bigmodel.cn/api/paas/v4
ZHIPUAI_API_KEY=your-zhipu-key

# ========== 中间件配置 ==========
SUMMARIZATION_TOKEN_THRESHOLD=20000
MESSAGES_TO_KEEP=10
MODEL_MAX_RETRIES=3
TOOL_MAX_RETRIES=3
FILESYSTEM_TOKEN_LIMIT=20000

# ========== 缓存配置 ==========
METADATA_CACHE_TTL=86400
DIMENSION_HIERARCHY_CACHE_TTL=86400

# ========== 重规划配置 ==========
MAX_REPLAN_ROUNDS=3
MAX_SUBTASKS_PER_ROUND=10

# ========== API 配置 ==========
HOST=127.0.0.1
PORT=8000
CORS_ORIGINS=https://localhost:5173

# ========== VizQL 配置 ==========
VIZQL_RETURN_FORMAT=OBJECTS
VIZQL_TIMEOUT=30
VIZQL_MAX_RETRIES=3
DECIMAL_PRECISION=2
```

### Docker 部署

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install -r tableau_assistant/requirements.txt

EXPOSE 8000

CMD ["python", "start.py", "--prod"]
```

```bash
# 构建和运行
docker build -t tableau-assistant .
docker run -p 8000:8000 --env-file .env tableau-assistant
```

---

## 常见问题

### Q1: 如何提高字段映射准确率？

**A**: 
1. 确保数据源字段有清晰的描述
2. 使用标准的业务术语
3. 提供上下文信息（如"销售相关的金额"）
4. 检查缓存是否过期

### Q2: 为什么分析速度较慢？

**A**:
1. 首次查询需要加载元数据（后续会缓存）
2. 复杂问题需要多轮 LLM 调用
3. 检查 LLM API 响应时间
4. 考虑使用更快的 LLM 模型

### Q3: 如何处理大数据集？

**A**:
1. 系统自动进行智能分块
2. 使用筛选条件缩小数据范围
3. 调整 `FILESYSTEM_TOKEN_LIMIT` 参数

### Q4: 支持哪些 Tableau 版本？

**A**:
- Tableau Server 2021.4+
- Tableau Cloud
- 需要启用 VizQL Data Service API

### Q5: 如何自定义 LLM 模型？

**A**:
1. 修改 `.env` 中的 `LLM_MODEL_PROVIDER`
2. 配置对应的 API 密钥
3. 可选：调整 `LLM_TEMPERATURE` 参数

---

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|---------|
| v2.2.0 | 2024-12-21 | 新增证书管理、多环境支持 |
| v2.1.0 | 2024-12-14 | 优化 RAG 检索、新增维度层级推断 |
| v2.0.0 | 2024-12-01 | 重构为 LangGraph 架构 |
| v1.0.0 | 2024-11-01 | 初始版本 |

---

## 联系与支持

- **GitHub**: [PandaHero/tableau-ai-analysis-assistant](https://github.com/PandaHero/tableau-ai-analysis-assistant)
- **文档**: 项目 `docs/` 目录
- **问题反馈**: GitHub Issues

---

*文档版本: v2.2.0*
*最后更新: 2024-12-22*
