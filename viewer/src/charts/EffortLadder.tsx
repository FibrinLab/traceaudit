import { useMemo, useRef } from 'react';
import type { Interval, Lexicon, Summary } from '../types';
import { applyFilters, filtersAreDefault, METRIC_META, ratesFromRows, ratesFromSummary, type Filters, type Rates, type TraceRow } from '../lib/cohort';
import { entityColor, entityOrder, entityShort } from '../lib/palette';
import { intervalText, pct } from '../lib/format';
import { ChartFrame } from './ChartFrame';
import { useTooltip } from './Tooltip';

const EFFORTS = ['low', 'medium', 'high'] as const;
/** Ordinal: two greys stepping up to the accent, so high effort is the one coloured step. */
export const EFFORT_COLOR: Record<(typeof EFFORTS)[number], string> = { low: 'var(--ord-1)', medium: 'var(--ord-2)', high: 'var(--ord-3)' };

/** Per-effort rates for every headline metric: summary facets when the view is unfiltered, Wilson from rows otherwise. */
export function ratesByEffort(rows: TraceRow[], summary: Summary, filters: Filters): { source: 'summary' | 'rows'; byEffort: Record<string, Rates> } {
  const base = { ...filters, effort: '' };
  const fromSummary = filtersAreDefault(base) || (!base.kind && !base.finding && !base.entity);
  const byEffort: Record<string, Rates> = {};
  if (fromSummary) {
    let ok = true;
    for (const e of EFFORTS) {
      const r = ratesFromSummary(summary, { ...base, effort: e });
      if (!r) { ok = false; break; }
      byEffort[e] = r;
    }
    if (ok) return { source: 'summary', byEffort };
  }
  for (const e of EFFORTS) byEffort[e] = ratesFromRows(applyFilters(rows, { ...base, effort: e }), filters.rule);
  return { source: 'rows', byEffort };
}

