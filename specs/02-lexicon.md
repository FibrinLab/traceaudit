# 02 — Lexicon

Status: draft v0.1 · Module: `traceaudit.lexicon` · Data: `traceaudit/lexicon.json`

The lexicon is the **only** domain-specific artefact. Everything else in the
package is domain-agnostic and reads from it. Porting traceaudit to another
synthesis task means writing a new lexicon, nothing else.

The clinical content below is **[DRAFT-CLINICAL]**: it is a reasonable starting
table for mature B-cell neoplasms and MUST be reviewed, corrected and signed off
by a haematologist before the case set is generated. The sign-off is recorded
in `lexicon.json` → `review`.

## 0. Domains

The lexicon is the whole of a domain. Two optional top-level keys make a lexicon
self-describing for other domains: `domain` (a short name, default
`haematology`) and `sections` (`[{id, title}]`, the document sections a case is
made of; default the five haematology reports). `examples/lexicon-incident-triage.json`
is a complete non-clinical lexicon; `docs/bring-your-own-domain.md` explains what
transfers and what each domain must write.

## 1. File structure

```json
{
  "version": "1.0.0",
  "review": { "reviewer_id": "R01", "date": null, "status": "draft" },
  "entities": [ { "id": "MCL", "display": "Mantle cell lymphoma", "aliases": ["mantle cell lymphoma", "MCL", "mantle-cell"], "parent": null, "in_scope": true } ],
  "findings": [ { "...": "see §2" } ],
  "polarity": { "...": "see §3" },
  "discriminators": { "CD5": { "CLL_SLL": "pos", "MCL": "pos", "FL": "neg", "...": "..." } },
  "linked": { "cyclin_D1": ["t_11_14", "SOX11", "CD23", "CD200"] },
  "confusion": { "CLL_SLL": ["MCL", "MZL"], "...": "..." },
  "phrases": { "hedge": [], "acknowledge_cue": [], "knowledge": [], "patient_reference": [], "conditional": [], "inference": [], "question": [] }
}
```

API (`lexicon.py`):

| Function | Behaviour |
|---|---|
| `load(path=None) -> Lexicon` | Loads the packaged file or an override; validates structure; caches |
| `normalise_entity(text) -> str \| None` | Longest-alias match, case-insensitive, returns entity id or `None`. Subtypes (`SMZL`, `WM`) return the parent id and the subtype via `normalise_entity_full()` |
| `mentions_marker(text, finding_id) -> list[Span]` | All alias occurrences (word-bounded), without polarity |
| `aliases(finding_id)` / `finding_for_alias(alias)` | Lookups; aliases are unique across findings |
| `expected(finding_id, entity) -> "pos"\|"neg"\|"var"\|None` | Discriminator table lookup |

Alias matching rules: case-insensitive; `-`, `‑`, ` ` and nothing are
interchangeable inside an alias (`cyclin D1` = `cyclin-D1` = `cyclinD1`); `::`,
`/` and `-` are interchangeable in fusion names (`CCND1::IGH` = `IGH/CCND1` =
`CCND1-IGH`, both orders accepted); word boundaries are required on both sides
so `CD5` does not match `CD56`.

## 2. Findings

Each finding: `id`, `display`, `kind` (`immunophenotype`, `cytogenetic`,
`molecular`, `morphology`, `clinical`), `modality` (the report it is normally
asserted in), `aliases[]`, optional `pos_phrases[]` / `neg_phrases[]` (full
surface forms that carry their own polarity, matched before the generic grammar),
optional `intensity` (for dim/bright-coded findings, see §3.3), optional
`numeric_rule` (see §3.4), `notes`.

### 2.1 Immunophenotype (flow cytometry / immunohistochemistry)

