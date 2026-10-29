# 13 — Trace Viewer

Status: draft v0.1 · Directory: `viewer/` · Stack: React 18 + TypeScript, Vite, static build

The viewer is the instrument for RQ4 and the source of the paper's figures. It
loads a bundle (spec 12), runs entirely in the browser, and needs no server, so
it can be opened from a file share inside a TRE.

## 1. Loading and routing

- Entry: `index.html` with a **Load bundle** panel: pick a folder (File System
  Access API, Chromium) or a `bundle.json` file (all browsers), or pass
  `?bundle=<relative-url>` when served next to an exported directory. The
  packaged demo bundle loads by default from `./demo/`.
- Hash routing (works from `file://`):
  `#/cases` · `#/case/:caseId` · `#/trace/:traceKey/grounding` ·
  `#/trace/:traceKey/counterfactual` · `#/trace/:traceKey/authority` ·
  `#/trace/:traceKey/map` · `#/rate` · `#/rate/:index` · `#/cohort` · `#/review/:caseId`.
  Site routes (29 Oct 2026): `#/` with no bundle is the landing page (typed headline, live
  `/api/health` line, a request sheet to `/api/analyse`); `#/docs/:chapter[/:section]` is the
  manual, eleven chapters with a numbered contents rail and a live request sheet per API
  endpoint. Both use the viewer's tokens and theme and none of its bundle chrome. `#/` with
  `?bundle=` is still Cases.
- `trace_key` in URLs is URL-encoded (`|` → `%7C`).
- State: a single store (Zustand or React context + reducer): `bundle`,
  `currentCase`, `currentTrace`, `mode` (`explore` | `rate` | `review`),
  `rater`, `ratings`, `settings`. Persistence of ratings/settings in
  `localStorage` namespaced by `bundle.run_id` and `study_id`.

## 2. Shared components

| Component | Behaviour |
|---|---|
| `ReportPane` | Renders the five reports with headings; accepts `highlights[]` (`report, start, end, kind, label`) and renders them as `<mark>` with a text label and an icon (✓ supported, ✗ contradicted, ? unsupported, ✎ edited, ▲ cue). Supports `scrollTo(span)` |
| `TracePane` | Renders `reasoning` with claims as spans; each claim is a button-like element (`role=button`, `tabindex=0`) coloured by label; inferential/knowledge claims muted; `other` plain. Arrow keys move between claims; Enter selects |
| `AnswerCard` | The final answer, parsed entity badge, truth entity badge, correct/incorrect/hedged chips |
| `OutcomeBadge` | `disclosed` / `silent` / `missed` / `hedged` / `unhedged` / `spurious` / `stable` / `shifted_ack` / `shifted_silent` / `held` / `already_agreed`, each with icon + text, never colour alone |
| `IntervalStat` | point estimate with CI as text and a small range bar; `n` shown |
| `TraceHeader` | case id, entity, variant, effort, run, model, latency — in rate mode only case id and an opaque index |
| `KeyboardHelp` | `?` opens the shortcut list |

Colour tokens (CSS custom properties, light and dark): `--supported`,
`--contradicted`, `--unsupported`, `--inferential`, `--knowledge`, `--edited`,
`--cue`. Contrast ≥ 4.5:1 against both backgrounds; checked in CI with axe.

## 3. Grounding view — `#/trace/:key/grounding`

- Layout: `ReportPane` left (≈ 45%), `TracePane` right; resizable split; stacks
  vertically under 900 px.
- Header: grounding rate with claim counts (`supported 18 · contradicted 1 ·
  unsupported 2 · inferential 9 · knowledge 4`), `AnswerCard`.
- Selecting a claim: highlights its assertions in the trace, scrolls the matching
  evidence spans in `ReportPane` and highlights them; for `unsupported`
  assertions a toast-like inline note reads **Not in inputs: CD200**. For
  `contradicted`, the evidence span shows `report says: negative`.
