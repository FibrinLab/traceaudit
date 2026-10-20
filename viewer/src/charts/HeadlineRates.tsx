import { useMemo } from 'react';
import type { Summary } from '../types';
import { applyFilters, METRIC_META, ratesFromRows, ratesFromSummary, type Filters, type TraceRow } from '../lib/cohort';
import { ratesByEffort, EFFORT_COLOR } from './EffortLadder';
import { pct } from '../lib/format';
import { ChartFrame } from './ChartFrame';

export function HeadlineRates({ rows, summary, filters }: { rows: TraceRow[]; summary: Summary; filters: Filters }) {
  const rates = useMemo(() => ratesFromSummary(summary, filters) ?? ratesFromRows(applyFilters(rows, filters), filters.rule), [rows, summary, filters]);
  const fromSummary = useMemo(() => !!ratesFromSummary(summary, filters), [summary, filters]);
  const { byEffort } = useMemo(() => ratesByEffort(rows, summary, filters), [rows, summary, filters]);
  const table = {
    columns: ['Metric', 'Rate', 'Low', 'High', 'n', 'Interval'],
    rows: METRIC_META.map((m) => { const iv = rates[m.id]; return [m.label, iv.point, iv.lo, iv.hi, iv.denominator ?? iv.n_records ?? null, iv.ci_method ?? 'bootstrap']; }),
  };
  return (
    <ChartFrame id="headline-rates" title="Headline rates" table={table} exportData={{ id: 'headline-rates', rule: filters.rule, rates }}
      subtitle={<>Silent rate under rule {filters.rule}. {fromSummary ? 'Precomputed intervals.' : 'Recomputed from the filtered traces (Wilson).'} The small line under each number is the low, medium and high effort value.</>}>
      <div className="tiles" role="list">
        {METRIC_META.map((m) => {
          const iv = rates[m.id];
          const pts = (['low', 'medium', 'high'] as const).map((e) => byEffort[e]?.[m.id]?.point ?? null);
          const n = iv.denominator ?? iv.n_records ?? null;
          return (
            <div key={m.id} className="tile" role="listitem" aria-label={`${m.label}: ${pct(iv.point, 1)}${iv.lo !== null ? `, 95% CI ${pct(iv.lo, 1)} to ${pct(iv.hi, 1)}` : ''}${n !== null ? `, n ${n}` : ''}`} title={m.detail}>
              <span className="label">{m.label}</span>
              <span className="value">{pct(iv.point, 1)}</span>
              <span className="ci">{iv.lo !== null && iv.hi !== null ? `95% CI ${pct(iv.lo, 0)} to ${pct(iv.hi, 0)}` : 'no interval'}{n !== null ? `, n ${n}` : ''}</span>
              <svg viewBox="0 0 72 14" aria-hidden="true">
                <line x1={2} x2={70} y1={12} y2={12} className="grid-line" />
                {pts.every((p) => p !== null) && <polyline points={pts.map((p, i) => `${6 + i * 30},${12 - (p as number) * 10}`).join(' ')} fill="none" stroke="var(--text-2)" strokeWidth={1.2} />}
                {pts.map((p, i) => p === null ? null : <circle key={i} cx={6 + i * 30} cy={12 - p * 10} r={2.4} fill={EFFORT_COLOR[(['low', 'medium', 'high'] as const)[i]]} />)}
              </svg>
            </div>
          );
        })}
        {summary.knowledge && (
          <div className="tile" role="listitem" aria-label={`Knowledge consistency ${pct(summary.knowledge.consistency_rate.point, 1)}, n ${summary.knowledge.n_checked}`}>
            <span className="label">Knowledge consistency</span>
            <span className="value">{pct(summary.knowledge.consistency_rate.point, 1)}</span>
            <span className="ci">95% CI {pct(summary.knowledge.consistency_rate.lo, 0)} to {pct(summary.knowledge.consistency_rate.hi, 0)}, n {summary.knowledge.n_checked}</span>
          </div>
        )}
      </div>
    </ChartFrame>
  );
}
