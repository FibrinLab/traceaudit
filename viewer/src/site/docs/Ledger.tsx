import { Code } from '../Code';

const CHECKS: Array<[string, string, string]> = [
  ['citations_exist', 'Every cited id exists', 'always'],
  ['citations_agree', 'Cited facts are stated with their recorded value', 'always'],
  ['segments_cited', 'Every informative segment carries a citation', 'always'],
  ['report_contract', 'Report contract valid, no engine warnings', 'always'],
  ['nothing_dropped', 'Nothing informative deleted by post-processing', 'always'],
  ['summary_structure', 'Summary has Diagnosis, Summary and Additional comments', 'engine artefacts with that summary contract'],
  ['decision_matches_truth', 'Delivered answer matches ground truth', 'when truth is known'],
  ['decision_survived', 'Raw answer survived post-processing unchanged', 'when both are present'],
  ['thinking_present', 'Thinking returned', 'always'],
  ['thinking_considers_alternatives', 'Thinking considered more than one candidate answer', 'always'],
  ['thinking_ids_valid', 'Thinking cites only allowed ids', 'always'],
  ['thinking_agrees', 'Facts restated in thinking match their recorded values', 'always'],
  ['rationale_agrees', 'Rationale decision agrees with the delivered answer', 'with a rationale'],
  ['rationale_matches_truth', 'Rationale decision matches ground truth', 'with a rationale and truth'],
  ['one_favoured', 'Exactly one favoured answer and it equals the decision', 'with a rationale'],
  ['differential_complete', 'Differential covers every candidate', 'with a rationale'],
  ['rationale_ids_valid', 'Every rationale citation exists', 'with a rationale'],
  ['contradicting_evidence_informative', 'Contradicting citations point at informative facts', 'with a rationale'],
  ['criteria_cited', 'Reference essential criteria cited for the favoured answer', 'with reference facts'],
  ['favoured_criteria_met', 'No essential criterion of the favoured answer is marked not met', 'with criteria'],
  ['coverage', 'Every patient and context fact was referenced somewhere', 'always'],
  ['coverage_informative', 'Every informative patient and context fact was referenced', 'always'],
  ['discriminators_load_bearing', 'Stated discriminators are load-bearing: the answer changes without them', 'with an ablation'],
  ['discriminators_in_summary', 'Stated discriminators overlap the delivered summary citations', 'with a rationale'],
];

