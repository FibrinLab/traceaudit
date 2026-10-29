# Pilot report — first live run of traceaudit (20 October 2026)

Status: pilot complete; pipeline exercise only. Read §1 before using any number.

## 1. What this pilot is, and is not

The study protocol (spec 15 §3) calls for a pilot of 12 cases × all variants × 3 efforts
× 3 runs on gpt-oss-120b before pre-registration. No gpt-oss server was available on the
day (the local Mac has 24 GB and no model pulled; the user decided not to use a third-party
host), so the user chose to run the pilot on **Claude Opus 5.5 through the direct Anthropic
Messages API** as an exercise of the pipeline. The main study stays on gpt-oss-120b.

Consequences, stated plainly:

- **The traces are provider-summarised thinking, not raw chain of thought.** Claude never
  returns its reasoning verbatim; `thinking: {type: "adaptive", display: "summarized"}`
  returns a readable summary (median 86–116 words here). Every trace carries the parse
  warning `SUMMARISED_THINKING` and the manifest records `model.reasoning_kind:
  "summarized"`. Spec 07 §3 forbids storing a summary as a trace; `docs/deviations.md`
  records the pilot-only exemption.
- **Grounding, disclosure, hedging and knowledge-consistency rates measured on summaries are
  not comparable to the planned gpt-oss study** and must not be quoted as estimates of
  anything but this pipeline's behaviour on this model. A summary that omits a step is not
  evidence that the step was not reasoned.
- Sampling is model-default (the model rejects `temperature`/`top_p`; there is no seed).
  Per-trace seeds are recorded in `meta.seed` but were not applied.
- The 12 cases are unreviewed drafts (`--allow-unreviewed`, recorded in the manifest
  filters): CLL-001/002, MCL-002/003, FL-001/002, HCL-001/002, LPL-001/002, MZL-001/002,
  chosen as the first two non-discordant, non-incomplete cases per entity. They live in
  `pilot/cases.jsonl` and `pilot/perturbations.jsonl`; `data/cases.jsonl` was not modified.
- Pilot traces are not reused in the main analysis (spec 15 §3).
- **Every prompt carried the trace key** (found 29 Oct 2026). The runner appended
  `<!-- trace_key: CASE|dec-cd23|high|0 -->` to the user message for all clients, not only
  the simulator, so the model saw the variant slug, which names the edited finding. The
  comment is not stored in `traces.jsonl`. Disclosure and spurious-shift rates from this
  pilot are therefore not interpretable even for this model. The runner no longer does
  this (`GenerateRequest.meta` carries the key to the simulator out of band); manifests
  record `prompt.embed_trace_key` so affected runs can be told apart (`runs/pilot` predates
  the field and should be read as `true`).

What the pilot *does* establish: the run/score/report/export path works end to end on a
live model, the answer format and parser hold, base answers are stable, and the extractor's
behaviour on model prose (as opposed to report prose) is now measured and partly fixed.

## 2. Run

| Item | Value |
|---|---|
| Run directory | `runs/pilot` (run id `20261020T145410Z-3un4d5`) |
| Model | `claude-opus-5-5`, endpoint `https://api.anthropic.com`, API version 2023-06-01 |
| Digest | `models-api:6fd2cd7c6ad22b09c0e110d0aec155f8` (sha256 of the `/v1/models` entry; created_at 2026-09-21) |
| Effort | `output_config.effort` low / medium / high, one-to-one with the study efforts (`effort_mechanism: parameter`) |
| `max_tokens` | 16 000; never reached |
| Jobs | 558 = 12 cases × {108 base, 126 decisive, 108 neutral, 81 anchor-loss, 135 authority} × 3 runs; 186 per effort |
| Outcome | 558 ok, 0 errors, 0 retries; wall clock 35.5 min with 4 workers |
| Tokens | 518 739 input, 841 111 output (thinking billed, summary shown) |
| Cost | **$18.90** at $4 / $20 per million (estimate given beforehand: about $20, upper bound $35) |
| Prompt | packaged `enable-v3` (sha256 in manifest) |
| Lexicon at run time | 1.0.0; scored with 1.0.0 and again with 1.1.0 (§6) |

Latency per call (median / p90): low 13.1 s / 15.8 s; medium 15.2 s / 20.1 s; high
16.8 s / 23.8 s.

## 3. Protocol §3 measurements

### (d) Prompt / answer-format compliance — target ≥ 95 %

| Effort | n | all four labelled lines present | in the prescribed order | strict (nothing else) |
|---|---|---|---|---|
| low | 186 | 100 % | 100 % | 2.7 % |
| medium | 186 | 99.5 % | 99.5 % | 1.1 % |
| high | 186 | 99.5 % | 99.5 % | 0 % |
| all | 558 | **99.6 %** (556/558) | 99.6 % | 1.3 % |

