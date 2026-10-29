import { Code } from '../Code';
import { REPO_URL } from '../SiteShell';

export default function Quickstart() {
  return (
    <>
      <h2 id="install">Install</h2>
      <p>Python 3.10 or later. The runtime has no dependencies outside the standard library, which is checked in continuous integration.</p>
      <Code lang="shell">{`git clone ${REPO_URL}.git
cd traceaudit
python3 -m pip install -e .
traceaudit --help`}</Code>
      <p className="muted">For development add the extras, <code>pip install -e ".[dev]"</code>, which brings pytest and ruff.</p>

      <h2 id="demo">The demo</h2>
      <p>
        The demo runs the whole text-mode pipeline on the packaged six-case sample with a simulated model, then scores it, judges it and writes a
        report. It takes under a minute and calls nothing outside your machine.
      </p>
      <Code lang="shell">{`traceaudit demo --out runs/demo --judge
traceaudit report runs/demo
traceaudit manifest verify runs/demo --cases traceaudit/domains/haematology/sample_cases.jsonl \\
  --perturbations traceaudit/domains/haematology/sample_perturbations.jsonl`}</Code>
      <p>
        <code>runs/demo/</code> now holds <code>manifest.json</code>, <code>traces.jsonl</code>, the graded claims, the probe records,
        <code> summary.json</code>, <code>report.md</code> and an <code>export/</code> bundle. Open the bundle in the viewer: start the service with
        <code> --static viewer/dist</code> and press Load bundle, or serve <code>runs/demo/export</code> with any static file server and open the
        viewer with <code>?bundle=&lt;url&gt;</code>.
      </p>

      <h2 id="audit">Audit an artefact</h2>
      <p>
        A structured trace artefact is a Markdown document that an engine produced for one case: the fact tables it was shown, its thinking, its
        report with citation ids, optionally its rationale and an ablation. The repository ships one as a test fixture.
      </p>
      <Code lang="shell">{`traceaudit ledger audit tests/fixtures/enable_trace_case_003.md
traceaudit ledger audit artefacts/ --summary --review-sheet review.csv --json > audit.json`}</Code>
      <p>
        The first prints the 24 checks and the metrics for one artefact. The second takes a directory, prints pass rates per check across every
        artefact and writes one CSV row per citation grade and per uncited assertion, so a human can scan for grades to dispute. Disputed rows become
        test fixtures.
      </p>

      <h2 id="serve">Start the service</h2>
      <Code lang="shell">{`cd viewer && npm ci && npm run build && cd ..
traceaudit serve --root serve-data --static viewer/dist --port 8080`}</Code>
      <p>
        That is this site, on your machine: the landing page, the manual, the viewer and the API under <code>/api/</code>. By default anonymous
        requests may analyse but not start jobs; see <a href="#/docs/service">self-hosting</a> for tokens, operator keys and limits.
      </p>

      <h2 id="model">Point at a model</h2>
      <p>
        Any client the package knows can run a study: <code>sim</code>, <code>ollama</code>, <code>openai</code> (any OpenAI-compatible
        endpoint) and <code>anthropic</code>. Keys are read from the environment or passed per job; they are held in memory and never written to disk
        or into a manifest. The open-weight path reads the raw reasoning channel; hosted APIs that return summarised thinking are flagged as such in
        the manifest.
      </p>
      <Code lang="shell">{`traceaudit run --client ollama --model gpt-oss:20b \\
  --cases pilot/cases.jsonl --perturbations pilot/perturbations.jsonl \\
  --efforts low,medium,high --runs 3 --out runs/pilot-20b
traceaudit score runs/pilot-20b --rule D1 --verify lexical
traceaudit export runs/pilot-20b -o runs/pilot-20b/export`}</Code>
      <p>
        The manifest records the model digest from the server, and the run aborts if the digest changes mid-run. Resume an interrupted run by
        repeating the command: finished traces are skipped.
      </p>
    </>
  );
}
