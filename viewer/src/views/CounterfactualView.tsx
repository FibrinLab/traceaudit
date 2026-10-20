import { useEffect, useMemo, useState } from 'react';
import { useStore, useTrace } from '../store';
import { variantKindOf, type Claim, type DiffOp, type ReportName, type Variant } from '../types';
import { titleFromId } from '../lib/documents';
import { ReportPane, type ReportHighlight } from '../components/ReportPane';
import { TracePane } from '../components/TracePane';
import { AnswerCard, Banner, Chip, Loading, OutcomeBadge } from '../components/Shared';
import { TraceScaffold, baseTracesFor } from '../components/TraceScaffold';
import { entityDisplay, findingDisplay, polarityText } from '../lib/format';
import type { Highlight } from '../lib/spans';

export function diffHighlights(diff: Variant['diff'], side: 'base' | 'variant', labelFor?: (op: DiffOp, report: ReportName) => string): ReportHighlight[] {
  const out: ReportHighlight[] = [];
  for (const report of Object.keys(diff)) {
    const ops = diff[report] ?? [];
    ops.forEach((op, i) => {
      const span = side === 'base' ? op.base_span : op.variant_span;
      if (span[1] <= span[0]) return; // zero-width (insert/delete) on this side: listed in the footer instead
      out.push({ report, start: span[0], end: span[1], kind: 'edited', label: labelFor ? labelFor(op, report) : 'edited', id: `diff-${side}-${report}-${i}`, priority: 3,
        title: `${op.op}: “${op.before}” → “${op.after}”` });
    });
  }
  return out;
}

