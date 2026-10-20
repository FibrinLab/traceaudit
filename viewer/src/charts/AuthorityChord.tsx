import { useMemo, useRef, useState } from 'react';
import { chordDirected, ribbonArrow, type Chord, type ChordGroup } from 'd3-chord';
import { arc } from 'd3-shape';
import type { Lexicon } from '../types';
import type { TraceRow } from '../lib/cohort';
import { entityColor, entityShort, orderEntities } from '../lib/palette';
import { pct } from '../lib/format';
import { ChartFrame } from './ChartFrame';
import { useTooltip } from './Tooltip';

const W = 520, H = 460, R = 160;

interface Cell { from: string; to: string; n: number; silent: number; ack: number; held: number; cues: Record<string, number> }

export function AuthorityChord({ rows, lexicon, onFilterEntity }: { rows: TraceRow[]; lexicon: Lexicon; onFilterEntity: (e: string) => void }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tip = useTooltip();
  const [hover, setHover] = useState<number | null>(null);

  const { names, matrix, cells, n } = useMemo(() => {
    const wrong = rows.filter((r) => r.edit_kind === 'authority_wrong' && r.base_stable && r.outcome && r.outcome !== 'already_agreed');
    const present = new Set<string>();
    for (const r of wrong) { present.add(r.base_modal_entity ?? 'UNRESOLVED'); present.add(r.answer_entity ?? 'UNRESOLVED'); }
    const names = orderEntities(lexicon, present);
    const idx = new Map(names.map((e, i) => [e, i]));
    const matrix = names.map(() => names.map(() => 0));
    const cells = new Map<string, Cell>();
    for (const r of wrong) {
      const from = r.base_modal_entity ?? 'UNRESOLVED', to = r.answer_entity ?? 'UNRESOLVED';
      matrix[idx.get(from)!][idx.get(to)!]++;
      const k = `${from}>${to}`;
      const c = cells.get(k) ?? { from, to, n: 0, silent: 0, ack: 0, held: 0, cues: {} };
      c.n++;
      if (r.outcome === 'shifted_silent') c.silent++; else if (r.outcome === 'shifted_ack') c.ack++; else c.held++;
      c.cues[r.cue_entity ?? '?'] = (c.cues[r.cue_entity ?? '?'] ?? 0) + 1;
      cells.set(k, c);
    }
    return { names, matrix, cells, n: wrong.length };
  }, [rows, lexicon]);

  const chords = useMemo(() => (names.length ? chordDirected().padAngle(0.05).sortSubgroups((a, b) => b - a)(matrix) : null), [names, matrix]);
  const arcGen = arc<ChordGroup>().innerRadius(R).outerRadius(R + 14);
  const ribbon = ribbonArrow<Chord, Chord['source']>().radius(R - 2).headRadius(10).padAngle(0.01);

  const cellFor = (c: Chord) => cells.get(`${names[c.source.index]}>${names[c.target.index]}`);
  const tipFor = (c: Chord) => {
    const cell = cellFor(c);
    if (!cell) return null;
    const self = cell.from === cell.to;
    return (
      <>
        <strong>{cell.n} traces</strong>
        <div>{self ? `Held the base answer ${entityShort(cell.from)} against a wrong cue` : `Base answer ${entityShort(cell.from)} became ${entityShort(cell.to)}`}</div>
        <div className="muted">Cue named: {Object.entries(cell.cues).map(([e, k]) => `${entityShort(e)} (${k})`).join(', ')}</div>
        <div className="muted">shifted silently {cell.silent}, shifted and acknowledged {cell.ack}, held {cell.held}</div>
      </>
    );
  };

  const table = { columns: ['Base answer', 'Answer after cue', 'n', 'Shifted silent', 'Shifted acknowledged', 'Held', 'Cue entities'], rows: [...cells.values()].sort((a, b) => b.n - a.n).map((c) => [entityShort(c.from), entityShort(c.to), c.n, c.silent, c.ack, c.held, Object.entries(c.cues).map(([e, k]) => `${entityShort(e)} ${k}`).join(', ')]) };
  const legend = names.map((e) => ({ label: entityShort(e), color: entityColor(lexicon, e) }));
  const shifted = [...cells.values()].filter((c) => c.from !== c.to).reduce((a, c) => a + c.n, 0);

  return (
    <ChartFrame id="authority-chord" title="Authority chord" svgRef={svgRef} table={table} legend={legend} tooltip={tip.node}
      exportData={{ id: 'authority-chord', entities: names, matrix, cells: [...cells.values()] }}
      subtitle={<>Wrong-cue traces flow from the model's base answer to its answer after an authority cue. A ribbon that returns to its own arc held the base answer; a ribbon crossing to another category followed the cue. {n} traces, {pct(n ? shifted / n : null, 0)} shifted.</>}>
      {!chords ? <p className="muted">No wrong-cue traces match the filters.</p> : (
        <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Authority chord diagram">
          <g transform={`translate(${W / 2} ${H / 2})`}>
            {chords.map((c, i) => {
              const cell = cellFor(c);
              const lit = hover === null || hover === i || hover === -1 - c.source.index || hover === -1 - c.target.index;
              return (
                <path key={i} d={ribbon(c) as unknown as string} fill={entityColor(lexicon, names[c.source.index])} fillOpacity={lit ? 0.72 : 0.12} stroke={entityColor(lexicon, names[c.source.index])} strokeOpacity={lit ? 0.9 : 0.15}
                  className="mark" tabIndex={0} role="img" aria-label={cell ? `${cell.n} traces, base ${entityShort(cell.from)} to ${entityShort(cell.to)}` : ''}
                  onMouseEnter={(e) => { setHover(i); tip.show(e, tipFor(c)); }} onMouseMove={tip.move} onMouseLeave={() => { setHover(null); tip.hide(); }}
                  onFocus={(e) => { setHover(i); tip.show(e, tipFor(c)); }} onBlur={() => { setHover(null); tip.hide(); }} />
              );
            })}
            {chords.groups.map((g) => {
              const a = (g.startAngle + g.endAngle) / 2 - Math.PI / 2;
              const lx = Math.cos(a) * (R + 30), ly = Math.sin(a) * (R + 30);
              const name = names[g.index];
              return (
                <g key={g.index} className="mark" tabIndex={0} role="button" aria-label={`${entityShort(name)}: ${g.value} traces with this base answer`}
                  onMouseEnter={() => setHover(-1 - g.index)} onMouseLeave={() => setHover(null)} onFocus={() => setHover(-1 - g.index)} onBlur={() => setHover(null)}
                  onClick={() => onFilterEntity(name)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFilterEntity(name); } }}>
                  <path d={arcGen(g) ?? undefined} fill={entityColor(lexicon, name)} />
                  <text x={lx} y={ly + 4} textAnchor={Math.cos(a) > 0.2 ? 'start' : Math.cos(a) < -0.2 ? 'end' : 'middle'} style={{ fontSize: 12 }}>{entityShort(name)} <tspan className="muted" style={{ fontSize: 11 }}>{matrix[g.index].reduce((x, y) => x + y, 0)}</tspan></text>
                </g>
              );
            })}
          </g>
        </svg>
      )}
    </ChartFrame>
  );
}
