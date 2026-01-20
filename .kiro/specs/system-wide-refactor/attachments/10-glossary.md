# 附件 10：术语表

本文档定义系统中使用的技术术语和概念。

## A

**Agent（智能体）**  
执行特定分析任务的专业化 LangGraph 节点。每个 Agent 负责一个明确的功能，如语义解析、字段映射、洞察生成等。

**API 层**  
系统的最外层，使用 FastAPI 实现，负责接收用户请求、流式输出响应、错误处理等。

---

## B

**BM25**  
一种基于词频的关键词检索算法，用于文本检索和排序。

**BaseComponent**  
可复用组件的抽象基类，定义了组件的标准接口（execute 方法）。

---

## C

**Cache（缓存）**  
使用 Redis 存储查询结果，减少重复计算，提升响应速度。

**Component（组件）**  
Agent 内部的可复用功能模块，如预处理组件、意图分类器、Schema Linker 等。

**Core 层（核心领域层）**  
系统的最底层，定义领域模型、业务逻辑和平台无关接口。不依赖任何其他层。

**Cross-Encoder**  
一种用于重排序的深度学习模型，同时编码查询和候选文档，计算相关性分数。

---

## D

**DataModel（数据模型）**  
描述数据源结构的模型，包含字段列表、关系等信息。

**Dimension（维度）**  
数据分析中的分类字段，如日期、地区、产品类别等。

**DimensionHierarchy Agent**  
推断维度层级关系的 Agent，如"国家 → 省份 → 城市"。

---

## E

**Embedding**  
将文本转换为向量表示的技术，用于语义相似度计算。

**Exact Match（精确匹配）**  
字段名与查询完全匹配的检索策略，优先级最高。

---

## F

**FAISS**  
Facebook 开发的向量相似度搜索库，用于高效的向量检索。

**Field（字段）**  
数据模型中的一个列，包含名称、类型、描述等属性。

**FieldMapper Agent**  
将语义查询中的实体映射到数据模型字段的 Agent。

---

## G

**Grafana**  
开源的监控可视化平台，用于展示 Prometheus 采集的指标。

---

## H

**Hybrid Retrieval（混合检索）**  
结合多种检索策略（向量、关键词、精确匹配）的方法，提升检索准确性。

**Hypothesis**  
Python 的 Property-Based Testing 框架，用于自动生成测试用例。

---

## I

**Idempotence（幂等性）**  
操作执行多次与执行一次效果相同的性质。

**Infrastructure 层（基础设施层）**  
提供横向基础设施服务的层，包括 AI、RAG、Storage、Config、Observability 等模块。

**Insight Agent**  
生成数据洞察和建议的 Agent，使用渐进式分析策略。

**Intent（意图）**  
用户查询的目的，如对比分析、趋势分析、排名分析等。

**IntentRouter（意图路由器）**  
三层意图识别系统，包括规则引擎、小模型和 LLM 兜底。

---

## L

**LangChain**  
用于构建 LLM 应用的 Python 框架，提供丰富的集成和工具。

**LangGraph**  
基于图的 LLM 工作流编排框架，支持状态管理、条件分支和循环。

**LLM（Large Language Model）**  
大语言模型，如 GPT-4、Claude 等。

---

## M

**Measure（度量）**  
数据分析中的数值字段，如销售额、数量、利润等。

**Middleware（中间件）**  
包装 Agent 执行的横切关注点处理器，如输出验证、工具调用修复、缓存等。

**ModelManager**  
统一管理多个 LLM 和 Embedding 模型的组件，支持多提供商、健康检查、使用统计等。

---

## O

**OpenTelemetry**  
开源的可观测性框架，用于采集追踪、指标和日志。

**Orchestration 层（编排层）**  
使用 LangGraph 编排多 Agent 工作流的层，负责状态管理、中间件和工具。

---

## P

**Platform 层（平台适配层）**  
实现特定平台（如 Tableau）的适配器，处理平台特定的 API 调用和数据格式。

