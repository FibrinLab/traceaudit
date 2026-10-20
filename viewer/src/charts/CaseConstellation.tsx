import { useMemo, useRef } from 'react';
import type { CaseFile, Lexicon, Variant } from '../types';
import { entityColor, entityShort } from '../lib/palette';
import { findingDisplay } from '../lib/format';
import { hubFontSize } from './LexiconAtlas';
import { ChartFrame } from './ChartFrame';
import { useTooltip } from './Tooltip';

interface Spoke { findingId: string; label: string; expected: 'pos' | 'neg' | 'var'; truth: 'pos' | 'neg' | null; angle: number }

/** The case's findings around its category hub: expected-positive on solid spokes, expected-negative on dashed; tested bright, untested hollow. */
export function buildSpokes(caseFile: CaseFile, lexicon: Lexicon): Spoke[] {
  const ent = caseFile.case.entity;
  const disc = lexicon.discriminators ?? {};
  const items: Omit<Spoke, 'angle'>[] = [];
  for (const f of lexicon.findings) {
    const expected = disc[f.id]?.[ent];
    const truth = caseFile.case.truth[f.id] ?? null;
    if (expected === 'pos' || expected === 'neg') items.push({ findingId: f.id, label: f.display, expected, truth });
    else if (truth === 'pos') items.push({ findingId: f.id, label: f.display, expected: 'var', truth });
  }
  const rank = (s: Omit<Spoke, 'angle'>) => (s.expected === 'pos' ? 0 : s.expected === 'neg' ? 1 : 2);
  items.sort((a, b) => rank(a) - rank(b) || a.label.localeCompare(b.label));
  return items.map((it, i) => ({ ...it, angle: -Math.PI / 2 + (i / items.length) * Math.PI * 2 }));
}

