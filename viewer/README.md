# traceaudit Trace Viewer

A static single-page app (React 18 + TypeScript, Vite) for reading model reasoning traces exported by
`traceaudit export`, and for driving the `traceaudit serve` service (analyse one trace, audit a model). It is
domain-neutral: the documents a model saw, the findings graded in them and the answer categories all come from a
lexicon, so any domain works with its own lexicon (the packaged demo bundle is a haematology study; the
`public/examples/` pair is an incident-triage lexicon with one trace). Reading a bundle runs entirely in the
browser: no server is needed, so it can be opened inside a TRE from a file share. It implements spec 13
(`specs/13-viewer.md`) against the bundle format in spec 12 and the service API in spec 17.

Views:

| Route | What it shows |
|---|---|
| `#/` | Cases when a bundle is loaded; otherwise, if the service answers `/api/health`, the Analyse front page; otherwise the Load bundle panel |
| `#/cases`, `#/case/:caseId` | Case list, base reports, variants, truth and the trace list |
| `#/trace/:traceKey/grounding` | Reports left, trace right; claims coloured by label (icon + text, never colour alone); click a claim to see its evidence span or **Not in inputs** |
| `#/trace/:traceKey/counterfactual` | Base vs perturbed reports with the diff highlighted, outcome badge, D1/D2/D3 chips, base-run selector and the perturbed trace with the primary mention highlighted |
| `#/trace/:traceKey/authority` | Injected cue highlighted, base modal answer vs cued answer, acknowledgement span or a "No acknowledgement" banner |
| `#/trace/:traceKey/map` | Reasoning constellation (`trace.map`) as a band-constrained graph with break markers; overlay the base map for counterfactual variants |
| `#/rate`, `#/rate/:index` | Blinded rating mode (study bundles only) |
| `#/cohort` | Dashboard over `index.summary` with exportable SVG/PNG/JSON charts |
| `#/review/:caseId` | Haematologist case review (bundles without a study only) |
| `#/analyse` | Front page of the service: analyse one trace (no model call) or audit a model |
| `#/analyse/trace` | Choose or upload a lexicon, paste its documents, the reasoning and the answer; `POST /api/analyse`; result rendered with the grounding view from an in-memory single-trace bundle |
| `#/analyse/audit` | Case set, client kind, endpoint, model, key (when needed), efforts, runs; `POST /api/jobs` |
| `#/jobs`, `#/jobs/:id` | Jobs in the workspace; a job page polls every 3 s, can cancel, and when done opens the job's bundle in the Cohort tab |

`trace_key` contains `|`, which is URL-encoded as `%7C` in the hash.

## Run

```bash
cd viewer
npm install
npm run dev        # http://localhost:5173, loads ./demo/ by default, proxies /api to the mock on 8787
npm run mock       # mock of `traceaudit serve` on http://127.0.0.1:8787 (see below)
npm test           # vitest unit tests
npm run build      # -> viewer/dist/ (includes the demo bundle from public/demo/)
npm run preview    # serve the built site locally
```

Requires Node 20+. Runtime dependencies are `react`, `react-dom`, the four small d3 layout modules and the
self-hosted fonts; React renders all SVG.

## Loading a bundle

Three ways, in order of convenience:

1. **Query parameter** — serve the viewer next to an export directory and open
   `index.html?bundle=../export/` (any relative URL to a directory containing `index.json` and `cases/`,
   or directly to a single `bundle.json`). With no parameter the packaged demo at `./demo/` loads.
2. **Pick folder** (Chromium, File System Access API) — choose the export directory. Case files are read
   lazily as you open them.
3. **Select folder contents / Select bundle.json** (all browsers) — a standard file input; selecting the
   export folder reads `index.json` and the `cases/*.json` it refers to.

When opened from `file://`, `fetch()` is blocked by browsers, so the Load bundle panel is shown and you use
option 2 or 3. Hash routing means every route works from `file://`. **Load bundle** in the top bar reopens the
panel at any time.

To refresh the packaged demo: copy `runs/<run>/export/{index.json,ratings-schema.json,cases/}` into
`viewer/public/demo/`.

## Rating mode

Rating mode is a separate entry so blinding is structural:

- Refuses to open unless `index.json` has a `study` block.
- Sign in with a rater id (`R\d\d`); the study id comes from the bundle. A session id (UUID) is generated.
- Presentation order is a seeded Fisher–Yates shuffle of `study.rating_set` with seed
  `FNV-1a(blinding_seed + ":" + rater_id)`, so each rater gets a fixed, reproducible order and resumes where
  they left off. The URL index is the presentation index, never the trace key.
- The page shows the variant's reports (cue included, no edit highlights), the raw reasoning as plain
  paragraphs, and the raw answer. Nothing identifies the case, variant, effort, labels, outcomes or judge
  scores; the header reads *Trace 14 of 100*.
- Seven 1–4 radio groups with the rubric anchors from `index.rubric`, error-tag checkboxes (`none` is
  exclusive) and a comment. Keys `1`–`4` score the dimension that has focus; `N` goes to the next trace once
  the current one is complete; `P` goes back. Edits remain allowed after completion and refresh `submitted_at`.
