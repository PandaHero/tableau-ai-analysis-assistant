# Semantic Parser 架构文档

> 自动生成于 2025-03 · 基于源码审查

---

## 1. 概述

Semantic Parser 是 Tableau AI Analysis Assistant 的核心语义解析模块，负责将用户自然语言问题转换为结构化数据查询。采用 **LangGraph StateGraph** 构建，包含 16 个节点，支持缓存加速、规则预处理、LLM 驱动理解、错误自修正等能力。

### 核心设计原则

- **信任 LLM 推理能力**，通过 Prompt 和 Few-shot 提升准确性
- **规则与模型协同**：规则层做快速预处理，LLM 层做深度理解
- **渐进式状态更新**：每个节点只更新自己负责的状态字段
- **多级缓存**：QueryCache（精确+语义）、FeatureCache（特征级语义缓存）
- **优雅降级**：关键 LLM 调用超时时提供降级方案

---

## 2. 目录结构

```
semantic_parser/
├── __init__.py              # 包导出（SemanticOutput, FieldCandidate 等）
├── graph.py                 # LangGraph 子图定义与编译
├── state.py                 # SemanticParserState（TypedDict）
├── routes.py                # 条件边路由函数
├── node_utils.py            # 节点工具函数（组件实例化、通用辅助）
│
├── schemas/                 # 数据模型定义（按功能分类）
│   ├── __init__.py           # 统一导出所有 schema
│   ├── output.py             # 核心输出：SemanticOutput, What, Where, DerivedComputation, SelfCheck, CalcType
│   ├── intermediate.py       # 中间模型：TimeHint, FieldCandidate（从 core 导入）, FewShotExample
│   ├── intent.py             # 意图模型：IntentType, IntentRouterOutput
│   ├── filters.py            # 筛选模型：FilterValidationType, FilterValidationResult, FilterConfirmation
│   ├── cache.py              # 缓存模型：CachedQuery, CachedFeature, CachedFieldValues
│   ├── planner.py            # 计划模型：AnalysisPlan, StepIntent, EvidenceContext, GlobalUnderstandingOutput
│   ├── prefilter.py          # 预处理模型：PrefilterResult, FeatureExtractionOutput, FieldRAGResult, ValidationResult
│   ├── dynamic_schema.py     # 动态 schema：DynamicSchemaResult
│   ├── error_correction.py   # 错误修正：ErrorCorrectionHistory, CorrectionResult
│   ├── feedback.py           # 反馈模型：FeedbackType, FeedbackRecord, SynonymMapping
│   └── config.py             # 运行时上下文：SemanticConfig（注意：非配置文件，是运行时上下文）
│
├── nodes/                   # LangGraph 节点函数
│   ├── __init__.py           # 统一导出
│   ├── intent.py             # intent_router_node
│   ├── cache.py              # query_cache_node, feature_cache_node
│   ├── optimization.py       # rule_prefilter_node, feature_extractor_node,
│   │                         #   dynamic_schema_builder_node, modular_prompt_builder_node
│   ├── global_understanding.py  # global_understanding_node
│   ├── planner.py            # analysis_planner_node（兼容层，非主链必经节点）
│   ├── retrieval.py          # field_retriever_node, few_shot_manager_node
│   ├── understanding.py      # semantic_understanding_node
│   ├── validation.py         # output_validator_node, filter_validator_node
│   └── execution.py          # query_adapter_node, error_corrector_node, feedback_learner_node
│
├── components/              # 业务组件（被节点函数调用）
│   ├── __init__.py            # 统一导出
│   ├── intent_router.py       # IntentRouter - 三级意图分类
│   ├── query_cache.py         # QueryCache - 查询级缓存
│   ├── semantic_cache.py      # SemanticCache - 语义缓存抽象基类
│   ├── feature_cache.py       # FeatureCache - 特征提取缓存
│   ├── rule_prefilter.py      # RulePrefilter - 规则预处理
│   ├── feature_extractor.py   # FeatureExtractor - LLM 特征提取
│   ├── field_retriever.py     # FieldRetriever - 字段检索
│   ├── field_value_cache.py   # FieldValueCache - 字段值缓存
│   ├── filter_validator.py    # FilterValueValidator - 筛选值验证
│   ├── output_validator.py    # OutputValidator - 输出验证与自动修正
│   ├── candidate_resolver.py  # CandidateResolver - 候选消歧
│   ├── history_manager.py     # HistoryManager - 对话历史管理
│   ├── dynamic_schema_builder.py    # DynamicSchemaBuilder - 动态 schema 构建
│   ├── semantic_lexicon_builder.py  # SemanticLexiconBuilder - 语义词典构建
│   ├── semantic_understanding.py    # SemanticUnderstanding - 核心语义理解组件
│   ├── error_corrector.py     # ErrorCorrector - 错误修正组件
│   ├── feedback_learner.py    # FeedbackLearner - 反馈学习组件
│   └── few_shot_manager.py    # FewShotManager - Few-shot 示例管理
│
├── prompts/                 # Prompt 模板
│   ├── __init__.py
│   ├── prompt_builder.py         # DynamicPromptBuilder - 动态 Prompt 组装
│   ├── time_hint_generator.py    # TimeHintGenerator - 时间表达式解析
│   ├── global_understanding_prompt.py  # 全局理解 Prompt
│   ├── feature_extractor_prompt.py     # 特征提取 Prompt
│   └── error_correction_prompt.py      # 错误修正 Prompt
│
└── seeds/                   # 种子数据与规则匹配器
    ├── __init__.py           # 重新导出 infra/seeds 的种子数据
    └── matchers/
        ├── __init__.py
        ├── computation_matcher.py   # ComputationMatcher - 计算种子匹配
        ├── complexity_detector.py   # ComplexityDetector - 复杂度检测
        └── intent_matcher.py        # IntentMatcher - 意图关键词匹配
```

