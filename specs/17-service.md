# 17 — Service: `traceaudit serve`

Status: draft v0.1 · Module: `traceaudit.serve` · Standard library only (`http.server`, `threading`)

A small HTTP service that puts the library behind a form. It runs the same code
as the command line, so numbers match and the manifest still records provenance.
It is designed to run as a public demo on synthetic data and, unchanged, as an
on-premises install inside a TRE.

## 1. Modes

| Mode | Input | Output | Calls a model |
|---|---|---|---|
| `analyse` | reports, reasoning text, answer text (one trace) | claims, grounding, parsed answer, finding spans, reasoning map | no |
| `audit` | a model endpoint and key, a case set, efforts, runs | a full run directory, scored, exported as a viewer bundle | yes, the user's model |
| `audit` with upload | as above plus the user's own cases/perturbations/lexicon | same | yes |

## 2. Authentication and keys

- Every request may carry `Authorization: Bearer <token>`. Tokens are configured
  by the operator (`--tokens token1:workspaceA,token2:workspaceB` or
  `TRACEAUDIT_TOKENS`). A token maps to a workspace; jobs and uploads are scoped
  to the workspace. The special workspace `public` is used for anonymous requests.
- `--anonymous analyse` (default) allows unauthenticated `analyse` requests with a
  per-address rate limit (`--rate 60/min`); `--anonymous none` requires a token
  for everything; `--anonymous all` allows anonymous audit jobs (demo instances
  with the simulated model only).
- Model API keys arrive in the job request body, are held in memory for the
  lifetime of the job, and are never written to disk or returned by any endpoint.
  `job.json` records only the client kind, endpoint and model tag.
- `--allow-clients sim,ollama,openai,anthropic` restricts which client kinds jobs
  may use; the public demo default is `sim` only.
- **Operator key.** `--operator-key anthropic=ANTHROPIC_API_KEY` lets jobs of that
  kind run on a key the site holds, read from the named environment variable at
  start-up and never persisted. Spend is bounded by `--max-calls-per-job` (default
  200; applies to every non-simulated job) and `--max-calls-per-day` (default 2000;
  applies to operator-key jobs, counted from each job's planned call count). A job
  without a key for a kind that has no operator key is refused with `key_required`;
  over the caps, `job_too_large` (400) or `budget_exhausted` (429).

## 3. Endpoints

All JSON unless stated. Errors: `{ "error": { "code": "...", "message": "..." } }`
with 400/401/403/404/409/429/500.

| Method, path | Body / query | Response |
|---|---|---|
| `GET /api/health` | | `{ version, lexicon_version, domain, sections, modes, clients, anonymous, workspace, operator_keys[], limits{max_calls_per_job, max_calls_per_day, calls_used_today} }` |
| `GET /api/lexicon` | | `{ version, entities[], findings[] }` (display fields only) |
| `GET /api/case-sets` | | `[{ id, name, n_cases, n_perturbations, approved, source }]` — packaged sample, `data/` set if approved, plus uploads in the workspace |
| `POST /api/analyse` | general form `{ documents{<section id>: text}, titles?, reasoning, answer, truth?, entity?, lexicon_id? }`; haematology shorthand `{ reports{clinical,…}, … }` still accepted | `{ case (with sections), lexicon{id,domain,version,entities,findings}, claims[], grounding, map, parsed_answer, oracle, domain }` where `oracle` is `"truth"` when supplied, else `"extracted"` (the documents' own assertions) |
| `GET /api/lexicons` | | the built-in lexicon plus uploads visible to the workspace: `[{ id, name, domain, version, sections, n_findings, n_entities, source }]` |
| `POST /api/lexicons` | `{ lexicon: <json text>, name? }` | `201` meta; `400 bad_lexicon` when the loader rejects it |
| `GET /api/lexicon?id=` | | `{ version, domain, sections, entities[], findings[] }` for one lexicon (default when `id` is omitted) |
| `POST /api/uploads` | multipart or JSON `{ cases: <jsonl text>, perturbations?: <jsonl text>, lexicon?: <json text>, name }` | `{ upload_id, n_cases, n_perturbations, problems[] }` — rejected (400) when any error-severity problem |
| `POST /api/jobs` | `{ mode: "audit", client: { kind, endpoint?, model, api_key? }, case_set, efforts[], runs, variants?, seed?, rule?, judge?: false, notes? }` | `202 { job_id }` |
| `GET /api/jobs` | | jobs in the workspace: `[{ job_id, status, created, progress, summary_headline? }]` |
| `GET /api/jobs/{id}` | | `{ job_id, status, created, started, finished, progress{done,total,ok,errors,eta_s}, config (no key), error?, headline? }` |
| `DELETE /api/jobs/{id}` | | cancels a queued or running job (`status: cancelled`); traces already written are kept and scored |
| `GET /api/jobs/{id}/bundle/{path}` | | the exported viewer bundle files (`index.json`, `cases/<id>.json`); the viewer loads `?bundle=/api/jobs/{id}/bundle/` |
| `GET /api/jobs/{id}/files/{name}` | | `summary.json`, `report.md`, `traces.jsonl`, `long.csv`, `manifest.json` as downloads |
| `GET /` and static | | the built viewer (`--static viewer/dist`) when present |

Status values: `queued → running → scoring → exporting → done`, or `failed`,
`cancelled`, `interrupted` (server restarted mid-run; resumable with the same
job id via `POST /api/jobs/{id}/resume`, which re-requires the key).

## 4. Job execution

- One worker thread per server by default (`--workers 1`), a FIFO queue; the
  server stays responsive while a job runs.
- A job directory `jobs/<job_id>/` under `--root`: `job.json` (config without
  key, status, timestamps), `run/` (a normal run directory with manifest,
  traces and scores), `export/` (the viewer bundle).
- `experiment.run_experiment` gains a `should_stop` callable checked between
  jobs so a cancel takes effect within one call.
- Audit jobs use `experiment.plan` with `allow_unreviewed` only for uploads that
  the uploader marked approved; the packaged sample is approved.
- `analyse` requests are bounded: reports ≤ 50 KB each, reasoning ≤ 200 KB.

## 5. Viewer "Analyse" tab

Routes `#/analyse` (chooser), `#/analyse/trace`, `#/analyse/audit`, `#/jobs`,
`#/jobs/:id`. Settings hold the API base URL (default: same origin) and the
bearer token (localStorage, never in URLs). The trace form posts to
`/api/analyse` and renders the result with the existing grounding and
constellation components from an in-memory single-trace bundle. The audit form
lists case sets, takes the client kind, endpoint, model and key (password field,
not persisted), efforts and runs, and submits a job; the jobs page polls every
few seconds and, when done, opens the cohort view on the job's bundle.

## 6. Packaging

`Dockerfile` (multi-stage: Node builds `viewer/dist`; Python slim image installs
the package and copies `dist`) and `docker-compose.yml` with a `./serve-data`
volume. `traceaudit serve --root /data --static /app/viewer/dist --port 8080`.
Environment: `TRACEAUDIT_TOKENS`, `TRACEAUDIT_ALLOW_CLIENTS`, `TRACEAUDIT_ANONYMOUS`.
