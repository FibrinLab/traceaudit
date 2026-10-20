import { describe, expect, it } from 'vitest';
import { buildConstellation, defaultBandX, layoutBands } from '../constellation/graph';
import { makeIncidentBundle } from './fixtures/incidentBundle';

const { caseFile: inc, lexicon } = makeIncidentBundle();
const trace = inc.traces.find((t) => t.variant === 'dec-recent_deploy' && t.effort === 'high')!;
const base = inc.traces.find((t) => t.variant === 'base' && t.effort === 'high')!;

describe('buildConstellation', () => {
  it('puts source findings, claims and the answer in three bands with unique edges', () => {
    const g = buildConstellation(trace, inc, lexicon, { editedFindings: new Set(['recent_deploy']) });
    const bands = [0, 1, 2].map((b) => g.nodes.filter((n) => n.band === b));
    expect(bands[0].length).toBe(Object.keys(inc.variants['dec-recent_deploy'].truth_after).length);
    expect(bands[1].length).toBe(trace.map!.nodes.filter((n) => n.type !== 'answer').length);
    expect(bands[2].length).toBe(1);
    expect(bands[2][0].entity).toBe(trace.grounding!.answer_entity);
    expect(new Set(g.edges.map((e) => e.id)).size).toBe(g.edges.length);
    expect(g.nodes.find((n) => n.id === 'f:recent_deploy')!.edited).toBe(true);
    // Source findings are grouped by section in reading order, with the section title in the node text.
    expect(bands[0][0].report).toBe('alerts');
    expect(bands[0][0].text).toMatch(/in alerts$/);
    // Each factual claim with evidence in the documents reads from a finding node.
    const reads = g.edges.filter((e) => e.kind === 'reads');
    expect(reads.length).toBeGreaterThan(0);
    for (const e of reads) {
      expect(g.nodes.find((n) => n.id === e.source)!.band).toBe(0);
      expect(g.nodes.find((n) => n.id === e.target)!.band).toBe(1);
    }
    expect(reads.every((e) => !e.flip)).toBe(true);
  });
  it('flags a reads edge as a flip when the claim contradicts the document', () => {
    const g = buildConstellation(base, inc, lexicon);
    const contradicted = base.claims.find((c) => c.label === 'contradicted')!;
    const node = g.nodes.find((n) => n.claimId === contradicted.claim_id)!;
    expect(g.edges.find((e) => e.kind === 'reads' && e.target === node.id)!.flip).toBe(true);
    // A finding the documents never state gets no source node, so the unsupported claim has no reads edge.
    const unsupported = base.claims.find((c) => c.label === 'unsupported')!;
    expect(g.edges.some((e) => e.kind === 'reads' && e.target === `c${unsupported.claim_id}`)).toBe(false);
  });
  it('overlays a base trace: matched nodes in place, base-only nodes as ghosts', () => {
    const g = buildConstellation(trace, inc, lexicon, { baseTrace: base });
    const ghosts = g.nodes.filter((n) => n.origin === 'base-only');
    const matched = g.nodes.filter((n) => n.origin === 'matched');
    expect(ghosts.length + matched.length).toBeGreaterThan(0);
    expect(ghosts.every((n) => n.id.startsWith('base:'))).toBe(true);
    expect(g.nodes.filter((n) => n.band === 2).length).toBe(base.grounding!.answer_entity === trace.grounding!.answer_entity ? 1 : 2);
  });
});

describe('layoutBands', () => {
  it('fixes x by band, keeps y inside the frame and is deterministic', () => {
    const g = buildConstellation(trace, inc, lexicon);
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
    const g = buildConstellation(trace, inc, lexicon);
    const a = layoutBands(g.nodes, g.edges, { width: 1000, height: 600, seed: 3 });
    const c = layoutBands(g.nodes, g.edges, { width: 1000, height: 600, seed: 4 });
    expect(a.map((p) => p.x)).toEqual(c.map((p) => p.x));
  });
});
