# traceaudit Trace Viewer

A static single-page app (React 18 + TypeScript, Vite) for reading model reasoning traces exported by
`traceaudit export`, and for driving the `traceaudit serve` service (analyse one trace, audit a model). It is
domain-neutral and ships with no domain built in: the documents a model saw, the findings graded in them and the answer
categories all come from a lexicon, chosen per analysis. `public/examples/` holds one starter pair (an incident-triage
lexicon and a matching trace) that the service also lists as the example lexicon `example:incident-triage`. Reading a
bundle runs entirely in the browser: no server is needed, so it can be opened inside a TRE from a file share. It
implements spec 13 (`specs/13-viewer.md`) against the bundle format in spec 12 and the service API in spec 17.

Views:

| Route | What it shows |
|---|---|
| `#/` | The Analyse front page; Cases when the address names a bundle (`?bundle=`) |
| `#/analyse` | Front page of the service: analyse one trace (no model call) or audit a model |
| `#/analyse/trace` | Choose or upload a lexicon, paste its documents, the reasoning and the answer; `POST /api/analyse`; result rendered with the grounding view from an in-memory single-trace bundle |
| `#/analyse/audit` | Case set (uploadable), client kind, endpoint, model, key (when needed), efforts, runs; `POST /api/jobs` |
| `#/jobs`, `#/jobs/:id` | Jobs in the workspace; a job page polls every 3 s, can cancel, and when done opens the job's bundle in the Cohort tab |
| `#/cases`, `#/case/:caseId` | Case list, base documents, variants, truth and the trace list. Without a bundle: "No results loaded" with the ways to get some |
| `#/trace/:traceKey/grounding` | Documents left, trace right; claims coloured by label (icon + text, never colour alone); click a claim to see its evidence span or **Not in inputs** |
| `#/trace/:traceKey/counterfactual` | Base vs perturbed documents with the diff highlighted, outcome badge, D1/D2/D3 chips, base-run selector and the perturbed trace with the primary mention highlighted |
| `#/trace/:traceKey/authority` | Injected cue highlighted, base modal answer vs cued answer, acknowledgement span or a "No acknowledgement" banner |
| `#/trace/:traceKey/map` | Reasoning constellation (`trace.map`) as a band-constrained graph with break markers; overlay the base map for counterfactual variants |
| `#/rate`, `#/rate/:index` | Blinded rating mode (study bundles only) |
| `#/cohort` | Dashboard over `index.summary` with exportable SVG/PNG/JSON charts; the same empty state as Cases without a bundle |
| `#/review/:caseId` | Case review (bundles without a study only) |

`trace_key` contains `|`, which is URL-encoded as `%7C` in the hash.

## Run

```bash
cd viewer
npm install
npm run dev        # http://localhost:5173, opens on Analyse, proxies /api to the mock on 8787
npm run mock       # mock of `traceaudit serve` on http://127.0.0.1:8787 (see below); serves dist/ at / when built
npm test           # vitest unit tests
npm run build      # -> viewer/dist/ (includes public/examples/)
npm run preview    # serve the built site locally
```

Requires Node 20+ for the viewer and Node 22.18+ for the mock (it imports the TypeScript test fixture directly).
Runtime dependencies are `react`, `react-dom`, the four small d3 layout modules and the self-hosted font; React renders
all SVG.

## Loading a bundle

Nothing is packaged: without a bundle the viewer opens on Analyse, and the Cases and Cohort tabs say so and offer
**Run an audit**, **Analyse a trace** and **Load a bundle**. Three ways to load one:

1. **Query parameter** — serve the viewer next to an export directory and open
   `index.html?bundle=../export/` (any relative or absolute URL to a directory containing `index.json` and `cases/`,
   or directly to a single `bundle.json`). `#/` then shows Cases.
2. **Pick folder** (Chromium, File System Access API) — choose the export directory. Case files are read
   lazily as you open them.
3. **Select folder contents / Select bundle.json** (all browsers) — a standard file input; selecting the
   export folder reads `index.json` and the `cases/*.json` it refers to.

When opened from `file://`, `fetch()` is blocked by browsers, so a `?bundle=` address shows the Load bundle panel and
you use option 2 or 3. Hash routing means every route works from `file://`. **Load bundle** in the top bar opens the
panel at any time; **Cancel** returns to the empty state.

## Rating mode

Rating mode is a separate entry so blinding is structural:

- Refuses to open unless `index.json` has a `study` block.
- Sign in with a rater id (`R\d\d`); the study id comes from the bundle. A session id (UUID) is generated.
- Presentation order is a seeded Fisher–Yates shuffle of `study.rating_set` with seed
  `FNV-1a(blinding_seed + ":" + rater_id)`, so each rater gets a fixed, reproducible order and resumes where
  they left off. The URL index is the presentation index, never the trace key.
- The page shows the variant's documents (cue included, no edit highlights), the raw reasoning as plain
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
  `viewer_version`, `bundle_run_id`; the schema is kept at `src/tests/fixtures/ratings-schema.json`). Import with
  `traceaudit import-ratings <file.jsonl> ratings/<study_id>/`.
