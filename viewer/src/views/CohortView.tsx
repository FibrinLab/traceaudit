import { useCallback, useMemo, useState } from 'react';
import { useStore } from '../store';
import type { Interval } from '../types';
import { applyFilters, EMPTY_FILTERS, filtersAreDefault, useAllCases, useTraceRows, type Filters, type Rule } from '../lib/cohort';
import { ENTITY_ORDER, entityShort, KIND_LABEL } from '../lib/palette';
import { entityDisplay, findingDisplay, intervalText, num, pct } from '../lib/format';
import { downloadJson } from '../lib/download';
import { OutcomeRiver, type RiverPin } from '../charts/OutcomeRiver';
import type { RiverLink, RiverNode } from '../charts/river';
import { EffortLadder } from '../charts/EffortLadder';
import { HeadlineRates } from '../charts/HeadlineRates';
import { LexiconAtlas } from '../charts/LexiconAtlas';
import { assertionCounts } from '../charts/atlas';
import { AuthorityChord } from '../charts/AuthorityChord';
import { Heatmap } from '../charts/Heatmap';
import { RuleSlope } from '../charts/RuleSlope';
import { BaseStability } from '../charts/BaseStability';
import { Banner } from '../components/Shared';

const KINDS = ['decisive', 'anchor_loss', 'neutral', 'authority_wrong', 'authority_right'] as const;

