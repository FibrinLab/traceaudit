# traceaudit

Trace analytics for LLM reasoning. Give it the documents a model read, the model's
reasoning and its answer, and it tells you whether the reasoning is grounded in the
documents, whether the answer changes for the right reasons, and whether a suggested
answer is followed silently. Paste a single trace for an instant grounding view, or
point it at a model endpoint to audit it with counterfactual, neutral and authority
probes across a case set and three reasoning efforts.

It is domain-agnostic. A **domain** is one JSON file, the lexicon: the document
sections a case is made of, the facts a document can assert and the words that name
them, the answer categories, and which facts each category expects. Everything else,
from extraction to the dashboard, reads the lexicon. Bring your own
([docs/bring-your-own-domain.md](docs/bring-your-own-domain.md); a software-incident
example is in `examples/`), or start from the packaged reference domain,
`traceaudit/domains/haematology/`, built for a study of mature B-cell neoplasm
diagnosis ([docs/00-project-spec.md](docs/00-project-spec.md)). It is not loaded
unless you ask for it.

Two ways in. If your pipeline already emits **facts with ids** and traces that
**cite** them (a report whose segments carry citation ids, a rationale with a
differential, an ablation arm), feed the artefact straight to the fact ledger:
every citation is checked against its fact, ignored facts are listed, the
differential and criteria are checked, and the ablation tells you whether the
stated discriminators were load-bearing. If you only have prose, the lexicon
extractor turns documents into facts first.

```bash
traceaudit ledger audit tests/fixtures/enable_trace_case_003.md      # 24 checks on a structured trace artefact
```

What a researcher gets, for any domain:

| Need | Tool |
|---|---|
| Describe the domain | a lexicon (upload in the app, or a file); validated on load |
| Get cases | upload documents with known answers (`traceaudit cases build`), or write a generator like the haematology one |
| Check a single output | Analyse tab or `POST /api/analyse`: every factual claim graded against the documents, answer parsed, reasoning graph |
| Audit a structured trace | `POST /api/ledger` or `traceaudit ledger audit`: citations graded against facts, coverage, differential and criteria checks, ablation verdict ([specs/18-fact-ledger.md](specs/18-fact-ledger.md)) |
| Audit a model | counterfactual edits derived from the lexicon's own discriminator table (or authored rows), neutral edits, authority cues, three reasoning efforts, 5 runs |
| Trust the instruments | a fault-injecting simulated model and a validation grid that must recover planted rates |
| Report | case-clustered intervals, effort contrasts, viewer dashboard with exportable figures, a long table for mixed-effects models |
| Human judgement | blinded rating mode with a rubric, agreement statistics, an LLM judge on the same rubric |

Standard-library only at runtime, so it runs inside locked-down research
environments. Specifications are in [`specs/`](specs/README.md); the reference study
is described in [`docs/00-project-spec.md`](docs/00-project-spec.md).

## Install

```bash
pip install -e ".[dev]"
```

## Quick start (no model needed)

```bash
traceaudit demo --out runs/demo --judge        # SimulatedModel end to end on the packaged 6-case sample
traceaudit report runs/demo                    # Markdown summary of summary.json
traceaudit validate-probes --grid quick        # probes must recover planted fault rates
```

The demo writes a viewer bundle to `runs/demo/export/`; open it with the viewer
(`viewer/`, see its README) or `traceaudit export ... --with-viewer viewer/dist`.

## Study workflow

```bash
traceaudit casegen -o data/cases.jsonl --per-entity 20 --seed 20261020     # drafts for haematologist review
traceaudit review-sheet data/cases.jsonl -o review.csv                     # … review … then --import-csv
traceaudit perturb data/cases.jsonl -o data/perturbations.jsonl --seed 20261020
traceaudit validate data/cases.jsonl --perturbations data/perturbations.jsonl
traceaudit run --client ollama --model gpt-oss:120b --cases data/cases.jsonl \
    --perturbations data/perturbations.jsonl --out runs/$(date -u +%Y%m%dT%H%M%SZ)-main --runs 5
traceaudit score runs/<run_id> --rule D1 --verify lexical
traceaudit export runs/<run_id> -o runs/<run_id>/export --study-id pilot-1 --rating-n 100
traceaudit import-ratings ratings-pilot-1-R01.jsonl ratings/
traceaudit agreement ratings/pilot-1 --judge runs/<run_id>/judge.jsonl
```