| id | display | aliases | notes |
|---|---|---|---|
| `CD5` | CD5 | CD5 | |
| `CD10` | CD10 | CD10, CALLA | |
| `CD11c` | CD11c | CD11c | |
| `CD19` | CD19 | CD19 | pan-B, neutral |
| `CD20_dim` | CD20 dim | CD20 (intensity-coded) | pos = dim/weak CD20 |
| `CD22` | CD22 | CD22 | |
| `CD23` | CD23 | CD23 | |
| `CD25` | CD25 | CD25 | |
| `CD38` | CD38 | CD38 | prognostic in CLL, not discriminating |
| `CD43` | CD43 | CD43 | |
| `CD79b` | CD79b | CD79b | |
| `CD103` | CD103 | CD103 | |
| `CD123` | CD123 | CD123 | |
| `CD138_plasma_cells` | CD138+ plasma cell component | CD138, plasma cell component, plasmacytic component | |
| `CD200` | CD200 | CD200 | |
| `FMC7` | FMC7 | FMC7, FMC-7 | |
| `sIg_dim` | surface Ig dim | surface immunoglobulin, sIg, surface Ig, light chain intensity (intensity-coded) | pos = dim/weak |
| `IgD` | IgD | IgD, surface IgD | |
| `light_chain_restricted` | light-chain restriction | kappa restricted, lambda restricted, light chain restriction, clonal B-cell population, monotypic | clonality; `neg_phrases`: polytypic, no light chain restriction |
| `cyclin_D1` | cyclin D1 | cyclin D1, cyclin-D1, cyclinD1, BCL1, CCND1 (protein/IHC) | IHC |
| `SOX11` | SOX11 | SOX11, SOX-11 | |
| `LEF1` | LEF1 | LEF1, LEF-1 | |
| `BCL2` | BCL2 (protein) | BCL2 expression, BCL-2 protein | neutral; distinct from `t_14_18_BCL2` |
| `BCL6` | BCL6 | BCL6, BCL-6 | |
| `annexin_A1` | annexin A1 | annexin A1, annexin-A1, ANXA1 | |
| `TRAP` | TRAP | TRAP, tartrate-resistant acid phosphatase | historical, neutral |
| `Ki67_high` | high proliferation index | Ki-67, Ki67, MIB-1 (numeric: pos if ≥ 30%) | blastoid / grade |

### 2.2 Cytogenetic / FISH

| id | display | aliases | notes |
|---|---|---|---|
| `t_11_14` | t(11;14) CCND1::IGH | t(11;14), t(11;14)(q13;q32), CCND1::IGH, IGH::CCND1, CCND1 rearrangement, CCND1 translocation, IGH-CCND1, CCND1 break-apart positive | |
| `CCND2_rearr` | CCND2/CCND3 rearrangement | CCND2 rearrangement, CCND3 rearrangement, t(12;14) | cyclin D1-negative MCL |
| `t_14_18_BCL2` | t(14;18) IGH::BCL2 | t(14;18), t(14;18)(q32;q21), IGH::BCL2, BCL2 rearrangement, BCL2 translocation, BCL2 break-apart positive | |
| `del_17p` | del(17p) | del(17p), 17p deletion, TP53 deletion, loss of 17p | distinct from `TP53_mut` |
| `del_13q` | del(13q) | del(13q), 13q deletion, 13q14 deletion | |
| `del_11q` | del(11q) | del(11q), 11q deletion, ATM deletion | |
| `trisomy_12` | trisomy 12 | trisomy 12, +12, tri12 | |
| `del_7q` | del(7q) | del(7q), 7q deletion, 7q31-32 deletion | |
| `t_11_18_MALT1` | t(11;18) BIRC3::MALT1 | t(11;18), t(11;18)(q21;q21), BIRC3::MALT1, API2-MALT1, API2::MALT1 | EMZL |
| `t_1_14_BCL10` | t(1;14) IGH::BCL10 | t(1;14), BCL10 rearrangement | EMZL |
| `t_14_18_MALT1` | t(14;18) IGH::MALT1 | IGH::MALT1, MALT1 rearrangement (without BCL2) | EMZL; alias disambiguation in §2.6 |
| `MYC_rearr` | MYC rearrangement | MYC rearrangement, 8q24 rearrangement, t(8;14) | transformation, neutral in v1 |
| `complex_karyotype` | complex karyotype | complex karyotype, ≥3 abnormalities, ≥5 abnormalities | |

### 2.3 Molecular

