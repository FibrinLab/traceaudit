// Reasoning constellation: graph construction (pure) and the band-constrained force layout (pure, worker-safe).
import { forceCollide, forceLink, forceSimulation, forceY, type SimulationLinkDatum, type SimulationNodeDatum } from 'd3-force';
import type { CaseFile, Claim, GroundingLabel, Lexicon, ReportName, Trace, Variant } from '../types';
import { sectionIndex, sectionTitle, sectionsFor } from '../lib/documents';
import { seeded, hashString } from '../lib/palette';
import { nodeMatchKey } from '../lib/layout';

export type Band = 0 | 1 | 2;
export type NodeShape = 'finding' | 'disc' | 'ring' | 'diamond' | 'answer';

export interface CNode {
  id: string;
  band: Band;
  shape: NodeShape;
  label: string;
  text: string;
  /** Band 0: the report the finding was read from. */
  report?: ReportName;
  polarity?: 'pos' | 'neg';
  findingId?: string;
  claimId?: number | null;
  claimType?: Claim['type'] | 'answer';
  grounding?: GroundingLabel;
  entity?: string | null;
  /** Reading-order index within the band (drives the initial y and tab order). */
  order: number;
  break?: boolean;
  /** Overlay provenance. */
  origin: 'this' | 'base-only' | 'matched';
  edited?: boolean;
  /** Fixed x by band; y relaxed by the layout. */
  x?: number;
  y?: number;
}

export interface CEdge { id: string; source: string; target: string; kind: 'evidence' | 'knowledge' | 'chain' | 'conclusion' | 'reads'; flip?: boolean; weak?: boolean; origin: 'this' | 'base-only' }

export interface Constellation { nodes: CNode[]; edges: CEdge[]; answerId: string }

const CLAIM_LABEL_CHARS = 34;

function shorten(s: string, n: number): string { return s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s; }

/** Findings asserted in the documents the model saw, grouped by section in reading order. */
export function sourceFindings(variant: Pick<Variant, 'finding_spans' | 'truth_after'> | null, caseFile: CaseFile, lexicon: Lexicon): CNode[] {
  const spans = variant?.finding_spans ?? caseFile.case.finding_spans ?? {};
  const truth = variant?.truth_after ?? caseFile.case.truth;
  const sections = sectionsFor(caseFile.case.reports, caseFile.case.sections);
  const order = (r: string) => sectionIndex(sections, r);
  const items: Array<{ findingId: string; report: ReportName; start: number; polarity: 'pos' | 'neg' }> = [];
  for (const [fid, list] of Object.entries(spans)) {
    if (!list?.length) continue;
    const first = list.slice().sort((a, b) => order(a.report) - order(b.report) || a.start - b.start)[0];
    items.push({ findingId: fid, report: first.report, start: first.start, polarity: truth[fid] ?? first.polarity });
  }
  for (const [fid, pol] of Object.entries(truth)) if (!spans[fid]?.length) items.push({ findingId: fid, report: sections[0]?.id ?? 'clinical', start: 1e9, polarity: pol });
  items.sort((a, b) => order(a.report) - order(b.report) || a.start - b.start);
  return items.map((it, i) => ({
    id: `f:${it.findingId}`, band: 0, shape: 'finding', label: shorten(lexicon.findings.find((f) => f.id === it.findingId)?.display ?? it.findingId, 26),
    text: `${lexicon.findings.find((f) => f.id === it.findingId)?.display ?? it.findingId} ${it.polarity === 'pos' ? 'positive' : 'negative'} in ${sectionTitle(sections, it.report).toLowerCase()}`,
    report: it.report, polarity: it.polarity, findingId: it.findingId, order: i, origin: 'this',
  }));
}

export interface BuildOptions {
  baseTrace?: Trace | null;
  editedFindings?: Set<string>;
  truthEntity?: string | null;
}

