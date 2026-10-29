import { Fragment, type ReactNode } from 'react';
import { Chip } from '../components/Shared';
import { ApiTry } from './ApiTry';
import { Code } from './Code';
import { INCIDENT_REQUEST, stringify } from './examples';
import { SiteShell, REPO_URL } from './SiteShell';
import { Typed } from './Typed';
import { useHealth } from './useHealth';

const HEADLINE = 'Does the reasoning hold up?';

/** `#/` with no bundle: the front page. */
export function Landing() {
  const health = useHealth();
  const wire = health.status === 'ok'
    ? `GET /api/health  200  version ${health.health.version}  clients ${health.health.clients.join(', ')}  anonymous ${health.health.anonymous}` +
      (health.health.limits ? `  budget today ${health.health.limits.calls_used_today}/${health.health.limits.max_calls_per_day} model calls` : '')
    : health.status === 'down' ? `GET /api/health  failed: ${health.error}` : '';
  return (
    <SiteShell active="home">
      <main>
        <section className="hero">
          <div className="sheet">
            <p className="kicker">traceaudit, reasoning-trace analytics. A research instrument you can run against the live service below.</p>
            <Typed as="h1" text={HEADLINE} speed={38} startDelay={200} />
            <p className="lede">
              A reasoning model writes a long chain of thought before it answers. traceaudit grades every factual claim in that chain against
              the documents the model was given, then changes the documents and asks whether the answer moves, and whether the trace says why.
              Any domain, no model of its own, standard-library Python.
            </p>
            <div className="actions">
              <a className="btn primary" href="#/" onClick={(e) => { e.preventDefault(); document.getElementById('try')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}>Send a trace now</a>
              <a className="btn" href="#/docs">Read the manual</a>
              <a className="btn" href="#/docs/api">API reference</a>
              <a className="btn quiet" href="#/analyse">Open the viewer</a>
            </div>
            <p className="wire" aria-label="Live service status">
              {health.status === 'loading' ? <span className="muted">connecting to the service</span> : <Typed text={wire} speed={10} startDelay={1400} cursor={false} />}
            </p>
          </div>
        </section>

        <section className="section" aria-labelledby="three">
          <div className="sheet">
            <h2 id="three">Three questions a trace has to answer</h2>
            <p className="lede">Each one is a measurement, not an opinion, and each has a validation path a reviewer can rerun.</p>
            <div className="cols">
              <div>
                <h3>Is it grounded?</h3>
                <p>Every document becomes a table of facts with ids. Every sentence in the report that cites a fact is graded against it:
                  agree, disagree, unverifiable, or the fact was never mentioned. Twenty-four checks run over the result.</p>
                <p><a href="#/docs/ledger">The fact ledger</a></p>
              </div>
              <div>
                <h3>Is it faithful?</h3>
                <p>Grounding says the trace is true. Faithfulness asks whether it reflects what drove the answer. traceaudit flips a decisive
                  fact, drops an anchor, plants an authority cue, removes the facts the model called load-bearing, and reruns the model.
                  A changed answer with no disclosure is a silent change.</p>
                <p><a href="#/docs/probes">The probes</a></p>
              </div>
              <div>
                <h3>Is it provable?</h3>
                <p>Every trace records the hash of the exact prompt it was sent and of its raw reasoning and answer. Every run commits to one
                  hash over its inputs before any model is called. A reviewer recomputes all of it with one command.</p>
                <p><a href="#/docs/provenance">Provenance</a></p>
              </div>
            </div>
          </div>
        </section>

        <section className="section" id="try" aria-labelledby="try-h">
          <div className="sheet">
            <h2 id="try-h">Send a trace to the live API</h2>
            <p className="lede">
              This sheet posts to <code>/api/analyse</code> on the service behind this page. The example is a software incident: three documents,
              a model's reasoning, an answer. Edit anything and send again. Nothing here calls a language model.
            </p>
            <ApiTry method="POST" path="/api/analyse" body={stringify(INCIDENT_REQUEST)} sendLabel="Send to /api/analyse"
              note="Anonymous requests are rate limited per address." summary={(json) => <AnalyseSummary data={json} />} />
            <p className="muted small">
              The reasoning above contains a deliberate error: it says CPU was saturated while the alert says CPU was normal. The grader marks that
              claim as disagreeing with its fact. The answer still names the right cause, which is exactly the gap between a right answer and a
              faithful explanation.
            </p>
          </div>
        </section>

        <section className="section" aria-labelledby="produces">
          <div className="sheet">
            <h2 id="produces">What a run produces</h2>
            <div className="figures">
              <div><div className="figure">24</div><div className="label">checks on every structured trace, each a named pass or fail</div></div>
              <div><div className="figure">5</div><div className="label">kinds of intervention: decisive, anchor loss, neutral, authority, ablation</div></div>
              <div><div className="figure">3</div><div className="label">disclosure rules, D1 headline and D2, D3 as sensitivity analyses</div></div>
              <div><div className="figure">1</div><div className="label">inputs hash per run, the value to publish in a pre-registration</div></div>
            </div>
            <p style={{ marginTop: 28 }}>
              A run directory holds the manifest, every trace as one JSON line, the graded claims, the probe records and a summary with Wilson
              intervals and case-clustered bootstrap confidence intervals. The viewer reads the exported bundle; the statistics export a long table
              for mixed-effects models in R.
            </p>
            <p><a href="#/docs/cli">Command line</a> and <a href="#/docs/validation">validation and statistics</a>.</p>
          </div>
        </section>

        <section className="section" aria-labelledby="probes">
          <div className="sheet">
            <h2 id="probes">How the interventions work</h2>
            <p className="lede">Each variant of a case is one specified change. The model sees the variant, never the change.</p>
            <div className="table-scroll">
              <table className="data">
                <thead><tr><th>Kind</th><th>What changes</th><th>What should happen</th><th>What is scored</th></tr></thead>
                <tbody>
                  <tr><td>Decisive</td><td>One fact (and its co-edits) flips so that another candidate fits the documents best</td><td>The answer changes and the trace states the new value</td><td>disclosed, silent, missed, or missed but mentioned</td></tr>
                  <tr><td>Anchor loss</td><td>A supporting fact becomes untested</td><td>The answer stands but hedges</td><td>hedge rate</td></tr>
                  <tr><td>Neutral</td><td>Presentation only: order, ids, synonyms</td><td>Nothing</td><td>spurious change rate</td></tr>
                  <tr><td>Authority</td><td>A context fact: the referrer's working diagnosis, right or wrong</td><td>Right answer, cue acknowledged</td><td>followed, resisted, acknowledged</td></tr>
                  <tr><td>Ablation</td><td>The facts the model itself called load-bearing are removed</td><td>The answer changes or hedges</td><td>load-bearing rate</td></tr>
                </tbody>
              </table>
            </div>
            <p style={{ marginTop: 18 }}>
              Before any real model is paid for, a simulated model with planted fault rates runs the whole pipeline. The probes have to recover the
              rates that were planted, within tolerance, on six grids. <a href="#/docs/validation">How the harness is validated</a>.
            </p>
          </div>
        </section>

        <section className="section" aria-labelledby="prov">
          <div className="sheet">
            <h2 id="prov">Proof, not trust</h2>
            <div className="cols two">
              <div>
                <h3>Per trace</h3>
                <Code lang="json" copy={false}>{`"provenance": {
 "prompt_sha256":    "sha256(system + NUL + user)",
 "reasoning_sha256": "sha256(raw reasoning)",
 "answer_sha256":    "sha256(raw answer)"
}`}</Code>
                <p>The prompt hash is the proof that nothing named the variant to the model. The other two show the released traces are the ones scored.</p>
              </div>
              <div>
                <h3>Per run</h3>
                <Code lang="shell" copy={false}>{`traceaudit manifest verify RUN \\
  --cases cases.jsonl --perturbations perts.jsonl
# provenance ok: 99 traces, reasoning 99, answer 99,
# prompt 99 verified / 0 unverified`}</Code>
                <p>The inputs hash commits to the prompt, cases, perturbations and lexicon before the run. It goes in the pre-registration.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="section" aria-labelledby="status">
          <div className="sheet">
            <h2 id="status">Where the research stands</h2>
            <ul>
              <li>The reference study is mature B-cell neoplasm diagnosis, run on synthetic cases where every fact is known. Clinical content is
                marked draft until a haematologist signs it off; nothing here is medical advice.</li>
              <li>The harness is validated against a simulated model. No open-weight pilot with raw chain of thought has been reported yet; a pilot
                on a hosted model with summarised thinking is documented in the repository and is explicitly not comparable to the planned study.</li>
              <li>The grader has no measured error yet. Two raters are blind-labelling a sample; the agreement statistics ship with the tool.</li>
              <li>Nothing is pre-registered yet. The deviations log is empty by design until it is.</li>
            </ul>
            <p><a href="#/docs/limits">Known limits and how to cite</a>.</p>
          </div>
        </section>

        <section className="section" aria-labelledby="install">
          <div className="sheet">
            <h2 id="install">Run it yourself</h2>
            <div className="cols two">
              <div>
                <h3>Install and demo, no model needed</h3>
                <Code lang="shell">{`git clone ${REPO_URL}.git
cd traceaudit
python3 -m pip install -e .
traceaudit demo --out runs/demo --judge
traceaudit report runs/demo`}</Code>
                <p>Python 3.10 or later, standard library only at runtime, so it runs inside a trusted research environment.</p>
              </div>
              <div>
                <h3>Audit a structured trace artefact</h3>
                <Code lang="shell">{`traceaudit ledger audit tests/fixtures/enable_trace_case_003.md
traceaudit ledger audit artefacts/ --summary --review-sheet review.csv`}</Code>
                <p>Twenty-four checks, pass rates across a directory, and every grade as a row a human can dispute.</p>
              </div>
            </div>
            <p style={{ marginTop: 20 }}><a href="#/docs/quickstart">Quick start</a>, <a href="#/docs/service">self-hosting</a>, <a href="#/docs/domains">bring your own domain</a>.</p>
          </div>
        </section>
      </main>
    </SiteShell>
  );
}

// ---- reading an /api/analyse response ---------------------------------------------------------------------------

interface Seg { text: string; citation_ids?: string[]; cited?: Array<{ id: string; grade: string; field?: string; value?: string }>; uncited_assertions?: Array<{ field: string; stated: string; grade: string }>; informative?: boolean }
interface AnalyseLike {
  decision?: string | null; truth?: string | null;
  metrics?: Record<string, unknown>;
  checks?: Array<{ id: string; title: string; status: string; detail?: string }>;
  sections?: Array<{ title: string; segments: Seg[] }>;
  answer?: { entity?: string | null; hedged?: boolean } | null;
  warnings?: string[];
}

const GRADE_TONE: Record<string, [string, string]> = {
  agree: ['good', '✓'], disagree: ['bad', '✗'], unverifiable: ['warn', '?'], not_mentioned: ['neutral', '–'], not_found: ['bad', '!'], reference: ['neutral', 'w'],
};

export function AnalyseSummary({ data }: { data: unknown }) {
  const r = (data ?? {}) as AnalyseLike;
  const m = r.metrics ?? {};
  const rate = typeof m.grounding_rate === 'number' ? `${Math.round(m.grounding_rate * 100)}%` : 'n/a';
  const failed = r.checks?.filter((c) => c.status === 'FAIL') ?? [];
  return (
    <div>
      <div className="result-tiles">
        <Tile value={rate} label="grounding rate: cited claims that agree with their fact" />
        <Tile value={String(m.facts ?? '–')} label="facts read from the documents" />
        <Tile value={String(m.cited_agree ?? 0)} label="citations agree" />
        <Tile value={String(m.cited_disagree ?? 0)} label="citations disagree" />
        <Tile value={`${m.checks_failed ?? 0}/${m.checks_total ?? 0}`} label="checks failed" />
        <Tile value={r.answer?.entity ?? r.decision ?? '–'} label={r.answer?.hedged ? 'answer, hedged' : 'answer'} />
      </div>
      {r.sections?.map((s) => (
        <Fragment key={s.title}>
          <h4>{s.title}</h4>
          <ul className="graded">
            {s.segments.map((seg, i) => (
              <li key={i}>
                <p>{seg.text}</p>
                <div className="cites">
                  {(seg.cited ?? []).map((c) => {
                    const [tone, icon] = GRADE_TONE[c.grade] ?? ['neutral', '·'];
                    return <Chip key={c.id} tone={tone} icon={icon} title={`${c.field ?? ''} ${c.value ?? ''}`.trim()}>{c.id} {c.grade.replace('_', ' ')}</Chip>;
                  })}
                  {(seg.uncited_assertions ?? []).map((u, j) => <Chip key={j} tone="warn" icon="!">{u.field}: {u.stated}, uncited</Chip>)}
                  {!(seg.cited?.length || seg.uncited_assertions?.length) && <span className="muted small">no factual claim</span>}
                </div>
              </li>
            ))}
          </ul>
        </Fragment>
      ))}
      {failed.length > 0 && (
        <>
          <h4>Checks failed</h4>
          <ul>{failed.map((c) => <li key={c.id}><code>{c.id}</code> {c.title}{c.detail ? `: ${c.detail}` : ''}</li>)}</ul>
        </>
      )}
      {r.warnings && r.warnings.length > 0 && <p className="muted small">Warnings: {r.warnings.join('; ')}</p>}
    </div>
  );
}

function Tile({ value, label }: { value: ReactNode; label: string }) {
  return <div><div className="value">{value}</div><div className="label">{label}</div></div>;
}
