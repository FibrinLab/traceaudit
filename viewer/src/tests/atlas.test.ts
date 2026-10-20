import { describe, expect, it } from 'vitest';
import type { Lexicon } from '../types';
import { assertionCounts, buildAtlas, neighbours } from '../charts/atlas';
import { layoutAtlas } from '../charts/LexiconAtlas';
import { makeIncidentBundle } from './fixtures/incidentBundle';

const { lexicon } = makeIncidentBundle();

describe('buildAtlas', () => {
  it('places the lexicon categories as hubs on a ring and links findings by expected polarity', () => {
    const asserted = new Map([['recent_deploy', 10], ['cpu_saturated', 4]]);
    const problems = new Map([['recent_deploy', 5]]);
    const atlas = buildAtlas({ lexicon, asserted, problems });
    const hubs = atlas.nodes.filter((n) => n.kind === 'entity');
    expect(hubs.map((h) => h.id)).toEqual(['BAD_DEPLOY', 'CAPACITY', 'DATABASE', 'DISK']);
    expect(hubs[0].label).toBe('Faulty deployment');
    for (const h of hubs) expect(Math.hypot(h.ring!.x, h.ring!.y)).toBeCloseTo(1, 6);
    const rd = atlas.nodes.find((n) => n.id === 'recent_deploy')!;
    expect(rd.size).toBe(10);
    expect(rd.heat).toBeCloseTo(0.5);
    expect(atlas.edges.find((e) => e.source === 'recent_deploy' && e.target === 'BAD_DEPLOY')?.expected).toBe('pos');
    expect(atlas.edges.find((e) => e.source === 'recent_deploy' && e.target === 'CAPACITY')?.expected).toBe('neg');
    // "var" discriminators draw no edge
    expect(atlas.edges.find((e) => e.source === 'cpu_saturated' && e.target === 'BAD_DEPLOY')).toBeUndefined();
    expect(neighbours(atlas, 'recent_deploy').has('BAD_DEPLOY')).toBe(true);
    expect(atlas.nodes.find((n) => n.id === 'CAPACITY')!.size).toBe(atlas.edges.filter((e) => e.target === 'CAPACITY').length);
  });
  it('drops isolated findings unless asked to keep them', () => {
    const lx: Lexicon = { ...lexicon, findings: [...lexicon.findings, { id: 'orphan', display: 'Orphan', kind: 'other' }] };
    expect(buildAtlas({ lexicon: lx, asserted: new Map(), problems: new Map() }).nodes.some((n) => n.id === 'orphan')).toBe(false);
    expect(buildAtlas({ lexicon: lx, asserted: new Map(), problems: new Map(), includeIsolated: true }).nodes.some((n) => n.id === 'orphan')).toBe(true);
  });
  it('counts assertions per finding', () => {
    const m = assertionCounts([['recent_deploy', 'recent_deploy', 'cpu_saturated'], ['cpu_saturated']]);
    expect(m.get('recent_deploy')).toBe(2);
    expect(m.get('cpu_saturated')).toBe(2);
  });
});

describe('layoutAtlas', () => {
  it('is deterministic and keeps hubs pinned', () => {
    const atlas = buildAtlas({ lexicon, asserted: new Map(), problems: new Map() });
    const a = layoutAtlas(atlas), b = layoutAtlas(atlas);
    expect(a.nodes.map((n) => [n.id, Math.round(n.x!), Math.round(n.y!)])).toEqual(b.nodes.map((n) => [n.id, Math.round(n.x!), Math.round(n.y!)]));
    for (const n of a.nodes) {
      expect(Number.isFinite(n.x)).toBe(true);
      expect(Number.isFinite(n.y)).toBe(true);
      if (n.kind === 'entity') { expect(n.fx).toBeDefined(); expect(n.x).toBe(n.fx); }
    }
  });
});
