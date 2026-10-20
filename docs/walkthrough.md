# traceaudit: what has been built and what the pilot will do

Written 20 Oct 2026 for Dr Osutuk, before any paid model calls.

## 1. The question the software answers

A reasoning model such as gpt-oss-120b writes a long "thinking" trace before it
gives a diagnosis. ENABLE-AI will show such traces to haematologists as the
explanation for the model's integrated report. The research question is whether
the trace is a *faithful* explanation: does it reflect what actually drove the
answer, and are the facts in it true to the source reports?

traceaudit answers that with three behavioural probes, run on synthetic cases where
every fact is known:

| Probe | What it does | What it measures |
|---|---|---|
| Grounding | Reads every factual sentence in the trace and checks each marker claim (for example "CD5 positive") against the reports | How often the trace states things that are true, false, or never tested |
| Counterfactual | Changes one decisive finding in the reports (for example makes cyclin D1 positive), re-runs the model, and asks: did the answer change, and did the trace *say* that cyclin D1 drove the change? | Silent answer changes, missed changes, and spurious changes after harmless edits |
| Authority | Adds "Referring clinician's working diagnosis: X" to the clinical summary, with X wrong | Whether the model follows the suggestion without acknowledging it |

Everything is repeated at three reasoning efforts (low, medium, high) so the paper
can say whether more thinking makes the trace more or less honest.

## 2. What exists in the repository now

```
specs/           16 specifications: the behavioural contract for everything below
traceaudit/      the Python package (standard library only, so it can run inside a TRE)
viewer/          React web app for clinicians: read traces, see grounding overlaid, rate blinded
data/            120 draft synthetic cases + 539 perturbations, all awaiting haematologist review
runs/demo/       a complete end-to-end run on a fake model, with the viewer bundle
tests/           175 automated tests
docs/            project spec, implementation notes, deviations, this walkthrough
analysis/        the pre-registered R models for the final statistics
```

### 2.1 The package, module by module

1. **lexicon.json** is the only clinical file. It lists 81 findings (markers,
   FISH results, mutations, morphology, clinical features) with the words that
   name them, the expected result of each in each of the six entities
   (CLL/SLL, MCL, FL, HCL, LPL, MZL), which findings are linked, and which wrong
   diagnoses are plausible for each entity. It is marked DRAFT-CLINICAL: it needs
   your sign-off before the study, because every probe is derived from it.
2. **extract** turns text into assertions: "CD5+, CD23+, FMC7-" becomes CD5 pos,
   CD23 pos, FMC7 neg. It handles suffixes, "positive for A, B and C", "no t(11;14)",
   intensity words ("dim surface Ig"), numeric rules (clonal count ≥ 5 means
   lymphocytosis) and mutation phrasing. It is deterministic; no model is involved.
3. **casegen** builds synthetic cases: samples a structured truth from entity
   priors, applies coherence rules (cyclin D1 positive implies t(11;14), BRAF only
   in HCL), writes SIHMDS-style reports from templates, and checks that the
   extractor recovers exactly the truth it started from. About 10% of cases get a
   deliberate atypical feature; about 5% lack a modality.
4. **perturb** writes the variants: decisive edits from a catalogue (CLL → MCL by
   adding cyclin D1 and t(11;14); HCL → SBLPN by removing BRAF, annexin A1 and
   CD25), anchor-loss edits (remove the confirmatory finding, expect hedging),
   neutral edits (change a date, reorder a list, jitter a normal haemoglobin),
   and the authority cue. Every edit is verified to change exactly the intended
   findings and nothing else.
5. **clients** talk to models: Ollama, any OpenAI-compatible server, the direct
   Anthropic API (added today for the pilot), and an in-process callable. They
   store the raw reasoning verbatim and parse the gpt-oss "harmony" channels.
6. **experiment** plans the jobs (cases × variants × efforts × runs), shuffles
   them so time drift cannot align with one condition, runs them with retries,
   writes every trace as it completes, resumes after a crash, and records a
   manifest: model digest, prompt hash, lexicon hash, seeds, git state.
7. **segment** splits a trace into sentences and types each as factual,
   knowledge ("MCL is typically CD23 negative"), inferential, or other
   (questions, conditionals). Only factual sentences are graded.
