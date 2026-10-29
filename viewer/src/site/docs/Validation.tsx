import { Code } from '../Code';

export default function Validation() {
  return (
    <>
      <h2 id="simulator">The simulated model</h2>
      <p>
        A harness that measures silent changes must be shown to recover a known rate of silent changes. The simulated model reads the facts from the
        rendered prompt, decides from the variant metadata it is handed out of band, and writes a trace with faults planted at chosen probabilities:
        silent changes, missed changes, spurious changes, authority following with and without acknowledgement, contradictions in the thinking, broken
        output contracts, ignored ablations. It never contradicts a fact it discloses, so a planted fault is always exactly one fault.
      </p>

      <h2 id="grid">The validation grid</h2>
      <p>
        Each grid cell is a parameter set; the pipeline runs end to end on synthetic cases and the recovered rates are compared with the planted
        ones under the tolerance rules of specification 10. The quick grid runs in continuous integration on every push, for both the text path and
        the ledger path.
      </p>
      <table className="data">
        <thead><tr><th>Cell</th><th>What is planted</th></tr></thead>
        <tbody>
          <tr><td><code>clean</code></td><td>nothing: every rate should recover as zero or one</td></tr>
          <tr><td><code>mid</code></td><td>moderate rates of every fault at once</td></tr>
          <tr><td><code>silent_only</code></td><td>silent changes only</td></tr>
          <tr><td><code>authority_only</code></td><td>authority following only</td></tr>
          <tr><td><code>ablation_only</code></td><td>ignored ablations only</td></tr>
          <tr><td><code>contract_break</code></td><td>a share of prose replies; scored through the text fallback and reported as a share</td></tr>
        </tbody>
      </table>
      <Code lang="shell">{`traceaudit validate-probes --grid quick            # text path
traceaudit ledger validate-probes --grid quick     # ledger path
traceaudit ledger validate-probes --grid default   # adds low, high, noisy_base and style cells`}</Code>
      <p>
        Passing the grid is a necessary condition, not proof of validity on a real model: the simulator plants faults the way the specification
        imagines them. That is why the <a href="#/docs/limits">limits chapter</a> exists.
      </p>

      <h2 id="grader">Grader validation</h2>
      <p>
        The ledger grader produces every grade by rule. Its error against human judgement is measured, not assumed (specification 20). The protocol:
      </p>
      <ol>
        <li><code>traceaudit ledger sample</code> draws a stratified sample of citations over grade and source (report, thinking, rationale), capped
          per case, and writes one blind file per rater in a per-rater seeded order. The files carry the segment, the fact and its evidence, and no
          grader label.</li>
        <li>Two raters label independently with the four grades, following the one-page labelling guide in the repository. Disagreements are
          adjudicated into a consensus file.</li>
        <li><code>traceaudit ledger agreement</code> reports inter-rater agreement (Cohen's kappa, Gwet's AC1, percent), grader against consensus
          (kappa and per-class precision and recall), and case-clustered bootstrap intervals.</li>
      </ol>
      <p>
        Acceptance rule, pre-registered: the grader's kappa against the consensus must be at least the inter-rater kappa minus 0.1, the same rule
        the judge model is held to.
      </p>
      <Code lang="shell">{`traceaudit ledger sample artefacts/ --n 300 --raters R01,R02 -o labels/
# ... both raters fill human_grade in their file ...
traceaudit ledger agreement labels/ --results audit.json`}</Code>

      <h2 id="stats">Statistics</h2>
      <ul>
        <li><strong>Rates</strong> are proportions with Wilson 95% intervals, and with case-clustered bootstrap intervals (B = 2000, seed
          20261020) because traces from one case are not independent.</li>
        <li><strong>Differences</strong> between efforts or variants are paired bootstrap differences over the same cases.</li>
        <li><strong>Sensitivity</strong>: every rate is reported under D1, D2 and D3, and the summary records the contract-fallback share so those
          traces can be excluded in a sensitivity row.</li>
        <li><strong>Mixed-effects models</strong> run in R on <code>long.csv</code>, one row per trace with case, variant kind, effort and outcome;
          the pre-registered models live in <code>analysis/</code>.</li>
        <li><strong>Agreement</strong>: weighted kappa and Gwet's AC2 for the ordinal rating study; Cohen's kappa and AC1 for the nominal grades.</li>
      </ul>
    </>
  );
}
