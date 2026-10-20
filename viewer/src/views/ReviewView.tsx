import { useEffect, useMemo, useState } from 'react';
import { useCaseFile, useStore, VIEWER_VERSION } from '../store';
import type { ReportName, Section, Variant } from '../types';
import { ReportPane, type ReportHighlight } from '../components/ReportPane';
import { Banner, Chip, Loading } from '../components/Shared';
import { entityDisplay, findingDisplay, polarityText } from '../lib/format';
import { downloadJson } from '../lib/download';
import { diffHighlights, describeEdits } from './CounterfactualView';
import { hrefCase } from '../lib/router';

type Decision = 'approve' | 'reject' | '';
interface ReviewItem { status: Decision; notes: string }
interface ReviewState { reviewer_id: string; case: ReviewItem; perturbations: Record<string, ReviewItem>; updated_at: string | null }

const key = (runId: string, caseId: string) => `traceaudit:review:${runId}:${caseId}`;

export function ReviewView({ caseId }: { caseId: string }) {
  const { bundle } = useStore();
  const idx = bundle!.index;
  const { caseFile, error, loading } = useCaseFile(caseId);
  const [review, setReview] = useState<ReviewState>(() => {
    try { const raw = localStorage.getItem(key(idx.run.run_id, caseId)); if (raw) return JSON.parse(raw) as ReviewState; } catch { /* ignore */ }
    return { reviewer_id: '', case: { status: '', notes: '' }, perturbations: {}, updated_at: null };
  });
  const [focusFinding, setFocusFinding] = useState<string | null>(null);

  useEffect(() => {
    try { localStorage.setItem(key(idx.run.run_id, caseId), JSON.stringify(review)); } catch { /* ignore */ }
  }, [review, idx.run.run_id, caseId]);

  const truthHighlights = useMemo<ReportHighlight[]>(() => {
    if (!caseFile || !focusFinding) return [];
    return (caseFile.case.finding_spans[focusFinding] ?? []).map((s, i) => ({ report: s.report, start: s.start, end: s.end, kind: 'focus', label: `${findingDisplay(idx.lexicon, focusFinding)} ${polarityText(s.polarity)}`, id: `truth-${focusFinding}-${i}`, priority: 3 }));
  }, [caseFile, focusFinding, idx.lexicon]);

  if (idx.study) {
    return <div className="narrow"><h1>Case review</h1><Banner tone="warn">Case review is disabled for study bundles so truth cannot leak into rating sessions. Export without <code>--study</code> to review cases.</Banner></div>;
  }
  if (error) return <Banner tone="bad">{error}</Banner>;
  if (loading || !caseFile) return <Loading what={`case ${caseId}`} />;

  const perturbed = Object.values(caseFile.variants).filter((v) => v.kind !== 'base');
  const setItem = (which: string | null, patch: Partial<ReviewItem>) => setReview((r) => {
    const now = new Date().toISOString();
    if (which === null) return { ...r, case: { ...r.case, ...patch }, updated_at: now };
    return { ...r, perturbations: { ...r.perturbations, [which]: { ...(r.perturbations[which] ?? { status: '', notes: '' }), ...patch } }, updated_at: now };
  });
  const exportReview = () => downloadJson(`review-${caseId}.json`, {
    schema_version: 1, case_id: caseId, reviewer_id: review.reviewer_id, date: new Date().toISOString().slice(0, 10), viewer_version: VIEWER_VERSION, bundle_run_id: idx.run.run_id,
    case: { status: review.case.status || 'pending', notes: review.case.notes },
    perturbations: perturbed.map((v) => ({ perturbation_id: `${caseId}/${v.variant}`, variant: v.variant, status: review.perturbations[v.variant]?.status || 'pending', notes: review.perturbations[v.variant]?.notes ?? '' })),
  });

  const findings = Object.entries(caseFile.case.truth);
  const flagged = new Set(caseFile.case.flags.atypical_features);

  return (
    <div>
      <nav aria-label="Breadcrumb" className="small muted"><a href="#/cases">Cases</a> › <a href={hrefCase(caseId)}>{caseId}</a> › review</nav>
      <h1>Review case {caseId} <span className="muted" style={{ fontWeight: 400 }}>{entityDisplay(idx.lexicon, caseFile.case.entity)}{caseFile.case.subtype ? ` (${caseFile.case.subtype})` : ''}</span></h1>
      <div className="row small">
        {caseFile.case.flags.discordant && <Chip tone="warn" icon="!">discordant: {caseFile.case.flags.atypical_features.join(', ')}</Chip>}
        {caseFile.case.flags.incomplete && <Chip tone="warn" icon="!">incomplete: {caseFile.case.flags.missing_modalities.join(', ')}</Chip>}
        <label>Reviewer id <input type="text" value={review.reviewer_id} onChange={(e) => setReview((r) => ({ ...r, reviewer_id: e.target.value.toUpperCase() }))} placeholder="R01" pattern="R\d\d" /></label>
        <button type="button" className="btn primary" onClick={exportReview}>Export review JSON</button>
      </div>

      <div className="grid-2" style={{ marginTop: 12 }}>
        <div>
          <h2>Rendered case</h2>
          <ReportPane reports={caseFile.case.reports} sections={caseFile.case.sections} highlights={truthHighlights} scrollTo={truthHighlights[0]?.id ?? null} />
        </div>
        <div>
          <h2>Truth table <span className="muted small">({findings.length} findings — click a finding to see its evidence)</span></h2>
          <div style={{ maxHeight: '60vh', overflow: 'auto' }}>
            <table className="data small">
              <thead><tr><th>Finding</th><th>Polarity</th><th>Evidence</th></tr></thead>
              <tbody>
                {findings.map(([f, p]) => {
                  const spans = caseFile.case.finding_spans[f] ?? [];
                  return (
                    <tr key={f} style={flagged.has(f) ? { background: 'var(--unsupported-wash)' } : undefined}>
                      <td><button type="button" className="btn small" aria-pressed={focusFinding === f} onClick={() => setFocusFinding((x) => (x === f ? null : f))}>{findingDisplay(idx.lexicon, f)}</button>{flagged.has(f) && <span className="small" style={{ color: 'var(--unsupported)' }}> atypical</span>}</td>
                      <td>{polarityText(p)}</td>
                      <td className="small muted">{spans.length ? spans.map((s) => `${s.report.replace('_', ' ')} [${s.start}–${s.end}] “${s.surface ?? ''}”`).join('; ') : <span style={{ color: 'var(--contradicted)' }}>no span found</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <h2>Case decision</h2>
      <DecisionForm item={review.case} onChange={(p) => setItem(null, p)} name="case" checklist={[
        'Is the answer the one you would reach from these documents?',
        'Is every stated finding plausible for this category, or deliberately atypical and flagged?',
        'Are the numbers and details plausible?',
        'Does the text read like a genuine document from this domain?',
        'Are there cues to the answer that should not be there?',
      ]} />

      <h2>Perturbations ({perturbed.length})</h2>
      {perturbed.map((v) => <PerturbationReview key={v.variant} v={v} base={caseFile.variants.base} sections={caseFile.case.sections} item={review.perturbations[v.variant] ?? { status: '', notes: '' }} onChange={(p) => setItem(v.variant, p)} />)}
    </div>
  );
}

function DecisionForm({ item, onChange, name, checklist }: { item: ReviewItem; onChange: (p: Partial<ReviewItem>) => void; name: string; checklist?: string[] }) {
  return (
    <div className="panel">
      {checklist && <ol className="small muted" style={{ marginTop: 0 }}>{checklist.map((c, i) => <li key={i}>{c}</li>)}</ol>}
      <div className="row" role="radiogroup" aria-label={`Decision for ${name}`}>
        <label><input type="radio" name={`dec-${name}`} checked={item.status === 'approve'} onChange={() => onChange({ status: 'approve' })} /> Approve</label>
        <label><input type="radio" name={`dec-${name}`} checked={item.status === 'reject'} onChange={() => onChange({ status: 'reject' })} /> Reject</label>
        {item.status && <button type="button" className="btn small" onClick={() => onChange({ status: '' })}>Clear</button>}
        {item.status === 'approve' && <Chip tone="good" icon="✓">approved</Chip>}
        {item.status === 'reject' && <Chip tone="bad" icon="✗">rejected</Chip>}
      </div>
      <label style={{ display: 'block', marginTop: 6 }}>Notes<br /><textarea value={item.notes} onChange={(e) => onChange({ notes: e.target.value })} /></label>
    </div>
  );
}

function PerturbationReview({ v, base, sections, item, onChange }: { v: Variant; base: Variant | undefined; sections: Section[] | null | undefined; item: ReviewItem; onChange: (p: Partial<ReviewItem>) => void }) {
  const { bundle } = useStore();
  const lexicon = bundle!.index.lexicon;
  const p = v.perturbation;
  const changed = Object.keys(v.diff).filter((r) => (v.diff[r] ?? []).length > 0);
  const only = (reports: Variant['reports']) => Object.fromEntries(Object.keys(reports).map((r) => [r, changed.includes(r) ? reports[r] : ''])) as Variant['reports'];
  return (
    <section className="panel" aria-labelledby={`pr-${v.variant}`}>
      <h3 id={`pr-${v.variant}`} style={{ marginTop: 0 }}><span className="mono">{v.variant}</span> {v.kind.replace('_', ' ')}</h3>
      {p && (
        <p style={{ margin: '4px 0' }}>
          <span className="hl-icon" aria-hidden="true">{p.cue ? '▲' : '✎'}</span>{' '}
          {p.cue ? <>Cue: “{p.cue.text}” — {entityDisplay(lexicon, p.cue.entity)} ({p.cue.correct ? 'correct' : 'wrong'})</> : <>Edited: {describeEdits(p.edits, (id) => findingDisplay(lexicon, id)) || 'text-only edits'}.</>}
          {' '}{p.expected_entity ? <>Expected: <strong>{entityDisplay(lexicon, p.expected_entity)}</strong>.</> : p.expected_behaviour ? <>Expected behaviour: <strong>{p.expected_behaviour}</strong>.</> : null}
          {p.linked_findings.length > 0 && <span className="muted"> Linked: {p.linked_findings.join(', ')}.</span>}
        </p>
      )}
      {p?.rationale && <p className="muted small" style={{ margin: '0 0 6px' }}>Rationale: {p.rationale}</p>}
      {changed.length > 0 && (
        <div className="grid-2">
          <ReportPane reports={only(base?.reports ?? v.reports)} sections={sections} highlights={diffHighlights(v.diff, 'base')} title="base (changed documents only)" emptyText="unchanged" />
          <ReportPane reports={only(v.reports)} sections={sections} highlights={diffHighlights(v.diff, 'variant')} title="perturbed (changed documents only)" emptyText="unchanged"
            footers={Object.fromEntries(changed.map((r) => [r, <ul key={r} className="small muted" style={{ margin: '4px 0 0', paddingLeft: 18 }}>{(v.diff[r as ReportName] ?? []).map((op, i) => <li key={i}>{op.op}: “{op.before || '∅'}” → “{op.after || '∅'}”</li>)}</ul>]))} />
        </div>
      )}
      <div style={{ marginTop: 8 }}>
        <DecisionForm item={item} onChange={onChange} name={v.variant} checklist={['Is the edited case still internally coherent?', 'Is the expected answer or behaviour what you would conclude?', 'Is the edit conspicuous in a way a real report would not be?']} />
      </div>
    </section>
  );
}
