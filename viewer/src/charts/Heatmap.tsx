import { useMemo, useRef, useState } from 'react';
import type { Lexicon } from '../types';
import type { TraceRow } from '../lib/cohort';
import { ENTITY_ORDER, entityColor, entityShort, heat } from '../lib/palette';
import { findingDisplay } from '../lib/format';
import { ChartFrame } from './ChartFrame';
import { useTooltip } from './Tooltip';

/** Finding × case entity: how many claims about the finding were contradicted or unsupported in traces of that entity. */
export function buildHeat(rows: TraceRow[]): { findings: string[]; entities: string[]; cell: Map<string, { contradicted: number; unsupported: number }> } {
  const cell = new Map<string, { contradicted: number; unsupported: number }>();
  const fs = new Set<string>(), es = new Set<string>();
  const bump = (f: string, e: string, k: 'contradicted' | 'unsupported') => {
    const key = `${f}|${e}`;
    const c = cell.get(key) ?? { contradicted: 0, unsupported: 0 };
    c[k]++; cell.set(key, c); fs.add(f); es.add(e);
  };
  for (const r of rows) {
    for (const f of r.contradicted_findings) bump(f, r.entity, 'contradicted');
    for (const f of r.unsupported_findings) bump(f, r.entity, 'unsupported');
  }
  const entities = [...ENTITY_ORDER.filter((e) => es.has(e)), ...[...es].filter((e) => !(ENTITY_ORDER as readonly string[]).includes(e)).sort()];
  return { findings: [...fs], entities, cell };
}

