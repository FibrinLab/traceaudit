import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import type { CaseFile, Claim, Lexicon, Trace } from '../types';
import { sectionTitle, sectionsFor } from '../lib/documents';
import { buildConstellation, defaultBandX, edgeLength, edgePath, frameHeight, type CNode, type Constellation as CGraph } from './graph';
import { useBandLayout } from './useBandLayout';
import { entityColor, entityShort } from '../lib/palette';
import { entityDisplay, labelIcon } from '../lib/format';
import { prefersReducedMotion } from '../components/ReportPane';
import { useTooltip } from '../charts/Tooltip';

/** Document sections in order wear an ordinal ramp of the one hue (the accent), dim to bright: step i of n. */
export function sectionColor(index: number, count: number): string {
  const step = count <= 1 ? 6 : 2 + Math.round((index / (count - 1)) * 4);
  return `var(--heat-${Math.max(2, Math.min(6, step))})`;
}

export interface ConstellationProps {
  trace: Trace;
  caseFile: CaseFile;
  lexicon: Lexicon;
  baseTrace?: Trace | null;
  editedFindings?: Set<string>;
  compact?: boolean;
  selectedClaimId: number | null;
  onSelectClaim: (claim: Claim | null, fromBase?: boolean) => void;
  /** Hide the truth entity (never used in rate mode, but kept explicit). */
  showTruth?: boolean;
  svgRef?: React.RefObject<SVGSVGElement>;
}

