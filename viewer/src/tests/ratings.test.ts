import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  DIMENSIONS, emptyTraceRating, exportFilename, isComplete, loadRatingState, ratingRecords, saveRatingState, storageKey, toJsonl, toggleTag, validateRecord,
  type RatingState,
} from '../lib/ratings';

const schema = JSON.parse(readFileSync(resolve(__dirname, '../../public/demo/ratings-schema.json'), 'utf8')) as {
  required: string[]; properties: Record<string, { type?: string | string[]; enum?: string[]; const?: unknown; pattern?: string; minimum?: number; maximum?: number }>;
};

function memStorage() {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => { m.set(k, v); }, removeItem: (k: string) => { m.delete(k); } };
}

function completeState(): RatingState {
  const r = emptyTraceRating('CLL-001|base|medium|2', 14, '2026-12-01T10:02:11Z');
  for (const d of DIMENSIONS) r.scores[d] = 3;
  r.scores.D7 = 2;
  r.error_tags = ['logical_leap', 'overconfidence'];
  r.comment = 'Reasonable but overconfident.';
  r.submitted_at = '2026-12-01T10:06:40Z';
  r.duration_ms = 269000;
  const incomplete = emptyTraceRating('CLL-001|base|low|1', 15, '2026-12-01T10:07:00Z');
  incomplete.scores.D1 = 4;
  return {
    session: { rater_id: 'R01', study_id: 'pilot-1', session_id: 'sess-1', order: [r.trace_key, incomplete.trace_key], started_at: '2026-12-01T10:00:00Z' },
    ratings: { [r.trace_key]: r, [incomplete.trace_key]: incomplete },
  };
}

/** Check a record against the JSON schema's type/enum/const/pattern/min/max constraints (no $ref in this schema). */
function checkAgainstSchema(rec: Record<string, unknown>): string[] {
  const errs: string[] = [];
  for (const k of schema.required) if (!(k in rec)) errs.push(`missing ${k}`);
  for (const [k, v] of Object.entries(rec)) {
    const p = schema.properties[k];
    if (!p) { errs.push(`unknown property ${k}`); continue; }
    const types = p.type ? (Array.isArray(p.type) ? p.type : [p.type]) : null;
    const jsType = v === null ? 'null' : Array.isArray(v) ? 'array' : Number.isInteger(v) ? 'integer' : typeof v;
    if (types && !types.includes(jsType) && !(jsType === 'integer' && types.includes('number'))) errs.push(`${k}: type ${jsType} not in ${types}`);
    if (p.enum && !p.enum.includes(v as string)) errs.push(`${k}: ${v} not in enum`);
    if ('const' in p && v !== p.const) errs.push(`${k}: const mismatch`);
    if (p.pattern && typeof v === 'string' && !new RegExp(p.pattern).test(v)) errs.push(`${k}: pattern`);
    if (typeof v === 'number' && p.minimum !== undefined && v < p.minimum) errs.push(`${k}: < min`);
    if (typeof v === 'number' && p.maximum !== undefined && v > p.maximum) errs.push(`${k}: > max`);
  }
  return errs;
}

describe('rating persistence', () => {
  it('round-trips through storage under a namespaced key', () => {
    const st = memStorage();
    const s = completeState();
    saveRatingState(st, 'run-1', s);
    expect(st.getItem(storageKey('run-1', 'pilot-1', 'R01'))).not.toBeNull();
    expect(loadRatingState(st, 'run-1', 'pilot-1', 'R01')).toEqual(s);
    expect(loadRatingState(st, 'run-2', 'pilot-1', 'R01')).toBeNull();
    expect(loadRatingState(st, 'run-1', 'pilot-1', 'R02')).toBeNull();
  });
  it('tolerates corrupt storage', () => {
    const st = memStorage();
    st.setItem(storageKey('r', 's', 'R01'), '{not json');
    expect(loadRatingState(st, 'r', 's', 'R01')).toBeNull();
  });
});

describe('tags and completeness', () => {
  it('makes `none` exclusive', () => {
    expect(toggleTag([], 'none')).toEqual(['none']);
    expect(toggleTag(['none'], 'logical_leap')).toEqual(['logical_leap']);
    expect(toggleTag(['logical_leap', 'overconfidence'], 'none')).toEqual(['none']);
    expect(toggleTag(['none'], 'none')).toEqual([]);
    expect(toggleTag(['logical_leap'], 'logical_leap')).toEqual([]);
  });
  it('requires all seven scores and at least one tag', () => {
    const s = completeState();
    expect(isComplete(s.ratings['CLL-001|base|medium|2'])).toBe(true);
    expect(isComplete(s.ratings['CLL-001|base|low|1'])).toBe(false);
    expect(isComplete(undefined)).toBe(false);
  });
});

describe('export format (spec 12 §5)', () => {
  const meta = { viewer_version: '0.1.0', bundle_run_id: '20261020T011914Z-3un4d5' };
  it('emits one record per dimension plus one tags record for complete traces only', () => {
    const recs = ratingRecords(completeState(), meta);
    expect(recs.length).toBe(8);
    expect(recs.filter((r) => r.dimension === 'tags').length).toBe(1);
    expect(recs.map((r) => r.dimension)).toEqual([...DIMENSIONS, 'tags']);
    const tags = recs.find((r) => r.dimension === 'tags')!;
    expect(tags.score).toBeNull();
    expect(tags.error_tags).toEqual(['logical_leap', 'overconfidence']);
    expect(tags.comment).toBe('Reasonable but overconfident.');
    const d7 = recs.find((r) => r.dimension === 'D7')!;
    expect(d7.score).toBe(2);
    expect(d7.error_tags).toBeNull();
    expect(d7.comment).toBeNull();
    for (const r of recs) {
      expect(r).toMatchObject({ schema_version: 1, study_id: 'pilot-1', rater_id: 'R01', session_id: 'sess-1', trace_key: 'CLL-001|base|medium|2', presentation_index: 14, started_at: '2026-12-01T10:02:11Z', submitted_at: '2026-12-01T10:06:40Z', duration_ms: 269000, blinded: true, viewer_version: '0.1.0', bundle_run_id: meta.bundle_run_id });
      expect(validateRecord(r)).toEqual([]);
      expect(checkAgainstSchema(r as unknown as Record<string, unknown>)).toEqual([]);
    }
  });
  it('can include incomplete traces when asked', () => {
    const recs = ratingRecords(completeState(), meta, true);
    expect(recs.filter((r) => r.trace_key === 'CLL-001|base|low|1').map((r) => r.dimension)).toEqual(['D1']);
  });
  it('serialises as JSONL with a trailing newline', () => {
    const txt = toJsonl(ratingRecords(completeState(), meta));
    const lines = txt.split('\n');
    expect(lines[lines.length - 1]).toBe('');
    expect(lines.length - 1).toBe(8);
    for (const l of lines.slice(0, -1)) expect(() => JSON.parse(l)).not.toThrow();
    expect(exportFilename('pilot-1', 'R01')).toBe('ratings-pilot-1-R01.jsonl');
  });
  it('validateRecord catches schema violations', () => {
    const [rec] = ratingRecords(completeState(), meta);
    expect(validateRecord({ ...rec, rater_id: 'Alice' })).toContain('rater_id must match ^R\\d{2}$');
    expect(validateRecord({ ...rec, score: 5 }).length).toBeGreaterThan(0);
    expect(validateRecord({ ...rec, dimension: 'D9' }).length).toBeGreaterThan(0);
  });
});