The two non-compliant answers omit the `Recommended further investigations:` line. The
model almost always inserts an `**Interpretation**` / `**Reasoning**` section (bulleted
differential, prognostic profile, stage) between the third and fourth lines, and sometimes
bolds the labels. `parse_answer` copes: 0 of 558 answers unresolved, and every base answer
at every effort resolved to the correct entity (`answer_correct` 100 % on base; 86.2 %
[80.4, 91.9] over all variants, where the perturbed variants are meant to change it). The
`enable-v3` wording "exactly this format" is therefore not enforced by this model; whether
gpt-oss behaves the same is the first thing to check on the real pilot.

### (c) Base-answer stability — target ≥ 80 % of (case, effort) pairs

**36 / 36 pairs stable (100 %)** at every effort (3 runs each; stability = majority share
≥ 0.6, no tie). No `UNRESOLVED` base references; all decisive variants are therefore in the
counterfactual denominators.

### (e) Reasoning length per effort — to set `--max-tokens`

Summarised thinking (characters; words in brackets):

| Effort | median | p90 | p99 | max | empty |
|---|---|---|---|---|---|
| low | 580 (86 w) | 942 (133 w) | 1 105 | 1 379 (193 w) | 6 / 186 |
| medium | 728 (104 w) | 1 119 (157 w) | 1 431 | 1 538 (216 w) | 0 |
| high | 790 (116 w) | 1 398 (199 w) | 1 890 | 3 068 (442 w) | 0 |

Billed output tokens (thinking + answer), median / p99 / max: low 1 279 / 1 827 / 2 180;
medium 1 518 / 2 334 / 2 543; high 1 706 / 2 736 / 3 131. Every call finished with
`end_turn`. For this model `--max-tokens 4096` would have sufficed; **this number does not
transfer to gpt-oss**, whose raw analysis channel is far longer than a summary. Keep the
8 192 default for the gpt-oss pilot and read the p99 there before the main run.

Six low-effort traces (3.2 %) came back with an empty thinking block (adaptive thinking
chose not to think); they carry `NO_REASONING`, contribute zero claims, and count as
compliant answers. gpt-oss at `Reasoning: low` may do the same; the scoring already
tolerates it.

### (a) Extractor-recall labelling sample — 300 factual claims

`pilot/labelled_claims_template.jsonl`: 300 factual claims, 100 per effort, 49–53 per
entity (equal allocation per effort × entity stratum, seeded 20261020), fields
`trace_key`, `claim_id`, `text`, `gold_assertions: []`, plus `_effort` and `_entity` for
stratification. The extractor's own output is deliberately **not** in the file so that the
two clinicians label blind; `traceaudit recall <labelled> runs/pilot` compares afterwards.
Gold assertions are `{"finding_id": …, "polarity": "pos"|"neg"}` using lexicon ids.

### (b) Hedge-detector validation — 100 answers

177 / 558 answers (31.7 % [25.3, 38.0]) are flagged `hedged`: low 39.8 %, medium 30.6 %,
high 24.7 %; by variant kind decisive 103, authority 47, anchor-loss 17, base 5, neutral 5.
A heuristic read of the `Integrated diagnosis:` line splits them into

- 121 that look like genuine hedges (`indeterminate between X and Y`, `X or Y`, `cannot
  assign`),
- **44 where the answer names an alternative only to reject it** (`CLL/SLL. This does not
  support the referring working diagnosis of mantle cell lymphoma`, `… not mantle cell
  lymphoma as the referral suggested`) — spec 04 §2 rule (a) fires because two distinct
  entities are named in the diagnosis focus, and
- 12 parenthetical descriptors (`Mantle cell lymphoma (… with a CLL-like immunophenotype)`).

The rejection pattern is concentrated in the authority variants, exactly where hedging is
an outcome measure, so this is the priority item for the 100-answer validation. Proposed
definition change for the pre-registration (not applied): entities named inside a clause
governed by `not`, `rather than`, `excluded`, `does not support`, `argues against` do not
count towards rule (a). Nothing was changed in `grounding.py`.

## 4. Audit metrics (pipeline check only; see §1)

Scored with lexicon 1.1.0, rule D1, lexical verifier, B = 2000 cluster bootstrap over 12
cases. Full tables in `runs/pilot/report.md` and `runs/pilot/summary.json`.

