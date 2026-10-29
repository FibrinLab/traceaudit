# 08 — Experiment orchestration, manifest and CLI

Status: draft v0.1 · Modules: `traceaudit.experiment`, `traceaudit.cli`

## 1. Run plan

`plan(cases, perturbations, efforts, runs_per_variant, filters) -> list[Job]`
where `Job = (case_id, variant, effort, run, rendered_input, truth_after)`.

- Includes `base` for every approved case and every approved perturbation
  whose case is approved.
- Filters: `--cases CLL-001,CLL-002`, `--entities CLL_SLL,MCL`, `--variants
  base,dec-*,auth-*` (glob), `--efforts medium`, `--runs 2`. Filters are
  recorded in the manifest.
- **Ordering [PRE-REG]:** jobs are shuffled with `random.Random(master_seed)`
  so that cases, variants and efforts interleave over wall-clock time. This
  prevents server drift (thermal throttling, model reload, a mid-run server
  update) from aligning with one condition. Resumed runs continue the same
  permutation.
- Per-trace seed: `zlib.crc32(f"{master_seed}:{trace_key}".encode()) & 0x7fffffff`.

## 2. Execution — `run_experiment(plan, client, out_dir, workers=1)`

- Writes `manifest.json` first (status `running`), then appends to
  `traces.jsonl` as jobs complete, flushing after every record. A crash loses
  at most the in-flight job.
- **Resume:** on start, existing `trace_key`s in `traces.jsonl` are skipped
  unless `--redo-errors` (re-run only records with `meta.error`) or `--force`.
- **Concurrency:** `workers` threads with a shared `queue`; the server is the
  bottleneck, so the default is 1 and the manifest records the value (parallel
  requests can change batching and thus sampling on some servers).
- **Rate limiting:** `--min-interval-ms` between requests, default 0.
- **Health check:** before the first job and after every 100 jobs, `describe()`
  is re-called; a changed model digest or server version aborts the run with
  exit code 3 and `manifest.status = "aborted:model_changed"`.
- Progress: one line per job to stderr (`[1234/9000] CLL-017|dec-cyclin_d1|high|2  ok 18.4s  reasoning=4.1k`) and a `progress.json` with counts, ETA, error count.
- On completion `manifest.status = "complete"`, with `finished`, `n_traces`,
  `n_errors`, `wall_clock_s`.

## 3. Scoring pipeline — `traceaudit score <run_dir>`

Runs in order, each idempotent and each appending to `manifest.scoring[]`:

1. `segment` + `ground` → `claims.jsonl`, `grounding.jsonl`
2. `probes.score_run` → `counterfactual.jsonl`, `authority.jsonl`
3. `judge` (optional, `--judge`) → `judge.jsonl`
4. `stats.summarise` → `summary.json`

`--rule D1|D2|D3` selects the disclosure rule (default D1; the summary always
includes all three). `--verify lexical|retrieval|llm|none` selects the knowledge
verifier (default `lexical`).

## 4. Manifest completeness check

`traceaudit manifest check <run_dir>` fails if any of: git dirty at run time
(`--allow-dirty` records a justification string), lexicon sha mismatch with the
packaged lexicon of the recorded version, prompt sha mismatch, model digest
absent, `status != complete`, or `n_errors / n_traces > 0.02`.

## 4a. Provenance hashes (29 Oct 2026)

