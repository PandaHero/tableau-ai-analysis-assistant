# Tableau Assistant DeepAgents 重构 - 设计文档

## 文档导航

本设计文档采用**精简主文档 + 详细附录**的结构，便于快速理解和深入研究。

### 📋 主文档（本文件）
- 技术架构概述
- 核心设计决策
- 数据流设计
- 关键技术选型

### 📚 详细附录（./design-appendix/）
- [子代理设计详解](./design-appendix/subagent-design.md) - 5个子代理的详细设计
- [中间件设计详解](./design-appendix/middleware-design.md) - 3个自定义中间件的详细设计
- [工具设计详解](./design-appendix/tools-design.md) - 8个Tableau工具的详细设计
- [数据模型设计详解](./design-appendix/data-models.md) - 完整的数据模型定义
- [字段语义推断系统](./design-appendix/field-semantics.md) - 统一的字段语义推断设计 ⭐
- [Task Planner与RAG集成](./design-appendix/task-planner-rag-integration.md) - 字段映射集成方案 ⭐
- [DeepAgents 特性详解](./design-appendix/deepagents-features.md) - 充分利用 DeepAgents 的高级特性
- [剩余主题概要](./design-appendix/remaining-topics.md) - 渐进式洞察、缓存、API等概要

---

## 技术架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    前端层 (Vue 3 + TypeScript)               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  对话界面 │ 进度展示 │ 数据可视化 │ Tableau Viz      │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │ HTTP/SSE
┌─────────────────────────────────────────────────────────────┐
│                    API层 (FastAPI)                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  /api/chat  │  /api/chat/stream  │  /api/health     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              DeepAgent 主编排层                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  TodoListMiddleware │ FilesystemMiddleware           │  │
│  │  SubAgentMiddleware │ SummarizationMiddleware        │  │
│  │  AnthropicPromptCachingMiddleware                    │  │
│  │  ApplicationLevelCacheMiddleware ⭐                   │  │
│  │  TableauMetadataMiddleware ⭐                         │  │
│  │  VizQLQueryMiddleware ⭐                              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                   子代理层 (5个SubAgent)                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  boost-agent        │ understanding-agent            │  │
│  │  planning-agent     │ insight-agent ⭐               │  │
│  │  replanner-agent ⭐                                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                Tableau 工具层 (5个工具)                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  vizql_query        │ get_metadata                   │  │
│  │  semantic_map_fields ⭐ │ parse_date                 │  │
│  │  build_vizql_query                                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                核心组件层 (100% 复用)                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  QueryBuilder       │ QueryExecutor                  │  │
│  │  DataProcessor      │ MetadataManager                │  │
│  │  DateParser         │ 所有 Pydantic 模型             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              渐进式洞察系统 ⭐ (新增)                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  准备层: Coordinator, DataProfiler, SemanticChunker │  │
│  │  分析层: ChunkAnalyzer, PatternDetector             │  │
│  │  累积层: InsightAccumulator, QualityFilter          │  │
│  │  合成层: InsightSynthesizer, SummaryGenerator       │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              语义字段映射系统 ⭐ (新增)                      │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Vector Store (FAISS)                                │  │
│  │  Embedding Model (bce-embedding-base-v1 或 OpenAI)  │  │
│  │  Field Metadata Index (~1000 字段)                  │  │
│  │  Semantic Mapper (LLM 语义判断)                     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              缓存系统 ⭐ (四层缓存)                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  L1: Prompt Caching (Anthropic 官方)                │  │
│  │  L2: Application Cache (PersistentStore)            │  │
│  │  L3: Query Result Cache (PersistentStore)           │  │
│  │  L4: Semantic Cache (可选，向量相似度)              │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      数据层                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  PersistentStore (SQLite) │ Tableau VDS API          │  │
│  │  Tableau REST API         │ LLM (Claude/GPT)         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**图例**：
- ⭐ 表示新增或重点增强的组件

---

## 核心设计决策

### 1. 为什么选择 DeepAgents？

**决策**：使用 LangChain DeepAgents 作为主编排框架

**理由**：
- ✅ **内置规划能力** - TodoListMiddleware 提供开箱即用的任务规划
- ✅ **文件系统管理** - FilesystemMiddleware 自动处理大型数据
- ✅ **子代理委托** - SubAgentMiddleware 支持复杂任务隔离
- ✅ **自动总结** - SummarizationMiddleware 管理长上下文
- ✅ **Prompt 缓存** - AnthropicPromptCachingMiddleware 节省 50-90% 成本
- ✅ **可扩展性** - 支持自定义中间件和工具

**替代方案**：
- ❌ 纯 LangGraph - 需要自己实现所有功能，开发成本高
- ❌ 自定义编排 - 缺少成熟的优化和最佳实践

### 2. 为什么 100% 复用现有组件？

**决策**：所有现有的核心业务组件都 100% 保留和复用

**理由**：
- ✅ **降低风险** - 不需要重写已验证的业务逻辑
- ✅ **保护投资** - 保留所有已有的开发成果
- ✅ **快速迁移** - 只需封装为工具，不需要重构内部实现
- ✅ **渐进式升级** - 可以逐步优化而不影响核心功能

**实现方式**：
```python
# 现有组件封装为 LangChain 工具
from langchain_core.tools import tool
from tableau_assistant.src.components.query_executor import QueryExecutor

@tool
def vizql_query(query: Dict, datasource_luid: str) -> Dict:
    """执行 VizQL 查询（内部使用现有的 QueryExecutor）"""
    executor = QueryExecutor(token, datasource_luid)
    return executor.execute(query)
```

### 3. 为什么采用渐进式洞察分析？

**决策**：对大数据集使用"AI 宝宝吃饭"式的渐进式分析

**理由**：
- ✅ **避免 Token 超限** - 大数据集（>100 行）无法一次性放入上下文
- ✅ **提升首次反馈速度** - 分析第一块数据后立即输出洞察
- ✅ **智能早停** - AI 判断已获得足够洞察时自动停止
- ✅ **更好的用户体验** - 流式输出洞察，类似 ChatGPT

**工作原理**：
```
大数据集（500 行）
  ↓
Coordinator: 检测数据规模 → 启动渐进式分析
  ↓
DataProfiler: 生成数据画像（分布、异常值位置）
  ↓
SemanticChunker: 智能分块
  ├─ 第1块: Top 异常值（offset=0, limit=50）
  ├─ 第2块: 高值区间（offset=50, limit=100）
  └─ 第3块: 中值区间（offset=150, limit=200）
  ↓
ChunkAnalyzer: 分析每个块 → 流式输出洞察
  ↓
AI 判断: 数据趋势已清晰 → 早停（跳过剩余 250 行）
```

### 4. 为什么采用智能重规划机制？

**决策**：支持多轮迭代分析，类似 Tableau Pulse

**理由**：
- ✅ **深度分析** - 像人类分析师一样逐层深入
- ✅ **根因挖掘** - 不止于表面现象，找到根本原因
- ✅ **自适应** - 根据分析结果动态调整下一步方向
- ✅ **用户体验** - 提供完整的分析路径和推理过程

**工作流程**：
```
第0轮: "为什么华东地区利润率低？"
  → 查询: 各地区利润率
  → 洞察: 华东利润率 12%，低于全国平均 15%
  → 重规划: 需要分析具体原因
  ↓
第1轮: "华东各产品类别的利润率如何？"
  → 查询: 华东各产品类别利润率
  → 洞察: 家具类利润率仅 8%，是主要拖累
  → 重规划: 需要分析家具类的具体问题
  ↓
第2轮: "家具类的成本和折扣情况如何？"
  → 查询: 家具类成本和折扣
  → 洞察: 折扣率 22%，远高于行业平均 12%
  → 重规划: 找到根因，停止重规划
  ↓
总结: 华东利润率低的根本原因是家具类折扣过高
```

### 5. 为什么采用语义字段映射？

**决策**：使用 RAG + LLM 实现智能字段映射，完全替代硬编码的映射规则

**理由**：
- ✅ **理解业务语义** - 区分"销售额"和"销售数量"
- ✅ **考虑上下文** - "去年的销售额"vs"今年的销售额"
- ✅ **处理同义词** - "收入"="营收"="销售额"
- ✅ **支持多语言** - "Sales"="销售额"
- ✅ **持续学习** - 从历史映射中学习，不断提升准确率
- ✅ **无需人工维护** - 系统自动管理映射历史

