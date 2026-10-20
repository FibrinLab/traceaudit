// Lexicon Atlas graph builder: entity hubs in a ring, finding satellites, expected-polarity edges.
// Pure (no d3); the force layout runs in LexiconAtlas.tsx. Unit-tested.
import type { Lexicon } from '../types';
import { ENTITY_ORDER } from '../lib/palette';

export interface AtlasNode {
  id: string;
  kind: 'entity' | 'finding';
  label: string;
  /** Findings: how often asserted in the traces in view. Entities: number of findings linked. */
  size: number;
  /** Findings: share of assertions contradicted or unsupported, 0..1 (hallucination heat). */
  heat: number;
  problems: number;
  findingKind?: string;
  /** Entities: fixed ring position (unit circle, scaled by the renderer). */
  ring?: { x: number; y: number };
}
export interface AtlasEdge { id: string; source: string; target: string; expected: 'pos' | 'neg' }
export interface Atlas { nodes: AtlasNode[]; edges: AtlasEdge[] }

export interface AtlasInputs {
  lexicon: Lexicon;
  /** finding → number of factual assertions (from the traces in view). */
  asserted: Map<string, number>;
  /** finding → contradicted + unsupported claim counts (summary.grounding.per_finding or recomputed). */
  problems: Map<string, number>;
  entities?: readonly string[];
  /** Include findings with neither a discriminator edge nor an assertion (default false). */
  includeIsolated?: boolean;
}

export function buildAtlas({ lexicon, asserted, problems, entities = ENTITY_ORDER, includeIsolated = false }: AtlasInputs): Atlas {
  const disc = lexicon.discriminators ?? {};
  const nodes: AtlasNode[] = [];
  const edges: AtlasEdge[] = [];
  const degree = new Map<string, number>();
  entities.forEach((e, i) => {
    const a = -Math.PI / 2 + (i / entities.length) * Math.PI * 2;
    const ent = lexicon.entities.find((x) => x.id === e);
    nodes.push({ id: e, kind: 'entity', label: ent?.display ?? e, size: 0, heat: 0, problems: 0, ring: { x: Math.cos(a), y: Math.sin(a) } });
  });
  for (const f of lexicon.findings) {
    const row = disc[f.id] ?? {};
    const fEdges: AtlasEdge[] = [];
    for (const e of entities) {
      const v = row[e];
      if (v === 'pos' || v === 'neg') fEdges.push({ id: `${f.id}-${e}`, source: f.id, target: e, expected: v });
    }
    const n = asserted.get(f.id) ?? 0;
    if (!fEdges.length && n === 0 && !includeIsolated) continue;
    const p = problems.get(f.id) ?? 0;
    nodes.push({ id: f.id, kind: 'finding', label: f.display, size: n, heat: n > 0 ? Math.min(1, p / n) : 0, problems: p, findingKind: f.kind });
    for (const e of fEdges) { edges.push(e); degree.set(e.target, (degree.get(e.target) ?? 0) + 1); }
  }
  for (const nd of nodes) if (nd.kind === 'entity') nd.size = degree.get(nd.id) ?? 0;
  return { nodes, edges };
}

/** Neighbour ids for keyboard navigation and dim-not-hide. */
export function neighbours(atlas: Atlas, id: string): Set<string> {
  const out = new Set<string>();
  for (const e of atlas.edges) { if (e.source === id) out.add(e.target); if (e.target === id) out.add(e.source); }
  return out;
}

/** Count factual assertions per finding across traces (accepts the flattened rows' asserted lists). */
export function assertionCounts(lists: Iterable<string[]>): Map<string, number> {
  const m = new Map<string, number>();
  for (const l of lists) for (const f of l) m.set(f, (m.get(f) ?? 0) + 1);
  return m;
}
