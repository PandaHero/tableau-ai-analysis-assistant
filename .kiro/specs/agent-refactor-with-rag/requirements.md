# 需求文档

## 简介

本文档定义了 Tableau Assistant 项目的 Agent 重构需求，整合现有的 RAG 增强功能和 LangChain/LangGraph 中间件系统。目标是构建一个统一的、可扩展的 Agent 架构，实现以下核心能力：

1. **统一的中间件架构**：基于 LangChain/LangGraph 的中间件系统，提供重试、总结、文件系统等通用能力
2. **RAG 集成**：将已实现的 RAG 功能（语义映射、字段索引、Rerank）无缝集成到 Agent 工作流中
3. **工具化设计**：所有 Agent 节点通过工具系统交互，便于扩展和测试
4. **生产级质量**：完整的错误处理、可观测性和性能优化

### 项目背景

**当前状态**：
- 已实现 RAG 增强功能（SemanticMapper、FieldIndexer、Reranker 等）
- 已有 Agent 节点（Understanding、Planning、Insight、Replanner 等）
- 缺少统一的中间件架构和工具化封装

**目标收益**：
- Agent 能力增强：自动重试、对话总结、大结果处理
- 字段映射准确率提升 10-20%（通过 RAG + Rerank）
- LLM 调用成本降低 50-70%（通过缓存和智能跳过）
- 代码可维护性提升（统一架构、清晰职责）

### 技术栈

| 组件 | 方案 | 说明 |
|-----|------|------|
| Agent 框架 | LangGraph StateGraph | 工作流编排 |
| 中间件 | LangChain AgentMiddleware | 通用能力增强 |
| 向量存储 | FAISS | 本地免费，已集成 |
| Embedding | 智谱 AI embedding-2 | 付费，国内可用 |
| 持久化 | SQLite (LangGraph Store) | 已集成 |
| 元数据 API | VizQL Data Service + GraphQL | 混合策略 |

## 术语表

- **Agent**: 基于 LLM 的智能代理，执行特定任务
- **Middleware（中间件）**: 在 Agent 执行过程中提供通用能力（重试、总结等）
- **StateGraph（状态图）**: LangGraph 的状态图，用于编排工作流
- **Tool（工具）**: Agent 可调用的功能单元
- **RAG**: Retrieval-Augmented Generation，检索增强生成
- **SemanticMapper（语义映射器）**: 将业务术语映射到技术字段
- **Reranker（重排序器）**: 对检索结果进行二次排序
- **VizQL**: Tableau 的可视化查询语言
- **Published Datasource（发布数据源）**: Tableau 发布的数据源
- **Dimension（维度）**: 维度字段，用于分组（GROUP BY）
- **Measure（度量）**: 度量字段，用于聚合（SUM/AVG 等）
- **Table Calculation（表计算）**: 在查询结果上进行的二次计算


## 需求列表

### 需求 1: 中间件架构基础

**用户故事:** 作为开发者，我希望有一个统一的中间件架构，以便所有 Agent 都能受益于重试、总结、文件处理等通用能力。

**优先级**: P0（核心架构）

**中间件来源说明**：
- **来自 LangChain（直接使用）**：TodoListMiddleware、SummarizationMiddleware、HumanInTheLoopMiddleware、ModelRetryMiddleware、ToolRetryMiddleware
- **自主实现（生产级代码）**：FilesystemMiddleware、PatchToolCallsMiddleware

#### 验收标准

1. 当创建 Agent 时，Agent_Factory 应配置包含以下中间件的中间件栈：TodoListMiddleware、SummarizationMiddleware、HumanInTheLoopMiddleware（可选）、ModelRetryMiddleware、ToolRetryMiddleware、FilesystemMiddleware（自定义）、PatchToolCallsMiddleware（自定义）
2. 当配置中间件时，Agent_Factory 应同时支持 LangChain 内置中间件（来自 langchain.agents.middleware）和自定义实现的中间件（来自 tableau_assistant.src.middleware）
3. 当提供中间件配置时，Agent_Factory 应允许通过配置字典自定义中间件参数（summarization_token_threshold、messages_to_keep、filesystem_token_limit、model_max_retries、tool_max_retries、interrupt_on）
4. 当创建 Agent 时，Agent_Factory 应使用 create_react_agent 返回已应用中间件的编译后 LangGraph StateGraph
5. 当中间件执行失败时，Agent_Factory 应记录错误并继续执行剩余中间件（优雅降级）

### 需求 2: 工作流编排

**用户故事:** 作为开发者，我希望有一个定义良好的工作流编排，以便 Agent 节点按正确顺序执行并正确管理状态。

**优先级**: P0（核心架构）

**说明**：采用纯语义中间层架构，移除 Planning Agent。原 Planning Agent 的职责由确定性代码组件承担：
- **FieldMapper**（RAG + LLM）：字段映射
- **ImplementationResolver**（代码）：判断表计算/LOD + addressing
- **ExpressionGenerator**（代码）：生成 VizQL 表达式

