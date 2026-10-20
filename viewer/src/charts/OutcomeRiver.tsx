import { useMemo, useRef, useState } from 'react';
import { sankey, sankeyJustify, sankeyLinkHorizontal, type SankeyLink, type SankeyNode } from 'd3-sankey';
import type { Lexicon, Outcome } from '../types';
import type { TraceRow } from '../lib/cohort';
import { buildRiver, COLUMN_TITLES, linkShare, type RiverLink, type RiverNode } from './river';
import { entityColor, entityShort, OUTCOME_COLOR, OUTCOME_GLYPH } from '../lib/palette';
import { OUTCOME_META } from '../lib/format';
import { wilson } from '../lib/stats';
import { pct } from '../lib/format';
import { ChartFrame } from './ChartFrame';
import { TipRow, useTooltip } from './Tooltip';

type SNode = SankeyNode<RiverNode, RiverLink>;
type SLink = SankeyLink<RiverNode, RiverLink>;

export interface RiverPin { source: string; target: string }

interface Props {
  rows: TraceRow[];
  lexicon: Lexicon;
  pin: RiverPin | null;
  onPin: (p: RiverPin | null, link: RiverLink | null) => void;
  onNode: (node: RiverNode) => void;
}

const W = 1120, H = 420, M = { top: 28, right: 150, bottom: 8, left: 110 };

