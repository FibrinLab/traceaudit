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

## Examples from the synthetic artefact `SYN-003`

The sentences below come from `tests/fixtures/synthetic_trace_SYN-003.md`, a generated
artefact with invented vocabulary (markers `mk1`..`mk16`, shapes, `GENEnn` variants) and the
structure of a real engine trace. Rows marked *modified* change one value.

### `agree`

| Sentence | Cited fact | Why |
|---|---|---|
| "mk1 positive; mk4 positive; mk2 positive; mk3 positive; mk5 weak; mk6 positive; mk7 strong; mk8 negative; mk9 positive; mk10 negative" | `p_10` mk10 = Negative | "mk10 negative" is the recorded value. |
| "Summary: ig mutated; del(3q) positive; GENE21 variant positive; GENE27 variant positive; GENE28 variant not detected" | `p_53` GENE28_variant = Negative | "Not detected" is the negative result; the words differ from the recorded value, the meaning does not. |
| "Small mature forms with shape_g and occasional shape_c and shape_e forms; shape_h forms present; no shape_f" | `p_22` shape_f = Negative | "No shape_f" states the recorded absence. |

### `disagree`

| Sentence | Cited fact | Why |
|---|---|---|
| *modified:* "mk1 positive; mk4 positive; …; mk10 positive" | `p_10` mk10 = Negative | Opposite polarity. |
| *modified:* "Additional comments: del(3q) not detected." | `p_55` del_3q = Positive | Opposite polarity. |
| *modified:* "No shape_i forms were seen, which argues against K7." | `p_25` shape_i = Not mentioned | The report never assessed shape_i; the sentence asserts a value for an untested fact. |

### `unverifiable`

| Sentence | Cited fact | Why |
|---|---|---|
| "The panel (mk1, mk4, mk6, mk7) and morphology (shape_g forms with occasional shape_c) fit K1, supported by ig mutation and del(3q)." | `c_108` level_e = 90.5 (as cited in the rationale) | The sentence cites a count but gives no number, so the recorded value cannot be checked. |
| "marker_x absent and mk4 positive argue against K4." | `c_109` marker_x = Absent | "Absent" matches, but the sentence is about K4's requirement, not the patient's result; grade what the sentence claims about the fact. If you read it as a claim, `agree`. |
| *modified:* "Morphology was reviewed." | `p_23` shape_g = Positive | Refers to the domain of the fact without claiming any value. |

### `not_mentioned`

| Sentence | Cited fact | Why |
|---|---|---|
| "The panel (mk1, mk4, mk6, mk7) and morphology (shape_g forms with occasional shape_c) fit K1, supported by ig mutation and del(3q)." | `p_2` mk2 = Positive | The rationale cites mk2 in support, but the sentence never mentions it. |
| "mk10 is negative, which K2 requires positive." | `p_23` shape_g = Positive | Nothing in the sentence is about shape_g. |
| "GENE05 variant negative and no shape_i forms described." | `p_22` shape_f = Negative | shape_f is not shape_i. |

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