**架构变更**：
```
旧架构: Boost → Understanding → Planning → Execute → Insight → Replanner
新架构: Boost → Understanding → QueryBuilder → Execute → Insight → Replanner
                    ↓                ↓
              SemanticQuery    FieldMapper + ImplementationResolver + ExpressionGenerator
              (LLM 输出)       (确定性代码)
```

#### 验收标准

1. 当创建工作流时，StateGraph 应定义以下节点：Boost、Understanding、QueryBuilder（非 LLM）、Execute、Insight、Replanner
2. 当工作流开始执行时，StateGraph 应遵循以下顺序：Boost → Understanding → QueryBuilder → Execute → Insight → Replanner
3. 当 boost_question 标志为 False 时，StateGraph 应跳过 Boost 节点，从 Understanding 开始
4. 当 Replanner 决定重规划（should_replan=True 且 replan_count < max）时，StateGraph 应路由回 Understanding 节点
5. 当 Replanner 决定不重规划或 replan_count 达到最大值时，StateGraph 应路由到 END 节点
6. 当状态转换发生时，StateGraph 应保留所有累积数据（insights、results、errors）
7. 当 QueryBuilder 节点执行时，应依次调用 FieldMapper、ImplementationResolver、ExpressionGenerator 组件

### 需求 3: 工具系统设计

**用户故事:** 作为开发者，我希望所有 Agent 能力都以工具形式暴露，以便 Agent 可以通过统一接口交互。

**优先级**: P0（核心架构）

#### 验收标准

1. 当定义工具时，Tool_System 应使用带有正确类型注解和文档字符串的 LangChain @tool 装饰器
2. 当调用工具时，Tool_System 应使用 Pydantic 模型验证输入参数
3. 当工具执行失败时，Tool_System 应返回包含错误类型和消息的结构化错误响应
4. 当注册工具时，Tool_System 应按 Agent 节点分组工具（boost_tools、understanding_tools、query_builder_tools 等）
5. 当工具返回大输出（>20000 tokens）时，Tool_System 应自动保存到文件系统并返回文件引用


### 需求 4: RAG 工具集成（语义字段映射）

**用户故事:** 作为开发者，我希望 RAG 能力以组件形式暴露，以便 FieldMapper 可以使用语义映射进行字段解析。

**优先级**: P0（核心功能）

**说明**：RAG 组件提供语义字段映射能力（业务术语 → 技术字段）。字段索引包含维度层级信息以增强检索准确性。在纯语义中间层架构中，FieldMapper 组件使用 RAG 进行字段映射。

#### 验收标准

1. 当 FieldMapper 需要字段映射时，RAG_Tools 应提供 semantic_map_fields 方法，接受业务术语并返回匹配的技术字段
2. 当调用 semantic_map_fields 时，RAG_Tools 应使用现有的 SemanticMapper 进行向量检索和可选的 LLM 判断
3. 当向量搜索 top-1 置信度高于 0.9 时，RAG_Tools 应跳过 LLM 判断直接返回（快速路径）
4. 当映射置信度低于 0.7 时，RAG_Tools 应返回带置信度分数的 top-3 备选项
5. 当执行字段映射时，RAG_Tools 应将结果缓存到 SQLite，TTL 为 1 小时
6. 当请求批量映射时，RAG_Tools 应使用 asyncio 并发处理最多 5 个术语
7. 当构建字段索引时，RAG_Tools 应包含维度层级信息（category、level、granularity）以增强检索准确性
8. 当返回映射结果时，RAG_Tools 应包含字段的维度层级信息（如 category="geographic"、level=2、granularity="province"）

### 需求 4.1: 维度层级推断 RAG 增强

**用户故事:** 作为开发者，我希望使用 RAG 增强维度层级推断，以便提高推断准确率并降低 LLM 成本。

**优先级**: P1（重要功能）

**说明**：增强现有的 DimensionHierarchyAgent，通过检索历史推断模式作为 few-shot 示例，提高推断准确率。成功的推断结果会被存储为新模式供未来检索。

#### 验收标准

1. 当推断维度层级时，Hierarchy_Inferrer 应首先从历史推断中检索相似度 > 0.8 的维度模式
2. 当找到相似模式时，Hierarchy_Inferrer 应将 top-3 模式作为 few-shot 示例提供给 LLM
3. 当推断成功完成时，Hierarchy_Inferrer 应将结果存储为新模式供未来检索使用
4. 当构建模式索引时，Hierarchy_Inferrer 应包含字段名、数据类型、样本值、唯一值数量和推断的 category/level
5. 当不存在相似模式（相似度 < 0.8）时，Hierarchy_Inferrer 应回退到纯 LLM 推断

### 需求 5: 元数据工具

**用户故事:** 作为开发者，我希望 Agent 可以通过工具访问数据源元数据，以便在 Planning 和 Boost 阶段获取字段信息。

**优先级**: P0（核心功能）

