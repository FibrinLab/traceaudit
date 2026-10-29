import { Code } from '../Code';
import { REPO_URL } from '../SiteShell';

export default function Domains() {
  return (
    <>
      <p>
        traceaudit is trace analytics for any task where a model reasons over a known set of source documents and gives a categorical answer. The
        reference domain is haematology because that is the study the authors run; a complete non-clinical example ships with the package, software
        incident triage, and it is the example this site's playground uses.
      </p>

      <h2 id="lexicon">The lexicon</h2>
      <p>One JSON file says five things about a domain.</p>
      <table className="data">
        <thead><tr><th>Key</th><th>What it holds</th><th>Needed for</th></tr></thead>
        <tbody>
          <tr><td><code>sections</code></td><td>the document sections a case is made of: <code>[{'{'}id, title{'}'}]</code></td><td>rendering and the Analyse form</td></tr>
          <tr><td><code>findings</code></td><td>the binary facts a document can assert, each with the words that name it (<code>aliases</code>), optional whole-phrase forms (<code>pos_phrases</code>, <code>neg_phrases</code>), an optional <code>numeric_rule</code>, and canonical sentences (<code>pos_text</code>, <code>neg_text</code>)</td><td>grounding, perturbation</td></tr>
          <tr><td><code>entities</code></td><td>the answer categories and their names</td><td>answer parsing, authority cues</td></tr>
          <tr><td><code>discriminators</code></td><td>for each finding, whether each entity expects it <code>pos</code>, <code>neg</code> or <code>var</code></td><td>decisive and anchor edits, knowledge checks, the simulated model</td></tr>
          <tr><td><code>linked</code>, <code>confusion</code>, <code>phrases</code></td><td>associated findings, plausible wrong answers, and the phrase lists for hedging, acknowledgement, knowledge and inference</td><td>probes and claim typing</td></tr>
        </tbody>
      </table>
      <p>
        Read <a href={`${REPO_URL}/blob/main/examples/lexicon-incident-triage.json`} rel="noreferrer">the incident-triage lexicon</a>: three sections
        (alerts, logs, deploy history), six findings, four answers. Upload your own at <a href="#/docs/api/lexicons">POST /api/lexicons</a> or pass
        it to any command with <code>--lexicon</code>.
      </p>

      <h2 id="cases">Cases</h2>
      <p>
        Cases are documents with a known answer, real or synthetic. <code>traceaudit cases build</code> turns records of the form
        <code> {'{'}case_id, entity, documents{'{'}section: text{'}'}{'}'}</code> into cases, reading the truth from the documents with the extractor and
        reporting anything it could not read. The packaged generator shows how to synthesise cases from priors when you have none.
      </p>
      <Code lang="shell">{`traceaudit cases build docs.jsonl -o cases.jsonl --lexicon my-lexicon.json
traceaudit perturb cases.jsonl -o perturbations.jsonl --lexicon my-lexicon.json
traceaudit validate cases.jsonl --perturbations perturbations.jsonl --lexicon my-lexicon.json`}</Code>
      <p>
        Decisive and anchor-loss edits are derived from the discriminator table: flip the finding after which another category fits the documents
        best. Neutral edits and authority cues are generic. To use hand-authored edits with an expert's rationale instead, add a
        <code> perturbations</code> block to the lexicon; authored rows take precedence over derived ones.
      </p>

      <h2 id="rules">Loader rules</h2>
      <ul>
        <li>Finding ids are unique; no alias is shared by two findings.</li>
        <li>Every finding named in <code>discriminators</code>, <code>linked</code> or <code>confusion</code> exists.</li>
        <li>Every entity has at least one alias. Aliases of five characters or fewer in capitals match case-sensitively, so <code>FL</code> does not
          match the unit <code>fL</code>.</li>
        <li>A lexicon the loader rejects is refused by the service with <code>bad_lexicon</code> and the reason.</li>
      </ul>

      <h2 id="transfer">What transfers unchanged</h2>
      <p>
        Extraction, segmentation, grounding, answer parsing, the probes, the ledger grader, the statistics, the service and the viewer. The authority
        cue sentence is a lexicon field. In the viewer, the category colours are assigned in lexicon order, so a new domain gets a consistent palette
        without configuration.
      </p>
    </>
  );
}