export function Heatmap({ rows, lexicon, onFilterFinding, onFilterEntity, filterFinding }: { rows: TraceRow[]; lexicon: Lexicon; onFilterFinding: (f: string) => void; onFilterEntity: (e: string) => void; filterFinding: string }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tip = useTooltip();
  const [sortBy, setSortBy] = useState<string>('total');
  const [limit, setLimit] = useState(24);
  const data = useMemo(() => buildHeat(rows), [rows]);
  const totals = useMemo(() => {
    const t = new Map<string, number>();
    for (const f of data.findings) t.set(f, data.entities.reduce((a, e) => { const c = data.cell.get(`${f}|${e}`); return a + (c ? c.contradicted + c.unsupported : 0); }, 0));
    return t;
  }, [data]);
  const value = (f: string, e: string) => { const c = data.cell.get(`${f}|${e}`); return c ? c.contradicted + c.unsupported : 0; };
  const sorted = useMemo(() => {
    const fs = data.findings.slice();
    fs.sort((a, b) => (sortBy === 'total' ? (totals.get(b) ?? 0) - (totals.get(a) ?? 0) : value(b, sortBy) - value(a, sortBy)) || a.localeCompare(b));
    return fs;
  }, [data, sortBy, totals]);
  const shown = sorted.slice(0, limit);
  const max = Math.max(1, ...data.findings.flatMap((f) => data.entities.map((e) => value(f, e))));

  const cellW = 44, cellH = 22, labelW = 150, top = 54;
  const W = labelW + data.entities.length * cellW + 56, H = top + shown.length * cellH + 8;
  const stepIndex = (v: number) => (v === 0 ? 0 : Math.max(1, Math.round((v / max) * 6)));

  const tipFor = (f: string, e: string) => {
    const c = data.cell.get(`${f}|${e}`);
    return (
      <>
        <strong>{c ? c.contradicted + c.unsupported : 0}</strong> <span className="muted">{findingDisplay(lexicon, f)} in {entityShort(e)} traces</span>
        <div className="muted">{c?.contradicted ?? 0} contradicted, {c?.unsupported ?? 0} unsupported</div>
      </>
    );
  };

  const table = { columns: ['Finding', ...data.entities.map(entityShort), 'Total'], rows: sorted.map((f) => [findingDisplay(lexicon, f), ...data.entities.map((e) => value(f, e)), totals.get(f) ?? 0]) };

  return (
    <ChartFrame id="hallucination-heatmap" title="Hallucination heatmap" svgRef={svgRef} table={table} tooltip={tip.node}
      exportData={{ id: 'hallucination-heatmap', entities: data.entities, rows: sorted.map((f) => ({ finding: f, by_entity: Object.fromEntries(data.entities.map((e) => [e, data.cell.get(`${f}|${e}`) ?? { contradicted: 0, unsupported: 0 }])) })) }}
      subtitle={<>Finding by case category; each cell counts claims about that finding that were contradicted by, or absent from, the documents. One hue, darker is more. Click a column heading to sort by that entity, a row label to filter the dashboard to that finding.</>}
      aside={data.findings.length > limit && <button type="button" className="btn small quiet" onClick={() => setLimit(data.findings.length)}>Show all {data.findings.length} findings</button>}>
      {!data.findings.length ? <p className="muted">No contradicted or unsupported findings in view.</p> : (
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Hallucination heatmap">
          {data.entities.map((e, j) => (
            <g key={e} className="mark" tabIndex={0} role="button" aria-sort={sortBy === e ? 'descending' : 'none'} aria-label={`Sort by category ${entityShort(e)}`}
              onClick={() => setSortBy(sortBy === e ? 'total' : e)} onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); setSortBy(sortBy === e ? 'total' : e); } }}
              onDoubleClick={() => onFilterEntity(e)}>
              <rect x={labelW + j * cellW} y={top - 30} width={cellW - 2} height={24} fill="transparent" />
              <circle cx={labelW + j * cellW + cellW / 2} cy={top - 24} r={4} fill={entityColor(lexicon, e)} />
              <text x={labelW + j * cellW + cellW / 2} y={top - 8} textAnchor="middle" style={{ fontSize: 11.5, fontWeight: sortBy === e ? 600 : 400 }}>{entityShort(e)}</text>
            </g>
          ))}
          <text x={labelW + data.entities.length * cellW + 8} y={top - 8} className="muted" style={{ fontSize: 11 }}>total</text>
          {shown.map((f, i) => (
            <g key={f} transform={`translate(0 ${top + i * cellH})`}>
              <g className="mark" tabIndex={0} role="button" aria-label={`Filter to ${findingDisplay(lexicon, f)}`} aria-pressed={filterFinding === f}
                onClick={() => onFilterFinding(filterFinding === f ? '' : f)} onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onFilterFinding(filterFinding === f ? '' : f); } }}>
                <rect x={0} y={0} width={labelW - 6} height={cellH} fill="transparent" />
                <text x={labelW - 10} y={cellH / 2 + 4} textAnchor="end" style={{ fontSize: 11.5, fontWeight: filterFinding === f ? 600 : 400 }}>{truncate(findingDisplay(lexicon, f), 22)}</text>
              </g>
              {data.entities.map((e, j) => {
                const v = value(f, e);
                const step = stepIndex(v);
                return (
                  <g key={e} className="mark" tabIndex={0} role="img" aria-label={`${findingDisplay(lexicon, f)}, ${entityShort(e)}: ${v}`}
                    onMouseEnter={(ev) => tip.show(ev, tipFor(f, e))} onMouseMove={tip.move} onMouseLeave={tip.hide} onFocus={(ev) => tip.show(ev, tipFor(f, e))} onBlur={tip.hide}>
                    <rect x={labelW + j * cellW} y={1} width={cellW - 2} height={cellH - 2} rx={2} fill={heat(step / 6)} />
                    {v > 0 && <text x={labelW + j * cellW + cellW / 2} y={cellH / 2 + 4} textAnchor="middle" style={{ fontSize: 11, fill: step >= 4 ? 'var(--ink)' : 'var(--text)' }} className="num">{v}</text>}
                  </g>
                );
              })}
              <text x={labelW + data.entities.length * cellW + 8} y={cellH / 2 + 4} className="muted num" style={{ fontSize: 11 }}>{totals.get(f)}</text>
            </g>
          ))}
        </svg>
      )}
    </ChartFrame>
  );
}

function truncate(s: string, n: number): string { return s.length > n ? s.slice(0, n - 1) + '…' : s; }