**说明**：元数据工具是对现有 MetadataManager 组件的薄封装。MetadataManager 已经实现了完整的元数据获取、缓存（SQLite）、智能增强（维度层级推断）和日期格式检测功能。工具层只需要将 MetadataManager 的能力暴露给 Agent 调用。

**架构关系**：
```
Agent (LLM) 
    ↓ 调用
@tool get_metadata()  ← 薄封装，定义输入/输出 schema
    ↓ 委托
MetadataManager       ← 已实现：缓存、增强、降级等所有逻辑
    ↓ 使用
StoreManager          ← SQLite 缓存
```

#### 验收标准

1. 当 Agent 需要元数据时，Metadata_Tools 应提供 get_metadata 工具，该工具委托给 MetadataManager.get_metadata_async() 方法
2. 当定义 get_metadata 工具时，Metadata_Tools 应使用 @tool 装饰器并定义清晰的输入参数（use_cache: bool = True, enhance: bool = True）和返回类型
3. 当工具被调用时，Metadata_Tools 应将 MetadataManager 返回的 Metadata 对象转换为 LLM 友好的格式（字段列表摘要，而非完整对象）
4. 当返回结果时，Metadata_Tools 应包含字段的关键信息：name、fieldCaption、role、dataType、category、level、granularity、sample_values（前 5 个）
5. 当字段数量超过 50 时，Metadata_Tools 应返回摘要信息并提示 Agent 可以使用 filter 参数按 role 或 category 过滤

### 需求 6: 日期处理工具

**用户故事:** 作为开发者，我希望日期处理能力以工具形式暴露，以便 Agent 可以解析日期表达式和检测日期格式。

**优先级**: P1（重要功能）

**说明**：日期工具是对现有 DateManager 组件的薄封装。DateManager 已经实现了日期计算（DateCalculator）、日期解析（DateParser）和日期格式检测（DateFormatDetector）功能。

**架构关系**：
```
Agent (LLM)
    ↓ 调用
@tool parse_date() / @tool detect_date_format()  ← 薄封装
    ↓ 委托
DateManager                                       ← 已实现：计算、解析、格式检测
    ├── DateCalculator (相对日期计算)
    ├── DateParser (TimeRange → 日期范围)
    └── DateFormatDetector (STRING 字段格式检测)
```

#### 验收标准

1. 当 Understanding Agent 遇到日期表达式时，Date_Tools 应提供 parse_date 工具，委托给 DateManager.parse_time_range() 方法
2. 当 parse_date 接收相对表达式（如"最近3个月"）时，Date_Tools 应返回计算后的开始/结束日期（YYYY-MM-DD 格式）
3. 当 parse_date 接收绝对表达式（如"2024年1月"）时，Date_Tools 应解析并返回日期范围
4. 当日期解析失败时，Date_Tools 应返回 null 和错误消息，而不是抛出异常
5. 当需要检测 STRING 字段的日期格式时，Date_Tools 应提供 detect_date_format 工具，委托给 DateManager.detect_field_date_format() 方法
6. 当检测到日期格式时，Date_Tools 应返回格式类型（ISO_DATE、US_DATE、EU_DATE 等）和转换建议

### 需求 7: 查询执行工具

**用户故事:** 作为开发者，我希望查询执行以工具形式暴露，以便 Execute 节点可以与 VizQL Data Service 交互。

**优先级**: P0（核心功能）

**说明**：Execute Node 是非 LLM 节点，执行确定性的查询转换和 API 调用。VizQL API 目前不支持分页功能。

#### 验收标准

1. 当 Execute 节点需要运行查询时，Query_Tools 应提供 build_vizql_query 工具，将 QueryPlan 转换为 VizQL Query 格式（DimensionIntent → DimensionField、MeasureIntent → MeasureField、FilterIntent → Filter、TableCalcIntent → TableCalcField）
2. 当 Execute 节点需要运行查询时，Query_Tools 应提供 execute_vizql_query 工具，调用 VizQL Data Service /query-datasource API
3. 当查询执行成功时，Query_Tools 应返回包含数据、行数和执行时间的 QueryResult
4. 当查询执行失败时，Query_Tools 应返回包含错误代码和消息的结构化错误
5. 当查询结果较大时，Query_Tools 应返回完整结果（VizQL API 不支持分页），并依赖 FilesystemMiddleware 处理大结果

### 需求 7.1: 表计算和 LOD 计算支持

**用户故事:** 作为开发者，我希望 QueryBuilder 支持表计算和 LOD 计算，以便能够处理复杂的分析查询。

**优先级**: P0（核心功能）

**说明**：需要完善 QueryBuilder 以支持 VizQL Data Service 的表计算和 LOD 计算接口。OpenAPI 文档已更新，需要根据新接口调整实现。

**参考文档**：
- `openapi.json`（VizQL Data Service API 规范）
- `design-appendix-query-builder.md`（QueryBuilder 实现细节）

#### 验收标准

