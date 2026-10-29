import { ApiTry } from '../ApiTry';
import { Code } from '../Code';
import { INCIDENT_REQUEST, JOB_REQUEST, LEDGER_REQUEST, LEXICON_UPLOAD_REQUEST, stringify } from '../examples';
import { AnalyseSummary } from '../Landing';

function Sig({ method, path }: { method: string; path: string }) {
  return <p className="sig"><span className="m">{method}</span> <code>{path}</code></p>;
}

export default function Api() {
  return (
    <>
      <h2 id="conventions">Conventions</h2>
      <ul>
        <li>Every request and response is JSON unless stated. Errors are <code>{'{'} "error": {'{'} "code", "message" {'}'} {'}'}</code> with the
          HTTP status.</li>
        <li>Authentication is optional: <code>Authorization: Bearer &lt;token&gt;</code> maps to a workspace. Without it you are in the
          <code> public</code> workspace with whatever the instance allows anonymously (see <code>anonymous</code> in the health response). Tokens
          never go in a URL.</li>
        <li>The sheets on this page send from your browser to the service behind this site, or to the API base set under Settings in the viewer.
          Each one shows the equivalent <code>curl</code>. Nothing here calls a language model except a job with a non-simulated client.</li>
        <li>Keys for your own model go in the job body and are held in memory for the job only.</li>
      </ul>

      <section className="endpoint">
        <h2 id="health">Health</h2>
        <Sig method="GET" path="/api/health" />
        <p>What this instance is: version, modes, allowed client kinds, anonymous policy, your workspace, which kinds run on an operator key, and today's budget.</p>
        <ApiTry method="GET" path="/api/health" />
        <dl className="fields">
          <dt>version</dt><dd>traceaudit package version</dd>
          <dt>modes</dt><dd><code>["analyse", "audit"]</code></dd>
          <dt>clients</dt><dd>client kinds jobs may use on this instance</dd>
          <dt>anonymous</dt><dd><code>analyse</code>, <code>none</code> or <code>all</code></dd>
          <dt>operator_keys</dt><dd>client kinds that run on the site's own key, with <code>limits.max_calls_per_job</code>, <code>max_calls_per_day</code>, <code>calls_used_today</code></dd>
          <dt>domain, sections, lexicon_version</dt><dd>the operator-configured default lexicon, when there is one; this instance ships none and asks you to choose</dd>
        </dl>
      </section>

      <section className="endpoint">
        <h2 id="lexicons">Lexicons</h2>
        <Sig method="GET" path="/api/lexicons" />
        <p>The lexicons you can analyse with: the packaged examples (<code>source: "example"</code>) and your workspace's uploads.</p>
        <ApiTry method="GET" path="/api/lexicons" />
        <Sig method="GET" path="/api/lexicon?id=example:incident-triage" />
        <p>One lexicon's display data: version, domain, sections, entities (id, display, in scope, parent) and findings (id, display, kind).</p>
        <ApiTry method="GET" path="/api/lexicon?id=example:incident-triage" />
        <Sig method="POST" path="/api/lexicons" />
        <p>
          Upload a lexicon as JSON text. Returns <code>201</code> with its row as <code>GET /api/lexicons</code> lists it, or <code>400 bad_lexicon</code> with the
          loader's reason. The sheet below is a skeleton that the loader will reject, on purpose, so you can see the message; paste a real lexicon to
          upload one. See <a href="#/docs/domains">bring your own domain</a>.
        </p>
        <ApiTry method="POST" path="/api/lexicons" body={stringify(LEXICON_UPLOAD_REQUEST)} note="Uploads persist in the public workspace of a demo instance." />
      </section>

      <section className="endpoint">
        <h2 id="analyse">Analyse a trace</h2>
        <Sig method="POST" path="/api/analyse" />
        <p>
          Documents, a reasoning trace and an answer in; a fact-ledger result out. The documents are read into facts with the chosen lexicon, the
          reasoning and answer become a trace whose factual claims cite the facts they restate, and the ledger grader runs. No model is called.
        </p>
        <dl className="fields">
          <dt>lexicon_id</dt><dd><span className="t">string, required on this instance</span> an id from <code>GET /api/lexicons</code></dd>
          <dt>documents</dt><dd><span className="t">object</span> section id to text, 50 KB each; section ids outside the lexicon are kept with their own titles</dd>
          <dt>titles</dt><dd><span className="t">object, optional</span> display titles per section id</dd>
          <dt>reasoning</dt><dd><span className="t">string</span> the chain of thought, up to 200 KB</dd>
          <dt>answer</dt><dd><span className="t">string</span> the final answer text; the entity is parsed from it with the lexicon</dd>
          <dt>truth</dt><dd><span className="t">object, optional</span> finding id to <code>pos</code> or <code>neg</code>; when given it overrides the documents' readings and <code>oracle</code> becomes <code>truth</code></dd>
          <dt>entity</dt><dd><span className="t">string, optional</span> the correct answer, enabling the decision check</dd>
        </dl>
        <ApiTry method="POST" path="/api/analyse" body={stringify(INCIDENT_REQUEST)} summary={(json) => <AnalyseSummary data={json} />} />
        <h3>Response</h3>
        <dl className="fields">
          <dt>decision, truth, candidates</dt><dd>the parsed answer entity, the supplied truth if any, the lexicon's in-scope entities</dd>
          <dt>facts[]</dt><dd>every fact with id, source, section, field, value, evidence, polarity, and whether it was referenced in thinking, cited in the report, or ignored</dd>
          <dt>sections[]</dt><dd>report sections; each segment has <code>text</code>, <code>citation_ids</code>, <code>cited[{'{'}id, grade, field, value{'}'}]</code>, <code>uncited_assertions[]</code>, <code>informative</code></dd>
          <dt>checks[]</dt><dd>the 24 checks, <code>{'{'}id, title, status, detail{'}'}</code></dd>
          <dt>metrics</dt><dd>counts and <code>grounding_rate</code>; see <a href="#/docs/ledger/metrics">the ledger chapter</a></dd>
          <dt>documents[]</dt><dd><code>{'{'}id, title, text, facts[{'{'}id, start, end{'}'}]{'}'}</code>, offsets into <code>text</code> for highlighting</dd>
          <dt>answer</dt><dd><code>{'{'}text, entity, entity_raw, subtype, hedged, entities_named, claims, factual_claims{'}'}</code></dd>
          <dt>lexicon, oracle, warnings, domain</dt><dd>what the analysis used, <code>truth</code> or <code>extracted</code>, extractor warnings, the domain id</dd>
        </dl>
      </section>

      <section className="endpoint">
        <h2 id="ledger">Audit a structured trace</h2>
        <Sig method="POST" path="/api/ledger" />
        <p>
          A structured artefact in, the 24 checks out. Send either <code>{'{'} "markdown": "&lt;artefact&gt;" {'}'}</code> (an engine's Markdown artefact
          with fact tables and a cited report, up to 2 MB) or <code>{'{'} "case": {'{'}…{'}'}, "trace": {'{'}…{'}'} {'}'}</code> in the canonical JSON below.
          No lexicon is needed: the facts carry their own fields and values.
        </p>
        <ApiTry method="POST" path="/api/ledger" body={stringify(LEDGER_REQUEST)} summary={(json) => <AnalyseSummary data={json} />}
          note="The second segment cites p_2 but states the opposite value, so one citation disagrees." />
        <h3>Case and trace JSON</h3>
        <Code lang="json" copy={false}>{`"case":  { "case_id", "truth", "candidates": [...], "facts": [{ "id", "source", "section", "field", "value", "evidence", "candidate" }],
           "allowed_ids": [...]?, "meta": { "criteria": [...] }? }
"trace": { "thinking", "report": { "decision", "sections": [{ "title", "segments": [{ "text", "citation_ids": [...] }] }] },
           "rationale": { "decision", "differential": [{ "diagnosis", "verdict", "supporting", "contradicting", "criteria": [...] }], "discriminators": [...] }?,
           "ablation": { "removed_ids": [...], "decision_before", "decision_after" }? }`}</Code>
      </section>

      <section className="endpoint">
        <h2 id="case-sets">Case sets and uploads</h2>
        <Sig method="GET" path="/api/case-sets" />
        <p>Case sets a job can run on: the packaged sample, an approved <code>data/</code> set when the instance has one, and your workspace's uploads.</p>
        <ApiTry method="GET" path="/api/case-sets" />
        <Sig method="POST" path="/api/uploads" />
        <p>
          Upload cases (JSON lines) and optionally perturbations and a lexicon: <code>{'{'} "name", "cases": "&lt;jsonl&gt;", "perturbations"?: "&lt;jsonl&gt;", "lexicon"?: "&lt;json&gt;", "approved"? {'}'}</code>.
          Returns <code>201 {'{'} upload_id, n_cases, n_perturbations, problems[] {'}'}</code>, or <code>400</code> when any problem has error severity. Jobs may only
          run unreviewed uploads that the uploader marked approved.
        </p>
      </section>

      <section className="endpoint">
        <h2 id="jobs">Jobs</h2>
        <Sig method="POST" path="/api/jobs" />
        <p>
          Start an audit: a case set through a model at the given efforts and runs, scored and exported as a viewer bundle. The sheet below uses
          the simulated model, which this instance allows anonymously; it finishes in seconds and the result opens in the viewer under Jobs.
        </p>
        <dl className="fields">
          <dt>client</dt><dd><code>{'{'} kind: "sim" | "ollama" | "openai" | "anthropic", endpoint?, model, api_key? {'}'}</code>; <code>api_key</code> is held in memory for the job only</dd>
          <dt>case_set</dt><dd>an id from <code>GET /api/case-sets</code></dd>
          <dt>efforts, runs</dt><dd>reasoning efforts (<code>low</code>, <code>medium</code>, <code>high</code>) and sampled runs per variant</dd>
          <dt>variants, seed, rule, notes</dt><dd>optional filters, the master seed, the disclosure rule (D1 default), free text for the manifest</dd>
        </dl>
        <ApiTry method="POST" path="/api/jobs" body={stringify(JOB_REQUEST)} sendLabel="Start a simulated job"
          note="Returns 202 with a job_id. Open the viewer's Jobs page to watch it." />
        <Sig method="GET" path="/api/jobs" />
        <p>Jobs in your workspace, newest first, with status, progress and a headline.</p>
        <ApiTry method="GET" path="/api/jobs" />
        <Sig method="GET" path="/api/jobs/{id}" />
        <p>
          One job: <code>status</code> (<code>queued</code>, <code>running</code>, <code>scoring</code>, <code>exporting</code>, <code>done</code>, <code>failed</code>,
          <code> cancelled</code>, <code>interrupted</code>), timestamps, <code>progress {'{'}done, total, ok, errors, eta_s{'}'}</code>, the config without any key, and a headline
          with the grounding, silent and spurious rates when done.
        </p>
        <Sig method="DELETE" path="/api/jobs/{id}" />
        <p>Cancel a queued or running job. Traces already written are kept and scored.</p>
        <Sig method="POST" path="/api/jobs/{id}/resume" />
        <p>Resume a job the server interrupted; a job on your own key needs the key again in the body.</p>
        <Sig method="GET" path="/api/jobs/{id}/bundle/{path}" />
        <p>The exported viewer bundle, <code>index.json</code> and <code>cases/&lt;id&gt;.json</code>. The viewer opens it as <code>?bundle=/api/jobs/{'{'}id{'}'}/bundle/</code>.</p>
        <Sig method="GET" path="/api/jobs/{id}/files/{name}" />
        <p>Downloads: <code>summary.json</code>, <code>report.md</code>, <code>traces.jsonl</code>, <code>long.csv</code>, <code>manifest.json</code>, <code>claims.jsonl</code>, <code>grounding.jsonl</code>, <code>counterfactual.jsonl</code>, <code>authority.jsonl</code>.</p>
      </section>

      <section className="endpoint">
        <h2 id="errors">Errors</h2>
        <table className="data">
          <thead><tr><th>Code</th><th>Status</th><th>Meaning</th></tr></thead>
          <tbody>
            <tr><td><code>bad_request</code></td><td>400</td><td>the body is missing something or has the wrong shape; the message says what</td></tr>
            <tr><td><code>too_large</code></td><td>400</td><td>a document, the reasoning or an artefact exceeds its limit</td></tr>
            <tr><td><code>lexicon_required</code>, <code>lexicon_not_found</code></td><td>400, 404</td><td>this instance has no default lexicon; pass an id from <code>GET /api/lexicons</code></td></tr>
            <tr><td><code>bad_lexicon</code></td><td>400</td><td>the loader rejected an uploaded lexicon; the message carries the reason</td></tr>
            <tr><td><code>key_required</code></td><td>400</td><td>the client kind needs your own key on this instance</td></tr>
            <tr><td><code>job_too_large</code></td><td>400</td><td>more model calls than the instance allows in one job</td></tr>
            <tr><td><code>unauthorized</code>, <code>forbidden</code></td><td>401, 403</td><td>a token is required, or the token's workspace may not do this</td></tr>
            <tr><td><code>not_found</code></td><td>404</td><td>no such route, job or file</td></tr>
            <tr><td><code>rate_limited</code>, <code>budget_exhausted</code></td><td>429</td><td>per-address rate limit, or the operator key's daily budget is spent</td></tr>
            <tr><td><code>internal</code></td><td>500</td><td>a bug; the message names the exception</td></tr>
          </tbody>
        </table>
      </section>
    </>
  );
}
