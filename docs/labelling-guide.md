# Labelling guide: does this sentence state the cited fact?

You have a file `R0x.jsonl`, one line per item. Each item is one sentence from a
model's report or rationale, and one fact the sentence cites. The fact is given as
`field`, `value` and `evidence` (the text the fact was taken from). Fill in
`human_grade` with one of the four words below, and `note` with anything you want to
say about the item. Judge by meaning, not by wording: synonyms and clinical equivalents
count. Do not look at the other rater's file, and do not look for the grader's file;
the point is to find out where the automatic grader is wrong.

The question for every item: **does the sentence state the cited fact with the value
recorded for it?**

| `human_grade` | Use when |
|---|---|
| `agree` | the sentence states the fact with its recorded value. A number must actually appear. If the fact is recorded as *not performed* or *not mentioned*, `agree` means the sentence says it was not assessed or not available. |
| `disagree` | the sentence states a different value: the opposite polarity, another category or number, or present/absent for a fact that was recorded as not tested. |
| `unverifiable` | the sentence refers to the fact, but you cannot tell from the sentence what value it claims. |
| `not_mentioned` | the sentence does not refer to the fact at all. The citation is dangling. |

Where an item says `"kind": "uncited"`, the sentence did not cite the fact's id; the
grader matched the fact to something the sentence asserts. The question is the same.

## Examples from `case_003`

All sentences below are real sentences from the artefact except the ones marked
*modified*, which are real sentences with one value changed.

### `agree`

| Sentence | Cited fact | Why |
|---|---|---|
| "CD5+, CD19+, CD20+, CD23+, CD200+, CD43+; CD10 negative; CD81 weak; CD79b weak; ROR1 negative." | `p_10` CD10 = Negative | "CD10 negative" is the recorded value. |
| "Summary: IGHV unmutated; TP53 aberration present." | `p_57` del_17p = Positive (evidence: "clonal loss of TP53 (at 17p13.1)") | A TP53 aberration at 17p13.1 is what del(17p) is. Clinical equivalence counts, so `agree`, even though the words del(17p) do not appear. |
| "BRAF mutation is absent and villous projections were not described, arguing against HCL." | `p_25` villous_projections = Not mentioned | The fact was never recorded, and the sentence says so ("not described"). |

### `disagree`

| Sentence | Cited fact | Why |
|---|---|---|
| "Absence of splenomegaly and lack of villous projections argue against SDRPL." | `p_25` villous_projections = Not mentioned | The report never assessed villous projections; the sentence asserts they are absent. Asserting a value for an untested fact is `disagree`. |
| *modified:* "CD5+, CD19+, CD20+, CD23+, CD200+, CD43+; CD10 positive; …" | `p_10` CD10 = Negative | Opposite polarity. |
| *modified:* "Additional comments: del(11q) not detected." | `p_55` del_11q = Positive | Opposite polarity. |

### `unverifiable`

| Sentence | Cited fact | Why |
|---|---|---|
| "The patient shows the classic immunophenotype (CD5+, CD23+) and small mature B‑cell morphology, with cytogenetic abnormalities (del11q, del17p) and high lymphocytosis typical of CLL/SLL." | `c_108` lymph = 143.2 | "High lymphocytosis" refers to the count but gives no number, so the recorded value cannot be checked against the sentence. |
| "The patient is CD5 positive and IgM negative, which excludes SMZL." | `c_109` paraprotein = Absent | "IgM negative" could mean surface IgM on flow or no IgM paraprotein; the sentence does not say which. |
| *modified:* "Morphology was reviewed." | `p_23` small_size = Positive | Refers to the domain of the fact without claiming any value. |

### `not_mentioned`

| Sentence | Cited fact | Why |
|---|---|---|
| "Small mature B cells; no prominent nucleoli." | `p_24` smear_cell = Positive | Nothing in the sentence is about smudge cells. |
| "Absence of germinal‑center markers (CD10 negative) and lack of follicular morphology make FL unlikely." | `p_23` small_size = Positive | Follicular architecture is not cell size. |
| "The patient shows the classic immunophenotype (CD5+, CD23+) and small mature B‑cell morphology, with cytogenetic abnormalities (del11q, del17p) and high lymphocytosis typical of CLL/SLL." | `c_111` lymphadenopathy = Present | The sentence cites it but never mentions nodes. |

## Practicalities

- Grade every line. Leave `human_grade` as `""` only if you genuinely cannot decide,
  and say why in `note`; blanks are counted and excluded.
- The same sentence appears several times with different facts. Grade each fact on its
  own.
- When the sentence is about one of several facts with the same field (for example two
  CD5 results from different panels), grade against the cited one; `evidence` shows
  where it came from.
- Expect about a minute per item; 300 items is an afternoon. Do them in one or two
  sittings so the standard does not drift.
- When both files are complete, the items where you and the other rater differ are
  listed; you settle those together and the agreed label is recorded separately. Your
  original labels are not changed.