**表计算支持：**
1. 当 QueryPlan 包含 TableCalcIntent 时，QueryBuilder 应将其转换为 VizQL TableCalcField 格式
2. 当构建表计算时，QueryBuilder 应支持以下类型：RUNNING_TOTAL（累计总计）、RANK（排名）、MOVING_CALCULATION（移动计算）、PERCENT_OF_TOTAL（总计百分比）、DIFFERENCE_FROM（差异）、PERCENT_DIFFERENCE_FROM（百分比差异）、CUSTOM（自定义计算）
3. 当 TableCalcIntent 的 table_calc_type 为 CUSTOM 时，QueryBuilder 应使用 calculation_expression 字段生成计算表达式
4. 当构建 TableCalcField 时，QueryBuilder 应正确设置 tableCalculation.dimensions 用于指定计算方向

**LOD 计算支持：**
5. 当 QueryPlan 包含 LODIntent 时，QueryBuilder 应将其转换为 VizQL CalculatedField 格式（使用 calculation 属性）
6. 当构建 LOD 计算时，QueryBuilder 应支持以下类型：FIXED（固定粒度）、INCLUDE（包含维度）、EXCLUDE（排除维度）
7. 当构建 LOD 表达式时，QueryBuilder 应生成正确的语法：`{TYPE [dim1], [dim2] : AGG([measure])}`
8. 当 LOD 表达式包含多个维度时，QueryBuilder 应使用逗号分隔维度列表

**错误处理：**
9. 当表计算或 LOD 计算参数无效时，QueryBuilder 应返回清晰的错误消息
10. 当 LOD 表达式中的字段不存在于元数据时，QueryBuilder 应抛出 ValueError

### 需求 7.2: 纯语义中间层架构

**用户故事:** 作为开发者，我希望采用纯语义中间层架构，以便 LLM 只做语义理解，所有 VizQL 技术转换由确定性代码完成，实现 100% 准确的查询生成。

**优先级**: P0（核心功能）

**说明**：采用纯语义中间层架构，移除 Planning Agent。LLM 输出纯语义的 SemanticQuery，不包含任何 VizQL 技术概念（addressing、partitioning、RUNNING_SUM 等）。技术转换由确定性代码组件完成。

**参考文档**：
- `tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md`（Prompt 和数据模型编写指南）
- `design-appendix-semantic-layer.md`（纯语义中间层架构详细设计）

**架构说明**：
```
用户问题 → Understanding Agent → SemanticQuery（纯语义）
                                      ↓
                              FieldMapper（RAG + LLM）
                                      ↓
                              ImplementationResolver（代码规则 + LLM 语义意图）
                                      ↓
                              ExpressionGenerator（代码模板）
                                      ↓
                                  VizQLQuery
```

#### 验收标准

**SemanticQuery 数据模型（LLM 输出）：**
1. 当定义 SemanticQuery 模型时，应只包含纯语义字段：measures、dimensions、filters、analyses、output_control
2. 当定义 AnalysisSpec 模型时，应包含语义意图字段：type、target_measure、computation_scope、requires_external_dimension、target_granularity
3. 当用户问题包含多维度分析时，Understanding Agent 应判断 computation_scope（per_group 或 across_all）
4. 当用户问题需要访问视图外维度时，Understanding Agent 应设置 requires_external_dimension=true

**FieldMapper 组件（RAG + LLM）：**
5. 当执行字段映射时，FieldMapper 应使用 RAG 检索候选字段
6. 当 RAG 置信度 > 0.9 时，FieldMapper 应直接返回结果（快速路径）
7. 当 RAG 置信度 < 0.9 时，FieldMapper 应使用 LLM 判断最佳匹配

**ImplementationResolver 组件（代码规则）：**
8. 当 requires_external_dimension=true 时，ImplementationResolver 应选择 LOD 实现
9. 当 target_granularity 与视图维度不同时，ImplementationResolver 应选择 LOD 实现
10. 当使用表计算且为单维度场景时，ImplementationResolver 应使用代码规则推导 addressing
11. 当使用表计算且为多维度场景时，ImplementationResolver 应根据 computation_scope 推导 addressing

**ExpressionGenerator 组件（代码模板）：**
12. 当生成表计算表达式时，ExpressionGenerator 应使用预定义模板（RUNNING_SUM、RANK、WINDOW_AVG 等）
13. 当生成 LOD 表达式时，ExpressionGenerator 应使用预定义模板（{FIXED ...}、{INCLUDE ...}、{EXCLUDE ...}）
14. 当生成表达式时，ExpressionGenerator 应确保 100% 语法正确（括号匹配、函数名正确）

**表计算场景覆盖（分阶段）：**
15. Phase 1（P0）：系统应支持 cumulative、moving、ranking、percentage、period_compare 分析类型
16. Phase 2（P1）：系统应支持 difference、percent_difference、ranking_dense、ranking_percentile 分析类型
17. Phase 3（P2）：系统应支持 position（FIRST、LAST、INDEX、SIZE）分析类型