- **Upload** posts the same JSONL to `<backendUrl>/ratings` (header `X-Study-Token` when a token is set) when a
  backend URL is entered in the Export panel; the values are kept with the viewer settings in `localStorage`.
  Any endpoint that accepts `POST /ratings` with an NDJSON body will do; the Python service is the intended one.

## Analyse tab and the service

The Analyse tab talks to `traceaudit serve` (spec 17). The service address and bearer token are set with the
**Settings** button in the top bar and kept in `localStorage` under `traceaudit:api`; the token is sent as an
`Authorization: Bearer` header and never placed in a URL. With an empty base URL the viewer calls `/api/*` on its own
origin, which is the layout when the service serves `viewer/dist`.

- `src/lib/api.ts` is the typed client (every endpoint in spec 17 §3, the `{ error: { code, message } }` shape as
  `ApiError`). `src/lib/analyseBundle.ts` turns an `/api/analyse` response into a one-trace `Bundle`/`CaseFile`/`Trace`
  so the existing grounding components render it; **Open in trace views** loads that bundle into the store.
  `src/lib/jobs.ts` is the polling state machine (3 s, stops on `done`/`failed`/`cancelled`/`interrupted`).
- **No default lexicon.** `GET /api/health` reports `domain: null` and `sections: []` unless the operator configured
  one. `GET /api/lexicons` lists the starter lexicons the service ships as examples (`source: "example"`, ids like
  `example:incident-triage`) and then the workspace's uploads (`source: "upload"`). In the form the lexicon select is
  required (first option *Choose a lexicon…*, examples then uploads) and the document textareas, generated from the
  chosen lexicon's `sections`, appear only once one is chosen. `POST /api/analyse` without a usable `lexicon_id` answers
  `400 lexicon_required`, which the form words in plain language (`PLAIN_ERRORS`). **Upload lexicon** posts a chosen
  `.json` file to `POST /api/lexicons` and selects the result; `public/examples/lexicon-incident-triage.json` is a
  template. The request is the general form `{ documents, titles, reasoning, answer, entity?, lexicon_id }`
  (`src/lib/documents.ts`, `buildAnalyseRequest`); results render with the returned `case.sections` as headings and the
  returned `lexicon` display names.
- **Load example** picks `example:incident-triage` from the service's list and fills `public/examples/incident-trace.json`
  (documents, reasoning, answer). If the service lists no such example the button explains how to upload the lexicon.
- **Case sets.** The Audit form lists `GET /api/case-sets`; when there are none it says *No case sets yet* and opens the
  **Upload a case set** panel, which posts `{ name, cases: <jsonl text>, approved: true }` to `POST /api/uploads`,
  refreshes the list and selects the new set.
- **Operator keys.** `GET /api/health` may report `operator_keys` (client kinds the site runs on its own key) and
  `limits: { max_calls_per_job, max_calls_per_day, calls_used_today, operator_keys }`. The Audit form defaults the
  client kind to the first operator-key kind (else `sim`), hides the API key field for those kinds and shows
  *Runs on this site's key* with the calls left today; when the estimated calls exceed `max_calls_per_job` (or the
  remaining daily budget) the submit button is disabled with a message suggesting fewer efforts or runs. The error
  codes `key_required`, `job_too_large` and `budget_exhausted` are shown in plain language.
- **Open results** on a finished job calls `openBundle("<base>/api/jobs/<id>/bundle/")` (the programmatic form of
  `?bundle=`) with the bearer header and goes to `#/cohort`.
- Model API keys, when needed, are typed into a password field, sent once in the job request body, and cleared from
  the form.

For development without the real service, `npm run mock` starts `mock/server.mjs` (Node 22.18+, no dependencies) on
port 8787 with the same contract: no default lexicon, `example:incident-triage` read from `public/examples/`, uploads
kept in memory, `lexicon_required`, an empty case-set list until `POST /api/uploads`, operator keys and limits
(`MOCK_MAX_CALLS_PER_JOB`, `MOCK_CALLS_USED` exercise the limit errors). `/api/analyse` grades the submitted text with a
small lexical grader against the chosen lexicon, so the example produces a real-looking result. Jobs advance one status
per poll, and a finished job's bundle and files are generated from the synthetic incident-triage fixture
(`src/tests/fixtures/incidentBundle.ts`) so the Cohort and Cases tabs have something to show. `npm run dev` proxies
`/api` to it (set `VITE_API_PROXY` to point at a real service instead). `MOCK_TOKEN=secret npm run mock` makes the mock
require a bearer token, to exercise the 401 path.

## Cohort dashboard and figures