- **Storage**: every change is autosaved to `localStorage` under
  `traceaudit:ratings:<run_id>:<study_id>:<rater_id>` as `{ session, ratings }` (the session holds the
  order and session id; `ratings` is keyed by trace key and holds scores, tags, comment, timestamps and
  accumulated active time). Clearing site data removes unsaved ratings, so export regularly.
- **Export ratings (JSONL)** downloads `ratings-<study>-<rater>.jsonl` with one record per scored dimension
  plus one `dimension: "tags"` record per complete trace, exactly in the `ratings-schema.json` shape
  (`schema_version`, `study_id`, `rater_id`, `session_id`, `trace_key`, `presentation_index`, `dimension`,
  `score`, `error_tags`, `comment`, `started_at`, `submitted_at`, `duration_ms`, `blinded: true`,
  `viewer_version`, `bundle_run_id`). Import with `traceaudit import-ratings <file.jsonl> ratings/<study_id>/`.
- **Upload** posts the same JSONL to `<backendUrl>/ratings` (header `X-Study-Token` when a token is set) when a
  backend URL is entered in the Export panel; the values are kept with the viewer settings in `localStorage`.
  Any endpoint that accepts `POST /ratings` with an NDJSON body will do; the Python service is the intended one.
  The dependency-free `server/ratings_server.py` that used to ship here has been removed in its favour.

## Analyse tab and the service

The Analyse tab talks to `traceaudit serve` (spec 17). The service address and bearer token are set with the
**Settings** button in the top bar and kept in `localStorage` under `traceaudit:api`; the token is sent as an
`Authorization: Bearer` header and never placed in a URL. With an empty base URL the viewer calls `/api/*` on its own
origin, which is the layout when the service serves `viewer/dist`.

- `src/lib/api.ts` is the typed client (every endpoint in spec 17 §3, the `{ error: { code, message } }` shape as
  `ApiError`). `src/lib/analyseBundle.ts` turns an `/api/analyse` response into a one-trace `Bundle`/`CaseFile`/`Trace`
  so the existing grounding components render it; **Open in trace views** loads that bundle into the store.
  `src/lib/jobs.ts` is the polling state machine (3 s, stops on `done`/`failed`/`cancelled`/`interrupted`).
- **Lexicons and documents.** `GET /api/lexicons` lists the built-in lexicon (`id: "default"`, labelled from its
  `domain`, e.g. *Haematology (built-in)*) and uploads; **Upload lexicon** posts a chosen `.json` file to
  `POST /api/lexicons` and selects the result. The document textareas are generated from the selected lexicon's
  `sections`, and the request is the general form `{ documents, titles, reasoning, answer, entity?, lexicon_id? }`
  (`src/lib/documents.ts`, `buildAnalyseRequest`). Results render with the returned `case.sections` as headings and the
  returned `lexicon` display names. **Load example** fills the demo CLL-001 case on the built-in lexicon;
  **Load incident-triage example** uploads `public/examples/lexicon-incident-triage.json` (unless a lexicon with that
  domain is already listed) and fills `public/examples/incident-trace.json`.
- **Operator keys.** `GET /api/health` may report `operator_keys` (client kinds the site runs on its own key) and
  `limits: { max_calls_per_job, max_calls_per_day, calls_used_today, operator_keys }`. The Audit form defaults the
  client kind to the first operator-key kind (else `sim`), hides the API key field for those kinds and shows
  *Runs on this site's key* with the calls left today; when the estimated calls exceed `max_calls_per_job` (or the
  remaining daily budget) the submit button is disabled with a message suggesting fewer efforts or runs. The error
  codes `key_required`, `job_too_large` and `budget_exhausted` are shown in plain language (`PLAIN_ERRORS`).
- **Open results** on a finished job calls `openBundle("<base>/api/jobs/<id>/bundle/")` (the programmatic form of
  `?bundle=`) with the bearer header and goes to `#/cohort`.
- Model API keys, when needed, are typed into a password field, sent once in the job request body, and cleared from
  the form.

For development without the real service, `npm run mock` starts `mock/server.mjs` (Node, no dependencies) on port
8787 with canned responses built from the demo bundle; jobs advance one status per poll so the whole lifecycle takes a
few seconds. The mock reports `operator_keys: ["anthropic"]` and limits (`MOCK_MAX_CALLS_PER_JOB`, `MOCK_CALLS_USED`
exercise the limit errors), serves `/api/lexicons` (uploads kept in memory) and, for an uploaded lexicon, grades the
submitted text with a small lexical grader so the incident-triage example produces a real-looking result. `npm run dev` proxies `/api` to it (set `VITE_API_PROXY` to point at a real service
instead). `MOCK_TOKEN=secret npm run mock` makes the mock require a bearer token, to exercise the 401 path.

## Cohort dashboard and figures