**Prompt 模板规范：**
18. 当定义 Understanding Prompt 时，应使用 4 段式结构（Role、Task、Domain Knowledge、Constraints）
19. 当定义 Understanding Prompt 时，应包含分析类型关键词映射表（累计→cumulative、排名→ranking 等）
20. 当定义 Understanding Prompt 时，应包含 computation_scope 判断规则（"各XX"→per_group、"总体"→across_all）


### 需求 8: 渐进式累积洞察分析系统

**用户故事:** 作为开发者，我希望 Insight Agent 能够使用渐进式累积分析处理大数据集，以便在不超出 LLM 上下文限制的情况下生成完整的数据洞察。

**优先级**: P1（重要功能）

**说明**：渐进式累积洞察分析是一个完整的系统，采用三层架构：Coordinator（主持人层，决策和编排）→ Processing（处理层，Map-Reduce）→ Synthesis（合成层，最终洞察）。核心组件包括：AnalysisCoordinator（分析协调器）、DataProfiler（数据画像器）、SemanticChunker（语义分块器）、ChunkAnalyzer（块分析器）、InsightAccumulator（洞察累积器）。

**架构**：
```
Coordinator (主持人层)
    ↓ 选择策略、编排流程
Processing (处理层)
    ├── DataProfiler (数据画像)
    ├── SemanticChunker (语义分块)
    ├── ChunkAnalyzer (块分析)
    └── InsightAccumulator (洞察累积)
    ↓ Map-Reduce
Synthesis (合成层)
    └── InsightSynthesizer (洞察合成)
```

**职责分离**：
- **渐进式洞察**：处理查询结果 DataFrame，洞察累积到 VizQLState.insights
- **SummarizationMiddleware**：处理对话历史 Messages，与洞察数据无关

#### 验收标准

1. 当 Insight Agent 开始分析时，AnalysisCoordinator 应首先使用 DataProfiler 生成数据画像（row_count、density、anomaly_ratio、semantic_groups）
2. 当选择分析策略时，AnalysisCoordinator 应根据数据量自动选择：direct（<100行）、progressive（100-1000行）、hybrid（>1000行）
3. 当执行渐进式分析时，SemanticChunker 应按业务逻辑分块（优先按时间、其次按类别、最后按地理）
4. 当分析数据块时，ChunkAnalyzer 应将之前的洞察摘要作为上下文传递给 LLM，避免重复发现
5. 当累积洞察时，InsightAccumulator 应检查重复、合并相似洞察、按优先级排序
6. 当分析完成时，InsightSynthesizer 应合成最终洞察并返回结构化 InsightResult（type、title、description、confidence、evidence、priority）
7. 当执行流式输出时，系统应实时输出分析进度和中间结果（chunk_start、chunk_complete、synthesizing、complete）

### 需求 9: ModelRetryMiddleware 集成

**用户故事:** 作为开发者，我希望有自动 LLM 重试能力，以便瞬态故障不会中断工作流。

**优先级**: P0（核心功能）

#### 验收标准

1. 当 LLM 调用因瞬态错误失败时，ModelRetryMiddleware 应自动重试最多 max_retries 次（可配置，默认 3）
2. 当重试时，ModelRetryMiddleware 应使用指数退避策略（1s、2s、4s）
3. 当所有重试耗尽时，ModelRetryMiddleware 应抛出包含原始错误和重试次数的异常
4. 当重试成功时，ModelRetryMiddleware 应记录重试次数并正常继续

### 需求 10: ToolRetryMiddleware 集成

**用户故事:** 作为开发者，我希望有自动工具重试能力，以便瞬态工具故障不会中断工作流。

**优先级**: P0（核心功能）

#### 验收标准

1. 当工具调用因瞬态错误失败时，ToolRetryMiddleware 应自动重试最多 max_retries 次（可配置，默认 3）
2. 当重试时，ToolRetryMiddleware 应使用指数退避策略
3. 当所有重试耗尽时，ToolRetryMiddleware 应返回错误 ToolMessage 而不是抛出异常
4. 当重试成功时，ToolRetryMiddleware 应记录重试次数并返回正常结果

### 需求 11: SummarizationMiddleware 集成

**用户故事:** 作为开发者，我希望有自动对话总结能力，以便长对话不会超过 token 限制。

**优先级**: P1（重要功能）

#### 验收标准

1. 当对话 token 数超过阈值（可配置，默认 100000）时，SummarizationMiddleware 应触发总结
2. 当触发总结时，SummarizationMiddleware 应保留最近 N 条消息（可配置，默认 10）
3. 当总结完成时，SummarizationMiddleware 应用总结消息替换旧消息
4. 当总结失败时，SummarizationMiddleware 应保留原始消息并记录警告
5. 当总结时，SummarizationMiddleware 应只总结对话消息，不总结 VizQLState.insights

### 需求 12: FilesystemMiddleware 实现

**用户故事:** 作为开发者，我希望有文件系统能力来处理大结果，以便 Agent 可以处理超出上下文限制的数据。

