import { describe, expect, it } from 'vitest';
import { hashSeed, presentationOrder, seededShuffle } from '../lib/shuffle';

const set = Array.from({ length: 100 }, (_, i) => `CASE-${String(i).padStart(3, '0')}|base|medium|0`);

describe('seeded shuffle', () => {
  it('is a stable permutation for the same seed and rater', () => {
    const a = presentationOrder(set, 7731, 'R01');
    const b = presentationOrder(set, 7731, 'R01');
    expect(a).toEqual(b);
    expect([...a].sort()).toEqual([...set].sort());
    expect(a).not.toEqual(set);
  });
  it('differs between raters and between seeds', () => {
    const r1 = presentationOrder(set, 7731, 'R01');
    const r2 = presentationOrder(set, 7731, 'R02');
    const s2 = presentationOrder(set, 7732, 'R01');
    expect(r1).not.toEqual(r2);
    expect(r1).not.toEqual(s2);
  });
  it('does not mutate the input', () => {
    const copy = set.slice();
    seededShuffle(set, 1);
    expect(set).toEqual(copy);
  });
  it('hashSeed is deterministic and 32-bit', () => {
    expect(hashSeed(20261020, 'R01')).toBe(hashSeed(20261020, 'R01'));
    expect(hashSeed(20261020, 'R01')).not.toBe(hashSeed(20261020, 'R10'));
    expect(hashSeed(1, 'R01')).toBeGreaterThanOrEqual(0);
    expect(hashSeed(1, 'R01')).toBeLessThanOrEqual(0xffffffff);
  });
  it('pins a known order so a regression in the PRNG is caught', () => {
    const order = presentationOrder(['a', 'b', 'c', 'd', 'e', 'f'], 20261020, 'R01');
    // Snapshot of the current implementation; update deliberately if the algorithm changes.
    expect(order).toMatchInlineSnapshot(`
      [
        "a",
        "b",
        "f",
        "c",
        "d",
        "e",
      ]
    `);
  });
});
