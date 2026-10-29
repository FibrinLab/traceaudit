# 18 — Fact ledger

Status: draft v0.1 · Modules: `traceaudit.ledger`, `traceaudit.importers`

The fact ledger is the structured core of trace analytics. It replaces "sentences
graded against documents" with "citations graded against facts" wherever the
pipeline under audit already emits facts with ids. The text path (spec 03–04)
remains as the adapter that turns free-text documents into facts.

## 1. Records

| Record | Fields |
|---|---|
| `Fact` | `id` (`p_12`, `c_104`, `w_65`), `source` (`patient` \| `context` \| `who`), `section` (modality or, for reference facts, the candidate they describe), `field`, `value`, `evidence`, `candidate` |
| `Segment` / `Section` / `Report` | the delivered report: sections of segments, each segment `text` + `citation_ids`; plus `decision`, `delivered_decision`, `contract_valid`, `failure_kind`, `dropped_segments` |
| `Rationale` | `decision`, `confidence`, `key_findings[{description, ids, modality}]`, `differential[{diagnosis, verdict, supporting, contradicting, rationale, criteria[{criterion, status, ids}]}]`, `discriminators[{text, ids}]`, `unresolved[]`, `would_change[]` |
| `Ablation` | `removed_ids`, `decision_before`, `decision_after`, `changed` |
| `LedgerCase` | `case_id`, `truth`, `candidates[]`, `facts[]`, `allowed_ids` |
| `LedgerTrace` | `thinking`, `report`, `rationale?`, `ablation?` |

Value polarity: `Positive/Present/Weak/Detected…` → `pos`; `Negative/Absent/Not detected…` → `neg`;
`Not performed/Not mentioned…` → `untested`; anything else (numbers, `unmutated`) → `other`,
graded by literal match of the value next to the field name. A fact is *informative* when it is
a patient or context fact and not untested.

## 2. Checks (all pure functions of the ledger)

| id | Question |
|---|---|
| `citations_exist` | every cited id exists among the allowed ids |
| `citations_agree` | the sentence citing a fact states the value the fact has (field found by alias, polarity by the extractor's cue grammar; categorical values by literal match) |
| `segments_cited` | every informative segment carries a citation |
| `report_contract`, `nothing_dropped`, `summary_structure` | engine contract fields when the artefact carries them |
| `decision_matches_truth`, `decision_survived` | the delivered answer vs truth, and vs the raw answer |
| `thinking_present`, `thinking_considers_alternatives`, `thinking_ids_valid`, `thinking_agrees` | the reasoning exists, names more than one candidate, cites only allowed ids, and restates facts with their recorded values |
| `rationale_agrees`, `rationale_matches_truth`, `one_favoured`, `differential_complete`, `rationale_ids_valid` | rationale structure |
| `contradicting_evidence_informative` | "contradicting" citations point at informative facts, not at untested ones |
| `criteria_cited`, `favoured_criteria_met` | the favoured answer cites the reference essential criteria and none is marked not met |
| `coverage`, `coverage_informative` | facts never referenced in thinking (by id or field name), report or rationale; informative ones separately |
| `discriminators_load_bearing`, `discriminators_in_summary` | ablation changed the answer; stated discriminators overlap the summary's citations |

Per segment the result records each citation's grade (`agree`, `disagree`,
`unverifiable`, `not_mentioned`, `not_found`, `reference`) and any assertion in the
text that cites no fact (`uncited_assertions`). Per fact it records whether it was
referenced in thinking, cited in the report, cited in the rationale, or ignored.

## 3. Importers

`importers.enable_md.parse_markdown(text)` reads the ENABLE-AI per-case artefact
(fact tables by modality, WHO blocks by candidate, the arm A thinking fence, the
report JSON fence, the arm B rationale tables, the arm C ablation table). Missing
parts are tolerated; fewer checks run. `serve.ledger_from_json` accepts the same
structures as plain JSON for pipelines that can emit them directly.

## 4. Surfaces

- CLI: `traceaudit ledger audit <artefact.md> [--json]` prints the checks and metrics; given directories or globs
  (or `--summary`) it prints pass rates per check and grade counts across artefacts (`ledger.audit_many`), and
  `--review-sheet out.csv` writes one row per citation grade and uncited assertion (`ledger.review_rows`) with empty
  `human_grade`/`note` columns for a reviewer to fill.
- Service: `POST /api/ledger` with `{markdown}` or `{case, trace}` returns the full result.
- Viewer: `#/analyse/ledger` renders the verdict, the report with graded citation
  chips, the ledger table with coverage marks, the reasoning with clickable ids,
  the rationale differential and the ablation.

## 5. Relationship to the probes

Counterfactual, neutral and authority probes operate on facts here: a decisive
edit flips a fact's value and re-renders the fact table for the model; the base
reference and disclosure rules (spec 06) are unchanged, with "cites the primary
finding" meaning "cites the edited fact's id or states its new value". The
ablation arm is the load-bearing probe already present in the ENABLE pipeline.