export function CohortView() {
  const { bundle } = useStore();
  const index = bundle!.index;
  const s = index.summary;
  const lexicon = index.lexicon;
  const { cases, loaded, total, error } = useAllCases();
  const allRows = useTraceRows(cases);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [pin, setPin] = useState<RiverPin | null>(null);
  const set = useCallback((patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch })), []);

  const rows = useMemo(() => applyFilters(allRows, filters), [allRows, filters]);
  const riverRows = useMemo(() => {
    if (!pin) return rows;
    return rows;
  }, [rows, pin]);

  const asserted = useMemo(() => assertionCounts(rows.map((r) => r.asserted)), [rows]);
  const problems = useMemo(() => {
    const m = new Map<string, number>();
    if (filtersAreDefault(filters) && s.grounding?.per_finding) {
      for (const p of s.grounding.per_finding) m.set(p.finding_id, p.contradicted + p.unsupported);
      return m;
    }
    for (const r of rows) { for (const f of r.contradicted_findings) m.set(f, (m.get(f) ?? 0) + 1); for (const f of r.unsupported_findings) m.set(f, (m.get(f) ?? 0) + 1); }
    return m;
  }, [rows, filters, s]);

  const onRiverPin = (p: RiverPin | null, link: RiverLink | null) => {
    setPin(p);
    if (!p || !link) return;
    const [sc, sk] = splitId(p.source), [tc, tk] = splitId(p.target);
    const patch: Partial<Filters> = {};
    if (sc === 1) patch.kind = sk; if (tc === 1) patch.kind = tk;
    if (sc === 0 && (ENTITY_ORDER as readonly string[]).includes(sk)) patch.entity = sk;
    setFilters((f) => ({ ...f, ...patch }));
  };
  const onRiverNode = (n: RiverNode) => {
    setPin(null);
    if (n.column === 1) set({ kind: filters.kind === n.key ? '' : n.key });
    else if ((n.column === 0 || n.column === 2) && (ENTITY_ORDER as readonly string[]).includes(n.key)) set({ entity: filters.entity === n.key ? '' : n.key });
  };

  const loading = loaded < total;
  const active = [
    filters.entity && `category ${entityShort(filters.entity)}`,
    filters.effort && `${filters.effort} effort`,
    filters.kind && KIND_LABEL[filters.kind],
    filters.finding && `finding ${findingDisplay(lexicon, filters.finding)}`,
  ].filter(Boolean) as string[];

  return (
    <div>
      <div className="row between" style={{ alignItems: 'flex-end', marginBottom: 12 }}>
        <div>
          <h1>Cohort</h1>
          <p className="lede">{s.counts.traces} traces over {s.counts.cases} cases, scored under rule {s.scoring.rule} with the {s.scoring.verifier} verifier and {s.scoring.B} bootstrap resamples. Precomputed rates come from the run summary; every panel below follows the one filter row.</p>
        </div>
        <button type="button" className="btn" onClick={() => downloadJson(`summary-${s.run_id}.json`, s)}>Export summary JSON</button>
      </div>

      <div className="filters" role="group" aria-label="Dashboard filters">
        <label className="field"><span>Category</span>
          <select value={filters.entity} onChange={(e) => set({ entity: e.target.value })}>
            <option value="">All categories</option>
            {ENTITY_ORDER.map((e) => <option key={e} value={e}>{entityDisplay(lexicon, e)}</option>)}
          </select>
        </label>
        <label className="field"><span>Effort</span>
          <select value={filters.effort} onChange={(e) => set({ effort: e.target.value })}>
            <option value="">All efforts</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
          </select>
        </label>
        <label className="field"><span>Edit kind</span>
          <select value={filters.kind} onChange={(e) => set({ kind: e.target.value })}>
            <option value="">All kinds</option>
            {KINDS.map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        </label>
        <div className="field" role="group" aria-label="Disclosure rule">
          <span className="small muted">Disclosure rule</span>
          <div className="seg">{(['D1', 'D2', 'D3'] as Rule[]).map((r) => <button key={r} type="button" aria-pressed={filters.rule === r} onClick={() => set({ rule: r })}>{r}</button>)}</div>
        </div>
        {filters.finding && <button type="button" className="chip filter" aria-pressed="true" onClick={() => set({ finding: '' })} title="Remove the finding filter">finding: {findingDisplay(lexicon, filters.finding)} ×</button>}
        <span className="spacer" />
        <span className="muted small" aria-live="polite">{loading ? `Loading cases ${loaded} of ${total}` : `${rows.length} of ${allRows.length} traces in view${active.length ? `, filtered by ${active.join(', ')}` : ''}`}</span>
        {(!filtersAreDefault(filters) || pin) && <button type="button" className="btn small" onClick={() => { setFilters({ ...EMPTY_FILTERS, rule: filters.rule }); setPin(null); }}>Reset filters</button>}
      </div>
      {loading && <div className="loading-strip" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={loaded} aria-label="Loading case files"><div style={{ width: `${total ? (loaded / total) * 100 : 0}%` }} /></div>}
      {error && <Banner tone="bad">{error}</Banner>}

      <div className="grid" style={{ marginTop: 16, opacity: loading ? 0.6 : 1, transition: 'opacity 200ms' }}>
        <div className="span-12"><OutcomeRiver rows={riverRows} lexicon={lexicon} pin={pin} onPin={onRiverPin} onNode={onRiverNode} /></div>
        <div className="span-6"><EffortLadder rows={allRows} summary={s} filters={filters} lexicon={lexicon} /></div>
        <div className="span-6">
          <HeadlineRates rows={allRows} summary={s} filters={filters} />
          {s.effort_contrasts && (
            <div className="panel tight" style={{ marginTop: 16 }}>
              <div className="panel-head"><h3 style={{ fontSize: 'var(--fs-1)', fontFamily: 'var(--font-ui)', fontWeight: 500 }}>Effort contrasts, high minus low</h3></div>
              <div className="row small">
                {Object.entries(s.effort_contrasts).map(([k, iv]) => <span key={k} className="chip neutral">{k.replace(/_high_minus_low/, '').replace(/_/g, ' ')} {signed(iv)}</span>)}
              </div>
            </div>
          )}
        </div>
        <div className="span-12">
          <LexiconAtlas lexicon={lexicon} asserted={asserted} problems={problems} filterEntity={filters.entity} filterFinding={filters.finding}
            onFilterEntity={(e) => set({ entity: e })} onFilterFinding={(f) => set({ finding: f })} />
        </div>
        <div className="span-6"><AuthorityChord rows={applyFilters(allRows, { ...filters, kind: filters.kind === 'authority_wrong' || !filters.kind ? '' : filters.kind })} lexicon={lexicon} onFilterEntity={(e) => set({ entity: filters.entity === e ? '' : e })} /></div>
        <div className="span-6"><Heatmap rows={rows} lexicon={lexicon} filterFinding={filters.finding} onFilterFinding={(f) => set({ finding: f })} onFilterEntity={(e) => set({ entity: e })} /></div>
        <div className="span-4"><RuleSlope rows={allRows} summary={s} filters={filters} onRule={(r) => set({ rule: r })} /></div>
        <div className="span-4"><BaseStability cases={cases} summary={s} lexicon={lexicon} filterEntity={filters.entity} /></div>
        <div className="span-4">{index.ratings ? <AgreementPanel /> : (
          <div className="chart">
            <div className="chart-head"><h2>Agreement</h2></div>
            <p className="chart-sub">No ratings are attached to this bundle. Run <code>traceaudit agreement</code> and re-export to see κ and AC2 per dimension here.</p>
            {s.judge && (
              <>
                <p className="small muted">Judge model over {s.judge.n} traces, mean score per dimension:</p>
                <div className="row small">{Object.entries(s.judge.mean_by_dimension).map(([d, v]) => <span key={d} className="chip neutral">{d} {num(v)}</span>)}</div>
                <div className="row small" style={{ marginTop: 6 }}>{Object.entries(s.judge.tag_counts).map(([t, c]) => <span key={t} className="chip neutral">{t.replace(/_/g, ' ')} {c}</span>)}</div>
              </>
            )}
          </div>
        )}</div>
      </div>
    </div>
  );
}

