# Insight Large Result Design

> Status: Draft v1.0
> Read order: 6/12
> Upstream: `requirements.md`, `design.md`, `middleware.md`, `data-and-api.md`
> Downstream: `migration.md`, `tasks.md`
> Purpose: Define how insight works when result size is large (e.g., 100k rows).

## 1. Scope

This document answers four concrete questions:

1. What does "full statistics computation" include?
2. What does "on-demand file reading" mean in practice?
3. If results are insufficient for insight, what is the requery flow?
4. What is the relationship between replanning and insight?

## 2. Full Statistics Computation

The large-result insight pipeline does **not** ask the model to scan all rows.
Instead, it runs **deterministic, full-scan statistics** and stores them as artifacts.

### 2.1 Required (always computed)

- Row count, column count, schema (name, type).
- Null rate per column.
- Distinct count per column.
- Basic numeric stats: min, max, mean, std, p5/p50/p95.
- Top-K categorical values with counts and percentage.
- Time coverage and granularity (min/max timestamp, suggested grain).
- Primary sort and data ordering (if present).

### 2.2 Strongly recommended (computed when applicable)

- Time rollups by day/week/month for key measures.
- Segment contribution: top-N groups by a small set of candidate dimensions.
- Outlier flags for numeric measures (IQR or z-score).
- Duplicate key rate if a natural key exists.
- "Change drivers" candidate summary: top-N positive/negative movers by dimension.

### 2.3 Optional (cost-aware)

- Correlation matrix for numeric measures (capped to top-M measures).
- Histogram bins for large numeric columns.
- Two-way pivot summaries (one dimension + one measure).

### 2.4 Artifact outputs

All above are materialized as small artifacts:

- `profiles/column_profile.json`
- `profiles/numeric_stats.json`
- `profiles/category_topk.json`
- `profiles/time_rollup_day.json`
- `profiles/segment_contribution.json`
- `profiles/outlier_flags.json`
- `result_manifest.json` (always)

## 3. On-Demand File Reading

On-demand means:

- The model never sees the full dataset in a single prompt.
- The model asks for **specific file slices** via tools.
- Each tool call has a **bounded, paginated** response.

### 3.1 Tool protocol

Tools exposed by `InsightFilesystemMiddleware`:

- `list_result_files`
- `describe_result_file`
- `read_result_file` (text artifacts, paginated)
- `read_result_rows` (table rows, paginated, column/filters)
- `read_spilled_artifact`

### 3.2 Typical read flow

1. `list_result_files` to identify what is available.
2. `describe_result_file` to see schema, row count, chunks, and columns.
3. Use `read_result_rows` with `columns + limit + offset + filters`.
4. Only request more pages if the answer truly needs more evidence.

### 3.3 Example interaction

```text
list_result_files()
describe_result_file(file="result.parquet")
read_result_rows(file="result.parquet", columns=["date","region","sales"], filters={"date": "last_30_days"}, limit=200, offset=0)
read_result_rows(file="result.parquet", columns=["date","region","sales"], filters={"date": "last_30_days", "region": "East"}, limit=200, offset=200)
```

### 3.4 Guardrails

- Hard limit on `limit` per call.
- Require explicit `columns`.
- Allow only simple filters (equality, range).
- All reads restricted to the current run's artifact root.

## 4. When Results Are Insufficient

If the current result does not support an insight, the system does **not** blindly re-run the full semantic pipeline.

### 4.1 Decision points

The `answer_graph` issues one of three decisions:

- `answer_with_caveat`: Output a weaker insight with explicit uncertainty.
- `clarify_interrupt`: Ask the user to refine scope.
- `replan_query`: Issue a requery with adjusted constraints.

### 4.2 Requery path

If `replan_query` is chosen:

- Reuse existing `semantic_state`.
- Adjust only query constraints (time window, filters, grain, grouping).
- Pass directly to `query_graph` without re-running semantic parsing.

Only if the user **changes intent** do we re-run `semantic_graph`.

## 5. Replanning vs Insight

They are related but should not be merged.

### 5.1 Why not merge

- Insight is an **interpretation** step.
- Replanning is a **query construction** step.
- If merged, the model would be allowed to generate executable queries directly, which breaks determinism and auditability.

### 5.2 How they cooperate

1. Insight runs and detects "missing evidence".
2. It emits a **replan request** with constraints.
3. Replan node compiles a deterministic query plan.
4. Query runs and produces new artifacts.
5. Insight runs again (bounded loop).

### 5.3 Loop limits

- Max 1 automatic replan per user request.
- Additional replans require user confirmation (`interrupt/resume`).

## 6. Summary

For 100k rows:

- Full statistics are computed deterministically and stored as artifacts.
- Insight reads artifacts and bounded file slices only.
- Replanning is a controlled loop, not an open-ended model-driven cycle.