**核心原则**：
- ✅ **RAG + LLM 主导映射** - 每次都通过向量检索 + LLM语义理解来决策
- ✅ **配置文件辅助** - YAML配置提供映射提示，但不强制执行
- ✅ **历史映射增强** - 成功的映射作为RAG的增强上下文
- ✅ **系统自动维护** - 映射历史和配置由系统自动管理，无需用户干预

**配置文件的角色**：
- 📝 **辅助提示** - 为LLM提供同义词、常见映射模式等提示
- 🚫 **不强制执行** - LLM可以根据上下文选择忽略配置
- 🔄 **自动更新** - 系统根据历史映射自动更新配置文件

**工作原理**：
```
用户输入: "华东地区的销售额"
  ↓
1. 向量检索 (FAISS)
   业务术语: "销售额"
   ├─ 候选1: [Sales].[Sales Amount] (0.95)
   ├─ 候选2: [Sales].[Revenue] (0.92)
   ├─ 候选3: [Sales].[Quantity] (0.65)
   └─ 候选4: [Orders].[Order Total] (0.60)
  ↓
2. 历史映射检索 (可选增强)
   查询: "销售额" + datasource_luid
   ├─ 历史1: "销售额" → [Sales].[Sales Amount] (使用3次, 成功率100%)
   └─ 历史2: "营收" → [Sales].[Revenue] (使用1次, 成功率100%)
  ↓
3. LLM 语义判断
   输入:
     - 问题上下文: "华东地区的销售额"
     - 候选字段: Top-5 + 字段描述 + 示例值
     - 历史映射: 相关的历史映射记录
     - 字段类型提示: "销售额"应该是measure类型
   
   输出:
     - 最佳匹配: [Sales].[Sales Amount]
     - 置信度: 0.95
     - 推理过程: "根据问题上下文和字段描述，'销售额'应该映射到..."
     - 备选方案: [[Sales].[Revenue] (0.92)]
  ↓
4. 保存映射历史 (用于未来学习)
   {
     "business_term": "销售额",
     "technical_field": "[Sales].[Sales Amount]",
     "datasource_luid": "xxx",
     "question_context": "华东地区的销售额",
     "confidence": 0.95,
     "timestamp": "2025-01-15T10:30:00Z",
     "success": true  # 后续会根据查询是否成功更新
   }
```

### 6. 为什么采用四层缓存架构？

**决策**：L1 Prompt Caching + L2 Application Cache + L3 Query Cache + L4 Semantic Cache

**理由**：
- ✅ **L1 (Prompt Caching)** - Anthropic 官方，节省 50-90% 成本
- ✅ **L2 (Application Cache)** - 缓存 LLM 响应，支持所有模型
- ✅ **L3 (Query Cache)** - 缓存查询结果，避免重复查询
- ✅ **L4 (Semantic Cache)** - 语义相似度匹配，可选功能

**缓存策略**：
| 层级 | 存储方式 | 有效期 | 命中率 | 节省成本 |
|------|---------|--------|--------|---------|
| L1 | Anthropic API | 5分钟 | 60-80% | 50-90% |
| L2 | PersistentStore | 1小时 | 40-60% | 30-50% |
| L3 | PersistentStore | 会话期间 | 20-40% | 10-30% |
| L4 | Vector Store | 永久 | 5-15% | 5-10% |

---

## Agent 配置

### 主 Agent 配置

主 Agent 负责整体编排，协调子代理和工具执行。

```python
from deepagents import create_deep_agent

main_agent = create_deep_agent(
    name="tableau-assistant",
    model="claude-3-5-sonnet-20241022",
    
    # 主 Agent 工具（8个）
    tools=[
        # 核心工具
        "get_metadata",           # 获取元数据
        "execute_vizql_query",    # 执行查询
        "process_query_result",   # 处理结果
        "save_large_result",      # 保存大结果
        "detect_statistics",      # 统计检测
        
        # 辅助工具
        "read_file",              # 读取文件（FilesystemMiddleware）
        "write_file",             # 写入文件（FilesystemMiddleware）
        "task",                   # 委托子代理（SubAgentMiddleware）
    ],
    
    # 子代理（5个）
    subagents=[
        boost_agent,
        understanding_agent,
        planning_agent,
        insight_agent,
        replanner_agent
    ],
    
    # 中间件（9个）
    middleware=[
        # 内置中间件
        TodoListMiddleware(),
        FilesystemMiddleware(),
        SubAgentMiddleware(),
        SummarizationMiddleware(threshold=170000),
        AnthropicPromptCachingMiddleware(),
        
        # 自定义中间件
        TableauMetadataMiddleware(),
        VizQLQueryMiddleware(),
        ApplicationLevelCacheMiddleware(store=store, ttl=3600)
    ],
    
    # 后端存储
    backend=CompositeBackend(
        checkpointer=SqliteSaver(conn),
        store=PersistentStore(conn)
    ),
    
    # 配置
    max_tokens=4000,
    temperature=0.0,
    timeout=300
)
```

### 工具分配策略

| 工具 | 主 Agent | 子 Agent | 说明 |
|------|---------|---------|------|
| **get_metadata** | ✅ | boost, planning, replanner | 元数据查询 |
| **semantic_map_fields** | ❌ | planning | 语义字段映射（RAG+LLM） |
| **parse_date** | ❌ | planning | 日期解析 |
| **build_vizql_query** | ❌ | planning | 查询构建 |
| **execute_vizql_query** | ✅ | - | 查询执行 |
| **process_query_result** | ✅ | - | 数据处理 |
| **detect_statistics** | ❌ | insight | 统计检测 |
| **save_large_result** | ✅ | - | 大结果保存 |

**设计原则**：
- 主 Agent 负责执行和数据管理
- 子 Agent 负责规划和分析
- 避免工具重复，减少混淆

---

## 数据流设计

### 主流程数据流

```
1. 用户输入问题
   ↓
2. (可选) Boost Agent 优化问题
   输入: 原始问题 + 元数据
   输出: 优化后的问题
   ↓
3. Understanding Agent 理解问题
   输入: 问题
   输出: 问题类型、复杂度、提取的实体
   ↓
4. Planning Agent 规划查询
   输入: 问题理解 + 元数据
   
   4.1 提取业务术语
       从understanding中提取:
       - mentioned_dimensions: ["华东地区", "产品类别"]
       - mentioned_measures: ["销售额", "利润率"]
       - mentioned_date_fields: ["订单日期"]
   
   4.2 调用语义字段映射工具 (semantic_map_fields)
       输入:
         - business_terms: ["华东地区", "产品类别", "销售额", ...]
         - question_context: 完整问题
         - metadata: Tableau元数据
         - field_type_hints: {"华东地区": "dimension", "销售额": "measure"}
       
       处理流程:
         a. 向量检索 (FAISS)
            为每个业务术语检索Top-5候选字段
         
         b. 历史映射检索 (PersistentStore)
            查询该数据源的历史映射记录
         
         c. LLM语义判断
            综合考虑:
            - 问题上下文
            - 候选字段描述
            - 历史映射记录
            - 字段类型提示
            
            输出每个术语的最佳匹配
         
         d. 保存映射历史
            将本次映射保存到PersistentStore
            命名空间: ("field_mappings", datasource_luid)
       
       输出: FieldMappingResult
         {
           "华东地区": {
             "technical_field": "[Region].[Region Name]",
             "confidence": 0.95,
             "alternatives": [...],
             "reasoning": "..."
           },
           "销售额": {
             "technical_field": "[Sales].[Sales Amount]",
             "confidence": 0.98,
             "alternatives": [...],
             "reasoning": "..."
           }
         }
   
   4.3 生成Intent模型
       使用FieldMappingResult中的technical_field
       不再需要在Prompt中硬编码映射规则
       
       输出: QueryPlanningResult
         subtasks: [
           {
             dimension_intents: [
               {
                 business_term: "华东地区",
                 technical_field: "[Region].[Region Name]",
                 mapping_confidence: 0.95
               }
             ],
             measure_intents: [
               {
                 business_term: "销售额",
                 technical_field: "[Sales].[Sales Amount]",
                 aggregation: "SUM",
                 mapping_confidence: 0.98
               }
             ]
           }
         ]
   ↓
5. 查询执行（并行）
   对每个子查询:
     6.1 检查缓存 (L3)
     6.2 如果缓存未命中 → 执行查询
     6.3 保存结果到缓存
   ↓
7. 渐进式洞察分析
   IF 数据量 > 100行:
     7.1 Coordinator 决定使用渐进式分析
     7.2 DataProfiler 生成数据画像
     7.3 SemanticChunker 智能分块
     7.4 ChunkAnalyzer 逐块分析 → 流式输出
     7.5 AI 判断是否早停
   ELSE:
     7.6 Insight Agent 直接分析
   ↓
8. Replanner Agent 评估
   输入: 原始问题 + 累积洞察 + 当前轮次
   输出: 是否需要重规划 + 新问题
   ↓
9. IF 需要重规划 AND 未达到最大轮次:
     → 回到步骤 3（使用新问题）
   ELSE:
     → 继续到步骤 10
   ↓
10. 生成最终报告
    输入: 原始问题 + 所有轮次的洞察
    输出: 执行摘要 + 关键发现 + 建议
```

