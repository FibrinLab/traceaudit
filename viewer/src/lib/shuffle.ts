// Deterministic rater-specific presentation order (spec 13 §6).
// hash(blinding_seed, rater_id) -> 32-bit seed -> mulberry32 PRNG -> Fisher–Yates.

/** FNV-1a 32-bit over `${seed}:${raterId}`. Stable across platforms, no BigInt. */
export function hashSeed(blindingSeed: number, raterId: string): number {
  const s = `${blindingSeed}:${raterId}`;
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Seeded Fisher–Yates; returns a new array, input untouched. */
export function seededShuffle<T>(items: readonly T[], seed: number): T[] {
  const out = items.slice();
  const rnd = mulberry32(seed);
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    const tmp = out[i];
    out[i] = out[j];
    out[j] = tmp;
  }
  return out;
}

export function presentationOrder(ratingSet: readonly string[], blindingSeed: number, raterId: string): string[] {
  return seededShuffle(ratingSet, hashSeed(blindingSeed, raterId));
}
