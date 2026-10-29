import { Code } from '../Code';

export default function Overview() {
  return (
    <>
      <h2 id="question">The question</h2>
      <p>
        A reasoning model writes a chain of thought before it answers. When that chain is shown to a clinician, an engineer or a reviewer as the
        explanation for the answer, two separate things can go wrong. The chain can state things that are not in the documents, or contradict them:
        it is not <strong>grounded</strong>. Or it can be true in every sentence and still not be the reason the model answered as it did: it is not
        <strong> faithful</strong>. A trace that is right for the wrong reasons looks identical to a trace that is right for the right ones until you
        change the inputs.
      </p>
      <p>
        traceaudit was built for a study of exactly this on diagnostic reasoning in haematology, where a model integrates several laboratory reports
        into one diagnosis and the trace is the proposed explanation. The engine is domain-agnostic: it takes documents, a reasoning trace, an answer
        and a lexicon that names the facts and candidate answers of the domain. The clinical content is one file.
      </p>

      <h2 id="measurements">Three measurements</h2>
      <h3>Grounding, by the fact ledger</h3>
      <p>
        Each document is read into facts with ids. Each sentence of the report that cites a fact is graded against that fact's recorded value:
        <code>agree</code>, <code>disagree</code>, <code>unverifiable</code>, or the fact was <code>not_mentioned</code>. Facts the trace asserts
        without citing are listed as uncited assertions. Twenty-four named checks run over the whole trace. The headline number is the grounding
        rate, the share of cited claims that agree with their fact.
      </p>
      <h3>Faithfulness, by intervention</h3>
      <p>
        The documents are changed in one specified way and the model is run again. A decisive edit flips a fact so that another candidate answer
        fits best. If the answer changes and the trace states the new value, the change is <em>disclosed</em>. If the answer changes and the trace
        says nothing, it is <em>silent</em>. A neutral edit that changes presentation only should change nothing; when it does, the change is
        <em>spurious</em>. An authority cue tests whether the model follows a suggestion it does not acknowledge. An ablation removes the facts the
        model itself called load-bearing and asks whether they were.
      </p>
      <h3>Provenance, by hashing</h3>
      <p>
        Every trace carries the hash of the exact prompt it was sent and of its raw reasoning and answer. Every run commits to one hash over its
        inputs. These prove identity, never faithfulness: that the model saw nothing naming the variant, that the traces scored are the traces
        released, and that the variant set was fixed before any result existed.
      </p>

      <h2 id="not">What it is not</h2>
      <ul>
        <li>It is not a judge model. The grader is deterministic: alias tables, a polarity grammar and literal matches. A model-based judge exists as
          an optional, calibrated extra for the rating study, never as the headline.</li>
        <li>It is not a benchmark with a leaderboard. It is a measurement harness for a pre-registered study, with a simulated model to prove that
          the harness recovers what was planted.</li>
        <li>It is not medical software. The reference domain's content is marked draft until a haematologist signs it off, and the public service runs
          on synthetic cases.</li>
      </ul>

      <h2 id="parts">The parts</h2>
      <Code copy={false}>{`specs/        20 specifications: the behavioural contract for everything below
traceaudit/   the Python package, standard library only at runtime
viewer/       this site and the Trace Viewer (React), served as static files
examples/     a non-clinical lexicon and trace (software incident triage)
tests/        the test suite, including the simulator validation grids
docs/         project spec, implementation notes, labelling guide, deviations log`}</Code>
      <p>
        Everything the service does is also a command, and the numbers match because they are the same code. The manifest of a run records the
        model digest, the prompt hash, the input hashes and the seeds, so a run can be audited without trusting the person who made it.
      </p>
    </>
  );
}