**优先级**: P0（核心功能）

#### 验收标准

1. 当工具输出超过 token 限制（可配置，默认 20000）时，FilesystemMiddleware 应自动保存到文件并返回文件引用
2. 当保存大结果时，FilesystemMiddleware 应使用 tool_call_id 生成唯一文件路径
3. 当文件保存后，FilesystemMiddleware 应返回文件路径和前 10 行作为预览
4. 当 Agent 需要文件内容时，FilesystemMiddleware 应提供带 offset 和 limit 参数的 read_file 工具
5. 当 Agent 需要写入文件时，FilesystemMiddleware 应提供 write_file 工具
6. 当 Agent 需要搜索文件时，FilesystemMiddleware 应提供 glob 和 grep 工具
7. 当会话结束时，FilesystemMiddleware 应清理与该会话关联的临时文件


### 需求 13: PatchToolCallsMiddleware 实现

**用户故事:** 作为开发者，我希望有自动修复悬空工具调用的能力，以便 LLM 调用不会因缺少 ToolMessages 而失败。

**优先级**: P0（核心功能）

#### 验收标准

1. 当 AIMessage 有 tool_calls 但没有对应的 ToolMessages 时，PatchToolCallsMiddleware 应添加取消 ToolMessages
2. 当修复时，PatchToolCallsMiddleware 应添加内容表明调用已取消的 ToolMessage
3. 当发生修复时，PatchToolCallsMiddleware 应记录被修复的 tool_call_ids 以便调试
4. 当不存在悬空工具调用时，PatchToolCallsMiddleware 应直接通过不做修改

### 需求 14: 工具注册与发现机制

**用户故事:** 作为开发者，我希望有一个统一的工具注册与发现机制，以便 Agent 节点可以动态获取其可用工具。

**优先级**: P0（核心功能）

**说明**：工具注册机制负责管理工具的生命周期和分配。具体工具定义参见需求 4-7。注意：R8（渐进式洞察系统）是独立系统，不是工具。

#### 验收标准

1. 当系统启动时，Tool_Registry 应自动发现并注册所有使用 @tool 装饰器定义的工具
2. 当注册工具时，Tool_Registry 应按 Agent 节点分组：boost_tools（get_metadata）、understanding_tools（parse_date、detect_date_format，均来自 DateManager）、query_builder_tools（semantic_map_fields，用于 FieldMapper 组件）、replanner_tools（write_todos，来自 TodoListMiddleware）
3. 当 Agent 节点创建时，Tool_Registry 应根据节点类型自动注入对应的工具集
4. 当工具依赖其他服务（如 MetadataManager、SemanticMapper、DateManager）时，Tool_Registry 应支持依赖注入
5. 当运行时需要添加或移除工具时，Tool_Registry 应支持动态更新而无需重启

**说明**：
- **中间件 vs 工具**：中间件自动生效（如 HumanInTheLoopMiddleware 自动暂停），工具需要 Agent 显式调用
- **Replanner Agent**：使用 write_todos 工具管理后续问题，HumanInTheLoopMiddleware 自动暂停让用户选择

### 需求 15: HumanInTheLoopMiddleware 集成

**用户故事:** 作为开发者，我希望在重规划阶段有人工介入能力，以便用户可以审查和选择后续问题。

**优先级**: P1（重要功能）

**说明**：主要用于重规划阶段，让用户选择后续分析问题。

**依赖关系**：与需求 16（TodoListMiddleware）协同工作，用户选中的问题会添加到 TodoList 执行队列。

#### 验收标准

1. 当 Replanner Agent 生成后续问题（2-5 个问题）时，HumanInTheLoopMiddleware 应暂停执行并向用户展示问题
2. 当用户审查问题时，HumanInTheLoopMiddleware 应允许用户选择部分问题、修改问题、执行全部或拒绝继续
3. 当用户选择问题时，HumanInTheLoopMiddleware 应调用 TodoListMiddleware 的 write_todos 工具将选中问题添加到执行队列（依赖 R16）
4. 当用户超时（可配置，默认 300 秒）时，HumanInTheLoopMiddleware 应根据配置执行默认操作（跳过或执行全部）
5. 当配置时，HumanInTheLoopMiddleware 应支持 interrupt_on 参数指定哪些工具调用需要人工确认

### 需求 16: TodoListMiddleware 集成

**用户故事:** 作为开发者，我希望有任务管理能力，以便可以跟踪和执行复杂的多步骤分析。

**优先级**: P1（重要功能）

#### 验收标准

1. 当启用 TodoListMiddleware 时，TodoListMiddleware 应提供 write_todos 工具用于任务管理
2. 当创建任务时，TodoListMiddleware 应存储包含 id、description 和 status（pending、in_progress、completed）的任务状态
3. 当 Agent 处理复杂任务时，TodoListMiddleware 应自动使用 write_todos 跟踪子任务
4. 当存储任务时，TodoListMiddleware 应将任务状态持久化到 VizQLState.todos


