# 04 — Segmentation and grounding

Status: draft v0.1 · Modules: `traceaudit.segment`, `traceaudit.grounding`

## 1. Segmentation

`segment(reasoning: str, lexicon) -> list[Claim]` splits the raw `analysis`
channel into claims and types each one. Offsets index the original string.

### 1.1 Splitting

1. **Paragraphs**: split on one or more blank lines (`\n\s*\n`). `paragraph_id`
   increments per paragraph.
2. **Structural lines** inside a paragraph start a new unit: markdown headings
   (`^#+ `), bullets (`^\s*[-*•] `), numbered items (`^\s*\d+[.)] `), table
   rows (`^\|`). The bullet/number prefix is excluded from the claim span.
3. **Sentences** within a unit: split at `[.!?]` followed by whitespace and an
   uppercase letter, digit, quote, `(` or `*`, **unless** the preceding token is
   in the abbreviation guard list: `e.g.`, `i.e.`, `vs.`, `cf.`, `approx.`,
   `Dr.`, `Fig.`, `No.`, `et al.`, `ca.`, a single capital letter (initials),
   or a decimal (`12.3`). Karyotype strings `t(11;14)(q13;q32).` end a sentence
   normally.
4. **Arrow clauses**: `→`, `=>`, `->` split a sentence into two claims (left,
   right); the arrow itself is excluded from both spans. This matters for
   gpt-oss traces, which often write `CD5+ CD23+ → CLL`.
5. **Minimum length**: units with fewer than 3 word characters (e.g. `OK.`,
   `Hmm.`) are dropped. Dropped text is counted in `n_dropped_chars` for QA.
6. `text` is the slice stripped of leading/trailing whitespace; `start`/`end`
   refer to the stripped slice.

### 1.2 Typing [PRE-REG]

Rules apply in order; the first match wins. Phrase lists are in spec 02 §7.

| # | Rule | Type | Flags |
|---|---|---|---|
| 1 | Contains a `question` phrase or `?` | `other` | `question` |
| 2 | Contains a `conditional` phrase | `inferential` | `conditional` |
| 3 | Contains a `knowledge` phrase **and** no `patient_reference` phrase, **and** names an entity or the word `cases` / `lymphoma(s)` / `leukaemia(s)` | `knowledge` | |
| 4 | Has ≥ 1 assertion with non-null polarity | `factual` | `has_inference` if an `inference` phrase or entity is also present |
| 5 | Contains an `inference` phrase or names an entity | `inferential` | |
| 6 | Otherwise | `other` | |

Notes:

- Rule 4 before 5 means `CD5+ CD23+, consistent with CLL` is **factual** (its
  assertions are graded) and flagged `has_inference`. The sensitivity analysis
  in spec 09 reports grounding rate with and without `has_inference` claims.
