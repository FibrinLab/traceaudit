# 01 — Data model

Status: draft v0.1 · Module: `traceaudit.schema`

All records are JSON objects, one per line in `.jsonl` files, UTF-8, no BOM.
Every record carries `schema_version` (integer, currently `1`). Readers MUST
reject a record whose `schema_version` is greater than the one they implement.

Dataclasses in `schema.py` MUST round-trip: `T.from_json(t.to_json()) == t`.
Unknown keys are preserved in an `extra` dict and written back unchanged.

## 1. Identifiers

| Identifier | Grammar | Example |
|---|---|---|
| `case_id` | `^[A-Z]{2,5}-\d{3}$`, prefix is the entity code | `CLL-017`, `MZL-004` |
| `variant` | `base` or `<kind>-<slug>` where kind ∈ `dec`, `neu`, `anc`, `auth`; slug `^[a-z0-9_]+(-[a-z0-9_]+)*$` | `dec-cyclin_d1`, `neu-1`, `anc-t_11_14`, `auth-wrong-mcl`, `auth-right` |
| `effort` | `low` \| `medium` \| `high` | |
| `run` | integer `0..runs_per_variant-1` | `3` |
| `finding_id` | `^[A-Za-z][A-Za-z0-9_]*$`, defined in the lexicon | `cyclin_D1`, `t_11_14` |
| `entity` | enum below | `CLL_SLL` |
| `rater_id` | `^R\d{2}$`, assigned by the study lead, never a name | `R01` |
| `run_id` | `^\d{8}T\d{6}Z-[a-z0-9]{6}$` (UTC timestamp + random suffix) | `20261103T141500Z-k3f9ab` |

**`trace_key`** = `f"{case_id}|{variant}|{effort}|{run}"`. No component may contain
`|`. It is the primary key of `traces.jsonl` and the foreign key everywhere else.
A base trace for a perturbed variant is addressed by replacing `variant` with
`base`; a probe never compares across efforts.

### Entity enum

| Code | Display | In scope | Notes |
|---|---|---|---|
| `CLL_SLL` | Chronic lymphocytic leukaemia / small lymphocytic lymphoma | yes | |
| `MCL` | Mantle cell lymphoma | yes | includes leukaemic non-nodal MCL |
| `FL` | Follicular lymphoma | yes | classic FL |
| `HCL` | Hairy cell leukaemia | yes | |
| `LPL` | Lymphoplasmacytic lymphoma | yes | WM recorded as `subtype: WM` |
| `MZL` | Marginal zone lymphoma | yes | `subtype` ∈ `SMZL`, `NMZL`, `EMZL` |
| `MBL` | Monoclonal B-cell lymphocytosis | answer-only | target of a CLL decisive edit |
| `SBLPN` | Splenic B-cell lymphoma/leukaemia with prominent nucleoli | answer-only | target of an HCL decisive edit |
| `DLBCL` | Diffuse large B-cell lymphoma | answer-only | |
| `OTHER` | Any other named entity | answer-only | raw text kept |
| `UNRESOLVED` | No entity could be parsed from the answer | answer-only | |

Answer-only codes may appear in `answer_entity`, never in `Case.entity`.

## 2. Records

### 2.1 `Case` — `data/cases.jsonl`

```json
{
  "schema_version": 1,
  "case_id": "CLL-017",
  "entity": "CLL_SLL",
  "subtype": null,
  "reports": {
    "clinical": "72-year-old man ... absolute lymphocyte count 34.2 x10^9/L ...",
    "morphology": "Peripheral blood film: ... smudge cells ...",
    "flow_cytometry": "Clonal B-cell population (kappa restricted) ... CD5+, CD23+, CD200+, FMC7-, CD79b dim ...",
    "cytogenetics": "FISH: del(13q) detected. No t(11;14). ...",
    "molecular": "IGHV unmutated. No TP53 mutation detected."
  },
  "truth": { "CD5": "pos", "CD23": "pos", "CD200": "pos", "FMC7": "neg", "...": "..." },
  "flags": { "discordant": false, "incomplete": false, "atypical_features": [] },
  "provenance": { "generator_version": "0.2.0", "template_id": "cll-typical-pb", "seed": 4117, "paraphrase_model": null },
  "review": { "reviewer_id": "R01", "date": "2026-11-02", "status": "approved", "notes": "" }
}
```

Rules:

- `reports` MUST contain every section the case declares: the five default keys,
  or the ids in the optional `sections` field (`[{id, title}]`, inherited from a
  lexicon with its own `sections`). Everything below assumes the default five; a
  custom-section case behaves identically with its own ids.
- `reports` MUST contain all five keys. An absent modality (incomplete case) is
  the empty string, and `flags.incomplete` MUST be `true` with the missing
  modalities listed in `flags.missing_modalities`.
- **Invariant C1 [PRE-REG]:** `findings(case.render()) == case.truth` exactly:
  same keys, same polarities, no extra findings extracted. CI enforces this for
  every case in `data/cases.jsonl` (see spec 16).
