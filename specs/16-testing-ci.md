# 16 — Testing and CI

Status: draft v0.1

## 1. Test layout

```
tests/
  conftest.py                       # fixtures: lexicon, sample cases, SimulatedModel, tmp run dir
  test_schema.py                    # round-trip, validation codes, trace_key parsing
  test_lexicon.py                   # alias uniqueness, table completeness, disambiguation
  test_extract.py                   # grammar table-driven cases (spec 03 §3), conflicts, spans
  test_extract_reports.py           # C1 on every case in data/cases.jsonl and data/sample_cases.jsonl
  test_segment.py                   # splitting, typing rules in order, arrows, abbreviations
  test_answer_parse.py              # diagnosis line, hedging rules (a)(b)(c)
  test_grounding.py                 # one test per label incl. precedence and variant-relative oracle
  test_perturb.py                   # apply() per surface form; P1 on every perturbation; neutral guards
  test_probes.py                    # one test per outcome category (spec 06), D1/D2/D3, edge cases table
  test_harmony.py                   # channel parsing, structured fields, summary-only rejection
  test_experiment.py                # plan ordering determinism, resume, error traces, health-check abort
  test_stats.py                     # wilson, bootstrap reproducibility, kappa/AC2 against hand-computed values
  test_stats_crosscheck.py          # [stats] extra; skipped if absent
  test_simulate.py                  # faults produce the intended labels one at a time
  test_probe_validation.py          # --grid quick passes criteria (spec 10 §2)
  test_judge.py                     # output parsing, retry, blinding (no truth in prompt)
  test_export.py                    # bundle schema, size budget, diff spans, ratings import
  test_cli.py                       # smoke: demo end-to-end in tmp dir
  golden/                           # frozen inputs/outputs for regression (claims and scores of the 6 sample cases)
```

## 2. Invariants enforced in CI

| Gate | Test | Fails build when |
|---|---|---|
| C1 truth consistency | `test_extract_reports` | any case's `findings(render()) != truth` |
| C2 no polarity conflict | same | any report-level conflict |
| P1 perturbation consistency | `test_perturb` | any approved perturbation's `truth_after` mismatch or off-span diff |
| Grammar table | `test_extract` | any row of spec 03 §3 fails |
| Outcome coverage | `test_probes` | any outcome in spec 06 lacks a passing test |
| Probe recovery | `test_probe_validation` (quick grid) | criteria in spec 10 §2 fail |
| Determinism | `test_cli` runs `demo` twice | `claims.jsonl`, `grounding.jsonl`, `summary.json` differ |
| Golden | `test_golden` | scores for sample cases change without `--update-golden` |
| Zero runtime deps | `scripts/check_deps.py` | any non-stdlib import outside `tests/`, `tools/`, extras-guarded blocks |
| Schema version | `test_schema` | a record type changes without a `schema_version` bump and migration note |
| Lexicon sanity | `test_lexicon` | duplicate alias; finding in table but not in findings; entity without aliases |

## 3. Viewer tests

- `vitest` unit tests: bundle loading, blinding order (seeded, stable),
  rating persistence and export, claim→span highlighting, map layout
  determinism.
- Playwright smoke: load the demo bundle, open each view, submit one rating,
  export, verify JSONL against `ratings-schema.json`.
- Accessibility: `axe-core` on each view, zero serious/critical violations;
  keyboard-only walkthrough script.

## 4. CI matrix and gates

- GitHub Actions: Python 3.10–3.13 on ubuntu-latest; macOS on 3.12 only.
  `pip install -e .[dev]`, `ruff check`, `mypy traceaudit`, `pytest -q`.
- Nightly: `traceaudit validate-probes --grid default`; uploads `validation.md`.
- Viewer: Node 20, `npm ci`, `npm run lint`, `npm test`, `npm run build`,
  Playwright smoke against the built static site.
- Release gate (tag `v*`): all above green, `CHANGELOG.md` entry, `traceaudit
  manifest check` on the packaged demo run, version in `pyproject.toml` equals
  the tag.

## 5. Coverage and performance

- Line coverage ≥ 90% on `extract`, `segment`, `grounding`, `probes`, `stats`;
  ≥ 80% overall. Measured with `coverage.py` in the dev extra.
- Benchmark test: scoring 1,000 synthetic traces of 5 KB completes in < 60 s on
  the CI runner (soft gate: warning, not failure).
