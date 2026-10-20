import { useMemo, useRef } from 'react';
import type { CaseFile, Lexicon, Summary } from '../types';
import { entityColor, entityShort } from '../lib/palette';
import { pct } from '../lib/format';
import { hrefCase } from '../lib/router';
import { ChartFrame } from './ChartFrame';
import { useTooltip } from './Tooltip';

const EFFORTS = ['low', 'medium', 'high'] as const;

export function BaseStability({ cases, summary, lexicon, filterEntity }: { cases: CaseFile[]; summary: Summary; lexicon: Lexicon; filterEntity: string }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tip = useTooltip();
  const pairs = useMemo(() => cases.flatMap((cf) => EFFORTS.map((e) => ({ case_id: cf.case.case_id, entity: cf.case.entity, effort: e, ref: cf.base_reference?.[e] ?? null }))).filter((p) => p.ref), [cases]);
  const stable = pairs.filter((p) => p.ref!.base_stable).length;
  const share = summary.counts.base_pairs ? (summary.counts.base_pairs - summary.counts.unstable_base_pairs) / summary.counts.base_pairs : pairs.length ? stable / pairs.length : null;

  const cell = 40, left = 84, top = 30;
  const W = left + 3 * cell + 12, H = top + cases.length * cell + 6;
  const table = { columns: ['Case', 'Entity', 'Effort', 'Modal answer', 'Modal share', 'Runs', 'Stable'], rows: pairs.map((p) => [p.case_id, entityShort(p.entity), p.effort, entityShort(p.ref!.base_modal_entity), p.ref!.base_mode_share, p.ref!.base_n, p.ref!.base_stable ? 'yes' : 'no']) };

  return (
    <ChartFrame id="base-stability" title="Base stability" svgRef={svgRef} table={table} tooltip={tip.node}
      exportData={{ id: 'base-stability', base_pairs: summary.counts.base_pairs, unstable_base_pairs: summary.counts.unstable_base_pairs, pairs }}
      legend={[{ label: 'stable: modal answer in every base run', color: 'var(--supported)', shape: 'square' }, { label: 'unstable: excluded from counterfactual rates', color: 'var(--contradicted)', shape: 'square' }]}
      subtitle={<>Each case needs a stable base answer at each effort before its perturbations can be scored. {summary.counts.unstable_base_pairs} of {summary.counts.base_pairs} case–effort pairs were unstable.</>}>
      <div className="row" style={{ alignItems: 'flex-start', gap: 24 }}>
        <div>
          <div className="hero-number" aria-label={`${pct(share, 0)} of base case–effort pairs stable`}>{pct(share, 0)}</div>
          <div className="muted small">stable pairs</div>
        </div>
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Base stability by case and effort" style={{ maxWidth: W }}>
          {EFFORTS.map((e, j) => <text key={e} x={left + j * cell + cell / 2} y={top - 10} textAnchor="middle" className="muted" style={{ fontSize: 11 }}>{e}</text>)}
          {cases.map((cf, i) => {
            const dim = filterEntity && cf.case.entity !== filterEntity;
            return (
              <g key={cf.case.case_id} transform={`translate(0 ${top + i * cell})`} opacity={dim ? 0.3 : 1}>
                <a href={hrefCase(cf.case.case_id)}><text x={0} y={cell / 2 + 4} style={{ fontSize: 11.5 }}><tspan fill={entityColor(lexicon, cf.case.entity)}>●</tspan> {cf.case.case_id}</text></a>
                {EFFORTS.map((e, j) => {
                  const ref = cf.base_reference?.[e];
                  if (!ref) return <rect key={e} x={left + j * cell} y={1} width={cell - 2} height={cell - 2} fill="var(--ink-3)" rx={3} />;
                  return (
                    <g key={e} className="mark" tabIndex={0} role="img" aria-label={`${cf.case.case_id} ${e}: ${ref.base_stable ? 'stable' : 'unstable'}, modal ${entityShort(ref.base_modal_entity)} in ${Math.round((ref.base_mode_share ?? 0) * ref.base_n)} of ${ref.base_n} runs`}
                      onMouseEnter={(ev) => tip.show(ev, <><strong>{ref.base_stable ? 'Stable' : 'Unstable'}</strong> <span className="muted">{cf.case.case_id}, {e} effort</span><div className="muted">modal {entityShort(ref.base_modal_entity)} in {Math.round((ref.base_mode_share ?? 0) * ref.base_n)} of {ref.base_n} runs</div></>)} onMouseMove={tip.move} onMouseLeave={tip.hide}
                      onFocus={(ev) => tip.show(ev, <><strong>{ref.base_stable ? 'Stable' : 'Unstable'}</strong> {cf.case.case_id} {e}</>)} onBlur={tip.hide}>
                      <rect x={left + j * cell} y={1} width={cell - 2} height={cell - 2} rx={3} fill={ref.base_stable ? 'var(--supported)' : 'var(--contradicted)'} fillOpacity={0.25 + 0.75 * (ref.base_mode_share ?? 0)} />
                      <text x={left + j * cell + cell / 2} y={cell / 2 + 4} textAnchor="middle" style={{ fontSize: 11 }}>{ref.base_stable ? '✓' : '✗'} {Math.round((ref.base_mode_share ?? 0) * ref.base_n)}/{ref.base_n}</text>
                    </g>
                  );
                })}
              </g>
            );
          })}
        </svg>
      </div>
    </ChartFrame>
  );
}
