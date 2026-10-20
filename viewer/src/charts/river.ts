// Outcome River data transform: per-trace records → Sankey nodes and links across four columns
// (base answer → edit kind → answer after edit → outcome). Pure, so it is unit-tested.
import type { TraceRow } from '../lib/cohort';
import { KIND_LABEL } from '../lib/palette';

export type RiverColumn = 0 | 1 | 2 | 3;
export interface RiverNode { id: string; column: RiverColumn; key: string; label: string; value: number }
export interface RiverLink {
  id: string;
  source: string;
  target: string;
  value: number;
  /** Base-answer entity of the traces in this ribbon; drives the ribbon colour. */
  entity: string | null;
  trace_keys: string[];
}
export interface River { nodes: RiverNode[]; links: RiverLink[]; n: number }

export const COLUMN_TITLES = ['Base answer', 'Edit kind', 'Answer after edit', 'Outcome'] as const;

export function riverPath(r: TraceRow): [string, string, string, string] | null {
  if (r.edit_kind === 'base' || !r.outcome) return null;
  return [r.base_modal_entity ?? 'UNRESOLVED', r.edit_kind, r.answer_entity ?? 'UNRESOLVED', r.outcome];
}

export function buildRiver(rows: TraceRow[], labelEntity: (id: string) => string = (x) => x, labelOutcome: (id: string) => string = (x) => x): River {
  const nodes = new Map<string, RiverNode>();
  const links = new Map<string, RiverLink>();
  let n = 0;
  const node = (column: RiverColumn, key: string): RiverNode => {
    const id = `${column}:${key}`;
    let nd = nodes.get(id);
    if (!nd) {
      const label = column === 0 || column === 2 ? labelEntity(key) : column === 1 ? (KIND_LABEL[key] ?? key) : labelOutcome(key);
      nd = { id, column, key, label, value: 0 };
      nodes.set(id, nd);
    }
    return nd;
  };
  for (const r of rows) {
    const path = riverPath(r);
    if (!path) continue;
    n++;
    const entity = r.base_modal_entity ?? null;
    const ids = path.map((k, i) => { const nd = node(i as RiverColumn, k); nd.value++; return nd.id; });
    for (let i = 0; i < 3; i++) {
      const id = `${ids[i]}>${ids[i + 1]}|${entity ?? ''}`;
      let l = links.get(id);
      if (!l) { l = { id, source: ids[i], target: ids[i + 1], value: 0, entity, trace_keys: [] }; links.set(id, l); }
      l.value++; l.trace_keys.push(r.trace_key);
    }
  }
  const order = (a: RiverNode, b: RiverNode) => a.column - b.column || b.value - a.value || a.key.localeCompare(b.key);
  return { nodes: [...nodes.values()].sort(order), links: [...links.values()].sort((a, b) => b.value - a.value), n };
}

/** Share of a node's outgoing flow carried by one link (the "rate" a hovered ribbon reports). */
export function linkShare(river: River, link: RiverLink): { k: number; n: number } {
  const out = river.links.filter((l) => l.source === link.source);
  const n = out.reduce((a, l) => a + l.value, 0);
  const k = out.filter((l) => l.target === link.target).reduce((a, l) => a + l.value, 0);
  return { k, n };
}
