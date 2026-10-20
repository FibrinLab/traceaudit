import { useEffect, useMemo, useState } from 'react';
import { useStore, useTrace } from '../store';
import { variantKindOf, type Claim } from '../types';
import { ReportPane, type ReportHighlight } from '../components/ReportPane';
import { TracePane } from '../components/TracePane';
import { AnswerCard, Banner, Chip, Loading, OutcomeBadge } from '../components/Shared';
import { TraceScaffold, baseTracesFor } from '../components/TraceScaffold';
import { entityDisplay } from '../lib/format';
import type { Highlight } from '../lib/spans';

export function AuthorityView({ traceKey }: { traceKey: string }) {
  const { bundle } = useStore();
  const { caseFile, trace, error, loading } = useTrace(traceKey);
  const lexicon = bundle!.index.lexicon;
  const [selected, setSelected] = useState<Claim | null>(null);
  useEffect(() => setSelected(null), [traceKey]);

  const variant = caseFile && trace ? caseFile.variants[trace.variant] : null;
  const auth = trace?.authority ?? null;
  const cue = variant?.perturbation?.cue ?? null;

  const cueHighlights = useMemo<ReportHighlight[]>(() => {
    if (!variant || !cue) return [];
    const text = variant.reports[cue.report] ?? '';
    let start = text.indexOf(cue.text);
    let end = start + cue.text.length;
    if (start < 0) {
      // Fall back to the diff insert span.
      const ins = (variant.diff[cue.report] ?? []).find((d) => d.op === 'insert');
      if (!ins) return [];
      start = ins.variant_span[0]; end = ins.variant_span[1];
    }
    return [{ report: cue.report, start, end, kind: 'cue', label: `Injected cue: ${entityDisplay(lexicon, cue.entity)} (${cue.correct ? 'correct' : 'wrong'})`, id: 'cue', priority: 3 }];
  }, [variant, cue, lexicon]);

  const baseTraces = useMemo(() => caseFile && trace ? baseTracesFor(caseFile, trace.effort) : [], [caseFile, trace]);
  const baseModal = auth?.base_modal_entity ?? caseFile?.base_reference?.[trace?.effort ?? 'low']?.base_modal_entity ?? null;
  const baseTrace = baseTraces.find((t) => t.grounding?.answer_entity === baseModal) ?? baseTraces[0] ?? null;

  if (error) return <Banner tone="bad">{error}</Banner>;
  if (loading || !trace || !caseFile || !variant) return <Loading what={`trace ${traceKey}`} />;
  if (variantKindOf(trace.variant) !== 'authority') {
    return (
      <TraceScaffold trace={trace} caseFile={caseFile} active="authority">
        <Banner tone="info">The authority view is available for authority-cue variants only. This trace is <strong>{trace.variant}</strong>.</Banner>
      </TraceScaffold>
    );
  }

  const extra: Highlight[] = auth?.ack_span ? [{ start: auth.ack_span[0], end: auth.ack_span[1], kind: 'ack', label: 'acknowledges cue', id: 'ack', priority: 4 }] : [];

  return (
    <TraceScaffold trace={trace} caseFile={caseFile} active="authority">
      <div className="panel" style={{ marginBottom: 10 }}>
        <div className="row">
          <OutcomeBadge outcome={auth?.outcome} large />
          {cue && <Chip tone="cue" icon="▲">cue: {entityDisplay(lexicon, cue.entity)} ({cue.correct ? 'correct' : 'wrong'})</Chip>}
          {auth && <Chip tone="neutral">base modal: {entityDisplay(lexicon, auth.base_modal_entity)}{auth.base_stable ? '' : ' (unstable)'}</Chip>}
          {auth?.held_detail && <Chip tone="neutral">{auth.held_detail}</Chip>}
          {auth?.flags.map((f) => <Chip key={f} tone="warn" icon="!">{f.replace(/_/g, ' ')}</Chip>)}
        </div>
        {variant.perturbation?.rationale && <p className="muted small" style={{ margin: '6px 0 0' }}>{variant.perturbation.rationale}</p>}
        {auth && !auth.acknowledged && (
          <Banner tone={auth.outcome === 'shifted_silent' ? 'bad' : 'warn'}>No acknowledgement of the injected suggestion found.</Banner>
        )}
        {auth?.acknowledged && <Banner tone="good">The trace acknowledges the injected suggestion (highlighted below).</Banner>}
      </div>

      <div className="grid-2">
        <AnswerCard title={baseTrace ? `Base modal answer (run ${baseTrace.run}, effort ${trace.effort})` : 'Base modal answer'} answer={baseTrace?.answer ?? `(no base trace) ${entityDisplay(lexicon, baseModal)}`} lexicon={lexicon} grounding={baseTrace?.grounding ?? null} />
        <AnswerCard title="Cued answer" answer={trace.answer} lexicon={lexicon} grounding={trace.grounding} truthEntity={caseFile.case.entity} />
      </div>

      <div className="grid-2" style={{ marginTop: 12 }}>
        <ReportPane reports={variant.reports} sections={caseFile.case.sections} highlights={cueHighlights} scrollTo="cue" title={`Documents with cue (${trace.variant})`} />
        <TracePane reasoning={trace.reasoning} claims={trace.claims} extraHighlights={extra} scrollToHighlightId={auth?.ack_span ? 'ack' : null} selectedClaimId={selected?.claim_id ?? null} onSelectClaim={setSelected} title="Cued trace" />
      </div>
    </TraceScaffold>
  );
}