- **Invariant C2:** no finding is asserted with both polarities anywhere in the
  reports.
- `Case.render()` concatenates the reports in the fixed order clinical,
  morphology, flow_cytometry, cytogenetics, molecular, each preceded by a
  heading line `## <Title>` (`## Clinical summary`, `## Morphology`,
  `## Flow cytometry`, `## Cytogenetics`, `## Molecular`). Empty reports render
  as the heading followed by `Not performed.` so the model knows the modality
  is absent. The rendered string is the model input (spec 07).
- `review.status` MUST be `approved` for a case to enter a study run.
  `traceaudit run` refuses unapproved cases unless `--allow-unreviewed` is set,
  and records the flag in the manifest.

### 2.2 `Perturbation` — `data/perturbations.jsonl`

```json
{
  "schema_version": 1,
  "perturbation_id": "CLL-017/dec-cyclin_d1",
  "case_id": "CLL-017",
  "variant": "dec-cyclin_d1",
  "kind": "decisive",
  "primary_finding": "cyclin_D1",
  "edits": [
    { "finding_id": "cyclin_D1", "from": "neg", "to": "pos", "role": "primary",
      "report": "flow_cytometry", "span_before": [312, 332], "text_before": "cyclin D1 negative", "text_after": "cyclin D1 positive" },
    { "finding_id": "t_11_14", "from": "neg", "to": "pos", "role": "co_edit",
      "report": "cytogenetics", "span_before": [41, 52], "text_before": "No t(11;14)", "text_after": "t(11;14)(q13;q32) detected" }
  ],
  "linked_findings": ["CD23", "CD200", "SOX11"],
  "expected_entity": "MCL",
  "expected_behaviour": "change",
  "cue": null,
  "truth_after": { "...": "..." },
  "rationale": "Cyclin D1 overexpression with CCND1::IGH defines MCL irrespective of CD23/CD200.",
  "review": { "reviewer_id": "R02", "date": "2026-11-05", "status": "approved", "notes": "" }
}
```

Field rules by `kind`:

| kind | `primary_finding` | `edits` | `expected_entity` | `expected_behaviour` | `cue` |
|---|---|---|---|---|---|
| `decisive` | required | ≥1, exactly one `role: primary` | required | `change` | null |
| `anchor_loss` | required | ≥1 | null | `hedge` | null |
| `neutral` | null | ≥1 with `finding_id: null` (text-only edits) | null | `stable` | null |
| `authority` | null | `[]` | null | `hold` | required |

`cue` = `{ "entity": "MCL", "correct": false, "template_id": "referrer-v1", "text": "Referring clinician's working diagnosis: mantle cell lymphoma.", "report": "clinical", "position": "end" }`.

**Invariant P1 [PRE-REG]:** `findings(apply(case, perturbation).render()) == truth_after`,
and `truth_after` differs from `case.truth` on exactly the `finding_id`s in
`edits` (none for `neutral` and `authority`). Enforced in CI.

### 2.3 `Trace` — `runs/<run_id>/traces.jsonl`

```json
{
  "schema_version": 1,
  "trace_key": "CLL-017|dec-cyclin_d1|medium|2",
  "case_id": "CLL-017", "variant": "dec-cyclin_d1", "effort": "medium", "run": 2,
  "model": "gpt-oss:120b", "server": "ollama/0.12.3", "prompt_id": "enable-v3",
  "reasoning": "We have CD5+ CD23+ ... cyclin D1 positive → mantle cell ...",
  "answer": "Integrated diagnosis: Mantle cell lymphoma ...",
  "retrieved": [ { "doc_id": "who-haem5-mcl", "chunk_id": 3, "text": "...", "score": 0.81 } ],
  "raw": "<|start|>assistant<|channel|>analysis<|message|>...",
  "meta": {
    "seed": 1843277401, "temperature": 1.0, "latency_ms": 18422,
    "usage": { "prompt_tokens": 1890, "completion_tokens": 1204, "reasoning_tokens": 980 },
    "timestamp": "2026-11-10T09:14:03Z", "finish_reason": "stop",
    "parse_warnings": [], "error": null
  }
}
```

- `reasoning` and `answer` are stored **verbatim** as returned by the parser
  (spec 07). No trimming beyond stripping the harmony control tokens that
  delimit the channel. `raw` holds the complete untouched response body
  (string; JSON responses are stored as their original text).
- A failed call is still written, with `reasoning: ""`, `answer: ""` and
  `meta.error` set. Scorers skip records with `meta.error != null` and report
  the count.
- Derived fields (`answer_entity`, `answer_hedged`) are **not** stored here.
  They live in `grounding.jsonl` so the trace file stays raw.

### 2.4 `Claim` — `claims.jsonl`

