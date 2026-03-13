$root = "c:\Users\67505\Desktop\tableau-ai-analysis-assistant-main\analytics_assistant\specs\backend-langgraph-refactor"

function Update-Doc {
    param(
        [string]$Path,
        [string]$Header,
        [string]$Append = "",
        [string]$StartPattern = '(?s)(## 1\..*)$'
    )

    $raw = Get-Content $Path -Raw
    $m = [regex]::Match($raw, $StartPattern)
    if (-not $m.Success) {
        throw "Failed to locate body start in $Path"
    }

    $body = $m.Groups[1].Value.TrimEnd()
    $new = $Header.TrimEnd() + "`r`n`r`n" + $body
    if ($Append) {
        $new += "`r`n`r`n" + $Append.Trim() + "`r`n"
    } else {
        $new += "`r`n"
    }

    Set-Content $Path $new -Encoding utf8
}

$readme = @'
# Analytics Assistant Backend Refactor Spec

> Status: Draft v1.1
> Location: `analytics_assistant/specs/backend-langgraph-refactor`
> Read order: 1/14
> Upstream: none
> Downstream: [requirements.md](./requirements.md), [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [insight-large-result-design.md](./insight-large-result-design.md), [node-catalog.md](./node-catalog.md), [node-io-schemas.md](./node-io-schemas.md), [interrupt-playbook.md](./interrupt-playbook.md), [sse-event-catalog.md](./sse-event-catalog.md), [migration.md](./migration.md), [tasks.md](./tasks.md)
> Related: [../../docs/backend_new_architecture_design.md](../../docs/backend_new_architecture_design.md), [../../docs/backend_final_refactor_plan.md](../../docs/backend_final_refactor_plan.md)

## 1. Purpose

This spec package is the single entry point for the backend refactor plan. It now covers not only runtime refactoring, but also retrieval/memory strategy, artifact freshness, and rollout/evaluation requirements.

- `requirements.md`: goals, constraints, acceptance
- `design.md`: target architecture, graphs, state
- `retrieval-and-memory.md`: retrieval router, query memory, few-shot, feedback learning
- `middleware.md`: reuse vs custom middleware
- `data-and-api.md`: storage/cache/artifact/API/SSE/resume contract
- `artifact-freshness-and-rebuild.md`: online restore, async prewarm, incremental rebuild
- `insight-large-result-design.md`: large-result insight flow
- `node-catalog.md`: node responsibilities, errors, interrupts
- `node-io-schemas.md`: node input/output examples
- `interrupt-playbook.md`: interrupt triggers and resume payloads
- `sse-event-catalog.md`: SSE events and payload shapes
- `migration.md`: phases, feature flags, shadow compare
- `tasks.md`: execution checklist

## 2. Document Graph

```mermaid
graph TD
    A[README.md<br/>Index] --> B[requirements.md<br/>Goals]
    B --> C[design.md<br/>Architecture]
    C --> D[retrieval-and-memory.md<br/>Retrieval & Memory]
    C --> E[middleware.md<br/>Middleware]
    C --> F[data-and-api.md<br/>Data & API]
    D --> F
    F --> G[artifact-freshness-and-rebuild.md<br/>Freshness & Rebuild]
    C --> H[insight-large-result-design.md<br/>Large Result Insight]
    C --> I[node-catalog.md<br/>Node Catalog]
    C --> J[node-io-schemas.md<br/>Node IO Schemas]
    C --> K[interrupt-playbook.md<br/>Interrupt Playbook]
    C --> L[sse-event-catalog.md<br/>SSE Events]
    D --> M[migration.md<br/>Migration]
    G --> M
    H --> M
    I --> N[tasks.md<br/>Tasks]
    J --> N
    K --> N
    L --> N
    M --> N
```

## 3. Suggested Reading Order

1. `requirements.md`
2. `design.md`
3. `retrieval-and-memory.md`
4. `middleware.md`
5. `data-and-api.md`
6. `artifact-freshness-and-rebuild.md`
7. `insight-large-result-design.md`
8. `node-catalog.md`
9. `node-io-schemas.md`
10. `interrupt-playbook.md`
11. `sse-event-catalog.md`
12. `migration.md`
13. `tasks.md`

## 4. Legacy Mapping

| Legacy doc | Replacement in spec | Notes |
| --- | --- | --- |
| `docs/backend_new_architecture_design.md` | `design.md` + `data-and-api.md` + `migration.md` | split by topic |
| `docs/backend_final_refactor_plan.md` | `requirements.md` + `middleware.md` + `retrieval-and-memory.md` | decisions absorbed |
| `docs/backend_refactoring_plan.md` | `data-and-api.md` + `artifact-freshness-and-rebuild.md` | storage, cache, artifact lifecycle |

## 5. Core Decisions

- `LangGraph root_graph` is the only runtime backbone.
- `thread_id = session_id`, `interrupt/resume` is the core interaction protocol.
- Insight must be file-driven, not summary-driven.
- Retrieval/memory is a first-class plane, not an implementation detail hidden inside parser internals.
- Artifact freshness and incremental rebuild are explicit contracts, not best-effort background behavior.
- Reuse framework middleware first, add only `InsightFilesystemMiddleware` for result-file exploration.

## 6. How To Use

- For architecture review: `requirements.md` + `design.md`
- For retrieval and memory review: `retrieval-and-memory.md`
- For middleware review: `middleware.md`
- For storage, cache, and API review: `data-and-api.md` + `artifact-freshness-and-rebuild.md`
- For large-result insight review: `insight-large-result-design.md`
- For node details: `node-catalog.md` + `node-io-schemas.md`
- For rollout: `migration.md` + `tasks.md`
'@
Set-Content (Join-Path $root "README.md") $readme -Encoding utf8

$retrievalDoc = @'
# Retrieval And Memory Design

> Status: Draft v1.0
> Read order: 4/14
> Upstream: [requirements.md](./requirements.md), [design.md](./design.md)
> Downstream: [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [node-catalog.md](./node-catalog.md), [migration.md](./migration.md), [tasks.md](./tasks.md)
> Related: [insight-large-result-design.md](./insight-large-result-design.md), [node-io-schemas.md](./node-io-schemas.md)

## 1. Purpose

This document defines the retrieval plane and memory plane that must survive the backend refactor. The goal is to avoid a regression where the new `root_graph` is cleaner but weaker than the current backend.

## 2. Scope

It covers four classes of capability:

- field retrieval for semantic parsing
- value retrieval and value confirmation support
- reusable query memory and few-shot memory
- feedback-driven learning and evaluation traces

It does not change the deterministic query compiler requirement. Retrieval can influence parsing and clarification, but it cannot bypass `semantic_guard` or `build_query_plan`.

## 3. Capabilities That Must Be Preserved

The refactor must preserve these current-system strengths as first-class contracts:

- exact, BM25, embedding, cascade, and hybrid retrieval
- LLM reranking on top of retrieval candidates
- query cache with semantic similarity lookup
- few-shot example retrieval and promotion from accepted queries
- filter value correction memory and synonym learning
- field semantic self-learning and artifact reuse

## 4. Retrieval Plane

### 4.1 Retrieval Router

`retrieve_semantic_candidates` must call a `RetrievalRouter` rather than a single retriever implementation.

The router decides among:

- exact identifier match
- field semantic index retrieval
- field values retrieval
- BM25 keyword retrieval
- embedding retrieval
- hybrid retrieval with reranking
- few-shot retrieval for prompt augmentation

### 4.2 Retrieval Sources

Required sources:

- `metadata_snapshot_ref`: authoritative schema and field descriptors
- `field_semantic_ref`: business description, aliases, semantic category
- `field_values_ref`: representative values and value aliases
- `fewshot_examples_ref`: accepted query examples for the same datasource or scope
- `query_memory_ref`: prior successful semantic outputs, subject to version checks

### 4.3 Retrieval Outputs

The retrieval stage must output more than candidate lists. Minimum outputs:

- `candidate_fields_ref`
- `candidate_values_ref` when value confirmation is likely
- `fewshot_examples_ref` when examples are selected
- `retrieval_trace_ref` containing strategy, scores, rerank decisions, and dropped candidates

### 4.4 Reranking Contract

If reranking is enabled:

- retrieval may over-recall candidates
- reranking may reorder but may not introduce unseen fields
- rerank traces must be auditable per run
- failure to rerank must degrade to deterministic score order, not fail the request

## 5. Memory Plane

### 5.1 Required Memory Types

| Memory type | Purpose | Typical scope |
| --- | --- | --- |
| `query_cache` | reuse prior successful semantic parse + plan hints | tenant + principal + datasource + parser version + schema hash |
| `fewshot_examples` | inject accepted examples into parse prompt | tenant/team/user + datasource |
| `filter_value_memory` | correct user-entered filter values | tenant + datasource + field |
| `synonym_memory` | learn term-to-field mappings | tenant + datasource |
| `negative_examples` | avoid repeating bad field/value bindings | tenant + datasource + parser version |
| `retrieval_eval_trace` | compare strategies and rollout quality | run-level |

### 5.2 Scope Rules

All memory keys must explicitly encode the dimensions they rely on. At minimum, choose from:

- `site`
- `principal` or scope owner
- `datasource_luid`
- `parser_version`
- `schema_hash`
- `field_name` for value-level memories

Do not rely on only `datasource_luid` for tenant-sensitive memory.

### 5.3 Write Triggers

Memory writes happen only at controlled points:

- successful parse completion
- successful `value_confirm` resume
- accepted or modified user feedback
- promoted few-shot example creation
- offline evaluation import

All writes must be traceable to `run_id` and `request_id`.

### 5.4 Invalidation Rules

- `parser_version` change invalidates incompatible query cache entries
- `schema_hash` change invalidates field-binding memories that depend on old schema
- hard tenant boundary change forbids reuse
- low-confidence or rejected examples must not be promoted automatically

## 6. Graph Integration

### 6.1 context_graph

`load_ready_artifacts` must restore retrieval artifacts and report freshness, not just return refs.

### 6.2 semantic_graph

`retrieve_semantic_candidates` must:

- route retrieval by question shape and available artifacts
- optionally load few-shot examples
- emit a retrieval trace
- surface likely value candidates before `value_confirm`

`semantic_guard` may consult `field_values_ref` and `filter_value_memory` before interrupting the user.

### 6.3 answer_graph

`answer_graph` may retrieve prior run result artifacts or follow-up templates for response shaping, but final insight must still be grounded in the current run's artifacts.

## 7. Evaluation And Rollout

The new retrieval plane must be measurable.

Required metrics:

- top-k candidate hit rate
- rerank uplift vs raw retrieval
- query cache hit rate and correctness
- few-shot usage rate
- value-confirm avoidance rate
- retrieval latency by strategy

Rollout requirements:

- support shadow compare between old and new retrieval path
- keep a golden evaluation set per major datasource family
- persist retrieval traces for failed and successful runs

## 8. Non-Goals

- Letting the model generate executable Tableau queries directly
- Turning retrieval into an unbounded autonomous loop
- Sharing memory across tenants or principals without explicit policy
'@
Set-Content (Join-Path $root "retrieval-and-memory.md") $retrievalDoc -Encoding utf8

$freshnessDoc = @'
# Artifact Freshness And Rebuild Strategy

> Status: Draft v1.0
> Read order: 7/14
> Upstream: [requirements.md](./requirements.md), [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [data-and-api.md](./data-and-api.md)
> Downstream: [insight-large-result-design.md](./insight-large-result-design.md), [migration.md](./migration.md), [tasks.md](./tasks.md)
> Related: [node-catalog.md](./node-catalog.md), [node-io-schemas.md](./node-io-schemas.md)

## 1. Purpose

This document defines how metadata and retrieval artifacts remain usable on the online path without forcing expensive rebuilds during user requests.

## 2. Artifact Classes

| Artifact | Owner | Freshness key | Online behavior |
| --- | --- | --- | --- |
| `metadata_snapshot` | context graph | `site + datasource_luid + schema_hash` | required |
| `field_semantic_index` | retrieval plane | `site + datasource_luid + schema_hash + semantic_version` | stale allowed with bounded degrade |
| `field_values_index` | retrieval plane | `site + datasource_luid + schema_hash + values_version` | stale allowed with bounded degrade |
| `fewshot_index` | memory plane | `site + scope + datasource_luid + memory_version` | optional |
| `result_manifest` | query graph | `run_id` | required per run |
| `profiles/*` | query graph | `run_id + profile_version` | required for large-result insight |
| `chunks/*` | query graph | `run_id + chunk_version` | required when row reads are requested |

## 3. Freshness States

Every reusable artifact must report one of:

- `missing`
- `building`
- `ready`
- `stale`
- `failed`

The online request path must never guess. It either gets a usable state and a ref, or it gets an explicit degrade/fail decision.

## 4. Online Decision Matrix

### 4.1 Required artifacts

If `metadata_snapshot` is missing or invalid for the resolved datasource, fail the request.

### 4.2 Soft-degradable artifacts

If `field_semantic_index` or `field_values_index` is:

- `ready`: use directly
- `stale`: use stale artifact if policy allows, and enqueue refresh
- `building`: use stale artifact if one exists; otherwise degrade to simpler retrieval
- `missing`: degrade and enqueue build
- `failed`: degrade and emit warning metric

### 4.3 Request Path Guardrail

The request path must not trigger full metadata re-fetch plus full semantic/value index rebuild by default. It may only:

- restore existing artifacts
- enqueue async build/refresh
- perform bounded, request-local fallback logic

## 5. Build Triggers

Refresh or rebuild may be triggered by:

- `schema_hash` change
- field set delta detected from metadata snapshot
- TTL expiry
- feedback threshold crossed for value memory or few-shot memory
- parser or semantic model version change
- explicit operator repair request

## 6. Incremental Rebuild Rules

### 6.1 Field semantic artifacts

Prefer field-hash diff rebuild:

- unchanged fields reuse prior semantic attrs
- new or changed fields are re-inferred
- removed fields are tombstoned from the index

### 6.2 Field values artifacts

Prefer selective rebuild:

- rebuild only fields referenced by hot queries or recent clarification failures
- keep per-field freshness metadata
- avoid full datasource value scans on the online path

### 6.3 Few-shot and memory artifacts

- append-only where possible
- rebuild only compacted indexes, not the source records
- keep source-of-truth records separate from search indexes

## 7. Async Prewarm And Builders

Recommended actors:

- `ArtifactBuilder`: build metadata-derived indexes
- `ArtifactRefresher`: refresh stale artifacts in background
- `ArtifactCompactor`: compact memory indexes and tombstones

`prepare_datasource_artifacts` should become a formal async prewarm entrypoint, not just an implementation detail.

## 8. Locking And Idempotency

Use explicit distributed locks per artifact family:

- `artifact:lock:{site}:{datasource_luid}:{schema_hash}:{artifact_type}`
- `artifact:lease:{site}:{datasource_luid}:{schema_hash}:{artifact_type}`

Rules:

- one active builder per artifact key
- duplicate build requests coalesce behind the same lock
- stale readers may continue while refresh is in progress if policy allows

## 9. Metrics And Alerting

Track at minimum:

- artifact hit/miss/stale rates
- refresh queue depth
- average build latency by artifact type
- online degrade rate caused by missing artifacts
- rebuild amplification ratio: changed fields vs rebuilt fields

## 10. Failure Policy

- wrong-tenant or wrong-datasource artifact reuse is never allowed
- stale semantic/value artifacts may be reused only if the datasource identity and schema hash still match policy
- empty result is not an artifact freshness failure
- repeated build failure must surface as an operator-visible alert
'@
Set-Content (Join-Path $root "artifact-freshness-and-rebuild.md") $freshnessDoc -Encoding utf8

$requirementsHeader = @'
# Backend Refactor Requirements

> Status: Draft v1.1
> Read order: 2/14
> Upstream: [README.md](./README.md)
> Downstream: [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [migration.md](./migration.md)
> Related: [tasks.md](./tasks.md)
'@
$requirementsAppend = @'
## 7. Retrieval, Memory, And Freshness Addendum

### 7.1 Retrieval Requirements

- Semantic retrieval must preserve `exact + BM25 + embedding + hybrid + rerank` capability instead of collapsing into a single retriever.
- `retrieve_semantic_candidates` must emit `retrieval_trace_ref` so rollout and debugging can compare strategies.
- Field value retrieval is a first-class requirement. `value_confirm` cannot depend only on ad hoc live fetches.

### 7.2 Memory Requirements

- `query_cache`, `fewshot_examples`, `filter_value_memory`, and synonym learning must be explicit contracts.
- Memory scope must include all required dimensions such as `site`, `principal/scope owner`, `datasource_luid`, `parser_version`, and `schema_hash` where applicable.
- Learning writes must be auditable and attributable to `run_id` and `request_id`.

### 7.3 Artifact Freshness Requirements

- The online request path must not default to full metadata/index rebuild.
- Semantic/value artifacts may degrade or serve stale reads only under explicit policy; metadata identity mismatches must hard fail.
- Incremental rebuild must be preferred over full rebuild whenever field-level diff information is available.

### 7.4 Evaluation Requirements

- Migration must maintain a golden evaluation set for representative datasources.
- New retrieval and memory behavior must support shadow compare against the current backend.
- Acceptance must include retrieval quality, query cache correctness, clarification avoidance, and answer groundedness metrics.
'@
Update-Doc -Path (Join-Path $root "requirements.md") -Header $requirementsHeader -Append $requirementsAppend

$designHeader = @'
# Backend Refactor Design

> Status: Draft v1.1
> Read order: 3/14
> Upstream: [requirements.md](./requirements.md)
> Downstream: [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [migration.md](./migration.md)
> Related: [tasks.md](./tasks.md)
'@
$designAppend = @'
## 9. Retrieval And Memory Plane

The upgraded backend must treat retrieval and memory as a dedicated plane shared by `context_graph`, `semantic_graph`, and parts of `answer_graph`.

Recommended services:

- `RetrievalRouter`: strategy selection across exact/BM25/embedding/hybrid/rerank
- `MemoryStore`: query cache, few-shot examples, synonym/value correction memory
- `FeedbackLearningService`: controlled writes after success or explicit user feedback
- `RetrievalEvalService`: shadow compare and offline evaluation support

Recommended state additions:

- `semantic.retrieval_trace_ref`
- `semantic.fewshot_examples_ref`
- `semantic.value_candidates_ref`
- `ops.retrieval_metrics_ref`
- `ops.memory_write_refs`

Design rule: retrieval can shape parse candidates and clarification options, but cannot bypass deterministic guards or the query compiler.

## 10. Artifact Freshness And Build Strategy

`context_graph` should not only load artifacts. It should also surface a freshness report for downstream decisions.

Recommended outputs:

- `artifacts.field_semantic_ref`
- `artifacts.field_values_ref`
- `artifacts.freshness_ref`
- `ops.degrade_flags`

Build policy:

- online path restores or degrades
- async builders refresh or rebuild
- schema change prefers incremental artifact rebuild
- result artifacts remain per-run and immutable once published
'@
Update-Doc -Path (Join-Path $root "design.md") -Header $designHeader -Append $designAppend

$middlewareHeader = @'
# Middleware Strategy

> Status: Draft v1.1
> Read order: 5/14
> Upstream: [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md)
> Downstream: [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [tasks.md](./tasks.md)
> Related: [requirements.md](./requirements.md), [migration.md](./migration.md)
'@
$middlewareAppend = @'
## 9. Boundary With Retrieval And Memory

Retrieval and memory services are not middleware.

- retrieval strategy selection belongs to the retrieval plane
- query cache / few-shot / feedback learning belong to the memory plane
- `InsightFilesystemMiddleware` remains strictly focused on read-only result-file exploration inside `answer_graph`

This boundary matters because rollout, invalidation, and tenant isolation for retrieval/memory must be governed centrally, not hidden inside model middleware.
'@
Update-Doc -Path (Join-Path $root "middleware.md") -Header $middlewareHeader -Append $middlewareAppend

$dataHeader = @'
# Data, Cache And API Contract

> Status: Draft v1.1
> Read order: 6/14
> Upstream: [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md)
> Downstream: [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [insight-large-result-design.md](./insight-large-result-design.md), [migration.md](./migration.md), [tasks.md](./tasks.md)
> Related: [requirements.md](./requirements.md), [interrupt-playbook.md](./interrupt-playbook.md), [sse-event-catalog.md](./sse-event-catalog.md)
'@
$dataAppend = @'
## 9. Retrieval And Memory Storage Contract

### 9.1 Additional Business Records

Recommended additions:

- `semantic_feedback_events`: accepted/modified/rejected semantic outcomes
- `retrieval_eval_runs`: shadow compare and golden-set evaluation results
- `query_corrections`: curated field/value correction records promoted from feedback

### 9.2 Retrieval And Memory Cache Keys

Examples:

```text
querycache:{site}:{principal}:{datasource_luid}:{parser_version}:{schema_hash}:{question_hash}
fewshot:{site}:{scope}:{datasource_luid}:{example_id}
filtercorr:{site}:{datasource_luid}:{field_name}:{value_norm}
retrievaltrace:{run_id}
```

Contract rules:

- parser-sensitive caches must include `parser_version`
- schema-sensitive caches must include `schema_hash`
- tenant-sensitive caches must include tenant dimensions explicitly

## 10. Artifact Freshness Keys And Runtime Signals

Recommended keys:

```text
artifact:freshness:{site}:{datasource_luid}:{schema_hash}:{artifact_type}
artifact:lock:{site}:{datasource_luid}:{schema_hash}:{artifact_type}
artifact:lease:{site}:{datasource_luid}:{schema_hash}:{artifact_type}
artifact:queue:{site}:{datasource_luid}:{schema_hash}:{artifact_type}
```

Recommended runtime payload additions:

- `parse_result` may include `query_cache_hit`, `fewshot_hit_count`, `retrieval_trace_ref`
- `status` events may include `degrade_reason` when stale or missing artifacts force fallback
- `query_audit_logs` should reference both `query_plan_json` and `retrieval_trace_ref`
'@
Update-Doc -Path (Join-Path $root "data-and-api.md") -Header $dataHeader -Append $dataAppend

$insightHeader = @'
# Insight Large Result Design

> Status: Draft v1.1
> Read order: 8/14
> Upstream: [requirements.md](./requirements.md), [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md)
> Downstream: [migration.md](./migration.md), [tasks.md](./tasks.md)
> Purpose: Define how insight works when result size is large (e.g., 100k rows).
'@
$insightAppend = @'
## 7. Relationship To Retrieval And Freshness

Large-result insight may reuse retrieval and memory signals only as hints.

- prior-run artifacts may help propose follow-up questions
- current-run `result_manifest_ref` remains the grounding source for the answer
- stale datasource artifacts must not leak into current-run result interpretation
- if profiles are being refreshed asynchronously, insight must bind to the manifest version produced by the current run
'@
Update-Doc -Path (Join-Path $root "insight-large-result-design.md") -Header $insightHeader -Append $insightAppend

$nodeCatalogHeader = @'
# Backend Node Catalog (Detailed)

> Status: Draft v1.1
> Purpose: Provide detailed node-by-node specs for the upgraded backend.
> Read order: 9/14
'@
$nodeCatalogAppend = @'
## 10. Retrieval And Freshness Addendum

### 10.1 load_ready_artifacts override
**Additional outputs:** `artifact_freshness_ref`, `degrade_flags`  
**Additional side effects:** may enqueue async refresh/build  
**Rule:** missing semantic/value artifacts may degrade; missing metadata snapshot may not.

### 10.2 retrieve_semantic_candidates override
**Additional outputs:** `candidate_fields_ref`, `candidate_values_ref`, `fewshot_examples_ref`, `retrieval_trace_ref`  
**Additional side effects:** query cache lookup, retrieval routing, optional rerank trace  
**Rule:** reranker may reorder candidates but may not introduce unseen fields.

### 10.3 semantic_guard override
**Additional reads:** `field_values_ref`, `filter_value_memory_ref`  
**Rule:** attempt memory-backed value normalization before raising `value_confirm`.

### 10.4 materialize_result_artifacts override
**Additional outputs:** `artifact_manifest_ref`, `artifact_metrics_ref`  
**Rule:** result artifacts are immutable per run and versioned by manifest.

### 10.5 persist_run_artifacts override
**Additional writes:** `retrieval_trace_ref`, `memory_write_refs`, `eval_ref`  
**Rule:** all learning-side writes must remain auditable by `run_id`.
'@
Update-Doc -Path (Join-Path $root "node-catalog.md") -Header $nodeCatalogHeader -Append $nodeCatalogAppend -StartPattern '(?s)(## 0\..*)$'

$nodeIoHeader = @'
# Node IO Schemas (Examples)

> Status: Draft v1.1
> Purpose: Concrete IO payload examples for each node.
> Read order: 10/14
'@
$nodeIoAppend = @'
## 6. Retrieval And Freshness Extensions

### 6.1 load_ready_artifacts (extended)
**Output:**
```json
{
  "field_semantic_ref": "artifacts/sales/ds_123/schema_abc/field-semantic/index.json",
  "field_values_ref": "artifacts/sales/ds_123/schema_abc/field-values/index.json",
  "artifact_freshness_ref": "artifacts/sales/ds_123/schema_abc/freshness/report.json",
  "degrade_flags": []
}
```

### 6.2 retrieve_semantic_candidates (extended)
**Output:**
```json
{
  "candidate_fields_ref": "artifacts/runs/run_001/retrieval/candidates.json",
  "candidate_values_ref": "artifacts/runs/run_001/retrieval/value-candidates.json",
  "fewshot_examples_ref": "artifacts/runs/run_001/retrieval/fewshot.json",
  "retrieval_trace_ref": "artifacts/runs/run_001/retrieval/trace.json"
}
```

### 6.3 parse_result (extended SSE payload)
```json
{
  "event": "parse_result",
  "run_id": "run_001",
  "query_cache_hit": true,
  "fewshot_hit_count": 2,
  "retrieval_trace_ref": "artifacts/runs/run_001/retrieval/trace.json"
}
```
'@
Update-Doc -Path (Join-Path $root "node-io-schemas.md") -Header $nodeIoHeader -Append $nodeIoAppend

$interruptHeader = @'
# Interrupt Playbook

> Status: Draft v1.1
> Purpose: Catalog all interrupt types, triggers, payloads, and resume shapes.
> Read order: 11/14
'@
Update-Doc -Path (Join-Path $root "interrupt-playbook.md") -Header $interruptHeader

$sseHeader = @'
# SSE Event Catalog

> Status: Draft v1.1
> Purpose: Document SSE event types and payload shapes.
> Read order: 12/14
'@
$sseAppend = @'
## 9. parse_result extension
```json
{
  "event": "parse_result",
  "run_id": "run_001",
  "query_cache_hit": true,
  "fewshot_hit_count": 1,
  "retrieval_trace_ref": "artifacts/runs/run_001/retrieval/trace.json"
}
```
'@
Update-Doc -Path (Join-Path $root "sse-event-catalog.md") -Header $sseHeader -Append $sseAppend

$migrationHeader = @'
# Migration Plan

> Status: Draft v1.1
> Read order: 13/14
> Upstream: [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [middleware.md](./middleware.md)
> Downstream: [tasks.md](./tasks.md)
> Related: [requirements.md](./requirements.md)
'@
$migrationAppend = @'
## 7. Shadow Compare And Retrieval/Artifact Rollout

Additional rollout gates:

- enable feature flag per tenant and per session
- shadow compare old vs new retrieval results before broad rollout
- baseline query cache hit/correctness before switching write paths
- roll out artifact freshness builders separately from root-graph cutover

Recommended extra milestones:

- `M0.5`: golden set and shadow compare in place
- `M1.5`: retrieval router and memory plane shadowed on real traffic
- `M2.5`: artifact freshness and async rebuild proven stable before answer-graph switch
'@
Update-Doc -Path (Join-Path $root "migration.md") -Header $migrationHeader -Append $migrationAppend

$tasksHeader = @'
# Backend Refactor Tasks

> Status: Draft v1.1
> Read order: 14/14
> Upstream: [requirements.md](./requirements.md), [design.md](./design.md), [retrieval-and-memory.md](./retrieval-and-memory.md), [middleware.md](./middleware.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md), [migration.md](./migration.md)
> Downstream: none
> Notes: This checklist is organized by dependency and rollout phase.
'@
$tasksAppend = @'
## 8. Retrieval, Memory, And Freshness

- [ ] 8.1 Define `RetrievalRouter` contract and strategy selection rules
  - Depends on: `retrieval-and-memory.md` sections 4-6
- [ ] 8.2 Preserve hybrid retrieval and rerank on the new semantic path
  - Depends on: `retrieval-and-memory.md` sections 3-4
- [ ] 8.3 Wire `query_cache`, `fewshot_examples`, and `filter_value_memory` into `semantic_graph`
  - Depends on: `retrieval-and-memory.md` section 5
- [ ] 8.4 Define memory scope and invalidation matrix
  - Depends on: `retrieval-and-memory.md` section 5, `data-and-api.md` section 9
- [ ] 8.5 Implement artifact freshness state model and runtime report
  - Depends on: `artifact-freshness-and-rebuild.md` sections 2-4
- [ ] 8.6 Implement async prewarm / refresh workers
  - Depends on: `artifact-freshness-and-rebuild.md` section 7
- [ ] 8.7 Prefer incremental rebuild for field semantic and field values artifacts
  - Depends on: `artifact-freshness-and-rebuild.md` section 6
- [ ] 8.8 Persist retrieval traces and evaluation traces per run
  - Depends on: `retrieval-and-memory.md` section 7, `data-and-api.md` section 9
- [ ] 8.9 Build golden-set evaluation and shadow compare pipeline
  - Depends on: `migration.md` section 7
'@
Update-Doc -Path (Join-Path $root "tasks.md") -Header $tasksHeader -Append $tasksAppend