export function buildConstellation(trace: Trace, caseFile: CaseFile, lexicon: Lexicon, opts: BuildOptions = {}): Constellation {
  const variant = caseFile.variants[trace.variant] ?? null;
  const nodes: CNode[] = sourceFindings(variant, caseFile, lexicon);
  const edges: CEdge[] = [];
  const findingNode = new Map(nodes.map((n) => [n.findingId!, n.id]));
  const edited = opts.editedFindings ?? new Set<string>();
  for (const n of nodes) if (n.findingId && edited.has(n.findingId)) n.edited = true;

  const claimById = new Map(trace.claims.map((c) => [c.claim_id, c]));
  const map = trace.map;
  const claimNodes: CNode[] = [];
  const edgeIds = new Set<string>();
  let answerId = 'answer';
  if (map) {
    let order = 0;
    for (const mn of map.nodes) {
      if (mn.type === 'answer') {
        answerId = mn.id;
        nodes.push({ id: mn.id, band: 2, shape: 'answer', label: mn.entities[0] ?? 'unresolved', text: mn.text, claimId: null, claimType: 'answer', entity: mn.entities[0] ?? trace.grounding?.answer_entity ?? null, order: 0, origin: 'this', break: mn.break });
        continue;
      }
      const c = mn.claim_id !== null ? claimById.get(mn.claim_id) : undefined;
      const shape: NodeShape = mn.type === 'inferential' ? 'diamond' : mn.type === 'knowledge' ? 'ring' : 'disc';
      claimNodes.push({ id: mn.id, band: 1, shape, label: shorten(mn.text, CLAIM_LABEL_CHARS), text: c?.text ?? mn.text, claimId: mn.claim_id, claimType: mn.type, grounding: mn.label, entity: mn.entities[0] ?? null, order: order++, origin: 'this', break: mn.break, edited: mn.findings.some((f) => edited.has(f)) });
      if (c) {
        for (const ev of c.evidence) {
          const src = findingNode.get(ev.finding_id);
          if (!src) continue;
          const id = `${src}>${mn.id}`;
          if (edgeIds.has(id)) continue;
          edgeIds.add(id);
          edges.push({ id, source: src, target: mn.id, kind: 'reads', flip: ev.truth !== null && ev.claimed !== null && ev.truth !== ev.claimed, origin: 'this' });
        }
      }
    }
    for (const e of map.edges) { const id = `${e.source}>${e.target}`; if (edgeIds.has(id)) continue; edgeIds.add(id); edges.push({ id, source: e.source, target: e.target, kind: e.kind, weak: e.weak, origin: 'this' }); }
  }
  nodes.push(...claimNodes);
  if (!nodes.some((n) => n.band === 2)) nodes.push({ id: answerId, band: 2, shape: 'answer', label: trace.grounding?.answer_entity ?? 'unresolved', text: trace.answer, claimId: null, claimType: 'answer', entity: trace.grounding?.answer_entity ?? null, order: 0, origin: 'this' });

  // Overlay: base nodes matched on (type, findings, entities) sit in place; unmatched base nodes are ghosts.
  const base = opts.baseTrace?.map;
  if (base) {
    const thisKeys = new Map(map ? map.nodes.map((n) => [nodeMatchKey(n), n.id]) : []);
    const idMap = new Map<string, string>();
    let order = claimNodes.length;
    for (const bn of base.nodes) {
      const match = thisKeys.get(nodeMatchKey(bn));
      if (match) { idMap.set(bn.id, match); const n = nodes.find((x) => x.id === match); if (n) n.origin = 'matched'; continue; }
      const id = `base:${bn.id}`;
      idMap.set(bn.id, id);
      if (bn.type === 'answer') nodes.push({ id, band: 2, shape: 'answer', label: bn.entities[0] ?? 'unresolved', text: bn.text, claimId: null, claimType: 'answer', entity: bn.entities[0] ?? null, order: 1, origin: 'base-only' });
      else nodes.push({ id, band: 1, shape: bn.type === 'inferential' ? 'diamond' : bn.type === 'knowledge' ? 'ring' : 'disc', label: shorten(bn.text, CLAIM_LABEL_CHARS), text: bn.text, claimId: bn.claim_id, claimType: bn.type, grounding: bn.label, entity: bn.entities[0] ?? null, order: order++, origin: 'base-only' });
    }
    const have = edgeIds;
    for (const e of base.edges) {
      const s = idMap.get(e.source), t = idMap.get(e.target);
      if (!s || !t) continue;
      const id = `${s}>${t}`;
      if (have.has(id)) continue;
      have.add(id);
      edges.push({ id, source: s, target: t, kind: e.kind, weak: e.weak, origin: 'base-only' });
    }
    for (const n of nodes) if (n.origin === 'this' && n.band === 1 && map) n.origin = 'this';
  }
  return { nodes, edges, answerId };
}

export interface LayoutOptions { width: number; height: number; seed?: number; bandX?: [number, number, number]; compact?: boolean }
export interface Positioned { id: string; x: number; y: number }