The dashboard reads `index.summary` verbatim and recomputes nothing. Each chart has **Show data** (the
intervals as a table), **Export SVG** / **Export PNG** (theme colours baked in) and **Export data** (JSON); files are
named `fig-<panel>.svg|png|json` for `traceaudit export --figures-check`. The agreement panel appears when the
bundle carries `index.ratings` (the output of `traceaudit agreement`). Category colours, filters and chart hubs follow
the bundle's lexicon: its top-level in-scope categories take the six colour slots in declared order
(`src/lib/palette.ts`, `entityOrder`), sub-categories fold to their parent's slot, anything else is grey.

## Accessibility

Document sections come from `case.sections` when a bundle or analysis carries them; otherwise the document keys,
humanised, serve as headings. User-facing copy says documents, answers and categories; the bundle's own content (case
ids, category names) is data and is shown as is.

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
# publish viewer/dist/ to the gh-pages branch, e.g.
npx gh-pages -d dist          # or copy dist/ into a docs/ folder and enable Pages on it
```

Or with Actions: build on push, upload `viewer/dist` as the Pages artifact, deploy with
`actions/deploy-pages`. Visitors can load their own bundle with the folder picker; a bundle hosted on the
same site can be linked as `?bundle=./my-run/`.

## Layout

```
viewer/
  index.html                 entry (hash routing; data-theme="light" so the first paint is white)
  src/
    main.tsx, App.tsx        bootstrap, top bar, route switch, landing redirect, empty state
    store.tsx                bundle/settings/mode context, lazy case loading, theme resolution
    types.ts                 TypeScript types derived from the bundle format
    tokens.css, styles.css   design tokens (with the contrast record) and all styles
    lib/                     bundle loading, hash router, seeded shuffle, span segmentation, documents (sections,
                             analyse request builder), evidence mapping, ratings persistence/export, node matching, downloads,
                             api (service client, limits, plain-language errors), analyseBundle, jobs (polling),
                             useApiSettings, palette (colour roles from the lexicon), cohort (filters and rates), stats (Wilson)
    components/              ReportPane, TracePane, Shared (Chip, AnswerCard, OutcomeBadge, TraceHeader,
                             KeyboardHelp, Banner), LoadPanel, ApiSettings, TraceScaffold/Split
    views/                   Cases, Case, Grounding, Counterfactual, Authority, Map, Rate, Cohort, Review,
                             Analyse (front page), AnalyseTrace, Audit (with case-set upload), Jobs, Job
    charts/                  ChartFrame (title, legend, Show data, export) and the dashboard panels:
                             OutcomeRiver (d3-sankey), EffortLadder, HeadlineRates, LexiconAtlas (d3-force),
                             AuthorityChord (d3-chord), Heatmap, RuleSlope, BaseStability, CaseConstellation
    constellation/           reasoning constellation: graph construction, band layout in a Web Worker, renderer
    tests/                   vitest: bundle loading, shuffle, ratings, spans/evidence, api, jobs, river, atlas, palette,
                             documents (request builder, sections-driven rendering), analyseBundle, constellation
    tests/fixtures/          incidentBundle.ts (synthetic 18-trace bundle generated from the types; also used by the mock),
                             ratings-schema.json
  public/examples/           incident-triage lexicon and trace: the service's example lexicon and the Load example button
  mock/server.mjs            mock of `traceaudit serve` for developing the Analyse tab (npm run mock)
```

## Visual layer

White is the default and primary theme: pure white page and panels, `#F5F5F5` raised surfaces, `#E5E5E5` hairlines,
black text and `#525252` secondary text. Dark is the same system on black (`#0A0A0A` panels, `#262626` hairlines),
chosen with the theme toggle; **System** follows the operating system but is never the default. The theme is
resolved by the store onto `data-theme` on `<html>`, so the stylesheet never guesses. Tokens live in `src/tokens.css`.
The single accent is a cobalt (`#1F4FD6` in light; `#4D83FF` text / `#2F6BFF` fills in dark) used for links, active
tabs, primary buttons, focus rings, selection, the edited highlight and the answer node. The three grounding colours
(green, red, amber) are the only other colours and are always paired with an icon and a label; inferential and
knowledge claims are two greys; the cue is a lighter accent tint. Category series have six slots, desaturated and
validated with the dataviz `validate_palette.js` on white, on `#F5F5F5` and on black (record in the tokens header);
the one-hue heat ramp and the semantic amber-to-red ramp were regenerated in OKLCH so every step clears the surface
and steps are visibly apart. Ordinal series (effort) are greys stepping up to the accent. No gradients, glows or
tinted panels.

Type: one typewriter face, **Courier Prime** (regular, bold, and their italics), self-hosted from
`@fontsource/courier-prime` so the viewer works offline, for headlines, body, UI and identifiers alike. Body is 15px on
a 1.6 line height; headlines are bold with slightly tighter letter-spacing; sentence case throughout, never all caps.
Layouts use `d3-sankey` (Outcome river), `d3-force` (Lexicon atlas, band-constrained reasoning constellation in a
Web Worker), `d3-chord` (Authority chord) and `d3-shape`. The Lexicon atlas and heatmap read
`index.lexicon.discriminators` and `index.lexicon.linked`, written by `export.to_viewer`.
