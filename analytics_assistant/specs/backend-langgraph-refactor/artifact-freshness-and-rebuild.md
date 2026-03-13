# Artifact Freshness And Rebuild Strategy

> Status: Draft v1.1
> Read order: 7/14
> Upstream: [requirements.md](./requirements.md), [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [data-and-api.md](./data-and-api.md)
> Downstream: [insight-large-result-design.md](./insight-large-result-design.md), [migration.md](./migration.md), [tasks.md](./tasks.md)

## 1. 目标

定义 metadata 与 retrieval artifact 在在线请求中的可用性策略，避免请求链路被全量重建阻塞。

## 2. Artifact 分类

| Artifact | 责任方 | 新鲜度主键 | 在线策略 |
| --- | --- | --- | --- |
| `metadata_snapshot` | context_graph | `site + datasource_luid + schema_hash` | 必须可用 |
| `field_semantic_index` | retrieval plane | `site + datasource_luid + schema_hash + semantic_version` | 可降级 |
| `field_values_index` | retrieval plane | `site + datasource_luid + schema_hash + values_version` | 可降级 |
| `fewshot_index` | memory plane | `site + scope + datasource_luid + memory_version` | 可选 |
| `result_manifest` | query_graph | `run_id` | 每轮必备 |
| `profiles/*` | query_graph | `run_id + profile_version` | 大结果洞察必备 |
| `chunks/*` | query_graph | `run_id + chunk_version` | 行级读取时必备 |

## 3. 新鲜度状态

每个可复用 artifact 必须有显式状态：

- `missing`
- `building`
- `ready`
- `stale`
- `failed`

禁止“猜测可用”。

## 4. 在线决策矩阵

### 4.1 必需工件

- `metadata_snapshot` 缺失或 identity 不匹配时：硬失败。

### 4.2 可降级工件

对于 `field_semantic_index/field_values_index`：

- `ready`：直接使用
- `stale`：按策略可读 stale，同时异步刷新
- `building`：若有旧版本可读则降级使用，否则降级到简化检索
- `missing`：降级并排队构建
- `failed`：降级并记录可观测告警

### 4.3 请求路径守则

在线请求默认只能：

- 复用已有工件
- 入队异步刷新/构建
- 执行有界 fallback

默认禁止在线全量 rebuild。

## 5. 触发条件

触发刷新/重建的条件：

- `schema_hash` 变化
- 字段集合差异（增删改）
- TTL 过期
- value/few-shot 反馈阈值触发
- parser/semantic 版本变化
- 运维显式修复请求

## 6. 增量重建优先

### 6.1 field semantic

- 未变化字段复用旧推断结果
- 新增/变化字段增量推断
- 删除字段做 tombstone

### 6.2 field values

- 优先重建“热点字段 + 高失败字段”
- 保留字段级 freshness 元数据
- 避免在线全量扫表

### 6.3 few-shot / memory index

- 尽量 append-only
- 索引可重建，源记录分离保存

## 7. 异步组件

建议组件：

- `ArtifactBuilder`
- `ArtifactRefresher`
- `ArtifactCompactor`

`prepare_datasource_artifacts` 应升级为正式异步预热入口。

## 8. 锁与幂等

分布式锁 key 建议：

- `artifact:lock:{site}:{datasource_luid}:{schema_hash}:{artifact_type}`
- `artifact:lease:{site}:{datasource_luid}:{schema_hash}:{artifact_type}`

规则：

- 同一 key 同时只允许一个 builder。
- 重复构建请求合并。
- 刷新期间可按策略继续读取 stale。

## 9. 观测指标

- hit/miss/stale rate
- refresh 队列深度
- 各 artifact build latency
- 降级率
- 重建放大比（changed vs rebuilt）

## 10. 失败策略

- 严禁跨租户/跨数据源复用 artifact。
- metadata identity 不匹配必须失败，不可降级。
- `EMPTY_RESULT` 不属于新鲜度失败。
- 连续构建失败必须触发运维告警。