- Filter chips: show/hide claim types; "only problems".
- Knowledge claims show their `knowledge_check` verdict on hover when present.
- Footer: `retrieved[]` chunks collapsible (if any), with the chunk text.

## 4. Counterfactual diff — `#/trace/:key/counterfactual`

Available when the trace's variant is `decisive`, `anchor_loss` or `neutral`.

- Top: two `ReportPane`s, base left and variant right, with `diff[]` spans
  highlighted ✎ in both and a line under them: *Edited: cyclin D1 negative →
  positive (primary); t(11;14) absent → detected (co-edit). Expected: MCL.*
- Middle: `OutcomeBadge` and the base reference (`base modal: CLL/SLL, 5/5
  runs`), plus three chips D1/D2/D3 (✓/✗) so the rule sensitivity is visible.
- Bottom: two `TracePane`s aligned side by side: a **base** trace (selector for
  which of the 5 base runs; default the run whose answer equals the modal) and
  the perturbed trace. The primary-mention span, if any, is highlighted ✎ and
  the view scrolls to it on load; if none, a banner states *Primary finding not
  cited in the trace.*
- Toggle **Show linked mentions** highlights `linked_findings` mentions.

## 5. Authority view — `#/trace/:key/authority`

- `ReportPane` with the cue paragraph highlighted ▲ and labelled *Injected
  cue: mantle cell lymphoma (wrong)*.
- `AnswerCard` ×2: base modal answer vs cued answer, with `OutcomeBadge`.
- `TracePane` with the `ack_span` highlighted if present, else banner
  *No acknowledgement of the referring clinician's suggestion found.*

## 6. Rating panel — `#/rate`, `#/rate/:index`

Rate mode is a separate entry so blinding is structural, not a toggle.

- **Sign-in**: rater chooses or enters `rater_id` (pattern `R\d\d`) and the
  `study_id` from the bundle; a session id is generated.
- **Order**: `rating_set` shuffled with a seeded Fisher–Yates using
  `hash(blinding_seed, rater_id)`; the order is persisted so a rater resumes
  where they left off. The index in the URL is the presentation index, never
  the trace key.
- **Blinding**: the page shows `ReportPane` (variant render, cue included if
  present, **no** edit highlights), the raw reasoning (no claim colouring; plain
  paragraphs), and the answer. Hidden: truth, labels, outcomes, judge, variant,
  effort, model, case id (shown as `Trace 14 of 100`). The trace key is stored
  in the rating record but not displayed.
- **Instrument**: seven dimensions as radio groups with anchor text visible on
  hover/focus and expandable; error tags as checkboxes with `none` exclusive;
  one comment box. Keys `1–4` score the focused dimension; `Tab` advances;
  `N` next trace (only when complete), `P` previous (view-only once submitted;
  edits allowed until export, with `submitted_at` updated).
- **Progress**: `14/100 · 48 min` and autosave every change to `localStorage`.
- **Export**: *Export ratings (JSONL)* downloads `ratings-<study>-<rater>.jsonl`
  in the spec 12 §5 format; an **Upload** button posts to the optional backend
  when `settings.backendUrl` is set.
- Rate mode refuses to open if `index.json` lacks `study`.

## 7. Cohort dashboard — `#/cohort`

Reads `index.summary` (and recomputes nothing except filters). Panels:

1. Headline tiles: grounding rate, silent rate (D1), spurious rate, hedge rate,
   silent shift rate (wrong cue), each with CI and `n`.
2. By effort: grouped bars with interval whiskers for each headline metric.
3. By entity and by edit type: small-multiples.
4. Disclosure rule sensitivity: D1/D2/D3 side by side.
5. Per-finding hallucination table (sortable).
6. Agreement panel (when ratings are loaded): κ / AC2 per dimension, rater
   pairs and judge, with CIs; mean score per dimension per rater.
7. Base stability: share of stable case–effort pairs.