### 缓存命中流程

```
查询请求
  ↓
生成 query_key (hash(query_params))
  ↓
检查 L3 缓存 (PersistentStore)
  ├─ 命中 → 直接返回结果 ⚡
  └─ 未命中 ↓
     执行查询
       ↓
     保存到 L3 缓存
       ↓
     返回结果
```

### LLM 调用流程（含缓存）

```
LLM 调用请求
  ↓
生成 cache_key (hash(system_prompt + user_input))
  ↓
检查 L2 缓存 (ApplicationLevelCacheMiddleware)
  ├─ 命中 → 直接返回响应 ⚡
  └─ 未命中 ↓
     IF 使用 Claude 模型:
       检查 L1 缓存 (AnthropicPromptCachingMiddleware)
         ├─ 命中 → 节省 50-90% 成本 ⚡
         └─ 未命中 ↓
     调用 LLM
       ↓
     保存到 L2 缓存 (TTL: 1小时)
       ↓
     返回响应
```

---

## 语义字段映射系统详细设计

### 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│  Planning Agent                                              │
│  ├─ 提取业务术语                                             │
│  └─ 调用 semantic_map_fields 工具                           │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  semantic_map_fields 工具                                    │
│                                                              │
│  输入:                                                       │
│    - business_terms: List[str]                              │
│    - question_context: str                                  │
│    - metadata: TableauMetadata                              │
│    - field_type_hints: Dict[str, str]                       │
│                                                              │
│  输出:                                                       │
│    - FieldMappingResult                                     │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│  SemanticMapper (核心组件)                                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  1. VectorStoreManager                                │  │
│  │     - 管理FAISS向量索引                               │  │
│  │     - 为每个datasource维护独立索引                    │  │
│  │     - 支持索引持久化和加载                            │  │
│  └──────────────────────────────────────────────────────┘  │
│                        ↓                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  2. FieldIndexer                                      │  │
│  │     - 从Tableau元数据构建字段索引                     │  │
│  │     - 生成富文本向量 (字段名+描述+示例值)            │  │
│  │     - 支持增量更新                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                        ↓                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  3. 向量检索                                          │  │
│  │     - 为每个业务术语检索Top-K候选                     │  │
│  │     - 使用余弦相似度排序                              │  │
│  │     - 过滤低质量候选 (相似度阈值)                     │  │
│  └──────────────────────────────────────────────────────┘  │
│                        ↓                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  4. 历史映射检索 (PersistentStore)                    │  │
│  │     - 查询该数据源的历史映射                          │  │
│  │     - 按使用频率和成功率排序                          │  │
│  │     - 作为LLM的增强上下文                             │  │
│  └──────────────────────────────────────────────────────┘  │
│                        ↓                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  5. LLM语义判断                                       │  │
│  │     输入:                                             │  │
│  │       - 问题上下文                                    │  │
│  │       - Top-K候选字段 + 描述 + 示例值                │  │
│  │       - 历史映射记录                                  │  │
│  │       - 字段类型提示                                  │  │
│  │                                                       │  │
│  │     输出:                                             │  │
│  │       - 最佳匹配字段                                  │  │
│  │       - 置信度 (0-1)                                  │  │
│  │       - 推理过程                                      │  │
│  │       - 备选方案                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                        ↓                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  6. 保存映射历史                                      │  │
│  │     - 保存到PersistentStore                           │  │
│  │     - 命名空间: ("field_mappings", datasource_luid)  │  │
│  │     - 包含: 业务术语、技术字段、置信度、上下文        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 数据模型

#### 输入模型

```python
class FieldMappingRequest(BaseModel):
    """字段映射请求"""
    business_terms: List[str]
    """业务术语列表，如 ["华东地区", "销售额"]"""
    
    question_context: str
    """完整问题上下文，用于语义理解"""
    
    metadata: TableauMetadata
    """Tableau元数据，包含所有可用字段"""
    
    field_type_hints: Optional[Dict[str, str]] = None
    """字段类型提示，如 {"华东地区": "dimension", "销售额": "measure"}"""
    
    datasource_luid: str
    """数据源唯一标识"""
```

#### 输出模型

```python
class FieldMapping(BaseModel):
    """单个字段的映射结果"""
    business_term: str
    """业务术语"""
    
    technical_field: str
    """技术字段名，如 [Sales].[Sales Amount]"""
    
    confidence: float
    """置信度 (0-1)"""
    
    alternatives: List[Dict[str, Any]]
    """备选方案列表"""
    
    reasoning: str
    """LLM的推理过程"""
    
    field_data_type: str
    """字段数据类型: STRING, REAL, INTEGER, DATE等"""
    
    field_role: str
    """字段角色: dimension, measure"""


class FieldMappingResult(BaseModel):
    """字段映射结果"""
    mappings: Dict[str, FieldMapping]
    """业务术语到映射结果的字典"""
    
    overall_confidence: float
    """整体置信度 (所有映射的平均值)"""
    
    datasource_luid: str
    """数据源唯一标识"""
```

#### 历史映射模型

```python
class MappingHistory(BaseModel):
    """映射历史记录"""
    business_term: str
    """业务术语"""
    
    technical_field: str
    """技术字段名"""
    
    datasource_luid: str
    """数据源唯一标识"""
    
    question_context: str
    """问题上下文"""
    
    confidence: float
    """映射置信度"""
    
    timestamp: datetime
    """创建时间"""
    
    usage_count: int = 1
    """使用次数"""
    
    success_count: int = 0
    """成功次数 (查询成功)"""
    
    success_rate: float = 0.0
    """成功率 = success_count / usage_count"""
```

### 向量索引构建

#### 维度层级推断与RAG的关系

**设计决策**：维度层级推断作为**元数据增强工具**，为RAG提供更丰富的语义信息

**工作流程**：
```
系统初始化
  ↓
1. 获取Tableau元数据
   - 字段名、类型、示例值
   - 唯一值数量
  ↓
2. 维度层级推断 (一次性)
   输入: 原始元数据
   输出: 增强的元数据
     - category: geographic, temporal, product等
     - level: 1-5 (粗到细)
     - parent/child: 父子关系
  ↓
3. 保存增强元数据
   - 保存到PersistentStore
   - 命名空间: ("metadata_enhanced", datasource_luid)
  ↓
4. 构建向量索引
   - 使用增强后的元数据
   - 字段富文本包含层级信息
```

**RAG如何利用层级信息**：
```
用户问题: "华东地区的销售额"
  ↓
RAG检索:
  业务术语: "华东地区"
  
  候选字段 (包含层级信息):
    1. [Region].[一级地区]
       - level: 1 (最粗)
       - category: geographic
       - samples: ["华东", "华北", "华南"]
       - 相似度: 0.95
    
    2. [Region].[二级地区]
       - level: 2 (粗)
       - category: geographic
       - samples: ["江苏省", "浙江省", "上海市"]
       - 相似度: 0.88
    
    3. [Region].[三级地区]
       - level: 3 (中)
       - category: geographic
       - samples: ["南京市", "杭州市", "苏州市"]
       - 相似度: 0.75
  ↓
LLM语义判断:
  分析: "华东地区"是一个大区概念
  - 示例值匹配: "华东"出现在一级地区的示例中
  - 层级匹配: 大区应该是最粗粒度 (level=1)
  
  选择: [Region].[一级地区] (置信度: 0.95)
```

