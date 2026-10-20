import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { forceCollide, forceLink, forceManyBody, forceRadial, forceSimulation, forceX, forceY, type SimulationLinkDatum, type SimulationNodeDatum } from 'd3-force';
import type { Lexicon } from '../types';
import { buildAtlas, neighbours, type Atlas, type AtlasNode } from './atlas';
import { entityColor, entityShort, seeded, warm } from '../lib/palette';
import { pct } from '../lib/format';
import { ChartFrame } from './ChartFrame';
import { useTooltip } from './Tooltip';

type SimNode = AtlasNode & SimulationNodeDatum;
type SimLink = SimulationLinkDatum<SimNode> & { expected: 'pos' | 'neg'; id: string };

const W = 1080, H = 560, CX = W / 2, CY = H / 2, RING = 190;

/** Deterministic force layout: hubs pinned on the ring, satellites relaxed around them. */
export function layoutAtlas(atlas: Atlas): { nodes: SimNode[]; links: SimLink[] } {
  const nodes: SimNode[] = atlas.nodes.map((n) => ({ ...n }));
  const rnd = seeded(7);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  for (const n of nodes) {
    if (n.ring) { n.fx = CX + n.ring.x * RING; n.fy = CY + n.ring.y * RING; n.x = n.fx; n.y = n.fy; }
    else { n.x = CX + (rnd() - 0.5) * 300; n.y = CY + (rnd() - 0.5) * 300; }
  }
  const links: SimLink[] = atlas.edges.filter((e) => byId.has(e.source) && byId.has(e.target)).map((e) => ({ id: e.id, source: e.source, target: e.target, expected: e.expected }));
  const linked = new Set(links.flatMap((l) => [l.source as string, l.target as string]));
  const sim = forceSimulation<SimNode>(nodes)
    .randomSource(seeded(11))
    .force('link', forceLink<SimNode, SimLink>(links).id((d) => d.id).distance((l) => (l.expected === 'pos' ? 95 : 150)).strength((l) => (l.expected === 'pos' ? 0.5 : 0.12)))
    .force('charge', forceManyBody<SimNode>().strength((d) => (d.kind === 'entity' ? -400 : -55)))
    .force('collide', forceCollide<SimNode>().radius((d) => (d.kind === 'entity' ? 30 : satR(d) + 7)).iterations(2))
    .force('x', forceX<SimNode>(CX).strength(0.03))
    .force('y', forceY<SimNode>(CY).strength(0.04))
    // Findings with no discriminator (context that points at no category) sit on an outer ring rather than drifting to the corners.
    .force('outer', forceRadial<SimNode>(RING + 70, CX, CY).strength((d) => (d.kind === 'finding' && !linked.has(d.id) ? 0.5 : 0)))
    .stop();
  for (let i = 0; i < 320; i++) sim.tick();
  for (const n of nodes) {
    if (n.ring) continue;
    const r = satR(n) + 6;
    n.x = Math.max(r + 70, Math.min(W - r - 70, n.x ?? CX));
    n.y = Math.max(r + 12, Math.min(H - r - 12, n.y ?? CY));
  }
  return { nodes, links };
}

function satR(n: AtlasNode): number { return 4 + Math.sqrt(n.size) * 1.1; }
/** Hub labels shrink with length so any lexicon's ids fit the 26px disc. */
export function hubFontSize(label: string): number { return label.length <= 4 ? 12 : label.length <= 7 ? 10 : label.length <= 10 ? 8 : 7; }

interface Props {
  lexicon: Lexicon;
  asserted: Map<string, number>;
  problems: Map<string, number>;
  filterEntity: string;
  filterFinding: string;
  onFilterEntity: (id: string) => void;
  onFilterFinding: (id: string) => void;
}

