import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { CaseFile } from '../types';
import { flattenTrace, applyFilters, EMPTY_FILTERS, ratesFromRows, silentUnderRule } from '../lib/cohort';
import { buildRiver, linkShare, riverPath } from '../charts/river';

const demo = resolve(__dirname, '../../public/demo');
const index = JSON.parse(readFileSync(resolve(demo, 'index.json'), 'utf8'));
const cll = JSON.parse(readFileSync(resolve(demo, 'cases/CLL-001.json'), 'utf8')) as CaseFile;
const rows = cll.traces.map((t) => flattenTrace(cll, t));

describe('flattenTrace', () => {
  it('derives the edit kind, outcome and assertions from the trace records', () => {
    const dec = rows.find((r) => r.variant === 'dec-cyclin_d1')!;
    expect(dec.edit_kind).toBe('decisive');
    expect(dec.primary_finding).toBe('cyclin_D1');
    expect(dec.outcome).toBeTruthy();
    expect(dec.asserted.length).toBeGreaterThan(0);
    const auth = rows.find((r) => r.variant === 'auth-wrong-mcl')!;
    expect(auth.edit_kind).toBe('authority_wrong');
    expect(auth.cue_entity).toBe('MCL');
    expect(rows.find((r) => r.variant === 'auth-right')!.edit_kind).toBe('authority_right');
    expect(rows.find((r) => r.variant === 'base')!.edit_kind).toBe('base');
  });
});

describe('buildRiver', () => {
  it('builds four columns with conserved flow and one path per perturbed trace', () => {
    const river = buildRiver(rows);
    const perturbed = rows.filter((r) => riverPath(r) !== null);
    expect(river.n).toBe(perturbed.length);
    expect(river.n).toBe(cll.traces.length - cll.traces.filter((t) => t.variant === 'base').length);
    for (const col of [0, 1, 2, 3]) {
      const total = river.nodes.filter((n) => n.column === col).reduce((a, n) => a + n.value, 0);
      expect(total).toBe(river.n);
    }
    for (const hop of [0, 1, 2]) {
      const flow = river.links.filter((l) => l.source.startsWith(`${hop}:`)).reduce((a, l) => a + l.value, 0);
      expect(flow).toBe(river.n);
    }
    expect(river.nodes.find((n) => n.id === '1:decisive')?.label).toBe('decisive edit');
    expect(river.nodes.filter((n) => n.column === 3).map((n) => n.key)).toEqual(expect.arrayContaining(['stable', 'held']));
    for (const l of river.links) {
      expect(l.trace_keys.length).toBe(l.value);
      expect(l.entity).toBe('CLL_SLL');
    }
  });
  it('reports a link share against its source node', () => {
    const river = buildRiver(rows);
    const l = river.links.find((x) => x.source === '1:decisive')!;
    const share = linkShare(river, l);
    expect(share.n).toBe(river.nodes.find((n) => n.id === '1:decisive')!.value);
    expect(share.k).toBeLessThanOrEqual(share.n);
  });
  it('is empty for base-only rows', () => {
    expect(buildRiver(rows.filter((r) => r.edit_kind === 'base')).n).toBe(0);
  });
});

describe('filters and recomputed rates', () => {
  it('silent under D1/D2/D3 follows the counterfactual flags', () => {
    const dec = rows.filter((r) => r.edit_kind === 'decisive' && r.changed_to_expected);
    expect(dec.length).toBeGreaterThan(0);
    for (const r of dec) {
      expect(silentUnderRule(r, 'D1')).toBe(!r.cited_primary);
      expect(silentUnderRule(r, 'D2')).toBe(!r.mentioned_primary);
      expect(silentUnderRule(r, 'D3')).toBe(!r.mentioned_any);
    }
    expect(silentUnderRule(rows.find((r) => r.edit_kind === 'neutral')!, 'D1')).toBeNull();
  });
  it('recomputed cohort-wide grounding matches the summary pooled rate when all cases are present', async () => {
    const all: ReturnType<typeof flattenTrace>[] = [];
    for (const c of index.cases) {
      const cf = JSON.parse(readFileSync(resolve(demo, c.file), 'utf8')) as CaseFile;
      all.push(...cf.traces.map((t) => flattenTrace(cf, t)));
    }
    const rates = ratesFromRows(all, 'D1');
    expect(rates.grounding.numerator).toBe(index.summary.grounding.pooled_rate.numerator);
    expect(rates.grounding.denominator).toBe(index.summary.grounding.pooled_rate.denominator);
    expect(rates.silent.numerator).toBe(index.summary.counterfactual.decisive.silent_rate.numerator);
    expect(rates.silent.denominator).toBe(index.summary.counterfactual.decisive.silent_rate.denominator);
    expect(rates.spurious.numerator).toBe(index.summary.counterfactual.neutral.spurious_rate.numerator);
    expect(rates.silentShift.numerator).toBe(index.summary.authority.wrong.silent_shift_rate.numerator);
    expect(rates.silentShift.denominator).toBe(index.summary.authority.wrong.silent_shift_rate.denominator);
    expect(applyFilters(all, { ...EMPTY_FILTERS, entity: 'MCL' }).every((r) => r.entity === 'MCL')).toBe(true);
    expect(applyFilters(all, { ...EMPTY_FILTERS, finding: 'cyclin_D1' }).length).toBeGreaterThan(0);
  });
});
