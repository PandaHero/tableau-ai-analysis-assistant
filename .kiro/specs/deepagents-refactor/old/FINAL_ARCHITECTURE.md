# Tableau Assistant DeepAgents 重构 - 最终架构

## 📋 文档版本
- 版本：2.0
- 日期：2024
- 状态：已审查，待实施

---

## 🎯 项目目标

将 Tableau Assistant 从自定义 LangGraph 架构迁移到 DeepAgents 框架，同时：
1. ✅ **保护投资**：核心组件 100% 复用
2. ✅ **架构升级**：利用 DeepAgents 的自动优化
3. ✅ **功能增强**：实现渐进式累积洞察系统
4. ✅ **技术迁移**：从 Polars 迁移到 Pandas

---

## 🏗️ 最终架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI REST API                             │
│                    (/api/chat, /api/chat/stream)                     │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      DeepAgent (主编排器)                            │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              内置中间件（5个）                               │   │
│  │  ├─ TodoListMiddleware (高层任务规划)                       │   │
│  │  ├─ FilesystemMiddleware (文件管理)                         │   │
│  │  ├─ SubAgentMiddleware (子代理委托)                         │   │
│  │  ├─ SummarizationMiddleware (自动总结)                      │   │
│  │  └─ AnthropicPromptCachingMiddleware (缓存)                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              自定义中间件（2个）                             │   │
│  │  ├─ TableauMetadataMiddleware                               │   │
│  │  └─ VizQLQueryMiddleware                                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              子代理（5个）                                   │   │
│  │  ├─ boost-agent (问题优化)                                  │   │
│  │  ├─ understanding-agent (问题理解)                          │   │
│  │  ├─ planning-agent (查询规划)                               │   │
│  │  ├─ insight-agent ⭐ (渐进式洞察分析)                       │   │
│  │  └─ replanner-agent ⭐ (智能重规划)                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              工具（5个）                                     │   │
│  │  ├─ vizql_query (QueryExecutor + DataProcessor)             │   │
│  │  ├─ get_metadata (MetadataManager)                          │   │
│  │  ├─ semantic_map_fields ⭐ (RAG + LLM)                      │   │
│  │  ├─ parse_date (DateParser)                                 │   │
│  │  └─ build_vizql_query (QueryBuilder)                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    核心组件层（100% 复用）                           │
│                                                                       │
│  ├─ QueryBuilder ✅                                                  │
│  ├─ QueryExecutor ✅                                                 │
│  ├─ DataProcessor ✅ (Pandas)                                        │
│  ├─ MetadataManager ✅                                               │
│  ├─ DateParser ✅                                                    │
│  ├─ QuestionBoostAgent ✅                                            │
│  └─ 所有 Pydantic 模型 ✅                                            │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│              渐进式洞察系统 ⭐ ("AI 宝宝吃饭")                       │
│                                                                       │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                    Coordinator (主持人)                        │  │
│  │  - 评估数据规模和复杂度                                        │  │
│  │  - 决定分析策略（直接 vs 渐进式）                              │  │
│  │  - 监控分析质量                                                │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ↓                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Data Preparation Layer (准备层)                   │  │
│  │                                                                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │  │
│  │  │   Data      │  │  Semantic   │  │  Adaptive   │           │  │
│  │  │ Profiler    │→ │  Chunker    │→ │  Optimizer  │           │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘           │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ↓                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Analysis Layer (分析层)                           │  │
│  │                                                                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │  │
│  │  │   Chunk     │  │  Pattern    │  │  Anomaly    │           │  │
│  │  │  Analyzer   │→ │  Detector   │→ │  Detector   │           │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘           │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ↓                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │            Accumulation Layer (累积层)                         │  │
│  │                                                                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │  │
│  │  │  Insight    │  │  Quality    │  │  Dedup &    │           │  │
│  │  │ Accumulator │→ │  Filter     │→ │  Merge      │           │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘           │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                              ↓                                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │            Synthesis Layer (合成层)                            │  │
│  │                                                                 │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │  │
│  │  │  Insight    │  │  Summary    │  │ Recommend   │           │  │
│  │  │ Synthesizer │→ │  Generator  │→ │  Generator  │           │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘           │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                  ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    Backend (CompositeBackend)                         │
│                                                                       │
│  ├─ StateBackend (临时文件)                                          │
│  └─ StoreBackend (持久化)                                            │
│      ├─ /metadata/*                                                  │
│      ├─ /hierarchies/*                                               │
│      ├─ /preferences/*                                               │
│      └─ /insights/* ⭐ (累积洞察)                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔑 核心特性

### 1. DeepAgents 框架优势
- ✅ **TodoListMiddleware**：自动管理工作流步骤
- ✅ **FilesystemMiddleware**：自动处理大结果
- ✅ **SummarizationMiddleware**：自动总结长上下文
- ✅ **AnthropicPromptCachingMiddleware**：节省 50-90% 成本
- ✅ **SubAgentMiddleware**：自动并行执行

### 2. 渐进式累积洞察（"AI 宝宝吃饭"）⭐
- 🍽️ **智能分块**：按优先级分块（异常值 → Top → 中间 → 尾部）
- 🧠 **AI 驱动累积**：AI 决定如何累积洞察
- 🎯 **智能选择**：AI 决定下一口吃什么
- ⏹️ **早停机制**：AI 判断问题已回答，自动停止
- 📊 **流式输出**：每个洞察立即输出
- 🔄 **Replan 集成**：发现异常时触发重新规划

### 3. 语义字段映射（RAG + LLM）⭐
- 🔍 **向量检索**：快速找到候选字段
- 🧠 **LLM 判断**：理解上下文选择最佳匹配
- 🌐 **多语言支持**：处理同义词和多语言
- 📚 **上下文感知**：考虑问题上下文

### 4. 核心组件 100% 复用
- ✅ **QueryBuilder**：查询构建逻辑完全保留
- ✅ **QueryExecutor**：查询执行逻辑完全保留
- ✅ **DataProcessor**：数据处理逻辑完全保留（迁移到 Pandas）
- ✅ **MetadataManager**：元数据管理逻辑完全保留
- ✅ **DateParser**：日期解析逻辑完全保留
- ✅ **QuestionBoostAgent**：问题优化逻辑完全保留

---

## 📊 完整功能清单

### ✅ 已实现（约 60%）
1. 问题优化（Question Boost）
2. 问题理解（Understanding）
3. 查询规划（Planning）
4. 查询执行（Query Execution）
5. 数据处理（Data Processing）
6. 元数据管理（Metadata Management）
7. 日期解析（Date Parsing）
8. 持久化存储（Persistent Storage）

### ⭐ 需要实现（约 40%）
1. **渐进式累积洞察系统**（核心功能）
   - Coordinator（主持人）
   - Data Profiler（数据画像）
   - Semantic Chunker（语义分块器）
   - Intelligent Priority Chunking（智能优先级分块）
   - AI-Driven Insight Accumulation（AI 驱动的洞察累积）
   - Next Bite Selection（下一口选择）
   - Quality Filter（质量过滤器）
   - Insight Synthesizer（洞察合成器）
   - Early Stop Mechanism（早停机制）
   - Streaming Output（流式输出）
   - Replan Integration（Replan 集成）

2. **语义字段映射**（RAG + LLM）
   - SemanticFieldMapper
   - 向量存储集成
   - LLM 语义判断

3. **增强版 Insight Agent**
   - 集成渐进式分析
   - 高级分析能力
   - 累积洞察管理

4. **增强版 Replanner Agent**
   - 智能决策逻辑
   - 交叉分析决策
   - 异常调查决策
   - 智能下钻决策

5. **高级分析功能**（可选）
   - 贡献度分析
   - 异常检测
   - 趋势分析
   - 相关性分析

---

## 🚀 实施计划

### Phase 0：准备工作（2-3 天）
- [ ] Polars 到 Pandas 迁移
  - [ ] 更新 DataProcessor
  - [ ] 更新所有 Processors
  - [ ] 更新 QueryResult 模型
  - [ ] 更新测试

### Phase 1：DeepAgents 架构迁移（2-3 周）
- [ ] 创建 DeepAgent 工厂
- [ ] 实现 5 个子代理
  - [ ] boost-agent
  - [ ] understanding-agent
  - [ ] planning-agent
  - [ ] insight-agent（基础版）
  - [ ] replanner-agent（基础版）
- [ ] 实现 2 个自定义中间件
  - [ ] TableauMetadataMiddleware
  - [ ] VizQLQueryMiddleware
- [ ] 封装 5 个工具
  - [ ] vizql_query
  - [ ] get_metadata
  - [ ] parse_date
  - [ ] build_vizql_query
  - [ ] semantic_map_fields（基础版）
- [ ] 配置 CompositeBackend
- [ ] API 集成
- [ ] 测试和验证

### Phase 2：渐进式累积洞察系统（2-3 周）⭐
- [ ] Coordinator（主持人）
- [ ] Data Profiler（数据画像）
- [ ] Semantic Chunker（语义分块器）
- [ ] Intelligent Priority Chunking（智能优先级分块）
- [ ] Chunk Analyzer（块分析器）
- [ ] AI-Driven Insight Accumulation（AI 驱动的洞察累积）
- [ ] Next Bite Selector（下一口选择器）
- [ ] Quality Filter（质量过滤器）
- [ ] Insight Synthesizer（洞察合成器）
- [ ] Early Stop Decider（早停决策器）
- [ ] Streaming Output（流式输出）
- [ ] Replan Integration（Replan 集成）
- [ ] 测试和优化

### Phase 3：功能增强（3-4 周）
- [ ] 语义字段映射（RAG + LLM）（1 周）
- [ ] 增强版 Insight Agent（1-2 周）
- [ ] 增强版 Replanner Agent（1 周）
- [ ] 测试和优化

### Phase 4：高级功能（可选）（2-3 周）
- [ ] 贡献度分析
- [ ] 异常检测
- [ ] 趋势分析
- [ ] 相关性分析

### Phase 5：锦上添花（可选）（1-2 周）
- [ ] 可视化建议
- [ ] 自然语言生成
- [ ] 多语言支持

**总工作量：11-16 周**

---

## 📈 预期收益

### 1. 性能提升
- **分析时间**：从 10 分钟降到 2 分钟（5x 提升）
- **Token 使用**：从 100K 降到 20K（5x 节省）
- **首次反馈**：从 10 分钟降到 10 秒（60x 提升）
- **准确率**：从 85% 提升到 95%（+10%）

### 2. 成本节省
- **LLM 成本**：节省 50-90%（Anthropic Prompt Caching）
- **开发成本**：减少 30-40% 自定义代码
- **维护成本**：减少 70% 维护工作

### 3. 用户体验
- **实时反馈**：流式输出，用户实时看到进度
- **智能分析**：AI 驱动的洞察累积和选择
- **早停机制**：避免无效分析，节省时间

---

## 🔗 相关文档

1. **PROJECT_AUDIT.md** - 项目全面审查
2. **ARCHITECTURE_REVIEW.md** - 架构审查和问题清单
3. **COMPONENT_REUSE.md** - 核心组件 100% 复用策略
4. **SEMANTIC_FIELD_MAPPING.md** - 语义字段映射升级方案
5. **progressive-insight-analysis/design.md** - 渐进式累积洞察系统设计
6. **requirements.md** - 需求文档
7. **design.md** - 详细设计文档

---

## ✅ 确认清单

- [x] 核心组件 100% 复用
- [x] Polars 迁移到 Pandas
- [x] 5 个子代理（boost, understanding, planning, insight, replanner）
- [x] 2 个自定义中间件（TableauMetadata, VizQLQuery）
- [x] 5 个工具（vizql_query, get_metadata, semantic_map_fields, parse_date, build_vizql_query）
- [x] 渐进式累积洞察系统（"AI 宝宝吃饭"）
- [x] 语义字段映射（RAG + LLM）
- [x] Boost Agent 由前端控制触发
- [x] 子代理可以使用不同的 LLM 模型

---

**架构已确认，准备开始实施！** 🚀
