# traceaudit — Specifications

Detailed specifications for the `traceaudit` package, the Trace Viewer, and the
synthetic study. The parent document is [docs/00-project-spec.md](../docs/00-project-spec.md)
(Project Specification v0.1). Where the two disagree, the parent document sets
scope and the documents here set behaviour.

## Index

| # | Spec | Covers |
|---|---|---|
| 01 | [Data model](01-data-model.md) | Record types, identifiers, `trace_key`, file layout, schema versioning |
| 02 | [Lexicon](02-lexicon.md) | Findings, aliases, polarity vocabulary, discriminator table, linked findings, confusion table |
| 03 | [Extraction](03-extraction.md) | Deterministic assertion grammar, polarity resolution, spans, conflicts |
| 04 | [Segmentation and grounding](04-segmentation-grounding.md) | Claim splitting, claim typing, grounding labels, verifier interface |
| 05 | [Perturbation](05-perturbation.md) | Decisive, neutral, anchor-loss and authority edits; `apply()`; validity checks |
| 06 | [Probes](06-probes.md) | Counterfactual and authority scoring, base reference, disclosure rules |
| 07 | [Clients and harmony](07-clients-harmony.md) | Client interface, Ollama / OpenAI-compatible / callable, harmony parsing, effort |
| 08 | [Experiment and manifest](08-experiment-manifest.md) | Run orchestration, seeding, resumption, manifest, CLI |
| 09 | [Statistics](09-stats.md) | Wilson, case-clustered bootstrap, mixed-effects export, agreement |
| 10 | [Simulation and probe validation](10-simulate-validation.md) | `SimulatedModel` faults, recovery criteria |
| 11 | [Judge](11-judge.md) | Rubric anchors, error taxonomy, judge prompt and output, calibration |
| 12 | [Export bundle](12-export-bundle.md) | Viewer JSON bundle, sharding, ratings export |
| 13 | [Trace Viewer](13-viewer.md) | Views, components, blinding, rating persistence, reasoning map, figures |
| 14 | [Case generation](14-case-generation.md) | Structured truth → SIHMDS-style reports → review |
| 15 | [Study protocol](15-study-protocol.md) | Sampling, rating study, pre-registration contents, deviations |
| 16 | [Testing and CI](16-testing-ci.md) | Test plan, invariants enforced in CI, release gates |

## Scope note

traceaudit is a domain-agnostic trace-analytics engine; these specifications were
written for its reference study (mature B-cell neoplasm diagnosis) and use that
domain's vocabulary in examples. Everything domain-specific is a *domain pack*
(`traceaudit/domains/<name>/`: a lexicon, optional generator and sample data);
specs 14 and 15 describe the reference study's case generation and protocol and
do not apply to other domains.

## Implementation status (20 Oct 2026)

All sixteen specs are implemented in `traceaudit/` and `viewer/`; see
[docs/implementation-notes.md](../docs/implementation-notes.md) for the places where the
code refines the text and for what is still open (statistics cross-check tests, the
`casegen paraphrase` pass, live model and judge clients). Run `traceaudit demo` and
`traceaudit validate-probes --grid quick` to exercise everything without a model.

## Conventions

- **MUST / SHOULD / MAY** as in RFC 2119.
- **[PRE-REG]** marks a definition that will be frozen in the OSF pre-registration.
  After registration, a change to a [PRE-REG] item MUST be recorded in
  `docs/deviations.md` and reported in the paper.
- **[DRAFT-CLINICAL]** marks clinical content (discriminator table, edit catalogue,
  rubric anchors) that is a starting point and MUST be signed off by a
  haematologist before use in the study.
- Spec version tracks the package version. Each spec carries a `Status` line.
- British English throughout, including identifiers that appear in UI text.
  Code identifiers use American spelling only where a dependency forces it.

## Glossary

| Term | Meaning |
|---|---|
| Case | One synthetic patient: a clinical summary and four laboratory reports plus a structured truth |
| Finding | A named, binary (pos / neg) feature a report can assert, e.g. `CD5`, `t_11_14`, `IgM_paraprotein`. "Marker" is used loosely for immunophenotype findings |
| Truth | The map `finding_id → pos|neg` for a case; the oracle for grounding |
| Entity | A WHO-HAEM5 diagnosis label in the answer space, e.g. `CLL_SLL`, `MCL` |
| Variant | A rendering of a case: `base` or one perturbed version |
| Perturbation | A specified set of finding edits, or an authority cue, producing one variant |
| Primary finding | The finding whose edit defines a decisive or anchor-loss perturbation |
| Co-edit | The same biological fact edited in another modality (e.g. `cyclin_D1` by IHC and `t_11_14` by FISH) |
| Linked finding | A finding clinically associated with the primary one but not edited |
| Run | One sampled model call for a given case, variant and effort (index 0..N-1) |
| Effort | gpt-oss reasoning effort: `low`, `medium`, `high` |
| Trace | The raw reasoning (harmony `analysis` channel) and the final answer for one run |
| Claim | One sentence-level unit of the trace, typed factual / knowledge / inferential / other |
| Assertion | One (finding, polarity) pair extracted from a claim or report |
| `trace_key` | `case_id|variant|effort|run`, the universal join key |
| Bundle | The JSON the viewer loads, produced by `traceaudit export` |
