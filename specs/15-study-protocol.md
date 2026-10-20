# 15 — Study protocol (synthetic phase)

Status: draft v0.1 · Companion to the OSF pre-registration

## 1. Design summary

Descriptive audit of gpt-oss-120b reasoning traces on 120 synthetic mature
B-cell neoplasm cases, under base and perturbed inputs, at three reasoning
efforts, with clinician rating of a 100-trace subset. No patient data. No
hypothesis tests declared primary; pre-specified estimands with 95% intervals.

## 2. Model runs

| Item | Value |
|---|---|
| Model | gpt-oss-120b, served locally (Ollama or vLLM), digest recorded |
| Pipeline | ENABLE-AI prompt and retrieval where available; otherwise `enable-v3` prompt without retrieval. Which one is used is fixed before registration |
| Efforts | low, medium, high |
| Runs per (case, variant, effort) | 5 |
| Variants | base; 1–2 decisive; 1 neutral; 0–1 anchor-loss; 1 wrong-cue; right-cue on a 50% case subsample |
| Expected calls | 120 × ≈5 × 3 × 5 ≈ 9,000 |
| Sampling | temperature 1.0, top_p 1.0, seeded per trace |
| Ordering | seeded interleaving (spec 08 §1) |
| Stopping | all jobs complete; error rate ≤ 2% else re-run errors |

## 3. Pilot (before registration)

- 12 cases (2 per entity) × all variants × 3 efforts × 3 runs ≈ 650 calls.
- Purposes: (a) extractor recall labelling sample (300 factual claims, two
  clinicians); (b) hedge-detector validation (100 answers); (c) check that
  base answers are stable (expect ≥ 80% of case–effort pairs stable);
  (d) confirm prompt/answer format compliance ≥ 95%; (e) estimate reasoning
  length per effort to set `max_tokens`.
- Pilot traces are **not** reused in the main analysis.

## 4. Clinician rating study

| Item | Value |
|---|---|
| Raters | 2–3 consultant or senior-trainee haematologists / haematopathologists, not involved in writing the cases they rate |
| Traces | 100, stratified: 6 entities × {base, decisive, anchor-loss, wrong-cue} × 3 efforts, filled by seeded sampling to 100 with roughly equal cells; every rater rates all 100 |
| Blinding | rating mode hides grounding labels, probe outcomes, judge scores, variant kind, effort, and the model name; traces presented in a per-rater seeded random order; the rater sees the reports exactly as the model did (including any cue) |
| Instrument | spec 11 §1 rubric (7 × 1–4) and error tags, one free-text comment |
| Training | 5 practice traces with group discussion; practice ratings discarded |
| Time | ~6–8 min per trace; sessions of ≤ 20 traces |
| Output | `ratings/<study_id>/<rater_id>.jsonl` exported from the viewer |
| Analysis | spec 09 §5; judge calibration spec 11 §5 |

## 5. Extractor recall sample

300 factual claims sampled from the pilot (stratified by effort and entity),
labelled independently by two clinicians for gold assertions (finding,
polarity). Disagreements resolved by discussion. Reported: assertion-level
precision/recall per finding kind, and the effect on grounding rate of
replacing extractor labels with gold labels on this sample.

## 6. Pre-registration contents (OSF)

1. Research questions and estimands (spec 09 §1), with the headline per RQ.
2. Definitions: claim typing (spec 04 §1.2), grounding labels (spec 04 §3),
   hedging (spec 04 §2), base reference and stability (spec 06 §1), disclosure
   rules D1–D3 and outcomes (spec 06 §2–3), acknowledgement (spec 06 §3.1).
3. Lexicon version and sha256; discriminator, linked and confusion tables.
4. Perturbation catalogue (spec 05 §2, §4, §5) as approved.
5. Case set sha256 (approved cases and perturbations), frozen before any
   real-model trace is scored.
6. Sampling, ordering and seeds (spec 08).
7. Statistical plan (spec 09), including sensitivity analyses and the
   mixed-effects specification.
8. Rating study plan (§4), rubric anchors, judge model and decision rule.
9. Probe validation results (spec 10) attached as a supplement.
10. Exclusion rules: error traces; unstable bases; `target_equals_base`
    perturbations; unparseable judge outputs.
11. What is exploratory: knowledge consistency, trace–answer agreement,
    per-finding breakdowns, reasoning-length correlations.

Timing: registration after the pilot and before `traceaudit score` is run on
any main-run trace. The main run **may** be collected before registration (the
traces are raw), but `score` on the main run is executed only after the DOI is
issued, and the manifest `scoring[0].timestamp` proves the order.

## 7. Deviations

Any post-registration change to a [PRE-REG] item goes in
`docs/deviations.md` and in the paper. Allowed without deviation: alias and
phrase-list extensions (spec 02 §8), bug fixes that do not change definitions
(each documented with before/after summary deltas).

## 8. Governance

- Synthetic data only; no ethics approval required for this phase; confirm in
  writing with the sponsor's R&D office before week 1.
- Authorship and sponsor sign-off agreed with the CI (project spec §8, week 0–1).
- Rater ids are pseudonymous; the key is held by the study lead.
- Code Apache-2.0; cases CC BY 4.0; traces released with the paper (they
  contain no personal data).

## 9. v2 pointer

Real-data phase (BRIDgE TRE) reuses the same package unchanged: cases become
retrospective reports with truth derived from the MDT diagnosis and the
extractor; perturbations are applied inside the TRE; only aggregate outputs
leave. Requires protocol amendment and a lexicon recall re-check on real report
language.