export function Constellation({ trace, caseFile, lexicon, baseTrace = null, editedFindings, compact = false, selectedClaimId, onSelectClaim, showTruth = true, svgRef }: ConstellationProps) {
  const W = 1000;
  const graph: CGraph = useMemo(() => buildConstellation(trace, caseFile, lexicon, { baseTrace, editedFindings, truthEntity: caseFile.case.entity }), [trace, caseFile, lexicon, baseTrace, editedFindings]);
  const H = useMemo(() => frameHeight(graph.nodes, compact), [graph, compact]);
  const { positions, ready } = useBandLayout(graph.nodes, graph.edges, { width: W, height: H, compact, seed: 3 });
  const tip = useTooltip();
  const [hover, setHover] = useState<string | null>(null);
  const localRef = useRef<SVGSVGElement>(null);
  const ref = svgRef ?? localRef;
  const [animate, setAnimate] = useState(false);
  const animatedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!ready) return;
    if (animatedFor.current === trace.trace_key || prefersReducedMotion()) { setAnimate(false); return; }
    animatedFor.current = trace.trace_key;
    setAnimate(true);
    const t = window.setTimeout(() => setAnimate(false), 1600);
    return () => window.clearTimeout(t);
  }, [ready, trace.trace_key]);

  const claimById = useMemo(() => new Map(trace.claims.map((c) => [c.claim_id, c])), [trace]);
  const baseClaimById = useMemo(() => new Map((baseTrace?.claims ?? []).map((c) => [c.claim_id, c])), [baseTrace]);
  const nodeById = useMemo(() => new Map(graph.nodes.map((n) => [n.id, n])), [graph]);
  const outgoing = useMemo(() => { const m = new Map<string, string[]>(); for (const e of graph.edges) m.set(e.source, [...(m.get(e.source) ?? []), e.target]); return m; }, [graph]);
  const incoming = useMemo(() => { const m = new Map<string, string[]>(); for (const e of graph.edges) m.set(e.target, [...(m.get(e.target) ?? []), e.source]); return m; }, [graph]);

  const selectedId = useMemo(() => selectedClaimId === null ? null : graph.nodes.find((n) => n.claimId === selectedClaimId && n.origin !== 'base-only')?.id ?? graph.nodes.find((n) => n.claimId === selectedClaimId)?.id ?? null, [graph, selectedClaimId]);
  const focusId = hover ?? selectedId;
  const litSet = useMemo(() => {
    if (!focusId) return null;
    const s = new Set<string>([focusId]);
    for (const x of outgoing.get(focusId) ?? []) s.add(x);
    for (const x of incoming.get(focusId) ?? []) s.add(x);
    return s;
  }, [focusId, outgoing, incoming]);

  const activate = (n: CNode) => {
    if (n.band === 2) { onSelectClaim(null); return; }
    if (n.band === 0) { onSelectClaim(null); return; }
    const c = n.origin === 'base-only' ? baseClaimById.get(n.claimId ?? -1) : claimById.get(n.claimId ?? -1);
    if (c) onSelectClaim(c, n.origin === 'base-only');
  };
  const focusNode = (id: string | undefined) => { if (!id) return; ref.current?.querySelector<SVGGElement>(`[data-node="${CSS.escape(id)}"]`)?.focus(); };
  const onKey = (e: KeyboardEvent<SVGGElement>, n: CNode) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(n); return; }
    if (e.key === 'Escape') { onSelectClaim(null); return; }
    if (e.key === 'ArrowRight') { e.preventDefault(); focusNode((outgoing.get(n.id) ?? [])[0]); return; }
    if (e.key === 'ArrowLeft') { e.preventDefault(); focusNode((incoming.get(n.id) ?? [])[0]); return; }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const band = graph.nodes.filter((x) => x.band === n.band).sort((a, b) => (positions.get(a.id)?.y ?? 0) - (positions.get(b.id)?.y ?? 0));
      const i = band.findIndex((x) => x.id === n.id);
      focusNode(band[e.key === 'ArrowDown' ? Math.min(band.length - 1, i + 1) : Math.max(0, i - 1)]?.id);
    }
  };

  const sections = useMemo(() => sectionsFor(caseFile.case.reports, caseFile.case.sections), [caseFile]);
  const sectionIds = sections.map((s) => s.id);
  const colorOf = (report: string | undefined) => sectionColor(Math.max(0, sectionIds.indexOf(report ?? '')), sectionIds.length);
  const tipFor = (n: CNode) => (
    <>
      <strong>{n.band === 0 ? n.label : n.claimType === 'answer' ? `Answer: ${entityDisplay(lexicon, n.entity)}` : `${n.claimType} claim${n.grounding ? `, ${n.grounding}` : ''}`}</strong>
      {n.band === 0 && <div className="muted">{n.polarity === 'pos' ? 'Positive' : 'Negative'} in {sectionTitle(sections, n.report ?? sectionIds[0] ?? '')}{n.edited ? '; edited in this variant' : ''}</div>}
      {n.band !== 0 && <div style={{ maxWidth: 280 }}>{n.text}</div>}
      {n.break && <div style={{ color: 'var(--contradicted)' }}>Broken chain: no incoming evidence</div>}
      {n.origin === 'base-only' && <div className="muted">Only in the base trace</div>}
      {n.origin === 'this' && baseTrace && n.band === 1 && <div style={{ color: 'var(--edited)' }}>New in this variant</div>}
    </>
  );

  const fill = (n: CNode) => {
    if (n.band === 0) return colorOf(n.report);
    if (n.shape === 'answer') return entityColor(lexicon, n.entity);
    if (n.shape === 'diamond') return 'var(--inferential)';
    if (n.shape === 'ring') return 'none';
    return n.grounding === 'supported' ? 'var(--supported)' : n.grounding === 'contradicted' ? 'var(--contradicted)' : n.grounding === 'unsupported' ? 'var(--unsupported)' : 'var(--text-2)';
  };
  const bandX = defaultBandX(W);
  const reportGroups = useMemo(() => sections.map((s) => ({ r: s.id, title: s.title, ys: graph.nodes.filter((n) => n.band === 0 && n.report === s.id).map((n) => positions.get(n.id)?.y ?? 0) })).filter((g) => g.ys.length), [graph, positions, sections]);
  const truth = showTruth ? caseFile.case.entity : null;
  let delayIndex = 0;

  return (
    <div className={`constellation${animate ? ' animate' : ''}`} aria-busy={!ready}>
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Reasoning constellation" style={{ opacity: ready ? 1 : 0.4, transition: 'opacity 200ms' }}>
        {[['Source findings', 0], ['Claims', 1], ['Answer', 2]].map(([t, i]) => (
          <text key={String(t)} x={bandX[i as number]} y={11} textAnchor="middle" className="band-label">{t}</text>
        ))}
        {!compact && reportGroups.map((g) => {
          const y0 = Math.min(...g.ys), y1 = Math.max(...g.ys);
          const rx = bandX[0] - 178;
          return (
            <g key={g.r}>
              <line x1={rx} x2={rx} y1={y0 - 6} y2={y1 + 6} stroke={colorOf(g.r)} strokeWidth={2} strokeLinecap="round" />
              <text transform={`translate(${rx - 6} ${(y0 + y1) / 2}) rotate(-90)`} textAnchor="middle" className="muted" style={{ fontSize: 10.5 }}>{y1 - y0 > 60 ? g.title : g.title.split(' ')[0]}</text>
            </g>
          );
        })}
        <g>
          {graph.edges.map((e) => {
            const a = positions.get(e.source), b = positions.get(e.target);
            if (!a || !b) return null;
            const lit = !litSet || (litSet.has(e.source) && litSet.has(e.target));
            const len = edgeLength(a, b);
            const cls = ['edge', e.kind === 'reads' ? 'evidence' : e.kind, e.flip ? 'flip' : '', e.weak ? 'weak' : '', e.origin === 'base-only' ? 'ghost' : '', animate ? 'animated' : ''].filter(Boolean).join(' ');
            const delay = e.kind === 'reads' ? 0 : e.kind === 'conclusion' ? 500 : 250;
            delayIndex++;
            return <path key={e.id} d={edgePath(a, b)} className={cls} opacity={lit ? 1 : 0.12} style={{ ['--len' as string]: len, ['--delay' as string]: `${delay + (delayIndex % 7) * 20}ms` }}><title>{`${nodeById.get(e.source)?.label} → ${nodeById.get(e.target)?.label}${e.flip ? ' (flipped)' : ''}`}</title></path>;
          })}
        </g>
        {graph.nodes.map((n) => {
          const p = positions.get(n.id);
          if (!p) return null;
          const lit = !litSet || litSet.has(n.id);
          const sel = n.id === selectedId;
          const r = n.band === 2 ? (compact ? 14 : 22) : n.band === 0 ? (compact ? 4 : 5.5) : (compact ? 6 : 8);
          const cls = ['node', n.origin === 'base-only' ? 'ghost' : '', sel ? 'selected' : '', animate && baseTrace && n.origin === 'this' && n.band === 1 ? 'new' : ''].filter(Boolean).join(' ');
          const labelOn = !compact || sel || hover === n.id || n.band === 2;
          return (
            <g key={n.id} data-node={n.id} className={cls} transform={`translate(${p.x} ${p.y})`} opacity={lit ? 1 : 0.22} tabIndex={0} role="button" aria-pressed={sel}
              aria-label={`${n.band === 0 ? 'Finding' : n.claimType === 'answer' ? 'Answer' : `${n.claimType} claim`} ${n.band === 0 ? n.text : n.text}${n.grounding ? `, ${n.grounding}` : ''}${n.break ? ', broken chain' : ''}`}
              onMouseEnter={(e) => { setHover(n.id); tip.show(e, tipFor(n)); }} onMouseMove={tip.move} onMouseLeave={() => { setHover(null); tip.hide(); }}
              onFocus={(e) => { setHover(n.id); tip.show(e, tipFor(n)); }} onBlur={() => { setHover(null); tip.hide(); }}
              onClick={() => activate(n)} onKeyDown={(e) => onKey(e, n)}>
              <circle r={Math.max(12, r + 6)} fill="transparent" />
              {n.shape === 'diamond' && <rect x={-r} y={-r} width={r * 2} height={r * 2} transform="rotate(45)" fill={fill(n)} stroke="var(--ink-2)" strokeWidth={2} />}
              {n.shape === 'ring' && <circle r={r} fill="var(--ink-2)" stroke="var(--knowledge)" strokeWidth={2} strokeDasharray="3 2.5" />}
              {n.shape === 'disc' && <circle r={r} fill={fill(n)} stroke="var(--ink-2)" strokeWidth={2} />}
              {n.shape === 'finding' && <circle r={r} fill={n.polarity === 'neg' ? 'var(--ink-2)' : fill(n)} stroke={fill(n)} strokeWidth={1.8} />}
              {n.shape === 'answer' && <circle r={r} fill={fill(n)} stroke="var(--ink-2)" strokeWidth={3} />}
              <circle r={r + 4} className="focus-ring" />
              {n.break && n.shape !== 'answer' && <circle cx={-r - 7} cy={0} r={3} fill="none" stroke="var(--contradicted)" strokeWidth={1.5} strokeDasharray="2 2"><title>Broken chain: no incoming evidence</title></circle>}
              {n.edited && <text x={n.band === 0 ? -r - 4 : r + 4} y={-r - 2} textAnchor={n.band === 0 ? 'end' : 'start'} style={{ fontSize: 11, fill: 'var(--edited)', fontWeight: 600 }}>✎</text>}
              {labelOn && n.band === 0 && <text x={-r - 6} y={4} textAnchor="end" className={compact ? '' : n.polarity === 'neg' ? 'sub' : ''} style={compact ? { paintOrder: 'stroke', stroke: 'var(--ink-2)', strokeWidth: 3 } : undefined}>{n.label}{n.polarity === 'neg' ? ' −' : ''}</text>}
              {labelOn && n.band === 1 && (
                <text x={r + 6} y={4} style={compact ? { paintOrder: 'stroke', stroke: 'var(--ink-2)', strokeWidth: 3 } : undefined}>
                  <tspan className="sub">{labelIcon(n.grounding ?? (n.claimType === 'inferential' ? 'inferential' : n.claimType === 'knowledge' ? 'knowledge' : 'other'))} </tspan>{compact ? n.label.slice(0, 26) : n.label}
                </text>
              )}
              {n.band === 2 && (
                <>
                  <text textAnchor="middle" y={r + 16} style={{ fontSize: 12.5, fontWeight: 600 }}>{entityShort(n.entity)}</text>
                  {n.origin !== 'base-only' && truth && <text textAnchor="middle" y={r + 30} className="sub">{n.entity === truth ? '✓ matches truth' : `truth ${entityShort(truth)}`}</text>}
                  {n.origin === 'base-only' && <text textAnchor="middle" y={r + 30} className="sub">base answer</text>}
                  {n.break && <text textAnchor="middle" y={-r - 8} className="sub" style={{ fill: 'var(--contradicted)' }}>weak conclusion</text>}
                </>
              )}
            </g>
          );
        })}
      </svg>
      <div className="visually-hidden">
        <h4>Constellation nodes</h4>
        <ol>{graph.nodes.map((n) => <li key={n.id}>{n.band === 0 ? `Finding ${n.text}` : n.claimType === 'answer' ? `Answer ${entityDisplay(lexicon, n.entity)}` : `${n.claimType} claim${n.grounding ? ` (${n.grounding})` : ''}: ${n.text}`}{n.origin === 'base-only' ? ' (base only)' : ''}</li>)}</ol>
      </div>
      {tip.node}
    </div>
  );
}

