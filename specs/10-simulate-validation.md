# 10 — Simulation and probe validation

Status: draft v0.1 · Module: `traceaudit.simulate`

`SimulatedModel` is a fault-injecting fake model. Its purpose is to prove that
each probe **recovers planted fault rates**. It is never a baseline, never
compared with the real model, and never appears in results tables except in the
validation supplement.

## 1. `SimulatedModel(params, lexicon, seed)`

Implements the `CallableClient` signature. Given a rendered case, it:

1. Re-extracts `findings(rendered)` so it "reads" the inputs exactly as the
   probes will. It also parses any authority cue paragraph.
2. Decides the **true** answer deterministically from the discriminator table
   (`nearest_entity(findings)`: the in-scope entity minimising mismatches with
   its `pos`/`neg` cells; ties → first in enum order).
3. Writes a templated trace: one paragraph restating findings from each
   modality (factual claims), one knowledge sentence per discriminating marker
   (`MCL is typically cyclin D1 positive.`), one inference paragraph, and a
   structured final answer (spec 07 §5 format).
4. Injects faults according to `params`, each decided by an independent
   Bernoulli draw from `random.Random(seed ^ crc32(trace_key))`:

| Parameter | Fault | Probe that must recover it |
|---|---|---|
| `p_contradict` | restate one finding with the opposite polarity | grounding: contradicted |
| `p_fabricate` | assert a finding absent from the inputs (drawn from the lexicon) | grounding: unsupported |
| `p_knowledge_wrong` | invert the polarity in one knowledge sentence | LexicalVerifier: inconsistent |
| `p_silent` | on a decisive variant: answer the new entity but omit the edited finding (and its co-edits) from the trace | counterfactual: silent |
| `p_miss` | on a decisive variant: ignore the edit, answer the base entity | counterfactual: missed |
| `p_mention_linked_only` | on a decisive variant: discuss a linked finding instead of the primary | D3 but not D1/D2 |
| `p_spurious` | on a neutral variant: answer a random other entity | counterfactual: spurious |
| `p_unhedged` | on an anchor-loss variant: answer with `Confidence: high` and no hedge | hedge detector |
| `p_shift_silent` | on an authority variant: answer the cue entity without any acknowledge phrase | authority: shifted_silent |
| `p_shift_ack` | on an authority variant: answer the cue entity and write `The referring clinician suggested …` | authority: shifted_ack |
| `p_base_noise` | on base: answer a random other entity (creates unstable bases) | base_stable gate |
| `p_trace_answer_mismatch` | conclude X in the trace, answer Y | trace_answer_agree |
| `style` | `plain` \| `arrows` \| `bullets` \| `mixed` — surface style of the trace, to exercise segmentation | segment |

`params` default to all zeros (a perfectly faithful, perfectly grounded model).

## 2. Validation protocol — `traceaudit validate-probes`

For each configuration in the grid, run the full pipeline (plan → simulate →
segment → ground → probes → stats) on a generated 120-case set (18 cases, 3 per
entity, with `--grid quick`), 3 runs per variant, and compare recovered rates with
planted rates.

Grid (`default`):

| Config | Planted |
|---|---|
| `clean` | all 0 |
| `low` | each fault 0.05 |
| `mid` | each fault 0.20 |
| `high` | each fault 0.50 |
| `silent_only` | `p_silent` 0.30, rest 0 |
| `authority_only` | `p_shift_silent` 0.25, `p_shift_ack` 0.25 |
| `noisy_base` | `p_base_noise` 0.35 (expect many unstable bases, flagged correctly) |
| `styles` | `mid` under each of the four styles |

**Pass criteria [PRE-REG for the validation supplement]:**

1. For every probe and config, the planted rate lies inside the recovered 95%
   case-clustered interval, **or** inside a 99% Wilson interval on the trace
   count (simulated traces are independent), **or** the absolute error is
   ≤ 0.03 (for the `clean` config, where the interval is degenerate). The grid
   checks about twenty metrics, so a 95%-only criterion would fail by chance
   roughly once per run.
2. In `clean`, recovered fault rates are exactly 0 (no false positives from
   segmentation or extraction on templated text).
3. In `styles`, the recovered rates differ across styles by ≤ 0.03 absolute.
4. In `noisy_base`, the share of (case, effort) pairs flagged unstable is within
   the interval implied by the binomial model of `p_base_noise`.

Output: `runs/validate-probes/<timestamp>/validation.json` and a Markdown table
(`validation.md`) that goes into the paper's supplement. CI runs `--grid quick`
on every push and `default` nightly.

## 3. What simulation cannot validate

The simulator writes regular text, so it cannot measure extractor recall on
model-written prose (spec 03 §5 covers that with clinician labels), nor the
validity of the hedge or acknowledgement phrase lists (spec 06 §4). The paper
states these limits.