**优势**：
- ✅ **一次推断，多次使用** - 不需要每次查询都推断
- ✅ **增强RAG准确性** - 层级信息帮助LLM做出更好的判断
- ✅ **支持粒度选择** - 用户问"省份"vs"城市"时自动选择正确层级
- ✅ **减少LLM负担** - 层级信息已经预计算好

#### 度量字段的语义增强（简化方案）

**问题**：度量字段不需要层级，但需要其他语义信息

**难点分析**：
- ❌ **业务含义难推断** - 需要深入理解业务逻辑
- ❌ **单位难识别** - 字段名通常不包含单位
- ❌ **相关维度难确定** - 需要分析查询模式
- ✅ **值域可计算** - 可以从统计信息获取
- ✅ **数据类型明确** - 元数据中已有

**简化方案**：采用**渐进式增强**策略

```python
class MeasureSemantics(BaseModel):
    """度量字段的语义信息（简化版）"""
    
    # ===== 阶段1：基础信息（从元数据直接获取）=====
    value_range: Optional[Dict[str, float]] = None
    """值域: {"min": 0, "max": 1000000, "avg": 50000}"""
    
    data_type: str
    """数据类型: REAL, INTEGER"""
    
    # ===== 阶段2：简单推断（LLM基于字段名）=====
    category: Optional[str] = None
    """度量类别: financial, operational, performance (可选)"""
    
    suggested_aggregation: Optional[str] = None
    """建议的聚合类型: SUM, AVG, COUNT (可选)"""
    
    # ===== 阶段3：历史学习（从实际使用中学习）=====
    common_aggregations: Dict[str, int] = {}
    """常用聚合统计: {"SUM": 10, "AVG": 3} (使用次数)"""
    
    common_dimensions: Dict[str, int] = {}
    """常用维度统计: {"Region": 8, "Product": 5} (共现次数)"""


# 阶段1：基础信息（不需要LLM）
def extract_basic_measure_info(field: FieldMetadata) -> MeasureSemantics:
    """
    从元数据提取基础信息（不需要LLM）
    
    包含:
    - 值域（从统计信息）
    - 数据类型
    """
    return MeasureSemantics(
        value_range={
            "min": field.min_value,
            "max": field.max_value,
            "avg": field.avg_value
        } if field.min_value is not None else None,
        data_type=field.data_type
    )


# 阶段2：简单推断（可选，使用LLM）
async def infer_measure_category(field: FieldMetadata) -> Dict[str, str]:
    """
    基于字段名简单推断类别和建议聚合（可选）
    
    只做简单的分类，不深入业务逻辑
    """
    prompt = f"""
    字段名: {field.name}
    数据类型: {field.data_type}
    示例值: {field.sample_values}
    
    请简单分类:
    1. 类别: financial/operational/performance/other
    2. 建议聚合: SUM/AVG/COUNT/MAX/MIN
    
    只需要简单判断，不确定就返回null
    """
    
    result = await llm.invoke(prompt)
    return {
        "category": result.get("category"),
        "suggested_aggregation": result.get("aggregation")
    }


# 阶段3：历史学习（从实际使用中学习）
async def update_measure_usage(
    field_name: str,
    aggregation: str,
    dimensions: List[str],
    store: PersistentStore
):
    """
    从实际查询中学习度量的使用模式
    
    每次查询后调用，记录:
    - 使用了哪种聚合
    - 与哪些维度一起使用
    """
    key = f"measure_usage_{field_name}"
    usage = await store.get(("measure_semantics", key)) or {
        "common_aggregations": {},
        "common_dimensions": {}
    }
    
    # 更新聚合统计
    usage["common_aggregations"][aggregation] = \
        usage["common_aggregations"].get(aggregation, 0) + 1
    
    # 更新维度共现统计
    for dim in dimensions:
        usage["common_dimensions"][dim] = \
            usage["common_dimensions"].get(dim, 0) + 1
    
    await store.put(("measure_semantics", key), usage)


# 示例：渐进式增强的度量信息
measure_info = {
    "[Sales].[Sales Amount]": {
        # 阶段1：基础信息（立即可用）
        "value_range": {"min": 0, "max": 1000000, "avg": 50000},
        "data_type": "REAL",
        
        # 阶段2：简单推断（可选）
        "category": "financial",
        "suggested_aggregation": "SUM",
        
        # 阶段3：历史学习（随时间积累）
        "common_aggregations": {"SUM": 15, "AVG": 3},
        "common_dimensions": {"Region": 10, "Product": 8, "Date": 12}
    }
}
```

**实现策略**：

| 阶段 | 内容 | 难度 | 是否必需 |
|------|------|------|---------|
| **阶段1** | 基础信息（值域、类型） | ⭐ 简单 | ✅ 必需 |
| **阶段2** | 简单推断（类别、建议聚合） | ⭐⭐ 中等 | ⏸️ 可选 |
| **阶段3** | 历史学习（使用模式） | ⭐ 简单 | ✅ 推荐 |

**MVP建议**：
- ✅ 实现阶段1（基础信息）- 简单且有用
- ⏸️ 跳过阶段2（简单推断）- 收益不大
- ✅ 实现阶段3（历史学习）- 简单且越用越准

#### 字段富文本生成（增强版）

```python
def build_field_rich_text(
    field: FieldMetadata,
    hierarchy_attrs: Optional[DimensionAttributes] = None,
    measure_semantics: Optional[MeasureSemantics] = None
) -> str:
    """
    为字段生成富文本，用于向量化
    
    包含:
    1. 字段名 (中英文)
    2. 字段描述
    3. 示例值 (更多样本) ⭐ 增强
    4. 字段类型和角色
    5. 维度层级信息 (如果是维度)
    6. 度量语义信息 (如果是度量) ⭐ 新增
    """
    parts = []
    
    # 字段名
    parts.append(f"字段名: {field.name}")
    
    # 描述
    if field.description:
        parts.append(f"描述: {field.description}")
    
    # ⭐ 示例值（增加数量）
    if field.sample_values:
        # 维度: 显示更多样本（5-10个）
        # 度量: 显示值域范围
        if field.role == "dimension":
            samples = ", ".join(str(v) for v in field.sample_values[:10])
            parts.append(f"示例值: {samples}")
        else:  # measure
            if len(field.sample_values) >= 2:
                min_val = min(field.sample_values)
                max_val = max(field.sample_values)
                parts.append(f"值域: {min_val} ~ {max_val}")
            samples = ", ".join(str(v) for v in field.sample_values[:5])
            parts.append(f"示例值: {samples}")
    
    # 类型和角色
    parts.append(f"类型: {field.data_type}")
    parts.append(f"角色: {field.role}")
    
    # ⭐ 维度层级信息（来自维度层级推断）
    if hierarchy_attrs:
        parts.append(f"类别: {hierarchy_attrs.category}")
        parts.append(f"层级: {hierarchy_attrs.level} ({hierarchy_attrs.granularity})")
        if hierarchy_attrs.parent_dimension:
            parts.append(f"父字段: {hierarchy_attrs.parent_dimension}")
        if hierarchy_attrs.child_dimension:
            parts.append(f"子字段: {hierarchy_attrs.child_dimension}")
    
    # ⭐ 度量语义信息（来自度量语义推断）
    if measure_semantics:
        parts.append(f"度量类别: {measure_semantics.category}")
        parts.append(f"常用聚合: {measure_semantics.aggregation_type}")
        if measure_semantics.unit:
            parts.append(f"单位: {measure_semantics.unit}")
        if measure_semantics.business_meaning:
            parts.append(f"业务含义: {measure_semantics.business_meaning}")
    
    return " | ".join(parts)
```

#### 完整的元数据增强流程（简化版）

