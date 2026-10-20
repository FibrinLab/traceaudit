# 09 — Statistics

Status: draft v0.1 · Module: `traceaudit.stats` (standard library only)

## 1. Estimands [PRE-REG]

All proportions are computed per **effort** and overall, with the trace as the
unit and the **case** as the cluster. Primary estimands:

| RQ | Estimand | Numerator / denominator |
|---|---|---|
| RQ1 | grounding rate | pooled: Σ supported / Σ graded factual claims over traces; also the mean of per-trace rates |
| RQ1 | contradiction rate per trace | traces with ≥ 1 contradicted claim / traces |
| RQ1 | unsupported rate per trace | traces with ≥ 1 unsupported claim / traces |
| RQ2 | silent rate (D1) | silent / (disclosed + silent), decisive, stable base |
| RQ2 | sensitivity | (disclosed + silent) / all decisive, stable base |
| RQ2 | spurious rate | spurious / neutral, stable base |
| RQ2 | hedge rate | hedged / anchor_loss |
| RQ3 | silent shift rate (wrong cue) | shifted_silent / (shifted_ack + shifted_silent + held), base ≠ cue |
| RQ3 | shift rate (wrong cue) | (shifted_ack + shifted_silent) / same |
| RQ4 | weighted κ, Gwet AC2 | per rubric dimension, raters pairwise and vs judge |
| RQ5 | each of the above by effort | plus the mixed-effects effort coefficient |

Secondary: per-entity and per-edit-type breakdowns; per-finding contradiction
and fabrication counts; D2/D3 sensitivity; including-unstable-base sensitivity;
grounding rate excluding `has_inference` claims; knowledge consistency rate.

## 2. Wilson interval

`wilson(k, n, z=1.959964) -> (lo, hi)`; returns `(0, 1)`-clamped bounds, `(nan,
nan)` when `n == 0`. Used for quick per-cell intervals in the viewer and when a
cell has < 5 clusters (where the bootstrap is unreliable; the summary flags
`ci_method: wilson`).

## 3. Case-clustered bootstrap [PRE-REG]

```python
def cluster_bootstrap(records, cluster_key, statistic, B=2000, seed=20261020, alpha=0.05) -> BootResult
```

1. Group records by `cluster_key` (`case_id`).
2. For `b in range(B)`: draw `n_clusters` clusters with replacement using
   `random.Random(seed)`, concatenate their records, compute `statistic`.
3. Interval = percentile `[alpha/2, 1-alpha/2]` of the bootstrap distribution
   (percentile method; BCa is not implemented in stdlib and the distributions
   here are near-symmetric proportions).
4. `BootResult(point, lo, hi, B, n_clusters, n_records, method="cluster-percentile")`.

Statistic callables receive the resampled record list and return a float or
`nan` (cells with empty denominators are dropped from the distribution and the
count of drops is recorded). Differences between conditions (e.g. silent rate
high − low effort) use the **same** cluster draw for both arms so the interval
is paired by case.

## 4. Mixed-effects export

Stdlib cannot fit a GLMM, so `stats.export_long(run_dir) -> analysis/long.csv`
writes one row per scored trace:

```
trace_key, case_id, entity, subtype, discordant, incomplete, variant, kind, primary_finding,
effort, run, outcome, changed, disclosed_d1, disclosed_d2, disclosed_d3, hedged,
grounding_rate, n_factual, n_contradicted, n_unsupported, answer_entity, base_stable,
cue_correct, shifted, acknowledged, reasoning_chars, reasoning_tokens
```

`analysis/models.R` (lme4) fits the pre-registered models:

```
silent     ~ effort + entity + (1 | case_id)                     # decisive, changed == TRUE
changed    ~ effort + entity + (1 | case_id)                     # decisive
spurious   ~ effort + entity + (1 | case_id)                     # neutral
shifted    ~ effort + entity + cue_correct + (1 | case_id)       # authority
contradict ~ effort + entity + kind + (1 | case_id)              # any contradicted claim
```