**Prometheus**  
开源的监控系统，用于采集和存储时间序列指标。

**Property-Based Testing（属性测试）**  
通过定义系统应该满足的通用属性，然后自动生成大量测试用例来验证这些属性的测试方法。

**Prompt**  
发送给 LLM 的输入文本，包含指令、上下文和问题。

---

## R

**RAG（Retrieval-Augmented Generation）**  
检索增强生成，结合检索和生成的技术，用于提升 LLM 的准确性。

**ReAct**  
Reasoning and Acting 的缩写，一种让 LLM 进行推理和行动的框架。

**Reranker（重排序器）**  
对检索结果进行重新排序的组件，提升 Top-K 准确性。

**Replanner Agent**  
评估分析完整度并决定是否继续探索的 Agent。

**Round Trip（往返）**  
操作与其逆操作组合后返回原始值的性质，如序列化后反序列化。

---

## S

**Schema Linking**  
将自然语言实体映射到数据模型字段的过程。

**SemanticParser Agent**  
理解用户意图并将自然语言转换为语义查询的 Agent。

**SemanticQuery（语义查询）**  
平台无关的查询表示，包含意图、实体、时间上下文、筛选条件等。

**Subgraph（子图）**  
LangGraph 中的嵌套工作流，可以作为一个节点在主工作流中使用。

---

## T

**Tableau**  
商业智能和数据可视化平台。

**Token**  
LLM 处理的最小文本单位，影响成本和延迟。

**Top-K**  
检索结果中排名前 K 的项目。

---

## U

**UnifiedRetriever（统一检索器）**  
支持多种检索策略（向量、关键词、精确匹配、混合）的检索组件。

---

## V

**Vector Store（向量存储）**  
存储和检索向量 Embedding 的数据库，如 FAISS、Chroma。

**VizQL**  
Tableau 的查询语言，用于构建数据可视化查询。

---

## W

**Workflow（工作流）**  
LangGraph 中定义的节点和边的有向图，描述 Agent 的执行顺序和条件分支。

---

## 缩写对照表

| 缩写 | 全称 | 中文 |
|------|------|------|
| AI | Artificial Intelligence | 人工智能 |
| API | Application Programming Interface | 应用程序接口 |
| BM25 | Best Matching 25 | 最佳匹配 25 算法 |
| CI/CD | Continuous Integration/Continuous Deployment | 持续集成/持续部署 |
| CRUD | Create, Read, Update, Delete | 增删改查 |
| LLM | Large Language Model | 大语言模型 |
| PBT | Property-Based Testing | 属性测试 |
| RAG | Retrieval-Augmented Generation | 检索增强生成 |
| SDK | Software Development Kit | 软件开发工具包 |
| SQL | Structured Query Language | 结构化查询语言 |
| TDD | Test-Driven Development | 测试驱动开发 |
| TTL | Time To Live | 生存时间 |

---

## 概念关系图

```
系统架构
├── API 层
├── Orchestration 层
│   ├── Workflow（工作流）
│   ├── Middleware（中间件）
│   └── Tools（工具）
├── Agent 层
│   ├── SemanticParser
│   ├── FieldMapper
│   ├── DimensionHierarchy
│   ├── Insight
│   └── Replanner
├── Platform 层
│   └── Tableau Adapter
├── Core 层
│   ├── Models（领域模型）
│   └── Interfaces（接口）
└── Infrastructure 层
    ├── AI（ModelManager）
    ├── RAG（UnifiedRetriever）
    ├── Storage（Cache）
    ├── Config（Settings）
    └── Observability（Logger, Metrics）
```

---

## 总结

本术语表提供了：

✅ **完整的术语定义**：系统中使用的所有关键术语  
✅ **缩写对照表**：常见缩写的全称和中文  
✅ **概念关系图**：术语之间的层次关系  

通过这个术语表，团队成员可以快速理解系统中使用的技术术语和概念，确保沟通的一致性。