The dashboard reads `index.summary` verbatim and recomputes nothing. Each chart has **Show data** (the
intervals as a table), **Export SVG** / **Export PNG** (theme colours baked in) and **Export data** (JSON); files are
named `fig-<panel>.svg|png|json` for `traceaudit export --figures-check`. The agreement panel appears when the
bundle carries `index.ratings` (the output of `traceaudit agreement`).

## Accessibility

Document sections come from `case.sections` when a bundle or analysis carries them; bundles exported before sections
existed fall back to the five haematology titles (`REPORT_TITLES`). User-facing copy says documents, answers and
categories; the bundle's own content (case ids, category names) is data and is shown as is.

Everything is reachable by keyboard: claims are `role=button` spans with arrow-key movement, constellation nodes are
focusable with a node list fallback, the split gutter resizes with ← →, `?` opens the shortcut list.
Banners use `aria-live`. Colour tokens are CSS custom properties (`--supported`, `--contradicted`,
`--unsupported`, `--inferential`, `--knowledge`, `--edited`, `--cue`) defined for light and dark with
≥ 4.5:1 text contrast on both (the record is in the header of `src/tokens.css`); every highlight also carries an
icon (✓ ✗ ? ✎ ▲) and a text label. `prefers-reduced-motion` disables the edge-draw animation and smooth scrolling.

## Deploy to GitHub Pages

The build uses a relative `base: './'`, so it works from any sub-path.

```bash
cd viewer && npm ci && npm run build
# publish viewer/dist/ (it already contains demo/) to the gh-pages branch, e.g.
npx gh-pages -d dist          # or copy dist/ into a docs/ folder and enable Pages on it
```

Or with Actions: build on push, upload `viewer/dist` as the Pages artifact, deploy with
`actions/deploy-pages`. Visitors can load their own bundle with the folder picker; a bundle hosted on the
same site can be linked as `?bundle=./my-run/`.

## Layout

```
viewer/
  index.html                 entry (hash routing)
  src/
    main.tsx, App.tsx        bootstrap, top bar, route switch, landing redirect
    store.tsx                bundle/settings/mode context, lazy case loading
    types.ts                 TypeScript types derived from the real bundle
    tokens.css, styles.css   design tokens (with the contrast record) and all styles
    lib/                     bundle loading, hash router, seeded shuffle, span segmentation, documents (sections,
                             analyse request builder), evidence mapping, ratings persistence/export, node matching, downloads,
                             api (service client, limits, plain-language errors), analyseBundle, jobs (polling),
                             useApiSettings, palette (colour roles), cohort (filters and rates), stats (Wilson)
    components/              ReportPane, TracePane, Shared (Chip, AnswerCard, OutcomeBadge, TraceHeader,
                             KeyboardHelp, Banner), LoadPanel, ApiSettings, TraceScaffold/Split
    views/                   Cases, Case, Grounding, Counterfactual, Authority, Map, Rate, Cohort, Review,
                             Analyse (front page), AnalyseTrace, Audit, Jobs, Job
    charts/                  ChartFrame (title, legend, Show data, export) and the dashboard panels:
                             OutcomeRiver (d3-sankey), EffortLadder, HeadlineRates, LexiconAtlas (d3-force),
                             AuthorityChord (d3-chord), Heatmap, RuleSlope, BaseStability, CaseConstellation
    constellation/           reasoning constellation: graph construction, band layout in a Web Worker, renderer
    tests/                   vitest: bundle loading, shuffle, ratings, spans/evidence, api, jobs, river, atlas,
                             documents (request builder, sections-driven rendering)
  public/demo/               packaged demo bundle
  public/examples/           incident-triage lexicon and trace for the second example button
  mock/server.mjs            mock of `traceaudit serve` for developing the Analyse tab (npm run mock)
```

## Visual layer

Black and white as the base, one accent. Tokens live in `src/tokens.css`: dark mode (default) is pure black with
`#0A0A0A` panels and `#262626` hairlines; light mode is white with `#F5F5F5` raised surfaces and `#E5E5E5` hairlines.
The single accent is an electric cobalt (`#4D83FF` text / `#2F6BFF` fills in dark, `#1F4FD6` in light) used for
links, active tabs, primary buttons, focus rings, selection, the edited highlight and the answer node. The three
grounding colours (green, red, amber) are the only other colours and are always paired with an icon and a label;
inferential and knowledge claims are two greys; the cue is a lighter accent tint. Entity series keep six hues,
desaturated and validated with the dataviz `validate_palette.js` in both modes (record in the tokens header);
ordinal series (effort, report order) are greys stepping up to the accent. No gradients, glows or tinted panels.

Type: headlines in **Instrument Serif** (the one memorable element), everything else in **Inter**, code in
**IBM Plex Mono**, all self-hosted from `@fontsource/*` so the viewer works offline. Sentence case throughout.
Layouts use `d3-sankey` (Outcome river), `d3-force` (Lexicon atlas, band-constrained reasoning constellation in a
Web Worker), `d3-chord` (Authority chord) and `d3-shape`. The Lexicon atlas and heatmap read
`index.lexicon.discriminators` and `index.lexicon.linked`, written by `export.to_viewer`.
