# 03 — Assertion extraction

Status: draft v0.1 · Module: `traceaudit.extract`

`extract_assertions(text, lexicon) -> list[Assertion]` finds every
(finding, polarity) pair in a string, with character spans. It is used on
**reports** (to compute truth and verify invariants C1/P1) and on **traces** (to
grade factual claims and detect disclosure). It is deterministic, regex-driven
and has no model component. `findings(text) -> dict[finding_id, polarity]`
reduces the assertion list to a map and raises `PolarityConflict` on
disagreement within the same text.

## 1. Pipeline

1. **Pre-normalise for matching only.** Build a lowercase copy with Unicode
   dashes (`−`, `–`, `—`, `‑`) mapped to `-`, non-breaking spaces to spaces, and
   `::`/`/` in fusion names kept. Spans are always reported against the
   **original** string; the normalisation is length-preserving (one char → one
   char) so no index map is needed.
2. **Phrase pass.** For each finding with `pos_phrases` / `neg_phrases`, match
   each phrase (word-bounded). Emit an assertion and mask the span so later
   passes do not re-match inside it.
3. **Numeric pass.** For findings with `numeric_rule`, find `anchor … number unit`
   within 60 characters, compare, emit, mask.
4. **Alias pass.** Find every alias occurrence of every finding (longest match
   first, word-bounded, disambiguated per spec 02 §2.6). Each hit becomes a
   *marker token* with its span and finding id.
5. **Polarity resolution** per marker token in this precedence order; the first
   rule that fires wins:
   1. **Suffix** immediately after the token (≤ 1 space): `+`, `(+)`, `++`,
      `-`, `(-)`, `pos`, `neg`, `positive`, `negative`, `dim`, `bright`, `weak`,
      `partial`, `strong`, `moderate`, `+dim`, `+ (dim)`, `(dim)`, `-positive`,
      `-negative` (hyphenated adjective). The bare `-` suffix counts as negative
      **only** when followed by whitespace, `,`, `;`, `.`, `/`, `)`, end of
      string, or another marker token; `CD5-positive` is positive and
      `CD5-CD23` is not an assertion on either.
   2. **Local verb/adjective** within the same clause and ≤ 6 tokens **before**
      the marker list: `positive for`, `negative for`, `expression of`,
      `expresses`, `co-expression of`, `lacks`, `lack of`, `loss of`, `absence
      of`, `absent`, `no`, `without`, `not expressed`, `fails to express`,
      `detected`, `not detected`, `shows`, `with`. A **marker list** is a
      maximal run of marker tokens separated by `,`, `/`, ` and `, ` & `,
      `, and `, ` plus `, ` with ` (only when the next token is a marker).
      The polarity applies to every member of the list unless a member has its
      own suffix (rule 1), which overrides.
   3. **Local verb/adjective after** the list, ≤ 4 tokens: `positive`, `negative`,
      `expressed`, `not expressed`, `absent`, `present`, `detected`, `not
      detected`, `identified`, `not identified`, `seen`, `not seen`, `excluded`,
      `wild-type`, `mutated`. Same list-scoping as rule 2.
   4. **Noun forms**: `<marker> positivity|expression|co-expression` → pos;
      `<marker> negativity|loss|absence` → neg; `positivity|expression for|of
      <list>` → pos; `absence|lack|loss of <list>` → neg.
   5. **Unresolved** → the token is recorded as a *mention* (`polarity: null`)
      and not an assertion. Mentions are kept for `mentioned_primary` (spec 06).
6. **Clause boundaries.** Scope for rules 2–4 stops at `.`, `;`, `:`, ` but `,
   ` whereas `, ` while `, ` however`, `→`, `=>`, `->`, newline, and at an
   opening parenthesis unless the whole list is inside the parentheses.
7. **Intensity-coded findings** (`sIg_dim`, `CD20_dim`) use the mapping in spec
   02 §3.3; an intensity word anywhere in the marker's clause within 4 tokens
   on either side resolves polarity. Plain `+`/`-` on these produce a mention,
   not an assertion.
