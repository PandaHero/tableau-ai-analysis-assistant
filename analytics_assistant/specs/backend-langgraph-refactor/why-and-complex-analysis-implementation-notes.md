# Why And Complex Analysis Implementation Notes

> Date: 2026-03-13
> Scope: why / complex planner runtime

## Current Runtime State

- `step_kind` has been promoted from schema metadata into real planner runtime behavior.
- The default why plan now uses five stable steps:
  1. `verify_anomaly`
  2. `rank_explanatory_axes`
  3. `screen_top_axes`
  4. `locate_anomalous_slice`
  5. `synthesize_cause`
- `screen_top_axes` is now an explicit query step instead of an implicit `rank -> locate` carry-forward.
- `why_screening_wave` is now a formal feature flag:
  - default on
  - can be overridden at tenant / session / request scope
  - rollback keeps the flow inside root-native planner and only removes the explicit screening wave
- `root_graph.planner.screening_top_k` currently defaults to `2`, so why flows only carry the top-K ranked axes into screening and locate.
- `EvidenceContext.axis_scores` now records both ranking evidence and screening evidence for downstream axis-aware grounding.
- `screen_top_axes` and `locate_anomalous_slice` both read prior why evidence instead of relying only on static step definitions.
- Final planner output is now handed to `answer_graph` as a formal `evidence_bundle_dict`:
  - planner runtime accumulates step evidence into `EvidenceContext`
  - `planner_support.build_evidence_bundle_dict(...)` turns that evidence chain into the final answer/replan input
  - `answer_graph` now builds final insight from the bundle and then runs final replan on the same bundle

## Runtime Semantics

### 1. `rank_explanatory_axes`

- Purpose:
  - rank candidate explanatory axes for the current why question
- Output:
  - `candidate_axes`
  - `validated_axes`
  - initial `axis_scores`

### 2. `screen_top_axes`

- Purpose:
  - run live screening queries for the top-K axes
- Input:
  - prior `axis_scores`
  - `screening_top_k`
  - prior why evidence
- Output:
  - screening-retained axes
  - screening step evidence for downstream locate/synthesis

When `why_screening_wave = false`:

- the why plan falls back to:
  1. `verify_anomaly`
  2. `rank_explanatory_axes`
  3. `locate_anomalous_slice`
  4. `synthesize_cause`
- rollback stays on the current root-native planner path
- no legacy executor path is reintroduced

### 3. `locate_anomalous_slice`

- Purpose:
  - continue only on the axes that survived screening
- Priority:
  1. latest `screen_top_axes` result
  2. fallback to `rank_explanatory_axes` only when screening evidence is absent

## Screening Scoring

- `screen_top_axes` no longer keeps axis order only from prior ranking.
- The screening step now uses live query results to compute deterministic `axis_scores`.
- Current scoring behavior:
  - detect which axis was actually grounded into the screening query
  - confirm that the screening query returned rows
  - estimate grouped contribution concentration from measure values in `tableData`
  - boost the screened axis with higher `explained_share` and confidence
  - keep unscreened axes as retained fallbacks with lower confidence

This means:

- `locate_anomalous_slice` now follows the axis that was truly screened and confirmed by data
- not just the original semantic ranking order

## Files

- `analytics_assistant/src/agents/semantic_parser/schemas/planner.py`
- `analytics_assistant/src/agents/semantic_parser/nodes/global_understanding.py`
- `analytics_assistant/src/agents/semantic_parser/prompts/prompt_builder.py`
- `analytics_assistant/src/orchestration/workflow/planner_support.py`
- `analytics_assistant/src/orchestration/root_graph/planner_runtime.py`
- `analytics_assistant/tests/agents/semantic_parser/nodes/test_planner.py`
- `analytics_assistant/tests/orchestration/workflow/test_root_graph_runner.py`
- `analytics_assistant/tests/orchestration/workflow/test_planner_support.py`

## Covered Behavior

1. `serialize_plan_step(...)` keeps `stepKind` and `candidateAxes`.
2. `prompt_builder` writes `axis_scores` into `evidence_context` for why follow-up steps.
3. `rank_explanatory_axes` provides the initial explanatory-axis ordering.
4. `screen_top_axes` consumes the ranked axes as top-K screening input.
5. `screen_top_axes` now produces data-backed `axis_scores`.
6. `locate_anomalous_slice` continues on the screening-retained axes instead of the raw pre-screen order.
7. Final planner evidence is handed to `answer_graph` as a formal `evidence_bundle_dict`, not as an old `data_profile_dict` bridge.
8. Planner final insight no longer needs an external `prebuilt_insight_output_dict`; `answer_graph` can build it directly from the final evidence bundle.
9. `why_screening_wave` can be rolled back per tenant/session/request without leaving the new stack.

## Validation

- `pytest analytics_assistant/tests/agents/semantic_parser/nodes/test_planner.py -q -o log_cli=false`
- `pytest analytics_assistant/tests/orchestration/workflow/test_root_graph_runner.py -q -o log_cli=false`
- `pytest analytics_assistant/tests/orchestration/root_graph/test_feature_flags.py -q -o log_cli=false`
- `pytest analytics_assistant/tests/orchestration/workflow/test_planner_support.py -q -o log_cli=false`
- `pytest analytics_assistant/tests/orchestration/workflow/test_executor.py analytics_assistant/tests/agents/semantic_parser/nodes/test_planner.py analytics_assistant/tests/agents/semantic_parser/test_planner_schema.py -q -o log_cli=false`
- `pytest analytics_assistant/tests/api/routers/test_chat.py -k "feature_flags_to_root_graph_runner" -q -o log_cli=false`
- `python -m compileall analytics_assistant/src/orchestration/workflow/planner_support.py`