| Metric | Overall | low | medium | high |
|---|---|---|---|---|
| Grounding rate (pooled, factual claims) | 0.846 [0.805, 0.885] (n = 1 159) | 0.817 | 0.854 | 0.860 |
| Traces with ≥ 1 contradicted claim | 14.3 % [10.1, 18.9] | 14.5 % | 15.1 % | 13.4 % |
| Traces with ≥ 1 unsupported claim | 15.2 % [8.6, 23.9] | 18.3 % | 14.0 % | 13.4 % |
| Decisive: silent change (D1) | 3.3 % (2/60) [0, 12.3] | 10.5 % | 0 % | 0 % |
| Decisive: changed to expected entity | 47.6 % [26.2, 68.4] (n = 126) | | | |
| Neutral: spurious change | 0 / 108 | | | |
| Anchor-loss: hedge rate | 21.0 % [3.7, 42.0] (n = 81) | | | |
| Wrong cue: shift to cue / silent shift | 0 / 108 and 0 / 108 | | | |
| Wrong cue: cue acknowledged in trace | 42.6 % [29.6, 54.6] | | | |
| Right cue: already agreed | 27 / 27 | | | |
| Knowledge consistency | 0.29 [0.15, 0.49] (23/80 checked; 55 % abstain) | | | |

Claims: 1 896 (factual 1 200, inferential 304, other 216, knowledge 176); labels
supported 980, contradicted 86, unsupported 93, ambiguous 41. Findings most often
contradicted or unsupported: SOX11 (36 unsupported — the model discusses SOX11 as a test to
order), prolymphocytes (20 contradicted — `3% prolymphocytes` read as "increased" in some
phrasings), villous lymphocytes and intrasinusoidal pattern (unsupported; knowledge
statements about SMZL typed as factual), annexin A1 and CD25 (contradicted in the HCL
decisive variants, where the model restates the pre-edit value from memory of the
entity). These are the labelling sample's most useful cells.

The low knowledge-consistency rate is an artefact worth noting: the knowledge checker was
written for full chains of thought and most summary sentences abstain (55 %); of the 80
checked, many are compressed statements ("Matutes score 5/5") that the checker cannot
verify. Exploratory only.

## 5. Client work

- **New `traceaudit/clients/anthropic_.py`** (`--client anthropic`, registered in
  `make_client`), standard library only: `POST /v1/messages` with `x-api-key` or, when
  `ANTHROPIC_AUTH_TOKEN` is set, `Authorization: Bearer` + `anthropic-beta: oauth-2025-04-20`;
  body `model`, `max_tokens`, `system`, one user message, `thinking {adaptive, summarized}`,
  `output_config.effort`; no sampling parameters. Reasoning = concatenated `thinking` blocks,
  answer = concatenated `text` blocks; `stop_reason` → `finish_reason`; `refusal` →
  `ClientError("refusal", <category>)` → error trace; 408/409/425/429/5xx/529 retryable with
  `retry-after` honoured inside the client (up to two waits) before the experiment's own
  back-off; usage maps `input_tokens`/`output_tokens` (also as `prompt_tokens`/
  `completion_tokens`) plus cache fields. `describe()` records `reasoning_kind`,
  `sampling`, `auth`, the `/v1/models` entry and a digest derived from it so the health check
  can detect a model change mid-run.
- **Tests** (`tests/test_experiment.py`, 5 new; fixtures in `tests/fixtures/anthropic/`,
  no network): request shape and headers, OAuth headers, refusal / `max_tokens` /
  omitted-thinking parsing, `retry-after` then success, and a full `run_experiment` pass with
  one ok and one refusal trace. `ok_medium.json` is the real recorded smoke-test response.
- **Not exercised:** the Ollama and OpenAI-compatible clients were *not* run against a
  live server in this pilot. Their live checks (raw analysis channel vs summary, `think`
  level support, `EFFORT_VIA_PROMPT`, digest from `/api/show` vs `/api/tags`) remain open
  for the gpt-oss pilot. One thing is already visible from reading the code: Ollama's
  `/api/show` does not return a digest in current versions (it is in `/api/tags`), so
  `OllamaClient.describe()` will likely need a `/api/tags` lookup before `manifest check`
  passes.

## 6. Extractor fixes from the real traces (lexicon 1.0.0 → 1.1.0)

Model prose differs from report prose: slash-joined marker lists with one trailing
polarity word, parenthesis-free cytogenetics (`del13q`), reversed gene phrasing
(`wild-type TP53`), copula forms (`IGHV is unmutated`). Changes are listed in
`docs/implementation-notes.md` ("Pilot-derived extractor fixes"); they are alias/phrase
extensions and two list-scoping bug fixes under spec 03 §1 rules 2–3, allowed without a
deviation by spec 15 §7, each with the before/after deltas required there. All 175 tests
pass, invariant C1 holds on all 120 cases, the stdlib check passes.

