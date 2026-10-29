# Changelog

## Unreleased

- Provenance hashes (`traceaudit.provenance`): each trace records the sha256 of the exact prompt sent, of its raw
  reasoning and of its raw answer (imports add the artefact hash); the manifest records `provenance.inputs_sha256`
  over the prompt, cases, perturbations and lexicon hashes, the value to pre-register. `traceaudit manifest verify
  RUN [--cases --perturbations]` recomputes all of them, rebuilding the prompts from the inputs when given.
  Ledger manifests now record `render.evidence_policy`.
- Grader validation (spec 20): `traceaudit ledger sample` writes a stratified sample of ledger citations as a
  grader file and blind per-rater files; `traceaudit ledger agreement` reports inter-rater (Cohen's kappa, Gwet AC1)
  and grader-vs-consensus agreement with case-clustered bootstrap CIs and the acceptance verdict. New `stats.cohen_kappa`,
  `stats.gwet_ac1`, `stats.per_class_pr`; `docs/labelling-guide.md` for raters.
- The text path is an adapter onto the fact ledger (`traceaudit.ledger_adapters`): documents become facts
  with evidence spans, factual claims become cited segments. `POST /api/analyse` now returns the ledger
  result plus `documents[]` with fact spans, `lexicon`, `answer`, `oracle`, `warnings`, `domain`; the
  `claims`, `grounding`, `map` and `parsed_answer` keys are gone. Ledger metrics gain `grounding_rate` and
  `uncited_assertions`. The Analyse-a-trace page renders the ledger blocks under a documents pane whose
  highlights are the facts; the single-trace bundle adapter and its "Open in trace views" button are removed.

## 0.2.0 (2026-10-20)

First public release.

- Specifications for the study and the software (`specs/`).
- `traceaudit` package, standard library only: lexicon, extractor, segmentation and grounding,
  perturbation engine, counterfactual and authority probes, model clients (Ollama, OpenAI-compatible,
  Anthropic, in-process) with harmony parsing, experiment runner with manifests, statistics
  (Wilson, case-clustered bootstrap, weighted kappa, Gwet AC2), simulator and probe-validation grid,
  LLM judge, viewer bundle export, synthetic case generator and CLI.
- `traceaudit serve`: HTTP service with analyse-a-trace, token-scoped audit jobs, uploads, an
  operator key with per-job and daily call caps, and static hosting of the viewer.
- Trace Viewer (React + TypeScript): grounding, counterfactual, authority and reasoning
  constellation views, Lexicon Atlas and Outcome River cohort dashboard, blinded rating mode,
  Analyse and Jobs pages.
- Draft synthetic case set (120 cases, 539 perturbations) awaiting haematologist review.
- Docker image, Fly.io and Render configurations.
