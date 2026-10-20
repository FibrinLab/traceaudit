import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore, useTrace } from '../store';
import { variantKindOf, type Claim } from '../types';
import { TracePane } from '../components/TracePane';
import { Banner, Loading } from '../components/Shared';
import { TraceScaffold, baseTracesFor } from '../components/TraceScaffold';
import { entityDisplay } from '../lib/format';
import { ClaimStrip, Constellation, ConstellationLegend } from '../constellation/Constellation';
import { ChartFrame } from '../charts/ChartFrame';
import { buildConstellation } from '../constellation/graph';

export function MapView({ traceKey }: { traceKey: string }) {
  const { bundle } = useStore();
  const { caseFile, trace, error, loading } = useTrace(traceKey);
  const lexicon = bundle!.index.lexicon;
  const [selected, setSelected] = useState<{ claim: Claim; fromBase: boolean } | null>(null);
  const [overlay, setOverlay] = useState(false);
  const [baseRun, setBaseRun] = useState<number | null>(null);
  const [visible, setVisible] = useState<Set<number> | undefined>(undefined);
  const svgRef = useRef<SVGSVGElement>(null);
  useEffect(() => { setSelected(null); setOverlay(false); setBaseRun(null); }, [traceKey]);

  const kind = trace ? variantKindOf(trace.variant) : 'base';
  const canOverlay = kind === 'decisive' || kind === 'anchor_loss' || kind === 'neutral';
  const baseTraces = useMemo(() => caseFile && trace ? baseTracesFor(caseFile, trace.effort).filter((t) => t.map) : [], [caseFile, trace]);
  const baseTrace = useMemo(() => {
    if (!baseTraces.length) return null;
    const modal = trace?.counterfactual?.base_modal_entity ?? null;
    if (baseRun !== null) return baseTraces.find((t) => t.run === baseRun) ?? null;
    return baseTraces.find((t) => t.grounding?.answer_entity === modal) ?? baseTraces[0];
  }, [baseTraces, baseRun, trace]);
  const editedFindings = useMemo(() => new Set([trace?.counterfactual?.primary_finding, ...(trace?.counterfactual?.co_edits ?? [])].filter((x): x is string => !!x)), [trace]);
  const graph = useMemo(() => trace && caseFile ? buildConstellation(trace, caseFile, lexicon, { baseTrace: overlay ? baseTrace : null, editedFindings }) : null, [trace, caseFile, lexicon, overlay, baseTrace, editedFindings]);

  if (error) return <Banner tone="bad">{error}</Banner>;
  if (loading || !trace || !caseFile) return <Loading what={`trace ${traceKey}`} />;
  if (!trace.map) {
    return <TraceScaffold trace={trace} caseFile={caseFile} active="map"><Banner tone="info">No precomputed reasoning map for this trace, so there is nothing to draw.</Banner></TraceScaffold>;
  }

  const breaks = trace.map.nodes.filter((n) => n.break && n.type !== 'answer').length;
  const table = graph ? {
    columns: ['Node', 'Band', 'Kind', 'Grounding', 'Text', 'Origin'],
    rows: graph.nodes.map((n) => [n.id, n.band === 0 ? 'source finding' : n.band === 1 ? 'claim' : 'answer', n.band === 0 ? `${n.polarity} in ${n.report}` : n.claimType ?? '', n.grounding ?? '', n.text, n.origin]),
  } : undefined;

  return (
    <TraceScaffold trace={trace} caseFile={caseFile} active="map">
      <ChartFrame id={`constellation-${trace.trace_key.replace(/[|]/g, '_')}`} title="Reasoning constellation" svgRef={svgRef} table={table} exportData={graph}
        subtitle={<>Findings the model was shown on the left, grouped by document section; its claims in the middle, coloured by grounding; the answer on the right. Edges are heuristic (built by <code>export.build_map</code>) and explanatory only; they play no part in scoring. {breaks > 0 ? `${breaks} inference${breaks > 1 ? 's' : ''} with no incoming evidence.` : 'Every inference has incoming evidence.'}</>}
        aside={
          <>
            <div className="row" style={{ marginTop: 10 }}>
              <ConstellationLegend overlay={overlay} />
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              {canOverlay && <label className="inline"><input type="checkbox" checked={overlay} onChange={(e) => setOverlay(e.target.checked)} disabled={!baseTrace} /> Overlay the base constellation</label>}
              {overlay && baseTraces.length > 1 && (
                <label className="inline">Base run{' '}
                  <select value={baseTrace?.run ?? ''} onChange={(e) => setBaseRun(Number(e.target.value))} aria-label="Base run for the overlay">
                    {baseTraces.map((t) => <option key={t.run} value={t.run}>run {t.run}, {entityDisplay(lexicon, t.grounding?.answer_entity)}</option>)}
                  </select>
                </label>
              )}
              {overlay && <span className="muted small">Nodes matched on (type, findings, categories) sit in place; base-only nodes are ghosts.</span>}
              {selected && <button type="button" className="btn small" onClick={() => setSelected(null)}>Clear selection</button>}
            </div>
            <ClaimStrip claims={trace.claims} selectedClaimId={selected && !selected.fromBase ? selected.claim.claim_id : null} onSelect={(c) => setSelected({ claim: c, fromBase: false })} visibleIds={visible} />
          </>
        }>
        <Constellation trace={trace} caseFile={caseFile} lexicon={lexicon} baseTrace={overlay ? baseTrace : null} editedFindings={editedFindings} svgRef={svgRef}
          selectedClaimId={selected ? selected.claim.claim_id : null} onSelectClaim={(c, fromBase) => setSelected(c ? { claim: c, fromBase: !!fromBase } : null)} />
      </ChartFrame>

      <div className="grid-2" style={{ marginTop: 16 }}>
        <TracePane reasoning={trace.reasoning} claims={trace.claims} selectedClaimId={selected && !selected.fromBase ? selected.claim.claim_id : null} onSelectClaim={(c) => setSelected({ claim: c, fromBase: false })} scrollToHighlightId={selected && !selected.fromBase ? `claim-${selected.claim.claim_id}` : null} title="This trace" onVisibleClaims={setVisible} />
        {overlay && baseTrace && <TracePane reasoning={baseTrace.reasoning} claims={baseTrace.claims} selectedClaimId={selected?.fromBase ? selected.claim.claim_id : null} onSelectClaim={(c) => setSelected({ claim: c, fromBase: true })} scrollToHighlightId={selected?.fromBase ? `claim-${selected.claim.claim_id}` : null} title={`Base trace, run ${baseTrace.run}`} />}
      </div>
    </TraceScaffold>
  );
}