```python
async def enhance_metadata(datasource_luid: str, metadata: Metadata):
    """
    完整的元数据增强流程（简化版）
    
    步骤:
    1. 维度层级推断 (为维度字段) - 使用LLM
    2. 度量基础信息提取 (为度量字段) - 不使用LLM
    3. 合并增强信息
    4. 保存到PersistentStore
    5. 构建向量索引
    
    注意: 度量的历史学习在查询执行后进行
    """
    # 1. 维度层级推断（使用LLM）
    dimension_hierarchy = await dimension_hierarchy_agent.execute(metadata)
    
    # 2. 度量基础信息提取（不使用LLM）
    measure_info = {}
    for field in metadata.get_measures():
        measure_info[field.name] = extract_basic_measure_info(field)
    
    # 3. 合并增强信息
    enhanced_metadata = {
        "original": metadata.model_dump(),
        "dimension_hierarchy": dimension_hierarchy,
        "measure_info": measure_info,
        "enhanced_at": datetime.now().isoformat()
    }
    
    # 4. 保存
    await store.put(
        namespace=("metadata_enhanced", datasource_luid),
        value=enhanced_metadata
    )
    
    # 5. 构建向量索引
    await build_field_index(datasource_luid, enhanced_metadata)
    
    return enhanced_metadata


# 查询执行后，更新度量使用统计
async def after_query_execution(
    query_plan: QueryPlanningResult,
    datasource_luid: str,
    store: PersistentStore
):
    """
    查询执行后，更新度量的使用统计
    
    从查询计划中提取:
    - 使用了哪些度量
    - 使用了哪种聚合
    - 与哪些维度一起使用
    """
    for subtask in query_plan.subtasks:
        # 提取度量和聚合
        for measure_intent in subtask.measure_intents:
            field_name = measure_intent.technical_field
            aggregation = measure_intent.aggregation
            
            # 提取维度
            dimensions = [
                dim.technical_field 
                for dim in subtask.dimension_intents
            ]
            
            # 更新使用统计
            await update_measure_usage(
                field_name,
                aggregation,
                dimensions,
                store
            )
```

**对比：完整版 vs 简化版**

| 项目 | 完整版 | 简化版 |
|------|--------|--------|
| **维度层级推断** | ✅ 使用LLM | ✅ 使用LLM |
| **度量语义推断** | ✅ 使用LLM（复杂） | ⏸️ 跳过 |
| **度量基础信息** | ✅ 提取 | ✅ 提取 |
| **度量历史学习** | ✅ 实现 | ✅ 实现 |
| **开发难度** | ⭐⭐⭐⭐ 高 | ⭐⭐ 中 |
| **准确性** | 高（初期） | 中（初期）→ 高（长期） |

**简化版的优势**：
- ✅ **开发简单** - 不需要复杂的度量语义推断
- ✅ **越用越准** - 通过历史学习不断提升
- ✅ **降低风险** - LLM推断可能不准确，历史数据更可靠

#### 示例值采样策略

**问题**：当前只有1个示例值，不足以表达字段的语义

**解决方案**：增加示例值数量，并智能采样

```python
async def fetch_field_samples(
    datasource_luid: str,
    field_name: str,
    sample_count: int = 10
) -> List[Any]:
    """
    从Tableau数据源获取字段的示例值
    
    策略:
    1. 维度字段: 获取10-20个不同的值（去重）
    2. 度量字段: 获取5-10个值，包含最小值、最大值、中位数
    3. 日期字段: 获取最早、最晚和几个中间值
    
    Args:
        datasource_luid: 数据源ID
        field_name: 字段名
        sample_count: 采样数量
    
    Returns:
        示例值列表
    """
    # 查询VizQL获取示例值
    query = {
        "datasource": datasource_luid,
        "fields": [field_name],
        "limit": sample_count * 2,  # 多获取一些，去重后可能不够
        "distinct": True  # 维度字段去重
    }
    
    result = await execute_vizql_query(query)
    samples = result.get_column_values(field_name)
    
    # 智能采样
    if len(samples) > sample_count:
        # 维度: 随机采样
        # 度量: 包含极值和中间值
        if is_measure_field(field_name):
            samples = smart_sample_measure(samples, sample_count)
        else:
            samples = random.sample(samples, sample_count)
    
    return samples


def smart_sample_measure(values: List[float], count: int) -> List[float]:
    """
    智能采样度量字段
    
    策略:
    - 包含最小值、最大值
    - 包含中位数
    - 其余均匀分布
    """
    sorted_values = sorted(values)
    n = len(sorted_values)
    
    samples = [
        sorted_values[0],           # 最小值
        sorted_values[n // 2],      # 中位数
        sorted_values[-1],          # 最大值
    ]
    
    # 其余均匀采样
    step = n // (count - 3)
    for i in range(1, count - 3):
        samples.append(sorted_values[i * step])
    
    return samples
```

#### 索引构建流程（增强版）

```python
async def build_field_index(
    datasource_luid: str,
    enhanced_metadata: Dict[str, Any]
) -> None:
    """
    为数据源构建字段向量索引（使用增强元数据）
    
    步骤:
    1. 获取更多示例值（如果需要）
    2. 为每个字段生成富文本（包含层级/语义信息）
    3. 使用Embedding模型向量化
    4. 构建FAISS索引
    5. 持久化到磁盘
    """
    metadata = enhanced_metadata["original"]
    dimension_hierarchy = enhanced_metadata.get("dimension_hierarchy", {})
    measure_semantics = enhanced_metadata.get("measure_semantics", {})
    
    # 1. 获取更多示例值（如果当前示例值不足）
    for field in metadata.fields:
        if not field.sample_values or len(field.sample_values) < 5:
            # 从数据源获取更多示例值
            field.sample_values = await fetch_field_samples(
                datasource_luid,
                field.name,
                sample_count=10 if field.role == "dimension" else 5
            )
    
    # 2. 生成富文本（包含增强信息）
    field_texts = []
    field_metadata = []
    
    for field in metadata.fields:
        # 获取增强信息
        hierarchy_attrs = dimension_hierarchy.get(field.name)
        measure_semantic = measure_semantics.get(field.name)
        
        # 生成富文本
        rich_text = build_field_rich_text(
            field,
            hierarchy_attrs=hierarchy_attrs,
            measure_semantics=measure_semantic
        )
        field_texts.append(rich_text)
        
        # 保存元数据
        field_metadata.append({
            "name": field.name,
            "data_type": field.data_type,
            "role": field.role,
            "hierarchy": hierarchy_attrs.model_dump() if hierarchy_attrs else None,
            "semantics": measure_semantic.model_dump() if measure_semantic else None
        })
    
    # 3. 向量化
    embeddings = await embedding_model.embed_documents(field_texts)
    
    # 4. 构建FAISS索引
    index = faiss.IndexFlatIP(embedding_dim)  # 使用点积相似度
    index.add(np.array(embeddings))
    
    # 5. 持久化
    index_path = f"data/vector_stores/{datasource_luid}.faiss"
    faiss.write_index(index, index_path)
    
    # 保存元数据
    metadata_path = f"data/vector_stores/{datasource_luid}.json"
    with open(metadata_path, 'w') as f:
        json.dump(field_metadata, f, ensure_ascii=False, indent=2)
```

### 映射配置文件（辅助）

```yaml
# config/field_mapping_hints.yaml
# 此配置文件由系统自动维护，提供映射提示但不强制执行

# 同义词提示（辅助LLM理解）
synonyms:
  销售额:
    - revenue
    - sales_amount
    - 营收
    - 收入
  地区:
    - region
    - area
    - district
    - 区域
  
# 常见映射模式（从历史学习）
common_patterns:
  - business_term: "销售额"
    technical_field: "[Sales].[Sales Amount]"
    frequency: 156
    success_rate: 0.98
    last_updated: "2025-01-15"
  
  - business_term: "地区"
    technical_field: "[Region].[Region Name]"
    frequency: 89
    success_rate: 0.95
    last_updated: "2025-01-14"

# 字段类别提示
category_hints:
  geographic:
    keywords: [地区, 区域, 城市, 省份, 国家]
    common_fields: ["Region", "City", "Province"]
  
  financial:
    keywords: [销售额, 利润, 成本, 收入]
    common_fields: ["Sales Amount", "Profit", "Cost"]
```

### LLM语义判断Prompt

