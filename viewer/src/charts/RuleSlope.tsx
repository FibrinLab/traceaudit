import { useMemo, useRef } from 'react';
import type { Interval, Summary } from '../types';
import { applyFilters, filtersAreDefault, silentUnderRule, type Filters, type Rule, type TraceRow } from '../lib/cohort';
import { wilson } from '../lib/stats';
import { intervalText, pct } from '../lib/format';
import { EFFORT_COLOR } from './EffortLadder';
import { ChartFrame } from './ChartFrame';
import { useTooltip } from './Tooltip';

const RULES: Rule[] = ['D1', 'D2', 'D3'];
const RULE_TEXT: Record<Rule, string> = { D1: 'D1 cited the primary finding as evidence', D2: 'D2 mentioned the primary finding anywhere', D3: 'D3 mentioned any edited finding' };
const SERIES = ['all', 'low', 'medium', 'high'] as const;

export function RuleSlope({ rows, summary, filters, onRule }: { rows: TraceRow[]; summary: Summary; filters: Filters; onRule: (r: Rule) => void }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tip = useTooltip();
  const { series, source } = useMemo(() => {
    const rs = summary.counterfactual?.decisive?.rule_sensitivity;
    const base = { ...filters, effort: '' };
    if (rs && filtersAreDefault(base)) {
      const series: Record<string, Record<Rule, Interval | null>> = {};
      for (const s of SERIES) series[s] = Object.fromEntries(RULES.map((r) => [r, s === 'all' ? rs[r] ?? null : rs[r]?.by_effort?.[s] ?? null])) as Record<Rule, Interval | null>;
      return { series, source: 'summary' as const };
    }
    const sub = applyFilters(rows, base);
    const series: Record<string, Record<Rule, Interval | null>> = {};
    for (const s of SERIES) {
      const pool = s === 'all' ? sub : sub.filter((r) => r.effort === s);
      series[s] = Object.fromEntries(RULES.map((r) => { const v = pool.map((x) => silentUnderRule(x, r)).filter((x): x is boolean => x !== null); return [r, v.length ? wilson(v.filter(Boolean).length, v.length) : null]; })) as Record<Rule, Interval | null>;
    }
    return { series, source: 'rows' as const };
  }, [rows, summary, filters]);

  const W = 360, H = 250, M = { top: 18, right: 54, bottom: 30, left: 40 };
  const x = (i: number) => M.left + (i / 2) * (W - M.left - M.right);
  const y = (v: number) => M.top + (1 - v) * (H - M.top - M.bottom);
  const color = (s: string) => (s === 'all' ? 'var(--text)' : EFFORT_COLOR[s as 'low' | 'medium' | 'high']);

  const table = { columns: ['Series', 'Rule', 'Silent rate', 'Low', 'High', 'n'], rows: SERIES.flatMap((s) => RULES.map((r) => { const iv = series[s][r]; return [s, r, iv?.point ?? null, iv?.lo ?? null, iv?.hi ?? null, iv?.denominator ?? iv?.n_records ?? null]; })) };

  return (
    <ChartFrame id="rule-sensitivity" title="Rule sensitivity" svgRef={svgRef} table={table} tooltip={tip.node} headingLevel={2}
      legend={[{ label: 'all efforts', color: 'var(--text)', shape: 'line' }, ...(['low', 'medium', 'high'] as const).map((e) => ({ label: e, color: EFFORT_COLOR[e], shape: 'line' as const }))]}
      exportData={{ id: 'rule-sensitivity', source, series }}
      subtitle={<>Silent rate under the three disclosure rules. {RULE_TEXT.D1}; {RULE_TEXT.D2.replace('D2 ', 'D2, ')}; {RULE_TEXT.D3.replace('D3 ', 'D3, ')}. Click a rule to make it the dashboard's rule.</>}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Rule sensitivity slope chart">
        {[0, 0.5, 1].map((t) => <g key={t}><line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} className="grid-line" /><text x={M.left - 6} y={y(t) + 4} textAnchor="end" className="muted" style={{ fontSize: 11 }}>{Math.round(t * 100)}%</text></g>)}
        {RULES.map((r, i) => (
          <g key={r} className="mark" tabIndex={0} role="button" aria-pressed={filters.rule === r} aria-label={RULE_TEXT[r]}
            onClick={() => onRule(r)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRule(r); } }}>
            <line x1={x(i)} x2={x(i)} y1={M.top} y2={H - M.bottom} stroke={filters.rule === r ? 'var(--focus)' : 'var(--line)'} strokeWidth={filters.rule === r ? 1.5 : 1} />
            <text x={x(i)} y={H - 10} textAnchor="middle" style={{ fontSize: 12.5, fontWeight: filters.rule === r ? 600 : 400 }}>{r}</text>
          </g>
        ))}
        {SERIES.map((s) => {
          const pts = RULES.map((r, i) => ({ r, i, iv: series[s][r] })).filter((p) => p.iv && p.iv.point !== null) as Array<{ r: Rule; i: number; iv: Interval }>;
          if (!pts.length) return null;
          return (
            <g key={s}>
              <polyline points={pts.map((p) => `${x(p.i)},${y(p.iv.point as number)}`).join(' ')} fill="none" stroke={color(s)} strokeWidth={s === 'all' ? 2.2 : 1.6} strokeLinecap="round" strokeLinejoin="round" opacity={s === 'all' ? 1 : 0.85} />
              {pts.map((p) => (
                <g key={p.r} className="mark" tabIndex={0} role="img" aria-label={`${s} ${p.r}: ${intervalText(p.iv)}`}
                  onMouseEnter={(e) => tip.show(e, <><strong>{pct(p.iv.point, 0)}</strong> <span className="muted">{s === 'all' ? 'all efforts' : `${s} effort`}, {p.r}</span><div className="muted">{intervalText(p.iv)}{p.iv.numerator != null ? `, ${p.iv.numerator}/${p.iv.denominator}` : ''}</div></>)} onMouseMove={tip.move} onMouseLeave={tip.hide}
                  onFocus={(e) => tip.show(e, <><strong>{pct(p.iv.point, 0)}</strong> {s} {p.r}<div className="muted">{intervalText(p.iv)}</div></>)} onBlur={tip.hide}>
                  {s === 'all' && p.iv.lo !== null && p.iv.hi !== null && <line x1={x(p.i)} x2={x(p.i)} y1={y(p.iv.lo)} y2={y(p.iv.hi)} stroke={color(s)} strokeWidth={2} opacity={0.5} strokeLinecap="round" />}
                  <circle cx={x(p.i)} cy={y(p.iv.point as number)} r={s === 'all' ? 5 : 4} fill={color(s)} stroke="var(--ink-2)" strokeWidth={2} />
                  <circle cx={x(p.i)} cy={y(p.iv.point as number)} r={12} fill="transparent" />
                </g>
              ))}
              {s === 'all' && <text x={x(2) + 10} y={y(pts[pts.length - 1].iv.point as number) + 4} style={{ fontSize: 11.5 }}>{pct(pts[pts.length - 1].iv.point, 0)}</text>}
            </g>
          );
        })}
      </svg>
    </ChartFrame>
  );
}
