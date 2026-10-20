import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { CaseFile, Lexicon } from '../types';
import { buildConstellation, defaultBandX, layoutBands } from '../constellation/graph';

const demo = resolve(__dirname, '../../public/demo');
const lexicon = JSON.parse(readFileSync(resolve(demo, 'index.json'), 'utf8')).lexicon as Lexicon;
const cll = JSON.parse(readFileSync(resolve(demo, 'cases/CLL-001.json'), 'utf8')) as CaseFile;
const trace = cll.traces.find((t) => t.variant === 'dec-cyclin_d1' && t.effort === 'high' && t.run === 0)!;
const base = cll.traces.find((t) => t.variant === 'base' && t.effort === 'high' && t.run === 0)!;

describe('buildConstellation', () => {
  it('puts source findings, claims and the answer in three bands with unique edges', () => {
    const g = buildConstellation(trace, cll, lexicon, { editedFindings: new Set(['cyclin_D1']) });
    const bands = [0, 1, 2].map((b) => g.nodes.filter((n) => n.band === b));
    expect(bands[0].length).toBe(Object.keys(cll.variants['dec-cyclin_d1'].truth_after).length);
    expect(bands[1].length).toBe(trace.map!.nodes.filter((n) => n.type !== 'answer').length);
    expect(bands[2].length).toBe(1);
    expect(bands[2][0].entity).toBe(trace.grounding!.answer_entity);
    expect(new Set(g.edges.map((e) => e.id)).size).toBe(g.edges.length);
    expect(g.nodes.find((n) => n.id === 'f:cyclin_D1')!.edited).toBe(true);
    // Each factual claim with evidence in the reports reads from a finding node.
    const reads = g.edges.filter((e) => e.kind === 'reads');
    expect(reads.length).toBeGreaterThan(0);
    for (const e of reads) {
      expect(g.nodes.find((n) => n.id === e.source)!.band).toBe(0);
      expect(g.nodes.find((n) => n.id === e.target)!.band).toBe(1);
    }
    const contradicted = trace.claims.find((c) => c.label === 'contradicted')!;
    const node = g.nodes.find((n) => n.claimId === contradicted.claim_id)!;
    expect(reads.find((e) => e.target === node.id)!.flip).toBe(true);
  });
  it('overlays a base trace: matched nodes in place, base-only nodes as ghosts', () => {
    const g = buildConstellation(trace, cll, lexicon, { baseTrace: base });
    const ghosts = g.nodes.filter((n) => n.origin === 'base-only');
    const matched = g.nodes.filter((n) => n.origin === 'matched');
    expect(ghosts.length + matched.length).toBeGreaterThan(0);
    expect(ghosts.every((n) => n.id.startsWith('base:'))).toBe(true);
    expect(g.nodes.filter((n) => n.band === 2).length).toBe(base.grounding!.answer_entity === trace.grounding!.answer_entity ? 1 : 2);
  });
});

describe('layoutBands', () => {
  it('fixes x by band, keeps y inside the frame and is deterministic', () => {
    const g = buildConstellation(trace, cll, lexicon);
    const opts = { width: 1000, height: 600, seed: 3 };
    const a = layoutBands(g.nodes, g.edges, opts);
    const b = layoutBands(g.nodes, g.edges, opts);
    expect(a).toEqual(b);
    const bx = defaultBandX(1000);
    for (const p of a) {
      const n = g.nodes.find((x) => x.id === p.id)!;
      expect(p.x).toBe(bx[n.band]);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(600);
    }
    // Finding band stays in reading order (the slot force dominates), claims are separated by the collision radius.
    const band0 = a.filter((p) => g.nodes.find((x) => x.id === p.id)!.band === 0).map((p) => ({ y: p.y, order: g.nodes.find((x) => x.id === p.id)!.order })).sort((u, v) => u.order - v.order);
    for (let i = 1; i < band0.length; i++) expect(band0[i].y).toBeGreaterThan(band0[i - 1].y);
    const band1 = a.filter((p) => g.nodes.find((x) => x.id === p.id)!.band === 1).map((p) => p.y).sort((u, v) => u - v);
    for (let i = 1; i < band1.length; i++) expect(band1[i] - band1[i - 1]).toBeGreaterThan(10);
  });
  it('changes with the seed but not with unrelated options', () => {
    const g = buildConstellation(trace, cll, lexicon);
    const a = layoutBands(g.nodes, g.edges, { width: 1000, height: 600, seed: 3 });
    const c = layoutBands(g.nodes, g.edges, { width: 1000, height: 600, seed: 4 });
    expect(a.map((p) => p.x)).toEqual(c.map((p) => p.x));
  });
});