### 需求 17: Replanner 重规划路由

**用户故事:** 作为开发者，我希望有正确的重规划路由，以便后续问题能被高效处理。

**优先级**: P0（核心功能）

#### 验收标准

1. 当 Replanner 决定重规划（should_replan=True 且 replan_count < max）时，StateGraph 应路由回 Understanding 节点（重新进行语义理解）
2. 当 completeness_score >= 0.9 时，Replanner_Agent 应设置 should_replan 为 False 并路由到 END
3. 当 replan_count 达到 max_replan_rounds 时，StateGraph 应路由到 END，无论 completeness_score 如何
4. 当路由到 Planning 时，StateGraph 应使用 ReplanDecision 中的 new_question 作为 current_question

### 需求 18: 状态管理

**用户故事:** 作为开发者，我希望有正确的状态管理，以便工作流状态在节点和会话之间得到保留。

**优先级**: P0（核心功能）

#### 验收标准

1. 当工作流执行时，State_Manager 应维护包含所有必需字段的 VizQLState（question、understanding、query_plan、insights 等）
2. 当节点完成时，State_Manager 应将节点输出合并到 VizQLState 而不丢失现有数据
3. 当发生错误时，State_Manager 应将错误追加到 VizQLState.errors 列表
4. 当会话被检查点时，State_Manager 应将 VizQLState 持久化到 SQLite store
5. 当会话恢复时，State_Manager 应从检查点恢复 VizQLState

### 需求 19: 可观测性

**用户故事:** 作为开发者，我希望有全面的可观测性，以便我可以调试和优化 Agent 性能。

**优先级**: P2（辅助功能）

#### 验收标准

1. 当 Agent 执行时，Observability_System 应记录节点名称、输入摘要、输出摘要和延迟
2. 当调用工具时，Observability_System 应记录工具名称、参数、结果摘要和延迟
3. 当中间件执行时，Observability_System 应记录中间件名称、采取的操作和任何错误
4. 当执行 RAG 检索时，Observability_System 应记录查询、候选数量、top-3 分数和延迟
5. 当发生错误时，Observability_System 应记录错误类型、消息、堆栈跟踪和上下文

### 需求 20: 配置管理

**用户故事:** 作为开发者，我希望有集中的配置管理，以便我可以在不修改代码的情况下轻松调整 Agent 行为。

**优先级**: P1（重要功能）

#### 验收标准

1. 当创建 Agent 时，Config_Manager 应从环境变量和配置文件加载配置
2. 当加载配置时，Config_Manager 应支持中间件参数（重试次数、token 阈值等）
3. 当加载配置时，Config_Manager 应支持每种 Agent 类型的模型参数（temperature、top_p 等）
4. 当配置缺失时，Config_Manager 应使用合理的默认值
5. 当配置更改时，Config_Manager 应支持运行时重新加载而无需重启

### 需求 21: 错误处理与分类

**用户故事:** 作为开发者，我希望有统一的错误处理机制，以便系统能正确分类和处理不同类型的错误。

**优先级**: P1（重要功能）

#### 验收标准

1. 当发生错误时，Error_Handler 应将错误分类为：瞬态错误（TransientError，可重试）、永久性错误（PermanentError，不可重试）、用户错误（UserError，需用户修正）
2. 当发生瞬态错误（网络超时、API 限流、服务暂时不可用）时，Error_Handler 应触发重试机制（参见 R9、R10）
3. 当发生永久性错误（无效配置、权限不足、资源不存在）时，Error_Handler 应立即终止并返回清晰的错误消息
4. 当发生用户错误（无效输入、字段不存在）时，Error_Handler 应返回用户友好的错误消息，包含修正建议
5. 当错误发生时，Error_Handler 应将错误详情（类型、消息、上下文、堆栈跟踪）记录到 VizQLState.errors 并发送到日志系统

### 需求 22: 安全性基础

**用户故事:** 作为开发者，我希望有基本的安全保障，以便用户数据和 API 密钥得到保护。

**优先级**: P1（重要功能）

#### 验收标准

1. 当存储 API 密钥时，Security_Manager 应使用环境变量或加密配置文件，禁止硬编码
2. 当记录日志时，Security_Manager 应自动脱敏敏感信息（API 密钥、用户凭证、个人数据）
3. 当多用户使用系统时，Security_Manager 应确保用户会话数据隔离（通过 session_id 和 user_id）
4. 当调用外部 API 时，Security_Manager 应使用 HTTPS 并验证证书
5. 当缓存数据时，Security_Manager 应按用户/会话隔离缓存命名空间

## 非功能性需求

### NFR-1: 性能要求

| 指标 | 目标值 | 测量方法 |
|-----|-------|---------|
| 工作流执行延迟（不含 LLM） | < 30s | 端到端计时 |
| 字段映射延迟（缓存命中） | < 500ms | 工具调用计时 |
| 字段映射延迟（需要 LLM） | < 2000ms | 工具调用计时 |
| 单会话内存占用 | < 1GB | 内存监控 |
| 向量检索延迟 | < 100ms | RAG 检索计时 |