```python
SEMANTIC_MAPPING_PROMPT = """你是一个Tableau字段映射专家。你的任务是将业务术语映射到正确的技术字段。

## 问题上下文
{question_context}

## 业务术语
{business_term}

## 候选字段 (Top-{k})
{candidates}

## 历史映射记录
{history_mappings}

## 映射提示（参考，非强制）
{mapping_hints}

## 字段类型提示
期望类型: {expected_type}

## 任务
请分析以上信息，选择最合适的技术字段。

## 分析步骤
1. 理解业务术语的含义
2. 分析问题上下文中的语义
3. **优先参考历史映射记录**（如果有高成功率的记录）
4. 参考映射提示中的同义词和常见模式
5. 比较候选字段的描述和示例值
6. 考虑字段类型是否匹配

## 重要提示
- 历史映射记录的权重最高（特别是成功率 > 0.9 的记录）
- 映射提示仅供参考，可以根据上下文选择忽略
- 最终决策基于语义理解，而非规则匹配

## 输出格式
请以JSON格式输出:
{{
  "technical_field": "选择的技术字段名",
  "confidence": 0.95,
  "reasoning": "详细的推理过程（说明为什么选择这个字段）",
  "alternatives": [
    {{"field": "备选字段1", "score": 0.85, "reason": "备选原因"}},
    {{"field": "备选字段2", "score": 0.75, "reason": "备选原因"}}
  ]
}}
"""
```

### 历史映射学习机制

#### 保存映射历史

```python
async def save_mapping_history(
    mapping: FieldMapping,
    question_context: str,
    datasource_luid: str,
    store: PersistentStore
) -> None:
    """
    保存映射历史到PersistentStore
    
    命名空间: ("field_mappings", datasource_luid)
    Key: hash(business_term + datasource_luid)
    """
    key = hashlib.md5(
        f"{mapping.business_term}_{datasource_luid}".encode()
    ).hexdigest()
    
    # 查询是否已存在
    existing = await store.get(
        namespace=("field_mappings", datasource_luid),
        key=key
    )
    
    if existing:
        # 更新使用次数
        existing["usage_count"] += 1
        await store.put(
            namespace=("field_mappings", datasource_luid),
            key=key,
            value=existing
        )
    else:
        # 创建新记录
        history = MappingHistory(
            business_term=mapping.business_term,
            technical_field=mapping.technical_field,
            datasource_luid=datasource_luid,
            question_context=question_context,
            confidence=mapping.confidence,
            timestamp=datetime.now()
        )
        await store.put(
            namespace=("field_mappings", datasource_luid),
            key=key,
            value=history.model_dump()
        )
```

#### 更新映射成功率

```python
async def update_mapping_success(
    business_term: str,
    datasource_luid: str,
    success: bool,
    store: PersistentStore
) -> None:
    """
    在查询执行后更新映射的成功率
    
    当查询成功执行时，调用此函数更新历史记录
    """
    key = hashlib.md5(
        f"{business_term}_{datasource_luid}".encode()
    ).hexdigest()
    
    history = await store.get(
        namespace=("field_mappings", datasource_luid),
        key=key
    )
    
    if history:
        if success:
            history["success_count"] += 1
        history["success_rate"] = history["success_count"] / history["usage_count"]
        
        await store.put(
            namespace=("field_mappings", datasource_luid),
            key=key,
            value=history
        )
        
        # 如果成功率高且使用频率高，更新配置文件
        if history["success_rate"] > 0.9 and history["usage_count"] >= 5:
            await update_mapping_hints_config(history)
```

#### 自动更新配置文件

```python
async def update_mapping_hints_config(
    history: MappingHistory
) -> None:
    """
    根据高质量的历史映射自动更新配置文件
    
    触发条件:
    - 成功率 > 0.9
    - 使用次数 >= 5
    
    更新内容:
    - 添加到 common_patterns
    - 更新 synonyms（如果发现新的同义词）
    """
    config_path = "config/field_mapping_hints.yaml"
    
    # 加载现有配置
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # 更新 common_patterns
    pattern = {
        "business_term": history.business_term,
        "technical_field": history.technical_field,
        "frequency": history.usage_count,
        "success_rate": history.success_rate,
        "last_updated": datetime.now().isoformat()
    }
    
    # 查找是否已存在
    existing_idx = None
    for idx, p in enumerate(config.get("common_patterns", [])):
        if p["business_term"] == history.business_term:
            existing_idx = idx
            break
    
    if existing_idx is not None:
        # 更新现有记录
        config["common_patterns"][existing_idx] = pattern
    else:
        # 添加新记录
        if "common_patterns" not in config:
            config["common_patterns"] = []
        config["common_patterns"].append(pattern)
    
    # 保存配置
    with open(config_path, 'w') as f:
        yaml.dump(config, f, allow_unicode=True)
```

#### 检索历史映射

```python
async def retrieve_mapping_history(
    business_term: str,
    datasource_luid: str,
    store: PersistentStore,
    top_k: int = 3
) -> List[MappingHistory]:
    """
    检索相关的历史映射记录
    
    策略:
    1. 精确匹配: 相同业务术语
    2. 模糊匹配: 相似业务术语 (使用向量相似度)
    3. 按成功率和使用频率排序
    """
    # 1. 精确匹配
    key = hashlib.md5(
        f"{business_term}_{datasource_luid}".encode()
    ).hexdigest()
    
    exact_match = await store.get(
        namespace=("field_mappings", datasource_luid),
        key=key
    )
    
    results = []
    if exact_match:
        results.append(MappingHistory(**exact_match))
    
    # 2. 模糊匹配 (可选)
    # TODO: 使用向量相似度查找相似的业务术语
    
    # 3. 排序
    results.sort(
        key=lambda x: (x.success_rate, x.usage_count),
        reverse=True
    )
    
    return results[:top_k]
```

### Task Planner Agent 集成

#### 修改后的执行流程

```python
class TaskPlannerAgent(BaseVizQLAgent):
    async def execute(self, state, runtime, model_config):
        understanding = state.get("understanding")
        metadata = state.get("metadata")
        
        # 1. 提取业务术语
        business_terms = self._extract_business_terms(understanding)
        
        # 2. 调用语义字段映射工具
        field_mapping_result = await self._call_semantic_mapping(
            business_terms=business_terms,
            question_context=understanding.original_question,
            metadata=metadata,
            field_type_hints=self._build_type_hints(understanding)
        )
        
        # 3. 准备输入数据 (包含映射结果)
        input_data = self._prepare_input_data(
            state=state,
            field_mapping_result=field_mapping_result
        )
        
        # 4. 调用LLM生成QueryPlanningResult
        # Prompt中直接使用映射结果，不再需要硬编码映射规则
        result = await self._execute_with_prompt(input_data, runtime, model_config)
        
        return self._process_result(result, state)
    
    def _extract_business_terms(self, understanding) -> List[str]:
        """从understanding中提取所有业务术语"""
        terms = []
        for sq in understanding.sub_questions:
            terms.extend(sq.mentioned_dimensions or [])
            terms.extend(sq.mentioned_measures or [])
            terms.extend(sq.mentioned_date_fields or [])
        return list(set(terms))  # 去重
    
    def _build_type_hints(self, understanding) -> Dict[str, str]:
        """构建字段类型提示"""
        hints = {}
        for sq in understanding.sub_questions:
            for dim in (sq.mentioned_dimensions or []):
                hints[dim] = "dimension"
            for mea in (sq.mentioned_measures or []):
                hints[mea] = "measure"
            for date in (sq.mentioned_date_fields or []):
                hints[date] = "date"
        return hints
```

#### 调整后的Prompt模板

```python
class TaskPlannerPrompt(VizQLPrompt):
    def get_specific_domain_knowledge(self) -> str:
        return """Resources: {original_question}, {sub_questions}, {field_mappings}, {metadata}

**Field mappings have been provided by the semantic mapping system:**
{field_mappings}

**Mapping confidence levels:**
- High (> 0.8): Use directly with confidence
- Medium (0.5-0.8): Use but note in rationale
- Low (< 0.5): Consider alternatives provided

**Your task:**
1. Use the provided technical_field from field_mappings
2. Generate Intent models with correct:
   - aggregation functions (for measures)
   - date functions (for date fields)
   - sorting and filtering

**Think step by step:**

Step 1: Review field mappings
- Check mapping confidence for each field
- Note any low-confidence mappings
- Review alternatives if confidence < 0.8

Step 2: Generate Intent models
- For dimensions: Use technical_field from mapping
  * Add aggregation ONLY if counting (COUNTD)
- For measures: Use technical_field + determine aggregation
  * Use aggregation from sub-question's measure_aggregations
  * Default to SUM if not specified
- For date fields: Use technical_field + determine date_function
  * Use date_function from sub-question's date_field_functions
  * Use extraction functions (YEAR/MONTH/DAY), not truncation

Step 3: Add filters and sorting
- Date filters: Use mapped date field + time_range from sub-question
- Other filters: Use mapped fields + filter conditions
- Sorting: Based on question requirements

**CRITICAL**: 
- Use technical_field from field_mappings (do not re-map)
- If mapping confidence is low, include alternatives in rationale
- Focus on generating correct Intent models, not field mapping
"""
```

