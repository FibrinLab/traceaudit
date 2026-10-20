// Colour roles: category categorical slots (taken from the bundle's lexicon, validated in tokens.css), ordinal
// greys-to-accent, and status tokens. Nothing here knows any particular domain.
import type { Lexicon, Outcome } from '../types';

/** The number of categorical colour slots in tokens.css (`--entity-1` … `--entity-6`). */
export const MAX_ENTITY_SLOTS = 6;

/** The lexicon's top-level in-scope categories in declared order: these take the colour slots, one each, up to six.
 *  Sub-categories fold to their parent's slot; anything else (out of scope, beyond six, unresolved) is grey. */
export function entityOrder(lexicon: Lexicon | undefined | null): string[] {
  if (!lexicon) return [];
  return lexicon.entities.filter((e) => e.in_scope !== false && !e.parent).map((e) => e.id).slice(0, MAX_ENTITY_SLOTS);
}

/** Short category label for chart marks and legends: the id as the lexicon spells it. */
export function entityShort(id: string | null | undefined): string {
  if (!id || id === 'UNRESOLVED') return 'unresolved';
  return id;
}

/** The 1-based colour slot of a category, via its parent for sub-categories; 'other' for the neutral slot. */
export function entitySlot(lexicon: Lexicon | undefined | null, id: string | null | undefined): number | 'other' {
  if (!id || !lexicon) return 'other';
  const order = entityOrder(lexicon);
  const direct = order.indexOf(id);
  if (direct >= 0) return direct + 1;
  const e = lexicon.entities.find((x) => x.id === id);
  const viaParent = e?.parent ? order.indexOf(e.parent) : -1;
  return viaParent >= 0 ? viaParent + 1 : 'other';
}

export function entityColor(lexicon: Lexicon | undefined | null, id: string | null | undefined): string {
  return `var(--entity-${entitySlot(lexicon, id)})`;
}

/** Order a set of category ids: lexicon slot order first, then anything else alphabetically. */
export function orderEntities(lexicon: Lexicon | undefined | null, ids: Iterable<string>): string[] {
  const present = new Set(ids);
  const order = entityOrder(lexicon);
  return [...order.filter((e) => present.has(e)), ...[...present].filter((e) => !order.includes(e)).sort()];
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