function splitId(id: string): [number, string] { const i = id.indexOf(':'); return [Number(id.slice(0, i)), id.slice(i + 1)]; }

function signed(iv: Interval): string {
  if (iv.point === null) return '—';
  const sgn = iv.point > 0 ? '+' : '';
  return `${sgn}${pct(iv.point, 1)}${iv.lo !== null && iv.hi !== null ? ` (${pct(iv.lo, 0)} to ${pct(iv.hi, 0)})` : ''}`;
}

function AgreementPanel() {
  const { bundle } = useStore();
  const r = bundle!.index.ratings!;
  const dims = Object.entries(r.dimensions ?? {});
  return (
    <div className="chart">
      <div className="chart-head"><h2>Agreement</h2></div>
      <p className="chart-sub">Raters {r.raters.join(', ')}. Gwet AC2 with linear weights per dimension; intervals bootstrap over traces.</p>
      <svg viewBox={`0 0 320 ${24 + dims.length * 26}`} role="img" aria-label={`AC2 per dimension: ${dims.map(([d, v]) => `${d} ${num(v.gwet_ac2?.point ?? null)}`).join(', ')}`} style={{ width: '100%', height: 'auto' }}>
        {[0, 0.5, 1].map((t) => <g key={t}><line x1={40 + t * 260} x2={40 + t * 260} y1={6} y2={dims.length * 26 + 6} className="grid-line" /><text x={40 + t * 260} y={dims.length * 26 + 20} textAnchor="middle" className="muted" style={{ fontSize: 10.5 }}>{t}</text></g>)}
        {dims.map(([d, v], i) => {
          const iv = v.gwet_ac2;
          const x = (p: number) => 40 + Math.max(0, Math.min(1, p)) * 260;
          return (
            <g key={d} transform={`translate(0 ${12 + i * 26})`}>
              <text x={0} y={4} style={{ fontSize: 12 }}>{d}</text>
              {iv && iv.lo !== null && iv.hi !== null && <line x1={x(iv.lo)} x2={x(iv.hi)} y1={0} y2={0} stroke="var(--text-2)" strokeWidth={2} />}
              {iv && iv.point !== null && <circle cx={x(iv.point)} cy={0} r={5} fill="var(--text)" stroke="var(--ink-2)" strokeWidth={2}><title>{intervalText(iv, false)}</title></circle>}
            </g>
          );
        })}
      </svg>
      <details className="showdata"><summary>Show data</summary>
        <table className="data small">
          <thead><tr><th>Dimension</th><th className="num">n</th><th>Pairwise κ</th><th>Judge κ</th></tr></thead>
          <tbody>{dims.map(([d, v]) => <tr key={d}><td>{d}</td><td className="num">{v.n_traces}</td><td>{Object.entries(v.pairwise_kappa ?? {}).map(([p, pa]) => `${p.replace('|', ' vs ')} ${intervalText(pa.linear, false)}`).join('; ')}</td><td>{typeof v.judge_kappa?.consensus === 'object' && v.judge_kappa.consensus ? intervalText(v.judge_kappa.consensus as Interval, false) : '—'}</td></tr>)}</tbody>
        </table>
      </details>
    </div>
  );
}