---

## 3. 主链流程

### 3.1 流程总览

```
用户问题
   │
   ▼
┌─────────────────┐
│  IntentRouter    │──── general / irrelevant / clarification ──→ END
│  (三级意图分类)   │
└────────┬────────┘
         │ data_query
         ▼
┌─────────────────┐
│  QueryCache      │──── cache_hit ──→ FeedbackLearner ──→ END
│  (精确+语义缓存)  │
└────────┬────────┘
         │ cache_miss
         ▼
┌─────────────────┐
│  RulePrefilter   │  纯规则：时间提示、计算匹配、复杂度检测、语言检测
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FeatureCache    │──── cache_hit ──→ 跳过 FeatureExtractor
│  (特征级语义缓存) │
└────────┬────────┘
         │ cache_miss
         ▼
┌─────────────────┐
│ FeatureExtractor │  LLM 验证规则结果 + 提取业务术语级度量/维度需求
└────────┬────────┘
         │
         ▼
┌──────────────────────┐
│ GlobalUnderstanding   │  LLM 判断：单步可答 / 需分解 / 归因分析
│ (全局问题理解)         │  输出 analysis_plan
└────────┬─────────────┘
         │
         ▼
┌─────────────────┐
│  FieldRetriever  │  语义词典 + 业务术语 → 从 schema 检索字段候选
└────────┬────────┘
         │
         ▼
┌──────────────────────┐
│ DynamicSchemaBuilder  │  按复杂度裁剪 schema，减少 token
└────────┬─────────────┘
         │
         ▼
┌──────────────────────┐
│ ModularPromptBuilder  │  组装最终 Prompt（规则 + 字段 + Few-shot + 上下文）
└────────┬─────────────┘
         │
         ▼
┌─────────────────┐
│  FewShotManager  │  检索相似历史成功案例
└────────┬────────┘
         │
         ▼
┌──────────────────────────┐
│  SemanticUnderstanding    │  核心 LLM 调用 → SemanticOutput
│  (语义理解)               │  needs_clarification → END
└────────┬─────────────────┘
         │
         ▼
┌─────────────────┐
│ OutputValidator  │  验证字段存在性，自动修正 → needs_clarification → END
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ FilterValidator  │  筛选值合法性验证，模糊匹配，interrupt() 用户确认
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  QueryAdapter    │  SemanticOutput → VizQL/SQL
└────────┬────────┘
         │ error ──→ ErrorCorrector ──→ retry → OutputValidator
         │                            abort → END
         ▼
┌──────────────────┐
│ FeedbackLearner  │  学习成功案例，更新缓存
└────────┬─────────┘
         │
         ▼
        END
```

### 3.2 状态定义

所有节点通过 `SemanticParserState`（TypedDict, total=False）共享状态，支持渐进式更新。

**核心输入字段：**
| 字段 | 类型 | 说明 |
|------|------|------|
| `question` | `str` | 用户问题 |
| `datasource_luid` | `str` | 数据源标识 |
| `chat_history` | `list[dict]` | 对话历史 |
| `current_time` | `str` | 当前时间（ISO 格式） |