/** Band-constrained force layout: x fixed by band, y relaxed by link pull, reading-order gravity and collision. Deterministic. */
export function layoutBands(nodes: CNode[], edges: CEdge[], opts: LayoutOptions): Positioned[] {
  const { width, height } = opts;
  const bandX = opts.bandX ?? defaultBandX(width);
  const seed = opts.seed ?? 1;
  const pad = opts.compact ? 14 : 30;
  type SN = CNode & SimulationNodeDatum & { slotY: number; r: number };
  const byBand: CNode[][] = [[], [], []];
  for (const n of nodes) byBand[n.band].push(n);
  for (const b of byBand) b.sort((a, c) => a.order - c.order);
  const sim: SN[] = [];
  const rnd = seeded(seed + hashString(nodes.map((n) => n.id).join('|')));
  for (let b = 0; b < 3; b++) {
    const list = byBand[b];
    const n = list.length;
    const r = b === 2 ? (opts.compact ? 14 : 22) : b === 0 ? (opts.compact ? 4 : 5.5) : (opts.compact ? 6 : 8);
    const step = n > 1 ? Math.min((height - pad * 2) / (n - 1), b === 0 ? (opts.compact ? 13 : 18) : (opts.compact ? 20 : 30)) : 0;
    const total = step * Math.max(0, n - 1);
    const y0 = (height - total) / 2;
    list.forEach((nd, i) => {
      const slotY = n > 1 ? y0 + i * step : height / 2;
      // Source findings keep their reading order exactly (fixed y); claims and the answer relax.
      sim.push({ ...nd, fx: bandX[b], x: bandX[b], y: slotY + (rnd() - 0.5) * 2, slotY, r, ...(b === 0 ? { fy: slotY } : {}) });
    });
  }
  const byId = new Map(sim.map((n) => [n.id, n]));
  const links: Array<SimulationLinkDatum<SN>> = edges.filter((e) => byId.has(e.source) && byId.has(e.target)).map((e) => ({ source: e.source, target: e.target }));
  const s = forceSimulation<SN>(sim)
    .randomSource(seeded(seed))
    .force('slot', forceY<SN>((d) => d.slotY).strength((d) => (d.band === 0 ? 0.9 : d.band === 2 ? 0.6 : 0.25)))
    .force('link', forceLink<SN, SimulationLinkDatum<SN>>(links).id((d) => d.id).strength(0.15).distance(0))
    .force('collide', forceCollide<SN>().radius((d) => d.r + (d.band === 1 ? 7 : 3)).strength(0.9).iterations(3))
    .alphaDecay(0.03)
    .stop();
  for (let i = 0; i < 220; i++) s.tick();
  // Keep each band inside the frame: rescale a band that spilled over rather than clamping (clamping would stack nodes).
  for (let b = 0; b < 3; b++) {
    const list = sim.filter((n) => n.band === b);
    if (!list.length) continue;
    const ys = list.map((n) => n.fy ?? n.y ?? 0);
    const lo = Math.min(...ys), hi = Math.max(...ys);
    if (lo >= pad && hi <= height - pad) continue;
    const span = Math.max(1, hi - lo), avail = height - pad * 2;
    for (const n of list) {
      const y = n.fy ?? n.y ?? 0;
      const ny = span <= avail ? y + (lo < pad ? pad - lo : height - pad - hi) : pad + ((y - lo) / span) * avail;
      if (n.fy !== undefined) n.fy = ny; else n.y = ny;
    }
  }
  return sim.map((n) => ({ id: n.id, x: n.fx ?? n.x ?? 0, y: n.fy ?? n.y ?? 0 }));
}

export function defaultBandX(width: number): [number, number, number] { return [Math.round(width * 0.22), Math.round(width * 0.56), Math.round(width * 0.91)]; }

/** Frame height that gives the finding band room: ~17px per source finding. */
export function frameHeight(nodes: CNode[], compact: boolean): number {
  const n0 = nodes.filter((n) => n.band === 0).length, n1 = nodes.filter((n) => n.band === 1).length;
  if (compact) return 300;
  return Math.max(520, Math.min(1100, Math.max(n0 * 17, n1 * 28) + 90));
}

export function edgePath(a: { x: number; y: number }, b: { x: number; y: number }): string {
  const dx = Math.max(24, (b.x - a.x) * 0.45);
  return `M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}`;
}

export function edgeLength(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.hypot(b.x - a.x, b.y - a.y) * 1.08 + 4;
}

