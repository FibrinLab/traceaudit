import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { Lexicon } from '../types';
import { assertionCounts, buildAtlas, neighbours } from '../charts/atlas';
import { layoutAtlas } from '../charts/LexiconAtlas';

const index = JSON.parse(readFileSync(resolve(__dirname, '../../public/demo/index.json'), 'utf8'));
const lexicon = index.lexicon as Lexicon;

describe('buildAtlas', () => {
  it('places six entity hubs on a ring and links findings by expected polarity', () => {
    const asserted = new Map([['CD5', 10], ['CD23', 4]]);
    const problems = new Map([['CD5', 5]]);
    const atlas = buildAtlas({ lexicon, asserted, problems });
    const hubs = atlas.nodes.filter((n) => n.kind === 'entity');
    expect(hubs.map((h) => h.id)).toEqual(['CLL_SLL', 'MCL', 'FL', 'HCL', 'LPL', 'MZL']);
    for (const h of hubs) expect(Math.hypot(h.ring!.x, h.ring!.y)).toBeCloseTo(1, 6);
    const cd5 = atlas.nodes.find((n) => n.id === 'CD5')!;
    expect(cd5.size).toBe(10);
    expect(cd5.heat).toBeCloseTo(0.5);
    expect(atlas.edges.find((e) => e.source === 'CD5' && e.target === 'CLL_SLL')?.expected).toBe('pos');
    expect(atlas.edges.find((e) => e.source === 'CD5' && e.target === 'FL')?.expected).toBe('neg');
    // "var" discriminators draw no edge
    expect(atlas.edges.find((e) => e.source === 'CD5' && e.target === 'MZL')).toBeUndefined();
    expect(neighbours(atlas, 'CD5').has('CLL_SLL')).toBe(true);
    expect(atlas.nodes.find((n) => n.id === 'MCL')!.size).toBe(atlas.edges.filter((e) => e.target === 'MCL').length);
  });
  it('drops isolated findings unless asked to keep them', () => {
    const lx: Lexicon = { ...lexicon, findings: [...lexicon.findings, { id: 'orphan', display: 'Orphan', kind: 'clinical' }] };
    expect(buildAtlas({ lexicon: lx, asserted: new Map(), problems: new Map() }).nodes.some((n) => n.id === 'orphan')).toBe(false);
    expect(buildAtlas({ lexicon: lx, asserted: new Map(), problems: new Map(), includeIsolated: true }).nodes.some((n) => n.id === 'orphan')).toBe(true);
  });
  it('counts assertions per finding', () => {
    const m = assertionCounts([['CD5', 'CD5', 'CD23'], ['CD23']]);
    expect(m.get('CD5')).toBe(2);
    expect(m.get('CD23')).toBe(2);
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