**核心输出字段：**
| 字段 | 类型 | 说明 |
|------|------|------|
| `semantic_output` | `dict` | 结构化语义输出（what/where/how/computations） |
| `semantic_query` | `dict` | 可执行查询（VizQL/SQL） |
| `parse_result` | `dict` | 最终解析结果汇总 |

**中间状态字段：**
| 字段 | 来源节点 | 说明 |
|------|----------|------|
| `intent_router_output` | IntentRouter | 意图分类结果 |
| `prefilter_result` | RulePrefilter | 规则预处理结果 |
| `feature_extraction_output` | FeatureExtractor | 特征提取结果 |
| `global_understanding` | GlobalUnderstanding | 全局理解输出 |
| `analysis_plan` | GlobalUnderstanding | 分析计划 |
| `current_step_intent` | 外部注入 | 当前执行步骤意图 |
| `evidence_context` | 外部累积 | 多步分析证据上下文 |
| `field_candidates` | FieldRetriever | 字段候选列表 |
| `field_rag_result` | FieldRetriever | RAG 检索结果 |
| `dynamic_schema_result` | DynamicSchemaBuilder | 动态 schema |
| `modular_prompt` | ModularPromptBuilder | 组装后的 Prompt |
| `few_shot_examples` | FewShotManager | Few-shot 示例 |
| `validation_result` | OutputValidator | 输出验证结果 |
| `filter_validation_result` | FilterValidator | 筛选值验证结果 |

---

## 4. 节点详解

### 4.1 IntentRouter（意图路由）

**三级判断架构：**

| 级别 | 方式 | 说明 |
|------|------|------|
| L0_RULE | 正则匹配 | `IRRELEVANT_PATTERNS` 快速过滤无关问题 |
| L1_MODEL | LLM 分类 | 四分类：data_query / clarification / general / irrelevant |
| L2_FALLBACK | 降级兜底 | LLM 超时时默认为 data_query |

**路由逻辑（`route_by_intent`）：**
- `data_query` → QueryCache
- `general` / `irrelevant` / `clarification` → END

### 4.2 QueryCache（查询缓存）

继承 `SemanticCache`，支持：
- **精确匹配**：question + datasource_luid 哈希
- **语义匹配**：embedding 向量 + FAISS 索引（阈值 0.95）
- **LRU 淘汰**：默认最大 1000 条

**路由逻辑（`route_by_cache`）：**
- `cache_hit` → FeedbackLearner（直接跳过整个解析链）
- `cache_miss` → RulePrefilter

### 4.3 RulePrefilter（规则预处理）

**纯规则处理，无 LLM 调用**，提取以下信息：

| 子组件 | 输出 | 说明 |
|--------|------|------|
| `TimeHintGenerator` | `time_hints` | 时间表达式 → 具体日期范围 |
| `ComputationMatcher` | `matched_computations` | 匹配计算种子（比率、同比等） |
| `ComplexityDetector` | `detected_complexity` | 复杂度标签（ratio/time_compare/ranking 等） |
| `IntentMatcher` | 意图标签 | 对比、趋势、排名等意图 |
| 语言检测 | `detected_language` | zh / en / ja |

输出 `PrefilterResult`，包含 `match_confidence` 和 `low_confidence` 标志。

### 4.4 FeatureCache（特征缓存）

- 继承 `SemanticCache`，缓存 `FeatureExtractionOutput`
- 版本标识：`semantic-v4-step-intent`
- TTL：3600 秒（1 小时）
- 语义相似度阈值：0.95
- 支持 `current_step_intent` 上下文感知

### 4.5 FeatureExtractor（特征提取）

**LLM 驱动**，基于 `feature_extractor_prompt.py` 定义的 Prompt：
- 验证 RulePrefilter 提取的时间提示和计算类型
- 提取业务术语级别的 `required_measures` 和 `required_dimensions`
- 输出 `confirmation_confidence`
- **降级机制**：超时返回 `is_degraded=True`，后续节点适配

### 4.6 GlobalUnderstanding（全局问题理解）

**LLM 驱动**，判断问题全局性质：

| 模式 | 说明 |
|------|------|
| `single_query` | 单步可答 |
| `complex_single_query` | 复杂但单步可答 |
| `multi_step_analysis` | 需分解为多步查询 |
| `why_analysis` | 归因分析（为什么） |

**关键输出：**
- `analysis_plan`：包含 `sub_questions`、`execution_strategy`、`reasoning_focus`
- `primary_restated_question`：重述后的主问题
- `risk_flags`：风险标记

### 4.7 FieldRetriever（字段检索）

