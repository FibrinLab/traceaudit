import { describe, expect, it } from 'vitest';
import type { Lexicon } from '../types';
import { entityColor, entityOrder, entitySlot, orderEntities, MAX_ENTITY_SLOTS } from '../lib/palette';
import { makeIncidentBundle } from './fixtures/incidentBundle';

const { lexicon } = makeIncidentBundle();

describe('category colour slots come from the lexicon', () => {
  it('assigns the top-level in-scope categories to slots in declared order', () => {
    expect(entityOrder(lexicon)).toEqual(['BAD_DEPLOY', 'CAPACITY', 'DATABASE', 'DISK']);
    expect(entitySlot(lexicon, 'BAD_DEPLOY')).toBe(1);
    expect(entitySlot(lexicon, 'DISK')).toBe(4);
    expect(entityColor(lexicon, 'CAPACITY')).toBe('var(--entity-2)');
    expect(entityColor(lexicon, 'UNRESOLVED')).toBe('var(--entity-other)');
    expect(entityColor(lexicon, null)).toBe('var(--entity-other)');
    expect(entityOrder(undefined)).toEqual([]);
  });
  it('folds sub-categories to their parent slot and caps at six slots', () => {
    const big: Lexicon = {
      version: '1', findings: [],
      entities: [
        ...['A', 'B', 'C', 'D', 'E', 'F', 'G'].map((id) => ({ id, display: id, in_scope: true, parent: null })),
        { id: 'A1', display: 'A one', in_scope: true, parent: 'A' },
        { id: 'OUT', display: 'Out of scope', in_scope: false, parent: null },
        { id: 'G1', display: 'G one', in_scope: true, parent: 'G' },
      ],
    };
    expect(entityOrder(big)).toEqual(['A', 'B', 'C', 'D', 'E', 'F']);
    expect(entityOrder(big).length).toBe(MAX_ENTITY_SLOTS);
    expect(entitySlot(big, 'A1')).toBe(1);
    expect(entitySlot(big, 'G')).toBe('other');
    expect(entitySlot(big, 'G1')).toBe('other');
    expect(entitySlot(big, 'OUT')).toBe('other');
  });
  it('orders an arbitrary set of ids by slot, then alphabetically', () => {
    expect(orderEntities(lexicon, new Set(['UNRESOLVED', 'DISK', 'BAD_DEPLOY', 'ZZZ']))).toEqual(['BAD_DEPLOY', 'DISK', 'UNRESOLVED', 'ZZZ']);
  });
});
