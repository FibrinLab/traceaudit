import { Code } from '../Code';

export default function Provenance() {
  return (
    <>
      <h2 id="what">What a hash proves</h2>
      <p>
        A hash answers one question: is this byte for byte the same thing? It therefore proves identity and never faithfulness. It cannot say
        whether a report's rationale matches the chain of thought; that comparison has to be made at the level of meaning, which is what the
        <a href="#/docs/ledger"> ledger grader</a> does with fact ids. What a hash can do is make three claims checkable by anyone with the files.
      </p>
      <ul>
        <li><strong>What the model saw.</strong> The hash of the exact prompt, rebuilt from the inputs, shows that no variant marker, trace key or
          edit rationale was in the text.</li>
        <li><strong>What was scored.</strong> Hashes of the raw reasoning and answer show that the released traces are the traces the statistics
          were computed on.</li>
        <li><strong>What was fixed in advance.</strong> One hash over the inputs, published in the pre-registration, shows the variant set did not
          change after results were seen.</li>
      </ul>

      <h2 id="trace">Per trace</h2>
      <Code lang="json" copy={false}>{`{
 "trace_key": "CLL-001|dec-cyclin_d1|high|0",
 "reasoning": "...", "answer": "...",
 "provenance": {
  "prompt_sha256":    "<sha256(system + '\\x00' + user)>",
  "reasoning_sha256": "<sha256(reasoning)>",
  "answer_sha256":    "<sha256(answer)>"
 }
}`}</Code>
      <p>
        An error trace keeps the prompt hash only. A trace imported from an external engine records <code>reasoning_sha256</code>,
        <code> answer_sha256</code>, <code>artefact_sha256</code> of the source file and the fact-table <code>fingerprint</code>; its
        <code> prompt_sha256</code> is null because traceaudit did not send that prompt.
      </p>

      <h2 id="run">Per run</h2>
      <Code lang="json" copy={false}>{`"provenance": {
 "rule": "sha256(utf8); prompt = sha256(system + '\\x00' + user); inputs = sha256('\\n'.join(name=sha256 or none))",
 "components": { "prompt": "<sha256>", "cases": "<sha256>", "perturbations": "<sha256>", "lexicon": "<sha256>" },
 "inputs_sha256": "8d24d0661e2c0a0e59bb5377056a0ab0ac2f0643481cb525c3e1e3d94636827f"
}`}</Code>
      <p>
        The manifest already recorded the model digest from the server, the prompt text, the seeds and the git commit. The inputs hash completes
        the chain: model, input and output are each verifiable. The example value above is the demo run's.
      </p>

      <h2 id="verify">Verify</h2>
      <Code lang="shell">{`traceaudit manifest verify RUN
traceaudit manifest verify RUN --cases cases.jsonl --perturbations perturbations.jsonl`}</Code>
      <p>
        The first form recomputes the prompt text against its hash, the components against the inputs hash, the input files against their recorded
        hashes when they still exist at the recorded paths, and every trace's reasoning and answer hashes. Prompts count as unverified, not failed.
        The second form re-renders every variant from the inputs with the run's own render settings (ablations in the run are added automatically)
        and rebuilds each prompt hash, which is the check that no variant text reached the model. Exit status 1 on any mismatch, and on a run made
        before these fields existed, which cannot be hashed truthfully after the fact.
      </p>
    </>
  );
}
