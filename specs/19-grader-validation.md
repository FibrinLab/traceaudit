# 19 — Grader validation

Status: draft v0.1 · Modules: `traceaudit.tools.ledger_labels`, `traceaudit.stats` · CLI: `traceaudit ledger sample`, `traceaudit ledger agreement`

The fact-ledger grader (spec 18 §2, `ledger.grade_segment`) decides by rule whether a
sentence that cites a fact states the value the fact has. Every grade it produces is
reported without a measured error. This spec defines how that error is measured:
two people label a sample of citations blind to the grader, their agreement with each
other bounds what can be expected of any grader, and the grader is compared with their
consensus.

## 1. Unit of labelling

One **item** is one (case, sentence, fact) triple: a sentence of the delivered report
or of the rationale (key findings, differential entries, discriminators; not the
criteria rows, which state what a candidate would require rather than what the
patient has) together with one fact it cites, or one fact the grader matched to an
assertion in the sentence that cites nothing (`kind = uncited`). Items whose grader
grade is `reference` (the cited fact is a reference criterion) or `not_found` (the id
does not exist) are mechanical and are not labelled.

The question asked of every item is the grader's question: *does this sentence state
the cited fact with its recorded value?* The answer set is

| Human grade | Meaning |
|---|---|
| `agree` | the sentence states the fact with the recorded value (by meaning: synonyms and clinical equivalents count; a number must appear; for a fact recorded as not performed / not mentioned, the sentence says it was not assessed or not available) |
| `disagree` | the sentence states a different value (opposite polarity, another category or number, or present/absent for a fact that was not tested) |
| `unverifiable` | the sentence refers to the fact but what value it claims cannot be told from it |
| `not_mentioned` | the sentence does not refer to the fact at all (a dangling citation) |

`item_id` is a stable hash of (case_id, section, sentence, fact_id), so a label can be
joined back to the audit regardless of file order.

## 2. Sample [PRE-REG]

1. `items_from_audit` lists every gradable item of every audited artefact.
2. `sample(items, n = 300, seed)` draws round-robin over the strata grade × source
   (report | rationale) so that rare grades (`disagree` above all) are
   over-represented relative to their frequency, with at most `per_case` items from
   any one case (default twice the even share, at least 5) so no case dominates.
   The draw is deterministic for the seed whatever the input order.
3. The grader's grade and the grader's extracted polarity (`stated`) are written to
   `grader.jsonl` only. Each rater's file carries the same items in a different seeded
   order with `human_grade` and `note` empty. Raters MUST NOT see `grader.jsonl` or
   each other's files before both have finished.

Target: 300 items; with the fixture alone the pool is 57, so the sample for the paper
comes from the pilot run's artefacts.

## 3. Raters and adjudication

- Two raters (the owner, `R01`, and one colleague, `R02`), independent, each labelling
  from `docs/labelling-guide.md` and nothing else. `note` is free text for the item.
- After both files are complete, items with different labels are listed
  (`n_disagreements_between_raters`) and the two raters settle each one together;
  the agreed label goes to `adjudicated.jsonl` as `{item_id, human_grade}`.
- Consensus per item: the raters' label where they agree; otherwise the adjudicated
  label; otherwise (three or more raters) a strict majority; otherwise unresolved and
  excluded from the grader comparison. Unlabelled items are counted (`n_unlabelled`)
  and excluded.

## 4. Statistics

All from `traceaudit.stats`, standard library only; cross-checked against
scikit-learn in `tests/test_stats_crosscheck.py`.

| Quantity | Estimator |
|---|---|
| Inter-rater agreement | Cohen's κ (unweighted, nominal) per pair, exact agreement, Gwet's AC1 over all raters (robust to the dominance of `agree`) |
| Grader vs consensus | Cohen's κ, exact agreement, precision and recall per grade, 4×4 confusion matrix (rows consensus, columns grader) |
| Grader vs each rater | Cohen's κ, exact agreement (point estimates) |
| Confidence intervals | percentile bootstrap resampling cases (`cluster_bootstrap` on `case_id`, B = 2000); item-level resampling when fewer than five cases |

## 5. Acceptance rule [PRE-REG]

Following spec 11 §5: the grader is reported as an acceptable stand-in for human
labelling when its κ with the rater consensus is not lower than the inter-rater κ
(mean of the pairwise values) minus 0.1. The report states both values, the
threshold and the verdict (`acceptance.accepted`); the per-grade recall says which
grades fail when it does not pass, and `disagree` recall is reported in the paper
whatever the verdict, because it is the grade the `citations_agree` check turns on.

## 6. Reporting

`traceaudit ledger agreement labels/` prints the report as JSON (stdout) and a short
summary (stderr). The paper reports: n items, n cases, n unlabelled, inter-rater κ and
AC1 with CIs, n disagreements and how they were resolved, grader κ with CI, per-grade
precision and recall, the confusion matrix, and the acceptance verdict. The label set
directory (`grader.jsonl`, rater files, `adjudicated.jsonl`, `manifest.json` with the
seed, the source artefacts and the stratum counts) is archived with the run.

## 7. Commands

```
traceaudit ledger sample <artefact.md | dir> --n 300 --raters R01,R02 --seed 20261029 --out labels/
traceaudit ledger agreement labels/ [--adjudicated labels/adjudicated.jsonl] [--B 2000]
```

## 8. Limitations

- The grader's `unverifiable` and `not_mentioned` grades both come from the extractor
  failing to find a cue; raters decide by meaning. Confusion between those two grades
  is expected and is less serious than `agree` ↔ `disagree` confusion.
- The sample is stratified by the grader's own grades, so the per-grade precision is
  estimated on a grader-chosen subset; recall per grade is estimated from the
  consensus within that sample, not from the population of citations.
- The rater files are JSONL edited by hand; `human_grade` values outside the four
  grades are counted as invalid and excluded, never silently mapped.