export function EffortLadder({ rows, summary, filters, lexicon }: { rows: TraceRow[]; summary: Summary; filters: Filters; lexicon: Lexicon }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tip = useTooltip();
  const { source, byEffort } = useMemo(() => ratesByEffort(rows, summary, filters), [rows, summary, filters]);
  const perEntity = useMemo(() => {
    const out: Record<string, Record<string, Rates>> = {};
    for (const ent of entityOrder(lexicon)) {
      const base = applyFilters(rows, { ...filters, entity: ent, effort: '' });
      if (!base.length) continue;
      out[ent] = {} as Record<string, Rates>;
      for (const e of EFFORTS) out[ent][e] = ratesFromRows(base.filter((r) => r.effort === e), filters.rule);
    }
    return out;
  }, [rows, filters, lexicon]);

  const W = 540, rowH = 46, labelW = 110, M = { top: 22, right: 20, bottom: 22 };
  const plotW = W - labelW - M.right;
  const H = M.top + METRIC_META.length * rowH + M.bottom;
  const x = (v: number) => labelW + v * plotW;
  const yRow = (i: number) => M.top + i * rowH + rowH / 2;
  const dy = { low: -9, medium: 0, high: 9 };

  const tipFor = (label: string, effort: string, iv: Interval) => (
    <>
      <strong>{pct(iv.point, 0)}</strong> <span className="muted">{label}, {effort} effort</span>
      <div className="muted">{intervalText(iv)}{iv.numerator != null ? `, ${iv.numerator}/${iv.denominator}` : iv.n_records ? `, n ${iv.n_records}` : ''} {iv.ci_method === 'wilson' ? 'Wilson' : 'bootstrap'}</div>
    </>
  );

  const table = {
    columns: ['Metric', 'Effort', 'Rate', 'Low', 'High', 'n'],
    rows: METRIC_META.flatMap((m) => EFFORTS.map((e) => { const iv = byEffort[e][m.id]; return [m.label, e, iv.point, iv.lo, iv.hi, iv.denominator ?? iv.n_records ?? null]; })),
  };

  return (
    <ChartFrame id="effort-ladder" title="Effort ladder" svgRef={svgRef} table={table} tooltip={tip.node}
      legend={EFFORTS.map((e) => ({ label: `${e} effort`, color: EFFORT_COLOR[e] }))}
      exportData={{ id: 'effort-ladder', source, rule: filters.rule, by_effort: byEffort, by_entity: perEntity }}
      subtitle={<>Each metric as three dots for low, medium and high effort with 95% intervals; a hairline joins them so a slope reads as an effort effect. {source === 'summary' ? 'Intervals from the precomputed summary (case-clustered bootstrap).' : 'Recomputed from the filtered traces with Wilson intervals.'}</>}
      aside={Object.keys(perEntity).length > 1 && (
        <div style={{ marginTop: 12 }}>
          <div className="muted small" style={{ marginBottom: 6 }}>By case category (Wilson, small n)</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
            {Object.entries(perEntity).map(([ent, by]) => (
              <svg key={ent} viewBox="0 0 150 104" role="img" aria-label={`${entityShort(ent)}: ${METRIC_META.map((m) => `${m.label} ${EFFORTS.map((e) => pct(by[e][m.id].point, 0)).join(', ')}`).join('; ')}`} style={{ width: '100%', height: 'auto' }}>
                <text x={0} y={11} style={{ fontSize: 11.5 }}><tspan fill={entityColor(lexicon, ent)}>●</tspan> {entityShort(ent)}</text>
                {METRIC_META.map((m, i) => {
                  const y = 24 + i * 16;
                  const pts = EFFORTS.map((e) => by[e][m.id].point).filter((p): p is number => p !== null);
                  return (
                    <g key={m.id}>
                      <text x={0} y={y + 4} className="muted" style={{ fontSize: 9.5 }}>{m.label}</text>
                      <line x1={62} x2={148} y1={y} y2={y} className="grid-line" />
                      {pts.length > 1 && <line x1={62 + Math.min(...pts) * 86} x2={62 + Math.max(...pts) * 86} y1={y} y2={y} stroke="var(--text-2)" strokeWidth={1} />}
                      {EFFORTS.map((e) => { const p = by[e][m.id].point; return p === null ? null : <circle key={e} cx={62 + p * 86} cy={y} r={3} fill={EFFORT_COLOR[e]} stroke="var(--ink-2)" strokeWidth={1.5} />; })}
                    </g>
                  );
                })}
              </svg>
            ))}
          </div>
        </div>
      )}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Effort ladder">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={M.top - 6} y2={H - M.bottom} className="grid-line" />
            <text x={x(t)} y={H - 6} textAnchor="middle" className="muted" style={{ fontSize: 11 }}>{Math.round(t * 100)}%</text>
          </g>
        ))}
        {METRIC_META.map((m, i) => {
          const y = yRow(i);
          const ivs = EFFORTS.map((e) => [e, byEffort[e][m.id]] as const).filter(([, iv]) => iv.point !== null);
          const pts = ivs.map(([, iv]) => iv.point as number);
          return (
            <g key={m.id}>
              <text x={0} y={y + 4} style={{ fontSize: 12.5 }}>{m.label}</text>
              {pts.length > 1 && <line x1={x(Math.min(...pts))} x2={x(Math.max(...pts))} y1={y} y2={y} stroke="var(--line-strong)" strokeWidth={1} />}
              {ivs.map(([e, iv]) => (
                <g key={e} className="mark" tabIndex={0} role="img" aria-label={`${m.label}, ${e} effort: ${intervalText(iv)}`}
                  onMouseEnter={(ev) => tip.show(ev, tipFor(m.label, e, iv))} onMouseMove={tip.move} onMouseLeave={tip.hide}
                  onFocus={(ev) => tip.show(ev, tipFor(m.label, e, iv))} onBlur={tip.hide}>
                  {iv.lo !== null && iv.hi !== null && <line x1={x(iv.lo)} x2={x(iv.hi)} y1={y + dy[e]} y2={y + dy[e]} stroke={EFFORT_COLOR[e]} strokeWidth={2} strokeLinecap="round" opacity={0.7} />}
                  <circle cx={x(iv.point as number)} cy={y + dy[e]} r={5} fill={EFFORT_COLOR[e]} stroke="var(--ink-2)" strokeWidth={2} />
                  <circle cx={x(iv.point as number)} cy={y + dy[e]} r={12} fill="transparent" />
                </g>
              ))}
              {!ivs.length && <text x={x(0)} y={y + 4} className="muted" style={{ fontSize: 11 }}>no traces</text>}
            </g>
          );
        })}
      </svg>
    </ChartFrame>
  );
}
