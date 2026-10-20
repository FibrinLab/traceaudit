# Trace Viewer v0.2: visual design brief

Status: brief for the rebuild of the dashboard, graphs and chrome. The behavioural
spec (routes, blinding, rating export, bundle format) in `specs/13-viewer.md` is
unchanged; this document decides how it looks and which visual forms carry the data.

## 1. Who it is for and what it must feel like

Haematopathologists and haematology researchers who spend their days reading flow
cytometry dot plots, FISH images and SIHMDS reports, now auditing an AI's
reasoning. The viewer should feel like a **diagnostic instrument**: precise, dark
like a cytometer screen or a fluorescence microscope, with jewel-coloured
populations on ink, and quiet typographic authority. Not a SaaS analytics
template; not a newspaper; not a startup landing page.

The one memorable thing: **the graphs are the interface**. Findings, claims,
inferences and diagnoses are nodes you can touch; the cohort is a river of
outcomes you can trace with a finger. Everything else is quiet.

## 2. Research that shaped this

- Reasoning-trace visualisation research (ReasonGraph, Vis-CoT, ReTrace, ReasonDiag)
  converges on: nodes = reasoning steps, directed edges = dependencies, a timeline
  companion view, and focus-plus-context (dim the rest, keep it visible). ReasonDiag's
  user study found coordinated node-link + arc views helped readers find erroneous
  steps faster than plain text. We adopt node-link + a sequential strip.
- Clinical diagnostic knowledge-graph interfaces (DiagLink, evidence-based
  diagnostic visualisation) place candidate diagnoses at the core, shared findings
  as a central cluster, edge weight = evidence strength, and selection dims
  unrelated nodes. They warn against overload. We adopt "diagnosis hubs, finding
  satellites, dim-not-hide".
- Graph rendering: our graphs are small (tens to a few hundred nodes), so SVG
  rendered from `d3-force` / layered layouts, with full styling and keyboard access,
  beats WebGL engines (Sigma, G6). Flows use `d3-sankey`; authority flows use `d3-chord`.
  Dependencies stay small: `d3-force`, `d3-sankey`, `d3-chord`, `d3-scale`, `d3-shape`,
  `d3-selection` is not needed (React renders).

## 3. Token system

### Colour

Dark is the primary mode (instrument screen); light is a first-class alternative
("paper"), not an inversion. Validate every categorical set with the dataviz
validator before use (`scripts/validate_palette.js` in the dataviz skill; run for
`--mode dark` with the ink surface and `--mode light` with the paper surface).

| Token | Dark | Light | Role |
|---|---|---|---|
| `--ink` | `#0E1A22` | `#F2F4F6` | page surface (blue-black, not neutral black) |
| `--ink-2` | `#142430` | `#FFFFFF` | panels |
| `--ink-3` | `#1C3140` | `#E6EAEE` | raised, hover |
| `--text` | `#E8EEF2` | `#14212B` | primary text |
| `--text-2` | `#9FB1BD` | `#4C6170` | secondary |
| `--line` | `#27404F` | `#C9D3DA` | hairlines |

Semantic (status-like, reserved; never reused for series):

| Token | Dark | Meaning |
|---|---|---|
| `--supported` | `#36C9A0` | claim matches the reports |
| `--contradicted` | `#FF6B57` | claim contradicts the reports |
| `--unsupported` | `#F5C451` | claim names a finding never tested |
| `--inferential` | `#9A9CF7` | inference, not graded |
| `--knowledge` | `#6FB3FF` | general knowledge, not graded |
| `--edited` | `#F06AD1` | a perturbed span |
| `--cue` | `#FF9D42` | the injected authority cue |

Entities (categorical, fixed order, validated): CLL/SLL, MCL, FL, HCL, LPL, MZL,
then SBLPN, MBL, other folded to a neutral. Start from a cytometry-inspired set
(teal, violet, chartreuse-gold, magenta, sky, salmon) and snap each to the
validator's passing steps; record the final hexes in `src/tokens.css`.

Every semantic colour ships with an icon and a text label; colour is never the
only cue. Texture (45° hatch) is available for forced-colours and print.

### Type

- Display and headings: **Fraunces** (optical-size serif, soft, slightly scientific
  warmth). Weight 500–600, no italics-for-emphasis tricks.
- UI and body: **IBM Plex Sans**. 15px base, 1.5 line height, ≤ 75 characters per line.
- Trace text and reports: **IBM Plex Sans** at 15–16px (readability for clinicians),
  not monospace. Only trace keys and identifiers use **IBM Plex Mono**.
- Self-host via `@fontsource/fraunces`, `@fontsource/ibm-plex-sans`,
  `@fontsource/ibm-plex-mono` so it works offline in a TRE.
- Scale (px): 13 / 15 / 18 / 22 / 28 / 40. Sentence case everywhere; no all-caps
  labels; no eyebrow labels; no numbered markers unless something is a sequence.

### Layout

Left-aligned, 12-column grid at ≥1200px, 16px gutters, 24px panel padding. Panels
are differentiated by surface (`--ink-2`) and a 1px `--line`, with a 6px radius;
no drop shadows. A persistent top bar with the run provenance (run id, model,
reasoning kind, lexicon version) rendered as a quiet strip, because provenance is
part of the science.

