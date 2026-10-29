import { Code } from '../Code';
import { REPO_URL } from '../SiteShell';

export default function Limits() {
  return (
    <>
      <h2 id="status">Status</h2>
      <table className="data">
        <thead><tr><th>Claim</th><th>Evidence today</th></tr></thead>
        <tbody>
          <tr><td>The harness recovers planted fault rates</td><td>Simulator grids pass in continuous integration, text and ledger paths, every push</td></tr>
          <tr><td>The grader agrees with human judgement</td><td>Not yet measured. Two raters are blind-labelling; the protocol and the statistics are implemented and the acceptance rule is fixed</td></tr>
          <tr><td>Prompts carry nothing that names the variant</td><td>Fixed and recorded on 29 October 2026, with per-trace prompt hashes and a verify command. Runs made before that date carried a comment naming the variant and are marked in their manifests</td></tr>
          <tr><td>Results on an open-weight model with raw chain of thought</td><td>None reported yet. The clients exist; a local pilot is the next step</td></tr>
          <tr><td>Clinical content is signed off</td><td>Not yet. The lexicon, edit catalogue and rubric anchors are marked draft-clinical</td></tr>
          <tr><td>Pre-registered</td><td>Not yet. The deviations log is empty until the OSF registration is published</td></tr>
        </tbody>
      </table>

      <h2 id="known">Known limits carried into the paper</h2>
      <ul>
        <li><strong>Expectation sparsity and circularity.</strong> Decisive edits on ledger cases need a table of what each candidate expects. Free-text
          reference material yields a sparse table; deriving it from the model's own rationale makes the edits specific to that model. The fix is
          structured criteria from the pipeline that owns the reference material.</li>
        <li><strong>Evidence conspicuousness.</strong> Rewriting an evidence snippet to match a flipped fact changes its wording. Rewrite, synthesis and
          redaction are flagged per variant and their rates belong in the report; <code>--no-evidence</code> is the sensitivity option.</li>
        <li><strong>Path-B fidelity.</strong> When an external engine runs the variants, traceaudit matches artefacts by fact-table fingerprint and cannot
          see the prompt. Reorder-type neutral edits are ineffective if the engine re-sorts.</li>
        <li><strong>Hedge measures differ per path.</strong> Structured output exposes hedging through the contract; free text through phrase lists.
          Report per path, do not pool.</li>
        <li><strong>Ablation selection.</strong> Only traces that stated discriminators can be ablated; the skipped count is in the manifest and is a
          selection effect.</li>
        <li><strong>Contract fallback.</strong> Prose replies are scored through a text reading. Their share is reported and they belong in a sensitivity
          row.</li>
        <li><strong>Extractor coverage.</strong> Grounding depends on aliases. A fact phrased in a way the lexicon does not list is unverifiable, not
          wrong; the recall tool and the labelling study measure this.</li>
        <li><strong>Hosted models with summarised thinking.</strong> A pilot on such a model is documented in the repository. Its numbers describe a
          summary, not a chain of thought, and are not comparable to the planned study.</li>
      </ul>

      <h2 id="cite">Cite</h2>
      <p>Until the paper is out, cite the software by its repository and version, and the specifications by number.</p>
      <Code>{`traceaudit: reasoning-trace analytics (version 0.2.0). ${REPO_URL}
Specifications: ${REPO_URL}/tree/main/specs`}</Code>
      <p>
        The repository is Apache-2.0. The clinical reference domain is a research artefact built for a study of mature B-cell neoplasm diagnosis
        and is not clinical guidance.
      </p>
    </>
  );
}