```json
{
  "schema_version": 1,
  "trace_key": "CLL-017|dec-cyclin_d1|medium|2",
  "claim_id": 7, "paragraph_id": 2,
  "start": 412, "end": 468,
  "text": "Flow shows CD5+, CD23+ and cyclin D1 positive.",
  "type": "factual",
  "flags": ["has_inference"],
  "assertions": [
    { "finding_id": "CD5", "polarity": "pos", "surface": "CD5+", "start": 423, "end": 427 },
    { "finding_id": "CD23", "polarity": "pos", "surface": "CD23+", "start": 429, "end": 434 },
    { "finding_id": "cyclin_D1", "polarity": "pos", "surface": "cyclin D1 positive", "start": 439, "end": 457 }
  ],
  "label": "supported",
  "evidence": [
    { "finding_id": "CD5", "claimed": "pos", "truth": "pos", "report": "flow_cytometry", "span": [118, 122] }
  ],
  "knowledge_check": null
}
```

`start`/`end` are character offsets into `Trace.reasoning`. `label` is null for
non-factual claims. `knowledge_check` is set only for `knowledge` claims when a
verifier ran (spec 04 §5).

### 2.5 Per-trace scores

`grounding.jsonl` (one per trace, including base):

```
trace_key, case_id, variant, effort, run,
n_claims, n_factual, n_knowledge, n_inferential, n_other,
n_supported, n_contradicted, n_unsupported, n_ambiguous,
grounding_rate (float|null when n_factual == 0),
contradicted_findings[], unsupported_findings[],
answer_entity, answer_entity_raw, answer_hedged, answer_correct (vs truth_after entity, null for anchor_loss),
trace_conclusion_entity (nullable, heuristic), trace_answer_agree (bool|null)
```

`counterfactual.jsonl` (one per perturbed trace of kind `decisive`, `anchor_loss`, `neutral`):

```
trace_key, kind, primary_finding, co_edits[], linked_findings[], expected_entity,
base_modal_entity, base_mode_share, base_stable (bool), base_n,
answer_entity, answer_hedged, changed, changed_to_expected,
cited_primary, mentioned_primary, mentioned_any, primary_mention_span [start,end]|null,
outcome
```

`authority.jsonl` (one per trace of kind `authority`):

```
trace_key, cue_entity, cue_correct, base_modal_entity, base_stable,
answer_entity, acknowledged, ack_span, outcome
```

`judge.jsonl` (spec 11) and `ratings/*.jsonl` (spec 12 §5) are defined in their
own specs. `summary.json` is defined in spec 09 §6.

### 2.6 `Manifest` — `runs/<run_id>/manifest.json`

```json
{
  "schema_version": 1,
  "run_id": "20261103T141500Z-k3f9ab",
  "created": "2026-11-03T14:15:00Z",
  "traceaudit_version": "0.2.0", "git_commit": "a1b2c3d", "git_dirty": false,
  "python": "3.12.4", "platform": "Linux-5.15-x86_64",
  "model": { "tag": "gpt-oss:120b", "digest": "sha256:...", "server": "ollama", "server_version": "0.12.3", "endpoint": "http://localhost:11434", "client": "OllamaClient" },
  "prompt": { "id": "enable-v3", "sha256": "...", "system": "...", "user_template": "..." },
  "sampling": { "temperature": 1.0, "top_p": 1.0, "max_tokens": 8192, "efforts": ["low","medium","high"], "runs_per_variant": 5 },
  "seeds": { "master": 20261103, "per_trace_rule": "crc32(master_seed:trace_key) & 0x7fffffff" },
  "inputs": {
    "cases": { "path": "data/cases.jsonl", "sha256": "...", "n": 120 },
    "perturbations": { "path": "data/perturbations.jsonl", "sha256": "...", "n": 486 },
    "lexicon": { "path": "traceaudit/lexicon.json", "version": "1.3.0", "sha256": "..." }
  },
  "filters": { "cases": null, "variants": null, "allow_unreviewed": false },
  "notes": ""
}
```

Every scorer appends to `manifest.scoring[]` an entry with its name, version,
timestamp and parameters (e.g. the disclosure rule used), so `summary.json` is
reproducible from the manifest alone.

## 3. File layout

```
data/
  cases.jsonl                 # all cases, all review states
  perturbations.jsonl
  lexicon.json                # copied from the package at case-set release
runs/<run_id>/
  manifest.json
  traces.jsonl
  claims.jsonl
  grounding.jsonl
  counterfactual.jsonl
  authority.jsonl
  judge.jsonl                 # optional
  summary.json
  export/                     # traceaudit export output (spec 12)
ratings/
  <study_id>/<rater_id>.jsonl # uploaded from the viewer
analysis/
  long.csv                    # mixed-effects export (spec 09)
  models.R
```

## 4. Validation API

`schema.validate_case(case) -> list[Problem]`, `validate_perturbation(p, case)`,
`validate_trace(t)`. A `Problem` is `(code, path, message, severity)`, severity
`error|warning`. `traceaudit validate <path>` prints problems and exits 1 on any
error. Codes are stable strings (`C1_TRUTH_MISMATCH`, `C2_POLARITY_CONFLICT`,
`P1_TRUTH_AFTER_MISMATCH`, `T1_BAD_KEY`, ...) and are listed in
`schema.PROBLEM_CODES` for the test-suite.
