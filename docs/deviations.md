# Deviations from pre-registration

Empty until the OSF registration is published. Each entry: date, [PRE-REG]
item, what changed, why, and how results under both definitions are reported.

## Pre-registration notes (not deviations: registration not yet filed)

### 2026-10-20 — Pilot run on Claude with summarised thinking

- **What:** the first pilot (`runs/pilot`) was run against Claude Opus 5.5 through the
  direct Anthropic Messages API (`traceaudit/clients/anthropic_.py`, `--client anthropic`)
  rather than gpt-oss-120b, because no gpt-oss server was available. The user chose this
  knowingly as a pipeline exercise; the main study stays on gpt-oss-120b.
- **Spec 07 §3 exemption:** that section requires a client to refuse a response that carries
  only a *summary* of the reasoning. Claude never returns its raw chain of thought; with
  `thinking: {type: "adaptive", display: "summarized"}` it returns a readable summary. The
  Anthropic client is therefore exempt from the summary-only refusal, marks every trace with
  the parse warning `SUMMARISED_THINKING`, and records `model.reasoning_kind: "summarized"`
  in the manifest so no pilot trace can be mistaken for a raw trace.
- **Sampling:** the model rejects `temperature`, `top_p`, `top_k` and has no seed, so the
  manifest records `model.sampling: "model-default"`; per-trace seeds are recorded but not
  applied. Runs are samples, as spec 07 §6 already states.
- **Effort:** study efforts low/medium/high map one-to-one onto `output_config.effort`.
- **Consequence:** grounding, disclosure and hedging rates measured on summarised thinking
  are **not comparable** to the planned gpt-oss study, and pilot traces are not reused in
  the main analysis (spec 15 §3). The pilot is used only to exercise the pipeline: answer
  format compliance, base stability, extractor recall labelling sample, reasoning length.