### 字段语义推断系统（统一设计）

**详细设计请参考**：[字段语义推断系统详解](./design-appendix/field-semantics.md)

#### 核心思想

将**维度层级推断**和**度量语义推断**统一为**字段语义推断系统**，为所有字段（维度、度量、日期）添加丰富的语义信息。

#### 为什么需要？

**核心问题**：Tableau元数据缺乏语义信息

```
原始元数据的问题:
1. 字段名不清晰: "[Region].[一级地区]" - 什么是"一级"？
2. 缺少业务含义: "[Sales].[Sales Amount]" - 是金额还是数量？
3. 缺少关系信息: 字段之间的层级关系不明确
4. 样本太少: 只有1个示例值，无法理解值域
5. 缺少使用提示: 不知道常用的聚合方式
```

#### 统一的语义模型

```python
class FieldSemantics(BaseModel):
    """统一的字段语义模型（适用于所有字段类型）"""
    
    # 通用信息（所有字段）
    category: str                    # geographic, temporal, financial等
    subcategory: Optional[str]       # region/city, revenue/cost等
    business_meaning: str            # 业务含义描述
    
    # 维度特有
    level: Optional[int]             # 1-5 (仅维度)
    granularity: Optional[str]       # coarsest/fine (仅维度)
    parent: Optional[str]            # 父字段 (仅维度)
    child: Optional[str]             # 子字段 (仅维度)
    
    # 度量特有
    value_range: Optional[Dict]      # 值域 (仅度量)
    default_aggregation: Optional[str]  # 默认聚合（从元数据获取）
    
    # 历史学习（所有字段）
    usage_stats: Optional[Dict]      # 使用统计
```

#### 分阶段推断

| 阶段 | 内容 | 适用字段 | 方法 | 优先级 |
|------|------|---------|------|--------|
| **阶段1** | 基础语义推断 | 所有字段 | LLM | P0 (必需) |
| **阶段2** | 维度层级推断 | 维度字段 | LLM | P0 (必需) |
| **阶段3** | 度量增强 | 度量字段 | 统计 | P1 (推荐) |
| **阶段4** | 历史学习 | 所有字段 | 统计 | P1 (推荐) |

**详细实现请参考**：[字段语义推断系统详解](./design-appendix/field-semantics.md)

**解决方案**：维度层级推断

```python
# 推断前
field = {
    "name": "[Region].[一级地区]",
    "samples": ["华东", "华北", "华南"]
}

# 推断后
field = {
    "name": "[Region].[一级地区]",
    "samples": ["华东", "华北", "华南"],
    "category": "geographic",      # ⭐ 新增
    "level": 1,                     # ⭐ 新增 (最粗粒度)
    "granularity": "coarsest",      # ⭐ 新增
    "parent": null,                 # ⭐ 新增
    "child": "[Region].[二级地区]"  # ⭐ 新增
}
```

#### 维度层级推断 vs RAG

| 维度 | 维度层级推断 | RAG字段映射 |
|------|-------------|------------|
| **运行时机** | 系统初始化（一次性） | 每次查询 |
| **输入** | 原始元数据 | 业务术语 + 增强元数据 |
| **输出** | 增强的元数据 | 字段映射结果 |
| **作用** | 元数据增强 | 字段选择 |
| **是否必需** | 可选（但强烈推荐） | 必需 |

#### 是否可以省略维度层级推断？

**可以，但会影响RAG准确性**：

**场景1：元数据已包含层级信息**
```yaml
# 如果Tableau元数据本身就很清晰
fields:
  - name: "省份"
    samples: ["江苏省", "浙江省"]
  - name: "城市"
    samples: ["南京市", "杭州市"]

# 这种情况下，RAG可以直接从字段名判断
# 不需要维度层级推断
```

**场景2：元数据不清晰（常见）**
```yaml
# 实际情况往往是这样
fields:
  - name: "[Region].[一级地区]"  # 什么是"一级"？
    samples: ["华东", "华北"]
  - name: "[Region].[二级地区]"  # 什么是"二级"？
    samples: ["江苏省", "浙江省"]

# 这种情况下，维度层级推断很有价值
# 它能告诉RAG："一级地区"是大区级别，"二级地区"是省级别
```

#### 推荐的实现策略

**阶段1：MVP（最小可行产品）**
- ✅ 实现RAG字段映射（核心功能）
- ⏸️ 暂时跳过维度层级推断
- 📝 在字段富文本中只包含基本信息

**阶段2：增强版**
- ✅ 添加维度层级推断
- ✅ 将层级信息添加到向量索引
- ✅ RAG检索时利用层级信息

**阶段3：智能版**
- ✅ 维度层级推断结果持久化
- ✅ 支持增量更新
- ✅ 历史映射学习层级偏好

#### 实现建议

```python
# 1. 系统初始化时
async def initialize_datasource(datasource_luid: str):
    # 获取元数据
    metadata = await get_metadata(datasource_luid)
    
    # 检查是否已有增强元数据
    enhanced_metadata = await store.get(
        namespace=("metadata_enhanced", datasource_luid)
    )
    
    if not enhanced_metadata:
        # 运行维度层级推断
        hierarchy = await dimension_hierarchy_agent.execute(metadata)
        
        # 保存增强元数据
        enhanced_metadata = merge_metadata_with_hierarchy(metadata, hierarchy)
        await store.put(
            namespace=("metadata_enhanced", datasource_luid),
            value=enhanced_metadata
        )
    
    # 构建向量索引（使用增强元数据）
    await build_field_index(datasource_luid, enhanced_metadata)


# 2. RAG检索时
async def semantic_map_fields(business_terms, metadata):
    # 使用增强元数据（如果有）
    enhanced_metadata = await store.get(
        namespace=("metadata_enhanced", datasource_luid)
    ) or metadata
    
    # 向量检索（富文本包含层级信息）
    candidates = await vector_search(business_terms, enhanced_metadata)
    
    # LLM判断（可以利用层级信息）
    mappings = await llm_semantic_judge(candidates, question_context)
    
    return mappings
```

### 性能优化

#### 向量索引缓存

```python
class VectorStoreManager:
    def __init__(self):
        self._index_cache: Dict[str, faiss.Index] = {}
        self._metadata_cache: Dict[str, List[Dict]] = {}
    
    async def get_index(self, datasource_luid: str):
        """获取向量索引 (带缓存)"""
        if datasource_luid not in self._index_cache:
            # 从磁盘加载
            index_path = f"data/vector_stores/{datasource_luid}.faiss"
            if os.path.exists(index_path):
                self._index_cache[datasource_luid] = faiss.read_index(index_path)
            else:
                # 构建新索引
                await self.build_index(datasource_luid)
        
        return self._index_cache[datasource_luid]
```

#### 批量映射

```python
async def batch_map_fields(
    business_terms: List[str],
    question_context: str,
    metadata: TableauMetadata,
    datasource_luid: str
) -> FieldMappingResult:
    """
    批量映射多个业务术语
    
    优化:
    1. 一次性检索所有术语的候选字段
    2. 批量调用LLM (减少API调用次数)
    3. 并行处理独立的映射
    """
    # 1. 批量向量检索
    candidates_batch = await vector_store.batch_search(
        queries=business_terms,
        top_k=5
    )
    
    # 2. 批量历史检索
    history_batch = await asyncio.gather(*[
        retrieve_mapping_history(term, datasource_luid, store)
        for term in business_terms
    ])
    
    # 3. 批量LLM调用
    mappings = await llm.batch_invoke([
        build_mapping_prompt(term, candidates, history, question_context)
        for term, candidates, history in zip(
            business_terms, candidates_batch, history_batch
        )
    ])
    
    return FieldMappingResult(mappings=mappings)
```

---

## 关键技术选型

### 后端技术栈

