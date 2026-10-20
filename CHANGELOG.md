# Changelog

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
