# 14 — Synthetic case generation

Status: draft v0.1 · Module: `traceaudit.casegen` (dev-time tool, not a runtime module)

Target: 120 approved cases, 20 per entity, ≈ 15% discordant or incomplete,
every one passing invariant C1, every one reviewed by a haematologist.

## 1. Pipeline

```
entity priors (lexicon + casegen/priors.json)
  → sample structured truth           (casegen.sample_truth)
  → render SIHMDS-style reports        (casegen.render_reports, templates)
  → optional paraphrase pass           (casegen.paraphrase, LLM, then C1 re-check)
  → validate (C1, C2, coherence)       (schema.validate_case)
  → review queue                       (viewer "case review" mode or spreadsheet export)
  → approved → data/cases.jsonl
```

Everything is seeded; `casegen --seed N` regenerates the same drafts.

## 2. Structured truth sampling

`priors.json` gives, per entity (and subtype), for every finding in the
discriminator table: `P(pos)` for `pos`/`neg` cells (defaults 0.95 / 0.05) and
an explicit probability for `var` cells (e.g. `CLL_SLL.CD38: 0.35`,
`CLL_SLL.del_13q: 0.55`, `MCL.SOX11: 0.90`, `FL.t_14_18_BCL2: 0.85`,
`HCL.BRAF_V600E: 0.97`, `LPL.MYD88_L265P: 0.90`). **[DRAFT-CLINICAL]**: the
priors file ships with literature-informed placeholders and is part of the
sign-off.

Per case:

1. Choose `subtype` where applicable (MZL: SMZL 0.45, NMZL 0.25, EMZL 0.30;
   LPL: WM 0.8).
2. Choose the **panel**: which findings are reported. A modality's default
   panel is fixed per template (e.g. PB flow panel: CD5, CD10, CD19, CD20,
   CD22, CD23, CD38, CD43, CD79b, CD200, FMC7, sIg, kappa/lambda; extended HCL
   panel adds CD11c, CD25, CD103, CD123). Cytogenetics panel is entity-driven
   (CLL FISH panel; MCL/FL FISH; SMZL del(7q)). Molecular panel: targeted NGS
   list by entity. Findings outside the panel are **absent from truth** (not
   `neg`), so the model's assertions about them are `unsupported`.
3. Sample each panel finding from the priors.
4. **Coherence repair**: enforce biological couplings so a case is never
   internally impossible: `t_11_14 pos → cyclin_D1 pos`; `cyclin_D1 pos and
   t_11_14 neg → CCND2_rearr considered (prob 0.3) else t_11_14 set pos`;
   `BRAF_V600E pos → hairy_cells pos`; `IgM_paraprotein pos → light_chain_restricted
   pos`; `lymphocytosis neg and entity CLL_SLL → entity remains CLL_SLL only if
   lymphadenopathy or cytopenias pos, else resample`.
5. **Discordance** (target 10% of cases): with probability 0.10 flip one `var`
   or weak-prior finding to its atypical value from a per-entity whitelist
   (`CLL_SLL: CD23 neg`, `MCL: CD23 pos`, `MCL: SOX11 neg`, `FL: CD10 neg`,
   `MZL: CD5 pos`, `HCL: CD25 neg`, `LPL: MYD88_L265P neg`) and set
   `flags.discordant = true`, `flags.atypical_features = [...]`.
6. **Incompleteness** (target 5%): with probability 0.05 drop one of
   cytogenetics or molecular (report text `Not performed.`), set
   `flags.incomplete = true`, `flags.missing_modalities`.
7. Draw demographics and numbers: age by entity-specific normal (CLL 72±9,
   MCL 68±8, FL 63±10, HCL 58±10, LPL 70±9, MZL 66±10, clamped 40–88), sex by
   entity ratio, counts consistent with truth (`lymphocytosis pos` → clonal B
   count log-uniform 5.5–120; `neg` → 1.0–4.9; HCL `monocytopenia pos` →
   monocytes 0.0–0.15), Hb/platelets consistent with `cytopenias`.

## 3. Report rendering

Templates per modality and specimen type, SIHMDS style: terse, headed,
present-tense findings, standard phrasing. Each template is a list of sentence
slots; a slot renders a finding set in one of the grammar forms the extractor
supports (suffix lists, `positive for … / negative for …`, phrase forms for
cytogenetics/molecular), chosen by seed so that forms vary across cases.

Example (flow, PB):

> Flow cytometry, peripheral blood. Gating on CD19+ events (84% of lymphocytes).
> A clonal B-cell population is present, kappa light-chain restricted with dim
> surface immunoglobulin. Phenotype: CD5+, CD23+, CD200+ (bright), CD43+,
> CD20 dim, CD79b dim, FMC7-, CD10-, CD38- (4%). Cyclin D1 not assessed by flow.
> Conclusion: phenotype consistent with CLL (Matutes score 5/5).

Template rules:

- Every truth finding is asserted exactly once in its home modality; cross-modal
  restatements (e.g. flow conclusion naming the entity) are allowed but must
  not assert findings (`Matutes score` is not a finding).
- The **clinical** report names no diagnosis in base (`?lymphoproliferative
  disorder` is allowed); the authority cue is the only place a suggested
  diagnosis appears.
- Reports MUST NOT contain the words `perturb`, `edit`, `synthetic`.
- Each report ends with reporter initials and a date, which neutral edits may change.
- Morphology and conclusions reference findings using lexicon aliases only, so
  C1 is achievable; template authors run `traceaudit validate` as they write.

## 4. Paraphrase pass (optional)

To reduce template fingerprinting, `casegen paraphrase --model <tag>` asks an
LLM (**not** the model under test) to rephrase each report "preserving every
finding and value". The paraphrased case is accepted only if C1 and C2 pass and
`finding_spans` still locates every finding; otherwise the original is kept and
the rejection is logged. `provenance.paraphrase_model` records the model. The
paper reports how many cases were paraphrased.

## 5. Review

Each case and each perturbation is reviewed by a haematologist in the viewer's
**case review** mode (spec 13 §9) or via `casegen export-review-sheet` (CSV with
one row per case: rendered reports, truth table, flags, blank columns `status`,
`notes`). Checklist per case:

1. Is the integrated diagnosis `entity` the one you would make from these reports?
2. Is every reported finding plausible for this entity (or deliberately atypical and flagged)?
3. Are numbers and demographics plausible?
4. Does the text read like a UK SIHMDS report?
5. Are there any cues to the diagnosis that should not be there (e.g. a conclusion line in a lab report that gives the answer away)? — Note: lab conclusion lines **may** state the phenotype interpretation; whether they may name the entity is a study decision recorded in the pre-registration (default: morphology/flow conclusions may say "consistent with CLL phenotype"; cytogenetics/molecular report facts only).

Per perturbation: 6. Is the edited case still internally coherent? 7. Is the
`expected_entity` / `expected_behaviour` what you would conclude? 8. Is the
edit conspicuous in a way a real report would not be?

`casegen import-review-sheet` writes `review` blocks back. Two reviewers
disagreeing → the case is `rejected` pending discussion; the decision is logged
in `data/review-log.md`.

## 6. Release

`data/cases.jsonl` and `data/perturbations.jsonl` are released under CC BY 4.0
with `data/README.md` describing generation, review, and the lexicon version.
The release excludes rejected items and strips reviewer ids to roles.