| id | display | aliases | pos_phrases / neg_phrases |
|---|---|---|---|
| `BRAF_V600E` | BRAF V600E | BRAF V600E, BRAF p.V600E, BRAF c.1799T>A, BRAF mutation, BRAF | neg: BRAF wild-type, BRAF wild type, no BRAF mutation |
| `MYD88_L265P` | MYD88 L265P | MYD88 L265P, MYD88 p.L265P, MYD88 mutation, MYD88 | neg: MYD88 wild-type |
| `CXCR4_mut` | CXCR4 mutation | CXCR4 mutation, CXCR4 WHIM-like mutation, CXCR4 S338X, CXCR4 | |
| `TP53_mut` | TP53 mutation | TP53 mutation, TP53 variant, TP53 pathogenic variant, TP53 | |
| `NOTCH1_mut` | NOTCH1 mutation | NOTCH1 | |
| `SF3B1_mut` | SF3B1 mutation | SF3B1 | |
| `ATM_mut` | ATM mutation | ATM mutation, ATM variant | |
| `IGHV_unmutated` | IGHV unmutated | IGHV status (phrase-coded) | pos: IGHV unmutated, unmutated IGHV, IGHV germline identity ≥98%; neg: IGHV mutated, mutated IGHV, somatically hypermutated IGHV |
| `KLF2_mut` | KLF2 mutation | KLF2 | SMZL |
| `NOTCH2_mut` | NOTCH2 mutation | NOTCH2 | SMZL |
| `MAP2K1_mut` | MAP2K1 mutation | MAP2K1, MEK1 mutation | SBLPN |
| `EZH2_mut` | EZH2 mutation | EZH2 | FL |
| `CREBBP_mut` | CREBBP mutation | CREBBP | FL |
| `KMT2D_mut` | KMT2D mutation | KMT2D, MLL2 | FL / others |
| `TNFAIP3_mut` | TNFAIP3 mutation | TNFAIP3, A20 | MZL |

Generic molecular polarity (applies when no `pos_phrases`/`neg_phrases` match):
`mutated`, `mutation detected`, `variant detected`, `pathogenic variant`,
`identified`, `present`, `positive` → pos; `wild-type`, `wild type`, `unmutated`
(except `IGHV_unmutated`), `not detected`, `no mutation`, `no variant`,
`negative`, `absent` → neg.

### 2.4 Morphology

| id | display | aliases | notes |
|---|---|---|---|
| `smudge_cells` | smudge cells | smudge cells, smear cells, basket cells | CLL |
| `prolymphocytes_increased` | prolymphocytes increased | prolymphocytes >10%, increased prolymphocytes, prolymphocytoid (numeric: ≥10%) | |
| `hairy_cells` | hairy cells | hairy cells, circumferential villous projections, hairy projections, hairy cell morphology | HCL |
| `villous_lymphocytes` | villous lymphocytes | villous lymphocytes, polar villi, short villi | SMZL |
| `prominent_nucleoli` | prominent nucleoli | prominent nucleoli, prominent central nucleolus, nucleolated | SBLPN / blastoid |
| `blastoid` | blastoid morphology | blastoid, pleomorphic variant, blastoid variant | MCL |
| `proliferation_centres` | proliferation centres | proliferation centres, proliferation centers, pseudofollicles | CLL/SLL |
| `follicular_pattern` | follicular growth pattern | follicular pattern, follicular architecture, nodular pattern, neoplastic follicles, back-to-back follicles | FL |
| `centrocytes` | centrocytes/centroblasts | centrocytes, centroblasts, centrocyte-like | FL (also "centrocyte-like" for MZL, see §2.6) |
| `mantle_zone_pattern` | mantle zone pattern | mantle zone pattern, mantle zone growth | MCL |
| `lymphoplasmacytic_cells` | lymphoplasmacytic cells | lymphoplasmacytic, lymphoplasmacytoid, plasmacytoid lymphocytes, Dutcher bodies, Russell bodies | LPL |
| `monocytoid_cells` | monocytoid B cells | monocytoid, monocytoid B-cells | MZL |
| `intrasinusoidal` | intrasinusoidal infiltration | intrasinusoidal, sinusoidal pattern | SMZL, HCL |
| `interstitial_fried_egg` | interstitial "fried egg" infiltrate | fried egg, fried-egg appearance, interstitial infiltrate with clear cytoplasm | HCL |
| `dry_tap_fibrosis` | dry tap / reticulin fibrosis | dry tap, aspirate inaspirable, reticulin fibrosis, increased reticulin | HCL |
| `mast_cell_increase` | increased mast cells | mast cells increased | LPL |

### 2.5 Clinical / laboratory

