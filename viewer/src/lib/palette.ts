// Colour roles: entity categorical (fixed slot order, validated in tokens.css), ordinal greys-to-accent, and status tokens.
import type { Lexicon, Outcome } from '../types';

export const ENTITY_ORDER = ['CLL_SLL', 'MCL', 'FL', 'HCL', 'LPL', 'MZL'] as const;
export type EntitySlot = (typeof ENTITY_ORDER)[number];

/** Short entity label for chart marks and legends. */
export function entityShort(id: string | null | undefined): string {
  if (!id) return 'unresolved';
  if (id === 'CLL_SLL') return 'CLL/SLL';
  if (id === 'UNRESOLVED') return 'unresolved';
  return id;
}

/** Fold a sub-entity (WM, SMZL…) to its colour slot via the lexicon parent; others to the neutral slot. */
export function entitySlot(lexicon: Lexicon | undefined, id: string | null | undefined): EntitySlot | 'other' {
  if (!id) return 'other';
  if ((ENTITY_ORDER as readonly string[]).includes(id)) return id as EntitySlot;
  const e = lexicon?.entities.find((x) => x.id === id);
  if (e?.parent && (ENTITY_ORDER as readonly string[]).includes(e.parent)) return e.parent as EntitySlot;
  return 'other';
}

export function entityColor(lexicon: Lexicon | undefined, id: string | null | undefined): string {
  return `var(--entity-${entitySlot(lexicon, id)})`;
}

export const OUTCOME_COLOR: Record<Outcome, string> = {
  disclosed: 'var(--supported)',
  silent: 'var(--contradicted)',
  missed: 'var(--unsupported)',
  hedged: 'var(--supported)',
  unhedged: 'var(--contradicted)',
  spurious: 'var(--contradicted)',
  stable: 'var(--supported)',
  shifted_ack: 'var(--unsupported)',
  shifted_silent: 'var(--contradicted)',
  held: 'var(--supported)',
  already_agreed: 'var(--neutral)',
};

export const OUTCOME_GLYPH: Record<Outcome, string> = {
  disclosed: '✓', silent: '!', missed: '✗', hedged: '≈', unhedged: '!', spurious: '!', stable: '✓',
  shifted_ack: '≈', shifted_silent: '!', held: '✓', already_agreed: '=',
};

export const KIND_LABEL: Record<string, string> = {
  base: 'base', decisive: 'decisive edit', anchor_loss: 'anchor loss', neutral: 'neutral edit',
  authority_wrong: 'wrong cue', authority_right: 'correct cue', authority: 'authority cue',
};

/** Seven-step one-hue (accent) heat ramp as CSS variables; t in [0,1]. */
export function heat(t: number): string {
  const i = Math.max(0, Math.min(6, Math.round(t * 6)));
  return `var(--heat-${i})`;
}

/** Seven-step semantic heat ramp (neutral → amber → contradicted red); t in [0,1]. */
export function warm(t: number): string {
  const i = Math.max(0, Math.min(6, Math.round(t * 6)));
  return `var(--warm-${i})`;
}

/** Deterministic PRNG (mulberry32) for stable layouts. */
export function seeded(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}
