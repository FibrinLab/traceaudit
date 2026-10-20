# 12 — Export bundle

Status: draft v0.1 · Module: `traceaudit.export`

`traceaudit export <run_dir> -o <dir>` produces the JSON the viewer loads. The
bundle is the **only** contract between the package and the viewer; the viewer
never reads `runs/` files directly.

## 1. Layout

```
<dir>/
  index.json                 # manifest, counts, case list, summary, lexicon subset
  cases/<case_id>.json       # one file per case: base + variants, traces, claims, scores
  ratings-schema.json        # the rating record schema the viewer must emit
  figures/                   # (viewer writes here when run locally; empty on export)
```

Un-sharded mode (`--single`) writes everything into one `bundle.json` with the
same objects under `index` and `cases{}`; it is for small demos only (≤ 20 cases).
The viewer accepts both.

## 2. `index.json`

```json
{
  "bundle_version": 1,
  "run": { "run_id": "...", "manifest": { "...": "spec 01 §2.6, minus prompt text when --redact-prompt" } },
  "lexicon": { "version": "1.3.0", "entities": [ {"id","display","in_scope"} ], "findings": [ {"id","display","kind"} ] },
  "rubric": { "dimensions": [ {"id":"D1","name":"Problem representation","anchors":["…","…","…","…"]} ], "error_tags": [ {"id","label","definition"} ] },
  "cases": [ { "case_id": "CLL-017", "entity": "CLL_SLL", "subtype": null, "flags": {...}, "variants": ["base","dec-cyclin_d1","neu-1","auth-wrong-mcl"], "n_traces": 60, "file": "cases/CLL-017.json" } ],
  "summary": { "…": "summary.json verbatim" },
  "study": { "study_id": "pilot-1", "rating_set": ["CLL-017|base|medium|2", "..."], "blinding_seed": 7731 }
}
```

`study.rating_set` is the list of `trace_key`s selected for the rating study
(spec 15 §4); the viewer's rating mode serves only these.

## 3. `cases/<case_id>.json`

```json
{
  "case": { "case_id", "entity", "subtype", "flags", "reports": {...}, "truth": {...}, "finding_spans": { "CD5": [ {"report":"flow_cytometry","start":118,"end":122,"polarity":"pos"} ] } },
  "variants": {
    "base": { "variant": "base", "kind": "base", "reports": {...}, "truth_after": {...}, "perturbation": null, "diff": [] },
    "dec-cyclin_d1": { "variant", "kind": "decisive", "reports": {...}, "truth_after": {...},
                       "perturbation": { "primary_finding","edits":[...],"linked_findings":[...],"expected_entity","cue":null,"rationale" },
                       "diff": [ { "report":"flow_cytometry", "base_span":[312,332], "variant_span":[312,332], "before":"cyclin D1 negative", "after":"cyclin D1 positive", "finding_id":"cyclin_D1" } ] }
  },
  "traces": [
    { "trace_key", "variant", "effort", "run", "reasoning", "answer", "retrieved": [...], "meta": { "latency_ms","usage","finish_reason","error" },
      "claims": [ { "claim_id","paragraph_id","start","end","text","type","flags","assertions":[...],"label","evidence":[...],"knowledge_check" } ],
      "grounding": { "…grounding.jsonl record…" },
      "counterfactual": { "…or null…" },
      "authority": { "…or null…" },
      "judge": { "…or null…" },
      "map": { "…spec 13 §8 precomputed graph…" } }
  ],
  "base_reference": { "low": {"base_modal_entity","base_mode_share","base_stable","base_n"}, "medium": {...}, "high": {...} }
}
```

- `raw` is omitted unless `--include-raw`.
- `diff` is computed by the exporter from the recorded rewrite spans so the
  viewer never diffs text itself.
- `map` is the reasoning-map graph (nodes/edges) precomputed in Python so the
  viewer and the paper figures use identical structure.
- Reasoning text is stored once per trace; claims reference it by offsets.

## 4. Size budget

120 cases × ~75 traces × ~4 KB reasoning ≈ 36 MB of text plus claims. Sharding
keeps each case file ≈ 300–600 KB so the viewer loads one case at a time.
`index.json` MUST stay under 2 MB; the exporter fails if it does not.

## 5. Ratings — `ratings-schema.json`

Record emitted by the viewer (one per trace × rater × dimension, plus one
`error_tags` record):

```json
{ "schema_version": 1, "study_id": "pilot-1", "rater_id": "R01", "session_id": "uuid",
  "trace_key": "CLL-017|base|medium|2", "presentation_index": 14,
  "dimension": "D3", "score": 2,
  "error_tags": null, "comment": null,
  "started_at": "2026-12-01T10:02:11Z", "submitted_at": "2026-12-01T10:06:40Z", "duration_ms": 269000,
  "blinded": true, "viewer_version": "0.1.3", "bundle_run_id": "..." }
```

The `error_tags` record uses `dimension: "tags"`, `score: null`,
`error_tags: [...]`, `comment: "free text"`. `traceaudit import-ratings
<file.jsonl> ratings/<study_id>/` validates and de-duplicates (latest
`submitted_at` per `trace_key, rater_id, dimension` wins) and refuses records
with `blinded: false` unless `--allow-unblinded`.

## 6. Figures manifest

The viewer writes `figures/<name>.svg` and `figures/<name>.json` (the data
behind the figure). `traceaudit export --figures-check <dir>` verifies that each
figure's JSON matches `summary.json` so the paper's figures are traceable to the
run.
