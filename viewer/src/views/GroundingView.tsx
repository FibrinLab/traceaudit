import { useEffect, useMemo, useState } from 'react';
import { useStore, useTrace } from '../store';
import type { CaseFile, Claim, ClaimType, Lexicon, Trace } from '../types';
import { ReportPane, type ReportHighlight } from '../components/ReportPane';
import { TracePane } from '../components/TracePane';
import { AnswerCard, Banner, Chip, Loading } from '../components/Shared';
import { Split, TraceScaffold } from '../components/TraceScaffold';
import { assertionHighlights, claimEvidenceHighlights } from '../lib/evidence';
import { findingDisplay, labelIcon, pct } from '../lib/format';
import { hrefTrace } from '../lib/router';
import { ClaimStrip, Constellation } from '../constellation/Constellation';

const ALL_TYPES: ClaimType[] = ['factual', 'inferential', 'knowledge', 'other'];

export function GroundingView({ traceKey }: { traceKey: string }) {
  const { bundle } = useStore();
  const { caseFile, trace, error, loading } = useTrace(traceKey);
  const lexicon = bundle!.index.lexicon;
  if (error) return <Banner tone="bad">{error}</Banner>;
  if (loading || !trace || !caseFile) return <Loading what={`trace ${traceKey}`} />;
  return (
    <TraceScaffold trace={trace} caseFile={caseFile} active="grounding">
      <GroundingBody trace={trace} caseFile={caseFile} lexicon={lexicon} mapHref={trace.map ? hrefTrace(trace.trace_key, 'map') : null} />
    </TraceScaffold>
  );
}

/** The grounding view proper: summary strip, docked constellation, filters, document and trace panes.
 *  Takes explicit data so the Analyse tab can render a trace that is not in the store's bundle. */