核心依赖 `SemanticLexiconBuilder`：
1. 从种子数据（`MEASURE_SEEDS` / `DIMENSION_SEEDS`）构建基础词汇表
2. 结合 `FeatureExtractionOutput` 的业务术语需求
3. 从数据源 schema 中检索最相关的 `FieldCandidate`

**SemanticLexicon 提供：**
- `measure_category_hints`：度量类别提示
- `measure_identifier_hints`：度量标识符提示（展开变体）
- `measure_placeholder_hints`：度量占位符提示（含 fallback）
- `dimension_category_hints`：维度类别提示
- `dimension_level_hints`：维度层级提示

### 4.8 DynamicSchemaBuilder（动态 Schema 构建）

根据检测到的复杂度和计算类型，动态选择 schema 模块：
- `base`：基础字段信息
- `time`：时间相关字段（当检测到时间表达式）
- `computation`：计算相关信息（当检测到计算需求）

目标：裁剪不必要的字段信息以减少 token 消耗。

### 4.9 ModularPromptBuilder（模块化 Prompt 构建）

基于 `DynamicPromptBuilder`，按模块组装最终 Prompt：

| 模块 | 说明 |
|------|------|
| 系统规则 | 基础解析指令 |
| 时间提示 | XML 格式的时间范围（由 `TimeHintGenerator` 生成） |
| 分析计划 | 当 `analysis_plan` 存在时插入 |
| 当前步骤意图 | 当 `current_step_intent` 存在时插入 |
| 证据上下文 | 多步分析的累积证据 |
| 可用字段列表 | 度量 / 维度分类展示 |
| Few-shot 示例 | 相似历史案例 |
| 计算种子参考 | 低置信度时插入 `COMPUTATION_SEEDS` |
| 对话历史 | 多轮对话上下文 |
| 任务模板 | SIMPLE / COMPLEX 两套模板 |

### 4.10 SemanticUnderstanding（语义理解）

核心 LLM 调用，输出 `SemanticOutput`：

```json
{
  "query_id": "uuid",
  "restated_question": "重述后的问题",
  "what": { "measures": [...] },
  "where": { "dimensions": [...], "filters": [...] },
  "how_type": "SIMPLE | COMPLEX",
  "computations": [...],
  "needs_clarification": false,
  "self_check": { ... }
}
```

### 4.11 OutputValidator + FilterValidator（验证链）

**OutputValidator：**
- 验证 LLM 输出的字段是否存在于候选列表
- 自动修正可修正的错误（如大小写、别名映射）
- 不可修正时触发 `needs_clarification`

**FilterValidator：**
- 验证筛选值是否合法
- 模糊匹配找到相似值
- 需确认时调用 `interrupt()` 暂停执行，等待用户确认
- 支持 `confirmed_filters` 多轮累积

### 4.12 ErrorCorrector（错误修正）

基于 `error_correction_prompt.py`，针对不同错误类型提供专用修正指导：

| 错误类型 | 说明 |
|----------|------|
| `field_not_found` | 字段不存在 |
| `syntax_error` | 语法错误 |
| `invalid_filter_value` | 无效筛选值 |
| `type_mismatch` | 类型不匹配 |
| `computation_error` | 计算表达式错误 |

**防无限循环机制：**
- 最大重试次数：3
- 检测重复错误（相同错误出现 2 次 → abort）
- 检测交替错误模式（A→B→A→B → abort）

---

## 5. 组件依赖关系

```
infra/seeds/
├── MEASURE_SEEDS ──────┐
├── DIMENSION_SEEDS ────┤
├── COMPUTATION_SEEDS ──┤
├── COMPLEXITY_KEYWORDS ┤
├── INTENT_KEYWORDS ────┤
└── IRRELEVANT_PATTERNS ┘
         │
         ▼
seeds/matchers/
├── ComputationMatcher ──→ RulePrefilter
├── ComplexityDetector ──→ RulePrefilter
└── IntentMatcher ───────→ RulePrefilter
         │
         ▼
components/
├── SemanticLexiconBuilder ──→ FieldRetriever
├── SemanticCache (abstract)
│   ├── QueryCache
│   └── FeatureCache
├── IntentRouter
├── FeatureExtractor
├── FilterValueValidator
├── CandidateResolver
└── HistoryManager

prompts/
├── TimeHintGenerator ───→ RulePrefilter + DynamicPromptBuilder
├── DynamicPromptBuilder ─→ ModularPromptBuilder 节点
├── global_understanding_prompt ──→ GlobalUnderstanding 节点
├── feature_extractor_prompt ─────→ FeatureExtractor 节点
└── error_correction_prompt ──────→ ErrorCorrector 节点
```