8. **Conflict handling.** If the same finding receives both polarities within
   one *sentence*, both assertions are emitted with `warnings: ["CONFLICT"]`
   and `findings()` raises `PolarityConflict`; `segment`/`grounding` (spec 04)
   mark the claim `ambiguous`. Across sentences in a **report**, a conflict is a
   case-validation error (C2). Across sentences in a **trace**, each claim is
   graded independently (the model may legitimately correct itself).

## 2. Output

```python
@dataclass(frozen=True)
class Assertion:
    finding_id: str
    polarity: Literal["pos", "neg"] | None   # None → mention only
    start: int; end: int                      # span of the marker token (original string)
    surface: str                              # original text covering marker + polarity cue
    cue_start: int; cue_end: int              # span of the polarity cue; equal to start/end when suffix-free
    rule: str                                 # "phrase" | "numeric" | "suffix" | "pre" | "post" | "noun" | "none"
    intensity: str | None                     # dim|weak|partial|moderate|bright|strong|None
    warnings: tuple[str, ...]
```

## 3. Worked examples

| Text | Assertions |
|---|---|
| `CD5+, CD23+, CD200+, FMC7-, CD79b dim` | CD5 pos, CD23 pos, CD200 pos, FMC7 neg, CD79b pos(dim) |
| `positive for CD19, CD20 and CD10 but negative for CD5` | CD19 pos, CD10 pos, CD5 neg; CD20 → mention only for `CD20_dim` (no intensity) |
| `no t(11;14) or t(14;18)` | t_11_14 neg, t_14_18_BCL2 neg |
| `cyclin D1 and SOX11 expression is absent` | cyclin_D1 neg, SOX11 neg (rule 3, `absent`) |
| `Lacks CD103 and CD25; CD11c partial` | CD103 neg, CD25 neg, CD11c pos(partial) |
| `BRAF V600E detected (VAF 31%)` | BRAF_V600E pos |
| `BRAF wild-type` | BRAF_V600E neg (phrase) |
| `IGHV unmutated (97.2% identity)` | IGHV_unmutated pos (phrase) — note: 97.2% < 98% conflicts with "unmutated"; phrase wins, warning `NUMERIC_DISAGREE` |
| `dim surface kappa` | sIg_dim pos |
| `moderate-intensity sIg lambda` | sIg_dim neg |
| `Clonal B-cell count 3.9 x10^9/L` | lymphocytosis neg |
| `CD5-positive, CD23-negative B-cell population` | CD5 pos, CD23 neg |
| `CD5- CD10- CD23-` | CD5 neg, CD10 neg, CD23 neg |
| `Is cyclin D1 positive?` | cyclin_D1 pos *extracted*, but the sentence is typed `other` by segment and not graded |
| `if cyclin D1 were positive this would be MCL` | cyclin_D1 pos extracted; claim typed `inferential/conditional`, not graded |
| `CD5+ CLL` | CD5 pos; `CLL` is an entity mention |
| `MCL is typically CD23 negative` | CD23 neg extracted; claim typed `knowledge` (spec 04) |

## 4. Report-level API

```python
def findings(text: str, lexicon=None) -> dict[str, str]           # raises PolarityConflict
def finding_spans(case: Case) -> dict[str, list[Evidence]]        # finding → [(report, start, end, polarity)]
def extract_assertions(text: str, lexicon=None) -> list[Assertion]
```

`finding_spans` runs extraction per report (not on the rendered string) so that
evidence offsets index into `Case.reports[report]` for the viewer.

## 5. Recall measurement

Model-written text is less regular than reports. `extract` MUST ship with
`traceaudit/tools/extractor_recall.py` which takes a clinician-labelled sample
(`labelled_claims.jsonl`: `trace_key, claim_id, gold_assertions[]`) and reports
per-finding precision/recall and the confusion of polarity. The study plan
(spec 15) labels 300 factual claims; the paper reports the figures. Target:
recall ≥ 0.90 and precision ≥ 0.95 at the assertion level before scoring the
real-model runs; below that, aliases and rules are extended and the sample is
re-run (allowed post-registration, spec 02 §8).

## 6. Non-goals (v1)

- Quantities other than the two numeric rules (counts, VAFs, percentages of
  cells) are not graded.
- Temporal or comparative statements (`now CD5 positive, previously negative`)
  are not modelled; both assertions are emitted and will conflict → ambiguous.
- Anaphora (`it is negative`, `the latter is absent`) is not resolved.