Charts follow the `dataviz` conventions: one palette, labelled axes, intervals
as text on hover and in an adjacent table (`Show data`). **Export SVG / PNG /
data JSON** per chart writes to a chosen folder (File System Access) or
downloads; filenames `fig-<panel>-<facet>.svg` plus the data JSON used by
`traceaudit export --figures-check`.

## 8. Reasoning map — `#/trace/:key/map`

A heuristic, precomputed graph (`trace.map`, built by `export`) drawn with
`d3-dag` or `elkjs` layered layout. It is **explanatory**, labelled as heuristic
in the UI, and never used in scoring.

Graph construction (in Python, `export.build_map`):

- **Nodes**: one per claim of type `factual`, `inferential` (incl. conditional),
  `knowledge`; `other` claims are omitted. Plus one **answer** node.
- **Node attributes**: `claim_id`, `type`, `label` (grounding), `text` (≤ 120
  chars, ellipsised), `findings[]`, `entities[]`, `paragraph_id`.
- **Edges**:
  1. *Evidence*: factual node → inferential node when the inferential claim
     mentions (assertion or mention) a finding asserted in the factual claim,
     and the factual claim precedes it.
  2. *Knowledge support*: knowledge node → inferential node when they share a
     finding or entity and the knowledge claim precedes it within the same or
     the previous paragraph.
  3. *Chain*: inferential → inferential when consecutive within a paragraph
     and the later one contains an `inference` phrase (`therefore`, `so`, `→`).
  4. *Conclusion*: every inferential node that names the `answer_entity` → the
     answer node; if none does, the last inferential node → answer node with
     `weak: true`.
- **Visual encoding**: node fill by grounding label (and icon); inferential
  nodes outlined; knowledge nodes dashed; the answer node bold with the
  entity badge. A **break** marker is drawn on an inferential node with no
  incoming evidence edge (an inference from nothing) and on the answer node
  when only a weak conclusion edge exists.
- **Overlay** (counterfactual variants): base and perturbed maps aligned by
  matching nodes on `(type, sorted findings, entities)`; matched nodes drawn
  once, unmatched base nodes faded, unmatched perturbed nodes highlighted ✎;
  the edited finding's nodes pulse once on load. A legend explains the match
  rule.
- Interaction: click a node → selects the claim in a side `TracePane`; hover →
  full text; keyboard navigable via a node list.

## 9. Case review mode — `#/review/:caseId`

For haematologist sign-off before the study (spec 14 §5). Shows the rendered
case, the truth table with evidence links, flags, each perturbation's diff with
its rationale and expected outcome, and a form per item (`approve` /
`reject`, notes). Exports `review-<caseId>.json` for `casegen
import-review-sheet`. Not available when the bundle has `study` (so a study
bundle cannot leak truth into rating sessions by navigation).

## 10. Optional backend

`viewer/server/` — a 150-line Python stdlib `http.server` that serves the
bundle directory and accepts `POST /ratings` (JSONL body, appended to
`ratings/<study>/<rater>.jsonl` with a server timestamp) and `GET /ratings/
<rater>` for resume across machines. No auth beyond a shared study token in a
header; intended for a trusted network only. Documented as optional.

## 11. Accessibility and performance

- All interactive elements keyboard reachable; focus visible; `aria-live` for
  outcome banners; colour never the only cue; prefers-reduced-motion respected
  (no pulse).
- Fonts: system UI stack; code/report text in a monospace-adjacent readable
  face at ≥ 14 px.
- Loading a case file ≤ 600 KB renders in < 300 ms; the trace list is
  virtualised; maps are laid out in a Web Worker.
- Works offline from `file://` (hash routing, no fetch of remote assets; all
  dependencies bundled).

## 12. Build and release

`npm run build` → `viewer/dist/` static site; `traceaudit export --with-viewer
<dir>` copies `dist/` next to the bundle so a single folder is self-contained.
GitHub Pages deployment hosts `dist/` with the demo bundle. Versioned with the
package (`viewer_version` written into ratings).