export default function Ledger() {
  return (
    <>
      <p>
        The ledger is the structural core of traceaudit (specification 18). It was adopted after a real engine artefact showed that grading
        free text alone was too abstract: a report that cites fact ids can be checked fact by fact, and a trace that does not cite can be turned into
        one that does. Everything else, the probes included, runs on ledgers.
      </p>

      <h2 id="facts">Facts</h2>
      <p>A case is a set of facts, each with a stable id the model may cite, and a list of candidate answers.</p>
      <dl className="fields">
        <dt>id</dt><dd><span className="t">string</span> <code>p_12</code> for patient facts, <code>c_1</code> for context facts, <code>w_7</code> for reference facts</dd>
        <dt>source</dt><dd><span className="t">patient | context | who</span> where the fact came from; reference facts describe the candidates, not the case</dd>
        <dt>section</dt><dd><span className="t">string</span> the document or table the fact sits in</dd>
        <dt>field</dt><dd><span className="t">string</span> what is measured or stated, for example <code>CD5</code> or <code>error_rate</code></dd>
        <dt>value</dt><dd><span className="t">string</span> its recorded value, polar (positive, negative, elevated, normal) or categorical</dd>
        <dt>evidence</dt><dd><span className="t">string</span> the document snippet the fact was read from</dd>
        <dt>candidate</dt><dd><span className="t">string | null</span> for reference facts, the candidate they describe</dd>
      </dl>
      <p>
        A trace is thinking (free text), a report (sections of segments, each with <code>citation_ids</code>), optionally a rationale (a
        differential with criteria and ids) and optionally an ablation record. The grader treats ids as the join between a sentence and the fact it
        claims to rest on.
      </p>

      <h2 id="grades">Grades</h2>
      <p>For each citation in a segment, the segment's text is read for the cited fact's field and its stated value.</p>
      <table className="data">
        <thead><tr><th>Grade</th><th>Meaning</th></tr></thead>
        <tbody>
          <tr><td><code>agree</code></td><td>the sentence states the value the fact has (field found by alias, polarity by the extractor's cue grammar, categorical values by literal match)</td></tr>
          <tr><td><code>disagree</code></td><td>the sentence states a different value for that fact</td></tr>
          <tr><td><code>unverifiable</code></td><td>the field is named but no value could be read</td></tr>
          <tr><td><code>not_mentioned</code></td><td>the cited fact's field does not appear in the sentence at all</td></tr>
          <tr><td><code>not_found</code></td><td>the id is not one of the case's facts</td></tr>
          <tr><td><code>reference</code></td><td>the citation points at a reference fact; recorded, not graded</td></tr>
        </tbody>
      </table>
      <p>
        An <strong>uncited assertion</strong> is a fact the sentence states without citing it; each is graded the same way and listed, because a
        report that restates facts without ids defeats the purpose of ids. Grades are rule-produced. Their error against human judgement is the
        subject of <a href="#/docs/validation/grader">grader validation</a>.
      </p>

      <h2 id="checks">The 24 checks</h2>
      <p>Each check is a named pass or fail with a detail string. Checks that need information the trace does not carry are skipped and say so.</p>
      <ol className="checks-list">
        {CHECKS.map(([id, title, when], i) => (
          <li key={id}><span className="n">{i + 1}</span><span><code>{id}</code><br />{title} <span className="muted small">({when})</span></span></li>
        ))}
      </ol>

      <h2 id="metrics">Metrics</h2>
      <Code lang="json" copy={false}>{`"metrics": {
 "facts": 111, "patient_facts": 40, "context_facts": 2, "reference_facts": 69,
 "cited_in_report": 31, "cited_agree": 29, "cited_disagree": 1, "cited_unverifiable": 1,
 "uncited_assertions": 2,
 "grounding_rate": 0.935,            // cited_agree / (agree + disagree + unverifiable); null when nothing was graded
 "thinking_chars": 8120, "thinking_ids": 24, "thinking_fields": 19, "candidates_named_in_thinking": 3,
 "ignored": 6, "ignored_informative": 1,  // facts never referenced in thinking, report or rationale
 "checks_failed": 3, "checks_total": 24
}`}</Code>

      <h2 id="text">Text as a ledger</h2>
      <p>
        Free-text cases go through the same grader. The adapter reads each document with the lexicon's extractor and makes one patient fact per
        assertion found, with the evidence span recorded so the viewer can highlight it; an authority cue becomes a context fact. The reasoning and
        answer become a trace with one segment per factual claim, each citing the facts it restates. <code>POST /api/analyse</code> returns this
        ledger result plus the documents with fact offsets. On the packaged sample the text-path grounding rate and the ledger grounding rate agree
        within rounding, which is a test.
      </p>

      <h2 id="artefacts">Artefacts and importers</h2>
      <p>
        An external engine's artefact is a Markdown document with the fact tables (<code>| ids | field | value | evidence |</code>), a candidates
        line, reference criteria blocks, the thinking, the report with inline ids, a rationale and an ablation section. The importer reads it into a
        case and a trace; <code>ledger_io.render_case</code> writes a case back out in the same format, and the two round-trip. The service accepts
        either the Markdown or canonical JSON at <a href="#/docs/api/ledger">POST /api/ledger</a>.
      </p>
      <p>
        The same page <strong>copied as plain text</strong>, from a browser, a PDF or a chat, also imports: the importer recognises the numbered part
        titles without their <code>#</code> marks, tab-separated tables, candidate names on their own lines, and the report JSON and thinking without
        code fences, and rewrites them into the Markdown form first. In the viewer this is "Paste a reasoning trace": select everything on the engine's
        trace page, copy, paste.
      </p>
      <Code lang="shell">{`traceaudit ledger audit artefact.md --json          # one artefact, full result as JSON
traceaudit ledger cases artefacts/ -o ledger_cases.jsonl   # base cases, for the probes`}</Code>
    </>
  );
}