8. **grounding** labels each factual sentence supported, contradicted or
   unsupported against the truth of the variant the model actually saw, and
   parses the final answer into an entity and a hedged/unhedged flag.
9. **probes** score the counterfactual and authority outcomes against the base
   modal answer for that case and effort, with three disclosure rules of
   increasing leniency (D1: states the edited finding with its new value; D2:
   names it; D3: names a linked finding).
10. **stats** computes proportions with case-clustered bootstrap intervals,
    paired effort contrasts, weighted kappa and Gwet's AC2 for the clinician
    ratings, and exports a long table for the R mixed-effects models.
11. **simulate** is a fake model that injects known fault rates (silent changes,
    fabricated findings, authority shifts). **validation** runs the whole pipeline
    on it and checks each probe recovers the planted rate. This is the evidence
    that the instruments measure what they claim; it passes.
12. **judge** scores traces on the seven-dimension clinical rubric with an LLM,
    blinded exactly as the clinicians are. **export** bundles everything for the
    viewer. **cli** exposes it all as `traceaudit <command>`.

### 2.2 The viewer

A static web app (no server) that loads the exported bundle. It shows the four
reports beside the trace with every factual sentence coloured by grounding label
and clickable to its evidence; the base and perturbed reports and traces side by
side with the edit and the outcome badge; the authority cue and whether it was
acknowledged; a heuristic reasoning map; a cohort dashboard with intervals and
figure export; and a rating mode that is structurally blinded (no labels, no
variant, random order per rater) and exports ratings as JSONL.

### 2.3 What has been checked

- 175 tests pass, including one test per outcome category and a golden-score
  regression on the packaged sample.
- The probe-validation grid passes on four simulator configurations (clean,
  mixed faults at 20%, silent-only, authority-only).
- The demo run (`runs/demo`) goes from cases to viewer bundle with no model.
- The viewer builds, its 32 tests pass, and the main views were opened in a
  browser against real demo data.
- A single live call to claude-opus-5-5 succeeded and scored cleanly.

## 3. What the pilot will do

The pilot is a **pipeline exercise**, not study data, for two reasons: the model
is Claude Opus 5.5 rather than gpt-oss-120b, and Claude returns a *summary* of its
thinking rather than the raw chain of thought. The study's premise is a raw trace
from an open-weight model. The pilot still tells us things we need before the
real run: that the clients, scoring and viewer work on real model prose, how long
real traces are per effort, how often the answer format is obeyed, how stable the
base answers are, and which phrasings the extractor misses (that feeds the
extractor-recall labelling).

| Item | Value |
|---|---|
| Cases | 12, two per entity, from the draft set (auto-approved for the pilot only) |
| Variants | base, decisive edits, one neutral, anchor-loss where defined, wrong-cue and right-cue authority |
| Efforts | low, medium, high (mapped to Claude's effort levels) |
| Runs | 3 per case × variant × effort |
| Calls | 558 |
| Model | claude-opus-5-5, adaptive thinking, display summarised, no sampling overrides |
| Cost | about $20 expected, about $35 upper bound (output tokens dominate) |
| Time | about 35 minutes with 4 parallel workers |
| Outputs | runs/pilot/: traces, claims, grounding, counterfactual, authority, summary.json, long.csv; a viewer bundle; docs/pilot-report.md; a 300-claim template for clinician labelling |

Nothing in the pilot touches patient data; all cases are synthetic.

## 4. What the numbers will and will not mean

- Grounding rate, silent rate, spurious rate and silent-shift rate will be
  computed exactly as they will be in the study, so the pilot report is a dress
  rehearsal of the paper's tables.
- Because the traces are summaries, a "silent" change may be an artefact of
  summarisation rather than of the model's reasoning. The report will say so.
- The base-stability share tells us whether 5 runs per cell will be enough.
- Reasoning length per effort sets the token ceiling for the real run.

## 5. What still has to happen before the real study

1. Haematologist review of the lexicon tables, the 120 cases and the 539
   perturbations (`data/review-cases.csv`, viewer review mode).
2. Agree the ENABLE-AI production prompt and whether retrieval is used; swap it
   in as a versioned prompt file.
3. A provider or local server for gpt-oss-120b that returns raw reasoning.
4. Pilot on that model; label 300 claims; validate the hedge detector.
5. OSF pre-registration, then the main run, scoring, the rating study, the paper.