### NFR-2: 可靠性要求

| 指标 | 目标值 | 测量方法 |
|-----|-------|---------|
| LLM 调用成功率（含重试） | > 99% | 成功/总调用 |
| 工具调用成功率（含重试） | > 99.5% | 成功/总调用 |
| 工作流完成率 | > 95% | 完成/总执行 |
| 平均故障恢复时间 | < 5s | 重试耗时 |

**故障处理策略**：
- 瞬态错误：自动重试最多 3 次，指数退避（1s、2s、4s）
- 永久性错误：立即终止，返回错误消息
- 中间件故障：跳过故障中间件，继续执行（优雅降级）

### NFR-3: 兼容性要求

- 兼容现有 RAG 模块 API（SemanticMapper、FieldIndexer、Reranker）
- 兼容现有 Agent 节点逻辑（Understanding、Planning、Insight、Replanner）
- 兼容现有前端 API 接口（/chat、/stream 端点）
- 支持多种 LLM 提供商：Claude、DeepSeek、Qwen、OpenAI（通过 model_manager 切换）

### NFR-4: 可维护性要求

| 指标 | 目标值 | 测量方法 |
|-----|-------|---------|
| 单元测试覆盖率 | > 80% | pytest-cov |
| 集成测试覆盖率 | > 60% | pytest-cov |
| 公共 API 文档覆盖率 | 100% | docstring 检查 |
| 中间件独立测试 | 每个中间件有独立测试文件 | 文件检查 |
| 工具独立测试 | 每个工具有独立测试用例 | 测试用例检查 |

## 实施优先级

| 阶段 | 需求 | 说明 |
|-----|------|------|
| Phase 1 | R1, R2, R3, R18, R21 | 核心架构（中间件栈、工作流编排、工具系统、状态管理、错误处理） |
| Phase 2 | R4, R4.1, R5, R6, R7, R14 | 核心工具（RAG 语义映射、维度层级 RAG 增强、元数据、日期、查询执行、工具注册） |
| Phase 3 | R9, R10, R12, R13 | 中间件实现（ModelRetry、ToolRetry、Filesystem、PatchToolCalls） |
| Phase 4 | R17, R22 | 重规划路由和安全性基础 |
| Phase 5 | R8, R11, R15, R16, R19, R20 | 增强功能（渐进式洞察系统、Summarization、HumanInTheLoop、TodoList、可观测性、配置） |

## 需求依赖关系

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              核心架构层                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  R1 (中间件架构) ─┬─> R9 (ModelRetry)                                        │
│                  ├─> R10 (ToolRetry)                                        │
│                  ├─> R11 (Summarization)                                    │
│                  ├─> R12 (Filesystem)                                       │
│                  ├─> R13 (PatchToolCalls)                                   │
│                  ├─> R15 (HumanInTheLoop) ──> R16 (TodoList)                │
│                  └─> R16 (TodoList)                                         │
│                                                                              │
│  R2 (工作流编排) ──> R17 (重规划路由)                                         │
│                                                                              │
│  R3 (工具系统) ──> R14 (工具注册)                                             │
│                                                                              │
│  R18 (状态管理) <── R2, R17                                                  │
│                                                                              │
│  R21 (错误处理) ──> R9, R10 (触发重试)                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              工具层                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  R14 (工具注册) ─┬─> R4 (RAG 语义映射工具)                                    │
│                 │    └─> R4.1 (维度层级 RAG 增强)                            │
│                 ├─> R5 (元数据工具) ← 封装 MetadataManager                   │
│                 ├─> R6 (日期工具) ← 封装 DateManager                         │
│                 └─> R7 (查询执行工具)                                        │
│                                                                              │
│  R4 (RAG 工具) <── R5 (元数据工具提供字段索引数据)                            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              增强功能层                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  R8 (渐进式洞察系统) ← 独立系统，依赖 R7 (查询结果)                           │
│                                                                              │
│  R11 (Summarization) ← 处理对话历史，与 R8 职责分离                          │
│                                                                              │
│  R15 (HumanInTheLoop) ──> R16 (TodoList) ← 用户选择问题后添加到队列          │
│                                                                              │
│  R19 (可观测性) ← 横切关注点，监控所有组件                                    │
│                                                                              │
│  R20 (配置管理) <── R22 (安全性，API 密钥管理)                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

关键依赖说明：
- R4 → R4.1: 维度层级 RAG 增强依赖 RAG 基础设施
- R4 ← R5: RAG 工具需要元数据工具提供字段信息用于索引
- R8 ← R7: 渐进式洞察系统处理查询执行工具返回的结果
- R8 ≠ R11: 渐进式洞察（处理 DataFrame）与 Summarization（处理 Messages）职责分离
- R15 → R16: HumanInTheLoop 选择的问题通过 TodoList 管理
```
