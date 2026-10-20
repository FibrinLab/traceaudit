import { useMemo, useState } from 'react';
import { useCaseFile, useStore } from '../store';
import { hrefTrace, hrefReview } from '../lib/router';
import { entityDisplay, pct, KIND_TEXT, findingDisplay } from '../lib/format';
import { variantKindOf, type ReportName, type Trace } from '../types';
import { Chip, Loading, Banner, OutcomeBadge } from '../components/Shared';
import { ReportPane } from '../components/ReportPane';
import { CaseConstellation } from '../charts/CaseConstellation';
import { diffHighlights } from './CounterfactualView';
import { entityColor } from '../lib/palette';

export function CaseView({ caseId }: { caseId: string }) {
  const { bundle } = useStore();
  const { caseFile, error, loading } = useCaseFile(caseId);
  const [variantFilter, setVariantFilter] = useState('');
  const [effortFilter, setEffortFilter] = useState('');
  const [previewVariant, setPreviewVariant] = useState<string | null>(null);
  const index = bundle!.index;
  const entry = index.cases.find((c) => c.case_id === caseId);

  const traces = useMemo(() => {
    const list = caseFile?.traces ?? [];
    return list
      .filter((t) => (!variantFilter || t.variant === variantFilter) && (!effortFilter || t.effort === effortFilter))
      .slice()
      .sort((a, b) => a.variant.localeCompare(b.variant) || effortOrder(a.effort) - effortOrder(b.effort) || a.run - b.run);
  }, [caseFile, variantFilter, effortFilter]);

  if (!entry) return <Banner tone="warn">Case {caseId} is not in this bundle.</Banner>;
  if (error) return <Banner tone="bad">{error}</Banner>;
  if (loading || !caseFile) return <Loading what={`case ${caseId}`} />;

  const variants = Object.values(caseFile.variants);
  const preview = previewVariant ? caseFile.variants[previewVariant] : null;
  const previewFooters: Partial<Record<ReportName, JSX.Element>> = {};
  if (preview) {
    for (const r of Object.keys(preview.diff)) {
      const ops = preview.diff[r] ?? [];
      if (ops.length) previewFooters[r] = <ul className="small muted" style={{ margin: '4px 0 0', paddingLeft: 18 }}>{ops.map((op, i) => <li key={i}>✎ {op.op}: “{op.before || '∅'}” became “{op.after || '∅'}”</li>)}</ul>;
    }
  }

  return (
    <div>
      <nav aria-label="Breadcrumb" className="crumbs"><a href="#/cases">Cases</a><span className="sep">/</span><span>{caseId}</span></nav>
      <h1>Case {caseId}</h1>
      <div className="row small" style={{ marginBottom: 12 }}>
        <Chip tone="neutral"><span className="entity-dot" style={{ background: entityColor(index.lexicon, caseFile.case.entity) }} aria-hidden="true" />{entityDisplay(index.lexicon, caseFile.case.entity)}{caseFile.case.subtype ? ` (${caseFile.case.subtype})` : ''}</Chip>
        {caseFile.case.flags.discordant && <Chip tone="warn" icon="!">discordant: {caseFile.case.flags.atypical_features.join(', ')}</Chip>}
        {caseFile.case.flags.incomplete && <Chip tone="warn" icon="!">incomplete: {caseFile.case.flags.missing_modalities.join(', ')}</Chip>}
        {(['low', 'medium', 'high'] as const).map((e) => {
          const br = caseFile.base_reference[e];
          return br ? <Chip key={e} tone={br.base_stable ? 'good' : 'warn'} icon={br.base_stable ? '✓' : '!'}>{e}: base {entityDisplay(index.lexicon, br.base_modal_entity)} in {Math.round((br.base_mode_share ?? 0) * br.base_n)} of {br.base_n}</Chip> : null;
        })}
        {!index.study && <a className="btn small" href={hrefReview(caseId)}>Review this case</a>}
      </div>

      <div className="grid">
        <div className="span-6">
          <CaseConstellation caseFile={caseFile} lexicon={index.lexicon} selectedVariant={previewVariant} onSelectVariant={setPreviewVariant} />
        </div>
        <div className="span-6">
          <div className="panel tight">
            <div className="panel-head">
              <h3 style={{ margin: 0 }}>{preview ? `Documents with ${preview.variant}` : 'Base documents'}</h3>
              {preview && <span className="small muted">{KIND_TEXT[preview.kind]}{preview.perturbation?.expected_entity ? `, expected ${entityDisplay(index.lexicon, preview.perturbation.expected_entity)}` : preview.perturbation?.expected_behaviour ? `, expected to ${preview.perturbation.expected_behaviour}` : ''}</span>}
            </div>
            <ReportPane reports={preview ? preview.reports : caseFile.case.reports} sections={caseFile.case.sections} highlights={preview ? diffHighlights(preview.diff, 'variant') : []} footers={preview ? previewFooters : undefined} scrollTo={preview ? diffHighlights(preview.diff, 'variant')[0]?.id ?? null : null} />
          </div>
        </div>
      </div>

      <h2>Variants</h2>
      <div className="panel tight">
        <table className="data">
          <thead><tr><th>Variant</th><th>Kind</th><th>Edit</th><th>Expected</th><th></th></tr></thead>
          <tbody>
            {variants.map((v) => (
              <tr key={v.variant}>
                <td className="mono">{v.variant}</td>
                <td>{KIND_TEXT[v.kind]}</td>
                <td>
                  {v.perturbation?.cue ? <>▲ cue: {entityDisplay(index.lexicon, v.perturbation.cue.entity)} ({v.perturbation.cue.correct ? 'correct' : 'wrong'})</>
                    : v.perturbation ? v.perturbation.edits.map((e) => e.finding_id ? `${findingDisplay(index.lexicon, e.finding_id)} ${e.from ?? '?'} to ${e.to ?? '?'} (${e.role.replace('_', ' ')})` : `${e.op} (${e.report.replace('_', ' ')})`).join('; ')
                    : 'none'}
                </td>
                <td>{v.perturbation?.expected_entity ? entityDisplay(index.lexicon, v.perturbation.expected_entity) : v.perturbation?.expected_behaviour ?? '—'}</td>
                <td>{v.kind !== 'base' && <button type="button" className="btn small quiet" aria-pressed={previewVariant === v.variant} onClick={() => setPreviewVariant(previewVariant === v.variant ? null : v.variant)}>{previewVariant === v.variant ? 'Previewing' : 'Preview diff'}</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <details style={{ marginTop: 10 }}>
          <summary className="small muted">Truth table, {Object.keys(caseFile.case.truth).length} findings</summary>
          <table className="data small" style={{ marginTop: 6 }}>
            <tbody>
              {Object.entries(caseFile.case.truth).map(([f, p]) => <tr key={f}><td>{findingDisplay(index.lexicon, f)}</td><td>{p === 'pos' ? 'positive' : 'negative'}</td></tr>)}
            </tbody>
          </table>
        </details>
      </div>

      <h2>Traces</h2>
      <div className="row" style={{ marginBottom: 8 }}>
        <label className="field"><span>Variant</span>
          <select value={variantFilter} onChange={(e) => setVariantFilter(e.target.value)}>
            <option value="">All variants</option>
            {variants.map((v) => <option key={v.variant} value={v.variant}>{v.variant}</option>)}
          </select>
        </label>
        <label className="field"><span>Effort</span>
          <select value={effortFilter} onChange={(e) => setEffortFilter(e.target.value)}>
            <option value="">All efforts</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
          </select>
        </label>
        <span className="muted small">{traces.length} traces</span>
      </div>
      <div className="trace-list" role="table" aria-label="Traces">
        <div className="trace-row head" role="row">
          <span role="columnheader">Trace</span><span role="columnheader">Answer</span><span role="columnheader">Grounding</span><span role="columnheader">Problems</span><span role="columnheader">Outcome</span><span role="columnheader">Views</span>
        </div>
        {traces.map((t) => <TraceRow key={t.trace_key} t={t} />)}
      </div>
    </div>
  );
}

function effortOrder(e: string): number { return e === 'low' ? 0 : e === 'medium' ? 1 : 2; }

function TraceRow({ t }: { t: Trace }) {
  const { bundle } = useStore();
  const kind = variantKindOf(t.variant);
  const g = t.grounding;
  const outcome = t.counterfactual?.outcome ?? t.authority?.outcome ?? null;
  return (
    <div className="trace-row" role="row">
      <span role="cell" className="mono"><a href={hrefTrace(t.trace_key, 'grounding')}>{t.variant} {t.effort} run {t.run}</a></span>
      <span role="cell">{g?.answer_entity ? <><span className="entity-dot" style={{ background: entityColor(bundle!.index.lexicon, g.answer_entity) }} aria-hidden="true" />{entityDisplay(bundle!.index.lexicon, g.answer_entity)}</> : '—'}{g?.answer_hedged ? ' (hedged)' : ''}</span>
      <span role="cell" className="num">{pct(g?.grounding_rate ?? null, 0)}</span>
      <span role="cell">
        {g && (g.n_contradicted > 0 || g.n_unsupported > 0) ? <>{g.n_contradicted > 0 && <span style={{ color: 'var(--contradicted)' }}>✗ {g.n_contradicted} </span>}{g.n_unsupported > 0 && <span style={{ color: 'var(--unsupported)' }}>? {g.n_unsupported}</span>}</> : <span className="muted">none</span>}
      </span>
      <span role="cell">{outcome ? <OutcomeBadge outcome={outcome} /> : <span className="muted">—</span>}</span>
      <span role="cell" className="links">
        <a href={hrefTrace(t.trace_key, 'grounding')}>grounding</a>
        {(kind === 'decisive' || kind === 'anchor_loss' || kind === 'neutral') && <a href={hrefTrace(t.trace_key, 'counterfactual')}>counterfactual</a>}
        {kind === 'authority' && <a href={hrefTrace(t.trace_key, 'authority')}>authority</a>}
        {t.map && <a href={hrefTrace(t.trace_key, 'map')}>constellation</a>}
      </span>
    </div>
  );
}