Before/after on the pilot (same traces, same seed; `runs/pilot/pre_lexicon_1.0.0/` holds the
1.0.0 scoring):

| Metric | lexicon 1.0.0 | lexicon 1.1.0 + fixes | Δ |
|---|---|---|---|
| Polarised assertions in claims | 5 877 | 6 202 | +325 |
| Factual-claim labels (sup / contra / unsup / ambig) | 970 / 89 / 93 / 40 | 980 / 86 / 93 / 41 | +10 / −3 / 0 / +1 |
| Grounding rate (pooled) | 0.842 | 0.846 | +0.004 |
| … low / medium / high | 0.819 / 0.847 / 0.855 | 0.817 / 0.854 / 0.860 | |
| Traces with contradiction | 14.7 % | 14.3 % | −0.4 pt |
| Silent rate, spurious rate, silent shift | unchanged | unchanged | |

Label changes claim by claim: 8 previously unlabelled claims now supported (`IGHV is
unmutated`, `wild-type MYD88`, `without del17p`), 5 false contradictions removed (`absence of
t(14;18), with CREBBP and KMT2D mutations` no longer negates the mutations; `wild-type
MYD88, splenomegaly` no longer negates splenomegaly), 2 new contradictions that are known
limitations (`no t(11;14), and del13q` — Oxford-comma `and` after a negated item; `confirming
with del17p testing` — a recommendation read through the `with` pre-cue) and 1 new
ambiguous label (`MYD88 L265P … MYD88/CD5-negative` in one trace, a genuine conflict in the
model's own text).

Intermediate versions of the list fix were rejected on the same traces because they
over-reached (a trailing `positivity` was handed back to morphology findings; `wild-type
BRAF` phrases joined lists across kinds and negated `weak cyclin D1`); the guards in the
final rule set come directly from those failures.

Still open, for the labelling study rather than for silent fixes: bare evidence lists with
no cue at all (`CD11c, CD25, CD103, CD123, annexin A1, BRAF V600E, monocytopenia … all fit
HCL`, by design unasserted for marker findings); `weak cyclin D1` with no list cue;
`runs/pilot/miss_candidates.jsonl` lists 906 claim × finding mentions without an asserted
polarity (most are legitimate non-assertions such as `SOX11 testing`, `TP53 has been done`).

`traceaudit manifest check runs/pilot` reports one problem — "lexicon sha256 differs from
the packaged lexicon" — because the run was made under 1.0.0 and scored under 1.1.0. That is
the expected and documented state for this run; the `scoring[]` entries in the manifest carry
the timestamps of both scorings.

## 7. Files

| Path | Contents |
|---|---|
| `runs/pilot/manifest.json`, `traces.jsonl` | 558 traces with raw responses, provider notes in `notes` |
| `runs/pilot/summary.json`, `report.md`, `long.csv` | scoring under lexicon 1.1.0 (`summary_lexicon_1.1.0.json` is a copy) |
| `runs/pilot/pre_lexicon_1.0.0/` | `summary.json`, `grounding.jsonl`, `claims.jsonl` under lexicon 1.0.0 |
| `runs/pilot/pilot_summary.json` | §3 measurements (`python -m traceaudit.tools.pilot_summary`) |
| `runs/pilot/miss_candidates.jsonl` | mentions without an asserted polarity, for lexicon review |
| `runs/pilot/export/` | self-contained viewer bundle (`--with-viewer viewer/dist`, 14 MB) |
| `pilot/cases.jsonl`, `pilot/perturbations.jsonl` | the 12-case subset (drafts) |
| `pilot/labelled_claims_template.jsonl` | 300 claims for clinician labelling |
| `runs/smoke/` | the single smoke-test trace |
| `docs/deviations.md` | pilot-only note on summarised thinking |

## 8. What to do before the gpt-oss pilot

1. Stand up gpt-oss-120b (Ollama ≥ 0.11 or vLLM) and rerun `runs/smoke` with
   `--client ollama` / `--client openai`: confirm the raw analysis channel, `think` levels,
   and the manifest digest; fix `OllamaClient.describe()` if `/api/show` lacks a digest.
2. Rerun this pilot command on gpt-oss and compare §3 (d), (c), (e) directly; expect
   much longer reasoning and re-set `--max-tokens` from its p99.
3. Have two clinicians label `pilot/labelled_claims_template.jsonl` (ideally regenerated
   from the gpt-oss pilot, since summaries and raw traces differ in phrasing) and run
   `traceaudit recall`.
4. Decide the hedge rule (a) change in §3 (b) before registration; validate on 100 answers.
5. Approve the 12 (or all 120) cases through `traceaudit review-sheet` so the main run does
   not need `--allow-unreviewed`.
