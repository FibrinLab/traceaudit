import type { Interval } from '../types';

/** Wilson score interval for a proportion; used only when a filter narrows below the precomputed facets. */
export function wilson(k: number, n: number, z = 1.96): Interval {
  if (n <= 0) return { point: null, lo: null, hi: null, numerator: k, denominator: n, n_records: n, ci_method: 'wilson' };
  const p = k / n;
  const z2 = z * z;
  const denom = 1 + z2 / n;
  const centre = (p + z2 / (2 * n)) / denom;
  const half = (z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))) / denom;
  return { point: p, lo: Math.max(0, centre - half), hi: Math.min(1, centre + half), numerator: k, denominator: n, n_records: n, ci_method: 'wilson' };
}
