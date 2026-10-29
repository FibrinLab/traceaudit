# 18 — Fact ledger

Status: draft v0.1 · Modules: `traceaudit.ledger`, `traceaudit.importers`

The fact ledger is the structured core of trace analytics. It replaces "sentences
graded against documents" with "citations graded against facts" wherever the
pipeline under audit already emits facts with ids. The text path (spec 03–04)
is an adapter onto it (`traceaudit.ledger_adapters`), so free text and
structured artefacts share one set of checks, one result shape and one viewer.

## 1. Records

| Record | Fields |
|---|---|
| `Fact` | `id` (`p_12`, `c_104`, `w_65`), `source` (`patient` \| `context` \| `who`), `section` (modality or, for reference facts, the candidate they describe), `field`, `value`, `evidence`, `candidate` |
| `Segment` / `Section` / `Report` | the delivered report: sections of segments, each segment `text` + `citation_ids`; plus `decision`, `delivered_decision`, `contract_valid`, `failure_kind`, `dropped_segments` |
| `Rationale` | `decision`, `confidence`, `key_findings[{description, ids, modality}]`, `differential[{diagnosis, verdict, supporting, contradicting, rationale, criteria[{criterion, status, ids}]}]`, `discriminators[{text, ids}]`, `unresolved[]`, `would_change[]` |
| `Ablation` | `removed_ids`, `decision_before`, `decision_after`, `changed` |
| `LedgerCase` | `case_id`, `truth`, `candidates[]`, `facts[]`, `allowed_ids` |
| `LedgerTrace` | `thinking`, `report`, `rationale?`, `ablation?` |

**The text path as an adapter.** `ledger_adapters.case_to_ledger(case, lx)` makes
one patient fact per polarised assertion the extractor finds in the documents
(`extract.finding_spans`): ids `p_1..` in document order, `section` the document
id, `field` the lexicon finding id, `value` the lexicon's polarity word
(`Positive`/`Negative`), `evidence` the asserted text, with `meta["spans"]`
holding `{report, start, end}` offsets so a viewer can highlight it. An authority
cue appended to a document (schema `Cue`, rendered from the lexicon's
`cue_templates`) becomes a context fact `c_1` with field
`referrer_working_diagnosis`. Candidates are the lexicon's answer entities and
`truth` the case's entity. `meta["lexicon_fields"]` tells `audit` that the fields
are the lexicon's own finding ids, so it grades with that lexicon (its aliases,
phrases, numeric rules and entity names) rather than a throwaway one built from
the field names. `trace_to_ledger(trace, claims, lx, case_ledger)` makes the
reasoning the thinking and the report one section, "Factual claims", with one
segment per factual claim (`segment.segment`) citing, for every finding it
asserts, the fact with the same polarity when the documents state the finding
more than once, else the first fact for that field, so a contradicted claim
cites the fact it contradicts and grades `disagree`. A finding no document
states cites nothing and surfaces as an `unknown_fact` uncited assertion (and
fails `segments_cited`). The decision is the parsed answer entity. With a
supplied truth table (`truth_overrides`), the table is the oracle: a fact whose
document polarity differs takes the table's value (the document's reading is
kept in `meta["stated"]`) and a truth entry no document states becomes a fact
without evidence.

Metrics include `grounding_rate = cited_agree / (cited_agree + cited_disagree +
cited_unverifiable)` (`null` when nothing was graded) and `uncited_assertions`,
so the text path's headline survives. It differs from the old claim-level rate in
two known ways: it counts citations rather than claims (a claim asserting two
findings contributes two), and a fabricated finding lowers the old rate (an
unsupported claim) but not this one (nothing to cite); `uncited_assertions` and
`segments_cited` carry that signal instead. On the packaged haematology sample
with the simulated model the two rates agree within 0.05
(`tests/test_ledger_adapters.py`).

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

- CLI: `traceaudit ledger audit <artefact.md> [--json]` prints the checks and metrics.
- Service: `POST /api/ledger` with `{markdown}` or `{case, trace}` returns the full result;
  `POST /api/analyse` (free text) runs the adapters and returns the same result plus the
  documents with each fact's span (spec 17 §3).
- Viewer: `#/analyse/ledger` renders the verdict, the report with graded citation
  chips, the ledger table with coverage marks, the reasoning with clickable ids,
  the rationale differential and the ablation. `#/analyse/trace` renders the same
  blocks for a free-text trace, under a documents pane whose highlights are the facts.

## 5. Relationship to the probes

Counterfactual, neutral and authority probes operate on facts here: a decisive
edit flips a fact's value and re-renders the fact table for the model; the base
reference and disclosure rules (spec 06) are unchanged, with "cites the primary
finding" meaning "cites the edited fact's id or states its new value". The
ablation arm is the load-bearing probe already present in the ENABLE pipeline.