## 4. Views

### 4.1 Cohort dashboard (`#/cohort`) — the hero is the Outcome River

```
+----------------------------------------------------------------------------+
| Filters: entity ▾  effort ▾  edit kind ▾  rule D1|D2|D3        Export ▾   |
+----------------------------------------------------------------------------+
| OUTCOME RIVER (full width, ~420px tall)                                     |
|  base answer ──▶ edit kind ──▶ answer after edit ──▶ outcome                |
|  (Sankey; link colour = entity of base answer; outcome column uses semantic |
|   colours: disclosed=supported, silent=contradicted, missed=unsupported,    |
|   spurious=contradicted, stable=supported, hedged/unhedged)                 |
|  hover a ribbon: n, rate with CI; click: pins and filters every panel       |
+-------------------------------------+--------------------------------------+
| EFFORT LADDER                        | HEADLINE RATES                       |
|  one row per metric; three dots     |  grounding, silent, spurious, hedge, |
|  (low/medium/high) with CI bars,    |  silent shift — large number, CI as  |
|  connected by a hairline; entity    |  text, n; a 6px sparkline of the     |
|  small multiples below              |  per-effort values                    |
+-------------------------------------+--------------------------------------+
| LEXICON ATLAS (knowledge graph)                                             |
|  entity hubs (6) in a ring; finding satellites; edge solid = expected pos,  |
|  dashed = expected neg; satellite size = how often asserted in traces;      |
|  satellite ring colour = share contradicted / unsupported (hallucination    |
|  heat); click a finding to filter; search box to find one; dim-not-hide     |
+-------------------------------------+--------------------------------------+
| AUTHORITY CHORD                      | HALLUCINATION HEATMAP               |
|  cue entity → answer entity flows   |  finding × entity, cell = count of   |
|  for wrong cues; held = self-loop   |  contradicted + unsupported; one-hue |
|  rendered as an arc back to source  |  sequential; sortable; table view    |
+-------------------------------------+--------------------------------------+
| RULE SENSITIVITY (D1→D2→D3 slope chart) | BASE STABILITY | AGREEMENT (if ratings)|
+----------------------------------------------------------------------------+
```

Every chart: tooltip on hover, keyboard focus on marks, "Show data" table, SVG and
PNG export with the data JSON, a legend always present for ≥2 series, one axis.
Intervals are drawn as thin bars with the numbers available as text.

### 4.2 Trace page: Reasoning constellation (`#/trace/:key/map`, and a compact
version docked in the grounding view)

- Three bands left to right: **source findings** (one node per finding asserted
  in the reports the model saw, grouped by report, coloured by report), **claims**
  (factual claims as discs coloured by grounding label; knowledge as dashed
  rings; inferences as diamonds in `--inferential`), **diagnosis** (the answer
  node, large, entity colour, with the truth beside it when not blinded).
- Edges: finding → claim (evidence the claim restates; `--supported` when it
  matches, `--contradicted` when it flips), claim → inference, inference → answer.
  A broken chain (inference with no incoming evidence) shows a small gap glyph.
- Layout: `d3-force` constrained to bands (x fixed by band, y relaxed), computed
  in a Web Worker; stable across reloads (seeded).
- One orchestrated moment on load: evidence edges draw in from sources to answer
  over ~900ms, once, respecting `prefers-reduced-motion`.
- Overlay for perturbed variants: base constellation in muted ink behind the
  perturbed one; nodes matched on (type, findings, entities) sit in place,
  unmatched base nodes fade, new nodes glow once in `--edited`; the edited
  finding's source node carries the ✎ mark.
- Sequential strip underneath: the claims in reading order as small tiles, the
  same colours, scrolling in sync with the trace pane; clicking either selects both.
- Keyboard: tab through nodes in reading order; Enter selects; arrows move along
  edges; a node list (visually hidden heading) mirrors the graph for screen readers.

### 4.3 Case page (`#/case/:id`): Case constellation

The case's findings around its entity hub, drawn from the Lexicon Atlas layout
but filtered: expected-pos findings on solid spokes, expected-neg on dashed,
present findings bright, absent (not tested) hollow. Variants listed beneath with
their edits shown as spokes that flip colour. Clicking a variant previews the diff
in the reports pane.

### 4.4 Chrome

Top bar: wordmark "traceaudit" in Fraunces, tabs Cases / Cohort / Rate, theme
toggle, keyboard help, Load bundle. Below it the provenance strip. Nothing else.

### 4.5 Rating mode

Unchanged in substance and deliberately plain: no graphs, no colours on claims,
because the rater must be blinded. Typography and spacing follow the new tokens.

## 5. Principles

1. Graphs are the interface; tables and numbers are always one click away.
2. Dim, never hide: selection focuses, the context remains.
3. Semantic colours are reserved and always paired with text and icon.
4. One orchestrated motion per view; everything else answers the user's action.
5. Works offline from a folder, keyboard end to end, light and dark both designed.
6. British English; sentence case; plain verbs on buttons.
