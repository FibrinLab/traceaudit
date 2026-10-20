import type { MapNode } from '../types';

/** Key used to match nodes across base and perturbed maps (spec 13 §8 overlay). */
export function nodeMatchKey(n: MapNode): string {
  return `${n.type}|${[...n.findings].sort().join(',')}|${[...n.entities].sort().join(',')}`;
}