export function CaseConstellation({ caseFile, lexicon, selectedVariant, onSelectVariant }: { caseFile: CaseFile; lexicon: Lexicon; selectedVariant: string | null; onSelectVariant: (v: string | null) => void }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tip = useTooltip();
  const spokes = useMemo(() => buildSpokes(caseFile, lexicon), [caseFile, lexicon]);
  const variants = useMemo(() => Object.values(caseFile.variants).filter((v) => v.kind !== 'base'), [caseFile]);
  const variant: Variant | null = selectedVariant ? caseFile.variants[selectedVariant] ?? null : null;
  const edits = useMemo(() => {
    const m = new Map<string, { from: string | null; to: string | null; role: string }>();
    for (const e of variant?.perturbation?.edits ?? []) if (e.finding_id) m.set(e.finding_id, { from: e.from, to: e.to, role: e.role });
    return m;
  }, [variant]);
  const W = 680, H = 600, cx = W / 2, cy = H / 2, R = 180;
  const ent = caseFile.case.entity;
  const colour = (s: Spoke) => {
    const ed = edits.get(s.findingId);
    if (ed) return 'var(--edited)';
    if (s.truth === null) return 'var(--line-strong)';
    if (s.expected === 'var') return 'var(--text-2)';
    return s.truth === s.expected ? 'var(--supported)' : 'var(--contradicted)';
  };
  const tipFor = (s: Spoke) => {
    const ed = edits.get(s.findingId);
    return (
      <>
        <strong>{s.label}</strong>
        <div className="muted">{s.expected === 'var' ? 'Variable' : `Expected ${s.expected === 'pos' ? 'positive' : 'negative'}`} in {entityShort(ent)}; {s.truth === null ? 'not tested in this case' : `reported ${s.truth === 'pos' ? 'positive' : 'negative'}`}</div>
        {ed && <div style={{ color: 'var(--edited)' }}>✎ edited {ed.from ?? '?'} to {ed.to ?? '?'} ({ed.role.replace('_', ' ')})</div>}
        {s.truth !== null && s.expected !== 'var' && s.truth !== s.expected && !ed && <div style={{ color: 'var(--contradicted)' }}>Atypical for the category</div>}
      </>
    );
  };
  const table = { columns: ['Finding', 'Expected', 'Reported', 'Edited in selected variant'], rows: spokes.map((s) => [s.label, s.expected, s.truth ?? 'not tested', edits.has(s.findingId) ? `${edits.get(s.findingId)!.from} to ${edits.get(s.findingId)!.to}` : '']) };

  return (
    <ChartFrame id={`case-${caseFile.case.case_id}`} title="Case constellation" headingLevel={2} svgRef={svgRef} table={table} tooltip={tip.node}
      exportData={{ case_id: caseFile.case.case_id, entity: ent, spokes, selected_variant: selectedVariant }}
      legend={[
        { label: 'expected positive', color: 'var(--text-2)', shape: 'line' },
        { label: 'expected negative', color: 'var(--text-2)', shape: 'dashed' },
        { label: 'reported as expected', color: 'var(--supported)' },
        { label: 'reported against expectation', color: 'var(--contradicted)' },
        { label: 'not tested', color: 'var(--line-strong)', shape: 'ring' },
        { label: 'edited by the selected variant', color: 'var(--edited)' },
      ]}
      subtitle={<>The findings that discriminate {entityShort(ent)} around the case's category hub. Solid spokes are expected positive, dashed expected negative; filled satellites were reported, hollow ones were not tested. Select a variant below to see which spokes its edits flip.</>}
      aside={
        <div className="row" style={{ marginTop: 10 }} role="group" aria-label="Variants">
          <button type="button" className="btn small" aria-pressed={selectedVariant === null} onClick={() => onSelectVariant(null)}>Base documents</button>
          {variants.map((v) => (
            <button key={v.variant} type="button" className="btn small" aria-pressed={selectedVariant === v.variant} onClick={() => onSelectVariant(selectedVariant === v.variant ? null : v.variant)}>
              <span style={{ color: v.kind === 'authority' ? 'var(--cue)' : 'var(--edited)' }} aria-hidden="true">{v.kind === 'authority' ? '▲' : '✎'}</span> <span className="mono">{v.variant}</span>
            </button>
          ))}
        </div>
      }>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`Case constellation for ${caseFile.case.case_id}`} style={{ ['--svg-max' as string]: '720px' }}>
        {spokes.map((s) => {
          const x = cx + Math.cos(s.angle) * R, y = cy + Math.sin(s.angle) * R;
          const c = colour(s);
          const lx = cx + Math.cos(s.angle) * (R + 13), ly = cy + Math.sin(s.angle) * (R + 13);
          const right = Math.cos(s.angle) >= 0;
          const deg = (s.angle * 180) / Math.PI;
          const ed = edits.get(s.findingId);
          return (
            <g key={s.findingId} className="mark" tabIndex={0} role="img" aria-label={`${s.label}: expected ${s.expected}, ${s.truth === null ? 'not tested' : `reported ${s.truth}`}${ed ? `, edited ${ed.from} to ${ed.to}` : ''}`}
              onMouseEnter={(e) => tip.show(e, tipFor(s))} onMouseMove={tip.move} onMouseLeave={tip.hide} onFocus={(e) => tip.show(e, tipFor(s))} onBlur={tip.hide}>
              <line x1={cx} y1={cy} x2={x} y2={y} stroke={c} strokeWidth={ed ? 2.4 : s.expected === 'var' ? 1 : 1.4} strokeDasharray={s.expected === 'neg' ? '4 4' : s.expected === 'var' ? '1 3' : undefined} opacity={s.truth === null ? 0.5 : 0.85} />
              <circle cx={x} cy={y} r={s.truth === null ? 5 : 6.5} fill={s.truth === null ? 'var(--ink-2)' : c} stroke={c} strokeWidth={1.8} />
              {ed && <text x={x} y={y - 10} textAnchor="middle" style={{ fontSize: 11, fill: 'var(--edited)', fontWeight: 600 }}>✎</text>}
              <text transform={`translate(${lx} ${ly}) rotate(${right ? deg : deg + 180})`} textAnchor={right ? 'start' : 'end'} dominantBaseline="middle" style={{ fontSize: 10.5 }} className={s.truth === null ? 'muted' : ''}>{s.label.length > 24 ? s.label.slice(0, 23) + '…' : s.label}</text>
            </g>
          );
        })}
        <circle cx={cx} cy={cy} r={34} fill={entityColor(lexicon, ent)} stroke="var(--ink-2)" strokeWidth={3} />
        <text x={cx} y={cy + 4.5} textAnchor="middle" style={{ fontSize: hubFontSize(entityShort(ent)) + 1, fontWeight: 700, fill: 'var(--ink)' }}>{entityShort(ent)}</text>
        {variant?.perturbation?.cue && <text x={cx} y={cy + 56} textAnchor="middle" style={{ fontSize: 11.5, fill: 'var(--cue)' }}>▲ cue: {entityShort(variant.perturbation.cue.entity)} ({variant.perturbation.cue.correct ? 'correct' : 'wrong'})</text>}
        {variant?.perturbation?.expected_entity && <text x={cx} y={cy + 56} textAnchor="middle" style={{ fontSize: 11.5, fill: 'var(--edited)' }}>✎ expected to become {entityShort(variant.perturbation.expected_entity)}</text>}
      </svg>
      {variant?.perturbation && <p className="small muted" style={{ marginTop: 6 }}>{variant.perturbation.rationale}{variant.perturbation.linked_findings.length ? ` Linked findings: ${variant.perturbation.linked_findings.map((f) => findingDisplay(lexicon, f)).join(', ')}.` : ''}</p>}
    </ChartFrame>
  );
}
