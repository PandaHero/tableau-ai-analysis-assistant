# Retrieval And Memory Plane

> Status: Draft v1.0
> Read order: 4/14
> Upstream: [requirements.md](./requirements.md), [design.md](./design.md)
> Downstream: [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [node-catalog.md](./node-catalog.md), [tasks.md](./tasks.md)

## 1. 目标

建立统一的检索与记忆平面，避免“每个节点各写一套缓存逻辑”。

该平面服务于 `context_graph`、`semantic_graph` 与 `answer_graph` 的部分节点。

## 2. 平面组成

### 2.1 RetrievalRouter

职责：

- 在 exact / BM25 / embedding / hybrid / rerank 之间路由。
- 输出统一候选结构与检索 trace。

输出契约：

- `candidate_fields_ref`
- `candidate_values_ref`
- `fewshot_examples_ref`
- `retrieval_trace_ref`

### 2.2 MemoryStore

职责：

- 管理 query cache / few-shot / value memory / synonym memory。
- 管理作用域与失效策略。

### 2.3 FeedbackLearningService

职责：

- 基于明确反馈或成功查询进行受控写入。
- 提供审计记录（写入人、写入时间、run_id、request_id）。

## 3. 检索策略

必须保留以下策略，不可退化为单一路径：

- exact（强约束词命中）
- BM25（关键词召回）
- embedding（语义召回）
- hybrid（融合）
- rerank（重排）

推荐默认：

- 先召回（exact + BM25 + embedding）
- 后融合（RRF/加权）
- 最后 rerank（可配置）

## 4. 记忆对象

### 4.1 Query Cache

用途：

- 缓存“语义解析 + 查询计划 + 结果摘要引用”的可复用组合。

建议 key 维度：

- `site`
- `principal_or_scope_owner`
- `datasource_luid`
- `schema_hash`
- `parser_version`
- `normalized_question_hash`

### 4.2 Few-shot Memory

用途：

- 存储“高质量历史问答样本”的引用，供 semantic parse 提示。

### 4.3 Filter Value Memory

用途：

- 记录历史值确认（value_confirm）结果，减少重复澄清。

### 4.4 Synonym Memory

用途：

- 记录业务同义词映射（字段与值两类）。

## 5. 失效与生命周期

### 5.1 必须硬失效

- `schema_hash` 变化后，依赖旧 schema 的强绑定缓存必须失效。
- 租户作用域变化（site/principal）后禁止复用旧数据。

### 5.2 可软失效

- few-shot 索引过期可异步刷新。
- value/synonym memory 可按权重衰减而非立即删除。

### 5.3 写入策略

- 仅在“成功执行”或“用户显式确认反馈”后写入。
- 写入必须可追踪到 `run_id` 与 `request_id`。

## 6. 运行边界

- 检索与记忆只用于候选与提示增强。
- 不允许直接绕过 `semantic_guard`。
- 不允许直接修改 `query_plan` 的确定性约束。

## 7. 可观测与评估

至少记录：

- `retrieval_strategy`
- `candidate_count_before_rerank`
- `candidate_count_after_rerank`
- `cache_hit/cache_miss`
- `clarification_rate`
- `memory_write_count`
- `memory_write_reason`

离线评估建议：

- 黄金问题集（golden set）覆盖多数据源、多语言、多复杂度。
- shadow compare 新旧策略差异。
- 关注：召回质量、澄清率、执行成功率、答案可溯源性。