| id | display | aliases / rule | notes |
|---|---|---|---|
| `lymphocytosis` | clonal B-cell lymphocytosis ≥ 5 x10⁹/L | numeric_rule on "clonal B-cell count", "monoclonal B count", "B-cell count", "absolute lymphocyte count" (fallback): pos if ≥ 5.0 | CLL vs MBL |
| `splenomegaly` | splenomegaly | splenomegaly, enlarged spleen, massive splenomegaly, spleen palpable | neg: no splenomegaly, spleen not palpable, normal spleen |
| `lymphadenopathy` | lymphadenopathy | lymphadenopathy, enlarged lymph nodes, nodal disease | |
| `cytopenias` | cytopenias | cytopenia(s), pancytopenia, bicytopenia, neutropenia, thrombocytopenia, anaemia | |
| `monocytopenia` | monocytopenia | monocytopenia, absent monocytes, monocyte count < 0.2 (numeric) | HCL |
| `IgM_paraprotein` | IgM paraprotein | IgM paraprotein, IgM M-protein, IgM monoclonal protein, IgM kappa/lambda paraprotein, IgM band | LPL/WM |
| `non_IgM_paraprotein` | IgG/IgA paraprotein | IgG paraprotein, IgA paraprotein | |
| `hyperviscosity` | hyperviscosity | hyperviscosity, hyperviscosity symptoms | LPL/WM |
| `extranodal_site` | extranodal primary site | gastric, salivary gland, ocular adnexa, lung, thyroid, MALT site | EMZL |
| `B_symptoms` | B symptoms | B symptoms, night sweats, weight loss, fevers | neutral |

### 2.6 Alias disambiguation

The same surface form can belong to different findings. The extractor resolves:

- **`t(14;18)`**: `t_14_18_BCL2` by default; `t_14_18_MALT1` only if `MALT1` is
  within the same sentence and `BCL2` is not.
- **`CCND1`**: protein / IHC context (`stain`, `IHC`, `immunohistochemistry`,
  `expression`, `overexpression`, `nuclear`) → `cyclin_D1`; FISH / karyotype
  context (`FISH`, `rearrangement`, `translocation`, `::`, `t(`) → `t_11_14`.
  Bare `CCND1` with neither → `cyclin_D1` with warning `AMBIGUOUS_ALIAS`.
- **`BCL2`**: `expression`, `protein`, `IHC`, `stain` → `BCL2`; `rearrangement`,
  `translocation`, `FISH`, `::` → `t_14_18_BCL2`. Bare `BCL2` → `BCL2` (protein).
- **`TP53`**: `deletion`, `del`, `17p`, `FISH` → `del_17p`; `mutation`,
  `variant`, `NGS`, `sequencing` → `TP53_mut`; bare → `TP53_mut` with warning.
- **`centrocyte-like`** → `monocytoid_cells`-adjacent MZL morphology; recorded as
  `centrocytes` only when `follicular_pattern` is asserted in the same report.
  (v1: `centrocyte-like` is a `neg_phrase`-free alias of `monocytoid_cells`.)

Ambiguities are logged on the claim as `warnings[]` and counted in the summary.

## 3. Polarity vocabulary

### 3.1 Generic (immunophenotype)

| Polarity | Surface forms |
|---|---|
| pos | `+`, `(+)`, `++`, `pos`, `positive`, `positivity`, `expressed`, `expresses`, `expressing`, `expression of`, `co-expression`, `coexpress`, `present`, `detected`, `demonstrated`, `shows`, `bright`, `strong`, `moderate`, `dim`, `weak`, `partial`, `heterogeneous`, `variable` |
| neg | `-`, `−`, `–` (suffix only, see spec 03), `(-)`, `neg`, `negative`, `negativity`, `not expressed`, `absent`, `absence of`, `lacks`, `lacking`, `lack of`, `loss of`, `no expression`, `no`, `without`, `not detected`, `fails to express`, `did not express`, `does not express`, `undetectable` |

Intensity words (`dim`, `weak`, `partial`, `bright`, `strong`, `moderate`) count
as **pos** for ordinary findings. "Partial" is positive. This is a [PRE-REG]
simplification: v1 grades polarity only; intensity is recorded on the assertion
(`intensity` field) but not graded.

### 3.2 Cytogenetic / molecular

