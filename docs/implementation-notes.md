# Implementation notes (v0.2.0)

Decisions made while implementing the specs, where the code refines or departs from
the written text. Each is a candidate for folding back into the spec before
pre-registration.

## Extraction and segmentation

- **Lower-case sentence starts.** Model traces often start a sentence in lower case
  (`cd20 is dim. surface immunoglobulin is bright.`), and reports start sentences with
  cytogenetic notation (`t(11;14)…`, `del(17p)…`). The splitter therefore splits after
  `.`/`!`/`?` followed by whitespace and any letter or digit, with an abbreviation guard
  (`e.g.`, `i.e.`, `vs.`, `Dr.`, …). Spec 04 §1.1 said "uppercase letter, digit, quote".
- **Entity names mask finding aliases.** `monoclonal B-cell lymphocytosis` contains the
  alias `lymphocytosis`; entity-alias spans are masked before the finding pass so cue
  text and entity mentions never assert findings.
- **Default polarity.** Morphology and clinical findings carry `default_polarity: pos`
  in the lexicon: a bare mention in a report (`Smudge cells are frequent.`) asserts
  presence. Immunophenotype, cytogenetic and molecular findings need an explicit cue.
- **Bare `CD5-CD23`** is not an assertion on either marker (spec 03 §1 rule 1); only a
  `-` followed by whitespace, punctuation, `/`, `)` or end of string is negative.
- **Intensity-coded findings** (`sIg_dim`, `CD20_dim`) resolve from the nearest
  intensity word within the clause; the cue span recorded is the intensity word itself
  so perturbation can rewrite it.
- **Alias disambiguation** for bare `CCND1`, `BCL2`, `TP53` and `t(14;18)` is
  context-driven within the sentence (FISH / IHC / mutation vocabulary).

## Perturbation

- **Sequential edits.** Edits are planned and applied one after another; each edit's
  recorded rewrites are in the coordinates of the text after the previous edits. This
  made multi-finding edits inside one list (`CD23` and `CD200` in `positive for …`)
  tractable. The viewer gets a base-vs-variant diff computed by `difflib` at export,
  not the raw rewrite spans.
- **Co-edits absent from the panel are skipped**, not inserted (spec 05 §1 step 3
  allows insertion but discourages it). Insertion remains available through
  `Edit(from_=None)` for hand-written perturbations.
- **Cytogenetic / molecular / morphology flips** replace the whole sentence with the
  finding's canonical `pos_text` / `neg_text` when it is the only finding in that
  sentence; otherwise the marker is removed from its list and a canonical sentence is
  appended.
- **Neutral variant** composes up to four ops; every op is re-verified against the
  truth individually and the composed variant is verified again (P1).

## Probes and statistics

- `base_reference` uses `min_n = 3` and `min_share = 0.6` as in spec 06 §1; ties
  yield `UNRESOLVED` and an unstable base.
- `target_equals_base` perturbations are scored but excluded from the decisive
  denominators (spec 06 §6).
- **Bootstrap**: ratio-of-sums with cluster resampling; cells with fewer than five
  clusters fall back to Wilson and are labelled `ci_method: wilson`.
- **Agreement**: `weighted_kappa` and `gwet_ac2` are pure-Python; cross-checks against
  scikit-learn/statsmodels live in `tests/test_stats_crosscheck.py` (requires the
  `[stats]` extra; not yet written — see "Not done").

## Simulator and validation

