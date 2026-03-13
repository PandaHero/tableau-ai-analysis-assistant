# Insight Large Result Design

> Status: Draft v1.1
> Read order: 8/14
> Upstream: [design.md](./design.md), [middleware.md](./middleware.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md)
> Downstream: [node-catalog.md](./node-catalog.md), [migration.md](./migration.md), [tasks.md](./tasks.md)

## 1. 设计问题

本文件回答四个问题：

1. 全量统计到底要算哪些内容？
2. “按需文件读取”在工程上如何落地？
3. 当前结果不足时，如何触发可控补查？
4. 洞察与重规划如何协同而不互相污染？

## 2. 全量统计（确定性）

大结果洞察不应让模型扫全量行，而应先计算统计工件。

### 2.1 必算项

- 行数、列数、schema
- 每列空值率、去重数
- 数值列 min/max/mean/std/p5/p50/p95
- 类别列 top-k + 占比
- 时间覆盖区间与建议粒度

### 2.2 推荐项

- 关键度量的日/周/月 rollup
- 关键维度贡献度（top-n）
- 异常点标记（IQR/z-score）
- 关键字段重复率

### 2.3 产物文件

- `result_manifest.json`
- `profiles/column_profile.json`
- `profiles/numeric_stats.json`
- `profiles/category_topk.json`
- `profiles/time_rollup_day.json`
- `profiles/segment_contribution.json`

## 3. 按需文件读取

### 3.1 原则

- 模型不能一次性拿到完整结果集。
- 只能通过只读工具按需拉取片段。
- 每次读取必须分页且受限。

### 3.2 典型流程

1. `list_result_files`
2. `describe_result_file`
3. `read_result_rows`（列裁剪 + 过滤 + 分页）
4. 必要时继续下一页

### 3.3 防护

- `limit` 上限强约束
- 强制显式列选择
- 过滤语法仅支持轻量操作
- 路径必须在当前 run 工作区

## 4. 结果不足时的处理

`answer_graph` 只能产出三种决策：

- `answer_with_caveat`：给出结论并明确不确定性
- `clarify_interrupt`：向用户澄清范围
- `replan_query`：补查（受限）

补查路径：

- 复用当前 `semantic_state`
- 仅调整 query 约束（粒度、过滤、时间窗、分组）
- 回到 `query_graph`，不重跑全语义解析

只有用户意图变化时才回到 `semantic_graph`。

## 5. 洞察与重规划的边界

- 洞察负责解释，不负责构造可执行查询。
- 重规划负责决策与约束组装，不负责解释证据。
- 两者解耦保证可审计与可回放。

推荐循环上限：

- 默认最多 1 次自动重规划
- 后续需用户确认（interrupt）

## 6. 与新鲜度/检索平面的关系

- 检索与记忆仅提供提示增强，不可替代当前 run 的证据。
- 洞察必须绑定当前 `result_manifest_ref` 版本。
- 旧 run 的 artifact 可用于“候选问题生成”，不可用于“当前结论证据”。