export function LexiconAtlas({ lexicon, asserted, problems, filterEntity, filterFinding, onFilterEntity, onFilterFinding }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tip = useTooltip();
  const [hover, setHover] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const atlas = useMemo(() => buildAtlas({ lexicon, asserted, problems }), [lexicon, asserted, problems]);
  const laid = useMemo(() => layoutAtlas(atlas), [atlas]);
  const nodeById = useMemo(() => new Map(laid.nodes.map((n) => [n.id, n])), [laid]);
  const maxSize = useMemo(() => Math.max(1, ...laid.nodes.filter((n) => n.kind === 'finding').map((n) => n.size)), [laid]);

  const focusId = hover ?? (filterFinding || null) ?? null;
  const focusSet = useMemo(() => {
    const ids = new Set<string>();
    if (filterFinding) { ids.add(filterFinding); for (const n of neighbours(atlas, filterFinding)) ids.add(n); for (const l of lexicon.linked?.[filterFinding] ?? []) ids.add(l); }
    if (filterEntity) { ids.add(filterEntity); for (const n of neighbours(atlas, filterEntity)) ids.add(n); }
    if (hover) { ids.add(hover); for (const n of neighbours(atlas, hover)) ids.add(n); }
    return ids;
  }, [atlas, filterFinding, filterEntity, hover, lexicon]);
  const dimming = focusSet.size > 0;

  const searchMatch = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return null;
    return laid.nodes.find((n) => n.kind === 'finding' && (n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q))) ?? null;
  }, [search, laid]);
  useEffect(() => {
    if (!searchMatch) return;
    const el = svgRef.current?.querySelector<SVGGElement>(`[data-id="${CSS.escape(searchMatch.id)}"]`);
    el?.focus();
  }, [searchMatch]);

  const labelled = useMemo(() => {
    // Label the largest satellites and anything in focus, skipping any label whose box would collide with one already placed.
    const priority = new Set([...focusSet, ...(searchMatch ? [searchMatch.id] : [])]);
    const cands = laid.nodes.filter((n) => n.kind === 'finding').sort((a, b) => Number(priority.has(b.id)) - Number(priority.has(a.id)) || b.size - a.size);
    const placed: Array<[number, number, number, number]> = laid.nodes.filter((n) => n.kind === 'entity').map((n) => [(n.x ?? 0) - 30, (n.y ?? 0) - 30, (n.x ?? 0) + 30, (n.y ?? 0) + 30]);
    const out = new Set<string>();
    for (const n of cands) {
      if (out.size >= 28 && !priority.has(n.id)) break;
      const r = satR(n);
      const box: [number, number, number, number] = [(n.x ?? 0) + r + 2, (n.y ?? 0) - 7, (n.x ?? 0) + r + 6 + n.label.length * 6.4, (n.y ?? 0) + 7];
      const hit = placed.some((b) => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]);
      if (hit && !priority.has(n.id)) continue;
      placed.push(box); out.add(n.id);
    }
    return out;
  }, [laid, focusSet, searchMatch]);

  const tipFor = (n: SimNode) => n.kind === 'entity' ? (
    <>
      <strong>{n.label}</strong>
      <div className="muted">{n.size} expected findings in the lexicon. Click to filter the dashboard to this category.</div>
    </>
  ) : (
    <>
      <strong>{n.label}</strong> <span className="muted">{n.findingKind}</span>
      <div>{n.size} assertions in view, {n.problems} contradicted or unsupported ({pct(n.heat, 0)})</div>
      <div className="muted">
        {atlas.edges.filter((e) => e.source === n.id).map((e) => `${entityShort(e.target)} ${e.expected === 'pos' ? 'positive' : 'negative'}`).join(', ') || 'no discriminator'}
      </div>
      <div className="muted">Click to filter traces that assert this finding.</div>
    </>
  );

  const onKey = (e: KeyboardEvent<SVGGElement>, n: SimNode) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(n); return; }
    if (!['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
    e.preventDefault();
    const nb = [...neighbours(atlas, n.id)].map((id) => nodeById.get(id)!).filter(Boolean)
      .sort((a, b) => Math.atan2((a.y ?? 0) - (n.y ?? 0), (a.x ?? 0) - (n.x ?? 0)) - Math.atan2((b.y ?? 0) - (n.y ?? 0), (b.x ?? 0) - (n.x ?? 0)));
    if (!nb.length) return;
    const cur = hover ? nb.findIndex((x) => x.id === hover) : -1;
    const i = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? (cur + 1) % nb.length : (cur <= 0 ? nb.length - 1 : cur - 1);
    const el = svgRef.current?.querySelector<SVGGElement>(`[data-id="${CSS.escape(nb[i].id)}"]`);
    el?.focus();
  };
  const activate = (n: SimNode) => { if (n.kind === 'entity') onFilterEntity(filterEntity === n.id ? '' : n.id); else onFilterFinding(filterFinding === n.id ? '' : n.id); };

  const table = {
    columns: ['Finding', 'Kind', 'Assertions', 'Problems', 'Problem share', 'Expected positive', 'Expected negative'],
    rows: atlas.nodes.filter((n) => n.kind === 'finding').sort((a, b) => b.size - a.size).map((n) => [
      n.label, n.findingKind ?? '', n.size, n.problems, n.heat,
      atlas.edges.filter((e) => e.source === n.id && e.expected === 'pos').map((e) => entityShort(e.target)).join(', '),
      atlas.edges.filter((e) => e.source === n.id && e.expected === 'neg').map((e) => entityShort(e.target)).join(', '),
    ]),
  };

  return (
    <ChartFrame id="lexicon-atlas" title="Lexicon atlas" svgRef={svgRef} table={table} tooltip={tip.node}
      exportData={{ id: 'lexicon-atlas', nodes: atlas.nodes, edges: atlas.edges }}
      legend={[
        { label: 'expected positive', color: 'var(--text-2)', shape: 'line' },
        { label: 'expected negative', color: 'var(--text-2)', shape: 'dashed' },
        { label: 'ring: none contradicted or unsupported', color: warm(0), shape: 'ring' },
        { label: 'ring: half', color: warm(0.5), shape: 'ring' },
        { label: 'ring: all contradicted or unsupported', color: warm(1), shape: 'ring' },
      ]}
      subtitle={<>The answer categories sit as hubs on a ring; each finding is a satellite drawn towards the categories it discriminates. Satellite size is how often the finding is asserted in the traces in view; its ring colour is the share of those assertions that were contradicted or unsupported. Click a hub or satellite to filter; hover to read; nothing is hidden, only dimmed.</>}
      aside={
        <div className="row" style={{ marginTop: 8 }}>
          <label className="field"><span>Find a finding</span>
            <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} list="atlas-findings" placeholder="CD23, cyclin D1, BRAF…" aria-describedby="atlas-search-help" />
          </label>
          <datalist id="atlas-findings">{atlas.nodes.filter((n) => n.kind === 'finding').map((n) => <option key={n.id} value={n.label} />)}</datalist>
          <span id="atlas-search-help" className="muted small">{searchMatch ? `Focused ${searchMatch.label}` : search ? 'No finding matches' : 'Typing focuses the first matching satellite'}</span>
          {(filterFinding || filterEntity) && <button type="button" className="btn small" onClick={() => { onFilterFinding(''); onFilterEntity(''); }}>Clear atlas selection</button>}
        </div>
      }>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Lexicon atlas knowledge graph">
        <g fill="none">
          {laid.links.map((l) => {
            const s = l.source as SimNode, t = l.target as SimNode;
            const lit = !dimming || (focusSet.has(s.id) && focusSet.has(t.id)) || focusId === s.id || focusId === t.id;
            return <line key={l.id} x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke={entityColor(lexicon, t.id)} strokeWidth={l.expected === 'pos' ? 1.3 : 1} strokeDasharray={l.expected === 'neg' ? '3 4' : undefined} strokeOpacity={lit ? (l.expected === 'pos' ? 0.6 : 0.38) : 0.06} />;
          })}
        </g>
        {laid.nodes.filter((n) => n.kind === 'finding').map((n) => {
          const r = satR(n);
          const lit = !dimming || focusSet.has(n.id);
          const show = labelled.has(n.id);
          return (
            <g key={n.id} data-id={n.id} className="mark" tabIndex={0} role="button" aria-label={`${n.label}: ${n.size} assertions, ${n.problems} contradicted or unsupported`} aria-pressed={filterFinding === n.id}
              transform={`translate(${n.x} ${n.y})`} opacity={lit ? 1 : 0.18}
              onMouseEnter={(e) => { setHover(n.id); tip.show(e, tipFor(n)); }} onMouseMove={tip.move} onMouseLeave={() => { setHover(null); tip.hide(); }}
              onFocus={(e) => { setHover(n.id); tip.show(e, tipFor(n)); }} onBlur={() => { setHover(null); tip.hide(); }}
              onClick={() => activate(n)} onKeyDown={(e) => onKey(e, n)}>
              <circle r={Math.max(12, r + 6)} fill="transparent" />
              <circle r={r} fill="var(--ink-3)" stroke={n.size ? warm(n.heat) : 'var(--line-strong)'} strokeWidth={n.size ? 2.5 : 1} />
              {filterFinding === n.id && <circle r={r + 4} fill="none" stroke="var(--focus)" strokeWidth={1.5} />}
              {show && <text x={r + 4} y={4} style={{ fontSize: n.size >= maxSize * 0.5 ? 12 : 11 }} className={lit ? '' : 'muted'}>{n.label}</text>}
            </g>
          );
        })}
        {laid.nodes.filter((n) => n.kind === 'entity').map((n) => {
          const lit = !dimming || focusSet.has(n.id);
          return (
            <g key={n.id} data-id={n.id} className="mark" tabIndex={0} role="button" aria-label={`${n.label}, ${n.size} expected findings`} aria-pressed={filterEntity === n.id}
              transform={`translate(${n.x} ${n.y})`} opacity={lit ? 1 : 0.3}
              onMouseEnter={(e) => { setHover(n.id); tip.show(e, tipFor(n)); }} onMouseMove={tip.move} onMouseLeave={() => { setHover(null); tip.hide(); }}
              onFocus={(e) => { setHover(n.id); tip.show(e, tipFor(n)); }} onBlur={() => { setHover(null); tip.hide(); }}
              onClick={() => activate(n)} onKeyDown={(e) => onKey(e, n)}>
              <circle r={26} fill={entityColor(lexicon, n.id)} stroke="var(--ink-2)" strokeWidth={3} />
              {filterEntity === n.id && <circle r={31} fill="none" stroke="var(--focus)" strokeWidth={2} />}
              <text textAnchor="middle" y={4} style={{ fontSize: hubFontSize(entityShort(n.id)), fontWeight: 700, fill: 'var(--ink)' }}>{entityShort(n.id)}</text>
            </g>
          );
        })}
      </svg>
      <div className="visually-hidden">
        <h4>Atlas nodes</h4>
        <ul>{laid.nodes.map((n) => <li key={n.id}>{n.kind === 'entity' ? `${n.label} hub` : `${n.label}: ${n.size} assertions, ${n.problems} problems`}</li>)}</ul>
      </div>
    </ChartFrame>
  );
}