Only cases and perturbations with `review.status: approved` are run; drafts need
`--allow-unreviewed`. Every run writes a manifest (model digest, prompt hash, lexicon
hash, seeds); `traceaudit manifest check <run_dir>` enforces completeness.

## Run it as a service

```bash
traceaudit serve --root serve-data --static viewer/dist --port 8080
```

Open http://127.0.0.1:8080. Nothing domain-specific is built in: pick a starter
lexicon from `examples/` (or upload your own) in the **Analyse** tab, paste a
trace to ground it immediately, or upload cases and submit an audit job that runs
the full probe suite against a model endpoint and opens the results in the cohort
dashboard. `--domain haematology` offers the packaged reference domain and its
sample cases as well; it is off by default. Tokens (`--tokens token:workspace`) scope jobs and uploads;
anonymous visitors can analyse traces but not run jobs unless `--anonymous all`.
`--allow-clients sim,ollama,openai,anthropic` decides which model clients jobs may
use (the public demo default is the simulated model only). Model keys travel in the
job request, are held in memory for the job, and are never written to disk.

### Let people use it on your key

The public configuration lets visitors analyse traces and run audits on a key the
site holds, within spend caps:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
traceaudit serve --static viewer/dist --anonymous all --allow-clients sim,anthropic \
    --operator-key anthropic=ANTHROPIC_API_KEY --max-calls-per-job 200 --max-calls-per-day 2000
```

The key is read from the environment, held in memory, and never written to disk or
returned by the API. Each audit is capped per job and the site has a daily call
budget; the Audit form shows what remains. Visitors may still paste their own key,
which bypasses the daily budget but not the per-job cap.

### Deploy

```bash
cp .env.example .env            # put your key in .env (git-ignored)
docker compose up --build       # http://localhost:8080, data in ./serve-data
```

**Cloudflare.** The viewer is a static site on Pages and the service runs as a
Cloudflare Container behind a Worker; a Pages Function proxies `/api/*` to it.

```bash
cd cloudflare && npm install && npx wrangler deploy          # builds the Dockerfile, deploys the container (Docker must be running)
npx wrangler secret put ANTHROPIC_API_KEY                     # the site key
cd ../viewer && npm run build && npx wrangler pages deploy dist --project-name traceaudit
npx wrangler pages secret put API_ORIGIN --project-name traceaudit   # https://traceaudit.<your-subdomain>.workers.dev
```

The container's disk is ephemeral: finished jobs disappear when it sleeps. Use a
host with a volume for durable results.

`fly.toml` and `render.yaml` are also included: on Fly, `fly launch --copy-config --no-deploy`,
`fly secrets set ANTHROPIC_API_KEY=...`, `fly deploy`; on Render, connect the repository,
set `ANTHROPIC_API_KEY` in the dashboard and deploy the blueprint.

The API is documented in [specs/17-service.md](specs/17-service.md).

## Layout

| Path | Purpose |
|---|---|
| `traceaudit/lexicon.json` | the only domain-specific file (built from `traceaudit/tools/build_lexicon.py`) |
| `traceaudit/extract.py`, `segment.py`, `grounding.py` | assertion grammar, claim typing, grounding labels |
| `traceaudit/perturb.py`, `probes.py` | decisive / neutral / anchor-loss / authority edits and their scoring |
| `traceaudit/clients/` | Ollama, OpenAI-compatible and in-process clients; harmony parser |
| `traceaudit/experiment.py`, `pipeline.py`, `stats.py` | orchestration, scoring, case-clustered bootstrap, agreement |
| `traceaudit/simulate.py`, `validation.py` | fault-injecting model and probe-validation grid |
| `traceaudit/judge.py`, `export.py` | LLM-as-judge rubric and viewer bundle |
| `traceaudit/serve.py` | HTTP service: analyse traces, run audit jobs, serve the viewer |
| `traceaudit/casegen.py` | synthetic case generation (dev-time) |
| `viewer/` | React + TypeScript trace viewer |
| `analysis/models.R` | pre-registered mixed-effects models |

## Licence

Apache-2.0 (code); CC BY 4.0 (synthetic cases).