| 技术 | 版本 | 用途 | 选择理由 |
|------|------|------|----------|
| **Python** | 3.11+ | 主要开发语言 | LangChain 生态、类型提示、异步支持 |
| **FastAPI** | 0.104+ | Web 框架 | 高性能、自动文档、类型安全 |
| **LangChain** | 1.0.3+ | LLM 框架 | 丰富的工具链、社区活跃 |
| **DeepAgents** | latest | Agent 编排 | 内置规划、文件系统、子代理委托 |
| **Pydantic** | 2.5+ | 数据验证 | 类型安全、自动验证、JSON 序列化 |
| **Pandas** | 2.1+ | 数据处理 | 强大的数据分析能力、生态成熟 |
| **FAISS** | 1.7+ | 向量检索 | 高性能、支持大规模索引 |
| **SQLite** | 3.40+ | 持久化存储 | 轻量级、无需额外服务 |

### 前端技术栈

| 技术 | 版本 | 用途 | 选择理由 |
|------|------|------|----------|
| **Vue 3** | 3.3+ | 前端框架 | Composition API、TypeScript 支持 |
| **TypeScript** | 5.0+ | 类型系统 | 类型安全、IDE 支持 |
| **Vite** | 5.0+ | 构建工具 | 快速开发、HMR |
| **Pinia** | 2.1+ | 状态管理 | 简洁、TypeScript 友好 |
| **Markdown-it** | 13.0+ | Markdown 渲染 | 可扩展、插件丰富 |

### LLM 选择

| 模型 | 上下文 | 用途 | 选择理由 |
|------|--------|------|----------|
| **Claude 3.5 Sonnet** | 200k | 主要模型 | 强大推理、Prompt Caching |
| **GPT-4o-mini** | 128k | 轻量任务 | 成本低、速度快 |
| **本地模型** | 可选 | 备用方案 | 数据隐私、成本控制 |

### Embedding 模型

| 模型 | 维度 | 用途 | 选择理由 |
|------|------|------|----------|
| **bce-embedding-base-v1** | 768 | 中文优先 | 中文效果好、支持 GPU |
| **text-embedding-3-large** | 3072 | 英文优先 | OpenAI 官方、效果好 |

---

## 目录结构

```
tableau_assistant/
├── src/
│   ├── deepagents/                    # DeepAgents 相关
│   │   ├── agent_factory.py           # Agent 创建工厂
│   │   ├── subagents/                 # 子代理定义
│   │   │   ├── boost_agent.py
│   │   │   ├── understanding_agent.py
│   │   │   ├── planning_agent.py
│   │   │   ├── insight_agent.py
│   │   │   └── replanner_agent.py
│   │   ├── middleware/                # 自定义中间件
│   │   │   ├── tableau_metadata.py
│   │   │   ├── vizql_query.py
│   │   │   └── application_cache.py
│   │   ├── tools/                     # Tableau 工具
│   │   │   ├── vizql_tools.py
│   │   │   ├── metadata_tools.py
│   │   │   ├── semantic_mapping.py
│   │   │   └── date_tools.py
│   │   └── backends/                  # 后端配置
│   │       └── composite_backend.py
│   │
│   ├── progressive_insight/           # 渐进式洞察系统
│   │   ├── coordinator.py
│   │   ├── data_profiler.py
│   │   ├── semantic_chunker.py
│   │   ├── chunk_analyzer.py
│   │   ├── insight_accumulator.py
│   │   └── insight_synthesizer.py
│   │
│   ├── semantic_mapping/              # 语义字段映射
│   │   ├── vector_store.py
│   │   ├── field_indexer.py
│   │   └── semantic_mapper.py
│   │
│   ├── components/                    # 核心组件（100% 复用）
│   │   ├── query_builder.py
│   │   ├── query_executor.py
│   │   ├── data_processor.py
│   │   ├── metadata_manager.py
│   │   └── date_parser.py
│   │
│   ├── models/                        # 数据模型
│   │   ├── state.py
│   │   ├── question.py
│   │   ├── query.py
│   │   ├── insight.py
│   │   └── result.py
│   │
│   ├── api/                           # FastAPI 路由
│   │   ├── chat.py
│   │   ├── stream.py
│   │   └── health.py
│   │
│   └── utils/                         # 工具函数
│       ├── cache.py
│       ├── auth.py
│       └── logging.py
│
├── tests/                             # 测试
│   ├── test_subagents/
│   ├── test_middleware/
│   ├── test_tools/
│   └── test_integration/
│
├── data/                              # 数据目录
│   ├── vector_stores/                 # 向量索引
│   ├── cache/                         # 缓存文件
│   └── persistent_store.db            # SQLite 数据库
│
└── docs/                              # 文档
    └── design-appendix/               # 设计文档附录
```

---

## 性能设计

### 性能目标

| 指标 | 当前系统 | 目标系统 | 提升 |
|------|---------|---------|------|
| 分析时间 | 180秒 | 60秒 | 3倍 |
| Token 使用 | 30k | 15k | 50% |
| 首次反馈 | 60秒 | 6秒 | 10倍 |
| 缓存命中率 | 20% | 60% | 3倍 |
| 成本 | $1.00 | $0.30 | 70% |

### 性能优化策略

**1. 并行执行**
- 独立子查询并行执行
- 多个 Insight Agent 并行分析
- 使用 asyncio.gather() 实现

**2. 智能缓存**
- L1: Prompt Caching（Anthropic）
- L2: Application Cache（所有模型）
- L3: Query Result Cache
- L4: Semantic Cache（可选）

**3. 渐进式分析**
- 大数据集智能分块
- AI 驱动的早停机制
- 流式输出洞察

**4. 上下文管理**
- 自动总结长对话
- 文件系统存储大数据
- 只传递结构化结果

### 缓存策略详情

| 缓存类型 | 存储 | 有效期 | Key 生成 | 用途 |
|---------|------|--------|---------|------|
| Prompt Cache | Anthropic | 5分钟 | 自动 | 系统提示词 |
| LLM Response | SQLite | 1小时 | hash(prompt+input) | LLM 响应 |
| Query Result | SQLite | 会话期间 | hash(query_params) | 查询结果 |
| Metadata | SQLite | 1小时 | datasource_luid | 元数据 |
| Field Index | Disk | 永久 | datasource_luid | 向量索引 |

---

## 错误处理

### 错误分类

**可重试错误**：
- 网络超时
- 临时服务不可用
- 速率限制

**不可重试错误**：
- 认证失败
- 参数错误
- 权限不足

### 重试策略

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((TimeoutError, ConnectionError))
)
async def call_llm(prompt: str) -> str:
    """带重试的 LLM 调用"""
    return await llm.ainvoke(prompt)
```

### 降级策略

1. **查询降级** - 减少维度、使用采样
2. **缓存降级** - 使用过期缓存
3. **功能降级** - 跳过可选功能
4. **部分失败** - 返回部分结果

---

## 安全设计

### 认证授权

- **Tableau 认证** - JWT token
- **API 认证** - OAuth2
- **权限控制** - 基于 Tableau 权限

### 数据安全

- **敏感信息** - 不记录到日志
- **临时文件** - 自动清理
- **缓存加密** - 敏感数据加密存储

---

## 监控设计

### 监控指标

**系统指标**：
- CPU、内存、磁盘使用率
- 网络流量

**应用指标**：
- QPS、响应时间
- 错误率、缓存命中率
- LLM 调用次数、Token 消耗

**业务指标**：
- 查询成功率
- 重规划率
- 用户满意度

### 告警规则

- 错误率 > 5% → 警告
- P95 响应时间 > 30秒 → 警告
- 缓存命中率 < 40% → 提示

---

## 附录索引

详细的设计文档请参考以下附录：

- [子代理设计详解](./design-appendix/subagent-design.md) - 5个子代理的详细设计
- [中间件设计详解](./design-appendix/middleware-design.md) - 3个自定义中间件的详细设计
- [工具设计详解](./design-appendix/tools-design.md) - Tableau工具集的详细设计
- [渐进式洞察系统](./design-appendix/progressive-insight.md) - 渐进式洞察分析的详细设计
- [语义字段映射](./design-appendix/semantic-mapping.md) - RAG + LLM 语义映射的详细设计
- [缓存系统设计](./design-appendix/cache-design.md) - 四层缓存架构的详细设计
- [数据模型设计](./design-appendix/data-models.md) - 完整的数据模型定义
- [API设计](./design-appendix/api-design.md) - REST API和内部接口设计

---

**设计文档版本**: v1.0  
**最后更新**: 2025-01-15  
**文档状态**: 待审核