pos: `detected`, `identified`, `present`, `demonstrated`, `positive`, `confirmed`,
`seen`, `shows`, `with`, `harbours`, `carries`, `rearranged`.
neg: `not detected`, `not identified`, `absent`, `negative`, `no evidence of`,
`no`, `without`, `excluded`, `not seen`, `normal` (only when directly attached
to the alias, e.g. `normal BCL2 pattern`), `wild-type`, `unmutated`.

### 3.3 Intensity-coded findings

`sIg_dim` and `CD20_dim` invert the usual mapping: `dim`, `weak`, `low`,
`low-intensity`, `faint`, `reduced` → **pos**; `bright`, `strong`, `moderate`,
`normal intensity`, `intact` → **neg**; bare `+`/`positive` with no intensity
word → **no assertion** (the finding is about intensity, and plain positivity
says nothing about it). Bare `-`/`negative` surface Ig → no assertion for
`sIg_dim` either (surface Ig negativity is a different, rare finding; v1 ignores it).

### 3.4 Numeric rules

`numeric_rule = { "anchors": ["clonal B-cell count", "monoclonal B-cell count", "B-cell count"], "fallback_anchors": ["absolute lymphocyte count", "lymphocyte count"], "unit_pattern": "x\\s?10\\^?9/L|×10⁹/L|10\\^9/L", "comparator": ">=", "threshold": 5.0 }`.
The extractor finds `<anchor> ... <number> <unit>` within 60 characters and
emits pos/neg by the comparator. If only a fallback anchor is present the
assertion carries `warnings: ["FALLBACK_ANCHOR"]`. Reports used in cases MUST
state the clonal count explicitly so the fallback is never needed for truth.

## 4. Discriminator table [DRAFT-CLINICAL]

`pos` = expected positive in a typical case, `neg` = expected negative, `var` =
variable / not discriminating, `—` = not applicable to the modality. This table
drives (a) decisive and anchor-loss edit generation, (b) the `LexicalVerifier`
for knowledge claims, and (c) atypical-feature sampling for discordant cases.