export function OutcomeRiver({ rows, lexicon, pin, onPin, onNode }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tip = useTooltip();
  const [hover, setHover] = useState<string | null>(null);
  const river = useMemo(() => buildRiver(rows, (id) => entityShort(id), (o) => OUTCOME_META[o as Outcome]?.text ?? o), [rows]);

  const laid = useMemo(() => {
    if (!river.nodes.length) return null;
    const gen = sankey<RiverNode, RiverLink>()
      .nodeId((d) => d.id)
      .nodeWidth(10)
      .nodePadding(10)
      .nodeAlign(sankeyJustify)
      .nodeSort((a, b) => a.column - b.column || (b.value ?? 0) - (a.value ?? 0))
      .linkSort((a, b) => (b.value ?? 0) - (a.value ?? 0))
      .extent([[M.left, M.top], [W - M.right, H - M.bottom]]);
    return gen({ nodes: river.nodes.map((n) => ({ ...n })), links: river.links.map((l) => ({ ...l })) });
  }, [river]);

  const path = sankeyLinkHorizontal<RiverNode, RiverLink>();
  const linkColor = (l: SLink) => entityColor(lexicon, l.entity);
  const nodeColor = (n: SNode) => n.column === 3 ? (OUTCOME_COLOR[n.key as Outcome] ?? 'var(--neutral)') : n.column === 1 ? 'var(--text-2)' : entityColor(lexicon, n.key);
  const isPinned = (l: SLink) => pin && (l.source as SNode).id === pin.source && (l.target as SNode).id === pin.target;
  const emphasis = (l: SLink) => {
    const sid = (l.source as SNode).id, tid = (l.target as SNode).id;
    if (pin) return isPinned(l) ? 1 : 0.15;
    if (hover) return hover === l.id || hover === sid || hover === tid ? 1 : 0.2;
    return 0.72;
  };

  const linkTip = (l: SLink) => {
    const share = linkShare(river, l as unknown as RiverLink);
    const iv = wilson(share.k, share.n);
    return (
      <>
        <strong>{l.value} traces</strong>
        <div>{(l.source as SNode).label} to {(l.target as SNode).label}</div>
        <div className="muted">{pct(iv.point, 0)} of {share.n} from {(l.source as SNode).label}, 95% CI {pct(iv.lo, 0)} to {pct(iv.hi, 0)} (Wilson)</div>
        <TipRow color={linkColor(l)} label="base answer" value={entityShort(l.entity)} />
        <div className="muted">Click to pin this ribbon and filter the dashboard.</div>
      </>
    );
  };
  const nodeTip = (n: SNode) => (
    <>
      <strong>{n.value} traces</strong>
      <div>{COLUMN_TITLES[n.column]}: {n.label}</div>
      {n.column === 3 && <div className="muted">{OUTCOME_META[n.key as Outcome]?.description}</div>}
      {n.column !== 3 && <div className="muted">Click to filter by this {n.column === 1 ? 'edit kind' : 'category'}.</div>}
    </>
  );

  const table = useMemo(() => ({
    columns: ['From', 'To', 'Base answer', 'n', 'Share of source'],
    rows: river.links.map((l) => {
      const s = river.nodes.find((n) => n.id === l.source)!, t = river.nodes.find((n) => n.id === l.target)!;
      const sh = linkShare(river, l);
      return [s.label, t.label, entityShort(l.entity), l.value, sh.n ? sh.k / sh.n : null];
    }),
  }), [river]);

  const legend = useMemo(() => {
    const ents = [...new Set(river.links.map((l) => l.entity ?? 'UNRESOLVED'))];
    return ents.map((e) => ({ label: `base ${entityShort(e)}`, color: entityColor(lexicon, e) }));
  }, [river, lexicon]);

  return (
    <ChartFrame id="outcome-river" title="Outcome river" headingLevel={2} svgRef={svgRef} table={table} legend={legend}
      exportData={{ id: 'outcome-river', columns: COLUMN_TITLES, nodes: river.nodes, links: river.links.map(({ trace_keys, ...l }) => ({ ...l, n_trace_keys: trace_keys.length })) }}
      subtitle={<>Each perturbed trace flows from the model's base answer through the kind of edit it received to its answer afterwards and the scored outcome. Ribbon colour is the base answer's category; the outcome column wears the status colours. {river.n} traces in view.</>}
      tooltip={tip.node}>
      {!laid ? <p className="muted">No perturbed traces match the filters.</p> : (
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Outcome river, a flow diagram">
          {COLUMN_TITLES.map((t, i) => {
            const col = laid.nodes.filter((n) => n.column === i);
            const x = col.length ? (col[0].x0! + col[0].x1!) / 2 : 0;
            return <text key={t} x={x} y={16} textAnchor={i === 0 ? 'start' : i === 3 ? 'end' : 'middle'} className="muted" style={{ fontSize: 12 }}>{t}</text>;
          })}
          <g fill="none">
            {laid.links.map((l) => (
              <path key={l.id} d={path(l) ?? undefined} stroke={linkColor(l)} strokeWidth={Math.max(1.5, l.width ?? 1)} strokeOpacity={emphasis(l)}
                className="mark" tabIndex={0} role="button" aria-label={`${l.value} traces from ${(l.source as SNode).label} to ${(l.target as SNode).label}`}
                aria-pressed={!!isPinned(l)}
                onMouseEnter={(e) => { setHover(l.id); tip.show(e, linkTip(l)); }} onMouseMove={tip.move} onMouseLeave={() => { setHover(null); tip.hide(); }}
                onFocus={(e) => { setHover(l.id); tip.show(e, linkTip(l)); }} onBlur={() => { setHover(null); tip.hide(); }}
                onClick={() => onPin(isPinned(l) ? null : { source: (l.source as SNode).id, target: (l.target as SNode).id }, isPinned(l) ? null : (l as unknown as RiverLink))}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPin(isPinned(l) ? null : { source: (l.source as SNode).id, target: (l.target as SNode).id }, isPinned(l) ? null : (l as unknown as RiverLink)); } }}
              />
            ))}
          </g>
          {laid.nodes.map((n) => {
            const h = Math.max(2, (n.y1 ?? 0) - (n.y0 ?? 0));
            const labelX = n.column === 0 ? n.x0! - 8 : n.x1! + 8;
            const anchor = n.column === 0 ? 'end' : 'start';
            const labelY = (n.y0! + n.y1!) / 2 + 4;
            const showLabel = h >= 10 || n.column === 0 || n.column === 3;
            const halo = n.column === 1 || n.column === 2 ? { paintOrder: 'stroke' as const, stroke: 'var(--ink-2)', strokeWidth: 4, strokeLinejoin: 'round' as const } : {};
            const dim = (pin && !laid.links.some((l) => isPinned(l) && ((l.source as SNode).id === n.id || (l.target as SNode).id === n.id))) || (hover && hover !== n.id && !laid.links.some((l) => l.id === hover && ((l.source as SNode).id === n.id || (l.target as SNode).id === n.id)));
            return (
              <g key={n.id} className="mark" opacity={dim ? 0.35 : 1} tabIndex={0} role="button" aria-label={`${COLUMN_TITLES[n.column]} ${n.label}, ${n.value} traces`}
                onMouseEnter={(e) => { setHover(n.id); tip.show(e, nodeTip(n)); }} onMouseMove={tip.move} onMouseLeave={() => { setHover(null); tip.hide(); }}
                onFocus={(e) => { setHover(n.id); tip.show(e, nodeTip(n)); }} onBlur={() => { setHover(null); tip.hide(); }}
                onClick={() => onNode(n)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNode(n); } }}>
                <rect x={n.x0} y={n.y0} width={(n.x1 ?? 0) - (n.x0 ?? 0)} height={h} fill={nodeColor(n)} rx={2} />
                {showLabel && (
                  <text x={labelX} y={labelY} textAnchor={anchor} style={{ fontSize: 12.5, ...halo }}>
                    {n.column === 3 && <tspan style={{ fontWeight: 600 }} fill={nodeColor(n)}>{OUTCOME_GLYPH[n.key as Outcome] ?? ''} </tspan>}
                    {n.label}
                    <tspan className="muted" style={{ fontSize: 11 }}> {n.value}</tspan>
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}
    </ChartFrame>
  );
}