export function GroundingBody({ trace, caseFile, lexicon, mapHref = null, reportsTitle }: { trace: Trace; caseFile: CaseFile; lexicon: Lexicon; mapHref?: string | null; reportsTitle?: string }) {
  const traceKey = trace.trace_key;
  const [selected, setSelected] = useState<Claim | null>(null);
  const [visible, setVisible] = useState<Set<ClaimType>>(new Set(ALL_TYPES));
  const [onlyProblems, setOnlyProblems] = useState(false);
  const [showMap, setShowMap] = useState(true);
  const [inView, setInView] = useState<Set<number> | undefined>(undefined);

  useEffect(() => { setSelected(null); }, [traceKey]);

  const reports = useMemo(() => caseFile.variants[trace.variant]?.reports ?? caseFile.case.reports, [caseFile, trace]);
  const evidence = useMemo(() => {
    if (!selected) return null;
    return claimEvidenceHighlights(selected, reports, caseFile.case.finding_spans, (id) => findingDisplay(lexicon, id));
  }, [selected, reports, caseFile, lexicon]);
  const editedFindings = useMemo(() => new Set([trace.counterfactual?.primary_finding, ...(trace.counterfactual?.co_edits ?? [])].filter((x): x is string => !!x)), [trace]);

  const g = trace.grounding;
  const reportHighlights: ReportHighlight[] = evidence?.highlights ?? [];
  const traceExtra = selected ? assertionHighlights(selected) : [];
  const toggleType = (t: ClaimType) => setVisible((v) => { const n = new Set(v); if (n.has(t)) n.delete(t); else n.add(t); return n; });
  const select = (c: Claim | null) => setSelected((s) => (c && s?.claim_id === c.claim_id ? null : c));

  return (
    <>
      <div className="panel tight" style={{ marginBottom: 16 }}>
        <div className="row" style={{ gap: 24, alignItems: 'flex-start' }}>
          <div>
            <div className="small muted">Grounding rate</div>
            <div className="hero-number" style={{ fontSize: 'var(--fs-4)' }}>{pct(g?.grounding_rate ?? null, 0)}</div>
          </div>
          {g && (
            <div className="row small" aria-label="Claim counts" style={{ paddingTop: 6 }}>
              <Chip tone="supported" icon={labelIcon('supported')}>supported {g.n_supported}</Chip>
              <Chip tone="contradicted" icon={labelIcon('contradicted')}>contradicted {g.n_contradicted}</Chip>
              <Chip tone="unsupported" icon={labelIcon('unsupported')}>unsupported {g.n_unsupported}</Chip>
              {g.n_ambiguous > 0 && <Chip tone="neutral">ambiguous {g.n_ambiguous}</Chip>}
              <Chip tone="inferential" icon={labelIcon('inferential')}>inferential {g.n_inferential}</Chip>
              <Chip tone="knowledge" icon={labelIcon('knowledge')}>knowledge {g.n_knowledge}</Chip>
              {g.n_other > 0 && <Chip tone="neutral">other {g.n_other}</Chip>}
              {g.knowledge_inconsistent > 0 && <Chip tone="warn" icon="!">knowledge inconsistent {g.knowledge_inconsistent}</Chip>}
            </div>
          )}
          {!g && <span className="muted">No grounding record for this trace.</span>}
          <span style={{ flex: 1 }} />
          <AnswerCard title="Final answer" answer={trace.answer} lexicon={lexicon} grounding={g} truthEntity={caseFile.case.entity} compact />
        </div>
      </div>

      {trace.map && (
        <div className="panel tight" style={{ marginBottom: 16 }}>
          <div className="panel-head">
            <h3 style={{ margin: 0 }}>Constellation</h3>
            <div className="row small">
              {mapHref && <a href={mapHref}>Open the full constellation</a>}
              <button type="button" className="btn small quiet" aria-expanded={showMap} onClick={() => setShowMap((s) => !s)}>{showMap ? 'Collapse' : 'Expand'}</button>
            </div>
          </div>
          {showMap && (
            <>
              <Constellation trace={trace} caseFile={caseFile} lexicon={lexicon} compact editedFindings={editedFindings} selectedClaimId={selected?.claim_id ?? null} onSelectClaim={(c) => select(c)} />
              <ClaimStrip claims={trace.claims} selectedClaimId={selected?.claim_id ?? null} onSelect={(c) => select(c)} visibleIds={inView} />
            </>
          )}
        </div>
      )}

      <div className="row small" style={{ marginBottom: 8 }} role="group" aria-label="Claim filters">
        <span className="muted">Show</span>
        {ALL_TYPES.map((t) => (
          <button key={t} type="button" className={`chip filter ${t === 'factual' ? 'supported' : t}`} aria-pressed={visible.has(t)} onClick={() => toggleType(t)}>{t}</button>
        ))}
        <button type="button" className="chip filter contradicted" aria-pressed={onlyProblems} onClick={() => setOnlyProblems((o) => !o)}>only problems</button>
        {selected && <button type="button" className="btn small" onClick={() => setSelected(null)}>Clear selection</button>}
      </div>

      {selected && (
        <div aria-live="polite">
          {evidence?.notInInputs.length ? (
            <Banner tone="warn">Not in inputs: {evidence.notInInputs.map((f) => findingDisplay(lexicon, f)).join(', ')}</Banner>
          ) : null}
          {selected.label === 'contradicted' && (
            <Banner tone="bad">Contradicted: {selected.evidence.filter((e) => e.truth !== e.claimed).map((e) => `${findingDisplay(lexicon, e.finding_id)} claimed ${e.claimed ?? '?'}, document says ${e.truth ?? 'not stated'}`).join('; ')}</Banner>
          )}
          {selected.type === 'knowledge' && selected.knowledge_check && (
            <Banner tone={selected.knowledge_check.verdict === 'consistent' ? 'good' : selected.knowledge_check.verdict === 'inconsistent' ? 'bad' : 'info'}>
              Knowledge check ({selected.knowledge_check.verifier}): {selected.knowledge_check.verdict}{selected.knowledge_check.evidence ? `. ${selected.knowledge_check.evidence}` : ''}
            </Banner>
          )}
          {selected.type !== 'factual' && !selected.knowledge_check && (
            <Banner tone="info">{selected.type} claim, not graded against the documents.{selected.entities.length ? ` Entities: ${selected.entities.join(', ')}.` : ''}</Banner>
          )}
        </div>
      )}

      <Split
        left={<ReportPane reports={reports} highlights={reportHighlights} scrollTo={evidence?.scrollTo ?? null} title={reportsTitle ?? `Documents, variant ${trace.variant}`} sections={caseFile.case.sections} />}
        right={
          <TracePane
            reasoning={trace.reasoning}
            claims={trace.claims}
            selectedClaimId={selected?.claim_id ?? null}
            onSelectClaim={(c) => select(c)}
            extraHighlights={traceExtra}
            visibleTypes={visible}
            onlyProblems={onlyProblems}
            title="Reasoning trace. Click or press Enter on a claim to see its evidence"
            onVisibleClaims={setInView}
          />
        }
      />

      {trace.retrieved && trace.retrieved.length > 0 && (
        <details className="panel" style={{ marginTop: 16 }}>
          <summary>Retrieved chunks ({trace.retrieved.length})</summary>
          {trace.retrieved.map((r, i) => (
            <div key={i} style={{ marginTop: 8 }}>
              <div className="small muted mono">{r.doc_id} #{r.chunk_id}, score {r.score.toFixed(2)}</div>
              <div className="report-text">{r.text}</div>
            </div>
          ))}
        </details>
      )}
      {trace.judge && !trace.judge.error && (
        <details className="panel" style={{ marginTop: 16 }}>
          <summary>Judge scores ({trace.judge.judge_model})</summary>
          <div className="row small" style={{ marginTop: 6 }}>
            {Object.entries(trace.judge.scores).map(([d, s]) => <Chip key={d} tone="neutral">{d} {s}</Chip>)}
            {trace.judge.error_tags.map((t) => <Chip key={t} tone="warn">{t.replace(/_/g, ' ')}</Chip>)}
          </div>
          {trace.judge.overall_comment && <p className="small">{trace.judge.overall_comment}</p>}
        </details>
      )}
    </>
  );
}
