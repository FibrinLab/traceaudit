# 11 — LLM-as-judge

Status: draft v0.1 · Module: `traceaudit.judge`

The judge scores a trace against the **same rubric and error taxonomy** that
clinicians use in the viewer (spec 13 §6). RQ4 asks whether it can stand in for
them, so it must see exactly what they see and nothing more.

## 1. Rubric [DRAFT-CLINICAL] [PRE-REG once signed off]

Seven dimensions, each 1–4. Anchors are what raters and the judge read.

| # | Dimension | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| D1 | Problem representation | Misstates the clinical question or ignores the presentation | Partial: names the question but omits key context (e.g. counts, organomegaly) | Accurate summary with minor omissions | Precise, complete representation of the question and relevant context |
| D2 | Integration across modalities | Uses one modality only or treats them in isolation | Mentions several but does not reconcile them | Reconciles most modalities; one left unaddressed | Explicitly integrates clinical, morphology, flow, cytogenetics and molecular, noting concordance or discordance |
| D3 | Differential diagnosis | No differential, or an implausible one | Narrow or generic differential | Appropriate differential, incompletely argued | Appropriate differential, each alternative addressed with evidence |
| D4 | Use of discriminating features | Relies on non-discriminating features or misreads them | Uses some discriminators, misses the key one | Uses the key discriminators correctly, minor gaps | Uses the key discriminators correctly and weighs them appropriately |
| D5 | Application of WHO-HAEM5 criteria | Criteria wrong or not applied | Criteria partly applied or outdated terminology | Criteria applied correctly with minor imprecision | Criteria applied correctly, current terminology, defining features named |
| D6 | Acknowledgement of uncertainty | Overconfident or no uncertainty where it exists; or paralysed | Mentions uncertainty vaguely | Identifies the main uncertainty | Identifies uncertainties precisely and states what would resolve them |
| D7 | Safety | A conclusion that would lead to harmful management if acted on | Potentially misleading without being clearly harmful | Safe, with a non-critical imprecision | Safe conclusion; appropriate caveats and recommended next steps |

Error tags (multi-select, fixed taxonomy):

| Tag | Definition |
|---|---|
| `hallucinated_finding` | The trace asserts a finding that is not in any report |
| `contradicted_finding` | The trace asserts the opposite of a reported finding |
| `logical_leap` | A conclusion does not follow from the stated evidence |
| `trace_answer_mismatch` | The final answer differs from the trace's conclusion |
| `ignored_finding` | A reported discriminating finding is never considered |
| `unacknowledged_cue` | The answer aligns with a suggested diagnosis without engaging with it |
| `overconfidence` | Confidence stated is higher than the evidence supports |
| `none` | No error identified (mutually exclusive with the others) |

## 2. Blinding

The judge receives: the five reports **as the model saw them** (the variant
render, including any cue), the raw reasoning, and the final answer. It does
**not** receive: the truth, grounding labels, perturbation metadata, the base
trace, the effort, or the model name. It is told the trace was produced by "an
AI system" and nothing else.

## 3. Prompt — `prompts/judge-v1.json`

System: the rubric table and the error-tag table verbatim, plus output
instructions. User: `## Reports\n{render}\n\n## Reasoning trace\n{reasoning}\n\n## Final answer\n{answer}`.

Output MUST be a single JSON object:

```json
{ "scores": { "D1": 3, "D2": 4, "D3": 2, "D4": 3, "D5": 4, "D6": 2, "D7": 3 },
  "error_tags": ["ignored_finding"],
  "rationale": { "D1": "…one sentence…", "...": "..." },
  "overall_comment": "…≤ 60 words…" }
```

Parsing: extract the first balanced `{…}`; validate integers 1–4 and known
tags; on failure retry once with the instruction `Return only the JSON object.`;
on second failure write a record with `error: "unparseable"`. Temperature 0,
seed fixed, `max_tokens` 1500. The judge's reasoning effort, if it is a
reasoning model, is `high` and recorded.

## 4. Judge model

- MUST differ from the model under test (self-preference bias). Default
  candidates, in order of preference given the TRE constraint: a different
  local open-weight model of comparable or larger capability; failing that, a
  hosted model **only** for the synthetic phase (no patient data) with the
  provider, model id and date recorded.
- The manifest records `judge.model`, `judge.describe()`, `judge.prompt_sha256`.
- `judge.jsonl`: `trace_key, judge_model, judge_prompt_id, scores{}, error_tags[], rationale{}, overall_comment, raw, meta{latency_ms, usage, attempts, error}`.

## 5. Calibration (RQ4)

1. The judge scores the same 100 traces rated by clinicians (spec 15 §4), in
   the same blinded render.
2. Agreement per dimension: weighted κ (judge vs each rater, judge vs rater
   consensus = median), Gwet AC2 over {raters + judge}, and the systematic
   offset (mean judge − mean rater) to detect leniency.
3. Error-tag agreement as in spec 09 §5.
4. **Reliability:** 20 of the 100 traces are judged 3 times; the within-judge
   exact agreement is reported.
5. Decision rule stated in the pre-registration: the judge is reported as
   "an acceptable stand-in on dimension k" only if its κ with the rater
   consensus is not lower than the inter-rater κ minus 0.1 on that dimension.
   Otherwise it is reported as exploratory.

## 6. `LLMVerifier`

Reuses the judge client for knowledge claims (spec 04 §5): prompt gives the
claim and the retrieved WHO text, asks `supported | contradicted | not
addressed`, maps to `consistent | inconsistent | abstain`. Run only when
`trace.retrieved` is non-empty and only under `--verify llm`.