export function CounterfactualView({ traceKey }: { traceKey: string }) {
  const { bundle, settings, updateSettings } = useStore();
  const { caseFile, trace, error, loading } = useTrace(traceKey);
  const lexicon = bundle!.index.lexicon;
  const [baseRun, setBaseRun] = useState<number | null>(null);
  const [selected, setSelected] = useState<Claim | null>(null);
  const [scrollTarget, setScrollTarget] = useState<string | null>(null);

  useEffect(() => { setBaseRun(null); setSelected(null); setScrollTarget(null); }, [traceKey]);

  const cf = trace?.counterfactual ?? null;
  const variant = caseFile && trace ? caseFile.variants[trace.variant] : null;
  const baseVariant = caseFile?.variants.base ?? null;
  const baseTraces = useMemo(() => caseFile && trace ? baseTracesFor(caseFile, trace.effort) : [], [caseFile, trace]);
  const defaultBase = useMemo(() => {
    const modal = cf?.base_modal_entity ?? caseFile?.base_reference?.[trace?.effort ?? 'low']?.base_modal_entity ?? null;
    return baseTraces.find((t) => t.grounding?.answer_entity === modal) ?? baseTraces[0] ?? null;
  }, [baseTraces, cf, caseFile, trace]);
  const baseTrace = baseRun === null ? defaultBase : baseTraces.find((t) => t.run === baseRun) ?? defaultBase;

  useEffect(() => {
    if (cf?.primary_mention_span) setScrollTarget('primary-mention');
  }, [cf]);

  if (error) return <Banner tone="bad">{error}</Banner>;
  if (loading || !trace || !caseFile || !variant) return <Loading what={`trace ${traceKey}`} />;
  const kind = variantKindOf(trace.variant);
  if (kind === 'base' || kind === 'authority') {
    return (
      <TraceScaffold trace={trace} caseFile={caseFile} active="counterfactual">
        <Banner tone="info">The counterfactual diff is available for decisive, anchor-loss and neutral variants only. This trace is <strong>{trace.variant}</strong>.</Banner>
      </TraceScaffold>
    );
  }

  const pert = variant.perturbation;
  const baseHl = diffHighlights(variant.diff, 'base');
  const varHl = diffHighlights(variant.diff, 'variant');

  const editedLine = pert ? describeEdits(pert.edits.map((e) => ({ finding_id: e.finding_id, from: e.from, to: e.to, role: e.role, op: e.op, report: e.report })), (id) => findingDisplay(lexicon, id)) : '';
  const expectation = pert?.expected_entity ? `Expected: ${entityDisplay(lexicon, pert.expected_entity)}.` : pert?.expected_behaviour ? `Expected behaviour: ${pert.expected_behaviour}.` : '';

  const footers: Partial<Record<ReportName, JSX.Element>> = {};
  for (const r of Object.keys(variant.diff)) {
    const ops = variant.diff[r] ?? [];
    if (ops.length) {
      footers[r] = (
        <ul className="small muted" style={{ margin: '4px 0 0', paddingLeft: 18 }}>
          {ops.map((op, i) => <li key={i}><span className="hl-icon" aria-hidden="true">✎</span> {op.op}: “{op.before || '∅'}” → “{op.after || '∅'}”</li>)}
        </ul>
      );
    }
  }

  // Perturbed trace highlights: primary mention + optional linked mentions.
  const extra: Highlight[] = [];
  if (cf?.primary_mention_span) {
    extra.push({ start: cf.primary_mention_span[0], end: cf.primary_mention_span[1], kind: 'edited', label: `primary finding: ${findingDisplay(lexicon, cf.primary_finding)}`, id: 'primary-mention', priority: 4 });
  }
  if (settings.showLinkedMentions && cf) {
    const linked = new Set([...cf.linked_findings, ...cf.co_edits]);
    for (const c of trace.claims) for (const a of c.assertions) {
      if (linked.has(a.finding_id) && a.end > a.start) extra.push({ start: a.start, end: a.end, kind: 'mention', label: `linked: ${findingDisplay(lexicon, a.finding_id)}`, id: `linked-${c.claim_id}-${a.finding_id}`, priority: 3 });
    }
  }

  const baseRef = cf ? `base modal: ${entityDisplay(lexicon, cf.base_modal_entity)}, ${Math.round((cf.base_mode_share ?? 0) * cf.base_n)}/${cf.base_n} runs${cf.base_stable ? '' : ' (unstable)'}` : null;

  return (
    <TraceScaffold trace={trace} caseFile={caseFile} active="counterfactual">
      <div className="panel" style={{ marginBottom: 10 }}>
        <div className="row">
          <OutcomeBadge outcome={cf?.outcome} large />
          {baseRef && <Chip tone="neutral">{baseRef}</Chip>}
          {cf && (
            <span className="row small" role="group" aria-label="Disclosure rule sensitivity">
              <RuleChip id="D1" ok={cf.cited_primary} text="cited primary" />
              <RuleChip id="D2" ok={cf.mentioned_primary} text="mentioned primary" />
              <RuleChip id="D3" ok={cf.mentioned_any} text="mentioned any edit" />
            </span>
          )}
          {cf?.flags.map((f) => <Chip key={f} tone="warn" icon="!">{f.replace(/_/g, ' ')}</Chip>)}
        </div>
        {pert && (
          <p style={{ margin: '8px 0 0' }}>
            <span className="hl-icon" aria-hidden="true">✎</span> <strong>Edited:</strong> {editedLine || 'text-only edits'}. {expectation}
            {pert.rationale && <span className="muted"> — {pert.rationale}</span>}
          </p>
        )}
        {cf && !cf.primary_mention_span && cf.primary_finding && (
          <Banner tone="warn">Primary finding not cited in the trace ({findingDisplay(lexicon, cf.primary_finding)}).</Banner>
        )}
      </div>

      <div className="grid-2">
        <div>
          <h3 style={{ margin: '0 0 4px' }}>Base documents</h3>
          <ReportPane reports={baseVariant?.reports ?? caseFile.case.reports} sections={caseFile.case.sections} highlights={baseHl} title="base" />
        </div>
        <div>
          <h3 style={{ margin: '0 0 4px' }}>Variant documents — {trace.variant}</h3>
          <ReportPane reports={variant.reports} sections={caseFile.case.sections} highlights={varHl} footers={footers} title={trace.variant} />
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 12 }}>
        <div>
          <div className="row" style={{ marginBottom: 4 }}>
            <h3 style={{ margin: 0 }}>Base trace</h3>
            <label className="small">Run{' '}
              <select value={baseTrace?.run ?? ''} onChange={(e) => setBaseRun(Number(e.target.value))} aria-label="Base run">
                {baseTraces.map((t) => <option key={t.run} value={t.run}>run {t.run} — {entityDisplay(lexicon, t.grounding?.answer_entity)}{t.grounding?.answer_hedged ? ' (hedged)' : ''}</option>)}
              </select>
            </label>
          </div>
          {baseTrace ? (
            <>
              <AnswerCard title={`Base answer (run ${baseTrace.run})`} answer={baseTrace.answer} lexicon={lexicon} grounding={baseTrace.grounding} compact />
              <div style={{ marginTop: 6 }}>
                <TracePane reasoning={baseTrace.reasoning} claims={baseTrace.claims} selectedClaimId={selected?.claim_id ?? null} onSelectClaim={setSelected} title="base reasoning" />
              </div>
            </>
          ) : <Banner tone="info">No base trace at effort {trace.effort}.</Banner>}
        </div>
        <div>
          <div className="row" style={{ marginBottom: 4 }}>
            <h3 style={{ margin: 0 }}>Perturbed trace</h3>
            <label className="small"><input type="checkbox" checked={settings.showLinkedMentions} onChange={(e) => updateSettings({ showLinkedMentions: e.target.checked })} /> Show linked mentions</label>
          </div>
          <AnswerCard title="Perturbed answer" answer={trace.answer} lexicon={lexicon} grounding={trace.grounding} compact />
          <div style={{ marginTop: 6 }}>
            <TracePane reasoning={trace.reasoning} claims={trace.claims} extraHighlights={extra} scrollToHighlightId={scrollTarget} selectedClaimId={selected?.claim_id ?? null} onSelectClaim={setSelected} title="perturbed reasoning" />
          </div>
        </div>
      </div>
    </TraceScaffold>
  );
}

function RuleChip({ id, ok, text }: { id: string; ok: boolean | null; text: string }) {
  return <Chip tone={ok === null ? 'neutral' : ok ? 'good' : 'bad'} icon={ok === null ? '–' : ok ? '✓' : '✗'} title={text}>{id} {ok === null ? 'n/a' : ok ? 'yes' : 'no'}</Chip>;
}

export function describeEdits(edits: Array<{ finding_id: string | null; from: string | null; to: string | null; role: string; op: string | null; report: string }>, display: (id: string) => string): string {
  return edits.map((e) => {
    if (e.finding_id) return `${display(e.finding_id)} ${polarityText(e.from as 'pos' | 'neg' | null)} → ${polarityText(e.to as 'pos' | 'neg' | null)} (${e.role.replace('_', '-')})`;
    return `${(e.op ?? 'edit').replace(/_/g, ' ')} in ${titleFromId(e.report).toLowerCase()}`;
  }).join('; ');
}
