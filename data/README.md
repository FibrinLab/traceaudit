# Synthetic case set (draft v1)

Generated with `traceaudit casegen --per-entity 20 --seed 20261020` and
`traceaudit perturb --seed 20261020` on 20 Oct 2026. Every record has
`review.status: draft`: nothing here has been reviewed by a haematologist yet, and
`traceaudit run` will refuse these inputs until they are approved.

| File | Contents |
|---|---|
| `cases.jsonl` | 120 cases, 20 per entity (CLL/SLL, MCL, FL, HCL, LPL, MZL), ~10% discordant, ~5% incomplete |
| `perturbations.jsonl` | decisive, neutral, anchor-loss and authority variants for every case |
| `review-cases.csv` | one row per case for review; fill `status` (`approved`/`rejected`) and `notes`, then `traceaudit review-sheet data/cases.jsonl --import-csv review-cases.csv --reviewer R01 --date YYYY-MM-DD` |
| `priors.json` (packaged) | the sampling priors used; [DRAFT-CLINICAL] |

Invariant C1 (`findings(render()) == truth`) and P1 (perturbation truth consistency)
hold for every record (`traceaudit validate data/cases.jsonl --perturbations data/perturbations.jsonl`).
The lexicon version is recorded in each run manifest.

Licence: CC BY 4.0 once released.
