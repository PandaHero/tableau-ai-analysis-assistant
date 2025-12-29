# Tableau Assistant Backend

基于 LangGraph + LangChain 的智能数据分析后端，集成 Tableau VizQL Data Service，采用 LLM 组合架构实现语义解析。

## 技术栈

- Python 3.12+
- LangGraph 0.3+
- LangChain 0.3+
- FastAPI
- Pydantic v2
- SQLite (LangGraph SqliteStore)
- Tableau VizQL Data Service
- JWT/PAT Authentication

## 项目结构

```
tableau_assistant/
├── src/
│   ├── agents/                     # Agent 节点
│   │   ├── base/                   # Agent 基类和工具
│   │   ├── semantic_parser/        # 语义解析 Agent (Step1 + Step2 + ReAct)
│   │   ├── field_mapper/           # 字段映射 Agent
│   │   ├── dimension_hierarchy/    # 维度层级 Agent
│   │   ├── insight/                # 洞察分析 Agent
│   │   └── replanner/              # 重规划 Agent
│   ├── nodes/                      # 纯代码节点
│   │   ├── query_builder/          # 查询构建
│   │   ├── execute/                # 查询执行
│   │   └── self_correction/        # 自我修正
│   ├── core/                       # 核心层
│   │   ├── models/                 # 平台无关数据模型
│   │   ├── interfaces/             # 抽象接口
│   │   └── exceptions.py           # 异常定义
│   ├── platforms/                  # 平台适配层
│   │   └── tableau/                # Tableau 平台实现
│   ├── orchestration/              # 编排层
│   │   ├── workflow/               # 工作流定义
│   │   ├── middleware/             # 中间件栈
│   │   └── tools/                  # LangChain 工具
│   ├── infra/                      # 基础设施层
│   │   ├── ai/                     # LLM/Embedding/RAG
│   │   ├── storage/                # 存储 (缓存、索引)
│   │   ├── config/                 # 配置管理
│   │   ├── certs/                  # 证书管理
│   │   └── monitoring/             # 监控日志
│   └── api/                        # FastAPI 端点
├── tests/                          # 测试
└── docs/                           # 文档
```

## 快速开始

```bash
# 一键启动
python start.py

# 或手动启动
pip install -r requirements.txt
python -m tableau_assistant.src.main
```

## 核心架构

### SemanticParser LLM 组合架构

采用 Step1 + Step2 + ReAct 三阶段架构：

```
用户问题 → Step1 (语义理解) → Step2 (计算推理) → Pipeline (执行)
                ↓                    ↓                ↓
           意图分类            计算类型推断        字段映射→构建→执行
           三元模型提取         自我验证            ↓
           (What/Where/How)                    ReAct (错误修正)
```

**Step1 输出模型**：
- `restated_question`: 重述问题 (英文)
- `what`: 度量 (MeasureField)
- `where`: 维度 + 过滤器 (DimensionField + Filter)
- `how_type`: SIMPLE | COMPLEX
- `intent`: DATA_QUERY | CLARIFICATION | GENERAL | IRRELEVANT

**Step2 输出模型** (仅 COMPLEX 触发)：
- `computations`: 计算定义列表
- `validation`: LLM 自我验证结果

**计算类型 (CalcType)**：
- Table Calculations: RANK, RUNNING_TOTAL, MOVING_CALC, PERCENT_OF_TOTAL, DIFFERENCE, PERCENT_DIFFERENCE
- LOD: LOD_FIXED, LOD_INCLUDE, LOD_EXCLUDE

### 三元模型 (What × Where × How)

| 元素 | 说明 | 示例 |
|------|------|------|
| What | 度量 + 聚合 | Sales (SUM) |
| Where | 维度 (分组) + 过滤器 (条件) | 维度: City, 过滤器: City="Beijing" |
| How | 计算复杂度 | SIMPLE / COMPLEX |

**Dimension vs Filter 区分**：
- Dimension: 分组字段，用于 "by X", "per X", "for each X"
- Filter: 值约束，用于 "in Beijing", "= X", 日期范围

### 数据模型层次

```
core/models/           # 平台无关 (语义层)
├── fields.py          # DimensionField, MeasureField
├── filters.py         # SetFilter, DateRangeFilter, ...
├── computations.py    # Computation, CalcParams
├── enums.py           # CalcType, HowType, IntentType, ...
└── query.py           # VizQLQuery

platforms/tableau/     # Tableau 平台实现
├── models/            # TableCalc, LODExpression
├── query_builder.py   # 查询构建器
├── field_mapper.py    # 字段映射器
└── vizql_client.py    # VizQL API 客户端
```

### 中间件栈

| 中间件 | 功能 |
|--------|------|
| ModelRetryMiddleware | LLM 重试 |
| ToolRetryMiddleware | 工具重试 |
| OutputValidationMiddleware | 输出校验 |

### Insight Agent 组件

```
EnhancedDataProfiler (单一入口)
├── StatisticalAnalyzer    # 统计分析 (分布/聚类/相关性)
└── AnomalyDetector        # 异常检测

AnalysisCoordinator        # 协调器 (只调用 EnhancedDataProfiler)
```

## Prompt 与 Model 规范

遵循 `docs/PROMPT_AND_MODEL_GUIDE.md` 和 `.kiro/specs/react-agent-refactor/prompt_and_models规范文档.md`：

**核心原则**：
- Prompt 教 LLM 如何思考，Schema 告诉 LLM 输出什么
- 信息去重：每种信息只在最相关位置出现一次
- 全英文 docstring

**XML 标签规范**：
- Class docstring: `<fill_order>`, `<examples>` (≤2), `<anti_patterns>` (≤3)
- Field description: `<what>`, `<when>`, `<rule>`, `<dependency>`, `<must_not>`
- Enum docstring: `<rule>` (选择逻辑) 或一行格式 (值含义)

## API 端点

| 端点 | 说明 |
|------|------|
| `/api/chat/stream` | 流式查询 |
| `/api/preload/dimension-hierarchy` | 预热 |
| `/api/health` | 健康检查 |

## 测试

```bash
# 运行所有测试
pytest

# 运行集成测试
pytest tableau_assistant/tests/integration/

# 运行 SemanticParser 测试
pytest tableau_assistant/tests/integration/test_semantic_parser_subgraph.py
```

---

**版本**: v2.3.0 | **更新**: 2024-12-29