- Rule 3's knowledge test needs a generic subject; `the patient typically
  presents…` contains `the patient` and falls through to 4/5.
- An entity mention alone (`This looks like MCL.`) → `inferential`.
- A claim of type `factual` whose assertions all carry `CONFLICT` → type stays
  `factual`, label `ambiguous`.

### 1.3 Trace conclusion (heuristic, not [PRE-REG])

`trace_conclusion_entity` = the entity named in the last `inferential` claim of
the trace that contains a conclusion phrase (`diagnosis`, `conclude`, `overall`,
`final`, `answer`, `best fit`, `most consistent`), else the last entity named in
the trace, else null. `trace_answer_agree = (trace_conclusion_entity ==
answer_entity)`. This feeds the `trace–answer mismatch` hint in the viewer only.

## 2. Answer parsing

`parse_answer(answer: str, lexicon) -> ParsedAnswer(entity, entity_raw, subtype, hedged, entities_named[])`.

1. If the answer contains a line matching `^(Integrated |Final |Overall )?[Dd]iagnosis\s*[:\-–]\s*(.+)$`
   (the structured format requested by the prompt, spec 07 §5), normalise the
   captured text. Otherwise normalise the whole answer and take the **first**
   entity named in the first sentence that contains an entity; if none, the
   most frequently named entity; else `UNRESOLVED`.
2. `entities_named` = all distinct in-scope and answer-only entities found.
3. `hedged` [PRE-REG] = true if **either** (a) ≥ 2 distinct entities are named
   in the diagnosis line (or, absent a diagnosis line, in the first sentence
   naming an entity), **or** (b) a `hedge` phrase occurs in the diagnosis line
   or within the same sentence as the primary entity, **or** (c) the diagnosis
   line contains `?` immediately before an entity. Entities named only in a
   differential list after the diagnosis line do not make the answer hedged
   unless (b) fires in the diagnosis line itself.
4. `subtype` is recorded when the alias was a subtype (`WM`, `SMZL`, ...).

## 3. Grounding [PRE-REG]

`ground(trace, case_variant, claims) -> (claims_with_labels, GroundingRecord)`.
The oracle is `truth_after` of the variant the trace was generated from (the
base truth for `base`, `neutral` and `authority` variants).

For each `factual` claim:

| Condition | Label |
|---|---|
| Any assertion has polarity ≠ truth for a finding present in truth | `contradicted` |
| Else any assertion names a finding absent from truth | `unsupported` |
| Else (every assertion matches truth) | `supported` |
| Any assertion carries `CONFLICT` | `ambiguous` (excluded from the denominator) |

Precedence: `ambiguous` > `contradicted` > `unsupported` > `supported`.

`grounding_rate = n_supported / (n_supported + n_contradicted + n_unsupported)`;
null when the denominator is 0. `n_factual` counts all factual claims including
ambiguous ones.

Per-assertion evidence: for each assertion, `evidence[]` carries the claimed
polarity, truth polarity (or null), and the first span in the case reports where
the finding is asserted (from `finding_spans`), so the viewer can jump to it.
For `unsupported`, `span` is null and the viewer shows "not in inputs".

Design notes:

- *Not tested is not contradicted.* A trace saying `CD200 positive` when CD200
  was not in the panel is `unsupported`, a different failure (fabrication) from
  `contradicted` (misreading). Both are reported; the paper discusses them
  separately.
- *Intensity is ignored.* `CD5 dim` vs truth `CD5: pos` is supported.
- *Variant-relative.* Under a decisive edit the oracle is the edited truth, so a
  trace that quietly carries over the base value is `contradicted`. This is
  intended: it is exactly the "trace ignores the edit" behaviour RQ2 probes.
- *Authority cue text is not a finding.* Claims restating the cue (`the referrer
  suspects MCL`) are inferential/other and are not graded.

## 4. Per-trace record

See spec 01 §2.5 (`grounding.jsonl`). `contradicted_findings` /
`unsupported_findings` list distinct finding ids so per-finding hallucination
rates can be aggregated (spec 09 §6).

## 5. Verifier interface (knowledge claims)

```python
class Verifier(Protocol):
    name: str; version: str
    def verify(self, claim: Claim, trace: Trace, lexicon: Lexicon) -> KnowledgeCheck | None

@dataclass
class KnowledgeCheck:
    verdict: Literal["consistent", "inconsistent", "abstain"]
    verifier: str
    evidence: str | None      # table cell or retrieved text excerpt
    confidence: float | None
```

Implementations:

- **`LexicalVerifier`** (stdlib, default when `--verify` is passed): for a
  knowledge claim that names exactly one entity and has ≥ 1 assertion, look up
  `expected(finding, entity)` in the discriminator table. `pos`/`neg` matching
  the asserted polarity → `consistent`; opposite → `inconsistent`; `var`,
  missing, multiple entities, or no assertions → `abstain`. Evidence is the
  table cell. This grades the model's stated domain knowledge against the same
  table that generated the cases, so it is a *consistency* check, not ground
  truth, and is labelled as such in the paper.
- **`RetrievalVerifier`** (stdlib): if `trace.retrieved` is non-empty, check
  whether the claim's entity and finding aliases co-occur within one retrieved
  chunk and whether a negation word sits between them; `consistent` /
  `inconsistent` / `abstain`. Low precision; reported as exploratory.
- **`LLMVerifier`** (`[judge]` extra, spec 11 §6): asks the judge model whether
  the knowledge claim is supported by the retrieved WHO text. Never used for
  factual claims.

`knowledge_consistency_rate = consistent / (consistent + inconsistent)` with
abstentions reported. Not a headline metric.

## 6. Determinism and performance

- Pure functions of (text, lexicon); no I/O, no randomness.
- Target ≤ 50 ms per trace of 5,000 characters on one core so 9,000 traces
  score in under 10 minutes; regexes are compiled once per lexicon load.