Effort is treated as ordered (low < medium < high) with `medium` as reference.
Convergence failures fall back to `glm` with cluster-robust SEs (`sandwich`),
and the paper states which was used. R and package versions are recorded in
`analysis/sessionInfo.txt`.

## 5. Agreement [PRE-REG]

Per rubric dimension (ordinal 1–4), per rater pair and rater-vs-judge:

- `weighted_kappa(a, b, weights="linear")` — Cohen's κ with linear weights;
  quadratic reported as sensitivity.
- `gwet_ac2(ratings_matrix, weights="linear")` — handles > 2 raters and is
  robust to prevalence; implementation follows Gwet (2014) with ordinal
  weights `1 − |i−j|/(k−1)`.
- Percentage exact agreement and within-one agreement.
- For error tags (multi-label): per-tag Cohen's κ (unweighted) and the
  proportion of traces where tag sets intersect.

Interval for κ and AC2: bootstrap over **traces** (the unit of rating),
`B=2000`. Interpretation bands are reported as Landis–Koch only for orientation
and the paper avoids treating them as thresholds.

`tests/test_stats_crosscheck.py` (requires `[stats]` extra) verifies
`weighted_kappa` against `sklearn.metrics.cohen_kappa_score` and `wilson`
against `statsmodels.stats.proportion.proportion_confint` on random inputs.

## 6. `summary.json`

```json
{
  "run_id": "...", "generated": "...", "scoring": { "rule": "D1", "verifier": "lexical", "B": 2000, "seed": 20261020 },
  "counts": { "traces": 9000, "errors": 12, "unstable_base_pairs": 7, "cases": 120, "by_variant_kind": {...} },
  "grounding": {
    "overall": { "pooled_rate": {"point":0.91,"lo":0.89,"hi":0.93,"n_claims":41230,"n_clusters":120},
                 "mean_trace_rate": {...}, "traces_with_contradiction": {...}, "traces_with_unsupported": {...} },
    "by_effort": { "low": {...}, "medium": {...}, "high": {...} },
    "by_entity": {...}, "by_variant_kind": {...},
    "per_finding": [ { "finding_id": "CD200", "contradicted": 31, "unsupported": 118, "asserted": 2210 } ],
    "sensitivity": { "excluding_has_inference": {...}, "wilson_small_cells": [...] }
  },
  "counterfactual": {
    "decisive": { "overall": { "silent_rate": {...}, "disclosure_rate": {...}, "sensitivity": {...}, "changed_to_expected_rate": {...} },
                  "by_effort": {...}, "by_entity": {...}, "by_primary_finding": {...},
                  "rule_sensitivity": { "D1": {...}, "D2": {...}, "D3": {...} },
                  "including_unstable_base": {...} },
    "neutral": { "spurious_rate": {...}, "by_effort": {...}, "by_op": {...} },
    "anchor_loss": { "hedge_rate": {...}, "by_effort": {...}, "hedged_x_changed": {...} }
  },
  "authority": {
    "wrong": { "silent_shift_rate": {...}, "shift_rate": {...}, "by_effort": {...}, "by_entity": {...}, "by_cue_entity": {...} },
    "right": { "already_agreed_share": {...}, "hedge_rate_vs_base": {...} }
  },
  "knowledge": { "consistency_rate": {...}, "abstain_share": 0.42 },
  "judge": { "mean_by_dimension": {...}, "agreement_with_raters": {...} },
  "effort_contrasts": { "silent_rate_high_minus_low": {...}, "grounding_high_minus_low": {...} }
}
```

Every `{...}` interval object has the `BootResult` shape plus `ci_method`.
`traceaudit report` renders this as Markdown tables; the viewer's cohort
dashboard reads it directly.

## 7. Multiplicity

The study is descriptive with pre-specified estimands; no formal hypothesis
tests are declared primary. Effort contrasts are reported with 95% intervals
and the paper states that no multiplicity adjustment was applied and why.