---

## 6. 缓存架构

### 6.1 SemanticCache（抽象基类）

提供通用缓存能力：
- **LRU 淘汰**：基于访问时间
- **精确匹配**：哈希键查找
- **语义匹配**：embedding 向量 + FAISS 索引（可降级为线性扫描）
- **Embedding 缓存**：避免重复计算
- **TTL 过期**：自动清理

子类需实现：
- `_make_namespace()` — 缓存命名空间
- `_validate_cached()` — 验证缓存条目
- `_parse_cached()` — 解析缓存条目
- `_get_cached_embedding()` — 获取条目的 embedding
- `_get_cached_expires_at()` — 获取条目的过期时间

### 6.2 两级缓存

| 缓存 | 粒度 | 命中后跳过 | 阈值 | TTL |
|------|------|-----------|------|-----|
| QueryCache | 查询级 | 整个解析链 → FeedbackLearner | 0.95 | 1h |
| FeatureCache | 特征级 | FeatureExtractor | 0.95 | 1h |

---

## 7. 路由函数一览

定义在 `routes.py`：

| 函数 | 源节点 | 路由结果 |
|------|--------|----------|
| `route_by_intent` | IntentRouter | data_query / general / irrelevant / clarification |
| `route_by_cache` | QueryCache | cache_hit / cache_miss |
| `route_by_feature_cache` | FeatureCache | cache_hit / cache_miss |
| `route_after_understanding` | SemanticUnderstanding | continue / needs_clarification |
| `route_after_output_validation` | OutputValidator | valid / needs_clarification |
| `route_after_filter_validation` | FilterValidator | valid / needs_clarification |
| `route_after_query` | QueryAdapter | success / error |
| `route_after_correction` | ErrorCorrector | retry / abort |

---

## 8. 关键数据模型

### SemanticOutput（语义理解输出）

```
SemanticOutput
├── query_id: str
├── restated_question: str
├── what: What
│   └── measures: list[str]
├── where: Where
│   ├── dimensions: list[str]
│   └── filters: list[dict]
├── how_type: "SIMPLE" | "COMPLEX"
├── computations: list[DerivedComputation]
├── needs_clarification: bool
├── clarification_question: Optional[str]
├── clarification_options: Optional[list[str]]
└── self_check: SelfCheck
```

### FieldCandidate（字段候选）

```
FieldCandidate
├── field_name: str
├── field_caption: str
├── role: "measure" | "dimension"
├── data_type: str
├── description: Optional[str]
├── sample_values: Optional[list[str]]
├── aliases: Optional[list[str]]
├── confidence: float
├── measure_category: Optional[str]      # 度量专用
├── hierarchy_category: Optional[str]     # 维度专用
├── hierarchy_level: Optional[int]        # 维度专用
└── business_description: Optional[str]
```

### PrefilterResult（规则预处理结果）

```
PrefilterResult
├── time_hints: list[TimeHint]
├── matched_computations: list[ComputationSeed]
├── detected_complexity: list[str]
├── detected_language: "zh" | "en" | "ja"
├── match_confidence: float
└── low_confidence: bool
```

---

## 9. 性能优化要点

1. **双层缓存**：QueryCache（查询级）+ FeatureCache（特征级），减少 LLM 调用
2. **规则预处理**：RulePrefilter 零 LLM 调用，毫秒级完成时间/计算/复杂度检测
3. **动态 Schema 裁剪**：DynamicSchemaBuilder 按需裁剪字段信息，减少 Prompt token
4. **进程级单例**：`compile_semantic_parser_graph()` 缓存编译结果，避免重复编译
5. **FAISS 索引**：语义缓存使用 FAISS 加速向量检索（不可用时降级为线性扫描）
6. **降级策略**：FeatureExtractor 超时时返回 `is_degraded=True`，后续节点适配

---

## 10. 扩展指南

### 添加新节点

1. 在 `nodes/` 下创建节点函数，签名为 `def xxx_node(state: SemanticParserState) -> dict`
2. 在 `nodes/__init__.py` 导出
3. 在 `graph.py` 的 `create_semantic_parser_graph()` 中添加节点和边
4. 如需条件路由，在 `routes.py` 添加路由函数

### 添加新组件

1. 在 `components/` 下创建组件类
2. 在 `components/__init__.py` 导出
3. 在对应节点函数中实例化并调用

### 添加新种子数据

1. 在 `infra/seeds/` 中添加种子定义
2. 在 `seeds/__init__.py` 重新导出（保持兼容）
3. 如需匹配器，在 `seeds/matchers/` 中添加