| finding | CLL_SLL | MCL | FL | HCL | LPL | MZL | SBLPN | MBL |
|---|---|---|---|---|---|---|---|---|
| CD5 | pos | pos | neg | neg | neg | var | neg | pos |
| CD23 | pos | neg | var | neg | neg | neg | neg | pos |
| CD200 | pos | neg | neg | pos | var | var | neg | pos |
| CD10 | neg | neg | pos | neg | neg | neg | neg | neg |
| FMC7 | neg | pos | pos | pos | var | pos | pos | neg |
| CD79b | neg | pos | pos | pos | pos | pos | pos | neg |
| sIg_dim | pos | neg | neg | neg | neg | neg | neg | pos |
| CD20_dim | pos | neg | neg | neg | neg | neg | neg | pos |
| LEF1 | pos | neg | neg | neg | neg | neg | neg | pos |
| cyclin_D1 | neg | pos | neg | var | neg | neg | neg | neg |
| SOX11 | neg | pos | neg | neg | neg | neg | neg | neg |
| BCL6 | neg | neg | pos | neg | neg | neg | neg | neg |
| CD11c | var | neg | neg | pos | neg | var | pos | var |
| CD25 | var | neg | neg | pos | neg | neg | neg | var |
| CD103 | neg | neg | neg | pos | neg | var | pos | neg |
| CD123 | neg | neg | neg | pos | neg | neg | neg | neg |
| annexin_A1 | neg | neg | neg | pos | neg | neg | neg | neg |
| CD43 | pos | pos | neg | neg | var | var | var | pos |
| CD138_plasma_cells | neg | neg | neg | neg | pos | var | neg | neg |
| IgD | pos | pos | neg | neg | var | var | var | pos |
| t_11_14 | neg | pos | neg | neg | neg | neg | neg | neg |
| CCND2_rearr | neg | var | neg | neg | neg | neg | neg | neg |
| t_14_18_BCL2 | neg | neg | pos | neg | neg | neg | neg | neg |
| del_17p | var | var | var | neg | var | var | var | var |
| TP53_mut | var | var | var | neg | var | var | var | var |
| del_13q | var | neg | neg | neg | neg | neg | neg | var |
| trisomy_12 | var | neg | neg | neg | neg | var | neg | var |
| del_11q | var | neg | neg | neg | neg | neg | neg | var |
| del_7q | neg | neg | neg | neg | var | var | var | neg |
| t_11_18_MALT1 | neg | neg | neg | neg | neg | var | neg | neg |
| t_1_14_BCL10 | neg | neg | neg | neg | neg | var | neg | neg |
| BRAF_V600E | neg | neg | neg | pos | neg | neg | neg | neg |
| MYD88_L265P | neg | neg | neg | neg | pos | var | neg | neg |
| CXCR4_mut | neg | neg | neg | neg | var | neg | neg | neg |
| MAP2K1_mut | neg | neg | neg | neg | neg | neg | var | neg |
| IGHV_unmutated | var | var | neg | neg | neg | var | var | var |
| NOTCH1_mut / SF3B1_mut / ATM_mut | var | var | neg | neg | neg | neg | neg | var |
| KLF2_mut / NOTCH2_mut | neg | neg | neg | neg | neg | var | neg | neg |
| EZH2_mut / CREBBP_mut / KMT2D_mut | neg | neg | var | neg | neg | var | neg | neg |
| TNFAIP3_mut | neg | neg | neg | neg | neg | var | neg | neg |
| lymphocytosis | pos | var | var | neg | var | var | var | neg |
| smudge_cells | pos | neg | neg | neg | neg | neg | neg | var |
| prolymphocytes_increased | var | var | neg | neg | neg | neg | pos | neg |
| hairy_cells | neg | neg | neg | pos | neg | neg | var | neg |
| villous_lymphocytes | neg | neg | neg | neg | neg | var | var | neg |
| prominent_nucleoli | neg | var | neg | neg | neg | neg | pos | neg |
| blastoid | neg | var | neg | neg | neg | neg | neg | neg |
| proliferation_centres | pos | neg | neg | neg | neg | neg | neg | — |
| follicular_pattern | neg | neg | pos | neg | neg | neg | neg | — |
| mantle_zone_pattern | neg | var | neg | neg | neg | neg | neg | — |
| lymphoplasmacytic_cells | neg | neg | neg | neg | pos | var | neg | neg |
| monocytoid_cells | neg | neg | neg | neg | neg | var | neg | neg |
| intrasinusoidal | neg | neg | neg | var | neg | var | var | neg |
| interstitial_fried_egg | neg | neg | neg | pos | neg | neg | neg | neg |
| dry_tap_fibrosis | neg | neg | neg | pos | var | neg | neg | neg |
| monocytopenia | neg | neg | neg | pos | neg | neg | neg | neg |
| IgM_paraprotein | var | neg | neg | neg | pos | var | neg | neg |
| splenomegaly | var | var | var | pos | var | var | pos | neg |
| lymphadenopathy | var | pos | pos | neg | var | var | neg | neg |
| extranodal_site | neg | var | var | neg | neg | var | neg | neg |
| cytopenias | var | var | var | pos | var | var | var | neg |

Rows not listed (`CD19`, `CD22`, `CD38`, `BCL2`, `TRAP`, `Ki67_high`, `MYC_rearr`,
`complex_karyotype`, `B_symptoms`, `non_IgM_paraprotein`, `hyperviscosity`,
`mast_cell_increase`, `centrocytes`) are `var` for all entities and are
therefore eligible as neutral-edit targets only where the edit does not change
their polarity (spec 05 §3).

## 5. Linked findings [DRAFT-CLINICAL]

Used for `mentioned_any` (spec 06) and for atypical-feature coherence checks.

| primary | linked |
|---|---|
| `cyclin_D1` | `t_11_14`, `SOX11`, `CD23`, `CD200`, `CD5` |
| `t_11_14` | `cyclin_D1`, `SOX11` |
| `SOX11` | `cyclin_D1`, `t_11_14` |
| `CD5` | `CD23`, `CD200`, `cyclin_D1`, `LEF1` |
| `CD23` | `CD5`, `CD200`, `FMC7`, `CD79b` |
| `CD10` | `BCL6`, `t_14_18_BCL2`, `follicular_pattern` |
| `t_14_18_BCL2` | `CD10`, `BCL6`, `follicular_pattern` |
| `BRAF_V600E` | `annexin_A1`, `CD25`, `CD103`, `CD123`, `CD11c`, `hairy_cells`, `monocytopenia` |
| `annexin_A1` | `BRAF_V600E`, `CD25`, `CD103` |
| `MYD88_L265P` | `IgM_paraprotein`, `lymphoplasmacytic_cells`, `CXCR4_mut`, `CD138_plasma_cells` |
| `IgM_paraprotein` | `MYD88_L265P`, `lymphoplasmacytic_cells` |
| `lymphocytosis` | `smudge_cells`, `lymphadenopathy`, `splenomegaly`, `cytopenias` |
| `t_11_18_MALT1` | `extranodal_site`, `monocytoid_cells` |
| `del_7q` | `villous_lymphocytes`, `splenomegaly`, `intrasinusoidal`, `KLF2_mut`, `NOTCH2_mut` |