/** Legend for the constellation; shared by the map and grounding views. */
export function ConstellationLegend({ overlay }: { overlay?: boolean }) {
  return (
    <ul className="legend" aria-label="Constellation legend" style={{ margin: 0, padding: 0, listStyle: 'none' }}>
      <li className="key"><i style={{ background: 'var(--supported)' }} />supported claim</li>
      <li className="key"><i style={{ background: 'var(--contradicted)' }} />contradicted claim</li>
      <li className="key"><i style={{ background: 'var(--unsupported)' }} />unsupported claim</li>
      <li className="key"><i className="diamond" style={{ background: 'var(--inferential)' }} />inference</li>
      <li className="key"><i className="ring" style={{ borderColor: 'var(--knowledge)', borderStyle: 'dashed' }} />knowledge</li>
      <li className="key"><i className="line" style={{ background: 'var(--supported)' }} />evidence read as reported</li>
      <li className="key"><i className="line" style={{ background: 'var(--contradicted)' }} />evidence flipped</li>
      <li className="key"><i className="ring" style={{ borderColor: 'var(--contradicted)', borderStyle: 'dashed', width: 8, height: 8 }} />broken chain</li>
      <li className="key">findings coloured by document section, first (dimmer) to last (brighter); hollow = stated negative</li>
      {overlay && <li className="key"><i style={{ background: 'var(--text-2)', opacity: 0.3 }} />base only (ghost); <span style={{ color: 'var(--edited)' }}>✎</span> edited finding; new claims are ringed once</li>}
    </ul>
  );
}