Hashes prove identity, not faithfulness: they show which prompt produced which trace and which
inputs a run committed to, and say nothing about whether the reasoning matches the report (that
is the probes' job, spec 06 and spec 19). Module `traceaudit.provenance`.

- Every trace record carries `provenance`: `prompt_sha256 = sha256(system + "\x00" + user)` of
  the exact strings sent to the client, `reasoning_sha256` and `answer_sha256` of the raw fields
  as stored. An error trace keeps `prompt_sha256` only. A path-B import (spec 19) records
  `reasoning_sha256`, `answer_sha256`, `artefact_sha256` of the source file and the fact-table
  `fingerprint`; its `prompt_sha256` is `null` because traceaudit did not send the prompt.
- The manifest carries `provenance.components` (the sha256 of prompt, cases, perturbations and
  lexicon, `null` when absent) and `provenance.inputs_sha256 = sha256("\n".join(name=sha256|none))`
  over those four in that order. [PRE-REG] `inputs_sha256` is the value to publish in the
  pre-registration before any model is called; it fixes the variant set.
- `traceaudit manifest verify <run_dir> [--cases F --perturbations F]` recomputes everything:
  the prompt text stored in the manifest against `prompt.sha256`, the components against
  `inputs_sha256`, the input files against their recorded hashes when they still exist at the
  recorded paths, and each trace's reasoning and answer hashes. With `--cases` (and
  `--perturbations`; `ablations.jsonl` in the run is added automatically) the variants are
  re-rendered with the manifest's render settings and each prompt hash is rebuilt, which is the
  check that no variant text reached the model; without them prompts count as *unverified*, not
  failed. Exit 1 on any mismatch or on a run that predates these fields.

## 5. CLI

```
traceaudit validate   <cases.jsonl> [--perturbations p.jsonl]        # invariants C1, C2, P1
traceaudit perturb    <cases.jsonl> -o <perturbations.jsonl> --seed N [--merge-review]
traceaudit run        --client ollama|openai|sim --model TAG --endpoint URL
                      --cases cases.jsonl --perturbations p.jsonl --out runs/<run_id>
                      [--efforts low,medium,high] [--runs 5] [--seed N] [filters…]
                      [--prompt enable-v3] [--workers 1] [--allow-unreviewed] [--allow-dirty "why"]
traceaudit score      <run_dir> [--rule D1] [--verify lexical] [--judge --judge-client … --judge-model …]
traceaudit ground     <run_dir>                                      # steps 1 only
traceaudit report     <run_dir> [--format md|json]                   # human-readable summary
traceaudit export     <run_dir> -o <dir> [--shard] [--include-raw] [--ratings ratings/…]
traceaudit demo       [--out runs/demo]                              # SimulatedModel end-to-end on the packaged 6-case sample
traceaudit validate-probes [--grid default|quick]                    # spec 10
traceaudit manifest   check|show|verify <run_dir> [--cases F --perturbations F]
traceaudit recall     <labelled_claims.jsonl> <run_dir>              # spec 03 §5
```

Exit codes: 0 ok · 1 validation/scoring error · 2 usage · 3 aborted (model
changed) · 4 client unreachable. All commands accept `--log-level` and write
structured logs (`jsonl`) to `<out>/logs/` when `--log-file` is given.

## 6. Package layout

```
traceaudit/
  __init__.py          __version__
  schema.py  lexicon.py  lexicon.json  extract.py  segment.py  grounding.py
  perturb.py  probes.py  clients/{__init__,base,ollama,openai_compat,callable_,harmony}.py
  experiment.py  stats.py  simulate.py  judge.py  export.py  cli.py
  prompts/enable-v3.json  prompts/judge-v1.json
  data/sample_cases.jsonl  data/sample_perturbations.jsonl        # 6 cases, 1 per entity, for demo/tests
  tools/extractor_recall.py
tests/                                                              # spec 16
viewer/                                                             # spec 13
analysis/models.R
pyproject.toml       # zero runtime deps; extras: stats (numpy, scipy, scikit-learn, statsmodels: cross-check tests only), dev (pytest, coverage, ruff, mypy)
```

Python ≥ 3.10. `pyproject.toml` declares **zero** runtime dependencies. The
`[stats]` extra is used only by `tests/test_stats_crosscheck.py` to verify the
stdlib implementations against SciPy; the `[judge]` extra is reserved for a
non-stdlib judge client if one becomes necessary (none is planned).