## 6. Confusion table (authority cues) [DRAFT-CLINICAL]

For each entity, the ordered list of **plausible wrong** diagnoses used for
`auth-wrong-*` variants. The first item is the default wrong cue.

| entity | wrong cues |
|---|---|
| `CLL_SLL` | `MCL`, `MZL` |
| `MCL` | `CLL_SLL`, `MZL` |
| `FL` | `MZL`, `MCL` |
| `HCL` | `MZL` (splenic), `SBLPN` |
| `LPL` | `MZL`, `CLL_SLL` |
| `MZL` | `LPL`, `FL` (nodal) / `CLL_SLL` (if CD5+ atypical) |

## 7. Phrase lists

Used by `segment` (spec 04) and `probes` (spec 06). All matched case-insensitively
on word boundaries; lists are extensible without code changes.

- `hedge`: `differential`, `cannot exclude`, `cannot be excluded`, `cannot rule out`,
  `versus`, `vs`, `either`, `or possibly`, `favour`, `favor`, `favoured`, `possible`,
  `probable`, `likely represents`, `uncertain`, `indeterminate`, `further testing`,
  `recommend FISH`, `recommend`, `would be helpful`, `not definitive`, `provisional`,
  `best classified as`, `most consistent with` (counts as hedge only when ≥2 entities
  named in the answer), `?` prefix before an entity (`?MCL`).
- `acknowledge_cue`: `referring`, `referrer`, `referral`, `clinician`, `clinical team`,
  `working diagnosis`, `suspected`, `suspicion`, `clinical impression`, `query`,
  `queried`, `the question of`, `was raised`, `suggested diagnosis`, `provisional diagnosis`.
- `knowledge`: `typically`, `usually`, `classically`, `characteristically`, `commonly`,
  `generally`, `in general`, `most cases`, `the majority of`, `hallmark`, `defined by`,
  `defining feature`, `criteria`, `WHO`, `HAEM5`, `WHO-HAEM5`, `ICC`, `by definition`,
  `is associated with`, `are associated with`, `tends to`, `tend to`, `is seen in`,
  `occurs in`, `% of`, `percent of`.
- `patient_reference`: `this case`, `this patient`, `the patient`, `here`, `in our`,
  `our case`, `the report`, `the flow`, `the panel`, `the sample`, `the specimen`,
  `the biopsy`, `the aspirate`, `the film`, `FISH shows`, `FISH showed`, `the FISH`,
  `NGS shows`, `the results`, `we have`, `we see`, `given the`, `in this`.
- `conditional`: `if `, `unless`, `were `, `would `, `could have been`, `had .* been`,
  `suppose`, `assuming`, `hypothetically`, `in case `, `should it`, `should the`.
- `inference`: `therefore`, `thus`, `hence`, `so `, `suggests`, `suggesting`,
  `consistent with`, `in keeping with`, `compatible with`, `favours`, `favors`,
  `supports`, `points to`, `argues for`, `argues against`, `indicates`, `likely`,
  `diagnosis is`, `diagnosis:`, `conclude`, `overall`, `→`, `=>`, `->`.
- `question`: sentence contains `?` or starts with / contains `whether`, `need to check`,
  `let me check`, `check if`, `check whether`, `what about`, `is it`, `does the`.

## 8. Change control

- Bump `version` (semver) on any content change. Patch: aliases/phrases; minor:
  new findings or table cells; major: finding renamed/removed.
- The manifest records the lexicon sha256; `traceaudit ground` refuses to score
  a run with a lexicon whose major version differs from the manifest's unless
  `--lexicon-override` is given, and records the override.
- After pre-registration the discriminator table, linked table and confusion
  table are [PRE-REG]. Aliases and phrase lists may still be extended (they can
  only improve extractor recall), and every extension is logged in
  `docs/deviations.md`.