/** Sequential strip: claims in reading order as tiles, synced with the selection. */
export function ClaimStrip({ claims, selectedClaimId, onSelect, visibleIds }: { claims: Claim[]; selectedClaimId: number | null; onSelect: (c: Claim) => void; visibleIds?: Set<number> }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (selectedClaimId === null) return;
    ref.current?.querySelector<HTMLElement>(`[data-claim="${selectedClaimId}"]`)?.scrollIntoView({ block: 'nearest', inline: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
  }, [selectedClaimId]);
  const kind = (c: Claim) => c.type === 'factual' ? (c.label ?? 'other') : c.type;
  return (
    <div className="strip" ref={ref} role="listbox" aria-label="Claims in reading order">
      {claims.filter((c) => c.type !== 'other').map((c) => (
        <button key={c.claim_id} type="button" role="option" data-claim={c.claim_id} className={`${kind(c)}${visibleIds && !visibleIds.has(c.claim_id) ? ' off' : ''}`} aria-selected={selectedClaimId === c.claim_id} aria-pressed={selectedClaimId === c.claim_id}
          title={`${kind(c)}: ${c.text}`} aria-label={`${kind(c)} claim ${c.claim_id}: ${c.text}`} onClick={() => onSelect(c)} />
      ))}
    </div>
  );
}
