import { Code } from '../Code';

export default function Service() {
  return (
    <>
      <h2 id="run">Run it</h2>
      <p>
        The service is one process on the standard library's HTTP server with a worker thread for jobs. It is designed to run as a public demo on
        synthetic data and, unchanged, as an on-premises install inside a trusted research environment where documents must not leave the network.
      </p>
      <Code lang="shell">{`traceaudit serve --root serve-data --static viewer/dist --port 8080 \\
  --anonymous analyse --rate 60 \\
  --tokens "$(cat tokens.txt)" \\
  --allow-clients ollama,openai`}</Code>
      <ul>
        <li><code>--root</code> holds jobs (<code>jobs/&lt;id&gt;/job.json</code>, a normal run directory and the exported bundle) and uploads.</li>
        <li><code>--static</code> serves the built viewer and this site; without it the root answers with a JSON pointer to <code>/api/health</code>.</li>
        <li><code>--workers</code> is the job queue width, default one, because the model server is the bottleneck and parallel requests can
          change batching and therefore sampling.</li>
        <li>The policy flags have environment variable twins (<code>TRACEAUDIT_TOKENS</code>, <code>TRACEAUDIT_ANONYMOUS</code>,
          <code> TRACEAUDIT_ALLOW_CLIENTS</code>, <code>TRACEAUDIT_OPERATOR_KEYS</code>, <code>TRACEAUDIT_MAX_CALLS_PER_JOB</code>,
          <code> TRACEAUDIT_MAX_CALLS_PER_DAY</code>), which is how the container deployment sets them.</li>
      </ul>

      <h2 id="keys">Keys and tokens</h2>
      <ul>
        <li><strong>Bearer tokens</strong> map to workspaces (<code>--tokens token:workspace,…</code>). Jobs and uploads are scoped to the workspace;
          anonymous requests use the workspace <code>public</code>.</li>
        <li><code>--anonymous analyse</code> (default) lets unauthenticated callers analyse, rate limited per address; <code>none</code> requires a
          token for everything; <code>all</code> allows anonymous jobs, meant for demo instances on the simulated model or a capped operator key.</li>
        <li><strong>Model keys</strong> arrive in the job body, live in memory for the job and are never written to disk, never returned by any
          endpoint and never placed in a manifest. The job record keeps the client kind, endpoint and model tag only.</li>
        <li><strong>Operator keys</strong> (<code>--operator-key anthropic=ANTHROPIC_API_KEY</code>) let jobs of that kind run on a key the site
          holds, read from the named environment variable at start-up. The health endpoint lists which kinds have one.</li>
      </ul>

      <h2 id="limits">Limits</h2>
      <table className="data">
        <thead><tr><th>Limit</th><th>Default</th><th>Error when exceeded</th></tr></thead>
        <tbody>
          <tr><td>analyse: each document</td><td>50 KB</td><td><code>too_large</code> 400</td></tr>
          <tr><td>analyse: reasoning</td><td>200 KB</td><td><code>too_large</code> 400</td></tr>
          <tr><td>ledger: Markdown artefact</td><td>2 MB</td><td><code>too_large</code> 400</td></tr>
          <tr><td>model calls per job</td><td>200</td><td><code>job_too_large</code> 400</td></tr>
          <tr><td>operator-key calls per day</td><td>2000</td><td><code>budget_exhausted</code> 429</td></tr>
          <tr><td>anonymous analyse requests</td><td>60 per minute per address</td><td><code>rate_limited</code> 429</td></tr>
        </tbody>
      </table>

      <h2 id="public">This public instance</h2>
      <p>
        The site you are reading is the built viewer on Cloudflare Pages. Requests to <code>/api/*</code> are proxied by a Pages Function to the
        service, which runs as a Cloudflare Container built from the repository's Dockerfile. Both deploy from the main branch on every push, after
        the test suite and the quick validation grids pass. The instance allows anonymous analyse and anonymous jobs on the simulated model; jobs on
        the operator's hosted-model key are capped per job and per day, and the current spend is visible in <code>/api/health</code>.
      </p>
      <p>
        <code>/api/analyse</code> and <code>/api/ledger</code> compute and return; they write nothing. Jobs and uploads are stored under the public
        workspace of this demo instance and should contain synthetic data only.
      </p>
    </>
  );
}