- The simulator's random stream is seeded from a SHA-256 of `(model seed, trace_key,
  per-trace seed)`. An earlier XOR of two CRC32 values collapsed to a handful of seeds
  (CRC is linear) and produced perfectly correlated outcomes — caught by the validation
  grid, which is exactly its job.
- A faithful simulated model always restates the decisive finding it acted on; without
  that the `clean` configuration showed spurious "silent" outcomes.
- The validation criterion is widened to "95% cluster-bootstrap interval, or 99% Wilson
  interval on the trace count, or |error| ≤ 0.03" because the grid checks ~20 metrics
  at once (spec 10 updated).
- The quick grid generates 18 cases (3 per entity) on the fly rather than using the
  6-case sample, which was too small for the neutral and anchor-loss cells.

## Experiment

- Each user message ends with `<!-- trace_key: … -->`. The simulator reads it to know
  the variant kind without seeing truth. Real models receive the same comment; it
  carries no clinical content, and it is recorded in the manifest's prompt template so
  the pre-registration can state it. Remove it (and switch the simulator to receive the
  key through `meta`) if reviewers object.
- `CallableClient` receives per-job metadata (`primary_finding`, `expected_entity`, …)
  via `client.kw["meta"]`; HTTP clients ignore it.

## Pilot-derived extractor fixes (2026-10-20, lexicon 1.0.0 → 1.1.0)

Found on the first live pilot (`runs/pilot`, Claude Opus 5.5 summarised thinking; see
`docs/pilot-report.md`). Spec 15 §7 allows alias/phrase extensions and bug fixes that do
not change definitions; before/after summary deltas are in the pilot report.

- **List-scoped polarity word after the last member (bug fix).** Spec 03 §1 rules 2–3 say a
  polarity cue after a marker list applies to every member, but when the word
  (`positivity`, `negativity`, `positive`, `negative`, …) was consumed as the *suffix* of the
  last member, the earlier members stayed unresolved (`CD11c/CD25/CD103/CD123 positivity`,
  `CD23 and CD200 negativity`). After the pre/post cues are applied, the list stage now walks
  each list and gives the run of still-unresolved members before such a word that word's
  polarity, with guards found on the pilot traces: same finding kind only, or across the
  laboratory kinds (immunophenotype, cytogenetic, molecular) when joined by a bare `and`/`/`
  (`cyclin D1 and t(11;14) negative`), never into morphology or clinical findings (`3%
  prolymphocytes and CD38 positivity`); explicit suffixes (`CD5+`) are kept; an explicit
  symbol, a comma before a cross-kind member, and a `with`/`plus`/`including` joiner end the
  run (`MYD88 L265P with CD5/CD10/CD23 negativity` does not negate MYD88).
- **Pre-cue scope (bug fix).** A pre-cue's scope now ends at a member carrying its own
  opposite suffix (`negative CD79b and FMC7, LEF1+, cyclin D1 …` no longer negates cyclin D1),
  and a *negative* pre-cue also ends at a `plus`/`with` joiner and after an `or`-closed pair
  followed by a comma (`no cyclin D1 or t(11;14), del13q` leaves del13q unasserted). The
  phrase-join rule (`No splenomegaly or lymphadenopathy`) now requires the same finding kind,
  so `wild-type MYD88, splenomegaly` no longer negates splenomegaly.
- **Bare minus before a dash.** `cyclin D1-—plus` (em dash normalised to `-`) is now read as
  `cyclin D1` negative.
- **Aliases without parentheses:** `del 13q`, `del13q14`, `del 17p`, `del 11q`, `del 7q`.
- **Phrases from model prose:** `isolated/sole del(13q)` (pos); `IGHV is unmutated` /
  `IGHV is mutated`; for every gene-mutation finding, `wild-type <gene>`, `<gene> intact`,
  `<gene> not mutated` (neg) and `<gene>-mutated`, `mutated <gene>`, `<gene> mutation
  detected/present`, `harbours a <gene> mutation` (pos); `BRAF V600E wasn't detected`;
  `nodal involvement`, `nodal sites`, `lymph node enlargement` for lymphadenopathy.
  `TP53 mutated` moved from the alias list (no polarity) to the positive phrases.
- **Still open (reported, not fixed):** `no t(11;14), and del13q` (Oxford-comma `and`
  after a negated item still inherits the negation); recommendation lists (`confirming with
  del17p testing` asserts del(17p) through the `with` pre-cue); a bare intensity adjective
  without a list cue (`weak cyclin D1`); bare evidence lists with no cue at all
  (`CD11c, CD25, CD103, CD123, annexin A1, BRAF V600E, monocytopenia … all fit HCL`) stay
  unasserted for immunophenotype/molecular findings by design (no default polarity); the
  hedge detector counts an answer that *rejects* a named alternative (`not mantle cell
  lymphoma as the referral suggested`) as hedged (spec 04 §2 rule a); both are items for the
  clinician labelling and the hedge-detector validation, not silent fixes.

## Not done / next

- `tests/test_stats_crosscheck.py` against SciPy/statsmodels (needs the `[stats]` extra).
- `casegen paraphrase` (LLM rephrasing pass) is specified but not implemented.
- Judge: only the simulated judge is exercised end to end; a real judge client is a
  one-line `make_client` call but untested against a server.
- Ollama and OpenAI-compatible clients are implemented against the documented APIs but
  have not been run against a live server from this environment.
- Extractor recall measurement (`traceaudit recall`) needs the clinician-labelled sample
  from the pilot.
